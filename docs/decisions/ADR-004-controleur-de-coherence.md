# ADR-004 — Contrôleur de cohérence déterministe

**Statut** : accepté
**Portée** : gouvernance de la décision

---

## Problème

Un système de diagnostic automatique qui ne sait pas dire quand il se trompe
est inexploitable en environnement industriel. Il faut donc un contrôle sur la
décision produite.

## Option écartée — le juge par modèle de langage

Confier ce rôle à un modèle de langage à qui l'on montre le diagnostic ne
produit qu'un tampon de conformité. Trois défauts structurels, indépendants du
prompt :

1. **Aucune source de vérité indépendante.** Le juge ne voit que ce que l'agent
   raconte. Si l'agent écrit « température 85 °C » alors que le capteur indique
   66 °C, le juge n'a aucun moyen de le savoir. Il note la *cohérence interne*
   d'un texte, pas sa *véracité*.
2. **Complaisance structurelle.** Un modèle à qui l'on demande de noter une
   production plausible note haut.
3. **Non-reproductibilité.** Note variable d'un appel à l'autre, dépendance à
   un quota réseau. Inutilisable comme dispositif de gouvernance.

## Décision

Le contrôleur **recalcule les faits** depuis la même chaîne de données et de
règles, puis confronte chaque affirmation du diagnostic à ce recalcul. Huit
contrôles logiques, déterministes et reproductibles. Le modèle de langage
n'intervient qu'ensuite, pour la rédaction, dans un corridor borné de ±1,5
point, et sans droit de veto sur un fait établi.

Certains manquements ne sont pas compensables par une moyenne pondérée. Des
plafonds l'interdisent : valeur inventée, mode inexistant, angle mort
revendiqué, action dangereuse et sévérité critique minimisée plafonnent la note
à 4/10.

## Ce que le banc d'évaluation mesure réellement

Le banc soumet au contrôleur des décisions délibérément fausses. **Ce n'est pas
une validation, et le rapport le dit.** Chaque piège porte le code d'anomalie
que le contrôleur implémente déjà : on fabrique une faute conçue pour
déclencher V1, puis on mesure que V1 la détecte. C'est un test de
non-régression.

Pour répondre à la seule question qui compte — *que détecte-t-il qu'il ne
connaît pas déjà ?* — le banc soumet **en plus des mutations non ciblées** :
bruit sur les valeurs, sévérité permutée, raisonnement tronqué, modes permutés,
confiance déplacée. Aucune ne vise un contrôle.

| Mesure | Résultat | Ce qu'elle vaut |
|---|---|---|
| Pièges ciblés | ~97 % | non-régression des huit contrôles |
| **Mutations non ciblées** | **~80 %** | **généralisation réelle** |
| Faux positifs sur cas sains | 0 % | ne rejette pas le correct |

L'auto-surveillance du contrôleur est **suspendue** pendant l'exécution du
banc : mélanger des décisions fausses par construction aux décisions réelles
rendait le taux d'accord affiché à l'exploitant ininterprétable.

## Limite assumée

L'agent et le contrôleur partagent la même chaîne de données et le même
référentiel. Le contrôleur vérifie la cohérence entre une décision et les faits
recalculés — c'est son objet — mais il ne constitue pas une validation externe
indépendante. Cette propriété est structurelle et énoncée dans chaque verdict
produit.
