.PHONY: install data train api frontend test clean lint docker-up docker-down docker-build

# Install all dependencies
install:
	pip install -r requirements.txt

# Generate synthetic sensor data
data:
	python data/data_generator.py

# Train anomaly detection models
train:
	python src/models/train.py

# Launch FastAPI server
api:
	uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Launch frontend React/Vite dev server
frontend:
	cd frontend && npm run dev

# Run full test suite with coverage
test:
	pytest tests/ -v --cov=src --cov=api --cov-report=term-missing --cov-report=html

# Lint with ruff (config in pyproject.toml)
lint:
	ruff check src/ api/ tests/

# Clean generated artifacts
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache htmlcov .coverage
	rm -rf mlruns mlartifacts
	rm -f data/*.db data/raw/*.csv data/processed/*.csv

# Run full pipeline
pipeline: data train api

# Docker
docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down -v

docker-setup: docker-build
	docker-compose up -d db
	sleep 5
	docker-compose run --rm api python data/data_generator.py
	docker-compose run --rm api python src/models/train.py
	docker-compose up -d
