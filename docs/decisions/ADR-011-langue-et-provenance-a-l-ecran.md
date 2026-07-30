# ADR-011 — La langue et la provenance sont des exigences, pas de la finition

**Statut** : accepté · **Date** : 2026-07-28

## Problème

Une revue écran par écran du poste a relevé treize défauts. Aucun n'était une
erreur de calcul : tous portaient sur **ce que l'écran dit de ce qu'il calcule**.
Ils se rangent en trois familles, et chacune a la même cause profonde — une
frontière franchie sans traduction entre la machine et le lecteur.

**Le code machine affiché tel quel.** `OVERCONFIDENCE` en réserve du
contrôleur, `duty_kw` et `control_deviation` en sous-titre de cartes dont les
voisines citent un tag DCS, `causalite_temporelle` en intitulé de porte de
déploiement, `RUNNING` et `STOPPED` dans une interface française,
`0 days 01:00:00` pour un pas d'échantillonnage horaire.

**Le champ disparu rendu en clair.** Le référentiel des tags avait changé de
structure ; l'affichage lisait toujours l'ancien champ et imprimait
`undefined / 6 tags du périmètre confirmés par OCP` — un mot anglais réservé
au débogage, dans une phrase qui affirmait par ailleurs une confirmation
inexistante.

**Le français à deux vitesses.** Les libellés écrits dans l'interface portaient
leurs accents ; tout texte produit par le serveur en était dépourvu. Les deux se
touchaient dans la même carte. Un premier test avait verrouillé les messages de
détection, les indicateurs et le référentiel — mais pas les **rapports de
gouvernance**, qui sont précisément les textes qu'un lecteur exigeant lit en
premier, puisqu'ils énoncent les limites du travail.

## Ce qui a été écarté

**Corriger les occurrences.** C'est ce qui avait été fait la fois précédente,
et la revue suivante en a trouvé autant. Une correction ponctuelle ne survit pas
à la ligne de code suivante.

**Un vernis de traduction générique.** Passer chaque code par un
`replace('_', ' ')` produit « causalite temporelle » : le code désouligné, pas
un intitulé métier. Cela masque le problème au lieu de le traiter.

## Décision

**Trois règles, et un test pour chacune.**

1. **Aucun identifiant machine n'atteint l'écran.** Les codes restent la
   référence pour l'API, la persistance et les tests ; l'interface porte une
   table de correspondance vers l'intitulé métier — réserves du contrôleur,
   états procédé, urgences, portes de déploiement, provenances AMDEC. Un banc
   frontend échoue si un code en capitales soulignées apparaît dans le
   diagnostic, ou si un nom de variable Python apparaît dans le bandeau.

2. **La mise en forme des nombres est centralisée.** `src/formatting` fournit
   `nombre`, `pourcent`, `unite`, `heures` et `duree_pas`. Python formate en
   notation anglaise ; chaque f-string réintroduisait le point décimal. Un test
   parcourt les sorties du système et échoue sur tout `1.7` qui aurait dû
   s'écrire `1,7`.

3. **Le test de typographie couvre toute surface lisible**, y compris les
   rapports de gouvernance. Il parcourt récursivement les structures
   sérialisables et écarte les identifiants techniques. Les comparaisons de
   contenu dans les autres tests passent par `sans_accents` : corriger la
   typographie ne doit jamais casser le test qui protège le fond, sinon
   l'équipe apprend à ne plus la corriger.

**Et une exigence de provenance à l'écran.** Le référentiel AMDEC mélange trois
natures de lignes : transcription fidèle du document OCP de 2019, règle dérivée
d'une ligne source, cotation proposée par ce travail. Le domaine les distinguait
déjà rigoureusement — champ `provenance_category`, valeurs d'origine
conservées — puis le tableau les affichait à l'identique. Un lecteur voyait donc
« Chaîne de mesure · C = 108 » avec la même autorité que « PLAQUE SACRIFICIELLE
· C = 112 ».

Chaque ligne porte désormais son marqueur, une légende l'explicite, et le banc
frontend échoue si une seule ligne en est dépourvue. Le travail de traçabilité
était fait ; il ne manquait qu'à le montrer.

## Conséquences

Le banc frontend passe de 36 à 43 vérifications. Les six ajoutées ne sont pas
des hypothèses : **chacune correspond à un défaut qui a été vu sur une capture
d'écran**. Un banc qui ne teste que ce qu'on a imaginé ne rattrape jamais ce
qu'on a manqué.

Deux fixtures de session — analyse de sensibilité et banc d'injection —
mutualisent des rapports coûteux entre les fichiers de tests qui en ont besoin.
La couverture s'élargit sans que la suite s'allonge, ce qui importe : une suite
lente finit par ne plus être lancée.
