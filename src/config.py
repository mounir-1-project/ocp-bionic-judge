"""
Configuration centrale — un seul point de verite pour tous les reglages.

Toute valeur susceptible de changer entre l'ordinateur de developpement, le
poste de demonstration et un serveur OCP passe par ce module. Le reste du code
n'appelle jamais `os.getenv` directement : une variable oubliee dans un coin
est une panne de production en attente.

Deux principes appliques ici :

  1. TOUTE VARIABLE DECLAREE EST UTILISEE. La version precedente exposait
     `DATABASE_URL`, `MLFLOW_TRACKING_URI` et `API_SECRET_KEY` alors qu'aucun
     module ne les lisait, et `LOG_LEVEL` n'etait jamais applique au logger.
     Une configuration qui ment sur ce qu'elle controle est pire qu'absente :
     elle fait croire qu'on a agi.

  2. LA CONFIGURATION EST VALIDEE AU DEMARRAGE, pas au premier appel. Un
     chemin de donnees invalide doit faire echouer le lancement avec un
     message clair, pas produire une trace obscure trois minutes plus tard.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

# Adresse electronique, forme minimale suffisante pour rejeter une saisie
# manifestement fautive au demarrage. La validation stricte des destinataires
# reste du ressort du relais SMTP.
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,63}$")

# Charge .env une seule fois pour tout le processus.
load_dotenv()
APP_VERSION = "3.0.0"
APP_ENV: str = os.getenv("APP_ENV", "demo").strip().lower()


def _env_bool(name: str, default: bool) -> bool:
    """Lit une variable d'environnement booleenne.

    Args:
        name: Nom de la variable.
        default: Valeur si absente.

    Returns:
        Le booleen correspondant.
    """
    raw = os.getenv(name)
    # UNE VARIABLE VIDE VAUT UNE VARIABLE ABSENTE.
    # `docker compose` injecte une chaine vide pour tout `${VAR:-}` non fourni.
    # Sans cette equivalence, laisser un reglage a sa valeur par defaut dans le
    # fichier de composition le forcait silencieusement a `false` : l'acces
    # protege se desactivait tout seul alors que la configuration exprimait
    # « laisser le systeme decider ».
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "oui", "on"}


def _env_float(name: str, default: float) -> float:
    """Lit une variable d'environnement numerique, avec repli silencieux.

    Args:
        name: Nom de la variable.
        default: Valeur si absente ou illisible.

    Returns:
        Le flottant correspondant.
    """
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# ── Chemins ───────────────────────────────────────────────────────────────────
BASE_DIR: Path = Path(__file__).parents[1]
DATA_DIR: Path = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
MODEL_DIR: Path = Path(os.getenv("MODEL_DIR", BASE_DIR / "models"))
ALARM_DB: Path = Path(os.getenv("ALARM_DB", BASE_DIR / "data" / "runtime" / "alarms.db"))
WORKFLOW_DB: Path = Path(
    os.getenv("WORKFLOW_DB", BASE_DIR / "data" / "runtime" / "workflows.db")
)
REPORT_DIR: Path = Path(os.getenv("REPORT_DIR", BASE_DIR / "reports"))

# Export DCS a surveiller. Surchargeable pour brancher un autre export sans
# toucher au code — c'est le seul point d'entree des donnees du systeme.
DCS_EXPORT: Path = Path(os.getenv("DCS_EXPORT", DATA_DIR / "raw" / "DATA.xlsx"))

# ── Journalisation ────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_JSON: bool = _env_bool("LOG_JSON", False)
LOG_FILE: str | None = os.getenv("LOG_FILE")

# ── Modele et detection ───────────────────────────────────────────────────────
# Fin de la periode de reference servant a apprendre le comportement normal.
# A ancrer sur la derniere revision de l'equipement des qu'OCP fournit la date.
REFERENCE_END: str | None = os.getenv("REFERENCE_END")
CONTAMINATION: float = _env_float("CONTAMINATION", 0.02)
RANDOM_SEED: int = int(_env_float("RANDOM_SEED", 42))
# `auto` charge l'artefact seulement si ses empreintes et son schéma concordent,
# sinon reconstruit un candidat. `artifact` interdit tout repli silencieux.
MODEL_STRATEGY: str = os.getenv("MODEL_STRATEGY", "auto").strip().lower()
MODEL_ALLOWED_STATUSES: set[str] = {
    status.strip()
    for status in os.getenv(
        "MODEL_ALLOWED_STATUSES",
        "shadow_only,approved_for_pilot,approved_for_production",
    ).split(",")
    if status.strip()
}

# ── Rejeu temps reel ──────────────────────────────────────────────────────────
REPLAY_SPEED: float = _env_float("REPLAY_SPEED", 120.0)
REPLAY_STEP: int = int(_env_float("REPLAY_STEP", 3))

# ── API ───────────────────────────────────────────────────────────────────────
# Ecoute sur la boucle locale par defaut : un poste de demonstration ne doit pas
# etre joignable depuis le reseau sans decision explicite. Le conteneur surcharge
# API_HOST a 0.0.0.0, ou l'exposition reste controlee par le mapping de port.
API_HOST: str = os.getenv("API_HOST", "127.0.0.1")
API_PORT: int = int(_env_float("API_PORT", 8000))
# Origines autorisees pour le navigateur. Par defaut aucune : le dashboard est
# servi par la meme application, donc aucune requete inter-origine n'est
# necessaire. N'ouvrir que si un front separe est deploye.
CORS_ORIGINS: list[str] = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()
]

# ── Accès opérateur ──────────────────────────────────────────────────────────
AUTH_PROVIDER: str = os.getenv("AUTH_PROVIDER", "local_demo").strip().lower()

# Registre local des techniciens. Hors dépôt, ignoré par git : il contient des
# empreintes de mots de passe et des adresses réelles.
OPERATOR_REGISTRY: Path = Path(
    os.getenv("OPERATOR_REGISTRY", BASE_DIR / "data" / "runtime" / "operators.json")
)


def _registry_is_populated(path: Path) -> bool:
    """Un technicien est-il enregistré ?

    Lecture volontairement tolérante : un registre absent ou illisible ne doit
    pas empêcher le module de configuration de se charger. La validation stricte
    a lieu au démarrage du service, avec un message explicite.

    Args:
        path: Emplacement du registre.

    Returns:
        Vrai si au moins un technicien y figure.
    """
    try:
        return bool(json.loads(path.read_text(encoding="utf-8")).get("operators"))
    except (OSError, json.JSONDecodeError, AttributeError):
        return False


# L'authentification s'active D'ELLE-MEME dès qu'un technicien est enregistré.
# C'est le comportement attendu : l'adresse saisie à l'ouverture de session
# devient le destinataire des alertes critiques, elle doit donc être
# authentifiée. `AUTH_ENABLED=false` reste possible pour une démonstration sans
# compte, mais le service le signale au démarrage.
AUTH_ENABLED: bool = _env_bool(
    "AUTH_ENABLED", _registry_is_populated(OPERATOR_REGISTRY)
)
AUTH_PASSWORD_HASH: str = os.getenv("AUTH_PASSWORD_HASH", "")
AUTH_IDLE_MINUTES: float = _env_float("AUTH_IDLE_MINUTES", 30.0)
AUTH_ABSOLUTE_HOURS: float = _env_float("AUTH_ABSOLUTE_HOURS", 8.0)
AUTH_SECURE_COOKIE: bool = _env_bool("AUTH_SECURE_COOKIE", False)
AUTH_ALLOWED_EMAILS: set[str] = {
    email.strip().lower()
    for email in os.getenv("AUTH_ALLOWED_EMAILS", "").split(",")
    if email.strip()
}
try:
    AUTH_USER_ROLES: dict[str, str] = {
        email.strip().lower(): str(role).strip()
        for email, role in json.loads(
            os.getenv("AUTH_USER_ROLES_JSON", "{}")
        ).items()
    }
except (json.JSONDecodeError, AttributeError):
    AUTH_USER_ROLES = {}

# ── Notification email (optionnelle et complémentaire à l'HMI) ──────────────
SMTP_HOST: str | None = os.getenv("SMTP_HOST") or None
SMTP_PORT: int = int(_env_float("SMTP_PORT", 587))
SMTP_USERNAME: str | None = os.getenv("SMTP_USERNAME") or None
SMTP_PASSWORD: str | None = os.getenv("SMTP_PASSWORD") or None
SMTP_FROM: str | None = os.getenv("SMTP_FROM") or None
ALERT_EMAIL_TO: str | None = os.getenv("ALERT_EMAIL_TO") or None
SMTP_STARTTLS: bool = _env_bool("SMTP_STARTTLS", True)
ALERT_MIN_SEVERITY: str = os.getenv("ALERT_MIN_SEVERITY", "CRITICAL").upper()
ALERT_COOLDOWN_MINUTES: float = _env_float("ALERT_COOLDOWN_MINUTES", 60.0)
# Dépôt local des escalades. Il sert de trace quand aucun relais n'est
# configuré, et de preuve de passage quand il y en a un.
ALERT_SPOOL: Path = Path(
    os.getenv("ALERT_SPOOL", BASE_DIR / "data" / "runtime" / "escalades")
)

# ── Modele de langage (optionnel) ─────────────────────────────────────────────
# Le systeme fonctionne integralement sans. Renseigner la cle active seulement
# la couche de redaction, jamais la couche de verification du Judge.
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY") or None

# DELAI MAXIMAL D'UN APPEL AU MODELE DE LANGAGE, EN SECONDES.
#
# Le client etait construit sans aucun delai. Un appel sortant qui ne repond
# pas bloquait alors indefiniment le thread appelant, et comme la redaction
# etait invoquee depuis une coroutine `async def` sans deport, c'est la boucle
# d'evenements ENTIERE qui restait bloquee : plus aucune requete servie, y
# compris la sonde de vivacite interrogee par l'orchestrateur, qui finissait
# par tuer un conteneur en bonne sante.
#
# La couche de redaction est facultative par construction : expirer et
# retomber sur la formulation deterministe est toujours preferable a figer la
# supervision d'un equipement en marche.
GEMINI_TIMEOUT_S: float = float(os.getenv("GEMINI_TIMEOUT_S", "20"))


# ── Application de la configuration ───────────────────────────────────────────

def setup_logging() -> None:
    """Applique LOG_LEVEL, LOG_JSON et LOG_FILE au logger du projet.

    Sans cet appel, `LOG_LEVEL` resterait une variable decorative : loguru
    conserverait son niveau DEBUG par defaut et ignorerait le reglage.
    """
    from loguru import logger

    logger.remove()
    fmt = (
        "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}"
        if not LOG_JSON else None
    )
    logger.add(sys.stderr, level=LOG_LEVEL, format=fmt or "{message}",
               serialize=LOG_JSON, backtrace=False, diagnose=False)
    if LOG_FILE:
        Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        logger.add(LOG_FILE, level=LOG_LEVEL, rotation="10 MB", retention="30 days",
                   serialize=LOG_JSON, enqueue=True)


def validate() -> list[str]:
    """Verifie la coherence de la configuration au demarrage.

    Returns:
        Liste des problemes bloquants. Vide si tout est correct.
    """
    problems: list[str] = []
    if APP_ENV not in {"development", "demo", "production"}:
        problems.append("APP_ENV doit valoir development, demo ou production")
    if not DCS_EXPORT.exists():
        problems.append(
            f"Export DCS introuvable : {DCS_EXPORT}. "
            f"Placer le fichier ou definir DCS_EXPORT."
        )
    if not (0.0 < CONTAMINATION < 0.5):
        problems.append(f"CONTAMINATION doit etre dans ]0, 0.5[ — recu {CONTAMINATION}")
    if REPLAY_SPEED <= 0:
        problems.append(f"REPLAY_SPEED doit etre strictement positif — recu {REPLAY_SPEED}")
    if MODEL_STRATEGY not in {"auto", "artifact", "train"}:
        problems.append("MODEL_STRATEGY doit valoir auto, artifact ou train")
    known_model_statuses = {
        "shadow_only", "approved_for_pilot", "approved_for_production"
    }
    if not MODEL_ALLOWED_STATUSES or not known_model_statuses >= MODEL_ALLOWED_STATUSES:
        problems.append(
            "MODEL_ALLOWED_STATUSES contient un statut non exécutable"
        )
    if LOG_LEVEL not in {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}:
        problems.append(f"LOG_LEVEL inconnu : {LOG_LEVEL}")
    # Deux sources d'identifiants possibles : le registre local par technicien
    # (recommande) ou l'empreinte partagee historique. Il en faut au moins une.
    registry_ready = _registry_is_populated(OPERATOR_REGISTRY)
    shared_ready = (
        AUTH_PASSWORD_HASH.startswith("pbkdf2_sha256$") and bool(AUTH_ALLOWED_EMAILS)
    )
    if AUTH_ENABLED and not (registry_ready or shared_ready):
        problems.append(
            "AUTH_ENABLED sans identifiants : enregistrer un technicien avec "
            "`python scripts/manage_operators.py add`, ou definir "
            "AUTH_PASSWORD_HASH et AUTH_ALLOWED_EMAILS."
        )
    if AUTH_PASSWORD_HASH and not AUTH_PASSWORD_HASH.startswith("pbkdf2_sha256$"):
        problems.append("AUTH_PASSWORD_HASH doit etre au format pbkdf2_sha256")
    known_roles = {
        "reader", "operator", "maintenance",
        "reliability_engineer", "administrator",
    }
    if not set(AUTH_USER_ROLES) <= AUTH_ALLOWED_EMAILS:
        problems.append("AUTH_USER_ROLES_JSON contient un e-mail hors allowlist")
    if not set(AUTH_USER_ROLES.values()) <= known_roles:
        problems.append("AUTH_USER_ROLES_JSON contient un rôle inconnu")
    if APP_ENV == "production":
        if not AUTH_ENABLED:
            problems.append("Le mode production exige AUTH_ENABLED=true")
        if AUTH_PROVIDER != "oidc":
            problems.append(
                "NO-GO production: AUTH_PROVIDER=oidc requis; "
                "le fournisseur IAM n'est pas encore intégré"
            )
        if not AUTH_SECURE_COOKIE:
            problems.append("Le mode production exige AUTH_SECURE_COOKIE=true")
    if AUTH_IDLE_MINUTES <= 0 or AUTH_ABSOLUTE_HOURS <= 0:
        problems.append("Les durees de session doivent etre strictement positives")
    if ALERT_MIN_SEVERITY not in {"INFO", "WARNING", "CRITICAL"}:
        problems.append(
            f"ALERT_MIN_SEVERITY inconnu : {ALERT_MIN_SEVERITY}"
        )
    if ALERT_COOLDOWN_MINUTES < 0:
        problems.append("ALERT_COOLDOWN_MINUTES ne peut pas etre negatif")

    # UN JOKER D'ORIGINE AVEC IDENTIFIANTS EST UNE FAILLE, PAS UN REGLAGE.
    # `allow_credentials=True` est passe a CORSMiddleware (api/main.py). Combine
    # a une origine `*`, il autorise n'importe quel site a lire les reponses
    # authentifiees du poste. Le navigateur refuse la combinaison, mais rien
    # n'empeche un client non navigateur de l'exploiter : le refus se fait ici.
    for origine in CORS_ORIGINS:
        if origine == "*":
            problems.append(
                "CORS_ORIGINS ne peut pas valoir '*' : les sessions sont "
                "portees par cookie et l'origine doit etre nommee"
            )
        elif not origine.startswith(("http://", "https://")):
            problems.append(
                f"CORS_ORIGINS contient une origine sans schema : {origine}"
            )

    # UN RELAIS A MOITIE CONFIGURE ECHOUE AU PREMIER ENVOI, PAS AU DEMARRAGE.
    # Sans ces controles, un SMTP_HOST sans SMTP_FROM ou un SMTP_USERNAME sans
    # mot de passe laissaient le canal se declarer pret, puis echouer
    # silencieusement dans le fil d'envoi — au moment precis d'une escalade.
    if SMTP_HOST and not SMTP_FROM:
        problems.append("SMTP_HOST est defini sans SMTP_FROM : aucun envoi ne partira")
    if SMTP_USERNAME and not SMTP_PASSWORD:
        problems.append(
            "SMTP_USERNAME est defini sans SMTP_PASSWORD : "
            "l'authentification du relais echouera au premier envoi"
        )
    if not (0 < SMTP_PORT < 65536):
        problems.append(f"SMTP_PORT hors plage : {SMTP_PORT}")
    for nom, adresse in (("SMTP_FROM", SMTP_FROM), ("ALERT_EMAIL_TO", ALERT_EMAIL_TO)):
        if adresse and not _EMAIL.fullmatch(adresse.strip()):
            problems.append(f"{nom} n'est pas une adresse valide : {adresse}")

    if not (0 < API_PORT < 65536):
        problems.append(f"API_PORT hors plage : {API_PORT}")
    return problems


def summary() -> dict[str, object]:
    """Configuration effective, pour l'endpoint de diagnostic.

    La cle API n'est jamais exposee : seule sa presence est indiquee.

    Returns:
        Dictionnaire de la configuration active.
    """
    # LES CHEMINS SONT PUBLIES EN RELATIF, JAMAIS EN ABSOLU.
    # `/api/config` renvoyait `C:\Users\<nom>\...` ou `/home/<nom>/...` : un
    # endpoint de diagnostic n'a aucune raison de divulguer l'arborescence de
    # la machine hote, son nom d'utilisateur ni sa structure de repertoires.
    # Le chemin relatif suffit a diagnostiquer un mauvais montage.
    def _relatif(chemin: Path) -> str:
        try:
            return chemin.resolve().relative_to(BASE_DIR.resolve()).as_posix()
        except ValueError:
            return chemin.name

    return {
        "app_version": APP_VERSION,
        "app_env": APP_ENV,
        "dcs_export": _relatif(DCS_EXPORT),
        "model_dir": _relatif(MODEL_DIR),
        "workflow_db": _relatif(WORKFLOW_DB),
        "report_dir": _relatif(REPORT_DIR),
        "log_level": LOG_LEVEL,
        "log_json": LOG_JSON,
        "reference_end": REFERENCE_END,
        "contamination": CONTAMINATION,
        "random_seed": RANDOM_SEED,
        "model_strategy": MODEL_STRATEGY,
        "model_allowed_statuses": sorted(MODEL_ALLOWED_STATUSES),
        "replay_speed": REPLAY_SPEED,
        "replay_step": REPLAY_STEP,
        "cors_origins": CORS_ORIGINS,
        "auth_enabled": AUTH_ENABLED,
        "auth_provider": AUTH_PROVIDER,
        "auth_identity": "session_email" if AUTH_ENABLED else "local_post",
        "auth_secure_cookie": AUTH_SECURE_COOKIE,
        "auth_allowlist_configured": bool(AUTH_ALLOWED_EMAILS),
        "auth_role_count": len(AUTH_USER_ROLES),
        "email_notifications_configured": bool(
            SMTP_HOST and SMTP_FROM
        ),
        "alert_min_severity": ALERT_MIN_SEVERITY,
        "alert_cooldown_minutes": ALERT_COOLDOWN_MINUTES,
        "llm_configured": GEMINI_API_KEY is not None,
        "llm_model": GEMINI_MODEL if GEMINI_API_KEY else None,
    }


setup_logging()
