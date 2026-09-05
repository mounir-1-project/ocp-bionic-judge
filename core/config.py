"""
Configuration centrale du projet E7301.

Toutes les variables de configuration sont ici. Le reste du code
n'appelle jamais os.getenv directement.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Charge .env une seule fois
load_dotenv()

APP_VERSION = "3.0.0"
APP_ENV: str = os.getenv("APP_ENV", "demo").strip().lower()


def _env_bool(name: str, default: bool) -> bool:
    """Lit une variable d'environnement booleenne."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "oui", "on"}


def _env_float(name: str, default: float) -> float:
    """Lit une variable d'environnement numerique."""
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# ── Chemins ───────────────────────────────────────────────────────────────────
BASE_DIR: Path = Path(__file__).parents[1]
DATA_DIR: Path = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
MODEL_DIR: Path = Path(os.getenv("MODEL_DIR", BASE_DIR / "models"))
REPORT_DIR: Path = Path(os.getenv("REPORT_DIR", BASE_DIR / "reports"))

# Export DCS a surveiller — le seul point d'entree des donnees
DCS_EXPORT: Path = Path(os.getenv("DCS_EXPORT", DATA_DIR / "raw" / "DATA.xlsx"))

# ── Journalisation ────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_JSON: bool = _env_bool("LOG_JSON", False)
LOG_FILE: str | None = os.getenv("LOG_FILE")

# ── Modele et detection ───────────────────────────────────────────────────────
# Fin de la periode de reference servant a apprendre le comportement normal
REFERENCE_END: str | None = os.getenv("REFERENCE_END")
CONTAMINATION: float = _env_float("CONTAMINATION", 0.02)
RANDOM_SEED: int = int(_env_float("RANDOM_SEED", 42))
# "auto" charge l'artefact si compatible, sinon reconstruit
# "artifact" ne reconstruit jamais, "train" entraine a chaque fois
MODEL_STRATEGY: str = os.getenv("MODEL_STRATEGY", "auto").strip().lower()

# ── Rejeu temps reel ──────────────────────────────────────────────────────────
REPLAY_SPEED: float = _env_float("REPLAY_SPEED", 120.0)
REPLAY_STEP: int = int(_env_float("REPLAY_STEP", 3))

# ── Modele de langage (optionnel) ─────────────────────────────────────────────
# Le systeme fonctionne sans LLM. Renseigner GEMINI_API_KEY active la couche
# de redaction pour les agents et le Judge.
GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY") or None
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_TIMEOUT_S: float = float(os.getenv("GEMINI_TIMEOUT_S", "20"))

# ── Email (optionnel) ─────────────────────────────────────────────────────────
SMTP_HOST: str | None = os.getenv("SMTP_HOST") or None
SMTP_PORT: int = int(_env_float("SMTP_PORT", 587))
SMTP_USERNAME: str | None = os.getenv("SMTP_USERNAME") or None
SMTP_PASSWORD: str | None = os.getenv("SMTP_PASSWORD") or None
SMTP_FROM: str | None = os.getenv("SMTP_FROM") or None
SMTP_STARTTLS: bool = _env_bool("SMTP_STARTTLS", True)

# ── API ───────────────────────────────────────────────────────────────────────
API_HOST: str = os.getenv("API_HOST", "127.0.0.1")
API_PORT: int = int(_env_float("API_PORT", 8000))
CORS_ORIGINS: list[str] = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()
]


# ── Application de la configuration ───────────────────────────────────────────

def setup_logging() -> None:
    """Applique LOG_LEVEL au logger du projet."""
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
    if LOG_LEVEL not in {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}:
        problems.append(f"LOG_LEVEL inconnu : {LOG_LEVEL}")
    if not (0 < API_PORT < 65536):
        problems.append(f"API_PORT hors plage : {API_PORT}")
    return problems


setup_logging()
