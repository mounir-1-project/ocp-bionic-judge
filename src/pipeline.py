"""
Pipeline de bout en bout : donnees DCS -> detection -> diagnostic -> jugement.

Point d'entree unique du systeme. Toutes les autres couches (API, replay
temps reel, notebooks, tests) s'appuient dessus pour garantir qu'elles
executent exactement la meme chaine de traitement.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import json
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
    MODEL_ALLOWED_STATUSES,
    MODEL_DIR,
    MODEL_STRATEGY,
    RANDOM_SEED,
    REFERENCE_END,
)
from src.domain.knowledge import DomainKnowledge, load_domain, seuil
from src.features.e7301_features import MODEL_FEATURES, build_features
from src.governance.lineage import (
    ManifestValidationError,
    build_manifest,
    validate_model_manifest,
    write_manifest,
)
from src.governance.model_validation import ValidationReport, validate_unsupervised_detector
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
        """Representation serialisable pour l'API et la persistance."""
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
        use_llm: bool = True,
        reference_end: str | None = None,
        model_strategy: str | None = None,
        model_path: str | Path = DEFAULT_MODEL,
    ) -> None:
        """Construit et entraine la chaine complete.

        Args:
            data_path: Export DCS a charger.
            domain: Connaissance domaine (chargee par defaut).
            use_llm: Autoriser l'usage du LLM pour les deux agents.
            reference_end: Fin de la periode de reference pour l'apprentissage.
        """
        self.domain = domain or load_domain()
        self.data_path = Path(data_path)
        self.model_path = Path(model_path)
        self.model_strategy = model_strategy or MODEL_STRATEGY
        self.model_source = "runtime_trained_unpromoted"
        self.model_rejection_reason: str | None = None
        self.model_promotion_status: str | None = None
        logger.info("=== Construction de la chaine E7301 ===")

        self.ingestion: IngestionResult = ingest(data_path, self.domain)
        loaded = self._load_compatible_artifact()
        if loaded is not None:
            self.detector = loaded
            self.references = loaded.references
            self.features, _ = build_features(
                self.ingestion.readings,
                self.ingestion.quality,
                self.domain,
                references=self.references,
                fit_references=False,
            )
            self.model_source = f"promoted_artifact:{self.model_promotion_status}"
        else:
            self.features, self.references = build_features(
                self.ingestion.readings,
                self.ingestion.quality,
                self.domain,
                reference_end=reference_end or REFERENCE_END,
            )
            stat = StatisticalDetector(contamination=CONTAMINATION, random_state=RANDOM_SEED)
            self.detector = CoolerAnomalyDetector(self.domain, stat=stat, references=self.references).fit(
                self.features, reference_end=reference_end or REFERENCE_END
            )
        self._validation_report: ValidationReport | None = None
        self.agent = DetectionAgent(self.domain, use_llm=use_llm)
        self.judge = JudgeAgent(self.detector, self.domain, use_llm=use_llm)
        logger.info(
            f"Chaine prete — modele '{self.model_source}', agent en mode '{self.agent.mode}', "
            f"Judge en mode '{self.judge.mode}'"
        )

    def _load_compatible_artifact(self) -> CoolerAnomalyDetector | None:
        """Charge uniquement un artefact promu dont toutes les gates passent."""
        if self.model_strategy == "train":
            # Le refus est explicite : sans motif, l'endpoint de sante affiche
            # un artefact « non promu » sans dire pourquoi, et l'on ne peut pas
            # distinguer un artefact refuse d'un reglage volontaire.
            self.model_rejection_reason = (
                "MODEL_STRATEGY=train : reconstruction demandee, aucun artefact "
                "candidat n'a ete examine"
            )
            return None
        manifest_path = self.model_path.with_suffix(".manifest.json")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.model_promotion_status = validate_model_manifest(
                manifest,
                model_path=self.model_path,
                data_path=self.data_path,
                expected_features=MODEL_FEATURES,
                allowed_statuses=MODEL_ALLOWED_STATUSES,
            )
            detector = CoolerAnomalyDetector.load(self.model_path, self.domain)
            if detector.stat.features != list(MODEL_FEATURES):
                raise ValueError("schéma de features différent")
            if not hasattr(detector.stat, "score_center_"):
                raise ValueError("calibration du score obsolète")
            return detector
        except (
            FileNotFoundError,
            KeyError,
            ValueError,
            ManifestValidationError,
            json.JSONDecodeError,
        ) as exc:
            self.model_rejection_reason = str(exc)
            if self.model_strategy == "artifact":
                # UN REFUS DOIT DIRE QUOI FAIRE.
                # Le message precedent citait la cause sans indiquer aucune
                # action : un exploitant devant `MODEL_STRATEGY=artifact` en
                # echec n'avait aucun moyen de savoir si l'artefact etait
                # corrompu, non promu, ou produit dans un autre environnement.
                raise RuntimeError(
                    f"MODEL_STRATEGY=artifact : artefact refusé — {exc}\n"
                    f"  manifeste attendu : {manifest_path}\n"
                    f"  état de promotion : python scripts/promote_model.py --etat\n"
                    f"  produire un artefact alignable : make release-runtime\n"
                    f"  démarrer sans artefact promu  : MODEL_STRATEGY=auto"
                ) from exc
            logger.warning(f"Artefact refusé, reconstruction locale non promue: {exc}")
            return None

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
            use_llm: Autoriser les couches LLM optionnelles. La detection et
                     la verification deterministes sont toujours executees.

        Returns:
            Analysis complete (detection, diagnostic, jugement).
        """
        detection = self.detector.analyze(self.features, timestamp)
        decision = self.agent.analyze(detection, use_llm=use_llm)
        verdict = self.judge.judge(decision, self.features, use_llm=use_llm)
        return Analysis(detection, decision, verdict)

    def analyze_many(self, timestamps: list[pd.Timestamp | str]) -> list[Analysis]:
        """Analyse une liste d'horodatages.

        Args:
            timestamps: Instants a analyser.

        Returns:
            Liste d'Analysis.
        """
        out: list[Analysis] = []
        for ts in timestamps:
            try:
                out.append(self.analyze_at(ts))
            except KeyError:
                logger.warning(f"Horodatage ignore (absent des donnees): {ts}")
        return out

    def stream(self, start: str | None = None, step: int = 1) -> Iterator[Analysis]:
        """Parcourt la periode instant par instant, comme un flux temps reel.

        Args:
            start: Horodatage de depart (defaut : debut des donnees).
            step: Pas de parcours en nombre d'echantillons.

        Yields:
            Analysis pour chaque instant parcouru.
        """
        idx = self.features.index
        if start:
            idx = idx[idx >= pd.Timestamp(start)]
        for ts in idx[::step]:
            yield self.analyze_at(ts, use_llm=False)

    # ── Selection d'instants d'interet ───────────────────────────────────────

    def episodes(self) -> pd.DataFrame:
        """Episodes d'anomalie agreges.

        Returns:
            DataFrame des episodes, tries par score maximal.
        """
        return self.detector.episodes(self.features)

    def notable_timestamps(self, limit: int = 25) -> list[pd.Timestamp]:
        """Instants les plus interessants a analyser en priorite.

        Combine les pics d'episodes statistiques et les instants ou une regle
        deterministe de severite elevee s'est declenchee. C'est la selection
        utilisee pour les demonstrations et l'evaluation.

        Args:
            limit: Nombre maximal d'instants retournes.

        Returns:
            Liste d'horodatages tries chronologiquement.
        """
        if limit <= 0:
            return []

        ts: set[pd.Timestamp] = set()
        episode_quota = max(1, (limit + 1) // 2)
        rule_quota = max(0, limit - episode_quota)

        ep = self.episodes()
        for t in ep["peak_at"].head(episode_quota):
            ts.add(pd.Timestamp(t))

        # LES SEUILS VIENNENT DU REFERENTIEL, PAS DU CODE.
        # Une version precedente les recopiait en dur ici. Deux consequences :
        # une modification de `tags.yaml` ne se propageait pas a cette
        # selection, et le seuil abandonne `conc_spread > 0.6` — remplace dans
        # le moteur de regles par une surveillance de la STABILITE du biais —
        # y survivait, faisant reapparaitre une regle que le projet declare
        # inefficace ailleurs.
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
        """Serialise le detecteur entraine.

        Args:
            path: Destination du fichier .joblib.

        Returns:
            Le chemin ecrit.
        """
        target = self.detector.save(path)
        manifest = build_manifest(
            data_path=self.data_path,
            model_path=target,
            model_metadata={
                "detector": self.detector.stat.train_meta_,
                "references": self.references.to_dict(),
                "validation": self.validation_report(),
            },
        )
        write_manifest(manifest, target.with_suffix(".manifest.json"))
        return target

    def health_report(self) -> dict[str, Any]:
        """Synthese de l'etat du systeme et des donnees.

        Returns:
            Dictionnaire de gouvernance : ingestion, capteurs, modele, angles morts.
        """
        return {
            "equipment": self.domain.equipment,
            "ingestion": self.ingestion.report,
            "sensor_health": self.ingestion.sensor_health.to_dict(orient="records"),
            "references": self.references.to_dict(),
            "detector": self.detector.stat.train_meta_,
            "model_source": self.model_source,
            "model_promotion_status": self.model_promotion_status,
            "model_rejection_reason": self.model_rejection_reason,
            "agent_mode": self.agent.mode,
            "judge_mode": self.judge.mode,
            "blind_spots": [
                {"code": m.code, "element": m.element, "mode": m.mode,
                 "criticite": m.C, "couverture_preventive": m.plan_maintenance_ref}
                for m in self.domain.blind_spots()
            ],
        }

    def validation_report(self) -> dict[str, Any]:
        """Retourne le backtest temporel, calculé une seule fois par processus."""
        if self._validation_report is None:
            self._validation_report = validate_unsupervised_detector(
                self.features,
                readings=self.ingestion.readings,
                quality=self.ingestion.quality,
                domain=self.domain,
                references=self.references,
                contamination=CONTAMINATION,
                random_state=RANDOM_SEED,
            )
        return self._validation_report.to_dict()


if __name__ == "__main__":
    pipe = E7301Pipeline(use_llm=False)
    print("\n=== EPISODES ===")
    print(pipe.episodes().head(10).to_string(index=False))

    print("\n=== ANALYSES ===")
    analyses = pipe.analyze_many(pipe.notable_timestamps(20))
    for a in analyses:
        print(a.summary_line())

    print("\n=== AUTO-SURVEILLANCE DU JUDGE ===")
    rep = pipe.judge.auditor.report()
    for k, v in rep.items():
        print(f"  {k}: {v}")
