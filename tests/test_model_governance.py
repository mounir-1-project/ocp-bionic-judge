"""Gates bloquants du manifeste modèle."""

from __future__ import annotations

from copy import deepcopy

import pytest

from src.governance.lineage import (
    ManifestValidationError,
    build_manifest,
    validate_model_manifest,
)

FEATURES = ["signal_a", "signal_b"]


def _validation(*, passed: bool = True) -> dict:
    names = (
        "causalite_temporelle",
        "redondance_features",
        "stabilite_hors_periode",
        "labels_gmao",
        "validation_externe",
    )
    return {
        "deployment_gates": [
            {"gate": name, "passed": passed, "evidence": "test"} for name in names
        ],
        "limitations": ["Validation terrain distincte des tests logiciels."],
    }


def _manifest(tmp_path, *, gates_pass=True):
    data = tmp_path / "data.bin"
    model = tmp_path / "model.bin"
    data.write_bytes(b"source-data")
    model.write_bytes(b"serialized-model")
    manifest = build_manifest(
        data_path=data,
        model_path=model,
        model_metadata={
            "detector": {
                "period": ["2024-01-01", "2024-02-01"],
                "features": FEATURES,
                "threshold": 0.73,
            },
            "validation": _validation(passed=gates_pass),
        },
    )
    return manifest, model, data


def _promote(manifest):
    promoted = deepcopy(manifest)
    promoted["promotion"].update(
        status="shadow_only",
        promoted_by="ci-governance-test",
        promoted_at_utc="2026-07-25T00:00:00+00:00",
    )
    return promoted


def test_candidat_est_refuse_meme_si_fichier_lisible(tmp_path):
    manifest, model, data = _manifest(tmp_path)
    with pytest.raises(ManifestValidationError, match="non autorisé"):
        validate_model_manifest(
            manifest,
            model_path=model,
            data_path=data,
            expected_features=FEATURES,
        )


def test_gates_en_echec_bloquent_un_statut_runtime(tmp_path):
    manifest, model, data = _manifest(tmp_path, gates_pass=False)
    manifest = _promote(manifest)
    with pytest.raises(ManifestValidationError, match="gates obligatoires"):
        validate_model_manifest(
            manifest,
            model_path=model,
            data_path=data,
            expected_features=FEATURES,
        )


def test_empreinte_modele_et_schema_ordonnee_sont_bloquants(tmp_path):
    manifest, model, data = _manifest(tmp_path)
    manifest = _promote(manifest)
    model.write_bytes(b"tampered")
    with pytest.raises(ManifestValidationError, match="modèle incorrecte"):
        validate_model_manifest(
            manifest,
            model_path=model,
            data_path=data,
            expected_features=FEATURES,
        )

    manifest, model, data = _manifest(tmp_path)
    manifest = _promote(manifest)
    with pytest.raises(ManifestValidationError, match="variables incompatible"):
        validate_model_manifest(
            manifest,
            model_path=model,
            data_path=data,
            expected_features=list(reversed(FEATURES)),
        )


def test_manifeste_promu_complet_est_autorise(tmp_path):
    manifest, model, data = _manifest(tmp_path)
    manifest = _promote(manifest)
    assert validate_model_manifest(
        manifest,
        model_path=model,
        data_path=data,
        expected_features=FEATURES,
    ) == "shadow_only"
