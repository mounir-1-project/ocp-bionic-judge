"""
Registre local des techniciens autorises.

POURQUOI CE REGISTRE EXISTE
----------------------------------------------------------------------------
La version precedente reposait sur UN mot de passe unique (`AUTH_PASSWORD_HASH`)
partage par toutes les adresses de l'allowlist. C'est un secret d'equipe : il
circule, il ne se revoque pas individuellement, et le journal d'audit ne peut
plus dire qui s'est reellement connecte.

Or l'adresse saisie a l'ouverture de session n'est pas decorative : elle devient
le DESTINATAIRE des alertes critiques. Une identite qui declenche l'envoi d'un
courriel d'intervention doit etre authentifiee individuellement.

Chaque technicien a donc son propre mot de passe, hache en PBKDF2-SHA256 avec
un sel distinct.

OU VIVENT LES SECRETS
----------------------------------------------------------------------------
Dans un fichier JSON place HORS DU DEPOT par defaut (`data/runtime/`, ignore par
git). Le depot ne contient aucun hash, aucun mot de passe, aucune adresse
reelle. Le fichier est cree avec des droits restreints la ou le systeme le
permet.

Ce registre est un mecanisme de DEMONSTRATION mono-poste. En exploitation OCP,
il doit ceder la place au fournisseur d'identite de l'entreprise : la
configuration `AUTH_PROVIDER=oidc` reste le chemin prevu, et le service refuse
de demarrer en mode production sans lui.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import contextlib
import json
import os
import stat
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.security.auth import EMAIL_PATTERN, VALID_ROLES, hash_password

UTC = timezone.utc

SCHEMA_VERSION = 1
MIN_PASSWORD_LENGTH = 12


@dataclass(frozen=True)
class Operator:
    """Un technicien habilite a ouvrir une session.

    Attributes:
        email: Adresse de connexion, qui recoit aussi les alertes critiques.
        name: Nom affiche sur le poste.
        role: Role applicatif (`VALID_ROLES`).
        password_hash: Empreinte PBKDF2-SHA256, jamais le mot de passe.
        created_at: Horodatage de creation.
        alert_recipient: Ce technicien doit-il recevoir les alertes critiques
            pendant sa session ? Vrai par defaut; un role de lecture seule peut
            legitimement ne pas vouloir etre reveille la nuit.
    """

    email: str
    name: str
    role: str
    password_hash: str
    created_at: str
    alert_recipient: bool = True

    def public(self) -> dict[str, Any]:
        """Vue sans secret, utilisable en journal ou en API."""
        return {
            "email": self.email,
            "name": self.name,
            "role": self.role,
            "created_at": self.created_at,
            "alert_recipient": self.alert_recipient,
        }


class OperatorRegistry:
    """Registre JSON des techniciens, protege par verrou.

    Attributes:
        path: Emplacement du fichier de registre.
    """

    def __init__(self, path: str | Path) -> None:
        """Ouvre (ou prepare) le registre.

        Args:
            path: Chemin du fichier JSON.
        """
        self.path = Path(path)
        self._lock = threading.Lock()
        self._operators: dict[str, Operator] = {}
        self.load()

    # ── Persistance ──────────────────────────────────────────────────────

    def load(self) -> None:
        """Recharge le registre depuis le disque.

        Un fichier absent n'est pas une erreur : cela signifie qu'aucun
        technicien n'est encore enregistre, et le service le dira clairement
        au demarrage plutot que d'echouer.
        """
        if not self.path.exists():
            with self._lock:
                self._operators = {}
            return
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(f"Registre illisible: {self.path} ({exc})") from exc

        # LE CHARGEMENT VALIDE CE QUE `add()` VALIDE. Il ne le faisait pas :
        # une entree editee a la main passait sans controle, et chaque champ
        # fautif etait absorbe silencieusement plus loin dans la chaine.
        #
        #   - un role inconnu ("admin" pour "administrator") etait accepte ici,
        #     puis ecarte par le filtre `VALID_ROLES` d'`AuthManager` : le
        #     technicien se retrouvait en `reader` sans qu'aucun message ne le
        #     dise. Une habilitation qui se degrade en silence est pire qu'une
        #     erreur au demarrage.
        #   - une empreinte vide laissait l'adresse dans l'allowlist alors
        #     qu'`AuthManager` retire les empreintes vides de `user_hashes`.
        #     L'authentification retombait donc sur `AUTH_PASSWORD_HASH` : ce
        #     compte devenait ouvrable avec le SECRET PARTAGE, precisement ce
        #     que le registre par technicien existe pour supprimer.
        #   - une adresse malformee etait ignoree par `continue`, sans trace :
        #     l'administrateur croyait le technicien enregistre.
        charges: dict[str, Operator] = {}
        for rang, entry in enumerate(doc.get("operators", []), start=1):
            email = str(entry.get("email", "")).strip().lower()
            if not EMAIL_PATTERN.fullmatch(email):
                raise ValueError(
                    f"{self.path} — entree {rang} : adresse invalide "
                    f"({entry.get('email')!r})"
                )
            role = str(entry.get("role", "reader"))
            if role not in VALID_ROLES:
                raise ValueError(
                    f"{self.path} — {email} : role inconnu {role!r}. "
                    f"Valeurs admises : {', '.join(sorted(VALID_ROLES))}"
                )
            password_hash = str(entry.get("password_hash", ""))
            if not password_hash.startswith("pbkdf2_sha256$"):
                raise ValueError(
                    f"{self.path} — {email} : empreinte absente ou non "
                    f"reconnue. Regenerer le mot de passe avec "
                    f"`python scripts/manage_operators.py set-password`."
                )
            if email in charges:
                raise ValueError(f"{self.path} — {email} : adresse en double")
            charges[email] = Operator(
                email=email,
                name=str(entry.get("name") or email.split("@", 1)[0]),
                role=role,
                password_hash=password_hash,
                created_at=str(entry.get("created_at", "")),
                alert_recipient=bool(entry.get("alert_recipient", True)),
            )
        # Publication ATOMIQUE. Les accesseurs de lecture ne prennent pas le
        # verrou; remplir le dictionnaire en place exposait un registre
        # partiellement charge a un rechargement concurrent.
        with self._lock:
            self._operators = charges

    def _save(self) -> None:
        """Ecrit le registre, en restreignant les droits quand c'est possible."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "note": (
                "Empreintes PBKDF2-SHA256 uniquement. Ce fichier ne doit jamais "
                "etre versionne ni transmis."
            ),
            "operators": [
                {
                    "email": op.email,
                    "name": op.name,
                    "role": op.role,
                    "password_hash": op.password_hash,
                    "created_at": op.created_at,
                    "alert_recipient": op.alert_recipient,
                }
                for op in sorted(self._operators.values(), key=lambda o: o.email)
            ],
        }
        # LES DROITS SONT POSES SUR LE FICHIER TEMPORAIRE, PAS SUR LA CIBLE.
        # Le code restreignait la cible APRES `replace()` : entre l'ecriture du
        # temporaire et le renommage, un fichier contenant toutes les
        # empreintes existait avec les droits par defaut du processus. La
        # fenetre etait courte, elle n'avait aucune raison d'exister.
        tmp = self.path.with_suffix(".tmp")
        contenu = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        descripteur = os.open(
            tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR
        )
        with os.fdopen(descripteur, "w", encoding="utf-8") as fichier:
            fichier.write(contenu)
            fichier.flush()
            # Sans `fsync`, `replace()` peut publier un fichier dont le contenu
            # n'est pas encore sur le disque : une coupure laisserait un
            # registre tronque, donc plus aucune connexion possible.
            os.fsync(fichier.fileno())
        tmp.replace(self.path)
        # Droits 600 : sans effet utile sous Windows, sans dommage non plus.
        with contextlib.suppress(OSError, NotImplementedError):
            os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)

    # ── Consultation ─────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._operators)

    @property
    def is_configured(self) -> bool:
        """Au moins un technicien peut-il ouvrir une session ?"""
        return bool(self._operators)

    def get(self, email: str) -> Operator | None:
        """Retourne un technicien par son adresse.

        Args:
            email: Adresse recherchee, insensible a la casse.

        Returns:
            L'Operator, ou None.
        """
        return self._operators.get(email.strip().lower())

    def emails(self) -> set[str]:
        """Adresses autorisees."""
        return set(self._operators)

    def roles(self) -> dict[str, str]:
        """Mapping adresse -> role."""
        return {email: op.role for email, op in self._operators.items()}

    def password_hashes(self) -> dict[str, str]:
        """Mapping adresse -> empreinte, pour l'authentification."""
        return {email: op.password_hash for email, op in self._operators.items()}

    def alert_recipients(self) -> set[str]:
        """Adresses devant recevoir les alertes critiques."""
        return {op.email for op in self._operators.values() if op.alert_recipient}

    def listing(self) -> list[dict[str, Any]]:
        """Vue sans secret de tous les techniciens."""
        return [op.public() for op in sorted(self._operators.values(), key=lambda o: o.email)]

    # ── Modification ─────────────────────────────────────────────────────

    def add(
        self,
        email: str,
        password: str,
        role: str = "maintenance",
        name: str | None = None,
        alert_recipient: bool = True,
    ) -> Operator:
        """Enregistre un technicien.

        Args:
            email: Adresse de connexion et de reception des alertes.
            password: Mot de passe en clair — hache immediatement, jamais stocke.
            role: Role applicatif.
            name: Nom affiche.
            alert_recipient: Recevoir les alertes critiques pendant la session.

        Returns:
            L'Operator cree.

        Raises:
            ValueError: Adresse invalide, role inconnu, mot de passe trop court,
                ou adresse deja enregistree.
        """
        normalized = email.strip().lower()
        if not EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError(f"Adresse invalide: {email}")
        if role not in VALID_ROLES:
            raise ValueError(
                f"Role inconnu: {role}. Valeurs admises: {', '.join(sorted(VALID_ROLES))}"
            )
        with self._lock:
            if normalized in self._operators:
                raise ValueError(f"{normalized} est deja enregistre")
            operator = Operator(
                email=normalized,
                name=(name or normalized.split("@", 1)[0]).strip(),
                role=role,
                password_hash=hash_password(password),  # leve si < 12 caracteres
                created_at=datetime.now(UTC).isoformat(timespec="seconds"),
                alert_recipient=alert_recipient,
            )
            self._operators[normalized] = operator
            self._save()
        return operator

    def set_password(self, email: str, password: str) -> None:
        """Remplace le mot de passe d'un technicien.

        Args:
            email: Adresse concernee.
            password: Nouveau mot de passe en clair.

        Raises:
            KeyError: Si l'adresse est inconnue.
        """
        normalized = email.strip().lower()
        with self._lock:
            current = self._operators.get(normalized)
            if current is None:
                raise KeyError(normalized)
            self._operators[normalized] = Operator(
                email=current.email,
                name=current.name,
                role=current.role,
                password_hash=hash_password(password),
                created_at=current.created_at,
                alert_recipient=current.alert_recipient,
            )
            self._save()

    def remove(self, email: str) -> None:
        """Retire un technicien.

        Args:
            email: Adresse a retirer.

        Raises:
            KeyError: Si l'adresse est inconnue.
        """
        normalized = email.strip().lower()
        with self._lock:
            if normalized not in self._operators:
                raise KeyError(normalized)
            del self._operators[normalized]
            self._save()


def load_registry(path: str | Path | None = None) -> OperatorRegistry:
    """Charge le registre a l'emplacement configure.

    Args:
        path: Emplacement explicite. Par defaut, `config.OPERATOR_REGISTRY`.

    Returns:
        Registre pret a l'emploi.
    """
    if path is None:
        from src import config

        path = config.OPERATOR_REGISTRY
    return OperatorRegistry(path)
