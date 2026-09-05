"""Templates de workflows pour inspections E7301.

Version simplifiee : retourne les templates predefinis.
Le frontend ne lit que /api/workflows/templates.
"""

from __future__ import annotations

from typing import Any


# Templates predefinis pour les inspections du refroidisseur E7301
WORKFLOW_TEMPLATES: dict[str, dict[str, Any]] = {
    "inspection_visuelle": {
        "id": "inspection_visuelle",
        "title": "Inspection visuelle du refroidisseur",
        "equipment_id": "S-PC-E7301",
        "description": "Inspection visuelle periodique du faisceau et de la coque",
        "steps": [
            {
                "code": "IV-01",
                "label": "Arreter la ligne si necessaire",
                "source_ref": "Gamme PV E7301",
                "dangerous": False,
            },
            {
                "code": "IV-02",
                "label": "Verifier l'etat des jointures",
                "source_ref": "Check-list INSPECTION",
                "dangerous": False,
            },
            {
                "code": "IV-03",
                "label": "Verifier les fuites evidentes",
                "source_ref": "Check-list INSPECTION",
                "dangerous": False,
            },
            {
                "code": "IV-04",
                "label": "Mesurer l'epaisseur des tubes",
                "source_ref": "Gamme PV E7301",
                "dangerous": True,
            },
        ],
    },
    "tamponnage": {
        "id": "tamponnage",
        "title": "Tamponnage des tubes",
        "equipment_id": "S-PC-E7301",
        "description": "Tamponnage des tubes endommages du faisceau",
        "steps": [
            {
                "code": "TN-01",
                "label": "Arreter la ligne et isoler",
                "source_ref": "Gamme de tamponnage",
                "dangerous": True,
            },
            {
                "code": "TN-02",
                "label": "Vider et rincer le faisceau",
                "source_ref": "Gamme de tamponnage",
                "dangerous": True,
            },
            {
                "code": "TN-03",
                "label": "Identifier les tubes a boucher",
                "source_ref": "Gamme de tamponnage",
                "dangerous": False,
            },
            {
                "code": "TN-04",
                "label": "Inserer les tampons",
                "source_ref": "Gamme de tamponnage",
                "dangerous": False,
            },
            {
                "code": "TN-05",
                "label": "Remise en service et controle",
                "source_ref": "Gamme PV E7301",
                "dangerous": True,
            },
        ],
    },
    "mesure_epaisseur": {
        "id": "mesure_epaisseur",
        "title": "Mesure d'epaisseur des tubes",
        "equipment_id": "S-PC-E7301",
        "description": "Mesure ultrasonique de l'epaisseur des tubes",
        "steps": [
            {
                "code": "ME-01",
                "label": "Preparer le materiel de mesure",
                "source_ref": "Gamme PV E7301",
                "dangerous": False,
            },
            {
                "code": "ME-02",
                "label": "Mesurer les tubes critiques",
                "source_ref": "Gamme PV E7301",
                "dangerous": False,
            },
            {
                "code": "ME-03",
                "label": "Enregistrer les resultats",
                "source_ref": "Gamme PV E7301",
                "dangerous": False,
            },
        ],
    },
}


class WorkflowStore:
    """Retourne les templates de workflows predefinis."""

    def get_templates(self) -> dict[str, dict[str, Any]]:
        """Retourne tous les templates disponibles."""
        return WORKFLOW_TEMPLATES

    def close(self) -> None:
        """Rien a fermer."""
        pass
