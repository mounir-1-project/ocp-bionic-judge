"""Tests for src/models/ modules."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import numpy as np
import pytest
from sklearn.ensemble import IsolationForest

import sys
sys.path.insert(0, str(Path(__file__).parents[1]))


# ── Drift Detector Tests ──────────────────────────────────────────────────────

from src.models.drift_detector import compute_psi, compute_ks_test, check_drift


def test_psi_zero_for_identical_distributions() -> None:
    """PSI should be ~0 for identical distributions."""
    rng = np.random.default_rng(1)
    data = rng.normal(0, 1, 1000)
    psi = compute_psi(data, data)
    assert psi < 0.01


def test_psi_high_for_shifted_distribution() -> None:
    """PSI should be > 0.2 for significantly different distributions."""
    rng = np.random.default_rng(2)
    ref = rng.normal(0, 1, 1000)
    cur = rng.normal(5, 1, 1000)  # large shift
    psi = compute_psi(ref, cur)
    assert psi > 0.2


def test_psi_returns_float() -> None:
    """compute_psi always returns a float."""
    ref = np.random.default_rng(3).normal(0, 1, 500)
    cur = np.random.default_rng(4).normal(0, 1, 500)
    assert isinstance(compute_psi(ref, cur), float)


def test_psi_empty_arrays() -> None:
    """compute_psi handles empty arrays gracefully."""
    result = compute_psi(np.array([]), np.array([]))
    assert result == 0.0


def test_ks_test_identical() -> None:
    """KS test p-value should be high (>0.05) for identical distributions."""
    data = np.random.default_rng(5).normal(0, 1, 500)
    _, pvalue = compute_ks_test(data, data.copy())
    assert pvalue == 1.0


def test_ks_test_different() -> None:
    """KS test p-value should be very low for very different distributions."""
    rng = np.random.default_rng(6)
    ref = rng.normal(0, 1, 500)
    cur = rng.normal(10, 1, 500)
    _, pvalue = compute_ks_test(ref, cur)
    assert pvalue < 0.01


def test_check_drift_insufficient_data(tmp_db_path) -> None:
    """check_drift returns status='insufficient_data' when DB is near empty."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        empty_db = Path(f.name)

    conn = sqlite3.connect(str(empty_db))
    conn.execute("""CREATE TABLE IF NOT EXISTS ml_decisions (
        id INTEGER PRIMARY KEY, anomaly_score REAL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY, timestamp TEXT, event_type TEXT, action TEXT, details TEXT, severity TEXT)")
    conn.commit()
    conn.close()

    result = check_drift(db_path=empty_db)
    assert result.get("status") == "insufficient_data"
    empty_db.unlink(missing_ok=True)


# ── Model Training Tests ──────────────────────────────────────────────────────

def test_isolation_forest_predicts() -> None:
    """IsolationForest trains and predicts on synthetic data."""
    rng = np.random.default_rng(42)
    X = rng.normal(0, 1, (200, 5))
    model = IsolationForest(n_estimators=10, contamination=0.05, random_state=42)
    model.fit(X)
    preds = model.predict(X)
    assert set(preds).issubset({1, -1})
    assert len(preds) == 200


def test_isolation_forest_contamination_rate() -> None:
    """IsolationForest anomaly rate ≈ contamination parameter."""
    rng = np.random.default_rng(42)
    X = rng.normal(0, 1, (1000, 5))
    model = IsolationForest(n_estimators=50, contamination=0.05, random_state=42)
    model.fit(X)
    preds = model.predict(X)
    anomaly_rate = (preds == -1).mean()
    assert 0.03 <= anomaly_rate <= 0.07


@pytest.mark.parametrize("contamination", [0.03, 0.05, 0.10])
def test_isolation_forest_various_contaminations(contamination) -> None:
    """IsolationForest works with different contamination values."""
    rng = np.random.default_rng(42)
    X = rng.normal(0, 1, (300, 3))
    model = IsolationForest(contamination=contamination, random_state=42)
    model.fit(X)
    assert hasattr(model, "decision_function")