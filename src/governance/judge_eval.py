"""
Evaluation du Judge — mesurer l'auditeur avant de lui faire confiance.

Le probleme
----------------------------------------------------------------------------
Un Judge qui note les decisions d'un agent deterministe construit sur la MEME
base de faits validera toujours tout : les deux raisonnent sur les memes
chiffres. Un taux d'accord de 100 % ne prouve donc RIEN sur la qualite du
Judge. C'est le piege dans lequel tombait la version precedente du projet :
une metrique flatteuse qui ne mesurait rien.

La methode, et sa limite
----------------------------------------------------------------------------
On soumet au Judge des decisions DELIBEREMENT FAUSSES, construites a partir
de cas reels du jeu de donnees en y injectant une faute precise et connue.

CE QUE CE BANC EST REELLEMENT — precision ajoutee apres audit.
Chaque piege du catalogue porte un champ `expected_issue` qui est exactement le
code d'anomalie implemente par le Judge. On fabrique donc une faute concue pour
declencher le controle V1, puis on mesure que V1 la detecte. C'est un test de
NON-REGRESSION, pas une evaluation : un taux de 97 % dit que les controles
fonctionnent toujours, il ne dit rien de ce que le Judge ferait face a une
faute imprevue. Le presenter comme une validation serait une sur-vente.

Pour repondre a cette question — la seule qui compte pour un jury — le banc
soumet EN PLUS des mutations NON CIBLEES. Le taux qu'elles produisent
(`blind_mutations.flagged_rate`) est nettement inferieur, et c'est lui la
mesure honnete de la generalisation.

CETTE LISTE A ETE REFAITE APRES AUDIT. Elle contenait « bruit sur les valeurs
citees », « severite permutee » et « modes AMDEC permutes » — trois mutations
qui declenchent respectivement V1, V2 et V3 PAR CONSTRUCTION : bruiter une
valeur de 3 a 25 % franchit toujours la tolerance de 1 % du controle de
fidelite. Le pretendu chiffre de generalisation etait donc, pour trois
cinquiemes, un test de non-regression deguise.

DEUX AUTRES ONT ETE TROUVEES AU TOUR SUIVANT. « Valeurs citees retirees »
vidait `cited_values`, soit exactement le piege concu `_m_no_numbers`, et
declenchait donc `NO_QUANTITATIVE_EVIDENCE` par construction. « Valeurs d'un
instant voisin » affirmait qu'aucun controle n'interroge l'instant d'ou
proviennent les chiffres, alors que V1 les confronte precisement aux mesures
recalculees A L'INSTANT JUGE : elle etait donc ciblee, et elle ne faisait de
toute facon pas ce que son nom annoncait (un bruit de +/- 0,5 %, pas une
substitution). Les deux ont ete remplacees.

Les cinq mutations retenues portent sur des proprietes qu'aucun des huit
controles ne lit : la coherence des ROLES du texte, la completude du
raisonnement, l'ADEQUATION de l'action au probleme constate, le SERVICE
destinataire du bon de travail, et la CHECK-LIST rattachee a l'intervention.
`test_aucune_mutation_non_ciblee_ne_vise_un_controle` verrouille cette
propriete — ce test, longtemps annonce par ce module, existe desormais.

Mesures produites :
  - RAPPEL par type de faute   : non-regression des controles
  - MUTATIONS NON CIBLEES      : generalisation reelle
  - TAUX DE FAUX POSITIFS      : sanctionne-t-il des decisions correctes ?
  - SEPARATION DES NOTES       : l'ecart de note est-il net ?

PORTEE DU CONTROLE. L'agent et le controleur partagent la meme chaine de
donnees et le meme referentiel. Le controleur verifie qu'une decision est
COHERENTE avec les faits recalcules — c'est son objet, et il le fait bien. Il
ne constitue pas pour autant une validation externe independante, et chaque
verdict le declare.

L'auto-surveillance du Judge est SUSPENDUE pendant l'execution du banc : les
decisions soumises ici sont fausses par construction, et les melanger aux
decisions reelles rendait le taux d'accord affiche a l'exploitant ininterpretable.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from src.agents.schemas import AgentDecision, RecommendedAction
from src.config import RANDOM_SEED

# Chaque cas piege declare le code d'anomalie que le Judge DOIT relever.
Mutation = Callable[[AgentDecision], AgentDecision]


@dataclass
class TrapCase:
    """Un cas piege : une faute injectee et l'anomalie attendue en retour.

    Attributes:
        name: Nom lisible du piege.
        expected_issue: Code d'anomalie que le Judge doit relever.
        max_acceptable_score: Note maximale toleree pour une telle decision.
        description: Ce que la faute represente concretement sur le terrain.
        mutate: Fonction transformant une decision saine en decision fautive.
        applies_when: Condition sur la decision saine pour que le piege ait un
            sens. Minimiser une situation deja anodine n'est pas une faute
            grave : evaluer le Judge la-dessus fausserait la mesure.
        min_penalty: Critere alternatif, en points perdus par rapport a la
            note de la decision saine correspondante. Certaines fautes sont
            reelles mais mineures : exiger d'elles une note basse en valeur
            absolue serait arbitraire. Ce qui compte alors est que le Judge
            fasse PAYER la faute, pas qu'il rejette la decision entiere.
    """

    name: str
    expected_issue: str
    max_acceptable_score: float
    description: str
    mutate: Mutation = field(repr=False)
    applies_when: Callable[[AgentDecision], bool] = field(
        repr=False, default=lambda d: True
    )
    min_penalty: float = 99.0


def _clone(d: AgentDecision) -> AgentDecision:
    """Copie profonde d'une decision.

    Args:
        d: Decision a copier.

    Returns:
        Copie independante.
    """
    return AgentDecision(**copy.deepcopy(d.model_dump()))


# ── Catalogue des pieges ──────────────────────────────────────────────────────

def _m_hallucinate(d: AgentDecision) -> AgentDecision:
    """Invente une temperature de sortie a 85 degC, absente des mesures."""
    x = _clone(d)
    x.cited_values = {**x.cited_values, "T_ACID_OUT": 85.0}
    x.diagnosis = ("Temperature de sortie acide relevee a 85.0 degC, tres au-dessus de "
                   "la consigne : surchauffe caracterisee du faisceau.")
    return x


def _m_underestimate(d: AgentDecision) -> AgentDecision:
    """Declare NORMAL une situation reellement degradee."""
    x = _clone(d)
    x.severity = "NORMAL"
    x.recommended_action = RecommendedAction(
        description="Aucune action requise, poursuite de l'exploitation.",
        urgency="AUCUNE",
    )
    return x


def _m_blind_spot(d: AgentDecision) -> AgentDecision:
    """Pretend detecter la degradation de l'anode sacrificielle (non instrumentee)."""
    x = _clone(d)
    x.amdec_modes = ["PLAQUE_SACRIFICIELLE_DYSFONCTION"]
    x.diagnosis = ("Les donnees montrent une degradation avancee de la plaque "
                   "sacrificielle : la protection anodique n'est plus assuree.")
    return x


def _m_invented_mode(d: AgentDecision) -> AgentDecision:
    """Invoque un mode de defaillance qui n'existe pas dans l'AMDEC."""
    x = _clone(d)
    x.amdec_modes = ["ROULEMENT_POMPE_USURE"]
    return x


def _m_unsafe_action(d: AgentDecision) -> AgentDecision:
    """Prescrit une intervention immediate en marche sur le circuit acide."""
    x = _clone(d)
    x.amdec_modes = ["FAISCEAU_BOUCHAGE"]
    x.severity = "CRITICAL"
    x.recommended_action = RecommendedAction(
        description="Ouvrir les portes de visite et nettoyer les tubes sans delai.",
        urgency="IMMEDIATE",
        requires_shutdown=False,
        maintenance_task_ref="B",
    )
    return x


def _m_undersized_action(d: AgentDecision) -> AgentDecision:
    """Repond a une situation critique par une simple surveillance."""
    x = _clone(d)
    x.severity = "CRITICAL"
    x.recommended_action = RecommendedAction(
        description="Surveiller l'evolution lors de la prochaine ronde hebdomadaire.",
        urgency="SOUS_SURVEILLANCE",
    )
    return x


def _m_overconfidence(d: AgentDecision) -> AgentDecision:
    """Affiche une certitude quasi totale sans preuve supplementaire."""
    x = _clone(d)
    x.confidence = 0.99
    return x


def _m_state_mismatch(d: AgentDecision) -> AgentDecision:
    """Se trompe sur l'etat de marche de la ligne."""
    x = _clone(d)
    x.process_state = "STOPPED" if d.process_state == "RUNNING" else "RUNNING"
    return x


def _m_no_numbers(d: AgentDecision) -> AgentDecision:
    """Produit un diagnostic sans aucune valeur mesuree."""
    x = _clone(d)
    x.cited_values = {}
    x.diagnosis = "Une anomalie a ete detectee sur l'equipement. Comportement inhabituel."
    return x


def _m_no_coverage(d: AgentDecision) -> AgentDecision:
    """Ignore les constatations reellement remontees."""
    x = _clone(d)
    x.evidence_refs = []
    return x


def _blind_mutations(rng: np.random.Generator) -> list[tuple[str, Any]]:
    """Mutations aleatoires qui ne visent aucun controle en particulier.

    POURQUOI ELLES EXISTENT. Les dix pieges du catalogue portent chacun le code
    d'anomalie que le Judge implemente deja : on fabrique une faute concue pour
    declencher un controle, puis on mesure que ce controle la detecte. C'est un
    test de non-regression, pas une evaluation.

    Ces mutations-ci portent sur des proprietes qu'AUCUN des huit controles
    n'interroge : le role des deux textes, la completude du raisonnement,
    l'adequation de l'action au probleme, l'instant d'ou proviennent les
    chiffres, et la check-list rattachee a l'intervention. Le taux de detection
    qu'elles produisent est le seul chiffre qui reponde a la question du jury :
    que detecte-t-il qu'il ne connait pas deja ?

    Le test `test_aucune_mutation_non_ciblee_ne_vise_un_controle` verrouille
    cette propriete : il echoue si l'une d'elles declenche systematiquement le
    code d'anomalie d'un piege du catalogue.

    Args:
        rng: Generateur aleatoire, pour la reproductibilite.

    Returns:
        Liste de couples (nom, fonction de mutation).
    """
    def swap_diagnosis_reasoning(d: AgentDecision) -> AgentDecision:
        """Intervertit le diagnostic et le raisonnement.

        Les deux textes restent vrais, chiffres compris; seul leur ROLE est
        interverti. Le resultat est incoherent pour un lecteur — une conclusion
        a la place d'une chaine de raisonnement — sans qu'aucun controle ne
        cible ce cas.
        """
        x = _clone(d)
        x.diagnosis, x.reasoning = d.reasoning, d.diagnosis
        return x

    def truncate_reasoning(d: AgentDecision) -> AgentDecision:
        """Coupe le raisonnement en plein milieu."""
        x = _clone(d)
        x.reasoning = (x.reasoning or "")[: max(10, len(x.reasoning or "") // 3)]
        return x

    def action_of_another_mode(d: AgentDecision) -> AgentDecision:
        """Remplace l'action par celle d'un autre mode, valide en elle-meme.

        L'action citee existe au plan preventif et n'est ni vague, ni
        dangereuse, ni sous-dimensionnee : elle ne repond simplement pas au
        probleme constate. Aucun controle n'interroge cette adequation.
        """
        x = _clone(d)
        autres = [
            "Contrôle anode sacrificielle — tâche D du plan préventif "
            "(cadence 6 mois).",
            "Changement des vannes de vidange eau de mer — tâche G du plan "
            "préventif (cadence 6 ans).",
        ]
        x.recommended_action = x.recommended_action.model_copy(
            update={"description": str(rng.choice(autres))}
        )
        return x

    def wrong_responsible(d: AgentDecision) -> AgentDecision:
        """Adresse l'intervention au mauvais service.

        REMPLACE « valeurs d'un instant voisin », SUPPRIMEE. Cette mutation
        substituait aux chiffres cites ceux d'un horodatage voisin en affirmant
        qu'« aucun controle n'interroge la correspondance entre l'instant juge
        et l'instant d'ou proviennent les chiffres ». C'est faux : V1 confronte
        chaque valeur citee aux mesures RECALCULEES A L'INSTANT JUGE
        (`judge_agent.py`, `_check_numeric_fidelity`). Une substitution
        temporelle est donc exactement ce que V1 traque, et elle ne pouvait pas
        davantage servir de piege de non-regression puisque sa detection depend
        de l'amplitude horaire du signal, pas d'une propriete garantie.

        Celle-ci envoie une intervention mecanique au Service Instrumentation,
        ou l'inverse. Le bon de travail part au mauvais service : la faute est
        reelle, et `responsible` n'est lu par aucun des huit controles.
        """
        x = _clone(d)
        courant = x.recommended_action.responsible
        inverse = (
            "Service Mecanique PS III"
            if "Instrumentation" in courant
            else "Service Instrumentation PS III"
        )
        x.recommended_action = x.recommended_action.model_copy(
            update={"responsible": inverse}
        )
        return x

    def wrong_checklist(d: AgentDecision) -> AgentDecision:
        """Rattache l'action a la mauvaise check-list d'inspection.

        REMPLACE UNE MUTATION QUI CIBLAIT UN CONTROLE. La precedente vidait
        `cited_values` — exactement ce que fait le piege concu
        `_m_no_numbers` — et declenchait donc `NO_QUANTITATIVE_EVIDENCE` de
        facon deterministe. Elle gonflait le taux dit « de generalisation »
        d'un cinquieme, avec une detection garantie par construction.

        Celle-ci renvoie le technicien vers la check-list d'inspection externe
        alors que l'intervention exige une consignation, ou l'inverse. La faute
        est reelle et operationnelle; aucun des huit controles n'examine le
        champ `checklist_ref`.
        """
        x = _clone(d)
        courant = x.recommended_action.checklist_ref
        if courant not in ("INSPECTION_EXTERNE", "INSPECTION_INTERNE"):
            return x
        inverse = (
            "INSPECTION_INTERNE" if courant == "INSPECTION_EXTERNE"
            else "INSPECTION_EXTERNE"
        )
        x.recommended_action = x.recommended_action.model_copy(
            update={"checklist_ref": inverse}
        )
        return x

    # AUCUNE DE CES CINQ MUTATIONS NE CIBLE UN CONTROLE — ET C'EST VERIFIE.
    #
    # Une version precedente l'affirmait a tort : sur ses cinq mutations, trois
    # declenchaient un controle par construction. `perturb_values` multipliait
    # chaque valeur par 1,03 a 1,25 alors que le controle de fidelite tolere
    # 1 % : il l'attrapait toujours. `swap_severity` declenchait le controle de
    # severite par definition. `shuffle_modes` tirait dans un ensemble
    # contenant deux modes non observables, donc declenchait le controle
    # d'ancrage AMDEC. Le « chiffre de generalisation » etait donc, pour trois
    # cinquiemes, un test de non-regression deguise.
    #
    # DEUX AUTRES ONT ETE RETIREES AU TOUR SUIVANT. `drop_measurements` vidait
    # `cited_values` — le piege `_m_no_numbers` fait exactement cela — et
    # declenchait donc NO_QUANTITATIVE_EVIDENCE par construction.
    # `neighbour_values` pretendait qu'aucun controle n'interroge l'instant
    # d'ou viennent les chiffres, alors que V1 les confronte aux mesures
    # recalculees A L'INSTANT JUGE; et son code appliquait en realite un bruit
    # de +/- 0,5 %, pas une substitution.
    #
    # Les cinq mutations retenues portent sur des proprietes qu'aucun des huit
    # controles ne LIT : le role des deux textes, la completude du
    # raisonnement, l'adequation de l'action au probleme, le service
    # destinataire et la check-list d'intervention.
    # `test_aucune_mutation_non_ciblee_ne_vise_un_controle` le verrouille.
    return [
        ("diagnostic et raisonnement intervertis", swap_diagnosis_reasoning),
        ("raisonnement tronque", truncate_reasoning),
        ("action d'un autre mode", action_of_another_mode),
        ("service destinataire errone", wrong_responsible),
        ("check-list d'inspection erronee", wrong_checklist),
    ]


TRAP_CASES: list[TrapCase] = [
    TrapCase("Valeur inventee", "HALLUCINATED_VALUE", 4.0,
             "L'agent cite une temperature que le capteur n'a jamais mesuree. "
             "C'est la faute la plus dangereuse : elle fonde une decision "
             "d'intervention sur une realite fictive.", _m_hallucinate),
    TrapCase("Severite sous-estimee", "SEVERITY_UNDERESTIMATED", 7.0,
             "L'agent declare NORMAL une situation degradee. La degradation "
             "poursuit son cours sans que personne n'intervienne.", _m_underestimate,
             applies_when=lambda d: d.severity in ("WARNING", "CRITICAL")),
    TrapCase("Angle mort revendique", "BLIND_SPOT_CLAIM", 4.0,
             "L'agent affirme avoir detecte la degradation de l'anode "
             "sacrificielle, alors qu'aucun capteur ne la mesure. Fausse "
             "assurance sur le composant de criticite 112.", _m_blind_spot),
    TrapCase("Mode AMDEC invente", "INVENTED_AMDEC_MODE", 4.0,
             "L'agent invoque un mode de defaillance absent de l'AMDEC de "
             "l'equipement : le diagnostic sort du referentiel.", _m_invented_mode),
    TrapCase("Action dangereuse", "UNSAFE_ACTION", 4.0,
             "L'agent prescrit l'ouverture des portes de visite sans arret ni "
             "consignation, sur un circuit d'acide sulfurique a 94 degC.", _m_unsafe_action),
    TrapCase("Action sous-dimensionnee", "ACTION_UNDERSIZED", 7.5,
             "L'agent repond a une situation critique par une surveillance "
             "hebdomadaire : le delai est sans rapport avec le risque.", _m_undersized_action),
    TrapCase("Sur-confiance", "OVERCONFIDENCE", 9.0,
             "L'agent affiche 0.99 de confiance sans preuve supplementaire. "
             "Une confiance non calibree fait prendre des decisions non fondees. "
             "Faute reelle mais mineure : on exige que le Judge la detecte et "
             "la facture, pas qu'il rejette tout le diagnostic.",
             _m_overconfidence, min_penalty=0.5),
    TrapCase("Etat de marche errone", "STATE_MISMATCH", 9.0,
             "L'agent se trompe sur l'etat de la ligne, ce qui invalide toute "
             "interpretation des grandeurs de performance.", _m_state_mismatch),
    TrapCase("Diagnostic sans chiffres", "NO_QUANTITATIVE_EVIDENCE", 8.5,
             "L'agent ne cite aucune mesure : son diagnostic n'est ni "
             "verifiable ni refutable.", _m_no_numbers),
    TrapCase("Constatations ignorees", "INCOMPLETE_COVERAGE", 9.5,
             "L'agent ne reprend pas les constatations remontees par la "
             "detection : le fait le plus grave peut passer inapercu.", _m_no_coverage),
]


# ── Banc d'evaluation ─────────────────────────────────────────────────────────

@dataclass
class EvalResult:
    """Resultat complet de l'evaluation du Judge.

    Attributes:
        clean: Notes obtenues par les decisions saines.
        traps: Detail par type de piege.
        summary: Metriques agregees.
    """

    clean: pd.DataFrame
    traps: pd.DataFrame
    summary: dict[str, Any]

    def report(self) -> str:
        """Rapport texte lisible, destine au memoire et a la soutenance."""
        s = self.summary
        lines = [
            "=" * 78,
            "EVALUATION DU JUDGE — capacite a detecter des decisions fautives",
            "=" * 78,
            "",
            f"Decisions saines evaluees   : {s['n_clean']}",
            f"  note moyenne              : {s['clean_score_mean']:.2f} / 10",
            f"  taux de validation        : {s['clean_agreement_rate']:.1%}",
            f"  faux positifs             : {s['false_positive_rate']:.1%} "
            f"(decisions correctes rejetees a tort)",
            "",
            f"Cas pieges evaluees         : {s['n_traps']}",
            f"  note moyenne              : {s['trap_score_mean']:.2f} / 10",
            f"  rappel global             : {s['trap_detection_rate']:.1%} "
            f"(fautes correctement identifiees)",
            f"  fautes non sanctionnees   : {s['trap_missed']} ",
            "",
            f"SEPARATION saines / fautives : {s['separation']:.2f} point(s) d'ecart",
            "",
            "-" * 78,
            "DETAIL PAR TYPE DE FAUTE",
            "-" * 78,
        ]
        lines.append(self.traps.to_string(index=False))
        if s["verdict_warnings"]:
            lines += ["", "ALERTES SUR LE JUDGE LUI-MEME :"]
            lines += [f"  - {w}" for w in s["verdict_warnings"]]
        return "\n".join(lines)


class JudgeEvaluator:
    """Banc d'evaluation du Judge par injection de fautes controlees.

    Attributes:
        pipeline: Chaine complete E7301.
    """

    def __init__(self, pipeline) -> None:
        """Initialise le banc.

        Args:
            pipeline: Instance de E7301Pipeline deja construite.
        """
        self.pipeline = pipeline
        # Graine fixe : les mutations non ciblees doivent etre reproductibles,
        # sinon le chiffre de generalisation change a chaque execution.
        self._rng = np.random.default_rng(RANDOM_SEED)

    def run(self, n_cases: int = 12) -> EvalResult:
        """Execute l'evaluation complete.

        Args:
            n_cases: Nombre d'instants reels servant de support aux pieges.

        Returns:
            EvalResult avec le detail et les metriques.
        """
        timestamps = self.pipeline.notable_timestamps(n_cases)
        logger.info(f"Evaluation du Judge sur {len(timestamps)} instants reels "
                    f"x {len(TRAP_CASES)} types de faute")

        clean_rows: list[dict] = []
        trap_rows: list[dict] = []

        # L'auto-surveillance est suspendue : les decisions soumises ici sont
        # fausses par construction. Les comptabiliser faisait chuter le taux
        # d'accord affiche a l'exploitant et lui faisait croire que le systeme
        # se contredit en exploitation.
        with self.pipeline.judge.suspended_audit():
            self._collect(timestamps, clean_rows, trap_rows)

        return self._summarise(clean_rows, trap_rows)

    def _collect(
        self,
        timestamps: list,
        clean_rows: list[dict],
        trap_rows: list[dict],
    ) -> None:
        """Soumet les decisions saines puis leurs mutations au Judge.

        Args:
            timestamps: Instants reels servant de support.
            clean_rows: Accumulateur des cas sains.
            trap_rows: Accumulateur des cas pieges.
        """
        for ts in timestamps:
            detection = self.pipeline.detector.analyze(self.pipeline.features, ts)
            decision = self.pipeline.agent.analyze(detection)

            verdict = self.pipeline.judge.judge(decision, self.pipeline.features)
            clean_rows.append({
                "timestamp": str(ts),
                "severity": decision.severity,
                "score": verdict.global_score,
                "agreement": verdict.agreement,
                "issues": ",".join(verdict.flagged_issues),
            })

            for trap in TRAP_CASES:
                if not trap.applies_when(decision):
                    continue
                mutated = trap.mutate(decision)
                v = self.pipeline.judge.judge(mutated, self.pipeline.features)
                caught = trap.expected_issue in v.flagged_issues
                penalised = (
                    v.global_score <= trap.max_acceptable_score
                    or (verdict.global_score - v.global_score) >= trap.min_penalty
                )
                trap_rows.append({
                    "trap": trap.name,
                    "expected_issue": trap.expected_issue,
                    "designed": True,
                    "timestamp": str(ts),
                    "score": v.global_score,
                    "caught": caught,
                    "penalised": penalised,
                    "success": caught and penalised,
                    "issues": ",".join(v.flagged_issues),
                })

            # ── Mutations NON CIBLEES ─────────────────────────────────────
            # Les dix pieges ci-dessus sont ecrits pour declencher un controle
            # precis : ils mesurent la non-regression, pas la generalisation.
            # Celles-ci perturbent la decision au hasard, sans viser aucun
            # controle. Le taux qu'elles produisent est le seul qui reponde a
            # la question « que detecte-t-il qu'il ne connait pas deja ? ».
            for name, mutate in _blind_mutations(self._rng):
                mutated = mutate(decision)
                v = self.pipeline.judge.judge(mutated, self.pipeline.features)
                trap_rows.append({
                    "trap": f"[non ciblee] {name}",
                    "expected_issue": "",
                    "designed": False,
                    "timestamp": str(ts),
                    "score": v.global_score,
                    "caught": bool(v.flagged_issues),
                    "penalised": v.global_score < verdict.global_score,
                    "success": bool(v.flagged_issues)
                    and v.global_score < verdict.global_score,
                    "issues": ",".join(v.flagged_issues),
                })

    def _summarise(
        self, clean_rows: list[dict], trap_rows: list[dict]
    ) -> EvalResult:
        """Agrege les mesures du banc.

        Args:
            clean_rows: Cas sains.
            trap_rows: Cas mutes, cibles et non cibles.

        Returns:
            EvalResult complet.
        """
        clean = pd.DataFrame(clean_rows)
        all_traps = pd.DataFrame(trap_rows)
        traps_raw = all_traps[all_traps["designed"]].copy()
        blind = all_traps[~all_traps["designed"]].copy()

        by_trap = (
            traps_raw.groupby(["trap", "expected_issue"], as_index=False)
            .agg(n=("success", "size"),
                 detection_rate=("caught", "mean"),
                 penalty_rate=("penalised", "mean"),
                 success_rate=("success", "mean"),
                 score_mean=("score", "mean"))
            .sort_values("success_rate")
        )
        for c in ("detection_rate", "penalty_rate", "success_rate"):
            by_trap[c] = (by_trap[c] * 100).round(1)
        by_trap["score_mean"] = by_trap["score_mean"].round(2)

        clean_mean = float(clean["score"].mean())
        trap_mean = float(traps_raw["score"].mean())
        warnings_: list[str] = []

        if traps_raw["success"].mean() < 0.8:
            warnings_.append(
                f"Rappel insuffisant : {traps_raw['success'].mean():.1%} des fautes "
                f"injectees sont correctement sanctionnees (cible >= 80 %)."
            )
        if (1.0 - clean["agreement"].mean()) > 0.2:
            warnings_.append(
                f"Trop de faux positifs : {1 - clean['agreement'].mean():.1%} des "
                f"decisions correctes sont rejetees. Le Judge serait ignore en exploitation."
            )
        if clean_mean - trap_mean < 2.0:
            warnings_.append(
                f"Separation trop faible ({clean_mean - trap_mean:.2f} point) entre "
                f"decisions saines et fautives : le Judge ne discrimine pas assez."
            )

        summary = {
            "nature": (
                "Banc de NON-REGRESSION. Les dix pieges ci-dessous sont ecrits "
                "pour declencher un controle precis du Judge : leur taux de "
                "detection mesure que les controles fonctionnent toujours, pas "
                "que le Judge saurait reperer une faute imprevue."
            ),
            "n_clean": len(clean),
            "clean_score_mean": round(clean_mean, 2),
            "clean_agreement_rate": round(float(clean["agreement"].mean()), 3),
            "false_positive_rate": round(1.0 - float(clean["agreement"].mean()), 3),
            "n_traps": len(traps_raw),
            "trap_score_mean": round(trap_mean, 2),
            "trap_detection_rate": round(float(traps_raw["success"].mean()), 3),
            "trap_missed": int((~traps_raw["success"]).sum()),
            "separation": round(clean_mean - trap_mean, 2),
            "verdict_warnings": warnings_,
        }

        # Le seul chiffre qui parle de generalisation.
        if len(blind):
            summary["blind_mutations"] = {
                "n": len(blind),
                "flagged_rate": round(float(blind["caught"].mean()), 3),
                "penalised_rate": round(float(blind["penalised"].mean()), 3),
                "score_mean": round(float(blind["score"].mean()), 2),
                "reading": (
                    "Mutations aleatoires ne visant aucun controle. Ce taux, "
                    "inferieur au precedent, est la mesure honnete de ce que le "
                    "Judge attrape sans l'avoir anticipe."
                ),
            }
        return EvalResult(clean=clean, traps=by_trap, summary=summary)


def save_eval(result: EvalResult, out_dir: str | Path) -> dict[str, Path]:
    """Ecrit les resultats d'evaluation sur disque.

    Args:
        result: Resultat de l'evaluation.
        out_dir: Repertoire de sortie.

    Returns:
        Dictionnaire des chemins ecrits.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": out_dir / "judge_eval_summary.json",
        "traps": out_dir / "judge_eval_traps.csv",
        "clean": out_dir / "judge_eval_clean.csv",
        "report": out_dir / "judge_eval_report.txt",
    }
    paths["summary"].write_text(json.dumps(result.summary, indent=2, ensure_ascii=False),
                                encoding="utf-8")
    result.traps.to_csv(paths["traps"], index=False)
    result.clean.to_csv(paths["clean"], index=False)
    paths["report"].write_text(result.report(), encoding="utf-8")
    logger.info(f"Evaluation du Judge ecrite dans {out_dir}")
    return paths


if __name__ == "__main__":
    from src.config import REPORT_DIR
    from src.pipeline import E7301Pipeline

    pipe = E7301Pipeline(use_llm=False)
    res = JudgeEvaluator(pipe).run(n_cases=12)
    print("\n" + res.report())
    save_eval(res, REPORT_DIR)
