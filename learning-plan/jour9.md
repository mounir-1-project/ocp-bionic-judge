# JOUR 9 — Contrôle (Judge) et 8 vérifications

## Objectif du jour

À la fin de cette journée, tu dois être capable de :
- Expliquer pourquoi un contrôleur de cohérence est nécessaire
- Connaître les 8 vérifications et leur rôle
- Comprendre les safety caps
- Expliquer la confiance partagée
- Comprendre le flux complet du Judge

---

## PARTIE 1 — Pourquoi un contrôleur ? (1h)

### 1.1 Le problème

Un diagnostic peut contenir des erreurs :
- Valeurs inventées (hallucination)
- Sévérité mal évaluée
- Mode AMDEC inexistant
- Action dangereuse ou non exécutable

### 1.2 La solution

Le **Judge** est un contrôleur déterministe qui :
1. **Recalcule les faits** depuis les données brutes (pas depuis le diagnostic)
2. **Compare** chaque affirmation du diagnostic aux faits recalculés
3. **Note** la cohérence de 0 à 10
4. **Détecte** les erreurs graves (safety caps)

### 1.3 Pourquoi déterministe ?

Parce que le contrôle doit être :
- **Reproductible** : même entrée → même résultat
- **Objectif** : pas d'opinion, des faits
- **Vérifiable** : on peut comprendre pourquoi il rejette

---

## PARTIE 2 — Les 8 vérifications (3h)

### 2.1 Vue d'ensemble

**Fichier** : `core/verification/judge_agent.py` → `VerificationLayer`

| # | ID | Poids | Question |
|---|-----|-------|----------|
| V1 | `NUMERIC_FIDELITY` | 22% | Les valeurs citées sont-elles exactes ? |
| V2 | `SEVERITY` | 16% | La sévérité correspond-elle aux faits ? |
| V3 | `AMDEC_GROUNDING` | 14% | Les modes AMDEC existent-ils et sont-ils détectables ? |
| V4 | `ACTION_CONFORMITY` | 14% | L'action est-elle proportionnée et exécutable ? |
| V5 | `CONFIDENCE` | 15% | La confiance reflète-t-elle les preuves ? |
| V6 | `STATE_AWARENESS` | 8% | L'état de marche est-il respecté ? |
| V7 | `EVIDENCE_COVERAGE` | 5% | Le fait le plus grave est-il traité ? |
| V8 | `UNCERTAINTY` | 6% | Les limites sont-elles énoncées ? |

### 2.2 V1 : Fidélité numérique (22%)

**Fichier** : `core/verification/judge_agent.py` → `_v1_numeric_fidelity`

**Question** : chaque valeur citée dans le diagnostic correspond-elle à la mesure réelle ?

**Méthode** :
1. Comparer chaque valeur de `cited_values` aux mesures recalculées
2. Tolérance : 1% relatif ou 0.05 absolu
3. Vérifier les nombres dans le texte du diagnostic

**Résultat** :
- 0/10 si valeur fausse
- 5/10 si valeurs invérifiables
- 1.5/10 si aucune valeur citée
- 10/10 si toutes exactes

### 2.3 V2 : Sévérité (16%)

**Fichier** : `core/verification/judge_agent.py` → `_v2_severity`

**Question** : la sévérité annoncée correspond-elle aux faits recalculés ?

**Logique** :
- Conforme → 10/10
- Sous-estimée → pénalité forte (max 0 si gap ≥ 2)
- Surestimée → pénalité légère (min 4)

**Pourquoi asymétrique** : sous-estimer est plus grave (laisse passer une dégradation).

### 2.4 V3 : Ancrage AMDEC (14%)

**Fichier** : `core/verification/judge_agent.py` → `_v3_amdec_grounding`

**Question** : les modes AMDEC invoqués existent-ils et sont-ils détectables ?

**Vérifications** :
- Mode existe dans l'AMDEC → sinon 0/10
- Mode est "full" observable → sinon 1/10 (angle mort)
- Mode est soutenu par les constatations → sinon 5/10

### 2.5 V4 : Conformité de l'action (14%)

**Fichier** : `core/verification/judge_agent.py` → `_v4_action_conformity`

**Question** : l'action est-elle proportionnée, exécutable, conforme au plan préventif ?

**Vérifications** :
- Urgence suffisante pour la sévérité
- Arrêt signalé si requis
- Pas d'arrêt si non requis
- Description suffisamment détaillée (≥ 25 caractères)
- Tâche existante dans le plan préventif

### 2.6 V5 : Calibration de la confiance (15%)

**Fichier** : `core/verification/judge_agent.py` → `_v5_confidence`

**Question** : la confiance annoncée reflète-t-elle la force des preuves ?

**Méthode** :
- Calculer la confiance attendue avec `confiance_justifiable()`
- Comparer à la confiance annoncée
- Tolérance : +0.12 (sur-confiance) / -0.30 (sous-confiance)

### 2.7 V6 : État de marche (8%)

**Fichier** : `core/verification/judge_agent.py` → `_v6_state_awareness`

**Question** : l'état de marche est-il respecté ?

**Vérifications** :
- État annoncé = état réel → sinon 0/10
- Diagnostic de performance hors RUNNING → 1/10

### 2.8 V7 : Couverture (5%)

**Fichier** : `core/verification/judge_agent.py` → `_v7_evidence_coverage`

**Question** : le fait le plus grave est-il traité ?

**Méthode** : comparer les constatations aux `evidence_refs` du diagnostic.

### 2.9 V8 : Incertitude (6%)

**Fichier** : `core/verification/judge_agent.py` → `_v8_uncertainty)

**Question** : les limites sont-elles énoncées ?

**Vérification** : si des capteurs sont en défaut ou le modèle inapplicable, le diagnostic doit le mentionner.

---

## PARTIE 3 — Les safety caps (1h)

### 3.1 Définition

Les **safety caps** sont des erreurs si graves qu'elles **plafonnent la note à 4/10**, quel que soit le reste.

**Fichier** : `core/verification/judge_agent.py` → `_apply_safety_cap`

### 3.2 Les erreurs bloquantes

| Erreur | Signification | Plafond |
|--------|---------------|---------|
| `HALLUCINATED_VALUE` | Valeur inventée | 4/10 |
| `UNSAFE_ACTION` | Action dangereuse | 4/10 |
| `INVENTED_AMDEC_MODE` | Mode AMDEC inexistant | 4/10 |
| `BLIND_SPOT_CLAIM` | Diagnostic sur angle mort | 4/10 |
| `STATE_MISMATCH` | État de marche erroné | 5/10 |

### 3.3 Pourquoi des plafonds ?

Ces erreurs sont **si graves** qu'elles rendent le diagnostic inutilisable, même si le reste est correct. Un diagnostic avec une valeur inventée ne peut pas être approuvé.

---

## PARTIE 4 — La confiance partagée (1h)

### 4.1 Le barème

**Fichier** : `core/detection/schemas.py` → `confiance_justifiable()`

Même formule pour l'agent et le Judge :

```
confiance = 0.50 (base)
         + 0.20 si preuves solides
         + 0.10 si corroboration (règle + modèle)
         + 0.10 si modèle applicable
         - 0.15 × min(n_invalid, 2) si capteurs en défaut
         - 0.15 si hors RUNNING
         - 0.30 si mode "none" (angle mort)
         - 0.10 si mode "partial"
```

### 4.2 Pourquoi partagé ?

Le Judge **vérifie** que l'agent a correctement évalué sa confiance. Si l'agent annonce 0.80 mais que les preuves ne justifient que 0.60, le Judge le détecte.

---

## PARTIE 5 — Le flux complet du Judge (1h)

### 5.1 Les étapes

**Fichier** : `core/verification/judge_agent.py` → `JudgeAgent.judge()`

```
1. _verified_facts() : recalcule la détection depuis les features
2. verifier.run() : 8 contrôles
3. det_score = Σ(score × weight)
4. _apply_safety_cap() : plafonds
5. agreement = final ≥ 6.0
```

### 5.2 Le recalcul des faits

**Fichier** : `core/verification/judge_agent.py` → `VerifiedFacts`

Le Judge **recalcule** la détection depuis les features brutes, sans jamais lire ce que l'agent a affirmé. C'est ce qui garantit l'indépendance du contrôle.

---

## PARTIE 6 — Manipulation (1h)

### 6.1 Explorer les poids

**Exécute :**
```bash
python -c "
from core.verification.judge_agent import VerificationLayer
from core.knowledge.knowledge import load_domain

d = load_domain()
v = VerificationLayer(d)
print('=== Poids des 8 vérifications ===')
for check_id, weight in v.WEIGHTS.items():
    print(f'  {check_id:25s} : {weight*100:.0f}%')
"
```

---

## Ce que je dois retenir

1. Le Judge recalcule les faits indépendamment
2. 8 vérifications avec poids différents
3. Safety caps = erreurs non compensables (plafond 4/10)
4. Seuil d'accord = 6/10
5. Confiance partagée Agent/Judge

---

## Questions du jury

**Faciles :**
1. "Combien de vérifications fait le Judge ?"
2. "Pourquoi un contrôleur de cohérence ?"
3. "Qu'est-ce qu'un safety cap ?"

**Techniques :**
4. "Donnez un exemple de safety cap"
5. "Comment le Judge recalcule-t-il les faits ?"
6. "Que sont les poids des vérifications ?"
7. "Comment fonctionne la confiance partagée ?"

**Pièges :**
8. "Comment savez-vous que le Judge ne valide pas tout ?"
9. "Pourquoi le seuil est-il à 6/10 et pas 5/10 ?"
10. "Que se passe-t-il si le Judge et l'agent sont en désaccord ?"
11. "Le Judge peut-il se tromper ?"

---

## Test de fin de journée

1. **Explique** pourquoi un contrôleur est nécessaire
2. **Cite** les 8 vérifications et leur poids
3. **Explique** un safety cap avec un exemple
4. **Explique** le flux complet du Judge
