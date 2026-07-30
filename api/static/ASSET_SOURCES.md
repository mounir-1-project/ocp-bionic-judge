# Sources des actifs visuels

Les photographies `e7301-field.jpg` et `e7301-tubesheet.jpg` sont extraites du
document interne fourni avec le projet :

- `docs/7-Gamme PV Refroidisseur d'acide PS3.pdf`
- Gamme de maintenance « Démontage et remontage : PV ou couvercles du
  refroidisseur d'acide PSIII »
- Référence documentaire : FO09-PSS01-IDS/C, édition 02

Elles représentent l'équipement et sa plaque tubulaire réels, et sont
embarquées localement afin que le poste reste utilisable hors ligne.

Leur usage diffère, et le dire évite de laisser croire que les deux sont
affichées :

- `e7301-tubesheet.jpg` est **affichée** dans la vue Intégrité, en regard du
  rappel que la surveillance couvre la signature thermique et non l'état des
  tubes.
- `e7301-field.jpg` n'est **pas affichée**. Elle est la RÉFÉRENCE DE
  MODÉLISATION du jumeau 3D : proportions du corps, position des brides, socles
  béton et passerelle en sont repris (voir l'en-tête de `twin.js`). Elle est
  conservée au dépôt pour que la géométrie reste vérifiable par rapport à
  l'équipement réel — c'est un élément de preuve, pas un actif d'interface.

## Marque

`ocp-logo.png` et `favicon.png` sont dérivés du logo institutionnel du Groupe
OCP fourni pour ce projet. Le fichier source portait une extension `.jpg` alors
qu'il s'agit d'un **WebP en RGBA** : le convertir en RGB le compositait sur du
noir et transformait le fond transparent en carré vert sombre. Le canal alpha
d'origine est donc conservé tel quel, sans détourage ni recolorisation ; seuls
le recadrage sur le contenu utile, une marge de 3 % et le rééchantillonnage à
220 px de haut ont été appliqués.

Aucune teinte de la charte n'est modifiée dans le fichier. L'interface applique
un éclaircissement CSS de 12 % à l'affichage, parce que le vert institutionnel
est sombre sur un fond à 6 % de luminance — la correction est réversible et ne
touche pas l'actif.

