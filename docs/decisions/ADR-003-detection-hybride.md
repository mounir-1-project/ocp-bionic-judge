# ADR-003 — Détection hybride : règles AMDEC et Isolation Forest

**Statut** : accepté
**Portée** : couche de détection

---

## Problème

Détecter des comportements anormaux sur douze signaux horaires, sans aucune
anomalie étiquetée. Le problème est non supervisé par nature : aucune métrique
de type AUC ou F1 n'est calculable, et en revendiquer une serait une faute.

## Options

**Seuils seuls.** Traçables et immédiatement acceptés en salle de contrôle,
mais aveugles aux combinaisons anormales de variables individuellement dans
les tolérances.

**Modèle statistique seul.** Voit ces combinaisons, mais produit des alertes
qu'aucun exploitant ne peut rattacher à un mode de défaillance. Un système qui
dit « point atypique » sans dire de quoi il s'agit est désactivé en trois
semaines.

## Décision

Les deux étages fonctionnent ensemble, pas en concurrence.

**Étage 1 — moteur de règles.** Six règles déterministes émettant **quinze
codes** de constatation, chacun encodant une signature de mode de défaillance
issue de l'AMDEC du 23/09/2019 — une même règle gradue sa sortie, ainsi
`CONC_LOW` et `CONC_LOW_LOW`. Toute
alerte se rattache à une ligne de ce document. Une règle ne peut pas halluciner :
elle cite les valeurs qui l'ont déclenchée.

**Étage 2 — Isolation Forest.** Onze features, choisies pour ne garder qu'une
représentation par mécanisme physique. Il capte ce que les règles n'anticipent
pas.

La sévérité finale retient le maximum des deux étages, et les preuves des deux
sont conservées. Un désaccord entre étages est lui-même transmis au contrôleur
de cohérence.

## Choix de conception qui comptent

**Les moyennes glissantes n'entrent pas dans le modèle.** Donner une tendance à
14 jours à un détecteur de points atypiques garantit que *toute* heure d'une
période dérivée soit signalée : le taux de signalement montait à 17 %, et à
65 % sur un mois. Une dérive lente est **un** événement, pas une succession
d'anomalies. Elle relève des règles de persistance, qui exigent 72 heures de
maintien avant de parler.

**Persistance exigée du modèle.** Une alerte n'est émise que si au moins trois
des six dernières heures sont atypiques. Sans cette règle, le modèle émet une
alerte par heure et l'opérateur en reçoit des milliers.

**Seule la marche établie est jugée.** Les états STOPPED et TRANSIENT sont
écartés de l'apprentissage et du jugement. Sans cette séparation, un arrêt
planifié devient l'anomalie la plus grave du corpus.

**Explicabilité par occlusion exacte.** Pour chaque feature, le score est
recalculé en remplaçant cette feature par sa médiane de référence. La chute
mesure sa contribution réelle. C'est exact, déterministe, et directement
lisible : « si UA avait été normal, le score serait tombé de 0,81 à 0,34 ».

## Conséquences

Taux horaire de signalement : 6,2 % des heures de marche, pour 58 épisodes
agrégés sur quatorze mois, soit environ 4,1 par mois. Ce chiffre est publié à
côté de la charge d'épisodes : l'agrégation ne doit pas masquer le volume réel.

La contamination du détecteur reste un paramètre de réglage sans justification
physique. Son influence est mesurée (`make sensitivity`) : le taux réel vaut
environ 2,7 fois la contamination visée, et ce facteur est stable sur toute la
grille testée.
