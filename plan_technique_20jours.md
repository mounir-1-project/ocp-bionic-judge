# OCP Bionic Judge Agent — Feuille de route technique 20 jours

---

# PARTIE 1 — Vue d'ensemble des 20 jours

### Jour 1 — Cartographie architecturale complète
**Objectif** : Construire une carte mentale globale du système (dossiers, fichiers, couches, bibliothèques, vocabulaire).
**Résumé** : Lecture transversale de la structure du projet, des 6 tables DB, des 3 ADRs clés, des dépendances (`requirements.txt`) — sans analyse ligne par ligne.

### Jour 2 — Traçage du flux de données end-to-end
**Objectif** : Suivre, étape par étape, le trajet d'une donnée capteur jusqu'à la réponse API.
**Résumé** : Séquence complète generate → DB → features → modèle → predict → agent → judge → governance → API, avec identification précise des entrées/sorties de chaque module.

### Jour 3 — Génération de données et schéma de base
**Objectif** : Maîtriser `data/data_generator.py` et le schéma SQL des 6 tables.
**Résumé** : Profils des 5 machines, 3 types d'anomalies (spike, drift, sensor_cutoff), DDL des tables, `init_db()`.

### Jour 4 — Feature engineering : `RollingFeatureExtractor`
**Objectif** : Comprendre la construction des 24 features.
**Résumé** : `src/features/feature_engineering.py` — fenêtres roulantes (5min/15min/1h), z-scores, deltas/lags, ratios, transformer custom sklearn.

### Jour 5 — Isolation Forest
**Objectif** : Maîtriser le premier modèle d'anomalie.
**Résumé** : `train_isolation_forest()` dans `src/models/train.py` — `ParameterGrid`, `contamination`, sélection du meilleur run.

### Jour 6 — One-Class SVM et HDBSCAN
**Objectif** : Comprendre les 2 autres modèles et le pattern wrapper.
**Résumé** : `train_one_class_svm()` (sous-échantillonnage 10k), `HDBSCANWrapper` (classe custom `fit/predict/decision_function`).

### Jour 7 — Orchestration de l'entraînement et MLflow
**Objectif** : Comprendre `train_all()` de bout en bout.
**Résumé** : split chronologique 80/20, fit du pipeline sur train uniquement, comparaison AUC-ROC des 3 modèles, sauvegarde du bundle `best_model.joblib`, tracking MLflow.

### Jour 8 — Pipeline d'inférence et scoring de sévérité
**Objectif** : Maîtriser `src/models/predict.py`.
**Résumé** : chargement du bundle, `_apply_pipeline()`, normalisation/inversion du score, `_score_to_severity()` via percentiles p30/p70, `_save_predictions()`.

### Jour 9 — Explicabilité SHAP
**Objectif** : Comprendre `generate_shap_explanation()`.
**Résumé** : `TreeExplainer` (IF) vs `KernelExplainer` (OC-SVM/HDBSCAN), extraction des top-3 features, structure JSON stockée dans `ml_decisions.features_json`.

### Jour 10 — Détection de dérive (drift)
**Objectif** : Maîtriser `src/models/drift_detector.py`.
**Résumé** : `compute_psi()`, `compute_ks_test()`, `check_drift()` — comparaison 5000 scores anciens vs 100 récents, seuils `PSI_THRESHOLD=0.2` / `KS_PVALUE_THRESHOLD=0.05`, cooldown 15 min, écriture `audit_log`.

### Jour 11 — Outils de l'agent Detection
**Objectif** : Comprendre les 3 `@tool` LangChain.
**Résumé** : `get_anomaly_data`, `get_machine_history`, `get_shap_explanation` dans `src/agents/detection_agent.py` — requêtes DB directes, signatures, docstrings critiques pour le LLM.

### Jour 12 — Agent Detection ReAct
**Objectif** : Maîtriser le cycle ReAct complet.
**Résumé** : `SYSTEM_PROMPT` (normales des 5 machines + protocole 4 étapes), `build_detection_agent()`, `create_react_agent`, `AgentExecutor`, `max_iterations=6`, parsing JSON → `AgentDecision`.

### Jour 13 — Agent Judge (LLM direct)
**Objectif** : Comprendre l'architecture non-ReAct du Judge.
**Résumé** : `src/agents/judge_agent.py` — `SystemMessage`/`HumanMessage`, 5 critères pondérés, `DISAGREEMENT_THRESHOLD=6.0`, recalcul de `agreement`, écriture `judge_evaluations`.

### Jour 14 — Gouvernance et alerting
**Objectif** : Maîtriser `src/governance/governance.py`.
**Résumé** : `compute_metrics()` sur fenêtres 1h/24h/7d, métriques (confiance moyenne, taux de désaccord, drift du score Judge, conformité OCP, backlog critique), seuils d'alerte, cooldown 10 min.

### Jour 15 — Structure de l'API FastAPI
**Objectif** : Cartographier `api/main.py`.
**Résumé** : `MachineId` Enum, schémas Pydantic (`AnalyzeRequest`, `AnalyzeResponse`, `DecisionRecord`, `GovernanceMetrics`), liste des ~12 endpoints, documentation auto `/docs`.

### Jour 16 — Authentification et sécurité
**Objectif** : Maîtriser le système d'auth dual.
**Résumé** : API Key (`X-API-Key`) vs JWT cookie httpOnly (`ocp_session`), `_JWT_SECRET`/`_JWT_HOURS`/HS256, `slowapi` rate limiting, endpoints `/auth/login`, `/auth/me`, `/auth/logout`.

### Jour 17 — Orchestration `/analyze` et concurrence
**Objectif** : Comprendre le pont sync/async.
**Résumé** : `_analyze_sync()` (predict → analyze_machine → judge_decision), `ThreadPoolExecutor(max_workers=4)`, `run_in_executor`, feature flags `use_agent`/`run_judge`.

### Jour 18 — Tests automatisés
**Objectif** : Comprendre la stratégie de test du projet.
**Résumé** : `tests/conftest.py` (DB de test isolée), `tests/test_api.py`, `tests/test_data_generator.py`, `TestClient`, couverture (`pytest --cov`), mocks LLM.

### Jour 19 — Conteneurisation et CI/CD
**Objectif** : Comprendre le déploiement.
**Résumé** : `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml` — image de base, services, étapes CI, gestion de `models/best_model.joblib`.

### Jour 20 — Synthèse et maîtrise globale
**Objectif** : Validation finale de la compréhension d'ensemble.
**Résumé** : Traçage complet d'une anomalie réelle (génération → décision → audit_log), relecture critique des ADRs, test de prédiction d'impact sur 4 paramètres clés, explication du système sans jargon.

---

# PARTIE 2 — Détail complet

---

## JOUR 1 — Immersion architecturale complète

### Objectif principal
Construire une carte mentale technique et complète du système : organisation des dossiers, rôle précis de chaque fichier majeur, flux global de données, bibliothèques utilisées, vocabulaire technique des 19 jours suivants. À la fin du jour, tu dois pouvoir dessiner le système entier sans ouvrir un seul fichier.

### Sous-objectifs
1. Cartographier l'arborescence complète du projet et attribuer un rôle à chaque dossier.
2. Identifier les 4 couches architecturales et leurs frontières.
3. Pour chaque fichier majeur, extraire : imports, classes/fonctions principales, rôle dans l'architecture.
4. Lister les 6 tables de la base de données et leur "propriétaire" (qui écrit, qui lit).
5. Lire les ADRs pertinents pour comprendre le "pourquoi" des choix techniques.
6. Construire un glossaire de ~25 termes techniques.

### Dossiers concernés
- `data/` — génération de données simulées + données brutes
- `src/` — code source principal (config, db, features, models, agents, governance)
- `src/features/`, `src/models/`, `src/agents/`, `src/governance/`
- `api/` — application FastAPI
- `models/` — artefacts entraînés (`best_model.joblib`)
- `mlruns/` — tracking MLflow
- `notebooks/` — exploration (EDA, training, SHAP)
- `tests/` — suite de tests pytest
- `docs/decisions/` — ADRs (Architecture Decision Records)

### Fichiers concernés (lecture en diagonale, sans détail ligne par ligne)
- `requirements.txt`
- `src/config.py`
- `src/db.py`
- `data/data_generator.py`
- `src/features/feature_engineering.py`
- `src/models/train.py`, `predict.py`, `drift_detector.py`
- `src/agents/detection_agent.py`, `judge_agent.py`
- `src/governance/governance.py`
- `api/main.py`
- `docs/decisions/*.md` (tous les ADRs, lecture rapide)
- `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml` (juste repérer leur existence)

### Dépendances et bibliothèques à analyser (depuis `requirements.txt`)
- **Données/ML** : `numpy`, `pandas`, `scikit-learn`, `hdbscan`, `scipy`, `joblib`
- **Explicabilité** : `shap`
- **Base de données** : `sqlalchemy`, `alembic`
- **Configuration/logs** : `python-dotenv`, `loguru`
- **Agents IA** : `langchain`, `langchain-google-genai` (Gemini)
- **API** : `fastapi`, `uvicorn`, `pydantic`, `pyjwt`, `slowapi`
- **MLOps** : `mlflow`
- **Tests** : `pytest`, `pytest-cov`, `httpx`

Pour chaque bibliothèque, note en une phrase : "à quoi sert-elle dans CE projet" (pas en général).

### Technologies utilisées
Python 3.11, SQLite (dev) / PostgreSQL (prod) via SQLAlchemy ORM, scikit-learn Pipeline, MLflow, LangChain (agents ReAct + appels LLM directs), Google Gemini (`gemini-2.0-flash`), FastAPI + Uvicorn, JWT (HS256), Docker, GitHub Actions.

### Concepts techniques à comprendre (niveau "définition", pas encore "implémentation")
- Détection d'anomalies non supervisée (pas de labels lors de l'entraînement)
- Méthodes d'ensemble (Isolation Forest)
- Frontière de décision (One-Class SVM)
- Clustering basé densité et notion d'"outlier" (HDBSCAN)
- Feature engineering pour séries temporelles (fenêtres roulantes, z-score, lag)
- Pipeline scikit-learn et transformateurs custom (`BaseEstimator`, `TransformerMixin`)
- Sérialisation de modèles (joblib, "bundle")
- Détection de dérive de données (PSI, test de Kolmogorov-Smirnov)
- Agents LLM : pattern ReAct (boucle Thought/Action/Observation) vs appel direct LLM
- Évaluation multi-critères ("LLM-as-judge")
- Gouvernance/monitoring de système IA (métriques, alertes, fenêtres temporelles)
- API REST, authentification (API Key + JWT cookie httpOnly), rate limiting
- Pont entre code synchrone (agents/ML) et serveur asynchrone (FastAPI) via `ThreadPoolExecutor`

### Termes techniques à rechercher (constituer un glossaire écrit)
anomaly detection, unsupervised learning, ensemble method, isolation forest, one-class SVM, density-based clustering, outlier score, feature engineering, rolling window, z-score normalization, lag feature, sklearn Pipeline, BaseEstimator/TransformerMixin, joblib serialization, model bundle, SHAP value, TreeExplainer, KernelExplainer, data drift, Population Stability Index (PSI), Kolmogorov-Smirnov test, LangChain, `@tool` decorator, ReAct pattern, AgentExecutor, LLM-as-judge, Pydantic BaseModel, JWT, httpOnly cookie, rate limiting, ORM, MLflow run, ThreadPoolExecutor, ADR (Architecture Decision Record).

### Flux de données / informations à identifier (vue d'ensemble seulement, le détail est pour Jour 2)
```
[data_generator.py] → DB (sensor_readings, anomalies)
        ↓
[feature_engineering.py] → 24 features
        ↓
[train.py] → models/best_model.joblib (pipeline + modèle + seuils)
        ↓
[predict.py] → DB (ml_decisions) + SHAP
        ↓
[detection_agent.py] → lit ml_decisions/sensor_readings via @tool → AgentDecision
        ↓
[judge_agent.py] → évalue AgentDecision → DB (judge_evaluations)
        ↓
[governance.py] → métriques + alertes → DB (audit_log)
        ↓
[api/main.py] → expose tout ça via REST, sécurisé par auth
```

### Interactions entre composants à noter
- `src/config.py` est importé par PRESQUE TOUS les modules (centralise `.env`, DATABASE_URL, GEMINI_*).
- `src/db.py` fournit l'`engine` SQLAlchemy utilisé par `data_generator.py`, `train.py`, `predict.py`, `drift_detector.py`, `governance.py`, `api/main.py`.
- Le "bundle" produit par `train.py` (`{model, name, pipeline, feature_cols, metrics, severity_thresholds}`) est l'objet pivot entre entraînement et inférence.
- `detection_agent.py` et `judge_agent.py` sont deux architectures DIFFÉRENTES (ReAct vs appel direct) — à ne pas confondre.
- `api/main.py::_analyze_sync()` est le SEUL point d'orchestration globale — il n'existe pas de fichier `orchestrator.py`.

### Schémas mentaux à construire (sur papier, obligatoire)
1. **Diagramme en couches** : Données → ML → Agents/Gouvernance → API, avec les fichiers placés dans chaque couche.
2. **Table de propriété des données** : pour chacune des 6 tables (`sensor_readings`, `anomalies`, `ml_decisions`, `judge_evaluations`, `audit_log`, + 1 autre à identifier), qui écrit et qui lit.
3. **Schéma du "bundle"** : un rectangle représentant `best_model.joblib`, avec ses 6 clés internes et une flèche vers chaque module qui les consomme.

### Questions à pouvoir répondre en fin de journée
- Quels sont les 6 tables de la base de données, et pour chacune : qui écrit, qui lit ?
- Quels sont les 3 modèles ML candidats, et lequel(s) algorithme(s) viennent de quelle bibliothèque ?
- Quel LLM est utilisé dans le projet, dans quels fichiers, et pourquoi ce choix (cf. ADR) ?
- Quelle est la différence architecturale fondamentale entre `detection_agent.py` et `judge_agent.py` ?
- Pourquoi `src/config.py` appelle `load_dotenv()` une seule fois, et que se passerait-il si chaque module le faisait individuellement ?
- À quoi sert le dossier `docs/decisions/` et que contient un ADR ?
- Où se trouve la logique d'orchestration globale (le "cerveau" qui appelle predict → agent → judge) ?

### Erreurs de compréhension fréquentes à éviter
- Croire qu'il n'y a qu'UN modèle ML — il y en a 3 (Isolation Forest, One-Class SVM, HDBSCAN), le meilleur est sélectionné automatiquement.
- Croire que le Judge est un agent ReAct comme le Detection Agent — non, c'est un appel LLM direct (`SystemMessage` + `HumanMessage`).
- Chercher un fichier `orchestrator.py` ou `pipeline.py` qui n'existe pas — l'orchestration est dans `api/main.py`.
- Croire que l'authentification se fait par username/password OAuth2 classique — c'est API Key OU JWT cookie.
- Penser que `feature_engineering.py` produit "quelques" features — il en produit 24, organisées en 6 catégories.

### Résultat concret attendu en fin de journée
Un document (papier ou fichier texte) contenant :
1. Un schéma en couches du projet avec tous les fichiers majeurs placés.
2. Un tableau "Table DB → écrivains → lecteurs" pour les 6 tables.
3. Un glossaire d'au moins 25 termes techniques avec définition d'une ligne chacun.
4. Une liste des 3 modèles ML avec leur bibliothèque d'origine.
5. Une phrase résumant le choix du LLM (Gemini) d'après l'ADR correspondant.

---

## JOUR 2 — Traçage technique du flux de données end-to-end

### Objectif principal
Suivre concrètement, fonction par fonction et table par table, le parcours complet d'une donnée — depuis la génération d'une lecture capteur jusqu'à la réponse JSON d'un appel `POST /analyze`. À la fin du jour, tu dois pouvoir dessiner un diagramme de séquence complet sans hésitation.

### Sous-objectifs
1. Tracer le flux "génération → DB" (`data_generator.py` + `db.py`).
2. Tracer le flux "DB brute → features" (`feature_engineering.py`) — comprendre les formes d'entrée/sortie (shapes).
3. Tracer le flux "entraînement → bundle" à haut niveau (`train.py`, sans entrer dans la théorie des 3 modèles — ce sera Jours 5-7).
4. Tracer le flux "bundle + DB → prédiction" (`predict.py`) jusqu'à l'écriture dans `ml_decisions`.
5. Tracer le flux complet d'un appel `POST /analyze` : `api/main.py::_analyze_sync()` → `predict()` → `analyze_machine()` → `judge_decision()` → réponse JSON.
6. Identifier, pour chaque étape, les tables DB lues/écrites.

### Fichiers concernés
- `data/data_generator.py` (fonctions de génération + `init_db()`)
- `src/db.py` (`get_engine()`, `init_schema()`)
- `src/features/feature_engineering.py` (`build_feature_pipeline()`, `RollingFeatureExtractor` — vue d'ensemble des entrées/sorties seulement)
- `src/models/train.py` (`load_training_data()`, `chronological_split()`, `train_all()` — niveau orchestration uniquement)
- `src/models/predict.py` (`predict()`, `_apply_pipeline()`, `_save_predictions()`)
- `api/main.py` (`_analyze_sync()`, endpoint `POST /analyze`, modèles `AnalyzeRequest`/`AnalyzeResponse`)

### Dossiers concernés
- `data/` (entrée du flux)
- `src/` (transformations et logique métier)
- `api/` (point d'entrée/sortie externe)

### Dépendances et bibliothèques à analyser (dans leur usage concret ici, pas en théorie)
- `sqlalchemy` : `to_sql()` (écriture), `read_sql()` / requêtes (lecture)
- `pandas` : DataFrame comme format d'échange entre toutes les étapes
- `joblib` : `load()` du bundle au démarrage de `predict.py`
- `sklearn.pipeline.Pipeline` : `fit_transform()` (train) vs `transform()` (inférence) — déjà rencontré au Jour 1, ici on voit OÙ il est appelé
- `concurrent.futures.ThreadPoolExecutor` + `asyncio.run_in_executor` : pont entre FastAPI (async) et le code ML/agents (sync)
- `pydantic` : validation de `AnalyzeRequest` en entrée et `AnalyzeResponse` en sortie

### Technologies utilisées
SQLite/SQLAlchemy pour la persistance, pandas comme format pivot entre tous les modules, joblib pour la sérialisation du modèle, FastAPI + ThreadPoolExecutor pour l'exécution.

### Concepts techniques à comprendre
- Pipeline ETL (Extract-Transform-Load) : génération → DB → features → modèle → résultats.
- Différence entre **données brutes** (`sensor_readings`, ~5 colonnes) et **données transformées** (24 features) — ce ne sont jamais les mêmes objets.
- Chargement UNIQUE du modèle au démarrage (pas de réentraînement par requête).
- Cycle de vie d'une requête HTTP : réception → validation Pydantic → exécution métier (souvent bloquante) → délégation à un thread → réponse.
- Boucle ReAct comme "sous-flux" à l'intérieur du flux global (détaillée au Jour 12, mais repérée ici comme une boîte noire avec entrée/sortie).

### Termes techniques à rechercher
pipeline ETL, schéma de base de données (DDL), DataFrame, sérialisation/désérialisation, singleton (pour l'engine et le bundle chargés une fois), cycle de requête HTTP, validation de schéma (Pydantic), exécuteur de threads (ThreadPoolExecutor), boucle d'événements (event loop asyncio), feature flag.

### Flux de données / informations détaillé à tracer (et noter par écrit)

**Étape 1 — Génération**
`data_generator.py` génère, pour chaque machine, une série temporelle de lectures (5 capteurs) avec injection d'anomalies (spike/drift/sensor_cutoff) → écriture dans `sensor_readings` (et `anomalies` pour les labels de vérité terrain) via `to_sql`.

**Étape 2 — Feature engineering**
`build_feature_pipeline()` construit un `Pipeline` sklearn contenant `RollingFeatureExtractor` (+ éventuellement un scaler). En ENTRÉE : DataFrame avec les colonnes brutes des 5 capteurs + timestamp. En SORTIE : DataFrame avec 24 colonnes (features).

**Étape 3 — Entraînement (vue d'ensemble)**
`load_training_data()` lit `sensor_readings` (+ `anomalies` pour évaluation) via SQL. `chronological_split()` divise 80% ancien / 20% récent. Le pipeline est `fit_transform()` sur le train, `transform()` sur le test. Les 3 modèles sont entraînés sur les features transformées. Le meilleur est sauvegardé avec le pipeline DANS le même bundle (`models/best_model.joblib`).

**Étape 4 — Inférence**
`predict.py` charge le bundle UNE FOIS (au démarrage du module). Pour chaque nouvelle lecture/fenêtre : lit les données brutes récentes depuis `sensor_readings`, applique `_apply_pipeline()` (le MÊME pipeline que l'entraînement, en mode `transform` seulement), obtient un score brut du modèle, le normalise/inverse, calcule la sévérité via `_score_to_severity()` (percentiles stockés dans le bundle), génère l'explication SHAP, écrit le résultat dans `ml_decisions` via `_save_predictions()`.

**Étape 5 — Appel API `/analyze`**
Client → `POST /analyze {machine_id, use_agent, run_judge}` → validation `AnalyzeRequest` (Pydantic) → `_analyze_sync(req)` exécuté dans `ThreadPoolExecutor` (via `run_in_executor`, pour ne pas bloquer le event loop FastAPI) :
  1. `predict()` → écrit `ml_decisions`, retourne score/sévérité/SHAP
  2. si `use_agent=True` : `analyze_machine()` (agent Detection ReAct) → lit `ml_decisions`/`sensor_readings` via ses `@tool` → produit `AgentDecision`
  3. si `run_judge=True` : `judge_decision()` (Judge, appel direct LLM) → évalue `AgentDecision` → écrit `judge_evaluations`
  4. Le tout est assemblé en `AnalyzeResponse` (Pydantic) → retourné au client en JSON.

### Interactions entre composants à noter
- `predict.py` et `train.py` DOIVENT utiliser exactement le même pipeline (objet fitté sauvegardé dans le bundle) — sinon les features ne correspondraient pas.
- `detection_agent.py` ne lit JAMAIS les données brutes directement pour son raisonnement — il passe par ses 3 `@tool`, qui elles-mêmes font des requêtes SQL.
- `judge_agent.py` ne touche PAS à la base de données pour lire — il reçoit l'`AgentDecision` déjà construite en mémoire ; il écrit seulement le résultat dans `judge_evaluations`.
- `_analyze_sync()` est le SEUL endroit où ces 3 composants (predict, detection agent, judge) sont appelés dans le même flux.

### Schémas mentaux à construire (sur papier, obligatoire)
1. **Diagramme de séquence** complet pour `POST /analyze` avec `use_agent=true, run_judge=true` : chaque flèche = un appel de fonction, chaque rectangle latéral = une table DB touchée (lecture en pointillé, écriture en trait plein).
2. **Tableau "Module → Entrée → Sortie → Table DB touchée"** pour `data_generator.py`, `feature_engineering.py`, `train.py` (vue d'ensemble), `predict.py`, `api/main.py::_analyze_sync`.
3. **Schéma "avant/après pipeline"** : une ligne de `sensor_readings` (5-6 colonnes) à gauche, une flèche "pipeline.transform()", et une ligne de 24 features à droite.

### Questions à pouvoir répondre en fin de journée
- Quelle est la séquence EXACTE d'appels de fonctions pour un `POST /analyze` avec `use_agent=true` et `run_judge=true` ?
- À quel moment précis le modèle ML est-il chargé en mémoire — à chaque requête, ou une seule fois ?
- Quelles tables sont lues, et lesquelles sont écrites, à chaque étape du flux ?
- Quelle est la différence entre les colonnes de `sensor_readings` et les colonnes utilisées par le modèle (`feature_cols` du bundle) ?
- Que se passe-t-il dans la réponse `/analyze` si `use_agent=false` — quels champs seront absents ou nuls ?
- Pourquoi `_analyze_sync()` est-elle exécutée dans un `ThreadPoolExecutor` plutôt que directement dans la fonction async de l'endpoint ?

### Erreurs de compréhension fréquentes à éviter
- Croire que `predict.py` réentraîne ou refitte le pipeline à chaque appel — il fait UNIQUEMENT `transform()`, jamais `fit()`.
- Croire que l'agent Detection interroge la base directement en SQL "à la main" — il passe systématiquement par ses `@tool`.
- Confondre `anomalies` (table de vérité terrain générée artificiellement, utilisée pour évaluer les modèles) et `ml_decisions` (sorties réelles du modèle en inférence).
- Penser que le Judge a accès à la base de données pour vérifier les faits — il raisonne uniquement sur ce qui lui est transmis en mémoire (`AgentDecision` + contexte).
- Oublier que `chronological_split()` (Jour 7) influence directement la qualité de `predict.py` (Jour 8) — le flux Jour 2 relie déjà ces deux étapes même si le détail vient plus tard.

### Résultat concret attendu en fin de journée
Un document contenant :
1. Le diagramme de séquence complet d'un appel `POST /analyze` (use_agent=true, run_judge=true), avec toutes les tables DB annotées.
2. Le tableau "Module → Entrée → Sortie → Table DB" pour les 5 modules tracés.
3. Une explication écrite (5-8 lignes) de la différence entre `sensor_readings` et les `feature_cols` du bundle, avec un exemple concret de transformation (une colonne brute → 2-3 features dérivées).

---

*Plan technique 20 jours · OCP Bionic Judge Agent*
