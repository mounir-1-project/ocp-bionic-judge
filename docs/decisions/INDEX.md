# Décisions d'architecture

Chaque décision structurante du système est consignée ici : le problème posé,
les options écartées, et la raison du choix retenu. Un lecteur qui conteste une
orientation doit pouvoir trouver en une page pourquoi elle a été prise.

| # | Décision | Portée |
|---|---|---|
| [ADR-001](ADR-001-indicateur-encrassement.md) | Le coefficient d'échange global comme indicateur d'encrassement | Cœur analytique |
| [ADR-002](ADR-002-temperature-eau-de-mer.md) | Climatologie de l'eau de mer comme référence externe | Physique |
| [ADR-003](ADR-003-detection-hybride.md) | Détection hybride : règles AMDEC + Isolation Forest | Détection |
| [ADR-004](ADR-004-controleur-de-coherence.md) | Contrôleur de cohérence déterministe plutôt que juge par modèle de langage | Gouvernance |
| [ADR-005](ADR-005-referentiel-gouverne.md) | Référentiel métier en YAML, hors du code | Domaine |
| [ADR-006](ADR-006-poste-local-hors-ligne.md) | Poste local hors ligne, sans dépendance réseau | Exploitation |
| [ADR-007](ADR-007-identification-technicien.md) | Compte individuel par technicien et routage des alertes | Sécurité |
| [ADR-008](ADR-008-interface-isa-101.md) | Interface conforme aux principes ISA-101 | Interface |
| [ADR-009](ADR-009-periode-de-reference-commune.md) | Une période de référence unique pour les trois références | Cœur analytique |
| [ADR-010](ADR-010-deux-horizons-pour-une-action.md) | Séparer le délai de qualification de la fenêtre d'exécution | Exploitation |
| [ADR-011](ADR-011-langue-et-provenance-a-l-ecran.md) | La langue et la provenance sont des exigences, pas de la finition | Interface |
