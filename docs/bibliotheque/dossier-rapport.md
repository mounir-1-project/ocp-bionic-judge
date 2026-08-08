# Dossier de rédaction du rapport — source unique

**À la session qui écrit le rapport : ne relis AUCUN fichier source.**
Tout ce qui suit a été mesuré sur les lots S1–S44. Les chiffres sont ici. Lis
ce fichier (≈200 lignes) et écris. Relire le dépôt épuiserait la fenêtre avant
la première page — c'est arrivé, c'est la raison d'être de ce document.

Ne va vers un fichier source que pour **vérifier un chiffre précis** que tu
t'apprêtes à écrire, et alors ouvre ce seul fichier.

---

## 1. L'équipement et le corpus

E7301 — refroidisseur d'acide sulfurique Chemetics, SIZE 1118-9754, tubes 904L.
Eau de mer côté tubes, acide côté calandre. Atelier PS III, site OCP Safi.

14 mois d'export DCS réel : **10 182 horodatages, 10 180 après déduplication**
(2 doublons, résolus par ordre source), **12 tags**, du 01/01/2024 au 28/02/2025.
Aucune imputation : un trou reste un trou. Deux capteurs écartés du périmètre —
TI5303-4X saturé à 327,67 depuis août 2024 (>4 000 heures), PHI5306X-3 figé à
−14,407 sur les premiers mois.

Aucune fiche d'instrumentation ne accompagnait l'export : le sens des 12 tags a
été établi par recoupement, chaque détermination citant **au moins deux bases
indépendantes** parmi `isa_5_1`, `process`, `data`, `climatology`.

## 2. La correction scientifique — le cœur du rapport (ADR-001, ADR-002)

**Le résidu de duty est algébriquement circulaire.** Mesuré :

| | R² |
|---|---|
| modèle appris | 0,968 |
| **sans aucun apprentissage** | 0,962 |

L'apprentissage n'apporte que 0,006. Et `corr(résidu, écart de consigne) = −0,94` :
le résidu mesure l'action du régulateur, pas l'état de l'échangeur. Renommé
`regulation_effort`. **Il ne fonde plus jamais un diagnostic d'encrassement.**

**L'indicateur réel est UA**, par efficacité-NTU, avec la climatologie d'eau de
mer de Safi (**17,0 °C** fév.–mars → **22,0 °C** septembre) — la seule entrée
externe à toute boucle de régulation. UA est **apparent** : le débit d'eau de
mer n'est pas instrumenté. Cette limite doit être écrite, pas atténuée.

## 3. Le chapitre ABSENT — les 7 portes de déploiement

Le poste affiche « 3 / 7 portes franchies ». Les 996 lignes du rapport n'en
disent **pas un mot**, et le mot « PSI » n'y figure pas une seule fois. C'est le
chapitre à écrire.

- **7 portes publiées**, `MANDATORY_GATES` = 5, `SOFTWARE_GATES` = 3.
- `labels_gmao` et `validation_externe` échouent **définitivement** : aucune
  vérité terrain, aucune validation externe. Ce n'est pas un défaut à corriger,
  c'est une limite à déclarer.
- Deux portes sont **publiées, en échec, et volontairement NON bloquantes** :
  `redondance_hors_modele` (propriété algébrique permanente, ADR-001) et
  `derive_de_distribution` (aucun pli saisonnièrement couvert). Restreindre le
  critère « pour qu'il passe » remasquerait ce que l'auteur a rendu visible.
  Verrouillé par `test_une_porte_publiee_non_bloquante_n_empeche_pas_la_promotion`.

### Le PSI ne mesure pas une dérive

`PSI_LIMIT = 0,25`. Valeurs par pli : **1,988 / 3,183 / 0,580 / 0,068**
(relues dans `reports/model_validation.json`, 2026-08-08).

La preuve publiée accusait « deux excursions de sur-refroidissement ». Les plis
la réfutent : **les plis 3 et 4 testent les périodes les PLUS RÉCENTES et dérivent
le MOINS, d'un facteur 55**. Une dérive ferait l'inverse.

Cause réelle : correspondance forte mais **non strictement monotone** — cinq
paires concordantes sur six, τ de Kendall +0,667 — avec la part d'heures de test
hors de la plage d'eau de mer apprise :

| pli | couverture hors plage | PSI |
|---|---|---|
| 1 | 76,5 % | 1,988 |
| 2 | 100 % | 3,183 |
| 3 | 5,2 % | 0,580 |
| 4 | 12,8 % | 0,068 |

**Le PSI mesure la couverture saisonnière du découpage, pas une dérive du procédé.**
Troisième banc du dépôt dont le dénominateur contenait des non-événements
(après S6-2 et S7-1).

Correction d'epsilon confirmée à 0,0002 près : plancher `0,5/n` au lieu de `1e-6`,
delta prédit par décile vide 0,5622, mesuré 3,7446 → 3,1826 = **0,5620**.

### Généralisation : 8,6 %, pas 95,8 %

Le chiffre honnête est 8,6 %. Écrire pourquoi les deux nombres existent et
pourquoi le second ne veut rien dire est le passage le plus utile du rapport.

## 4. Le Judge

`VerificationLayer.WEIGHTS` — V1 22 %, V2 16 %, V3 14 %, V4 14 %, V5 15 %,
V6 8 %, V7 5 %, V8 6 %. Plafonds de sécurité 4,0 et 5,0, appliqués par
`_apply_safety_cap`. Verrouillé par `test_les_poids_affiches_sont_ceux_que_le_juge_applique`.

## 5. Trois inventions du dépôt, à expliquer au jury

1. **`knowledge.seuil(valeur, defaut)`** — teste l'ABSENCE, pas la fausseté.
   L'idiome `x or defaut` est banni. Trois récidives trouvées et corrigées :
   `if limit:` (S14), `if lead:` (S42), et le sentinelle `lead=None` (S42).
2. **`src/formatting.py`** — typographie française, espace fine insécable U+202F.
   Règle : **le texte comparé est déaccentué par `sans_accents`, le texte affiché
   est accentué.** Sans quoi accentuer correctement casse le test qui protège.
3. **« Le patron »** — un test qui interdit le retour d'un défaut **par analyse
   du source** (AST, `inspect.getsource`), non par exécution. 15 emplois.

## 6. Le fil conducteur — le motif à 18 occurrences

> **Corrigé à un endroit, pas à son jumeau.** Et **toujours** le code servant
> porte la version juste, l'affichage ou le document la version périmée.

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

Exemple le plus parlant — « cinq épisodes par mois », mesuré à **4,1** (58 × 30 / 424) :
présent dans **cinq documents avec cinq formulations différentes**, dont un
commentaire de `test_documentation.py` qui qualifiait la valeur fausse de
« juste ». C'est la variété des formulations qui a empêché tout motif unique de
l'attraper.

**C'est l'argument du rapport** : il explique POURQUOI la gouvernance du dépôt
est faite ainsi, au lieu de la décrire.

## 7. Vérifications d'interface et de dépôt

- Câblage du poste : **110 identifiants dans la page, 99 cherchés par le JS, 0 manquant.**
- Historique git : 3 101 objets. `.env` et `operators.json` **jamais** présents.
  2 887 objets (93 %) proviennent d'un dossier frontend/node\_modules mort,
  supprimé depuis mais conservé dans l'historique. Non réécrit — l'opération est
  destructive et invaliderait le tag `v3.0.0`.
  *(Le chemin est écrit sans guillemets techniques à dessein : il ne désigne
  aucun dossier actuel, et le contrôle des chemins cités le prendrait pour tel.)*
- **État au 8 août 2026** : **162 fichiers suivis**, `node_modules` n'est pas
  tracké, 23 commits. Onze objets temporaires abandonnés par des opérations git
  interrompues ont été retirés de `.git`.

## 8. Ce que le rapport ne doit PAS affirmer

- que le banc d'injection vaut une validation terrain — il est **optimiste**, il
  ne simule pas la compensation par la vanne d'eau de mer ;
- que le taux de détection brut est une performance — la détection est **tardive**,
  elle constate plus qu'elle n'anticipe ;
- que l'encrassement a été observé — la règle ne s'est **jamais** déclenchée sur
  les données réelles ; c'est le banc qui répond « le détecteur verrait-il ? » ;
- qu'un angle mort est couvert — `PLAQUE_SACRIFICIELLE_DYSFONCTION`, criticité
  112, n'est pas instrumenté et est déclaré tel.

## 9. Après le chapitre : trois tâches courtes

1. Régénérer `project_metrics.json` et confronter le « 290 cas de test » affiché.
2. Élargir `test_aucun_chiffre_cle_ne_contredit_les_artefacts` aux chiffres ci-dessus.
3. Vérifier que chaque nombre écrit dans le rapport existe dans un artefact.

## 10. Les sept erreurs de l'auditeur — matière du notebook n° 2

| # | lot | nature |
|---|---|---|
| 1 | S21-2 | extrapolation calculée sur le calendrier, pas sur les heures de marche |
| 2 | S23-6 | nom de classe inféré ; il était 435 lignes plus haut dans le fichier |
| 3 | S25-1 | contenu du rapport affirmé sans l'avoir lu |
| 4 | S29-5 | prédicat de forme ; tests ajoutés à un fichier non lu |
| 5 | S38-1 | symétrie affirmée contre une causalité documentée |
| 6 | S41-1 | tautologie : le test vérifiait sa propre réimplémentation |
| 7 | S41-3 | comparaison de deux représentations au lieu de deux valeurs |

**Les sept ont la même cause — conclure avant d'avoir lu — et les sept ont été
trouvées par la lecture, jamais par l'exécution.** Un test vert ne prouve rien
par lui-même : c'est le sujet du second notebook, et le plus utile.
