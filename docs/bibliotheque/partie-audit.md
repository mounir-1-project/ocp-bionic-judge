# Bibliothèque du projet E7301 — source unique, de A à Z

**À toute session neuve : lis CE fichier, pas le dépôt.**

Il contient l'architecture, les idées implémentées, les chiffres, les méthodes et
les limites, établis par lecture intégrale de chaque fichier sur les lots S1–S44.
Une relecture du dépôt épuiserait ta fenêtre avant le premier livrable — c'est
arrivé deux fois, et c'est la raison d'être de ce document.

N'ouvre un fichier source que pour **vérifier un chiffre précis que tu t'apprêtes
à écrire**, et alors ce fichier-là seulement.

Compléments : `docs/bibliotheque/dossier-rapport.md` (matière du rapport, 165 l.),
`OBJECTIFS-FINAUX.md` (plan et décisions ouvertes),
`analyse-architecture.md` (journal d'audit intégral, 10 183 l. — n'y va que pour
retrouver la démonstration d'un point précis).

---

# I. IDENTITÉ

## 1.1 L'équipement

**E7301** — refroidisseur d'acide sulfurique à faisceau tubulaire, constructeur
**CHEMETICS**, SIZE 1118-9754, tubes **904L**. Atelier **PS III**, site OCP Safi.
Identifiant dépôt : `S-PC-E7301`.

- Côté **tubes** : eau de mer (fluide froid) — **non instrumenté en débit**.
- Côté **calandre** : acide sulfurique (fluide chaud).

Sujet d'un mémoire de fin d'études soutenu devant un jury industriel OCP.

## 1.2 Le corpus

Export DCS réel, **14 mois** : 01/01/2024 → 28/02/2025.

| grandeur | valeur |
|---|---|
| horodatages bruts | 10 182 |
| après déduplication | 10 180 (2 doublons, résolus par ordre source) |
| tags | 12 |
| heures RUNNING | > 8 000 |
| pas de temps | horaire |

**Aucune imputation.** Une valeur invalide devient `NaN`, jamais une valeur
inventée — combler un trou ferait croire au modèle que la mesure existe, et c'est
ainsi qu'un système déclare « tout va bien » pendant sept mois de capteur mort.

Deux capteurs **exclus du périmètre** parce qu'avérés défaillants :

- `TI5303-4X` — saturé à 327,67 depuis août 2024 (> 4 000 heures marquées) ;
- `PHI5306X-3` — figé à −14,407 sur les premiers mois (> 500 heures).

Codes qualité DCS relevés : `Bad`, `Configure`, `I/O Timeout`.

## 1.3 Provenance des sources métier

Huit documents OCP dans `docs/` : fiche équipement, fiche sous-ensemble, liste des
composants, **AMDEC**, plan de maintenance préventive, check-list d'inspection,
gamme PV, gamme de tamponnage.

**Aucune fiche d'instrumentation n'accompagnait l'export DCS.** Le sens des 12 tags
a donc été établi **par recoupement**, et le dépôt l'assume : chaque détermination
doit citer **au moins deux bases indépendantes** parmi `isa_5_1` (nomenclature),
`process` (physique du procédé), `data` (comportement observé), `climatology`,
`stoichio`. Verrouillé par `test_chaque_tag_declare_sur_quoi_repose_son_sens`.
Les 6 tags qui fondent un diagnostic exigent en plus la base `process`.

---

# II. ARCHITECTURE

## 2.1 Vue d'ensemble — la chaîne

```
DATA.xlsx
   │
   ▼
src/ingest/dcs_loader.py      ingestion, qualité, état procédé
   │
   ▼
src/features/                 e7301_features.py + thermal.py  (UA, NTU)
   │
   ▼
src/models/detector.py        règles + modèle, produit des FINDINGS
   │
   ▼
src/agents/detection_agent.py décision : sévérité, modes AMDEC, action
   │
   ▼
src/agents/judge_agent.py     VerificationLayer — 8 vérifications pondérées
   │
   ▼
src/pipeline.py               Analysis = (detection, decision, verdict)
   │
   ├──► src/operations/alarms.py     registre ISA-18.2 persistant
   ├──► src/operations/workflows.py  interventions maintenance
   ├──► src/notifications/email.py   alerte + rédaction
   ├──► src/realtime/replay.py       rejeu DCS
   └──► api/main.py ──► api/static/  poste local
```

## 2.2 Les modules, un par un

| module | rôle |
|---|---|
| `src/config.py` | configuration, variables d'environnement |
| `src/domain/knowledge.py` | référentiel gouverné : tags, AMDEC, topologie |
| `src/domain/*.yaml` | `tags.yaml`, `amdec.yaml`, `topology.yaml` |
| `src/ingest/dcs_loader.py` | lecture DCS, qualité, gel, état procédé |
| `src/features/e7301_features.py` | table de features horaire |
| `src/features/thermal.py` | thermique : UA, efficacité-NTU |
| `src/models/detector.py` | règles métier + modèle, produit les findings |
| `src/agents/detection_agent.py` | décision : sévérité, modes, action |
| `src/agents/judge_agent.py` | contrôleur de cohérence (8 vérifications) |
| `src/agents/schemas.py` | schémas de données + vocabulaires FR |
| `src/analytics/kpi.py` | indicateurs de performance |
| `src/governance/lineage.py` | manifeste modèle, portes, promotion |
| `src/governance/model_validation.py` | backtest 4 plis, PSI, causalité |
| `src/governance/fouling_injection.py` | banc d'injection d'encrassement |
| `src/governance/judge_eval.py` | évaluation du Judge, pièges |
| `src/governance/sensitivity.py` | analyse de sensibilité |
| `src/operations/alarms.py` | registre d'alarmes ISA-18.2 |
| `src/operations/workflows.py` | interventions, barrières HSE |
| `src/notifications/email.py` | canal e-mail, file, spool |
| `src/notifications/redaction.py` | rédaction française des messages |
| `src/security/auth.py` | sessions, CSRF, limitation de débit |
| `src/security/registry.py` | registre des opérateurs, rôles |
| `src/realtime/replay.py` | rejeu DCS, décimation, causalité |
| `src/formatting.py` | typographie française (U+202F) |
| `src/pipeline.py` | orchestration des trois étages |

## 2.3 Le référentiel gouverné (ADR-005) — idée centrale

Trois YAML : `tags.yaml`, `amdec.yaml`, `topology.yaml`.

> **Aucun seuil n'est codé en dur ailleurs.** Un seuil vit dans le YAML, et le
> code le lit. Un seuil mal saisi produirait des alertes fausses sans qu'aucun
> test aval ne s'en aperçoive : d'où les contrôles de cohérence du référentiel.

Contrôles appliqués (`test_domain.py`) :

- seuils ordonnés `LL < L < H < HH` ;
- plage opérationnelle **incluse** dans la plage physique ;
- criticité AMDEC **C = F × G × N** exactement, cotations dans le barème 1–10 ;
- toute tâche préventive citée par un mode AMDEC **existe** dans le plan ;
- alias uniques ; tag inconnu ⇒ `KeyError` explicite.

### Provenance AMDEC — une règle applicative n'est jamais présentée comme OCP

Cinq catégories : `ocp_source`, `derived_rule`, `application_rule`, `hypothesis`,
`field_validated`. Chaque mode porte `source_file`, `source_location`,
`transformations`, `validation_status`, `validation_owner`. Les modes `ocp_source`
**conservent leurs valeurs originales** F/G/N/C, vérifié par test.

Exemple : `CAPTEUR_DEFAILLANT` est `application_rule` avec
`original_values = {F: None, G: None, N: None, C: None}` — il n'a jamais existé
dans l'AMDEC OCP, et le dépôt le dit.

### Les angles morts sont déclarés

`PLAQUE_SACRIFICIELLE_DYSFONCTION` — **criticité 112** — n'est pas instrumenté.
Le déclarer détectable donnerait une fausse assurance. Tout angle mort **doit**
avoir une couverture préventive, sinon le test échoue.

## 2.4 État procédé — et la causalité

`classify_process_state` produit trois états : `RUNNING`, `STOPPED`, `TRANSIENT`.

```python
state[is_trans & ~is_down] = "TRANSIENT"
state[is_down]             = "STOPPED"      # s'applique en dernier
```

**L'entrée en arrêt ne peut PAS être transitoire.** La marquer exigerait
`is_down.shift(-1)` — « t est transitoire parce que la ligne s'arrête en t+1 » —
c'est-à-dire une **lecture du futur**, supprimée délibérément sur 27 horodatages :
*une chaîne de détection ne peut pas être à demi causale.* Seule la **reprise**
après arrêt est marquée, via `is_down.shift(1)`.

Détection de gel (`_detect_frozen`) : causale elle aussi — un point n'est déclaré
figé qu'à partir du moment où la durée écoulée atteint `FROZEN_MIN_HOURS`, jamais
rétroactivement. Un signal à zéro **pendant un arrêt n'est pas un capteur mort** :
sans cette règle, chaque arrêt générerait des centaines d'alertes instrumentation
et le système serait désactivé en salle de contrôle.

---

# III. LA SCIENCE — la correction qui fonde le projet

## 3.1 ADR-001 — le résidu de duty est circulaire

L'indicateur initial d'encrassement était le **résidu de puissance thermique**
(duty) entre valeur mesurée et valeur prédite. Il ne vaut rien. Mesuré :

| | R² |
|---|---|
| modèle appris | **0,968** |
| **sans aucun apprentissage** | **0,962** |

L'apprentissage n'apporte que **0,006**. Et :

```
corr(résidu, écart de consigne) = −0,94
```

Le résidu mesure **l'action du régulateur**, pas l'état de l'échangeur : quand
l'encrassement monte, la vanne d'eau de mer compense, et le duty reste au point
de consigne. La grandeur est **algébriquement circulaire** — elle est fonction de
ce qu'elle prétend expliquer.

**Conséquence dans le code** : renommé `regulation_effort`. Il **ne fonde plus
jamais un diagnostic d'encrassement**. Il reste publié comme indicateur de
sollicitation de la régulation, ce qu'il est réellement.

La porte de gouvernance `redondance_hors_modele` est **publiée en échec de façon
permanente** pour cette raison — c'est une propriété algébrique, aucun commit ne
peut la franchir.

## 3.2 ADR-002 — l'indicateur réel est UA, et l'eau de mer vient du climat

Le vrai indicateur est le **coefficient global d'échange UA**, calculé par
**efficacité-NTU** dans `src/features/thermal.py`.

Problème : la température d'eau de mer **n'est pas mesurée**. Solution retenue —
la **climatologie de Safi** :

| période | T eau de mer |
|---|---|
| février–mars | **17,0 °C** |
| septembre | **22,0 °C** |

C'est la **seule entrée externe à toute boucle de régulation** du système, et
c'est précisément ce qui lui donne sa valeur : rien dans la chaîne de commande ne
peut la faire bouger.

Déclarée dans `tags.yaml` sous `external_inputs.T_SEAWATER`, base `["climatology"]`,
source citant Safi, `range_operating = [17.0, 22.0]`, avec preuve. Verrouillé par
`test_la_temperature_d_eau_de_mer_est_declaree_comme_entree_externe`.

### La limite à écrire, jamais à atténuer

> **UA est APPARENT.** Le débit d'eau de mer n'est pas instrumenté. Une variation
> de débit se lit comme une variation de UA. Le projet ne peut pas les distinguer.

---

# IV. LA CHAÎNE DE DÉTECTION

## 4.1 Détection hybride (ADR-003)

`src/models/detector.py` combine **règles métier** et **modèle**. Chaque
déclenchement produit un `finding` portant un `code` (`DUTY_LOW`, `TEMP_HIGH`,
`CONC_DROP_SEVERE`, `SENSOR_FAULT`, `FOULING_DRIFT`…).

Deux structures importantes :

- `_MODE_BY_THRESHOLD` — réduite à **1 seule entrée réelle** (les autres étaient
  mortes) ;
- `_FEATURES_SANS_ACCUSATION` — `frozenset` des features qui ne peuvent fonder
  aucune accusation.

`DetectionResult.timestamp` est une **chaîne ISO 8601** (`2024-01-15T15:00:00`),
pas un `pd.Timestamp`. **Piège réel** : comparer à `str(pd.Timestamp)` échoue sur
le séparateur (espace vs `T`). Toujours normaliser par `pd.Timestamp` avant
comparaison.

## 4.2 L'agent de décision

`src/agents/detection_agent.py` transforme les findings en décision :
`severity`, `amdec_modes`, `diagnosis`, `recommended_action`, `confidence`,
`evidence_refs`, `lead_finding`, `cited_values`, `generated_by`.

**`lead_finding` — la constatation dominante.** `RuleEngine.evaluate` appelle
`_rule_sensor_health` **en premier** : une analyse portant `SENSOR_FAULT` et
`CONC_DROP_SEVERE` présentait `SENSOR_FAULT` en tête. L'agent tranche par
`_priorite`, qui fait passer un défaut de mesure **après** un diagnostic
équipement. Le registre d'alarmes consomme ce choix (défaut AL-1, corrigé).

**Mais le chemin nominal émet `lead_finding=None` avec des findings non vides**
(`detection_agent.py:376`) : le registre retombe alors sur `findings[0]`, donc sur
l'ordre des règles. C'est **AL-4, décision ouverte**.

## 4.3 Le contrôleur de cohérence — « le Judge » (ADR-004)

`src/agents/judge_agent.py`, classe **`VerificationLayer`** (attention : ce n'est
PAS `JudgeVerifier` — erreur commise et corrigée).

Huit vérifications pondérées :

| | poids |
|---|---|
| V1 | 22 % |
| V2 | 16 % |
| V3 | 14 % |
| V4 | 14 % |
| V5 | 15 % |
| V6 | 8 % |
| V7 | 5 % |
| V8 | 6 % |

Plafonds de sécurité **4,0** et **5,0**, appliqués par `_apply_safety_cap`.
Verrouillé par `test_les_poids_affiches_sont_ceux_que_le_juge_applique` : les
poids affichés à l'écran sont ceux que le Judge applique réellement.

`_facts_cache` est clé par `(decision.timestamp, detector._cache_key(features))`.
**Avant correction, la clé ne portait que l'horodatage** — le second appel
recevait les faits du premier quelle que soit la table, ce qui rendait **vacueux**
le test de causalité du rejeu.

Le verdict porte `agreement` (bool) et `global_score`. **Un désaccord du Judge
conteste une rédaction, il ne dit rien du procédé** : il ne doit jamais résoudre
une alarme (défaut AL-2, corrigé).

---

# V. GOUVERNANCE

## 5.1 Le manifeste modèle et la promotion (`lineage.py`)

`build_manifest` écrit toujours le statut `candidate`. `promote_model.py` est le
seul autre producteur, borné à `RUNTIME_STATUSES`. `validate_model_manifest`
vérifie empreinte du modèle, empreinte des données, **ordre** des variables, et
les portes obligatoires.

Vocabulaire nettoyé : `validated_offline` et `rejected` étaient déclarés et
**aucun code ne pouvait les écrire**. Verrouillé par
`test_tout_statut_de_promotion_declare_est_productible` (analyse du source).

## 5.2 Les 7 portes de déploiement

- **7 publiées**, `MANDATORY_GATES` = **5**, `SOFTWARE_GATES` = **3**.
- Le poste affiche « **3 / 7 portes franchies** ».
- `labels_gmao` et `validation_externe` échouent **définitivement** : aucune
  vérité terrain, aucune validation externe disponible. Ce n'est pas un défaut à
  corriger, c'est une **limite à déclarer**.
- Deux portes sont **publiées, en échec, et volontairement NON bloquantes** :
  - `redondance_hors_modele` — propriété algébrique permanente (ADR-001) ;
  - `derive_de_distribution` — aucun pli saisonnièrement couvert.

> **Principe** : restreindre un critère « pour qu'il passe » **remasque** ce que
> l'auteur avait délibérément rendu visible. On publie sans bloquer.

Verrouillé par `test_une_porte_publiee_non_bloquante_n_empeche_pas_la_promotion`.

## 5.3 Le backtest 4 plis et le PSI — le passage le plus important

`PSI_LIMIT = 0,25`. Valeurs mesurées par pli, relues dans
`reports/model_validation.json` le 2026-08-08 :

| pli | PSI |
|---|---|
| 1 | 1,988 |
| 2 | **3,183** |
| 3 | 0,580 |
| 4 | 0,068 |

> Ce tableau portait « 1,989 / 3,745 » — les valeurs d'**avant** la correction
> d'epsilon décrite plus bas dans cette même section. Le texte expliquait la
> correction ; le tableau gardait les chiffres qu'elle remplace.

**La preuve publiée accusait « deux excursions de sur-refroidissement ». Les plis
la réfutent** : les plis 3 et 4 testent les périodes **les plus récentes** et
dérivent **le moins**, d'un facteur **47** (3,183 / 0,068). Une dérive réelle ferait l'inverse.

Cause réelle — correspondance **forte mais non strictement monotone** avec la part d'heures de test hors de la plage d'eau de mer apprise : **cinq paires concordantes sur six**, τ de Kendall +0,667, r de Pearson +0,966. Les deux plis fortement extrapolants portent les deux PSI les plus élevés ; entre les plis 3 et 4, faiblement extrapolants tous deux, l'ordre s'inverse.

Le détail, par extrapolation croissante :

| pli | heures hors plage | PSI |
|---|---|---|
| 1 | **76,5 %** | 1,988 |
| 2 | 100 % | **3,183** |
| 3 | **5,2 %** | 0,580 |
| 4 | **12,8 %** | 0,068 |

> La dernière ligne portait « 0 % », que le paragraphe *Extrapolation
> saisonnière* dément dix lignes plus bas en annonçant 12,8 %. Deux valeurs de
> la même grandeur, dans la même section, dont l'une est expliquée comme une
> erreur corrigée — et l'autre restée dans le tableau.

> **Le PSI mesure la couverture saisonnière du découpage, pas une dérive du
> procédé.** Troisième banc du dépôt dont le dénominateur contenait des
> non-événements (après S6-2 et S7-1).

**Correction d'epsilon** : `_population_stability_index` rend désormais
`(psi, empty_deciles)` avec plancher `0,5/n` au lieu de `1e-6`. Delta prédit par
décile vide **0,5622** ; mesuré **3,7446 → 3,1826 = 0,5620** — accord à 0,0002.

**Extrapolation saisonnière** : mesurée à **12,8 %** sur le pli 4 (et non 0 %
comme je l'avais prédit à tort en calculant sur un calendrier `pd.date_range` au
lieu de `train.index` / `test.index`, qui ne portent que les **heures de marche**).
Conclusion : **0 pli qualifié**, pas 1. Le critère n'a pas été assoupli —
*on ne choisit pas un critère en fonction du verdict qu'il produit.*

**Audit de causalité** : `_decalages_non_causaux()` utilise `tokenize` pour
blanchir chaînes et commentaires, ce qui permet d'inclure `src/governance/` sans
faux positifs.

**Généralisation : 8,6 %**, et non 95,8 %. Écrire pourquoi les deux nombres
existent et pourquoi le second ne veut rien dire est un passage obligé du rapport.

## 5.4 Le banc d'injection d'encrassement

Répond à la seule question que le projet ne savait pas traiter : *le détecteur
verrait-il un encrassement s'il s'en produisait un ?* La règle **ne s'est jamais
déclenchée sur les données réelles** — rien ne permettait de distinguer « il n'y a
pas eu d'encrassement » de « le détecteur ne peut pas se déclencher ».

Méthode verrouillée autant que le résultat :

- l'injection doit **démarrer dans une fenêtre silencieuse** — sinon la détection
  mesurée n'est attribuable à rien (la première version annonçait 100 % de
  détection à 0 % d'avancement : un résultat vide) ;
- le témoin sur données non modifiées doit rester muet : `false_positive_rate < 0,02` ;
- la rampe **ne touche pas les arrêts** et la dégradation est **monotone** ;
- le prédicat du banc `_fouling_hours` doit **équivaloir à la règle réelle** —
  vérifié sur un échantillon couvrant les trois états.

**Le banc est OPTIMISTE** : il ne simule pas la compensation par la vanne d'eau de
mer. C'est la limite la plus importante, et elle est déclarée.

**La détection est TARDIVE** : elle constate la dégradation plus qu'elle ne
l'anticipe. Le chiffre honnête n'est pas le taux brut mais **l'avancement à la
détection**.

## 5.5 Évaluation du Judge — les pièges

`judge_eval.py` mesure : `trap_detection_rate`, `trap_success_rate`,
`trap_caught_not_sanctioned`, `trap_missed`. Le dernier compte les pièges
**manqués**, distinct de ceux qui sont vus mais non sanctionnés.

---

# VI. EXPLOITATION

## 6.1 Registre d'alarmes ISA-18.2 (`alarms.py`)

Persistance SQLite. **617 lignes** (mesurées le 2026-08-08). États : `ACTIVE`, `ACKNOWLEDGED`, `SHELVED`,
`RETURNED_NORMAL`, `CLOSED`. Chaque alarme porte `alarm_key`, `trigger_rule`,
`occurrence_count`, `evidence`, et un **historique immuable**.

Transitions journalisées : `APPEARED`, `REPEATED`, `REACTIVATED`,
`ACKNOWLEDGED_BY_OPERATOR`, etc.

> **La colonne `transition` nomme l'ACTION, pas l'état d'arrivée.** Elle recevait
> `target`, si bien que le journal inscrivait « ACTIVE » aussi bien pour une
> désinhibition que pour une réapparition : l'auditeur ne pouvait plus dire
> **pourquoi** l'état avait changé.

Règles établies :

- `condition_presente` est **séparé** de `accepted_alarm` : un désaccord du Judge
  ne résout plus une alarme (AL-2) ;
- l'alarme porte la **constatation dominante**, pas la première évaluée (AL-1) ;
- une alarme `SHELVED` **ne revient pas silencieusement à la normale** ;
- une analyse normale sans clé ne résout rien ;
- les observations concurrentes sont **atomiques** (20 threads, 1 alarme,
  20 occurrences).

**AL-3, ouvert** : une alarme dont la condition cesse **sans réémission du même
code** ne se résout jamais et ne peut pas être close — `close` n'est permis que
depuis `RETURNED_NORMAL`. Le registre n'accumule alors que des ouvertures.

## 6.2 Interventions de maintenance (`workflows.py`)

États : `PLANNED`, `IN_PROGRESS`, `BLOCKED`, `COMPLETED` (+ `TERMINAL_STATES`).
Étapes : `STEP_STATES` avec `NOT_APPLICABLE`, qui vaut `COMPLETED` pour la clôture.

Barrières :

- une **étape dangereuse** est bloquée tant que ses préalables ne sont pas faits ;
- **versionnement optimiste** : `expected_version` ⇒ « Conflit de version » ;
- la clôture exige **toutes les étapes fermées** et une **signature** non vide ;
- une intervention close **ne se reclôt pas** (WF-1) — la signature ne peut plus
  être réécrite sans trace.

`CANCELLED` a été **supprimé** : déclaré, présent dans `TERMINAL_STATES` et le
`CHECK` SQL, mais **aucun producteur ne pouvait l'écrire** (WF-2).

**Le `CHECK` SQL est DÉRIVÉ des constantes Python** par `_contrainte()` (WF-3) :
le vocabulaire vivait auparavant en deux exemplaires qui pouvaient diverger sans
bruit. C'est le motif de S8-2.

## 6.3 Sécurité (`auth.py`, `registry.py`)

- `MIN_PASSWORD_LENGTH = 12`, déclaré dans `auth.py` (il était dans `registry.py`,
  qui importe `auth` — `hash_password` ne pouvait donc pas l'importer et le codait
  en dur).
- Sessions opaques (jeton ≥ 32), jeton **CSRF**, expiration **idle** et **absolue**.
- Allowlist d'e-mails, rôles par utilisateur.
- **Limitation de débit** : 5 tentatives, la 6ᵉ lève `TooManyAttemptsError`
  — **vérifiée avant le mot de passe**. L'événement `LOGIN_RATE_LIMITED` nomme le
  compte visé et la clé client.
- **`rotate()` publie un objet neuf** via `dataclasses.replace`, il ne mute jamais
  la session (SEC-2). Le lecteur ne prend jamais le verrou : `api/main.py` compare
  `X-CSRF-Token` à `session.csrf_token` **verrou relâché**. Muter l'objet donnait
  un **403 sur une requête légitime**. La rotation ne prolonge pas l'expiration
  absolue.

**SEC-3, ouvert** : `auth.py` n'a **qu'un seul** `self._audit.append`, atteint
depuis `authenticate` seul. `rotate()` et `destroy()` n'inscrivent rien — la fin
de session n'est pas tracée.

## 6.4 Notifications (`email.py`, `redaction.py`)

- File asynchrone, **cooldown**, sévérité minimale, déduplication.
- **Trace AVANT dépôt** dans la file (l'inverse perdait l'événement) ;
  `queue.Full` est tracé.
- Une alerte `CRITICAL` **sans destinataire laisse une trace** : compteur
  `undelivered_no_recipient`, ligne « non distribué » au journal, **fichier `.eml`
  dans le spool**. Sans quoi, la nuit ou le week-end, une décision critique
  repartait sans envoi, sans fichier, sans journal et sans compteur.
- `diagnostiquer_echec` traduit l'erreur SMTP en **cause actionnable** :
  « SMTPAuthenticationError » seul n'apprend rien à un exploitant.
- Rédaction française : `RESERVE_LIBELLES` (20 entrées), `ETATS_CONTROLEUR`,
  dates par `_horodatage`. **Aucun identifiant machine ne part dans un courriel.**
- Corps d'alerte : accents obligatoires (« Sévérité », « Équipement »), note au
  format français **« 9,20/10 »**.

## 6.5 Rejeu DCS (`replay.py`)

- **Le module ne transmet aucune fenêtre.** `pipeline.analyze_at(ts)` passe la
  table **entière** ; la troncature a lieu deux couches plus bas, dans
  `detector.analyze` et `_recent_exceedances`. La promesse « seule la fenêtre
  [début, t] est transmise » était fausse — la propriété est vraie **par la
  discipline des appelés**, pas par construction. D'où un test **comportemental** :
  même analyse sur table complète et sur table tronquée ⇒ résultat identique.
- **Décimation** : `analyze_every`. Les **instants incontournables**
  (franchissements de seuil, 62 sur le corpus) sont analysés **même** au pas
  d'allègement — garantie qui ne valait que pour la boucle threadée, `run_sync`
  décimait à l'aveugle.
- `limit=0` signifie **zéro instant**, pas « aucune limite » (`if limit:` → `if
  limit is not None:`).
- La **vitesse publiée est celle qui est appliquée** : le délai valait
  `analyze_every / speed`, donc la vitesse réelle était `speed / analyze_every`
  pendant que l'API publiait `speed` — un facteur 3 sur le seul réglage que
  l'exploitant manipule.

## 6.6 Poste local et interface (ADR-006, ADR-008, ADR-011)

`api/main.py` (1 759 l.) + `api/static/app.js` (2 407 l.) + `twin.js` (2 167 l.,
jumeau numérique Three.js) + `dashboard.html`.

- `/api/health` porte `status_reason` ; `/api/health/database` rend **503 + motifs**.
- `_identite_poste_local()` ; `GATE_LABEL` couvre les 7 portes ; l'evidence n'est
  plus tronquée à 120 caractères.
- **Câblage vérifié** : 110 identifiants dans la page, **99 cherchés par le JS,
  0 manquant**.
- ADR-011 : **langue et provenance à l'écran** — tout libellé affiché est français
  et accentué ; tout libellé comparé est déaccentué.

## 6.7 Invariants de service — vérifiés sans démarrer le service

`tests/test_service_invariants.py` (389 l.) est le plus bel emploi du patron :
onze propriétés établies par **analyse de l'arbre syntaxique**, en quelques
millisecondes, sur des défauts qui ne se voient pas à l'exécution d'une requête
isolée.

| invariant | défaut d'origine |
|---|---|
| aucun handler calculant sur la boucle | **32 handlers sur 47** étaient `async def` sans `await` — dont `auth_login` (PBKDF2, **600 000 itérations**) et `analyze` |
| en-têtes de sécurité en un seul endroit | 401, 403, 500 partaient **sans aucun en-tête** ; **6 en-têtes**, posés par `_durcir` seul |
| config validée avant tout effet de bord | validée seulement au `lifespan`, donc après sessions, registre et CORS |
| client LLM avec délai maximal | `max_retries=0` mais aucun `timeout` : un appel pendu figeait la supervision |
| pas d'allègement hors de la vitesse | **REPLAY_SPEED=120, REPLAY_STEP=3 ⇒ 40 h/s réels** publiés comme 120 |
| `run_sync` consulte `_obligatoires` | la garantie ne tenait que sur la boucle threadée |
| `fit()` invalide le cache | la clé de `score_series` ne décrit que les données, jamais le modèle ; `invalidate_cache()` existait, débranchée |
| durées mises en forme côté serveur | l'ingestion publiait `str(step_nominal)` = « 0 days 01:00:00 », rattrapé par le navigateur |
| aucun outil qualité inerte | mypy configuré, ni installé, ni dans le Makefile, ni en CI |
| bancs du poste exécutés en CI | **84 vérifications** ne bloquaient rien |
| chaque action opérateur a un libellé | `OPERATOR_TRANSITIONS` ≡ `OPERATOR_TRANSITION_LABELS` |

---

# VII. LES TROIS INVENTIONS DU DÉPÔT

## 7.1 `knowledge.seuil(valeur, defaut)`

Teste **l'absence**, pas la fausseté. **L'idiome `x or defaut` est banni** :
un seuil légitime à `0` disparaîtrait. Trois récidives trouvées et corrigées :
`if limit:` (rejeu), `if lead:` (alarmes), et un sentinelle `lead=None` qui
rendait une valeur réelle inexprimable.

## 7.2 `src/formatting.py`

Typographie française, **espace fine insécable U+202F**. Règle absolue :

> **Le texte COMPARÉ est déaccentué par `sans_accents` ; le texte AFFICHÉ est
> accentué.** Sans cette précaution, accentuer correctement casse le test qui
> protège le texte — et l'équipe apprend à ne plus l'accentuer.

## 7.3 « Le patron » — 15 emplois

Un test qui interdit le **retour** d'un défaut par **analyse du source** (`ast`,
`inspect.getsource`, lecture de fichier), non par exécution. Employé quand
exécuter serait trop coûteux (le backtest demande le corpus entier) ou impossible.

Exemples : les portes publiées ont toutes un intitulé à l'écran ; tout état
déclaré est productible ; les poids affichés sont ceux appliqués ; les réserves
sont traduites des deux côtés ; tout identifiant cherché par le poste existe dans
la page.

---

# VIII. CONVENTIONS DE TEST — la méthode

1. **Ne réimplémente pas pour tester.** Importe le prédicat réel. Un test qui
   vérifie sa propre réimplémentation est une tautologie.
2. **Aucun `grep` n'établit une absence.** Les champs sont renommés en transit :
   il faut suivre la donnée jusqu'à son point de rendu.
3. **Prouve par mutation.** Réintroduis le défaut, montre que le contrôle échoue,
   restaure, publie le avant/après.
4. **Un test qui réussit d'autant plus sûrement qu'il ne lit rien ne contrôle
   rien.** Un `if` qui rend l'assertion facultative doit devenir un `skip` déclaré.
5. **La portée de l'assertion doit coïncider avec celle de l'intention.**
   Trop étroite : le test ne couvre pas son nom. Trop large : il gèle une absence
   et devient un obstacle à la correction qu'il devrait appeler.
6. **Normalise avant de comparer** — accents, horodatages, formats. Sinon le
   contrôle mesure la mise en forme, pas le fond.
7. Une **union** d'assertions (`A or B`) rend le test vrai sans rien garantir.
8. **Un contrôle dont le message ment quand il échoue est pire qu'absent** — il
   envoie corriger un défaut qui n'existe pas. Ne compare jamais des chaînes
   sensibles à l'indentation : passe par l'AST.

### Le défaut de test le plus fréquent du dépôt

**La portée de l'assertion ne coïncide pas avec celle de l'intention.** Quatre
formes, toutes rencontrées :

| forme | lots |
|---|---|
| assertion plus étroite que le nom du test | S29-5, S43-1, S45-1 |
| assertion plus large que son objet (gèle une absence) | S44-1 |
| assertion qui ne peut pas échouer (tautologie) | S41-1 |
| assertion qui échoue à tort (faux positif) | S41-3 |

Loin devant l'absence de test. À vérifier en priorité sur tout test relu.

## Fichiers de test

`test_domain.py`, `test_ingest.py`, `test_features_detector.py`,
`test_agents_judge.py`, `test_model_governance.py`, `test_fouling_injection.py`,
`test_sensitivity.py`, `test_kpi.py`, `test_alarm_store.py`, `test_workflows.py`,
`test_access_notifications.py`, `test_operator_registry.py`,
`test_redaction_gouvernance.py`, `test_replay.py`, `test_api.py`,
`test_service_invariants.py`, `test_topology.py`, `test_typographie.py`,
`test_documentation.py`, `test_project_metrics.py`.

Commande unique (Windows PowerShell) :

```powershell
cd C:\dev\ocp-bionic-judge
.\.venv\Scripts\python.exe -m pytest -q
```

---

# IX. TABLEAU DES CHIFFRES

| grandeur | valeur |
|---|---|
| horodatages | 10 182 → 10 180 |
| tags | 12 |
| période | 01/01/2024 → 28/02/2025 (14 mois) |
| heures RUNNING | > 8 000 |
| R² modèle appris | 0,968 |
| R² sans apprentissage | 0,962 |
| corr(résidu, écart consigne) | **−0,938** (arrondi −0,94) |
| T eau de mer Safi | 17,0 → 22,0 °C |
| `PSI_LIMIT` | 0,25 |
| PSI par pli | 1,988 / 3,183 / 0,580 / 0,068 |
| couverture hors plage | 76,5 / 100 / 5,2 / 12,8 % |
| delta epsilon prédit / mesuré | 0,5622 / 0,5620 |
| extrapolation saisonnière pli 4 | 12,8 % |
| plis qualifiés | 0 |
| généralisation | 8,6 % (et non 95,8 %) |
| portes publiées / obligatoires / logicielles | 7 / 5 / 3 |
| portes franchies à l'écran | 3 / 7 |
| poids Judge V1…V8 | 22/16/14/14/15/8/5/6 % |
| plafonds de sécurité | 4,0 et 5,0 |
| épisodes par mois | **4,1** (58 × 30 / 424) — jamais « 5 » |
| criticité plaque sacrificielle | 112 |
| couverture du risque AMDEC | **30,2 %** |
| épisodes agrégés (total, 14 mois) | **58** |
| heures atypiques | **530** |
| instants incontournables (rejeu) | 62 |
| identifiants page / cherchés / manquants | 110 / 99 / 0 |
| objets git | 3 101 (dont 2 887 = `node_modules` mort) |
| capteur saturé TI5303-4X | 327,67 |
| capteur figé PHI5306X-3 | −14,407 |

---

# X. CE QUE LE PROJET NE DOIT PAS AFFIRMER

- que le **banc d'injection** vaut une validation terrain — il est **optimiste** ;
- que le **taux de détection brut** est une performance — la détection est tardive ;
- qu'un **encrassement a été observé** — la règle ne s'est jamais déclenchée sur
  les données réelles ;
- que **UA** mesure l'encrassement seul — il est apparent, le débit d'eau de mer
  n'est pas instrumenté ;
- qu'un **angle mort** est couvert — la plaque sacrificielle ne l'est pas ;
- que le **résidu de duty** dit quoi que ce soit de l'échangeur ;
- que le **PSI** mesure une dérive du procédé.

---

# XI. LE FIL CONDUCTEUR — le motif à 18 occurrences

> **Corrigé à un endroit, pas à son jumeau.** Et **toujours** le code servant
> porte la version juste ; l'affichage ou le document porte la version périmée.

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

**Exemple le plus parlant** — « cinq épisodes par mois », mesuré à **4,1** : présent dans
**cinq documents avec cinq formulations différentes**, dont un commentaire de
`test_documentation.py` qui qualifiait la valeur fausse de « juste ». C'est la
variété des formulations qui a empêché tout motif unique de l'attraper.

C'est l'argument du rapport : il explique **pourquoi** la gouvernance du dépôt est
faite ainsi, au lieu de la décrire.

---

# XII. DÉCISIONS OUVERTES (à l'auteur, jamais tranchées par défaut)

| réf | question |
|---|---|
| AL-3 | alarme dont la condition cesse sans réémission : ni résolue ni closable |
| AL-4 | le chemin nominal doit-il désigner une dominante ? |
| SEC-3 | tracer la fin de session au journal d'audit ? |
| DOM-1 | base `stoichio` déclarée, utilisée par zéro tag |
| ALM-2 | plafonner `ACTION_OVERSIZED` ? |
| FI-1 | le `or` de `test_la_detection_est_tardive_et_le_projet_le_dit` |
| OPS-1 | vérifier la facturation Gemini (clés **non** révoquées, sur demande) |

**Contraintes de l'auteur** : ne pas changer l'API Gemini ; **ne pas pousser le
projet sur GitHub** ; ne jamais commiter depuis une session d'agent.

---

# XIII. RESTE À FAIRE

**Propreté (F3)** — mécanique, ne touche pas au code : supprimer `node_modules/`
et les caches (`__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`,
`.coverage`, `.pytest-tmp`) ; sortir `AUDIT_ADVERSE_2026-07-28.md` et
`AUDIT_PROMPT.md` de la racine ; fusionner les 4 fichiers de reprise de
`docs/audits/`.

**Rapport (F1)** — écrire le chapitre **absent** sur les 7 portes et le backtest
(le mot « PSI » n'apparaît pas dans les 996 lignes actuelles) ; régénérer
`project_metrics.json` ; confronter le « 290 cas de test ».

**Notebooks (F4)** — 7 proposés. Les deux plus utiles : *pourquoi le résidu de
duty est circulaire*, et *pourquoi un test vert ne prouve rien par lui-même*.

**Lecture restante** : `twin.js` (2 167 l.), `test_api.py` (1 043),
`test_features_detector.py` (860), `test_operator_registry.py` (371).
`test_service_invariants.py` a été lu au lot S45. Tout le reste a été lu ligne à ligne.
