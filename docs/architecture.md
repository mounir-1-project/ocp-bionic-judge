# Architecture technique — surveillance E7301

**Version active : 3.0**

*Dernière confrontation de ce document au code : 7 août 2026. Elle a porté sur
la chaîne de traitement, le tableau des responsabilités, les six invariants, la
période de référence et les commandes de lancement. Une date de vérification
sans son périmètre n'engage rien : le document précédent en portait une, et
`src/operations/` — deux bases SQLite, six routes et un écran — n'y figurait
pourtant nulle part.*

## Finalité et périmètre

Le service surveille un seul équipement industriel : le refroidisseur d'acide
de séchage **S-PC-E7301**, atelier Sulfurique PS III. Il transforme un export
DCS horaire en diagnostics traçables, puis soumet chaque diagnostic à un
contrôle déterministe séparé de la génération textuelle.

La version active est volontairement compacte :

- un processus Python ;
- une API FastAPI qui sert aussi l'interface opérationnelle E7301 ;
- un référentiel métier YAML versionné ;
- aucun serveur de base de données ni build frontend ;
- un modèle de langage strictement optionnel ;
- une authentification locale de démonstration désactivée sans configuration
  explicite ; l'IAM OIDC reste obligatoire avant tout profil production.

La version 1 n'est pas conservée dans le dépôt. Les choix qu'elle portait et
les raisons de leur abandon sont consignés dans les décisions d'architecture,
qui sont la seule trace utile : un répertoire de code mort se lit moins bien
qu'un ADR qui dit pourquoi il l'est.

## Chaîne de traitement

```text
DATA.xlsx (10 180 h, 12 tags)
        |
        v
src/ingest/        schéma, codes qualité, gels, saturations, états process
        |
        v
src/features/      physique de l'échangeur, coefficient d'échange UA, trois références
        |
        v
src/models/        règles AMDEC + Isolation Forest + attribution par occlusion
        |
        v
src/agents/        diagnostic et action issus du référentiel
        |
        v
src/agents/judge   8 contrôles de cohérence recalculés sur la même chaîne
        |
        +------> src/governance/  injection de fautes et métriques du Judge
        |
        +------> src/analytics/   Indicateurs mesurés, sans hypothèse économique
        |
        +------> src/operations/  registre d'alarmes ISA-18.2 et interventions
        |
        v
api/main.py        API, dashboard statique et rejeu accéléré
        |
        +------> src/security/       session opaque, CSRF, expiration
        |
        +------> src/notifications/  file SMTP non bloquante et dédoublonnage
```

`src/pipeline.py::E7301Pipeline` est l'unique façade de bout en bout. L'API, le
rejeu, les tests et le notebook appellent cette même chaîne afin d'éviter une
divergence entre démonstration et calcul hors ligne.

## Responsabilités

| Composant | Responsabilité | Source de vérité |
|---|---|---|
| `src/domain/` | Tags, seuils, AMDEC, plan préventif, gammes | `tags.yaml`, `amdec.yaml` |
| `src/ingest/` | Lecture DCS et qualité de donnée | export DCS original |
| `src/features/` | Variables physiques et temporelles | tags majoritairement inférés |
| `src/models/` | Détection hybride et explicabilité | référence d'apprentissage |
| `src/agents/` | Diagnostic/action et contrôle du diagnostic | faits recalculés + domaine |
| `src/governance/` | Évaluation adversariale du Judge | fautes injectées connues |
| `src/analytics/` | Indicateurs d’exploitation | mesures seules, aucune hypothèse |
| `src/operations/` | Cycle de vie des alarmes ISA-18.2 et traçabilité des interventions | deux bases SQLite locales |
| `src/realtime/` | Rejeu borné dans le temps | pipeline déterministe |
| `api/` | Contrat HTTP et interface opérateur | mêmes objets métier |

## Invariants de sûreté

1. **Pas d'imputation silencieuse.** Une mesure mauvaise, gelée ou saturée
   devient indisponible ; elle n'est jamais remplacée par une valeur plausible.
2. **Pas de conclusion mécanique sur le seul score statistique.** Les règles
   AMDEC, l'état de marche et la persistance restent explicites.
3. **Pas de diagnostic d'un angle mort.** Le Judge sanctionne toute
   revendication concernant un mode non observable par les tags disponibles.
4. **Pas de dépendance LLM pour l'exploitation.** Le rejeu et le flux utilisent
   toujours le chemin déterministe. Sur une analyse à la demande, le premier
   échec LLM ouvre un coupe-circuit et le résultat par règles reste disponible.
5. **Pas de métrique supervisée inventée.** En l'absence de panne étiquetée,
   AUC, rappel et F1 de détection ne sont pas revendiqués.
6. **Aucune valorisation monétaire.** Aucun montant n'est calculé nulle part.
   Deux tests interdisent le retour de la couche économique : l'un vérifie
   qu'aucun endpoint économique ne répond, l'autre qu'aucun indicateur ne porte
   de montant.

*(Le point 6 était auparavant rédigé comme une note d'édition expliquant la
suppression d'un principe antérieur. Un lecteur comptait six invariants là où il
y en avait cinq et un commentaire.)*

## Modèles et reproductibilité

### L'indicateur d'encrassement est le coefficient d'échange global

**Ce paragraphe décrivait le résidu de duty comme la référence du système.**
C'est l'approche qu'[ADR-001](decisions/ADR-001-indicateur-encrassement.md)
démontre algébriquement circulaire : la cible est déjà une combinaison linéaire
de deux régresseurs présents, R² = 0,968 contre 0,962 **sans aucun
apprentissage**, et corr(résidu, écart de consigne) = −0,94. Le résidu a été
renommé `regulation_effort` et ne fonde jamais un diagnostic d'encrassement.

Le diagnostic repose sur le **coefficient d'échange global UA**, calculé par la
méthode efficacité-NTU :

```text
ε   = (T_entrée − T_sortie) / (T_entrée − T_eau_de_mer)
NTU = −ln(1 − ε)
UA  = C_acide · NTU
```

La température d'eau de mer vient de la climatologie de Safi
([ADR-002](decisions/ADR-002-temperature-eau-de-mer.md)) : c'est une grandeur
extérieure à l'atelier, qu'aucune boucle de régulation ne contraint, et c'est ce
qui rend l'indicateur interprétable. Une référence linéaire apprend
`UA(F^0,8, T_moyenne, T_eau)` ; le résidu est l'indicateur, et
`Rf = 1/UA − 1/UA_attendu` la grandeur suivie par le service fiabilité.

**UA est un UA apparent** : le débit d'eau de mer n'est pas instrumenté, et
c'est lui que la régulation manipule. La grandeur mesure donc l'état de la
surface d'échange **multiplié par** l'action de la boucle froide. Tant que la
vanne conserve de la marge, elle compense un début d'encrassement.

L'Isolation Forest est entraînée uniquement sur les heures de marche établie
exploitables, avec graine fixe. Ses contributions sont calculées par occlusion
exacte de chaque variable, pas par une explication générative.

### Période de référence

Les trois références — conductance, effort de régulation, température d'entrée —
partagent la **même fenêtre** : les 40 % premières heures de marche établie,
constante `REFERENCE_FRACTION` définie une seule fois dans
`src/features/thermal.py`. `REFERENCE_END = None` par défaut était une **fuite
de données** : la conductance s'ajustait sur les quatorze mois, y compris la
dégradation qu'elle doit détecter. Voir
[ADR-009](decisions/ADR-009-periode-de-reference-commune.md).

Le choix de 40 % reste arbitraire et il est traité comme tel :
`src.governance.sensitivity` mesure ce que devient le diagnostic quand on
déplace cette borne, et le résultat est publié sur l'onglet Contrôle.

## Exécution et déploiement

En local :

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m api
```

`python -m api` est la forme à retenir : elle **honore `API_HOST` et
`API_PORT`**. Ce document écrivait auparavant `-m uvicorn api.main:app --host
127.0.0.1 --port 8000`, c'est-à-dire la troisième source de vérité que
`api/__main__.py` a été écrit pour supprimer — son en-tête cite nommément « le
README et le runbook [qui] passaient leurs propres valeurs sur la ligne de
commande ». La forme uvicorn reste valable ; la ligne de commande prime alors
sur la configuration.

En conteneur, un seul worker est imposé : chaque worker reconstruirait
inutilement l'historique et le modèle en mémoire. Les données sont montées en
lecture seule et le processus s'exécute avec l'utilisateur non privilégié
`e7301`.

```bash
docker compose up -d --build
docker compose ps
```

## Décisions actives

| Sujet | Décision |
|---|---|
| Runtime | Python 3.10+ / cible conteneur Python 3.11 |
| API et UI | FastAPI + HMI E7301 servie sur la même origine |
| Persistance | fichiers versionnés et volumes pour modèles/rapports |
| Détection | règles AMDEC + Isolation Forest non supervisée |
| Explicabilité | attribution déterministe par occlusion |
| Agent/Judge | règles déterministes, LLM optionnel et non bloquant |
| Accès | e-mail de quart, session opaque, cookie HttpOnly/SameSite et CSRF ; désactivable |
| Notification | destinataire de session, SMTP asynchrone, seuil et temporisation anti-rafale |
| Déploiement | image multi-stage, utilisateur non-root, 1 worker |

Voir l'[index des décisions d'architecture](decisions/INDEX.md), qui recense
les onze décisions structurantes et les choix v1 qu'elles remplacent.

## Frontière de la version démonstrateur

- l'environnement cible pourra substituer une fédération d'identité au mot de
  passe local et terminer TLS en frontal ;
- l'adaptateur d'acquisition temps réel remplacera le fichier de rejeu sans
  changer le contrat des douze tags ;
- une base d'audit durable pourra remplacer la mémoire du démonstrateur ;
- l'ajout de tags côté eau de mer et protection anodique lèvera les angles morts
  déjà déclarés par le Judge ;
- un historique d'interventions horodatées permettra de compléter les métriques
  non supervisées par rappel, précision et délai de détection.
