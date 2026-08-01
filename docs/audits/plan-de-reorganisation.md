# Plan de réorganisation — dépôt E7301

**Établi après lecture intégrale du dépôt.** Les constats et leurs preuves sont
dans `analyse-architecture.md` (5 634 lignes, 8 lots). Ce document ne les répète
pas : il décide et il ordonne.

Les décisions sont **prises**, pas soumises. Là où j'ai tranché contre une
option défendable, je dis pourquoi.

---

## 1. Le diagnostic, en cinq lignes

**Le dépôt n'est pas désordonné. Il est stratifié.**

Sur les seize occurrences relevées du motif « corrigé à un endroit, pas à son
jumeau », **sans une seule exception**, c'est le code qui porte la version
corrigée et le document qui porte la version d'avant. Le projet a été corrigé
scientifiquement une fois — le passage du résidu de duty au coefficient
d'échange UA — et cette correction n'a été propagée qu'à une partie des
supports.

| Strate | Fraîcheur |
|---|---|
| Code, tests, artefacts `reports/` | **état courant** |
| Poste (`app.js`, `twin.js`, `app.css`) | courant, sauf trois champs venus de l'API |
| `README.md` | une génération de retard sur deux chiffres |
| Les 11 ADR | trois chiffres périmés sur ADR-003 et ADR-004 |
| `docs/rapport_technique.md` | **antérieur à la réfutation du résidu de duty** |
| `architecture.md`, `runbook-operations.md` | « vérifiés le 25 juillet », avant les trois derniers ADR |
| `notebooks/01_analyse_E7301.ipynb` | **la strate la plus ancienne** |

La chaîne de propagation du défaut central est établie de bout en bout :

```
notebook  →  update_report_docx.py  →  rapport Word  →  rapport_technique.md  →  ADR-003
```

**Conséquence : le travail est un travail de propagation, pas de rédaction.** Le
texte juste existe déjà, presque toujours — dans le README, dans un commentaire
de module, ou dans un ADR.

---

## 2. Décision B1 — **les alarmes et les gammes sont conservées et exposées**

C'était la décision bloquante. Je tranche : **on construit l'interface, on ne
retire pas le code.**

### Ce qui a été mis en balance

| Retirer | Exposer |
|---|---|
| −849 lignes, −6 routes, −10 tests | +1 page dans la vue Intégrité |
| Il faut **quand même** corriger le rapport (l. 789) | Le rapport devient vrai sans être touché |
| On perd un cycle de vie d'alarme ISA-18.2 complet et persistant | On l'affiche |

### Pourquoi exposer

1. **Le code est bon et il est testé.** `test_alarm_store.py` porte sept tests
   dont un de concurrence à vingt fils qui vérifie qu'une rafale identique
   produit une alarme et vingt occurrences. `AlarmStore` est le **seul état
   persistant** du poste entre deux redémarrages.
2. **Le sujet est celui du mémoire.** Un cycle `ACTIVE → ACKNOWLEDGED → SHELVED
   → RETURNED_NORMAL → CLOSED`, avec journal d'audit nommant l'action et non
   l'état d'arrivée, est exactement ce qu'un service fiabilité attend. Le retirer
   appauvrit le dossier au moment où il faut le défendre.
3. **Le coût de construction est faible.** Le poste possède déjà tous les
   patrons nécessaires : `.tbl`, `.chip[data-tone]`, `.seg`, `.plan-item`,
   `.blind-item`. Aucun CSS nouveau.
4. **Le retrait ne dispense pas de la correction documentaire.** Il faudrait de
   toute façon reprendre la ligne 789 du rapport et l'ADR correspondante.

### Deux corrections obligatoires **avant** la construction

- **AL-1 — vérifié au source, et plus grave que décrit.**

  `alarms.py:161-172` :

  ```python
  @staticmethod
  def _trigger(analysis):
      findings = getattr(analysis.detection, "findings", ())
      return str(findings[0].code) if findings else None

  @classmethod
  def _key(cls, analysis):
      """Clé stable : équipement et signal déclencheur, jamais la sévérité."""
  ```

  La docstring promet une **clé stable**. Elle dépend de l'ordre d'évaluation
  des règles, et `RuleEngine.evaluate` (`detector.py:35-41`) appelle
  **`_rule_sensor_health` en premier**.

  **Trois conséquences établies au code :**

  1. **Le registre nomme l'alarme d'après le capteur qui dérive, pas d'après le
     tube qui fuit.** Si `SENSOR_FAULT` et `CONC_DROP_SEVERE` coexistent,
     `alarm_key` et `trigger_rule` valent `SENSOR_FAULT`. L'agent, lui, retient
     correctement `CONC_DROP_SEVERE` : **le diagnostic à l'écran et l'alarme
     persistée ne désignent pas la même chose.**
  2. **Une alarme peut ne jamais se résoudre.** `observe` cherche
     `WHERE alarm_key=?` avec la clé *courante*. Si la constatation-clé
     disparaît alors qu'une autre subsiste, `row is None` : une **seconde**
     alarme est créée et la première reste `ACTIVE` indéfiniment. Personne ne
     la résoudra.
  3. La sévérité stockée est celle de la **décision** (l. 273-277), pas de la
     constatation-clé : une alarme nommée `SENSOR_FAULT` peut porter
     `CRITICAL`. L'incohérence est lisible dans la ligne elle-même.

  **Le correctif est de réutiliser `_priorite`, pas d'en écrire un second.**
  `detection_agent.py:206-217` porte déjà exactement la règle manquante :
  sévérité, puis `0 if sous_ensemble == "INSTRUMENTATION" else 1`, puis
  criticité AMDEC, puis source, puis code pour départager. Écrire un second
  barème rouvrirait le motif qu'on est en train de fermer.

  À décharge : `_evidence` conserve `finding_codes` **au complet**. L'information
  n'est pas perdue, seule l'identité l'est — la réparation est donc possible sur
  les alarmes déjà enregistrées.

  Le défaut est invisible pour la suite parce que `_analysis()` de
  `test_alarm_store.py` ne construit **jamais plus d'une constatation** : le test
  à écrire en passe deux, dont un `SENSOR_FAULT` en tête.
- **WF-1 / WF-4** — `store.complete` n'a pas de garde d'état terminal, et
  `BLOCKED`, `NOT_APPLICABLE`, `CANCELLED` ne sont exercés par aucun test.
  `test_alarm_store` porte le garde équivalent
  (`test_shelved_ne_revient_pas_silencieusement_a_la_normale`) : **les alarmes
  ont la protection que les gammes n'ont pas.**

### Et **API-3** se corrige dans le même geste

Les six prérequis HSE codés en dur dans `_workflow_templates()` doivent lire
`amdec.yaml/gammes/PS3-ABS-REFR/prerequis`. **Quatre points de consignation sur
sept n'atteignent pas l'écran aujourd'hui** — dont le débranchement du courant
sur les anodes et le cadenas par intervenant. Les huit étapes de tamponnage
n'ont **aucune source** dans le dépôt : soit la gamme est transcrite dans
`amdec.yaml`, soit le modèle est retiré. Je tranche : **transcrire**, le fichier
source est dans `docs/`.

---

## 3. Décision — **le motif de duplication se traite par le patron déjà présent**

Le dépôt contient **quatre exemplaires** d'un même patron : un contrôle qui
interdit par analyse du source la réapparition d'un défaut.

| Exemplaire | Ce qu'il verrouille |
|---|---|
| `test_features_detector.py:196` | aucun `0.40` en dur hors de la définition de `REFERENCE_FRACTION` |
| `twin_smoke.mjs:282-285` | `_loop` délègue, `etat.avance +=` n'existe qu'en un exemplaire |
| `test_service_invariants.py` | **douze** contrôles par arbre syntaxique |
| `test_agents_judge.py:545` | aucune mutation « non ciblée » ne déclenche systématiquement un contrôle |

**Ce n'est plus une pratique isolée à généraliser : c'est la pratique dominante
du projet.** Le plan l'étend à la documentation, qui est la seule surface non
couverte.

**Trois contrôles à ajouter dans `test_documentation.py`**, qui balaie déjà les
11 ADR, le runbook, `architecture.md`, le rapport et le README :

| Contrôle | Ce qu'il attrape |
|---|---|
| tout **chemin** cité entre accents graves doit exister | `legacy/` × 4 |
| tout **lien Markdown relatif** doit résoudre | ARCH-2 |
| tout **chiffre-clé** doit **égaler** l'artefact, et aucune valeur concurrente ne doit qualifier le même terme | RAP-4, RAP-7, READ-1, ADR-3-1, ADR-3-2, ADR-4-1, ADR-11-1, TEST-1 |

**Les deux premiers sont écrits en étape 3** — dix minutes, et ils passent au
vert immédiatement une fois `legacy/` retiré des quatre documents et le lien
ADR-008 réparé.

**Le troisième est écrit ET activé en phase D, dans le même geste que les
corrections qu'il verrouille.** L'écrire en étape 3 le ferait échouer sur une
quinzaine de divergences que la phase D ne corrige qu'en étape 6 : la suite ne
pourrait pas être verte en étape 4. Un contrôle et sa condition de succès ne se
séparent pas.

C'est l'item le plus rentable du plan : huit constats, un contrôle.
Il corrige au passage **TEST-1** — `test_le_rapport_technique_cite_les_artefacts`
vérifie `v not in rapport`, une inclusion de sous-chaîne. La valeur attendue
pour les features est `"11"`, et `"11"` est satisfait par `1118-9754`, la taille
Chemetics de l'appareil. Le contrôle resterait vert si le rapport écrivait « dix
features » partout — ce qu'il fait dans son annexe B.

---

## 4. Phase 0 — les trois préalables bloquants

Rien d'autre ne peut être livré tant que ces trois points ne sont pas traités.

### 0.1 — La chaîne d'intégration est rouge par construction

`ci.yml` lance `validate_release.py` **sans `continue-on-error`**. Ce script
retourne `2` dès qu'une porte obligatoire échoue, et `MANDATORY_GATES` en
déclare cinq dont **quatre échouent**, deux **définitivement** — `labels_gmao`
et `validation_externe` attendent un historique qu'OCP n'a jamais fourni.

Le job `tests` échoue à chaque exécution ; le job `image`, qui porte
`needs: [qualite, tests, frontend]`, **n'est jamais construit**.

**Décision : séparer deux natures de portes.**

| Nature | Portes | Effet d'un échec |
|---|---|---|
| **Logicielles** | `causalite_temporelle`, `redondance_features`, `stabilite_hors_periode` | un commit a cassé une propriété → **bloque la fusion** |
| **Données externes** | `labels_gmao`, `validation_externe` | OCP n'a pas fourni → **publié, jamais bloquant** |

Concrètement : introduire `SOFTWARE_GATES` dans `lineage.py`, faire porter le
code de retour de `validate_release.py` sur ce sous-ensemble, et laisser le
script publier l'état complet des cinq portes. `promote_model.py` continue
d'exiger les cinq — la promotion reste légitimement impossible, et c'est
correct.

### 0.2 — Deux tests échouent

`reports/junit.xml` : **277 tests, 2 échecs, 1 ignoré.**

| Test | Cause |
|---|---|
| `test_project_metrics_restent_coherentes_avec_les_artefacts` | boucle d'amorçage connue ; **la sortie est écrite dans le fichier même**, l. 34-51 |
| `test_api.py::test_acces_local_et_notifications_desactivees` | porte sur les deux routes de notification touchées par les modifications non commitées ; très probablement **API-5** |

### 0.3 — Vérifier la transcription de l'AMDEC

Ce n'était pas une zone d'ombre : `docs/4-AMDEC - REFROIDISSEUR DE SECHAGE
PSIII.xlsx` est dans le dépôt, et la vérification prend une heure.

**Toute l'architecture de provenance repose dessus.** `amdec.yaml` s'annonce
« transcription fidèle », chaque mode porte `original_values` et
`validation_status: source_transcribed`, un test vérifie que les cotations
`ocp_source` conservent leurs valeurs d'origine — mais **rien n'a jamais comparé
ces valeurs au fichier source**. Le test compare le YAML à lui-même.

Et il existe une raison concrète de douter : les **huit étapes de tamponnage**
de `_workflow_templates()` affichent `source_ref: "8-Gamme de tamponnage des
tubes de refroidisseur.xls"`, un fichier qui **ne les contient pas** —
`gammes.TAMPONNAGE` ne porte ni étapes, ni EPI, ni durée. Une provenance
affichée sans source vérifiée a déjà été prise en défaut une fois dans ce dépôt.

À confronter, ligne à ligne : les neuf modes `ocp_source`, leurs cotations
F / G / N / C, les libellés d'élément et de mode, les actions correctives, les
huit tâches A→H du plan préventif et les deux check-lists.

**Si la transcription est fidèle, c'est le meilleur argument du mémoire** : un
référentiel métier vérifiable contre son document d'origine. Si elle ne l'est
pas, tout ce qui est bâti dessus est à revoir, et il vaut mieux le savoir
maintenant.

### 0.4 — Deux défauts introduits par la session précédente

- **API-5** — `api/main.py:1555` passe `demandeur=` à `enqueue_governance` ;
  `:1535` appelle `enqueue_test()` sans argument, alors que la méthode porte le
  paramètre. **NOTIF-1** ajoute une troisième jambe : le corps du courriel de
  test est resté sans accents (`operationnel`, `associee`) quand le rapport de
  gouvernance est intégralement accentué.
- **FMT-1** — `redaction.py:65-75` définit `_nombre()`, qui refait exactement ce
  que `src/formatting.nombre` fait déjà, contre la règle 2 d'ADR-011 qu'il
  invoque lui-même. `tests/helpers.py:12-27` duplique de même
  `src/formatting.sans_accents`, **ligne pour ligne** (FMT-2).

---

## 5. Phase A — assainissement

### A.1 — Retirer 16,2 Mo du disque, sans aucun risque git

Vérifié par `git ls-files` : **`.gitignore` les a interceptés avant tout commit.**

| À supprimer | Taille | Pourquoi c'est sûr |
|---|---|---|
| `rapport/` | 11 Mo | non suivi, projet de rédaction distinct |
| `Rapport de stage … v2.docx` et `… .docx` | 3,8 Mo | non suivis (`*.docx`) |
| `docs/DATA.xlsx` | 1,4 Mo | non suivi ; **doublon MD5 exact** de `data/raw/DATA.xlsx` (`586fc002…` des deux côtés) |

```powershell
# Vérifier d'abord qu'aucun n'est suivi — la sortie doit être vide
git ls-files | Select-String -Pattern 'rapport/|\.docx$|docs/DATA\.xlsx'

# Sauvegarder hors dépôt, puis retirer
$sauvegarde = "$HOME\Documents\E7301-archive"
New-Item -ItemType Directory -Force -Path $sauvegarde | Out-Null
Move-Item -Path .\rapport, ".\Rapport de stage*.docx", .\docs\DATA.xlsx -Destination $sauvegarde
```

### A.2 — Supprimer quatre scripts orphelins et trois dépendances

Aucune référence dans `Makefile`, `package.json`, `ci.yml`, `tests/`, `src/`,
`api/`, `README.md` ni `docs/*.md`.

| Script | Motif |
|---|---|
| `audit_corpus.py` (243 l.) | écrit **en anglais**, seul fichier du dépôt dans ce cas ; écrit dans `tmp/`, qui n'existe pas ; **seul lecteur de `docs/DATA.xlsx`** |
| `update_report_docx.py` (360 l.) | déclaré hors service par son propre en-tête ; **source de l'erreur des « dix features »** ; substitutions littérales non qualifiées (`"8 274" → "8 235"`) sur un document Word entier |
| `make_contact_sheets.py` (56 l.) | outil générique de planches-contact, aucun lien avec E7301 |
| `browser_smoke.mjs` (212 l.) | **cassé** — itère sur `reliability/governance/business/overview`, quatre vues qui n'existent pas, et `business` est interdit par `test_api.py:86` |

**`browser_smoke.mjs` contient le seul mot de passe en clair du dépôt** —
ligne 96, unique occurrence. La valeur n'est pas reproduite ici : la citer
ferait entrer dans l'historique git le secret que sa suppression doit
précisément en sortir. Le README affirme : « Le dépôt
ne contient **aucun mot de passe**, aucune empreinte, aucune adresse réelle. »
**Cette phrase est fausse aujourd'hui, et ce fichier en est la seule cause.**

Retirer ensuite de `requirements.txt` les trois dépendances qui n'existent que
pour eux — `pypdf`, `Pillow`, `python-docx`, chacune commentée du nom de son
script.

### A.3 — `.gitattributes` et le notebook

`notebooks/01_analyse_E7301.ipynb` pèse **567 Ko dont 519 Ko de sorties
embarquées — 92 %**. Cinquième fichier suivi le plus lourd, devant
`three.core.min.js`, et il apparaît modifié dans `git status` dès qu'on l'ouvre.

**Le dépouillement est reporté en fin de phase D**, et voici pourquoi.

Justifier le retrait des sorties par « les figures sont ailleurs » était faux
dans ce document même : **A.1 déplace `rapport/` hors du dépôt**. Et **NB-1 /
NB-2** établissent que le notebook **ne s'exécute pas** — `duty_residual_trend_14d`
n'est plus produite, et `twin.r2` n'existe pas sur l'objet `References`.

Dépouiller maintenant laisserait un fichier qui ne tourne pas **et** ne montre
plus rien. On refait d'abord ses sections 3 et 4 sur UA, on le réexécute, on
vérifie qu'il produit ses figures, **puis** on retire les sorties et on pose le
filtre `.gitattributes`.

En étape 1, on se contente de **déclarer le filtre sans l'appliquer**.

---

## 6. Phase C — recette du poste et les trois défauts d'écran

La lecture du front change la nature de cette phase. **Sur 5 966 lignes je
trouve un seul défaut visible à l'écran**, et il ne vient pas du poste.

### C.1 — FRONT-1, le seul défaut visible

`app.js:577` affiche, dans le tiroir ouvert **à chaque clic sur un capteur du
jumeau 3D** :

> **Capteur primary · confiance isa_5_1,process,data**

Deux identifiants machine dans la même phrase. C'est ce qu'ADR-011 déclare avoir
corrigé, et **les trois bancs ne l'attrapent pas** : leurs contrôles portent sur
`#readouts` et `#diag`, aucun n'ouvre `#drawer`.

Origine réelle : **DOM-6**. `Tag.confidence` a **gardé son nom et changé de
sens** — il porte la liste des bases jointes par des virgules. Le rapport § 2.2
promet encore `confirmed` / `inferred` / `unknown` : ces trois valeurs n'existent
plus.

Correctif : renommer le champ `bases`, `rationale` → `evidence`, et afficher via
`BASE_LABEL`, **qui existe déjà** à `app.js:1642` et fait exactement cela pour un
autre panneau.

### C.2 — API-2, le meilleur rapport effet/effort du dossier

Le menu « Signaux » offre six familles. **Aucune ne porte UA.** L'exploitant peut
tracer `duty_kw`/`duty_expected` — la paire qu'ADR-001 réfute — et **pas**
`ua_kw_per_k`, `ua_expected`, `fouling_resistance`, `ua_residual_trend_14d`.

Mais **le front connaît déjà ces grandeurs** : `MESURE_LABEL` (`app.js:1394`)
les nomme toutes avec leur unité et leur précision, et la carte de lignage
affiche déjà UA depuis `references.conductance`.

**Deux gestes suffisent** : servir les colonnes UA dans `/api/timeseries`,
ajouter une septième entrée à `TREND_SETS`.

⚠️ **`test_api.py:348` verrouille le défaut** : il exige `duty_kw` et
`duty_expected` et n'exige aucune grandeur UA. Ce test doit être amendé — c'est
la seule correction du plan qui oblige à toucher un test existant.

### C.3 — C2 change de nature : ce n'est plus une correction

Le constat **T-1** attribue le recouvrement des capteurs au champ `anchor`,
« censé éviter les recouvrements ». **C'est faux.** `twin.js:1265` :

```js
group.position.set(ax, ay, az);                        // ← la position vient de `at`
group.rotation.z = ANCHOR_ROTATION[meta.anchor] ?? 0;  // ← anchor = une rotation
```

Et le commentaire dit à quoi il sert : « le doigt de gant doit pointer **vers**
la tuyauterie, pas dans le vide ». Corriger les ancres n'aurait rien changé.

De plus, `_resolveLabelCollisions` tourne **à chaque image** : elle estompe les
étiquettes en conflit à 12 %, **sauf celles en défaut**, et efface celles qui
débordent du cadre. **Le recouvrement est déjà atténué.**

C2 devient donc un réglage de coordonnées `at` dans `topology.yaml`, sous deux
gardes :

- `egares.length === 0` — tout capteur du périmètre à moins de **0,9 m** de sa
  pièce ;
- **BANC-3** — `["etiquettes qui se recouvrent sont estompees", someFaded]` exige
  qu'**au moins une étiquette soit estompée**. Écarter les capteurs **fera
  échouer ce contrôle**. Il doit être reformulé d'abord : « aucune étiquette ne
  se recouvre, **ou** celles qui se recouvrent sont estompées ».

### C.4 — Trois points mineurs

- `dashboard.html:447` — un `.split` (grille à deux colonnes) à un seul enfant :
  le panneau « Les huit contrôles » occupe la moitié gauche et laisse un vide.
- `renderFeed` (`app.js:1053`) — la garde `box.innerHTML === html` ne peut
  probablement pas fonctionner, le navigateur normalisant `innerHTML`. **À
  mesurer avant correction**, je ne l'affirme pas.
- `.kpi[data-evidence="derived"]`, `.readout[data-live="on"]` — deux règles CSS
  mortes.

### C.5 — À savoir avant la recette

Sous 14 images/seconde, `_guardPerformance` masque le faisceau tubulaire, mais
`_marquerPieces` dessine son cartouche **sans test de profondeur** : sur un poste
à carte graphique intégrée — la configuration de salle de contrôle que le code
cite lui-même — l'écran affichera « ▲ CRITIQUE — FAISCEAU TUBULAIRE » au-dessus
d'un appareil dont le faisceau n'est pas rendu.

---

## 7. Phase E — livraison

**E1 est la dernière action avant E2.** La phase B ajoute des tests HTTP et la
phase D réécrit les chiffres du rapport : `test_project_metrics.py` compare la
suite et le rapport aux artefacts, il serait donc invalidé **deux fois** si E1
était exécuté en étape 4. La boucle d'amorçage se joue une seule fois, à la fin.

### E.1 — Suite verte et artefacts régénérés

La boucle d'amorçage est déjà documentée dans `test_project_metrics.py:34-51`,
avec le bon arbitrage : « Affaiblir l'assertion pour éviter la boucle
reviendrait à autoriser la publication de métriques rouges. »

```powershell
.\.venv\Scripts\python.exe -m pytest tests\ -q --junitxml=reports\junit.xml `
  --deselect tests/test_project_metrics.py::test_project_metrics_restent_coherentes_avec_les_artefacts
.\.venv\Scripts\python.exe scripts\generate_project_metrics.py
.\.venv\Scripts\python.exe -m pytest tests\ -q --junitxml=reports\junit.xml
.\.venv\Scripts\python.exe scripts\generate_project_metrics.py
```

### E.2 — Le dépôt distant doit être privé dès sa création

Vérifié par `git ls-files` : **les huit documents sources OCP et
`data/raw/DATA.xlsx` sont suivis**, soit ~12,5 Mo déjà dans l'historique.

| Fichier suivi | Taille |
|---|---|
| `docs/2-Fiche Identifcation sous ensemble … .xlsx` | 5,79 Mo |
| `docs/8-Gamme de tamponnage des tubes … .xls` | 4,57 Mo |
| `data/raw/DATA.xlsx` — 14 mois d'exploitation réelle | 1,45 Mo |
| `docs/7-Gamme PV … .pdf` | 0,68 Mo |

**Aucun `.gitignore` posé aujourd'hui n'y changera rien.** Il n'existe pas de
variante « publier le code sans les données » qui n'exigerait pas une réécriture
d'historique.

### E.3 — Révoquer les deux clés Gemini

Elles ont été collées en clair dans une conversation : elles sont compromises.
`GEMINI_API_KEY` figure encore dans `.env`. À révoquer côté Google avant tout
commit, indépendamment du reste.

---

## 8. Phase B — les pages manquantes

Conformément à la décision du § 2, dans la vue **Intégrité** :

1. **Registre d'alarmes** — tableau `.tbl`, colonnes : apparition, dernière
   occurrence, règle, mode AMDEC, occurrences, statut (`.chip[data-tone]`),
   propriétaire. Actions `acknowledge` / `shelve` / `unshelve` / `close` sur la
   ligne sélectionnée. Le journal de transitions dans la fenêtre modale, qui
   nomme déjà l'action et non l'état d'arrivée.
2. **Gammes d'intervention** — les trois modèles, leurs étapes avec le marqueur
   `dangerous`, la `source_ref`, l'avertissement HSE permanent, la signature de
   clôture.

Les six routes existent déjà. **Aucun CSS nouveau n'est nécessaire.**

Écrire au passage les tests HTTP manquants : **API-6** relève que
`/api/alarms`, `/api/alarms/{id}/transition`, `/api/config`, `/api/auth/audit`
et `/api/auth/refresh` n'ont **aucun test HTTP**, quand les gammes en ont neuf.

---

## 9. Phase D — réaligner la documentation

**Le rapport ne doit pas être refait. Il doit être réaligné sur le README.**

Le README contient déjà, rédigé, tout ce qui manque au chapitre 5 : UA, la
climatologie de Safi, la formule efficacité-NTU, la réfutation du résidu de duty
avec son tableau, l'aveu du *UA apparent*, la sensibilité à la fenêtre.

### D.1 — Ce qui est à reprendre dans `rapport_technique.md`

| Section | Ce qui est faux |
|---|---|
| Résumé, l. 27 | « 96,8 % de la variance du proxy de duty » en tête de résultats |
| **Chapitre 5 entier** | enseigne la thèse réfutée : « l'encrassement se lit sur l'**effort** » |
| Ligne 761 | déclare **impossible** le calcul du coefficient d'échange, que la ligne 357 utilise |
| Ligne 845 | l'annonce en **travail futur** |
| **Annexe A** | rattache `FAISCEAU_BOUCHAGE` au résidu de duty |
| **Annexe B** | deux features inexistantes, trois réelles omises, décompte à 10 |
| **§ 10.4** | revendique −40 % de criticité sur deux modes `observable: partial`, contre le § 9.3 du même rapport |
| § 6.4 | « 511 heures » puis « 530 points » à trois lignes d'écart |
| § 8.4 | « deux cas / 98,3 % » quand le § 8.3 dit « cinq cas / 95,8 % » |
| § 2.2 | décrit un champ `confidence` dont les trois valeurs n'existent plus |
| § 3.3 | dossier `legacy/` inexistant |
| § 12.3 | 267 tests et 84 vérifications ; les mesures sont 277 et ≈ 96 |

**Ce qui doit survivre intact :** le § 9.2 (l'erreur de causalité corrigée —
l'excursion de mai commence 100 jours avant la panne du capteur), le § 10.5 (le
retrait des 1,07 M MAD avec son raisonnement), le § 10.1 (l'aveu qu'un test cité
n'existait pas), le § 8.4 (65 % → 100 %), tout le § 2.3, tout le § 11 sauf la
ligne 761. **C'est ce que le dossier a de meilleur.**

### D.2 — Les autres documents

| Document | Correction |
|---|---|
| **ADR-004** | publie **~80 %** de généralisation ; mesure réelle **10 %**. Le README dit lui-même : « cette valeur **n'a jamais été mesurée** » |
| **README** | annonce **22 % (n = 50)** ; l'artefact mesure **10 % (n = 60)**, et **2 des 5 mutations listées n'existent plus** |
| **README** | « part du risque **réellement couverte : 48,8 %** » ; le code publie **30,2 % + 18,5 % partiel**, et son commentaire chiffre l'écart à 18 points |
| **ADR-003** | « dix features » (il y en a 11), « 62 épisodes » (58), « 5,8 % » (6,2 %) |
| **ADR-011** | « 43 vérifications » (52) |
| **ADR-006** | « aucune requête sortante » puis, 15 lignes plus bas, la clé LLM |
| **`architecture.md`** | décrit le résidu de duty comme la référence ; **le mot UA n'y figure pas une seule fois** ; `legacy/` ; lien mort vers un ADR-008 qui n'a jamais existé |
| **`runbook`** | fait attendre `status: ok`, que `/api/health` **ne retourne jamais** ; prescrit l'empreinte partagée qu'**ADR-007 déclare inacceptable** et ignore `manage_operators.py` |
| **notebook** | trace `duty_residual_trend_14d`, colonne qui n'est plus produite ; sections 3 et 4 à refaire, la structure en six questions à garder |

**Le piège `/api/health` mérite d'être noté** : il a été corrigé **trois fois**
— dans `ci.yml`, le `Dockerfile` et `docker-compose.yml`, chacun avec son
commentaire — et manqué dans le seul des quatre qu'un humain lit.

---

## 10. Ordre d'exécution

```
0. Préalables    transcription AMDEC · CI-5 · les 2 tests rouges
                 API-5 · FMT-1/FMT-2
1. A             16,2 Mo retirés · 4 scripts · 3 dépendances
                 .gitattributes DÉCLARÉ, pas appliqué
2. C             FRONT-1 · API-2 (+ amender test_api.py:348)
                 BANC-3 reformulé, PUIS C2
3. Le patron     contrôles 1 et 2 dans test_documentation.py — chemins cités,
                 liens Markdown · mypy en CI · retirer les 60 lignes inline
                 de ci.yml
4. B             AL-1 (réutiliser `_priorite`) · WF-1 · API-3
                 les deux pages · les tests HTTP manquants
5. D             rapport · ADR · architecture · runbook
                 notebook refait, réexécuté, PUIS dépouillé
                 contrôle 3 écrit ET activé ici
6. E1            suite verte, artefacts régénérés — une seule fois
7. E2            commit · dépôt privé · tag v3.0.0
```

**Trois principes d'ordonnancement, tous issus des amendements :**

- un contrôle et sa condition de succès ne se séparent pas — le contrôle 3 vit
  en 5, avec les corrections qu'il verrouille ;
- la boucle d'amorçage se joue **une seule fois**, après tout ce qui touche aux
  tests ou aux chiffres du rapport ;
- on ne dépouille pas un notebook avant qu'il ne s'exécute.

---

## 11. Ce qu'il ne faut pas faire

- **Ne pas supprimer le rapport.** Six sections sont à reprendre ; le reste est
  ce que le dossier a de meilleur.
- **Ne pas « nettoyer » le noyau scientifique.** L'auto-réfutation de
  `e7301_features.py`, l'aveu du UA apparent dans `thermal.py`, le « publié ici
  pour être contesté, pas pour être cru » de `sensitivity.py`, les quatre portes
  qui échouent et qui sont publiées, l'instant critique en position 6 610 jamais
  analysé de `replay.py`, le comptage de tentative **avant** la dérivation PBKDF2
  de `auth.py`.
- **Ne pas toucher aux tests qui verrouillent des retraits** : `/api/business/*`
  → 404, `"MAD"` absent, `"business"` absent du HTML, `severities=1,2,3` → 422.
- **`promote_model.py --par` est sans danger.** La contrainte « ne jamais le
  lancer » de la reprise est infondée : la fonction vérifie les portes,
  l'existence de l'artefact et l'empreinte SHA-256 — **trois refus avant la
  première écriture**.
- **Ne pas croire un `grep` qui ne trouve rien.** Je m'y suis laissé prendre :
  j'ai déclaré `Tag.confidence` inexistant sur la foi d'un `grep "def confidence"`,
  alors que c'est un champ de dataclass. La règle du § 5 de la reprise est juste,
  et elle vaut aussi pour moi.

---

## 12. Zones d'ombre assumées

Trois ensembles n'ont pas été lus, et le plan n'en dépend pas :

| Non lu | Volume | Risque |
|---|---|---|
| `src/` + `api/` en Python | 14 280 l. | lu par la session précédente, que j'ai prise en défaut **quatre fois** sur des faits vérifiables. Les 69 constats d'origine méritent d'être revérifiés au fil des corrections, pas repris tels quels |
| Les 8 documents sources OCP | 11,3 Mo | **personne n'a jamais vérifié** que `amdec.yaml` transcrit fidèlement `4-AMDEC.xlsx`. C'est la fondation du référentiel |
| `M-3` | — | le garde `test_le_rattachement_ne_cite_que_des_features_du_modele` couvre désormais **les deux tables** et il passe. Soit le défaut est corrigé, soit il portait sur autre chose. **À rouvrir avant de l'inscrire au plan** |
