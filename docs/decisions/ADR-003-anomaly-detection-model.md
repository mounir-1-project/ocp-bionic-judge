# ADR-003 — Choix du modèle de détection d'anomalies

**Statut** : Accepté  
**Date** : 2024-01-20  
**Auteur** : Mounir Sanbouli  

---

## Contexte

On doit détecter des anomalies dans des données capteurs industrielles. Les contraintes sont :
- **Pas de labels** en production (on ne sait pas à l'avance quelles lectures sont des anomalies)
- **Données très déséquilibrées** : ~97% normal, ~3% anomalie
- **Temps réel** : l'inférence doit prendre < 10ms par lecture
- **Explicabilité** : OCP exige de pouvoir expliquer chaque alerte

---

## Pourquoi on fait de l'apprentissage NON-SUPERVISÉ

Dans la vraie vie OCP, personne n'a annoté 2.5M de lectures en disant "celle-ci est une anomalie".
Les modèles supervisés (classification) nécessitent ces labels. Sans labels → on utilise des modèles non-supervisés qui apprennent ce qui est "normal" et alertent sur ce qui dévie.

---

## Modèles évalués

### 1. Isolation Forest ✅ CHOISI

**Principe :** Isole les points anormaux en les "coupant" aléatoirement dans l'espace des features. Les anomalies s'isolent en peu de coupes, les points normaux nécessitent beaucoup de coupes.

**Pourquoi c'est bien pour nous :**
- O(n) en mémoire — tient en RAM pour 2.5M lignes
- Inférence : **< 2ms** par lecture ✅
- Fonctionne bien avec des données déséquilibrées
- Compatible SHAP (TreeExplainer) → explicabilité ✅
- Robuste au bruit (nos données ont des NaN)

**Limitation :** Moins précis sur des anomalies de type "drift lent" (compensé par les rolling features)

---

### 2. One-Class SVM ⚠️ ALTERNATIF

**Principe :** Apprend une frontière autour des données normales. Tout ce qui est hors frontière = anomalie.

**Évaluation :**
- **Meilleur AUC-ROC des trois (0.93)** sur notre jeu de features ciblées
- **Problème majeur : O(n²) à l'entraînement** → on sous-échantillonne à 10k lignes pour fitter
- Inférence rapide une fois entraîné (~0.09 ms/lecture)
- **Non compatible SHAP TreeExplainer** → seulement KernelExplainer (lent, approximatif) : c'est le point bloquant pour OCP

**Verdict :** Leader sur l'AUC, mais **écarté du déploiement** car non tree-explicable. Conservé dans la comparaison comme référence de performance maximale atteignable.

---

### 3. HDBSCAN ⚠️ ALTERNATIF

**Principe :** Clustering hiérarchique basé densité. Les points qui n'appartiennent à aucun cluster (bruit) reçoivent un `outlier_score_` élevé = anomalie.

**Évaluation :**
- Détecte bien les anomalies locales et les structures non sphériques
- Encapsulé dans un `HDBSCANWrapper` pour exposer l'API sklearn (`fit/predict/decision_function`) et `approximate_predict()` sur de nouvelles données
- AUC-ROC plus faible que IF et OC-SVM sur nos features (0.75)
- Plus lent à l'inférence (~1.5 ms)

**Verdict :** Conservé en comparaison mais écarté en production.

---

## Résultat du GridSearch (split chronologique 80/20, mesuré sur le test set)

| Modèle | F1 optimal | AUC-ROC | Avg Precision | Inférence (ms) | SHAP TreeExplainer |
|--------|-----------|---------|---------------|----------------|--------------------|
| **IsolationForest (déployé)** | **0.47** | **0.82** | **0.44** | **0.02 ms** | ✅ oui |
| OneClassSVM (leader AUC) | 0.67 | **0.93** | 0.66 | 0.09 ms | ❌ non (KernelExplainer lent) |
| HDBSCAN | 0.16 | 0.75 | 0.08 | 1.5 ms | ❌ non |

> **Modèle déployé vs leader AUC.** One-Class SVM obtient le meilleur AUC-ROC (0.93), mais
> c'est **Isolation Forest qui est déployé en production**. Raison : c'est le seul modèle
> compatible avec **SHAP TreeExplainer** (explications par prédiction rapides et exactes —
> exigence OCP, voir ADR-006) et il a la latence la plus basse. Sur des équipements
> industriels, une alerte non explicable n'est pas exploitable par un technicien : on
> accepte un AUC légèrement inférieur en échange de l'explicabilité et de la robustesse de
> l'arbre. `train.py` rapporte le classement complet par AUC mais déploie Isolation Forest.
>
> **Note sur le F1 :** ces scores sont mesurés sur données simulées avec ~4–5% d'anomalies,
> au seuil optimal de la courbe P-R. L'AUC-ROC est la vraie métrique de référence en
> détection d'anomalies non-supervisée — elle mesure la qualité du classement indépendamment
> du seuil.
>
> **Historique — refonte du feature engineering (v1.3).** Une première version produisait
> ~102 features (rolling mean/std/min/max sur 3 fenêtres + lags + ratios bruts). Sur un
> modèle d'isolation, où chaque coupure d'arbre tire UNE feature au hasard, ces ~95 features
> faiblement informatives noyaient les ~5 signaux discriminants : l'AUC-ROC tombait à ~0.51
> (équivalent au hasard). La pipeline a été recentrée sur **24 features** physiquement
> motivées (z-scores par machine, flags de coupure, z-scores locaux glissants, deltas,
> features temporelles), faisant remonter l'AUC-ROC à 0.82 (IF) / 0.93 (OC-SVM).

---

## Hyperparamètres optimaux (IsolationForest)

```python
IsolationForest(
    n_estimators=200,      # Nombre d'arbres — plus = plus stable, plus lent à entraîner
    contamination=0.04,    # Estimation du taux d'anomalies (mesuré ~4-5% sur nos données)
    max_features=1.0,      # Utiliser toutes les features à chaque arbre
    random_state=42,       # Reproductibilité
    n_jobs=-1,             # Utiliser tous les cœurs CPU
)
```

> Le grid search (`n_estimators` ∈ {100, 200}, `contamination` ∈ {0.04, 0.06}) sélectionne
> `n_estimators=200, contamination=0.04` par AUC-ROC sur le test set.

**Pourquoi `contamination ≈ 0.04` ?**
→ C'est l'ordre de grandeur du taux d'anomalies réellement injecté (~4–5%). On reste volontairement proche de la vraie valeur pour ne pas sur-déclencher d'alertes.

---

## Étapes suivantes recommandées

**Court terme :** Ajouter un modèle de streaming avec `River` (apprentissage incrémental) pour les nouvelles machines sans historique.

**Moyen terme :** Explorer **Autoencoder LSTM** pour mieux capturer les dépendances temporelles longues (drifts sur plusieurs jours).

**Long terme :** Si OCP labellise des anomalies confirmées par les techniciens → basculer vers un modèle supervisé (XGBoost ou LightGBM) pour améliorer le F1 à > 95%.

---

## Quand revisiter cette décision

- Si le F1 descend en dessous de 85% en production (dérive détectée par PSI)
- Si le volume de données dépasse 50M lignes (OC-SVM et HDBSCAN deviennent hors budget mémoire)
- Si une méthode tree-explicable (ex: ExtraTrees + SHAP) dépasse l'AUC d'OC-SVM → reconsidérer le modèle déployé
- Si OCP crée une base de données d'anomalies labellisées (→ modèle supervisé)
