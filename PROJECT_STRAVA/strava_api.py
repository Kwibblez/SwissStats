"""
strava_api.py — Wrapper pour l'API Strava v3
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
        """Échange le code OAuth contre des tokens."""
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
        """Rafraîchit l'access token s'il expire dans moins de 60s."""
        if time.time() < self.expires_at - 60:
            return None   # encore valide

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

    def _get(self, endpoint, params=None):
        """Requête GET authentifiée."""
        self.refresh_if_needed()
        headers = {"Authorization": f"Bearer {self.access_token}"}
        resp = requests.get(f"{self.BASE_URL}{endpoint}",
                            headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()

    # ── Activités ────────────────────────────────────────────

    def get_activities_for_year(self, year: int):
        """
        Retourne toutes les activités d'une année donnée (pagination auto).
        Strava filtre par timestamp Unix (after/before).
        """
        import calendar
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
        """Détail complet d'une activité (inclut les segments, etc.)."""
        return self._get(f"/activities/{activity_id}")

    # ── Streams GPS ──────────────────────────────────────────

    def get_latlng_stream(self, activity_id: int):
        """
        Retourne la liste de [lat, lng] du parcours GPS.
        Retourne None si l'activité n'a pas de GPS.
        """
        try:
            data = self._get(f"/activities/{activity_id}/streams", params={
                "keys":           "latlng",
                "key_by_type":    "true",
            })
            if "latlng" in data:
                return data["latlng"]["data"]   # [[lat, lng], ...]
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise
        return None

    def get_full_streams(self, activity_id: int):
        """
        Retourne tous les streams utiles :
        latlng, altitude, heartrate, cadence, velocity_smooth, time
        """
        keys = "latlng,altitude,heartrate,cadence,velocity_smooth,time"
        try:
            return self._get(f"/activities/{activity_id}/streams", params={
                "keys":        keys,
                "key_by_type": "true",
            })
        except requests.HTTPError:
            return {}

    # ── Athlète ──────────────────────────────────────────────

    def get_athlete(self):
        return self._get("/athlete")

    def get_athlete_stats(self, athlete_id: int):
        return self._get(f"/athletes/{athlete_id}/stats")
