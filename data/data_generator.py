"""
Générateur de données capteurs pour les 5 machines OCP.
Simule des lectures toutes les 30s sur 6 mois avec 3 types d'anomalies.

Les taux ont été calibrés pour avoir ~4% d'anomalies au total,
ce qui correspond à ce qu'on observe sur les vraies lignes de production.

Author: Mounir Sanbouli
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger

from src.config import GEMINI_MODEL  # noqa: F401 — ensures load_dotenv() called
from src.db import get_engine, init_schema
from sqlalchemy import text


DATA_DIR = Path(__file__).parent

MACHINES = [
    {"id": "BROYEUR_01",    "name": "Broyeur à Boulets",     "type": "broyeur"},
    {"id": "POMPE_02",      "name": "Pompe Centrifuge",       "type": "pompe"},
    {"id": "CONVOYEUR_03",  "name": "Convoyeur à Courroie",   "type": "convoyeur"},
    {"id": "REACTEUR_04",   "name": "Réacteur d'Attaque",     "type": "reacteur"},
    {"id": "COMPRESSEUR_05","name": "Compresseur Industriel", "type": "compresseur"},
]

SENSOR_PROFILES: dict[str, dict] = {
    "broyeur":      {"temperature": (45, 75, 5),  "vibration": (4.0, 1.0, 0.3), "pression": (3.0, 0.5, 0.1), "courant": (35.0, 5.0, 1.0), "rpm": (1450, 50, 10)},
    "pompe":        {"temperature": (40, 60, 4),  "vibration": (2.0, 0.5, 0.2), "pression": (6.0, 1.0, 0.2), "courant": (20.0, 3.0, 0.5), "rpm": (2950, 30, 8)},
    "convoyeur":    {"temperature": (30, 50, 3),  "vibration": (1.5, 0.4, 0.1), "pression": (1.5, 0.3, 0.05),"courant": (15.0, 2.0, 0.4), "rpm": (800, 20, 5)},
    "reacteur":     {"temperature": (60, 85, 6),  "vibration": (1.0, 0.3, 0.1), "pression": (7.0, 1.5, 0.3), "courant": (25.0, 4.0, 0.8), "rpm": (300, 10, 3)},
    "compresseur":  {"temperature": (50, 70, 4),  "vibration": (3.0, 0.8, 0.2), "pression": (8.0, 1.0, 0.2), "courant": (40.0, 5.0, 1.0), "rpm": (2900, 40, 8)},
}

# Anomaly rates calibrated for ~4% overall anomaly rate (realistic industrial setting).
#
# MATH: anomaly_rate = spike_rate + drift_rate + nan_rate
#   spike : checked ONCE per timestep → 2% of readings
#   drift : per sensor per step × 5 sensors × DRIFT_MAX_STEPS steps
#           0.00003 × 5 × 120 = 1.8%  contribution
#   nan   : per sensor per step × 5 sensors × avg_nan_duration (35 steps)
#           0.00008 × 5 × 35  = 1.4%  contribution
#   Total ≈ 2 + 1.8 + 1.4 = 5.2%  (some overlap → real ~4-5%) ✓
ANOMALY_RATE_SPIKE = 0.02      # 2%  — once per timestep (not per sensor)
ANOMALY_DRIFT_PROB = 0.00003   # per sensor per step (was 0.005 → 31% anomaly rate)
NAN_PROB           = 0.00008   # per sensor per step
DRIFT_MAX_STEPS    = 120       # 1h max drift at 30s intervals


def _shift(ts: datetime) -> str:
    """Return shift label for a timestamp.

    Args:
        ts: Datetime to classify.

    Returns:
        One of 'matin', 'soir', 'nuit'.
    """
    h = ts.hour
    if 6 <= h < 14:   return "matin"
    elif 14 <= h < 22: return "soir"
    return "nuit"


def generate_machine_data(
    machine: dict,
    start: datetime,
    end: datetime,
    freq_seconds: int = 30,
) -> tuple[pd.DataFrame, list[dict]]:
    """Generate time series sensor data for a single machine.

    Args:
        machine: Machine metadata dict with 'id' and 'type'.
        start: Start datetime.
        end: End datetime.
        freq_seconds: Interval between readings in seconds.

    Returns:
        Tuple of (DataFrame of readings, list of anomaly dicts).
    """
    machine_id = machine["id"]
    profile = SENSOR_PROFILES[machine["type"]]
    rng = np.random.default_rng(seed=abs(hash(machine_id)) % 2**31)
    timestamps = pd.date_range(start=start, end=end, freq=f"{freq_seconds}s")
    n = len(timestamps)
    sensors = ["temperature", "vibration", "pression", "courant", "rpm"]
    data: dict[str, np.ndarray] = {}

    for s in sensors:
        mean, std, noise = profile[s]
        t = np.linspace(0, 4 * np.pi, n)
        seasonal = std * 0.3 * np.sin(t + rng.uniform(0, np.pi))
        data[s] = mean + seasonal + rng.normal(0, noise, n)

    # is_anomalous[i] = True if timestep i has ANY active anomaly event.
    # We label EVERY affected timestep, not just the start event.
    # This ensures ML evaluation (F1, AUC) uses correct ground truth.
    is_anomalous: np.ndarray = np.zeros(n, dtype=bool)
    event_records: list[dict] = []  # one record per event START (for audit)

    # Per-timestep anomaly metadata — lets the persisted `anomalies` table carry the
    # real type/sensor/severity (spike/drift/sensor_cutoff) instead of a generic label,
    # WITHOUT changing which timesteps are labelled (the ML ground truth stays identical).
    kind:     list[str | None] = [None] * n
    kind_sens: list[str | None] = [None] * n
    kind_sev:  list[str | None] = [None] * n

    in_drift: dict[str, int | None] = {s: None for s in sensors}
    in_nan:   dict[str, int | None] = {s: None for s in sensors}

    limits = {"temperature": (20.0, 90.0), "vibration": (0.0, 10.0),
              "pression": (1.0, 10.0), "courant": (0.0, 50.0), "rpm": (0.0, 3000.0)}

    for i in range(n):
        ts = timestamps[i]

        # ── Spikes : one check per timestep → target rate = ANOMALY_RATE_SPIKE
        if rng.random() < ANOMALY_RATE_SPIKE:
            s = sensors[rng.integers(0, len(sensors))]
            mean, std, _ = profile[s]
            spike = rng.choice([-1, 1]) * rng.uniform(3 * std, 6 * std)
            data[s][i] += spike
            is_anomalous[i] = True
            _sev = "WARNING" if abs(spike) < 5 * std else "CRITICAL"
            kind[i], kind_sens[i], kind_sev[i] = "spike", s, _sev
            event_records.append({"machine_id": machine_id, "timestamp": ts.isoformat(),
                "anomaly_type": "spike", "sensor_affected": s, "severity": _sev})

        # ── Drifts and NaN : per sensor (rare start events)
        for s in sensors:
            mean, std, _ = profile[s]

            if in_drift[s] is None and rng.random() < ANOMALY_DRIFT_PROB:
                in_drift[s] = i
                event_records.append({"machine_id": machine_id, "timestamp": ts.isoformat(),
                    "anomaly_type": "drift", "sensor_affected": s, "severity": "WARNING"})
            elif in_drift[s] is not None:
                data[s][i] += std * ((i - in_drift[s]) / DRIFT_MAX_STEPS) * 2.5
                is_anomalous[i] = True  # label ALL drift timesteps
                kind[i], kind_sens[i], kind_sev[i] = "drift", s, "WARNING"
                if i - in_drift[s] >= DRIFT_MAX_STEPS:
                    in_drift[s] = None

            elif in_nan[s] is None and rng.random() < NAN_PROB:
                in_nan[s] = i
                event_records.append({"machine_id": machine_id, "timestamp": ts.isoformat(),
                    "anomaly_type": "sensor_cutoff", "sensor_affected": s, "severity": "CRITICAL"})
            elif in_nan[s] is not None:
                data[s][i] = np.nan
                is_anomalous[i] = True  # label ALL NaN timesteps
                kind[i], kind_sens[i], kind_sev[i] = "sensor_cutoff", s, "CRITICAL"
                if i - in_nan[s] >= rng.integers(10, 60):
                    in_nan[s] = None

    # Build anomaly_records from ALL labeled timesteps (used by ML evaluation).
    # Each labelled row carries the real anomaly type/sensor/severity when known
    # (spike / drift / sensor_cutoff); the labelled set itself is unchanged.
    anomaly_records: list[dict] = []
    for i, ts in enumerate(timestamps):
        if is_anomalous[i]:
            anomaly_records.append({
                "machine_id":    machine_id,
                "timestamp":     ts.isoformat(),
                "anomaly_type":  kind[i] or "labeled",
                "sensor_affected": kind_sens[i] or "any",
                "severity":      kind_sev[i] or "WARNING",
                "injected":      1,
            })

    for s in sensors:
        lo, hi = limits[s]
        data[s] = np.clip(data[s], lo, hi)

    df = pd.DataFrame({
        "machine_id":  machine_id,
        "timestamp":   [t.isoformat() for t in timestamps],
        "temperature": data["temperature"].round(2),
        "vibration":   data["vibration"].round(3),
        "pression":    data["pression"].round(3),
        "courant":     data["courant"].round(2),
        "rpm":         data["rpm"].round(1),
        "shift":       [_shift(t) for t in timestamps],
    })

    logger.info(f"[{machine_id}] Generated {len(df):,} readings | {len(anomaly_records)} anomalies injected")
    return df, anomaly_records


def generate_all(months: int = 6, freq_seconds: int = 30) -> None:
    """Generate and persist data for all machines to the configured database.

    Args:
        months: Number of months of history to simulate.
        freq_seconds: Interval between sensor readings in seconds.
    """
    logger.info("=" * 60)
    logger.info("OCP Bionic — Data Generator Starting")
    logger.info("=" * 60)

    end   = datetime.now().replace(second=0, microsecond=0)
    start = end - timedelta(days=30 * months)
    logger.info(f"Period: {start.date()} → {end.date()} | Interval: {freq_seconds}s")

    engine = get_engine()
    init_schema(engine)

    # Insert machines
    locations = ["Khouribga Site A", "Benguerir Site B", "Jorf Lasfar", "Youssoufia", "Safi"]
    with engine.begin() as conn:
        for i, m in enumerate(MACHINES):
            conn.execute(text("""
                INSERT INTO machines (id, name, type, location, installed)
                VALUES (:id, :name, :type, :loc, :inst)
                ON CONFLICT (id) DO NOTHING
            """ if engine.dialect.name == "postgresql" else """
                INSERT OR IGNORE INTO machines (id, name, type, location, installed)
                VALUES (:id, :name, :type, :loc, :inst)
            """), {"id": m["id"], "name": m["name"], "type": m["type"],
                   "loc": locations[i], "inst": "2020-01-01"})
    logger.info(f"Inserted {len(MACHINES)} machines.")

    total_rows = 0
    total_anomalies = 0

    for machine in MACHINES:
        df, anomalies = generate_machine_data(machine, start, end, freq_seconds)
        df.to_sql("sensor_readings", engine, if_exists="append", index=False, chunksize=100)
        total_rows += len(df)

        if anomalies:
            anom_df = pd.DataFrame(anomalies)
            anom_df.to_sql("anomalies", engine, if_exists="append", index=False, chunksize=100)
            total_anomalies += len(anomalies)

    logger.success(f"✓ Total rows inserted   : {total_rows:,}")
    logger.success(f"✓ Total anomalies logged: {total_anomalies:,}")
    logger.success(f"✓ Database              : {engine.url}")

    summary = {
        "generated_at": datetime.now().isoformat(),
        "period_start": start.isoformat(), "period_end": end.isoformat(),
        "freq_seconds": freq_seconds, "total_rows": total_rows,
        "total_anomalies": total_anomalies, "machines": [m["id"] for m in MACHINES],
    }
    out = DATA_DIR / "processed" / "generation_summary.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(summary, indent=2))
    logger.info(f"Summary written to {out}")



def init_db(conn) -> None:
    """Create all required tables in a sqlite3 connection.

    Accepts a standard sqlite3 connection (used by tests).

    Args:
        conn: sqlite3.Connection instance.
    """
    ddl = [
        """CREATE TABLE IF NOT EXISTS machines (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL,
            location TEXT, installed TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS sensor_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, machine_id TEXT NOT NULL,
            timestamp TEXT NOT NULL, temperature REAL, vibration REAL,
            pression REAL, courant REAL, rpm REAL, shift TEXT,
            FOREIGN KEY (machine_id) REFERENCES machines(id))""",
        """CREATE INDEX IF NOT EXISTS idx_readings_machine_ts
            ON sensor_readings (machine_id, timestamp)""",
        """CREATE TABLE IF NOT EXISTS anomalies (
            id INTEGER PRIMARY KEY AUTOINCREMENT, machine_id TEXT NOT NULL,
            timestamp TEXT NOT NULL, anomaly_type TEXT NOT NULL,
            sensor_affected TEXT, severity TEXT, injected INTEGER DEFAULT 1,
            FOREIGN KEY (machine_id) REFERENCES machines(id))""",
        """CREATE TABLE IF NOT EXISTS ml_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, machine_id TEXT NOT NULL,
            timestamp TEXT NOT NULL, anomaly_score REAL, is_anomaly INTEGER,
            severity TEXT, model_version TEXT, inference_ms REAL,
            features_json TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS judge_evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, decision_id INTEGER,
            machine_id TEXT NOT NULL, timestamp TEXT NOT NULL,
            global_score REAL, relevance_score REAL, history_score REAL,
            confidence_score REAL, compliance_score REAL, feasibility_score REAL,
            agreement INTEGER, feedback TEXT, flagged_issues TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL, machine_id TEXT, user_id TEXT DEFAULT 'system',
            action TEXT NOT NULL, details TEXT, severity TEXT DEFAULT 'INFO')""",
    ]
    cursor = conn.cursor()
    for stmt in ddl:
        cursor.execute(stmt)
    conn.commit()


def insert_machines(conn) -> None:
    """Insert all 5 MACHINES into the machines table.

    Args:
        conn: sqlite3.Connection instance.
    """
    locations = ["Khouribga Site A", "Benguerir Site B", "Jorf Lasfar", "Youssoufia", "Safi"]
    cursor = conn.cursor()
    for i, m in enumerate(MACHINES):
        cursor.execute(
            "INSERT OR IGNORE INTO machines (id, name, type, location, installed) VALUES (?,?,?,?,?)",
            (m["id"], m["name"], m["type"], locations[i], "2020-01-01"),
        )
    conn.commit()


if __name__ == "__main__":
    generate_all(months=6, freq_seconds=30)
