"""
Agent de detection — transforme des constatations brutes en diagnostic actionnable.

Deux modes de production, un seul contrat de sortie
----------------------------------------------------------------------------
  mode 'rules' : l'agent compose le diagnostic a partir des constatations et
                 de la connaissance AMDEC, sans aucun appel externe. Toujours
                 disponible, deterministe, reproductible.
  mode 'llm'   : Gemini redige le diagnostic a partir du MEME dossier de faits.

Le mode 'rules' n'est pas un pis-aller. C'est la reference : il fournit au
Judge un point de comparaison pour mesurer ce que le LLM apporte reellement,
et il garantit que le systeme reste demontrable sans connexion ni quota API.
Les deux modes produisent un `AgentDecision` identique en structure.

Point de vigilance assume : le LLM ne voit QUE le dossier de faits construit
par le code. Il n'a pas acces aux donnees brutes et ne peut donc pas inventer
une mesure sans que le Judge le detecte par confrontation aux valeurs reelles.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import json
import re
from typing import Any, ClassVar

from loguru import logger

from src.agents.schemas import (
    MIN_URGENCY_FOR_SEVERITY,
    AgentDecision,
    RecommendedAction,
    Severity,
    confiance_justifiable,
)
from src.domain.knowledge import DomainKnowledge, load_domain
from src.models.detector import SEVERITY_ORDER, DetectionResult

# Correspondance severite -> urgence. Une seule table existe : celle du
# contrat, que le controleur utilise pour juger le sous-dimensionnement. Elle
# etait recopiee ici a l'identique, avec un commentaire annoncant l'alignement
# — deux tables qui doivent coincider et que rien ne comparait.
_DEFAULT_URGENCY = MIN_URGENCY_FOR_SEVERITY

# Les etats process viennent du DCS et sont des identifiants techniques. Les
# afficher bruts dans une interface francaise — « Ligne en etat STOPPED » —
# obligeait l'exploitant a traduire mentalement. Le code reste la reference
# machine; seul l'affichage est traduit.
_ETAT_LISIBLE: dict[str, str] = {
    "RUNNING": "en marche établie",
    "TRANSIENT": "en régime transitoire",
    "STOPPED": "à l'arrêt",
}

def _nominal_confidence(result: DetectionResult) -> float:
    """Confiance d'une decision nominale, alignee sur le bareme du controleur.

    LE DEFAUT QUE CETTE FONCTION CORRIGE.
    L'agent annoncait 0,50 des que le modele statistique etait inapplicable,
    sans distinguer POURQUOI il l'etait. Le controleur, lui, retranche 0,15
    lorsque la ligne n'est pas en marche etablie, et jugeait donc 0,35
    justifiable. L'ecart de 0,15 depasse la tolerance de 0,12 : le controleur
    accusait l'agent de sur-confiance sur CHACUNE des 1 385 heures d'arret du
    corpus, soit 13,6 % des horodatages.

    L'anomalie ne se voyait nulle part dans la note globale — elle restait a
    8,74/10 et l'accord etait maintenu. Elle ne se lisait que dans l'encart
    « Reserves du controleur », c'est-a-dire au seul endroit destine a
    l'exploitant.

    Les deux bordereaux sont desormais alignes explicitement.
    `test_aucune_decision_native_ne_declenche_la_sur_confiance` soumet les
    decisions reelles de la chaine, sans mutation, et echoue si le controleur
    releve OVERCONFIDENCE ou UNDERCONFIDENCE sur l'une d'elles.

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


# Formulation du delai de qualification, pour l'inserer dans une phrase.
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

    C'est la seule information dont dispose l'agent — LLM comme regles. Tout
    ce qui n'y figure pas ne peut pas etre affirme legitimement.

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
            # Les trois degres, pas un booleen : reduire `partial` a `false`
            # faisait lire au modele qu'un mode que les regles rattachent
            # activement est un angle mort.
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
        """Initialise le compositeur.

        Args:
            domain: Connaissance domaine.
        """
        self.domain = domain

    def compose(self, result: DetectionResult, case: dict[str, Any]) -> AgentDecision:
        """Produit une decision structuree.

        Args:
            result: Sortie de la detection.
            case: Dossier de faits.

        Returns:
            AgentDecision generee par regles.
        """
        # LA CONSTATATION DOMINANTE SE CHOISIT PAR CRITICITE, PAS PAR L'ORDRE
        # OU LES REGLES SE TROUVENT ECRITES.
        # `max()` renvoie le premier element a egalite : entre un SENSOR_FAULT
        # et un CONC_DROP_SEVERE tous deux CRITICAL, le diagnostic retenait le
        # defaut capteur — parce que `_rule_sensor_health` s'execute en premier
        # dans `RuleEngine.evaluate`. Le fait le plus grave se trouvait relegue
        # en constatation concomitante, et c'est le defaut capteur qui pilotait
        # l'action recommandee et le mode AMDEC affiche.
        #
        # UN DEFAUT DE MESURE N'EST PAS UN DIAGNOSTIC D'EQUIPEMENT.
        # Trier sur la seule criticite AMDEC ne suffit pas : CAPTEUR_DEFAILLANT
        # porte 108 — cotation PROPOSEE par ce travail, `application_rule`,
        # `validation_status: hypothesis` — contre 105 pour FAISCEAU_FUITE,
        # ligne transcrite du document OCP. Un analyseur degrade aurait donc
        # domine une suspicion de percement de tube, l'evenement le plus grave
        # que le systeme puisse voir, et l'aurait relegue en constatation
        # concomitante. L'etat de la chaine de mesure est une RESERVE sur la
        # lecture, pas une conclusion sur l'appareil : il figure deja comme tel
        # dans le raisonnement.
        #
        # L'ordre est donc : severite, puis equipement avant instrumentation,
        # puis criticite AMDEC, puis preuve deterministe avant ecart
        # statistique, le code departageant en dernier recours pour que la
        # selection reste reproductible. La distinction equipement /
        # instrumentation est lue dans le referentiel (`sous_equipement`), pas
        # ecrite ici.
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
        # Reserves explicites. Taire une limite de la base de mesure revient a
        # laisser croire a l'ingenieur que le diagnostic repose sur des donnees
        # completes — c'est precisement ce que le Judge sanctionne (controle V8).
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
        confidence = self._calibrate_confidence(result, lead, mode)

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
            cited_values=cited,
            generated_by="rules",
        )

    def _nominal_decision(self, result: DetectionResult) -> AgentDecision:
        """Decision pour un point sans constatation actionnable.

        Args:
            result: Sortie de la detection.

        Returns:
            AgentDecision de severite NORMAL ou INFO.
        """
        # La severite reste celle du detecteur : une constatation INFO (point
        # isole atypique, ligne a l'arret) ne doit pas etre effacee en NORMAL.
        # L'ecraser reviendrait a masquer une information au Judge, qui la
        # recalcule de toute facon et sanctionnerait l'ecart.
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

        # Un diagnostic sans valeur mesuree n'est pas verifiable. Meme en
        # situation nominale, on ancre la conclusion sur des chiffres reels.
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
            cited_values=cited,
            generated_by="rules",
        )

    # Periodicites du plan preventif, converties en heures pour etre ordonnees.
    # Le referentiel les exprime en langage naturel ('1 mois', '4 ans').
    _UNITES_PERIODICITE: ClassVar[dict[str, float]] = {
        "heure": 1.0, "jour": 24.0, "mois": 730.0, "an": 8766.0,
    }

    def _periodicite_heures(self, ref: str) -> float:
        """Convertit la periodicite d'une tache preventive en heures.

        Args:
            ref: Reference de tache ('A'..'H').

        Returns:
            Periodicite en heures, ou l'infini si elle n'est pas interpretable —
            une tache dont on ne sait pas lire la cadence ne doit jamais etre
            retenue comme la plus frequente.
        """
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
        """Tache du plan preventif dont la cadence est la plus courte.

        Args:
            refs: References de taches rattachees au mode.

        Returns:
            La reference retenue, ou None si le mode n'en cite aucune.
        """
        if not refs:
            return None
        return min(refs, key=self._periodicite_heures)

    def _build_action(self, severity: str, mode) -> RecommendedAction:
        """Construit l'action recommandee a partir de l'AMDEC.

        Args:
            severity: Severite de la constatation dominante.
            mode: FailureMode associe, ou None.

        Returns:
            RecommendedAction conforme au plan de maintenance.
        """
        urgency = _DEFAULT_URGENCY.get(severity, "SOUS_SURVEILLANCE")
        if mode is None:
            return RecommendedAction(
                description="Vérification du point de mesure concerné et confirmation "
                            "par une seconde source avant toute intervention.",
                urgency=urgency,
                execution_window="EN_MARCHE",
                responsible="Service Instrumentation PS III",
            )

        # LA TACHE RETENUE EST LA PLUS FREQUENTE DU MODE, PAS LA PREMIERE ECRITE.
        # `plan_maintenance_ref[0]` dependait de l'ordre de saisie du YAML :
        # pour FAISCEAU_BOUCHAGE, refs ["B", "H"], la recommandation citait le
        # controle d'epaisseurs bisannuel plutot que le changement octennal —
        # correct par chance. Inverser les deux lettres dans le referentiel
        # aurait fait recommander un remplacement de faisceau sur une derive
        # naissante. On retient explicitement la tache de cadence la plus
        # courte : c'est la premiere action que le plan preventif prevoit.
        task_ref = self._tache_la_plus_frequente(mode.plan_maintenance_ref)
        task = self.domain.maintenance_task(task_ref) if task_ref else None
        needs_stop = self.domain.task_requires_shutdown(task_ref)

        # La fenetre d'execution vient de l'etat exige par la tache du plan
        # preventif, jamais de la severite. Une severite eleve accelere la
        # QUALIFICATION, elle ne rend pas realisable en marche une operation
        # qui exige la consignation des circuits.
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

        # Le texte enonce les deux horizons cote a cote : c'est ce qui empeche
        # de lire « sous 24 h » comme un ordre d'intervention immediate.
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

        responsible = ("Service Instrumentation PS III" if mode.code == "CAPTEUR_DEFAILLANT"
                       else "Service Mécanique PS III")

        return RecommendedAction(
            description=desc,
            urgency=urgency,
            execution_window=window,
            requires_shutdown=needs_stop,
            maintenance_task_ref=task_ref,
            checklist_ref="INSPECTION_INTERNE" if needs_stop else "INSPECTION_EXTERNE",
            responsible=responsible,
        )

    def _calibrate_confidence(self, result: DetectionResult, lead, mode) -> float:
        """Calibre la confiance sur la force reelle des preuves.

        LE BAREME EST CELUI DU CONTROLEUR, PAS UNE SECONDE IMPLEMENTATION.
        `schemas.confiance_justifiable` affirme que « deux baremes qui doivent
        coincider ne se recopient pas, ils se partagent » et que « toute
        divergence future devient impossible par construction ». C'etait faux :
        cette methode reimplementait une formule differente — base 0,55 contre
        0,50, penalite binaire de 0,30 sur l'observabilite au lieu d'une
        graduation, corroboration creditee ici et ignoree la. Ecart mesure
        jusqu'a 0,25 point sur un mode partiellement observe, a 0,05 point de
        declencher une reserve de sous-confiance a l'ecran.

        Une seule fonction calcule desormais la valeur; l'agent l'ANNONCE, le
        controleur la VERIFIE, et la divergence est reellement impossible.

        Args:
            result: Sortie de la detection.
            lead: Constatation dominante (conservee pour la signature).
            mode: Mode AMDEC associe.

        Returns:
            Confiance dans [0.15, 0.95].
        """
        # L'OBSERVABILITE PORTE SUR TOUS LES MODES INVOQUES, PAS SUR LE SEUL
        # MODE DOMINANT. Le controleur prend le minimum sur `amdec_modes`; ne
        # retenir ici que celui de la constatation dominante rouvrait la
        # divergence par une autre porte : une decision citant a la fois un mode
        # pleinement observe et un mode partiel aurait ete annoncee a 0,80 et
        # jugee a 0,70.
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
        """Rassemble les valeurs numeriques citees, pour verification par le Judge.

        On y met les preuves de la constatation dominante ET les grandeurs de
        conduite principales : plus la decision expose de valeurs verifiables,
        plus le controle du Judge a de prise. Une decision qui ne cite rien
        n'est pas refutable, donc pas fiable.

        Args:
            result: Sortie de la detection.
            lead: Constatation dominante.

        Returns:
            Dictionnaire {grandeur: valeur}.
        """
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
    """Formate les grandeurs cles pour les citer dans un diagnostic nominal.

    Args:
        m: Dictionnaire de mesures.

    Returns:
        Chaine du type "entree 94.2 degC, sortie 65.9 degC, debit 56.4 m3/h".
    """
    parts = []
    for key, label, unit in (
        ("T_ACID_IN", "entree acide", "degC"),
        ("T_ACID_OUT", "sortie acide", "degC"),
        ("F_ACID", "debit acide", "m3/h"),
        ("conc_min", "titre", "%"),
    ):
        if key in m and m[key] is not None:
            parts.append(f"{label} {m[key]:.2f} {unit}")
    return ", ".join(parts) + "." if parts else "valeurs indisponibles."


# ── Mode LLM ──────────────────────────────────────────────────────────────────

AGENT_SYSTEM = """Tu es l'agent de diagnostic du refroidisseur d'acide de sechage E7301
(atelier sulfurique PS III, Maroc Chimie, OCP). Tu rediges pour un ingenieur
fiabilite qui va decider d'une intervention.

## EQUIPEMENT
{equipment}

## POINTS DE MESURE ET SEUILS
{tags}

## AMDEC DE REFERENCE (analyse OCP du 23/09/2019)
{amdec}

## CE QUE LE SYSTEME NE PEUT PAS VOIR
{blind_spots}

## REGLES ABSOLUES

1. Tu ne cites QUE des valeurs presentes dans le dossier de faits. Inventer une
   mesure est la faute la plus grave possible — elle sera detectee et sanctionnee.
2. Tu ne diagnostiques JAMAIS un mode declare non observable. Si les faits
   evoquent un tel mode, tu dis explicitement qu'une inspection physique est requise.
3. Si l'etat process n'est pas RUNNING, aucun diagnostic de performance de
   l'echangeur n'est recevable : dis-le.
4. Ta confiance doit refleter la force des preuves. Preuves faibles ou base de
   mesure degradee => confiance basse. Une confiance elevee sans preuve solide
   sera sanctionnee.
5. L'action recommandee doit etre executable a PS III : si elle exige un arret
   process, tu le dis et tu mentionnes la consignation. Tu ne prescris jamais
   une intervention en marche sur un circuit acide.
6. L'encrassement se lit sur le COEFFICIENT D'ECHANGE GLOBAL, et sur rien
   d'autre. Un deficit persistant de ce coefficient a debit, temperature et eau
   de mer donnes en est la signature. L'effort de regulation n'est PAS une
   preuve : il vaut, a l'algebre pres, l'ecart de consigne change de signe, et
   un exces d'effort designe un regime de conduite, jamais une degradation.

## SORTIE
Reponds UNIQUEMENT par un objet JSON valide, sans texte autour :
{{
  "severity": "NORMAL" | "INFO" | "WARNING" | "CRITICAL",
  "amdec_modes": ["CODE", ...],
  "diagnosis": "diagnostic en 2 a 4 phrases, avec les valeurs mesurees et leurs unites",
  "reasoning": "chaine de raisonnement en 2 a 4 phrases",
  "recommended_action": {{
    "description": "action concrete et executable",
    "urgency": "AUCUNE" | "SOUS_SURVEILLANCE" | "SOUS_24H" | "SOUS_8H" | "IMMEDIATE",
    "requires_shutdown": true | false,
    "maintenance_task_ref": "A".."H" ou null,
    "checklist_ref": "INSPECTION_EXTERNE" | "INSPECTION_INTERNE" | null,
    "responsible": "service concerne"
  }},
  "confidence": 0.0 a 1.0,
  "cited_values": {{"nom_grandeur": valeur_numerique, ...}}
}}
"""


class DetectionAgent:
    """Agent de diagnostic, avec bascule automatique LLM -> regles.

    Attributes:
        domain: Connaissance domaine.
        composer: Compositeur par regles (toujours disponible).
        llm: Client Gemini, ou None si indisponible.
    """

    def __init__(self, domain: DomainKnowledge | None = None, use_llm: bool = True) -> None:
        """Initialise l'agent.

        Args:
            domain: Connaissance domaine (chargee par defaut).
            use_llm: Tenter d'utiliser le LLM. Bascule silencieusement sur les
                     regles si la cle API ou la librairie manquent.
        """
        self.domain = domain or load_domain()
        self.composer = RuleBasedComposer(self.domain)
        self.llm = _try_build_llm() if use_llm else None
        logger.info(f"Agent de detection initialise — mode "
                    f"{'LLM + regles' if self.llm else 'regles seules'}")

    @property
    def mode(self) -> str:
        """Mode de production effectif ('llm' ou 'rules')."""
        return "llm" if self.llm else "rules"

    def analyze(self, result: DetectionResult, use_llm: bool = True) -> AgentDecision:
        """Produit un diagnostic a partir d'une detection.

        Args:
            result: Sortie du detecteur pour un horodatage.
            use_llm: Autoriser la redaction LLM pour cet appel. Le rejeu temps
                     reel le desactive afin de garantir une latence bornee.

        Returns:
            AgentDecision. Toujours valide : en cas d'echec du LLM, la decision
            par regles est retournee.
        """
        case = build_case_file(result, self.domain)
        baseline = self.composer.compose(result, case)
        if self.llm is None or not use_llm:
            return baseline
        try:
            return self._analyze_llm(result, case, baseline)
        except Exception as e:
            # Coupe-circuit : une cle invalide ou un service indisponible ne
            # doit pas bloquer chaque point du rejeu ni provoquer une rafale
            # de requetes identiques. Le mode regles reste completement
            # fonctionnel jusqu'au prochain redemarrage configure.
            self.llm = None
            logger.warning(
                f"Agent LLM indisponible ({type(e).__name__}: {e}) — "
                "coupe-circuit ouvert, repli sur les regles"
            )
            return baseline

    def _analyze_llm(
        self, result: DetectionResult, case: dict[str, Any], baseline: AgentDecision
    ) -> AgentDecision:
        """Fait rediger le diagnostic par le LLM a partir du dossier de faits.

        Args:
            result: Sortie de la detection.
            case: Dossier de faits.
            baseline: Decision par regles, servant de valeur de repli.

        Returns:
            AgentDecision produite par le LLM.
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        system = AGENT_SYSTEM.format(
            equipment=self.domain.briefing_equipment(),
            tags=self.domain.briefing_tags(),
            amdec=self.domain.briefing_amdec(),
            blind_spots=self.domain.briefing_blind_spots(),
        )
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
            cited_values={k: float(v) for k, v in (data.get("cited_values") or {}).items()
                          if isinstance(v, (int, float)) and not isinstance(v, bool)},
            generated_by="llm",
        )


# ── Utilitaires ───────────────────────────────────────────────────────────────

def _try_build_llm():
    """Instancie le client Gemini si tout est disponible.

    Returns:
        Le client LangChain, ou None si la librairie ou la cle manquent.
    """
    try:
        from src.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_TIMEOUT_S
        if not GEMINI_API_KEY:
            logger.info("GEMINI_API_KEY absente — les agents fonctionnent en mode regles")
            return None
        from langchain_google_genai import ChatGoogleGenerativeAI
        # `timeout` EST OBLIGATOIRE. Sans lui, un appel sortant qui ne repond
        # pas bloque le thread appelant sans limite. La redaction est une
        # couche facultative : expirer et retomber sur la formulation
        # deterministe vaut mieux que de figer la supervision.
        return ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            google_api_key=GEMINI_API_KEY,
            temperature=0.1,
            max_retries=0,
            timeout=GEMINI_TIMEOUT_S,
        )
    except ImportError as e:
        logger.info(f"LangChain/Gemini non installe ({e}) — mode regles")
        return None


def _extract_json(raw: str) -> dict:
    """Extrait le premier objet JSON d'une reponse LLM.

    Args:
        raw: Texte brut renvoye par le modele.

    Returns:
        Le dictionnaire decode.

    Raises:
        ValueError: Si aucun JSON exploitable n'est trouve.
    """
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}") + 1
    if start < 0 or end <= start:
        raise ValueError(f"Aucun JSON dans la reponse: {raw[:200]}")
    return json.loads(text[start:end])
