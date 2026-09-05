"""
Agent de detection — transforme des constatations brutes en diagnostic actionnable.

L'agent compose le diagnostic a partir des constatations et de la connaissance
AMDEC, sans aucun appel externe. Deterministe, reproductible.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from loguru import logger

from src.agents.schemas import (
    MIN_URGENCY_FOR_SEVERITY,
    SERVICE_INSTRUMENTATION,
    SERVICE_MECANIQUE,
    AgentDecision,
    RecommendedAction,
    Severity,
    confiance_justifiable,
)
from src.domain.knowledge import DomainKnowledge, load_domain
from src.models.detector import SEVERITY_ORDER, DetectionResult

# Correspondance severite -> urgence
_DEFAULT_URGENCY = MIN_URGENCY_FOR_SEVERITY

# Les etats process sont des identifiants techniques, traduits pour l'affichage
_ETAT_LISIBLE: dict[str, str] = {
    "RUNNING": "en marche établie",
    "TRANSIENT": "en régime transitoire",
    "STOPPED": "à l'arrêt",
}


def _nominal_confidence(result: DetectionResult) -> float:
    """Confiance d'une decision nominale, alignee sur le bareme du controleur.

    Args:
        result: Sortie de la detection.

    Returns:
        Confiance dans [0, 1].
    """
    return confiance_justifiable(
        rule_codes=[f.code for f in result.findings],
        model_applicable=bool(result.data_quality.get("model_applicable")),
        n_invalid_tags=int(result.data_quality.get("n_invalid_tags", 0)),
        process_state=result.process_state,
    )


# Formulation du delai de qualification
_URGENCY_TEXT: dict[str, str] = {
    "AUCUNE": "aucun délai particulier",
    "SOUS_SURVEILLANCE": "une semaine",
    "SOUS_24H": "24 heures",
    "SOUS_8H": "8 heures",
    "IMMEDIATE": "l'heure",
}


# ── Dossier de faits ──────────────────────────────────────────────────────────

def build_case_file(result: DetectionResult, domain: DomainKnowledge) -> dict[str, Any]:
    """Assemble le dossier de faits soumis a l'agent.

    C'est la seule information dont dispose l'agent. Tout ce qui n'y figure
    pas ne peut pas etre affirme legitimement.

    Args:
        result: Sortie de la detection pour un horodatage.
        domain: Connaissance domaine.

    Returns:
        Dictionnaire de faits serialisable.
    """
    modes = []
    for code in result.amdec_modes:
        m = domain.modes.get(code)
        if not m:
            continue
        modes.append({
            "code": m.code, "element": m.element, "mode": m.mode,
            "causes": m.causes, "effet": m.effet,
            "criticite": m.C, "bande": m.criticality_band(),
            "observabilite": m.observabilite,
            "action_corrective_amdec": m.action_corrective,
            "taches_preventives": [
                {"ref": r, **(domain.maintenance_task(r) or {})}
                for r in m.plan_maintenance_ref
            ],
        })

    return {
        "equipement": domain.equipment["id"],
        "timestamp": result.timestamp,
        "etat_process": result.process_state,
        "severite_calculee": result.severity,
        "score_modele": result.anomaly_score,
        "modele_applicable": result.data_quality.get("model_applicable", False),
        "mesures": result.measurements,
        "constatations": [
            {"code": f.code, "source": f.source, "severite": f.severity,
             "mode_amdec": f.amdec_mode, "message": f.message, "preuves": f.evidence}
            for f in result.findings
        ],
        "contributions_modele": result.attributions,
        "modes_amdec": modes,
        "qualite_donnees": result.data_quality,
        "angles_morts": [m.code for m in domain.blind_spots()],
    }


# ── Mode regles ───────────────────────────────────────────────────────────────

class RuleBasedComposer:
    """Compose un diagnostic a partir des constatations, sans LLM."""

    def __init__(self, domain: DomainKnowledge) -> None:
        self.domain = domain

    def compose(self, result: DetectionResult) -> AgentDecision:
        """Produit une decision structuree.

        Args:
            result: Sortie de la detection.

        Returns:
            AgentDecision generee par regles.
        """
        # La constatation dominante se choisit par severite, puis equipement
        # avant instrumentation, puis criticite AMDEC
        def _priorite(constatation) -> tuple[int, int, int, int, str]:
            mode_associe = self.domain.modes.get(constatation.amdec_mode or "")
            sous_ensemble = (
                mode_associe.raw.get("sous_equipement", "") if mode_associe else ""
            )
            return (
                SEVERITY_ORDER.get(constatation.severity, 0),
                0 if sous_ensemble == "INSTRUMENTATION" else 1,
                mode_associe.C if mode_associe else 0,
                1 if constatation.source == "RULE" else 0,
                constatation.code,
            )

        actionable = [f for f in result.findings if f.severity in ("WARNING", "CRITICAL")]
        lead = max(actionable, key=_priorite) if actionable else None

        if lead is None:
            return self._nominal_decision(result)

        mode = self.domain.modes.get(lead.amdec_mode) if lead.amdec_mode else None
        cited = self._collect_cited(result, lead)

        diagnosis = lead.message
        if mode:
            diagnosis += (
                f" Rattachement AMDEC : {mode.element} / {mode.mode} "
                f"(criticité {mode.C}, {mode.criticality_band().lower()})."
            )

        others = [f for f in result.findings if f is not lead and f.severity != "INFO"]
        reasoning_parts = [
            f"État process : {_ETAT_LISIBLE.get(result.process_state, result.process_state)}.",
            f"Constatation dominante : {lead.code} ({lead.severity}, source {lead.source}).",
        ]
        if others:
            reasoning_parts.append(
                "Constatations concomitantes : "
                + ", ".join(f"{f.code}({f.severity})" for f in others) + "."
            )
        if result.attributions:
            from src.models.detector import _label, _pretty

            top = result.attributions[0]
            reasoning_parts.append(
                f"Contribution statistique dominante : {_label(top['feature'])} à "
                f"{_pretty(top['feature'], top['value'])} contre "
                f"{_pretty(top['feature'], top['reference'])} en référence."
            )
        if result.data_quality.get("n_invalid_tags"):
            reasoning_parts.append(
                f"Réserve : {result.data_quality['n_invalid_tags']} point(s) de mesure "
                f"en défaut à cet instant — à confirmer avant intervention."
            )
        if not result.data_quality.get("model_applicable") and result.process_state == "RUNNING":
            reasoning_parts.append(
                "Réserve : le modèle statistique est inapplicable à cet instant "
                "(au moins une grandeur d'entrée manquante). Le diagnostic ne "
                "repose que sur les règles déterministes, sans corroboration "
                "multivariée — à vérifier."
            )

        action = self._build_action(lead.severity, mode)
        confidence = self._calibrate_confidence(result)

        return AgentDecision(
            timestamp=result.timestamp,
            process_state=result.process_state,
            severity=lead.severity,
            anomaly_score=result.anomaly_score,
            amdec_modes=result.amdec_modes,
            diagnosis=diagnosis,
            reasoning=" ".join(reasoning_parts),
            recommended_action=action,
            confidence=confidence,
            evidence_refs=[f.code for f in result.findings],
            lead_finding=lead.code,
            cited_values=cited,
            generated_by="rules",
        )

    def _nominal_decision(self, result: DetectionResult) -> AgentDecision:
        """Decision pour un point sans constatation actionnable."""
        sev: Severity = result.severity if result.findings else "NORMAL"

        info = [f for f in result.findings if f.severity == "INFO"]
        if result.process_state != "RUNNING":
            diag = (f"Ligne {_ETAT_LISIBLE.get(result.process_state, result.process_state)} : "
                    f"la surveillance de performance de l'échangeur n'est pas "
                    f"applicable. Aucun diagnostic de dégradation ne peut être "
                    f"formulé à partir de mesures prises hors marche établie.")
        elif info:
            diag = ("Aucun écart actionnable. " + " ".join(f.message for f in info[:2]))
        else:
            diag = ("Marche établie, aucun écart significatif. Les grandeurs de "
                    "performance du refroidisseur sont dans leur domaine de "
                    "référence : " + _quote_measurements(result.measurements))

        cited = {k: v for k, v in result.measurements.items()
                 if k in ("T_ACID_IN", "T_ACID_OUT", "F_ACID", "conc_min",
                          "delta_t", "duty_kw", "control_deviation")}
        cited["anomaly_score"] = result.anomaly_score

        return AgentDecision(
            timestamp=result.timestamp,
            process_state=result.process_state,
            severity=sev,
            anomaly_score=result.anomaly_score,
            amdec_modes=result.amdec_modes,
            diagnosis=diag,
            reasoning=f"Aucune constatation de sévérité WARNING ou CRITICAL. "
                      f"Ligne {_ETAT_LISIBLE.get(result.process_state, result.process_state)}.",
            recommended_action=RecommendedAction(
                description="Poursuite de la surveillance en continu. Maintien de "
                            "l'inspection externe mensuelle (tâche C du plan "
                            "préventif, réalisable équipement en service).",
                urgency="AUCUNE" if sev == "NORMAL" else "SOUS_SURVEILLANCE",
                execution_window="EN_MARCHE",
                maintenance_task_ref="C",
                checklist_ref="INSPECTION_EXTERNE",
            ),
            confidence=_nominal_confidence(result),
            evidence_refs=[f.code for f in result.findings],
            lead_finding=None,
            cited_values=cited,
            generated_by="rules",
        )

    # Periodicites du plan preventif, converties en heures
    _UNITES_PERIODICITE: ClassVar[dict[str, float]] = {
        "heure": 1.0, "jour": 24.0, "mois": 730.0, "an": 8766.0,
    }

    def _periodicite_heures(self, ref: str) -> float:
        """Convertit la periodicite d'une tache preventive en heures."""
        tache = self.domain.maintenance_task(ref) or {}
        texte = str(tache.get("periodicite", "")).strip().lower()
        nombre = re.match(r"(\d+(?:[.,]\d+)?)", texte)
        if not nombre:
            return float("inf")
        for radical, heures in self._UNITES_PERIODICITE.items():
            if radical in texte:
                return float(nombre.group(1).replace(",", ".")) * heures
        return float("inf")

    def _tache_la_plus_frequente(self, refs: list[str]) -> str | None:
        """Tache du plan preventif dont la cadence est la plus courte."""
        if not refs:
            return None
        return min(refs, key=self._periodicite_heures)

    def _build_action(self, severity: str, mode) -> RecommendedAction:
        """Construit l'action recommandee a partir de l'AMDEC."""
        urgency = _DEFAULT_URGENCY.get(severity, "SOUS_SURVEILLANCE")
        if mode is None:
            return RecommendedAction(
                description="Vérification du point de mesure concerné et confirmation "
                            "par une seconde source avant toute intervention.",
                urgency=urgency,
                execution_window="EN_MARCHE",
                responsible=SERVICE_INSTRUMENTATION,
            )

        task_ref = self._tache_la_plus_frequente(mode.plan_maintenance_ref)
        task = self.domain.maintenance_task(task_ref) if task_ref else None
        needs_stop = self.domain.task_requires_shutdown(task_ref)

        if not needs_stop:
            window = "EN_MARCHE"
        elif severity == "CRITICAL":
            window = "ARRET_IMMEDIAT"
        else:
            window = "ARRET_PROGRAMME"

        desc = mode.action_corrective
        if task:
            desc += (f" — tâche {task_ref} du plan préventif : {task['tache']} "
                     f"(cadence {task['periodicite']}).")

        if window == "ARRET_PROGRAMME":
            desc += (" Deux horizons distincts : la constatation doit être qualifiée "
                     f"par le service fiabilité sous {_URGENCY_TEXT[urgency]}, tandis "
                     "que l'intervention elle-même exige un arrêt process et la "
                     "consignation des circuits acide et eau de mer (gamme "
                     "PS3-ABS-REFR) — elle se cale sur le prochain arrêt programmé.")
        elif window == "ARRET_IMMEDIAT":
            desc += (" L'intervention exige un arrêt process et la consignation des "
                     "circuits acide et eau de mer (gamme PS3-ABS-REFR). La sévérité "
                     "atteinte ne permet pas d'attendre un arrêt programmé : la mise "
                     "à l'arrêt de la ligne relève de la décision d'exploitation.")

        instrumentation = mode.raw.get("sous_equipement", "") == "INSTRUMENTATION"
        responsible = SERVICE_INSTRUMENTATION if instrumentation else SERVICE_MECANIQUE

        return RecommendedAction(
            description=desc,
            urgency=urgency,
            execution_window=window,
            requires_shutdown=needs_stop,
            maintenance_task_ref=task_ref,
            checklist_ref="INSPECTION_INTERNE" if needs_stop else "INSPECTION_EXTERNE",
            responsible=responsible,
        )

    def _calibrate_confidence(self, result: DetectionResult) -> float:
        """Calibre la confiance sur la force reelle des preuves."""
        modes = [
            self.domain.modes[code]
            for code in result.amdec_modes
            if code in self.domain.modes
        ]
        observabilite = min(
            (m.observabilite for m in modes),
            key=lambda o: {"none": 0, "partial": 1, "full": 2}[o],
            default="full",
        )
        return confiance_justifiable(
            rule_codes=[f.code for f in result.findings],
            model_applicable=bool(result.data_quality.get("model_applicable")),
            n_invalid_tags=int(result.data_quality.get("n_invalid_tags", 0)),
            process_state=result.process_state,
            mode_observabilite=observabilite,
        )

    @staticmethod
    def _collect_cited(result: DetectionResult, lead) -> dict[str, float]:
        """Rassemble les valeurs numeriques citees, pour verification par le Judge."""
        cited: dict[str, float] = {}
        for k, v in (lead.evidence or {}).items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                cited[k] = float(v)
        for k in ("T_ACID_IN", "T_ACID_OUT", "F_ACID", "conc_min"):
            if k in result.measurements:
                cited.setdefault(k, float(result.measurements[k]))
        cited.setdefault("anomaly_score", result.anomaly_score)
        return cited


def _quote_measurements(m: dict[str, float]) -> str:
    """Formate les grandeurs cles pour les citer dans un diagnostic nominal."""
    from src.formatting import unite

    parts = []
    for key, label, symbole, decimales in (
        ("T_ACID_IN", "entrée acide", "°C", 2),
        ("T_ACID_OUT", "sortie acide", "°C", 2),
        ("F_ACID", "débit acide", "m³/h", 2),
        ("conc_min", "titre", "%", 2),
    ):
        if key in m and m[key] is not None:
            parts.append(f"{label} {unite(m[key], symbole, decimales)}")
    return ", ".join(parts) + "." if parts else "valeurs indisponibles."


# ── Agent ──────────────────────────────────────────────────────────────────────

AGENT_SYSTEM = """Tu es l'agent de diagnostic du refroidisseur d'acide de sechage E7301
(atelier sulfurique PS III, Maroc Chimie, OCP). Tu rediges pour un ingenieur
fiabilite qui va decider d'une intervention.

## REGLES ABSOLUES
1. Tu ne cites QUE des valeurs presentes dans le dossier de faits.
2. Tu ne diagnostiques JAMAIS un mode declare non observable.
3. Si l'etat process n'est pas RUNNING, aucun diagnostic n'est recevable.
4. Ta confiance doit refleter la force des preuves.

## SORTIE
Reponds UNIQUEMENT par un objet JSON valide :
{{
  "severity": "NORMAL" | "INFO" | "WARNING" | "CRITICAL",
  "amdec_modes": ["CODE", ...],
  "diagnosis": "diagnostic en 2 a 4 phrases",
  "reasoning": "chaine de raisonnement",
  "recommended_action": {{
    "description": "action concrete",
    "urgency": "AUCUNE" | "SOUS_SURVEILLANCE" | "SOUS_24H" | "SOUS_8H" | "IMMEDIATE",
    "requires_shutdown": true | false,
    "maintenance_task_ref": "A".."H" ou null,
    "responsible": "service concerne"
  }},
  "confidence": 0.0 a 1.0,
  "cited_values": {{"nom_grandeur": valeur_numerique, ...}}
}}
"""


def _try_build_llm():
    """Instancie le client Gemini si disponible."""
    try:
        from src.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_TIMEOUT_S
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


def _extract_json(raw: str) -> dict:
    """Extrait le premier objet JSON d'une reponse LLM."""
    import re
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}") + 1
    if start < 0 or end <= start:
        raise ValueError(f"Aucun JSON dans la reponse: {raw[:200]}")
    return json.loads(text[start:end])


class DetectionAgent:
    """Agent de diagnostic, avec bascule automatique LLM -> regles.

    Attributes:
        domain: Connaissance domaine.
        composer: Compositeur par regles (toujours disponible).
        llm: Client Gemini, ou None si indisponible.
    """

    def __init__(self, domain: DomainKnowledge | None = None, use_llm: bool = True) -> None:
        self.domain = domain or load_domain()
        self.composer = RuleBasedComposer(self.domain)
        self.llm = _try_build_llm() if use_llm else None
        logger.info(f"Agent initialise — mode {'LLM + regles' if self.llm else 'regles seules'}")

    @property
    def mode(self) -> str:
        return "llm" if self.llm else "rules"

    def analyze(self, result: DetectionResult, use_llm: bool = True) -> AgentDecision:
        """Produit un diagnostic a partir d'une detection."""
        baseline = self.composer.compose(result)
        if self.llm is None or not use_llm:
            return baseline
        try:
            return self._analyze_llm(result, baseline)
        except Exception as e:
            logger.warning(f"LLM indisponible ({type(e).__name__}) — repli sur les regles")
            return baseline

    def _analyze_llm(self, result: DetectionResult, baseline: AgentDecision) -> AgentDecision:
        """Fait rediger le diagnostic par le LLM."""
        from langchain_core.messages import HumanMessage, SystemMessage

        case = build_case_file(result, self.domain)
        system = AGENT_SYSTEM
        user = ("Dossier de faits :\n"
                + json.dumps(case, indent=2, ensure_ascii=False, default=str)
                + "\n\nRedige le diagnostic.")
        raw = self.llm.invoke([SystemMessage(content=system), HumanMessage(content=user)]).content
        data = _extract_json(raw)

        action = (RecommendedAction(**data["recommended_action"])
                  if isinstance(data.get("recommended_action"), dict)
                  else baseline.recommended_action)

        return AgentDecision(
            timestamp=result.timestamp,
            process_state=result.process_state,
            severity=data.get("severity", baseline.severity),
            anomaly_score=result.anomaly_score,
            amdec_modes=data.get("amdec_modes", baseline.amdec_modes),
            diagnosis=data.get("diagnosis", baseline.diagnosis),
            reasoning=data.get("reasoning", baseline.reasoning),
            recommended_action=action,
            confidence=float(data.get("confidence", baseline.confidence)),
            evidence_refs=[f.code for f in result.findings],
            lead_finding=baseline.lead_finding,
            cited_values={k: float(v) for k, v in (data.get("cited_values") or {}).items()
                          if isinstance(v, (int, float)) and not isinstance(v, bool)},
            generated_by="llm",
        )
