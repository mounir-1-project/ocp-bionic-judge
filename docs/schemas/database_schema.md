# Schéma de Base de Données — OCP Bionic Judge

**Base :** PostgreSQL 15 (dev : SQLite via SQLAlchemy)  
**Version :** v1.1  
**Dernière mise à jour :** 2024-02-10

---

## Diagramme ERD (Entity-Relationship Diagram)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          OCP BIONIC — DATABASE SCHEMA                       │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────────┐         ┌────────────────────────────────────────────────┐
│    machines      │         │               sensor_readings                  │
├──────────────────┤         ├────────────────────────────────────────────────┤
│ PK id       TEXT │◄────────│ PK id          BIGSERIAL                       │
│    name     TEXT │  1      │ FK machine_id  TEXT          NOT NULL          │
│    type     TEXT │  │      │    timestamp   TEXT          NOT NULL  ← index │
│    location TEXT │  │      │    temperature DOUBLE PRECISION                │
│    installed TEXT│  │      │    vibration   DOUBLE PRECISION                │
│    created_at TS │  │      │    pression    DOUBLE PRECISION                │
└──────────────────┘  │      │    courant     DOUBLE PRECISION                │
         │            │      │    rpm         DOUBLE PRECISION                │
         │            │ N    │    shift       TEXT  (matin/soir/nuit)         │
         │            └──────┤                                                │
         │                   └────────────────────────────────────────────────┘
         │
         │            ┌────────────────────────────────────────────────┐
         │            │                  anomalies                     │
         │            ├────────────────────────────────────────────────┤
         ├────────────│ PK id              BIGSERIAL                   │
         │  1:N       │ FK machine_id      TEXT         NOT NULL       │
         │            │    timestamp       TEXT         NOT NULL       │
         │            │    anomaly_type    TEXT  (spike/drift/cutoff)  │
         │            │    sensor_affected TEXT  (temperature/...)     │
         │            │    severity        TEXT  (WARNING/CRITICAL)    │
         │            │    injected        INTEGER  DEFAULT 1          │
         │            └────────────────────────────────────────────────┘
         │
         │            ┌────────────────────────────────────────────────┐
         │            │                 ml_decisions                   │
         │            ├────────────────────────────────────────────────┤
         ├────────────│ PK id              BIGSERIAL                   │
         │  1:N       │ FK machine_id      TEXT         NOT NULL       │
         │            │    timestamp       TEXT         NOT NULL       │
         │            │    anomaly_score   DOUBLE PRECISION [0.0-1.0]  │
         │            │    is_anomaly      INTEGER      (0 ou 1)       │
         │            │    severity        TEXT  (NORMAL/WARNING/CRIT) │
         │            │    model_version   TEXT  (IsolationForest/...) │
         │            │    inference_ms    DOUBLE PRECISION            │
         │            │    features_json   TEXT  (JSON features SHAP)  │
         │            │    created_at      TIMESTAMP  DEFAULT NOW()    │
         │            └──────────────────────┬─────────────────────────┘
         │                                   │ 1
         │                                   │
         │                                   │ N
         │            ┌──────────────────────▼─────────────────────────┐
         │            │              judge_evaluations                  │
         │            ├────────────────────────────────────────────────┤
         │            │ PK id                  BIGSERIAL               │
         │            │ FK decision_id          BIGINT  → ml_decisions  │
         ├────────────│ FK machine_id           TEXT    NOT NULL        │
         │  1:N       │    timestamp            TEXT    NOT NULL        │
         │            │    global_score         DOUBLE  [0.0-10.0]     │
         │            │    relevance_score      DOUBLE  [0.0-10.0]     │
         │            │    history_score        DOUBLE  [0.0-10.0]     │
         │            │    confidence_score     DOUBLE  [0.0-10.0]     │
         │            │    compliance_score     DOUBLE  [0.0-10.0]     │
         │            │    feasibility_score    DOUBLE  [0.0-10.0]     │
         │            │    agreement            INTEGER (0=non, 1=oui) │
         │            │    feedback             TEXT                    │
         │            │    flagged_issues       TEXT  (JSON array)     │
         │            │    created_at           TIMESTAMP              │
         │            └────────────────────────────────────────────────┘
         │
         │            ┌────────────────────────────────────────────────┐
         │            │                  audit_log                     │
         │            ├────────────────────────────────────────────────┤
         └────────────│ PK id          BIGSERIAL                       │
              1:N     │ FK machine_id  TEXT  (nullable)                │
                      │    timestamp   TEXT         NOT NULL           │
                      │    event_type  TEXT  (DRIFT_CHECK/JUDGE/...)   │
                      │    user_id     TEXT  DEFAULT 'system'          │
                      │    action      TEXT         NOT NULL           │
                      │    details     TEXT  (JSON payload)            │
                      │    severity    TEXT  (INFO/WARNING/CRITICAL)   │
                      └────────────────────────────────────────────────┘
```

---

## Flux de données entre les tables

```
sensor_readings
      │
      │  ML Pipeline (train.py + predict.py)
      ▼
ml_decisions ──────────────────────────────────┐
      │                                         │
      │  Detection Agent                        │
      │  (lit ml_decisions + sensor_readings)   │
      ▼                                         │
  [AgentDecision JSON]                          │
      │                                         │
      │  Judge Agent                            │
      ▼                                         │
judge_evaluations ◄────────────────────────────┘
      │
      │  Governance Module
      ▼
audit_log  ◄──── drift_detector (PSI, KS)
               ◄──── governance (alertes)
               ◄──── judge (désaccords)
```

---

## Description détaillée de chaque table

### `machines` — Référentiel des équipements

```sql
CREATE TABLE machines (
    id          TEXT PRIMARY KEY,        -- ex: "BROYEUR_01"
    name        TEXT NOT NULL,           -- ex: "Broyeur à Boulets"
    type        TEXT NOT NULL,           -- ex: "broyeur" (enum: broyeur|pompe|convoyeur|reacteur|compresseur)
    location    TEXT,                    -- ex: "Khouribga Site A"
    installed   TEXT,                    -- date de mise en service
    created_at  TIMESTAMP DEFAULT NOW()
);
```

**Cardinalité :** 5 lignes fixes (les 5 machines du projet)  
**Croissance :** Quasi-nulle — une nouvelle machine = 1 insertion manuelle

---

### `sensor_readings` — Lectures capteurs (table principale, haute volumétrie)

```sql
CREATE TABLE sensor_readings (
    id          BIGSERIAL PRIMARY KEY,
    machine_id  TEXT NOT NULL REFERENCES machines(id),
    timestamp   TEXT NOT NULL,     -- ISO 8601 : "2024-01-15T14:23:30"
    temperature DOUBLE PRECISION,  -- °C [20-90]  — NULL si coupure capteur
    vibration   DOUBLE PRECISION,  -- mm/s [0-10] — NULL si coupure capteur
    pression    DOUBLE PRECISION,  -- bar [1-10]  — NULL si coupure capteur
    courant     DOUBLE PRECISION,  -- A [0-50]    — NULL si coupure capteur
    rpm         DOUBLE PRECISION,  -- tr/min [0-3000] — NULL si coupure capteur
    shift       TEXT               -- matin|soir|nuit (calculé depuis timestamp)
);

CREATE INDEX idx_readings_machine_ts ON sensor_readings (machine_id, timestamp);
```

**Cardinalité :** ~2.5M lignes pour 6 mois (5 machines × 17,280 lectures/jour)  
**Croissance :** +17,280 lignes/jour en production  
**Optimisation :** L'index composite `(machine_id, timestamp)` est CRITIQUE pour les requêtes filtrées par machine et période. Sans lui, une requête simple prend 30s au lieu de 50ms.  
**Valeurs NULL :** Intentionnelles — indiquent une coupure capteur (type d'anomalie)

---

### `anomalies` — Anomalies injectées / détectées manuellement

```sql
CREATE TABLE anomalies (
    id              BIGSERIAL PRIMARY KEY,
    machine_id      TEXT NOT NULL REFERENCES machines(id),
    timestamp       TEXT NOT NULL,
    anomaly_type    TEXT NOT NULL,  -- spike | drift | sensor_cutoff
    sensor_affected TEXT,           -- temperature | vibration | ...
    severity        TEXT,           -- WARNING | CRITICAL
    injected        INTEGER DEFAULT 1  -- 1=simulé, 0=réel confirmé par technicien
);
```

**Cardinalité :** ~4,000 lignes pour 6 mois de simulation  
**Usage :** Sert de "vérité terrain" pour évaluer le F1-score du modèle ML  
**En production réelle :** La colonne `injected=0` contiendrait les vraies anomalies confirmées par les techniciens OCP → deviendrait la base d'un modèle supervisé

---

### `ml_decisions` — Prédictions du modèle ML (production)

```sql
CREATE TABLE ml_decisions (
    id              BIGSERIAL PRIMARY KEY,
    machine_id      TEXT NOT NULL,
    timestamp       TEXT NOT NULL,         -- timestamp de la lecture scorée
    anomaly_score   DOUBLE PRECISION,      -- [0.0-1.0] : 0=normal, 1=anomalie
    is_anomaly      INTEGER,               -- 1 si score > seuil, 0 sinon
    severity        TEXT,                  -- NORMAL | WARNING | CRITICAL
    model_version   TEXT,                  -- "IsolationForest" | "LOF" | ...
    inference_ms    DOUBLE PRECISION,      -- temps d'inférence en ms (monitoring perf)
    features_json   TEXT,                  -- JSON des valeurs SHAP {feature: value}
    created_at      TIMESTAMP DEFAULT NOW() -- quand la prédiction a été faite
);
```

**Cardinalité :** Même volumétrie que sensor_readings (1 décision par lecture scorée)  
**Colonne clé :** `inference_ms` — si la moyenne dépasse 10ms, le modèle est trop lent  
**`features_json` :** Stocke les top-3 features SHAP pour chaque prédiction → permet de rejouer l'explication sans recalculer SHAP

---

### `judge_evaluations` — Évaluations du Judge Agent

```sql
CREATE TABLE judge_evaluations (
    id                  BIGSERIAL PRIMARY KEY,
    decision_id         BIGINT REFERENCES ml_decisions(id),  -- quelle décision ML est évaluée
    machine_id          TEXT NOT NULL,
    timestamp           TEXT NOT NULL,
    global_score        DOUBLE PRECISION,   -- [0.0-10.0] score pondéré final
    relevance_score     DOUBLE PRECISION,   -- critère 1 (poids 25%)
    history_score       DOUBLE PRECISION,   -- critère 2 (poids 20%)
    confidence_score    DOUBLE PRECISION,   -- critère 3 (poids 20%)
    compliance_score    DOUBLE PRECISION,   -- critère 4 (poids 20%)
    feasibility_score   DOUBLE PRECISION,   -- critère 5 (poids 15%)
    agreement           INTEGER,            -- 1=accord, 0=désaccord (score >= 6)
    feedback            TEXT,               -- explication textuelle du Judge
    flagged_issues      TEXT,               -- JSON array ["WRONG_DIAGNOSIS", ...]
    created_at          TIMESTAMP DEFAULT NOW()
);
```

**Cardinalité :** 1 évaluation par analyse complète (moins fréquent que ml_decisions)  
**Colonne clé :** `agreement` — si la moyenne sur 24h descend sous 70%, alerter  
**`flagged_issues` :** Permet de catégoriser les types de désaccords pour améliorer le prompt

---

### `audit_log` — Journal d'audit universel

```sql
CREATE TABLE audit_log (
    id          BIGSERIAL PRIMARY KEY,
    timestamp   TEXT NOT NULL,
    event_type  TEXT NOT NULL,   -- DRIFT_CHECK | JUDGE_EVALUATION | GOVERNANCE_ALERT | GOVERNANCE_REPORT
    machine_id  TEXT,            -- NULL pour événements globaux (ex: drift)
    user_id     TEXT DEFAULT 'system',  -- 'system' = automatique, sinon email utilisateur
    action      TEXT NOT NULL,   -- description courte de l'action
    details     TEXT,            -- JSON complet de l'événement
    severity    TEXT DEFAULT 'INFO'  -- INFO | WARNING | CRITICAL
);
```

**Usage :** Table centrale d'audit pour la conformité OCP. Tout événement système s'y enregistre.  
**En production :** Cette table est la piste d'audit pour les auditeurs et régulateurs.  
**Rétention :** Recommandation = garder 2 ans (réglementation industrie)

---

## Indexes recommandés en production

```sql
-- Pour les requêtes de monitoring temps réel
CREATE INDEX idx_decisions_machine_ts ON ml_decisions (machine_id, created_at DESC);
CREATE INDEX idx_decisions_severity ON ml_decisions (severity) WHERE is_anomaly = 1;)_+

-- Pour le dashboard governance
CREATE INDEX idx_judge_machine_ts ON judge_evaluations (machine_id, created_at DESC);
CREATE INDEX idx_audit_event_ts ON audit_log (event_type, timestamp DESC);

-- Pour les séries temporelles (critique sur gros volumes)
CREATE INDEX idx_readings_ts ON sensor_readings (timestamp DESC);
```

---

## Migration vers TimescaleDB (étape suivante recommandée)

Quand les sensor_readings dépassent 10M lignes, convertir en hypertable :

```sql
-- Une seule commande — pas de migration des données
SELECT create_hypertable('sensor_readings', 'timestamp', 
                          chunk_time_interval => INTERVAL '1 week');

-- Active la compression automatique après 1 mois
ALTER TABLE sensor_readings SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'machine_id'
);
SELECT add_compression_policy('sensor_readings', INTERVAL '1 month');
```

**Résultat :** Réduction 10x de l'espace disque + requêtes de séries temporelles 50x plus rapides.
