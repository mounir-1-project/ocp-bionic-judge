# Guide de Contribution — OCP Bionic Judge

> **C'est quoi un CONTRIBUTING.md ?**  
> C'est le contrat entre les développeurs d'un projet. Il explique comment
> contribuer correctement : comment nommer ses branches, écrire ses commits,
> ouvrir une Pull Request, etc. Dans un vrai projet en équipe, tout le monde
> suit ces règles pour garder un historique propre.

---

## Avant de commencer

1. Lis le `README.md` pour comprendre le projet
2. Lis les ADRs dans `docs/decisions/` pour comprendre pourquoi les choix ont été faits
3. Assure-toi que les tests passent sur ta machine : `pytest tests/ -v`

---

## Branches Git

```
main          ← production stable (protégée — pas de push direct)
develop       ← intégration des features
feat/xxx      ← nouvelle fonctionnalité
fix/xxx       ← correction de bug
docs/xxx      ← documentation uniquement
refactor/xxx  ← refactoring sans changement de comportement
```

**Exemple :**
```bash
git checkout -b feat/timescaledb-migration
git checkout -b fix/shap-waterfall-crash
git checkout -b docs/adr-008-caching-strategy
```

---

## Convention de commit (Conventional Commits)

Format : `type(scope): description courte`

```bash
feat(models): add LSTM autoencoder for long-term drift detection
fix(api): handle empty decisions table gracefully (500 → 404)
docs(adr): add ADR-008 for caching strategy
refactor(db): extract connection factory to src/db.py
test(governance): add parametrize tests for all time windows
chore(deps): upgrade langchain to 0.3.5
```

**Types valides :**
- `feat` : nouvelle fonctionnalité
- `fix` : correction de bug
- `docs` : documentation uniquement
- `refactor` : restructuration sans changement fonctionnel
- `test` : ajout ou modification de tests
- `chore` : tâches de maintenance (deps, CI, config)
- `perf` : amélioration de performance

---

## Avant chaque Pull Request

```bash
# 1. Mettre à jour depuis main
git fetch origin
git rebase origin/main

# 2. Vérifier que les tests passent
pytest tests/ -v --cov=src --cov-report=term-missing

# 3. Vérifier le style de code (config dans pyproject.toml)
ruff check src/ api/ tests/

# 4. Vérifier les type annotations
mypy src/ --ignore-missing-imports

# 5. S'assurer qu'il n'y a pas de secrets dans le code
git diff origin/main | grep -i "api_key\|password\|secret"
# → Ne doit rien trouver
```

---

## Règles de code

### Type annotations obligatoires
```python
# ❌ Mauvais
def load_data(path, limit):
    ...

# ✅ Bon
def load_data(path: Path, limit: Optional[int] = None) -> pd.DataFrame:
    ...
```

### Docstrings Google style obligatoires sur toutes les fonctions publiques
```python
# ❌ Mauvais
def compute_psi(ref, cur):
    ...

# ✅ Bon
def compute_psi(reference: np.ndarray, current: np.ndarray, n_bins: int = 10) -> float:
    """Compute Population Stability Index between two distributions.

    Args:
        reference: Reference distribution (training scores).
        current: Current production scores.
        n_bins: Number of histogram bins.

    Returns:
        PSI value. Higher = more drift.
    """
```

### Pas de secrets dans le code
```python
# ❌ JAMAIS
api_key = "AQ.Ab8RN6KQ1G_..."

# ✅ Toujours depuis .env
api_key = os.getenv("GEMINI_API_KEY")
```

### Logs structurés avec loguru
```python
# ❌ Mauvais
print("Model trained")

# ✅ Bon
logger.success(f"Model trained: F1={f1:.4f} | params={best_params}")
```

---

## Ajouter une décision technique (ADR)

Si tu changes une technologie, un algorithme, ou une architecture :
1. Crée `docs/decisions/ADR-XXX-titre.md`
2. Suis le format des ADRs existants :
   - **Contexte** : quel problème tu résous
   - **Pourquoi AVANT** : ce qui existait et ses limites
   - **Décision** : ce que tu as choisi
   - **Alternatives évaluées** : tableau comparatif
   - **Conséquences** : trade-offs
   - **Quand revisiter**
3. Référence l'ADR dans le CHANGELOG

---

## Modifier le schéma de base de données

**Toute modification de schéma nécessite :**

1. Mettre à jour `docs/schemas/database_schema.md`
2. Créer un script de migration Alembic :
   ```bash
   alembic revision --autogenerate -m "add column X to table Y"
   alembic upgrade head
   ```
3. Tester la migration sur une BDD vide ET une BDD avec données existantes
4. Mettre à jour `src/db.py` si le DDL change

---

## Structure d'un test acceptable

```python
# ✅ Un bon test
def test_compute_psi_high_for_shifted_distribution():
    """PSI doit être > 0.2 pour des distributions très différentes."""
    rng = np.random.default_rng(42)
    ref = rng.normal(0, 1, 1000)    # distribution de référence
    cur = rng.normal(5, 1, 1000)    # distribution décalée de 5 sigma
    
    psi = compute_psi(ref, cur)
    
    assert psi > 0.2, f"PSI devrait être > 0.2 mais est {psi:.4f}"
```

**Règles des tests :**
- 1 test = 1 comportement précis
- Nom du test = description du comportement testé
- `pytest.mark.parametrize` pour les cas limites
- Pas de connexion réseau dans les tests unitaires (mocker les APIs externes)
