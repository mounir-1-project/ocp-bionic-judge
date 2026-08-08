# Objectifs finaux — à ne pas clore avant

**Écrit dans le dépôt, pas dans une mémoire de session** : ce document survit à
toute interruption. Toute session qui reprend ce travail le lit en premier, avec
la fin de `analyse-architecture.md`.

Demande explicite du propriétaire, 7 août 2026 :

> « fait dans ta mémoire qu'on aura besoin de faire un rapport et des notebooks
> d'explications ; la session ne doit pas se terminer avant ceci. Continue la
> correction du projet, je le veux clean pour avoir un rapport qui parle de
> lui-même et des notebooks qui l'expliquent pour mon propre apprentissage. »

---

## F1 — Le rapport doit parler de lui-même

`docs/rapport_technique.md` (996 l.) a été **lu intégralement** (S26) et corrigé
sur cinq points. Il reste :

1. **Écrire le chapitre absent sur la validation** (S25-2). Le document est
   **entièrement muet** sur les sept portes de déploiement, le backtest à quatre
   plis et l'analyse de dérive — alors que le poste affiche « 3 / 7 portes
   franchies » et que `validate_release.py` en fait son code de retour. Ce n'est
   pas une réécriture, c'est un ajout, et il porte ce que le projet a de plus
   défendable : **la promotion est refusée, pour deux raisons nommées.**
2. **Régénérer `project_metrics.json`** puis confronter « 290 cas de test »
   (S25-3) — cette session a ajouté une douzaine de tests.
   Commande : `python scripts/generate_project_metrics.py`, avec la boucle
   d'amorçage que `test_project_metrics` documente sur dix-huit lignes.
3. **Élargir `test_aucun_chiffre_cle_ne_contredit_les_artefacts`** à chaque
   chiffre réécrit. Six termes y sont aujourd'hui ; le rapport en publie des
   dizaines.

## F4 — Des notebooks qui expliquent, pour l'apprentissage

`notebooks/01_analyse_E7301.ipynb` — 29 cellules, 325 lignes, **aucune sortie
enregistrée**. Il n'a pas été lu par cet audit.

Objectif du propriétaire : **comprendre son propre projet**, pas seulement le
livrer. Un notebook d'analyse ne suffit pas ; il faut une progression qui
explique **pourquoi** chaque décision a été prise.

Découpage proposé, à confirmer avec lui :

| # | Sujet | Ce qu'il doit faire comprendre |
|---|---|---|
| 01 | La donnée et ses défauts | pourquoi la qualité de donnée est une information, et non un déchet |
| 02 | **La variable régulée** | pourquoi l'encrassement ne se lit pas sur la sortie acide — le cœur du sujet |
| 03 | **La circularité du duty** | l'erreur algébrique d'ADR-001, refaite pas à pas : R² 0,968 contre 0,962 sans apprentissage |
| 04 | **UA et l'eau de mer** | efficacité-NTU, climatologie de Safi, et pourquoi c'est un UA *apparent* |
| 05 | La détection hybride | règles AMDEC + Isolation Forest, occlusion exacte |
| 06 | Le contrôleur et son banc | pourquoi un taux d'accord ne prouve rien, et ce que mesure la généralisation |
| 07 | Les paramètres arbitraires | 61 points d'écart selon la fenêtre de référence |

Contraintes tirées de l'audit :

- **chaque chiffre affiché doit venir d'un artefact**, jamais d'une saisie —
  sinon le notebook devient une neuvième source de vérité à maintenir ;
- `make notebook-clean` retire les sorties avant commit : les notebooks ne
  doivent pas versionner leurs figures ;
- la typographie française s'applique (`src.formatting`), et
  `test_documentation.py` balaie déjà les notebooks pour les tests cités.

## F2 — L'interface, ce qui reste

- **cinq routes d'intervention sans écran** (S15-1) : `POST /api/workflows`,
  `PATCH .../steps/{id}`, `POST .../complete`, et les deux lectures ;
- `/api/auth/audit` sans chemin documenté — **à brancher, pas à retirer** ;
- `/api/notable` sans lecteur ;
- rôle sur les trois bancs de gouvernance non protégés (S15-4, décision
  d'habilitation) ;
- la prise de quart déclarative ne trace rien (S23-3).

## F3 — Propreté, en dernier

Arborescence, `.gitignore`, `requirements.txt`, `Makefile`. Puis, seulement
alors : dépôt distant **privé** — ou pas de dépôt distant, décision prise le
7 août.

## Décisions ouvertes, à trancher par le propriétaire

| # | Question |
|---|---|
| S34-4 | `stoichio` est déclaré et utilisé par aucun tag. L'inscrire au `basis` de `LOAD_SULFUR` — dont le rapport § 2.2 fait l'argument — ou le retirer du `Literal` ? Le verrou s'écrit une ligne après (S37-2). |
| S33-1 | Faut-il plafonner `ACTION_OVERSIZED` ? Aucun plafond aujourd'hui ; l'ADR en annonçait un. |
| AL-3 | Une alarme dont la condition cesse ne se résout jamais et ne peut pas être close. Trois arbitrages de sécurité (S22-3). |
| S38-3 | Le `or` de `test_la_detection_est_tardive` neutralise le test si la détection devient parfaite. |
| — | Révoquer les deux clés Gemini, ou vérifier qu'aucune facturation n'est attachée. |

## État de la lecture au 7 août 2026

**Terminé** : tout `src/`, `api/`, `scripts/` ; tout le corpus documentaire
(rapport, README, architecture, onze ADR, runbook, dictionnaire, matrice) ;
`dashboard.html` ; huit fichiers de tests.

**Reste** : `api/static/twin.js` (2 167 l.), neuf fichiers de tests — dont
`test_api.py` (1 043) et `test_features_detector.py` (860) —, et le notebook.


---

# ÉTAT AU 7 AOÛT 2026 — REPRISE EN SESSION NEUVE

Écrit dans le dépôt, et non gardé en mémoire de session : c'est le seul endroit
qui survit à une interruption. Une session neuve peut repartir d'ici sans rien
me demander.

## Ce qui reste à lire intégralement

| fichier | lignes | remarque |
|---|---|---|
| `api/static/twin.js` | 2 167 | session dédiée, comme `app.js` |
| `tests/test_api.py` | 1 043 | session dédiée |
| `tests/test_features_detector.py` | 860 | session dédiée |
| `tests/test_service_invariants.py` | 388 | tient dans un lot |
| `tests/test_operator_registry.py` | 371 | tient dans un lot |

Tout le reste du dépôt — sources, documentation, ADR, notebook — a été lu ligne
à ligne sur les lots S1 à S44.

## Décisions en attente de l'auteur (je ne les prends pas)

| réf | question |
|---|---|
| AL-3 | une alarme dont la condition cesse sans réémission ne se résout jamais et ne peut être close |
| AL-4 | le chemin nominal doit-il désigner une dominante, ou laisser le registre retomber sur l'ordre des règles ? |
| SEC-3 | consigner la fin de session (déconnexion, expiration, rotation) au journal d'audit ? |
| DOM-1 | base `stoichio` déclarée, utilisée par zéro tag (verrou : `test_domain.py:25`) |
| ALM-2 | plafonner `ACTION_OVERSIZED` ? |
| FI-1 | le `or` de `test_la_detection_est_tardive` |
| OPS-1 | vérifier la facturation Gemini (clés non révoquées, à votre demande) |

## Priorité 1 — le rapport (F1)

Le chapitre **absent** : les 7 portes de déploiement et le backtest à 4 plis. Le
poste affiche « 3 / 7 portes franchies » ; les 996 lignes du rapport n'en disent
pas un mot, et le mot « PSI » n'y figure pas une fois. C'est le document que le
jury lit.

Matière déjà mesurée et disponible dans le journal :

- pourquoi PSI 3,18 ne mesure pas une dérive mais la couverture saisonnière des
  plis (correspondance monotone 73,8 / 100 / 5,9 / 0 % → 1,989 / 3,745 / 0,580 / 0,068) ;
- pourquoi deux portes sont **publiées, en échec, et non bloquantes** — aucun
  commit ne peut les franchir (ADR-001 pour l'une, S21-3 pour l'autre) ;
- pourquoi la généralisation est 8,6 % et non 95,8 %.

Puis : régénérer `project_metrics.json`, confronter le « 290 cas de test »
affiché, et élargir `test_aucun_chiffre_cle_ne_contredit_les_artefacts`.

## Priorité 2 — les notebooks (F4)

Sept notebooks proposés plus haut dans ce fichier. Les deux sujets les plus
difficiles et les plus utiles à votre apprentissage :

1. **pourquoi le résidu de duty est circulaire** — R² 0,968 appris contre 0,962
   sans apprentissage, corr(résidu, écart de consigne) = −0,94 — et pourquoi UA
   par efficacité-NTU est le seul indicateur qui tienne ;
2. **pourquoi un test vert ne prouve rien par lui-même** — les sept erreurs de
   l'audit, toutes trouvées par la lecture, aucune par l'exécution.

## Le motif à retenir pour le rapport

Sur 18+ occurrences relevées : *corrigé à un endroit, pas à son jumeau* — et
**toujours** le code servant porte la version juste, l'affichage ou le document
la version périmée. Ordre de fraîcheur constaté :
`code/artefacts → README → ADR → rapport_technique.md → architecture.md → notebook`.
Deux exceptions seulement (S27-2, S32-1).

C'est le fil conducteur naturel du rapport : il explique **pourquoi** la
gouvernance du dépôt est faite comme elle est.
