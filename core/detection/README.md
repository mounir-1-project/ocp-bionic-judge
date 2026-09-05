# Détection d'anomalies

Ce dossier contient le moteur de détection du refroidisseur E7301.

## Fichiers

| Fichier | Rôle |
|---------|------|
| `detector.py` | Détection complète (règles + modèle statistique) |
| `detection_agent.py` | Transforme les constatations en diagnostic |
| `schemas.py` | Schémas de données Pydantic |

## Architecture

### Moteur de règles (RuleEngine)
6 règles déterministes dérivées de l'AMDEC :
1. SENSOR_FAULT — état des capteurs
2. CONTROL_LOSS — perte de contrôle température
3. FOULING_DRIFT — dérive du coefficient d'échange
4. CONC_DROP — chute de titre acide
5. T_IN_HIGH — température d'entrée excessive
6. FLOW_LOW — débit acide anormal

### Modèle statistique (StatisticalDetector)
- Isolation Forest sur 11 features physiques
- Attribution par occlusion exacte
- Score normalisé dans [0, 1]

### Fusion
Le score final combine les deux étages et retient la sévérité la plus élevée.
