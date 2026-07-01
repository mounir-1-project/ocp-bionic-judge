# Flux de Données — OCP Bionic Judge

## Vue d'ensemble du pipeline complet

```
╔══════════════════════════════════════════════════════════════════════╗
║                    SOURCES DE DONNÉES                                ║
║                                                                      ║
║  [BROYEUR_01]  [POMPE_02]  [CONVOYEUR_03]  [REACTEUR_04]  [COMP_05] ║
║       │             │            │               │              │    ║
║       └─────────────┴────────────┴───────────────┴──────────────┘   ║
║                              │  30s interval                         ║
╚══════════════════════════════╪═════════════════════════════════════════╝
                               │
                               ▼
╔══════════════════════════════════════════════════════════════════════╗
║                    COUCHE INGESTION                                  ║
║                                                                      ║
║   data_generator.py (simulation) / Vrai capteur (production)        ║
║                                                                      ║
║   • Validation des plages physiques (temp: 20-90°C)                 ║
║   • Détection des NaN (coupures capteur)                             ║
║   • Ajout du label "shift" (matin/soir/nuit)                        ║
║   • Insertion dans sensor_readings (PostgreSQL)                     ║
╚══════════════════════════════╪═════════════════════════════════════════╝
                               │
                               ▼
╔══════════════════════════════════════════════════════════════════════╗
║                    FEATURE ENGINEERING                               ║
║                  (feature_engineering.py)                            ║
║                                                                      ║
║   Données brutes (8 cols)  ──►  24 features ML ciblées              ║
║                                                                      ║
║   SensorCutoffIndicator    → is_nan_temperature, ... (5 flags)      ║
║   TemporalFeatureExtractor → hour, day_of_week, is_weekend, shift   ║
║   ZScoreNormalizer         → temperature_zscore (par machine, 5)    ║
║   RollingFeatureExtractor  → temperature_local_z (z glissant, 5)    ║
║   DeltaFeatureExtractor    → temperature_delta (|Δ|, 5)             ║
║   FinalScaler              → StandardScaler (features continues)     ║
╚══════════════════════════════╪═════════════════════════════════════════╝
                               │
                    ┌──────────┴──────────┐
                    │                     │
                    ▼                     ▼
          ╔══════════════╗     ╔══════════════════════╗
          ║  ENTRAÎNE-   ║     ║     INFÉRENCE         ║
          ║  MENT        ║     ║     (predict.py)      ║
          ║ (train.py)   ║     ║                       ║
          ║              ║     ║  Charge best_model    ║
          ║  IF / SVM /  ║     ║  Score chaque lecture ║
          ║  HDBSCAN     ║     ║  → anomaly_score[0,1] ║
          ║  GridSearch  ║     ║  → severity label     ║
          ║  MLflow log  ║     ║  → SHAP explanation   ║
          ║      │       ║     ║         │             ║
          ║      ▼       ║     ║         ▼             ║
          ║  best_model  ║     ║    ml_decisions       ║
          ║  .joblib     ║     ║    (PostgreSQL)       ║
          ╚══════════════╝     ╚══════════════════════╝
                                          │
                               ┌──────────┴──────────┐
                               │                     │
                               ▼                     ▼
              ╔═══════════════════════╗   ╔════════════════════╗
              ║   DETECTION AGENT    ║   ║   DRIFT DETECTOR   ║
              ║ (detection_agent.py) ║   ║ (drift_detector.py)║
              ║                      ║   ║                    ║
              ║  LangChain ReAct     ║   ║  PSI toutes les    ║
              ║  + Gemini 2.0 Flash  ║   ║  100 prédictions   ║
              ║    (Google AI)       ║   ║                    ║
              ║                      ║   ║  KS-test           ║
              ║  Outils :            ║   ║                    ║
              ║  ├ get_anomaly_data  ║   ║  Alert si          ║
              ║  ├ get_machine_hist  ║   ║  PSI > 0.2 ou      ║
              ║  └ get_shap_expl.   ║   ║  p-val < 0.05      ║
              ║         │            ║   ║       │            ║
              ║         ▼            ║   ║       ▼            ║
              ║  AgentDecision JSON  ║   ║  audit_log         ║
              ╚═══════════╪══════════╝   ╚════════════════════╝
                          │
                          ▼
              ╔═══════════════════════╗
              ║     JUDGE AGENT       ║
              ║  (judge_agent.py)     ║
              ║                       ║
              ║  Gemini appel direct  ║
              ║  5 critères pondérés  ║
              ║                       ║
              ║  Score < 6 → ALERT   ║
              ║         │             ║
              ║         ▼             ║
              ║  judge_evaluations    ║
              ║  + audit_log          ║
              ╚═══════════╪═══════════╝
                          │
                          ▼
              ╔═══════════════════════╗
              ║     GOVERNANCE        ║
              ║   (governance.py)     ║
              ║                       ║
              ║  Fenêtres 1h/24h/7d  ║
              ║  Métriques :         ║
              ║  • confiance judge   ║
              ║  • taux désaccord    ║
              ║  • conformité OCP    ║
              ║  • alertes critiques ║
              ║         │             ║
              ║         ▼             ║
              ║  audit_log (rapport) ║
              ╚═══════════╪═══════════╝
                          │
               ┌──────────┴──────────┐
               ▼                     ▼
   ╔═══════════════════╗  ╔════════════════════════╗
   ║    FastAPI        ║  ║  Frontend React/Vite   ║
   ║   (api/main.py)   ║  ║  (frontend/src/)       ║
   ║                   ║  ║                        ║
   ║  POST /analyze    ║  ║  SensorsPage           ║
   ║  GET  /decisions  ║  ║  JudgePage             ║
   ║  GET  /governance ║  ║  GovernancePage        ║
   ║  GET  /health     ║  ║  Auto-refresh 30s      ║
   ║  GET  /auth/me    ║  ║  JWT httpOnly cookie   ║
   ╚═══════════════════╝  ╚════════════════════════╝
```

---

## Volumétrie attendue par table (6 mois production)

| Table | Lignes | Croissance/jour | Taille estimée |
|-------|--------|-----------------|----------------|
| `machines` | 5 | 0 | < 1 KB |
| `sensor_readings` | 2,592,000 | 17,280 | ~500 MB |
| `anomalies` | ~4,000 | ~65 | ~2 MB |
| `ml_decisions` | 2,592,000 | 17,280 | ~1 GB (avec features_json) |
| `judge_evaluations` | ~1,000 | ~10-20 | < 10 MB |
| `audit_log` | ~5,000 | ~50 | < 5 MB |

**Total estimé : ~1.5 GB pour 6 mois**

→ PostgreSQL gère ça facilement. TimescaleDB recommandé au-delà de 50M lignes.
