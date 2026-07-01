"""Initial schema -- all 6 tables for OCP Bionic Judge.

Creates: machines, sensor_readings, anomalies, ml_decisions,
         judge_evaluations, audit_log.

Revision ID: 0001
Revises:
Create Date: 2026-06-05
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SQL_MACHINES = """
    CREATE TABLE IF NOT EXISTS machines (
        id          TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        type        TEXT NOT NULL,
        location    TEXT,
        installed   TEXT,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""

_SQL_SENSOR_READINGS = """
    CREATE TABLE IF NOT EXISTS sensor_readings (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        machine_id  TEXT NOT NULL,
        timestamp   TEXT NOT NULL,
        temperature REAL,
        vibration   REAL,
        pression    REAL,
        courant     REAL,
        rpm         REAL,
        shift       TEXT,
        FOREIGN KEY (machine_id) REFERENCES machines(id)
    )
"""

_SQL_ANOMALIES = """
    CREATE TABLE IF NOT EXISTS anomalies (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        machine_id      TEXT NOT NULL,
        timestamp       TEXT NOT NULL,
        anomaly_type    TEXT NOT NULL,
        sensor_affected TEXT,
        severity        TEXT,
        injected        INTEGER DEFAULT 1,
        FOREIGN KEY (machine_id) REFERENCES machines(id)
    )
"""

_SQL_ML_DECISIONS = """
    CREATE TABLE IF NOT EXISTS ml_decisions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        machine_id      TEXT NOT NULL,
        timestamp       TEXT NOT NULL,
        anomaly_score   REAL,
        is_anomaly      INTEGER,
        severity        TEXT,
        model_version   TEXT,
        inference_ms    REAL,
        features_json   TEXT,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""

_SQL_JUDGE_EVALUATIONS = """
    CREATE TABLE IF NOT EXISTS judge_evaluations (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        decision_id         INTEGER,
        machine_id          TEXT NOT NULL,
        timestamp           TEXT NOT NULL,
        global_score        REAL,
        relevance_score     REAL,
        history_score       REAL,
        confidence_score    REAL,
        compliance_score    REAL,
        feasibility_score   REAL,
        agreement           INTEGER,
        feedback            TEXT,
        flagged_issues      TEXT,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (decision_id) REFERENCES ml_decisions(id)
    )
"""

_SQL_AUDIT_LOG = """
    CREATE TABLE IF NOT EXISTS audit_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp   TEXT NOT NULL,
        event_type  TEXT NOT NULL,
        machine_id  TEXT,
        user_id     TEXT DEFAULT 'system',
        action      TEXT NOT NULL,
        details     TEXT,
        severity    TEXT DEFAULT 'INFO'
    )
"""


def _ddl(sql: str) -> str:
    """Adapt SQLite-style DDL to the active dialect.

    The table definitions above are written in SQLite syntax. On PostgreSQL we
    translate the auto-increment primary key and the float type, mirroring the
    same mapping used in ``src/db.py`` so the schema is identical on both engines.
    """
    if op.get_bind().dialect.name == "postgresql":
        return (
            sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
            .replace("REAL", "DOUBLE PRECISION")
        )
    return sql


def upgrade() -> None:
    op.execute(_ddl(_SQL_MACHINES))
    op.execute(_ddl(_SQL_SENSOR_READINGS))
    op.execute("CREATE INDEX IF NOT EXISTS idx_readings_machine_ts ON sensor_readings (machine_id, timestamp)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_readings_ts ON sensor_readings (timestamp)")
    op.execute(_ddl(_SQL_ANOMALIES))
    op.execute(_ddl(_SQL_ML_DECISIONS))
    op.execute("CREATE INDEX IF NOT EXISTS idx_decisions_machine_ts ON ml_decisions (machine_id, timestamp)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_decisions_severity ON ml_decisions (severity) WHERE is_anomaly = 1")
    op.execute(_ddl(_SQL_JUDGE_EVALUATIONS))
    op.execute("CREATE INDEX IF NOT EXISTS idx_judge_machine_ts ON judge_evaluations (machine_id, timestamp)")
    op.execute(_ddl(_SQL_AUDIT_LOG))
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_event_ts ON audit_log (event_type, timestamp)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_audit_event_ts")
    op.execute("DROP TABLE IF EXISTS audit_log")
    op.execute("DROP INDEX IF EXISTS idx_judge_machine_ts")
    op.execute("DROP TABLE IF EXISTS judge_evaluations")
    op.execute("DROP INDEX IF EXISTS idx_decisions_severity")
    op.execute("DROP INDEX IF EXISTS idx_decisions_machine_ts")
    op.execute("DROP TABLE IF EXISTS ml_decisions")
    op.execute("DROP TABLE IF EXISTS anomalies")
    op.execute("DROP INDEX IF EXISTS idx_readings_ts")
    op.execute("DROP INDEX IF EXISTS idx_readings_machine_ts")
    op.execute("DROP TABLE IF EXISTS sensor_readings")
    op.execute("DROP TABLE IF EXISTS machines")
