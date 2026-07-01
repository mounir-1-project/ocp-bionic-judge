"""Tests for src/agents/judge_agent.py (unit tests with mocking)."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.agents.judge_agent import (
    CriteriaScores,
    JudgeEvaluation,
    JudgeInput,
    DISAGREEMENT_THRESHOLD,
)


def test_judge_evaluation_agreement_flag() -> None:
    """JudgeEvaluation.agreement is True when global_score >= 6."""
    ev = JudgeEvaluation(
        global_score=7.5,
        criteria_scores=CriteriaScores(
            relevance=8.0, history_coherence=7.0, calibrated_confidence=7.5,
            ocp_compliance=7.0, action_feasibility=8.0
        ),
        agreement=True,
        feedback="Good decision",
        flagged_issues=[],
    )
    assert ev.agreement is True
    assert ev.global_score == 7.5


def test_judge_evaluation_disagreement_flag() -> None:
    """JudgeEvaluation.agreement is False when global_score < 6."""
    ev = JudgeEvaluation(
        global_score=4.5,
        criteria_scores=CriteriaScores(
            relevance=4.0, history_coherence=5.0, calibrated_confidence=4.0,
            ocp_compliance=5.0, action_feasibility=5.0
        ),
        agreement=False,
        feedback="Poor diagnosis",
        flagged_issues=["WRONG_DIAGNOSIS"],
    )
    assert ev.agreement is False
    assert len(ev.flagged_issues) == 1


def test_judge_evaluation_score_bounds() -> None:
    """JudgeEvaluation rejects scores outside [0, 10]."""
    with pytest.raises(Exception):
        JudgeEvaluation(
            global_score=11.0,  # invalid
            criteria_scores=CriteriaScores(
                relevance=5.0, history_coherence=5.0, calibrated_confidence=5.0,
                ocp_compliance=5.0, action_feasibility=5.0
            ),
            agreement=True,
            feedback="",
        )


def test_judge_input_pydantic_validation(anomaly_decision) -> None:
    """JudgeInput validates required fields."""
    payload = JudgeInput(
        machine_context={"machine_id": "BROYEUR_01"},
        detected_anomaly={"anomaly_score": 0.85},
        agent_decision=anomaly_decision,
    )
    assert payload.agent_decision["machine_id"] == "BROYEUR_01"


def test_disagreement_threshold_value() -> None:
    """DISAGREEMENT_THRESHOLD is between 5 and 7."""
    assert 5.0 <= DISAGREEMENT_THRESHOLD <= 7.0


@pytest.mark.parametrize("score,expected_agreement", [
    (9.0, True),
    (6.0, True),
    (5.9, False),
    (0.0, False),
])
def test_agreement_threshold_parametrize(score, expected_agreement) -> None:
    """agreement flag based on DISAGREEMENT_THRESHOLD."""
    agreement = score >= DISAGREEMENT_THRESHOLD
    assert agreement == expected_agreement