"""
Pipeline de bout en bout : donnees DCS -> detection -> diagnostic -> jugement.

Point d'entree unique du systeme. Toutes les autres couches (API, replay
temps reel, notebooks, tests) s'appuient dessus.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from src.agents.detection_agent import DetectionAgent
from src.agents.judge_agent import JudgeAgent
from src.agents.schemas import AgentDecision, JudgeVerdict
from src.config import (
    CONTAMINATION,
    DCS_EXPORT,
    MODEL_DIR,
    MODEL_STRATEGY,
    RANDOM_SEED,
    REFERENCE_END,
)
from src.domain.knowledge import DomainKnowledge, load_domain, seuil
from src.features.e7301_features import build_features
from src.ingest.dcs_loader import IngestionResult, ingest
from src.models.detector import (
    CoolerAnomalyDetector,
    DetectionResult,
    StatisticalDetector,
)

DEFAULT_DATA = DCS_EXPORT
DEFAULT_MODEL = MODEL_DIR / "e7301_detector.joblib"


@dataclass
class Analysis:
    """Resultat complet de l'analyse d'un instant.

    Attributes:
        detection: Sortie du detecteur.
        decision: Diagnostic de l'agent.
        verdict: Jugement du Judge.
    """

    detection: DetectionResult
    decision: AgentDecision
    verdict: JudgeVerdict

    def to_dict(self) -> dict[str, Any]:
        """Representation serialisable pour l'API."""
        return {
            "detection": self.detection.to_dict(),
            "decision": self.decision.model_dump(),
            "verdict": self.verdict.model_dump(),
        }

    def summary_line(self) -> str:
        """Ligne de synthese lisible en console."""
        return (
            f"{self.detection.timestamp} | {self.decision.severity:8s} | "
            f"score={self.detection.anomaly_score:.3f} | "
            f"conf={self.decision.confidence:.2f} | "
            f"judge={self.verdict.global_score:5.2f}/10 "
            f"{'OK ' if self.verdict.agreement else 'NOK'} | "
            f"{', '.join(self.verdict.flagged_issues) or '-'}"
        )


class E7301Pipeline:
    """Chaine complete de surveillance du refroidisseur E7301.

    Attributes:
        domain: Connaissance domaine.
        ingestion: Resultat de l'ingestion.
        features: Table des features.
        references: References ajustees.
        detector: Detecteur consolide.
        agent: Agent de diagnostic.
        judge: Judge.
    """

    def __init__(
        self,
        data_path: str | Path = DEFAULT_DATA,
        domain: DomainKnowledge | None = None,
        reference_end: str | None = None,
        model_strategy: str | None = None,
        use_llm: bool = True,
    ) -> None:
        """Construit et entraine la chaine complete.

        Args:
            data_path: Export DCS a charger.
            domain: Connaissance domaine (chargee par defaut).
            reference_end: Fin de la periode de reference pour l'apprentissage.
            model_strategy: Strategie de chargement du modele.
            use_llm: Autoriser l'usage du LLM pour les agents.
        """
        self.domain = domain or load_domain()
        self.data_path = Path(data_path)
        self.model_strategy = model_strategy or MODEL_STRATEGY
        logger.info("=== Construction de la chaine E7301 ===")

        self.ingestion: IngestionResult = ingest(data_path, self.domain)

        # Construction des features
        self.features, self.references = build_features(
            self.ingestion.readings,
            self.ingestion.quality,
            self.domain,
            reference_end=reference_end or REFERENCE_END,
        )

        # Construction et entrainement du detecteur
        stat = StatisticalDetector(contamination=CONTAMINATION, random_state=RANDOM_SEED)
        self.detector = CoolerAnomalyDetector(
            self.domain, stat=stat, references=self.references
        ).fit(self.features, reference_end=reference_end or REFERENCE_END)

        # Agents
        self.agent = DetectionAgent(self.domain, use_llm=use_llm)
        self.judge = JudgeAgent(self.detector, self.domain, use_llm=use_llm)

        logger.info(
            f"Chaine prete — agent en mode '{self.agent.mode}', "
            f"Judge en mode '{self.judge.mode}'"
        )

    # ── Analyse ──────────────────────────────────────────────────────────────

    def analyze_at(
        self,
        timestamp: pd.Timestamp | str,
        *,
        use_llm: bool = True,
    ) -> Analysis:
        """Analyse un horodatage de bout en bout.

        Args:
            timestamp: Instant a analyser.
            use_llm: Ignoré (conservé pour compatibilité API).

        Returns:
            Analysis complete (detection, diagnostic, jugement).
        """
        detection = self.detector.analyze(self.features, timestamp)
        decision = self.agent.analyze(detection, use_llm=use_llm)
        verdict = self.judge.judge(decision, self.features, use_llm=use_llm)
        return Analysis(detection, decision, verdict)

    def analyze_many(self, timestamps: list[pd.Timestamp | str]) -> list[Analysis]:
        """Analyse une liste d'horodatages."""
        out: list[Analysis] = []
        for ts in timestamps:
            try:
                out.append(self.analyze_at(ts))
            except KeyError:
                logger.warning(f"Horodatage ignore (absent des donnees): {ts}")
        return out

    def stream(self, start: str | None = None, step: int = 1) -> Iterator[Analysis]:
        """Parcourt la periode instant par instant, comme un flux temps reel."""
        idx = self.features.index
        if start:
            idx = idx[idx >= pd.Timestamp(start)]
        for ts in idx[::step]:
            yield self.analyze_at(ts, use_llm=False)

    # ── Selection d'instants d'interet ───────────────────────────────────────

    def episodes(self) -> pd.DataFrame:
        """Episodes d'anomalie agreges."""
        return self.detector.episodes(self.features)

    def notable_timestamps(self, limit: int = 25) -> list[pd.Timestamp]:
        """Instants les plus interessants a analyser en priorite."""
        if limit <= 0:
            return []

        ts: set[pd.Timestamp] = set()
        episode_quota = max(1, (limit + 1) // 2)
        rule_quota = max(0, limit - episode_quota)

        ep = self.episodes()
        for t in ep["peak_at"].head(episode_quota):
            ts.add(pd.Timestamp(t))

        from src.models.detector import CONC_DROP_SUSPICIOUS

        f = self.features
        d = self.domain
        running = f["process_state"].eq("RUNNING")
        k_sigma = float(d.get("C_ACID_1200").spec.get("cross_check_k_sigma", 4.0))
        rule_hits = running & (
            (f["T_ACID_OUT"] >= seuil(d.get("T_ACID_OUT").threshold("alarm_high"), 68.0))
            | (f["conc_min"] <= seuil(d.get("C_ACID_1100").threshold("alarm_low"), 98.0))
            | (f["T_ACID_IN"] >= seuil(d.get("T_ACID_IN").threshold("alarm_high"), 100.0))
            | (f["F_ACID"] <= seuil(d.get("F_ACID").threshold("alarm_low"), 35.0))
            | (f["conc_drop_24h"] <= -CONC_DROP_SUSPICIOUS)
            | (f["conc_bias_drift_z"].abs() > k_sigma)
        )
        for t in f.index[rule_hits][:rule_quota]:
            ts.add(pd.Timestamp(t))

        return sorted(ts)[:limit]

    # ── Persistance ──────────────────────────────────────────────────────────

    def save_model(self, path: str | Path = DEFAULT_MODEL) -> Path:
        """Serialise le detecteur entraine."""
        return self.detector.save(path)

    def health_report(self) -> dict[str, Any]:
        """Synthese de l'etat du systeme."""
        return {
            "equipment": self.domain.equipment,
            "ingestion": self.ingestion.report,
            "sensor_health": self.ingestion.sensor_health.to_dict(orient="records"),
            "references": self.references.to_dict(),
            "detector": self.detector.stat.train_meta_,
            "agent_mode": self.agent.mode,
            "judge_mode": self.judge.mode,
            "blind_spots": [
                {"code": m.code, "element": m.element, "mode": m.mode,
                 "criticite": m.C, "couverture_preventive": m.plan_maintenance_ref}
                for m in self.domain.blind_spots()
            ],
        }


if __name__ == "__main__":
    pipe = E7301Pipeline()
    print("\n=== EPISODES ===")
    print(pipe.episodes().head(10).to_string(index=False))

    print("\n=== ANALYSES ===")
    analyses = pipe.analyze_many(pipe.notable_timestamps(20))
    for a in analyses:
        print(a.summary_line())
