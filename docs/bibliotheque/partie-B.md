# Bibliothèque du mémoire E7301 — partie B

Suite de `docs/bibliotheque/partie-A.md` (sections 0–16). Numérotation à partir
de 17, concaténation directe.

Marqueurs de provenance, comme en partie A :
**[LU]** lecture intégrale du fichier · **[MESURÉ]** issu d'une exécution ·
**[DÉCLARÉ]** affirmé par le dépôt, non recalculé.

> **État de la partie B au 8 août 2026.** Les sections **17 et 23** sont écrites.
> Les sections 18, 19, 20, 21, 22, 24 restent à produire — consigne détaillée
> dans `docs/audits/CONSIGNE-BIBLIOTHEQUE-B.md`, **avec ses amendements**, qui
> corrigent deux prémisses périmées.

Tous les chiffres de la section 17 sont produits par
`scripts/collecte_chiffres_front.py`, sortie dans `reports/chiffres_front.txt`.
Aucun n'est repris d'un commentaire du code.

---

# 17. La réalisation — le poste opérateur

C'est le chapitre que le jury manipulera. Il repose sur la lecture intégrale de
`api/dashboard.html`, `api/static/app.js`, `api/static/twin.js`,
`api/static/app.css` et `docs/decisions/ADR-008-interface-isa-101.md`, et sur une
campagne de mesure du 8 août 2026.

## 17.1 Volumétrie réelle **[MESURÉ, 2026-08-08]**

`python scripts/collecte_chiffres_front.py`

| fichier | à l'ouverture de l'audit | après les corrections de § 17.8 |
|---|---|---|
| `api/dashboard.html` | 586 | 593 |
| `api/static/app.js` | **2 445** | 2 450 |
| `api/static/twin.js` | 2 167 | 2 167 |
| `api/static/app.css` | **1 167** | 1 167 |
| `api/main.py` | **1 830** | 1 830 |
| **total** | **8 195** | 8 207 |

> **Deux colonnes, et c'est volontaire.** La session a corrigé trois commentaires
> fautifs (§ 17.8), ce qui a ajouté douze lignes au périmètre qu'elle était en
> train de mesurer. Publier la seule valeur finale masquerait que l'instrument a
> bougé pendant la mesure ; publier la seule valeur initiale la rendrait
> irreproductible dès le prochain lancement du script. **Les deux sont écrites,
> avec ce qui les sépare.** C'est la même exigence que celle imposée aux
> décomptes de bancs de la partie A.

> **Trois chiffres de la consigne ont dérivé** : elle annonce `app.js` à 2 407
> lignes (2 445 à l'ouverture) et `main.py` à 1 759 (1 830). `app.css` n'y figure
> pas du tout, alors qu'il porte toute la charte ISA-101. Le périmètre du front
> n'est pas de 5 160 lignes mais de **6 365**, feuille de style comprise.

**Part de commentaire** : 539 lignes dans `app.js` (**22,0 %**), 443 dans
`twin.js` (**20,4 %**). Un cinquième du front est de la prose que rien n'exécute
— c'est le terrain que l'amendement A2 de la consigne désigne, et § 17.8 y
revient avec ce qu'on y a trouvé.

## 17.2 Hiérarchie de vues — la structure ISA-101 **[LU + MESURÉ]**

**Trois vues**, conformes à la structure hiérarchique de la norme, du général au
détail. Le décompte est exact : 3 boutons `role="tab"`, 3 sections
`role="tabpanel"`, aucun orphelin.

| n° | vue | rôle | cartes |
|---|---|---|---|
| I | **Salle** | état de l'appareil, situation prioritaire, décision attendue | 3 |
| II | **Intégrité** | épisodes, santé des capteurs, couverture AMDEC, plan préventif | 8 |
| III | **Contrôle** | cohérence des décisions, sensibilité, bancs de validation | 12 |

**23 cartes** `<article class="panel">` au total, 4 tableaux, 3 `<canvas>`, une
seule boîte de dialogue `<dialog>` réemployée par quatre gestes distincts
(décision, pièce 3D, alarme, épisode analysé).

**Le parcours de l'exploitant** suit la gravité décroissante de l'urgence, pas
l'arborescence des données : il ouvre **Salle** en prise de quart et y reste ;
il passe en **Intégrité** quand une alarme demande un rattachement AMDEC ou une
gamme d'intervention ; il n'ouvre **Contrôle** que pour contester une décision —
c'est la vue du jury et de l'ingénieur fiabilité, pas celle du quart. La
répartition des cartes le confirme : la vue la moins consultée en porte la
moitié.

### Ce que la norme demande, et ce que le poste en applique **[LU]**

ADR-008 revendique quatre principes. Chacun est vérifiable à l'écran :

**1. La couleur est réservée à l'anormal.** Le principe est le plus mal compris
de la norme — souvent réduit à « tout mettre en gris ». L'intention réelle est
que *la saturation soit une ressource rare*. Le poste tient la règle par une
convention de nommage : les teintes procédé existent en deux exemplaires,
`--acid` / `--acid-live` et `--sea` / `--sea-live`, et les variantes vives ne
sont employées **que sur un état anormal**. Un circuit s'identifie par une teinte
désaturée ; il ne réclame l'œil que lorsqu'il va mal.

**2. La gravité n'est jamais portée par la seule couleur.** Chaque état porte un
**glyphe**, un **mot** et une **couleur** — `sevMark()` produit les trois
ensemble, et il n'existe aucun autre chemin pour afficher une sévérité. Les
bordures d'alarme portent en plus un motif distinct : trait plein pour
l'avertissement, trait double pour le critique. Justification donnée par le
dépôt : environ 8 % des hommes ne distinguent pas le rouge de l'ambre, et une
capture en noir et blanc les confond toujours — or une soutenance se lit souvent
sur un tirage papier.

**3. Trois niveaux de conscience de situation.** Le modèle d'Endsley, qui
structure la norme, distingue **percevoir**, **comprendre** et **projeter**. Les
deux premiers étaient traités ; le troisième a été ajouté sous la forme d'une
**tendance** portée par chacune des six cartes du bandeau de lecture.

`trendOf()` mérite d'être cité, parce qu'il illustre une erreur de conception
courante et sa correction. La première version déclarait une pente significative
dès qu'elle déplaçait la grandeur de 0,5 % de son **niveau moyen**. Pour l'écart
de consigne, dont la moyenne vaut zéro par construction, ce seuil tombait à zéro :
la moindre oscillation lisait « en hausse », les six cartes affichaient la même
flèche montante, et l'indicateur devenait décoratif. La zone morte se mesure
désormais sur la **dispersion résiduelle** autour de la droite de régression —
en dessous d'un demi écart-type, ce qu'on voit est du bruit, et le poste le dit.

> **Un indicateur qui s'allume toujours n'indique rien.** C'est le même défaut
> que le taux de détection à 100 % du banc de pièges (§ 17.5), et que la colonne
> de score saturée à 1,000 du tableau des épisodes : trois fois, la grandeur
> mise en avant était bornée par construction.

**4. Fluidité.** Trois dispositifs, tous vérifiables :

- la série temporelle n'est rechargée que si la fenêtre demandée a changé
  (`SERIES_MIN_INTERVAL_MS = 8000`) ; auparavant 650 points étaient retransmis
  toutes les 1,6 s pour déplacer un curseur d'un pixel ;
- le rendu 3D **se dégrade tout seul** sous 22 images par seconde — ombres
  d'abord, puis résolution, puis masquage du faisceau hors coupe ;
- le moteur 3D est **suspendu hors de sa vue** (`setPaused(view !== "salle")`).

Toutes les animations s'effacent si le système déclare `prefers-reduced-motion`,
lu une fois à la construction du jumeau.

### Contraste : le seul écart mesuré sur ADR-008 **[MESURÉ]**

Le contraste a été recalculé, encre par encre, sur les **cinq** fonds réellement
employés — et non sur un seul, ce qui était le défaut de la correction
précédente :

| jeton | valeur | pire fond | rapport |
|---|---|---|---|
| `--ink` | `#e9f2f1` | `--raise` | 14,61:1 |
| `--ink-2` | `#b3c6c7` | `--raise` | 9,37:1 |
| `--ink-3` | `#7c9396` | `--raise` | 5,13:1 |
| `--ink-4` | `#718a8e` | `--raise` | **4,54:1** |

`--ink-4` porte les micro-libellés en 10 px, c'est-à-dire le texte le plus petit
du poste. Le seuil AA est 4,5:1 : il est tenu, de justesse, **sur tous les fonds
y compris le survol** — et c'est ce dernier point qui avait été manqué, puisque
`--raise` est le fond de survol de toutes les lignes du poste, donc l'état exact
dans lequel l'exploitant lit.

> **ADR-008 annonce « 4,6:1 minimum ». La mesure donne 4,54:1**, que la feuille
> de style arrondit honnêtement à « 4,5:1 au pire ». L'ADR arrondit dans l'autre
> sens et se place au-dessus de la valeur vraie. L'écart est d'un dixième et
> sans conséquence pratique — mais sa **direction** est celle du fil conducteur :
> le fichier exécuté et vérifié par un banc porte la valeur juste, le document
> qu'on se contente de lire porte la valeur flatteuse. À corriger dans ADR-008,
> pas en annexe.

## 17.3 Le jumeau numérique **[LU + MESURÉ]**

`api/static/twin.js`, 2 167 lignes, Three.js r128 sans aucune ressource réseau :
la carte d'environnement est générée au démarrage par `PMREMGenerator` à partir
d'une scène construite en mémoire, et les cinq textures de matière (peinture,
acier brossé, béton, calorifuge, caillebotis) sont peintes dans des `canvas`.
C'est la condition d'ADR-006 — poste local, hors ligne — appliquée au rendu.

### Les proportions viennent de la fiche, pas du dessin

La fiche équipement porte **SIZE 1118-9754**. Les deux nombres sont lus comme le
diamètre intérieur de calandre (1 118 mm) et la longueur de tube (9 754 mm), et
le modèle est construit à l'échelle 1 unité = 1 mètre sur ces valeurs. Il en
résulte un appareil **long et élancé**, très différent du tonneau trapu qu'on
obtient en dessinant « un échangeur » sans lire la fiche.

**Aucune autre cote n'est revendiquée**, et `topology.yaml` le déclare :
`dimensional_status: "representation a l'echelle, non cotee"`. Les plans
constructeur 711-104, 711-105 et 711-106 ne sont pas au dossier. Le pied de
scène affiche la mention et la source, calculées et non écrites en dur.

### Ce que la scène contient **[MESURÉ]**

`node scripts/twin_smoke.mjs` :

| grandeur | mesure |
|---|---|
| pièces distinctes dans la scène | **10** |
| objets sélectionnables au pointeur | **102** |
| tubes réellement instanciés | **1 541** |
| capteurs posés en 3D | **12** |
| chicanes segmentaires | 9 |
| matériaux de la palette | 20 |
| textures procédurales | 9 |

Le faisceau est bâti par une boucle sur un pas triangulaire de 24,38 mm dans un
cercle utile de 504 mm de rayon : **1 541 tubes**, en trois appels de rendu grâce
à `InstancedMesh`. Le commentaire de `_guardPerformance` annonce « plus de
1 500 tubes » — **conforme**, et c'est l'une des rares assertions chiffrées du
front qui survive au recomptage.

### La correspondance pièce ↔ référentiel est exacte **[MESURÉ]**

C'est le contrôle que la consigne demandait de faire route par route, appliqué
ici à la géométrie :

| | |
|---|---|
| pièces déclarées dans `topology.yaml` | **10** |
| pièces modélisées dans `twin.js` | **10** |
| déclarées au référentiel, non modélisées | **aucune** |
| modélisées hors référentiel | **aucune** |
| ciblées par `finding_map`, non modélisées | **aucune** |

`SHELL`, `TUBESHEET`, `BUNDLE`, `WATERBOX_IN`, `WATERBOX_OUT`, `NOZZLE_ACID_IN`,
`NOZZLE_ACID_OUT`, `VALVE_ACID`, `VALVE_SEA`, `ANODE`. Aucun écart, dans aucun
sens. C'est le seul câblage du poste qui soit parfaitement fermé.

> **Avertissement de méthode, et il compte.** Le premier motif de recherche
> employé pour ce décompte — `_register(x, "CODE")` — a conclu que quatre pièces
> n'étaient pas modélisées. C'était faux : `NOZZLE_ACID_IN`, `NOZZLE_ACID_OUT`,
> `VALVE_ACID` et `VALVE_SEA` sont construites par des fonctions auxiliaires qui
> reçoivent le code **en paramètre**, aux lignes 885-886 et 906-907. Le motif ne
> voyait que les littéraux écrits sur place.
>
> C'est le défaut de test dominant du dépôt — *la portée de l'assertion ne
> coïncide pas avec celle de l'intention* (§ 23.3) — commis dans l'instrument
> même qui sert à le mesurer, et rattrapé avant publication. Le script porte le
> commentaire. **Le résultat faux n'a pas été publié en annexe : le contrôle a
> été corrigé.**

### `finding_map` : comment une constatation allume une pièce **[LU]**

Le rattachement d'une anomalie à une pièce est une **connaissance métier**, pas
un détail d'affichage. Il vit donc dans `topology.yaml`, et le tuteur OCP peut le
corriger sans qu'une ligne de code change. Avant ce fichier, le rattachement
était improvisé côté interface par recherche de sous-chaîne dans le libellé :
`CONC_DROP_SEVERE` — signature d'une fuite de tube, l'événement le plus grave que
ce système puisse voir — ne colorait **aucune** pièce.

`twinStateFrom()` fait quatre choses, et rien d'autre :

1. il ignore les constatations `INFO` et `NORMAL` — le jumeau ne s'allume que
   sur un état qui appelle une décision ;
2. il lit `map[finding.code]` ; **un code inconnu n'allume rien**, plutôt que
   d'accuser la mauvaise pièce ;
3. il retient la sévérité **maximale** par cible, jamais la dernière vue ;
4. il rend deux sacs séparés, pièces et capteurs.

**18 codes de constatation** sont déclarés dans `finding_map`. **Cinq n'allument
délibérément aucune pièce**, et c'est un choix de gouvernance à écrire tel quel :

| code | pourquoi rien ne s'allume |
|---|---|
| `OVERCOOLING_REGIME` | un **régime de conduite**, pas une dégradation ; l'annoncer sur le faisceau accuserait une pièce sur la foi d'un signal qui ne la concerne pas |
| `CONC_BIAS_DRIFT` | dérive entre deux analyseurs : l'écart est instrumental |
| `SENSOR_FAULT` | défaut de mesure, aucune pièce de procédé en cause |
| `MODEL_UNAVAILABLE` | état du système de surveillance, pas de l'appareil |
| `NOT_RUNNING` | la ligne est à l'arrêt |

> Cinq codes sur dix-huit produisent volontairement un écran muet. C'est le même
> principe que le refus d'imputer une valeur manquante : **ne rien affirmer coûte
> moins cher qu'affirmer à côté.**

Symétriquement, **cinq pièces modélisées ne sont allumées par aucune
constatation** : `SHELL`, `WATERBOX_IN`, `WATERBOX_OUT`, `VALVE_SEA` et
**`ANODE`**. La dernière est le point à défendre en soutenance.

> **L'anode sacrificielle — criticité AMDEC 112 — est modélisée en 3D
> précisément parce qu'aucun capteur ne la couvre.** Elle est visible, cliquable,
> et son panneau affiche « Instrumenté : non — angle mort » avec la tâche
> préventive qui la couvre. Le poste **montre ce qu'il ne sait pas voir**, au
> lieu de le laisser hors du champ. C'est la traduction visuelle de la règle du
> référentiel : tout angle mort doit être déclaré et couvert par le préventif.

### La vue éclatée : la pièce la plus accusée est celle qu'on ne voit pas **[LU]**

Colorer une pièce en rouge ne suffit pas quand elle est **enfermée**. Le faisceau
tubulaire est le composant le plus souvent mis en cause par `finding_map` — il
figure dans neuf codes sur dix-huit — et il est invisible tant que la coupe n'est
pas active. L'exploitant lisait « CRITIQUE » dans le bandeau et voyait un
appareil intact : la contradiction la plus coûteuse qu'une supervision puisse
produire.

`_eclater()` extrait la pièce hors de l'enveloppe, radialement, et l'y maintient
**tant que la panne dure** — un aller-retour bref se lirait comme un artefact
d'affichage, une pièce restée sortie se lit comme une désignation.

La distance se **calcule** : rayon d'enveloppe + demi-épaisseur de la pièce dans
sa direction de sortie + 0,75 m de marge. Une valeur en dur de 1,15 m paraissait
franche jusqu'à confrontation aux cotes réelles — le faisceau a 0,5 m de rayon et
la calandre 0,56 m, si bien qu'à 1,15 m son bord inférieur **effleurait** le
dessus de l'enveloppe : à l'écran, une pièce posée sur l'appareil, pas une pièce
extraite. Une petite vanne sort peu, le faisceau sort beaucoup, chacun se dégage
nettement.

Chaque pièce extraite porte un **cartouche** — glyphe ▲, mot CRITIQUE ou ALERTE,
et **nom de la pièce**, parce qu'un halo rouge sans nom oblige à chercher. Le nom
vient de `topology.components[].label`, donc du dossier machine : un repère de
défaut doit nommer la pièce comme la nomme la GMAO. Le cartouche est rendu **sans
test de profondeur**, donc il traverse la tôle et désigne la pièce même fermée.

Deux subtilités que le code documente et qu'il faut retenir :

- **L'ordre compte.** `_eclater` fige, à la première mise en défaut, le centre
  que la pièce occupe **au repos** ; `_marquerPieces` s'en sert pour ancrer le
  cartouche. Dans l'ordre inverse, une panne qui persiste recalculerait le centre
  depuis la position déjà éclatée, et le repère s'éloignerait un peu plus à
  chaque image.
- **Le mouvement n'existe qu'en un exemplaire.** `animerEclats(dt)` a été
  extraite de la boucle de rendu pour une raison d'audit : le banc `twin_smoke`
  ne peut pas appeler `_loop`, qui exige un contexte WebGL que jsdom n'a pas, et
  y avait donc **réimplémenté l'interpolation pour la mesurer**. Le banc validait
  sa copie, pas l'original. `« 32/32 »` ne disait rien du code servi au
  navigateur. Un contrôle qui teste sa propre réimplémentation ne teste rien —
  c'est la règle 1 des conventions de test, rencontrée ici dans le front.

### Le tiroir capteur **[LU]**

Cliquer un capteur ouvre `/api/sensor/{alias}` et remplit un panneau latéral :
valeur courante, disponibilité colorée par palier (> 95 % / > 70 %), courbe sur
une fenêtre **propre au tiroir** (504 h par défaut — la version précédente
empruntait celle du sélecteur de tendance, couplage arbitraire et invisible),
neuf faits chiffrés, et la justification textuelle du sens du tag.

Deux corrections de ce panneau valent d'être citées, parce qu'elles portent sur
le geste central de la vue Salle :

**Deux identifiants machine dans la même phrase.** Le tiroir affichait
« Capteur `primary` · confiance `isa_5_1,process,data` ». `role` est un code du
référentiel ; et `confidence` **a gardé son nom en changeant de sens** — il ne
porte plus un niveau de confiance mais la liste des bases ayant servi à établir
le sens du tag. Les deux tables de traduction existaient déjà dans le fichier,
elles n'étaient simplement pas appelées ici. Le tiroir lit désormais « Capteur du
périmètre · sens établi par nomenclature ISA-5.1, physique du procédé,
comportement des données ».

**Un capteur mort n'affiche pas de mesure.** `TI5303-4X` est collé à sa butée
d'échelle 327,67 depuis août 2024 — 32767/100, un dépassement d'entier signé sur
16 bits côté acquisition. Le jumeau affichait « 327,7 » dans la même typographie
que les mesures valides, *c'est-à-dire exactement ce que fait le DCS et
exactement ce que ce projet lui reproche*. L'étiquette porte désormais « hors
service » et « signal figé à … ». Ces deux capteurs sont le cas d'école du
mémoire : les montrer comme des mesures ruinerait la démonstration.

### Collisions d'étiquettes **[LU]**

Douze étiquettes ancrées en 3D finissent par se superposer sous certains angles,
et une pile de textes illisibles est pire que pas d'étiquette. `_resolveLabel­Collisions()`
projette chaque étiquette en coordonnées écran, trie par distance à la caméra et
tranche en trois cas :

| situation | traitement |
|---|---|
| étiquette **derrière** la caméra (`z > 1`) | effacée |
| étiquette **débordant du cadre** | effacée — une étiquette à moitié coupée par le bord est pire qu'absente |
| **recouvrement** avec une plus proche | estompée à 0,12, pas masquée : le repère reste devinable |

**Un capteur en défaut n'est jamais effacé**, quel que soit le conflit. C'est la
seule exception, et c'est la bonne.

La demi-taille employée pour détecter le recouvrement est **dérivée** des
constantes d'échelle `LABEL_W` et `LABEL_H` par `labelHalfNDC()`, et non recopiée
en deux nombres calés à la main. Sans cela, changer l'échelle des étiquettes sans
recalculer les seuils ferait sous-estimer les recouvrements : *le résolveur
laisserait passer des chevauchements qu'il croit traiter*. Un contrôle qui ment
en silence.

### Accessibilité de la scène **[LU + MESURÉ]**

Un `<canvas>` n'est pas focusable et ne reçoit aucun événement clavier : sans
traitement, toute la scène 3D est inaccessible sans souris. Le poste pose
`tabIndex = 0`, `role="application"` et une `aria-description` qui **énonce les
commandes** ; flèches pour orienter, `+`/`-` pour zoomer, `T` pour parcourir les
douze capteurs, `Entrée` pour ouvrir, `Origine` pour recadrer. Sept vérifications
du banc `twin_smoke` couvrent ce seul point.

## 17.4 Les familles de signaux **[LU + MESURÉ]**

**Dix familles**, 20 courbes, cinq fenêtres (24 h, 7 j, 21 j par défaut, 90 j,
tout). Le menu HTML et la table `TREND_SETS` sont **exactement en
correspondance** : aucune option sans famille, aucune famille sans option.

| famille | ce qu'elle trace | pourquoi elle existe |
|---|---|---|
| **Coefficient d'échange · UA** | `ua_kw_per_k` vs `ua_expected` | l'indicateur réel d'ADR-002 |
| Résistance d'encrassement | `Rf = 1/UA − 1/UA attendu` | lecture directe de la dégradation |
| Température d'entrée · obs./att. | `T_ACID_IN` vs `t_in_expected` | le seul résidu indépendant de la variable régulée |
| Source froide · eau de mer | `T_SEAWATER` | l'entrée extérieure à toute boucle |
| Thermique · 3 capteurs | `T_ACID_IN`, `T_ACID_OUT`, `T_CIRC_1300` | lecture brute |
| Titre acide · 2 analyseurs | `C_ACID_1100`, `C_ACID_1200` | redondance analytique |
| Débit & charge | `F_ACID`, `LOAD_SULFUR` | allure de marche |
| Effort de régulation | `duty_kw` vs `duty_expected` | ADR-001, publié pour ce qu'il est |
| Contexte absorption | `F_3412`, `A_3301`, `A_3302` | amont / aval |
| Instrumentation dégradée | `TI_5303`, `PHI_5306` | les deux capteurs exclus, montrés bruts |

Trois choses à dire de cette liste, et elles sont toutes trois des arguments du
rapport.

**La famille qui porte le diagnostic manquait.** Le menu offrait six familles,
dont **aucune ne traçait le coefficient d'échange**. L'exploitant pouvait suivre
le duty — dont ADR-001 démontre qu'il redit l'écart de consigne — et pas UA, la
seule grandeur construite sur ce que l'encrassement dégrade. `echange` est
désormais **en tête de liste** : c'est celle qu'on ouvre en premier quand on
cherche une dérive du faisceau.

**Le titre disait le contraire de la mesure.** La paire duty s'intitulait
« Performance observée / attendue ». C'est précisément ce qu'elle n'est pas :
son résidu vaut l'écart de consigne changé de signe (r = −0,938). Elle s'appelle
maintenant **« Effort de régulation »**. Renommer une courbe est un geste de
gouvernance, pas de mise en forme : *le nom affiché est ce que le jury retiendra
de la grandeur*.

**L'instrumentation défaillante est une famille du menu.** Les deux capteurs
exclus du périmètre restent traçables, en valeurs DCS brutes, avec leur butée
annoncée dans le libellé — « TI5303-4X · butée 327,67 », « PHI5306X-3 · figé
−14,407 ». Le poste ne cache pas ce qu'il a écarté.

## 17.5 Ce que chaque vue montre, panneau par panneau **[LU]**

### Vue I · Salle

Le jumeau occupe la scène. Deux cartouches en vis-à-vis — **état de l'appareil**
(traduit : « En marche », jamais `RUNNING`) et **situation** (sévérité + note du
contrôleur). Ils partagent un conteneur et s'empilent sous 760 px : le verdict de
sévérité était auparavant masqué sur écran étroit, c'est-à-dire *la seule lecture
qu'un agent de ronde consulte sur sa tablette*.

Sous la scène : la **frise** des 14 mois, avec un repère par épisode, dont les
plus francs sont distingués — non par le score, qui sature à 1,0000 et ne sépare
rien, mais par la **marge en écarts-types**, non bornée.

Puis le **bandeau de lecture** : six cartes, chacune portant sa provenance en
sous-titre. Les quatre premières sont des mesures et citent leur **tag DCS** ;
les deux dernières sont calculées et citent leur **formule** (`ρ·cp·Q·ΔT`,
`sortie − 66 °C`). La version précédente affichait `duty_kw` et
`control_deviation` — des noms de variables Python — là où les autres cartes
affichaient un tag d'instrumentation. Un opérateur ne peut rien faire d'un
identifiant de code, et un jury y voit la couture entre le calcul et l'affichage.

Enfin la **courbe** (§ 17.4), le **diagnostic** courant avec ses réserves
traduites, et le **journal du rejeu**, filtrable en trois : tout, alertes, rejets.

### Vue II · Intégrité

Bandeau de KPI, calendrier de densité des épisodes, photographie de la plaque
tubulaire **avec sa source citée** (« gamme OCP FO09-PSS01-IDS/C, édition 02 » —
une photographie industrielle sans source est invérifiable, et celle-ci ne sort
pas d'une banque d'images), tableau des épisodes les plus sévères, disponibilité
des douze capteurs, **registre d'alarmes ISA-18.2** avec ses actions par état,
gammes d'intervention OCP, plan préventif A → H, et le tableau AMDEC intégral.

Le tableau AMDEC porte la correction la plus coûteuse du poste, et elle est de
gouvernance pure. Le référentiel mélange **trois natures de lignes** : la
transcription fidèle de l'AMDEC OCP du 23/09/2019, des règles dérivées d'une
ligne source, et des cotations proposées par ce projet. Le domaine les distingue
rigoureusement — champ `provenance_category`, valeurs d'origine conservées — puis
le tableau les affichait **toutes à l'identique**.

> Un lecteur voyait « Chaîne de mesure · C = 108 » avec exactement la même
> autorité que « PLAQUE SACRIFICIELLE · C = 112 », alors que la première est une
> proposition de stage et la seconde une cotation OCP. C'est précisément le genre
> de confusion qu'un jury cherche — et le travail de traçabilité était **déjà
> fait**, il ne manquait qu'à le montrer.

Chaque ligne porte désormais un marqueur — `OCP`, `dérivée`, `projet`,
`hypothèse`, `terrain` — avec le détail en infobulle et une **légende** au-dessus
du tableau. Sans la légende, le marqueur serait un ornement ; avec elle, c'est
une lecture : trois natures, trois niveaux d'autorité, et le lecteur sait laquelle
il conteste.

La colonne « Détectable » porte une seconde correction, du même genre. Elle se
lisait `m.observable ? "oui" : "non — angle mort"`. Le serveur publie pourtant
`observabilite` **à trois valeurs**, parce que le booléen faisait afficher « non —
angle mort » sur la corrosion du faisceau et la fuite de calandre — deux modes
auxquels le moteur de règles rattache activement des constatations. Les compter
comme couverts surévaluait la couverture de 18 points ; les compter comme
aveugles effaçait la surveillance réelle. **La correction avait été portée côté
serveur et pas à l'écran** : le poste démentait sa propre chaîne de détection.

### Vue III · Contrôle

Douze cartes, c'est-à-dire la moitié du poste. Elles répondent une à une aux
questions qu'un jury pose : le contrôleur discrimine-t-il ? le détecteur verrait-il
un encrassement ? que valent les huit contrôles ? combien l'exploitant reçoit-il
d'alertes par heure de marche ? quelle part du risque AMDEC est couverte ? à qui
partent les escalades ? les deux paramètres arbitraires changent-ils le résultat ?
d'où vient la donnée ? le contrôleur se surveille-t-il ? que ne voit-on pas ? et
le backtest, avec ses sept portes.

Une décision d'affichage y est à défendre, et elle est écrite en capitales dans
le HTML :

> **Le chiffre mis en avant est celui qui se défend.** Un « 100,0 % » en corps 72
> sur un banc dont les pièges ont été **écrits contre les contrôles qui les
> attrapent** est la cible la plus facile d'une soutenance : un contrôle qui ne
> rate jamais rien ne contrôle rien.

La grandeur promue au premier rang est donc l'**écart** entre la note des cas
piégés et celle des cas sains — la mesure de discrimination, qui n'est pas bornée
par construction. Le taux de détection reste publié, en second rang. Et le
premier chiffre du sous-bandeau est celui des **fautes d'un genre non anticipé** :
les pièges conçus mesurent la non-régression, lui seul mesure ce que le contrôleur
attrape sans l'avoir prévu. Ce chiffre était calculé, puis perdu — le panneau
n'affichait que le taux flatteur, et l'aveu restait dans le code.

Le tableau des pièges est trié par **note croissante** : la première ligne est la
faute que le contrôleur sanctionne le moins fermement, donc son point faible.
L'ordre alphabétique précédent plaçait douze « 100 % » les uns sous les autres
sans rien hiérarchiser.

## 17.6 Le câblage serveur → écran, route par route **[MESURÉ]**

La consigne demandait de vérifier « que ce que le serveur sert est rendu, et que
ce que l'écran affiche existe ». Les deux sens ont été mesurés par analyse de
l'AST de `api/main.py` — un `grep` ne conviendrait pas, un décorateur est un
appel et une chaîne citée dans un docstring ressemble à une route.

| | |
|---|---|
| routes déclarées (verbe + chemin) | **47** |
| chemins distincts servis | **46** |
| chemins consommés par `app.js` | **32** |
| chemins appelés par l'écran et **non servis** | **0** |
| chemins servis et **consommés par personne** | **14** |
| taux de câblage | **69,6 %** |

**Aucun appel fantôme.** Le poste ne demande rien que le serveur ne serve : c'est
le sens qui casserait bruyamment, et il est propre.

Les **quatorze chemins orphelins** se répartissent en trois familles, et il faut
les distinguer plutôt que les compter :

| chemin | nature |
|---|---|
| `GET /` | sert la page elle-même — orphelin par construction, pas un défaut |
| `GET /api/health/live` `ready` `model` `database` `version` | **cinq sondes d'orchestrateur** : elles s'adressent à Docker et à la CI, pas au navigateur. §18 les traitera |
| `GET /api/config` · `GET /api/notable` · `GET /api/auth/audit` · `POST /api/auth/refresh` | **quatre routes réellement inertes** |
| `GET/POST /api/workflows` · `GET /api/workflows/{id}` · `POST .../complete` · `PATCH .../steps/{id}` | **le module d'intervention n'a pas d'interface** |

Deux constats à porter au rapport, chacun avec sa portée exacte.

> **Le cycle de vie des interventions n'est pas manipulable depuis le poste.**
> Cinq routes sur six de la famille `workflows` sont servies et jamais appelées ;
> seule `/api/workflows/templates` l'est, pour afficher les gammes en **lecture
> seule**. `src/operations/workflows.py` porte les barrières HSE, le
> versionnement optimiste, l'exigence de signature à la clôture — tout est testé,
> **et rien n'est atteignable à l'écran**. C'est exactement le défaut que le
> commentaire du registre d'alarmes dénonce pour les alarmes, corrigé pour
> celles-ci et **laissé en l'état pour les interventions**.

> **`POST /api/auth/refresh` n'est appelé par personne.** La rotation de jeton
> est implémentée, corrigée (SEC-2 : `rotate()` publie un objet neuf plutôt que
> de muter la session), testée — et le poste ne la déclenche jamais. Une session
> expire donc sur son délai absolu sans que l'écran tente quoi que ce soit. À
> confronter en §22 avec ce que `replay.py` et `auth.py` promettent.

### Identifiants **[MESURÉ]**

| | |
|---|---|
| identifiants posés dans la page | **110** |
| identifiants cherchés par le JS | **99** |
| cherchés et **absents** de la page | **0** |
| posés et jamais cherchés par `$()` | **11** |

Les onze non cherchés ne sont pas morts : neuf sont atteints par sélecteur —
`panel-*` et `tab-*` par `$$(".view-tab")` et `$$(".view")`, `shell`, `who`,
`work` sont des ancres CSS ou de navigation — et deux, `benchReading` et
`friezeTrack`, sont du contenu statique. **Aucun identifiant orphelin réel.** Le
chiffre « 110 / 99 / 0 » de `docs/bibliotheque/partie-audit.md` § 6.6 est confirmé au 8 août 2026.

## 17.7 Les bancs du poste **[MESURÉ, 2026-08-08]**

`npm run test:front` — trois bancs jsdom, sans démarrer le service, sur les
fixtures de `tests/fixtures/api/` :

| banc | vérifications | durée |
|---|---|---|
| `frontend_smoke.mjs` | **54** | 1,94 s |
| `twin_smoke.mjs` | **35** | 0,39 s |
| `boot_smoke.mjs` | **9** | 1,39 s |
| **total** | **98** | **3,7 s** |

**98/98 passées.** Le poste entier est vérifié en moins de quatre secondes, sans
serveur, sans navigateur et sans GPU.

> **Correction d'un chiffre de la partie B elle-même.** La section 23.2 cite
> « **84 vérifications** ne bloquaient rien » comme le défaut d'origine de
> l'invariant *bancs du poste exécutés en CI*. C'était juste au moment de la
> correction ; le décompte est **98** au 8 août 2026. Le premier chiffre décrit
> un état passé et doit rester tel quel ; le second est l'état courant. Les deux
> sont désormais écrits, avec leur date.

Ce que ces bancs couvrent est instructif, parce qu'ils ne testent presque aucune
fonction : ils testent des **propriétés de l'écran**. « Aucun seuil en dur »,
« la gravité n'est pas portée par la seule couleur », « le contraste AA est tenu
sur tous les fonds », « aucun identifiant de code dans le bandeau », « les
réserves du contrôleur sont traduites », « le verdict n'est masqué à aucune
largeur », « aucun champ manquant rendu en clair ». C'est **le patron de § 23.2
appliqué au front** : douze de ces cinquante-quatre vérifications interdisent le
retour d'un défaut par analyse du rendu, jamais par appel de fonction.

`twin_smoke` en porte un cas remarquable — *« le déplacement n'existe qu'en un
exemplaire »* et *« le banc appelle bien la méthode du twin »*. Deux
vérifications dont le seul objet est **d'empêcher le banc de redevenir creux**.
Un banc qui se surveille lui-même est un objet rare, et c'est une contribution
méthodologique à citer à côté du patron.

## 17.8 Ce que les commentaires du front affirment, et qui est faux **[MESURÉ]**

L'amendement A2 de la consigne prédit que le front est « le terrain le plus
fertile du dépôt » : 20 à 22 % de commentaires, que rien n'exécute et qu'aucun
test ne relit. La prédiction est vérifiée. **65 lignes de commentaire portaient
une assertion chiffrée** dans les quatre fichiers du poste à l'ouverture de
l'audit ; elles ont été confrontées une à une.

*(Le script en compte **68** depuis, parce que les trois corrections ci-dessous
citent chacune leur valeur recomptée et sa date. Le dénominateur du taux d'erreur
reste 65 : c'est la population auditée.)*

La grande majorité tient. Trois ne tiennent pas.

### 1. `app.js:1332` — « sépare 57 épisodes sur 59 »

L'artefact en compte **58**. Recomptés sur `tests/fixtures/api/episodes.json` :
58 épisodes, dont **57 valeurs de marge distinctes**. Le numérateur est juste, le
dénominateur est faux d'une unité.

Le chiffre 58 est celui de la partie A, de `docs/bibliotheque/partie-audit.md` § IX et de
`project_metrics.json`. **Quatre sources concordent, le commentaire du front est
seul.** À corriger sur place : « sépare 57 épisodes sur 58 ».

### 2. `dashboard.html:367` — « 849 lignes de code testé, six routes »

Le commentaire justifie l'existence du panneau Registre d'alarmes. Mesuré au
8 août :

| | annoncé | mesuré |
|---|---|---|
| `src/operations/alarms.py` | — | **617** lignes |
| `tests/test_alarm_store.py` | — | **335** lignes |
| total du couple | « 849 » | **952** |
| routes `/api/alarms*` | « six » | **2** |

Ni le volume ni le nombre de routes ne tiennent. Le second écart est le plus
gênant : deux routes, pas six. L'argument du commentaire — *« du code testé et
aucune interface »* — reste vrai et l'était ; ce sont ses chiffres qui ont vieilli
pendant que le code changeait sous eux.

> **Effet de bord utile.** Le recomptage montre au passage que
> `docs/bibliotheque/partie-audit.md` § VI.1 annonce `alarms.py` à **561** lignes et
> `test_alarm_store.py` à **291** — mesurés à **617** et **335**. La consigne B4
> reprend le 561. **Trois documents portent la même valeur périmée**, parce
> qu'ils se sont recopiés. §20 devra partir de la mesure, pas de la consigne.

### 3. ADR-008 — « 4,6:1 minimum » contre 4,54:1 mesuré

Traité en § 17.2. Écart d'un dixième, mais dans le sens flatteur.

### Un point à trancher, pas à corriger d'office

`app.js:1695` se déclare **« dix-neuvième occurrence du motif de cet audit »**.
`docs/bibliotheque/partie-audit.md` § XI et la partie A en recensent **dix-huit**. L'un des deux a
raison et je ne peux pas le déterminer sans reprendre le journal d'audit
intégral (`analyse-architecture.md`, 10 183 lignes), ce qui excède le périmètre
de cette session.

Deux lectures possibles, et elles n'ont pas les mêmes conséquences :

- le commentaire a été écrit **après** le recensement à 18, et il en est
  légitimement la 19ᵉ — auquel cas c'est le **tableau** qui est périmé, et le
  décompte à porter partout est 19 ;
- le commentaire s'est compté lui-même en double, et 18 tient.

**Décision ouverte, référencée `UI-1`.** Elle est de la même famille que les huit
de `docs/bibliotheque/partie-audit.md` § XII, et elle appartient à l'auteur : *on ne choisit pas un
chiffre en fonction de celui qui arrange le récit.*

### Le bilan, qui est le résultat de la section

Sur **65 assertions chiffrées** dans les commentaires du front, **trois sont
fausses et une est indéterminée** — soit un taux d'erreur de 4,6 à 6,2 %. Sur
les vingt et quelques chiffres **exécutés** du même périmètre (constantes de
géométrie, seuils de dégradation, poids, tailles d'étiquette), **aucun** n'est
faux : ils sont vérifiés par 98 assertions de banc.

> **C'est la mesure directe du fil conducteur, faite sur le seul terrain que
> l'audit n'avait pas visité.** Ce qui est exécuté reste juste. Ce qui est
> seulement lu dérive — y compris quand c'est écrit dans le fichier même dont le
> code est juste, à trois lignes de distance.

## 17.9 Les captures d'écran à produire

La consigne en demande au moins quatre. Elles n'existent pas et **ne peuvent pas
être produites dans cette session** : le poste exige un service démarré, donc le
chargement de `DATA.xlsx` et l'entraînement du modèle, puis un navigateur avec
WebGL. La liste, avec ce que chacune doit montrer :

**Attention à la numérotation.** La partie A liste douze figures (§ 14.5) et sa
**figure 12 est déjà « Capture du poste : vue Salle avec le jumeau 3D »**.
Reprendre la vue Salle en F13 la produirait deux fois dans le mémoire fusionné —
exactement la duplication que la consigne interdit. **F12 est donc reprise ici
avec un cahier des charges précis**, et la partie B n'ouvre de nouveaux numéros
qu'à partir de 13.

| # | vue | ce qu'elle doit établir |
|---|---|---|
| **F12** *(précisée)* | Salle, rejeu actif | le jumeau avec une pièce **extraite** et son cartouche, le bandeau de lecture avec ses six tendances, la frise et ses repères d'épisode. C'est la capture que A prévoit ; elle doit montrer l'état éclaté, sans quoi elle ne démontre rien de la chaîne de détection |
| **F13** | Salle, coupe active | chicanes segmentaires et faisceau visibles — la vue qui explique le fonctionnement de l'appareil |
| **F14** | Salle, tiroir capteur ouvert sur `TI5303-4X` | l'étiquette « hors service » et le tiroir citant les bases de détermination du tag |
| **F15** | Intégrité, tableau AMDEC | les trois marqueurs de provenance côte à côte, légende comprise |
| **F16** | Contrôle, banc de pièges | l'écart de discrimination au premier rang, le taux de détection au second |
| **F17** | Contrôle, auto-surveillance | le seul dispositif du projet qui se retourne contre lui-même |

## 17.10 Ce que la section 17 ne permet pas d'affirmer

- que le poste a été **essayé par un exploitant** — il n'a jamais quitté le poste
  de développement ; aucune mesure d'usage, aucun retour terrain ;
- que la conformité ISA-101 est **certifiée** — elle est revendiquée par ADR-008,
  vérifiée point par point par 54 assertions de banc, et jamais auditée par un
  tiers ;
- que les **latences** annoncées tiennent en exploitation — les bancs tournent
  sur fixtures, sans service ; la mesure de latence des routes appartient à §18 ;
- que le **jumeau 3D est une représentation cotée** — deux nombres de la fiche
  équipement, aucun plan constructeur au dossier, et le poste l'écrit sous la
  scène ;
- que le module d'**interventions** est utilisable — il est servi, testé, et sans
  interface (§ 17.6).

---

# 18. Le contrat d'API

`api/main.py`, **1 830 lignes**, **47 routes**. C'est la couche que le jury ne
verra pas et sur laquelle tout repose : le poste de §17 n'affiche rien qu'elle
ne serve.

Tous les chiffres de cette section viennent de
`scripts/collecte_chiffres_api.py` → `reports/chiffres_api.txt`, par analyse de
l'arbre syntaxique. Un `grep` ne conviendrait pas : un décorateur est un appel,
et une chaîne citée dans un docstring ressemble à une route.

## 18.1 Les familles **[MESURÉ, 2026-08-08]**

| famille | routes | ce qu'elle porte |
|---|---|---|
| **Donnees** | 5 | séries temporelles, topologie, fiche capteur, santé instrumentation, épisodes |
| **Temps reel** | 7 | pilotage et lecture du rejeu |
| **Maintenance** | 5 | modèles d'intervention et cycle de vie |
| **Acces** | 5 | session, CSRF, rotation, journal d'authentification |
| **Sante** | 5 | sondes d'orchestrateur |
| **Systeme** | 4 | synthèse de santé, gouvernance, configuration, fiche équipement |
| **Gouvernance** | 3 | sensibilité, couverture du risque, validation du modèle |
| **Notifications** | 3 | état du canal, test, synthèse |
| **Alarmes** | 2 | registre et transitions |
| **Judge** | 2 | auto-surveillance et banc de pièges |
| **Analyse** | 2 | analyse d'un instant, instants notables |
| *(sans étiquette)* | 1 | `GET /` — le tableau de bord lui-même |

**46 chemins distincts, 47 couples verbe+chemin** — seul `/api/workflows` porte
deux verbes.

## 18.2 La règle de déclaration des handlers **[LU + MESURÉ]**

C'est le point le plus instructif de ce fichier, et il ne se voit pas à
l'exécution d'une requête isolée.

> **Un handler est `async def` uniquement s'il `await`, ou si son corps se
> limite à des lectures en mémoire. Tout ce qui calcule est déclaré `def` —
> FastAPI l'exécute alors dans son pool de threads.**

Le défaut d'origine : **32 des 47 handlers** étaient `async def` sans le moindre
`await`. Leur corps entier s'exécutait sur la boucle d'événements, qui est
unique. Trois conséquences, par gravité croissante :

- `auth_login` dérive un PBKDF2 à **600 000 itérations**, volontairement coûteux.
  Chaque tentative de connexion, réussie ou non, gelait tout le service ;
- `analyze` appelle le modèle de langage, appel synchrone et sans délai maximal.
  Une réponse lente figeait la supervision **sonde de vivacité comprise** — et
  l'orchestrateur finissait par tuer un conteneur en parfait état ;
- `notable` enchaîne jusqu'à cent analyses complètes ; `timeseries`,
  `operational_kpi` et `episodes` balayent tout l'historique.

**État au 8 août 2026** :

| | |
|---|---|
| handlers `async def` | 29 |
| handlers `def` | 18 |
| `async def` sans aucun `await` | 17 |
| dont déclarés **calculants** | **0** |
| dont hors de la liste tolérée | **0** |

Les 17 `async def` sans `await` sont des **sondes et des lectures de
dictionnaire**, explicitement tolérées : elles doivent répondre même si le pool
de threads est saturé. C'est le bon compromis, et il est déclaré plutôt que subi.

> **Note de méthode, et elle a coûté une correction.** La première version du
> script de mesure employait une heuristique maison — « calcule » tout handler
> citant `_replay()` ou `_notifier()`. Elle désignait **neuf routes fautives**,
> dont `replay_state`, qui ne fait que lire un dictionnaire.
>
> `tests/test_service_invariants.py` porte la liste qui fait autorité,
> `HANDLERS_CALCULANTS`, établie à la main lors de la correction. Le script la
> **lit** désormais. C'est la convention n° 1 du dépôt — *ne réimplémente pas
> pour mesurer, importe le prédicat réel* — et l'avoir enfreinte a produit neuf
> accusations fausses en une seule exécution.

## 18.3 Le flux d'authentification **[LU]**

Cinq routes, et un middleware qui les précède toutes.

```
  GET  /api/auth/status    → { required, authenticated, operator }
  POST /api/auth/login     → cookie HttpOnly + jeton CSRF dans le corps
  POST /api/auth/refresh   → rotation du cookie ET du jeton CSRF
  POST /api/auth/logout    → destruction de session, cookie supprimé
  GET  /api/auth/audit     → journal, réservé au rôle administrator
```

**Le cookie.** `e7301_session`, `HttpOnly`, `SameSite=strict`, `Secure` piloté
par configuration, `max_age` égal à l'expiration absolue. Le jeton de session ne
transite jamais par le JavaScript ; le jeton **CSRF**, lui, est rendu dans le
corps de la réponse et renvoyé par l'écran dans l'en-tête `X-CSRF-Token`.

**Le middleware `operator_access`** fait quatre choses dans cet ordre :

1. il attribue un `X-Request-ID` — repris de l'appelant s'il en fournit un, sinon
   tiré au sort — qui servira à corréler toute trace serveur ;
2. il laisse passer sans session les chemins **publics** : `/`, `/assets/*`,
   `/api/health`, `/api/health/*` et `/api/auth/*` ;
3. il refuse en **401** toute autre route sans session valide ;
4. il refuse en **403** toute mutation dont l'en-tête `X-CSRF-Token` ne
   correspond pas au jeton de session — sauf `login` et `logout`, qui ne peuvent
   pas en porter.

Puis il journalise chaque mutation : verbe, chemin, acteur, rôle, identifiant de
requête.

**Les rôles.** Dix routes sur 47 exigent un rôle, résolu **côté serveur** :

| rôles admis | routes |
|---|---|
| `maintenance`, `reliability_engineer`, `administrator` | les 4 routes `workflows` en écriture, les 2 routes `notifications` en envoi |
| + `operator` | les 3 routes de pilotage du rejeu |
| `reliability_engineer`, `administrator` | `GET /api/judge/evaluation` |
| `administrator` seul | `GET /api/auth/audit` |

`POST /api/alarms/{id}/transition` n'appelle pas `_require_roles` mais porte sa
**propre table par action** : acquitter est ouvert à `operator`, tandis
qu'inhiber, désinhiber et clôturer exigent au minimum `maintenance`. C'est plus
fin que le garde générique, et c'est justifié — l'acquittement est un geste de
quart, l'inhibition est une décision de maintenance.

Restent **quatre mutations sans exigence de rôle** : les trois routes
d'authentification, qui ne peuvent pas en avoir, et `POST /api/analyze`, qui est
une lecture déguisée en POST — elle ne modifie rien, le verbe ne tient qu'au
corps de requête.

**Les en-têtes de défense.** `_durcir()` en pose **huit**, et c'est le seul
endroit du fichier où un en-tête de sécurité est écrit : politique de sécurité du
contenu, `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
`Permissions-Policy`, `Cache-Control` (`no-store` sur `/api/`), l'identifiant de
requête, et `Strict-Transport-Security` **uniquement en HTTPS** — le promettre
sur du HTTP local serait trompeur.

> Le défaut corrigé mérite d'être cité : les refus **401, 403 et 500 partaient
> sans aucun en-tête**. Le middleware retournait directement la réponse d'erreur,
> sautant le bloc placé après `call_next` ; et le gestionnaire d'exception
> s'exécute *en dehors* des middlewares applicatifs. Ce sont précisément les
> réponses qu'un attaquant provoque le plus facilement, et les seules qu'un
> exploitant ne pouvait pas corréler à une trace serveur.

## 18.4 Le flux de rejeu **[LU]**

Sept routes, dont quatre en lecture.

| route | rôle |
|---|---|
| `POST /api/replay/start` | arrête le rejeu courant s'il tourne, en **reconstruit** un neuf, l'abonne, le démarre |
| `POST /api/replay/stop` | arrête |
| `POST /api/replay/speed` | change la vitesse à chaud — **paramètre d'URL, pas corps JSON** |
| `GET /api/replay/state` | instantané : curseur, nombre d'instants analysés, marche/arrêt |
| `GET /api/replay/stream` | les *n* dernières analyses, compactées |
| `GET /api/replay/alerts` | les *n* dernières alertes |
| `GET /api/replay/disagreements` | les décisions **rejetées par le contrôleur** |

Deux points de conception à retenir.

**Le rejeu est reconstruit, jamais reconfiguré.** `_build_replay()` est le seul
constructeur, et il **abonne systématiquement** le canal e-mail et le registre
d'alarmes. Un rejeu ne peut donc pas exister sans ses deux consommateurs : une
route qui construirait un `DCSReplay` directement perdrait silencieusement
l'escalade et la persistance des alarmes.

**`/api/replay/disagreements` est la route de gouvernance.** Son docstring le dit
sans détour : *« c'est la vue la plus importante du point de vue gouvernance :
elle montre où le système s'est contrôlé lui-même »*. Elle est servie, consommée
par le filtre « Rejets » du journal, et c'est la seule route dont l'objet est
d'exposer les échecs du système.

Le défaut du réglage de vitesse est raconté en § 17 côté écran ; côté serveur, la
signature `speed: float = Query(..., gt=0, le=100000)` déclare un paramètre de
requête **obligatoire**. Le poste l'envoyait dans le corps, FastAPI répondait
**422**, et l'erreur était avalée par un `.catch()` muet. `test_api.py` appelait
`?speed=500`, c'est-à-dire le contrat réel : *le test passait pendant que le
poste échouait, chaque côté cohérent avec lui-même, et les deux ne se parlaient
pas.*

## 18.5 Les six sondes de santé **[LU + MESURÉ]**

| route | à qui elle s'adresse |
|---|---|
| `GET /api/health` | **synthèse humaine** — la seule que le poste appelle |
| `GET /api/health/live` | *liveness* — le processus HTTP répond, sans prétendre que ses dépendances sont prêtes |
| `GET /api/health/ready` | *readiness* — **503** tant que la chaîne ou l'un des deux registres manque |
| `GET /api/health/model` | promotion du modèle, **distincte** de sa disponibilité d'exécution |
| `GET /api/health/database` | **lecture réelle** des deux bases SQLite, 503 + motif nommé |
| `GET /api/health/version` | versions applicative, source du modèle, signature d'exécution, version des règles |

Deux de ces sondes portent une leçon.

**`/api/health` répond `degraded` en permanence, et c'est voulu.** Le statut passe
à `degraded` dès que le modèle n'est pas promu — or la promotion est
**légitimement impossible** sur ce corpus : `labels_gmao` et `validation_externe`
échouent faute d'historique de pannes étiqueté, et aucun commit ne les
franchira.

> La tentation était de ramener `status` à l'état du **service** et de renvoyer
> la gouvernance à `ready_for_production`. Elle a été écartée, et le raisonnement
> est le même que pour les portes de déploiement : *restreindre un critère « pour
> qu'il puisse passer » remasque ce que l'auteur avait délibérément rendu
> visible.* Ce qui manquait n'était pas la nuance, c'était sa **raison** — d'où
> le champ `status_reason`, qui distingue « dégradé par un défaut réparable » de
> « dégradé par une limite définitive du corpus ».

**`/api/health/database` vérifiait et ne décidait de rien.** Le verdict était figé
*avant* la lecture — `store is not None` — donc il mesurait la construction de
l'objet au démarrage, jamais l'état de la base. La lecture était bien exécutée,
et son résultat jeté. Pire : quand elle échouait — fichier verrouillé, base
corrompue, disque plein, c'est-à-dire les seules pannes qu'une sonde de base
existe pour voir — l'exception remontait au gestionnaire générique et la route
répondait **500**. Une sonde qui répond 500 au lieu d'« indisponible » se confond
avec un bogue applicatif et n'apprend rien à un orchestrateur.

## 18.6 Les bornes, et ce qu'elles empêchent **[MESURÉ]**

**19 paramètres de requête sont bornés.** Aucun paramètre de pagination ou de
fenêtre n'est libre :

| paramètre | plage | pourquoi |
|---|---|---|
| `limit` (alarmes, épisodes, workflows, audit) | 1 → 500 | une liste non bornée est un déni de service offert |
| `n` (flux, alertes) | 1 → 500 | idem |
| `max_points` (timeseries) | 100 → 20 000 | le rendu s'effondre au-delà |
| `window_h` (capteur) | 6 → 20 000 | 20 000 h > le corpus entier : la borne est large mais existe |
| `n_cases` (banc du Judge) | 2 → 30 | chaque cas est une analyse complète |
| `duration_days` (banc d'encrassement) | 14 → 180 | une rampe plus courte ne mesure rien |
| `speed` (rejeu) | ]0 ; 100 000] | obligatoire, sans défaut |

Sept **modèles Pydantic** valident les corps de requête, tous avec des bornes
explicites — et trois avec un motif fermé : `AlarmTransitionRequest.action`,
`WorkflowCreateRequest.template_id`, `WorkflowStepRequest.status`. Un état
d'étape inconnu est refusé **avant** d'atteindre le magasin SQLite.

Le contrôle de plage du banc d'encrassement mérite d'être cité, parce qu'il
protège un **résultat** et non un service :

> Une sévérité est une **fraction** de perte de UA. Laisser passer 1, 2 ou 3
> produirait des scénarios où l'échangeur n'échange plus rien, détectés par
> construction : *le banc afficherait 100 % sans rien démontrer.*

## 18.7 Routes et champs orphelins **[MESURÉ]**

C'est la vérification que la consigne demande explicitement, dans les deux sens.

### Routes servies et consommées par personne — 14

Reprises de § 17.6, avec leur nature :

| nature | nombre | verdict |
|---|---|---|
| `GET /` | 1 | sert la page — orphelin par construction |
| sondes d'orchestrateur `/api/health/*` | 5 | **normal** — elles s'adressent à Docker et à la CI |
| famille `workflows` | 5 | **le module n'a pas d'interface** |
| `GET /api/config`, `GET /api/notable`, `GET /api/auth/audit`, `POST /api/auth/refresh` | 4 | réellement inertes |

**Aucun appel fantôme dans l'autre sens** : le poste ne demande rien que le
serveur ne serve.

### Champs servis que l'écran ne lit jamais — 35 sur 79

Le décompte porte sur les clés de premier niveau des dictionnaires littéraux
retournés par les handlers.

> **Portée exacte de ce constat, et elle est étroite.** Un champ non lu par le
> poste n'est pas mort : il peut servir à un orchestrateur, à un test, ou à un
> lecteur de la documentation OpenAPI. Le contrôle dit ce qu'il mesure — *ce que
> l'écran ignore* — et rien de plus. Vingt-quatre des trente-cinq sont
> légitimes : ce sont les champs des cinq sondes de santé et les accusés de
> réception `accepted`.

Restent **onze champs de routes métier**, et trois sont des trouvailles :

| route | champ | constat |
|---|---|---|
| `/api/health` | **`status_reason`** | ajouté précisément pour qu'un jury lise *pourquoi* le service est `degraded` — **l'écran ne le lit pas** |
| `/api/equipment` | **`process_states`** | les trois définitions `RUNNING` / `TRANSIENT` / `STOPPED` |
| `/api/equipment` | `baremes` | les trois barèmes GRV / OCC / DET |
| `/api/equipment` | `partially_observable` | la liste des modes en observabilité partielle |
| `/api/equipment` | `tag_registry_change_history` | l'historique des changements du référentiel |
| `/api/sensor/{alias}` | `criticality_link` | seul `criticality_link_label` est lu |
| `/api/sensor/{alias}` | `kind` | nature du tag |
| `/api/kpi` | `stabilite_regulation` | série calculée, jamais tracée |
| `/api/judge/evaluation` | `report` | le rapport textuel du banc |

**`process_states` est le cas exemplaire, et il est cité par le serveur
lui-même.** Le commentaire d'`api/main.py` explique pourquoi le champ a été
ajouté :

> *« La classification STOPPED / TRANSIENT / RUNNING est la décision la plus
> déterminante du système — c'est elle qui décide quelles heures sont jugeables —
> et un exploitant qui voit "ligne à l'arrêt" sur son écran n'avait aucun moyen
> de savoir quel critère l'avait déclenché. »*

Le serveur a été corrigé. **L'écran ne l'a jamais été.** L'exploitant lit
toujours « À l'arrêt » sans pouvoir savoir quel critère l'a produit, alors que la
réponse voyage déjà jusqu'à son navigateur à chaque chargement de page.

> **Vingtième occurrence du motif de cet audit**, et dans le sens habituel : le
> code de service porte la version juste, l'affichage la version périmée. Elle
> se distingue des précédentes sur un point — ici l'affichage ne porte pas une
> valeur *fausse*, il porte une **absence**. Un champ servi et jamais rendu ne
> déclenche aucun test, ne produit aucune contradiction visible, et ne se voit
> qu'en confrontant les deux côtés. C'est le seul défaut de cette famille qu'un
> banc de rendu ne peut pas attraper.
>
> *(Le rang « vingtième » dépend de la résolution de **UI-1**, § 17.8 : le front
> se déclare dix-neuvième occurrence, les tableaux en recensent dix-huit. Le
> compte relatif est sûr, sa base ne l'est pas.)*

## 18.8 Ce que la section 18 ne permet pas d'affirmer

- que les **latences** tiennent en exploitation — aucune n'a été mesurée : le
  service exige le chargement de `DATA.xlsx` et l'entraînement du modèle au
  démarrage, hors de portée de cette session. C'est le premier chiffre à
  produire pour compléter ce chapitre ;
- que les **35 champs non lus** sont morts — le contrôle ne mesure que ce que
  l'écran ignore, et vingt-quatre d'entre eux servent légitimement ailleurs ;
- que le **contrôle d'accès a été éprouvé** — il est lu, testé par
  `test_api.py` et `test_access_notifications.py`, et jamais soumis à un test
  d'intrusion ;
- que `POST /api/analyze` **devrait** exiger un rôle — c'est une lecture, et
  trancher appartient à l'auteur.

---

# 19. La validation du modèle

`src/governance/model_validation.py`, **834 lignes**. La partie A dispose des
**résultats** (§ 15.8) et ignore **comment ils sont construits**. C'est l'objet de
ce chapitre.

Chiffres relus dans `reports/model_validation.json`, l'artefact que produit
`make test` — jamais dans un commentaire.

## 19.1 Le plan d'expérience **[LU]**

```
validate_unsupervised_detector(
    features, readings, quality, domain, references,
    contamination, random_state,
    n_splits = 4,        # quatre plis
    gap_hours = 24,      # écart causal
)
```

**Pourquoi une fenêtre croissante et non des blocs disjoints.** `TimeSeriesSplit`
produit un apprentissage strictement antérieur au test, et **grandissant** : le
pli 1 apprend sur 1 055 heures, le pli 4 sur 6 551. C'est le seul découpage qui
reproduise la situation réelle d'exploitation — à chaque instant, le système ne
dispose que de son passé. Un découpage par blocs disjoints, ou pire une
validation croisée aléatoire, entraînerait le modèle sur des heures postérieures
à celles qu'il score : une fuite temporelle qui gonfle toute métrique.

**Pourquoi quatre plis.** Contrainte du corpus, pas choix méthodologique. Chaque
fenêtre de test compte environ 1 800 heures ; en exiger davantage réduirait
l'apprentissage du premier pli sous le seuil d'utilisabilité, et le code refuse
explicitement un pli trop maigre — `train < 100` ou `test < 50` lève une
`ValueError` plutôt que de produire un chiffre creux.

**Pourquoi un écart causal, et pourquoi 25 h et non 24.** Le paramètre vaut
`gap_hours = 24`. Le gap **mesuré** vaut **25,0 h** sur les quatre plis, et
l'écart d'une heure n'est pas une erreur : `TimeSeriesSplit` laisse 24 pas
d'index entre la dernière heure d'apprentissage et la première de test, ce qui
fait 25 heures d'horloge entre les deux bornes incluses.

Ce détail est publié parce que le champ a changé de nature :

> **Le gap publié était le paramètre reçu, pas celui obtenu** — un champ qui
> affirme au lieu de constater. Il est désormais recalculé
> (`gap_mesure = (test_start − train_end) / 1h`) et c'est cette valeur que le
> rapport porte.

Ce que l'écart protège : les features portent des tendances glissantes sur 14
jours et des références ajustées. Sans lui, la dernière heure d'apprentissage et
la première de test partageraient des fenêtres de calcul — l'apprentissage
verrait le test par la bande.

**Ce qui est réajusté à chaque pli.** Cinq objets, et le manifeste les nomme :
`thermal_reference`, `causal_features`, `scaler`, `isolation_forest`,
`threshold`. Les **trois références** — conductance, effort de régulation, entrée
acide — sont réajustées sur le seul passé du pli. C'est indispensable : la
référence d'entrée acide apprend `T_in` en fonction de la charge et du débit ; si
elle voyait le corpus entier, elle aurait déjà vu l'été que le pli 1 est censé
découvrir.

## 19.2 `causal_pipeline_refit` — le champ qui était un littéral **[LU]**

Le champ portait la valeur `True`, écrite en dur.

> Exactement le défaut que le commentaire des portes dénonce vingt lignes plus
> bas à propos de `causalite_temporelle` — *« aucune mesure, aucune possibilité
> d'échec »* — reproduit un cran plus bas, dans le détail des plis. Et le test
> l'affirmait : `assert all(fold["causal_pipeline_refit"] ...)`, **c'est-à-dire
> un test qui vérifiait une constante.**

Ce que le nom promet est désormais **mesuré**, sur les trois choses qui peuvent
le démentir :

```python
refit_causal = (
    fin_references <= train_end     # les 3 références s'arrêtent au passé
    and fin_detecteur <= train_end  # l'Isolation Forest aussi
    and gap_mesure >= gap_hours     # l'écart est réellement tenu
)
```

Et — c'est le point qui manquait — **un pli en défaut remonte jusqu'à la porte**.
Les manquements sont collectés dans `fuites_de_pli` et injectés dans
`_causality_audit` : auparavant, une fuite dans un pli laissait
`causalite_temporelle` afficher « franchie ».

## 19.3 L'audit de causalité — trois niveaux **[LU]**

La porte `causalite_temporelle` était, elle aussi, un littéral `True`. Elle est
maintenant établie par trois contrôles de natures différentes, et c'est leur
empilement qui fait la solidité.

### Niveau 1 — reconstruction réelle sur histoire tronquée

Le contrôle affirmait reconstruire et ne le faisait pas :

```python
tronque = features.loc[:coupe, colonnes]
complet = features.loc[:coupe, colonnes]   # la MÊME expression
```

Deux fois la même expression, puis `complet` supprimé sans jamais être comparé.
La seule vérification effective était qu'une ligne n'était pas entièrement vide.

La chaîne est désormais **réellement reconstruite** sur l'histoire tronquée, à
trois coupes (40, 60, 80 % du corpus), **références figées** pour que la
comparaison porte sur le calcul des grandeurs et non sur un réajustement
légitime. L'état de marche — là où vivait le `shift(-1)` historique — est
reclassé et comparé séparément.

Le principe tient en une phrase : *une chaîne causale doit produire, à l'instant
t, exactement la même valeur qu'elle produirait si les données s'arrêtaient à t.*

### Niveau 2 — inspection statique du source, littéraux blanchis

`_decalages_non_causaux()` cherche dans **tout `src/`** les motifs qui trahissent
une lecture de l'aval : `shift(-n)`, `center=True`, `.bfill(`, `backfill`,
`method="b"`, `.transform("sum")`.

L'histoire de son périmètre est un cas d'école :

> Le balayage portait `if "governance" not in chemin.parts`, **sans un mot de
> justification**, sous un commentaire annonçant au contraire que « le périmètre
> couvre toute la chaîne, pas trois fichiers ». La raison réelle était mécanique
> et personne ne l'avait écrite : le motif contient l'alternative `backfill`,
> donc **la ligne de source qui porte le motif contient le mot `backfill`**. Le
> balayage se signalait lui-même.

Blanchir chaînes et commentaires **par tokenisation** — `_code_sans_litteraux()`,
qui préserve la numérotation des lignes — fait disparaître les faux positifs sans
rien exclure. L'exclusion coûtait cher : `sensitivity.py`,
`fouling_injection.py` et `judge_eval.py` produisent des chiffres publiés dans le
rapport, et un `shift(-1)` introduit dans l'un d'eux n'aurait rien déclenché.

Détail à retenir : **un module illisible est déclaré suspect, jamais ignoré.** Un
contrôle de causalité qui échoue en silence vaut moins que pas de contrôle.

### Niveau 3 — agrégation des fuites de pli

Les manquements relevés pli par pli (§ 19.2) remontent dans le même verdict.

**Résultat au dernier artefact : porte franchie.** Aucun décalage négatif ni
fenêtre centrée dans le code exécutable de `src`, gouvernance comprise ; chaîne
reconstruite et vérifiée sur les trois troncatures.

## 19.4 Le PSI — comment il est calculé, et ce qu'il mesure vraiment

C'est le passage le plus important du chapitre.

### Le calcul **[LU]**

`_population_stability_index(reference, observed)` découpe les scores
d'apprentissage en **déciles**, y range les scores de test, et somme
`(obs_p − ref_p) · ln(obs_p / ref_p)`.

**La correction d'epsilon, et pourquoi ce n'était pas un lissage.** La version
précédente écrasait les deux distributions à `1e-6`, sous le mot « lissage ». Sur
des déciles de référence — donc `ref_p = 0,1` par construction — une seule
cellule **vide** côté observé contribue alors :

```
(1e-6 − 0,1) × ln(1e-6 / 0,1) = 1,1513
```

soit, à elle seule, **plus de quatre fois la borne de 0,25** opposée au total.

> Le PSI publié comptait donc, pour l'essentiel, des **cellules vides multipliées
> par une constante arbitraire**. Et `1e-6` n'est même pas une fréquence
> atteignable : sur ~1 800 heures de test, la plus petite fréquence non nulle
> vaut 5,6 × 10⁻⁴.

Le plancher est désormais `0,5 / n` — la **correction de continuité usuelle**,
donc rattachée à la taille de l'échantillon au lieu d'être posée. Même cellule
vide, même corpus : **0,589 au lieu de 1,1513**.

La fonction rend en outre le **nombre de déciles vides**, parce que sans lui la
valeur n'est pas interprétable : *un PSI de 3,7 peut signifier une distribution
déplacée ou trois déciles jamais visités, et ce n'est pas le même constat.*

### Les valeurs mesurées **[MESURÉ, `reports/model_validation.json`]**

| pli | n train | n test | gap | seuil | alertes | **PSI** | déciles vides | **extrapolation** |
|---|---|---|---|---|---|---|---|---|
| 1 | 1 055 | 1 786 | 25,0 h | 0,9661 | 16,1 % | **1,988** | 0 | **76,5 %** |
| 2 | 2 841 | 1 837 | 25,0 h | 0,9656 | 4,4 % | **3,183** | **1** | **100,0 %** |
| 3 | 4 702 | 1 873 | 25,0 h | 0,9647 | 7,3 % | **0,580** | 0 | **5,2 %** |
| 4 | 6 551 | 1 908 | 25,0 h | 0,9653 | 3,5 % | **0,068** | 0 | **12,8 %** |

> **Ces valeurs corrigent le tableau des chiffres de `partie-audit.md` § IX**, qui
> portait les valeurs **d'avant** la correction d'epsilon — « 1,989 / 3,745 » — et
> une couverture hors plage « 73,8 / 100 / 5,9 / 0 % » que son propre § 5.3
> dément deux lignes plus bas en annonçant 12,8 % sur le pli 4. Un document qui se
> contredit à deux lignes d'écart, dans le tableau écrit pour faire autorité.
> Corrigé à chaque occurrence le 8 août 2026.

### Ce que le PSI mesure — et ce qu'il ne mesure pas **[MESURÉ]**

La correspondance entre extrapolation saisonnière et PSI est **monotone et sans
exception** : plus la fenêtre de test sort de la plage d'eau de mer vue à
l'apprentissage, plus le PSI monte. Le maximum tombe sur le pli **entièrement**
hors plage, le minimum sur le pli qui extrapole le moins.

**Ce que cela réfute.** La preuve affichée attribuait ce chiffre à « deux
excursions de sur-refroidissement » entre les deux moitiés de la période. Les
plis 3 et 4 testent les périodes **les plus tardives**, donc les plus éloignées de
la référence : cette explication prédit qu'ils dérivent le plus. **Ils dérivent le
moins, d'un facteur 47.** Une affirmation juste par ailleurs, écrite à côté de
chiffres qui la démentent.

**Ce que cela établit.**

> Le PSI élevé des premiers plis mesure **l'année incomplète de la fenêtre
> d'apprentissage**. Un backtest à fenêtre croissante sur quatorze mois ne peut
> pas avoir vu un cycle entier d'eau de mer avant son dernier pli. C'est une
> propriété du **plan d'expérience**, pas du modèle — aucun commit ne la
> déplacera, et aucun seuil, de quelque domaine qu'il vienne, n'est interprétable
> sur un pli qui extrapole.

`seasonal_extrapolation` est la mesure qui l'établit :

```python
mer_train = seawater_temperature(train.index)
mer_test  = seawater_temperature(test.index)
hors_plage = ((mer_test < mer_train.min()) | (mer_test > mer_train.max())).mean()
```

Elle compare les **heures de marche réellement présentes** dans chaque fenêtre,
via `train.index` et `test.index`. C'est ce qui explique le 12,8 % du pli 4, là où
un calcul sur calendrier continu donnerait 0 % : les heures d'arrêt ne sont pas
dans l'index, et leur absence décale la couverture.

**Conséquence sur la porte** : `plis_couverts` ne retient que les plis à
extrapolation nulle. Au dernier artefact, **`n_seasonally_covered_folds = 0`** et
`max_score_psi_seasonally_covered = None`. La porte échoue faute de pli
interprétable, pas faute de stabilité.

> **Troisième occurrence du même motif dans ce dépôt** : un dénominateur qui
> contient des essais où rien ne pouvait être mesuré. `judge_eval` comptait des
> mutations qui ne mutaient rien (S6-2), `fouling_injection` des fenêtres calmes
> parce que la ligne était à l'arrêt (S7-1), et ce banc-ci des plis qui
> extrapolent. **Le critère n'a pas été assoupli pour produire un pli qualifié :
> on ne choisit pas un critère en fonction du verdict qu'il produit.**

## 19.5 Les sept portes — ce que chacune calcule, et d'où vient son seuil

C'est la demande explicite de la consigne : la partie A signale que le 0,25 du
PSI vient du scoring de crédit ; voici l'origine de chacun des autres.

| porte | prédicat | seuil | **origine du seuil** | verdict |
|---|---|---|---|---|
| `causalite_temporelle` | aucun écart sur 3 troncatures, aucun motif non causal, aucune fuite de pli | **aucun seuil** — binaire | propriété logique, rien à calibrer | **franchie** |
| `redondance_features` | 0 paire à \|r\| ≥ 0,90 dans la matrice du modèle, conditionnement calculable | **0,90** | seuil usuel de colinéarité en régression ; au-delà, l'inversion devient instable | **franchie** |
| `redondance_hors_modele` | aucune grandeur du modèle à \|r\| ≥ 0,80 avec une variable régulée hors modèle | **0,80** | seuil retenu par le projet, verrouillé par `test_effort_de_regulation_est_redondant_et_le_declare` | **échec permanent** |
| `stabilite_hors_periode` | taux d'alertes moyen ≤ limite | **max(0,15 ; 5 × contamination)** | **dérivé du réglage**, pas importé : cinq fois la contamination visée, plancher à 15 % | **franchie** — 7,8 % pour 15 % admis |
| `derive_de_distribution` | PSI max sur plis couverts ≤ limite | **0,25** | **scoring de crédit**, où les populations comparées sont supposées échangeables. Transfert non argumenté | **échec** — 0 pli mesurable |
| `labels_gmao` | existence d'une vérité terrain | **aucun** | — | **échec définitif** |
| `validation_externe` | existence d'une annotation indépendante | **aucun** | — | **échec définitif** |

**3 / 7 franchies**, et c'est ce que le poste affiche.

### Le seul seuil vraiment arbitraire, et le seul qui soit dérivé

Deux entrées de ce tableau méritent d'être opposées.

**`derive_de_distribution` — 0,25, importé.** Le seuil vient du *Population
Stability Index* tel qu'il est employé en scoring de crédit, où les deux
populations comparées sont censées être échangeables. **Le dossier n'argumente
nulle part son transfert à des scores d'Isolation Forest**, et la preuve de la
porte le dit à l'écran, en toutes lettres. C'est la seule constante du fichier
qui vienne d'un autre domaine.

Elle est nommée **une seule fois**, `PSI_LIMIT = 0.25`, et le commentaire explique
pourquoi :

> La version précédente l'écrivait **deux fois** — dans le prédicat de la porte
> et dans la preuve affichée — à onze lignes d'écart. C'est le défaut de S8-2,
> commis dans le fichier qui porte le principe.

**`stabilite_hors_periode` — dérivé du réglage.**
`alert_rate_limit = max(0.15, contamination * 5)` ne vient d'aucune littérature :
il se déduit du paramètre que l'exploitant règle. Changer la contamination déplace
la limite, ce qui est le comportement voulu — la porte demande « le détecteur
reste-t-il cohérent avec sa propre calibration », pas « le taux est-il bon dans
l'absolu ».

### Deux natures de portes, et les confondre rendait la chaîne rouge à jamais

| ensemble | portes | ce qu'il conditionne |
|---|---|---|
| `MANDATORY_GATES` | **5** — causalité, redondance features, stabilité, labels GMAO, validation externe | la **promotion** d'un artefact |
| `SOFTWARE_GATES` | **3** — causalité, redondance features, stabilité | ce que la **CI** peut bloquer |

La différence est le cœur de la gouvernance du projet. `labels_gmao` et
`validation_externe` échouent définitivement, faute de données OCP : les inclure
dans ce que la CI bloque aurait rendu toute fusion impossible pour une raison
qu'aucun développeur ne peut lever.

Et deux portes sont **publiées, en échec, et délibérément non bloquantes** :

- **`redondance_hors_modele`** — le résidu d'effort *est* l'écart de consigne
  (ADR-001, r = −0,938). C'est une propriété **algébrique permanente** : aucun
  commit ne peut la franchir. On ne masque pas la redondance pour autant — c'était
  le défaut d'origine, et publier « 0 paire redondante » deux cents lignes
  au-dessus d'un −0,938 mesuré était malhonnête ;
- **`derive_de_distribution`** — aucun pli saisonnièrement couvert. Elle
  **n'est pas** algébriquement impossible : un modèle autrement conçu, ou un
  corpus de deux ans, déplacerait ce chiffre. Elle sort du blocage faute de seuil
  justifié et faute de plis interprétables, **pas faute de sens**.

Distinguer ces deux échecs est ce qui sépare une limite déclarée d'un aveu de
défaite. Verrouillé par
`test_une_porte_publiee_non_bloquante_n_empeche_pas_la_promotion`.

## 19.6 L'audit de redondance — le contrôle qui se validait lui-même **[LU]**

`_feature_audit()` calculait la colinéarité sur la seule matrice du modèle, d'où
`control_deviation` est **absente**. Il concluait donc « 0 paire redondante » en
ayant justement écarté la variable qui révèle la redondance.

L'audit porte désormais sur deux questions séparées, et le fait de les **séparer**
est ce qui l'a corrigé :

| question | prédicat | seuil |
|---|---|---|
| colinéarité **interne** au modèle | paires de features | \|r\| ≥ 0,90 |
| redondance avec une variable **régulée hors modèle** | features × `control_deviation`, `delta_t`, `duty_kw`, `T_ACID_OUT`, en marche établie | \|r\| ≥ 0,80 |

La seconde est celle qui expose ADR-001. Chaque paire trouvée porte sa lecture en
clair : *« cette grandeur est une réécriture de la variable régulée : elle ne
constitue pas une preuve indépendante »*.

Au dernier artefact : **11 features**, conditionnement calculable, **0 paire
interne redondante**, et la redondance hors modèle qui fait échouer sa porte.

## 19.7 Ce que la section 19 ne permet pas d'affirmer

- que le backtest mesure une **performance de détection** — il mesure stabilité et
  charge d'alerte. Le rapport le déclare : *« aucune AUC, précision, rappel ou
  réduction de panne revendiquée »* ;
- que le **PSI actuel dit quoi que ce soit du procédé** — sur zéro pli
  saisonnièrement couvert, il ne mesure rien d'interprétable ;
- que le seuil de **0,25 soit valide ici** — son transfert depuis le scoring de
  crédit n'est pas argumenté, et le dépôt l'écrit à l'écran ;
- que `causalite_temporelle` **prouve** l'absence de fuite — elle établit
  l'absence de trois familles de fuite, sur trois troncatures. Une quatrième
  famille, non anticipée, ne serait pas vue ;
- que **quatre plis suffisent** — c'est le maximum que le corpus autorise, pas un
  optimum. Un corpus de deux ans donnerait le premier pli réellement
  interprétable.

---

# 20. Les alarmes ISA-18.2

`src/operations/alarms.py`, **617 lignes** — et non 561, valeur que
`partie-audit.md` § VI.1 et la consigne B4 portaient toutes deux. Le fichier de
test associé fait **335 lignes** pour **11 tests**.

C'est **le seul état du poste qui survive à un redémarrage**. Tout le reste est
recalculé au démarrage ; le registre d'alarmes, lui, est la mémoire du système.

## 20.1 Ce que la norme exige, et ce que ce registre en applique

ANSI/ISA-18.2 encadre le cycle de vie d'un système d'alarmes industriel. Quatre
exigences la structurent, et il faut dire pour chacune ce que ce projet fait —
et ce qu'il ne fait pas.

| exigence ISA-18.2 | ce que le registre applique |
|---|---|
| **cycle de vie explicite** — une alarme a des états nommés et des transitions permises | 5 états, 4 actions opérateur, transitions refusées si invalides |
| **acquittement traçable** — on sait qui a vu quoi, et quand | `acknowledged_by` / `acknowledged_at`, journal immuable |
| **inhibition encadrée** (*shelving*) — temporaire, motivée, réversible | motif **obligatoire**, `shelved_by` / `shelved_at` / `shelve_reason` |
| **retour à la normale distinct de la clôture** | `RETURNED_NORMAL` puis `CLOSED`, jamais l'un pour l'autre |

> **Ce que ce registre n'est pas, et le poste l'écrit à l'écran** : *« il ne
> remplace ni l'alarme DCS ni la GMAO »*. Il ne pilote aucun organe, ne suspend
> aucune alarme de conduite, et n'a aucune autorité sur la ligne. C'est un
> registre de **traçabilité** de ce que le système de surveillance a signalé.
>
> La norme demande aussi une **rationalisation** — justifier chaque alarme,
> fixer sa priorité et son temps de réponse — et une mesure de performance de la
> philosophie d'alarmes. Le projet couvre la première par l'AMDEC et les
> criticités ; **il ne fait pas la seconde**, faute d'exploitation réelle.

## 20.2 Les cinq états et les quatre actions **[MESURÉ]**

```
                    condition détectée
                            │
                            ▼
       ┌──────────────► ACTIVE ◄──────────┐
       │                 │    │            │ unshelve
       │      acknowledge│    │shelve      │
       │                 ▼    ▼            │
       │         ACKNOWLEDGED ──shelve──► SHELVED
       │                 │                 │
       │  condition      │                 │ (la condition peut cesser :
       │  cesse          │                 │  inscrit au journal, l'état
       ▼                 ▼                 │  SHELVED est conservé)
  RETURNED_NORMAL ◄──────┘                 │
       │                                   │
       │ close                             │
       ▼                                   │
    CLOSED                                 │
   (terminal)                              │
```

| | |
|---|---|
| `VALID_STATES` | **5** — `ACTIVE`, `ACKNOWLEDGED`, `SHELVED`, `RETURNED_NORMAL`, `CLOSED` |
| `OPEN_STATES` | **3** — les trois premiers |
| actions opérateur | **4** — `acknowledge`, `shelve`, `unshelve`, `close` |
| libellés de transition au journal | **8** |

Deux règles de transition méritent d'être soulignées, parce qu'elles ferment des
portes qu'on ouvre naturellement par commodité.

**`close` n'est permis que depuis `RETURNED_NORMAL`.** On ne clôture pas une
alarme dont la condition est toujours présente. C'est la bonne règle — et c'est
aussi ce qui rend AL-3 bloquant (§ 20.6).

**Une alarme inhibée ne revient pas silencieusement à la normale.** Le
commentaire du code raconte l'inversion :

> Il affirmait que « l'inhibition ne doit jamais masquer une résolution
> automatique », **et le code retournait immédiatement sans rien enregistrer** :
> l'inhibition masquait donc exactement cela.

Conserver l'état `SHELVED` est le comportement correct — inhiber sert précisément
à figer une alarme le temps d'une intervention, et une désinhibition doit rendre
la main sur une alarme dont l'état n'a pas été décidé en son absence. Mais le
retour aux conditions normales est un **fait**, et il est désormais inscrit au
journal sous `RETURN_TO_NORMAL_WHILE_SHELVED`. Sans lui, l'opérateur qui
désinhibe ne peut pas savoir que la condition avait cessé entre-temps.

## 20.3 Le schéma SQLite **[LU + MESURÉ]**

Deux tables, **26 colonnes** pour `alarms`, **9** pour `alarm_history`, **2**
index, **3** `PRAGMA`.

```sql
PRAGMA foreign_keys = ON     -- l'historique ne peut pas orpheliner
PRAGMA journal_mode = WAL    -- lecture concurrente pendant l'écriture
```

L'ouverture pose `isolation_level=None` — SQLite ne gère plus les transactions
implicitement — et chaque écriture est encadrée par un `BEGIN IMMEDIATE`
explicite, sous un `threading.RLock`. C'est ce qui rend les observations
concurrentes atomiques : **20 fils, 1 alarme, 20 occurrences**, verrouillé par
test.

**Le `CHECK` du statut est écrit en SQL et duplique les constantes Python.** À
noter, parce que c'est le motif inverse de celui appliqué dans `workflows.py` :
là-bas, le `CHECK` est **dérivé** des constantes par `_contrainte()` (défaut
WF-3, corrigé), ici les cinq états sont recopiés dans le littéral SQL. Le
vocabulaire vit donc en deux exemplaires qui peuvent diverger sans bruit — le
défaut de S8-2, corrigé dans un module et pas dans son voisin.

> **Constat ouvert, non référencé jusqu'ici** : ce que `workflows.py` a corrigé,
> `alarms.py` ne l'a pas. La correction est mécanique et sans risque. Elle est
> laissée à l'auteur plutôt que faite au passage, parce qu'elle touche au schéma.

**Migration non destructive.** `_add_missing_columns()` compare `PRAGMA
table_info` au schéma attendu et ajoute ce qui manque : **24 colonnes** peuvent
être ajoutées à une base créée par une version antérieure, sans perte. Deux
`UPDATE` de rattrapage complètent l'ancien format (`alarm_uid` vide,
`to_status` absent). Un registre qui perdrait son historique à chaque montée de
version ne serait pas opposable.

**La preuve est stockée en JSON**, sur l'alarme *et* sur chaque ligne
d'historique : horodatage, score d'anomalie, état procédé, codes de constatation,
valeurs citées, accord du contrôleur. C'est ce qui rend le registre **opposable**
— une transition sans sa preuve n'est qu'une affirmation.

## 20.4 La clé de déduplication **[LU]**

```python
alarm_key = f"{equipement}::{constatation_dominante}"
```

**La sévérité n'entre pas dans la clé**, et c'est délibéré : une même condition
qui passe de `WARNING` à `CRITICAL` doit rester **la même alarme** qui s'aggrave,
pas une seconde alarme. La sévérité stockée est d'ailleurs monotone —
`CRITICAL in {ancienne, nouvelle}` — donc une alarme montée en critique n'en
redescend jamais tant qu'elle est ouverte.

Le choix de la constatation dominante est le défaut **AL-1**, et il est **clos**.

> `RuleEngine.evaluate` appelle `_rule_sensor_health` **en premier**. Dès qu'un
> capteur dérivait, `SENSOR_FAULT` devenait donc la clé de l'alarme — même
> lorsqu'un `CONC_DROP_SEVERE`, suspicion de percement de tube, figurait dans la
> même analyse.

Trois conséquences, mesurées sur le code :

1. le registre nommait l'alarme d'après **le capteur qui dérive**, pas d'après le
   tube qui fuit — alors que l'agent, lui, retenait correctement la constatation
   dominante. *Le diagnostic affiché et l'alarme persistée ne désignaient pas la
   même chose* ;
2. `observe` cherche `WHERE alarm_key=?` avec la clé **courante**. Si la
   constatation-clé disparaissait alors qu'une autre subsistait, la ligne n'était
   plus retrouvée : une **seconde** alarme naissait et la première restait
   `ACTIVE` indéfiniment ;
3. la sévérité stockée est celle de la décision : une alarme nommée
   `SENSOR_FAULT` pouvait porter `CRITICAL`.

La correction **réutilise `_priorite`**, le barème de l'agent, au lieu d'en écrire
un second : *deux règles de priorité qui doivent coïncider ne se recopient pas.*

Détail à retenir, parce qu'il est l'idiome banni du dépôt :

> `if lead:` **testait la fausseté, pas l'absence**. Le champ est déclaré
> `str | None` : seul `None` signifie « l'agent n'a pas tranché ». Une chaîne
> vide tombait dans le repli sans que rien ne le dise. Troisième récidive de
> l'idiome, après `if limit:` (rejeu) et le sentinelle `lead=None`.

## 20.5 Le déclencheur, et le défaut AL-2 **[LU]**

`observe()` pose **deux questions séparées**, et les avoir séparées est la
correction.

```python
condition_presente = severite in {"WARNING", "CRITICAL"}
accepted_alarm     = condition_presente and verdict.agreement
```

Le test valait auparavant `sévérité alarmante ET accord du Judge`. Sa négation
partait donc vers la résolution dans **deux cas de natures opposées** :

| cas | traitement d'alors | correct ? |
|---|---|---|
| la condition a cessé | résolution | oui |
| la condition **persiste**, le Judge a rejeté la rédaction | résolution | **absurde** |

> Mesuré : une alarme `CRITICAL` levée à t₁, réobservée à t₂ avec la même
> constatation et `agreement = False`, passait à `RETURNED_NORMAL` — **alors que
> le percement suspecté était toujours là**.

C'est exactement ce que l'en-tête du module interdit : *« le registre ne déduit
jamais qu'une alarme a disparu parce qu'une autre analyse est normale »*. Ici il
le déduisait d'un désaccord de gouvernance, **ce qui est pire** :

> **Le Judge conteste la rédaction d'un diagnostic. Il ne dit rien du procédé.**

Trois branches désormais, et la branche du milieu ne fait **rien** :

| état | effet sur le registre |
|---|---|
| condition présente **et** acceptée | levée ou répétition |
| condition présente, **contestée** | **aucun** — le désaccord est déjà publié par `/api/replay/disagreements` |
| condition absente | retour à la normale |

**AL-2 est clos**, verrouillé par test au lot S42.

## 20.6 AL-3 — la décision encore ouverte **[LU]**

C'est le seul « correctif identifié, jamais appliqué » qui subsiste ; AL-1 et
AL-2 sont clos.

Quand l'agent n'a pas désigné de constatation dominante, `_trigger` retombe sur
`findings[0]` — c'est-à-dire **l'ordre d'écriture des règles**. Le commentaire
qui justifiait ce repli affirmait que *« l'ordre des règles y est sans
conséquence : la clé recherchée est celle déjà enregistrée »*. **C'est l'inverse
qui est vrai** : `observe` calcule la clé sur l'analyse **courante**, puis cherche
avec cette clé-là.

Le scénario, mesuré sur trois instants :

| instant | ce qui se passe | état du registre |
|---|---|---|
| t₁ | `CONC_DROP_SEVERE` dominant | alarme `::CONC_DROP_SEVERE` **ACTIVE** |
| t₂ | nominal, `SENSOR_FAULT` en INFO | clé cherchée `::SENSOR_FAULT` → aucune ligne, **alarme intacte** |
| t₃ | plus aucune constatation | `_key` rend `None`, `observe` sort immédiatement |
| — | clôture manuelle tentée | **refusée** : `close` n'est permis que depuis `RETURNED_NORMAL` |

> **L'alarme ne peut ni se résoudre, ni être close. Elle reste `ACTIVE`
> indéfiniment, et le registre ISA-18.2 n'accumule que des ouvertures.** La voie
> de résolution ne fonctionne que pour une règle qui réémet le **même code** à
> une sévérité plus basse — cas rare.

C'est un défaut de fond pour un registre d'alarmes : une supervision dont les
alarmes ne se ferment jamais devient illisible en quelques jours, et l'exploitant
apprend à ne plus la regarder.

**Pourquoi il n'est pas corrigé**, et la raison est bonne. Balayer les alarmes
ouvertes dont la condition n'est plus observée suppose **trois décisions de
sécurité** :

1. qu'une analyse **sans constatation** vaille preuve de retour à la normale —
   or l'en-tête du module dit exactement le contraire ;
2. ce qu'on fait d'une **ligne à l'arrêt** — c'est le piège de S7-1, où des
   fenêtres calmes parce que la ligne ne tournait pas comptaient comme des
   non-événements ;
3. comment un **capteur en défaut** interagit avec le balayage — un capteur mort
   ne prouve pas que la condition a cessé.

Aucune ne se tranche sans pouvoir rejouer la suite complète. **Décision de
l'auteur, pas de la session.**

## 20.7 Ce que la section 20 ne permet pas d'affirmer

- que le registre soit **conforme ISA-18.2** — il en applique le cycle de vie et
  la traçabilité ; il ne fait ni rationalisation formelle ni mesure de
  performance de la philosophie d'alarmes ;
- qu'il ait été **éprouvé en exploitation** — il n'a jamais tourné hors du poste
  de développement, et le journal d'escalade est resté vide (§ 21) ;
- que le **cycle de vie soit complet** — AL-3 laisse une branche par laquelle une
  alarme ne se ferme jamais ;
- que le **schéma soit à l'abri d'une divergence** — le `CHECK` SQL recopie les
  constantes Python au lieu d'en dériver, contrairement à `workflows.py` ;
- qu'une alarme **atteigne un opérateur** — le registre trace, il n'escalade pas.
  C'est le rôle du canal de § 21, et un seul instant du corpus atteint la
  sévérité critique en marche établie.

---

# 21. Notifications et escalade

`src/notifications/email.py` (**546 lignes**) et `redaction.py` (**312**) — et
non 512 et 294, valeurs que la consigne porte encore.

Ce chapitre est court à décrire et lourd de conséquences : c'est la seule voie
par laquelle le système atteint quelqu'un qui n'est pas devant l'écran.

## 21.1 Le filtre d'escalade — quatre gardes en série **[LU]**

`notify()` reçoit **toutes** les analyses du rejeu et n'en laisse passer presque
aucune. Dans l'ordre :

| garde | condition | ce qu'il devient sinon |
|---|---|---|
| **1. exutoire** | un relais SMTP **ou** un dépôt local | sortie immédiate, rien n'est comptabilisable |
| **2. accord du contrôleur** | `verdict.agreement` | `_suppressed += 1` — *une décision rejetée ne réveille personne* |
| **3. sévérité minimale** | `ALERT_MIN_SEVERITY`, défaut **`CRITICAL`** | `_suppressed += 1` |
| **4. anti-rebond** | `ALERT_COOLDOWN_MINUTES`, défaut **60 min**, par couple destinataire × événement | ignoré silencieusement |

La clé d'anti-rebond est `sévérité:modes AMDEC triés`, préfixée du destinataire.
Deux points comptent :

- **le cooldown n'est validé qu'après livraison SMTP réussie** — un envoi qui
  échoue ne consomme pas la fenêtre de silence, sinon une panne de relais
  produirait une heure de mutisme non voulue ;
- `_pending_keys` empêche qu'un même événement soit mis en file deux fois pendant
  que le worker travaille.

**Conséquence sur le corpus, et il faut l'écrire** : avec `CRITICAL` en seuil,
**un seul instant des quatorze mois** atteint la sévérité critique en marche
établie. Le journal d'escalade reste donc vide tant que le rejeu ne l'a pas
franchi, et le poste le dit à l'écran plutôt que d'afficher un compteur à zéro
sans explication.

## 21.2 Le dépôt local — la preuve de passage **[LU]**

C'est le dispositif le plus intéressant du module.

> Sans relais SMTP, la version précédente ne faisait **rien du tout** : pas
> d'envoi, pas de trace, pas de moyen de vérifier que la chaîne d'escalade
> fonctionne. Une supervision industrielle ne peut pas se permettre ce silence —
> si le canal sortant tombe, il faut pouvoir dire **après coup** quelles alertes
> auraient dû partir.

Chaque message est donc écrit sur disque au **format RFC 822** (`.eml`), dans
`data/runtime/escalades/`, avec un état explicite :

| état | signification |
|---|---|
| `envoye` | le relais a accepté |
| `depose` | aucun relais — le message est sur disque |
| `echec` | le relais a refusé, après 3 tentatives |
| `non distribue` | l'alerte était qualifiée et **aucune adresse ne pouvait la recevoir** |

Le **journal en mémoire** (200 entrées, 25 exposées) alimente l'interface ; les
fichiers survivent à l'arrêt. C'est ce couple qui rend l'escalade vérifiable :
*un compteur à zéro ne distingue pas « rien à escalader » de « canal mort ».*

### Le défaut le plus grave du module, et il est revenu deux fois

**Une alerte critique sans destinataire disparaissait sans trace.**

Le garde d'entrée était `if not self.enabled` — or `enabled` exige un
destinataire actif. Sans session ouverte et sans `ALERT_EMAIL_TO`, une décision
`CRITICAL` validée par le contrôleur repartait en silence : *pas d'envoi, pas de
fichier, pas de ligne de journal, pas même un incrément de compteur.* Rien.

> Et le moment où l'alerte automatique compte le plus est précisément celui où
> personne n'est devant l'écran — **donc celui où aucune session n'est ouverte**.
> La nuit, le week-end, pendant tout arrêt de poste.

La correction : le garde ne retient plus que l'exutoire, et l'absence de
destinataire est traitée après rédaction, avec un compteur dédié
(`undelivered_no_recipient`), une ligne « non distribué » au journal, et un
fichier `.eml` dans le dépôt.

**Puis le défaut est revenu par l'ordre des appels.** `_deposer` était appelé
**avant** `_tracer`, et il lève `RuntimeError` dès que le dépôt vaut `None` — cas
atteignable, puisque le garde d'entrée n'exige que « relais **ou** dépôt ».
L'exception remontait, était attrapée plus haut, et `_tracer` n'était **jamais**
atteint : l'alerte critique disparaissait du journal d'escalade.

> C'est le défaut **exact** que ce bloc avait été écrit pour corriger,
> réintroduit par l'ordre de deux appels. La trace est la garantie ; le fichier
> n'en est que la copie durable. **La trace d'abord, le dépôt ensuite.**

Même principe appliqué à la file : une `queue.Full` incrémentait un compteur et
écrivait dans le journal **serveur**, que l'exploitant ne lit pas. Or la
saturation survient précisément quand le relais est lent ou tombe, *c'est-à-dire
quand le plus d'alertes se perdent d'un coup*. Elle passe désormais par `_tracer`
comme les trois autres issues.

## 21.3 Concurrence — trois threads sur un même ensemble **[LU]**

`_recipients` est lu et modifié par **trois** threads : HTTP (ouverture et
fermeture de session), rejeu (`notify`), worker (`_send`).

Le raisonnement de la correction mérite d'être cité, parce qu'il refuse le
diagnostic facile :

> **Ce n'est pas l'itération qui casse** — vérification faite, `sorted()` sur un
> ensemble est atomique sous le GIL de CPython et ne lève jamais ici. Le défaut
> réel est la **fenêtre de cohérence** de `remove_recipient`, qui retire
> l'adresse puis remet le destinataire par défaut **en deux temps** : entre les
> deux, l'ensemble est vide.

**Mesure : sur 200 000 retraits, un observateur concurrent l'a vu vide 54 098
fois.** Une alerte émise dans cette fenêtre ne trouve aucun destinataire et
disparaît. Un `RLock` et une lecture unique par `_destinataires()` ferment la
fenêtre.

Second défaut de la même famille : `enabled` vérifie qu'un destinataire existe,
puis **relâche le verrou** ; les envois ponctuels indexaient ensuite la liste à
`[0]`. Entre les deux, une session peut se fermer. *C'est exactement ce qui se
produit quand une session expire pendant qu'un rapport part : `enabled` a répondu
vrai, la session tombe, l'indexation lève `IndexError` et l'envoi remonte en 500
sans qu'aucune trace ne dise pourquoi.*

### Le rapport partait au premier par ordre alphabétique

`_premier_destinataire()` porte une correction que le poste rendait invisible :

> `_destinataires()` rend une liste **triée**, et les envois ponctuels en
> prenaient l'élément `[0]` — sans aucun rapport avec le technicien qui venait de
> cliquer. Avec deux adresses actives, « astreinte@… » passe avant « mounir@… » :
> **le rapport demandé par l'un arrivait chez l'autre, et l'interface annonçait un
> succès.**

L'adresse demandée n'est retenue **que si elle est déjà destinataire actif** :
ce canal ne doit pas devenir un moyen d'expédier l'état du poste vers une adresse
arbitraire. C'est une décision de sécurité, pas de confort.

## 21.4 Ce que la rédaction expurge, et pourquoi **[LU]**

C'est un sujet de **gouvernance**, pas de mise en forme — la consigne insiste, et
elle a raison.

Ce que l'endpoint `/api/notifications/governance` envoyait réellement :
`json.dumps(payload, indent=2)`. **Trois cents lignes de structure interne,
coefficients de régression compris, expédiées à l'adresse d'un technicien.**

Trois défauts, par gravité croissante :

**1. Ce n'est pas une synthèse.** Personne ne lit un dictionnaire imbriqué sur un
téléphone. L'information qui compte — *le contrôleur est en ALERTE sur son propre
comportement* — était noyée sous deux cents lignes de santé capteur. **Un rapport
que son destinataire ne lit pas ne trace rien.**

**2. Il divulguait l'arborescence du producteur.** Le chemin absolu du fichier
source partait dans chaque message. Le dépôt interdit déjà cela dans ses
artefacts, et `test_les_artefacts_ne_portent_pas_de_chemin_absolu` le vérifie —
**le canal e-mail échappait à ce contrôle.** Seul le nom du fichier est conservé,
et la normalisation traite les deux familles de séparateurs : un chemin Windows
quand le service tourne sous Linux, et inversement.

**3. Il était écrit en nombres anglais.** « 0.9642612800415576 » dans un document
francophone destiné à un site marocain, quand tout le reste du poste applique la
virgule décimale.

### Quatre vocabulaires traduits

Les identifiants internes ne sont pas des libellés. Le rapport annonçait
« Régimes : 8 832 h running », « Agent : rules », « Origine :
runtime_trained_unpromoted » — **des clés de code livrées telles quelles à un
exploitant francophone**.

| table | ce qu'elle traduit |
|---|---|
| `REGIMES` | `RUNNING` → « en marche », etc. |
| `ORIGINES` | `runtime_trained_unpromoted` → « entraîné au démarrage, non promu » |
| `ETATS_CONTROLEUR` | `ALERTE` → « le contrôleur signale une anomalie sur lui-même » |
| `MODES_AGENT` | `rules` → « règles déterministes » |

Plus `RESERVE_LIBELLES`, partagée avec l'écran : **les réserves du contrôleur
sont traduites des deux côtés par la même table**, ce qui interdit qu'elles
divergent.

Règle de repli, et elle est juste : **un identifiant inconnu retombe sur
lui-même** plutôt que de disparaître. *Mieux vaut un mot anglais qu'une
information perdue.*

Le rapport tient en **une page**, place le verdict en tête, et se termine par une
section « **Ce que ce rapport n'affirme pas** » — parce qu'une supervision non
supervisée qui laisse croire à un diagnostic confirmé est un risque, pas un
service.

### La duplication que le module correcteur avait introduite

`_nombre()` reduplique `src.formatting.nombre`. Le module écrit **pour corriger un
défaut de typographie** l'a corrigé en recopiant la conversion que
`src/formatting.py` porte déjà — ADR-011 règle 2 : *« la mise en forme des nombres
est centralisée »*.

> **Le module qui invoque cette règle ne peut pas être celui qui l'enfreint.**

L'enveloppe subsiste, mais elle délègue, et deux comportements propres au rapport
la justifient : le défaut à **zéro décimale** (seize appels s'y fient, et
« 3 436,0 décisions jugées » ne se lit pas), et le refus de formater un booléen —
`float(True)` vaut 1,0, donc un champ resté à `True` s'afficherait « 1 » au lieu
d'être signalé absent.

## 21.5 Diagnostiquer un échec plutôt que le nommer **[LU]**

`diagnostiquer_echec()` traduit une exception SMTP en **cause actionnable**. Le
journal ne conservait que `type(exc).__name__` : l'interface affichait donc
« SMTPAuthenticationError » à un exploitant, *qui n'a aucun moyen d'en déduire
quoi faire*.

| exception | ce que l'exploitant lit |
|---|---|
| `SMTPAuthenticationError` | Gmail n'accepte plus le mot de passe du compte depuis mai 2022 — il faut un **mot de passe d'application de 16 caractères**, sans espaces |
| `SMTPSenderRefused` | `SMTP_FROM` doit correspondre au compte authentifié par `SMTP_USERNAME` |
| `SMTPNotSupportedError` | le relais ne propose pas STARTTLS sur ce port — utiliser le **587** |
| `SMTPRecipientsRefused` | le relais a refusé l'adresse du destinataire |
| `TimeoutError` / `OSError` | vérifier `SMTP_HOST`, `SMTP_PORT`, et le pare-feu en sortie |

**Le texte du serveur n'est pas recopié tel quel** : il varie selon le relais et
peut contenir l'adresse d'authentification. Chaque cause est traduite par une
phrase fixe, vérifiable, **qui ne divulgue aucun paramètre du poste**.

Même principe pour `status()`, qui dit **pourquoi** le canal est inactif plutôt
qu'un « désactivé » laissant croire à une panne. Le message le plus important est
celui du canal sans destinataire :

> « **AUCUNE ALERTE NE PEUT PARTIR.** Aucun destinataire actif : l'adresse d'un
> technicien ne devient destinataire qu'à l'ouverture de sa session. Pour une
> escalade permanente, indépendante de toute session, renseigner `ALERT_EMAIL_TO`
> dans le fichier `.env`. »

L'ancienne phrase décrivait un canal qui s'activerait tout seul à la prochaine
session. *Elle laissait croire que la surveillance était couverte, alors qu'aucune
alerte ne peut partir tant que personne n'est connecté.*

## 21.6 Ce que la section 21 ne permet pas d'affirmer

- que le canal ait **délivré une alerte réelle** — le journal d'escalade est resté
  vide, et un seul instant du corpus atteint la sévérité critique en marche
  établie ;
- que l'escalade soit **permanente** — sans `ALERT_EMAIL_TO`, elle dépend d'une
  session ouverte, donc elle est absente la nuit et le week-end. Le poste
  l'écrit ;
- que le **relais ait été éprouvé** — les envois sont testés contre un faux
  serveur, jamais contre un relais OCP ;
- que la **rédaction couvre tout** — le corps de l'alerte et le message de test
  sont écrits dans `email.py`, hors du parcours du test de typographie, qui ne
  visite que les surfaces exposées par une API. Le message de test a été
  rattrapé à la main (NOTIF-1) ; **rien n'empêche un troisième corps d'échapper
  au contrôle.**

---

# 22. Rejeu temps réel et sécurité

`src/realtime/replay.py` (**502 lignes**) et `src/security/auth.py` (**414**) —
et non 430 et 300. Le registre technicien (`registry.py`) est couvert par la
partie A ; il n'est pas repris ici.

## 22.1 La promesse de causalité, vérifiée ligne à ligne **[LU]**

La consigne demande une vérification prioritaire : *le système promet qu'« à
l'instant t, seule la fenêtre [début, t] est transmise à la détection ».*

**La promesse, telle qu'elle était écrite, est fausse.** Le module l'a reconnu
lui-même dans son en-tête, et le dire est plus utile que de la répéter :

> **Ce module ne transmet aucune fenêtre.** Il appelle `pipeline.analyze_at(ts)`,
> qui passe la table de features **entière** à ses trois étages.

Voici la chaîne, étage par étage, telle qu'elle a été relue :

| étage | ce qui est reçu | ce qui est lu |
|---|---|---|
| `DCSReplay._loop` | — | appelle `analyze_at(ts)` |
| `pipeline.analyze_at` | table entière | la passe telle quelle aux trois étages |
| `detector.analyze` | table entière | `row = features.loc[ts]` puis **`history = features.loc[:ts]`** — tronqué |
| `rules.evaluate` | `row`, `history` | ne voit que le tronqué |
| étage statistique | `row` seule | une ligne, pas une fenêtre |
| `_recent_exceedances` | table entière | `score_series(features)` **sur tout**, puis `s.index <= ts` |
| `judge.judge` | table entière | ne la consulte qu'à travers `detector.analyze` **au même horodatage** |

**Le point à vérifier était `_recent_exceedances`**, et c'est le seul endroit où
un doute était permis : il score la table **entière**, futur compris, avant de
tronquer. Si ce scoring normalisait sur le lot, le futur fuirait dans le passé.

Vérification faite dans `StatisticalDetector` :

```python
def _normalize(self, raw):
    z = np.clip((raw - self.score_center_) / self.score_scale_, -60.0, 60.0)
    return 1.0 / (1.0 + np.exp(-z))
```

`score_center_` et `score_scale_` sont **figés à l'ajustement** — médiane et MAD
de la période de référence — et non recalculés sur le lot présenté. Le score
d'une ligne ne dépend donc **que de cette ligne** et du modèle ajusté :
`score_series(table)` et `score_series(table[:t])` rendent des valeurs
identiques sur les lignes communes. La troncature qui suit est saine.

> **La propriété est donc vraie, et vraie pour une bonne raison** — la fonction
> de score est ponctuelle. Mais elle n'est **imposée nulle part**. Ajouter à
> `analyze_at` un consommateur qui lirait un quantile sur la table entière
> suffirait à la rompre, et ce fichier continuerait de l'affirmer.

C'est la situation de S7-2 : **vrai par accident, pas par construction**. D'où le
verrou, qui est **comportemental** et non déclaratif :

> `test_le_rejeu_ne_lit_jamais_l_aval` rejoue **la même analyse** sur la table
> complète et sur la table tronquée à `t`, et exige un résultat identique.

C'est la bonne forme de contrôle pour cette propriété : elle ne dépend d'aucune
inspection de code, elle échouerait sur n'importe quelle fuite, quelle qu'en soit
la forme syntaxique.

## 22.2 La décimation, et l'instant qu'elle sautait **[LU]**

Le rejeu n'analyse qu'un instant sur `analyze_every` — trois par défaut. Le
défaut qui en découlait est le plus spectaculaire du module.

> Sur ce corpus, **un unique horodatage** atteint la sévérité critique en marche
> établie : le **2 octobre 2024 à 18 h**, température de sortie acide à
> **72,15 °C**, position **6 610** dans la série. **6 610 n'est pas multiple de
> trois.**
>
> Départ au début des données, cet instant n'était donc **jamais analysé** : pas
> de rouge sur le jumeau, pas d'alarme ouverte, pas d'escalade. *Le seul
> événement critique de quatorze mois disparaissait par une règle de
> performance.*

`_instants_incontournables()` marque tout instant franchissant un seuil du
référentiel — **62 sur le corpus** — et ceux-là sont analysés quelle que soit
leur position. Le filtre est vectoriel, calculé une fois : son coût est celui
d'une comparaison de colonnes.

Trois détails de mise en œuvre méritent d'être retenus :

**Les horodatages, pas les positions.** Le rejeu peut démarrer au milieu de la
série, auquel cas les positions ne coïncident plus.

**Un franchissement pendant un arrêt ne désigne rien.** Le masque est intersecté
avec `process_state ∈ {RUNNING, TRANSIENT}` — les transitoires sont conservés,
parce que c'est là que la perte de contrôle s'installe.

**`except Exception` avalait tout.** La fonction qui lit un seuil du référentiel
attrapait n'importe quelle panne — alias inexistant, référentiel mal chargé — et
rendait `None`, c'est-à-dire *pas de seuil, donc pas d'instant incontournable*.
**La garantie disparaissait en silence par le mécanisme même censé la tenir.**
Seule l'absence déclarée est désormais tolérée.

Et la fonction s'appelait `seuil`, nom de la fonction canonique de
`knowledge` — le piège exact de M-1, où une locale de ce nom rendait la fonction
importée inaccessible à l'endroit même où le défaut se reproduisait. Le nom est
libéré.

### La garantie ne valait que pour un des deux chemins

`run_sync()` — celui qu'empruntent **les tests et les scripts hors ligne** —
décimait par simple découpage `[::analyze_every]`, sans consulter
`_obligatoires`.

> *La propriété était affirmée dans un chemin et vérifiée dans l'autre.*

Corrigé, et verrouillé par `test_service_invariants`. Au passage, `limit=0`
valait « aucune limite » : `if limit:` teste la fausseté au lieu de l'absence, et
la signature annonce `int | None`. **Zéro instant est une demande légitime**, et
elle rejouait le corpus entier. Deuxième récidive de l'idiome, après `if lead:`
dans le registre d'alarmes.

## 22.3 La vitesse publiée est celle qui est appliquée **[LU]**

Le délai valait `analyze_every / speed`, appliqué à **chaque entrée d'index**.
La vitesse effective valait donc `speed / analyze_every`.

> Avec les valeurs par défaut du dépôt — `REPLAY_SPEED=120`, `REPLAY_STEP=3` — le
> rejeu défilait à **40 h/s** pendant que l'API publiait
> `speed_hours_per_second: 120`. **Un facteur trois sur le seul réglage que
> l'exploitant manipule.**

Une entrée d'index vaut une heure de process : le délai est `1 / speed`, quel que
soit le nombre d'instants analysés. La vitesse est **relue à chaque tour** sous
verrou, pour que `set_speed()` prenne effet sans redémarrer, et l'attente passe
par `Event.wait()` — interruptible, donc `stop()` reste immédiat même à basse
vitesse.

**Un arrêt qui n'arrête pas ne se déclare pas arrêté.** `running` était remis à
faux sans vérifier que le thread avait fini. Passé le délai de garde, l'état
annonçait donc un rejeu arrêté pendant qu'un thread continuait d'émettre — et
`start()`, qui ne se protège que par ce booléen, **en aurait lancé un second**,
deux boucles alimentant le même état. Le cas demande qu'une analyse dépasse cinq
secondes ; il n'est pas atteint aujourd'hui, *et il ne signalerait rien s'il
l'était*.

## 22.4 Les sessions **[LU + MESURÉ]**

| paramètre | valeur | source |
|---|---|---|
| dérivation du mot de passe | **PBKDF2-SHA256, 600 000 itérations** | `auth.py` |
| longueur minimale | **12 caractères** | `MIN_PASSWORD_LENGTH` |
| tentatives avant blocage | **5**, la 6ᵉ lève `TooManyAttemptsError` | `MAX_ATTEMPTS` |
| jeton de session | `token_urlsafe(32)` — opaque | — |
| jeton CSRF | `token_urlsafe(24)` | — |
| expiration par **inactivité** | **30 min** | `AUTH_IDLE_MINUTES` |
| expiration **absolue** | **8 h** | `AUTH_ABSOLUTE_HOURS` |

**La limitation de débit est vérifiée avant le mot de passe.** L'ordre compte :
vérifier après ferait payer la dérivation PBKDF2 à chaque tentative, ce qui
transforme le garde anti-force-brute en amplificateur de déni de service.
L'événement `LOGIN_RATE_LIMITED` nomme le compte visé **et** la clé client.

**`MIN_PASSWORD_LENGTH` vivait dans `registry.py`**, qui importe `auth` —
`hash_password` ne pouvait donc pas l'importer et codait la valeur en dur. Deux
exemplaires d'une même règle, séparés par une dépendance circulaire. La constante
est descendue dans `auth.py`.

## 22.5 SEC-2 — la rotation qui invalidait des requêtes légitimes **[LU]**

C'est le défaut le plus instructif du module, parce que **le diagnostic était
juste et le correctif ne le traitait pas**.

La version précédente portait :

```python
# LE JETON CSRF ETAIT REMPLACE HORS VERROU, donc pendant qu'une
# requete concurrente pouvait le lire [...] : la rotation faisait
# echouer des requetes legitimes.
session.csrf_token = secrets.token_urlsafe(24)   # ← déplacé sous le verrou
```

> Déplacer l'affectation **sous** le verrou ne change rien, **parce que le
> lecteur ne prend jamais le verrou** : `api/main.py` compare
> `X-CSRF-Token != session.csrf_token` sur l'objet que `validate()` lui a rendu,
> verrou déjà relâché. **Le verrou sérialise les écrivains entre eux ; il n'a
> jamais protégé personne d'une mutation en place.**

Déroulé du défaut, avec `/api/auth/refresh` appelé pendant qu'une écriture est en
vol :

1. la requête **A** obtient la session par `validate()` ;
2. la requête **B** fait tourner le jeton et **écrase `csrf_token` sur l'objet que
   A tient toujours** ;
3. A compare son en-tête — l'ancien jeton — à la valeur nouvelle, et reçoit
   **403 « Jeton de session invalide » sur une requête parfaitement légitime**.

La correction applique la doctrine établie au lot S11 sur le registre technicien
(SEC-1) : **la publication atomique**.

> *On ne modifie pas l'objet que d'autres tiennent ; on en publie un nouveau.*

`dataclasses.replace` construit une session neuve, l'ancienne restant intacte
pour les requêtes en vol. `created_at` est recopié tel quel : **la rotation ne
prolonge pas l'expiration absolue**, ce que la première ligne promet.

**Second défaut fermé au passage** : `validate()` prenait puis relâchait le verrou
avant que `rotate` ne le reprenne. Deux rotations concurrentes du même jeton
produisaient donc **deux cookies valides pour une seule ouverture de session**.
La validation et la publication tiennent maintenant dans une seule prise.

## 22.6 SEC-3 — la décision encore ouverte **[LU]**

`auth.py` ne porte **qu'un seul** `self._audit.append`, atteint depuis
`authenticate` seul.

`rotate()` et `destroy()` n'inscrivent rien : **la fin de session n'est pas
tracée**. Un journal d'authentification qui enregistre les ouvertures et pas les
fermetures ne permet pas de reconstituer qui était en poste à un instant donné —
ce qui est précisément l'usage attendu, puisque l'adresse de session détermine le
destinataire des escalades critiques.

Le contrôle qui aurait dû l'attraper l'a **gelé** au lieu de le signaler :

> `test_session_opaque_csrf_et_invalidation` comparait le journal d'audit
> **entier** après `rotate()` et `destroy()`. Il figeait donc l'absence de toute
> trace de fin de session, **et cassait si on l'ajoutait**. C'est la forme « plus
> large que l'objet » du défaut de test dominant (§ 23.3).

**Décision de l'auteur.** Le correctif est de deux lignes ; ce qui se décide,
c'est ce qu'on inscrit — une déconnexion volontaire, une expiration par
inactivité et une expiration absolue ne se lisent pas de la même façon dans un
journal d'audit.

## 22.7 Ce que la section 22 ne permet pas d'affirmer

- que la **causalité soit garantie par construction** — elle est vraie, vérifiée
  étage par étage, et tenue par un test comportemental, pas par le code ;
- que le rejeu **soit un flux DCS** — c'est un rejeu d'historique. Le poste
  n'a **aucune connexion temps réel** à un DCS ou à un historian ;
- que l'**authentification soit éprouvée** — aucun test d'intrusion, et le
  registre local est un mécanisme de démonstration mono-poste. Le service bloque
  d'ailleurs son démarrage en production tant qu'un fournisseur IAM OIDC n'est pas
  intégré ;
- que la **fin de session soit traçable** — elle ne l'est pas (SEC-3) ;
- que `stop()` **arrête toujours** — au-delà du délai de garde de cinq secondes,
  il refuse de mentir et laisse l'état à « en cours », ce qui est le comportement
  correct mais n'est pas un arrêt.

---

# 23. La stratégie de validation logicielle

## 23.1 Le périmètre **[MESURÉ, 2026-08-08]**

**20 fichiers de test, ≈ 7 200 lignes.** Dix ont été lus intégralement pendant
l'audit (lots S29, S40–S45), soit ≈ 2 700 lignes ; les corrections qui suivent en
sont issues.

| fichier | lignes | ce qu'il verrouille |
|---|---|---|
| `test_domain.py` | 206 | cohérence du référentiel gouverné |
| `test_ingest.py` | 235 | qualité de donnée, causalité de l'ingestion |
| `test_fouling_injection.py` | 229 | méthode du banc d'injection |
| `test_model_governance.py` | 283 | manifeste, portes, promotion |
| `test_replay.py` | 157 | causalité et décimation du rejeu |
| `test_alarm_store.py` | **335** | cycle de vie ISA-18.2 |
| `test_workflows.py` | 312 | barrières HSE, états, schéma SQL |
| `test_access_notifications.py` | 332 | sessions, CSRF, canal d'escalade |
| `test_service_invariants.py` | 389 | invariants de la couche HTTP, par AST |
| `test_redaction_gouvernance.py` | — | expurgation des identifiants internes |

Restent à couvrir : `test_api.py` (1 043), `test_features_detector.py` (860),
`test_operator_registry.py` (371), `test_agents_judge.py`, `test_kpi.py`,
`test_sensitivity.py`, `test_topology.py`, `test_typographie.py`,
`test_documentation.py`, `test_project_metrics.py`, `conftest.py`, `helpers.py`.

## 23.2 « Le patron » — la contribution méthodologique **[LU]**

Le dépôt a inventé une forme de test qu'il emploie **quinze fois** :

> **Un test qui interdit le retour d'un défaut par ANALYSE DU SOURCE — `ast`,
> `inspect.getsource`, lecture de fichier — et non par exécution.**

### Pourquoi il fallait l'inventer

Trois situations où l'exécution ne peut pas servir :

1. **Le coût.** Vérifier que les sept portes publiées ont toutes un intitulé à
   l'écran demanderait de lancer le backtest — corpus entier, plusieurs minutes.
   On lit les littéraux `{"gate": "..."}` que la fonction construit.
2. **La forme, pas le comportement.** Un handler déclaré `async def` sans jamais
   `await` fonctionne parfaitement en test unitaire **et gèle la boucle
   d'événements en exploitation**. Le défaut est dans la forme du code ; il se
   voit dans l'arbre syntaxique, jamais dans une requête isolée.
3. **La cohérence entre deux langages.** Les identifiants HTML cherchés par le
   JavaScript n'existent dans aucun espace Python : seule la lecture croisée des
   deux sources peut les confronter.

### Les quinze emplois **[LU]**

`test_service_invariants.py` en concentre onze, chacun né d'un défaut réel :

| invariant | défaut d'origine **[MESURÉ]** |
|---|---|
| aucun handler calculant sur la boucle | **32 handlers sur 47** étaient `async def` sans `await` — dont `auth_login` (PBKDF2, **600 000 itérations**) et `analyze` (appel LLM) |
| en-têtes de sécurité en un seul lieu | 401, 403 et 500 partaient **sans aucun en-tête de défense** ; six en-têtes, posés par `_durcir` seul |
| config validée avant tout effet de bord | validée au `lifespan` seulement, donc après sessions, registre et CORS |
| client LLM avec délai maximal | `max_retries=0` mais aucun `timeout` : un appel pendu figeait la supervision |
| pas d'allègement hors de la vitesse | REPLAY_SPEED=120, REPLAY_STEP=3 ⇒ **40 h/s réels**, publiés comme 120 |
| `run_sync` consulte `_obligatoires` | la garantie ne tenait que sur la boucle threadée |
| `fit()` invalide le cache de scores | la clé de `score_series` ne décrit que les données, jamais le modèle ; `invalidate_cache()` existait, débranchée |
| durées mises en forme côté serveur | l'ingestion publiait `str(step_nominal)` = « 0 days 01:00:00 » |
| aucun outil qualité inerte | mypy configuré, ni installé, ni dans le Makefile, ni en CI |
| bancs du poste exécutés en CI | **84 vérifications** ne bloquaient rien *(état au moment de la correction ; elles sont **98** au 2026-08-08 — voir § 17.7)* |
| chaque action opérateur a un libellé | `OPERATOR_TRANSITIONS` ≡ `OPERATOR_TRANSITION_LABELS` |

Quatre autres ailleurs : les portes publiées ont toutes un intitulé ; tout état
déclaré est productible ; les poids affichés sont ceux que le Judge applique ;
tout identifiant cherché par le poste existe dans la page.

### La limite du procédé, et sa parade **[LU]**

Un test qui lit du texte peut se satisfaire de **sa propre explication**. Deux
parades sont employées dans le dépôt :

- `test_aucun_outil_de_qualite_declare_n_est_inerte` cherche une **ligne de
  dépendance**, pas une mention : « un simple `in` aurait passé même après
  suppression de la dépendance — le contrôle se serait auto-satisfait sur son
  propre commentaire » ;
- `test_la_mise_en_forme_des_durees_est_centralisee` **écarte les commentaires**
  avant de chercher, parce qu'ils citent l'ancienne expression pour expliquer le
  défaut ;
- `model_validation._decalages_non_causaux` va plus loin : il **blanchit chaînes
  et commentaires par `tokenize`**, ce qui permet d'auditer `src/governance/`
  lui-même sans faux positif.

## 23.3 Le défaut de test dominant — résultat d'audit **[MESURÉ]**

Six occurrences prouvées sur dix fichiers relus. Ce n'est **pas** l'absence de
test :

> **La portée de l'assertion ne coïncide pas avec celle de l'intention.**

Quatre formes, toutes rencontrées :

| forme | exemple mesuré |
|---|---|
| **plus étroite que le nom** | `test_le_schema_derive_son_vocabulaire_des_constantes` annonce une dérivation — donc une égalité — et vérifiait une inclusion plus l'absence d'un intrus **nommé** (`CANCELLED`). Un état ajouté au seul littéral SQL passait |
| **plus étroite que le nom** | `test_les_en_tetes_de_securite...` nomme « les refus **401, 403 et 500** » et n'en vérifiait que deux — le 500 manquait, seul obtenable sans authentification |
| **plus étroite que le nom** | `test_les_identifiants_internes_sont_traduits` couvrait 3 vocabulaires sur 5 |
| **plus large que l'objet** | `test_session_opaque_csrf_et_invalidation` comparait le journal d'audit **entier** après `rotate()` et `destroy()` : il **gelait l'absence** de toute trace de fin de session, et cassait si on l'ajoutait |
| **tautologie** | un test du rejeu réimplémentait la sélection de `run_sync` puis vérifiait sa réimplémentation ; `isin` rendait l'assertion **impossible à faire échouer** |
| **faux positif** | le contrôle suivant comparait `str(pd.Timestamp)` à un champ **ISO 8601** : il accusait le rejeu d'avoir sauté un instant qu'il avait analysé |

### Les règles qui en découlent **[LU + audit]**

1. **N'importe pas ta propre réimplémentation.** Importe le prédicat réel.
2. **Aucun `grep` n'établit une absence** — les champs sont renommés en transit ;
   il faut suivre la donnée jusqu'à son point de rendu.
3. **Prouve par mutation** : réintroduis le défaut, montre l'échec, restaure.
4. **Un contrôle qui réussit d'autant plus sûrement qu'il ne lit rien ne contrôle
   rien.** Un `if` qui rend l'assertion facultative doit devenir un `skip` déclaré.
5. **Normalise avant de comparer** — accents, horodatages, formats. Sinon le
   contrôle mesure la mise en forme.
6. **Une union `A or B`** rend le test vrai sans rien garantir.
7. **Un contrôle dont le message ment quand il échoue est pire qu'absent** : il
   envoie corriger un défaut inexistant. Ne compare jamais des chaînes sensibles
   à l'indentation — passe par l'AST.

## 23.4 Les gardes documentaires **[LU + MESURÉ]**

`test_documentation.py` empêche la documentation de mentir. Trois contrôles :

- **chemins cités et inexistants** ;
- **liens morts** ;
- **chiffres publiés qui contredisent les artefacts** — confrontation à
  `reports/project_metrics.json`, `reports/judge_eval_summary.json` et à
  `domain.risk_coverage()`.

### Démonstration en conditions réelles, 8 août 2026 **[MESURÉ]**

La partie A de cette bibliothèque, **1 519 lignes produites par une autre
session**, a fait échouer ces deux contrôles au premier lancement :

1. quatre chemins cités sans leur préfixe `src/` ;
2. un décompte de points d'alarme presque **quatre fois** supérieur au mesuré
   (`alert_hours_historical = 530`), et un nombre d'épisodes annoncé « une
   dizaine » là où l'artefact en compte **58**.

**Le défaut n'était pas dans la bibliothèque** : elle citait mot pour mot la
docstring de `src/models/detector.py`. Et l'historique du contrôle raconte la
suite. La même grandeur était publiée deux fois, à trois lignes d'écart, sous
deux noms — « points d'alarme » et « heures atypiques » — et portait dans les
deux cas la valeur **511**, là où l'artefact en mesure **530**. La première
occurrence a été corrigée ; **la seconde a survécu en changeant de mot**, puis a
été « arrondie » à une valeur encore plus fausse. Un chiffre faux corrigé en un
chiffre plus faux.

*(Les deux valeurs historiques sont écrites ici détachées du terme qu'elles
qualifiaient. Accolées, elles se relisent comme une affirmation courante — et
c'est exactement ce qui a donné vingt lots de survie à la charge d'alertes
fautive. Le contrôle `test_aucun_chiffre_cle_ne_contredit_les_artefacts` refuse
l'adjacence, à juste titre : il n'a aucun moyen de distinguer ce qu'on affirme
de ce qu'on cite.)*

> **Anecdote qui vaut démonstration.** La première rédaction de la parenthèse
> ci-dessus citait la charge fautive en chiffres, accolée au mot « épisodes ».
> Le contrôle l'a rejetée — **la phrase qui explique le piège est tombée dedans
> en l'écrivant.** C'est la meilleure preuve que le garde-fou ne se satisfait pas
> des bonnes intentions de l'auteur, et qu'un contrôle par le texte doit être
> aveugle à l'intention pour valoir quelque chose.

C'est l'argument de gouvernance le plus solide du mémoire, parce qu'il n'est pas
une explication : **deux documents écrits sans coordination, et c'est l'artefact
mesuré qui a tranché** — ni le plus récent, ni le plus long, ni le plus assuré.

### Le corollaire, qui corrige un énoncé de la partie A

A affirme que sur dix-huit occurrences **sans exception**, « le code de service
porte la version juste, le document la version périmée ». L'épisode ci-dessus est
un contre-exemple : le code portait la version fausse — **dans une docstring**.

> **Énoncé corrigé : ce qui est exécuté reste juste ; ce qui est seulement lu
> dérive.** Commentaires et docstrings sont de la documentation qui habite le
> code : rien ne les exécute.

## 23.5 Les huit erreurs de l'auditeur **[MESURÉ]**

Un chapitre de validation honnête cite aussi les erreurs de la méthode.

| # | nature |
|---|---|
| 1 | extrapolation calculée sur le calendrier, non sur les heures de marche |
| 2 | nom de classe inféré ; il figurait 435 lignes plus haut dans le fichier |
| 3 | contenu d'un document affirmé sans l'avoir lu |
| 4 | prédicat de forme ; tests ajoutés à un fichier non lu |
| 5 | symétrie affirmée contre une causalité documentée |
| 6 | tautologie : le test vérifiait sa propre réimplémentation |
| 7 | comparaison de deux représentations au lieu de deux valeurs |
| 8 | `print` de fin de script pris pour une vérification — `str.replace` ne lève pas quand il ne trouve rien |

**Sept sur huit ont été trouvées par la lecture intégrale, aucune par
l'exécution.** C'est l'argument empirique en faveur de la méthode d'audit
retenue, et la raison pour laquelle la suite verte de ce dépôt ne suffisait pas.

---

# 24. Le déploiement

`Dockerfile` (95 l.), `docker-compose.yml` (128), `.github/workflows/ci.yml`
(209), `Makefile` (135), `requirements-runtime.lock` (46) et
`scripts/validate_release.py` (89).

## 24.1 Deux environnements distincts, et ils le restent **[LU]**

| fichier | rôle | cible |
|---|---|---|
| `requirements.txt` | développement et analyse complets | **Python 3.10+** |
| `requirements-runtime.txt` | dépendances d'exécution, non figées | — |
| `requirements-runtime.lock` | **versions exactes**, dérivées du précédent | **Python 3.11** |

> Le verrou **n'est pas installable sur 3.10**, et c'est assumé : l'image Docker
> installe le `.lock`, le poste de développement installe `requirements.txt`.
> Confondre les deux produit une erreur de résolution immédiate, ce qui vaut
> mieux qu'une divergence silencieuse de versions entre le poste et le serveur.

## 24.2 L'image — deux étapes, aucun compilateur à l'arrivée **[LU]**

La construction est en **deux étapes**. Les roues scientifiques sont compilées
dans une image jetable qui embarque `gcc` et `g++` ; seul l'environnement virtuel
résultant est copié dans l'image finale. Celle-ci ne contient donc **ni
compilateur ni en-têtes de développement** — moins de surface d'attaque, image
nettement plus légère.

Quatre décisions à retenir :

**L'application ne tourne jamais en root.** Un utilisateur dédié, uid 10001,
shell `nologin`. *Un service de supervision n'a aucune raison de disposer des
droits d'administration de la machine.*

**Les données et les modèles sont montés en volume**, pas embarqués : l'export
DCS évolue indépendamment du code, et l'image ne doit pas transporter quatorze
mois d'exploitation OCP.

**Un seul worker, et la raison est écrite.** La chaîne charge l'historique
complet et entraîne le modèle au démarrage, **en mémoire**. Plusieurs workers
dupliqueraient ce travail et ce modèle sans aucun gain — la charge de ce service
est très inférieure à ce qu'un seul processus absorbe (**45 analyses par
seconde** mesurées, pour un équipement échantillonné à l'heure).

**Le point d'entrée honore la configuration.** Une version précédente écrivait
l'hôte et le port en dur dans le `CMD` : *les variables prévues pour les régler
n'avaient alors aucun effet.*

### La sonde du conteneur, et le piège qu'elle a évité

C'est le défaut le plus coûteux de ce fichier, et il découle directement de la
gouvernance décrite en § 19.5.

> Une version précédente exigeait `"status":"ok"` dans `/api/health`. Or ce
> statut est **inatteignable par construction** : il vaut `degraded` dès lors que
> le modèle n'est pas promu, et **aucun modèle ne peut l'être** —
> `build_manifest` écrit toujours `candidate`, absent de
> `MODEL_ALLOWED_STATUSES`.
>
> **Le conteneur livré était donc marqué `unhealthy` en permanence**, et un
> orchestrateur l'aurait retiré de la rotation ou redémarré en boucle.

La sonde porte désormais sur `/api/health/ready`, avec `start-period=90s` — le
temps de charger l'historique et d'entraîner le modèle. *La disponibilité du
service et la promotion du modèle sont deux questions distinctes* : la première
est `/api/health/ready`, la seconde `/api/health/model`.

C'est la même distinction qui structure les portes de déploiement, appliquée à
l'infrastructure.

## 24.3 L'intégration continue — quatre étages **[LU]**

```
  qualite ──┐
  tests   ──┼──► image
  frontend ─┘
```

| étage | ce qu'il fait | bloquant ? |
|---|---|---|
| **qualite** | analyse statique | **oui** |
| — typage | mypy | **non** — `continue-on-error: true`, déclaré informatif |
| **tests** | suite complète sur matrice de versions Python | **oui** |
| — Judge | banc de pièges, 6 cas | **oui**, sur trois critères |
| — validation | `validate_release.py` | **oui**, sur les portes **logicielles** |
| **frontend** | fixtures régénérées depuis le service réel, puis les 3 bancs jsdom | **oui** |
| **image** | construction, démarrage du conteneur, réponse vérifiée | **oui** — dépend des trois autres |

**Le banc du Judge est bloquant sur des seuils explicites** :
`trap_success_rate ≥ 0,85`, `false_positive_rate ≤ 0,20`, `separation ≥ 2,0`. Ce
sont des garde-fous de non-régression, pas des mesures de performance — et le
troisième est le seul non borné par construction, donc le seul qui discrimine.

**Les fixtures du front sont régénérées depuis le service réel avant les bancs.**
C'est ce qui empêche les 98 vérifications de § 17.7 de tourner sur des données
figées qui ne correspondraient plus à ce que l'API sert. Sans cette étape, les
bancs vérifieraient la cohérence du poste avec un contrat périmé.

**Les preuves sont publiées en artefact**, 90 jours de rétention :
`reports/model_validation.json` et le manifeste du modèle, avec
`if-no-files-found: error` — *une preuve absente doit faire échouer la
publication, pas passer inaperçue*.

## 24.4 Ce qui bloque une fusion, et ce qui se publie sans bloquer **[LU]**

C'est le point que la consigne désigne, et il est le prolongement direct de
§ 19.5.

`validate_release.py` publie **les deux listes** et n'en fait décider **qu'une** :

```python
bloquantes = failed_software_gates(validation)   # 3 portes
# failed_mandatory_gates(validation)             # 5 portes, publiées
```

Le défaut corrigé mérite d'être cité en entier, parce qu'il montre ce que coûte
une confusion de natures :

> Le code de retour portait sur les **cinq portes de promotion**, dont
> `labels_gmao` et `validation_externe`, qui exigent un historique de pannes
> étiqueté. Ce script étant appelé par l'intégration continue **sans
> `continue-on-error`**, le job `tests` échouait à chaque exécution et le job
> `image`, qui en dépend, **n'était jamais construit**.
>
> **La chaîne était rouge par construction, et aucun commit ne pouvait la rendre
> verte.**

| ensemble | portes | ce qu'il décide |
|---|---|---|
| `MANDATORY_GATES` | **5** | la **promotion** d'un artefact — `promote_model.py` et `validate_model_manifest` les exigent toutes, inchangés |
| `SOFTWARE_GATES` | **3** | le **code de retour de la CI** — ce qu'un commit peut casser |

> **Le principe, et il vaut pour tout le projet** : on ne restreint pas un
> critère pour qu'il passe — cela **remasque** ce que l'auteur avait délibérément
> rendu visible. On sépare ce qu'un développeur peut corriger de ce qu'OCP n'a
> pas fourni, on publie les deux, et on ne bloque que sur le premier.

Une chaîne rouge en permanence n'est pas une chaîne exigeante : c'est une chaîne
que l'équipe apprend à ignorer.

## 24.5 Ce que la section 24 ne permet pas d'affirmer

- que le système ait été **déployé** — l'image est construite et démarrée en CI ;
  elle n'a jamais tourné sur une infrastructure OCP ;
- que la **production soit autorisée** — le service refuse de se déclarer
  `ready_for_production` tant que `APP_ENV != production` **et** que le modèle
  n'est pas promu, ce qui est définitivement impossible sur ce corpus ;
- que l'**identité soit gérée** — le démarrage reste bloqué en production tant
  que le fournisseur IAM OIDC de l'entreprise n'est pas intégré. Le registre local
  est un mécanisme de démonstration mono-poste ;
- que le **dépôt soit publiable** — `data/raw/DATA.xlsx` est versionné
  délibérément, et il porte quatorze mois d'exploitation réelle d'une
  installation OCP. **Le dépôt distant doit rester privé** : ce n'est pas une
  préférence, c'est la condition qui rend acceptable le choix de versionner
  l'export ;
- que les **45 analyses par seconde** soient une mesure de charge en exploitation
  — c'est un débit mesuré sur le poste de développement, sur des données déjà
  chargées en mémoire.
