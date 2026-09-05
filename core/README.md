# Core — Logique métier du projet E7301

Ce dossier contient toute la logique métier du système de surveillance du refroidisseur E7301.

## Structure

| Dossier | Rôle |
|---------|------|
| `detection/` | Détection d'anomalies (règles + Isolation Forest) |
| `verification/` | Contrôle de cohérence (8 vérifications du Judge) |
| `knowledge/` | Connaissance métier (AMDEC, tags, topologie) |
| `features/` | Ingénierie des features (calcul UA, features physiques) |
| `ingestion/` | Chargement des données DCS depuis Excel |
| `analytics/` | Indicateurs opérationnels (KPI) |
| `alerts/` | Alertes, alarmes et notifications email |

## Fichiers à la racine

| Fichier | Rôle |
|---------|------|
| `config.py` | Configuration centralisée (variables d'environnement) |
| `pipeline.py` | Pipeline de bout en bout (orchestrateur) |
| `formatting.py` | Utilitaires de formatage (nombres français) |

## Flux de données

```
Données DCS (Excel)
    ↓
Ingestion (dcs_loader.py)
    ↓
Features (thermal.py, e7301_features.py)
    ↓
Détection (detector.py = règles + Isolation Forest)
    ↓
Diagnostic (detection_agent.py)
    ↓
Vérification (judge_agent.py = 8 contrôles)
    ↓
Résultat (Analysis)
```

## Point d'entrée

Le pipeline est le point d'entrée unique :

```python
from core.pipeline import E7301Pipeline

pipeline = E7301Pipeline()
analysis = pipeline.analyze_at("2024-10-25T21:00:00")
```
