# Dictionnaire gouverné des tags E7301

Version 1.1 — confronté au référentiel le 2026-08-07

Source commune : `DATA.xlsx`, feuille `Feuil1`, en-têtes `B1:M1`, données
`2:10183`, SHA-256
`93487c581f4cd684e8783251e91f15274d8ca4e3a0ae1eb332370039a5520239`.
Pas nominal : 1 h.

**LA COLONNE « STATUT » A ÉTÉ REMPLACÉE.** Elle publiait `inferred` et
`unknown`, avec la règle « aucun tag `inferred` ou `unknown` n'est déclaré
confirmé ». **Ce vocabulaire n'existe plus** : `confirmed`, `inferred` et
`unknown` apparaissent **zéro fois** dans `src/domain/tags.yaml`. Le référentiel
porte désormais un champ `basis` — la liste des bases indépendantes ayant servi
à établir le sens du tag — et c'est lui qui est publié ici, tag par tag.

Le principe qu'énonçait l'ancienne phrase reste vrai et se dit mieux : **aucune
interprétation n'est confirmée par OCP**, toutes sont établies par recoupement
d'au moins deux bases, et chacune reste contestable ligne à ligne.

| Tag DCS | Alias | Unité | Rôle | Bases de détermination |
|---|---|---:|---|---|
| `S_MC_SULF_TI1100_B` | `T_ACID_IN` | °C | périmètre | ISA-5.1, procédé, données |
| `S_MC_SULF_TI1105_B` | `T_ACID_OUT` | °C | périmètre | ISA-5.1, procédé, données |
| `S_MC_SULF_FI1300_B` | `F_ACID` | m³/h | périmètre | ISA-5.1, procédé, données |
| `S_MC_SULF_AI1100_B` | `C_ACID_1100` | % | périmètre | ISA-5.1, procédé, données |
| `S_MC_SULF_AI1200_B` | `C_ACID_1200` | % | périmètre | ISA-5.1, procédé, données |
| `S_MC_SULF_TI1300_B` | `T_CIRC_1300` | °C | secondaire | ISA-5.1, procédé, données |
| `S_MC_SULF_023_B` | `LOAD_SULFUR` | t/h | contexte | ISA-5.1, procédé, données |
| `S_MC_SULF_FI3412_B` | `F_3412` | m³/h | contexte | ISA-5.1, procédé, données |
| `S_MC_SULF_AI3301_B` | `A_3301` | - | contexte | ISA-5.1, données |
| `S_MC_SULF_AI3302_B` | `A_3302` | - | contexte | ISA-5.1, données |
| `S_MC_SULF_PHI5306X-3_B` | `PHI_5306` | - | **déclaré défaillant** | ISA-5.1, données |
| `S_MC_SULF_TI5303-4X_B` | `TI_5303` | °C | **déclaré défaillant** | ISA-5.1, données |

Les descriptions, plages physiques, seuils, justifications détaillées, règles
de qualité et historique de changement sont versionnés dans
`src/domain/tags.yaml` et exposés par `/api/equipment`.

Règles communes :

- conserver les codes qualité DCS et leur horodatage ;
- tracer les deux timestamps dupliqués avant de conserver la dernière ligne
  dans l'ordre source ;
- détecter trous temporels, désordre, absence, saturation, gel et hors-plage ;
- séparer `RUNNING`, arrêt et transition avant toute lecture de performance ;
- ne jamais pratiquer d'imputation globale ou cachée ;
- ne pas utiliser les deux tags dégradés comme variables du modèle ;
- traiter les unités comme métadonnées à confirmer : l'export ne fournit pas
  un historique d'unité permettant de prouver l'absence de changement.

