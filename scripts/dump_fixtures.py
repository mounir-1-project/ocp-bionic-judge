"""
Capture les reponses reelles de l'API pour alimenter les bancs frontend.

Les bancs `frontend_smoke.mjs` et `twin_smoke.mjs` ne doivent pas s'appuyer sur
des donnees inventees : une reponse simulee a la main continue de passer quand
le contrat de l'API change, ce qui est exactement le defaut qu'on cherche a
eviter. Les fixtures sont donc extraites du service lui-meme.

Le rejeu est demarre puis arrete pendant la capture afin que le journal, le
diagnostic courant et l'etat de l'appareil soient reellement peuples.

Usage :
    python scripts/dump_fixtures.py [dossier]
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# LA CAPTURE SE FAIT EN MODE POSTE LOCAL, ET C'EST IMPOSE ICI.
#
# `AUTH_ENABLED` vaut par defaut `_registry_is_populated(...)` : il passe a vrai
# des qu'UN technicien est enregistre dans `data/runtime/operators.json`. Sur
# toute machine correctement configuree — c'est-a-dire la configuration que le
# projet recommande — ce script recevait donc `401 Unauthorized` des le premier
# appel, et la capture echouait.
#
# Le defaut ne se voyait que la ou un registre existe : ni en integration
# continue, qui part d'un depot vierge, ni dans l'environnement d'audit.
#
# Forcer la valeur n'est pas un contournement de securite : les fixtures
# alimentent des bancs qui verifient precisement que le poste propose une PRISE
# DE QUART DECLARATIVE. Capturees session ouverte, elles feraient tomber trois
# verifications. L'affectation precede l'import de `src.config`, et
# `load_dotenv()` n'ecrase pas une variable deja posee.
os.environ["AUTH_ENABLED"] = "false"

ROUTES: dict[str, str] = {
    "auth_status": "/api/auth/status",
    "equipment": "/api/equipment",
    "topology": "/api/topology",
    "health": "/api/health",
    "episodes": "/api/episodes?limit=200",
    "governance": "/api/governance",
    "sensor_health": "/api/sensor-health",
    "kpi": "/api/kpi",
    "validation": "/api/model/validation",
    "judge_eval": "/api/judge/evaluation?n_cases=4",
    "judge_audit": "/api/judge/audit",
    "timeseries": "/api/timeseries?max_points=650",
    "sensor_T_ACID_OUT": "/api/sensor/T_ACID_OUT?window_h=504",
    "coverage": "/api/coverage",
    "sensitivity": "/api/sensitivity",
    # Les deux surfaces que la vue Integrite expose desormais. Sans fixture,
    # `frontend_smoke` recevrait 404 et les panneaux resteraient vides sans
    # qu'aucun controle ne le signale.
    "alarms": "/api/alarms?active_only=false&limit=100",
    "workflow_templates": "/api/workflows/templates",
    "fouling_bench": "/api/detection/fouling-bench?severities=0.05,0.10,0.20,0.30&duration_days=60",
}

REPLAY_ROUTES: dict[str, str] = {
    "replay_state": "/api/replay/state",
    "stream": "/api/replay/stream?n=60",
    "alerts": "/api/replay/alerts?n=60",
}


def main() -> int:
    """Ecrit une fixture JSON par route dans le dossier demande."""
    from fastapi.testclient import TestClient

    from api.main import app

    out = Path(sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/api")
    out.mkdir(parents=True, exist_ok=True)

    with TestClient(app) as client:
        for name, path in ROUTES.items():
            response = client.get(path)
            response.raise_for_status()
            (out / f"{name}.json").write_text(
                json.dumps(response.json(), ensure_ascii=False), encoding="utf-8"
            )
            print(f"  {name:22s} {path}")

        # Le rejeu doit avoir tourne pour que le journal ne soit pas vide.
        client.post("/api/replay/start", json={"speed": 900})
        time.sleep(14)
        for name, path in REPLAY_ROUTES.items():
            response = client.get(path)
            response.raise_for_status()
            (out / f"{name}.json").write_text(
                json.dumps(response.json(), ensure_ascii=False), encoding="utf-8"
            )
            print(f"  {name:22s} {path}")
        client.post("/api/replay/stop")

    print(f"\n{len(ROUTES) + len(REPLAY_ROUTES)} fixtures ecrites dans {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
