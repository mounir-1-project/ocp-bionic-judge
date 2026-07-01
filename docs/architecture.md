# Architecture Technique — OCP Bionic Judge

---

## Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────────────┐
│                        COUCHES DU SYSTÈME                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────────────┐   │
│  │  PRÉSENTA-  │    │   API REST   │    │     NOTEBOOKS        │   │
│  │    TION     │    │  (FastAPI)   │    │  (Jupyter / EDA)     │   │
│  │(React/Vite) │    │              │    │                      │   │
│  └──────┬──────┘    └──────┬───────┘    └──────────────────────┘   │
│         │                  │                                        │
│  ──────────────────────────────────────────────────────────────     │
│                    COUCHE MÉTIER (src/)                             │
│  ──────────────────────────────────────────────────────────────     │
│         │                  │                                        │
│  ┌──────▼──────────────────▼──────────────────────────────────┐    │
│  │                     src/agents/                             │    │
│  │   DetectionAgent (LangChain ReAct)  JudgeAgent (Gemini)    │    │
│  └──────────────────────┬─────────────────────────────────────┘    │
│                         │                                           │
│  ┌──────────────────────▼─────────────────────────────────────┐    │
│  │                     src/models/                             │    │
│  │   train.py   predict.py   drift_detector.py                │    │
│  └──────────────────────┬─────────────────────────────────────┘    │
│                         │                                           │
│  ┌──────────────────────▼─────────────────────────────────────┐    │
│  │                   src/features/                             │    │
│  │               feature_engineering.py                       │    │
│  └──────────────────────┬─────────────────────────────────────┘    │
│                         │                                           │
│  ┌──────────────────────▼─────────────────────────────────────┐    │
│  │                     src/db.py                               │    │
│  │           SQLAlchemy Engine Factory                         │    │
│  └──────────────────────┬─────────────────────────────────────┘    │
│                         │                                           │
│  ──────────────────────────────────────────────────────────────     │
│                    COUCHE DONNÉES                                    │
│  ──────────────────────────────────────────────────────────────     │
│                         │                                           │
│  ┌──────────────────────▼─────────────────────────────────────┐    │
│  │              PostgreSQL (dev: SQLite)                       │    │
│  │  machines | sensor_readings | anomalies | ml_decisions      │    │
│  │  judge_evaluations | audit_log                              │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Principe de séparation des responsabilités

Chaque couche a une responsabilité unique et ne connaît pas les détails des autres.

| Couche | Responsabilité | Ne sait pas |
|--------|---------------|-------------|
| `dashboard/` | Afficher les données | Comment les données sont générées |
| `api/` | Exposer les fonctionnalités via HTTP | Comment le ML fonctionne |
| `src/agents/` | Raisonner et diagnostiquer | Comment les features sont calculées |
| `src/models/` | Scorer les anomalies | Qui utilise les scores |
| `src/features/` | Transformer les données | Quel modèle utilisera les features |
| `src/db.py` | Gérer les connexions BDD | Quelle requête sera exécutée |

**Pourquoi c'est important ?**
Si on change de modèle ML (ex: IF → LSTM), on ne modifie que `src/models/`. Le dashboard, l'API, et les agents n'ont pas besoin de changer.

---

## Décisions d'architecture clés

| Décision | Choix | Voir |
|----------|-------|------|
| Langage | Python 3.11 | ADR-001 |
| Base de données | PostgreSQL (dev: SQLite) | ADR-002 |
| Modèle ML | Isolation Forest | ADR-003 |
| Agents IA | LangChain + Gemini | ADR-004 |
| API | FastAPI | ADR-005 |
| Explicabilité | SHAP | ADR-006 |
| Tracking ML | MLflow | ADR-007 |

---

## Ce qui manque pour une vraie production (roadmap)

```
Version actuelle (v1.2) :
✅ Pipeline ML complet
✅ Agents IA avec gouvernance
✅ API + Frontend React/Vite (TypeScript + Recharts)
✅ Tests + CI/CD
✅ PostgreSQL
✅ JWT authentication (httpOnly cookie, 8h)
✅ Rate limiting (slowapi — 60 req/min par IP)
✅ Session persistence (GET /auth/me au rechargement)

Version 2.0 (recommandée avant déploiement OCP) :
○ Docker Compose (PostgreSQL + API + Frontend en 1 commande)
○ Alembic (migrations de schéma versionnées)
○ Logs centralisés (ELK Stack ou équivalent)
○ Alertes email/SMS pour anomalies CRITICAL

Version 3.0 (production à grande échelle) :
○ TimescaleDB pour les séries temporelles
○ Kafka pour l'ingestion en streaming
○ Kubernetes pour l'orchestration
○ Feature Store (ex: Feast) pour partager les features entre modèles
```
