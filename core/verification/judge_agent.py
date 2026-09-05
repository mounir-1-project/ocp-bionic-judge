"""
Judge Agent — contrôleur deterministe de coherence des decisions.

Le contrôleur recalcule les faits depuis la même chaine de données et de règles,
puis confronte chaque affirmation de l'agent a ces faits. Huit controles
independants et deterministes.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, ClassVar

import numpy as np
import pandas as pd
from loguru import logger

from core.detection.schemas import (
    CONFIANCE_MAX,
    EXECUTION_WINDOW_LABEL,
    MIN_URGENCY_FOR_SEVERITY,
    URGENCY_HOURS,
    AgentDecision,
    Check,
    JudgeVerdict,
    confiance_justifiable,
)
from core.knowledge.knowledge import DomainKnowledge, load_domain
from core.formatting import nombre, sans_accents
from core.detection.detector import SEVERITY_ORDER, CoolerAnomalyDetector, DetectionResult

# Seuil de validation. En dessous, le Judge est en desaccord.
AGREEMENT_THRESHOLD = 6.0

# Tolerances pour la verification des valeurs
VALUE_REL_TOL = 0.01
VALUE_ABS_TOL = 0.05
TEXT_REL_TOL = 0.02
TEXT_ABS_TOL = 0.15
TEXT_MIN_MAGNITUDE = 10.0

# Piece portant les grandeurs de performance
PERFORMANCE_COMPONENT = "BUNDLE"


# ── Etage 1 : verification factuelle ──────────────────────────────────────────

@dataclass
class VerifiedFacts:
    """Faits recalcules par le Judge, independamment de l'agent.

    Attributes:
        timestamp: Instant concerne.
        process_state: Etat de marche reel.
        measurements: Mesures reelles a cet instant.
        rule_severity: Severite obtenue en rejouant le moteur de regles.
        rule_codes: Codes des constatations reelles.
        amdec_modes: Modes AMDEC reellement invoques par les faits.
        anomaly_score: Score reel du modele.
        model_applicable: Le modele etait-il applicable ?
        n_invalid_tags: Nombre de points de mesure en defaut.
        legitimate_numbers: Univers des nombres qu'un diagnostic a le droit de citer.
    """

    timestamp: str
    process_state: str
    measurements: dict[str, float]
    rule_severity: str
    rule_codes: list[str]
    amdec_modes: list[str]
    anomaly_score: float
    model_applicable: bool
    n_invalid_tags: int
    legitimate_numbers: set[float] = field(default_factory=set)

    @classmethod
    def from_detection(
        cls, result: DetectionResult, domain: DomainKnowledge
    ) -> VerifiedFacts:
        """Construit les faits verifies a partir d'une detection recalculee."""
        legit: set[float] = set()

        def _add(v: Any) -> None:
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                with contextlib.suppress(TypeError, ValueError):
                    legit.add(round(float(v), 3))

        for v in result.measurements.values():
            _add(v)
        for f in result.findings:
            for v in (f.evidence or {}).values():
                _add(v)
        for a in result.attributions:
            _add(a.get("value"))
            _add(a.get("reference"))
            _add(a.get("contribution"))
        _add(result.anomaly_score)

        for tag in domain.tags.values():
            for key in ("alarm_low_low", "alarm_low", "alarm_high", "alarm_high_high"):
                _add(tag.threshold(key))
            _add(tag.setpoint)
            _add(tag.saturation_value)
            for rng in (tag.range_operating, tag.range_physical, tag.control_band):
                if rng:
                    _add(rng[0])
                    _add(rng[1])
        for m in domain.modes.values():
            _add(m.C)
            _add(m.F)
            _add(m.G)
            _add(m.N)

        return cls(
            timestamp=result.timestamp,
            process_state=result.process_state,
            measurements=dict(result.measurements),
            rule_severity=result.severity,
            rule_codes=[f.code for f in result.findings],
            amdec_modes=result.amdec_modes,
            anomaly_score=result.anomaly_score,
            model_applicable=bool(result.data_quality.get("model_applicable")),
            n_invalid_tags=int(result.data_quality.get("n_invalid_tags", 0)),
            legitimate_numbers=legit,
        )

    def to_dict(self) -> dict[str, Any]:
        """Representation serialisable."""
        return {
            "timestamp": self.timestamp,
            "process_state": self.process_state,
            "measurements": self.measurements,
            "rule_severity": self.rule_severity,
            "rule_codes": self.rule_codes,
            "amdec_modes": self.amdec_modes,
            "anomaly_score": self.anomaly_score,
            "model_applicable": self.model_applicable,
            "n_invalid_tags": self.n_invalid_tags,
        }


class VerificationLayer:
    """Les huit controles factuels du Judge.

    Chaque controle repond a une question qu'un ingenieur poserait en relisant
    le rapport d'un collegue, et y repond avec des chiffres, pas une opinion.
    """

    WEIGHTS: ClassVar[dict[str, float]] = {
        "V1_NUMERIC_FIDELITY":   0.22,
        "V2_SEVERITY":           0.16,
        "V3_AMDEC_GROUNDING":    0.14,
        "V4_ACTION_CONFORMITY":  0.14,
        "V5_CONFIDENCE":         0.15,
        "V6_STATE_AWARENESS":    0.08,
        "V7_EVIDENCE_COVERAGE":  0.05,
        "V8_UNCERTAINTY":        0.06,
    }

    def __init__(self, domain: DomainKnowledge) -> None:
        self.domain = domain

    def run(self, decision: AgentDecision, facts: VerifiedFacts) -> list[Check]:
        """Execute les huit controles."""
        return [
            self._v1_numeric_fidelity(decision, facts),
            self._v2_severity(decision, facts),
            self._v3_amdec_grounding(decision, facts),
            self._v4_action_conformity(decision, facts),
            self._v5_confidence(decision, facts),
            self._v6_state_awareness(decision, facts),
            self._v7_evidence_coverage(decision, facts),
            self._v8_uncertainty(decision, facts),
        ]

    def _v1_numeric_fidelity(self, d: AgentDecision, f: VerifiedFacts) -> Check:
        """Chaque valeur citee correspond-elle a la mesure reelle ?"""
        wrong: list[str] = []
        checked = 0
        for name, claimed in (d.cited_values or {}).items():
            actual = f.measurements.get(name)
            if actual is None:
                continue
            checked += 1
            tol = max(abs(actual) * VALUE_REL_TOL, VALUE_ABS_TOL)
            if abs(float(claimed) - float(actual)) > tol:
                wrong.append(f"{name} : annoncé {nombre(claimed, 2)}, mesuré {nombre(actual, 2)}")

        known = set(f.legitimate_numbers or set())
        known |= {round(float(v), 3) for v in (d.cited_values or {}).values()}
        unmatched = [
            n for n in _extract_numbers(d.diagnosis)
            if abs(n) >= TEXT_MIN_MAGNITUDE
            and not any(
                abs(n - k) <= max(abs(k) * TEXT_REL_TOL, TEXT_ABS_TOL) for k in known
            )
        ]

        if wrong:
            return Check(
                id="V1_NUMERIC_FIDELITY",
                label="Les valeurs citées correspondent-elles aux mesures réelles ?",
                passed=False, weight=self.WEIGHTS["V1_NUMERIC_FIDELITY"], score=0.0,
                detail=f"{len(wrong)} valeur(s) fausse(s) sur {checked} vérifiée(s) : "
                       + " ; ".join(wrong[:4]),
                issue_codes=["HALLUCINATED_VALUE"],
            )
        if unmatched:
            return Check(
                id="V1_NUMERIC_FIDELITY",
                label="Les valeurs citées correspondent-elles aux mesures réelles ?",
                passed=False, weight=self.WEIGHTS["V1_NUMERIC_FIDELITY"], score=5.0,
                detail=f"{checked} valeur(s) déclarée(s) exacte(s), mais le texte contient "
                       f"des nombres non rattachables aux mesures : "
                       f"{', '.join(nombre(n, 2) for n in unmatched[:4])}.",
                issue_codes=["UNVERIFIABLE_VALUE"],
            )
        if checked == 0:
            return Check(
                id="V1_NUMERIC_FIDELITY",
                label="Les valeurs citées correspondent-elles aux mesures réelles ?",
                passed=False, weight=self.WEIGHTS["V1_NUMERIC_FIDELITY"], score=1.5,
                detail="Aucune valeur mesurée n'est citée : le diagnostic n'est pas "
                       "rattachable aux données et ne peut pas être vérifié.",
                issue_codes=["NO_QUANTITATIVE_EVIDENCE"],
            )
        return Check(
            id="V1_NUMERIC_FIDELITY",
            label="Les valeurs citées correspondent-elles aux mesures réelles ?",
            passed=True, weight=self.WEIGHTS["V1_NUMERIC_FIDELITY"], score=10.0,
            detail=f"{checked} valeur(s) confrontée(s) aux mesures recalculées, toutes exactes.",
        )

    def _v2_severity(self, d: AgentDecision, f: VerifiedFacts) -> Check:
        """La severite annoncee correspond-elle aux faits recalcules ?"""
        claimed = SEVERITY_ORDER.get(d.severity, 0)
        actual = SEVERITY_ORDER.get(f.rule_severity, 0)
        gap = claimed - actual

        if gap == 0:
            return Check(
                id="V2_SEVERITY", label="La sévérité correspond-elle aux faits ?",
                passed=True, weight=self.WEIGHTS["V2_SEVERITY"], score=10.0,
                detail=f"Sévérité {d.severity} conforme au recalcul interne des règles.",
            )
        if gap < 0:
            score = max(0.0, 6.0 + 3.0 * gap)
            return Check(
                id="V2_SEVERITY", label="La sévérité correspond-elle aux faits ?",
                passed=False, weight=self.WEIGHTS["V2_SEVERITY"], score=score,
                detail=f"Sévérité SOUS-ESTIMÉE : l'agent annonce {d.severity} alors que "
                       f"le recalcul donne {f.rule_severity} "
                       f"(constatations réelles : {', '.join(f.rule_codes) or 'aucune'}).",
                issue_codes=["SEVERITY_UNDERESTIMATED"],
            )
        return Check(
            id="V2_SEVERITY", label="La sévérité correspond-elle aux faits ?",
            passed=False, weight=self.WEIGHTS["V2_SEVERITY"], score=max(4.0, 8.0 - 2.0 * gap),
            detail=f"Sévérité SUR-ESTIMÉE : l'agent annonce {d.severity} contre "
                   f"{f.rule_severity} au recalcul.",
            issue_codes=["SEVERITY_OVERESTIMATED"],
        )

    def _v3_amdec_grounding(self, d: AgentDecision, f: VerifiedFacts) -> Check:
        """Les modes AMDEC invoques existent-ils et sont-ils detectables ?"""
        if not d.amdec_modes:
            if f.amdec_modes:
                return Check(
                    id="V3_AMDEC_GROUNDING", label="Les modes AMDEC invoqués sont-ils fondés ?",
                    passed=False, weight=self.WEIGHTS["V3_AMDEC_GROUNDING"], score=4.0,
                    detail=f"Aucun mode AMDEC rattache alors que les faits en designent "
                           f"{', '.join(f.amdec_modes)}.",
                    issue_codes=["NO_AMDEC_LINK"],
                )
            return Check(
                id="V3_AMDEC_GROUNDING", label="Les modes AMDEC invoqués sont-ils fondés ?",
                passed=True, weight=self.WEIGHTS["V3_AMDEC_GROUNDING"], score=10.0,
                detail="Aucun mode invoqué, aucun mode attendu — cohérent.",
            )

        unknown = [m for m in d.amdec_modes if m not in self.domain.modes]
        if unknown:
            return Check(
                id="V3_AMDEC_GROUNDING", label="Les modes AMDEC invoqués sont-ils fondés ?",
                passed=False, weight=self.WEIGHTS["V3_AMDEC_GROUNDING"], score=0.0,
                detail=f"Mode(s) inexistant(s) dans l'AMDEC : {', '.join(unknown)}.",
                issue_codes=["INVENTED_AMDEC_MODE"],
            )

        blind = [
            m for m in d.amdec_modes
            if self.domain.modes[m].observabilite == "none"
        ]
        if blind:
            return Check(
                id="V3_AMDEC_GROUNDING", label="Les modes AMDEC invoqués sont-ils fondés ?",
                passed=False, weight=self.WEIGHTS["V3_AMDEC_GROUNDING"], score=1.0,
                detail=f"Mode(s) NON détectable(s) : {', '.join(blind)}.",
                issue_codes=["BLIND_SPOT_CLAIM"],
            )

        unsupported = [m for m in d.amdec_modes if m not in f.amdec_modes]
        if unsupported:
            return Check(
                id="V3_AMDEC_GROUNDING", label="Les modes AMDEC invoqués sont-ils fondés ?",
                passed=False, weight=self.WEIGHTS["V3_AMDEC_GROUNDING"], score=5.0,
                detail=f"Mode(s) invoqué(s) sans constatation : {', '.join(unsupported)}.",
                issue_codes=["UNSUPPORTED_AMDEC_MODE"],
            )
        return Check(
            id="V3_AMDEC_GROUNDING", label="Les modes AMDEC invoqués sont-ils fondés ?",
            passed=True, weight=self.WEIGHTS["V3_AMDEC_GROUNDING"], score=10.0,
            detail=f"Mode(s) {', '.join(d.amdec_modes)} : existant(s) et soutenu(s) par les faits.",
        )

    def _v4_action_conformity(self, d: AgentDecision, f: VerifiedFacts) -> Check:
        """L'action est-elle proportionnee et executable ?"""
        action = d.recommended_action
        problems: list[str] = []
        issues: list[str] = []
        score = 10.0

        need = MIN_URGENCY_FOR_SEVERITY.get(d.severity, "SOUS_SURVEILLANCE")
        if URGENCY_HOURS[action.urgency] > URGENCY_HOURS[need]:
            problems.append(f"délai insuffisant : urgence '{action.urgency}' pour sévérité {d.severity}")
            issues.append("ACTION_UNDERSIZED")
            score = min(score, 3.0)

        if action.maintenance_task_ref:
            needs_stop = self.domain.task_requires_shutdown(action.maintenance_task_ref)
        else:
            needs_stop = any(
                self.domain.task_requires_shutdown(ref)
                for code in d.amdec_modes
                if (mode := self.domain.modes.get(code)) is not None
                for ref in mode.plan_maintenance_ref
            )
        text = f"{action.description}".lower()
        mentions_stop = action.requires_shutdown or any(
            k in text for k in ("arret", "arrêt", "consign", "isoler", "vidang")
        )
        if needs_stop and not mentions_stop:
            problems.append("l'intervention exige un arrêt process non mentionné")
            issues.append("UNSAFE_ACTION")
            score = min(score, 1.0)

        if needs_stop and action.execution_window == "EN_MARCHE":
            problems.append("l'action est annoncée réalisable en marche alors qu'un arrêt est requis")
            issues.append("UNSAFE_ACTION")
            score = min(score, 1.0)
        if not needs_stop and action.execution_window != "EN_MARCHE":
            problems.append("l'action réclame un arrêt non requis par le plan préventif")
            issues.append("ACTION_OVERSIZED")
            score = min(score, 4.0)

        if d.severity in ("WARNING", "CRITICAL") and len(action.description.strip()) < 25:
            problems.append("action trop vague pour être exécutée")
            issues.append("VAGUE_ACTION")
            score = min(score, 4.0)

        if action.maintenance_task_ref and action.maintenance_task_ref not in self.domain.plan_maintenance:
            problems.append(f"tâche '{action.maintenance_task_ref}' absente du plan de maintenance")
            issues.append("INVALID_TASK_REF")
            score = min(score, 5.0)

        if problems:
            return Check(
                id="V4_ACTION_CONFORMITY",
                label="L'action est-elle proportionnée, conforme et exécutable ?",
                passed=False, weight=self.WEIGHTS["V4_ACTION_CONFORMITY"], score=score,
                detail="; ".join(problems).capitalize() + ".",
                issue_codes=issues,
            )
        return Check(
            id="V4_ACTION_CONFORMITY",
            label="L'action est-elle proportionnée, conforme et exécutable ?",
            passed=True, weight=self.WEIGHTS["V4_ACTION_CONFORMITY"], score=10.0,
            detail=f"Action proportionnée, fenêtre {EXECUTION_WINDOW_LABEL[action.execution_window]}.",
        )

    def _v5_confidence(self, d: AgentDecision, f: VerifiedFacts) -> Check:
        """La confiance affichee reflete-t-elle la force reelle des preuves ?"""
        modes = [self.domain.modes[m] for m in d.amdec_modes if m in self.domain.modes]
        observabilite = min(
            (m.observabilite for m in modes),
            key=lambda o: {"none": 0, "partial": 1, "full": 2}[o],
            default="full",
        )
        expected = confiance_justifiable(
            rule_codes=f.rule_codes,
            model_applicable=f.model_applicable,
            n_invalid_tags=f.n_invalid_tags,
            process_state=f.process_state,
            mode_observabilite=observabilite,
        )

        gap = d.confidence - expected

        if d.confidence > CONFIANCE_MAX:
            return Check(
                id="V5_CONFIDENCE", label="La confiance est-elle calibrée sur les preuves ?",
                passed=False, weight=self.WEIGHTS["V5_CONFIDENCE"],
                score=max(0.0, 5.0 - 20.0 * (d.confidence - CONFIANCE_MAX)),
                detail=f"Sur-confiance : {nombre(d.confidence, 2)} annoncé alors que le barème "
                       f"plafonne à {nombre(CONFIANCE_MAX, 2)}.",
                issue_codes=["OVERCONFIDENCE"],
            )
        if gap > 0.12:
            return Check(
                id="V5_CONFIDENCE", label="La confiance est-elle calibrée sur les preuves ?",
                passed=False, weight=self.WEIGHTS["V5_CONFIDENCE"],
                score=max(0.0, 5.0 - 20.0 * (gap - 0.12)),
                detail=f"Sur-confiance : {nombre(d.confidence, 2)} annoncé contre {nombre(expected, 2)} "
                       f"justifiable.",
                issue_codes=["OVERCONFIDENCE"],
            )
        if gap < -0.30:
            return Check(
                id="V5_CONFIDENCE", label="La confiance est-elle calibrée sur les preuves ?",
                passed=False, weight=self.WEIGHTS["V5_CONFIDENCE"], score=6.0,
                detail=f"Sous-confiance : {nombre(d.confidence, 2)} annoncé contre {nombre(expected, 2)} "
                       f"justifiable.",
                issue_codes=["UNDERCONFIDENCE"],
            )
        return Check(
            id="V5_CONFIDENCE", label="La confiance est-elle calibrée sur les preuves ?",
            passed=True, weight=self.WEIGHTS["V5_CONFIDENCE"],
            score=round(10.0 - 8.0 * abs(gap), 2),
            detail=f"Confiance {nombre(d.confidence, 2)} cohérente avec les {nombre(expected, 2)} justifiables.",
        )

    def _v6_state_awareness(self, d: AgentDecision, f: VerifiedFacts) -> Check:
        """L'agent respecte-t-il l'etat de marche reel ?"""
        if d.process_state != f.process_state:
            return Check(
                id="V6_STATE_AWARENESS", label="L'état de marche est-il respecté ?",
                passed=False, weight=self.WEIGHTS["V6_STATE_AWARENESS"], score=0.0,
                detail=f"État annoncé '{d.process_state}' contre '{f.process_state}' réel.",
                issue_codes=["STATE_MISMATCH"],
            )
        if f.process_state != "RUNNING":
            perf_modes = self.domain.modes_for_component(PERFORMANCE_COMPONENT)
            if set(d.amdec_modes) & perf_modes or d.severity in ("WARNING", "CRITICAL"):
                return Check(
                    id="V6_STATE_AWARENESS", label="L'état de marche est-il respecté ?",
                    passed=False, weight=self.WEIGHTS["V6_STATE_AWARENESS"], score=1.0,
                    detail=f"Diagnostic de dégradation formulé alors que la ligne est "
                           f"en état {f.process_state}.",
                    issue_codes=["DIAGNOSIS_OUT_OF_STATE"],
                )
        return Check(
            id="V6_STATE_AWARENESS", label="L'état de marche est-il respecté ?",
            passed=True, weight=self.WEIGHTS["V6_STATE_AWARENESS"], score=10.0,
            detail=f"État {f.process_state} correctement pris en compte.",
        )

    def _v7_evidence_coverage(self, d: AgentDecision, f: VerifiedFacts) -> Check:
        """La constatation la plus grave est-elle traitee ?"""
        if not f.rule_codes:
            return Check(
                id="V7_EVIDENCE_COVERAGE", label="Le fait le plus grave est-il traité ?",
                passed=True, weight=self.WEIGHTS["V7_EVIDENCE_COVERAGE"], score=10.0,
                detail="Aucune constatation à couvrir.",
            )
        covered = set(d.evidence_refs or [])
        missing = [c for c in f.rule_codes if c not in covered]
        ratio = 1.0 - len(missing) / len(f.rule_codes)
        if missing:
            return Check(
                id="V7_EVIDENCE_COVERAGE", label="Le fait le plus grave est-il traité ?",
                passed=False, weight=self.WEIGHTS["V7_EVIDENCE_COVERAGE"],
                score=round(10.0 * ratio, 2),
                detail=f"Constatation(s) non reprise(s) : {', '.join(missing[:4])}.",
                issue_codes=["INCOMPLETE_COVERAGE"],
            )
        return Check(
            id="V7_EVIDENCE_COVERAGE", label="Le fait le plus grave est-il traité ?",
            passed=True, weight=self.WEIGHTS["V7_EVIDENCE_COVERAGE"], score=10.0,
            detail=f"Les {len(f.rule_codes)} constatation(s) sont reprises.",
        )

    def _v8_uncertainty(self, d: AgentDecision, f: VerifiedFacts) -> Check:
        """Les limites du diagnostic sont-elles enoncees ?"""
        needs_caveat = f.n_invalid_tags > 0 or not f.model_applicable
        text = sans_accents(d.diagnosis + " " + d.reasoning)
        has_caveat = any(k in text for k in (
            "reserve", "defaut", "degrade", "non applicable", "pas applicable",
            "inapplicable", "confirmer", "a valider", "incertitude",
            "prelevement", "verifier", "suspect", "manquant",
        ))
        if needs_caveat and not has_caveat:
            return Check(
                id="V8_UNCERTAINTY", label="Les limites du diagnostic sont-elles énoncées ?",
                passed=False, weight=self.WEIGHTS["V8_UNCERTAINTY"], score=3.0,
                detail=f"Aucune réserve énoncée alors que {f.n_invalid_tags} point(s) de "
                       f"mesure sont en défaut.",
                issue_codes=["MISSING_CAVEAT"],
            )
        return Check(
            id="V8_UNCERTAINTY", label="Les limites du diagnostic sont-elles énoncées ?",
            passed=True, weight=self.WEIGHTS["V8_UNCERTAINTY"], score=10.0,
            detail="Réserves énoncées à bon escient." if needs_caveat
                   else "Aucune réserve nécessaire.",
        )


# ── Judge ─────────────────────────────────────────────────────────────────────

LLM_CORRIDOR = 1.5

JUDGE_SYSTEM = """Tu es le Judge du systeme de surveillance du refroidisseur E7301.
Tu es un contrôleur de cohérence, pas un validateur terrain.

Tu as deux missions :
1. AJUSTER la note dans un corridor de +/- {corridor} points pour des motifs
   que la verification automatique ne sait pas evaluer.
2. REDIGER une synthese de 2 a 4 phrases.

Interdictions :
- inventer un fait qui ne figure pas dans les faits verifies
- remonter la note d'une decision dont un controle de securite a echoue

## SORTIE
JSON valide uniquement :
{{
  "score_adjustment": <float entre -{corridor} et +{corridor}>,
  "adjustment_reason": "<motif en une phrase>",
  "feedback": "<2 a 4 phrases>"
}}
"""


def _try_build_llm():
    """Instancie le client Gemini si disponible."""
    try:
        from core.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_TIMEOUT_S
        if not GEMINI_API_KEY:
            return None
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            google_api_key=GEMINI_API_KEY,
            temperature=0.1,
            max_retries=0,
            timeout=GEMINI_TIMEOUT_S,
        )
    except ImportError:
        return None


class JudgeAgent:
    """Contrôleur hybride : verification logique puis redaction bornee.

    Attributes:
        domain: Connaissance domaine.
        detector: Detecteur utilise pour RECALCULER les faits.
        verifier: Couche des huit controles.
        llm: Client Gemini, ou None.
    """

    def __init__(
        self,
        detector: CoolerAnomalyDetector,
        domain: DomainKnowledge | None = None,
        use_llm: bool = True,
    ) -> None:
        self.domain = domain or load_domain()
        self.detector = detector
        self.verifier = VerificationLayer(self.domain)
        self.llm = _try_build_llm() if use_llm else None
        self._audit_enabled = True
        self._facts_cache: dict[tuple[str, tuple], VerifiedFacts] = {}
        logger.info(f"Judge initialise — mode {'hybride' if self.llm else 'deterministe'}")

    @property
    def mode(self) -> str:
        return "hybrid" if self.llm else "deterministic"

    @contextmanager
    def suspended_audit(self) -> Iterator[None]:
        """Suspend l'auto-surveillance le temps d'un banc de test."""
        previous = self._audit_enabled
        self._audit_enabled = False
        try:
            yield
        finally:
            self._audit_enabled = previous

    def _verified_facts(
        self,
        decision: AgentDecision,
        features: pd.DataFrame,
    ) -> VerifiedFacts:
        """Reconstruit les faits depuis les données, avec memoisation."""
        key = (decision.timestamp, self.detector._cache_key(features))
        facts = self._facts_cache.get(key)
        if facts is None:
            recomputed = self.detector.analyze(features, pd.Timestamp(decision.timestamp))
            facts = VerifiedFacts.from_detection(recomputed, self.domain)
            self._facts_cache[key] = facts
        return facts

    @staticmethod
    def _apply_safety_cap(
        score: float,
        issues: list[str],
        facts: VerifiedFacts,
    ) -> tuple[float, float | None]:
        """Applique les plafonds non compensables de securite."""
        blocking = {
            "UNSAFE_ACTION",
            "HALLUCINATED_VALUE",
            "INVENTED_AMDEC_MODE",
            "BLIND_SPOT_CLAIM",
        }
        if blocking.intersection(issues):
            return min(score, 4.0), 4.0
        if "STATE_MISMATCH" in issues:
            return min(score, 5.0), 5.0
        if "SEVERITY_UNDERESTIMATED" in issues and facts.rule_severity == "CRITICAL":
            return min(score, 4.0), 4.0
        return score, None

    def _review_with_llm(
        self,
        decision: AgentDecision,
        facts: VerifiedFacts,
        checks: list[Check],
        det_score: float,
        capped: float | None,
    ) -> tuple[float, float | None, str]:
        """Ajoute la couche redactionnelle LLM si disponible."""
        final = det_score
        llm_score: float | None = None
        feedback = _default_feedback(checks, facts, capped)
        if self.llm is None:
            return final, llm_score, feedback

        try:
            payload = {
                "decision": decision.model_dump(),
                "faits_verifies": facts.to_dict(),
                "controles": [c.model_dump() for c in checks],
                "note_deterministe": round(det_score, 2),
            }
            system = JUDGE_SYSTEM.format(corridor=LLM_CORRIDOR)
            user = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
            from langchain_core.messages import HumanMessage, SystemMessage
            raw = self.llm.invoke([SystemMessage(content=system), HumanMessage(content=user)]).content
            data = _extract_json(raw)

            adjustment = float(np.clip(
                float(data.get("score_adjustment", 0.0)),
                -LLM_CORRIDOR, LLM_CORRIDOR
            ))
            if capped is not None and adjustment > 0:
                adjustment = 0.0
            llm_score = round(min(10.0, max(0.0, det_score + adjustment)), 2)
            final = llm_score
            feedback = str(data.get("feedback", "")).strip() or feedback
        except Exception as exc:
            self.llm = None
            logger.warning(f"LLM du Judge indisponible ({type(exc).__name__})")
        return final, llm_score, feedback

    def judge(
        self,
        decision: AgentDecision,
        features: pd.DataFrame,
        use_llm: bool = True,
    ) -> JudgeVerdict:
        """Juge une decision en recalculant les faits depuis les données brutes."""
        facts = self._verified_facts(decision, features)
        checks = self.verifier.run(decision, facts)
        det_score = sum(c.score * c.weight for c in checks)
        issues = [code for c in checks for code in c.issue_codes]

        det_score, capped = self._apply_safety_cap(det_score, issues, facts)
        final, llm_score, feedback = self._review_with_llm(
            decision, facts, checks, det_score, capped,
        )
        final = round(min(10.0, max(0.0, final)), 2)

        verdict = JudgeVerdict(
            timestamp=decision.timestamp,
            global_score=final,
            deterministic_score=round(det_score, 2),
            llm_score=llm_score,
            agreement=final >= AGREEMENT_THRESHOLD,
            checks=checks,
            flagged_issues=issues,
            feedback=feedback,
            corrected_severity=(facts.rule_severity if facts.rule_severity != decision.severity
                                else None),
            verified_facts=facts.to_dict(),
            judged_by="hybrid" if llm_score is not None else "deterministic",
            limitations=[
                "Contrôle de cohérence interne utilisant les mêmes données et référentiels.",
                "Aucune vérité terrain GMAO ni validation opérateur indépendante.",
                "Un accord ne confirme ni panne, ni cause physique, ni action terrain.",
            ],
            evidence_refs=list(decision.evidence_refs),
        )

        if not verdict.agreement:
            logger.warning(
                f"DESACCORD DU JUDGE — note {final:.2f}/10 a {decision.timestamp} | "
                f"anomalies: {', '.join(issues) or 'aucune'}"
            )
        return verdict


# ── Utilitaires ───────────────────────────────────────────────────────────────

def _default_feedback(
    checks: list[Check], facts: VerifiedFacts, capped: float | None
) -> str:
    """Redige une synthese a partir des seuls controles."""
    failed = [c for c in checks if not c.passed]
    if not failed:
        return (f"Cohérence interne acceptée : les {len(checks)} contrôles sont satisfaits. "
                f"Valeurs citées conformes aux mesures, sévérité {facts.rule_severity} "
                f"retrouvée par les mêmes règles. "
                "Ce résultat ne constitue pas une validation terrain.")

    worst = min(failed, key=lambda c: c.score)
    parts = [
        f"{len(failed)} contrôle(s) en échec sur {len(checks)}.",
        f"Point le plus penalisant — {worst.label} {worst.detail}",
    ]
    if capped:
        parts.append(
            f"Note plafonnée à {nombre(capped, 0)}/10 : un manquement de sécurité "
            f"interdit toute validation."
        )
    others = [c for c in failed if c is not worst]
    if others:
        parts.append("Autres réserves : " + " ".join(f"{c.detail}" for c in others[:2]))
    return " ".join(parts)


def _extract_numbers(text: str) -> list[float]:
    """Extrait les nombres decimaux d'un texte."""
    return [
        float(m.replace(",", "."))
        for m in re.findall(r"-?\d[\d\s]*[\d,.]|\d+[.,]\d+", text)
        if m.strip()
    ]
