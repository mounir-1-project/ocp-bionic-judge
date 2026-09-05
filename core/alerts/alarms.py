"""Registre en memoire du cycle de vie des alarmes E7301.

Meme API que la version SQLite, mais stockee dans un dictionnaire.
Suffisant pour un projet de demonstration personnelle.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from core.pipeline import Analysis

UTC = timezone.utc

OPEN_STATES = ("ACTIVE", "ACKNOWLEDGED", "SHELVED")
VALID_STATES = (*OPEN_STATES, "RETURNED_NORMAL", "CLOSED")
OPERATOR_TRANSITIONS: dict[str, dict[str, str]] = {
    "acknowledge": {"ACTIVE": "ACKNOWLEDGED"},
    "shelve": {"ACTIVE": "SHELVED", "ACKNOWLEDGED": "SHELVED"},
    "unshelve": {"SHELVED": "ACTIVE"},
    "close": {"RETURNED_NORMAL": "CLOSED"},
}
OPERATOR_TRANSITION_LABELS: dict[str, str] = {
    "acknowledge": "ACKNOWLEDGED_BY_OPERATOR",
    "shelve": "SHELVED_BY_OPERATOR",
    "unshelve": "UNSHELVED_BY_OPERATOR",
    "close": "CLOSED_BY_OPERATOR",
}


class AlarmStore:
    """Stocke les alarmes en memoire (dict)."""

    def __init__(self) -> None:
        self._alarms: dict[int, dict[str, Any]] = {}
        self._history: dict[int, list[dict[str, Any]]] = {}
        self._next_id = 1

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _equipment(analysis: Analysis) -> str:
        return str(getattr(analysis.decision, "equipment_id", "S-PC-E7301"))

    @staticmethod
    def _trigger(analysis: Analysis) -> str | None:
        """Constatation dominante qui identifie l'alarme."""
        findings = list(getattr(analysis.detection, "findings", ()) or [])
        if not findings:
            return None
        lead = getattr(analysis.decision, "lead_finding", None)
        if lead is not None:
            return str(lead)
        return str(findings[0].code)

    @classmethod
    def _key(cls, analysis: Analysis) -> str | None:
        """Cle stable : equipement et signal declencheur."""
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
        """Observe une condition et met a jour l'alarme correspondante."""
        timestamp = str(analysis.detection.timestamp)
        key = self._key(analysis)
        if key is None:
            return None

        condition_presente = analysis.decision.severity in {"WARNING", "CRITICAL"}
        accepted_alarm = condition_presente and analysis.verdict.agreement
        evidence = self._evidence(analysis)

        # Chercher une alarme existante avec cette cle
        existing = None
        for alarm in self._alarms.values():
            if alarm["alarm_key"] == key and alarm["status"] != "CLOSED":
                existing = alarm
                break

        if accepted_alarm:
            return self._raise_or_repeat(existing, analysis, key, timestamp, evidence)
        elif condition_presente:
            return None  # Contestee par le Judge
        else:
            return self._return_to_normal(existing, timestamp, evidence)

    def _raise_or_repeat(
        self,
        existing: dict[str, Any] | None,
        analysis: Analysis,
        key: str,
        timestamp: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        now = self._now()
        mode = next(iter(analysis.decision.amdec_modes), None)
        action = analysis.decision.recommended_action

        if existing is None:
            # Nouvelle alarme
            alarm_id = self._next_id
            self._next_id += 1
            alarm = {
                "id": alarm_id,
                "alarm_uid": str(uuid.uuid4()),
                "alarm_key": key,
                "equipment_id": self._equipment(analysis),
                "failure_mode": mode,
                "trigger_rule": self._trigger(analysis),
                "first_seen": timestamp,
                "last_seen": timestamp,
                "returned_at": None,
                "closed_at": None,
                "severity": analysis.decision.severity,
                "diagnosis": analysis.decision.diagnosis,
                "action": action.description,
                "procedure_ref": mode,
                "status": "ACTIVE",
                "occurrence_count": 1,
                "owner": None,
                "comment": None,
                "acknowledged_by": None,
                "acknowledged_at": None,
                "shelved_by": None,
                "shelved_at": None,
                "shelve_reason": None,
                "evidence": evidence,
                "return_evidence": None,
                "updated_at": now,
            }
            self._alarms[alarm_id] = alarm
            self._history[alarm_id] = []
            self._add_history(alarm_id, "system", None, "ACTIVE", "APPEARED", None, evidence)
            return self.get(alarm_id)

        # Alarme existante — mise a jour
        old_status = existing["status"]
        target = "ACTIVE" if old_status == "RETURNED_NORMAL" else old_status
        severity = (
            "CRITICAL"
            if "CRITICAL" in {existing["severity"], analysis.decision.severity}
            else "WARNING"
        )
        existing["last_seen"] = timestamp
        existing["severity"] = severity
        existing["diagnosis"] = analysis.decision.diagnosis
        existing["action"] = action.description
        existing["failure_mode"] = mode
        existing["procedure_ref"] = mode
        existing["status"] = target
        existing["returned_at"] = None
        existing["occurrence_count"] += 1
        existing["evidence"] = evidence
        existing["updated_at"] = now

        transition = "REACTIVATED" if old_status == "RETURNED_NORMAL" else "REPEATED"
        self._add_history(existing["id"], "system", old_status, target, transition, None, evidence)
        return self.get(existing["id"])

    def _return_to_normal(
        self,
        existing: dict[str, Any] | None,
        timestamp: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any] | None:
        if existing is None or existing["status"] not in OPEN_STATES:
            return None
        if existing["status"] == "SHELVED":
            self._add_history(
                existing["id"], "system", "SHELVED", "SHELVED",
                "RETURN_TO_NORMAL_WHILE_SHELVED", None, evidence,
            )
            return None

        now = self._now()
        old_status = existing["status"]
        existing["status"] = "RETURNED_NORMAL"
        existing["returned_at"] = timestamp
        existing["return_evidence"] = evidence
        existing["updated_at"] = now
        self._add_history(existing["id"], "system", old_status, "RETURNED_NORMAL", "RETURNED_NORMAL", None, evidence)
        return self.get(existing["id"])

    def transition(
        self,
        alarm_id: int,
        *,
        action: str,
        operator: str,
        comment: str = "",
    ) -> dict[str, Any]:
        """Applique une transition d'operateur."""
        if action not in OPERATOR_TRANSITIONS:
            raise ValueError("Action d'alarme invalide")
        comment = comment.strip()
        if action == "shelve" and not comment:
            raise ValueError("Le motif d'inhibition est obligatoire")

        alarm = self._alarms.get(alarm_id)
        if alarm is None:
            raise KeyError(alarm_id)

        target = OPERATOR_TRANSITIONS[action].get(alarm["status"])
        if target is None:
            raise ValueError(f"Transition {action} interdite depuis {alarm['status']}")

        now = self._now()
        old_status = alarm["status"]

        if action == "acknowledge":
            alarm["acknowledged_by"] = operator
            alarm["acknowledged_at"] = now
        elif action == "shelve":
            alarm["shelved_by"] = operator
            alarm["shelved_at"] = now
            alarm["shelve_reason"] = comment
        elif action == "unshelve":
            alarm["shelved_by"] = None
            alarm["shelved_at"] = None
            alarm["shelve_reason"] = None
        elif action == "close":
            alarm["closed_at"] = now

        alarm["status"] = target
        alarm["owner"] = operator
        alarm["comment"] = comment
        alarm["updated_at"] = now

        self._add_history(alarm_id, operator, old_status, target, OPERATOR_TRANSITION_LABELS[action], comment, {})
        return self.get(alarm_id)

    def _add_history(
        self,
        alarm_id: int,
        actor: str,
        from_status: str | None,
        to_status: str,
        transition: str,
        comment: str | None,
        evidence: dict[str, Any],
    ) -> None:
        if alarm_id not in self._history:
            self._history[alarm_id] = []
        self._history[alarm_id].append({
            "changed_at": self._now(),
            "actor": actor,
            "from_status": from_status,
            "to_status": to_status,
            "transition": transition,
            "comment": comment,
            "evidence": evidence,
        })

    def get(self, alarm_id: int) -> dict[str, Any]:
        alarm = self._alarms.get(alarm_id)
        if alarm is None:
            raise KeyError(alarm_id)
        result = dict(alarm)
        result["history"] = list(self._history.get(alarm_id, []))
        return result

    def list(self, *, active_only: bool = False, limit: int = 100) -> list[dict[str, Any]]:
        alarms = list(self._alarms.values())
        if active_only:
            alarms = [a for a in alarms if a["status"] in ("ACTIVE", "ACKNOWLEDGED", "SHELVED")]
        alarms.sort(key=lambda a: (a["last_seen"], a["id"]), reverse=True)
        return alarms[:max(1, min(limit, 500))]

    def close(self) -> None:
        """Rien a fermer en memoire."""
        pass
