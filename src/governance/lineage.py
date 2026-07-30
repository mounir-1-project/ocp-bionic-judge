"""Traçabilité et gates d'intégrité des données et artefacts modèle."""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

PROMOTION_STATUSES = {
    "candidate",
    "validated_offline",
    "shadow_only",
    "approved_for_pilot",
    "approved_for_production",
    "rejected",
}
RUNTIME_STATUSES = {
    "shadow_only",
    "approved_for_pilot",
    "approved_for_production",
}
MANDATORY_GATES = {
    "causalite_temporelle",
    "redondance_features",
    "stabilite_hors_periode",
    "labels_gmao",
    "validation_externe",
}


class ManifestValidationError(ValueError):
    """Artefact refusé par une gate vérifiable."""


def sha256_file(path: str | Path) -> str:
    """Calcule l'empreinte stable d'un fichier par blocs."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def package_versions(
    names: tuple[str, ...] = (
        "numpy",
        "pandas",
        "scikit-learn",
        "fastapi",
        "pydantic",
        "joblib",
    ),
) -> dict[str, str]:
    """Versions des dépendances qui influencent directement l'inférence."""
    out: dict[str, str] = {}
    for name in names:
        try:
            out[name] = version(name)
        except PackageNotFoundError:
            out[name] = "not-installed"
    return out


def failed_mandatory_gates(validation: dict[str, Any]) -> list[str]:
    """Retourne les gates absentes ou en échec, jamais seulement celles listées."""
    by_name = {
        str(item.get("gate")): bool(item.get("passed"))
        for item in validation.get("deployment_gates", [])
        if isinstance(item, dict)
    }
    return sorted(gate for gate in MANDATORY_GATES if not by_name.get(gate, False))


def _chemin_relatif(chemin: Path) -> str:
    """Chemin relatif a la racine du depot, pour un artefact reproductible.

    Args:
        chemin: Chemin absolu ou relatif.

    Returns:
        Chemin POSIX relatif au depot, ou le nom du fichier a defaut.
    """
    racine = Path(__file__).resolve().parents[2]
    try:
        return Path(chemin).resolve().relative_to(racine).as_posix()
    except ValueError:
        return Path(chemin).name


def build_manifest(
    *,
    data_path: str | Path,
    model_path: str | Path,
    model_metadata: dict[str, Any],
    model_id: str = "e7301-behavioral-iforest",
    model_version: str | None = None,
) -> dict[str, Any]:
    """Construit un manifeste candidat complet et vérifiable.

    La création d'un artefact n'est jamais une promotion. Le statut initial
    reste donc ``candidate`` même lorsque certains contrôles hors ligne passent.
    """
    data, model = Path(data_path), Path(model_path)
    detector = model_metadata.get("detector", {})
    validation = model_metadata.get("validation", {})
    created = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": "2.0",
        "model_identity": {
            "id": model_id,
            "version": model_version or created.replace(":", "").replace("+00:00", "Z"),
        },
        "training": {
            "trained_at_utc": created,
            "data_period": detector.get("period"),
            "ordered_features": list(detector.get("features", [])),
            "decision_threshold": detector.get("threshold"),
        },
        "created_at_utc": created,
        # LES CHEMINS SONT RELATIFS AU DEPOT, JAMAIS ABSOLUS.
        # Le manifeste publiait `/home/<utilisateur>/...` : un artefact de
        # gouvernance qui porte l'arborescence de la machine de developpement
        # n'est pas reproductible, et il expose une information sans rapport
        # avec le projet. L'empreinte SHA-256 identifie le fichier; le chemin
        # ne sert qu'a le situer dans le depot.
        "data": {
            "path": _chemin_relatif(data),
            "sha256": sha256_file(data),
            "size_bytes": data.stat().st_size,
        },
        "model": {
            "path": _chemin_relatif(model),
            "sha256": sha256_file(model),
            "size_bytes": model.stat().st_size,
            "metadata": model_metadata,
        },
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": package_versions(),
        },
        "validation": {
            "results": validation,
            "failed_mandatory_gates": failed_mandatory_gates(validation),
        },
        "promotion": {
            "status": "candidate",
            "promoted_by": None,
            "promoted_at_utc": None,
            "process": "manual_governed_promotion",
        },
        "known_limitations": list(validation.get("limitations", [])),
    }


def validate_model_manifest(
    manifest: dict[str, Any],
    *,
    model_path: str | Path,
    data_path: str | Path,
    expected_features: list[str] | tuple[str, ...],
    allowed_statuses: set[str] | None = None,
) -> str:
    """Valide intégrité, schéma, runtime, gates et statut avant désérialisation.

    Returns:
        Le statut de promotion autorisé.

    Raises:
        ManifestValidationError: raison explicite et exploitable du refus.
    """
    allowed = allowed_statuses or RUNTIME_STATUSES
    try:
        if manifest.get("schema_version") != "2.0":
            raise ManifestValidationError("version de manifeste non supportée")
        status = str(manifest["promotion"]["status"])
        if status not in PROMOTION_STATUSES:
            raise ManifestValidationError(f"statut de promotion inconnu: {status}")
        if status not in allowed:
            raise ManifestValidationError(
                f"statut '{status}' non autorisé au runtime"
            )
        failed = list(manifest["validation"]["failed_mandatory_gates"])
        recomputed = failed_mandatory_gates(
            manifest["validation"]["results"]
        )
        if sorted(failed) != recomputed:
            raise ManifestValidationError("résumé des gates incohérent")
        if failed:
            raise ManifestValidationError(
                "gates obligatoires en échec: " + ", ".join(sorted(failed))
            )
        if sha256_file(model_path) != manifest["model"]["sha256"]:
            raise ManifestValidationError("empreinte SHA-256 du modèle incorrecte")
        if sha256_file(data_path) != manifest["data"]["sha256"]:
            raise ManifestValidationError("empreinte SHA-256 des données incorrecte")
        features = manifest["training"]["ordered_features"]
        if features != list(expected_features):
            raise ManifestValidationError("schéma ordonné des variables incompatible")
        current_python = platform.python_version()
        if manifest["runtime"]["python"] != current_python:
            raise ManifestValidationError(
                f"Python incompatible: manifeste={manifest['runtime']['python']}, "
                f"runtime={current_python}"
            )
        current_packages = package_versions(
            tuple(manifest["runtime"]["packages"].keys())
        )
        if manifest["runtime"]["packages"] != current_packages:
            raise ManifestValidationError("versions de bibliothèques incompatibles")
        threshold = manifest["training"]["decision_threshold"]
        if not isinstance(threshold, (int, float)) or not 0.0 <= threshold <= 1.0:
            raise ManifestValidationError("seuil de décision absent ou invalide")
        if not manifest["model_identity"]["id"] or not manifest["model_identity"]["version"]:
            raise ManifestValidationError("identité ou version du modèle absente")
        if not manifest["promotion"].get("promoted_by"):
            raise ManifestValidationError("auteur de promotion absent")
        if not manifest["promotion"].get("promoted_at_utc"):
            raise ManifestValidationError("date de promotion absente")
        return status
    except ManifestValidationError:
        raise
    except (KeyError, TypeError, AttributeError) as exc:
        raise ManifestValidationError(f"champ manifeste absent ou invalide: {exc}") from exc


def write_manifest(manifest: dict[str, Any], path: str | Path) -> Path:
    """Écrit un JSON canonique lisible et stable."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target
