# Consigne pour la bibliothèque B

À la session qui produit la seconde moitié de la bibliothèque du mémoire E7301.

La **partie A** existe : `docs/BIBLIOTHEQUE-RAPPORT-partieA.md`, 2 316 lignes.
Lis-la avant de commencer — pas pour la refaire, pour savoir où elle s'arrête.
Les deux parties seront fusionnées, et **toute redite créera une contradiction**
le jour où l'une des deux sera corrigée et pas l'autre. C'est le défaut central
que tout l'audit de ce dépôt a documenté ; ne le réintroduis pas dans sa
documentation.

---

## 1. Ce que la partie A couvre déjà — n'y reviens pas

| section A | contenu |
|---|---|
| 0 | le problème, les trois questions de l'exploitant, ce qui est revendiqué et ce qui ne l'est pas |
| 1–2 | équipement, corpus, les 12 tags, la qualité de donnée, les états procédé |
| 3 | **ADR-001** (circularité du duty) et **ADR-002** (climatologie), efficacité-NTU, UA apparent |
| 4 | architecture de la chaîne, référentiel gouverné, mise en forme française |
| 5 | les 11 features, les 3 références, les fenêtres |
| 6 | les deux étages de détection, les 15 règles, l'Isolation Forest, l'occlusion |
| 7 | **l'AMDEC intégrale** — 13 modes, barèmes, couverture 30,2 %, plan A–H |
| 8 | les deux agents, les 8 contrôles et leurs poids, l'auto-surveillance |
| 9 | les 3 bancs de gouvernance, le lignage, les 5 portes |
| 10 | workflows, registre technicien, configuration |
| 11 | les indicateurs d'exploitation |
| 12 | la méthode d'audit, le « patron », les motifs découverts |
| 13 | les 10 limites du projet |
| 14 | barème de confiance, contrats de données, glossaire, **12 figures à produire**, chronologie |
| 15 | **RÉSULTATS MESURÉS** — exécution complète du 2026-08-07 |
| 16 | 6 recommandations, chacune adossée à un chiffre |

**Fichiers lus intégralement pour A** : `formatting`, `config`, `pipeline`,
`knowledge` + les 3 YAML, `dcs_loader`, `thermal`, `e7301_features`, `detector`,
`detection_agent`, `judge_agent`, `judge_eval`, `fouling_injection`,
`sensitivity`, `lineage`, `promote_model`, `kpi`, `workflows`, `registry`.

---

## 2. Ce que la partie B doit contenir

Sept chapitres. Chacun manque **entièrement** — un mémoire ne peut pas être
soutenu sans eux.

### B1. La réalisation — l'interface **(le plus important)**

C'est **le chapitre que le jury manipulera**, et il n'existe aucune matière.
5 160 lignes jamais ouvertes : `api/static/app.js` (2 407),
`api/static/twin.js` (2 167), `api/dashboard.html` (586). Lis aussi
**ADR-008 « Interface conforme aux principes ISA-101 »** (91 l.), dont A ne
connaît que le titre.

À produire :

- **l'inventaire des vues** — combien, lesquelles, ce que chacune montre, dans
  quel ordre un exploitant les parcourt ;
- **la conformité ISA-101** : que dit la norme, qu'est-ce que le poste en
  applique concrètement (hiérarchie des niveaux, codage de la sévérité, charte
  de couleurs, absence d'ornement) ;
- **le jumeau 3D** : ce qu'il rend, comment `finding_map` allume une pièce,
  comment le tiroir capteur s'ouvre, la résolution des collisions d'étiquettes ;
- **les familles de signaux** du menu Signaux et ce que chacune trace ;
- **les captures d'écran**, au moins quatre : vue Salle avec le jumeau, carte de
  diagnostic, tableau AMDEC, panneau d'auto-surveillance du contrôleur.

Vérifie **route par route** que ce que le serveur sert est rendu et que ce que
l'écran affiche existe. Trois écarts de ce type ont déjà été trouvés par A ;
ils ont été trouvés depuis le serveur, jamais depuis l'écran.

### B2. Le contrat d'API

`api/main.py`, 1 759 lignes, **47 routes** dont A ne connaît que la liste. À
produire : les familles, la signature et le schéma de réponse de chaque route
utile au rapport, le flux d'authentification (login → cookie → CSRF → refresh →
rotation), le **flux de rejeu** (`/api/replay/stream`) et son mécanisme, les
**six sondes de santé** et à quoi chacune correspond côté orchestrateur.

Signale les **routes orphelines** — servies et consommées par personne — et les
**champs orphelins** dans les réponses.

### B3. La validation du modèle

`src/governance/model_validation.py`, 592 lignes. A dispose des **résultats**
mesurés (§ 15.8) mais ignore **comment ils sont construits**. À produire :

- la construction du **backtest temporel** : pourquoi 4 plis, pourquoi une
  fenêtre croissante, pourquoi un **écart causal de 25 h** ;
- ce que `causal_pipeline_refit = True` vérifie exactement ;
- le calcul du **PSI** et celui de `seasonal_extrapolation` — c'est la seconde
  qui explique la première, et A l'a établi par corrélation sans lire le code ;
- les **sept portes** : ce que chacune calcule, avec ses seuils et leur origine.
  A signale que le seuil PSI de **0,25 vient du scoring de crédit** ; dis
  précisément d'où vient chacun des autres.

### B4. Les alarmes ISA-18.2

`src/operations/alarms.py`, 561 lignes. À produire : le cycle de vie complet,
le schéma SQLite, la **clé de déduplication** (`_key`) et le déclencheur
(`_trigger`), l'anti-rebond, l'inhibition (*shelving*), le journal d'audit — et
ce que la norme ISA-18.2 exige d'un système d'alarmes.

**Constat ouvert depuis la phase 0, à trancher** : le registre nomme l'alarme
d'après le capteur, et une alarme peut ne jamais se résoudre. Correctif
identifié, jamais appliqué.

### B5. Notifications et escalade

`src/notifications/email.py` (512) et `redaction.py` (294). À produire : le
canal d'escalade, le filtre de sévérité (`ALERT_MIN_SEVERITY`), l'anti-rebond
de 60 min, le **dépôt local des escalades** qui sert de preuve de passage quand
aucun relais n'est configuré, et surtout **ce que la rédaction expurge et
pourquoi** — c'est un sujet de gouvernance, pas de mise en forme.

### B6. Le rejeu temps réel et la sécurité

`src/realtime/replay.py` (430) et `src/security/auth.py` (300).

Pour le rejeu, une vérification prioritaire : le système promet qu'**« à
l'instant t, seule la fenêtre [début, t] est transmise à la détection »**.
Vérifie-la **ligne à ligne** — deux lectures du futur ont déjà été trouvées et
corrigées ailleurs dans la chaîne (détection de gel, classification d'état).

Pour l'authentification : sessions, CSRF, rotation de jeton, expiration par
inactivité (30 min) et absolue (8 h). A couvre déjà le **registre** technicien
(`registry.py`) — ne le refais pas.

### B7. La stratégie de validation logicielle

**310 tests, 20 fichiers, 7 201 lignes**, dont A n'a lu que deux. C'est un
chapitre à part entière d'un mémoire d'ingénieur. À produire :

- la répartition et ce que chaque famille verrouille ;
- **le « patron »** — les tests qui interdisent la réapparition d'un défaut par
  analyse du source. A en recense neuf ; recense-les tous et explique le
  procédé, c'est une **contribution méthodologique** du projet ;
- `test_typographie.py` : le lexique, et le **garde-fou qui teste le détecteur
  lui-même** ;
- `test_documentation.py` : les contrôles qui empêchent la documentation de
  mentir (chemins cités, liens morts, **chiffres contredisant les artefacts**) ;
- la **couverture de code** mesurée, pas estimée.

### B8. Le déploiement

`Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`, `Makefile`,
`requirements-runtime.lock`. À produire : la chaîne d'intégration, ce qui bloque
une fusion et ce qui se publie sans bloquer (A explique la séparation des
portes en deux natures, § 9.4), la construction de l'image, la procédure de
publication d'un artefact.

---

## 3. Ce que B doit **mesurer**, pas décrire

A a appris une leçon coûteuse : **quatre chiffres cités dans les commentaires
du code sont contredits par l'exécution** — « cinq fois la contamination » vaut
3,00 ×, « dépasse 40 % » vaut 26,9 %, « 1 385 heures d'arrêt » vaut 1 251,
« ~5 épisodes/mois » vaut 4,10.

**Ne reprends aucun chiffre d'un commentaire sans l'avoir recalculé.**

Le script `scripts/collecte_chiffres_rapport.py` montre le procédé : treize
blocs isolés, sortie dans `reports/chiffres_rapport.txt`. Écris l'équivalent
pour ton périmètre. Il te faut au minimum :

- la **couverture de code** réelle (`pytest --cov`), par module ;
- le **temps d'exécution** de la suite, et celui d'une analyse d'instant ;
- la **latence** d'une requête sur les routes principales ;
- le résultat des **bancs `.mjs`** qui vérifient le poste ;
- le nombre de vues, de composants 3D, de familles de signaux — comptés, pas
  estimés.

---

## 4. Les conventions à respecter, pour que la fusion tienne

### Marqueurs de provenance, sur chaque affirmation

- **[LU]** — établi par lecture intégrale du fichier. Cite la ligne.
- **[MESURÉ]** — issu d'une exécution. Cite la date et la commande.
- **[DÉCLARÉ]** — le dépôt l'affirme, tu ne l'as pas recalculé. À éviter : si
  c'est mesurable, mesure-le.

A porte ces marqueurs partout. Une fusion qui les efface rend la bibliothèque
invérifiable, et le mémoire redevient un texte qu'on croit sur parole.

### Corriger là où ça se lit, pas en annexe

Piège dans lequel A est tombé et dont elle est sortie : signaler en annexe qu'un
chiffre est faux **ne suffit pas**. Un rédacteur lit dans l'ordre, prend le
premier chiffre, et n'atteint jamais le démenti. **Corrige à chaque
occurrence**, et garde le tableau des divergences comme trace, pas comme
correctif.

### Numérote à partir de 17

A occupe les sections 0 à 16. Commence à **17** pour que la concaténation soit
directe. Structure suggérée :

```
17. La réalisation — le poste opérateur
18. Le contrat d'API
19. La validation du modèle
20. Les alarmes ISA-18.2
21. Notifications et escalade
22. Rejeu temps réel et sécurité
23. La stratégie de validation logicielle
24. Le déploiement
25. Résultats mesurés — partie B
26. Bibliographie
27. Les figures produites
```

### Deux livrables transverses qui n'appartiennent à personne

**Les figures.** A en liste **douze** avec leur source (§ 14.5) ; **aucune
n'existe** — `rapport/figures` a été sorti du dépôt en phase A. Produis-les. La
plus importante est le **nuage résidu de duty × écart de consigne, r = −0,938** :
elle montre en un coup d'œil que l'indicateur de la v2 était l'écart de consigne
réécrit, et c'est l'argument qui justifie toute la refonte.

**La bibliographie.** Sources identifiées par A, jamais référencées : Perry
*Chemical Engineers' Handbook* (propriétés de H₂SO₄ 98 %), Dittus-Boelter
(exposant 0,8 sur Reynolds), **ISA-5.1** (nomenclature d'instrumentation),
**ISA-18.2** (gestion des alarmes), **ISA-101** (conception des IHM). Ajoute les
tiennes.

---

## 5. Une dernière chose

Ce dépôt est traversé par un motif que l'audit a documenté sur **dix-huit
occurrences sans exception** : quand une correction n'est portée qu'à un
endroit, c'est **le code de service qui porte la version juste et l'affichage ou
le document qui porte la version périmée**.

Ta partie est celle de l'affichage. C'est statistiquement là que se trouvent les
écarts restants — et A ne les a pas cherchés, faute d'avoir ouvert un seul
fichier du front.
