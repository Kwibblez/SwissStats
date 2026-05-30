-- ============================================================
-- SwissStats — Schéma PostgreSQL
-- HEIG-VD, 2026 — Fardel, Perroud, Smith
-- ============================================================

-- ============================================================
-- TABLE : users
-- ============================================================
-- Supprime tout et recrée


CREATE TABLE IF NOT EXISTS users (
    id                  SERIAL PRIMARY KEY,
    strava_id           BIGINT UNIQUE NOT NULL,
    access_token        TEXT NOT NULL,
    refresh_token       TEXT NOT NULL,
    token_expires_at    BIGINT NOT NULL,
    firstname           VARCHAR(100),
    lastname            VARCHAR(100),
    profile_pic_url     TEXT,
    city                VARCHAR(100),
    country             VARCHAR(100),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TABLE : activities
-- ============================================================
CREATE TABLE IF NOT EXISTS activities (
    id                  SERIAL PRIMARY KEY,
    strava_id           BIGINT UNIQUE NOT NULL,
    user_id             INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name                VARCHAR(255),
    sport_type          VARCHAR(50),
    start_date          TIMESTAMPTZ,
    start_date_local    TIMESTAMPTZ,
    timezone            VARCHAR(100),
    distance_m          FLOAT,
    moving_time_s       INTEGER,
    elapsed_time_s      INTEGER,
    total_elevation_m   FLOAT,
    calories            FLOAT,
    average_speed_ms    FLOAT,
    max_speed_ms        FLOAT,
    average_heartrate   FLOAT,
    max_heartrate       FLOAT,
    average_cadence     FLOAT,
    average_watts       FLOAT,
    suffer_score        INTEGER,
    start_lat           FLOAT,
    start_lng           FLOAT,
    end_lat             FLOAT,
    end_lng             FLOAT,
    track_geojson       TEXT,
    has_gpx             BOOLEAN DEFAULT FALSE,
    manual              BOOLEAN DEFAULT FALSE,
    commute             BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_activities_user_date
    ON activities(user_id, start_date_local);

CREATE INDEX IF NOT EXISTS idx_activities_sport_type
    ON activities(sport_type);

-- ============================================================
-- VUE : stats annuelles par utilisateur et sport
-- ============================================================
CREATE OR REPLACE VIEW yearly_stats AS
SELECT
    u.strava_id                                      AS user_strava_id,
    EXTRACT(YEAR FROM a.start_date_local)            AS year,
    a.sport_type,
    COUNT(*)                                         AS nb_activities,
    ROUND((SUM(a.distance_m) / 1000.0)::numeric, 2) AS total_km,
    SUM(a.moving_time_s) / 3600.0                   AS total_hours,
    ROUND(SUM(a.total_elevation_m)::numeric)         AS total_elevation_m,
    ROUND(SUM(calories)::numeric)                  AS total_calories,
    ROUND(AVG(a.average_heartrate)::numeric, 1)      AS avg_heartrate
FROM activities a
JOIN users u ON a.user_id = u.id
WHERE a.start_date_local IS NOT NULL
GROUP BY u.strava_id, EXTRACT(YEAR FROM a.start_date_local), a.sport_type;

-- ============================================================
-- VUE : résumé mensuel
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
