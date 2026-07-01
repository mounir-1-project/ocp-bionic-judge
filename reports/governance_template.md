# OCP Bionic Judge — Rapport de Gouvernance IA

**Date** : {{date}}
**Période** : {{window}}
**Généré par** : OCP Bionic Judge System v1.0

---

## 1. Résumé Exécutif

| Indicateur                | Valeur       | Statut |
|---------------------------|-------------|--------|
| Confiance moyenne Judge   | {{mean_confidence}}% | {{confidence_status}} |
| Taux de désaccord         | {{disagreement_rate}}% | {{disagreement_status}} |
| Conformité OCP            | {{ocp_compliance}}% | {{compliance_status}} |
| Alertes critiques         | {{critical_alerts}} | {{alert_status}} |

---

## 2. Métriques par Machine

{{machine_metrics_table}}

---

## 3. Dérive du Modèle ML

- **PSI (Population Stability Index)** : {{psi_value}}
  - Seuil d'alerte : 0.20
  - Statut : {{psi_status}}

- **Test de Kolmogorov-Smirnov** : p-value = {{ks_pvalue}}
  - Seuil d'alerte : 0.05
  - Statut : {{ks_status}}

---

## 4. Alertes et Incidents

{{alerts_list}}

---

## 5. Recommandations

{{recommendations}}

---

## 6. Actions Requises

- [ ] Révision des anomalies CRITICAL non résolues
- [ ] Re-calibration du modèle si PSI > 0.2
- [ ] Audit des décisions avec score Judge < 6.0
- [ ] Mise à jour de la baseline si distribution stable

---

*Ce rapport est généré automatiquement par le système OCP Bionic Judge.*
*Confidentiel — Usage interne OCP Group uniquement.*
