# JOUR 8 — Diagnostic, AMDEC et lien physique

## Objectif du jour

À la fin de cette journée, tu dois être capable de :
- Expliquer ce qu'est l'AMDEC et pourquoi elle est utilisée
- Comprendre les modes de défaillance présents
- Expliquer comment un diagnostic est produit
- Comprendre le lien anomalie → AMDEC → action

---

## PARTIE 1 — L'AMDEC (2h)

### 1.1 Définition

**AMDEC** = Analyse des Modes de Défaillance, de leurs Effets et de leur Criticité.

C'est un outil d'**analyse de risque** utilisé en maintenance industrielle. Pour chaque mode de défaillance possible, on évalue :
- **F** (Fréquence) : à quelle fréquence cela peut-il arriver ? (1-10)
- **G** (Gravité) : quel est l'impact si cela arrive ? (1-10)
- **N** (Non-détection) : quelle est la probabilité de ne pas le détecter ? (1-10)
- **C** (Criticité) = F × G × N

**Fichier** : `core/knowledge/amdec.yaml`

### 1.2 Les modes de défaillance

| Code | Élément | Mode | F | G | N | C | Détectable |
|------|---------|------|---|---|---|---|------------|
| FAISCEAU_BOUCHAGE | Faisceau tubulaire | Bouchage/encrassement | 5 | 7 | 3 | 105 | oui |
| FAISCEAU_FUITE | Faisceau tubulaire | Fuite de tube | 5 | 7 | 3 | 105 | oui |
| FAISCEAU_CORROSION | Faisceau tubulaire | Corrosion/perte d'épaisseur | 5 | 7 | 3 | 105 | partielle |
| CALANDRE_FUITE | Calandre | Fuite | 5 | 6 | 3 | 90 | partielle |
| CAPTEUR_DEFAILLANT | Chaîne de mesure | Signal figé/saturé | 6 | 6 | 3 | 108 | oui |
| PLAQUE_SACRIFICIELLE | Anode sacrificielle | Dysfonctionnement | 8 | 7 | 2 | 112 | **NON** |
| PORTE_VISITE_FUITE | Porte de visite | Fuite | 5 | 6 | 3 | 90 | NON |
| VANNE_ACIDE_FUITE | Vanne d'acide | Fuite | 8 | 7 | 2 | 112 | NON |
| VANNE_EM_BOUCHAGE | Vanne eau de mer | Bouchage/coincement | 6 | 7 | 1 | 42 | NON |

### 1.3 L'observabilité

**Fichier** : `core/knowledge/knowledge.py` → `FailureMode.observabilite`

Un mode peut être :
- **full** (observable) : on peut le détecter avec les capteurs disponibles
- **partial** (partiellement observable) : on observe les conditions, pas l'état
- **none** (non observable) : aucun signal ne dit rien de ce mode

**Exemple** :
- FAISCEAU_BOUCHAGE → **full** (on voit UA baisser)
- FAISCEAU_CORROSION → **partial** (on voit les conditions favorables, pas l'amincissement)
- PLAQUE_SACRIFICIELLE → **none** (aucun capteur ne mesure l'état de l'anode)

### 1.4 Les angles morts

Les modes **none** sont les "angles morts" du système. Le système les déclare explicitement :

```python
blind_spots = [m for m in modes if m.observabilite == "none"]
# → PLAQUE_SACRIFICIELLE, VANNE_ACIDE_*, VANNE_EM_*, PORTE_VISITE_*
```

**30,2% du risque AMDEC est couvert** par les données. Le reste relève du plan préventif.

---

## PARTIE 2 — Le diagnostic (2h)

### 2.1 Le dossier de faits

**Fichier** : `core/detection/detection_agent.py` → `build_case_file()`

Avant de diagnostiquer, on assemble un **dossier de faits** contenant :
- Équipement, timestamp, état process
- Sévérité calculée, score modèle
- Mesures réelles
- Constatations avec preuves
- Modes AMDEC avec criticité
- Qualité des données
- Angles morts

### 2.2 La composition du diagnostic

**Fichier** : `core/detection/detection_agent.py` → `RuleBasedComposer`

**Étape 1** : Sélectionner la constatation dominante
- Critères : sévérité > équipement > criticité > source

**Étape 2** : Rattacher au mode AMDEC
- Le code de la constatation pointe vers un mode (ex: FOULING_DRIFT → FAISCEAU_BOUCHAGE)

**Étape 3** : Construire l'action
- Lire le plan préventif pour ce mode
- Choisir la tâche la plus fréquente
- Déterminer l'urgence et la fenêtre d'exécution

**Étape 4** : Évaluer la confiance
- Utiliser `confiance_justifiable()` (barème partagé avec le Judge)

### 2.3 Exemple concret

**Constatation** : FOULING_DRIFT (WARNING)

**Diagnostic** :
```
"Coefficient d'échange global inférieur de 2.3 sigma à sa référence 
sur 14 jours, maintenu depuis plus de 72h. UA mesuré 16.2 kW/K 
pour 17.8 attendu. Rattachement AMDEC : FAISCEAU TUBULAIRE / 
Bouchage / encrassement (criticité 105, majeure)."
```

**Action** :
```
"Mesure des épaisseurs (courant de Foucault) — nettoyage haute 
pression des tubes — tâche B du plan préventif (cadence 2 ans)."
```

**Urgence** : SOUS_24H ( WARNING → 24 heures)

---

## PARTIE 3 — Le lien anomalie → AMDEC → action (1h)

### 3.1 Le chaînage

```
Anomalie détectée (FOULING_DRIFT)
    ↓
Mode AMDEC (FAISCEAU_BOUCHAGE, C=105)
    ↓
Action corrective du plan préventif
    ↓
Urgence selon la sévérité
    ↓
Responsable (SERVICE_MÉCANIQUE)
```

### 3.2 L'action recommandée

**Fichier** : `core/detection/detection_agent.py` → `_build_action`

| Sévérité | Urgence | Fenêtre |
|----------|---------|---------|
| NORMAL | AUCUNE | EN_MARCHE |
| INFO | SOUS_SURVEILLANCE | EN_MARCHE |
| WARNING | SOUS_24H | ARRET_PROGRAMME |
| CRITICAL | SOUS_8H | ARRET_IMMEDIAT |

---

## PARTIE 4 — Manipulation (2h)

### 4.1 Explorer l'AMDEC

**Exécute :**
```bash
python -c "
from core.knowledge.knowledge import load_domain
d = load_domain()
print('=== Modes AMDEC par criticité ===')
for m in d.modes_ranked():
    print(f'  {m.code:25s} | C={m.C:3d} | {m.observabilite:10s} | {m.mode}')
"
```

### 4.2 Explorer les angles morts

**Exécute :**
```bash
python -c "
from core.knowledge.knowledge import load_domain
d = load_domain()
print('=== Angles morts (non détectables) ===')
for m in d.blind_spots():
    print(f'  {m.code:25s} | C={m.C:3d} | {m.mode}')
print()
print(f'Risque couvert : {d.risk_coverage()[\"part_couverte_pct\"]}%')
"
```

---

## Ce que je dois retenir

1. AMDEC = F × G × N, modes avec observabilité
2. 3 niveaux d'observabilité : full, partial, none
3. 30,2% du risque couvert, le reste = plan préventif
4. Diagnostic = constatation dominante → mode AMDEC → action
5. Confiance = barème partagé Agent/Judge

---

## Questions du jury

**Faciles :**
1. "Qu'est-ce que l'AMDEC ?"
2. "Combien de modes de défaillance avez-vous ?"
3. "Qu'est-ce qu'un angle mort ?"

**Techniques :**
4. "Comment le diagnostic utilise-t-il l'AMDEC ?"
5. "Qu'est-ce que la confiance justifiable ?"
6. "Comment choisissez-vous l'action corrective ?"

**Pièges :**
7. "Comment savez-vous que le diagnostic est correct ?"
8. "Que se passe-t-il si le mode AMDEC n'est pas observable ?"
9. "Pourquoi 30,2% de couverture et pas plus ?"

---

## Test de fin de journée

1. **Explique** ce qu'est l'AMDEC et ses composantes (F, G, N, C)
2. **Cite** 3 modes détectables et 2 non détectables
3. **Explique** le chaînage anomalie → AMDEC → action
4. **Pourquoi** certains modes sont des angles morts ?
