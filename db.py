"""
db.py — Connexion PostgreSQL
Lit DATABASE_URL (Railway) ou les variables séparées (local)
"""

import os
import psycopg2
from contextlib import contextmanager
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

def _config():
    url = os.getenv("DATABASE_URL", "")
    if url:
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        r = urlparse(url)
        return dict(dbname=r.path[1:], user=r.username,
                    password=r.password, host=r.hostname,
                    port=r.port or 5432)
    return dict(
        dbname   = os.getenv("POSTGRES_DB",       "stravaGeoInfo"),
        user     = os.getenv("POSTGRES_USER",     "postgres"),
        password = os.getenv("POSTGRES_PASSWORD", "postgres"),
        host     = os.getenv("POSTGRES_HOST",     "localhost"),
        port     = int(os.getenv("POSTGRES_PORT", "5432")),
    )

@contextmanager
def get_db_connection():
    conn = psycopg2.connect(**_config())
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(path, "r", encoding="utf-8") as f:
        sql = f.read()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    print("Base de données initialisée.")
