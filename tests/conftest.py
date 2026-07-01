"""
OCP Bionic Judge — pytest Fixtures
Uses SQLite in-memory for all tests (no PostgreSQL required).
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.db import init_schema, reset_engine


@pytest.fixture(scope="session")
def tmp_db_path(tmp_path_factory):
    """Create a temp SQLite DB populated with test data.

    Yields:
        SQLAlchemy engine connected to the temp DB.
    """
    db_file = tmp_path_factory.mktemp("data") / "test.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    init_schema(engine)

    rng = np.random.default_rng(42)
    now = datetime.now()

    # Machines
    with engine.begin() as conn:
        from sqlalchemy import text
        conn.execute(text("""
            INSERT OR IGNORE INTO machines (id, name, type, location, installed)
            VALUES ('BROYEUR_01','Broyeur','broyeur','Khouribga','2020-01-01'),
                   ('POMPE_02','Pompe','pompe','Benguerir','2020-01-01')
        """))

        # Sensor readings
        for machine_id in ["BROYEUR_01", "POMPE_02"]:
            for i in range(500):
                ts = (now - timedelta(seconds=30 * i)).isoformat()
                conn.execute(text("""
                    INSERT INTO sensor_readings
                    (machine_id, timestamp, temperature, vibration, pression, courant, rpm, shift)
                    VALUES (:mid, :ts, :tmp, :vib, :pre, :cur, :rpm, 'matin')
                """), {"mid": machine_id, "ts": ts,
                       "tmp": float(rng.normal(65, 5)), "vib": float(rng.normal(4, 0.5)),
                       "pre": float(rng.normal(3, 0.3)), "cur": float(rng.normal(35, 3)),
                       "rpm": float(rng.normal(1450, 30))})

        # Anomalies
        for i in range(30):
            ts = (now - timedelta(seconds=300 * i)).isoformat()
            conn.execute(text("""
                INSERT INTO anomalies (machine_id, timestamp, anomaly_type, sensor_affected, severity)
                VALUES ('BROYEUR_01', :ts, 'spike', 'temperature', 'WARNING')
            """), {"ts": ts})

        # ML decisions
        for i in range(200):
            ts    = (now - timedelta(seconds=30 * i)).isoformat()
            score = float(rng.uniform(0, 1))
            sev   = "CRITICAL" if score > 0.7 else ("WARNING" if score > 0.3 else "NORMAL")
            conn.execute(text("""
                INSERT INTO ml_decisions
                (machine_id, timestamp, anomaly_score, is_anomaly, severity, model_version, inference_ms, features_json)
                VALUES ('BROYEUR_01', :ts, :sc, :ia, :sev, 'IsolationForest', 0.5, '{}')
            """), {"ts": ts, "sc": score, "ia": int(score > 0.5), "sev": sev})

        # Judge evaluations
        for i in range(50):
            ts    = (now - timedelta(hours=i)).isoformat()
            score = float(rng.uniform(5, 10))
            conn.execute(text("""
                INSERT INTO judge_evaluations
                (machine_id, timestamp, global_score, relevance_score, history_score,
                 confidence_score, compliance_score, feasibility_score, agreement, feedback, flagged_issues)
                VALUES ('BROYEUR_01', :ts, :gs, :gs, :gs, :gs, :gs, :gs, :agr, 'Test', '[]')
            """), {"ts": ts, "gs": score, "agr": int(score >= 6)})

    yield engine
    engine.dispose()


@pytest.fixture
def sample_sensor_df() -> pd.DataFrame:
    """Return a small DataFrame mimicking sensor_readings."""
    rng = np.random.default_rng(99)
    n   = 100
    now = datetime.now()
    return pd.DataFrame({
        "machine_id":  ["BROYEUR_01"] * 50 + ["POMPE_02"] * 50,
        "timestamp":   [(now - timedelta(seconds=30 * i)).isoformat() for i in range(n)],
        "temperature": rng.normal(65, 5, n).round(2),
        "vibration":   rng.normal(4, 0.5, n).round(3),
        "pression":    rng.normal(3, 0.3, n).round(3),
        "courant":     rng.normal(35, 3, n).round(2),
        "rpm":         rng.normal(1450, 30, n).round(1),
        "shift":       ["matin"] * n,
    })


@pytest.fixture
def anomaly_decision():
    """Return a sample Detection Agent decision dict."""
    return {
        "machine_id": "BROYEUR_01",
        "timestamp":  datetime.now().isoformat(),
        "anomaly_score": 0.85, "severity": "CRITICAL",
        "diagnosis": "Surchauffe moteur + vibrations élevées",
        "recommended_action": "Arrêt préventif sous 2h",
        "confidence": 0.88, "reasoning": "Température 87°C > seuil critique 80°C",
        "shap_top_features": [{"feature": "temperature", "shap_value": 0.42}],
    }