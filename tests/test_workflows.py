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


def test_une_intervention_close_ne_se_reclot_pas(tmp_path):
    """WF-1 — LA SIGNATURE DE CLOTURE POUVAIT ETRE REECRITE SANS TRACE.

    `update_step` refuse d'agir sur une intervention terminale. `complete` ne
    verifiait rien : une seconde cloture remplacait le signataire, la date et
    la preuve de la premiere. Sur un document qui atteste qu'une consignation a
    ete levee, l'identite du signataire est ce qui compte.
    """
    store = WorkflowStore(tmp_path / "workflows.db")
    workflow = store.create(
        template_id="INSPECTION_INTERNE", title="Inspection interne",
        owner="Equipe mécanique", planned_at=None, created_by="maintenance",
        steps=_steps(),
    )
    current = workflow
    for step in workflow["steps"]:
        current = store.update_step(
            workflow["id"], step["id"], status="COMPLETED", actor="maintenance",
            comment="Contrôle documenté", expected_version=step["version"],
        )
    premier = store.complete(
        workflow["id"], actor="maintenance", signature="Chef mécanique",
        proof_ref="CR-001",
    )
    assert premier["signed_by"] == "Chef mécanique"

    with pytest.raises(ValueError, match="déjà en état"):
        store.complete(
            workflow["id"], actor="autre", signature="Quelqu'un d'autre",
            proof_ref="CR-002",
        )
    assert store.get(workflow["id"])["signed_by"] == "Chef mécanique"
    store.close()


def test_les_etats_non_nominaux_sont_atteignables(tmp_path):
    """WF-4 — TROIS ETATS DECLARES QU'AUCUN TEST N'EXERCAIT.

    `BLOCKED`, `NOT_APPLICABLE` et `CANCELLED` figurent dans `WORKFLOW_STATES`
    et `STEP_STATES`. Aucun test ne les atteignait : une enumeration dont une
    valeur n'est jamais produite est soit un chemin mort, soit un chemin non
    verifie. Ici c'etait le second — et `NOT_APPLICABLE` intervient dans la
    condition de cloture, donc dans la barriere la plus importante du module.
    """
    store = WorkflowStore(tmp_path / "workflows.db")
    workflow = store.create(
        template_id="INSPECTION_EXTERNE", title="Inspection externe",
        owner="Equipe mécanique", planned_at=None, created_by="maintenance",
        steps=_steps(),
    )
    etapes = workflow["steps"]

    bloquee = store.update_step(
        workflow["id"], etapes[0]["id"], status="BLOCKED", actor="maintenance",
        comment="Accès condamné par un échafaudage", expected_version=etapes[0]["version"],
    )
    assert bloquee["steps"][0]["status"] == "BLOCKED"

    # Une etape bloquee interdit la cloture : c'est tout l'objet de l'etat.
    with pytest.raises(ValueError, match="restent ouvertes"):
        store.complete(workflow["id"], actor="maintenance", signature="Chef")

    # NOT_APPLICABLE vaut COMPLETED pour la cloture, et le dit.
    courant = bloquee
    for etape in courant["steps"]:
        v = next(s for s in courant["steps"] if s["id"] == etape["id"])["version"]
        courant = store.update_step(
            workflow["id"], etape["id"], status="NOT_APPLICABLE", actor="maintenance",
            comment="Sans objet sur cette révision", expected_version=v,
        )
    assert {s["status"] for s in courant["steps"]} == {"NOT_APPLICABLE"}
    ferme = store.complete(
        workflow["id"], actor="maintenance", signature="Chef mécanique",
    )
    assert ferme["status"] == "COMPLETED"
    store.close()
