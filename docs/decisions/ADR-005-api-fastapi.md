# ADR-005 — API REST : FastAPI

**Statut** : Accepté  
**Date** : 2024-02-05  

---

## Décision

Utiliser **FastAPI** pour exposer le pipeline via une API REST.

## Alternatives évaluées

| Framework | Évaluation | Verdict |
|-----------|-----------|---------|
| **FastAPI** | Async natif, validation Pydantic intégrée, Swagger auto-généré, le plus rapide des frameworks Python | ✅ Choisi |
| Flask | Simple, mais synchrone, pas de validation native, pas de Swagger auto | ❌ |
| Django REST | Puissant mais lourd pour une API ML, courbe d'apprentissage élevée | ❌ |
| gRPC | Performant pour microservices mais complexe, pas d'interface browser | ❌ |

## Pourquoi FastAPI est supérieur à Flask pour ce cas

```python
# Flask — validation manuelle, pas de Swagger
@app.route("/decisions", methods=["GET"])
def get_decisions():
    machine_id = request.args.get("machine_id")  # pas de type, pas de validation
    limit = int(request.args.get("limit", 50))   # crash si non-int
    return jsonify(results)

# FastAPI — validation automatique, Swagger auto-généré
@app.get("/decisions", response_model=list[DecisionRecord])
async def get_decisions(
    machine_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),  # validé automatiquement
):
    ...
```

## Quand revisiter

- Si l'équipe préfère JavaScript → remplacer par Express.js (Node)
- Si performance critique (>10k req/s) → envisager Rust (Axum) ou Go (Gin)
