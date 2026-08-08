"""
Gestion des techniciens habilites a ouvrir une session sur le poste E7301.

L'adresse saisie a la connexion n'est pas decorative : elle devient le
DESTINATAIRE des alertes critiques. Elle doit donc etre authentifiee
individuellement, avec un mot de passe propre a chaque technicien.

Le mot de passe n'est JAMAIS accepte en argument de ligne de commande : il
apparaitrait dans l'historique du terminal et dans la liste des processus. Il
est saisi masque, et confirme.

Aucun secret n'est ecrit dans le depot. Le registre vit dans
`data/runtime/operators.json`, ignore par git.

Usage :
    python scripts/manage_operators.py add [email] [--role maintenance] [--name "Nom"]
    python scripts/manage_operators.py list
    python scripts/manage_operators.py passwd [email]
    python scripts/manage_operators.py remove [email]
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.security.auth import VALID_ROLES
from src.security.auth import MIN_PASSWORD_LENGTH
from src.security.registry import load_registry

ROLE_HELP = {
    "reader": "consultation seule",
    "operator": "conduite, peut piloter le rejeu",
    "maintenance": "intervention et checklists",
    "reliability_engineer": "fiabilite, acces aux bancs de gouvernance",
    "administrator": "administration, journal d'authentification",
}


def _ask_password(prompt: str = "Mot de passe") -> str:
    """Demande un mot de passe masque, avec confirmation.

    Args:
        prompt: Intitule affiche.

    Returns:
        Le mot de passe saisi.

    Raises:
        SystemExit: Si les deux saisies different ou si la longueur est
            insuffisante.
    """
    first = getpass.getpass(f"{prompt} ({MIN_PASSWORD_LENGTH} caractères minimum) : ")
    if len(first) < MIN_PASSWORD_LENGTH:
        raise SystemExit(
            f"Mot de passe trop court : {len(first)} caractère(s), "
            f"{MIN_PASSWORD_LENGTH} exigés."
        )
    second = getpass.getpass("Confirmer : ")
    if first != second:
        raise SystemExit("Les deux saisies different.")
    return first


def _ask(prompt: str, default: str = "") -> str:
    """Demande une valeur au clavier.

    Args:
        prompt: Intitule affiche.
        default: Valeur retenue si la saisie est vide.

    Returns:
        La valeur saisie ou la valeur par defaut.
    """
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix} : ").strip()
    return value or default


def cmd_add(args: argparse.Namespace) -> int:
    """Enregistre un technicien."""
    registry = load_registry(args.registry)
    email = args.email or _ask("Adresse du technicien")
    name = args.name or _ask("Nom affiche", email.split("@", 1)[0] if "@" in email else "")

    role = args.role
    if not role:
        print("\nRoles disponibles :")
        for key, description in ROLE_HELP.items():
            print(f"  {key:22s} {description}")
        role = _ask("\nRole", "maintenance")

    password = _ask_password()

    try:
        operator = registry.add(
            email=email,
            password=password,
            role=role,
            name=name,
            alert_recipient=not args.no_alerts,
        )
    except ValueError as exc:
        raise SystemExit(f"Enregistrement refuse : {exc}") from exc

    print(f"\nTechnicien enregistre : {operator.email} ({operator.role})")
    print(f"Registre : {registry.path}")
    if operator.alert_recipient:
        print(
            "Il recevra les alertes critiques pendant ses sessions, "
            "si le relais SMTP est configure."
        )
    print("\nL'acces protege s'active automatiquement au prochain demarrage.")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """Affiche les techniciens enregistres."""
    registry = load_registry(args.registry)
    if not registry.is_configured:
        print(f"Aucun technicien enregistre ({registry.path}).")
        print("Le poste demarrera SANS acces protege.")
        return 0

    print(f"{len(registry)} technicien(s) — {registry.path}\n")
    print(f"{'ADRESSE':38s} {'ROLE':22s} {'ALERTES':8s} CREE LE")
    for op in registry.listing():
        alerts = "oui" if op["alert_recipient"] else "non"
        print(
            f"{op['email']:38s} {op['role']:22s} {alerts:8s} {op['created_at'][:10]}"
        )
    return 0


def cmd_passwd(args: argparse.Namespace) -> int:
    """Change le mot de passe d'un technicien."""
    registry = load_registry(args.registry)
    email = args.email or _ask("Adresse du technicien")
    try:
        registry.set_password(email, _ask_password("Nouveau mot de passe"))
    except KeyError as exc:
        raise SystemExit(f"Adresse inconnue : {email}") from exc
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Mot de passe remplace pour {email.strip().lower()}.")
    print("Les sessions ouvertes restent valides jusqu'a leur expiration.")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    """Retire un technicien."""
    registry = load_registry(args.registry)
    email = (args.email or _ask("Adresse a retirer")).strip().lower()
    if registry.get(email) is None:
        raise SystemExit(f"Adresse inconnue : {email}")
    if not args.yes and _ask(f"Retirer {email} ? (oui/non)", "non").lower() != "oui":
        print("Annule.")
        return 1
    registry.remove(email)
    print(f"{email} retire.")
    if not registry.is_configured:
        print(
            "\nPlus aucun technicien enregistre : le poste demarrera sans acces "
            "protege au prochain lancement."
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construit l'analyseur d'arguments."""
    parser = argparse.ArgumentParser(
        prog="manage_operators",
        description=(
            "Gere les techniciens du poste E7301. Le mot de passe est toujours "
            "saisi masque, jamais passe en argument."
        ),
    )
    parser.add_argument(
        "--registry",
        default=None,
        help="Emplacement du registre (defaut : data/runtime/operators.json)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="enregistrer un technicien")
    add.add_argument("email", nargs="?", help="adresse de connexion et d'alerte")
    add.add_argument("--name", help="nom affiche sur le poste")
    add.add_argument("--role", choices=sorted(VALID_ROLES), help="role applicatif")
    add.add_argument(
        "--no-alerts",
        action="store_true",
        help="ne pas envoyer les alertes critiques a ce technicien",
    )
    add.set_defaults(func=cmd_add)

    listing = sub.add_parser("list", help="lister les techniciens")
    listing.set_defaults(func=cmd_list)

    passwd = sub.add_parser("passwd", help="changer un mot de passe")
    passwd.add_argument("email", nargs="?")
    passwd.set_defaults(func=cmd_passwd)

    remove = sub.add_parser("remove", help="retirer un technicien")
    remove.add_argument("email", nargs="?")
    remove.add_argument("--yes", action="store_true", help="ne pas demander confirmation")
    remove.set_defaults(func=cmd_remove)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Point d'entree."""
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
