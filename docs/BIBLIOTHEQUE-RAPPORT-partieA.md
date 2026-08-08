# Bibliothèque de référence E7301 — partie A

**Périmètre : la chaîne de production `src/`, lue intégralement.**

Ce document est la **moitié amont** d'une bibliothèque destinée à la rédaction
du mémoire. Il rassemble les faits, chiffres, définitions et raisonnements
établis par la lecture **intégrale** des fichiers listés ci-dessous. Une
seconde partie couvre l'interface, l'API, la validation du modèle, les alarmes,
le rejeu, les notifications et les tests ; les deux se complètent sans se
recouvrir.

## Fichiers couverts par cette partie — lus intégralement

| domaine | fichiers | lignes |
|---|---|---|
| Socle | `formatting.py`, `config.py`, `pipeline.py` | 981 |
| Domaine | `domain/knowledge.py` + les 3 YAML gouvernés | 849 |
| Ingestion | `ingest/dcs_loader.py` | 586 |
| Features | `features/thermal.py`, `features/e7301_features.py` | 1 218 |
| Détection | `models/detector.py` | 1 334 |
| Agents | `agents/detection_agent.py`, `agents/judge_agent.py` | 2 070 |
| Gouvernance | `judge_eval.py`, `fouling_injection.py`, `sensitivity.py`, `lineage.py`, `scripts/promote_model.py` | 1 928 |
| Analytique | `analytics/kpi.py` | 340 |
| Exploitation | `operations/workflows.py`, `security/registry.py` | 709 |

**Non couverts ici** : le front (`app.js`, `twin.js`, `dashboard.html`),
`api/main.py`, `governance/model_validation.py`, `operations/alarms.py`,
`notifications/`, `realtime/replay.py`, `security/auth.py`, la suite de tests,
le déploiement. Ils relèvent de la partie B.

## Convention de fiabilité — à conserver dans la fusion

Chaque affirmation porte un marqueur :

- **[LU]** — établi par lecture intégrale du fichier source. Le fait est dans
  le code, vérifiable à la ligne citée.
- **[DÉCLARÉ]** — le dépôt l'affirme (commentaire, docstring, référentiel) sans
  que je l'aie recalculé. Vrai selon le code, non revérifié par exécution.

**Aucun chiffre de ce document ne provient d'une exécution du système.** Le
`.venv` du dépôt est Windows et n'était pas accessible depuis l'environnement
d'audit. Les résultats marqués [DÉCLARÉ] doivent être confirmés par un run
avant d'être publiés comme mesures.

**Règle à tenir dans le rapport** : ne jamais citer un [DÉCLARÉ] comme une
mesure sans dire d'où il vient. C'est précisément le défaut que tout ce travail
a corrigé.

---

# 0. Le problème — ce que le rapport doit poser en ouverture

**[LU — synthèse des énoncés de `fouling_injection.py`, `kpi.py`, `amdec.yaml`,
`detector.py`]**

Un mémoire s'ouvre sur une question, pas sur une architecture. Voici la
question, telle que le dépôt la pose lui-même.

## 0.1 La situation

E7301 refroidit l'acide de séchage de la ligne PS III. Il est en service depuis
**novembre 2015**. Son AMDEC de 2019 recense **treize modes de défaillance**
pour une criticité totale de **1052**, dont les deux plus graves — plaque
sacrificielle et fuite de vanne d'acide, **112 chacun** — ne sont couverts par
**aucune mesure**.

L'exploitant dispose de deux choses : un **plan préventif à huit tâches**, dont
sept exigent l'arrêt process, et un **export DCS** de douze points de mesure.
Entre les deux, rien ne relie l'analyse de risque aux données.

## 0.2 Les trois questions auxquelles le système répond

Formulées dans `kpi.py` comme celles « que l'exploitant se pose réellement » :

1. **Mes mesures sont-elles disponibles ?** — deux capteurs sur douze sont morts
   depuis des mois, et personne ne l'avait chiffré.
2. **Combien d'événements ce système va-t-il me demander de traiter ?** — *« Un
   système qui génère plus d'alertes que l'équipe ne peut en traiter sera
   désactivé, quelle que soit sa performance statistique. »*
3. **Mon faisceau vieillit-il plus vite que prévu ?** — c'est-à-dire : quand
   programmer la prochaine mesure d'épaisseurs par courant de Foucault (tâche B,
   arrêt process, cadence 2 ans) ?

## 0.3 La difficulté centrale, et pourquoi elle n'est pas triviale

**La grandeur qu'on voudrait surveiller est régulée.** La température de sortie
acide est maintenue à 66 °C par une vanne d'eau de mer. Sa distribution réelle
sur 14 mois tient dans **3 °C** : P1 = 63,7 °C, P99 = 66,6 °C.

Conséquence : *« Un z-score sur ce signal ne détecte rien tant que la régulation
tient — et quand elle lâche, il est déjà trop tard. »*

C'est ce qui condamne l'approche générique — z-scores et statistiques
glissantes sur des capteurs quelconques — et c'est ce qui a conduit la v1 du
projet dans une impasse dont l'audit a dû la sortir.

## 0.4 La difficulté que personne ne peut lever

**Il n'existe aucune vérité terrain.** Pas d'historique GMAO, pas une seule
panne étiquetée sur les 14 mois. Cette absence a une conséquence directe et
irréductible :

> La règle d'encrassement ne s'est **jamais déclenchée** sur le corpus. Sans
> anomalie étiquetée, on ne peut pas distinguer trois situations :
> **(1)** il n'y a pas eu d'encrassement, **(2)** le détecteur est incapable de
> se déclencher, **(3)** l'indicateur ne mesure pas ce qu'on croit.

Présenter ce zéro comme un résultat serait **une inversion de la charge de la
preuve**. Tout le dispositif de gouvernance du projet — banc d'injection, banc
d'évaluation du contrôleur, analyse de sensibilité, portes de déploiement —
existe pour répondre à cette impossibilité sans la nier.

## 0.5 Ce que le projet revendique, et ce qu'il ne revendique pas

| revendiqué | **non** revendiqué |
|---|---|
| relier chaque alerte à une ligne de l'AMDEC de 2019 | prédire une panne |
| chiffrer ce que la surveillance par données couvre : **30,2 %** de la criticité | remplacer le plan préventif ou l'inspection |
| mesurer l'**avancement** auquel un encrassement simulé serait vu | garantir la détection d'un encrassement réel |
| rendre chaque diagnostic réfutable en citant ses valeurs | valider un diagnostic par la donnée terrain |
| publier la sensibilité des conclusions à ses propres choix arbitraires | prétendre que ces choix sont neutres |

# 1. L'équipement et son contexte

**[LU — `src/domain/tags.yaml`, `knowledge.briefing_equipment`]**

| | |
|---|---|
| Repère fonctionnel | **E7301** |
| Identifiant système | `S-PC-E7301` |
| Désignation | REFROIDISSEUR D'ACIDE DE SECHAGE |
| Constructeur | **CHEMETICS** |
| Taille | **1118-9754** |
| **Date de fabrication** | **2014-04-08** |
| **Mise en production** | **2015-11-01** |
| Atelier | PS III |
| Site | Maroc Chimie (Safi, côte atlantique marocaine) |
| Type | échangeur à faisceau tubulaire |
| Fluide calandre | acide sulfurique de séchage, ~98 % |
| Fluide tubes | **eau de mer** |
| Matériau tubes | **904L** (inox superausténitique) |
| Protection | plaques sacrificielles (protection anodique) |

**Âge de l'équipement** : mis en production le 1ᵉʳ novembre 2015. Le corpus
couvre 14 mois s'achevant début 2025 — l'appareil a donc environ **neuf ans de
service** sur la période analysée. C'est l'argument qui soutient la conclusion
du KPI d'exposition corrosive : *le vieillissement relève de l'âge et de
l'érosion, non du régime de marche*.

**Pourquoi le 904L compte** : sa vitesse de corrosion en H₂SO₄ 98 % croît
fortement au-delà de 110 °C. C'est la justification du seuil
`T_ACID_IN.alarm_high_high = 105 °C` et du rattachement de ce tag au mode AMDEC
`FAISCEAU_CORROSION`. **[LU — `tags.yaml`, commentaire du bloc T_ACID_IN]**

---

# 2. Les données

## 2.1 Le corpus **[LU — `dcs_loader.py`, `config.py`]**

| | |
|---|---|
| Source | `data/raw/DATA.xlsx`, export DCS |
| Feuille gouvernée | `Feuil1` (nommée, pas devinée par position) |
| **Début du corpus** | **2024-01-01 à 07:00** |
| **Fin du corpus** | **2025-02-28 à 11:00** |
| Étendue | **14 mois** |
| Horodatages | **10 182**, pas nominal **1 h** |
| Tags DCS | 12, dont 2 déclarés `degraded` |
| Heures à l'arrêt | **1 251**, soit **12,3 %** — voir § 15.1 **[MESURÉ]** |

## 2.2 Les douze tags **[LU — `tags.yaml`, `knowledge.py`]**

Rôles : `primary` (surveillé), `secondary`, `context` (normalisation),
`degraded` (capteur hors service, exclu d'office du périmètre).

### Les douze tags, table exacte du référentiel

| alias | rôle | unité | plage exploitation | bases de détermination |
|---|---|---|---|---|
| `T_ACID_IN` | primary | degC | **85,0 – 100,0** | isa_5_1, process, data |
| `T_ACID_OUT` | primary | degC | **63,0 – 68,0** | isa_5_1, process, data |
| `F_ACID` | primary | m³/h | **40,0 – 80,0** | isa_5_1, process, data |
| `C_ACID_1100` | primary | % | **98,0 – 99,3** | isa_5_1, process, data |
| `C_ACID_1200` | primary | % | **98,0 – 99,3** | isa_5_1, process, data |
| `T_CIRC_1300` | secondary | degC | **35,0 – 55,0** | isa_5_1, process, data |
| `LOAD_SULFUR` | context | t/h | **10,0 – 22,0** | isa_5_1, process, data |
| `F_3412` | context | m³/h | **1 500 – 2 400** | isa_5_1, process, data |
| `A_3301` | context | — | **7,0 – 8,6** | isa_5_1, data |
| `A_3302` | context | — | **5,5 – 8,6** | isa_5_1, data |
| `PHI_5306` | **degraded** | — | — | isa_5_1, data |
| `TI_5303` | **degraded** | degC | — | isa_5_1, data |

**Répartition** : 5 `primary`, 1 `secondary`, 4 `context`, **2 `degraded`**.
Le **périmètre surveillé** (`monitored_tags`) est primary + secondary = **6
tags**. Le **périmètre modèle** (`model_tags`) ajoute le contexte = **10 tags**.

**Dix tags sur douze reposent sur trois bases** (ISA 5.1 + procédé + données) ;
seuls `A_3301`, `A_3302` et les deux dégradés en ont deux.

### Seuils gouvernés des grandeurs de diagnostic

| tag | LL | L | consigne | H | HH | arrêt sous |
|---|---|---|---|---|---|---|
| `T_ACID_OUT` | — | — | **66,0 °C** | 68,0 | 72,0 | — |
| `T_ACID_IN` | — | — | — | 100,0 | 105,0 | **60,0 °C** |
| `F_ACID` | **20,0** | 35,0 | — | — | — | (LL sert à l'arrêt) |
| `C_ACID_1100` | **97,0 %** | 98,0 % | — | — | — | — |
| `LOAD_SULFUR` | — | — | — | — | — | **8,0 t/h** |

`T_SEAWATER` n'est **pas un tag** : il est déclaré sous `external_inputs`,
plage 17,0 – 22,0 °C, base `climatology`. C'est ce qui explique qu'il ait été
invisible à toutes les routes de l'API jusqu'à sa correction.

**Point de méthode important** : aucune fiche d'instrumentation n'accompagne
l'export DCS. Le **sens** de chaque tag a été établi par recoupement d'au moins
deux bases indépendantes, publiées dans `determination_basis()` :

- `isa_5_1` — nomenclature d'instrumentation (TI, FI, AI, PHI)
- `process` — physique du procédé sulfurique et données Chemetics
- `data` — comportement observé sur les 10 182 heures
- `stoichio` — cohérence stœchiométrique de la ligne
- `climatology` — pour la seule entrée externe

**[LU — `knowledge.determination_basis`]**

## 2.3 Les deux capteurs déclarés défaillants **[LU — `e7301_features.py`, `tags.yaml`]**

| capteur | défaut | durée |
|---|---|---|
| `TI5303-4X` | **saturé à 327,67** (butée d'échelle) | depuis août 2024, ~7 mois |
| `PHI5306X-3` | **figé à −14,407**, puis 139 codes qualité | ~1 900 h |

Ils sont exclus du périmètre par `role: degraded`, et **signalés une fois** dans
la synthèse de santé capteurs plutôt que recomptés chaque heure — sinon sept
mois de données seraient marqués « dégradés » et les vrais défauts noyés.

## 2.4 La qualité de donnée est une information, pas un déchet

**[LU — `dcs_loader.py`, en-tête]**

Quatre familles d'événements horodatés, jamais comblés par interpolation :

| motif | détection | sévérité |
|---|---|---|
| `QUALITY_CODE` | codes texte DCS : `Bad`, `Configure`, `I/O Timeout` | selon `quality_codes` |
| `SATURATED` | valeur collée à la butée, tolérance 10⁻⁴ relatif | HIGH |
| `OUT_OF_RANGE` | hors plage physique déclarée | HIGH |
| `FROZEN` | signal strictement constant ≥ **6 h** en marche | HIGH |
| `MISSING_VALUE`, `DUPLICATE_TIMESTAMP`, `OUT_OF_ORDER`, `TIME_GAP` | qualité structurelle | MEDIUM |

**Constantes** : `FROZEN_MIN_HOURS = 6` (un poste), `FROZEN_EPS = 1e-9`,
`SATURATION_REL_TOL = 1e-4`. **[LU]**

Politique déclarée : *« Aucune imputation globale ; valeurs invalides ou
absentes = NaN. »* Un `fillna(method='ffill')` produirait un système qui
déclare « tout va bien » pendant sept mois de capteur mort.

**Deux corrections de causalité, à citer dans le rapport :**

1. **Détection de gel** — une version antérieure mesurait la longueur **totale**
   du palier et marquait rétroactivement tous ses points. **2 327 événements
   FROZEN** étaient ainsi datés d'une information venue du futur, et ils
   alimentent `n_invalid_tags`, la règle `CAPTEUR_DEFAILLANT` et le drapeau
   d'applicabilité du modèle. Le compteur ne regarde plus que le passé.
   **[DÉCLARÉ — `dcs_loader.py:244-256`]**
2. **Classification d'état** — `is_down.shift(-1)` déclarait un instant
   TRANSIENT parce que la ligne s'arrêtait à t+1. **27 horodatages** concernés.
   Supprimé. **[DÉCLARÉ — `dcs_loader.py:380-388`]**

## 2.5 L'état procédé — la décision la plus déterminante

**[LU — `dcs_loader.classify_process_state`, `tags.yaml/process_states`]**

Trois états, et **seul RUNNING autorise un jugement de performance** :

| état | règle |
|---|---|
| `STOPPED` | `LOAD_SULFUR < 8` **ou** `F_ACID < 20` **ou** `T_ACID_IN < 60` |
| `TRANSIENT` | `abs(d(LOAD_SULFUR)/dt) > 2 t/h/h` **ou** état précédent = STOPPED |
| `RUNNING` | aucun des deux |

Les quatre seuils viennent du référentiel, aucun n'est écrit dans le code.

**Nuance à mentionner** : une mesure absente est remplie par zéro, donc
classée STOPPED. C'est le seul sens acceptable — déclarer RUNNING une heure
dont on ignore la charge reviendrait à juger un échangeur sur une base qu'on
sait trouée — mais ces heures s'affichent « ligne à l'arrêt » alors qu'elles
sont des heures de **mesure indisponible**. **[LU, corrigé en S2-3]**

---

# 3. Le cœur scientifique

C'est la section qui porte le mémoire. Deux décisions, ADR-001 et ADR-002.

## 3.1 ADR-001 — le résidu de duty est algébriquement circulaire

**[LU — `e7301_features.py`, en-tête, lignes 13-46]**

La v1 affirmait que l'encrassement « se lit sur l'effort, pas sur le
résultat », l'effort étant le résidu de puissance thermique. **C'est faux, et
l'erreur est algébrique.**

Le duty est calculé **par définition** :

```
duty = ρ·cp · F · (T_in − T_out)
```

La référence le régresse sur `LOAD_SULFUR`, `F_ACID`, `T_ACID_IN`, `conc_min`
et le produit `F × T_in`. Or **T_out est régulée** — écart-type 0,8 °C sur
14 mois — donc :

```
duty ≈ ρ·cp·F·T_in  −  ρ·cp·66·F
```

est déjà une combinaison linéaire de deux régresseurs présents. **La régression
ne modélise pas l'échangeur : elle retrouve sa propre définition.**

### Les chiffres qui l'établissent **[DÉCLARÉ, recalculés à chaque ajustement]**

| grandeur | valeur |
|---|---|
| R² de la référence apprise | **0,968** |
| R² d'une reconstruction **sans apprentissage** | **0,962** |
| apport réel du modèle appris (`learned_gain`) | **0,006** |
| corrélation(résidu, écart de consigne) | **−0,94** |
| variance du résidu expliquée par l'écart seul | **88 %** |

Ces chiffres ne sont pas figés dans un commentaire : `naive_r2` et
`learned_gain` sont **recalculés à chaque `fit`**, publiés dans le manifeste, et
un test échoue si la redondance disparaît sans que l'analyse soit reprise.

**Conséquence** : le résidu est renommé `regulation_effort` — c'est ce qu'il
mesure — et il **n'entre dans aucune condition de déclenchement ni de
gradation**. Il est cité comme contexte, et sa valeur de preuve est nulle.

### La distribution qui explique tout

`T_ACID_OUT` : **P1 = 63,7 °C, P99 = 66,6 °C** sur 14 mois, soit une bande de
3 °C. Un z-score sur ce signal ne détecte rien tant que la régulation tient —
et quand elle lâche, il est déjà trop tard. **[DÉCLARÉ]**

`T_ACID_IN` : écart-type **2,0 °C** en marche établie, contre **0,6 °C** pour la
sortie. C'est une variable **libre**, corrélée à la charge (r = +0,57).

## 3.2 ADR-002 — la climatologie de Safi rend UA calculable

**[LU — `src/features/thermal.py`, en-tête et `SEAWATER_MONTHLY_C`]**

Un indicateur de dégradation doit porter sur **la grandeur que la dégradation
attaque**. Pour un échangeur, c'est le coefficient d'échange global **UA**.
Le calculer exige la température du fluide froid, absente de l'export DCS.

Elle est néanmoins connue : le refroidisseur est refroidi à l'eau de mer, à
Safi, où le **courant des Canaries** et l'**upwelling côtier** maintiennent une
eau fraîche à faible amplitude annuelle.

### Climatologie mensuelle retenue, en °C **[LU — valeurs exactes du code]**

| J | F | M | A | M | J | J | A | S | O | N | D |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 17,5 | 17,0 | 17,2 | 17,8 | 18,6 | 19,6 | 20,6 | 21,6 | **22,0** | 21,2 | 19,8 | 18,4 |

Minimum 17,0 °C en février-mars, maximum 22,0 °C en septembre, moyenne annuelle
19,3 °C, amplitude ≈ 5 °C. Interpolation **cyclique** au jour de l'année
(décembre voisin de janvier).

**Argument de prudence à citer** : la prise d'eau est immergée, donc plus stable
que la surface. Ces valeurs de surface constituent une **borne haute** de
l'amplitude réelle — l'écart introduit va dans le sens de la prudence.

## 3.3 La méthode efficacité-NTU **[LU — `thermal.overall_conductance`]**

Le débit d'eau de mer est très supérieur au débit acide en capacité thermique :
le côté froid se comporte comme une **source isotherme**. D'où, directement :

```
ε   = (T_acide_entrée − T_acide_sortie) / (T_acide_entrée − T_eau)
NTU = −ln(1 − ε)
UA  = C_acide · NTU          avec  C_acide = ρ·cp(T̄) · F_acide
```

Cette formulation **évite la moyenne logarithmique et sa singularité** quand les
écarts aux deux extrémités se rapprochent.

**Garde-fous** : `MIN_APPROACH_K = 1,0` K aux deux bornes (en dessous,
l'échangeur ne travaille pas), `ε` borné dans [10⁻⁴ ; 0,999]. **Tout écrêtage
effectif est compté et journalisé** — un écrêtage sur la grandeur de diagnostic
ne peut pas être silencieux.

## 3.4 Propriétés physiques de l'acide **[LU — `e7301_features.py:108-158`]**

Corrélations linéaires ajustées sur les tables de référence H₂SO₄ 98 %
(Perry, *Chemical Engineers' Handbook*), valides 20 – 120 °C :

```
ρ(T)  = 1857 − 1,03·T        kg/m³
cp(T) = 1,363 + 7,5e-4·T     kJ/(kg·K)
```

**Résultat mesuré, et honnêteté à conserver dans le rapport** : sur 66 – 95 °C,
ρ baisse d'environ 1,8 % et cp monte d'environ 1,5 % — **en sens opposés**. Leur
**produit ne bouge que de ~0,2 %**. Le raffinement est conservé parce qu'il est
plus juste, mais **il ne change pas les conclusions** et ne doit pas être
présenté comme une correction significative. Un test fige ce constat pour
empêcher de le survendre.

**Portée de l'incertitude de tabulation** (~1 % sur ρ, ~2 % sur cp) : ρ·cp
intervient en facteur commun de `duty_kw` **et** de la capacité thermique
utilisée pour UA. Une erreur d'échelle de 2 % déplace UA et UA attendu **dans le
même rapport**, donc laisse le **résidu normalisé inchangé**. Elle n'affecte que
la lecture en valeur absolue des kW affichés.

## 3.5 UA est un UA APPARENT — la limite à énoncer sans détour

**[LU — `thermal.py:43-73`]**

C'est le paragraphe le plus important du dossier pour la crédibilité devant un
jury.

Le débit d'eau de mer **n'est pas instrumenté**, et c'est **lui** que la
régulation manipule pour tenir la consigne de 66 °C. La grandeur calculée est
donc le produit de deux facteurs :

```
UA_apparent  =  état de la surface d'échange  ×  action de la boucle froide
```

**Conséquence** : tant que la vanne d'eau de mer conserve de la marge, elle
compense un début d'encrassement et `UA_apparent` ne bouge pas. L'indicateur
devient sensible **quand cette marge se consomme**.

C'est pourquoi le banc d'injection ne publie pas un taux de détection mais
**l'AVANCEMENT auquel la détection survient** : c'est la mesure de ce retard, et
c'est le chiffre honnête.

**Signature visible dans les données** : `UA_apparent` suit la température
d'eau de mer — **13,8 kW/K en janvier, 21,9 kW/K en septembre** — parce qu'une
eau plus chaude oblige la vanne à s'ouvrir davantage. La régression retire cette
part saisonnière ; le résidu est ce qui reste. **[DÉCLARÉ]**

## 3.6 Indépendance mesurée des trois indicateurs **[DÉCLARÉ, publié par `independence_report()`]**

Corrélation avec l'écart de consigne, en marche établie :

| indicateur | r | variance partagée | rôle |
|---|---|---|---|
| `regulation_effort_z` | **−0,94** | 88 % | **conduite** — jamais une preuve |
| `ua_residual_z` | **−0,54** | 29 % | **diagnostic** — partiellement confondu |
| `t_in_residual_z` | **+0,03** | 0,1 % | **contexte** — indépendant, mais confondu côté procédé |

Le verdict publié par le système, à reprendre tel quel :

> *« Le diagnostic d'encrassement est porté par le résidu de coefficient
> d'échange, seul indicateur construit sur la grandeur que l'encrassement
> dégrade. Sa confusion résiduelle avec l'écart de consigne est mesurée et
> publiée plutôt que niée. »*

**Limite de `t_in_residual_z`** : il est **confondu côté procédé**. Une dérive de
l'entrée peut venir du refroidisseur **comme de la tour de séchage** ou de tout
autre organe amont. Il ne prouve rien seul ; il contextualise.

## 3.7 La résistance d'encrassement **[LU — `thermal.add_conductance_features`]**

```
Rf = 1/UA − 1/UA_attendu        en K/kW
```

**Le terme de comparaison est UA ATTENDU AUX CONDITIONS DE L'INSTANT, pas la
moyenne de référence.** Une version antérieure écrivait `Rf = 1/UA − 1/UA_moyen`.
Comme UA varie légitimement d'un **facteur 1,6** avec le débit et la saison,
cette différence mesurait surtout le régime :

| corrélation de Rf avec | ancienne formule | formule actuelle |
|---|---|---|
| le débit | **−0,76** | **+0,13** |
| UA attendu | **−0,90** | **+0,08** |

Autrement dit, une simple baisse de débit se lisait comme un encrassement.
**[DÉCLARÉ]**

## 3.8 Les deux analyseurs de titre ne sont pas redondants

**[LU — `e7301_features.py:248-278`]**

Correction d'une erreur de conception initiale. La v1 prenait `min(AI1100,
AI1200)` au nom d'une « approche conservative », en les supposant redondants.

| mesure | valeur |
|---|---|
| corrélation entre les deux, en marche | **+0,35 seulement** |
| biais systématique AI1200 − AI1100 | **−0,124 point** |
| écart-type du biais | **0,079 point** |
| part des cas où AI1200 est le minimum | **94,9 %** |

Le `min()` se réduisait donc à un seul capteur, tout en donnant l'illusion d'une
sécurité par redondance.

**Nouvelle règle** : les deux circuits sont exposés séparément, et l'écart
devient un indicateur à part entière — **ce n'est pas sa valeur absolue qui
compte, mais sa STABILITÉ**. Un biais constant est normal ; un biais qui dérive
signale un analyseur qui part. Seuil : `|conc_bias_drift_z| > k σ`, avec
`k = cross_check_k_sigma = 4,0` gouverné dans `tags.yaml`.

**L'ancien seuil abandonné** valait 0,6 point absolu, soit **6 σ** : il ne se
déclenchait que **19 heures sur 14 mois**. Il ne servait à rien. **[DÉCLARÉ]**

---

# 4. Architecture logicielle

## 4.1 Chaîne de traitement **[LU — `pipeline.py`]**

```
data/raw/DATA.xlsx
  │
  ├─ src/ingest/dcs_loader.py ....... ingest() → IngestionResult
  │     readings · observations · quality · sensor_health · report
  │
  ├─ src/features/thermal.py ........ UA, ε-NTU, climatologie, ConductanceReference
  │  src/features/e7301_features.py . build_features() → (DataFrame, References)
  │
  ├─ src/models/detector.py ......... CoolerAnomalyDetector
  │     étage 1 : RuleEngine (déterministe, ancré AMDEC)
  │     étage 2 : StatisticalDetector (Isolation Forest)
  │
  ├─ src/agents/detection_agent.py .. DetectionAgent → AgentDecision
  │  src/agents/judge_agent.py ...... JudgeAgent → JudgeVerdict (8 contrôles)
  │
  └─ api/main.py + api/static/ ...... poste FastAPI, jumeau 3D three.js
```

`src/pipeline.py` est le **point d'entrée unique**. API, rejeu temps réel,
notebooks et tests s'appuient dessus pour garantir qu'ils exécutent exactement
la même chaîne.

## 4.2 Le référentiel gouverné (ADR-005) **[LU — `knowledge.py`]**

`src/domain/knowledge.py` est la **seule porte d'entrée** vers les trois YAML.
Règle du dépôt : *aucun seuil, aucun nom de tag, aucune criticité AMDEC codé en
dur ailleurs*.

| fichier | contenu |
|---|---|
| `tags.yaml` | 12 tags, `external_inputs`, `process_states`, `quality_codes`, `governance_defaults`, `registry_change_history` |
| `amdec.yaml` | 13 modes, 3 barèmes (GRV/OCC/DET), plan de maintenance A–H, gammes, checklists |
| `topology.yaml` | pièces physiques, placement 3D des capteurs, `finding_map` |

**La fonction `seuil(valeur, defaut)`** — invention centrale du dépôt :

> *« Le repli teste l'ABSENCE, pas la fausseté. L'idiome `tag.threshold(...) or
> <defaut>` remplaçait un seuil légitimement nul par la valeur de secours : un
> débit d'arrêt à 0 m³/h se serait transformé en 20 m³/h, un titre à 0 % en
> 97 %, sans le moindre avertissement. Il était employé à douze endroits. »*

## 4.3 Mise en forme française (ADR-011) **[LU — `src/formatting.py`]**

Conventions : virgule décimale, **espace insécable étroite U+202F** en
séparateur de milliers, **insécable ordinaire U+00A0** avant `%`, `°C` et les
unités.

`sans_accents()` vit dans `src/` et non dans les tests, pour une raison
documentée : le contrôle V8 du Judge cherche des mots-clés — « réserve »,
« défaut », « dégradé » — dans le texte produit. Quand ces textes ont été
correctement accentués, **cinq des douze clés sont devenues introuvables** :
V8 a échoué sur **100 % des heures hors marche**, et l'exploitant a reçu
« limite non énoncée » sur des diagnostics qui énonçaient précisément leur
limite.

**Règle qui en découle, à énoncer dans le rapport** : *le texte COMPARÉ est
dépouillé, le texte AFFICHÉ est accentué.*

---

# 5. Les features

## 5.1 Les onze features du modèle **[LU — `MODEL_FEATURES`]**

```python
["ua_residual_z", "regulation_effort_z", "t_in_residual_z",
 "conc_min", "conc_bias_drift_z", "conc_drop_24h",
 "flow_per_load", "d_t_out", "d_conc",
 "t_out_local_z", "t_in_local_z"]
```

**Ce qui a été retiré, et pourquoi** — argument de conception à citer :

- `regulation_effort` et sa version standardisée sont **strictement colinéaires**
- `delta_t` et `approach_ratio` portent presque la même information
- `duty_kw`, `duty_per_load` et les régresseurs de la référence se recouvrent
- `control_deviation` et l'effort de régulation sont **le même signal** (r = −0,94)

**Les moyennes glissantes 14 jours n'entrent PAS dans le modèle.** C'est une
correction de conception : donner une tendance lente à un détecteur de points
atypiques garantit que **toute** heure d'une période dérivée sera signalée. Le
taux de signalement passait alors de **10 % à 17 %**, et **à 65 % sur le mois
d'octobre**. **[DÉCLARÉ]**

> Une dérive lente n'est pas une succession de points anormaux, c'est **UN
> événement** — et c'est le rôle des règles de persistance de le dire une fois,
> pas celui du modèle de le répéter à chaque heure.

**Répartition des rôles** :

| étage | ce qu'il capte |
|---|---|
| modèle statistique | combinaisons **instantanées** inhabituelles |
| règles de dérive | tendances **lentes**, avec exigence de persistance |

## 5.2 Les trois références linéaires **[LU]**

Une régression linéaire sur termes physiques est préférée à un modèle complexe
pour trois raisons explicites :

1. elle est **explicable** devant un exploitant ;
2. elle **ne peut pas apprendre la dégradation** elle-même et la masquer ;
3. ses coefficients sont **vérifiables** par le contrôleur de cohérence.

| référence | cible | régresseurs | unité |
|---|---|---|---|
| `ConductanceReference` | `ua_kw_per_k` | `F_ACID^0,8`, T̄ acide, `T_SEAWATER`, const | kW/K |
| `RegulationEffortReference` | `duty_kw` | charge, débit, T_in, titre, `F×T_in`, const | kW |
| `InletReference` | `T_ACID_IN` | charge, débit, `charge×débit`, const | °C |

**L'exposant 0,8** sur le débit vient de la forme de **Dittus-Boelter** :
c'est l'exposant sur le nombre de Reynolds, donc sur le débit, qui gouverne la
turbulence côté calandre. **[LU — `FLOW_EXPONENT`]**

### La période de référence — le point le plus discutable du projet

`REFERENCE_FRACTION = 0.40` : les **40 % initiaux des heures de marche
établie**, à défaut d'une date de révision qu'OCP n'a pas fournie.

**Correction importante à raconter** : chaque `fit` découpait ses 40 % **après**
avoir appliqué son propre masque d'éligibilité. Or ces masques diffèrent — la
conductance exige `ua_kw_per_k`, l'effort exige `duty_kw` et `conc_min`,
l'entrée n'exige que charge et débit. Les trois références s'arrêtaient donc à
des instants différents — **mesure : 2024-07-13 à 17 h, 18 h et 21 h** — alors
que l'ADR-009 affirme qu'elles « partagent la même règle ET la même période ».
**La règle était partagée, la période non.** **[DÉCLARÉ]**

La borne est désormais calculée **une fois** par `reference_cutoff()`, sur les
heures de marche, indépendamment de toute disponibilité de mesure.

## 5.3 Fenêtres temporelles **[LU]**

Toutes **calendaires**, jamais en nombre de lignes — un trou d'acquisition ne
doit pas transformer « 24 lignes » en une durée supérieure à 24 heures.

| constante | valeur | usage |
|---|---|---|
| `SHORT_WINDOW` | `24h` | z-scores locaux |
| `LONG_WINDOW` | `14D` | tendances de dérive, `min_periods=112` |
| `DRIFT_PERSISTENCE_H` | 72 h | persistance exigée d'une dérive |

---

# 6. La détection

## 6.1 Deux étages fusionnés, pas mis en concurrence **[LU — `detector.py`]**

| étage | nature | apport |
|---|---|---|
| **1 — RuleEngine** | déterministe, ancré AMDEC | vérifiable, traçable, **ne peut pas halluciner**. Toute alerte se rattache à une ligne de l'AMDEC de 2019. |
| **2 — Isolation Forest** | statistique | capte les **combinaisons anormales** de variables qui, prises une à une, restent dans les tolérances |

Le score final retient la **sévérité la plus élevée**, et les preuves des deux
étages sont conservées. **Un écart entre les deux — règle silencieuse / modèle
alarmiste, ou l'inverse — est lui-même une information transmise au Judge.**

## 6.2 Les règles et leurs seuils **[LU — tous gouvernés]**

| code | mode AMDEC | condition | sévérité |
|---|---|---|---|
| `CONTROL_LOSS_CRITICAL` | FAISCEAU_BOUCHAGE | `T_ACID_OUT ≥ 72 °C` | CRITICAL |
| `CONTROL_LOSS` | FAISCEAU_BOUCHAGE | `T_ACID_OUT ≥ 68 °C` | WARNING |
| `FOULING_DRIFT` | FAISCEAU_BOUCHAGE | `ua_residual_trend_14d ≤ −1,5 σ`, **> 80 % de la fenêtre de 72 h** | WARNING si ≤ −3 σ, sinon INFO |
| `OVERCOOLING_REGIME` | *aucun* | effort ≥ +1,5 σ persistant | INFO — **régime de conduite** |
| `CONC_LOW_LOW` | FAISCEAU_FUITE | titre ≤ 97 % | CRITICAL |
| `CONC_LOW` | FAISCEAU_CORROSION | titre ≤ 98 % | WARNING |
| `CONC_DROP_SEVERE` | FAISCEAU_FUITE | chute ≥ 0,80 point / 24 h | CRITICAL |
| `CONC_DROP` | FAISCEAU_FUITE | chute ≥ 0,35 point / 24 h | WARNING |
| `CONC_BIAS_DRIFT` | CAPTEUR_DEFAILLANT | `\|z\| > 4 σ` | WARNING |
| `T_IN_HIGH_HIGH` | FAISCEAU_CORROSION | `T_ACID_IN ≥ 105 °C` | CRITICAL |
| `T_IN_HIGH` | FAISCEAU_CORROSION | `T_ACID_IN ≥ 100 °C` | WARNING |
| `FLOW_LOW_LOW` | CALANDRE_FUITE | `F_ACID ≤ 20 m³/h` | CRITICAL |
| `FLOW_LOW` | CALANDRE_FUITE | `F_ACID ≤ 35 m³/h` | WARNING |
| `SENSOR_FAULT` | CAPTEUR_DEFAILLANT | ≥ 1 point en défaut | WARNING si ≥ 2 |
| `NOT_RUNNING` | *aucun* | hors marche établie | INFO |

**Deux corrections de raisonnement à citer :**

- **La conjonction qui ne pouvait pas échouer** : la règle de dérive croisait le
  résidu de duty et l'écart de consigne « comme deux preuves concordantes ». Ce
  sont deux écritures de la **même** grandeur (r = −0,94). La conjonction ne
  vérifiait rien.
- **Le même symptôme accusait deux pièces** : le seuil LL du débit était
  rattaché à CALANDRE_FUITE et le seuil L à FAISCEAU_BOUCHAGE. Une perte de
  débit **se constate ; elle ne désigne pas sa cause**. Les deux niveaux
  renvoient au même mode, et le message énonce les causes possibles sans
  trancher.

## 6.3 L'Isolation Forest **[LU]**

| paramètre | valeur |
|---|---|
| `n_estimators` | 300 |
| `max_samples` | min(1024, n) |
| `contamination` | 0,02 (**arbitraire, valeur usuelle par défaut**) |
| `random_state` | 42 |
| entrée | 11 features standardisées, **marche établie uniquement**, sans NaN |

### Deux corrections de calibration

**1. La saturation du score.** Avec `1,4826 × MAD` seul, l'échelle valait
**0,050** alors que la queue de distribution s'étend sur **0,30** : la sigmoïde
saturait, et **1,3 % des heures ressortaient à 1,0000**, indistinguables. Le
tableau des « épisodes les plus sévères » affichait douze fois la même valeur.
Correctif : `score_scale_ = max(1,4826·MAD, σ, 1e-9)`. **[DÉCLARÉ]**

**2. La marge en sigma.** Le score normalisé sert à **décider**, pas à
**classer** : toute transformation bornée écrase la queue, c'est-à-dire
précisément la zone où l'exploitant distingue un épisode d'un autre. D'où :

```
marge = (score brut − seuil brut) / écart-type de la référence
```

non bornée, lisible directement (« +3,2 σ au-dessus du seuil »), et c'est **elle
qui trie le tableau des épisodes**.

### Persistance exigée du modèle

`MODEL_PERSIST_MIN = 3` heures atypiques sur les `MODEL_PERSIST_WIN = 6`
dernières heures **calendaires**. Motif : *« Sans cette règle, le modèle émet une
alerte par heure atypique et l'opérateur en reçoit des milliers — le système
devient inutilisable et sera désactivé en salle de contrôle. »*

Sous ce seuil, la constatation devient `MODEL_ANOMALY_ISOLATED` en INFO, sans
rattachement AMDEC.

## 6.4 L'explicabilité par occlusion exacte **[LU]**

Pour chaque feature, on remplace sa valeur par la **médiane de référence** et on
recalcule le score. La baisse obtenue est la contribution réelle :

> *« si cette grandeur avait été normale, le score serait tombé de 0,81 à
> 0,34 »*

C'est **exact** (pas une approximation), déterministe, sans dépendance lourde,
et directement interprétable. Le point de référence et ses N variantes occluses
partent en **un seul appel** à la forêt.

## 6.5 Agrégation en épisodes **[LU]**

`EPISODE_MAX_GAP_H = 6`, `EPISODE_MIN_DURATION_H = 3`.

> *« Un exploitant ne traite pas 530 points d'alarme : il traite 58 épisodes.
> Cette agrégation est ce qui rend le système utilisable en salle de contrôle. »*

Les deux nombres viennent de `reports/project_metrics.json`
(`alert_hours_historical = 530`, `episodes = 58`). La docstring de
`src/models/detector.py` annonçait un décompte presque quatre fois trop élevé,
puis un nombre d'épisodes d'un ordre de grandeur trop faible. Corrigé aux deux
endroits au lot S46 : la bibliothèque citait fidèlement une source fausse.
(La valeur fautive n'est pas recopiée ici — la réécrire, même pour l'expliquer,
la remettrait sous le nez du contrôle qui vient de l'attraper.)

## 6.6 Le rattachement feature → mode AMDEC **[LU]**

Trois familles, **et une seule peut accuser une pièce** :

1. **Résidus normalisés** — leur écart à la valeur attendue **est** le
   diagnostic. `ua_residual_z ≤ −1,5 σ` → FAISCEAU_BOUCHAGE licite.
2. **Grandeurs à seuil** — titre, débit, températures ont des seuils
   d'exploitation qui font foi. Le modèle peut trouver leur valeur inhabituelle
   **sans qu'elle soit hors spécification** : *98,36 % de titre pour une
   référence à 98,60 % est atypique, ce n'est pas de la corrosion*. Elles
   n'accusent que si le seuil métier est franchi — auquel cas la règle
   déterministe s'est déjà déclenchée. **Le modèle ne double pas la règle.**
3. **Indicateurs de conduite** — effort et écart de consigne ne désignent
   aucune pièce.

---

# 7. L'AMDEC

**[LU — `amdec.yaml`, `knowledge.py`]**

Source : *« 4-AMDEC - REFROIDISSEUR DE SECHAGE PSIII.xlsx »*, analyse OCP du
**23/09/2019**.

| | |
|---|---|
| Modes | **13** |
| Criticité | **C = F × G × N** |
| Total de criticité | **1052** |
| Bandes | MAJEURE (C ≥ 100), SIGNIFICATIVE (C ≥ 60), MODÉRÉE |

## 7.1 Les trois barèmes **[LU — transcrits des onglets GRV, OCC, DET]**

**Gravité (onglet GRV)**, 10 échelons — extraits :

| G | définition |
|---|---|
| 10 | dangereux **sans** alarme — sécurité / non-respect réglementaire |
| 9 | dangereux **avec** alarme |
| 8 | très élevé — arrêt > 8 h ou produit non conforme > 4 h |
| 7 | élevé — arrêt 4 à 8 h |
| 1 | sans effet |

**Fréquence (onglet OCC)** — MTBF en heures :

| F | 10 | 9 | 8 | 7 | 6 | 5 | 4 | 3 | 2 | 1 |
|---|---|---|---|---|---|---|---|---|---|---|
| MTBF (h) | 1 | 8 | 24 | 80 | 350 | 1 000 | 2 500 | 5 000 | 10 000 | 25 000 |

**Détection (onglet DET)**, 5 échelons : 1 très élevé · 3 élevé · 5 modéré
(outillage spécifique requis) · 7 faible (démontage requis) · **10 aucune
détection possible**.

## 7.2 L'observabilité à trois degrés — correction majeure

**[LU — `knowledge.FailureMode.observabilite`]**

Le code lisait `bool(signature.get("observable"))`, et **`bool("partial")` vaut
`True`** : une valeur écrite pour signifier « partiellement » était lue comme
« entièrement », sans avertissement. **La couverture publiée du risque AMDEC
s'en trouvait surévaluée.**

| degré | signification | conséquence |
|---|---|---|
| `full` | le système mesure l'état de la pièce | compté comme couvert |
| `partial` | le **symptôme** est mesurable, l'**état** ne l'est pas | **compté à part**, jamais comme couvert |
| `none` | aucun signal ne dit rien de ce mode | angle mort au sens strict |

**Une définition, pas deux** : `blind_spots()` retournait `not observable`,
c'est-à-dire aussi les modes `partial`, tandis que `risk_coverage()` les
comptait séparément. L'écart se lisait à l'écran — le tableau AMDEC affichait
« non — angle mort » pour la corrosion du faisceau et la fuite de calandre,
**deux modes auxquels le moteur de règles rattache activement des
constatations**.

## 7.2 bis Les treize modes, table complète **[LU — extraite de `amdec.yaml`]**

Triée par criticité décroissante. `obs.` = observabilité, `prov.` = catégorie de
provenance, `tâches` = plan préventif rattaché.

| # | code | F | G | N | **C** | obs. | prov. | tâches |
|---|---|---|---|---|---|---|---|---|
| 1 | `PLAQUE_SACRIFICIELLE_DYSFONCTION` | 2 | 8 | 7 | **112** | none | ocp_source | D, E |
| 2 | `VANNE_ACIDE_FUITE` | 2 | 8 | 7 | **112** | none | ocp_source | F |
| 3 | `CAPTEUR_DEFAILLANT` | 6 | 6 | 3 | **108** | **full** | application_rule | — |
| 4 | `FAISCEAU_BOUCHAGE` | 3 | 7 | 5 | **105** | **full** | derived_rule | B, H |
| 5 | `FAISCEAU_FUITE` | 3 | 7 | 5 | **105** | **full** | derived_rule | B, H |
| 6 | `FAISCEAU_CORROSION` | 3 | 7 | 5 | **105** | *partial* | derived_rule | A, B |
| 7 | `PORTE_VISITE_FUITE` | 3 | 6 | 5 | 90 | none | ocp_source | C |
| 8 | `CALANDRE_FUITE` | 3 | 6 | 5 | 90 | *partial* | ocp_source | A, C |
| 9 | `VANNE_ACIDE_BOUCHAGE` | 3 | 6 | 5 | 90 | none | ocp_source | F |
| 10 | `VANNE_EM_BOUCHAGE` | 2 | 3 | 7 | 42 | none | ocp_source | G |
| 11 | `VANNE_ACIDE_DYSFONCTION` | 2 | 3 | 7 | 42 | none | ocp_source | F |
| 12 | `VANNE_EM_FUITE` | 2 | 3 | 7 | 42 | none | ocp_source | G |
| 13 | `VANNE_EM_DYSFONCTION` | 3 | 1 | 3 | 9 | none | ocp_source | G |
| | **total** | | | | **1052** | | | |

**Lecture de cette table pour le mémoire :**

- **Neuf modes sur treize viennent directement du document OCP** de 2019
  (`ocp_source`). Trois sont des `derived_rule` — la ligne AMDEC source
  « FAISEAU TUBULAIRE / Fuite / Bouchage / Corrosion » a été **éclatée en trois
  modes distincts** parce que leurs signatures dans les données diffèrent. Un
  seul est une `application_rule` : `CAPTEUR_DEFAILLANT`, **proposé par ce
  travail**, avec `validation_status: hypothesis`.
- Les trois modes de faisceau partagent la même cotation **F=3, G=7, N=5** :
  c'est la cotation de la ligne source unique, reportée sur les trois éclats. À
  signaler comme une transformation assumée, pas comme trois évaluations
  indépendantes.
- **`CAPTEUR_DEFAILLANT` porte la fréquence la plus élevée du référentiel
  (F = 6, soit un MTBF de 350 h, « défaillance chaque mois »)** — cotation
  justifiée par les données : deux capteurs effectivement morts sur douze.
- Le mode le moins critique, `VANNE_EM_DYSFONCTION`, vaut **9** : G = 1, « sans
  effet — ajustement en maintenance normale ».

## 7.3 La couverture du risque — le chiffre central du mémoire

**[LU — recalculé depuis `amdec.yaml` par la formule de `risk_coverage()`]**

| catégorie | modes | criticité | part |
|---|---|---|---|
| **couverte** (`full`) | 3 | **318** | **30,2 %** |
| **partielle** (`partial`) | 2 | 195 | 18,5 % |
| **non couverte** (`none`) | **8** | **539** | **51,2 %** |
| total | 13 | **1052** | 100 % |

**Les trois modes réellement couverts** : `CAPTEUR_DEFAILLANT` (108),
`FAISCEAU_BOUCHAGE` (105), `FAISCEAU_FUITE` (105).

**Les deux modes partiellement observés** : `FAISCEAU_CORROSION` (105) — on lit
l'exposition cumulée, pas l'amincissement des tubes — et `CALANDRE_FUITE` (90)
— on devine par une perte de débit, on ne mesure pas.

**Formulation à retenir** : la surveillance par données couvre **30,2 %** de la
criticité AMDEC. Ce n'est pas un échec, c'est le chiffre honnête — et il est
publié parce que, sans lui, *« un lecteur pressé conclut que la surveillance par
données traite le risque ; elle n'en traite qu'une part »*.

## 7.3 bis Les modes non instrumentés **[LU]**

Les **deux modes les plus critiques de l'équipement** — `PLAQUE_SACRIFICIELLE_
DYSFONCTION` et `VANNE_ACIDE_FUITE`, **criticité 112 chacun**, tous deux
`ocp_source` — ne sont **pas instrumentés**.

Leur cotation est identique et parlante : **F = 2** (défaillance tous les 2 ans,
MTBF 10 000 h), **G = 8** (très élevé : arrêt > 8 h ou produit non conforme
> 4 h), **N = 7** (faible : nécessite un démontage, la surveillance ne détecte
pas). C'est le **N = 7** qui les rend critiques — ce sont des défaillances graves
qu'**aucune surveillance ne peut voir**, et l'ajout de capteurs ne changerait
pas leur gravité.

Formulation à reprendre :

> *« La part non couverte reste sous la responsabilité du plan préventif A–H et
> de l'inspection : la surveillance par données ne s'y substitue pas. La part
> PARTIELLE désigne les modes dont le système observe les conditions
> favorisantes sans mesurer l'état de la pièce — corrosion du faisceau, fuite de
> calandre. Elle n'est pas comptée comme couverte, parce qu'**une condition
> surveillée n'est pas une défaillance détectée**. »*

## 7.4 Provenance de chaque ligne AMDEC **[LU]**

Cinq catégories, publiées par mode : `ocp_source`, `derived_rule`,
`application_rule`, `hypothesis`, `field_validated`. Chaque mode porte
`source_file`, `source_location` (ex. *« Feuille AMDEC FOUR A SOUFRE, lignes
10-12 »*), `original_values`, `transformations` et `validation_status`.

**Exemple de transparence à citer** : `FAISCEAU_CORROSION` porte
`validation_status: hypothesis` et la transformation *« La cause source
Corrosion est utilisée comme règle de risque distincte ; ce n'est pas une ligne
AMDEC OCP autonome. »*

**Et un arbitrage qui en découle** : `CAPTEUR_DEFAILLANT` porte **C = 108**,
cotation **proposée par ce travail** (`application_rule`, `hypothesis`), contre
**105** pour `FAISCEAU_FUITE`, ligne transcrite du document OCP. Trier sur la
seule criticité aurait fait dominer un analyseur dégradé sur une **suspicion de
percement de tube**. L'état de la chaîne de mesure est une **réserve sur la
lecture**, pas une conclusion sur l'appareil.

## 7.5 Plan de maintenance préventive **[LU]**

Source : *« 5-Plan de Maintenance Preventive REFROIDISSEUR DE SECHAGE
PSIII.xlsx »*. Tâches A à H, chacune avec type, **état exigé** et périodicité.

| réf | tâche | état exigé | cadence |
|---|---|---|---|
| **A** | Mesure des épaisseurs de la calandre | Arrêt process | 4 ans |
| **B** | Mesure des épaisseurs des tubes par courant de Foucault | Arrêt process | 2 ans |
| **C** | Inspection externe du refroidisseur | **En marche** | **1 mois** |
| **D** | Contrôle anode sacrificielle | Arrêt process | 6 mois |
| **E** | Changement anode sacrificielle | Arrêt process | 3 ans |
| **F** | Changement de la vanne d'acide de vidange | Arrêt process | 4 ans |
| **G** | Changement des vannes de vidange eau de mer | Arrêt process | 6 ans |
| **H** | Changement refroidisseur ou tubes tamponnés ≥ 30 % | Arrêt process | 8 ans |

**Sept tâches sur huit exigent l'arrêt process.** La seule réalisable en marche
est l'inspection externe mensuelle (C) — c'est pourquoi c'est celle que la
décision **nominale** recommande, et pourquoi la fenêtre d'exécution ne peut pas
être déduite de la sévérité.

**Le critère de la tâche H est un fait métier à citer** : « changement
refroidisseur ou tubes tamponnés **≥ 30 %** ». C'est le seuil de fin de vie du
faisceau, et il donne son sens à la surveillance de l'encrassement.

**Gammes d'intervention** déclarées : `PS3-ABS-REFR` (consignation des circuits
acide et eau de mer) et `TAMPONNAGE`.
**Check-lists** : `INSPECTION_EXTERNE`, `INSPECTION_INTERNE`.

**Règle de sélection corrigée** : la tâche retenue est **la plus fréquente** du
mode, pas la première écrite. `plan_maintenance_ref[0]` dépendait de l'ordre de
saisie du YAML — inverser deux lettres aurait fait recommander un
**remplacement de faisceau** sur une dérive naissante.

## 7.6 ADR-010 — deux horizons pour une action **[LU]**

Distinction structurante, à expliquer au jury :

| horizon | ce qu'il gouverne | source |
|---|---|---|
| **urgence** | délai de **qualification** par le service fiabilité | la sévérité |
| **fenêtre d'exécution** | `EN_MARCHE` / `ARRET_PROGRAMME` / `ARRET_IMMEDIAT` | **l'état exigé par la tâche du plan préventif** |

> *« Une sévérité élevée accélère la QUALIFICATION ; elle ne rend pas réalisable
> en marche une opération qui exige la consignation des circuits. »*

Le texte de l'action énonce les **deux horizons côte à côte** — c'est ce qui
empêche de lire « sous 24 h » comme un ordre d'intervention immédiate.

---

# 8. Les agents

## 8.1 L'agent de diagnostic **[LU — `detection_agent.py`]**

Deux modes de production, **un seul contrat de sortie** (`AgentDecision`) :

| mode | production |
|---|---|
| `rules` | composition déterministe depuis les constatations et l'AMDEC. Toujours disponible, reproductible. |
| `llm` | Gemini rédige à partir du **même dossier de faits** |

> *« Le mode `rules` n'est pas un pis-aller. C'est la référence : il fournit au
> Judge un point de comparaison pour mesurer ce que le LLM apporte réellement,
> et il garantit que le système reste démontrable sans connexion ni quota. »*

**Point de vigilance assumé** : le LLM ne voit **que** le dossier de faits
construit par le code. Il n'a pas accès aux données brutes et ne peut donc pas
inventer une mesure sans que le Judge le détecte.

### Le barème de confiance est PARTAGÉ, pas recopié

`schemas.confiance_justifiable()` est appelé par **l'agent** (qui l'annonce) et
par **le contrôleur** (qui le vérifie). Les deux avaient divergé : base 0,55
contre 0,50, pénalité binaire de 0,30 au lieu d'une graduation, corroboration
créditée d'un côté et ignorée de l'autre. **Écart mesuré jusqu'à 0,25 point.**

Effet du défaut : le contrôleur accusait l'agent de sur-confiance sur **chacune
des heures d'arrêt** du corpus — **1 251 h, 12,3 %** des horodatages (§ 15.1) —
invisible dans la note globale (8,74/10, accord maintenu), lisible uniquement
dans l'encart « Réserves du contrôleur », **c'est-à-dire au seul endroit destiné
à l'exploitant**. **[DÉCLARÉ]**

## 8.2 Le Judge — contrôleur de cohérence **[LU — `judge_agent.py`]**

### Pourquoi la v1 ne pouvait pas fonctionner

Trois failles **structurelles**, indépendantes du prompt :

1. **Aucune source de vérité indépendante.** Le Judge ne voyait que ce que
   l'agent lui racontait. Il notait la **cohérence interne** d'un texte, pas sa
   **véracité**. Un diagnostic inventé et bien rédigé obtenait une meilleure
   note qu'un diagnostic juste et mal formulé.
2. **Complaisance structurelle.** Un LLM à qui l'on demande de noter une
   production plausible note haut. Il produisait **un tampon de conformité, pas
   un contrôle**.
3. **Non reproductibilité.** Note variable, dépendance à un quota API.

### L'architecture retenue

| étage | rôle |
|---|---|
| **1 — Vérification** | déterministe, **fait autorité**. Huit contrôles, note reproductible, journal d'audit. |
| **2 — Rédaction** | LLM, optionnel, **borné à ±1,5 point**. Ne peut pas contredire un fait établi. |

Le contrôleur **recalcule les faits depuis les données brutes**, jamais depuis
les champs de la décision — qui sont précisément ce qu'on met à l'épreuve.

### Les huit contrôles et leurs poids **[LU — somme = 1,00]**

| id | question | poids |
|---|---|---|
| V1 | les chiffres cités sont-ils les vrais ? | **0,22** |
| V2 | la sévérité correspond-elle aux faits ? | 0,16 |
| V5 | la confiance est-elle calibrée ? | 0,15 |
| V3 | le mode invoqué existe-t-il et est-il observable ? | 0,14 |
| V4 | l'action est-elle conforme et exécutable ? | 0,14 |
| V6 | l'état de marche est-il respecté ? | 0,08 |
| V8 | les réserves sont-elles énoncées ? | 0,06 |
| V7 | le fait le plus grave est-il traité ? | 0,05 |

### Paramètres **[LU]**

| constante | valeur | rôle |
|---|---|---|
| `AGREEMENT_THRESHOLD` | 6,0 / 10 | en dessous, désaccord et alerte de gouvernance |
| `LLM_CORRIDOR` | ±1,5 pt | *« Le LLM apporte de la nuance, pas un droit de veto sur les faits. »* |
| `VALUE_REL_TOL` / `ABS` | 1 % / 0,05 | valeurs **déclarées** |
| `TEXT_REL_TOL` / `ABS` | 2 % / 0,15 | nombres **lus dans le texte** — un texte arrondit légitimement |
| `TEXT_MIN_MAGNITUDE` | 10,0 | en deçà, c'est un comptage, pas une mesure |
| `CONFIANCE_MAX` | 0,95 | **plafond absolu** du barème |

### Les plafonds de sécurité, non compensables

| déclencheur | plafond |
|---|---|
| `UNSAFE_ACTION`, `HALLUCINATED_VALUE`, `INVENTED_AMDEC_MODE`, `BLIND_SPOT_CLAIM` | **4,0 / 10** |
| `STATE_MISMATCH` | 5,0 / 10 |
| `SEVERITY_UNDERESTIMATED` avec sévérité réelle CRITICAL | 4,0 / 10 |

**Asymétrie assumée** : sous-estimer est bien plus grave que surestimer — une
sous-estimation laisse passer une dégradation réelle. Mais sur-alerter *« use la
confiance des équipes et finit par faire ignorer les vraies alarmes »*.

### V1 — le contrôle qui rend l'hallucination impossible

Deux niveaux : les valeurs **déclarées** confrontées aux mesures recalculées, et
**tout nombre présent dans le texte** confronté à l'**univers des nombres
légitimes** — mesures, preuves des constatations, contributions du modèle,
seuils du référentiel, cotations AMDEC. *« Tout nombre cité hors de cet ensemble
est, par construction, non rattachable aux faits. »*

### L'auto-surveillance du Judge **[LU — `JudgeAuditor`]**

> *« Un juge qui valide tout ne juge pas. »*

Trois pathologies détectées à partir de **20 décisions** :

| alerte | seuil |
|---|---|
| **complaisance** | taux de validation > 97 % |
| **sévérité systématique** | taux de validation < 10 % |
| **notes indifférenciées** | écart-type < 0,35 point |

### La portée du contrôle — phrase à ne jamais retirer

> *« Contrôle de cohérence interne utilisant les mêmes données et référentiels.
> Aucune vérité terrain GMAO ni validation opérateur indépendante. Un accord ne
> confirme ni panne, ni cause physique, ni action terrain. »*

---

# 9. La gouvernance

## 9.1 Le banc d'évaluation du Judge **[LU — `judge_eval.py`]**

### La distinction essentielle du dossier

| ce qu'on mesure | ce que ça vaut |
|---|---|
| **10 pièges conçus** portant chacun le code d'anomalie que le Judge implémente | **test de NON-RÉGRESSION** — dit que les contrôles fonctionnent toujours |
| **5 mutations non ciblées** portant sur des propriétés qu'aucun contrôle ne lit | **mesure honnête de la GÉNÉRALISATION** |

> *« On fabrique une faute conçue pour déclencher V1, puis on mesure que V1 la
> détecte. Le présenter comme une validation serait une sur-vente. »*

### Les dix pièges **[LU]**

| piège | anomalie attendue | note max tolérée |
|---|---|---|
| Valeur inventée | `HALLUCINATED_VALUE` | 4,0 |
| Angle mort revendiqué | `BLIND_SPOT_CLAIM` | 4,0 |
| Mode AMDEC inventé | `INVENTED_AMDEC_MODE` | 4,0 |
| Action dangereuse | `UNSAFE_ACTION` | 4,0 |
| Sévérité sous-estimée | `SEVERITY_UNDERESTIMATED` | 7,0 |
| Action sous-dimensionnée | `ACTION_UNDERSIZED` | 7,5 |
| Diagnostic sans chiffres | `NO_QUANTITATIVE_EVIDENCE` | 8,5 |
| Sur-confiance | `OVERCONFIDENCE` | 9,0 (pénalité ≥ 0,5) |
| État de marche erroné | `STATE_MISMATCH` | 9,0 |
| Constatations ignorées | `INCOMPLETE_COVERAGE` | 9,5 |

### Histoire à raconter : trois nettoyages successifs des mutations « non ciblées »

**Premier tour** — sur cinq mutations, **trois déclenchaient un contrôle par
construction** : bruiter une valeur de 3 à 25 % franchit toujours la tolérance
de 1 % ; permuter la sévérité déclenche V2 par définition ; mélanger les modes
tirait dans un ensemble contenant deux modes non observables. *« Le prétendu
chiffre de généralisation était donc, pour trois cinquièmes, un test de
non-régression déguisé. »*

**Deuxième tour** — deux autres retirées. *« Valeurs citées retirées »* vidait
`cited_values`, soit exactement le piège conçu `_m_no_numbers`. *« Valeurs d'un
instant voisin »* affirmait qu'aucun contrôle n'interroge l'instant d'où
viennent les chiffres, alors que V1 les confronte aux mesures recalculées **à
l'instant jugé**.

**Troisième tour (audit S6)** — le banc fixait sa graine « sinon le chiffre
change à chaque exécution » puis laissait `use_llm=True` : ±1,5 point sur chaque
verdict rendait les deux chiffres publiés aléatoires. Et une mutation
(`wrong_checklist`) rendait la décision **inchangée** quand le champ était
absent, peuplant le dénominateur de **non-événements**.

### Les cinq mutations retenues

Elles portent sur des propriétés qu'**aucun des huit contrôles ne lit** :

1. diagnostic et raisonnement **intervertis** (les deux textes restent vrais,
   seul leur **rôle** est inversé)
2. raisonnement **tronqué**
3. **action d'un autre mode** — valide en elle-même, mais ne répond pas au
   problème constaté
4. **service destinataire** erroné
5. **check-list** d'inspection erronée

`test_aucune_mutation_non_ciblee_ne_vise_un_controle` verrouille la propriété.

### Seuils d'alerte du banc **[LU]**

| critère | seuil |
|---|---|
| rappel sur pièges conçus | ≥ 80 % |
| faux positifs sur décisions saines | ≤ 20 % |
| séparation saines / fautives | ≥ 2,0 points |

## 9.2 Le banc d'injection d'encrassement **[LU — `fouling_injection.py`]**

### Pourquoi il existe

La règle d'encrassement ne s'est **jamais déclenchée** sur les 14 mois, et le
projet présentait ce zéro comme un résultat. **C'est une inversion de la charge
de la preuve.** Sans anomalie étiquetée, on ne peut pas distinguer :

1. il n'y a pas eu d'encrassement,
2. le détecteur est incapable de se déclencher,
3. l'indicateur ne mesure pas ce qu'on croit.

**Ce banc tranche entre (1) et (2).**

### Le modèle d'injection — la clé de sa validité

L'injection **ne bricole aucune température**. Elle dégrade UA et laisse la
physique produire les températures qui en résultent :

```
UA'      = UA · (1 − sévérité · avancement)
ε'       = 1 − exp(−UA' / C_acide)
T_sortie'= T_entrée − ε' · (T_entrée − T_eau_de_mer)
```

> *« C'est la seule construction qui garantisse que le détecteur ne reconnaisse
> pas la faute par un artefact de fabrication : il voit exactement ce qu'il
> verrait d'un dépôt réel de même sévérité. »*

### Le chiffre à publier

**Pas le taux de détection brut** — une dérive finit toujours par dépasser le
seuil. Mais l'**AVANCEMENT auquel elle est vue** :

| | |
|---|---|
| Sévérités testées | 5 %, 10 %, 20 %, 30 % de perte de UA |
| Durées de rampe | 30 et 60 jours |
| `USEFUL_ADVANCEMENT` | **0,50** — au-delà, l'arrêt sera subi, pas programmé |

> *« Détecter à 90 % d'avancement revient à constater la dégradation, pas à
> l'anticiper. »*

### Les trois limites publiées, à reprendre intégralement

1. le banc établit qu'un encrassement **conforme au modèle d'injection** serait
   détecté ; il **ne valide pas la signature physique réelle** ;
2. aucune vérité terrain n'existe : c'est une **borne supérieure** de
   performance ;
3. **l'injection dégrade UA à débit d'eau de mer inchangé.** La régulation
   réelle ouvrirait la vanne pour compenser, ce que le banc ne simule pas faute
   de mesure côté eau de mer : **l'avancement à la détection publié est donc
   plus favorable que celui qu'on observerait en marche.**

### Le témoin

Un **taux de faux positifs** est mesuré sur les données **non modifiées** : part
des heures de marche où la règle se déclenche sans aucune faute injectée. Les
rampes ne démarrent que dans une fenêtre où le témoin est silencieux **et** où
la ligne tourne au moins la moitié du temps.

## 9.3 L'analyse de sensibilité **[LU — `sensitivity.py`]**

> *« Un paramètre non justifié n'est pas une faute en soi. Un paramètre non
> justifié ET dont on ignore l'influence en est une. »*

### Paramètre 1 — la contamination

Grille testée : 0,005 · 0,01 · **0,02** · 0,05 · 0,10.

**Résultat mesuré** (§ 15.9) : le taux de signalement réel vaut **2,88 fois**
la contamination visée en moyenne — **3,00 ×** à la valeur retenue de 0,02 — et
**ce facteur reste stable sur toute la grille** (dispersion 0,41). La
contamination est donc un levier utilisable pour régler le volume d'alertes,
mais **elle ne se lit pas comme le taux attendu** : le seuil est appris sur la
période de référence puis appliqué à une période qui a changé de régime.
**[DÉCLARÉ]**

### Paramètre 2 — la période de référence

Grille : 25 % · **40 %** · 55 % · 70 % des heures de marche.

**C'est le résultat le plus important de l'analyse, et le plus gênant.** Texte
publié par le système, à citer tel quel dans le mémoire :

> *« La part d'heures de marche que le système déclarerait en encrassement varie
> [fortement] selon la seule fenêtre retenue comme référence. Le "zéro heure
> d'encrassement sur quatorze mois" annoncé ailleurs dans ce projet est celui de
> la fenêtre à 40 % : **ce n'est pas un constat sur l'équipement, c'est une
> conséquence de ce choix.** »*

**Le mécanisme est compréhensible** : une référence précoce apprend un
coefficient d'échange bas — l'eau de mer est froide en hiver, la vanne peu
ouverte — et voit ensuite comme une dérive la remontée saisonnière que la
régression ne compense qu'imparfaitement. Une référence plus longue couvre
plusieurs saisons et absorbe cette variation.

**Conséquence pratique** :

> *« AUCUN chiffre d'encrassement n'est publiable sans la fenêtre qui l'a
> produit. La fenêtre de 40 % est retenue parce qu'elle couvre un cycle
> saisonnier complet là où celle de 25 % s'arrête en mai, et ce choix est publié
> ici pour être contesté, pas pour être cru. »*

## 9.4 Lignage et promotion d'artefact **[LU — `lineage.py`, `promote_model.py`]**

Manifeste `schema_version 2.0`, contenant : identité et version du modèle,
période d'entraînement, features ordonnées, seuil de décision, **SHA-256 des
données et du modèle**, version de Python, **versions des six bibliothèques qui
influencent l'inférence**, résultats de validation, statut de promotion,
limitations connues.

### Le cycle de vie **[LU, corrigé en S9]**

| statut | qui l'écrit |
|---|---|
| `candidate` | `build_manifest`, **toujours** |
| `shadow_only`, `approved_for_pilot`, `approved_for_production` | `promote_model.py`, avec identité du promoteur |

> *« Produire un artefact n'est pas le promouvoir. »*

Un refus **ne s'écrit pas** : il se constate à `candidate` + liste de portes en
échec non vide.

### Les cinq portes de déploiement, et leur séparation en deux natures

| porte | nature |
|---|---|
| `causalite_temporelle` | **logicielle** — bloque une fusion |
| `redondance_features` | **logicielle** |
| `stabilite_hors_periode` | **logicielle** |
| `labels_gmao` | **donnée externe** — se publie, ne bloque pas |
| `validation_externe` | **donnée externe** |

**Pourquoi cette séparation, à expliquer** : sur ce corpus, `labels_gmao` et
`validation_externe` sont en **échec définitif** faute d'historique de pannes
étiqueté. La promotion est donc **légitimement impossible** — c'est le résultat
correct. Mais faire porter le code de retour de l'intégration continue sur les
cinq rendait **la chaîne rouge par construction** : aucun commit ne pouvait y
changer quoi que ce soit.

> *« Les deux autres attendent une donnée qu'OCP n'a jamais fournie : elles se
> PUBLIENT, elles ne bloquent pas. »*

---

# 10. Exploitation

## 10.1 Alarmes ISA-18.2

*Hors périmètre de cette bibliothèque — `operations/alarms.py` (561 l.) n'a pas
été lu ici.*

## 10.2 Workflows d'intervention **[LU — `workflows.py`]**

Base SQLite tracée, avec journal d'événements immuable.

| ensemble | valeurs |
|---|---|
| `WORKFLOW_STATES` | PLANNED, IN_PROGRESS, BLOCKED, COMPLETED, CANCELLED |
| `TERMINAL_STATES` | COMPLETED, CANCELLED |
| `STEP_STATES` | TODO, IN_PROGRESS, BLOCKED, COMPLETED, NOT_APPLICABLE |

**Trois garde-fous à citer** :

1. **Étape dangereuse** — refusée si des étapes préalables sont incomplètes, et
   **commentaire de contrôle obligatoire**.
2. **L'état de l'intervention est déduit de TOUTES ses étapes**, pas de la
   dernière touchée. Bloquer A puis compléter B repassait l'intervention « en
   cours » alors que A restait bloquée. *« Sur un bordereau qui trace une
   consignation, un blocage qui cesse de se voir est une régression de sécurité,
   pas d'affichage. »*
3. **Une clôture ne se réécrit pas** — clore deux fois réécrivait la signature,
   la date et la preuve de la première clôture, sans trace. *« Sur un document
   qui atteste qu'une consignation a été levée et une ligne remise en service,
   l'identité du signataire est la seule chose qui compte. »*

**Contrôle de concurrence** : chaque étape porte une `version`, et une
modification exige `expected_version` — sinon *« Conflit de version : recharger
le workflow »*.

**Avertissement à conserver** : *« Registre local démonstrateur ; il ne remplace
ni GMAO ni permis HSE. »*

## 10.3 Sécurité **[LU — `registry.py`, `config.py`]**

| | |
|---|---|
| Hachage | **PBKDF2-SHA256**, sel distinct par technicien |
| Longueur minimale | **12 caractères** |
| Session inactive | 30 min |
| Session absolue | 8 h |
| Rôles | reader, operator, maintenance, reliability_engineer, administrator |

**Pourquoi un registre par technicien** : la v1 reposait sur **un mot de passe
unique partagé** par toute l'allowlist. *« C'est un secret d'équipe : il
circule, il ne se révoque pas individuellement, et le journal d'audit ne peut
plus dire qui s'est réellement connecté. »*

Et surtout : *« L'adresse saisie à l'ouverture de session n'est pas décorative :
elle devient le DESTINATAIRE des alertes critiques. Une identité qui déclenche
l'envoi d'un courriel d'intervention doit être authentifiée individuellement. »*

**Le fichier de secrets vit hors du dépôt** (`data/runtime/operators.json`,
ignoré par git), écrit avec droits 600 posés **sur le fichier temporaire avant
le renommage**, et `fsync` avant publication.

**Limite déclarée** : mécanisme de **démonstration mono-poste**. En exploitation
OCP il doit céder la place au fournisseur d'identité d'entreprise —
`AUTH_PROVIDER=oidc`, et **le service refuse de démarrer en production sans
lui**.

## 10.4 Configuration **[LU — `config.py`]**

Deux principes énoncés en tête, et tenus :

1. **Toute variable déclarée est utilisée.** La v1 exposait `DATABASE_URL`,
   `MLFLOW_TRACKING_URI`, `API_SECRET_KEY` qu'aucun module ne lisait, et
   `LOG_LEVEL` n'était jamais appliqué. *« Une configuration qui ment sur ce
   qu'elle contrôle est pire qu'absente : elle fait croire qu'on a agi. »*
2. **La configuration est validée au démarrage**, pas au premier appel.

**Trois refus de sécurité notables** :

- `CORS_ORIGINS = "*"` est **refusé** : combiné à `allow_credentials=True`, il
  autoriserait n'importe quel site à lire les réponses authentifiées. Le
  navigateur refuse la combinaison, mais **rien n'empêche un client non
  navigateur de l'exploiter**.
- `SMTP_HOST` sans `SMTP_FROM`, ou `SMTP_USERNAME` sans mot de passe : refusés
  au démarrage. *« Un relais à moitié configuré échoue au premier envoi, pas au
  démarrage »* — c'est-à-dire au moment précis d'une escalade.
- **Production** exige `AUTH_ENABLED`, `AUTH_PROVIDER=oidc` et
  `AUTH_SECURE_COOKIE`.

**Délai LLM obligatoire** : `GEMINI_TIMEOUT_S = 20`. Sans lui, un appel sortant
sans réponse bloquait le thread appelant — et comme la rédaction était invoquée
depuis une coroutine `async def` sans déport, **c'est la boucle d'événements
entière qui restait bloquée** : plus aucune requête servie, y compris la sonde
de vivacité, qui finissait par tuer un conteneur en bonne santé.

---

# 11. Les indicateurs d'exploitation

**[LU — `kpi.py`]**

> *« Ce module ne contient AUCUNE hypothèse économique. Un chiffre sorti d'ici
> peut être recalculé par un tiers à partir de `DATA.xlsx` et de `tags.yaml`. »*

## 11.1 Les deux niveaux de preuve **[corrigé en S10]**

| niveau | définition |
|---|---|
| `observed` | lu directement dans les données et le référentiel |
| `derived` | passe par un **artefact ajusté** — référence thermique ou détecteur. Hérite du choix de la période de référence. |

| indicateur | niveau |
|---|---|
| Disponibilité moyenne des mesures | `observed` |
| Exposition cumulée aux conditions corrosives | `observed` |
| Charge d'alertes (épisodes/mois) | **`derived`** |
| Marche durablement sous consigne | **`derived`** |
| Taux horaire de signalement | **`derived`** |

## 11.2 Les chiffres marquants **[DÉCLARÉ]**

**Stabilité de régulation** — part du temps où la sortie s'écarte de plus de
1 °C de sa consigne : **0 % en janvier, juin et décembre, plus de 90 % en
octobre**. *« Un écart qu'aucun tableau de bord actuel ne fait apparaître. »*

**Taux horaire de signalement** — indicateur ajouté après audit. La docstring
du code annonce « cinq fois » et « dépasse 40 % » : **ces deux chiffres sont
périmés**, la mesure donne 3,00 × et 26,9 % (§ 15.0). Le fond de l'argument
tient, sa formulation chiffrée doit être reprise :

> *« Le projet calibrait le détecteur sur 2 % et n'affichait que la charge
> d'épisodes agrégés (~5 par mois), ce qui donnait l'impression d'un système
> sobre. Le taux HORAIRE réel est **trois fois supérieur** au paramètre de
> conception, et **atteint 26,9 % en octobre 2024**. Un opérateur devant un
> poste où quatre heures sur dix sont signalées cesse de regarder l'écran. »*

Ce chiffre doit être affiché **à côté** de la charge d'épisodes, *« faute de quoi
l'agrégation masque le problème qu'elle prétend résoudre »*.

**Exposition corrosive** — sur cette période, la conduite n'expose pratiquement
jamais le faisceau à des conditions agressives. Formulation retenue :

> *« Le vieillissement observé relève de l'âge et de l'érosion, non du régime de
> marche. »*

Et le principe : *« Un indicateur proche de zéro EST un résultat. »*

**Sur-refroidissement** — critère strict : écart < −0,5 °C **et** dérive de la
référence > +1 σ. Lecture :

> *« Constat de conduite, pas de dégradation : la vanne d'eau de mer travaille
> plus qu'il n'est nécessaire, ce qui **consomme par avance la marge disponible
> pour compenser un futur encrassement**. »*

**Pourquoi les MWh ont été retirés** — argument d'honnêteté à citer :

> *« La formulation était trompeuse à deux titres. D'abord parce qu'elle appelle
> immédiatement la question du coût, à laquelle la réponse honnête est "presque
> rien" : l'eau de mer circule de toute façon et la pompe ne module pas, seule
> la vanne s'ouvre. Ensuite parce qu'elle déplaçait un constat de CONDUITE vers
> un registre économique que ce projet n'a pas les données pour traiter. »*

---

# 12. La méthode de travail

Cette section est un **atout du mémoire** : elle montre une démarche, pas
seulement un résultat.

## 12.1 Les règles de l'audit

1. **Lire chaque fichier entièrement**, jamais par extraits.
2. **Aucun `grep` n'établit une absence** — suivre la donnée jusqu'à son point
   de rendu, les champs sont renommés en transit.
3. **Prouver chaque correction par mutation** : réintroduire le défaut, vérifier
   que le contrôle échoue, restaurer.
4. **Ne pas réimplémenter pour tester** — importer le prédicat réel.
5. **Se corriger explicitement** quand on a eu tort.
6. **Consigner au fur et à mesure**, pas à la fin.

## 12.2 Le « patron » — un test qui interdit la réapparition d'un défaut

Invention méthodologique du projet, employée **neuf fois**. Plutôt que de
corriger un défaut et d'espérer, on écrit un test qui **analyse le source**
(AST, `inspect.getsource`) et échoue si le défaut revient.

Exemples : *aucun rattachement ne cite une feature hors modèle* ·
*toute sévérité imposée par l'AMDEC correspond à ce que les règles émettent* ·
*tout statut de promotion déclaré est productible* · *aucune mutation dite non
ciblée ne vise un contrôle* · *tout indicateur lisant une grandeur ajustée est
marqué `derived`*.

## 12.3 Le motif central découvert par l'audit

> **Ce qui est exécuté reste juste. Ce qui est seulement lu dérive.**

Sur **18 occurrences** recensées de « corrigé à un endroit, pas à son jumeau »,
c'est presque toujours **le code de service qui porte la version juste** et
**l'affichage ou le document qui porte la version périmée**.

**Trois exceptions connues — S27-2, S32-1, S46-1** — et la troisième reformule la
règle. En S46-1, le code portait la version FAUSSE : mais dans une *docstring*.
Commentaires et docstrings sont de la documentation qui habite le code ; ils
vieillissent comme des documents, parce que **rien ne les exécute**. La frontière
n'est donc pas code / document, elle est **exécuté / seulement lu**.

Ordre de fraîcheur constaté :

```
code/artefacts → README → ADR → rapport_technique.md → architecture.md → notebook
```

Ordre de fraîcheur établi :

```
code / artefacts  →  README  →  ADR  →  rapport_technique  →  architecture  →  notebook
```

**C'est un résultat en soi**, et il mérite une place dans le mémoire : dans un
dépôt traversé par plusieurs intervenants, la documentation dérive **toujours
dans le même sens**.

## 12.4 Le second motif : des affirmations justes à côté d'un code qui ne les tient pas

Quatre exemples, tous trouvés en lecture intégrale et **invisibles en lecture
partielle** :

| affirmation | réalité |
|---|---|
| *« Les accesseurs de lecture ne prennent pas le verrou »* (commentaire justifiant une publication atomique) | les trois méthodes voisines mutaient le dictionnaire **en place** |
| *« Les deux modules ne peuvent plus diverger »* (docstring de `thermal`) | `sensitivity` recopiait la formule **sans sa garde** |
| *« Un test parcourt les sorties pour vérifier qu'aucun nombre n'échappe à la règle »* | les 23 messages du moteur de règles écrivaient « 66.3 °C » |
| graine fixée *« sinon le chiffre change à chaque exécution »* | l'appel suivant laissait un LLM ajuster ±1,5 point |

**Leçon transposable** : quand un commentaire énonce un principe, il faut aller
vérifier que le code voisin le respecte. C'est là que sont les défauts.

## 12.5 Le troisième motif : des contrôles dont le dénominateur contient des non-événements

Deux bancs de gouvernance, deux chiffres publiés, la même faille :

- une **mutation qui ne mute rien** comptée comme non-détection ;
- une **fenêtre « calme » parce que la ligne est à l'arrêt**, où l'injection est
  un no-op, comptée comme non-détection.

Dans les deux cas le biais était **prudent** — il abaissait le chiffre. Position
retenue : *un chiffre faussé dans le bon sens reste un chiffre faussé.*

## 12.6 Quatre rétractations, à assumer

L'audit s'est trompé et l'a écrit :

1. `Tag.confidence` déclaré inexistant sur la foi d'un `grep "def confidence"` —
   c'est un **champ de dataclass**.
2. `ntu_de()` et `EFFECTIVENESS_MAX` déclarés morts — ils sont **appelés dans le
   même module**.
3. `EXTERNAL_DATA_GATES`, code mort **introduit par l'audit lui-même**, et
   retiré à ce titre.
4. Une correction typographique qui **cassait un test** en accentuant un texte
   que le test cherchait sans accents.

---

# 13. Les limites du projet — à énoncer sans détour

Elles font la crédibilité du mémoire. Aucune ne doit disparaître à la
réécriture.

| # | limite |
|---|---|
| 1 | **Aucune vérité terrain.** Pas d'historique GMAO, pas de panne étiquetée. Deux portes de déploiement sont en échec définitif, et c'est le résultat correct. |
| 2 | **UA est apparent.** Le débit d'eau de mer n'est pas instrumenté ; la vanne masque un début d'encrassement tant qu'elle a de la marge. |
| 3 | **La période de référence est arbitraire.** Le « zéro encrassement » est une conséquence de la fenêtre à 40 %, pas un constat sur l'équipement. |
| 4 | **Le contrôleur n'est pas une validation indépendante.** Il recalcule avec les mêmes données et les mêmes référentiels. |
| 5 | **Le banc d'injection est une borne supérieure.** Il valide qu'un encrassement conforme au modèle serait vu, pas la signature physique réelle. |
| 6 | **Deux modes de criticité 112 ne sont pas instrumentés.** La couverture par les données n'est qu'une part du risque. |
| 7 | **Le sens des tags est établi par recoupement**, faute de fiche d'instrumentation. |
| 8 | **L'authentification est un démonstrateur mono-poste.** La production exige OIDC. |
| 9 | **Le registre de workflows ne remplace ni GMAO ni permis HSE.** |
| 10 | **`t_in_residual_z` est confondu côté procédé** : une dérive de l'entrée peut venir de la tour de séchage. |

---

# 14. Annexes factuelles

## 14.1 Le barème de confiance partagé **[LU — `schemas.confiance_justifiable`]**

Formule exacte. L'agent l'utilise pour **annoncer**, le contrôleur pour
**vérifier** — c'est le même appel de fonction, pas deux implémentations.

```
valeur = 0,50                                    base
       + 0,20   si une constatation déterministe porte une preuve
       + 0,10   si les deux étages se corroborent
       + 0,10   si le modèle statistique est applicable
       − 0,15 × min(n_points_en_défaut, 2)
       − 0,15   si l'état n'est pas RUNNING
       (pénalité graduée selon l'observabilité du mode dominant)

borné dans [0,15 ; 0,95]
```

`CONFIANCE_MAX = 0,95` est un **plafond absolu** : aucune combinaison de preuves
ne le franchit. Annoncer au-delà n'est pas un écart d'appréciation, c'est
revendiquer une certitude que le barème ne peut pas produire — d'où un contrôle
V5 distinct, avant celui de la tolérance.

**Tolérances du contrôleur** : +0,12 à la hausse (serré — *« une quasi-certitude
affichée doit être gagnée, pas supposée »*), −0,30 à la baisse.

## 14.2 Les trois contrats de données **[LU]**

Ce que le système produit à chaque horodatage, dans l'ordre de la chaîne.

**`DetectionResult`** — sortie du détecteur

| champ | contenu |
|---|---|
| `timestamp`, `process_state`, `severity` | instant, état, sévérité consolidée |
| `anomaly_score`, `model_is_anomaly` | score normalisé [0,1] et verdict binaire |
| `findings` | constatations des deux étages (`code`, `source`, `severity`, `amdec_mode`, `message`, `evidence`) |
| `attributions` | contributions par occlusion (`feature`, `value`, `reference`, `contribution`, `score_if_normal`) |
| `measurements` | 19 grandeurs clés de l'instant |
| `data_quality` | `n_invalid_tags`, `model_applicable` |
| `amdec_modes` *(propriété)* | modes distincts invoqués |

**`AgentDecision`** — diagnostic

| champ | contenu |
|---|---|
| `severity`, `amdec_modes`, `anomaly_score` | conclusion |
| `diagnosis`, `reasoning` | deux textes de rôles distincts |
| `recommended_action` | `description`, `urgency`, `execution_window`, `requires_shutdown`, `maintenance_task_ref`, `checklist_ref`, `responsible` |
| `confidence` | issue du barème partagé |
| `evidence_refs`, `lead_finding` | codes repris, constatation dominante |
| `cited_values` | valeurs numériques annoncées — **c'est la prise du contrôleur** |
| `generated_by` | `rules` ou `llm` |

**`JudgeVerdict`** — jugement

| champ | contenu |
|---|---|
| `global_score`, `deterministic_score`, `llm_score` | notes /10 |
| `agreement` | `global_score ≥ 6,0` |
| `checks` | les huit `Check` (`id`, `label`, `passed`, `weight`, `score`, `detail`, `issue_codes`) |
| `flagged_issues`, `corrected_severity` | anomalies, sévérité que le Judge aurait retenue |
| `verified_facts` | faits **recalculés**, jamais lus dans la décision |
| `feedback`, `limitations`, `evidence_refs` | synthèse et portée |
| `rule_version`, `model_runtime_signature` | traçabilité : SHA de l'AMDEC, signature du modèle |

## 14.3 Glossaire

| terme | définition |
|---|---|
| **UA** | coefficient d'échange global, kW/K. Produit du coefficient de transfert et de la surface. Ce que l'encrassement dégrade. |
| **UA apparent** | UA calculé sans mesure du débit d'eau de mer : produit de l'état de la surface **et** de l'action de la boucle froide. |
| **ε (efficacité)** | part de la chaleur théoriquement disponible réellement extraite. |
| **NTU** | nombre d'unités de transfert, `−ln(1 − ε)`. Évite la moyenne logarithmique et sa singularité. |
| **Rf** | résistance d'encrassement, K/kW : `1/UA − 1/UA_attendu`. |
| **AMDEC** | Analyse des Modes de Défaillance, de leurs Effets et de leur Criticité. |
| **C = F × G × N** | criticité = Fréquence × Gravité × Non-détection, chacun coté 1 à 10. |
| **MTBF** | temps moyen entre défaillances, en heures — barème de la cotation F. |
| **GMAO** | gestion de maintenance assistée par ordinateur. Sa **vérité terrain manque**, d'où deux portes en échec définitif. |
| **PSI** | *Population Stability Index*, mesure de dérive de distribution. |
| **Isolation Forest** | détecteur d'anomalies non supervisé isolant les points atypiques par partitions aléatoires. |
| **Occlusion exacte** | attribution : on remplace une feature par sa médiane et on recalcule le score. La chute mesure sa contribution. |
| **Dittus-Boelter** | corrélation de convection forcée en régime turbulent ; l'exposant 0,8 sur Reynolds justifie `F_ACID^0,8`. |
| **ISA-5.1 / 18.2 / 101** | normes : nomenclature d'instrumentation / gestion des alarmes / conception des IHM. |
| **Marche établie (RUNNING)** | seul état où juger la performance de l'échangeur a un sens. |
| **Période de référence** | fenêtre servant à apprendre le comportement normal : 40 % initiaux des heures de marche. |
| **Le « patron »** | test qui interdit la réapparition d'un défaut par analyse du source, pas par exécution. |

## 14.4 Ce que cette partie ne peut PAS fournir, même dans son périmètre

Trois manques que la partie B ne comblera pas non plus, et qu'il faut produire :

1. **Aucun exemple travaillé de bout en bout.** Pas un seul horodatage réel
   suivi de sa détection, son diagnostic et son verdict. Un mémoire technique en
   a besoin — c'est ce qui rend la chaîne concrète pour un jury. **À produire
   par exécution.**
2. **Aucun résultat issu d'un run.** Tous les chiffres [DÉCLARÉ] viennent des
   commentaires du code. À confirmer par exécution avant publication :
   `make judge-eval`, banc d'injection, sensibilité, backtest.
3. **Les dates exactes de la période de référence** ne sont pas établies ici.
   Elle vaut les 40 % initiaux des heures de marche du corpus
   (2024-01-01 07:00 → 2025-02-28 11:00), mais la borne exacte dépend du
   décompte des heures RUNNING et doit être lue dans
   `references.conductance.train_period`.

## 14.5 Les figures que le rapport devrait porter

Proposées d'après le contenu réel du système. Toutes sont productibles depuis la
chaîne ; aucune n'existe dans le dépôt à ce jour (`rapport/figures` a été sorti
en phase A).

| # | figure | source |
|---|---|---|
| 1 | Schéma de l'échangeur : acide côté calandre, eau de mer côté tubes, position des 6 capteurs du périmètre | `topology.yaml` |
| 2 | Chaîne de traitement, de `DATA.xlsx` au poste | § 4.1 |
| 3 | **Distribution de `T_ACID_OUT`** — la bande de 3 °C qui condamne l'approche générique | corpus |
| 4 | **UA observé contre UA attendu**, sur 14 mois, avec la saisonnalité de l'eau de mer superposée | `/api/timeseries` |
| 5 | Climatologie de Safi interpolée au jour | `seawater_temperature()` |
| 6 | **Nuage résidu de duty × écart de consigne**, r = −0,938 — la preuve visuelle d'ADR-001 | `independence_report()` |
| 7 | Couverture AMDEC : 30,2 % / 18,5 % / 51,2 % en anneau | § 7.3 |
| 8 | Banc d'injection : **avancement à la détection** par sévérité et durée de rampe | `FoulingInjectionBench` |
| 9 | **Sensibilité à la période de référence** — la part d'heures déclarées en encrassement selon la fenêtre | `reference_period_sensitivity()` |
| 10 | Distribution des notes du Judge, saines contre mutées, avec la séparation | `JudgeEvaluator` |
| 11 | Taux horaire de signalement **mois par mois** — là où la moyenne ment | `monthly_flag_rate()` |
| 12 | Capture du poste : vue Salle avec le jumeau 3D | interface |

**La figure 6 est la plus importante du mémoire** : elle montre en un coup d'œil
que l'indicateur de la v1 était l'écart de consigne réécrit. C'est l'argument
qui justifie toute la refonte.

## 14.6 La chronologie du projet — le récit à tenir

| étape | ce qui s'est passé |
|---|---|
| **v1** | z-scores génériques sur capteurs quelconques. Échoue : la sortie acide est régulée. |
| **v2** | « jumeau thermique » : résidu de duty présenté comme indicateur d'encrassement. Le R² de 0,968 semble excellent. |
| **audit** | démonstration algébrique que ce R² est **circulaire** : 0,962 sans apprentissage, r = −0,938 avec l'écart de consigne. L'indicateur est l'écart de consigne réécrit. |
| **v3 — ADR-001** | l'indicateur devient **UA**, le résidu de duty est renommé `regulation_effort` et perd toute valeur de preuve. |
| **v3 — ADR-002** | UA n'est calculable qu'avec la température du fluide froid : la **climatologie de Safi** entre comme donnée externe. |
| **gouvernance** | faute de vérité terrain, on construit ce qui peut l'être : banc d'injection, banc d'évaluation du contrôleur, sensibilité, portes de déploiement. |
| **audits S1–S11** | relecture intégrale de la chaîne de production ; 18 cas de « corrigé d'un côté, pas de son jumeau », deux dénominateurs de bancs faussés, un barème de confiance divergent, neuf verrous par analyse du source. |

**Ce récit est un atout, pas un aveu.** Un mémoire qui montre qu'il a réfuté sa
propre v2 par l'algèbre, et qui publie la sensibilité de ses conclusions à ses
propres choix arbitraires, est plus solide qu'un mémoire sans faux pas.

---

# 15. RÉSULTATS MESURÉS

**[MESURÉ]** — exécution complète de la chaîne le 2026-08-07 sur le corpus
2024-01-01 07:00 → 2025-02-28 11:00. Script : `scripts/collecte_chiffres_rapport.py`,
sortie brute : `reports/chiffres_rapport.txt`.

**Cette section prime sur tout `[DÉCLARÉ]` du document.** Là où les deux
divergent, c'est la mesure qui fait foi.

## 15.0 Trois chiffres du code sont faux — à ne pas reprendre

| affirmation du code | source | **mesure** |
|---|---|---|
| « le taux horaire réel est **cinq fois** supérieur au paramètre de conception » | `kpi.flag_rate` docstring | **3,00 ×** (et 2,88 × en moyenne sur la grille) |
| « dépasse **40 %** sur certains mois » | `kpi.flag_rate` docstring | maximum **26,9 %** (octobre 2024) |
| « **1 385** heures d'arrêt, 13,6 % des horodatages » | `detection_agent` docstring | **1 251 h**, **12,3 %** |
| « ~**5** épisodes par mois » | `kpi.flag_rate` docstring | **4,10** épisodes/mois |

Ce sont des chiffres périmés dans les commentaires, pas des défauts de calcul.
**Ils ne doivent pas passer dans le rapport.** Le contrôle
`test_aucun_chiffre_cle_ne_contredit_les_artefacts` devrait être étendu pour
les verrouiller.

## 15.1 Ingestion **[MESURÉ]**

| | |
|---|---|
| Lignes brutes | 10 182 |
| **Lignes retenues** | **10 180** (2 doublons fusionnés) |
| Trous temporels | **1** |
| Hors ordre | 0 |
| **Événements qualité** | **8 995** |

**Répartition des états procédé :**

| état | heures | part |
|---|---|---|
| **RUNNING** | **8 832** | **86,8 %** |
| STOPPED | 1 251 | 12,3 % |
| TRANSIENT | 97 | 1,0 % |

**Santé des capteurs — disponibilité croissante :**

| tag | rôle | dispo | h en défaut | motif dominant |
|---|---|---|---|---|
| `TI_5303` | degraded | **47,83 %** | 5 311 | **5 170 h saturé** |
| `PHI_5306` | degraded | 85,43 % | 1 483 | **1 344 h figé** |
| `C_ACID_1200` | primary | 93,93 % | 618 | 515 h saturé |
| `C_ACID_1100` | primary | 94,00 % | 611 | 536 h saturé |
| `F_3412` | context | 96,99 % | 306 | 231 h hors plage |
| `T_ACID_OUT` | primary | 98,52 % | 151 | gel |
| `LOAD_SULFUR` | context | 98,90 % | 112 | |
| `F_ACID` | primary | 99,06 % | 96 | |
| `A_3302`, `A_3301` | context | 99,24 % | 77 | |
| `T_ACID_IN`, `T_CIRC_1300` | primary/sec. | 99,26 % | 75 | |

**Fait non documenté jusqu'ici, à signaler dans le rapport** : les **deux
analyseurs de titre** sont saturés ~520 h chacun, soit 6 % du temps. Ce sont
les capteurs les moins disponibles du périmètre surveillé — et ce sont eux qui
portent le mode le plus grave détectable, `FAISCEAU_FUITE`.

Disponibilité moyenne du périmètre surveillé : **97,34 %** sur 6 capteurs.

## 15.2 Les trois références — ADR-009 vérifié **[MESURÉ]**

**Les trois partagent exactement la même borne : `2024-07-13 17:00`.** La
correction d'ADR-009 est confirmée par la mesure — auparavant elles
s'arrêtaient à 17 h, 18 h et 21 h.

| référence | période | n heures | R² | σ résidu |
|---|---|---|---|---|
| Conductance (UA) | 2024-01-01 07:00 → **2024-07-13 17:00** | **3 505** | **0,9244** | 0,626 kW/K |
| Effort de régulation | idem | **3 505** | **0,9682** | 24,38 kW |
| Température d'entrée | idem | **3 532** | **0,4791** | 1,532 °C |

**Les effectifs diffèrent (3 505 / 3 505 / 3 532) alors que la fenêtre est
identique** : chaque référence écarte ses propres trous. C'est exactement la
propriété que le code annonce.

### ADR-001 confirmé par la mesure

| | |
|---|---|
| R² de la référence d'effort | **0,9682** |
| R² d'une reconstruction **sans apprentissage** | **0,9623** |
| **apport réel du modèle appris** | **0,0059** |

Coefficients de la référence d'effort — on y lit la circularité :
`LOAD_SULFUR` +17,86 · `F_ACID` **−62,36** · `T_ACID_IN` −14,18 ·
`conc_min` +25,28 · **`F_ACID × T_ACID_IN` +0,862** · const −1 425,9.

Le terme croisé et le terme en débit dominent : c'est bien la définition du
duty que la régression retrouve.

### Coefficients de la référence de conductance

`F_ACID^0,8` **+1,0515** · `T_acide_moyenne` +0,2900 · **`T_eau_de_mer`
+0,8173** · const −46,54. UA moyen de référence : **17,766 kW/K**.

Le coefficient sur l'eau de mer est le troisième en poids : c'est la
saisonnalité que la régression retire.

**À noter** : le R² de la référence d'entrée n'est que de **0,479**. C'est le
plus faible des trois, et c'est cohérent avec son rôle — la température
d'entrée est une variable **libre**, mal expliquée par la charge et le débit
seuls. Le rapport doit le dire plutôt que de le taire.

## 15.3 Indépendance des indicateurs **[MESURÉ]**

| indicateur | r avec l'écart de consigne | variance partagée | indépendant |
|---|---|---|---|
| `regulation_effort_z` | **−0,9378** | **87,9 %** | non |
| `ua_residual_z` | **−0,5366** | 28,8 % | non |
| `t_in_residual_z` | **+0,0332** | **0,1 %** | **oui** |

Les trois valeurs annoncées par le code (−0,94 / −0,54 / +0,03) sont
**confirmées à la deuxième décimale**.

## 15.4 UA mois par mois — la saisonnalité **[MESURÉ]**

| mois | UA obs. | UA att. | T mer | Rf | résidu z |
|---|---|---|---|---|---|
| 2024-01 | **13,81** | 14,46 | 17,7 | +0,00312 | **−1,03** |
| 2024-02 | 15,43 | 15,57 | 17,1 | +0,00054 | −0,23 |
| 2024-03 | 17,51 | 17,37 | 17,3 | −0,00078 | +0,23 |
| 2024-04 | 17,09 | 17,35 | 17,9 | +0,00085 | −0,43 |
| 2024-05 | 18,96 | 18,20 | 18,7 | −0,00222 | +1,21 |
| 2024-06 | 19,31 | 19,52 | 19,7 | +0,00055 | −0,34 |
| 2024-07 | 20,51 | 20,46 | 20,7 | −0,00012 | +0,08 |
| 2024-08 | 21,79 | 21,32 | 21,6 | −0,00098 | +0,76 |
| 2024-09 | **21,86** | 21,38 | 21,8 | −0,00102 | +0,77 |
| 2024-10 | 21,56 | 20,44 | 21,1 | −0,00264 | **+1,80** |
| 2024-11 | 19,49 | 19,16 | 19,7 | −0,00081 | +0,52 |
| 2024-12 | 18,73 | 18,47 | 18,4 | −0,00075 | +0,41 |
| 2025-01 | 18,51 | 17,75 | 17,5 | −0,00236 | +1,21 |
| 2025-02 | 18,60 | 17,33 | 17,1 | −0,00432 | **+2,01** |

**UA suit la température d'eau de mer** : minimum **13,81 kW/K en janvier 2024**
(eau à 17,7 °C), maximum **21,86 kW/K en septembre 2024** (eau à 21,8 °C).
Rapport max/min = **1,58**, cohérent avec le « facteur 1,6 » annoncé.

**Observation qui mérite d'être discutée dans le rapport** : le résidu
normalisé **monte** en fin de corpus (+1,21 en janvier 2025, **+2,01 en février
2025**) — l'échangeur transmet *mieux* que ne le prédit la référence, pas moins.
Ce n'est pas un encrassement ; c'est le signe que la référence, apprise en
hiver-printemps, sous-estime UA quand l'eau est de nouveau froide. C'est
exactement le mécanisme que l'analyse de sensibilité décrit.

## 15.5 Détection **[MESURÉ]**

| | |
|---|---|
| Seuil de décision | **0,9643** |
| Heures de marche | 8 832 |
| **Heures signalées** | **530** |
| **Taux de signalement** | **6,00 %** |
| **Ratio à la contamination visée** | **3,00 ×** |
| Effectif d'entraînement | 3 367 h (2024-01-02 07:00 → 2024-07-13 17:00) |

**Taux mois par mois — la moyenne ment, et voici de combien :**

| mois | part signalée | | mois | part signalée |
|---|---|---|---|---|
| 2024-01 | 0,8 % | | 2024-08 | 2,4 % |
| 2024-02 | 10,7 % | | 2024-09 | 3,6 % |
| 2024-03 | 1,3 % | | **2024-10** | **26,9 %** |
| 2024-04 | 2,3 % | | 2024-11 | 13,9 % |
| 2024-05 | 1,5 % | | 2024-12 | 0,7 % |
| 2024-06 | 0,5 % | | 2025-01 | 2,6 % |
| 2024-07 | 4,5 % | | 2025-02 | 14,0 % |

**Écart de 1 à 54 entre le mois le plus calme (juin, 0,5 %) et le plus chargé
(octobre, 26,9 %).** C'est l'argument central du KPI de charge d'alertes.

**Épisodes agrégés : 58**, soit **4,10 par mois** sur 424 jours. Durée médiane
**7 h**, maximum **38 h**.

Les cinq plus marqués :

| début | durée | h atypiques | marge max |
|---|---|---|---|
| **2024-10-25 04:00** | **38 h** | 23 | **+5,40 σ** |
| 2025-02-19 14:00 | 5 h | 4 | +4,65 σ |
| 2025-01-29 08:00 | 4 h | 4 | +4,21 σ |
| 2024-03-26 09:00 | 3 h | 2 | +3,94 σ |
| 2025-02-20 02:00 | 35 h | 23 | +3,52 σ |

La marge en sigma **sépare bien** les épisodes (5,40 à 3,31 sur les dix
premiers) là où le score sature tout à 0,999x. C'est la justification empirique
de la correction décrite au § 6.3.

## 15.6 Les indicateurs d'exploitation **[MESURÉ]**

| indicateur | valeur | niveau |
|---|---|---|
| Disponibilité moyenne des mesures | **97,34 %** | observed |
| Charge d'alertes | **4,10 épisodes/mois** | derived |
| Exposition cumulée aux conditions corrosives | **2 h** sur 8 832 (**0,02 %**) | observed |
| **Marche durablement sous consigne** | **29,89 %** du temps de marche | derived |
| Taux horaire de signalement | **6,0 %** | derived |

**Le chiffre le plus fort du lot, et il n'était nulle part** : la ligne passe
**29,89 % de son temps de marche** — **2 640 heures** — durablement sous
consigne, à **1,7 °C en dessous** en moyenne. Ce n'est pas une dégradation,
c'est un **régime de conduite**, et il *« consomme par avance la marge
disponible pour compenser un futur encrassement »*.

**Stabilité de régulation, mois par mois** — l'écart moyen à la consigne et la
part du temps hors bande de 1 °C :

| mois | écart moyen | hors bande |
|---|---|---|
| 2024-01 | −0,004 °C | 0,3 % |
| 2024-02 | +0,361 °C | 0,7 % |
| 2024-03 | +0,016 °C | 1,6 % |
| 2024-04 | −0,097 °C | 1,8 % |
| **2024-05** | **−1,474 °C** | **87,0 %** |
| 2024-06 | −0,006 °C | 0,0 % |
| 2024-07 | −0,123 °C | 1,4 % |
| **2024-08** | **−1,358 °C** | **82,0 %** |
| **2024-09** | **−1,652 °C** | **96,8 %** |
| **2024-10** | **−1,777 °C** | **99,1 %** |
| 2024-11 | −0,532 °C | 36,2 % |
| 2024-12 | +0,003 °C | 0,0 % |
| 2025-01 | −0,003 °C | 0,3 % |
| 2025-02 | −0,272 °C | 18,3 % |

**Le régime bascule.** Cinq mois quasi parfaits (0,0 à 1,8 % hors bande) et
quatre mois où la ligne est hors bande **plus de 80 % du temps**, toujours
**du côté froid**. Octobre 2024 : 99,1 %. C'est un fait d'exploitation majeur
qu'aucun tableau de bord ne faisait apparaître, et il est **entièrement
observé**, sans modèle.

## 15.7 Un exemple travaillé — 2024-01-15 15:00 **[MESURÉ]**

État : **RUNNING**. Instant retenu comme le plus sévère parmi les notables.

**Mesures** : charge 11,50 t/h · débit **29,21 m³/h** · entrée 84,85 °C ·
sortie 65,60 °C · titre 98,64 % · Δt 19,25 °C · duty 394,5 kW · eau de mer
17,5 °C · **UA 6,90 kW/K** pour 5,22 attendu · résidu UA **+2,67 σ**.

**Constatations :**

| code | sévérité | mode | message |
|---|---|---|---|
| `FLOW_LOW` | WARNING | CALANDRE_FUITE | Débit acide à 29,2 m³/h (seuil L 35,0 m³/h) |
| `MODEL_ANOMALY_ISOLATED` | INFO | — | 1 h atypique sur 4 exploitables des 6 dernières |

**Attribution du modèle** (score 0,9873 / seuil 0,9643) :

| feature | valeur | référence | contribution |
|---|---|---|---|
| `t_in_local_z` | **−3,73 σ** | +0,01 | 0,0303 |
| `t_out_local_z` | −3,61 σ | −0,01 | 0,0208 |
| `flow_per_load` | 2,54 | 3,08 | 0,0155 |
| `ua_residual_z` | +2,67 | −0,17 | 0,0094 |
| `conc_bias_drift_z` | +1,69 | +0,23 | 0,0061 |

**Diagnostic** : WARNING, confiance **0,80**, mode CALANDRE_FUITE, constatation
dominante `FLOW_LOW`.

**Action** : urgence **SOUS_24H**, fenêtre **EN_MARCHE**, arrêt non requis,
tâche **C** (inspection externe mensuelle), check-list INSPECTION_EXTERNE,
Service Mécanique PS III.

**Verdict du contrôleur : 10,0 / 10, accord, aucune anomalie.** Les huit
contrôles passent, dont V5 : *« Confiance 0,80 cohérente avec les 0,80
justifiables par les preuves disponibles »* — le barème partagé fonctionne.

**Ce cas illustre trois choses utiles au rapport :** le modèle statistique
signale la combinaison (chute simultanée des deux températures face à leurs
24 h) sans désigner de cause ; la règle déterministe porte le diagnostic ; et
le contrôleur vérifie les deux sans rien avoir à croire sur parole.

## 15.8 Backtest et portes de déploiement **[MESURÉ]**

**Revendication du système** : *« non démontrable avec le corpus disponible ;
aucune AUC, précision, rappel ou réduction de panne revendiquée »*.

| porte | état | mesure |
|---|---|---|
| `causalite_temporelle` | **PASSE** | aucun décalage négatif ; chaîne vérifiée sur 3 troncatures (40, 60, 80 %) |
| `redondance_features` | **PASSE** | 0 paire redondante ; conditionnement **3,09** |
| `redondance_hors_modele` | ÉCHEC | 2 grandeurs redondantes avec une variable régulée ; la plus forte **r = −0,938**. Propriété algébrique permanente (ADR-001), **publiée, non bloquante** |
| `stabilite_hors_periode` | **PASSE** | alertes **7,8 %** hors référence pour 15,0 % admis ; dispersion du seuil **0,001** |
| `derive_de_distribution` | ÉCHEC | **aucun des 4 plis n'est mesurable** — voir ci-dessous |
| `labels_gmao` | ÉCHEC | aucune date de panne dans le corpus |
| `validation_externe` | ÉCHEC | aucune annotation indépendante |

**Backtest temporel, 4 plis à fenêtre croissante, écart causal de 25 h :**

| pli | train | test | n test | taux d'alerte | **PSI** | extrapolation saisonnière |
|---|---|---|---|---|---|---|
| 1 | → 2024-03-25 | 03-26 → 06-18 | 1 786 | **16,07 %** | 1,99 | 0,76 |
| 2 | → 2024-06-17 | 06-19 → 09-10 | 1 837 | 4,41 % | **3,18** | **1,00** |
| 3 | → 2024-09-10 | 09-11 → 12-05 | 1 873 | 7,26 % | 0,58 | 0,05 |
| 4 | → 2024-12-04 | 12-05 → 02-28 | 1 908 | **3,46 %** | **0,068** | 0,13 |

**Le résultat le plus intéressant du backtest**, et il faut le raconter : le PSI
et l'extrapolation saisonnière **varient ensemble**. Le pli 2 extrapole
totalement hors de la plage d'eau de mer vue à l'apprentissage
(extrapolation = 1,00) et affiche PSI = 3,18 ; le pli 4, qui n'extrapole
presque pas (0,13), affiche PSI = 0,068 — quarante-sept fois moins.

**Le PSI ne mesure donc pas une dérive du modèle : il mesure l'année incomplète
de la fenêtre croissante.** C'est pourquoi la porte est publiée et non
bloquante, et pourquoi le seuil de 0,25 — issu du scoring de crédit, où les
populations comparées sont supposées échangeables — n'est pas transposable tel
quel à des scores d'anomalie non supervisés. Le système le dit lui-même dans
l'évidence de la porte.

**État de la chaîne** : modèle `runtime_trained_unpromoted`, statut de promotion
`candidate` — *« statut non autorisé au runtime »*. Agent en mode `rules`,
contrôleur en mode `deterministic`. **La promotion est légitimement impossible**,
et c'est le résultat correct.

## 15.9 Sensibilité — LE résultat du mémoire **[MESURÉ]**

### Contamination

| valeur | seuil | taux signalé | ratio | heures |
|---|---|---|---|---|
| 0,005 | 0,9925 | 1,53 % | 3,06 × | 135 |
| 0,01 | 0,9846 | 2,76 % | 2,76 × | 244 |
| **0,02** | **0,9643** | **6,00 %** | **3,00 ×** | **530** |
| 0,05 | 0,8980 | 14,75 % | 2,95 × | 1 303 |
| 0,10 | 0,8143 | 26,48 % | 2,65 × | 2 339 |

**Ratio moyen 2,88 ×, dispersion 0,41.** Le facteur est **stable sur toute la
grille** : la contamination est un levier fiable pour régler le volume
d'alertes, mais elle ne se lit pas comme le taux attendu. Pour viser 2 %
d'heures signalées, il faut paramétrer environ **0,7 %**.

### Période de référence — ce n'est pas une sensibilité, c'est une falaise

| fraction | fin de référence | n ref UA | R² UA | σ UA | min résidu | **h en encrassement** | **part** |
|---|---|---|---|---|---|---|---|
| **0,25** | 2024-05-14 13:00 | 2 208 | 0,941 | 0,533 | **−6,41 σ** | **4 605** | **52,14 %** |
| **0,40** | 2024-07-13 17:00 | 3 505 | 0,924 | 0,626 | −1,22 σ | **0** | **0,00 %** |
| 0,55 | 2024-09-08 00:00 | 4 830 | 0,953 | 0,575 | −1,35 σ | 0 | 0,00 % |
| 0,70 | 2024-11-04 10:00 | 6 106 | 0,948 | 0,632 | −1,26 σ | 0 | 0,00 % |

**Dispersion : 52,14 points.**

C'est plus tranché que « sensible ». La fenêtre à **25 % déclare 52 % du corpus
en encrassement** ; les trois autres en déclarent **exactement zéro**. Le résidu
minimal passe de **−6,41 σ** à −1,22 σ — un facteur cinq — d'une fenêtre à la
suivante.

**L'explication est datée.** La fenêtre à 25 % s'achève le **14 mai 2024**,
avant la remontée saisonnière de l'eau de mer. Elle apprend un UA bas et lit
ensuite comme une dérive toute la saison chaude. La fenêtre à 40 % s'achève le
**13 juillet** et couvre le début de cette remontée.

**Formulation pour le mémoire** :

> Le « zéro heure d'encrassement sur quatorze mois » n'est pas un constat sur
> l'équipement. C'est une propriété de la fenêtre de référence retenue. Une
> fenêtre plus courte de deux mois aurait déclaré la moitié du corpus en
> encrassement. **Aucun chiffre d'encrassement n'est publiable sans la fenêtre
> qui l'a produit.**

## 15.10 Banc d'injection d'encrassement **[MESURÉ]**

| | |
|---|---|
| Scénarios | 8 |
| **Taux de détection brut** | **100 %** |
| **Taux de détection UTILE** (avancement ≤ 50 %) | **37,5 %** |
| **Avancement médian à la détection** | **0,674** |
| Latence médiane | **562 h** (≈ 23 jours) |
| Plus petite perte détectée | 5 % |
| **Faux positifs sur le témoin** | **0,00 %** sur 8 832 h |

| perte UA | durée | détecté | **avancement** | latence |
|---|---|---|---|---|
| 5 % | 30 j | oui | **1,000** | 1 617 h |
| 5 % | 60 j | oui | **1,000** | 3 097 h |
| 10 % | 30 j | oui | 0,781 | 562 h |
| 10 % | 60 j | oui | 0,876 | 1 261 h |
| 20 % | 30 j | oui | 0,568 | 409 h |
| **20 %** | **60 j** | oui | **0,390** | 562 h |
| **30 %** | **30 j** | oui | **0,478** | 344 h |
| **30 %** | **60 j** | oui | **0,322** | 464 h |

**Lecture honnête, et c'est la conclusion la plus importante du banc :** le
détecteur voit **tous** les encrassements simulés — le taux brut de 100 % ne
prouve rien, une dérive finit toujours par franchir le seuil. Ce qui compte est
**quand** : à **5 % de perte, la détection arrive à 100 % d'avancement**,
c'est-à-dire quand tout est déjà consommé. Il faut **20 % de perte sur 60 jours**
pour descendre sous la barre des 50 %.

**Le système est donc utile pour un encrassement franc, aveugle à un
encrassement lent.** Et ce résultat est **optimiste** : l'injection dégrade UA
à débit d'eau de mer inchangé, alors que la régulation réelle ouvrirait la
vanne pour compenser.

Zéro faux positif sur le témoin : la règle ne se déclenche jamais sur les
données réelles non modifiées, ce qui confirme le « zéro encrassement » du
§ 15.9 — **à la fenêtre de référence retenue.**

## 15.11 Banc d'évaluation du contrôleur **[MESURÉ]**

| | |
|---|---|
| Décisions saines | 12 · note moyenne **9,91/10** · validation **100 %** |
| **Faux positifs** | **0,0 %** |
| Cas piégés (non-régression) | **118** |
| **Rappel sur pièges conçus** | **100 %** · 0 faute non sanctionnée |
| Note moyenne des pièges | 5,78 / 10 |
| **Séparation saines / fautives** | **4,13 points** |
| Mutations non ciblées | **58** |
| **TAUX DE GÉNÉRALISATION** | **8,6 %** |
| Pénalisation des mutations non ciblées | **1,7 %** |
| Note moyenne des mutations non ciblées | **9,91 / 10** |

**Détail par type de faute — les dix pièges conçus :**

| faute | n | détection | pénalisation | succès | note moy. |
|---|---|---|---|---|---|
| Valeur inventée | 12 | 100 % | 100 % | 100 % | 4,00 |
| Mode AMDEC inventé | 12 | 100 % | 100 % | 100 % | 4,00 |
| Angle mort revendiqué | 12 | 100 % | 100 % | 100 % | 4,00 |
| Action dangereuse | 12 | 100 % | 100 % | 100 % | 4,00 |
| État de marche erroné | 12 | 100 % | 100 % | 100 % | 5,00 |
| Diagnostic sans chiffres | 12 | 100 % | 100 % | 100 % | 8,13 |
| Sur-confiance | 12 | 100 % | 100 % | 100 % | 9,04 |
| Constatations ignorées | 12 | 100 % | 100 % | 100 % | 9,41 |
| **Sévérité sous-estimée** | 10 | 100 % | **80 %** | **80 %** | 4,77 |
| **Action sous-dimensionnée** | 12 | 100 % | **75 %** | **75 %** | 5,32 |

**Les quatre plafonds de sécurité fonctionnent** : les quatre fautes les plus
graves plafonnent exactement à **4,00/10**, comme prévu.

**Deux pièges détectés mais insuffisamment pénalisés** (80 % et 75 %) : le
contrôleur **relève** l'anomalie mais la note globale reste au-dessus du seuil
toléré dans un cinquième des cas. C'est une limite mesurée, à énoncer.

### Le chiffre à mettre en avant, et sa lecture

> **Non-régression : 100 %. Généralisation : 8,6 %.**

Les 118 pièges conçus portent chacun le code d'anomalie que le contrôleur
implémente : on fabrique une faute pour déclencher V1, puis on mesure que V1 la
détecte. **Ce 100 % dit que les huit contrôles fonctionnent, rien de plus.**

Les 58 mutations non ciblées portent sur ce qu'aucun contrôle ne lit — rôle des
textes intervertis, raisonnement tronqué, action d'un autre mode, mauvais
service, mauvaise check-list. Le contrôleur en attrape **8,6 %**, en pénalise
**1,7 %**, et leur donne une note moyenne de **9,91/10 — exactement celle des
décisions saines.** Autrement dit : **il ne les voit pas.**

**C'est le chiffre honnête du mémoire.** Le contrôleur est un excellent
vérificateur de ce qu'il sait vérifier, et **presque aveugle au reste**. Le
présenter autrement serait la sur-vente que tout ce projet s'est employé à
éviter.

## 15.12 Pourquoi 118 pièges et 58 mutations, et pas 120 et 60

Deux effectifs qui surprennent à la lecture, et qui sont tous deux **le
résultat d'une correction** :

**118 pièges au lieu de 10 × 12 = 120.** Le piège « sévérité sous-estimée »
porte une condition `applies_when` : minimiser une situation **déjà anodine**
n'est pas une faute grave, et évaluer le contrôleur là-dessus fausserait la
mesure. Il ne s'est appliqué qu'à **10 instants sur 12** — la table du § 15.11
le montre, seule ligne à `n = 10`.

**58 mutations non ciblées au lieu de 5 × 12 = 60.** Deux mutations sont
restées **sans effet** sur la décision : `wrong_checklist` ne peut pas inverser
une check-list quand la décision n'en cite aucune. Elles sont **écartées du
dénominateur** — compter un essai où rien n'a été tenté comme une non-détection
fausserait le taux de généralisation. C'est une correction apportée par l'audit
(lot S6), et **l'écart de 60 à 58 en est la trace mesurable**.

---

# 16. Ce que le rapport doit recommander

Ces recommandations ne sont pas des opinions : chacune découle d'un chiffre
mesuré au § 15, et chacune est cité avec lui.

## 16.1 Un gain d'exploitation immédiat, sans investissement

**Fait** : la ligne passe **29,89 % de son temps de marche — 2 640 heures — à
1,7 °C sous la consigne**, et quatre mois sur quatorze sont hors bande plus de
80 % du temps, toujours du côté froid (octobre 2024 : **99,1 %**).

**Ce n'est pas une dégradation, c'est un réglage.** La vanne d'eau de mer
travaille plus qu'il n'est nécessaire, et cette sur-ouverture **consomme par
avance la marge disponible pour compenser un futur encrassement** — c'est-à-dire
la marge dont dépend précisément la détectabilité (§ 3.5).

**Recommandation** : faire examiner par le service procédé le réglage de la
boucle sur les périodes mai, août, septembre, octobre et novembre 2024. C'est
la seule action de ce mémoire qui ne coûte rien et produit un effet mesurable.

## 16.2 La mesure qui débloquerait tout : le débit d'eau de mer

**Fait** : UA n'est qu'un **UA apparent** parce que le débit d'eau de mer n'est
pas instrumenté (§ 3.5). Conséquence mesurée au banc : à **5 % de perte de UA,
la détection arrive à 100 % d'avancement** (§ 15.10) — donc trop tard — et le
résultat publié est encore **optimiste**, puisque le banc n'y simule pas la
compensation par la vanne.

**Recommandation** : instrumenter le débit d'eau de mer. C'est le seul ajout qui
transformerait un UA apparent en UA réel, et qui ferait passer la détection d'un
encrassement lent de « aveugle » à « mesurable ». **Coût d'un débitmètre contre
le coût d'un remplacement de faisceau (tâche H, arrêt process, 8 ans).**

## 16.3 Deux analyseurs saturés portent le mode le plus grave

**Fait non anticipé, sorti de la mesure** (§ 15.1) : `C_ACID_1100` et
`C_ACID_1200` sont saturés **536 h et 515 h** respectivement, soit **~6 % du
corpus**. Ce sont **les deux capteurs les moins disponibles du périmètre
surveillé** (94,0 % et 93,9 %).

Or ce sont eux qui portent `FAISCEAU_FUITE` — *« le signal le plus critique du
système »*, une entrée d'eau de mer dans l'acide par percement de tube.

**Recommandation** : faire vérifier la chaîne de mesure des deux analyseurs de
titre par le service instrumentation. Six pour cent d'indisponibilité sur le
capteur du mode le plus grave est un angle mort qui n'était pas identifié.

## 16.4 Deux portes ne s'ouvriront jamais sans OCP

**Fait** : `labels_gmao` et `validation_externe` sont en **échec définitif**
(§ 15.8) — aucune date de panne, aucune annotation indépendante dans le corpus.
La promotion de l'artefact est donc **légitimement impossible**, et le modèle
tourne en `runtime_trained_unpromoted`.

**Recommandation** : extraire de la GMAO l'historique d'interventions sur E7301
depuis 2015. C'est la seule donnée qui permettrait de passer d'un contrôle de
cohérence interne à une validation, et de mesurer une performance de détection
au lieu de la borner.

## 16.5 Une date de révision remplacerait un choix arbitraire

**Fait** : la période de référence vaut « les 40 % initiaux des heures de
marche » **faute de date de révision communiquée**. La mesure montre que ce
choix décide de tout : une fenêtre plus courte de deux mois déclare **52,14 %**
du corpus en encrassement au lieu de **0 %** (§ 15.9).

**Recommandation** : obtenir d'OCP la date du dernier nettoyage ou de la
dernière révision du faisceau. Elle remplacerait une convention par un état de
référence physique, et retirerait au projet sa plus grande fragilité.

## 16.6 Ce que le système ne remplacera pas

**Fait** : **51,2 % de la criticité AMDEC** reste non couverte, dont les deux
modes les plus graves — plaque sacrificielle et fuite de vanne d'acide,
**112 chacun** (§ 15.7 et § 7.3).

**Recommandation, et elle doit clore le mémoire** : le plan préventif A–H reste
la première ligne de défense. La surveillance par données **ne s'y substitue
pas** ; elle en éclaire l'arbitrage, en particulier la date de la prochaine
mesure d'épaisseurs par courant de Foucault (tâche B, cadence 2 ans, arrêt
process).
