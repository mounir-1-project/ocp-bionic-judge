# Reprise de la relecture intégrale de `src/` — passation

Copie ce fichier entier comme premier message à l'IA qui reprend.

---

Tu reprends la relecture ligne à ligne d'un dépôt Python à
`C:\dev\ocp-bionic-judge`, sur un poste **Windows / PowerShell**. Onze lots ont
déjà été traités. Il en reste quatre. Ce document te dit ce qu'est le projet,
ce qui a été fait, comment on travaille ici, et ce qui t'attend.

Tu es attendu comme un expert. Le dépôt est destiné à un mémoire de fin
d'études et à une soutenance devant un jury industriel : chaque chiffre publié
doit pouvoir être défendu, et chaque affirmation du code doit être vraie.

---

## 0. LIS LES FICHIERS EN ENTIER. C'EST LA CONSIGNE CENTRALE.

Le propriétaire du dépôt l'a exigée **sept fois** en deux sessions. Elle a été
tenue sur onze lots. Elle n'est pas négociable, et voici ce qu'elle signifie
concrètement, parce que la formule est facile à contourner sans le vouloir.

**Ce que « lire entièrement » veut dire :**

- Tu ouvres le fichier avec **un seul appel de lecture, sans `offset` ni
  `limit`**, du début à la fin. Un fichier de 1 759 lignes se lit en une fois.
- Tu **annonces le nombre de lignes lues** au début de ton compte rendu :
  « `api/main.py` lu intégralement — 1 759 lignes ». C'est ta signature, et
  c'est vérifiable.
- Tu lis **avant** de chercher. Pas de `grep` exploratoire pour « voir où ça se
  passe » puis lecture des seuls extraits trouvés. Le `grep` sert **après**, à
  suivre une donnée jusqu'à son point de rendu.

**Ce qui NE compte PAS comme une lecture entière :**

- lire les 200 premières lignes et les 200 dernières ;
- lire par tranches successives en croyant que la somme équivaut au tout — elle
  n'équivaut pas, parce qu'on perd le fil entre deux appels et qu'on ne voit
  plus les contradictions à distance ;
- lire seulement les fonctions que `grep` a signalées ;
- lire les docstrings et survoler les corps.

**Pourquoi cette consigne, et pas une autre.** Les défauts les plus graves
trouvés dans ce dépôt étaient invisibles en lecture partielle, parce que ce
sont des **contradictions à distance** :

- un commentaire ligne 169 qui énonce un principe, trois méthodes lignes
  292-346 qui le violent (SEC-1) ;
- une docstring de `thermal.py` qui déclare un autre module non divergent,
  alors que ce module recopie la formule sans sa garde (S8-1) ;
- un en-tête de module qui cite comme exemple un chiffre qu'une méthode
  cinquante lignes plus bas explique avoir supprimé (S10-1) ;
- un `__init__` qui fixe une graine « pour la reproductibilité » et trois
  lignes plus bas un appel qui laisse un LLM décider (S6-1).

Aucun de ces défauts n'apparaît dans un extrait. Ils n'apparaissent que quand
on a **tout le fichier dans la tête en même temps**.

**Gestion de ton contexte.** Si tu sens que la place manque, **ne commence pas
un fichier que tu ne pourras pas finir**. Termine ton lot, écris ton compte
rendu, consigne dans le journal, et dis franchement au propriétaire qu'il faut
une session neuve. C'est ce qui a été fait à la fin du lot S11 — c'est un
comportement attendu, pas un échec.

---

## 0 bis. Ce qu'il attend À LA FIN — les trois objectifs d'origine

La relecture de `src/` est un **moyen**. Voici la commande initiale, mot pour
mot dans son intention :

1. **Des fichiers et des dossiers bien structurés, sans rien de superflu.**
   Une phase A a déjà retiré quatre scripts morts, trois dépendances inutiles
   (`pypdf`, `Pillow`, `python-docx`) et sorti 16 Mo de binaires du dépôt vers
   `$HOME\Documents\E7301-archive`. À toi de finir : plus aucun fichier qui ne
   serve à rien, plus aucun nom qui mente sur son contenu.

2. **UN RAPPORT COHÉRENT AVEC LE PROJET RÉEL** — « quitte à le supprimer et le
   refaire », a-t-il dit. C'est `docs/rapport_technique.md`, appuyé par
   `docs/architecture.md`, les ADR de `docs/decisions/`, le README et
   `notebooks/01_analyse_E7301.ipynb`. Une phase D a déjà réaligné le § 5.3,
   les annexes A et B (11 features), les figures et quatre ADR. **Mais onze
   lots de corrections ont eu lieu depuis** : chaque suppression de surface
   morte, chaque `evidence_level` requalifié, chaque chiffre de banc dont le
   dénominateur a changé doit être répercuté. C'est le livrable final, et c'est
   celui sur lequel le jury te lira.

3. **CHAQUE PAGE DE L'INTERFACE DOIT FONCTIONNER**, back-end et front-end.
   Le poste est dans `api/dashboard.html` + `api/static/app.js` (~2 300 l.) +
   `api/static/twin.js` (jumeau 3D three.js). Vérifie **route par route** que
   ce que le serveur sert est rendu, et que ce que le front affiche existe
   côté serveur. Trois écarts de ce type ont déjà été trouvés : `T_SEAWATER`
   avec un libellé au front et aucune route pour le servir, une colonne
   `observabilite` publiée par le serveur et lue en booléen par l'écran, un
   libellé « grandeur dérivée » qu'aucune figure ne pouvait déclencher.

**Et une exigence de fond : tu dois MAÎTRISER ce projet.** Il finira la
soutenance avec toi. Tu dois pouvoir répondre sans hésiter à « pourquoi UA et
pas le duty ? », « d'où vient le 0,25 du PSI ? », « que vaut vraiment le taux
de généralisation du Judge et pourquoi est-il si bas ? ». Si tu ne sais pas,
va lire — ne devine pas.

---

## 1. Le projet

**E7301** est le refroidisseur d'acide sulfurique de séchage de l'atelier
PS III, Maroc Chimie, groupe OCP (Safi, Maroc). Échangeur Chemetics à faisceau
tubulaire, SIZE 1118-9754, tubes 904L, **eau de mer côté tubes, acide côté
calandre**. Le dépôt construit une chaîne de surveillance par les données sur
14 mois d'export DCS réel (10 182 horodatages horaires).

### La correction scientifique qui structure tout (ADR-001 et ADR-002)

La version initiale du projet diagnostiquait l'encrassement sur le **résidu de
puissance thermique** (`duty`). C'est algébriquement circulaire : `duty` est
défini comme `rho.cp × F × (T_in − T_out)`, la référence le régresse sur `F`,
`T_in` et `F×T_in`, et `T_out` est **régulée** à 66 °C. La régression retrouve
donc sa propre définition.

| mesure | valeur |
|---|---|
| R² de la référence apprise | 0,968 |
| R² d'une formule **sans apprentissage** | 0,962 |
| apport réel du modèle | **0,006** |
| corrélation(résidu, écart de consigne) | **−0,94** |

Le résidu a été renommé `regulation_effort` — c'est ce qu'il mesure — et il
**ne fonde jamais un diagnostic d'encrassement**.

Le vrai indicateur est **UA**, le coefficient d'échange global, calculé par la
méthode **efficacité-NTU**. Il exige la température du fluide froid, absente de
l'export DCS : elle vient de la **climatologie mensuelle de l'eau de mer à
Safi** (17,0 °C en février-mars à 22,0 °C en septembre), seule donnée du
système extérieure à toute boucle de régulation de l'atelier.

**UA est un UA APPARENT**, et le dépôt le dit partout : le débit d'eau de mer
n'est pas instrumenté, et c'est lui que la régulation manipule. Tant que la
vanne garde de la marge, elle compense un début d'encrassement. C'est pourquoi
le banc d'injection ne publie pas un taux de détection mais **l'AVANCEMENT
auquel la détection survient**.

### Architecture

```
DATA.xlsx (DCS, 14 mois)
   └─> src/ingest/dcs_loader.py        ingestion, qualité de donnée, état procédé
        └─> src/features/thermal.py     UA, efficacité-NTU, climatologie Safi
             e7301_features.py          11 MODEL_FEATURES, 3 références linéaires
             └─> src/models/detector.py  RuleEngine (AMDEC) + Isolation Forest
                  └─> src/agents/detection_agent.py   diagnostic (règles | Gemini)
                       └─> src/agents/judge_agent.py  8 contrôles V1–V8
                            └─> api/main.py + api/static/  poste FastAPI + 3D
```

- **Référentiel YAML gouverné** : `src/domain/tags.yaml` (12 tags,
  `external_inputs`, `process_states`, `quality_codes`), `amdec.yaml`
  (13 modes, criticité C = F×G×N, total 1052, barèmes GRV/OCC/DET transcrits du
  classeur OCP), `topology.yaml` (pièces, capteurs, `finding_map`).
  **Aucun seuil n'est écrit en dur ailleurs** — c'est une règle du dépôt.
- **Gouvernance** : `src/governance/` — lignage et manifeste d'artefact,
  validation du modèle et portes de déploiement, banc d'injection
  d'encrassement, banc d'évaluation du Judge, analyse de sensibilité.
- **Exploitation** : `src/operations/` (alarmes ISA-18.2 et workflows SQLite),
  `src/notifications/` (rédaction et escalade e-mail), `src/security/`
  (auth PBKDF2, registre technicien), `src/realtime/replay.py`.
- **Tests** : 22 fichiers dans `tests/`, ~300 tests, tous verts.

### Trois inventions du dépôt qu'il faut respecter

1. **`src/domain/knowledge.seuil(valeur, defaut)`** — le repli teste
   **l'absence**, pas la fausseté. L'idiome `x or defaut` est proscrit : il
   remplace un seuil légitimement nul par la valeur de secours.
2. **`src/formatting`** — toute sortie destinée à un humain est en notation
   française : virgule décimale, espace insécable étroite (U+202F) pour les
   milliers, insécable ordinaire avant l'unité. `sans_accents()` sert aux
   comparaisons de FOND. **Règle absolue : le texte COMPARÉ est dépouillé, le
   texte AFFICHÉ est accentué.**
3. **Le « patron »** — un test qui interdit la réapparition d'un défaut par
   **analyse du source** (AST, `inspect.getsource`), pas par exécution. Il est
   employé neuf fois dans le dépôt. Généralise-le.

---

## 2. La méthode de travail — non négociable

Ces règles viennent du propriétaire du dépôt et ont été tenues sur onze lots.

1. **Lis chaque fichier ENTIÈREMENT** — voir la section 0, qui dit précisément
   ce que cela veut dire et ce que cela ne veut pas dire. C'est la consigne qui
   compte le plus.
2. **Aucun `grep` n'établit une absence.** Suis la donnée jusqu'à son point de
   rendu : les champs sont renommés en transit. Deux constats de la session
   précédente ont dû être **rétractés** pour avoir violé cette règle.
3. **Prouve chaque correction par mutation** : réintroduis le défaut, montre
   que le contrôle échoue, restaure. Publie le tableau avant/après.
4. **Ne réimplémente pas pour tester.** Importe le prédicat réel.
5. **Corrige-toi explicitement.** Deux corrections écrites par l'audit ont dû
   être défaites par l'audit lui-même. Dis-le quand ça arrive.
6. **Travaille par lots**, en rapportant ce que tu as lu et trouvé.
7. **Consigne au fur et à mesure** dans `docs/audits/analyse-architecture.md`
   (7 139 lignes, lots S1 à S11 en fin de fichier), pas à la fin.
8. **Prends les décisions, ne les soumets pas à arbitrage.** Quand tu ne peux
   pas trancher sans lire un autre fichier, dis-le et laisse le constat
   **ouvert** plutôt que de fermer au jugé.
9. **Windows PowerShell** : jamais de `grep`, `sed`, `wc` dans les commandes
   que tu lui donnes. La seule qu'il lance est :

   ```powershell
   cd C:\dev\ocp-bionic-judge
   .\.venv\Scripts\python.exe -m pytest -q
   ```

10. **Ne committe jamais depuis ton environnement.** Une session précédente a
    laissé des `.git/index.lock` qu'il a dû nettoyer à la main.

---

## 3. Ce qui a déjà été fait — lots S1 à S11

Environ **7 400 lignes de `src/` lues intégralement**, toutes corrections
vérifiées par la suite de tests.

| lot | fichiers | lignes |
|---|---|---|
| S1 | `formatting`, `config`, `pipeline`, `thermal`, `e7301_features` | 1 384 |
| S2 | `dcs_loader`, `knowledge` | 1 433 |
| S3 | `models/detector` | 1 334 |
| S4 | `agents/detection_agent` | 780 |
| S5 | `agents/judge_agent` (+ surfaces de `schemas`) | 1 290 |
| S6 | `governance/judge_eval` | 700 |
| S7 | `governance/fouling_injection` | 467 |
| S8 | `governance/sensitivity` | 265 |
| S9 | `governance/lineage` + `scripts/promote_model` | 498 |
| S10 | `analytics/kpi` | 340 |
| S11 | `security/registry` | 363 |

### Le motif qui revient — retiens-le, tu vas le retrouver

Sur **dix-huit** occurrences recensées de « corrigé à un endroit, pas à son
jumeau », **sans exception** : le code de service porte la version juste,
l'affichage ou le document porte la version périmée. Ordre de fraîcheur établi :
`code/artefacts → README → ADR → rapport_technique.md → architecture.md →
notebook`.

### Les corrections les plus lourdes

- **M-1** — `detector._fouling_warning_sigma` écrivait `(...) or 3.0` et
  nommait le résultat `seuil`, **masquant la fonction importée** que le module
  emploie correctement huit fois ailleurs. Un `warning_sigma: 0` gouverné
  devenait 3,0.
- **Le plus gros angle mort typographique** — deux tests se partageaient la
  typographie : l'un cherchait les accents sur les constatations, l'autre le
  point décimal sur les rapports de gouvernance. **L'intersection était vide**,
  et les 23 messages du moteur de règles écrivaient « 66.3 °C » dans le journal
  du rejeu, le registre d'alarmes et les courriels d'escalade. Corrigé, et les
  deux contrôles croisent maintenant critère × population.
- **A-1** — `_quote_measurements` rendait « entree acide 94.23 degC ». Elle
  n'est appelée que par la branche **nominale**, et le test échantillonnait
  `notable_timestamps` — **le complémentaire exact** de la population qui peut
  déclencher le défaut.
- **S6-1** — le banc du Judge fixait sa graine « sinon le chiffre de
  généralisation change à chaque exécution » puis laissait `use_llm=True` :
  ±1,5 point d'ajustement sur chaque verdict rendait les deux chiffres publiés
  aléatoires.
- **S6-2 et S7-1** — **deux bancs de gouvernance dont le dénominateur
  contenait des non-événements** : une mutation qui ne mute rien (`checklist_ref`
  absent), une fenêtre « calme » parce que la ligne est à l'arrêt.
- **S8-1** — `thermal.reference_cutoff` affirme « les deux modules ne peuvent
  plus diverger » à propos de `sensitivity`, qui recopiait la formule **sans la
  garde `max(0, ...)`** : une fraction assez petite donnait l'indice −1, donc la
  **dernière** heure de marche, donc le corpus entier comme référence.
- **S10** — `evidence_level` était devenu une constante et son exemple un
  fantôme ; trois résultats de modèle, dont le « ~5 épisodes/mois » cité dans le
  rapport, étaient étiquetés comme des mesures.
- **S11 / SEC-1** — `add`, `set_password`, `remove` mutaient le registre **en
  place** alors que le commentaire onze lignes plus haut énonce que « les
  accesseurs de lecture ne prennent pas le verrou ». Preuve par mutation :
  4 `RuntimeError: dictionary changed size during iteration` sur le chemin
  d'authentification, 0 après.

### Surfaces mortes supprimées

`approach_ratio`, `fouling_resistance_trend_14d`, `duty_per_load`,
`components_for_mode()`, `Check.issue_code`, `JudgeVerdict.validation_scope`,
`JudgeVerdict.uncertainty_level`, `EXTERNAL_DATA_GATES` (introduite **par
l'audit lui-même**, et retirée à ce titre), `PROMOTION_STATUSES.validated_offline`
et `.rejected`.

### Surfaces mortes rendues vivantes

Barèmes AMDEC GRV/OCC/DET, `Tag.criticality_link`, `process_states`,
`T_SEAWATER` et les trois colonnes de la référence d'entrée (servies par
`/api/timeseries`, deux familles de signaux ajoutées au poste),
`severite_immediate` (verrouillée par test plutôt que câblée).

---

## 4. Ce qu'il te reste — 3 960 lignes

Dans cet ordre, du plus dense en gouvernance au plus large :

| fichier | lignes | ce que tu y cherches |
|---|---|---|
| `src/governance/model_validation.py` | 592 | **Prioritaire.** Backtest temporel, cinq portes de déploiement. Deux portes ont été scindées en phase 0 : `redondance_features` / `redondance_hors_modele`, `stabilite_hors_periode` / `derive_de_distribution`. **Le seuil PSI de 0,25 est d'origine credit-scoring et n'a jamais été justifié pour un procédé industriel** — c'est un constat ouvert, tranche-le. Vérifie que `causal_pipeline_refit` fait ce que son nom dit. |
| `src/security/auth.py` | 300 | Sessions, CSRF, PBKDF2, rotation de jeton. Une session précédente a corrigé un test faux sur `/api/auth/refresh` (POST + `X-CSRF-Token`). |
| `src/realtime/replay.py` | 430 | Promesse centrale : « à l'instant t, seule la fenêtre [début, t] est transmise ». **Vérifie-la ligne à ligne** — une lecture du futur a déjà été trouvée et corrigée dans `classify_process_state`. |
| `api/main.py` | 1 759 | Le plus gros. ~40 routes. Vérifie que **chaque route est consommée par le front** et que chaque champ servi est rendu. Le propriétaire exige que **toutes les pages fonctionnent**. |

Non lus non plus, moins urgents : `src/notifications/email.py` (512) et
`redaction.py` (294, déjà corrigé en phase 0), `api/__main__.py` (73).

### Constats connus qui t'attendent

- **`model_validation`** : justifier ou remplacer le seuil PSI 0,25.
- **WF-2 / WF-3** : `CANCELLED` et `WORKFLOW_STATES` dans
  `operations/workflows.py` — jamais produits ? à vérifier (le fichier a été lu,
  ces deux constats n'ont pas été tranchés).
- **M-3** : à rouvrir et revérifier.
- Les **libellés des huit contrôles du Judge** restent partiellement sans
  accents (`citees`, `reelles`, `invoques`, `fondes`) : ces mots ne sont pas
  dans le lexique de `tests/test_typographie.py`. Élargis le lexique **après**
  avoir lu le fichier concerné, pas à l'aveugle.

---

## 5. Sécurité — à traiter, ce n'est pas fait

1. **Deux clés Gemini ont été collées en clair dans une conversation** : elles
   sont **compromises**. `GEMINI_API_KEY` est toujours dans `.env`. À révoquer
   côté Google, puis vider la variable.
2. **Le dépôt distant doit être PRIVÉ.** `data/raw/DATA.xlsx` contient 14 mois
   de données d'exploitation réelles d'OCP.
3. **`data/runtime/operators.json`** contient des empreintes PBKDF2 et des
   adresses réelles — jamais versionné.
4. Le tag `v3.0.0` existe en local ; rien n'a encore été poussé.

---

## 5 bis. La phase finale — après la lecture, le livrable

Quand les quatre fichiers restants sont lus et corrigés, **le travail n'est pas
fini**. Il reste trois chantiers, dans cet ordre.

### F1. Le rapport, repris contre onze lots de corrections

`docs/rapport_technique.md` et ses satellites décrivent un dépôt qui a changé
onze fois depuis leur dernière relecture. **Chaque lot S1–S11 a une conséquence
documentaire**, et le journal `analyse-architecture.md` te dit laquelle. Passe
le rapport au crible sur au moins ceci :

- les **features** : trois colonnes supprimées (`approach_ratio`,
  `duty_per_load`, `fouling_resistance_trend_14d`). L'annexe B doit les perdre.
- les **KPI** : cinq figures sur sept sont passées de `observed` à `derived`.
  Le « ~5 épisodes/mois » cité dans le rapport **est un résultat de modèle** —
  le rapport doit le dire.
- les **bancs** : le taux de généralisation du Judge et l'avancement médian à
  la détection ont tous deux vu leur **dénominateur corrigé**. Les chiffres du
  rapport sont donc à recalculer et à réécrire, pas à recopier.
- la **couverture AMDEC** et les barèmes GRV/OCC/DET, désormais publiés.
- les **statuts de promotion** : le rapport décrit-il un cycle de vie à six
  états ? Il n'y en a que quatre.

Un contrôle existe déjà et te sera utile :
`tests/test_documentation.py::test_aucun_chiffre_cle_ne_contredit_les_artefacts`.
**Élargis-le** à chaque chiffre que tu réécris — c'est ce qui empêchera le
rapport de redevenir faux.

Il t'a dit dès le départ : « quitte à le supprimer et le refaire ». Si une
section ne survit pas à la confrontation, réécris-la plutôt que de la rapiécer.

### F2. L'interface, page par page

Ouvre le poste et **parcours chaque vue**. Pour chacune, deux questions :

- tout ce que l'écran affiche existe-t-il côté serveur, avec la bonne
  sémantique ? (le booléen `observable` lu à la place d'`observabilite` à trois
  états est passé six mois sans être vu) ;
- tout ce que le serveur sert est-il rendu quelque part ? (`T_SEAWATER` avait
  un libellé et aucune route ; `t_in_expected` était calculé et jamais exposé).

`tests/test_api.py` couvre les routes ; il ne couvre pas le rendu. La commande
pour lancer le poste :

```powershell
cd C:\dev\ocp-bionic-judge
.\.venv\Scripts\python.exe -m api
```

### F3. La propreté du dépôt

Dernier passage, à faire **en dernier** parce qu'il dépend des deux autres :
arborescence, noms de fichiers, `.gitignore`, `requirements.txt`, README,
`Makefile`. Plus rien qui ne serve, plus rien qui mente sur son contenu.

Puis, seulement à ce moment : dépôt distant **privé**, `git push main --tags`.

---

## 6. Comment démarrer

1. Lis la fin de `docs/audits/analyse-architecture.md` — les lots **S1 à S11**,
   à partir de « Reprise de `src/` — lecture intégrale ». Tout y est, avec les
   preuves. C'est long ; lis-le quand même, c'est ce qui te donnera la maîtrise
   du dossier qu'il attend de toi.
2. Ouvre `src/governance/model_validation.py` et **lis ses 592 lignes en une
   fois**. Annonce le nombre de lignes lues dans ton compte rendu.
3. Corrige, prouve par mutation, consigne dans le journal, puis fais lancer :

   ```powershell
   cd C:\dev\ocp-bionic-judge
   .\.venv\Scripts\python.exe -m pytest -q
   ```

4. Enchaîne : `auth.py` (300), `replay.py` (430), `api/main.py` (1 759).
   Un lot par fichier. Puis les trois chantiers de la section 5 bis.
5. Rapporte de façon courte. Il a dit deux fois qu'on écrit trop. Le journal
   d'audit porte le détail ; le message porte la conclusion.

Une dernière chose. Ce dépôt est traversé par un motif : **des affirmations
justes écrites à côté d'un code qui ne les tient pas**. Un commentaire qui
promet une atomicité que les trois méthodes voisines n'appliquent pas. Une
docstring qui déclare deux modules non divergents alors qu'ils divergent. Un
banc qui fixe sa graine puis laisse un LLM décider. Quand tu lis un commentaire
qui énonce un principe, **va vérifier que le code d'à côté le respecte**. C'est
là que sont les défauts.
