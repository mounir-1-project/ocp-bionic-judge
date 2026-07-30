"""
Promotion gouvernée d'un artefact modèle E7301.

POURQUOI CE SCRIPT EXISTE
----------------------------------------------------------------------------
`build_manifest` écrit toujours le statut `candidate` et laisse `promoted_by`
et `promoted_at_utc` à `None` — c'est voulu : produire un artefact n'est pas
le promouvoir. Mais `validate_model_manifest` exige ces deux champs pour
autoriser le chargement au runtime, et AUCUN code du dépôt ne pouvait les
renseigner. Le circuit de promotion était donc déclaré, documenté dans le
manifeste sous `promotion.process = "manual_governed_promotion"`, et
inexécutable : aucun artefact n'était chargeable par aucun chemin.

Ce script ferme le circuit. Il refuse de promouvoir tant qu'une porte de
déploiement obligatoire est en échec, et exige une identité de promoteur :
une promotion sans auteur n'est pas une décision de gouvernance.

CE QU'IL NE FAIT PAS
----------------------------------------------------------------------------
Il ne contourne aucune porte. Sur le corpus actuel, `labels_gmao` et
`validation_externe` sont en échec définitif faute d'historique de pannes
étiquetées : la promotion est donc légitimement impossible, et le script le
dit avec la liste des portes bloquantes. C'est le résultat correct, pas une
panne du script.

Usage :
    python scripts/promote_model.py --statut shadow_only --par "prenom.nom@ocpgroup.ma"
    python scripts/promote_model.py --etat        # lit l'état sans rien modifier

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import MODEL_DIR
from src.governance.lineage import (
    RUNTIME_STATUSES,
    failed_mandatory_gates,
    sha256_file,
    write_manifest,
)

UTC = timezone.utc
MANIFESTE = MODEL_DIR / "e7301_detector.manifest.json"
MODELE = MODEL_DIR / "e7301_detector.joblib"


def _charger(chemin: Path) -> dict:
    """Lit le manifeste, ou échoue avec un message exploitable.

    Args:
        chemin: Emplacement du manifeste.

    Returns:
        Le manifeste décodé.

    Raises:
        SystemExit: Si le fichier est absent ou illisible.
    """
    if not chemin.exists():
        raise SystemExit(
            f"Manifeste introuvable : {chemin}\n"
            f"Produire d'abord un artefact candidat : make release"
        )
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Manifeste illisible : {chemin} ({exc})") from exc


def etat(manifeste: dict) -> int:
    """Affiche l'état de promotion sans rien modifier.

    Args:
        manifeste: Manifeste chargé.

    Returns:
        0 si l'artefact est promu, 1 sinon.
    """
    promotion = manifeste.get("promotion", {})
    bloquantes = failed_mandatory_gates(manifeste.get("validation", {}).get("results", {}))
    print(f"identifiant     : {manifeste['model_identity']['id']}")
    print(f"version         : {manifeste['model_identity']['version']}")
    print(f"statut          : {promotion.get('status')}")
    print(f"promu par       : {promotion.get('promoted_by') or '—'}")
    print(f"promu le        : {promotion.get('promoted_at_utc') or '—'}")
    print(f"runtime Python  : {manifeste['runtime']['python']}")
    print(
        "portes en echec : "
        + (", ".join(bloquantes) if bloquantes else "aucune")
    )
    if bloquantes:
        print(
            "\nLa promotion est IMPOSSIBLE tant que ces portes sont en echec.\n"
            "Sur ce corpus, `labels_gmao` et `validation_externe` le sont\n"
            "definitivement : aucun historique de pannes etiquetees n'existe.\n"
            "C'est le resultat attendu, pas un dysfonctionnement."
        )
    return 0 if promotion.get("status") in RUNTIME_STATUSES else 1


def promouvoir(manifeste: dict, statut: str, par: str, chemin: Path) -> int:
    """Applique la promotion après vérification des portes et des empreintes.

    Args:
        manifeste: Manifeste chargé.
        statut: Statut de promotion visé.
        par: Identité du promoteur.
        chemin: Emplacement du manifeste à réécrire.

    Returns:
        0 si la promotion a eu lieu, 2 sinon.
    """
    if statut not in RUNTIME_STATUSES:
        print(
            f"Statut '{statut}' non executable au runtime. "
            f"Valeurs admises : {', '.join(sorted(RUNTIME_STATUSES))}",
            file=sys.stderr,
        )
        return 2

    bloquantes = failed_mandatory_gates(manifeste.get("validation", {}).get("results", {}))
    if bloquantes:
        print(
            "PROMOTION REFUSEE — portes obligatoires en echec : "
            + ", ".join(bloquantes),
            file=sys.stderr,
        )
        return 2

    if not MODELE.exists():
        print(f"PROMOTION REFUSEE — artefact absent : {MODELE}", file=sys.stderr)
        return 2
    empreinte = sha256_file(MODELE)
    if empreinte != manifeste["model"]["sha256"]:
        print(
            "PROMOTION REFUSEE — l'artefact ne correspond pas a son manifeste.\n"
            f"  manifeste : {manifeste['model']['sha256']}\n"
            f"  fichier   : {empreinte}",
            file=sys.stderr,
        )
        return 2

    manifeste["promotion"].update(
        status=statut,
        promoted_by=par.strip(),
        promoted_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    write_manifest(manifeste, chemin)
    print(f"Artefact promu '{statut}' par {par.strip()} — manifeste reecrit : {chemin}")
    return 0


def main() -> int:
    """Point d'entrée."""
    analyseur = argparse.ArgumentParser(
        description="Promotion gouvernee d'un artefact modele E7301.",
    )
    analyseur.add_argument(
        "--etat", action="store_true", help="affiche l'etat sans rien modifier"
    )
    analyseur.add_argument(
        "--statut",
        choices=sorted(RUNTIME_STATUSES),
        help="statut de promotion vise",
    )
    analyseur.add_argument(
        "--par", help="identite du promoteur (adresse professionnelle)"
    )
    analyseur.add_argument(
        "--manifeste", type=Path, default=MANIFESTE, help="emplacement du manifeste"
    )
    args = analyseur.parse_args()

    manifeste = _charger(args.manifeste)
    if args.etat or not args.statut:
        return etat(manifeste)
    if not args.par:
        print(
            "--par est obligatoire : une promotion sans auteur n'est pas "
            "une decision de gouvernance.",
            file=sys.stderr,
        )
        return 2
    return promouvoir(manifeste, args.statut, args.par, args.manifeste)


if __name__ == "__main__":
    raise SystemExit(main())
