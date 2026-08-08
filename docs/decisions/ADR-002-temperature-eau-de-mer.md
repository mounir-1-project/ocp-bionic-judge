# ADR-002 — Climatologie de l'eau de mer comme référence externe

**Statut** : accepté
**Portée** : physique de l'échangeur

---

## Problème

Calculer le coefficient d'échange global exige la température du fluide froid.
L'export DCS fourni contient douze tags, tous du côté acide : aucune mesure
côté eau de mer.

Sans cette température, il n'existe aucune façon de distinguer une perte de
performance de l'échangeur d'une variation des conditions extérieures. C'est
la limite qui bloquait tout le raisonnement.

## Ce que l'on sait sans mesure

Le refroidisseur est refroidi à l'eau de mer, à Safi, sur la côte atlantique
marocaine. La température de cette eau n'est pas une inconnue : c'est une
grandeur climatologique documentée, remarquablement stable d'une année sur
l'autre.

Le régime local est dominé par le **courant des Canaries** et l'**upwelling
côtier**, qui maintiennent une eau fraîche et une amplitude annuelle modeste —
environ 5 °C, contre 10 à 12 °C en Méditerranée à latitude comparable.

Climatologie mensuelle retenue, en degrés Celsius :

| J | F | M | A | M | J | J | A | S | O | N | D |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 17,5 | 17,0 | 17,2 | 17,8 | 18,6 | 19,6 | 20,6 | 21,6 | 22,0 | 21,2 | 19,8 | 18,4 |

Minimum en février-mars, maximum en septembre, moyenne annuelle 19,3 °C.

## Décision

La température d'eau de mer est modélisée par interpolation cyclique de cette
climatologie au jour de l'année, et traitée comme une **entrée externe** du
système au même titre que les mesures DCS.

Deux propriétés justifient ce choix :

1. **Indépendance.** La température de l'océan ne dépend d'aucune boucle de
   régulation de l'atelier. C'est précisément ce qui manquait à tous les autres
   candidats indicateurs, et c'est ce qui rend UA interprétable.

2. **Conservatisme.** La prise d'eau d'un refroidisseur industriel est immergée,
   donc thermiquement plus stable que la surface. Les valeurs de surface
   utilisées constituent une **borne haute de l'amplitude réelle** : l'erreur
   introduite va dans le sens d'une sous-estimation de la stabilité de UA, donc
   d'une prudence sur le diagnostic.

## Validation

La cohérence du modèle se vérifie sur les données elles-mêmes. À charge
constante, la température d'entrée acide monte de 89,4 °C en janvier à 96,8 °C
en juillet, puis redescend. Cette respiration annuelle suit la climatologie de
l'eau de mer, et sa prise en compte fait disparaître une « dérive de régime »
qu'une lecture naïve aurait attribuée à une dégradation de l'équipement.

Le point mérite d'être souligné : **le système a d'abord signalé une dérive, et
c'est l'océan Atlantique.**

La référence de conductance ajustée sur ce modèle atteint **R² = 0,924** avec
un écart-type résiduel de **0,63 kW/K**, soit **3,5 %** de la valeur de UA
(17,77 kW/K en référence) — une dispersion compatible avec le bruit de mesure du
débit acide, sous-échantillonné au pas horaire.

*Ces trois valeurs étaient périmées, et incohérentes entre elles : 0,70 kW/K
rapporté à 17,77 donne 3,9 % et non les 3,6 % annoncés. Le rapport technique et
le README publiaient déjà 0,924 / 0,63 / 3,5 %, conformes à l'artefact. Seul cet
ADR portait l'ancien jeu.*

## Conséquences

L'encrassement devient observable, ce qu'il n'était pas. Le calcul reste
valable pour tout refroidisseur du même site ; il devrait être réajusté pour un
site sur une autre façade maritime.
