# Vérification — Contrôle de cohérence

Ce dossier contient le Judge Agent qui vérifie la cohérence des diagnostics.

## Fichiers

| Fichier | Rôle |
|---------|------|
| `judge_agent.py` | 8 contrôles déterministes + rédaction LLM optionnelle |

## Les 8 contrôles

| Contrôle | Poids | Question |
|----------|-------|----------|
| V1 | 22% | Les valeurs citées sont-elles exactes ? |
| V2 | 16% | La sévérité correspond-elle aux faits ? |
| V3 | 14% | Les modes AMDEC existent-ils et sont-ils détectables ? |
| V4 | 14% | L'action est-elle proportionnée et exécutable ? |
| V5 | 15% | La confiance est-elle calibrée ? |
| V6 | 8% | L'état de marche est-il respecté ? |
| V7 | 5% | Le fait le plus grave est-il traité ? |
| V8 | 6% | Les limites sont-elles énoncées ? |

## Principe

Le Judge recalcule les faits depuis les données brutes, puis confronte chaque affirmation de l'agent à ces faits. Il ne demande jamais son avis au LLM sur un point vérifiable.
