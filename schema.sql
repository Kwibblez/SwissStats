-- ============================================================
-- GIN_Strava_sport_stats — Schéma PostgreSQL + PostGIS
-- HEIG-VD, 2026 — Fardel, Perroud, Smith
-- ============================================================

-- Extension géospatiale (PostGIS obligatoire)
CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================
-- TABLE : users (authentification OAuth Strava)
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id                  SERIAL PRIMARY KEY,
    strava_id           BIGINT UNIQUE NOT NULL,
    access_token        TEXT NOT NULL,
    refresh_token       TEXT NOT NULL,
    token_expires_at    BIGINT NOT NULL,       -- Unix timestamp
    firstname           VARCHAR(100),
    lastname            VARCHAR(100),
    profile_pic_url     TEXT,
    city                VARCHAR(100),
    country             VARCHAR(100),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TABLE : activities (données brutes Strava)
-- ============================================================
CREATE TABLE IF NOT EXISTS activities (
    id                  SERIAL PRIMARY KEY,
    strava_id           BIGINT UNIQUE NOT NULL,
    user_id             INTEGER REFERENCES users(id) ON DELETE CASCADE,

    -- Infos générales
    name                VARCHAR(255),
    sport_type          VARCHAR(50),          -- Run, Ride, Hike, Swim, Walk, ...
    start_date          TIMESTAMPTZ,
    start_date_local    TIMESTAMPTZ,
    timezone            VARCHAR(100),

    -- Métriques principales
    distance_m          FLOAT,                -- mètres
    moving_time_s       INTEGER,              -- secondes
    elapsed_time_s      INTEGER,              -- secondes
    total_elevation_m   FLOAT,                -- mètres de dénivelé positif
    calories            FLOAT,                -- kcal (si dispo)
    average_speed_ms    FLOAT,                -- m/s
    max_speed_ms        FLOAT,
    average_heartrate   FLOAT,
    max_heartrate       FLOAT,
    average_cadence     FLOAT,
    average_watts       FLOAT,                -- vélo
    suffer_score        INTEGER,

    -- Localisation de départ
    start_lat           FLOAT,
    start_lng           FLOAT,
    end_lat             FLOAT,
    end_lng             FLOAT,

    -- Géométrie PostGIS du tracé complet (ligne 2D)
    track_geom          GEOMETRY(LINESTRING, 4326),

    -- GPX raw (optionnel, stocké en texte)
    gpx_data            TEXT,

    -- Flags
    has_gpx             BOOLEAN DEFAULT FALSE,
    manual              BOOLEAN DEFAULT FALSE,
    commute             BOOLEAN DEFAULT FALSE,

    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Index géographique pour les requêtes spatiales
CREATE INDEX IF NOT EXISTS idx_activities_track_geom
    ON activities USING GIST(track_geom);

CREATE INDEX IF NOT EXISTS idx_activities_user_date
    ON activities(user_id, start_date_local);

CREATE INDEX IF NOT EXISTS idx_activities_sport_type
    ON activities(sport_type);

-- ============================================================
-- TABLE : gpx_points (points GPS individuels)
-- Utile pour des analyses détaillées, heatmap, etc.
-- ============================================================
CREATE TABLE IF NOT EXISTS gpx_points (
    id              SERIAL PRIMARY KEY,
    activity_id     INTEGER REFERENCES activities(id) ON DELETE CASCADE,
    point_order     INTEGER NOT NULL,
    geom            GEOMETRY(POINT, 4326) NOT NULL,
    elevation_m     FLOAT,
    recorded_at     TIMESTAMPTZ,
    heartrate       INTEGER,
    cadence         INTEGER,
    speed_ms        FLOAT
);

CREATE INDEX IF NOT EXISTS idx_gpx_points_geom
    ON gpx_points USING GIST(geom);

CREATE INDEX IF NOT EXISTS idx_gpx_points_activity
    ON gpx_points(activity_id, point_order);

-- ============================================================
-- VUE : stats annuelles par utilisateur et sport
-- ============================================================
CREATE OR REPLACE VIEW yearly_stats AS
SELECT
    u.strava_id                                          AS user_strava_id,
    EXTRACT(YEAR FROM a.start_date_local)                AS year,
    a.sport_type,
    COUNT(*)                                             AS nb_activities,
    ROUND((SUM(a.distance_m) / 1000.0)::numeric, 2)     AS total_km,
    SUM(a.moving_time_s) / 3600.0                        AS total_hours,
    ROUND(SUM(a.total_elevation_m)::numeric)             AS total_elevation_m,
    ROUND(SUM(a.calories)::numeric)                      AS total_calories,
    ROUND(AVG(a.average_heartrate)::numeric, 1)          AS avg_heartrate
FROM activities a
JOIN users u ON a.user_id = u.id
WHERE a.start_date_local IS NOT NULL
GROUP BY u.strava_id, EXTRACT(YEAR FROM a.start_date_local), a.sport_type;

-- ============================================================
-- VUE : résumé mensuel (pour graphiques)
-- ============================================================
CREATE OR REPLACE VIEW monthly_stats AS
SELECT
    a.user_id,
    DATE_TRUNC('month', a.start_date_local)          AS month,
    a.sport_type,
    COUNT(*)                                         AS nb_activities,
    ROUND((SUM(a.distance_m) / 1000.0)::numeric, 2) AS total_km,
    ROUND(SUM(a.calories)::numeric)                  AS total_calories
FROM activities a
GROUP BY a.user_id, DATE_TRUNC('month', a.start_date_local), a.sport_type;
