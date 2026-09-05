# Alertes — Notifications et alarmes

Ce dossier gère les alertes et notifications du système.

## Fichiers

| Fichier | Rôle |
|---------|------|
| `email.py` | Envoi d'emails au technicien connecté |
| `alarms.py` | Registre des alarmes (cycle de vie ISA-18.2) |
| `workflows.py` | Templates d'interventions (inspection, tamponnage) |

## Fonctionnement

- **Email** : Envoi automatique lors de pannes WARNING/CRITICAL
- **Alarmes** : Suivi du cycle vie (ACTIVE → ACKNOWLEDGED → CLOSED)
- **Workflows** : Templates d'interventions préventives
