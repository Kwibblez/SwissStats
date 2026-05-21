"""
GIN_Strava_sport_stats — Application Flask principale
HEIG-VD 2026 — Fardel, Perroud, Smith
"""

import os
from flask import Flask, redirect, request, session, url_for, render_template, jsonify
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
from strava_api import StravaAPI
from db import get_db_connection, init_db

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change_me_in_prod")

# ── Constantes Strava OAuth ──────────────────────────────────
STRAVA_CLIENT_ID     = os.getenv("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
STRAVA_REDIRECT_URI  = os.getenv("STRAVA_REDIRECT_URI", "http://localhost:5000/callback")
STRAVA_SCOPES        = "read,activity:read_all"


# ═══════════════════════════════════════════════════════════════
# AUTHENTIFICATION STRAVA (OAuth 2)
# ═══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    """Page d'accueil : si connecté → carte, sinon → login."""
    if "user_id" not in session:
        return render_template("login.html")
    return redirect(url_for("map_view"))


@app.route("/login")
def login():
    """Redirige vers la page d'autorisation Strava."""
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
    """Reçoit le code OAuth de Strava, échange contre un token."""
    code = request.args.get("code")
    if not code:
        return "Erreur : pas de code reçu de Strava.", 400

    strava = StravaAPI(STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET)
    token_data = strava.exchange_code(code, STRAVA_REDIRECT_URI)
    athlete    = token_data.get("athlete", {})

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

    session["user_id"]    = user_id
    session["strava_id"]  = athlete.get("id")
    session["firstname"]  = athlete.get("firstname", "Athlète")
    return redirect(url_for("map_view"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ═══════════════════════════════════════════════════════════════
# SYNCHRONISATION DES ACTIVITÉS STRAVA
# ═══════════════════════════════════════════════════════════════

@app.route("/sync")
def sync_activities():
    """Stream SSE de progression — envoie un événement par activité traitée."""
    if "user_id" not in session:
        return redirect(url_for("login"))

    year    = request.args.get("year", 2024, type=int)
    user_id = session["user_id"]

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()

    strava = StravaAPI(STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET)
    strava.set_tokens(user["access_token"], user["refresh_token"],
                      user["token_expires_at"])

    new_tokens = strava.refresh_if_needed()
    if new_tokens:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users SET access_token=%s, refresh_token=%s,
                    token_expires_at=%s WHERE id=%s
                """, (new_tokens["access_token"], new_tokens["refresh_token"],
                      new_tokens["expires_at"], user_id))
                conn.commit()

    from flask import Response, stream_with_context
    import json

    def generate():
        activities = strava.get_activities_for_year(year)
        total      = len(activities)

        yield f"data: " + json.dumps({'total': total, 'done': 0, 'msg': f'Récupération de {total} activités...'}) + "\n\n"

        saved = 0
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                for i, act in enumerate(activities):
                    name = act.get("name", "Activité")

                    try:
                        detail   = strava.get_activity_detail(act["id"])
                        calories = detail.get("calories") or 0
                    except Exception:
                        calories = 0

                    latlng_stream = strava.get_latlng_stream(act["id"])
                    track_geom    = None
                    has_gpx       = False

                    if latlng_stream and len(latlng_stream) > 1:
                        has_gpx    = True
                        wkt_pts    = ", ".join(f"{pt[1]} {pt[0]}" for pt in latlng_stream)
                        track_geom = f"LINESTRING({wkt_pts})"

                    start_ll = act.get("start_latlng") or [None, None]
                    end_ll   = act.get("end_latlng")   or [None, None]
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
                        track_geom, has_gpx,
                        act.get("manual", False), act.get("commute", False),
                    ))
                    saved += 1
                    pct = round((saved / total) * 100) if total else 100
                    yield "data: " + json.dumps({'total': total, 'done': saved, 'pct': pct, 'msg': name}) + "\n\n"

                conn.commit()

        yield "data: " + json.dumps({'total': total, 'done': saved, 'pct': 100, 'finished': True, 'msg': f'✅ {saved} activités synchronisées !'}) + "\n\n"

    return Response(stream_with_context(generate()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ═══════════════════════════════════════════════════════════════
# CARTE (page principale)
# ═══════════════════════════════════════════════════════════════

@app.route("/map")
def map_view():
    if "user_id" not in session:
        return redirect(url_for("login"))
    year = request.args.get("year", 2024, type=int)
    return render_template("map.html",
                           firstname=session.get("firstname"),
                           year=year)


@app.route("/api/tracks")
def api_tracks():
    """Retourne les tracés GeoJSON pour l'année demandée."""
    if "user_id" not in session:
        return jsonify({"error": "non connecté"}), 401

    year       = request.args.get("year", 2024, type=int)
    sport_type = request.args.get("sport")   # optionnel : filtrer par sport

    query = """
        SELECT
            strava_id, name, sport_type,
            start_date_local,
            ROUND((distance_m / 1000.0)::numeric, 2)      AS distance_km,
            moving_time_s,
            ROUND(total_elevation_m::numeric)              AS elevation_m,
            ROUND(calories::numeric)                       AS calories,
            ROUND((average_speed_ms * 3.6)::numeric, 1)   AS avg_speed_kmh,
            average_heartrate,
            ST_AsGeoJSON(track_geom)::json          AS geojson
        FROM activities
        WHERE user_id = %s
          AND EXTRACT(YEAR FROM start_date_local) = %s
          AND track_geom IS NOT NULL
    """
    params = [session["user_id"], year]

    if sport_type:
        query += " AND sport_type = %s"
        params.append(sport_type)

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

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
                "calories":      row["calories"],
                "avg_speed":     row["avg_speed_kmh"],
                "heartrate":     row["average_heartrate"],
            }
        })

    return jsonify({"type": "FeatureCollection", "features": features})


# ═══════════════════════════════════════════════════════════════
# STATISTIQUES (page fun)
# ═══════════════════════════════════════════════════════════════

@app.route("/stats")
def stats_view():
    if "user_id" not in session:
        return redirect(url_for("login"))
    year = request.args.get("year", 2024, type=int)
    return render_template("stats.html",
                           firstname=session.get("firstname"),
                           year=year)


@app.route("/api/stats")
def api_stats():
    """Retourne les statistiques agrégées pour la page fun."""
    if "user_id" not in session:
        return jsonify({"error": "non connecté"}), 401

    year = request.args.get("year", 2024, type=int)

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Stats globales
            cur.execute("""
                SELECT
                    COUNT(*)                            AS nb_activities,
                    COALESCE(SUM(distance_m), 0)        AS total_m,
                    COALESCE(SUM(moving_time_s), 0)     AS total_seconds,
                    COALESCE(SUM(total_elevation_m), 0) AS total_elevation,
                    COALESCE(SUM(calories), 0)          AS total_calories,
                    COALESCE(AVG(average_heartrate), 0) AS avg_heartrate
                FROM activities
                WHERE user_id = %s
                  AND EXTRACT(YEAR FROM start_date_local) = %s
            """, (session["user_id"], year))
            totals = dict(cur.fetchone())

            # Par sport
            cur.execute("""
                SELECT sport_type,
                       COUNT(*)                       AS nb,
                       ROUND((SUM(distance_m)/1000)::numeric, 1) AS km,
                       ROUND(SUM(calories)::numeric)             AS kcal
                FROM activities
                WHERE user_id = %s
                  AND EXTRACT(YEAR FROM start_date_local) = %s
                GROUP BY sport_type
                ORDER BY nb DESC
            """, (session["user_id"], year))
            by_sport = [dict(r) for r in cur.fetchall()]

            # Par mois
            cur.execute("""
                SELECT
                    EXTRACT(MONTH FROM start_date_local) AS month,
                    COUNT(*)                             AS nb,
                    ROUND((SUM(distance_m)/1000)::numeric, 1)  AS km
                FROM activities
                WHERE user_id = %s
                  AND EXTRACT(YEAR FROM start_date_local) = %s
                GROUP BY EXTRACT(MONTH FROM start_date_local)
                ORDER BY month
            """, (session["user_id"], year))
            by_month = [dict(r) for r in cur.fetchall()]

    total_km = totals["total_m"] / 1000.0

    # ── Comparaisons fun ────────────────────────────────────
    # 1 vache suisse = 2.4m de long en moyenne
    VACHE_LONGUEUR_M = 2.4
    # Distance Lausanne-Tokyo = 9 600 km
    # Mont Blanc = 4808m
    # Tour du Lac Léman = 170 km
    fun = {
        "vaches":         round(totals["total_m"] / VACHE_LONGUEUR_M),
        "lac_leman":      round(total_km / 170, 1),
        "cervin":     round(totals["total_elevation"] / 4478, 1),
        "lausanne_tokyo": round(total_km / 9600, 2),
        "fondue":         round(totals["total_calories"] / 800),   # ~800 kcal/pizza
        "heures":         round(totals["total_seconds"] / 3600, 1),
    }

    return jsonify({
        "year":     year,
        "totals":   totals,
        "by_sport": by_sport,
        "by_month": by_month,
        "fun":      fun,
    })


# ═══════════════════════════════════════════════════════════════
# EXPORT GPX d'une activité
# ═══════════════════════════════════════════════════════════════

@app.route("/api/gpx/<int:strava_id>")
def export_gpx(strava_id):
    """Retourne le GPX reconstruit depuis les points stockés."""
    if "user_id" not in session:
        return jsonify({"error": "non connecté"}), 401

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT a.name, a.start_date_local, a.sport_type,
                       ST_AsGeoJSON(a.track_geom)::json AS geojson
                FROM activities a
                WHERE a.strava_id = %s AND a.user_id = %s
            """, (strava_id, session["user_id"]))
            act = cur.fetchone()

    if not act or not act["geojson"]:
        return "Activité introuvable ou sans tracé", 404

    coords = act["geojson"]["coordinates"]  # [[lng, lat], ...]
    trkpts = "\n".join(
        f'      <trkpt lat="{lat}" lon="{lng}"></trkpt>'
        for lng, lat in coords
    )
    name  = act["name"] or "Activité"
    date  = str(act["start_date_local"])
    sport = act["sport_type"] or "other"

    gpx = f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="GIN_Strava_stats">
  <metadata><name>{name}</name><time>{date}</time></metadata>
  <trk>
    <name>{name}</name>
    <type>{sport}</type>
    <trkseg>
{trkpts}
    </trkseg>
  </trk>
</gpx>"""

    from flask import Response
    filename = f"strava_{strava_id}.gpx"
    return Response(gpx, mimetype="application/gpx+xml",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


if __name__ == "__main__":
    init_db()
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
