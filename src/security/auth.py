"""Sessions serveur sobres pour un déploiement industriel mono-poste.

L'authentification est optionnelle. Lorsqu'elle est active, aucun secret ni
jeton n'est stocké dans le navigateur : le client ne reçoit qu'un cookie de
session HttpOnly opaque et un jeton CSRF distinct.
"""

from __future__ import annotations

import functools
import hashlib
import hmac
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, replace

PBKDF2_ITERATIONS = 600_000

# LONGUEUR MINIMALE — TROIS ECRITURES, ET LA MAUVAISE APPARTENANCE.
#
# La constante vivait dans `src.security.registry` sous le nom
# `MIN_PASSWORD_LENGTH`; `manage_operators.py` la lisait correctement. Mais
# `hash_password`, qui est le DERNIER verrou — `registry.add` et
# `registry.set_password` passent tous deux par elle — ecrivait `12` en dur,
# et son message une troisieme fois.
#
# La dependance interdisait d'ailleurs de faire autrement : `registry` importe
# `auth`, donc `auth` ne pouvait pas importer la constante de `registry` sans
# cycle. Le module qui APPLIQUE la regle ne possedait pas la valeur.
#
# Consequence mesurable : porter la politique a 14 caracteres dans `registry`
# aurait change ce que le script exige et ce que `add()` verifie, et
# `hash_password` aurait continue d'accepter 12. Une politique de mot de passe
# a moitie appliquee, sans que rien ne le signale. C'est le motif d'A-5 et de
# S8-2. La constante vit ici, `registry` la reexporte.
MIN_PASSWORD_LENGTH = 12

MAX_ATTEMPTS = 5
ATTEMPT_WINDOW_SECONDS = 300
EMAIL_PATTERN = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,63}$")
VALID_ROLES = {
    "reader", "operator", "maintenance", "reliability_engineer", "administrator"
}


class TooManyAttemptsError(PermissionError):
    """La fenêtre de limitation des tentatives est saturée."""


def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    """Produit une empreinte PBKDF2-SHA256 transportable dans `.env`."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"Le mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} "
            f"caractères"
        )
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Vérifie une empreinte PBKDF2 sans comparaison temporelle naïve."""
    try:
        algorithm, raw_iterations, raw_salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(raw_iterations)
        salt = bytes.fromhex(raw_salt)
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        ).hex()
        return hmac.compare_digest(candidate, expected)
    except (TypeError, ValueError):
        return False


@functools.lru_cache(maxsize=1)
def _decoy_hash() -> str:
    """Empreinte factice servant a egaliser le temps de reponse.

    Refuser immediatement une adresse inconnue reviendrait a annoncer, par le
    temps de reponse, quelles adresses sont enregistrees. On derive donc une
    empreinte quoi qu'il arrive. Calculee une seule fois, a la premiere
    tentative echouee, pour ne pas ralentir le demarrage.

    LE PRIX DE CE CHOIX, ECRIT PLUTOT QUE TU. La toute premiere tentative sur
    une adresse INCONNUE paie deux derivations — celle-ci, puis la comparaison
    — la ou une adresse connue n'en paie qu'une. L'egalisation que promet cette
    fonction est donc fausse exactement une fois par processus. Le
    prechauffement au demarrage supprimerait l'ecart au prix d'une demi-seconde
    de latence a l'ouverture du service, et d'une derivation PBKDF2 sur un
    poste qui, la plupart du temps, tourne sans authentification active. La
    fenetre est d'un unique essai et n'est pas rejouable : l'ecart est assume,
    pas ignore.
    """
    return hash_password(secrets.token_urlsafe(24))


@dataclass
class OperatorSession:
    """État serveur associé à un identifiant de session opaque."""

    username: str
    email: str
    role: str
    csrf_token: str
    created_at: float
    last_seen_at: float

    def public(self) -> dict[str, str]:
        """Vue sans secret utilisable par le frontend."""
        return {
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "csrf_token": self.csrf_token,
        }


class AuthManager:
    """Gestion en mémoire adaptée au service mono-worker documenté."""

    def __init__(
        self,
        # `None`, PAS LA CHAINE VIDE. Une chaine vide comme valeur par defaut
        # d'un parametre nomme `password_hash` fait echouer l'analyse de
        # securite du depot (bandit B107, mot de passe code en dur) : c'est la
        # derniere etape de l'integration continue, et elle etait rouge. Le
        # signalement est ici un faux positif, mais `None` dit mieux ce que le
        # code veut dire — aucune empreinte partagee n'est configuree — et
        # supprime la lecture ambigue d'une valeur vide.
        password_hash: str | None = None,
        idle_timeout_s: float = 1800,
        absolute_timeout_s: float = 28800,
        allowed_emails: set[str] | None = None,
        user_roles: dict[str, str] | None = None,
        user_hashes: dict[str, str] | None = None,
    ) -> None:
        """Initialise la gestion de session.

        Args:
            password_hash: Empreinte PARTAGEE, mode historique. `None` quand
                aucune n'est configuree. Conservee pour les deploiements
                existants, mais deconseillee : un secret d'equipe ne se revoque
                pas individuellement et le journal d'audit ne peut plus dire
                qui s'est connecte.
            idle_timeout_s: Expiration sur inactivite.
            absolute_timeout_s: Expiration absolue.
            allowed_emails: Adresses autorisees.
            user_roles: Role par adresse.
            user_hashes: Empreinte PAR TECHNICIEN. Mode recommande, et le seul
                acceptable des lors que l'adresse de session determine le
                destinataire des alertes critiques.
        """
        self.password_hash = password_hash or None
        self.idle_timeout_s = idle_timeout_s
        self.absolute_timeout_s = absolute_timeout_s
        self.user_hashes = {
            email.strip().lower(): value
            for email, value in (user_hashes or {}).items()
            if value
        }
        self.allowed_emails = {
            email.strip().lower() for email in (allowed_emails or set()) if email.strip()
        } or set(self.user_hashes)
        self.user_roles = {
            email.strip().lower(): role
            for email, role in (user_roles or {}).items()
            if role in VALID_ROLES
        }
        self._sessions: dict[str, OperatorSession] = {}
        self._attempts: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._audit: deque[dict[str, object]] = deque(maxlen=1000)

    def _purger(self, now: float) -> None:
        """Retire les compteurs de tentatives et les sessions perimes.

        DEUX STRUCTURES CROISSAIENT SANS LIMITE, TOUTES DEUX ALIMENTEES PAR
        UNE VALEUR QUE L'APPELANT CHOISIT.

        `_attempts` est un `defaultdict` indexe par adresse cliente : chaque
        adresse distincte y creait une entree, et seule une connexion REUSSIE
        la supprimait. Un balayage d'adresses laissait donc une file par
        adresse, definitivement.

        `_sessions` n'etait purge que lorsqu'un porteur revenait presenter son
        propre jeton expire. Une session ouverte puis abandonnee — la fin de
        quart, la fermeture du navigateur — n'etait jamais liberee.

        A appeler sous verrou.

        Args:
            now: Instant courant.
        """
        peremption = ATTEMPT_WINDOW_SECONDS
        for cle in [
            cle for cle, essais in self._attempts.items()
            if not essais or now - essais[-1] > peremption
        ]:
            del self._attempts[cle]
        for jeton in [
            jeton for jeton, session in self._sessions.items()
            if now - session.created_at > self.absolute_timeout_s
            or now - session.last_seen_at > self.idle_timeout_s
        ]:
            del self._sessions[jeton]

    def _record(self, event: str, email: str, client_key: str) -> None:
        self._audit.append({
            "timestamp": time.time(),
            "event": event,
            "email": email,
            "client_key": client_key,
        })

    def authenticate(
        self,
        email: str,
        password: str,
        client_key: str,
    ) -> tuple[str, OperatorSession] | None:
        """Authentifie l'email de quart et crée une session limitée."""
        now = time.time()
        # Normalisation remontee AVANT le verrou : le journal d'audit en a
        # besoin des la limitation de debit, voir `_record` ci-dessous.
        normalized_email = email.strip().lower()
        with self._lock:
            # LA TENTATIVE EST COMPTEE AVANT LA VERIFICATION, PAS APRES.
            #
            # Le compteur n'etait incremente qu'en cas d'echec, dans un SECOND
            # bloc verrouille, apres une derivation PBKDF2 de 600 000
            # iterations. Entre la lecture du compteur et son increment, toutes
            # les tentatives concurrentes voyaient la meme valeur : il suffisait
            # de lancer les requetes en parallele plutot qu'en serie pour que la
            # limite de cinq essais n'en arrete aucun.
            #
            # Compter d'abord ferme la fenetre. Le compteur est efface en cas de
            # succes, donc une session legitime ne paie rien.
            attempts = self._attempts[client_key]
            while attempts and now - attempts[0] > ATTEMPT_WINDOW_SECONDS:
                attempts.popleft()
            if len(attempts) >= MAX_ATTEMPTS:
                # L'ADRESSE VISEE ETAIT JETEE SUR LE SEUL EVENEMENT QUI LA
                # RECLAME. `LOGIN_RATE_LIMITED` etait consigne avec une chaine
                # vide : le journal d'authentification disait qu'une limite
                # avait ete atteinte, jamais CONTRE QUEL COMPTE. C'est le seul
                # evenement du journal qui signale une attaque en cours, et
                # c'est celui qui taisait sa cible — alors que la valeur etait
                # dans la portee. Rien ne la protegeait : les deux autres
                # evenements consignent deja l'adresse.
                self._record("LOGIN_RATE_LIMITED", normalized_email, client_key)
                raise TooManyAttemptsError("Trop de tentatives")
            attempts.append(now)
            self._purger(now)

        valid_user = bool(EMAIL_PATTERN.fullmatch(normalized_email))
        valid_user = valid_user and normalized_email in self.allowed_emails

        # Empreinte propre au technicien quand elle existe, empreinte partagee
        # sinon. La derivation PBKDF2 est menee DANS TOUS LES CAS, y compris
        # pour une adresse inconnue : sans cela, le temps de reponse indiquerait
        # a un attaquant quelles adresses sont enregistrees.
        expected = self.user_hashes.get(normalized_email) or self.password_hash
        valid_password = verify_password(password, expected or _decoy_hash())

        if not (valid_user and valid_password):
            with self._lock:
                self._record("LOGIN_FAILED", normalized_email, client_key)
            return None

        token = secrets.token_urlsafe(32)
        session = OperatorSession(
            username=normalized_email.split("@", 1)[0],
            email=normalized_email,
            role=self.user_roles.get(normalized_email, "reader"),
            csrf_token=secrets.token_urlsafe(24),
            created_at=now,
            last_seen_at=now,
        )
        with self._lock:
            self._attempts.pop(client_key, None)
            self._sessions[token] = session
            self._record("LOGIN_SUCCEEDED", normalized_email, client_key)
        return token, session

    def _valider_sous_verrou(self, token: str, now: float) -> OperatorSession | None:
        """Cœur de `validate`, à appeler verrou déjà pris.

        `threading.Lock` n'est pas reentrant : `rotate` ne pouvait pas appeler
        `validate` sans relacher le verrou entre la validation et la rotation.
        C'est ce qui ouvrait la fenetre decrite dans `rotate`.

        Args:
            token: Identifiant de session opaque.
            now: Instant courant.

        Returns:
            La session vivante, ou `None` si absente ou périmée.
        """
        session = self._sessions.get(token)
        if session is None:
            return None
        expired = (
            now - session.created_at > self.absolute_timeout_s
            or now - session.last_seen_at > self.idle_timeout_s
        )
        if expired:
            self._sessions.pop(token, None)
            return None
        session.last_seen_at = now
        return session

    def validate(self, token: str | None) -> OperatorSession | None:
        """Valide expiration absolue et inactivité côté serveur."""
        if not token:
            return None
        now = time.time()
        with self._lock:
            return self._valider_sous_verrou(token, now)

    def destroy(self, token: str | None) -> None:
        """Invalide immédiatement une session."""
        if not token:
            return
        with self._lock:
            self._sessions.pop(token, None)

    def rotate(self, token: str | None) -> tuple[str, OperatorSession] | None:
        """Remplace l'identifiant opaque sans prolonger l'expiration absolue.

        LE VERROU NE PROTEGEAIT PAS CE QUE LE COMMENTAIRE CROYAIT PROTEGER.

        La version precedente portait ceci :

            # LE JETON CSRF ETAIT REMPLACE HORS VERROU, donc pendant qu'une
            # requete concurrente pouvait le lire [...] : la rotation faisait
            # echouer des requetes legitimes.
            session.csrf_token = secrets.token_urlsafe(24)

        Le diagnostic etait juste; le correctif ne le traitait pas. Deplacer
        l'affectation SOUS le verrou ne change rien, parce que **le lecteur ne
        prend jamais le verrou** : `api/main.py` compare
        `request.headers.get("X-CSRF-Token") != session.csrf_token` sur l'objet
        que `validate()` lui a rendu, verrou deja relache. Le verrou serialise
        les ecrivains entre eux, il n'a jamais protege personne d'une mutation
        en place.

        C'est mot pour mot SEC-1, lot S11, sur une autre structure : le
        registre des techniciens mutait `self._operators` en place sous un
        commentaire qui expliquait onze lignes plus haut pourquoi il ne fallait
        pas. La doctrine etablie alors est la PUBLICATION ATOMIQUE — on ne
        modifie pas l'objet que d'autres tiennent, on en publie un nouveau.

        Deroule du defaut, avec `/api/auth/refresh` appele pendant qu'une
        ecriture est en vol :

          1. la requete A obtient la session par `validate()` ;
          2. la requete B fait tourner le jeton, et ecrase `csrf_token` sur
             l'objet que A tient toujours ;
          3. A compare son en-tete — l'ANCIEN jeton — a la valeur NOUVELLE, et
             recoit `403 Jeton de session invalide` sur une requete parfaitement
             legitime.

        Une session distincte est desormais construite, l'ancienne restant
        intacte pour les requetes en vol : A voit l'ancien jeton et passe.

        Second defaut ferme au passage : `validate()` prenait puis relachait le
        verrou avant que `rotate` ne le reprenne. Deux rotations concurrentes du
        meme jeton produisaient donc DEUX cookies valides pour une seule
        ouverture de session. La validation et la publication tiennent
        maintenant dans une seule prise de verrou.

        Args:
            token: Identifiant de session courant.

        Returns:
            Le nouvel identifiant et la nouvelle session, ou `None`.
        """
        if not token:
            return None
        now = time.time()
        replacement = secrets.token_urlsafe(32)
        with self._lock:
            courante = self._valider_sous_verrou(token, now)
            if courante is None:
                return None
            # `created_at` est recopie tel quel : la rotation ne prolonge pas
            # l'expiration absolue, ce que promet la premiere ligne.
            renouvelee = replace(
                courante,
                csrf_token=secrets.token_urlsafe(24),
                last_seen_at=now,
            )
            self._sessions.pop(token, None)
            self._sessions[replacement] = renouvelee
        return replacement, renouvelee

    def audit_events(self, limit: int = 100) -> list[dict[str, object]]:
        """Journal borné des authentifications, sans mot de passe ni jeton."""
        with self._lock:
            return list(self._audit)[-max(1, min(limit, 500)):]
