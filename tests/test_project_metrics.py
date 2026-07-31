"""Cohérence de la source unique de vérité chiffrée."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from api.main import app
from src.features.e7301_features import MODEL_FEATURES


def test_project_metrics_restent_coherentes_avec_les_artefacts():
    root = Path(__file__).resolve().parents[1]
    metrics = json.loads(
        (root / "reports/project_metrics.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (root / "models/e7301_detector.manifest.json").read_text(encoding="utf-8")
    )
    data_path = root / "data/raw/DATA.xlsx"
    data_sha = hashlib.sha256(data_path.read_bytes()).hexdigest()
    api_routes = {
        route.path for route in app.routes if route.path.startswith("/api/")
    }

    assert metrics["data"]["sha256"] == data_sha == manifest["data"]["sha256"]
    assert metrics["model"]["ordered_features"] == MODEL_FEATURES
    assert manifest["training"]["ordered_features"] == MODEL_FEATURES
    assert metrics["model"]["artifact_promotion_status"] == "candidate"
    assert metrics["model"]["artifact_failed_gates"]
    assert metrics["api"]["route_count"] == len(api_routes)
    assert set(metrics["api"]["routes"]) == api_routes
    # CE CONTROLE EXIGE UN AMORÇAGE, ET C'EST INHERENT.
    #
    # Il interdit de publier des metriques issues d'un run rouge — c'est son
    # objet. Mais `project_metrics.json` est produit a partir du `junit.xml`
    # d'une execution qui contient CE test : s'il echoue une fois, il
    # s'auto-entretient. Run rouge -> metriques a `failures: 1` -> test rouge.
    #
    # La sortie de boucle, a executer une seule fois apres tout changement qui
    # rend la suite rouge :
    #
    #   pytest tests/ -q --junitxml=reports/junit.xml \
    #          --deselect tests/test_project_metrics.py::test_project_metrics_restent_coherentes_avec_les_artefacts
    #   python scripts/generate_project_metrics.py
    #   pytest tests/ -q --junitxml=reports/junit.xml     # vert, 267 cas
    #   python scripts/generate_project_metrics.py        # instantane definitif
    #
    # Affaiblir l'assertion pour eviter la boucle reviendrait a autoriser la
    # publication de metriques rouges : le remede serait pire que la gene.
    assert metrics["tests"]["failures"] == metrics["tests"]["errors"] == 0
    assert metrics["coverage"]["percent"] >= 85.0
    assert metrics["industrial_validation"]["production_go"] is False


def test_les_artefacts_ne_portent_pas_de_chemin_absolu():
    """Un artefact publie ne doit pas porter l'arborescence de son producteur.

    Le manifeste et les metriques citaient `/home/<utilisateur>/...` : un
    chemin qui n'existe sur aucune autre machine, qui rend l'artefact non
    reproductible, et qui expose une information sans rapport avec le projet.
    """
    root = Path(__file__).resolve().parents[1]
    for nom in ("reports/project_metrics.json", "models/e7301_detector.manifest.json"):
        contenu = (root / nom).read_text(encoding="utf-8")
        for prefixe in ("/home/", "/Users/", "C:\\\\", "/sessions/"):
            assert prefixe not in contenu, f"{nom} contient un chemin absolu {prefixe}"


def test_le_rapport_technique_cite_les_artefacts():
    """LE TEST QUI EMPECHE LE RAPPORT DE DERIVER DE SES PROPRES CHIFFRES.

    La section 6 publiait sept valeurs et deux identifiants contredits par
    `project_metrics.json` et par le manifeste du jour — dont « 77 episodes »
    en tete du resume executif, quand l'artefact en comptait 59. Un examinateur
    ouvre le fichier que le projet designe comme sa source de verite, et lit
    autre chose. Deux identifiants cites comme preuves n'existaient meme pas
    dans le depot : une commande `grep` suffisait a le montrer.

    Ce test compare le rapport aux artefacts a chaque execution.
    """
    root = Path(__file__).resolve().parents[1]
    rapport = (root / "docs/rapport_technique.md").read_text(encoding="utf-8")
    metrics = json.loads(
        (root / "reports/project_metrics.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (root / "models/e7301_detector.manifest.json").read_text(encoding="utf-8")
    )

    # Chiffres qui doivent figurer tels quels dans le rapport.
    attendus = {
        "nombre de features": str(metrics["model"]["n_features"]),
        "episodes": str(metrics["model"]["episodes"]),
        "heures signalees": str(metrics["model"]["alert_hours_historical"]),
        "seuil de decision": f"{manifest['training']['decision_threshold']:.4f}".replace(
            ".", ","
        ),
    }
    manquants = {k: v for k, v in attendus.items() if v not in rapport}
    assert not manquants, (
        "le rapport technique ne cite pas les valeurs des artefacts : "
        + ", ".join(f"{k} attendu {v}" for k, v in manquants.items())
    )

    # Identifiants cites comme preuves : ils doivent exister dans le depot.
    for identifiant in ("CONC_BIAS_DRIFT", "test_sur_refroidissement_est_un_regime_de_conduite"):
        if identifiant not in rapport:
            continue
        trouve = any(
            identifiant in chemin.read_text(encoding="utf-8", errors="ignore")
            for dossier in ("src", "tests")
            for chemin in (root / dossier).rglob("*.py")
        )
        assert trouve, f"le rapport cite {identifiant}, absent du depot"

    for fantome in ("CONC_CROSS_CHECK", "test_exces_de_duty_nest_pas_un_encrassement"):
        assert fantome not in rapport, (
            f"le rapport cite {fantome}, qui n'existe nulle part dans le code"
        )
