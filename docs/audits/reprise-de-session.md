# Reprise de session — lecture intégrale du dépôt E7301

Ce document permet à une nouvelle session de reprendre le travail **sans rien
redécouvrir**. Il dit ce qui a été lu, ce qui reste, ce qui a été trouvé, la
méthode à tenir, et les erreurs à ne pas refaire.

Le document de fond est **`docs/audits/analyse-architecture.md`** : il porte les
constats détaillés avec leurs preuves. Celui-ci en est la carte.

---

## 1. Mandat

L'utilisateur (Mounir Sanbouli, stage OCP, refroidisseur d'acide E7301) veut
sortir de cette phase avec un projet **propre et présentable** :

1. fichiers et dossiers bien structurés, aucun fichier superflu ;
2. rapport cohérent avec le projet réel — quitte à le supprimer et le refaire ;
3. **chaque page de l'interface fonctionne**, back-end comme front-end.

Il a demandé une **lecture intégrale du dépôt, fichier par fichier, sans rien
oublier**, avant tout plan de réorganisation. Le projet est passé par plusieurs
IA successives ; il soupçonne que cela l'a désordonné.

**Le plan de réorganisation n'est pas encore rédigé.** Il doit découler de la
lecture.

---

## 2. État de la lecture — ≈ 31 500 lignes sur ≈ 32 000

### Lu intégralement

| Ensemble | Fichiers | Lignes |
|---|---|---|
| `src/` Python | **39 / 39** | 12 077 |
| `src/domain/topology.yaml` | 1 | 264 |
| `api/` Python | 3 / 3 | 1 712 |
| `api/dashboard.html` | 1 | 545 |
| `api/static/app.js`, `app.css`, `twin.js` | 3 | 5 418 |
| `tests/` — lus verbatim | 13 / 41 | ~3 700 |
| `tests/` — analysés par AST (272 fonctions, 687 assertions) | 41 / 41 | — |
| `docs/` — `INDEX.md`, `traceability_matrix`, `data_dictionary` | 3 / 17 | 84 |
| Racine — `Makefile`, `pyproject.toml`, `.env` (noms seuls) | — | — |

**Fichiers `src/` sans aucun défaut trouvé** : `auth.py`, `formatting.py`,
`lineage.py`, `model_validation.py`, `fouling_injection.py`, `sensitivity.py`.

### Reste à lire

| Fichier | Lignes | Pourquoi c'est important |
|---|---|---|
| `docs/rapport_technique.md` | **894** | conditionne D1 ; contient les chiffres à réaligner |
| `README.md` | ? | conditionne D2 |
| `docs/decisions/ADR-001` à `ADR-011` | ~830 | **plusieurs ADR affirment des garanties non tenues** — voir §5 |
| `docs/architecture.md` | 156 | conditionne toute décision de structure |
| `docs/runbooks/runbook-operations.md` | 219 | procédures d'exploitation |
| `src/domain/amdec.yaml` | 532 | référentiel métier — décisif |
| `src/domain/tags.yaml` | 364 | référentiel métier — décisif |
| `notebooks/01_analyse_E7301.ipynb` | 556 | jamais inspecté |
| `scripts/` — 12 fichiers | ~1 900 | dont 4 orphelins (A2) |
| `tests/` — 28 fichiers restants | ~1 900 | confirmations attendues |
| `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml` | ~200 | conditionne E1/E2 |

**Priorité recommandée** : `amdec.yaml` + `tags.yaml` → les 11 ADR →
`rapport_technique.md` → `README.md` → `architecture.md` → le reste.

---

## 3. Les constats — 69 numérotés

Détail complet et preuves dans `docs/audits/analyse-architecture.md`.

### Les cinq constats structurants

| # | Constat | Gravité |
|---|---|---|
| **B1** | `alarms.py` (517 l.) et `workflows.py` (326 l.), testés, exposés sur 6 routes, **n'ont aucune interface**. Le rapport l. 789 annonce pourtant « le cycle de vie des alarmes et les gammes de maintenance ». | haute |
| **API-2** | `/api/timeseries` **n'expose pas** `ua_kw_per_k`, `ua_expected`, `ua_residual_trend_14d`, `fouling_resistance`, `t_in_residual_z` — mais expose `duty_kw`/`duty_expected` et l'effort de régulation. L'exploitant peut tracer l'indicateur **sans valeur de preuve** et **pas** celui qui porte le diagnostic. Le menu « Signaux » intitule même cette paire « Performance observée / attendue ». | haute |
| **API-3** | `_workflow_templates()` code en dur 6 prérequis HSE et 8 étapes de tamponnage, alors que `amdec.yaml/gammes` les contient (7 prérequis). **Les deux listes ont déjà divergé** : le point manquant est « Débranchement du courant sur les anodes », composant de criticité 112. | haute |
| **AL-1** | `AlarmStore._key` utilise `findings[0]` — le premier **par ordre d'écriture des règles**, pas le plus grave. Sa *docstring* promet une « clé stable ». Le même défaut a été corrigé dans l'agent (`_priorite`) et **pas** ici. | haute |
| **T-1** | Les six paires de capteurs les plus proches (0,75 à 0,96 m) portent **deux ancres identiques** — le champ `anchor` censé éviter les recouvrements les garantit. C'est le défaut visible signalé par l'utilisateur. | haute |

### Les deux motifs récurrents — c'est le vrai diagnostic du dépôt

**Motif 1 — « corrigé à un endroit, pas à son jumeau » : 9 occurrences.**

| # | Où |
|---|---|
| 1 | `_MODE_BY_RESIDUAL` corrigé, `_MODE_BY_THRESHOLD` non (M-3) |
| 2 | `if capped is not None` corrigé l. 957, `if capped` resté l. 1239 (J-3) |
| 3 | chemin absolu corrigé dans `redaction.py`, source `dcs_loader.py:495` intacte (D-1) |
| 4 | `enqueue_governance` câblé, `enqueue_test` non (API-5) — **introduit par moi** |
| 5 | garde d'état terminal sur `update_step`, absent de `complete` (WF-1) |
| 6 | publication atomique dans `load()`, mutation en place ailleurs (SEC-1) |
| 7 | `src/formatting.nombre` dupliqué dans `redaction.py` (FMT-1) — **introduit par moi** |
| 8 | `sans_accents` dupliqué dans `tests/helpers.py` (FMT-2) |
| 9 | `_try_build_llm`/`_extract_json` dupliqués par import différé (J-4) |

**Parade déjà présente dans le dépôt** :
`test_la_borne_de_reference_est_definie_a_un_seul_endroit`
(`tests/test_features_detector.py`) interdit par AST toute réapparition d'un
littéral. **C'est le patron à généraliser.**

**Motif 2 — « garantie annoncée sans garde » : 8 occurrences, toutes corrigées
depuis**, mais qui expliquent la défiance à avoir envers toute affirmation
documentaire non vérifiée :

| # | Garantie annoncée | Où |
|---|---|---|
| 1 | `test_le_gain_ne_vient_pas_dune_baisse_de_frequence` | rapport technique |
| 2 | test sur les handlers de la boucle d'événements | `api/main.py` |
| 3 | équivalence prédicat / règle d'encrassement | `fouling_injection.py` |
| 4 | non-ciblage des mutations aveugles | `judge_eval.py` |
| 5 | absence de sur-confiance native | `detection_agent.py` |
| 6 | centralisation de `duree_pas` | **ADR-011** |
| 7 | alignement des trois périodes de référence | **ADR-009** |
| 8 | « la fraction est définie une fois » | **ADR-009** |

⚠️ **Deux des huit viennent des ADR.** Les onze ADR n'ont **pas encore été
lues** : elles sont la source la plus probable de nouvelles affirmations non
tenues. **À lire en priorité.**

### Autres constats notables

| # | Constat |
|---|---|
| **JE-1** | Généralisation mesurée du Judge : **10 % de réserves levées, 1,7 % sanctionnées, note 9,89/10** contre 9,91 pour une décision saine. L'interface l'affiche **en premier** (correct), mais `judge_eval_report.txt` — « destiné au mémoire et à la soutenance » — et le CSV **l'omettent**. Le rapport le dit qualitativement sans publier les chiffres. |
| **SEN** | La part d'heures déclarées en encrassement **varie de plusieurs dizaines de points** selon la seule fenêtre de référence. Le « zéro heure sur quatorze mois » est celui de la fenêtre à 40 %. **Aucun chiffre d'encrassement n'est publiable sans sa fenêtre.** Appliqué dans l'interface, **pas encore dans le rapport**. |
| **API-6** | `/api/alarms`, `/api/alarms/{id}/transition`, `/api/config`, `/api/auth/audit`, `/api/auth/refresh` : **zéro test HTTP**. Les gammes, elles, ont 9 tests. |
| **WF-4** | `BLOCKED`, `NOT_APPLICABLE`, `CANCELLED` : **jamais exercés par un test**. La correction la plus argumentée de `workflows.py` (« un blocage qui cesse de se voir est une régression de sécurité ») n'a aucun garde. |
| **DOC-2** | `traceability_matrix_E7301.md` cite `economics.yaml` (**couche retirée**) et `reports/audit_initial_state_2026-07-25.md` (**inexistant**). |
| **C-2** | Le `.env` porte 5 variables mortes : `DATABASE_URL`, `MLFLOW_TRACKING_URI`, `API_SECRET_KEY`, `JWT_SECRET`, `COOKIE_SECURE`. Aucun `.env.example` n'existe. |
| **A-1** | `_quote_measurements` produit « entree acide 94.20 degC » — sans accents, point décimal anglais — dans le **diagnostic nominal**, le texte le plus souvent affiché. |
| **J-2** | 5 des 8 libellés de contrôle du Judge sont sans accents. Le test **les inspecte** ; son lexique de 44 mots ne contient pas `citees`, `reelles`, `invoques`, `fondes`, `calibree`, `traite`, `enoncees`. |
| **TOPO-1** | `tests/test_topology.py:84` utilise `Path("src/models/detector.py")` — **seul chemin relatif de la suite**, dépendant du répertoire courant. |
| **CI-1** | `mypy` déclaré, installé, cible `make types` présente, **absent de la CI**. |
| **DOC-1** | Le pire mois de signalement est chiffré « 40 % » dans `kpi.py` et « 20 % » dans `test_api.py`. |
| **KPI-1**, **LIN-1**, **WF-2**, **J-5** | Quatre énumérations dont une valeur n'est **jamais produite** : `derived`, `validated_offline`/`rejected`, `CANCELLED`, `uncertainty_level`. |
| **A-2** | Le coupe-circuit LLM ne distingue pas une panne de service d'une réponse mal formée : une seule réponse invalide désactive le LLM pour tout le processus. |
| **API-1** | 11 routes sur 45 exemptées du contrôle de session par préfixe, dont `/api/auth/audit`. |
| **API-4** | `alarm_transition` attribue le rôle `"administrator"` quand l'accès protégé est désactivé. |
| **SEN-1** | Le rapport de sensibilité n'est **persisté dans aucun artefact** de `reports/`. |
| **A1** | `docs/DATA.xlsx` est un duplicat MD5-identique de `data/raw/DATA.xlsx` (1,4 Mo de données OCP réelles). `rapport/` à la racine est un projet distinct. `update_report_docx.py` (359 l.) est mort. |

### Colonnes calculées et jamais consommées

`duty_per_load`, `approach_ratio`, `t_in_expected`, `fouling_resistance_trend_14d`
— calculées sur 10 180 lignes à chaque construction de features.

### Surfaces publiques mortes

`bareme_gravite`, `bareme_frequence`, `bareme_detection`, `criticality_link`,
`components_for_mode()`, `gammes`, `process_states` (K-1) ;
`Check.issue_code`, `JudgeVerdict.validation_scope` ;
`ntu_de()`, `EFFECTIVENESS_MAX` ; `WORKFLOW_STATES` (WF-3).

---

## 4. Ce qui est **solide** — à ne pas casser

Le noyau scientifique est de très bonne qualité. À ne pas « nettoyer » par
inadvertance :

- **L'auto-réfutation de `e7301_features.py`** : R² 0,968 contre 0,962 sans
  apprentissage, gain réel 0,006, corr(résidu, écart de consigne) = −0,94. Le
  résidu de duty a été renommé `regulation_effort` en conséquence.
- **L'aveu de `thermal.py`** : UA est un **UA apparent** = état de la surface ×
  action de la boucle froide. D'où la publication de l'**avancement à la
  détection** plutôt que d'un taux.
- **`sensitivity.py`** : « aucun chiffre d'encrassement n'est publiable sans la
  fenêtre qui l'a produit […] publié ici **pour être contesté, pas pour être
  cru** ».
- **`model_validation.py`** : les portes recalculent le résumé du manifeste et
  le comparent — un manifeste édité à la main est rejeté. Quatre portes sur
  cinq échouent, et c'est publié.
- **`replay.py`** : l'unique instant critique de 14 mois était en position
  6 610, non multiple de `analyze_every=3`, donc **jamais analysé**.
- **`auth.py`** : la tentative est comptée **avant** la dérivation PBKDF2 — sans
  quoi la limite de 5 essais était contournable en parallélisant.
- **Les tests qui verrouillent des retraits** : `/api/business/*` doit renvoyer
  404, `"MAD"` absent du HTML, `includes("FAISCEAU")` interdit dans `app.js`,
  `severities=1,2,3` refusé.

---

## 5. Méthode à tenir

1. **Lire les fichiers entièrement.** L'utilisateur l'a redemandé trois fois.
2. **Consigner au fil de l'eau** dans `docs/audits/analyse-architecture.md` —
   ne pas dépendre de la mémoire de session.
3. **Aucun grep n'établit une absence.** Suivre la donnée jusqu'à son point de
   rendu : les champs sont **renommés en transit**
   (`flagged_issues` → `judge_issues`, `blind_mutations` → `benchMeta`).
4. **Prouver par mutation** toute correction : réintroduire le défaut, vérifier
   que le test échoue, restaurer.
5. **Ne pas réimplémenter pour tester.** J'ai commis cette faute dans
   `twin_smoke.mjs` : le banc validait ma copie, pas `_loop`.
6. **Se corriger explicitement** quand on s'est trompé.

### Mes six erreurs d'analyse, déjà corrigées dans le document

| Ce que j'avais conclu | Réalité |
|---|---|
| « 46 routes contre 45 annoncées » | 47 décorateurs, 46 `/api/`, **45 chemins distincts** — les trois chiffres sont justes |
| « le contrôleur est muet à l'écran » (J-1) | note, accord et **réserves traduites** sont affichés |
| « le chiffre honnête est masqué partout » (JE-1) | l'interface l'affiche **en premier**, seuls les exports l'omettent |
| « le corpus typographique ne couvre pas le Judge » (J-2) | il le couvre ; c'est le **lexique** qui est trop court |
| « aucun test creux dans la suite » | **quatre** documentés : `json.dumps` sans assertion, conjugaison verrouillée, `0 <= taux <= 1`, `_exiger` sur corpus vide |
| « `IndexError` garanti » sur `_destinataires()[0]` | `enabled` le garde ; le défaut réel est une **fenêtre de course** |

---

## 6. Travail en cours et non commité

**Rien n'est commité.** `git status` : 16 fichiers modifiés, 2 non suivis.

Modifications faites pendant cette mission :

| Fichier | Changement |
|---|---|
| `api/static/twin.js` | correctif de la coupe ; vue éclatée ; extraction de `animerEclats(dt)` |
| `scripts/twin_smoke.mjs` | banc rendu honnête (il réimplémentait l'animation) ; 35 contrôles |
| `api/static/app.js` | arrêt de la scrutation à l'expiration de session ; `window.__twin` ; `setLink` défensif |
| `src/notifications/email.py` | `diagnostiquer_echec` ; `_premier_destinataire` ; alerte critique tracée sans destinataire ; corps accentué |
| `src/notifications/redaction.py` | **nouveau** — rapport de gouvernance rédigé (remplace `json.dumps`) |
| `api/main.py` | branchement de `rediger_gouvernance` ; `demandeur` |
| `tests/test_access_notifications.py` | 4 tests ajoutés |
| `tests/test_redaction_gouvernance.py` | **nouveau** — 6 tests |
| `docs/audits/analyse-architecture.md` | **nouveau** — le document d'analyse |
| Artefacts | `models/`, `reports/`, `notebooks/`, `requirements-runtime.lock` régénérés |

**Deux défauts que j'ai introduits et qui restent à corriger** : API-5
(`enqueue_test` non câblé) et FMT-1 (`redaction.py` duplique
`src/formatting`).

---

## 7. Tâches ouvertes

| # | Tâche | État |
|---|---|---|
| A1 | Assainir la racine et `docs/` | en attente |
| A2 | Documenter ou supprimer les scripts orphelins | en attente |
| B1 | **Trancher le sort des alarmes et des gammes** | **bloquant** — l'utilisateur a demandé de ne rien décider avant le plan exact |
| B2 | Construire les pages manquantes | bloqué par B1 |
| C1 | Recette page par page des 3 vues | en attente |
| C2 | Réorganiser les capteurs du jumeau 3D | en attente — cause identifiée (T-1) |
| D1 | Réaligner le rapport technique | bloqué par B1 et E1 |
| D2 | Vérifier README et `docs/` | en attente — `test_documentation.py` couvre déjà le référentiel |
| E1 | Suite complète verte et artefacts régénérés | en attente |
| E2 | Commit, `.gitattributes`, dépôt **privé**, tag `v3.0.0` | bloqué par E1 |
| L0 | **Lecture intégrale** | **en cours — ≈ 98 %** |

### Ordre de travail retenu par l'utilisateur

**A (nettoyage) → C (recette) → E (livraison)**, puis B et D une fois
l'interface vue élément par élément.

---

## 8. Contraintes non négociables

- **Le dépôt distant doit être privé** : `data/raw/DATA.xlsx` contient 14 mois
  de données d'exploitation OCP réelles, et `docs/` versionne 11 Mo de
  documents internes OCP.
- **`data/runtime/operators.json`** contient des empreintes PBKDF2 et des
  adresses réelles — jamais versionné.
- **Deux clés Gemini** ont été collées en clair dans la conversation : elles
  sont **compromises** et doivent être révoquées. `GEMINI_API_KEY` figure
  encore dans le `.env`.
- **Ne jamais lancer `promote_model.py --par`** : 4 portes sur 5 échouent, dont
  deux définitivement (`labels_gmao`, `validation_externe`).
- L'utilisateur travaille sous **Windows PowerShell** — pas de `grep`, `wc`,
  `sed` dans les commandes qu'on lui donne.
- Il demande des **procédures complètes**, pas des commandes une par une, et
  que les décisions techniques soient **prises**, pas soumises à arbitrage.

---

## 9. État mesuré du projet

```
Tests            267 cas (262 fonctions) — chiffre du rapport, à réactualiser :
                 10 tests Python et 3 contrôles 3D ont été ajoutés
Couverture       87,15 %
Bancs frontend   51 + 35 + 9   (le rapport annonce 84, il en faut 95)
Routes API       45 chemins /api/ distincts
Modèle           statut « candidate » — 4 portes sur 5 en échec
Judge            95,8 % non-régression · 4,13 pts de séparation
                 10 % généralisation · 1,7 % sanction · 9,89/10
```

⚠️ `test_project_metrics.py` compare le rapport aux artefacts. Toute
modification de la suite impose la **boucle d'amorçage** documentée dans ce
fichier.

---

## 10. Prompt d'ouverture pour la nouvelle session

À coller tel quel comme premier message, le dossier `<racine du depot>`
étant ouvert.

---

> Tu as accès à mon projet. Avant toute chose, lis ces deux fichiers
> intégralement, dans cet ordre :
>
> 1. `docs/audits/reprise-de-session.md`
> 2. `docs/audits/analyse-architecture.md`
>
> Ils viennent d'une session précédente qui a lu **environ 31 500 des 32 000
> lignes** de ce dépôt, fichier par fichier, et y a consigné **69 constats
> numérotés avec leurs preuves mesurées**. Ne recommence pas ce travail : il
> est fait et il est traçable.
>
> Le contexte en deux phrases : je suis Mounir, stagiaire chez OCP, et ce dépôt
> est mon système de surveillance du refroidisseur d'acide de séchage E7301
> (atelier PS III, Maroc Chimie). Il est passé par plusieurs IA successives et
> s'est désordonné.
>
> Ce que je veux en sortir : un projet **propre et présentable**. Structure de
> fichiers saine, aucun fichier superflu, rapport cohérent avec le système
> réel, et **chaque page de l'interface qui fonctionne vraiment** — back-end
> comme front-end.
>
> **Ta première tâche : terminer la lecture du dépôt.** Le paragraphe 2 de la
> reprise te dit exactement ce qui reste et dans quel ordre. Commence par
> `src/domain/amdec.yaml` et `src/domain/tags.yaml` — c'est le référentiel
> métier, il conditionne toute décision de structure. Puis les **11 ADR** de
> `docs/decisions/` : deux d'entre elles ont déjà été prises en défaut, elles
> affirmaient des garanties qui n'existaient pas. Puis
> `docs/rapport_technique.md`, `README.md`, `docs/architecture.md`, le runbook,
> le notebook, les 12 scripts et les 28 fichiers de tests restants.
>
> Tiens la méthode du paragraphe 5, elle a été payante :
>
> - lis chaque fichier **en entier**, pas par extraits ;
> - consigne chaque constat dans `analyse-architecture.md` **au fil de la
>   lecture**, pas à la fin ;
> - **aucun `grep` n'établit une absence** — suis la donnée jusqu'à son point
>   de rendu, les champs sont renommés en transit dans ce projet ;
> - prouve toute correction **par mutation** : réintroduis le défaut, vérifie
>   que le test échoue, restaure ;
> - **corrige-toi explicitement** quand tu t'es trompé. La session précédente
>   s'est corrigée six fois, c'est consigné, et c'est ce qui rend le document
>   utilisable.
>
> Travaille par lots, en me disant à chaque fois ce que tu as lu et ce que tu
> as trouvé. Je te répondrai « continue ».
>
> **Quand la lecture sera complète, rédige le plan de réorganisation** — et
> seulement à ce moment-là. Il doit découler des constats, pas d'impressions.
> Deux décisions m'attendent : le sort des alarmes et des gammes de maintenance
> (constat **B1** — 849 lignes de code testé, six routes API, **aucune
> interface**, alors que mon rapport les annonce), et la correction du motif de
> duplication à neuf occurrences, pour lequel le dépôt contient déjà la parade.
>
> **Ne commence aucune correction avant que je valide le plan.** Deux défauts
> ont été introduits par la session précédente et sont à reprendre : **API-5**
> et **FMT-1**, tous deux décrits dans le document.
>
> Deux choses à savoir tout de suite : le dépôt distant devra être **privé**
> (il contient 14 mois de données d'exploitation OCP réelles et 11 Mo de
> documents internes), et je travaille sous **Windows PowerShell** — donne-moi
> des commandes qui marchent chez moi, pas du `grep`/`sed`/`wc`.
