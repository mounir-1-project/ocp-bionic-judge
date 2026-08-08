# Analyse architecturale du dépôt — lecture fichier par fichier

Document de travail. Il consigne, au fil de la lecture, ce que **contient
réellement** chaque fichier, par opposition à ce que le dépôt prétend contenir.
Il sert de base factuelle au plan de réorganisation : aucune décision de
structure n'y est prise sans une observation datée qui la justifie.

Méthode : lecture intégrale, fichier par fichier. Chaque constat porte sa
preuve — un chemin, une ligne, une empreinte, une commande. Les constats sans
preuve sont marqués `À VÉRIFIER` et ne fondent aucune décision.

---

## 0. Périmètre mesuré

| Ensemble | Fichiers | Lignes |
|---|---|---|
| `src/` Python | 39 | 12 077 |
| `src/domain/` YAML | 3 | 1 160 |
| `api/` Python | 3 | 1 712 |
| `api/` front (html, css, js) | 4 | 5 963 |
| `tests/` | 41 | ~5 600 |
| `scripts/` | 12 | ~1 900 |
| `docs/` Markdown | 17 | 2 179 |
| `docs/` sources OCP (xls, xlsx, pdf) | 8 | binaire, ~11 Mo |
| `notebooks/` | 1 | 556 |
| `reports/`, `models/` | 10 | artefacts |

Total lu : **~32 000 lignes**.

---

## 1. Racine du dépôt

### 1.1 Pièces qui n'appartiennent pas au projet logiciel

| Pièce | Constat | Preuve |
|---|---|---|
| `rapport/` | Projet **distinct** de génération du rapport de stage : `chapitre_realisation.py`, `chapitres456.py`, `contenu.py`, `c16-16.png`, `__pycache__`. Non suivi par git. | `git ls-files rapport` → vide. Aucun import depuis `src/`, `api/`, `tests/`, `scripts/`. |
| `Rapport de stage … .docx` ×2 | Sorties du projet ci-dessus. | Référencés nulle part dans le code ni la doc. |
| `AUDIT_PROMPT.md` | Consigne d'audit, document de travail. | Cité uniquement par `AUDIT_ADVERSE_2026-07-28.md`. |
| `AUDIT_ADVERSE_2026-07-28.md` | Compte rendu d'audit. | Aucun code n'y renvoie. |

**Conséquence** : la racine mélange un livrable logiciel et un livrable
documentaire produit par une chaîne indépendante. Un lecteur ne peut pas
distinguer les deux.

### 1.2 Duplication de données réelles

`docs/DATA.xlsx` et `data/raw/DATA.xlsx` ont la **même empreinte MD5**
`586fc00278043c571afebdcb41efb97a`. Il s'agit de 1,4 Mo de données
d'exploitation OCP réelles, présentes deux fois.

- `data/raw/DATA.xlsx` est **suivi par git** et référencé par
  `config.DCS_EXPORT`.
- `docs/DATA.xlsx` n'est **suivi par personne** et **référencé nulle part**.

### 1.3 Confidentialité

Sont versionnés dans git :

| Fichier | Taille |
|---|---|
| `docs/2-Fiche Identifcation sous ensemble…xlsx` | 5,6 Mo |
| `docs/8-Gamme de tamponnage des tubes…xls` | 4,4 Mo |
| `data/raw/DATA.xlsx` | 1,4 Mo |
| `docs/7-Gamme PV Refroidisseur d'acide PS3.pdf` | 0,7 Mo |

Documents internes OCP et 14 mois de données d'exploitation.
**Le dépôt distant doit être privé. Ce n'est pas une préférence.**

Note : `2-Fiche Identifcation` porte une faute de frappe dans son nom
(« Identifcation »). Nom d'origine OCP — à conserver tel quel, la provenance
prime sur l'orthographe.

---

## 2. `src/config.py` — 413 lignes — **lu intégralement**

Rôle : point de vérité unique de la configuration. Charge `.env` une fois,
expose des constantes de module, valide au démarrage.

### Ce qui est solide

- `_env_bool` traite une variable **vide** comme absente. Le commentaire
  explique pourquoi : `docker compose` injecte `""` pour tout `${VAR:-}` non
  fourni, ce qui désactivait silencieusement l'accès protégé.
- `validate()` retourne une liste de problèmes plutôt que de lever : le service
  peut tous les afficher d'un coup au lieu du premier rencontré.
- `summary()` publie les chemins en **relatif** — un endpoint de diagnostic n'a
  pas à divulguer l'arborescence de l'hôte.
- Refus explicite de `CORS_ORIGINS=*` combiné à `allow_credentials=True`.
- `AUTH_ENABLED` s'active seule dès qu'un technicien est enregistré.

### Défauts constatés

| # | Constat | Gravité |
|---|---|---|
| C-1 | **`ALARM_DB` est défini (l. 87) mais absent de `summary()`**, alors que `WORKFLOW_DB` y figure. Asymétrie non justifiée : `/api/config` ne permet pas de diagnostiquer un mauvais montage de la base d'alarmes. | mineure |
| C-2 | **Le `.env` de l'utilisateur porte 5 variables mortes** : `DATABASE_URL`, `MLFLOW_TRACKING_URI`, `API_SECRET_KEY`, `JWT_SECRET`, `COOKIE_SECURE`. Aucune n'est lue par `config.py`. L'en-tête du module affirme pourtant en principe n°1 : « TOUTE VARIABLE DECLAREE EST UTILISEE ». | moyenne |

C-2 est exactement le résidu attendu d'un passage par plusieurs générateurs :
le code a été nettoyé, le `.env` ne l'a pas été. Il n'existe **aucun
`.env.example`** dans le dépôt pour faire autorité.

`AUTH_PROVIDER` vaut `local_demo` par défaut et la production exige `oidc`,
non intégré : le mode production est **volontairement et définitivement
bloqué**. C'est cohérent avec le statut `candidate` du modèle.

---

## 3. `src/pipeline.py` — 402 lignes — **lu intégralement**

Rôle : chaîne complète ingestion → features → détection → diagnostic →
jugement. Point d'entrée unique revendiqué pour API, rejeu, notebooks, tests.

### Ce qui est solide

- `_load_compatible_artifact()` ne charge un artefact que si le manifeste, les
  empreintes et le schéma de features concordent. Trois stratégies explicites
  (`auto`, `artifact`, `train`), chacune avec son motif de refus enregistré
  dans `model_rejection_reason`.
- Le message d'erreur de `MODEL_STRATEGY=artifact` **dit quoi faire** : quatre
  lignes d'actions concrètes.
- `notable_timestamps()` lit ses seuils depuis le référentiel, pas en dur. Le
  commentaire documente le défaut réparé : un seuil abandonné (`conc_spread >
  0.6`) survivait dans une copie locale.
- `validation_report()` mémorise son résultat — le backtest ne tourne qu'une
  fois par processus.

### Points d'attention

| # | Constat | Gravité |
|---|---|---|
| P-1 | `health_report()` expose `references` — les coefficients de régression complets. C'est la source du rapport de gouvernance de 300 lignes. Corrigé côté rédaction (`src/notifications/redaction.py` ne les imprime pas), mais l'API `/api/health/*` les publie toujours. | à trancher |
| P-2 | `import` local de `CONC_DROP_SUSPICIOUS` au milieu d'une méthode (l. 307), pour éviter un cycle. Fonctionne, mais signale un couplage `pipeline ↔ detector` qui mériterait d'être nommé. | mineure |

---

## 4. Modules `__init__.py`

Quatre paquets exposent une API publique explicite avec `__all__` :
`analytics`, `notifications`, `operations`, `security`.

Sept paquets ont un `__init__.py` **vide** : `agents`, `domain`, `features`,
`governance`, `ingest`, `models`, `realtime`, plus `src/` lui-même.

| # | Constat | Gravité |
|---|---|---|
| I-1 | Incohérence de convention : la moitié des paquets déclare sa surface publique, l'autre non. Les imports se font alors sur les chemins internes (`from src.models.detector import …`), ce qui fige la structure interne dans tous les appelants. | moyenne |

---

## 5. Interface — surface mesurée

3 vues : `salle`, `controle`, `integrite`.

**Décompte des routes — correction d'une erreur de ma part.** J'avais noté
« 46 routes, le rapport en annonce 45 ». Vérification faite, le rapport a
raison et je comptais mal :

| Mesure | Valeur |
|---|---|
| Décorateurs `@app.<verbe>` | 47 |
| dont chemins `/api/` | 46 |
| **chemins `/api/` distincts** | **45** |

Un même chemin porte deux verbes. `test_project_metrics.py` compare à un
**ensemble** de chemins, donc 45 — cohérent avec le rapport. Et les
« quarante-sept handlers » cités dans le commentaire de `main.py` désignent le
total des décorateurs : également exact. **Les trois chiffres sont justes, ils
ne comptent simplement pas la même chose.**

**15 routes sans aucun consommateur front** :

```
/api/alarms                          /api/health/live
/api/alarms/{alarm_id}/transition    /api/health/model
/api/auth/audit                      /api/health/ready
/api/auth/refresh                    /api/health/version
/api/config                          /api/notable
/api/health/database                 /api/workflows
/api/workflows/templates             /api/workflows/{workflow_id}
/api/workflows/{workflow_id}/complete
```

Toutes ne sont pas fautives : `/api/health/*` sont des sondes destinées à
Docker et à l'orchestrateur, leur absence du front est normale.

En revanche `alarms` et `workflows` couvrent **849 lignes de code testé**
(`src/operations/alarms.py` 517, `workflows.py` 326) exposées sur 6 routes,
sans la moindre page. Le rapport technique, ligne 789, annonce pourtant que
l'API couvre « le cycle de vie des alarmes et les gammes de maintenance ».

`grep -c` sur `api/static/app.js` et `api/dashboard.html` :
`alarms` → 0 et 0. `workflows` → 0 et 0. `notable` → 0 et 0.

---

## 6. Scripts — appartenance vérifiée

Référencés par le `Makefile` ou la CI :
`manage_operators.py`, `promote_model.py`, `validate_release.py`,
`dump_fixtures.py`, `frontend_smoke.mjs`, `twin_smoke.mjs`, `boot_smoke.mjs`.

| Script | Statut | Preuve |
|---|---|---|
| `update_report_docx.py` (359 l.) | **Mort.** Son propre en-tête le déclare hors service. | Zéro référence hors de lui-même. |
| `audit_corpus.py` (243 l.) | Orphelin. | Aucune référence. |
| `browser_smoke.mjs` | Orphelin. | Aucune référence hors de lui-même. |
| `make_contact_sheets.py` (56 l.) | Orphelin, mais cité dans `requirements.txt`. | Seule mention. |
| `generate_project_metrics.py` (138 l.) | **Vivant mais non déclaré** : indispensable à la boucle d'amorçage documentée dans `tests/test_project_metrics.py`, absent du `Makefile`. | — |

---

## 7. `src/domain/knowledge.py` — 848 lignes — **lu intégralement**

Rôle revendiqué : **seule** porte d'entrée vers `tags.yaml` et `amdec.yaml`.
Aucun seuil, aucun nom de tag, aucune criticité ne doit être codé en dur
ailleurs. Le module tient sa promesse.

### C'est le meilleur fichier du dépôt

Il documente ses propres défauts passés, avec le raisonnement :

- `seuil()` teste l'**absence**, pas la fausseté. L'idiome
  `tag.threshold(...) or <defaut>` remplaçait un seuil légitimement nul par le
  repli : un débit d'arrêt à 0 m³/h devenait 20 m³/h, silencieusement, **à
  douze endroits de la chaîne**.
- `observabilite` distingue `full`, `partial`, `none`. Avant,
  `bool("partial")` valait `True` : un mode déclaré *partiellement* observable
  était compté comme *entièrement* observable, et la couverture du risque AMDEC
  publiée s'en trouvait surévaluée.
- La validation de `observable` a été déplacée **au chargement**, pas au
  premier accès : une faute de saisie du référentiel arrête le démarrage au
  lieu de lever au fond d'une requête HTTP.
- `blind_spots()` avait **deux définitions concurrentes** dans la même classe.
- `task_requires_shutdown()` normalise les accents : un « Arrêt process »
  accentué dans le référentiel faisait passer une intervention sous
  consignation pour une intervention réalisable en marche.
- Deux méthodes mortes ont été supprimées, avec la raison consignée en
  commentaire (`is_out_of_physical_range`, `mode_for_indicator`).

### Surface publique morte

Chargée depuis les YAML, exposée en attribut, **jamais lue par personne** —
vérifié par recherche d'appels réels sur `src`, `api`, `tests`, `scripts` :

| Surface | Origine | Appels réels |
|---|---|---|
| `bareme_gravite`, `bareme_frequence`, `bareme_detection` | `amdec.yaml` (3 blocs) | **0** |
| `criticality_link` (propriété de `Tag`) | `tags.yaml` (5 tags) | **0** |
| `components_for_mode()` | méthode publique | **0** |
| `gammes` | `amdec.yaml` | **0** (une seule mention, dans une *docstring* de `api/main.py`) |
| `process_states` | `tags.yaml` | **0** (une seule mention, dans un *commentaire* de `dcs_loader.py`) |

| # | Constat | Gravité |
|---|---|---|
| K-1 | Cinq surfaces publiques chargées et jamais consommées. Les barèmes AMDEC et les gammes sont des données de valeur : le défaut n'est pas qu'elles existent, c'est qu'elles soient **chargées en mémoire comme si elles servaient**. Soit un consommateur les expose, soit elles restent dans le YAML sans être hissées en attribut. | moyenne |
| K-2 | `components_for_mode()` est la réciproque documentée de `modes_for_component()`, qui elle est utilisée. Symétrie d'API non consommée. | mineure |

---

## 8. `src/domain/topology.yaml` — 264 lignes — **lu intégralement**

Contrat entre données DCS, pièces physiques et AMDEC. 11 pièces, 12 capteurs,
19 codes de règle rattachés. Excellente gouvernance : `dimensional_status`
précise que le modèle est *« à l'échelle, non coté »* et que les plans
constructeur 711-104/105/106 ne sont pas au dossier — aucune cote affichée ne
doit passer pour une cote de fabrication.

### La cause du désordre des capteurs — **trouvée**

Le fichier déclare un champ `anchor`, documenté ligne 140 :

> `anchor` : orientation de l'etiquette pour eviter les recouvrements.

Mesure des distances entre capteurs voisins :

| Paire | Distance | Ancres |
|---|---|---|
| `T_ACID_IN` / `C_ACID_1100` | 0,96 m | **up / up** |
| `T_ACID_OUT` / `C_ACID_1200` | 0,96 m | **down / down** |
| `LOAD_SULFUR` / `F_3412` | 0,75 m | **left / left** |
| `F_3412` / `A_3301` | 0,75 m | **left / left** |
| `A_3301` / `A_3302` | 0,75 m | **left / left** |
| `PHI_5306` / `TI_5303` | 0,75 m | **right / right** |

**Les six paires les plus rapprochées portent chacune deux ancres
identiques.** Le champ censé écarter les étiquettes pousse les deux voisines
dans la *même* direction : le recouvrement est garanti par construction. C'est
exactement ce que montre la capture — `C_ACID_1100` et `T_ACID_IN` empilées en
haut à gauche.

| # | Constat | Gravité |
|---|---|---|
| T-1 | Le mécanisme anti-recouvrement produit le recouvrement. Correction : alterner les ancres au sein de chaque paire, ou espacer, ou les deux. | **haute** — c'est le défaut visible signalé par l'utilisateur |
| T-2 | `attaches_to` n'est lu **ni par `twin.js` ni par `app.js`** (0 occurrence). Le lien capteur → pièce est gouverné, exposé par `knowledge.topology()`, et jamais exploité à l'écran. | moyenne |

---

## 9. `src/ingest/dcs_loader.py` — 585 lignes — **lu intégralement**

Rôle : transformer l'export DCS brut en table exploitable **sans jamais masquer
un problème de donnée**. Principe directeur énoncé en tête : la qualité de
donnée est une information, pas un déchet. Un capteur figé n'est pas du bruit à
nettoyer, c'est le mode AMDEC `CAPTEUR_DEFAILLANT` (criticité 108).

### Trois corrections de causalité, documentées et vérifiables

- `_detect_frozen` mesurait la longueur **totale** du palier et marquait
  rétroactivement tous ses points — y compris ceux où l'on ne pouvait pas
  encore savoir que le signal resterait constant. **2 327 événements `FROZEN`**
  étaient datés ainsi, et ils alimentent `n_invalid_tags`, la règle
  `CAPTEUR_DEFAILLANT` et le drapeau d'applicabilité du modèle. La chaîne
  consommait une information venue du futur.
- `classify_process_state` lisait `is_down.shift(-1)` : l'instant *t* était
  déclaré `TRANSIENT` parce que la ligne s'arrêtait en *t+1*. **27 horodatages**
  concernés, écartés du modèle sur la foi d'une information qui n'existait pas
  encore.
- La feuille Excel est désignée **par son nom** (`Feuil1`, gouverné dans
  `tags.yaml`) et non par sa position : l'ajout d'un onglet en tête de classeur
  aurait fait ingérer silencieusement des données étrangères.

`classify_process_state` **lève** si une des trois colonnes requises manque, au
lieu d'appliquer « les critères disponibles ». Sur la décision la plus
déterminante du système, c'est le bon choix.

### Le chemin absolu — la source, enfin trouvée

```python
report = {
    "source": str(path),      # ligne 495
    ...
}
```

Ce champ remonte par `pipeline.health_report()["ingestion"]` et est publié tel
quel par l'API. C'est **lui** qui mettait
`<racine du depot>\data\raw\DATA.xlsx` dans le rapport de gouvernance.

| # | Constat | Gravité |
|---|---|---|
| D-1 | La correction appliquée à `src/notifications/redaction.py` est **en aval** : elle assainit le courriel, pas la source. `/api/health/*` continue de publier le chemin absolu de la machine hôte. | **haute** |
| D-2 | Le dépôt applique pourtant déjà cette discipline ailleurs : `config.summary()` publie ses chemins en relatif, avec un commentaire qui explique exactement pourquoi. Deux parties du même code, deux règles opposées. | — |
| D-3 | `test_les_artefacts_ne_portent_pas_de_chemin_absolu` ne contrôle que des **fichiers JSON**. Aucun test ne contrôle les **réponses de l'API**. Le garde-fou existe mais ne couvre pas la porte ouverte. | moyenne |

### Doublon de représentation des données

`IngestionResult` porte **deux** tables de valeurs :

- `readings` — valeurs assainies, capteurs `degraded` supprimés, invalides à
  `NaN`. Consommée par tout le pipeline.
- `observations` — valeurs brutes, capteurs dégradés compris,
  « réservées à la visualisation ». Consommée uniquement par `api/main.py`
  (lignes 846-847 et 985).

La distinction est **légitime et bien motivée** : montrer à l'écran ce que le
DCS affiche réellement, sans jamais le donner au modèle. À conserver, mais à
documenter dans l'architecture — ce n'est pas un doublon accidentel.

---

## 10. `src/features/e7301_features.py` — 806 lignes — **lu intégralement**

L'en-tête de 88 lignes est le document le plus important du dépôt sur le plan
scientifique. Il consigne une **auto-réfutation** :

> La version précédente affirmait que l'encrassement « se lit sur l'effort ».
> Cette affirmation est FAUSSE, et l'erreur est algébrique.

Démonstration : `duty = ρ·cp·F·(T_in − T_out)` avec `T_out` régulée (σ = 0,8 °C
sur 14 mois) est déjà une combinaison linéaire des régresseurs de la référence.
La régression ne modélisait pas l'échangeur, **elle retrouvait sa propre
définition**.

| Mesure | Valeur |
|---|---|
| R² de la référence apprise | 0,968 |
| R² d'une formule **sans apprentissage** | 0,962 |
| Apport réel du modèle appris | **0,006** |
| corr(résidu, écart de consigne) | **−0,94** |

Conséquence tirée : le résidu est renommé `regulation_effort` — ce qu'il mesure
réellement — et n'est plus jamais présenté comme une preuve distincte. Ces
chiffres sont **recalculés à chaque ajustement** (`naive_r2`, `learned_gain`),
publiés dans le manifeste, et un test échoue si la redondance disparaît sans
que l'analyse soit reprise.

Même rigueur sur `rho_cp` : le raffinement en température est conservé « parce
qu'il est plus juste », mais un test **empêche de le survendre** — ρ et cp
varient en sens opposés et leur produit ne bouge que de 0,2 %.

### Corps du fichier

`MODEL_FEATURES` compte 11 variables, conformes au manifeste. Trois références
linéaires (`ConductanceReference`, `RegulationEffortReference`,
`InletReference`) partagent une classe de base et **la même borne de période de
référence** — `reference_cutoff(df)`, calculée une fois sur les heures de marche
établie. Le commentaire consigne le défaut réparé : le repli `0.40` était
découpé **après** application du masque d'éligibilité propre à chaque
référence, si bien que les trois s'arrêtaient à des instants différents.

Autres corrections documentées et vérifiées dans le code :

- `conc_min` : la v1 prenait `min(AI1100, AI1200)` au nom d'une « approche
  conservative » supposant les analyseurs redondants. Corrélation réelle
  **+0,35**, biais systématique de 0,124 point : AI1200 était le minimum dans
  **94,9 % des cas**. Le `min()` se réduisait à un seul capteur tout en donnant
  l'illusion d'une sécurité par redondance.
- `d_t_out` et `d_conc` sont calculés **par segment continu de marche** : une
  reprise après arrêt n'est pas comparée au dernier point avant l'arrêt.
- `conc_drop_24h` utilise `shift(freq="24h")` — décalage calendaire, pas
  positionnel : un trou d'acquisition ne transforme pas « 24 lignes » en plus
  de 24 heures.
- Les moyennes glissantes 14 jours **n'entrent pas** dans le modèle. Le
  commentaire chiffre pourquoi : le taux de signalement passait de 10 % à 17 %,
  et à **65 % sur octobre**. Une dérive lente est *un* événement, pas une
  succession de points anormaux.

### Colonnes calculées et jamais consommées

Recherche d'usage hors du fichier producteur, sur `src/` et `api/` :

| Colonne | Usages ailleurs |
|---|---|
| `duty_per_load` | **0** |
| `approach_ratio` | **0** |
| `t_in_expected` | **0** |
| `t_in_residual_trend_14d` | 1 (contre 9 pour son homologue `regulation_effort_trend_14d`) |

| # | Constat | Gravité |
|---|---|---|
| F-1 | Trois colonnes sont calculées à chaque construction de features, sur 10 180 lignes, et lues par personne. L'en-tête les annonce « disponibles pour l'affichage et les règles métier » — elles ne le sont ni pour l'un ni pour l'autre. | moyenne |
| F-2 | ~~Asymétrie : `regulation_effort_trend_14d` consommé 9 fois contre 1 pour `t_in_residual_trend_14d`. Soupçon de contradiction entre le fichier de features et le moteur de règles.~~ **HYPOTHÈSE RÉFUTÉE — voir ci-dessous.** | — |

### F-2 : vérification faite, il n'y a pas de contradiction

Le comptage brut était trompeur et je l'avais mal interprété. Lecture de
`_rule_thermal_drift` (`detector.py` l. 298-444) :

- La **dégradation** (`FOULING_DRIFT`, mode `FAISCEAU_BOUCHAGE`) est déclenchée
  par `ua_residual_trend_14d` — le résidu de coefficient d'échange, seule
  grandeur ancrée sur une donnée extérieure à l'atelier.
- L'effort de régulation ne sert que de **corroboration facultative**
  (`corrobore` dans les preuves) et ne déclenche jamais rien seul.
- Seul il ne produit que `OVERCOOLING_REGIME`, en sévérité `INFO`, explicitement
  qualifié de **régime de conduite et non de dégradation**, avec un rappel de
  lecture inséré dans le message : « cet indicateur est une réécriture de
  l'écart de consigne, pas une preuve indépendante ».

Ses 9 occurrences sont des citations **en contexte**, pas des conditions de
déclenchement. Le moteur de règles et le fichier de features disent la même
chose. La hiérarchie annoncée est respectée dans le code.

Reste un constat mineur : `t_in_residual_trend_14d` est calculé et consommé une
seule fois, alors que `t_in_residual_z` (sans tendance) figure bien dans
`MODEL_FEATURES`. La tendance 14 jours de cet indicateur n'a pas d'emploi établi.

---

## 10 bis. `src/models/detector.py` — 1 333 lignes — **lecture en cours**

`_rule_thermal_drift` porte la correction la plus instructive du dépôt :

> Une version précédente faisait dépendre le passage en `WARNING` d'une
> corroboration par l'effort de régulation, exigeant `effort <= -1.5 sigma`.
> Cet indicateur **ne descend jamais sous −0,99 sigma** sur ce corpus, quelle
> que soit la période de référence : la sévérité `WARNING` était
> **structurellement inatteignable**, et un test l'affirmait pourtant en
> forçant une valeur que les données ne produisent pas.

Deux fautes en une : une branche morte, et une incohérence de fond — le projet
déclare partout que l'effort de régulation « ne constitue jamais une preuve
d'encrassement », puis lui confiait la gradation de l'alerte d'encrassement.

Également corrigé et documenté ici : `tail(72)` retenait les 72 dernières
**lignes**, pas les 72 dernières **heures**. À travers un arrêt de ligne, ces
72 lignes couvrent plusieurs semaines — le message affirmait « maintenu depuis
plus de 72 h » sur une fenêtre qui n'en représentait pas 72, et la preuve
`persistance_h` publiait un nombre de lignes sous un nom d'heures.

### M-1 — le seul endroit du dépôt qui viole sa propre règle des seuils

```python
# src/models/detector.py, l. 49
from src.domain.knowledge import DomainKnowledge, load_domain, seuil
...
# l. 294-296
mode = self.domain.modes.get("FAISCEAU_BOUCHAGE")
seuil = (mode.signature.get("warning_sigma") if mode else None) or 3.0
return max(float(seuil), DRIFT_Z_THRESHOLD)
```

Deux fautes superposées.

**1. L'idiome `or` sur un seuil gouverné.** La fonction `seuil()` existe
précisément pour cela — son *docstring* dit : « LE REPLI TESTE L'ABSENCE, PAS
LA FAUSSETÉ », et documente que cet idiome sévissait à douze endroits. Ici
`warning_sigma` est lu dans `amdec.yaml`, donc modifiable par le service
fiabilité : c'est exactement la catégorie visée. Une valeur légitimement nulle
serait remplacée par 3,0 sans avertissement.

**2. Le nom local écrase la fonction importée.** Dans le corps de
`_fouling_warning_sigma`, `seuil` ne désigne plus la fonction mais un `float`.
Le code marche aujourd'hui parce que la fonction n'y est pas appelée — mais
toute ligne ajoutée dans cette méthode qui appellerait `seuil(...)` échouerait
sur `'float' object is not callable`. C'est un piège posé pour le prochain
lecteur, dans la méthode même qui aurait dû utiliser la fonction.

Correction : `seuil_sigma = seuil(mode.signature.get("warning_sigma") if mode
else None, 3.0)`.

Vérification faite sur tout le dépôt : les autres emplois de `or` portent sur
des compteurs (`n_invalid_tags or 0`), des libellés d'affichage ou des listes
par défaut, où `0`, `""` et `None` ont le même sens. **`detector.py:295` est le
seul cas fautif restant.**

### M-2 — résidus du renommage « jumeau thermique »

Le projet a répudié le terme « jumeau thermique » pour une raison de fond,
exposée dans `e7301_features.py` l. 436 : ce que l'objet modélisait n'était pas
l'échangeur mais sa propre définition algébrique. L'objet a été renommé
`References` et le paramètre `twin` est devenu `references`.

Le renommage est incomplet — la *signature* a changé, la *documentation* non :

| Emplacement | Texte | Réalité |
|---|---|---|
| `detector.py` l. 861 | `twin: Jumeau thermique associe (conserve pour l'audit).` | l'attribut s'appelle `self.references` |
| `detector.py` l. 875 | `twin: Jumeau thermique deja ajuste.` | le paramètre s'appelle `references` |
| `tests/conftest.py` l. 46-50 | `"""Table de features et jumeau thermique ajuste."""` puis `feats, twin = build_features(...)` | la fixture renvoie des `References` |

| # | Constat | Gravité |
|---|---|---|
| M-2 | La classe `CoolerAnomalyDetector` documente un paramètre `twin` qui n'existe pas, sous un nom que le projet déclare ailleurs trompeur. Un lecteur qui suit la *docstring* cherche un argument absent, et réapprend un vocabulaire abandonné. | moyenne |

### Ce qui est solide dans l'étage statistique

- **Calibration du score.** `1.4826 · MAD` seul donnait une échelle de 0,050
  pour une queue s'étendant sur 0,30 : la sigmoïde saturait et **1,3 % des
  heures ressortaient à 1,0000**, indistinguables. Le tableau des « épisodes
  les plus sévères » affichait douze fois la même valeur. L'échelle ne descend
  plus sous l'écart-type.
- **`margin_sigma()`** existe parce que le score borné sert à *décider*, pas à
  *classer* : toute transformation bornée écrase la queue, c'est-à-dire
  exactement la zone où l'exploitant doit distinguer deux épisodes. La marge
  n'est pas bornée et se lit « +3,2 σ au-dessus du seuil ».
- **`attribute()`** groupe le point de référence et ses N variantes occluses en
  **un seul appel** à la forêt — le coût fixe de sklearn domine le calcul.
- La borne d'apprentissage de l'étage statistique a été alignée sur celle des
  trois références thermiques : il apprenait auparavant sur une fenêtre
  différente de celle des résidus qu'il consomme.
- Le cache de scores est justifié par une mesure : 38 ms par instant, dont
  **27 ms de rescorage redondant**.
- `invalidate_cache()` **existait, avec pour *docstring* « à appeler après tout
  ré-entraînement », et rien ne l'appelait**. Deux ajustements successifs
  produisaient la même clé de cache et les scores de l'ancien modèle étaient
  renvoyés tels quels : le ré-entraînement restait sans effet observable. Le
  commentaire le formule mieux que je ne le ferais — « la méthode était l'aveu
  du défaut, laissée débranchée ».

### M-3 — la correction appliquée à une table, pas à sa jumelle

Le commentaire des lignes 1203-1209 énonce une règle et la revendique comme
corrigée :

> LA TABLE NE COUVRE QUE DES FEATURES QUE LE MODÈLE PEUT DÉSIGNER. Elle
> contenait `ua_residual_trend_14d`, `fouling_resistance` et `n_invalid_tags`
> — trois grandeurs absentes de `MODEL_FEATURES` […] **trois entrées sur cinq
> étaient inatteignables et donnaient l'illusion d'une couverture plus large.**

La correction a été portée sur `_MODE_BY_RESIDUAL`, réduit à 2 entrées, toutes
atteignables. **`_MODE_BY_THRESHOLD`, juste en dessous, n'a pas été traité :**

```
"conc_min":      ("FAISCEAU_CORROSION", "C_ACID_1100", "alarm_low"),
"conc_drop_24h": ("FAISCEAU_FUITE",  "", "")   <-- ne peut jamais accuser
"d_conc":        ("FAISCEAU_FUITE",  "", "")   <-- ne peut jamais accuser
"flow_per_load": ("CALANDRE_FUITE",  "", "")   <-- ne peut jamais accuser
```

`_mode_for_feature` sort sur `if not tag_name: return None` : **trois entrées
sur quatre retournent invariablement `None`**. Le comportement est délibéré et
motivé — la règle déterministe correspondante porte déjà son seuil de
matérialité — mais la forme retenue est exactement celle que le commentaire
voisin condamne : une table qui paraît couvrir quatre modes et n'en rattache
qu'un.

| # | Constat | Gravité |
|---|---|---|
| M-3 | Le même défaut de « couverture illusoire » subsiste dans la table jumelle, à vingt lignes de son propre correctif. Le test `test_le_rattachement_ne_cite_que_des_features_du_modele` verrouille l'appartenance à `MODEL_FEATURES`, pas l'**atteignabilité**. | moyenne |

| # | Constat | Gravité |
|---|---|---|
| M-4 | `save()` sérialise `"features": MODEL_FEATURES` (constante de module) au lieu de `self.stat.features` (état réel de l'instance). Le constructeur accepte pourtant une liste de features personnalisée. Divergence silencieuse possible entre l'artefact et son manifeste. | mineure |

---

## 12. `src/features/thermal.py` — 410 lignes — **lu intégralement**

C'est le module qui porte le diagnostic. Sa qualité d'énonciation est
remarquable, en particulier cet aveu placé en tête plutôt qu'en note de bas de
page :

> Le débit d'eau de mer n'est pas instrumenté, et c'est LUI que la régulation
> manipule pour tenir la consigne. La grandeur calculée ici est donc un **UA
> APPARENT** : état de la surface × action de la boucle froide. Tant que la
> vanne conserve de la marge, elle compense un début d'encrassement et
> UA_apparent ne bouge pas.

Conséquence assumée : le banc d'injection ne publie pas un taux de détection
mais **l'avancement auquel la détection survient**. C'est la mesure du retard,
et c'est le chiffre honnête.

### Deux corrections majeures documentées

- **La référence voyait tout le corpus.** Faute de date de révision,
  `reference_end` valait `None` et la référence UA était ajustée sur les
  quatorze mois : elle apprenait comme normale la dégradation qu'elle doit
  détecter, et le résidu ne pouvait plus dériver.
- **`reference_cutoff` répare une contradiction avec l'ADR-009.** L'ADR affirme
  que les trois références « partagent la même règle ET la même période ».
  Mesure : elles s'arrêtaient à **2024-07-13 17:00, 18:00 et 21:00**. La règle
  était partagée, la période non.
- **`fouling_resistance` comparait à la mauvaise valeur.** `Rf = 1/UA −
  1/UA_moyen` mesurait surtout le régime : corrélation **−0,76 avec le débit**
  et **−0,90 avec UA attendu**. Une simple baisse de débit se lisait comme un
  encrassement. En comparant à la valeur attendue *aux conditions de
  l'instant*, ces corrélations tombent à **+0,13 et +0,08**.
- L'écrêtage d'efficacité à 0,999 est **compté et journalisé** : un écrêtage
  sur la grandeur de diagnostic ne peut pas être silencieux.

### Surface morte

| Élément | Usages hors du fichier |
|---|---|
| `fouling_resistance_trend_14d` | **0** |
| `ntu_de()` (fonction publique) | **0** |
| `EFFECTIVENESS_MAX` | **0** |

| # | Constat | Gravité |
|---|---|---|
| TH-1 | `fouling_resistance_trend_14d` est calculé à chaque construction de features — une moyenne glissante 14 jours sur 10 180 lignes — et n'est lu par personne. C'est la quatrième colonne morte identifiée, après `duty_per_load`, `approach_ratio` et `t_in_expected`. | moyenne |

---

## 13. `src/agents/schemas.py` — 286 lignes — **lu intégralement**

Contrats partagés entre l'agent et le contrôleur. Le fichier porte deux
corrections de conception majeures.

**Deux horizons au lieu d'un.** Une seule échelle d'urgence produisait des
recommandations contradictoires : *« SOUS_24H — mesure des épaisseurs par
courant de Foucault, tâche à cadence 4 ans, exige un arrêt process à programmer
avec la production »*. On demandait sous 24 h ce qui se planifie sur des mois.
`Urgency` (délai de **qualification**) et `ExecutionWindow` (fenêtre
d'**exécution**) sont désormais séparés.

**Un barème de confiance partagé.** L'agent annonçait selon une règle, le
contrôleur jugeait selon une autre. Les deux ont divergé sans que personne ne
s'en aperçoive, et le contrôleur a fini par accuser l'agent de sur-confiance
sur **100 % des heures d'arrêt**. Le commentaire tire la leçon : « deux barèmes
qui doivent coïncider ne se recopient pas, ils se partagent ».

### J-1 — Ce que la couche de vérification transmet, et ce qu'elle perd

**CORRECTION D'UNE ERREUR D'ANALYSE DE MA PART.** J'avais d'abord cherché les
noms de champs de `JudgeVerdict` dans le front et conclu qu'aucun n'était
affiché. C'était faux : `realtime/replay._compact()` **renomme** les champs
avant transport (`flagged_issues` → `judge_issues`, `feedback` →
`judge_feedback`). Recherche refaite sur les noms réellement transmis.

**Ce qui est bien affiché :**

| Champ transmis | Usages dans `app.js` | Rendu |
|---|---|---|
| `judge_score` | 5 | note du contrôleur |
| `judge_agreement` | 2 | accord / désaccord |
| `judge_issues` | 2 | bloc « **Réserves du contrôleur** », chaque code traduit en français via `RESERVE_LABEL` |
| `findings` | 3 | constatations |
| `measurements` | 2 | mesures |

Le rendu des réserves est même soigné : chaque code d'anomalie porte un titre
et une glose en français plutôt que son identifiant brut.

**Ce qui est transmis et jamais affiché :**

| Champ | Ce qu'il porte | Usages |
|---|---|---|
| `judge_feedback` | **la synthèse de 2 à 4 phrases rédigée pour l'ingénieur fiabilité** | **0** |
| `attributions` | l'explication du modèle — quelle grandeur a fait le score | **0** |

**Ce que `_compact()` ne transmet même pas :**

`corrected_severity`, `verified_facts`, `deterministic_score`, `llm_score`,
`judged_by`, `rule_version`, `model_runtime_signature`. Ces champs existent
dans `JudgeVerdict`, sont calculés à chaque décision — et **l'API les écarte
avant l'envoi**. Ce n'est donc pas le front qui les ignore : ils ne lui
parviennent jamais.

`corrected_severity` est le plus regrettable : c'est **la sévérité que le
contrôleur aurait retenue** quand il diverge de l'agent. C'est l'objection du
contrôleur, sous sa forme la plus directe et la plus utile.

**Le panneau « contrôles » est une description statique.** `dashboard.html`
porte `<div class="checks" id="checks">`, rempli ligne 1347 par :

```js
const CHECKS = [
  ["V1", "Fidélité numérique", "22 %", "Chaque valeur citée est confrontée..."],
  ...
];
```

Une constante en dur. Le panneau explique **ce que le Judge vérifie**, jamais
**ce qu'il a trouvé** sur la décision affichée. Or `_compact(full=True)`
transmet bien les `checks` réels pour les désaccords : la donnée est là,
l'affichage ne la lit pas.

| # | Constat | Gravité |
|---|---|---|
| J-1 | La partie visible du contrôleur se limite à une note, un booléen et des codes de réserve. Le raisonnement — synthèse rédigée, sévérité corrigée, faits recalculés, résultat réel des huit contrôles — reste invisible. Trois champs sont même écartés par `_compact()` avant transport. | moyenne |

Constat révisé à la baisse : le contrôleur **n'est pas muet** à l'écran,
contrairement à ce que j'avais conclu. Il dit *qu'il* a une réserve et *laquelle*,
sans dire *pourquoi* ni *ce qu'il aurait retenu à la place*.

### Surface morte confirmée

| Élément | Usages |
|---|---|
| `Check.issue_code` (propriété) | **0** partout — y compris le front |
| `JudgeVerdict.validation_scope` | **0** partout |

`issue_code` est explicitement l'ancien accesseur mono-code que la classe a
remplacé — sa propre *docstring* explique pourquoi la liste était nécessaire :
« n'en garder qu'un faisait disparaître l'autre du journal d'audit ». Le
vestige est resté.

---

## 14. `src/agents/judge_agent.py` — 1 289 lignes — **lu intégralement**

L'en-tête énonce pourquoi la v1 ne pouvait pas fonctionner, et c'est juste :
pas de source de vérité indépendante (le contrôleur notait la **cohérence
interne d'un texte, pas sa véracité**), complaisance structurelle d'un LLM à
qui l'on demande de noter une production plausible, et non-reproductibilité.

La v2 recalcule les faits depuis la même chaîne, puis confronte. Huit contrôles
pondérés, `V1_NUMERIC_FIDELITY` en tête à 0,22.

### Le mécanisme anti-hallucination

`VerifiedFacts.legitimate_numbers` construit **l'univers des nombres qu'un
diagnostic a le droit de citer** : mesures, preuves des constatations,
contributions du modèle, seuils du référentiel, cotations AMDEC. Tout nombre du
texte hors de cet ensemble est signalé `UNVERIFIABLE_VALUE`. Les entiers sous
10 sont ignorés — ce sont des comptages, pas des mesures.

C'est une bonne idée, et elle est proprement bornée.

### Corrections documentées, toutes vérifiables

- **V3** confondait `none` et `partial` : invoquer un mode partiellement
  observé sur la foi de son symptôme est légitime — c'est ce que fait le moteur
  de règles quand le débit s'effondre. La confusion **sanctionnait comme
  hallucination six décisions parfaitement fondées**.
- **V4** balayait *toutes* les tâches de *tous* les modes invoqués. Pour
  `CALANDRE_FUITE` (tâches A — arrêt process, 4 ans ; C — en marche, 1 mois),
  une inspection externe mensuelle correcte était sanctionnée `UNSAFE_ACTION`
  avec note plafonnée à 1/10, parce que la tâche A du même mode exige une
  consignation.
- **V5** — le cas le plus instructif du dépôt. En alignant le contrôleur sur le
  barème de l'agent, la corroboration a porté la confiance justifiable maximale
  de 0,80 à 0,90 : une annonce à 0,99 ne laissait plus qu'un écart de 0,09,
  **sous la tolérance de 0,12**, et cessait d'être relevée. Le piège
  `_m_overconfidence` du banc, qui affiche exactement 0,99, n'était plus
  détecté. Le commentaire le qualifie exactement : « régression introduite par
  une correction, et invisible tant que la suite n'a pas tourné ».

### J-2 — typographie incohérente dans les libellés du contrôleur

Sur les 8 libellés de contrôle, **5 sont sans accents et 3 en portent** :

```
SANS ACCENT                                        ACCENTUÉS
  Les valeurs citees correspondent-elles ...         La sévérité correspond-elle aux faits ?
  Les modes AMDEC invoques sont-ils fondes ?         L'action est-elle proportionnée ... ?
  La confiance est-elle calibree sur les preuves ?   L'état de marche est-il respecté ?
  Le fait le plus grave est-il traite ?
  Les limites du diagnostic sont-elles enoncees ?
```

Ce sont des textes destinés à l'exploitant.

**CORRECTION DE MA JUSTIFICATION.** J'avais écrit que le corpus de
`tests/test_typographie.py` « ne couvre pas les contrôles du Judge ». **C'est
faux** : `test_les_controles_du_juge_sont_accentues` les inspecte explicitement,
`label` et `detail`, sur six instants notables.

La vraie raison est ailleurs. La détection est **lexicale et volontairement
limitée** — le fichier l'énonce : « la détection est volontairement lexicale
plutôt que morphologique : elle est **exacte sur ce qu'elle couvre**, et
n'invente aucun faux positif ». Or aucun des mots fautifs de ces cinq libellés
ne figure dans `MOTS_A_ACCENTUER` :

```
citees · reelles · invoques · fondes · calibree · traite · enoncees
```

Vérification exécutée : `fautes()` **ne signale aucun** des cinq libellés.

| # | Constat | Gravité |
|---|---|---|
| J-2 | Deux typographies dans le même fichier, sur une surface **effectivement inspectée** par la suite. Le contrôle ne les voit pas parce que son lexique de 44 mots ne contient pas ces participes. Correction : enrichir `MOTS_A_ACCENTUER`, ce qui fera immédiatement échouer le test et révélera d'autres cas ailleurs. | moyenne |

**J-2 est un symptôme de J-1** : personne n'a soigné la forme de textes que
personne n'affiche. Les deux constats se corrigent ensemble ou pas du tout.

### Suite de la lecture — V6 à V8, étage LLM, `JudgeAuditor`

- **V8** porte une correction remarquable. Le contrôle cherchait ses mots-clés
  dans un texte simplement mis en minuscules. **Quand les textes du système ont
  été correctement accentués, cinq des douze clés sont devenues introuvables**
  — « reserve », « defaut », « degrade », « prelevement », « verifier ». V8 a
  échoué sur **100 % des heures hors marche**, et l'exploitant lisait « limite
  non énoncée » sous un diagnostic dont la première phrase est « la surveillance
  de performance n'est pas applicable ». La leçon est écrite : *« un contrôle de
  gouvernance ne doit jamais dépendre de la typographie du texte qu'il
  inspecte »*. `sans_accents()` règle le cas.
- **V6** lit désormais les modes de performance depuis la topologie
  (`modes_for_component("BUNDLE")`) au lieu d'une liste en dur.
- **`suspended_audit()`** : les décisions du banc d'injection sont fausses *par
  construction*. Les compter faisait chuter le taux d'accord affiché de 1,00 à
  **0,50**, et laissait croire à l'exploitant que le système se contredit en
  exploitation.
- **`_apply_safety_cap`** renvoie le plafond au lieu de seulement l'appliquer :
  la synthèse annonçait « note plafonnée à 4/10 » quel que soit le plafond réel
  (un état de marche erroné plafonne à 5,0). « Un texte de gouvernance qui cite
  un chiffre faux se disqualifie seul. »
- **`JudgeAuditor.report()`** traite le panneau vide comme une occasion
  pédagogique plutôt que par « AUCUNE DONNEE ».

### J-3 — la même correction appliquée à un endroit, pas à l'autre

```
l. 954-957   # `if capped` traitait un plafond nul comme une absence de plafond
             if capped is not None and adjustment > 0:      ← corrigé
l. 1239      if capped:                                      ← non corrigé
```

Le commentaire de la ligne 954 explique le danger : un plafond nul lu comme une
absence de plafond aurait permis au LLM de **remonter la note de la décision la
plus gravement fautive**. La correction n'a pas été portée sur
`_default_feedback`, 285 lignes plus bas, où la même expression décide si la
mention « Note plafonnée à … » figure dans la synthèse.

Aujourd'hui sans effet — `_apply_safety_cap` ne renvoie que `4.0`, `5.0` ou
`None`. Mais c'est le troisième cas de **correction appliquée à un exemplaire
et pas à son jumeau** (après M-3 sur `_MODE_BY_THRESHOLD`, et la fuite de
chemin absolu corrigée en aval seulement). Le motif est récurrent et mérite
d'être traité comme tel.

### J-4 — couplage circulaire contourné par imports différés

`schemas.py` existe, dit son en-tête, pour « éviter l'import circulaire entre
les deux agents ». Or `judge_agent.py` importe bien `detection_agent` — mais
**à l'intérieur des fonctions**, lignes 1275 et 1288 :

```python
def _try_build_llm():
    from src.agents.detection_agent import _try_build_llm as _build
    return _build()

def _extract_json(raw: str) -> dict:
    from src.agents.detection_agent import _extract_json as _ej
    return _ej(raw)
```

Deux fonctions qui ne font que déléguer, avec un import différé pour casser le
cycle. Le cycle existe donc bel et bien, et le remède énoncé (`schemas.py`)
n'a pas été appliqué à ces deux utilitaires. Ils appartiennent à un module
partagé — `schemas.py` ou un `src/agents/llm.py`.

### J-5 — `uncertainty_level` est une constante déguisée en champ

```python
uncertainty_level: Literal["low", "medium", "high"] = "high"   # schemas.py
uncertainty_level="high",                                       # judge_agent.py, seul appel
```

Le champ propose trois valeurs, une seule est jamais produite, et le front ne
le lit pas (voir J-1). Soit il varie selon les faits — l'information existe :
`n_invalid_tags`, `model_applicable`, `observabilite` — soit c'est une phrase
fixe qui n'a pas besoin d'un champ typé.

---

## 15. `src/agents/detection_agent.py` — 772 lignes — **lu intégralement**

Deux modes, un seul contrat de sortie. Le mode `rules` est revendiqué comme la
**référence** et non comme un pis-aller : il donne au contrôleur un point de
comparaison pour mesurer ce que le LLM apporte réellement, et garantit que le
système reste démontrable sans connexion ni quota.

### Corrections documentées

- **`_priorite`** : `max()` renvoie le premier élément à égalité. Entre un
  `SENSOR_FAULT` et un `CONC_DROP_SEVERE` tous deux `CRITICAL`, le diagnostic
  retenait le défaut capteur — **parce que `_rule_sensor_health` s'exécute en
  premier**. Le fait le plus grave était relégué en constatation concomitante,
  et c'est le défaut capteur qui pilotait l'action recommandée.
  Le tri sur la seule criticité AMDEC ne suffisait pas non plus :
  `CAPTEUR_DEFAILLANT` porte 108 — cotation **proposée** par ce travail,
  `validation_status: hypothesis` — contre 105 pour `FAISCEAU_FUITE`, ligne
  **transcrite du document OCP**. Un analyseur dégradé aurait dominé une
  suspicion de percement de tube.
- **`_tache_la_plus_frequente`** : `plan_maintenance_ref[0]` dépendait de
  l'ordre de saisie du YAML. Pour `FAISCEAU_BOUCHAGE`, refs `["B", "H"]`, la
  recommandation citait le contrôle bisannuel plutôt que le changement octennal
  — *correct par chance*. Inverser les deux lettres dans le référentiel aurait
  fait recommander un remplacement de faisceau sur une dérive naissante.
- **`_calibrate_confidence`** réimplémentait une formule différente du barème
  partagé : base 0,55 contre 0,50, pénalité binaire au lieu d'une graduation,
  corroboration créditée ici et ignorée là. **Écart mesuré jusqu'à 0,25 point**,
  à 0,05 de déclencher une réserve de sous-confiance à l'écran. Alors même que
  `schemas.py` affirmait que « la divergence future devient impossible par
  construction ».
- **`_nominal_confidence`** : l'agent annonçait 0,50 dès que le modèle était
  inapplicable, sans distinguer pourquoi. Le contrôleur retranche 0,15 hors
  marche établie et jugeait 0,35 justifiable — écart de 0,15 au-dessus de la
  tolérance de 0,12. **Le contrôleur accusait l'agent de sur-confiance sur
  chacune des 1 385 heures d'arrêt, soit 13,6 % du corpus.** La note globale
  restait à 8,74/10 et l'accord était maintenu : l'anomalie ne se lisait que
  dans l'encart destiné à l'exploitant.

### A-1 — typographie mixte dans un texte **réellement affiché**

`_quote_measurements` (l. 546-555) compose la fin du diagnostic nominal :

```python
("T_ACID_IN",  "entree acide", "degC"),
("T_ACID_OUT", "sortie acide", "degC"),
("F_ACID",     "debit acide",  "m3/h"),
```

Assemblé dans `_nominal_decision` :

> « Marche établie, aucun écart significatif. Les grandeurs de performance du
> refroidisseur sont dans leur **domaine de référence** : **entree acide**
> 94.20 degC, **sortie acide** 65.90 degC, **debit acide** 56.40 m3/h. »

`diagnosis` est lu 4 fois par `app.js` : ce texte **est affiché**. Et comme la
majorité des heures sont nominales, c'est la phrase que l'exploitant voit le
plus souvent. Deux typographies dans la même phrase, plus les décimales en
point anglais (`94.20`) alors que le projet impose la virgule ailleurs.

| # | Constat | Gravité |
|---|---|---|
| A-1 | Contrairement à J-2, ce texte-ci **est sous les yeux de l'utilisateur**, et c'est le plus fréquent de tous. Le corpus de `test_typographie.py` ne le couvre pas. | **haute** |

### A-2 — le coupe-circuit ne distingue pas la panne de la maladresse

```python
except Exception as e:
    self.llm = None      # définitif jusqu'au redémarrage
```

Le commentaire justifie le mécanisme par « une clé invalide ou un service
indisponible ». Mais `_extract_json` lève `ValueError` si la réponse ne contient
pas de JSON exploitable, et `RecommendedAction(**data)` lève une
`ValidationError` si le LLM produit un champ hors énumération. **Une seule
réponse mal formée désactive donc le LLM pour tout le processus.**

Le repli sur les règles est correct et sûr — le système reste entièrement
fonctionnel. Mais le diagnostic porté au journal (« coupe-circuit ouvert »)
laisse croire à une indisponibilité du service, alors qu'il peut s'agir d'un
simple écart de format sur un point isolé.

| # | Constat | Gravité |
|---|---|---|
| A-2 | Deux familles d'erreurs — configuration/disponibilité et format de réponse — traitées identiquement, avec une conséquence irréversible. | moyenne |

### A-3 — paramètre inutilisé

`_calibrate_confidence(self, result, lead, mode)` : `lead` n'apparaît que dans
la signature, et sa *docstring* le reconnaît (« conservée pour la signature »).
`mode` n'est pas utilisé non plus — l'observabilité est recalculée sur
`result.amdec_modes`. Deux paramètres sur trois sont morts.

---

## 16. `api/main.py` — 1 639 lignes — **lu intégralement**

### Corrections déjà en place

- **La validation de configuration a été remontée avant tout effet de bord du
  module.** Elle n'intervenait qu'au `lifespan`, donc **après** la construction
  de la gestion de session, **après** la lecture du registre et **après** le
  montage du middleware CORS — tous trois pilotés par cette configuration. Un
  lancement par `uvicorn api.main:app`, forme documentée dans l'en-tête du
  fichier, contournait entièrement le refus propre de `api/__main__.py`.
- **`alert_recipient` était un drapeau mort.** Le registre le stockait,
  `manage_operators add --no-alerts` le posait, un test vérifiait l'accesseur —
  et personne ne l'interrogeait. `auth_login` abonnait inconditionnellement
  l'adresse de session : *un technicien enregistré en lecture seule,
  explicitement exclu des escalades, était réveillé la nuit dès qu'il ouvrait
  une session.*
- **Règle `async def` tenue.** Vérification par AST : 19 handlers restent
  `async` sans `await`, et **tous** relèvent de l'exception énoncée — sondes de
  santé, état de session, lectures du tampon de rejeu, configuration effective.
  Aucun ne calcule, ne lit le disque ni ne sort sur le réseau. Le test cité
  existe (`test_service_invariants.py:74`).

### API-1 — l'exemption publique est plus large que nécessaire

Le middleware exempte du contrôle de session tout chemin commençant par
`/api/auth/` ou `/api/health`. **11 routes sur 45** sont ainsi publiques :

```
GET   /api/auth/status        ← doit l'être
POST  /api/auth/login         ← doit l'être
POST  /api/auth/refresh
POST  /api/auth/logout
GET   /api/auth/audit         ← journal d'authentification
GET   /api/health             GET /api/health/live
GET   /api/health/ready       GET /api/health/model
GET   /api/health/database    GET /api/health/version
```

Deux endpoints seulement ont besoin de l'être : `status` et `login`.

`/api/auth/audit` — **le journal d'authentification, l'endpoint le plus
sensible du sous-système d'accès** — traverse le filtre le plus faible. Il
n'est protégé que par `_require_roles(request, "administrator")` à l'intérieur
du handler.

Ce n'est pas exploitable en l'état : session absente ⇒ `_require_roles` renvoie
403, et si l'accès protégé est désactivé, `AUTH_MANAGER is None` ⇒ liste vide.
Mais la défense repose sur **une seule ligne dans le corps du handler**, là où
le reste du service bénéficie de deux barrières. Une exemption nominative
(`{"/api/auth/status", "/api/auth/login"}`) rendrait la protection structurelle.

Accessoirement, `/api/health`, `/api/health/model` et `/api/health/version`
publient sans session la période de données, la signature d'exécution du
modèle, la version de règles et le motif de rejet de l'artefact. Information
de faible valeur, mais publiée à qui la demande.

| # | Constat | Gravité |
|---|---|---|
| API-1 | Exemption par préfixe là où une liste nominative suffirait ; le journal d'authentification en dépend. | moyenne |

### API-2 — la courbe qui porte le diagnostic n'est pas exposée

`/api/timeseries` (l. 856-861) publie exactement ces colonnes :

```python
raw_aliases = [tag.alias for tag in p.domain.tags.values()]   # 12 tags DCS
cols = [*raw_aliases,
    "conc_min", "delta_t", "duty_kw", "duty_expected", "regulation_effort_z",
    "regulation_effort_trend_14d", "control_deviation",
]
```

Vérification colonne par colonne :

| Grandeur | Rôle déclaré par le projet | Dans `/api/timeseries` |
|---|---|---|
| `regulation_effort_z` | « ne constitue **jamais** une preuve d'encrassement » | **oui** |
| `regulation_effort_trend_14d` | idem | **oui** |
| `control_deviation` | l'écart de consigne, dont l'effort est la réécriture | **oui** |
| `duty_kw` / `duty_expected` | la paire dont le R² est **algébrique**, gain appris 0,006 | **oui** |
| `ua_kw_per_k` | **le coefficient d'échange — porte le diagnostic** | **non** |
| `ua_expected` | sa valeur attendue aux conditions | **non** |
| `ua_residual_z` | l'indicateur d'encrassement | **non** |
| `ua_residual_trend_14d` | **la tendance qui déclenche `FOULING_DRIFT`** | **non** |
| `fouling_resistance` | « la grandeur que suit un ingénieur fiabilité pour arbitrer la date du prochain nettoyage » | **non** |
| `t_in_residual_z` | le seul résidu indépendant (r = +0,03) | **non** |

Et le graphique principal de `app.js` (l. 757) trace :

```js
lines: [["duty_kw", "Observé"], ["duty_expected", "Référence semi-empirique"]]
```

c'est-à-dire précisément la paire dont `e7301_features.py` démontre qu'elle
**retrouve sa propre définition**.

**Conséquence.** L'encrassement se manifeste par une **dérive lente sur des
semaines** — c'est l'argument central du projet, et `FOULING_DRIFT` exige 72 h
de persistance sur une tendance 14 jours. Une dérive se lit sur une **courbe**.
Or la courbe du coefficient d'échange n'existe nulle part dans l'interface :
l'API ne la transmet pas.

Nuance nécessaire : les valeurs UA **atteignent** bien l'écran, mais seulement
comme **points isolés**, à l'intérieur des preuves d'une constatation
(`detector.py` place `ua_kw_per_k`, `ua_expected`, `ua_residual_z` et
`fouling_resistance` dans `measurements`). Les 1 à 3 occurrences trouvées dans
`app.js` sont dans le dictionnaire de libellés et d'unités, pas dans une série.

| # | Constat | Gravité |
|---|---|---|
| API-2 | L'exploitant peut tracer l'indicateur que le projet déclare sans valeur de preuve, et **ne peut pas tracer celui qui porte le diagnostic**. Trois colonnes suffisent à corriger : `ua_kw_per_k`, `ua_expected`, `ua_residual_trend_14d`. | **haute** |

API-2 relève de la même famille que J-1 et que l'absence de pages d'alarmes :
**le raisonnement est juste côté serveur, et l'interface n'en montre pas la
partie décisive.**

### API-3 — le référentiel des gammes est gouverné en YAML **et** recopié en Python

`knowledge.py` ouvre sur ce principe :

> Aucun seuil, aucun nom de tag, aucune criticité AMDEC ne doit être codé en
> dur ailleurs dans le projet : tout passe par ici. C'est ce qui permet de
> **corriger une détermination métier sans toucher au code**.

`_workflow_templates()` (`main.py`, l. 1245-1340) l'applique à moitié :

| Contenu | Origine |
|---|---|
| `INSPECTION_EXTERNE` — 14 points | `domain.checklists` ✅ gouverné |
| `INSPECTION_INTERNE` — 13 points | `domain.checklists` ✅ gouverné |
| **6 prérequis HSE** (`HSE-01` à `HSE-06`) | **écrits en dur dans `main.py`** |
| **8 étapes de tamponnage** (`TAM-01` à `TAM-08`) | **écrites en dur dans `main.py`** |

Or `amdec.yaml` porte une section `gammes` — **chargée dans
`DomainKnowledge.gammes` et lue par personne** (voir K-1) — qui contient
précisément ces informations, sourcées :

```
gammes.PS3-ABS-REFR :
  intitule, duree_min: 295, etat_requis: "Arrêt process + consignation",
  epi: [5 items], outillage: [...],
  prerequis: [7 items]
     1. Consigner le moteur de la pompe d'absorption
     2. Isoler et consigner les circuits acide et eau de mer
     3. Vidanger les boites d'eau de mer
     4. Vidanger la calandre d'acide (pression intérieure ramenée à 0 bar)
     5. Cadenas par intervenant
     6. Autorisation de travail
     7. Débranchement du courant sur les anodes (film-garde)
gammes.TAMPONNAGE : intitule, etat_requis, note
```

**Le référentiel gouverné compte 7 prérequis, la copie Python en compte 6.**
Les deux listes ont déjà divergé. Le point manquant côté code est
« Débranchement du courant sur les anodes (film-garde) » — la protection
anodique, c'est-à-dire le composant de criticité AMDEC **112**, la plus élevée
de l'équipement.

| # | Constat | Gravité |
|---|---|---|
| API-3 | Un tuteur OCP qui corrige `gammes` dans le YAML ne change rien à ce que le poste affiche : les prérequis viennent du Python. C'est exactement ce que `knowledge.py` déclare impossible. Et la divergence est déjà constituée — un prérequis de consignation sur 7 manque. | **haute** |

La correction est nette : `gammes` est déjà chargé, il suffit de le lire.
Cela résout simultanément K-1 (surface morte) et API-3 (duplication divergente).

### API-4 — rôle par défaut « administrator » sur les transitions d'alarme

```python
# alarm_transition, l. 1443-1444
identity = operator.email if operator is not None else "poste-local"
role = operator.role if operator is not None else "administrator"
```

Quand l'accès protégé est désactivé, l'appelant se voit attribuer le rôle **le
plus élevé**, ce qui ouvre `acknowledge`, `shelve`, `unshelve` et `close`.

C'est cohérent avec la posture assumée du poste local — `_require_roles`
retourne également sans rien vérifier dans ce cas — et l'accès protégé
s'active de lui-même dès qu'un technicien est enregistré. Mais la formulation
diffère : ailleurs on **court-circuite** le contrôle, ici on **accorde le rôle
maximal**. Le shelving d'alarme est une action ISA-18.2 à conséquence
opérationnelle : elle masque une alarme.

| # | Constat | Gravité |
|---|---|---|
| API-4 | Deux écritures de la même politique. Un lecteur qui audite les droits doit comprendre que « poste-local » est administrateur. | mineure |

### API-5 — défaut que j'ai moi-même introduit dans cette conversation

En corrigeant la fenêtre de course sur `_premier_destinataire`, j'ai ajouté un
paramètre `demandeur` à **`enqueue_governance` et `enqueue_test`**, puis je ne
l'ai câblé que sur un seul appelant :

```python
# l. 1535 — non câblé
if not _notifier().enqueue_test():

# l. 1555 — câblé
accepted = _notifier().enqueue_governance(
    rediger_gouvernance(payload),
    demandeur=operator.email if operator is not None else None,
)
```

L'e-mail de test part donc toujours au **premier destinataire par ordre
alphabétique**, pas au technicien qui a cliqué — exactement le défaut que je
venais de corriger sur le rapport de gouvernance.

C'est le **quatrième cas** du même motif dans ce dépôt (après M-3, J-3 et la
fuite de chemin absolu), et cette fois j'en suis l'auteur. À corriger en phase
d'exécution.

### Le reste du fichier

- `replay_disagreements` — « la vue la plus importante du point de vue
  gouvernance : elle montre où le système s'est contrôlé lui-même ». Elle est
  bien consommée par le front (mode de flux `disagreements`).
- `unhandled` — un gestionnaire d'exception s'exécute **en dehors** des
  middlewares : sans durcissement explicite, la réponse 500 partait sans aucun
  en-tête de défense. Corrigé, avec un identifiant d'incident.
- `operational_kpi` — publie le **taux horaire réel** à côté de la charge
  d'épisodes, « sans lui, l'agrégation en épisodes masque un taux de
  signalement cinq fois supérieur à la contamination de calibration ».
- `sensor_detail` — lit `observations` et non `features` : « un capteur mort
  doit rester consultable, c'est même la seule façon de voir qu'il est mort ».

---

## 17. `src/operations/alarms.py` — 517 lignes — **lu intégralement**

Registre SQLite du cycle de vie ISA-18.2. Schéma sérieux : WAL, clés
étrangères, `BEGIN IMMEDIATE` avec *rollback*, migration non destructive des
bases antérieures, journal `alarm_history` séparé, et un libellé de transition
qui nomme **l'action de l'opérateur** parce que l'état d'arrivée ne suffit pas
— « ACTIVE » ne distingue pas une désinhibition d'une réapparition.

### AL-1 — la clé fonctionnelle n'est pas stable, malgré ce qu'affirme sa *docstring*

```python
@staticmethod
def _trigger(analysis) -> str | None:
    findings = getattr(analysis.detection, "findings", ())
    return str(findings[0].code) if findings else None      # ← premier de la liste

@classmethod
def _key(cls, analysis) -> str | None:
    """Clé stable : équipement et signal déclencheur, jamais la sévérité."""
```

`findings[0]` est le **premier dans l'ordre d'écriture des règles**, et cet
ordre est fixe dans `RuleEngine.evaluate` :

```python
out += self._rule_sensor_health(row)     # ← toujours en premier
out += self._rule_control_loss(...)
out += self._rule_thermal_drift(...)
out += self._rule_concentration(...)     # ← CONC_DROP_SEVERE est ici
...
```

**C'est exactement le défaut que `detection_agent._priorite` a été écrit pour
corriger**, avec ce commentaire :

> `max()` renvoie le premier élément à égalité : entre un `SENSOR_FAULT` et un
> `CONC_DROP_SEVERE` tous deux `CRITICAL`, le diagnostic retenait le défaut
> capteur — parce que `_rule_sensor_health` s'exécute en premier.

L'agent a été corrigé. **Le registre d'alarmes ne l'a pas été.**

Conséquences concrètes :

1. Un point de mesure en défaut **pendant** une suspicion de percement de tube
   produit la clé `S-PC-E7301::SENSOR_FAULT`, alors que le champ `diagnosis`
   enregistré décrit correctement la fuite — grâce à `_priorite`. **L'alarme
   est classée sous une identité qui ne correspond pas à son contenu.**
2. Quand le défaut capteur se résorbe et que la chute de titre persiste,
   `findings[0]` devient `CONC_DROP_SEVERE` : **une nouvelle alarme est levée**
   tandis que l'ancienne est retournée à la normale — alors que la condition
   critique n'a jamais cessé.

C'est un défaut ISA-18.2 de première grandeur : l'identité d'une alarme doit
survivre aux variations de son contexte. Ici elle dépend de l'ordre
d'exécution des règles.

**Aucun test ne couvre la stabilité de la clé** — `test_alarm_store.py` ne
mentionne ni `alarm_key`, ni `_trigger`, ni `findings[0]`.

| # | Constat | Gravité |
|---|---|---|
| AL-1 | La *docstring* promet une clé stable ; l'implémentation la fait dépendre de l'ordre d'écriture des règles. Cinquième occurrence du motif « correction appliquée à un exemplaire, pas à son jumeau ». Correction : réutiliser le tri de `_priorite`, ou dériver la clé du mode AMDEC dominant. | **haute** |

### AL-2 — la sévérité ne redescend jamais, et ce n'est écrit nulle part

```python
severity = (
    "CRITICAL"
    if "CRITICAL" in {row["severity"], analysis.decision.severity}
    else "WARNING"
)
```

Dès qu'une occurrence a été `CRITICAL`, l'alarme reste `CRITICAL` jusqu'à sa
clôture, même si toutes les observations suivantes sont `WARNING`.

Ce verrouillage au pire cas est **défendable** en ISA-18.2 — une priorité
d'alarme qui oscillerait rendrait la hiérarchisation illisible. Mais il n'est
énoncé ni dans le code, ni dans la *docstring*, ni dans le rapport. La sévérité
affichée est donc un **maximum historique**, présenté comme un état courant.

| # | Constat | Gravité |
|---|---|---|
| AL-2 | Comportement correct mais tacite, sur la grandeur qui pilote la hiérarchisation en salle de contrôle. Une ligne de commentaire et une mention au rapport suffisent. | mineure |

### AL-3 — aucun chemin de clôture pour une alarme active

```python
OPERATOR_TRANSITIONS = {
    "acknowledge": {"ACTIVE": "ACKNOWLEDGED"},
    "shelve":      {"ACTIVE": "SHELVED", "ACKNOWLEDGED": "SHELVED"},
    "unshelve":    {"SHELVED": "ACTIVE"},
    "close":       {"RETURNED_NORMAL": "CLOSED"},      # ← seule entrée
}
```

Refuser de clôturer une alarme encore active est la bonne discipline. Mais le
seul chemin vers `RETURNED_NORMAL` passe par `_return_matching_to_normal`,
c'est-à-dire par **une nouvelle observation du rejeu** portant la même clé.

Deux impasses en découlent :

1. Rejeu arrêté ⇒ aucune observation ⇒ une alarme `ACTIVE` ou `ACKNOWLEDGED`
   ne peut **jamais** être clôturée.
2. Une alarme `SHELVED` dont la condition a cessé conserve son état — c'est
   voulu et bien argumenté — mais après `unshelve` elle repasse en `ACTIVE`,
   pas en `RETURNED_NORMAL`. Il faut donc **attendre une nouvelle observation**
   pour pouvoir la fermer.

Sur un poste de démonstration, le rejeu tourne et le cas se résorbe. Sur un
poste réel, un opérateur qui vient d'intervenir doit pouvoir clore ce qu'il a
traité.

| # | Constat | Gravité |
|---|---|---|
| AL-3 | Le cycle de vie n'a pas de sortie opérateur. À trancher avec B1 : si les pages d'alarmes sont construites, ce chemin devient indispensable. | moyenne |

### Ce que le fichier fait très bien

- Un commentaire signale que **le commentaire précédent disait l'inverse du
  code** : il affirmait que « l'inhibition ne doit jamais masquer une
  résolution automatique », et le code retournait sans rien enregistrer. Le
  retour aux conditions normales est désormais inscrit au journal sous
  `RETURN_TO_NORMAL_WHILE_SHELVED` — « sans lui, l'opérateur qui désinhibe ne
  peut pas savoir que la condition avait cessé entre-temps ».
- La colonne `transition` recevait **l'état d'arrivée, pas l'action** : le
  journal enregistrait « ACTIVE » aussi bien pour une désinhibition que pour
  une réapparition. Les transitions système inscrivaient correctement
  `APPEARED` / `REPEATED` / `REACTIVATED` — « seules les actions OPÉRATEUR, les
  seules imputables à une personne, perdaient leur cause ».
- Le motif d'inhibition est **obligatoire** (`shelve` sans commentaire lève).

---

## 18. `src/operations/workflows.py` — 326 lignes — **lu intégralement**

Registre SQLite des interventions. Même rigueur que `alarms.py` : WAL, clés
étrangères, `BEGIN IMMEDIATE` avec *rollback*, journal séparé, verrouillage
optimiste par `version` sur les étapes, et un garde-fou de sécurité réel :

```python
if status == "COMPLETED" and step["dangerous"]:
    # refuse si une étape précédente reste ouverte
    # refuse si aucun commentaire de contrôle n'est fourni
```

Une étape dangereuse — consignation, vidange, ouverture de couvercle — ne peut
donc pas être cochée avant ses prérequis, ni sans trace écrite.

Correction documentée : l'état de l'intervention était déduit de **la dernière
étape touchée** et non de l'ensemble. Bloquer l'étape A puis compléter l'étape B
repassait l'intervention « en cours » alors que A restait bloquée. Le
commentaire tranche : « sur un bordereau qui trace une consignation, un blocage
qui cesse de se voir est une régression de sécurité, pas d'affichage ».

### WF-1 — `complete()` n'a pas de garde d'état terminal

`update_step` refuse toute modification sur une intervention terminale :

```python
if workflow["status"] in {"COMPLETED", "CANCELLED"}:
    raise ValueError("Workflow terminal: modification interdite")
```

**`complete()` ne fait pas cette vérification.** Elle contrôle l'existence du
workflow, compte les étapes ouvertes — zéro sur un workflow déjà clos — puis
écrit :

```sql
UPDATE workflows SET status='COMPLETED', executed_at=?,
    signed_by=?, signed_at=?, proof_ref=?, updated_at=? WHERE id=?
```

Un second appel sur une intervention déjà clôturée **réussit** et **remplace la
signature, la date de clôture et la référence de preuve**. Sur un registre dont
la raison d'être est la traçabilité, la signature de clôture peut donc être
silencieusement réécrite par n'importe quel détenteur du rôle.

Le journal `workflow_history` conserve les deux événements `COMPLETED`, donc la
trace n'est pas perdue — mais l'en-tête, c'est-à-dire ce que la liste affiche,
porte la dernière signature.

| # | Constat | Gravité |
|---|---|---|
| WF-1 | Garde présent sur `update_step`, absent sur `complete`. **Sixième occurrence** du motif « appliqué à un exemplaire, pas à son jumeau ». Une ligne suffit à corriger. | **haute** |

### WF-2 — `CANCELLED` existe partout sauf dans le code qui le pose

`CANCELLED` figure dans `WORKFLOW_STATES`, dans la contrainte `CHECK` du
schéma, et dans le garde d'état terminal de `update_step`. **Aucune méthode ne
l'attribue jamais.**

Conséquence, symétrique de AL-3 : une intervention devenue sans objet ne peut
être ni annulée, ni clôturée — `complete()` exige que toutes les étapes soient
`COMPLETED` ou `NOT_APPLICABLE`. Elle reste indéfiniment `PLANNED` ou
`IN_PROGRESS` dans la liste.

Il existe un contournement — passer chaque étape en `NOT_APPLICABLE` puis
clôturer — mais il produit une intervention « terminée » là où elle a été
abandonnée. Ce n'est pas la même information.

### WF-3 — `WORKFLOW_STATES` est déclaré et jamais utilisé

Une seule occurrence dans tout le dépôt : sa propre définition. La liste
autoritaire est celle de la contrainte `CHECK` du schéma SQL, qui la duplique.
`STEP_STATES`, lui, est bien utilisé (`update_step`, l. 150).

| # | Constat | Gravité |
|---|---|---|
| WF-3 | Constante morte doublant une contrainte SQL. Deux sources pour la même énumération, dont une inerte. | mineure |

---

## 19. `src/security/auth.py` — 300 lignes — **lu intégralement**

**Aucun défaut trouvé.** C'est le fichier le plus solide du dépôt avec
`knowledge.py`, et le seul sur lequel je n'ai rien à redire.

Ce qu'il fait correctement, point par point :

- **La tentative est comptée AVANT la vérification.** Le compteur n'était
  incrémenté qu'en cas d'échec, dans un second bloc verrouillé, **après** une
  dérivation PBKDF2 de 600 000 itérations. Entre la lecture du compteur et son
  incrément, toutes les tentatives concurrentes voyaient la même valeur : *il
  suffisait de lancer les requêtes en parallèle plutôt qu'en série pour que la
  limite de cinq essais n'en arrête aucune.* C'est le contournement de limitation
  que j'avais mesuré plus tôt dans cette mission (20/20 puis 5/20).
- **Empreinte leurre** (`_decoy_hash`) : la dérivation PBKDF2 est menée même
  pour une adresse inconnue, sinon le temps de réponse révélerait quelles
  adresses sont enregistrées. Calculée une seule fois, à la première tentative
  échouée.
- **`_purger` borne deux structures qui croissaient sans limite**, toutes deux
  alimentées par une valeur que l'appelant choisit : `_attempts` créait une file
  par adresse cliente, supprimée seulement par une connexion réussie ; une
  session abandonnée en fin de quart n'était jamais libérée.
- **`hmac.compare_digest`** pour la comparaison d'empreintes.
- **Le jeton CSRF était remplacé hors verrou**, pendant qu'une requête
  concurrente pouvait le lire pour le comparer : la rotation faisait échouer
  des requêtes légitimes.
- **`rotate()` ne prolonge pas l'expiration absolue** — `created_at` est
  conservé.
- `password_hash: str | None = None` plutôt que `""`, pour que *bandit* B107 ne
  signale pas un faux positif de mot de passe codé en dur. Le commentaire note
  que `None` dit mieux ce que le code veut dire.

---

## 20. `src/security/registry.py` — 362 lignes — **lu intégralement**

Registre JSON par technicien, hors dépôt. L'argumentaire est juste : un secret
d'équipe « circule, ne se révoque pas individuellement, et le journal d'audit ne
peut plus dire qui s'est réellement connecté » — or l'adresse de session
**devient le destinataire des alertes critiques**.

### Corrections documentées, toutes vérifiables

- **`load()` ne validait pas ce que `add()` valide.** Trois conséquences
  chiffrées dans le commentaire, dont celle-ci : *une empreinte vide laissait
  l'adresse dans l'allowlist alors qu'`AuthManager` retire les empreintes vides
  de `user_hashes`. L'authentification retombait donc sur
  `AUTH_PASSWORD_HASH` : ce compte devenait ouvrable avec le **secret
  partagé**, précisément ce que le registre existe pour supprimer.*
- **Les droits étaient posés sur la cible APRÈS `replace()`** : entre l'écriture
  du temporaire et le renommage, un fichier contenant toutes les empreintes
  existait avec les droits par défaut du processus. Ils sont maintenant posés à
  l'`os.open` du temporaire, avec `fsync` avant publication.
- **Publication atomique** de `self._operators` : remplir le dictionnaire en
  place exposait un registre partiellement chargé à un rechargement concurrent.

### SEC-1 — la publication atomique n'a pas été étendue aux mutateurs

Le commentaire de `load()` (l. 169-171) énonce la règle :

> Les accesseurs de lecture ne prennent pas le verrou ; remplir le dictionnaire
> **en place** exposait un registre partiellement chargé.

`load()` a été corrigé — il construit `charges` puis rebinde. Mais `add()`,
`remove()` et `set_password()` mutent toujours **en place** :

```python
self._operators[normalized] = operator     # add
del self._operators[normalized]            # remove
```

Un lecteur sans verrou qui itère au même instant — `alert_recipients()`,
`listing()`, `roles()`, `password_hashes()` parcourent tous
`self._operators.values()` — lèverait `RuntimeError: dictionary changed size
during iteration`.

**Portée réelle : nulle en l'état.** Les trois mutateurs ne sont appelés que
par `scripts/manage_operators.py`, un **processus distinct** du service. L'API
ne fait que `load_registry()` au démarrage puis des lectures. Mutateurs et
lecteurs ne coexistent donc jamais dans le même interpréteur.

| # | Constat | Gravité |
|---|---|---|
| SEC-1 | Défaut structurel non atteignable dans le déploiement actuel, mais la règle énoncée n'est appliquée qu'à un des quatre points de mutation. **Septième occurrence** du motif. Il devient atteignable dès qu'une route d'administration exposerait `add`/`remove`. | mineure |

---

## 21. `src/realtime/replay.py` — 430 lignes — **lu intégralement**

Le rejeu fait défiler les 10 180 heures **réelles** plutôt que des données
synthétiques : « simuler serait plus simple, et sans valeur : on ne prouverait
que la capacité du système à retrouver des anomalies qu'on y a soi-même
placées ». Et la contrainte de causalité est explicite : « à l'instant *t*,
seule la fenêtre [début, *t*] est transmise à la détection ».

### La correction la plus frappante du dépôt

> Un unique horodatage atteint la sévérité critique en marche établie : le
> **2 octobre 2024 à 18 h**, sortie acide à 72,15 °C, **position 6 610** dans
> la série. 6 610 n'est pas multiple de trois.

Avec `analyze_every=3` — la valeur par défaut du dépôt — cet instant n'était
**jamais analysé**. Pas de rouge sur le jumeau, pas d'alarme ouverte, pas
d'escalade. *« Le seul événement critique de quatorze mois disparaissait par
une règle de performance. »*

`_instants_incontournables()` calcule une fois, vectoriellement, l'ensemble des
horodatages franchissant un seuil du référentiel ; ils sont analysés quelle que
soit leur position. Le filtre retient des **horodatages et non des positions**,
parce que le rejeu peut démarrer au milieu de la série.

### Deux autres corrections documentées

- **Le pas d'allègement entrait dans la temporisation.** Le délai valait
  `analyze_every / speed` appliqué à chaque heure de process : avec
  `REPLAY_SPEED=120` et `REPLAY_STEP=3`, le rejeu défilait à **40 h/s pendant
  que l'API publiait `speed_hours_per_second: 120`**. Facteur trois sur le seul
  réglage que l'exploitant manipule.
- **`run_sync` sautait les instants incontournables** : la garantie était
  affirmée dans la boucle threadée et absente du chemin qu'empruntent les tests
  et les scripts hors ligne.
- L'exemple de la *docstring* disait « 24 secondes » pour une vitesse de 60 h/s
  — soixante fois faux, et contredisant à la fois l'unité, le nom du champ
  publié et le code. « Trois énoncés pour un seul réglage, dont deux faux. »

`_emit` publie sous verrou puis appelle les abonnés **hors verrou**, et isole
chaque abonné dans son `try` : un registre d'alarmes en erreur n'interrompt pas
le rejeu.

---

## 22. `src/formatting.py` — 165 lignes — **lu intégralement**

Module de mise en forme française, créé pour une raison qu'il énonce
clairement :

> Corriger les occurrences une par une ne tient pas : **la suivante
> reviendra**. La conversion est donc centralisée ici, et un test parcourt les
> sorties du système pour vérifier qu'aucun nombre n'échappe à la règle.

Six fonctions, toutes utilisées : `nombre` (10 appels), `pourcent` (8),
`heures` (5), `unite` (2), `duree_pas` (2), `sans_accents` (1 — le contrôle V8).

Conventions correctes : virgule décimale, espace insécable **étroite**
(U+202F) pour les milliers, espace insécable ordinaire (U+00A0) avant l'unité
« pour qu'un retour à la ligne ne sépare jamais un nombre de son unité ».

### FMT-1 — j'ai dupliqué ce module dans `redaction.py`

Le fichier que j'ai écrit pendant cette mission ne l'importe pas
(`grep "from src.formatting"` → **0**) et réimplémente sa fonction principale :

```python
# src/notifications/redaction.py — ma version
def _nombre(valeur, decimales=0, defaut="—"):
    brut = f"{float(valeur):,.{decimales}f}"
    entier, _, decimal = brut.partition(".")
    entier = entier.replace(",", " ")
    return f"{entier},{decimal}" if decimal else entier

# src/formatting.py — l'original, U+202F identique
def nombre(valeur, decimales=1):
    brut = f"{x:,.{decimales}f}"
    return brut.replace(",", FINE).replace(".", ",")
```

Même conversion, même séparateur, deux implémentations. C'est exactement ce que
le module existe pour empêcher, et je l'ai fait en écrivant un rapport dont
l'un des reproches était… la mise en forme anglaise des nombres.

| # | Constat | Gravité |
|---|---|---|
| FMT-1 | **Huitième occurrence du motif de duplication, et la mienne.** `redaction.py` doit importer `nombre`, `pourcent` et `unite` au lieu de les réécrire. Un seul détail justifie une adaptation : mon `_nombre` renvoie un repli configurable et refuse les booléens. | moyenne |

---

## 23. `src/governance/lineage.py` — 239 lignes — **lu intégralement**

Traçabilité et portes d'intégrité. **Aucun défaut trouvé.** Le fichier est
court, dense, et chacune de ses vérifications a une raison d'être.

### Ce qui rend ce fichier remarquable

`validate_model_manifest` ne fait pas confiance au manifeste qu'il lit :

```python
failed = list(manifest["validation"]["failed_mandatory_gates"])
recomputed = failed_mandatory_gates(manifest["validation"]["results"])
if sorted(failed) != recomputed:
    raise ManifestValidationError("résumé des gates incohérent")
```

Le résumé publié est **recalculé depuis les résultats bruts** et comparé. Un
manifeste édité à la main pour effacer ses échecs est donc rejeté — c'est
exactement la discipline que le Judge applique aux décisions de l'agent,
transposée aux artefacts.

`failed_mandatory_gates` traite une porte **absente** comme échouée
(`by_name.get(gate, False)`), ce que sa *docstring* énonce : « jamais seulement
celles listées ». Retirer une porte du manifeste ne la fait pas disparaître.

L'égalité runtime est **exacte** sur la version de Python **et** sur celle des
six paquets qui influencent l'inférence. C'est strict, et c'est la raison
d'être de `make release-runtime` : produire l'artefact **dans** l'image
d'exécution, faute de quoi il ne pourra jamais être promu.

Enfin, `build_manifest` fixe le statut initial à `candidate` quoi qu'il
arrive : « la création d'un artefact n'est jamais une promotion ».

### État mesuré de l'artefact courant

```
statut    : candidate
gates KO  : labels_gmao, redondance_features,
            stabilite_hors_periode, validation_externe
```

Quatre portes obligatoires sur cinq échouent. Deux d'entre elles —
`labels_gmao` et `validation_externe` — **ne peuvent pas passer** : aucun
historique de pannes étiqueté n'existe pour cet équipement. La promotion est
donc structurellement impossible, et le système le dit plutôt que de le
contourner. C'est cohérent avec `AUTH_PROVIDER=oidc` exigé en production et non
intégré : **le projet refuse de se déclarer déployable.**

### LIN-1 — `validated_offline` n'est jamais attribué

Sur les six statuts de `PROMOTION_STATUSES`, `validated_offline` n'apparaît
qu'une fois dans tout le code : **sa propre déclaration**. `rejected` également.
Ni `promote_model.py` ni aucun autre module ne les pose.

| # | Constat | Gravité |
|---|---|---|
| LIN-1 | Deux états de cycle de vie déclarés et inatteignables. Même forme que `CANCELLED` dans `workflows.py` (WF-2) : l'énumération décrit un cycle plus riche que ce que le code sait produire. Sans conséquence fonctionnelle — ils ne figurent pas dans `RUNTIME_STATUSES` — mais un lecteur du manifeste croit à un cycle en six états. | mineure |

---

## 24. `src/governance/model_validation.py` — 515 lignes — **lu intégralement**

**Aucun défaut trouvé.** Quatrième fichier dans ce cas.

C'est aussi le fichier qui contient les **deux aveux les plus sévères** du
dépôt sur lui-même, tous deux corrigés.

### « Les deux portes qui ne pouvaient pas échouer »

> `causalite_temporelle` était un littéral `True` : aucune mesure, aucune
> possibilité d'échec. Elle était de surcroît **fausse**, le classement d'état
> procédé lisant l'instant suivant.
>
> `redondance_features` ne comptait que les redondances **internes** à la
> matrice du modèle, en ignorant `shadow_redundancy` — c'est-à-dire exactement
> la variable que l'audit avait été écrit pour exposer. Elle publiait « 0 paire
> redondante » **deux cents lignes en dessous d'un −0,94 mesuré**.

Deux portes de déploiement structurellement incapables de refuser quoi que ce
soit. Aujourd'hui : `causalite_temporelle` passe pour de bon,
`redondance_features` **échoue** — et le commentaire conclut « c'est le
résultat correct ».

### Le contrôle de causalité qui ne comparait rien

```python
tronque = features.loc[:coupe, colonnes]
complet = features.loc[:coupe, colonnes]     # ← la MÊME expression
```

Deux fois la même ligne, puis `complet` supprimé sans jamais être comparé. La
seule vérification effective était qu'une ligne n'était pas entièrement vide.

La *docstring* d'origine reconnaissait pourtant qu'une inspection statique des
`shift()` se contourne par un `rolling(center=True)`, un `transform("sum")` ou
un `bfill()`, et que **seule la reconstruction peut échouer**. Elle décrivait
le bon contrôle et en exécutait un autre.

La chaîne est désormais réellement reconstruite sur l'histoire tronquée, à
**trois découpes** (40, 60, 80 %), références figées pour que la comparaison
porte sur le calcul et non sur un réajustement légitime. L'état de marche — là
où vivait le `shift(-1)` historique — est reclassé et comparé séparément.

L'inspection statique complémentaire couvre **toute la chaîne** et non trois
fichiers, et inclut `transform("sum")` parce que la version historique du
détecteur de gel mesurait la longueur totale d'un palier, donc son extension
dans le futur.

### Un audit de redondance qui se validait lui-même

`_feature_audit` calculait la colinéarité sur la seule matrice du modèle, d'où
`control_deviation` est absente. Il concluait « 0 paire redondante » **en ayant
justement écarté la variable qui révèle la redondance**. Les variables de
contrôle hors modèle sont désormais confrontées séparément.

### Le backtest

Quatre folds à fenêtre croissante sur calendrier horaire, `gap` de 24 h, et à
chaque fold : **réajustement des trois références thermiques, reconstruction
causale des features, réajustement du scaler, de l'Isolation Forest et du
seuil**. Rien n'est réutilisé du corpus complet.

Et la revendication scientifique est explicite :

> « non démontrable avec le corpus disponible ; **aucune AUC, précision, rappel
> ou réduction de panne revendiquée** »

Cinq limitations sont publiées, dont « le modèle thermique reconstruit un proxy
calculé ; son R² n'est pas une preuve d'état » et « le rejeu historique n'est
pas une connexion DCS/PI temps réel ».

C'est, avec `lineage.py`, ce qui donne au projet sa crédibilité de gouvernance :
**le système mesure ses propres portes, en échoue quatre sur cinq, et le
publie.**

---

## 25. `src/governance/fouling_injection.py` — 466 lignes — **lu intégralement**

**Aucun défaut trouvé.** Cinquième fichier dans ce cas.

### Le raisonnement qui justifie le banc

> Un audit a relevé que la règle d'encrassement ne s'était **jamais** déclenchée
> sur les quatorze mois disponibles, et que le projet présentait ce zéro comme
> un résultat. C'est une inversion de la charge de la preuve : sans anomalie
> étiquetée, on ne peut pas distinguer
> **(1)** il n'y a pas eu d'encrassement, **(2)** le détecteur est incapable de
> se déclencher, **(3)** l'indicateur ne mesure pas ce qu'on croit.

Le banc tranche entre (1) et (2). C'est la seule métrique de détection
défendable en l'absence d'historique GMAO.

### Le modèle d'injection est physique, pas cosmétique

```
UA'       = UA · (1 − sévérité · avancement)
ε'        = 1 − exp(−UA' / C_acide)
T_sortie' = T_entrée − ε' · (T_entrée − T_eau_de_mer)
```

L'injection **ne bricole aucune température** : elle dégrade le coefficient
d'échange et laisse la physique produire les températures qui en résultent.
Le commentaire en donne la raison exacte : « c'est la seule construction qui
garantisse que le détecteur ne reconnaisse pas la faute par un **artefact de
fabrication** ».

### Trois précautions méthodologiques réelles

- **`_quiet_start`** cherche une fenêtre où le témoin ne déclenche rien avant
  d'y poser la rampe. Sans elle, la « détection » n'est attribuable à rien —
  et le commentaire l'assume : « c'est le défaut qu'avait la première version
  de ce banc : **elle annonçait 100 % de détection à 0 % d'avancement** ».
- **Détection attribuable** : `fouling & ~control_aligned` — le déclenchement
  doit être absent du témoin au même instant.
- **`useful_detection_rate`** plutôt que le taux brut : « une dérive finit
  toujours par dépasser le seuil. Ce qui compte est l'**avancement** auquel elle
  est vue. Détecter à 90 % d'avancement revient à constater la dégradation, pas
  à l'anticiper. »

### La limitation que peu de projets publieraient

> L'injection dégrade UA à débit d'eau de mer inchangé. La régulation réelle
> ouvrirait la vanne pour compenser, ce que le banc ne simule pas faute de
> mesure côté eau de mer : **l'avancement à la détection publié ici est donc
> plus favorable que celui qu'on observerait en marche.**

Le projet publie que sa propre métrique de détection est **optimiste**, et
explique pourquoi. C'est la conséquence directe de l'aveu de `thermal.py` sur
le UA apparent — la chaîne de raisonnement est tenue de bout en bout.

### Cohérence prédicat / règle

`_fouling_hours` évalue la condition de `_rule_thermal_drift` directement,
pour ne pas appeler `analyze` sur 8 800 instants. Le risque de divergence est
identifié et verrouillé par `test_le_predicat_du_banc_equivaut_a_la_regle` — et
il s'était **déjà réalisé** : le prédicat comptait 72 **lignes** quand la règle
compte 72 **heures**, « et ce prédicat alimente aussi la grille de sensibilité,
donc un chiffre publié ».

C'est le seul endroit du dépôt où une duplication assumée est **explicitement
verrouillée par un test d'équivalence**. Comparé aux huit occurrences du motif
« corrigé à un endroit, pas à l'autre », c'est la bonne façon de faire — et
elle existe déjà dans le projet.

---

## 26. `src/governance/sensitivity.py` — 264 lignes — **lu intégralement**

**Aucun défaut trouvé.** Sixième fichier dans ce cas. Et c'est le fichier qui
porte, de l'aveu même du projet, **le résultat le plus gênant de tout le
travail**.

### Le raisonnement

> Un paramètre non justifié n'est pas une faute en soi. Un paramètre non
> justifié **et dont on ignore l'influence** en est une.

Deux paramètres décident de presque tout : `contamination = 0.02` fixe le
volume d'alertes, et « les 40 % initiaux » définissent ce qui est *normal*.
Aucun des deux n'a de justification physique, et le module le dit sans détour :
« valeur usuelle par défaut d'Isolation Forest ».

### SEN — le constat que le rapport technique doit reprendre

```
RÉSULTAT LE PLUS IMPORTANT DE CETTE ANALYSE, ET LE PLUS GÊNANT.
La part d'heures de marche que le système déclarerait en encrassement varie
de X % à Y % selon la seule fenêtre retenue comme référence.

Le « zéro heure d'encrassement sur quatorze mois » annoncé ailleurs dans ce
projet est celui de la fenêtre à 40 % : ce n'est pas un constat sur
l'équipement, c'est une conséquence de ce choix.
```

Le mécanisme est expliqué : une référence précoce apprend un coefficient
d'échange bas — eau de mer froide en hiver, vanne peu ouverte — et lit ensuite
la remontée saisonnière comme une dérive. Une référence plus longue couvre
plusieurs saisons et l'absorbe.

Conséquence opérationnelle, énoncée par le module lui-même :

> **AUCUN chiffre d'encrassement n'est publiable sans la fenêtre qui l'a
> produit.** La fenêtre de 40 % est retenue parce qu'elle couvre un cycle
> saisonnier complet là où celle de 25 % s'arrête en mai, et ce choix est
> publié ici **pour être contesté, pas pour être cru**.

**Cela conditionne D1.** Tout énoncé du rapport technique sur l'encrassement
doit porter sa fenêtre de référence. C'est une exigence de fond, pas de forme.

### Une correction du même genre que celles déjà vues

La version précédente ne mesurait que le résidu de température d'entrée — que
le projet classe lui-même en « contexte » — puis **concluait sur le coefficient
d'échange, qu'elle n'observait jamais**. Elle affirmait qu'aucune fenêtre ne
faisait apparaître de perte de UA. « C'était faux, et la grille de cette
fonction suffisait à le montrer : sur la fenêtre à 25 %, la règle
d'encrassement se déclenche sur **plus de la moitié du corpus**. »

### Bon réflexe de conception

`reference_period_sensitivity` **réutilise** `FoulingInjectionBench._fouling_hours`
au lieu de réécrire le prédicat : « un prédicat recopié dérive de son original ».
Deuxième occurrence de la bonne pratique dans ce dossier.

### SEN-1 — la sensibilité n'est pas persistée

`reports/` contient `model_validation.json`, `project_metrics.json`,
`judge_eval_*` — **mais aucun artefact de sensibilité**. Le rapport n'existe
qu'à la demande, via `/api/sensitivity`, recalculé à chaque appel (quatre
reconstructions complètes de features).

| # | Constat | Gravité |
|---|---|---|
| SEN-1 | Le résultat que le module qualifie lui-même de « plus important » n'est figé dans aucun artefact versionné. Il ne peut donc être ni cité avec une date, ni comparé d'une version à l'autre, ni vérifié par un test comme le sont les métriques de `project_metrics.json`. | moyenne |

---

## 27. `src/governance/judge_eval.py` — 699 lignes — **lu intégralement**

Ce fichier contient l'auto-critique la plus aboutie du dépôt, et elle porte sur
la métrique que le projet mettrait en avant devant un jury.

### L'aveu central : ce banc n'est pas une évaluation

> Chaque piège du catalogue porte un champ `expected_issue` qui est **exactement
> le code d'anomalie implémenté par le Judge**. On fabrique donc une faute
> conçue pour déclencher le contrôle V1, puis on mesure que V1 la détecte.
> C'est un test de **NON-RÉGRESSION**, pas une évaluation : un taux de 97 % dit
> que les contrôles fonctionnent toujours, il ne dit rien de ce que le Judge
> ferait face à une faute imprévue. **Le présenter comme une validation serait
> une sur-vente.**

D'où l'ajout de mutations **non ciblées**, dont le taux — nettement inférieur —
est « la mesure honnête de la généralisation ».

### Deux tours de purge des mutations « aveugles » qui ne l'étaient pas

**Premier tour — 3 des 5 mutations dites de généralisation ciblaient un
contrôle par construction :**

| Mutation retirée | Pourquoi elle était garantie de déclencher |
|---|---|
| `perturb_values` | multipliait chaque valeur par 1,03 à 1,25, alors que V1 tolère **1 %** |
| `swap_severity` | déclenche V2 **par définition** |
| `shuffle_modes` | tirait dans un ensemble contenant deux modes non observables ⇒ V3 |

> Le « chiffre de généralisation » était donc, **pour trois cinquièmes, un test
> de non-régression déguisé.**

**Second tour — deux de plus :**

- `drop_measurements` vidait `cited_values` — soit exactement le piège conçu
  `_m_no_numbers` ⇒ `NO_QUANTITATIVE_EVIDENCE` par construction.
- `neighbour_values` affirmait qu'« aucun contrôle n'interroge l'instant d'où
  proviennent les chiffres », alors que V1 les confronte aux mesures
  **recalculées à l'instant jugé**. Et son code appliquait en réalité un bruit
  de ±0,5 %, **pas une substitution** : elle ne faisait même pas ce que son nom
  annonçait.

**Bilan : les cinq mutations « non ciblées » d'origine l'étaient toutes.** La
métrique de généralisation mesurait la non-régression.

### Les cinq mutations retenues

Elles portent sur des propriétés qu'**aucun des huit contrôles ne lit** :

1. rôle des deux textes (diagnostic et raisonnement intervertis — les deux
   restent vrais, chiffres compris, seul leur rôle change) ;
2. complétude du raisonnement (tronqué) ;
3. adéquation de l'action au problème (action valide, mais d'un autre mode) ;
4. service destinataire du bon de travail ;
5. check-list rattachée à l'intervention.

`test_aucune_mutation_non_ciblee_ne_vise_un_controle` verrouille la propriété
— et le module note que ce test était « **longtemps annoncé par ce module** »
avant d'exister. C'est la **troisième fois** que je rencontre un test cité dans
un commentaire et absent du dépôt (après celui de `main.py` sur les handlers, et
le nom inexistant qu'il mentionne lui-même).

### Un détail de conception juste

`TrapCase.min_penalty` : certaines fautes sont réelles mais mineures. Pour la
sur-confiance, « on exige que le Judge la détecte et **la facture**, pas qu'il
rejette tout le diagnostic ». Le critère est alors une **perte de points par
rapport à la décision saine**, pas une note absolue. Et `applies_when` évite
d'évaluer la sous-estimation sur une situation déjà anodine.

### JE-1 — le rapport de soutenance omet le seul chiffre honnête

Valeurs **mesurées** dans `reports/judge_eval_summary.json` :

| Mesure | Valeur | Ce qu'elle vaut |
|---|---|---|
| `trap_detection_rate` (pièges conçus) | **95,8 %** | non-régression |
| `separation` (saines / pièges conçus) | **4,13 pts** | non-régression |
| `blind_mutations.flagged_rate` | **10,0 %** | **généralisation** |
| `blind_mutations.penalised_rate` | **1,7 %** | **généralisation** |
| `blind_mutations.score_mean` | **9,89 / 10** | **généralisation** |
| `clean_score_mean` | 9,91 / 10 | référence |

Sur une faute **non anticipée**, le Judge lève une réserve dans **10 % des
cas**, la facture dans **1,7 %**, et la décision fautive obtient **9,89/10**
contre 9,91 pour une décision saine.

**Séparation réelle sur mutations non ciblées : 0,02 point.** Contre les 4,13
affichés.

Or `EvalResult.report()` — dont la *docstring* précise « rapport texte lisible,
**destiné au mémoire et à la soutenance** » — imprime `n_clean`,
`clean_score_mean`, le taux de validation, les faux positifs, `n_traps`,
`trap_score_mean`, `trap_detection_rate`, `trap_missed`, `separation`, le
tableau par piège et les alertes. **`blind_mutations` n'y figure pas.**

Vérifié sur l'artefact réellement produit :

```
$ grep -c "non ciblee" reports/judge_eval_traps.csv
0
```

Les mutations non ciblées sont exclues du tableau (`by_trap` filtre
`designed`), absentes du CSV, absentes du rapport texte. **Elles n'existent que
dans le JSON.**

Aucun seuil d'alerte ne porte sur elles non plus : `verdict_warnings` ne teste
que `traps_raw`. Un taux de généralisation de 0 % ne déclencherait rien.

**CORRECTION APRÈS LECTURE DU FRONT — le constat est plus étroit que je ne
l'avais écrit.** J'avais conclu que le chiffre honnête était masqué partout.
Vérification faite sur `dashboard.html` et `app.js` : **l'interface l'affiche,
et le met en premier.**

`dashboard.html` l. 398-416 porte ce commentaire :

> LE CHIFFRE MIS EN AVANT EST CELUI QUI SE DÉFEND. Un « 100,0 % » en corps 72
> sur un banc dont les pièges ont été écrits contre les contrôles qui les
> attrapent est **la cible la plus facile d'une soutenance**. […] **Le chiffre
> à lire en premier est celui des fautes d'un genre non anticipé.**

Et `app.js` l. 1476 le rend effectivement, en **tête** du bloc, avec une alerte
visuelle quand il passe sous 50 % — donc active à 10 % :

```js
<strong data-alert="${(aveugle.flagged_rate ?? 1) < 0.5}">
  ${fmt(aveugle.flagged_rate * 100, 0)} %
</strong>fautes d'un genre non anticipé
<span><strong>${fmt(s.trap_detection_rate * 100, 0)} %</strong>
  pièges conçus (non-régression)</span>
```

Le poste est donc **honnête, et plus honnête que je ne l'avais jugé** : il
affiche 10 % avant 95,8 %, et signale le premier comme une alerte.

**Ce qui reste vrai, et qui reste un défaut :**

| Support | Taux non ciblé | Verdict |
|---|---|---|
| Interface `Contrôle` | affiché **en premier**, marqué en alerte | correct |
| `reports/judge_eval_summary.json` | présent | correct |
| `EvalResult.report()` → `judge_eval_report.txt` | **absent** | défaut |
| `judge_eval_traps.csv` | **absent** (`grep -c` → 0) | défaut |
| `docs/rapport_technique.md` | qualitatif seulement, **aucun chiffre** | défaut |

| # | Constat | Gravité |
|---|---|---|
| JE-1 | Le rapport texte, dont la *docstring* dit « destiné **au mémoire et à la soutenance** », omet le chiffre que le module et l'interface désignent tous deux comme le seul à lire en premier. Le CSV l'omet aussi. **Correction : trois lignes dans `report()`, et les mutations non ciblées conservées dans le CSV.** | moyenne |

**Conséquence pour D1 :** `docs/rapport_technique.md` dit la vérité
qualitativement — « la mesure de généralisation est distincte, plus basse » —
sans jamais publier 10 %, 1,7 % ni 9,89. Il doit citer les deux séries côte à
côte, comme le fait déjà l'interface.

### Note sur mes propres erreurs d'analyse

C'est la **troisième fois** dans cette lecture que je surestime un constat, et
le motif est constant : je cherche un nom de champ, j'obtiens zéro, et je
conclus à l'absence — sans vérifier que la donnée est **renommée** en transit
(J-1, `flagged_issues` → `judge_issues`) ou **rendue sous un autre identifiant**
(JE-1, `blind_mutations` → `benchMeta`). Les trois corrections :

| Constat | Ma conclusion initiale | Après vérification |
|---|---|---|
| Décompte des routes | « 46 mesurées contre 45 annoncées » | les trois chiffres sont justes, ils comptent des choses différentes |
| J-1 | « le contrôleur est muet à l'écran » | note, accord et réserves traduites **sont** affichés |
| JE-1 | « le chiffre honnête est masqué partout » | l'interface l'affiche **en premier**, seuls les exports l'omettent |

Aucun grep n'établit une absence tant qu'on n'a pas suivi la donnée jusqu'à son
point de rendu.

---

## 29. `api/dashboard.html` — 545 lignes — **lu intégralement**

Trois vues, structure ARIA correcte (`role="tablist"`, `aria-controls`,
`aria-selected`, `tabindex` géré), écran d'attente pendant la construction de
la chaîne, panneau d'identification, `dialog` modale, zone de toasts.

Corrections documentées dans le balisage lui-même :

- L'onglet du navigateur restait vide (`data:,`) — « en soutenance, plusieurs
  onglets sont ouverts côte à côte : la marque est le seul repère ».
- Le poste **n'affichait rien** tant que le service ne répondait pas : « coque
  à opacité nulle, panneau masqué, aucun message. Or le service charge
  l'historique et entraîne le modèle au démarrage — toute ouverture pendant
  cette fenêtre tombait sur une page blanche ».
- Le verdict de sévérité était masqué sous 760 px, « la seule lecture qu'un
  agent de ronde consulte sur sa tablette ».
- La photographie porte sa **source documentaire** : « une photographie
  industrielle sans source est invérifiable […] elle vient du dossier de
  maintenance de CET équipement ».

### Confirmation de API-2 au niveau de l'interface

Le sélecteur « Signaux » (l. 251-258) offre six jeux de courbes :

```
thermal · titre · debit · duty · absorption · degrade
```

Aucune entrée pour le coefficient d'échange, la résistance d'encrassement ou
le résidu d'entrée. Et l'entrée `duty` est intitulée **« Performance observée /
attendue »** — c'est-à-dire `duty_kw` contre `duty_expected`, la paire dont
`e7301_features.py` démontre qu'elle retrouve sa propre définition.

Un exploitant qui cherche « la performance de l'échangeur » sélectionne donc
l'unique jeu que le projet déclare **sans valeur de preuve**, sous un intitulé
qui le désigne comme la performance.

### SEN est déjà appliqué ici

Le panneau d'encrassement (l. 438) énonce : « Avec la période de référence
retenue (**40 % initiaux**), la règle ne se déclenche sur aucun des quatorze
mois — voir l'analyse de sensibilité pour ce que donnent les autres fenêtres. »
Le commentaire précise que la formulation précédente « était vraie pour la
fenêtre retenue, et **fausse pour celle de 25 %** ».

L'interface applique donc la règle que le rapport technique doit encore
adopter.

### Ni `alarms` ni `workflows`

Confirmé sur les 545 lignes : aucune occurrence. Les trois vues sont Salle,
Intégrité, Contrôle.

---

## 30. `tests/` — 41 fichiers, 272 fonctions, 687 assertions

### Analyse systématique du motif « contrôle qui ne peut pas échouer »

Ce dépôt a produit ce défaut au moins cinq fois — porte `causalite_temporelle`
en littéral `True`, audit de redondance amputé de sa variable révélatrice,
seuil `WARNING` structurellement inatteignable, cinq mutations « aveugles »
toutes ciblées, et mon propre banc 3D. J'ai donc balayé la suite par AST.

| Recherche | Résultat |
|---|---|
| Fonctions de test | **272** |
| Assertions `assert` | **687** |
| Assertions littérales toujours vraies | **0** |
| Assertions tautologiques `x == x` | **0** |
| Tests sans `assert` | 26 |
| …dont sans `pytest.raises`/`warns`/`approx`/aide de vérification | **0** |

Les 26 tests sans `assert` vérifient tous un **refus** — `pytest.raises` —
comme leurs noms l'annoncent : `test_tag_inconnu_leve_une_erreur`,
`test_detecteur_non_ajuste_refuse_de_scorer`,
`test_candidat_est_refuse_meme_si_fichier_lisible`.

**Aucun test creux détecté par cette analyse.** C'est un résultat solide, et il
contraste avec l'historique du code : les contrôles vacants ont été trouvés
dans le code de gouvernance, pas dans la suite de tests.

Réserve de méthode : cette analyse détecte les tautologies **syntaxiques**.
Elle ne détecte pas un test qui exerce une réimplémentation plutôt que
l'original — précisément la faute que j'ai commise dans `twin_smoke.mjs`, et
qui n'est décelable que par lecture ou par mutation.

### `tests/conftest.py` — 113 lignes — **lu intégralement**

Fixtures de session : la chaîne complète est construite une fois, « les refaire
à chaque test rendrait la suite inutilisable et découragerait de la lancer ».
`sensitivity_report` et `fouling_bench_report` sont mémoïsés pour la même
raison — « une suite lente finit par ne plus être lancée ».

`os.environ.setdefault("AUTH_ENABLED", "false")` est posé **avant** l'import de
`src.config`, qui lit l'environnement à l'import. Nécessaire, et l'ordre est le
bon.

Confirme **M-2** : `feats, twin = build_features(...)` et la *docstring*
« Table de features et **jumeau thermique** ajusté ». Le vocabulaire répudié
survit dans les fixtures.

### `tests/test_documentation.py` — 166 lignes — **lu intégralement**

Ce fichier **automatise déjà l'essentiel de la tâche D2**, et il faut en tenir
compte dans le plan.

Quatre contrôles mécaniques sur les 17 documents Markdown plus le README :

| Test | Ce qu'il interdit |
|---|---|
| `test_aucun_endpoint_documente_n_a_disparu_de_l_api` | citer une route `/api/...` absente de `main.py` (résolution des paramètres `{...}` comprise) |
| `test_aucun_test_cite_par_la_documentation_n_est_absent` | citer un `test_*` qui n'existe pas |
| `test_aucun_script_ni_cible_make_documente_n_est_absent` | citer un `scripts/*` ou un `make *` inexistant |
| `test_aucun_montant_n_est_presente_comme_un_resultat` | publier un montant en MAD dans un tableau de résultats |

L'en-tête recense quatre dérives réellement survenues :

> - le rapport technique présentait un **modèle économique de 29 paramètres et
>   un solde annuel de 1,07 M MAD**, alors que la couche économique avait été
>   **retirée** du système et que deux tests interdisent son retour ;
> - il citait `test_le_gain_ne_vient_pas_dune_baisse_de_frequence` comme verrou
>   de son principe le plus important : **ce test n'a jamais existé** ;
> - le runbook demandait au technicien de consulter chaque jour
>   `/api/business/assumptions`, **un endpoint supprimé** ;
> - le README listait « énergie thermique évacuée en excès » parmi les
>   indicateurs produits, **quelques paragraphes avant d'expliquer que cette
>   formulation avait été retirée**.

> Une documentation fausse est pire qu'une documentation absente : **elle est
> lue, et elle est crue.**

C'est la **quatrième occurrence** du motif « test cité et inexistant » — et
elle est ici institutionnalisée : `ABSENCES_ASSUMEES` liste nommément le test
fantôme pour que la documentation puisse **expliquer** qu'il n'existe pas sans
faire échouer le contrôle. C'est la bonne réponse à ce motif.

**Conséquence pour D2 :** la vérification *référentielle* de la documentation
est déjà outillée et verrouillée en intégration continue. Ce qui reste à faire
relève du **fond** — la documentation décrit-elle correctement le système, avec
les bons chiffres et les bonnes réserves — et non des références mortes.

Le contrôle des montants est correctement borné : il interdit **le montant dans
un tableau** (`ligne.lstrip().startswith("|")`), pas le mot, « les sections qui
expliquent le retrait doivent pouvoir le nommer ».

### `tests/test_service_invariants.py` — 372 lignes — **lu intégralement**

Douze invariants vérifiés **par arbre syntaxique**, sans démarrer le service.
Le raisonnement est juste :

> Un handler déclaré `async def` sans jamais `await` fonctionne parfaitement en
> test unitaire et **gèle la boucle d'événements en exploitation**. Une réponse
> d'erreur renvoyée avant le bloc d'en-têtes répond correctement et **part sans
> politique de sécurité**. Un client sortant construit sans délai maximal
> **répond vite tant que le réseau va bien**.

Chacun des douze verrouille un défaut réellement survenu, déjà rencontré dans
cette lecture : handlers sur la boucle, refus 401/403/500 sans en-têtes,
validation de configuration tardive, client LLM sans `timeout`, pas
d'allègement dans la temporisation, `run_sync` ignorant les instants
incontournables, cache de scores survivant au ré-entraînement, `duree_pas`
non appelée, bancs frontend absents de la CI, libellés de transition d'alarme.

### Ce fichier a appris la leçon des contrôles vacants — et l'applique

Deux tests se prémunissent explicitement contre l'auto-satisfaction :

```python
# test_la_mise_en_forme_des_durees_est_centralisee
# Les COMMENTAIRES sont ecartes : ils citent l'ancienne expression pour
# expliquer le defaut, et une recherche naive retomberait dessus — le meme
# faux positif qu'un motif attrapant une docstring au lieu du code.
```

```python
# test_aucun_outil_de_qualite_declare_n_est_inerte
# On cherche une LIGNE DE DEPENDANCE, pas une mention. […] un simple `in`
# aurait passe meme apres suppression de la dependance — le controle se
# serait auto-satisfait sur sa propre explication.
```

C'est exactement la parade au motif que ce dépôt a produit cinq fois.

### Conception « refus par défaut »

`test_tout_handler_asynchrone_attend_reellement` affirme
`set(sans_await) <= tolerees` : **tout nouveau handler `async` sans `await`
échoue** tant qu'il n'est pas explicitement ajouté à la liste. La liste
`HANDLERS_CALCULANTS` du premier test est, elle, une liste d'autorisation —
mais le second la couvre. Les deux ensemble sont solides.

### CI-1 — `mypy` est déclaré, exécutable, et absent de l'intégration continue

État mesuré :

| Élément | État |
|---|---|
| `[tool.mypy]` dans `pyproject.toml` | présent |
| `mypy>=1.11` dans `requirements.txt` | présent (l. 46) |
| cible `make types` | présente (`Makefile` l. 23) |
| exécution par `.github/workflows/ci.yml` | **absente** |

L'invariant `test_aucun_outil_de_qualite_declare_n_est_inerte` est donc
satisfait — il exige une dépendance **et** une cible, pas une exécution en CI.
Et le `Makefile` qualifie la cible d'« informatif, non bloquant ».

| # | Constat | Gravité |
|---|---|---|
| CI-1 | Le typage statique est installé, configuré et invocable, mais rien ne le lance automatiquement. Ce n'est pas contradictoire avec l'invariant — c'est une décision à assumer explicitement : soit `make types` rejoint la CI en avertissement, soit le `[tool.mypy]` est retiré. En l'état, l'outil existe et personne ne sait s'il passe. | mineure |

### `tests/test_topology.py` — 109 lignes — **lu intégralement**

Dix tests sur le référentiel de topologie. Bonne couverture : existence des
capteurs situés, des modes cités par chaque pièce, des pièces et capteurs cités
par `finding_map`, rattachement correct des deux cas qui comptent (fuite de
tube, perte de régulation), et refus de désigner quoi que ce soit sur un code
inconnu.

`test_tous_les_codes_du_detecteur_sont_couverts` extrait par expression
régulière tous les `code="..."` du détecteur et vérifie qu'aucun n'échappe à
`finding_map` — un code émis sans rattachement « passerait inaperçu ».

`test_les_pieces_non_instrumentees_sont_declarees` verrouille le cas de l'anode :
`instrumented is False`, mode rattaché, criticité **112**. « La représentation
doit le dire, pas le taire. »

### T-2 précisé

`test_chaque_capteur_situe_existe_dans_le_registre` vérifie bien
`placement["attaches_to"] in domain.components`. Le champ est donc **gouverné,
validé et testé** — mais toujours **jamais lu par le front** (0 occurrence dans
`twin.js` et `app.js`). Ce n'est pas une donnée morte, c'est une donnée
**produite, garantie, et non consommée par celui qui en a besoin**.

### TOPO-1 — un test dépend du répertoire courant

```python
# tests/test_topology.py, l. 84
source = Path("src/models/detector.py").read_text(encoding="utf-8")
```

**Seul chemin relatif de toute la suite.** Les quatre autres fichiers qui lisent
des sources du dépôt utilisent tous la forme robuste :

```python
RACINE = Path(__file__).resolve().parents[1]
```

Vérification : `Path("src/models/detector.py").exists()` vaut `False` dès que
le répertoire courant n'est pas la racine du dépôt. Le test lève alors
`FileNotFoundError` — pas un échec d'assertion lisible, une erreur de collecte.

Il passe aujourd'hui parce que `pytest` est toujours lancé depuis la racine.
C'est la même classe de fragilité que le `--import-mode=importlib` rencontré
plus tôt dans cette mission : **une propriété tenue par l'habitude
d'invocation, pas par le code.**

| # | Constat | Gravité |
|---|---|---|
| TOPO-1 | Chemin relatif isolé dans une suite qui utilise partout ailleurs une racine résolue depuis `__file__`. Correction d'une ligne. | mineure |

### Aucun garde sur T-1

Aucun test de ce fichier n'examine le champ `anchor` ni la distance entre
capteurs voisins. Le défaut de recouvrement des étiquettes — six paires à moins
d'un mètre portant deux ancres identiques — n'est verrouillé par rien. Toute
correction de T-1 devra s'accompagner d'un test, faute de quoi le référentiel
pourra redériver.

### `tests/test_ingest.py` — 190 lignes — **lu intégralement**

Seize tests, tous adossés à des faits **avérés** du corpus réel : saturation de
`TI5303-4X` (> 4 000 événements), gel de `PHI5306X-3` (> 500), deux doublons
d'horodatage, présence des trois codes DCS `Bad` / `Configure` / `I/O Timeout`.

Le premier test porte sa propre correction :

> **CE TEST AFFIRMAIT LE CONTRAIRE DU COMPORTEMENT VOULU.** Il exigeait que
> TOUS les points d'un palier constant soient marqués, y compris les premières
> heures — c'est-à-dire **un marquage rétroactif**, décidé avec une information
> que le système n'a pas encore.

Il vérifie désormais la causalité elle-même : rien avant le seuil, tout après.

`test_valeurs_invalides_mises_a_nan_et_non_inventees` verrouille la règle
centrale du module : « combler un trou par la dernière valeur connue ferait
croire au modèle que la mesure existe. **C'est ainsi qu'un système déclare
"tout va bien" pendant sept mois de capteur mort.** »

Réserve mineure : `test_transitoire_autour_dun_arret` affirme dans sa
*docstring* que « les instants **encadrant** un arrêt doivent être marqués
TRANSIENT », mais son assertion accepte l'un **ou** l'autre côté
(`set(...) | set(...)`). C'est correct — la suppression du `shift(-1)` interdit
de marquer le côté *avant* l'arrêt — mais la *docstring* décrit une propriété
bilatérale que la causalité rend impossible.

### `tests/test_alarm_store.py` — 168 lignes — **lu intégralement**

Sept tests, dont un de **concurrence réelle** : vingt observations identiques
lancées sur huit fils doivent produire une seule alarme, vingt occurrences et
vingt lignes de journal. Bonne couverture du cycle ISA-18.2 : acquittement,
inhibition avec motif obligatoire, désinhibition, transition interdite,
répétition, réactivation, clôture refusée tant que l'alarme est active.

`test_shelved_ne_revient_pas_silencieusement_a_la_normale` verrouille le
comportement discuté en AL-2/AL-3.

### AL-1 renforcé — le défaut est **structurellement intestable**

L'aide de construction du fichier produit **toujours exactement une
constatation** :

```python
findings=[SimpleNamespace(code=finding)] if finding else []
```

Recherche sur toute la suite : **aucun test ne soumet une analyse portant
plusieurs constatations.** Or AL-1 ne se manifeste que dans ce cas — quand
`findings[0]` désigne le premier code par ordre d'exécution des règles plutôt
que le plus grave.

`test_deux_alarmes_independantes_et_retour_cible` teste bien deux clés
distinctes, mais en soumettant **deux analyses séparées**, une constatation
chacune. L'instabilité de la clé sous constatations concomitantes n'est donc
pas seulement non testée : **le harnais ne permet pas de l'exprimer.**

Détail annexe : les codes utilisés — `DUTY_LOW`, `TEMP_HIGH` — **n'existent ni
dans `detector.py` ni dans `topology.yaml`** (0 occurrence). Acceptable pour un
test unitaire, mais la suite ne confronte jamais le registre d'alarmes au
vocabulaire réel du détecteur.

| # | Constat | Gravité |
|---|---|---|
| AL-1 *(complément)* | Correction de AL-1 : il faudra **d'abord étendre l'aide de construction** pour accepter plusieurs constatations, sinon le test de non-régression sera impossible à écrire. | — |

### `tests/test_workflows.py` — 130 lignes — **lu intégralement**

**Trois tests seulement**, pour 326 lignes de registre. Ils couvrent la
persistance, le blocage d'une étape dangereuse dont les prérequis sont
incomplets, le verrouillage optimiste par `version`, le refus de clôture tant
qu'une étape reste ouverte, et l'obligation de signature.

C'est correct, et c'est incomplet.

### WF-4 — la correction la plus argumentée du fichier n'a aucun test

`workflows.py` consacre seize lignes de commentaire à cette correction :

> **L'ÉTAT DE L'INTERVENTION EST DÉDUIT DE TOUTES SES ÉTAPES, PAS DE LA
> DERNIÈRE TOUCHÉE.** […] Bloquer l'étape A puis compléter l'étape B repassait
> l'intervention en cours alors que A restait bloquée. **Sur un bordereau qui
> trace une consignation, un blocage qui cesse de se voir est une régression
> de sécurité, pas d'affichage.**

Recherche sur toute la suite :

| Terme | `workflows.py` | `tests/` |
|---|---|---|
| `BLOCKED` | 7 | **0** |
| `NOT_APPLICABLE` | 4 | **0** |
| `CANCELLED` | 3 | **0** |

**Aucun test ne place jamais une étape en `BLOCKED`.** La correction est donc
énoncée, argumentée en termes de sécurité, implémentée — et **rien ne la
retient**. Un retour à `workflow_status = "BLOCKED" if status == "BLOCKED"
else "IN_PROGRESS"` passerait la suite au vert.

C'est le miroir exact du motif inverse rencontré partout ailleurs : ici la
correction est bonne et le garde manque.

| # | Constat | Gravité |
|---|---|---|
| WF-4 | Trois états sur cinq (`BLOCKED`, `NOT_APPLICABLE`, `CANCELLED`) ne sont jamais exercés. La propriété de sécurité la plus explicitement défendue du module n'a aucun test de non-régression. | **haute** |

### `tests/helpers.py` — 27 lignes — **lu intégralement**

### FMT-2 — `sans_accents` existe en double, et `src/formatting.py` affirme le contraire

`src/formatting.py` consacre un paragraphe à ce sujet précis :

> **POURQUOI CETTE FONCTION VIT DANS `src/` ET NON DANS LES TESTS.**
> Elle n'existait que côté tests, et un contrôle du Judge a été silencieusement
> désactivé faute d'y avoir accès. […] Toute comparaison de FOND portant sur du
> texte français passe désormais par ici, **côté code comme côté tests**.

Vérification :

| Consommateur | Import |
|---|---|
| `src/agents/judge_agent.py` | `from src.formatting import nombre, sans_accents` |
| `tests/test_features_detector.py` | `from tests.helpers import sans_accents` |
| `tests/test_fouling_injection.py` | `from tests.helpers import sans_accents` |
| `tests/test_sensitivity.py` | `from tests.helpers import sans_accents` |

Comparaison des deux corps par AST, *docstrings* écartées : **identiques**.

Les tests n'utilisent donc **jamais** la fonction de `src/`. L'énoncé « côté
code comme côté tests » est faux, et la duplication que le module dit avoir
supprimée est intacte.

| # | Constat | Gravité |
|---|---|---|
| FMT-2 | **Neuvième occurrence du motif de duplication**, et celle qu'un *docstring* déclare explicitement résolue. Correction : `tests/helpers.py` réexporte `src.formatting.sans_accents`, ou disparaît. | moyenne |

### `tests/test_domain.py` — 205 lignes — **lu intégralement**

Vingt tests sur le référentiel, dont plusieurs sont des **contrôles de saisie**
au sens strict : `C == F × G × N` pour chaque mode, cotations dans `[1, 10]`,
seuils ordonnés `LL < L < H < HH`, plage opérationnelle incluse dans la plage
physique, alias uniques, tâches préventives citées existantes.

Deux exigences remarquables :

- **Chaque tag doit citer au moins deux bases indépendantes.** « Sans cela,
  *TI1100 = entrée acide* resterait une supposition invérifiable. » Et les six
  tags du périmètre surveillé doivent en plus porter la base `process` : « un
  tag qui déclenche une intervention doit être cohérent avec la physique du
  procédé sulfurique ».
- **Un angle mort sans couverture préventive est interdit** : « ni la
  surveillance ni le préventif ne le couvrent » ferait échouer le test.

`test_cotations_officielles_conservent_les_valeurs_originales` garantit qu'une
ligne `ocp_source` n'a jamais été retouchée : `original_values` doit égaler
`(F, G, N, C)`. C'est la garantie de provenance du document de 2019.

### `tests/test_kpi.py` — 106 lignes — **lu intégralement**

Neuf tests. `test_aucun_indicateur_ne_porte_de_montant` interdit `MAD`, `EUR`,
`USD`, `dirham`, et les mots `coût`, `gain`, `économie` dans les libellés —
c'est le pendant côté code du contrôle de `test_documentation.py`.

`test_le_sur_refroidissement_ne_se_presente_plus_en_energie` verrouille le
retrait des MWh.

**KPI-1 confirmé non couvert** : `assert f.evidence_level in {"observed",
"derived"}` accepte les deux valeurs. Un `derived` jamais produit ne fait donc
échouer aucun test.

### `tests/test_model_governance.py` — 118 lignes — **lu intégralement**

Quatre tests, tous des refus : un `candidate` est rejeté même si le fichier est
lisible, des portes en échec bloquent un statut runtime, une empreinte de
modèle altérée bloque, un ordre de features inversé bloque. Puis un manifeste
promu complet est accepté. Couverture juste et suffisante.

### `tests/test_sensitivity.py` — 147 lignes — **lu intégralement**

Neuf tests, et **deux aveux qui m'obligent à corriger une affirmation
antérieure.**

### Correction — il y avait bien des tests creux dans cette suite

J'ai écrit au lot 29 : « les contrôles vacants ont été trouvés dans le code de
gouvernance, **pas dans la suite de tests** ». C'est faux, et ce fichier le
documente lui-même :

> **LE TEST NE VÉRIFIAIT PAS CE QU'IL ANNONÇAIT.** Il appelait `json.dumps`
> sans rien affirmer : un rapport réduit à `{}` — clé disparue, calcul
> court-circuité — **passait sans un mot**, alors que l'endpoint aurait renvoyé
> une réponse vide. Sérialisable et non vide sont deux propriétés distinctes ;
> seule la première était couverte, et elle l'était **par accident**.

Et un second, d'une autre nature :

> **LE TEST VERROUILLAIT DEUX FORMES VERBALES, PAS UNE PROPRIÉTÉ.** Il exigeait
> littéralement « survit » ou « retient ». La lecture a été réécrite […] : la
> conclusion est là, plus explicite qu'avant, et le test **tombait sur une
> conjugaison**.

Mon analyse AST du lot 29 ne pouvait pas les voir : le premier était un appel
sans assertion — donc invisible à un détecteur d'assertions —, le second une
assertion parfaitement valide portant sur la mauvaise chose.

**Ce que cela établit :** l'analyse syntaxique borne le risque, elle ne
l'élimine pas. Les deux défauts ont été trouvés par **lecture**, comme le mien
dans `twin_smoke.mjs`.

### Le test qui porte le résultat le plus gênant

`test_la_periode_de_reference_change_la_conclusion` exige trois choses :
`sensible is True`, `dispersion_part_derive_pct > 15`, et surtout
**qu'aucune abstention ne subsiste** :

```python
for renoncement in ("communiquee par ocp", "tant que la date",
                    "aucun chiffre de derive ne doit"):
    assert renoncement not in lecture
```

La version précédente concluait « tant que la date de révision réelle n'est pas
communiquée par OCP, aucun chiffre de dérive ne doit être présenté ».
Le test le qualifie : « **c'est une abstention, pas une conclusion** : elle
suspend le résultat à une information que ce travail n'obtiendra pas ».

C'est, à mon sens, le meilleur test du dépôt : il interdit au projet de se
défausser.

### `tests/test_fouling_injection.py` — 213 lignes — **lu intégralement**

Onze tests, dont trois sur le **modèle d'injection lui-même** : la rampe monte
progressivement, elle n'agit pas à l'arrêt, et la dégradation est **monotone**
— « c'est la propriété qui garantit que l'injection est physique : **un dépôt
ne se résorbe pas tout seul** ».

`test_l_injection_demarre_dans_une_fenetre_silencieuse` verrouille le point de
méthode : « la première version de ce banc annonçait 100 % de détection à 0 %
d'avancement — **un résultat vide** ».

`test_le_temoin_mesure_les_declenchements_sans_faute` documente une **troisième
tautologie corrigée dans la suite** :

> `0 <= taux <= 1` est une tautologie : un taux est toujours dans [0, 1]. Ce
> qui doit être verrouillé est le **NIVEAU**.

`test_les_limites_sont_declarees` exige que le mot « favorable » figure dans
les limitations — c'est-à-dire que le banc continue d'admettre qu'il est
**optimiste**.

### `tests/test_operator_registry.py` — 352 lignes — **lu intégralement**

Vingt-sept tests. La couverture la plus complète du dépôt, et **aucun défaut**.

Deux tests de concurrence et de fuite mémoire méritent d'être signalés :

- `test_la_limite_de_tentatives_tient_sous_concurrence` lance **vingt fils** et
  exige que le nombre de dérivations reste sous la limite. C'est le garde du
  contournement que j'avais moi-même mesuré plus tôt dans cette mission :
  « vingt requêtes simultanées produisaient vingt dérivations complètes et
  **zéro refus** ».
- `test_les_compteurs_et_sessions_perimes_sont_liberes` crée 40 adresses
  clientes puis vérifie que `_purger` les libère.

Trois tests couvrent la validation au chargement (rôle inconnu, empreinte
absente, adresse malformée), et un dernier vérifie les droits POSIX du fichier
— c'est **le test ignoré sous Windows** que la campagne signale (`266 passed,
1 skipped`).

### `tests/test_agents_judge.py` — 593 lignes — **lu intégralement**

Trente tests. C'est le cœur de la garantie du projet, et la couverture est à la
hauteur.

**Le guard que AL-1 devrait avoir existe déjà — pour l'agent.**

`test_un_defaut_de_mesure_ne_domine_jamais_un_diagnostic_equipement` verrouille
exactement la propriété que `AlarmStore._key` viole :

> La constatation dominante était choisie par `max()` sur la seule sévérité,
> qui renvoie le premier élément à égalité : **l'ordre d'écriture des règles
> décidait**. `_rule_sensor_health` s'exécutant en tête, un `SENSOR_FAULT`
> l'emportait sur un `CONC_DROP_SEVERE` de même sévérité.

**Conséquence pour le plan :** corriger AL-1 ne demande pas d'inventer un test,
mais de **transposer celui-ci** au registre d'alarmes.

`test_un_seul_bareme_de_confiance_existe` compare, sur quinze instants, la
confiance annoncée par l'agent à celle du barème partagé — divergence
impossible.

`test_les_mutations_non_ciblees_mesurent_la_generalisation` impose que le taux
de généralisation reste **au moins dix points sous** celui de non-régression :
« si les deux se rejoignent, c'est que les mutations dites non ciblées visent
en réalité un contrôle ». Aucune borne **inférieure** n'est posée — un taux de
0 % passerait. C'est défendable (on ne peut pas exiger un rendement sur
l'imprévu), et cela renforce JE-1 : puisque le chiffre n'est pas verrouillé, il
doit au moins être **publié**.

### Le motif « test annoncé et inexistant » — décompte final

Ce fichier en documente **deux de plus**, et les nomme :

> `test_aucune_decision_native_ne_declenche_la_sur_confiance` :
> **LE TEST QUE `detection_agent` AFFIRMAIT AVOIR.**
>
> `test_aucune_mutation_non_ciblee_ne_vise_un_controle` :
> **LE TEST QUE `judge_eval` AFFIRMAIT AVOIR — DEUX FOIS.**

Récapitulatif des garanties documentées sans garde, toutes corrigées depuis :

| # | Garantie annoncée | Où |
|---|---|---|
| 1 | `test_le_gain_ne_vient_pas_dune_baisse_de_frequence` | rapport technique |
| 2 | test sur les handlers de la boucle d'événements | `api/main.py` |
| 3 | équivalence prédicat / règle d'encrassement | `fouling_injection.py` |
| 4 | non-ciblage des mutations aveugles | `judge_eval.py` |
| 5 | absence de sur-confiance native | `detection_agent.py` |
| 6 | centralisation de `duree_pas` | ADR-011 |
| 7 | verrouillage de l'équivalence par un test | `_fouling_hours` |

**Sept affirmations sans preuve, toutes désormais tenues.** C'est le motif le
plus instructif du dépôt, avec les neuf duplications : le projet a longtemps
**décrit** ses garanties avant de les **implémenter**.

### `tests/test_api.py` — 721 lignes — **lu intégralement**

Une quarantaine de tests, avec cycle de vie complet de l'application. Couverture
très large : santé, actifs servis et actifs **supprimés**, en-têtes de sécurité,
session et CSRF, rôles, gouvernance, validation scientifique, séries, capteurs,
épisodes, analyse, rejeu, Judge, topologie, KPI, couverture du risque,
sensibilité, banc d'encrassement, routage des alertes.

Plusieurs tests verrouillent des retraits plutôt que des ajouts :

- `test_endpoints_economiques_retires` — les trois routes `/api/business/*`
  doivent renvoyer 404.
- `test_dashboard_servi` — `"MAD" not in r.text`, `"business" not in
  r.text.lower()`, aucune ressource CDN, une seule feuille de style.
- `test_actifs_servis_et_actifs_supprimes` — les quatre anciens actifs doivent
  répondre 404, et `app.js` ne doit plus contenir
  `includes("FAISCEAU")` : la recherche de sous-chaîne est interdite par test.
- `test_le_banc_refuse_une_severite_physiquement_impossible` — « LE TEST QUI
  EMPÊCHE LA RECHUTE LA PLUS COÛTEUSE DU PROJET » : `severities=1,2,3`
  décrivaient des pertes de 100, 200 et 300 % de UA, « un échangeur qui
  n'échange plus rien, détecté par construction. La page de gouvernance
  affichait ainsi **100 % de détection sans rien démontrer** ».

### API-6 — `/api/alarms` n'est testé à aucun niveau HTTP

| Route | Occurrences dans `test_api.py` |
|---|---|
| `/api/workflows*` | **9** — cycle complet : modèles, création, étape, conflit 409, clôture refusée, clôture OK, lecture, liste |
| `/api/alarms` | **0** |
| `/api/alarms/{id}/transition` | **0** |
| `/api/config` | **0** |
| `/api/auth/audit` | **0** |
| `/api/auth/refresh` | **0** |

Les gammes sont donc **entièrement couvertes côté HTTP** — seul l'affichage
manque. Les alarmes, elles, ne sont testées qu'au niveau unitaire
(`test_alarm_store.py`) : **ni la route de liste, ni la route de transition,
ni la matrice de rôles par action** (`allowed_by_action`, `main.py` l. 1445) ne
sont exercées.

Or c'est précisément là que se trouve API-4 — le rôle par défaut
`"administrator"` pour « poste-local ». Aucun test ne le constate.

| # | Constat | Gravité |
|---|---|---|
| API-6 | Cinq routes sans test HTTP, dont les deux du cycle de vie des alarmes et le journal d'authentification. Combiné à B1 (aucune interface) et à AL-1 (harnais incapable d'exprimer le défaut), le sous-système d'alarmes est **le moins éprouvé du dépôt** alors qu'il porte la revendication ISA-18.2. | **haute** |

### DOC-1 — deux chiffres pour le même fait

| Source | Énoncé |
|---|---|
| `src/analytics/kpi.py` l. 271 | « dépasse **40 %** sur certains mois » |
| `tests/test_api.py` l. 564 | « dépasse **20 %** sur certains mois » |

Le test n'impose aucun seuil absolu — il vérifie seulement que le pire mois
dépasse la moyenne — donc les deux commentaires cohabitent sans conflit
mécanique. Mais le même fait est chiffré deux fois différemment dans le dépôt.

**À trancher en D1** : mesurer la valeur réelle et l'écrire une seule fois.

### `tests/test_features_detector.py` — 652 lignes — **lu jusqu'à la ligne 450**

Le fichier le plus dense de la suite, et celui qui contient **les deux parades
dont le plan de réorganisation a besoin.**

### La parade au motif de duplication existe déjà

`test_la_borne_de_reference_est_definie_a_un_seul_endroit` interdit, **par
analyse syntaxique**, toute réapparition du littéral `0.40` hors de la
définition de la constante, dans trois fichiers :

```python
if (isinstance(noeud, ast.Constant) and noeud.value == 0.40
        and noeud.lineno not in lignes_de_definition):
    fautifs.append(f"{chemin.name}:{noeud.lineno}")
```

> La constante était recopiée dans `LinearReference.fit` et dans
> `CoolerAnomalyDetector.fit` alors qu'ADR-009 affirme qu'elle est « définie
> une fois ». **Trois copies d'un paramètre qui décide du résultat central du
> projet finissent par diverger.**

**C'est exactement le remède à appliquer aux neuf duplications recensées.** Le
patron est écrit, éprouvé, et déjà dans le dépôt.

### La parade au motif de « branche morte » existe aussi

`test_le_seuil_de_gradation_est_atteignable_par_les_donnees` mesure le domaine
réellement atteint par l'indicateur et échoue si le seuil de gouvernance en
sort :

> Un seuil que le corpus ne franchit jamais est une branche morte. […] **C'est
> le contrôle qui manquait : sans lui, un seuil peut redevenir inatteignable
> en silence.**

Applicable directement à M-3 (`_MODE_BY_THRESHOLD`, trois entrées inertes).

### Huitième « test annoncé et inexistant »

> `test_les_trois_references_partagent_la_meme_periode` :
> **LE TEST QU'ADR-009 AFFIRMAIT AVOIR.** ADR-009 conclut par « un test
> verrouille l'alignement ». **Ce test n'existait pas**, et l'alignement
> n'était pas tenu : les trois références s'arrêtaient à **17 h, 18 h et 21 h
> du même jour**.

### Un défaut qui était dans le test, pas dans le code

`_hist` porte cette note :

> Le défaut était dans le TEST, pas dans le code : en exploitation, `history`
> est toujours une tranche de `features`, donc indexée par le temps.
> **Un repli sur le comptage de lignes aurait réintroduit en silence exactement
> le défaut que la fenêtre calendaire corrige.**

C'est la bonne décision : réparer le harnais plutôt que d'affaiblir le code —
et c'est précisément ce qu'il faudra faire pour AL-1.

### Autres verrous notables

- `test_effort_de_regulation_est_redondant_et_le_declare` : `|r| > 0,80` **et**
  `independent is False`. Le test échoue si quelqu'un tente de présenter
  l'effort comme indépendant.
- `test_effort_de_regulation_seul_ne_declare_pas_un_encrassement` : « l'annoncer
  comme un encrassement conduirait à programmer un nettoyage haute pression —
  **plusieurs jours d'arrêt de ligne** — sur la foi d'un signal redondant ».
- `test_rho_cp_varie_peu_car_les_deux_effets_se_compensent` : fige le constat
  « pour empêcher de le sur-vendre ».
- `test_la_gradation_de_l_encrassement_porte_sur_ua` : « la version précédente
  de ce test l'affirmait pourtant **en forçant −2,0** […] un test qui ne peut
  passer qu'avec une valeur que les données ne produisent pas ne vérifie
  rien ».

### M-3 confirmé par le test lui-même

`test_le_rattachement_ne_cite_que_des_features_du_modele` inspecte bien **les
deux tables** :

```python
hors_modele = {**_MODE_BY_RESIDUAL, **_MODE_BY_THRESHOLD}.keys() - set(MODEL_FEATURES)
```

Il verrouille l'**appartenance** à `MODEL_FEATURES`, jamais
l'**atteignabilité**. Les trois entrées inertes (`conc_drop_24h`, `d_conc`,
`flow_per_load`) appartiennent bien à `MODEL_FEATURES` : le test passe. M-3
tient exactement comme énoncé.

---

## 31. `docs/` — documents transverses

### `docs/decisions/INDEX.md` — 19 lignes — **lu intégralement**

Onze ADR, chacune avec sa portée. Table cohérente, liens relatifs corrects.

### `docs/data_dictionary_E7301.md` — 40 lignes — **lu intégralement**

Douze tags, statut de détermination (`inferred` / `unknown`), propriétaire à
confirmer, et huit règles communes. Aucun tag n'est déclaré confirmé — c'est
cohérent avec `test_domain.py`, qui exige deux bases indépendantes sans jamais
prétendre à une validation OCP.

**Empreinte vérifiée** : le SHA-256 cité,
`93487c58…5520239`, **correspond exactement** au fichier réel **et** au
manifeste. Trois sources, une seule valeur.

### `docs/traceability_matrix_E7301.md` — 25 lignes — **lu intégralement**

Quinze lignes reliant chaque information à sa source et à son usage, avec la
distinction `source OCP` / `règle dérivée` / `règle applicative` / `hypothèse`.
C'est le document qui rend la provenance contestable — et il est bon.

### DOC-2 — deux références mortes dans la matrice de traçabilité

| Référence citée | État |
|---|---|
| `economics.yaml` — « Valeur économique · hypothèse · `economics.yaml` avec niveaux de confiance » | **le fichier n'existe nulle part dans le dépôt** |
| `reports/audit_initial_state_2026-07-25.md` — « les SHA-256 complets des neuf originaux […] y sont consignés » | **le fichier n'existe pas** |

La première est la plus gênante : la couche économique a été **retirée**, deux
tests interdisent son retour, `test_documentation.py` interdit tout montant en
MAD dans un tableau — et la matrice de traçabilité continue de décrire un
`economics.yaml` « avec niveaux de confiance » comme s'il faisait partie du
système.

La seconde promet un document de preuve — les empreintes des neuf originaux
OCP — qui n'existe pas. C'est une **promesse de traçabilité non tenue**, dans
le document dont c'est précisément l'objet.

`test_documentation.py` ne les détecte pas : ses quatre contrôles portent sur
les routes `/api/`, les noms de tests, les scripts et cibles `make`, et les
montants. **Ni les chemins de fichiers, ni les noms de fichiers de
configuration ne sont vérifiés.**

| # | Constat | Gravité |
|---|---|---|
| DOC-2 | Deux références mortes dans le document de traçabilité, dont une décrivant une couche retirée du système. Correction en deux lignes ; extension du contrôle documentaire aux chemins de fichiers cités entre *backticks*. | **haute** |

### WF-1 confirmé côté tests

`store.complete` est appelé **trois fois** dans le fichier — mais toujours sur
des workflows **différents ou dans des états différents** : une fois avec des
étapes ouvertes (échec attendu), une fois avec signature vide (échec attendu),
une fois valide. **Jamais deux fois de suite sur la même intervention
clôturée.** L'écrasement de signature décrit en WF-1 n'est donc pas couvert.

---

## 28. `src/analytics/kpi.py` — 339 lignes — **lu intégralement**

Indicateurs calculés **sans aucune hypothèse économique** : « un chiffre sorti
d'ici peut être recalculé par un tiers à partir de `DATA.xlsx` et de
`tags.yaml`, sans rien d'autre ».

### Deux corrections d'honnêteté

**`flag_rate`, ajouté après audit.** Le projet calibrait sur 2 % de
contamination et n'affichait que la charge d'épisodes agrégés — environ 5 par
mois — « ce qui donnait l'impression d'un système sobre » :

> Le taux **horaire** réel est **cinq fois supérieur** au paramètre de
> conception, et dépasse **40 % sur certains mois**. Un opérateur devant un
> poste où quatre heures sur dix sont signalées cesse de regarder l'écran.
>
> Ce chiffre doit être affiché à côté de la charge d'épisodes, faute de quoi
> **l'agrégation masque le problème qu'elle prétend résoudre**.

**`overcooling_regime` ne publie plus de MWh.** La version précédente chiffrait
le sur-refroidissement en « énergie évacuée en excès » :

> La formulation était trompeuse à deux titres. D'abord parce qu'elle appelle
> immédiatement la question du coût, à laquelle la réponse honnête est
> « presque rien » : l'eau de mer circule de toute façon et la pompe ne module
> pas. Ensuite parce qu'elle déplaçait un constat de **conduite** vers un
> registre économique que ce projet n'a pas les données pour traiter.

Le critère retenu est strict — plus d'un demi-degré sous consigne **et** dérive
confirmée de la référence — « c'est-à-dire un régime installé et non une
oscillation ». Et l'usage de `regulation_effort_trend_14d` est ici **légitime** :
il sert d'indicateur de conduite, jamais de dégradation.

`corrosion_exposure` traite correctement un résultat proche de zéro : « un
indicateur proche de zéro **est** un résultat », qui déplace la question vers
l'âge et l'érosion.

### KPI-1 — `evidence_level: derived` est déclaré et jamais produit

L'en-tête du module en fait une distinction de fond :

> Cette distinction **n'est pas cosmétique** : une grandeur `derived` hérite
> des limites du modèle de référence et **ne doit jamais être présentée comme
> une mesure**.

Vérification sur les sept `Figure` construites dans le fichier : **toutes
portent `evidence_level="observed"`**. Aucune n'est `derived`, et aucun autre
module ne construit de `Figure`.

Le front lit pourtant le champ (2 occurrences dans `app.js`) : il affiche donc
une distinction qui ne varie jamais.

| # | Constat | Gravité |
|---|---|---|
| KPI-1 | Catégorie déclarée avec insistance, jamais instanciée. Même forme que `CANCELLED` (WF-2), `validated_offline` (LIN-1) et `uncertainty_level` (J-5) : **quatrième énumération dont une valeur n'est jamais produite**. Soit un indicateur `derived` existe — l'énergie évacuée le serait, mais elle a été retirée à raison — soit le champ est une constante. | mineure |

Note : la disparition de `derived` est probablement la **conséquence directe**
du retrait des MWh dans `overcooling_regime`. C'était la seule grandeur
`derived` du module. Le retrait était juste ; le champ est resté orphelin.

---

## 11. À lire

- [ ] `src/domain/` — `knowledge.py` (848), `amdec.yaml` (532), `tags.yaml` (364), `topology.yaml` (264)
- [ ] `src/models/detector.py` (1 333)
- [ ] `src/agents/` — `judge_agent.py` (1 289), `detection_agent.py` (772), `schemas.py` (286)
- [ ] `src/features/` — `e7301_features.py` (806), `thermal.py` (410)
- [ ] `src/ingest/dcs_loader.py` (585)
- [ ] `src/governance/` — `judge_eval.py` (699), `model_validation.py` (515), `fouling_injection.py` (466), `sensitivity.py` (264), `lineage.py` (239)
- [ ] `src/operations/` — `alarms.py` (517), `workflows.py` (326)
- [ ] `src/realtime/replay.py` (430), `src/analytics/kpi.py` (339), `src/formatting.py` (165)
- [ ] `src/security/` — `registry.py` (362), `auth.py` (300)
- [ ] `api/main.py` (1 639), `api/__main__.py` (73), `api/dashboard.html` (545)
- [ ] `tests/` — 41 fichiers
- [ ] `docs/` — 17 Markdown dont `rapport_technique.md` (894)
- [ ] `notebooks/01_analyse_E7301.ipynb` (556)
- [ ] Racine : `README.md`, `Makefile`, `Dockerfile`, `docker-compose.yml`, `pyproject.toml`, `requirements*.txt`

---

# Lot 2 — référentiel métier, ADR, architecture, CI

*Session du 1er août 2026. Fichiers lus intégralement dans ce lot :*
`src/domain/amdec.yaml` (532), `src/domain/tags.yaml` (364),
`docs/decisions/INDEX.md` + les **onze ADR** (830), `docs/architecture.md` (156),
`Makefile` (172), `package.json`, `.github/workflows/ci.yml` (212).
*Vérifications croisées :* `api/main.py:1245-1346`, `src/ingest/dcs_loader.py:330-394`,
`src/notifications/redaction.py`, `reports/judge_eval_summary.json`,
`reports/project_metrics.json`, `reports/junit.xml`.

## 20. `src/domain/amdec.yaml` — 532 lignes — **lu intégralement**

### Ce qui est solide

Treize modes, chacun avec un bloc `provenance` complet : `category`,
`source_file`, `source_location`, `original_values`, `transformations`,
`validation_status`, `validation_owner`. Les trois natures sont séparées sans
ambiguïté — `ocp_source` (transcription), `derived_rule` (règle tirée d'une
ligne source), `application_rule` (cotation proposée par ce travail, jamais
validée). `CAPTEUR_DEFAILLANT` porte explicitement
`original_values: {F: null, G: null, N: null, C: null}` : la cotation F6/G6/N3
n'usurpe aucune autorité OCP.

Le champ `observable` est un vrai garde-fou et son commentaire l'explique :
`FAISCEAU_CORROSION` est passé à `partial` parce que `bool(indicators)` le
comptait comme pleinement couvert — **105 points de criticité ajoutés à tort à
la couverture publiée**. C'est le genre de correction qu'on ne trouve que si on
la cherche, et elle est écrite.

### DOM-2 — `gammes` : le bloc le plus détaillé du référentiel n'atteint aucun écran

`DomainKnowledge.gammes` (`knowledge.py:360`) est chargé et **jamais lu**.
Vérifié : zéro consommateur dans `src/`, `api/`, `tests/`, `scripts/`.

Ce qui est ainsi perdu, pour la seule gamme `PS3-ABS-REFR` : 7 prérequis de
consignation, 5 EPI, 5 outillages, 2 pièces de rechange, et `duree_min: 295`.
Une durée d'intervention de 4 h 55 est exactement ce qu'un planificateur
cherche, et elle est dans le dépôt sans être affichée nulle part.

Symétriquement, `gammes.TAMPONNAGE` ne porte **ni étapes, ni EPI, ni durée** —
un intitulé, un état requis, une note sur le seuil de 30 %. Le fichier source
`8-Gamme de tamponnage des tubes de refroidisseur.xls` est dans `docs/` mais
n'a jamais été transcrit.

### API-3 — **correction et aggravation du constat de la session précédente**

Le constat disait : « `_workflow_templates()` code en dur 6 prérequis HSE et
8 étapes de tamponnage, alors que `amdec.yaml/gammes` les contient
(7 prérequis) ; le point manquant est le débranchement des anodes ».

**C'est incomplet sur trois points, et je me corrige.**

**1. Les deux check-lists, elles, sont bien gouvernées.** `api/main.py:1259` et
`:1292` lisent `domain.checklists["INSPECTION_EXTERNE"/"INSPECTION_INTERNE"]`.
Le défaut ne porte pas sur tout `_workflow_templates()`, seulement sur les
prérequis HSE et le tamponnage.

**2. L'écart n'est pas d'un point, il est de quatre.** Confrontation ligne à
ligne de `amdec.yaml:478-485` (7 prérequis gouvernés) et de
`api/main.py:1262-1269` (6 prérequis en dur) :

| Prérequis gouverné | À l'écran ? |
|---|---|
| Consigner le moteur de la pompe d'absorption | **absent** |
| Isoler et consigner les circuits acide et eau de mer | HSE-02 |
| Vidanger les boîtes d'eau de mer | **absent** |
| Vidanger la calandre (pression ramenée à 0 bar) | HSE-03 |
| Cadenas par intervenant | **absent** |
| Autorisation de travail | HSE-01 |
| Débranchement du courant sur les anodes (film-garde) | **absent** |

Les quatre absents sont tous des points de **consignation** — le cadenas par
intervenant et la consignation du moteur de pompe autant que le débranchement
des anodes. Un écran de prérequis HSE amputé de la moitié de ses points de
consignation est pire qu'un écran sans prérequis, parce qu'il se présente comme
complet.

**3. Trois des six points affichés ne sont pas des prérequis.** HSE-04 (« EPI
anti-acide complets ») vient du champ `epi`, HSE-06 (« manutention au palan »)
du champ `outillage`, et HSE-05 (« Couvercles ouverts selon la gamme ») décrit
**l'opération elle-même**, pas une condition préalable. Les trois portent
pourtant `source_ref: "7-Gamme PV … phases 10 à 120"`.

**4. Les 8 étapes de tamponnage n'ont aucune source dans le dépôt.**
`gammes.TAMPONNAGE` ne contient pas d'étapes. Chacune des huit porte néanmoins
`source_ref: "8-Gamme de tamponnage des tubes de refroidisseur.xls"`. La
provenance affichée à l'exploitant est **invérifiable depuis le dépôt** — c'est
précisément ce que l'exigence de provenance d'ADR-011 était censée empêcher.

| # | Constat | Gravité |
|---|---|---|
| API-3 | 4 prérequis de consignation gouvernés sur 7 n'atteignent pas l'écran ; 3 des 6 affichés ne sont pas des prérequis ; les 8 étapes de tamponnage affichent une provenance invérifiable | **haute** |

### DOM-3 — le seuil de réforme de 30 % n'est gouverné nulle part

Le critère de déclenchement de la tâche H — remplacement du refroidisseur — est
présent **trois fois, jamais comme valeur** :

- `amdec.yaml:464` : en prose dans `plan_maintenance.H.tache` ;
- `amdec.yaml:491` : en prose dans `gammes.TAMPONNAGE.note` ;
- `api/main.py:1301` et `:1336` : en littéral dans deux chaînes françaises.

ADR-005 affirme : « **Aucun seuil, aucun nom de tag, aucune criticité, aucune
position de capteur n'est écrit ailleurs.** » Ce seuil-là l'est, et il n'existe
pas de champ numérique à corriger si OCP le révise.

### DOM-4 — `tags.yaml` porte sa bannière de titre au milieu du fichier

Les lignes 1 et 2 sont un `# ===` orphelin ; `governance_defaults` et
`registry_change_history` occupent les lignes 3 à 31 ; la bannière
« REGISTRE DES TAGS DCS — REFROIDISSEUR E7301 », avec tout l'avertissement
méthodologique sur les corrélations, ne commence qu'à la ligne 32. Deux blocs
ont été insérés **au-dessus** de l'en-tête au lieu d'être insérés dedans.

Sans conséquence fonctionnelle. C'est une trace lisible du passage de plusieurs
mains sur ce fichier, et elle mérite d'être corrigée avant présentation.

## 21. `src/domain/tags.yaml` — 364 lignes — **lu intégralement**

### Ce qui est solide

Douze tags, chacun avec `basis` (≥ 2 bases) et `evidence` détaillée.
L'avertissement méthodologique des lignes 52-60 est le passage le plus honnête
du référentiel : il donne les corrélations **fausses** qu'une lecture naïve
produirait (`TI1100~TI1105 : r = +0,976 sur tout, −0,083 en marche`) avant de
donner les vraies. Et `S_MC_SULF_AI1200_B` publie en toutes lettres une
correction d'analyse initiale — les deux analyseurs avaient été pris pour une
redondance, ils ne le sont pas, biais constant de +0,124 point et corrélation
de +0,35 seulement.

### DOM-1 — `process_states` est une prose non consommée **qui contredit le code**

`process_states` (`tags.yaml:355-364`) est chargé dans
`DomainKnowledge.process_states` (`knowledge.py:283`) et n'est lu **par
personne** — confirmation du constat K-1. La classification réelle est
`dcs_loader.classify_process_state` (l. 330-394).

Le point nouveau est que les deux ont **divergé dans les deux sens** :

| Critère | `tags.yaml` | `dcs_loader.py` |
|---|---|---|
| `T_ACID_IN < 60` | classé **TRANSIENT** (l. 361) | classé **STOPPED** — `is_down`, l. 376 |
| reprise après arrêt (`is_down.shift(1)`) | **non mentionné** | critère TRANSIENT, l. 390 |
| `LOAD_SULFUR < 8`, `F_ACID < 20` | STOPPED | STOPPED — identique |

À décharge, et c'est important : les **quatre seuils numériques sont bien
gouvernés** (`shutdown_below`, `alarm_low_low`, `transient_rate_per_h`), avec
un repli en `is None` et non en `or` — le commentaire des lignes 357-364 de
`dcs_loader.py` est exact et la correction est réelle. Ce qui a dérivé, c'est
la **description en prose** de la règle, restée à l'état antérieur.

C'est le motif 1 sous sa forme la plus discrète : la valeur a été centralisée,
la phrase qui la décrit ne l'a pas suivie. Sur « la décision la plus
déterminante du système », selon les mots du fichier lui-même.

| # | Constat | Gravité |
|---|---|---|
| DOM-1 | `process_states` décrit une règle de classification que le code n'applique pas, et omet un critère que le code applique | moyenne |

### DOM-5 — `F_ACID` : le seuil d'arrêt emprunte le champ d'une alarme

`classify_process_state` lit `domain.get("F_ACID").threshold("alarm_low_low")`
pour son critère d'arrêt, là où `LOAD_SULFUR` et `T_ACID_IN` utilisent tous deux
`shutdown_below`. Les deux valeurs coïncident aujourd'hui (20 m³/h), mais elles
répondent à deux questions différentes : « à partir de quand alerter » et « à
partir de quand considérer la ligne arrêtée ». Abaisser l'alarme basse-basse
déplacerait silencieusement la frontière marche/arrêt de tout le corpus.

`F_ACID` devrait porter son propre `shutdown_below`, comme ses deux voisins.

## 22. Les onze ADR — **lues intégralement**

La session précédente l'avait annoncé : *« deux des huit garanties non tenues
viennent des ADR ; les onze n'ont pas encore été lues, elles sont la source la
plus probable de nouvelles affirmations non tenues. À lire en priorité. »*

**C'était juste. Quatre affirmations sont prises en défaut, dont une grave.**

### ADR-4-1 — le chiffre de généralisation publié est **huit fois** le chiffre mesuré

ADR-004 publie, dans le tableau intitulé « Ce que le banc d'évaluation mesure
réellement » :

| Mesure | Résultat annoncé | Ce qu'elle vaut, selon l'ADR |
|---|---|---|
| Pièges ciblés | ~97 % | non-régression des huit contrôles |
| **Mutations non ciblées** | **~80 %** | **généralisation réelle** |
| Faux positifs sur cas sains | 0 % | ne rejette pas le correct |

Mesure réelle, `reports/judge_eval_summary.json` :

```json
"trap_detection_rate": 0.958,
"false_positive_rate": 0.0,
"blind_mutations": { "n": 60, "flagged_rate": 0.1, "penalised_rate": 0.017 }
```

- généralisation annoncée **80 %**, mesurée **10 %** — et 1,7 % réellement
  sanctionnées. **Facteur 8.**
- pièges ciblés annoncés ~97 %, mesurés 95,8 %.
- faux positifs 0 % — exact.

Le fichier de mesure porte lui-même l'explication, dans son champ `reading` :

> « Mutations aleatoires ne visant aucun controle. **Ce taux, inferieur au
> precedent**, est la mesure honnete de ce que le Judge attrape sans l'avoir
> anticipe. »

Le banc a été rendu honnête, le chiffre s'est effondré, **et l'ADR n'a pas
suivi**. C'est la seule ligne du dossier qui prétend répondre à « que
détecte-t-il qu'il ne connaît pas déjà ? », et c'est celle qui est fausse. Dans
le document qu'un jury lit pour comprendre le dispositif de gouvernance.

| # | Constat | Gravité |
|---|---|---|
| ADR-4-1 | ADR-004 publie 80 % de généralisation là où le banc en mesure 10 % | **haute** |
| ADR-4-2 | ADR-004 publie ~97 % de détection des pièges là où le banc en mesure 95,8 % | mineure |

### ADR-3-1 et ADR-3-2 — ADR-003 compte faux sur deux chiffres

- « **Dix** features, choisies pour ne garder qu'une représentation par
  mécanisme physique. » `MODEL_FEATURES` (`e7301_features.py:188-200`) en
  compte **onze**, et `project_metrics.json` publie `"n_features": 11` avec la
  liste ordonnée. La onzième est `t_in_local_z`.
- « **62** épisodes agrégés sur quatorze mois, soit environ **4,4** par mois. »
  `project_metrics.json` : `"episodes": 58`, soit 4,1 par mois.

« Dix-sept règles déterministes » : vérifié, 17. « Trois des six dernières
heures » : conforme au code.

### ADR-11-1 — ADR-011 sous-compte son propre banc de neuf vérifications

« Le banc frontend passe de 36 à **43** vérifications. » `frontend_smoke.mjs`
en porte **52** aujourd'hui. Le chiffre était juste au moment de l'écriture ; il
n'a pas été tenu.

### ADR-6-1 — ADR-006 se contredit à deux paragraphes d'intervalle

Section « Décision » : « **Aucune requête sortante à l'exécution.** »
Section « Modèle de langage », 15 lignes plus bas : « Renseigner une clé active
uniquement la couche de rédaction. »

La couche de rédaction appelle un service distant. L'affirmation absolue doit
être conditionnée — « aucune requête sortante **en configuration par défaut** »
— sinon elle est fausse dès qu'on renseigne `GEMINI_API_KEY`, ce que le `.env`
du dépôt fait précisément.

### Les affirmations d'ADR qui **tiennent** — vérifiées une par une

| Affirmation | Vérification |
|---|---|
| ADR-004 — « huit contrôles logiques » | V1 à V8 dans `judge_agent.py` ✔ |
| ADR-005 — « les douze tags DCS » | 12 entrées dans `tags.yaml/tags` ✔ |
| ADR-007 — « le mode production refuse de démarrer sans OIDC » | `config.py:307-309` lève un NO-GO ✔ |
| ADR-009 — « `REFERENCE_FRACTION` définie une fois » | `thermal.py:112`, unique ✔ **et verrouillée par un test AST** (`test_features_detector.py:221`) |
| ADR-009 — « un test verrouille l'alignement » | présent ✔ |
| ADR-006 — « provenance documentée dans `ASSET_SOURCES.md` » | le fichier existe ✔ |
| ADR-003 — « dix-sept règles » | 17 ✔ |
| ADR-001 — R² 0,968 / 0,962 / corr −0,94 | conformes aux constats du lot 1 ✔ |

Sept affirmations vérifiables sur onze ADR tiennent. Quatre ne tiennent pas.
**Le rapport n'a pas encore été confronté ; c'est la prochaine source.**

## 23. `docs/architecture.md` — 156 lignes — **lu intégralement**

**C'est le document le plus périmé du dépôt.** Il porte en en-tête « Version
active : 3.0 — état vérifié le 25 juillet 2026 », soit **trois jours avant** les
ADR-009, -010 et -011, qu'il ignore toutes les trois.

### ARCH-3 — le document d'architecture décrit le système **d'avant sa correction centrale**

Ligne 98 :

> « La référence thermique semi-empirique estime **le duty attendu** à
> conditions comparables. Le résidu met en évidence un **effort de
> refroidissement anormal** sans confondre charge et dégradation. »

C'est mot pour mot l'approche que **ADR-001 démontre algébriquement fausse** —
« Le résidu de puissance *est* l'écart de consigne, changé de signe et pondéré
par le débit » — et qui a été renommée `regulation_effort` pour cette raison.

Et la mesure qui l'établit : **`UA` n'apparaît pas une seule fois dans les
156 lignes du fichier.** L'indicateur qui porte tout le diagnostic
d'encrassement, le cœur scientifique du travail, est absent du document
d'architecture.

Un lecteur qui commence par `architecture.md` — c'est-à-dire tout lecteur —
repart avec la version fausse.

| # | Constat | Gravité |
|---|---|---|
| ARCH-3 | `architecture.md` présente le résidu de duty comme la référence du système, approche réfutée par ADR-001 ; le mot UA n'y figure pas | **haute** |

### ARCH-4 — la période de référence y est encore décrite par `REFERENCE_END`

Lignes 104-107 : « La période de référence est sélectionnée automatiquement
[…] La variable `REFERENCE_END` permet de reproduire ou de déplacer cet
ancrage. » ADR-009 établit que `REFERENCE_END = None` **était la fuite de
données** qui expliquait à elle seule que `FOULING_DRIFT` ne se déclenche jamais.
Le repli à 40 % — la décision d'ADR-009 — n'est pas mentionné.

### ARCH-1 — le document décrit un dossier qui n'existe pas

Lignes 22-23 : « `legacy/` conserve l'ancienne architecture à des fins
historiques. Elle n'est ni importée, ni déployée, ni couverte par les
procédures d'exploitation v2. » **Il n'y a pas de dossier `legacy/`.**

### ARCH-2 — lien mort vers un ADR qui n'a jamais existé

Lignes 143-144 : `Voir [ADR-008](decisions/ADR-008-architecture-v2-locale-deterministe.md)`.
Le fichier réel est `ADR-008-interface-isa-101.md`, et aucun ADR du dépôt ne
porte le titre « architecture v2 locale déterministe ». Le lien est mort **et**
la référence est fausse.

### ARCH-6 — un des six « invariants de sûreté » n'est pas un invariant

Le point 6 (« Aucune valorisation monétaire ») consacre ses six lignes à
expliquer qu'un principe antérieur a été supprimé et pourquoi. C'est une note
d'édition, correcte sur le fond, mais placée dans une liste numérotée
d'invariants : le lecteur compte six invariants là où il y en a cinq.

### Ce qui est juste dans ce fichier

`10 180 h, 12 tags` — conforme à `project_metrics.json`. Les invariants 1 à 5
sont exacts et bien formulés. Le tableau des responsabilités est fidèle. La
« frontière de la version démonstrateur » est honnête.

## 24. Chaîne d'intégration continue et `Makefile` — **lus intégralement**

### CI-1 — confirmé

`ci.yml` n'exécute que `ruff` et `bandit`. `mypy` est déclaré dans
`pyproject.toml`, installé, dispose d'une cible `make types`, et la cible
elle-même se qualifie de « informative, non bloquante ». Rien ne l'exécute.

### CI-2 — **le plus gros doublon du dépôt : soixante lignes de Python dans le YAML**

Le job `qualite` embarque un heredoc `python - <<'PY'` de ~60 lignes qui
revérifie le référentiel métier. **Sept de ces contrôles existent déjà en
pytest**, vérifié un par un :

| Contrôle inline de `ci.yml` | Jumeau pytest |
|---|---|
| `C == F × G × N` | `test_domain.py:113` `test_criticite_amdec_est_le_produit_fgn` |
| tâche préventive citée existante | `test_domain.py:127` `test_taches_preventives_referencees_existent` |
| champs de `provenance` complets | `test_domain.py:169` `test_provenance_amdec_source_et_enrichissements_separes` |
| `evidence` ou `rationale` présent | `test_domain.py:28` `test_chaque_tag_declare_sur_quoi_repose_son_sens` |
| ≥ 2 bases de détermination | `test_domain.py:65` `test_la_base_de_determination_est_publiee` |
| capteur de la topologie connu de `tags.yaml` | `test_topology.py:28` |
| pièce, mode AMDEC et `finding_map` existants | `test_topology.py:40` et `:46` |

C'est la **dixième occurrence du motif 1**, et la plus mal placée du dépôt : ce
code n'est ni linté par `ruff`, ni typé, ni couvert, ni exécutable en local.
Il ne peut que diverger de son jumeau, et personne ne le verra.

### CI-3 — la seule métrique honnête du banc est la seule sans garde

La porte « Évaluation du Judge » contrôle trois seuils :

```
trap_detection_rate >= 0.85
false_positive_rate <= 0.20
separation          >= 2.0
```

Elle **ne contrôle pas `blind_mutations`** — c'est-à-dire exactement la mesure
que ADR-004 présente comme « la généralisation réelle » et que
`judge_eval_summary.json` appelle « la mesure honnête ». Le taux peut tomber de
10 % à 0 % sans qu'aucune fusion soit bloquée.

C'est la **neuvième occurrence du motif 2**, et la plus significative : les huit
précédentes étaient des garanties de texte, celle-ci est une garantie de
gouvernance.

| # | Constat | Gravité |
|---|---|---|
| CI-3 | La métrique de généralisation du contrôleur n'a aucune porte en intégration continue, alors que les trois métriques de non-régression en ont une | **haute** |

### CI-4 — commentaire périmé, et une bonne nouvelle

Le commentaire du job `frontend` dit : « 84 vérifications existaient sans jamais
s'opposer à une fusion ». C'était vrai ; ce ne l'est plus. Les trois bancs
(`frontend_smoke`, `twin_smoke`, `boot_smoke`) sont désormais appelés par le
job, avec régénération des fixtures depuis le service réel — ce qui est
exactement la bonne conception. Seul le chiffre est faux : **96 vérifications**
aujourd'hui (52 + 35 + 9).

### MAKE-1 et MAKE-2

- `types` est la **seule cible du `Makefile` absente de `.PHONY`**.
- La liste des trois bancs frontend est écrite **trois fois** : `Makefile`
  (cible `test-front`), `package.json` (script `test:front`) et `ci.yml`.
  Onzième occurrence du motif 1. Ajouter un quatrième banc demande trois
  modifications, et rien ne signale l'oubli de la troisième.

### Ce qui est solide dans la chaîne

La cible `release-runtime` et son avertissement — « un artefact produit hors du
runtime cible ne pourra jamais être promu » — sont justes et évitent une perte
de temps réelle. Le commentaire de `lock-runtime` documente un bug mesuré (32
insertions, épinglages contradictoires `loguru==0.7.2` et `0.7.3`) et sa
correction. La sonde du job `image` porte sur `/api/health/ready` et non sur
`/api/health`, avec la raison écrite. Ce sont trois bonnes décisions
documentées.

## 25. Scripts — **A2 confirmé, quatre orphelins**

Recherche exhaustive dans `Makefile`, `package.json`, `.github/`, `tests/`,
`src/`, `api/`, `README.md`, `docs/*.md` :

| Script | Référencé par |
|---|---|
| `audit_corpus.py` | **aucune référence** |
| `browser_smoke.mjs` | **aucune référence** |
| `make_contact_sheets.py` | **aucune référence** |
| `update_report_docx.py` (359 l.) | **aucune référence** |
| `boot_smoke.mjs` | Makefile · package.json · ci.yml · `test_service_invariants.py` |
| `frontend_smoke.mjs` | idem |
| `twin_smoke.mjs` | idem |
| `dump_fixtures.py` | Makefile · package.json · ci.yml |
| `generate_project_metrics.py` | `test_project_metrics.py` |
| `manage_operators.py` | Makefile · ADR-007 · config · registry · api · README |
| `promote_model.py` | Makefile · `pipeline.py` |
| `validate_release.py` | Makefile · ci.yml |

`browser_smoke.mjs` mérite une mention : c'est un banc pilotant un Chrome réel
par le protocole DevTools. Il n'est pas mort par erreur d'écriture, il est mort
parce qu'aucune cible ne l'appelle — et il n'expose aucun compteur de
vérifications, contrairement aux trois autres.

## 26. État réel de la suite — **la suite n'est pas verte**

`reports/junit.xml`, exécution du 31 juillet : **277 tests, 2 échecs, 1 ignoré.**

| Test en échec | Fichier |
|---|---|
| `test_acces_local_et_notifications_desactivees` | `tests/test_api.py:138` |
| `test_project_metrics_restent_coherentes_avec_les_artefacts` | `tests/test_project_metrics.py` |

Le second est la boucle d'amorçage connue : la suite a gagné des tests, les
artefacts n'ont pas été régénérés depuis.

Le premier est **nouveau et non documenté**. Il vérifie précisément
`/api/notifications/test` et `/api/notifications/governance` en mode local, les
deux routes touchées par les modifications non commitées de la session
précédente. C'est très probablement la manifestation de **API-5**, le défaut
qu'elle a elle-même introduit. Cause exacte à établir en phase E1.

Le chiffre de **267 tests** du rapport technique et de la reprise est donc
périmé de dix unités, et il faudra le réactualiser à 277 — moins les deux
échecs corrigés.

### NOTIF-1 — l'asymétrie API-5 a une troisième jambe

`enqueue_test` et `enqueue_governance` (`email.py:352` et `:365`) ont la même
signature, `demandeur: str | None = None`. `api/main.py:1555` la renseigne pour
la gouvernance ; `api/main.py:1535` appelle `enqueue_test()` sans argument.

Et le corps du message de test (`email.py:359-360`) est resté **sans accents** :
« Le canal email du poste E7301 est **operationnel**. Aucune alerte process
n'est **associee** a ce message. » Le rapport de gouvernance, lui, est
intégralement accentué depuis `redaction.py`.

Deux corps de message, deux typographies, dans le même fichier, produits par
deux méthodes voisines. ADR-011 règle 3 dit que « le test de typographie couvre
toute surface lisible » : cette chaîne-là n'est retournée par aucune API, donc
elle échappe au parcours du test.

### FMT-1 — confirmé par lecture

`redaction.py:65-75` définit `_nombre(valeur, decimales, defaut)`, qui refait
exactement ce que `src/formatting.nombre` fait déjà. ADR-011 règle 2 : « **La
mise en forme des nombres est centralisée.** » Le module écrit pour corriger un
défaut de typographie en introduit un de duplication, contre l'ADR qui l'a
motivé. À reprendre avec API-5.

---

# Lot 3 — `docs/rapport_technique.md`, 894 lignes, **lu intégralement**

*Vérifications croisées :* `src/features/e7301_features.py:188-200`,
`src/governance/judge_eval.py:540-660`, `src/domain/amdec.yaml`,
`reports/project_metrics.json`, `reports/judge_eval_summary.json`,
ADR-001, ADR-002, ADR-003, ADR-009.

## 27. Le constat central : **le rapport décrit un autre système**

Ce n'est pas une affaire de chiffres périmés. Le chapitre 5, l'annexe A et
l'annexe B décrivent une **conception scientifique différente de celle qui est
livrée** — celle d'avant la réfutation d'ADR-001.

### RAP-1 — la preuve la plus courte : quatre recherches dans les 894 lignes

| Terme | Occurrences dans `rapport_technique.md` |
|---|---|
| `UA` (mot entier) | **0** |
| `NTU` | **0** |
| `Safi` | **0** |
| `climatolog…` | **0** |
| `ua_residual…`, `fouling_resistance`, `regulation_effort` | **0** |

L'indicateur qui porte tout le diagnostic d'encrassement, la méthode qui le
calcule, la source de la température d'eau de mer qui le rend calculable, et
les trois variables du modèle qui en dérivent : **aucun n'est nommé une seule
fois dans le rapport technique.**

### RAP-2 — le rapport déclare impossible, à la ligne 761, ce qu'il utilise à la ligne 357

Trois lignes du même document, trois positions incompatibles :

| Ligne | Texte | Position |
|---|---|---|
| 357 | `FOULING_DRIFT` — **déficit de coefficient d'échange** persistant, WARNING au-delà de 3 σ | l'indicateur est **utilisé** |
| 761 | « Le calcul d'un coefficient d'échange global U ou d'une DTLM rigoureuse est donc **impossible** » | il est **déclaré impossible** |
| 845 | Suites à moyen terme : « Intégrer les tags eau de mer pour **calculer un coefficient d'échange global exact** » | il est **annoncé comme travail futur** |

ADR-002 répond précisément à la ligne 761 : le fluide froid n'est pas
instrumenté, sa température est établie par la climatologie de Safi, et c'est
**exactement ce qui a levé le blocage**. Le rapport ignore cette décision et
maintient le blocage comme une limite du travail.

| # | Constat | Gravité |
|---|---|---|
| RAP-2 | Le rapport présente comme impossible et comme travail futur l'indicateur que le système calcule et publie | **haute** |

### RAP-3 — le chapitre 5 enseigne la thèse réfutée

§ 5.1, ligne 278 : « L'encrassement ne se lit pas sur le **résultat**, mais sur
l'**effort** fourni pour l'obtenir. »

§ 5.3 « La référence thermique semi-empirique » donne l'équation de régression
du duty, sa période, ses 3 483 heures, **R² = 0,968**, σ = 24,7 kW — et
présente le résidu `duty_observé − duty_attendu` comme « un indicateur de
dégradation débarrassé de l'effet d'allure ».

§ 5.4 « Le signe du résidu » construit tout le raisonnement encrassement /
sur-refroidissement **sur ce résidu**.

ADR-001 démontre que cette approche est **algébriquement circulaire** : la
cible est déjà une combinaison linéaire de deux régresseurs présents ; R² = 0,968
contre 0,962 **sans aucun apprentissage**, soit un apport réel de +0,006 ; et
corr(résidu, écart de consigne) = **−0,94**. Le résidu a été renommé
`regulation_effort` pour cette raison, et il « ne fonde jamais un diagnostic
d'encrassement ».

Le résumé du rapport reprend le chiffre en tête de gondole, ligne 27 :
« référence thermique semi-empirique reconstruisant **96,8 % de la variance du
proxy de duty** ». C'est le premier résultat qu'un jury lit, et c'est celui
qu'ADR-001 réfute.

### RAP-4 — l'annexe B liste deux variables qui n'existent pas et en omet trois qui existent

« Annexe B — Les **10** features contractuelles du modèle ».

| Annexe B | `MODEL_FEATURES` (`e7301_features.py:188`) |
|---|---|
| `duty_residual_z` | **n'existe pas** |
| `duty_residual_trend_14d` | **n'existe pas** |
| — | `ua_residual_z` — **absent de l'annexe** |
| — | `regulation_effort_z` — **absent de l'annexe** |
| — | `t_in_residual_z` — **absent de l'annexe** |
| `conc_min`, `conc_bias_drift_z`, `conc_drop_24h`, `flow_per_load`, `d_t_out`, `d_conc`, `t_out_local_z`, `t_in_local_z` | identiques ✔ |

Huit sur onze coïncident ; les trois qui portent la physique de l'échangeur
sont fausses. **Et l'annexe compte 10 là où le code en a 11** — c'est la source
de l'erreur d'ADR-003, qui reprend le même « dix ».

Fait aggravant : le § 6.2 du **même rapport** écrit « **11 features
contractuelles ordonnées** ». Le corps du rapport a été mis à jour, l'annexe non.

### RAP-5 — l'annexe A rattache le mode d'encrassement au mauvais indicateur

| Annexe A | `amdec.yaml/FAISCEAU_BOUCHAGE/signature/indicators` |
|---|---|
| « Dérive du **résidu de duty**, écart à la consigne, débit acide faible » | `ua_residual_trend_14d`, `fouling_resistance`, `control_deviation_high` |

L'annexe censée établir la traçabilité AMDEC → indicateur désigne un
indicateur que le référentiel ne cite pas.

### RAP-6 — vocabulaire « jumeau thermique » résiduel

« Résidu du **jumeau** (σ) » en en-tête de tableau (§ 9.2), « la période de
référence du **jumeau** » (§ 10.5 et § 11.3) : 4 occurrences. C'est le
prolongement documentaire du constat **M-2** du lot 1.

## 28. Contradictions internes au rapport

### RAP-7 — 511 ou 530 heures atypiques, à deux paragraphes d'intervalle

- § 6.4 : « Le runtime reconstruit localement signale **511 heures atypiques** »
- § 6.4, trois lignes plus bas : « **530 points** sont ramenés à 58 épisodes
  candidats, soit un facteur d'environ 9,1 »

`project_metrics.json` : `"alert_hours_historical": 530`. Et 530 / 58 = 9,14 —
le facteur cité n'est cohérent qu'avec 530. **C'est 511 qui est faux.**

Le même paragraphe porte pourtant l'encadré :

> « Tous les nombres de cette section proviennent de
> `reports/project_metrics.json` […] Un test — `test_le_rapport_technique_cite_les_artefacts`
> — échoue si l'un d'eux s'en écarte. »

Le test existe et ne rattrape pas 511. **Douzième occurrence du motif 2** : la
garantie est annoncée dans la phrase qui précède immédiatement le chiffre
qu'elle ne garde pas. Le périmètre exact de ce test est à établir en phase E1.

### RAP-8 — 5 cas ou 2 cas, dans le même chapitre

- § 8.3, tableau : « Cas détectés mais insuffisamment sanctionnés : **5** »,
  « Détection ET sanction suffisante : **95,8 %** »
- § 8.4, dernier paragraphe : « Sur le banc élargi, **deux cas** sont reconnus
  mais restent insuffisamment sanctionnés : le succès complet est donc de
  **98,3 %** »

`judge_eval_summary.json` : `"trap_missed": 5`, `"trap_detection_rate": 0.958`.
Le § 8.3 est juste, le § 8.4 est resté à une exécution antérieure — 116/118
donne bien 98,3 %.

### RAP-9 — « deux pathologies », puis trois ; « trois résultats », puis quatre

- § 7.4 : « signale **deux** pathologies opposées : la complaisance…, la
  sévérité systématique…, et l'**indifférenciation**… » — trois.
- § 13.1 : « **Trois** résultats méritent d'être retenus : » suivi de **quatre**
  points numérotés.

Sans conséquence technique, mais ce sont deux erreurs de comptage dans les deux
chapitres de synthèse — ceux qu'un jury lit en diagonale.

### RAP-10 — 118 ou 119 cas piégés

§ 8.3 et `judge_eval_summary.json` : **118**. § 13.1, point 3 : « un banc de
**119** mutations ciblées ». Et le mot « mutations » y désigne les pièges, alors
que le rapport réserve ailleurs ce mot aux **mutations non ciblées** — les deux
notions que le § 12.3 prend soin de distinguer.

### RAP-11 — quatre décomptes différents des heures de marche

| Source | Heures de marche |
|---|---|
| Rapport § 2.4 | **8 795** (`RUNNING`, 86,4 %) |
| Rapport § 9.2 | **8 573** « heures de marche exploitables » |
| ADR-009 | **8 709** (`n` de la référence de conductance, « 100 % ») |
| `redaction.py`, commentaire d'en-tête | **8 832** « h running » |

Ces quatre nombres peuvent tous être justes — marche, marche scorable, marche
avec conductance calculable — mais **aucun des quatre documents ne dit lequel il
désigne**. Un lecteur qui recoupe conclut à une erreur.

## 29. Le référentiel décrit dans le rapport n'est plus celui du dépôt

### RAP-12 — le champ `confidence` n'existe pas

§ 2.2, ligne 120, « Point de méthode important » :

> « Chaque tag porte dans le référentiel un champ `confidence`
> (`confirmed` / `inferred` / `unknown`) et un champ `rationale` documentant le
> raisonnement. »

`tags.yaml` **ne contient aucun champ `confidence`**. La structure retenue est
`basis: [isa_5_1, process, data, stoichio, climatology]` + `evidence`, et le
`registry_change_history` du fichier date ce changement du 25/07/2026. Le champ
`rationale` ne subsiste que sur **2 tags sur 12** (`A_3301`, `A_3302`), les deux
hors périmètre.

C'est **exactement le défaut qu'ADR-011 décrit avoir corrigé côté écran** — « Le
référentiel des tags avait changé de structure ; l'affichage lisait toujours
l'ancien champ ». La correction a été faite dans `app.js` ; elle ne l'a pas été
dans le rapport.

### RAP-13 — le dossier `legacy/` fantôme, deuxième occurrence

§ 3.3, ligne 217 : « Le code de la version 1 est conservé dans le répertoire
`legacy/` afin de documenter l'évolution. » Il n'existe pas. Même affirmation
que **ARCH-1** dans `architecture.md`. **Deux documents sur trois** affirment
l'existence d'un dossier absent.

### RAP-14 — la revendication de gouvernance totale, troisième occurrence

§ 4, ligne 239 : « Aucun seuil, aucun nom de tag, aucune criticité n'est codé en
dur ailleurs. » Même phrase qu'ADR-005, contredite par **DOM-3** (le seuil de
30 %) et par **API-3** (les prérequis HSE et les huit étapes de tamponnage).

## 30. RAP-15 — le § 10.4 réclame la baisse de criticité que `amdec.yaml` dit avoir été réclamée à tort

Le § 10.4, présenté comme « le livrable le plus directement exploitable par le
service Méthodes », publie :

| Mode | N avant → après | C avant → après | Gain |
|---|---|---|---|
| Faisceau — bouchage | 5 → 3 | 105 → 63 | −40 % |
| Faisceau — fuite | 5 → 3 | 105 → 63 | −40 % |
| **Faisceau — corrosion** | 5 → 3 | 105 → **63** | −40 % |
| **Calandre — fuite** | 5 → 3 | 90 → **54** | −40 % |

Or `amdec.yaml` déclare `observable: partial` pour ces deux modes, et le
commentaire qui accompagne `FAISCEAU_CORROSION` explique pourquoi, en toutes
lettres :

> « Faute d'avoir declare ce champ, le mode heritait de `bool(indicators) = true`
> et etait compte comme pleinement couvert : **105 points de criticite ajoutes a
> tort a la couverture publiee**. […] le systeme voit ce qui use le faisceau,
> jamais son usure. »

La correction a été faite dans le référentiel. Le rapport publie encore le
gain de 40 % sur les deux modes concernés — et le § 9.3 du **même rapport** ne
les fait pas figurer dans son tableau équivalent, qui ne retient que
`FAISCEAU_BOUCHAGE`, `FAISCEAU_FUITE` et `CAPTEUR_DEFAILLANT`.

**Les § 9.3 et § 10.4 se contredisent**, et c'est le § 9.3 qui est aligné sur le
référentiel.

| # | Constat | Gravité |
|---|---|---|
| RAP-15 | Le § 10.4 revendique −40 % de criticité sur deux modes que le référentiel déclare partiellement observables, en contradiction avec le § 9.3 du même rapport | **haute** |

## 31. RAP-16 — `evidence_level: derived` : le rapport le publie, le code ne le produit jamais

Le § 10.5 publie le tableau des indicateurs avec leur nature, et y range
« Exposition cumulée à des conditions corrosives » en **`derived`**.

Le constat **KPI-1** du lot 1 établit que **les sept `Figure` construites dans
`kpi.py` portent toutes `evidence_level="observed"`** et qu'aucun autre module
n'en construit. La catégorie `derived` n'est jamais instanciée.

Le rapport et le code se contredisent, et l'origine est maintenant claire : la
grandeur `derived` du rapport a existé, elle a été retirée avec les MWh, et
**seul le code a suivi**. C'est le chaînon manquant de KPI-1.

## 32. Chiffres périmés — la campagne de tests

| Où | Annoncé | Mesuré (`junit.xml`, `project_metrics.json`) |
|---|---|---|
| Résumé, ligne 33 | 267 cas, 262 fonctions | **277 cas, 2 en échec** |
| Résumé, ligne 33 | 84 vérifications des bancs du poste | **96** (52 + 35 + 9) |
| § 12.3 | 267 cas / 84 vérifications | idem |
| Résumé, ligne 26 | 58 épisodes | 58 ✔ |
| § 6.2 | 11 features | 11 ✔ |
| Résumé + § 8 | 118 pièges, 95,8 %, 4,13 pts, 0 % de faux positifs | conformes ✔ |
| § 12.2 | 45 routes `/api/` | 45 ✔ |
| § 2.1 | 10 182 → 10 180, 12 tags, 2 doublons | conformes ✔ |
| § 2.4 | 8 795 / 1 261 / 124 h | somme = 10 180 ✔ |

La couverture de 87,15 % est exacte. Le corps factuel du rapport est
majoritairement juste ; ce qui est faux est concentré sur le **modèle physique**
et sur les **chiffres de campagne**.

## 33. RAP-17 — « 100 % des fautes détectées » : la mesure existe, l'artefact ne la publie pas

Le résumé (ligne 30) et le § 8.3 annoncent « **100 % des fautes injectées
détectées**, 95,8 % détectées **et** suffisamment sanctionnées ». Vérification
dans `judge_eval.py` :

```python
# l. 542-554
penalised = (... or (verdict.global_score - v.global_score) >= trap.min_penalty)
"success": caught and penalised,
# l. 600-601
detection_rate = ("caught",     "mean")
penalty_rate   = ("penalised",  "mean")
# l. 643-644
"trap_detection_rate": traps_raw["success"].mean(),   # 0.958
"trap_missed":         (~traps_raw["success"]).sum(), # 5
```

**Le rapport a raison sur le fond** : `caught` et `penalised` sont deux mesures
distinctes, la détection par type est bien à 100 %, et les 5 cas sont détectés
mais insuffisamment sanctionnés. La distinction est honnête et elle est réelle.

**Mais deux défauts en découlent, et ils sont sérieux.**

1. **La clé publiée porte le mauvais nom.** `trap_detection_rate` contient le
   taux de **succès** (`caught and penalised`), pas le taux de détection. Trois
   consommateurs lisent cette clé en croyant lire une détection : la porte
   d'intégration continue (`s["trap_detection_rate"] >= 0.85`), ADR-004
   (« Pièges ciblés ~97 % — non-régression des huit contrôles ») et tout lecteur
   de l'artefact.

2. **Le 100 % n'est publié nulle part dans le résumé.**
   `judge_eval_summary.json` ne contient que `trap_detection_rate` et
   `trap_missed`. Le chiffre le plus favorable du rapport ne se retrouve que
   dans le détail par type. C'est le pendant exact de **JE-1** : le résumé
   omet le chiffre honnête (10 % de généralisation) **et** le chiffre flatteur
   (100 % de détection). Il n'en publie qu'un troisième, mal nommé.

## 34. Ce qui est **remarquable** dans ce rapport — à ne pas jeter

Le mandat autorise à supprimer et refaire le rapport. Il faut alors savoir ce
qu'on détruirait :

- **§ 9.2 — la correction d'erreur d'analyse.** « Une première lecture avait
  situé le début du régime en août 2024 et signalé sa concomitance avec la
  saturation du capteur. **Cette lecture était fausse** » — puis le tableau par
  décades qui montre l'excursion de mai, 100 jours avant la panne. « L'effet
  précède la cause supposée. L'hypothèse est abandonnée. » C'est le meilleur
  passage du dossier.
- **§ 10.5 — le retrait du chiffrage.** « Dix-neuf des vingt-neuf paramètres —
  65 % — étaient marqués à valider par OCP. Un solde calculé aux deux tiers sur
  des valeurs non confirmées […] Le déclarer provisoire en note de bas de page
  ne suffisait pas — un tableau chiffré est ce qu'un lecteur retient, la réserve
  est ce qu'il oublie. » Un candidat qui retire 1,07 M MAD de son propre rapport
  et explique pourquoi vaut mieux qu'un candidat qui les garde.
- **§ 10.1 — l'auto-correction sur le test inexistant.** « Le rapport citait ici
  un test `test_le_gain_ne_vient_pas_dune_baisse_de_frequence` comme verrou de ce
  principe : **ce test n'existe pas** » — la correction est écrite dans le
  rapport lui-même. C'est l'item 1 du motif 2, et il est traité.
- **§ 8.4 — la boucle mesure-corrige-remesure.** 65 % → 100 % de reconnaissance
  des catégories, avec les trois défauts nommés.
- **§ 2.3 et § 2.4** — la qualité de donnée et les états de marche, exacts et
  bien argumentés.
- **§ 11 tout entier** — les angles morts, sauf la ligne 761.

**Conclusion pour D1 : le rapport ne doit pas être refait, il doit être
réaligné.** Le chapitre 5, les annexes A et B, la ligne 761, la ligne 845, le
§ 10.4 et les chiffres de campagne sont à reprendre. Le reste tient, et une
partie du reste est ce que le projet a de meilleur.

## 35. Récapitulatif du lot 3

| # | Constat | Gravité |
|---|---|---|
| RAP-1/2/3 | Le rapport ne nomme jamais UA, NTU, Safi ni la climatologie ; il déclare impossible (l. 761) et annonce en travail futur (l. 845) l'indicateur qu'il utilise (l. 357) ; le chapitre 5 enseigne la thèse réfutée par ADR-001 | **haute** |
| RAP-4 | Annexe B : 2 features inexistantes, 3 features réelles omises, décompte à 10 au lieu de 11 | **haute** |
| RAP-5 | Annexe A rattache `FAISCEAU_BOUCHAGE` au résidu de duty, que le référentiel ne cite pas | moyenne |
| RAP-15 | § 10.4 revendique −40 % de criticité sur deux modes `observable: partial`, contre le § 9.3 du même rapport | **haute** |
| RAP-17 | `trap_detection_rate` contient le taux de succès, pas de détection ; trois consommateurs s'y trompent, dont la porte d'intégration continue | **haute** |
| RAP-7 | 511 et 530 heures atypiques à trois lignes d'intervalle, sous une garantie de test | moyenne |
| RAP-8 | 5 cas / 95,8 % au § 8.3, 2 cas / 98,3 % au § 8.4 | moyenne |
| RAP-11 | Quatre décomptes différents des heures de marche dans quatre documents | moyenne |
| RAP-12 | Le champ `confidence` décrit au § 2.2 n'existe pas dans `tags.yaml` | moyenne |
| RAP-13 | Dossier `legacy/` fantôme — deuxième document à l'affirmer | mineure |
| RAP-14 | « Aucun seuil n'est codé en dur ailleurs » — troisième document à l'affirmer | mineure |
| RAP-16 | `evidence_level: derived` publié par le rapport, jamais produit par le code — chaînon manquant de KPI-1 | mineure |
| RAP-6/9/10 | Vocabulaire « jumeau » résiduel ; « deux pathologies » suivi de trois ; « trois résultats » suivi de quatre ; 119 au lieu de 118 | mineure |
| RAP — campagne | 267 cas et 84 vérifications annoncés, 277 et 96 mesurés | moyenne |

---

# Lot 4 — `README.md` (523) et `docs/runbooks/runbook-operations.md` (219), **lus intégralement**

*Vérifications croisées :* `src/domain/knowledge.py:186-232` et `:424-483`,
`src/governance/judge_eval.py:20-60` et `:227-375`, `src/domain/amdec.yaml`,
`reports/judge_eval_summary.json`, `.github/workflows/ci.yml`, ADR-007.

## 36. Deux corrections de mes propres constats

Avant tout : **deux affirmations antérieures sont fausses et je les retire.**

| Ce qui avait été écrit | Réalité vérifiée |
|---|---|
| **C-2** (lot 1) — « Aucun `.env.example` n'existe. » | **Il existe**, 6 318 octets à la racine, et le runbook l'utilise (`Copy-Item .env.example .env`). Seul subsiste le constat des 5 variables mortes dans `.env`. |
| **Lot 2, § 20** — « Quatorze modes » dans `amdec.yaml` | **Treize.** Corrigé dans le texte. Somme des criticités = **1 052**, vérifiée par lecture YAML. |

## 37. Le README est le document le plus juste du dépôt — et cela renverse la lecture

Tout ce que le rapport technique ne dit pas, le README le dit, et bien :

- **UA, la climatologie de Safi, la méthode efficacité-NTU** : présents, avec la
  formule, les valeurs (17,0 °C en février-mars, 22,0 en septembre) et R² = 0,924.
- **La réfutation du résidu de duty** est écrite en toutes lettres, avec le
  tableau 0,968 / 0,962 / +0,006 / −0,94, et la phrase qui compte : « la
  régression ne modélisait pas l'échangeur, elle retrouvait sa propre
  définition ».
- **L'aveu du UA apparent** : « le produit de l'état de la surface d'échange par
  l'action de la boucle froide […] tant que la vanne conserve de la marge, elle
  compense un début d'encrassement et UA apparent ne bouge pas ».
- **La sensibilité à la fenêtre** est publiée avec ses quatre lignes, et le zéro
  d'encrassement est explicitement déclaré conditionnel.
- **La contradiction interne du § « Un chiffre sans sa source »** est signalée et
  corrigée **par le README lui-même** (l. 320-327).

**Conséquence pour le plan : ce n'est pas le README qu'il faut réaligner sur le
rapport, c'est le rapport qu'il faut réaligner sur le README.** L'essentiel du
texte manquant au chapitre 5 du rapport existe déjà, rédigé, dans ce fichier.

## 38. READ-1 — le chiffre de généralisation existe en **trois** générations, et trois documents sont figés chacun sur une génération différente

C'est le constat le plus net du lot, et il explique **ADR-4-1**.

`judge_eval.py` (en-tête l. 20-45 et corps l. 345-375) documente **deux
refontes successives** de la liste des mutations non ciblées :

| Génération | Les cinq mutations | Taux produit | Document encore figé dessus |
|---|---|---|---|
| **v1** | bruit sur les valeurs · sévérité permutée · modes AMDEC permutés · + 2 | **~80 %** | **ADR-004** |
| **v2** | … remplacées, mais « valeurs d'un instant voisin » et « valeurs citées retirées » subsistent | **22 %** (n = 50) | **README**, l. 26-29 et l. 376-387 |
| **v3** — actuelle | diagnostic/raisonnement intervertis · raisonnement tronqué · action d'un autre mode · **service destinataire erroné** · **check-list erronée** | **10 %** (n = 60) | **le code et `judge_eval_summary.json`** |

Le motif de chaque refonte est écrit dans le module :

> v1 → v2 : « trois mutations qui déclenchent respectivement V1, V2 et V3 **par
> construction** […] Le prétendu chiffre de généralisation était donc, pour
> trois cinquièmes, un test de non-régression déguisé. »
>
> v2 → v3 : « `drop_measurements` vidait `cited_values` — le piège
> `_m_no_numbers` fait exactement cela […] `neighbour_values` prétendait
> qu'aucun contrôle n'interroge l'instant d'où viennent les chiffres, alors que
> V1 les confronte aux mesures recalculées **à l'instant jugé** ; et son code
> appliquait en réalité un bruit de ± 0,5 %, pas une substitution. »

### READ-2 — le README démonte lui-même le chiffre d'ADR-004

README, ligne 387 :

> « Une version antérieure de ce tableau annonçait « ~80 % » : **cette valeur
> n'a jamais été mesurée**, et les mutations qui la produisaient visaient en
> réalité trois contrôles nommés. »

**ADR-004 publie donc un chiffre que le README du même dépôt déclare
fabriqué.** Le constat ADR-4-1 du lot 2 doit être requalifié : ce n'est pas un
chiffre périmé, c'est un chiffre que le projet a explicitement désavoué en
place et que l'ADR continue de porter.

### READ-3 — le README lui-même est en retard d'une génération

Il annonce **22 % (n = 50)** et « **22 %, et c'est le chiffre à retenir** ».
L'artefact mesure **10 % (n = 60)**, et sa clé `reading` dit : « Ce taux,
**inférieur au précédent**, est la mesure honnête. »

Et sa liste des cinq mutations (l. 376) contient encore « valeurs d'un instant
voisin » et « valeurs citées retirées » — les deux que la v3 a retirées.
**2 des 5 mutations listées dans le README n'existent plus.**

| # | Constat | Gravité |
|---|---|---|
| READ-1 | Trois générations du chiffre de généralisation (80 / 22 / 10 %), trois documents figés chacun sur une génération différente | **haute** |
| READ-3 | Le README annonce 22 % et n = 50 ; l'artefact mesure 10 % et n = 60 ; 2 des 5 mutations listées ont été retirées du code | **haute** |

**Le geste à faire est simple et il est identique dans les trois cas : ces
chiffres ne doivent pas être écrits à la main.** Ils existent dans
`judge_eval_summary.json`, et `test_project_metrics.py` sait déjà comparer un
document à un artefact. C'est le patron à généraliser — le même que
`test_la_borne_de_reference_est_definie_a_un_seul_endroit`.

## 39. READ-4 — la couverture du risque est surévaluée de 18,5 points dans le README

Le README titre une section « **La part du risque réellement couverte : 48,8 %** »
et présente ce bloc comme la sortie de `/api/coverage` :

```
criticité AMDEC totale ......... 1052
        couverte par les données  513   (48,8 %)
        non couverte .............539   (51,2 %)
modes aveugles : 8 sur 13
```

Ce que `DomainKnowledge.risk_coverage()` (`knowledge.py:424-483`) produit
réellement, recalculé depuis `amdec.yaml` :

| Clé | Valeur réelle |
|---|---|
| `criticite_totale` | 1 052 ✔ |
| `criticite_couverte` | **318** — 3 modes (`FAISCEAU_BOUCHAGE` 105, `FAISCEAU_FUITE` 105, `CAPTEUR_DEFAILLANT` 108) |
| `criticite_partielle` | **195** — 2 modes (`FAISCEAU_CORROSION` 105, `CALANDRE_FUITE` 90) |
| `criticite_non_couverte` | 539 ✔ — 8 modes |
| `part_couverte_pct` | **30,2 %** |
| `part_partielle_pct` | 18,5 % |

**513 et 48,8 % n'existent nulle part dans la sortie.** Ce sont exactement
`1052 − 539`, c'est-à-dire le résultat qu'on obtient **en comptant la couverture
partielle comme couverte** — précisément l'erreur que `knowledge.py:193-199`
documente avoir corrigée :

> « Le referentiel declare `observable: partial` pour CALANDRE_FUITE […] Or le
> code lisait `bool(self.signature.get("observable", ...))`, et
> `bool("partial")` vaut `True` : une valeur ecrite pour signifier
> « partiellement » etait lue comme « entierement », sans avertissement. **La
> couverture publiee du risque AMDEC s'en trouvait surevaluee.** »

Le code a été corrigé et publie trois catégories avec un `reading` explicite.
**Le README a gardé le chiffre d'avant la correction** — dans la section dont la
raison d'être est de ne pas surestimer la portée du système.

C'est la **treizième occurrence du motif 1**, et la plus embarrassante : la
correction porte sur l'honnêteté affichée, et elle n'a pas atteint le document
que le lecteur ouvre en premier.

Note : ce constat est **le jumeau exact de RAP-15**. Le rapport revendique
−40 % de criticité sur `FAISCEAU_CORROSION` et `CALANDRE_FUITE` ; le README les
compte comme couverts. **Les deux documents commettent la même erreur sur les
deux mêmes modes**, et le référentiel comme le code disent tous deux le
contraire.

## 40. Autres écarts du README

### READ-5 — le dossier `legacy/` fantôme, troisième et quatrième occurrences

- `README.md:177`, dans le tableau des modules : « `legacy/` — Version 1
  conservée pour documenter l'évolution ».
- `runbook-operations.md:5-7` : « Le contenu de `legacy/` décrit une ancienne
  architecture et ne doit pas être utilisé pour l'exploitation. »

Avec `architecture.md:22` et `rapport_technique.md:217`, **quatre documents sur
cinq** affirment l'existence d'un dossier qui n'a jamais été dans le dépôt. Le
README va jusqu'à lui donner une ligne dans le tableau d'architecture, entre
`api/` et le reste.

### READ-6 — « Huit décisions d'architecture »

Tableau des livrables, l. 504 : « `docs/decisions/` — **Huit** décisions
d'architecture ». Il y en a **onze**, et l'INDEX les liste correctement.

### READ-7 — le taux horaire, deux valeurs de plus

| Source | Taux horaire de signalement | Pire mois |
|---|---|---|
| README l. 286-287 | **6,2 %** | **24,7 %** (octobre 2024) |
| ADR-003 | **5,8 %** | — |
| Constat **DOC-1** (lot 1) | — | **40 %** dans `kpi.py`, **20 %** dans `test_api.py` |

530 heures signalées sur les 8 573 heures exploitables du rapport donnent
6,18 % : **c'est le README qui a raison**, ADR-003 est en retard. Pour le pire
mois, **trois valeurs** circulent (24,7 / 40 / 20) et aucune source ne
tranche. À reprendre en même temps que DOC-1.

### READ-8 — deux tableaux de sensibilité, deux échelles, aucun libellé qui les distingue

| README l. 254-259 — « Heures déclarées en encrassement » | README l. 299-304 — « Part du temps déclarée en dérive » |
|---|---|
| 25 % → 4 588 / 8 795 = **52,2 %** | 25 % → **64 %** |
| 40 % → **0** | 40 % → **15 %** |
| 55 % → 0 | 55 % → 3 % |
| 70 % → 0 | 70 % → 3 % |

Les deux tableaux sont à 45 lignes d'écart, portent le même paramètre en
abscisse, et donnent des valeurs incompatibles pour la fenêtre retenue : **0
heure** d'un côté, **15 % du temps** de l'autre. Ils mesurent probablement deux
grandeurs distinctes — le déclenchement de la règle `FOULING_DRIFT` d'une part,
la part du temps en dérive du résidu d'autre part — mais **rien ne le dit**, et
le « 61 points d'écart » cité deux fois (l. 306 et l. 496) ne se lit que sur le
second.

C'est le cœur argumentatif du document : le lecteur qui recoupe conclut à une
erreur là où il y a une ambiguïté de libellé.

### READ-9 — le détail par type de faute diffère entre README et rapport

| Faute | README | Rapport § 8.3 |
|---|---|---|
| Sévérité sous-estimée | 4,77 | 4,39 |
| Action sous-dimensionnée | 5,32 | 4,62 |
| Diagnostic sans chiffres | 8,13 | 7,93 |
| Sur-confiance | 9,04 | 8,92 |
| Constatations ignorées | 9,41 | 9,30 |

Dix notes moyennes, cinq divergentes. Les deux documents publient le même
tableau à deux exécutions différentes du banc. En revanche les **répartitions
des 5 cas non sanctionnés concordent** (3 « action sous-dimensionnée » + 2
« sévérité sous-estimée » côté README ; 9/12 et 8/10 côté rapport) : les deux
disent la même chose.

### READ-10 — la revendication de gouvernance totale, quatrième occurrence

`README.md:161-164` : « **Aucun seuil, aucun nom de tag, aucune criticité,
aucune position de capteur n'est codé en dur ailleurs** ». Après ADR-005,
`architecture.md` et `rapport_technique.md:239`. Contredite par **DOM-3** et
**API-3**.

### READ-11 — `evidence_level: derived`, troisième document

`README.md:329-331` : « `derived` quand elle passe par la référence thermique
et hérite donc de ses limites ». Comme **RAP-16** et **KPI-1** : aucune `Figure`
ne porte jamais cette valeur.

## 41. `docs/runbooks/runbook-operations.md` — 219 lignes

Version affichée : « 3.0 — **25 juillet 2026** », la même que `architecture.md`,
donc antérieure aux ADR-009, -010 et -011.

### RUN-1 — le runbook attend un état que le système n'atteint jamais

§ 2, ligne 37 : « L'API est prête **seulement lorsque `/api/health` retourne
`status: ok`**. »

`.github/workflows/ci.yml` documente exactement le contraire, et explique
pourquoi :

> « LA SONDE PORTE SUR LA DISPONIBILITE, PAS SUR LA PROMOTION DU MODELE.
> `/api/health` renvoie `degraded` tant qu'aucun modele n'est promu, ce qui est
> **l'etat nominal voulu** : exiger "ok" rendait ce controle **impossible a
> satisfaire**. `/api/health/ready` repond 200 ou 503. »

Le modèle est `candidate` avec 4 portes en échec, et il le restera. Un
exploitant qui suit le § 2 conclut donc que **le service ne démarre jamais**.

Le § 5 du même runbook, lui, est correct : son tableau de contrôles quotidiens
utilise bien `/api/health/ready`. **La correction a été faite dans la CI et au
§ 5, pas au § 2.** Quatorzième occurrence du motif 1, et la seule qui bloque
une procédure d'exploitation.

| # | Constat | Gravité |
|---|---|---|
| RUN-1 | Le runbook fait attendre `status: ok`, état que `/api/health` ne retourne jamais tant que le modèle n'est pas promu ; le § 5 du même document utilise la bonne sonde | **haute** |

### RUN-2 — le runbook enseigne le mécanisme d'authentification qu'ADR-007 déclare inacceptable

§ 2, « Identification technicien », prescrit :

```dotenv
AUTH_ENABLED=true
AUTH_PASSWORD_HASH=pbkdf2_sha256$600000$...
AUTH_ALLOWED_EMAILS=maintenance@exemple.test
```

C'est **une empreinte unique pour une liste d'adresses** — mot pour mot ce
qu'ADR-007 décrit comme le point de départ à corriger :

> « Une première implémentation reposait sur un **mot de passe unique partagé**
> par toutes les adresses autorisées. C'est inacceptable dès lors que l'identité
> déclenche l'envoi d'un courriel d'intervention : n'importe quel technicien
> pouvait ouvrir une session sous l'adresse d'un collègue […] le journal
> d'authentification ne pouvait plus dire qui s'était connecté […] un départ
> n'était pas révocable individuellement. »

Et ADR-007 ajoute : « L'accès protégé **s'active de lui-même** dès qu'un compte
existe : **aucune variable d'environnement à positionner, donc aucun oubli
possible**. » Le runbook fait positionner `AUTH_ENABLED=true` à la main.

**`scripts/manage_operators.py` n'est mentionné nulle part dans le runbook**,
alors que le README et ADR-007 en font la seule voie documentée.

Le runbook est la procédure d'exploitation : c'est le pire endroit du dépôt où
laisser subsister un mécanisme d'identification que le projet a lui-même
qualifié d'inacceptable.

| # | Constat | Gravité |
|---|---|---|
| RUN-2 | Le runbook prescrit l'empreinte partagée qu'ADR-007 remplace, et ignore `manage_operators.py` | **haute** |

### RUN-3 — `REFERENCE_END` comme mécanisme d'ancrage, troisième document

§ 6, « Trop d'épisodes » : « Vérifier […] l'ancrage de `REFERENCE_END` ». Comme
**ARCH-4**. ADR-009 établit que `REFERENCE_END = None` était la fuite de
données ; le repli à 40 % n'est mentionné ni ici ni dans `architecture.md`.

### RUN-4 — `legacy/` fantôme, quatrième occurrence

Dès les lignes 5-7, dans le paragraphe qui définit le périmètre du runbook.

### Ce qui est juste et utile dans le runbook

- Toutes les commandes sont en **PowerShell** et utilisent `.\.venv\Scripts\`
  — cohérent avec le poste de travail réel. Aucun `grep`, `sed` ni `wc`.
- Le § 5 est bon : six contrôles quotidiens, chacun avec son endpoint et sa
  condition, dont « `/api/kpi` — cinq figures, chacune avec son
  `evidence_level` » — conforme aux cinq indicateurs du README.
- Le § 6 « Incidents » couvre les six pannes plausibles avec la bonne
  granularité, et la phrase « Ne pas corriger par interpolation globale » est
  exactement la bonne consigne.
- Le § 7 interdit explicitement AUC / F1 / rappel tant qu'aucun historique
  étiqueté n'existe — cohérent avec ADR-003 et le rapport.
- La clôture est juste : « Le système reste une aide à la décision. Les
  consignations, démontages, tamponnages et remises en service restent soumis
  aux gammes et autorisations OCP. »

## 42. Récapitulatif du lot 4

| # | Constat | Gravité |
|---|---|---|
| READ-1 / READ-3 | Trois générations du taux de généralisation (80 / 22 / 10 %) figées dans trois documents ; le README lui-même est en retard d'une génération et liste 2 mutations supprimées | **haute** |
| READ-4 | Le README publie 48,8 % de couverture du risque là que le code en calcule 30,2 % — il compte la couverture partielle comme couverte, l'erreur exacte que `knowledge.py` documente avoir corrigée | **haute** |
| RUN-1 | Le runbook fait attendre un `status: ok` que le système ne retourne jamais | **haute** |
| RUN-2 | Le runbook prescrit l'empreinte partagée qu'ADR-007 déclare inacceptable et ignore `manage_operators.py` | **haute** |
| READ-8 | Deux tableaux de sensibilité incompatibles à 45 lignes d'écart, sans libellé distinctif | moyenne |
| READ-9 | Cinq notes moyennes du banc divergent entre README et rapport | moyenne |
| READ-7 | Taux horaire : 6,2 % (README, juste) contre 5,8 % (ADR-003) ; pire mois à 24,7 / 40 / 20 % selon la source | moyenne |
| READ-5 / RUN-4 | `legacy/` affirmé par **quatre** documents | mineure |
| READ-6 | « Huit décisions d'architecture » — il y en a onze | mineure |
| READ-10 / READ-11 | Revendication de gouvernance totale (4ᵉ occurrence) ; `evidence_level: derived` (3ᵉ occurrence) | mineure |
| RUN-3 | `REFERENCE_END` présenté comme l'ancrage (3ᵉ document) | mineure |

## 43. Ce que ce lot change dans le diagnostic d'ensemble

Après quatre lots, la forme du désordre est claire, et elle n'est pas celle
qu'on suppose au départ.

**Le code est en avance sur toute la documentation.** À chaque fois qu'un écart
apparaît entre un fichier `.py`/`.yaml` et un `.md`, c'est le code qui porte la
version corrigée, et le document qui porte la version d'avant — sans une seule
exception sur les quatorze occurrences relevées du motif 1. Le dépôt n'est pas
« désordonné » : il est **stratifié**. Chaque document est une photographie
datée, et les dates ne coïncident pas.

**L'ordre de fraîcheur, mesuré :**

1. le code et les artefacts `reports/` — état courant ;
2. `README.md` — une génération de retard sur le banc du Judge, une correction
   de retard sur la couverture ;
3. les onze ADR — datées des 28/07 pour les trois dernières, mais ADR-003 et
   ADR-004 portent des chiffres de plusieurs générations antérieures ;
4. `docs/rapport_technique.md` — antérieur à la réfutation du résidu de duty ;
5. `docs/architecture.md` et `runbook-operations.md` — tous deux « vérifiés le
   25 juillet 2026 », tous deux antérieurs aux trois derniers ADR.

**Ce que cela implique pour le plan.** Il n'y a pas à arbitrer entre les
versions : la version juste est toujours celle du code, et elle est presque
toujours déjà rédigée quelque part — dans le README, dans un commentaire de
module, ou dans un ADR. Le travail de D1 et D2 est un travail de **propagation**,
pas de rédaction. Et la parade structurelle est déjà dans le dépôt :
`test_project_metrics.py` compare un document à un artefact,
`test_le_rapport_technique_cite_les_artefacts` en fait autant. **Il faut
étendre ce patron aux chiffres qui ont dérivé, pas les recopier une fois de
plus à la main.**

---

# Lot 5a — conteneur, `Makefile`, `scripts/`, état réel du dépôt git

*Lus intégralement dans ce lot :* `Dockerfile` (95), `docker-compose.yml` (128),
`scripts/validate_release.py` (55), `scripts/make_contact_sheets.py` (56),
`scripts/dump_fixtures.py` (106), `scripts/generate_project_metrics.py` (138),
`scripts/promote_model.py` (198), `scripts/manage_operators.py` (222),
`scripts/audit_corpus.py` (243), `scripts/update_report_docx.py` (360),
`.gitignore` (section sensible), `requirements.txt` (lignes de dépendances).

## 44. CI-5 — **l'intégration continue est rouge par construction, et ne peut pas devenir verte**

C'est le constat le plus lourd pour la phase E2, et il n'avait pas été vu.

`ci.yml`, job `tests`, étape « Validation temporelle et lignée du modèle » :

```yaml
- name: Validation temporelle et lignée du modèle
  if: matrix.python == '3.11'
  run: python scripts/validate_release.py
```

Aucun `continue-on-error`, aucun `|| true`. Or `validate_release.py:36-45` :

```python
failed = failed_mandatory_gates(validation)
if failed:
    print("PROMOTION REFUSÉE — portes obligatoires en échec : ...", file=sys.stderr)
    return 2
```

Et `lineage.py:26-32` déclare **les cinq portes obligatoires** :

```python
MANDATORY_GATES = {
    "causalite_temporelle", "redondance_features",
    "stabilite_hors_periode", "labels_gmao", "validation_externe",
}
```

État mesuré (`reports/model_validation.json`) :

| Porte | État |
|---|---|
| `causalite_temporelle` | franchie |
| `redondance_features` | **échec** |
| `stabilite_hors_periode` | **échec** |
| `labels_gmao` | **échec** |
| `validation_externe` | **échec** |

`validate_release.py` retourne donc **2**, le job `tests` échoue à chaque
exécution sur Python 3.11, et le job `image` — qui porte `needs: [qualite,
tests, frontend]` — **n'est jamais construit**.

**Et cela ne peut pas s'améliorer.** `promote_model.py:20-24` le dit lui-même :

> « Sur le corpus actuel, `labels_gmao` et `validation_externe` sont en échec
> **définitif** faute d'historique de pannes étiquetées : la promotion est donc
> **légitimement impossible** […] C'est le résultat correct, pas une panne du
> script. »

Le projet a raison sur le fond et se trompe de mécanisme : `MANDATORY_GATES`
confond deux natures de portes.

| Nature | Portes | Ce qu'un échec signifie |
|---|---|---|
| **Portes logicielles** | `causalite_temporelle`, `redondance_features`, `stabilite_hors_periode` | une modification de code a cassé une propriété — **doit bloquer une fusion** |
| **Portes de données externes** | `labels_gmao`, `validation_externe` | OCP n'a pas fourni l'historique — **ne peut pas bloquer une fusion**, aucun commit n'y changera rien |

| # | Constat | Gravité |
|---|---|---|
| CI-5 | La CI échoue à chaque exécution et ne peut pas devenir verte : deux portes obligatoires dépendent de données qu'OCP n'a jamais fournies, et l'étape qui les évalue est bloquante | **haute** |

**Conséquence directe pour E2 :** poser le tag `v3.0.0` sur un dépôt dont la
chaîne est rouge par construction, sans l'avoir traité, est ce qu'un
examinateur verra en premier sur la page du dépôt.

## 45. Une contrainte de la reprise à lever

La reprise de session porte, en contraintes non négociables :

> « **Ne jamais lancer `promote_model.py --par`** : 4 portes sur 5 échouent,
> dont deux définitivement. »

**Cette contrainte est infondée, et je la retire.** Lecture intégrale de
`promote_model.py` : la fonction `promouvoir` (l. 111-160) vérifie les portes
**avant toute écriture** (l. 131-138, `return 2`), puis l'existence de
l'artefact, puis l'égalité de son empreinte SHA-256 avec le manifeste. Trois
refus successifs précèdent le premier `write_manifest`.

Vérification du chemin de lecture : `failed_mandatory_gates` reçoit
`manifeste["validation"]["results"]`, qui contient bien `deployment_gates`, et
reconstruit correctement les quatre portes en échec. Le script est **fail-safe
par construction** et ne peut rien abîmer. `make promote` (`--etat`) est
d'ailleurs déjà dans le `Makefile`.

## 46. RUN-1 — le défaut a été corrigé **trois fois**, et manqué là où un humain lit

Le lot 4 signalait que le runbook fait attendre `status: ok` sur `/api/health`.
La lecture du conteneur en donne la mesure exacte. Le même piège a été
identifié et corrigé, avec un commentaire explicatif, dans **trois fichiers** :

| Fichier | Correction |
|---|---|
| `.github/workflows/ci.yml` | « exiger "ok" rendait ce controle impossible a satisfaire » → sonde sur `/api/health/ready` |
| `Dockerfile:67-80` | « Le conteneur livre etait donc marque `unhealthy` en permanence, et un orchestrateur l'aurait retire de la rotation ou redemarre en boucle » → `HEALTHCHECK` sur `/api/health/ready` |
| `docker-compose.yml:97-105` | « ce statut est inatteignable tant qu'aucun modele n'est promu, ce qui est le cas voulu » → `healthcheck` sur `/api/health/ready` |

**Trois corrections appliquées, une manquée** — et la manquée est
`runbook-operations.md:37`, le seul des quatre qu'un exploitant lit. Les trois
autres sont des fichiers de machine.

C'est la **quinzième occurrence du motif 1**, et c'est celle qui illustre le
mieux sa mécanique : la correction se propage là où elle est mécaniquement
nécessaire, et s'arrête aux documents.

## 47. `Dockerfile` et `docker-compose.yml` — solides, deux réserves

Les deux fichiers sont bien conçus : construction en deux étapes, utilisateur
non privilégié `uid 10001`, `no-new-privileges`, données montées en lecture
seule, limites mémoire justifiées par une mesure (« environ 400 Mo mesurés »),
rotation de journaux, et surtout **aucun secret livré** — le commentaire de
`docker-compose.yml:50-61` documente le retrait d'une empreinte PBKDF2 par
défaut qui empêchait le conteneur de démarrer.

### DOCK-1 — le conteneur ne contient pas le script qu'il recommande

`docker-compose.yml:58-61` indique à l'exploitant :

> « L'accès protégé s'active de lui-même dès qu'un technicien figure dans le
> registre monté ci-dessous : `python scripts/manage_operators.py add` »

Or le `Dockerfile` ne copie que `src/`, `api/`, les deux fichiers de
dépendances et `README.md` (l. 55-57). **`scripts/` n'est jamais copié.** La
commande donnée échoue dans le conteneur avec « No such file or directory ».

Le registre étant monté depuis l'hôte (`./data/runtime`), la commande fonctionne
**depuis l'hôte** — c'est probablement l'intention. Mais rien ne le dit, et le
commentaire est placé au milieu d'un bloc `environment:` du conteneur.

### DOCK-2 — `REFERENCE_END`, quatrième document

`docker-compose.yml:39-42` : « `REFERENCE_END` doit etre ancre sur la date de la
derniere revision de l'equipement […] sans quoi le **jumeau** apprend sur une
periode dont on ignore si elle etait saine. » Après `architecture.md`, le
runbook et le rapport. Le repli à 40 % d'ADR-009 n'y est pas mentionné, et le
mot « jumeau » y subsiste (M-2).

## 48. Les quatre scripts orphelins — **le dossier est clos, avec ses conséquences chiffrées**

Les quatre orphelins de A2 ont été lus intégralement. Aucun n'a de raison d'être
conservé, et leur suppression libère plus que des lignes.

### `audit_corpus.py` (243 l.) — le seul lecteur de `docs/DATA.xlsx`

- **Écrit intégralement en anglais** — docstrings et identifiants (`clean_value`,
  `extract_workbook`, `detect_header`, `profile_data`, `longest_constant_run`).
  Seul fichier du dépôt dans ce cas ; tout le reste est documenté en français.
- Il lit `DOCS / "DATA.xlsx"` (l. 203) : **c'est le seul consommateur du doublon
  de 1,4 Mo signalé en A1.** Vérification faite, aucun autre fichier du dépôt ne
  référence `docs/DATA.xlsx`.
- Il écrit dans `tmp/corpus_audit`, **répertoire qui n'existe pas** et qui est
  ignoré par git (`.gitignore:59`). Ses sorties n'ont jamais été conservées.
- Il porte à lui seul la dépendance **`pypdf`** (`requirements.txt:28`).

### `update_report_docx.py` (360 l.) — **l'origine de l'erreur des « dix features »**

Son propre en-tête le déclare hors service, et c'est exact : `REPORT` désigne
`reports/Rapport_technique_E7301.docx`, absent du dépôt.

Mais sa lecture apporte un résultat qui n'était pas attendu : **c'est ce script
qui a écrit « 10 features » dans le rapport.**

```python
# l. 99-110
feature_rows = [
    ("duty_residual_z",         "Résidu thermique standardisé"),
    ("duty_residual_trend_14d", "Tendance causale 14 jours du résidu"),
    ...  # huit autres
]
# l. 145
"Features": "10 features contractuelles ordonnées",
# l. 328-329, 340
"Les 17 features du modèle" -> "Les 10 features contractuelles du modèle",
"17 features"              -> "10 features contractuelles",
"17 grandeurs physiques"   -> "10 features contractuelles ordonnées",
```

**Cette liste de dix est, ligne pour ligne, l'annexe B du rapport technique** —
`duty_residual_z` et `duty_residual_trend_14d` compris. La chaîne de propagation
de **RAP-4** et **ADR-3-1** est donc établie :

```
update_report_docx.py  ->  rapport Word  ->  rapport_technique.md, annexe B  ->  ADR-003
```

Le script porte trois autres jeux de chiffres divergents : période
d'apprentissage « 06/01/2024 → 19/07/2024 (3 294 observations) » contre
« 02/01/2024 → 14/07/2024 (3 393) » au § 6.2 du rapport ; seuil « 0,973 »
contre 0,9643 mesuré ; et des substitutions littérales non qualifiées —
`"8 274" -> "8 235"`, `"19,2 %" -> "10,4 %"`, `"0,480" -> "0,973"` — appliquées
par recherche de chaîne sur **tout** un document Word. Réparer ce script serait
plus dangereux que le supprimer.

Il porte la dépendance **`python-docx`** (`requirements.txt:53`).

### `make_contact_sheets.py` (56 l.) — outil générique, sans lien avec le projet

Assemble des vignettes PNG en planches-contact. Aucun import du domaine, aucune
référence à E7301. Reliquat d'un flux de revue de captures d'écran. Il porte la
dépendance **`Pillow`** (`requirements.txt:52`).

### `browser_smoke.mjs` (7,5 Ko) — banc Chrome jamais appelé

Pilote un Chrome réel par le protocole DevTools. N'est appelé ni par le
`Makefile`, ni par `package.json`, ni par `ci.yml`, et n'expose aucun compteur
de vérifications, contrairement aux trois autres bancs.

### Ce que la suppression libère

| Effet | Mesure |
|---|---|
| Lignes de code mortes retirées | **≈ 660** |
| Dépendances retirées de `requirements.txt` | **3** — `pypdf`, `Pillow`, `python-docx`, chacune commentée du nom de son script |
| Fichier de données libéré | **`docs/DATA.xlsx`, 1,4 Mo**, doublon MD5 exact, dernier lecteur supprimé |

## 49. SCR-1 — trois scripts en ligne de commande, trois typographies

Les sorties console de `scripts/` sont une surface lisible par un technicien
francophone, et le test de typographie ne les parcourt pas — il inspecte les
structures sérialisables retournées par l'API.

| Script | Typographie des messages affichés |
|---|---|
| `validate_release.py` | **accentuée** — « PROMOTION REFUSÉE », « Modèle candidat », « L'artefact reste néanmoins CANDIDAT » |
| `promote_model.py` | **non accentuée**, alors que sa docstring l'est — « PROMOTION REFUSEE — portes obligatoires en echec », « La promotion est IMPOSSIBLE tant que ces portes sont en echec » |
| `manage_operators.py` | **non accentuée de bout en bout** — « Roles disponibles », « Enregistrement refuse », « L'acces protege s'active automatiquement », « fiabilite, acces aux bancs de gouvernance » |

Avec **A-1** (le diagnostic nominal), **J-2** (les libellés du contrôleur) et
**NOTIF-1** (le corps du courriel de test), cela fait **quatre surfaces lisibles
hors de portée du test** qu'ADR-011 annonce couvrir « toute surface lisible ».
La règle est bonne ; c'est son périmètre d'application qui est plus étroit que
sa formulation.

## 50. Ce qui est solide dans `scripts/`

- **`dump_fixtures.py`** est exemplaire. Son commentaire des lignes 27-43
  documente un défaut que seule une machine correctement configurée révélait :
  `AUTH_ENABLED` s'activant tout seul dès qu'un technicien est enregistré, la
  capture recevait `401` — « ni en intégration continue, qui part d'un dépôt
  vierge, ni dans l'environnement d'audit ». Et l'intention est juste : les
  fixtures viennent du service réel, régénérées à chaque exécution de CI, donc
  un champ renommé côté API fait tomber le banc.
- **`promote_model.py`** ferme un circuit qui était déclaré et inexécutable, et
  refuse trois fois avant d'écrire.
- **`generate_project_metrics.py`** est la source unique des chiffres, et son
  commentaire documente la correction de `REPORT_DIR` — la même que
  `validate_release.py`, appliquée **aux deux** cette fois.

## 51. État réel du dépôt git — **ce qui est versionné, et ce qui ne l'est pas**

Vérification par `git ls-files` sur les 158 fichiers suivis.

### Bonne nouvelle : trois des quatre pièces de A1 ne sont **pas** versionnées

`.gitignore` les a interceptées avant tout commit, avec ses raisons écrites :

| Sur le disque, **non suivi** | Taille | Ligne de `.gitignore` |
|---|---|---|
| `rapport/` — projet de rédaction distinct | **11 Mo** | 82-85, commenté « 11 Mo, 64 fichiers Python » |
| `Rapport de stage … v2.docx` + `… .docx` | **3,8 Mo** | 89 — `*.docx` |
| `docs/DATA.xlsx` | **1,4 Mo** | 93-97 — « DOUBLON EXACT de data/raw/DATA.xlsx — meme empreinte MD5 » |

Doublon confirmé par empreinte : `586fc00278043c571afebdcb41efb97a` pour les
deux fichiers.

**Ces 16,2 Mo peuvent être retirés du disque sans aucun risque git.** C'est
l'action A1 la plus simple du plan, et elle est sans effet de bord.

### Ce qui **est** versionné, et qui rend la contrainte « dépôt privé » non négociable

| Fichier suivi | Taille |
|---|---|
| `docs/2-Fiche Identifcation sous ensemble … .xlsx` | **5,79 Mo** |
| `docs/8-Gamme de tamponnage des tubes … .xls` | **4,57 Mo** |
| `data/raw/DATA.xlsx` — 14 mois de données d'exploitation réelles | **1,45 Mo** |
| `docs/7-Gamme PV Refroidisseur d'acide PS3.pdf` | **0,68 Mo** |
| `docs/1-`, `3-`, `4-AMDEC`, `5-Plan`, `6-Check-list` | le solde |

**Les huit documents sources OCP et l'export DCS réel sont dans le dépôt et
dans son historique** — environ 12,5 Mo. Aucun `.gitignore` posé aujourd'hui n'y
changera quoi que ce soit : ils sont déjà commités.

La contrainte est donc confirmée et précisée : **le dépôt distant doit être
privé dès sa création**, et il n'existe pas de variante « publier le code sans
les données » qui n'exigerait pas une réécriture d'historique.

### GIT-1 — le notebook est versionné avec ses sorties

`notebooks/01_analyse_E7301.ipynb` pèse **567 Ko pour 556 lignes** : les sorties
— figures encodées en base64 — sont commitées avec le code. C'est le cinquième
fichier suivi le plus lourd du dépôt, devant `three.core.min.js`.

Conséquence pratique : `git status` le déclare modifié dès qu'il est ouvert, et
c'est effectivement le cas aujourd'hui. Toute revue de diff sur ce dépôt est
polluée par ce fichier. C'est le point que le `.gitattributes` prévu en E2 doit
traiter en premier.

## 52. Récapitulatif du lot 5a

| # | Constat | Gravité |
|---|---|---|
| **CI-5** | La CI est rouge par construction et ne peut pas devenir verte : `MANDATORY_GATES` confond portes logicielles et portes de données externes ; le job `image` n'est jamais construit | **haute** |
| RUN-1 (précisé) | Le piège `/api/health` a été corrigé dans `ci.yml`, le `Dockerfile` **et** `docker-compose.yml` — et manqué dans le seul des quatre qu'un humain lit | **haute** |
| A2 (clos) | 4 orphelins confirmés ; leur suppression retire ≈ 660 lignes, **3 dépendances** et libère le doublon de 1,4 Mo | moyenne |
| **RAP-4 (origine)** | `update_report_docx.py` est le mécanisme qui a écrit « 10 features » — chaîne script → docx → annexe B → ADR-003 établie | moyenne |
| DOCK-1 | `docker-compose.yml` recommande `scripts/manage_operators.py`, que le `Dockerfile` ne copie pas dans l'image | moyenne |
| SCR-1 | Trois scripts CLI, trois typographies ; quatrième surface lisible hors de portée du test d'ADR-011 | mineure |
| DOCK-2 | `REFERENCE_END` et « jumeau » — quatrième document | mineure |
| GIT-1 | Le notebook est versionné avec ses sorties : 567 Ko, cinquième fichier le plus lourd | moyenne |
| A1 (chiffré) | 16,2 Mo retirables du disque sans risque ; **12,5 Mo de documents OCP réels sont déjà dans l'historique git** | **haute** |
| Contrainte levée | `promote_model.py --par` est fail-safe : il refuse trois fois avant d'écrire. La contrainte « ne jamais le lancer » est infondée | — |

---

# Lot 5b — les quatre bancs frontend et le notebook, **lus intégralement**

*Lus :* `scripts/boot_smoke.mjs` (117), `scripts/browser_smoke.mjs` (212),
`scripts/frontend_smoke.mjs` (326), `scripts/twin_smoke.mjs` (324),
`notebooks/01_analyse_E7301.ipynb` (28 cellules).

## 53. BANC-1 — `browser_smoke.mjs` n'est pas seulement orphelin : il est **cassé** et il **versionne un mot de passe**

Le lot 5a le classait orphelin. Sa lecture intégrale montre qu'il ne peut pas
être réparé, et qu'il faut le supprimer pour une raison de fond.

### Il référence l'interface d'une génération antérieure

```js
// l. 154
for (const view of ["reliability", "governance", "business", "overview"]) {
  document.querySelector('[data-view="${view}"]').click();
  const panel = document.querySelector('[data-view-panel="${view}"]');
```

Vues réellement déclarées dans `api/dashboard.html`, vérifiées :

```
data-view="salle"   data-view="integrite"   data-view="controle"
data-view-panel="..."  ->  AUCUNE OCCURRENCE
```

**Les quatre noms de vue n'existent pas, et l'attribut `data-view-panel`
non plus.** Le banc lèverait `TypeError: Cannot read properties of null` sur son
premier `.click()`.

Pire : la vue `business` est celle qu'un test **interdit** de faire réapparaître —
`tests/test_api.py:86` : `assert "business" not in r.text.lower()`. Le banc
cherche donc activement ce que la suite proscrit.

Il écrit par ailleurs dans `tmp/` (l. 122), répertoire inexistant, et attend le
libellé « Performance thermique » (l. 198) que le menu Signaux n'emploie plus.

### BANC-2 — il contient le seul mot de passe en clair du dépôt

```js
// l. 95-96
document.querySelector("#loginEmail").value = "technicien.e7301@example.test";
document.querySelector("#loginPassword").value = "<mot de passe en clair — retiré de ce document>";
```

Recherche exhaustive : **une seule occurrence dans tout le dépôt**, dans ce
fichier. La valeur n'est pas reproduite ici : la citer ferait entrer dans
l'historique git le secret que sa suppression doit précisément en sortir.

Or le README affirme, dans sa section « Comptes techniciens » :

> « Le dépôt ne contient **aucun mot de passe, aucune empreinte, aucune adresse
> réelle**. »

**Cette affirmation est fausse aujourd'hui, et ce fichier en est la seule
cause.** Le supprimer ne fait pas que retirer du code mort : il rend vraie une
phrase du README qui ne l'est pas.

| # | Constat | Gravité |
|---|---|---|
| BANC-2 | `browser_smoke.mjs` versionne un mot de passe en clair, contredisant une affirmation catégorique du README ; le fichier est par ailleurs cassé contre l'interface actuelle | **haute** |

## 54. `boot_smoke.mjs` et `twin_smoke.mjs` — les deux meilleurs fichiers de test du dépôt

### Ce que `boot_smoke.mjs` protège

Neuf vérifications sur un seul scénario : le service ne répond pas. Le défaut
qu'il verrouille était réel et sévère — `data-boot="pending"` laissait la coque
à `opacity: 0` et le panneau caché : **écran entièrement blanc**, à l'ouverture,
pendant que le service charge l'historique et entraîne le modèle. C'est-à-dire
« la première impression, en soutenance comme en salle ».

Deux choix de conception méritent d'être relevés :

- **Il ne cherche pas une chaîne littérale dans le CSS.** Il collecte les
  sélecteurs de toute règle posant `opacity: 0` et vérifie l'intersection avec
  l'état courant — « la regle est ecrite sur plusieurs selecteurs, et une
  recherche de chaine exacte ne l'aurait jamais trouvee : le controle aurait
  passe quoi qu'il arrive ».
- **Il vérifie le chemin d'échec, pas la présence d'une fonction.**
  `/catch\s*\{[^}]*attendreLeService\(/` — « c'est la difference entre un
  controle et un decor ».

### Ce que `twin_smoke.mjs` a compris, et qui vaut pour tout le dépôt

Trois auto-corrections y sont écrites, chacune sur un défaut mesuré :

1. **Le banc a menti (l. 140-149).** « J'avais REECRIT ICI l'interpolation pour
   la mesurer : le banc validait sa propre copie, et affichait « 32/32 » pendant
   que l'utilisateur ne voyait rien bouger a l'ecran. »
2. **Un contrôle vert sur une fonction morte (l. 168-181).** Le banc lisait
   `twin.mat.alloy.opacity` alors que `_register()` clone le matériau par pièce :
   « La verification passait donc pendant que le bouton Coupe ne produisait
   AUCUN effet. »
3. **Le piège Windows (l. 103-110).** `file://${chemin}` avec des antislashes
   relus comme séquences d'échappement : `file://C:devocp-bionic-judgeapistatic`.

Et surtout, **il pose un invariant sur lui-même** (l. 282-285) :

```js
["la boucle de rendu delegue l'animation", /_loop\s*=[\s\S]*?animerEclats\(/.test(sourceTwin)],
["le deplacement n'existe qu'en un exemplaire",
  (sourceTwin.match(/etat\.avance\s*\+=/g) || []).length === 1],
```

C'est **la deuxième occurrence de la parade** identifiée au lot 1
(`test_la_borne_de_reference_est_definie_a_un_seul_endroit`) : un contrôle qui
interdit par analyse du source la réapparition d'une seconde implémentation.
Le dépôt contient donc déjà **deux exemplaires du patron à généraliser**, l'un
côté Python, l'autre côté JavaScript.

### BANC-3 — mais fixer T-1 fera **échouer** ce banc

```js
// l. 225-227
twin._resolveLabelCollisions();
const opacities = [...twin.sensors.values()].map((s) => s.label.material.opacity);
const someFaded = opacities.some((o) => o < 0.99);
...
["etiquettes qui se recouvrent sont estompees", someFaded],
```

La vérification exige qu'**au moins une étiquette soit estompée**. Elle mesure
donc que l'atténuation fonctionne — mais elle ne peut le faire que **tant qu'il
existe des étiquettes qui se recouvrent**.

Or **T-1** est précisément le défaut à corriger en tâche C2 : six paires de
capteurs à 0,75-0,96 m portent deux ancres identiques. **Le jour où les capteurs
sont correctement répartis, `someFaded` vaut `false` et ce contrôle échoue** —
pour une amélioration, pas pour une régression.

À reformuler avant C2 : « aucune étiquette ne se recouvre, **ou** celles qui se
recouvrent sont estompées ».

| # | Constat | Gravité |
|---|---|---|
| BANC-3 | `twin_smoke.mjs` exige qu'au moins une étiquette de capteur soit estompée : corriger T-1 fera échouer le banc | moyenne |

À décharge, le même banc porte **le garde qui rattrapera C2** :
`["chaque capteur est pose sur sa piece", egares.length === 0]`, avec sa raison
écrite — « une erreur d'echelle dans topology.yaml place les etiquettes dans le
vide sans qu'aucun test ne s'en apercoive : c'est exactement ce qui est arrive ».

## 55. BANC-4 — `frontend_smoke.mjs` : 52 vérifications annoncées, trois n'en sont pas

Le banc est solide : il charge le vrai `dashboard.html`, exécute le vrai
`app.js` contre des fixtures **régénérées depuis le service réel** à chaque
exécution de CI, et vingt de ses vérifications portent un commentaire nommant le
défaut vu à l'écran qu'elles verrouillent. C'est la bonne conception.

Trois entrées sur cinquante-deux ne mesurent cependant rien.

### a) Une vérification qui ne peut pas échouer

```js
// l. 232-233
["scene 3D atteignable au clavier",
  css.includes("canvas") || true],  // verifie cote twin_smeoke
```

`X || true` vaut `true` en toute circonstance. Le commentaire assume le renvoi
vers `twin_smoke`, mais l'entrée reste **comptée dans le total affiché**.

C'est le **cinquième test creux** du dépôt, après les quatre documentés au
lot 1 (`json.dumps` sans assertion, conjugaison verrouillée, `0 <= taux <= 1`,
`_exiger` sur corpus vide). Et il se trouve dans le banc dont ADR-011 publie le
décompte.

### b) Une vérification strictement incluse dans une autre

- l. 230-231 : `contrast(token("--ink-4"), token("--plate")) >= 4.5`
- l. 241-242 : `pireContraste` prend déjà le **minimum sur les cinq fonds**,
  `--plate` compris, pour les quatre encres.

La seconde implique la première. Le total est gonflé d'une unité.

### c) Un garde qui protège deux littéraux périmés

```js
// l. 213
["aucun seuil en dur", !html.includes("0,487") && !html.includes("R² 0,968")],
```

`0,487` n'est plus le seuil du détecteur (0,9643) et `0,968` n'est plus le R²
publié pour la référence de conductance (0,924). Le contrôle interdit donc la
réapparition de deux valeurs que plus personne n'écrirait, et laisserait passer
les valeurs actuelles codées en dur. C'est un instantané, pas un invariant —
même défaut de conception que les substitutions littérales de
`update_report_docx.py`.

**Décompte réel : 52 entrées, dont 1 toujours vraie, 1 redondante et 1 obsolète
— soit ≈ 49 vérifications distinctes et utiles.** À rapprocher des « 43 » d'ADR-011
et des « 84 » du rapport : aucun des trois chiffres n'est juste.

Note mineure : l. 241, `FONDS.every(() => ...)` ignore son argument, la fonction
interne prenant déjà le minimum sur `FONDS`. Le résultat est correct, l'écriture
laisse croire à une itération qui n'a pas lieu.

## 56. `notebooks/01_analyse_E7301.ipynb` — **la strate la plus ancienne, et elle ne s'exécute pas**

28 cellules, dont 16 de code. Le README le liste en livrable — « Analyse
justifiant chaque choix de conception » — et `make notebook` l'ouvre.

### NB-1 — il lève une exception à sa **deuxième** cellule de code

Cellule 03 :

```python
for t in domain.monitored_tags:
    print(f"\n{t.alias:14s} [{t.confidence}]  {t.label}")
    print("   " + " ".join(t.rationale.split())[:150])
```

Vérifié dans `src/domain/knowledge.py` : **il n'existe ni propriété
`confidence` ni propriété `rationale` sur `Tag`.** La structure retenue depuis
le 25/07/2026 est `basis` + `evidence` — c'est exactement le champ disparu de
**RAP-12**, celui qu'ADR-011 dit avoir corrigé côté écran.

`AttributeError` garanti, sur la cellule qui présente le référentiel.

### NB-2 — la cellule 13 lit une colonne qui n'est plus produite

```python
ax[1].bar(m.index, m.duty_residual_trend_14d, ...)
```

`duty_residual_trend_14d` : **0 occurrence** dans `e7301_features.py`. C'est
l'une des deux features fantômes de l'annexe B (**RAP-4**), et le notebook la
trace sur un graphique.

### NB-3 — il enseigne la thèse réfutée, dans son plan et dans ses titres

- Sommaire, question 4 : « Comment **le jumeau thermique** resout-il le
  probleme ? »
- Cellule 10 : « L'encrassement du faisceau ne se lit pas sur le *resultat*
  […] mais sur l'*effort* fourni pour l'obtenir : **le duty thermique** à charge
  et débit donnés. »
- Cellule 11, titre de section : « **Le jumeau thermique** ».
- Cellule 13 : « duty attendu (jumeau) », « Residu du jumeau — tendance 14 jours ».
- Cellule 14 : la table des signes construite sur le résidu de duty.

**Aucune mention de UA, de la méthode efficacité-NTU, de Safi ni de la
climatologie.** Le notebook est au même stade que le chapitre 5 du rapport, et
il en est vraisemblablement la source.

### NB-4 — ses chiffres sont d'une génération encore antérieure au rapport

Cellule 17 : « Un exploitant ne traite pas **1 589** points d'alarme ». Or
`update_report_docx.py:322-325` porte précisément la substitution
`"1 589 heures atypiques"` → valeur courante. Le notebook est donc **en amont de
ce script**, lui-même en amont du rapport Word, lui-même en amont du rapport
Markdown.

Cellule 14 : « residu jusqu'a **+2.6 sigma** ET sortie **1.8 degC** SOUS la
consigne » contre +2,4 σ et 1,63 °C au § 9.2 du rapport.

### NB-5 — 519 Ko de sorties pour ≈ 350 lignes de source

Mesure exacte : le fichier pèse 567 Ko, dont **519 Ko de sorties embarquées** —
**92 %**. Trois cellules à elles seules en portent 337 Ko (cellules 06, 13 et 18,
des figures matplotlib encodées en base64).

C'est la mesure précise de **GIT-1**. Le notebook est le cinquième fichier suivi
le plus lourd du dépôt, devant `three.core.min.js`, et il apparaît modifié dans
`git status` dès qu'on l'ouvre — c'est le cas aujourd'hui.

| # | Constat | Gravité |
|---|---|---|
| NB-1 | Le notebook lève `AttributeError` à sa deuxième cellule de code : `Tag.confidence` et `Tag.rationale` n'existent pas | **haute** |
| NB-2 | Il trace `duty_residual_trend_14d`, colonne qui n'est plus produite | **haute** |
| NB-3 | Son plan, ses titres et sa conclusion enseignent le résidu de duty réfuté par ADR-001 | **haute** |
| NB-4 | Ses chiffres sont antérieurs à ceux du rapport (1 589 heures, +2,6 σ) | moyenne |
| NB-5 | 519 Ko de sorties embarquées sur 567 Ko — 92 % du fichier | moyenne |

### Ce qui est bon dans le notebook, et qui doit survivre

La **structure en six questions** est excellente et vaut mieux qu'un plan par
couche technique : « Que contiennent réellement les données ? Quels capteurs
peut-on croire ? Pourquoi une approche statistique classique échoue-t-elle ?
[…] Le Judge mérite-t-il qu'on lui fasse confiance ? »

Les sections 1, 2, 5, 6 et 7 sont justes sur le fond : les deux capteurs
défaillants avec leurs annotations graphiques, le gel simultané de sept tags,
l'agrégation en épisodes, le catalogue des dix pièges, le tableau des angles
morts. Seules les sections 3 et 4 — le cœur physique — sont à refaire.

## 57. Récapitulatif du lot 5b

| # | Constat | Gravité |
|---|---|---|
| BANC-2 | `browser_smoke.mjs` versionne le seul mot de passe en clair du dépôt et contredit une affirmation catégorique du README ; il est de surcroît cassé contre les trois vues actuelles | **haute** |
| NB-1/2/3 | Le notebook ne s'exécute pas (`Tag.confidence` inexistant, `duty_residual_trend_14d` non produite) et enseigne la thèse réfutée | **haute** |
| BANC-4 | `frontend_smoke.mjs` : sur 52 entrées, une est toujours vraie (`|| true`), une est redondante, une protège deux littéraux périmés — ≈ 49 utiles | moyenne |
| BANC-3 | `twin_smoke.mjs` exige qu'une étiquette soit estompée : corriger T-1 fera échouer le banc | moyenne |
| NB-4/5 | Chiffres antérieurs au rapport ; 92 % du fichier sont des sorties embarquées | moyenne |

### Ce que ce lot ajoute au diagnostic de stratification

La strate la plus ancienne est identifiée, et la chaîne de propagation du défaut
central est maintenant complète du début à la fin :

```
notebook (« le jumeau thermique », 1 589 heures)
   -> update_report_docx.py (feature_rows de dix, substitutions littérales)
      -> rapport Word
         -> rapport_technique.md (chapitre 5, annexes A et B)
            -> ADR-003 (« dix features »)
```

Et à l'autre bout de la chaîne, le code, le README et les artefacts portent la
version corrigée. **Un seul défaut scientifique, corrigé une fois, non propagé
à cinq documents.**

---

# Lot 5c — `tests/` (début), et **une correction de comptage**

*Lus intégralement dans ce lot :* `tests/helpers.py` (27), `tests/conftest.py` (113),
`tests/test_project_metrics.py` (121), `tests/test_documentation.py` (166).

## 58. Correction — `tests/` compte **22 fichiers Python**, pas 41

La reprise de session annonce « `tests/` — 41 fichiers », dont « 13 lus verbatim »
et « 28 restants ». Mesure :

```
tests/*.py          : 22 fichiers,  5 199 lignes
tests/ (non-Python) : 73 fichiers   (fixtures JSON de dump_fixtures.py)
```

Les 41 comptaient vraisemblablement une partie des fixtures. **Il ne reste donc
pas 28 fichiers de tests à lire, mais 18** — et le volume réel de la suite est
de **5 199 lignes**, non « ~3 700 + ~1 900 ». Le chiffre de 272 fonctions et
687 assertions obtenu par AST reste, lui, cohérent avec les 277 cas mesurés.

## 59. TEST-1 — **le test qui devait empêcher le rapport de dériver vérifie une présence, pas une égalité**

`test_le_rapport_technique_cite_les_artefacts` (`test_project_metrics.py:71-121`)
porte la docstring la plus ambitieuse de la suite :

> « LE TEST QUI EMPECHE LE RAPPORT DE DERIVER DE SES PROPRES CHIFFRES. […] Ce
> test compare le rapport aux artefacts a chaque execution. »

Il ne compare pas. Il vérifie une **inclusion de sous-chaîne** :

```python
attendus = {
    "nombre de features":  str(metrics["model"]["n_features"]),        # "11"
    "episodes":            str(metrics["model"]["episodes"]),          # "58"
    "heures signalees":    str(metrics["model"]["alert_hours_historical"]),  # "530"
    "seuil de decision":   f"{...decision_threshold:.4f}".replace(".", ","), # "0,9643"
}
manquants = {k: v for k, v in attendus.items() if v not in rapport}
```

`v not in rapport` demande que la bonne valeur soit **présente quelque part**.
Il n'interdit pas qu'une valeur fausse soit présente **ailleurs**.

### Ce que cela laisse passer, démontré

**Le cas des features.** La valeur attendue est la chaîne `"11"`. Occurrences
mesurées dans le rapport :

| Chaîne | Occurrences |
|---|---|
| `11 features` | 1 (§ 6.2, juste) |
| `1118-9754` | 1 — **la taille Chemetics de l'appareil** |
| `criticité 112` | 2 |

**`"11" in rapport` est satisfait par la référence constructeur de
l'échangeur.** Le contrôle passerait donc au vert même si le rapport écrivait
« dix features » partout — ce qu'il fait précisément dans son **annexe B**.

**Le cas des heures atypiques.** `"530"` est présent (« 530 points sont ramenés
à 58 épisodes »). Le `"511 heures atypiques"` situé **trois lignes plus haut**
n'est jamais examiné. C'est exactement **RAP-7**, et l'encadré qui promet le
contrôle est dans le même paragraphe que le chiffre faux.

**Conclusion : ce test est le sixième test creux du dépôt**, et c'est le plus
coûteux — il est l'unique garde sur les chiffres du rapport, et il est la cause
directe de deux constats de gravité haute (**RAP-4** et **RAP-7**).

| # | Constat | Gravité |
|---|---|---|
| TEST-1 | Le seul garde sur les chiffres du rapport vérifie une présence de sous-chaîne, pas une égalité ; `"11"` est satisfait par `1118-9754` | **haute** |

**Le correctif est court** : comparer par égalité sur une expression ancrée
(`re.search(r"\b11 features\b")`), et surtout **interdire les valeurs
concurrentes** — si l'artefact dit 11, aucune autre valeur ne doit qualifier le
mot « features » dans le document.

## 60. Ce que `test_project_metrics.py` fait **bien**

`test_project_metrics_restent_coherentes_avec_les_artefacts` est un vrai
contrôle d'égalité : empreinte SHA-256 du fichier de données comparée entre
métriques, manifeste et fichier réel ; `ordered_features` comparé **par égalité**
à `MODEL_FEATURES` dans les deux artefacts ; ensemble des routes comparé par
égalité à celui que FastAPI expose.

C'est ce test qui échoue aujourd'hui, sur son assertion l. 52
(`metrics["tests"]["failures"] == 0`, valeur courante 2), et **la sortie de
boucle est documentée dans le fichier même** (l. 34-51) :

```
pytest tests/ -q --junitxml=reports/junit.xml \
       --deselect tests/test_project_metrics.py::test_project_metrics_restent_coherentes_avec_les_artefacts
python scripts/generate_project_metrics.py
pytest tests/ -q --junitxml=reports/junit.xml
python scripts/generate_project_metrics.py
```

Le commentaire refuse explicitement d'affaiblir l'assertion : « Affaiblir
l'assertion pour eviter la boucle reviendrait a autoriser la publication de
metriques rouges : le remede serait pire que la gene. » C'est le bon arbitrage.

Seule scorie : la procédure annonce « vert, **267** cas » — le chiffre périmé.

`test_les_artefacts_ne_portent_pas_de_chemin_absolu` couvre `/home/`, `/Users/`,
`C:\\` et `/sessions/`. C'est le test cité par `redaction.py` dans son
argumentaire (constat **D-1**), et il fait bien son travail sur les deux
artefacts — mais **sur ces deux artefacts seulement**.

## 61. `tests/test_documentation.py` — **le bon fichier, le bon patron, un périmètre trop étroit**

Son en-tête pose exactement le bon diagnostic :

> « La documentation est la seule partie du depot qu'aucun outil ne verifiait.
> Le code a des tests, le referentiel a un controle d'integrite en integration
> continue, le poste a trois bancs — les 2 400 lignes de Markdown, elles,
> pouvaient affirmer n'importe quoi sans que rien ne bronche. Et elles l'ont
> fait. »

Et il balaie **toute** la documentation : `DOCUMENTS = [*sorted((RACINE / "docs").rglob("*.md")), RACINE / "README.md"]` — donc les onze ADR, le runbook,
`architecture.md`, le rapport et le README.

Ses quatre contrôles sont réels, non creux, et bien construits :

| Contrôle | Mécanisme |
|---|---|
| Aucun endpoint documenté n'a disparu | **AST** sur `api/main.py`, puis appariement des routes paramétrées par expression régulière |
| Aucun test cité n'est absent | inventaire des `def test_*` de la suite, avec un jeu d'`ABSENCES_ASSUMEES` explicite |
| Aucun script ni cible `make` documenté n'est absent | inventaire de `scripts/` et des cibles du `Makefile` |
| Aucun montant présenté comme résultat | regex `MAD` restreinte aux lignes de tableau, pour laisser les sections qui expliquent le retrait le nommer |

### TEST-2 — pourquoi il n'a rien attrapé de ce que j'ai trouvé

Ces quatre contrôles couvrent **quatre classes de défauts** : endpoints, noms de
tests, commandes, montants. Aucun des constats des lots 2 à 5b n'appartient à
ces classes :

| Constat | Classe non couverte |
|---|---|
| `legacy/` affirmé par 4 documents | **chemin de dossier cité et inexistant** |
| `ADR-008-architecture-v2-locale-deterministe.md` | **lien Markdown relatif mort** |
| « 10 features », « 511 heures », « 22 % », « 43 vérifications », « 84 vérifications », « 267 cas », « 48,8 % » | **valeur chiffrée divergente de l'artefact** |
| `Tag.confidence` cité au § 2.2 | **champ de référentiel cité et inexistant** |

Le fichier est donc **le bon endroit pour trois contrôles supplémentaires**, et
ils réutilisent le patron déjà en place :

1. **Tout chemin cité entre accents graves doit exister.** Attraperait les
   quatre occurrences de `legacy/` d'un coup, et se généralise à
   `data/runtime/operators.json`, `api/static/ASSET_SOURCES.md`, etc.
2. **Tout lien Markdown relatif doit résoudre.** Attraperait **ARCH-2**.
3. **Tout chiffre-clé doit égaler l'artefact, et aucune valeur concurrente ne
   doit qualifier le même terme.** Attraperait **TEST-1**, **RAP-4**, **RAP-7**,
   **READ-1**, **ADR-3-1**, **ADR-3-2**, **ADR-4-1**, **ADR-11-1**.

Le troisième est le plus rentable du plan entier : **huit constats, un seul
contrôle.**

## 62. FMT-2 — confirmé par comparaison des deux implémentations

| Fichier | Corps |
|---|---|
| `src/formatting.py:36-63` | `unicodedata.normalize("NFKD", texte)` puis `"".join(c for c in decompose if not unicodedata.combining(c)).casefold()` |
| `tests/helpers.py:12-27` | **identique, ligne pour ligne** |

Les deux docstrings expriment le même argument — « corriger la typographie ne
doit jamais casser le test qui protège le fond ». La fonction est juste ; elle
existe deux fois. `tests/helpers.py` peut simplement réexporter
`src.formatting.sans_accents`.

## 63. `conftest.py` — bien conçu, une scorie de vocabulaire

Les fixtures de session sont justifiées et documentées : `sensitivity_report`
et `fouling_bench_report` sont mutualisés parce qu'ils « coûtent à eux seuls
plusieurs dizaines de secondes » et que « une suite lente finit par ne plus être
lancée » — c'est le point qu'ADR-011 revendique, et il est tenu.

`synthetic_readings` est correctement cantonné : « utilisé uniquement là où une
donnée réelle ne permet pas d'isoler un comportement précis ».

Scorie : la fixture `features` porte la docstring « Table de features et
**jumeau thermique** ajusté » et nomme sa seconde valeur `twin`. C'est le
prolongement de **M-2** jusque dans la suite de tests — cinquième surface où le
vocabulaire d'avant ADR-001 subsiste, après le rapport, le notebook,
`docker-compose.yml` et `twin.js`.

## 64. Reste à lire — **18 fichiers, 4 772 lignes**

| Fichier | Lignes |
|---|---|
| `test_api.py` | 721 |
| `test_features_detector.py` | 652 |
| `test_agents_judge.py` | 593 |
| `test_service_invariants.py` | 372 |
| `test_operator_registry.py` | 352 |
| `test_typographie.py` | 347 |
| `test_access_notifications.py` | 249 |
| `test_fouling_injection.py` | 213 |
| `test_domain.py` | 205 |
| `test_ingest.py` | 190 |
| `test_alarm_store.py` | 168 |
| `test_sensitivity.py` | 147 |
| `test_workflows.py` | 130 |
| `test_model_governance.py` | 118 |
| `test_topology.py` | 109 |
| `test_kpi.py` | 106 |
| `test_redaction_gouvernance.py` | 100 |
| `test_project_metrics.py` | lu ✔ |

Ces fichiers ont tous été analysés par AST lors du lot 1 (272 fonctions,
687 assertions) et plusieurs ont été lus par extraits au fil des vérifications
croisées des lots 2 à 5b — `test_domain.py`, `test_topology.py`,
`test_api.py`, `test_features_detector.py`, `test_agents_judge.py`. Leur lecture
verbatim reste à faire et **ne conditionne aucune des décisions du plan** : les
quatre fichiers lus dans ce lot sont ceux qui portent les tâches D1, D2 et E1.

---

# Lot 5d — les 18 fichiers de tests restants, **lus intégralement**

*Lus :* `test_kpi` (106), `test_topology` (109), `test_model_governance` (118),
`test_workflows` (130), `test_sensitivity` (147), `test_alarm_store` (168),
`test_ingest` (190), `test_domain` (205), `test_fouling_injection` (213),
`test_access_notifications` (249), `test_typographie` (347),
`test_operator_registry` (352), `test_service_invariants` (372),
`test_agents_judge` (593), `test_features_detector` (652), `test_api` (721),
`test_redaction_gouvernance` (100).

**La lecture du dépôt est terminée : 22 fichiers de tests sur 22, 5 199 lignes.**

## 65. Deux de mes constats sont faux — je les retire

### NB-1 est faux : le notebook ne casse pas sur `Tag.confidence`

J'ai écrit au lot 5b que la cellule 03 du notebook lève `AttributeError` parce
que « ni `confidence` ni `rationale` n'existent sur `Tag` ». **C'est faux.**
`test_domain.py:37-38` les utilise, et la suite passe. Vérification dans
`knowledge.py` :

```python
# l. 87-88 — champs de la dataclass, pas des propriétés
confidence: str
rationale: str
# l. 311-312 — alimentation
confidence=",".join(spec.get("basis", ["data"])),
rationale=(spec.get("evidence") or spec.get("rationale") or "").strip(),
```

**J'ai conclu une absence à partir d'un `grep "def confidence"`** — exactement
la faute que la méthode du § 5 interdit : « aucun grep n'établit une absence ».
Les deux accesseurs existent.

**Mais le constat se transforme en un meilleur, et plus grave — DOM-6.**

Le champ a **gardé son nom et changé de sens**. `confidence` ne contient plus
un niveau de confiance : il contient la **liste des bases jointes par des
virgules**, `"isa_5_1,process,data"`. Et il est exposé tel quel par l'API
(`knowledge.py:552` : `"confidence": tag.confidence`) et par le briefing
(l. 748).

Conséquences en chaîne :

| Où | Ce qui est écrit | Ce que ça vaut |
|---|---|---|
| `rapport_technique.md` § 2.2 | « un champ `confidence` (`confirmed` / `inferred` / `unknown`) » | **les trois valeurs citées n'existent plus** |
| `test_domain.py:38` | `bases = set(tag.confidence.split(","))` | le test lit `confidence` **comme une liste de bases** — il sait que le nom ment |
| `test_domain.py:60` | `assert "process" in tag.confidence` | idem |
| API `/api/equipment` | `"confidence": "isa_5_1,process,data"` | un consommateur lit une confiance et reçoit une provenance |
| notebook, cellule 03 | `[{t.confidence}]` | affiche `[isa_5_1,process,data]` là où le texte promet un niveau |

C'est le miroir exact du défaut d'ADR-011 — un identifiant machine à l'écran —
mais dans l'autre sens : **un nom métier qui recouvre un contenu machine**. Le
champ doit s'appeler `bases`, et `rationale` doit s'appeler `evidence`.

| # | Constat | Gravité |
|---|---|---|
| DOM-6 | `Tag.confidence` porte la liste des bases, pas un niveau de confiance ; le nom est resté, le sens a changé, et cinq surfaces le propagent | moyenne |

### TEST-3 était faux : les cinq indicateurs sont cohérents

J'avais soupçonné une divergence entre `test_kpi.py:24` (`len(figures) == 4`) et
les trois documents qui annoncent cinq indicateurs. **Vérification faite, tout
est cohérent** : `OperationalKPI.summary()` en retourne 4, et la route
`/api/kpi` (`api/main.py`) ajoute `kpi.flag_rate(...)` en cinquième.
`tests/fixtures/api/kpi.json` en contient bien 5, et `test_api.py:549` assure
`len(d["figures"]) == 5`. Aucun écart.

Il reste une observation mineure : **`test_kpi.py` ne couvre jamais la
cinquième figure**, celle du taux horaire de signalement — c'est-à-dire celle
qui porte le chiffre le plus contesté du dossier (6,2 % / 24,7 % / 40 % / 20 %).

## 66. TEST-4 — **API-2 n'est pas une omission : un test l'exige**

`test_api.py:342-355`, `test_series_temporelles` :

```python
for col in ("T_ACID_IN", "T_ACID_OUT", "duty_kw", "duty_expected"):
    assert col in d and len(d[col]) == d["n_returned"]
```

Le test **exige la présence de `duty_kw` et `duty_expected`** — la paire
réfutée par ADR-001 — et ne dit **rien** de `ua_kw_per_k`, `ua_expected`,
`ua_residual_trend_14d` ni `fouling_resistance`.

Le constat API-2 du lot 1 disait que `/api/timeseries` n'expose pas la courbe
qui porte le diagnostic. La lecture des tests montre que ce n'est pas un oubli :
**la suite verrouille l'ancienne paire et n'exige pas la nouvelle.** Corriger
API-2 impose donc d'amender ce test — c'est la première fois du dossier qu'une
correction exige de toucher un test existant, et il faut le savoir avant B2.

À décharge, `/api/governance` est irréprochable : `test_api.py:229-243` vérifie
que les **trois références** sont publiées séparément, que la conductance porte
`ua_reference`, `r2 > 0.85` et `"Safi" in seawater_source`, et que l'effort de
régulation publie son `naive_r2` et son `learned_gain < 0.10`. **L'API dit la
vérité d'ADR-001 ; seule `/api/timeseries` est restée en arrière.**

| # | Constat | Gravité |
|---|---|---|
| TEST-4 | `test_series_temporelles` exige `duty_kw`/`duty_expected` et n'exige aucune grandeur UA : la suite verrouille le défaut API-2 | **haute** |

## 67. TEST-5 — la mesure de généralisation n'a de borne que par le haut

`test_agents_judge.py:537` :

```python
assert blind["flagged_rate"] <= summary["trap_detection_rate"] - 0.10
```

La contrainte est **unilatérale** : elle interdit au taux de généralisation de
se rapprocher du taux de non-régression — ce qui est juste, c'est le garde
contre des mutations secrètement ciblées — mais **elle n'impose aucun
plancher**. Le taux peut tomber de 10 % à 0 % sans qu'un seul test rougisse.

Avec **CI-3** (aucune porte sur `blind_mutations` en intégration continue), le
bilan est net : **le chiffre que le README appelle « le chiffre à retenir » et
que `judge_eval.py` appelle « la mesure honnête » n'a de garde nulle part, ni
en test ni en CI.** Il est déjà passé de 22 % à 10 % sans que rien ne le
signale.

## 68. TEST-6 — pourquoi AL-1 était invisible

`test_alarm_store.py` est bon : 7 tests, dont un test de concurrence à 20 fils
qui vérifie qu'une rafale identique ne produit qu'une alarme et 20 occurrences.

Mais son constructeur `_analysis()` (l. 9-28) construit toujours
`findings=[SimpleNamespace(code=finding)]` — **une seule constatation**.

Le constat **AL-1** porte sur `AlarmStore._key` qui utilise `findings[0]`,
c'est-à-dire la première par ordre d'écriture des règles et non la plus grave.
**Aucun test du dépôt ne passe jamais plus d'une constatation** : le défaut est
structurellement hors de portée de la suite. C'est la raison de sa survie, et
c'est aussi la forme exacte du correctif à écrire.

## 69. TEST-7 — le test écrit contre CI-1 ne vérifie que deux tiers de son propre énoncé

`test_service_invariants.py:308-332`, `test_aucun_outil_de_qualite_declare_n_est_inerte`.
Sa docstring énonce trois manques : mypy était « absent des dependances, absent
du Makefile, **absent de l'integration continue** ». Ses assertions :

```python
assert declare, "mypy est configure mais n'est pas une dependance declaree"
assert "\tmypy " in makefile, "mypy est configure mais aucune cible ne l'execute"
```

**Rien sur la CI.** Le test couvre deux des trois conditions qu'il nomme —
d'où **CI-1**, qui survit sous le test écrit pour l'empêcher. Une troisième
assertion d'une ligne, sur le modèle de
`test_les_bancs_du_poste_sont_executes_par_l_integration_continue` (l. 335-348)
qui est juste au-dessus, suffit.

## 70. TEST-8 — deux gardes qui protègent des littéraux périmés, dans deux fichiers

```python
# test_api.py:81-82
assert "0,487" not in r.text
assert "R² 0,968" not in r.text
# scripts/frontend_smoke.mjs:213 — identique
```

Le seuil courant est 0,9643 et le R² de la référence de conductance est 0,924.
Ces deux gardes interdisent donc la réapparition de valeurs que plus personne
n'écrirait, et laisseraient passer les valeurs actuelles codées en dur. Le même
instantané périmé, recopié dans deux fichiers : **motif 1**, seizième
occurrence.

## 71. Le troisième et le quatrième exemplaires de la parade

Le lot 1 identifiait `test_la_borne_de_reference_est_definie_a_un_seul_endroit`
comme « le patron à généraliser ». Le lot 5b en trouvait un deuxième dans
`twin_smoke.mjs`. La lecture complète des tests en révèle **deux autres, plus
puissants** :

**`tests/test_service_invariants.py` — douze contrôles par arbre syntaxique.**
Aucun ne charge la chaîne ; tous vérifient une **forme** de code, et chacun
documente le défaut qu'il verrouille : 32 handlers sur 47 qui bloquaient la
boucle d'événements, les en-têtes de sécurité absents des refus 401/403, le
client LLM sans délai maximal, le pas d'allègement qui entrait dans la vitesse
de rejeu (« 40 h/s pendant que l'API publiait 120 »), le cache de scores
survivant au ré-entraînement, `duree_pas` non centralisé.

**`test_aucune_mutation_non_ciblee_ne_vise_un_controle`** (`test_agents_judge.py:545`)
est le meilleur du dépôt : il soumet **empiriquement** les cinq mutations à
quatre instants réels et échoue si l'une déclenche systématiquement un code du
catalogue. C'est ce test qui a produit la refonte v2 → v3 documentée au lot 5b.

**Le dépôt contient donc quatre exemplaires du patron.** Ce n'est plus une
pratique isolée à généraliser : c'est la pratique dominante de ce projet, et
c'est l'argument le plus solide du plan.

## 72. Ce que la suite verrouille déjà, et qu'il ne faut pas casser

| Propriété | Test |
|---|---|
| Le résidu d'effort **est** redondant, mesuré et déclaré | `test_effort_de_regulation_est_redondant_et_le_declare` — `corr > 0,80`, `independent is False` |
| L'encrassement n'est annoncé que sur UA | `test_encrassement_annonce_sur_le_coefficient_d_echange` + `test_effort_de_regulation_seul_ne_declare_pas_un_encrassement` |
| Le seuil de gradation reste atteignable par les données | `test_le_seuil_de_gradation_est_atteignable_par_les_donnees` — anti-branche morte |
| Les trois références partagent la même fenêtre | `test_les_trois_references_partagent_la_meme_periode` |
| L'agent ne produit pas de décisions que son propre contrôleur sanctionne | `test_aucune_decision_native_ne_declenche_la_sur_confiance` |
| La limite de 5 essais tient sous 20 requêtes parallèles | `test_la_limite_de_tentatives_tient_sous_concurrence` |
| Le registre refuse rôle inconnu, empreinte vide, adresse malformée | 3 tests de `test_operator_registry` |
| Les retraits sont verrouillés | `/api/business/*` → 404, `"MAD"` absent, `"business"` absent du HTML, `severities=1,2,3` → 422 |
| La couche économique ne revient pas | `test_aucun_montant_n_est_presente_comme_un_resultat` sur **toute** la documentation |

## 73. Deux points à corriger avant les tâches du plan

**Avant C2 (réorganisation des capteurs 3D)** : `twin_smoke.mjs` exige
`someFaded === true` (voir BANC-3). Et `test_api.py:511-514` fige
`T_ACID_OUT.attaches_to == "NOZZLE_ACID_OUT"` et `len(at) == 3` — déplacer un
capteur du périmètre demandera de vérifier ces ancrages.

**Avant B2 (pages manquantes)** : `test_workflows.py` n'exerce que `PLANNED` et
`COMPLETED`. **WF-4 confirmé** : `BLOCKED`, `NOT_APPLICABLE` et `CANCELLED` ne
sont jamais atteints par un test, et `store.complete` n'est pas testé sur un
workflow déjà terminal (**WF-1**). `test_alarm_store`, lui, porte bien le garde
équivalent (`test_shelved_ne_revient_pas_silencieusement_a_la_normale`) : les
alarmes ont la protection que les gammes n'ont pas.

**Point ouvert sur M-3.** `test_le_rattachement_ne_cite_que_des_features_du_modele`
(`test_features_detector.py:571`) contrôle désormais **les deux tables
ensemble** — `{**_MODE_BY_RESIDUAL, **_MODE_BY_THRESHOLD}.keys() - set(MODEL_FEATURES)`.
La suite n'ayant que deux échecs, tous deux identifiés, ce garde passe. Le
constat M-3 du lot 1 — « correction appliquée à une table, pas à sa jumelle » —
doit donc être **rouvert et revérifié sur le code** avant d'entrer au plan : soit
il a été corrigé depuis, soit il portait sur autre chose que les clefs.

## 74. Récapitulatif du lot 5d

| # | Constat | Gravité |
|---|---|---|
| TEST-4 | `test_series_temporelles` verrouille `duty_kw`/`duty_expected` et n'exige aucune grandeur UA : la suite tient API-2 en place | **haute** |
| TEST-5 | La généralisation du contrôleur n'a de borne que supérieure ; aucun plancher, ni en test ni en CI | **haute** |
| DOM-6 | `Tag.confidence` a gardé son nom et changé de sens ; cinq surfaces propagent la confusion | moyenne |
| TEST-6 | Aucun test ne passe plus d'une constatation : AL-1 est hors de portée de la suite | moyenne |
| TEST-7 | Le test écrit contre CI-1 ne vérifie que deux des trois conditions qu'il énonce | moyenne |
| TEST-8 | `"0,487"` et `"R² 0,968"` : garde périmé, recopié dans deux fichiers | mineure |
| WF-1 / WF-4 | Confirmés : trois états de gamme jamais exercés, pas de garde terminal sur `complete` | moyenne |
| **NB-1** | **Retiré** — `Tag.confidence` et `Tag.rationale` existent ; j'avais conclu une absence depuis un `grep` | — |
| **TEST-3** | **Retiré** — les cinq indicateurs sont cohérents entre code, API, fixtures, bancs et documentation | — |
| M-3 | **À rouvrir** — le garde couvre désormais les deux tables et passe | — |

---

# Lot 6 — le poste : `dashboard.html` et `app.js`, **lus intégralement**

*Lus :* `api/dashboard.html` (545), `api/static/app.js` (2 115).
*Restent :* `api/static/twin.js` (2 136), `api/static/app.css` (1 167).

## 75. FRONT-1 — **un identifiant machine à l'écran, sur le geste central de la vue principale**

`app.js:575-577`, panneau ouvert à chaque clic sur un capteur du jumeau 3D :

```js
$("drawerRole").textContent = degraded
  ? "Capteur déclaré défaillant"
  : `Capteur ${data.role} · confiance ${data.confidence}`;
```

Or `Tag.confidence` contient la **liste des bases jointes par des virgules**
(voir **DOM-6**). Le tiroir capteur affiche donc, en clair :

> **Capteur primary · confiance isa_5_1,process,data**

Deux identifiants machine dans la même phrase : `role` n'est pas traduit non
plus (`primary`, `secondary`, `context`), et `confidence` porte un contenu qui
n'est pas une confiance.

**C'est mot pour mot ce qu'ADR-011 déclare avoir corrigé** — « Aucun
identifiant machine n'atteint l'écran […] un banc frontend échoue si un code en
capitales soulignées apparaît ». Le banc ne l'attrape pas : son contrôle
« aucun identifiant de code dans le bandeau » porte sur `#readouts`, celui des
réserves sur `#diag`. **Le tiroir `#drawer` n'est ouvert par aucun des trois
bancs.**

Et c'est le geste principal du poste : ADR-008 énonce « cliquer un capteur ouvre
sa fiche ». Un lecteur qui clique le premier capteur du jumeau 3D lit
`isa_5_1,process,data`.

| # | Constat | Gravité |
|---|---|---|
| FRONT-1 | Le tiroir capteur affiche `role` et `confidence` bruts ; `confidence` contient une liste de bases. Défaut visible au premier clic, hors de portée des trois bancs | **haute** |

Correctif : traduire `role` par la table déjà présente dans le fichier, et
remplacer `confidence` par les bases mises en forme — `BASE_LABEL` existe déjà
à la ligne 1642 et fait exactement cela pour un autre panneau.

## 76. FRONT-2 — API-2, la démonstration complète

`TREND_SETS` (`app.js:741-767`) déclare les **six** familles du menu
« Signaux » :

| Clé | Titre affiché | Colonnes |
|---|---|---|
| `thermal` | Températures du circuit acide | `T_ACID_IN`, `T_ACID_OUT`, `T_CIRC_1300` |
| `titre` | Analyseurs de titre acide | `C_ACID_1100`, `C_ACID_1200` |
| `debit` | Débit acide et allure de marche | `F_ACID`, `LOAD_SULFUR` |
| `duty` | **Puissance évacuée — observée contre attendue** | **`duty_kw`, `duty_expected`** |
| `absorption` | Contexte section absorption | `F_3412`, `A_3301`, `A_3302` |
| `degrade` | Instrumentation dégradée | `TI_5303`, `PHI_5306` |

**Aucune famille ne porte UA.** L'exploitant ne peut tracer ni `ua_kw_per_k`, ni
`ua_expected`, ni `fouling_resistance`, ni `ua_residual_trend_14d` — et il peut
tracer la paire que ADR-001 réfute, sous le titre « observée contre attendue ».

**Mais le front connaît déjà ces grandeurs.** `MESURE_LABEL` (`app.js:1394-1414`)
les nomme toutes, avec leur unité et leur précision :

```js
ua_kw_per_k:        { nom: "Coefficient d'échange",           unite: "kW/K",  decimales: 1 },
ua_expected:        { nom: "Coefficient d'échange attendu",   unite: "kW/K",  decimales: 1 },
ua_residual_z:      { nom: "Écart de coefficient d'échange",  unite: "σ",     decimales: 2 },
fouling_resistance: { nom: "Résistance d'encrassement",       unite: "K/kW",  decimales: 4 },
```

Et `renderGovernance` (`app.js:1362-1372`) affiche déjà la carte
« Coefficient d'échange — UA x,x kW/K · R² · σ · n h de référence », avec un
commentaire qui documente la correction de `thermal_twin` vers
`references.conductance`.

**API-2 se réduit donc à deux gestes** : ajouter les colonnes UA à
`/api/timeseries`, et ajouter une septième entrée à `TREND_SETS`. Le
vocabulaire, les unités, les libellés et la carte de lignage existent déjà.
C'est le meilleur rapport effet/effort de tout le dossier.

## 77. FRONT-3 — READ-4 tranché : **l'écran est juste, le README est faux**

`renderCoverage` (`app.js:1581-1601`) affiche **trois degrés**, avec son
commentaire :

> « TROIS DEGRES, PAS DEUX. […] Les compter comme couverts **surévaluait la
> couverture de 18 points** ; les compter comme aveugles effacerait la
> surveillance réelle qui existe. »

```js
<b>${fmt(risk.part_couverte_pct, 1)} %</b> détecté ·
<b class="is-partial">${fmt(risk.part_partielle_pct, 1)} %</b> conditions
surveillées sans mesure d'état
```

Le poste affiche donc **30,2 % détecté · 18,5 % conditions surveillées**, et le
README titre **« La part du risque réellement couverte : 48,8 % »**.

Le constat **READ-4** est confirmé de bout en bout : le référentiel, le code,
l'API et l'écran disent tous la même chose ; **seul le README porte encore le
chiffre d'avant la correction**, et le commentaire du code en chiffre l'écart à
18 points.

## 78. Ce que le poste fait **bien**, et qu'il ne faut pas casser

- **JE-1 confirmé.** `renderBench` (l. 1476-1484) affiche
  `blind_mutations.flagged_rate` **en premier**, marqué `data-key="true"`,
  libellé « fautes d'un genre non anticipé », le taux de non-régression venant
  en second et explicitement étiqueté. Le commentaire dit pourquoi : « Le
  lecteur repartait avec le taux flatteur, et l'aveu restait dans le code. »
  C'est le seul des quatre supports à publier le chiffre honnête en tête.
- **Le tableau des pièges est trié par note croissante** : la première ligne est
  le point faible du contrôleur. « Trier par ordre alphabétique plaçait douze
  100 % les uns sous les autres sans rien hiérarchiser. »
- **Les épisodes sont triés par marge, pas par score** — le score sature à 1,000
  et n'ordonnait rien.
- **`trendOf`** mesure la zone morte sur la **dispersion résiduelle** et non sur
  la moyenne : pour l'écart de consigne, dont la moyenne vaut zéro par
  construction, l'ancien seuil relatif tombait à zéro et les six cartes
  affichaient la même flèche montante.
- **`jeton()`** résout les couleurs depuis les variables CSS : les graphiques
  figeaient `#5b7276`, l'ancienne valeur de `--ink-4` rejetée pour échec WCAG,
  hors de portée du banc qui, lui, lit le jeton.
- **`showGate()`** arrête la scrutation à l'expiration de session, avec les
  trois conséquences chiffrées (75 requêtes 401 par minute, écran figé
  silencieux, diagnostic « Service injoignable » faux).
- **`$("speed")`** : la vitesse passe désormais en paramètre d'URL. Le
  commentaire (l. 1984-1994) est le meilleur du fichier — « `test_api.py`
  appelait `?speed=500`, c'est-à-dire le contrat réel : le test passait pendant
  que le poste échouait. Chaque côté était cohérent avec lui-même, et les deux
  ne se parlaient pas. »
- **`twinStateFrom`** ne colore que depuis `finding_map` : un code inconnu
  n'allume rien.

## 79. Trois points mineurs relevés dans le poste

**FRONT-4 — la branche « grandeur dérivée » est morte à l'écran.**
`renderKpi` (l. 1209) : `f.evidence_level === "derived" ? "grandeur dérivée" : "grandeur observée"`.
Aucune `Figure` n'étant jamais `derived` (**KPI-1**), le premier libellé n'est
jamais rendu. Quatrième surface concernée, après le rapport, le README et
`api/main.py` dont la docstring promet la distinction.

**FRONT-5 — une garde de réécriture qui ne peut pas fonctionner.**
`renderFeed` (l. 1053) : `if (box.dataset.sig === html.length.toString() && box.innerHTML === html) return;`
Le navigateur normalise `innerHTML` — attributs réordonnés, entités
réencodées — donc l'égalité stricte avec la chaîne produite échouera presque
toujours. La réécriture annoncée « seulement si le contenu a changé » a
vraisemblablement lieu à chaque cycle de 1,6 s. L'effet visible est masqué par
la restauration de `scrollTop` juste après. **À confirmer par mesure avant
correction** — je ne l'affirme pas.

**FRONT-6 — `dashboard.html:447-453` : un `split` à un seul enfant.**
Le conteneur `<div class="split">` de la vue Contrôle n'entoure qu'un unique
`<article>` (« Les huit contrôles »). Un `split` est une grille à deux colonnes :
le panneau occupe donc la moitié gauche et laisse un vide à droite. Reliquat
d'un panneau retiré.

## 80. Ce que la lecture du poste change pour le plan

**Le poste est la couche la mieux tenue du dépôt après les tests.** Sur
2 660 lignes lues, une trentaine de commentaires documentent chacun un défaut
mesuré et sa correction, et je n'y trouve **qu'un seul défaut visible à
l'écran** — FRONT-1 — plus deux points mineurs.

Cela renverse une hypothèse de départ. La tâche **C1** (« recette page par
page ») ne va pas révéler un poste en ruine : elle va confirmer un poste
soigné, avec un tiroir capteur à corriger et une famille de courbes à ajouter.

Et surtout, **les trois défauts que je trouve ici ont tous leur origine
ailleurs** :

| Défaut à l'écran | Origine réelle |
|---|---|
| FRONT-1, `confidence` affiché brut | **DOM-6** — le champ a changé de sens dans `knowledge.py` |
| FRONT-2, pas de courbe UA | **API-2** — `/api/timeseries` ne sert pas les colonnes |
| FRONT-4, « grandeur dérivée » jamais rendue | **KPI-1** — `kpi.py` ne produit jamais `derived` |

**Aucun n'est un défaut du poste.** Le front est fidèle à ce que l'API lui
donne ; ce sont les trois couches derrière qui ont bougé sans qu'il le sache.

---

# Lot 7 — `api/static/twin.js`, 2 137 lignes, **lu intégralement**

*Reste :* `api/static/app.css` (1 167 lignes).

## 81. TWIN-1 — **T-1 est mal diagnostiqué : le champ `anchor` n'a jamais servi à éviter les recouvrements**

Le constat **T-1** du lot 1 — repris comme cause de la tâche **C2** — énonce :

> « Les six paires de capteurs les plus proches (0,75 à 0,96 m) portent **deux
> ancres identiques** — le champ `anchor` **censé éviter les recouvrements** les
> garantit. »

**Lecture du code : `anchor` ne détermine qu'une rotation.**

```js
// twin.js:47-52
const ANCHOR_ROTATION = { up: 0, down: Math.PI, left: Math.PI / 2, right: -Math.PI / 2 };

// twin.js:1262-1265, setSensors()
const [ax, ay, az] = meta.at;
group.position.set(ax, ay, az);
group.rotation.z = ANCHOR_ROTATION[meta.anchor] ?? 0;
```

Le commentaire qui l'accompagne (l. 45-46) dit exactement à quoi il sert :

> « Orientation du capteur selon la face de l'appareil où il est monté : **le
> doigt de gant doit pointer VERS la tuyauterie, pas dans le vide.** »

**La position vient entièrement de `meta.at`.** Deux capteurs portant la même
ancre et des `at` éloignés ne se recouvrent pas ; deux capteurs portant des
ancres opposées et des `at` identiques se recouvrent quand même. Le champ est
sans rapport avec le problème.

**Conséquence pour C2 : le correctif porte sur les coordonnées `at` de
`topology.yaml`, pas sur les ancres.** Corriger les ancres n'aurait rien changé,
et aurait fait pointer des doigts de gant dans le vide.

| # | Constat | Gravité |
|---|---|---|
| TWIN-1 | T-1 attribue le recouvrement au champ `anchor`, qui ne gouverne que l'orientation du doigt de gant ; la cause est dans les coordonnées `at` | correction |

## 82. TWIN-2 — et le recouvrement est **déjà traité à l'écran**

`_resolveLabelCollisions` (l. 2076-2118) est appelée à **chaque image** depuis
`_loop`. Elle projette chaque étiquette en coordonnées écran, trie par distance
à la caméra, et pour chaque conflit :

```js
if (behind || horsCadre)        item.entry.label.material.opacity = 0;
else if (clash && !faulted)     item.entry.label.material.opacity = min(opacity, 0.12);
else                            kept.push(item);
```

Trois propriétés qui comptent :

1. **Un capteur en défaut n'est jamais effacé** (`&& !faulted`) — c'est la bonne
   priorité.
2. **Une étiquette qui déborde du cadre est effacée**, pas rognée : « une
   étiquette à moitié coupée par le bord est pire qu'absente ».
3. La plus proche de la caméra gagne, ce qui est le comportement attendu.

**Le désordre visuel signalé par l'utilisateur produit donc des étiquettes
estompées à 12 %, pas des piles de texte illisible.** C2 n'est pas une
correction de fonctionnement : c'est un réglage de lisibilité, et il se fait
dans `topology.yaml`.

**Deux gardes à respecter avant d'y toucher :**

- `twin_smoke.mjs` : `["chaque capteur est pose sur sa piece", egares.length === 0]`
  — tout capteur du périmètre doit rester à moins de **0,9 m** de la pièce
  déclarée dans `attaches_to` ;
- **BANC-3** : `["etiquettes qui se recouvrent sont estompees", someFaded]`
  exige qu'au moins une étiquette soit estompée. **Écarter les capteurs fera
  échouer ce contrôle** — il doit être reformulé d'abord.

## 83. Ce que `twin.js` fait remarquablement

- **TWIN-3 — un capteur mort n'affiche pas de mesure.** `_paintLabel`
  (l. 1391-1416) écrit « hors service » et « signal figé à 327,67 » au lieu de
  la valeur, avec la raison la mieux formulée du dépôt :

  > « Le jumeau affichait « 327,7 » et « 10,2 » dans la même typographie que les
  > mesures valides, c'est-à-dire **exactement ce que fait le DCS et exactement
  > ce que ce projet reproche au DCS**. Ces deux capteurs sont d'ailleurs le cas
  > d'école que le projet met en avant : les montrer comme des mesures ruinerait
  > la démonstration. »

- **TWIN-4 — le clonage de matériau par pièce.** `_register` (l. 545-581)
  documente que `mat.acidLine` était partagé entre le piquage d'entrée et celui
  de sortie : « peindre `NOZZLE_ACID_OUT` en rouge peignait donc du même coup
  `NOZZLE_ACID_IN` et toute la tuyauterie acide ». Le clone porte
  `userData.materiauSource`, ce qui permet à `setCutaway` de retrouver ses
  descendants — la correction qui a réparé le bouton « Coupe ».

- **TWIN-5 — la distance d'extraction se calcule.**
  `distance = SHELL_R + demiEpaisseur + 0.75` au lieu d'un 1,15 m en dur, parce
  que « le faisceau a lui-même 0,5 m de rayon et la calandre 0,56 : monté de
  1,15 m, son bord inférieur **effleure** le dessus de l'enveloppe ».

- **TWIN-6 — `setSensors` libère les ressources GPU** des capteurs précédents,
  géométries, matériaux **et textures d'étiquette** (un canvas 512×256 par
  capteur). Et le filtrage de `pickables` a été sorti de la boucle où il
  rebalayait le tableau onze fois pour rien.

- **TWIN-7 — l'accessibilité clavier est réelle** : `tabIndex = 0`,
  `role="application"`, `aria-description` énumérant les touches, flèches,
  `+`/`-`, `T` pour parcourir les capteurs, `Entrée` pour ouvrir, `Home` pour
  recadrer.

- **TWIN-8 — aucune ressource réseau.** La carte d'environnement est construite
  en mémoire par `PMREMGenerator` à partir d'une scène de boîtes émissives, et
  les six textures (peinture, acier brossé, béton, rouille, caillebotis,
  bardage) sont peintes dans des canvas. C'est ce qui tient la promesse
  d'ADR-006.

## 84. TWIN-9 — un point à connaître pour la recette C1

`_guardPerformance` (l. 1933-1957) dégrade en deux paliers. Au second — sous
14 images par seconde :

```js
if (this.bundleMesh) this.bundleMesh.visible = this.cutaway;
```

**Le faisceau tubulaire disparaît de la scène**, sauf en mode coupe. Or c'est la
pièce la plus souvent mise en cause, et `_marquerPieces` dessine son cartouche
**sans test de profondeur** : sur un poste faible, l'écran affichera
« ▲ CRITIQUE — FAISCEAU TUBULAIRE » au-dessus d'un appareil dont le faisceau
n'est pas rendu.

Ce n'est pas incohérent — le faisceau est de toute façon enfermé dans la
calandre — mais c'est un état à connaître avant de faire la recette sur un poste
à carte graphique intégrée, qui est la configuration de salle de contrôle que
le commentaire lui-même cite.

## 85. Ce que la lecture du jumeau change

Le fichier est **le plus soigné du dépôt avec `test_service_invariants.py`**.
Sur 2 137 lignes je ne trouve **aucun défaut**, et une douzaine de commentaires
documentent chacun un défaut mesuré et corrigé.

Mais il apporte une **correction de fond au plan** : la tâche C2, telle que la
reprise la formule, repose sur un diagnostic faux. Le champ `anchor` n'est pas
en cause, le recouvrement est déjà atténué à l'écran, et le travail réel est un
réglage de coordonnées dans `topology.yaml` sous deux gardes existants.

**C2 passe donc de « corriger un défaut visible » à « affiner un placement »**,
et descend en priorité derrière FRONT-1 et API-2, qui sont, eux, des défauts
réels visibles à l'écran.

---

# Lot 8 — `api/static/app.css`, 1 168 lignes, **lu intégralement**

**La lecture du dépôt est terminée.** Code, front, référentiel, documentation,
tests, scripts, conteneur, chaîne d'intégration et état git.

## 86. Aucun défaut trouvé dans la feuille de style

Une feuille unique, comme ADR-008 l'annonce. Chaque section porte un commentaire
qui documente un défaut mesuré et sa correction :

| Correction documentée | Ce qu'elle évitait |
|---|---|
| Contraste mesuré sur **le pire des cinq fonds** | `--ink-4` valait 4,57:1 sur `--plate` et **4,20:1 sur `--raise`**, le fond de survol — le texte le plus petit repassait sous AA au moment précis où le pointeur l'atteignait |
| `overflow-x: hidden` retiré de `<body>` | le bandeau de couverture du risque était rogné, sans barre de défilement pour y accéder |
| `outline: none` retiré des champs d'identification | seul repérage de focus du premier écran, information portée par la couleur seule |
| `100dvh` | la coque dépassait de la hauteur de la barre d'adresse au premier affichage mobile |
| `.stage-tr` n'est plus masqué sous 760 px | la lecture de sévérité disparaissait sur la tablette de ronde |
| Quatre variables CSS inexistantes | `--surface-2`, `--line`, `--pane-2`, `--ink-1` : un `var()` sans repli rend la propriété invalide — le libellé de cible s'affichait sans fond, le journal d'escalade perdait son code couleur |
| Deux jetons retirés | `--plate-hi` valait `#12212800`, entièrement transparent, sans consommateur ; `--frame` n'était consommé par aucun sélecteur — « la teinte du châssis vit dans `twin.js`, une feuille de style ne peut pas la lui fournir » |
| Palier 460 px et `pointer: coarse` à 44 px | aucun palier n'existait sous 760 px, et les commandes mesuraient 28 à 35 px pour un doigt ganté |

Et la gravité n'est jamais portée par la couleur seule : `.sev-mark::before`
donne un glyphe par sévérité (`=`, `i`, `!`, `✕`) et les bordures portent un
motif distinct — trait plein pour l'avertissement, **double** pour le critique.

## 87. Trois règles mortes, toutes issues de constats déjà ouverts

| Règle | Pourquoi elle ne s'applique jamais |
|---|---|
| `.kpi[data-evidence="derived"] { border-top-color: var(--warn) }` | aucune `Figure` n'est jamais `derived` — **KPI-1**, cinquième surface |
| `.readout[data-live="on"]` | `app.js` ne pose que `data-tone` sur les cartes du bandeau, jamais `data-live` |
| `.split` à un seul enfant | `grid-template-columns: 1.55fr 1fr` laisse la colonne de droite vide — **FRONT-6** |

Aucune n'est un défaut de la feuille : deux découlent de constats situés en
amont, la troisième est un reliquat d'un sélecteur abandonné.

## 88. Bilan de la lecture intégrale

| Ensemble | Lignes | Défauts trouvés |
|---|---|---|
| `src/` + `api/` Python | 14 280 | lus par la session précédente ; vérifiés par sondages ciblés |
| Front — `dashboard.html`, `app.js`, `twin.js`, `app.css` | 5 966 | **1 défaut visible** (FRONT-1) + 3 mineurs |
| `tests/` | 5 199 | 8 constats, dont 2 de gravité haute |
| Documentation — 5 documents + 11 ADR | ~2 900 | **la majorité des constats du dossier** |
| Scripts, conteneur, CI, Makefile | ~2 500 | CI-5, 4 orphelins, 3 dépendances mortes |
| Référentiel — 3 YAML | 1 160 | 6 constats |

**Le rapport est constant sur tout le dépôt : plus on descend vers le code, moins
il y a de défauts ; plus on monte vers la documentation, plus il y en a.**
C'est la mesure du diagnostic de stratification établi au lot 4.

---

# Phase 0.3 — transcription de l'AMDEC **vérifiée contre le fichier source**

`docs/4-AMDEC - REFROIDISSEUR DE SECHAGE PSIII.xlsx`, feuille
`AMDEC FOUR A SOUFRE`, 25 lignes. Onglets `GRV` / `OCC` / `DET` présents, comme
l'annonce l'en-tête de `amdec.yaml`.

## Verdict : **la transcription est fidèle**, avec quatre écarts mineurs

### Les dix cotations sont exactes, au chiffre près

| Mode | Source (F/G/N/C) | `amdec.yaml` | |
|---|---|---|---|
| FAISCEAU (Fuite / Bouchage) | 3/7/5/105 | 3/7/5/105 | ✔ |
| PORTE DE VISITE — Fuite | 3/6/5/90 | 3/6/5/90 | ✔ |
| CALENDRE — Fuite | 3/6/5/90 | 3/6/5/90 | ✔ |
| PLAQUE SACRIFICIELLE | 2/8/7/112 | 2/8/7/112 | ✔ |
| VANNE D'ACIDE — Bouchage | 3/6/5/90 | 3/6/5/90 | ✔ |
| VANNE D'ACIDE — Fuite | 2/8/7/112 | 2/8/7/112 | ✔ |
| VANNE D'ACIDE — Dysfonction. | 2/3/7/42 | 2/3/7/42 | ✔ |
| VANNE D'E/M — Bouchage | 2/3/7/42 | 2/3/7/42 | ✔ |
| VANNE D'E/M — Fuite | 2/3/7/42 | 2/3/7/42 | ✔ |
| VANNE D'E/M — Dysfonction. | 3/1/3/9 | 3/1/3/9 | ✔ |

En-tête source : `S-PC-E7301`, `PSIII`, `23/09/2019`, `Réalisé par : OUBID` —
tous conformes.

### Trois transformations déclarées sont **exactes**

- La source écrit **`CALENDRE`** ; `amdec.yaml` déclare
  `"Correction orthographique CALENDRE vers CALANDRE"`. ✔
- La source écrit **`FAISEAU TUBULAIRE`** (sic) ; `original_values.element`
  **conserve la faute de frappe source**. ✔ C'est exactement le comportement
  attendu d'une transcription.
- La source porte un libellé **combiné** `Fuite / Bouchage` sur une seule ligne ;
  `amdec.yaml` le sépare en trois modes et le déclare dans `transformations`. ✔

### Les quatre écarts à corriger

| # | Écart | Détail |
|---|---|---|
| **AMDEC-1** | `VANNE_ACIDE_BOUCHAGE` : `causes: ["Depot"]` | La colonne *Cause* est **vide** dans la source (L20). Ajout non déclaré — `transformations` dit seulement « Normalisation du code; cotations inchangées » |
| **AMDEC-2** | `PLAQUE_SACRIFICIELLE` : `effet: "Perte de protection cathodique…"` | La colonne *Effet* est **vide** dans la source (L19). Même ajout non déclaré |
| **AMDEC-3** | `PORTE_VISITE_FUITE` : une seule action corrective | La source en porte **trois** (L13-15) : « Changement joint chaque révision », « Inspection visuelle », « Mesure des epaisseurs ». Les deux dernières sont perdues — alors que `CALANDRE_FUITE`, qui a la même structure, **les conserve toutes les trois** |
| **AMDEC-4** | `source_location` : décalage systématique de **+1** | « lignes 9-11 » pour L10-12, « ligne 18 » pour L19, etc. Cohérent sur les dix modes, donc une convention de numérotation différente — mais un lecteur qui ouvre le fichier ne retrouve pas la ligne citée |

**AMDEC-1 et AMDEC-2 comptent plus que leur taille** : `VANNE_EM_DYSFONCTION`
porte `effet: ""` là où la source est vide. **Le projet sait donc laisser vide
quand c'est vide** — ce qui rend les deux ajouts silencieux d'autant plus
notables. Ils ne sont pas faux au fond ; ils ne sont simplement pas déclarés
comme des ajouts, dans un fichier dont c'est toute la discipline.

## Ce que cela établit

**Le meilleur argument du mémoire tient.** Un référentiel métier confronté
ligne à ligne à son document d'origine, dix cotations exactes, les fautes de
frappe source conservées, les transformations déclarées et vérifiables. C'est
défendable devant un service Méthodes.

Les quatre écarts se corrigent en une demi-heure : compléter deux
`transformations`, restaurer une action corrective, réaligner dix
`source_location`. Aucun ne remet en cause l'architecture de provenance.

**Et ce contrôle doit devenir un test**, sur le patron du § 3 du plan : les
cotations `ocp_source` sont aujourd'hui comparées au YAML par lui-même
(`test_cotations_officielles_conservent_les_valeurs_originales`). Elles doivent
l'être **au classeur**.

---

# Phase 0.4 — FMT-1 et FMT-2 corrigés

## FMT-2 — `tests/helpers.py`

`sans_accents` existait **deux fois, ligne pour ligne** — même `NFKD`, même
filtrage des `combining`, même `casefold`, et le même argument dans les deux
docstrings. `tests/helpers.py` réexporte désormais `src.formatting.sans_accents`.
Les fichiers de tests continuent d'écrire `from tests.helpers import sans_accents`
sans rien changer. **27 lignes → 18, dont zéro logique.**

## FMT-1 — `src/notifications/redaction.py`

La conversion `,` → espace fine puis `.` → `,` est retirée ; `_nombre` délègue à
`src.formatting.nombre`. L'enveloppe subsiste parce que deux comportements
propres à ce rapport devaient être préservés, et ils sont désormais documentés :
le **défaut à zéro décimale** (seize appels s'y fient — « 3 436,0 décisions
jugées » ne se lit pas) et le **refus du booléen** (`float(True)` vaut 1,0).

### Contrôle par comparaison des deux implémentations

Seize cas, dont les valeurs réelles du rapport de gouvernance. **Un seul
écart :**

| Entrée | Ancien | Nouveau |
|---|---|---|
| `float("nan")`, 1 décimale | **`'nan'`** | `'—'` |

**C'est une correction, pas une régression — et elle révèle un défaut de plus.**

L'ancien `_nombre` gardait `try / except (TypeError, ValueError)`, qui **ne
capture pas NaN** : `float('nan')` réussit et `f"{nan:,.1f}"` rend la chaîne
`'nan'`. `src.formatting.nombre` porte, lui, la garde explicite `if x != x`.

Autrement dit : **le module écrit pour empêcher un artefact machine d'atteindre
un technicien — « 0.9642612800415576 » — pouvait lui envoyer `nan`**, parce que
la copie avait perdu une garde que l'original possédait. C'est la démonstration
la plus courte du motif 1 de tout le dossier : dupliquer une fonction, ce n'est
pas la copier, c'est en copier une version.

| Rendus vérifiés | |
|---|---|
| `_nombre(3436)` | `3 436` |
| `_nombre(9.98, 2)` | `9,98` |
| `_nombre(0.96426128, 4)` | `0,9643` |
| `_nombre(1234567)` | `1 234 567` |
| `_nombre(None)` · `_nombre(True)` | `—` |

### Confirmé sur le poste

`test_redaction_gouvernance.py`, `test_typographie.py`, `test_sensitivity.py` et
`test_fouling_injection.py` — **tous verts**, aucun échec. Les quatre fichiers
couvrent les deux surfaces touchées : le rapport de gouvernance rédigé par
`_nombre`, et les trois modules qui importent `sans_accents` depuis
`tests/helpers`.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_redaction_gouvernance.py `
  tests\test_typographie.py tests\test_sensitivity.py tests\test_fouling_injection.py -q
```

---

# Phase 0.5 — CI-5 : correctif appliqué, et **il révèle une porte mal écrite**

## Ce qui est corrigé

`lineage.py` distingue désormais deux natures de portes :

```python
SOFTWARE_GATES      = {causalite_temporelle, redondance_features, stabilite_hors_periode}
EXTERNAL_DATA_GATES = {labels_gmao, validation_externe}
```

`failed_software_gates()` s'ajoute à `failed_mandatory_gates()`, qui est
**inchangée**. `validate_release.py` fait porter son code de retour sur les
trois portes logicielles et **publie les deux listes**. `promote_model.py`,
`validate_model_manifest` et le champ `failed_mandatory_gates` du manifeste
sont intacts : **la promotion continue d'exiger les cinq**, et elle reste
légitimement impossible.

### Contrôle par mutation

| Cas | Portes logicielles en échec | Promotion |
|---|---|---|
| Rapport réel | `redondance_features`, `stabilite_hors_periode` | 4/5 |
| `causalite_temporelle` cassée | les trois | 5/5 |
| Les 3 logicielles franchies | **aucune** | 2/5 |
| Rapport amputé (`deployment_gates: []`) | les trois | 5/5 |

Le garde mord bien, y compris sur un rapport vide — une porte absente compte
comme en échec.

## Mais la chaîne reste rouge, et pour une raison qu'il faut regarder

**Deux des trois portes logicielles échouent réellement.** Mon correctif était
nécessaire — il retire deux portes qu'aucun commit ne peut franchir — mais il ne
rend pas la CI verte.

### CI-6 — `redondance_features` se contredit dans sa propre preuve

```
0 paire(s) redondante(s) entre grandeurs du modèle,
2 avec une variable régulée HORS MODÈLE
(la plus forte : regulation_effort_z contre control_deviation, r = -0,938)
```

La porte s'appelle « redondance des **features** ». Son critère propre est
**satisfait** : zéro paire redondante entre grandeurs du modèle. Elle échoue sur
une corrélation avec `control_deviation`, **qui n'est pas dans
`MODEL_FEATURES`**.

Or cette corrélation est **exactement ce qu'ADR-001 établit**, ce que
`independence_report` publie, et ce que
`test_effort_de_regulation_est_redondant_et_le_declare` **verrouille** :

```python
assert abs(effort["corr_control_deviation"]) > 0.80
assert effort["independent"] is False
```

**La porte échoue donc sur une propriété que le projet documente, publie et
protège par un test.** Ce n'est pas un défaut qu'un commit a introduit : c'est
l'algèbre du système, et le projet a choisi de la dire plutôt que de la nier.
Une porte de déploiement qui sanctionne une limite assumée et déclarée ne
mesure pas une régression — elle demande au projet de se dédire.

**Décision à porter au plan** : le critère doit se restreindre aux paires
**internes à `MODEL_FEATURES`** — ce que son propre libellé annonce — et la
redondance avec une variable régulée hors modèle doit être **publiée en
observation**, pas en échec. `test_features_modele_non_redondantes` porte déjà
exactement ce critère restreint, et il passe.

### `stabilite_hors_periode` — à instruire

`alertes moyennes 7,8 % · PSI max 3,745 · dispersion du seuil 0,001`. Le PSI
mesure un déplacement de distribution entre période de référence et période de
test. 3,745 est élevé — mais le § 9.2 du rapport établit que **le régime change
réellement** entre les deux périodes (deux excursions de sur-refroidissement).
La porte mesure peut-être correctement un fait que le projet a déjà expliqué.

**À instruire avant de trancher.** Contrairement à `redondance_features`, je
n'ai pas d'élément pour conclure que le critère est mal écrit.

| # | Constat | Gravité |
|---|---|---|
| CI-6 | `redondance_features` échoue sur une corrélation avec une variable hors modèle, alors que son critère interne est satisfait et que la propriété est documentée par ADR-001 et verrouillée par un test | **haute** |

## Phase 0.5 (suite) — CI-5 confirmé sur le poste, et deux effets à connaître

`test_model_governance.py` reste vert — `validate_model_manifest` est bien
inchangée. `validate_release.py` publie désormais les deux listes :

```
Portes en attente de données OCP (non bloquantes) : labels_gmao, validation_externe
  Elles exigent un historique de pannes étiqueté et une validation hors site.
  Aucun commit ne peut les franchir.
ÉCHEC — portes logicielles en échec : redondance_features, stabilite_hors_periode
```

La séparation est faite et lisible. **CI-6 reste le point bloquant**, et il est
maintenant isolé : deux portes, pas quatre.

### EXEC-1 — `validate_release.py` réécrit huit artefacts

`git status` après l'exécution :

```
M models/e7301_detector.manifest.json      M reports/model_validation.json
M reports/project_metrics.json             M reports/junit.xml
M reports/judge_eval_{summary.json,report.txt,clean.csv,traps.csv}
```

Le script **entraîne, sérialise et réécrit** — ce n'est pas une lecture. C'est
la confirmation opérationnelle de l'amendement 2 : **E1 doit être la dernière
action avant E2.** Toute exécution de `validate_release.py` invalide
`project_metrics.json`, donc `test_project_metrics.py`.

### DOC-3 — quatre valeurs pour les heures d'apprentissage

Le journal d'exécution donne, pour la fenêtre retenue à 40 % :

```
Reference de conductance      n = 3 505 h   UA 17,77 kW/K   R² 0,924   σ 0,63
Reference d'effort            n = 3 505 h   R² 0,968 (0,962 sans apprentissage)
Reference de temperature      n = 3 532 h   R² 0,479
```

| Source | Heures d'apprentissage |
|---|---|
| `rapport_technique.md` § 5.3 | **3 483** |
| ADR-009, section « Problème » | **3 483** |
| ADR-009, tableau des conséquences | **3 487** |
| **Mesure du jour** | **3 505** |

**ADR-009 porte deux valeurs différentes dans le même document**, et aucune des
trois ne correspond à la mesure. Les effectifs distincts entre références sont
légitimes — `test_les_trois_references_partagent_la_meme_periode` l'admet
explicitement, seule la **fenêtre** doit être identique, et elle l'est
(2024-01-01 07:00 → 2024-07-13 17:00 pour les trois). Ce qui ne l'est pas, c'est
qu'un chiffre publié quatre fois prenne quatre valeurs.

À verser à la liste de la phase D. **C'est exactement la classe de défauts que
le contrôle 3 attrapera** : une valeur écrite à la main dans un document, jamais
comparée à l'artefact qui la produit.

Note au passage : le journal confirme **« 11 features modèle »** à chaque
construction — ADR-003 et l'annexe B du rapport, qui annoncent dix, sont bien
les documents fautifs.


## Phase 0.6 — CI-6 traité, **et je corrige ma propre proposition**

### Ce que je proposais était faux

J'avais écrit : « le critère doit se restreindre aux paires internes à
`MODEL_FEATURES` ». La lecture de `model_validation.py:415-422` montre que le
comportement actuel est **délibéré** :

> « `redondance_features` ne comptait que les redondances INTERNES à la matrice
> du modèle, en ignorant `shadow_redundancy` — c'est-à-dire exactement la
> variable que l'audit de redondance avait été écrit pour exposer. Elle publiait
> « 0 paire redondante » deux cents lignes en dessous d'un −0,94 mesuré. Les deux
> sont désormais calculées. **La seconde échoue, et c'est le résultat correct.** »

**Ma correction aurait remasqué ce que l'auteur a rendu visible** — précisément
le « nettoyage par inadvertance » contre lequel le § 11 du plan met en garde.
L'argument d'honnêteté est juste et il devait être préservé.

### Le vrai défaut : une porte mesurait deux natures

`redondance_features` exigeait **à la fois** :

| Propriété | Nature |
|---|---|
| aucune paire redondante **interne** au modèle, conditionnement défini | **logicielle** — un commit peut la casser en ajoutant une variable |
| aucune redondance avec une variable régulée **hors modèle** | **algébrique et permanente** — le résidu d'effort *est* l'écart de consigne (ADR-001), et `test_effort_de_regulation_est_redondant_et_le_declare` le verrouille à `corr > 0,80` |

Une porte de déploiement ne peut pas exiger d'un commit qu'il démente l'algèbre
du système.

### Correctif : scission, pas restriction

- **`redondance_features`** — paires internes et conditionnement. Reste dans
  `SOFTWARE_GATES`. **Passe** aujourd'hui (0 paire, conditionnement 3,09).
- **`redondance_hors_modele`** — nouvelle porte, **en échec**, avec sa preuve
  chiffrée et son rattachement à ADR-001. Elle n'est **ni dans
  `MANDATORY_GATES`, ni dans `SOFTWARE_GATES`** : `_failed_among` itère sur des
  ensembles explicites, donc elle est publiée dans `deployment_gates`, affichée
  par `renderValidation`, et ignorée par les deux gardes.

La redondance reste donc **visible, chiffrée et en échec** — mais elle ne bloque
plus ni la fusion ni la promotion.

### Contrôle

| | Avant | Après |
|---|---|---|
| Portes publiées à l'écran | 5 | **6** |
| Bloquantes (logicielles) | `redondance_features`, `stabilite_hors_periode` | **`stabilite_hors_periode`** |
| Promotion en échec | 4/5 | 3/5 — **toujours impossible** ✔ |

**Le point bloquant se réduit à une seule porte.** `test_model_governance.py`
n'est pas affecté : il construit son propre bloc de cinq portes et
`MANDATORY_GATES` est inchangé.

### Reste à instruire : `stabilite_hors_periode`

`alertes moyennes 7,8 % · PSI max 3,745 · dispersion du seuil 0,001`. Le § 9.2
du rapport établit que **le régime change réellement** entre période de
référence et période de test — deux excursions de sur-refroidissement. La porte
mesure peut-être correctement un fait déjà expliqué et documenté, auquel cas
elle relève de la même reclassification. **Je ne tranche pas** : contrairement à
la précédente, je n'ai pas lu de quoi conclure.


## Phase 0.7 — `stabilite_hors_periode` scindée : **CI-5 est entièrement résolu**

### La mesure tranche

```python
stable = mean_rate <= max(0.15, contamination * 5) and max_psi <= 0.25
```

| Terme | Mesure | Seuil | |
|---|---|---|---|
| taux d'alertes hors période | **7,8 %** | 15 % | **franchi** |
| PSI max sur les scores | **3,745** | 0,25 | échoue, facteur 15 |

**La porte n'échouait que sur le second terme et entraînait le premier avec
elle** — exactement la structure de `redondance_features`.

### Deux natures, deux portes

- **`stabilite_hors_periode`** conserve le taux d'alertes. C'est ce qu'un commit
  déplace — contamination, seuil, variables — et c'est le vrai garde de
  non-régression. Il reste **bloquant**, et il **passe**.
- **`derive_de_distribution`** porte le PSI. Publiée, en échec, non bloquante.

### Et le seuil de 0,25 n'est pas justifié pour cet usage

C'est la borne usuelle du *Population Stability Index* en **scoring de crédit**,
où les populations comparées sont supposées échangeables. Elle est appliquée ici
à des scores d'Isolation Forest sur un procédé dont le § 9.2 du rapport établit
qu'il **change de régime** entre les deux moitiés de la période — un cas où un
PSI élevé est attendu. **Le transfert n'est argumenté nulle part dans le
dossier.** La preuve de la porte le dit désormais.

### Une différence à ne pas gommer

`redondance_hors_modele` est **algébriquement** infranchissable : le résidu
d'effort *est* l'écart de consigne. `derive_de_distribution` ne l'est pas — un
modèle autrement conçu déplacerait ce chiffre. Elle sort du blocage **faute de
seuil justifié, pas faute de sens**. Le commentaire du code porte cette nuance.

### État final de CI-5

| | Avant | Après |
|---|---|---|
| Portes publiées | 5 | **7** |
| Bloquantes pour une fusion | 4 | **aucune** |
| Promotion en échec | 4/5 | **2/5 — toujours impossible** ✔ |
| Code de retour de `validate_release.py` | **2** | **0** |

**La chaîne d'intégration peut redevenir verte, et le job `image` être construit
pour la première fois.** Rien n'a été assoupli : les sept portes sont publiées,
quatre sont en échec, elles s'affichent à l'écran avec leur preuve, et la
promotion reste refusée. Ce qui change, c'est **ce qui bloque une fusion** —
et il ne reste que ce qu'un commit peut réellement casser.

`stable` a disparu au profit de `alert_rate_limit`, nommé une seule fois pour
que la borne n'existe pas en deux exemplaires.


## Phase 0.8 — CI-5 validé sur le poste, et **je corrige mon diagnostic du test rouge**

### CI-5 : confirmé

```
Portes en attente de données OCP (non bloquantes) : labels_gmao, validation_externe
Portes logicielles franchies.
L'artefact reste CANDIDAT : labels_gmao, validation_externe ne sont pas franchies.
La promotion est légitimement impossible sur ce corpus, et c'est le résultat attendu.
```

Code de retour **0**. Sept portes publiées, deux en échec pour la seule raison
qui vaut, promotion refusée. **La chaîne peut redevenir verte.**

### ENV-1 — le test rouge n'est PAS API-5

J'avais écrit : « porte sur les deux routes de notification touchées par les
modifications non commitées ; très probablement **API-5** ». **C'est faux**, et
la trace le montre en une ligne :

```
tests\test_api.py:147: in test_acces_local_et_notifications_desactivees
    assert status.json()["enabled"] is False
```

**Ligne 147**, pas 148 ni 149. L'échec ne porte pas sur les codes 409 des routes
`/api/notifications/test` et `/api/notifications/governance` — il porte sur
`enabled`.

Cause vérifiée : le `.env` du poste porte **`SMTP_HOST` et `ALERT_EMAIL_TO`
renseignés**. `EmailNotifier.enabled` exige un relais **et** un destinataire :
il vaut donc `True`, et le canal est réellement actif.

**Le test décrit la machine, pas le système.** Il passe en intégration continue,
qui part d'un dépôt vierge sans `.env`, et échoue sur un poste **correctement
configuré** — celui que le runbook décrit.

### C'est le piège que `dump_fixtures.py` documentait déjà

> « `AUTH_ENABLED` vaut par defaut `_registry_is_populated(...)` […] Sur toute
> machine correctement configuree — c'est-a-dire la configuration que le projet
> recommande — ce script recevait donc `401 Unauthorized` […] **Le defaut ne se
> voyait que la ou un registre existe : ni en integration continue, qui part
> d'un depot vierge, ni dans l'environnement d'audit.** »

**La même cause, sur une autre variable.** Et la même parade : `dump_fixtures.py`
force `os.environ["AUTH_ENABLED"] = "false"` avant l'import de `src.config`.
`conftest.py` faisait déjà ce geste pour l'authentification — il le fait
désormais pour le canal e-mail.

`setdefault` n'aurait pas suffi : ces deux variables ne sont pas *absentes*,
elles viennent du fichier `.env`. Il faut les neutraliser explicitement.

Les tests qui ont besoin d'un canal actif — `test_access_notifications.py`,
`test_le_canal_d_escalade_est_redige_en_francais` — construisent leur propre
`EmailNotifier` avec un hôte explicite et ne dépendent pas de cette valeur.

| # | Constat | Gravité |
|---|---|---|
| ENV-1 | `test_acces_local_et_notifications_desactivees` dépendait du `.env` du poste : vert sur un dépôt vierge, rouge sur une machine configurée. Deuxième occurrence du piège documenté par `dump_fixtures.py` | moyenne |

**API-5 reste ouvert** — `enqueue_test()` est toujours appelé sans `demandeur`
alors que la méthode porte le paramètre, et le corps du courriel de test est
toujours sans accents (**NOTIF-1**). Simplement, ce n'est pas ce que ce test
mesurait.

## Phase 0.9 — API-5 et NOTIF-1 corrigés, et **la mutation révèle J-2 élargi**

### API-5 — les deux appels transmettent désormais le demandeur

`enqueue_test` et `enqueue_governance` portent la même signature et servent les
deux boutons voisins de la page Contrôle. Seul le second recevait `demandeur` :
le technicien qui **testait son propre canal** recevait le courriel à la
première adresse abonnée, pas à la sienne — et en concluait que le canal ne
marchait pas. Vérifié sur les deux appels lus en entier : `demandeur=` transmis
des deux côtés.

*(Ma première vérification annonçait le contraire pour `enqueue_governance` :
l'expression régulière non gourmande s'arrêtait au `)` de
`rediger_gouvernance(payload)`. Artefact de mesure, pas constat.)*

### NOTIF-1 — le corps du courriel de test est accentué

« operationnel » et « associee » deviennent « opérationnel » et « associée », et
le message dit désormais ce qu'il vaut : une vérification du relais et du
destinataire, pas une alerte procédé.

### CONTRÔLE PAR MUTATION — et il trouve mieux que la correction

Méthode du § 5 : réintroduire le défaut, vérifier que le contrôle échoue.

```
corps corrigé                          -> fautes détectées : AUCUNE   ✔
corps muté (opérationnel -> operationnel) -> fautes détectées : AUCUNE   ✗
```

**Le détecteur ne mord pas.** `operationnel` n'est pas dans le lexique de
`MOTS_A_ACCENTUER`, ni `procede`, ni `associee`. Ma correction est juste sur le
fond, mais **le contrôle censé la protéger est aveugle aux mots qu'elle
contient**.

C'est **J-2 élargi**. Le constat du lot 1 relevait sept mots manquants sur les
libellés du Judge — `citees`, `reelles`, `invoques`, `fondes`, `calibree`,
`traite`, `enoncees`. Il faut y ajouter au moins `operationnel`, `procede`,
`associee`.

**Et le défaut est double** : cette chaîne n'est retournée par aucune API, donc
`_textes_du_rapport` ne la parcourt jamais. Même un lexique complet ne la
verrait pas. C'est la quatrième surface hors de portée du test, avec le
diagnostic nominal (**A-1**), les libellés du contrôleur (**J-2**) et les trois
scripts en ligne de commande (**SCR-1**).

**Deux corrections à porter en phase D**, et elles se tiennent :
1. **élargir le lexique** — il est lexical par construction, donc « exact sur ce
   qu'il couvre » comme le dit son commentaire ; sa faiblesse est sa taille ;
2. **élargir le périmètre** — le test doit parcourir les chaînes littérales des
   modules qui produisent du texte lisible, pas seulement les sorties d'API.

Sans quoi la règle 3 d'ADR-011 — « le test de typographie couvre toute surface
lisible » — restera plus large que ce qu'elle couvre.

## Phase 0.10 — suite complète : trois échecs, **deux étaient de mon fait**

```
FAILED test_documentation.py::test_aucun_endpoint_documente_n_a_disparu_de_l_api
FAILED test_project_metrics.py::test_project_metrics_restent_coherentes_avec_les_artefacts
FAILED test_typographie.py::test_aucun_point_decimal_dans_les_textes_affiches
```

### 1. Le test de typographie attrapait **ma nouvelle porte**

```
backtest.deployment_gates[4].evidence : 9.2
```

`deployment_gates[4]` est `derive_de_distribution`, que je venais d'écrire. Sa
preuve citait « § 9.2 » — un **numéro de section**, que le détecteur lit comme
un point décimal anglais. Il ne peut pas distinguer les deux, et c'est le
comportement correct.

Corrigé en supprimant la référence numérotée : « deux excursions de
sur-refroidissement établies par l'analyse ». Le rapport sera de toute façon
réaligné en phase D, citer un numéro de section y était fragile.

**Le test a fait exactement son travail, sur du texte écrit une heure plus tôt.**

### 2. Le test de documentation attrapait **mon propre journal d'audit**

```
endpoints documentes et inexistants : ['docs\\audits\\analyse-architecture.md : /api/...',
  '/api/auth/', '/api/business/assumptions']
```

`DOCUMENTS` balayait `docs/**/*.md`, donc `analyse-architecture.md`, qui cite
`/api/business/assumptions` **pour dire qu'il a été supprimé** — c'est le
constat DOC-2 lui-même — et `/api/...` comme forme générique.

**Ce n'est pas un défaut du test : c'est une erreur de périmètre.** Il vérifie
que la documentation décrit **le système qui existe**. Un journal d'audit décrit
son **histoire**, y compris ce qui n'existe plus. Deux contrats différents.

`docs/audits/` est écarté, avec la raison écrite dans le fichier et la
contrepartie assumée : de la documentation d'usage écrite là échapperait aux
quatre contrôles — elle n'y a pas sa place. C'est le même raisonnement
qu'`ABSENCES_ASSUMEES`, appliqué à un dossier plutôt qu'à une liste de noms.

**Quatre documents restent balayés** : `architecture.md`,
`data_dictionary_E7301.md`, `rapport_technique.md`,
`traceability_matrix_E7301.md`, les onze ADR, le runbook et le README.

### 3. `test_project_metrics` — attendu

Boucle d'amorçage, et `validate_release.py` a été exécuté deux fois entre-temps.
**Ne pas la jouer maintenant** : E1 est la dernière action avant E2, par
l'amendement 2.

### Ce que ces deux régressions enseignent

Elles sont arrivées en **une heure**, sur du code que je venais d'écrire, dans un
dépôt dont je documente depuis huit lots qu'il dérive par défaut de propagation.
Les deux ont été attrapées par des tests que le projet possédait déjà.

C'est l'argument le plus concret pour le § 3 du plan : **le patron fonctionne, y
compris contre celui qui l'invoque.**

---

# Phase 0 — **close**

Un seul échec subsiste sur la suite complète :
`test_project_metrics_restent_coherentes_avec_les_artefacts`, sur son assertion
`failures == errors == 0`. **C'est la boucle d'amorçage, et elle doit rester
rouge jusqu'à E1** — dernière action avant E2, par l'amendement 2.

## Ce qui a été fait

| Item | Résultat |
|---|---|
| **Transcription AMDEC** | **fidèle** — 10 cotations exactes, faute de frappe source conservée, 3 transformations justes. 4 écarts mineurs versés en phase D |
| **AL-1** | vérifié au source. Plus grave que décrit : le registre nomme l'alarme d'après le capteur, et une alarme peut ne jamais se résoudre. Correctif identifié — réutiliser `_priorite` |
| **FMT-1 / FMT-2** | corrigés. La duplication avait **perdu la garde NaN** de l'original : le rapport pouvait envoyer `nan` à un technicien |
| **CI-5** | `SOFTWARE_GATES` séparé des portes de données externes |
| **CI-6** | `redondance_features` scindée — la redondance algébrique reste **publiée et en échec**, sans bloquer |
| **`stabilite_hors_periode`** | scindée — le taux d'alertes reste bloquant et passe ; le PSI est publié, avec la remarque que son seuil de 0,25 vient du scoring de crédit |
| **ENV-1** | le test rouge n'était pas API-5 : il dépendait du `.env` du poste. Deuxième occurrence du piège documenté par `dump_fixtures.py` |
| **API-5 / NOTIF-1** | corrigés — `demandeur` transmis des deux côtés, corps du courriel accentué |

## État de la chaîne

`validate_release.py` sort désormais en **0** : sept portes publiées, quatre en
échec avec leur preuve, promotion refusée pour les deux seules raisons qui
valent. **Le job `image` peut être construit pour la première fois.**

## Ce que la phase 0 a appris, et qui n'était pas prévu

**Trois de mes propres affirmations ont été démenties par la mesure :**

1. « très probablement API-5 » pour le test rouge — c'était le `.env` (**ENV-1**) ;
2. « restreindre le critère de `redondance_features` » — cela aurait **remasqué**
   ce que l'auteur avait délibérément rendu visible ;
3. `Tag.confidence` déclaré inexistant sur la foi d'un `grep` (**DOM-6**).

Et **deux régressions introduites en une heure**, toutes deux attrapées par des
tests que le projet possédait déjà : un numéro de section lu comme un point
décimal, et mon journal d'audit balayé par le contrôle de documentation.

Le patron du § 3 du plan n'est pas une hypothèse : **il a mordu cinq fois en une
séance, dont deux fois sur moi.**

## Reste, par phase

- **A** — 16,2 Mo, 4 scripts orphelins, 3 dépendances, `.gitattributes` déclaré
- **C** — FRONT-1, API-2 (+ amender `test_api.py:348`), BANC-3 puis C2
- **Patron** — contrôles 1 et 2 dans `test_documentation.py`, mypy en CI,
  retirer les 60 lignes inline de `ci.yml`
- **B** — AL-1, WF-1, API-3, les deux pages, les tests HTTP
- **D** — rapport, ADR, architecture, runbook, notebook, **+ 4 écarts AMDEC,
  DOC-3, J-2 élargi (lexique et périmètre)**, contrôle 3
- **E1 puis E2** — dans cet ordre, une seule fois

---

# Reprise de `src/` — lecture intégrale, fichier par fichier

La session précédente avait **diagnostiqué** `src/` sans rien y corriger. Les
constats y étaient donc ouverts, et ils ont été traités à tort comme acquis.
Cette section reprend la lecture ligne à ligne, et **corrige au fur et à
mesure**. Chaque entrée dit ce qui a été lu, ce qui a été trouvé, et ce qui a
été fait.

## Lot S1 — la couche features (1 384 lignes lues intégralement)

`src/formatting.py` (165) · `src/config.py` (413) · `src/pipeline.py` (403) ·
`src/features/thermal.py` (411) · `src/features/e7301_features.py` (807)

### S1-0 — `formatting.py` et `config.py` : rien à reprendre

Lus en entier. `formatting.py` n'expose que cinq fonctions, toutes consommées,
et le repli NaN/None est uniforme. `config.py` tient sa promesse d'en-tête :
les 44 variables déclarées sont toutes lues quelque part, `validate()` couvre
chacune d'elles, et `summary()` ne publie aucun chemin absolu. Aucun constat.

### S1-1 — RETRACTATION : `ntu_de()` et `EFFECTIVENESS_MAX` ne sont pas morts

Le diagnostic précédent les déclarait inutilisés. C'est faux, et l'erreur est
du même type que celle déjà retirée sur `Tag.confidence` : une absence établie
par recherche de nom au lieu d'être suivie jusqu'à son point d'usage.

- `ntu_de()` est appelée `thermal.py:221`, dans le corps de
  `overall_conductance` — c'est-à-dire au cœur du calcul de UA.
- `EFFECTIVENESS_MAX` est lue trois fois, lignes 206, 214 et 217 : la borne du
  `clip`, le comptage des écrêtages, et le message de journal.

Ce sont des symboles **internes au module**, ce qui explique qu'une recherche
menée hors de `thermal.py` n'en trouve aucune trace. Constat retiré.

### S1-2 — `fouling_resistance` divergeait sans garde  → corrigé

`Rf = 1/UA − 1/UA_attendu`. `UA_attendu` est une prédiction linéaire **non
contrainte** : rien dans `np.linalg.lstsq` n'interdit une valeur proche de
zéro à des conditions extrêmes (débit très bas, eau de mer hors plage), et le
terme `1/UA_attendu` diverge alors. Une résistance d'encrassement de plusieurs
milliers de K/kW s'afficherait sur le poste — le tracé `encrassement` la sert
telle quelle — et se lirait comme un faisceau bouché.

Correction : plancher de 1 kW/K sur les deux termes, deux ordres de grandeur
sous toute valeur observée sur ce corpus (UA attendu y vaut 14 à 22 kW/K). La
grandeur devient **indisponible** plutôt que fausse.

### S1-3 — Trois colonnes calculées à chaque heure, lues par personne → retirées

Vérification menée sur `src`, `api`, `tests`, `scripts`, `notebooks`, `docs`,
extensions `.py .js .html .ipynb .yaml .md` :

| colonne | lecteurs trouvés | verdict |
|---|---|---|
| `approach_ratio` | **aucun**, nulle part | retirée |
| `fouling_resistance_trend_14d` | **aucun**, nulle part | retirée |
| `duty_per_load` | **un seul** : le test qui vérifie qu'elle existe | retirée |

`approach_ratio` se décrivait elle-même comme un « proxy sans mesure d'eau de
mer » : c'est précisément ce que la climatologie de Safi (ADR-002) a rendu
inutile, puisque UA est désormais calculé avec la température du fluide froid.
C'est un résidu de la conception antérieure à la correction scientifique.

`fouling_resistance_trend_14d` doublait `ua_residual_trend_14d`, seule tendance
que `FOULING_DRIFT` consulte réellement. En publier deux laissait croire à deux
critères de dérive là où il n'y en a qu'un.

`duty_per_load` était maintenue en vie par `test_features_de_performance_
nulles_a_larret`. Le test a été réaligné sur `flow_per_load`, qui est, elle,
dans `MODEL_FEATURES`. La normalisation à l'allure n'est donc pas perdue.

### S1-4 — API-7 : l'entrée externe et le seul résidu indépendant n'étaient servis nulle part

`/api/timeseries` construit sa liste de colonnes à partir de `raw_aliases`,
qui ne parcourt que la section `tags` de `tags.yaml`. Or **`T_SEAWATER` est
déclaré sous `external_inputs`** (ligne 331) : il n'était donc servi par
aucune route — alors que le poste en connaît déjà le libellé et l'unité
(`MESURE_LABEL`, `app.js:1592`). L'entrée qui rend UA calculable n'était pas
traçable, et l'on ne pouvait pas vérifier à l'œil que la saisonnalité de UA la
suit bien.

Même sort pour la référence d'entrée. `e7301_features.py` la désigne comme
« le seul indicateur de dégradation indépendant de la variable régulée »
(r = +0,03 contre −0,94 pour l'effort de régulation) et `t_in_residual_z` est
l'une des onze `MODEL_FEATURES` — mais ses trois colonnes étaient calculées et
jamais exposées.

Correction : `T_SEAWATER`, `t_in_expected`, `t_in_residual_z` et
`t_in_residual_trend_14d` ajoutés à la liste servie; deux familles de signaux
ajoutées au menu du poste (`entrée · observée / attendue` et
`source froide · eau de mer`), avec leurs libellés et unités.

### S1-5 — M-2 : deux derniers résidus de « jumeau »  → corrigés

`e7301_features.py:2` (titre du module) et `:599` (docstring de
`add_dynamic_features`, « là où le jumeau capte les dérives lentes »). Ce sont
les deux dernières occurrences du vocabulaire abandonné dans la couche
features; elles sont remplacées par la désignation des références réelles.

## Lot S2 — ingestion et domaine (1 433 lignes lues intégralement)

`src/ingest/dcs_loader.py` (586) · `src/domain/knowledge.py` (849)

### S2-1 — D-1 confirmé : le chemin absolu passait par une autre porte → corrigé

`config.summary()` relativise délibérément tous ses chemins, et le commentaire
qui le justifie est explicite : « un endpoint de diagnostic n'a aucune raison
de divulguer l'arborescence de la machine hôte, son nom d'utilisateur ni sa
structure de répertoires ». Le rapport d'ingestion publiait `str(path)` tel
quel — et il est servi par `/api/health` à travers `health_report()`. La
correction faite sur `/api/config` était donc contournée par la route voisine.
Même relativisation appliquée.

### S2-2 — Le référentiel et le code divergeaient sur la classification d'état → corrigé

`tags.yaml/process_states` annonçait `T_ACID_IN < 60` comme critère de
**TRANSIENT**. `classify_process_state` le place parmi les critères
d'**arrêt** — ce que dit d'ailleurs le nom de la clé qui le porte,
`T_ACID_IN.shutdown_below`, et le commentaire qui l'accompagne
(« ce seuil gouverne la classification d'état de marche »). Le critère de
reprise après arrêt (`is_down.shift(1)`) ne figurait pas du tout dans la prose.

C'est la décision la plus déterminante du système — elle décide quelles heures
sont jugeables — et sa description publique ne correspondait pas à son
exécution. Les trois règles de `process_states` disent maintenant exactement ce
que fait le code. Aucun test n'en dépendait, ce qui explique la dérive.

### S2-3 — `fillna(0)` sur les entrées de classification : conservé, mais énoncé

Le module s'interdit partout d'inventer une donnée, et `classify_process_state`
remplit pourtant les manquants par zéro — ce qui déclare STOPPED. Vérifié :
la fonction est appelée deux fois, et au second appel les NaN sont ceux que la
détection de défaut capteur vient de poser. Le zéro tranche donc l'indécision
dans le sens qui **exclut** l'heure du jugement de performance, seul sens
acceptable.

Décision : ne pas changer le comportement — la modification déplacerait des
heures vers RUNNING, donc déplacerait la borne de `reference_cutoff`, qui
compte les heures de marche — mais **écrire le raisonnement dans le code**,
avec son prix : ces heures s'affichent « ligne à l'arrêt » alors qu'elles sont
des heures de mesure indisponible.

### S2-4 — K-1 vérifié surface par surface

| surface | lecteurs | décision |
|---|---|---|
| `bareme_gravite` / `frequence` / `detection` | **aucun** | **publiées** |
| `Tag.criticality_link` (5 tags le portent) | **aucun** | **publié** |
| `FailureMode.immediate_severity` (2 modes) | **aucun** | publié, à instruire |
| `process_states` | **aucun** | **publié** |
| `components_for_mode()` | **aucun** | supprimée |
| `modes_for_component()` | `judge_agent.py:672` | conservée |
| `locate_finding()` | tests seuls | conservée, voir S2-6 |

Les trois barèmes sont transcrits des onglets **GRV, OCC et DET** du classeur
AMDEC d'OCP. Ce sont eux qui donnent un sens à « G = 7 » ou « N = 5 », donc à
chacune des treize criticités affichées. Les charger sans jamais les montrer
revenait à publier des nombres que rien ne définit, alors que le référentiel
porte leur définition exacte. `/api/equipment` les sert désormais, et chaque
ligne AMDEC cite son échelon en infobulle.

`criticality_link` rattache cinq capteurs à un mode de défaillance, avec le
raisonnement en clair dans `tags.yaml` (« 904L : la vitesse de corrosion en
H2SO4 98 % croît fortement au-delà de 110 °C — Réf AMDEC :
FAISCEAU_CORROSION »). Le tiroir capteur énonçait des seuils sans jamais dire
quel risque le capteur sert à couvrir. Il le dit maintenant, dans les deux
routes qui décrivent un capteur.

### S2-5 — L'écran démentait la correction serveur sur l'observabilité → corrigé

`api/main.py` publie `observabilite` à trois valeurs depuis une correction dont
le commentaire dit le motif : « le booléen seul faisait afficher *non — angle
mort* sur des modes que le détecteur rattache activement à des constatations ».

`app.js:1397` lisait toujours `m.observable ? "oui" : "non — angle mort"`.

C'est le seizième cas — et le plus visible — du motif établi par cet audit :
**corrigé d'un côté, pas de son jumeau, et c'est toujours le code de service
qui porte la version juste et l'affichage la version périmée**. Ici la
conséquence est directe : la table AMDEC affichait « angle mort » sur la
corrosion du faisceau et la fuite de calandre, deux modes que le moteur de
règles déclenche. La colonne a maintenant les trois états, avec l'aide qui dit
ce que « partielle » implique.

### S2-6 — `locate_finding` : vérifié, ce n'est pas un doublon fautif

Le front ne réimplémente pas une règle : `twinStateFrom` fait la même lecture
directe de `finding_map`, table gouvernée servie par `/api/topology`, avec la
même garde (« un code inconnu n'allume rien »). Les deux côtés lisent la même
source; la mise en évidence 3D est nécessairement cliente. Aucune correction.

## Lot S3 — le détecteur (1 334 lignes lues intégralement)

`src/models/detector.py`

### S3-1 — M-1 confirmé : le seul endroit du dépôt qui enfreignait sa propre règle → corrigé

`_fouling_warning_sigma` écrivait :

```python
seuil = (mode.signature.get("warning_sigma") if mode else None) or 3.0
return max(float(seuil), DRIFT_Z_THRESHOLD)
```

Deux fautes superposées sur six lignes.

L'idiome `or` est exactement celui que `src.domain.knowledge.seuil` existe
pour abolir — sa docstring dit « le repli teste l'absence, pas la fausseté »
et recense les douze endroits où il avait été remplacé. Le module importe
d'ailleurs `seuil` ligne 49 et l'emploie correctement **huit fois** ailleurs :
lignes 256, 257, 461, 462, 537, 538, 564, 565.

Et la variable locale s'appelait `seuil`, masquant donc la fonction importée
dans cette portée : la fonction qui corrige le défaut était inaccessible sous
son propre nom, à l'endroit précis où le défaut se reproduisait.

**Preuve par mutation** (les deux implémentations comparées hors dépôt) :

| `warning_sigma` gouverné | ancien | nouveau |
|---|---|---|
| absent | 3,0 | 3,0 |
| 2,5 | 2,5 | 2,5 |
| **0** | **3,0** | **1,5** |

Un `warning_sigma: 0` — réglage parfaitement légitime, signifiant « toute
perte de coefficient d'échange persistante passe en WARNING » — était
silencieusement remplacé par 3,0. C'est précisément le scénario que la
fonction `seuil` documente.

### S3-2 — La correction de la fenêtre n'avait pas été portée jusqu'à la preuve publiée → corrigé

Le commentaire de `_rule_thermal_drift` explique, sur huit lignes, que
`persistance_h` « publiait un nombre de lignes sous un nom d'heures », et la
fenêtre est bien devenue calendaire. Mais la preuve valait toujours
`len(recent)` : le nombre d'heures **où la tendance était calculable** dans la
fenêtre — donc toujours un compte de lignes, sous toujours le même nom.

Trois champs distincts remplacent le champ ambigu : `fenetre_h` (constante
calendaire), `heures_mesurees_dans_la_fenetre`, `part_sous_le_seuil`. Aucun
consommateur n'existait pour `persistance_h`, vérifié sur tout le dépôt.

### S3-3 — M-2 : la classe documentait un paramètre qui n'existe pas → corrigé

`CoolerAnomalyDetector` documentait, dans ses `Attributes` **et** dans les
`Args` de `__init__`, un paramètre `twin: Jumeau thermique`. Le paramètre
réel s'appelle `references` et n'était documenté nulle part. La signature
décrivait donc un argument absent et taisait celui qu'elle accepte.

### S3-4 — Le cache de scores ne distinguait pas deux tables → corrigé

La clé valait `(longueur, premier horodatage, dernier horodatage)`. Deux
tables construites sur la même période, avec le même nombre de lignes et des
**valeurs différentes**, recevaient la même clé — et la seconde se voyait
servir les scores de la première.

C'est exactement ce que produit le banc d'injection d'encrassement, qui
superpose une rampe aux données réelles sans toucher à l'index. Vérifié :
`FoulingInjectionBench` n'exploite pas ce chemin, parce qu'il évalue le
prédicat de la règle déterministe (`_fouling_hours`) et ne sollicite jamais
l'étage statistique. Le piège ne se déclenche donc pas aujourd'hui — mais il
rendrait un résultat **faux sans rien signaler**, et rien ne garantit que le
banc restera déterministe. La clé intègre désormais une empreinte du contenu
(somme des features du modèle, ~1 ms sur dix mille lignes contre plusieurs
dizaines pour la forêt que le cache évite).

### S3-5 — `severite_immediate` : détermination de gouvernance sans effet → verrouillée

`amdec.yaml` déclare `signature.severite_immediate` pour deux modes —
CRITICAL pour FAISCEAU_FUITE, WARNING pour CAPTEUR_DEFAILLANT — et
`FailureMode.immediate_severity` la charge. **Aucun appelant ne la lisait.**
Le service fiabilité pouvait la corriger dans le référentiel sans qu'aucune
alerte ne change.

L'appliquer comme plancher aurait cassé une gradation voulue : `CONC_DROP`
est délibérément WARNING (« à confirmer par prélèvement laboratoire ») tout en
portant FAISCEAU_FUITE. La sémantique juste est donc : la sévérité déclarée
est celle que le mode atteint **au plus haut**.

C'est ce qu'établit désormais un test par analyse du source de `RuleEngine` —
le patron déjà employé sept fois dans le dépôt. Il lit les `Finding(...)`
construits, apparie `amdec_mode` et `severity`, compare au référentiel.
Mesuré à l'écriture :

| mode | sévérités émises | plafond | AMDEC |
|---|---|---|---|
| FAISCEAU_FUITE | WARNING, CRITICAL | CRITICAL | CRITICAL ✓ |
| CAPTEUR_DEFAILLANT | WARNING | WARNING | WARNING ✓ |

Limite énoncée : le test verrouille le **plafond collectif** d'un mode. Deux
règles portant FAISCEAU_FUITE en CRITICAL, abaisser l'une des deux ne le fait
pas échouer. Il interdit la dérive du référentiel et l'abaissement complet
d'un mode, pas la modification d'une règle isolée.

### S3-6 — Constat mineur, non corrigé

`test_agregation_en_episodes` affirme `ep["score_max"].is_monotonic_decreasing`
alors que `episodes()` trie sur `margin_max` depuis la correction de la
saturation du score. Les deux grandeurs étant monotones en score brut,
l'assertion reste vraie — mais elle vérifie une propriété de l'ancienne clé de
tri, et le score sature, donc elle passe surtout par égalités. Elle ne protège
plus grand-chose. Signalée, pas réécrite : elle n'est pas fausse.

## Lot S4 — l'agent de détection (780 lignes lues intégralement)

`src/agents/detection_agent.py`

### S4-1 — A-1 confirmé, et le contrôle échantillonnait la population complémentaire

`_quote_measurements` rendait :

> « entree acide 94.23 degC, sortie acide 65.91 degC, debit acide 56.40 m3/h »

Trois fautes cumulées — libellés sans accents, unités en ASCII là où le
référentiel et le poste écrivent « °C » et « m³/h », point décimal anglais.

**Pourquoi rien ne l'a vu.** Cette fonction n'est appelée que par la branche
NOMINALE de `_nominal_decision`, c'est-à-dire quand il n'y a **aucune**
constatation actionnable. Or `test_les_messages_de_detection_sont_accentues`
échantillonne `notable_timestamps(12)` — par construction, exactement les
instants qui en portent une. Le contrôle inspectait le complémentaire de la
population qui peut déclencher le défaut.

Et même échantillonné, il l'aurait laissé passer : `entree` et `debit` ne
figuraient pas dans le lexique des 44 mots. Deux verrous manquants sur le même
texte, qui est pourtant la phrase la plus fréquemment produite du système —
l'immense majorité des heures de marche établie sont nominales.

Corrigé aux trois niveaux : la fonction, le lexique (7 mots ajoutés, dont les
3 déjà relevés en J-2), et un test dédié aux instants nominaux.

### S4-2 — LE PLUS GROS ANGLE MORT TYPOGRAPHIQUE DU DÉPÔT

En cherchant l'origine de S4-1, un défaut plus large est apparu.

`src/formatting.py` s'ouvre sur : « un test parcourt les sorties du système
pour vérifier qu'aucun nombre n'échappe à la règle ». **C'était faux pour la
plus grande surface de texte du projet.**

Les vingt-trois messages du moteur de règles formataient leurs valeurs par
f-string — `f"...{t_out:.1f} °C"` — et rendaient donc « 66.3 °C ». Ces
messages remplissent le journal du rejeu, la carte de diagnostic, le registre
d'alarmes et les courriels d'escalade.

**Deux tests se partagent la typographie, et chacun couvrait une moitié
différente sur une population différente :**

| test | cherche | échantillonne |
|---|---|---|
| `..._messages_de_detection_sont_accentues` | accents | constatations ✓ |
| `..._aucun_point_decimal_dans_les_textes_affiches` | point décimal | indicateurs, sensibilité, backtest — **jamais une constatation** |

L'intersection était vide. C'est le même motif que S4-1, un cran au-dessus :
non pas une branche non échantillonnée, mais **un croisement de critère et de
population que personne n'avait fermé**.

Corrigé : helper `_n()` adossé à `src.formatting`, 23 sites convertis dans
`detector.py`, `_pretty` réécrite, `m3/h` → `m³/h`, et le contrôle du point
décimal étendu aux constatations, diagnostics, raisonnements et actions.

### S4-3 — A-2 : une réponse mal formée coupait le LLM pour tout le processus

Le coupe-circuit s'ouvrait sur `Exception` et posait `self.llm = None`
définitivement. Un unique JSON tronqué — le mode d'échec le plus banal d'un
modèle de langage, celui que `_extract_json` est écrit pour rencontrer —
désactivait donc la rédaction pour toutes les heures suivantes, en
journalisant « Agent LLM indisponible », ce qui était faux : le service
répondait.

Conséquence directe sur la démonstration : le premier point mal rendu
basculait toute la session en mode règles, et l'apport du LLM devenait
inobservable sans qu'on sache pourquoi.

Les deux familles sont désormais distinguées. Réponse inexploitable
(`ValueError`, `JSONDecodeError`, `KeyError`, `TypeError`, `ValidationError`)
→ repli sur cet instant, **circuit maintenu fermé**. Panne franche → circuit
ouvert, comme avant.

### S4-4 — A-3 : trois paramètres documentés et jamais lus

`compose(result, case)` recevait le dossier de faits et ne le lisait jamais :
le corps entier travaille sur `result`. Le paramètre disait le contraire de ce
que la classe fait, et laissait croire que le compositeur déterministe et le
LLM partagent la même entrée — seul le second lit le dossier.

Le coût n'était pas nul : `analyze()` appelait `build_case_file` **avant** de
savoir si le LLM allait servir, donc à chaque instant du rejeu, y compris en
mode règles seules. Sa construction parcourt les modes AMDEC et le plan
préventif. Il n'est plus assemblé que si la rédaction va l'utiliser.

`_calibrate_confidence(result, lead, mode)` : `lead` et `mode` inutilisés
également. Le premier était annoté « conservée pour la signature » — l'aveu
qu'il ne servait à rien; le second n'avait même pas cet aveu.

### S4-5 — A-5 : la même distinction, lue d'un côté et écrite en dur de l'autre

`_build_action` tranchait « instrumentation ou équipement » par
`mode.code == "CAPTEUR_DEFAILLANT"`. Or `_priorite`, dans le même fichier,
tranche exactement la même question en lisant `sous_equipement` dans le
référentiel — avec un commentaire disant que la distinction « est lue dans le
référentiel, pas écrite ici ».

Ajouter un second mode d'instrumentation dans `amdec.yaml` l'aurait fait
trier comme un défaut de mesure par l'une, et adresser au service mécanique
par l'autre. Les deux lisent maintenant la même clé.

## Lot S5 — le contrôleur (1 290 lignes lues intégralement)

`src/agents/judge_agent.py` · `src/agents/schemas.py` (surfaces concernées)

### S5-1 — La correction typographique de S4-2 aurait cassé V1 en silence

`_extract_numbers` lit les nombres du diagnostic pour vérifier qu'ils sont
rattachables aux faits. Son motif s'arrête à l'espace. Or `src.formatting`
écrit dix mille cent quatre-vingt-deux « 10 182 », avec une espace insécable
étroite (U+202F).

**Preuve par mutation :**

| texte | ancien lecteur | nouveau |
|---|---|---|
| `Puissance évacuée 10 182 kW` | `[10, 182]` | `[10182]` |
| `Titre acide à 98,36 %` | `[98.36]` | `[98.36]` |

Ni 10 ni 182 ne figurent dans les faits : V1 aurait signalé « nombres non
rattachables aux mesures » sur un diagnostic parfaitement exact, et plafonné
sa note à 5/10.

Le cas ne se présentait pas tant que les messages étaient en notation
anglaise — c'est-à-dire tant qu'ils étaient fautifs. **Corriger l'affichage
sans corriger le lecteur aurait transformé un défaut de forme en faux positif
de gouvernance.** C'est le risque propre à ce type de correction, et il n'était
signalé nulle part.

### S5-2 — Troisième surface du même angle mort typographique

Les détails des huit contrôles citaient « 0.85 annonce contre 0.70 » et
« annonce 66.3, mesure 66.1 », et quatre libellés sur huit étaient sans
accents — « Les valeurs citees correspondent-elles aux mesures reelles ? ».
C'est le texte de l'encart « Réserves du contrôleur », seul endroit où une
anomalie de calibration est présentée à l'exploitant.

`test_les_controles_du_juge_sont_accentues` les regardait déjà — mais ne
cherchait, là encore, que des accents. Le contrôle du point décimal leur est
étendu, ainsi qu'à la synthèse du verdict.

### S5-3 — J-1, J-4, J-5 : trois surfaces mortes, dont deux pires que mortes

`Check.issue_code` — propriété annoncée « pour compatibilité d'affichage »,
rendant le premier élément de `issue_codes`. Aucun appelant, aucun test, et
aucun affichage : le poste lit la liste entière. V4 cumule jusqu'à quatre
codes; n'en exposer qu'un les aurait masqués. **Supprimée.**

`JudgeVerdict.validation_scope` — un `Literal` à **une seule** valeur admise,
avec cette valeur pour défaut. Un champ qui ne peut rien porter d'autre qu'une
constante. **Supprimé.**

`JudgeVerdict.uncertainty_level` — déclaré à trois valeurs, ne valait jamais
que `"high"`, ni au défaut ni au seul site de construction. Ce n'est pas une
simple redondance : **annoncer un champ à trois états laisse entendre que le
contrôleur pourrait, dans de bonnes conditions, descendre à `"low"`.** C'est
exactement la sur-promesse contre laquelle tout l'en-tête du module met en
garde — l'incertitude du Judge est structurelle, il recalcule avec les mêmes
données et les mêmes référentiels, et aucune combinaison de résultats ne la
fait baisser. **Supprimé**; l'énoncé survit dans `limitations`, en toutes
lettres et sans graduation implicite.

## Lot S6 — le banc d'évaluation du Judge (700 lignes lues intégralement)

`src/governance/judge_eval.py` · `src/agents/schemas.py` (surfaces concernées)

### S6-1 — Le banc se déclare reproductible et laissait le LLM décider

`__init__` fixe la graine avec ce motif explicite : « les mutations non ciblées
doivent être reproductibles, **sinon le chiffre de généralisation change à
chaque exécution** ».

Trois lignes plus bas, `agent.analyze(detection)` et `judge.judge(...)`
prenaient leur défaut `use_llm=True`.

Conséquence dès qu'une clé Gemini est présente : la décision **saine** est
rédigée par le modèle, et le Judge s'autorise un ajustement de ±1,5 point sur
**chaque** verdict — sain comme muté. Or `penalised` compare la note mutée à la
note saine, et `separation` est la différence des moyennes. Les deux chiffres
que le rapport publie devenaient aléatoires, et la graine n'y changeait rien :
elle ne gouverne que le tirage des mutations.

Le banc mesure les huit contrôles **déterministes**. La couche de rédaction
n'entre pas dans son objet, et sa présence rendait le résultat indémontrable.
`use_llm=False` sur les trois sites.

### S6-2 — Le dénominateur du chiffre de généralisation contenait des non-événements

`wrong_checklist` rend la décision **inchangée** quand `checklist_ref` ne vaut
ni `INSPECTION_EXTERNE` ni `INSPECTION_INTERNE` — cas fréquent, le champ étant
facultatif. Le verdict était alors identique à celui de la décision saine, donc
`caught=False`, `penalised=False`, et la ligne entrait au dénominateur.

Le chiffre publié comme « mesure honnête de ce que le Judge attrape sans
l'avoir anticipé » comptait donc des essais **où rien n'avait été tenté**.

Le biais va dans le sens de la prudence — il abaisse le taux — mais un banc
dont le dénominateur contient des non-événements ne mesure pas ce qu'il
annonce, et le sens du biais n'y change rien. La comparaison se fait désormais
sur le contenu sérialisé (`_clone` produit toujours un objet distinct, même
quand il recopie à l'identique), et la lecture publiée dit ce qui est écarté.

### S6-3 — Trois orthographes du même service, dont la valeur par défaut

| fichier | chaîne |
|---|---|
| `schemas.py` (défaut de `responsible`) | `Service Mecanique PS III` |
| `detection_agent.py` (`_build_action`) | `Service Mécanique PS III` |
| `judge_eval.py` (mutation) | `Service Mecanique PS III` |

Et la décision **nominale** ne renseigne pas ce champ : elle prend le défaut, et
affichait donc « Mecanique » à l'exploitant sur la formulation la plus
fréquente du système. **Même angle mort que `_quote_measurements`, au même
endroit, invisible au contrôle typographique** puisque « mecanique » ne figure
pas dans son lexique.

La mutation `wrong_responsible` basculait par ailleurs sur `"Instrumentation"
in courant` — une comparaison par sous-chaîne là où deux constantes suffisent.
Les deux noms vivent maintenant une seule fois, dans `schemas.py`, accentués,
et les trois fichiers les lisent.

### S6-4 — Un test qui n'acceptait la lecture que si elle était mal écrite

`test_les_mutations_non_ciblees_mesurent_la_generalisation` se terminait par
`assert "honnete" in blind["reading"]`. Il a échoué à la seconde où ce texte a
été correctement accentué.

C'est le défaut exact que documente `src.formatting.sans_accents` : le contrôle
V8 cherchait « reserve », « defaut », « degrade » dans des textes accentués et
échouait sur 100 % des heures hors marche. Ici, le même piège du côté des
tests — un contrôle qui verrouille la faute au lieu du fond.

| | texte accentué |
|---|---|
| `"honnete" in reading` | **False** |
| `"honnete" in sans_accents(reading)` | True |

La règle du dépôt est désormais appliquée des deux côtés : le texte **comparé**
est dépouillé, le texte **affiché** est accentué. L'assertion a été renforcée
au passage — elle exige aussi que la lecture mentionne le dénominateur, sans
quoi le chiffre de S6-2 redeviendrait ininterprétable.

## Lot S7 — le banc d'injection d'encrassement (467 lignes lues intégralement)

`src/governance/fouling_injection.py`

### S7-1 — Une fenêtre pouvait être « calme » parce que la ligne était à l'arrêt

`_quiet_start` cherche une fenêtre où la règle ne se déclenche pas sur les
données réelles, pour que la détection mesurée soit attribuable à la rampe.
Son unique critère était `not window.any()` — l'absence de déclenchement.

Or les deux bouts de la chaîne exigent la marche établie :

- `_fouling_hours` filtre sur `process_state == "RUNNING"` ;
- `inject_fouling` n'altère que les heures de marche
  (`effect = advancement.where(running, 0.0)`).

**Un arrêt de ligne satisfait donc le critère de calme sans pouvoir rien
porter.** La rampe n'y modifie aucune température, la règle ne peut pas s'y
déclencher, et le scénario était pourtant enregistré « NON DÉTECTÉE ».

C'est exactement le défaut relevé en S6-2 sur le banc du Judge, dans un autre
module et pour un autre chiffre : **un dénominateur qui contient des essais où
rien n'a été tenté.** Ici il abaisse le taux de détection et dégrade
l'avancement médian publié. Le biais est prudent — et un chiffre faussé dans le
bon sens reste un chiffre faussé, d'autant qu'il figure dans le rapport.

Correction : la moitié au moins de la fenêtre doit être en marche établie. Le
corpus compte 1 385 heures d'arrêt sur 10 182, réparties en épisodes : la
contrainte reste satisfiable. La limite est publiée dans `limitations`.

### S7-2 — « Le détecteur n'est pas réentraîné » : vrai par accident, pas par construction

`to_dict()` annonçait « le détecteur n'est pas réentraîné sur les données
modifiées ». L'Isolation Forest ne l'est pas — le banc ne le sollicite jamais,
il évalue le prédicat déterministe. Mais `build_features(injected, ...)` **réajuste
les trois références thermiques** sur la table injectée.

Vérifié : la fenêtre d'apprentissage s'achève à `ref_end`, et la rampe démarre
au plus tôt à `ref_end + 7 jours`. Les références ne voient donc effectivement
aucune donnée modifiée. **Mais c'est une conséquence du placement de la rampe,
pas une propriété du code** : rapprocher le début de la rampe ferait apprendre
aux références la dégradation qu'elles doivent révéler, sans qu'aucun garde-fou
ne le signale. L'énoncé dit maintenant ce qui se passe réellement.

## Lot S8 — l'analyse de sensibilité (265 lignes lues intégralement)

`src/governance/sensitivity.py` · `src/features/thermal.py` (docstring)

### S8-1 — Une revendication de non-divergence, démentie par le module qu'elle cite

`thermal.reference_cutoff` porte cette phrase dans sa docstring :

> « La formule reprend celle de `src.governance.sensitivity`, qui coupait déjà
> sur les heures de marche : **les deux modules ne peuvent plus diverger.** »

Ils divergeaient au moment même où la phrase a été écrite.

```python
# thermal.reference_cutoff
position = max(0, int(len(running) * fraction) - 1)

# sensitivity.reference_period_sensitivity
cut = running_index[int(len(running_index) * fraction) - 1]
```

La garde `max(0, ...)` manque du second. **Preuve par mutation :**

| n heures de marche | fraction | indice ancien | nouveau |
|---|---|---|---|
| 8 800 | 0,25 | 2 199 | 2 199 |
| 8 800 | 0,40 | 3 519 | 3 519 |
| 120 | 0,005 | **−1** | 0 |
| 50 | 0,01 | **−1** | 0 |

Un indice `-1` désigne la **dernière** heure de marche : la période de référence
devient le corpus entier, et la référence apprend comme normale la dégradation
qu'elle doit révéler. En silence — et précisément dans l'analyse dont l'objet
est de chiffrer l'effet de cette fenêtre.

La grille actuelle ne l'atteint jamais. Ce n'est pas le point : **reprendre une
formule n'est pas la partager.** `sensitivity` appelle maintenant
`reference_cutoff`, et la docstring dit ce qui s'est réellement passé.

### S8-2 — Trois écritures de la même convention, dans le module qui la mesure

`contamination_sensitivity` se repliait sur `matrix.iloc[: len(matrix) // 2]`,
soit **50 %**, quand tout le reste du système s'arrête à `REFERENCE_FRACTION =
0.40`. Trois écritures d'une même convention — 0,40 dans `thermal`, la formule
recopiée plus bas dans ce fichier, 0,50 ici — dans le module dont l'unique
raison d'être est de mesurer l'effet de cette convention.

### S8-3 — Le raisonnement n'avait été appliqué qu'à une moitié de la fonction

Ligne 151, un commentaire justifie l'import du prédicat d'encrassement :
« un prédicat recopié dérive de son original ». Dix lignes plus haut, la voie
« température d'entrée » comparait à `1.5` écrit en dur — la valeur de
`DRIFT_Z_THRESHOLD`. La voie UA lisait le détecteur, la voie entrée gardait sa
constante. Les deux lisent maintenant la même source.

## Lot S9 — la traçabilité des artefacts (299 lignes lues intégralement)

`src/governance/lineage.py`

### S9-1 — Un constat de cet audit, introduit PAR cet audit

`EXTERNAL_DATA_GATES = MANDATORY_GATES - SOFTWARE_GATES` a été ajoutée en
phase 0, par symétrie : puisqu'on séparait les portes qu'une modification de
code peut casser, il paraissait naturel de nommer les autres.

**Aucun appelant ne l'a jamais lue.** `validate_release.py` n'importe que
`failed_mandatory_gates` et `failed_software_gates`. C'est exactement le défaut
retiré partout ailleurs dans ce travail — un nom sans lecteur, qui donne au
fichier une apparence de complétude et oblige chaque relecture à redémontrer
qu'il ne sert à rien — et il a été écrit par cet audit. Supprimée ; le
complément se lit en une soustraction, et le commentaire l'énonce.

### S9-2 — Le refus le plus probable était le moins explicite

`validate_model_manifest` refusait un artefact sur « versions de bibliothèques
incompatibles », sans nommer un seul paquet.

C'est le refus **le plus probable** de toute la fonction — un `pip install` qui
monte pandas d'un correctif suffit — et il laissait l'exploitant sans point de
départ, là où le refus sur Python, six lignes plus haut, cite ses deux valeurs.

| | message |
|---|---|
| avant | `versions de bibliothèques incompatibles` |
| après | `versions de bibliothèques incompatibles — pandas : manifeste=2.2.2, runtime=2.2.3` |

`pipeline._load_compatible_artifact` avait déjà été corrigé sur ce motif exact
(« UN REFUS DOIT DIRE QUOI FAIRE ») — la correction n'avait pas été portée à la
cause qu'il rapporte.

### S9-3 — LIN-1 : deux statuts déclarés que rien ne produit — OUVERT

Vérifié sur `src`, `api`, `tests`, `scripts`, `docs` : `validated_offline` et
`rejected` n'apparaissent nulle part ailleurs que dans `PROMOTION_STATUSES`.
`build_manifest` écrit toujours `candidate`; seuls les trois statuts de
`RUNTIME_STATUSES` sont atteignables ensuite.

Le vocabulaire annonce donc un cycle de vie dont le code n'implémente que la
moitié. Et les deux intrus ne sont pas inoffensifs : `validate_model_manifest`
les accepte comme statuts **connus**, si bien qu'un manifeste écrit à la main
annonçant `rejected` franchit le contrôle de vocabulaire avant d'être refusé au
suivant — pour un motif qui ne dit pas que ce statut n'a jamais pu être produit
légitimement.

**Non corrigé volontairement.** Trancher exige de lire
`scripts/promote_model.py` pour savoir si le refus d'une promotion doit
s'inscrire dans le manifeste ou rester hors artefact. Supprimer `rejected` à
l'aveugle priverait un modèle refusé de tout moyen de le dire. Le constat est
consigné, pas résolu.

### S9-3 bis — LIN-1 CLOS après lecture de `scripts/promote_model.py` (199 lignes)

Le constat laissé ouvert au lot précédent est tranché. Le script confirme
**par deux gardes indépendantes** qu'aucun statut hors `RUNTIME_STATUSES` n'est
écrivable :

```python
analyseur.add_argument("--statut", choices=sorted(RUNTIME_STATUSES), ...)
...
if statut not in RUNTIME_STATUSES:      # re-vérification dans promouvoir()
```

Le seul autre producteur est `build_manifest`, qui écrit toujours `candidate`.

Et surtout, les deux statuts n'étaient pas seulement morts, ils étaient
**redondants avec ce que le manifeste porte déjà** :

| statut fantôme | équivalent déjà présent |
|---|---|
| `rejected` | `candidate` + `failed_mandatory_gates` non vide |
| `validated_offline` | `candidate` + `failed_mandatory_gates` vide |

C'est exactement la doctrine que le script énonce : un refus **ne s'écrit pas**,
il se constate à l'absence de promotion. Les deux ont été retirés du
vocabulaire. Effet concret : un manifeste écrit à la main annonçant `rejected`
était refusé pour « statut non autorisé au runtime » — motif qui laisse croire
à un réglage. Il l'est maintenant pour « statut de promotion inconnu », ce qui
est le fait.

**Verrou** (le patron, huitième emploi) —
`test_tout_statut_de_promotion_declare_est_productible` établit par analyse du
source qu'il n'existe que deux producteurs et que leur union couvre exactement
le vocabulaire.

**Preuve par mutation** : réintroduire `"rejected"` dans `PROMOTION_STATUSES`
fait apparaître un orphelin et le test échoue. Vérifié.

## Lot S10 — les indicateurs d'exploitation (340 lignes lues intégralement)

`src/analytics/kpi.py`

### S10-1 — KPI-1 : un champ devenu constante, et son exemple devenu fantôme

L'en-tête déclare que `evidence_level` sépare `observed` de `derived`, et
donne pour exemple de `derived` : « énergie évacuée en excès ».

C'est **exactement le chiffre que `overcooling_regime` explique avoir retiré** :
la méthode consacre douze lignes à dire pourquoi les MWh ont disparu — ils
« déplaçaient un constat de conduite vers un registre économique que ce projet
n'a pas les données pour traiter ».

Le seul producteur de `derived` ayant été supprimé, **les six indicateurs
annonçaient tous `observed`** : le champ ne distinguait plus rien, et sa
documentation renvoyait à une grandeur qui n'existe plus. Même défaut que
`uncertainty_level` sur le verdict du Judge (S5-3), à un détail près qui
l'aggrave — ici le vocabulaire promet une distinction que le module considère
comme une exigence de probité, pas comme un ornement.

### S10-2 — Et trois résultats de modèle étaient présentés comme des mesures

L'en-tête dit qu'une grandeur `derived` « ne doit **jamais** être présentée
comme une mesure ». Trois indicateurs le faisaient :

| indicateur | ce qu'il lit | déclarait |
|---|---|---|
| `overcooling_regime` | `regulation_effort_trend_14d`, résidu d'une régression apprise | `observed` |
| `alert_load` | des épisodes issus des scores de l'Isolation Forest | `observed` |
| `flag_rate` | des scores et un seuil, tous deux appris | `observed` |

Le cas d'`alert_load` est le plus lourd de conséquence : le **« ~5 épisodes par
mois »** cité ailleurs dans le projet est un résultat de modèle, sensible au
choix de la période de référence dont `sensitivity` chiffre l'effet — et il
était étiqueté comme un comptage.

Les cinq figures concernées passent en `derived`; `measurement_availability` et
`corrosion_exposure` restent `observed`, elles ne lisent que `DATA.xlsx` et
`tags.yaml`.

**Verrou** (neuvième emploi du patron) —
`test_le_niveau_de_preuve_distingue_reellement_deux_natures` exige les deux
natures dans la même restitution, puis vérifie par analyse du source que toute
méthode lisant une grandeur issue d'un ajustement se déclare `derived`.
**Preuve par mutation** : remettre `alert_load` en `observed` fait échouer le
test. Vérifié.

### S10-3 — Le test qui figeait le défaut ne justifiait que la moitié du critère

`test_le_niveau_de_preuve_est_declare_pour_chaque_indicateur` affirmait
`overcooling_regime().evidence_level == "observed"`, avec ce motif :

> « Le régime de sur-refroidissement se lit sur l'écart de consigne mesuré :
> c'est une observation. »

L'écart de consigne est bien mesuré — mais ce n'est pas le critère.
`overcooling_regime` en exige **deux**, et sa propre docstring le dit : « plus
d'un demi-degré sous consigne **ET** une dérive confirmée de la référence ».

```python
sustained = (dev < -0.5) & (trend > 1.0)
```

`trend` est `regulation_effort_trend_14d`, résidu d'une régression apprise sur
la période de référence — dont `sensitivity` chiffre l'effet du choix. **La
seconde moitié du critère, celle que la justification passait sous silence, est
exactement ce qui rend l'indicateur dérivé.**

Retirer les MWh a supprimé un registre économique injustifiable ; cela n'a pas
transformé la grandeur restante en mesure. Le test a été aligné avec la preuve
plutôt que l'inverse.

Effet visible : `app.js:1282` sait déjà afficher « grandeur dérivée » contre
« grandeur observée ». Le poste portait ce libellé sans qu'aucune figure ne
puisse jamais le déclencher — cinq cartes le porteront désormais.

## Lot S11 — le registre des techniciens (363 lignes lues intégralement)

`src/security/registry.py`

### S11-1 — SEC-1 : le principe était énoncé onze lignes au-dessus des méthodes qui l'enfreignaient

`load()` construit son dictionnaire à part puis le publie d'un coup, avec ce
motif écrit dans le fichier :

> « Publication ATOMIQUE. **Les accesseurs de lecture ne prennent pas le
> verrou**; remplir le dictionnaire en place exposait un registre partiellement
> chargé à un rechargement concurrent. »

`add`, `set_password` et `remove` mutaient pourtant `self._operators` **en
place** :

```python
self._operators[normalized] = operator      # add
self._operators[normalized] = Operator(...) # set_password
del self._operators[normalized]             # remove
```

Le verrou protège les écrivains les uns des autres, **pas les lecteurs** —
c'est la prémisse même du commentaire. Or cinq accesseurs parcourent le
dictionnaire sans verrou : `emails`, `roles`, `password_hashes`,
`alert_recipients`, `listing`.

FastAPI sert ses endpoints dans un pool de threads. Un `remove()` concurrent
d'une authentification levait donc `RuntimeError: dictionary changed size
during iteration` **au milieu de `password_hashes()`** — c'est-à-dire sur le
chemin d'ouverture de session, et sur l'action « retirer une habilitation »,
qu'on exécute précisément quand la situation est tendue.

**Preuve par mutation** (quatre lecteurs, 400 suppressions) :

| | RuntimeError levées |
|---|---|
| mutation en place | **4** — `dictionary changed size during iteration` |
| publication atomique | 0 |

Les trois méthodes passent par `_publier()`, qui construit un dictionnaire
complet et le substitue par une seule affectation. Un lecteur voit l'ancien
registre ou le nouveau, jamais un état intermédiaire.

## Lot S12 — la validation du modèle (592 lignes lues intégralement)

`src/governance/model_validation.py` · `api/static/app.js` (surfaces concernées)

### S12-1 — CONSTAT OUVERT TRANCHÉ : le seuil PSI de 0,25, et pire que son origine

Le constat laissé ouvert en phase 0.7 disait que **0,25 est la borne du
*Population Stability Index* en scoring de crédit et n'a jamais été justifiée
pour un procédé industriel**. C'est vrai, et ce n'était pas le principal.

La mesure, pli par pli, sur les chiffres de l'artefact publié :

| pli | apprentissage | test | heures de test **hors** de la plage d'eau de mer apprise | PSI |
|---|---|---|---|---|
| 1 | jan → 25 mars | 26 mars → 18 juin | 73,8 % | 1,989 |
| 2 | jan → 17 juin | 19 juin → 10 sept | **100,0 %** | **3,745** |
| 3 | jan → 10 sept | 11 sept → 5 déc | 5,9 % | 0,580 |
| 4 | jan → 4 déc | 5 déc → 28 fév | **0,0 %** | **0,068** |

La correspondance est **parfaite et monotone**. Le maximum publié — 3,7446, le
chiffre que le rapport cite — tombe sur le seul pli dont la fenêtre de test est
**entièrement** hors de la plage de température d'eau de mer vue à
l'apprentissage. Le minimum tombe sur le seul pli qui n'extrapole pas.

**Ce que cela réfute.** La preuve affichée par la porte attribuait ce chiffre à
« deux excursions de sur-refroidissement » entre les deux moitiés de la période.
Les plis 3 et 4 testent les périodes **les plus tardives**, donc les plus
éloignées de la référence : cette explication prédit qu'ils dérivent le plus.
Ils dérivent le moins, d'un facteur **cinquante-cinq**. Affirmation juste par
ailleurs, écrite à côté de chiffres qui la démentent — le motif du dépôt.

**Ce que cela établit.** Le PSI élevé des premiers plis mesure **l'année
incomplète de la fenêtre d'apprentissage**. La température d'eau de mer est la
seule entrée extérieure à toute boucle de régulation (ADR-002) et elle est
cyclique sur douze mois ; le corpus en couvre quatorze. Un backtest à fenêtre
croissante ne peut donc **pas**, par construction, offrir plus d'un pli
saisonnièrement couvert. C'est une propriété du **plan d'expérience**, pas du
modèle : aucun commit ne la déplacera, et aucun seuil, de quelque domaine qu'il
vienne, n'est interprétable sur un pli qui extrapole.

**Troisième occurrence du même motif.** Un dénominateur qui contient des essais
où rien ne pouvait être mesuré : `judge_eval` comptait des mutations qui ne
mutaient rien (S6-2), `fouling_injection` des fenêtres calmes parce que la ligne
était à l'arrêt (S7-1), ce banc-ci des plis qui extrapolent. Trois bancs de
gouvernance, trois fois la même faute, trois chiffres publiés.

Correction : `seasonal_extrapolation` est mesurée et publiée par pli ; la porte
`derive_de_distribution` ne retient que les plis couverts, et échoue faute de
pli mesurable s'il n'y en a aucun. Elle reste **non bloquante** — mais le motif
change : non plus « seuil non justifié » seulement, mais « la mesure n'est
interprétable que sur un pli sur quatre, et le corpus ne peut pas en offrir
davantage ». La limite est versée dans `limitations`.

### S12-2 — Le PSI publié comptait des cellules vides multipliées par une constante

`_population_stability_index` écrasait les deux distributions à `1e-6` sous le
mot **« lissage »**. Sur des déciles de référence — donc `ref_p = 0,1` par
construction — une seule cellule vide côté observé contribue

```
(1e-6 − 0,1) × ln(1e-6 / 0,1) = 1,1513
```

soit, à elle seule, **plus de quatre fois la borne de 0,25 opposée au total**.
Le maximum publié, 3,7446, vaut 3,25 fois cette contribution.

Et `1e-6` n'est pas une fréquence atteignable : sur les ~1 800 heures d'une
fenêtre de test, la plus petite fréquence non nulle vaut 5,6 × 10⁻⁴. Le plancher
est désormais **la moitié d'un comptage** — la correction de continuité usuelle
— donc rattaché à la taille de l'échantillon au lieu d'être posé.

**Preuve par mutation** (ancienne et nouvelle implémentation comparées) :

| cas | ancien | nouveau | déciles vides |
|---|---|---|---|
| distributions identiques | 0,0047 | 0,0047 | 0 |
| décalage d'un sigma | 0,9165 | 0,9165 | 0 |
| trois déciles bas jamais visités | 0,0104 | 0,0104 | 0 |
| **décalage massif** | **8,0542** | **5,7969** | **4** |

Là où aucune cellule n'est vide, le chiffre est **inchangé** : la correction ne
touche que ce qui était faux. Le nombre de déciles vides est désormais rendu
avec la valeur — un PSI de 3,7 peut signifier une distribution déplacée ou trois
déciles jamais visités, et ce n'est pas le même constat.

### S12-3 — `causal_pipeline_refit` était un littéral, et son test le vérifiait

Le fichier consacre onze lignes à dénoncer que `causalite_temporelle` « était un
littéral `True` : aucune mesure, aucune possibilité d'échec ». Cent-soixante
lignes plus haut, chaque pli publiait :

```python
"causal_pipeline_refit": True,
```

**Le même défaut, un cran plus bas, dans le fichier qui le dénonce.** Et
`test_backtest_temporel_declare_les_limites` l'affirmait —
`assert all(fold["causal_pipeline_refit"] ...)` — c'est-à-dire un test qui
vérifiait une constante et ne pouvait pas échouer.

Le champ mesure désormais les trois choses qui peuvent le démentir : la fin
d'ajustement des **trois** références, celle du détecteur, et le gap calendaire
**obtenu**. `gap_calendar_hours` était de même le paramètre reçu republié comme
un constat ; c'est maintenant la valeur mesurée.

Et surtout : un pli en défaut **n'était agrégé nulle part**. Il ne faisait
échouer aucune porte. Les manquements de pli remontent maintenant à
`causalite_temporelle`, qui est dans `MANDATORY_GATES` **et** `SOFTWARE_GATES`.

### S12-4 — Le balayage de non-causalité excluait un répertoire, et ne le disait pas

Le commentaire annonce « **LE PÉRIMÈTRE COUVRE TOUTE LA CHAÎNE, PAS TROIS
FICHIERS** ». Le code portait `if "governance" not in chemin.parts`, sans un mot
de justification.

La raison réelle est mécanique : le motif contient l'alternative `backfill`,
donc **la ligne de source qui porte le motif contient le mot `backfill`**. Le
balayage se signalait lui-même. Vérifié : les trois seules occurrences dans tout
`src/`, gouvernance comprise, sont aux lignes 149, 155 et 224 de ce fichier —
la docstring qui cite `bfill()` et `shift(-1)` pour expliquer ce qu'elle
cherche, et le littéral du motif.

**Les trois étaient des chaînes de caractères, jamais du code.** Le filtre
`not ligne.lstrip().startswith("#")` ne voyait ni un commentaire de fin de ligne
ni le contenu d'une chaîne. Le balayage blanchit désormais littéraux et
commentaires **par tokenisation**, et l'exclusion tombe : mesuré, le balayage
sur `src/` entier ne rend aucun résultat.

L'exclusion coûtait cher — `sensitivity.py`, `fouling_injection.py` et
`judge_eval.py` produisent des chiffres publiés dans le rapport, et un
`shift(-1)` introduit dans l'un d'eux n'aurait rien déclenché. Un module
illisible est désormais déclaré **suspect**, jamais ignoré.

### S12-5 — Le seuil de 0,25 écrit deux fois, à onze lignes du commentaire qui l'interdit

`alert_rate_limit` avait été nommé en phase 0.7 « pour que la borne n'existe pas
en deux exemplaires ». La porte voisine écrivait `0.25` dans son prédicat **et**
`« pour 0,25 admis »` dans sa preuve. C'est S8-2, dans le fichier qui porte le
principe. Une seule constante, `PSI_LIMIT`, avec sa provenance en commentaire.

### S12-6 — FRONT : deux portes servies sans intitulé, et la réserve coupée à l'écran

Le serveur publie **sept** portes depuis les phases 0.6 et 0.7. `GATE_LABEL`
(`app.js`) en connaissait **cinq**. Les deux nouvelles tombaient sur le repli
`g.gate.replace(/_/g, " ")` et s'affichaient « redondance hors modele » et
« derive de distribution » — en minuscules et **sans accents**, c'est-à-dire
exactement le défaut que le commentaire de `renderValidation`, trois lignes plus
bas, déclare corrigé. **Dix-neuvième occurrence du motif**, toujours dans le
même sens : le code de service porte la version juste, l'affichage la périmée.

Pire, et jamais relevé : `renderValidation` coupait la preuve à **120
caractères**. Les preuves font 300 à 500 caractères depuis qu'elles portent leur
réserve — origine credit-scoring du seuil PSI, caractère algébrique de la
redondance hors modèle, renvoi à ADR-001 — et **toutes ces phrases sont placées
après la mesure, donc toutes tombaient**. L'exploitant lisait le chiffre nu,
sans ce qui le rend défendable. C'est la partie de l'écran qu'un jury lit ligne
à ligne. Le texte est rendu en entier.

**Verrou** (le patron, dixième emploi) —
`test_les_portes_publiees_ont_toutes_un_intitule_a_l_ecran` lit par AST les
littéraux `{"gate": ...}` de `model_validation.py` et les clés de `GATE_LABEL`
dans `app.js`, et exige l'égalité **dans les deux sens** : une porte sans
intitulé est un affichage périmé, un intitulé sans porte est une surface morte.
**Preuve par mutation** : retirer les deux intitulés ajoutés fait apparaître
`derive_de_distribution` et `redondance_hors_modele`, et le test échoue. Vérifié.

### Conséquences documentaires du lot S12 (pour la phase F1)

- Le rapport cite un **PSI de 3,745** comme mesure de dérive. Ce n'en est pas
  une : il faut publier le PSI du pli couvert (**0,068**) et dire que les trois
  autres plis extrapolent.
- Le nombre de portes publiées est **sept**, dont quatre en échec.
- Le tableau des plis gagne trois colonnes : `seasonal_extrapolation`,
  `score_psi_empty_deciles`, `gap_calendar_hours` mesuré.
- `reports/model_validation.json` et `models/e7301_detector.manifest.json`
  portent les **anciens** chiffres : ils doivent être régénérés par
  `scripts/validate_release.py` avant toute relecture du rapport.

### Constat resté OUVERT

`derive_de_distribution` retient les plis à extrapolation **strictement nulle**.
Le pli 3 en est à 5,9 % et porte un PSI de 0,580. Fixer une tolérance non nulle
ferait échouer la porte ; la fixer à zéro la fait passer sur un seul pli. **Je
ne choisis pas un critère en fonction du verdict qu'il produit** : le critère
retenu est le seul qui se justifie sans référence au résultat — une comparaison
de distributions n'a de sens que si l'échantillon comparé est dans le domaine
appris. Mais le fait qu'il ne reste qu'**un pli sur quatre** est une faiblesse
du corpus, pas une force de la porte, et la preuve affichée doit continuer à le
dire aussi crûment.

## Lot S13 — l'authentification (300 lignes lues intégralement)

`src/security/auth.py` · surfaces suivies dans `api/main.py`,
`src/security/registry.py`, `scripts/manage_operators.py`

### S13-1 — SEC-2 : le verrou ne protégeait pas ce que le commentaire croyait protéger

`rotate()` portait ceci :

```python
with self._lock:
    # LE JETON CSRF ETAIT REMPLACE HORS VERROU, donc pendant qu'une requete
    # concurrente pouvait le lire [...] : la rotation faisait echouer des
    # requetes legitimes.
    session.csrf_token = secrets.token_urlsafe(24)
```

**Le diagnostic était juste, le correctif ne le traitait pas.** Déplacer
l'affectation sous le verrou ne change rien, parce que **le lecteur ne prend
jamais le verrou**. Suivi jusqu'à son point d'usage — `api/main.py:299` :

```python
and request.headers.get("X-CSRF-Token") != session.csrf_token
```

La comparaison porte sur l'objet que `validate()` a rendu, verrou déjà relâché.
Un verrou sérialise les écrivains entre eux ; il n'a jamais protégé personne
d'une mutation en place.

**C'est SEC-1 du lot S11, mot pour mot, sur une autre structure.** Le registre
des techniciens mutait `self._operators` en place sous un commentaire qui
expliquait onze lignes plus haut pourquoi il ne fallait pas. Ici le commentaire
est *dans* la méthode fautive. La doctrine établie en S11 est la **publication
atomique** : on ne modifie pas l'objet que d'autres tiennent, on en publie un
nouveau. Elle n'avait pas été portée.

Déroulé, avec `/api/auth/refresh` appelé pendant qu'une écriture est en vol :
la requête A obtient sa session ; la requête B fait tourner le jeton et écrase
`csrf_token` sur l'objet que A tient toujours ; A compare son en-tête — l'ancien
jeton — à la valeur nouvelle.

**Preuve par mutation :**

| | requête légitime en vol |
|---|---|
| mutation en place | **403 Jeton de session invalide** |
| publication atomique | **200 OK** |

**Second défaut fermé au passage.** `rotate()` appelait `self.validate()`, qui
prend puis **relâche** le verrou, avant de le reprendre. Deux rotations
concurrentes du même jeton produisaient donc **deux cookies valides pour une
seule ouverture de session**. `threading.Lock` n'étant pas réentrant, la
validation et la publication tiennent maintenant dans une seule prise de verrou,
via `_valider_sous_verrou`. Mesuré : la seconde rotation du même jeton rend
`None`, un seul cookie survit.

### S13-2 — SEC-3 : la politique de mot de passe écrite trois fois, et mal située

| lieu | écriture |
|---|---|
| `registry.MIN_PASSWORD_LENGTH` | `12` — la constante nommée |
| `auth.hash_password` | `if len(password) < 12:` — **en dur** |
| son message | `« au moins 12 caracteres »` — **en dur, une troisième fois** |
| `registry.py:335` (commentaire) | `# leve si < 12 caracteres` — une quatrième |

`hash_password` est le **dernier verrou** : `registry.add()` et
`registry.set_password()` y passent toutes deux. Et la dépendance interdisait de
faire autrement — `registry` importe `auth`, jamais l'inverse : **le module qui
applique la règle ne possédait pas la valeur.**

Conséquence mesurable : porter la politique à 14 caractères dans `registry`
aurait changé ce que `manage_operators.py` exige et ce que `add()` vérifie, et
laissé `hash_password` accepter 12. **Une politique de mot de passe à moitié
appliquée, sans que rien ne le signale.** Motif d'A-5 et de S8-2.

La constante vit désormais dans `auth`, et ses deux lecteurs l'y importent.
Aucun alias n'est laissé dans `registry` : un nom réexporté sans lecteur est
précisément ce que ce travail retire partout.

### S13-3 — SEC-4 : le seul événement qui signale une attaque taisait sa cible

`LOGIN_RATE_LIMITED` était consigné avec une **chaîne vide** en guise d'adresse.
Le journal d'authentification disait qu'une limite avait été atteinte, jamais
**contre quel compte** — alors que `LOGIN_FAILED` et `LOGIN_SUCCEEDED`
consignent tous deux l'adresse, et que la valeur était dans la portée : seule la
normalisation était écrite dix lignes plus bas. Elle est remontée avant le
verrou. Mesuré : `'vise@example.test'` au lieu de `''`.

### S13-4 — Le test verrouillait la faute d'orthographe (troisième occurrence de S6-4)

`test_mot_de_passe_trop_court_refuse` exigeait `match="12 caracteres"`.
Accentuer « caractères » — ce que la règle du dépôt impose à tout texte affiché
— le faisait échouer. Le contrôle rendait donc la correction typographique
impossible sans le modifier.

La règle est appliquée des deux côtés : le texte **comparé** est dépouillé par
`sans_accents`, le texte **affiché** reste accentué, et le test exige désormais
les deux. La longueur n'y est plus écrite non plus. Trois chaînes de
`manage_operators.py` sont accentuées au passage (**SCR-1**).

### S13-5 — Vérifié, sans correction

- **`_purger`** construit ses listes avant de supprimer : pas de mutation en
  cours d'itération. `defaultdict` crée bien une entrée à la lecture ligne 216,
  mais elle est périmée au bout de 300 s. Conforme à ce que le commentaire dit.
- **`client_key`** vaut `request.client.host`, **pas** un en-tête que le client
  contrôle : la limitation n'est pas contournable par `X-Forwarded-For`.
  Derrière un reverse proxy, en revanche, tous les clients s'effondreraient sur
  une seule clé — sans objet sur un poste mono-worker, à retenir si le
  déploiement change.
- **`_decoy_hash`** : l'égalisation des temps de réponse est fausse **exactement
  une fois par processus** — la première tentative sur une adresse inconnue paie
  deux dérivations, celle du leurre puis la comparaison. La fenêtre est d'un
  unique essai et n'est pas rejouable ; le préchauffage coûterait une
  demi-seconde au démarrage sur un poste qui tourne le plus souvent sans
  authentification. Écart **assumé et écrit dans la docstring**, plutôt que tu.
- **Le filtre `if role in VALID_ROLES`** de `__init__` dégrade silencieusement
  un rôle inconnu en `reader`. Ses deux producteurs le valident déjà bruyamment
  — `registry.load()` depuis le lot S11, `config.validate()` ligne 302 — il
  n'est donc plus atteignable, et reste comme défense en profondeur.

### Conséquence pour la phase F2 (interface)

**`/api/auth/refresh` n'a aucun appelant dans le poste.** `app.js` lit
`S.csrf` une fois (ligne 323) au retour de l'authentification et ne le rafraîchit
jamais. La route est testée et documentée — ce n'est pas une surface morte — mais
si un exploitant la déclenche hors du poste, la page ouverte enverra
indéfiniment un jeton périmé. À trancher en F2 : soit le poste consomme la
rotation, soit la route dit qu'elle est réservée à l'exploitation.

## Lot S14 — le rejeu temps réel (430 lignes lues intégralement)

`src/realtime/replay.py` · surfaces suivies dans `src/pipeline.py`,
`src/models/detector.py`, `src/agents/judge_agent.py`

### S14-1 — La promesse centrale du projet est VRAIE, et n'est pas tenue ici

L'en-tête affirmait :

> « Le simulateur ne voit jamais le futur : à l'instant t, seule la fenêtre
> [début, t] **est transmise** à la détection. C'est cette contrainte qui rend
> la démonstration honnête. »

**Ce module ne transmet aucune fenêtre.** Il appelle `pipeline.analyze_at(ts)`,
qui passe `self.features` — la table **entière** — à ses trois étages :

```python
detection = self.detector.analyze(self.features, timestamp)
decision  = self.agent.analyze(detection, use_llm=use_llm)
verdict   = self.judge.judge(decision, self.features, use_llm=use_llm)
```

**Vérification menée jusqu'au bout, étage par étage** — la propriété tient :

| étage | ce qu'il reçoit | ce qu'il en fait |
|---|---|---|
| `detector.analyze` | table complète | `history = features.loc[:ts]` ✔ |
| `_recent_exceedances` | table complète | `s.index <= ts` ✔ |
| `judge.judge` | table complète | uniquement via `detector.analyze` **au même horodatage** ✔ |

Aucune lecture de l'aval. Mais la propriété tient par **la discipline des
appelés**, et rien dans ce fichier ne l'impose. C'est la situation de S7-2 —
« vrai par accident, pas par construction ». Ajouter à `analyze_at` un
consommateur qui lirait un quantile sur la table entière suffirait à la rompre,
et `replay.py` continuerait de l'affirmer, en tête de fichier, comme ce qui
« rend la démonstration honnête ».

L'en-tête dit maintenant **où la propriété vit réellement**, et le verrou est
comportemental : `test_le_rejeu_ne_lit_jamais_l_aval` rejoue la même analyse sur
la table complète et sur la table tronquée à `t`, et exige un résultat
identique. C'est la technique de `model_validation._causality_audit`, appliquée
à l'analyse plutôt qu'aux features.

**Et `replay.py` n'avait AUCUN test.** Vingt-deux fichiers dans `tests/`, aucun
pour le module qui porte la promesse d'honnêteté du projet. `tests/test_replay.py`
est créé.

### S14-2 — Le cache de faits du Judge ne distinguait pas deux tables

```python
key = decision.timestamp
facts = self._facts_cache.get(key)
```

**La clé ne porte que l'horodatage.** Deux tables de features différentes
interrogées au même instant reçoivent donc les mêmes faits : la seconde se voit
servir ceux de la première.

C'est **mot pour mot S3-4**, corrigé dans `detector._cache_key` — dont le
commentaire porte le raisonnement : « un piège qui ne se déclenche pas encore
reste un piège, d'autant qu'il rendrait un résultat FAUX sans rien signaler ».
**La correction n'avait pas été portée à son jumeau**, et la conséquence y est
plus lourde : `VerifiedFacts` est la vérité *indépendante* du Judge, celle
contre laquelle il met la décision à l'épreuve. Servir des faits issus d'une
autre table revient à valider une décision contre les preuves d'un autre monde.

La clé réutilise `detector._cache_key`, qui porte déjà l'empreinte de contenu —
un prédicat recopié dérive de son original (S8-3).

**Conséquence directe et vérifiable** : le contrôle de causalité de S14-1 aurait
été **vacueux** sans cette correction. Le second appel, sur la table tronquée,
aurait reçu les faits mémoïsés du premier, et la comparaison aurait comparé un
résultat avec lui-même. Les deux corrections se tiennent.

### S14-3 — `limit=0` rejouait le corpus entier

```python
if limit:
    idx = idx[:limit]
```

L'idiome que `src.domain.knowledge.seuil` existe pour abolir — « le repli teste
l'absence, pas la fausseté ». La signature annonce `int | None` : `0` est une
demande légitime de zéro instant, et elle rejouait les dix mille heures. Même
famille que M-1.

`positions` était par ailleurs un jeu d'**horodatages**, alors que le
commentaire de `_instants_incontournables` insiste vingt lignes plus haut sur
cette distinction exacte (« On retient des HORODATAGES, pas des positions »).
Renommé `ordinaires`.

### S14-4 — Un `except Exception` protégeait la garantie contre le silence… en silence

`_instants_incontournables` existe pour une raison écrite dans sa docstring :
sans elle, **le seul instant critique de quatorze mois disparaissait** par une
règle de performance. Sa lecture de seuil portait :

```python
def seuil(alias, cle):
    try:
        return domaine.get(alias).threshold(cle)
    except Exception:
        return None
```

Un alias mal orthographié, un référentiel mal chargé, une erreur d'attribut :
tout devenait « pas de seuil déclaré », donc « aucun instant à protéger », donc
la disparition exacte que la fonction existe pour empêcher — sans une ligne de
journal. Seule l'absence déclarée (`KeyError`, `AttributeError`) est désormais
tolérée.

La fonction s'appelait de surcroît `seuil`, nom de la fonction canonique de
`src.domain.knowledge`. Elle n'est pas importée ici, donc **rien n'était masqué**
— mais c'est le piège exact de M-1, où une locale de ce nom rendait la fonction
importée inaccessible à l'endroit même où le défaut se reproduisait. Le nom est
libéré (`borne_d_alarme`).

### S14-5 — Un arrêt qui n'arrête pas se déclarait arrêté

`stop()` remettait `running` à faux **sans vérifier que le thread avait fini**.
Passé le délai de garde de cinq secondes, l'état annonçait donc un rejeu arrêté
pendant qu'un thread continuait d'émettre — et `start()`, qui ne se protège que
par ce booléen, en aurait lancé un **second**, deux boucles alimentant le même
`ReplayState`. Le cas exige qu'une analyse dépasse cinq secondes ; il n'est pas
atteint aujourd'hui, et il ne signalerait rien s'il l'était. `stop()` journalise
maintenant en `error` et laisse l'état à « en cours ».

### S14-6 — Vérifié, sans correction

- Le délai de temporisation vaut bien `1 / speed` et non `analyze_every / speed`
  (correction antérieure) ; `REPLAY_SPEED=120` et `REPLAY_STEP=3` cités dans le
  commentaire correspondent aux valeurs de `config.py` lignes 121-122. Verrouillé
  par `test_la_vitesse_publiee_est_celle_qui_est_appliquee`.
- L'exemple « une journée de process défile en 0,4 seconde » à 60 h/s est exact.
- `_obligatoires` est calculé sur `pipeline.features` entier alors que `_index`
  peut être tronqué par `start` : les entrées surnuméraires sont simplement
  jamais atteintes, `isin` les filtre. Sans conséquence.
- `_emit` appelle les abonnés **hors** verrou et les lecteurs (`recent`,
  `alerts`, `disagreements`) le prennent : pas de réentrance possible.

## Lot S15 — le service HTTP (1 759 lignes lues intégralement, en deux appels contigus)

`api/main.py` · confronté à `api/static/app.js`, `api/static/twin.js`,
`api/dashboard.html`

**Réserve de méthode, dite franchement.** La consigne impose un appel de lecture
unique. Elle n'était pas satisfaisable ici : 1 759 lignes représentent 26 419
jetons pour un plafond de 25 000. Le fichier a été lu en **deux tranches
contiguës** (1-1415, 1416-1760), sans recouvrement, sans trou, et sans qu'aucune
recherche n'ait guidé le découpage. C'est la seule entorse du travail, elle est
technique, et elle est signalée plutôt que dissimulée.

### S15-1 — FRONT : cinq routes d'exploitation servies, aucune interface

Confrontation route par route des **47 routes servies** aux chemins réellement
appelés par le poste :

| route servie | appelée par le poste |
|---|---|
| `GET /api/workflows` | **non** |
| `GET /api/workflows/{id}` | **non** |
| `POST /api/workflows` | **non** |
| `PATCH /api/workflows/{id}/steps/{step_id}` | **non** |
| `POST /api/workflows/{id}/complete` | **non** |
| `GET /api/workflows/templates` | oui — seule consommée |

Le poste ne sait afficher que les **modèles**. Le panneau de `dashboard.html`
s'intitule « Modèles d'intervention » et se réduit à un sélecteur et une liste
d'étapes. Créer une intervention, faire avancer une étape, la clôturer par
signature : **rien de tout cela n'est atteignable depuis l'interface**, alors
que le serveur porte les cinq routes, le contrôle de rôle, la persistance
SQLite, le verrouillage optimiste (`expected_version`) et les tests.

**Et le commentaire qui documente la correction du jumeau nomme ce qui n'a été
corrigé qu'à moitié.** `dashboard.html` ligne 366 :

> « 849 lignes de code testé, six routes, et aucune interface : le rapport
> annonçait "**le cycle de vie des alarmes ET LES GAMMES DE MAINTENANCE**" que
> rien n'affichait. »

Le cycle de vie des alarmes a reçu son écran. Les gammes de maintenance ont reçu
un lecteur de modèles. Le commentaire qui énonce le principe est écrit trois
pouces au-dessus de la moitié qui l'enfreint — motif du dépôt, dans le fichier
même qui le corrigeait.

### S15-2 — Les autres routes non appelées par le poste : vérifiées une à une

Rule 2 appliquée — aucune absence établie par recherche de nom seule :

| route | consommateur réel | verdict |
|---|---|---|
| `/api/health/ready` | `docker-compose.yml:101`, `ci.yml:200`, runbook | **vivante** |
| `/api/health/live`, `/model`, `/database`, `/version` | runbook, `test_api.py:49-53` | **vivantes** (orchestration) |
| `/api/config` | runbook ligne 32 et 156 | **vivante** |
| `/` | le navigateur | vivante |
| `/api/auth/refresh` | tests seuls — voir S13 | à trancher |
| `/api/auth/audit` | **aucun**, hors liste d'endpoints | **à trancher** |
| `/api/notable` | **aucun**, nulle part | **à trancher** |

`/api/auth/audit` sert le journal d'authentification réservé à l'administrateur
— celui-là même dont S13-3 vient de corriger la cible manquante sur
`LOGIN_RATE_LIMITED`. Il n'a **ni écran, ni entrée de runbook** : le seul journal
qui signale une attaque n'est consultable par aucun chemin documenté. Ce n'est
pas une surface morte à retirer, c'est une surface morte à **brancher**.

`/api/notable` analyse jusqu'à cent instants et n'a aucun lecteur.

### S15-3 — `/api/health` est « degraded » par construction, définitivement

```python
"status": "degraded" if p and not model_promoted else ("ok" if p else "starting")
```

`model_promoted` exige un statut de promotion autorisé. Or la promotion est
**légitimement impossible sur ce corpus** — `labels_gmao` et `validation_externe`
échouent définitivement faute de vérité terrain, et le dépôt le démontre. La
route principale de santé renvoie donc `degraded` à chaque appel, pour toujours.

C'est honnête et c'est inexploitable : `degraded` annonce conventionnellement un
défaut réparable. Le dépôt a déjà tranché cette question deux fois — pour
`redondance_hors_modele` et `derive_de_distribution` — avec la même doctrine :
**une propriété qu'aucun commit ne peut franchir se publie avec son motif, elle
ne se confond pas avec ce qui est réparable.** Le raisonnement n'a pas été porté
ici. À reprendre en F2, avec le rendu de `/api/health` par le poste.

### S15-4 — Deux bancs de gouvernance, un seul protégé

| route | coût | contrôle de rôle |
|---|---|---|
| `/api/judge/evaluation` | élevé | `reliability_engineer`, `administrator` |
| `/api/detection/fouling-bench` | élevé | **aucun** |
| `/api/sensitivity` | élevé | **aucun** |
| `/api/model/validation` | très élevé (backtest) | **aucun** |

**Constat laissé OUVERT, volontairement.** Trancher exige de savoir si la page
Contrôle doit rester lisible par un `reader` : `app.js:2180` appelle
`fouling-bench` au chargement de cette page, donc y poser un contrôle de rôle la
casserait pour les lecteurs. Le choix relève de la politique d'habilitation, pas
de la lecture du code, et il se prend en F2 avec l'écran sous les yeux.

### S15-5 — `/api/health/database` annonce une vérification qui ne décide de rien

La docstring dit « Vérifie **par lecture** les registres locaux ». La lecture a
bien lieu — mais son résultat n'est jamais consulté :

```python
alarm_ok = STATE.get("alarm_store") is not None   # verdict fixé AVANT
if alarm_ok:
    await run_in_threadpool(_alarm_store().list, limit=1)
```

Le verdict publié ne mesure que la **construction** de l'objet. Si la lecture
échoue — base verrouillée, fichier corrompu — l'exception remonte et la route
répond **500**, là où `/api/health/ready` répond proprement 503 avec le détail.
Une sonde de santé qui renvoie 500 au lieu de « indisponible » n'apprend rien à
un orchestrateur.

### S15-6 — Deux écritures de l'identité « Poste local »

Le bloc `{"username": "Poste local", "email": "", "role": "local",
"csrf_token": ""}` est écrit **deux fois**, lignes 503-509 et 521-527, dans deux
routes voisines. Motif S8-2. De même, `alarm_transition` replie sur
`role = "administrator"` quand l'authentification est inactive, tandis que
`_require_roles` traite le même cas par un retour anticipé : une même politique,
deux écritures, dont une seule bougerait si elle changeait.

### Ce qui reste à faire sur ce fichier

Les constats S15-1 à S15-6 sont **établis et non corrigés**. Ils touchent tous
au rendu, donc ils appartiennent à la phase F2, qui se conduit le poste ouvert —
pas à une session de lecture. La lecture de `api/main.py` est en revanche
terminée et complète.

## Lot S16 — corrections serveur des constats de S15

Trois des six constats de S15 se corrigent sans ouvrir le poste : ils sont
entièrement côté serveur, et donc prouvables ici. Les trois autres (interface
des interventions, `/api/auth/audit` et `/api/notable` sans chemin, rôle sur les
bancs) restent pour F2.

### S16-1 — `/api/health/database` : la vérification n'entrait pas dans le verdict

```python
alarm_ok = STATE.get("alarm_store") is not None   # verdict figé AVANT
if alarm_ok:
    await run_in_threadpool(_alarm_store().list, limit=1)   # résultat jeté
```

Le verdict ne mesurait que la **construction** de l'objet au démarrage. La
lecture avait bien lieu, et n'était jamais consultée. Surtout : quand elle
échouait — fichier verrouillé, base corrompue, disque plein, **c'est-à-dire les
seules pannes qu'une sonde de base de données existe pour voir** — l'exception
remontait au gestionnaire générique et la route répondait **500**,
indiscernable d'un bogue applicatif.

`/api/health/ready`, la route voisine, traitait déjà le cas correctement en
répondant 503 avec le détail par registre. Le même contrat est appliqué, avec le
motif nommé.

| | base verrouillée |
|---|---|
| avant | **500** `internal_server_error` |
| après | **503** `{"status": "unavailable", "alarm_store": false, "reasons": {...}}` |

### S16-2 — `/api/health` reste `degraded`, et dit désormais pourquoi il l'est

La promotion est légitimement impossible sur ce corpus, donc `status` vaut
`degraded` **définitivement**.

**La correction tentante a été écartée.** Ramener `status` à l'état du service
et renvoyer la gouvernance vers `ready_for_production` aurait rendu la route
verte — et c'est exactement la faute que la phase 0 a documentée sur
`redondance_features` : « restreindre le critère aurait **remasqué** ce que
l'auteur avait délibérément rendu visible ». `degraded` est une visibilité
voulue, et un jury doit la lire.

Ce qui manquait n'était pas la nuance mais la **raison** : rien ne distinguait
« dégradé par un défaut réparable » de « dégradé par une limite définitive du
corpus ». C'est la distinction que `redondance_hors_modele` et
`derive_de_distribution` publient depuis la phase 0.7, et elle n'avait pas été
portée jusqu'à la sonde de santé. `status_reason` la porte.

### S16-3 — L'identité « Poste local » était écrite deux fois

Le bloc `{"username": "Poste local", "email": "", "role": "local",
"csrf_token": ""}` figurait à l'identique dans `auth_status` et `auth_login`, à
quinze lignes d'écart. Renommer le rôle local, ou changer ce que le poste
affiche faute de session, n'aurait bougé qu'à un endroit. Motif de S8-2 et A-5.

**Verrou** (le patron, onzième emploi) —
`test_l_identite_du_poste_local_n_existe_qu_en_un_exemplaire` compte par AST les
littéraux « Poste local » dans le module.

**Preuve par mutation** :

| | littéraux comptés |
|---|---|
| après correction | **1** — le test passe |
| doublon réintroduit | **2** — le test échoue |

### Reste de S15, pour F2

- l'interface des interventions : cinq routes servies, aucun écran ;
- `/api/auth/audit` : le journal qui signale une attaque n'est atteignable par
  aucun chemin documenté — à **brancher**, pas à retirer ;
- `/api/notable` : aucun lecteur, à trancher ;
- le contrôle de rôle sur les trois bancs de gouvernance non protégés — décision
  d'habilitation, à prendre l'écran sous les yeux.

## Lot S17 — WF-2 et WF-3 tranchés (`src/operations/workflows.py`, 345 lignes lues intégralement)

Les deux constats laissés ouverts par la session précédente sur ce fichier. Ils
se tranchent ensemble : c'est le même vocabulaire, vu par ses deux bouts.

### S17-1 — WF-2 : `CANCELLED` existait partout sauf dans le code qui le pose

Lecture intégrale : le statut d'une intervention n'a que **trois** producteurs.

| producteur | statut écrit |
|---|---|
| `create` | `PLANNED` |
| `update_step` | `BLOCKED` si une étape l'est, sinon `IN_PROGRESS` |
| `complete` | `COMPLETED` |

`CANCELLED` figurait dans `WORKFLOW_STATES`, dans `TERMINAL_STATES` et dans le
`CHECK` du schéma. **Nulle part ailleurs.** C'est la forme exacte de LIN-1
(lot S9) : un vocabulaire qui annonce un cycle de vie plus riche que ce que le
code sait produire.

**Et il n'était pas inoffensif**, pour trois raisons :

1. `TERMINAL_STATES` le contenait, donc les gardes de `update_step` et de
   `complete` — `if workflow["status"] in TERMINAL_STATES` — testaient une
   valeur impossible : **la moitié de chaque garde était morte.**
2. Un lecteur, ou un jury, en déduit qu'un chemin d'annulation existe.
3. Le `CHECK` l'acceptait, si bien qu'une base éditée à la main pouvait porter
   un statut qu'aucun processus légitime n'a produit — et l'intervention se
   retrouvait **définitivement figée**, les deux gardes la refusant, sans
   qu'aucun message ne dise pourquoi. Même structure que le manifeste annonçant
   `rejected`, refusé pour un motif qui laissait croire à un réglage.

**Ce que le retrait rend visible, et qui était masqué.** Une intervention
planifiée puis abandonnée n'a aujourd'hui **aucune représentation** : elle reste
`PLANNED` indéfiniment. C'est une lacune fonctionnelle réelle. Déclarer l'état
sans écrire le chemin la rendait invisible ; la retirer la donne à voir.
Rétablir `CANCELLED` suppose `cancel()`, sa route, son contrôle de rôle et sa
trace au journal — et le verrou le rappellera à quiconque le remettrait seul.

### S17-2 — WF-3 : `WORKFLOW_STATES` était déclaré et lu par personne

Vérifié sur tout le dépôt : **aucun lecteur**. `update_step` valide contre
`STEP_STATES`, jamais contre `WORKFLOW_STATES`. La seule contrainte réellement
appliquée était le littéral SQL du `CHECK`, que rien ne rattachait à la
constante — **deux écritures du même vocabulaire**, libres de diverger sans
bruit. Motif de S8-2.

Les deux `CHECK` sont désormais **dérivés des constantes** par `_contrainte()`.
La constante a enfin un lecteur, et le schéma suit toute modification du
vocabulaire. Mesuré sur une base neuve :

```
CHECK genere    : CHECK(status IN ('BLOCKED','COMPLETED','IN_PROGRESS','PLANNED'))
schema reel     : CHECK(status IN ('BLOCKED','COMPLETED','IN_PROGRESS','PLANNED'))
ecriture directe CANCELLED : REFUSEE par le schema — IntegrityError
```

*Réserve honnête* : `CREATE TABLE IF NOT EXISTS` n'altère pas une table déjà
créée. Les bases existantes conservent l'ancien `CHECK`, plus permissif — sans
conséquence, puisque aucun code n'écrit `CANCELLED`, mais il faut le savoir.

### S17-3 — La docstring de WF-4 annonçait une couverture qu'elle n'avait pas

`test_les_etats_non_nominaux_sont_atteignables` déclarait couvrir « `BLOCKED`,
`NOT_APPLICABLE` et `CANCELLED` ». Il en exerçait **deux**. Il ne pouvait pas
faire autrement : rien ne produisait le troisième. Le test qui existait pour
prouver que trois états déclarés sont atteignables **en affirmait un qui ne
l'était pas** — la faute qu'il était censé interdire, dans son propre texte.

### Verrous (le patron, douzième et treizième emplois)

`test_tout_etat_declare_est_productible` conduit la boutique par son **API
publique** et exige que l'ensemble des statuts observés soit **exactement**
l'ensemble déclaré, dans les deux sens.

**Preuve par mutation :**

| vocabulaire déclaré | orphelins | verdict |
|---|---|---|
| après correction | **aucun** | le test passe |
| `CANCELLED` réintroduit | `['CANCELLED']` | **le test échoue** |

`test_le_schema_derive_son_vocabulaire_des_constantes` vérifie que le `CHECK`
d'une base neuve porte exactement les états déclarés, et pas `CANCELLED`.

### Reste ouvert sur ce module

`update_step` remet `completed_by` et `completed_at` à `None` dès qu'une étape
quitte `COMPLETED` : la ligne courante perd le nom du signataire. La trace
survit dans `workflow_history`, qui conserve l'événement `STEP_COMPLETED` — donc
rien n'est perdu, mais la lecture du détail et celle du journal ne racontent pas
la même histoire. **Signalé, non corrigé** : trancher demande de savoir laquelle
des deux vues le bordereau d'intervention fait foi, et cette question se prend
avec l'écran de F2.

## Lot S18 — J-2 élargi, volet « périmètre » (`tests/test_typographie.py`, 441 lignes lues intégralement)

La phase 0.9 avait recensé deux corrections à porter et n'en avait fermé
aucune : **élargir le lexique**, et **élargir le périmètre**. La première a été
faite au fil des lots (51 mots aujourd'hui). Voici la seconde.

### S18-1 — Le diagnostic : onze contrôles qui n'inspectent que des sorties

Les onze contrôles du fichier lisent tous des **sorties d'exécution** : ils ne
voient une chaîne que si un appel la produit. Une chaîne qui ne traverse aucune
API leur est structurellement invisible — quel que soit le lexique.

Les **messages de refus** sont la famille la plus visible de cet angle mort. Un
`detail` de 401, 403, 404 ou 422 n'apparaît dans **aucune réponse nominale**,
donc dans aucun corpus de test typographique — alors que c'est exactement ce
qu'un exploitant lit quand quelque chose ne va pas. Idem pour la description
OpenAPI, qui ne sort dans aucune réponse métier et qui est la **première page
qu'un jury ouvre** sur `/docs`.

Corrigé : « Authentification **operateur** requise », « **Severite** hors
plage », « **Severites** illisibles », « Au moins une **severite** est
requise », « Horodatage absent des **donnees** », la description du paramètre
`severities`, et l'en-tête OpenAPI (« Rejeu historique **accelere** […]
**Detection** hybride **regles** applicatives + **modele** statistique »).

### S18-2 — Le verrou, et pourquoi il lit le source

`test_les_textes_de_refus_de_l_api_sont_accentues` lit `api/main.py` **par
AST** au lieu d'appeler une route. C'est le patron du dépôt appliqué à la
typographie. Trois familles sont écartées, chacune pour une raison qui lui est
propre et écrite dans le code :

| écarté | motif |
|---|---|
| docstrings et commentaires | l'en-tête du fichier les exclut depuis l'origine — ils s'adressent au relecteur |
| arguments de `logger.*` | le journal serveur n'est pas une surface d'exploitation |
| chaînes de plus de 400 caractères | ce sont les **prompts** des agents : les accentuer modifierait l'entrée d'un modèle de langage, donc son comportement — une modification de fond déguisée en correction de forme |

**Preuve par mutation :**

| | corpus inspecté | fautes |
|---|---|---|
| après correction | **61 chaînes** | **aucune** — le test passe |
| « opérateur » remuté en « operateur » | 61 | `['operateur']` — **le test échoue** |

### S18-3 — RÉTRACTATION EN COURS DE LOT : `knowledge.py` n'est pas une surface d'affichage

Le balayage désignait six chaînes de `src/domain/knowledge.py` — « Echangeur a
faisceau tubulaire », « PARTIELLEMENT OBSERVES », « criticite », « preventif ».
J'allais les corriger.

Vérification avant édition : elles appartiennent à `briefing_equipment()` et
`briefing_*`, dont la docstring dit **« injectée dans les prompts des agents »**.
Ce sont des instructions à un modèle de langage — « ne jamais les
diagnostiquer » — et elles ne sont affichées nulle part. Les accentuer aurait
modifié l'entrée des deux agents sans qu'aucun test ne le signale, sous
l'apparence d'une correction typographique.

C'est la règle 2 qui a payé : suivre la chaîne jusqu'à son point de rendu avant
de conclure. Le motif du dépôt aurait été reproduit **par l'audit**, pour la
troisième fois.

### S18-4 — Ce que la mesure établit, et qui reste ouvert

Balayage complet de `src/`, `scripts/` et `api/`, exclusions appliquées :
**49 chaînes** portant au moins un mot du lexique sans son accent, réparties en
familles qui ne relèvent pas du même traitement :

| famille | volume | verdict |
|---|---|---|
| refus et description de l'API | 7 | **corrigées** (S18-1) |
| prompts des agents (`knowledge`, `detection_agent`, `judge_agent`) | ~8 | **hors périmètre** — modifier une entrée de modèle |
| libellés et descriptions des pièges du Judge (`judge_eval`) | 14 | **à instruire** : `by_trap` est servi et rendu par `renderBench`, mais certaines chaînes sont des charges volontairement fautives et ne doivent pas être touchées |
| sorties console des `__main__` et des scripts (SCR-1) | ~10 | à trancher : lues par un opérateur en ligne de commande, jamais par le poste |
| messages d'exception internes (`Modele introuvable`, `Periode de reference trop courte`) | ~10 | à trancher : remontent en 500 ou au démarrage |

**Ces quatre dernières familles ne se tranchent pas au balayage.** Chacune exige
de suivre la chaîne jusqu'à son point de rendu, et c'est précisément ce que la
famille « prompts » vient de démontrer. Le constat J-2 passe donc d'une note
vague à une **liste comptée et catégorisée** ; il reste ouvert sur quatre
familles, avec le critère de décision écrit.

## Lot S19 — M-3 rouvert, revérifié et clos

Le dernier constat que le brief laissait explicitement à rouvrir.

### S19-1 — Le constat tient, mot pour mot, à l'endroit annoncé

Vérifié sur le code courant : `_MODE_BY_THRESHOLD` portait toujours quatre
entrées, dont **trois avec un tag et un seuil vides**.

```python
"conc_min":      ("FAISCEAU_CORROSION", "C_ACID_1100", "alarm_low"),
"conc_drop_24h": ("FAISCEAU_FUITE",  "", "")
"d_conc":        ("FAISCEAU_FUITE",  "", "")
"flow_per_load": ("CALANDRE_FUITE",  "", "")
```

`_mode_for_feature` sort sur `if not tag_name: return None` : **trois entrées
sur quatre rendaient invariablement `None`**. La table paraissait rattacher
quatre grandeurs à trois modes de défaillance, et n'en rattachait qu'une —
exactement la « couverture illusoire » que le commentaire condamne **quinze
lignes plus haut**, à propos de la table d'à côté. La correction avait été
portée à `_MODE_BY_RESIDUAL` et pas à sa jumelle.

### S19-2 — Le comportement était juste ; c'est la forme qui mentait

C'est ce qui distingue M-3 de LIN-1 et de WF-2, et ce qui interdisait la
correction évidente. Les trois grandeurs sont des **variations**, et la règle
déterministe correspondante porte déjà son seuil de matérialité : le modèle
statistique ne doit pas la doubler. C'est une décision, motivée sur huit lignes
au-dessus de la table.

**Les supprimer aurait effacé cette décision** et laissé croire à un oubli — un
futur relecteur les aurait rattachées, et le modèle se serait mis à accuser une
pièce là où la règle tranche déjà. C'est l'inverse de WF-2, où l'état déclaré
n'était soutenu par aucune intention.

Les deux natures sont donc **séparées**, comme les portes de la phase 0.7 et les
plis de S12 : `_MODE_BY_THRESHOLD` ne contient plus que ce qui peut réellement
accuser, et `_FEATURES_SANS_ACCUSATION` déclare les trois autres pour ce
qu'elles sont. `_mode_for_feature` teste l'ensemble nommé au lieu d'une chaîne
vide.

### S19-3 — Le test verrouillait l'appartenance, pas l'atteignabilité

Le journal l'avait déjà noté :
`test_le_rattachement_ne_cite_que_des_features_du_modele` vérifiait que chaque
entrée porte une grandeur de `MODEL_FEATURES` — **pas qu'elle puisse produire un
rattachement**. Une entrée à tag vide franchissait donc le contrôle.

`test_toute_entree_de_rattachement_peut_reellement_accuser` exige les quatre
propriétés qui manquaient :

1. aucune entrée à tag ou seuil vide ;
2. chaque seuil cité **existe** dans le référentiel ;
3. chaque mode cité **existe** dans l'AMDEC ;
4. les deux ensembles sont **disjoints** — une grandeur ne peut pas à la fois
   accuser et ne pas accuser.

Le test d'origine est étendu à `_FEATURES_SANS_ACCUSATION` : le nouvel ensemble
est soumis à la même exigence d'appartenance à `MODEL_FEATURES`.

**Preuve par mutation :**

| `_MODE_BY_THRESHOLD` | entrées | inertes | verdict |
|---|---|---|---|
| avant | 4 | `conc_drop_24h`, `d_conc`, `flow_per_load` | **le test échoue** |
| après | 1 | aucune | le test passe |

### Où en sont les constats ouverts du brief

| constat | état |
|---|---|
| seuil PSI 0,25 | **tranché** — S12-1, par la mesure |
| WF-2 / WF-3 | **tranchés** — S17 |
| M-3 | **clos** — ce lot |
| libellés des huit contrôles du Judge | lexique complété; **périmètre** mesuré et catégorisé en S18-4, quatre familles restent à instruire |

## Lot S20 — Ce que le dépôt versionne réellement (phase F3, volet sécurité)

Vérifié **avant** toute autre chose, parce que c'est le seul point de ce travail
dont une erreur serait irréversible : ce qui est poussé une fois l'est pour
toujours.

### S20-1 — Les secrets : sains, et vérifiés sur l'historique entier

Balayage des **3 101 objets** de `git rev-list --all --objects` :

| fichier | suivi aujourd'hui | a-t-il existé dans l'historique |
|---|---|---|
| `.env` | non ✔ | **jamais** ✔ |
| `data/runtime/operators.json` | non ✔ | **jamais** ✔ |
| toute clé (`*.key`, `*.pem`, `id_rsa`, `credential*`) | non ✔ | **aucune** ✔ |

C'est le point le plus important de la section sécurité, et il est propre. Le
`.gitignore` porte d'ailleurs déjà la correction d'un piège subtil :
`data/runtime/` excluait le répertoire et non son contenu, ce qui rendait la
négation `!data/runtime/.gitkeep` **inerte** — Git ne descend jamais dans un
répertoire exclu.

La révocation des deux clés Gemini côté Google reste à faire : elles ont été
exposées hors du dépôt, et rien ici ne peut le constater.

### S20-2 — La contrainte la plus lourde du projet n'était écrite nulle part

`data/raw/DATA.xlsx` est versionné **délibérément** — le `.gitignore` le dit et
le justifie : « il fait partie du livrable et permet à quiconque clone le dépôt
de reproduire tous les résultats ». C'est un choix défendable.

Mais ce fichier porte **quatorze mois d'exploitation réelle** d'une installation
d'OCP Group. Le choix n'est acceptable qu'à une condition : **le dépôt distant
doit rester privé.**

**Cette condition ne figurait dans aucun des 162 fichiers versionnés.** Le
README s'ouvre au contraire sur « OCP Group », « 10 180 horodatages DCS » et
« AMDEC OCP du 23/09/2019 », sans un mot sur la confidentialité. Le commentaire
du `.gitignore` justifiait le versionnement **sans jamais énoncer sa
contrepartie**.

C'est la doctrine de ce dépôt appliquée à lui-même : *une décision qui n'est pas
écrite est une décision perdue*. À une différence près, et elle est décisive —
les dix-neuf lots précédents corrigeaient des défauts rattrapables. **Celui-ci
ne l'est pas** : publié une fois, un fork ou un miroir suffit.

Corrigé aux deux endroits : une section « Ce dépôt ne peut pas être public » en
tête de README, et la contrepartie écrite dans le commentaire du `.gitignore`
qui portait la justification.

### S20-3 — 93 % de l'historique est un `node_modules` mort

| famille | objets | part |
|---|---|---|
| `frontend/node_modules/` | **2 887** | 93,1 % |
| `frontend/` (total) | 2 890 | 93,2 % |
| tout le reste du projet | 211 | 6,8 % |

`frontend/` **n'existe plus** dans l'arbre de travail — le poste est
`api/static/` — et n'est plus suivi. Mais l'historique le porte intégralement,
et un `push` le transfère.

L'arbre courant est en revanche propre : **162 fichiers suivis**, aucun
`alembic`, aucun `frontend/`, aucun `dashboard/` — la phase A avait fait ce
travail sur l'arbre, pas sur l'historique.

**Non corrigé, et délibérément.** Réécrire l'historique (`git filter-repo`,
BFG) est une opération destructive qui invalide le tag `v3.0.0` et toute copie
existante. Elle ne se fait pas depuis une session d'audit, et elle ne se fait
pas sans que le propriétaire ait décidé s'il veut un dépôt léger ou un
historique intact. Les deux options se défendent ; la mesure est publiée pour
que le choix soit informé.

### S20-4 — DÉCISION DU PROPRIÉTAIRE : le dépôt ne sera pas publié

Ce lot s'était conclu sur quatre actions à mener avant un `push`. **Le
propriétaire a tranché : le projet ne part pas sur GitHub.** Deux des quatre
tombent, et il faut le dire ici plutôt que de laisser une consigne périmée —
c'est le défaut que ce travail corrige depuis vingt lots.

| action | état |
|---|---|
| visibilité du dépôt distant | **sans objet** — aucun distant, `git remote -v` vide |
| historique `frontend/` (S20-3) | **sans objet** — 2 887 objets morts dans un `.git` local, sans conséquence |
| clés Gemini | **non révoquées, décision assumée.** Le risque est borné et n'est pas celui du dépôt : une clé Gemini ne donne accès ni au code ni à `DATA.xlsx`, seulement au quota et à la facturation du compte Google. Vérifier qu'aucune facturation n'est attachée au projet neutralise le seul risque réel |
| régénérer les artefacts | **reste à faire** — seule action ouverte |

**Ce que la décision de ne pas publier change au dossier.** Le constat S20-2 — la
contrainte de confidentialité écrite nulle part — n'est pas annulé pour autant.
Il devient même plus utile : la section du README documente désormais *pourquoi*
le dépôt ne peut pas être publié, ce qui protège la décision contre un futur
relecteur qui, ne voyant aucune raison écrite, la croirait arbitraire. Une
décision non écrite est une décision perdue, y compris quand elle consiste à ne
rien faire.

**Risque résiduel, hors périmètre d'audit** : le dépôt n'existe qu'en un
exemplaire, sur un poste. Une sauvegarde hors ligne relève de la conservation du
mémoire, pas de la sécurité des données — mais l'absence de distant la rend
nécessaire.

## Lot S21 — Les artefacts régénérés : une correction confirmée, une affirmation à retirer

`scripts/validate_release.py` a été relancé après S12. `reports/model_validation.json`
et le manifeste portent désormais les chiffres du code corrigé. Suite complète
verte.

### S21-1 — S12-2 confirmé au dix-millième

Le plancher des cellules vides prédisait un effet exact et chiffrable. Mesuré
sur l'artefact réel :

| | valeur |
|---|---|
| pli 2 — `n_test` | 1 837, et **1 décile vide** — le seul des quatre plis |
| contribution d'une cellule vide, plancher `1e-6` | 1,1513 |
| contribution d'une cellule vide, plancher `0,5/n` | 0,5890 |
| écart **prédit** | **0,5622** |
| écart **mesuré** — 3,7446 → 3,1826 | **0,5620** |

**Prédiction confirmée à 0,0002 près.** Le PSI publié contenait bien, pour
0,56 point sur 3,74, une constante arbitraire et non une distance entre
distributions. Et l'instrumentation ajoutée le dit maintenant : un décile vide,
sur ce pli, et zéro sur les trois autres.

### S21-2 — RETRACTATION : « un pli sur quatre est couvert » était faux, il n'y en a AUCUN

Le lot S12 annonçait, sur la foi d'un calcul mené hors du dépôt, que le pli 4
n'extrapolait pas et fournissait la seule mesure de dérive interprétable
(PSI 0,068). **C'est faux.**

| pli | annoncé en S12 | mesuré par le code |
|---|---|---|
| 1 | 73,8 % | 76,5 % |
| 2 | 100,0 % | 100,0 % |
| 3 | 5,9 % | 5,2 % |
| 4 | **0,0 %** | **12,8 %** |

**Cause de l'erreur, et elle est instructive.** Mon calcul comparait les
températures d'eau de mer sur le CALENDRIER — `pd.date_range(début, fin, 'h')`.
Le code compare `train.index` et `test.index`, c'est-à-dire la **matrice du
modèle** : heures de marche établie uniquement, `dropna` appliqué. La plage
apprise n'est donc pas celle du calendrier, c'est celle des heures où la ligne
tournait réellement.

Le pli 4 apprend de janvier à début décembre, ce qui couvre le calendrier
presque entier — mais si la ligne était à l'arrêt pendant les journées les plus
froides de janvier-février 2024, ces valeurs d'eau de mer **n'ont jamais été
apprises**. Sa fenêtre de test, qui va jusqu'au 28 février, y redescend :
12,8 % de ses heures sont hors de la plage vue.

**Et c'est le code qui a raison.** Le modèle n'a pas appris sur ces valeurs,
donc les scorer est bien une extrapolation, que le calendrier les ait contenues
ou non. La plage apprise est une propriété du **régime de marche de l'atelier**,
pas de l'année. Ma mesure hors dépôt était plus grossière que l'instrument que
je venais d'écrire.

### S21-3 — Conséquence : la porte dit « aucun pli mesurable », et je ne l'assouplis pas

`max_score_psi_seasonally_covered` vaut `None`, `n_seasonally_covered_folds`
vaut **0**, et `derive_de_distribution` échoue en publiant « aucun des 4 plis
n'est mesurable ».

La tentation est évidente : poser une tolérance — 5 %, 15 % — pour qu'au moins
un pli qualifie. **Elle est refusée**, et le motif est écrit noir sur blanc dans
S12 : « je ne choisis pas un critère en fonction du verdict qu'il produit ».
Introduire la tolérance maintenant, parce que le critère strict donne une
réponse gênante, serait exactement la faute que la phase 0 a documentée sur
`redondance_features`.

Le résultat est donc plus dur que ce que j'annonçais, et il est plus vrai :
**sur ce corpus, aucune fenêtre de test n'est saisonnièrement couverte par son
apprentissage.** Un backtest à fenêtre croissante sur quatorze mois, pour un
cycle d'eau de mer de douze, avec une ligne qui s'arrête, ne peut pas en
produire. La porte reste publiée et non bloquante — ce qui est son statut depuis
la phase 0.7 — et la promotion reste refusée pour les deux seules raisons qui
valent.

### S21-4 — Les deux autres corrections de S12, confirmées

| champ | avant | après |
|---|---|---|
| `causal_pipeline_refit` | littéral `True` | **mesuré** — vrai sur les 4 plis, références et détecteur bornés à `train_end` |
| `gap_calendar_hours` (par pli) | le paramètre reçu, `24` | **mesuré**, `25,0` h — l'écart réel de `TimeSeriesSplit` |

Les sept portes sont publiées, trois franchies, quatre en échec avec leur
preuve. `causalite_temporelle` passe, balayage tokenisé compris, `governance`
désormais dans le périmètre.

### Ce que F1 devra écrire, et qui a changé depuis S12

- le PSI maximal n'est plus 3,7446 mais **3,1826**, et la différence a une cause
  nommée ;
- le rapport ne peut pas citer « 0,068 comme mesure de dérive » : **aucun pli
  n'est interprétable** ;
- la limite à publier n'est pas « un seul pli couvert » mais « aucun », et la
  raison est physique, pas méthodologique.

## Lot S22 — le registre d'alarmes (561 lignes lues intégralement)

`src/operations/alarms.py`

### S22-1 — AL-1, première moitié : réellement close, vérifiée jusqu'au producteur

Le constat portait sur `_trigger`, qui identifiait l'alarme par `findings[0]`,
c'est-à-dire par l'ordre d'écriture des règles — `_rule_sensor_health` passant
en premier, un capteur qui dérive volait son identité à un percement de tube.

**Corrigé, et pas seulement en apparence.** `_trigger` lit
`analysis.decision.lead_finding`, et ce champ est genuinement peuplé :
`detection_agent.py:316` écrit `lead_finding=lead.code` avec
`lead = max(actionable, key=_priorite)`. Le barème est donc **réutilisé**, pas
recopié — ce que le correctif annonçait. Vérifié du consommateur au producteur.

### S22-2 — AL-2 : un désaccord du Judge résolvait une alarme critique

```python
accepted_alarm = severity in {"WARNING", "CRITICAL"} and verdict.agreement
```

La négation de ce test partait vers `_return_matching_to_normal` dans **deux cas
de natures opposées** :

| cas | ce qui se passait |
|---|---|
| la condition a cessé | résolution — légitime |
| la condition **persiste**, le Judge a rejeté la décision | **résolution — absurde** |

**Preuve par mutation**, sur le registre réel :

| | statut de l'alarme |
|---|---|
| t1 — CRITICAL, Judge d'accord | ACTIVE |
| t2 — CRITICAL, **Judge en désaccord**, même constatation | **RETURNED_NORMAL** ✘ |
| t2 après correction | **ACTIVE** ✔ |
| t3 — condition cessée | RETURNED_NORMAL ✔ — la voie légitime est intacte |

C'est précisément ce que l'en-tête du module interdit — « le registre ne déduit
jamais qu'une alarme a disparu parce qu'une **autre** analyse est normale » — en
pire : il le déduisait d'un désaccord de gouvernance. Le Judge conteste la
**rédaction** d'un diagnostic; il ne dit rien du procédé. Les deux questions sont
désormais séparées : la présence de la condition se lit sur la sévérité, l'accord
du Judge décide seulement si l'alarme mérite d'être **levée**. Une condition
présente et contestée ne fait rien bouger, ni dans un sens ni dans l'autre.

### S22-3 — AL-3 : une justification fausse masquait la seconde moitié d'AL-1

Le repli de `_trigger` portait :

> « L'ordre des règles y est sans conséquence : la clé recherchée est celle
> **déjà enregistrée**. »

**C'est l'inverse.** `observe` calcule `key = self._key(analysis)` sur l'analyse
**courante**, puis cherche `WHERE alarm_key=?` avec cette clé. L'ordre des règles
décide donc exactement quelle alarme sera retrouvée.

**Mesuré, sur trois instants :**

| | |
|---|---|
| t1 — `CONC_DROP_SEVERE` dominant | alarme `::CONC_DROP_SEVERE` **ACTIVE** |
| t2 — nominal, `SENSOR_FAULT` en INFO | clé cherchée `::SENSOR_FAULT` → aucune ligne, **alarme intacte** |
| t3 — plus aucune constatation | `_key` rend `None`, `observe` sort → **alarme intacte** |
| clôture manuelle | **REFUSÉE** — `close` n'est permis que depuis `RETURNED_NORMAL` |

**L'alarme ne peut ni se résoudre ni être close.** Elle reste ACTIVE
indéfiniment, et le registre ISA-18.2 n'accumule que des ouvertures. La voie de
résolution ne fonctionne que pour une règle qui réémet le **même code** à une
sévérité plus basse — cas rare.

Et le principe qui produit cela est énoncé comme une prudence dans l'en-tête :
« une analyse sans constatation ne possède pas la preuve permettant de résoudre
une alarme, elle est donc volontairement sans effet ». Or l'absence de
constatation **est** le cas nominal le plus fréquent. Une règle présentée comme
prudente garantit ici l'inverse de la prudence.

**NON CORRIGÉ, ET C'EST UNE DÉCISION.** Balayer les alarmes ouvertes dont la
condition n'est plus observée suppose trois arbitrages de sécurité :

1. une analyse sans constatation vaut-elle preuve de retour à la normale —
   l'en-tête dit non, et c'est ce non qui bloque tout ;
2. que fait-on d'une **ligne à l'arrêt** ? Le balayage y viderait le registre,
   c'est le piège de S7-1 ;
3. comment un capteur en défaut interagit-il avec le balayage ?

Ces trois décisions engagent la sécurité d'exploitation et modifient un test
existant (`test_alarm_store.py:160`, qui verrouille le comportement actuel). Les
prendre en fin de session, sans pouvoir jouer la suite complète, serait fermer au
jugé. **AL-1 est donc close sur sa première moitié, et sa seconde moitié est
reformulée en AL-3 avec sa mesure et ses trois questions.**

## Lot S23 — le poste de surveillance (2 407 lignes lues intégralement)

`api/static/app.js`, lu en deux tranches contiguës (1-1200, 1201-2407) — même
réserve technique qu'`api/main.py`, le fichier dépasse le plafond d'un appel.

Le fichier est de très bonne facture : la charte est résolue depuis le CSS, les
codes machine sont traduits par sept tables de libellés, la zone morte de
l'indicateur de tendance est calculée sur la dispersion résiduelle, et
l'accessibilité clavier suit WAI-ARIA. Les quatre constats ci-dessous portent
sur des **écarts entre ce que l'écran affirme et ce que le serveur fait**.

### S23-1 — « Session expirée » annoncé dans trois situations, dont deux fausses

`showGate()` posait invariablement `setLink("down", "Session expirée — écran
figé")`. Elle est appelée depuis trois endroits :

| appelant | situation réelle | message affiché |
|---|---|---|
| `api()`, sur un 401 | session expirée | juste ✔ |
| `boot()`, accès protégé, jamais identifié | **aucune session n'a existé** | « Session expirée » ✘ |
| `boot()`, poste local sans authentification | **il n'existe pas de session** | « Session expirée » + « Prise de quart » ✘ |

Le commentaire de cette même fonction dénonce le message précédent — « le
bandeau annonçait *Service injoignable*. C'est FAUX […] un diagnostic erroné
envoie l'exploitant vérifier le réseau au lieu de se reconnecter » — et la
correction avait remplacé un message faux par un autre message faux, dans deux
cas sur trois. **Corrigé** : le motif et l'état de liaison sont des paramètres,
et `down` n'est plus posé que lorsque l'écran est réellement figé sur des
données périmées.

### S23-2 — Les huit pondérations du contrôleur sont écrites en dur à l'écran

Le fichier s'ouvre sur trois principes. Le deuxième :

> « Aucun chiffre affiché n'est en dur. La version précédente affichait
> *seuil 0,487* et *R² 0,968* dans le HTML alors que les valeurs réelles
> étaient 0,973. »

`CHECKS`, ligne 1 563, écrit les huit pondérations en clair — « 22 % », « 16 % »,
« 14 % »… — dans le panneau qui explique **à un jury** comment la note globale
du contrôleur est composée. Rien ne les rattache à `JudgeVerifier.WEIGHTS`, qui
est la seule source appliquée.

**Elles coïncident aujourd'hui** — vérifié, les huit valeurs correspondent. Le
défaut est donc latent, et c'est le traitement retenu pour la clé du cache de
scores en S3-4 : *un piège qui ne se déclenche pas encore reste un piège,
d'autant qu'il rendrait un résultat faux sans rien signaler*.

**Verrou** (le patron, quatorzième emploi) —
`test_les_poids_affiches_sont_ceux_que_le_juge_applique` lit `CHECKS` dans
`app.js` et `WEIGHTS` dans `judge_agent.py`, et exige l'égalité.

**Preuve par mutation** : porter V1 à 0,17 et V5 à 0,20 côté serveur fait
échouer le test. Vérifié.

### S23-3 — La prise de quart déclarative ne trace rien

Sur un poste sans authentification, l'écran d'accueil affiche :

> « Renseignez votre adresse pour **tracer la prise de quart** ; aucun mot de
> passe ne peut être vérifié. »

La deuxième moitié de la phrase est honnête. La première ne l'est pas :

```js
S.shiftOperator = email;      // ligne 424
```

Vérifié sur tout le fichier et sur `dashboard.html` : **`shiftOperator` est
écrit une fois et lu nulle part.** Aucun appel serveur, aucune entrée de
journal, rien qui survive à un rechargement de page. L'écran promet une
traçabilité qui n'existe pas — sur un projet dont le journal d'actions est
l'argument central.

**Non corrigé** : le rendre vrai suppose une décision — soit retirer la promesse
du texte, soit ouvrir une route qui consigne la prise de quart, ce qui pose la
question de ce que vaut une identité non authentifiée dans un journal
d'exploitation. Elle rejoint le chantier de S15-1.

### S23-4 — L'écran doit deviner un indicateur à partir de son libellé français

```js
const figure = (kpi?.figures || []).find((f) => f.label.includes("signalement"));
```

`renderFlagRate` cherche l'indicateur de taux de signalement **par sous-chaîne
de son intitulé affiché**. Ce n'est pas de la négligence : la dataclass `Figure`
de `src/analytics/kpi.py` ne porte **aucun identifiant stable** — `label`,
`value`, `unit`, `note`, `evidence_level`, et c'est tout.

Le front n'a donc pas le choix : il doit apparier sur de la prose destinée à un
humain. Or le lot S10 a réécrit ces libellés, et toute réécriture future casse
le rattachement **en silence** — le bandeau se vide sans qu'aucune erreur ne
soit levée.

**Non corrigé** : la correction est côté serveur — ajouter un `key` stable à
`Figure` et le publier — et touche la forme de `/api/kpi`. À faire avec S15-1.

### S23-5 — Vérifié, sans constat

- `twinStateFrom` lit `finding_map` servi par `/api/topology` : aucune règle
  métier réimplémentée, un code inconnu n'allume rien (confirme S2-6).
- `OBSERVABILITE` porte bien les trois états et se replie sur le booléen
  seulement si `observabilite` est absent — la correction de S2-5 est en place.
- `GATE_LABEL` et le rendu intégral des preuves : corrections de S12-6 en place.
- `renderCoverage` tronque la liste des angles morts à **cinq**, sans « et N
  autres ». Le référentiel en déclare huit au total, tous états confondus : la
  troncature est silencieuse par construction, même si elle ne mord pas
  forcément aujourd'hui. Signalé, non corrigé.
- `generated_from.gap_calendar_hours` affiché par `renderValidation` reste le
  **paramètre** (24 h), alors que les plis publient désormais la valeur mesurée
  (25,0 h) depuis S12-3. Écart d'une heure, sans conséquence de lecture, mais
  c'est la même distinction « affirmé / constaté ».

### S23-6 — ERREUR DE L'AUDIT : un nom inféré au lieu d'être lu

`test_les_poids_affiches_sont_ceux_que_le_juge_applique` importait
`JudgeVerifier`. **Cette classe n'existe pas.** La classe qui porte `WEIGHTS`
s'appelle `VerificationLayer`.

Je l'avais déduite de `self.verifier.run(decision, facts)`, lu au site d'appel
dans `judge()` — c'est-à-dire que j'ai construit un nom à partir d'un nom
d'attribut au lieu de suivre la référence jusqu'à sa définition. C'est la
**règle 2 de la méthode**, appliquée à mon propre code et enfreinte : *aucune
recherche n'établit un nom, il faut suivre la donnée jusqu'à son point de
définition*.

Aggravant : le nom correct figurait **435 lignes plus haut dans le fichier même
que j'étais en train de compléter** —
`test_poids_des_controles_somment_a_un` importe `VerificationLayer` depuis
toujours. Je n'avais pas lu `test_agents_judge.py` intégralement, et c'est
précisément le trou de couverture que l'inventaire du lot précédent a chiffré :
21 fichiers de tests sur 23 jamais lus.

Corrigé. Le test mesure bien ce qu'il annonce — vérifié hors dépôt, les huit
poids coïncident et leur somme vaut 1,0.

**Ce que cela confirme** : la lecture des tests n'est pas une formalité de fin de
liste. C'est la couche où quatre défauts de ce travail ont été trouvés (S6-4,
S13-4, S19-3, WF-4), et celle où j'ai commis le mien.

## Lot S24 — la couche de vérification (835 lignes lues intégralement)

`tests/test_agents_judge.py` (699) · `tests/conftest.py` (136)

Lot ouvert par une **erreur de l'audit** : S23-6, un nom de classe inféré au
lieu d'être lu, dans le fichier même que je complétais. Le propriétaire l'a
relevé, et il a raison — c'est la démonstration de sa consigne. Ce lot est donc
la lecture qui aurait dû précéder.

### S24-1 — Quatre contrôles pouvaient passer sans rien vérifier

Le fichier se présente comme « le cœur de la garantie apportée par le projet ».
Quatre de ses tests portent leur assertion **à l'intérieur d'une boucle ou
d'une condition**, sans jamais vérifier qu'un cas a été examiné :

| test | condition | si elle n'est jamais vraie |
|---|---|---|
| `..._action_avec_arret_mentionne_la_consignation` | `if requires_shutdown` | passe, **zéro assertion** |
| `..._un_defaut_de_mesure_ne_domine_jamais...` | `if dominant is not None and len(severites) == 1` | passe, zéro assertion |
| `..._la_tache_preventive_citee_est_la_plus_frequente` | `if len(refs) < 2: continue` | passe, zéro assertion |
| `..._un_seul_bareme_de_confiance_existe` | boucle sur `notable_timestamps(15)` | passe si la liste est vide |

**Et le dépôt porte déjà la doctrine, écrite deux fois.**
`test_typographie._exiger` impose un corpus minimal avec ce motif : « un
contrôle qui réussit d'autant plus sûrement qu'il ne lit rien ne contrôle
rien ». Et **ce fichier l'applique lui-même trois fois** —
`test_une_action_en_marche_conforme...` et
`test_judge_detecte_une_severite_sous_estimee` par `pytest.skip`,
`test_aucune_decision_native_ne_declenche_la_sur_confiance` par
`assert instants`. Sept tests exposés au même risque, trois protégés, quatre
non. Le motif du dépôt, dans la couche censée l'empêcher.

Corrigé : chacun compte ce qu'il a réellement mis à l'épreuve, et **déclare**
par `skip` quand le corpus ne lui offre rien — plutôt que de rendre un vert
silencieux.

### S24-2 — Et l'une des deux moitiés de ce test était morte

```python
txt = d.recommended_action.description.lower()
assert "consign" in txt or "arret" in txt
```

Le texte comparé est **accentué** depuis S4-2 : les actions écrivent « arrêt ».
`"arret" in txt` était donc **toujours faux**, et seule la première moitié de la
disjonction pouvait valoir. Une action qui dirait « Arrêter la ligne » sans le
mot « consignation » serait passée.

C'est S6-4 une nouvelle fois — comparer une chaîne dépouillée à un texte
accentué — et le fichier importe `sans_accents` depuis sa vingtième ligne. Il ne
s'en servait que dans un test sur onze. Le texte comparé est désormais dépouillé.

### S24-3 — Deux tests mutent une fixture de session sans la restituer

`pipeline` est de portée **session**. `test_le_banc_ne_pollue_pas_l_auto_surveillance`
remplaçait l'auditeur du Judge :

```python
pipeline.judge.auditor = type(pipeline.judge.auditor)()
```

sans jamais le restituer. Toutes les décisions accumulées par les tests
précédents disparaissaient, et le nouvel auditeur restait en place pour tous les
suivants. `test_auto_surveillance_du_judge` exige `n > 0` : **il ne passe que
parce qu'il est déclaré plus haut dans le fichier**, donc exécuté avant. Une
sélection par `-k`, une exécution en parallèle ou un simple déplacement de
fonction le casse — et le message ne dirait rien de la cause.

Le bon patron est **dix lignes plus bas** dans le même fichier :
`suspended_audit()` restitue l'état antérieur même en cas d'exception, et
`test_l_auto_surveillance_reprend_apres_le_banc` le vérifie explicitement.

Corrigé par `try/finally`. **Y compris sur mon propre test** de S14-2, qui
vidait `_facts_cache` sans le restituer : même défaut, commis par l'audit, deux
lots plus tôt.

### S24-4 — Vérifié, sans constat

- **`conftest.py`** neutralise `AUTH_ENABLED`, `SMTP_HOST` et `ALERT_EMAIL_TO`,
  et construit le pipeline `use_llm=False`. Ma crainte d'une dépendance à
  `GEMINI_API_KEY` du poste — la famille ENV-1 — est **infondée** : vérifiée,
  pas supposée. Le mode « règles » ne dépend pas du `.env`.
- `test_agent_fonctionne_sans_cle_api` vérifie en réalité qu'un pipeline
  construit `use_llm=False` est en mode règles. Ce n'est pas ce que son nom
  annonce — « sans clé API » — et le chemin réel, clé absente avec
  `use_llm=True`, n'est testé nulle part. Observation mineure, non corrigée :
  la propriété utile (démontrable hors ligne) est bien tenue.
- Les seuils d'acceptation du banc (`0,85`, `0,20`, `2,0`) sont le contrat, et
  ils sont écrits à un seul endroit.

## Lot S25 — les contrôles de documentation (802 lignes lues intégralement)

`tests/test_documentation.py` (345) · `tests/test_project_metrics.py` (121) ·
`tests/helpers.py` (24) · plus la mesure du rapport qu'ils balaient.

### S25-1 — RETRACTATION : le rapport ne cite pas le PSI. Je l'ai affirmé deux fois.

Les lots S12 et S21 écrivent, comme conséquence documentaire à porter en F1 :

> « Le rapport cite un **PSI de 3,745** comme mesure de dérive. »
> « Le PSI maximal n'est plus 3,7446 mais **3,1826**, et le rapport doit le
> réécrire. »

**Mesuré sur `docs/rapport_technique.md`, 996 lignes : le mot « PSI » n'y
figure pas.** Ni « 3,745 », ni « dérive de distribution », ni « portes de
déploiement », ni « pli ». Le rapport est **entièrement muet** sur l'appareil
de validation.

J'ai donc décrit le contenu d'un fichier que je n'avais pas lu, dans le journal
que le jury lira. C'est la **troisième fois de cette session** :

| # | affirmation | ce qui était vrai |
|---|---|---|
| S21-2 | pli 4 à 0 % d'extrapolation | 12,8 % — j'avais calculé sur le calendrier, le code compte les heures de marche |
| S23-6 | classe `JudgeVerifier` | `VerificationLayer`, nommée 435 lignes plus haut dans le fichier que je complétais |
| S25-1 | le rapport cite le PSI | il n'en parle pas |

Les trois ont la même cause : **avoir conclu sur un fichier non lu**. C'est la
consigne centrale du propriétaire, et c'est moi qui l'ai enfreinte trois fois en
auditant les autres sur ce point exact.

### S25-2 — Et le vrai constat est plus lourd que celui que j'avais inventé

Le rapport ne se trompe pas sur le PSI : **il n'en parle pas du tout.** Or le
poste affiche en page Contrôle « 3 / 7 portes franchies », avec les preuves de
chacune, et `validate_release.py` en fait son code de retour.

Un jury qui lit le rapport puis ouvre le poste trouve un dispositif de
gouvernance — sept portes, quatre en échec, un backtest à quatre plis, une
analyse de dérive — dont **aucune ligne du document ne parle**. Ce n'est pas un
chiffre faux à corriger, c'est un chapitre absent à écrire. Il porte pourtant
ce que le projet a de plus défendable : la promotion est refusée, et elle l'est
pour deux raisons nommées.

### S25-3 — Trois chiffres du résumé exécutif n'ont aucun verrou

`test_aucun_chiffre_cle_ne_contredit_les_artefacts` couvre cinq termes :
features, épisodes agrégés, heures atypiques, généralisation du contrôleur, part
du risque couverte. Le résumé exécutif en publie trois autres, non couverts :

| ligne 33 du rapport | verrou |
|---|---|
| « **290 cas de test** côté Python » | **aucun** |
| « **98 vérifications** des bancs du poste » | aucun — mais mesuré vert : 54 + 35 + 9 = 98 ✔ |
| « **87,15 %** de couverture de lignes » | `test_project_metrics` exige seulement `>= 85,0` |

**Et cette session a ajouté une dizaine de tests.** « 290 » est donc
vraisemblablement périmé, et rien ne le dira : `project_metrics.json` n'a pas
été régénéré — seul `validate_release.py` l'a été. La commande manquante est
`scripts/generate_project_metrics.py`, avec la boucle d'amorçage que
`test_project_metrics` documente sur dix-huit lignes.

### S25-4 — Ce que ces contrôles font bien, et qu'il faut garder

Quatre balayages complémentaires, chacun né d'un défaut réel : endpoints
documentés et supprimés, tests cités et inexistants, commandes `make` absentes,
chemins fantômes (`legacy/`), liens Markdown morts. `docs/audits/` est écarté
avec un motif écrit — un journal décrit une **histoire**, pas un système —
et la contrepartie est assumée.

`helpers.py` ne fait plus que réexporter `sans_accents` depuis `src.formatting`
au lieu d'en porter une copie : « on réexporte, on ne recopie pas ». C'est la
correction FMT-2, et elle est exemplaire.

### Ce que F1 doit faire, révisé

1. **écrire le chapitre absent** sur les portes de déploiement et le backtest —
   ce n'est pas une réécriture, c'est un ajout ;
2. régénérer `project_metrics.json` puis confronter « 290 cas de test » ;
3. élargir `test_aucun_chiffre_cle_ne_contredit_les_artefacts` **après** avoir
   lu le rapport, pas avant — cinq termes couverts sur les dizaines qu'il
   publie.

## Lot S26 — le rapport technique (997 lignes lues intégralement)

`docs/rapport_technique.md`, lu en deux tranches contiguës (1-732, 733-997).
C'est l'objectif n° 2 du propriétaire et le document que le jury lira.

**Six constats vérifiés avant d'être écrits. Deux de mes suspicions étaient
fausses** — et c'est le point le plus utile du lot, après trois erreurs de ce
type dans cette session.

| suspicion | mesure | verdict |
|---|---|---|
| « 45 routes `/api/` » serait périmé | **45** exactement | **juste, aucun constat** |
| les chiffres du § 8.3 dateraient d'avant S6 | l'artefact donne 12, 9,91, 0 %, 118, 5,78, 5, 4,13 | **tous exacts** |

### S26-1 — Une grandeur supprimée du code décrite au § 5.2

Le tableau des grandeurs dérivées publie `duty_per_load`, et le paragraphe
suivant en tire un principe : « la normalisation par la charge soufre est
indispensable ». **Cette colonne a été retirée en S1-3** — aucun lecteur, nulle
part — et le test qui la maintenait en vie a été réaligné sur `flow_per_load`.

L'annexe B, elle, **avait été corrigée** : elle liste bien `flow_per_load`. Le
§ 5.2 ne l'avait pas été. Corrigé à un endroit, pas à son jumeau — dans le
document où ce motif est le plus coûteux.

### S26-2 — Le § 4.1 décrit un booléen, le § 10.4 lui donne trois états

§ 4.1 : « un indicateur `observable` déclarant s'il est détectable **ou non** ».
§ 10.4, soixante pages plus loin : « le référentiel les déclare
`observable: partial` ».

Un booléen ne vaut pas `partial`. Le champ à trois états s'appelle
`observabilite` depuis S2-5, et le booléen n'est conservé que pour compatibilité
d'affichage — c'est lui qui faisait afficher « non — angle mort » sur la
corrosion du faisceau. **Le rapport se contredit à l'intérieur de lui-même.**
Corrigé, et le § 4.1 renvoie désormais au § 10.4.

### S26-3 — « 511 » avait survécu en changeant de mot

Le docstring de `test_aucun_chiffre_cle_ne_contredit_les_artefacts` recense,
parmi ses huit prises : « **511 heures atypiques** à trois lignes de 530 ».

La première occurrence a bien été corrigée. La **seconde**, trois lignes plus
bas, écrivait : « un opérateur ne traite pas **511 points d'alarme** ». Le motif
`(\d+)\s+heures atypiques` ne la voyait pas — **elle désigne la même grandeur
sous un autre nom**, et elle est restée fausse.

C'est le motif dominant du dépôt appliqué au contrôle censé l'empêcher.

**Verrou** : le terme `points d'alarme` est ajouté aux `attendus`, adossé au
même champ d'artefact. **Preuve par mutation** : « 511 points d'alarme » →
écart détecté, le test échoue ; « 530 » → conforme. Le nombre de routes `/api/`
du § 12.2 est verrouillé au passage — juste aujourd'hui, mais rien ne le
maintenait.

### S26-4 — Trois indicateurs déclarés `observed` que le code déclare `derived`

Le tableau du § 10.5 publie le niveau de preuve de cinq indicateurs. `kpi.py`
en déclare **deux `observed` et cinq `derived`** depuis S10-2. Trois lignes se
contredisent :

| indicateur | rapport | code |
|---|---|---|
| Marche durablement sous consigne | `observed` | **`derived`** |
| Charge d'alertes pour l'exploitant | `observed` | **`derived`** |
| Taux horaire de signalement | `observed` | **`derived`** |
| Exposition corrosive cumulée | `derived` | **`observed`** |

Les quatre étaient faux, **dont un dans l'autre sens**. Or l'en-tête de `kpi.py`
pose qu'une grandeur `derived` « ne doit jamais être présentée comme une
mesure » : le rapport faisait exactement cela pour la charge d'alertes, c'est-à-dire
pour le « 5 épisodes/mois » qu'il publie deux sections plus haut. Corrigé.

### S26-5 — Le § 12.2 décrit le poste d'avant la correction scientifique

« **Six familles de courbes** couvrent […] performance observée/attendue. »

Le poste en compte **dix**. Les quatre manquantes sont précisément celles
ajoutées par S1-4 et API-2 : coefficient d'échange observé contre attendu,
résistance d'encrassement, température d'entrée observée contre attendue, source
froide. **Ce sont les quatre qui portent le diagnostic** — celles que toute la
correction d'ADR-002 existe pour rendre traçables.

Et « performance observée / attendue » est **mot pour mot le libellé que
`app.js` a explicitement corrigé** : « Le titre disait *Performance observée /
attendue*. C'est ce que cette paire n'est pas : le résidu de duty vaut l'écart
de consigne changé de signe. » Le rapport portait encore le libellé fautif.
Corrigé, avec le renvoi au § 5.3.

### S26-6 — Constat OUVERT : ce que mesure `trap_detection_rate`

L'artefact publie `trap_detection_rate: 0.958` et `trap_missed: 5`. Le rapport
présente **100 %** comme taux de détection et **95,8 %** comme « détection ET
sanction suffisante », avec « 5 cas détectés mais insuffisamment sanctionnés ».

Les deux lectures sont cohérentes entre elles **si** le champ nommé
`trap_detection_rate` mesure en réalité détection + sanction. Le nom dit le
contraire, et `renderBench` l'affiche sous « pièges conçus (non-régression) ».
**Trancher exige de lire `judge_eval.py` intégralement** — 759 lignes, lues par
une session antérieure, pas par moi. Constat laissé ouvert plutôt que fermé au
jugé.

### Ce que le rapport fait bien, et qu'il ne faut pas toucher

Le § 5.3 démontre la circularité algébrique du duty avec ses chiffres. Le
§ 5.3 bis expose la climatologie de Safi et **dit franchement** que UA est
apparent. Le § 9.2 documente une erreur d'analyse commise puis corrigée. Le
§ 10.5 explique le retrait du chiffrage économique au lieu de le supprimer en
silence. L'annexe B porte sa propre note de correction. **C'est un rapport
honnête** ; ses défauts sont des retards de propagation, pas des complaisances.

### Reste pour F1

- écrire le chapitre absent sur les **portes de déploiement** et le backtest
  (S25-2) — le document n'en dit rien ;
- régénérer `project_metrics.json` et confronter « 290 cas de test » ;
- trancher S26-6 après lecture intégrale de `judge_eval.py`.

## Lot S27 — RAP-17 clos (759 lignes lues intégralement)

`src/governance/judge_eval.py`

### S27-1 — Le constat que j'ai retrouvé sans l'avoir lu

S26-6 laissait ouverte la question de ce que mesure `trap_detection_rate`. La
lecture intégrale tranche en une ligne :

```python
"trap_detection_rate": round(float(traps_raw["success"].mean()), 3),
#                                            ^^^^^^^ = caught AND penalised
```

**Le champ contient un taux de SUCCÈS, pas de détection.** Et dix lignes plus
haut, `by_trap` publie un `detection_rate` qui, lui, vaut bien `caught.mean()`.
**Deux champs, le même mot, deux grandeurs.**

**Ce constat existait déjà dans ce journal, sous le nom RAP-17, gravité
« haute »**, écrit lors de la phase de diagnostic — ligne 3715 :

> « La clé publiée porte le mauvais nom […] Trois consommateurs lisent cette clé
> en croyant lire une détection : la porte d'intégration continue, ADR-004, et
> tout lecteur de l'artefact. »
> « Le 100 % n'est publié nulle part dans le résumé. »

Il n'a jamais été corrigé. Je l'ai retrouvé indépendamment, par lecture — ce qui
valide la méthode, mais je l'aurais trouvé plus vite en lisant le journal en
entier plutôt que ses onze derniers lots.

### S27-2 — Ce que le mauvais nom coûtait

Sur ce corpus, l'écart est de **4,2 points** : 100 % de détection pour 95,8 % de
succès. Un lecteur de l'artefact concluait « 4,2 % des fautes ne sont pas
vues ». **C'est faux : elles sont toutes vues.** Les cinq cas sont détectés et
insuffisamment sanctionnés, sur deux familles seulement — et cette distinction
est précisément ce que le rapport § 8.3 explique correctement.

**Le rapport était donc plus juste que l'artefact qu'il cite.** C'est l'inverse
de l'ordre de fraîcheur établi par cet audit sur dix-huit occurrences
(`code/artefacts → README → ADR → rapport`). Première exception recensée.

Quatre consommateurs lisaient la clé mal nommée, dont **la porte d'intégration
continue** (`ci.yml:114`) et `test_api.py:522`. Fonctionnellement le seuil de
0,85 opposé au taux le plus strict reste correct — le risque était
interprétatif, et il portait sur le chiffre que le jury regardera.

### S27-3 — Correction : trois situations, trois champs

Le résumé ne distinguait pas « jamais vue » de « vue mais peu sanctionnée » :
`trap_missed` comptait les deux.

| champ | mesure |
|---|---|
| `trap_detection_rate` | `caught` — les fautes réellement identifiées |
| `trap_success_rate` | `caught ET penalised` — l'ancien contenu, sous son vrai nom |
| `trap_caught_not_sanctioned` | vues, pas assez sanctionnées |
| `trap_missed` | **jamais vues** |

**Preuve par mutation**, sur quatre cas construits (2 succès, 1 vue-non-sanctionnée,
1 jamais vue) :

| | ancien | nouveau |
|---|---|---|
| `trap_detection_rate` | 0,500 — nommé « détection » | **0,750** — réellement vues |
| `trap_success_rate` | absent | 0,500 |
| `trap_caught_not_sanctioned` | absent | **1** |
| `trap_missed` | **2** — deux natures confondues | **1** |

Portés : le producteur, `report()` (qui écrivait « rappel global … fautes
correctement identifiées » sur le taux de succès), `ci.yml`, `test_api.py`,
`test_agents_judge.py`, le poste, et la fixture du banc front. Le poste affiche
désormais **les deux** chiffres — « pièges conçus : vus » et « vus ET
sanctionnés » — au lieu du seul taux mal nommé.

`test_agents_judge.py` gagne l'invariant qui manquait :
`trap_detection_rate >= trap_success_rate`. Il est vrai par construction
(`success ⊆ caught`) et il échouerait si quelqu'un réintervertissait les deux.

### À régénérer

`reports/judge_eval_summary.json` porte encore l'ancien vocabulaire. La commande
est `make eval-judge`, ou `.\.venv\Scripts\python.exe -m src.governance.judge_eval`.
Le § 8.3 du rapport reste juste sur le fond, et pourra désormais **citer les
champs par leur nom**.

## Lot S28 — README et ADR-004 (643 lignes lues intégralement)

`README.md` (556) · `docs/decisions/ADR-004-controleur-de-coherence.md` (87)

Lot déclenché par la régénération de S27 : le banc republié donne
**8,6 % (n = 58)** de généralisation, contre « 10 % (n = 60) » dans les
documents. Le contrôle étendu en S26 l'a signalé — **le dispositif a fonctionné
avant moi**.

### S28-1 — Le même chiffre publié trois fois, verrouillé une seule

Le README publie le taux de généralisation **trois fois** : dans la synthèse
d'ouverture, dans le tableau du banc, et dans la phrase de mise en avant
« **10 %**, et c'est le chiffre à retenir ». Le motif du contrôle exigeait
`(n = …)` : il n'en voyait **qu'une**.

C'est exactement le motif de « 511 » (S26-3) : la valeur survit là où le
contrôle ne regarde pas. Un second motif est ajouté, adossé à la phrase de mise
en avant.

**Et il a immédiatement trouvé ce que je n'avais pas vu** : deux occurrences de
plus dans **ADR-004**, un fichier que je n'avais pas lu. Je l'ai lu avant d'y
toucher.

### S28-2 — La précision publiée n'était pas celle de l'artefact

L'attendu était arrondi à l'entier (`:.0f`) : le banc mesure 0,086, le contrôle
attendait « 9 » et lisait « 8 » dans « 8,6 % ». **Arrondir à l'entier un taux de
gouvernance qui vaut moins de dix fait perdre un demi-point sur le chiffre que
le projet met le plus en avant.** Attendu et motif passent à la décimale
française.

### S28-3 — ADR-004 se contredit à neuf lignes d'intervalle

L'ADR liste les cinq mutations non ciblées :

> « bruit sur les valeurs, sévérité permutée, raisonnement tronqué, modes
> permutés, confiance déplacée. **Aucune ne vise un contrôle.** »

Neuf lignes plus bas, le même document explique que **trois de ces cinq
visaient trois contrôles nommés** et ont été retirées pour cette raison —
« bruiter une valeur de 3 à 25 % franchit toujours la tolérance de 1 % ».

**Le paragraphe qui corrige le défaut est imprimé sous la liste qui le porte.**
La liste réelle est celle de `_blind_mutations` : diagnostic et raisonnement
intervertis, raisonnement tronqué, action d'un autre mode, service destinataire
erroné, check-list erronée. Corrigée, avec le renvoi au test qui la verrouille.

### S28-4 — Un fragment de tableau échoué en plein texte

Le tableau du banc portait **deux colonnes sur trois** :

```
| Faux positifs sur cas sains | 0 % |
```

et sa dernière cellule se trouvait **neuf lignes plus bas**, collée à la fin
d'un paragraphe :

```
dispositif du tout. ne rejette pas le correct |
```

Une coquille de copie, dans une décision d'architecture destinée au jury. Le
tableau est reconstitué, et il publie désormais **les deux** taux distingués par
S27 : « pièges conçus — vus » à 100 %, « vus ET sanctionnés » à 95,8 %.

### S28-5 — Les plafonds de sécurité, incomplets dans l'ADR

L'ADR cite cinq manquements plafonnés à 4/10 et **omet l'état de marche erroné,
plafonné à 5/10** — que le README comme le rapport mentionnent tous deux, et
que `_apply_safety_cap` applique. Ajouté, avec son motif.

### S28-6 — Six corrections au README

| # | ce qui était écrit | mesure |
|---|---|---|
| variance partagée | **90,6 %** | **88 %** — le même document publie 88 % trente lignes plus bas, et r = −0,94 donne r² = 88,4 % |
| bases de détermination | quatre | **cinq** — `climatology` manquait, celle qui fonde la température d'eau de mer, donc toute la correction d'ADR-002 |
| « 5 épisodes par mois » | présenté comme un comptage | **`derived`** (S10-2) — le README énonce la distinction trente lignes plus bas sans se l'appliquer |
| généralisation ×3 | 10 % | 8,6 % |
| accord | « aucune des quatorze mois » | « aucun » |

Le **90,6 %** est le plus net : il est contredit par l'arithmétique du document
lui-même. `r = −0,94` publié deux lignes au-dessus donne `r² = 88,4 %`, et le
tableau d'indépendance trente lignes plus bas écrit **88 %**. Une seule des deux
valeurs pouvait être vraie.

### État des quatre motifs après correction

**Zéro écart** sur `README.md`, les onze ADR, `architecture.md`,
`rapport_technique.md`, le runbook et la matrice de traçabilité.

## Lot S29 — le point d'entrée et le rédacteur d'escalade (367 lignes lues intégralement)

`api/__main__.py` (73) · `src/notifications/redaction.py` (294)

Les deux derniers fichiers de `src/` et `api/` que le brief listait comme jamais
lus, hors `email.py`.

### S29-0 — `api/__main__.py` : rien à reprendre

Lu en entier. Il tient exactement sa promesse d'en-tête — rendre `API_HOST` et
`API_PORT` effectifs, là où trois sources de vérité coexistaient et où la seule
documentée était inerte. `config.validate()` échoue **avant** l'import
d'uvicorn, `workers=1` porte son motif, et la double validation avec
`api/main.py` est un filet assumé pour le lancement direct par uvicorn. **Aucun
constat.**

### S29-1 — Le courriel d'escalade expédiait les codes bruts que l'écran traduit

`app.js` porte une table de **vingt** réserves traduites, avec ce motif :

> « Le poste affichait le code brut — OVERCONFIDENCE — dans un encadré destiné à
> l'exploitant. **Un code de programme n'est pas une réserve** : il faut dire ce
> qui a été constaté et ce que cela change. »

`rediger_gouvernance` publiait, sous le titre « Réserves les plus fréquentes sur
les décisions » :

```
  • OVERCONFIDENCE — 12 cas
  • HALLUCINATED_VALUE — 3 cas
```

**Et c'est le canal le plus asymétrique du système.** L'écran se lit devant le
poste, avec le contexte sous les yeux. Le courriel se lit sur un téléphone, la
nuit, sans rien d'autre — c'est précisément la situation où un code de programme
ne veut rien dire.

Le module condamne pourtant cela dans son propre en-tête, et porte **trois**
tables de traduction pour les régimes, les origines et les modes d'agent. Il en
manquait une, sur la surface qui en avait le plus besoin.

### S29-2 — Et l'état du contrôleur, première ligne du rapport

```python
statut = juge.get("status") or "—"
lignes.append(f"État : {statut}")
```

`status` vaut `ALERTE`, `OK` ou **`EN_ATTENTE`** — un identifiant à tiret bas,
exactement ce que l'en-tête reproche à `running` et `rules`. C'est la première
ligne de la section que le module désigne comme « l'information à agir ».

### S29-3 — Deux formats de date dans un rapport d'une page

La date d'édition passait par `_horodatage` — « 01/01/2024 à 07h00 ». La période
analysée sortait brute — « 2024-01-01 07:00:00 ». **L'aide existe dans ce
fichier et n'était appelée qu'une fois sur trois.**

### S29-4 — Une suspicion vérifiée et retirée

Je soupçonnais `step_nominal` d'être expédié sous sa forme pandas
« 0 days 01:00:00 », par symétrie avec la fonction `duree()` que `app.js` porte
pour ce cas. **Faux** : `dcs_loader.py:543` applique déjà `duree_pas()`, et son
commentaire documente précisément cette correction — « deux implémentations
d'une même règle, dans deux langages, dont la seule vivante était celle que
l'ADR dit ne pas exister ». Vérifié avant d'écrire.

### Correction et verrou

La table des vingt libellés vit désormais dans `src/agents/schemas.py`, auprès
du contrat de décision. Le poste garde la sienne — **on ne partage pas un
dictionnaire entre Python et JavaScript** — et deux contrôles ferment l'écart :

- `test_les_reserves_sont_traduites_des_deux_cotes` (le patron, quinzième
  emploi) exige l'égalité des deux jeux de codes, dans les deux sens ;
- l'extension de `test_les_identifiants_internes_sont_traduits` — voir S29-5.

### État de la lecture

Il ne reste, hors documentation et tests, que `src/notifications/email.py`
(512 lignes) et le front `twin.js` (2 167) + `dashboard.html` (586).

### S29-5 — DEUX ERREURS DE L'AUDIT SUR CE MEME LOT

**Première.** J'ai écrit `test_le_courriel_ne_publie_aucun_identifiant_machine`
avec un critère de **forme** : toute chaîne en majuscules de six lettres ou
plus. Il a échoué sur `['AFFIRME', 'SERVICE', 'VERDICT']` — des mots français.
`_titre()` met les intitulés de section en majuscules : « VERDICT DU
CONTRÔLEUR », « CE QUE CE RAPPORT N'AFFIRME PAS ».

**Une heuristique de forme ne distingue pas un identifiant d'un titre.** Le
contrôle interroge désormais les **vocabulaires réels** : pour chaque code
soumis, le libellé doit être présent et le code absent. Il ne peut plus produire
de faux positif.

C'est la quatrième fois de cette session que j'écris un prédicat sans avoir
observé la sortie réelle — après le nom de classe, le calcul d'extrapolation et
le contenu du rapport. La cause est chaque fois la même.

**Seconde, et plus grave.** J'ai ajouté **deux tests à un fichier que je n'avais
pas lu**. Il contenait déjà `test_les_identifiants_internes_sont_traduits`,
dont le nom couvre exactement ma correction. Mon ajout faisait doublon sur trois
vocabulaires, et sa fixture recopiait un `PAYLOAD` déjà défini au module.

**Ce que la lecture a révélé, et qui vaut mieux que mon doublon** : le test
existant portait **un nom plus large que sa couverture**. Il vérifiait trois
vocabulaires sur cinq, et les deux manquants sont précisément ceux qui
échappaient à la règle. C'est le motif du dépôt, et il ne se voyait qu'en
lisant le fichier.

Le doublon est retiré ; le test existant est étendu aux cinq vocabulaires, à la
mise en forme de la période, et il réutilise le `PAYLOAD` du module — qui portait
déjà `NO_QUANTITATIVE_EVIDENCE` et `ALERTE` sans que personne ne les vérifie.

## Lot S30 — le canal d'escalade (512 lignes lues intégralement)

`src/notifications/email.py` — dernier fichier de `src/` jamais lu.

Le module est de très bonne facture : `diagnostiquer_echec` traduit chaque
panne SMTP en cause actionnable plutôt qu'en nom de classe, le verrou sur les
destinataires est justifié par une mesure (« 200 000 retraits, un observateur
concurrent l'a vu vide 54 098 fois »), et `status()` dit **pourquoi** le canal
est muet au lieu d'afficher « désactivé ». Les deux constats ci-dessous portent
sur la même promesse d'en-tête, prise au mot.

> « Si le canal sortant tombe, il faut pouvoir dire **APRÈS COUP** quelles
> alertes auraient dû partir. »

### S30-1 — La correction réintroduisait le défaut qu'elle corrige, par l'ordre de deux appels

Le bloc « aucun destinataire » a été écrit pour un motif explicite : *une alerte
critique sans destinataire disparaissait sans trace*. Il faisait :

```python
self._deposer(orphelin)          # peut lever
self._tracer(orphelin, ...)      # jamais atteint si le dépôt lève
```

`_deposer` lève `RuntimeError("aucun dépôt configuré")` dès que `self.spool`
vaut `None`. **Ce cas est atteignable** : le garde d'entrée n'exige que
`transport_ready OU journal_ready`, donc un relais SMTP configuré **sans** dépôt
passe ; `EmailNotifier` construit sans `spool` est exactement ce que font les
tests ; et un système de fichiers en lecture seule annule le dépôt au démarrage.

**Vérifié plutôt qu'affirmé** : l'exception ne tue pas le rejeu —
`replay._emit` enveloppe ses abonnés dans un `try/except`. Mais elle empêche
`_tracer`, et **l'alerte critique disparaît du journal d'escalade**, ne laissant
qu'un « Abonné en erreur » dans le journal serveur, que l'exploitant ne lit pas.

C'est le défaut exact que ce bloc existe pour corriger, réintroduit par l'ordre
des deux appels.

**Preuve par mutation** — relais configuré, aucun dépôt, aucun destinataire :

| | journal d'escalade |
|---|---|
| avant | **0 entrée** — l'alerte disparaît |
| après | **1 entrée** : « non distribué — aucun destinataire actif […] **— dépôt local indisponible (RuntimeError)** » |

La trace passe avant le dépôt : c'est elle la garantie, le fichier n'en est que
la copie durable. Et l'échec du dépôt est **nommé dans la trace** plutôt qu'avalé.

### S30-2 — La seule perte d'alerte qui ne laissait aucune trace

Les trois issues du worker — `envoye`, `depose`, `echec` — passent toutes par
`_tracer`. Une quatrième existe et n'y passait pas : la **file saturée**.

```python
except queue.Full:
    self._failed += 1
    self._last_error = "file de notification saturee"
    logger.warning(...)          # journal SERVEUR, pas journal d'escalade
```

Or la saturation survient **précisément quand le relais est lent ou tombe**,
c'est-à-dire au moment où le plus d'alertes se perdent d'un coup. Le compteur
`failed` montait ; l'exploitant voyait un nombre sans savoir lesquelles.

**Preuve par mutation** : file de taille 1 déjà pleine, message critique soumis
— 0 entrée avant, **1 entrée « echec — file de notification saturée : le relais
ne suit pas, ce message n'a pas été mis en file »** après.

### S30-3 — Vérifié, sans constat

- **`_emit` enveloppe ses abonnés** : aucun abonné en erreur n'arrête le rejeu.
  Ma crainte d'un plantage du fil de rejeu était infondée.
- **`_recipients` est le seul état réellement partagé par trois fils**, et il
  porte son verrou. `journal`, `_pending_keys` et `_last_sent_by_key` sont
  manipulés par des opérations atomiques sous le GIL, ou n'ont qu'un écrivain.
- **`stop()` renonce si la file est pleine** — le worker est un thread démon,
  le processus se termine quand même. Sans conséquence, non corrigé.
- `self.recipient` (affichage masqué) prend le **dernier** destinataire par ordre
  alphabétique, tandis que `_premier_destinataire` prend le premier. Deux
  conventions, mais la première ne sert qu'à l'affichage d'une adresse masquée.

### État de la lecture de `src/` et `api/`

**Terminé.** Tous les fichiers Python de `src/`, `api/` et `scripts/` producteurs
de code ont été lus intégralement, par cette session ou les précédentes. Il ne
reste que le front (`twin.js` 2 167, `dashboard.html` 586), la documentation
(`architecture.md`, dix ADR) et une quinzaine de fichiers de tests.

## Lot S31 — l'architecture et les deux ADR du cœur analytique (395 lignes lues intégralement)

`docs/architecture.md` (196) · `ADR-001` (105) · `ADR-002` (75) ·
`decisions/INDEX.md` (19)

### S31-1 — ADR-002 portait trois chiffres périmés, et incohérents entre eux

L'ADR qui fonde toute la correction scientifique — la climatologie de Safi qui
rend UA calculable — publiait :

> « R² = 0,92 avec un écart-type résiduel de **0,70 kW/K**, soit **3,6 %** de la
> valeur de UA »

| source | R² | σ | part de UA |
|---|---|---|---|
| **ADR-002** | 0,92 | **0,70 kW/K** | **3,6 %** |
| rapport § 5.3 bis | 0,924 | 0,63 kW/K | 3,5 % |
| README | 0,924 | 0,63 kW/K | 3,5 % |
| artefact (`validate_release`) | **0,924** | **0,63 kW/K** | — |

**Et les chiffres de l'ADR ne tiennent pas entre eux** : 0,70 rapporté à la
référence de 17,77 kW/K donne **3,9 %**, pas 3,6 %. Le rapport et le README
étaient déjà corrigés ; seul cet ADR portait l'ancien jeu — et c'est celui qu'un
jury ouvre pour comprendre d'où vient l'indicateur.

### S31-2 — Une couche entière absente de l'architecture

Le schéma de chaîne et le tableau des responsabilités listent `domain`,
`ingest`, `features`, `models`, `agents`, `governance`, `analytics`, `realtime`,
`api`, `security`, `notifications`. **`src/operations/` n'y figure nulle part.**

C'est pourtant 967 lignes, **deux bases SQLite**, le cycle de vie ISA-18.2 des
alarmes, la traçabilité des interventions, six routes et un écran du poste. Un
lecteur de l'architecture ne peut pas savoir que cette couche existe.

Ajoutée au schéma et au tableau.

### S31-3 — La commande de lancement contredisait le module écrit pour l'abolir

`architecture.md` documentait :

```
.venv\Scripts\python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Or `api/__main__.py` existe **précisément** pour supprimer cette forme, et son
en-tête nomme les coupables :

> « Le Dockerfile écrivait `--host 0.0.0.0 --port 8000` en dur, **le README et
> le runbook passaient leurs propres valeurs sur la ligne de commande**. Trois
> sources de vérité pour une même décision, dont la seule documentée comme telle
> était inerte. »

**`architecture.md` était la quatrième**, et elle n'était pas citée. Remplacée
par `python -m api`, avec la raison écrite et la forme uvicorn conservée comme
alternative explicite.

### S31-4 — Une date de vérification sans périmètre n'engage rien

L'en-tête portait « **état vérifié le 2 août 2026** ». Cinq jours et une
trentaine de lots plus tard, la mention affirmait une fraîcheur que le document
n'avait plus — et elle ne disait pas **ce qui** avait été vérifié. La preuve est
S31-2 : le document portait cette date alors qu'une couche entière y manquait.

Remplacée par une mention qui nomme son périmètre, et qui cite l'omission comme
raison d'être de ce format.

### S31-5 — Vérifié, sans constat

- **ADR-001** est exact de bout en bout : R² 0,968 / 0,962 / +0,006, r = −0,94,
  variance partagée 88 % puis 29 %, et le tableau du banc d'injection correspond
  au README. Le seul ADR du cœur analytique qui n'avait pas dérivé.
- **INDEX** recense onze décisions, onze fichiers existent.
- L'affirmation « `REFERENCE_FRACTION` définie une seule fois dans
  `src/features/thermal.py` » est vraie — vérifiée en S1 et S8.
- Les six invariants de sûreté correspondent au code, y compris le sixième dont
  la note d'édition explique pourquoi un lecteur en comptait cinq.

### Reste du corpus documentaire

Huit ADR non lus (ADR-003, 005 à 011, 610 lignes) et le runbook.

## Lot S32 — quatre ADR (291 lignes lues intégralement)

`ADR-003` (73) · `ADR-005` (49) · `ADR-009` (82) · `ADR-011` (87)

### S32-1 — La charge d'alertes était sur-estimée de 22 %, et c'est l'ADR qui avait raison

ADR-003 conclut : « 58 épisodes agrégés sur quatorze mois, soit environ **4,1
par mois** ». Le README et le rapport publiaient tous deux **5 épisodes/mois**.

L'arbitre est le code. `kpi.alert_load` :

```python
span_days = (self.f.index.max() - self.f.index.min()).days
per_month = len(episodes) * 30.0 / span_days
```

soit **58 × 30 / 424 = 4,10**. ADR-003 est exact ; les deux documents les plus
lus sur-estimaient de **22 %**.

**C'est la seconde exception à l'ordre de fraîcheur** que cet audit a établi sur
dix-huit occurrences — `code/artefacts → README → ADR → rapport_technique`.
Après S27-2, où le rapport était plus juste que l'artefact qu'il cite, voici un
ADR plus juste que le README. L'ordre est une tendance forte, pas une loi : il
ne dispense pas de vérifier.

Le brief avait signalé ce chiffre pour sa **nature** — « le ~5 épisodes/mois est
un résultat de modèle, le rapport doit le dire ». C'était vrai, et corrigé en
S26-4 et S28-6. **Sa valeur était fausse en plus**, et personne ne l'avait vu :
qualifier un chiffre ne le vérifie pas.

**Verrou** : le terme est ajouté à `test_aucun_chiffre_cle_ne_contredit_les_artefacts`,
calculé depuis `project_metrics` par la formule du KPI. Mesuré après correction :
aucun écart sur le README et le rapport.

### S32-2 — ADR-009 : les heures d'apprentissage avaient bougé

Le tableau « avant / après » du rebasage publiait **3 487 h** d'apprentissage.
L'artefact courant et le rapport § 5.3 bis disent **3 505 h**. Les cinq autres
lignes du tableau — UA 17,77, R² 0,924, σ 0,63, corr −0,54 — sont exactes.
Corrigée.

### S32-3 — Vérifié, sans constat

- **ADR-003** : « dix-sept règles », « trois des six dernières heures »
  (`MODEL_PERSIST_MIN = 3`, `MODEL_PERSIST_WIN = 6`), « onze features »,
  « 6,2 % » — tous conformes au code.
- **ADR-005** : les quatre contrôles d'intégration continue qu'il annonce
  existent, et le défaut qu'il documente — le rattachement d'une anomalie à une
  pièce improvisé par sous-chaîne côté interface — est bien celui que S2-6 a
  vérifié comme corrigé.
- **ADR-009** : l'énoncé de la fuite de données est exact, et le test
  d'alignement des trois périodes existe.
- **ADR-011** : « le banc frontend passe de 36 à 54 vérifications » — mesuré,
  `frontend_smoke` en compte **54**. Les cinq fonctions de `src/formatting` sont
  exactes.

Ces quatre ADR sont d'une qualité remarquable : chacun énonce l'option écartée
et la raison de l'écarter, et ADR-009 publie l'effet mesuré de sa propre
correction. **Deux chiffres périmés sur 291 lignes**, et l'un des deux
corrigeait les documents plus lus que lui.

### Reste du corpus documentaire

Quatre ADR non lus — 006, 007, 008, 010 (284 lignes) — et le runbook.

## Lot S33 — les quatre derniers ADR (284 lignes lues intégralement)

`ADR-006` (48) · `ADR-007` (58) · `ADR-008` (91) · `ADR-010` (87).
**Le corpus décisionnel est entièrement lu.**

### S33-1 — ADR-010 annonçait deux plafonds de sécurité : les deux étaient faux

> « une action `EN_MARCHE` alors que la tâche exige la consignation est
> sanctionnée `UNSAFE_ACTION`, note plafonnée à **1/10** ; une action réclamant
> un arrêt que le plan n'exige pas est sanctionnée `ACTION_OVERSIZED`, note
> plafonnée à **4/10**. »

Confronté à `_apply_safety_cap` :

| plafond annoncé | plafond appliqué |
|---|---|
| `UNSAFE_ACTION` → **1/10** | **4,0** |
| `ACTION_OVERSIZED` → **4/10** | **aucun** |

Le second est le plus lourd. `ACTION_OVERSIZED` n'apparaît qu'**une fois** dans
`judge_agent.py` — ligne 533, ajouté à `issues` — et il est **absent de
l'ensemble bloquant**. Un arrêt injustifié ne coûte donc que le poids de V4,
soit 14 %. **L'ADR annonce une barrière qui n'existe pas.**

Le rapport § 7.3 et le README listent correctement les six plafonds, et aucun
des deux ne mentionne `ACTION_OVERSIZED`. Troisième document isolé du corpus —
et cette fois l'ADR est celui qui se trompe, à l'inverse de S32-1.

**La question de fond est posée, pas tranchée.** Faut-il plafonner
`ACTION_OVERSIZED` ? L'argument de l'ADR — « immobiliser une ligne sans
nécessité est aussi une faute » — plaide pour. Le faire modifie le comportement
du contrôleur et les chiffres du banc : c'est une décision, pas une correction
documentaire. Elle est écrite dans l'ADR, à l'endroit où elle se pose.

*La docstring de `test_une_action_en_marche_conforme_a_sa_tache_n_est_pas_sanctionnee`
portait le même « 1/10 ». Corrigée.*

### S33-2 — La commande de lancement, cinquième et sixième occurrences

`api/__main__.py` a été écrit pour supprimer trois sources de vérité
concurrentes, et son en-tête les nomme : « le Dockerfile […], **le README et le
runbook** passaient leurs propres valeurs sur la ligne de commande ».

Recensement après lecture :

| document | ce qu'il écrivait | état |
|---|---|---|
| `architecture.md` | `-m uvicorn … --host … --port …` | corrigé en S31-3 |
| **`ADR-006`** | `uvicorn api.main:app --port 8000` | **corrigé ici** |
| **`README.md`** | `uvicorn api.main:app --reload --port 8000` | **corrigé ici** |
| `docs/runbooks/runbook-operations.md` | `-m uvicorn … --host 0.0.0.0 --port 8000` | **reste** — fichier non lu |

**Le module a été écrit pour mettre fin à cette dispersion, et aucun document ne
l'avait adopté.** Quatre au lieu de trois, puisque `ADR-006` s'ajoutait à la
liste que l'en-tête dressait. ADR-006 affirmait de surcroît « une seule commande
le démarre » en publiant celle qui ignore la configuration.

Le runbook n'est **pas corrigé** : je ne l'ai pas lu. Il fera son propre lot.

### S33-3 — ADR-007 et ADR-008 : exacts

- **ADR-007** : 600 000 itérations, douze caractères minimum, cinq tentatives,
  dérivation PBKDF2 même sur adresse inconnue, session opaque + CSRF + double
  expiration, registre hors dépôt — **tout est conforme au code lu en S13**. La
  seule nuance non dite est l'écart d'égalisation d'une fois par processus
  (S13-5), désormais écrit dans la docstring de `_decoy_hash` ; l'inscrire dans
  un ADR relèverait de la sur-précision.
- **ADR-008** : les cinq principes ISA-101 correspondent au code lu en S23 —
  glyphe + mot + couleur (`sevMark`), troisième niveau d'Endsley (`trendOf`),
  cache de série (`loadSeries`), moteur suspendu hors vue (`setPaused`),
  dégradation automatique du rendu. Le banc frontend vérifie le contraste AA.
  **Aucun constat.**

### Bilan du corpus décisionnel — onze ADR lus

| ADR | état |
|---|---|
| 001, 005, 007, 008 | exacts |
| **002** | trois chiffres périmés et incohérents (S31-1) |
| **003** | **plus juste que le README et le rapport** (S32-1) |
| **004** | liste de mutations contredite neuf lignes plus bas, tableau amputé (S28-3, S28-4) |
| **006** | commande de lancement obsolète |
| **009** | heures d'apprentissage périmées (S32-2) |
| **010** | deux plafonds faux, dont une barrière inexistante |
| 011 | exact |

**Quatre ADR sur onze sont exacts.** Les sept autres portent des chiffres ou des
affirmations que le code a dépassés — et dans un cas, c'est l'ADR qui avait
raison contre les deux documents les plus lus.

## Lot S34 — runbook et documents de traçabilité (316 lignes lues intégralement)

`docs/runbooks/runbook-operations.md` (248) · `data_dictionary_E7301.md` (40) ·
`traceability_matrix_E7301.md` (28).
**Le corpus documentaire est entièrement lu**, hors notebook.

### S34-1 — Le canal d'escalade ne fait pas ce que le runbook annonce

> « `ALERT_EMAIL_TO` reste un destinataire de repli facultatif ; **dès la
> connexion, l'e-mail de la session le remplace**. »

**Faux, et vérifié par la mesure.** `add_recipient` **ajoute** l'adresse du
technicien à l'ensemble sans en retirer aucune, et `notify` boucle sur tous les
destinataires :

```
ALERT_EMAIL_TO seul        : ['astreinte@ocpgroup.ma']
après ouverture de session : ['astreinte@ocpgroup.ma', 'mounir@ocpgroup.ma']
après déconnexion          : ['astreinte@ocpgroup.ma']
```

**Le comportement du code est le bon** — une astreinte permanente ne doit pas
cesser d'être prévenue parce qu'un technicien s'est connecté. C'est le runbook
qui décrivait l'inverse, et un exploitant qui le lit croit que l'adresse
d'astreinte se tait dès qu'une session s'ouvre. Corrigé, avec la mesure.

### S34-2 — Le compte des portes ne correspondait pas à l'écran

Le runbook explique très bien pourquoi `/api/health` est `degraded` par
construction, puis nomme « les trois portes que le code décide » et les deux en
échec définitif. **Cinq.** Le poste en affiche **sept**.

Les deux absentes — `redondance_hors_modele` et `derive_de_distribution` — sont
publiées et en échec **sans bloquer**, et un exploitant qui lit « 3 / 7 portes
franchies » sans les connaître y voit deux incidents. Ajoutées avec leur nature :
l'une algébriquement infranchissable, l'autre non interprétable faute de pli
saisonnièrement couvert.

### S34-3 — Le dictionnaire des tags publiait un vocabulaire disparu

La colonne « Statut » portait `inferred` et `unknown`, et la note d'en-tête une
règle à leur sujet. **Ces trois valeurs — `confirmed`, `inferred`, `unknown` —
apparaissent zéro fois dans `src/domain/tags.yaml`.** Le référentiel porte
désormais `basis`, la liste des bases indépendantes.

C'est exactement ce que le commentaire d'`app.js` documentait depuis longtemps :
« `confidence` a **gardé son nom en changeant de sens** […] le rapport promet
encore `confirmed` / `inferred` / `unknown` : ces trois valeurs n'existent
plus ». Le poste avait été corrigé ; le dictionnaire gouverné, non.

La colonne est remplacée par les bases réelles, tag par tag, lues dans le YAML.
Les unités et les rôles y sortaient en codes bruts — `degC`, `m3/h`, `primary`,
`degraded` — ce qu'ADR-011 règle 1 interdit : traduits.

### S34-4 — CONSTAT OUVERT : `stoichio` est déclaré et utilisé par aucun tag

`DeterminationBasis` (`knowledge.py:52`) déclare cinq bases. Mesuré sur
`tags.yaml`, toutes sections :

| base | tags |
|---|---|
| `isa_5_1` | 12 |
| `data` | 12 |
| `process` | 8 |
| `climatology` | **1** — `T_SEAWATER`, sous `external_inputs` |
| **`stoichio`** | **0** |

**Cinquième occurrence du motif** après `rejected`/`validated_offline` (LIN-1),
`CANCELLED` (WF-2), `derived` avant S10-2 et `uncertainty_level` (J-5) : une
valeur déclarée qu'aucun producteur n'écrit.

**Et elle n'est pas gratuite.** Le rapport § 2.2 fait explicitement l'argument
stœchiométrique pour `LOAD_SULFUR` — « 1 t de soufre donne 3,06 t de H₂SO₄, soit
~1 370 t/j à 18,6 t/h ». **Le raisonnement est tenu dans le rapport et n'est pas
consigné dans le référentiel.** Deux issues, et je ne tranche pas : ajouter
`stoichio` au `basis` de `LOAD_SULFUR` — ce qui rend le vocabulaire productible
et aligne le référentiel sur son propre argument — ou retirer la valeur. La
première est probablement la bonne, mais **`tags.yaml` est une donnée gouvernée**
et son édition engage la provenance, pas la mise en forme.

*Au passage, ma correction de S28-6 est confirmée : `climatology` est bien
utilisé, par l'entrée qui rend UA calculable. La matrice de traçabilité, elle,
listait quatre bases en omettant `climatology` et en incluant `stoichio` —
fausse dans les deux sens. Corrigée.*

### S34-5 — Vérifié, sans constat

- **L'empreinte SHA-256** de `DATA.xlsx` est identique dans le fichier réel,
  `project_metrics.json` et le dictionnaire. Septième suspicion vérifiée et
  écartée.
- **« cinq figures » sur `/api/kpi`** : `summary()` en rend quatre,
  `api/main.py` ajoute `flag_rate` — **cinq**. Le runbook, le README et le
  rapport disent tous cinq. Exact.
- La fenêtre de référence à 40 %, les 600 000 itérations PBKDF2, les cinq
  tentatives, le registre en droits 600 : conformes au code lu en S13.

### S34-6 — La commande de lancement : recensement clos

Après S31, S33 et ce lot, **les quatre documents qui prescrivaient
`uvicorn api.main:app` ont adopté `python -m api`**. Les occurrences restantes
sont des mentions explicatives — « ce document écrivait auparavant », « reste
utilisable en développement ». Le module écrit pour supprimer trois sources de
vérité concurrentes est enfin celui que la documentation désigne.

## Lot S35 — la page du poste (586 lignes lues intégralement)

`api/dashboard.html`, confrontée aux 2 407 lignes d'`app.js` lues en S23.

### S35-0 — Le câblage est complet : 98 identifiants cherchés, aucun manquant

C'est le contrôle que la phase F2 réclamait, et il est **vert** : chaque
`$("id")` d'`app.js` et de `twin.js` correspond à un élément de la page.

| | |
|---|---|
| identifiants dans la page | 110 |
| cherchés par le poste | **99** |
| **manquants** | **aucun** |

Un identifiant manquant produirait la panne d'interface la plus silencieuse
qui soit — `getElementById` rend `null`, le panneau ne s'affiche pas, aucune
erreur n'apparaît. **Verrouillé** par
`test_tout_identifiant_cherche_par_le_poste_existe_dans_la_page`.

Le sens inverse n'est **pas** verrouillé, et c'est délibéré : cinq identifiants
existent sans être atteints — `shell`, `who`, `friezeTrack` (ancrages de mise
en page), `benchReading` (texte statique). Exiger l'égalité stricte
transformerait un point d'accroche CSS en défaut.

### S35-1 — Deux affirmations contradictoires sur le tout premier écran

Le cinquième orphelin n'en était pas un. `gateAlertNote` porte :

> « **Cette adresse recevra les états critiques.** Chaque décision de sévérité
> critique retenue par le contrôleur déclenche un courriel dédoublonné vers le
> technicien connecté. »

`setGateMode(secured)` masque `passwordField` et révèle `gateDisclaimer` quand
l'accès n'est pas protégé — **mais ne touche jamais `gateAlertNote`**. Sur un
poste sans authentification, l'écran affiche donc simultanément :

| élément | ce qu'il dit |
|---|---|
| `gateAlertNote` | « cette adresse recevra les états critiques » |
| `gateDisclaimer` | « cette identification est **déclarative** » |

**C'est le second qui a raison.** La branche déclarative de `login()` ne fait
aucun appel serveur (S23-3) : `add_recipient` n'est jamais appelé, et l'adresse
ne reçoit rien.

Le défaut compose avec S23-3 et le rend plus lourd que je ne l'avais écrit. Je
notais alors que la prise de quart « ne trace rien » ; **elle promet en plus une
escalade qui n'aura pas lieu**, sur l'écran que le technicien voit avant tous
les autres. Deux promesses fausses, côte à côte, à l'entrée du poste.

`gateAlertNote` suit désormais le même sort que `passwordField` : visible
seulement quand l'accès protégé est actif — c'est-à-dire quand elle est vraie.

### S35-2 — Troisième occurrence de la même faute d'accord

« la règle ne se déclenche sur **aucune** des quatorze mois » — corrigée dans le
README en S32, présente à l'identique dans la page. Le texte a manifestement été
copié d'un document à l'autre, la correction non.

### S35-3 — Ce que la page fait remarquablement bien

- **Chaque commentaire HTML dit quel défaut il corrige** : l'onglet vide
  (`data:,`), la coque à opacité nulle pendant le démarrage, les deux textes de
  pied de scène qui se chevauchaient, les dimensions intrinsèques de la
  photographie qui déplaçaient les tableaux.
- La **photographie de la plaque tubulaire cite sa source** — gamme OCP
  FO09-PSS01-IDS/C — au lieu de passer pour une image de banque.
- La **légende de provenance AMDEC** est présente : sans elle, le marqueur
  serait un ornement.
- Le **menu Signaux publie les dix familles**, les quatre du diagnostic en tête
  — ce que le rapport § 12.2 ignorait encore avant S26-5.
- Le panneau de score explique **pourquoi** il met en avant l'écart plutôt que
  le taux de détection : « un contrôle qui ne rate jamais rien ne contrôle
  rien ».

### État de la lecture

Il ne reste que `twin.js` (2 167 lignes) côté front, une quinzaine de fichiers
de tests, et le notebook.

## Lot S36 — topologie et sensibilité (256 lignes lues intégralement)

`tests/test_topology.py` (109) · `tests/test_sensitivity.py` (147)

### S36-1 — Le contrôle de couverture des codes en manquait un, et le compte fautif avait essaimé

`test_tous_les_codes_du_detecteur_sont_couverts` cherchait
`code="([A-Z_]+)"`. Or `detector.py` écrit :

```python
code="MODEL_ANOMALY" if persistent else "MODEL_ANOMALY_ISOLATED",
```

**Le second membre de la conditionnelle n'était jamais confronté à la table.**
Mesuré : le motif voit **17** codes, le détecteur en émet **18**.

Sans conséquence aujourd'hui — `MODEL_ANOMALY_ISOLATED` figure bien dans
`finding_map`, vérifié — mais le test promet qu'« un code émis sans entrée
passerait inaperçu », et pour celui-là c'était exactement l'inverse.

**Et le compte fautif s'était propagé dans la documentation.** Mesure complète :

| | |
|---|---|
| codes émis par le détecteur | **18** — tous rattachés, aucun orphelin |
| dont règles déterministes | 15, produits par **6 méthodes** `_rule_*` |
| dont étage statistique | 3 |

| document | ce qu'il annonçait | mesure |
|---|---|---|
| README | « chacun des **dix-sept** codes du détecteur » | **18** |
| ADR-003 | « **Dix-sept** règles déterministes » | **6 règles**, 15 codes |

« Dix-sept » n'est juste sous aucune lecture — ni les codes, ni les règles, ni
les méthodes. Les deux documents ont vraisemblablement recopié le chiffre que
ce test produisait. **Un contrôle qui compte mal ne se contente pas de manquer
sa cible : il devient une source citée.**

Corrigé aux trois endroits, et le test **exige désormais un minimum de 18 codes
lus** — sans quoi il signale que son propre motif a cessé de suivre le code.

### S36-2 — Un chemin relatif, troisième variante du piège ENV-1

```python
source = Path("src/models/detector.py").read_text(encoding="utf-8")
```

Tous les autres contrôles par analyse de source du dépôt partent de
`Path(__file__).resolve().parents[1]`. Celui-ci dépendait du **répertoire
courant** : il passe lancé depuis la racine — ce que fait le propriétaire — et
lève `FileNotFoundError` lancé depuis `tests/`.

C'est le piège d'ENV-1 (« le test décrit la machine, pas le système »)
transposé à l'invocation, après le `.env` du poste et le registre d'opérateurs.

### S36-3 — Vérifié, sans constat

- **`test_sensitivity.py`** est exemplaire. Son
  `test_le_rapport_est_serialisable` porte la trace d'une correction rare : il
  appelait `json.dumps` **sans rien affirmer** — « sérialisable et non vide sont
  deux propriétés distinctes ; seule la première était couverte, et elle l'était
  par accident ». Et
  `test_la_periode_de_reference_change_la_conclusion` documente qu'il
  verrouillait *deux formes verbales, pas une propriété*, puis exige désormais
  la famille lexicale **et** l'absence d'abstention. C'est exactement la
  distinction fond/forme que ce travail cherche partout.
- **`test_topology.py`** verrouille les bonnes propriétés : un code inconnu ne
  désigne rien, l'anode non instrumentée est déclarée avec sa criticité 112, et
  les douze capteurs sont tous situés.

## Lot S37 — indicateurs et domaine (396 lignes lues intégralement)

`tests/test_kpi.py` (191) · `tests/test_domain.py` (205)

### S37-1 — Le « 5 épisodes/mois » avait laissé deux traces de plus

Après le README, le rapport et ADR-003 (S32-1), la valeur périmée subsistait
dans deux fichiers de tests :

- **`test_kpi.py`**, dans la docstring du contrôle qui verrouille
  `evidence_level` : « le ~5 épisodes par mois cité ailleurs dans le projet est
  un résultat de modèle, pas un comptage ». La qualification était juste, la
  valeur non.
- **`test_documentation.py`**, dans le commentaire qui explique pourquoi le
  motif « épisodes » a été restreint : il écartait « 5 épisodes/mois » en la
  qualifiant explicitement **« une autre grandeur, juste »**.

**Ce second cas est le plus instructif de tout ce travail sur les chiffres.**
Le fichier qui arbitre les valeurs publiées croisait la mauvaise, l'écartait de
son motif — décision correcte, ce n'est pas la même grandeur — et **la déclarait
juste au passage**. Écarter une valeur d'un contrôle n'est pas la vérifier ; la
qualifier de juste sans la mesurer lui a donné vingt lots de survie, dans quatre
documents.

Les deux sont corrigés, et le terme « charge d'alertes » ajouté en S32-1
confronte désormais la valeur à l'artefact.

### S37-2 — Où le verrou de S34-4 devra vivre

`test_domain.py:25` déclare `VALID_BASES = {isa_5_1, process, data, stoichio,
climatology}` et exige `bases <= VALID_BASES`. Le contrôle vérifie donc qu'aucune
base **inconnue** n'apparaît — jamais qu'une base déclarée soit **utilisée**.

C'est exactement l'asymétrie que `test_tout_statut_de_promotion_declare_est_productible`
(S9-3 bis) et `test_tout_etat_declare_est_productible` (S17) ont fermée ailleurs.
Le verrou manquant est le symétrique :

```python
assert not VALID_BASES - bases_utilisees
```

**Il échouerait aujourd'hui** — `stoichio` n'est utilisé par aucun tag (S34-4) —
et je ne l'ajoute donc pas : un test rouge ajouté sciemment ne verrouille rien,
il masque une décision non prise. La décision reste celle de S34-4 : inscrire
`stoichio` au `basis` de `LOAD_SULFUR`, dont le rapport § 2.2 fait explicitement
l'argument stœchiométrique, ou retirer la valeur du `Literal`. **Le verrou
s'écrit une ligne après.**

### S37-3 — Vérifié, sans constat

- `test_kpi.py` couvre les deux natures d'`evidence_level` par analyse du
  source, et son commentaire explique pourquoi `threshold` est **exclu** de la
  liste des marqueurs : le mot désigne deux choses opposées — le seuil appris du
  détecteur et `Tag.threshold("alarm_low")`, qui lit le référentiel. « Un
  contrôle qui produit un faux positif sur une figure correcte sera désactivé au
  premier échec. » C'est le raisonnement le plus fin de la suite.
- `test_domain.py` verrouille C = F × G × N, l'ordre des seuils, l'inclusion des
  plages, la conservation des cotations OCP d'origine, et le fait que tout angle
  mort porte une couverture préventive. Douze tags, deux bases minimum chacun,
  six tags de périmètre ancrés sur la physique — conformes à la mesure de S34.
- `test_le_niveau_de_preuve_est_declare_pour_chaque_indicateur` confirme
  `corrosion_exposure = observed`, ce qui valide la correction S26-4 du § 10.5
  du rapport.

## Lot S38 — ingestion et banc d'encrassement (403 lignes lues intégralement)

`tests/test_ingest.py` (190) · `tests/test_fouling_injection.py` (213)

### S38-1 — Une union masquait une décision de causalité (et mon assertion était fausse)

```python
assert "TRANSIENT" in set(state.iloc[95:105]) | set(state.iloc[148:158])
```

La phrase au-dessus dit « les instants **encadrant** un arrêt doivent être
marqués TRANSIENT ». L'union rend **une seule** des deux bornes suffisante.

Et les deux ne viennent pas du même critère : l'entrée en arrêt procède du seuil
de charge, la reprise procède de `is_down.shift(1)` — un critère ajouté plus
tard, et que S2-2 a dû inscrire dans `process_states` parce qu'il n'y figurait
pas. **J'ai donc scindé l'assertion en deux — et la moitié « entrée » a échoué.**

La lecture de `classify_process_state` donne la raison, et c'est le code qui a
raison :

```python
state[is_trans & ~is_down] = "TRANSIENT"
state[is_down]            = "STOPPED"
```

Sur une chute instantanée, l'instant où la charge tombe est **déjà** `is_down`,
donc STOPPED. Le marquer transitoire exigerait `is_down.shift(-1)` — « l'instant
t est transitoire parce que la ligne s'arrête en t+1 » — c'est-à-dire **la
lecture du futur que `dcs_loader` documente avoir supprimée**, sur vingt-sept
horodatages, « parce qu'une chaîne de détection ne peut pas être à demi
causale ».

**Cinquième fois que j'affirme une propriété sans avoir lu le code qui la
produit.** Mais l'erreur a été productive : l'union rendait le test vrai sans
rien garantir, et c'est en la scindant que la décision de causalité est
redevenue visible.

Le contrôle verrouille désormais **trois** propriétés, toutes vérifiées contre
la logique réelle :

| propriété | attendu | mesuré |
|---|---|---|
| reprise après arrêt | TRANSIENT | ✔ |
| entrée sur chute instantanée | **jamais** TRANSIENT | ✔ — que du RUNNING |
| descente progressive > 2 t/h en marche | TRANSIENT | ✔ |

La troisième est nouvelle : elle éprouve `transient_rate`, le seul critère
transitoire réellement causal, qu'aucun test n'atteignait.

### S38-2 — Un `if` rendait un contrôle facultatif, troisième fichier

```python
if len(par_severite) >= 2:
    assert fort <= faible + 1e-9
```

Sans deux scénarios détectés, l'assertion ne s'exécute pas et le test passe en
n'ayant rien comparé. **Or c'est précisément quand la détection faiblit — donc
quand un seul cas est vu — que la monotonie mérite d'être examinée.**

C'est la troisième fois que ce motif apparaît, après les quatre contrôles de
`test_agents_judge.py` (S24-1). Le dépôt porte pourtant la doctrine, écrite dans
`test_typographie._exiger` : *un contrôle qui réussit d'autant plus sûrement
qu'il ne lit rien ne contrôle rien.* Corrigé par `pytest.skip`, qui **déclare**
l'absence de matière au lieu de rendre un vert silencieux.

### S38-3 — Signalé, non corrigé

`test_la_detection_est_tardive_et_le_projet_le_dit` porte :

```python
assert result.detection_rate > result.useful_detection_rate or (
    result.useful_detection_rate == result.detection_rate == 1.0
)
```

La seconde branche satisfait l'assertion dès que les deux taux valent 1,0 —
c'est-à-dire quand la détection devient parfaite **et** utile. La docstring dit
que ce test « fige ce constat pour empêcher de présenter le taux brut comme une
performance » : dans ce cas-là, il ne fige plus rien.

**Je ne le corrige pas** : l'échappatoire peut être délibérée — un détecteur
devenu réellement bon ne doit pas faire échouer une suite. Trancher demande de
savoir si l'on veut alors un `skip`, un avertissement, ou l'acceptation
silencieuse. C'est une décision, pas une correction.

### S38-4 — Ce que ces deux fichiers font remarquablement bien

- **`test_gel_detecte_sur_signal_constant`** documente qu'il affirmait
  auparavant **le contraire** du comportement voulu : il exigeait un marquage
  rétroactif de tout le palier, « décidé avec une information que le système n'a
  pas encore ». Il vérifie désormais la causalité — rien avant le seuil, tout
  après. C'est le même raisonnement que S14-1, appliqué à l'ingestion.
- **`test_le_predicat_du_banc_equivaut_a_la_regle`** est un « test que le code
  prétendait avoir » qui a été **écrit** : `_fouling_hours` affirmait qu'un test
  verrouillait son équivalence avec `_rule_thermal_drift`, et il n'existait pas.
  Il compare maintenant les deux prédicats sur un échantillon déterministe.
- **`test_le_temoin_mesure_les_declenchements_sans_faute`** remplace un
  `0 <= taux <= 1` — que son commentaire appelle « une tautologie » — par une
  exigence de **niveau**, avec le motif : un témoin bruyant rendrait toute
  détection inattribuable.
- **`test_les_limites_sont_declarees`** exige que le banc déclare être
  **favorable** — il ne simule pas la compensation par la vanne d'eau de mer,
  donc il est optimiste. Un banc qui déclare son propre biais est rare.

## Lot S39 — le notebook d'analyse (29 cellules lues intégralement)

`notebooks/01_analyse_E7301.ipynb` — jamais lu par cet audit, et pièce centrale
de l'objectif F4 : **comprendre le projet, pas seulement le livrer.**

### S39-1 — Deux sections numérotées 5, et la huitième absente du sommaire

| sommaire | sections réelles |
|---|---|
| 7 questions annoncées | **8 sections** |
| — | **deux portaient le numéro 5** : « Ce qui débloque tout » et « Que détecte le système » |

Conséquence : tout ce qui suit la section 5 est décalé par rapport au sommaire,
et **la huitième section n'y figure pas du tout**. Or c'est « Ce que le système
ne voit pas » — les angles morts, c'est-à-dire la section qui porte l'honnêteté
du projet, celle dont le rapport, le README, ADR-008 et le poste font tous un
argument central. **Un lecteur qui suit le sommaire ne sait pas qu'elle existe.**

Renumérotée, et la huitième question ajoutée au sommaire : « Que ne voit-il
PAS, et pourquoi faut-il le dire ? »

### S39-2 — Cinquième document portant une charge d'alertes fausse

> « Un exploitant ne traite pas 530 points d'alarme, il traite **une dizaine
> d'événements par mois**. »

La mesure est **4,1** (S32-1). « Une dizaine » sur-estime de 2,4 fois — plus
encore que le « ~5 » corrigé dans le README, le rapport, ADR-003, `test_kpi` et
`test_documentation`. **Cinquième support, cinquième formulation différente**,
et c'est cette variété qui a permis au chiffre de survivre : aucun motif ne les
attrape tous.

Le passage dit désormais la valeur **et sa nature** — dérivée, pas observée —
avec la formule qui la produit. C'est un notebook d'apprentissage : y écrire
d'où vient un chiffre vaut mieux que de l'y écrire juste.

### S39-3 — Un chemin relatif qui suppose le répertoire de lancement

```python
sys.path.insert(0, "..")
```

Le notebook ne s'importe que si le noyau démarre dans `notebooks/`. Ouvert
depuis la racine — ce que fait n'importe quel éditeur moderne — **aucun import
du projet ne résout**, et l'utilisateur voit une pile d'erreurs sans rapport
avec le sujet. Troisième variante du piège ENV-1, après le `.env` du poste et
le chemin relatif de `test_topology` (S36-2). Le chemin remonte désormais depuis
l'emplacement réel.

### S39-4 — Ce que le notebook fait déjà très bien

- Il **ne trace pas des courbes** : chaque section répond à une question qui a
  décidé d'un choix technique. C'est exactement la forme que F4 doit prolonger.
- La cellule des tags porte **le constat de S34-3 avant que je le trouve** :
  « `Tag.confidence` a gardé son nom en changeant de sens […] `confirmed` /
  `inferred` / `unknown`, valeurs qui n'existent plus ». Le notebook était à jour
  là où le dictionnaire gouverné ne l'était pas.
- La section 4 mesure l'apport réel du modèle — `effort.r2 - effort.naive_r2` —
  **calculé, jamais recopié**. C'est la règle que F4 doit tenir partout.
- Aucune sortie n'est enregistrée, conformément à `make notebook-clean`.

### S39-5 — Ce qui reste à écrire pour F4

Le notebook 01 couvre la démonstration. L'objectif du propriétaire est
**l'apprentissage**, et deux sujets manquent — ce sont les deux plus difficiles
du dossier, et ceux qu'un jury interrogera :

1. **Pourquoi le PSI de 3,18 ne mesure pas une dérive** : la correspondance
   parfaite entre extrapolation saisonnière et PSI (S12-1) se démontre en une
   cellule, et elle explique la seule porte que le projet ne peut pas franchir ;
2. **Pourquoi le taux de généralisation vaut 8,6 % et pas 95,8 %** : la
   différence entre un piège conçu contre un contrôle et une mutation qui n'en
   vise aucun (S27).

Le découpage complet est dans `docs/audits/OBJECTIFS-FINAUX.md`.

## Lot S40 — les portes du manifeste (233 lignes lues intégralement)

`tests/test_model_governance.py` — fichier auquel **j'avais ajouté un test en
S12 sans l'avoir lu**. La lecture confirme cette fois qu'il n'y avait pas de
doublon, contrairement à `test_redaction_gouvernance` (S29-5).

### S40-1 — La décision de gouvernance la plus délicate n'était verrouillée nulle part

Les phases 0.6 et 0.7 ont scindé deux portes. `redondance_hors_modele` et
`derive_de_distribution` sont désormais **publiées, en échec, et hors de
`MANDATORY_GATES`** — parce qu'aucun commit ne peut les franchir : la première
est une propriété algébrique d'ADR-001, la seconde n'est interprétable sur aucun
pli de ce corpus (S21-3).

Le journal s'en inquiétait explicitement, et c'est l'une des trois leçons de la
phase 0 : restreindre un critère « pour qu'il puisse passer » **remasque** ce
que l'auteur avait délibérément rendu visible.

**Cette parade n'était vérifiée par aucun test.** `_validation()` ne construit
que les cinq portes obligatoires, et le seul contrôle d'échec les fait **toutes**
échouer ensemble. Deux régressions symétriques passaient donc inaperçues :

| régression | conséquence |
|---|---|
| ajouter une des deux portes à `MANDATORY_GATES` | la promotion devient impossible **par construction**, et rien ne dit pourquoi |
| retirer une porte obligatoire | un artefact est promu à tort |

Le nouveau contrôle construit le cas **réel de production** — cinq portes
obligatoires franchies, deux portes publiées en échec — et vérifie que le
manifeste est accepté de bout en bout. **Preuve par mutation** : ajouter l'une
des deux à `MANDATORY_GATES` le fait échouer.

### S40-2 — Un résidu que j'avais introduit en S12

En ajoutant `test_les_portes_publiees_ont_toutes_un_intitule_a_l_ecran`, j'avais
hissé `ast`, `re` et `Path` au niveau du module. Le test voisin réimportait
`ast` et `Path` dans son corps, et reconstruisait la racine par
`Path(lineage.__file__).resolve().parents[2]` alors que `RACINE` existait
désormais trois lignes plus haut.

Deux chemins vers la même racine, dont l'un passe par le module audité — le
genre de doublon que ce travail retire partout. Nettoyé.

### S40-3 — Vérifié, sans constat

`_validation()` construit exactement les cinq portes de `MANDATORY_GATES` :
c'est cohérent, et la note de la phase 0.6 — « `test_model_governance.py` n'est
pas affecté : il construit son propre bloc de cinq portes » — reste vraie. Le
fichier verrouille correctement le refus d'un `candidate`, le blocage sur portes
en échec, l'empreinte du modèle et l'ordre des variables.

### Ce qui reste

`api/static/twin.js` (2 167 l.), huit fichiers de tests dont `test_api.py`
(1 043) et `test_features_detector.py` (860), et mon propre `test_replay.py`
(124) que je n'ai pas relu depuis S14.

## Lot S41 — relecture de mon propre test (124 lignes lues intégralement)

`tests/test_replay.py`, écrit par cet audit en S14 et jamais relu.

### S41-1 — J'avais écrit une tautologie, et c'est la règle 4 que j'ai enfreinte

`test_les_instants_a_franchissement_ne_sont_jamais_sautes` calculait :

```python
ordinaires = set(index[::pas])
rejoues    = set(index[index.isin(ordinaires | obligatoires)])
assert not (obligatoires & set(index)) - rejoues
```

Il **réimplémentait la sélection de `run_sync`**, puis vérifiait sa propre
réimplémentation. `isin` garantit par construction que tout élément
d'`obligatoires` présent dans l'index se retrouve dans `rejoues` : **l'assertion
ne pouvait pas échouer, quel que soit le code du rejeu.** Démontré sur un index
synthétique — le résultat est vide en toutes circonstances.

C'est la **règle 4 de la méthode** — *ne réimplémente pas pour tester, importe le
prédicat réel* — enfreinte par le test censé la servir. Et c'est ma sixième
erreur de cette session, la plus instructive : les cinq précédentes étaient des
affirmations sur du code non lu ; celle-ci est un test **vert qui ne teste
rien**, écrit en toute bonne foi pour combler l'absence de tests de `replay.py`.

**Combler un trou avec un contrôle vide, c'est le refermer sans rien y mettre.**

Le contrôle passe désormais par `run_sync` — donc par le vrai chemin de
sélection — sur un franchissement dont la position n'est **pas** multiple du pas
d'allègement, c'est-à-dire exactement le cas que la décimation faisait
disparaître. Rejeu borné à six instants pour rester rapide.

*Deux nettoyages au passage : un paramètre `combien` inerte — la liste étant
construite à trois éléments avant d'être tronquée à `combien` — et une assertion
nue sans message, seule du fichier.*

### S41-2 — Ce que cette relecture confirme sur la méthode

Le propriétaire a exigé sept fois la lecture intégrale. Sur ce lot, elle
s'applique à **mon propre code**, et elle trouve un défaut qu'aucune exécution
n'aurait révélé : un test qui passe toujours passe aussi quand il est faux.

Le compte des erreurs de cet audit, tenu à jour :

| # | lot | nature |
|---|---|---|
| 1 | S21-2 | calcul d'extrapolation sur le calendrier au lieu des heures de marche |
| 2 | S23-6 | nom de classe inféré, présent 435 lignes plus haut |
| 3 | S25-1 | contenu du rapport affirmé sans l'avoir lu |
| 4 | S29-5 | prédicat de forme, et deux tests ajoutés à un fichier non lu |
| 5 | S38-1 | symétrie affirmée contre une décision de causalité documentée |
| 6 | **S41-1** | **tautologie : un test vert qui ne testait rien** |

Les six ont la même cause — conclure avant d'avoir lu — et les six ont été
trouvées par la lecture, jamais par l'exécution.

### S41-3 — Et le test corrigé était faux à son tour : septième erreur

Le remplacement de la tautologie a échoué au premier lancement, en accusant le
rejeu d'avoir sauté le franchissement du 15/01/2024 15:00. **Le rejeu l'avait
analysé.**

```
str(pd.Timestamp)         : '2024-01-15 15:00:00'
DetectionResult.timestamp : '2024-01-15T15:00:00'   ← ISO 8601, dit par la docstring
égalité de chaînes        : False
```

Je comparais **deux écritures du même instant**. `DetectionResult.timestamp`
est déclaré « ISO 8601 » dans sa propre docstring — je ne l'avais pas lue.

C'est le piège que `sans_accents` traite pour le texte, transposé aux dates :
**un contrôle qui compare des représentations mesure la mise en forme, pas le
fond.** Le dépôt a la règle, écrite dans ADR-011 et appliquée douze fois ; je ne
l'ai pas appliquée aux horodatages. Les deux côtés passent désormais par
`pd.Timestamp`.

**Ce que cet enchaînement enseigne, et qui vaut d'être gardé.** La tautologie de
S41-1 était verte : elle n'aurait jamais rien signalé. En la remplaçant par un
contrôle qui éprouve le vrai chemin, j'ai immédiatement produit un **faux
positif** — le test accusait un code correct. Les deux défauts sont opposés et
ont la même racine :

| | ce que le test faisait | ce qu'il aurait fallu |
|---|---|---|
| S41-1 | vérifier sa propre réimplémentation | appeler le code réel |
| S41-3 | comparer deux formats | comparer deux instants |

**Un test qui ne peut pas échouer et un test qui échoue à tort sont le même
défaut** : dans les deux cas, ce qu'il mesure n'est pas ce qu'il annonce.

| # | lot | nature |
|---|---|---|
| 7 | **S41-3** | **comparaison de représentations au lieu de valeurs** |

## Lot S42 — `tests/test_alarm_store.py` lu intégralement (291 lignes)

Dernier fichier auquel j'avais ajouté du code (S22, clôture d'AL-1) sans
l'avoir lu en entier. La relecture en a montré la conséquence.

### S42-1 — le sentinelle du constructeur masquait le chemin le plus fréquent

```python
lead_finding=lead if lead is not None else finding    # avant
```

`lead=None` signifiait « prends `finding` ». **Aucun appel du fichier ne pouvait
donc produire une décision dont `lead_finding` vaut vraiment `None`.**

Or c'est le cas NOMINAL en production — `detection_agent.py:376` :

```python
evidence_refs=[f.code for f in result.findings],
lead_finding=None,
```

des constatations non vides, aucune dominante. `_trigger` retombe alors sur
`findings[0]`, c'est-à-dire sur **l'ordre d'évaluation des règles** — le défaut
exact qu'AL-1 corrige. Les deux tests d'AL-1 passent la dominante explicitement :
ils vérifient la branche corrigée et **jamais le repli**, qui est pourtant le
chemin le plus emprunté du système.

Sentinelle remplacé par `_DEFAUT = object()`, qui ne peut entrer en collision
avec aucune valeur du domaine. Nouveau test `test_sans_dominante_l_alarme_
retombe_sur_l_ordre_des_regles` : le repli est désormais **atteignable et
verrouillé**.

**Le motif est celui de S41-3, un cran plus haut.** Là je comparais deux
écritures d'un instant ; ici le constructeur confond « non fourni » et « fourni
à None ». Dans les deux cas **une distinction du domaine est écrasée par une
commodité d'écriture**, et ce qui disparaît est précisément le cas intéressant.
C'est aussi la troisième forme du même interdit : `x or defaut`, `if limit:`,
`if lead:` — le dépôt a la règle et l'énonce dans `knowledge.seuil`.

### S42-2 — `if lead:` dans `_trigger`

L'idiome banni, sur un champ déclaré `str | None`. Corrigé en `is not None`,
comme `run_sync` sur `limit` en S14. Sans conséquence mesurable aujourd'hui
(aucun producteur n'émet `""`), mais c'est la règle nommée du dépôt.

### S42-3 — cosmétique

`__import__("pytest").raises(...)` ligne 93 et un `import pytest` en corps de
fonction ligne 132, faute d'import au module. Remontés en tête.

### AL-4 — ouvert, pour l'auteur

Faut-il que le chemin nominal de `detection_agent` désigne lui aussi une
dominante, plutôt que de laisser le registre retomber sur l'ordre des règles ?
Ce n'est pas une décision de test et je ne la prends pas. Elle rejoint AL-3
(une alarme dont la condition cesse sans réémission ne se résout jamais).

## Lot S43 — `tests/test_workflows.py` lu intégralement (312 lignes)

### S43-1 — un nom plus large que la couverture, sur le test de WF-3

`test_le_schema_derive_son_vocabulaire_des_constantes` annonce une DÉRIVATION,
donc une **égalité**. Il vérifiait :

```python
for etat in WORKFLOW_STATES:
    assert f"'{etat}'" in schema          # inclusion, un seul sens
assert "'CANCELLED'" not in schema        # l'intrus, nommé
```

soit une inclusion et l'absence d'**un seul intrus désigné par son nom**. Un état
ajouté au seul littéral SQL — ou une seconde valeur morte, `ABORTED`, `ON_HOLD` —
passait sans bruit. C'est précisément la divergence Python/SQL que WF-3 prétend
avoir refermée, et le test censé la verrouiller la laissait ouverte dans un sens.

La contrainte `CHECK(status IN (...))` est désormais extraite et comparée par
**égalité d'ensembles**. Cela subsume le cas `CANCELLED` au lieu de le nommer :
le contrôle porte sur la propriété, non sur l'exemple qui l'a fait découvrir.

**Troisième occurrence de ce motif précis** — après `test_les_identifiants_
internes_sont_traduits` (S29-5, 3 vocabulaires sur 5) et la moitié « entrée » de
S38-1. Le motif se dit simplement : *un test qui interdit le défaut connu n'interdit
pas sa famille.* On corrige le cas rencontré, on nomme le test d'après la règle,
et l'écart entre les deux ne se voit plus jamais.

Reste que ce fichier est, à ce jour, le mieux tenu de la suite : WF-1, WF-2 et
WF-4 sont éprouvés par l'API publique, et `test_tout_etat_declare_est_productible`
est déjà bidirectionnel — c'est même lui qui donne la forme juste appliquée ici.

## Lot S44 — `tests/test_access_notifications.py` lu intégralement (332 lignes)

### S44-1 — une égalité qui gelait une absence

`test_session_opaque_csrf_et_invalidation` appelle `rotate()` puis `destroy()`,
et finit par :

```python
assert [event["event"] for event in manager.audit_events()] == [
    "LOGIN_FAILED", "LOGIN_SUCCEEDED",
]
```

L'égalité porte sur le journal **entier**, après ces deux opérations. Elle gèle
donc l'**absence de toute trace** pour la rotation et la destruction de session :
qui ajoute une ligne de déconnexion casse ce test, avec un message qui n'en dit
pas la raison.

Mesuré : `src/security/auth.py` ne contient **qu'un seul** `self._audit.append`,
ligne 222, atteint depuis `authenticate` seul. `rotate()` et `destroy()`
n'inscrivent rien.

L'exactitude est conservée sur ce que le test dit examiner — les deux issues
d'authentification, dans l'ordre — et ne s'étend plus au reste du journal.

**Même famille que S43-1, sens inverse.** Là une assertion était plus étroite que
son nom ; ici elle est plus large que son objet. Dans les deux cas la portée de
l'assertion et celle de l'intention ne coïncident pas — et c'est toujours le
même prix : le test devient un obstacle à la correction qu'il devrait appeler.

### SEC-3 — ouvert, pour l'auteur

Faut-il consigner la fin de session (déconnexion, expiration, rotation) au
journal d'audit ? Un exploitant qui enquête sur un accès veut savoir quand la
session s'est terminée, et `/api/auth/audit` est le seul endroit qui pourrait le
dire. Je ne tranche pas : c'est une décision de périmètre, pas de test. À joindre
à AL-3, AL-4 et aux quatre décisions déjà en attente.

## Lot S45 — `tests/test_service_invariants.py` lu intégralement (389 lignes)

Le meilleur fichier du dépôt : « le patron » appliqué systématiquement, onze
invariants vérifiés par AST sans démarrer le service. Il porte quand même le motif.

### S45-1 — trois codes nommés, deux vérifiés, et par comparaison de chaînes

`test_les_en_tetes_de_securite_sont_poses_en_un_seul_endroit` :

```python
for chemin in ("_durcir(\n            JSONResponse(\n                status_code=401",
               "_durcir(\n            JSONResponse(\n                status_code=403"):
    assert chemin in source, "un refus ne passe plus par `_durcir`"
```

Sa docstring nomme « LES REFUS **401, 403 ET 500** ». Le **500 n'était pas
vérifié** — et c'est le seul des trois qu'un attaquant obtient sans authentification.

Pire que la lacune : la comparaison porte sur **l'indentation exacte**, 12 puis
16 espaces. Un `ruff format` la casse, et le message d'échec annonce alors « un
refus ne passe plus par `_durcir` » — **ce qui serait faux**.

> **Un contrôle dont le message ment quand il échoue est pire qu'absent :** il
> envoie corriger un défaut qui n'existe pas, et le vrai reste.

Remplacé par la propriété générale, en AST : *toute `JSONResponse` portant un code
d'erreur littéral doit être enveloppée par `_durcir`*. Elle subsume les trois
exemples et couvrira tout refus ajouté demain. Mesuré sur `api/main.py` :
**aucune réponse d'erreur non durcie ; codes durcis = {401, 403, 500}**.

**Quatrième occurrence du motif** — après S29-5, S43-1 et S44-1. Il se dit
maintenant sous sa forme complète :

| forme | exemple |
|---|---|
| assertion plus étroite que le nom | S29-5, S43-1, **S45-1** |
| assertion plus large que l'objet | S44-1 |
| assertion qui ne peut pas échouer | S41-1 |
| assertion qui échoue à tort | S41-3 |

Les quatre disent la même chose : **la portée de l'assertion et celle de
l'intention ne coïncident pas.** C'est le défaut de test le plus fréquent du
dépôt, loin devant l'absence de test.

Ce fichier en donne d'ailleurs lui-même le remède, deux fonctions plus bas :
`test_aucun_outil_de_qualite_declare_n_est_inerte` porte le commentaire « CE TEST
NE VERIFIAIT QUE DEUX TIERS DE SON PROPRE ENONCE » et a été élargi pour cette
raison exacte. L'auteur avait vu le motif sur un test et ne l'a pas cherché sur
son voisin.

### Faits relevés pour la bibliothèque

- **32 handlers sur 47** étaient `async def` sans `await` : leur corps entier
  s'exécutait sur la boucle d'événements unique — dont `auth_login` (PBKDF2,
  **600 000 itérations**) et `analyze` (appel au modèle de langage).
- Rejeu : valeurs par défaut **REPLAY_SPEED=120, REPLAY_STEP=3** ⇒ défilement
  réel **40 h/s** pendant que l'API publiait 120.
- **6 en-têtes de sécurité**, posés en un seul endroit (`_durcir`).
- `fit()` doit appeler `invalidate_cache()` : la clé de `score_series` ne décrit
  que les données, jamais le modèle.
- **84 vérifications** des bancs du poste ; CI : `frontend_smoke.mjs`,
  `twin_smoke.mjs`, `boot_smoke.mjs`, avec `needs: [qualite, tests, frontend]`.

### API-2 — ouvert

Six `JSONResponse` ne passent pas par `_durcir`, dont deux qui peuvent rendre
**503** (`200 if ready else 503`, lignes 699 et 761 — sondes de disponibilité).
Ce sont des sondes, pas des refus : faut-il les durcir aussi ? Décision de
périmètre, laissée à l'auteur.

## Lot S46 — le garde documentaire attrape la bibliothèque neuve

`docs/BIBLIOTHEQUE-RAPPORT.md` (1 519 lignes, apportée par l'auteur) a fait
échouer deux contrôles de `test_documentation.py` **au premier lancement**.
C'est le meilleur résultat possible : le dispositif que ce dépôt s'est donné a
fonctionné sur un document qu'il n'avait jamais vu.

### S46-1 — « 2 000 points d'alarme » : la bibliothèque citait fidèlement une source fausse

`test_aucun_chiffre_cle_ne_contredit_les_artefacts` : « 2 000 » écrit, **530**
mesuré (`project_metrics.json → alert_hours_historical`).

**Le défaut n'est pas dans la bibliothèque.** Elle cite `src/models/detector.py:1236`
mot pour mot :

> « Un exploitant ne traite pas 2 000 points d'alarme : il traite une dizaine
> d'evenements. »

Les deux nombres sont faux : **530** heures atypiques, **58** épisodes. Presque
quatre fois trop pour le premier, un ordre de grandeur trop peu pour le second.

Et le commentaire du test raconte l'histoire complète : la phrase disait
auparavant « 511 points d'alarme », le jumeau de « 511 heures atypiques ». La
première occurrence a été corrigée, **la seconde a survécu en changeant de mot**
— « points d'alarme » au lieu de « heures atypiques » — puis quelqu'un l'a
« arrondie » à 2 000. Un chiffre faux corrigé en un chiffre plus faux.

**Exception au motif dominant, et elle l'éclaire.** Ma règle disait : *le code
servant porte la version juste, le document la version périmée*. Ici le code
porte la version fausse — mais dans un **commentaire**. Les commentaires sont de
la documentation qui habite le code : ils vieillissent comme des documents, pas
comme du code, parce que **rien ne les exécute**. La règle se reformule donc plus
justement : *ce qui est exécuté reste juste, ce qui est seulement lu dérive.*

Corrigé aux deux endroits.

### S46-2 — quatre chemins cités sans leur préfixe `src/`

`governance/model_validation.py`, `operations/alarms.py`, `realtime/replay.py`,
`security/auth.py` — tableau de synthèse en fin de bibliothèque. Aucun n'existe
sous cette forme. Corrigés, plus `email.py` / `redaction.py` qui échappaient au
contrôle faute de contenir une barre oblique (limite connue du prédicat, non
corrigée : elle ne produit pas de faux positif).

### Ce que cet épisode établit pour le rapport

Deux documents produits par deux sessions différentes, sans coordination, et
c'est **l'artefact mesuré** qui a tranché — pas le plus récent, pas le plus long,
pas le plus assuré. C'est exactement l'argument de la gouvernance du dépôt, et il
vaut mieux qu'une explication : **une démonstration en conditions réelles.**

### S46-3 — huitième erreur : j'ai cru un `print` plutôt qu'une vérification

Au lot S46 j'ai écrit `print("corrige aux trois endroits")` après un
`str.replace` sur trois cibles. **Une seule des trois avait matché** : mon motif
supposait une coupure de ligne (« il traite une \n dizaine ») que le fichier ne
portait pas (« il traite une dizaine \n d'événements »).

La preuve était **dans ma propre sortie**, deux lignes plus bas : le `grep` de
vérification ne rendait qu'un fichier au lieu de deux. Je ne l'ai pas lue.

> **Un `print` de fin de script n'est pas une vérification** : il atteste que le
> code s'est exécuté, jamais qu'il a fait quelque chose. `str.replace` ne lève
> pas quand il ne trouve rien — c'est le `x or defaut` de la manipulation de
> texte : l'échec silencieux prend l'apparence du succès.

Correctif de méthode appliqué immédiatement : tout remplacement passe désormais
par `assert motif in source` **avant** l'écriture, et la vérification relit le
fichier au lieu d'annoncer le résultat.

Huitième erreur, même cause que les sept autres : **conclure sans regarder**.
Sept ont été trouvées par la lecture ; celle-ci l'a été par l'exécution — la
première.

### S46-4 — ouvert : le prédicat des chemins a un angle mort

La bibliothèque cite une quinzaine de modules sans préfixe `src/`
(`models/detector.py`, `agents/judge_agent.py`, `domain/knowledge.py`…). Le test
ne les signale pas : son `motif` filtre en amont de la vérification d'existence.
Ce ne sont pas des faux positifs — ces chemins n'existent pas — mais élargir le
prédicat demande de le mesurer d'abord, sur les six documents concernés, pour ne
pas rendre le contrôle bruyant. À faire, pas à improviser en fin de session.
