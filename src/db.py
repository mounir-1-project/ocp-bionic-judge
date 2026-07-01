"""
Point d’entrée unique pour la connexion BDD.
En dev on utilise SQLite (simple, pas besoin d’installer PostgreSQL),
en prod on passe sur PostgreSQL juste en changeant DATABASE_URL dans .env.

Author: Mounir Sanbouli
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from src.config import DATABASE_URL  # noqa: F401
from loguru import logger
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, Engine


_engine: Engine | None = None

DEFAULT_SQLITE_URL = f"sqlite:///{Path(__file__).parents[1] / 'data' / 'ocp_bionic.db'}"


def get_engine(database_url: str | None = None) -> Engine:
    """Return (or create) the global SQLAlchemy engine.

    Reads DATABASE_URL from environment if not provided.
    Supports postgresql:// and sqlite:// URLs.

    Args:
        database_url: Optional override. Falls back to DATABASE_URL env var,
                      then to a local SQLite file.

    Returns:
        SQLAlchemy Engine instance.
    """
    global _engine
    if _engine is not None and database_url is None:
        return _engine

    url = database_url or os.getenv("DATABASE_URL", DEFAULT_SQLITE_URL)

    # SQLite: allow multi-threaded access (needed for FastAPI)
    if url.startswith("sqlite"):
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            echo=False,
        )
        # Enable WAL mode for better concurrency on SQLite
        @event.listens_for(engine, "connect")
        def set_wal(dbapi_conn, _rec) -> None:
            dbapi_conn.execute("PRAGMA journal_mode=WAL")
            dbapi_conn.execute("PRAGMA synchronous=NORMAL")

        logger.debug(f"SQLite engine created: {url}")
    else:
        engine = create_engine(
            url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            echo=False,
        )
        logger.debug(f"PostgreSQL engine created: {url.split('@')[-1]}")  # hide credentials

    if database_url is None:
        _engine = engine

    return engine


@contextmanager
def get_connection(database_url: str | None = None) -> Generator[Connection, None, None]:
    """Context manager that yields a SQLAlchemy connection with auto-commit/rollback.

    Args:
        database_url: Optional URL override.

    Yields:
        Active SQLAlchemy Connection.

    Example:
        with get_connection() as conn:
            conn.execute(text("SELECT 1"))
    """
    engine = get_engine(database_url)
    with engine.begin() as conn:
        yield conn


def reset_engine() -> None:
    """Dispose and reset the global engine (useful for testing).

    Returns:
        None.
    """
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None
    logger.debug("Engine reset.")


DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS machines (
        id          TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        type        TEXT NOT NULL,
        location    TEXT,
        installed   TEXT,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sensor_readings (
        id          BIGSERIAL PRIMARY KEY,
        machine_id  TEXT NOT NULL,
        timestamp   TEXT NOT NULL,
        temperature DOUBLE PRECISION,
        vibration   DOUBLE PRECISION,
        pression    DOUBLE PRECISION,
        courant     DOUBLE PRECISION,
        rpm         DOUBLE PRECISION,
        shift       TEXT,
        FOREIGN KEY (machine_id) REFERENCES machines(id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_readings_machine_ts
        ON sensor_readings (machine_id, timestamp)
    """,
    """
    CREATE TABLE IF NOT EXISTS anomalies (
        id              BIGSERIAL PRIMARY KEY,
        machine_id      TEXT NOT NULL,
        timestamp       TEXT NOT NULL,
        anomaly_type    TEXT NOT NULL,
        sensor_affected TEXT,
        severity        TEXT,
        injected        INTEGER DEFAULT 1,
        FOREIGN KEY (machine_id) REFERENCES machines(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ml_decisions (
        id              BIGSERIAL PRIMARY KEY,
        machine_id      TEXT NOT NULL,
        timestamp       TEXT NOT NULL,
        anomaly_score   DOUBLE PRECISION,
        is_anomaly      INTEGER,
        severity        TEXT,
        model_version   TEXT,
        inference_ms    DOUBLE PRECISION,
        features_json   TEXT,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS judge_evaluations (
        id                  BIGSERIAL PRIMARY KEY,
        decision_id         BIGINT,
        machine_id          TEXT NOT NULL,
        timestamp           TEXT NOT NULL,
        global_score        DOUBLE PRECISION,
        relevance_score     DOUBLE PRECISION,
        history_score       DOUBLE PRECISION,
        confidence_score    DOUBLE PRECISION,
        compliance_score    DOUBLE PRECISION,
        feasibility_score   DOUBLE PRECISION,
        agreement           INTEGER,
        feedback            TEXT,
        flagged_issues      TEXT,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (decision_id) REFERENCES ml_decisions(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_log (
        id          BIGSERIAL PRIMARY KEY,
        timestamp   TEXT NOT NULL,
        event_type  TEXT NOT NULL,
        machine_id  TEXT,
        user_id     TEXT DEFAULT 'system',
        action      TEXT NOT NULL,
        details     TEXT,
        severity    TEXT DEFAULT 'INFO'
    )
    """,
]

# SQLite-compatible DDL (BIGSERIAL → INTEGER PRIMARY KEY AUTOINCREMENT)
DDL_SQLITE = [s.replace("BIGSERIAL", "INTEGER").replace("DOUBLE PRECISION", "REAL")
              for s in DDL_STATEMENTS]


def init_schema(engine: Engine | None = None) -> None:
    """Create all tables if they don't exist.

    Uses PostgreSQL DDL for postgres engines, SQLite DDL otherwise.

    Args:
        engine: Optional engine override (uses global engine if None).
    """
    eng = engine or get_engine()
    is_sqlite = eng.dialect.name == "sqlite"
    statements = DDL_SQLITE if is_sqlite else DDL_STATEMENTS

    with eng.begin() as conn:
        for stmt in statements:
            stmt = stmt.strip()
            if not stmt:
                continue
            try:
                conn.execute(text(stmt))
            except Exception as e:
                # Index may already exist — not fatal
                if "already exists" in str(e).lower():
                    pass
                else:
                    logger.warning(f"DDL warning: {e}")

    logger.info(f"Schema initialized ({eng.dialect.name}).")