# JOUR 1 — Comprendre le projet E7301 dans sa totalité

## Objectif du jour

À la fin de cette journée, tu dois être capable de :
- Expliquer en quoi consiste ton projet
- Identifier le problème industriel que tu résous
- Décrire le flux complet des données
- Connaître l'architecture du code et où trouve-t-on chaque chose
- Lancer le projet et naviguer dans l'interface

---

## PARTIE 1 — Le problème industriel (2h)

### 1.1 Qu'est-ce qu'un refroidisseur ?

Un **refroidisseur** est une machine qui enlève la chaleur d'un fluide. Dans notre cas :

- **Ce qu'on refroidit** : de l'acide sulfurique (H₂SO₄) à 98% de concentration
- **Avec quoi** : de l'eau de mer
- **Pourquoi** : l'acide sort de la réaction de contact à ~94°C, il faut le refroidir à ~66°C pour le séchage

**Fichier** : `docs/1- Fiche équipement REFROIDISSEUR DE SECHAGE PSIII.xls`

### 1.2 Comment ça marche physiquement ?

Imagine deux tubes emboîtés :
- Le **gros tube** (calandre, Ø 1118 mm) contient l'acide chaud
- Les **petits tubes** (1541 tubes, Ø 3/4") contiennent l'eau de mer froide

La chaleur traverse la paroi des petits tubes :
```
Acide chaud (94°C) → paroi → eau de mer (19°C)
```

Résultat : l'acide sort à ~66°C, l'eau de mer sort à ~22°C.

### 1.3 Le problème : l'encrassement

Au fil du temps, des dépôts de sels (sulfates) s'accumulent sur les parois des tubes. C'est l'**encrassement** (ou fouling en anglais).

**Conséquence** : la chaleur traverse moins bien → l'acide sort plus chaud → dommages en aval.

**Notre objectif** : détecter cet encrassement AVANT qu'il ne devienne critique.

### 1.4 Pourquoi c'est difficile ?

- On ne peut pas voir à l'intérieur du refroidisseur en fonctionnement
- La température de sortie dépend de beaucoup de facteurs (débit, température d'entrée, etc.)
- Un simple seuil sur la température ne suffit pas

**Solution** : un système intelligent qui combine des règles physiques et du Machine Learning.

---

## PARTIE 2 — Le flux de données (2h)

### 2.1 De où viennent les données ?

Les données viennent du **DCS** (Distributed Control System), le système de contrôle automatique de l'usine.

**Fichier** : `data/raw/DATA.xlsx`

Contenu :
- **10 180 lignes** = 10 180 heures de fonctionnement
- **14 mois** (janvier 2024 → février 2025)
- **12 colonnes** = 12 capteurs qui mesurent températures, débits, titres

### 2.2 Le flux complet

```
1. DATA.xlsx (données brutes)
   ↓
2. INGESTION (core/ingestion/dcs_loader.py)
   - Lecture du fichier Excel
   - Détection des capteurs défaillants
   - Classification : marche / arrêt / transitoire
   - Résultat : un tableau propre avec des NaN là où les données sont mauvaises
   ↓
3. FEATURES (core/features/thermal.py + e7301_features.py)
   - Calcul du coefficient d'échange UA
   - Calcul de 11 variables physiques (features)
   - Résultat : un tableau avec 11 colonnes de variables calculées
   ↓
4. DÉTECTION (core/detection/detector.py)
   - 6 règles déterministes (si X alors anomalie)
   - Isolation Forest (modèle ML qui trouve les anomalies)
   - Résultat : score d'anomalie + liste de constatations
   ↓
5. DIAGNOSTIC (core/detection/detection_agent.py)
   - Transforme les constatations en language opérateur
   - Rattache à l'AMDEC (modes de défaillance)
   - Propose une action corrective
   - Résultat : un diagnostic complet avec action recommandée
   ↓
6. CONTRÔLE (core/verification/judge_agent.py)
   - Vérifie que le diagnostic est cohérent
   - 8 vérifications indépendantes
   - Résultat : note de 0 à 10 + accord/désaccord
   ↓
7. INTERFACE (interface/main.py + dashboard.html)
   - Affiche le résultat sur un dashboard 3D
   - Envoie des emails si alerte critique
   - Permet de rejouer les données en accéléré
```

### 2.3 Chaque étape en détail

**Étape 2 - Ingestion** :
- Lit le fichier Excel
- Détecte les capteurs qui ne fonctionnent pas (gelé, saturé, hors plage)
- Classe chaque heure en RUNNING (marche), STOPPED (arrêt), TRANSIENT (transitoire)
- Ne comble JAMAIS les valeurs manquantes (NaN = information)

**Étape 3 - Features** :
- Calcule UA (coefficient d'échange) via la méthode efficacité-NTU
- Calcule 11 variables physiques qui résument le comportement
- Apprend ce qui est "normal" sur les 40% premières heures de marche

**Étape 4 - Détection** :
- 6 règles basées sur la physique (seuils)
- Isolation Forest qui trouve les anomalies par le ML
- Fusion des deux approches

**Étape 5 - Diagnostic** :
- Traduit les constatations en "L'encrassement du faisceau progresse"
- Rattache au mode AMDEC correspondant
- Propose "Mesure des épaisseurs sous 24h"

**Étape 6 - Contrôle** :
- Vérifie : les valeurs citées sont-elles exactes ?
- Vérifie : la sévérité correspond-elle aux faits ?
- Vérifie : l'action est-elle exécutable ?
- Note finale ≥ 6/10 = accord

**Étape 7 - Interface** :
- Dashboard 3D interactif
- Timeline des anomalies
- Registre d'alarmes
- Rejeu accéléré

---

## PARTIE 3 — L'architecture du code (2h)

### 3.1 La structure des dossiers

```
core/                    ← TOUTE la logique métier
├── config.py            ← Variables de configuration
├── pipeline.py          ← Orchestrateur (point d'entrée)
├── formatting.py        ← Formatage nombres français
├── detection/           ← Détection d'anomalies
│   ├── detector.py      ← Règles + Isolation Forest
│   ├── detection_agent.py ← Diagnostic
│   └── schemas.py       ← Schémas de données
├── verification/        ← Contrôle de cohérence
│   └── judge_agent.py   ← 8 vérifications
├── knowledge/           ← Données de référence
│   ├── knowledge.py     ← Accès aux données
│   ├── amdec.yaml       ← AMDEC
│   ├── tags.yaml        ← Capteurs
│   └── topology.yaml    ← Topologie physique
├── features/            ← Calcul des variables
│   ├── thermal.py       ← Calcul UA
│   └── e7301_features.py ← 11 features
├── ingestion/           ← Chargement données
│   └── dcs_loader.py    ← Lecture Excel
├── analytics/           ← Indicateurs
│   └── kpi.py           ← KPI opérationnels
└── alerts/              ← Alertes
    ├── email.py         ← Notifications
    ├── alarms.py        ← Registre alarmes
    └── workflows.py     ← Templates interventions

interface/               ← Dashboard web
├── main.py              ← Serveur FastAPI
├── dashboard.html       ← Page HTML
└── static/              ← JS, CSS, images

replay/                  ← Rejeu temps réel
└── replay.py            ← Simulation du flux

tests/                   ← Tests unitaires
data/                    ← Données DCS
docs/                    ← Documentation
```

### 3.2 Les fichiers clés

| Fichier | Rôle | Taille |
|---------|------|--------|
| `core/pipeline.py` | Orchestrateur principal | 248 l. |
| `core/detection/detector.py` | Moteur de détection | 821 l. |
| `core/detection/detection_agent.py` | Diagnostic | 515 l. |
| `core/verification/judge_agent.py` | Contrôle | 754 l. |
| `core/features/thermal.py` | Calcul UA | 435 l. |
| `core/features/e7301_features.py` | 11 features | 815 l. |
| `core/ingestion/dcs_loader.py` | Chargement données | 617 l. |
| `core/knowledge/knowledge.py` | Connaissance métier | 478 l. |

### 3.3 Le point d'entrée

**Fichier** : `core/pipeline.py`

```python
from core.pipeline import E7301Pipeline

# Crée et entraîne toute la chaîne
pipeline = E7301Pipeline()

# Analyse un instant précis
analysis = pipeline.analyze_at("2024-10-25T21:00:00")

# Résultat
print(analysis.detection.severity)  # WARNING, CRITICAL, etc.
print(analysis.decision.diagnosis)  # Le diagnostic
print(analysis.verdict.global_score)  # Note du Judge
```

---

## PARTIE 4 — Lancer le projet (2h)

### 4.1 Installation

```bash
pip install -r requirements.txt
```

### 4.2 Démarrage

```bash
python -m interface
```

### 4.3 Connexion

Ouvre http://localhost:8000

**Identifiants** :
- Email : `mounirsanbouli@gmail.com`
- Mot de passe : `123`

### 4.4 Explorer l'interface

**Onglet Salle** :
- Le modèle 3D du refroidisseur
- La timeline avec les épisodes d'anomalie
- Les signaux (UA, températures, débits)
- Le diagnostic courant

**Onglet Intégrité** :
- Les KPIs (disponibilité, épisodes/mois)
- Le registre d'alarmes
- L'AMDEC complète
- Les workflows d'intervention

**Onglet Contrôle** :
- Les 8 vérifications du Judge
- Le taux de signalement
- La couverture AMDEC
- Les angles morts

### 4.5 Lancer le rejeu

1. Sélectionne "5 jours/s" dans la vitesse
2. Clique sur "Rejouer"
3. Observe les analyses qui défilent
4. Observe les alertes qui apparaissent
5. Arrête le rejeu

---

## PARTIE 5 — Concepts clés à retenir

### 5.1 Les 3 idées fondatrices

1. **L'indicateur évident était faux** — Le résidu de puissance thermique semblait mesurer l'encrassement. Il est **circulaire** : il redit l'écart de consigne.

2. **Le vrai indicateur (UA) exige une donnée absente** — La température d'eau de mer n'est pas mesurée. Elle vient de la **climatologie de Safi**.

3. **Le système déclare ce qu'il ne voit pas** — 30,2% du risque AMDEC est couvert par les données ; le reste relève du plan préventif.

### 5.2 Le vocabulaire essential

| Terme | Définition |
|-------|------------|
| **DCS** | Distributed Control System — système de contrôle de l'usine |
| **UA** | Coefficient d'échange global — mesure les performances |
| **AMDEC** | Analyse des Modes de Défaillance — base de connaissances |
| **Feature** | Variable calculée à partir des données brutes |
| **Isolation Forest** — Algorithme de ML qui détecte les anomalies |
| **Règle** | Condition simple (seuil) qui détecte une anomalie |
| **Judge** | Contrôleur qui vérifie la cohérence du diagnostic |
| **Safety cap** | Plafond non compensable pour erreurs graves |

---

## Questions du jury pour J1

**Faciles :**
1. "Quel est le sujet de votre projet ?"
2. "Quel équipement surveillez-vous ?"
3. "Quel est le problème industriel ?"
4. "Comment s'appelle votre système ?"

**Techniques :**
5. "Pourquoi ne pas simplement surveiller les températures ?"
6. "Quelle est la différence entre une anomalie et une panne ?"
7. "Combien de temps de données utilisez-vous ?"

---

## Test de fin de journée

Réponds à ces 3 questions avec tes propres mots :

1. **Quel est le problème ?** (2-3 phrases)
2. **Comment ton système le résout-il ?** (3-4 phrases)
3. **Quels sont les 7 étapes du flux de données ?** (liste)

Si tu peux répondre à ces 3 questions sans regarder le document, tu as compris J1.
