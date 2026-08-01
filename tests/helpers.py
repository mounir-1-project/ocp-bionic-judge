"""
Outils partages par la suite de tests.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

# FMT-2 — CETTE FONCTION EXISTAIT DEUX FOIS, LIGNE POUR LIGNE.
#
# `src/formatting.sans_accents` et la copie qui vivait ici portaient le meme
# corps — `NFKD`, filtrage des `combining`, `casefold` — et le meme argument :
# « corriger la typographie ne doit jamais casser le test qui protege le fond ».
#
# Deux exemplaires d'une regle de normalisation finissent par diverger, et le
# jour ou ils divergent c'est la suite de tests qui ment sur ce qu'elle compare.
# ADR-011 exige d'ailleurs que la mise en forme soit centralisee : le test ne
# peut pas s'en dispenser au motif qu'il est un test.
#
# On reexporte, on ne recopie pas. Les fichiers de tests continuent d'ecrire
# `from tests.helpers import sans_accents` sans rien changer.
from src.formatting import sans_accents

__all__ = ["sans_accents"]
