"""
Mise en forme des nombres destines a la lecture humaine.

POURQUOI CE MODULE EXISTE
----------------------------------------------------------------------------
Le poste affichait « 1.7 °C sous la consigne », « 2.8 fois la contamination »,
« PSI max 4.113 », « (0.02%) ». Python formate en notation anglaise, et chaque
chaine construite avec une f-string reintroduisait le point decimal dans une
interface entierement francaise.

Corriger les occurrences une par une ne tient pas : la suivante reviendra. La
conversion est donc centralisee ici, et un test parcourt les sorties du systeme
pour verifier qu'aucun nombre n'echappe a la regle.

CONVENTIONS RETENUES
----------------------------------------------------------------------------
  - virgule decimale
  - espace insecable etroite comme separateur de milliers, conforme a l'usage
    typographique francais (10 182 horodatages)
  - espace insecable avant %, °C et les unites, pour qu'un retour a la ligne ne
    separe jamais un nombre de son unite

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import unicodedata

# Espace insecable etroite (U+202F) : le separateur de milliers francais.
# Espace insecable ordinaire (U+00A0) : entre un nombre et son unite.
FINE = " "
NBSP = " "


def sans_accents(texte: str) -> str:
    """Retire accents et casse, pour comparer un FOND et non une typographie.

    POURQUOI CETTE FONCTION VIT DANS `src/` ET NON DANS LES TESTS.
    Elle n'existait que cote tests, et un controle du Judge a ete
    silencieusement desactive faute d'y avoir acces. Le controle V8 verifie
    qu'un diagnostic enonce ses limites en cherchant des mots-cles —
    « reserve », « defaut », « degrade » — dans le texte produit. Lorsque tous
    ces textes ont ete correctement accentues, cinq des douze cles sont
    devenues introuvables : V8 a echoue sur 100 % des heures hors marche, et
    l'exploitant a recu « limite non enoncee » sur des diagnostics qui
    enoncaient precisement leur limite.

    Toute comparaison de FOND portant sur du texte francais passe desormais
    par ici, cote code comme cote tests.

    Args:
        texte: Chaine quelconque.

    Returns:
        La meme chaine, sans diacritiques et en minuscules.

    Examples:
        >>> sans_accents("Réserve : mesure dégradée")
        'reserve : mesure degradee'
    """
    decompose = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in decompose if not unicodedata.combining(c)).casefold()


def nombre(valeur: float | int | None, decimales: int = 1) -> str:
    """Formate un nombre a la francaise.

    Args:
        valeur: Nombre a formater. `None` et NaN donnent un tiret cadratin.
        decimales: Nombre de decimales conservees.

    Returns:
        Chaine formatee, virgule decimale et milliers separes.

    Examples:
        >>> nombre(1.7)
        '1,7'
        >>> nombre(10182, 0)
        '10\\u202f182'
        >>> nombre(None)
        '—'
    """
    if valeur is None:
        return "—"
    try:
        x = float(valeur)
    except (TypeError, ValueError):
        return "—"
    if x != x:  # NaN
        return "—"
    brut = f"{x:,.{decimales}f}"
    return brut.replace(",", FINE).replace(".", ",")


def pourcent(valeur: float | None, decimales: int = 1) -> str:
    """Formate un pourcentage, unite comprise et non secable.

    Args:
        valeur: Valeur deja exprimee en pourcent (12.8 pour 12,8 %).
        decimales: Nombre de decimales conservees.

    Returns:
        Par exemple `'12,8 %'`, l'espace etant insecable.
    """
    return f"{nombre(valeur, decimales)}{NBSP}%"


def unite(valeur: float | None, symbole: str, decimales: int = 1) -> str:
    """Formate une grandeur avec son unite, sans cesure possible.

    Args:
        valeur: Grandeur mesuree.
        symbole: Unite, par exemple `'°C'` ou `'kW/K'`.
        decimales: Nombre de decimales conservees.

    Returns:
        Par exemple `'17,8 kW/K'`.
    """
    return f"{nombre(valeur, decimales)}{NBSP}{symbole}"


def heures(valeur: float | int | None) -> str:
    """Formate une duree en heures, avec separateur de milliers.

    Args:
        valeur: Nombre d'heures.

    Returns:
        Par exemple `'8\\u202f795 h'`.
    """
    return f"{nombre(valeur, 0)}{NBSP}h"


def duree_pas(delta: object) -> str:
    """Traduit un pas d'echantillonnage en formulation lisible.

    Le pas nominal transite sous forme de `Timedelta` pandas serialise, dont la
    representation textuelle est `'0 days 01:00:00'`. Affichee telle quelle sur
    le passeport de la donnee, elle trahit un objet technique recopie sans
    relecture.

    Args:
        delta: Pas d'echantillonnage, `Timedelta` ou sa representation texte.

    Returns:
        Par exemple `'1 h'`, `'30 min'`, `'1 j'`.
    """
    import pandas as pd

    try:
        td = pd.Timedelta(delta)
    except (ValueError, TypeError):
        return str(delta)
    if td != td or td.total_seconds() <= 0:
        return "—"

    secondes = td.total_seconds()
    if secondes % 86400 == 0:
        return f"{int(secondes // 86400)}{NBSP}j"
    if secondes % 3600 == 0:
        return f"{int(secondes // 3600)}{NBSP}h"
    if secondes % 60 == 0:
        return f"{int(secondes // 60)}{NBSP}min"
    return f"{nombre(secondes, 0)}{NBSP}s"
