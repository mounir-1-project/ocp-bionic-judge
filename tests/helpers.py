"""
Outils partages par la suite de tests.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import unicodedata


def sans_accents(texte: str) -> str:
    """Retire accents et casse, pour comparer un FOND et non une typographie.

    Un test qui verifie qu'un message parle bien du coefficient d'echange doit
    continuer de passer quand ce message gagne ses accents. Sans cette
    normalisation, corriger la typographie casserait les tests, et l'equipe
    apprendrait a ne plus la corriger.

    Args:
        texte: Chaine quelconque.

    Returns:
        La meme chaine, sans diacritiques et en minuscules.
    """
    decompose = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in decompose if not unicodedata.combining(c)).casefold()
