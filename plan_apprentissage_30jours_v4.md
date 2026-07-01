# Plan d'apprentissage – OCP Bionic Judge Agent
## 30 jours · Version finale · Structure théorie → pratique → projet

---

## Comment lire ce plan

Chaque jour est divisé en deux blocs :

**Matin — Théorie + exercice (HORS projet)**
Tu apprends un concept depuis zéro (YouTube, documentation officielle).
Puis tu le pratiques dans un fichier Python que tu crées toi-même, sans ouvrir le projet.
Objectif : avoir le vocabulaire et les bases pour que le code du projet ne soit pas du charabia.

**Après-midi — Lecture du projet**
Tu ouvres les fichiers du projet qui utilisent exactement ce que tu as appris le matin.
Tu lis, tu cherches les patterns que tu connais maintenant, tu poses des questions à l'IA avec le bon vocabulaire.

---

## SEMAINE 1 — Python, données, base de données

---

## Jour 1 — Vue d'ensemble du projet

> Pas de théorie technique ce jour. L'objectif est de comprendre CE QUE fait le projet avant de comprendre COMMENT.

### Matin — Orientation
- Chercher sur YouTube : **"predictive maintenance explained"** (5-10 min, n'importe quelle vidéo grand public)
- Chercher : **"what is anomaly detection machine learning simple explanation"**
- Lire `README.md` du projet + les 7 fichiers dans `docs/decisions/` (5 min chacun, ne pas essayer de tout comprendre — juste répondre à : "quel problème règle ce projet et pourquoi ces choix ?")

### Après-midi — Explorer la structure
- Ouvrir le projet dans ton éditeur. Passer 30 min à naviguer dans les dossiers sans ouvrir de fichier Python.
- Dessiner sur papier un schéma avec ces 5 cases reliées par des flèches :
  `[Données capteurs] → [Features ML] → [Modèle ML] → [Agent IA] → [API]`
- Question à répondre : d'après les ADRs, quel LLM (modèle de langage) est utilisé et pourquoi ?

---

## Jour 2 — Variables d'environnement, connexion DB, logging

### Matin — Théorie + exercice

**Ce que tu dois apprendre :**
- **"python-dotenv tutorial"** : comment charger des secrets (clés API, URL de base de données) depuis un fichier `.env` au lieu de les écrire en dur dans le code.
- **"SQLAlchemy create_engine tutorial beginner"** : comment Python se connecte à une base de données SQL sans écrire du SQL dans les paramètres de connexion.
- **"loguru Python logging tutorial"** : bibliothèque de logging plus simple que le module standard. `logger.info()`, `logger.success()`, `logger.warning()`.

**Mini exercice à écrire (fichier `exercice_j2.py`) :**
```python
# Crée un fichier .env avec : MON_NOM=Alice
# Puis écris ce script :

from dotenv import load_dotenv
import os

load_dotenv()
nom = os.getenv("MON_NOM", "inconnu")
print(f"Bonjour {nom}")

# Maintenant avec loguru :
from loguru import logger
logger.info(f"Script démarré pour {nom}")
logger.success("Tout fonctionne")
logger.warning("Ceci est un avertissement")
```
Objectif : voir la différence entre `print()` et `logger`, et comprendre que `.env` garde les secrets hors du code.

### Après-midi — Projet : `src/config.py` et `src/db.py`

Ouvrir ces deux fichiers. Tu reconnais maintenant `load_dotenv()` et `os.getenv()`.
- Dans `config.py` : trouver où est chargée la clé API Gemini et l'URL de la base de données.
- Dans `db.py` : trouver la fonction `get_engine()` — elle fait exactement ce que SQLAlchemy t'a appris le matin.
- Action : copier `.env.example` en `.env`, remplir les valeurs, lancer `python -c "from src.config import DATABASE_URL; print(DATABASE_URL)"`.
- Question : pourquoi tous les autres fichiers du projet font `from src.config import GEMINI_MODEL` même quand ils n'utilisent pas Gemini ?

---

## Jour 3 — NumPy, pandas et séries temporelles

### Matin — Théorie + exercice

**Ce que tu dois apprendre :**
- **"numpy random array generation tutorial"** : générer des données aléatoires avec `np.random.default_rng()`. La base de toute simulation de données.
- **"pandas DataFrame creation from dict"** : créer un tableau de données depuis un dictionnaire Python.
- **"time series datetime pandas date_range"** : créer une séquence de timestamps réguliers (toutes les 30 secondes, par exemple).

**Mini exercice à écrire (fichier `exercice_j3.py`) :**
```python
import numpy as np
import pandas as pd

rng = np.random.default_rng(seed=42)

# Simuler 100 lectures de température (valeurs normales autour de 60°C)
timestamps = pd.date_range(start="2024-01-01", periods=100, freq="30s")
temperature = rng.normal(loc=60, scale=3, size=100)

# Injecter une anomalie (spike) à l'indice 50
temperature[50] += 20  # +20 degrés = anomalie claire

df = pd.DataFrame({
    "timestamp": timestamps,
    "temperature": temperature.round(2),
    "is_anomaly": [1 if i == 50 else 0 for i in range(100)]
})

print(df.head())
print(f"\nAnomalie : {df[df['is_anomaly']==1][['timestamp','temperature']]}")
```
Objectif : comprendre comment des données industrielles sont simulées avant de voir comment le projet le fait.

### Après-midi — Projet : `data/data_generator.py`

Tu reconnais maintenant `np.random.default_rng()`, `pd.date_range()`, et le concept d'injection d'anomalie.
- Trouver dans le code les 3 types d'anomalies : spike, drift, sensor_cutoff.
- Trouver où les données sont sauvegardées en base de données (`to_sql`).
- Action : lancer `python data/data_generator.py` et vérifier `data/processed/generation_summary.json`.
- Question : dans ton exercice du matin, l'anomalie est simple (un seul point). Dans le projet, pourquoi le "drift" affecte-t-il TOUS les timesteps d'une séquence et non un seul ?

---

## Jour 4 — Pandas avancé : groupby, rolling, z-score

### Matin — Théorie + exercice

**Ce que tu dois apprendre :**
- **"pandas rolling window statistics tutorial"** : calculer des statistiques sur une fenêtre glissante (les 10 dernières valeurs, les 30 dernières...). Un spike fait exploser l'écart-type local.
- **"pandas groupby tutorial"** : appliquer un calcul séparément pour chaque groupe (par machine, par exemple).
- **"z-score normalization explained"** : `z = (valeur - moyenne) / écart_type`. Ramène des capteurs aux échelles très différentes (température 60°C vs vibration 2 mm/s) sur la même échelle.

**Mini exercice à écrire (fichier `exercice_j4.py`) :**
```python
import pandas as pd
import numpy as np

# Données de 2 machines avec une anomalie dans machine_A
data = {
    "machine": ["A"]*10 + ["B"]*10,
    "temperature": [60,61,59,62,60,61,59,60,85,61,  # 85 = anomalie dans A
                    40,41,40,42,40,41,40,41,40,42]
}
df = pd.DataFrame(data)

# Rolling std par machine (fenêtre de 3)
df["temp_roll_std"] = (
    df.groupby("machine")["temperature"]
    .transform(lambda x: x.rolling(3, min_periods=1).std())
)

# Z-score par machine
df["temp_zscore"] = (
    df.groupby("machine")["temperature"]
    .transform(lambda x: (x - x.mean()) / x.std())
)

print(df)
# Observer : à l'indice 8 (anomalie machine A), temp_roll_std et temp_zscore sont élevés
```
Objectif : voir visuellement comment ces features "révèlent" une anomalie que la valeur brute seule montre moins clairement.

### Après-midi — Projet : `src/features/feature_engineering.py`

Tu reconnais maintenant `groupby`, `rolling`, `transform`, et z-score.
- Trouver la classe `RollingFeatureExtractor` — c'est exactement ce que tu as fait manuellement le matin, mais encapsulé dans un transformateur sklearn.
- Lire le commentaire en tête de fichier qui liste les 24 features : identifier combien viennent du z-score par machine, du z-score local glissant, des deltas.
- Question : `RollingFeatureExtractor` produit désormais un z-score *local* `(x - rolling_mean)/rolling_std`. Pourquoi est-ce plus informatif pour une anomalie qu'une simple moyenne glissante brute ?

---

## Jour 5 — sklearn Pipeline : enchaîner des transformations

### Matin — Théorie + exercice

**Ce que tu dois apprendre :**
- **"sklearn Pipeline tutorial step by step"** : enchaîner plusieurs transformations (ex : normalisation → sélection de features → modèle) en un seul objet.
- **"sklearn fit transform fit_transform"** : `fit()` apprend les paramètres sur les données d'entraînement. `transform()` applique ces paramètres. **Ne jamais faire `fit` sur les données de test** — fuite de données.
- **"sklearn BaseEstimator TransformerMixin custom"** : créer son propre transformateur compatible sklearn Pipeline.

**Mini exercice à écrire (fichier `exercice_j5.py`) :**
```python
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.base import BaseEstimator, TransformerMixin
import numpy as np

# Transformateur custom : ajoute une feature "carré" de chaque colonne
class SquareFeatures(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None):
        return self  # rien à apprendre

    def transform(self, X):
        return np.hstack([X, X**2])

# Pipeline : custom transformer + normalisation
pipe = Pipeline([
    ("square", SquareFeatures()),
    ("scale", StandardScaler()),
])

X_train = np.array([[1, 2], [3, 4], [5, 6]])
X_test  = np.array([[2, 3]])

X_train_t = pipe.fit_transform(X_train)  # fit ET transform sur train
X_test_t  = pipe.transform(X_test)       # transform SEULEMENT sur test (pas fit!)

print("Train transformé :", X_train_t.shape)
print("Test transformé  :", X_test_t.shape)
```
Objectif : comprendre pourquoi `fit` ne se fait qu'une fois sur le train, et comment un custom transformer s'intègre dans un Pipeline.

### Après-midi — Projet : `src/features/feature_engineering.py` + `src/models/train.py` (lignes 495-510 seulement)

Tu reconnais maintenant `Pipeline`, `fit_transform`, `fit`, `transform`, `BaseEstimator`, `TransformerMixin`.
- Dans `feature_engineering.py` : voir que `RollingFeatureExtractor` est exactement un custom transformer comme celui de ton exercice.
- Dans `train.py` lignes 495-510 : voir `pipeline.fit_transform(train_df)` puis `pipeline.transform(test_df)` — exactement le pattern du matin.
- Question : dans le projet, `pipeline.fit()` est appelé uniquement sur `train_df`. Que se passerait-il si on avait appelé `fit` sur toutes les données (train + test) ?

---

## Jour 6 — SQL et SQLAlchemy : lire depuis une base de données

### Matin — Théorie + exercice

**Ce que tu dois apprendre :**
- **"SQL SELECT WHERE ORDER BY LIMIT tutorial"** : les 4 clauses SQL les plus importantes pour lire des données.
- **"pandas read_sql sqlalchemy"** : lire une table SQL directement dans un DataFrame pandas avec `pd.read_sql()`.
- **"SQL GROUP BY COUNT aggregate"** : compter, sommer, moyenner par groupe.

**Mini exercice à écrire (fichier `exercice_j6.py`) :**
```python
import sqlite3
import pandas as pd

# Créer une mini DB en mémoire
conn = sqlite3.connect(":memory:")
conn.execute("CREATE TABLE capteurs (id INTEGER, machine TEXT, valeur REAL)")
conn.executemany("INSERT INTO capteurs VALUES (?,?,?)", [
    (1, "A", 60.0), (2, "A", 85.0), (3, "B", 40.0), (4, "B", 42.0)
])
conn.commit()

# Lire avec SQL pur
df = pd.read_sql("SELECT * FROM capteurs WHERE machine = 'A'", conn)
print(df)

# Agrégation
df2 = pd.read_sql("SELECT machine, COUNT(*) as n, AVG(valeur) as moy FROM capteurs GROUP BY machine", conn)
print(df2)

conn.close()
```
Objectif : comprendre `pd.read_sql()` et les requêtes SQL de base avant de voir leur usage dans le projet.

### Après-midi — Projet : `src/models/train.py` (fonctions `load_training_data`, `chronological_split`)

Tu reconnais maintenant `pd.read_sql`, `sqlite3.connect`, les requêtes SQL.
- Trouver dans `load_training_data()` les deux requêtes SQL — que chargent-elles ?
- Trouver `chronological_split()` — pourquoi trier par `timestamp` avant de diviser au lieu de diviser aléatoirement ?
- Action : lancer `sqlite3 data/ocp_bionic.db` et taper ces requêtes manuellement :
  - `SELECT COUNT(*) FROM sensor_readings;`
  - `SELECT anomaly_type, COUNT(*) FROM anomalies GROUP BY anomaly_type;`
- Question : la fonction `chronological_split` met les 80 % anciens en train et les 20 % récents en test. Pourquoi ce sens et pas l'inverse ?

---

## Jour 7 — Révision semaine 1 : assembler les briques

> Pas de nouvelle théorie. Consolider et vérifier que tout s'enchaîne.

### Matin — Révision active
Reprendre les 5 exercices des jours 2 à 6. Pour chacun :
- Le relire sans regarder le cours.
- Ajouter un commentaire `# Pourquoi ce code existe` sur chaque bloc.
- Vérifier qu'il tourne encore.

### Après-midi — Mini projet de révision
Écrire un script `revision_s1.py` (sans copier du projet) qui :
1. Charge `sensor_readings` depuis `data/ocp_bionic.db` avec `pd.read_sql`
2. Applique `build_feature_pipeline(scale=True)` depuis `feature_engineering.py`
3. Affiche : nombre de lignes, nombre de colonnes, la colonne `temperature_roll_std_1h` des 5 premières lignes

Ce script utilise ce que tu as appris les jours 2, 3, 4, 5, 6. S'il fonctionne du premier coup, la semaine 1 est acquise. S'il plante, identifier pourquoi — c'est tout aussi formateur.

---

## SEMAINE 2 — Machine Learning

---

## Jour 8 — Isolation Forest : l'algorithme

### Matin — Théorie + exercice

**Ce que tu dois apprendre :**
- **"Isolation Forest explained visually"** : chercher une vidéo ou article avec des graphiques. L'idée clé : une anomalie est isolée en PEU de coupures aléatoires. Un point normal, entouré d'autres points similaires, nécessite BEAUCOUP de coupures.
- **"sklearn IsolationForest fit predict"** : `fit(X)` entraîne le modèle, `predict(X)` retourne 1 (normal) ou -1 (anomalie), `decision_function(X)` retourne un score (plus négatif = plus anomal).
- **"contamination parameter IsolationForest"** : dit au modèle quelle proportion de points sont des anomalies. Dans notre projet, ~4 % des données sont anormales.

**Mini exercice à écrire (fichier `exercice_j8.py`) :**
```python
import numpy as np
from sklearn.ensemble import IsolationForest
import matplotlib.pyplot as plt

rng = np.random.default_rng(42)

# 95 points normaux autour de (0,0) et 5 anomalies loin
X_normal   = rng.normal(0, 1, (95, 2))
X_anomaly  = rng.uniform(4, 6, (5, 2))
X = np.vstack([X_normal, X_anomaly])
labels_vrais = np.array([1]*95 + [-1]*5)

# Entraîner
model = IsolationForest(contamination=0.05, random_state=42)
model.fit(X)
preds = model.predict(X)

# Résultats
print(f"Anomalies détectées : {(preds == -1).sum()}")
print(f"Vrais anomalies     : {(labels_vrais == -1).sum()}")

# Visualiser
plt.scatter(X[preds==1, 0],  X[preds==1, 1],  c="blue",  label="normal")
plt.scatter(X[preds==-1, 0], X[preds==-1, 1], c="red",   label="anomalie")
plt.legend(); plt.title("Isolation Forest"); plt.savefig("if_result.png")
print("Graphique sauvegardé : if_result.png")
```
Objectif : voir concrètement ce que fait Isolation Forest avant de lire son implémentation dans le projet.

### Après-midi — Projet : `src/models/train.py` (fonction `train_isolation_forest`)

Tu reconnais maintenant `IsolationForest`, `contamination`, `fit`, `predict`, `decision_function`.
- Lire `train_isolation_forest()` — elle entraîne plusieurs modèles avec différentes combinaisons de paramètres (`ParameterGrid`) et garde le meilleur.
- Trouver la grille de paramètres : quelles valeurs de `contamination` sont testées ?
- Question : dans ton exercice tu as mis `contamination=0.05` car tu savais qu'il y avait 5 anomalies sur 100. Dans le projet, comment ce taux a-t-il été estimé ?

---

## Jour 9 — One-Class SVM et HDBSCAN : deux autres approches

### Matin — Théorie + exercice

**Ce que tu dois apprendre :**
- **"One-Class SVM anomaly detection explained"** : apprend une "frontière" autour des données normales. Tout ce qui est en dehors = anomalie. Le paramètre `nu` ≈ proportion d'anomalies (comme `contamination`).
- **"HDBSCAN clustering explained simply"** : forme des groupes (clusters) dans les données. Les points qui n'appartiennent à aucun groupe = anomalies. `outlier_scores_` donne la note d'anomalie de chaque point.
- **"sklearn wrapper API fit predict"** : pourquoi on crée des "wrappers" — pour que des algorithmes avec des APIs différentes aient la même interface (`fit`, `predict`, `decision_function`).

**Mini exercice à écrire (fichier `exercice_j9.py`) :**
```python
import numpy as np
from sklearn.svm import OneClassSVM

rng = np.random.default_rng(42)
X_normal  = rng.normal(0, 1, (100, 2))
X_anomaly = rng.uniform(4, 6, (5, 2))
X = np.vstack([X_normal, X_anomaly])

# One-Class SVM
model = OneClassSVM(nu=0.05, kernel="rbf")
model.fit(X_normal)  # on entraîne sur les normaux seulement
preds = model.predict(X)

print(f"Anomalies détectées : {(preds == -1).sum()}")
# -1 = anomalie, 1 = normal — même convention que IsolationForest
```
Puis écrire (sans exécuter, juste lire et comprendre) ce pseudo-code HDBSCAN :
```python
# Pseudo-code HDBSCAN
# hdbscan.fit(X_train) → forme des clusters
# points avec label=-1 dans fit_predict = bruit = anomalies
# hdbscan.outlier_scores_ = score d'anomalie pour chaque point du train
# hdbscan.approximate_predict(X_test) → prédire sur de nouvelles données
```

### Après-midi — Projet : `src/models/train.py` (classe `HDBSCANWrapper`, fonctions `train_one_class_svm`, `train_hdbscan`)

Tu reconnais maintenant OneClassSVM, le concept de wrapper, et HDBSCAN.
- Lire `HDBSCANWrapper` — c'est exactement un wrapper comme expliqué le matin : il donne à HDBSCAN la même API que sklearn.
- Trouver pourquoi `train_one_class_svm` sous-échantillonne à 10 000 lignes (chercher le commentaire dans le code).
- Question : `HDBSCANWrapper.predict()` utilise le 95ème percentile des scores d'entraînement comme seuil. Pourquoi un percentile et pas une valeur fixe comme 0.5 ?

---

## Jour 10 — MLflow : tracker les expériences ML

### Matin — Théorie + exercice

**Ce que tu dois apprendre :**
- **"MLflow tutorial beginner tracking"** : MLflow enregistre chaque entraînement (run) avec ses paramètres, ses métriques, et le modèle lui-même. Permet de comparer des dizaines d'entraînements.
- **"mlflow.start_run log_param log_metric log_model"** : les 4 fonctions de base.
- **"joblib dump load Python"** : sérialiser (sauvegarder) un objet Python complexe (modèle sklearn + pipeline + dictionnaire) dans un fichier binaire.

**Mini exercice à écrire (fichier `exercice_j10.py`) :**
```python
import mlflow
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

X = np.random.normal(0, 1, (200, 3))

# Enregistrer un run MLflow
with mlflow.start_run(run_name="test_IF"):
    model = IsolationForest(contamination=0.05, n_estimators=100)
    model.fit(X)

    mlflow.log_param("contamination", 0.05)
    mlflow.log_param("n_estimators", 100)
    mlflow.log_metric("n_anomalies", int((model.predict(X) == -1).sum()))

# Sauvegarder avec joblib
bundle = {"model": model, "name": "IsolationForest", "contamination": 0.05}
joblib.dump(bundle, "mon_modele.joblib")

# Recharger
bundle2 = joblib.load("mon_modele.joblib")
print(f"Modèle rechargé : {bundle2['name']}")

# Lancer 'mlflow ui' dans le terminal pour voir les résultats
```

### Après-midi — Projet : `src/models/train.py` (fonction `train_all`)

Tu reconnais maintenant `mlflow.start_run`, `log_param`, `log_metric`, `joblib.dump`.
- Trouver le bloc `with mlflow.start_run(run_name=name)` dans `train_all` — il boucle sur les 3 modèles.
- Trouver où le bundle final est construit (le dictionnaire avec `model`, `pipeline`, `feature_cols`, `severity_thresholds`) et sauvegardé.
- Action : lancer `make train` puis `mlflow ui` — comparer les 3 runs (IF, OC-SVM, HDBSCAN) sur `auc_roc`.
- Question : le bundle contient `severity_thresholds` avec `p30` et `p70` — à quoi vont-ils servir dans `predict.py` demain ?

---

## Jour 11 — Inférence : du modèle au score de sévérité

### Matin — Théorie + exercice

**Ce que tu dois apprendre :**
- **"machine learning inference pipeline production"** : en production, on n'entraîne pas — on charge le modèle et on prédit sur de nouvelles données. La cohérence avec l'entraînement est critique.
- **"min max normalization score 0 1"** : normaliser un score entre 0 et 1 avec `(x - min) / (max - min)`.
- **"percentile threshold classification"** : utiliser un percentile pour séparer les classes (30ème percentile = seuil low/medium, 70ème = seuil medium/high).

**Mini exercice à écrire (fichier `exercice_j11.py`) :**
```python
import numpy as np
import joblib
from sklearn.ensemble import IsolationForest

# Simuler un score brut (valeurs négatives pour IF)
rng = np.random.default_rng(42)
X_train = rng.normal(0, 1, (500, 3))
X_new   = np.vstack([rng.normal(0, 1, (95, 3)),
                     rng.uniform(4, 6, (5, 3))])  # 5 anomalies

model = IsolationForest(contamination=0.05, random_state=42)
model.fit(X_train)

# Scores bruts
raw = model.decision_function(X_new)

# Normaliser en [0,1] puis inverser (plus grand = plus anormal)
raw_norm = (raw - raw.min()) / (raw.max() - raw.min())
anomaly_score = 1.0 - raw_norm

# Calculer seuils sur le TRAIN (comme le projet)
raw_train = model.decision_function(X_train)
raw_train_norm = (raw_train - raw_train.min()) / (raw_train.max() - raw_train.min())
train_scores = 1.0 - raw_train_norm

p30 = np.percentile(train_scores, 30)
p70 = np.percentile(train_scores, 70)

# Assigner sévérité
def severity(score):
    if score <= p30: return "NORMAL"
    elif score <= p70: return "WARNING"
    return "CRITICAL"

severities = [severity(s) for s in anomaly_score]
print(f"p30={p30:.3f}  p70={p70:.3f}")
print(f"CRITICAL: {severities.count('CRITICAL')}, WARNING: {severities.count('WARNING')}")
```

### Après-midi — Projet : `src/models/predict.py`

Tu reconnais maintenant la normalisation du score, l'inversion, et les seuils percentile.
- Trouver la fonction `predict()` — localiser exactement les lignes de normalisation et d'inversion.
- Trouver `_score_to_severity()` — c'est exactement ta fonction `severity()` du matin.
- Trouver `_apply_pipeline()` — elle applique le pipeline sklearn sauvegardé dans le bundle (le même objet `fit` sur le train).
- Action : lancer `python -m src.models.predict` et observer les sévérités produites.
- Question : si on change `p70` de 0.70 à 0.50 dans le bundle, que se passe-t-il sur le nombre de CRITICAL ?

---

## Jour 12 — SHAP : expliquer une prédiction

### Matin — Théorie + exercice

**Ce que tu dois apprendre :**
- **"SHAP values explained for beginners"** : pour une prédiction donnée, SHAP dit quelle feature a le plus contribué. Ce n'est pas une importance globale — c'est local à **ce** point de données.
- **"shap TreeExplainer IsolationForest"** : explainer rapide pour les modèles basés sur des arbres.
- **"shap waterfall plot"** : graphique qui montre les contributions positives et négatives de chaque feature pour UN point.

**Mini exercice à écrire (fichier `exercice_j12.py`) :**
```python
import numpy as np
import shap
from sklearn.ensemble import IsolationForest

rng = np.random.default_rng(42)
X = np.vstack([rng.normal(0, 1, (100, 4)),
               rng.uniform(5, 8, (3, 4))])  # 3 anomalies

feature_names = ["temperature", "vibration", "pression", "courant"]

model = IsolationForest(contamination=0.03, random_state=42)
model.fit(X)

# SHAP pour la première anomalie (indice 100)
explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X[100:101])

print("Contributions SHAP pour l'anomalie :")
for i, fname in enumerate(feature_names):
    print(f"  {fname}: {shap_values[0][i]:.4f}")

# La feature avec la plus grande valeur absolue est la plus "responsable"
top = np.argmax(np.abs(shap_values[0]))
print(f"\nFeature principale : {feature_names[top]}")
```

### Après-midi — Projet : `src/models/predict.py` (fonction `generate_shap_explanation`) + `notebooks/03_shap_explainability.ipynb`

Tu reconnais maintenant `TreeExplainer`, `shap_values`, et la notion de "top features".
- Trouver dans `generate_shap_explanation()` comment les `top_features` (top 3) sont extraites et structurées en JSON.
- Comprendre pourquoi pour OC-SVM et HDBSCAN, le code utilise `KernelExplainer` (moins rapide que TreeExplainer).
- Ouvrir `notebooks/03_shap_explainability.ipynb` et l'exécuter — observer les waterfall plots.
- Question : les `top_features` SHAP sont stockées dans `ml_decisions.features_json` — qui les utilise ensuite et pour quoi faire ?

---

## Jour 13 — Drift Detection : PSI et test de Kolmogorov-Smirnov

### Matin — Théorie + exercice

**Ce que tu dois apprendre :**
- **"data drift concept machine learning production"** : avec le temps, les données réelles peuvent changer (nouvelles conditions, nouvel équipement). Le modèle entraîné sur les données passées peut se dégrader.
- **"Population Stability Index PSI"** : mesure si la distribution d'une variable a changé entre une référence et une période courante. PSI > 0.2 = dérive significative.
- **"Kolmogorov-Smirnov test Python scipy"** : test statistique qui vérifie si deux séries de nombres suivent la même distribution. `p_value < 0.05` = distributions différentes.

**Mini exercice à écrire (fichier `exercice_j13.py`) :**
```python
import numpy as np
from scipy import stats

rng = np.random.default_rng(42)

# Distribution de référence (entraînement)
reference = rng.normal(0.3, 0.1, 500)  # scores autour de 0.3

# Distribution courante — sans drift
current_ok = rng.normal(0.3, 0.1, 100)
stat1, pval1 = stats.ks_2samp(reference, current_ok)
print(f"Sans drift   — KS stat={stat1:.3f}, p-value={pval1:.3f}")

# Distribution courante — avec drift
current_drift = rng.normal(0.6, 0.15, 100)  # a changé !
stat2, pval2 = stats.ks_2samp(reference, current_drift)
print(f"Avec drift   — KS stat={stat2:.3f}, p-value={pval2:.3f}")

# Règle : p < 0.05 → les distributions sont différentes → drift détecté
```

### Après-midi — Projet : `src/models/drift_detector.py`

Tu reconnais maintenant `stats.ks_2samp` et la comparaison référence/courant.
- Trouver `compute_psi()` — c'est le PSI. Lire les commentaires pour comprendre comment il est calculé (histogrammes).
- Trouver `check_drift()` — elle compare les 5 000 scores les plus anciens (référence) aux 100 scores les plus récents (courant).
- Lancer `python -m src.models.drift_detector` et lire le résultat.
- Question : le `_DRIFT_COOLDOWN_MINUTES=15` empêche d'écrire dans `audit_log` à chaque appel. Pourquoi ce mécanisme existe-t-il ?

---

## Jour 14 — Révision semaine 2 : cycle ML complet

### Matin — Révision active
Reprendre les exercices des jours 8 à 13. Pour chacun, ajouter des commentaires `# connexion avec le projet` qui expliquent où ce concept apparaît dans quel fichier du projet.

### Après-midi — Lancer le cycle ML complet
Exécuter dans l'ordre, avec les commandes du `Makefile` :
1. `make generate` → données en DB
2. `make train` → modèle entraîné + bundle joblib
3. `python -m src.models.predict` → scores en DB
4. `python -m src.models.drift_detector` → vérification drift

Puis ouvrir `notebooks/02_model_training.ipynb` et l'exécuter. Observer la courbe Precision-Recall des 3 modèles.
Question finale de révision : *"Sans regarder le code, expliquer ce que contient `models/best_model.joblib` et pourquoi chaque élément de ce dictionnaire est nécessaire."*

---

## SEMAINE 3 — Agents IA

---

## Jour 15 — LangChain : outils `@tool` et appel au LLM

### Matin — Théorie + exercice

**Ce que tu dois apprendre :**
- **"LangChain tutorial beginners 2024"** : LangChain est une bibliothèque qui facilite la création d'applications avec des LLMs (modèles de langage comme Gemini ou GPT).
- **"LangChain @tool decorator"** : décorer une fonction Python avec `@tool` la rend utilisable par un agent LLM — le LLM peut "appeler" cette fonction quand il en a besoin.
- **"ChatGoogleGenerativeAI langchain tutorial"** : appeler Google Gemini via LangChain.

**Mini exercice à écrire (fichier `exercice_j15.py`) :**
```python
from langchain_core.tools import tool

# Créer un outil simple : une fonction que l'agent pourra appeler
@tool
def get_temperature(machine_id: str) -> str:
    """Retourne la température actuelle d'une machine.

    Args:
        machine_id: Identifiant de la machine.

    Returns:
        Température en degrés Celsius.
    """
    # Simulé — dans le projet réel, ça lit la DB
    temperatures = {"A": "65°C", "B": "42°C", "C": "88°C (CRITIQUE)"}
    return temperatures.get(machine_id, "Machine inconnue")

# Tester l'outil directement (sans agent)
result = get_temperature.invoke({"machine_id": "C"})
print(f"Résultat : {result}")
print(f"Nom de l'outil : {get_temperature.name}")
print(f"Description    : {get_temperature.description}")
```
Objectif : voir qu'un `@tool` est juste une fonction Python ordinaire avec une décoration qui ajoute un nom et une description lisibles par un LLM.

### Après-midi — Projet : `src/agents/detection_agent.py` (les 3 outils seulement)

Tu reconnais maintenant `@tool` et la structure d'un outil LangChain.
- Trouver les 3 fonctions décorées `@tool` : `get_anomaly_data`, `get_machine_history`, `get_shap_explanation`.
- Pour chacune, noter : que prend-elle en paramètre ? Où lit-elle les données (quelle table DB) ? Que retourne-t-elle ?
- Tester chaque outil ISOLÉMENT (sans lancer l'agent) :
  ```python
  from src.agents.detection_agent import get_anomaly_data
  print(get_anomaly_data.invoke({"machine_id": "BROYEUR_01", "n": 3}))
  ```
- Question : la docstring de `get_machine_history` dit "Retrieve historical sensor statistics" — c'est CETTE description que le LLM lira pour décider quand utiliser cet outil. Que se passe-t-il si la docstring est vague ou incorrecte ?

---

## Jour 16 — Pattern ReAct : raisonnement + action

### Matin — Théorie + exercice

**Ce que tu dois apprendre :**
- **"ReAct pattern LLM agent explained"** : le LLM alterne entre "Thought" (réflexion) et "Action" (appel d'outil) jusqu'à avoir assez d'informations pour répondre. C'est un cycle, pas un appel unique.
- **"LangChain create_react_agent AgentExecutor"** : les deux fonctions qui créent l'agent ReAct dans LangChain.
- **"PromptTemplate agent_scratchpad"** : le placeholder `{agent_scratchpad}` dans le prompt est l'endroit où LangChain colle les itérations précédentes (Thought + Action + Observation).

**Mini exercice (lecture + schéma) :**
Pas de code à écrire ce matin. À la place, lire ce pseudo-dialogue et le dessiner comme un schéma :
```
Entrée : "Quel est l'état de la machine BROYEUR_01 ?"

Thought: Je dois d'abord regarder les anomalies récentes.
Action: get_anomaly_data(machine_id="BROYEUR_01", n=5)
Observation: [3 anomalies CRITICAL dans les 2 dernières heures]

Thought: Je dois comparer avec l'historique.
Action: get_machine_history(machine_id="BROYEUR_01", days=7)
Observation: [température moyenne 65°C, actuelle 85°C → +3 sigma]

Thought: J'ai assez d'informations pour diagnostiquer.
Final Answer: {"diagnosis": "Surchauffe roulement...", "severity": "CRITICAL", ...}
```
Objectif : visualiser le cycle avant de le voir dans le code.

### Après-midi — Projet : `src/agents/detection_agent.py` (fonctions `build_detection_agent`, `analyze_machine`, `SYSTEM_PROMPT`)

Tu reconnais maintenant le cycle ReAct et les paramètres `create_react_agent`, `AgentExecutor`.
- Trouver `max_iterations=6` et `max_execution_time=60` — comprendre pourquoi ces limites existent.
- Lire le `SYSTEM_PROMPT` — trouver les 4 étapes du "PROTOCOLE D'ANALYSE" inscrites dedans.
- Lancer `python -m src.agents.detection_agent` et observer le scratchpad (Thought → Action → Observation → ...).
- Question : le scratchpad que tu vois dans le terminal correspond exactement au schéma que tu as dessiné le matin. Combien d'itérations (Action/Observation) l'agent a-t-il utilisé ?

---

## Jour 17 — Pydantic : valider les données structurées

### Matin — Théorie + exercice

**Ce que tu dois apprendre :**
- **"Pydantic BaseModel validation Python"** : définir un modèle de données avec des types stricts. Si une donnée ne respecte pas le schéma, Pydantic lance une erreur claire.
- **"Pydantic Field ge le pattern"** : valider qu'un nombre est dans une plage (`ge=0.0, le=1.0`), ou qu'une chaîne correspond à un pattern (`pattern="^(A|B|C)$"`).
- **"Pydantic model_dump model_validate"** : convertir un objet Pydantic en dictionnaire et inversement.

**Mini exercice à écrire (fichier `exercice_j17.py`) :**
```python
from pydantic import BaseModel, Field

class Diagnostic(BaseModel):
    machine_id: str
    score:      float = Field(ge=0.0, le=1.0)   # entre 0 et 1
    severite:   str   = Field(pattern="^(NORMAL|WARNING|CRITICAL)$")
    confiance:  float = Field(ge=0.0, le=1.0)

# Valide — aucune erreur
d = Diagnostic(machine_id="BROYEUR_01", score=0.72, severite="CRITICAL", confiance=0.85)
print(d.model_dump())  # → dictionnaire Python

# Invalid — va lever une erreur claire
try:
    Diagnostic(machine_id="X", score=1.5, severite="URGENT", confiance=0.5)
except Exception as e:
    print(f"Erreur Pydantic : {e}")
```

### Après-midi — Projet : `src/agents/detection_agent.py` (classe `AgentDecision`) et `src/agents/judge_agent.py` (classes `JudgeInput`, `CriteriaScores`, `JudgeEvaluation`)

Tu reconnais maintenant `BaseModel`, `Field(ge=, le=, pattern=)`.
- Trouver `AgentDecision` — c'est le schéma de sortie de l'agent Detection. Identifier quels champs ont des contraintes `Field`.
- Trouver `JudgeEvaluation` — c'est le schéma de sortie du Judge. Identifier les 5 critères dans `CriteriaScores`.
- Question : `AgentDecision` est créée avec `AgentDecision(**data)` depuis un JSON parsé. Que se passe-t-il si le LLM retourne `"severity": "DANGER"` au lieu de `"CRITICAL"` ?

---

## Jour 18 — Judge Agent : évaluer une décision avec un LLM

### Matin — Théorie + exercice

**Ce que tu dois apprendre :**
- **"LLM as a judge concept"** : utiliser un LLM pour noter la qualité de la réponse d'un autre LLM. Le principe : indépendance — le Judge doit être un appel séparé pour ne pas être influencé par le premier.
- **"SystemMessage HumanMessage LangChain"** : construire un dialogue pour un LLM. `SystemMessage` = les instructions fixes (le "rôle" du LLM). `HumanMessage` = la question ou données variables.
- **"weighted average score calculation"** : Score = 0.25×A + 0.20×B + ... — une moyenne pondérée.

**Mini exercice (lecture + calcul) :**
Pas de code à exécuter. À la place :
1. Lire la grille d'évaluation du Judge dans `src/agents/judge_agent.py` (section `JUDGE_SYSTEM`) — comprendre les 5 critères.
2. Calculer manuellement le score global pour ce diagnostic fictif :
   - Pertinence (R) = 8/10
   - Cohérence historique (H) = 5/10
   - Confiance calibrée (C) = 7/10
   - Conformité OCP (O) = 9/10
   - Faisabilité (F) = 6/10
   - Formule : `0.25×R + 0.20×H + 0.20×C + 0.20×O + 0.15×F`

### Après-midi — Projet : `src/agents/judge_agent.py`

Tu reconnais maintenant `SystemMessage`, `HumanMessage`, la formule de score pondéré, et Pydantic.
- Constater que le Judge **n'utilise PAS** `AgentExecutor` ni `create_react_agent` — c'est un appel direct LLM (pas de boucle ReAct).
- Lancer `python -m src.agents.judge_agent` — observer le JSON retourné.
- Injecter un mauvais diagnostic dans le sample (confidence=0.95, diagnosis="anomalie détectée") et vérifier que `flagged_issues` contient `OVERCONFIDENCE` et `VAGUE_DIAGNOSIS`.
- Question : ligne `evaluation.agreement = evaluation.global_score >= DISAGREEMENT_THRESHOLD` — pourquoi recalculer `agreement` alors que le LLM l'a déjà calculé ?

---

## Jour 19 — async/await et threads : FastAPI + agents bloquants

### Matin — Théorie + exercice

**Ce que tu dois apprendre :**
- **"async await Python explained simply"** : le code asynchrone permet d'attendre plusieurs choses sans bloquer. FastAPI est entièrement asynchrone — il peut traiter 100 requêtes en parallèle.
- **"ThreadPoolExecutor Python blocking code"** : les agents LangChain sont synchrones (bloquants). Pour les utiliser dans FastAPI sans bloquer les autres requêtes, on les exécute dans un thread séparé.
- **"asyncio run_in_executor"** : la fonction qui dit "exécute ce code bloquant dans un thread, et attends le résultat sans bloquer l'event loop".

**Mini exercice à écrire (fichier `exercice_j19.py`) :**
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time

executor = ThreadPoolExecutor(max_workers=2)

def travail_lent(nom: str) -> str:
    """Simule un appel LLM bloquant (3 secondes)."""
    time.sleep(3)
    return f"{nom} terminé"

async def main():
    loop = asyncio.get_running_loop()

    # Lancer 2 travaux en parallèle sans bloquer
    t0 = time.time()
    r1, r2 = await asyncio.gather(
        loop.run_in_executor(executor, travail_lent, "Agent A"),
        loop.run_in_executor(executor, travail_lent, "Agent B"),
    )
    print(f"{r1}, {r2}")
    print(f"Temps total : {time.time()-t0:.1f}s (devrait être ~3s, pas 6s)")

asyncio.run(main())
```
Objectif : voir concrètement que 2 appels bloquants de 3s chacun prennent 3s et non 6s quand ils sont en parallèle.

### Après-midi — Projet : `api/main.py` (fonction `_analyze_sync` + endpoint `POST /analyze`)

Tu reconnais maintenant `ThreadPoolExecutor`, `run_in_executor`, `asyncio.gather`.
- Trouver `_AGENT_POOL = ThreadPoolExecutor(max_workers=4)` — 4 agents peuvent tourner en parallèle.
- Trouver `await loop.run_in_executor(_AGENT_POOL, _analyze_sync, req)` — c'est exactement ton exercice du matin.
- Lancer l'API et envoyer une requête `POST /analyze` — observer `processing_ms` dans la réponse.
- Question : si on envoie 5 requêtes `/analyze` simultanément et que `max_workers=4`, que se passe-t-il pour la 5ème ?

---

## Jour 20 — Gouvernance IA : surveiller le comportement du système

### Matin — Théorie + exercice

**Ce que tu dois apprendre :**
- **"AI governance monitoring metrics"** : en production, un système IA doit être surveillé — pas seulement en termes de performance technique, mais aussi de qualité des décisions.
- **"pandas groupby agg mean std"** : calculer des statistiques agrégées par groupe (par machine, par fenêtre de temps).
- **"alert threshold trigger condition"** : déclencher une alerte quand une métrique dépasse un seuil.

**Mini exercice à écrire (fichier `exercice_j20.py`) :**
```python
import pandas as pd

# Simule des évaluations du Judge (normalement lues depuis la DB)
data = {
    "machine_id": ["A","A","A","B","B","B"],
    "global_score": [7.5, 6.2, 4.8, 8.1, 7.9, 8.3],  # A a un score faible
    "agreement":    [1,   1,   0,   1,   1,   1],       # A a un désaccord
}
df = pd.DataFrame(data)

# Métriques globales
mean_score = df["global_score"].mean() / 10.0
disagreement_rate = 1 - df["agreement"].mean()

print(f"Confiance moyenne  : {mean_score:.1%}")
print(f"Taux de désaccord  : {disagreement_rate:.1%}")

# Alertes
if mean_score < 0.70:
    print("⚠️  ALERTE : confiance trop faible")
if disagreement_rate > 0.30:
    print("⚠️  ALERTE : trop de désaccords")

# Par machine
print(df.groupby("machine_id").agg(score_moy=("global_score","mean"),
                                    desaccords=("agreement", lambda x: 1-x.mean())))
```

### Après-midi — Projet : `src/governance/governance.py`

Tu reconnais maintenant `groupby`, `agg`, les seuils d'alerte, et le concept de monitoring IA.
- Trouver `compute_metrics()` — elle fait exactement ce que tu as fait dans l'exercice mais sur les vraies données en DB, avec 3 fenêtres temporelles.
- Trouver les seuils `CONFIDENCE_THRESHOLD=0.70` et `DISAGREEMENT_THRESHOLD=0.30` — ce sont les seuils de ton exercice.
- Lancer `python -m src.governance.governance` et comparer les métriques des 3 fenêtres.
- Question : modifier `DISAGREEMENT_THRESHOLD` de 0.30 à 0.10 et relancer — combien d'alertes supplémentaires ?

---

## Jour 21 — Révision semaine 3 : flux complet agents + gouvernance

### Matin — Révision active
Reprendre les exercices des jours 15 à 20. Pour chacun, écrire 2 lignes :
- "Ce concept est utilisé dans le projet dans [fichier] à la fonction [nom]."
- "Sans ce concept, [problème concret] se poserait."

### Après-midi — Flux complet
Lancer, dans l'ordre : API démarrée → `POST /analyze` pour les 5 machines → `python -m src.governance.governance`. Puis vérifier en DB :
```sql
SELECT COUNT(*) FROM ml_decisions;
SELECT COUNT(*) FROM judge_evaluations;
SELECT event_type, COUNT(*) FROM audit_log GROUP BY event_type;
```
Question finale : *"Sans regarder le code, expliquer la différence architecturale entre l'agent Detection (ReAct) et l'agent Judge (LLM direct) — pourquoi chacun est-il conçu différemment ?"*

---

## SEMAINE 4 — API, Tests, Production, Maîtrise

---

## Jour 22 — FastAPI : endpoints, Pydantic, validation

### Matin — Théorie + exercice

**Ce que tu dois apprendre :**
- **"FastAPI tutorial beginners"** : créer une API REST en Python. Chaque endpoint est une fonction Python décorée avec `@app.get()` ou `@app.post()`.
- **"FastAPI Pydantic request response validation"** : les schémas Pydantic (`BaseModel`) valident automatiquement ce que le client envoie et ce que l'API retourne.
- **"FastAPI query parameters path parameters"** : `GET /items/{id}` = paramètre de chemin. `GET /items?limit=10` = paramètre de requête.

**Mini exercice à écrire (fichier `exercice_j22.py`) :**
```python
from fastapi import FastAPI, Query
from pydantic import BaseModel
import uvicorn

app = FastAPI()

class MachineResponse(BaseModel):
    machine_id: str
    temperature: float
    status: str

@app.get("/machines/{machine_id}", response_model=MachineResponse)
def get_machine(machine_id: str, detail: bool = Query(default=False)):
    # FastAPI valide automatiquement que machine_id est une string
    return MachineResponse(
        machine_id=machine_id,
        temperature=65.4,
        status="normal" if not detail else "normal (détail activé)"
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
    # Tester : http://localhost:8001/machines/BROYEUR_01?detail=true
    # Puis :   http://localhost:8001/docs
```

### Après-midi — Projet : `api/main.py` (structure globale + schemas Pydantic)

Tu reconnais maintenant les décorateurs `@app.get`, `@app.post`, `response_model`, `Query`.
- Lire les schémas Pydantic : `AnalyzeRequest`, `AnalyzeResponse`, `DecisionRecord`, `GovernanceMetrics`.
- Lister tous les endpoints (méthode + path) — il y en a ~12.
- Lancer l'API et ouvrir `/docs` — voir la documentation générée automatiquement par FastAPI.
- Question : `MachineId` est un `str, Enum` avec les 5 IDs valides. Que retourne FastAPI si on envoie `machine_id="MACHINE_INCONNUE"` ?

---

## Jour 23 — Authentification JWT

### Matin — Théorie + exercice

**Ce que tu dois apprendre :**
- **"JWT JSON Web Token explained"** : un token signé qui contient des informations (user, expiration). Le serveur n'a pas besoin de base de données pour vérifier — il vérifie juste la signature.
- **"httpOnly cookie vs Authorization header"** : cookie httpOnly = inaccessible au JavaScript (protection contre le vol de token). Header = plus simple pour les scripts.
- **"PyJWT encode decode Python"** : créer et vérifier des JWT en Python.

**Mini exercice à écrire (fichier `exercice_j23.py`) :**
```python
import jwt
import datetime

SECRET = "mon_secret_tres_long_32_caracteres_!"

# Créer un token
payload = {
    "sub":  "utilisateur_1",
    "iat":  datetime.datetime.utcnow(),
    "exp":  datetime.datetime.utcnow() + datetime.timedelta(hours=1),
}
token = jwt.encode(payload, SECRET, algorithm="HS256")
print(f"Token : {token[:50]}...")

# Vérifier le token
decoded = jwt.decode(token, SECRET, algorithms=["HS256"])
print(f"Décodé : {decoded}")

# Token expiré
import time
old_payload = {**payload, "exp": datetime.datetime.utcnow() - datetime.timedelta(hours=1)}
old_token = jwt.encode(old_payload, SECRET, algorithm="HS256")
try:
    jwt.decode(old_token, SECRET, algorithms=["HS256"])
except jwt.ExpiredSignatureError:
    print("Token expiré — accès refusé")
```

### Après-midi — Projet : `api/main.py` (fonctions `verify_api_key`, `auth_login`, `auth_me`, `auth_logout`)

Tu reconnais maintenant `jwt.encode`, `jwt.decode`, `ExpiredSignatureError`.
- Trouver `_JWT_SECRET`, `_JWT_ALGO`, `_JWT_HOURS` — ce sont les paramètres de ton exercice.
- Trouver les deux mécanismes dans `verify_api_key` : API Key (header) ET cookie JWT.
- Tester en `curl` : POST `/auth/login` → cookie → GET `/decisions` avec le cookie.
- Question : `_JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))` — que se passe-t-il si le serveur redémarre et qu'aucun `JWT_SECRET` n'est dans `.env` ?

---

## Jour 24 — pytest : tester son code

### Matin — Théorie + exercice

**Ce que tu dois apprendre :**
- **"pytest tutorial beginners"** : écrire des tests automatiques. Une fonction qui commence par `test_` est automatiquement découverte et exécutée par pytest.
- **"pytest fixture conftest"** : des données ou objets partagés entre plusieurs tests. Définis dans `conftest.py`.
- **"FastAPI TestClient pytest"** : simuler des requêtes HTTP vers l'API dans les tests, sans lancer un vrai serveur.

**Mini exercice à écrire (fichier `exercice_j24/test_simple.py`) :**
```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()

@app.get("/add")
def add(a: int, b: int):
    return {"result": a + b}

client = TestClient(app)

def test_add_positifs():
    response = client.get("/add?a=3&b=5")
    assert response.status_code == 200
    assert response.json()["result"] == 8

def test_add_negatif():
    response = client.get("/add?a=-1&b=1")
    assert response.json()["result"] == 0

def test_param_invalide():
    response = client.get("/add?a=abc&b=5")
    assert response.status_code == 422  # FastAPI renvoie 422 si le type est mauvais
```
Lancer avec `pytest exercice_j24/ -v`.

### Après-midi — Projet : `tests/conftest.py`, `tests/test_api.py`, `tests/test_data_generator.py`

Tu reconnais maintenant les fonctions `test_*`, `TestClient`, les assertions.
- Lire `conftest.py` — trouver comment la DB de test est créée (SQLite en mémoire pour ne pas toucher la vraie DB).
- Lancer `pytest tests/ -v --cov=src --cov-report=html` et ouvrir le rapport HTML.
- Écrire UN test supplémentaire pour un endpoint non encore testé (ex: `GET /api/audit-log`).
- Question : les appels à Gemini (agents LLM) dans les tests — sont-ils réels ou mockés ? Trouver la preuve dans le code.

---

## Jour 25 — Docker et CI/CD

### Matin — Théorie + exercice

**Ce que tu dois apprendre :**
- **"Docker tutorial beginners"** : containeriser une application = l'emballer avec toutes ses dépendances dans une "boîte" qui tourne de la même façon partout.
- **"Dockerfile FROM COPY RUN CMD"** : les 4 instructions de base d'un Dockerfile.
- **"GitHub Actions CI tutorial"** : à chaque `git push`, GitHub exécute automatiquement des étapes (tests, build) dans un environnement Linux isolé.

**Mini exercice (lecture uniquement) :**
Chercher sur YouTube : **"Docker in 7 minutes"** et **"GitHub Actions in 5 minutes"**. Regarder sans prendre de notes — juste comprendre le concept visuel.

### Après-midi — Projet : `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`

Tu connais maintenant les concepts Docker et CI.
- Lire le `Dockerfile` — identifier : quelle image de base Python ? Quelles dépendances sont installées ?
- Lire `docker-compose.yml` — combien de services ? Quel port expose l'API ?
- Lire `ci.yml` — quel événement déclenche la CI ? Quelles étapes s'exécutent ?
- Question : `models/best_model.joblib` est produit par `make train` — est-il dans l'image Docker ou doit-il être monté comme volume ? Quelle est la différence en production ?

---

## Jour 26 — Notebooks et rapport de comparaison

### Matin — Pas de nouvelle théorie
Pas de nouveau concept ce matin — tous les outils pour comprendre les notebooks sont déjà acquis.

### Après-midi — Projet : tous les notebooks + `reports/`

Exécuter les 3 notebooks dans l'ordre :
- `notebooks/01_EDA.ipynb` — quelle feature sépare le mieux les anomalies des données normales ?
- `notebooks/02_model_training.ipynb` — tracer la courbe PR des 3 modèles sur le même graphique.
- `notebooks/03_shap_explainability.ipynb` — quelles sont les 5 features SHAP les plus importantes globalement ?

Lire `reports/model_comparison.json` avec Python :
```python
import json
with open("reports/model_comparison.json") as f:
    report = json.load(f)
print(f"Meilleur modèle : {report['best_model']}")
for name, data in report["comparison"].items():
    print(f"  {name} — AUC: {data['metrics']['auc_roc']:.4f}")
```

---

## Jour 27 — Modifier des paramètres et prédire les effets

> Pas de théorie. La maîtrise se prouve en modifiant quelque chose et en prédissant ce qui va changer AVANT de faire le changement.

### Après-midi — 4 exercices de modification

Pour chaque exercice : écrire ta prédiction sur papier, faire la modification, vérifier.

**Exercice 1 — Seuil de sévérité**
Ouvrir `src/models/train.py`, chercher `np.percentile(train_scores, 70)`.
Changer `70` en `50`. Réentraîner (`make train`). Relancer `python -m src.models.predict`.
*Prédiction à noter avant* : le nombre de CRITICAL va-t-il augmenter ou diminuer ?

**Exercice 2 — Contamination Isolation Forest**
Dans `train.py`, remplacer `"contamination": [0.04, 0.06]` par `[0.15, 0.20]`. Réentraîner.
*Prédiction* : l'AUC-ROC va-t-il monter ou descendre ?

**Exercice 3 — Seuil de désaccord du Judge**
Dans `src/agents/judge_agent.py`, changer `DISAGREEMENT_THRESHOLD = 6.0` en `8.0`.
Relancer une analyse et observer `governance.py`.
*Prédiction* : `disagreement_rate` va-t-il augmenter ou diminuer ?

**Exercice 4 — Prompt de l'agent Detection**
Dans `src/agents/detection_agent.py`, supprimer l'étape 3 (SHAP) du SYSTEM_PROMPT.
Relancer `analyze_machine("BROYEUR_01")`.
*Prédiction* : le champ `shap_top_features` dans la réponse sera-t-il vide ou renseigné ?

**Après chaque exercice : revenir à l'état original.**

---

## Jour 28 — Traçabilité : le parcours complet d'une donnée

### Après-midi — Exercice de synthèse

Choisir une ligne dans `ml_decisions` avec `is_anomaly=1` et `severity='CRITICAL'`.
Répondre par écrit à ces 6 questions en citant fichier et fonction :

1. Cette anomalie a été générée dans quel fichier, par quelle fonction, et quel type est-ce (spike/drift/cutoff) ?
2. Quelle feature a le plus contribué à sa détection (SHAP) — si `features_json="{}"`, expliquer pourquoi.
3. Quel modèle l'a détectée (`model_version` en DB) et quel score lui a-t-il attribué ?
4. Quel diagnostic l'agent Detection a-t-il émis — citer le champ `diagnosis` depuis `judge_evaluations`.
5. Quelle note le Judge lui a-t-il donnée et y a-t-il des `flagged_issues` ?
6. Cette anomalie a-t-elle déclenché une entrée dans `audit_log` ? De quel type (`event_type`) ?

---

## Jour 29 — ADRs revisités : les décisions ont-elles tenu leurs promesses ?

Au Jour 1, les ADRs étaient abstraits. Maintenant que tu connais tout le code, relire les 7 ADRs avec un regard critique.

### Après-midi
Pour chaque ADR, répondre par une phrase :
*"J'ai vu cette décision se matérialiser dans [fichier], fonction [nom], à la ligne [numéro approximatif]."*

Puis rédiger un court "ADR-008" fictif sur un choix technique que tu ferais différemment si tu refaisais le projet, avec une justification.

---

## Jour 30 — Évaluation finale

### Exercice 1 — Expliquer (sans ouvrir de fichier)
Pour chacun de ces 11 fichiers, donner son rôle en 2 phrases max :
`data_generator.py` · `config.py` · `db.py` · `feature_engineering.py` · `train.py` · `predict.py` · `drift_detector.py` · `detection_agent.py` · `judge_agent.py` · `governance.py` · `api/main.py`

### Exercice 2 — Tracer le flux
Dessiner, sans aide, le schéma complet d'une anomalie de sa génération jusqu'à `audit_log`. Inclure les noms de tables DB et de fonctions.

### Exercice 3 — Prédire
Si Gemini est indisponible (API down), quelles parties du système continuent de fonctionner ? Quelles parties s'arrêtent ? Citer les lignes de code qui gèrent cette situation (`try/except`).

### Exercice 4 — Expliquer à quelqu'un d'autre
Rédiger un texte de 10 lignes qui explique le projet à quelqu'un qui ne connaît pas le Machine Learning — sans jargon technique.

---

*Plan v4 · Structure théorie+exercice hors projet / lecture du projet*
*OCP Bionic Judge Agent · Mounir Sanbouli*
