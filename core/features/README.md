# Features — Ingénierie des variables

Ce dossier calcule les features physiques pour la détection.

## Fichiers

| Fichier | Rôle |
|---------|------|
| `thermal.py` | Calcul UA (coefficient d'échange) par effectiveness-NTU |
| `e7301_features.py` | Construction des 11 features pour le modèle |

## Features calculées

1. **ua_residual_z** — Écart du coefficient d'échange
2. **ua_residual_trend_14d** — Tendance UA sur 14 jours
3. **regulation_effort_z** — Effort de régulation
4. **t_in_residual_z** — Résidu température d'entrée
5. **conc_min** — Titre acide minimal
6. **conc_bias_drift_z** — Dérive biais analyseurs
7. **conc_drop_24h** — Chute titre sur 24h
8. **flow_per_load** — Débit rapporté à la charge
9. **d_t_out** — Variation horaire sortie
10. **d_conc** — Variation horaire titre
11. **t_out_local_z** — Sortie acide vs ses 24h
