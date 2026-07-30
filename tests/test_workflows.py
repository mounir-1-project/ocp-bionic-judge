"""Traçabilité et barrières des workflows maintenance."""

from __future__ import annotations

import pytest

from src.operations import WorkflowStore


def _steps():
    return [
        {
            "code": "HSE-01",
            "label": "Autorisation de travail",
            "source_ref": "Gamme OCP page 1",
            "dangerous": False,
        },
        {
            "code": "HSE-02",
            "label": "Consignation",
            "source_ref": "Gamme OCP page 1",
            "dangerous": True,
        },
        {
            "code": "HSE-03",
            "label": "Pression nulle",
            "source_ref": "Gamme OCP page 1",
            "dangerous": True,
        },
    ]


def test_workflow_persistant_et_historique_immuable(tmp_path):
    path = tmp_path / "workflows.db"
    store = WorkflowStore(path)
    workflow = store.create(
        template_id="INSPECTION_INTERNE",
        title="Inspection interne",
        owner="Equipe mécanique",
        planned_at="2026-08-01",
        created_by="maintenance@example.test",
        steps=_steps(),
    )
    assert workflow["status"] == "PLANNED"
    assert len(workflow["steps"]) == 3
    assert workflow["history"][0]["event"] == "CREATED"
    store.close()

    reopened = WorkflowStore(path)
    assert reopened.get(workflow["id"])["owner"] == "Equipe mécanique"
    reopened.close()


def test_etape_dangereuse_bloquee_et_version_optimiste(tmp_path):
    store = WorkflowStore(tmp_path / "workflows.db")
    workflow = store.create(
        template_id="INSPECTION_INTERNE",
        title="Inspection interne",
        owner="Equipe mécanique",
        planned_at=None,
        created_by="maintenance",
        steps=_steps(),
    )
    dangerous = workflow["steps"][1]
    with pytest.raises(ValueError, match="préalables"):
        store.update_step(
            workflow["id"],
            dangerous["id"],
            status="COMPLETED",
            actor="maintenance",
            comment="Consignation vérifiée",
            expected_version=1,
        )
    first = workflow["steps"][0]
    updated = store.update_step(
        workflow["id"],
        first["id"],
        status="COMPLETED",
        actor="maintenance",
        comment="Permis reçu",
        expected_version=1,
    )
    with pytest.raises(ValueError, match="Conflit de version"):
        store.update_step(
            workflow["id"],
            first["id"],
            status="COMPLETED",
            actor="maintenance",
            comment="Répétition",
            expected_version=1,
        )
    assert updated["steps"][0]["version"] == 2
    store.close()


def test_cloture_exige_toutes_les_etapes_et_signature(tmp_path):
    store = WorkflowStore(tmp_path / "workflows.db")
    workflow = store.create(
        template_id="INSPECTION_INTERNE",
        title="Inspection interne",
        owner="Equipe mécanique",
        planned_at=None,
        created_by="maintenance",
        steps=_steps(),
    )
    with pytest.raises(ValueError, match="restent ouvertes"):
        store.complete(
            workflow["id"], actor="maintenance", signature="Chef mécanique"
        )
    current = workflow
    for step in current["steps"]:
        current = store.update_step(
            workflow["id"],
            step["id"],
            status="COMPLETED",
            actor="maintenance",
            comment="Contrôle documenté",
            expected_version=step["version"],
        )
    with pytest.raises(ValueError, match="Signature"):
        store.complete(workflow["id"], actor="maintenance", signature="")
    completed = store.complete(
        workflow["id"],
        actor="maintenance",
        signature="Chef mécanique",
        proof_ref="GMAO-A-CONFIRMER",
    )
    assert completed["status"] == "COMPLETED"
    assert completed["signed_by"] == "Chef mécanique"
    store.close()
