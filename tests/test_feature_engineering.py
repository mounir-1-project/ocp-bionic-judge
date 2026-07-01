"""Tests for src/features/feature_engineering.py"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.features.feature_engineering import (
    RollingFeatureExtractor,
    ZScoreNormalizer,
    DeltaFeatureExtractor,
    TemporalFeatureExtractor,
    SensorCutoffIndicator,
    build_feature_pipeline,
    get_numeric_feature_cols,
    SENSORS,
)


@pytest.fixture
def small_df(sample_sensor_df):
    return sample_sensor_df


def test_rolling_feature_extractor_adds_local_z(small_df) -> None:
    """RollingFeatureExtractor adds one local z-score column per sensor."""
    ext = RollingFeatureExtractor()
    result = ext.fit_transform(small_df)
    assert "temperature_local_z" in result.columns
    assert "vibration_local_z" in result.columns


def test_rolling_feature_extractor_no_nan(small_df) -> None:
    """Local z-score features should not produce NaN."""
    ext = RollingFeatureExtractor()
    result = ext.fit_transform(small_df)
    local_cols = [c for c in result.columns if c.endswith("_local_z")]
    assert result[local_cols].isna().sum().sum() == 0


def test_zscore_normalizer_zero_mean(small_df) -> None:
    """ZScoreNormalizer z-scores should have approx mean=0 per machine."""
    norm = ZScoreNormalizer()
    norm.fit(small_df)
    result = norm.transform(small_df)
    for machine in small_df["machine_id"].unique():
        mask = result["machine_id"] == machine
        for s in SENSORS:
            col = f"{s}_zscore"
            if col in result.columns:
                assert abs(result.loc[mask, col].mean()) < 0.5


def test_delta_extractor_delta_columns(small_df) -> None:
    """DeltaFeatureExtractor adds one absolute-delta column per sensor."""
    ext = DeltaFeatureExtractor()
    result = ext.fit_transform(small_df)
    assert "temperature_delta" in result.columns
    assert "rpm_delta" in result.columns
    # |delta| is always non-negative
    assert (result["temperature_delta"] >= 0).all()


def test_temporal_extractor_adds_hour(small_df) -> None:
    """TemporalFeatureExtractor adds hour and shift columns."""
    ext = TemporalFeatureExtractor()
    result = ext.fit_transform(small_df)
    assert "hour" in result.columns
    assert "day_of_week" in result.columns
    assert result["hour"].between(0, 23).all()


def test_cutoff_indicator_flags_nan() -> None:
    """SensorCutoffIndicator adds binary nan flags."""
    df = pd.DataFrame({
        "machine_id": ["A"] * 5,
        "timestamp": ["2024-01-01"] * 5,
        "temperature": [65.0, np.nan, 66.0, np.nan, 64.0],
        "vibration":   [4.0, 4.1, np.nan, 4.0, 4.2],
        "pression":    [3.0] * 5,
        "courant":     [35.0] * 5,
        "rpm":         [1450.0] * 5,
    })
    ind = SensorCutoffIndicator()
    result = ind.fit_transform(df)
    assert result["temperature_is_nan"].sum() == 2
    assert result["vibration_is_nan"].sum() == 1
    assert result["temperature"].isna().sum() == 0  # NaN filled


def test_cutoff_indicator_fills_nan(small_df) -> None:
    """SensorCutoffIndicator fills NaN with median."""
    df_with_nan = small_df.copy()
    df_with_nan.loc[:5, "temperature"] = np.nan
    ind = SensorCutoffIndicator()
    result = ind.fit_transform(df_with_nan)
    assert result["temperature"].isna().sum() == 0


def test_build_feature_pipeline_runs(small_df) -> None:
    """Full pipeline runs end to end without errors."""
    pipeline = build_feature_pipeline(scale=True)
    pipeline.fit(small_df)
    result = pipeline.transform(small_df)
    assert len(result) == len(small_df)
    assert result.shape[1] > small_df.shape[1]


def test_pipeline_produces_24_model_features(small_df) -> None:
    """The focused v2 pipeline yields exactly 24 model features."""
    pipeline = build_feature_pipeline(scale=True)
    result = pipeline.fit_transform(small_df)
    cols = get_numeric_feature_cols(result)
    assert len(cols) == 24
    # raw sensors are excluded from the model features
    for s in SENSORS:
        assert s not in cols


def test_pipeline_no_inf_values(small_df) -> None:
    """Pipeline output contains no Inf values."""
    pipeline = build_feature_pipeline(scale=False)
    pipeline.fit(small_df)
    result = pipeline.transform(small_df)
    num_cols = result.select_dtypes(include=[np.number]).columns
    assert not np.isinf(result[num_cols].fillna(0).values).any()