"""
Judge Agent — évalue la qualité des décisions du Detection Agent.
Appel séparé à Gemini avec un prompt différent pour avoir un avis indépendant.
Score < 6/10 = désaccord, une alerte est générée dans l’audit trail.

Author: Mounir Sanbouli
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import text


BASE_DIR = Path(__file__).parents[2]

from src.config import GEMINI_MODEL, GEMINI_API_KEY  # noqa: F401 — ensures load_dotenv() called
from src.db import get_engine  # noqa: E402

MODEL_ID: str = GEMINI_MODEL
DISAGREEMENT_THRESHOLD = 6.0  # Score < 6/10 → disagreement


# ── I/O Schemas ───────────────────────────────────────────────────────────────

class JudgeInput(BaseModel):
    """Input payload for the Judge Agent.

    Attributes:
        machine_context: Machine metadata and recent sensor stats.
        detected_anomaly: Raw anomaly detection data.
        agent_decision: The Detection Agent's structured decision.
    """

    machine_context: dict[str, Any]
    detected_anomaly: dict[str, Any]
    agent_decision: dict[str, Any]


class CriteriaScores(BaseModel):
    """Weighted evaluation criteria scores.

    Attributes:
        relevance: Diagnostic relevance (weight 25%).
        history_coherence: Consistency with machine history (20%).
        calibrated_confidence: Calibration quality (20%).
        ocp_compliance: Compliance with OCP procedures (20%).
        action_feasibility: Feasibility of recommended action (15%).
    """

    relevance: float = Field(ge=0.0, le=10.0)
    history_coherence: float = Field(ge=0.0, le=10.0)
    calibrated_confidence: float = Field(ge=0.0, le=10.0)
    ocp_compliance: float = Field(ge=0.0, le=10.0)
    action_feasibility: float = Field(ge=0.0, le=10.0)


class JudgeEvaluation(BaseModel):
    """Structured output from the Judge Agent.

    Attributes:
        global_score: Weighted average score [0.0, 10.0].
        criteria_scores: Per-criterion breakdown.
        agreement: True if global_score >= 6.0.
        feedback: Narrative feedback on the decision quality.
        flagged_issues: List of identified issues (if any).
    """

    global_score: float = Field(ge=0.0, le=10.0)
    criteria_scores: CriteriaScores
    agreement: bool
    feedback: str
    flagged_issues: list[str] = Field(default_factory=list)


# ── Judge Prompt ──────────────────────────────────────────────────────────────

JUDGE_SYSTEM = """Tu es le Judge Agent du système OCP Bionic — auditeur indépendant et expert en fiabilité industrielle pour les équipements de traitement du phosphate (OCP Group, Khouribga).

Ton rôle est d'évaluer objectivement et rigoureusement les décisions de l'Agent de Détection, comme le ferait un ingénieur de fiabilité senior qui relit le rapport d'un junior.

## CONTEXTE TECHNIQUE DE RÉFÉRENCE

Tu connais les plages normales et les seuils critiques de chaque équipement surveillé :

| Machine | Temp (°C) | Vibration (mm/s) | Pression (bar) | Courant (A) | RPM |
|---------|-----------|-----------------|----------------|-------------|-----|
| BROYEUR_01 | 50–70 (crit>80) | 2–5 (crit>7) | 3–6 | 30–45 (crit>50) | 800–1200 |
| POMPE_02 | 25–45 (crit>55) | 1–3 (crit>5) | 4–8 (crit<2) | 15–25 (crit>30) | 1400–1800 |
| CONVOYEUR_03 | 20–40 (crit>50) | 0.5–2 (crit>4) | 1–2 | 10–20 (crit>25) | 200–400 |
| REACTEUR_04 | 60–80 (crit>85) | 1–2.5 (crit>4) | 2–4 (crit<1) | 20–35 (crit>40) | 60–120 |
| COMPRESSEUR_05 | 30–60 (crit>70) | 1–4 (crit>6) | 6–10 (crit<4) | 25–40 (crit>50) | 1000–1500 |

## GRILLE D'ÉVALUATION DÉTAILLÉE (5 critères pondérés)

### 1. PERTINENCE DU DIAGNOSTIC — poids 25%

Évalue si le diagnostic identifie correctement la cause probable à partir des données capteurs.

| Note | Critère |
|------|---------|
| 9–10 | Cause racine précise citant les valeurs mesurées ET les plages normales ET le mécanisme de défaillance (ex: "température 85°C vs normale 65°C → surchauffe roulement probable") |
| 7–8 | Cause identifiée correctement, quelques valeurs citées, mécanisme partiellement expliqué |
| 5–6 | Diagnostic vague mais cohérent ("anomalie détectée" sans précision) |
| 3–4 | Cause possible mais incohérente avec les données (ex: cavitation diagnostiquée alors que pression est normale) |
| 1–2 | Diagnostic manifestement faux ou contradictoire avec les valeurs capteurs |

### 2. COHÉRENCE AVEC L'HISTORIQUE — poids 20%

Vérifie si la décision tient compte du comportement historique de la machine.

| Note | Critère |
|------|---------|
| 9–10 | Compare explicitement mesures actuelles vs moyennes historiques (ex: "+2.8σ par rapport aux 7 derniers jours"), distingue événement soudain vs dérive progressive |
| 7–8 | Historique mentionné, comparaison implicite ou partielle |
| 5–6 | Décision sans référence à l'historique mais plausible au vu des données brutes |
| 3–4 | Décision ignore un historique clairement anormal signalé dans le contexte |
| 1–2 | Décision contredit l'historique (ex: NORMAL malgré une déviation historique significative) |

### 3. CONFIANCE CALIBRÉE — poids 20%

Vérifie si le niveau de confiance reflète réellement l'incertitude des preuves disponibles.

| Note | Critère |
|------|---------|
| 9–10 | Confiance justifiée : haute (>0.8) si données complètes + SHAP disponibles + historique cohérent ; basse (<0.6) si données insuffisantes ou contradictoires |
| 7–8 | Confiance globalement correcte avec légère surévaluation ou sous-évaluation |
| 5–6 | Confiance non justifiée mais dans une plage acceptable (0.4–0.7) |
| 3–4 | Confiance 0.9+ alors que les données sont ambiguës ou incomplètes (OVERCONFIDENCE) |
| 1–2 | Confiance 0.9+ avec diagnostic vague OU confiance 0.1 alors que les données sont claires |

### 4. CONFORMITÉ AUX PROCÉDURES OCP — poids 20%

Évalue si l'action recommandée est conforme aux standards industriels OCP (ISO 55000, maintenance préventive vs corrective).

| Note | Critère |
|------|---------|
| 9–10 | Action prioritisée correctement (CRITICAL → arrêt immédiat ; WARNING → inspection sous X heures ; NORMAL → surveillance). Délai précis fourni. Escalade mentionnée si nécessaire. |
| 7–8 | Action correcte mais délai imprécis ou escalade non mentionnée |
| 5–6 | Action générique mais non dangereuse (ex: "surveiller" pour un WARNING) |
| 3–4 | Action sous-dimensionnée pour la sévérité (ex: "surveillance 24h" pour un CRITICAL) |
| 1–2 | Action dangereuse ou inverse (ex: "continuer l'exploitation" pour CRITICAL, ou "arrêt immédiat" pour NORMAL) |

### 5. FAISABILITÉ DE L'ACTION — poids 15%

Évalue si l'action est concrète, réalisable et actionnée par un technicien OCP.

| Note | Critère |
|------|---------|
| 9–10 | Action spécifique, avec délai précis, indique le personnel nécessaire ou l'équipement à inspecter |
| 7–8 | Action claire mais manque de précision opérationnelle (ex: pas de délai) |
| 5–6 | Action possible mais trop vague pour être exécutée directement |
| 3–4 | Action irréalisable dans le contexte OCP (ex: "remplacer le moteur immédiatement" sans arrêt de production planifié) |
| 1–2 | Aucune action concrète ou action absurde |

## FORMULE DE CALCUL

Score global = 0.25 × R + 0.20 × H + 0.20 × C + 0.20 × O + 0.15 × F

**RÈGLE CRITIQUE : Score < 6.0 → DÉSACCORD → alerte automatique générée**

## CATÉGORIES D'ANOMALIES À SIGNALER (flagged_issues)

Utilise ces codes standardisés si applicable :
- `OVERCONFIDENCE` : confiance > 0.8 sans justification suffisante
- `SEVERITY_MISMATCH` : sévérité incohérente avec le score d'anomalie (ex: NORMAL avec score > 0.6)
- `MISSING_HISTORICAL_CONTEXT` : historique ignoré alors que disponible
- `UNSAFE_ACTION` : action recommandée pourrait aggraver la situation
- `VAGUE_DIAGNOSIS` : diagnostic sans identification de cause racine
- `DELAY_TOO_LONG` : délai d'intervention insuffisant pour la sévérité déclarée
- `CONTRADICTORY_DATA` : données capteurs contradictoires non résolues dans le raisonnement

## FORMAT DE SORTIE

Réponds UNIQUEMENT en JSON valide, sans texte avant ou après. Calcule le score global toi-même :
{
  "global_score": <float 0-10, calculé avec la formule>,
  "criteria_scores": {
    "relevance": <float 0-10>,
    "history_coherence": <float 0-10>,
    "calibrated_confidence": <float 0-10>,
    "ocp_compliance": <float 0-10>,
    "action_feasibility": <float 0-10>
  },
  "agreement": <true si global_score >= 6.0, false sinon>,
  "feedback": "<2-3 phrases d'analyse factuelle : ce qui est bien fait, ce qui manque, recommandation concrète d'amélioration>",
  "flagged_issues": ["<CODE_1>", ...] ou [] si aucun problème
}
"""


# ── Judge Agent ───────────────────────────────────────────────────────────────

class JudgeAgent:
    """Autonomous Judge Agent using Google Gemini via LangChain.

    Args:
        model_id: Gemini model identifier.
    """

    def __init__(
        self,
        model_id: str = MODEL_ID,
    ) -> None:
        self.model_id = model_id
        self.llm = ChatGoogleGenerativeAI(
            model=model_id,
            google_api_key=GEMINI_API_KEY,
            temperature=0.1,
        )
        logger.info(f"Judge Agent initialized with model={model_id}")

    def evaluate(self, payload: JudgeInput) -> JudgeEvaluation:
        """Evaluate a Detection Agent decision.

        Args:
            payload: JudgeInput with machine context, anomaly data, and agent decision.

        Returns:
            JudgeEvaluation with scores, agreement flag, and feedback.
        """
        user_message = f"""
## Contexte Machine
{json.dumps(payload.machine_context, indent=2, ensure_ascii=False)}

## Anomalie Détectée
{json.dumps(payload.detected_anomaly, indent=2, ensure_ascii=False)}

## Décision de l'Agent de Détection
{json.dumps(payload.agent_decision, indent=2, ensure_ascii=False)}

Évalue cette décision selon les 5 critères pondérés. Sois rigoureux et objectif.
"""

        logger.debug(f"Calling Judge Agent for machine {payload.agent_decision.get('machine_id', '?')}...")

        messages = [
            SystemMessage(content=JUDGE_SYSTEM),
            HumanMessage(content=user_message),
        ]
        response = self.llm.invoke(messages)
        raw = response.content.strip()

        # Extract JSON
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            data = json.loads(raw[start:end])
            evaluation = JudgeEvaluation(**data)
        except Exception as e:
            logger.error(f"Judge JSON parse failed: {e}\nRaw: {raw[:300]}")
            evaluation = JudgeEvaluation(
                global_score=5.0,
                criteria_scores=CriteriaScores(
                    relevance=5.0,
                    history_coherence=5.0,
                    calibrated_confidence=5.0,
                    ocp_compliance=5.0,
                    action_feasibility=5.0,
                ),
                agreement=False,
                feedback=f"Erreur de parsing: {str(e)[:200]}",
                flagged_issues=["PARSE_ERROR"],
            )

        # Recompute agreement from actual global score (avoid hallucination)
        evaluation.agreement = evaluation.global_score >= DISAGREEMENT_THRESHOLD

        if not evaluation.agreement:
            logger.warning(
                f"JUDGE DISAGREEMENT: score={evaluation.global_score:.1f} | "
                f"machine={payload.agent_decision.get('machine_id')} | "
                f"issues={evaluation.flagged_issues}"
            )

        return evaluation


def _save_evaluation(ev: JudgeEvaluation, machine_id: str) -> None:
    """Persist a JudgeEvaluation to the judge_evaluations table.

    Args:
        ev: Completed evaluation.
        machine_id: Machine identifier for the evaluation record.
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO judge_evaluations
                (timestamp, machine_id, global_score, relevance_score, history_score,
                 confidence_score, compliance_score, feasibility_score, agreement,
                 feedback, flagged_issues)
            VALUES
                (:ts, :mid, :gs, :rel, :hist, :conf, :comp, :feas, :agr, :fb, :fi)
        """), {
            "ts":   datetime.now().isoformat(),
            "mid":  machine_id,
            "gs":   ev.global_score,
            "rel":  ev.criteria_scores.relevance,
            "hist": ev.criteria_scores.history_coherence,
            "conf": ev.criteria_scores.calibrated_confidence,
            "comp": ev.criteria_scores.ocp_compliance,
            "feas": ev.criteria_scores.action_feasibility,
            "agr":  int(ev.agreement),
            "fb":   ev.feedback,
            "fi":   json.dumps(ev.flagged_issues),
        })
    logger.debug(f"Evaluation saved for machine={machine_id} score={ev.global_score:.1f}")


_JUDGE: JudgeAgent | None = None


def judge_decision(
    machine_context: dict,
    detected_anomaly: dict,
    agent_decision: dict,
) -> JudgeEvaluation:
    """Module-level helper to build/reuse a JudgeAgent and evaluate a decision.

    This is the main entry point called by api/main.py.

    Args:
        machine_context: Machine metadata and recent sensor stats.
        detected_anomaly: Raw anomaly detection data.
        agent_decision: The Detection Agent's structured decision (model_dump()).

    Returns:
        JudgeEvaluation with scores, agreement flag, and feedback.
    """
    global _JUDGE
    if _JUDGE is None:
        _JUDGE = JudgeAgent()

    payload = JudgeInput(
        machine_context=machine_context,
        detected_anomaly=detected_anomaly,
        agent_decision=agent_decision,
    )
    ev = _JUDGE.evaluate(payload)

    machine_id = agent_decision.get("machine_id", "UNKNOWN")
    try:
        _save_evaluation(ev, machine_id)
    except Exception as e:
        logger.warning(f"Could not save evaluation for {machine_id}: {e}")

    return ev


if __name__ == "__main__":
    sample = JudgeInput(
        machine_context={"machine_id": "BROYEUR_01", "location": "Khouribga"},
        detected_anomaly={"anomaly_score": 0.72, "severity": "CRITICAL"},
        agent_decision={
            "machine_id":        "BROYEUR_01",
            "timestamp":         datetime.now().isoformat(),
            "anomaly_score":     0.72,
            "severity":          "CRITICAL",
            "diagnosis":         "Surchauffe roulement: temperature 85C vs normale 65C.",
            "recommended_action":"Arret preventif sous 2h, inspection roulement.",
            "confidence":        0.82,
            "reasoning":         "Temperature hors plage (+2.8 sigma), vibration elevated.",
            "shap_top_features": [],
        },
    )
    agent = JudgeAgent()
    result = agent.evaluate(sample)
    print(result.model_dump_json(indent=2))
