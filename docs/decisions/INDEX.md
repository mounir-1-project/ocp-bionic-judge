# Index des Décisions Techniques (ADRs)

> **C'est quoi un ADR ?**  
> Architecture Decision Record. Dans un vrai projet, chaque fois qu'on choisit
> une technologie, un algorithme, ou une architecture — on l'écrit ici avec
> le POURQUOI. Comme ça, dans 6 mois, on comprend pourquoi on a fait ce choix.
> Et si quelqu'un propose de changer, on a les arguments pour ou contre.

---

| N° | Titre | Statut | Date |
|----|-------|--------|------|
| [ADR-001](ADR-001-python-version.md) | Choix de Python 3.11 | ✅ Accepté | 2024-01-15 |
| [ADR-002](ADR-002-database-sqlite-then-postgresql.md) | BDD : SQLite → PostgreSQL | ✅ Accepté | 2024-02-10 |
| [ADR-003](ADR-003-anomaly-detection-model.md) | Modèle : Isolation Forest | ✅ Accepté | 2024-01-20 |
| [ADR-004](ADR-004-ai-agents-langchain-claude.md) | Agents IA : LangChain + Gemini | ✅ Accepté | 2024-02-01 |
| [ADR-005](ADR-005-api-fastapi.md) | API : FastAPI | ✅ Accepté | 2024-02-05 |
| [ADR-006](ADR-006-explainability-shap.md) | Explicabilité : SHAP | ✅ Accepté | 2024-02-08 |
| [ADR-007](ADR-007-mlflow-tracking.md) | Tracking ML : MLflow | ✅ Accepté | 2024-02-10 |

---

## Comment lire un ADR

Chaque ADR répond à ces questions :
1. **Quel problème on avait ?** (Contexte)
2. **Qu'est-ce qu'on aurait dû évaluer AVANT de coder ?** (Critères)
3. **Qu'est-ce qu'on a choisi et pourquoi ?** (Décision)
4. **Pourquoi pas les alternatives ?** (Tableau comparatif)
5. **Quels sont les trade-offs ?** (Conséquences)
6. **Quand changer d'avis ?** (Quand revisiter)

## Statuts possibles

- ✅ **Accepté** : décision active, en production
- 🔄 **Remplacé** : remplacé par un ADR plus récent
- ⚠️ **Déprécié** : toujours en place mais prévu pour changement
- 💡 **Proposé** : en discussion, pas encore décidé
