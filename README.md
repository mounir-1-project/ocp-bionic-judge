# Détection d'anomalies du refroidisseur E7301

**S-PC-E7301 — Atelier Sulfurique PS III, Maroc Chimie, OCP Group**
Projet de stage — Programme Bionic · Mounir Sanbouli

---

## 🚀 Démarrage rapide

```bash
pip install -r requirements.txt
python -m interface
```

Puis ouvrir http://localhost:8000

**Identifiants** : `mounirsanbouli@gmail.com` / `123`

---

## 📁 Structure du projet

```
ocp-bionic-judge/
├── core/                    ← Logique métier
│   ├── detection/           ← Détection d'anomalies
│   ├── verification/        ← Contrôle de cohérence (Judge)
│   ├── knowledge/           ← Connaissance métier (AMDEC)
│   ├── features/            ← Ingénierie des features
│   ├── ingestion/           ← Chargement des données
│   ├── analytics/           ← Indicateurs opérationnels
│   └── alerts/              ← Alarmes et notifications
├── interface/               ← Dashboard web
│   ├── main.py              ← Serveur FastAPI
│   ├── dashboard.html       ← Page HTML
│   └── static/              ← Assets (JS, CSS, images)
├── replay/                  ← Rejeu temps réel
├── tests/                   ← Tests unitaires
├── data/                    ← Données DCS
└── docs/                    ← Documentation
```

---

## 🔬 Flux de données

```
Données DCS (Excel)
    ↓
Ingestion (core/ingestion/)
    ↓
Features (core/features/)
    ↓
Détection (core/detection/)
    ↓
Diagnostic (core/detection/detection_agent.py)
    ↓
Vérification (core/verification/)
    ↓
Résultat → Dashboard (interface/)
```

---

## 🎯 Fonctionnalités principales

| Composant | Description |
|-----------|-------------|
| **Détection** | 6 règles déterministes + Isolation Forest |
| **Vérification** | 8 contrôles du Judge (cohérence) |
| **LLM** | Gemini pour la rédaction (optionnel) |
| **Email** | Notifications automatiques sur pannes |
| **3D** | Modèle interactif du refroidisseur |
| **Replay** | Simulation temps réel des données |

---

## 📊 Résultats clés

- **10 180 horodatages** analysés (14 mois)
- **12 capteurs** DCS surveillés
- **13 modes** de défaillance AMDEC
- **30,2%** du risque couvert par les données
- **8 contrôles** de cohérence déterministes

---

## 📚 Documentation

| Document | Rôle |
|----------|------|
| `docs/README.md` | Index de la documentation |
| `docs/architecture.md` | Architecture technique |
| `docs/data_dictionary_E7301.md` | Dictionnaire des tags DCS |
| `docs/1-` à `8-` | Documents OCP originaux |

---

## 🧪 Tests

```bash
pytest tests/ -v
```

125 tests couvrant :
- Détection d'anomalies
- Vérification du Judge
- Connaissance métier
- Features physiques
- API REST
