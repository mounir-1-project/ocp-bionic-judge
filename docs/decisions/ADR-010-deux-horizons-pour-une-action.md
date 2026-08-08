# ADR-010 — Séparer le délai de qualification de la fenêtre d'exécution

**Statut** : accepté · **Date** : 2026-07-28

## Problème

L'action recommandée ne portait qu'une seule grandeur temporelle, `urgency`,
dérivée mécaniquement de la sévérité :

```
WARNING  -> SOUS_24H
CRITICAL -> SOUS_8H
```

Le texte de l'action était, lui, construit à partir du plan préventif OCP. La
combinaison produisait des recommandations qui se contredisent dans la même
phrase. Exemple réellement affiché en salle :

> **SOUS_24H** — Mesure des épaisseurs (courant de Foucault), tâche A du plan
> préventif : *Mesure des épaisseurs de la calandre* (**4 ans**). Cette
> intervention exige un arrêt process et la consignation des circuits acide et
> eau de mer — **à programmer avec la production, pas à exécuter en marche**.

Le système réclamait sous 24 heures une opération à cadence quadriennale qui
suppose de vider et consigner l'appareil. Un exploitant lit cela une fois, en
conclut que l'outil ne connaît pas le métier, et cesse de le consulter.

La faute n'est pas dans le texte : elle est dans le modèle de données. Une
seule grandeur portait **deux questions sans rapport**.

- Sous quel délai un ingénieur fiabilité doit-il **qualifier** la constatation ?
  C'est une question de sévérité. Une dérive du faisceau mérite un regard sous
  24 h même si rien ne sera démonté avant des mois.
- Dans quelle fenêtre d'exploitation l'intervention peut-elle être **exécutée** ?
  C'est une question d'état requis par la tâche, et la sévérité n'y change rien :
  aucune urgence ne rend réalisable en marche une opération sous consignation.

## Décision

`RecommendedAction` porte désormais deux champs indépendants.

| Champ | Question | Source |
|---|---|---|
| `urgency` | délai de qualification | sévérité de la constatation |
| `execution_window` | fenêtre d'exécution | champ `etat` de la tâche du plan préventif |

`execution_window` prend trois valeurs : `EN_MARCHE`, `ARRET_PROGRAMME`,
`ARRET_IMMEDIAT`. Seule une sévérité CRITICAL fait passer de `ARRET_PROGRAMME`
à `ARRET_IMMEDIAT` — et le texte dit alors explicitement que la mise à l'arrêt
relève de la décision d'exploitation, pas de l'outil.

Le message énonce les deux horizons côte à côte, ce qui empêche de lire
« sous 24 h » comme un ordre d'intervention immédiate :

> Deux horizons distincts : la constatation doit être qualifiée par le service
> fiabilité sous 24 heures, tandis que l'intervention elle-même exige un arrêt
> process et la consignation des circuits — elle se cale sur le prochain arrêt
> programmé.

## Le contrôleur vérifie la cohérence

Le contrôle V4 gagne deux vérifications, et elles sont symétriques :

- une action annoncée `EN_MARCHE` alors que la tâche exige la consignation est
  sanctionnée `UNSAFE_ACTION`, **note plafonnée à 4/10** par
  `_apply_safety_cap` ;
- une action réclamant un arrêt que le plan n'exige pas est sanctionnée
  `ACTION_OVERSIZED` — immobiliser une ligne sans nécessité est aussi une faute.

*Les deux chiffres de ce paragraphe étaient faux.* Le premier annonçait **1/10**
là où le plafond appliqué vaut **4,0** — la valeur que publient le rapport
§ 7.3 et le README. Le second annonçait un plafond de 4/10 pour
`ACTION_OVERSIZED` : **il n'en existe aucun.** Le code ne plafonne que
`UNSAFE_ACTION`, `HALLUCINATED_VALUE`, `INVENTED_AMDEC_MODE`,
`BLIND_SPOT_CLAIM` et la sévérité critique minimisée (4,0), plus l'état de
marche erroné (5,0). Un arrêt injustifié ne coûte donc aujourd'hui que le poids
de V4, soit 14 %.

**La question de fond reste ouverte, et elle est posée ici plutôt que tranchée
en silence** : faut-il plafonner `ACTION_OVERSIZED` ? L'argument de cet ADR —
immobiliser une ligne sans nécessité est une faute — plaide pour. Le faire
modifie le comportement du contrôleur et les chiffres du banc; cela relève
d'une décision, pas d'une correction documentaire.

## Effet de bord corrigé

Le test de l'état requis se faisait par `"Arret" in task["etat"]`, dans deux
modules distincts. L'accentuation du référentiel en « Arrêt process » aurait
fait passer silencieusement toutes les interventions sous consignation pour des
interventions réalisables en marche — une régression de sécurité provoquée par
une correction typographique.

La question est désormais posée à un seul endroit,
`DomainKnowledge.task_requires_shutdown`, qui normalise les diacritiques avant
de comparer.

## Conséquences

Sur les instants notables du corpus, toutes les constatations `WARNING`
rattachées au faisceau ressortent en `SOUS_24H` / `ARRET_PROGRAMME` : la
qualification est rapide, l'intervention est planifiée. Plus aucune
recommandation ne se contredit.
