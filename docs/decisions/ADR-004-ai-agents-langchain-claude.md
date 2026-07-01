# ADR-004 — Agents IA : LangChain + Google Gemini 2.0 Flash

**Statut** : Accepté (mis à jour 2025-06)  
**Date** : 2024-02-01  
**Auteur** : Mounir Sanbouli  

---

## Contexte

Après détection ML d'une anomalie, on veut un diagnostic en langage naturel avec une recommandation d'action. Deux approches possibles :
1. **Règles if/else codées en dur** (ex: `if temp > 80 → "surchauffe"`)
2. **Agent IA avec un LLM** qui raisonne sur les données

---

## Pourquoi un Agent IA et pas des règles ?

Les règles if/else sont fragiles :
- Il faudrait encoder les comportements spécifiques de chaque type de machine (broyeur vs pompe vs réacteur)
- Les combinaisons de capteurs créent des milliers de cas (température OK + vibration élevée + pression basse = ?)
- Impossible de contextualiser avec l'historique de la machine
- Les règles ne s'expliquent pas elles-mêmes

Un Agent IA avec accès à la BDD peut :
- Comparer la valeur actuelle avec l'historique 7 jours de CETTE machine
- Croiser plusieurs capteurs dans son raisonnement
- Expliquer son diagnostic en langage naturel pour les techniciens OCP
- S'adapter sans recodage si un nouveau type d'anomalie apparaît

---

## Pourquoi pas Mistral AI (le LLM officiel du programme Bionic OCP) ?

Le programme **Bionic × Mistral AI** est le partenariat officiel OCP pour les projets IA internes. En production, `mistral-large-latest` serait le choix naturel. Trois raisons expliquent pourquoi ce n'est pas le cas ici :

1. **Accès API** : l'accès à Mistral dans le cadre du programme Bionic passe par les comptes entreprise OCP — un stagiaire n'a pas accès à ces credentials en dehors du réseau interne.
2. **Coût** : `mistral-large-latest` est un modèle payant. Dans un contexte de stage étudiant, la contrainte principale est le coût zéro.
3. **Portabilité** : ce projet doit pouvoir tourner localement, sur n'importe quelle machine, sans dépendance à l'infrastructure OCP.

**Le chemin de migration vers Mistral en production est trivial** — une ligne dans `.env` :
```
GEMINI_MODEL=mistral-large-latest
```
et remplacer `ChatGoogleGenerativeAI` par `ChatMistralAI` dans `detection_agent.py`. Le reste du code (outils ReAct, prompts, Judge Agent) ne change pas.

---

## Choix du LLM : comparaison sur critères pratiques

Mistral étant écarté pour les raisons ci-dessus, les alternatives sont toutes des LLMs externes à OCP — elles sont donc sur un pied d'égalité de ce point de vue. Le critère de sélection devient purement **pratique** : qualité, coût, accessibilité immédiate.

| LLM | Tier gratuit | Contexte | Qualité JSON | Accessibilité | Verdict |
|-----|-------------|---------|-------------|--------------|---------|
| **Gemini 2.0 Flash** | ✅ 1 500 req/jour | 1M tokens | Fiable | Clé en 30s, sans CB | ✅ Choisi |
| Mistral Large | ❌ Payant | 128k tokens | Très fiable | Accès entreprise OCP | 🏭 Production |
| GPT-4o | ❌ Payant | 128k tokens | Très fiable | Carte bancaire requise | ❌ Coût |
| Llama 3.1 70B | ✅ Open source | 128k tokens | Bonne | GPU local requis | ❌ Infra |
| Gemini 1.5 Pro | ✅ Quota limité | 2M tokens | Fiable | Même que Flash | 🔮 Alternative |

**Pourquoi Gemini 2.0 Flash ?** Parmi les LLMs accessibles gratuitement sans infrastructure particulière, c'est celui qui offre le meilleur rapport qualité/contexte : 1 million de tokens (suffisant pour historique capteurs + raisonnement ReAct), réponses JSON structurées fiables, intégration LangChain native. GPT-4o et Mistral sont techniquement supérieurs mais nécessitent un paiement — ce qui sort du cadre d'un stage étudiant.

---

## Choix du framework : LangChain vs alternatives

| Framework | Évaluation | Verdict |
|-----------|-----------|---------|
| **LangChain** | Standard industrie, pattern ReAct intégré, nombreux outils | ✅ Choisi |
| LlamaIndex | Meilleur pour RAG (recherche dans documents), moins adapté aux agents avec outils | ❌ |
| Code pur (appel API direct) | Plus simple pour le Judge Agent (1 seul appel) | ✅ Utilisé pour judge_agent.py |
| AutoGen (Microsoft) | Multi-agent natif mais plus complexe à déboguer | 🔮 Alternative future |
| CrewAI | Plus récent, intéressant pour orchestration multi-agents | 🔮 Alternative future |

**Décision hybride :** LangChain pour le Detection Agent (ReAct avec outils), appel via LangChain direct pour le Judge Agent (plus simple, 1 seul call).

---

## Pattern ReAct expliqué

```
QUESTION → Agent reçoit la tâche
    ↓
THOUGHT  → "Je dois d'abord regarder les anomalies récentes"
    ↓
ACTION   → Appelle l'outil get_anomaly_data("BROYEUR_01", n=10)
    ↓
OBSERVATION → [{"score": 0.87, "severity": "CRITICAL"}, ...]
    ↓
THOUGHT  → "Score élevé. Je dois comparer avec l'historique"
    ↓
ACTION   → Appelle get_machine_history("BROYEUR_01", days=7)
    ↓
OBSERVATION → {"temp_mean": 65.2, "temp_std": 3.1, ...}
    ↓
THOUGHT  → "Temp actuelle 85°C vs moyenne 65°C → +3 sigma → CRITIQUE"
    ↓
FINAL ANSWER → JSON structuré avec diagnosis + recommended_action
```

**Pourquoi ce pattern est supérieur à un simple prompt ?**
L'agent ne connaît pas les données à l'avance — il les cherche activement. Comme un vrai ingénieur qui va chercher les données avant de diagnostiquer.

---

## Conséquences

**Positives :**
- Diagnostics en français, compréhensibles par les techniciens OCP non-data
- Coût zéro pendant le stage (tier gratuit Google AI Studio)
- Adaptable sans recodage
- Extensible : ajouter un outil `get_maintenance_history()` sans changer l'architecture
- Migration vers Mistral (production OCP) = 1 ligne dans `.env`

**Négatives :**
- Latence : 2-5 secondes par analyse (vs <10ms pour le ML pur)
- Dépendance à une API externe (risque de downtime Google)
- Quota gratuit limité à 1 500 req/jour — suffisant pour le stage, pas pour la production

**Mitigation du risque API externe :**
```python
# Dans detection_agent.py — fallback si API down
try:
    decision = analyze_machine(machine_id)
except Exception:
    # Fallback : retourner uniquement le score ML sans diagnostic LLM
    decision = AgentDecision(severity=ml_severity, diagnosis="LLM unavailable — ML score only", ...)
```

---

## Quand revisiter

- **Déploiement OCP** → remplacer `ChatGoogleGenerativeAI` par `ChatMistralAI` (`mistral-large-latest`) et mettre la clé Bionic dans `.env`
- **Quota dépassé** (>1 500 analyses/jour) → passer au tier payant Gemini ou migrer vers Mistral
- **Temps de réponse < 1s requis** → pre-compute les analyses en batch la nuit
