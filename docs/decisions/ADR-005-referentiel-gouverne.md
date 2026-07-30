# ADR-005 — Référentiel métier en YAML, hors du code

**Statut** : accepté
**Portée** : couche domaine

---

## Problème

Un système de surveillance industrielle porte des seuils, des criticités, des
rattachements à un plan de maintenance. Ces valeurs appartiennent au métier,
pas au logiciel. Codées en dur, elles rendent toute correction dépendante d'un
développeur, et le référentiel dérive silencieusement du document papier.

## Décision

Trois fichiers YAML portent l'intégralité de la connaissance métier :

| Fichier | Contenu |
|---|---|
| `tags.yaml` | Les douze tags DCS : sens, unité, rôle, plages, seuils, base d'établissement |
| `amdec.yaml` | Transcription de l'AMDEC du 23/09/2019, plan préventif A→H, gammes, check-lists |
| `topology.yaml` | Pièces physiques, position des capteurs, rattachement des codes de règle |

**Aucun seuil, aucun nom de tag, aucune criticité, aucune position de capteur
n'est écrit ailleurs.** Une correction métier se fait dans le YAML, sans
toucher une ligne de code.

## Contrôles associés

L'intégration continue vérifie à chaque modification que :

- la criticité de chaque mode vaut bien F × G × N ;
- toute tâche préventive citée existe dans le plan ;
- la topologie ne cite aucun tag, mode ou composant inexistant ;
- tout code émis par le détecteur possède un rattachement déclaré.

Ce dernier point corrige un défaut réel : le rattachement d'une anomalie à une
pièce était auparavant improvisé côté interface par recherche de sous-chaîne.
Un code comme `CONC_DROP_SEVERE` — signature d'une fuite de tube, l'événement
le plus grave que le système puisse voir — ne désignait alors aucune pièce.

Un code absent de la table n'allume rien : mieux vaut ne rien montrer
qu'accuser la mauvaise pièce.

## Conséquences

Le référentiel est directement réutilisable sur les autres refroidisseurs de
PS II et PS III : seuls les tags et les plages changent.
