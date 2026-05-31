"""
strava_api.py — Wrapper pour l'API Strava v3
=============================================
Ce module encapsule toutes les interactions avec l'API REST de Strava.
Il gère automatiquement :
  - L'échange du code OAuth contre des tokens d'accès
  - Le rafraîchissement du token lorsqu'il expire
  - Le rate limiting de Strava (100 requêtes / 15 minutes)
  - La pagination des résultats

Documentation Strava API : https://developers.strava.com/docs/reference/

HEIG-VD 2026 — Fardel, Perroud, Smith
"""

import time
import requests


class StravaAPI:
    """
    Client pour l'API Strava v3.

    Utilisation typique :
        strava = StravaAPI(client_id, client_secret)
        strava.exchange_code(code, redirect_uri)     # OAuth
        strava.set_tokens(access, refresh, expires)  # depuis la DB
        activities = strava.get_activities_for_year(2024)
    """

    BASE_URL = "https://www.strava.com/api/v3"

    def __init__(self, client_id: str, client_secret: str):
        """
        Initialise le client avec les credentials de l'application Strava.

        Args:
            client_id:     L'ID client de l'app (visible sur strava.com/settings/api)
            client_secret: Le secret client de l'app
        """
        self.client_id     = client_id
        self.client_secret = client_secret
        self.access_token  = None   # Token d'accès valide ~6h
        self.refresh_token = None   # Token de rafraîchissement (longue durée)
        self.expires_at    = 0      # Timestamp Unix d'expiration de l'access token

    def set_tokens(self, access_token: str, refresh_token: str, expires_at: int):
        """
        Charge les tokens depuis la base de données (après connexion initiale).

        Args:
            access_token:  Token Bearer pour les requêtes API
            refresh_token: Token pour obtenir un nouvel access token
            expires_at:    Timestamp Unix d'expiration de l'access token
        """
        self.access_token  = access_token
        self.refresh_token = refresh_token
        self.expires_at    = int(expires_at)

    # ── OAuth 2.0 ────────────────────────────────────────────────────────────

    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """
        Échange le code d'autorisation OAuth contre des tokens d'accès.
        Appelé une seule fois lors de la première connexion de l'utilisateur.

        Args:
            code:         Code reçu de Strava dans le callback URL
            redirect_uri: URL de redirection (doit correspondre aux paramètres Strava)

        Returns:
            dict contenant access_token, refresh_token, expires_at, et athlete
        """
        resp = requests.post("https://www.strava.com/oauth/token", data={
            "client_id":     self.client_id,
            "client_secret": self.client_secret,
            "code":          code,
            "grant_type":    "authorization_code",
            "redirect_uri":  redirect_uri,
        })
        resp.raise_for_status()
        return resp.json()

    def refresh_if_needed(self) -> dict | None:
        """
        Rafraîchit l'access token s'il expire dans moins de 60 secondes.
        Le token Strava est valide environ 6 heures.

        Returns:
            dict avec les nouveaux tokens si rafraîchis, None sinon
        """
        # Si le token est encore valide, rien à faire
        if time.time() < self.expires_at - 60:
            return None

        # Le token a expiré → on en demande un nouveau avec le refresh_token
        resp = requests.post("https://www.strava.com/oauth/token", data={
            "client_id":     self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type":    "refresh_token",
        })
        resp.raise_for_status()
        data = resp.json()

        # Met à jour les tokens en mémoire
        self.access_token  = data["access_token"]
        self.refresh_token = data["refresh_token"]
        self.expires_at    = data["expires_at"]
        return data

    # ── Requête HTTP interne ─────────────────────────────────────────────────

    def _get(self, endpoint: str, params: dict = None, _retry: int = 3) -> dict:
        """
        Effectue une requête GET authentifiée vers l'API Strava.
        Gère automatiquement le rate limiting (HTTP 429).

        Strava limite à 100 requêtes/15min et 1000 requêtes/jour.
        En cas de dépassement, Strava répond avec HTTP 429 et un header
        X-RateLimit-Reset indiquant quand réessayer.

        Args:
            endpoint: Chemin de l'endpoint (ex: "/athlete/activities")
            params:   Paramètres de requête optionnels
            _retry:   Nombre de tentatives restantes (évite les boucles infinies)

        Returns:
            Réponse JSON de l'API sous forme de dict ou list
        """
        self.refresh_if_needed()

        headers = {"Authorization": f"Bearer {self.access_token}"}
        resp    = requests.get(
            f"{self.BASE_URL}{endpoint}",
            headers=headers,
            params=params
        )

        # Rate limit atteint → attendre avant de réessayer
        if resp.status_code == 429 and _retry > 0:
            # Strava indique dans le header combien de secondes attendre
            wait = int(resp.headers.get("X-RateLimit-Reset", 60))
            # On attend au maximum 60s pour ne pas bloquer trop longtemps
            time.sleep(min(wait, 60))
            return self._get(endpoint, params, _retry - 1)

        resp.raise_for_status()
        return resp.json()

    # ── Activités ────────────────────────────────────────────────────────────

    def get_activities_for_year(self, year: int) -> list:
        """
        Récupère toutes les activités d'un utilisateur pour une année donnée.

        L'API Strava pagine les résultats par 200 max. Cette méthode
        parcourt automatiquement toutes les pages jusqu'à tout récupérer.

        Les timestamps Unix sont calculés pour couvrir du 1er janvier
        au 31 décembre de l'année demandée.

        Args:
            year: Année à récupérer (ex: 2024)

        Returns:
            Liste de dicts représentant chaque activité Strava
        """
        # Conversion des bornes de l'année en timestamps Unix
        after  = int(time.mktime((year,  1,  1,  0,  0,  0, 0, 0, 0)))
        before = int(time.mktime((year, 12, 31, 23, 59, 59, 0, 0, 0)))

        activities = []
        page       = 1

        while True:
            # Récupère une page de 200 activités maximum
            batch = self._get("/athlete/activities", params={
                "after":    after,
                "before":   before,
                "per_page": 200,
                "page":     page,
            })

            if not batch:
                break  # Plus rien à récupérer

            activities.extend(batch)

            if len(batch) < 200:
                break  # Dernière page atteinte

            page += 1  # Passe à la page suivante

        return activities

    def get_activity_detail(self, activity_id: int) -> dict:
        """
        Récupère le détail complet d'une activité.
        Contrairement à la liste, le détail inclut les calories.

        Args:
            activity_id: Identifiant Strava de l'activité

        Returns:
            dict complet de l'activité avec tous les champs
        """
        return self._get(f"/activities/{activity_id}")

    def get_latlng_stream(self, activity_id: int) -> list | None:
        """
        Récupère le stream GPS (latitude/longitude) d'une activité.
        Toutes les activités n'ont pas de GPS (ex: natation en piscine).

        Args:
            activity_id: Identifiant Strava de l'activité

        Returns:
            Liste de [lat, lng] ou None si pas de données GPS
        """
        try:
            data = self._get(f"/activities/{activity_id}/streams", params={
                "keys":        "latlng",
                "key_by_type": "true",
            })
            if "latlng" in data:
                return data["latlng"]["data"]   # [[lat, lng], [lat, lng], ...]
        except requests.HTTPError as e:
            # 404 = activité sans stream GPS, 403 = accès refusé
            if e.response.status_code in (404, 403):
                return None
            raise
        return None

    def get_athlete(self) -> dict:
        """
        Récupère le profil de l'athlète connecté.

        Returns:
            dict avec les informations du profil Strava
        """
        return self._get("/athlete")
