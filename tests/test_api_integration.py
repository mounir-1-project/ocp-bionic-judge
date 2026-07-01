"""Integration tests for POST /analyze — full pipeline with mocked agents.

These tests exercise the complete HTTP → FastAPI → ML → Agent chain without
hitting real Gemini API calls.  The detection agent and judge agent are patched
with lightweight fakes that return realistic Pydantic-validated responses.

Run:
    pytest tests/test_api_integration.py -v
"""

from __future__ import annotations

import importlib
import sys
import unittest.mock as _umock

# Mock heavy/optional ML deps ONLY when they are genuinely not importable (e.g. a
# minimal CI sandbox). On a full install these modules ARE present, so we must NOT
# replace them: inserting a MagicMock for "sklearn"/"sklearn.base" into sys.modules
# leaks into every other test file collected afterwards and makes a real transformer
# subclass a MagicMock base -> "metaclass conflict" when importing feature_engineering.
_OPTIONAL_DEPS = (
    "joblib", "shap", "mlflow",
    "google.generativeai", "langchain", "langchain_google_genai",
    "sklearn", "sklearn.base", "sklearn.ensemble", "sklearn.svm",
    "sklearn.neighbors", "sklearn.preprocessing", "sklearn.pipeline",
    "sklearn.model_selection", "sklearn.metrics",
    "src.models.predict", "src.agents.detection_agent", "src.agents.judge_agent",
)
for _dep in _OPTIONAL_DEPS:
    try:
        importlib.import_module(_dep)          # already installed -> keep the real module
    except Exception:
        sys.modules.setdefault(_dep, _umock.MagicMock())  # absent -> safe to mock

# Wire mock submodules onto the real src packages so patch() can find them — only for
# the ones that ended up mocked (absent). When the real modules are present this is a
# no-op and the tests use @patch on the real callables.
import src.models, src.agents
for _name, _pkg, _attr in (
    ("src.models.predict", src.models, "predict"),
    ("src.agents.detection_agent", src.agents, "detection_agent"),
    ("src.agents.judge_agent", src.agents, "judge_agent"),
):
    if isinstance(sys.modules.get(_name), _umock.MagicMock):
        setattr(_pkg, _attr, sys.modules[_name])

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))

from api.main import app, API_KEY
import src.db as _db_module

HEADERS = {"X-API-Key": API_KEY}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_predictions_df(machine_id: str = "BROYEUR_01", n: int = 20) -> pd.DataFrame:
    """Build a minimal predictions DataFrame as returned by src.models.predict.predict()."""
    rng = np.random.default_rng(42)
    now = datetime.now()
    rows = []
    for i in range(n):
        score = float(rng.uniform(0.1, 0.9))
        rows.append({
            "machine_id":    machine_id,
            "timestamp":     (now.replace(microsecond=0)).isoformat(),
            "anomaly_score": score,
            "is_anomaly":    int(score > 0.5),
            "severity":      "CRITICAL" if score > 0.7 else ("WARNING" if score > 0.3 else "NORMAL"),
            "model_version": "IsolationForest",
            "inference_ms":  float(rng.uniform(0.5, 2.0)),
        })
    return pd.DataFrame(rows)


def _make_agent_decision() -> MagicMock:
    """Return a mock that looks like a DetectionDecision Pydantic model."""
    dec = MagicMock()
    dec.diagnosis          = "Surchauffe moteur détectée — température 83 °C > seuil critique"
    dec.recommended_action = "Arrêt préventif recommandé dans les 2 heures"
    dec.confidence         = 0.87
    dec.model_dump.return_value = {
        "diagnosis":          dec.diagnosis,
        "recommended_action": dec.recommended_action,
        "confidence":         dec.confidence,
    }
    return dec


def _make_judge_evaluation() -> MagicMock:
    """Return a mock that looks like a JudgeEvaluation Pydantic model."""
    ev = MagicMock()
    ev.global_score = 7.4
    ev.agreement    = True
    return ev


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def inject_test_db(tmp_db_path):
    """Redirect the API engine to the test SQLite DB for every test."""
    _db_module._engine = tmp_db_path
    yield
    _db_module._engine = None


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


# ── Tests: invalid machine_id → 422 ───────────────────────────────────────────

def test_analyze_invalid_machine_id_returns_422(client: TestClient) -> None:
    """POST /analyze with an unknown machine_id must return 422 (Enum validation)."""
    payload = {"machine_id": "UNKNOWN_MACHINE", "use_agent": False, "run_judge": False}
    response = client.post("/analyze", json=payload, headers=HEADERS)
    assert response.status_code == 422, response.text
    body = response.json()
    # FastAPI 422 body contains a 'detail' list with the offending field
    assert "detail" in body
    assert any("machine_id" in str(err) for err in body["detail"])


def test_analyze_missing_machine_id_returns_422(client: TestClient) -> None:
    """POST /analyze without machine_id must return 422."""
    response = client.post("/analyze", json={"use_agent": False}, headers=HEADERS)
    assert response.status_code == 422


def test_analyze_requires_auth(client: TestClient) -> None:
    """POST /analyze without API key returns 401."""
    payload = {"machine_id": "BROYEUR_01", "use_agent": False, "run_judge": False}
    response = client.post("/analyze", json=payload)
    assert response.status_code == 401


# ── Tests: valid machine_id, agent mocked ──────────────────────────────────────

@patch("api.main._AGENT_POOL")
@patch("src.models.predict.predict", return_value=_make_predictions_df())
def test_analyze_no_agent_returns_200(mock_predict, mock_pool, client: TestClient) -> None:
    """POST /analyze with use_agent=False returns 200 with correct schema."""
    # Run synchronously in test (bypass thread pool)
    from api.main import _analyze_sync, AnalyzeRequest, MachineId
    req = AnalyzeRequest(machine_id=MachineId.BROYEUR_01, use_agent=False, run_judge=False)

    with patch("src.models.predict.predict", return_value=_make_predictions_df()):
        response = _analyze_sync(req)

    assert response.machine_id == "BROYEUR_01"
    assert response.anomaly_score is not None
    assert response.severity in {"NORMAL", "WARNING", "CRITICAL"}
    assert response.processing_ms >= 0


@patch("src.agents.detection_agent.analyze_machine", return_value=_make_agent_decision())
@patch("src.models.predict.predict", return_value=_make_predictions_df())
def test_analyze_with_agent_no_judge(mock_predict, mock_agent) -> None:
    """_analyze_sync with use_agent=True fills diagnosis + confidence fields."""
    from api.main import _analyze_sync, AnalyzeRequest, MachineId

    req = AnalyzeRequest(machine_id=MachineId.BROYEUR_01, use_agent=True, run_judge=False)
    response = _analyze_sync(req)

    assert response.diagnosis is not None
    assert "Surchauffe" in response.diagnosis
    assert response.confidence == pytest.approx(0.87, abs=1e-3)
    assert response.judge_score is None  # judge not requested


@patch("src.agents.judge_agent.judge_decision",   return_value=_make_judge_evaluation())
@patch("src.agents.detection_agent.analyze_machine", return_value=_make_agent_decision())
@patch("src.models.predict.predict",              return_value=_make_predictions_df())
def test_analyze_with_agent_and_judge(mock_predict, mock_agent, mock_judge) -> None:
    """_analyze_sync with run_judge=True fills judge_score and judge_agreement."""
    from api.main import _analyze_sync, AnalyzeRequest, MachineId

    req = AnalyzeRequest(machine_id=MachineId.BROYEUR_01, use_agent=True, run_judge=True)
    response = _analyze_sync(req)

    assert response.judge_score == pytest.approx(7.4, abs=1e-3)
    assert response.judge_agreement is True


@patch("src.models.predict.predict", return_value=pd.DataFrame())  # empty → 404
def test_analyze_no_data_returns_404(mock_predict) -> None:
    """_analyze_sync raises 404 when predict returns no rows."""
    from fastapi import HTTPException
    from api.main import _analyze_sync, AnalyzeRequest, MachineId

    req = AnalyzeRequest(machine_id=MachineId.POMPE_02, use_agent=False, run_judge=False)
    with pytest.raises(HTTPException) as exc_info:
        _analyze_sync(req)
    assert exc_info.value.status_code == 404


# ── Tests: all five valid machine IDs accepted ──────────────────────────────────

@pytest.mark.parametrize("machine_id", [
    "BROYEUR_01", "POMPE_02", "CONVOYEUR_03", "REACTEUR_04", "COMPRESSEUR_05",
])
def test_all_valid_machine_ids_pass_enum_validation(machine_id: str) -> None:
    """All five OCP Bionic machines are accepted by the MachineId enum."""
    from api.main import MachineId
    m = MachineId(machine_id)
    assert m.value == machine_id


# ── Tests: GET /decisions machine_id filter ────────────────────────────────────

def test_decisions_filter_by_valid_machine(client: TestClient) -> None:
    """GET /decisions?machine_id=BROYEUR_01 returns 200."""
    response = client.get("/decisions?machine_id=BROYEUR_01", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert all(d["machine_id"] == "BROYEUR_01" for d in data)


def test_decisions_filter_by_invalid_machine_returns_422(client: TestClient) -> None:
    """GET /decisions?machine_id=INVALID returns 422."""
    response = client.get("/decisions?machine_id=INVALID", headers=HEADERS)
    assert response.status_code == 422


def test_decisions_filter_by_severity(client: TestClient) -> None:
    """GET /decisions?severity=CRITICAL returns only CRITICAL rows."""
    response = client.get("/decisions?severity=CRITICAL", headers=HEADERS)
    assert response.status_code == 200
    for row in response.json():
        assert row["severity"] == "CRITICAL"


def test_decisions_invalid_severity_returns_422(client: TestClient) -> None:
    """GET /decisions?severity=BAD returns 422 (pattern validation)."""
    response = client.get("/decisions?severity=BAD", headers=HEADERS)
    assert response.status_code == 422


# ── Tests: GET /api/sensors/{machine_id} ──────────────────────────────────────

def test_sensors_valid_machine(client: TestClient) -> None:
    """GET /api/sensors/BROYEUR_01 returns 200 with a list."""
    response = client.get("/api/sensors/BROYEUR_01", headers=HEADERS)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_sensors_invalid_machine_returns_422(client: TestClient) -> None:
    """GET /api/sensors/UNKNOWN returns 422."""
    response = client.get("/api/sensors/UNKNOWN", headers=HEADERS)
    assert response.status_code == 422
