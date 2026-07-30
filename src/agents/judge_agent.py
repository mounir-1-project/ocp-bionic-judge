"""
Judge Agent — contrôleur hybride de cohérence des décisions.

POURQUOI LA VERSION PRECEDENTE NE POUVAIT PAS FONCTIONNER
============================================================================
La v1 envoyait a un LLM la decision de l'agent et lui demandait de la noter
sur 5 criteres. Trois failles structurelles, independantes du prompt :

1. AUCUNE SOURCE DE VERITE INDEPENDANTE.
   Le Judge ne voyait que ce que l'agent lui racontait. Si l'agent ecrivait
   "temperature 85 degC" alors que le capteur indiquait 66 degC, le Judge
   n'avait aucun moyen de le savoir. Il notait la COHERENCE INTERNE d'un
   texte, pas sa VERACITE. Un diagnostic entierement invente et bien redige
   obtenait une meilleure note qu'un diagnostic juste et mal formule.

2. COMPLAISANCE STRUCTURELLE.
   Un LLM a qui l'on demande de noter une production plausible note haut.
   Sans ancrage factuel, le Judge validait presque tout : il produisait un
   tampon de conformite, pas un controle.

3. NON REPRODUCTIBILITE.
   Note variable d'un appel a l'autre, dependance a un quota API. Inutilisable
   comme dispositif de gouvernance, et indemontrable sans connexion.

CE QUE FAIT CETTE VERSION
============================================================================
Le contrôleur recalcule les faits depuis la même chaîne de données et de règles, puis
confronte chaque affirmation de l'agent a ces faits. Il ne demande jamais son
avis au LLM sur un point verifiable.
Il n'est pas une validation terrain indépendante et ne peut confirmer une panne.

  ETAGE 1 — VERIFICATION (deterministe, fait autorite)
      Huit controles independants, chacun repondant a une question factuelle
      tranchable. Produit une note reproductible et un journal d'audit.

  ETAGE 2 — REDACTION ET NUANCE (LLM, optionnel, borne)
      Le LLM recoit les faits verifies ET le resultat des controles. Il peut
      ajuster la note dans un corridor de +/- LLM_CORRIDOR points et rediger
      la synthese. Il ne peut PAS contredire un fait etabli : sur tout point
      verifiable, l'etage 1 fait autorite.

Le Judge s'auto-surveille : `JudgeAuditor` mesure sa propre distribution de
notes. Un Judge qui valide tout est un Judge defaillant, et le systeme le dit.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import contextlib
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, ClassVar

import numpy as np
import pandas as pd
from loguru import logger

from src.agents.schemas import (
    EXECUTION_WINDOW_LABEL,
    MIN_URGENCY_FOR_SEVERITY,
    URGENCY_HOURS,
    AgentDecision,
    Check,
    JudgeVerdict,
    confiance_justifiable,
)
from src.domain.knowledge import AMDEC_PATH, DomainKnowledge, load_domain
from src.formatting import nombre, sans_accents
from src.governance.lineage import sha256_file
from src.models.detector import SEVERITY_ORDER, CoolerAnomalyDetector, DetectionResult

# Seuil de validation. En dessous, le Judge est en desaccord et une alerte de
# gouvernance est levee.
AGREEMENT_THRESHOLD = 6.0

# Amplitude maximale de correction autorisee au LLM, en points sur 10.
# Le LLM apporte de la nuance, pas un droit de veto sur les faits.
LLM_CORRIDOR = 1.5

# Tolerance relative admise entre une valeur citee par l'agent et la mesure
# reelle. 1 % couvre les arrondis d'affichage sans laisser passer une invention.
VALUE_REL_TOL = 0.01
VALUE_ABS_TOL = 0.05

# Tolerance appliquee aux nombres LUS DANS LE TEXTE, plus large que celle des
# valeurs declarees : un diagnostic redige arrondit legitimement a l affichage.
# Elle etait ecrite en dur dans le predicat, si bien que deux tolerances
# repondaient a la meme question sans qu on puisse les comparer.
TEXT_REL_TOL = 0.02
TEXT_ABS_TOL = 0.15

# En deca de ce seuil, un nombre du texte est un comptage ou une reference
# (« 8 controles », « tache 2 »), pas une mesure : le controle l ignore.
TEXT_MIN_MAGNITUDE = 10.0

# Piece portant les grandeurs de performance de l'echangeur. Les modes qui s'y
# rattachent ne sont pas interpretables hors marche etablie : c'est ce que
# verifie le controle d'etat de marche. La liste est lue dans la topologie.
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
        legitimate_numbers: Univers des nombres qu'un diagnostic a le droit de
            citer : mesures, preuves des constatations, contributions du modele,
            seuils du referentiel et cotations AMDEC. Tout nombre cite hors de
            cet ensemble est, par construction, non rattachable aux faits.
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
        """Construit les faits verifies a partir d'une detection recalculee.

        Args:
            result: Detection recalculee par le Judge lui-meme.
            domain: Connaissance domaine (seuils et cotations legitimes).

        Returns:
            VerifiedFacts.
        """
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

        # Seuils, plages et consignes du referentiel : les citer est legitime.
        for tag in domain.tags.values():
            for key in ("alarm_low_low", "alarm_low", "alarm_high", "alarm_high_high"):
                _add(tag.threshold(key))
            _add(tag.setpoint)
            _add(tag.saturation_value)
            for rng in (tag.range_operating, tag.range_physical, tag.control_band):
                if rng:
                    _add(rng[0])
                    _add(rng[1])
        # Cotations AMDEC.
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

    Attributes:
        domain: Connaissance domaine.
        weights: Poids de chaque controle dans la note globale.
    """

    WEIGHTS: ClassVar[dict[str, float]] = {
        "V1_NUMERIC_FIDELITY":   0.22,   # les chiffres cites sont-ils les vrais ?
        "V2_SEVERITY":           0.16,   # la severite correspond-elle aux faits ?
        "V3_AMDEC_GROUNDING":    0.14,   # le mode invoque existe-t-il et est-il observable ?
        "V4_ACTION_CONFORMITY":  0.14,   # l'action est-elle conforme et executable ?
        "V5_CONFIDENCE":         0.15,   # la confiance est-elle calibree ?
        "V6_STATE_AWARENESS":    0.08,   # l'etat de marche est-il respecte ?
        "V7_EVIDENCE_COVERAGE":  0.05,   # le fait le plus grave est-il traite ?
        "V8_UNCERTAINTY":        0.06,   # les reserves sont-elles enoncees ?
    }

    def __init__(self, domain: DomainKnowledge) -> None:
        """Initialise la couche de verification.

        Args:
            domain: Connaissance domaine.
        """
        self.domain = domain

    def run(self, decision: AgentDecision, facts: VerifiedFacts) -> list[Check]:
        """Execute les huit controles.

        Args:
            decision: Decision produite par l'agent.
            facts: Faits recalcules independamment.

        Returns:
            Liste des resultats de controle.
        """
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

    # -- V1 -------------------------------------------------------------------

    def _v1_numeric_fidelity(self, d: AgentDecision, f: VerifiedFacts) -> Check:
        """Chaque valeur citee correspond-elle a la mesure reelle ?

        Le controle le plus important : il rend l'hallucination impossible.
        Les valeurs declarees dans `cited_values` sont confrontees aux mesures
        recalculees. Les nombres presents dans le texte du diagnostic mais
        absents des faits sont egalement releves.
        """
        wrong: list[str] = []
        checked = 0

        for name, claimed in (d.cited_values or {}).items():
            actual = f.measurements.get(name)
            if actual is None:
                continue
            checked += 1
            tol = max(abs(actual) * VALUE_REL_TOL, VALUE_ABS_TOL)
            if abs(float(claimed) - float(actual)) > tol:
                wrong.append(f"{name}: annonce {claimed:g}, mesure {actual:g}")

        # Verification du texte : tout nombre present dans le diagnostic doit
        # appartenir a l'univers des nombres legitimes (mesures, preuves, seuils
        # du referentiel, cotations AMDEC). Les entiers inferieurs a 10 sont
        # ignores : ce sont des comptages ou des references, pas des mesures.
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
                label="Les valeurs citees correspondent-elles aux mesures reelles ?",
                passed=False, weight=self.WEIGHTS["V1_NUMERIC_FIDELITY"], score=0.0,
                detail=f"{len(wrong)} valeur(s) fausse(s) sur {checked} verifiee(s) : "
                       + " ; ".join(wrong[:4]),
                issue_codes=["HALLUCINATED_VALUE"],
            )
        if unmatched:
            return Check(
                id="V1_NUMERIC_FIDELITY",
                label="Les valeurs citees correspondent-elles aux mesures reelles ?",
                passed=False, weight=self.WEIGHTS["V1_NUMERIC_FIDELITY"], score=5.0,
                detail=f"{checked} valeur(s) declaree(s) exacte(s), mais le texte contient "
                       f"des nombres non rattachables aux mesures : "
                       f"{', '.join(f'{n:g}' for n in unmatched[:4])}.",
                issue_codes=["UNVERIFIABLE_VALUE"],
            )
        if checked == 0:
            return Check(
                id="V1_NUMERIC_FIDELITY",
                label="Les valeurs citees correspondent-elles aux mesures reelles ?",
                passed=False, weight=self.WEIGHTS["V1_NUMERIC_FIDELITY"], score=1.5,
                detail="Aucune valeur mesuree n'est citee : le diagnostic n'est pas "
                       "rattachable aux donnees et ne peut pas etre verifie.",
                issue_codes=["NO_QUANTITATIVE_EVIDENCE"],
            )
        return Check(
            id="V1_NUMERIC_FIDELITY",
            label="Les valeurs citees correspondent-elles aux mesures reelles ?",
            passed=True, weight=self.WEIGHTS["V1_NUMERIC_FIDELITY"], score=10.0,
            detail=f"{checked} valeur(s) confrontee(s) aux mesures recalculees, toutes exactes.",
        )

    # -- V2 -------------------------------------------------------------------

    def _v2_severity(self, d: AgentDecision, f: VerifiedFacts) -> Check:
        """La severite annoncee correspond-elle aux faits recalcules ?

        Sous-estimer est bien plus grave que sur-estimer : une sous-estimation
        laisse passer une degradation reelle. La sanction est donc asymetrique.
        """
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
            score = max(0.0, 6.0 + 3.0 * gap)   # -1 -> 3.0 ; -2 -> 0.0
            return Check(
                id="V2_SEVERITY", label="La sévérité correspond-elle aux faits ?",
                passed=False, weight=self.WEIGHTS["V2_SEVERITY"], score=score,
                detail=f"Sévérité SOUS-ESTIMÉE : l'agent annonce {d.severity} alors que "
                       f"le recalcul donne {f.rule_severity} "
                       f"(constatations reelles : {', '.join(f.rule_codes) or 'aucune'}).",
                issue_codes=["SEVERITY_UNDERESTIMATED"],
            )
        return Check(
            id="V2_SEVERITY", label="La sévérité correspond-elle aux faits ?",
            passed=False, weight=self.WEIGHTS["V2_SEVERITY"], score=max(4.0, 8.0 - 2.0 * gap),
            detail=f"Sévérité SUR-ESTIMÉE : l'agent annonce {d.severity} contre "
                   f"{f.rule_severity} au recalcul. Sur-alerter use la confiance "
                   f"des equipes et finit par faire ignorer les vraies alarmes.",
            issue_codes=["SEVERITY_OVERESTIMATED"],
        )

    # -- V3 -------------------------------------------------------------------

    def _v3_amdec_grounding(self, d: AgentDecision, f: VerifiedFacts) -> Check:
        """Les modes AMDEC invoques existent-ils et sont-ils detectables ?

        Attrape la faute la plus insidieuse : diagnostiquer un mode que les
        capteurs disponibles ne permettent pas de voir (ex. degradation de
        l'anode sacrificielle, non instrumentee). Une telle affirmation donne
        a l'exploitant une fausse certitude sur un composant de criticite 112.
        """
        if not d.amdec_modes:
            if f.amdec_modes:
                return Check(
                    id="V3_AMDEC_GROUNDING", label="Les modes AMDEC invoques sont-ils fondes ?",
                    passed=False, weight=self.WEIGHTS["V3_AMDEC_GROUNDING"], score=4.0,
                    detail=f"Aucun mode AMDEC rattache alors que les faits en designent "
                           f"{', '.join(f.amdec_modes)}. Le diagnostic n'est pas raccorde "
                           f"a l'analyse de criticite de l'equipement.",
                    issue_codes=["NO_AMDEC_LINK"],
                )
            return Check(
                id="V3_AMDEC_GROUNDING", label="Les modes AMDEC invoques sont-ils fondes ?",
                passed=True, weight=self.WEIGHTS["V3_AMDEC_GROUNDING"], score=10.0,
                detail="Aucun mode invoque, aucun mode attendu — coherent.",
            )

        unknown = [m for m in d.amdec_modes if m not in self.domain.modes]
        if unknown:
            return Check(
                id="V3_AMDEC_GROUNDING", label="Les modes AMDEC invoques sont-ils fondes ?",
                passed=False, weight=self.WEIGHTS["V3_AMDEC_GROUNDING"], score=0.0,
                detail=f"Mode(s) inexistant(s) dans l'AMDEC de l'equipement : "
                       f"{', '.join(unknown)}. Invention pure.",
                issue_codes=["INVENTED_AMDEC_MODE"],
            )

        # UN ANGLE MORT EST UN MODE QU'AUCUN SIGNAL NE TOUCHE — PAS UN MODE
        # PARTIELLEMENT OBSERVE.
        #
        # Le referentiel distingue trois degres. `none` : aucune mesure ne dit
        # rien de ce mode, l'invoquer est une hallucination. `partial` : un
        # symptome est mesurable mais l'etat de la piece ne l'est pas — une
        # fuite de calandre se devine par une perte de debit, la corrosion par
        # l'exposition cumulee. Invoquer un mode `partial` sur la foi de son
        # symptome est LEGITIME, et c'est meme ce que le moteur de regles fait
        # quand le debit acide s'effondre.
        #
        # Confondre les deux faisait sanctionner comme hallucination six
        # decisions parfaitement fondees.
        blind = [
            m for m in d.amdec_modes
            if self.domain.modes[m].observabilite == "none"
        ]
        if blind:
            return Check(
                id="V3_AMDEC_GROUNDING", label="Les modes AMDEC invoques sont-ils fondes ?",
                passed=False, weight=self.WEIGHTS["V3_AMDEC_GROUNDING"], score=1.0,
                detail=f"Mode(s) NON detectable(s) avec l'instrumentation disponible : "
                       f"{', '.join(blind)}. Affirmer les avoir detectes donne une fausse "
                       f"assurance sur un composant que seule une inspection physique "
                       f"peut controler.",
                issue_codes=["BLIND_SPOT_CLAIM"],
            )

        unsupported = [m for m in d.amdec_modes if m not in f.amdec_modes]
        if unsupported:
            return Check(
                id="V3_AMDEC_GROUNDING", label="Les modes AMDEC invoques sont-ils fondes ?",
                passed=False, weight=self.WEIGHTS["V3_AMDEC_GROUNDING"], score=5.0,
                detail=f"Mode(s) invoque(s) sans constatation correspondante : "
                       f"{', '.join(unsupported)}. Attendus d'apres les faits : "
                       f"{', '.join(f.amdec_modes) or 'aucun'}.",
                issue_codes=["UNSUPPORTED_AMDEC_MODE"],
            )
        return Check(
            id="V3_AMDEC_GROUNDING", label="Les modes AMDEC invoques sont-ils fondes ?",
            passed=True, weight=self.WEIGHTS["V3_AMDEC_GROUNDING"], score=10.0,
            detail=f"Mode(s) {', '.join(d.amdec_modes)} : existant(s), observable(s), "
                   f"et soutenu(s) par les constatations.",
        )

    # -- V4 -------------------------------------------------------------------

    def _v4_action_conformity(self, d: AgentDecision, f: VerifiedFacts) -> Check:
        """L'action est-elle proportionnee, conforme a l'AMDEC et executable ?

        Trois fautes possibles, par gravite decroissante :
          - prescrire une intervention en marche sur un circuit acide (danger)
          - sous-dimensionner le delai face a la severite (risque)
          - s'ecarter de l'action corrective prevue par l'AMDEC (conformite)
        """
        action = d.recommended_action
        problems: list[str] = []
        issues: list[str] = []
        score = 10.0

        # Delai de qualification vs severite
        need = MIN_URGENCY_FOR_SEVERITY.get(d.severity, "SOUS_SURVEILLANCE")
        if URGENCY_HOURS[action.urgency] > URGENCY_HOURS[need]:
            problems.append(
                f"délai insuffisant : urgence '{action.urgency}' pour une sévérité "
                f"{d.severity} qui exige au minimum '{need}'"
            )
            issues.append("ACTION_UNDERSIZED")
            score = min(score, 3.0)

        # Securite : arret process requis mais non signale
        # L'ETAT REQUIS EST CELUI DE LA TACHE CITEE, PAS DU MODE ENTIER.
        # Ce controle balayait TOUTES les taches de TOUS les modes invoques et
        # concluait « arret requis » des qu'une seule l'exigeait. Or l'action ne
        # cite qu'une tache. Pour CALANDRE_FUITE, refs ["A" (arret process,
        # 4 ans), "C" (en marche, 1 mois)], une recommandation d'inspection
        # externe mensuelle — realisable equipement en service, et correcte —
        # etait sanctionnee UNSAFE_ACTION avec note plafonnee a 1/10 parce que
        # la tache A du meme mode exige une consignation.
        #
        # Le controle porte donc sur la tache effectivement citee. En son
        # absence, on retombe sur l'exigence la plus stricte des modes invoques :
        # une action qui ne cite aucune tache ne doit pas echapper au controle.
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
            problems.append(
                "l'intervention prévue par le plan préventif exige un arrêt process et "
                "une consignation (gamme PS3-ABS-REFR), ce que l'action ne mentionne pas"
            )
            issues.append("UNSAFE_ACTION")
            score = min(score, 1.0)

        # FENETRE D'EXECUTION : une operation sous consignation ne peut pas
        # etre annoncee comme realisable en marche. Ce controle existe parce
        # qu'une version precedente prescrivait « sous 24 h » une tache a
        # cadence quadriennale exigeant la vidange des circuits : la
        # recommandation etait inexecutable telle qu'elle etait formulee.
        if needs_stop and action.execution_window == "EN_MARCHE":
            problems.append(
                "l'action est annoncée réalisable en marche alors que la tâche du "
                "plan préventif exige la consignation des circuits : la fenêtre "
                "d'exécution doit être un arrêt"
            )
            issues.append("UNSAFE_ACTION")
            score = min(score, 1.0)
        if not needs_stop and action.execution_window != "EN_MARCHE":
            problems.append(
                "l'action réclame un arrêt process que le plan préventif n'exige "
                "pas pour ce mode : immobilisation injustifiée de la ligne"
            )
            issues.append("ACTION_OVERSIZED")
            score = min(score, 4.0)

        # Action vide ou purement contemplative face a un fait grave
        if d.severity in ("WARNING", "CRITICAL") and len(action.description.strip()) < 25:
            problems.append("action trop vague pour être exécutée par un technicien")
            issues.append("VAGUE_ACTION")
            score = min(score, 4.0)

        # Conformite au plan preventif
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
            detail=(
                f"Qualification sous '{action.urgency}', proportionnée à la sévérité "
                f"{d.severity} ; intervention {EXECUTION_WINDOW_LABEL[action.execution_window]}, "
                f"conforme à l'état exigé par le plan préventif."
            ),
        )

    # -- V5 -------------------------------------------------------------------

    def _v5_confidence(self, d: AgentDecision, f: VerifiedFacts) -> Check:
        """La confiance affichee reflete-t-elle la force reelle des preuves ?

        Le Judge calcule une confiance attendue a partir des seuls faits, puis
        compare. L'exces de confiance est sanctionne plus durement que l'exces
        de prudence : c'est lui qui conduit a des decisions non fondees.
        """
        # Bareme PARTAGE avec l'agent : voir `confiance_justifiable`. Les deux
        # avaient diverge, et le controleur accusait l'agent de sur-confiance
        # sur des decisions parfaitement calibrees.
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

        # Tolerance volontairement asymetrique et serree a la hausse : le banc
        # d'evaluation a montre qu'une tolerance de 0.25 laissait passer une
        # confiance annoncee a 0.99 sur des preuves justifiant 0.80. Une quasi
        # certitude affichee doit etre gagnee, pas supposee.
        gap = d.confidence - expected
        if gap > 0.12:
            return Check(
                id="V5_CONFIDENCE", label="La confiance est-elle calibree sur les preuves ?",
                passed=False, weight=self.WEIGHTS["V5_CONFIDENCE"],
                score=max(0.0, 5.0 - 20.0 * (gap - 0.12)),
                detail=f"Sur-confiance : {d.confidence:.2f} annonce contre {expected:.2f} "
                       f"justifiable par les preuves ({f.n_invalid_tags} capteur(s) en défaut, "
                       f"modèle {'applicable' if f.model_applicable else 'inapplicable'}).",
                issue_codes=["OVERCONFIDENCE"],
            )
        if gap < -0.30:
            return Check(
                id="V5_CONFIDENCE", label="La confiance est-elle calibree sur les preuves ?",
                passed=False, weight=self.WEIGHTS["V5_CONFIDENCE"], score=6.0,
                detail=f"Sous-confiance : {d.confidence:.2f} annonce contre {expected:.2f} "
                       f"justifiable. Une prudence excessive fait ignorer des signaux valides.",
                issue_codes=["UNDERCONFIDENCE"],
            )
        return Check(
            id="V5_CONFIDENCE", label="La confiance est-elle calibree sur les preuves ?",
            passed=True, weight=self.WEIGHTS["V5_CONFIDENCE"],
            score=round(10.0 - 8.0 * abs(gap), 2),
            detail=f"Confiance {d.confidence:.2f} coherente avec les {expected:.2f} "
                   f"justifiables par les preuves disponibles.",
        )

    # -- V6 -------------------------------------------------------------------

    def _v6_state_awareness(self, d: AgentDecision, f: VerifiedFacts) -> Check:
        """L'agent respecte-t-il l'etat de marche reel de la ligne ?

        Diagnostiquer une degradation d'echangeur pendant un arret est une
        faute de raisonnement industriel : les grandeurs de performance n'ont
        aucun sens hors marche etablie.
        """
        if d.process_state != f.process_state:
            return Check(
                id="V6_STATE_AWARENESS", label="L'état de marche est-il respecté ?",
                passed=False, weight=self.WEIGHTS["V6_STATE_AWARENESS"], score=0.0,
                detail=f"État annoncé '{d.process_state}' contre '{f.process_state}' réel.",
                issue_codes=["STATE_MISMATCH"],
            )
        if f.process_state != "RUNNING":
            # LES MODES DE PERFORMANCE VIENNENT DU REFERENTIEL, PAS DU CODE.
            # L'ensemble etait ecrit en dur ici : l'ajout d'un mode porte par le
            # faisceau dans `amdec.yaml` ne l'aurait pas rejoint, et ce controle
            # aurait laisse passer un diagnostic de degradation formule a
            # l'arret. La topologie declare deja quels modes affectent la
            # surface d'echange.
            perf_modes = self.domain.modes_for_component(PERFORMANCE_COMPONENT)
            if set(d.amdec_modes) & perf_modes or d.severity in ("WARNING", "CRITICAL"):
                return Check(
                    id="V6_STATE_AWARENESS", label="L'état de marche est-il respecté ?",
                    passed=False, weight=self.WEIGHTS["V6_STATE_AWARENESS"], score=1.0,
                    detail=f"Diagnostic de dégradation formulé alors que la ligne est "
                           f"en état {f.process_state}. Les grandeurs de performance "
                           f"de l'échangeur ne sont pas interprétables hors marche "
                           f"établie.",
                    issue_codes=["DIAGNOSIS_OUT_OF_STATE"],
                )
        return Check(
            id="V6_STATE_AWARENESS", label="L'état de marche est-il respecté ?",
            passed=True, weight=self.WEIGHTS["V6_STATE_AWARENESS"], score=10.0,
            detail=f"État {f.process_state} correctement pris en compte.",
        )

    # -- V7 -------------------------------------------------------------------

    def _v7_evidence_coverage(self, d: AgentDecision, f: VerifiedFacts) -> Check:
        """La constatation la plus grave est-elle traitee par le diagnostic ?

        Un diagnostic qui commente un detail en passant a cote du fait le plus
        grave est formellement correct et operationnellement dangereux.
        """
        if not f.rule_codes:
            return Check(
                id="V7_EVIDENCE_COVERAGE", label="Le fait le plus grave est-il traite ?",
                passed=True, weight=self.WEIGHTS["V7_EVIDENCE_COVERAGE"], score=10.0,
                detail="Aucune constatation a couvrir.",
            )
        covered = set(d.evidence_refs or [])
        missing = [c for c in f.rule_codes if c not in covered]
        ratio = 1.0 - len(missing) / len(f.rule_codes)
        if missing:
            return Check(
                id="V7_EVIDENCE_COVERAGE", label="Le fait le plus grave est-il traite ?",
                passed=False, weight=self.WEIGHTS["V7_EVIDENCE_COVERAGE"],
                score=round(10.0 * ratio, 2),
                detail=f"Constatation(s) non reprise(s) : {', '.join(missing[:4])}.",
                issue_codes=["INCOMPLETE_COVERAGE"],
            )
        return Check(
            id="V7_EVIDENCE_COVERAGE", label="Le fait le plus grave est-il traite ?",
            passed=True, weight=self.WEIGHTS["V7_EVIDENCE_COVERAGE"], score=10.0,
            detail=f"Les {len(f.rule_codes)} constatation(s) sont reprises dans la decision.",
        )

    # -- V8 -------------------------------------------------------------------

    def _v8_uncertainty(self, d: AgentDecision, f: VerifiedFacts) -> Check:
        """Les limites du diagnostic sont-elles enoncees quand elles existent ?

        Quand la base de mesure est degradee ou le modele inapplicable, le
        silence sur ces reserves est une omission : l'ingenieur qui lit le
        rapport doit savoir sur quoi il s'appuie.
        """
        needs_caveat = f.n_invalid_tags > 0 or not f.model_applicable
        # LA COMPARAISON IGNORE LES ACCENTS, ET C'EST INDISPENSABLE.
        #
        # Ce controle cherchait ses mots-cles dans un texte simplement mis en
        # minuscules. Lorsque les textes du systeme ont ete correctement
        # accentues, cinq des douze cles — « reserve », « defaut », « degrade »,
        # « prelevement », « verifier » — sont devenues introuvables. V8 a
        # echoue sur 100 % des heures hors marche, et l'exploitant a lu
        # « limite non enoncee » sous un diagnostic dont la premiere phrase est
        # « la surveillance de performance n'est pas applicable ».
        #
        # Un controle de gouvernance ne doit jamais dependre de la typographie
        # du texte qu'il inspecte.
        text = sans_accents(d.diagnosis + " " + d.reasoning)
        has_caveat = any(k in text for k in (
            "reserve", "defaut", "degrade", "non applicable", "pas applicable",
            "inapplicable", "confirmer", "a valider", "incertitude",
            "prelevement", "verifier", "suspect", "manquant",
        ))
        if needs_caveat and not has_caveat:
            return Check(
                id="V8_UNCERTAINTY", label="Les limites du diagnostic sont-elles enoncees ?",
                passed=False, weight=self.WEIGHTS["V8_UNCERTAINTY"], score=3.0,
                detail=f"Aucune reserve enoncee alors que {f.n_invalid_tags} point(s) de "
                       f"mesure sont en défaut et que le modèle est "
                       f"{'applicable' if f.model_applicable else 'INAPPLICABLE'}.",
                issue_codes=["MISSING_CAVEAT"],
            )
        return Check(
            id="V8_UNCERTAINTY", label="Les limites du diagnostic sont-elles enoncees ?",
            passed=True, weight=self.WEIGHTS["V8_UNCERTAINTY"], score=10.0,
            detail="Reserves enoncees a bon escient." if needs_caveat
                   else "Aucune reserve necessaire : base de mesure complete.",
        )


# ── Etage 2 : redaction LLM ───────────────────────────────────────────────────

JUDGE_SYSTEM = """Tu es le Judge du systeme de surveillance du refroidisseur E7301
(PS III, Maroc Chimie, OCP). Tu es un contrôleur de cohérence interne, pas une
validation terrain indépendante ni un relecteur
bienveillant.

## TON ROLE EXACT — LIS ATTENTIVEMENT

Une couche de VERIFICATION AUTOMATIQUE a deja confronte la decision de l'agent
aux donnees brutes recalculees independamment. Ses resultats sont des FAITS
ETABLIS. Tu ne peux ni les contester ni les reinterpreter.

Tu as deux missions, et seulement deux :

1. AJUSTER la note dans un corridor de +/- {corridor} points autour de la note
   deterministe, et UNIQUEMENT pour des motifs que la verification automatique
   ne sait pas evaluer : qualite du raisonnement causal, pertinence operationnelle
   pour un technicien de PS III, clarte pour un ingenieur presse.

2. REDIGER une synthese de 2 a 4 phrases : ce qui est solide, ce qui manque,
   et l'amelioration concrete a apporter.

Interdictions absolues :
- inventer un fait qui ne figure pas dans les faits verifies
- remonter la note d'une decision dont un controle de securite a echoue
- te contenter de reformuler les resultats de la verification

## EQUIPEMENT
{equipment}

## AMDEC DE REFERENCE
{amdec}

## SORTIE
JSON valide uniquement, sans texte autour :
{{
  "score_adjustment": <float entre -{corridor} et +{corridor}>,
  "adjustment_reason": "<motif en une phrase, ou '' si aucun ajustement>",
  "feedback": "<2 a 4 phrases pour l'ingenieur fiabilite>"
}}
"""


# ── Judge ─────────────────────────────────────────────────────────────────────

class JudgeAgent:
    """Contrôleur hybride : vérification logique puis rédaction bornée.

    Attributes:
        domain: Connaissance domaine.
        detector: Detecteur utilise pour RECALCULER les faits, independamment
                  de ce que l'agent a rapporte.
        verifier: Couche des huit controles.
        llm: Client Gemini, ou None.
        auditor: Auto-surveillance du Judge.
    """

    def __init__(
        self,
        detector: CoolerAnomalyDetector,
        domain: DomainKnowledge | None = None,
        use_llm: bool = True,
    ) -> None:
        """Initialise le Judge.

        Args:
            detector: Detecteur servant a recalculer les faits.
            domain: Connaissance domaine (chargee par defaut).
            use_llm: Activer l'etage de redaction LLM si disponible.
        """
        self.domain = domain or load_domain()
        self.detector = detector
        self.verifier = VerificationLayer(self.domain)
        self.llm = _try_build_llm() if use_llm else None
        self.auditor = JudgeAuditor()
        # L'auto-surveillance ne doit compter QUE les decisions reelles.
        # Le banc d'injection soumet volontairement des decisions fausses; les
        # comptabiliser faisait chuter le taux d'accord affiche a l'exploitant
        # de 1.00 a 0.50 et lui faisait croire que le systeme se contredit en
        # exploitation. Voir `suspended_audit()`.
        self._audit_enabled = True
        self.rule_version = sha256_file(AMDEC_PATH)[:16]
        meta = getattr(self.detector.stat, "train_meta_", {})
        self.model_runtime_signature = (
            f"n={meta.get('n_train', 'na')};"
            f"threshold={meta.get('threshold', 'na')};"
            f"features={len(meta.get('features', []))}"
        )
        # Memoire des faits recalcules, indexee par horodatage.
        #
        # L'independance du Judge est STRUCTURELLE, pas temporelle : elle tient
        # au fait qu'il reconstruit ses faits depuis les donnees brutes sans
        # jamais lire ce que l'agent affirme. Memoriser le resultat d'une
        # fonction pure des donnees ne l'affaiblit en rien — cela evite
        # seulement de refaire deux fois le meme calcul lorsque plusieurs
        # decisions portent sur le meme instant (cas du banc d'evaluation, qui
        # juge dix variantes d'une meme decision).
        self._facts_cache: dict[str, VerifiedFacts] = {}
        logger.info(f"Judge initialise — mode "
                    f"{'hybride (verification + LLM)' if self.llm else 'verification deterministe'}")

    @property
    def mode(self) -> str:
        """Mode effectif du Judge."""
        return "hybrid" if self.llm else "deterministic"

    @contextmanager
    def suspended_audit(self) -> Iterator[None]:
        """Suspend l'auto-surveillance le temps d'un banc de test.

        Les decisions soumises par un banc d'injection sont fausses PAR
        CONSTRUCTION. Les melanger aux decisions reelles dans les statistiques
        d'auto-surveillance donne un taux d'accord qui ne veut rien dire et
        alarme l'exploitant sans raison.

        Yields:
            None. L'etat anterieur est restaure meme en cas d'exception.
        """
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
        """Reconstruit les faits depuis les données, avec mémoïsation sûre."""
        key = decision.timestamp
        facts = self._facts_cache.get(key)
        if facts is None:
            recomputed = self.detector.analyze(features, pd.Timestamp(key))
            facts = VerifiedFacts.from_detection(recomputed, self.domain)
            self._facts_cache[key] = facts
        return facts

    @staticmethod
    def _apply_safety_cap(
        score: float,
        issues: list[str],
        facts: VerifiedFacts,
    ) -> tuple[float, float | None]:
        """Applique les plafonds non compensables de sécurité industrielle."""
        blocking = {
            "UNSAFE_ACTION",
            "HALLUCINATED_VALUE",
            "INVENTED_AMDEC_MODE",
            "BLIND_SPOT_CLAIM",
        }
        # LE PLAFOND EST RENVOYE, PAS SEULEMENT APPLIQUE.
        # La synthese annoncait « Note plafonnee a 4/10 » quel que soit le
        # plafond reellement retenu — un etat de marche errone plafonne a 5,0.
        # Un texte de gouvernance qui cite un chiffre faux se disqualifie seul.
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
        deterministic_score: float,
        capped: float | None,
        use_llm: bool,
    ) -> tuple[float, float | None, str]:
        """Ajoute, si disponible, la seule couche rédactionnelle du Judge."""
        final = deterministic_score
        llm_score: float | None = None
        feedback = _default_feedback(checks, facts, capped)
        if self.llm is None or not use_llm:
            return final, llm_score, feedback

        try:
            adjustment, reason, llm_feedback = self._llm_review(
                decision,
                facts,
                checks,
                deterministic_score,
            )
            adjustment = float(np.clip(adjustment, -LLM_CORRIDOR, LLM_CORRIDOR))
            # `if capped` traitait un plafond nul comme une absence de
            # plafond : le LLM aurait pu remonter la note de la decision la
            # plus gravement fautive.
            if capped is not None and adjustment > 0:
                adjustment = 0.0
            llm_score = round(
                min(10.0, max(0.0, deterministic_score + adjustment)),
                2,
            )
            final = llm_score
            feedback = llm_feedback or feedback
            if reason:
                feedback += (
                    f" [Ajustement Judge {adjustment:+.1f} : {reason}]"
                )
        except Exception as exc:
            # Le verdict déterministe reste disponible sans dépendance externe.
            self.llm = None
            logger.warning(
                "Etage LLM du Judge indisponible (%s) — "
                "coupe-circuit ouvert, note deterministe conservee",
                type(exc).__name__,
            )
        return final, llm_score, feedback

    def judge(
        self,
        decision: AgentDecision,
        features: pd.DataFrame,
        use_llm: bool = True,
    ) -> JudgeVerdict:
        """Juge une decision en recalculant les faits depuis les donnees brutes.

        Args:
            decision: Decision produite par l'agent de detection.
            features: DataFrame de features complet — le Judge y puise sa
                      propre verite, sans passer par l'agent.
            use_llm: Autoriser l'ajustement redactionnel LLM pour cet appel.
                     La verification deterministe reste toujours executee.

        Returns:
            JudgeVerdict complet.
        """
        # Recalcul séparé de la décision, mais pas validation terrain indépendante.
        # Les faits sont reconstruits depuis `features` — jamais depuis les
        # champs de `decision`, qui sont precisement ce que l'on met a l'epreuve.
        facts = self._verified_facts(decision, features)
        checks = self.verifier.run(decision, facts)
        det_score = sum(c.score * c.weight for c in checks)
        issues = [code for c in checks for code in c.issue_codes]

        det_score, capped = self._apply_safety_cap(det_score, issues, facts)
        final, llm_score, feedback = self._review_with_llm(
            decision,
            facts,
            checks,
            det_score,
            capped,
            use_llm,
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
            uncertainty_level="high",
            limitations=[
                "Contrôle de cohérence interne utilisant les mêmes données et référentiels.",
                "Aucune vérité terrain GMAO ni validation opérateur indépendante.",
                "Un accord ne confirme ni panne, ni cause physique, ni action terrain.",
            ],
            evidence_refs=list(decision.evidence_refs),
            rule_version=self.rule_version,
            model_runtime_signature=self.model_runtime_signature,
        )
        if self._audit_enabled:
            self.auditor.record(verdict)

        if not verdict.agreement:
            logger.warning(
                f"DESACCORD DU JUDGE — note {final:.2f}/10 a {decision.timestamp} | "
                f"anomalies: {', '.join(issues) or 'aucune'}"
            )
        return verdict

    def _llm_review(
        self,
        decision: AgentDecision,
        facts: VerifiedFacts,
        checks: list[Check],
        det_score: float,
    ) -> tuple[float, str, str]:
        """Soumet le dossier verifie au LLM pour nuance et redaction.

        Args:
            decision: Decision jugee.
            facts: Faits verifies.
            checks: Resultats des controles.
            det_score: Note deterministe.

        Returns:
            Tuple (ajustement, motif, synthese).
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        system = JUDGE_SYSTEM.format(
            corridor=LLM_CORRIDOR,
            equipment=self.domain.briefing_equipment(),
            amdec=self.domain.briefing_amdec(),
        )
        payload = {
            "decision_de_l_agent": decision.model_dump(),
            "faits_verifies_independamment": facts.to_dict(),
            "resultats_de_la_verification": [c.model_dump() for c in checks],
            "note_deterministe": round(det_score, 2),
        }
        user = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
        raw = self.llm.invoke([SystemMessage(content=system), HumanMessage(content=user)]).content
        data = _extract_json(raw)
        return (
            float(data.get("score_adjustment", 0.0)),
            str(data.get("adjustment_reason", "")).strip(),
            str(data.get("feedback", "")).strip(),
        )


# ── Auto-surveillance du Judge ────────────────────────────────────────────────

class JudgeAuditor:
    """Surveille le Judge lui-meme.

    Un juge qui valide tout ne juge pas. Cette classe mesure la distribution
    des notes et signale deux pathologies opposees : la complaisance (tout
    valider) et la severite systematique (tout rejeter). C'est le controle
    de dernier niveau exige par la gouvernance.

    Attributes:
        MIN_SAMPLE: Nombre de decisions en dessous duquel aucune alerte n'est
            emise. Conclure sur la distribution des notes d'un echantillon de
            cinq decisions n'aurait aucun sens; le panneau dit alors ce qu'il
            attend plutot que de rester muet.
    """

    MIN_SAMPLE: ClassVar[int] = 20

    def __init__(self) -> None:
        """Initialise l'auditeur."""
        self.scores: list[float] = []
        self.agreements: list[bool] = []
        self.issues: list[str] = []

    def record(self, verdict: JudgeVerdict) -> None:
        """Enregistre un verdict.

        Args:
            verdict: Verdict rendu par le Judge.
        """
        self.scores.append(verdict.global_score)
        self.agreements.append(verdict.agreement)
        self.issues.extend(verdict.flagged_issues)

    def report(self) -> dict[str, Any]:
        """Produit le rapport d'auto-surveillance.

        Returns:
            Dictionnaire de metriques et d'alertes sur le Judge lui-meme.
        """
        n = len(self.scores)
        # UN PANNEAU VIDE EST UNE OCCASION MANQUEE.
        # Avant le premier rejeu, l'auto-surveillance renvoyait « n = 0,
        # status = AUCUNE DONNEE » et le poste affichait une colonne vide sur
        # les deux tiers de sa hauteur. Or c'est precisement le moment ou le
        # lecteur decouvre le panneau : il doit y apprendre a quoi il sert et
        # a partir de quand il parlera.
        if n == 0:
            return {
                "n": 0,
                "status": "EN_ATTENTE",
                "seuil_activation": self.MIN_SAMPLE,
                "reading": (
                    f"Ce panneau surveille le contrôleur lui-même. Il compare la "
                    f"distribution de ses notes à ce qu'on attend d'un contrôle "
                    f"utile : un dispositif qui valide tout, ou qui note tout "
                    f"pareil, ne contrôle rien. Les trois alertes se déclenchent "
                    f"à partir de {self.MIN_SAMPLE} décisions jugées — lancez le "
                    f"rejeu pour les alimenter."
                ),
                "controles": [
                    "Taux de validation supérieur à 97 % — complaisance",
                    "Taux de validation inférieur à 10 % — sévérité systématique",
                    "Écart-type des notes inférieur à 0,35 point — notes indifférenciées",
                ],
            }

        arr = np.array(self.scores, dtype=float)
        rate = float(np.mean(self.agreements))
        warnings_: list[str] = []

        if n >= self.MIN_SAMPLE:
            if rate > 0.97:
                warnings_.append(
                    "COMPLAISANCE : le contrôleur valide plus de 97 % des "
                    "décisions. Un contrôle qui ne rejette jamais rien ne "
                    "contrôle rien — vérifier que des cas dégradés lui sont "
                    "bien soumis."
                )
            if rate < 0.10:
                warnings_.append(
                    "SÉVÉRITÉ SYSTÉMATIQUE : moins de 10 % de validations. "
                    "Les seuils de contrôle sont probablement mal calibrés."
                )
            if arr.std() < 0.35:
                warnings_.append(
                    f"NOTES INDIFFÉRENCIÉES : écart-type de "
                    f"{nombre(arr.std(), 2)} point. Le contrôleur ne distingue "
                    f"pas les bonnes des mauvaises décisions."
                )

        from collections import Counter
        return {
            "n": n,
            "score_mean": round(float(arr.mean()), 2),
            "score_std": round(float(arr.std()), 2),
            "score_min": round(float(arr.min()), 2),
            "score_max": round(float(arr.max()), 2),
            "score_p25": round(float(np.percentile(arr, 25)), 2),
            "score_p75": round(float(np.percentile(arr, 75)), 2),
            "agreement_rate": round(rate, 3),
            "top_issues": Counter(self.issues).most_common(8),
            "self_check_warnings": warnings_,
            "seuil_activation": self.MIN_SAMPLE,
            "reading": (
                f"{n} décision(s) jugée(s). "
                + (
                    "Aucune alerte : les notes se répartissent et le taux de "
                    "validation reste dans la plage attendue d'un contrôle utile."
                    if not warnings_ and n >= self.MIN_SAMPLE else
                    f"Échantillon encore court — les alertes se déclenchent à "
                    f"partir de {self.MIN_SAMPLE} décisions."
                    if n < self.MIN_SAMPLE else
                    "Le contrôleur signale une anomalie sur son propre "
                    "comportement : voir ci-dessous."
                )
            ),
            "status": "ALERTE" if warnings_ else "OK" if n >= self.MIN_SAMPLE else "EN_ATTENTE",
        }


# ── Utilitaires ───────────────────────────────────────────────────────────────

def _default_feedback(
    checks: list[Check], facts: VerifiedFacts, capped: float | None
) -> str:
    """Redige une synthese sans LLM, a partir des seuls controles.

    Args:
        checks: Resultats des controles.
        facts: Faits verifies.
        capped: Plafond applique pour motif de securite, ou None.

    Returns:
        Synthese en texte clair.
    """
    failed = [c for c in checks if not c.passed]
    if not failed:
        return (f"Cohérence interne acceptée : les {len(checks)} contrôles sont satisfaits. "
                f"Valeurs citées conformes aux mesures, sévérité {facts.rule_severity} "
                f"retrouvée par les mêmes règles, action logiquement proportionnée. "
                "Ce résultat ne constitue pas une validation terrain.")

    worst = min(failed, key=lambda c: c.score)
    parts = [
        f"{len(failed)} controle(s) en echec sur {len(checks)}.",
        f"Point le plus penalisant — {worst.label} {worst.detail}",
    ]
    if capped:
        parts.append(
            f"Note plafonnée à {nombre(capped, 0)}/10 : un manquement de sécurité, "
            f"une valeur non vérifiable ou un état de marche erroné interdit "
            f"toute validation, indépendamment du reste."
        )
    others = [c for c in failed if c is not worst]
    if others:
        parts.append("Autres reserves : " + " ".join(f"{c.detail}" for c in others[:2]))
    return " ".join(parts)


def _extract_numbers(text: str) -> list[float]:
    """Extrait les nombres decimaux d'un texte.

    Args:
        text: Texte a analyser.

    Returns:
        Liste des nombres trouves.
    """
    out: list[float] = []
    for m in re.finditer(r"[-+]?\d+(?:[.,]\d+)?", text or ""):
        try:
            out.append(float(m.group().replace(",", ".")))
        except ValueError:
            continue
    return out


def _try_build_llm():
    """Instancie le client Gemini si disponible.

    Returns:
        Le client LangChain, ou None.
    """
    from src.agents.detection_agent import _try_build_llm as _build
    return _build()


def _extract_json(raw: str) -> dict:
    """Extrait le premier objet JSON d'une reponse LLM.

    Args:
        raw: Texte brut du modele.

    Returns:
        Le dictionnaire decode.
    """
    from src.agents.detection_agent import _extract_json as _ej
    return _ej(raw)
