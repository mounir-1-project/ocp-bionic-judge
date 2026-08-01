"""
Fixtures partagees pour la suite de tests E7301.

La chaine complete est construite UNE fois par session : l'ingestion et
l'entrainement prennent quelques secondes, les refaire a chaque test rendrait
la suite inutilisable et decouragerait de la lancer.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

# La suite teste séparément l'authentification et conserve le client API
# général en mode local pour éviter de masquer les contrats métier.
os.environ.setdefault("AUTH_ENABLED", "false")

# LA SUITE DECRIT UN ETAT, PAS LA MACHINE QUI LA FAIT TOURNER.
#
# `test_acces_local_et_notifications_desactivees` affirme qu'aucun courriel ne
# part sans relais SMTP, et l'ecrit `enabled is False`. Or `EmailNotifier.enabled`
# devient vrai des que `.env` porte un relais ET un destinataire — c'est-a-dire
# sur toute machine CORRECTEMENT CONFIGUREE, celle que le runbook decrit. Le
# test passait en integration continue, qui part d'un depot vierge sans `.env`,
# et echouait sur le poste de l'exploitant.
#
# C'est exactement le piege que `scripts/dump_fixtures.py` documente pour
# `AUTH_ENABLED` : « le defaut ne se voyait que la ou un registre existe ; ni en
# integration continue, ni dans l'environnement d'audit ». La meme cause, sur
# une autre variable.
#
# `setdefault` ne suffit pas ici : `load_dotenv()` n'ecrase pas une variable
# deja posee, mais ces deux-la ne sont pas posees — elles viennent du fichier.
# On les neutralise donc explicitement pour la duree de la suite. Les tests qui
# ont besoin d'un canal actif construisent leur propre `EmailNotifier` avec un
# hote explicite, et ne dependent pas de cette valeur.
os.environ["SMTP_HOST"] = ""
os.environ["ALERT_EMAIL_TO"] = ""

from src.config import DCS_EXPORT
from src.domain.knowledge import load_domain
from src.ingest.dcs_loader import ingest

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
    from src.features.e7301_features import build_features

    feats, twin = build_features(ingestion.readings, ingestion.quality, domain)
    return feats, twin


@pytest.fixture(scope="session")
def pipeline():
    """Chaine complete, sans LLM (deterministe et hors ligne)."""
    if not DATA_PATH.exists():
        pytest.skip(f"Donnees DCS absentes: {DATA_PATH}")
    from src.pipeline import E7301Pipeline

    return E7301Pipeline(data_path=DATA_PATH, use_llm=False)


@pytest.fixture(scope="session")
def sensitivity_report(pipeline):
    """Analyse de sensibilite, calculee UNE fois pour toute la session.

    Ce rapport reconstruit les features pour quatre periodes de reference : il
    coute a lui seul plusieurs dizaines de secondes. Deux fichiers de tests en
    ont besoin — celui qui verifie son contenu et celui qui verifie sa
    typographie. Le recalculer deux fois doublait la duree de la suite, et une
    suite lente finit par ne plus etre lancee.
    """
    from src.governance.sensitivity import full_report

    return full_report(pipeline)


@pytest.fixture(scope="session")
def fouling_bench_report(pipeline):
    """Banc d'injection, calcule UNE fois pour toute la session."""
    from src.governance.fouling_injection import FoulingInjectionBench

    return FoulingInjectionBench(pipeline).run(
        severities=(0.10, 0.30), durations_days=(60,)
    )


@pytest.fixture
def synthetic_readings(domain):
    """Petit jeu synthetique controle, pour tester des cas limites.

    Utilise uniquement la ou une donnee reelle ne permet pas d'isoler un
    comportement precis (arret, gel de signal, chute de titre).
    """
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

    from src.ingest.dcs_loader import classify_process_state

    df["process_state"] = classify_process_state(df, domain)
    return df
