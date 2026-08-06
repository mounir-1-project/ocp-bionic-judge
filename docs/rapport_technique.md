---
title: "Surveillance comportementale et aide au diagnostic du refroidisseur d'acide de séchage E7301"
subtitle: "Atelier Sulfurique PS III — Maroc Chimie, OCP Group"
author: "Mounir Sanbouli — Élève ingénieur, stage OCP (Programme Bionic)"
date: "Juillet 2026"
lang: fr
---

# Résumé

Ce rapport présente la conception et la validation d'un système de surveillance
sur données historiques rejouées du refroidisseur d'acide de séchage **E7301**
(S-PC-E7301, atelier sulfurique PS III, Maroc Chimie). Le système exploite
**10 180 heures de données DCS réelles** couvrant la période du 1^er^ janvier
2024 au 28 février 2025, et les rattache à l'**AMDEC de l'équipement établie
par OCP le 23 septembre 2019**.

L'originalité du dispositif tient à son architecture à trois niveaux : une
détection hybride combinant règles ancrées sur l'AMDEC et modèle statistique,
un agent de diagnostic, et un **Judge Agent** — vérificateur déterministe qui
recalcule la cohérence des faits depuis la même chaîne de données. Il est
indépendant du texte produit par l'agent, pas de la donnée ni du détecteur.

Résultats mesurés :

- **58 épisodes comportementaux candidats** identifiés sur 14 mois par l'artefact livré ; ils restent des hypothèses à qualifier, pas des pannes confirmées ;
- **coefficient d'échange global UA** comme indicateur d'encrassement, calculé par la méthode efficacité-NTU à partir de la climatologie d'eau de mer de Safi. Référence ajustée sur les 40 % premières heures de marche : R² = 0,924, écart-type résiduel 0,63 kW/K soit 3,5 % de UA. C'est un **UA apparent** — le débit d'eau de mer n'étant pas instrumenté, il mesure l'état de la surface multiplié par l'action de la boucle froide ;
- **deux défaillances d'instrumentation majeures** caractérisées, jusqu'alors non tracées : un capteur saturé en butée d'échelle pendant sept mois, et un capteur figé pendant environ 1 900 heures ;
- **aucun encrassement du faisceau** sur la période — la signature dominante est un **sur-refroidissement** installé pendant 28 % du temps de marche, avec une régulation hors bande jusqu'à 99 % du temps en octobre 2024 ;
- **Judge éprouvé sur 118 cas piégés** : **100 % des fautes injectées détectées**, 95,8 % détectées ET suffisamment sanctionnées, 0 % de faux positifs, écart de 4,13 points entre décisions saines et décisions fautives. Le mot **« validé » a été retiré de cette ligne** : chaque piège du catalogue porte exactement le code d'anomalie que le Judge sait produire, si bien que ce taux mesure une **non-régression** des contrôles implémentés, jamais leur capacité face à une faute imprévue. `src/governance/judge_eval.py` le dit dans son en-tête — le présenter comme une validation serait une sur-vente. La mesure de généralisation est distincte, plus basse, et porte sur des mutations non ciblées ;
- **aucun chiffrage économique** : la couche qui en produisait a été retirée du périmètre, et deux tests interdisent son retour (§ 10.5). Les indicateurs publiés portent chacun leur niveau de preuve et ne se convertissent pas en dirhams.

Le cœur de détection fonctionne intégralement hors ligne et sans service externe obligatoire. L'authentification locale est désactivée par défaut et ne devient utilisable qu'avec une empreinte PBKDF2 et une liste d'e-mails autorisés explicitement configurées ; elle n'est pas une authentification industrielle de production. Le relais SMTP reste une intégration externe de déploiement. La campagne finale couvre **277 cas de test** côté Python et **98 vérifications** des bancs du poste, avec **87,15 %** de couverture de lignes.

Deux erreurs d'analyse commises en cours de projet ont été détectées et corrigées : une causalité apparente entre une panne de capteur et un changement de régime, invalidée par une analyse à granularité plus fine ; et une hypothèse de redondance entre deux analyseurs de titre, invalidée par leur corrélation réelle. Elles sont documentées dans le corps du rapport, parce qu'un projet dont on ne peut pas retracer les corrections n'est pas vérifiable.

\newpage

# 1. Contexte et problématique

## 1.1 L'équipement

Le refroidisseur E7301 est un échangeur à faisceau tubulaire de marque **CHEMETICS** (size 1118-9754), fabriqué le 8 avril 2014 et mis en production le 1^er^ novembre 2015. Il assure le refroidissement de l'acide sulfurique du circuit de séchage de la ligne PS III.

| Caractéristique | Valeur |
|---|---|
| Repère fonctionnel | S-PC-E7301 |
| Fluide côté calandre | Acide sulfurique de séchage |
| Fluide côté tubes | Eau de mer |
| Matériau des tubes | Alliage 904L |
| Protection | Anodique, par plaques sacrificielles |
| Constructeur | CHEMETICS |

L'association acide sulfurique concentré / eau de mer, séparés par une paroi de quelques millimètres d'alliage, définit à elle seule la criticité de l'équipement : un percement de tube met en contact deux fluides dont le mélange est violemment exothermique et corrosif, et impose l'arrêt de la ligne.

## 1.2 Ce que dit l'AMDEC de l'équipement

L'analyse AMDEC réalisée par OCP le 23 septembre 2019 recense neuf modes de défaillance. Les criticités les plus élevées (C = F × G × N) sont :

| Élément | Mode | F | G | N | C | Détectable en ligne |
|---|---|---|---|---|---|---|
| Plaque sacrificielle | Dysfonctionnement | 2 | 8 | 7 | **112** | Non |
| Vanne d'acide | Fuite | 2 | 8 | 7 | **112** | Non |
| Faisceau tubulaire | Fuite | 3 | 7 | 5 | **105** | Oui |
| Faisceau tubulaire | Bouchage / encrassement | 3 | 7 | 5 | **105** | Oui |
| Faisceau tubulaire | Corrosion | 3 | 7 | 5 | **105** | Partiellement |
| Porte de visite | Fuite | 3 | 6 | 5 | 90 | Non |
| Calandre | Fuite | 3 | 6 | 5 | 90 | Partiellement |

Un constat structure tout le projet : **la colonne « Détection » de l'AMDEC de 2019 indique « Visuel » pour la quasi-totalité des modes**. La surveillance repose donc sur l'inspection humaine périodique — inspection externe mensuelle (tâche C), contrôle d'anode semestriel (tâche D), mesure d'épaisseurs des tubes par courant de Foucault tous les deux ans (tâche B).

C'est précisément la cotation de non-détection (N = 5 à 7) qui gonfle la criticité. **Réduire N est le levier le plus direct pour abaisser la criticité sans modifier l'équipement**, et c'est l'objet de ce travail.

## 1.3 Objectif du stage

Concevoir un système capable de :

1. surveiller en continu l'état du refroidisseur à partir des signaux DCS existants, sans instrumentation supplémentaire ;
2. rattacher chaque anomalie détectée à un mode de défaillance de l'AMDEC et à une tâche du plan de maintenance préventive ;
3. produire une recommandation d'intervention exécutable par les équipes de PS III ;
4. **garantir la fiabilité de ses propres conclusions** par un mécanisme d'audit automatique.

Le quatrième point est le cœur du programme Bionic : un système de diagnostic automatique qui ne sait pas dire quand il se trompe est inexploitable en environnement industriel.

\newpage

# 2. Les données

## 2.1 Périmètre

Le fichier `DATA.xlsx` est un export du système de conduite (DCS) de la ligne PS III.

| Caractéristique | Valeur |
|---|---|
| Période | 01/01/2024 07:00 → 28/02/2025 11:00 |
| Nombre d'enregistrements | 10 182 (10 180 après dédoublonnage) |
| Pas d'échantillonnage | 1 heure |
| Nombre de tags | 12 |
| Horodatages dupliqués | 2 |
| Trous temporels | 1 |

## 2.2 Interprétation des tags

Les tags sont nommés selon la convention `S_MC_SULF_<boucle>_B`. Aucun dictionnaire de tags n'accompagnait l'export. L'interprétation a donc été reconstruite à partir de trois sources convergentes : la nomenclature ISA-5.1 (TI = température, FI = débit, AI = analyseur), la plage de valeurs observée, et le comportement des signaux lors des arrêts de ligne.

| Alias | Tag DCS | Interprétation retenue | Médiane | Rôle |
|---|---|---|---|---|
| `T_ACID_IN` | S_MC_SULF_TI1100_B | Température acide entrée refroidisseur | 94,1 °C | Surveillé |
| `T_ACID_OUT` | S_MC_SULF_TI1105_B | Température acide sortie (régulée) | 65,8 °C | Surveillé |
| `F_ACID` | S_MC_SULF_FI1300_B | Débit acide de séchage | 56,5 m³/h | Surveillé |
| `C_ACID_1100` | S_MC_SULF_AI1100_B | Titre acide circuit 1100 | 98,71 % | Surveillé |
| `C_ACID_1200` | S_MC_SULF_AI1200_B | Titre acide circuit 1200 | 98,57 % | Surveillé |
| `T_CIRC_1300` | S_MC_SULF_TI1300_B | Température circuit aval | 43,0 °C | Secondaire |
| `LOAD_SULFUR` | S_MC_SULF_023_B | Charge soufre / allure de marche | 18,6 t/h | Contexte |
| `F_3412` | S_MC_SULF_FI3412_B | Débit circuit absorption | 2 028 m³/h | Contexte |
| `A_3301`, `A_3302` | S_MC_SULF_AI33xx_B | Analyseurs section absorption | — | Contexte |
| `PHI_5306` | S_MC_SULF_PHI5306X-3_B | Non identifié | — | **Hors périmètre** |
| `TI_5303` | S_MC_SULF_TI5303-4X_B | Non identifié | — | **Hors périmètre** |

**Point de méthode important.** Ces interprétations sont *établies par recoupement*, non *confirmées par OCP*. Chaque tag porte dans le référentiel un champ `basis` citant **au moins deux bases indépendantes** — nomenclature ISA-5.1, physique du procédé, comportement des données, cohérence stœchiométrique, climatologie — et un champ `evidence` qui publie la preuve correspondante. Un test échoue si un tag repose sur une base unique. Ce référentiel est un fichier YAML éditable : **une correction apportée par le tuteur OCP se répercute dans tout le système sans modification de code**. Le système fonctionne indépendamment de cette validation — les seuils sont dérivés statistiquement — mais la traçabilité métier l'exige.

Deux éléments corroborent l'interprétation de `LOAD_SULFUR` comme charge soufre : le préfixe `SULF`, et la cohérence stœchiométrique — 1 t de soufre donne 3,06 t de H₂SO₄, soit environ 1 370 t/j à 18,6 t/h, ce qui correspond à la capacité d'une ligne PS III.

### Un piège d'analyse à signaler : les corrélations d'arrêt

Les corrélations calculées sur l'ensemble du jeu de données sont **trompeuses**, et l'ont été dans une première version de ce travail. Pendant les arrêts, tous les signaux s'effondrent simultanément, ce qui crée des corrélations artificiellement élevées entre grandeurs sans lien physique direct :

| Paire | Sur tout le jeu | En marche établie | Lecture |
|---|---|---|---|
| TI1100 ~ TI1105 | **+0,976** | **−0,083** | artefact d'arrêt |
| 023 ~ TI1100 | +0,970 | +0,574 | artefact d'arrêt |
| 023 ~ FI1300 | +0,938 | +0,540 | artefact d'arrêt |
| AI1100 ~ AI1200 | +0,656 | +0,347 | artefact d'arrêt |
| 023 ~ duty | +0,641 | +0,641 | stable |

Le cas de TI1100 ~ TI1105 est le plus instructif : une corrélation de 0,976 suggérerait que la sortie acide suit mécaniquement son entrée. En marche établie, elle est **nulle**. C'est précisément la preuve que la sortie est régulée — le régulateur absorbe intégralement les variations amont. La corrélation apparente ne mesurait que la synchronisation des arrêts.

Toutes les corrélations citées dans ce rapport sont donc calculées **sur la marche établie uniquement**.

## 2.3 Analyse critique de la qualité des données

L'analyse a révélé des défauts d'instrumentation **non tracés à ce jour**, qui constituent en eux-mêmes un résultat du stage.

### Capteur TI5303-4X — saturation en butée d'échelle

Le signal reste **collé à la valeur 327,67 depuis le mois d'août 2024**, sans jamais en redescendre, soit sept mois de données mortes. La valeur 327,67 correspond exactement à 32767 / 100, c'est-à-dire à la valeur maximale d'un entier signé sur 16 bits : il s'agit d'un dépassement de capacité de la chaîne d'acquisition, et non d'une grandeur physique.

### Capteur PHI5306X-3 — signal figé

Le signal est resté **constant à la valeur −14,407 du 1^er^ janvier au 20 mars 2024**, soit environ 1 900 heures, avant de reprendre des valeurs plausibles. Il porte par ailleurs 139 codes qualité DCS.

### Codes qualité DCS

L'export contient des valeurs textuelles mêlées aux valeurs numériques : `Bad`, `Configure`, `I/O Timeout`. Une lecture naïve du fichier — `pd.read_excel` suivi d'une conversion numérique — les transforme silencieusement en valeurs manquantes, puis un `fillna` les remplace par la dernière valeur connue. **Le système déclarerait alors « tout va bien » pendant sept mois de capteur mort.**

### Saturation des analyseurs de titre

Les deux analyseurs de titre acide atteignent leur butée haute d'échelle (99,995 % et 99,996 %) pendant respectivement 536 et 515 heures.

### Synthèse

| Capteur | Disponibilité | Heures figées | Heures saturées |
|---|---|---|---|
| `TI_5303` | 47,8 % | 4 | 5 170 |
| `PHI_5306` | 85,4 % | 1 351 | 0 |
| `C_ACID_1200` | 93,8 % | 118 | 515 |
| `C_ACID_1100` | 93,9 % | 85 | 536 |
| `T_ACID_OUT` | 98,3 % | 171 | 0 |
| `F_ACID` | 99,0 % | 86 | 0 |
| `T_ACID_IN` | 99,2 % | 85 | 0 |
| `T_CIRC_1300` | 99,2 % | 85 | 0 |

Un phénomène remarquable apparaît : **85 à 86 heures de gel simultané sur sept tags différents, du 3 au 10 juin 2024**. La simultanéité exclut une panne de capteur individuelle et désigne une interruption de l'historisation ou de l'acquisition au niveau du système. Ce type d'événement doit être qualifié comme défaillance système, et non comme anomalie procédé.

## 2.4 États de marche

La distinction entre marche et arrêt est la décision de conception la plus déterminante du projet.

| État | Heures | Part |
|---|---|---|
| `RUNNING` — marche établie | 8 795 | 86,4 % |
| `STOPPED` — ligne à l'arrêt | 1 261 | 12,4 % |
| `TRANSIENT` — transitoire | 124 | 1,2 % |

Sans cette classification, l'arrêt de février 2024 (charge soufre descendue à 3,9 t/h en moyenne mensuelle) serait interprété comme un effondrement des performances du refroidisseur. Le système émettrait des centaines d'alertes critiques sur un arrêt planifié, et serait désactivé en salle de contrôle dans la semaine.

**Toutes les grandeurs de performance sont donc définies comme indisponibles hors marche établie.** Ce n'est pas une commodité de calcul : juger le rendement d'un échangeur à l'arrêt n'a aucun sens physique.

\newpage

# 3. Analyse critique de la version précédente

Un premier prototype avait été développé avant ce travail. Son architecture d'ensemble — détection, agent de diagnostic, Judge — était pertinente. Sa mise en œuvre présentait cependant des limites qu'il est utile d'expliciter, car elles éclairent les choix de la version présentée ici.

## 3.1 Absence d'ancrage sur l'équipement réel

Le prototype opérait sur **cinq machines fictives** (`BROYEUR_01`, `POMPE_02`, `CONVOYEUR_03`, `REACTEUR_04`, `COMPRESSEUR_05`) décrites par cinq grandeurs génériques : température, vibration, pression, courant, vitesse de rotation. Ces données étaient produites par un générateur synthétique.

Or aucune de ces grandeurs n'existe dans `DATA.xlsx`. Le refroidisseur E7301 n'a ni vibration, ni courant, ni vitesse de rotation : c'est un équipement statique. Les seuils codés dans le prompt du Judge — « BROYEUR_01 : température 50–70 °C, critique > 80 » — ne correspondaient à aucun point de mesure réel.

Le système fonctionnait donc parfaitement sur un domaine qui n'existe pas.

## 3.2 Les trois failles structurelles du Judge

Le Judge de la version précédente recevait la décision de l'agent et demandait à un LLM de la noter sur cinq critères pondérés. Trois limites en découlaient, indépendantes de la qualité du prompt.

**Première limite — aucune source de vérité indépendante.** Le Judge ne voyait que ce que l'agent lui rapportait. Si l'agent écrivait « température 85 °C » alors que le capteur indiquait 66 °C, le Judge n'avait aucun moyen de le savoir. Il évaluait la **cohérence interne d'un texte**, non sa **véracité**. Un diagnostic entièrement inventé mais bien rédigé obtenait une meilleure note qu'un diagnostic exact mais mal formulé.

**Deuxième limite — complaisance structurelle.** Un modèle de langage à qui l'on demande de noter une production plausible note haut. Sans ancrage factuel, le Judge validait pratiquement tout : il produisait un tampon de conformité, non un contrôle.

**Troisième limite — non-reproductibilité.** La note variait d'un appel à l'autre, et le dispositif dépendait d'un quota API. Un mécanisme de gouvernance dont le verdict n'est pas reproductible ne peut être opposé à personne, et une soutenance dépendant d'une connexion réseau est un risque inutile.

## 3.3 Ce qui a été conservé

L'idée directrice du Judge — un second contrôle logique des conclusions d'un système automatique — est utile, sans constituer une validation industrielle indépendante. L'ossature technique du prototype (API FastAPI, structuration en modules, suite de tests, conteneurisation) a également été conservée. C'est le **domaine métier et le mécanisme de jugement** qui ont été refondus.

La version 1 n'est pas conservée dans le dépôt : ce sont les décisions d'architecture (`docs/decisions/`) qui documentent l'évolution, en disant pourquoi chaque choix a été abandonné plutôt qu'en gardant le code qui le portait.

\newpage

# 4. Architecture du système

```
        DATA.xlsx (10 180 h, 12 tags DCS)
                    |
    [1] INGESTION — codes qualité, gel, saturation, états de marche
                    |
    [2] FEATURES — physique de l'échangeur + référence thermique semi-empirique
                    |
    [3] DÉTECTION — règles AMDEC  ⊕  Isolation Forest
                    |
    [4] AGENT — diagnostic + action rattachée au plan préventif
                    |
    [5] CONTRÔLEUR HYBRIDE — recalcul interne, 8 contrôles de cohérence
                    |
        API FastAPI + dashboard + rejeu accéléré
```

Le référentiel métier (`tags.yaml`, `amdec.yaml`) alimente **toutes** les couches. Aucun seuil, aucun nom de tag, aucune criticité n'est codé en dur ailleurs.

## 4.1 Couche domaine

Deux fichiers YAML constituent la source de vérité métier :

- `tags.yaml` — les 12 points de mesure, leurs plages opératoires, leurs seuils d'alarme, leur consigne de régulation, leur niveau de confiance d'interprétation et sa justification ;
- `amdec.yaml` — la transcription fidèle de l'AMDEC de 2019, les barèmes de gravité / fréquence / non-détection, le plan de maintenance préventive (tâches A à H), les gammes d'intervention et les check-lists d'inspection.

Chaque mode de défaillance est enrichi d'une **signature** : la manière dont il se manifeste dans les signaux DCS, et surtout un indicateur `observable` déclarant s'il est détectable ou non avec l'instrumentation disponible.

## 4.2 Ingestion

Principe directeur : **la qualité de donnée est une information, pas un déchet à nettoyer**.

Un capteur figé ou un code `I/O Timeout` n'est pas du bruit : c'est le mode de défaillance `CAPTEUR_DEFAILLANT`, ajouté à l'AMDEC dans le cadre de ce travail avec une criticité proposée de 108 (F = 6, G = 6, N = 3). Ce mode était absent de l'AMDEC mécanique de 2019, laquelle ne couvrait pas la chaîne d'instrumentation.

Les valeurs invalides sont **mises à NaN et jamais remplacées**. Une donnée absente doit rester absente : la combler par interpolation reviendrait à faire apprendre au modèle une mesure qui n'a jamais existé.

**Une subtilité de conception mérite d'être signalée.** La détection de gel de signal ne peut pas s'appliquer aveuglément : pendant un arrêt de ligne, un débit reste légitimement à zéro pendant des jours. Une détection naïve produisait initialement 17 786 événements qualité, dont l'écrasante majorité étaient de faux positifs liés aux arrêts. En restreignant la recherche de gel aux périodes de marche, ce nombre tombe à **9 116 événements réels**, et la disponibilité des capteurs du périmètre remonte de 88–96 % à 93–99 %.

\newpage

# 5. Modélisation physique

## 5.1 Le problème central : la variable de sortie est régulée

La distribution de la température de sortie acide sur 14 mois est la suivante :

| Percentile | Valeur |
|---|---|
| P1 | 63,7 °C |
| P50 | 65,9 °C |
| P99 | 66,6 °C |

Soit une amplitude de **moins de 3 °C sur 14 mois**. Cette signature est celle d'une variable maintenue par une boucle de régulation autour d'une consigne de 66 °C.

La conséquence est fondamentale et invalide l'approche statistique classique : **l'encrassement du faisceau ne se lit pas sur la température de sortie**. Tant que la régulation tient, elle compense la dégradation en ouvrant davantage la vanne d'eau de mer. Un z-score sur ce signal ne détecte rien — et quand il détecte enfin quelque chose, la régulation a déjà décroché, c'est-à-dire qu'il est trop tard.

L'encrassement ne se lit donc pas sur le **résultat**. Une première approche en
concluait qu'il fallait lire l'**effort** — le résidu de puissance évacuée. Le
§ 5.3 montre pourquoi cette conclusion était fausse, et sur quoi le diagnostic
repose réellement.

## 5.2 Grandeurs physiques dérivées

| Grandeur | Définition | Signification |
|---|---|---|
| `delta_t` | T_entrée − T_sortie | Travail brut de l'échangeur |
| `duty_kw` | ρ·c_p·V·ΔT | Puissance thermique évacuée |
| `duty_per_load` | duty / charge soufre | Duty neutralisé de l'effet d'allure |
| `control_deviation` | T_sortie − 66 °C | Écart à la consigne de régulation |
| `conc_min` | min(AI1100, AI1200) | Titre gouvernant la corrosion |
| `conc_bias_drift_z` | (écart − biais normal) / σ | Dérive d'un analyseur |

La normalisation par la charge soufre est indispensable : sans elle, une simple montée en cadence de la ligne est indiscernable d'une dérive de l'équipement.

### Les deux analyseurs de titre ne sont pas redondants

Une première version du système traitait AI1100 et AI1200 comme deux mesures du même titre, et surveillait leur écart avec une tolérance absolue de 0,6 point. L'analyse en marche établie invalide cette hypothèse :

| Grandeur | Valeur |
|---|---|
| Corrélation AI1100 ~ AI1200 | +0,347 |
| Écart moyen (AI1200 − AI1100) | −0,124 point |
| Écart-type de cet écart | 0,079 point |
| AI1200 inférieur à AI1100 | 94,9 % du temps |

Une corrélation faible assortie d'un biais constant désigne **deux circuits distincts**, pas une redondance. Deux conséquences ont été corrigées :

1. Le `min()` des deux analyseurs se réduisait en pratique à AI1200 seul dans 95 % des cas, tout en donnant l'illusion d'une sécurité par redondance.
2. Le seuil de 0,6 point représentait **6 σ** de l'écart normal : il ne se déclenchait que 19 heures sur 14 mois, autant dire jamais.

La règle a été remplacée par une surveillance de la **stabilité du biais** : une alerte est levée lorsque l'écart s'éloigne de plus de 4 σ de sa valeur habituelle. Ce test détecte une dérive d'analyseur bien avant qu'un seuil absolu ne bouge.

## 5.3 Pourquoi le résidu de puissance ne pouvait pas marcher

Modéliser la puissance évacuée attendue puis suivre le résidu paraissait
naturel. **Cette approche est fausse, et l'erreur est algébrique.**

La puissance est calculée par définition :

$$
Q = \rho c_p \dot{V} (T_{\text{entrée}} - T_{\text{sortie}})
$$

Le modèle de référence la régresse sur $\dot{V}$, $T_{\text{entrée}}$ et leur
produit. Comme $T_{\text{sortie}}$ est régulée autour de 66 °C, la cible s'écrit
déjà comme une combinaison linéaire de deux régresseurs présents. **La
régression ne modélise pas l'échangeur : elle retrouve sa propre définition.**

| Grandeur | Valeur |
|---|---|
| R² de la référence apprise | 0,968 |
| R² d'une reconstruction **sans aucun apprentissage** | 0,962 |
| **Apport réel du modèle** | **+0,006** |
| Corrélation résidu ↔ écart de consigne | **−0,94** |
| Variance partagée | 88 % |

Le résidu de puissance **est** l'écart de consigne, changé de signe et pondéré
par le débit. Il est conservé sous le nom `regulation_effort` — qui dit ce qu'il
mesure — et il ne fonde jamais un diagnostic d'encrassement. Un test échoue si
quelqu'un tente de le présenter comme indépendant.

## 5.3 bis Ce qui débloque tout : la température d'eau de mer

L'encrassement d'un échangeur se lit sur son **coefficient d'échange global
UA**, et sur rien d'autre. Le calculer exige la température du fluide froid,
absente de l'export DCS. C'est ce qui bloquait le raisonnement.

Cette température n'est pourtant pas une inconnue. Le refroidisseur est refroidi
à l'eau de mer, à **Safi**, où le courant des Canaries et l'upwelling côtier
maintiennent une eau fraîche à faible amplitude : **17,0 °C en février-mars,
22,0 °C en septembre**, moyenne annuelle 19,3 °C. C'est une donnée
climatologique documentée, stable d'une année sur l'autre, et surtout
**extérieure à l'atelier** — aucune boucle de régulation ne la contraint.

$$
\varepsilon = \frac{T_{\text{entrée}} - T_{\text{sortie}}}{T_{\text{entrée}} - T_{\text{eau de mer}}}
\qquad
\text{NTU} = -\ln(1 - \varepsilon)
\qquad
UA = C_{\text{acide}} \cdot \text{NTU}
$$

UA varie légitimement avec le régime — le débit gouverne la turbulence, la
viscosité de l'acide chute avec la température. Une référence linéaire apprend
$UA(\dot{V}^{0,8}, T_{\text{moy}}, T_{\text{eau}})$ sur la période de
référence uniquement.

| Paramètre | Valeur |
|---|---|
| Période de référence | 01/01/2024 → 13/07/2024 |
| Heures d'apprentissage | 3 505 |
| **R²** | **0,924** |
| Écart-type du résidu | 0,63 kW/K, soit 3,5 % de UA |

La résistance d'encrassement $R_f = 1/UA - 1/UA_{\text{attendu}}$, en K/kW, est
la grandeur que suit le service fiabilité pour arbitrer la date du prochain
nettoyage.

### Ce que UA est, et ce qu'il n'est pas

Le débit d'eau de mer n'est pas instrumenté, et c'est lui que la régulation
manipule pour tenir 66 °C. La grandeur calculée est donc un **UA apparent** : le
produit de l'état de la surface d'échange par l'action de la boucle froide.

La conséquence doit être dite franchement — **tant que la vanne conserve de la
marge, elle compense un début d'encrassement et UA apparent ne bouge pas.**
L'indicateur devient sensible quand cette marge se consomme. C'est précisément
pour chiffrer ce retard que le banc d'injection publie l'**avancement à la
détection** plutôt qu'un taux.

Indépendance mesurée vis-à-vis de l'écart de consigne, en marche établie :

| Indicateur | r | Variance partagée | Rôle |
|---|---|---|---|
| `regulation_effort_z` | −0,94 | 88 % | conduite — jamais une preuve d'encrassement |
| `ua_residual_z` | −0,54 | 29 % | **diagnostic** — partiellement confondu, le banc chiffre le retard |
| `t_in_residual_z` | +0,03 | 0,1 % | contexte amont — indépendant, mais confondu côté procédé |

Aucun de ces indicateurs n'est parfait, et le projet ne prétend pas le
contraire. UA porte le diagnostic parce qu'il est le seul construit sur la
grandeur que l'encrassement dégrade.

**Validation croisée.** À charge constante, la température d'entrée acide monte
de 89,4 °C en janvier à 96,8 °C en juillet. Une lecture naïve y voit une
dégradation. C'est la climatologie de l'eau de mer — **le système a signalé une
dérive, et c'était l'océan Atlantique.**

## 5.4 Le signe du résidu — un point critique

C'est le point technique le plus délicat du système, et une source d'erreur coûteuse.

| Configuration | Interprétation |
|---|---|
| Déficit de **UA** persistant, au-delà de 3 σ | La surface d'échange transmet moins bien à conditions comparables → **encrassement** (`FAISCEAU_BOUCHAGE`) |
| Excès d'**effort de régulation** et sortie sous consigne | La boucle froide travaille au-delà du nécessaire → **régime de conduite, pas une dégradation** |

Confondre les deux conduirait à programmer un nettoyage haute pression du faisceau — donc un arrêt de ligne de plusieurs jours et une intervention en tenue anti-acide complète — alors que l'échangeur fonctionne mieux que sa référence.

Le système traite explicitement les deux cas, et un test automatisé dédié (`test_sur_refroidissement_est_un_regime_de_conduite`) verrouille ce comportement.

Une exigence de **persistance de 72 heures** est par ailleurs imposée avant de déclarer une dérive : l'encrassement s'installe sur des semaines, un à-coup d'exploitation ne dure que quelques heures.

\newpage

# 6. Détection hybride

## 6.1 Étage 1 — moteur de règles ancré sur l'AMDEC

Chaque règle encode la signature d'un mode de défaillance de l'AMDEC. Elle est déterministe, traçable, et ne peut pas produire d'affirmation non fondée. C'est ce qui donne au système sa crédibilité devant un exploitant : **toute alerte se rattache à une ligne de l'AMDEC de 2019**.

| Constatation | Sévérité | Mode AMDEC |
|---|---|---|
| `CONTROL_LOSS_CRITICAL` — sortie acide ≥ 72 °C | CRITICAL | `FAISCEAU_BOUCHAGE` |
| `CONTROL_LOSS` — sortie acide ≥ 68 °C | WARNING | `FAISCEAU_BOUCHAGE` |
| `FOULING_DRIFT` — déficit de coefficient d'échange persistant | INFO, WARNING au-delà de 3 σ | `FAISCEAU_BOUCHAGE` |
| `CONC_LOW_LOW` — titre ≤ 97 % | CRITICAL | `FAISCEAU_FUITE` |
| `CONC_DROP_SEVERE` — chute > 0,8 point en 24 h | CRITICAL | `FAISCEAU_FUITE` |
| `CONC_BIAS_DRIFT` — dérive du biais entre analyseurs | WARNING | `CAPTEUR_DEFAILLANT` |
| `T_IN_HIGH_HIGH` — entrée acide ≥ 105 °C | CRITICAL | `FAISCEAU_CORROSION` |
| `FLOW_LOW_LOW` — débit ≤ 20 m³/h en marche | CRITICAL | `CALANDRE_FUITE` |
| `SENSOR_FAULT` — points de mesure en défaut | WARNING | `CAPTEUR_DEFAILLANT` |

## 6.2 Étage 2 — Isolation Forest

Le modèle statistique capte ce qu'aucune règle univariée ne peut voir : les **combinaisons anormales** de variables qui, prises une à une, restent dans les tolérances.

| Paramètre | Valeur |
|---|---|
| Algorithme | Isolation Forest (300 arbres) |
| Features | 11 features contractuelles ordonnées |
| Période d'apprentissage | 02/01/2024 → 14/07/2024 (3 393 observations) |
| Contamination supposée | 2 % |
| Seuil de décision du runtime non promu | 0,9643 |
| Graine aléatoire | 42 (reproductibilité) |

## 6.3 Explicabilité par occlusion exacte

L'attribution des contributions est réalisée par **occlusion exacte** : pour chaque feature, sa valeur est remplacée par la médiane de référence et le score est recalculé. La chute obtenue mesure la contribution réelle de cette variable.

L'interprétation est directe et se formule en une phrase compréhensible par un ingénieur : *« si le duty avait été normal, le score serait tombé de 0,81 à 0,34 »*.

Cette méthode a été retenue plutôt que SHAP pour trois raisons : elle est **exacte** et non approchée ; elle est **déterministe** ; et elle n'introduit aucune dépendance lourde. Le système reste compatible avec SHAP si la bibliothèque est présente.

## 6.4 Des heures atypiques aux épisodes opérables

Le runtime reconstruit localement signale **530 heures atypiques** sur les heures scorables. **Ce chiffre brut est inexploitable en salle de contrôle** : un opérateur ne traite pas 511 points d'alarme. Ce runtime est explicitement `runtime_trained_unpromoted` et ne peut pas être présenté comme un modèle approuvé.

Les heures atypiques sont agrégées en **épisodes** — regroupement des heures consécutives avec tolérance de 6 heures d'interruption, et rejet des épisodes de moins de 3 heures. L'artefact final produit **58 épisodes candidats** sur 14 mois. Ces valeurs sont recalculées avec le modèle livré et ne constituent pas 58 défaillances confirmées.

C'est cette agrégation qui rend le signal plus opérable : 530 points sont ramenés à 58 épisodes candidats, soit un facteur d'environ 9,1. Le pic de chaque épisode reste analysable en détail.

> Tous les nombres de cette section proviennent de `reports/project_metrics.json` et du manifeste du modèle. Un test — `test_le_rapport_technique_cite_les_artefacts` — échoue si l'un d'eux s'en écarte.

Une exigence de persistance s'applique également au modèle : un dépassement isolé est classé `MODEL_ANOMALY_ISOLATED` en sévérité INFO, avec la mention explicite « trop bref pour conclure à une anomalie de procédé — surveiller sans agir ».

\newpage

# 7. Le Judge Agent

## 7.1 Principe

Le Judge **recalcule les faits lui-même** depuis les données brutes, puis confronte chaque affirmation de l'agent à cette vérité reconstituée indépendamment. Il ne demande jamais son avis à un modèle de langage sur un point vérifiable.

L'architecture est à deux étages :

**Étage 1 — vérification déterministe, qui fait autorité.** Huit contrôles indépendants, chacun répondant à une question factuelle tranchable. Production d'une note reproductible et d'un journal d'audit.

**Étage 2 — rédaction et nuance, optionnel et borné.** Le modèle de langage reçoit les faits vérifiés *et* le résultat des contrôles. Il peut ajuster la note dans un corridor de ± 1,5 point et rédiger la synthèse, pour des motifs que la vérification automatique ne sait pas évaluer : qualité du raisonnement causal, pertinence opérationnelle, clarté. **Il ne peut pas contredire un fait établi.**

## 7.2 Les huit contrôles

| Contrôle | Question posée | Poids |
|---|---|---|
| **V1** Fidélité numérique | Les valeurs citées correspondent-elles aux mesures réelles ? | 22 % |
| **V2** Sévérité | La sévérité annoncée correspond-elle aux faits recalculés ? | 16 % |
| **V3** Ancrage AMDEC | Les modes invoqués existent-ils et sont-ils détectables ? | 14 % |
| **V4** Conformité de l'action | L'action est-elle proportionnée, conforme et exécutable ? | 14 % |
| **V5** Calibration | La confiance reflète-t-elle la force réelle des preuves ? | 15 % |
| **V6** État de marche | L'état de marche réel est-il respecté ? | 8 % |
| **V7** Couverture | Le fait le plus grave est-il traité ? | 5 % |
| **V8** Incertitude | Les limites du diagnostic sont-elles énoncées ? | 6 % |

**V1 est le contrôle décisif** : il rend l'hallucination impossible. Chaque valeur déclarée est confrontée à la mesure recalculée, avec une tolérance de 1 %. Les nombres présents dans le texte du diagnostic sont également vérifiés contre l'univers des valeurs légitimes — mesures, preuves des constatations, seuils du référentiel et cotations AMDEC.

**V3 attrape la faute la plus insidieuse** : diagnostiquer un mode que les capteurs disponibles ne permettent pas de voir. Affirmer avoir détecté une dégradation de l'anode sacrificielle — non instrumentée — donnerait à l'exploitant une fausse certitude sur un composant de criticité 112.

## 7.3 Asymétries assumées

Trois asymétries traduisent des réalités d'exploitation :

**Sous-estimer est plus grave que sur-estimer.** Une sévérité sous-estimée laisse la dégradation se poursuivre sans intervention ; une sévérité sur-estimée use la confiance des équipes. La première est pénalisée plus lourdement.

**La sur-confiance est plus grave que la prudence.** La tolérance est de +0,12 point de confiance à la hausse contre −0,30 à la baisse. Une quasi-certitude affichée doit être gagnée, non supposée.

**Certains manquements ne sont pas compensables.** Une moyenne pondérée permettrait à une action dangereuse d'être noyée par sept contrôles réussis. Des **plafonds de sécurité** l'interdisent :

| Manquement | Note plafonnée à |
|---|---|
| Valeur inventée | 4,0 |
| Mode AMDEC inexistant | 4,0 |
| Angle mort revendiqué | 4,0 |
| Action dangereuse | 4,0 |
| Sévérité critique minimisée | 4,0 |
| État de marche erroné | 5,0 |

## 7.4 Auto-surveillance

Le Judge surveille sa propre distribution de notes et signale trois pathologies : la **complaisance** (plus de 97 % de validations), la **sévérité systématique** (moins de 10 %), et l'**indifférenciation** (écart-type inférieur à 0,35 point).

Un juge qui valide tout ne juge pas. Le système est conçu pour le dire.

\newpage

# 8. Validation du Judge

## 8.1 Pourquoi le taux d'accord ne prouve rien

Le Judge et l'agent déterministe raisonnent sur la même base de faits. Un taux d'accord de 100 % est donc **attendu et sans valeur démonstrative**. C'est précisément le piège de la version précédente : une métrique flatteuse qui ne mesurait rien.

## 8.2 Méthode : injection de fautes contrôlées

Des décisions **délibérément fausses** sont soumises au Judge, construites à partir de cas réels du jeu de données en y injectant une faute précise et connue. Pour chaque cas piégé, on sait quelle anomalie le Judge **doit** relever.

Dix types de faute ont été catalogués, correspondant chacun à une erreur plausible d'un système de diagnostic automatique.

## 8.3 Résultats

**Décisions saines — 12 cas**

| Métrique | Valeur |
|---|---|
| Note moyenne | 9,91 / 10 |
| Taux de validation | 100 % |
| **Faux positifs** | **0 %** |

**Cas piégés — 118 cas**

| Métrique | Valeur |
|---|---|
| Note moyenne | 5,78 / 10 |
| **Taux de détection** | **100 %**, sur les dix types de faute |
| **Détection ET sanction suffisante** | **95,8 %** |
| Cas détectés mais insuffisamment sanctionnés | 5 |
| **Séparation saines / fautives** | **4,13 points** |

Les cinq cas concernés se répartissent sur deux types seulement : « action
sous-dimensionnée » (sanction dans 9 cas sur 12) et « sévérité sous-estimée »
(8 sur 10). Le Judge les **repère tous** ; il ne les fait pas toujours payer
assez cher au regard du critère `min_penalty`. Distinguer les deux mesures est
plus honnête qu'un taux unique : ce n'est pas la détection qui faiblit, c'est
la fermeté de la sanction sur deux familles de fautes.

**Détail par type de faute**

| Faute injectée | Anomalie attendue | Détection | Sanction | Note moyenne |
|---|---|---|---|---|
| Valeur inventée | `HALLUCINATED_VALUE` | 100 % | 100 % | 4,00 |
| Mode AMDEC inventé | `INVENTED_AMDEC_MODE` | 100 % | 100 % | 4,00 |
| Angle mort revendiqué | `BLIND_SPOT_CLAIM` | 100 % | 100 % | 4,00 |
| Action dangereuse | `UNSAFE_ACTION` | 100 % | 100 % | 4,00 |
| Sévérité sous-estimée | `SEVERITY_UNDERESTIMATED` | 100 % | 90,9 % | 4,39 |
| Action sous-dimensionnée | `ACTION_UNDERSIZED` | 100 % | 91,7 % | 4,62 |
| État de marche erroné | `STATE_MISMATCH` | 100 % | 100 % | 5,00 |
| Diagnostic sans chiffres | `NO_QUANTITATIVE_EVIDENCE` | 100 % | 100 % | 7,93 |
| Sur-confiance | `OVERCONFIDENCE` | 100 % | 100 % | 8,92 |
| Constatations ignorées | `INCOMPLETE_COVERAGE` | 100 % | 100 % | 9,30 |

## 8.4 Ce que le banc a corrigé dans le Judge

Le banc d'évaluation n'a pas seulement mesuré le Judge : **il l'a corrigé**. La première exécution a révélé un taux de détection global de 65 % et trois défauts précis :

1. **Codes d'anomalie écrasés.** Un contrôle ne pouvait remonter qu'une anomalie ; lorsqu'une action était à la fois sous-dimensionnée et dangereuse, la première disparaissait du journal d'audit. Corrigé par un passage à une liste de codes.

2. **Tolérance de confiance trop laxiste.** Une confiance annoncée à 0,99 sur des preuves justifiant 0,80 passait sous le radar. Tolérance ramenée de 0,25 à 0,12.

3. **État de marche erroné insuffisamment pénalisé.** Détecté à 100 %, mais avec un poids de 8 % la note restait à 9,08 / 10. Un plafond à 5,0 a été introduit : se tromper d'état invalide toute lecture des grandeurs de performance.

Le taux de reconnaissance des catégories de faute est passé de 65 % à 100 %. Sur le banc élargi, **cinq cas sur 118** sont reconnus mais restent insuffisamment sanctionnés — trois « action sous-dimensionnée », deux « sévérité sous-estimée » : le succès complet est donc de **95,8 %**, chiffre publié au § 8.3. Cette itération mesure-corrige-remesure est, méthodologiquement, le résultat le plus significatif de ce travail.

## 8.5 Une correction du Judge sur l'agent

Le Judge a également relevé une omission réelle de l'agent : lorsque le modèle statistique était inapplicable — au moins une grandeur d'entrée manquante — le diagnostic n'en faisait pas mention. Le contrôle V8 signalait `MISSING_CAVEAT`. L'agent a été corrigé pour énoncer explicitement cette réserve.

Le dispositif d'audit a donc produit une amélioration mesurable du système audité. C'est l'objectif même du concept de Judge.

\newpage

# 9. Résultats sur la période

## 9.1 Épisodes les plus marqués

| Début | Durée | Score max | Lecture |
|---|---|---|---|
| 25/10/2024 06:00 | 40 h | 1,000 | Perte de contrôle : sortie acide à 69,7 °C, hors bande de régulation |
| 07/10/2024 21:00 | 390 h | 0,938 | Régime durablement différent de la référence |
| 23/08/2024 14:00 | 305 h | 0,921 | Idem, début de la période atypique |
| 06/11/2024 17:00 | 112 h | 0,940 | Retour progressif vers la référence |
| 29/02/2024 20:00 | 5 h | 1,000 | Point isolé, classé INFO (persistance insuffisante) |

## 9.2 Le régime de sur-refroidissement — correction d'une erreur d'analyse

Une première lecture des moyennes mensuelles avait situé le début du régime atypique en **août 2024**, et signalé sa concomitance avec la saturation du capteur TI5303-4X. **Cette lecture était fausse**, et il est utile d'expliquer pourquoi : les moyennes mensuelles masquaient une première excursion, plus courte, survenue dès le mois de mai.

La reprise de l'analyse par décades donne le tableau réel :

| Période | Résidu du jumeau (σ) | Écart à la consigne | Sortie acide | Régime |
|---|---|---|---|---|
| Janvier – 25 avril 2024 | −0,6 | +0,04 °C | 66,04 °C | nominal |
| **1er – 28 mai 2024** | **+1,6** | **−1,50 °C** | **64,50 °C** | **excursion 1** |
| Juin – 25 juillet 2024 | −0,1 | −0,02 °C | 65,98 °C | nominal |
| **5 août – 10 nov. 2024** | **+2,4** | **−1,63 °C** | **64,37 °C** | **excursion 2** |
| 15 nov. 2024 – févr. 2025 | −0,3 | −0,07 °C | 65,93 °C | nominal |

Il y a donc **deux excursions distinctes**, séparées par deux mois de fonctionnement parfaitement nominal. La première commence **100 jours avant** la saturation permanente de TI5303-4X (8 août 2024).

**Conséquence sur l'hypothèse initiale.** Le lien de causalité entre la panne du capteur et le changement de régime **ne tient pas** : l'effet précède la cause supposée. L'hypothèse est abandonnée. La concomitance de la seconde excursion avec la saturation reste notable et mérite d'être signalée à la conduite, mais elle ne peut plus être présentée comme une explication.

Cet épisode illustre un risque méthodologique concret : une agrégation mensuelle avait suffi à créer une causalité apparente entre deux événements sans rapport établi.

### Nature du phénomène

Dans les deux excursions, l'échangeur évacue **plus** de chaleur que la référence et la sortie acide s'établit **1,6 °C sous la consigne**. Ce n'est pas un encrassement : un faisceau encrassé évacuerait moins et la sortie dériverait vers le haut.

Le tableau de stabilité de la régulation rend le phénomène immédiatement lisible :

| Mois | Part du temps hors bande (écart > 1 °C) |
|---|---|
| Janvier 2024 | 0,3 % |
| **Mai 2024** | **87,0 %** |
| Juin 2024 | 0,0 % |
| **Août 2024** | **82,1 %** |
| **Septembre 2024** | **96,7 %** |
| **Octobre 2024** | **99,1 %** |
| Novembre 2024 | 36,3 % |
| Décembre 2024 | 0,0 % |

En régime nominal la sortie acide est tenue à 66,00 °C au centième près — signature d'un régulateur qui fait exactement son travail. Pendant les excursions, elle décroche pendant des semaines entières sans revenir.

**Il s'agit donc d'une anomalie de conduite ou de régulation, pas d'une dégradation mécanique du refroidisseur.**

### Le système ne détecte aucun encrassement sur la période

Constat qu'il faut énoncer sans détour :

| Signature recherchée | Heures détectées |
|---|---|
| Encrassement — déficit de duty **et** sortie trop chaude | **0** |
| Sur-refroidissement — excès de duty **et** sortie trop froide | **2 406** |

Sur 8 573 heures de marche exploitables, **aucune heure ne présente la signature d'un encrassement du faisceau**. Ce n'est pas un échec de détection : c'est un résultat. Le refroidisseur E7301 n'a pas connu de dégradation d'échange significative entre janvier 2024 et février 2025.

Ce constat ne modifie pas le plan préventif. La tâche B — mesure d'épaisseurs par courant de Foucault tous les deux ans avec arrêt process — reste calendaire. Un éventuel déclenchement sur état exigerait une étude prospective, une confrontation aux événements GMAO et une validation formelle OCP maintenance/procédé/HSE.

### Portée du sur-refroidissement

Une version précédente de ce rapport chiffrait ce régime en **154 MWh thermiques
évacués en excès**. Le chiffre a été retiré, et la raison mérite d'être exposée
plutôt que corrigée en silence.

Une énergie appelle une valorisation, et celle-ci ne tient pas : l'eau de mer
circule de toute façon, la pompe ne module pas, seule la vanne s'ouvre
davantage. Le surcoût réel est marginal, et présenter 154 MWh laissait croire à
un gisement d'économies que ce projet n'a pas les données pour établir. C'était
convertir un constat de conduite en argument économique.

Le fait reste, et il se formule mieux : **la boucle froide travaille au-delà du
nécessaire 28 % du temps de marche**, à 1,5 °C sous consigne en moyenne. Sa
portée n'est pas énergétique mais fonctionnelle — c'est cette marge de vanne qui
permettra d'absorber un futur encrassement sans décrocher la consigne. La
consommer sans raison réduit l'horizon d'alerte du dispositif de surveillance
lui-même.

## 9.3 Contribution à la réduction de criticité

| Mode AMDEC | N avant | N atteignable | C avant | C après |
|---|---|---|---|---|
| `FAISCEAU_BOUCHAGE` | 5 | 3 | 105 | **63** |
| `FAISCEAU_FUITE` | 5 | 3 | 105 | **63** |
| `CAPTEUR_DEFAILLANT` | — | 3 | — | 108 |

Le passage de N = 5 (« nécessite un outillage spécifique, la surveillance ne détecte pas ») à N = 3 (« la surveillance peut détecter la cause potentielle ») est justifié par le fait que la dérive de duty et la chute de titre sont désormais suivies en continu. **Cette réduction reste à valider formellement par le service Méthodes d'OCP.**

\newpage

\newpage

# 10. Analyse business

## 10.1 Où l'argent se déplace réellement

Un système de surveillance ne crée pas de valeur en détectant. Il en crée en **changeant une décision**. Les cinq leviers identifiés, par ordre de valeur décroissante :

| Levier | Mécanisme | Chiffrable aujourd'hui ? |
|---|---|---|
| Éviter un arrêt subi | Convertir une fuite tube détectée tôt en intervention programmée | Oui, sous hypothèses |
| Éviter une intervention inutile | Aucun encrassement en 14 mois — la tâche B (arrêt process) pourrait devenir conditionnelle | Oui, sous hypothèses |
| Récupérer la marge de régulation | 28 % du temps de marche sous consigne, marge de vanne consommée sans nécessité | Oui, en heures de marche |
| Rétablir les mesures mortes | 7 mois de conduite aveugle sur un capteur | Non chiffrable directement |
| Prolonger la vie du faisceau | Suivi de l'exposition corrosive cumulée | Non, horizon trop long |

**Le point le plus important, et le plus souvent survendu dans ce type de projet :** le système **ne réduit pas la fréquence des défaillances**. Il ne répare rien et ne change pas la cinétique de corrosion. Il réduit la **non-détection** — la cotation N de l'AMDEC. Détecter plus tôt permet de convertir un arrêt subi en arrêt programmé. C'est la seule source de gain honnêtement défendable. Le rapport citait ici un test `test_le_gain_ne_vient_pas_dune_baisse_de_frequence` comme verrou de ce principe : **ce test n'existe pas**, et il n'a pas lieu d'exister depuis que le chiffrage lui-même a été retiré (§ 10.5). Le verrou effectif est ailleurs, et il est plus fort : aucun montant n'est calculé nulle part, et deux tests echouent si un endpoint économique ou la chaîne « MAD » réapparaissent.

## 10.2 Parties prenantes

| Acteur | Ce qu'il attend du système | Ce qu'il doit fournir |
|---|---|---|
| Chef d'atelier Mécanique | Anticiper les interventions sur E7301 | Durées réelles d'intervention |
| Service Instrumentation | Savoir quelle boucle de mesure est morte | Suivi des DI capteurs |
| Salle de contrôle | Un nombre d'alertes traitable | Retour sur la pertinence des alertes |
| Service Méthodes / Fiabilité | Réviser les cotations N de l'AMDEC | Validation de la baisse de N |
| Contrôle de gestion | Un chiffrage auditable | Marge contributive de la tonne |
| Production | Ne pas subir de faux arrêts | Explication des excursions de mai et août |

## 10.3 Indicateurs observés et dérivés — non opposables en l'état

Ces indicateurs ne dépendent pas d'une hypothèse de prix, mais les indicateurs
thermiques dépendent du modèle de référence et ne sont pas des mesures directes.

| Indicateur | Valeur | Lecture |
|---|---|---|
| Disponibilité des mesures du périmètre | 97,2 % | 6 capteurs surveillés |
| Charge d'alertes | 5 épisodes/mois | Durée médiane 8 h — traitable |
| Exposition corrosive cumulée | 2 h | 0,02 % du temps de marche |
| Marche durablement sous consigne | 28 % du temps | Réglage de conduite, mesuré sur l'écart de consigne |

À quoi s'ajoute l'indicateur de conduite le plus parlant du projet : **la part du temps hors bande de régulation**, qui passe de 0 % en juin et décembre à 99 % en octobre. Aucun tableau de bord existant ne fait apparaître cet écart.

## 10.4 Réduction de criticité AMDEC

C'est le livrable le plus directement exploitable par le service Méthodes, parce qu'il s'exprime dans le langage de l'AMDEC existante. Le barème DET du document OCP définit N = 3 comme « les équipements de surveillance peuvent détecter la cause potentielle » — ce que la surveillance continue du duty et du titre acide justifie.

| Mode | F | G | N avant | N après | C avant | C après | Gain |
|---|---|---|---|---|---|---|---|
| Faisceau — bouchage | 3 | 7 | 5 | 3 | 105 | **63** | −40 % |
| Faisceau — fuite | 3 | 7 | 5 | 3 | 105 | **63** | −40 % |

**Deux modes ont été retirés de ce tableau.** `FAISCEAU_CORROSION` et
`CALANDRE_FUITE` y figuraient avec le même gain de 40 %. Le référentiel les
déclare `observable: partial` : le système observe les **conditions** qui les
favorisent — titre sous spécification, température excessive, perte de débit —
jamais l'**état** de la pièce. L'amincissement d'un tube ne se mesure que par
courant de Foucault, à l'arrêt.

Les compter comme détectables ajoutait 195 points de criticité à la couverture
revendiquée. `/api/coverage` les publie désormais en catégorie distincte :
**30,2 % de la criticité détectée, 18,5 % en conditions surveillées sans mesure
d'état**, le reste relevant du plan préventif.

**Statut : à faire valider par le service Méthodes** avant toute mise à jour de l'AMDEC officielle.

## 10.5 Le chiffrage économique a été retiré — et voici pourquoi

Cette section présentait un modèle à 29 paramètres et un solde annuel de
**≈ 1,07 M MAD**. **Ce modèle n'existe plus dans le système, et ces montants ne
sont plus produits par quoi que ce soit.** La couche économique a été retirée du
périmètre ; deux tests interdisent son retour silencieux :
`test_endpoints_economiques_retires` vérifie qu'aucun endpoint ne répond plus, et
`test_api.py` échoue si la chaîne « MAD » réapparaît dans une réponse de l'API.
L'en-tête de `src/analytics/kpi.py` énonce la règle : *« ce module ne contient
aucune hypothèse économique »*.

Le raisonnement est le même que pour les 154 MWh du § 10.1, poussé à son terme.
Dix-neuf des vingt-neuf paramètres — 65 % — étaient marqués « à valider par
OCP ». Un solde calculé aux deux tiers sur des valeurs non confirmées n'est pas
un ordre de grandeur prudent : c'est un chiffre dont la précision affichée, au
millier de dirhams près, contredit sa propre incertitude. Le déclarer provisoire
en note de bas de page ne suffisait pas — un tableau chiffré est ce qu'un
lecteur retient, la réserve est ce qu'il oublie.

Ce que le système publie désormais à la place, et qui est intégralement calculé
sur les données :

| Indicateur | Nature |
|---|---|
| Disponibilité moyenne des mesures du périmètre | `observed` |
| Exposition cumulée à des conditions corrosives | `derived` |
| Marche durablement sous consigne | `observed` |
| Charge d'alertes pour l'exploitant | `observed` |
| Taux horaire de signalement en marche | `observed` |

Chaque figure porte son `evidence_level`. Aucune ne se convertit en dirhams, et
c'est délibéré : **la conversion suppose des données de gestion que ce projet
n'a jamais reçues.** Le jour où elles seront fournies, le calcul se fera à
partir des indicateurs ci-dessus, dont la provenance, elle, est vérifiable.

Les cinq chiffres à demander en priorité — ceux qui rendraient un chiffrage
possible — par ordre d'impact :

1. **Marge contributive d'une tonne de H₂SO₄ PS III** — contrôle de gestion
2. **Durée réelle d'un arrêt pour fuite tube** — chef d'atelier Mécanique
3. **Taux de récupération de production après arrêt** — production
4. **Rendement de pompage eau de mer** — service Utilités
5. **Date de la dernière révision de E7301** — sans elle, la période de référence du jumeau reste une supposition

## 10.6 Intégration au processus existant

Le système ne remplace aucun processus : il s'insère en amont de la demande d'intervention.

```
Surveillance continue  →  Épisode détecté  →  Diagnostic + action AMDEC
                                                       ↓
                                          Audit du Judge (note /10)
                                                       ↓
                                   note ≥ 6 : DI vers la GMAO
                                   note < 6 : revue par l'ingénieur fiabilité
```

Chaque recommandation cite déjà la tâche du plan préventif (A à H) et la check-list d'inspection correspondante : le technicien reçoit une instruction rattachée à un document qu'il connaît, pas une sortie de modèle.


# 11. Limites et angles morts

Un système de surveillance qui ne dit pas ce qu'il ne voit pas donne une fausse assurance. Les angles morts sont donc déclarés explicitement dans le référentiel, exposés par l'API, affichés sur le dashboard, et le Judge sanctionne tout diagnostic qui prétendrait les avoir détectés.

## 11.1 Modes non détectables

| Mode | Criticité | Couverture préventive |
|---|---|---|
| Plaque sacrificielle — dysfonctionnement | 112 | Tâches D (6 mois) et E (3 ans) |
| Vanne d'acide — fuite | 112 | Tâche F (4 ans) |
| Porte de visite — fuite | 90 | Tâche C (1 mois) |
| Vanne d'acide — bouchage | 90 | Tâche F (4 ans) |
| Vanne eau de mer — bouchage | 42 | Tâche G (6 ans) |

Aucune mesure de potentiel ou de courant de protection anodique ne figure dans l'export : **la dégradation de l'anode sacrificielle, mode de criticité la plus élevée, est structurellement invisible au système**. Elle reste couverte par l'inspection périodique.

## 11.2 Limites du jeu de données

**Absence de mesure côté eau de mer.** Ni le débit ni les températures d'entrée et de sortie de l'eau de mer ne figurent dans l'export. La température est reconstituée par la climatologie de Safi (§ 5.3 bis), ce qui rend UA calculable — mais le **débit** reste inconnu, et c'est lui que la régulation manipule. La grandeur obtenue est donc un **UA apparent**, dont la limite est énoncée au § 5.3 bis : tant que la vanne conserve de la marge, elle compense un début d'encrassement. Un accès aux tags eau de mer donnerait un UA vrai et supprimerait ce retard.

**Interprétation des tags non confirmée.** Les correspondances tag / grandeur physique sont déduites, non validées par OCP.

**Pas d'historique de maintenance.** Aucune date d'intervention, de tamponnage de tubes ou de révision n'accompagne les données. Il est donc impossible de valider les détections contre des événements de maintenance réels, ni de calibrer le seuil de réforme (30 % de tubes tamponnés, tâche H).

**Aucune anomalie étiquetée.** Le problème est non supervisé. Les performances de détection ne peuvent pas être exprimées en précision / rappel classiques ; c'est la raison pour laquelle le rapport ne présente ni AUC ni F1 sur la détection d'anomalies — de telles métriques exigeraient une vérité terrain qui n'existe pas.

**Pas d'échelle horaire fine.** Le pas d'une heure interdit la détection d'événements rapides — à-coups, transitoires de vanne.

## 11.3 Limites de la modélisation

**Période de référence supposée saine.** Le jumeau est ajusté sur les six premiers mois, sans certitude que l'échangeur y était propre. Une date de révision fournie par OCP permettrait un ancrage rigoureux.

**Dérive du modèle de référence.** Un modèle ajusté sur janvier–juillet 2024 signale légitimement le régime d'août–octobre comme différent. Sur une exploitation longue, un ré-ajustement périodique et documenté sera nécessaire.

\newpage

# 12. Mise en œuvre

## 12.1 Démonstration par rejeu historique accéléré

Le simulateur rejoue les 10 180 heures réelles à vitesse configurable, de 24 h/s à 720 h/s. À l'instant *t*, seule la fenêtre [début, *t*] est transmise à la détection : **le système ne voit jamais le futur**. C'est cette contrainte qui rend la démonstration honnête.

Un générateur synthétique aurait été plus simple et sans valeur : il n'aurait prouvé que la capacité du système à retrouver des anomalies qu'on y aurait soi-même placées.

## 12.2 Interfaces

L'API FastAPI expose **45 routes `/api/`** couvrant la santé détaillée du système, la gouvernance, les séries temporelles, la santé des capteurs, les épisodes, l'analyse à la demande, le pilotage du rejeu, l'évaluation du Judge, les sessions technicien, les notifications, le cycle de vie des alarmes et les gammes de maintenance.

L'interface est servie par la même application, sans étape de compilation. Elle remplace le synoptique statique par une représentation WebGL **horizontale et conceptuelle** du E7301 : calandre, fonds, brides, plaques tubulaires, faisceau illustratif et selles. Aucune cote ni quantité de tubes n'est revendiquée sans les plans 711-104/105/106. Le modèle tourne lentement, peut être orienté à la souris et colore les zones concernées en ambre ou rouge selon la sévérité. Un clic ouvre l'événement correspondant ou la vue AMDEC filtrée ; un mode sans WebGL reste disponible.

Les douze tags DCS sont accessibles dans une constellation de capteurs indiquant dernière valeur, unité, rôle et disponibilité. Un clic isole le signal dans le graphe. Six familles de courbes couvrent températures, titres acides, débits/charge, contexte absorption, instrumentation dégradée et performance observée/attendue, sur cinq fenêtres temporelles. Les valeurs brutes des deux capteurs dégradés restent visibles pour expliquer la panne, mais sont strictement exclues de l'apprentissage.

Lorsque l'administrateur active explicitement le profil local de démonstration, le technicien saisit un e-mail présent dans la liste autorisée ; cet e-mail identifie la session et peut devenir un destinataire d'alerte. Le secret est vérifié par PBKDF2 ; la session reste opaque côté serveur avec cookie HttpOnly/SameSite, expiration, rotation et protection CSRF. Une file SMTP asynchrone envoie les décisions critiques acceptées, avec dédoublonnage et temporisation, uniquement lorsqu'un relais est configuré. Ces e-mails complètent l'alarme opérateur ; ils ne la remplacent pas. Pour la production, le démarrage impose un fournisseur OIDC et refuse ce profil local.

## 12.3 Reproductibilité et tests

| Élément | Valeur |
|---|---|
| Tests automatisés (Python) | 277 cas |
| Vérifications des bancs du poste (jsdom) | 98 — câblage, scène 3D, écran de démarrage |
| Couverture de lignes | 87,15 % (seuil bloquant en intégration continue : 85 %) |
| Fonctionnement hors ligne | Intégral pour la détection et le Judge |
| Graine aléatoire fixée | Oui (42) |
| Dépendance à un service externe obligatoire | Aucune |
| Services optionnels | SMTP et Gemini |

Les tests couvrent la cohérence du référentiel (dont la vérification que C = F × G × N pour chaque mode AMDEC), la détection des défauts capteur réels, la physique de l'échangeur, le signe du résidu, et surtout **les tests dédiés à la capacité du Judge à détecter chaque type de faute**. Ces derniers mesurent une NON-RÉGRESSION des contrôles implémentés, pas une validation : chaque piège du catalogue porte le code d'anomalie que le Judge sait produire. La mesure de généralisation est distincte et plus basse — c'est celle des mutations non ciblées, portées sur des propriétés qu'aucun des huit contrôles ne lit.

Le mode déterministe n'est pas un pis-aller : il fournit au Judge un point de comparaison pour mesurer ce qu'un modèle de langage apporte réellement, et garantit que le système reste démontrable en soutenance sans connexion ni quota.

\newpage

# 13. Conclusion et suites

## 13.1 Ce qui a été établi

Le travail a produit un système de surveillance du refroidisseur E7301 opérationnel sur données réelles, dont chaque alerte se rattache à un mode de défaillance de l'AMDEC de 2019 et à une tâche du plan de maintenance préventive.

Quatre résultats méritent d'être retenus :

1. **Deux défaillances d'instrumentation non tracées ont été caractérisées** — TI5303-4X saturé depuis août 2024, PHI5306X-3 figé environ 1 900 heures — ainsi qu'une interruption d'acquisition de sept tags en juin 2024. Ces constats ont une valeur opérationnelle immédiate, indépendamment du reste du système.

2. **Une erreur d'analyse a été détectée et corrigée par le projet lui-même.** Une première lecture attribuait le changement de régime à la panne du capteur TI5303-4X ; l'analyse par décades a montré que le phénomène commençait 100 jours plus tôt. L'hypothèse a été abandonnée. Un projet qui ne documente pas ses corrections n'est pas vérifiable.

3. **Le Judge a été rendu testable.** En le dotant d'un recalcul déterministe
et en le soumettant à un banc de 118 pièges ciblés, sa capacité à détecter
les incohérences couvertes par ses règles est mesurée. Ce résultat ne constitue
pas une validation indépendante sur décisions terrain.

4. **Le banc d'évaluation a corrigé le Judge, et le Judge a corrigé l'agent.** Cette boucle est la démonstration concrète de ce qu'un mécanisme d'audit automatique apporte.

## 13.2 Suites recommandées

**À court terme, avec OCP**

- Faire valider les interprétations de tags par l'équipe de conduite PS III (fichier `tags.yaml`) ;
- Expliquer les deux excursions de régulation (mai 2024, août-novembre 2024) : changement de consigne, vanne d'eau de mer en pleine ouverture, ou bascule en mode dégradé ?
- Déclencher une demande d'intervention instrumentation sur TI5303-4X et PHI5306X-3 ;
- Obtenir l'historique des interventions pour ancrer la période de référence du jumeau.

**À moyen terme**

- Intégrer les tags eau de mer — débit et températures — pour passer du UA apparent à un UA vrai, et supprimer le retard de détection lié à la marge de vanne ;
- Réduire le pas d'échantillonnage à la minute pour la détection d'événements rapides ;
- Instrumenter la protection anodique afin de couvrir le mode de criticité 112 ;
- Étendre la démarche aux autres refroidisseurs de PS II et PS III, le référentiel étant conçu pour être dupliqué par fichier YAML.

**Sur le plan méthodologique**

Le banc d'injection de fautes constitue un patron réutilisable pour tout système de décision automatique déployé chez OCP. La question qu'il pose — *« quelles fautes ce système doit-il détecter, et les détecte-t-il réellement ? »* — devrait précéder tout déploiement.

\newpage

# Annexe A — Correspondance modes AMDEC / indicateurs

| Mode | Criticité | Indicateurs de détection |
|---|---|---|
| `FAISCEAU_BOUCHAGE` | 105 | Dérive du coefficient d'échange (`ua_residual_trend_14d`), résistance d'encrassement (`fouling_resistance`), perte de contrôle sur la sortie acide au stade terminal |
| `FAISCEAU_FUITE` | 105 | Chute soutenue de titre, divergence des analyseurs |
| `FAISCEAU_CORROSION` | 105 | Titre sous spécification, température d'entrée excessive, exposition cumulée |
| `CALANDRE_FUITE` | 90 | Perte de débit non expliquée par la charge |
| `CAPTEUR_DEFAILLANT` | 108 | Codes qualité, gel de signal, butée d'échelle, hors plage physique |
| `PLAQUE_SACRIFICIELLE_DYSFONCTION` | 112 | **Aucun — angle mort déclaré** |
| `PORTE_VISITE_FUITE` | 90 | **Aucun — angle mort déclaré** |
| `VANNE_ACIDE_FUITE` | 112 | **Aucun — angle mort déclaré** |
| `VANNE_ACIDE_BOUCHAGE` | 90 | **Aucun — angle mort déclaré** |
| `VANNE_EM_BOUCHAGE` | 42 | **Aucun — angle mort déclaré** |

# Annexe B — Les 11 features contractuelles du modèle

Liste et ordre repris de `MODEL_FEATURES` dans `src/features/e7301_features.py`.
L'ordre est contractuel : le manifeste du modèle le consigne et
`validate_model_manifest` refuse le chargement d'un artefact dont le schéma
ordonné diffère.

| Feature | Nature |
|---|---|
| `ua_residual_z` | Écart standardisé du coefficient d'échange — **porte le diagnostic d'encrassement** |
| `regulation_effort_z` | Effort de régulation standardisé — conduite, jamais une preuve d'encrassement (§ 5.3) |
| `t_in_residual_z` | Résidu de température d'entrée — contexte amont |
| `conc_min` | Titre acide, minimum des deux analyseurs |
| `conc_bias_drift_z` | Dérive standardisée du biais entre analyseurs |
| `conc_drop_24h` | Variation de titre sur 24 h |
| `flow_per_load` | Débit acide normalisé par la charge |
| `d_t_out` | Variation instantanée de la température de sortie |
| `d_conc` | Variation instantanée du titre |
| `t_out_local_z` | Déviation locale glissante de la sortie |
| `t_in_local_z` | Déviation locale glissante de l'entrée |

*Une version précédente de cette annexe annonçait dix features et citait
`duty_residual_z` et `duty_residual_trend_14d`, qui n'existent pas — vestiges
de l'approche réfutée au § 5.3. Elle omettait les trois grandeurs qui portent
la physique de l'échangeur.*

# Annexe C — Sources documentaires

1. Fiche Équipement — Refroidisseur de séchage PS III (FO03-PR01-PSR05-ICS, 23/09/2019, OUBID)
2. Fiche Identification sous-ensemble — Refroidisseur de séchage PS III
3. Liste des composants — Refroidisseur de séchage PS III (20/09/2019)
4. **AMDEC — Refroidisseur de séchage PS III (23/09/2019, OUBID)**
5. Plan de Maintenance Préventive — S-PC-E7301 (FO06ST-FI-01-OI, 23/04/2018)
6. Check-list Inspection externe et interne (H3SH 16_3, 26/09/2019)
7. Gamme PV — Démontage/remontage couvercles refroidisseur PS III (21/09/2016)
8. Gamme de tamponnage mécanique des tubes (16/03/2015)
9. **DATA.xlsx — Export DCS, 01/01/2024 → 28/02/2025**
