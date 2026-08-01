"""Génère les preuves de validation et l'artefact candidat reproductible."""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import REPORT_DIR
from src.governance.lineage import failed_mandatory_gates, failed_software_gates
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
    # LE CODE DE RETOUR PORTE SUR CE QU'UN COMMIT PEUT CASSER, PAS SUR CE
    # QU'OCP N'A PAS FOURNI.
    #
    # Il portait sur les cinq portes de promotion, dont `labels_gmao` et
    # `validation_externe` qui exigent un historique de pannes étiqueté. Ce
    # script étant appelé par l'intégration continue sans `continue-on-error`,
    # le job `tests` échouait à chaque exécution et le job `image`, qui en
    # dépend, n'était jamais construit. La chaîne était rouge par construction
    # et aucun commit ne pouvait la rendre verte.
    #
    # Les deux listes sont désormais publiées l'une et l'autre : le lecteur voit
    # l'état réel des cinq portes, et seules les trois portes logicielles
    # décident du code de retour. La promotion, elle, continue d'exiger les cinq
    # — `promote_model.py` et `validate_model_manifest` sont inchangés.
    bloquantes = failed_software_gates(validation)
    promotion = failed_mandatory_gates(validation)
    externes = [gate for gate in promotion if gate not in bloquantes]

    if externes:
        print(
            "Portes en attente de données OCP (non bloquantes) : "
            + ", ".join(externes)
            + "\n  Elles exigent un historique de pannes étiqueté et une "
            "validation hors site. Aucun commit ne peut les franchir."
        )
    if bloquantes:
        print(
            "ÉCHEC — portes logicielles en échec : "
            + ", ".join(bloquantes)
            + "\nCe sont les propriétés qu'une modification de code peut casser. "
            "Corriger avant de fusionner.",
            file=sys.stderr,
        )
        return 2

    print("Portes logicielles franchies.")
    if promotion:
        print(
            "L'artefact reste CANDIDAT : "
            + ", ".join(promotion)
            + " ne sont pas franchies. La promotion est légitimement impossible "
            "sur ce corpus, et c'est le résultat attendu."
        )
    else:
        print(
            "Portes de promotion franchies. L'artefact reste néanmoins "
            "CANDIDAT : produire n'est pas promouvoir.\nPromotion explicite : "
            "`python scripts/promote_model.py --statut shadow_only --par <identité>`."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
