# Détection d'anomalies du refroidisseur d'acide de séchage E7301

**S-PC-E7301 — Atelier Sulfurique PS III, Maroc Chimie, OCP Group**
Projet de stage — Programme Bionic · Mounir Sanbouli

Système de détection d'anomalies pour le refroidisseur d'acide de séchage E7301,
construit sur **10 180 horodatages DCS** (01/01/2024 → 28/02/2025) et sur
l'**AMDEC OCP du 23/09/2019**.

Il diagnostique l'encrassement du faisceau par le **coefficient d'échange global**,
rattache chaque anomalie à un mode de défaillance et à une tâche du plan
préventif, puis soumet chaque décision à un **contrôleur de cohérence
déterministe** avant qu'elle n'atteigne l'exploitant.

---

## L'idée : un contrôleur de cohérence qui peut réellement contredire

Un système de diagnostic automatique qui ne sait pas dire quand il se trompe est inexploitable en environnement industriel. Ce projet ajoute donc au diagnostic un **vérificateur déterministe de cohérence factuelle**.

La difficulté est que confier ce rôle à un modèle de langage à qui l'on montre le diagnostic ne produit qu'un tampon de conformité : sans source de vérité indépendante, il note la **cohérence interne d'un texte**, pas sa **véracité**. Un diagnostic entièrement inventé mais bien rédigé obtiendrait une meilleure note qu'un diagnostic exact mal formulé.

Ici, **le contrôleur recalcule les faits** depuis la même chaîne de données et de règles, puis confronte chaque affirmation du diagnostic à ce recalcul. Huit contrôles logiques, déterministes et reproductibles. Le modèle de langage n'intervient qu'ensuite, pour la nuance et la rédaction, dans un corridor borné.

Le banc d'évaluation distingue deux mesures : la **non-régression** des huit
contrôles (96 %) et la **généralisation** face à des mutations non ciblées
(**22 %**). C'est la seconde qui répond à la question « que détecte-t-il qu'il
ne connaît pas déjà ? » — et c'est elle que ce projet met en avant, parce
qu'un dispositif de gouvernance qui surestime sa portée est pire qu'aucun.

---

## Démarrage

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

`requirements.txt` installe l'environnement complet de développement et
d'analyse, sur Python 3.10 ou plus. L'image Docker installe
`requirements-runtime.lock` — un verrou de versions exactes dérivé de
`requirements-runtime.txt` et **ciblant Python 3.11**, la version de l'image.
Les deux environnements sont distincts et le restent : le verrou n'est pas
installable sur 3.10.

Ouvrir <http://localhost:8000>, puis **Rejouer**. Les 10 180 heures réelles
défilent à la vitesse choisie ; à l'instant *t*, le système ne voit que la
fenêtre [début, *t*].

### Le jumeau 3D

La vue principale n'est pas un tableau de bord avec une vignette 3D : c'est le
modèle lui-même, orientable à la souris, zoomable, avec une rotation lente qui
reprend après quelques secondes d'inactivité.

Sa géométrie suit la **liste des composants** : acide côté calandre, eau de mer
dans les tubes 3/4″ en 904L, deux plaques tubulaires, une boîte à eau par
extrémité fermée par un couvercle boulonné, piquages bridés d'entrée et de
sortie acide. Les proportions reprennent la mention `SIZE : 1118-9754` de la
fiche équipement, d'où un appareil long et élancé plutôt que le tonneau trapu
qu'on obtient en dessinant « un échangeur ». Le décor — châssis acier peint,
platelage caillebotis, garde-corps, échelle, socles béton — vient de la photo
terrain : sans lui, l'appareil flotte dans le vide et l'œil perd toute
référence d'échelle.

**Les douze capteurs DCS sont des objets 3D**, posés à leur emplacement
physique, étiquetés avec leur valeur en direct. Cliquer sur l'un d'eux ouvre sa
fiche : courbe, seuils, consigne, disponibilité, défauts tracés et
justification de l'interprétation du tag. Cliquer sur une pièce ouvre les modes
AMDEC qu'elle porte.

Quand une anomalie survient, la pièce concernée et les capteurs qui la révèlent
passent en ambre ou en rouge et pulsent — deux battements par seconde pour un
état critique, un pour un avertissement. **Ce rattachement vient de
`src/domain/topology.yaml`**, pas d'une heuristique d'affichage : chaque code
de règle y désigne explicitement ses pièces et ses capteurs, et un code non
déclaré n'allume rien plutôt que d'accuser la mauvaise pièce.

Le moteur 3D et la carte d'environnement sont générés localement : aucune
ressource Internet n'est appelée à l'exécution.

### Comptes techniciens et escalade e-mail

L'adresse saisie à l'ouverture de session **n'est pas décorative** : elle devient
le destinataire des états critiques retenus par le contrôleur de cohérence. Elle
doit donc être authentifiée individuellement — un mot de passe partagé ne
permettrait ni de savoir qui a ouvert la session, ni de révoquer un départ.

Chaque technicien a son propre compte :

```bash
python scripts/manage_operators.py add      # crée un compte (mot de passe masqué)
python scripts/manage_operators.py list     # liste les techniciens
python scripts/manage_operators.py passwd   # change un mot de passe
python scripts/manage_operators.py remove   # retire un technicien
```

**L'accès protégé s'active de lui-même** dès qu'un compte existe : aucune
variable à positionner. Tant qu'aucun compte n'est enregistré, le poste
s'ouvre sur une prise de quart déclarative, et l'écran le dit explicitement.

Le dépôt ne contient **aucun mot de passe, aucune empreinte, aucune adresse
réelle**. Le registre vit dans `data/runtime/operators.json`, ignoré par git,
en droits 600, et ne stocke que des empreintes PBKDF2-SHA256 à 600 000
itérations, avec un sel distinct par technicien. Le mot de passe n'est jamais
accepté en argument de ligne de commande : il apparaîtrait dans l'historique du
terminal et dans la liste des processus.

Pour que les courriels partent réellement, il faut un relais SMTP dans `.env`
(`SMTP_HOST`, `SMTP_FROM`, éventuellement `SMTP_USERNAME` / `SMTP_PASSWORD`).
Sans lui, le canal reste inactif — et la vue *Contrôle* affiche **pourquoi**,
plutôt qu'un simple « désactivé » qui laisserait croire à une panne.

Un état critique ne déclenche un envoi que s'il est **retenu par le contrôleur
de cohérence** : une décision rejetée ne réveille personne. Les envois sont
dédoublonnés par un délai anti-répétition.

En production, le démarrage reste bloqué tant que le fournisseur IAM OIDC de
l'entreprise n'est pas intégré : ce registre local est un mécanisme de
démonstration mono-poste, pas une gestion d'identités.

Aucune clé API n'est nécessaire : le système fonctionne intégralement hors ligne. Renseigner `GEMINI_API_KEY` dans `.env` active la couche de rédaction par modèle de langage.

```bash
make test           # suite complète, couverture mesurée
make test-front     # bancs frontend : câblage du poste et scène 3D
make bench-fouling  # injection d'encrassement et courbe de détection
make sensitivity    # influence des paramètres de réglage
make eval-judge     # banc d'injection de fautes sur le contrôleur
make operator       # enregistre un technicien
make notebook       # analyse complète
make docker-run     # déploiement conteneurisé
```

---

## Architecture

```
        DATA.xlsx — 10 180 h, 12 tags DCS
                    |
  [1] INGESTION     codes qualité, gel, saturation, états de marche
                    |
  [2] FEATURES      physique de l'échangeur, coefficient d'échange global UA
                    |   (climatologie eau de mer Safi comme référence externe)
                    |
  [3] DÉTECTION     règles AMDEC + Isolation Forest -> épisodes recalculés
                    |
  [4] AGENT         diagnostic + action rattachée au plan préventif
                    |
  [5] CONTRÔLEUR    cohérence interne, 8 contrôles logiques
                    |
  [6] INDICATEURS   grandeurs mesurées, sans hypothèse ni valorisation
                    |
        API FastAPI + poste de surveillance 3D + rejeu accéléré
```

Le référentiel métier (`src/domain/tags.yaml`, `src/domain/amdec.yaml`,
`src/domain/topology.yaml`) alimente toutes les couches, interface comprise.
**Aucun seuil, aucun nom de tag, aucune criticité, aucune position de capteur
n'est codé en dur ailleurs** — une correction métier se répercute sans
modification de code, et l'intégration continue vérifie la cohérence du
référentiel à chaque changement.

| Module | Rôle |
|---|---|
| `src/domain/` | Référentiel : tags, seuils, AMDEC, plan préventif, gammes, topologie physique |
| `src/ingest/` | Ingestion DCS, qualité de donnée, états de marche |
| `src/features/` | Grandeurs physiques, coefficient d'échange UA et références |
| `src/models/` | Moteur de règles AMDEC + Isolation Forest + explicabilité |
| `src/agents/` | Agent de diagnostic et Judge |
| `src/governance/` | Banc d'évaluation du Judge par injection de fautes |
| `src/analytics/` | Indicateurs d'exploitation calculés sur les données mesurées |
| `src/realtime/` | Rejeu accéléré du flux DCS |
| `api/` | API FastAPI, poste de surveillance et jumeau 3D |
| `legacy/` | Version 1 conservée pour documenter l'évolution |

---

## Quatre décisions qui font le système

### La variable de sortie est régulée — et le détour qui semblait la contourner n'en était pas un

La température de sortie acide varie de **moins de 3 °C sur 14 mois** (P1 = 63,7 °C, P99 = 66,6 °C) : c'est une variable maintenue par une boucle de régulation autour de 66 °C. L'encrassement ne s'y lit pas tant que la régulation tient.

Une version antérieure en concluait qu'il fallait lire **l'effort** plutôt que le résultat, via le résidu du duty thermique, présenté comme un indicateur indépendant. **Cette conclusion était fausse, et l'erreur était algébrique.**

Le duty est calculé par définition `ρ·cp·F·(T_in − T_out)`, et la référence le régresse sur `F`, `T_in` et `F × T_in`. Comme `T_out` est régulée, la cible est déjà presque une combinaison linéaire des régresseurs : la régression ne modélisait pas l'échangeur, elle retrouvait sa propre définition.

| Mesure | Valeur |
|---|---|
| R² de la référence apprise | **0,968** |
| R² d'une formule **sans aucun apprentissage** | **0,962** |
| Apport réel du modèle | **+0,006** |
| Corrélation résidu ↔ écart de consigne | **−0,94** |
| Variance du résidu expliquée par l'écart seul | **90,6 %** |

Conséquence : le résidu du duty **est** l'écart de consigne, changé de signe et pondéré par le débit. La « table des signes » qui croisait les deux comme deux preuves concordantes ne pouvait pas échouer, donc ne vérifiait rien.

**Correction appliquée.** Le résidu est renommé `regulation_effort` — c'est ce qu'il mesure — et n'est plus jamais présenté comme une preuve distincte. Un test échoue si quelqu'un tente à nouveau de le déclarer indépendant, et le manifeste publie sa part non apprise (`naive_r2`).

### Ce qui débloque tout : la température de l'eau de mer

L'encrassement d'un échangeur se lit sur son **coefficient d'échange global UA**, et sur rien d'autre. Le calculer exige la température du fluide froid, absente de l'export DCS. C'est ce qui bloquait le raisonnement.

Cette température n'est pourtant pas une inconnue. Le refroidisseur est refroidi à l'eau de mer, à **Safi**, où le courant des Canaries et l'upwelling côtier maintiennent une eau fraîche à faible amplitude : **17,0 °C en février-mars, 22,0 °C en septembre**. C'est une donnée climatologique documentée et stable d'une année sur l'autre, **extérieure à l'atelier**.

```
ε   = (T_entrée − T_sortie) / (T_entrée − T_eau_de_mer)
NTU = −ln(1 − ε)
UA  = C_acide · NTU
```

UA varie légitimement avec le régime — le débit gouverne la turbulence, la viscosité de l'acide chute avec la température, et la température d'eau de mer fixe le point de fonctionnement de la boucle froide. Une référence apprend `UA(F^0,8, T_moyenne, T_eau)` sur la période de référence uniquement : **R² = 0,924**, écart-type résiduel 0,63 kW/K, soit 3,5 % de UA. Le résidu est l'indicateur d'encrassement, et la résistance `Rf = 1/UA − 1/UA_attendu` en K/kW est la grandeur que suit le service fiabilité.

**Ce que UA est, et ce qu'il n'est pas.** Le débit d'eau de mer n'est pas instrumenté, et c'est lui que la régulation manipule pour tenir 66 °C. La grandeur calculée est donc un **UA apparent** : le produit de l'état de la surface d'échange par l'action de la boucle froide. La conséquence doit être dite franchement — tant que la vanne conserve de la marge, elle compense un début d'encrassement et UA apparent ne bouge pas. L'indicateur devient sensible quand cette marge se consomme.

La signature de cette dépendance est visible dans les données : UA apparent suit l'eau de mer, de 13,8 kW/K en janvier à 21,9 en septembre, parce qu'une eau plus chaude oblige la vanne à s'ouvrir davantage. La régression retire cette part saisonnière. C'est précisément pour chiffrer le retard résiduel que le banc d'injection publie l'**avancement à la détection** plutôt qu'un taux.

Indépendance mesurée vis-à-vis de l'écart de consigne, en marche établie :

| Indicateur | r | Variance partagée | Rôle |
|---|---|---|---|
| `regulation_effort_z` | −0,94 | 88 % | conduite — jamais une preuve d'encrassement |
| `ua_residual_z` | −0,54 | 29 % | **diagnostic** — partiellement confondu, et le banc chiffre le retard |
| `t_in_residual_z` | +0,03 | 0,1 % | contexte amont — indépendant, mais confondu côté procédé |

Aucun de ces indicateurs n'est parfait, et le projet ne prétend pas le contraire. UA porte le diagnostic parce qu'il est le seul construit sur la grandeur que l'encrassement dégrade.

**Validation croisée intéressante.** À charge constante, la température d'entrée acide monte de 89,4 °C en janvier à 96,8 °C en juillet. Une lecture naïve y voit une dégradation. C'est la climatologie de l'eau de mer — **le système a signalé une dérive, et c'était l'océan Atlantique**.

### Le détecteur verrait-il un encrassement ?

Avec la période de référence retenue, la règle ne se déclenche sur aucune des quatorze mois. Ce zéro est **conditionnel** : sur une référence arrêtée à 25 % du corpus, la même règle se déclencherait sur 52 % des heures de marche. Le tableau de sensibilité publie les quatre fenêtres, et aucun chiffre d'encrassement n'est cité dans ce document sans elle. Reste la question de fond : sans anomalie étiquetée, on ne distingue pas « il n'y a rien eu » de « la règle ne peut pas se déclencher ». `make bench-fouling` tranche : il dégrade UA d'une fraction donnée sur les **données réelles**, laisse la physique efficacité-NTU recalculer les températures, et démarre la rampe **dans une fenêtre où la règle est silencieuse**.

| Perte de UA injectée | Détectée à | Délai |
|---|---|---|
| **30 %** | 32 % d'avancement | 464 h |
| **20 %** | 39 % d'avancement | 561 h |
| 10 % | 87 % d'avancement | 1 257 h |
| 5 % | fin de rampe | — |

**Faux positifs sur les données non modifiées : 0 %.**

Le chiffre honnête n'est pas le taux de détection brut — une dérive finit toujours par franchir un seuil — mais **l'avancement auquel elle est vue**. Une perte de 20 % détectée à 39 % laisse le temps de programmer un arrêt ; une perte de 5 % n'est pas distinguable du bruit, et le banc le dit.

### Résultat sur l'équipement

**Le faisceau n'est pas encrassé — sous la période de référence retenue.** À saison comparable, février 2024 → février 2025, UA passe de 15,4 à 18,6 kW/K et la résistance d'encrassement de +0,015 à +0,002 K/kW. La surface d'échange transmet mieux, pas moins bien.

Ce n'est plus une absence de détection : c'est une mesure. Mais c'est une mesure **relative à une référence**, et le tableau de sensibilité montre de combien elle en dépend :

| Fenêtre de référence | Fin | R² UA | UA minimal | Heures déclarées en encrassement |
|---|---|---|---|---|
| 25 % | 14/05/2024 | 0,940 | −6,36 σ | **4 588 / 8 795 = 52,2 %** |
| **40 %** (retenue) | 13/07/2024 | 0,924 | −1,22 σ | **0** |
| 55 % | 08/09/2024 | 0,953 | −1,34 σ | 0 |
| 70 % | 04/11/2024 | 0,947 | −1,26 σ | 0 |

La fenêtre à 25 % n'est pas dégénérée : 2 198 heures d'apprentissage, R² = 0,940. Elle s'arrête simplement en mai, avant que l'eau de mer ne se réchauffe — et la régression, qui n'a jamais vu d'été, lit la remontée saisonnière de UA comme une dérive.

**C'est pour cette raison que la fenêtre de 40 % est retenue : elle est la plus courte qui couvre un cycle saisonnier complet.** Ce critère est explicite et contestable ; le zéro qui en découle ne vaut qu'avec lui.

### La qualité de donnée est une information, pas un déchet

L'analyse a caractérisé **deux défaillances d'instrumentation non tracées** :

- **TI5303-4X** collé à 327,67 depuis août 2024 — soit 32767/100, un dépassement d'entier 16 bits : sept mois de données mortes ;
- **PHI5306X-3** figé à −14,407 pendant environ 1 900 heures, plus 139 codes qualité DCS ;
- un gel simultané de **sept tags** du 3 au 10 juin 2024, dont la simultanéité désigne une interruption d'acquisition et non une panne de capteur.

Les valeurs invalides sont mises à `NaN` et **jamais remplacées**. Un `fillna` ferait déclarer au système « tout va bien » pendant sept mois de capteur mort.

Point de conception subtil : la détection de gel ne s'applique **que hors arrêt**. Un débit à zéro pendant un arrêt planifié est légitime. Sans cette restriction, la détection produisait 17 786 événements dont la majorité étaient faux ; elle en produit 9 116 réels.

### Les alertes horaires doivent être agrégées — sans que l'agrégation ne masque le problème

Aucun opérateur ne traite des milliers de points horaires isolés. Les heures atypiques sont donc agrégées en **épisodes temporels**, ce qui ramène la charge à environ **5 épisodes par mois**.

Ce chiffre est flatteur, et il masquait une réalité. Le **taux horaire réel** est publié à côté :

| | |
|---|---|
| Contamination de calibration | 2 % |
| Taux horaire réel | **6,2 %** |
| Pire mois (octobre 2024) | **24,7 %** |

L'analyse de sensibilité (`/api/sensitivity`) montre que ce facteur ~2,7× est **stable** sur toute la grille de contamination : le paramètre reste un levier utilisable, mais il ne doit pas se lire comme le taux attendu. Pour viser 2 % d'heures signalées, il faut paramétrer environ 0,7 %.

**Correction associée** : les moyennes glissantes 14 jours ont été retirées des entrées du modèle statistique. Donner une tendance lente à un détecteur de points atypiques garantissait que *toute* heure d'une période dérivée soit signalée — le taux montait à 17 %, et à 65 % en octobre. Une dérive lente est **un** événement, pas une succession d'anomalies : c'est le rôle des règles de persistance de le dire une fois.

### Deux paramètres arbitraires, désormais mesurés

`contamination = 0,02` et « période de référence = 40 % initiaux » décident de presque tout, et aucun n'a de justification physique. Leur influence est maintenant quantifiée.

Le second résultat est le plus important du projet :

| Fenêtre de référence | Part du temps déclarée en dérive |
|---|---|
| 25 % initiaux | **64 %** |
| 40 % initiaux (retenu) | 15 % |
| 55 % initiaux | 3 % |
| 70 % initiaux | 3 % |

**61 points d'écart selon le seul choix de la fenêtre.** Le mécanisme se comprend : plus la référence est tardive, plus elle englobe le changement de régime de juin 2024, et plus celui-ci devient la normalité. La conclusion dépend donc davantage de ce choix que des données. **Tant que la date de révision réelle n'est pas communiquée par OCP, aucun chiffre de dérive n'est un résultat.**

### Un chiffre sans sa source est un chiffre faux

Le projet ne produit **aucune valorisation monétaire**. Une version antérieure
portait un modèle économique de 29 paramètres dont 19 restaient non confirmés
par OCP : chiffrer un gain en dirhams à partir d'hypothèses invérifiables
n'ajoute rien à un sujet de maintenance, et fragilise tout ce qui l'entoure.

Restent **cinq** indicateurs, tous recalculables à partir du seul `DATA.xlsx` :
disponibilité des mesures, exposition cumulée à des conditions corrosives,
marche durablement sous consigne, charge d'alertes pour l'exploitant, et taux
horaire de signalement en marche.

Cette liste en comptait quatre, dont « énergie thermique évacuée en excès » —
**c'est-à-dire précisément la formulation que ce même README déclare retirée
quelques paragraphes plus loin**, et pour la raison qui y est exposée. Une
contradiction interne à un document est plus dommageable qu'une erreur : elle
apprend au lecteur à ne se fier à aucune de ses deux moitiés. Le constat
subsiste sous sa forme fonctionnelle — « marche durablement sous consigne » —
et `test_le_sur_refroidissement_ne_se_presente_plus_en_energie` interdit le
retour de la formulation énergétique.

Chacun porte son `evidence_level` — `observed` quand la grandeur est lue dans
les données, `derived` quand elle passe par la référence thermique et hérite
donc de ses limites. `test_aucun_indicateur_ne_porte_de_montant` vérifie
qu'aucun indicateur ne réintroduise un montant.

### Une anomalie doit désigner une pièce, pas une couleur

Relier un code de règle à la pièce concernée est une **connaissance métier**.
Elle vit dans `src/domain/topology.yaml`, avec les dix pièces de l'appareil,
les douze capteurs situés, et la table qui rattache chacun des dix-sept codes
du détecteur aux pièces et capteurs qu'il met en cause.

Un code absent de cette table n'allume rien : mieux vaut ne rien montrer
qu'accuser la mauvaise pièce. L'intégration continue vérifie que la topologie
ne cite aucun tag, mode AMDEC ou composant inexistant, et un test s'assure que
tout code émis par le détecteur y possède une entrée.

---

## Les huit contrôles du Judge

| Contrôle | Question | Poids |
|---|---|---|
| **V1** Fidélité numérique | Les valeurs citées correspondent-elles aux mesures réelles ? | 22 % |
| **V2** Sévérité | La sévérité correspond-elle aux faits recalculés ? | 16 % |
| **V3** Ancrage AMDEC | Les modes invoqués existent-ils et sont-ils détectables ? | 14 % |
| **V4** Conformité de l'action | L'action est-elle proportionnée, conforme, exécutable ? | 14 % |
| **V5** Calibration | La confiance reflète-t-elle la force des preuves ? | 15 % |
| **V6** État de marche | L'état de marche réel est-il respecté ? | 8 % |
| **V7** Couverture | Le fait le plus grave est-il traité ? | 5 % |
| **V8** Incertitude | Les limites du diagnostic sont-elles énoncées ? | 6 % |

**V1** rend l'hallucination impossible : chaque valeur est confrontée à la mesure recalculée, tolérance 1 %.
**V3** attrape la faute la plus insidieuse — prétendre avoir détecté un mode que les capteurs ne permettent pas de voir, comme la dégradation de l'anode sacrificielle (criticité 112, non instrumentée).

Certains manquements ne sont **pas compensables** par une moyenne pondérée. Des plafonds l'interdisent : valeur inventée, mode inexistant, angle mort revendiqué, action dangereuse et sévérité critique minimisée plafonnent la note à 4/10 ; un état de marche erroné à 5/10.

Le Judge **s'auto-surveille** : il signale sa propre complaisance (> 97 % de validations), sa sévérité systématique (< 10 %) et l'indifférenciation de ses notes (écart-type < 0,35).

---

## Évaluation du Judge — ce que le banc mesure vraiment

Le taux d'accord ne prouve rien : le Judge et l'agent raisonnent sur la même base de faits, un accord de 100 % est attendu et vide de sens.

Le banc soumet au Judge des décisions **délibérément fausses**, construites à partir de cas réels en y injectant une faute connue. **Mais ce banc n'est pas une validation**, et le dire est important : chaque piège porte le code d'anomalie que le Judge implémente déjà. On fabrique une faute conçue pour déclencher V1, puis on mesure que V1 la détecte. C'est un **test de non-régression**.

Pour répondre à la seule question qui compte — *que détecte-t-il qu'il ne connaît pas déjà ?* — le banc soumet **en plus des mutations non ciblées** : diagnostic et raisonnement intervertis, raisonnement tronqué, action d'un autre mode AMDEC pourtant valide, valeurs d'un instant voisin, valeurs citées retirées.

**Cette liste a été refaite.** Elle contenait auparavant « bruit sur les valeurs citées », « sévérité permutée » et « modes AMDEC permutés » — trois mutations qui déclenchent respectivement V1, V2 et V3 *par construction* : bruiter une valeur de 3 à 25 % franchit toujours la tolérance de 1 %. Le chiffre annoncé comme mesure de généralisation était donc, pour trois cinquièmes, un test de non-régression déguisé. Les cinq mutations retenues portent sur des propriétés qu'aucun des huit contrôles n'interroge, et un test le vérifie.

| Mesure | Résultat | Ce qu'elle vaut |
|---|---|---|
| Pièges ciblés | **96 %** | non-régression des huit contrôles |
| **Mutations non ciblées** | **22 %** (n = 50) | **généralisation réelle** |
| Écart de note piégés / sains | 4,1 points | discrimination |
| Faux positifs sur cas sains | 0 % | le Judge ne rejette pas le correct |

**22 %, et c'est le chiffre à retenir.** Le contrôleur attrape presque tout ce qu'il a été conçu pour attraper, et à peine un cinquième de ce qu'il n'a pas prévu. Une version antérieure de ce tableau annonçait « ~80 % » : cette valeur n'a jamais été mesurée, et les mutations qui la produisaient visaient en réalité trois contrôles nommés. Un dispositif de gouvernance qui surestime sa propre portée est plus dangereux que pas de dispositif du tout.

**Limite structurelle qui subsiste.** L'agent et le Judge partagent la même chaîne de données et le même référentiel. Si l'interprétation d'un tag est fausse, les deux se trompent ensemble et le Judge certifie l'erreur avec une note élevée. Aucun banc interne ne corrige cela — seule la confirmation OCP des tags le peut.

**Défaut corrigé** : le banc réutilisait le Judge de production, donc son auditeur. Les décisions volontairement fausses étaient comptabilisées dans l'auto-surveillance affichée à l'opérateur, faisant chuter le taux d'accord de 1,00 à 0,50. L'auditeur est désormais suspendu pendant le banc, et un test le vérifie.

Détail par type de faute :

| Mesure | Décisions saines | Cas piégés |
|---|---|---|
| Nombre | 12 | 119 |
| Note moyenne | 9,80 / 10 | 5,63 / 10 |
| Taux de détection | — | **98,3 %** |
| Faux positifs | **0 %** | — |
| Séparation | **4,18 points** | |

| Faute injectée | Détection | Note moyenne |
|---|---|---|
| Valeur inventée | 100 % | 4,00 |
| Mode AMDEC inexistant | 100 % | 4,00 |
| Angle mort revendiqué | 100 % | 4,00 |
| Action dangereuse | 100 % | 4,00 |
| Sévérité sous-estimée | 100 % | 4,39 |
| Action sous-dimensionnée | 100 % | 4,62 |
| État de marche erroné | 100 % | 5,00 |
| Diagnostic sans chiffres | 100 % | 7,93 |
| Sur-confiance | 100 % | 8,92 |
| Constatations ignorées | 100 % | 9,30 |

**Le banc n'a pas seulement mesuré le Judge, il l'a corrigé.** La première exécution donnait 65 % de détection et a révélé trois défauts : des codes d'anomalie écrasés quand un contrôle en relevait plusieurs, une tolérance de confiance trop laxiste (0,99 annoncé sur 0,80 justifiable passait), et un état de marche erroné détecté mais insuffisamment pénalisé. Le banc élargi reconnaît les dix catégories de faute dans 100 % des cas ; deux cas sur 119 restent insuffisamment sanctionnés, d'où un succès global de 98,3 %.

Le Judge a par ailleurs corrigé l'agent : il signalait `MISSING_CAVEAT` lorsque le modèle statistique était inapplicable sans que le diagnostic en fasse mention. L'agent énonce désormais cette réserve.

---

## Ce que l'analyse a révélé sur l'équipement

**Une bascule de régime thermique en juin-juillet 2024.** Le résidu de température d'entrée — seul indicateur indépendant de la boucle — passe de −0,5 σ sur janvier-mai à +1,9 σ en juillet, et reste au-dessus de +0,8 σ jusqu'à la fin du corpus. À charge et débit donnés, le circuit travaille durablement plus chaud après cette date.

Ce que cela **ne prouve pas** : que le refroidisseur en soit la cause. L'indicateur est confondu avec toute dérive du circuit amont, et la sensibilité à la période de référence (61 points) interdit d'en tirer un chiffre. C'est une **piste d'inspection**, pas un diagnostic.

**Un sur-refroidissement installé pendant 28 % du temps de marche.** Deux excursions distinctes — mai 2024, puis août à novembre 2024 — pendant lesquelles la sortie acide décroche à 64,4 °C au lieu des 66,0 °C tenus au centième près le reste du temps.

| Mois | Part du temps hors bande (> 1 °C) |
|---|---|
| Juin, décembre 2024 | 0,0 % |
| Mai 2024 | 87,0 % |
| Septembre 2024 | 96,7 % |
| **Octobre 2024** | **99,1 %** |

C'est un réglage de conduite, pas une dégradation mécanique.

Une version précédente publiait ce constat en **MWh thermiques évacués en excès**. La formulation a été retirée, et le raisonnement mérite d'être exposé : elle appelle immédiatement la question du coût, à laquelle la réponse honnête est « presque rien ». L'eau de mer circule de toute façon et la pompe ne module pas ; seule la vanne s'ouvre. Convertir un écart de régulation en énergie donnait à un constat de conduite l'apparence d'un gisement d'économies que ce projet n'a pas les données pour établir.

Le fait qui compte se formule autrement, et il est plus dérangeant : **la boucle froide travaille déjà plus qu'il n'est nécessaire un tiers du temps**. C'est de cette marge que dépend la capacité du refroidisseur à absorber un futur encrassement sans décrocher — la consommer sans raison réduit l'horizon d'alerte du système lui-même.

### Deux erreurs d'analyse corrigées en cours de route

Un projet dont on ne peut pas retracer les corrections n'est pas vérifiable. Les deux sont documentées dans le rapport :

**Une causalité qui n'existait pas.** Une première lecture attribuait le changement de régime à la saturation du capteur TI5303-4X en août 2024. L'analyse par décades montre que la première excursion commence en **mai**, soit 100 jours *avant*. L'effet précédait la cause supposée : l'hypothèse est abandonnée.

**Une redondance qui n'en était pas une.** Les deux analyseurs de titre étaient traités comme deux mesures du même point. Leur corrélation réelle en marche établie n'est que de **+0,35**, avec un biais permanent de 0,124 point : ce sont deux circuits distincts. Le `min()` des deux se réduisait à un seul capteur dans 95 % des cas, et le seuil de contrôle croisé représentait 6 σ — il ne se déclenchait jamais. La règle a été remplacée par une surveillance de la stabilité du biais.

---

## Ce que le système ne voit pas

Un système de surveillance qui ne déclare pas ses angles morts donne une fausse assurance. Ils sont exposés par l'API, affichés sur le poste, et le Judge sanctionne tout diagnostic qui prétendrait les avoir détectés.

### La part du risque réellement couverte : 48,8 %

Déclarer les angles morts un par un ne suffisait pas — il manquait la fraction. Elle est désormais calculée et affichée (`/api/coverage`) :

```
criticité AMDEC totale ......... 1052
        couverte par les données  513   (48,8 %)
        non couverte .............539   (51,2 %)
modes aveugles : 8 sur 13
```

| Mode non détectable | Criticité | Couverture préventive |
|---|---|---|
| Plaque sacrificielle — dysfonctionnement | **112** | Tâches D (6 mois), E (3 ans) |
| Vanne d'acide — fuite | **112** | Tâche F (4 ans) |
| Porte de visite — fuite | 90 | Tâche C (1 mois) |
| Vanne d'acide — bouchage | 90 | Tâche F (4 ans) |
| Vanne eau de mer — bouchage | 42 | Tâche G (6 ans) |

**Les deux modes les plus critiques de l'équipement sont hors de portée du système.** La conclusion à en tirer, et qui manquait : pour ce refroidisseur, **la maîtrise du risque reste majoritairement dans le plan préventif A→H et l'inspection**. La surveillance par données ne s'y substitue pas ; elle couvre l'autre moitié.

### Sur quoi repose le sens des tags

Aucune fiche d'instrumentation n'accompagne l'export DCS. Le sens des douze tags a donc été **établi par recoupement**, et chaque détermination cite au moins deux bases indépendantes :

| Base | Ce qu'elle apporte |
|---|---|
| `isa_5_1` | Nomenclature instrumentation : TI, FI, AI, PHI, et numéro de boucle |
| `process` | Physique du procédé sulfurique et données constructeur Chemetics — titre 93-98 %, plages de température de service |
| `data` | Comportement observé sur 10 180 heures : plages, corrélations en marche établie, effondrement à l'arrêt, autocorrélation |
| `stoichio` | Cohérence de la ligne : 1 t de soufre donne 3,06 t de H₂SO₄, soit ~1 370 t/j à 18,6 t/h — la capacité d'une ligne PS III |

Les six tags qui fondent un diagnostic exigent la base la plus forte : un test échoue si l'un d'eux perd son ancrage procédé. Le détail de chaque détermination est dans `src/domain/tags.yaml`, et publié par `/api/coverage` — un lecteur peut contester une détermination précise plutôt que douter de l'ensemble.

### Ce que le corpus ne permet pas

Aucune anomalie étiquetée : le problème est non supervisé, ce qui interdit toute métrique de type AUC ou F1. La seule mesure de détection possible est le banc d'injection, qui donne une **borne supérieure** de performance.

La période de référence n'est pas ancrée sur une date de révision. Sa sensibilité est mesurée (`make sensitivity`) : la part du temps déclarée en dérive varie de 61 points selon la fenêtre retenue. C'est pourquoi le diagnostic s'appuie sur UA, dont le niveau absolu est physique, plutôt que sur un résidu dont le zéro dépend de ce choix.

---

## Livrables

| Fichier | Contenu |
|---|---|
| `docs/decisions/` | Huit décisions d'architecture, du cœur analytique à l'interface |
| `docs/rapport_technique.md` | Dossier technique complet |
| `docs/architecture.md` | Vue d'ensemble des couches |
| `notebooks/01_analyse_E7301.ipynb` | Analyse justifiant chaque choix de conception |
| `src/domain/tags.yaml` | Référentiel des tags : sens, bases d'établissement, seuils |
| `src/domain/amdec.yaml` | AMDEC du 23/09/2019, plan préventif, gammes, check-lists |
| `src/domain/topology.yaml` | Pièces, position des capteurs, rattachement des codes |
| `reports/project_metrics.json` | Source unique des chiffres du projet |

## Suites recommandées

**Avec OCP** — valider les interprétations de tags ; vérifier l'hypothèse liant la saturation de TI5303-4X au changement de régime d'août 2024 ; déclencher une demande d'intervention instrumentation sur les deux capteurs défaillants ; obtenir l'historique des interventions.

**Techniques** — intégrer les tags eau de mer pour un coefficient d'échange exact ; descendre au pas d'une minute ; instrumenter la protection anodique pour couvrir le mode de criticité 112 ; dupliquer le référentiel aux autres refroidisseurs de PS II et PS III.

---

## Sources documentaires

Fiche équipement, fiche d'identification des sous-ensembles, liste des composants, **AMDEC du 23/09/2019**, plan de maintenance préventive, check-lists d'inspection externe et interne, gamme PV de démontage des couvercles, gamme de tamponnage mécanique des tubes, et l'export DCS `DATA.xlsx`. Documents originaux dans `docs/`.
