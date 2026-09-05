# JOUR 4 — Physique du refroidisseur et calcul de UA

## Objectif du jour

À la fin de cette journée, tu dois être capable de :
- Expliquer le transfert thermique dans un échangeur
- Comprendre la méthode efficacité-NTU
- Expliquer pourquoi on calcule UA
- Comprendre le rôle de la climatologie de Safi
- Expliquer ce qu'est un résidu et ce qu'il signifie

---

## PARTIE 1 — Le transfert thermique (2h)

### 1.1 Les grandeurs fondamentales

**Fichier** : `core/features/thermal.py`

Dans un échangeur thermique, on a :
- **Q** = puissance thermique transférée (kW) — combien de chaleur passe
- **U** = coefficient d'échange global (kW/m²·K) — combien la paroi laisse passer
- **A** = surface d'échange (m²) — la surface de contact
- **ΔT** = différence de température — le "moteur" du transfert

**Relation** : Q = U × A × ΔT

### 1.2 UA : l'indicateur clé

**UA = U × A** est la **capacité thermique totale** de l'échangeur.

C'est le produit de :
- U (efficacité de la paroi) × A (surface disponible)

**Interprétation** :
- UA élevé = bon échange thermique = refroidisseur performant
- UA faible = mauvais échange = encrassement probable

### 1.3 Pourquoi ne peut-on pas mesurer UA directement ?

Pour calculer UA, il faudrait connaître :
- T_acide_in (mesurée ✓)
- T_acide_out (mesurée ✓)
- T_eau_de_mer (PAS mesurée ✗)
- Débit acide (mesuré ✓)

**Problème** : T_eau_de_mer n'est pas dans le DCS.

### 1.4 La solution : efficacité-NTU

**Fichier** : `core/features/thermal.py`

Quand le débit d'eau de mer est **très supérieur** au débit acide (c'est notre cas), le côté froid est **quasi-isotherme**. On peut utiliser une méthode simplifiée :

```
ε = (T_in - T_out) / (T_in - T_sea)    # efficacité
NTU = -ln(1 - ε)                         # nombre d'unités de transfert
UA = C_acide × NTU                       # coefficient d'échange
```

Où :
- **ε** (epsilon) = efficacité de l'échangeur (0 à 1)
- **NTU** = Number of Transfer Units (nombre d'unités de transfert)
- **C_acide** = capacité thermique du débit d'acide

### 1.5 Exemple concret

Données :
- T_in = 94°C (entrée acide)
- T_out = 66°C (sortie acide)
- T_sea = 19°C (eau de mer)
- C_acide = 1800 kJ/(h·K)

Calcul :
```
ε = (94 - 66) / (94 - 19) = 28/75 = 0.373
NTU = -ln(1 - 0.373) = -ln(0.627) = 0.467
UA = 1800 × 0.467 = 840 kW/K
```

---

## PARTIE 2 — La climatologie de Safi (1h)

### 2.1 Le problème

La température d'eau de mer n'est pas mesurée dans le DCS. Mais on en a besoin pour calculer UA.

### 2.2 La solution

**Fichier** : `core/features/thermal.py` → constante `SEAWATER_MONTHLY_C`

On utilise les **moyennes mensuelles historiques** de la température de surface de la mer à Safi :

```python
SEAWATER_MONTHLY_C = {
    1: 17.5,   # Janvier
    2: 17.0,   # Février
    3: 17.2,   # Mars
    4: 17.8,   # Avril
    5: 18.6,   # Mai
    6: 19.6,   # Juin
    7: 20.6,   # Juillet
    8: 21.6,   # Août
    9: 22.0,   # Septembre (maximum)
    10: 21.2,  # Octobre
    11: 19.8,  # Novembre
    12: 18.4,  # Décembre
}
```

### 2.3 Pourquoi Safi ?

Safi est le port côtier du Maroc, influenced by :
- Le **courant des Canaries** (froid)
- L'**upwelling côtier** (remontée d'eau froide des profondeurs)

La température varie de 17°C (hiver) à 22°C (été).

### 2.4 C'est la seule entrée extérieure

C'est important : la climatologie est la **seule donnée qui ne vient pas du DCS**. Tout le reste est mesuré sur place. C'est ce qui donne de la valeur au système : il intègre une connaissance extérieure au procédé.

---

## PARTIE 3 — La référence thermique (2h)

### 3.1 Pourquoi une référence ?

Pour détecter une dégradation, il faut comparer le UA **mesuré** au UA **attendu** (sans encrassement).

**Résidu** = UA_mesuré - UA_attendu

- Résidu = 0 → pas d'encrassement
- Résidu < 0 → encrassement probable
- Résidu > 0 → meilleures performances que la référence

### 3.2 Comment calcule-t-on UA_attendu ?

**Fichier** : `core/features/thermal.py` → classe `ConductanceReference`

On apprend la relation entre UA et les conditions de fonctionnement pendant la **période de référence** (les 40% premières heures de marche établie).

**Modèle** :
```
UA_attendu = a × F_acide^0.8 + b × T_acide_moyenne + c × T_eau_de_mer + d
```

Où :
- F_acide^0.8 : exposant de Dittus-Boelter (physique de la convection forcée)
- T_acide_moyenne : température moyenne de l'acide
- T_eau_de_mer : température d'eau de mer (climatologie)
- a, b, c, d : coefficients appris par régression linéaire

### 3.3 La période de référence

**Fichier** : `core/features/thermal.py` → `reference_cutoff()`

**Constante** : `REFERENCE_FRACTION = 0.40`

On prend les **40% premières heures de marche établie** comme période "saine" pour apprendre le comportement normal.

**Pourquoi 40% ?** C'est un compromis :
- Trop peu → pas assez de données pour apprendre
- Trop long → on inclut des périodes déjà dégradées

### 3.4 Le résidu

**Fichier** : `core/features/thermal.py` → `add_conductance_features()`

```
ua_residual = UA_mesuré - UA_attendu
ua_residual_z = ua_residual / σ_résidu   (standardisé en z-score)
```

**Interprétation** :
- ua_residual_z = 0 → UA est normal
- ua_residual_z = -2 → UA est 2 écarts-types en dessous de la normale
- ua_residual_z ≤ -1.5 pendant 72h → **alerte encrassement**

### 3.5 La résistance d'encrassement

```
Rf = 1/UA - 1/UA_attendu   (K/kW)
```

C'est la résistance thermique ajoutée par l'encrassement. Plus Rf est grand, plus l'encrassement est sévère.

---

## PARTIE 4 — Manipulation (2h)

### 4.1 Calculer la température d'eau de mer

**Exécute :**
```bash
python -c "
from core.features.thermal import seawater_temperature
import pandas as pd

index = pd.date_range('2024-01-01', periods=12, freq='MS')
temps = seawater_temperature(index)
print('=== Température eau de mer à Safi ===')
for m, t in zip(range(1, 13), temps):
    print(f'  Mois {m:2d} : {t:.1f}°C')
"
```

### 4.2 Calculer UA manuellement

**Exercice** : avec ces valeurs, calcule UA :
- T_in = 94°C
- T_out = 66°C
- T_sea = 19°C
- C_acide = 1800 kJ/(h·K)

**Solution** :
```
ε = (94 - 66) / (94 - 19) = 28/75 = 0.373
NTU = -ln(1 - 0.373) = 0.467
UA = 1800 × 0.467 = 840 kW/K
```

### 4.3 Explorer le calcul de UA dans le projet

**Exécute :**
```bash
python -c "
from core.features.thermal import overall_conductance
import numpy as np

# Données d'un instant
t_in = 94.0    # °C
t_out = 66.0   # °C
t_sea = 19.0   # °C
c_acid = 1800  # kJ/(h·K)

ua = overall_conductance(
    np.array([t_in]),
    np.array([t_out]),
    np.array([c_acid]),
    np.array([t_sea])
)
print(f'UA calculé : {ua[0]:.1f} kW/K')
"
```

---

## Ce que je dois retenir

1. UA = capacité thermique = U × A
2. Efficacité-NTU : ε = (T_in - T_out)/(T_in - T_sea), NTU = -ln(1-ε), UA = C × NTU
3. T_SEAWATER vient de la climatologie de Safi (17-22°C)
4. Période de référence = 40% premières heures RUNNING
5. Résidu UA < 0 persistant → encrassement probable
6. Résistance d'encrassement Rf = 1/UA - 1/UA_attendu

---

## Questions du jury

**Faciles :**
1. "Qu'est-ce que UA ?"
2. "Pourquoi la température d'eau de mer est-elle importante ?"
3. "Comment calculez-vous UA ?"

**Techniques :**
4. "Pourquoi efficacité-NTU et pas LMTD ?"
5. "Qu'est-ce que la résistance d'encrassement ?"
6. "Comment calculez-vous la période de référence ?"
7. "Que signifie un résidu UA négatif ?"

**Pièges :**
8. "La climatologie de Safi est-elle précise ?"
9. "Que se passe-t-il si T_SEAWATER réelle diffère de la climatologie ?"
10. "Pourquoi ne pas mesurer T_SEAWATER ?"
11. "Pourquoi 40% et pas 50% pour la référence ?"

---

## Test de fin de journée

1. **Calcule UA** pour : T_in=92°C, T_out=68°C, T_sea=20°C, C=1900 kJ/(h·K)
2. **Explique** pourquoi on utilise la climatologie de Safi
3. **Explique** ce qu'est un résidu UA et ce qu'il signifie
4. **Pourquoi** la période de référence est de 40% ?
