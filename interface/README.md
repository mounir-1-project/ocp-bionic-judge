# Interface — Dashboard web

Ce dossier contient l'interface web du système de surveillance.

## Fichiers

| Fichier | Rôle |
|---------|------|
| `main.py` | Serveur FastAPI (API REST + dashboard) |
| `__main__.py` | Point d'entrée (`python -m interface`) |
| `dashboard.html` | Page HTML du dashboard |
| `static/` | Assets statiques (JS, CSS, images) |

## Structure du dashboard

### Onglet I — Salle
- Modèle 3D interactif du refroidisseur
- Timeline avec épisodes d'anomalie
- Diagnostics en temps réel
- 10 signaux disponibles

### Onglet II — Intégrité
- KPIs opérationnels
- Tableau des alarmes ISA-18.2
- Templates d'interventions
- Plan préventif A-H
- Tableau AMDEC

### Onglet III — Contrôle
- 8 contrôles du Judge
- Taux de signalement
- Couverture AMDEC
- Notifications email
- Angles morts

## Lancement

```bash
python -m interface
# ou
python interface/main.py
```

Puis ouvrir http://localhost:8000
