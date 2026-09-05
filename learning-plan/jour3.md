# JOUR 3 — Ingestion des données et qualité

## Objectif du jour

À la fin de cette journée, tu dois être capable de :
- Expliquer comment les données sont chargées depuis le fichier Excel
- Comprendre comment les défauts capteurs sont détectés
- Expliquer la politique "aucune imputation"
- Connaître les 5 sorties de l'ingestion

---

## PARTIE 1 — Le fichier de données (1h)

### 1.1 Le fichier DATA.xlsx

**Emplacement** : `data/raw/DATA.xlsx`

C'est le fichier contenant toutes les mesures DCS du refroidisseur sur 14 mois.

**Caractéristiques** :
- **Format** : Microsoft Excel (.xlsx)
- **Feuille** : "Feuil1" (nom par défaut)
- **Lignes** : 10 180 (une par heure)
- **Colonnes** : 12 capteurs + timestamp
- **Taille** : environ 1 Mo

### 1.2 Comment le lire ?

**Fichier** : `core/ingestion/dcs_loader.py` → fonction `read_raw`

```python
import pandas as pd

# Lecture brute
df = pd.read_excel("data/raw/DATA.xlsx", sheet_name="Feuil1")

# Résultat : un DataFrame avec
# - Les colonnes = aliases des capteurs (T_ACID_IN, T_ACID_OUT, etc.)
# - Les lignes = timestamps (une par heure)
# - Les valeurs = nombres OU textes (codes qualité)
```

**Point important** : le DCS peut mettre du texte dans une cellule numérique quand le capteur est en défaut. C'est pour ça qu'on lit en "object" (mélange nombres + texte).

---

## PARTIE 2 — Détection des défauts capteurs (2h)

### 2.1 Les types de défauts

**Fichier** : `core/ingestion/dcs_loader.py`

| Type de défaut | Comment on le détecte | Exemple | Conséquence |
|----------------|----------------------|---------|-------------|
| **Code qualité** | Texte dans la cellule ("Bad", "I/O Timeout") | Un capteur qui envoie un message d'erreur | Mesure → NaN |
| **Signal gelé** | La valeur reste identique pendant ≥ 6h (hors arrêt) | Un capteur bloqué sur 65.3°C | Mesure → NaN |
| **Saturation** | La valeur est collée à la butée physique | Un capteur à 327.67°C (butée) | Mesure → NaN |
| **Hors plage** | La valeur dépasse la plage physique du capteur | Une température négative sur un capteur 0-200°C | Mesure → NaN |

### 2.2 Comment détecte-t-on un capteur gelé ?

**Fichier** : `core/ingestion/dcs_loader.py` → `_detect_frozen`

**Principe** : si la valeur reste identique pendant au moins 6 heures consécutives (hors arrêt), le capteur est probablement gelé.

**Constante** : `FROZEN_MIN_HOURS = 6`

**Exemple** :
```
Heure 100: 65.3°C
Heure 101: 65.3°C
Heure 102: 65.3°C
...
Heure 105: 65.3°C  ← 6 heures identiques = GELÉ
```

**Pourquoi 6 heures ?** Un capteur peut avoir des variations normales sur quelques minutes. 6 heures sans variation最小 est un signal fort de gel.

### 2.3 Comment détecte-t-on la saturation ?

**Fichier** : `core/ingestion/dcs_loader.py` → `_detect_sensor_faults`

**Principe** : si la valeur est très proche de la butée physique du capteur, il est probablement saturé.

**Constante** : `SATURATION_REL_TOL = 1e-4`

**Exemple** : un capteur de température 0-200°C qui renvoie 199.99°C en continu est saturé.

### 2.4 Comment détecte-t-on les codes qualité ?

**Fichier** : `core/ingestion/dcs_loader.py` → `_detect_quality_codes`

Le DCS met des textes dans les cellules quand le capteur est en problème :
- "Bad" : mesure invalide
- "I/O Timeout" : timeout de communication
- "Configure" : capteur en configuration

On cherche ces textes dans chaque colonne et on met la mesure à NaN.

---

## PARTIE 3 — La politique d'imputation (1h)

### 3.1 Qu'est-ce que l'imputation ?

Imputer = remplacer une valeur manquante par une valeur calculée :
- Imputation par la moyenne
- Imputation par interpolation
- Imputation par le dernier point valide
- etc.

### 3.2 Pourquoi on n'impute PAS

**Fichier** : `core/ingestion/dcs_loader.py`

**Notre règle** : une mesure invalide = `NaN`. Aucune imputation.

**Raisons** :
1. Un NaN est une **information** : ça veut dire "ce capteur ne fonctionne pas à ce moment-là"
2. Imputer masquerait les problèmes de capteurs
3. Le système a besoin de savoir qu'il manque des données pour évaluer la fiabilité du diagnostic

**Conséquence** : les valeurs NaN se propagent dans le calcul des features et du modèle. Le système sait qu'il travaille avec des données incomplètes.

---

## PARTIE 4 — IngestionResult (1h)

### 4.1 Les 5 sorties

**Fichier** : `core/ingestion/dcs_loader.py` → dataclass `IngestionResult`

| Sortie | Type | Contenu | Utilité |
|--------|------|---------|---------|
| `readings` | DataFrame | Mesures nettoyées (NaN pour défauts) | Calcul des features |
| `observations` | DataFrame | Valeurs brutes DCS | Affichage dans l'interface |
| `quality` | DataFrame | Événements de qualité | Diagnostic des capteurs |
| `sensor_health` | DataFrame | Synthèse santé par capteur | KPI disponibilité |
| `report` | dict | Statistiques globales | Rapport d'ingestion |

### 4.2 Le rapport de santé des capteurs

**Fichier** : `core/ingestion/dcs_loader.py` → `_sensor_health()`

Pour chaque capteur, on calcule :
- **Disponibilité** : % de données valides (non-NaN)
- **Défauts** : nombre de défauts par type

**Exemple de sortie** :
```
Alias          | Disponibilité | Défauts
TI_5303        | 47.8%         | 5170 (gelés)
PHI_5306       | 85.4%         | 1344 (gelés)
C_ACID_1200    | 93.9%         | 103 (codes qualité) + 515 (gelés)
...
```

---

## PARTIE 5 — Le pipeline d'ingestion (1h)

### 5.1 Le flux complet

```
DATA.xlsx
    ↓
read_raw()                    → DataFrame brut (nombres + texte)
    ↓
_detect_quality_codes()        → Événements qualité (Bad, I/O Timeout...)
    ↓
_detect_sensor_faults()        → Événements (gel, saturation, hors plage)
    ↓
classify_process_state()       → Colonne process_state (RUNNING/STOPPED/TRANSIENT)
    ↓
ingest()                       → IngestionResult (5 sorties)
```

### 5.2 La fonction principale

**Fichier** : `core/ingestion/dcs_loader.py` → `ingest()`

```python
def ingest(path, domain, sheet="Feuil1"):
    # 1. Lecture brute
    raw = read_raw(path, sheet)
    
    # 2. Détection des défauts
    quality_events = _detect_quality_codes(raw, domain)
    sensor_events = _detect_sensor_faults(values, domain, eligible)
    
    # 3. Nettoyage : invalides → NaN
    readings = raw.copy()
    readings[invalid_mask] = np.nan
    
    # 4. Classification état process
    readings["process_state"] = classify_process_state(readings, domain)
    
    # 5. Rapport de santé
    sensor_health = _sensor_health(readings, quality_events, domain)
    
    return IngestionResult(readings, observations, quality, sensor_health, report)
```

---

## PARTIE 6 — Manipulation (2h)

### 6.1 Explorer l'ingestion

**Exécute :**
```bash
python -c "
from core.knowledge.knowledge import load_domain
from core.ingest.dcs_loader import ingest
from core.config import DCS_EXPORT

d = load_domain()
result = ingest(DCS_EXPORT, d)

print('=== Résultat de l ingestion ===')
print(f'Mesures: {len(result.readings)} lignes x {len(result.readings.columns)} colonnes')
print(f'Événements qualité: {len(result.quality)}')
print()
print('=== Santé des capteurs ===')
for _, row in result.sensor_health.iterrows():
    avail = row['availability_pct']
    status = 'OK' if avail >= 99 else 'DÉGRADÉ' if avail >= 80 else 'CRITIQUE'
    print(f'  {row[\"alias\"]:15s} | {avail:5.1f}% | {status}')
"
```

### 6.2 Voir les données brutes

**Exécute :**
```bash
python -c "
from core.ingest.dcs_loader import read_raw
from core.config import DCS_EXPORT

df = read_raw(DCS_EXPORT)
print('=== 5 premières lignes ===')
print(df.head())
print()
print('=== Types des colonnes ===')
print(df.dtypes)
"
```

### 6.3 Lancer et observer

```bash
python -m interface
```

**Actions :**
1. Ouvre l'onglet Intégrité
2. Regarde la section "Disponibilité des capteurs"
3. Note quel capteur a la pire disponibilité (TI_5303 à 47,8%)
4. Regarde le "Registre d'alarmes" — il se remplit pendant le rejeu

---

## Ce que je dois retenir

1. Le fichier DATA.xlsx contient 10 180 mesures (14 mois, 12 capteurs)
2. 4 types de défauts : code qualité, gel, saturation, hors plage
3. Aucune imputation — NaN = information de qualité
4. 5 sorties : readings, observations, quality, sensor_health, report
5. Classification : RUNNING / STOPPED / TRANSIENT

---

## Questions du jury

**Faciles :**
1. "Comment chargez-vous les données ?"
2. "Que faites-vous des valeurs manquantes ?"
3. "Combien de mesures utilisez-vous ?"

**Techniques :**
4. "Comment détectez-vous un capteur gelé ?"
5. "Que se passe-t-il avec TI_5303 (47,8%) ?"
6. "Quelle est la différence entre readings et observations ?"

**Pièges :**
7. "Si vous imputiez les valeurs, quel serait le risque ?"
8. "Un NaN est-il une erreur ?" → Non, c'est une information
9. "Pourquoi 6 heures pour le gel ?"

---

## Test de fin de journée

1. **Explique le parcours d'une mesure** depuis Excel jusqu'au DataFrame readings
2. **Cite 3 types de défauts** capteurs et comment on les détecte
3. **Pourquoi ne pas imputer** les valeurs manquantes ?
4. **Quelles sont les 5 sorties** de l'ingestion ?
