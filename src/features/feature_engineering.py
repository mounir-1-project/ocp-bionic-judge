"""
Pipeline de feature engineering pour les données capteurs.
Les données brutes (5 capteurs) sont transformées en 24 features à fort pouvoir
de séparation (signal-focused) qui permettent au modèle de détecter spikes,
drifts et coupures.

⚠️ Note méthodologique (v2 — focused feature set)
La première version produisait ~102 features (60 rolling mean/std/min/max sur 3
fenêtres + lags + ratios bruts). Sur un modèle d'isolation (Isolation Forest), où
chaque coupure d'arbre tire UNE feature au hasard, ces ~95 features faiblement
informatives noyaient les ~5 signaux réellement discriminants : l'AUC-ROC tombait
à ~0.51 (équivalent au hasard). La v2 recentre la pipeline sur des features
physiquement motivées et standardisées par machine, ce qui fait remonter l'AUC-ROC
à 0.82 (Isolation Forest déployé) / 0.93 (One-Class SVM, leader AUC). Voir docs/decisions/ADR-003.

Feature groups (post-pipeline) — 24 features numériques :
  - 5 z-scores par machine        (écart à la normale historique de CETTE machine)
  - 5 NaN-flag indicators         (coupures capteur — type d'anomalie à part entière)
  - 5 local z-scores (rolling)    (écart à la baseline glissante → spikes & drifts)
  - 5 deltas absolus              (variation instantanée → spikes)
  - 4 temporal features           (hour, day_of_week, is_weekend, shift_encoded)
  Total : 24 features numériques
  (Les 5 capteurs bruts servent au calcul mais sont exclus des features du modèle :
   à l'échelle brute ils encodent surtout l'identité de la machine, pas l'anomalie.)

Author: Mounir Sanbouli
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import text

from src.config import GEMINI_MODEL  # noqa: F401 — ensures load_dotenv() called
from src.db import get_engine


SENSORS = ["temperature", "vibration", "pression", "courant", "rpm"]

# Single short window (≈20 min @ 30s) for the rolling baseline used by the local
# z-score. A short window reacts to spikes; the per-machine z-score (ZScoreNormalizer)
# already captures the global deviation, so multi-window rolling stats are redundant.
ROLL_WINDOW = 40


class RollingFeatureExtractor(TransformerMixin, BaseEstimator):
    """Compute a per-sensor *local* z-score over a short rolling window, per machine.

    For each sensor we compute ``(x - rolling_mean) / rolling_std`` over a short
    window. Unlike a raw rolling mean (which stays on the sensor's native scale and
    mostly encodes the machine identity), this *standardised deviation from the local
    baseline* is directly anomaly-informative: a spike or a drift pushes it far from 0.

    Args:
        sensors: List of sensor column names.
        window: Rolling window size in periods.
    """

    def __init__(self, sensors: list[str] = SENSORS, window: int = ROLL_WINDOW) -> None:
        """Initialize with sensor list and window size."""
        self.sensors = sensors
        self.window = window

    def fit(self, X: pd.DataFrame, y=None) -> "RollingFeatureExtractor":
        """Fit (no-op — stateless transformer).

        Args:
            X: Input DataFrame.
            y: Ignored.

        Returns:
            self.
        """
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Add one ``{sensor}_local_z`` column per sensor, computed per machine.

        Args:
            X: DataFrame with sensor columns and 'machine_id'.

        Returns:
            DataFrame enriched with local z-score columns.
        """
        parts: list[pd.DataFrame] = []
        for _, group in X.groupby("machine_id", sort=False):
            g = group.copy().sort_values("timestamp")
            for s in self.sensors:
                col = g[s]
                roll_mean = col.rolling(self.window, min_periods=1).mean()
                roll_std = col.rolling(self.window, min_periods=1).std().fillna(0.0)
                g[f"{s}_local_z"] = ((col - roll_mean) / (roll_std + 1e-6)).clip(-10, 10)
            parts.append(g)
        logger.debug(f"Local z-score features computed for {X['machine_id'].nunique()} machines.")
        return pd.concat(parts, axis=0).reset_index(drop=True)


class ZScoreNormalizer(TransformerMixin, BaseEstimator):
    """Per-machine Z-score normalization for each sensor.

    This is the single strongest feature group: it measures how far a reading is
    from the historical normal of THAT specific machine (not the global normal).

    Args:
        sensors: List of sensor column names.
    """

    def __init__(self, sensors: list[str] = SENSORS) -> None:
        """Initialize with sensor list."""
        self.sensors = sensors
        self._stats: dict[str, dict[str, tuple[float, float]]] = {}

    def fit(self, X: pd.DataFrame, y=None) -> "ZScoreNormalizer":
        """Compute per-machine mean and std for each sensor.

        Args:
            X: DataFrame with sensor columns and 'machine_id'.
            y: Ignored.

        Returns:
            self.
        """
        for machine_id, group in X.groupby("machine_id"):
            self._stats[machine_id] = {}
            for s in self.sensors:
                m = group[s].mean()
                sd = group[s].std()
                self._stats[machine_id][s] = (m, sd if sd > 0 else 1.0)
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Apply Z-score normalization per machine per sensor.

        Args:
            X: DataFrame with sensor columns and 'machine_id'.

        Returns:
            DataFrame with added z-score columns.
        """
        result = X.copy()
        for machine_id, group in result.groupby("machine_id"):
            stats = self._stats.get(machine_id, {})
            for s in self.sensors:
                if s in stats:
                    mean, std = stats[s]
                    result.loc[group.index, f"{s}_zscore"] = (group[s] - mean) / std
                else:
                    result.loc[group.index, f"{s}_zscore"] = 0.0
        return result


class DeltaFeatureExtractor(TransformerMixin, BaseEstimator):
    """Compute the absolute rate of change per sensor, per machine.

    A spike produces a large instantaneous |delta|. Lag features (t-1, t-5, t-10)
    were dropped in v2: on an isolation model they added dimensionality without
    discriminative power and diluted the AUC.

    Args:
        sensors: List of sensor column names.
    """

    def __init__(self, sensors: list[str] = SENSORS) -> None:
        """Initialize with sensor list."""
        self.sensors = sensors

    def fit(self, X: pd.DataFrame, y=None) -> "DeltaFeatureExtractor":
        """Fit (no-op — stateless transformer).

        Args:
            X: Input DataFrame.
            y: Ignored.

        Returns:
            self.
        """
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Add one ``{sensor}_delta`` (absolute first difference) column per sensor.

        Args:
            X: DataFrame with sensor columns and 'machine_id'.

        Returns:
            DataFrame with delta columns added.
        """
        parts: list[pd.DataFrame] = []
        for _, group in X.groupby("machine_id", sort=False):
            g = group.copy().sort_values("timestamp")
            for s in self.sensors:
                g[f"{s}_delta"] = g[s].diff().abs().fillna(0.0)
            parts.append(g)
        return pd.concat(parts).reset_index(drop=True)


class TemporalFeatureExtractor(TransformerMixin, BaseEstimator):
    """Extract calendar and shift features from timestamp column.

    Args:
        timestamp_col: Name of the timestamp column.
    """

    def __init__(self, timestamp_col: str = "timestamp") -> None:
        """Initialize with timestamp column name."""
        self.timestamp_col = timestamp_col

    def fit(self, X: pd.DataFrame, y=None) -> "TemporalFeatureExtractor":
        """Fit (no-op — stateless transformer).

        Args:
            X: Input DataFrame.
            y: Ignored.

        Returns:
            self.
        """
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Add hour, day_of_week, is_weekend and shift_encoded columns.

        Args:
            X: DataFrame with timestamp column.

        Returns:
            DataFrame with temporal features added.
        """
        result = X.copy()
        ts = pd.to_datetime(result[self.timestamp_col])
        result["hour"] = ts.dt.hour
        result["day_of_week"] = ts.dt.dayofweek
        result["is_weekend"] = (result["day_of_week"] >= 5).astype(int)
        result["shift_encoded"] = result.get("shift", pd.Series(["matin"] * len(result))).map(
            {"matin": 1, "soir": 2, "nuit": 0}
        ).fillna(1)
        return result


class SensorCutoffIndicator(TransformerMixin, BaseEstimator):
    """Binary flags for missing sensor readings (sensor cut-off = anomaly type).

    Args:
        sensors: List of sensor column names.
    """

    def __init__(self, sensors: list[str] = SENSORS) -> None:
        """Initialize with sensor list."""
        self.sensors = sensors

    def fit(self, X: pd.DataFrame, y=None) -> "SensorCutoffIndicator":
        """Fit (no-op — stateless transformer).

        Args:
            X: Input DataFrame.
            y: Ignored.

        Returns:
            self.
        """
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Add binary NaN-flag columns and fill missing values with median.

        Args:
            X: DataFrame with sensor columns.

        Returns:
            DataFrame with NaN flags and filled sensor values.
        """
        result = X.copy()
        for s in self.sensors:
            result[f"{s}_is_nan"] = result[s].isna().astype(int)
            result[s] = result[s].fillna(result[s].median())
        return result


# Columns that are NEVER fed to the model: metadata + the raw sensor values
# (kept in the frame for computation but excluded as features — at raw scale they
# encode the machine identity rather than the anomaly).
_EXCLUDE_FROM_MODEL = {"machine_id", "timestamp", "shift", "id", *SENSORS}


class FinalScaler(TransformerMixin, BaseEstimator):
    """Apply StandardScaler to the model feature columns (everything except metadata,
    raw sensors and binary NaN flags, which are already 0/1)."""

    def __init__(self) -> None:
        """Initialize the scaler."""
        self._scaler = StandardScaler()
        self._fitted_cols: list[str] = []

    def _feature_cols(self, X: pd.DataFrame) -> list[str]:
        """Return continuous feature columns to scale (excludes meta, raw, *_is_nan)."""
        return [
            c for c in X.columns
            if c not in _EXCLUDE_FROM_MODEL
            and not c.endswith("_is_nan")
            and pd.api.types.is_numeric_dtype(X[c])
        ]

    def fit(self, X: pd.DataFrame, y=None) -> "FinalScaler":
        """Fit the StandardScaler on the continuous feature columns.

        Args:
            X: Transformed DataFrame.
            y: Ignored.

        Returns:
            self.
        """
        self._fitted_cols = self._feature_cols(X)
        if self._fitted_cols:
            self._scaler.fit(X[self._fitted_cols].fillna(0))
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Apply the fitted scaler to the continuous feature columns.

        Args:
            X: DataFrame to scale.

        Returns:
            Scaled DataFrame.
        """
        result = X.copy()
        cols = [c for c in self._fitted_cols if c in result.columns]
        if cols:
            result[cols] = self._scaler.transform(result[cols].fillna(0))
        return result


def get_numeric_feature_cols(df: pd.DataFrame) -> list[str]:
    """Return the model feature column names from a pipeline-transformed DataFrame.

    Excludes metadata columns AND the raw sensor columns (machine_id, timestamp,
    shift, id, and the 5 raw sensors) so the result is safe to pass directly to a
    sklearn model. The expected result is the 24 focused features.

    Args:
        df: DataFrame output of ``build_feature_pipeline().fit_transform()``.

    Returns:
        Ordered list of numeric feature column names.
    """
    return [
        c for c in df.columns
        if c not in _EXCLUDE_FROM_MODEL and pd.api.types.is_numeric_dtype(df[c])
    ]


def extract_model_features(df: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    """Lightweight 15-feature extractor used by unit tests and quick prototyping.

    Computes 5 raw sensors + rolling mean + rolling std per sensor (15 features).
    This is a **simplified** extractor for tests and fallback usage only.
    Production training and inference use ``build_feature_pipeline`` which produces
    the 24 focused features — see ``get_numeric_feature_cols`` for the full list.

    Args:
        df: DataFrame with sensor columns and 'machine_id'.

    Returns:
        Tuple of (feature matrix as np.ndarray, list of feature column names).
    """
    sensors = ["temperature", "vibration", "pression", "courant", "rpm"]
    feature_cols: list[str] = []
    df = df.copy()
    for s in sensors:
        df[f"{s}_roll_mean"] = df.groupby("machine_id")[s].transform(
            lambda x: x.rolling(10, min_periods=1).mean()
        )
        df[f"{s}_roll_std"] = df.groupby("machine_id")[s].transform(
            lambda x: x.rolling(10, min_periods=1).std().fillna(0)
        )
        feature_cols += [s, f"{s}_roll_mean", f"{s}_roll_std"]
    df = df.fillna(df.median(numeric_only=True))
    return df[feature_cols].values, feature_cols


def build_feature_pipeline(scale: bool = True) -> Pipeline:
    """Build the complete feature engineering pipeline (24 focused features).

    Order matters: the cut-off indicator must run first (NaN flags computed before
    the median fill), then the per-machine z-score, the local rolling z-score, the
    deltas and the temporal features. The optional final scaler standardises the
    continuous features.

    Args:
        scale: Whether to include the final scaling step.

    Returns:
        scikit-learn Pipeline instance.
    """
    steps = [
        ("cutoff_indicator", SensorCutoffIndicator()),
        ("temporal",         TemporalFeatureExtractor()),
        ("zscore",           ZScoreNormalizer()),
        ("rolling",          RollingFeatureExtractor()),
        ("delta",            DeltaFeatureExtractor()),
    ]
    if scale:
        steps.append(("scaler", FinalScaler()))
    return Pipeline(steps)


def load_raw_data(machine_id: Optional[str] = None, limit: Optional[int] = None) -> pd.DataFrame:
    """Load raw sensor readings from the configured database.

    Args:
        machine_id: Optional machine filter.
        limit: Optional row limit.

    Returns:
        DataFrame of sensor readings.
    """
    engine = get_engine()
    query = "SELECT * FROM sensor_readings"
    params: dict = {}
    if machine_id:
        query += " WHERE machine_id = :machine_id"
        params["machine_id"] = machine_id
    query += " ORDER BY machine_id, timestamp"
    if limit:
        query += " LIMIT :limit"
        params["limit"] = int(limit)  # parameterized — no f-string injection

    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn, params=params)
    logger.info(f"Loaded {len(df):,} raw readings from DB.")
    return df


if __name__ == "__main__":
    logger.info("Running feature engineering pipeline...")
    raw = load_raw_data(limit=10_000)
    if raw.empty:
        logger.warning("No data found. Run data/data_generator.py first.")
    else:
        pipeline = build_feature_pipeline(scale=True)
        pipeline.fit(raw)
        features = pipeline.transform(raw)
        cols = get_numeric_feature_cols(features)
        logger.success(f"Feature matrix: {features[cols].shape} ({len(cols)} model features)")
