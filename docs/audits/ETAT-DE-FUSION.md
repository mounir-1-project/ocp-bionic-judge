# État de fusion des bibliothèques — verdict mesuré, 8 août 2026

**Question posée : une session neuve, n'ayant pas lu le projet, peut-elle
produire un rapport parfait à partir des bibliothèques existantes ?**

**Non.** Cinq obstacles, mesurés, pas estimés.

> **Mise à jour du 8 août, après la passe de cohérence.** Les obstacles **1, 2 et
> 3 sont levés et vérifiés** ; **4 et 5 demeurent** et demandent des sessions
> dédiées. Détail en fin de document.

## 1. Le fil conducteur existe en trois versions incompatibles — dont deux dans le même fichier

C'est le défaut le plus grave, parce qu'il porte sur **l'argument central du
rapport**.

| document | ligne | énoncé |
|---|---|---|
| `docs/bibliotheque/partie-A.md` | 1535 | « **sans exception** : le code de service porte la version juste » |
| `docs/bibliotheque/partie-audit.md` | **700** | « Ordre de fraîcheur constaté, **sans exception notable** » |
| `docs/bibliotheque/partie-audit.md` | **706** | « **Deux exceptions** seulement sur 18 (S27-2, S32-1) » |
| `docs/bibliotheque/dossier-rapport.md` | 116 | « Deux exceptions seulement sur 18 » |
| `docs/bibliotheque/partie-B.md` | 169 | énoncé **corrigé** : *ce qui est exécuté reste juste, ce qui est seulement lu dérive* |

Les lignes 700 et 706 sont **dans le même document, à six lignes d'écart, et se
contredisent**. C'est exactement le défaut que ces quarante-six lots ont
documenté, commis dans le document écrit pour l'empêcher.

**Version à retenir** — la seule compatible avec la mesure du lot S46 :

> **Ce qui est exécuté reste juste. Ce qui est seulement lu dérive.**
> Trois exceptions connues à l'ancienne formulation : S27-2, S32-1, S46-1.

À corriger **à chaque occurrence**, pas en annexe.

## 2. Le coefficient de corrélation a deux précisions

`−0,938` (1 fois, partie A — c'est le titre de la figure à produire) contre
`−0,94` (9 fois en A, 2 fois dans `docs/bibliotheque/partie-audit.md`, 1 fois dans
`docs/bibliotheque/dossier-rapport.md`). Trancher sur la valeur de l'artefact, puis unifier.

## 3. Chaque bibliothèque ignore des chiffres de l'autre

| chiffre | partie A | mes documents |
|---|---|---|
| couverture du risque **30,2 %** | 4 occurrences | **absent** |
| généralisation **95,8 %** (le contraste avec 8,6 %) | **absent** | 3 occurrences |
| **58 épisodes** (total) | 1 | absent du tableau des chiffres |

Une session qui lit l'une des deux écrira un rapport incomplet sans le savoir.

## 4. Sept chapitres sur huit n'existent pas

Seule la section **23** de la partie B est écrite. Manquent 17 (interface),
18 (API), 19 (validation modèle), 20 (alarmes), 21 (notifications),
22 (rejeu et sécurité), 24 (déploiement).

**5 160 lignes de front n'ont jamais été ouvertes** — et c'est le chapitre que le
jury manipulera.

## 5. Aucune des douze figures n'existe

Dont la plus importante : le nuage **résidu de duty × écart de consigne**, qui
montre en un coup d'œil que l'indicateur de la v2 était l'écart de consigne
réécrit. C'est l'argument qui justifie toute la refonte, et il n'est pas
illustré.

---

## Ce qu'une session neuve PEUT écrire aujourd'hui

Sans rien relire du code : les **chapitres scientifiques et de gouvernance** —
ADR-001 et ADR-002, le corpus et sa qualité, l'AMDEC, les portes de déploiement,
le backtest et le PSI, la stratégie de validation logicielle (section 23), les
limites déclarées. C'est substantiel, et c'est le cœur intellectuel du mémoire.

## Ce qu'elle ne peut pas écrire

La réalisation, le contrat d'API détaillé, les figures. Autrement dit : **tout ce
qui montre que le système existe.**

## Ordre recommandé

1. **Fusionner et dédupliquer** les trois bibliothèques en résolvant les cinq
   points ci-dessus. Une demi-session. À faire **avant** d'écrire quoi que ce
   soit, sinon la contradiction se propage dans le rapport.
2. **B1 — l'interface** (`twin.js`, `dashboard.html`, ADR-008). Une session.
3. **B2, B3, B4** puis **B5, B6, B8 + les figures**. Deux sessions.


---

# PASSE DE COHÉRENCE — 8 août 2026, résultat vérifié

## Levé — 1. Le fil conducteur est unifié

`« sans exception »` : **0 occurrence** dans les trois documents (3 avant).
`« Ce qui est exécuté reste juste »` : **exactement 1 occurrence dans chacun des
quatre documents**. Un énoncé, une place, partout le même :

> **Ce qui est exécuté reste juste. Ce qui est seulement lu dérive.**
> 18 occurrences ; **trois exceptions — S27-2, S32-1, S46-1** — et la troisième
> reformule la règle : la frontière n'est pas code / document, elle est
> **exécuté / seulement lu**.

La contradiction interne de `docs/bibliotheque/partie-audit.md` (lignes 700 et 706, à six lignes
d'écart) est supprimée.

## Levé — 2. Le coefficient est unifié

`−0,938` partout, avec « (arrondi −0,94) » là où le texte courant l'exige.
C'est la valeur qui titre la figure à produire.

## Levé — 3. Les chiffres manquants sont croisés

Ajoutés au tableau de `docs/bibliotheque/partie-audit.md` : **couverture du risque AMDEC 30,2 %**,
**58 épisodes agrégés**, **530 heures atypiques**. Le contraste **8,6 / 95,8 %**
reste à porter dans la partie A.

## Levé — 4a. Le front est lu, et la section 17 est écrite *(8 août 2026)*

`dashboard.html` (586), `app.js` (2 445), `twin.js` (2 167), `app.css` (1 167) et
ADR-008 ont été **lus intégralement**. La section **17 — La réalisation, le poste
opérateur** est écrite : 10 sous-sections, 18 marqueurs de provenance, aucun
`[DÉCLARÉ]`.

Chiffres produits par `scripts/collecte_chiffres_front.py` →
`reports/chiffres_front.txt`. Acquis principaux :

| grandeur | mesure |
|---|---|
| périmètre réel du front | **6 365** lignes, et non 5 160 (`app.css` manquait au décompte) |
| vues / cartes | 3 / 23 |
| familles de signaux | 10, en correspondance exacte HTML ↔ JS |
| pièces 3D vs référentiel | **10 / 10, zéro écart dans les deux sens** |
| tubes instanciés | **1 541** |
| routes servies / consommées / fantômes | 47 / 32 / **0** |
| routes orphelines | **14**, dont 5 sondes d'orchestrateur et **5 pour `workflows`, sans interface** |
| identifiants page / cherchés / manquants | 110 / 99 / **0** |
| bancs du poste | **98/98** en 3,7 s |

**Trois assertions chiffrées du front étaient fausses, et sont corrigées à la
source** : « 57 épisodes sur 59 » (58), « 849 lignes, six routes » (952, deux),
ADR-008 « 4,6:1 » (4,54:1). Une reste ouverte — **UI-1**, le rang du motif
d'audit : le front se dit 19ᵉ occurrence, les tableaux en recensent 18.

## Levé — 4c. Les sections 18 et 19 sont écrites *(8 août 2026)*

`api/main.py` (1 830 l.) et `src/governance/model_validation.py` (834 l.) ont été
**lus intégralement**. Chiffres produits par `scripts/collecte_chiffres_api.py` →
`reports/chiffres_api.txt`, et relus dans `reports/model_validation.json`.

**§18 — Le contrat d'API.** Acquis :

| grandeur | mesure |
|---|---|
| routes | 47 couples verbe+chemin, 46 chemins, 11 familles |
| handlers calculant sur la boucle d'événements | **0** — la règle tient |
| routes exigeant un rôle | 10 sur 47 |
| paramètres bornés | 19 |
| champs servis / jamais lus par l'écran | 79 / **35**, dont 11 sur des routes métier |

**Trouvaille de §18** : `/api/equipment` sert `process_states` — les trois
définitions `RUNNING` / `TRANSIENT` / `STOPPED` — précisément parce que
« l'exploitant n'avait aucun moyen de savoir quel critère l'avait déclenché ».
**Le serveur a été corrigé, l'écran ne l'a jamais été.** Même chose pour
`status_reason`, ajouté pour qu'un jury lise *pourquoi* le service est `degraded`.
Vingtième occurrence du motif — et la première où l'affichage porte une
**absence** plutôt qu'une valeur fausse, ce qu'aucun banc de rendu ne peut
attraper.

**§19 — La validation du modèle.** Acquis : le plan d'expérience (4 plis, fenêtre
croissante, écart causal mesuré à 25 h et non 24), la construction du PSI et sa
correction d'epsilon, `seasonal_extrapolation`, et **l'origine de chacun des sept
seuils de porte**. Un seul est importé d'un autre domaine — le 0,25 du PSI, venu
du scoring de crédit — et le dépôt l'écrit à l'écran.

**Correction propagée** : les valeurs de PSI **d'avant** la correction d'epsilon
— « 1,989 / 3,745 » et « 73,8 / 100 / 5,9 / 0 % » — survivaient dans **quatre
endroits**, dont le commentaire de `model_validation.py` lui-même, à vingt lignes
du code qui implémente la correction. Valeurs réelles : **1,988 / 3,183 / 0,580 /
0,068** et **76,5 / 100 / 5,2 / 12,8 %**. Corrigées à chaque occurrence.

> `partie-audit.md` § 5.3 se contredisait **à dix lignes d'écart** : son tableau
> annonçait 0 % d'extrapolation sur le pli 4, son propre paragraphe suivant
> annonçait 12,8 % en expliquant que le 0 % était une erreur de calcul. Le texte
> portait la correction, le tableau non.

## Demeure — 4d. Quatre chapitres

Manquent **20** (alarmes), **21** (notifications), **22** (rejeu et sécurité),
**24** (déploiement).

§ 17.6 et § 18.7 leur laissent deux prises fermes : le module `workflows` est
servi et testé **sans aucune interface**, et `POST /api/auth/refresh` n'est
appelé par personne. § 17.8 en laisse une troisième : `alarms.py` fait **617**
lignes et non 561 — `docs/bibliotheque/partie-audit.md` et la consigne B4
portent tous deux la valeur périmée. **§20 doit partir de la mesure, pas de la
consigne.**

## Demeure — 5. Les figures

Aucune n'existe. La plus importante — nuage **résidu de duty × écart de consigne,
r = −0,938** — est l'argument qui justifie la refonte, et elle n'est pas illustrée.

§ 17.9 signale un **conflit de numérotation** : la figure 12 de la partie A est
déjà la capture de la vue Salle. La partie B la reprend en la précisant et
n'ouvre de nouveaux numéros qu'à partir de 13, pour ne pas la produire deux fois.

---

## Verdict, en une phrase

La bibliothèque est désormais **cohérente, honnête, et elle porte la
réalisation** : le poste opérateur est décrit, mesuré et vérifié (§ 17). Restent
six chapitres et les figures. Ce qui manque n'est plus « tout ce qui montre que
le système existe » — c'est le **contrat de service** derrière l'écran.

## Ce que la session du 8 août a ajouté au fil conducteur

Le motif était établi sur dix-huit occurrences, toutes trouvées côté serveur et
côté documents. § 17.8 le mesure pour la première fois **sur un périmètre
entier, dans les deux natures à la fois** :

> Sur les 65 assertions chiffrées portées par les **commentaires** du poste,
> **trois sont fausses et une est indéterminée** — 4,6 à 6,2 %.
> Sur les grandeurs **exécutées** du même périmètre — constantes de géométrie,
> seuils de dégradation, poids, tailles d'étiquette — **aucune** ne l'est ; 98
> assertions de banc les tiennent.

Ce n'est plus une régularité observée sur des cas choisis : c'est un **taux
d'erreur comparé, sur le même fichier, entre ce qui s'exécute et ce qui se lit**.
C'est l'argument le plus fort dont dispose le mémoire pour justifier sa
gouvernance, et il vient du seul terrain que l'audit n'avait pas visité.
