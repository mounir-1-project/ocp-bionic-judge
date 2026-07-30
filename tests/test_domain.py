"""
Tests de la couche domaine — le referentiel metier doit etre coherent.

Une erreur ici se propage silencieusement a tout le systeme : un seuil mal
saisi produit des alertes fausses sans qu'aucun test aval ne s'en apercoive.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import pytest


def test_equipement_correspond_a_la_fiche_ocp(domain):
    """L'identite de l'equipement doit correspondre a la fiche OCP fournie."""
    e = domain.equipment
    assert e["id"] == "S-PC-E7301"
    assert e["code"] == "E7301"
    assert e["fabricant"] == "CHEMETICS"
    assert e["atelier"] == "PS III"
    assert e["materiau_tubes"] == "904L"


VALID_BASES = {"isa_5_1", "process", "data", "stoichio", "climatology"}


def test_chaque_tag_declare_sur_quoi_repose_son_sens(domain):
    """Aucune fiche d'instrumentation n'accompagne l'export DCS.

    Le sens des douze tags a donc ete etabli par recoupement. Ce test exige que
    chaque determination cite AU MOINS DEUX bases independantes et porte la
    preuve correspondante : sans cela, 'TI1100 = entree acide' resterait une
    supposition invérifiable.
    """
    for tag in domain.tags.values():
        assert tag.rationale, f"{tag.tag} n'a aucune preuve"
        bases = set(tag.confidence.split(","))
        assert bases <= VALID_BASES, f"{tag.tag} : base inconnue {bases - VALID_BASES}"
        assert len(bases) >= 2, (
            f"{tag.tag} ne repose que sur {bases} — une base unique ne suffit pas"
        )
        governance = tag.governance
        assert governance["source_file"] == "DATA.xlsx"
        assert governance["source_location"]
        assert governance["source_sha256"]
        assert governance["sampling_frequency"]
        assert governance["business_owner"]
        assert governance["quality_rules"]


def test_les_tags_du_perimetre_reposent_sur_la_physique(domain):
    """Les six tags qui fondent un diagnostic exigent la base la plus forte.

    Un tag de contexte peut se contenter de la nomenclature et du comportement
    observe. Un tag qui declenche une intervention doit en plus etre coherent
    avec la physique du procede sulfurique.
    """
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
    assert "recoupement" in report["methode"]


def test_la_temperature_d_eau_de_mer_est_declaree_comme_entree_externe(domain):
    """Le fluide froid n'est pas instrumente : sa source doit etre tracee."""
    external = domain._tags_doc.get("external_inputs", {})
    assert "T_SEAWATER" in external
    seawater = external["T_SEAWATER"]
    assert seawater["basis"] == ["climatology"]
    assert "Safi" in seawater["source"]
    assert seawater["range_operating"] == [17.0, 22.0]
    assert seawater["evidence"]


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
        if lo is not None and hi is not None:
            assert lo < hi, f"{tag.alias}: L >= H"


def test_plage_operationnelle_incluse_dans_plage_physique(domain):
    """La plage normale ne peut pas sortir de la plage physiquement possible."""
    for tag in domain.tags.values():
        op, ph = tag.range_operating, tag.range_physical
        if op and ph:
            assert ph[0] <= op[0] and op[1] <= ph[1], f"{tag.alias}: plages incoherentes"


def test_criticite_amdec_est_le_produit_fgn(domain):
    """C doit valoir exactement F x G x N — controle de saisie de l'AMDEC."""
    for m in domain.modes.values():
        assert m.C == m.F * m.G * m.N, (
            f"{m.code}: C={m.C} mais F*G*N={m.F * m.G * m.N}"
        )


def test_cotations_dans_les_baremes(domain):
    """Les cotations doivent rester dans les baremes de 1 a 10."""
    for m in domain.modes.values():
        assert 1 <= m.F <= 10 and 1 <= m.G <= 10 and 1 <= m.N <= 10, m.code


def test_taches_preventives_referencees_existent(domain):
    """Toute tache citee par un mode AMDEC doit exister dans le plan."""
    for m in domain.modes.values():
        for ref in m.plan_maintenance_ref:
            assert ref in domain.plan_maintenance, f"{m.code} reference la tache inconnue {ref}"


def test_angles_morts_declares(domain):
    """Le systeme doit declarer explicitement ce qu'il ne peut pas detecter."""
    blind = {m.code for m in domain.blind_spots()}
    assert "PLAQUE_SACRIFICIELLE_DYSFONCTION" in blind, (
        "L'anode sacrificielle n'est pas instrumentee : la declarer detectable "
        "donnerait une fausse assurance sur un composant de criticite 112."
    )
    for m in domain.blind_spots():
        assert m.plan_maintenance_ref, (
            f"{m.code} est un angle mort SANS couverture preventive : "
            f"ni la surveillance ni le preventif ne le couvrent."
        )


def test_capteurs_degrades_exclus_du_modele(domain):
    """Les capteurs averes defaillants ne doivent pas alimenter le modele."""
    model_tags = {t.tag for t in domain.model_tags}
    assert "S_MC_SULF_TI5303-4X_B" not in model_tags
    assert "S_MC_SULF_PHI5306X-3_B" not in model_tags


def test_modes_observables_ont_des_indicateurs(domain):
    """Un mode declare detectable doit dire par quel indicateur il l'est."""
    for m in domain.observable_modes():
        assert m.indicators, f"{m.code} est declare observable sans indicateur"


def test_briefings_non_vides(domain):
    """Les briefings injectes dans les prompts doivent etre exploitables."""
    assert "E7301" in domain.briefing_equipment()
    assert "T_ACID_IN" in domain.briefing_tags()
    assert "FAISCEAU" in domain.briefing_amdec()
    assert "PLAQUE_SACRIFICIELLE" in domain.briefing_blind_spots()


def test_provenance_amdec_source_et_enrichissements_separes(domain):
    """Une règle applicative ne doit jamais être présentée comme une ligne OCP."""
    allowed = {
        "ocp_source", "derived_rule", "application_rule",
        "hypothesis", "field_validated",
    }
    for mode in domain.modes.values():
        assert mode.provenance_category in allowed
        assert mode.source_file
        assert mode.source_location
        assert mode.transformations
        assert mode.validation_status
        assert mode.validation_owner

    sensor = domain.modes["CAPTEUR_DEFAILLANT"]
    assert sensor.provenance_category == "application_rule"
    assert sensor.original_values == {"F": None, "G": None, "N": None, "C": None}
    assert sensor.validation_status == "hypothesis"
    assert domain.modes["PLAQUE_SACRIFICIELLE_DYSFONCTION"].provenance_category == (
        "ocp_source"
    )


def test_cotations_officielles_conservent_les_valeurs_originales(domain):
    for mode in domain.modes.values():
        if mode.provenance_category != "ocp_source":
            continue
        original = mode.original_values
        assert (
            original["F"], original["G"], original["N"], original["C"]
        ) == (mode.F, mode.G, mode.N, mode.C)


def test_tag_inconnu_leve_une_erreur(domain):
    """Demander un tag inexistant doit echouer clairement."""
    with pytest.raises(KeyError):
        domain.get("TAG_QUI_NEXISTE_PAS")
