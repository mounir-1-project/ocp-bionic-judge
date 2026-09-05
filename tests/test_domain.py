"""
Tests de la couche domaine — le referentiel metier doit etre coherent.

Une erreur ici se propage silencieusement a tout le systeme.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import pytest


def test_equipement_correspond_a_la_fiche_ocp(domain):
    """L'identite de l'equipement doit correspondre a la fiche OCP."""
    e = domain.equipment
    assert e["id"] == "S-PC-E7301"
    assert e["code"] == "E7301"
    assert e["fabricant"] == "CHEMETICS"
    assert e["atelier"] == "PS III"
    assert e["materiau_tubes"] == "904L"


VALID_BASES = {"isa_5_1", "process", "data", "stoichio", "climatology"}


def test_chaque_tag_declare_son_sens(domain):
    """Chaque tag doit avoir une explication de son sens."""
    for tag in domain.tags.values():
        assert tag.rationale, f"{tag.tag} n'a aucune preuve"
        bases = set(tag.confidence.split(","))
        assert bases <= VALID_BASES, f"{tag.tag} : base inconnue {bases - VALID_BASES}"
        assert len(bases) >= 2, (
            f"{tag.tag} ne repose que sur {bases} — une base unique ne suffit pas"
        )


def test_les_tags_du_perimetre_reposent_sur_la_physique(domain):
    """Les six tags qui fondent un diagnostic exigent la base la plus forte."""
    for tag in domain.monitored_tags:
        assert "process" in tag.confidence, (
            f"{tag.alias} fonde un diagnostic sans ancrage procede"
        )


def test_la_base_de_determination_est_publiee(domain):
    """Un lecteur doit pouvoir contester une determination precise."""
    report = domain.determination_basis()
    assert report["n_total"] == 12
    assert set(report["par_base"]) <= VALID_BASES
    assert len(report["detail"]) == 12
    assert all(d["n_basis"] >= 2 for d in report["detail"])


def test_la_temperature_d_eau_de_mer_est_declaree(domain):
    """Le fluide froid n'est pas instrumente : sa source doit etre tracee."""
    external = domain._tags_doc.get("external_inputs", {})
    assert "T_SEAWATER" in external
    seawater = external["T_SEAWATER"]
    assert seawater["basis"] == ["climatology"]
    assert "Safi" in seawater["source"]


def test_alias_uniques(domain):
    """Deux tags ne peuvent pas partager le meme alias."""
    aliases = [t.alias for t in domain.tags.values()]
    assert len(aliases) == len(set(aliases))


def test_seuils_ordonnes(domain):
    """Les seuils doivent respecter LL < L < H < HH."""
    for tag in domain.tags.values():
        ll, lo = tag.threshold("alarm_low_low"), tag.threshold("alarm_low")
        hi, hh = tag.threshold("alarm_high"), tag.threshold("alarm_high_high")
        if ll is not None and lo is not None:
            assert ll < lo, f"{tag.alias}: LL >= L"
        if hi is not None and hh is not None:
            assert hi < hh, f"{tag.alias}: H >= HH"


def test_modes_amdec_cotations(domain):
    """Les modes AMDEC doivent avoir des cotation valides."""
    for mode in domain.modes.values():
        assert 1 <= mode.F <= 10
        assert 1 <= mode.G <= 10
        assert 1 <= mode.N <= 10
        assert mode.C == mode.F * mode.G * mode.N


def test_modes_observabilite_valide(domain):
    """L'observabilite doit etre full, partial ou none."""
    for mode in domain.modes.values():
        assert mode.observabilite in ("full", "partial", "none")


def test_maintenance_task_refs_valides(domain):
    """Les references de taches doivent exister dans le plan de maintenance."""
    for mode in domain.modes.values():
        for ref in mode.plan_maintenance_ref:
            assert ref in domain.plan_maintenance, (
                f"{mode.code} reference la tache {ref} absente du plan"
            )


def test_blind_spots_sont_none(domain):
    """Les angles morts ne doivent pas etre observables."""
    for mode in domain.blind_spots():
        assert mode.observabilite == "none"


def test_risk_coverage_couvert_plus_que_zero(domain):
    """La couverture du risque doit etre > 0."""
    coverage = domain.risk_coverage()
    assert coverage["criticite_couverte"] > 0
    assert coverage["part_couverte_pct"] > 0
