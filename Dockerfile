# =============================================================================
# Surveillance du refroidisseur E7301 — image de production
#
# Construction en deux etapes : les dependances sont compilees dans une image
# de build jetable, seul le resultat est copie dans l'image finale. Celle-ci
# ne contient donc ni compilateur ni en-tetes de developpement — moins de
# surface d'attaque et une image nettement plus legere.
# =============================================================================

# ── Etape 1 : construction des dependances ───────────────────────────────────
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# gcc et g++ sont necessaires a la compilation de certaines roues scientifiques.
# Ils restent dans cette etape et n'atteignent jamais l'image finale.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements-runtime.txt requirements-runtime.lock ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements-runtime.lock


# ── Etape 2 : image d'execution ──────────────────────────────────────────────
FROM python:3.11-slim

LABEL org.opencontainers.image.title="Surveillance refroidisseur E7301" \
      org.opencontainers.image.description="Surveillance comportementale et verification deterministe — PS III, Maroc Chimie" \
      org.opencontainers.image.version="3.0.0" \
      org.opencontainers.image.vendor="OCP Group — Programme Bionic" \
      org.opencontainers.image.authors="Mounir Sanbouli"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PATH="/opt/venv/bin:$PATH" \
    LOG_LEVEL=INFO

# curl sert uniquement a la sonde de sante du conteneur.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# L'application ne tourne jamais en root. Un service de supervision n'a
# aucune raison de disposer des droits d'administration de la machine.
RUN useradd --create-home --shell /usr/sbin/nologin --uid 10001 e7301

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=e7301:e7301 src/ ./src/
COPY --chown=e7301:e7301 api/ ./api/
COPY --chown=e7301:e7301 requirements-runtime.txt requirements-runtime.lock README.md ./

# Les donnees et les modeles sont montes en volume, pas embarques dans l'image :
# l'export DCS evolue independamment du code.
RUN mkdir -p /app/data/raw /app/models /app/reports \
    && chown -R e7301:e7301 /app/data /app/models /app/reports

USER e7301
EXPOSE 8000

# LA SONDE PORTE SUR LA DISPONIBILITE, PAS SUR LA PROMOTION DU MODELE.
#
# Une version precedente exigeait `"status":"ok"` dans /api/health. Or ce
# statut est INATTEIGNABLE par construction : il vaut `degraded` des lors que
# le modele n'est pas promu, et aucun modele ne peut l'etre — `build_manifest`
# ecrit toujours le statut `candidate`, absent de MODEL_ALLOWED_STATUSES. Le
# conteneur livre etait donc marque `unhealthy` en permanence, et un
# orchestrateur l'aurait retire de la rotation ou redemarre en boucle.
#
# La disponibilite du service et la promotion du modele sont deux questions
# distinctes. /api/health/ready repond a la premiere (200 ou 503) ;
# /api/health/model repond a la seconde.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health/ready || exit 1

# Le point d'entree honore API_HOST, API_PORT et LOG_LEVEL, et refuse de
# demarrer sur une configuration invalide. Une version precedente ecrivait
# l'hote et le port en dur ici : les variables de configuration prevues pour
# les regler n'avaient alors aucun effet.
ENV API_HOST=0.0.0.0 \
    API_PORT=8000

CMD ["python", "-m", "api"]

# Note sur le nombre de workers : la chaine charge l'historique complet et
# entraine le modele au demarrage, en memoire. Plusieurs workers dupliqueraient
# ce travail et ce modele sans aucun gain — la charge de ce service est tres
# inferieure a ce qu'un seul processus absorbe (45 analyses par seconde
# mesurees, pour un equipement echantillonne a l'heure).
