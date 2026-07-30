"""Génère la source unique de vérité chiffrée du projet E7301."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

# Voir la note dans src/operations/alarms.py : compatibilite Python 3.10.
UTC = timezone.utc

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.main import app
from src.config import REPORT_DIR
from src.features.e7301_features import MODEL_FEATURES
from src.pipeline import E7301Pipeline


def _test_metrics(path: Path) -> dict:
    if not path.exists():
        return {"status": "not_measured"}
    root = ElementTree.parse(path).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        return {"status": "invalid_junit"}
    return {
        "status": "measured",
        "tests": int(suite.attrib.get("tests", 0)),
        "failures": int(suite.attrib.get("failures", 0)),
        "errors": int(suite.attrib.get("errors", 0)),
        "skipped": int(suite.attrib.get("skipped", 0)),
        "duration_s": float(suite.attrib.get("time", 0)),
    }


def _coverage_metrics(path: Path) -> dict:
    if not path.exists():
        return {"status": "not_measured"}
    totals = json.loads(path.read_text(encoding="utf-8"))["totals"]
    return {
        "status": "measured",
        "covered_lines": totals["covered_lines"],
        "statements": totals["num_statements"],
        "percent": round(float(totals["percent_covered"]), 2),
    }


def _relatif(chemin) -> str:
    """Chemin relatif a la racine du depot.

    Args:
        chemin: Chemin absolu ou relatif.

    Returns:
        Chemin relatif a la racine, ou le seul nom de fichier s'il est hors
        arborescence.
    """
    # `from pathlib import Path` etait reimporte ici alors que le module
    # l'importe deja en tete : un import local qui masque un import global
    # laisse croire a une dependance conditionnelle qui n'existe pas.
    racine = Path(__file__).resolve().parents[1]
    try:
        return Path(chemin).resolve().relative_to(racine).as_posix()
    except ValueError:
        return Path(chemin).name


def main() -> int:
    pipeline = E7301Pipeline(use_llm=False)
    scores = pipeline.detector.score_series(pipeline.features)
    threshold = float(pipeline.detector.stat.threshold_)
    alert_mask = scores >= threshold
    manifest_path = pipeline.model_path.with_suffix(".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    routes = sorted({
        route.path for route in app.routes
        if route.path.startswith("/api/")
    })
    metrics = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "application_version": app.version,
        "data": {
            # Chemin relatif : un artefact publie ne porte pas l'arborescence
            # de la machine qui l'a produit.
            "source": _relatif(pipeline.data_path),
            "sha256": manifest["data"]["sha256"],
            "raw_rows": pipeline.ingestion.report["n_raw_rows"],
            "usable_timestamps": len(pipeline.features),
            "period": [
                str(pipeline.features.index.min()),
                str(pipeline.features.index.max()),
            ],
            "dcs_tags": pipeline.ingestion.report["n_tags"],
            "duplicates_merged_with_audit": pipeline.ingestion.report["n_duplicates"],
        },
        "model": {
            "runtime_source": pipeline.model_source,
            "artifact_promotion_status": manifest["promotion"]["status"],
            "artifact_failed_gates": manifest["validation"]["failed_mandatory_gates"],
            "ordered_features": list(MODEL_FEATURES),
            "n_features": len(MODEL_FEATURES),
            "threshold": threshold,
            "alert_hours_historical": int(alert_mask.sum()),
            "episodes": len(pipeline.episodes()),
            "claim": "surveillance comportementale non supervisée, non validée terrain",
        },
        "api": {
            "route_count": len(routes),
            "routes": routes,
        },
        # REPORT_DIR ETAIT DECLARE ET JAMAIS LU. Les chemins litteraux
        # `Path("reports/...")` resolvaient relativement au repertoire courant :
        # la sortie changeait d'emplacement selon l'endroit d'ou la commande
        # etait lancee, et la variable prevue pour la deplacer n'avait aucun effet.
        "tests": _test_metrics(REPORT_DIR / "junit.xml"),
        "coverage": _coverage_metrics(REPORT_DIR / "coverage_final.json"),
        "industrial_validation": {
            "software_tests_prove_industrial_validity": False,
            "production_go": False,
        },
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    target = REPORT_DIR / "project_metrics.json"
    target.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
