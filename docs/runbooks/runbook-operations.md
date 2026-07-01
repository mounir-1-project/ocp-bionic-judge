# Runbook Opérationnel — OCP Bionic Judge

> **C'est quoi un runbook ?**  
> C'est le manuel de l'opérateur. Dans un vrai projet, quand quelque chose casse à 3h du matin,
> le technicien de garde ouvre ce fichier et suit les étapes. Pas besoin de comprendre le code.

---

## 1. Démarrage du système (ordre obligatoire)

```bash
# Étape 1 : Vérifier que PostgreSQL tourne
pg_isready -h localhost -p 5432
# ✓ Si OK → passe à l'étape 2
# ✗ Si FAIL → voir section "PostgreSQL ne démarre pas" ci-dessous

# Étape 2 : Activer l'environnement Python
cd ocp-bionic-judge
venv\Scripts\activate          # Windows
source venv/bin/activate       # Linux/Mac

# Étape 3 : Vérifier les variables d'environnement
python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.getenv('DATABASE_URL'))"
# ✓ Doit afficher l'URL de ta BDD

# Étape 4 : Lancer l'API
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
# ✓ Vérifier : http://localhost:8000/health → {"status": "ok"}

# Étape 5 : Lancer le frontend React (nouveau terminal)
cd frontend && npm install && npm run dev
# ✓ Vérifier : http://localhost:5173 → page de connexion OCP Bionic Judge
# Clé par défaut : ocp-bionic-dev-key (définie dans .env → OCP_API_KEY)
```

---

## 2. Procédures de maintenance courantes

### Générer de nouvelles données (dev/test)
```bash
python data/data_generator.py
# Durée : ~5 minutes pour 6 mois de données
# Résultat : data/ocp_bionic.db (SQLite) ou tables PostgreSQL remplies
```

### Réentraîner les modèles
```bash
python src/models/train.py
# Durée : 5-15 minutes selon CPU
# Résultat : models/best_model.joblib + reports/model_comparison.json
# Vérifier : F1-score > 0.85 sinon investiguer (voir ADR-003)
```

### Vérifier la dérive du modèle
```bash
python src/models/drift_detector.py
# Résultat : {"psi": X, "drift_detected": true/false}
# Seuil d'alerte : PSI > 0.2 ou ks_pvalue < 0.05
# Si drift → réentraîner le modèle (voir "Réentraîner les modèles")
```

---

## 3. Résolution des problèmes courants

### Problème : "Model not found at models/best_model.joblib"
```
Cause   : Le modèle n'a jamais été entraîné, ou le fichier a été supprimé
Solution: python src/models/train.py
```

### Problème : "database is locked" (SQLite uniquement)
```
Cause   : Plusieurs processus écrivent en même temps dans SQLite
Solution: Migrer vers PostgreSQL (voir ADR-002)
         Ou : tuer les processus Python qui tiennent la connexion
         ps aux | grep python  →  kill PID
```

### Problème : "GEMINI_API_KEY not found"
```
Cause   : Le fichier .env n'existe pas ou la clé est manquante
Solution: cp .env.example .env  →  éditer .env  →  ajouter la clé Google AI Studio
          https://aistudio.google.com/app/apikey
```

### Problème : API répond 503 sur /analyze
```
Cause   : Le modèle n'est pas chargé
Solution: python src/models/train.py  →  relancer l'API
```

### Problème : Dashboard vide (pas de graphiques)
```
Cause 1 : Pas de données en BDD
Solution: python data/data_generator.py

Cause 2 : Pas de prédictions ML en BDD
Solution: python src/models/predict.py

Cause 3 : Mauvaise DATABASE_URL dans .env
Solution: vérifier .env → relancer l'API (uvicorn) + le frontend (npm run dev)

Cause 4 : L'API n'est pas démarrée
Solution: vérifier http://localhost:8000/health → lancer uvicorn si absent
```

### Problème : F1-score < 0.80 après réentraînement
```
Cause possible 1 : Les données ont changé de distribution (drift)
Solution         : Vérifier avec drift_detector.py

Cause possible 2 : Trop peu de données d'entraînement
Solution         : Augmenter la période de simulation dans data_generator.py

Cause possible 3 : Mauvais hyperparamètres
Solution         : Élargir le ParameterGrid dans train.py
```

---

## 4. Surveillance (monitoring)

### Métriques à surveiller quotidiennement

| Métrique | Seuil d'alerte | Comment vérifier |
|----------|---------------|-----------------|
| F1-score du modèle | < 0.85 | `reports/model_comparison.json` |
| PSI (dérive) | > 0.20 | `python src/models/drift_detector.py` |
| Score Judge moyen | < 7.0/10 | `GET /governance-metrics?window=24h` |
| Taux désaccord | > 30% | `GET /governance-metrics?window=24h` |
| Temps inférence ML | > 10ms | Table `ml_decisions`, colonne `inference_ms` |

### Requête de monitoring rapide
```python
# Coller dans un terminal Python pour voir l'état global
from src.governance.governance import compute_metrics
m = compute_metrics(window="24h")
print(f"Confidence: {m.get('mean_judge_confidence', 0)*100:.1f}%")
print(f"Disagreement: {m.get('disagreement_rate', 0)*100:.1f}%")
print(f"Alerts: {len(m.get('alerts', []))}")
```

---

## 5. Sauvegarde des données

### PostgreSQL (production)
```bash
# Backup quotidien recommandé
pg_dump -U ocp_user -h localhost ocp_bionic > backup_$(date +%Y%m%d).sql

# Restore
psql -U ocp_user -h localhost ocp_bionic < backup_20240215.sql
```

### SQLite (développement)
```bash
# Simplement copier le fichier
cp data/ocp_bionic.db backups/ocp_bionic_$(date +%Y%m%d).db
```

---

## 6. Installation PostgreSQL (première fois)

### Windows
```bash
# Option recommandée : Docker
docker run --name ocp-postgres \
  -e POSTGRES_USER=ocp_user \
  -e POSTGRES_PASSWORD=ocp_password \
  -e POSTGRES_DB=ocp_bionic \
  -p 5432:5432 \
  -d postgres:15
```

### Puis dans .env
```
DATABASE_URL=postgresql://ocp_user:ocp_password@localhost:5432/ocp_bionic
```

### Créer le schéma automatiquement
```bash
python -c "from src.db import get_engine, init_schema; init_schema(get_engine())"
```
