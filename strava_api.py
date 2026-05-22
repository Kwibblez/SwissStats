"""
strava_api.py — Wrapper pour l'API Strava v3
Gère le rate limiting (100 req/15min) automatiquement.
"""

import time
import requests


class StravaAPI:
    BASE_URL = "https://www.strava.com/api/v3"

    def __init__(self, client_id, client_secret):
        self.client_id     = client_id
        self.client_secret = client_secret
        self.access_token  = None
        self.refresh_token = None
        self.expires_at    = 0

    def set_tokens(self, access_token, refresh_token, expires_at):
        self.access_token  = access_token
        self.refresh_token = refresh_token
        self.expires_at    = int(expires_at)

    # ── OAuth ────────────────────────────────────────────────

    def exchange_code(self, code, redirect_uri):
        resp = requests.post("https://www.strava.com/oauth/token", data={
            "client_id":     self.client_id,
            "client_secret": self.client_secret,
            "code":          code,
            "grant_type":    "authorization_code",
            "redirect_uri":  redirect_uri,
        })
        resp.raise_for_status()
        return resp.json()

    def refresh_if_needed(self):
        if time.time() < self.expires_at - 60:
            return None
        resp = requests.post("https://www.strava.com/oauth/token", data={
            "client_id":     self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type":    "refresh_token",
        })
        resp.raise_for_status()
        data = resp.json()
        self.access_token  = data["access_token"]
        self.refresh_token = data["refresh_token"]
        self.expires_at    = data["expires_at"]
        return data

    def _get(self, endpoint, params=None, _retry=3):
        """Requête GET avec gestion automatique du rate limit (429)."""
        self.refresh_if_needed()
        headers = {"Authorization": f"Bearer {self.access_token}"}
        resp = requests.get(f"{self.BASE_URL}{endpoint}",
                            headers=headers, params=params)

        # Rate limit atteint → attend et réessaie
        if resp.status_code == 429 and _retry > 0:
            wait = int(resp.headers.get("X-RateLimit-Reset", 60))
            # Attend au max 60s pour ne pas bloquer trop longtemps
            time.sleep(min(wait, 60))
            return self._get(endpoint, params, _retry - 1)

        resp.raise_for_status()
        return resp.json()

    # ── Activités ────────────────────────────────────────────

    def get_activities_for_year(self, year: int):
        after  = int(time.mktime((year,  1,  1, 0, 0, 0, 0, 0, 0)))
        before = int(time.mktime((year, 12, 31, 23, 59, 59, 0, 0, 0)))

        activities = []
        page = 1
        while True:
            batch = self._get("/athlete/activities", params={
                "after":    after,
                "before":   before,
                "per_page": 200,
                "page":     page,
            })
            if not batch:
                break
            activities.extend(batch)
            if len(batch) < 200:
                break
            page += 1

        return activities

    def get_activity_detail(self, activity_id: int):
        return self._get(f"/activities/{activity_id}")

    def get_latlng_stream(self, activity_id: int):
        try:
            data = self._get(f"/activities/{activity_id}/streams", params={
                "keys":        "latlng",
                "key_by_type": "true",
            })
            if "latlng" in data:
                return data["latlng"]["data"]
        except requests.HTTPError as e:
            if e.response.status_code in (404, 403):
                return None
            raise
        return None

    def get_athlete(self):
        return self._get("/athlete")
