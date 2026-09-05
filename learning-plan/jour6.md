# JOUR 6 — Machine Learning : Isolation Forest

## Objectif du jour

À la fin de cette journée, tu dois être capable de :
- Expliquer ce qu'est le Machine Learning non supervisé
- Comprendre le principe d'Isolation Forest
- Connaître les paramètres et leur signification
- Expliquer le score et son interprétation
- Comprendre l'explicabilité par occlusion

---

## PARTIE 1 — Introduction au Machine Learning (2h)

### 1.1 Qu'est-ce que le Machine Learning ?

Le **Machine Learning** (apprentissage automatique) est une technique qui permet à un ordinateur d'apprendre à partir de données, sans être explicitement programmé pour chaque cas.

### 1.2 Supervisé vs Non supervisé

| Type | Principe | Exemple |
|------|----------|---------|
| **Supervisé** | On donne des exemples étiquetés (entrée → sortie) | Chat vs Chien (on montre des photos étiquetées) |
| **Non supervisé** | On donne des données sans étiquettes, le modèle trouve des patterns | Regrouper des clients par comportement |

### 1.3 Pourquoi notre projet utilise du non supervisé ?

**Problème** : nous n'avons PAS d'historique de pannes étiquetées. On ne sait pas quelles heures étaient "anormales" dans le passé.

**Solution** : on montre au modèle des données "normales" (la période de référence) et il apprend ce qui est normal. Tout ce qui s'écarte fortement = anomalie potentielle.

### 1.4 Qu'est-ce qu'une anomalie ?

Une **anomalie** est une observation qui s'écarte significativement du comportement normal.

**Important** : une anomalie n'est PAS une panne. C'est un signal qui mérite attention.

**Différence** :
- **Anomalie** : le système détecte quelque chose d'inhabituel
- **Panne** : l'équipement est en panne (confirmé par un expert)

Notre système détecte des anomalies, pas des pannes.

---

## PARTIE 2 — Isolation Forest (3h)

### 2.1 Le principe intuitif

**Fichier** : `core/detection/detector.py` → classe `StatisticalDetector`

Imagine que tu as un tas de feuilles blanches et une feuille rouge. Comment trouves-tu la rouge ?

**Méthode 1** : regarder chaque feuille une par une → long
**Méthode 2** : couper le tas en deux, puis en deux, etc. → la rouge est isolée rapidement

C'est le principe d'Isolation Forest : **une anomalie est plus facile à isoler** qu'une observation normale.

### 2.2 Le fonctionnement technique

Isolation Forest construit des **arbres de décision** avec des coupes aléatoires :

1. Choisis une feature au hasard
2. Choisis une valeur de coupe au hasard entre min et max
3. Coupe les données en deux
4. Répète jusqu'à isoler le point

**Score** = nombre moyen de coupes pour isoler un point :
- Point normal → beaucoup de coupes → score faible
- Point anormal → peu de coupes → score élevé

### 2.3 Les paramètres

**Fichier** : `core/detection/detector.py`

```python
IsolationForest(
    n_estimators=300,      # Nombre d'arbres
    contamination=0.02,    # % d'anomalies attendues
    max_samples=1024,      # Taille des sous-échantillons
    random_state=42        # Graine aléatoire
)
```

| Paramètre | Valeur | Signification |
|-----------|--------|---------------|
| `n_estimators` | 300 | Plus d'arbres = plus stable, mais plus lent |
| `contamination` | 0.02 | On s'attend à 2% d'anomalies |
| `max_samples` | 1024 | Chaque arbre voit 1024 heures |
| `random_state` | 42 | Pour la reproductibilité |

### 2.4 Le score brut

Le modèle produit un **score brut** pour chaque observation :
- Plus le score est élevé, plus le point est anormal
- Le score est proportionnel au nombre de coupes nécessaires

### 2.5 La normalisation

**Fichier** : `core/detection/detector.py`

Le score brut est transformé en **probabilité** via une sigmoïde :

```
score = 1 / (1 + exp(-z))
```

Où z est le score brut standardisé.

**Résultat** : score ∈ [0, 1]
- score ≈ 0 → très normal
- score ≈ 1 → très anormal

### 2.6 Le seuil

**Fichier** : `core/detection/detector.py`

Le seuil est le quantile (1 - contamination) = 98ème percentile.

```
threshold_ = quantile(0.98) des scores normalisés
```

**Règle** : score > threshold → **anomalie**

---

## PARTIE 3 — L'explicabilité (1h)

### 3.1 Pourquoi expliquer ?

Un modèle qui dit "c'est anormal" sans expliquer pourquoi n'est pas utile pour un opérateur. Il faut savoir **quelle variable** a causé l'anomalie.

### 3.2 L'occlusion exacte

**Fichier** : `core/detection/detector.py` → méthode `attribute`

**Principe** : pour chaque feature, on remplace sa valeur par la **médiane de référence** et on recalcule le score.

**La chute de score = contribution de cette feature** à l'anomalie.

**Exemple** :
- Score original : 0.85
- Score sans `ua_residual_z` : 0.40
- Contribution de `ua_residual_z` : 0.85 - 0.40 = **+0.45**

Ça veut dire : "si UA avait été normal, le score serait tombé de 0.85 à 0.40".

### 3.3 L'attribution

**Fichier** : `core/detection/detector.py`

On retourne les **top 5** features les plus contributives, triées par contribution décroissante.

---

## PARTIE 4 — La persistance (1h)

### 4.1 Pourquoi la persistance ?

Une anomalie isolée (1 heure) n'est pas alarmante. Ça peut être un artefact d'acquisition.

**Exigence** : on ne déclenche une alerte que si l'anomalie est **persistante**.

### 4.2 Les constantes

**Fichier** : `core/detection/detector.py`

```python
MODEL_PERSIST_WIN = 6    # Fenêtre de 6 heures
MODEL_PERSIST_MIN = 3    # Minimum 3 heures atypiques sur 6
```

**Règle** : il faut au moins 3 heures atypiques sur les 6 dernières heures pour que l'anomalie soit considérée comme persistante.

### 4.3 Pourquoi 3/6 ?

- Moins de 3h → trop bref, probablement un artefact
- Plus de 3h sur 6 → tendance confirmée

---

## PARTIE 5 — Manipulation (2h)

### 5.1 Explorer le modèle

**Exécute :**
```bash
python -c "
from core.detection.detector import StatisticalDetector
from core.features.e7301_features import MODEL_FEATURES

det = StatisticalDetector()
print('=== Configuration du modèle ===')
print(f'Features: {len(det.features)}')
print(f'Contamination: {det.contamination}')
print(f'Nombre d arbres: {det.model.n_estimators}')
print(f'Max samples: {det.model.max_samples}')
"
```

### 5.2 Comprendre le score

**Exercice** : avec ces scores, quel est le plus anormal ?
- A : 0.15
- B : 0.50
- C : 0.85
- D : 0.95

**Réponse** : D (0.95) est le plus anormal. Si le seuil est 0.98, aucun n'est alertant. Si le seuil est 0.80, C et D sont alertants.

---

## Ce que je dois retenir

1. Isolation Forest isole les anomalies plus facilement que les observations normales
2. contamination=0.02 → 2% d'anomalies attendues
3. n_estimators=300 → 300 arbres pour la robustesse
4. Score ∈ [0,1], seuil = quantile 98ème
5. Occlusion = contribution de chaque feature au score
6. Persistance ≥ 3h/6h pour alerte
7. Une anomalie n'est PAS une panne

---

## Questions du jury

**Faciles :**
1. "Qu'est-ce que le Machine Learning non supervisé ?"
2. "Pourquoi Isolation Forest ?"
3. "Que signifie contamination=0.02 ?"

**Techniques :**
4. "Comment le modèle produit-il son score ?"
5. "Comment expliquez-vous une anomalie ?"
6. "Que signifie l'occlusion exacte ?"
7. "Pourquoi 300 arbres ?"

**Pièges :**
8. "Votre modèle prédit-il une panne ?"
9. "Quelle différence entre anomalie et panne ?"
10. "Que se passe-t-il si les données de référence ne sont pas représentatives ?"
11. "Pourquoi pas un modèle supervisé ?"

---

## Test de fin de journée

1. **Explique** comment Isolation Forest fonctionne avec une analogie simple
2. **Explique** le calcul du score et son interprétation
3. **Explique** l'occlusion avec un exemple concret
4. **Pourquoi** 3 heures atypiques sur 6 pour la persistance ?
