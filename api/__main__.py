"""
Point d'entrée du service E7301.

POURQUOI CE MODULE EXISTE
----------------------------------------------------------------------------
`API_HOST` et `API_PORT` étaient déclarés dans `src/config.py`, validés par
personne et lus par aucun module : les modifier n'avait aucun effet. Le
Dockerfile écrivait `--host 0.0.0.0 --port 8000` en dur, le README et le
runbook passaient leurs propres valeurs sur la ligne de commande. Trois
sources de vérité pour une même décision, dont la seule documentée comme
telle était inerte.

`src/config.py` énonce en tête que toute variable déclarée est utilisée, et
qu'une configuration qui ment sur ce qu'elle contrôle est pire qu'absente.
Ce module rend les deux variables effectives.

Usage :
    python -m api                      # honore API_HOST et API_PORT
    uvicorn api.main:app --port 8000   # reste possible, la ligne prime

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import sys

from loguru import logger

from src import config


def main() -> int:
    """Démarre le service en appliquant la configuration effective.

    Returns:
        0 si le serveur s'est arrêté normalement, 1 si la configuration
        est invalide.
    """
    problemes = config.validate()
    if problemes:
        # ECHOUER AU DEMARRAGE, PAS AU PREMIER APPEL.
        # Un chemin de donnees invalide ou un relais a moitie configure doit
        # arreter le lancement avec un message lisible, pas produire une trace
        # obscure trois minutes plus tard.
        for probleme in problemes:
            logger.error(f"Configuration invalide : {probleme}")
        return 1

    import uvicorn

    logger.info(
        f"Demarrage du service E7301 sur {config.API_HOST}:{config.API_PORT} "
        f"(profil {config.APP_ENV})"
    )
    uvicorn.run(
        "api.main:app",
        host=config.API_HOST,
        port=config.API_PORT,
        # UN SEUL WORKER, ET C'EST UNE DECISION.
        # La chaine charge l'historique complet et entraine le modele en
        # memoire au demarrage. Plusieurs workers dupliqueraient ce travail et
        # ce modele sans aucun gain : le service surveille UN equipement sur un
        # historique fini.
        workers=1,
        log_level=config.LOG_LEVEL.lower(),
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
