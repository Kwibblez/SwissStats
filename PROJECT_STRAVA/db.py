"""
db.py — Connexion PostgreSQL + initialisation du schéma
Supporte DATABASE_URL (Render) et variables séparées (local)
"""

import os
import psycopg2
from contextlib import contextmanager
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

def _build_config():
    url = os.getenv("DATABASE_URL")
    if url:
        # Render fournit postgres:// mais psycopg2 veut postgresql://
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        r = urlparse(url)
        return {
            "dbname":   r.path[1:],
            "user":     r.username,
            "password": r.password,
            "host":     r.hostname,
            "port":     r.port or 5432,
        }
    # Développement local
    return {
        "dbname":   os.getenv("POSTGRES_DB",       "stravaGeoInfo"),
        "user":     os.getenv("POSTGRES_USER",     "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
        "host":     os.getenv("POSTGRES_HOST",     "localhost"),
        "port":     int(os.getenv("POSTGRES_PORT", "5432")),
    }


@contextmanager
def get_db_connection():
    conn = psycopg2.connect(**_build_config())
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Applique le schéma SQL au démarrage."""
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        sql = f.read()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    print("✅ Base de données initialisée.")
