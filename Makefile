# =============================================================================
# Surveillance du refroidisseur E7301 — commandes courantes
# =============================================================================
.DEFAULT_GOAL := help
.PHONY: help install check test test-front eval-judge bench-fouling sensitivity operator operators train release release-runtime lock-runtime promote serve dev replay analyse notebook docker docker-run clean

help:  ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	 awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ── Installation ─────────────────────────────────────────────────────────────
install:  ## Installe les dependances
	pip install -r requirements.txt

# ── Qualite ──────────────────────────────────────────────────────────────────
check:  ## Analyse statique du code
	ruff check src api tests scripts
	bandit -q -r src api -x tests
	node --check api/static/app.js
	node --check api/static/twin.js

types:  ## Typage statique — informatif, non bloquant (voir pyproject.toml)
	mypy src api

test:  ## Suite complete de tests
	pytest tests/ -q --cov=src --cov=api --cov-fail-under=85

test-front:  ## Bancs frontend : cablage du poste et scene 3D
	npm install --no-audit --no-fund
	python scripts/dump_fixtures.py
	node scripts/frontend_smoke.mjs
	node scripts/twin_smoke.mjs
	node scripts/boot_smoke.mjs

bench-fouling:  ## Injecte un encrassement simule et mesure la detection
	python -m src.governance.fouling_injection

sensitivity:  ## Sensibilite aux deux parametres arbitraires du systeme
	python -m src.governance.sensitivity

operator:  ## Enregistre un technicien (adresse + mot de passe masque)
	python scripts/manage_operators.py add

operators:  ## Liste les techniciens habilites
	python scripts/manage_operators.py list

eval-judge:  ## Evalue le Judge par injection de fautes controlees
	python -m src.governance.judge_eval

# ── Exploitation ─────────────────────────────────────────────────────────────
serve:  ## Lance l'API et le dashboard (honore API_HOST et API_PORT)
	python -m api

dev:  ## Idem avec rechargement a chaud (developpement uniquement)
	uvicorn api.main:app --reload --host $${API_HOST:-127.0.0.1} --port $${API_PORT:-8000}

train:  ## Entraine et serialise le detecteur
	python -c "from src.pipeline import E7301Pipeline; E7301Pipeline(use_llm=False).save_model()"

release:  ## Genere backtest, modele candidat et manifeste SHA-256 (environnement local)
	python scripts/validate_release.py

release-runtime:  ## Produit l'artefact DANS l'image d'execution (seul artefact promouvable)
	@echo "Un artefact produit hors du runtime cible ne pourra jamais etre promu :"
	@echo "validate_model_manifest exige l'egalite EXACTE des versions de paquets."
	docker run --rm -v "$(CURDIR):/w" -w /w python:3.11-slim \
	  bash -c "pip install -q --no-cache-dir -r requirements-runtime.lock \
	           && pip install -q --no-cache-dir pytest \
	           && python scripts/validate_release.py"

lock-runtime:  ## Regenere requirements-runtime.lock dans l'image d'execution
	docker run --rm -v "$(CURDIR):/w" -w /w python:3.11-slim \
	  bash -c "pip install -q --no-cache-dir -r requirements-runtime.txt \
	           && pip freeze --exclude-editable > /tmp/f.txt \
	           && cat requirements-runtime.lock | sed -n '1,/^\$$/p' > /tmp/h.txt \
	           && cat /tmp/h.txt /tmp/f.txt > requirements-runtime.lock"
	@echo "Verrou regenere. Relancer 'make release-runtime' pour aligner le manifeste."

promote:  ## Affiche l'etat de promotion de l'artefact courant
	python scripts/promote_model.py --etat

replay:  ## Rejeu accelere en console
	python -m src.realtime.replay

analyse:  ## Analyse de bout en bout des instants notables
	python -m src.pipeline

notebook:  ## Ouvre le notebook d'analyse
	jupyter notebook notebooks/01_analyse_E7301.ipynb

# ── Deploiement ──────────────────────────────────────────────────────────────
docker:  ## Construit l'image de production
	docker build -t ocp/e7301-surveillance:3.0.0 .

docker-run:  ## Demarre le service conteneurise
	docker compose up -d
	@echo "Dashboard : http://localhost:8000"

# ── Entretien ────────────────────────────────────────────────────────────────
clean:  ## Supprime les fichiers temporaires
	find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache 2>/dev/null || true
