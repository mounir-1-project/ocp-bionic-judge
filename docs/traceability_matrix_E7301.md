# Matrice de traçabilité documentaire E7301

Version 1.2 — confrontée au référentiel le 2026-08-07

| Information | Nature | Source et emplacement | Utilisation |
|---|---|---|---|
| Identité S-PC-E7301, constructeur, size, dates | source OCP | Fiche équipement, feuille principale | `tags.yaml/equipment` |
| Représentation horizontale, couvercles et plaque tubulaire | source OCP visuelle | Identification sous-ensemble, feuilles et médias embarqués ; Gamme PV page 1 | schéma 3D conceptuel |
| Lignes AMDEC officielles | source OCP | `4-AMDEC...xlsx`, feuille `AMDEC FOUR A SOUFRE`, lignes 9-24 | `amdec.yaml`, catégorie `ocp_source` |
| Séparation faisceau fuite/bouchage | règle dérivée | ligne source combinée 9-11 | `derived_rule`, validation OCP requise |
| Corrosion comme mode autonome | hypothèse/règle dérivée | corrosion est une cause aux lignes 9-11 | `derived_rule`, non présentée comme ligne officielle |
| `CAPTEUR_DEFAILLANT` F6/G6/N3/C108 | règle applicative | qualité observée dans DATA ; aucune ligne AMDEC | `application_rule`, cotation proposée |
| Périodicités A-H | source OCP | Plan préventif, feuille `Plan Maintenance Préventive` | `amdec.yaml/plan_maintenance` |
| Inspection externe/interne | source OCP | Check-list inspection, deux feuilles | templates `/api/workflows/templates` |
| Consignation, pression 0 bar, EPI, palan, couvercles | source OCP | Gamme PV page 1, phases 10-120 | barrières HSE du workflow interne |
| Tamponnage et critère 30 % | source OCP | Gamme tamponnage ; plan préventif H | workflow tamponnage ; total de tubes non inventé |
| 12 séries DCS et période | source | DATA.xlsx, Feuil1, B1:M10183 | ingestion et dictionnaire |
| Tags, sens et unités | établi par recoupement | nomenclature ISA-5.1, physique du procédé, comportement des données, climatologie | `tags.yaml`, champ `basis` — au moins deux bases indépendantes par tag, preuve publiée |
| Duty, résidus, z-scores | calcul | code versionné `src/features/` | indicateurs comportementaux |
| Score Isolation Forest | calcul non supervisé | `src/models/` et manifeste candidat | suspicion d'écart, jamais panne confirmée |
| Valeur économique | **retirée du périmètre** | aucune source, aucun fichier | aucun montant n'est produit ; deux tests interdisent le retour d'un endpoint économique et de la chaîne « MAD » |

L'empreinte SHA-256 de l'export DCS est publiée par `tags.yaml`
(`governance_defaults.source_sha256`) et recalculée à chaque exécution par
`generate_project_metrics.py`, qui la compare au manifeste du modèle. Un
document d'empreintes séparé avait été annoncé ici ; il n'a jamais été produit,
et l'artefact vérifié à chaque passage vaut mieux qu'un relevé figé.

