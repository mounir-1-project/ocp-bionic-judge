# ADR-001 — Choix de Python 3.11

**Statut** : Accepté  
**Date** : 2024-01-15  
**Auteur** : Mounir Sanbouli  

---

## Contexte

Le projet nécessite un langage de scripting pour le ML, les agents IA, et l'API.
Plusieurs versions de Python sont disponibles. Il faut choisir une version stable et supportée.

## Décision

**Utiliser Python 3.11.**

## Pourquoi Python 3.11 et pas une autre version ?

| Version | Raison d'écarter |
|---------|-----------------|
| Python 3.9 | Trop vieux, pas les derniers `typing` features (ex: `X \| Y` au lieu de `Union[X, Y]`) |
| Python 3.10 | Correct mais 3.11 est 60% plus rapide sur certains benchmarks |
| Python 3.12 | Trop récent au moment du projet — certaines libs ML pas encore compatibles |
| **Python 3.11** | ✅ Stable, rapide, toutes nos dépendances supportées |

## Conséquences

**Positives :**
- Type annotations modernes (`X | None` au lieu de `Optional[X]`)
- Meilleure performance à l'inférence ML
- Support LTS jusqu'en 2027

**Négatives :**
- Certains environnements OCP pourraient avoir Python 3.9 → nécessite mise à jour

## Mise à jour (v1.3)

Python 3.12 est désormais **validé** : la CI exécute la suite de tests sur la matrice
`["3.11", "3.12"]` et toutes les dépendances (scikit-learn, LangChain, SHAP, hdbscan…) sont
compatibles. `pyproject.toml` déclare `requires-python = ">=3.10"`. Python 3.11 reste la
version de référence/déploiement ; 3.12 est supporté.

## Quand revisiter cette décision

- Quand Python 3.12 devient la version de déploiement par défaut sur les machines OCP
- Si une dépendance critique (LangChain, SHAP) abandonne Python 3.11
