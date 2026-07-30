"""
Coherence de la topologie physique.

La topologie relie les codes emis par le detecteur aux pieces reelles de
l'equipement. Avant son introduction, ce rattachement etait improvise cote
interface par recherche de sous-chaine : un code comme `CONC_DROP_SEVERE`,
signature d'une fuite de tube, ne designait aucune piece.

Ces tests verrouillent trois proprietes :
  - tout ce que la topologie cite existe reellement (tag, mode, piece) ;
  - le rattachement d'une anomalie a une piece est correct pour les cas qui
    comptent, en particulier la fuite de tube et la perte de regulation ;
  - un code inconnu ne designe rien, plutot que de designer au hasard.
"""

from __future__ import annotations

import pytest

from src.domain.knowledge import load_domain


@pytest.fixture(scope="module")
def domain():
    return load_domain()


def test_chaque_capteur_situe_existe_dans_le_registre(domain):
    for alias, placement in domain.sensor_placements.items():
        assert alias in domain.by_alias, f"capteur '{alias}' absent de tags.yaml"
        assert len(placement["at"]) == 3, f"'{alias}' sans position 3D"
        assert placement["attaches_to"] in domain.components


def test_les_douze_tags_dcs_sont_tous_situes(domain):
    """Aucun capteur ne doit rester invisible dans la representation."""
    assert set(domain.sensor_placements) == {t.alias for t in domain.tags.values()}


def test_chaque_piece_cite_des_modes_amdec_existants(domain):
    for code, spec in domain.components.items():
        for mode in spec.get("amdec_modes") or []:
            assert mode in domain.modes, f"'{code}' cite un mode inconnu '{mode}'"


def test_le_rattachement_des_codes_ne_cite_rien_d_inconnu(domain):
    for code, entry in domain.finding_map.items():
        for component in entry.get("components") or []:
            assert component in domain.components, f"{code} -> piece '{component}'"
        for sensor in entry.get("sensors") or []:
            assert sensor in domain.by_alias, f"{code} -> capteur '{sensor}'"


def test_une_chute_de_titre_designe_le_faisceau_et_les_plaques(domain):
    """Le mode le plus grave doit designer les pieces qui le portent.

    Une chute brutale de titre signale de l'eau de mer dans l'acide, donc une
    fuite de tube. C'est le faisceau et les plaques tubulaires qui sont en
    cause, et ce sont les deux analyseurs qui la revelent.
    """
    located = domain.locate_finding("CONC_DROP_SEVERE")
    assert set(located["components"]) == {"BUNDLE", "TUBESHEET"}
    assert set(located["sensors"]) == {"C_ACID_1100", "C_ACID_1200"}


def test_une_perte_de_regulation_designe_la_sortie_acide(domain):
    located = domain.locate_finding("CONTROL_LOSS_CRITICAL")
    assert "BUNDLE" in located["components"]
    assert located["sensors"] == ["T_ACID_OUT"]


def test_un_code_inconnu_ne_designe_aucune_piece(domain):
    """Mieux vaut ne rien allumer que d'accuser la mauvaise piece."""
    assert domain.locate_finding("CODE_QUI_NEXISTE_PAS") == {
        "components": [], "sensors": []
    }


def test_tous_les_codes_du_detecteur_sont_couverts(domain):
    """Un code emis sans entree dans la table passerait inapercu."""
    import re
    from pathlib import Path

    source = Path("src/models/detector.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r'code="([A-Z_]+)"', source))
    manquants = emitted - set(domain.finding_map)
    assert not manquants, f"codes sans rattachement declare : {sorted(manquants)}"


def test_les_pieces_non_instrumentees_sont_declarees(domain):
    """Les angles morts doivent etre visibles dans la topologie.

    L'anode sacrificielle porte la criticite 112, la plus elevee de
    l'equipement, et aucun capteur ne la couvre. La representation doit le
    dire, pas le taire.
    """
    anode = domain.components["ANODE"]
    assert anode["instrumented"] is False
    assert "PLAQUE_SACRIFICIELLE_DYSFONCTION" in anode["amdec_modes"]
    assert domain.modes["PLAQUE_SACRIFICIELLE_DYSFONCTION"].C == 112


def test_la_topologie_exposee_est_complete(domain):
    payload = domain.topology()
    assert len(payload["sensors"]) == 12
    assert len(payload["components"]) == len(domain.components)
    bundle = next(c for c in payload["components"] if c["code"] == "BUNDLE")
    assert bundle["criticite_max"] == 105
    assert payload["meta"]["validation_status"] == "derived_from_equipment_sheet"
