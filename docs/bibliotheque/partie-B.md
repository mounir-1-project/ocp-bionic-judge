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
| `test_alarm_store.py` | 291 | cycle de vie ISA-18.2 |
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
