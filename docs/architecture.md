# Architecture technique — surveillance E7301

**Version active : 3.0 — état vérifié le 25 juillet 2026**

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
src/features/      physique de l'échangeur, fenêtres temporelles, référence thermique
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
6. **Aucune valorisation monétaire.** Ce principe énonçait que « le scénario
   financier reste séparé des KPI mesurés » : il n'y a plus de scénario
   financier du tout. La couche économique a été retirée du périmètre, et deux
   tests interdisent son retour — l'un vérifie qu'aucun endpoint économique ne
   répond, l'autre qu'aucun indicateur ne porte de montant. Un principe qui
   décrit un sous-système supprimé donne au lecteur une carte fausse de ce
   qu'il va trouver dans le code.

## Modèles et reproductibilité

La référence thermique semi-empirique estime le duty attendu à conditions comparables. Le résidu
met en évidence un effort de refroidissement anormal sans confondre charge et
dégradation. L'Isolation Forest est entraînée uniquement sur les heures de
marche établie exploitables, avec graine fixe. Ses contributions sont calculées
par occlusion exacte de chaque variable, pas par une explication générative.

La période de référence est sélectionnée automatiquement dans l'historique
disponible selon les critères de marche établie et de qualité. La variable
`REFERENCE_END` permet de reproduire ou de déplacer cet ancrage sans modifier
le code.

## Exécution et déploiement

En local :

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

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
