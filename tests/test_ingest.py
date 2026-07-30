"""
Tests de l'ingestion DCS — la qualite de donnee est une information.

Ces tests verifient que le pipeline detecte les defauts REELS presents dans
DATA.xlsx, et surtout qu'il ne les invente pas la ou il n'y en a pas.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.ingest.dcs_loader import (
    FROZEN_MIN_HOURS,
    _detect_frozen,
    classify_process_state,
)

# ── Detection de gel ──────────────────────────────────────────────────────────

def test_gel_detecte_sur_signal_constant():
    """Un signal constant est declare fige, mais seulement une fois etabli.

    CE TEST AFFIRMAIT LE CONTRAIRE DU COMPORTEMENT VOULU. Il exigeait que
    TOUS les points d'un palier constant soient marques, y compris les
    premieres heures — c'est-a-dire un marquage retroactif, decide avec une
    information que le systeme n'a pas encore au moment ou il passe. La
    detection a ete rendue causale a dessein : un point n'est declare fige
    qu'a partir du moment ou la duree ecoulee depuis le debut du palier
    atteint le seuil. Le test verifie desormais cette causalite, qui est la
    propriete qui compte : rien avant le seuil, tout apres.
    """
    s = pd.Series([10.0] * 20, index=pd.date_range("2024-01-01", periods=20, freq="h"))
    gel = _detect_frozen(s)
    assert not gel.iloc[: FROZEN_MIN_HOURS - 1].any(), (
        "aucun point ne peut etre declare fige avant que le palier soit etabli"
    )
    assert gel.iloc[FROZEN_MIN_HOURS - 1:].all(), (
        "une fois le seuil atteint, chaque point du palier est fige"
    )


def test_signal_variable_non_marque():
    """Un signal qui bouge normalement ne doit jamais etre marque fige."""
    rng = np.random.default_rng(0)
    s = pd.Series(50 + rng.normal(0, 1, 200),
                  index=pd.date_range("2024-01-01", periods=200, freq="h"))
    assert not _detect_frozen(s).any()


def test_gel_ignore_pendant_un_arret():
    """Un signal a zero pendant un arret n'est pas un capteur mort.

    C'est le faux positif le plus couteux : sans cette regle, chaque arret de
    ligne genererait des centaines d'alertes instrumentation et le systeme
    serait desactive en salle de controle.
    """
    idx = pd.date_range("2024-01-01", periods=48, freq="h")
    s = pd.Series([0.0] * 48, index=idx)
    eligible = pd.Series(False, index=idx)   # ligne a l'arret
    assert not _detect_frozen(s, eligible=eligible).any()


def test_gel_partiel_compte_seulement_les_heures_en_marche():
    """Un palier majoritairement a l'arret ne doit pas declencher un gel."""
    idx = pd.date_range("2024-01-01", periods=30, freq="h")
    s = pd.Series([5.0] * 30, index=idx)
    eligible = pd.Series([False] * 27 + [True] * 3, index=idx)
    assert not _detect_frozen(s, eligible=eligible).any()


# ── Etat process ──────────────────────────────────────────────────────────────

def test_etat_marche_sur_donnees_nominales(synthetic_readings, domain):
    """Des conditions nominales doivent donner l'etat RUNNING."""
    state = classify_process_state(synthetic_readings, domain)
    assert (state == "RUNNING").mean() > 0.9


def test_arret_detecte_sur_charge_nulle(synthetic_readings, domain):
    """Une charge soufre nulle doit produire l'etat STOPPED."""
    df = synthetic_readings.copy()
    df.loc[df.index[100:150], "LOAD_SULFUR"] = 0.0
    state = classify_process_state(df, domain)
    assert (state.iloc[110:140] == "STOPPED").all()


def test_transitoire_autour_dun_arret(synthetic_readings, domain):
    """Les instants encadrant un arret doivent etre marques TRANSIENT."""
    df = synthetic_readings.copy()
    df.loc[df.index[100:150], "LOAD_SULFUR"] = 0.0
    state = classify_process_state(df, domain)
    assert "TRANSIENT" in set(state.iloc[95:105]) | set(state.iloc[148:158])


# ── Ingestion reelle ──────────────────────────────────────────────────────────

def test_perimetre_temporel(ingestion):
    """La periode chargee doit couvrir l'export fourni."""
    r = ingestion.report
    assert r["n_rows"] > 10000
    assert r["t_start"].startswith("2024-01-01")
    assert r["t_end"].startswith("2025-02-28")


def test_doublons_horodatage_supprimes(ingestion):
    """Aucun horodatage ne doit apparaitre deux fois apres ingestion."""
    assert not ingestion.readings.index.duplicated().any()
    assert ingestion.report["n_duplicates"] == 2
    duplicate_events = ingestion.quality[
        ingestion.quality["issue"] == "DUPLICATE_TIMESTAMP"
    ]
    assert len(duplicate_events) == 2
    assert "ordre source" in ingestion.report["duplicate_resolution"]


def test_codes_qualite_dcs_captures(ingestion):
    """Les codes 'Bad' / 'Configure' / 'I/O Timeout' doivent etre releves."""
    q = ingestion.quality
    codes = set(q[q["issue"] == "QUALITY_CODE"]["detail"].unique())
    assert {"Bad", "Configure", "I/O Timeout"} <= codes


def test_capteur_sature_identifie(ingestion):
    """TI5303-4X est sature a 327.67 depuis aout 2024 — cas avere."""
    sat = ingestion.quality[
        (ingestion.quality["alias"] == "TI_5303")
        & (ingestion.quality["issue"] == "SATURATED")
    ]
    assert len(sat) > 4000, "La saturation de TI5303-4X n'est pas detectee"


def test_capteur_fige_identifie(ingestion):
    """PHI5306X-3 est fige a -14.407 sur les premiers mois — cas avere."""
    frozen = ingestion.quality[
        (ingestion.quality["alias"] == "PHI_5306")
        & (ingestion.quality["issue"] == "FROZEN")
    ]
    assert len(frozen) > 500


def test_capteurs_degrades_absents_des_lectures(ingestion):
    """Les capteurs hors perimetre ne doivent pas polluer la table de lecture."""
    assert "TI_5303" not in ingestion.readings.columns
    assert "PHI_5306" not in ingestion.readings.columns


def test_valeurs_invalides_mises_a_nan_et_non_inventees(ingestion):
    """Une valeur invalide doit devenir NaN, jamais etre remplacee.

    Combler un trou par la derniere valeur connue ferait croire au modele que
    la mesure existe. C'est ainsi qu'un systeme declare 'tout va bien' pendant
    sept mois de capteur mort.
    """
    df = ingestion.readings
    assert df.isna().any().any(), "Aucune valeur manquante : les trous ont ete combles"
    assert ingestion.report["imputation_policy"].startswith("Aucune imputation")


def test_trous_ordre_et_absences_sont_audites(ingestion):
    issues = set(ingestion.quality["issue"])
    assert "TIME_GAP" in issues
    assert ingestion.report["n_out_of_order"] >= 0
    assert ingestion.report["unit_control"]


def test_disponibilite_des_capteurs_du_perimetre(ingestion):
    """Les capteurs surveilles doivent rester majoritairement disponibles."""
    h = ingestion.sensor_health
    scope = h[h["role"].isin(["primary", "secondary"])]
    assert (scope["availability_pct"] > 90).all()
    assert (scope["availability_pct"] <= 100).all()


def test_etats_process_tous_presents(ingestion):
    """Les trois etats doivent apparaitre sur 14 mois d'exploitation."""
    counts = ingestion.report["state_counts"]
    assert set(counts) == {"RUNNING", "STOPPED", "TRANSIENT"}
    assert counts["RUNNING"] > 8000


def test_fichier_absent_leve_une_erreur():
    """Un chemin invalide doit echouer explicitement."""
    from src.ingest.dcs_loader import ingest

    with pytest.raises(FileNotFoundError):
        ingest("/chemin/inexistant/DATA.xlsx")
