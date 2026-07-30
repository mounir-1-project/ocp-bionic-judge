# ADR-009 — Une période de référence unique pour les trois références

**Statut** : accepté · **Date** : 2026-07-28

## Problème

Le système apprend trois références sur une période dite « saine » :

| Référence | Cible | Rôle |
|---|---|---|
| `ConductanceReference` | `ua_kw_per_k` | porte le diagnostic d'encrassement |
| `RegulationEffortReference` | `duty_kw` | mesure la conduite |
| `InletReference` | `T_ACID_IN` | contexte thermique amont |

Aucune date de révision de l'équipement ne figure au dossier. À défaut,
`LinearReference.fit` retient les **40 % premières heures de marche établie**.

`ConductanceReference` n'appliquait pas ce repli. Son code filtrait sur
`reference_end` lorsqu'il était fourni, et ne faisait **rien** sinon. Or
`REFERENCE_END` vaut `None` par défaut. Mesure sur le corpus :

```
conductance : 2024-01-01 07:00 -> 2025-02-28 11:00   n = 8 709 h   (100 %)
effort      : 2024-01-01 07:00 -> 2024-07-13 18:00   n = 3 483 h   ( 40 %)
inlet       : 2024-01-01 07:00 -> 2024-07-13 21:00   n = 3 518 h   ( 40 %)
```

La référence qui porte le diagnostic était donc ajustée **sur la totalité des
quatorze mois**, y compris toute dégradation qu'elle est censée détecter. Elle
apprenait l'encrassement comme un comportement normal, et le résidu ne pouvait
plus dériver. C'est la définition d'une fuite de données, et elle explique à
elle seule pourquoi la règle `FOULING_DRIFT` ne s'était jamais déclenchée.

## Options écartées

**Attendre la date de révision d'OCP.** Elle n'est pas au dossier et le projet
doit conclure avec les données dont il dispose. Faire dépendre un résultat d'une
information indisponible revient à ne rien conclure.

**Détecter automatiquement une rupture de régime pour couper la référence.**
Séduisant, mais circulaire : l'algorithme de rupture chercherait précisément le
type de changement que le détecteur doit trouver, et son propre réglage
deviendrait un second paramètre arbitraire à justifier.

**Ajuster sur une fenêtre glissante.** Une référence glissante suit la dérive
et l'absorbe : c'est la même fuite, étalée dans le temps.

## Décision

Les trois références partagent la **même règle et la même période**. La
constante `REFERENCE_FRACTION = 0.40` est définie une fois dans
`src/features/thermal.py` et le repli est explicite dans chaque `fit`.

Le choix de 40 % reste arbitraire, et il est traité comme tel :
`src.governance.sensitivity` mesure ce que devient le diagnostic quand on
déplace cette borne, et le résultat est publié sur l'onglet Contrôle.

## Conséquences

Effet mesuré du seul rebasage de la période de conductance :

| Grandeur | Avant | Après |
|---|---|---|
| Heures d'apprentissage | 8 709 | 3 487 |
| UA de référence | 19,20 kW/K | 17,77 kW/K |
| R² de la référence | 0,920 | 0,924 |
| σ du résidu | 0,70 kW/K | 0,63 kW/K |
| corr(`ua_residual_z`, écart de consigne) | −0,60 | −0,54 |

Le résidu devient à la fois plus serré et moins confondu avec la variable
régulée.

**Résultat de fond sur ce corpus.** Une fois la fuite fermée,
`ua_residual_trend_14d` a une moyenne de **+0,57 σ** et ne descend jamais sous
−1,22 σ : **zéro heure** sous le seuil de déclenchement. Le coefficient
d'échange de la seconde moitié de la période est **supérieur** à celui de la
période de référence. Il n'y a pas d'encrassement sur ces quatorze mois — et ce
n'est plus un silence dont on ne sait que penser, c'est un constat, puisque le
banc d'injection (ADR-010) établit par ailleurs que la règle sait se déclencher.

**Un test verrouille l'alignement** : si une référence retrouvait une période
différente des autres, il échoue.
