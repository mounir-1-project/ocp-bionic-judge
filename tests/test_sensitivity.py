"""
Sensibilite aux parametres arbitraires.

Deux choix decident de presque tout le comportement du systeme, et aucun n'a
de justification physique : la contamination du detecteur et la periode de
reference. Un parametre arbitraire n'est pas une faute; un parametre arbitraire
dont on ignore l'influence en est une.

Ces tests verrouillent la publication de cette influence.
"""

from __future__ import annotations

import pytest

from src.governance.sensitivity import (
    contamination_sensitivity,
    reference_period_sensitivity,
)
from tests.helpers import sans_accents


@pytest.fixture(scope="module")
def report(sensitivity_report):
    """Le rapport est calcule une fois par session, pas par module."""
    return sensitivity_report


def test_les_parametres_arbitraires_sont_declares(report):
    """Le systeme doit nommer ce qu'il choisit sans justification."""
    noms = {p["nom"] for p in report["parametres_arbitraires"]}
    assert noms == {"contamination", "periode_de_reference"}
    for p in report["parametres_arbitraires"]:
        assert p["justification"]


def test_la_contamination_pilote_bien_le_volume(report):
    """Propriete attendue : plus de contamination, plus d'heures signalees."""
    grid = report["contamination"]["grid"]
    assert len(grid) >= 4
    taux = [g["taux_signalement_pct"] for g in grid]
    assert taux == sorted(taux), "le taux doit croitre avec la contamination"


def test_le_taux_reel_depasse_la_cible_de_facon_stable(report):
    """Le facteur de depassement doit etre publie, et rester stable.

    Il vaut environ 2,7 sur ce corpus : le seuil est appris sur la periode de
    reference puis applique a une periode qui a change de regime. C'est
    exploitable — on regle la contamination en consequence — mais cela doit
    etre dit, sinon `contamination = 2 %` se lit comme « 2 % d'alertes ».
    """
    contamination = report["contamination"]
    assert contamination["ratio_moyen"] > 1.5
    assert contamination["ratio_dispersion"] < 2.0, (
        "un facteur instable rendrait la contamination inutilisable comme levier"
    )
    assert "0,7" in contamination["reading"] or "levier" in contamination["reading"]


def test_la_periode_de_reference_change_la_conclusion(report):
    """LE RESULTAT LE PLUS IMPORTANT.

    La part du temps declaree en derive varie de plusieurs dizaines de points
    selon la seule fenetre de reference.

    CE QUE LA LECTURE DOIT DIRE — ET CE QU'ELLE NE DOIT PLUS DIRE.
    Une version precedente concluait « tant que la date de revision reelle
    n'est pas communiquee par OCP, aucun chiffre de derive ne doit etre
    presente ». C'est une abstention, pas une conclusion : elle suspend le
    resultat a une information que ce travail n'obtiendra pas.

    La lecture attendue publie TOUTE la grille et retient ce qui y survit.
    Ce test verrouille les deux exigences.
    """
    periode = report["periode_reference"]
    assert len(periode["grid"]) >= 3
    assert periode["sensible"] is True
    assert periode["dispersion_part_derive_pct"] > 15.0

    lecture = sans_accents(periode["reading"])
    # La dispersion doit etre annoncee, pas noyee.
    assert "varie de" in lecture
    # Et une conclusion doit etre tiree malgre elle.
    #
    # LE TEST VERROUILLAIT DEUX FORMES VERBALES, PAS UNE PROPRIETE. Il exigeait
    # litteralement « survit » ou « retient ». La lecture a ete reecrite et dit
    # desormais « il faut retenir » puis « la fenetre de 40 % est retenue parce
    # que » : la conclusion est la, plus explicite qu'avant, et le test tombait
    # sur une conjugaison. On verifie donc la famille lexicale, et surtout —
    # ci-dessous — qu'aucune abstention ne subsiste : c'est cette seconde
    # assertion qui porte l'exigence de fond.
    assert any(marque in lecture for marque in ("surviv", "reten", "retient")), (
        "la lecture ne tire aucune conclusion de la grille"
    )
    # Aucune abstention suspendue a une information indisponible.
    for renoncement in ("communiquee par ocp", "tant que la date",
                        "aucun chiffre de derive ne doit"):
        assert renoncement not in lecture, (
            f"la lecture suspend sa conclusion : « {renoncement} »"
        )


def test_une_reference_plus_tardive_normalise_la_derive(report):
    """Mecanisme attendu : integrer le changement de regime le banalise."""
    grid = sorted(report["periode_reference"]["grid"], key=lambda g: g["fraction_reference"])
    assert grid[0]["part_derive_pct"] > grid[-1]["part_derive_pct"], (
        "une reference tardive doit englober la bascule et reduire la derive vue"
    )


def test_le_rapport_est_serialisable(report):
    """L'API doit pouvoir le renvoyer sans conversion manuelle.

    LE TEST NE VERIFIAIT PAS CE QU'IL ANNONCAIT. Il appelait `json.dumps` sans
    rien affirmer : un rapport reduit a `{}` — cle disparue, calcul court-
    circuite — passait sans un mot, alors que l'endpoint aurait renvoye une
    reponse vide. Serialisable et non vide sont deux proprietes distinctes;
    seule la premiere etait couverte, et elle l'etait par accident.
    """
    import json

    brut = json.dumps(report)
    relu = json.loads(brut)
    assert relu == report, "la serialisation altere le rapport"
    assert isinstance(relu, dict) and relu, "rapport de sensibilite vide"
    assert {"contamination", "periode_reference"} <= set(relu), (
        f"les deux parametres arbitraires ne sont plus publies : {sorted(relu)}"
    )


def test_analyse_de_contamination_isolee(features):
    """La fonction doit rester utilisable hors pipeline complet."""
    feats, refs = features
    out = contamination_sensitivity(
        feats, refs.effort.train_period[1], grid=(0.01, 0.05)
    )
    assert len(out["grid"]) == 2
    assert out["valeur_retenue"] == 0.02


def test_analyse_de_periode_isolee(ingestion, domain):
    """Idem pour la periode de reference."""
    out = reference_period_sensitivity(
        ingestion.readings, ingestion.quality, domain, fractions=(0.40, 0.60)
    )
    assert 1 <= len(out["grid"]) <= 2
