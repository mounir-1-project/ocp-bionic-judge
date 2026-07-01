# Changelog — OCP Bionic Judge

> **C'est quoi un CHANGELOG ?**  
> C'est l'historique de toutes les modifications du projet, version par version.
> Dans un vrai projet, chaque modification importante est documentée ici.
> Le format standard utilisé est [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/).

---

## Format

Chaque version contient ces sections :
- **Ajouté** : nouvelles fonctionnalités
- **Modifié** : changements dans des fonctionnalités existantes
- **Corrigé** : corrections de bugs
- **Supprimé** : fonctionnalités retirées
- **Sécurité** : corrections de vulnérabilités

---

## [1.3.0] — 2026-06-30

### Corrigé
- **Refonte du feature engineering — correction d'une dilution du signal** (ADR-003)
  - La pipeline produisait ~102 features (rolling mean/std/min/max sur 3 fenêtres + lags +
    ratios bruts) qui noyaient le signal d'anomalie : AUC-ROC mesuré ~0.51 (≈ hasard).
  - Recentrage sur **24 features** physiquement motivées et standardisées par machine
    (z-scores par machine, flags de coupure, z-scores locaux glissants, |deltas|, temporel).
  - Résultat : **AUC-ROC 0.82 (Isolation Forest déployé) / 0.93 (One-Class SVM, leader AUC)**,
    Average Precision 0.44, F1 optimal 0.47.
  - `RollingFeatureExtractor` calcule désormais un z-score local ; `DeltaFeatureExtractor` ne
    produit plus de lags ; `SensorRatioExtractor` retiré ; les capteurs bruts sont exclus des
    features du modèle.
- Alignement de toute la documentation (README, ADR-003/007, dashboard, guide, audit,
  notebooks) sur les chiffres réellement mesurés et reproductibles.

### Modifié
- **Déploiement explicite d'Isolation Forest** : `train.py` rapporte le classement des 3
  modèles par AUC-ROC mais déploie Isolation Forest (seul modèle compatible SHAP
  TreeExplainer + latence minimale — ADR-003 / ADR-006). `model_comparison.json` expose
  `deployed_model`, `auc_leader` et `deployment_rationale`.
- **MLflow rendu optionnel** dans `train.py` (`try/except`) — l'entraînement et la CI tournent
  sans MLflow, tracking complet conservé s'il est présent (ADR-007).

---

## [1.1.0] — 2024-02-10

### Modifié
- **Migration SQLite → PostgreSQL** (ADR-002)
  - Création de `src/db.py` avec engine SQLAlchemy centralisé
  - Suppression de tous les `import sqlite3` dans les modules
  - Remplacement des paramètres `?` (SQLite) par `:param` (SQLAlchemy)
  - `cursor.executescript()` → requêtes DDL individuelles compatibles PostgreSQL
  - `INSERT OR IGNORE` → `INSERT ... ON CONFLICT DO NOTHING`
  - `INTEGER AUTOINCREMENT` → `BIGSERIAL`
- Mise à jour `requirements.txt` : ajout `psycopg2-binary==2.9.9`
- Mise à jour `.env.example` : `DATABASE_URL` pointe vers PostgreSQL par défaut

### Corrigé
- `feature_engineering.py` : `fillna(method="bfill")` → `.bfill()` (dépréciation pandas 2.x)
- `tests/conftest.py` : fixtures migrent vers SQLAlchemy (SQLite in-memory pour tests)

### Ajouté
- `docs/decisions/` : 7 ADRs documentant toutes les décisions techniques
- `docs/schemas/database_schema.md` : schéma ERD complet avec descriptions
- `docs/schemas/data_flow.md` : diagramme de flux de données
- `docs/runbooks/runbook-operations.md` : procédures opérationnelles
- `CHANGELOG.md` (ce fichier)
- `CONTRIBUTING.md` : guide de contribution

---

## [1.0.0] — 2024-01-15 (Version initiale)

### Ajouté
- **Pipeline de données** : `data/data_generator.py`
  - Simulation de 5 machines phosphate (broyeur, pompe, convoyeur, réacteur, compresseur)
  - 3 types d'anomalies : spike (3%), drift (2h), sensor_cutoff (NaN)
  - Stockage SQLite avec 6 tables
  - 6 mois de données @ 30s = ~2.5M lignes

- **Feature Engineering** : `src/features/feature_engineering.py`
  - 6 transformers sklearn en pipeline
  - Rolling features sur 3 fenêtres (5min, 15min, 1h)
  - Z-score normalisé par machine
  - Lag features (t-1, t-5, t-10)

- **Modèles ML** : `src/models/`
  - Isolation Forest + One-Class SVM + HDBSCAN
  - GridSearchCV sur hyperparamètres
  - Tracking MLflow
  - SHAP explainability (TreeExplainer + KernelExplainer)
  - Drift detector (PSI + KS-test)

- **Agents IA** : `src/agents/`
  - Detection Agent : LangChain ReAct + Google Gemini 2.0 Flash
  - Judge Agent : évaluation 5 critères pondérés, score /10
  - Sortie Pydantic validée

- **Gouvernance** : `src/governance/governance.py`
  - Métriques sur 3 fenêtres (1h, 24h, 7j)
  - Alertes automatiques (confiance < 70%, désaccord > 30%)

- **API REST** : `api/main.py`
  - FastAPI avec auth X-API-Key
  - 4 endpoints : /analyze, /decisions, /governance-metrics, /health
  - Documentation Swagger auto-générée

- **Dashboard** : `dashboard/app.py`
  - Streamlit 3 pages avec Plotly Express
  - Auto-refresh 30s

- **Notebooks** : `notebooks/`
  - 01_EDA.ipynb : 10 visualisations annotées
  - 02_model_training.ipynb : courbes ROC, matrices de confusion
  - 03_shap_explainability.ipynb : waterfall plots, beeswarm

- **Tests** : `tests/`
  - 30+ tests unitaires et d'intégration
  - pytest avec coverage

- **CI/CD** : `.github/workflows/ci.yml`
  - GitHub Actions : install → pytest → coverage

---

## [Unreleased] — Fonctionnalités planifiées

### À faire
- [ ] **TimescaleDB** : migration de sensor_readings en hypertable (ADR-002)
- [ ] **Alembic** : gestion des migrations de schéma BDD versionnées
- [ ] **Streaming** : River pour apprentissage incrémental (nouvelles machines)
- [ ] **Authentification** : JWT tokens au lieu de clé API statique
- [ ] **Tests d'intégration** : pipeline complet bout en bout avec DB de test
- [ ] **Docker Compose** : PostgreSQL + API + Dashboard en un seul `docker-compose up`
- [ ] **Alertes email/SMS** : notifier les techniciens OCP sur anomalies CRITICAL
- [ ] **LSTM Autoencoder** : améliorer la détection des drifts lents multi-jours
