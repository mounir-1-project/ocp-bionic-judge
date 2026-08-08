# Runbook opérationnel — E7301

**Version active : 3.0**

*Dernière confrontation de ce runbook au code : 7 août 2026 — commandes de
démarrage, portes de déploiement, comportement du canal d'escalade, contrôles
quotidiens.*

Ce runbook concerne le service FastAPI local de la version 3, seule
architecture présente dans le dépôt.

## 1. Précontrôles

Depuis la racine du dépôt :

```powershell
Test-Path data\raw\DATA.xlsx
Copy-Item .env.example .env   # uniquement si une configuration locale est nécessaire
.\.venv\Scripts\python.exe -c "from src.config import validate; print(validate())"
```

Le dernier résultat doit être `[]`. La clé Gemini n'est pas requise. Sans clé,
le diagnostic et le Judge utilisent les règles déterministes.

## 2. Démarrage local

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m api
```

`python -m api` **honore `API_HOST` et `API_PORT`**. Ce runbook écrivait
`-m uvicorn api.main:app --host 0.0.0.0 --port 8000` : c'est l'une des sources
de vérité concurrentes que `api/__main__.py` a été écrit pour supprimer, et son
en-tête nomme explicitement « le README et le runbook ». Pour écouter sur
toutes les interfaces, poser `API_HOST=0.0.0.0` dans `.env`.

Contrôles :

```powershell
Invoke-RestMethod http://localhost:8000/api/health
Invoke-RestMethod http://localhost:8000/api/config
```

Le dashboard est disponible sur `http://localhost:8000`. **La sonde de
disponibilité est `/api/health/ready`**, qui répond 200 ou 503.

N'attendez pas `status: ok` sur `/api/health` : ce statut est **inatteignable
par construction**. Il vaut `degraded` tant qu'aucun modèle n'est promu, et
aucun ne peut l'être : **`labels_gmao` et `validation_externe` sont en échec
définitif**, faute d'historique de pannes étiqueté et de validation hors site.
Aucun commit ne les franchira. `degraded` est donc l'état nominal du
démonstrateur, et non un incident.

Les trois portes que le code décide — causalité temporelle, redondance des
grandeurs du modèle, taux d'alertes hors période — sont, elles, **franchies**.

Le poste en affiche **sept**, pas cinq : deux autres sont publiées et en échec
**sans bloquer**, et il faut savoir pourquoi avant de les lire comme des
incidents.

| porte | état | nature |
|---|---|---|
| `redondance_hors_modele` | échec | **algébriquement infranchissable** — le résidu d'effort *est* l'écart de consigne (ADR-001) |
| `derive_de_distribution` | échec | le PSI n'est interprétable que sur un pli saisonnièrement couvert, et le corpus n'en offre aucun |

Un rapport de sept portes dont quatre en échec est donc l'**état nominal**, et
la promotion reste légitimement refusée pour les deux seules raisons qui
valent : `labels_gmao` et `validation_externe`.

La promotion du modèle et la disponibilité du service sont deux questions
distinctes : `/api/health/model` répond à la première, `/api/health/ready` à la
seconde.

Le registre d'alarmes est conservé dans `data/runtime/alarms.db`. Il trace
apparition, dernière occurrence, acquittement, shelving, propriétaire,
commentaire et retour à la normale. Le sauvegarder avec les journaux de quart ;
ne pas le confondre avec une historisation DCS ou GMAO.

### Identification technicien

Le dépôt ne contient aucun mot de passe ni empreinte. **Chaque technicien a son
propre compte**, enregistré par la commande dédiée :

```powershell
.\.venv\Scripts\python.exe scripts\manage_operators.py add      # crée un compte
.\.venv\Scripts\python.exe scripts\manage_operators.py list     # liste les techniciens
.\.venv\Scripts\python.exe scripts\manage_operators.py passwd   # change un mot de passe
.\.venv\Scripts\python.exe scripts\manage_operators.py remove   # retire un technicien
```

Le mot de passe est saisi masqué et confirmé, jamais passé en argument : il
apparaîtrait dans l'historique du terminal et dans la liste des processus. Le
registre vit dans `data/runtime/operators.json`, ignoré par git, en droits 600,
et ne stocke que des empreintes PBKDF2-SHA256 à 600 000 itérations avec un sel
distinct par technicien.

**L'accès protégé s'active de lui-même** dès qu'un compte existe : aucune
variable d'environnement à positionner, donc aucun oubli possible. Tant
qu'aucun compte n'est enregistré, le poste s'ouvre sur une prise de quart
déclarative, et l'écran le dit explicitement.

```dotenv
AUTH_IDLE_MINUTES=30
AUTH_ABSOLUTE_HOURS=8
AUTH_SECURE_COOKIE=true
```

`AUTH_SECURE_COOKIE=true` exige un accès HTTPS. Les sessions expirent côté
serveur après 30 minutes d'inactivité et 8 heures au maximum.

> **Le mode à empreinte partagée — `AUTH_ENABLED` et `AUTH_PASSWORD_HASH` —
> reste supporté pour les déploiements existants, mais ne doit pas être utilisé
> pour une nouvelle installation.** L'adresse de session détermine le
> destinataire des états critiques : un secret partagé ne permet ni de savoir
> qui a ouvert la session, ni de révoquer un départ individuellement. Voir
> [ADR-007](../decisions/ADR-007-identification-technicien.md).

### Activer les notifications

Configurer `SMTP_HOST` et `SMTP_FROM`, puis vérifier
`/api/notifications/status`. `ALERT_EMAIL_TO` reste un destinataire
permanent facultatif. **Il n'est pas remplacé par l'e-mail de session : les deux
reçoivent.** `add_recipient` ajoute l'adresse du technicien à l'ensemble sans en
retirer la précédente, et l'escalade est envoyée à chacune. À la déconnexion,
seule l'adresse de session est retirée. C'est le comportement voulu — une
astreinte permanente ne doit pas cesser d'être prévenue parce qu'un technicien
s'est connecté — mais le runbook annonçait l'inverse. *Mesuré : avec
`ALERT_EMAIL_TO=astreinte@…` et une session ouverte par `mounir@…`, les
destinataires sont les deux.* Le bouton
**Tester le canal** n'est actif que si le relais et un destinataire sont prêts.

Les emails CRITICAL sont envoyés hors du thread de rejeu, dédupliqués
par mode et sévérité, avec un délai de 60 minutes par défaut. Ils complètent
l'alarme visible dans l'HMI ; ils ne doivent jamais être utilisés comme unique
moyen d'alerte.

## 3. Démarrage conteneurisé

```powershell
docker compose up -d --build
docker compose ps
docker compose logs --tail 100 e7301
```

Le fichier `data/raw/DATA.xlsx` est monté en lecture seule. Ne jamais écrire
dans ce fichier depuis le service.

Arrêt normal :

```powershell
docker compose down
```

## 4. Rejeu et analyse

Dans le dashboard, sélectionner la vitesse puis **Démarrer le rejeu**.
Le rejeu est toujours déterministe et n'appelle pas le LLM, afin de garantir
une latence bornée.

Commandes API utiles :

```powershell
Invoke-RestMethod -Method Post -ContentType application/json `
  -Body '{"speed":120,"analyze_every":3}' `
  http://localhost:8000/api/replay/start

Invoke-RestMethod http://localhost:8000/api/replay/state
Invoke-RestMethod http://localhost:8000/api/replay/alerts?n=20
Invoke-RestMethod -Method Post http://localhost:8000/api/replay/stop
```

Analyse d'un instant précis :

```powershell
$body = '{"timestamp":"2024-10-15T12:00:00"}'
Invoke-RestMethod -Method Post -ContentType application/json `
  -Body $body http://localhost:8000/api/analyze
```

## 5. Contrôles quotidiens

| Contrôle | Endpoint | Condition attendue |
|---|---|---|
| Disponibilité | `/api/health/ready` | HTTP 200 (`status = ready`) |
| Configuration | `/api/config` | chemin DCS correct, secret non exposé |
| Capteurs | `/api/sensor-health` | dérives/gels connus expliqués |
| Alertes | `/api/replay/alerts` | volume compatible avec l'exploitation |
| Judge | `/api/judge/audit` | pas d'avertissement d'auto-surveillance |
| Indicateurs d'exploitation | `/api/kpi` | cinq figures, chacune avec son `evidence_level` |

Une note Judge élevée n'est pas une preuve de performance de détection. La
validation du Judge se lit dans `/api/judge/evaluation` et dans le banc
d'injection de fautes.

## 6. Incidents

### L'API refuse de démarrer

Lire la première erreur de configuration dans les logs. Causes habituelles :

- `DCS_EXPORT` absent ou mal monté ;
- `CONTAMINATION` hors de l'intervalle `]0, 0.5[` ;
- vitesse de rejeu non positive ;
- niveau de log inconnu.
- authentification activée sans empreinte PBKDF2 ;
- sévérité ou délai de notification invalide.

Corriger `.env` ou le montage, puis redémarrer.

### Le dashboard s'affiche mais les graphiques restent vides

1. Vérifier `/api/health`.
2. Vérifier `/api/timeseries?max_points=100`.
3. Ouvrir la console du navigateur et relever l'erreur.
4. Vérifier que l'actif JavaScript local de graphiques est servi par l'image.

Ne pas réintroduire de dépendance CDN sur un réseau industriel isolé.

### Un capteur affiche une disponibilité faible

Consulter `/api/sensor-health`. Un gel ou une saturation est volontairement
transformé en donnée indisponible. Ne pas corriger par interpolation globale.
Comparer avec les codes qualité du DCS puis ouvrir une intervention
instrumentation si le défaut est confirmé.

### La clé LLM est absente ou rejetée

Ce n'est pas un incident bloquant. Le service continue en mode règles. Sur une
analyse à la demande, le premier échec désactive le client LLM pour le reste du
processus et journalise le repli. Le rejeu n'utilise jamais ce client.

### Trop d'épisodes

Ne pas augmenter arbitrairement le seuil. Vérifier d'abord :

- l'état de marche et les arrêts ;
- la qualité des tags ;
- la fenêtre de référence — 40 % des heures de marche par défaut, dont l'analyse de sensibilité publie l'influence sur `/api/sensitivity` ;
- un changement réel de régime opératoire.

Tout changement de seuil doit être tracé, évalué sur l'historique complet et
approuvé avec le métier.

### Suspicion de diagnostic dangereux

Arrêter le rejeu si nécessaire, conserver le timestamp et la réponse JSON,
puis exécuter :

```powershell
.\.venv\Scripts\python.exe -m src.governance.judge_eval
.\.venv\Scripts\python.exe -m pytest tests\test_agents_judge.py -q
```

Le système reste une aide à la décision. Les consignations, démontages,
tamponnages et remises en service restent soumis aux gammes et autorisations
OCP.

## 7. Validation avant livraison

```powershell
.\.venv\Scripts\python.exe -m ruff check src api tests scripts
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m src.governance.judge_eval
docker compose config --quiet
```

Les résultats Judge de référence sont archivés dans `reports/`. Les métriques
supervisées de détection (AUC, F1, rappel) sont interdites tant qu'un historique
de pannes étiquetées n'est pas disponible.

## 8. Sauvegarde et audit

Le fichier DCS source est un intrant immuable à sauvegarder selon la politique
OCP. Les volumes `e7301_models` et `e7301_reports` peuvent être sauvegardés,
mais le modèle est reproductible depuis les données, le code et la
configuration. Pour une production connectée, prévoir un journal d'audit
externe, horodaté et non modifiable.
