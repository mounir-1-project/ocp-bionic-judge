"""Tests for src/models/predict.py

Tests cover the public helpers that do not require a trained model file:
  - _apply_pipeline : feature extraction from model bundle
  - _score_to_severity : anomaly-score -> severity label mapping
  - _save_predictions : persistence to ml_decisions table
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.models.predict import (
    _apply_pipeline,
    _score_to_severity,
    _save_predictions,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sensor_df() -> pd.DataFrame:
    """Small sensor DataFrame for testing."""
    rng = np.random.default_rng(42)
    n = 50
    # Valid, monotonically increasing ISO timestamps (30s apart). The previous
    # f"2025-01-01T{i:02d}:00:00" produced invalid hours like "24:00:00" for i>=24.
    timestamps = pd.date_range("2025-01-01", periods=n, freq="30s").strftime(
        "%Y-%m-%dT%H:%M:%S"
    ).tolist()
    return pd.DataFrame({
        "machine_id":  ["BROYEUR_01"] * n,
        "timestamp":   timestamps,
        "temperature": rng.normal(65, 5, n).round(2),
        "vibration":   rng.normal(4, 0.5, n).round(3),
        "pression":    rng.normal(3, 0.3, n).round(3),
        "courant":     rng.normal(35, 3, n).round(2),
        "rpm":         rng.normal(1450, 30, n).round(1),
        "shift":       ["matin"] * n,
    })


@pytest.fixture
def ml_decisions_engine(tmp_path):
    """SQLite engine with ml_decisions table for testing _save_predictions."""
    engine = create_engine(f"sqlite:///{tmp_path}/test_predict.db")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE ml_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id TEXT, timestamp TEXT,
                anomaly_score REAL, is_anomaly INTEGER,
                severity TEXT, model_version TEXT,
                inference_ms REAL, features_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
    return engine


# ── _apply_pipeline — legacy fallback (no pipeline in bundle) ─────────────────

def test_apply_pipeline_legacy_shape(sensor_df) -> None:
    """Bundle without 'pipeline' falls back to lightweight 15-feature extractor."""
    bundle = {"model": MagicMock(), "name": "IsolationForest", "pipeline": None}
    X, feature_cols = _apply_pipeline(sensor_df, bundle)
    assert X.shape[0] == len(sensor_df)
    assert X.shape[1] == 15   # 5 sensors x (raw + roll_mean + roll_std)


def test_apply_pipeline_legacy_col_names(sensor_df) -> None:
    """Legacy fallback returns expected feature column names."""
    bundle = {"model": MagicMock(), "name": "IsolationForest", "pipeline": None}
    _, feature_cols = _apply_pipeline(sensor_df, bundle)
    assert "temperature" in feature_cols
    assert "temperature_roll_mean" in feature_cols
    assert "temperature_roll_std" in feature_cols
    assert len(feature_cols) == 15


def test_apply_pipeline_legacy_no_nan(sensor_df) -> None:
    """Legacy fallback output has no NaN values."""
    bundle = {"model": MagicMock(), "name": "IsolationForest", "pipeline": None}
    X, _ = _apply_pipeline(sensor_df, bundle)
    assert not np.isnan(X).any()


def test_apply_pipeline_legacy_no_inf(sensor_df) -> None:
    """Legacy fallback output has no Inf values."""
    bundle = {"model": MagicMock(), "name": "IsolationForest", "pipeline": None}
    X, _ = _apply_pipeline(sensor_df, bundle)
    assert not np.isinf(X).any()


def test_apply_pipeline_legacy_with_nan_input(sensor_df) -> None:
    """Legacy fallback handles NaN sensor readings gracefully."""
    sensor_df.loc[5:10, "temperature"] = np.nan
    bundle = {"model": MagicMock(), "name": "IsolationForest", "pipeline": None}
    X, _ = _apply_pipeline(sensor_df, bundle)
    assert not np.isnan(X).any()


# ── _apply_pipeline — full pipeline path ────────────────────────────────────

def test_apply_pipeline_uses_bundle_pipeline(sensor_df) -> None:
    """When bundle has a fitted pipeline, it is applied correctly."""
    from src.features.feature_engineering import build_feature_pipeline, get_numeric_feature_cols
    pipeline = build_feature_pipeline(scale=True)
    transformed = pipeline.fit_transform(sensor_df)
    feature_cols = get_numeric_feature_cols(transformed)

    bundle = {
        "model":        MagicMock(),
        "name":         "IsolationForest",
        "pipeline":     pipeline,
        "feature_cols": feature_cols,
    }
    X, cols = _apply_pipeline(sensor_df, bundle)
    assert X.shape[0] == len(sensor_df)
    assert X.shape[1] == len(feature_cols)
    assert not np.isnan(X).any()
    assert cols == feature_cols


def test_apply_pipeline_full_feature_count(sensor_df) -> None:
    """Full pipeline produces the 24 focused features (more than the 15-feature fallback)."""
    from src.features.feature_engineering import build_feature_pipeline, get_numeric_feature_cols

    pipeline = build_feature_pipeline(scale=True)
    transformed = pipeline.fit_transform(sensor_df)
    feature_cols = get_numeric_feature_cols(transformed)

    bundle = {
        "model":        MagicMock(),
        "name":         "IsolationForest",
        "pipeline":     pipeline,
        "feature_cols": feature_cols,
    }
    X, cols = _apply_pipeline(sensor_df, bundle)
    assert X.shape[1] == 24
    assert X.shape[1] > 15  # richer than the lightweight fallback
    assert not np.isnan(X).any()