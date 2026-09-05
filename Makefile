# =============================================================================
# Surveillance du refroidisseur E7301 — commandes courantes
# =============================================================================
.DEFAULT_GOAL := help
.PHONY: help install test serve dev train replay clean

help:  ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	 awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install:  ## Installe les dependances
	pip install -r requirements.txt

test:  ## Suite complete de tests
	pytest tests/ -q

serve:  ## Lance l'API et le dashboard
	python -m api

dev:  ## Lance avec rechargement a chaud (developpement)
	uvicorn api.main:app --reload --host $${API_HOST:-127.0.0.1} --port $${API_PORT:-8000}

train:  ## Entraine et serialise le detecteur
	python -c "from src.pipeline import E7301Pipeline; E7301Pipeline().save_model()"

replay:  ## Rejeu accelere en console
	python -m src.realtime.replay

analyse:  ## Analyse de bout en bout
	python -m src.pipeline

clean:  ## Supprime les fichiers temporaires
	find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache 2>/dev/null || true
