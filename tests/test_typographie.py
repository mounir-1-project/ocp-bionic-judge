"""
Typographie des textes destines a l'exploitant.

POURQUOI CE FICHIER EXISTE
----------------------------------------------------------------------------
Le poste affichait deux francais differents dans la meme carte. Les libelles
ecrits dans l'interface portaient leurs accents — « Fenêtre causale »,
« Épisodes les plus sévères » — tandis que tout texte produit par le backend
en etait depourvu : « Le modele statistique classe ce point comme atypique »,
« criticite 105 », « arret process ». Les deux se touchaient a l'ecran.

Ce n'est pas un detail cosmetique. Un exploitant, un ingenieur fiabilite ou un
jury lisent d'abord la forme; un texte sans accents signale un contenu produit
a la chaine plutot que redige, et jette un doute sur le reste. La correction ne
tient que si elle est verrouillee : sans ce test, la premiere chaine ajoutee
sans accents reintroduit le probleme sans que personne ne le voie.

CE QUE LE TEST COUVRE
----------------------------------------------------------------------------
Les trois surfaces que l'exploitant lit reellement :
  - les messages des regles de detection et du modele,
  - les libelles et lectures des indicateurs,
  - le referentiel metier affiche (AMDEC, plan preventif).

Il ne couvre PAS les commentaires de code, les docstrings, les identifiants
techniques ni les blocs `original_values` de l'AMDEC, qui reproduisent le
document OCP de 2019 tel qu'il a ete recu — les alterer serait une faute de
provenance bien plus grave qu'un accent manquant.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import re

import pytest
import yaml

from src.analytics import OperationalKPI
from src.domain.knowledge import AMDEC_PATH

# Mots francais courants dans ce domaine dont la forme SANS accent est fautive.
# La detection est volontairement lexicale plutot que morphologique : elle est
# exacte sur ce qu'elle couvre, et n'invente aucun faux positif.
MOTS_A_ACCENTUER: dict[str, str] = {
    "acceleree": "accélérée",
    "arret": "arrêt",
    "arrets": "arrêts",
    "controle": "contrôle",
    "criticite": "criticité",
    "declenche": "déclenche",
    "defaillance": "défaillance",
    "defaut": "défaut",
    "degradation": "dégradation",
    "degrade": "dégradé",
    "degradee": "dégradée",
    "degres": "degrés",
    "derive": "dérive",
    "detecte": "détecté",
    "detection": "détection",
    "donnees": "données",
    # AJOUTS — CE QUE LE LEXIQUE NE COUVRAIT PAS, ET QUI ETAIT FAUTIF.
    # `_quote_measurements` écrivait « entree acide », « debit acide » : même
    # échantillonné, ce test l'aurait laissé passer, faute d'avoir ces deux
    # mots. Un lexique est exact sur ce qu'il couvre — encore faut-il qu'il
    # couvre les mots que le système écrit réellement.
    "debit": "débit",
    "entree": "entrée",
    "elevee": "élevée",
    "reserve": "réserve",
    "procede": "procédé",
    "operationnel": "opérationnel",
    "associee": "associée",
    "echange": "échange",
    "echangeur": "échangeur",
    "ecart": "écart",
    "energie": "énergie",
    "epaisseur": "épaisseur",
    "epaisseurs": "épaisseurs",
    "episode": "épisode",
    "episodes": "épisodes",
    "etat": "état",
    "fige": "figé",
    "melange": "mélange",
    "mesuree": "mesurée",
    "modele": "modèle",
    "operateur": "opérateur",
    "periode": "période",
    "preventif": "préventif",
    "qualite": "qualité",
    "reduction": "réduction",
    "reference": "référence",
    "regle": "règle",
    "regulation": "régulation",
    "severite": "sévérité",
    "specification": "spécification",
    "surveillee": "surveillée",
    "systeme": "système",
    "tache": "tâche",
    "temperature": "température",
    "verification": "vérification",
}

_MOTIF = re.compile(
    r"\b(" + "|".join(sorted(MOTS_A_ACCENTUER, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def fautes(texte: str) -> list[str]:
    """Mots devant porter un accent et n'en portant pas.

    Args:
        texte: Chaine destinee a l'exploitant.

    Returns:
        Liste des formes fautives trouvees, avec leur correction.
    """
    return [
        f"{m.group(0)} -> {MOTS_A_ACCENTUER[m.group(0).lower()]}"
        for m in _MOTIF.finditer(texte)
    ]


def _exiger(textes: dict[str, str], minimum: int = 3) -> None:
    """Echoue en nommant chaque texte fautif et sa correction.

    LE CORPUS EST EXIGE NON VIDE, ET C'EST LE POINT IMPORTANT.

    Ces dix tests delegaient toute leur assertion a cette fonction. Si le
    dictionnaire arrivait vide — champ renomme dans l'AMDEC, cle disparue d'un
    rapport, `notable_timestamps` ne retournant rien — `problemes` etait vide
    lui aussi et le test PASSAIT en n'ayant rien inspecte. Un controle qui
    reussit d'autant plus surement qu'il ne lit rien ne controle rien : c'est
    exactement le defaut corrige dans `_causality_audit`, ici sous une autre
    forme.

    Args:
        textes: Textes a verifier, indexes par origine lisible.
        minimum: Nombre minimal de textes non vides attendus.

    Raises:
        AssertionError: Corpus insuffisant, ou texte sans accents.
    """
    peuples = {origine: texte for origine, texte in textes.items() if texte}
    assert len(peuples) >= minimum, (
        f"corpus typographique insuffisant : {len(peuples)} texte(s) non vide(s) "
        f"pour un minimum de {minimum}. Le controle ne verifie rien — une cle "
        f"a probablement ete renommee en amont."
    )
    problemes = {
        origine: fautes(texte)
        for origine, texte in peuples.items()
        if fautes(texte)
    }
    assert not problemes, "Textes affichés sans accents :\n" + "\n".join(
        f"  {origine} : {', '.join(mots)}" for origine, mots in problemes.items()
    )


# ── Referentiel metier ────────────────────────────────────────────────────────

# Notation anglaise d'un nombre decimal : « 1.7 », « 98.36 ». Le motif est
# defini ici parce que DEUX tests s'en servent — les diagnostics nominaux et
# les rapports de gouvernance — et qu'il n'appartient a aucun des deux.
_NOMBRE_ANGLAIS = re.compile(r"(?<![\w.])\d+\.\d+(?![\w.])")


def test_le_referentiel_amdec_affiche_est_accentue():
    """Les champs normalises par le projet portent leurs accents.

    Les blocs `original_values` sont exclus : ils reproduisent la cotation OCP
    de 2019 telle qu'elle figure dans le fichier source, et leur fidelite prime
    sur leur typographie.
    """
    doc = yaml.safe_load(AMDEC_PATH.read_text(encoding="utf-8"))
    textes: dict[str, str] = {}
    for code, mode in (doc.get("modes") or {}).items():
        for champ in ("element", "mode", "cause", "effet", "action_corrective"):
            valeur = mode.get(champ)
            if isinstance(valeur, str):
                textes[f"AMDEC {code}.{champ}"] = valeur
    _exiger(textes)


def test_le_plan_preventif_affiche_est_accentue():
    doc = yaml.safe_load(AMDEC_PATH.read_text(encoding="utf-8"))
    textes = {
        f"plan {ref}.{champ}": tache[champ]
        for ref, tache in (doc.get("plan_maintenance") or {}).items()
        for champ in ("tache", "etat")
        if isinstance(tache.get(champ), str)
    }
    _exiger(textes)


# ── Sorties du systeme ────────────────────────────────────────────────────────

def test_les_indicateurs_affiches_sont_accentues(pipeline):
    """Libelles et lectures des cartes de l'onglet Intégrité."""
    kpi = OperationalKPI(pipeline.features, pipeline.domain)
    figures = kpi.summary(pipeline.ingestion.sensor_health, pipeline.episodes())
    textes: dict[str, str] = {}
    for figure in figures:
        textes[f"KPI « {figure.label} » (libellé)"] = figure.label
        textes[f"KPI « {figure.label} » (lecture)"] = figure.note
    _exiger(textes)


def test_les_messages_de_detection_sont_accentues(pipeline):
    """Tout ce qui atterrit dans le journal du rejeu et la carte de diagnostic."""
    textes: dict[str, str] = {}
    for ts in pipeline.notable_timestamps(12):
        analysis = pipeline.analyze_at(ts, use_llm=False)
        for finding in analysis.detection.findings:
            textes[f"{ts} / {finding.code}"] = finding.message
        decision = analysis.decision
        textes[f"{ts} / diagnostic"] = decision.diagnosis
        textes[f"{ts} / raisonnement"] = decision.reasoning
        textes[f"{ts} / action"] = decision.recommended_action.description
    _exiger(textes)


def test_les_diagnostics_nominaux_sont_rediges_en_francais(pipeline):
    """La formulation la plus fréquente du système n'était contrôlée nulle part.

    `test_les_messages_de_detection_sont_accentues` échantillonne
    `notable_timestamps`, c'est-à-dire les instants qui portent une
    constatation. Or la branche nominale de `_nominal_decision` ne s'exécute
    QUE lorsqu'il n'y en a aucune : la population testée était exactement le
    complémentaire de celle qui peut déclencher le défaut.

    `_quote_measurements` y rendait « entree acide 94.23 degC, sortie acide
    65.91 degC, debit acide 56.40 m3/h » — sans accents, unités en ASCII,
    point décimal anglais. Sur ce corpus, l'immense majorité des heures de
    marche établie sont nominales : c'est la phrase que l'exploitant voit le
    plus souvent.
    """
    running = pipeline.features.index[
        pipeline.features["process_state"].eq("RUNNING")
    ]
    textes: dict[str, str] = {}
    for ts in running[:: max(1, len(running) // 40)]:
        decision = pipeline.analyze_at(ts, use_llm=False).decision
        if decision.severity not in ("NORMAL", "INFO"):
            continue
        textes[f"{ts} / diagnostic nominal"] = decision.diagnosis
        textes[f"{ts} / raisonnement nominal"] = decision.reasoning
        if len(textes) >= 16:
            break

    assert textes, (
        "aucun instant nominal trouvé : ce test ne prouve plus rien, "
        "la sélection a dérivé"
    )
    _exiger(textes)
    fautifs = {
        origine: _NOMBRE_ANGLAIS.findall(texte)
        for origine, texte in textes.items()
        if _NOMBRE_ANGLAIS.search(texte)
    }
    assert not fautifs, "Point décimal anglais dans un diagnostic nominal :\n" + "\n".join(
        f"  {origine} : {', '.join(n)}" for origine, n in fautifs.items()
    )


def test_les_controles_du_juge_sont_accentues(pipeline):
    """Les huit contrôles sont affichés tels quels sur l'onglet Contrôle."""
    textes: dict[str, str] = {}
    for ts in pipeline.notable_timestamps(6):
        verdict = pipeline.analyze_at(ts, use_llm=False).verdict
        for check in verdict.checks:
            textes[f"{ts} / {check.id} (libellé)"] = check.label
            textes[f"{ts} / {check.id} (détail)"] = check.detail
        textes[f"{ts} / synthèse"] = verdict.feedback
    _exiger(textes)

    # TROISIÈME SURFACE DU MÊME DÉFAUT (voir S4-2 de l'audit).
    # Les détails du contrôleur citaient « 0.85 annonce contre 0.70 » et
    # « annonce 66.3, mesure 66.1 ». C'est le texte que l'exploitant lit dans
    # l'encart « Réserves du contrôleur » — le seul endroit où une anomalie de
    # calibration lui est présentée.
    fautifs = {
        origine: _NOMBRE_ANGLAIS.findall(texte)
        for origine, texte in textes.items()
        if _NOMBRE_ANGLAIS.search(texte)
    }
    assert not fautifs, "Point décimal anglais dans un contrôle du Judge :\n" + "\n".join(
        f"  {origine} : {', '.join(n)}" for origine, n in fautifs.items()
    )


# ── Rapports de gouvernance ───────────────────────────────────────────────────
#
# LA SURFACE QUI AVAIT ECHAPPE AU CONTROLE.
# Les trois tests ci-dessus couvraient les messages de detection, les
# indicateurs et le referentiel. Les RAPPORTS de gouvernance — banc
# d'encrassement, analyse de sensibilite, backtest, canal d'escalade — n'etaient
# verifies par personne, et continuaient d'afficher « Le banc valide qu'un
# encrassement CONFORME AU MODELE D'INJECTION serait detecte » en pleine page
# Controle. Ces textes sont pourtant ceux qu'un jury lit le plus attentivement,
# puisque ce sont eux qui enoncent les limites du projet.

def _textes_du_rapport(rapport: object, chemin: str = "") -> dict[str, str]:
    """Parcourt un rapport serialisable et en extrait les chaines lisibles.

    Les identifiants techniques — codes de portes, noms de colonnes, chemins de
    fichiers, horodatages — sont ecartes : ils ne sont pas du francais et n'ont
    pas a porter d'accents.

    Args:
        rapport: Dictionnaire ou liste issu d'un `to_dict()` de gouvernance.
        chemin: Chemin courant, pour nommer la faute.

    Returns:
        Chemin -> texte destine a la lecture.
    """
    ignore = {"gate", "source", "source_file", "start", "end", "period",
              "detected_at", "fin_reference", "train_period", "sha256",
              "timestamp", "features", "pipeline_refit_per_fold", "nom"}
    out: dict[str, str] = {}
    if isinstance(rapport, dict):
        for cle, valeur in rapport.items():
            if cle in ignore:
                continue
            out |= _textes_du_rapport(valeur, f"{chemin}.{cle}")
    elif isinstance(rapport, list):
        for i, valeur in enumerate(rapport):
            out |= _textes_du_rapport(valeur, f"{chemin}[{i}]")
    elif isinstance(rapport, str) and " " in rapport.strip():
        # Une chaine sans espace est un identifiant, pas une phrase.
        out[chemin.lstrip(".")] = rapport
    return out


def test_le_banc_d_encrassement_est_redige_en_francais(fouling_bench_report):
    """Méthode, lecture et limites du banc sont affichées intégralement."""
    _exiger(_textes_du_rapport(fouling_bench_report.to_dict(), "banc"))


def test_l_analyse_de_sensibilite_est_redigee_en_francais(sensitivity_report):
    """C'est le texte le plus lu de la page Contrôle : il porte les limites."""
    _exiger(_textes_du_rapport(sensitivity_report, "sensibilité"))


def test_le_backtest_est_redige_en_francais(pipeline):
    """Portes de déploiement, preuves et limites déclarées."""
    _exiger(_textes_du_rapport(pipeline.validation_report(), "backtest"))


@pytest.mark.parametrize("relais", [None, "smtp.interne.test"])
def test_le_canal_d_escalade_est_redige_en_francais(relais):
    """Le motif d'inactivité s'affiche en clair sur la page Contrôle.

    Les deux causes d'inactivité sont couvertes : relais SMTP absent, et relais
    présent mais aucune session ouverte. Chacune produit son propre texte.
    """
    from src.notifications import EmailNotifier

    notifier = EmailNotifier(
        host=relais, port=587, username=None, password=None,
        sender="poste-e7301@interne.test" if relais else None,
        recipient=None, starttls=True,
        cooldown_minutes=60.0, minimum_severity="CRITICAL",
    )
    # Minimum abaisse a 2, et c'est justifie : `status()` n'expose que DEUX
    # champs de texte libre — `reason` et `retry_policy`. Les autres chaines
    # (`mode`, `minimum_severity`) sont des codes d'un seul mot, ecartes par
    # `_textes_du_rapport` qui ne retient que les chaines contenant un espace.
    # Exiger trois textes ici ferait echouer un controle sain.
    _exiger(_textes_du_rapport(notifier.status(), "escalade"), minimum=2)


def test_aucun_point_decimal_dans_les_textes_affiches(pipeline, sensitivity_report):
    """Une interface française n'écrit pas « 1.7 °C » ni « 2.8 fois ».

    Python formate en notation anglaise, et chaque f-string réintroduisait le
    point décimal. `src.formatting` centralise la conversion; ce test vérifie
    qu'aucune sortie n'y échappe.

    Les identifiants de version, les chemins et les horodatages sont écartés
    par `_textes_du_rapport`.
    """
    from src.analytics import OperationalKPI

    textes: dict[str, str] = {}
    kpi = OperationalKPI(pipeline.features, pipeline.domain)
    for figure in kpi.summary(pipeline.ingestion.sensor_health, pipeline.episodes()):
        textes[f"KPI « {figure.label} »"] = figure.note
    textes |= _textes_du_rapport(sensitivity_report, "sensibilité")
    textes |= _textes_du_rapport(pipeline.validation_report(), "backtest")

    # LA SURFACE QUE CE TEST NE REGARDAIT PAS, ET C'EST LA PLUS GRANDE.
    #
    # Deux tests se partagent la typographie, et chacun couvrait la moitié du
    # problème sur une population différente :
    #
    #   `test_les_messages_de_detection_sont_accentues` regarde bien les
    #   constatations et les diagnostics — mais ne cherche que des accents.
    #
    #   celui-ci cherche bien le point décimal — mais n'échantillonnait que
    #   les indicateurs, la sensibilité et le backtest, jamais une
    #   constatation.
    #
    # L'intersection était vide, et tout le moteur de règles écrivait
    # « 66.3 °C » dans le journal du rejeu, la carte de diagnostic, le
    # registre d'alarmes et les courriels d'escalade.
    for ts in pipeline.notable_timestamps(12):
        analysis = pipeline.analyze_at(ts, use_llm=False)
        for finding in analysis.detection.findings:
            textes[f"{ts} / {finding.code}"] = finding.message
        textes[f"{ts} / diagnostic"] = analysis.decision.diagnosis
        textes[f"{ts} / raisonnement"] = analysis.decision.reasoning
        textes[f"{ts} / action"] = analysis.decision.recommended_action.description

    fautifs = {
        origine: _NOMBRE_ANGLAIS.findall(texte)
        for origine, texte in textes.items()
        if _NOMBRE_ANGLAIS.search(texte)
    }
    assert not fautifs, "Point décimal anglais dans un texte affiché :\n" + "\n".join(
        f"  {origine} : {', '.join(n)}" for origine, n in fautifs.items()
    )


# ── Garde-fou du test lui-meme ────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("Temperature de sortie acide", True),
        ("Température de sortie acide", False),
        ("Le systeme n'a rien detecte", True),
        ("Le système n'a rien détecté", False),
        ("UA, NTU et Isolation Forest", False),
    ],
)
def test_le_detecteur_de_fautes_fonctionne(texte, attendu):
    """Un controle qui ne detecte rien ne controle rien : on le verifie."""
    assert bool(fautes(texte)) is attendu


# ── Perimetre : les chaines qu'aucune reponse nominale ne contient ────────────
#
# J-2 ELARGI, VOLET « PERIMETRE ». Les onze controles ci-dessus inspectent des
# SORTIES D'EXECUTION : ils ne voient une chaine que si un appel la produit.
# Quatre surfaces echappaient donc structurellement au controle, et la phase 0.9
# les avait recensees sans les fermer : le diagnostic nominal (A-1, ferme
# depuis), les libelles du controleur (J-2), les trois scripts en ligne de
# commande (SCR-1), et le corps du courriel de test.
#
# Les messages de REFUS d'`api/main.py` sont de cette famille, et c'est la plus
# visible : un `detail` de 401, 403, 404 ou 422 n'apparait dans aucune reponse
# nominale, donc dans aucun corpus de test typographique — alors que c'est
# exactement ce qu'un exploitant lit quand quelque chose ne va pas. La
# description OpenAPI est du meme ordre : elle ne sort dans aucune reponse
# metier, et c'est la premiere page qu'un jury ouvre sur `/docs`.
#
# Ce controle-ci lit donc le SOURCE, pas une sortie. C'est le patron du depot,
# applique a la typographie.

_MODULES_A_TEXTE = ("api/main.py",)


def _litteraux_lisibles(chemin) -> dict[str, str]:
    """Chaines de `chemin` destinees a un humain, avec leur ligne.

    Trois familles sont ECARTEES, et chacune pour une raison qui lui est propre :

      - les DOCSTRINGS et commentaires : l'en-tete de ce fichier les exclut
        explicitement depuis l'origine, ils s'adressent au relecteur ;
      - les arguments de `logger.*` : le journal serveur n'est pas une surface
        d'exploitation, et l'accentuer n'ajoute rien a ce qu'un exploitant lit ;
      - les chaines de plus de 400 caracteres : ce sont les PROMPTS des agents.
        Les accentuer modifierait l'entree d'un modele de langage, donc son
        comportement — c'est une modification de fond deguisee en correction de
        forme. Meme raison pour `knowledge.briefing_*`, dont la docstring dit
        « injectee dans les prompts des agents » : verifie, ces chaines ne sont
        affichees nulle part.

    Args:
        chemin: Chemin du module a lire.

    Returns:
        `fichier:ligne` -> chaine lisible.
    """
    import ast

    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    ecartes: set[int] = set()
    for noeud in ast.walk(arbre):
        if isinstance(
            noeud, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            corps = noeud.body
            if (
                corps
                and isinstance(corps[0], ast.Expr)
                and isinstance(corps[0].value, ast.Constant)
                and isinstance(corps[0].value.value, str)
            ):
                ecartes.add(id(corps[0].value))
        if isinstance(noeud, ast.Call):
            fonction = noeud.func
            base = getattr(getattr(fonction, "value", None), "id", "")
            nom = getattr(fonction, "attr", None)
            if base in {"logger", "logging"} or nom in {
                "debug", "info", "warning", "error", "exception", "critical",
            }:
                for sous in ast.walk(noeud):
                    if isinstance(sous, ast.Constant) and isinstance(sous.value, str):
                        ecartes.add(id(sous))

    sql = re.compile(r"\b(SELECT|INSERT|UPDATE|CREATE|DELETE|PRAGMA|FROM|WHERE)\b")
    out: dict[str, str] = {}
    for noeud in ast.walk(arbre):
        if not (isinstance(noeud, ast.Constant) and isinstance(noeud.value, str)):
            continue
        if id(noeud) in ecartes:
            continue
        valeur = noeud.value
        if " " not in valeur.strip() or not 12 <= len(valeur) <= 400:
            continue
        if sql.search(valeur):
            continue
        out[f"{chemin.name}:{noeud.lineno}"] = valeur
    return out


def test_les_textes_de_refus_de_l_api_sont_accentues():
    """Un message d'erreur est la phrase qu'on lit quand rien ne va.

    Aucun test de ce fichier ne pouvait l'atteindre : un `detail` de 401, 403,
    404 ou 422 n'apparaît dans aucune réponse nominale. « Authentification
    operateur requise », « Severite hors plage », « Severites illisibles » et
    la description OpenAPI — la première page qu'un jury ouvre — sont restées
    sans accents pour cette seule raison.
    """
    from pathlib import Path

    racine = Path(__file__).resolve().parents[1]
    textes: dict[str, str] = {}
    for relatif in _MODULES_A_TEXTE:
        textes |= _litteraux_lisibles(racine / relatif)
    _exiger(textes, minimum=20)
