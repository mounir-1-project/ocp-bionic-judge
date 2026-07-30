"""Registre SQLite auditable du cycle de vie des alarmes E7301.

Le registre ne déduit jamais qu'une alarme a disparu parce qu'une autre
analyse est normale. Une disparition doit cibler la même clé fonctionnelle
que l'apparition et conserver la preuve qui a provoqué la transition.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.pipeline import Analysis

# `datetime.UTC` n'existe qu'a partir de Python 3.11 alors que le projet
# declare un plancher a 3.10. On garde donc l'alias explicite plutot que de
# relever le plancher pour une seule constante.
UTC = timezone.utc

OPEN_STATES = ("ACTIVE", "ACKNOWLEDGED", "SHELVED")
VALID_STATES = (*OPEN_STATES, "RETURNED_NORMAL", "CLOSED")
OPERATOR_TRANSITIONS: dict[str, dict[str, str]] = {
    "acknowledge": {"ACTIVE": "ACKNOWLEDGED"},
    "shelve": {"ACTIVE": "SHELVED", "ACKNOWLEDGED": "SHELVED"},
    "unshelve": {"SHELVED": "ACTIVE"},
    "close": {"RETURNED_NORMAL": "CLOSED"},
}
# Libelle inscrit dans la colonne `transition` du journal. Il nomme l'ACTION
# de l'operateur, que l'etat d'arrivee ne suffit pas a restituer : « ACTIVE »
# ne distingue pas une desinhibition d'une reapparition.
OPERATOR_TRANSITION_LABELS: dict[str, str] = {
    "acknowledge": "ACKNOWLEDGED_BY_OPERATOR",
    "shelve": "SHELVED_BY_OPERATOR",
    "unshelve": "UNSHELVED_BY_OPERATOR",
    "close": "CLOSED_BY_OPERATOR",
}


class AlarmStore:
    """Conserve un cycle de vie indépendant pour chaque clé fonctionnelle."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(
            self.path,
            check_same_thread=False,
            timeout=15.0,
            isolation_level=None,
        )
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("PRAGMA journal_mode=WAL")
        self._create_schema()

    def _create_schema(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS alarms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alarm_uid TEXT,
                alarm_key TEXT NOT NULL,
                equipment_id TEXT NOT NULL DEFAULT 'S-PC-E7301',
                failure_mode TEXT,
                trigger_rule TEXT,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                returned_at TEXT,
                closed_at TEXT,
                severity TEXT NOT NULL,
                diagnosis TEXT NOT NULL,
                action TEXT NOT NULL,
                procedure_ref TEXT,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                occurrence_count INTEGER NOT NULL DEFAULT 1,
                owner TEXT,
                comment TEXT,
                acknowledged_by TEXT,
                acknowledged_at TEXT,
                shelved_by TEXT,
                shelved_at TEXT,
                shelve_reason TEXT,
                evidence_json TEXT NOT NULL DEFAULT '{}',
                return_evidence_json TEXT,
                updated_at TEXT NOT NULL,
                CHECK(status IN (
                    'ACTIVE','ACKNOWLEDGED','SHELVED','RETURNED_NORMAL','CLOSED'
                ))
            );
            CREATE INDEX IF NOT EXISTS ix_alarms_status
                ON alarms(status, last_seen);
            CREATE INDEX IF NOT EXISTS ix_alarms_key
                ON alarms(alarm_key, id DESC);
            CREATE TABLE IF NOT EXISTS alarm_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alarm_id INTEGER NOT NULL,
                changed_at TEXT NOT NULL,
                actor TEXT NOT NULL,
                from_status TEXT,
                to_status TEXT NOT NULL,
                transition TEXT NOT NULL,
                comment TEXT,
                evidence_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(alarm_id) REFERENCES alarms(id)
            );
            """
        )
        # Migration non destructive des bases créées par les versions antérieures.
        alarm_columns = {
            "alarm_uid": "TEXT",
            "equipment_id": "TEXT NOT NULL DEFAULT 'S-PC-E7301'",
            "failure_mode": "TEXT",
            "trigger_rule": "TEXT",
            "closed_at": "TEXT",
            "occurrence_count": "INTEGER NOT NULL DEFAULT 1",
            "acknowledged_by": "TEXT",
            "shelved_by": "TEXT",
            "shelved_at": "TEXT",
            "shelve_reason": "TEXT",
            "evidence_json": "TEXT NOT NULL DEFAULT '{}'",
            "return_evidence_json": "TEXT",
        }
        history_columns = {
            "from_status": "TEXT",
            "to_status": "TEXT",
            "evidence_json": "TEXT NOT NULL DEFAULT '{}'",
        }
        self._add_missing_columns("alarms", alarm_columns)
        self._add_missing_columns("alarm_history", history_columns)
        self._db.execute(
            "UPDATE alarms SET alarm_uid='legacy-' || id "
            "WHERE alarm_uid IS NULL OR alarm_uid=''"
        )
        self._db.execute(
            "UPDATE alarm_history SET to_status=transition "
            "WHERE to_status IS NULL OR to_status=''"
        )

    def _add_missing_columns(self, table: str, columns: dict[str, str]) -> None:
        present = {
            row["name"] for row in self._db.execute(f"PRAGMA table_info({table})")
        }
        for name, definition in columns.items():
            if name not in present:
                self._db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _equipment(analysis: Analysis) -> str:
        return str(getattr(analysis.decision, "equipment_id", "S-PC-E7301"))

    @staticmethod
    def _trigger(analysis: Analysis) -> str | None:
        findings = getattr(analysis.detection, "findings", ())
        return str(findings[0].code) if findings else None

    @classmethod
    def _key(cls, analysis: Analysis) -> str | None:
        """Clé stable : équipement et signal déclencheur, jamais la sévérité."""
        trigger = cls._trigger(analysis)
        if trigger is None:
            return None
        return f"{cls._equipment(analysis)}::{trigger}"

    @staticmethod
    def _evidence(analysis: Analysis) -> dict[str, Any]:
        detection = analysis.detection
        values: dict[str, Any] = {
            "timestamp": str(detection.timestamp),
            "anomaly_score": getattr(detection, "anomaly_score", None),
            "process_state": getattr(detection, "process_state", None),
            "finding_codes": [
                str(item.code) for item in getattr(detection, "findings", ())
            ],
            "cited_values": dict(
                getattr(analysis.decision, "cited_values", {}) or {}
            ),
            "judge_agreement": bool(analysis.verdict.agreement),
        }
        return {key: value for key, value in values.items() if value is not None}

    def observe(self, analysis: Analysis) -> dict[str, Any] | None:
        """Observe une condition et ne modifie que sa propre clé fonctionnelle.

        Une analyse sans ``finding`` ne possède pas la preuve permettant de
        résoudre une alarme : elle est donc volontairement sans effet.
        """
        timestamp = str(analysis.detection.timestamp)
        key = self._key(analysis)
        if key is None:
            return None
        accepted_alarm = (
            analysis.decision.severity in {"WARNING", "CRITICAL"}
            and analysis.verdict.agreement
        )
        evidence = self._evidence(analysis)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row = self._db.execute(
                    "SELECT * FROM alarms WHERE alarm_key=? AND status!='CLOSED' "
                    "ORDER BY id DESC LIMIT 1",
                    (key,),
                ).fetchone()
                result = (
                    self._raise_or_repeat(
                        row, analysis, key, timestamp, evidence
                    )
                    if accepted_alarm
                    else self._return_matching_to_normal(
                        row, timestamp, evidence
                    )
                )
                self._db.commit()
                return result
            except Exception:
                self._db.rollback()
                raise

    def _raise_or_repeat(
        self,
        row: sqlite3.Row | None,
        analysis: Analysis,
        key: str,
        timestamp: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        now = self._now()
        mode = next(iter(analysis.decision.amdec_modes), None)
        action = analysis.decision.recommended_action
        if row is None:
            cursor = self._db.execute(
                """
                INSERT INTO alarms(
                    alarm_uid,alarm_key,equipment_id,failure_mode,trigger_rule,
                    first_seen,last_seen,severity,diagnosis,action,procedure_ref,
                    status,occurrence_count,evidence_json,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,'ACTIVE',1,?,?)
                """,
                (
                    str(uuid.uuid4()),
                    key,
                    self._equipment(analysis),
                    mode,
                    self._trigger(analysis),
                    timestamp,
                    timestamp,
                    analysis.decision.severity,
                    analysis.decision.diagnosis,
                    action.description,
                    mode,
                    json.dumps(evidence, ensure_ascii=False, sort_keys=True),
                    now,
                ),
            )
            alarm_id = int(cursor.lastrowid)
            self._history(
                alarm_id, "system", None, "ACTIVE", "APPEARED", None, evidence
            )
            return self.get(alarm_id)

        old_status = str(row["status"])
        target = "ACTIVE" if old_status == "RETURNED_NORMAL" else old_status
        severity = (
            "CRITICAL"
            if "CRITICAL" in {row["severity"], analysis.decision.severity}
            else "WARNING"
        )
        self._db.execute(
            """
            UPDATE alarms
            SET last_seen=?, severity=?, diagnosis=?, action=?, procedure_ref=?,
                failure_mode=?, status=?, returned_at=NULL,
                occurrence_count=occurrence_count+1, evidence_json=?, updated_at=?
            WHERE id=?
            """,
            (
                timestamp,
                severity,
                analysis.decision.diagnosis,
                action.description,
                mode,
                mode,
                target,
                json.dumps(evidence, ensure_ascii=False, sort_keys=True),
                now,
                row["id"],
            ),
        )
        transition = "REACTIVATED" if old_status == "RETURNED_NORMAL" else "REPEATED"
        self._history(
            row["id"], "system", old_status, target, transition, None, evidence
        )
        return self.get(row["id"])

    def _return_matching_to_normal(
        self,
        row: sqlite3.Row | None,
        timestamp: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any] | None:
        if row is None or row["status"] not in OPEN_STATES:
            return None
        if row["status"] == "SHELVED":
            # LE COMMENTAIRE DISAIT L'INVERSE DU CODE. Il affirmait que
            # « l'inhibition ne doit jamais masquer une resolution
            # automatique », et le code retournait immediatement sans rien
            # enregistrer : l'inhibition masquait donc exactement cela.
            #
            # Conserver l'etat SHELVED est le comportement correct — inhiber
            # sert precisement a figer une alarme le temps d'une intervention,
            # et une desinhibition doit rendre la main sur une alarme dont
            # l'etat n'a pas ete decide en son absence. Mais le retour aux
            # conditions normales est un FAIT, et il est desormais inscrit au
            # journal : sans lui, l'operateur qui desinhibe ne peut pas savoir
            # que la condition avait cesse entre-temps.
            self._history(
                row["id"],
                "system",
                "SHELVED",
                "SHELVED",
                "RETURN_TO_NORMAL_WHILE_SHELVED",
                None,
                evidence,
            )
            return None
        now = self._now()
        self._db.execute(
            """
            UPDATE alarms SET status='RETURNED_NORMAL', returned_at=?,
                return_evidence_json=?, updated_at=? WHERE id=?
            """,
            (
                timestamp,
                json.dumps(evidence, ensure_ascii=False, sort_keys=True),
                now,
                row["id"],
            ),
        )
        self._history(
            row["id"],
            "system",
            row["status"],
            "RETURNED_NORMAL",
            "RETURNED_NORMAL",
            None,
            evidence,
        )
        return self.get(row["id"])

    def transition(
        self,
        alarm_id: int,
        *,
        action: str,
        operator: str,
        comment: str = "",
    ) -> dict[str, Any]:
        """Applique une transition explicite et refuse toute transition invalide."""
        if action not in OPERATOR_TRANSITIONS:
            raise ValueError("Action d'alarme invalide")
        comment = comment.strip()
        if action == "shelve" and not comment:
            raise ValueError("Le motif d'inhibition est obligatoire")
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row = self._db.execute(
                    "SELECT * FROM alarms WHERE id=?", (alarm_id,)
                ).fetchone()
                if row is None:
                    raise KeyError(alarm_id)
                target = OPERATOR_TRANSITIONS[action].get(row["status"])
                if target is None:
                    raise ValueError(
                        f"Transition {action} interdite depuis {row['status']}"
                    )
                now = self._now()
                acknowledged_by = row["acknowledged_by"]
                acknowledged_at = row["acknowledged_at"]
                shelved_by = row["shelved_by"]
                shelved_at = row["shelved_at"]
                shelve_reason = row["shelve_reason"]
                closed_at = row["closed_at"]
                if action == "acknowledge":
                    acknowledged_by, acknowledged_at = operator, now
                elif action == "shelve":
                    shelved_by, shelved_at, shelve_reason = operator, now, comment
                elif action == "unshelve":
                    shelved_by, shelved_at, shelve_reason = None, None, None
                elif action == "close":
                    closed_at = now
                self._db.execute(
                    """
                    UPDATE alarms SET
                        status=?, owner=?, comment=?, updated_at=?,
                        acknowledged_by=?, acknowledged_at=?,
                        shelved_by=?, shelved_at=?, shelve_reason=?, closed_at=?
                    WHERE id=?
                    """,
                    (
                        target,
                        operator,
                        comment,
                        now,
                        acknowledged_by,
                        acknowledged_at,
                        shelved_by,
                        shelved_at,
                        shelve_reason,
                        closed_at,
                        alarm_id,
                    ),
                )
                # LA COLONNE `transition` RECEVAIT L'ETAT D'ARRIVEE, PAS
                # L'ACTION. Le journal enregistrait donc « ACTIVE » aussi bien
                # pour une desinhibition que pour une reapparition, et
                # « SHELVED » sans dire qui avait demande l'inhibition ni au
                # titre de quelle action. Les transitions systeme, elles,
                # inscrivaient bien APPEARED / REPEATED / REACTIVATED /
                # RETURNED_NORMAL : seules les actions OPERATEUR — les seules
                # imputables a une personne — perdaient leur cause.
                self._history(
                    alarm_id,
                    operator,
                    row["status"],
                    target,
                    OPERATOR_TRANSITION_LABELS[action],
                    comment,
                    {},
                )
                self._db.commit()
                return self.get(alarm_id)
            except Exception:
                self._db.rollback()
                raise

    def _history(
        self,
        alarm_id: int,
        actor: str,
        from_status: str | None,
        to_status: str,
        transition: str,
        comment: str | None,
        evidence: dict[str, Any],
    ) -> None:
        self._db.execute(
            """
            INSERT INTO alarm_history(
                alarm_id,changed_at,actor,from_status,to_status,transition,
                comment,evidence_json
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                alarm_id,
                self._now(),
                actor,
                from_status,
                to_status,
                transition,
                comment,
                json.dumps(evidence, ensure_ascii=False, sort_keys=True),
            ),
        )

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        for name in ("evidence_json", "return_evidence_json"):
            raw = result.pop(name, None)
            result[name.removesuffix("_json")] = json.loads(raw) if raw else None
        return result

    def get(self, alarm_id: int) -> dict[str, Any]:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM alarms WHERE id=?", (alarm_id,)
            ).fetchone()
            if row is None:
                raise KeyError(alarm_id)
            result = self._decode(row)
            history = []
            for item in self._db.execute(
                "SELECT changed_at,actor,from_status,to_status,transition,comment,"
                "evidence_json FROM alarm_history WHERE alarm_id=? ORDER BY id",
                (alarm_id,),
            ).fetchall():
                decoded = dict(item)
                decoded["evidence"] = json.loads(decoded.pop("evidence_json") or "{}")
                history.append(decoded)
            result["history"] = history
            return result

    def list(self, *, active_only: bool = False, limit: int = 100) -> list[dict[str, Any]]:
        query = "SELECT * FROM alarms"
        if active_only:
            query += " WHERE status IN ('ACTIVE','ACKNOWLEDGED','SHELVED')"
        query += " ORDER BY last_seen DESC, id DESC LIMIT ?"
        with self._lock:
            rows = self._db.execute(
                query, (max(1, min(limit, 500)),)
            ).fetchall()
            return [self._decode(row) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._db.close()
