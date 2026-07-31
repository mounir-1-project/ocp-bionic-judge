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


def test_les_controles_du_juge_sont_accentues(pipeline):
    """Les huit contrôles sont affichés tels quels sur l'onglet Contrôle."""
    textes: dict[str, str] = {}
    for ts in pipeline.notable_timestamps(6):
        verdict = pipeline.analyze_at(ts, use_llm=False).verdict
        for check in verdict.checks:
            textes[f"{ts} / {check.id} (libellé)"] = check.label
            textes[f"{ts} / {check.id} (détail)"] = check.detail
    _exiger(textes)


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


# ── Notation des nombres ──────────────────────────────────────────────────────

_NOMBRE_ANGLAIS = re.compile(r"(?<![\w.])\d+\.\d+(?![\w.])")


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
