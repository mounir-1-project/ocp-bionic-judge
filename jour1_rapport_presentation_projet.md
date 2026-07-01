# JOUR 1 — Rapport de présentation du projet OCP Bionic Judge
### Format : soutenance — l'étudiant présente, le jury écoute

---

## 0. Arborescence complète du projet (commentée)

Voici l'arborescence réelle du projet (dossiers techniques uniquement — `venv/`, `node_modules/`, `.git/`, `mlruns/`, `__pycache__/` masqués car ce sont des dossiers générés/outils, pas du code écrit) :

```
ocp-bionic-judge/
│
├── data/                              ← COUCHE 1 : génération des données
│   ├── data_generator.py              → simule les capteurs des 5 machines
│   ├── ocp_bionic.db / -wal / -shm    → base SQLite (mode WAL)
│   ├── processed/
│   │   └── generation_summary.json    → résumé de la dernière génération
│   └── raw/                           → (réservé aux futurs imports de données réelles)
│
├── src/                               ← COUCHE 2 : code métier (cœur du projet)
│   ├── config.py                      → configuration centrale (.env)
│   ├── db.py                          → connexion base de données (SQLAlchemy)
│   │
│   ├── features/
│   │   └── feature_engineering.py     → transforme 5 capteurs → 24 features ciblées
│   │
│   ├── models/
│   │   ├── train.py                   → entraîne 3 modèles ML, garde le meilleur
│   │   ├── predict.py                 → applique le modèle, calcule scores + SHAP
│   │   └── drift_detector.py          → détecte la dérive des données (PSI/KS)
│   │
│   ├── agents/
│   │   ├── detection_agent.py         → agent IA ReAct (LangChain + Gemini)
│   │   └── judge_agent.py             → agent IA "juge" (appel direct Gemini)
│   │
│   └── governance/
│       └── governance.py              → métriques de gouvernance + alertes
│
├── api/                                ← COUCHE 3 : exposition HTTP
│   └── main.py                        → API FastAPI (12+ endpoints, auth, orchestration)
│
├── dashboard/                          ← COUCHE 4 : interface de visualisation (Python)
│   ├── app.py                         → dashboard Streamlit (Plotly)
│   └── assets/ocp_logo.png
│
├── frontend/                           ← (hors périmètre — React/TS/Vite)
│
├── models/
│   └── best_model.joblib              → modèle ML sélectionné + pipeline + seuils
│
├── mlruns/                              → historique des runs MLflow
│
├── migrations/                          ← gestion de schéma versionné (Alembic)
│   ├── env.py
│   ├── script.py.mako
│   └── versions/0001_initial_schema.py → migration initiale (6 tables)
│
├── notebooks/
│   ├── 01_EDA.ipynb                   → analyse exploratoire des données
│   ├── 02_model_training.ipynb        → entraînement et comparaison des modèles
│   └── 03_shap_explainability.ipynb   → exploration SHAP
│
├── tests/                               ← suite de tests pytest
│   ├── conftest.py                    → fixtures partagées (DB de test isolée)
│   ├── test_api.py / test_api_integration.py
│   ├── test_data_generator.py
│   ├── test_feature_engineering.py
│   ├── test_models.py / test_predict.py
│   ├── test_judge_agent.py
│   └── test_governance.py
│
├── docs/
│   ├── architecture.md                → vue d'ensemble des couches
│   ├── decisions/                     → 7 ADRs (Architecture Decision Records)
│   ├── schemas/
│   │   ├── database_schema.md         → ERD complet (voir section 10)
│   │   └── data_flow.md               → flux de données complet
│   └── runbooks/runbook-operations.md → procédures d'exploitation
│
├── reports/
│   ├── model_comparison.json          → comparaison AUC-ROC des 3 modèles
│   ├── governance_template.md
│   └── shap/                          → graphiques SHAP exportés
│
├── Dockerfile / docker-compose.yml     → conteneurisation
├── .github/workflows/ci.yml            → intégration continue (GitHub Actions)
├── Makefile                            → raccourcis (make generate, make train, ...)
├── alembic.ini                         → config Alembic
├── requirements.txt / pyproject.toml   → dépendances Python
└── .env / .env.example                 → secrets (clé Gemini, DATABASE_URL, JWT)
```

**Logique générale** : les données remontent de bas en haut. `data/` génère → `src/` transforme et décide → `api/` expose → `dashboard/` affiche. `docs/`, `tests/`, `migrations/`, Docker/CI sont des couches transversales (documentation, qualité, déploiement).

🔍 **À rechercher avant de continuer** : "monorepo project structure Python", "separation of concerns software architecture", "ce qu'est un ADR (Architecture Decision Record)".

---

## 1. Zoom sur `data/` — la couche de génération de données

### `data/data_generator.py`

C'est le point de départ de tout le projet : sans données, rien d'autre ne peut fonctionner.

**Bibliothèques importées** : `numpy` (génération aléatoire), `pandas` (construction de DataFrames), `loguru` (logs), `sqlalchemy.text` (requêtes SQL brutes), plus `src.config` et `src.db` (pour la connexion).

**Constantes structurantes** :
- `MACHINES` : liste de 5 dictionnaires, un par machine (`BROYEUR_01`, `POMPE_02`, `CONVOYEUR_03`, `REACTEUR_04`, `COMPRESSEUR_05`), chacune avec un `id`, un `name` (nom métier) et un `type`.
- `SENSOR_PROFILES` : un dictionnaire de dictionnaires — pour chaque type de machine, les 5 capteurs (`temperature`, `vibration`, `pression`, `courant`, `rpm`) ont un triplet `(moyenne, écart-type, bruit)`. C'est ce qui fait qu'un broyeur "chauffe" différemment d'un réacteur.
- `ANOMALY_RATE_SPIKE`, `ANOMALY_DRIFT_PROB`, `NAN_PROB`, `DRIFT_MAX_STEPS` : ces 4 constantes sont calibrées mathématiquement (le commentaire du fichier donne le calcul) pour obtenir ~4% d'anomalies au total — un taux réaliste pour de la maintenance industrielle.

**Fonction `_shift(ts)`** : convertit une heure en `"matin"`, `"soir"` ou `"nuit"` — c'est une feature métier simple (le comportement d'une machine change selon l'équipe qui la pilote).

**Fonction `generate_machine_data(machine, start, end, freq_seconds)`** — le cœur du générateur :
- Crée une série temporelle de timestamps avec `pd.date_range(..., freq="30s")`.
- Pour chaque capteur, génère un signal de base = `moyenne + composante saisonnière sinusoïdale + bruit gaussien` (via `np.linspace` + `np.sin` + `rng.normal`).
- Parcourt ensuite chaque pas de temps (`for i in range(n)`) et, avec de petites probabilités, injecte 3 types d'anomalies :
  - **spike** : un pic brutal sur un capteur aléatoire (`rng.uniform(3*std, 6*std)`), classé `WARNING` ou `CRITICAL` selon l'amplitude.
  - **drift** : une dérive progressive sur `DRIFT_MAX_STEPS` (120 pas = 1h) — la valeur s'éloigne lentement de la normale.
  - **sensor_cutoff** : le capteur renvoie `NaN` pendant une durée aléatoire (10 à 60 pas) — simule une coupure capteur.
- Chaque pas de temps marqué `is_anomalous[i] = True` est ensuite transformé en ligne dans `anomaly_records` (table `anomalies`).
- `np.clip()` borne chaque capteur dans ses limites physiques réalistes (ex : température entre 20°C et 90°C).
- Retourne un `DataFrame` (lignes = lectures capteurs) + une liste de dictionnaires (anomalies).

**Fonction `generate_all(months, freq_seconds)`** — orchestration :
- Calcule la période (`6 mois` par défaut).
- Appelle `get_engine()` + `init_schema()` (créent les tables si absentes — voir section 10).
- Insère les 5 machines dans la table `machines` (avec `ON CONFLICT DO NOTHING` / `INSERT OR IGNORE` selon le dialecte SQL — gère SQLite ET PostgreSQL dans le même code).
- Pour chaque machine, appelle `generate_machine_data()`, puis écrit le résultat avec `df.to_sql("sensor_readings", engine, if_exists="append", chunksize=100)`.
- Écrit un résumé JSON dans `data/processed/generation_summary.json`.

**Fonctions `init_db(conn)` et `insert_machines(conn)`** : versions "sqlite3 brut" (pas SQLAlchemy) des mêmes opérations, utilisées par les tests (`tests/conftest.py`) pour créer une base de test isolée rapidement.

### `data/ocp_bionic.db`, `-wal`, `-shm`

Ce sont les 3 fichiers d'une base **SQLite en mode WAL** (Write-Ahead Logging) : `.db` = données validées, `.db-wal` = écritures récentes pas encore fusionnées, `.db-shm` = mémoire partagée entre processus. Ce mode est activé explicitement dans `src/db.py` (`PRAGMA journal_mode=WAL`) pour permettre des accès concurrents (FastAPI lit pendant que `data_generator.py` écrit).

### `data/processed/generation_summary.json`

Petit fichier JSON récapitulatif (date de génération, période couverte, nombre de lignes, nombre d'anomalies, liste des machines) — utile pour vérifier rapidement qu'une génération a fonctionné sans interroger la base.

🔍 **À rechercher après cette section** :
- "numpy random default_rng seed reproducibility"
- "pandas date_range frequency string (30s, 1h...)"
- "simulating sensor data with sinusoidal seasonal pattern"
- "SQLite WAL mode explained"
- "SQL ON CONFLICT DO NOTHING vs INSERT OR IGNORE"

---

## 2. Zoom sur `src/` (racine) — configuration et connexion DB

### `src/config.py`

Le fichier le plus court mais le plus important — TOUT le projet dépend de lui.

- Appelle `load_dotenv()` **une seule fois**, en commentaire explicite : *"Load .env exactly once — idempotent but calling it 8× is unnecessary noise."*
- Définit les chemins de base : `BASE_DIR`, `DATA_DIR`, `MODEL_DIR` (via `pathlib.Path`).
- Définit `DATABASE_URL` (par défaut SQLite local, override possible via `.env`).
- Définit `GEMINI_MODEL` (`"gemini-2.0-flash"`) et `GEMINI_API_KEY`.
- Définit `LOG_LEVEL`, `API_SECRET_KEY`, `MLFLOW_TRACKING_URI`.

**Pattern important** : presque tous les autres fichiers du projet font `from src.config import GEMINI_MODEL  # noqa: F401 — ensures load_dotenv() called`, même s'ils n'utilisent pas Gemini. Ce n'est pas un import "utile" au sens strict — c'est un **effet de bord intentionnel** : importer `config.py` déclenche `load_dotenv()`, donc tous les modules sont sûrs d'avoir leurs variables d'environnement chargées, sans dépendre de l'ordre d'import.

### `src/db.py`

Point d'entrée unique pour la base de données.

- `get_engine(database_url=None)` : crée (ou réutilise) un **singleton** `Engine` SQLAlchemy (variable globale `_engine`). Détecte si l'URL commence par `sqlite` ou non :
  - SQLite : `connect_args={"check_same_thread": False}` (nécessaire car FastAPI utilise plusieurs threads) + active le mode WAL via un `@event.listens_for(engine, "connect")`.
  - PostgreSQL : configure un pool de connexions (`pool_size=5`, `max_overflow=10`, `pool_pre_ping=True`).
- `get_connection()` : context manager (`@contextmanager`) qui ouvre une transaction (`engine.begin()`) — gère automatiquement commit/rollback.
- `reset_engine()` : utilitaire de test pour repartir d'un état propre.
- `DDL_STATEMENTS` / `DDL_SQLITE` : la définition SQL des 6 tables (détail complet en section 10), avec une version PostgreSQL (`BIGSERIAL`, `DOUBLE PRECISION`) et une version SQLite (`INTEGER`, `REAL`) générée automatiquement par `.replace()`.
- `init_schema(engine=None)` : exécute le bon jeu de DDL selon `engine.dialect.name`.

**Pourquoi c'est central** : `data_generator.py`, `train.py`, `predict.py`, `drift_detector.py`, `governance.py`, `detection_agent.py`, `judge_agent.py` et `api/main.py` appellent TOUS `get_engine()`. Un seul endroit définit comment on parle à la base — si on migre SQLite → PostgreSQL, on ne change qu'ici (et `.env`).

🔍 **À rechercher après cette section** :
- "python-dotenv load_dotenv best practices"
- "SQLAlchemy create_engine singleton pattern"
- "Python context manager @contextmanager"
- "SQLAlchemy connection pooling pool_size max_overflow"
- "SQLite check_same_thread explained"

---

## 3. Zoom sur `src/features/feature_engineering.py` — fabrique de features

Ce fichier transforme **5 colonnes brutes** en **24 features numériques ciblées** exploitables par un modèle ML. Il contient **6 classes de transformation**, toutes héritant de `BaseEstimator, TransformerMixin` (le standard scikit-learn pour créer des étapes de pipeline custom), et chacune implémente `fit()` / `transform()`.

> **Pourquoi 24 et pas ~102 ?** Une première version produisait ~102 features (rolling
> mean/std/min/max sur 3 fenêtres + lags + ratios bruts). Sur un modèle d'isolation, où chaque
> coupure d'arbre tire UNE feature au hasard, ces ~95 features faiblement informatives noyaient
> les ~5 signaux réellement discriminants : l'AUC-ROC tombait à ~0.51 (≈ hasard). La pipeline a
> été recentrée sur 24 features physiquement motivées → AUC-ROC 0.82 (IF) / 0.93 (OC-SVM).

| Classe | Rôle | Colonnes produites |
|---|---|---|
| `SensorCutoffIndicator` | Détecte les `NaN` (coupures capteur), les remplace par la médiane | 5 flags `*_is_nan` |
| `TemporalFeatureExtractor` | Extrait des infos calendaires depuis `timestamp` | `hour`, `day_of_week`, `is_weekend`, `shift_encoded` (4) |
| `ZScoreNormalizer` | Normalise chaque capteur par rapport à sa propre machine (`fit` apprend moyenne/écart-type **par machine**) | 5 `*_zscore` |
| `RollingFeatureExtractor` | Z-score *local* glissant `(x - rolling_mean)/rolling_std` (fenêtre courte ≈20 min), **par machine** | 5 `*_local_z` |
| `DeltaFeatureExtractor` | Variation instantanée absolue d'un pas à l'autre, **par machine** | 5 `*_delta` |
| `FinalScaler` | Mise à l'échelle finale : `StandardScaler` sur les features continues (hors capteurs bruts et flags 0/1) | (aucune nouvelle colonne — transforme les valeurs existantes) |

**Détails techniques importants** :
- `RollingFeatureExtractor` et `DeltaFeatureExtractor` font `X.groupby("machine_id", sort=False)` puis traitent chaque groupe séparément avant de les recoller avec `pd.concat()` — **chaque machine a ses propres statistiques**, on ne mélange jamais les séries temporelles de deux machines.
- `ZScoreNormalizer.fit()` est **stateful** : il stocke `self._stats[machine_id][sensor] = (mean, std)` — c'est le seul transformer (avec `FinalScaler`) qui "apprend" quelque chose pendant `fit()`. Les autres sont "stateless" (`fit` ne fait que `return self`).
- Les **5 capteurs bruts** restent dans le DataFrame pour le calcul mais sont **exclus des features du modèle** (`get_numeric_feature_cols` les retire) : à l'échelle brute ils encodent surtout l'identité de la machine, pas l'anomalie.

**Fonction `build_feature_pipeline(scale=True)`** : assemble les 6 transformers (5 si `scale=False`) dans un `sklearn.pipeline.Pipeline` — **l'ordre est important** : `cutoff → temporal → zscore → rolling → delta → scaler`. Par exemple, `cutoff` doit s'exécuter en premier pour calculer les flags `*_is_nan` avant le remplissage par la médiane.

**Fonction `get_numeric_feature_cols(df)`** : retourne les 24 colonnes-features du modèle, en excluant les colonnes "méta" ET les 5 capteurs bruts (`machine_id`, `timestamp`, `shift`, `id`, `temperature`, …).

**Fonction `extract_model_features(df)`** : une version **simplifiée à 15 features** (5 capteurs + rolling mean + rolling std), utilisée uniquement par les tests unitaires — ne pas la confondre avec le pipeline complet à 24 features utilisé en production.

**Fonction `load_raw_data(machine_id=None, limit=None)`** : lit `sensor_readings` via `pd.read_sql(text(query), conn, params=params)` — requête **paramétrée** (pas de f-string dans le SQL → protection contre l'injection SQL).

🔍 **À rechercher après cette section** :
- "sklearn BaseEstimator TransformerMixin custom transformer tutorial"
- "sklearn Pipeline order of steps matters"
- "pandas groupby transform vs apply"
- "StandardScaler vs RobustScaler difference"
- "z-score normalization per group"
- "SQL injection parameterized queries pandas read_sql"

---

## 4. Zoom sur `src/models/` — entraînement, inférence, dérive

### `src/models/train.py`

**Bibliothèques** : `numpy`, `pandas`, `joblib` (sérialisation), `mlflow` + `mlflow.sklearn` (tracking), `hdbscan`, `sklearn.ensemble.IsolationForest`, `sklearn.svm.OneClassSVM`, `sklearn.model_selection.ParameterGrid`, `sklearn.metrics` (plusieurs métriques).

**Classe `HDBSCANWrapper`** : HDBSCAN n'a pas nativement la même interface que les modèles sklearn (`fit/predict/decision_function`). Cette classe l'encapsule pour lui donner :
- `fit(X)` : entraîne `hdbscan.HDBSCAN`, calcule un seuil = 95e percentile de `outlier_scores_`.
- `predict(X)` : utilise `approximate_predict()` + le seuil appris pour classer chaque point.
- `decision_function(X)` : retourne un score continu d'anomalie.
- `get_params()` / `set_params()` : pour la compatibilité avec `ParameterGrid` de sklearn.

**Fonction `load_training_data(db_path)`** : charge `sensor_readings` (features brutes) et `anomalies` (vérité terrain) depuis SQLite, retourne `(DataFrame, y_true array)`.

**Fonction `chronological_split(df, ...)`** : trie par `timestamp` et coupe à 80% / 20% — **PAS de split aléatoire** (sinon le modèle "verrait" indirectement le futur pendant l'entraînement, c'est de la fuite de données temporelle).

**Fonction `_f1_at_optimal_threshold(y_true, scores)`** : balaye plusieurs seuils pour trouver celui qui maximise le F1-score (utile car les modèles non supervisés ne fournissent qu'un score continu, pas une classe).

**Fonction `evaluate_model(...)`** : calcule un dictionnaire de métriques (AUC-ROC, F1, precision, recall...) pour un modèle donné sur le jeu de test.

**Trois fonctions d'entraînement, une par algorithme** :
- `train_isolation_forest(...)` : utilise `ParameterGrid` pour tester plusieurs combinaisons de `contamination`/`n_estimators`, garde la meilleure selon AUC-ROC.
- `train_one_class_svm(...)` : **sous-échantillonne à 10 000 lignes** avant l'entraînement (OC-SVM est en `O(n²)` ou pire — trop lent sur 2,5M lignes).
- `train_hdbscan(...)` : **sous-échantillonne à 50 000 lignes**, utilise `HDBSCANWrapper`.

**Fonction `train_all(db_path)`** — orchestration complète :
1. `load_training_data()` → `chronological_split()`.
2. `build_feature_pipeline()` → `pipeline.fit_transform(train)` puis `pipeline.transform(test)` (jamais `fit` sur le test).
3. Pour chacun des 3 modèles : `with mlflow.start_run(run_name=...)`, entraînement, `evaluate_model()`, `mlflow.log_param()` / `log_metric()` / `mlflow.sklearn.log_model()`.
4. Sélectionne le modèle avec le meilleur AUC-ROC.
5. Calcule `severity_thresholds` = percentiles 30 et 70 des scores du modèle gagnant sur le train.
6. Sauvegarde le **bundle** complet avec `joblib.dump()` :
   ```python
   {"model": ..., "name": ..., "pipeline": ..., "feature_cols": [...],
    "metrics": {...}, "severity_thresholds": {"p30": ..., "p70": ...}}
   ```
   → fichier `models/best_model.joblib`.

### `src/models/predict.py`

**Bibliothèques** : `joblib`, `numpy`, `pandas`, `shap`.

- `load_model(model_path)` : charge le bundle une seule fois (mis en cache via une variable globale).
- `invalidate_model_cache()` : force un rechargement (utile après un nouvel entraînement).
- `_apply_pipeline(df, bundle)` : applique `bundle["pipeline"].transform(df)` (jamais `fit`) et sélectionne `bundle["feature_cols"]`.
- `_score_to_severity(score, p30, p70)` : règle simple — `score <= p30 → NORMAL`, `score <= p70 → WARNING`, sinon `CRITICAL`.
- `generate_shap_explanation(...)` : choisit `shap.TreeExplainer` si le modèle est l'Isolation Forest (rapide, basé arbres), sinon `shap.KernelExplainer` (plus lent, model-agnostic) pour OC-SVM/HDBSCAN. Extrait les 3 features les plus influentes.
- `predict(...)` : pipeline complet — charge le bundle, applique `_apply_pipeline`, calcule le score brut du modèle, le **normalise en [0,1]** puis **l'inverse si nécessaire** (pour IF et OC-SVM, un score "normal" est positif ; on veut que "1 = anormal"), applique `_score_to_severity`, génère SHAP, retourne un DataFrame enrichi.
- `_save_predictions(df, engine)` : déduplique (évite d'insérer deux fois la même `(machine_id, timestamp)`) puis `to_sql("ml_decisions", ...)`.

### `src/models/drift_detector.py`

**Bibliothèques** : `numpy`, `pandas`, `scipy.stats`.

- `compute_psi(reference, current, n_bins)` : implémente le **Population Stability Index** — découpe les deux distributions en `n_bins` bacs, compare les proportions, somme `(p_ref - p_cur) * ln(p_ref / p_cur)`.
- `compute_ks_test(reference, current)` : applique `scipy.stats.ks_2samp` — retourne `(statistique, p-value)`.
- `_load_scores_sqlite(db_path, n, oldest)` / `_load_scores(...)` : récupère les `n` scores les plus anciens (référence) ou les plus récents (courant) depuis `ml_decisions`.
- `_save_drift_result(...)` : écrit le résultat dans `audit_log` avec `event_type="DRIFT_CHECK"`.
- `check_drift(...)` : orchestration — compare 5000 scores anciens vs 100 récents, applique les seuils (`PSI > 0.2` ou `p-value < 0.05` → alerte), respecte un cooldown de 15 minutes pour ne pas spammer `audit_log`.

🔍 **À rechercher après cette section** :
- "Isolation Forest algorithm explained" / "One-Class SVM kernel rbf nu parameter" / "HDBSCAN outlier_scores_ explained"
- "ParameterGrid sklearn grid search manual"
- "MLflow start_run log_param log_metric log_model"
- "joblib dump load Python serialization"
- "chronological train test split time series data leakage"
- "SHAP TreeExplainer vs KernelExplainer"
- "Population Stability Index (PSI) formula"
- "Kolmogorov-Smirnov two-sample test scipy"

---

## 5. Zoom sur `src/agents/` — les deux agents IA

### `src/agents/detection_agent.py` (agent ReAct)

**Bibliothèques** : `langchain.agents` (`AgentExecutor`, `create_react_agent`), `langchain.prompts.PromptTemplate`, `langchain_google_genai.ChatGoogleGenerativeAI`, `langchain_core.tools.tool`, `pydantic`, `threading`.

- **Classe `AgentDecision(BaseModel)`** : schéma Pydantic de la sortie de l'agent (diagnostic, sévérité, confiance, actions recommandées, etc. — avec contraintes `Field(ge=..., le=..., pattern=...)`).
- **3 outils `@tool`** — chacun est une fonction Python normale, décorée, avec une docstring qui sert de "mode d'emploi" pour le LLM :
  - `get_anomaly_data(machine_id, n=10)` : requête SQL sur `ml_decisions` (+ `sensor_readings`), retourne les `n` dernières anomalies en JSON texte.
  - `get_machine_history(machine_id, days=7)` : statistiques historiques (moyennes, écarts-types) sur `sensor_readings`.
  - `get_shap_explanation(anomaly_id)` : relit `features_json` depuis `ml_decisions` pour une décision donnée.
- **`build_detection_agent()`** : construit le `SYSTEM_PROMPT` (qui contient les plages normales des 5 machines + un protocole d'analyse en 4 étapes), crée un `PromptTemplate`, instancie `ChatGoogleGenerativeAI(model=GEMINI_MODEL, temperature=0.1, max_output_tokens=2048)`, puis `create_react_agent(llm, tools, prompt)` enveloppé dans un `AgentExecutor(max_iterations=6, max_execution_time=60)`.
- **`_get_agent()`** : singleton thread-safe (`threading.Lock`) — un seul `AgentExecutor` est créé et réutilisé.
- **`analyze_machine(machine_id, executor=None)`** : lance l'agent sur une question concernant la machine, récupère la sortie texte, extrait le JSON par regex, et instancie `AgentDecision(**data)`.

**Le cycle ReAct** : à chaque itération, le LLM produit `Thought: ... / Action: <nom_outil> / Action Input: {...}`, LangChain exécute l'outil et injecte le résultat comme `Observation: ...` dans le prompt suivant, jusqu'à ce que le LLM produise `Final Answer: ...` ou que `max_iterations` soit atteint.

### `src/agents/judge_agent.py` (appel direct, PAS ReAct)

**Bibliothèques** : `langchain_google_genai.ChatGoogleGenerativeAI`, `langchain_core.messages.SystemMessage, HumanMessage`, `pydantic`.

- **`JudgeInput(BaseModel)`** : ce que le Judge reçoit (la décision de l'agent Detection + le contexte).
- **`CriteriaScores(BaseModel)`** : les 5 sous-scores (pertinence 25%, cohérence historique 20%, confiance calibrée 20%, conformité OCP 20%, faisabilité 15%).
- **`JudgeEvaluation(BaseModel)`** : sortie complète (score global, sous-scores, `agreement`, `feedback`, `flagged_issues`).
- **`class JudgeAgent`** : encapsule un appel **unique** au LLM — construit un `SystemMessage` (la grille d'évaluation `JUDGE_SYSTEM`) + un `HumanMessage` (le `JudgeInput` sérialisé en JSON), appelle `llm.invoke([...])`, parse le JSON de réponse en `JudgeEvaluation`.
- **Étape critique** : après le parsing, le code **recalcule** `evaluation.agreement = (evaluation.global_score >= DISAGREEMENT_THRESHOLD)` — il ne fait PAS confiance au booléen renvoyé par le LLM, pour éviter qu'une incohérence du LLM (score=8 mais agreement=False) ne se propage.
- **`_save_evaluation(ev, machine_id)`** : écrit dans `judge_evaluations`.
- **`judge_decision(...)`** : fonction d'entrée publique, utilisée par `api/main.py`.

**Différence architecturale fondamentale (à bien retenir)** :
| | Detection Agent | Judge Agent |
|---|---|---|
| Pattern | ReAct (boucle Thought/Action/Observation) | Appel LLM direct, un seul tour |
| Outils | 3 `@tool` (accès DB) | aucun |
| Entrée | un `machine_id` | la sortie du Detection Agent (en mémoire) |
| Pourquoi | doit "explorer" les données pour diagnostiquer | a déjà toutes les infos nécessaires, doit juste "noter" |

🔍 **À rechercher après cette section** :
- "LangChain @tool decorator how it works"
- "LangChain create_react_agent AgentExecutor max_iterations"
- "ReAct prompting pattern LLM Thought Action Observation"
- "ChatGoogleGenerativeAI temperature parameter effect"
- "Pydantic BaseModel Field validation constraints"
- "LLM as a judge pattern evaluation"
- "SystemMessage vs HumanMessage LangChain"

---

## 6. Zoom sur `src/governance/governance.py`

**Bibliothèques** : `pandas`, `sqlalchemy.text`, importe `compute_psi` depuis `drift_detector`.

- **`compute_metrics(window="24h", db_path=None)`** : pour une fenêtre temporelle donnée (`"1h"`, `"24h"`, `"7d"`), lit `judge_evaluations` et `ml_decisions` sur cette période et calcule :
  - `mean_judge_confidence` (moyenne de `global_score / 10`)
  - `disagreement_rate` (proportion de `agreement = 0`)
  - `judge_score_drift` (comparaison avec une période antérieure, via `compute_psi`)
  - `ocp_compliance_rate` (moyenne de `compliance_score`)
  - `critical_unresolved` (nombre de décisions `CRITICAL` sans évaluation Judge)
  - `per_machine` : le même détail, ventilé par machine.
- **Seuils d'alerte** : `LOW_CONFIDENCE` si confiance < 0.70, `HIGH_DISAGREEMENT` si taux de désaccord > 0.30, `CRITICAL_BACKLOG` si `critical_unresolved` > 5. Chaque alerte déclenchée est écrite dans `audit_log` (`event_type="GOVERNANCE_ALERT"`), avec un cooldown de 10 minutes (`event_type="GOVERNANCE_REPORT"` pour les rapports périodiques).
- **`get_all_windows()`** : appelle `compute_metrics()` pour les 3 fenêtres et retourne un dictionnaire combiné — c'est ce qu'expose l'endpoint `/governance-metrics`.

🔍 **À rechercher après cette section** :
- "AI system monitoring metrics dashboard design"
- "alerting cooldown pattern to avoid spam"
- "sliding time window aggregation pandas"

---

## 7. Zoom sur `api/main.py` — l'API FastAPI (fichier unique, ~900 lignes)

**Bibliothèques** : `fastapi` (`FastAPI`, `Cookie`, `Depends`, `HTTPException`, `Query`, `Request`, `Response`, `Security`), `fastapi.security.APIKeyHeader`, `fastapi.middleware.cors.CORSMiddleware`, `slowapi` (`Limiter`, `_rate_limit_exceeded_handler`, `get_remote_address`), `jwt` (PyJWT), `pandas`, `asyncio`, `concurrent.futures.ThreadPoolExecutor`.

**`class MachineId(str, Enum)`** : énumère les 5 IDs valides. Tout endpoint qui prend un `machine_id: MachineId` rejette automatiquement (HTTP 422) un ID inconnu — validation gratuite grâce à FastAPI/Pydantic.

**Schémas Pydantic** (modèles de requête/réponse) :
- `LoginRequest`, `AnalyzeRequest`, `AnalyzeResponse`, `DecisionRecord`, `GovernanceMetrics`, `HealthResponse`.

**Authentification (double mécanisme)** :
- `APIKeyHeader` : header `X-API-Key`, comparé à `API_SECRET_KEY` (depuis `config.py`).
- JWT : cookie httpOnly `ocp_session`, signé avec `_JWT_SECRET` (HS256, durée `_JWT_HOURS=8`). `/auth/login` génère le cookie, `/auth/me` le vérifie, `/auth/logout` l'efface.
- `slowapi.Limiter` : limite le nombre de requêtes par IP (`get_remote_address`), renvoie 429 via `_rate_limit_exceeded_handler` en cas de dépassement.

**Fonctions utilitaires internes** :
- `_db_read(sql, params)` : wrapper `pd.read_sql` réutilisé par tous les endpoints "lecture".
- `_check_db()` / `_check_model()` : vérifications de santé pour `/health`.
- `_analyze_sync(req: AnalyzeRequest) -> AnalyzeResponse` : **fonction d'orchestration centrale**, exécutée dans un thread (voir ci-dessous). Elle enchaîne :
  1. `predict()` (depuis `predict.py`) → écrit `ml_decisions`.
  2. si `req.use_agent` : `analyze_machine()` (Detection Agent).
  3. si `req.run_judge` : `judge_decision()` (Judge Agent).
  4. Assemble tout dans un `AnalyzeResponse`.

**Pont synchrone/asynchrone** : FastAPI est async, mais `predict()`, les agents LangChain, et les requêtes SQL synchrones sont **bloquants**. L'endpoint `/analyze` fait :
```python
loop = asyncio.get_running_loop()
result = await loop.run_in_executor(_AGENT_POOL, _analyze_sync, req)
```
avec `_AGENT_POOL = ThreadPoolExecutor(max_workers=4)` — jusqu'à 4 analyses peuvent tourner en parallèle sans bloquer le serveur pour les autres requêtes (ex : `/health`).

**Inventaire des endpoints** (12, regroupés par tag) :

| Méthode + chemin | Tag | Rôle |
|---|---|---|
| `GET /docs` (custom HTML) | — | documentation enrichie (logo encodé en base64) |
| `POST /auth/login` | Auth | génère le cookie JWT |
| `GET /auth/me` | Auth | vérifie la session courante |
| `POST /auth/logout` | Auth | invalide le cookie |
| `GET /api/summary` | Dashboard | résumé global (public, sans auth) |
| `GET /api/sensors/{machine_id}` | Dashboard | dernières lectures capteurs |
| `GET /api/judge-evals` | Dashboard | évaluations du Judge |
| `GET /api/audit-log` | Dashboard | journal d'audit |
| `GET /health` | System | statut DB + modèle |
| `POST /analyze` | Detection | déclenche `_analyze_sync` |
| `GET /decisions` | Decisions | liste des `ml_decisions` |
| `GET /governance-metrics` | Governance | appelle `governance.get_all_windows()` |
| `GET /api/drift` | Dashboard | appelle `drift_detector.check_drift()` |

🔍 **À rechercher après cette section** :
- "FastAPI Enum path parameter automatic validation"
- "FastAPI dependency injection Depends Security"
- "JWT httpOnly cookie vs Authorization header security"
- "slowapi rate limiting FastAPI tutorial"
- "Python ThreadPoolExecutor run_in_executor asyncio bridge"
- "FastAPI CORS middleware configuration"

---

## 8. Zoom sur `dashboard/app.py` — interface Streamlit

**Bibliothèques** : `streamlit` (`st`), `plotly.graph_objects` / `plotly.express`, `pandas`, `sqlite3`, `python-dotenv`.

- `st.set_page_config(...)` : configure la page (titre, layout large, icône).
- Fonctions `q(sql, params)`, `sensor_data()`, `decisions()`, `judge_evals()`, `audit_log()` : requêtes directes (via `sqlite3`, pas l'API) vers `data/ocp_bionic.db` — le dashboard lit la base **directement**, il ne passe pas par `api/main.py`.
- Fonctions de présentation : `metric()`, `section()`, `page_header()`, `alert()` — génèrent du HTML/CSS injecté via `st.markdown(..., unsafe_allow_html=True)` pour un look personnalisé (CSS custom stocké dans `_CSS`).
- `_model_metrics()` : charge `reports/model_comparison.json` pour afficher l'AUC-ROC du modèle sélectionné.
- Graphiques construits avec `plotly.graph_objects.Figure` et `plotly.express` (séries temporelles des capteurs, distribution des scores, etc.).

**Remarque architecturale** : ce dashboard est un outil de visualisation **séparé** de l'API — il a son propre accès direct à la base. C'est différent du `frontend/` (React), qui lui consomme l'API REST.

🔍 **À rechercher après cette section** :
- "Streamlit tutorial layout columns metrics"
- "Plotly express vs graph_objects difference"
- "st.markdown unsafe_allow_html custom CSS Streamlit"

---

## 9. Zoom rapide sur les dossiers transversaux

### `tests/`
- `conftest.py` : fixtures pytest — crée une base SQLite **en mémoire ou temporaire** via `init_db()`/`insert_machines()` (les versions sqlite3 de `data_generator.py`), isolée de `data/ocp_bionic.db`.
- `test_api.py`, `test_api_integration.py` : utilisent `fastapi.testclient.TestClient` pour simuler des requêtes HTTP.
- `test_data_generator.py`, `test_feature_engineering.py`, `test_models.py`, `test_predict.py`, `test_judge_agent.py`, `test_governance.py` : un fichier de test par module métier — couverture quasi 1:1 avec `src/`.

### `notebooks/`
- `01_EDA.ipynb` : analyse exploratoire (distributions, corrélations, visualisation des anomalies).
- `02_model_training.ipynb` : reproduit `train_all()` de manière interactive, compare les courbes Precision-Recall des 3 modèles.
- `03_shap_explainability.ipynb` : explore les explications SHAP (waterfall plots).

### `migrations/` (Alembic)
- `0001_initial_schema.py` : la **même** définition des 6 tables que `src/db.py::DDL_STATEMENTS`, mais sous forme de migration versionnée (`revision`, `down_revision`). Permet de faire évoluer le schéma en production sans perte de données (futurs `0002_...py`, etc.).

### `docs/`
- `architecture.md` : diagramme en couches (présentation/API/notebooks → métier → données) + tableau de responsabilités + roadmap v1→v3.
- `decisions/ADR-001` à `ADR-007` : 7 décisions techniques documentées (Python 3.11, SQLite→PostgreSQL, Isolation Forest, LangChain+Gemini, FastAPI, SHAP, MLflow) avec contexte/alternatives/conséquences.
- `schemas/database_schema.md` et `data_flow.md` : voir section 10 — ce sont les documents de référence pour le schéma de données.
- `runbooks/runbook-operations.md` : procédures opérationnelles (que faire en cas d'incident).

### `models/best_model.joblib` et `mlruns/`
- `best_model.joblib` : le **bundle** produit par `train_all()` — l'objet pivot entre entraînement et inférence (section 4).
- `mlruns/` : stockage local MLflow — un dossier par run d'entraînement, avec paramètres/métriques/artefacts.

### `reports/`
- `model_comparison.json` : pour chacun des 3 modèles, ses hyperparamètres et métriques (AUC-ROC, F1...), plus le champ `best_model`.
- `shap/` : graphiques SHAP exportés en image.

### `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`, `Makefile`
- `Dockerfile` : image Python avec dépendances installées, point d'entrée = `uvicorn api.main:app`.
- `docker-compose.yml` : orchestre les services (API + éventuellement PostgreSQL + dashboard).
- `ci.yml` : pipeline GitHub Actions — à chaque push, installe les dépendances, lance `pytest`, vérifie le linting.
- `Makefile` : raccourcis (`make generate`, `make train`, `make test`, `make run`...).

🔍 **À rechercher après cette section** :
- "pytest fixtures conftest.py explained"
- "FastAPI TestClient how it works"
- "Jupyter notebook role in data science workflow"
- "Alembic migrations revision down_revision"
- "Dockerfile vs docker-compose difference"
- "GitHub Actions workflow YAML basics"

---

## 10. Schéma complet de la base de données

### Vue d'ensemble — 6 tables, 1 base SQLite (dev) / PostgreSQL (prod)

```
machines (référentiel, 5 lignes fixes)
   │ 1
   │
   ├──N──► sensor_readings   (table principale, ~2.5M lignes/6 mois)
   │
   ├──N──► anomalies          (vérité terrain, ~4000 lignes/6 mois)
   │
   ├──N──► ml_decisions       (sorties du modèle ML, ~2.5M lignes/6 mois)
   │            │ 1
   │            │
   │            └──N──► judge_evaluations  (évaluations du Judge, ~1000 lignes)
   │
   └──N──► audit_log          (journal universel, ~5000 lignes)
```

### Table 1 — `machines` (référentiel)

```sql
CREATE TABLE machines (
    id          TEXT PRIMARY KEY,        -- "BROYEUR_01", "POMPE_02", ...
    name        TEXT NOT NULL,           -- "Broyeur à Boulets"
    type        TEXT NOT NULL,           -- broyeur | pompe | convoyeur | reacteur | compresseur
    location    TEXT,                    -- "Khouribga Site A", ...
    installed   TEXT,                    -- date de mise en service
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```
- **Écrit par** : `data_generator.py::generate_all()` (une fois, au début).
- **Lu par** : essentiellement implicite — sert de référence pour `MachineId` Enum dans `api/main.py` et pour les jointures conceptuelles (pas de vraies foreign keys actives en SQLite par défaut, mais déclarées dans le DDL).
- **Cardinalité** : 5 lignes, ne change jamais.

### Table 2 — `sensor_readings` (haute volumétrie)

```sql
CREATE TABLE sensor_readings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_id  TEXT NOT NULL REFERENCES machines(id),
    timestamp   TEXT NOT NULL,           -- ISO 8601
    temperature REAL,                    -- °C [20-90], NULL = coupure capteur
    vibration   REAL,                    -- mm/s [0-10]
    pression    REAL,                    -- bar [1-10]
    courant     REAL,                    -- A [0-50]
    rpm         REAL,                    -- tr/min [0-3000]
    shift       TEXT                     -- matin | soir | nuit
)
-- + INDEX (machine_id, timestamp)
```
- **Écrit par** : `data_generator.py` (simulation) — en production, remplacé par de vrais capteurs.
- **Lu par** : `feature_engineering.py::load_raw_data()`, `train.py::load_training_data()`, `predict.py` (lectures récentes à scorer), `detection_agent.py` (outil `get_machine_history`), `dashboard/app.py`, `api/main.py` (`/api/sensors/{machine_id}`).
- **Point clé** : les `NULL` sont **intentionnels** — ils représentent une coupure capteur (anomalie `sensor_cutoff`), traités par `SensorCutoffIndicator`.
- **Index `(machine_id, timestamp)`** : critique — sans lui, une requête filtrée par machine+période scanne toute la table.

### Table 3 — `anomalies` (vérité terrain / labels)

```sql
CREATE TABLE anomalies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_id      TEXT NOT NULL REFERENCES machines(id),
    timestamp       TEXT NOT NULL,
    anomaly_type    TEXT NOT NULL,       -- spike | drift | sensor_cutoff | labeled
    sensor_affected TEXT,                -- temperature | vibration | ... | any
    severity        TEXT,                -- WARNING | CRITICAL
    injected        INTEGER DEFAULT 1    -- 1 = simulé, 0 = réel confirmé
)
```
- **Écrit par** : `data_generator.py` (anomalies injectées pendant la simulation).
- **Lu par** : `train.py::load_training_data()` — sert de `y_true` pour calculer AUC-ROC/F1 (évaluation hors-ligne uniquement, **jamais** utilisée comme feature d'entrée du modèle — sinon ce serait de l'apprentissage supervisé déguisé).
- **Remarque projet réel** : en production, `injected=0` contiendrait les anomalies confirmées par un technicien — base d'un futur modèle supervisé.

### Table 4 — `ml_decisions` (sorties du modèle, production)

```sql
CREATE TABLE ml_decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_id      TEXT NOT NULL,
    timestamp       TEXT NOT NULL,           -- timestamp de la lecture scorée
    anomaly_score   REAL,                    -- [0.0-1.0], 0=normal, 1=anomalie
    is_anomaly      INTEGER,                 -- 0 ou 1
    severity        TEXT,                    -- NORMAL | WARNING | CRITICAL
    model_version   TEXT,                    -- "IsolationForest" | "OneClassSVM" | "HDBSCAN"
    inference_ms    REAL,                    -- temps d'inférence (monitoring perf)
    features_json   TEXT,                    -- top-3 features SHAP en JSON
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```
- **Écrit par** : `predict.py::_save_predictions()` (avec déduplication sur `(machine_id, timestamp)`).
- **Lu par** : `detection_agent.py` (outils `get_anomaly_data`, `get_shap_explanation`), `drift_detector.py` (scores de référence/courants), `governance.py` (métriques), `api/main.py` (`/decisions`), `dashboard/app.py`.
- **Colonne clé `inference_ms`** : si la moyenne dépasse un seuil, le modèle est trop lent pour de l'inférence temps réel.
- **`features_json`** : permet de réafficher l'explication SHAP sans recalculer (SHAP est coûteux, surtout `KernelExplainer`).

### Table 5 — `judge_evaluations` (évaluations du Judge)

```sql
CREATE TABLE judge_evaluations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id         INTEGER REFERENCES ml_decisions(id),
    machine_id          TEXT NOT NULL,
    timestamp           TEXT NOT NULL,
    global_score        REAL,    -- [0.0-10.0] score pondéré final
    relevance_score     REAL,    -- critère 1, poids 25%
    history_score       REAL,    -- critère 2, poids 20%
    confidence_score    REAL,    -- critère 3, poids 20%
    compliance_score    REAL,    -- critère 4, poids 20%
    feasibility_score   REAL,    -- critère 5, poids 15%
    agreement           INTEGER, -- 1=accord, 0=désaccord (recalculé : global_score >= 6)
    feedback            TEXT,    -- explication textuelle
    flagged_issues      TEXT,    -- JSON array, ex: ["OVERCONFIDENCE", "VAGUE_DIAGNOSIS"]
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```
- **Écrit par** : `judge_agent.py::_save_evaluation()`.
- **Lu par** : `governance.py::compute_metrics()` (confiance moyenne, taux de désaccord, drift du score Judge), `api/main.py` (`/api/judge-evals`), `dashboard/app.py`.
- **Relation `decision_id → ml_decisions.id`** : c'est la SEULE foreign key "fonctionnelle" entre tables de résultats — relie une évaluation à la décision ML qu'elle juge.

### Table 6 — `audit_log` (journal universel)

```sql
CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    event_type  TEXT NOT NULL,       -- DRIFT_CHECK | GOVERNANCE_ALERT | GOVERNANCE_REPORT | ...
    machine_id  TEXT,                -- NULL pour événements globaux (ex: drift global)
    user_id     TEXT DEFAULT 'system',
    action      TEXT NOT NULL,
    details     TEXT,                -- JSON complet de l'événement
    severity    TEXT DEFAULT 'INFO'  -- INFO | WARNING | CRITICAL
)
```
- **Écrit par** : `drift_detector.py::_save_drift_result()` (event_type=`DRIFT_CHECK`), `governance.py` (alertes/rapports).
- **Lu par** : `api/main.py` (`/api/audit-log`), `dashboard/app.py`.
- **Rôle** : table de conformité — toute décision automatique du système (drift détecté, alerte de gouvernance) y laisse une trace, indépendamment des autres tables.

### Flux de données entre les tables (synthèse)

```
sensor_readings ──(feature pipeline + modèle ML)──► ml_decisions
                                                          │
                          ┌───────────────────────────────┤
                          │ (Detection Agent lit            │
                          │  ml_decisions + sensor_readings)│
                          ▼                                 │
                   AgentDecision (en mémoire)               │
                          │                                 │
                          │ (Judge Agent évalue)            │
                          ▼                                 │
                   judge_evaluations ◄──────────────────────┘
                          │
                          │ (Governance agrège)
                          ▼
                     audit_log  ◄── drift_detector (PSI/KS sur ml_decisions)
```

🔍 **À rechercher après cette section** :
- "Entity-Relationship Diagram (ERD) how to read"
- "foreign key constraints SQLite vs PostgreSQL"
- "primary key autoincrement vs BIGSERIAL"
- "database indexing composite index performance"
- "audit log table design pattern"
- "data deduplication before insert SQL"

---

## Synthèse du Jour 1

À ce stade, je peux :
1. Dessiner l'arborescence du projet de mémoire et placer chaque fichier dans sa couche.
2. Pour chaque fichier majeur, citer ses imports clés, ses classes/fonctions principales, et son rôle exact.
3. Dessiner les 6 tables de la base de données, avec leurs colonnes, leurs relations, et identifier qui écrit/lit chacune.
4. Tracer le flux global : génération → features → modèle → décisions → agents → gouvernance → audit → API/dashboard.

**Prochaine étape (Jour 2)** : suivre une donnée RÉELLE à travers tout ce système — un appel `POST /analyze` complet, fonction par fonction, table par table.
