"""Workflows SQLite traçables pour inspections et interventions E7301."""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Voir la note dans src/operations/alarms.py : compatibilite Python 3.10.
UTC = timezone.utc

WORKFLOW_STATES = {"PLANNED", "IN_PROGRESS", "BLOCKED", "COMPLETED", "CANCELLED"}
STEP_STATES = {"TODO", "IN_PROGRESS", "BLOCKED", "COMPLETED", "NOT_APPLICABLE"}


class WorkflowStore:
    """Registre local démonstrateur; il ne remplace ni GMAO ni permis HSE."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(
            self.path, check_same_thread=False, timeout=15, isolation_level=None
        )
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                template_id TEXT NOT NULL,
                equipment_id TEXT NOT NULL,
                title TEXT NOT NULL,
                owner TEXT NOT NULL,
                planned_at TEXT,
                executed_at TEXT,
                status TEXT NOT NULL,
                created_by TEXT NOT NULL,
                signed_by TEXT,
                signed_at TEXT,
                proof_ref TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK(status IN ('PLANNED','IN_PROGRESS','BLOCKED','COMPLETED','CANCELLED'))
            );
            CREATE TABLE IF NOT EXISTS workflow_steps (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                code TEXT NOT NULL,
                label TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                dangerous INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'TODO',
                measurement TEXT,
                unit TEXT,
                comment TEXT,
                proof_ref TEXT,
                completed_by TEXT,
                completed_at TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                UNIQUE(workflow_id, sequence),
                FOREIGN KEY(workflow_id) REFERENCES workflows(id),
                CHECK(status IN ('TODO','IN_PROGRESS','BLOCKED','COMPLETED','NOT_APPLICABLE'))
            );
            CREATE TABLE IF NOT EXISTS workflow_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL,
                step_id TEXT,
                changed_at TEXT NOT NULL,
                actor TEXT NOT NULL,
                event TEXT NOT NULL,
                detail TEXT NOT NULL,
                FOREIGN KEY(workflow_id) REFERENCES workflows(id)
            );
            """
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def create(
        self,
        *,
        template_id: str,
        title: str,
        owner: str,
        planned_at: str | None,
        created_by: str,
        steps: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not steps:
            raise ValueError("Le workflow doit contenir au moins une étape")
        workflow_id = str(uuid.uuid4())
        now = self._now()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._db.execute(
                    """
                    INSERT INTO workflows(
                        id,template_id,equipment_id,title,owner,planned_at,status,
                        created_by,created_at,updated_at
                    ) VALUES(?,?, 'S-PC-E7301', ?,?,?,'PLANNED',?,?,?)
                    """,
                    (
                        workflow_id, template_id, title, owner, planned_at,
                        created_by, now, now,
                    ),
                )
                for sequence, step in enumerate(steps, start=1):
                    self._db.execute(
                        """
                        INSERT INTO workflow_steps(
                            id,workflow_id,sequence,code,label,source_ref,dangerous
                        ) VALUES(?,?,?,?,?,?,?)
                        """,
                        (
                            str(uuid.uuid4()), workflow_id, sequence,
                            step["code"], step["label"], step["source_ref"],
                            int(bool(step.get("dangerous"))),
                        ),
                    )
                self._history(workflow_id, None, created_by, "CREATED", template_id)
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise
        return self.get(workflow_id)

    def update_step(
        self,
        workflow_id: str,
        step_id: str,
        *,
        status: str,
        actor: str,
        measurement: str = "",
        unit: str = "",
        comment: str = "",
        proof_ref: str = "",
        expected_version: int,
    ) -> dict[str, Any]:
        if status not in STEP_STATES:
            raise ValueError("État d'étape invalide")
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                workflow = self._db.execute(
                    "SELECT * FROM workflows WHERE id=?", (workflow_id,)
                ).fetchone()
                step = self._db.execute(
                    "SELECT * FROM workflow_steps WHERE id=? AND workflow_id=?",
                    (step_id, workflow_id),
                ).fetchone()
                if workflow is None or step is None:
                    raise KeyError(step_id)
                if workflow["status"] in {"COMPLETED", "CANCELLED"}:
                    raise ValueError("Workflow terminal: modification interdite")
                if step["version"] != expected_version:
                    raise ValueError("Conflit de version: recharger le workflow")
                if status == "COMPLETED" and step["dangerous"]:
                    previous_open = self._db.execute(
                        """
                        SELECT COUNT(*) FROM workflow_steps
                        WHERE workflow_id=? AND sequence<?
                          AND status NOT IN ('COMPLETED','NOT_APPLICABLE')
                        """,
                        (workflow_id, step["sequence"]),
                    ).fetchone()[0]
                    if previous_open:
                        raise ValueError(
                            "Étape dangereuse bloquée: étapes préalables incomplètes"
                        )
                    if not comment.strip():
                        raise ValueError(
                            "Commentaire de contrôle obligatoire pour une étape dangereuse"
                        )
                now = self._now()
                completed_by = actor if status == "COMPLETED" else None
                completed_at = now if status == "COMPLETED" else None
                self._db.execute(
                    """
                    UPDATE workflow_steps SET status=?,measurement=?,unit=?,comment=?,
                        proof_ref=?,completed_by=?,completed_at=?,version=version+1
                    WHERE id=?
                    """,
                    (
                        status, measurement.strip(), unit.strip(), comment.strip(),
                        proof_ref.strip(), completed_by, completed_at, step_id,
                    ),
                )
                # L'ETAT DE L'INTERVENTION EST DEDUIT DE TOUTES SES ETAPES,
                # PAS DE LA DERNIERE TOUCHEE.
                #
                # Il valait `BLOCKED` si l'etape courante venait d'etre
                # bloquee, `IN_PROGRESS` dans tous les autres cas. Consequence :
                # bloquer l'etape A puis completer l'etape B repassait
                # l'intervention en cours alors que A restait bloquee. Le
                # blocage disparaissait de l'en-tete — donc de la liste des
                # interventions — tout en subsistant dans le detail. Sur un
                # bordereau qui trace une consignation, un blocage qui cesse de
                # se voir est une regression de securite, pas d'affichage.
                bloquees = self._db.execute(
                    "SELECT COUNT(*) FROM workflow_steps "
                    "WHERE workflow_id=? AND status='BLOCKED'",
                    (workflow_id,),
                ).fetchone()[0]
                workflow_status = "BLOCKED" if bloquees else "IN_PROGRESS"
                self._db.execute(
                    "UPDATE workflows SET status=?,updated_at=? WHERE id=?",
                    (workflow_status, now, workflow_id),
                )
                self._history(
                    workflow_id, step_id, actor, f"STEP_{status}",
                    comment.strip() or measurement.strip() or "-",
                )
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise
        return self.get(workflow_id)

    def complete(
        self,
        workflow_id: str,
        *,
        actor: str,
        signature: str,
        proof_ref: str = "",
    ) -> dict[str, Any]:
        if not signature.strip():
            raise ValueError("Signature de clôture obligatoire")
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                workflow = self._db.execute(
                    "SELECT * FROM workflows WHERE id=?", (workflow_id,)
                ).fetchone()
                if workflow is None:
                    raise KeyError(workflow_id)
                open_count = self._db.execute(
                    """
                    SELECT COUNT(*) FROM workflow_steps WHERE workflow_id=?
                    AND status NOT IN ('COMPLETED','NOT_APPLICABLE')
                    """,
                    (workflow_id,),
                ).fetchone()[0]
                if open_count:
                    raise ValueError(f"{open_count} étape(s) restent ouvertes")
                now = self._now()
                self._db.execute(
                    """
                    UPDATE workflows SET status='COMPLETED',executed_at=?,
                        signed_by=?,signed_at=?,proof_ref=?,updated_at=? WHERE id=?
                    """,
                    (now, signature.strip(), now, proof_ref.strip(), now, workflow_id),
                )
                self._history(workflow_id, None, actor, "COMPLETED", signature.strip())
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise
        return self.get(workflow_id)

    def _history(
        self,
        workflow_id: str,
        step_id: str | None,
        actor: str,
        event: str,
        detail: str,
    ) -> None:
        self._db.execute(
            """
            INSERT INTO workflow_history(
                workflow_id,step_id,changed_at,actor,event,detail
            ) VALUES(?,?,?,?,?,?)
            """,
            (workflow_id, step_id, self._now(), actor, event, detail),
        )

    def get(self, workflow_id: str) -> dict[str, Any]:
        with self._lock:
            workflow = self._db.execute(
                "SELECT * FROM workflows WHERE id=?", (workflow_id,)
            ).fetchone()
            if workflow is None:
                raise KeyError(workflow_id)
            result = dict(workflow)
            result["steps"] = [
                {**dict(step), "dangerous": bool(step["dangerous"])}
                for step in self._db.execute(
                    "SELECT * FROM workflow_steps WHERE workflow_id=? ORDER BY sequence",
                    (workflow_id,),
                )
            ]
            result["history"] = [
                dict(item) for item in self._db.execute(
                    """
                    SELECT step_id,changed_at,actor,event,detail
                    FROM workflow_history WHERE workflow_id=? ORDER BY id
                    """,
                    (workflow_id,),
                )
            ]
            return result

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(row) for row in self._db.execute(
                    "SELECT * FROM workflows ORDER BY updated_at DESC LIMIT ?",
                    (max(1, min(limit, 500)),),
                )
            ]

    def close(self) -> None:
        with self._lock:
            self._db.close()
