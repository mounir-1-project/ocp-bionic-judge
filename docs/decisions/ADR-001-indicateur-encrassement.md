# ADR-001 — Le coefficient d'échange global comme indicateur d'encrassement

**Statut** : accepté
**Portée** : cœur analytique du système

---

## Problème

Détecter l'encrassement du faisceau tubulaire (mode AMDEC `FAISCEAU_BOUCHAGE`,
criticité 105) à partir des seuls signaux DCS disponibles.

La difficulté est que **la température de sortie acide est régulée**. Sa
distribution sur quatorze mois est P1 = 63,7 °C, P99 = 66,6 °C : une bande de
3 °C. Tant que la boucle tient, elle compense toute perte de performance en
ouvrant la vanne d'eau de mer. Un seuil ou un z-score sur ce signal ne voit
rien, et quand il voit enfin quelque chose, la dégradation est consommée.

## Option écartée — le résidu de puissance évacuée

Une première approche consistait à surveiller « l'effort » plutôt que le
résultat : modéliser la puissance évacuée attendue selon les conditions
d'exploitation, et suivre le résidu.

**Cette approche est fausse, et l'erreur est algébrique.** La puissance est
calculée par définition :

```
Q = ρ·cp · F · (T_entrée − T_sortie)
```

Le modèle de référence la régresse sur `F`, `T_entrée` et le produit
`F × T_entrée`. Comme `T_sortie` est régulée autour de 66 °C, la cible s'écrit

```
Q ≈ ρ·cp · F · T_entrée  −  ρ·cp · 66 · F
```

soit déjà une combinaison linéaire de deux régresseurs présents. La régression
ne modélise pas l'échangeur : elle retrouve sa propre définition.

Mesures qui l'établissent, sur le corpus :

| Grandeur | Valeur |
|---|---|
| R² de la référence apprise | 0,968 |
| R² d'une reconstruction sans aucun apprentissage | 0,962 |
| Apport réel du modèle | **+0,006** |
| Corrélation résidu ↔ écart de consigne | **−0,94** |
| Variance partagée | 88 % |

Le résidu de puissance **est** l'écart de consigne, changé de signe et pondéré
par le débit. Il est conservé sous le nom `regulation_effort`, qui dit ce qu'il
mesure, et il ne fonde jamais un diagnostic d'encrassement.

## Décision

L'encrassement est diagnostiqué sur le **coefficient d'échange global UA**,
calculé par la méthode efficacité-NTU :

```
ε   = (T_entrée − T_sortie) / (T_entrée − T_eau_de_mer)
NTU = −ln(1 − ε)
UA  = C_acide · NTU
```

La température d'eau de mer provient de la climatologie de Safi (voir
[ADR-002](ADR-002-temperature-eau-de-mer.md)). C'est ce qui rend l'indicateur
interprétable : une grandeur extérieure à l'atelier, qu'aucune boucle de
régulation ne contraint.

UA varie légitimement avec le régime — le débit gouverne la turbulence, et la
viscosité de l'acide chute fortement avec la température. Une référence
linéaire apprend `UA(F^0.8, T_moyenne, T_eau_de_mer)` sur la période de
référence ; le résidu est l'indicateur d'encrassement.

La résistance d'encrassement `Rf = 1/UA − 1/UA_référence`, en K/kW, est la
grandeur suivie par le service fiabilité pour arbitrer la date du prochain
nettoyage.

## Conséquences

**Ce qui est gagné.** L'indicateur est physique, deséasonnalisé, et ne partage
plus que 29 % de sa variance avec la variable régulée au lieu de 88 %.

**Performance mesurée** par injection d'encrassement simulé sur données réelles
(`make bench-fouling`) :

| Perte de UA injectée | Détectée à |
|---|---|
| 30 % | 32 % d'avancement — 464 h |
| 20 % | 39 % d'avancement — 561 h |
| 10 % | 87 % d'avancement |
| 5 % | en fin de rampe seulement |

Faux positifs sur les données non modifiées : **0 %**.

**Résultat sur l'équipement.** Sur quatorze mois, aucune dérive descendante de
UA. À saison comparable, février 2024 → février 2025, UA passe de 15,4 à
18,6 kW/K : la surface d'échange transmet mieux, pas moins bien. Le faisceau
n'est pas encrassé.

**Coût.** Le calcul dépend d'une donnée climatologique externe. Elle est stable
d'une année sur l'autre et documentée, mais elle constitue une entrée
supplémentaire à maintenir si l'équipement était dupliqué sur un autre site.
