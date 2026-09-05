# JOUR 7 — Détection par règles et fusion

## Objectif du jour

À la fin de cette journée, tu dois être capable de :
- Expliquer pourquoi on utilise des règles en plus du ML
- Connaître les 6 règles déterministes
- Expliquer comment les règles et le ML sont combinés
- Comprendre la priorité des constatations

---

## PARTIE 1 — Pourquoi des règles ? (1h)

### 1.1 Le problème du ML seul

Le ML (Isolation Forest) détecte les anomalies, mais :
- Il ne peut pas expliquer **pourquoi** c'est anormal
- Il ne peut pas rattacher à un mode de défaillance
- Il ne peut pas proposer d'action corrective

### 1.2 L'avantage des règles

Les règles déterministes sont :
- **Basées sur la physique** : elles encodent des connaissances métier
- **Explicables** : on sait pourquoi l'alerte s'est déclenchée
- **Toujours disponibles** : ne dépendent pas de la qualité des données
- **Rattachées à l'AMDEC** : chaque règle pointe vers un mode de défaillance

### 1.3 La complémentarité

| Règle | ML |
|-------|-----|
| Explique **pourquoi** | Détecte **quoi** |
| Basée sur la physique | Basée sur les patterns |
| Toujours disponible | Dépend des données |
| Peut rater des combinaisons | Voit l'invisible |

**Conclusion** : les deux se complètent.

---

## PARTIE 2 — Les 6 règles (3h)

### 2.1 Vue d'ensemble

**Fichier** : `core/detection/detector.py` → classe `RuleEngine`

| # | Règle | Ce qu'elle vérifie | Seuils | Mode AMDEC |
|---|-------|-------------------|--------|------------|
| 1 | `SENSOR_FAULT` | Nombre de capteurs défaillants | ≥ 2 → WARNING | CAPTEUR_DEFAILLANT |
| 2 | `CONTROL_LOSS` | Température sortie acide | ≥ 68°C (H), ≥ 72°C (HH) | FAISCEAU_BOUCHAGE |
| 3 | `FOULING_DRIFT` | Dérive UA persistante | ≤ -1.5σ pendant 72h | FAISCEAU_BOUCHAGE |
| 4 | `CONC_LOW` | Titre acide | ≤ 98% (L), ≤ 97% (LL) | CORROSION / FUITE |
| 5 | `T_IN_HIGH` | Température entrée | ≥ 100°C (H), ≥ 105°C (HH) | FAISCEAU_CORROSION |
| 6 | `FLOW_LOW` | Débit acide | ≤ 35 m³/h (L), ≤ 20 (LL) | CALANDRE_FUITE |

### 2.2 Règle 1 : SENSOR_FAULT

**Fichier** : `core/detection/detector.py` → `_rule_sensor_health`

**Logique** : si au moins 2 capteurs sont en défaut, la base de mesure est dégradée.

```python
n_bad = nombre de capteurs défaillants
if n_bad >= 2:
    → WARNING (capteurs dégradés)
else if n_bad == 1:
    → INFO (un seul capteur en défaut)
```

**Pourquoi c'est important** : un diagnostic basé sur des données dégradées est moins fiable. Il faut le signaler.

### 2.3 Règle 2 : CONTROL_LOSS

**Fichier** : `core/detection/detector.py` → `_rule_control_loss`

**Logique** : si la température de sortie acide dépasse les seuils, l'échangeur ne tient plus sa consigne.

```python
if T_ACID_OUT >= 72°C (HH):
    → CRITICAL (perte de contrôle totale)
elif T_ACID_OUT >= 68°C (H):
    → WARNING (début de perte de contrôle)
```

**Mode AMDEC** : FAISCEAU_BOUCHAGE (l'encrassement empêche le refroidissement)

### 2.4 Règle 3 : FOULING_DRIFT

**Fichier** : `core/detection/detector.py` → `_rule_thermal_drift`

**C'est la règle la plus importante pour l'encrassement.**

**Logique** : si le UA residual trend est négatif de façon **persistante** (72h), c'est un signe d'encrassement.

```python
ua_z = ua_residual_trend_14d
fenetre = historique[72_dernières_heures]
persistent = (fenetre <= -1.5).mean() > 0.8

if ua_z <= -1.5 and persistent:
    → WARNING (FOULING_DRIFT)
```

**Constantes** :
- `DRIFT_PERSISTENCE_H = 72` (heures de persistance)
- `DRIFT_Z_THRESHOLD = 1.5` (seuil z-score)

**Pourquoi 72h ?** L'encrassement est un phénomène lent. Une dérive ponctuelle peut être un artefact. 72h confirme la tendance.

### 2.5 Règle 4 : CONC_LOW

**Fichier** : `core/detection/detector.py` → `_rule_concentration`

**Logique** : si le titre acide chute, ça peut indiquer une fuite d'eau de mer dans l'acide.

```python
if conc <= 97% (LL):
    → CRITICAL (FAISCEAU_FUITE — dilution majeure)
elif conc <= 98% (L):
    → WARNING (FAISCEAU_CORROSION — conditions corrosives)
```

### 2.6 Règle 5 : T_IN_HIGH

**Fichier** : `core/detection/detector.py` → `_rule_temperature_corrosion`

**Logique** : si la température d'entrée acide est trop élevée, ça accélère la corrosion.

```python
if T_ACID_IN >= 105°C (HH):
    → CRITICAL (FAISCEAU_CORROSION)
elif T_ACID_IN >= 100°C (H):
    → WARNING (FAISCEAU_CORROSION)
```

### 2.7 Règle 6 : FLOW_LOW

**Fichier** : `core/detection/detector.py` → `_rule_flow_anomaly`

**Logique** : si le débit acide est trop bas, la circulation est insuffisante.

```python
if F_ACID <= 20 m³/h (LL):
    → CRITICAL (CALANDRE_FUITE)
elif F_ACID <= 35 m³/h (L):
    → WARNING (CALANDRE_FUITE)
```

---

## PARTIE 3 — La fusion (1h)

### 3.1 Comment combine-t-on règles et ML ?

**Fichier** : `core/detection/detector.py` → `CoolerAnomalyDetector.analyze`

**Règle simple** : `severity = max(severities)` sur tous les findings.

### 3.2 Les cas de figure

| Situation | Résultat |
|-----------|----------|
| Règle WARNING + modèle WARNING | Confiance renforcée |
| Règle CRITICAL seule | Alert WARNING |
| Modèle seul (score élevé) | Alert INFO (point isolé) |
| Modèle seul (persistant) | Alert WARNING |
| Aucun des deux | Pas d'alerte |

### 3.3 La persistance du modèle

**Fichier** : `core/detection/detector.py`

```python
if score > threshold:
    n_recent = heures atypiques sur les 6 dernières heures
    if n_recent >= 3:
        → MODEL_ANOMALY (WARNING)
    else:
        → MODEL_ANOMALY_ISOLATED (INFO)
```

---

## PARTIE 4 — Priorité des constatations (1h)

### 4.1 Pourquoi une priorité ?

Quand plusieurs constatations sont détectées en même temps, il faut choisir laquelle mettre en avant dans le diagnostic.

### 4.2 L'algorithme de priorité

**Fichier** : `core/detection/detection_agent.py` → `_priorite`

```python
def _priorite(constatation):
    return (
        SEVERITY_ORDER[constatation.severity],  # 1. Sévérité
        0 if sous_ensemble == "INSTRUMENTATION" else 1,  # 2. Équipement > Instrumentation
        mode.C if mode else 0,  # 3. Criticité AMDEC
        1 if source == "RULE" else 0,  # 4. Règle > Modèle
        constatation.code,  # 5. Code alphabétique
    )
```

### 4.3 Exemple

Si on a en même temps :
- SENSOR_FAULT (INFO, instrumentation)
- FOULING_DRIFT (WARNING, équipement, C=105)

**Priorité** : FOULING_DRIFT gagne car :
1. WARNING > INFO
2. Équipement > Instrumentation
3. C=105 > 0

---

## PARTIE 5 — Manipulation (2h)

### 5.1 Explorer les règles

**Exécute :**
```bash
python -c "
from core.detection.detector import RuleEngine
from core.knowledge.knowledge import load_domain

d = load_domain()
engine = RuleEngine(d)
print('=== Les 6 règles du moteur ===')
print('  1. SENSOR_FAULT   - état des capteurs')
print('  2. CONTROL_LOSS   - perte de contrôle température')
print('  3. FOULING_DRIFT  - dérive UA persistante (72h)')
print('  4. CONC_LOW       - titre acide bas')
print('  5. T_IN_HIGH      - température d entrée excessive')
print('  6. FLOW_LOW       - débit acide anormal')
"
```

### 5.2 Comprendre la fusion

**Exercice** : à un instant donné, on détecte :
- SENSOR_FAULT (INFO)
- FOULING_DRIFT (WARNING)
- Score modèle = 0.85 (threshold = 0.98)

**Question** : quelle est la sévérité finale et pourquoi ?

**Réponse** : WARNING (FOULING_DRIFT gagne car c'est la sévérité la plus élevée). Le modèle n'est pas au-dessus du seuil donc pas de finding modèle.

---

## Ce que je dois retenir

1. 6 règles déterministes basées sur la physique
2. FOULING_DRIFT est la règle la plus importante (72h de persistance)
3. Fusion : severity = max(règles, modèle)
4. Priorité : sévérité > équipement > criticité > source
5. Les règles et le ML se complètent

---

## Questions du jury

**Faciles :**
1. "Combien de règles avez-vous ?"
2. "Pourquoi des règles en plus du ML ?"
3. "Comment combinez-vous les deux ?"

**Techniques :**
4. "Pourquoi FOULING_DRIFT exige 72h de persistance ?"
5. "Comment choisissez-vous la constatation dominante ?"
6. "Que se passe-t-il si une règle et le modèle sont en désaccord ?"

**Pièges :**
7. "Pourquoi pas uniquement le ML ?"
8. "Que se passe-t-il si un seuil est mal calibré ?"
9. "Comment savez-vous que vos règles ne génèrent pas trop de faux positifs ?"

---

## Test de fin de journée

1. **Cite** les 6 règles et leur seuil
2. **Explique** pourquoi FOULING_DRIFT exige 72h
3. **Explique** comment la fusion fonctionne
4. **Donne un exemple** de priorité de constatation
