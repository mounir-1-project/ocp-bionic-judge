"""Tests for data/data_generator.py"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import sys
sys.path.insert(0, str(Path(__file__).parents[1]))

from data.data_generator import (
    MACHINES,
    generate_machine_data,
    init_db,
    insert_machines,
    _shift,
)


def test_shift_matin() -> None:
    """_shift returns 'matin' for morning hours."""
    assert _shift(datetime(2024, 1, 1, 8, 0)) == "matin"


def test_shift_soir() -> None:
    """_shift returns 'soir' for afternoon."""
    assert _shift(datetime(2024, 1, 1, 16, 0)) == "soir"


def test_shift_nuit() -> None:
    """_shift returns 'nuit' for night hours."""
    assert _shift(datetime(2024, 1, 1, 2, 0)) == "nuit"


@pytest.mark.parametrize("hour,expected", [(6, "matin"), (14, "soir"), (22, "nuit"), (0, "nuit")])
def test_shift_boundaries(hour, expected) -> None:
    """_shift correctly handles boundary hours."""
    assert _shift(datetime(2024, 1, 1, hour, 0)) == expected


def test_generate_machine_data_shape() -> None:
    """generate_machine_data returns correct number of rows."""
    machine = MACHINES[0]
    start = datetime.now() - timedelta(hours=2)
    end = datetime.now()
    df, anomalies = generate_machine_data(machine, start, end, freq_seconds=30)
    expected_rows = int(2 * 3600 / 30)
    assert len(df) == pytest.approx(expected_rows, abs=5)


def test_generate_machine_data_columns() -> None:
    """generate_machine_data DataFrame has required columns."""
    machine = MACHINES[0]
    start = datetime.now() - timedelta(hours=1)
    df, _ = generate_machine_data(machine, start, datetime.now(), freq_seconds=60)
    for col in ["machine_id", "timestamp", "temperature", "vibration", "pression", "courant", "rpm", "shift"]:
        assert col in df.columns, f"Missing column: {col}"


def test_generate_machine_data_no_extreme_values() -> None:
    """Sensor values stay within physical limits."""
    machine = MACHINES[0]
    start = datetime.now() - timedelta(hours=2)
    df, _ = generate_machine_data(machine, start, datetime.now(), freq_seconds=60)
    assert df["temperature"].dropna().between(20, 90).all()
    assert df["vibration"].dropna().between(0, 10).all()
    assert df["pression"].dropna().between(1, 10).all()


def test_anomalies_are_injected() -> None:
    """At least some anomalies are injected in a 6-month simulation."""
    machine = MACHINES[0]
    start = datetime.now() - timedelta(days=30)
    df, anomalies = generate_machine_data(machine, start, datetime.now(), freq_seconds=300)
    assert len(anomalies) > 0, "No anomalies injected in 30-day simulation"


def test_all_machines_have_data() -> None:
    """All 5 machines can generate data."""
    start = datetime.now() - timedelta(hours=1)
    end = datetime.now()
    for machine in MACHINES:
        df, _ = generate_machine_data(machine, start, end, freq_seconds=120)
        assert len(df) > 0, f"No data for {machine['id']}"


def test_init_db_creates_tables(tmp_path) -> None:
    """init_db creates all expected tables."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    init_db(conn)
    tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'", conn)["name"].tolist()
    conn.close()
    for table in ["machines", "sensor_readings", "anomalies", "ml_decisions", "judge_evaluations", "audit_log"]:
        assert table in tables, f"Table {table} missing"


def test_insert_machines(tmp_path) -> None:
    """insert_machines inserts exactly 5 machine records."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    init_db(conn)
    insert_machines(conn)
    count = pd.read_sql("SELECT COUNT(*) as n FROM machines", conn).iloc[0]["n"]
    conn.close()
    assert count == 5