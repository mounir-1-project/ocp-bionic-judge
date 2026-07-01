"""
Agent de detection base sur LangChain + Google Gemini.
Utilise le pattern ReAct pour raisonner etape par etape
avant de formuler un diagnostic.

Author: Mounir Sanbouli
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any

import pandas as pd
from langchain.agents import AgentExecutor, create_react_agent
from langchain.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import tool
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import text

from src.config import GEMINI_MODEL, GEMINI_API_KEY  # noqa: F401
from src.db import get_engine


MODEL_ID: str = GEMINI_MODEL


class AgentDecision(BaseModel):
    """Structured output from the Detection Agent."""

    machine_id:         str
    timestamp:          str
    anomaly_score:      float = Field(ge=0.0, le=1.0)
    severity:           str   = Field(pattern="^(NORMAL|WARNING|CRITICAL)$")
    diagnosis:          str
    recommended_action: str
    confidence:         float = Field(ge=0.0, le=1.0)
    reasoning:          str
    shap_top_features:  list[dict] = Field(default_factory=list)


@tool
def get_anomaly_data(machine_id: str, n: int = 10) -> str:
    """Retrieve the most recent anomaly detections for a machine.

    Args:
        machine_id: Machine identifier (e.g. BROYEUR_01).
        n: Number of records to retrieve.

    Returns:
        JSON string of recent anomaly records.
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            df = pd.read_sql(
                text("""
                    SELECT machine_id, timestamp, anomaly_score, severity, model_version, inference_ms
                    FROM ml_decisions
                    WHERE machine_id = :mid AND is_anomaly = 1
                    ORDER BY timestamp DESC
                    LIMIT :n
                """),
                conn, params={"mid": machine_id, "n": n},
            )
        return df.to_json(orient="records", date_format="iso")
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_machine_history(machine_id: str, days: int = 7) -> str:
    """Retrieve historical sensor statistics for a machine.

    Args:
        machine_id: Machine identifier.
        days: Number of past days.

    Returns:
        JSON string with mean/std/min/max per sensor.
    """
    try:
        engine = get_engine()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with engine.connect() as conn:
            df = pd.read_sql(
                text("SELECT * FROM sensor_readings WHERE machine_id = :mid AND timestamp >= :cut"),
                conn, params={"mid": machine_id, "cut": cutoff},
            )
        sensors = ["temperature", "vibration", "pression", "courant", "rpm"]
        summary = {
            s: {"mean": round(df[s].mean(), 3), "std": round(df[s].std(), 3),
                "min":  round(df[s].min(), 3),  "max": round(df[s].max(), 3)}
            for s in sensors if s in df.columns
        }
        return json.dumps({"machine_id": machine_id, "days": days,
                           "n_readings": len(df), "stats": summary})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_shap_explanation(anomaly_id: str) -> str:
    """Retrieve SHAP explanation for a specific ML decision.

    Args:
        anomaly_id: Integer ID from ml_decisions table.

    Returns:
        JSON with top SHAP features.
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            df = pd.read_sql(
                text("SELECT features_json FROM ml_decisions WHERE id = :id"),
                conn, params={"id": int(anomaly_id)},
            )
        if df.empty:
            return json.dumps({"error": f"No decision id={anomaly_id}"})
        features = json.loads(df.iloc[0]["features_json"] or "{}")
        return json.dumps({"anomaly_id": anomaly_id, "shap_features": features})
    except Exception as e:
        return json.dumps({"error": str(e)})


SYSTEM_PROMPT = (
    "Tu es un expert en fiabilite industrielle et maintenance predictive, "
    "specialise dans les equipements de traitement du phosphate chez OCP Group "
    "(Khouribga, Maroc) - premier producteur mondial de phosphate brut.\n\n"

    "## TON EXPERTISE METIER\n\n"
    "Tu maitrises parfaitement les 5 equipements surveilles :\n\n"

    "**BROYEUR_01 - Broyeur a Boulets**\n"
    "- Plages normales : temperature 50-70C | vibration 2-5 mm/s | pression 3-6 bar | courant 30-45 A | rpm 800-1200\n"
    "- Defaillances : usure billes (vibration progressive), surcharge (courant+temp), bouchage (pression haute + rpm bas), roulement (vibration HF)\n\n"

    "**POMPE_02 - Pompe Centrifuge**\n"
    "- Plages normales : temperature 25-45C | vibration 1-3 mm/s | pression 4-8 bar | courant 15-25 A | rpm 1400-1800\n"
    "- Defaillances : cavitation (vibration + bruit), joint mecanique (temp + fuite), desequilibre rotor (vibration periodique)\n\n"

    "**CONVOYEUR_03 - Convoyeur a Courroie**\n"
    "- Plages normales : temperature 20-40C | vibration 0.5-2 mm/s | pression 1-2 bar | courant 10-20 A | rpm 200-400\n"
    "- Defaillances : glissement (rpm bas + courant haut), desalignement (vibration laterale), surcharge (courant > 25A)\n\n"

    "**REACTEUR_04 - Reacteur d'Attaque**\n"
    "- Plages normales : temperature 60-80C | vibration 1-2.5 mm/s | pression 2-4 bar | courant 20-35 A | rpm 60-120\n"
    "- Defaillances : surchauffe (temp > 85C = CRITIQUE), fuite acide (pression basse + temp haute), encrassement\n\n"

    "**COMPRESSEUR_05 - Compresseur Industriel**\n"
    "- Plages normales : temperature 30-60C | vibration 1-4 mm/s | pression 6-10 bar | courant 25-40 A | rpm 1000-1500\n"
    "- Defaillances : surchauffe (temp > 70C), fuite (pression basse progressive), usure pistons\n\n"

    "## SEUILS D'ALERTE\n"
    "- NORMAL   : score < 0.3, tous capteurs dans les plages normales\n"
    "- WARNING  : 1-2 capteurs hors plage OU score 0.3-0.6 OU deviation 2-3 sigma\n"
    "- CRITICAL : temperature > seuil critique OU score > 0.6 OU deviation > 3 sigma\n\n"

    "## TES OUTILS DISPONIBLES\n\n"
    "{tools}\n\n"

    "## PROTOCOLE D'ANALYSE (obligatoire)\n\n"
    "Etape 1 - Donnees recentes :\n"
    "Thought: Je recupere les anomalies recentes.\n"
    "Action: get_anomaly_data\n"
    "Action Input: {{\"machine_id\": \"<id>\", \"n\": 5}}\n"
    "Observation: [resultats]\n\n"

    "Etape 2 - Historique :\n"
    "Thought: Je compare avec l'historique 7 jours.\n"
    "Action: get_machine_history\n"
    "Action Input: {{\"machine_id\": \"<id>\", \"days\": 7}}\n"
    "Observation: [resultats]\n\n"

    "Etape 3 - SHAP (si anomaly_id disponible) :\n"
    "Thought: Je recupere les features SHAP.\n"
    "Action: get_shap_explanation\n"
    "Action Input: {{\"anomaly_id\": \"<id>\"}}\n"
    "Observation: [resultats]\n\n"

    "Etape 4 - Synthese :\n"
    "Thought: J'ai suffisamment d'informations. Je formule mon diagnostic.\n"
    "Final Answer: [JSON AgentDecision]\n\n"

    "## FORMAT DE SORTIE\n\n"
    "Reponds UNIQUEMENT avec ce JSON valide (aucun texte avant ou apres) :\n"
    "{{\n"
    "  \"machine_id\": \"<string>\",\n"
    "  \"timestamp\": \"<ISO 8601>\",\n"
    "  \"anomaly_score\": <float 0.0-1.0>,\n"
    "  \"severity\": \"<NORMAL|WARNING|CRITICAL>\",\n"
    "  \"diagnosis\": \"<diagnostic technique precis, 1-2 phrases>\",\n"
    "  \"recommended_action\": \"<action concrete avec delai precis>\",\n"
    "  \"confidence\": <float 0.0-1.0>,\n"
    "  \"reasoning\": \"<capteurs observes -> historique -> cause probable>\",\n"
    "  \"shap_top_features\": [<features SHAP ou []>]\n"
    "}}\n\n"

    "## STANDARDS DE QUALITE\n"
    "- Diagnostic : cite les valeurs mesurees ET normales (ex: temp 85C vs normale 65C, +3 sigma)\n"
    "- Action : delai precis (ex: Inspection sous 4h, Arret preventif dans 2h)\n"
    "- Confiance : reflete l'incertitude reelle (< 0.6 si donnees insuffisantes)\n"
    "- Ton : professionnel, factuel, actionnable pour un technicien OCP\n\n"

    "{agent_scratchpad}"
)

REACT_PROMPT = PromptTemplate.from_template(
    "Question: {input}\n\nTool names: {tool_names}\n\n" + SYSTEM_PROMPT
)


# Module-level singleton — built once, reused for all analyze_machine() calls.
_AGENT_EXECUTOR: Optional[AgentExecutor] = None
_AGENT_LOCK = threading.Lock()


def build_detection_agent() -> AgentExecutor:
    """Build and return the LangChain ReAct Detection Agent.

    Returns:
        Configured AgentExecutor.
    """
    llm = ChatGoogleGenerativeAI(
        model=MODEL_ID,
        google_api_key=GEMINI_API_KEY,
        temperature=0.1,
        max_output_tokens=2048,
    )
    tools = [get_anomaly_data, get_machine_history, get_shap_explanation]
    agent = create_react_agent(llm, tools, REACT_PROMPT)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        max_iterations=6,
        max_execution_time=60,
        handle_parsing_errors=True,
    )


def _get_agent() -> AgentExecutor:
    """Return the singleton AgentExecutor, building it on first call (thread-safe).

    Returns:
        The cached AgentExecutor instance.
    """
    global _AGENT_EXECUTOR
    if _AGENT_EXECUTOR is None:
        with _AGENT_LOCK:
            if _AGENT_EXECUTOR is None:
                logger.info("Building Detection Agent (first call)...")
                _AGENT_EXECUTOR = build_detection_agent()
    return _AGENT_EXECUTOR


def analyze_machine(machine_id: str, executor: Optional[AgentExecutor] = None) -> AgentDecision:
    """Run the detection agent for a given machine.

    Args:
        machine_id: Machine identifier to analyze.
        executor: Optional executor override (uses cached singleton by default).

    Returns:
        Validated AgentDecision.
    """
    agent = executor or _get_agent()
    result = agent.invoke({"input": f"Analyse l'etat actuel de la machine {machine_id}."})
    raw_output = result.get("output", "{}")

    try:
        match = re.search(r'\{.*\}', raw_output, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            raise ValueError("No JSON object found in agent output")
        return AgentDecision(**data)
    except Exception as e:
        logger.warning(f"JSON parse failed: {e} — returning safe fallback")
        return AgentDecision(
            machine_id=machine_id,
            timestamp=datetime.now().isoformat(),
            anomaly_score=0.5,
            severity="WARNING",
            diagnosis=raw_output[:500],
            recommended_action="Inspection manuelle recommandee",
            confidence=0.5,
            reasoning=f"Parse error: {e}",
            shap_top_features=[],
        )


if __name__ == "__main__":
    decision = analyze_machine("BROYEUR_01")
    print(decision.model_dump_json(indent=2))
