"""
Fixtures partagees pour la suite de tests E7301.

La chaine complete est construite UNE fois par session.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.config import DCS_EXPORT
from core.knowledge.knowledge import load_domain
from core.ingestion.dcs_loader import ingest

DATA_PATH = DCS_EXPORT


@pytest.fixture(scope="session")
def domain():
    """Connaissance domaine chargee depuis les YAML."""
    return load_domain()


@pytest.fixture(scope="session")
def ingestion(domain):
    """Resultat d'ingestion des donnees DCS reelles."""
    if not DATA_PATH.exists():
        pytest.skip(f"Donnees DCS absentes: {DATA_PATH}")
    return ingest(DATA_PATH, domain)


@pytest.fixture(scope="session")
def features(ingestion, domain):
    """Table de features et jumeau thermique ajuste."""
    from core.features.e7301_features import build_features

    feats, twin = build_features(ingestion.readings, ingestion.quality, domain)
    return feats, twin


@pytest.fixture(scope="session")
def pipeline():
    """Chaine complete, mode deterministe."""
    if not DATA_PATH.exists():
        pytest.skip(f"Donnees DCS absentes: {DATA_PATH}")
    from core.pipeline import E7301Pipeline

    return E7301Pipeline(data_path=DATA_PATH)


@pytest.fixture
def synthetic_readings(domain):
    """Petit jeu synthetique controle, pour tester des cas limites."""
    idx = pd.date_range("2024-06-01", periods=400, freq="h")
    rng = np.random.default_rng(7)
    df = pd.DataFrame(index=idx)
    df.index.name = "timestamp"
    df["LOAD_SULFUR"] = 18.5 + rng.normal(0, 0.2, len(idx))
    df["F_ACID"] = 56.0 + rng.normal(0, 1.0, len(idx))
    df["T_ACID_IN"] = 94.0 + rng.normal(0, 0.5, len(idx))
    df["T_ACID_OUT"] = 66.0 + rng.normal(0, 0.3, len(idx))
    df["C_ACID_1100"] = 98.70 + rng.normal(0, 0.03, len(idx))
    df["C_ACID_1200"] = 98.57 + rng.normal(0, 0.03, len(idx))
    df["T_CIRC_1300"] = 43.0 + rng.normal(0, 0.5, len(idx))
    df["F_3412"] = 2000.0 + rng.normal(0, 20, len(idx))
    df["A_3301"] = 7.9 + rng.normal(0, 0.05, len(idx))
    df["A_3302"] = 7.4 + rng.normal(0, 0.05, len(idx))

    from core.ingestion.dcs_loader import classify_process_state

    df["process_state"] = classify_process_state(df, domain)
    return df
