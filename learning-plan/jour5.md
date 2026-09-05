# JOUR 5 — Features et statistiques

## Objectif du jour

À la fin de cette journée, tu dois être capable de :
- Connaître les 11 features du modèle et leur signification
- Comprendre le z-score et son interprétation
- Expliquer pourquoi certaines features sont redondantes
- Comprendre les références linéaires

---

## PARTIE 1 — Qu'est-ce qu'une feature ? (1h)

### 1.1 Définition

Une **feature** (ou variable) est une valeur calculée à partir des données brutes qui résume un aspect du comportement du système.

**Exemple simple** : si tu as T_acide_in = 94°C et T_acide_out = 66°C, la feature "delta_t" = 94 - 66 = 28°C.

### 1.2 Pourquoi calculer des features ?

Les données brutes (12 capteurs) ne suffisent pas pour détecter les anomalies. Il faut des variables qui résument le comportement.

**Exemple** : la température de sortie à elle seule ne dit pas si c'est normal. Mais si on sait que UA est inférieur de 2 écarts-types à sa valeur attendue, c'est un signal fort d'encrassement.

---

## PARTIE 2 — Les 11 features du modèle (3h)

### 2.1 La liste complète

**Fichier** : `core/features/e7301_features.py` → constante `MODEL_FEATURES`

| # | Nom | Signification | Utilité |
|---|-----|---------------|---------|
| 1 | `ua_residual_z` | Écart du coefficient d'échange en sigma | **Diagnostic** encrassement |
| 2 | `regulation_effort_z` | Effort de régulation en sigma | Conduite (**redondant !**) |
| 3 | `t_in_residual_z` | Résidu température d'entrée | Contexte amont |
| 4 | `conc_min` | Titre acide minimal (2 analyseurs) | Qualité acide |
| 5 | `conc_bias_drift_z` | Dérive entre les 2 analyseurs | Défaut capteur |
| 6 | `conc_drop_24h` | Chute de titre en 24h | Fuite possible |
| 7 | `flow_per_load` | Débit rapporté à la charge | Circulation |
| 8 | `d_t_out` | Variation horaire sortie acide | Dynamique |
| 9 | `d_conc` | Variation horaire titre | Dynamique |
| 10 | `t_out_local_z` | Sortie acide vs ses 24h | Comportement récent |
| 11 | `t_in_local_z` | Entrée acide vs ses 24h | Comportement récent |

### 2.2 Détail de chaque feature

**Feature 1 : ua_residual_z** (LA PLUS IMPORTANTE)

- **Signification** : écart du coefficient d'échange par rapport à la référence
- **Calcul** : (UA_mesuré - UA_attendu) / σ_résidu
- **Utilité** : détecte l'encrassement
- **Comportement normal** : autour de 0
- **Comportement anormal** : persistant < -1.5 pendant 72h

**Feature 2 : regulation_effort_z**

- **Signification** : effort de la boucle de régulation
- **Calcul** : (duty_mesuré - duty_attendu) / σ_résidu
- **Problème** : corrélé à -0.94 avec l'écart de consigne → **redondant**
- **Rôle** : mesure la conduite, pas l'encrassement

**Feature 3 : t_in_residual_z**

- **Signification** : écart de la température d'entrée par rapport à la référence
- **Utilité** : contexte amont (ce qui entre dans l'échangeur)
- **Indépendant** : corrélation < 0.30 avec les autres

**Features 4-6 : Titre acide**

- `conc_min` : le plus bas des 2 analyseurs
- `conc_bias_drift_z` : dérive entre les 2 analyseurs
- `conc_drop_24h` : chute en 24h (fuite possible)

**Features 7-9 : Dynamique**

- `flow_per_load` : débit rapporté à la charge
- `d_t_out` : variation horaire de la sortie
- `d_conc` : variation horaire du titre

**Features 10-11 : Comportement récent**

- `t_out_local_z` : sortie vs ses 24 dernières heures
- `t_in_local_z` : entrée vs ses 24 dernières heures

---

## PARTIE 3 — Le z-score (1h)

### 3.1 Définition

Le **z-score** (ou score standardisé) mesure combien une valeur est éloignée de la moyenne, en unités d'écart-type.

```
z = (valeur - moyenne) / écart_type
```

### 3.2 Interprétation

| z-score | Signification |
|---------|---------------|
| z = 0 | Valeur normale (à la moyenne) |
| z = +1 | 1 écart-type au-dessus |
| z = +2 | 2 écart-types au-dessus → inhabituel |
| z = +3 | 3 écart-types au-dessus → très inhabituel |
| z = -1 | 1 écart-type en dessous |
| z = -2 | 2 écart-types en dessous → inhabituel |
| z = -3 | 3 écart-types en dessous → très inhabituel |

### 3.3 Application dans le projet

**Exemple** : `ua_residual_z = -2.5`

Ça veut dire : "le UA mesuré est 2.5 écarts-types en dessous de ce qu'on attendrait". C'est un signal fort d'encrassement.

### 3.4 Pourquoi le z-score ?

Le z-score permet de comparer des grandeurs qui ont des unités différentes :
- UA est en kW/K
- La température est en °C
- Le débit est en m³/h

En z-score, tout est sur la même échelle : "combien d'écarts-types par rapport à la normale".

---

## PARTIE 4 — Les références linéaires (2h)

### 4.1 Le concept

Une **référence linéaire** est un modèle simple qui prédit la valeur attendue d'une grandeur en fonction des conditions.

**Exemple** : UA_attendu = f(F_acide, T_acide, T_eau_de_mer)

On apprend cette relation sur la période de référence (40% premières heures RUNNING), puis on la compare aux mesures réelles.

### 4.2 Les 3 références du projet

**Fichier** : `core/features/e7301_features.py`

| Référence | Cible | Régresseurs | Rôle |
|-----------|-------|-------------|------|
| `ConductanceReference` | UA | F^0.8, T_mean, T_sea, 1 | **Diagnostic** encrassement |
| `RegulationEffortReference` | duty | LOAD, F, T_in, conc, F×T_in, 1 | **Conduite** |
| `InletReference` | T_in | LOAD, F, LOAD×F, 1 | **Contexte** amont |

### 4.3 Pourquoi F^0.8 ?

C'est l'**exposant de Dittus-Boelter** en mécanique des fluides. Il relie le coefficient d'échange au débit :
```
h ∝ Re^0.8 ∝ F^0.8
```

C'est une relation physique connue, pas un choix arbitraire.

### 4.4 La leçon critique : regulation_effort_z est faux

**Fichier** : `core/features/e7301_features.py`

`regulation_effort_z` est **algébriquement circulaire** : il vaut `-écart_de_consigne` changé de signe.

**Corrélation mesurée** : r = -0.94 avec `control_deviation`

**Conséquence** : cette feature ne mesure pas l'encrassement, elle redit la consigne. C'est `ua_residual_z` qui porte le vrai diagnostic.

---

## PARTIE 5 — Manipulation (2h)

### 5.1 Lister les features

**Exécute :**
```bash
python -c "
from core.features.e7301_features import MODEL_FEATURES
print('=== Les 11 features du modèle ===')
for i, f in enumerate(MODEL_FEATURES, 1):
    print(f'  {i:2d}. {f}')
"
```

### 5.2 Voir les constantes physiques

**Exécute :**
```bash
python -c "
from core.features.e7301_features import RHO_A, RHO_B, CP_A, CP_B
print('=== Constantes physiques H2SO4 98% ===')
print(f'Densité : ρ(T) = {RHO_A} + {RHO_B}×T kg/m³')
print(f'Capacité : cp(T) = {CP_A} + {CP_B}×T kJ/(kg·K)')
"
```

---

## Ce que je dois retenir

1. 11 features physiques pour le modèle
2. ua_residual_z est LA feature la plus importante
3. regulation_effort_z est redondant (r = -0.94)
4. z-score = (valeur - moyenne) / écart-type
5. 3 références linéaires partagent la même période de référence
6. Les moyennes glissantes 14 jours n'entrent PAS dans le modèle

---

## Questions du jury

**Faciles :**
1. "Quelles sont vos features ?"
2. "Pourquoi 11 features et pas plus ?"
3. "Que signifie un z-score ?"

**Techniques :**
4. "Pourquoi F^0.8 dans le modèle de référence ?"
5. "Comment savez-vous que regulation_effort_z est redondant ?"
6. "Pourquoi les moyennes glissantes n'entrent pas dans le modèle ?"

**Pièges :**
7. "Pourquoi ne pas supprimer regulation_effort_z du modèle ?"
8. "Quelle est la période de référence et pourquoi 40% ?"
9. "Que se passe-t-il si la période de référence n'est pas représentative ?"

---

## Test de fin de journée

1. **Explique** pourquoi `ua_residual_z` est la feature la plus importante
2. **Calcule** le z-score pour : valeur=65, moyenne=66, écart_type=0.5
3. **Explique** pourquoi `regulation_effort_z` est redondant
4. **Cite** les 3 références linéaires et leur rôle
