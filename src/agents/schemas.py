"""
Contrats de donnees partages entre l'agent de detection et le Judge.

Isoler les schemas ici evite l'import circulaire entre les deux agents et
garantit qu'ils parlent exactement le meme langage — condition necessaire
pour qu'un jugement automatique ait un sens.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Severity = Literal["NORMAL", "INFO", "WARNING", "CRITICAL"]

# DEUX HORIZONS DISTINCTS, ET C'EST UNE CORRECTION DE CONCEPTION.
#
# La version precedente n'avait qu'une echelle d'urgence, ce qui produisait des
# recommandations contradictoires : « SOUS_24H — mesure des epaisseurs par
# courant de Foucault, tache a cadence 4 ans, exige un arret process a
# programmer avec la production ». On demandait sous 24 h ce qui se planifie
# sur des mois.
#
# La confusion venait de ce qu'une seule grandeur portait deux questions sans
# rapport : sous quel delai un ingenieur doit-il QUALIFIER la constatation, et
# dans quelle fenetre d'exploitation l'intervention peut-elle etre EXECUTEE.
# Elles sont desormais separees.
Urgency = Literal["AUCUNE", "SOUS_SURVEILLANCE", "SOUS_24H", "SOUS_8H", "IMMEDIATE"]
ExecutionWindow = Literal[
    "EN_MARCHE",          # realisable equipement en service
    "ARRET_PROGRAMME",    # exige un arret, a caler avec la production
    "ARRET_IMMEDIAT",     # exige de descendre la ligne sans attendre
]

# Delai maximal de QUALIFICATION associe a chaque niveau d'urgence, en heures.
# Ce delai porte sur l'analyse par un ingenieur fiabilite, pas sur la
# realisation de l'intervention.
URGENCY_HOURS: dict[str, float] = {
    "AUCUNE": float("inf"),
    "SOUS_SURVEILLANCE": 168.0,
    "SOUS_24H": 24.0,
    "SOUS_8H": 8.0,
    "IMMEDIATE": 1.0,
}

# Urgence minimale exigee par severite. Le Judge s'en sert pour detecter une
# action sous-dimensionnee (ex. "surveiller" pour un CRITICAL).
MIN_URGENCY_FOR_SEVERITY: dict[str, str] = {
    "NORMAL": "AUCUNE",
    "INFO": "SOUS_SURVEILLANCE",
    "WARNING": "SOUS_24H",
    "CRITICAL": "SOUS_8H",
}

# Constatations qui ne constituent pas une preuve supplementaire : elles
# decrivent l'etat du dispositif, pas celui de l'equipement.
_CODES_SANS_PREUVE = frozenset({
    "MODEL_ANOMALY", "MODEL_ANOMALY_ISOLATED", "NOT_RUNNING", "MODEL_UNAVAILABLE",
})

# Constatations produites par l'etage statistique.
_CODES_MODELE = frozenset({"MODEL_ANOMALY", "MODEL_ANOMALY_ISOLATED"})


def corroboration(rule_codes: list[str]) -> bool:
    """Les deux etages ont-ils parle sur le meme instant ?

    Une regle deterministe et le modele statistique qui se declenchent ensemble
    constituent une preuve plus solide que l'un des deux seul : ce sont deux
    mecanismes independants. L'agent creditait deja cette corroboration, le
    controleur non — d'ou une divergence permanente entre les deux baremes.
    Le critere est desormais calcule ici, a partir des seuls codes, donc de
    facon identique des deux cotes.

    Args:
        rule_codes: Codes des constatations de l'instant.

    Returns:
        Vrai si au moins une constatation deterministe ET une constatation du
        modele sont presentes.
    """
    codes = set(rule_codes)
    return bool(codes - _CODES_SANS_PREUVE) and bool(codes & _CODES_MODELE)


# BORNES DU BAREME DE CONFIANCE.
#
# Elles etaient ecrites en dur dans la clause de bornage, donc invisibles pour
# le controleur. Or le PLAFOND est une information de premiere importance : au
# mieux des preuves possibles — constatation deterministe, corroboration des
# deux etages, modele applicable, marche etablie, mode pleinement observe — le
# bareme ne depasse jamais 0,95. Toute confiance annoncee au-dela est donc
# injustifiable PAR CONSTRUCTION, quel que soit l'ecart a la valeur attendue.
CONFIANCE_MIN = 0.15
CONFIANCE_MAX = 0.95


def confiance_justifiable(
    *,
    rule_codes: list[str],
    model_applicable: bool,
    n_invalid_tags: int,
    process_state: str,
    mode_observabilite: str = "full",
) -> float:
    """Confiance que les FAITS justifient, indépendamment de qui les regarde.

    POURQUOI CE BAREME EST PARTAGE.
    L'agent annoncait sa confiance selon une regle, le controleur la jugeait
    selon une autre. Les deux baremes ont diverge sans que personne ne s'en
    apercoive, et le controleur a fini par accuser l'agent de sur-confiance sur
    100 % des heures d'arret — puis, une fois ce cas corrige, sur les instants
    nominaux ou le modele etait applicable. A chaque fois, la note globale
    restait haute et l'accord etait maintenu : l'anomalie ne se lisait que dans
    l'encart destine a l'exploitant.

    Deux baremes qui doivent coincider ne se recopient pas, ils se partagent.
    L'agent l'utilise pour ANNONCER, le controleur pour VERIFIER; toute
    divergence future devient impossible par construction.

    Args:
        rule_codes: Codes des constatations deterministes de l'instant.
        model_applicable: Le modele statistique etait-il exploitable ?
        n_invalid_tags: Points de mesure en defaut a cet instant.
        process_state: Etat de marche reel.
        mode_observabilite: Degre d'observabilite du mode dominant invoque.

    Returns:
        Confiance justifiable, dans [0,15 ; 0,95].
    """
    valeur = 0.5
    if any(code not in _CODES_SANS_PREUVE for code in rule_codes):
        valeur += 0.20
    # Corroboration entre les deux etages : deux mecanismes independants qui
    # concluent ensemble valent mieux qu'un seul. Terme que l'agent appliquait
    # et que le controleur ignorait.
    if corroboration(rule_codes):
        valeur += 0.10
    if model_applicable:
        valeur += 0.10
    valeur -= 0.15 * min(n_invalid_tags, 2)
    if process_state != "RUNNING":
        valeur -= 0.15
    # Un mode dont l'etat n'est pas mesurable interdit la certitude; un mode
    # partiellement observe la reduit sans l'interdire.
    valeur -= {"none": 0.30, "partial": 0.10}.get(mode_observabilite, 0.0)
    return round(min(CONFIANCE_MAX, max(CONFIANCE_MIN, valeur)), 2)


# Formulation lisible de la fenetre d'execution, pour l'exploitant.
EXECUTION_WINDOW_LABEL: dict[str, str] = {
    "EN_MARCHE": "réalisable équipement en service",
    "ARRET_PROGRAMME": "exige un arrêt, à caler avec la production",
    "ARRET_IMMEDIAT": "exige de descendre la ligne sans attendre",
}


class RecommendedAction(BaseModel):
    """Action de maintenance recommandee, formulee pour etre executable.

    Attributes:
        description: Ce qu'il faut faire, en clair.
        urgency: Delai sous lequel la constatation doit etre QUALIFIEE.
        execution_window: Fenetre d'exploitation dans laquelle l'intervention
            elle-meme peut avoir lieu. Independante de `urgency` : une derive
            peut exiger une analyse sous 24 h et une intervention au prochain
            arret programme, sans qu'il y ait la moindre contradiction.
        requires_shutdown: L'action exige-t-elle un arret process ?
        maintenance_task_ref: Reference au plan preventif (A..H) si applicable.
        checklist_ref: Check-list d'inspection a utiliser, si applicable.
        responsible: Entite qui doit intervenir.
    """

    description: str
    urgency: Urgency = "SOUS_SURVEILLANCE"
    execution_window: ExecutionWindow = "EN_MARCHE"
    requires_shutdown: bool = False
    maintenance_task_ref: str | None = None
    checklist_ref: str | None = None
    responsible: str = "Service Mecanique PS III"


class AgentDecision(BaseModel):
    """Diagnostic structure produit par l'agent de detection.

    Attributes:
        equipment_id: Identifiant de l'equipement.
        timestamp: Instant analyse (ISO 8601).
        process_state: Etat de marche au moment de l'analyse.
        severity: Severite retenue par l'agent.
        anomaly_score: Score du modele statistique.
        amdec_modes: Modes de defaillance AMDEC invoques.
        diagnosis: Diagnostic en clair, avec les valeurs mesurees.
        reasoning: Chaine de raisonnement menant au diagnostic.
        recommended_action: Action a mener.
        confidence: Confiance de l'agent dans son diagnostic [0, 1].
        evidence_refs: Codes des constatations sur lesquelles il s'appuie.
        cited_values: Valeurs numeriques citees, pour verification par le Judge.
        generated_by: 'llm' ou 'rules' — tracabilite du mode de production.
    """

    equipment_id: str = "S-PC-E7301"
    timestamp: str
    process_state: str
    severity: Severity
    anomaly_score: float = Field(ge=0.0, le=1.0, default=0.0)
    amdec_modes: list[str] = Field(default_factory=list)
    diagnosis: str
    reasoning: str
    recommended_action: RecommendedAction
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    evidence_refs: list[str] = Field(default_factory=list)
    cited_values: dict[str, float] = Field(default_factory=dict)
    generated_by: Literal["llm", "rules"] = "rules"
    # LA CONSTATATION DOMINANTE EST NOMMEE, PAS DEDUITE.
    #
    # `evidence_refs` porte TOUTES les constatations, dans l'ordre d'evaluation
    # des regles. Un consommateur qui voulait savoir laquelle a fonde la
    # decision n'avait que deux recours : reprendre `findings[0]` — ce que
    # `AlarmStore._key` faisait, et qui donne l'ordre d'ecriture des regles et
    # non la gravite — ou lire `reasoning` au motif qu'il contient la phrase
    # « Constatation dominante : ... ».
    #
    # L'agent tranche deja par `_priorite` : severite, puis defaut de mesure
    # apres diagnostic equipement, puis criticite AMDEC. Ce choix est publie
    # ici plutot que recalcule ailleurs — deux baremes qui doivent coincider ne
    # se recopient pas.
    lead_finding: str | None = None


class Check(BaseModel):
    """Resultat d'une verification elementaire du Judge.

    Attributes:
        id: Identifiant du controle.
        label: Question posee par le controle, en clair.
        passed: Le controle est-il satisfait ?
        weight: Poids du controle dans le score global.
        score: Note du controle sur 10.
        detail: Justification factuelle, avec les valeurs comparees.
        issue_codes: Codes d'anomalie normalises releves par ce controle.
            Une liste et non un code unique : un meme controle peut relever
            plusieurs manquements simultanes (par exemple un delai
            sous-dimensionne ET une action dangereuse). N'en garder qu'un
            faisait disparaitre l'autre du journal d'audit.
    """

    id: str
    label: str
    passed: bool
    weight: float
    score: float = Field(ge=0.0, le=10.0)
    detail: str
    issue_codes: list[str] = Field(default_factory=list)

    @property
    def issue_code(self) -> str | None:
        """Premier code releve, pour compatibilite d'affichage."""
        return self.issue_codes[0] if self.issue_codes else None


class JudgeVerdict(BaseModel):
    """Verdict complet du Judge sur une decision de l'agent.

    Attributes:
        timestamp: Instant juge.
        global_score: Note globale sur 10.
        deterministic_score: Note issue de la seule verification factuelle.
        llm_score: Note proposee par le LLM, si sollicite.
        agreement: Le Judge valide-t-il la decision ?
        checks: Detail de tous les controles.
        flagged_issues: Codes d'anomalie releves.
        feedback: Synthese redigee a destination de l'ingenieur.
        corrected_severity: Severite que le Judge aurait retenue, si differente.
        verified_facts: Faits recalcules independamment par le Judge.
        judged_by: 'deterministic' ou 'hybrid'.
    """

    timestamp: str
    global_score: float = Field(ge=0.0, le=10.0)
    deterministic_score: float = Field(ge=0.0, le=10.0)
    llm_score: float | None = None
    agreement: bool
    checks: list[Check] = Field(default_factory=list)
    flagged_issues: list[str] = Field(default_factory=list)
    feedback: str = ""
    corrected_severity: str | None = None
    verified_facts: dict[str, Any] = Field(default_factory=dict)
    judged_by: Literal["deterministic", "hybrid"] = "deterministic"
    validation_scope: Literal["internal_logical_consistency"] = (
        "internal_logical_consistency"
    )
    uncertainty_level: Literal["low", "medium", "high"] = "high"
    limitations: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    rule_version: str = ""
    model_runtime_signature: str = ""
