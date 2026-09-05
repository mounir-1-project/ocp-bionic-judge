# Ingestion — Chargement des données

Ce dossier charge les données DCS depuis le fichier Excel.

## Fichiers

| Fichier | Rôle |
|---------|------|
| `dcs_loader.py` | Lecture du fichier Excel, détection des défauts capteurs |

## Fonctionnement

1. Lecture du fichier `DATA.xlsx` (10 180 horodatages, pas 1h)
2. Détection des défauts capteurs (gel, butée, code qualité)
3. Classification de l'état procédé (RUNNING/TRANSIENT/STOPPED)
4. Retourne `IngestionResult` avec readings et qualité
