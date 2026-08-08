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
    """« Agent : rules » est une clef de code, pas un libelle d'exploitation.

    CE CONTROLE PORTAIT UN NOM PLUS LARGE QUE SA COUVERTURE. Il vérifiait trois
    vocabulaires — origines, modes d'agent, régimes — et le module en publie
    CINQ. Les deux qui manquaient sont précisément celles qui échappaient à la
    règle : l'état du contrôleur (`EN_ATTENTE`, un identifiant à tiret bas sur
    la première ligne de la section « information à agir ») et les codes de
    réserve (`NO_QUANTITATIVE_EVIDENCE`), que le poste traduit depuis longtemps
    et que le courriel expédiait bruts.

    Le courriel se lit sur un téléphone, la nuit, sans le contexte que l'écran
    fournit : c'est la surface où un code de programme coûte le plus.
    """
    from src.notifications.redaction import ETATS_CONTROLEUR

    texte = rediger_gouvernance(PAYLOAD)
    assert "règles déterministes" in texte
    assert "entraîné au démarrage, non promu" in texte
    assert "en marche" in texte
    for identifiant in ("runtime_trained_unpromoted", "Agent : rules", "h running"):
        assert identifiant not in texte

    # Réserves : le code brut ne sort pas, son libellé sort.
    assert "Diagnostic sans chiffres" in texte
    assert "NO_QUANTITATIVE_EVIDENCE" not in texte

    # État du contrôleur : `ALERTE` est aussi un mot français et ouvre son
    # propre libellé, donc on éprouve la traduction sur `EN_ATTENTE`.
    attente = rediger_gouvernance(
        {**PAYLOAD, "judge": {**PAYLOAD["judge"], "status": "EN_ATTENTE"}}
    )
    assert ETATS_CONTROLEUR["EN_ATTENTE"] in attente
    assert "EN_ATTENTE" not in attente

    # La période analysée est mise en forme comme la date d'édition : le
    # rapport ne doit pas porter deux formats de date sur une seule page.
    assert "01/01/2024" in texte
    assert "2024-01-01 07:00:00" not in texte


def test_le_rapport_rappelle_ce_qu_il_n_affirme_pas():
    """Une detection non supervisee qui laisse croire a un diagnostic confirme."""
    texte = rediger_gouvernance(PAYLOAD)
    assert "Aucune panne n'est confirmée" in texte
    assert "n'est pas promu" in texte


def test_un_payload_ampute_ne_fait_pas_echouer_l_envoi():
    """Un rapport partiel vaut mieux qu'une escalade qui ne part pas."""
    assert "E7301" in rediger_gouvernance({})
    assert rediger_gouvernance({"health": None, "judge": None})


def test_les_reserves_sont_traduites_des_deux_cotes():
    """Les vingt codes d'anomalie ont un libellé au poste ET dans le courriel.

    `app.js` traduisait les codes depuis longtemps — « le poste affichait le
    code brut OVERCONFIDENCE dans un encadré destiné à l'exploitant ; un code
    de programme n'est pas une réserve » — mais le COURRIEL D'ESCALADE
    expédiait toujours les codes bruts.

    C'est le canal le plus asymétrique du système : l'écran se lit devant le
    poste, le courriel se lit sur un téléphone, la nuit, sans contexte.

    Deux langages, donc deux tables : on ne partage pas un dictionnaire entre
    Python et JavaScript. Ce contrôle interdit qu'elles divergent — le patron,
    quinzième emploi.
    """
    import re
    from pathlib import Path

    from src.agents.schemas import RESERVE_LIBELLES

    racine = Path(__file__).resolve().parents[1]
    js = (racine / "api" / "static" / "app.js").read_text(encoding="utf-8")
    bloc = re.search(r"const RESERVE_LABEL = \{(.*?)\n\};", js, re.S)
    assert bloc, "RESERVE_LABEL introuvable dans app.js"
    poste = set(re.findall(r"^  ([A-Z_]+): \{", bloc.group(1), re.M))

    assert poste, "aucune réserve traduite côté poste"
    assert not poste - set(RESERVE_LIBELLES), (
        f"codes traduits au poste et absents du courriel : "
        f"{sorted(poste - set(RESERVE_LIBELLES))}"
    )
    assert not set(RESERVE_LIBELLES) - poste, (
        f"codes traduits dans le courriel et absents du poste : "
        f"{sorted(set(RESERVE_LIBELLES) - poste)}"
    )
    assert all(RESERVE_LIBELLES.values()), "un libellé vide ne traduit rien"
