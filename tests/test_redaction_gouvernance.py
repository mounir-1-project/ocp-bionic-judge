"""Le rapport de gouvernance est un texte lisible, pas un vidage de structure.

Ce que partait auparavant : `json.dumps(payload, indent=2)`. Trois cents lignes
de dictionnaire imbriqué, expédiées par email à un technicien, contenant le
chemin absolu du poste qui les a produites.
"""

from __future__ import annotations

from src.notifications.redaction import rediger_gouvernance

PAYLOAD = {
    "equipment": "S-PC-E7301",
    "generated_at": "2026-07-31T19:46:57.357997",
    "health": {
        "equipment": {"code": "E7301", "name": "REFROIDISSEUR", "site": "Maroc Chimie"},
        "ingestion": {
            "source": "C:\\dev\\ocp-bionic-judge\\data\\raw\\DATA.xlsx",
            "t_start": "2024-01-01 07:00:00",
            "t_end": "2025-02-28 11:00:00",
            "n_raw_rows": 10182,
            "n_rows": 10180,
            "n_tags": 12,
            "step_nominal": "1 h",
            "state_counts": {"RUNNING": 8832, "STOPPED": 1251},
            "excluded_degraded": ["PHI_5306", "TI_5303"],
        },
        "sensor_health": [
            {"alias": "TI_5303", "role": "degraded",
             "availability_pct": 47.83, "n_saturated": 5170},
        ],
        "detector": {"n_train": 3367, "threshold": 0.9642612800415576,
                     "features": ["a", "b"]},
        "model_source": "runtime_trained_unpromoted",
        "model_promotion_status": None,
        "model_rejection_reason": "statut 'candidate' non autorise",
        "agent_mode": "rules",
        "judge_mode": "deterministic",
        "blind_spots": [
            {"element": "VANNE D'ACIDE", "mode": "Fuite", "criticite": 112,
             "couverture_preventive": ["F"]},
            {"element": "PORTE DE VISITE", "mode": "Fuite", "criticite": 90,
             "couverture_preventive": ["C"]},
        ],
    },
    "judge": {
        "n": 3436, "score_mean": 9.98, "agreement_rate": 1.0, "status": "ALERTE",
        "top_issues": [["NO_QUANTITATIVE_EVIDENCE", 25]],
        "self_check_warnings": ["COMPLAISANCE : valide plus de 97 %."],
    },
}


def test_le_rapport_ne_divulgue_aucun_chemin_absolu():
    """Le dépôt interdit déjà cela dans ses artefacts; l'email y échappait."""
    texte = rediger_gouvernance(PAYLOAD)
    for fragment in ("C:\\", "/home/", "/Users/", "ocp-bionic-judge", "/sessions/"):
        assert fragment not in texte, f"le rapport divulgue {fragment}"
    assert "DATA.xlsx" in texte, "le nom du fichier source reste une information utile"


def test_les_nombres_sont_ecrits_en_francais():
    """« 0.9642612800415576 » dans un document francophone, pour un site marocain."""
    texte = rediger_gouvernance(PAYLOAD)
    assert "0,9643" in texte, "seuil arrondi et virgule décimale attendus"
    assert "0.9642612800415576" not in texte
    assert "9,98" in texte


def test_le_verdict_du_controleur_ouvre_le_rapport():
    """L'information a agir etait noyee sous deux cents lignes de sante capteur."""
    texte = rediger_gouvernance(PAYLOAD)
    position_verdict = texte.index("VERDICT DU CONTRÔLEUR")
    position_capteurs = texte.index("CAPTEURS LES MOINS DISPONIBLES")
    assert position_verdict < position_capteurs
    assert "ALERTE" in texte
    assert "COMPLAISANCE" in texte


def test_les_identifiants_internes_sont_traduits():
    """« Agent : rules » est une clef de code, pas un libelle d'exploitation."""
    texte = rediger_gouvernance(PAYLOAD)
    assert "règles déterministes" in texte
    assert "entraîné au démarrage, non promu" in texte
    assert "en marche" in texte
    for identifiant in ("runtime_trained_unpromoted", "Agent : rules", "h running"):
        assert identifiant not in texte


def test_le_rapport_rappelle_ce_qu_il_n_affirme_pas():
    """Une detection non supervisee qui laisse croire a un diagnostic confirme."""
    texte = rediger_gouvernance(PAYLOAD)
    assert "Aucune panne n'est confirmée" in texte
    assert "n'est pas promu" in texte


def test_un_payload_ampute_ne_fait_pas_echouer_l_envoi():
    """Un rapport partiel vaut mieux qu'une escalade qui ne part pas."""
    assert "E7301" in rediger_gouvernance({})
    assert rediger_gouvernance({"health": None, "judge": None})
