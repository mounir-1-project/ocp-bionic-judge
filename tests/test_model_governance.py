"""Gates bloquants du manifeste modèle."""

from __future__ import annotations

import ast
import re
from copy import deepcopy
from pathlib import Path

import pytest

from src.governance.lineage import (
    ManifestValidationError,
    build_manifest,
    validate_model_manifest,
)

RACINE = Path(__file__).resolve().parents[1]

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


def test_tout_statut_de_promotion_declare_est_productible():
    """Un vocabulaire de gouvernance ne déclare pas d'états inatteignables.

    `PROMOTION_STATUSES` portait `validated_offline` et `rejected` — deux
    statuts qu'AUCUN code du dépôt ne pouvait écrire. Ils n'étaient pas
    inoffensifs : `validate_model_manifest` les acceptait comme statuts
    connus, si bien qu'un manifeste écrit à la main annonçant `rejected` était
    refusé pour « statut non autorisé au runtime » — motif qui laisse croire à
    un réglage, là où la vérité est qu'aucun processus ne peut le produire.

    Ce contrôle établit par analyse du source qu'il n'existe que deux
    producteurs de statut, et que leur union couvre exactement le vocabulaire.
    Rouvrir un état sans écrire le chemin qui l'atteint le fait échouer.
    """
    import inspect

    from src.governance import lineage

    # Producteur 1 — `build_manifest`, qui écrit toujours la même constante.
    arbre = ast.parse(inspect.getsource(lineage.build_manifest))
    ecrits = {
        noeud.value
        for noeud in ast.walk(arbre)
        if isinstance(noeud, ast.Constant)
        and isinstance(noeud.value, str)
        and noeud.value in lineage.PROMOTION_STATUSES
    }
    assert ecrits == {"candidate"}, (
        f"`build_manifest` n'écrit plus le seul statut attendu : {sorted(ecrits)}"
    )

    # Producteur 2 — `promote_model.py`, borné à RUNTIME_STATUSES en deux
    # endroits (le `choices` de l'option et la re-vérification de `promouvoir`).
    source = (RACINE / "scripts" / "promote_model.py").read_text(encoding="utf-8")
    assert "choices=sorted(RUNTIME_STATUSES)" in source
    assert "if statut not in RUNTIME_STATUSES:" in source

    productibles = ecrits | lineage.RUNTIME_STATUSES
    orphelins = lineage.PROMOTION_STATUSES - productibles
    assert not orphelins, (
        f"statuts déclarés qu'aucun code ne peut produire : {sorted(orphelins)}. "
        f"Soit écrire le chemin qui les atteint, soit les retirer du vocabulaire."
    )
    assert not (productibles - lineage.PROMOTION_STATUSES), (
        "un producteur écrit un statut absent du vocabulaire déclaré"
    )


def _portes_publiees_par_le_serveur() -> set[str]:
    """Codes de portes construits par `model_validation`, lus AU SOURCE.

    Le patron du dépôt, dixième emploi : on n'exécute pas le backtest — il
    demande le corpus entier et plusieurs minutes — on lit les littéraux
    `{"gate": "..."}` que la fonction construit.
    """
    source = (RACINE / "src" / "governance" / "model_validation.py").read_text(
        encoding="utf-8"
    )
    portes: set[str] = set()
    for noeud in ast.walk(ast.parse(source)):
        if not isinstance(noeud, ast.Dict):
            continue
        for cle, valeur in zip(noeud.keys, noeud.values):
            if (
                isinstance(cle, ast.Constant)
                and cle.value == "gate"
                and isinstance(valeur, ast.Constant)
                and isinstance(valeur.value, str)
            ):
                portes.add(valeur.value)
    return portes


def _intitules_du_poste() -> set[str]:
    """Clés de `GATE_LABEL` dans `api/static/app.js`, lues au source."""
    source = (RACINE / "api" / "static" / "app.js").read_text(encoding="utf-8")
    bloc = re.search(r"const GATE_LABEL = \{(.*?)\n\};", source, re.S)
    assert bloc, "GATE_LABEL introuvable dans app.js"
    return set(re.findall(r"^\s*([a-z_]+)\s*:", bloc.group(1), re.M))


def test_les_portes_publiees_ont_toutes_un_intitule_a_l_ecran():
    """Toute porte servie doit avoir un intitulé métier, et réciproquement.

    LE DEFAUT QUE CE TEST INTERDIT. Les phases 0.6 et 0.7 ont scinde deux
    portes; le serveur en a publie sept, `GATE_LABEL` en connaissait cinq. Les
    deux nouvelles tombaient sur le repli `g.gate.replace(/_/g, " ")` et
    s'affichaient sans accents et en minuscules — le defaut meme que le
    commentaire de `renderValidation` declare corrige.

    Le sens inverse est verifie aussi : un intitule sans porte est une surface
    morte, et le depot en a retire une dizaine.
    """
    servies = _portes_publiees_par_le_serveur()
    affichees = _intitules_du_poste()
    assert servies, "aucune porte lue dans model_validation.py"
    assert not servies - affichees, (
        f"portes servies sans intitule a l'ecran : {sorted(servies - affichees)}"
    )
    assert not affichees - servies, (
        f"intitules sans porte correspondante : {sorted(affichees - servies)}"
    )


def test_une_porte_publiee_non_bloquante_n_empeche_pas_la_promotion(tmp_path):
    """La décision la plus délicate de la gouvernance n'était verrouillée nulle part.

    Les phases 0.6 et 0.7 ont scindé deux portes. `redondance_hors_modele` et
    `derive_de_distribution` sont désormais **publiées, en échec, et hors de
    `MANDATORY_GATES`** — parce qu'aucun commit ne peut les franchir : la
    première est une propriété algébrique (ADR-001), la seconde n'est
    interprétable sur aucun pli de ce corpus (S21-3).

    Le journal d'audit s'en inquiétait explicitement : restreindre un critère
    « pour qu'il puisse passer » REMASQUE ce que l'auteur avait délibérément
    rendu visible. La parade retenue — publier sans bloquer — n'était vérifiée
    par **aucun test** : `_validation()` ne construit que les cinq portes
    obligatoires, et le seul contrôle d'échec les fait toutes échouer ensemble.

    Deux régressions symétriques passaient donc inaperçues : ajouter une de ces
    deux portes à `MANDATORY_GATES` rendrait la promotion impossible sans que
    rien ne le dise, et retirer une porte obligatoire l'autoriserait à tort.
    """
    from src.governance.lineage import MANDATORY_GATES, failed_mandatory_gates

    validation = _validation(passed=True)
    validation["deployment_gates"] += [
        {"gate": "redondance_hors_modele", "passed": False,
         "evidence": "propriété algébrique permanente, ADR-001"},
        {"gate": "derive_de_distribution", "passed": False,
         "evidence": "aucun pli saisonnièrement couvert"},
    ]

    # Les deux portes en échec ne sont pas obligatoires : rien ne bloque.
    assert not failed_mandatory_gates(validation), (
        "une porte publiée non bloquante fait échouer la promotion : la "
        "distinction des phases 0.6 et 0.7 a été perdue"
    )
    assert {"redondance_hors_modele", "derive_de_distribution"}.isdisjoint(
        MANDATORY_GATES
    ), "une porte qu'aucun commit ne peut franchir est redevenue bloquante"

    # Et le manifeste correspondant est bien accepté de bout en bout.
    data, model = tmp_path / "d.bin", tmp_path / "m.bin"
    data.write_bytes(b"source-data")
    model.write_bytes(b"serialized-model")
    manifest = _promote(build_manifest(
        data_path=data, model_path=model,
        model_metadata={
            "detector": {"period": ["2024-01-01", "2024-02-01"],
                         "features": FEATURES, "threshold": 0.73},
            "validation": validation,
        },
    ))
    assert validate_model_manifest(
        manifest, model_path=model, data_path=data, expected_features=FEATURES,
    ) == "shadow_only"
