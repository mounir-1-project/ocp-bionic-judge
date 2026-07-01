"""
OCP Bionic Judge — API REST
Author: Mounir Sanbouli
"""
from __future__ import annotations
import asyncio
import base64, os, secrets, time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

import jwt
import pandas as pd
from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Request, Response, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import APIKeyHeader
from loguru import logger
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import text

from src.config import API_SECRET_KEY as _CFG_API_KEY  # ensures load_dotenv() is called
from src.db import get_engine, init_schema

# ── Machine ID enum — single source of truth for all valid machine IDs ─────────
class MachineId(str, Enum):
    """All 5 OCP Bionic machines. FastAPI validates and returns 422 for unknown IDs."""
    BROYEUR_01     = "BROYEUR_01"
    POMPE_02       = "POMPE_02"
    CONVOYEUR_03   = "CONVOYEUR_03"
    REACTEUR_04    = "REACTEUR_04"
    COMPRESSEUR_05 = "COMPRESSEUR_05"

# ── JWT configuration ─────────────────────────────────────────────────────────
# JWT_SECRET is generated fresh each process — stored sessions survive restarts
# only if you set JWT_SECRET explicitly in .env.
_JWT_SECRET:  str = os.getenv("JWT_SECRET", secrets.token_hex(32))
_JWT_ALGO:    str = "HS256"
_JWT_HOURS:   int = 8   # session lifetime

# Thread pool for running synchronous agent/ML code without blocking the event loop.
# max_workers=4: allows 4 concurrent /analyze requests; agent calls take ~10-60s.
_AGENT_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ocp_agent")

# API key comes from src.config (which called load_dotenv already).
if not _CFG_API_KEY:
    logger.warning(
        "API_SECRET_KEY not set in .env — authentication is DISABLED. "
        "Set API_SECRET_KEY in your .env file before deploying."
    )
API_KEY: str = _CFG_API_KEY or "INSECURE_DEV_KEY"

# Set COOKIE_SECURE=true in .env when deploying behind HTTPS.
# False is intentional for local HTTP dev — do NOT change to True without TLS.
COOKIE_SECURE: bool = os.getenv("COOKIE_SECURE", "false").lower() == "true"

# Rate limiter — keyed by client IP address.
# /auth/login is limited to 10 requests/minute to prevent brute-force attacks.
_limiter = Limiter(key_func=get_remote_address)

# DB_PATH kept for legacy reference; all reads now go through SQLAlchemy (see _db_read).
DB_PATH = Path(__file__).parent.parent / "data" / "ocp_bionic.db"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Security fail-fast: production must have COOKIE_SECURE=true ────────────
    # This prevents accidental deployment with insecure cookie settings.
    # Set ENV=production and COOKIE_SECURE=true in .env before going live.
    _env = os.getenv("ENV", "development").lower()
    if _env == "production" and not COOKIE_SECURE:
        raise ValueError(
            "SECURITY ERROR: ENV=production requires COOKIE_SECURE=true. "
            "Set COOKIE_SECURE=true in your .env file before deploying behind HTTPS."
        )
    try:
        init_schema(get_engine())
        logger.info("DB ready.")
    except Exception as e:
        logger.warning(f"Schema init skipped: {e}")
    yield


app = FastAPI(
    title="OCP Bionic Judge — API",
    description="""
## Système de Détection d'Anomalies Industrielles

API REST pour la surveillance en temps réel des équipements phosphate OCP.

### Pipeline ML
- **3 modèles comparés** : Isolation Forest (déployé), One-Class SVM, HDBSCAN
- **24 features ciblées** (z-scores par machine, flags de coupure, z-scores locaux, deltas, temporel)
- **Split chronologique 80/20** — AUC-ROC 0.82 (IF déployé) / 0.93 (OC-SVM, leader AUC)

### Agents IA
- **Detection Agent** (LangChain + Gemini) : diagnostic ReAct
- **Judge Agent** (Gemini API) : 5 critères pondérés

### Authentification
Cookie JWT httpOnly (session navigateur via `POST /auth/login`) ou header `X-API-Key` (scripts/CLI).
Routes publiques : `/health` et `/api/summary`.

### Machines surveillées
| ID | Machine | Site |
|----|---------|------|
| BROYEUR_01 | Broyeur à Boulets | Khouribga |
| POMPE_02 | Pompe Centrifuge | Benguerir |
| CONVOYEUR_03 | Convoyeur à Courroie | Jorf Lasfar |
| REACTEUR_04 | Réacteur d'Attaque | Youssoufia |
| COMPRESSEUR_05 | Compresseur Industriel | Safi |
""",
    version="1.2.0",
    contact={"name": "Mounir Sanbouli", "email": "mounir.sanbouli.43@edu.uiz.ac.ma"},
    license_info={"name": "MIT"},
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

app.state.limiter = _limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip() for o in
        os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000,http://localhost:5173").split(",")
        if o.strip()   # guard against empty strings from trailing commas
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
    allow_credentials=True,   # required for httpOnly cookie auth cross-origin
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_logo_b64() -> str:
    p = Path(__file__).parent.parent / "dashboard" / "assets" / "ocp_logo.png"
    return base64.b64encode(p.read_bytes()).decode() if p.exists() else ""

_LOGO = _get_logo_b64()


async def verify_api_key(
    api_key: str = Security(api_key_header),
    ocp_session: Optional[str] = Cookie(default=None),
) -> str:
    """Accept either X-API-Key header (direct calls) or an httpOnly JWT cookie (browser).

    Browser flow: POST /auth/login → httpOnly cookie set → subsequent requests
    include the cookie automatically. The API key never touches JavaScript memory.

    CLI/script flow: X-API-Key header as before.
    """
    # 1. Check X-API-Key header (backward-compatible for scripts/CLI)
    if api_key and api_key == API_KEY:
        return api_key
    # 2. Check JWT from httpOnly cookie (browser sessions)
    if ocp_session:
        try:
            jwt.decode(ocp_session, _JWT_SECRET, algorithms=[_JWT_ALGO])
            return "cookie_session"
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Session expirée — reconnectez-vous.")
        except jwt.InvalidTokenError:
            pass
    raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ── Scalar API Docs ───────────────────────────────────────────────────────────

@app.get("/docs", include_in_schema=False)
async def scalar_docs() -> HTMLResponse:
    """Scalar API Reference — premium OCP-branded API documentation."""
    logo_tag = (
        f'<img src="data:image/png;base64,{_LOGO}" '
        'height="30" style="object-fit:contain;vertical-align:middle;'
        'margin-right:12px;border-radius:7px;'
        'box-shadow:0 0 14px rgba(0,211,127,.3),0 0 0 1px rgba(0,211,127,.15);" />'
        if _LOGO else
        '<span style="display:inline-flex;align-items:center;justify-content:center;'
        'width:32px;height:32px;border-radius:8px;margin-right:12px;font-size:14px;'
        'font-weight:900;background:rgba(0,211,127,.12);border:1px solid rgba(0,211,127,.3);'
        'color:#00D37F;">OCP</span>'
    )
    now_str = datetime.now().strftime("%d %b %Y · %H:%M UTC")
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>OCP Bionic Judge — API Reference</title>
  {"" if not _LOGO else f'<link rel="icon" type="image/png" href="data:image/png;base64,{_LOGO}" />'}
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500&display=swap');

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{ height: 100%; background: #080B10; }}

    /* ── Keyframes ── */
    @keyframes sweep {{
      0%   {{ background-position: -200% 0; }}
      100% {{ background-position: 200% 0; }}
    }}
    @keyframes pulse-dot {{
      0%, 100% {{ box-shadow: 0 0 0 2px rgba(0,211,127,.25); }}
      50%       {{ box-shadow: 0 0 0 6px rgba(0,211,127,.06); }}
    }}
    @keyframes fade-up {{
      from {{ opacity: 0; transform: translateY(8px); }}
      to   {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes spin {{
      to {{ transform: rotate(360deg); }}
    }}

    /* ── Premium topbar ── */
    .ocp-bar {{
      position: fixed; top: 0; left: 0; right: 0; z-index: 10000;
      height: 56px;
      background: rgba(8,11,16,.92);
      backdrop-filter: blur(20px) saturate(180%);
      -webkit-backdrop-filter: blur(20px) saturate(180%);
      border-bottom: 1px solid rgba(30,36,50,.9);
      display: flex; align-items: center;
      padding: 0 28px;
      justify-content: space-between;
      font-family: 'Inter', sans-serif;
    }}
    /* animated gradient line under topbar */
    .ocp-bar::after {{
      content: '';
      position: absolute; bottom: -1px; left: 0; right: 0; height: 1px;
      background: linear-gradient(90deg,
        transparent 0%,
        rgba(0,211,127,.0) 20%,
        rgba(0,211,127,.7) 50%,
        rgba(0,211,127,.0) 80%,
        transparent 100%);
      background-size: 200% 100%;
      animation: sweep 4s ease-in-out infinite;
    }}
    .ocp-brand {{ display: flex; align-items: center; }}
    .ocp-title {{
      font-size: 15px; font-weight: 800; color: #E6EDF3;
      letter-spacing: -0.3px;
    }}
    .ocp-subtitle {{
      font-size: 10px; color: #3D4455;
      text-transform: uppercase; letter-spacing: 1.3px; margin-top: 2px;
    }}
    .ocp-right {{ display: flex; align-items: center; gap: 10px; }}
    .ocp-chip {{
      font-size: 10px; font-weight: 700; padding: 4px 11px; border-radius: 5px;
      letter-spacing: 0.6px; text-transform: uppercase;
      font-family: 'Inter', sans-serif; display: inline-flex; align-items: center; gap: 5px;
    }}
    .ocp-chip.green {{
      background: rgba(0,211,127,.09); border: 1px solid rgba(0,211,127,.25); color: #00D37F;
      box-shadow: 0 0 12px rgba(0,211,127,.12);
    }}
    .ocp-chip.green .dot {{
      width: 5px; height: 5px; background: #00D37F; border-radius: 50%;
      animation: pulse-dot 2.5s ease-in-out infinite;
    }}
    .ocp-chip.gray  {{
      background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.09); color: #6B7280;
    }}
    .ocp-divider {{
      width: 1px; height: 20px; background: rgba(255,255,255,.07);
    }}
    .ocp-time {{
      font-size: 10px; color: #3D4455;
      font-family: 'JetBrains Mono', monospace;
    }}

    /* ── Intro hero banner ── */
    .ocp-hero {{
      padding: 72px 40px 0;
      background: #080B10;
      border-bottom: 1px solid rgba(30,36,50,.8);
      animation: fade-up 0.5s ease forwards;
    }}
    .ocp-hero-inner {{
      max-width: 1200px; margin: 0 auto;
      padding: 36px 0 32px;
      display: grid; grid-template-columns: 1fr auto; gap: 40px; align-items: start;
    }}
    .ocp-hero-tag {{
      display: inline-flex; align-items: center; gap: 7px;
      font-size: 10px; font-weight: 700; color: #00D37F;
      text-transform: uppercase; letter-spacing: 1.5px;
      background: rgba(0,211,127,.07); border: 1px solid rgba(0,211,127,.2);
      padding: 4px 12px; border-radius: 4px; margin-bottom: 14px;
    }}
    .ocp-hero-title {{
      font-size: 30px; font-weight: 900; color: #E6EDF3;
      letter-spacing: -1px; line-height: 1.15;
      background: linear-gradient(135deg, #E6EDF3 55%, #6B7280);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      background-clip: text;
    }}
    .ocp-hero-desc {{
      font-size: 14px; color: #4B5263; line-height: 1.65; margin-top: 10px;
      max-width: 560px;
    }}

    /* ── Quick-stat cards ── */
    .ocp-stats {{
      display: flex; flex-direction: column; gap: 8px; min-width: 220px;
    }}
    .ocp-stat {{
      background: rgba(14,18,28,.8);
      border: 1px solid rgba(30,36,50,.9);
      border-radius: 10px; padding: 14px 18px;
      display: flex; align-items: center; gap: 12px;
      transition: border-color .2s, box-shadow .2s;
    }}
    .ocp-stat:hover {{
      border-color: rgba(0,211,127,.2);
      box-shadow: 0 0 16px rgba(0,211,127,.06);
    }}
    .ocp-stat-icon {{
      width: 34px; height: 34px; border-radius: 8px; flex-shrink: 0;
      display: flex; align-items: center; justify-content: center;
      font-size: 15px;
    }}
    .ocp-stat-icon.green {{ background: rgba(0,211,127,.1); border: 1px solid rgba(0,211,127,.2); }}
    .ocp-stat-icon.blue  {{ background: rgba(79,124,246,.1); border: 1px solid rgba(79,124,246,.2); }}
    .ocp-stat-icon.amber {{ background: rgba(255,176,32,.1);  border: 1px solid rgba(255,176,32,.2); }}
    .ocp-stat-val  {{ font-size: 18px; font-weight: 800; color: #E6EDF3; letter-spacing: -0.5px; }}
    .ocp-stat-label{{ font-size: 10px; color: #4B5263; text-transform: uppercase; letter-spacing: 0.8px; margin-top: 1px; }}

    /* ── Endpoint summary chips ── */
    .ocp-endpoints {{
      max-width: 1200px; margin: 0 auto;
      padding: 20px 0 28px;
      display: flex; gap: 10px; flex-wrap: wrap; align-items: center;
    }}
    .ocp-ep-label {{
      font-size: 10px; color: #3D4455; text-transform: uppercase;
      letter-spacing: 1px; font-weight: 600; margin-right: 4px;
    }}
    .ocp-ep {{
      display: inline-flex; align-items: center; gap: 6px;
      font-size: 11px; font-weight: 600;
      padding: 4px 12px; border-radius: 5px;
      font-family: 'JetBrains Mono', monospace;
    }}
    .ocp-ep.post {{ background: rgba(0,211,127,.07); border: 1px solid rgba(0,211,127,.18); color: #00D37F; }}
    .ocp-ep.get  {{ background: rgba(79,124,246,.07); border: 1px solid rgba(79,124,246,.18); color: #4F7CF6; }}

    /* ── Loading overlay while Scalar initialises ── */
    #scalar-loader {{
      position: fixed; inset: 56px 0 0 0;
      background: #080B10;
      display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      gap: 16px; z-index: 5000;
      transition: opacity .4s ease;
    }}
    #scalar-loader .ring {{
      width: 36px; height: 36px;
      border: 2px solid rgba(0,211,127,.15);
      border-top-color: #00D37F;
      border-radius: 50%;
      animation: spin .8s linear infinite;
    }}
    #scalar-loader p {{
      font-size: 12px; color: #3D4455;
      font-family: 'Inter', sans-serif; letter-spacing: 0.5px;
    }}

    /* ── Push content below fixed bar, and insert hero above Scalar ── */
    body {{ padding-top: 56px; }}

    /* ── Scalar dark overrides ── */
    :root {{
      --scalar-color-1: #E6EDF3;
      --scalar-color-2: #8B949E;
      --scalar-color-3: #484F58;
      --scalar-background-1: #080B10;
      --scalar-background-2: #0D1117;
      --scalar-background-3: #131920;
      --scalar-border-color: #1E2432;
      --scalar-color-accent: #00D37F;
      --scalar-sidebar-background-1: #0A0D14;
      --scalar-sidebar-color: #6B7280;
      --scalar-sidebar-color-active: #E6EDF3;
      --scalar-sidebar-search-background: #131920;
    }}
    ::-webkit-scrollbar {{ width: 5px; height: 5px; }}
    ::-webkit-scrollbar-track {{ background: transparent; }}
    ::-webkit-scrollbar-thumb {{ background: #1E2432; border-radius: 4px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: #2A3040; }}
  </style>
</head>
<body>

  <!-- ── Premium topbar ── -->
  <div class="ocp-bar">
    <div class="ocp-brand">
      {logo_tag}
      <div>
        <div class="ocp-title">Bionic Judge</div>
        <div class="ocp-subtitle">OCP · Industrial AI Platform</div>
      </div>
    </div>
    <div class="ocp-right">
      <span class="ocp-time">{now_str}</span>
      <div class="ocp-divider"></div>
      <span class="ocp-chip green"><span class="dot"></span>API Online</span>
      <span class="ocp-chip gray">v1.2.0</span>
    </div>
  </div>

  <!-- ── Hero intro banner ── -->
  <div class="ocp-hero">
    <div class="ocp-hero-inner">
      <div>
        <div class="ocp-hero-tag">
          <span>●</span> REST API · OCP Bionic Programme
        </div>
        <div class="ocp-hero-title">API Reference</div>
        <div class="ocp-hero-desc">
          Surveillance en temps réel des équipements phosphate OCP. 3 modèles ML (Isolation Forest,
          One-Class SVM, HDBSCAN), 24 features ciblées, agents IA ReAct (LangChain + Gemini),
          et Judge Agent à 5 critères pondérés.
        </div>
      </div>
      <div class="ocp-stats">
        <div class="ocp-stat">
          <div class="ocp-stat-icon green">⚙</div>
          <div>
            <div class="ocp-stat-val" id="stat-machines">—</div>
            <div class="ocp-stat-label">Machines actives</div>
          </div>
        </div>
        <div class="ocp-stat">
          <div class="ocp-stat-icon blue">◈</div>
          <div>
            <div class="ocp-stat-val" id="stat-readings">—</div>
            <div class="ocp-stat-label">Lectures analysées</div>
          </div>
        </div>
        <div class="ocp-stat">
          <div class="ocp-stat-icon amber">◆</div>
          <div>
            <div class="ocp-stat-val" id="stat-anomalies">—</div>
            <div class="ocp-stat-label">Anomalies détectées</div>
          </div>
        </div>
      </div>
    </div>
    <div class="ocp-endpoints">
      <span class="ocp-ep-label">Endpoints</span>
      <span class="ocp-ep post">POST /analyze</span>
      <span class="ocp-ep get">GET /decisions</span>
      <span class="ocp-ep get">GET /governance-metrics</span>
      <span class="ocp-ep get">GET /health</span>
      <span class="ocp-ep get">GET /api/summary</span>
      <span class="ocp-ep get">GET /api/sensors/{{machine_id}}</span>
    </div>
  </div>

  <!-- Loading spinner while Scalar initialises -->
  <div id="scalar-loader">
    <div class="ring"></div>
    <p>Chargement de la documentation…</p>
  </div>

  <!-- Scalar API Reference -->
  <script
    id="api-reference"
    data-url="/openapi.json"
    data-configuration='{{"darkMode": true, "theme": "saturn", "layout": "modern", "defaultHttpClient": {{"targetKey": "python", "clientKey": "requests"}}, "hideClientButton": false, "searchHotKey": "k", "hiddenClients": []}}'
  ></script>
  <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>

  <script>
    // Hide the loader once Scalar has painted its first frame
    const loader = document.getElementById('scalar-loader');
    const observer = new MutationObserver(() => {{
      const scalar = document.querySelector('.scalar-app, #api-reference + div, [class*="scalar"]');
      if (scalar) {{
        loader.style.opacity = '0';
        setTimeout(() => loader.remove(), 400);
        observer.disconnect();
      }}
    }});
    observer.observe(document.body, {{ childList: true, subtree: true }});
    // Fallback: hide after 4s regardless
    setTimeout(() => {{ loader.style.opacity = '0'; setTimeout(() => loader.remove(), 400); }}, 4000);
  </script>

  <script>
    // Populate hero stat cards from live /api/summary (no auth required)
    fetch('/api/summary')
      .then(r => r.ok ? r.json() : null)
      .then(d => {{
        if (!d) return;
        const m = document.getElementById('stat-machines');
        const r = document.getElementById('stat-readings');
        const a = document.getElementById('stat-anomalies');
        if (m) m.textContent = d.machines_active ?? '—';
        if (r) r.textContent = d.total_readings != null
          ? d.total_readings.toLocaleString('fr-FR') : '—';
        if (a) a.textContent = d.anomalies != null
          ? d.anomalies.toLocaleString('fr-FR') : '—';
      }})
      .catch(() => {{}});
  </script>
</body>
</html>""")


# ── Auth endpoints ────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    api_key: str = Field(..., description="The X-API-Key value from your .env file")


@app.post("/auth/login", tags=["Auth"])
async def auth_login(req: LoginRequest, response: Response) -> dict:
    """Validate the API key and set a signed JWT in an httpOnly cookie.

    The browser frontend calls this once on login.  All subsequent API requests
    include the cookie automatically — the raw API key never touches JS memory.

    Returns:
        {"status": "ok"} on success, 401 on invalid key.
    """
    if req.api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Clé API invalide.")
    token = jwt.encode(
        {
            "sub": "ocp_user",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=_JWT_HOURS),
        },
        _JWT_SECRET,
        algorithm=_JWT_ALGO,
    )
    response.set_cookie(
        key="ocp_session",
        value=token,
        httponly=True,           # not accessible to JS — XSS-safe
        samesite="lax",          # "strict" breaks cross-origin dev proxy
        secure=COOKIE_SECURE,    # True in prod — set COOKIE_SECURE=true in .env
        max_age=_JWT_HOURS * 3600,
        path="/",
    )
    logger.info("Login successful — JWT session cookie set (%dh)", _JWT_HOURS)
    return {"status": "ok", "expires_in_hours": _JWT_HOURS}


@app.get("/auth/me", tags=["Auth"])
async def auth_me(request: Request) -> dict:
    """Check if the current session cookie is still valid.

    Returns 200 {"status": "ok"} if authenticated, 401 otherwise.
    Used by the frontend to restore session after a page reload.
    """
    token = request.cookies.get("ocp_session")
    if not token:
        raise HTTPException(status_code=401, detail="Non authentifié.")
    try:
        jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGO])
    except Exception:
        raise HTTPException(status_code=401, detail="Session expirée.")
    return {"status": "ok"}


@app.post("/auth/logout", tags=["Auth"])
async def auth_logout(response: Response) -> dict:
    """Clear the JWT session cookie.

    Returns:
        {"status": "logged_out"}
    """
    response.delete_cookie(key="ocp_session", path="/")
    return {"status": "logged_out"}


# ── Data endpoints ────────────────────────────────────────────────────────────

@app.get("/api/summary", tags=["Dashboard"])
async def public_summary():
    """Public summary — no auth required."""
    dec = _db_read("SELECT severity, machine_id FROM ml_decisions")
    return {
        "total_readings":  len(dec),
        "machines_active": int(dec["machine_id"].nunique()) if not dec.empty else 0,
        "anomalies":       int(dec[dec["severity"] != "NORMAL"].shape[0]) if not dec.empty else 0,
        "critical":        int((dec["severity"] == "CRITICAL").sum()) if not dec.empty else 0,
        "normal":          int((dec["severity"] == "NORMAL").sum()) if not dec.empty else 0,
        "db_connected":    _check_db(),
        "model_loaded":    _check_model(),
        "generated_at":    datetime.now().isoformat(),
    }


@app.get("/api/sensors/{machine_id}", tags=["Dashboard"])
async def get_sensor_readings(
    machine_id: MachineId,
    limit: int = Query(720, ge=10, le=2000),
    _key: str = Depends(verify_api_key),
) -> list:
    """Time-series sensor readings for a machine.

    machine_id must be one of the 5 known OCP machines — FastAPI returns 422
    with a descriptive error if an unknown ID is provided.
    """
    df = _db_read(
        "SELECT * FROM sensor_readings WHERE machine_id=:mid ORDER BY timestamp DESC LIMIT :lim",
        {"mid": machine_id.value, "lim": limit},
    )
    if df.empty:
        return []
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.sort_values("timestamp").to_dict(orient="records")


@app.get("/api/judge-evals", tags=["Dashboard"])
async def get_judge_evals(
    limit:  int = Query(300, ge=1, le=1000),
    offset: int = Query(0,   ge=0),
    _key: str = Depends(verify_api_key),
) -> list:
    """Judge evaluation records with optional pagination via limit/offset."""
    df = _db_read(
        "SELECT * FROM judge_evaluations ORDER BY timestamp DESC LIMIT :lim OFFSET :off",
        {"lim": limit, "off": offset},
    )
    return [] if df.empty else df.to_dict(orient="records")


@app.get("/api/audit-log", tags=["Dashboard"])
async def get_audit_log(
    limit:      int                  = Query(300, ge=1, le=1000),
    machine_id: Optional[MachineId] = Query(None),
    severity:   Optional[str]       = Query(None, pattern="^(INFO|WARNING|CRITICAL)$"),
    _key: str = Depends(verify_api_key),
) -> list:
    """Audit log entries. machine_id is validated against the 5 known machines."""
    sql = "SELECT * FROM audit_log WHERE 1=1"
    params: dict = {}
    if machine_id:
        sql += " AND machine_id=:mid"
        params["mid"] = machine_id.value
    if severity:
        sql += " AND severity=:sev"
        params["sev"] = severity
    sql += " ORDER BY timestamp DESC LIMIT :lim"
    params["lim"] = int(limit)
    df = _db_read(sql, params)
    return [] if df.empty else df.to_dict(orient="records")


# ── Schemas ───────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    machine_id: MachineId = Field(..., json_schema_extra={"example": "BROYEUR_01"})
    use_agent:  bool      = Field(default=True)
    run_judge:  bool      = Field(default=True)

class AnalyzeResponse(BaseModel):
    machine_id:         str
    timestamp:          str
    anomaly_score:      float
    severity:           str
    diagnosis:          Optional[str]   = None
    recommended_action: Optional[str]   = None
    confidence:         Optional[float] = None
    judge_score:        Optional[float] = None
    judge_agreement:    Optional[bool]  = None
    processing_ms:      float

class DecisionRecord(BaseModel):
    id:            int
    machine_id:    str
    timestamp:     str
    anomaly_score: float
    is_anomaly:    int
    severity:      str
    model_version: Optional[str]   = None
    inference_ms:  Optional[float] = None

class GovernanceMetrics(BaseModel):
    window:                str
    computed_at:           str
    n_evaluations:         int
    mean_judge_confidence: Optional[float] = None
    disagreement_rate:     Optional[float] = None
    ocp_compliance_rate:   Optional[float] = None
    critical_unresolved:   Optional[int]   = None
    alerts:                list[dict]      = Field(default_factory=list)

class HealthResponse(BaseModel):
    status:       str
    timestamp:    str
    db_connected: bool
    model_loaded: bool
    version:      str = "1.2.0"


# ── DB helpers ────────────────────────────────────────────────────────────────

def _db_read(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Execute a read-only SQL query via the SQLAlchemy engine.

    Unified replacement for the former _db_query() that used sqlite3 directly.
    Using the engine ensures compatibility with both SQLite (dev) and
    PostgreSQL (production) without maintaining two DB connections.

    Args:
        sql:    SQL query using :named_param syntax (SQLAlchemy text()).
        params: Optional dict of named parameters matching :placeholders.

    Returns:
        DataFrame with query results, or empty DataFrame on failure.
    """
    try:
        with get_engine().connect() as conn:
            return pd.read_sql(text(sql), conn, params=params or {})
    except Exception as exc:
        logger.error(f"DB read error: {exc}")
        return pd.DataFrame()


def _check_db() -> bool:
    """Return True if the SQLAlchemy engine can reach the database."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _check_model() -> bool:
    """Return True if the best_model.joblib bundle exists on disk."""
    return (Path(__file__).parent.parent / "models" / "best_model.joblib").exists()


# ── Analysis pipeline (sync — runs in thread pool) ────────────────────────────

def _analyze_sync(req: AnalyzeRequest) -> AnalyzeResponse:
    """Synchronous analysis pipeline executed in _AGENT_POOL.

    Keeps the FastAPI event loop free during the potentially long agent calls.

    Args:
        req: Analysis request with machine_id and feature flags.

    Returns:
        Populated AnalyzeResponse.
    """
    t0 = time.perf_counter()
    mid = req.machine_id.value  # plain str for internal functions
    logger.info(f"[thread] /analyze machine={mid}")
    try:
        from src.models.predict import predict
        results = predict(machine_id=mid, limit=100, save_to_db=True)
    except FileNotFoundError:
        raise HTTPException(503, "Model not loaded — run `make train` first.")
    except Exception as e:
        raise HTTPException(500, str(e))
    if results.empty:
        raise HTTPException(404, f"No data for {mid}")

    latest = results.sort_values("timestamp").iloc[-1]
    data: dict = {
        "machine_id":    mid,
        "timestamp":     str(latest.get("timestamp", datetime.now().isoformat())),
        "anomaly_score": float(latest.get("anomaly_score", 0.0)),
        "severity":      str(latest.get("severity", "NORMAL")),
        "processing_ms": 0.0,
    }
    if req.use_agent:
        try:
            from src.agents.detection_agent import analyze_machine
            dec = analyze_machine(mid)
            data.update({
                "diagnosis":          dec.diagnosis,
                "recommended_action": dec.recommended_action,
                "confidence":         dec.confidence,
            })
            if req.run_judge:
                from src.agents.judge_agent import judge_decision
                ev = judge_decision(
                    {"machine_id": mid},
                    {"anomaly_score": data["anomaly_score"]},
                    dec.model_dump(),
                )
                data.update({"judge_score": ev.global_score, "judge_agreement": ev.agreement})
        except Exception as e:
            logger.warning(f"Agent/Judge skipped: {e}")
    data["processing_ms"] = (time.perf_counter() - t0) * 1000
    return AnalyzeResponse(**data)


# ── Core Endpoints ────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health() -> dict:
    """Public health-check — no auth required.

    Returns db connectivity, model availability, and a UTC timestamp.
    Used by Docker HEALTHCHECK and monitoring tools.
    """
    db_ok    = False
    model_ok = False
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass
    # Use the same helper as /api/summary so both report the real bundle file
    # (models/best_model.joblib) — the previous glob("*.pkl") never matched the
    # .joblib bundle and always reported model_loaded=false.
    model_ok = _check_model()
    return {
        "status":      "ok",
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "db_connected": db_ok,
        "model_loaded": model_ok,
    }


@app.post("/analyze", response_model=AnalyzeResponse, tags=["Detection"])
async def analyze(req: AnalyzeRequest, _key: str = Depends(verify_api_key)) -> AnalyzeResponse:
    """Trigger full detection + agent + judge pipeline (non-blocking)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_AGENT_POOL, _analyze_sync, req)


@app.get("/decisions", response_model=list[DecisionRecord], tags=["Decisions"])
async def get_decisions(
    machine_id: Optional[MachineId] = Query(None),
    limit:      int                 = Query(50, ge=1, le=500),
    severity:   Optional[str]       = Query(None, pattern="^(NORMAL|WARNING|CRITICAL)$"),
    _key: str = Depends(verify_api_key),
) -> list[DecisionRecord]:
    """Query recent ML decisions."""
    sql    = "SELECT * FROM ml_decisions WHERE 1=1"
    params: dict = {"limit": limit}
    if machine_id: sql += " AND machine_id=:mid"; params["mid"] = machine_id.value
    if severity:   sql += " AND severity=:sev";   params["sev"] = severity
    sql += " ORDER BY created_at DESC LIMIT :limit"
    try:
        with get_engine().connect() as conn:
            df = pd.read_sql(text(sql), conn, params=params)
    except Exception as e:
        raise HTTPException(500, str(e))
    return [] if df.empty else [DecisionRecord(**r) for r in df.to_dict(orient="records")]


@app.get("/governance-metrics", response_model=GovernanceMetrics, tags=["Governance"])
async def governance_metrics(
    window: str = Query("24h", pattern="^(1h|24h|7d)$"),
    _key: str = Depends(verify_api_key),
) -> GovernanceMetrics:
    """Governance + compliance metrics for a time window."""
    try:
        from src.governance.governance import compute_metrics
        m = compute_metrics(window=window)
        return GovernanceMetrics(**{k: v for k, v in m.items() if k != "per_machine"})
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/drift", tags=["Dashboard"])
async def get_drift(_key: str = Depends(verify_api_key)) -> dict:
    """Run drift detection -- PSI + KS test on recent vs. historical anomaly scores."""
    try:
        from src.models.drift_detector import check_drift
        return check_drift()
    except Exception as e:
        logger.error(f"Drift check failed: {e}")
        raise HTTPException(500, f"Drift check failed: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("API_PORT", 8000)))
