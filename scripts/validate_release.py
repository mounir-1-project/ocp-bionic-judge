"""Génère les preuves de validation et l'artefact candidat reproductible."""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import REPORT_DIR
from src.governance.lineage import failed_mandatory_gates
from src.pipeline import E7301Pipeline


def main() -> int:
    pipeline = E7301Pipeline(use_llm=False)
    validation = pipeline.validation_report()
    # REPORT_DIR ETAIT DECLARE ET JAMAIS LU.
    # Ce script ecrivait `Path("reports")` en dur, donc relativement au
    # repertoire courant : la sortie changeait d'emplacement selon l'endroit
    # d'ou la commande etait lancee, et la variable de configuration prevue
    # pour la deplacer n'avait aucun effet.
    report_dir = REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)
    target = report_dir / "model_validation.json"
    target.write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    model = pipeline.save_model()
    print(f"Validation : {target}")
    print(f"Modèle candidat : {model}")
    print(f"Manifeste : {model.with_suffix('.manifest.json')}")
    failed = failed_mandatory_gates(validation)
    if failed:
        print(
            "PROMOTION REFUSÉE — portes obligatoires en échec : "
            + ", ".join(failed)
            + "\nL'artefact reste candidat. La promotion s'effectue ensuite par "
            "`python scripts/promote_model.py --statut <statut> --par <identité>`.",
            file=sys.stderr,
        )
        return 2
    print(
        "Portes obligatoires franchies. L'artefact reste néanmoins CANDIDAT : "
        "produire n'est pas promouvoir.\nPromotion explicite : "
        "`python scripts/promote_model.py --statut shadow_only --par <identité>`."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
