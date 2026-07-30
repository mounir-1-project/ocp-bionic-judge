"""
Tests des agents et du Judge — le controle doit reellement mordre.

Ces tests sont le coeur de la garantie apportee par le projet. Chacun injecte
une faute precise dans une decision et verifie que le Judge la releve ET la
sanctionne. Un Judge qui passe ces tests ne peut pas se contenter de valider.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import contextlib
import copy

import pytest

from src.agents.schemas import AgentDecision, RecommendedAction
from src.governance.judge_eval import TRAP_CASES, JudgeEvaluator


@pytest.fixture(scope="module")
def case(pipeline):
    """Un instant reel degrade, sa decision saine et son verdict."""
    ts = pipeline.episodes().iloc[0]["peak_at"]
    detection = pipeline.detector.analyze(pipeline.features, ts)
    decision = pipeline.agent.analyze(detection)
    verdict = pipeline.judge.judge(decision, pipeline.features)
    return {"ts": ts, "detection": detection, "decision": decision, "verdict": verdict}


def _mutate(decision: AgentDecision, **kw) -> AgentDecision:
    """Copie une decision en surchargeant des champs.

    Args:
        decision: Decision d'origine.
        **kw: Champs a modifier.

    Returns:
        Nouvelle decision.
    """
    data = copy.deepcopy(decision.model_dump())
    data.update(kw)
    return AgentDecision(**data)


# ── Agent de detection ────────────────────────────────────────────────────────

def test_agent_fonctionne_sans_cle_api(pipeline):
    """Le systeme doit etre demontrable hors ligne, sans quota API."""
    assert pipeline.agent.mode == "rules"
    assert pipeline.judge.mode == "deterministic"


def test_agent_ouvre_un_coupe_circuit_apres_echec_llm(pipeline):
    """Un service LLM en panne ne doit pas ralentir chaque point du rejeu."""

    class BrokenLLM:
        def invoke(self, _messages):
            raise RuntimeError("service indisponible")

    pipeline.agent.llm = BrokenLLM()
    ts = pipeline.notable_timestamps(1)[0]
    detection = pipeline.detector.analyze(pipeline.features, ts)
    decision = pipeline.agent.analyze(detection)

    assert decision.generated_by == "rules"
    assert pipeline.agent.llm is None
    assert pipeline.agent.mode == "rules"


def test_decision_bien_formee(case):
    """La decision doit respecter le contrat de donnees."""
    d = case["decision"]
    assert d.severity in ("NORMAL", "INFO", "WARNING", "CRITICAL")
    assert 0.0 <= d.confidence <= 1.0
    assert d.diagnosis and d.recommended_action.description
    assert d.equipment_id == "S-PC-E7301"


def test_decision_cite_des_valeurs_verifiables(case):
    """Un diagnostic doit etre refutable, donc chiffre."""
    assert case["decision"].cited_values, "aucune valeur citee : diagnostic non verifiable"


def test_confiance_baisse_quand_les_preuves_faiblissent(pipeline):
    """La confiance doit reagir a la qualite des preuves, pas etre constante."""
    confs = []
    for ts in pipeline.notable_timestamps(15):
        det = pipeline.detector.analyze(pipeline.features, ts)
        confs.append(pipeline.agent.analyze(det).confidence)
    assert len(set(confs)) > 1, "confiance constante : elle n'est pas calibree"


def test_un_seul_bareme_de_confiance_existe(pipeline):
    """L'agent ANNONCE ce que le controleur VERIFIE, avec la meme fonction.

    `schemas.confiance_justifiable` affirmait que « deux baremes qui doivent
    coincider ne se recopient pas, ils se partagent » et que « toute divergence
    future devient impossible par construction ». C'etait faux :
    `_calibrate_confidence` reimplementait une formule differente — base 0,55
    contre 0,50, penalite binaire sur l'observabilite au lieu d'une graduation,
    corroboration creditee d'un cote seulement. Ecart mesure jusqu'a 0,25 point.
    """
    from src.agents.schemas import confiance_justifiable

    for ts in pipeline.notable_timestamps(15):
        detection = pipeline.detector.analyze(pipeline.features, ts)
        decision = pipeline.agent.analyze(detection)
        modes = [
            pipeline.domain.modes[m]
            for m in decision.amdec_modes
            if m in pipeline.domain.modes
        ]
        observabilite = min(
            (m.observabilite for m in modes),
            key=lambda o: {"none": 0, "partial": 1, "full": 2}[o],
            default="full",
        )
        attendu = confiance_justifiable(
            rule_codes=[f.code for f in detection.findings],
            model_applicable=bool(detection.data_quality.get("model_applicable")),
            n_invalid_tags=int(detection.data_quality.get("n_invalid_tags", 0)),
            process_state=detection.process_state,
            mode_observabilite=observabilite,
        )
        assert decision.confidence == attendu, (
            f"{ts} : l'agent annonce {decision.confidence}, le bareme partage "
            f"donne {attendu} — les deux formules ont diverge"
        )


def test_un_defaut_de_mesure_ne_domine_jamais_un_diagnostic_equipement(pipeline):
    """La chaine de mesure est une reserve, pas une conclusion sur l'appareil.

    La constatation dominante etait choisie par `max()` sur la seule severite,
    qui renvoie le premier element a egalite : l'ordre d'ecriture des regles
    decidait. `_rule_sensor_health` s'executant en tete, un SENSOR_FAULT
    l'emportait sur un CONC_DROP_SEVERE de meme severite — une suspicion de
    percement de tube reléguée derriere un analyseur qui derive.

    Trier sur la criticite AMDEC ne suffisait pas : CAPTEUR_DEFAILLANT porte
    108, cotation PROPOSEE par ce travail, contre 105 pour FAISCEAU_FUITE,
    ligne transcrite du document OCP de 2019.
    """
    domain = pipeline.domain
    instrumentation = {
        code
        for code, mode in domain.modes.items()
        if mode.raw.get("sous_equipement") == "INSTRUMENTATION"
    }
    assert instrumentation, "aucun mode d'instrumentation dans le referentiel"

    for ts in pipeline.notable_timestamps(20):
        detection = pipeline.detector.analyze(pipeline.features, ts)
        actionnables = [
            f for f in detection.findings if f.severity in ("WARNING", "CRITICAL")
        ]
        modes_equipement = {
            f.amdec_mode
            for f in actionnables
            if f.amdec_mode and f.amdec_mode not in instrumentation
        }
        if not modes_equipement:
            continue
        decision = pipeline.agent.analyze(detection)
        dominant = next(
            (f for f in actionnables if f.code in decision.evidence_refs
             and f.amdec_mode in decision.amdec_modes),
            None,
        )
        severites = {f.severity for f in actionnables}
        if dominant is not None and len(severites) == 1:
            assert dominant.amdec_mode not in instrumentation, (
                f"{ts} : un defaut de mesure ({dominant.code}) domine alors "
                f"qu'un diagnostic equipement de meme severite existe "
                f"({sorted(modes_equipement)})"
            )


def test_la_tache_preventive_citee_est_la_plus_frequente(pipeline):
    """Le plan preventif se cite par cadence, pas par ordre de saisie du YAML.

    `plan_maintenance_ref[0]` dependait de l'ordre d'ecriture du referentiel :
    pour CALANDRE_FUITE, refs ["A", "C"], la recommandation citait la mesure
    d'epaisseurs quadriennale plutot que l'inspection externe mensuelle. Une
    permutation des deux lettres aurait change la recommandation sans qu'aucun
    controle ne le voie.
    """
    composeur = pipeline.agent.composer
    for code, mode in pipeline.domain.modes.items():
        refs = mode.plan_maintenance_ref
        if len(refs) < 2:
            continue
        retenue = composeur._tache_la_plus_frequente(refs)
        cadences = {r: composeur._periodicite_heures(r) for r in refs}
        assert cadences[retenue] == min(cadences.values()), (
            f"{code} : tache {retenue} retenue alors que {cadences} "
            f"designe une cadence plus courte"
        )


def test_action_avec_arret_mentionne_la_consignation(pipeline):
    """Toute action exigeant un arret doit mentionner la consignation."""
    for ts in pipeline.notable_timestamps(20):
        det = pipeline.detector.analyze(pipeline.features, ts)
        d = pipeline.agent.analyze(det)
        if d.recommended_action.requires_shutdown:
            txt = d.recommended_action.description.lower()
            assert "consign" in txt or "arret" in txt


# ── Judge : cas sain ──────────────────────────────────────────────────────────

def test_judge_valide_une_decision_saine(case):
    """Une decision correcte ne doit pas etre rejetee."""
    v = case["verdict"]
    assert v.agreement
    assert v.global_score >= 6.0
    assert len(v.checks) == 8


def test_judge_recalcule_les_faits_lui_meme(case):
    """Le Judge doit disposer de faits reconstruits, pas des dires de l'agent."""
    vf = case["verdict"].verified_facts
    assert vf["timestamp"] == case["decision"].timestamp
    assert vf.get("measurements")
    assert "rule_severity" in vf


def test_judge_est_reproductible(pipeline, case):
    """Deux jugements de la meme decision doivent donner la meme note."""
    v2 = pipeline.judge.judge(case["decision"], pipeline.features)
    assert v2.global_score == case["verdict"].global_score
    assert v2.flagged_issues == case["verdict"].flagged_issues


def test_poids_des_controles_somment_a_un(pipeline):
    """La ponderation doit etre coherente, sinon la note perd son sens."""
    from src.agents.judge_agent import VerificationLayer

    assert sum(VerificationLayer.WEIGHTS.values()) == pytest.approx(1.0)


# ── Judge : detection des fautes ──────────────────────────────────────────────

def test_judge_detecte_une_valeur_inventee(pipeline, case):
    """Citer une mesure qui n'existe pas doit etre sanctionne severement."""
    bad = _mutate(
        case["decision"],
        cited_values={**case["decision"].cited_values, "T_ACID_OUT": 85.0},
        diagnosis="Temperature de sortie relevee a 85.0 degC, surchauffe caracterisee.",
    )
    v = pipeline.judge.judge(bad, pipeline.features)
    assert "HALLUCINATED_VALUE" in v.flagged_issues
    assert not v.agreement
    assert v.global_score <= 4.0


def test_judge_detecte_un_angle_mort_revendique(pipeline, case):
    """Pretendre detecter l'anode sacrificielle doit etre rejete."""
    bad = _mutate(case["decision"], amdec_modes=["PLAQUE_SACRIFICIELLE_DYSFONCTION"])
    v = pipeline.judge.judge(bad, pipeline.features)
    assert "BLIND_SPOT_CLAIM" in v.flagged_issues
    assert not v.agreement


def test_judge_detecte_un_mode_inexistant(pipeline, case):
    """Invoquer un mode absent de l'AMDEC doit etre rejete."""
    bad = _mutate(case["decision"], amdec_modes=["ROULEMENT_POMPE_USURE"])
    v = pipeline.judge.judge(bad, pipeline.features)
    assert "INVENTED_AMDEC_MODE" in v.flagged_issues
    assert not v.agreement


def test_une_action_en_marche_conforme_a_sa_tache_n_est_pas_sanctionnee(pipeline):
    """V4 juge la tache CITEE, pas toutes celles du mode.

    Le controle balayait toutes les taches de tous les modes invoques et
    concluait « arret requis » des qu'une seule l'exigeait. Pour CALANDRE_FUITE,
    refs ["A" (arret process, 4 ans), "C" (en marche, 1 mois)], une
    recommandation d'inspection externe mensuelle — realisable equipement en
    service, et correcte — etait sanctionnee UNSAFE_ACTION avec note plafonnee
    a 1/10 parce que la tache A du meme mode exige une consignation.
    """
    decision = None
    for ts in pipeline.notable_timestamps(25):
        detection = pipeline.detector.analyze(pipeline.features, ts)
        candidate = pipeline.agent.analyze(detection)
        if candidate.recommended_action.execution_window == "EN_MARCHE" and (
            candidate.recommended_action.maintenance_task_ref
        ):
            decision = candidate
            break
    if decision is None:
        pytest.skip("aucune action realisable en marche sur les instants notables")

    ref = decision.recommended_action.maintenance_task_ref
    assert not pipeline.domain.task_requires_shutdown(ref), (
        f"la tache {ref} citee exige un arret : le cas de test est invalide"
    )
    verdict = pipeline.judge.judge(decision, pipeline.features)
    assert "UNSAFE_ACTION" not in verdict.flagged_issues, (
        f"action conforme a la tache {ref} (realisable en marche) sanctionnee "
        f"UNSAFE_ACTION : {verdict.feedback}"
    )


def test_les_modes_de_performance_viennent_du_referentiel(pipeline):
    """L'ensemble utilise par V6 est derive de la topologie, pas ecrit en dur.

    Il figurait en litteral dans `_v6_state_awareness` : l'ajout d'un mode porte
    par le faisceau dans `amdec.yaml` ne l'aurait pas rejoint, et le controle
    aurait laisse passer un diagnostic de degradation formule a l'arret.
    """
    from src.agents.judge_agent import PERFORMANCE_COMPONENT

    modes = pipeline.domain.modes_for_component(PERFORMANCE_COMPONENT)
    assert modes, f"la piece {PERFORMANCE_COMPONENT} ne porte aucun mode"
    assert modes <= set(pipeline.domain.modes), "mode inconnu dans la topologie"
    assert "FAISCEAU_FUITE" in modes, (
        "la fuite de tube doit rester un mode de performance de l'echangeur"
    )


def test_judge_detecte_une_action_dangereuse(pipeline, case):
    """Prescrire une ouverture de PV en marche doit etre rejete."""
    bad = _mutate(
        case["decision"],
        severity="CRITICAL",
        amdec_modes=["FAISCEAU_BOUCHAGE"],
        recommended_action=RecommendedAction(
            description="Ouvrir les portes de visite et nettoyer les tubes sans delai.",
            urgency="IMMEDIATE", requires_shutdown=False, maintenance_task_ref="B",
        ).model_dump(),
    )
    v = pipeline.judge.judge(bad, pipeline.features)
    assert "UNSAFE_ACTION" in v.flagged_issues
    assert not v.agreement


def test_judge_detecte_une_action_sous_dimensionnee(pipeline, case):
    """Repondre a un CRITICAL par une surveillance hebdomadaire est une faute."""
    bad = _mutate(
        case["decision"],
        severity="CRITICAL",
        recommended_action=RecommendedAction(
            description="Surveiller lors de la prochaine ronde hebdomadaire.",
            urgency="SOUS_SURVEILLANCE",
        ).model_dump(),
    )
    v = pipeline.judge.judge(bad, pipeline.features)
    assert "ACTION_UNDERSIZED" in v.flagged_issues


def test_judge_detecte_la_sur_confiance(pipeline, case):
    """Une confiance de 0.99 sans preuve doit etre relevee et facturee."""
    bad = _mutate(case["decision"], confidence=0.99)
    v = pipeline.judge.judge(bad, pipeline.features)
    assert "OVERCONFIDENCE" in v.flagged_issues
    assert v.global_score < case["verdict"].global_score


def test_aucune_decision_native_ne_declenche_la_sur_confiance(pipeline):
    """LE TEST QUE `detection_agent` AFFIRMAIT AVOIR.

    `_calibrate_confidence` affirme, depuis l'alignement des deux baremes de
    confiance, qu'« un test verifie qu'aucun etat de marche ne produit
    OVERCONFIDENCE sur une decision nominale ». Aucun test ne le faisait : la
    seule occurrence du code dans la suite forcait `confidence=0.99` pour
    verifier que le piege est bien detecte.

    L'affirmation compte pourtant plus que le piege. Tant que les deux baremes
    divergeaient, l'agent produisait de lui-meme des decisions que son propre
    controleur sanctionnait : la note globale n'en portait pas la trace, mais
    l'encart « Reserves du controleur » — le seul que lit l'exploitant —
    affichait une sur-confiance sur une decision parfaitement reguliere.

    On soumet donc les decisions REELLES de la chaine, sans aucune mutation.
    """
    instants = pipeline.notable_timestamps(12)
    assert instants, "aucun instant notable disponible"

    fautives = [
        (str(ts), analyse.decision.confidence, analyse.verdict.flagged_issues)
        for ts in instants
        for analyse in [pipeline.analyze_at(ts)]
        if "OVERCONFIDENCE" in analyse.verdict.flagged_issues
        or "UNDERCONFIDENCE" in analyse.verdict.flagged_issues
    ]
    assert not fautives, (
        "l'agent produit des decisions que son propre controleur sanctionne "
        f"sur l'echelle de confiance : {fautives}"
    )


def test_judge_detecte_un_etat_de_marche_errone(pipeline, case):
    """Se tromper d'etat invalide toute lecture des grandeurs de performance."""
    other = "STOPPED" if case["decision"].process_state == "RUNNING" else "RUNNING"
    bad = _mutate(case["decision"], process_state=other)
    v = pipeline.judge.judge(bad, pipeline.features)
    assert "STATE_MISMATCH" in v.flagged_issues
    assert v.global_score <= 5.0


def test_judge_detecte_un_diagnostic_sans_chiffres(pipeline, case):
    """Un diagnostic non chiffre n'est pas verifiable et doit etre sanctionne."""
    bad = _mutate(
        case["decision"], cited_values={},
        diagnosis="Une anomalie a ete detectee sur l'equipement.",
    )
    v = pipeline.judge.judge(bad, pipeline.features)
    assert "NO_QUANTITATIVE_EVIDENCE" in v.flagged_issues
    assert v.global_score < case["verdict"].global_score


def test_judge_detecte_une_severite_sous_estimee(pipeline, case):
    """Minimiser une situation degradee doit etre sanctionne."""
    if case["decision"].severity not in ("WARNING", "CRITICAL"):
        pytest.skip("le cas de reference n'est pas degrade")
    bad = _mutate(case["decision"], severity="NORMAL")
    v = pipeline.judge.judge(bad, pipeline.features)
    assert "SEVERITY_UNDERESTIMATED" in v.flagged_issues
    assert v.corrected_severity == case["verdict"].verified_facts["rule_severity"]


def test_la_note_ne_peut_pas_etre_compensee(pipeline, case):
    """Un manquement de securite ne doit jamais etre rattrape par le reste.

    Sans plafonnement, une moyenne ponderee permettrait a une action dangereuse
    d'etre noyee par sept controles reussis et de passer en validation.
    """
    bad = _mutate(
        case["decision"],
        cited_values={**case["decision"].cited_values, "T_ACID_OUT": 85.0},
        diagnosis="Sortie acide a 85.0 degC.",
    )
    v = pipeline.judge.judge(bad, pipeline.features)
    passed = [c for c in v.checks if c.passed]
    assert len(passed) >= 4, "cas de test invalide : trop de controles echouent"
    assert v.global_score <= 4.0


# ── Evaluation globale du Judge ───────────────────────────────────────────────

def test_banc_devaluation_du_judge(pipeline):
    """Le Judge doit attraper la quasi-totalite des fautes sans sur-rejeter.

    C'est le test qui justifie de faire confiance au dispositif. Les seuils
    sont ceux qu'un exploitant exigerait : un controle qui laisse passer une
    faute sur cinq, ou qui rejette une decision correcte sur cinq, ne sera
    pas utilise.
    """
    res = JudgeEvaluator(pipeline).run(n_cases=6)
    s = res.summary
    assert s["trap_detection_rate"] >= 0.85, f"rappel insuffisant: {s['trap_detection_rate']}"
    assert s["false_positive_rate"] <= 0.20, f"trop de faux positifs: {s['false_positive_rate']}"
    assert s["separation"] >= 2.0, f"separation trop faible: {s['separation']}"


def test_chaque_type_de_faute_est_couvert(pipeline):
    """Chaque piege du catalogue doit etre detecte au moins une fois."""
    res = JudgeEvaluator(pipeline).run(n_cases=4)
    covered = set(res.traps["expected_issue"])
    expected = {t.expected_issue for t in TRAP_CASES}
    missing = expected - covered
    assert not missing, f"types de faute non evalues: {missing}"
    undetected = res.traps[res.traps["detection_rate"] < 100.0]["expected_issue"].tolist()
    assert not undetected, f"fautes non systematiquement detectees: {undetected}"


def test_auto_surveillance_du_judge(pipeline):
    """Le Judge doit produire son propre rapport de controle."""
    pipeline.analyze_many(pipeline.notable_timestamps(8))
    rep = pipeline.judge.auditor.report()
    assert rep["n"] > 0
    assert 0.0 <= rep["agreement_rate"] <= 1.0
    assert "self_check_warnings" in rep


# ── Corrections d'audit : isolation et generalisation ─────────────────────────

def test_le_banc_ne_pollue_pas_l_auto_surveillance(pipeline):
    """DEFAUT D DE L'AUDIT.

    Le banc reutilise le Judge de production. Sans isolation, les decisions
    volontairement fausses etaient comptabilisees dans l'auto-surveillance :
    le taux d'accord affiche a l'exploitant tombait de 1,00 a 0,50 et lui
    faisait croire que le systeme se contredit en exploitation.
    """
    from src.governance.judge_eval import JudgeEvaluator

    pipeline.judge.auditor = type(pipeline.judge.auditor)()
    for ts in pipeline.notable_timestamps(3):
        detection = pipeline.detector.analyze(pipeline.features, ts)
        pipeline.judge.judge(pipeline.agent.analyze(detection), pipeline.features)
    avant = pipeline.judge.auditor.report()["n"]

    JudgeEvaluator(pipeline).run(n_cases=2)
    apres = pipeline.judge.auditor.report()["n"]

    assert apres == avant, (
        f"le banc a ajoute {apres - avant} decisions fausses a l'auto-surveillance"
    )


def test_l_auto_surveillance_reprend_apres_le_banc(pipeline):
    """La suspension doit etre temporaire, meme en cas d'exception."""
    judge = pipeline.judge
    assert judge._audit_enabled is True
    with contextlib.suppress(RuntimeError), judge.suspended_audit():
        assert judge._audit_enabled is False
        raise RuntimeError("interruption simulee")
    assert judge._audit_enabled is True


def test_les_mutations_non_ciblees_mesurent_la_generalisation(pipeline):
    """LE CHIFFRE HONNETE.

    Les pieges du catalogue sont ecrits pour declencher un controle precis :
    leur taux mesure la non-regression. Les mutations non ciblees, elles, ne
    visent rien et donnent la vraie mesure de ce que le Judge attrape sans
    l'avoir anticipe.
    """
    from src.governance.judge_eval import JudgeEvaluator

    summary = JudgeEvaluator(pipeline).run(n_cases=3).summary

    assert "blind_mutations" in summary
    blind = summary["blind_mutations"]
    assert blind["n"] > 0
    # La generalisation doit rester NETTEMENT sous la non-regression. Si les
    # deux se rejoignent, c'est que les mutations dites non ciblees visent en
    # realite un controle — exactement le defaut qui rendait ce chiffre
    # trompeur : trois des cinq mutations d'origine declenchaient V1, V2 et V3
    # par construction.
    assert blind["flagged_rate"] <= summary["trap_detection_rate"] - 0.10, (
        f"generalisation {blind['flagged_rate']:.0%} trop proche de la "
        f"non-regression {summary['trap_detection_rate']:.0%} : les mutations "
        f"visent probablement un controle"
    )
    assert "honnete" in blind["reading"]


def test_aucune_mutation_non_ciblee_ne_vise_un_controle(pipeline):
    """LE TEST QUE `judge_eval` AFFIRMAIT AVOIR — DEUX FOIS.

    Le module declare que « les cinq mutations retenues portent sur des
    proprietes qu'aucun des huit controles n'interroge » et qu'« un test
    verifie qu'aucune ne porte le nom d'un controle implemente ». Ce test
    n'existait pas, et l'affirmation etait fausse : `drop_measurements` vidait
    `cited_values`, exactement ce que fait le piege concu `_m_no_numbers`, et
    declenchait donc `NO_QUANTITATIVE_EVIDENCE` de facon deterministe. Un
    cinquieme du « chiffre de generalisation » etait garanti par construction.

    On soumet chaque mutation non ciblee a plusieurs instants reels et l'on
    exige qu'aucune ne produise systematiquement le meme code d'anomalie qu'un
    piege du catalogue : une mutation dont la detection est certaine mesure la
    non-regression, pas la generalisation.
    """
    from src.governance.judge_eval import _blind_mutations

    codes_cibles = {trap.expected_issue for trap in TRAP_CASES}
    evaluateur = JudgeEvaluator(pipeline)
    mutations = _blind_mutations(evaluateur._rng)
    assert mutations, "aucune mutation non ciblee definie"

    instants = pipeline.notable_timestamps(4)
    systematiques: dict[str, set[str]] = {}
    with pipeline.judge.suspended_audit():
        for nom, muter in mutations:
            releves: list[set[str]] = []
            for ts in instants:
                detection = pipeline.detector.analyze(pipeline.features, ts)
                decision = pipeline.agent.analyze(detection)
                verdict = pipeline.judge.judge(muter(decision), pipeline.features)
                releves.append(set(verdict.flagged_issues) & codes_cibles)
            toujours = set.intersection(*releves) if releves else set()
            if toujours:
                systematiques[nom] = toujours

    assert not systematiques, (
        "mutations dites non ciblees declenchant systematiquement un controle "
        f"du catalogue : {systematiques}"
    )


def test_le_banc_declare_sa_nature_de_test_de_regression(pipeline):
    """Le rapport ne doit pas laisser croire a une validation."""
    from src.governance.judge_eval import JudgeEvaluator

    summary = JudgeEvaluator(pipeline).run(n_cases=2).summary
    assert "NON-REGRESSION" in summary["nature"]
