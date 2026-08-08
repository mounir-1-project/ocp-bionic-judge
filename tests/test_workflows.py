"""Traçabilité et barrières des workflows maintenance."""

from __future__ import annotations

import re

import pytest

from src.operations import WorkflowStore
from src.operations.workflows import TERMINAL_STATES, WORKFLOW_STATES


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

    `BLOCKED` et `NOT_APPLICABLE` figuraient dans `WORKFLOW_STATES` et
    `STEP_STATES` sans qu'aucun test ne les atteigne : une enumeration dont une
    valeur n'est jamais produite est soit un chemin mort, soit un chemin non
    verifie. Ici c'etait le second — et `NOT_APPLICABLE` intervient dans la
    condition de cloture, donc dans la barriere la plus importante du module.

    LA DOCSTRING ANNONCAIT AUSSI `CANCELLED`, ET NE L'EXERCAIT PAS. Elle ne le
    pouvait pas : aucun producteur ne l'ecrivait. Le troisieme etat n'etait pas
    « non verifie », il etait mort — c'est WF-2, tranche depuis, et couvert par
    `test_tout_etat_declare_est_productible`.
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


def test_tout_etat_declare_est_productible(tmp_path):
    """WF-2 — Un vocabulaire d'états ne déclare rien d'inatteignable.

    `WORKFLOW_STATES` portait `CANCELLED`, qu'AUCUN des trois producteurs de
    statut ne pouvait écrire — `create` pose `PLANNED`, `update_step` pose
    `BLOCKED` ou `IN_PROGRESS`, `complete` pose `COMPLETED`. Même forme que
    LIN-1 sur `PROMOTION_STATUSES`.

    Il n'était pas inoffensif : `TERMINAL_STATES` le contenait, donc les gardes
    de `update_step` et de `complete` testaient une valeur impossible, et un
    lecteur en déduisait qu'un chemin d'annulation existe.

    Le contrôle est BEHAVIORAL et bidirectionnel : la boutique est conduite par
    son API publique, et l'ensemble des statuts réellement observés doit être
    exactement l'ensemble déclaré. Remettre `CANCELLED` sans écrire `cancel()`
    fait échouer ce test.
    """
    observes: set[str] = set()

    # PLANNED — à la création.
    store = WorkflowStore(tmp_path / "etats.db")
    workflow = store.create(
        template_id="INSPECTION_EXTERNE", title="Inspection externe",
        owner="Equipe mécanique", planned_at=None, created_by="maintenance",
        steps=_steps(),
    )
    observes.add(workflow["status"])

    # BLOCKED — dès qu'une étape est bloquée.
    etapes = workflow["steps"]
    courant = store.update_step(
        workflow["id"], etapes[0]["id"], status="BLOCKED", actor="maintenance",
        comment="Accès condamné", expected_version=etapes[0]["version"],
    )
    observes.add(courant["status"])

    # IN_PROGRESS — dès qu'aucune étape ne l'est plus.
    version = next(
        s for s in courant["steps"] if s["id"] == etapes[0]["id"]
    )["version"]
    courant = store.update_step(
        workflow["id"], etapes[0]["id"], status="COMPLETED", actor="maintenance",
        comment="Échafaudage retiré", expected_version=version,
    )
    observes.add(courant["status"])

    # COMPLETED — à la clôture signée.
    for etape in courant["steps"]:
        if etape["status"] in {"COMPLETED", "NOT_APPLICABLE"}:
            continue
        version = next(
            s for s in courant["steps"] if s["id"] == etape["id"]
        )["version"]
        courant = store.update_step(
            workflow["id"], etape["id"], status="COMPLETED", actor="maintenance",
            comment="Contrôlé", expected_version=version,
        )
    observes.add(
        store.complete(
            workflow["id"], actor="maintenance", signature="Chef mécanique"
        )["status"]
    )
    store.close()

    assert not WORKFLOW_STATES - observes, (
        f"états déclarés qu'aucun chemin ne produit : "
        f"{sorted(WORKFLOW_STATES - observes)}. Soit écrire la méthode qui les "
        f"atteint, soit les retirer du vocabulaire."
    )
    assert not observes - WORKFLOW_STATES, (
        f"états produits hors du vocabulaire déclaré : "
        f"{sorted(observes - WORKFLOW_STATES)}"
    )
    # Et la garde d'état terminal ne teste que des états atteignables.
    assert TERMINAL_STATES <= WORKFLOW_STATES


def test_le_schema_derive_son_vocabulaire_des_constantes(tmp_path):
    """WF-3 — `WORKFLOW_STATES` était déclaré et lu par personne.

    Le vocabulaire vivait en deux exemplaires : la constante Python, et la liste
    recopiée dans le `CHECK` du schéma. `update_step` validait contre
    `STEP_STATES`, jamais contre `WORKFLOW_STATES` — seul le littéral SQL était
    réellement appliqué, et rien ne le rattachait à la constante. Motif de S8-2.

    CE TEST PORTAIT UN NOM PLUS LARGE QUE SA COUVERTURE. « Dérive son
    vocabulaire des constantes » est une ÉGALITÉ ; il ne vérifiait qu'une
    inclusion — chaque état déclaré figure dans le schéma — plus l'absence
    NOMMÉE d'un seul intrus, `CANCELLED`. Un état ajouté au seul littéral SQL,
    ou une seconde valeur morte, passait donc sans bruit : exactement la
    divergence que WF-3 prétend avoir refermée.

    La contrainte est maintenant lue et comparée par ÉGALITÉ D'ENSEMBLES, ce qui
    subsume le cas `CANCELLED` au lieu de le nommer. Le contrôle porte sur la
    propriété, non sur l'exemple qui l'a fait découvrir.
    """
    store = WorkflowStore(tmp_path / "schema.db")
    schema = store._db.execute(
        "SELECT sql FROM sqlite_master WHERE name='workflows'"
    ).fetchone()[0]
    store.close()

    clause = re.search(r"CHECK\s*\(\s*status\s+IN\s*\(([^)]*)\)", schema)
    assert clause, f"aucune contrainte CHECK sur `status` dans le schéma :\n{schema}"
    admis = set(re.findall(r"'([A-Z_]+)'", clause.group(1)))

    assert admis == WORKFLOW_STATES, (
        f"le schéma et la constante divergent — "
        f"acceptés par le seul SQL : {sorted(admis - WORKFLOW_STATES)} ; "
        f"déclarés sans être acceptés : {sorted(WORKFLOW_STATES - admis)}"
    )
