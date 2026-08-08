# Documentation E7301 — où lire quoi

Ce dossier contient quatre natures de documents, et les confondre fait perdre du
temps. La règle est simple :

> **`bibliotheque/` dit ce que le système EST. `audits/` dit comment on l'a
> découvert. `decisions/` dit pourquoi il est ainsi. Le reste sert à s'en
> servir.**

---

## Je veux…

| … | lire |
|---|---|
| **comprendre le projet en 10 minutes** | `README.md` (racine du dépôt), puis `architecture.md` |
| **écrire ou relire le rapport** | `bibliotheque/` — commencer par son `README.md` |
| **savoir pourquoi tel choix technique** | `docs/decisions/INDEX.md`, puis l'ADR concerné |
| **exploiter le poste au quotidien** | `docs/runbooks/runbook-operations.md` |
| **savoir ce que signifie un tag DCS** | `data_dictionary_E7301.md` |
| **relier une exigence à son test** | `traceability_matrix_E7301.md` |
| **retrouver la preuve d'un constat d'audit** | `docs/audits/analyse-architecture.md` |
| **savoir où en est le chantier** | `docs/audits/ETAT-DE-FUSION.md` |

---

## `bibliotheque/` — la source unique du rapport

Quatre documents, ≈ 4 100 lignes, **chaque affirmation portant un marqueur de
provenance**. C'est là qu'on écrit et c'est là qu'on vérifie. Détail dans
`docs/bibliotheque/README.md`.

Ces documents sont soumis aux quatre contrôles de `tests/test_documentation.py` :
chemin cité inexistant, lien mort, test inexistant, chiffre contredisant un
artefact. **C'est voulu** — ce sont eux qui alimentent le mémoire.

## `decisions/` — les onze ADR

Un ADR répond à « pourquoi ce choix plutôt qu'un autre ». Les trois qui portent
le projet :

- **ADR-001** — le résidu de duty est algébriquement circulaire, il ne peut pas
  fonder un diagnostic d'encrassement ;
- **ADR-002** — l'indicateur réel est UA, calculé par efficacité-NTU, et la
  température d'eau de mer vient de la climatologie de Safi ;
- **ADR-008** — l'interface applique les principes ISA-101.

`docs/decisions/INDEX.md` les liste tous.

## `audits/` — l'histoire, pas le système

**Ce dossier est délibérément exempté** des contrôles de documentation, et la
raison est un contrat, pas une commodité : un journal d'audit cite par
construction des routes supprimées, des fichiers renommés et des chiffres
retirés — c'est son objet, et c'est ce qui rend une correction retraçable.

Conséquence à respecter : **aucune documentation d'usage ne doit être écrite
sous `audits/`**, elle y échapperait à toute vérification.

| document | rôle |
|---|---|
| `ETAT-DE-FUSION.md` | **vivant** — où en est le chantier, ce qui reste |
| `OBJECTIFS-FINAUX.md` | **vivant** — ce qui doit être livré avant de clore |
| `CONSIGNE-BIBLIOTHEQUE-B.md` | **vivant** — consigne de rédaction, avec ses amendements |
| `analyse-architecture.md` | archive, 10 336 l. — le journal intégral, avec les preuves |
| `AUDIT_ADVERSE_2026-07-28.md` | archive — l'audit adverse et son verdict |
| `AUDIT_PROMPT.md` | archive — le prompt qui l'a produit |
| `passations/` | archive — les reprises de session successives |

## Documents d'usage, à la racine de `docs/`

| document | rôle |
|---|---|
| `architecture.md` | la chaîne, module par module |
| `rapport_technique.md` | le rapport technique en cours de refonte |
| `data_dictionary_E7301.md` | les 12 tags DCS et leur sens établi |
| `traceability_matrix_E7301.md` | exigence → implémentation → test |
| `docs/runbooks/runbook-operations.md` | exploitation du poste |

## Les huit sources OCP

Les fichiers numérotés `1-` à `8-` sont les **documents métier d'origine** :
fiche équipement, fiche sous-ensemble, liste des composants, AMDEC du 23/09/2019,
plan de maintenance préventive, check-list d'inspection, gamme PV, gamme de
tamponnage. Ils ne sont ni modifiés ni régénérés — toute cotation AMDEC marquée
`ocp_source` en descend directement.

---

## La règle qui vaut pour tout ce dossier

> **Ce qui est exécuté reste juste. Ce qui est seulement lu dérive.**

Dix-huit occurrences recensées où une correction n'a été portée qu'à un endroit,
et presque toujours dans le même sens : le code de service porte la version
juste, le document la version périmée. La mesure du 8 août 2026 le confirme sur
le poste opérateur — sur 65 assertions chiffrées portées par des commentaires,
trois étaient fausses ; sur les grandeurs réellement exécutées, aucune.

C'est pourquoi la documentation de ce dépôt est testée.
