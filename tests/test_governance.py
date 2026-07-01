"""Tests for src/governance/governance.py"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.governance.governance import compute_metrics, CONFIDENCE_THRESHOLD, DISAGREEMENT_THRESHOLD


def test_compute_metrics_returns_dict(tmp_db_path) -> None:
    """compute_metrics returns a dict with required keys."""
    result = compute_metrics(db_path=tmp_db_path, window="24h")
    assert isinstance(result, dict)
    assert "window" in result
    assert "computed_at" in result


def test_compute_metrics_all_windows(tmp_db_path) -> None:
    """compute_metrics runs for all three time windows."""
    for window in ["1h", "24h", "7d"]:
        result = compute_metrics(db_path=tmp_db_path, window=window)
        assert result["window"] == window


def test_compute_metrics_confidence_in_range(tmp_db_path) -> None:
    """Mean judge confidence is between 0 and 1."""
    result = compute_metrics(db_path=tmp_db_path, window="7d")
    if "mean_judge_confidence" in result:
        assert 0.0 <= result["mean_judge_confidence"] <= 1.0


def test_compute_metrics_disagreement_in_range(tmp_db_path) -> None:
    """Disagreement rate is between 0 and 1."""
    result = compute_metrics(db_path=tmp_db_path, window="7d")
    if "disagreement_rate" in result:
        assert 0.0 <= result["disagreement_rate"] <= 1.0


def test_alerts_list_present(tmp_db_path) -> None:
    """compute_metrics always includes an 'alerts' list."""
    result = compute_metrics(db_path=tmp_db_path, window="24h")
    assert "alerts" in result
    assert isinstance(result["alerts"], list)


def test_thresholds_constants() -> None:
    """Governance threshold constants are in valid range."""
    assert 0 < CONFIDENCE_THRESHOLD < 1
    assert 0 < DISAGREEMENT_THRESHOLD < 1