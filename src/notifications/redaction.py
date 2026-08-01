"""Rédaction du rapport de gouvernance destiné au technicien.

POURQUOI CE MODULE EXISTE
----------------------------------------------------------------------------
L'endpoint `/api/notifications/governance` promet dans sa docstring « une
synthèse de gouvernance traçable ». Ce qui partait réellement était
`json.dumps(payload, indent=2)` : trois cents lignes de structure interne,
coefficients de régression compris, expédiées à l'adresse d'un technicien.

Trois défauts, par gravité croissante :

  1. CE N'EST PAS UNE SYNTHÈSE. Personne ne lit un dictionnaire imbriqué sur
     un téléphone. L'information qui compte — le contrôleur est en ALERTE sur
     son propre comportement — était noyée sous deux cents lignes de santé
     capteur. Un rapport que son destinataire ne lit pas ne trace rien.

  2. IL DIVULGUE L'ARBORESCENCE DU PRODUCTEUR.
     `C:\\dev\\ocp-bionic-judge\\data\\raw\\DATA.xlsx` partait dans chaque
     message. Le dépôt interdit déjà cela dans ses artefacts, et un test le
     vérifie — `test_les_artefacts_ne_portent_pas_de_chemin_absolu`. Le canal
     email échappait à ce contrôle. Seul le nom du fichier est conservé.

  3. IL EST ÉCRIT EN NOMBRES ANGLAIS. « 0.9642612800415576 » dans un document
     francophone destiné à un site marocain, quand tout le reste du poste
     applique la virgule décimale.

Le rapport produit ici tient en une page, place le verdict en tête, et se
termine par ce qu'il n'affirme pas — parce qu'une supervision non supervisée
qui laisse croire à un diagnostic confirmé est un risque, pas un service.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePath, PureWindowsPath
from typing import Any

from src import formatting

LARGEUR = 68

# LES IDENTIFIANTS INTERNES NE SONT PAS DES LIBELLES. Le rapport annoncait
# « Régimes : 8 832 h running », « Agent : rules », « Origine :
# runtime_trained_unpromoted » — des clefs de code livrees telles quelles a un
# exploitant francophone. Un identifiant inconnu retombe sur lui-meme plutot
# que de disparaitre : mieux vaut un mot anglais qu'une information perdue.
REGIMES = {
    "RUNNING": "en marche",
    "STOPPED": "à l'arrêt",
    "TRANSIENT": "en transitoire",
}
ORIGINES = {
    "runtime_trained_unpromoted": "entraîné au démarrage, non promu",
    "promoted_artifact": "artefact promu",
    "manifest_validated": "artefact validé par manifeste",
}
MODES_AGENT = {
    "rules": "règles déterministes",
    "llm": "modèle de langage",
    "hybrid": "règles + modèle de langage",
    "deterministic": "déterministe",
}


def _nombre(valeur: Any, decimales: int = 0, defaut: str = "—") -> str:
    """Met un nombre en forme française, en déléguant au module de formatage.

    FMT-1 — CE MODULE REDUPLIQUAIT `src.formatting.nombre`.
    Il a été écrit pour corriger un défaut de typographie — « 0.9642612800415576 »
    expédié à un technicien francophone — et il l'a corrigé en recopiant la
    conversion que `src/formatting` porte déjà. ADR-011, règle 2 : « la mise en
    forme des nombres est centralisée ». Le module qui invoque cette règle ne
    peut pas être celui qui l'enfreint.

    Deux comportements propres à ce rapport sont conservés, et c'est pourquoi
    une enveloppe subsiste au lieu d'un simple alias :

      - le défaut est **zéro décimale**, contre une dans `src.formatting` :
        seize appels de ce fichier s'y fient, et « 3 436,0 décisions jugées » ne
        se lit pas ;
      - un booléen ne se formate pas. `float(True)` vaut 1,0 : un champ resté à
        `True` s'afficherait « 1 » au lieu d'être signalé absent.

    Args:
        valeur: Nombre à mettre en forme.
        decimales: Décimales conservées.
        defaut: Rendu lorsque la valeur n'est pas un nombre exploitable.

    Returns:
        Le nombre en notation française, ou `defaut`.
    """
    if valeur is None or isinstance(valeur, bool):
        return defaut
    rendu = formatting.nombre(valeur, decimales)
    return defaut if rendu == "—" else rendu


def _horodatage(valeur: Any) -> str:
    """Date lisible, sans imposer un format machine au lecteur."""
    if not valeur:
        return "—"
    texte = str(valeur)
    for motif in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(texte, motif).strftime("%d/%m/%Y à %Hh%M")
        except ValueError:
            continue
    return texte


def _titre(texte: str) -> str:
    return f"\n{texte.upper()}\n{'-' * LARGEUR}"


def rediger_gouvernance(payload: dict) -> str:
    """Compose le rapport de gouvernance en texte lisible.

    Chaque accès est tolérant : un rapport amputé d'une section vaut mieux
    qu'une escalade qui ne part pas parce qu'une clé manquait.

    Args:
        payload: Structure produite par `/api/notifications/governance`.

    Returns:
        Le corps du message, prêt à être envoyé.
    """
    sante = payload.get("health") or {}
    juge = payload.get("judge") or {}
    equipement = sante.get("equipment") or {}
    ingestion = sante.get("ingestion") or {}
    detecteur = sante.get("detector") or {}

    lignes: list[str] = []
    lignes.append("RAPPORT DE GOUVERNANCE — " + str(equipement.get("code", "E7301")))
    lignes.append(str(equipement.get("name", "")).capitalize())
    atelier = equipement.get("atelier")
    site = equipement.get("site")
    if atelier or site:
        lignes.append(" · ".join(x for x in (atelier, site) if x))
    lignes.append("Édité le " + _horodatage(payload.get("generated_at")))
    lignes.append("=" * LARGEUR)

    # ── Verdict du contrôleur, en tête : c'est l'information à agir ──────────
    lignes.append(_titre("Verdict du contrôleur"))
    statut = juge.get("status") or "—"
    lignes.append(f"État : {statut}")
    if juge.get("n") is not None:
        lignes.append(
            f"{_nombre(juge.get('n'))} décisions jugées · "
            f"note moyenne {_nombre(juge.get('score_mean'), 2)}/10 · "
            f"accord {_nombre((juge.get('agreement_rate') or 0) * 100, 1)} %"
        )
    alertes = juge.get("self_check_warnings") or []
    if alertes:
        lignes.append("")
        lignes.append("Le contrôleur signale une anomalie sur son PROPRE comportement :")
        for message in alertes:
            lignes.append(f"  • {message}")
    reserves = juge.get("top_issues") or []
    if reserves:
        lignes.append("")
        lignes.append("Réserves les plus fréquentes sur les décisions :")
        for entree in reserves[:5]:
            try:
                code, compte = entree[0], entree[1]
            except (TypeError, IndexError, KeyError):
                continue
            lignes.append(f"  • {code} — {_nombre(compte)} cas")

    # ── Modèle réellement en service ────────────────────────────────────────
    lignes.append(_titre("Modèle en service"))
    origine = sante.get("model_source") or "—"
    lignes.append(f"Origine : {ORIGINES.get(origine, origine)}")
    promotion = sante.get("model_promotion_status")
    lignes.append(f"Statut de promotion : {promotion or 'aucun — artefact non promu'}")
    if sante.get("model_rejection_reason"):
        lignes.append(f"Motif : {sante['model_rejection_reason']}")
    if detecteur:
        lignes.append(
            f"Seuil de décision : {_nombre(detecteur.get('threshold'), 4)} · "
            f"{len(detecteur.get('features') or [])} variables · "
            f"{_nombre(detecteur.get('n_train'))} points d'apprentissage"
        )
    agent = sante.get("agent_mode") or "—"
    controleur = sante.get("judge_mode") or "—"
    lignes.append(
        f"Agent : {MODES_AGENT.get(agent, agent)} · "
        f"Contrôleur : {MODES_AGENT.get(controleur, controleur)}"
    )

    # ── Données ─────────────────────────────────────────────────────────────
    lignes.append(_titre("Données analysées"))
    source = ingestion.get("source")
    if source:
        # LE CHEMIN ABSOLU NE SORT PAS DU POSTE. `PurePath` seul ne découpe pas
        # un chemin Windows quand le service tourne sous Linux, et inversement :
        # on tente les deux, le nom de fichier est la seule chose utile ici.
        nom = PureWindowsPath(str(source)).name or PurePath(str(source)).name
        lignes.append(f"Source : {nom}")
    lignes.append(
        f"Période : {ingestion.get('t_start', '—')} → {ingestion.get('t_end', '—')}"
    )
    lignes.append(
        f"{_nombre(ingestion.get('n_rows'))} lignes retenues sur "
        f"{_nombre(ingestion.get('n_raw_rows'))} · "
        f"{_nombre(ingestion.get('n_tags'))} tags · "
        f"pas nominal {ingestion.get('step_nominal', '—')}"
    )
    etats = ingestion.get("state_counts") or {}
    if etats:
        lignes.append(
            "Régimes : "
            + " · ".join(
                f"{_nombre(v)} h {REGIMES.get(str(k).upper(), str(k).lower())}"
                for k, v in etats.items()
            )
        )
    ecartes = ingestion.get("excluded_degraded") or []
    if ecartes:
        lignes.append("")
        lignes.append(
            "Capteurs écartés du périmètre : " + ", ".join(str(x) for x in ecartes)
        )
        lignes.append(
            "  Leur signal est inexploitable sur la période; ils ne sont ni "
            "imputés ni utilisés comme preuve."
        )

    # ── Capteurs les plus dégradés ──────────────────────────────────────────
    capteurs = sante.get("sensor_health") or []
    if capteurs:
        lignes.append(_titre("Capteurs les moins disponibles"))
        for capteur in capteurs[:5]:
            alias = str(capteur.get("alias", "?"))
            dispo = _nombre(capteur.get("availability_pct"), 1)
            details = []
            if capteur.get("n_saturated"):
                details.append(f"{_nombre(capteur['n_saturated'])} points saturés")
            if capteur.get("n_frozen"):
                details.append(f"{_nombre(capteur['n_frozen'])} points figés")
            if capteur.get("n_out_of_range"):
                details.append(f"{_nombre(capteur['n_out_of_range'])} hors plage")
            suffixe = " — " + ", ".join(details) if details else ""
            role = capteur.get("role")
            marque = " [hors service]" if role == "degraded" else ""
            lignes.append(f"  {alias:<14}{dispo:>7} %{marque}{suffixe}")

    # ── Angles morts ────────────────────────────────────────────────────────
    angles = sante.get("blind_spots") or []
    if angles:
        lignes.append(_titre("Angles morts de la surveillance"))
        lignes.append(
            f"{_nombre(len(angles))} modes de défaillance AMDEC ne sont couverts "
            "par aucune"
        )
        lignes.append("détection instrumentée. Les plus critiques :")
        lignes.append("")
        tries = sorted(
            angles, key=lambda m: m.get("criticite") or 0, reverse=True
        )
        for mode in tries[:5]:
            couverture = ", ".join(str(x) for x in (mode.get("couverture_preventive") or []))
            lignes.append(
                f"  C={_nombre(mode.get('criticite')):<5} "
                f"{mode.get('element', '?')} — {mode.get('mode', '?')}"
                + (f"  (préventif {couverture})" if couverture else "")
            )
        lignes.append("")
        lignes.append(
            "Ces modes relèvent du plan préventif, pas de la surveillance en ligne."
        )

    # ── Réserves : la section qui empêche de sur-lire le reste ──────────────
    lignes.append(_titre("Ce que ce rapport n'affirme pas"))
    lignes.append(
        "Aucune panne n'est confirmée. Le système signale des écarts de\n"
        "comportement par rapport à une référence apprise; leur cause reste à\n"
        "établir sur le terrain."
    )
    if not promotion or promotion == "candidate":
        lignes.append(
            "\nLe modèle n'est pas promu : il n'a pas franchi les critères de\n"
            "déploiement, faute d'historique de pannes étiqueté. Ses sorties\n"
            "sont indicatives et ne valent pas décision de maintenance."
        )
    lignes.append("")
    lignes.append("=" * LARGEUR)
    lignes.append(
        "Message émis automatiquement par le poste de surveillance E7301."
    )

    return "\n".join(lignes)
