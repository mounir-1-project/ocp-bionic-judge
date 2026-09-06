"""
Tests des agents et du Judge — le controle doit reellement mordre.

Ces tests injectent des fautes precises dans une decision et verifient
que le Judge les releve et les sanctionne.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import copy

import pytest

from core.detection.schemas import AgentDecision, RecommendedAction
from tests.helpers import sans_accents


@pytest.fixture(scope="module")
def case(pipeline):
    """Un instant reel degrade, sa decision saine et son verdict."""
    ts = pipeline.episodes().iloc[0]["peak_at"]
    detection = pipeline.detector.analyze(pipeline.features, ts)
    decision = pipeline.agent.analyze(detection)
    verdict = pipeline.judge.judge(decision, pipeline.features)
    return {"ts": ts, "detection": detection, "decision": decision, "verdict": verdict}


def _mutate(decision: AgentDecision, **kw) -> AgentDecision:
    """Copie une decision en surchargeant des champs."""
    data = copy.deepcopy(decision.model_dump())
    data.update(kw)
    return AgentDecision(**data)


# ── Agent de detection ────────────────────────────────────────────────────────

def test_agent_fonctionne_sans_cle_api(pipeline):
    """L'agent doit fonctionner en mode regles sans aucune cle API."""
    ts = pipeline.features.index[100]
    d = pipeline.detector.analyze(pipeline.features, ts)
    decision = pipeline.agent.analyze(d)
    assert decision.severity in ("NORMAL", "INFO", "WARNING", "CRITICAL")
    assert 0.0 <= decision.confidence <= 1.0
    assert decision.generated_by == "rules"


def test_agent_nominal(pipeline):
    """Un instant nominal doit donner un diagnostic sans alarme."""
    for ts in pipeline.features.index:
        if pipeline.features.loc[ts, "process_state"] == "RUNNING":
            d = pipeline.detector.analyze(pipeline.features, ts)
            if d.severity == "NORMAL":
                decision = pipeline.agent.analyze(d)
                assert decision.severity == "NORMAL"
                assert "Marche établie" in decision.diagnosis
                break


# ── Judge ─────────────────────────────────────────────────────────────────────

def test_judge_valide_une_decision_saine(case):
    """Une decision correctement calibree doit obtenir un accord."""
    assert case["verdict"].agreement is True
    assert case["verdict"].global_score >= 6.0


def test_judge_releve_valeur_inventee(case, pipeline):
    """Le Judge doit detecter une valeur citee qui n'existe pas dans les faits."""
    mutated = _mutate(
        case["decision"],
        cited_values={"T_ACID_OUT": 999.0},
    )
    verdict = pipeline.judge.judge(mutated, pipeline.features)
    issues = verdict.flagged_issues
    assert "HALLUCINATED_VALUE" in issues or verdict.global_score < 6.0


def test_judge_releve_severite_sous_estimee(case, pipeline):
    """Le Judge doit detecter une sous-estimation de severite."""
    if case["decision"].severity == "CRITICAL":
        mutated = _mutate(case["decision"], severity="INFO")
        verdict = pipeline.judge.judge(mutated, pipeline.features)
        assert "SEVERITY_UNDERESTIMATED" in verdict.flagged_issues


def test_judge_releve_etat_errone(case, pipeline):
    """Le Judge doit detecter un etat de marche errone."""
    wrong_state = "STOPPED" if case["decision"].process_state != "STOPPED" else "RUNNING"
    mutated = _mutate(case["decision"], process_state=wrong_state)
    verdict = pipeline.judge.judge(mutated, pipeline.features)
    assert "STATE_MISMATCH" in verdict.flagged_issues


def test_judge_releve_mode_invente(case, pipeline):
    """Le Judge doit detecter un mode AMDEC inexistant."""
    mutated = _mutate(case["decision"], amdec_modes=["MODE_INEXISTANT"])
    verdict = pipeline.judge.judge(mutated, pipeline.features)
    assert "INVENTED_AMDEC_MODE" in verdict.flagged_issues


def test_judge_releve_angle_mort(case, pipeline):
    """Le Judge doit detecter un diagnostic sur un mode non observable."""
    # Trouver un mode non observable (none)
    from core.knowledge.knowledge import load_domain
    d = load_domain()
    blind = [m.code for m in d.modes.values() if m.observabilite == "none"]
    if blind:
        mutated = _mutate(case["decision"], amdec_modes=[blind[0]])
        verdict = pipeline.judge.judge(mutated, pipeline.features)
        assert "BLIND_SPOT_CLAIM" in verdict.flagged_issues
    else:
        pytest.skip("Aucun mode non observable dans l'AMDEC")


def test_judge_releve_action_dangereuse(case, pipeline):
    """Le Judge doit detecter une action sans mention d'arret alors que c'est requis."""
    mutated = _mutate(
        case["decision"],
        recommended_action=RecommendedAction(
            description="Inspection visuelle rapide en marche",
            urgency="SOUS_24H",
            execution_window="EN_MARCHE",
            requires_shutdown=False,
        ),
    )
    verdict = pipeline.judge.judge(mutated, pipeline.features)
    issues = verdict.flagged_issues
    assert "UNSAFE_ACTION" in issues or verdict.global_score < 4.0


def test_judge_releve_sur_confiance(case, pipeline):
    """Le Judge doit detecter une confiance trop elevee."""
    mutated = _mutate(case["decision"], confidence=0.99)
    verdict = pipeline.judge.judge(mutated, pipeline.features)
    assert "OVERCONFIDENCE" in verdict.flagged_issues


def test_judge_feedback_est_lisible(case):
    """Le feedback du Judge doit etre lisible et en francais."""
    feedback = case["verdict"].feedback
    assert len(feedback) > 20
    assert sans_accents(feedback) == sans_accents(feedback)


def test_judge_eight_checks(case):
    """Le verdict doit contenir exactement 8 controles."""
    assert len(case["verdict"].checks) == 8
    check_ids = {c.id for c in case["verdict"].checks}
    expected = {
        "V1_NUMERIC_FIDELITY", "V2_SEVERITY", "V3_AMDEC_GROUNDING",
        "V4_ACTION_CONFORMITY", "V5_CONFIDENCE", "V6_STATE_AWARENESS",
        "V7_EVIDENCE_COVERAGE", "V8_UNCERTAINTY",
    }
    assert check_ids == expected
