# ADR-008 — Interface conforme aux principes ISA-101

**Statut** : accepté
**Portée** : interface opérateur

---

## Problème

Une interface de supervision industrielle n'est pas un tableau de bord
d'entreprise. Elle est regardée huit heures d'affilée, souvent en vision
périphérique, et sa fonction est de faire remarquer ce qui sort de l'ordinaire
— pas d'être belle.

La première version de ce poste appliquait les réflexes du web : couleurs
saturées partout, cartes arrondies, dégradés. Sur un tel écran, une alarme rouge
ne ressort pas, parce que tout ressort.

## Décision

L'interface applique les principes de la norme **ANSI/ISA-101.01**, qui encadre
les interfaces homme-machine des systèmes d'automatisation de procédé.

### 1. La couleur est réservée à l'anormal

C'est le principe le plus mal compris de la norme — souvent réduit à tort à
« tout mettre en gris ». L'intention réelle est que **la saturation soit une
ressource rare** : si la couleur ne signale rien, elle ne signale plus rien.

En fonctionnement nominal, l'écran est neutre. Les teintes procédé — ambre pour
l'acide, turquoise pour l'eau de mer — restent désaturées et servent à
identifier un circuit, pas à attirer l'œil. Le rouge et l'ambre saturés
n'apparaissent que sur un état anormal.

### 2. La gravité n'est jamais portée par la seule couleur

Environ 8 % des hommes ne distinguent pas le rouge de l'ambre, et une capture
en noir et blanc les confond toujours. Chaque état porte donc un **glyphe**, un
**mot** et une **couleur**, et les bordures d'alarme portent en plus un motif
distinct — trait plein pour l'avertissement, trait double pour le critique.

Contraste vérifié : 4,6:1 minimum sur les micro-libellés, conforme au niveau AA.

### 3. Hiérarchie de vues

Trois niveaux, du général au détail, conformément à la structure hiérarchique
de la norme :

| Vue | Rôle |
|---|---|
| **Salle** | État de l'appareil, situation prioritaire, décision attendue |
| **Intégrité** | Épisodes, santé des capteurs, couverture AMDEC, plan préventif |
| **Contrôle** | Cohérence des décisions, sensibilité, bancs de validation |

Le jumeau 3D occupe la vue principale : cliquer un capteur ouvre sa fiche,
cliquer une pièce ouvre les modes de défaillance qu'elle porte. La navigation
suit l'équipement, pas une arborescence de menus.

### 4. Les trois niveaux de conscience de situation

Le modèle d'Endsley, qui structure la norme, distingue **percevoir**,
**comprendre** et **projeter**. Les deux premiers niveaux étaient traités ; le
troisième manquait.

Chaque grandeur du bandeau de lecture porte désormais sa **tendance** : sens et
vitesse d'évolution sur la fenêtre récente. Un opérateur voit non seulement où
il est, mais où il va.

### 5. Fluidité

Une interface qui saccade est une interface qu'on cesse de regarder.

- La série temporelle n'est rechargée que si la fenêtre demandée a changé ;
  auparavant 650 points étaient retransmis toutes les 1,6 seconde pour déplacer
  un curseur d'un pixel.
- Le rendu 3D se dégrade tout seul sous 22 images par seconde — ombres d'abord,
  puis résolution — ce qui préserve l'interactivité sur un poste à carte
  graphique intégrée.
- Le moteur 3D est suspendu hors de sa vue.
- Les transitions de vue et les apparitions de panneau sont animées, et toutes
  les animations s'effacent si le système déclare `prefers-reduced-motion`.

## Conséquences

Une seule feuille de style, sans couche de rattrapage. La précédente
implémentation en empilait deux, de thèmes opposés, dont l'une était
majoritairement inerte.

L'accès clavier complet à la scène 3D est assuré : orientation aux flèches,
zoom, parcours des capteurs, ouverture — un `<canvas>` n'étant pas focusable par
défaut, sans ce traitement la scène serait inaccessible sans souris.
