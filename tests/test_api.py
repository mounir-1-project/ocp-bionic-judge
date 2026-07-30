"""
Tests de l'API et du rejeu temps reel.

La chaine est construite une seule fois pour tout le module : le TestClient
declenche le cycle de vie complet de l'application, exactement comme en
production.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import time

import pytest

fastapi = pytest.importorskip("fastapi", reason="fastapi non installe")
from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    """Client de test avec cycle de vie complet de l'application."""
    with TestClient(app) as c:
        yield c


# ── Systeme ───────────────────────────────────────────────────────────────────

def test_sante(client):
    """L'API doit exposer son etat et le mode de ses agents."""
    d = client.get("/api/health").json()
    assert d["status"] == "degraded"
    assert d["ready_for_demo"] is True
    assert d["ready_for_production"] is False
    assert d["version"] == "3.0.0"
    assert d["equipment"] == "S-PC-E7301"
    assert d["n_samples"] > 10000
    assert d["data_start"] < d["data_end"]
    assert d["sampling"] == "1h"
    # Un modele non promu doit TOUJOURS dire pourquoi. Le motif variait selon
    # la strategie de chargement, et restait vide en mode `train` : la sante
    # annoncait alors un artefact non promu sans cause consultable.
    assert d["model_rejection_reason"]
    assert d["model_source"].startswith(("runtime_trained", "promoted_artifact"))
    assert client.get("/api/health/live").json()["status"] == "alive"
    assert client.get("/api/health/ready").json()["status"] == "ready"
    assert client.get("/api/health/database").json()["status"] == "available"
    assert client.get("/api/health/model").json()["approved_for_production"] is False
    assert client.get("/api/health/version").json()["rule_version"]


def test_dashboard_servi(client):
    """Le poste et ses actifs doivent fonctionner hors ligne."""
    r = client.get("/")
    assert r.status_code == 200
    assert "E7301" in r.text

    # Une seule feuille de style et un seul module d'entree : la version
    # precedente en empilait deux qui se contredisaient.
    assert r.text.count("<link rel=\"stylesheet\"") == 1
    assert "/assets/app.css" in r.text
    assert "/assets/app.js" in r.text
    assert "/assets/dashboard.css" not in r.text
    assert "/assets/hmi-refinement.css" not in r.text

    # Aucune ressource distante : le poste doit tourner sans Internet.
    assert "cdnjs.cloudflare.com" not in r.text
    assert "//unpkg" not in r.text
    assert "/assets/chart.umd.min.js" in r.text

    # Le jumeau 3D est la vue principale, avec ses commandes.
    assert 'id="twin"' in r.text
    assert 'id="toolCut"' in r.text
    assert 'id="drawer"' in r.text
    assert "SIZE 1118-9754" in r.text

    # Aucun chiffre de modele ecrit en dur dans la page.
    assert "0,487" not in r.text
    assert "R² 0,968" not in r.text

    # La couche economique a ete retiree du perimetre.
    assert "MAD" not in r.text
    assert "business" not in r.text.lower()


def test_entetes_de_securite_du_dashboard(client):
    """La page doit porter ses en-tetes de securite."""
    r = client.get("/")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_actifs_servis_et_actifs_supprimes(client):
    """Le poste embarque ses actifs; les anciens ne doivent plus exister."""
    # L'ancienne pile frontend a ete retiree, pas seulement debranchee.
    for gone in ("dashboard.css", "hmi-refinement.css", "dashboard.js", "e7301-twin.js"):
        assert client.get(f"/assets/{gone}").status_code == 404

    for kept in ("app.css", "app.js", "twin.js", "three.module.min.js"):
        assert client.get(f"/assets/{kept}").status_code == 200

    chart = client.get("/assets/chart.umd.min.js")
    assert len(chart.content) > 100_000

    css = client.get("/assets/app.css")
    assert b"prefers-reduced-motion" in css.content

    twin = client.get("/assets/twin.js")
    # Le jumeau doit poser des capteurs et un etat de defaut, pas seulement
    # dessiner une forme : ce sont ces deux methodes qui manquaient avant.
    assert b"setSensors" in twin.content
    assert b"setState" in twin.content

    app_js = client.get("/assets/app.js")
    # Le rattachement anomalie -> piece doit venir du referentiel, pas d'une
    # recherche de sous-chaine dans le libelle de l'anomalie.
    assert b"finding_map" in app_js.content
    assert b'includes("FAISCEAU")' not in app_js.content

    assert client.get("/assets/e7301-field.jpg").status_code == 200
    assert client.get("/assets/e7301-tubesheet.jpg").status_code == 200

    # La marque est embarquee, comme le reste : le poste doit s'afficher
    # complet sans acces reseau.
    logo = client.get("/assets/ocp-logo.png")
    assert logo.status_code == 200
    assert logo.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert client.get("/assets/favicon.png").status_code == 200

    page = client.get("/").text
    assert "/assets/ocp-logo.png" in page
    assert 'href="data:,"' not in page, "l'onglet du navigateur restait sans icone"


def test_acces_local_et_notifications_desactivees(client):
    """Le mode local reste utilisable et aucun email ne part sans SMTP."""
    auth = client.get("/api/auth/status")
    assert auth.status_code == 200
    assert auth.json()["authenticated"] is True
    assert auth.json()["operator"]["role"] == "local"

    status = client.get("/api/notifications/status")
    assert status.status_code == 200
    assert status.json()["enabled"] is False
    assert client.post("/api/notifications/test").status_code == 409
    assert client.post("/api/notifications/governance").status_code == 409


def test_acces_protege_session_et_csrf(client, monkeypatch):
    """Une session identifiée protège les API mutantes par un jeton CSRF."""
    import api.main as api_main
    from src import config
    from src.security import AuthManager, hash_password

    manager = AuthManager(
        password_hash=hash_password("phrase secrete industrielle 2026"),
        allowed_emails={"tech@example.test"},
        user_roles={"tech@example.test": "operator"},
    )
    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    monkeypatch.setattr(api_main, "AUTH_MANAGER", manager)

    assert client.get("/api/equipment").status_code == 401
    login = client.post("/api/auth/login", json={
        "email": "tech@example.test",
        "password": "phrase secrete industrielle 2026",
    })
    assert login.status_code == 200
    assert login.json()["operator"]["email"] == "tech@example.test"
    assert client.get("/api/notifications/status").json()["recipient"] == (
        "te***@example.test"
    )
    csrf = login.json()["operator"]["csrf_token"]
    assert client.get("/api/equipment").status_code == 200
    assert client.post("/api/replay/stop").status_code == 403
    assert client.post(
        "/api/replay/stop",
        headers={"X-CSRF-Token": csrf},
    ).status_code == 200

    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/equipment").status_code == 401


def test_role_lecture_ne_peut_pas_piloter_le_rejeu(client, monkeypatch):
    """Le rôle reader lit l'état mais ne déclenche aucune action d'exploitation."""
    import api.main as api_main
    from src import config
    from src.security import AuthManager, hash_password

    manager = AuthManager(
        password_hash=hash_password("phrase secrete industrielle 2026"),
        allowed_emails={"lecture@example.test"},
        user_roles={"lecture@example.test": "reader"},
    )
    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    monkeypatch.setattr(api_main, "AUTH_MANAGER", manager)
    login = client.post(
        "/api/auth/login",
        json={
            "email": "lecture@example.test",
            "password": "phrase secrete industrielle 2026",
        },
    )
    assert login.status_code == 200
    csrf = login.json()["operator"]["csrf_token"]
    assert client.get("/api/replay/state").status_code == 200
    denied = client.post(
        "/api/replay/start",
        json={"speed": 120, "analyze_every": 6},
        headers={"X-CSRF-Token": csrf},
    )
    assert denied.status_code == 403
    assert "Rôle insuffisant" in denied.json()["detail"]
    assert client.post("/api/auth/logout").status_code == 200


def test_gouvernance_declare_les_angles_morts(client):
    """Le rapport de gouvernance doit dire ce que le systeme ne voit pas."""
    d = client.get("/api/governance").json()
    assert d["blind_spots"], "aucun angle mort declare"
    codes = {b["code"] for b in d["blind_spots"]}
    assert "PLAQUE_SACRIFICIELLE_DYSFONCTION" in codes
    assert d["sensor_health"]

    # Les trois references sont publiees separement. Celle qui porte le
    # diagnostic d'encrassement est la conductance, ancree sur l'eau de mer.
    refs = d["references"]
    conductance = refs["conductance"]
    assert conductance["ua_reference"] > 5.0
    assert conductance["r2"] > 0.85
    assert "Safi" in conductance["seawater_source"]

    # L'effort de regulation publie sa part non apprise : c'est ce chiffre qui
    # empeche de re-vendre son R2 comme une preuve.
    assert refs["regulation_effort"]["r2"] > 0.85
    assert refs["regulation_effort"]["naive_r2"] > 0.85
    assert refs["regulation_effort"]["learned_gain"] < 0.10
    assert 0.2 < refs["inlet"]["r2"] < 0.95
    assert "encrassement" in refs["hierarchy"]


def test_validation_scientifique_exposee(client):
    """L'API distingue stabilité mesurée et performance prédictive inconnue."""
    d = client.get("/api/model/validation").json()
    assert d["scientific_status"].startswith("surveillance comportementale")
    assert d["temporal_backtest"]["folds"]
    assert "non démontrable" in d["predictive_claim"]


def test_fiche_equipement(client):
    """La fiche doit exposer tags, AMDEC et plan de maintenance."""
    d = client.get("/api/equipment").json()
    assert len(d["tags"]) == 12
    assert len(d["amdec"]) >= 10
    assert set("ABCDEFGH") <= set(d["plan_maintenance"])
    # L'AMDEC doit etre triee par criticite decroissante.
    crits = [m["C"] for m in d["amdec"]]
    assert crits == sorted(crits, reverse=True)
    sensor_rule = next(m for m in d["amdec"] if m["code"] == "CAPTEUR_DEFAILLANT")
    assert sensor_rule["provenance_category"] == "application_rule"
    assert sensor_rule["original_values"]["C"] is None


def test_workflow_inspection_executable_et_trace(client):
    """La checklist API doit bloquer les incohérences et conserver la signature."""
    templates = client.get("/api/workflows/templates")
    assert templates.status_code == 200
    assert "permis de travail" in templates.json()["INSPECTION_EXTERNE"]["warning"]

    created = client.post("/api/workflows", json={
        "template_id": "INSPECTION_EXTERNE",
        "owner": "Équipe mécanique PS III",
        "planned_at": "2026-08-01T08:00:00",
    })
    assert created.status_code == 201
    workflow = created.json()
    assert workflow["status"] == "PLANNED"
    assert workflow["steps"]

    first = workflow["steps"][0]
    updated = client.patch(
        f"/api/workflows/{workflow['id']}/steps/{first['id']}",
        json={
            "status": "COMPLETED",
            "comment": "Contrôle visuel documenté",
            "measurement": "Conforme",
            "unit": "-",
            "proof_ref": "photo-locale-non-jointe",
            "expected_version": first["version"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["steps"][0]["completed_by"] == "poste-local"

    stale = client.patch(
        f"/api/workflows/{workflow['id']}/steps/{first['id']}",
        json={
            "status": "COMPLETED",
            "comment": "Version périmée",
            "expected_version": first["version"],
        },
    )
    assert stale.status_code == 409
    assert client.post(
        f"/api/workflows/{workflow['id']}/complete",
        json={"signature": "Chef atelier mécanique"},
    ).status_code == 409

    current = updated.json()
    for step in current["steps"][1:]:
        response = client.patch(
            f"/api/workflows/{workflow['id']}/steps/{step['id']}",
            json={
                "status": "COMPLETED",
                "comment": "Contrôle exécuté",
                "expected_version": step["version"],
            },
        )
        assert response.status_code == 200

    completed = client.post(
        f"/api/workflows/{workflow['id']}/complete",
        json={
            "signature": "Chef atelier mécanique",
            "proof_ref": "Compte rendu à verser dans la GMAO",
        },
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETED"
    assert client.get(f"/api/workflows/{workflow['id']}").status_code == 200
    assert any(
        item["id"] == workflow["id"] for item in client.get("/api/workflows").json()
    )


# ── Donnees ───────────────────────────────────────────────────────────────────

def test_series_temporelles(client):
    """Les series doivent etre sous-echantillonnees et completes."""
    d = client.get("/api/timeseries?max_points=300").json()
    assert d["n_returned"] <= 300
    assert len(d["timestamps"]) == d["n_returned"]
    assert d["timestamps"][-1].startswith("2025-02-28")
    for col in ("T_ACID_IN", "T_ACID_OUT", "duty_kw", "duty_expected"):
        assert col in d and len(d[col]) == d["n_returned"]
    aliases = {
        tag["alias"] for tag in client.get("/api/equipment").json()["tags"]
    }
    assert aliases <= d.keys()
    assert any(value == 327.67 for value in d["TI_5303"] if value is not None)
    assert any(value is not None for value in d["PHI_5306"])


def test_series_filtrees_par_periode(client):
    """Le filtrage temporel doit reduire le volume renvoye."""
    full = client.get("/api/timeseries?max_points=20000").json()
    part = client.get(
        "/api/timeseries?start=2024-10-01&end=2024-10-31&max_points=20000"
    ).json()
    assert part["n_total"] < full["n_total"]


def test_series_refusent_les_bornes_invalides(client):
    """Les dates illisibles ou inversees doivent produire une erreur client."""
    assert client.get("/api/timeseries?start=pas-une-date").status_code == 422
    assert client.get(
        "/api/timeseries?start=2024-11-01&end=2024-10-01"
    ).status_code == 422
    # Une date ISO avec fuseau reste compatible avec l'index DCS local.
    assert client.get(
        "/api/timeseries?end=2024-10-01T00:00:00Z&max_points=100"
    ).status_code == 200


def test_sante_capteurs(client):
    """La synthese capteurs doit remonter les defauts averes."""
    d = client.get("/api/sensor-health").json()
    by_alias = {r["alias"]: r for r in d}
    assert by_alias["TI_5303"]["n_saturated"] > 4000
    assert by_alias["PHI_5306"]["n_frozen"] > 500


def test_episodes_tries(client):
    """Les episodes doivent etre tries par gravite decroissante."""
    d = client.get("/api/episodes?limit=20").json()
    assert d
    scores = [e["score_max"] for e in d]
    assert scores == sorted(scores, reverse=True)


# ── Analyse ───────────────────────────────────────────────────────────────────

def test_analyse_dun_instant(client):
    """Une analyse doit contenir detection, decision et verdict complets."""
    r = client.post("/api/analyze", json={"timestamp": "2024-10-25T21:00:00"})
    assert r.status_code == 200
    d = r.json()
    assert d["detection"]["severity"] in ("NORMAL", "INFO", "WARNING", "CRITICAL")
    assert d["decision"]["diagnosis"]
    assert len(d["verdict"]["checks"]) == 8
    assert 0.0 <= d["verdict"]["global_score"] <= 10.0


def test_instant_inconnu_renvoie_404(client):
    """Un horodatage hors periode doit renvoyer une erreur explicite."""
    r = client.post("/api/analyze", json={"timestamp": "2030-01-01T00:00:00"})
    assert r.status_code == 404
    assert "absent" in r.json()["detail"]


def test_instants_notables(client):
    """Les instants notables doivent etre analysables en lot."""
    d = client.get("/api/notable?limit=5").json()
    assert 0 < len(d) <= 5
    assert all("judge_score" in a for a in d)


# ── Temps reel ────────────────────────────────────────────────────────────────

def test_cycle_de_rejeu(client):
    """Le rejeu doit demarrer, produire des analyses, puis s'arreter."""
    start = client.post(
        "/api/replay/start",
        json={"speed": 100000, "start": "2024-10-20", "analyze_every": 6},
    ).json()
    assert start["running"]
    assert start["started_at"]

    time.sleep(3)
    state = client.get("/api/replay/state").json()
    assert state["n_processed"] > 0

    stream = client.get("/api/replay/stream?n=5").json()
    assert stream
    a = stream[0]
    for key in ("timestamp", "severity", "judge_score", "judge_agreement", "diagnosis"):
        assert key in a

    stopped = client.post("/api/replay/stop").json()
    assert not stopped["running"]


def test_changement_de_vitesse(client):
    """La vitesse de rejeu doit etre modifiable a chaud."""
    client.post("/api/replay/start", json={"speed": 50, "analyze_every": 12})
    d = client.post("/api/replay/speed?speed=500").json()
    assert d["speed_hours_per_second"] == 500
    client.post("/api/replay/stop")


def test_vitesse_invalide_refusee(client):
    """Une vitesse negative doit etre rejetee par la validation."""
    assert client.post("/api/replay/speed?speed=-5").status_code == 422


def test_debut_de_rejeu_hors_periode_refuse(client):
    """Un rejeu vide doit etre refuse explicitement, pas demarrer sans donnees."""
    r = client.post(
        "/api/replay/start",
        json={"speed": 120, "start": "2030-01-01", "analyze_every": 3},
    )
    assert r.status_code == 422
    assert "Aucune donnee" in r.json()["detail"]


def test_arret_reste_immediat_a_basse_vitesse(client):
    """Le thread doit etre interruptible meme pendant une longue temporisation."""
    client.post(
        "/api/replay/start",
        json={"speed": 0.1, "start": "2024-10-20", "analyze_every": 24},
    )
    before = time.perf_counter()
    stopped = client.post("/api/replay/stop").json()
    elapsed = time.perf_counter() - before
    assert not stopped["running"]
    assert elapsed < 1.0


# ── Judge ─────────────────────────────────────────────────────────────────────

def test_audit_du_judge(client):
    """Le Judge doit exposer son auto-surveillance."""
    client.get("/api/notable?limit=5")
    d = client.get("/api/judge/audit").json()
    assert d["n"] > 0
    assert "self_check_warnings" in d


def test_evaluation_du_judge(client):
    """Le banc d'evaluation doit etre exposé et donner de bons resultats."""
    d = client.get("/api/judge/evaluation?n_cases=3").json()
    s = d["summary"]
    assert s["trap_detection_rate"] >= 0.85
    assert s["false_positive_rate"] <= 0.25
    assert d["by_trap"]


# ── Topologie et fiche capteur ────────────────────────────────────────────────

def test_topologie_exposee(client):
    """La representation 3D doit recevoir son contrat depuis le referentiel."""
    d = client.get("/api/topology").json()
    assert len(d["sensors"]) == 12
    assert len(d["components"]) >= 8
    assert d["meta"]["validation_status"] == "derived_from_equipment_sheet"

    sortie = next(s for s in d["sensors"] if s["alias"] == "T_ACID_OUT")
    assert sortie["setpoint"] == 66.0
    assert len(sortie["at"]) == 3
    assert sortie["attaches_to"] == "NOZZLE_ACID_OUT"

    # Le rattachement des codes voyage avec la topologie : sans lui, l'interface
    # devrait le deviner, ce qui etait precisement le defaut precedent.
    assert d["finding_map"]["CONC_DROP_SEVERE"]["components"] == ["BUNDLE", "TUBESHEET"]


def test_fiche_capteur_complete(client):
    """Un clic sur un capteur doit tout ramener en un seul appel."""
    d = client.get("/api/sensor/T_ACID_OUT?window_h=168").json()
    assert d["tag"] == "S_MC_SULF_TI1105_B"
    assert d["setpoint"] == 66.0
    assert d["rationale"]
    assert d["series"]["timestamps"] and d["series"]["values"]
    assert len(d["series"]["timestamps"]) == len(d["series"]["values"])
    assert d["stats"]["n_valid"] > 0
    assert 0 <= d["quality"]["availability_pct"] <= 100


def test_fiche_capteur_degrade_reste_consultable(client):
    """Un capteur mort doit rester lisible : c'est la seule facon de le voir mort."""
    d = client.get("/api/sensor/TI_5303?window_h=720").json()
    assert d["role"] == "degraded"
    assert d["quality"]["issues"]["SATURATED"] > 1000
    assert d["quality"]["availability_pct"] < 60
    assert d["stats"]["max"] == 327.67


def test_fiche_capteur_inconnu(client):
    assert client.get("/api/sensor/PAS_UN_CAPTEUR").status_code == 404


def test_indicateurs_sans_montant(client):
    """Les indicateurs ne doivent porter aucune valorisation monetaire."""
    d = client.get("/api/kpi").json()
    assert len(d["figures"]) == 5
    assert d["stabilite_regulation"]
    rendu = str(d).lower()
    for interdit in ("mad", "dirham", "roi", "euro"):
        assert interdit not in rendu.split()
    for figure in d["figures"]:
        assert figure["evidence_level"] in {"observed", "derived"}


def test_le_taux_horaire_de_signalement_est_publie(client):
    """CORRECTION D'AUDIT.

    Le projet n'affichait que la charge d'episodes agreges (~5 par mois), ce
    qui donnait l'impression d'un systeme sobre. Le taux HORAIRE reel est
    plusieurs fois superieur a la contamination de calibration, et depasse
    20 % sur certains mois. L'agregation masquait le probleme qu'elle
    pretendait resoudre.
    """
    d = client.get("/api/kpi").json()

    figure = next(f for f in d["figures"] if "signalement" in f["label"])
    assert figure["unit"] == "%"
    assert figure["value"] > 0

    assert d["calibration"]["contamination_visee_pct"] > 0
    monthly = d["signalement_mensuel"]
    assert len(monthly) >= 12
    assert max(m["part_signalee_pct"] for m in monthly) > figure["value"], (
        "le pire mois doit depasser la moyenne, sinon l'agregation ment encore"
    )


def test_la_couverture_du_risque_est_publiee(client):
    """Quelle fraction de la criticite AMDEC le systeme voit-il reellement ?"""
    d = client.get("/api/coverage").json()

    risque = d["risque"]
    assert 0 < risque["part_couverte_pct"] < 100
    assert risque["n_modes_aveugles"] > 0
    # Les deux modes de criticite 112 ne sont pas instrumentes : ils doivent
    # apparaitre, sinon le systeme laisse croire qu'il couvre le risque majeur.
    aveugles = {m["criticite"] for m in risque["modes_aveugles"]}
    assert 112 in aveugles

    tags = d["tags"]
    assert tags["perimetre_surveille"] == 6
    assert tags["n_total"] == 12
    # Chaque determination repose sur au moins deux bases independantes.
    assert all(entry["n_basis"] >= 2 for entry in tags["detail"])
    assert "recoupement" in tags["methode"]


def test_la_sensibilite_aux_parametres_arbitraires_est_publiee(client):
    """Contamination et periode de reference n'ont aucune justification physique."""
    d = client.get("/api/sensitivity").json()
    assert len(d["parametres_arbitraires"]) == 2
    assert len(d["contamination"]["grid"]) >= 4
    assert d["periode_reference"]["dispersion_part_derive_pct"] > 0


def test_le_banc_d_encrassement_est_expose(client):
    """La seule metrique de detection du projet doit etre consultable."""
    d = client.get(
        "/api/detection/fouling-bench?severities=0.20&duration_days=60"
    ).json()
    assert d["n_cases"] >= 1
    assert 0.0 <= d["detection_rate"] <= 1.0
    assert 0.0 <= d["useful_detection_rate"] <= d["detection_rate"] + 1e-9
    assert d["limitations"]
    assert d["cases"][0]["perte_UA_pct"] == 20.0


def test_le_banc_refuse_une_severite_physiquement_impossible(client):
    """LE TEST QUI EMPECHE LA RECHUTE LA PLUS COUTEUSE DU PROJET.

    L'endpoint acceptait autrefois `amplitudes=1,2,3`, herites d'une epoque ou
    l'injection ajoutait des degres. Devenues des FRACTIONS de perte de
    coefficient d'echange, ces memes valeurs decrivaient des pertes de 100,
    200 et 300 % : un echangeur qui n'echange plus rien, detecte par
    construction. La page de gouvernance affichait ainsi « 100 % de detection »
    sans rien demontrer.
    """
    for invalide in ("1", "2,3", "0.2,1.5", "0"):
        r = client.get(f"/api/detection/fouling-bench?severities={invalide}")
        assert r.status_code == 422, f"severite {invalide} acceptee a tort"
        assert "fraction" in r.json()["detail"].lower()


def test_endpoints_economiques_retires(client):
    """La couche economique ne doit plus repondre."""
    for gone in ("/api/business/kpi", "/api/business/case", "/api/business/assumptions"):
        assert client.get(gone).status_code == 404


# ── Routage des alertes vers le technicien connecte ──────────────────────────
def test_l_email_de_session_devient_destinataire_des_alertes(client, monkeypatch, tmp_path):
    """LE COMPORTEMENT ATTENDU BOUT EN BOUT.

    L'adresse saisie a la connexion n'est pas decorative : c'est elle qui
    recoit les etats critiques. On verifie la chaine complete, depuis un compte
    du registre jusqu'au destinataire effectif du canal e-mail.
    """
    import api.main as api_main
    from src import config
    from src.security import AuthManager
    from src.security.registry import OperatorRegistry

    registry = OperatorRegistry(tmp_path / "operators.json")
    registry.add(
        "astreinte@ocpgroup.ma", "motdepasse-industriel-2026", role="maintenance"
    )
    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    monkeypatch.setattr(
        api_main,
        "AUTH_MANAGER",
        AuthManager(
            user_hashes=registry.password_hashes(),
            user_roles=registry.roles(),
        ),
    )

    notifier = api_main.STATE["notifier"]
    avant = set(notifier._recipients)

    login = client.post("/api/auth/login", json={
        "email": "astreinte@ocpgroup.ma",
        "password": "motdepasse-industriel-2026",
    })
    assert login.status_code == 200

    # Le technicien connecte est desormais destinataire.
    assert "astreinte@ocpgroup.ma" in notifier._recipients

    status = client.get("/api/notifications/status").json()
    assert status["active_recipients"] >= 1
    # L'adresse n'est jamais renvoyee en clair.
    assert status["recipient"] is None or "***" in status["recipient"]
    assert status["requires_judge_agreement"] is True

    client.post("/api/auth/logout")
    assert "astreinte@ocpgroup.ma" not in notifier._recipients
    assert set(notifier._recipients) == avant


def test_un_mauvais_mot_de_passe_n_ajoute_aucun_destinataire(client, monkeypatch, tmp_path):
    """Une tentative echouee ne doit pas abonner l'adresse aux alertes."""
    import api.main as api_main
    from src import config
    from src.security import AuthManager
    from src.security.registry import OperatorRegistry

    registry = OperatorRegistry(tmp_path / "operators.json")
    registry.add("tech@ocpgroup.ma", "motdepasse-industriel-2026")
    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    monkeypatch.setattr(
        api_main, "AUTH_MANAGER",
        AuthManager(user_hashes=registry.password_hashes(), user_roles=registry.roles()),
    )
    notifier = api_main.STATE["notifier"]

    assert client.post("/api/auth/login", json={
        "email": "tech@ocpgroup.ma", "password": "mauvais",
    }).status_code == 401
    assert "tech@ocpgroup.ma" not in notifier._recipients


def test_le_canal_explique_pourquoi_il_est_inactif(client):
    """Un canal muet sans explication est le pire defaut d'un systeme d'astreinte."""
    status = client.get("/api/notifications/status").json()
    assert "transport_ready" in status
    assert "reason" in status
    if not status["enabled"]:
        assert status["reason"], "un canal inactif doit dire pourquoi"
