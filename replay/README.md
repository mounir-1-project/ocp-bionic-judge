# Replay — Rejeu temps réel

Ce dossier contient le moteur de rejeu accéléré des données DCS.

## Fichiers

| Fichier | Rôle |
|---------|------|
| `replay.py` | Simulation du flux de données en temps réel |

## Fonctionnement

- Parcourt l'historique heure par heure
- Applique la vitesse sélectionnée (1 jour/s, 5 jours/s, 1 mois/s)
- Émet les analyses en temps réel
- Alimente le dashboard et les notifications

## Vitesse

La vitesse est en heures de process par seconde réelle :
- 24 h/s = 1 jour/s
- 120 h/s = 5 jours/s
- 720 h/s = 1 mois/s
