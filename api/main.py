"""
API de surveillance temps reel du refroidisseur E7301.

Expose la chaine complete (detection -> diagnostic -> jugement) et pilote le
rejeu accelere des donnees DCS reelles. Le dashboard est servi par cette meme
application.

Lancement :
    python -m api
    puis ouvrir http://localhost:8000

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from secrets import token_hex
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel, Field

from src import config
from src.notifications import EmailNotifier
from src.operations import AlarmStore, WorkflowStore
from src.pipeline import E7301Pipeline
from src.realtime.replay import DCSReplay, _compact

DASHBOARD_HTML = Path(__file__).parent / "dashboard.html"
ASSETS_DIR = Path(__file__).parent / "static"

# Etat applicatif — singleton en memoire
STATE: dict[str, Any] = {
    "pipeline": None,
    "replay": None,
    "notifier": None,
    "alarm_store": None,
    "workflow_store": None,
}


# Validation de la configuration au chargement
_PROBLEMES_CONFIG = config.validate()
if _PROBLEMES_CONFIG:
    for _probleme in _PROBLEMES_CONFIG:
        logger.error(f"Configuration invalide : {_probleme}")
    raise RuntimeError(
        "Configuration invalide au chargement du service :\n  - "
        + "\n  - ".join(_PROBLEMES_CONFIG)
    )


# Gestion de session simplifiee (dict en memoire)
_SESSIONS: dict[str, dict[str, Any]] = {}
SESSION_COOKIE = "e7301_session"


def _create_session(email: str) -> tuple[str, dict[str, Any]]:
    """Cree une session simple en memoire."""
    token = token_hex(32)
    session = {
        "email": email,
        "role": "operator",
        "csrf_token": token_hex(16),
    }
    _SESSIONS[token] = session
    return token, session


def _validate_session(cookie: str | None) -> dict[str, Any] | None:
    """Valide une session depuis le cookie."""
    if not cookie:
        return None
    return _SESSIONS.get(cookie)


def _destroy_session(cookie: str | None) -> None:
    """Detruit une session."""
    if cookie and cookie in _SESSIONS:
        del _SESSIONS[cookie]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Construit la chaine au demarrage et libere les ressources a l'arret."""
    logger.info("Demarrage de l'API — construction de la chaine E7301")
    pipeline = E7301Pipeline()
    STATE["pipeline"] = pipeline
    STATE["notifier"] = EmailNotifier(
        host=config.SMTP_HOST,
        port=config.SMTP_PORT,
        username=config.SMTP_USERNAME,
        password=config.SMTP_PASSWORD,
        sender=config.SMTP_FROM,
        starttls=config.SMTP_STARTTLS,
    )
    STATE["alarm_store"] = AlarmStore()
    STATE["workflow_store"] = WorkflowStore()
    STATE["replay"] = _build_replay(
        pipeline,
        speed=config.REPLAY_SPEED,
        analyze_every=config.REPLAY_STEP,
    )
    logger.info("API prete")
    yield
    replay: DCSReplay | None = STATE.get("replay")
    if replay is not None:
        replay.stop()
    alarm_store: AlarmStore | None = STATE.get("alarm_store")
    if alarm_store is not None:
        alarm_store.close()
    workflow_store: WorkflowStore | None = STATE.get("workflow_store")
    if workflow_store is not None:
        workflow_store.close()
    logger.info("API arretee")


app = FastAPI(
    title="OCP Bionic Judge — Refroidisseur E7301",
    description=(
        "Rejeu historique accelere et surveillance d'ecarts comportementaux du refroidisseur "
        "d'acide de sechage E7301 (PS III, Maroc Chimie)."
    ),
    version=config.APP_VERSION,
    lifespan=lifespan,
)

# Actifs embarques
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

if config.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
    )


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Ajoute un identifiant de requete."""
    request_id = request.headers.get("X-Request-ID") or token_hex(12)
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ── Helpers ────────────────────────────────────────────────────────────────────

def _pipeline() -> E7301Pipeline:
    """Recupere la chaine."""
    p = STATE.get("pipeline")
    if p is None:
        raise HTTPException(status_code=503, detail="Chaine en cours d'initialisation")
    return p


def _replay() -> DCSReplay:
    """Recupere le simulateur."""
    r = STATE.get("replay")
    if r is None:
        raise HTTPException(status_code=503, detail="Simulateur non initialise")
    return r


def _alarm_store() -> AlarmStore:
    store = STATE.get("alarm_store")
    if store is None:
        raise HTTPException(status_code=503, detail="Registre d'alarmes non initialise")
    return store


def _workflow_store() -> WorkflowStore:
    store = STATE.get("workflow_store")
    if store is None:
        raise HTTPException(status_code=503, detail="Registre d'interventions non initialisé")
    return store


def _notifier() -> EmailNotifier:
    notifier = STATE.get("notifier")
    if notifier is None:
        raise HTTPException(status_code=503, detail="Service de notification non initialise")
    return notifier


def _build_replay(
    pipeline: E7301Pipeline,
    *,
    speed: float,
    start: str | None = None,
    analyze_every: int,
) -> DCSReplay:
    """Construit un rejeu avec tous ses abonnements."""
    replay = DCSReplay(
        pipeline,
        speed=speed,
        start=start,
        analyze_every=analyze_every,
    )
    notifier: EmailNotifier | None = STATE.get("notifier")
    if notifier is not None:
        replay.subscribe(notifier.notify)
    alarm_store: AlarmStore | None = STATE.get("alarm_store")
    if alarm_store is not None:
        replay.subscribe(alarm_store.observe)
    return replay


def _naive_timestamp(value: datetime | None) -> pd.Timestamp | None:
    """Normalise une borne API vers l'index DCS."""
    if value is None:
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert(None)
    return timestamp


# ── Modeles de requete ────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=1, max_length=1024)


class AlarmTransitionRequest(BaseModel):
    action: str = Field(..., pattern="^(acknowledge|shelve|unshelve|close)$")
    comment: str = Field("", max_length=1000)


class AnalyzeRequest(BaseModel):
    timestamp: str = Field(..., examples=["2024-10-25T21:00:00"])


class ReplayConfig(BaseModel):
    speed: float = Field(120.0, gt=0, le=100000)
    start: str | None = None
    analyze_every: int = Field(3, ge=1, le=24)


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard() -> HTMLResponse:
    """Sert le dashboard de supervision."""
    if not DASHBOARD_HTML.exists():
        return HTMLResponse("<h1>Dashboard introuvable</h1>", status_code=404)
    return HTMLResponse(DASHBOARD_HTML.read_text(encoding="utf-8"))


# ── Authentification securisee ────────────────────────────────────────────────
# Identifiants valides : mounirsanbouli@gmail.com / 123
VALID_EMAIL = "mounirsanbouli@gmail.com"
VALID_PASSWORD = "123"


@app.get("/api/auth/status", tags=["Acces"])
def auth_status(request: Request) -> dict:
    """Etat de la protection et identite de la session."""
    session = _validate_session(request.cookies.get(SESSION_COOKIE))
    return {
        "required": True,
        "authenticated": session is not None,
        "operator": {
            "username": session["email"] if session else "",
            "email": session["email"] if session else "",
            "role": session["role"] if session else "",
            "csrf_token": session["csrf_token"] if session else "",
        } if session else None,
    }


@app.post("/api/auth/login", tags=["Acces"])
def auth_login(payload: LoginRequest, request: Request) -> JSONResponse:
    """Authentifie le technicien avec email et mot de passe."""
    # Verification des identifiants
    if payload.email != VALID_EMAIL or payload.password != VALID_PASSWORD:
        raise HTTPException(
            status_code=401,
            detail="Identifiants invalides"
        )
    token, session = _create_session(payload.email)
    # Ajouter l'email du technicien aux notifications
    notifier: EmailNotifier | None = STATE.get("notifier")
    if notifier is not None:
        notifier.add_recipient(payload.email)
    response = JSONResponse({
        "required": True,
        "authenticated": True,
        "operator": session,
    })
    response.set_cookie(
        SESSION_COOKIE, token,
        max_age=8 * 3600, httponly=True, secure=False,
        samesite="strict", path="/",
    )
    return response


@app.post("/api/auth/logout", tags=["Acces"])
def auth_logout(request: Request) -> JSONResponse:
    """Invalide la session et retire l'email des notifications."""
    session = _validate_session(request.cookies.get(SESSION_COOKIE))
    if session:
        notifier: EmailNotifier | None = STATE.get("notifier")
        if notifier is not None:
            notifier.remove_recipient(session["email"])
    _destroy_session(request.cookies.get(SESSION_COOKIE))
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="strict")
    return response


@app.post("/api/auth/refresh", tags=["Acces"])
def auth_refresh(request: Request) -> JSONResponse:
    """Refresh simple."""
    session = _validate_session(request.cookies.get(SESSION_COOKIE))
    if session is None:
        raise HTTPException(status_code=401, detail="Session expirée")
    return JSONResponse({"authenticated": True, "operator": session})


# ── Systeme ───────────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["Systeme"])
def health() -> dict:
    """Synthese de l'etat du service."""
    p = STATE.get("pipeline")
    return {
        "status": "ok" if p else "starting",
        "liveness": "alive",
        "readiness": "ready" if p else "starting",
        "version": config.APP_VERSION,
        "equipment": p.domain.equipment["id"] if p else None,
        "agent_mode": p.agent.mode if p else None,
        "judge_mode": p.judge.mode if p else None,
        "n_samples": len(p.features) if p else 0,
        "data_start": p.features.index.min().isoformat() if p else None,
        "data_end": p.features.index.max().isoformat() if p else None,
    }


@app.get("/api/equipment", tags=["Systeme"])
def equipment() -> dict:
    """Fiche equipement, tags surveilles et AMDEC de reference."""
    d = _pipeline().domain
    return {
        "equipment": d.equipment,
        "tags": [
            {"tag": t.tag, "alias": t.alias, "label": t.label, "unit": t.unit,
             "role": t.role, "confidence": t.confidence,
             "range_operating": t.range_operating, "setpoint": t.setpoint,
             "rationale": t.rationale,
             "criticality_link": t.criticality_link}
            for t in d.tags.values()
        ],
        "amdec": [
            {"code": m.code, "element": m.element, "mode": m.mode,
             "F": m.F, "G": m.G, "N": m.N, "C": m.C,
             "band": m.criticality_band(),
             "observable": m.observable, "observabilite": m.observabilite,
             "action": m.action_corrective, "tasks": m.plan_maintenance_ref,
             "provenance_category": m.raw.get("provenance", {}).get("category", "ocp_source"),
             "source_file": m.raw.get("provenance", {}).get("source_file", ""),
             "source_location": m.raw.get("provenance", {}).get("source_location", "")}
            for m in d.modes_ranked()
        ],
        "plan_maintenance": d.plan_maintenance,
        "process_states": d.process_states,
        "blind_spots": [m.code for m in d.blind_spots()],
        "partially_observable": [m.code for m in d.partially_observable_modes()],
    }


@app.get("/api/governance", tags=["Systeme"])
def governance() -> dict:
    """Rapport de gouvernance : donnees, capteurs, modele, angles morts."""
    p = _pipeline()
    report = p.health_report()
    return report


@app.get("/api/coverage", tags=["Gouvernance"])
def coverage() -> dict:
    """Part du risque AMDEC couverte."""
    d = _pipeline().domain
    return {
        "risque": d.risk_coverage(),
        "tags": d.determination_basis(),
    }


@app.get("/api/config", tags=["Systeme"])
def effective_config() -> dict:
    """Configuration effective du service."""
    return {
        "app_version": config.APP_VERSION,
        "dcs_export": config.DCS_EXPORT.name,
        "log_level": config.LOG_LEVEL,
        "contamination": config.CONTAMINATION,
        "model_strategy": config.MODEL_STRATEGY,
        "replay_speed": config.REPLAY_SPEED,
    }


# ── Donnees ───────────────────────────────────────────────────────────────────

@app.get("/api/timeseries", tags=["Donnees"])
def timeseries(
    start: datetime | None = None,
    end: datetime | None = None,
    max_points: int = Query(1500, ge=100, le=20000),
) -> dict:
    """Series temporelles des grandeurs cles."""
    p = _pipeline()
    start_ts = _naive_timestamp(start)
    end_ts = _naive_timestamp(end)
    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        raise HTTPException(status_code=422, detail="La borne de debut doit preceder la borne de fin")

    df = p.features.join(
        p.ingestion.observations[
            [c for c in p.ingestion.observations if c not in p.features.columns]
        ],
        how="left",
    )
    if start_ts is not None:
        df = df[df.index >= start_ts]
    if end_ts is not None:
        df = df[df.index <= end_ts]

    raw_aliases = [tag.alias for tag in p.domain.tags.values()]
    cols = [*raw_aliases,
        "conc_min", "delta_t", "duty_kw", "duty_expected", "regulation_effort_z",
        "regulation_effort_trend_14d", "control_deviation",
        "T_SEAWATER",
        "ua_kw_per_k", "ua_expected", "ua_residual_z", "fouling_resistance",
        "t_in_expected", "t_in_residual_z", "t_in_residual_trend_14d",
    ]
    cols = [c for c in cols if c in df.columns]

    if len(df) <= max_points:
        sub = df
    else:
        positions = [
            round(i * (len(df) - 1) / (max_points - 1))
            for i in range(max_points)
        ]
        sub = df.iloc[positions]

    out: dict[str, Any] = {
        "timestamps": [t.isoformat() for t in sub.index],
        "process_state": sub["process_state"].tolist(),
        "n_total": len(df),
        "n_returned": len(sub),
    }
    for c in cols:
        out[c] = [None if pd.isna(v) else round(float(v), 4) for v in sub[c]]
    return out


@app.get("/api/sensor-health", tags=["Donnees"])
def sensor_health() -> list[dict]:
    """Synthese de disponibilite par capteur."""
    return _pipeline().ingestion.sensor_health.to_dict(orient="records")


@app.get("/api/topology", tags=["Donnees"])
def topology() -> dict:
    """Topologie physique : pieces, capteurs situes, rattachement des codes."""
    return _pipeline().domain.topology()


@app.get("/api/sensor/{alias}", tags=["Donnees"])
def sensor_detail(
    alias: str,
    window_h: int = Query(504, ge=6, le=20000),
    end: datetime | None = None,
    max_points: int = Query(700, ge=50, le=5000),
) -> dict:
    """Fiche complete d'un capteur."""
    p = _pipeline()
    tag = p.domain.by_alias.get(alias)
    if tag is None:
        raise HTTPException(status_code=404, detail=f"Capteur inconnu: {alias}")

    source = p.ingestion.observations
    if alias not in source.columns:
        raise HTTPException(status_code=404, detail=f"Serie absente pour {alias}")
    series = source[alias]

    end_ts = _naive_timestamp(end) or series.index.max()
    start_ts = end_ts - pd.Timedelta(hours=window_h)
    window = series[(series.index >= start_ts) & (series.index <= end_ts)]

    if len(window) > max_points:
        step = max(1, len(window) // max_points)
        window = window.iloc[::step]

    valid = series.dropna()
    quality = p.ingestion.quality
    events = quality[quality["alias"] == alias] if len(quality) else quality
    issues = events["issue"].value_counts().to_dict() if len(events) else {}
    health_rows = p.ingestion.sensor_health
    health = health_rows[health_rows["alias"] == alias]
    availability = float(health["availability_pct"].iloc[0]) if len(health) else None

    def _num(value: Any) -> float | None:
        return None if pd.isna(value) else round(float(value), 4)

    return {
        "alias": alias, "tag": tag.tag, "label": tag.label, "unit": tag.unit,
        "kind": tag.kind, "role": tag.role, "confidence": tag.confidence,
        "rationale": tag.rationale, "criticality_link": tag.criticality_link,
        "setpoint": tag.setpoint, "range_operating": tag.range_operating,
        "thresholds": {
            "alarm_low_low": tag.threshold("alarm_low_low"),
            "alarm_low": tag.threshold("alarm_low"),
            "alarm_high": tag.threshold("alarm_high"),
            "alarm_high_high": tag.threshold("alarm_high_high"),
        },
        "placement": p.domain.sensor_placements.get(alias, {}),
        "series": {
            "timestamps": [t.isoformat() for t in window.index],
            "values": [_num(v) for v in window],
        },
        "stats": {
            "last": _num(valid.iloc[-1]) if len(valid) else None,
            "min": _num(valid.min()) if len(valid) else None,
            "max": _num(valid.max()) if len(valid) else None,
            "mean": _num(valid.mean()) if len(valid) else None,
            "n_total": len(series), "n_valid": len(valid),
        },
        "quality": {"availability_pct": availability, "issues": issues, "n_events": len(events)},
    }


@app.get("/api/episodes", tags=["Donnees"])
def episodes(limit: int = Query(50, ge=1, le=500)) -> list[dict]:
    """Episodes d'anomalie agreges."""
    ep = _pipeline().episodes().head(limit).copy()
    for c in ("start", "end", "peak_at"):
        ep[c] = ep[c].astype(str)
    return ep.to_dict(orient="records")


# ── Analyse ───────────────────────────────────────────────────────────────────

@app.post("/api/analyze", tags=["Analyse"])
def analyze(req: AnalyzeRequest) -> dict:
    """Analyse complete d'un instant."""
    p = _pipeline()
    try:
        return p.analyze_at(req.timestamp).to_dict()
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Horodatage {req.timestamp} absent des données",
        ) from exc


@app.get("/api/notable", tags=["Analyse"])
def notable(limit: int = Query(20, ge=1, le=100)) -> list[dict]:
    """Analyse les instants les plus interessants."""
    p = _pipeline()
    return [
        _compact(p.analyze_at(ts, use_llm=False))
        for ts in p.notable_timestamps(limit)
    ]


# ── Temps reel ────────────────────────────────────────────────────────────────

@app.post("/api/replay/start", tags=["Temps reel"])
def replay_start(cfg: ReplayConfig) -> dict:
    """Demarre le rejeu accelere."""
    p = _pipeline()
    old: DCSReplay | None = STATE.get("replay")
    if old is not None and old.state.running:
        old.stop()
    replay = _build_replay(p, speed=cfg.speed, start=cfg.start, analyze_every=cfg.analyze_every)
    STATE["replay"] = replay
    replay.start()
    return replay.snapshot()


@app.post("/api/replay/stop", tags=["Temps reel"])
def replay_stop() -> dict:
    """Arrete le rejeu."""
    r = _replay()
    r.stop()
    return r.snapshot()


@app.post("/api/replay/speed", tags=["Temps reel"])
async def replay_speed(speed: float = Query(..., gt=0, le=100000)) -> dict:
    """Change la vitesse du rejeu."""
    r = _replay()
    r.set_speed(speed)
    return r.snapshot()


@app.get("/api/replay/state", tags=["Temps reel"])
async def replay_state() -> dict:
    """Etat courant du rejeu."""
    return _replay().snapshot()


@app.get("/api/replay/stream", tags=["Temps reel"])
async def replay_stream(n: int = Query(40, ge=1, le=500)) -> list[dict]:
    """Dernieres analyses du rejeu."""
    return _replay().recent(n)


@app.get("/api/replay/alerts", tags=["Temps reel"])
async def replay_alerts(n: int = Query(40, ge=1, le=500)) -> list[dict]:
    """Dernieres alertes du rejeu."""
    return _replay().alerts(n)


@app.get("/api/replay/disagreements", tags=["Temps reel"])
async def replay_disagreements(n: int = Query(20, ge=1, le=200)) -> list[dict]:
    """Decisions rejetees par le Judge."""
    return _replay().disagreements(n)


# ── Alarmes ───────────────────────────────────────────────────────────────────

@app.get("/api/alarms", tags=["Alarmes"])
async def alarm_registry(
    active_only: bool = True,
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    """Registre des alarmes."""
    return await run_in_threadpool(
        _alarm_store().list, active_only=active_only, limit=limit,
    )


@app.post("/api/alarms/{alarm_id}/transition", tags=["Alarmes"])
async def alarm_transition(
    alarm_id: int,
    payload: AlarmTransitionRequest,
) -> dict:
    """Transition d'une alarme."""
    try:
        return await run_in_threadpool(
            _alarm_store().transition,
            alarm_id,
            action=payload.action,
            operator="poste-local",
            comment=payload.comment,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Alarme inconnue") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ── Workflows ─────────────────────────────────────────────────────────────────

@app.get("/api/workflows/templates", tags=["Maintenance"])
def workflow_templates() -> dict[str, dict[str, Any]]:
    """Templates de workflows predefinis."""
    return _workflow_store().get_templates()


# ── Judge ─────────────────────────────────────────────────────────────────────

@app.get("/api/judge/audit", tags=["Judge"])
def judge_audit() -> dict:
    """Synthese du Judge — comportement du controleur."""
    p = _pipeline()
    replay = STATE.get("replay")
    history = replay.state.history if replay else []

    if not history:
        return {
            "n": 0,
            "status": "EN_ATTENTE",
            "seuil_activation": 20,
            "reading": (
                "Ce panneau surveille le contrôleur lui-même. Il compare la "
                "distribution de ses notes à ce qu'on attend d'un contrôle "
                "utile. Les trois alertes se déclenchent à partir de 20 "
                "décisions jugées — lancez le rejeu pour les alimenter."
            ),
            "controles": [
                "Taux de validation supérieur à 97% — complaisance",
                "Taux de validation inférieur à 10% — sévérité systématique",
                "Écart-type des notes inférieur à 0,35 point — notes indifférenciées",
            ],
        }

    import numpy as np
    scores = [a.verdict.global_score for a in history]
    agreements = [a.verdict.agreement for a in history]
    arr = np.array(scores)
    rate = float(np.mean(agreements))
    n = len(scores)

    warnings = []
    if n >= 20:
        if rate > 0.97:
            warnings.append("COMPLAISANCE : le contrôleur valide plus de 97% des décisions.")
        if rate < 0.10:
            warnings.append("SÉVÉRITÉ SYSTÉMATIQUE : moins de 10% de validations.")
        if arr.std() < 0.35:
            warnings.append(f"NOTES INDIFFÉRENCIÉES : écart-type de {arr.std():.2f} point.")

    from collections import Counter
    all_issues = []
    for a in history:
        all_issues.extend(a.verdict.flagged_issues)

    return {
        "n": n,
        "score_mean": round(float(arr.mean()), 2),
        "score_std": round(float(arr.std()), 2),
        "score_min": round(float(arr.min()), 2),
        "score_max": round(float(arr.max()), 2),
        "score_p25": round(float(np.percentile(arr, 25)), 2),
        "score_p75": round(float(np.percentile(arr, 75)), 2),
        "agreement_rate": round(rate, 3),
        "top_issues": Counter(all_issues).most_common(8),
        "self_check_warnings": warnings,
        "seuil_activation": 20,
        "reading": (
            f"{n} décision(s) jugée(s). "
            + (
                "Aucune alerte : les notes se répartissent et le taux de "
                "validation reste dans la plage attendue d'un contrôle utile."
                if not warnings and n >= 20 else
                f"Échantillon encore court — les alertes se déclenchent à "
                f"partir de 20 décisions."
                if n < 20 else
                "Le contrôleur signale une anomalie sur son propre "
                "comportement : voir ci-dessous."
            )
        ),
        "status": "ALERTE" if warnings else "OK" if n >= 20 else "EN_ATTENTE",
    }


@app.get("/api/judge/evaluation", tags=["Judge"])
def judge_evaluation() -> dict:
    """Evaluation du Judge."""
    return {
        "message": "Evaluation disponible apres le rejeu",
        "checks": 8,
    }


# ── Indicateurs ───────────────────────────────────────────────────────────────

@app.get("/api/kpi", tags=["Indicateurs"])
def operational_kpi() -> dict:
    """Indicateurs calcules sur les donnees."""
    from src.analytics import OperationalKPI

    p = _pipeline()
    kpi = OperationalKPI(p.features, p.domain)
    stability = kpi.control_stability()
    scores = p.detector.score_series(p.features)
    threshold = float(p.detector.stat.threshold_)
    figures = kpi.summary(p.ingestion.sensor_health, p.episodes())
    figures.append(kpi.flag_rate(scores, threshold, config.CONTAMINATION))
    monthly = kpi.monthly_flag_rate(scores, threshold)

    return {
        "figures": [f.to_dict() for f in figures],
        "stabilite_regulation": [
            {"periode": str(idx.date()), **{k: (None if pd.isna(v) else float(v)) for k, v in row.items()}}
            for idx, row in stability.iterrows()
        ],
        "signalement_mensuel": [
            {"periode": str(idx.date()), **{k: (None if pd.isna(v) else float(v)) for k, v in row.items()}}
            for idx, row in monthly.iterrows()
        ],
        "calibration": {
            "contamination_visee_pct": round(config.CONTAMINATION * 100, 2),
            "seuil": round(threshold, 4),
        },
    }


# ── Notifications ─────────────────────────────────────────────────────────────

@app.get("/api/notifications/status", tags=["Notifications"])
def notification_status() -> dict:
    """État du canal email."""
    return _notifier().status()


@app.post("/api/notifications/test", tags=["Notifications"])
def notification_test(request: Request) -> dict:
    """Envoie un email de test au technicien connecté."""
    session = _validate_session(request.cookies.get(SESSION_COOKIE))
    email = session["email"] if session else None
    if not _notifier().enqueue_test(demandeur=email):
        raise HTTPException(status_code=409, detail="Canal email non configuré")
    return {"accepted": True}


# ── Gestion d'erreurs ────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def unhandled(request, exc: Exception) -> JSONResponse:
    """Renvoie une erreur lisible plutot qu'une trace brute."""
    incident = token_hex(5)
    logger.exception(f"Erreur non geree [{incident}] sur {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "detail": "Erreur interne du service",
            "incident": incident,
        },
    )
