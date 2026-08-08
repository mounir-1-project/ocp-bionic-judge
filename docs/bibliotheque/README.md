# La bibliothèque — source unique du rapport

**À toute session qui écrit ou relit le rapport : lis ces documents, pas le
dépôt.** Une relecture du code épuiserait la fenêtre avant le premier livrable —
c'est arrivé deux fois, et c'est la raison d'être de ces fichiers.

N'ouvre un fichier source que pour **vérifier un chiffre précis que tu
t'apprêtes à écrire**, et alors ce fichier-là seulement.

---

## Les quatre documents

| document | lignes | ce qu'il porte |
|---|---|---|
| `partie-A.md` | 2 330 | sections **0 à 16** — le problème, le corpus, ADR-001 et ADR-002, l'architecture, les features, la détection, **l'AMDEC intégrale**, les agents, la gouvernance, les limites, les résultats mesurés, les recommandations |
| `partie-B.md` | **2 526** | sections **17 à 24** — la réalisation, l'API, la validation du modèle, les alarmes, les notifications, le rejeu et la sécurité, la validation logicielle, le déploiement |
| `partie-audit.md` | 775 | la bibliothèque de l'audit : invariants de service, conventions de test, **tableau des chiffres**, décisions ouvertes |
| `dossier-rapport.md` | 186 | la matière condensée du rapport — à lire en premier si le temps manque |

Les deux parties se **concatènent directement** : A occupe les sections 0–16,
B commence à 17. `partie-audit.md` est complémentaire, pas redondante.

## Comment les lire

**Si vous découvrez le projet** → `dossier-rapport.md`, puis `partie-A.md` § 0 à 3.

**Si vous écrivez un chapitre** → la section correspondante, puis
`partie-audit.md` § IX (le tableau des chiffres) pour vérifier chaque valeur.

**Si vous cherchez un chiffre** → `partie-audit.md` § IX d'abord. S'il n'y est
pas, `reports/chiffres_rapport.txt` et `reports/chiffres_front.txt`, qui sont
produits par script et horodatés.

---

## Les marqueurs de provenance

Chaque affirmation en porte un. **Une fusion qui les efface rend la bibliothèque
invérifiable, et le mémoire redevient un texte qu'on croit sur parole.**

| marqueur | sens |
|---|---|
| **[LU]** | établi par lecture intégrale du fichier ; la ligne est citée |
| **[MESURÉ]** | issu d'une exécution ; la date et la commande sont citées |
| **[DÉCLARÉ]** | le dépôt l'affirme, non recalculé — **à éviter** : si c'est mesurable, mesurez-le |

## La règle des chiffres

> **Ne reprenez aucun chiffre d'un commentaire sans l'avoir recalculé.**

Sept l'ont été et étaient faux : « cinq fois la contamination » valait 3,00 ×,
« dépasse 40 % » valait 26,9 %, « 1 385 heures d'arrêt » valait 1 251,
« ~cinq épisodes par mois » valait 4,1, « 57 épisodes sur 59 » valait 58,
« 849 lignes, six routes » valait 952 et deux, « 4,6:1 » valait 4,54:1.

Deux scripts produisent les chiffres, et rien d'autre ne fait autorité :

```powershell
.\.venv\Scripts\python.exe scripts\collecte_chiffres_rapport.py   # -> reports\chiffres_rapport.txt
.\.venv\Scripts\python.exe scripts\collecte_chiffres_front.py     # -> reports\chiffres_front.txt
```

## Corriger là où ça se lit

Piège dans lequel la partie A est tombée, et dont elle est sortie : **signaler en
annexe qu'un chiffre est faux ne suffit pas.** Un rédacteur lit dans l'ordre,
prend le premier chiffre, et n'atteint jamais le démenti.

**Corrigez à chaque occurrence.** Le tableau des divergences est une trace, pas
un correctif.

---

## État au 8 août 2026 — la bibliothèque est complète

**Partie A** : sections 0 à 16.
**Partie B** : sections **17 à 24**, soit les huit chapitres demandés.
**2 526 lignes**, 44 marqueurs `[LU]`, 20 `[MESURÉ]`, **aucun `[DÉCLARÉ]`**.

| § | chapitre | source lue |
|---|---|---|
| 17 | la réalisation — le poste opérateur | `dashboard.html`, `app.js`, `twin.js`, `app.css`, ADR-008 |
| 18 | le contrat d'API | `api/main.py` |
| 19 | la validation du modèle | `src/governance/model_validation.py` |
| 20 | les alarmes ISA-18.2 | `src/operations/alarms.py` |
| 21 | notifications et escalade | `src/notifications/email.py`, `redaction.py` |
| 22 | rejeu temps réel et sécurité | `src/realtime/replay.py`, `src/security/auth.py` |
| 23 | la stratégie de validation logicielle | les 20 fichiers de test |
| 24 | le déploiement | `Dockerfile`, `ci.yml`, `Makefile`, `validate_release.py` |

> **Les tailles de fichier de la consigne ont toutes dérivé.** Mesurées le
> 8 août : `alarms.py` **617** (annoncé 561), `email.py` **546** (512),
> `redaction.py` **312** (294), `replay.py` **502** (430), `auth.py` **414**
> (300), `main.py` **1 830** (1 759), `app.js` **2 445** (2 407). Corrigées là où
> elles se lisent. **Partir de la mesure, jamais de la consigne.**

## Le seul manque : les figures

Aucune des douze n'existe. La plus importante est le nuage **résidu de duty ×
écart de consigne, r = −0,938** — elle montre en un coup d'œil que l'indicateur
de la v2 était l'écart de consigne réécrit, et c'est l'argument qui justifie
toute la refonte.

Attention à la numérotation : la **figure 12** de la partie A est déjà la capture
de la vue Salle, et § 17.9 la reprend en la précisant. La partie B n'ouvre de
nouveaux numéros qu'à partir de **13**.

## Les décisions encore ouvertes, rencontrées en écrivant

| réf | § | question |
|---|---|---|
| **AL-3** | 20.6 | une alarme dont la condition cesse sans réémission ne peut ni se résoudre ni être close |
| **SEC-3** | 22.6 | la fin de session n'est pas tracée au journal d'audit |
| **UI-1** | 17.8 | le front se déclare 19ᵉ occurrence du motif, les tableaux en recensent 18 |
| — | 20.3 | le `CHECK` SQL d'`alarms.py` recopie les constantes au lieu de les dériver, contrairement à `workflows.py` |

Les quatre appartiennent à l'auteur. Aucune n'a été tranchée par défaut.

Avancement détaillé : `docs/audits/ETAT-DE-FUSION.md`.
