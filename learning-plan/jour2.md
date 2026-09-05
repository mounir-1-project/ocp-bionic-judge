# JOUR 2 — Le refroidisseur industriel et les données DCS

## Objectif du jour

À la fin de cette journée, tu dois être capable de :
- Expliquer comment fonctionne un échangeur thermique
- Connaître les 12 capteurs et leur rôle
- Comprendre le format des données DCS
- Expliquer la classification état process (RUNNING/STOPPED/TRANSIENT)

---

## PARTIE 1 — Le refroidisseur industriel (3h)

### 1.1 C'est quoi un échangeur thermique ?

Un **échangeur thermique** est un appareil qui transfère la chaleur d'un fluide chaud vers un fluide froid, SANS les mélanger.

**Analogie simple** : imagine un tuyau d'eau chaude plongé dans une bassine d'eau froide. La chaleur passe à travers la paroi du tuyau.

### 1.2 Notre refroidisseur E7301

**Fichiers** :
- `docs/1- Fiche équipement REFROIDISSEUR DE SECHAGE PSIII.xls`
- `core/knowledge/topology.yaml`

**Caractéristiques** :
- **Type** : Faisceau tubulaire
- **Fabricant** : Chemetics
- **Site** : Atelier sulfurique PS III, Maroc Chimie, Safi
- **Taille** : calandre Ø 1118 mm, tubes 9754 mm
- **Nombre de tubes** : 1541
- **Matériau des tubes** : Acier 904L (résistant à l'acide)

### 1.3 Le circuit d'acide

```
Acide à 94°C → [CALANDRE] → Acide à 66°C
                  ↕ transfert thermique
Eau de mer à 19°C → [TUBES] → Eau de mer à 22°C
```

- **Côté calandre** (gros tube) : acide sulfurique à 98%, chaud
- **Côté tubes** (1541 petits tubes) : eau de mer, froide
- La chaleur passe de l'acide vers l'eau de mer à travers la paroi des tubes

### 1.4 Le transfert thermique

La quantité de chaleur transférée Q est donnée par :

```
Q = U × A × ΔT_lm
```

Où :
- **Q** = puissance thermique transférée (kW)
- **U** = coefficient d'échange global (kW/m²·K)
- **A** = surface d'échange (m²) — constante pour un équipement donné
- **ΔT_lm** = différence de température moyenne logarithmique

**UA = U × A** est la **capacité thermique totale** de l'échangeur.

**Quand UA baisse** = l'échangeur fonctionne moins bien = probable encrassement.

### 1.5 Le problème de l'encrassement

Quand des dépôts s'accumulent sur les parois des tubes :
- La résistance thermique augmente
- UA diminue
- L'acide sort plus chaud
- Les performances se dégradent

**Objectif** : détecter cette dégradation de UA avant qu'elle ne devienne critique.

### 1.6 Les capteurs

**Fichier** : `core/knowledge/tags.yaml`

Le refroidisseur est équipé de 12 capteurs qui mesurent en continu :

| # | Alias | Ce qu'il mesure | Unité | Pourquoi c'est important |
|---|-------|----------------|-------|--------------------------|
| 1 | T_ACID_IN | Température entrée acide | °C | Performance de l'échangeur |
| 2 | T_ACID_OUT | Température sortie acide | °C | **Performance** — celle qu'on veut à 66°C |
| 3 | F_ACID | Débit acide | m³/h | Conditions de fonctionnement |
| 4 | LOAD_SULFUR | Charge soufre | t/h | Charge de l'installation |
| 5 | C_ACID_1100 | Titre acide (analyseur 1) | % | Qualité de l'acide |
| 6 | C_ACID_1200 | Titre acide (analyseur 2) | % | Redondance avec le précédent |
| 7 | T_CIRC_1300 | Température circulation | °C | Contexte |
| 8 | F_3412 | Débit eau de mer | m³/h | Conditions du côté froid |
| 9 | A_3301 | Absorption 1 | - | Contexte absorption |
| 10 | A_3302 | Absorption 2 | - | Contexte absorption |
| 11 | T_SEAWATER | Température eau de mer | °C | **Pas mesurée** — climatologie |
| 12 | TI_5303 | Capteur dégradé | °C | Instrumentation défectueuse |

**Point important** : T_SEAWATER n'est PAS mesurée dans le DCS. Elle vient de la **climatologie de Safi** (moyennes mensuelles historiques).

### 1.7 Le rôle de chaque catégorie de capteurs

**Capteurs de performance** (ceux qui mesurent si l'échangeur marche bien) :
- T_ACID_IN, T_ACID_OUT, F_ACID

**Capteurs de contexte** (ceux qui donnent les conditions de fonctionnement) :
- LOAD_SULFUR, T_CIRC_1300, F_3412, A_3301, A_3302

**Capteurs de qualité** (ceux qui mesurent la qualité de l'acide) :
- C_ACID_1100, C_ACID_1200

**Capteur dégradé** (qui ne fonctionne pas bien) :
- TI_5303 (47,8% de disponibilité)

---

## PARTIE 2 — Les données DCS (2h)

### 2.1 Qu'est-ce qu'un fichier DCS ?

Le DCS (Distributed Control System) est le système de contrôle automatique de l'usine. Il enregistre toutes les mesures en continu.

**Fichier** : `data/raw/DATA.xlsx`

**Contenu** :
- **10 180 lignes** = 10 180 heures de fonctionnement
- **14 mois** : janvier 2024 → février 2025
- **12 colonnes** = 12 capteurs
- **Pas** : 1 mesure par heure

### 2.2 Le format des données

Chaque ligne du fichier Excel représente **une heure** de fonctionnement.

Exemple :
```
Timestamp          | T_ACID_IN | T_ACID_OUT | F_ACID | C_ACID_1100 | ...
2024-01-01 07:00   | 94.2      | 66.1       | 56.4   | 98.7        | ...
2024-01-01 08:00   | 94.5      | 66.0       | 55.8   | 98.6        | ...
```

### 2.3 Les valeurs spéciales

Dans le DCS, les mesures peuvent être :
- **Un nombre** : la valeur mesurée (ex: 94.2)
- **Un texte** : un code qualité (ex: "Bad", "I/O Timeout", "Configure")
- **Vide** : pas de mesure

### 2.4 La qualité des données

**Fichier** : `core/ingestion/dcs_loader.py`

Chaque mesure peut porter un **code qualité** :
- **Bad** : mesure invalide
- **I/O Timeout** : timeout de communication
- **Configure** : capteur en configuration
- **Frozen** : signal constant (gelé)

**Règle du projet** : une mesure invalide = `NaN` (Not a Number). **Aucune imputation**.

### 2.5 Pourquoi pas d'imputation ?

Imputer = remplacer une valeur manquante par une valeur calculée (moyenne, interpolation, etc.).

**Problème** : si on impute, on masque les problèmes de capteurs. Un capteur qui renvoie "Bad" est une information importante : ça veut dire qu'on ne peut pas faire confiance à ce capteur.

**Notre politique** : NaN = information de qualité. On garde le NaN pour que le système sache qu'il manque des données.

---

## PARTIE 3 — Classification état process (1h)

### 3.1 Pourquoi classifier l'état ?

Un refroidisseur à l'arrêt ne peut pas être évalué sur ses performances. Il faut savoir si la ligne est en marche avant de calculer UA.

**Fichier** : `core/ingestion/dcs_loader.py` → fonction `classify_process_state`

### 3.2 Les 3 états

| État | Définition | Quand | Conséquence |
|------|-----------|-------|-------------|
| **RUNNING** | Marche établie | La ligne produit normalement | Surveillance active, calcul UA valide |
| **TRANSIENT** | Arrêt ou démarrage | La ligne change d'état | Suspension temporaire |
| **STOPPED** | Arrêt complet | La ligne ne tourne pas | Aucun diagnostic possible |

### 3.3 Les critères de classification

**Fichier** : `core/ingestion/dcs_loader.py`

| Critère | Seuil | État résultant |
|---------|-------|----------------|
| LOAD_SULFUR < 8.0 | Très faible | STOPPED |
| F_ACID < 20.0 | Débit quasi nul | STOPPED |
| T_ACID_IN < 60.0 | Température trop basse | STOPPED |
| Variation LOAD > 2/h | Changement rapide | TRANSIENT |
| État précédent = STOPPED | Venait de s'arrêter | TRANSIENT |

**Règle** : si une donnée est absente → classify STOPPED (ne pas deviner).

### 3.4 Pourquoi c'est important ?

- **UA ne peut être calculé que pendant RUNNING**
- Les heures STOPPED ne doivent pas polluer l'apprentissage
- Les heures TRANSIENT sont des zones d'incertitude

---

## PARTIE 4 — Manipulation (2h)

### 4.1 Explorer les capteurs

**Exécute :**
```bash
python -c "
from core.knowledge.knowledge import load_domain
d = load_domain()
print('=== Les 12 capteurs du refroidisseur E7301 ===')
print()
for t in d.tags.values():
    print(f'{t.alias:15s} | {t.label:40s} | {t.unit:5s} | role: {t.role}')
"
```

### 4.2 Explorer les seuils

**Exécute :**
```bash
python -c "
from core.knowledge.knowledge import load_domain
d = load_domain()
print('=== Seuils d alarme pour T_ACID_OUT ===')
tag = d.get('T_ACID_OUT')
print(f'  alarm_low     : {tag.threshold(\"alarm_low\")} °C')
print(f'  alarm_high    : {tag.threshold(\"alarm_high\")} °C')
print(f'  alarm_high_high: {tag.threshold(\"alarm_high_high\")} °C')
print(f'  setpoint      : {tag.setpoint} °C')
print(f'  plage normale : {tag.range_operating}')
"
```

### 4.3 Lancer le projet et observer

```bash
python -m interface
```

**Actions :**
1. Connecte-toi
2. Regarde l'onglet Salle : le modèle 3D, les signaux
3. Regarde l'onglet Intégrité : les KPIs, la disponibilité des capteurs
4. Note la disponibilité de TI_5303 (47,8%)

---

## Ce que je dois retenir

1. Le refroidisseur refroidit l'acide avec l'eau de mer
2. UA = U × A = capacité thermique = indicateur de performance
3. 12 capteurs : 3 de performance, 5 de contexte, 2 de qualité, 1 dégradé, 1 climatologie
4. T_SEAWATER n'est pas mesurée (climatologie de Safi)
5. 3 états : RUNNING (marche), STOPPED (arrêt), TRANSIENT (transitoire)
6. Aucune imputation des données manquantes

---

## Questions du jury

**Faciles :**
1. "Qu'est-ce qu'un échangeur thermique ?"
2. "Combien de capteurs utilisez-vous ?"
3. "Pourquoi la température d'eau de mer n'est-elle pas mesurée ?"

**Techniques :**
4. "Que se passe-t-il quand un capteur est en défaut ?"
5. "Quelle est la différence entre RUNNING et STOPPED ?"
6. "Pourquoi ne pas imputer les valeurs manquantes ?"

**Pièges :**
7. "Un NaN est-il une erreur ?" → Non, c'est une information de qualité
8. "Que se passe-t-il si on ignore les heures STOPPED ?" → On ne peut pas évaluer les performances

---

## Test de fin de journée

Réponds à ces questions :

1. **Explique le fonctionnement du refroidisseur** en 3 phrases
2. **Cite 5 capteurs** et leur rôle
3. **Pourquoi T_SEAWATER n'est-elle pas mesurée ?**
4. **Quelle est la différence entre RUNNING et STOPPED ?**
5. **Pourquoi ne pas imputer les valeurs manquantes ?**
