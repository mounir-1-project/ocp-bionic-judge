# ADR-006 — Poste local hors ligne

**Statut** : accepté
**Portée** : exploitation

---

## Problème

Un poste de surveillance destiné à une salle de contrôle d'atelier chimique ne
peut pas dépendre d'un accès Internet, ni d'un service tiers, ni d'une clé API.

## Décision

Le service est **intégralement autonome**. Une seule commande le démarre, et
il sert lui-même son interface :

```
python -m api
```

Cette forme **honore `API_HOST` et `API_PORT`**. Ce document écrivait
`uvicorn api.main:app --port 8000`, c'est-à-dire l'une des sources de vérité
concurrentes que `api/__main__.py` a été écrit pour supprimer.

- Aucune étape de compilation, aucun gestionnaire de paquets JavaScript.
- Le moteur 3D, la bibliothèque de graphiques et les polices sont embarqués.
- La carte d'environnement du rendu 3D est **générée en mémoire** au démarrage,
  pas téléchargée.
- Aucune requête sortante à l'exécution **en configuration par défaut**.

Une politique de sécurité de contenu stricte (`default-src 'self'`) est servie
avec chaque réponse, ce qui rend une régression sur ce point immédiatement
visible.

## Persistance

SQLite pour le registre d'alarmes et les interventions. Le système surveille
**un** équipement sur un historique fini : un serveur de base de données
n'apporterait rien et masquerait la logique métier derrière de la plomberie.

## Modèle de langage

Optionnel, et le système est complet sans lui. Renseigner une clé active
uniquement la couche de rédaction, dans un corridor borné. Aucune décision,
aucun seuil, aucun verdict n'en dépend.

## Conséquences

Le poste fonctionne sur un réseau industriel isolé. La contrepartie est que la
mise à jour des actifs embarqués est manuelle ; leur provenance et leur licence
sont documentées dans `api/static/ASSET_SOURCES.md`.
