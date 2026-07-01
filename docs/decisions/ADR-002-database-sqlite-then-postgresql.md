# ADR-002 — Base de données : SQLite en développement, PostgreSQL en production

**Statut** : Accepté (migration effectuée en v1.1)  
**Date** : 2024-01-15 (SQLite) → 2024-02-10 (migration PostgreSQL)  
**Auteur** : Mounir Sanbouli  

---

## Contexte

Le projet stocke 6 types de données dans une base relationnelle :
- lectures de capteurs (~2.5M lignes pour 6 mois)
- anomalies détectées
- décisions ML
- évaluations du Judge
- logs d'audit
- informations machines

Il faut choisir un système de base de données.

---

## ⚠️ Ce que nous aurions dû dire AVANT de coder

> **Règle d'or dans un vrai projet :** avant de choisir une technologie, tu évalues les critères suivants et tu les documentes. Si tu sautes cette étape, tu codes, puis tu dois tout réécrire (comme nous l'avons fait).

Critères à évaluer pour une BDD :
1. **Volume de données** — combien de lignes, quelle croissance ?
2. **Concurrence** — combien d'écritures simultanées ?
3. **Type de requêtes** — simples (CRUD) ou complexes (agrégations temporelles) ?
4. **Déploiement** — un serveur ou plusieurs ?
5. **Équipe** — quelle expertise disponible ?

---

## Phase 1 : SQLite (prototype)

### Décision initiale

Utiliser SQLite pour le prototype et le développement local.

### Pourquoi SQLite était correct pour commencer

| Avantage | Détail |
|----------|--------|
| Zéro configuration | Pas de serveur à installer |
| Un fichier unique | `data/ocp_bionic.db` — facile à partager |
| Intégré à Python | `import sqlite3` — pas de dépendance externe |
| Parfait pour 1 utilisateur | Développement local, tests, démos |

### Problèmes rencontrés avec SQLite (qui ont justifié la migration)

**Problème 1 — Concurrence en écriture :**
```
# FastAPI reçoit 5 requêtes simultanées qui écrivent en BDD
# SQLite les bloque les unes après les autres → timeout errors en production
ERROR: database is locked
```

**Problème 2 — Performance sur séries temporelles :**
```sql
-- Cette requête prend 8s sur 2.5M lignes en SQLite
SELECT machine_id, AVG(temperature) 
FROM sensor_readings 
WHERE timestamp >= '2024-01-01' 
GROUP BY machine_id, strftime('%H', timestamp)
```
→ En PostgreSQL + index : < 200ms

**Problème 3 — Pas de types avancés :**
- SQLite n'a pas de type `TIMESTAMP` natif → tout stocké en `TEXT`
- Pas de `ARRAY`, pas de `JSONB` (utile pour `features_json`)

**Problème 4 — Pas de monitoring :**
- Impossible d'utiliser pgAdmin, Datadog, ou tout outil de monitoring BDD

---

## Phase 2 : Migration vers PostgreSQL (v1.1)

### Décision

Migrer vers **PostgreSQL 15** pour la production.

### Pourquoi PostgreSQL et pas les autres ?

| Option | Évaluation | Verdict |
|--------|-----------|---------|
| **PostgreSQL** | Standard industrie, gratuit, excellente gestion des séries temporelles, JSON natif | ✅ Choisi |
| MySQL | Moins bon sur les requêtes analytiques, licence complexe | ❌ |
| MongoDB | NoSQL — pas adapté aux relations entre tables (machine → décision → évaluation) | ❌ |
| TimescaleDB | Extension de PostgreSQL optimisée time-series — **idéal pour la production OCP** | 🔮 Étape suivante |
| InfluxDB | Très bien pour IoT mais pas de SQL standard, écosystème limité pour ML | ❌ |

### Comment la migration a été faite

La migration propre utilise **SQLAlchemy** comme couche d'abstraction :

```python
# AVANT (lié à SQLite) :
import sqlite3
conn = sqlite3.connect("data/ocp_bionic.db")
df = pd.read_sql("SELECT * FROM sensor_readings WHERE machine_id = ?", conn, params=["BROYEUR_01"])

# APRÈS (compatible PostgreSQL ET SQLite) :
from src.db import get_engine
engine = get_engine()  # lit DATABASE_URL depuis .env
with engine.connect() as conn:
    df = pd.read_sql(text("SELECT * FROM sensor_readings WHERE machine_id = :mid"), 
                     conn, params={"mid": "BROYEUR_01"})
```

**Changements clés de syntaxe SQL :**

| SQLite | PostgreSQL | Explication |
|--------|-----------|-------------|
| `?` | `:param_name` | Paramètres nommés |
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGSERIAL PRIMARY KEY` | Auto-incrément |
| `REAL` | `DOUBLE PRECISION` | Flottants |
| `INSERT OR IGNORE` | `INSERT ... ON CONFLICT DO NOTHING` | Upsert |
| `executescript()` | Requêtes individuelles | SQLite-only |

### Fichier `.env` : le switch en une ligne

```bash
# Développement (SQLite — pas besoin de PostgreSQL installé)
DATABASE_URL=sqlite:///data/ocp_bionic.db

# Production OCP (PostgreSQL)
DATABASE_URL=postgresql://ocp_user:password@db-server:5432/ocp_bionic
```

Le code ne change PAS. Seul `.env` change.

---

## Étape suivante recommandée : TimescaleDB

**Quand activer TimescaleDB :**
- Quand les lectures capteurs dépassent 10M lignes
- Quand les requêtes de rolling average prennent > 1s

**Ce que ça change :**
```sql
-- Convertir sensor_readings en hypertable TimescaleDB
SELECT create_hypertable('sensor_readings', 'timestamp');

-- Cette requête devient 50x plus rapide automatiquement
SELECT time_bucket('15 minutes', timestamp) AS bucket, AVG(temperature)
FROM sensor_readings
WHERE machine_id = 'BROYEUR_01'
GROUP BY bucket ORDER BY bucket;
```

**Migration :** TimescaleDB est une extension PostgreSQL — même URL, même driver, juste `CREATE EXTENSION timescaledb`.

---

## Conséquences de la décision finale (PostgreSQL)

**Positives :**
- Concurrence multi-utilisateurs sans locks
- Requêtes analytiques 10-50x plus rapides
- Types natifs `TIMESTAMP`, `JSONB`, `ARRAY`
- Ecosystème monitoring (pgAdmin, pg_stat_statements)
- Compatible TimescaleDB sans refactor

**Négatives :**
- Nécessite un serveur PostgreSQL installé (Docker recommandé)
- Plus complexe à configurer pour un débutant
- Besoin de gérer les migrations de schema (Alembic)

## Leçon apprise

> Si au moment de conception on avait évalué les critères (volume, concurrence, requêtes temporelles), on aurait choisi PostgreSQL directement. SQLite est excellent pour les tests unitaires et le dev local, mais **jamais pour une API en production avec données industrielles**.
