"""
Tests de l'API et du rejeu temps reel.

La chaine est construite une seule fois pour tout le module.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import json

import pytest

fastapi = pytest.importorskip("fastapi", reason="fastapi non installe")
from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    """Client de test avec cycle de vie complet."""
    with TestClient(app) as c:
        yield c


# ── Systeme ───────────────────────────────────────────────────────────────────

def test_sante(client):
    """L'API doit exposer son etat."""
    d = client.get("/api/health").json()
    assert d["status"] == "ok"
    assert d["version"] == "3.0.0"
    assert d["equipment"] == "S-PC-E7301"
    assert d["n_samples"] > 10000


def test_dashboard_servi(client):
    """Le poste doit fonctionner hors ligne."""
    r = client.get("/")
    assert r.status_code == 200
    assert "E7301" in r.text
    assert "/assets/app.css" in r.text
    assert "/assets/app.js" in r.text


def test_equipement(client):
    """L'equipement doit etre expose."""
    d = client.get("/api/equipment").json()
    assert "equipment" in d
    assert "tags" in d
    assert "amdec" in d
    assert len(d["tags"]) > 0
    assert len(d["amdec"]) > 0


def test_topologie(client):
    """La topologie 3D doit etre exposee."""
    d = client.get("/api/topology").json()
    assert "components" in d
    assert "sensors" in d
    assert len(d["sensors"]) > 0


# ── Donnees ───────────────────────────────────────────────────────────────────

def test_timeseries(client):
    """Les series temporelles doivent etre accessibles."""
    d = client.get("/api/timeseries").json()
    assert "timestamps" in d
    assert "n_total" in d
    assert d["n_total"] > 10000


def test_sensor_health(client):
    """La sante des capteurs doit etre exposee."""
    r = client.get("/api/sensor-health")
    assert r.status_code == 200
    data = r.json()
    assert len(data) > 0


def test_sensor_detail(client):
    """Le detail d'un capteur doit etre accessible."""
    d = client.get("/api/sensor/T_ACID_OUT").json()
    assert d["alias"] == "T_ACID_OUT"
    assert "series" in d
    assert "stats" in d


def test_episodes(client):
    """Les episodes doivent etre exposes."""
    r = client.get("/api/episodes")
    assert r.status_code == 200


# ── Analyse ───────────────────────────────────────────────────────────────────

def test_analyze(client):
    """L'analyse d'un instant doit fonctionner."""
    # Utiliser un timestamp connu
    ts = "2024-10-25T21:00:00"
    d = client.post("/api/analyze", json={"timestamp": ts}).json()
    assert "detection" in d
    assert "decision" in d
    assert "verdict" in d


def test_notable(client):
    """Les instants notables doivent etre exposes."""
    r = client.get("/api/notable?limit=5")
    assert r.status_code == 200


# ── Authentification ──────────────────────────────────────────────────────────

def test_auth_status(client):
    """Le status auth doit fonctionner."""
    d = client.get("/api/auth/status").json()
    assert "authenticated" in d


def test_auth_login_logout(client):
    """Le login/logout doit fonctionner."""
    r = client.post("/api/auth/login", json={"email": "test@test.com", "password": "test"})
    assert r.status_code == 200
    r = client.post("/api/auth/logout")
    assert r.status_code == 200


# ── Alarmes ───────────────────────────────────────────────────────────────────

def test_alarms(client):
    """Le registre d'alarmes doit etre accessible."""
    r = client.get("/api/alarms")
    assert r.status_code == 200


# ── Workflows ─────────────────────────────────────────────────────────────────

def test_workflow_templates(client):
    """Les templates doivent etre exposes."""
    d = client.get("/api/workflows/templates").json()
    assert len(d) > 0


# ── Judge ─────────────────────────────────────────────────────────────────────

def test_judge_audit(client):
    """Le Judge doit exposer sa synthese."""
    d = client.get("/api/judge/audit").json()
    assert "mode" in d
    assert "checks" in d


# ── KPI ───────────────────────────────────────────────────────────────────────

def test_kpi(client):
    """Les KPI doivent etre exposes."""
    d = client.get("/api/kpi").json()
    assert "figures" in d
    assert "calibration" in d


# ── Notifications ─────────────────────────────────────────────────────────────

def test_notifications_status(client):
    """Le status des notifications doit etre expose."""
    r = client.get("/api/notifications/status")
    assert r.status_code == 200
