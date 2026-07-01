# ADR-007 — Suivi des expériences ML : MLflow

**Statut** : Accepté  
**Date** : 2024-02-10  

---

## Problème

Sans tracking, si on entraîne 20 configurations de modèles et qu'on oublie les paramètres du meilleur → impossible de reproduire le résultat. En industrie, la reproductibilité est non-négociable.

## Décision

Utiliser **MLflow** pour logger chaque expérience.

## Ce que MLflow enregistre automatiquement

```python
with mlflow.start_run(run_name="IsolationForest_v2"):
    mlflow.log_params({"n_estimators": 200, "contamination": 0.05})
    mlflow.log_metrics({"f1": 0.913, "auc_roc": 0.943, "inference_ms": 1.8})
    mlflow.sklearn.log_model(model, "model")
```

→ Interface web sur http://localhost:5000 avec historique complet, comparaison de runs, artefacts.

## Alternatives évaluées

| Outil | Évaluation | Verdict |
|-------|-----------|---------|
| **MLflow** | Open source, self-hosted, intégration sklearn native, standard industrie | ✅ Choisi |
| Weights & Biases | Très bien mais payant pour équipes | ❌ (budget) |
| Neptune.ai | Similaire à W&B | ❌ (budget) |
| Fichiers JSON manuels | Simple mais pas de comparaison visuelle | ❌ |

## Mise à jour (v1.3) — MLflow optionnel

L'import de MLflow dans `src/models/train.py` est désormais encapsulé dans un `try/except` :
si le package n'est pas installé, l'entraînement tourne quand même et saute simplement le
tracking (un avertissement est loggé). Cela allège la CI et permet de lancer `make train`
sur une machine minimale, tout en conservant le tracking complet quand MLflow est présent.

## Quand revisiter

- Si OCP a déjà une plateforme MLOps (ex: Azure ML, AWS SageMaker) → intégrer MLflow à la plateforme existante
- En production → configurer un serveur MLflow distant avec S3 pour les artefacts
