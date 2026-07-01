# OCP Bionic Judge Agent

[![CI](https://github.com/mounir-sanbouli/ocp-bionic-judge/actions/workflows/ci.yml/badge.svg)](https://github.com/mounir-sanbouli/ocp-bionic-judge/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/database-PostgreSQL-336791.svg)](https://postgresql.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> Projet de stage — Programme Bionic, OCP Group Khouribga.  
> J'ai construit un système de détection d'anomalies sur les capteurs de machines phosphate,
> avec deux agents IA en cascade : un agent principal (LangChain ReAct) qui analyse et explique
> l'anomalie, et un Judge Agent (Gemini) qui note indépendamment la qualité de ce diagnostic
> sur 5 critères. L'idée derrière le Judge vient du concept "Independent Judge Model" du programme Bionic.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     OCP Bionic Judge System                     │
├──────────────┬──────────────────┬──────────────────────────────┤
│  5 Machines  │   ML Pipeline    │      AI Agents (Gemini)      │
│  Phosphate   │                  │                              │
│              │  IsolationForest │  Detection Agent (ReAct)     │
│  BROYEUR_01  │  OneClassSVM     │  ┌─ get_anomaly_data()       │
│  POMPE_02    │  HDBSCAN         │  ├─ get_machine_history()    │
│  CONVOYEUR_03│                  │  └─ get_shap_explanation()   │
│  REACTEUR_04 │  SHAP            │                              │
│  COMPRESSEUR │  Explainability  │  Judge Agent (Autonomous)    │
│              │                  │  └─ 5 critères pondérés /10  │
│  30s interval│  PSI/KS Drift    │                              │
│  ~2.5M rows  │  Detection       │                              │
└──────────────┴──────────────────┴──────────────────────────────┘
        │                  │                       │
        ▼                  ▼                       ▼
   PostgreSQL          FastAPI              React/Vite Frontend
   (6 tables)      POST /analyze          TypeScript + Recharts
                   GET /decisions
                   GET /governance
```

---

## Stack Technique

| Couche | Technologies |
|--------|-------------|
| **ML** | scikit-learn (IsolationForest, OC-SVM), HDBSCAN, SHAP, MLflow |
| **Agents** | LangChain 0.3, Google Gemini 2.0 Flash (gratuit — Google AI Studio) |
| **API** | FastAPI, Uvicorn, Pydantic v2 |
| **Frontend** | React 18 + Vite, TypeScript, Tailwind CSS, Recharts |
| **Data** | PostgreSQL 15 (dev: SQLite), SQLAlchemy, Pandas |
| **Tests** | pytest, pytest-cov |
| **CI/CD** | GitHub Actions, Docker Compose |

---

## Performances ML (mesurées sur jeu de test, reproductibles)

| Métrique | Valeur | Note |
|----------|--------|------|
| **AUC-ROC** | **0.82** | Métrique principale — classement anomalie vs normal (Isolation Forest déployé) |
| **Average Precision** | **0.44** | Aire sous la courbe Précision-Rappel |
| **F1 @ seuil optimal** | **0.47** | F1 au meilleur seuil trouvé via PR curve |
| Taux d'anomalies simulées | ~4–5% | Réaliste pour industrie phosphate |
| Latence inférence | < 0.1 ms | Par lecture capteur (Isolation Forest) |

> **Modèle déployé vs leader AUC.** Trois modèles sont entraînés et comparés sur le test
> set : Isolation Forest (AUC 0.82), One-Class SVM (AUC 0.93) et HDBSCAN (AUC 0.75).
> One-Class SVM a l'AUC le plus élevé, mais c'est **Isolation Forest qui est déployé** :
> c'est le seul modèle compatible avec SHAP TreeExplainer (explications rapides et exactes)
> et le plus rapide à l'inférence — l'explicabilité et la latence < 2 ms sont des exigences
> OCP non négociables (voir `docs/decisions/ADR-003` et `ADR-006`).
>
> **Méthodologie d'évaluation :** split chronologique 80% train / 20% test — le test set
> contient uniquement des données futures que le modèle n'a pas vues pendant l'entraînement.
> La pipeline de features (24 features ciblées) est fittée exclusivement sur le train set et
> sérialisée avec le modèle pour garantir la cohérence train–inférence.
>
> **Pourquoi F1 = 0.47 ?**  
> Le F1 reste modéré parce qu'on est en apprentissage non-supervisé — le modèle n'a jamais
> vu de labels "c'est une anomalie". L'AUC-ROC est la métrique pertinente ici : elle
> mesure si le modèle arrive à séparer les anomalies des points normaux, indépendamment
> du seuil qu'on choisit. Si on avait des labels confirmés par les techniciens OCP,
> un modèle supervisé monterait facilement à F1 > 0.80. Voir `docs/decisions/ADR-003`.
>
> **Note v1.3 — refonte du feature engineering.** Une première version produisait ~102
> features (rolling mean/std/min/max sur 3 fenêtres + lags + ratios bruts) qui *noyaient* le
> signal : l'AUC-ROC tombait à ~0.51. La pipeline a été recentrée sur 24 features
> physiquement motivées et standardisées par machine → AUC-ROC 0.82 (IF) / 0.93 (OC-SVM).

---

## Installation en 3 commandes

### Option A — Docker (recommandé)

```bash
git clone https://github.com/mounir-sanbouli/ocp-bionic-judge.git
cd ocp-bionic-judge
cp .env.example .env          # puis éditer .env

docker-compose up -d db       # démarrer PostgreSQL
docker-compose run --rm api python data/data_generator.py
docker-compose run --rm api python src/models/train.py
docker-compose up -d          # tout démarrer
```

→ API : http://localhost:8000/docs  
→ Frontend : http://localhost:5173  
→ MLflow : http://localhost:5000

### Option B — Local (dev) · Linux / macOS

```bash
git clone https://github.com/mounir-sanbouli/ocp-bionic-judge.git
cd ocp-bionic-judge
pip install -r requirements.txt
cp .env.example .env          # éditer DATABASE_URL

python data/data_generator.py     # génère les données capteurs
python -m src.models.train        # entraîne les 3 modèles
uvicorn api.main:app --reload     # FastAPI → localhost:8000
cd frontend && npm install && npm run dev   # React/Vite → localhost:5173
```

### Option C — Local (dev) · Windows PowerShell

Sur Windows, Python ne trouve pas le package `src` si on lance le script directement.
Il faut définir le `PYTHONPATH` ou utiliser le flag `-m` :

```powershell
git clone https://github.com/mounir-sanbouli/ocp-bionic-judge.git
cd ocp-bionic-judge
pip install -r requirements.txt
copy .env.example .env            # puis éditer .env dans le Bloc-notes

# Générer les données
$env:PYTHONPATH = "."; python data/data_generator.py

# Entraîner le modèle (deux syntaxes équivalentes)
python -m src.models.train
# ou : $env:PYTHONPATH = "."; python src/models/train.py

# Lancer l'API
$env:PYTHONPATH = "."; uvicorn api.main:app --reload

# Lancer le frontend (dans un autre terminal)
cd frontend; npm install; npm run dev
```

> **Note :** si tu vois `ModuleNotFoundError: No module named 'src.config'`, c'est que
> `PYTHONPATH` n'est pas défini. La commande `python -m src.models.train` règle ça
> automatiquement en traitant `src` comme un package du répertoire courant.

---

## Exemples d'API

```bash
# Health check
curl http://localhost:8000/health

# Analyser une machine
curl -X POST http://localhost:8000/analyze \
  -H "X-API-Key: ocp-bionic-dev-key" \
  -H "Content-Type: application/json" \
  -d '{"machine_id": "BROYEUR_01", "use_agent": false}'

# Décisions récentes critiques
curl "http://localhost:8000/decisions?severity=CRITICAL&limit=10" \
  -H "X-API-Key: ocp-bionic-dev-key"

# Métriques gouvernance 24h
curl "http://localhost:8000/governance-metrics?window=24h" \
  -H "X-API-Key: ocp-bionic-dev-key"
```

---

## Réentraîner le modèle

Si le dashboard affiche ~100% d'anomalies ou une dérive CRITICAL, c'est que le modèle
n'a pas encore été entraîné sur les données actuelles. Relance l'entraînement :

```bash
# Docker
docker compose run --rm api python -m src.models.train

# Linux / macOS local
python -m src.models.train

# Windows PowerShell
python -m src.models.train
# ou : $env:PYTHONPATH = "."; python src/models/train.py
```

Après l'entraînement, le taux d'anomalies doit revenir à ~2–5% et la dérive PSI
doit passer sous le seuil 0.2.

---

## Structure du projet

```
ocp-bionic-judge/
├── data/                    # Générateur de données + DB SQLite (dev)
├── src/
│   ├── db.py                # Engine SQLAlchemy central (PostgreSQL/SQLite)
│   ├── features/            # Pipeline feature engineering (24 features ciblées)
│   ├── models/              # train · predict · drift_detector
│   ├── agents/              # detection_agent · judge_agent (Gemini)
│   └── governance/          # Métriques gouvernance IA
├── api/                     # FastAPI — endpoints REST
├── frontend/                # React 18 + Vite + TypeScript — interface principale
├── dashboard/               # Streamlit (déprécié — conservé pour référence)
├── notebooks/
│   ├── 01_EDA.ipynb          # Analyse exploratoire des capteurs
│   ├── 02_model_training.ipynb  # Comparaison des 3 modèles
│   └── 03_shap_explainability.ipynb  # SHAP feature importance
├── tests/                   # 65+ tests pytest (couverture ≥ 75%)
├── docs/
│   ├── decisions/           # 7 ADRs (Architecture Decision Records)
│   ├── schemas/             # Schéma ERD + flux de données
│   └── runbooks/            # Procédures opérationnelles
├── docker-compose.yml       # PostgreSQL + API + Frontend + MLflow
├── Dockerfile
├── CHANGELOG.md
└── CONTRIBUTING.md
```

---

## Décisions techniques documentées

Chaque choix technique est documenté dans `docs/decisions/` avec le pourquoi, les alternatives évaluées, et quand changer :

| ADR | Décision | Statut |
|-----|---------|--------|
| [ADR-001](docs/decisions/ADR-001-python-version.md) | Python 3.11 | ✅ |
| [ADR-002](docs/decisions/ADR-002-database-sqlite-then-postgresql.md) | SQLite → PostgreSQL | ✅ |
| [ADR-003](docs/decisions/ADR-003-anomaly-detection-model.md) | Isolation Forest | ✅ |
| [ADR-004](docs/decisions/ADR-004-ai-agents-langchain-claude.md) | LangChain + Claude | ✅ |
| [ADR-005](docs/decisions/ADR-005-api-fastapi.md) | FastAPI | ✅ |
| [ADR-006](docs/decisions/ADR-006-explainability-shap.md) | SHAP | ✅ |
| [ADR-007](docs/decisions/ADR-007-mlflow-tracking.md) | MLflow | ✅ |

---

## Sécurité

- `API_SECRET_KEY` **doit** être défini dans `.env` — le serveur refuse de démarrer sans cette variable.
- Ne jamais committer le fichier `.env` (il est dans `.gitignore`).
- Pour retirer `venv/` du tracking git si déjà commité : `git rm -r --cached venv/`
- La clé API Gemini (`GEMINI_API_KEY`) ne transite jamais dans les logs (loguru masque les credentials).

---

## Contexte

Stage de fin d'études (2 mois) — OCP Group, Programme **Bionic** × Mistral AI  
 Safi — Encadrement : Équipe Data Science OCP  
**Mounir Sanbouli** — Université Ibn Zohr, Agadir (Data Science & IA)  
Contact : mounir.sanbouli.43@edu.uiz.ac.ma
