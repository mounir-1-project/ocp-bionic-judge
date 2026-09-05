"""
Couche domaine — chargement et acces a la connaissance metier E7301.

Ce module est la SEULE porte d'entree vers `tags.yaml` et `amdec.yaml`.
Aucun seuil, aucun nom de tag, aucune criticite AMDEC ne doit etre code en dur
ailleurs dans le projet : tout passe par ici.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml

DOMAIN_DIR = Path(__file__).parent
TAGS_PATH = DOMAIN_DIR / "tags.yaml"
AMDEC_PATH = DOMAIN_DIR / "amdec.yaml"
TOPOLOGY_PATH = DOMAIN_DIR / "topology.yaml"


def seuil(valeur: float | None, defaut: float) -> float:
    """Retourne un seuil du referentiel, ou son repli si le champ est absent.

    Args:
        valeur: Seuil lu dans le referentiel, ou None s'il n'y figure pas.
        defaut: Valeur de secours.

    Returns:
        Le seuil effectif.
    """
    return defaut if valeur is None else float(valeur)


Role = Literal["primary", "secondary", "context", "degraded"]


# ── Modeles ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Tag:
    """Un point de mesure DCS et tout ce que le systeme sait a son sujet.

    Attributes:
        tag: Identifiant DCS brut (ex. 'S_MC_SULF_TI1100_B').
        alias: Nom court lisible utilise dans le code et l'UI (ex. 'T_ACID_IN').
        label: Libelle metier en francais.
        unit: Unite physique.
        kind: Nature du signal (temperature, flow, concentration, load...).
        role: primary = surveille, context = normalisation, degraded = capteur HS.
        confidence: Bases ayant servi a etablir le sens du tag.
        rationale: Justification de l'interpretation.
        spec: Dictionnaire brut complet issu du YAML (seuils, plages, etc.).
    """

    tag: str
    alias: str
    label: str
    unit: str
    kind: str
    role: Role
    confidence: str
    rationale: str
    spec: dict[str, Any] = field(repr=False, default_factory=dict)

    @property
    def range_operating(self) -> tuple[float, float] | None:
        r = self.spec.get("range_operating")
        return (float(r[0]), float(r[1])) if r else None

    @property
    def range_physical(self) -> tuple[float, float] | None:
        r = self.spec.get("range_physical")
        return (float(r[0]), float(r[1])) if r else None

    @property
    def control_band(self) -> tuple[float, float] | None:
        r = self.spec.get("control_band")
        return (float(r[0]), float(r[1])) if r else None

    @property
    def setpoint(self) -> float | None:
        v = self.spec.get("setpoint")
        return float(v) if v is not None else None

    @property
    def saturation_value(self) -> float | None:
        v = self.spec.get("saturation_value")
        return float(v) if v is not None else None

    def threshold(self, name: str) -> float | None:
        """Retourne un seuil d'alarme nomme."""
        v = self.spec.get(name)
        return float(v) if v is not None else None

    @property
    def criticality_link(self) -> str | None:
        """Mode de defaillance AMDEC auquel ce tag est rattache."""
        return self.spec.get("criticality_link")


@dataclass(frozen=True)
class FailureMode:
    """Un mode de defaillance AMDEC enrichi de sa signature dans les donnees.

    Attributes:
        code: Cle du mode (ex. 'FAISCEAU_BOUCHAGE').
        element: Composant concerne.
        mode: Libelle du mode de defaillance.
        causes: Causes recensees dans l'AMDEC.
        effet: Effet sur l'installation.
        F: Cotation frequence (1-10).
        G: Cotation gravite (1-10).
        N: Cotation non-detection (1-10).
        C: Criticite = F x G x N.
        action_corrective: Action prevue par l'AMDEC.
        plan_maintenance_ref: Taches du plan preventif associees (A..H).
        signature: Comment ce mode se manifeste dans les signaux DCS.
    """

    code: str
    element: str
    mode: str
    causes: list[str]
    effet: str
    F: int
    G: int
    N: int
    C: int
    action_corrective: str
    plan_maintenance_ref: list[str]
    signature: dict[str, Any] = field(repr=False, default_factory=dict)
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @property
    def observabilite(self) -> str:
        """Degre d'observabilite declare : `full`, `partial` ou `none`."""
        brut = self.signature.get("observable", bool(self.signature.get("indicators")))
        if brut is True:
            return "full"
        if brut is False:
            return "none"
        if isinstance(brut, str) and brut.lower() in {"full", "partial", "none"}:
            return brut.lower()
        raise ValueError(
            f"{self.code} : `observable` vaut {brut!r}. Valeurs admises : "
            f"true, false, 'partial'."
        )

    @property
    def observable(self) -> bool:
        """Vrai si ce mode est PLEINEMENT detectable par les signaux disponibles."""
        return self.observabilite == "full"

    @property
    def indicators(self) -> list[str]:
        """Indicateurs calcules qui portent la signature de ce mode."""
        return list(self.signature.get("indicators") or [])

    @property
    def immediate_severity(self) -> str | None:
        """Severite imposee d'office par l'AMDEC pour ce mode, si definie."""
        return self.signature.get("severite_immediate")

    def criticality_band(self) -> str:
        """Classe la criticite en bande lisible."""
        if self.C >= 100:
            return "MAJEURE"
        if self.C >= 60:
            return "SIGNIFICATIVE"
        return "MODEREE"


# ── Registre ──────────────────────────────────────────────────────────────────

class DomainKnowledge:
    """Agregat de toute la connaissance metier du refroidisseur E7301."""

    def __init__(
        self,
        tags_doc: dict,
        amdec_doc: dict,
        topology_doc: dict | None = None,
    ) -> None:
        self._tags_doc = tags_doc
        self._amdec_doc = amdec_doc
        self._topology_doc = topology_doc or {}

        self.equipment: dict[str, Any] = tags_doc["equipment"]
        self.quality_codes: dict[str, dict] = tags_doc.get("quality_codes", {})
        self.process_states: dict[str, dict] = tags_doc.get("process_states", {})

        # Chargement des tags
        self.tags: dict[str, Tag] = {}
        for tag_id, spec in tags_doc["tags"].items():
            spec = dict(spec)
            self.tags[tag_id] = Tag(
                tag=tag_id,
                alias=spec["alias"],
                label=spec.get("label", tag_id),
                unit=spec.get("unit", "-"),
                kind=spec.get("kind", "unknown"),
                role=spec.get("role", "context"),
                confidence=",".join(spec.get("basis", ["data"])),
                rationale=(spec.get("evidence") or spec.get("rationale") or "").strip(),
                spec=spec,
            )
        self.by_alias: dict[str, Tag] = {t.alias: t for t in self.tags.values()}

        # Chargement des modes AMDEC
        self.modes: dict[str, FailureMode] = {}
        observabilites_admises = {"full", "partial", "none"}
        for code, m in amdec_doc["modes"].items():
            signature = m.get("signature") or {}
            brut = signature.get("observable", bool(signature.get("indicators")))
            normalise = (
                "full" if brut is True
                else "none" if brut is False
                else str(brut).lower() if isinstance(brut, str)
                else brut
            )
            if normalise not in observabilites_admises:
                raise ValueError(
                    f"{code} : `signature.observable` vaut {brut!r}. "
                    f"Valeurs admises : true, false, 'partial'."
                )
            self.modes[code] = FailureMode(
                code=code,
                element=m.get("element", ""),
                mode=m.get("mode", ""),
                causes=list(m.get("causes") or []),
                effet=m.get("effet", ""),
                F=int(m["F"]), G=int(m["G"]), N=int(m["N"]), C=int(m["C"]),
                action_corrective=m.get("action_corrective", ""),
                plan_maintenance_ref=list(m.get("plan_maintenance_ref") or []),
                signature=m.get("signature") or {},
                raw=m,
            )

        self.plan_maintenance: dict[str, dict] = amdec_doc.get("plan_maintenance", {})

        # Topologie physique
        topo = self._topology_doc
        self.topology_meta: dict[str, Any] = topo.get("meta", {})
        self.components: dict[str, dict] = topo.get("components", {})
        self.sensor_placements: dict[str, dict] = topo.get("sensors", {})
        self.finding_map: dict[str, dict] = topo.get("finding_map", {})

    # ── Topologie ────────────────────────────────────────────────────────────

    def locate_finding(self, code: str) -> dict[str, list[str]]:
        """Pieces et capteurs concernes par un code de regle."""
        entry = self.finding_map.get(code) or {}
        return {
            "components": list(entry.get("components") or []),
            "sensors": list(entry.get("sensors") or []),
        }

    def modes_for_component(self, component_code: str) -> set[str]:
        """Modes de defaillance portes par une piece physique."""
        return set((self.components.get(component_code) or {}).get("amdec_modes") or [])

    def topology(self) -> dict[str, Any]:
        """Topologie complete pour la representation 3D."""
        sensors = []
        for alias, placement in self.sensor_placements.items():
            tag = self.by_alias.get(alias)
            if tag is None:
                continue
            sensors.append({
                "alias": alias,
                "tag": tag.tag,
                "label": tag.label,
                "unit": tag.unit,
                "kind": tag.kind,
                "role": tag.role,
                "confidence": tag.confidence,
                "range_operating": tag.range_operating,
                "setpoint": tag.setpoint,
                "alarm_high": tag.threshold("alarm_high"),
                "alarm_high_high": tag.threshold("alarm_high_high"),
                "alarm_low": tag.threshold("alarm_low"),
                "alarm_low_low": tag.threshold("alarm_low_low"),
                "criticality_link": tag.criticality_link,
                "at": list(placement.get("at") or [0, 0, 0]),
                "attaches_to": placement.get("attaches_to", ""),
                "anchor": placement.get("anchor", "up"),
                "placement": placement.get("placement", ""),
            })
        components = []
        for code, spec in self.components.items():
            modes = spec.get("amdec_modes") or []
            components.append({
                "code": code,
                "label": spec.get("label", code),
                "fluide": spec.get("fluide", ""),
                "description": (spec.get("description") or "").strip(),
                "amdec_modes": modes,
                "criticite_max": max(
                    (self.modes[m].C for m in modes if m in self.modes), default=0
                ),
                "inspection": spec.get("inspection", ""),
                "instrumented": bool(spec.get("instrumented", True)),
            })
        return {
            "meta": self.topology_meta,
            "components": components,
            "sensors": sensors,
            "finding_map": self.finding_map,
        }

    # ── Selecteurs de tags ───────────────────────────────────────────────────

    def tags_by_role(self, *roles: str) -> list[Tag]:
        """Tags filtres par role."""
        return [t for t in self.tags.values() if t.role in roles]

    @property
    def monitored_tags(self) -> list[Tag]:
        """Tags reellement surveilles : primary + secondary."""
        return self.tags_by_role("primary", "secondary")

    @property
    def model_tags(self) -> list[Tag]:
        """Tags autorises en entree du modele ML."""
        return self.tags_by_role("primary", "secondary", "context")

    def alias_map(self) -> dict[str, str]:
        """Mapping {tag DCS brut -> alias court} pour renommer un DataFrame."""
        return {t.tag: t.alias for t in self.tags.values()}

    def get(self, key: str) -> Tag:
        """Recupere un tag par identifiant DCS ou par alias."""
        if key in self.tags:
            return self.tags[key]
        if key in self.by_alias:
            return self.by_alias[key]
        raise KeyError(f"Tag inconnu: {key}")

    # ── Selecteurs AMDEC ─────────────────────────────────────────────────────

    def observable_modes(self) -> list[FailureMode]:
        """Modes de defaillance detectables depuis les signaux disponibles."""
        return [m for m in self.modes.values() if m.observable]

    def blind_spots(self) -> list[FailureMode]:
        """Modes dont AUCUNE mesure ne dit rien."""
        return [m for m in self.modes.values() if m.observabilite == "none"]

    def partially_observable_modes(self) -> list[FailureMode]:
        """Modes dont le systeme observe les conditions, jamais l'etat."""
        return [m for m in self.modes.values() if m.observabilite == "partial"]

    def modes_ranked(self) -> list[FailureMode]:
        """Modes tries par criticite AMDEC decroissante."""
        return sorted(self.modes.values(), key=lambda m: m.C, reverse=True)

    def maintenance_task(self, ref: str) -> dict | None:
        """Tache du plan preventif par reference ('A'..'H')."""
        return self.plan_maintenance.get(ref)

    def task_requires_shutdown(self, ref: str | None) -> bool:
        """La tache exige-t-elle l'arret et la consignation de la ligne ?"""
        if not ref:
            return False
        task = self.plan_maintenance.get(ref)
        if not task:
            return False
        etat = unicodedata.normalize("NFKD", str(task.get("etat", "")))
        etat = etat.encode("ascii", "ignore").decode("ascii").casefold()
        return "arret" in etat

    def risk_coverage(self) -> dict[str, Any]:
        """Part de la criticite AMDEC reellement couverte par les donnees."""
        covered: list[dict[str, Any]] = []
        partial: list[dict[str, Any]] = []
        blind: list[dict[str, Any]] = []
        for mode in self.modes_ranked():
            row = {
                "code": mode.code,
                "element": mode.element,
                "mode": mode.mode,
                "criticite": mode.C,
                "observabilite": mode.observabilite,
                "taches_preventives": mode.plan_maintenance_ref,
            }
            {"full": covered, "partial": partial, "none": blind}[
                mode.observabilite
            ].append(row)

        total = sum(m["criticite"] for m in covered + partial + blind)
        covered_c = sum(m["criticite"] for m in covered)
        partial_c = sum(m["criticite"] for m in partial)
        return {
            "criticite_totale": total,
            "criticite_couverte": covered_c,
            "criticite_partielle": partial_c,
            "criticite_non_couverte": total - covered_c - partial_c,
            "part_couverte_pct": round(100.0 * covered_c / total, 1) if total else 0.0,
            "part_partielle_pct": round(100.0 * partial_c / total, 1) if total else 0.0,
            "n_modes_couverts": len(covered),
            "n_modes_partiels": len(partial),
            "n_modes_aveugles": len(blind),
            "modes_partiels": partial,
            "modes_aveugles": blind,
        }

    def determination_basis(self) -> dict[str, Any]:
        """Sur quoi repose le sens attribue a chaque tag."""
        counts: dict[str, int] = {}
        detail: list[dict[str, Any]] = []
        for tag in self.tags.values():
            bases = [b for b in tag.confidence.split(",") if b]
            for basis in bases:
                counts[basis] = counts.get(basis, 0) + 1
            detail.append({
                "alias": tag.alias,
                "tag": tag.tag,
                "label": tag.label,
                "role": tag.role,
                "basis": bases,
                "n_basis": len(bases),
            })
        scope = self.monitored_tags
        return {
            "n_total": len(self.tags),
            "perimetre_surveille": len(scope),
            "par_base": dict(sorted(counts.items())),
            "detail": sorted(detail, key=lambda d: d["alias"]),
        }


# ── Chargement ────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_domain(
    tags_path: str | Path = TAGS_PATH,
    amdec_path: str | Path = AMDEC_PATH,
    topology_path: str | Path = TOPOLOGY_PATH,
) -> DomainKnowledge:
    """Charge (et met en cache) la connaissance domaine depuis les YAML.

    Args:
        tags_path: Chemin de tags.yaml.
        amdec_path: Chemin de amdec.yaml.
        topology_path: Chemin de topology.yaml.

    Returns:
        Instance DomainKnowledge prete a l'emploi.
    """
    tags_path, amdec_path = Path(tags_path), Path(amdec_path)
    for p in (tags_path, amdec_path):
        if not p.exists():
            raise FileNotFoundError(f"Fichier domaine introuvable: {p}")
    with tags_path.open(encoding="utf-8") as f:
        tags_doc = yaml.safe_load(f)
    with amdec_path.open(encoding="utf-8") as f:
        amdec_doc = yaml.safe_load(f)

    topology_doc: dict = {}
    topology_path = Path(topology_path)
    if topology_path.exists():
        with topology_path.open(encoding="utf-8") as f:
            topology_doc = yaml.safe_load(f) or {}

    return DomainKnowledge(tags_doc, amdec_doc, topology_doc)


if __name__ == "__main__":
    d = load_domain()
    print(f"Equipement: {d.equipment['name']}")
    print(f"Tags: {len(d.tags)}")
    print(f"Modes AMDEC: {len(d.modes)}")
