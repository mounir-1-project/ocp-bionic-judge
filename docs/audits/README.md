# `docs/audits/` — l'histoire du projet, pas sa description

Ce dossier raconte **comment le système a été audité et corrigé**. Il ne décrit
pas le système tel qu'il est aujourd'hui : pour cela, voir `../bibliotheque/` et
`../architecture.md`.

## Pourquoi ce dossier échappe aux contrôles de documentation

`tests/test_documentation.py` vérifie que la documentation ne cite ni chemin
inexistant, ni lien mort, ni test absent, ni chiffre contredisant un artefact.
**Ce dossier en est écarté, et c'est un contrat, pas une commodité :**

> Un journal d'audit cite par construction des routes supprimées
> (`/api/business/assumptions`), des fichiers renommés, des scripts effacés et
> des montants retirés. C'est précisément son objet — c'est ce qui rend une
> correction retraçable. Les soumettre aux contrôles obligerait à échapper chaque
> citation, donc à rendre le journal illisible pour satisfaire une vérification
> qui ne le vise pas.

**Contrepartie, à respecter :** aucune documentation d'usage ne doit être écrite
ici, elle y échapperait à toute vérification. C'est la raison pour laquelle
`BIBLIOTHEQUE.md` et `DOSSIER-RAPPORT.md` ont été déplacés vers
`../bibliotheque/` le 8 août 2026 — ce sont des sources du rapport, pas des
journaux, et ils doivent être vérifiés.

---

## Vivant — à lire si vous reprenez le travail

| document | rôle |
|---|---|
| `ETAT-DE-FUSION.md` | **où en est le chantier**, ce qui est levé, ce qui demeure |
| `OBJECTIFS-FINAUX.md` | ce qui doit être livré avant de clore — rapport, notebooks |
| `CONSIGNE-BIBLIOTHEQUE-B.md` | consigne de rédaction de la partie B, **avec ses amendements** |

> **Lisez toujours les amendements de la consigne.** Ils sont en fin de fichier
> et corrigent deux prémisses devenues fausses. Une version tronquée traînait
> dans `docs/` ; elle a été supprimée le 8 août 2026.

## Archive — on n'y va que pour retrouver une preuve

| document | lignes | contenu |
|---|---|---|
| `analyse-architecture.md` | 10 336 | le journal intégral, lot par lot, avec la démonstration de chaque constat |
| `AUDIT_ADVERSE_2026-07-28.md` | 336 | l'audit adverse et son verdict « non livrable en l'état » |
| `AUDIT_PROMPT.md` | 296 | le prompt qui l'a produit, réutilisable |
| `passations/` | 1 391 | les reprises de session successives — **périmées**, conservées pour la méthode |

`passations/` contient `reprise-de-session.md`, `REPRISE-src.md` et
`plan-de-reorganisation.md`. Leur contenu opérationnel est dépassé : tout `src/`
a été relu, la réorganisation est faite. Ils gardent une valeur de **méthode**,
pas d'instruction.

---

## Ce que l'audit a établi, en une ligne

> **Ce qui est exécuté reste juste. Ce qui est seulement lu dérive.**

Dix-huit occurrences d'une correction portée à un endroit et pas à son jumeau, et
presque toujours dans le même sens. Trois exceptions connues — S27-2, S32-1,
S46-1 — et la troisième reformule la règle : la frontière n'est pas
code / document, elle est **exécuté / seulement lu**. Commentaires et docstrings
sont de la documentation qui habite le code ; ils vieillissent comme des
documents, parce que rien ne les exécute.
