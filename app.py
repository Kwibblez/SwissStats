"""
SwissStats — Application Flask + PostGIS
HEIG-VD 2026 — Fardel, Perroud, Smith
"""

import os
import json
import threading
import uuid

from flask import Flask, redirect, request, session, url_for, render_template, jsonify, Response
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras

from strava_api import StravaAPI
from db import get_db_connection, init_db

load_dotenv() # Charge les variables d'environnement depuis le fichier .env

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change_me_in_prod")


# Identifiants Strava
STRAVA_CLIENT_ID     = os.getenv("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
STRAVA_REDIRECT_URI  = os.getenv("STRAVA_REDIRECT_URI", "http://localhost:5000/callback")
STRAVA_SCOPES        = "read,activity:read_all"

SYNC_JOBS = {}

# Permet de passer d'une polyligne à liste de coordonnées (longitude et latitude)
def _decode_polyline(polyline_str):
    """Décode un Google Encoded Polyline en liste de [lat, lng]."""
    coords = []
    index, lat, lng = 0, 0, 0
    while index < len(polyline_str):
        for is_lng in [False, True]:
            shift, result = 0, 0
            while True:
                b = ord(polyline_str[index]) - 63 # décalage ASCII standard
                index += 1
                result |= (b & 0x1f) << shift # accumule les 5 bits utiles
                shift += 5
                if b < 0x20:
                    break
            value = ~(result >> 1) if result & 1 else result >> 1
            if is_lng:
                lng += value
                coords.append((lng / 1e5, lat / 1e5))  # conversion en degrés décimaux
            else:
                lat += value
    return coords


def estimate_calories(moving_time_s, avg_heartrate):
    """Estimation calories via FC et durée (formule ACSM, 65kg/25ans)."""
    if moving_time_s and avg_heartrate:
        mins = moving_time_s / 60.0
        kcal = (-55.0969 + 0.6309 * avg_heartrate + 0.1988 * 65 + 0.2017 * 25) / 4.184 * mins
        return max(0, round(kcal))
    if moving_time_s:
        return round(moving_time_s / 3600 * 600)
    return 0


# ═══════════════════════════════════════════════════════════════
# OAUTH STRAVA
# ═══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    if "user_id" not in session:
        return render_template("login.html")
    return redirect(url_for("map_view"))
# affiche la carte si l'utilisateur est déjà connecté, sinon login


@app.route("/login")
def login(): # redirige l'utilisateur vers la page d'identification de strava
    auth_url = (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={STRAVA_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={STRAVA_REDIRECT_URI}"
        f"&approval_prompt=auto"
        f"&scope={STRAVA_SCOPES}"
    )
    return redirect(auth_url)


@app.route("/callback")
def callback():
    # après avoir faire l'identification, strava redirige ici avec un code temporaire
    code = request.args.get("code")
    if not code:
        return "Erreur : pas de code reçu de Strava.", 400
    # avec ce code, on peut récupérer les données de l'utilisateur
    strava     = StravaAPI(STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET)
    token_data = strava.exchange_code(code, STRAVA_REDIRECT_URI)
    athlete    = token_data.get("athlete", {})

    # les infos sur l'utilisateur sont mises dans la DB
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (strava_id, access_token, refresh_token,
                                   token_expires_at, firstname, lastname,
                                   profile_pic_url, city, country)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (strava_id) DO UPDATE SET
                    access_token     = EXCLUDED.access_token,
                    refresh_token    = EXCLUDED.refresh_token,
                    token_expires_at = EXCLUDED.token_expires_at,
                    updated_at       = NOW()
                RETURNING id
            """, (
                athlete.get("id"),
                token_data["access_token"],
                token_data["refresh_token"],
                token_data["expires_at"],
                athlete.get("firstname"),
                athlete.get("lastname"),
                athlete.get("profile"),
                athlete.get("city"),
                athlete.get("country"),
            ))
            user_id = cur.fetchone()[0]
            conn.commit()

    # stocke les infos en session flask
    session["user_id"]   = user_id
    session["strava_id"] = athlete.get("id")
    session["firstname"] = athlete.get("firstname", "Athlete")
    return redirect(url_for("map_view"))


@app.route("/logout")
def logout():
    # détruit les infos de l'utilisateur et renvoie à la page d'acceuil
    session.clear()
    return redirect(url_for("index"))



# SYNC STRAVA

@app.route("/sync") # synchronise avec les données de l'utilisateur, on va récupérer toutes ses activités par année
def sync_start():
    if "user_id" not in session:
        return jsonify({"error": "non connecte"}), 401

    year    = request.args.get("year", 2024, type=int)
    user_id = session["user_id"]
    job_id  = str(uuid.uuid4())[:8]

    SYNC_JOBS[job_id] = {
        "done": 0, "total": 0, "pct": 0,
        "msg": "Demarrage...", "finished": False, "error": None
    }

    def run():  # permet de synchroniser les données
        try: # on récupère les infos de l'utilisateur depuis la DB
            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
                    user = cur.fetchone()

            if not user:
                SYNC_JOBS[job_id].update({"finished": True,
                                          "error": "Utilisateur introuvable - reconnecte-toi"})
                return

            strava = StravaAPI(STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET)
            strava.set_tokens(user["access_token"], user["refresh_token"],
                              user["token_expires_at"])
            strava.refresh_if_needed()

            activities = strava.get_activities_for_year(year)
            total = len(activities)
            SYNC_JOBS[job_id].update({"total": total, "msg": f"{total} activites trouvees..."})

            saved = 0
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    for act in activities:
                        name     = act.get("name", "Activite")
                        track_wkt = None
                        has_gpx   = False

                        calories = estimate_calories(
                            act.get("moving_time"),
                            act.get("average_heartrate")
                        )

                        # Décode le polyline → pour PostGIS
                        polyline_str = (act.get("map") or {}).get("summary_polyline", "")
                        if polyline_str:
                            coords = _decode_polyline(polyline_str)
                            if len(coords) > 1:
                                has_gpx   = True
                                pts       = ", ".join(f"{lng} {lat}" for lng, lat in coords)
                                track_wkt = f"LINESTRING({pts})"

                        start_ll = act.get("start_latlng") or [None, None]
                        end_ll   = act.get("end_latlng")   or [None, None]
                        # coordonnées de départ/ arrivée
                        if len(start_ll) < 2: start_ll = [None, None]
                        if len(end_ll)   < 2: end_ll   = [None, None]

                        cur.execute("""
                            INSERT INTO activities (
                                strava_id, user_id, name, sport_type,
                                start_date, start_date_local, timezone,
                                distance_m, moving_time_s, elapsed_time_s,
                                total_elevation_m, calories,
                                average_speed_ms, max_speed_ms,
                                average_heartrate, max_heartrate,
                                average_cadence, average_watts, suffer_score,
                                start_lat, start_lng, end_lat, end_lng,
                                track_geom, has_gpx, manual, commute
                            ) VALUES (
                                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                                %s,%s,%s,%s,%s,%s,%s,%s,%s,
                                ST_GeomFromText(%s, 4326),
                                %s,%s,%s
                            )
                            ON CONFLICT (strava_id) DO UPDATE SET
                                track_geom = EXCLUDED.track_geom,
                                has_gpx    = EXCLUDED.has_gpx,
                                calories   = EXCLUDED.calories
                        """, (
                            act["id"], user_id,
                            act.get("name"), act.get("sport_type"),
                            act.get("start_date"), act.get("start_date_local"),
                            act.get("timezone"),
                            act.get("distance"), act.get("moving_time"),
                            act.get("elapsed_time"), act.get("total_elevation_gain"),
                            calories,
                            act.get("average_speed"), act.get("max_speed"),
                            act.get("average_heartrate"), act.get("max_heartrate"),
                            act.get("average_cadence"), act.get("average_watts"),
                            act.get("suffer_score"),
                            start_ll[0], start_ll[1],
                            end_ll[0],   end_ll[1],
                            track_wkt, has_gpx,
                            act.get("manual", False), act.get("commute", False),
                        ))
                        saved += 1
                        # mise à jour de la progression
                        pct = round((saved / total) * 100) if total else 100
                        SYNC_JOBS[job_id].update({"done": saved, "pct": pct, "msg": name})

                    conn.commit()

            SYNC_JOBS[job_id].update({
                "pct": 100, "finished": True,
                "msg": f"{saved} activites synchronisees !"
            })
        except Exception as e:
            SYNC_JOBS[job_id].update({"finished": True, "error": str(e)})
            # affiche message erreur si erreur

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/sync/status")
def sync_status():
    # permet d'afficher une barre de progression pour la synchronisation
    job_id = request.args.get("job_id")
    if not job_id or job_id not in SYNC_JOBS:
        return jsonify({"error": "job inconnu"}), 404
    return jsonify(SYNC_JOBS[job_id])


# CARTE
@app.route("/map")
def map_view(): # affiche la carte
    if "user_id" not in session:
        return redirect(url_for("login"))
    year = request.args.get("year", 2024, type=int)
    return render_template("map.html", firstname=session.get("firstname"), year=year)


@app.route("/api/tracks")
def api_tracks():
    if "user_id" not in session:
        return jsonify({"error": "non connecte"}), 401

    year       = request.args.get("year", 2024, type=int)
    sport_type = request.args.get("sport")
    # script pour récupérer toutes les infos utiles de la DB
    query = """
        SELECT strava_id, name, sport_type, start_date_local,
            ROUND((distance_m / 1000.0)::numeric, 2)    AS distance_km,
            moving_time_s,
            ROUND(total_elevation_m::numeric)            AS elevation_m,
            ROUND((average_speed_ms * 3.6)::numeric, 1) AS avg_speed_kmh,
            average_heartrate, calories,
            ST_AsGeoJSON(track_geom)::json               AS geojson
        FROM activities
        WHERE user_id = %s
          AND EXTRACT(YEAR FROM start_date_local) = %s
          AND track_geom IS NOT NULL
    """
    params = [session["user_id"], year]
    # tri en fonction de l'activité (si indiqué)
    if sport_type:
        query += " AND sport_type = %s"
        params.append(sport_type)

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    # construction du GeoJSON
    features = []
    for row in rows:
        features.append({
            "type": "Feature",
            "geometry": row["geojson"],
            "properties": {
                "id":            row["strava_id"],
                "name":          row["name"],
                "sport_type":    row["sport_type"],
                "date":          str(row["start_date_local"]),
                "distance_km":   row["distance_km"],
                "moving_time_s": row["moving_time_s"],
                "elevation_m":   row["elevation_m"],
                "avg_speed":     row["avg_speed_kmh"],
                "heartrate":     row["average_heartrate"],
                "calories":      row["calories"],
            }
        })

    return jsonify({"type": "FeatureCollection", "features": features})



# STATISTIQUES


@app.route("/stats")
def stats_view():
    # retourne les différentes statistiques
    if "user_id" not in session:
        return redirect(url_for("login"))
    year = request.args.get("year", 2024, type=int)
    return render_template("stats.html", firstname=session.get("firstname"), year=year)


@app.route("/api/stats")
def api_stats():
    if "user_id" not in session:
        return jsonify({"error": "non connecte"}), 401

    year = request.args.get("year", 2024, type=int)
    # récupère les infos utiles de la DB
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # récupère les différents totaux de l'année
            cur.execute("""
                SELECT COUNT(*) AS nb_activities,
                    COALESCE(SUM(distance_m), 0)        AS total_m,
                    COALESCE(SUM(moving_time_s), 0)     AS total_seconds,
                    COALESCE(SUM(total_elevation_m), 0) AS total_elevation,
                    COALESCE(SUM(calories), 0)          AS total_calories,
                    COALESCE(AVG(average_heartrate), 0) AS avg_heartrate
                FROM activities
                WHERE user_id = %s AND EXTRACT(YEAR FROM start_date_local) = %s
            """, (session["user_id"], year))
            totals = dict(cur.fetchone())


            # récupère les totaux par type de sport
            cur.execute("""
                SELECT sport_type, COUNT(*) AS nb,
                    ROUND((SUM(distance_m)/1000)::numeric, 1) AS km,
                    ROUND(SUM(calories)::numeric) AS kcal
                FROM activities
                WHERE user_id = %s AND EXTRACT(YEAR FROM start_date_local) = %s
                GROUP BY sport_type ORDER BY nb DESC
            """, (session["user_id"], year))
            by_sport = [dict(r) for r in cur.fetchall()]

            # récupère les totaux par mois
            cur.execute("""
                SELECT EXTRACT(MONTH FROM start_date_local) AS month,
                    COUNT(*) AS nb,
                    ROUND((SUM(distance_m)/1000)::numeric, 1) AS km
                FROM activities
                WHERE user_id = %s AND EXTRACT(YEAR FROM start_date_local) = %s
                GROUP BY EXTRACT(MONTH FROM start_date_local) ORDER BY month
            """, (session["user_id"], year))
            by_month = [dict(r) for r in cur.fetchall()]

    # calcul des différentes statistiques fun
    total_km = totals["total_m"] / 1000.0
    fun = {
        "vaches":     round(totals["total_m"] / 2.4),
        "lac_leman":  round(total_km / 170, 1),
        "cervin":     round(totals["total_elevation"] / 4478, 1),
        "swissTotal": round((total_km / 66000) * 100, 2),
        "fondues":    round(totals["total_calories"] / 800),
        "heures":     round(totals["total_seconds"] / 3600, 1),
    }

    return jsonify({"year": year, "totals": totals,
                    "by_sport": by_sport, "by_month": by_month, "fun": fun})


# EXPORT GPX

@app.route("/api/gpx/<int:strava_id>")
def export_gpx(strava_id):
    # permet de générer un fichier GPX pour une activité
    if "user_id" not in session:
        return jsonify({"error": "non connecte"}), 401

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # vérifie que l'activité appartient bien à l'utilisateur connecté (par sécurité)
            cur.execute("""
                SELECT name, start_date_local, sport_type,
                       ST_AsGeoJSON(track_geom)::json AS geojson
                FROM activities WHERE strava_id = %s AND user_id = %s
            """, (strava_id, session["user_id"]))
            act = cur.fetchone()

    if not act or not act["geojson"]:
        return "Activite introuvable", 404

    coords = act["geojson"]["coordinates"]   # Inversion lng/lat -> lat/lon
    trkpts = "\n".join(
        f'      <trkpt lat="{lat}" lon="{lng}"></trkpt>'
        for lng, lat in coords
    )

    gpx = f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="SwissStats">
  <trk>
    <name>{act['name']}</name>
    <type>{act['sport_type'] or 'other'}</type>
    <trkseg>
{trkpts}
    </trkseg>
  </trk>
</gpx>"""
    # retourne le GPX en tant que fichier téléchargeable
    return Response(gpx, mimetype="application/gpx+xml",
                    headers={"Content-Disposition": f"attachment; filename=strava_{strava_id}.gpx"})


if __name__ == "__main__":
    init_db()
    port = int(os.getenv("PORT", 5000))
    app.run(debug=True, port=port)
