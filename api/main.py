"""
API de surveillance temps reel du refroidisseur E7301.

Expose la chaine complete (detection -> diagnostic -> jugement) et pilote le
rejeu accelere des donnees DCS reelles. Le dashboard est servi par cette meme
application : aucune etape de build, aucun serveur supplementaire a lancer
pour la demonstration.

Lancement :
    uvicorn api.main:app --reload --port 8000
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
from src.security import AuthManager, TooManyAttemptsError
from src.security.registry import load_registry

DASHBOARD_HTML = Path(__file__).parent / "dashboard.html"
ASSETS_DIR = Path(__file__).parent / "static"

# Etat applicatif. Volontairement un singleton en memoire : le systeme surveille
# UN equipement, sur un historique fini. Une base de donnees n'apporterait rien
# ici et masquerait la logique metier derriere de la plomberie.
STATE: dict[str, Any] = {
    "pipeline": None,
    "replay": None,
    "notifier": None,
    "alarm_store": None,
    "workflow_store": None,
}


# Adresses ayant explicitement demande a NE PAS recevoir les alertes
# critiques. Renseigne au demarrage depuis le registre; vide si l'acces
# protege est desactive. Voir `auth_login`.
OPT_OUT_ALERTES: set[str] = set()


def _build_auth_manager() -> AuthManager | None:
    """Construit la gestion de session a partir des identifiants disponibles.

    Deux sources, dans cet ordre de preference :

      1. le REGISTRE LOCAL, un mot de passe par technicien. C'est le mode
         attendu des lors que l'adresse de session determine le destinataire
         des alertes critiques : un secret partage ne permettrait pas de dire
         qui a ouvert la session ni de revoquer un depart.
      2. l'empreinte PARTAGEE `AUTH_PASSWORD_HASH`, conservee pour les
         deploiements existants.

    Returns:
        AuthManager, ou None si l'acces protege est desactive.
    """
    if not config.AUTH_ENABLED:
        return None

    registry = load_registry()
    # `alert_recipient` ETAIT UN DRAPEAU MORT. Le registre le stockait, la
    # commande `manage_operators add --no-alerts` le posait, un test verifiait
    # l'accesseur — et personne ne l'interrogeait. `auth_login` abonnait
    # inconditionnellement l'adresse de session aux alertes critiques : un
    # technicien enregistre en lecture seule, explicitement exclu des
    # escalades, etait reveille la nuit des qu'il ouvrait une session.
    OPT_OUT_ALERTES.clear()
    OPT_OUT_ALERTES.update(registry.emails() - registry.alert_recipients())
    if OPT_OUT_ALERTES:
        logger.info(
            f"{len(OPT_OUT_ALERTES)} technicien(s) exclu(s) des escalades "
            f"par le registre"
        )
    if registry.is_configured:
        logger.info(
            f"Acces protege — {len(registry)} technicien(s) enregistre(s) dans "
            f"{registry.path}"
        )
        return AuthManager(
            idle_timeout_s=config.AUTH_IDLE_MINUTES * 60,
            absolute_timeout_s=config.AUTH_ABSOLUTE_HOURS * 3600,
            user_hashes=registry.password_hashes(),
            user_roles=registry.roles(),
        )

    logger.warning(
        "Acces protege par empreinte partagee : preferer un compte par "
        "technicien (`python scripts/manage_operators.py add`)"
    )
    return AuthManager(
        password_hash=config.AUTH_PASSWORD_HASH,
        idle_timeout_s=config.AUTH_IDLE_MINUTES * 60,
        absolute_timeout_s=config.AUTH_ABSOLUTE_HOURS * 3600,
        allowed_emails=config.AUTH_ALLOWED_EMAILS,
        user_roles=config.AUTH_USER_ROLES,
    )


# LA CONFIGURATION EST VALIDEE AVANT TOUT EFFET DE BORD DU MODULE.
#
# Elle ne l'etait qu'au demarrage du `lifespan`, c'est-a-dire APRES la
# construction de la gestion de session, APRES la lecture du registre des
# techniciens et APRES le montage du middleware CORS — tous trois pilotes par
# cette meme configuration. Un lancement direct par `uvicorn api.main:app`,
# forme documentee dans l'en-tete de ce fichier, contournait donc entierement
# le refus propre implemente dans `api/__main__.py` : la premiere erreur
# visible etait une trace d'import, pas le message de configuration.
_PROBLEMES_CONFIG = config.validate()
if _PROBLEMES_CONFIG:
    for _probleme in _PROBLEMES_CONFIG:
        logger.error(f"Configuration invalide : {_probleme}")
    raise RuntimeError(
        "Configuration invalide au chargement du service :\n  - "
        + "\n  - ".join(_PROBLEMES_CONFIG)
    )

AUTH_MANAGER = _build_auth_manager()
SESSION_COOKIE = "e7301_session"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Construit la chaine au demarrage et libere les ressources a l'arret.

    Args:
        app: Application FastAPI.

    Yields:
        None.
    """
    # La configuration a deja ete validee au chargement du module, avant la
    # construction de la gestion de session et le montage du middleware CORS.
    logger.info("Demarrage de l'API — construction de la chaine E7301")
    pipeline = E7301Pipeline(use_llm=True)
    STATE["pipeline"] = pipeline
    notifier = EmailNotifier(
        host=config.SMTP_HOST,
        port=config.SMTP_PORT,
        username=config.SMTP_USERNAME,
        password=config.SMTP_PASSWORD,
        sender=config.SMTP_FROM,
        recipient=config.ALERT_EMAIL_TO,
        starttls=config.SMTP_STARTTLS,
        cooldown_minutes=config.ALERT_COOLDOWN_MINUTES,
        minimum_severity=config.ALERT_MIN_SEVERITY,
        spool=config.ALERT_SPOOL,
    )
    STATE["notifier"] = notifier
    STATE["alarm_store"] = AlarmStore(config.ALARM_DB)
    STATE["workflow_store"] = WorkflowStore(config.WORKFLOW_DB)
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
    notifier = STATE.get("notifier")
    if notifier is not None:
        notifier.stop()
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
        "Rejeu historique accelere et surveillance d'écarts comportementaux du refroidisseur "
        "d'acide de sechage E7301 (PS III, Maroc Chimie). Detection hybride "
        "regles applicatives + modele statistique non supervisé, diagnostic suspecté, "
        "puis contrôle de cohérence interne. Aucune panne n'est confirmée."
    ),
    version=config.APP_VERSION,
    lifespan=lifespan,
)

# Actifs embarques : le dashboard doit rester exploitable sur un reseau
# industriel isole, sans appel a un CDN public.
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

# Le dashboard est servi par cette meme application : aucune requete
# inter-origine n'est necessaire par defaut. On n'ouvre que si un front
# separe est explicitement declare dans la configuration.
if config.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
    )


def _durcir(response, request: Request, request_id: str):
    """Pose les en-tetes de defense sur TOUTE reponse, refus compris.

    LES REFUS N'EN AVAIENT AUCUN. Le middleware retournait directement la
    reponse 401 ou 403, sautant le bloc d'en-tetes place apres `call_next` :
    une reponse d'erreur partait donc sans politique de securite du contenu,
    sans `nosniff`, sans `X-Frame-Options` et sans identifiant de requete —
    c'est-a-dire exactement les reponses qu'un attaquant provoque le plus
    facilement, et les seules qu'un exploitant ne peut pas correler a une
    trace serveur.

    Args:
        response: Reponse a durcir.
        request: Requete d'origine, pour le schema et le chemin.
        request_id: Identifiant de correlation.

    Returns:
        La meme reponse, en-tetes poses.
    """
    response.headers["X-Request-ID"] = request_id
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; font-src 'self'; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; "
        "form-action 'self'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    )
    response.headers["Cache-Control"] = (
        "no-store" if request.url.path.startswith("/api/") else "no-cache"
    )
    # HSTS n'est annonce que si HTTPS est reellement utilise : le promettre
    # sur du HTTP local serait trompeur.
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


@app.middleware("http")
async def operator_access(request: Request, call_next):
    """Protège les API quand l'accès opérateur est activé."""
    request_id = request.headers.get("X-Request-ID") or token_hex(12)
    request.state.request_id = request_id
    public = (
        request.url.path == "/"
        or request.url.path.startswith("/assets/")
        or request.url.path == "/api/health"
        or request.url.path.startswith("/api/health/")
        or request.url.path.startswith("/api/auth/")
    )
    session = (
        AUTH_MANAGER.validate(request.cookies.get(SESSION_COOKIE))
        if AUTH_MANAGER else None
    )
    request.state.operator = session
    if config.AUTH_ENABLED and not public and session is None:
        return _durcir(
            JSONResponse(
                status_code=401,
                content={"detail": "Authentification operateur requise"},
            ),
            request,
            request_id,
        )
    if (
        config.AUTH_ENABLED
        and session is not None
        and request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and request.url.path not in {"/api/auth/login", "/api/auth/logout"}
        and request.headers.get("X-CSRF-Token") != session.csrf_token
    ):
        return _durcir(
            JSONResponse(
                status_code=403,
                content={"detail": "Jeton de session invalide"},
            ),
            request,
            request_id,
        )
    response = await call_next(request)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        actor = session.email if session is not None else "poste-local"
        logger.info(
            "audit action={} path={} actor={} role={} request_id={}",
            request.method,
            request.url.path,
            actor,
            session.role if session is not None else "local",
            request_id,
        )
    # Défense en profondeur navigateur, posée par le même point unique que les
    # refus : un seul endroit à relire pour savoir ce que le service annonce.
    return _durcir(response, request, request_id)


def _pipeline() -> E7301Pipeline:
    """Recupere la chaine, ou echoue proprement si elle n'est pas prete.

    Returns:
        La chaine E7301.

    Raises:
        HTTPException: 503 si la chaine n'est pas encore construite.
    """
    p = STATE.get("pipeline")
    if p is None:
        raise HTTPException(status_code=503, detail="Chaine en cours d'initialisation")
    return p


def _replay() -> DCSReplay:
    """Recupere le simulateur de rejeu.

    Returns:
        Le simulateur.

    Raises:
        HTTPException: 503 si le simulateur n'est pas pret.
    """
    r = STATE.get("replay")
    if r is None:
        raise HTTPException(status_code=503, detail="Simulateur non initialise")
    return r


def _notifier() -> EmailNotifier:
    """Récupère le canal email construit au démarrage."""
    notifier = STATE.get("notifier")
    if notifier is None:
        raise HTTPException(
            status_code=503,
            detail="Service de notification non initialise",
        )
    return notifier


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


def _require_roles(request: Request, *roles: str) -> None:
    """Autorise une action sensible selon le rôle résolu côté serveur."""
    session = request.state.operator
    if not config.AUTH_ENABLED:
        return
    if session is None or session.role not in roles:
        raise HTTPException(status_code=403, detail="Rôle insuffisant pour cette action")


def _build_replay(
    pipeline: E7301Pipeline,
    *,
    speed: float,
    start: str | None = None,
    analyze_every: int,
) -> DCSReplay:
    """Construit un rejeu avec tous ses abonnements obligatoires."""
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
    """Normalise une borne API vers l'index DCS sans fuseau horaire."""
    if value is None:
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert(None)
    return timestamp


# ── Règle de déclaration des handlers ────────────────────────────────────────
#
# UN HANDLER EST `async def` UNIQUEMENT S'IL `await`, OU SI SON CORPS SE LIMITE
# A DES LECTURES EN MEMOIRE. Tout ce qui calcule, lit le disque ou sort sur le
# reseau est declare `def` : FastAPI l'execute alors dans son pool de threads.
#
# CE N'ETAIT PAS LE CAS. Trente-deux des quarante-sept handlers etaient
# `async def` sans le moindre `await` : leur corps entier s'executait sur la
# boucle d'evenements, qui est unique. Parmi eux :
#
#   - `auth_login`, dont la derivation PBKDF2 est VOLONTAIREMENT couteuse
#     (600 000 iterations). Chaque tentative de connexion, reussie ou non,
#     gelait tout le service le temps du calcul.
#   - `analyze`, qui appelle le modele de langage. L'appel etait synchrone et
#     sans delai maximal : une reponse lente figeait la supervision entiere,
#     sonde de vivacite comprise — l'orchestrateur finissait par tuer un
#     conteneur en parfait etat.
#   - `notable`, jusqu'a cent analyses completes enchainees.
#   - `timeseries`, `operational_kpi`, `episodes`, qui balayent tout l'historique.
#
# `test_aucun_handler_calculant_ne_reste_sur_la_boucle_d_evenements`
# verrouille la regle. Le nom cite ici etait auparavant celui d'un test
# INEXISTANT — la faute exacte que cet audit corrige ailleurs, commise en la
# corrigeant.
#
# ── Accès opérateur ──────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    """Email de quart et secret d'accès au poste."""

    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=1, max_length=1024)


class AlarmTransitionRequest(BaseModel):
    """Action tracée d'un opérateur sur une alarme."""

    action: str = Field(..., pattern="^(acknowledge|shelve|unshelve|close)$")
    comment: str = Field("", max_length=1000)


class WorkflowCreateRequest(BaseModel):
    """Création d'une exécution depuis un modèle documentaire."""

    template_id: str = Field(
        ..., pattern="^(INSPECTION_EXTERNE|INSPECTION_INTERNE|TAMPONNAGE)$"
    )
    owner: str = Field(..., min_length=2, max_length=254)
    planned_at: str | None = Field(None, max_length=64)


class WorkflowStepRequest(BaseModel):
    """Mise à jour optimiste d'une étape traçable."""

    status: str = Field(
        ..., pattern="^(TODO|IN_PROGRESS|BLOCKED|COMPLETED|NOT_APPLICABLE)$"
    )
    measurement: str = Field("", max_length=500)
    unit: str = Field("", max_length=32)
    comment: str = Field("", max_length=1000)
    proof_ref: str = Field("", max_length=500)
    expected_version: int = Field(..., ge=1)


class WorkflowCompleteRequest(BaseModel):
    """Clôture signée d'une intervention."""

    signature: str = Field(..., min_length=2, max_length=254)
    proof_ref: str = Field("", max_length=500)


@app.get("/api/auth/status", tags=["Acces"])
async def auth_status(request: Request) -> dict:
    """État de la protection et identité de la session courante."""
    session = request.state.operator
    return {
        "required": config.AUTH_ENABLED,
        "authenticated": not config.AUTH_ENABLED or session is not None,
        "operator": (
            session.public()
            if session is not None
            else {
                "username": "Poste local",
                "email": "",
                "role": "local",
                # Champ volontairement vide lorsque la protection est désactivée.
                "csrf_token": "",  # nosec B105
            }
        ) if not config.AUTH_ENABLED or session is not None else None,
    }


@app.post("/api/auth/login", tags=["Acces"])
def auth_login(payload: LoginRequest, request: Request) -> JSONResponse:
    """Ouvre une session HttpOnly après authentification."""
    if AUTH_MANAGER is None:
        return JSONResponse({
            "required": False,
            "authenticated": True,
            "operator": {
                "username": "Poste local",
                "email": "",
                "role": "local",
                # Champ volontairement vide lorsque la protection est désactivée.
                "csrf_token": "",  # nosec B105
            },
        })
    client_key = request.client.host if request.client else "unknown"
    try:
        result = AUTH_MANAGER.authenticate(
            payload.email,
            payload.password,
            client_key,
        )
    except TooManyAttemptsError as exc:
        raise HTTPException(
            status_code=429,
            detail="Trop de tentatives; réessayez ultérieurement",
            headers={"Retry-After": "300"},
        ) from exc
    if result is None:
        raise HTTPException(
            status_code=401,
            detail="Identifiants invalides ou trop de tentatives",
        )
    token, session = result
    notifier: EmailNotifier | None = STATE.get("notifier")
    # Le registre decide qui recoit les escalades, pas le simple fait d'avoir
    # ouvert une session. Voir `OPT_OUT_ALERTES`.
    if notifier is not None and session.email not in OPT_OUT_ALERTES:
        notifier.add_recipient(session.email)
    response = JSONResponse({
        "required": True,
        "authenticated": True,
        "operator": session.public(),
    })
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(config.AUTH_ABSOLUTE_HOURS * 3600),
        httponly=True,
        secure=config.AUTH_SECURE_COOKIE,
        samesite="strict",
        path="/",
    )
    return response


@app.post("/api/auth/refresh", tags=["Acces"])
async def auth_refresh(request: Request) -> JSONResponse:
    """Effectue une rotation explicite du cookie et du jeton CSRF."""
    if AUTH_MANAGER is None:
        raise HTTPException(status_code=409, detail="Authentification locale inactive")
    result = AUTH_MANAGER.rotate(request.cookies.get(SESSION_COOKIE))
    if result is None:
        raise HTTPException(status_code=401, detail="Session expirée")
    token, session = result
    response = JSONResponse({"authenticated": True, "operator": session.public()})
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(config.AUTH_ABSOLUTE_HOURS * 3600),
        httponly=True,
        secure=config.AUTH_SECURE_COOKIE,
        samesite="strict",
        path="/",
    )
    return response


@app.post("/api/auth/logout", tags=["Acces"])
async def auth_logout(request: Request) -> JSONResponse:
    """Invalide la session et supprime son cookie."""
    session = request.state.operator
    notifier: EmailNotifier | None = STATE.get("notifier")
    if notifier is not None and session is not None:
        notifier.remove_recipient(session.email)
    if AUTH_MANAGER is not None:
        AUTH_MANAGER.destroy(request.cookies.get(SESSION_COOKIE))
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="strict")
    return response


@app.get("/api/auth/audit", tags=["Acces"])
async def auth_audit(request: Request, limit: int = Query(100, ge=1, le=500)) -> list[dict]:
    """Journal d'authentification réservé à l'administrateur."""
    _require_roles(request, "administrator")
    return AUTH_MANAGER.audit_events(limit) if AUTH_MANAGER is not None else []


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard() -> HTMLResponse:
    """Sert le dashboard de supervision."""
    if not DASHBOARD_HTML.exists():
        return HTMLResponse("<h1>Dashboard introuvable</h1>", status_code=404)
    return HTMLResponse(DASHBOARD_HTML.read_text(encoding="utf-8"))


# ── Systeme ───────────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["Systeme"])
async def health() -> dict:
    """Synthèse non ambiguë : service disponible ne signifie pas modèle promu."""
    p = STATE.get("pipeline")
    model_promoted = bool(
        p and p.model_promotion_status in config.MODEL_ALLOWED_STATUSES
    )
    return {
        "status": "degraded" if p and not model_promoted else ("ok" if p else "starting"),
        "liveness": "alive",
        "readiness": "ready" if p else "starting",
        "ready_for_demo": bool(p),
        "ready_for_production": bool(p and model_promoted and config.APP_ENV == "production"),
        "version": config.APP_VERSION,
        "equipment": p.domain.equipment["id"] if p else None,
        "agent_mode": p.agent.mode if p else None,
        "judge_mode": p.judge.mode if p else None,
        "model_source": p.model_source if p else None,
        "model_promotion_status": p.model_promotion_status if p else None,
        "model_rejection_reason": p.model_rejection_reason if p else None,
        "n_samples": len(p.features) if p else 0,
        "data_start": p.features.index.min().isoformat() if p else None,
        "data_end": p.features.index.max().isoformat() if p else None,
        "sampling": "1h" if p else None,
    }


@app.get("/api/health/live", tags=["Sante"])
async def liveness() -> dict:
    """Le processus HTTP répond, sans prétendre que ses dépendances sont prêtes."""
    return {"status": "alive", "version": config.APP_VERSION}


@app.get("/api/health/ready", tags=["Sante"])
async def readiness() -> JSONResponse:
    """Disponibilité de la chaîne et des deux registres SQLite."""
    checks = {
        "pipeline": STATE.get("pipeline") is not None,
        "alarm_database": STATE.get("alarm_store") is not None,
        "workflow_database": STATE.get("workflow_store") is not None,
    }
    ready = all(checks.values())
    return JSONResponse(
        {"status": "ready" if ready else "not_ready", "checks": checks},
        status_code=200 if ready else 503,
    )


@app.get("/api/health/model", tags=["Sante"])
async def model_availability() -> dict:
    """État d'exécution et promotion, sans confondre disponibilité et autorisation."""
    p = _pipeline()
    return {
        "runtime_available": True,
        "source": p.model_source,
        "promotion_status": p.model_promotion_status,
        "artifact_rejection_reason": p.model_rejection_reason,
        "approved_for_production": (
            p.model_promotion_status == "approved_for_production"
        ),
        "scientific_claim": "écart comportemental non supervisé à confirmer",
    }


@app.get("/api/health/database", tags=["Sante"])
async def database_health() -> dict:
    """Vérifie par lecture les registres locaux sans modifier leur contenu."""
    alarm_ok = STATE.get("alarm_store") is not None
    workflow_ok = STATE.get("workflow_store") is not None
    if alarm_ok:
        await run_in_threadpool(_alarm_store().list, limit=1)
    if workflow_ok:
        await run_in_threadpool(_workflow_store().list, 1)
    return {
        "status": "available" if alarm_ok and workflow_ok else "unavailable",
        "alarm_store": alarm_ok,
        "workflow_store": workflow_ok,
    }


@app.get("/api/health/version", tags=["Sante"])
async def version_health() -> dict:
    """Versions de l'application et du détecteur effectif."""
    p = _pipeline()
    return {
        "application": config.APP_VERSION,
        "model_source": p.model_source,
        "model_promotion_status": p.model_promotion_status,
        "model_runtime_signature": p.judge.model_runtime_signature,
        "rule_version": p.judge.rule_version,
    }


@app.get("/api/governance", tags=["Systeme"])
def governance() -> dict:
    """Rapport de gouvernance : donnees, capteurs, modele, angles morts.

    Contient volontairement les angles morts et l'etat de sante des capteurs :
    un systeme de surveillance doit declarer ce qu'il ne voit pas.
    """
    p = _pipeline()
    report = p.health_report()
    report["judge_self_audit"] = p.judge.auditor.report()
    return report


@app.get("/api/sensitivity", tags=["Gouvernance"])
async def sensitivity() -> dict:
    """Sensibilite aux deux parametres arbitraires du systeme.

    La contamination fixe le volume d'alertes et la periode de reference
    definit ce qui est « normal ». Aucun des deux n'est justifie physiquement.
    Cet endpoint mesure leur influence pour que le choix soit discutable
    plutot que subi.
    """
    from src.governance.sensitivity import full_report

    return await run_in_threadpool(full_report, _pipeline())


@app.get("/api/coverage", tags=["Gouvernance"])
def coverage() -> dict:
    """Part du risque AMDEC couverte, et etat de confirmation des tags.

    Deux elements que tout jury demandera : quelle fraction de la criticite
    AMDEC le systeme voit reellement, et sur quoi repose le sens attribue a
    chacun des douze tags.
    """
    d = _pipeline().domain
    return {
        "risque": d.risk_coverage(),
        "tags": d.determination_basis(),
    }


@app.get("/api/model/validation", tags=["Gouvernance"])
async def model_validation() -> dict:
    """Backtest temporel et portes de déploiement, sans fausse métrique de panne."""
    return await run_in_threadpool(_pipeline().validation_report)


@app.get("/api/config", tags=["Systeme"])
async def effective_config() -> dict:
    """Configuration effective du service.

    La cle du modele de langage n'est jamais exposee : seule sa presence est
    indiquee. Utile pour diagnostiquer un ecart de comportement entre le poste
    de developpement et le serveur.
    """
    return config.summary()


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
             "rationale": t.rationale, "governance": t.governance}
            for t in d.tags.values()
        ],
        "amdec": [
            {"code": m.code, "element": m.element, "mode": m.mode,
             "F": m.F, "G": m.G, "N": m.N, "C": m.C,
             "band": m.criticality_band(),
             # `observable` est conserve pour compatibilite; `observabilite`
             # porte les trois etats reels du referentiel. Le booleen seul
             # faisait afficher « non — angle mort » sur des modes que le
             # detecteur rattache activement a des constatations.
             "observable": m.observable, "observabilite": m.observabilite,
             "action": m.action_corrective, "tasks": m.plan_maintenance_ref,
             "provenance_category": m.provenance_category,
             "source_file": m.source_file,
             "source_location": m.source_location,
             "original_values": m.original_values,
             "transformations": m.transformations,
             "validation_status": m.validation_status,
             "validation_owner": m.validation_owner}
            for m in d.modes_ranked()
        ],
        "plan_maintenance": d.plan_maintenance,
        "blind_spots": [m.code for m in d.blind_spots()],
        "partially_observable": [m.code for m in d.partially_observable_modes()],
        "tag_registry_change_history": d.tag_registry_history,
    }


# ── Donnees ───────────────────────────────────────────────────────────────────

@app.get("/api/timeseries", tags=["Donnees"])
def timeseries(
    start: datetime | None = None,
    end: datetime | None = None,
    max_points: int = Query(1500, ge=100, le=20000),
) -> dict:
    """Series temporelles des grandeurs cles, sous-echantillonnees si besoin.

    Args:
        start: Borne de debut (ISO 8601).
        end: Borne de fin (ISO 8601).
        max_points: Nombre maximal de points renvoyes.

    Returns:
        Dictionnaire {colonne: liste de valeurs} plus les horodatages.
    """
    p = _pipeline()
    start_ts = _naive_timestamp(start)
    end_ts = _naive_timestamp(end)
    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        raise HTTPException(
            status_code=422,
            detail="La borne de debut doit preceder la borne de fin",
        )
    # Les features restent la source des grandeurs calculées. Les observations
    # ajoutent les 12 tags DCS, y compris les deux capteurs dégradés, uniquement
    # pour la visualisation : elles ne réintègrent jamais l'apprentissage.
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
    ]
    cols = [c for c in cols if c in df.columns]

    if len(df) <= max_points:
        sub = df
    else:
        # Echantillonnage regulier qui respecte strictement max_points et
        # conserve toujours le dernier point (le curseur du rejeu).
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
    """Synthese de disponibilite et de defauts par capteur."""
    return _pipeline().ingestion.sensor_health.to_dict(orient="records")


@app.get("/api/detection/fouling-bench", tags=["Gouvernance"])
async def fouling_bench(
    severities: str = Query(
        "0.05,0.10,0.20,0.30",
        description=(
            "Pertes de coefficient d'echange testees, en FRACTION dans ]0, 1[ "
            "et separees par des virgules. 0.20 = perte de 20 % de UA."
        ),
    ),
    duration_days: int = Query(60, ge=14, le=180),
) -> dict:
    """Banc d'injection d'encrassement — mesure de detection sur donnees reelles.

    Repond a la question qu'aucune metrique du projet ne couvrait : le detecteur
    verrait-il un encrassement s'il s'en produisait un ? Une rampe simulee est
    superposee aux donnees reelles dans une fenetre ou la regle est silencieuse,
    puis on mesure ce que le detecteur en fait.

    Le chiffre a lire n'est pas le taux de detection brut mais le taux de
    detection UTILE, c'est-a-dire assez tot pour programmer un arret.
    """
    from src.governance.fouling_injection import FoulingInjectionBench

    try:
        levels = tuple(float(a) for a in severities.split(",") if a.strip())
    except ValueError as exc:
        raise HTTPException(422, "Severites illisibles") from exc
    if not levels:
        raise HTTPException(422, "Au moins une severite est requise")
    # Une severite est une FRACTION de perte de UA. Laisser passer 1, 2 ou 3
    # produirait des scenarios ou l'echangeur n'echange plus rien, detectes
    # par construction : le banc afficherait 100 % sans rien demontrer.
    hors_plage = [level for level in levels if not 0.0 < level < 1.0]
    if hors_plage:
        raise HTTPException(
            422,
            f"Severite hors plage : {hors_plage}. Une severite est une perte "
            f"de coefficient d'echange exprimee en fraction, dans ]0, 1[ "
            f"(0.20 = perte de 20 % de UA).",
        )

    bench = FoulingInjectionBench(_pipeline())
    result = await run_in_threadpool(
        bench.run, levels, (duration_days,),
    )
    return result.to_dict()


@app.get("/api/topology", tags=["Donnees"])
def topology() -> dict:
    """Topologie physique : pieces, capteurs situes, rattachement des codes.

    C'est le contrat que consomme la representation 3D. Il vient integralement
    de `src/domain/topology.yaml` : aucune position, aucun rattachement piece
    n'est ecrit dans le code de l'interface. Une correction validee par OCP se
    fait dans le YAML.
    """
    return _pipeline().domain.topology()


@app.get("/api/sensor/{alias}", tags=["Donnees"])
def sensor_detail(
    alias: str,
    window_h: int = Query(504, ge=6, le=20000),
    end: datetime | None = None,
    max_points: int = Query(700, ge=50, le=5000),
) -> dict:
    """Fiche complete d'un capteur : metadonnees, serie et qualite.

    C'est la reponse au clic sur un capteur du modele 3D. Elle rassemble en un
    seul appel ce qu'un exploitant veut voir : ce que le capteur mesure, ce
    qu'il vaut maintenant, comment il a evolue, et si on peut lui faire
    confiance.

    Args:
        alias: Alias court du tag, ex. 'T_ACID_OUT'.
        window_h: Profondeur d'historique en heures.
        end: Instant de fin (defaut : fin des donnees ou curseur de rejeu).
        max_points: Nombre maximal de points renvoyes.

    Returns:
        Metadonnees, seuils, serie temporelle, statistiques et evenements qualite.

    Raises:
        HTTPException: 404 si l'alias est inconnu du referentiel.
    """
    p = _pipeline()
    tag = p.domain.by_alias.get(alias)
    if tag is None:
        raise HTTPException(status_code=404, detail=f"Capteur inconnu: {alias}")

    # Les observations portent les 12 tags DCS, capteurs degrades compris : un
    # capteur mort doit rester consultable, c'est meme la seule facon de voir
    # qu'il est mort. Les features n'en gardent que le perimetre exploitable.
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
    issues = (
        events["issue"].value_counts().to_dict() if len(events) else {}
    )
    health_rows = p.ingestion.sensor_health
    health = health_rows[health_rows["alias"] == alias]
    availability = float(health["availability_pct"].iloc[0]) if len(health) else None

    def _num(value: Any) -> float | None:
        return None if pd.isna(value) else round(float(value), 4)

    return {
        "alias": alias,
        "tag": tag.tag,
        "label": tag.label,
        "unit": tag.unit,
        "kind": tag.kind,
        "role": tag.role,
        "confidence": tag.confidence,
        "rationale": tag.rationale,
        "setpoint": tag.setpoint,
        "range_operating": tag.range_operating,
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
            "last_at": str(valid.index[-1]) if len(valid) else None,
            "min": _num(valid.min()) if len(valid) else None,
            "max": _num(valid.max()) if len(valid) else None,
            "mean": _num(valid.mean()) if len(valid) else None,
            "p01": _num(valid.quantile(0.01)) if len(valid) else None,
            "p99": _num(valid.quantile(0.99)) if len(valid) else None,
            "n_total": len(series),
            "n_valid": len(valid),
        },
        "quality": {
            "availability_pct": availability,
            "issues": issues,
            "n_events": len(events),
        },
    }


@app.get("/api/episodes", tags=["Donnees"])
def episodes(limit: int = Query(50, ge=1, le=500)) -> list[dict]:
    """Episodes d'anomalie agreges, tries par score maximal.

    Args:
        limit: Nombre maximal d'episodes.

    Returns:
        Liste d'episodes serialisables.
    """
    ep = _pipeline().episodes().head(limit).copy()
    for c in ("start", "end", "peak_at"):
        ep[c] = ep[c].astype(str)
    return ep.to_dict(orient="records")


# ── Analyse ───────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    """Requete d'analyse d'un instant.

    Attributes:
        timestamp: Instant a analyser (ISO 8601).
    """

    timestamp: str = Field(..., examples=["2024-10-25T21:00:00"])


@app.post("/api/analyze", tags=["Analyse"])
def analyze(req: AnalyzeRequest) -> dict:
    """Analyse complete d'un instant : detection, diagnostic, jugement.

    Args:
        req: Requete contenant l'horodatage.

    Returns:
        Dictionnaire complet de l'analyse.

    Raises:
        HTTPException: 404 si l'horodatage est absent des donnees.
    """
    p = _pipeline()
    try:
        return p.analyze_at(req.timestamp).to_dict()
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Horodatage {req.timestamp} absent des donnees "
                   f"({p.features.index.min()} -> {p.features.index.max()})",
        ) from exc


@app.get("/api/notable", tags=["Analyse"])
def notable(limit: int = Query(20, ge=1, le=100)) -> list[dict]:
    """Analyse les instants les plus interessants de la periode.

    Args:
        limit: Nombre d'instants a analyser.

    Returns:
        Liste d'analyses compactes.
    """
    p = _pipeline()
    return [
        _compact(p.analyze_at(ts, use_llm=False))
        for ts in p.notable_timestamps(limit)
    ]


# ── Temps reel ────────────────────────────────────────────────────────────────

class ReplayConfig(BaseModel):
    """Parametres de demarrage du rejeu.

    Attributes:
        speed: Heures de process simulees par seconde reelle.
        start: Horodatage de depart.
        analyze_every: Analyser un instant sur N.
    """

    speed: float = Field(120.0, gt=0, le=100000)
    start: str | None = None
    analyze_every: int = Field(3, ge=1, le=24)


@app.post("/api/replay/start", tags=["Temps reel"])
def replay_start(cfg: ReplayConfig, request: Request) -> dict:
    """Demarre (ou redemarre) le rejeu accelere du flux DCS.

    Args:
        cfg: Parametres du rejeu.

    Returns:
        Etat du rejeu apres demarrage.
    """
    _require_roles(
        request, "operator", "maintenance", "reliability_engineer", "administrator"
    )
    p = _pipeline()
    old: DCSReplay | None = STATE.get("replay")
    if old is not None and old.state.running:
        old.stop()
    try:
        replay = _build_replay(
            p,
            speed=cfg.speed,
            start=cfg.start,
            analyze_every=cfg.analyze_every,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    STATE["replay"] = replay
    replay.start()
    return replay.snapshot()


@app.post("/api/replay/stop", tags=["Temps reel"])
def replay_stop(request: Request) -> dict:
    """Arrete le rejeu en cours."""
    _require_roles(
        request, "operator", "maintenance", "reliability_engineer", "administrator"
    )
    r = _replay()
    r.stop()
    return r.snapshot()


@app.post("/api/replay/speed", tags=["Temps reel"])
async def replay_speed(
    request: Request,
    speed: float = Query(..., gt=0, le=100000),
) -> dict:
    """Change la vitesse du rejeu a chaud.

    Args:
        speed: Nouvelle vitesse en heures de process par seconde.

    Returns:
        Etat du rejeu.
    """
    _require_roles(
        request, "operator", "maintenance", "reliability_engineer", "administrator"
    )
    r = _replay()
    r.set_speed(speed)
    return r.snapshot()


@app.get("/api/replay/state", tags=["Temps reel"])
async def replay_state() -> dict:
    """Etat courant du rejeu."""
    return _replay().snapshot()


@app.get("/api/replay/stream", tags=["Temps reel"])
async def replay_stream(n: int = Query(40, ge=1, le=500)) -> list[dict]:
    """Dernieres analyses produites par le rejeu.

    Args:
        n: Nombre d'elements.

    Returns:
        Liste d'analyses compactes, du plus recent au plus ancien.
    """
    return _replay().recent(n)


@app.get("/api/replay/alerts", tags=["Temps reel"])
async def replay_alerts(n: int = Query(40, ge=1, le=500)) -> list[dict]:
    """Dernieres alertes du rejeu.

    Args:
        n: Nombre d'elements.

    Returns:
        Liste d'alertes compactes.
    """
    return _replay().alerts(n)


@app.get("/api/alarms", tags=["Alarmes"])
async def alarm_registry(
    active_only: bool = True,
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    """Registre durable avec état, propriétaire et historique opérateur."""
    return await run_in_threadpool(
        _alarm_store().list,
        active_only=active_only,
        limit=limit,
    )


def _workflow_templates() -> dict[str, dict[str, Any]]:
    """Modèles issus des checklists et gammes OCP, sans remplacer le permis HSE."""
    domain = _pipeline().domain
    external = [
        {
            "code": f"EXT-{index:02d}",
            "label": label,
            "dangerous": False,
            "source_ref": (
                "6-Check-list INSPECTION REFROIDISSEUR DE SECHAGE PSIII.xlsx "
                "- checklist externe"
            ),
        }
        for index, label in enumerate(
            domain.checklists["INSPECTION_EXTERNE"]["points"], start=1
        )
    ]
    prerequisites = [
        ("HSE-01", "Autorisation de travail officielle reçue", False),
        ("HSE-02", "Circuits acide et eau de mer isolés et consignés", True),
        ("HSE-03", "Calandre vidangée et pression intérieure vérifiée à 0 bar", True),
        ("HSE-04", "EPI anti-acide complets contrôlés", True),
        ("HSE-05", "Couvercles ouverts selon la gamme approuvée", True),
        ("HSE-06", "Manutention au palan réalisée avec moyen contrôlé", True),
    ]
    internal = [
        {
            "code": code,
            "label": label,
            "dangerous": dangerous,
            "source_ref": (
                "7-Gamme PV Refroidisseur d'acide PS3.pdf - page 1, "
                "phases 10 à 120"
            ),
        }
        for code, label, dangerous in prerequisites
    ] + [
        {
            "code": f"INT-{index:02d}",
            "label": label,
            "dangerous": False,
            "source_ref": (
                "6-Check-list INSPECTION REFROIDISSEUR DE SECHAGE PSIII.xlsx "
                "- checklist interne"
            ),
        }
        for index, label in enumerate(
            domain.checklists["INSPECTION_INTERNE"]["points"], start=1
        )
    ]
    tamponnage_labels = [
        "Identifier et repérer le tube à contrôler",
        "Confirmer consignation, vidange et pression nulle",
        "Contrôler visuellement les extrémités et la plaque tubulaire",
        "Exécuter le tamponnage selon la gamme approuvée",
        "Enregistrer le nombre cumulé de tubes tamponnés",
        "Comparer au critère documentaire de 30 % sans inventer le nombre total",
        "Contrôler l'étanchéité avant fermeture",
        "Clôturer et préparer la remise en service autorisée",
    ]
    tamponnage = [
        {
            "code": f"TAM-{index:02d}",
            "label": label,
            "dangerous": index in {2, 4, 7, 8},
            "source_ref": (
                "8-Gamme de tamponnage des tubes de refroidisseur.xls; "
                "plan préventif H pour le critère 30 %"
            ),
        }
        for index, label in enumerate(tamponnage_labels, start=1)
    ]
    warning = (
        "Démonstrateur de traçabilité uniquement: ne remplace pas la procédure HSE, "
        "la consignation officielle, le permis de travail ni la GMAO OCP."
    )
    return {
        "INSPECTION_EXTERNE": {
            "title": "Inspection externe mensuelle",
            "frequency": "1 mois - source plan préventif C",
            "warning": warning,
            "steps": external,
        },
        "INSPECTION_INTERNE": {
            "title": "Inspection interne en arrêt process",
            "frequency": "Révision - sans périodicité interprétée",
            "warning": warning,
            "steps": internal,
        },
        "TAMPONNAGE": {
            "title": "Contrôle et tamponnage des tubes",
            "frequency": "Selon inspection/autorisation - critère H confirmé à 30 %",
            "warning": warning,
            "steps": tamponnage,
        },
    }


@app.get("/api/workflows/templates", tags=["Maintenance"])
def workflow_templates() -> dict[str, dict[str, Any]]:
    """Modèles documentaires avec provenance et avertissement HSE permanent."""
    return _workflow_templates()


@app.get("/api/workflows", tags=["Maintenance"])
async def workflow_list(limit: int = Query(100, ge=1, le=500)) -> list[dict]:
    """Liste paginée bornée des interventions locales."""
    return await run_in_threadpool(_workflow_store().list, limit)


@app.get("/api/workflows/{workflow_id}", tags=["Maintenance"])
async def workflow_detail(workflow_id: str) -> dict:
    try:
        return await run_in_threadpool(_workflow_store().get, workflow_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Intervention inconnue") from exc


@app.post("/api/workflows", tags=["Maintenance"], status_code=201)
async def workflow_create(
    payload: WorkflowCreateRequest,
    request: Request,
) -> dict:
    _require_roles(request, "maintenance", "reliability_engineer", "administrator")
    template = _workflow_templates()[payload.template_id]
    operator = request.state.operator
    actor = operator.email if operator is not None else "poste-local"
    return await run_in_threadpool(
        _workflow_store().create,
        template_id=payload.template_id,
        title=template["title"],
        owner=payload.owner,
        planned_at=payload.planned_at,
        created_by=actor,
        steps=template["steps"],
    )


@app.patch("/api/workflows/{workflow_id}/steps/{step_id}", tags=["Maintenance"])
async def workflow_step_update(
    workflow_id: str,
    step_id: str,
    payload: WorkflowStepRequest,
    request: Request,
) -> dict:
    _require_roles(request, "maintenance", "reliability_engineer", "administrator")
    operator = request.state.operator
    actor = operator.email if operator is not None else "poste-local"
    try:
        return await run_in_threadpool(
            _workflow_store().update_step,
            workflow_id,
            step_id,
            status=payload.status,
            actor=actor,
            measurement=payload.measurement,
            unit=payload.unit,
            comment=payload.comment,
            proof_ref=payload.proof_ref,
            expected_version=payload.expected_version,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Étape inconnue") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/workflows/{workflow_id}/complete", tags=["Maintenance"])
async def workflow_complete(
    workflow_id: str,
    payload: WorkflowCompleteRequest,
    request: Request,
) -> dict:
    _require_roles(request, "maintenance", "reliability_engineer", "administrator")
    operator = request.state.operator
    actor = operator.email if operator is not None else "poste-local"
    try:
        return await run_in_threadpool(
            _workflow_store().complete,
            workflow_id,
            actor=actor,
            signature=payload.signature,
            proof_ref=payload.proof_ref,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Intervention inconnue") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/alarms/{alarm_id}/transition", tags=["Alarmes"])
async def alarm_transition(
    alarm_id: int,
    payload: AlarmTransitionRequest,
    request: Request,
) -> dict:
    """Acquitte, shelve ou réactive une alarme avec traçabilité."""
    operator = request.state.operator
    identity = operator.email if operator is not None else "poste-local"
    role = operator.role if operator is not None else "administrator"
    allowed_by_action = {
        "acknowledge": {
            "operator", "maintenance", "reliability_engineer", "administrator"
        },
        "shelve": {"maintenance", "reliability_engineer", "administrator"},
        "unshelve": {"maintenance", "reliability_engineer", "administrator"},
        "close": {"maintenance", "reliability_engineer", "administrator"},
    }
    if role not in allowed_by_action[payload.action]:
        raise HTTPException(status_code=403, detail="Rôle insuffisant pour cette action")
    try:
        return await run_in_threadpool(
            _alarm_store().transition,
            alarm_id,
            action=payload.action,
            operator=identity,
            comment=payload.comment,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Alarme inconnue") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/replay/disagreements", tags=["Temps reel"])
async def replay_disagreements(n: int = Query(20, ge=1, le=200)) -> list[dict]:
    """Decisions rejetees par le Judge pendant le rejeu.

    C'est la vue la plus importante du point de vue gouvernance : elle montre
    ou le systeme s'est controle lui-meme.

    Args:
        n: Nombre d'elements.

    Returns:
        Liste d'analyses completes avec le detail des controles.
    """
    return _replay().disagreements(n)


# ── Judge ─────────────────────────────────────────────────────────────────────

@app.get("/api/judge/audit", tags=["Judge"])
def judge_audit() -> dict:
    """Auto-surveillance du Judge : distribution des notes et alertes."""
    return _pipeline().judge.auditor.report()


@app.get("/api/judge/evaluation", tags=["Judge"])
async def judge_evaluation(
    request: Request,
    n_cases: int = Query(8, ge=2, le=30),
) -> dict:
    """Teste le contrôleur de cohérence par injection de fautes logicielles.

    Soumet au Judge des decisions deliberement fausses et mesure sa capacite
    à les détecter. Cette robustesse logicielle ne mesure pas l'exactitude industrielle.

    Args:
        n_cases: Nombre d'instants reels servant de support aux pieges.

    Returns:
        Metriques et detail par type de faute.
    """
    _require_roles(request, "reliability_engineer", "administrator")
    from src.governance.judge_eval import JudgeEvaluator

    res = await run_in_threadpool(
        JudgeEvaluator(_pipeline()).run,
        n_cases,
    )
    return {
        "summary": res.summary,
        "by_trap": res.traps.to_dict(orient="records"),
        "report": res.report(),
    }


# ── Notifications ─────────────────────────────────────────────────────────────

@app.get("/api/notifications/status", tags=["Notifications"])
async def notification_status() -> dict:
    """État du canal complémentaire sans révéler les secrets SMTP."""
    return _notifier().status()


@app.post("/api/notifications/test", tags=["Notifications"])
async def notification_test(request: Request) -> dict:
    """Place un email de test dans la file asynchrone."""
    _require_roles(request, "maintenance", "reliability_engineer", "administrator")
    if not _notifier().enqueue_test():
        raise HTTPException(status_code=409, detail="Canal email non configure")
    return {"accepted": True}


@app.post("/api/notifications/governance", tags=["Notifications"])
def notification_governance(request: Request) -> dict:
    """Envoie au technicien une synthèse de gouvernance traçable."""
    _require_roles(request, "maintenance", "reliability_engineer", "administrator")
    pipeline = _pipeline()
    payload = {
        "equipment": pipeline.domain.equipment["id"],
        "generated_at": datetime.now().isoformat(),
        "health": pipeline.health_report(),
        "judge": pipeline.judge.auditor.report(),
    }
    accepted = _notifier().enqueue_governance(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    )
    if not accepted:
        raise HTTPException(status_code=409, detail="Canal email non configure")
    return {"accepted": True}


# ── Indicateurs d'exploitation ────────────────────────────────────────────────

@app.get("/api/kpi", tags=["Indicateurs"])
def operational_kpi() -> dict:
    """Indicateurs calcules sur les donnees, sans hypothese economique.

    Chaque figure porte son `evidence_level` : `observed` pour une grandeur lue
    directement dans les donnees, `derived` pour une grandeur passant par la
    reference thermique semi-empirique.
    """
    from src.analytics import OperationalKPI

    p = _pipeline()
    kpi = OperationalKPI(p.features, p.domain)
    stability = kpi.control_stability()

    # Le taux horaire reel est publie a cote de la charge d'episodes : sans
    # lui, l'agregation en episodes masque un taux de signalement cinq fois
    # superieur a la contamination de calibration.
    scores = p.detector.score_series(p.features)
    threshold = float(p.detector.stat.threshold_)
    figures = kpi.summary(p.ingestion.sensor_health, p.episodes())
    figures.append(kpi.flag_rate(scores, threshold, config.CONTAMINATION))
    monthly = kpi.monthly_flag_rate(scores, threshold)

    return {
        "figures": [f.to_dict() for f in figures],
        "stabilite_regulation": [
            {
                "periode": str(idx.date()),
                **{k: (None if pd.isna(v) else float(v)) for k, v in row.items()},
            }
            for idx, row in stability.iterrows()
        ],
        "signalement_mensuel": [
            {
                "periode": str(idx.date()),
                **{k: (None if pd.isna(v) else float(v)) for k, v in row.items()},
            }
            for idx, row in monthly.iterrows()
        ],
        "calibration": {
            "contamination_visee_pct": round(config.CONTAMINATION * 100, 2),
            "seuil": round(threshold, 4),
        },
    }


@app.exception_handler(Exception)
async def unhandled(request, exc: Exception) -> JSONResponse:
    """Renvoie une erreur lisible plutot qu'une trace brute.

    Args:
        request: Requete entrante.
        exc: Exception levee.

    Returns:
        Reponse JSON 500.
    """
    incident = token_hex(5)
    logger.exception(f"Erreur non geree [{incident}] sur {request.url.path}")
    # Un gestionnaire d'exception s'execute EN DEHORS des middlewares
    # applicatifs : sans ce durcissement explicite, la reponse 500 partait
    # elle aussi sans aucun en-tete de defense.
    return _durcir(
        JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "detail": "Erreur interne du service",
                "incident": incident,
            },
        ),
        request,
        getattr(request.state, "request_id", incident),
    )
