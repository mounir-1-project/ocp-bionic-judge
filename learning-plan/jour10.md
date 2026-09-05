# JOUR 10 — Interface, démonstration et soutenance

## Objectif du jour

À la fin de cette journée, tu dois être capable de :
- Maîtriser l'interface pour faire une démonstration fluide
- Répondre à toutes les questions du jury
- Faire une démonstration complète de A à Z

---

## PARTIE 1 — L'interface (2h)

### 1.1 Les 3 onglets

**Fichiers** : `interface/dashboard.html`, `interface/main.py`

| Onglet | Objectif | Contenu principal |
|--------|----------|-------------------|
| **Salle** | Vue temps réel | 3D, timeline, diagnostic, journal |
| **Intégrité** | Vue synthèse | KPIs, alarmes, AMDEC, workflows |
| **Contrôle** | Vue gouvernance | 8 checks, couverture, notifications |

### 1.2 Onglet Salle

**Fichiers** : `interface/static/app.js`

- **Modèle 3D** : visualisation interactive du refroidisseur
- **Timeline** : épisodes d'anomalie avec sigma
- **Signaux** : 10 courbes disponibles (UA, titres, débits...)
- **Diagnostic** : décision courante avec confiance et action
- **Journal** : flux des analyses successives

### 1.3 Onglet Intégrité

- **KPIs** : disponibilité (97,3%), épisodes/mois (4), exposition corrosive (2h)
- **Alarmes** : cycle ISA-18.2 (ACTIVE → ACKNOWLEDGED → CLOSED)
- **AMDEC** : tableau complet avec criticité et observabilité
- **Workflows** : templates d'interventions

### 1.4 Onglet Contrôle

- **8 checks** : corridor de vérification visuel
- **Taux de signalement** : graphique mensuel avec cible 2%
- **Couverture AMDEC** : 30,2% détecté
- **Notifications** : statut email
- **Angles morts** : modes non détectables

---

## PARTIE 2 — Le rejeu (1h)

### 2.1 Principe

Le rejeu simule le flux de données en accéléré. C'est comme si on regardait 14 mois de fonctionnement en quelques minutes.

### 2.2 Les vitesses

| Vitesse | Signification |
|---------|---------------|
| 1 jour/s | 24 heures de process par seconde réelle |
| 5 jours/s | 120 heures de process par seconde |
| 1 mois/s | 720 heures de process par seconde |

### 2.3 Le fonctionnement

**Fichier** : `replay/replay.py`

1. Le rejeu parcourt l'historique heure par heure
2. À chaque heure (ou toutes les N heures selon le pas), il analyse
3. L'analyse est envoyée au dashboard en temps réel
4. Les alertes sont enregistrées et les emails envoyés

---

## PARTIE 3 — Les alarmes (1h)

### 3.1 Le cycle de vie

**Fichier** : `core/alerts/alarms.py`

```
ACTIVE → ACKNOWLEDGED → RETURNED_NORMAL → CLOSED
    ↓
  SHELVED (inhibition temporaire)
```

### 3.2 Les états

| État | Signification |
|------|---------------|
| **ACTIVE** | Alerte en cours, non traitée |
| **ACKNOWLEDGED** | Opérateur a pris connaissance |
| **SHELVED** | Inhibition temporaire (maintenance) |
| **RETURNED_NORMAL** | La condition a cessé |
| **CLOSED** | Alerte clôturée |

### 3.3 L'email

**Fichier** : `core/alerts/email.py`

Quand une alerte WARNING ou CRITICAL est détectée pendant le rejeu :
1. L'alarme apparaît dans le registre
2. Un email est envoyé au technicien connecté
3. L'opérateur peut acquitter ou inhiber

---

## PARTIE 4 — Simulation de soutenance (5h)

### 4.1 Révision générale (2h)

Relis les résumés des jours 1-9. Concentre-toi sur :
- Les 3 idées clés (J1)
- UA et efficacité-NTU (J4)
- Les 11 features (J5)
- Isolation Forest (J6)
- Les 6 règles (J7)
- Les 8 checks du Judge (J9)

### 4.2 Questions du jury (3h)

**Partie 1 — Présentation (10 min)**

**Q1 : "Présentez votre projet en 3 minutes."**

**Réponse modèle :**

"Mon projet est un système de détection d'anomalies pour le refroidisseur d'acide de séchage E7301 de l'atelier sulfurique PS III à Maroc Chimie.

Ce refroidisseur refroidit de l'acide sulfurique à 98% avec de l'eau de mer. Au fil du temps, des dépôts s'accumulent sur les tubes, réduisant les performances.

Mon système surveille 12 capteurs DCS sur 14 mois de données (10 180 horodatages). Il calcule le coefficient d'échange UA qui mesure directement les performances, puis combine un modèle statistique (Isolation Forest) avec 6 règles déterministes pour détecter les anomalies.

Chaque diagnostic est vérifié par un contrôleur de cohérence (Judge) avec 8 vérifications indépendantes avant d'être affiché sur le dashboard."

---

**Q2 : "Quel est le problème industriel ?"**

L'encrassement du faisceau tubulaire réduit les performances du refroidisseur. Si on ne le détecte pas, l'acide sort trop chaud, endommageant l'équipement en aval.

---

**Q3 : "Pourquoi ce refroidisseur ?"**

C'est un équipement critique de l'atelier sulfurique. Il refroidit l'acide de séchage à 98%, essentiel pour la production d'acide sulfurique. Un arrêt non planifié a un coût industriel important.

---

**Q4 : "Quelles sont vos données ?"**

10 180 horodatages DCS (une mesure par heure, 14 mois) avec 12 capteurs : températures, débits, titres d'acide. Le fichier DATA.xlsx fait partie du livrable.

---

**Partie 2 — Technique (20 min)**

**Q5 : "Décrivez le flux complet."**

Ingestion → Features (11 variables) → Détection (règles + ML) → Diagnostic → Judge (8 vérifications) → Interface.

---

**Q6 : "Expliquez le calcul de UA."**

ε = (T_in - T_out) / (T_in - T_sea), NTU = -ln(1-ε), UA = C_acide × NTU. La température d'eau de mer vient de la climatologie de Safi.

---

**Q7 : "Pourquoi Isolation Forest ?"**

Pas d'historique de pannes étiqueté → non supervisé. contamination=0.02, 300 arbres. Le modèle apprend ce qui est "normal" et détecte les écarts.

---

**Q8 : "Quelle différence entre règles et ML ?"**

Règles = physique, toujours disponibles, expliquent pourquoi. ML = patterns, voit l'invisible. Les deux se complètent et sont fusionnées.

---

**Q9 : "Expliquez les 8 vérifications du Judge."**

V1 (22%) : valeurs exactes. V2 (16%) : sévérité conforme. V3 (14%) : modes AMDEC fondés. V4 (14%) : action exécutable. V5 (15%) : confiance calibrée. V6 (8%) : état respecté. V7 (5%) : fait le plus grave traité. V8 (6%) : limites énoncées.

---

**Q10 : "Que sont les safety caps ?"**

Erreurs si graves (valeur inventée, action dangereuse, mode inexistant, angle mort, état erroné) qu'elles plafonnent la note à 4/10, quel que soit le reste.

---

**Partie 3 — Démonstration (10 min)**

**Script :**
1. `python -m interface`
2. Connexion
3. Lancer rejeu à 5 jours/s
4. Observer une alerte WARNING
5. Montrer le diagnostic et l'action
6. Montrer l'alarme dans le registre
7. Arrêter le rejeu

---

**Partie 4 — Réflexion (10 min)**

**Q11 : "Quelles sont les limites ?"**

- Climatologie ≠ température réelle
- Pas de vérité terrain (pas d'historique de pannes)
- Modèle sur une seule période
- 30,2% du risque AMDEC couvert

---

**Q12 : "Que faudrait-il améliorer ?"**

Mesurer réellement T_SEAWATER, intégrer l'historique GMAO, tester sur plus de données, valider avec des experts terrain.

---

**Q13 : "Comment savez-vous qu'une anomalie est réelle ?"**

Le Judge recalcule les faits indépendamment et vérifie 8 points. Un safety cap empêche les hallucinations. Mais c'est un contrôle de cohérence interne, pas une validation terrain.

---

**Q14 : "Peut-on utiliser ce système en production ?"**

Pour la démonstration, oui. Pour la production, il faudrait : mesurer T_SEAWATER, intégrer GMAO, tester sur plus de données, et valider avec des experts terrain.

---

## PARTIE 5 — Conseils pour la soutenance

### 5.1 Avant la soutenance

- Relis le résumé de chaque jour
- Entraîne-toi à parler à voix haute
- Prépare une démo fluide (5-7 minutes max)

### 5.2 Pendant la soutenance

- **Sois confiant** : tu connais ton projet mieux que quiconque
- **Sois clair** : utilise des termes simples quand c'est possible
- **Sois honnête** : admet les limites, c'est un signe de maturité
- **Montre le code** : si on te demande, montre la fonction concernée
- **Fais la démo** : c'est le meilleur moyen de prouver que ça marche

### 5.3 Les erreurs à éviter

- Ne dis pas "je ne sais pas" → dis "je vais vérifier"
- Ne dis pas "c'est compliqué" → simplifie l'explication
- Ne dis pas "on m'a dit de faire comme ça" → justifie ton choix
- Ne cache pas les limites → elles montrent que tu comprends

---

## Test final

Fais une démonstration complète :
1. Connecte-toi
2. Explique le flux de données
3. Lance le rejeu
4. Observe une alerte
5. Explique le diagnostic
6. Montre le Judge
7. Explique les limites

Si tu peux faire tout ça sans être perdu, tu es prêt pour la soutenance.
