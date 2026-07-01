"""
Central configuration module — import once, used everywhere.

Calls load_dotenv() exactly once for the entire process. All modules that need
environment variables should import from here rather than calling load_dotenv()
themselves.

Author: Mounir Sanbouli
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env exactly once — idempotent but calling it 8× is unnecessary noise.
load_dotenv()

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR: Path = Path(__file__).parents[1]
DATA_DIR: Path = BASE_DIR / "data"
MODEL_DIR: Path = BASE_DIR / "models"

# ── Database ──────────────────────────────────────────────────────────────────
DEFAULT_DB_URL: str = f"sqlite:///{DATA_DIR / 'ocp_bionic.db'}"
DATABASE_URL: str = os.getenv("DATABASE_URL", DEFAULT_DB_URL)

# ── Gemini (Google AI Studio — free tier) ────────────────────────────────────
# Override via GEMINI_MODEL in .env to switch models without code changes.
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# ── API ───────────────────────────────────────────────────────────────────────
API_SECRET_KEY: str | None = os.getenv("API_SECRET_KEY")
MLFLOW_TRACKING_URI: str = os.getenv("MLFLOW_TRACKING_URI", str(BASE_DIR / "mlruns"))
