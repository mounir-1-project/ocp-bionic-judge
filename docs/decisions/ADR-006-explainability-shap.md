# ADR-006 — Explicabilité ML : SHAP

**Statut** : Accepté  
**Date** : 2024-02-08  

---

## Contexte

OCP Group opère dans un secteur réglementé. Chaque décision de maintenance doit être **justifiable** auprès des ingénieurs, des auditeurs, et des assurances. Un modèle "boîte noire" qui dit juste "anomalie" n'est pas acceptable.

## Décision

Utiliser **SHAP** (SHapley Additive exPlanations) pour expliquer chaque prédiction du modèle.

## Alternatives évaluées

| Méthode | Évaluation | Verdict |
|---------|-----------|---------|
| **SHAP** | Fondé sur la théorie des jeux (Shapley values), model-agnostic, plots standard industrie | ✅ Choisi |
| LIME | Plus rapide mais moins fiable (approximation locale instable) | ❌ |
| Feature importance (sklearn) | Global uniquement, pas par prédiction individuelle | ❌ |
| Grad-CAM | Pour images (CNN) — hors scope | ❌ |

## Ce que SHAP produit dans ce projet

```
Exemple : BROYEUR_01 — anomaly_score = 0.87

SHAP Waterfall Plot :
Base value: 0.42
+ temperature_roll_mean_15min : +0.31  ← température en hausse sur 15min
+ vibration_roll_std_5min     : +0.18  ← vibrations instables
- rpm_lag5                    : -0.04  ← RPM stable (facteur rassurant)
= Prediction: 0.87 (CRITICAL)
```

Le technicien OCP lit : "La hausse de température sur 15 min + instabilité des vibrations expliquent 56% de l'alerte."

## Quand revisiter

- Si on passe à un modèle Deep Learning → utiliser SHAP DeepExplainer
- Si SHAP devient trop lent (>500ms) → utiliser FastTreeSHAP ou pré-calculer en batch
