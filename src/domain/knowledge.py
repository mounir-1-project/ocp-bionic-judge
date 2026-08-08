"""
Couche domaine — chargement et acces a la connaissance metier E7301.

Ce module est la SEULE porte d'entree vers `tags.yaml` et `amdec.yaml`.
Aucun seuil, aucun nom de tag, aucune criticite AMDEC ne doit etre code en dur
ailleurs dans le projet : tout passe par ici. C'est ce qui permet de corriger
une determination metier sans toucher au code.

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

    LE REPLI TESTE L'ABSENCE, PAS LA FAUSSETE.
    L'idiome `tag.threshold(...) or <defaut>` remplacait un seuil legitimement
    nul par la valeur de secours : un debit d'arret a 0 m3/h se serait
    transforme en 20 m3/h, un titre a 0 % en 97 %, sans le moindre
    avertissement. Il etait employe a douze endroits de la chaine.

    Cette fonction vit dans la couche domaine parce que l'ingestion et le
    moteur de regles en dependent tous deux : la placer dans l'un des deux
    aurait fait dependre la detection de l'ingestion pour un utilitaire qui
    n'appartient ni a l'une ni a l'autre.

    Args:
        valeur: Seuil lu dans le referentiel, ou None s'il n'y figure pas.
        defaut: Valeur de secours.

    Returns:
        Le seuil effectif.
    """
    return defaut if valeur is None else float(valeur)


Role = Literal["primary", "secondary", "context", "degraded"]
DeterminationBasis = Literal["isa_5_1", "process", "data", "stoichio", "climatology"]
ProvenanceCategory = Literal[
    "ocp_source",
    "derived_rule",
    "application_rule",
    "hypothesis",
    "field_validated",
]


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
        confidence: Bases ayant servi a etablir le sens du tag, separees
            par des virgules (isa_5_1, process, data, stoichio).
        rationale: Justification de l'interpretation — tracabilite obligatoire.
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

    # ── Plages et seuils ─────────────────────────────────────────────────────
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
        """Retourne un seuil d'alarme nomme.

        Args:
            name: 'alarm_high', 'alarm_high_high', 'alarm_low', 'alarm_low_low'.

        Returns:
            La valeur du seuil, ou None s'il n'est pas defini pour ce tag.
        """
        v = self.spec.get(name)
        return float(v) if v is not None else None

    @property
    def criticality_link(self) -> str | None:
        """Mode de defaillance AMDEC auquel ce tag est rattache."""
        return self.spec.get("criticality_link")

    @property
    def governance(self) -> dict[str, Any]:
        """Métadonnées de gouvernance résolues avec les valeurs par défaut."""
        return dict(self.spec.get("_governance") or {})

    # `is_out_of_physical_range(value)` A ETE SUPPRIMEE.
    #
    # Elle reimplementait, valeur par valeur, une regle deja appliquee de
    # maniere vectorielle par l'ingestion (`dcs_loader._sensor_faults`, motif
    # `OUT_OF_RANGE`), et personne ne l'appelait. Deux ecritures d'une meme
    # regle metier finissent toujours par diverger, et c'est celle qui ne sert
    # a rien qui derive en premier, faute de test pour la retenir. La plage
    # physique reste lisible via `range_physical`.


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
    provenance_category: ProvenanceCategory
    source_file: str
    source_location: str
    original_values: dict[str, Any] = field(repr=False, default_factory=dict)
    transformations: list[str] = field(repr=False, default_factory=list)
    validation_status: str = "unknown"
    validation_owner: str = ""
    signature: dict[str, Any] = field(repr=False, default_factory=dict)
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @property
    def observabilite(self) -> str:
        """Degre d'observabilite declare : `full`, `partial` ou `none`.

        UNE COERCITION SILENCIEUSE CORRIGEE.
        Le referentiel declare `observable: partial` pour CALANDRE_FUITE — une
        fuite de calandre se devine par une perte de debit, elle ne se mesure
        pas. Or le code lisait `bool(self.signature.get("observable", ...))`, et
        `bool("partial")` vaut `True` : une valeur ecrite pour signifier
        « partiellement » etait lue comme « entierement », sans avertissement.
        La couverture publiee du risque AMDEC s'en trouvait surevaluee.

        Les trois etats sont desormais distincts, et toute autre valeur est
        refusee au chargement plutot que coercee.

        Returns:
            `'full'`, `'partial'` ou `'none'`.

        Raises:
            ValueError: Si le referentiel declare une valeur non reconnue.
        """
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
        """Vrai si ce mode est PLEINEMENT detectable par les signaux disponibles.

        Critique pour le Judge : un diagnostic qui pretend detecter un mode
        NON observable (ex. anode sacrificielle) est une hallucination.

        Un mode `partial` n'est PAS compte comme observable : la couverture du
        risque doit se lire comme un plancher, jamais comme une promesse.
        """
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
        """Classe la criticite en bande lisible.

        Returns:
            'MAJEURE' (C >= 100), 'SIGNIFICATIVE' (C >= 60), sinon 'MODEREE'.
        """
        if self.C >= 100:
            return "MAJEURE"
        if self.C >= 60:
            return "SIGNIFICATIVE"
        return "MODEREE"


# ── Registre ──────────────────────────────────────────────────────────────────

class DomainKnowledge:
    """Agregat immuable de toute la connaissance metier du refroidisseur E7301."""

    def __init__(
        self,
        tags_doc: dict,
        amdec_doc: dict,
        topology_doc: dict | None = None,
    ) -> None:
        """Construit le registre a partir des documents YAML gouvernes.

        Args:
            tags_doc: Contenu de tags.yaml.
            amdec_doc: Contenu de amdec.yaml.
            topology_doc: Contenu de topology.yaml — rattachement des capteurs
                et des codes de regle aux pieces physiques. Optionnel : le
                systeme fonctionne sans, mais l'interface 3D perd son ancrage.
        """
        self._tags_doc = tags_doc
        self._amdec_doc = amdec_doc
        self._topology_doc = topology_doc or {}

        self.equipment: dict[str, Any] = tags_doc["equipment"]
        self.quality_codes: dict[str, dict] = tags_doc.get("quality_codes", {})
        self.process_states: dict[str, dict] = tags_doc.get("process_states", {})
        self.tag_registry_history: list[dict] = tags_doc.get(
            "registry_change_history", []
        )
        governance_defaults = tags_doc.get("governance_defaults", {})

        self.tags: dict[str, Tag] = {}
        for tag_id, spec in tags_doc["tags"].items():
            spec = dict(spec)
            spec["_governance"] = {
                **governance_defaults,
                **{
                    key: spec[key]
                    for key in (
                        "source_file", "source_location", "source_sha256",
                        "sampling_frequency", "validation_status",
                        "business_owner", "quality_rules",
                    )
                    if key in spec
                },
            }
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

        self.modes: dict[str, FailureMode] = {}
        observabilites_admises = {"full", "partial", "none"}
        for code, m in amdec_doc["modes"].items():
            # L'OBSERVABILITE EST VALIDEE AU CHARGEMENT, PAS AU PREMIER ACCES.
            # Le controle vivait dans la propriete `observabilite` : une valeur
            # fautive dans le YAML ne levait qu'au moment ou un appelant la
            # lisait, potentiellement au fond d'une requete HTTP en production.
            # Une erreur de saisie du referentiel doit arreter le chargement.
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
            provenance = m.get("provenance") or {}
            self.modes[code] = FailureMode(
                code=code,
                element=m.get("element", ""),
                mode=m.get("mode", ""),
                causes=list(m.get("causes") or []),
                effet=m.get("effet", ""),
                F=int(m["F"]), G=int(m["G"]), N=int(m["N"]), C=int(m["C"]),
                action_corrective=m.get("action_corrective", ""),
                plan_maintenance_ref=list(m.get("plan_maintenance_ref") or []),
                provenance_category=provenance.get("category", "hypothesis"),
                source_file=provenance.get("source_file", ""),
                source_location=provenance.get("source_location", ""),
                original_values=dict(provenance.get("original_values") or {}),
                transformations=list(provenance.get("transformations") or []),
                validation_status=provenance.get("validation_status", "unknown"),
                validation_owner=provenance.get("validation_owner", ""),
                signature=m.get("signature") or {},
                raw=m,
            )

        self.plan_maintenance: dict[str, dict] = amdec_doc.get("plan_maintenance", {})
        self.gammes: dict[str, dict] = amdec_doc.get("gammes", {})
        self.checklists: dict[str, dict] = amdec_doc.get("checklists", {})
        self.bareme_gravite: dict[int, str] = amdec_doc.get("bareme_gravite", {})
        self.bareme_frequence: dict[int, dict] = amdec_doc.get("bareme_frequence", {})
        self.bareme_detection: dict[int, str] = amdec_doc.get("bareme_detection", {})

        # ── Topologie physique ───────────────────────────────────────────────
        topo = self._topology_doc
        self.topology_meta: dict[str, Any] = topo.get("meta", {})
        self.components: dict[str, dict] = topo.get("components", {})
        self.sensor_placements: dict[str, dict] = topo.get("sensors", {})
        self.finding_map: dict[str, dict] = topo.get("finding_map", {})

    # ── Topologie ────────────────────────────────────────────────────────────

    def locate_finding(self, code: str) -> dict[str, list[str]]:
        """Pieces et capteurs concernes par un code de regle.

        Remplace la recherche de sous-chaine qui existait cote interface. Un
        code inconnu ne designe rien : mieux vaut n'allumer aucune piece que
        d'en accuser une mauvaise.

        Args:
            code: Code emis par le detecteur, ex. 'CONC_DROP_SEVERE'.

        Returns:
            Dictionnaire {'components': [...], 'sensors': [...]}.
        """
        entry = self.finding_map.get(code) or {}
        return {
            "components": list(entry.get("components") or []),
            "sensors": list(entry.get("sensors") or []),
        }

    def modes_for_component(self, component_code: str) -> set[str]:
        """Modes de defaillance portes par une piece physique.

        Elle existe parce que le controleur de coherence avait besoin de
        l'ensemble des modes affectant la surface d'echange et l'ecrivait en
        dur : l'ajout d'un mode dans le referentiel ne l'aurait pas rejoint.

        Args:
            component_code: Code de piece, ex. 'BUNDLE'.

        Returns:
            Codes des modes rattaches, ensemble vide si la piece est inconnue.
        """
        return set((self.components.get(component_code) or {}).get("amdec_modes") or [])

    # `components_for_mode(mode_code)` A ETE SUPPRIMEE.
    #
    # Elle parcourait la topologie dans le sens mode -> pieces. Aucun appelant,
    # aucun test : la seule direction reellement empruntee est la reciproque
    # ci-dessus, `modes_for_component`, qu'utilise le controleur de coherence
    # du Judge. La liste des pieces d'un mode reste lisible par l'interface,
    # qui recoit `components[].amdec_modes` dans `topology()`.
    #
    # Meme motif que pour `is_out_of_physical_range` et `mode_for_indicator`,
    # deja retirees : une seconde facon de repondre a la question, sans test
    # pour la retenir, derive avant celle qui sert.

    def risk_coverage(self) -> dict[str, Any]:
        """Part de la criticite AMDEC reellement couverte par les donnees.

        INDICATEUR AJOUTE APRES AUDIT. Le projet declarait ses angles morts un
        par un, mais ne disait nulle part quelle FRACTION du risque il couvre.
        Or les deux modes les plus critiques de l'equipement — plaque
        sacrificielle et fuite de vanne d'acide, criticite 112 chacun — ne sont
        pas instrumentes. Sans ce ratio, un lecteur presse conclut que la
        surveillance par donnees traite le risque; elle n'en traite qu'une part.

        Returns:
            Criticite couverte, non couverte, ratio et detail par mode.
        """
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
            # LA COUVERTURE PARTIELLE EST COMPTEE A PART, JAMAIS DANS LA
            # COUVERTURE. Un mode dont on observe les conditions favorisantes
            # mais pas l'etat — la corrosion du faisceau, la fuite de calandre —
            # ne peut pas etre presente comme couvert : ce serait promettre une
            # detection que le systeme ne peut pas tenir. Il est publie
            # separement pour ne pas etre confondu avec un angle mort complet.
            "criticite_partielle": partial_c,
            "criticite_non_couverte": total - covered_c - partial_c,
            "part_couverte_pct": round(100.0 * covered_c / total, 1) if total else 0.0,
            "part_partielle_pct": round(100.0 * partial_c / total, 1) if total else 0.0,
            "n_modes_couverts": len(covered),
            "n_modes_partiels": len(partial),
            "n_modes_aveugles": len(blind),
            "modes_partiels": partial,
            "modes_aveugles": blind,
            "reading": (
                "La part non couverte reste sous la responsabilite du plan "
                "preventif A-H et de l'inspection : la surveillance par donnees "
                "ne s'y substitue pas. La part PARTIELLE designe les modes dont "
                "le systeme observe les conditions favorisantes sans mesurer "
                "l'etat de la piece — corrosion du faisceau, fuite de calandre. "
                "Elle n'est pas comptee comme couverte, parce qu'une condition "
                "surveillee n'est pas une defaillance detectee."
            ),
        }

    def determination_basis(self) -> dict[str, Any]:
        """Sur quoi repose le sens attribue a chaque tag.

        Le systeme ne dispose d'aucune fiche d'instrumentation : le sens des
        douze tags a ete ETABLI par recoupement. Cette methode publie le
        detail, afin qu'un lecteur puisse contester une determination precise
        plutot que de douter de l'ensemble.

        Les quatre bases sont :
          isa_5_1   nomenclature instrumentation (TI, FI, AI, PHI)
          process   physique du procede sulfurique et donnees Chemetics
          data      comportement observe sur 10 180 heures
          stoichio  coherence stoechiometrique de la ligne

        Returns:
            Repartition par base et detail par tag.
        """
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
            "methode": (
                "Aucune fiche d'instrumentation n'accompagne l'export DCS. Le "
                "sens de chaque tag est etabli par recoupement d'au moins deux "
                "bases independantes, et le detail de chaque determination "
                "figure dans src/domain/tags.yaml."
            ),
        }

    def topology(self) -> dict[str, Any]:
        """Topologie complete, enrichie des metadonnees de chaque tag.

        C'est le contrat consomme par la representation 3D : chaque capteur y
        porte sa position, la piece qu'il surveille, son unite, sa plage
        d'exploitation, sa consigne et son niveau de confiance.

        Returns:
            Dictionnaire serialisable.
        """
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
                # Le mode AMDEC que ce capteur sert a surveiller. Le contrat 3D
                # portait deja la piece et ses modes; il ne disait pas pourquoi
                # tel capteur est place la. `tags.yaml` le dit depuis toujours.
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
        """Tags filtres par role.

        Args:
            *roles: Un ou plusieurs roles ('primary', 'context', ...).

        Returns:
            Liste de Tag.
        """
        return [t for t in self.tags.values() if t.role in roles]

    @property
    def monitored_tags(self) -> list[Tag]:
        """Tags reellement surveilles : primary + secondary (les 'degraded' sont exclus)."""
        return self.tags_by_role("primary", "secondary")

    @property
    def model_tags(self) -> list[Tag]:
        """Tags autorises en entree du modele ML.

        Les capteurs `degraded` (TI5303-4X sature, PHI5306X-3 fige) sont exclus :
        entrainer un modele dessus revient a apprendre du bruit d'instrumentation.
        """
        return self.tags_by_role("primary", "secondary", "context")

    def alias_map(self) -> dict[str, str]:
        """Mapping {tag DCS brut -> alias court} pour renommer un DataFrame."""
        return {t.tag: t.alias for t in self.tags.values()}

    def get(self, key: str) -> Tag:
        """Recupere un tag par identifiant DCS ou par alias.

        Args:
            key: 'S_MC_SULF_TI1100_B' ou 'T_ACID_IN'.

        Returns:
            Le Tag correspondant.

        Raises:
            KeyError: Si aucun tag ne correspond.
        """
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
        """Modes dont AUCUNE mesure ne dit rien — angles morts au sens strict.

        UNE DEFINITION, PAS DEUX. Cette methode retournait `not m.observable`,
        c'est-a-dire tout ce qui n'est pas `full` — donc aussi les modes
        `partial`. `risk_coverage()` les comptait separement. La meme classe
        portait deux definitions de « angle mort », et l'ecart se lisait a
        l'ecran : le tableau AMDEC affichait « non — angle mort » pour la
        corrosion du faisceau et la fuite de calandre, deux modes auxquels le
        moteur de regles rattache activement des constatations
        (`CONC_LOW`, `T_IN_HIGH*`, `FLOW_LOW*`). Le prompt de l'agent leur
        interdisait par ailleurs tout diagnostic que les regles produisaient.

        Un angle mort est un mode qu'aucun signal ne touche. Un mode dont on
        observe un symptome sans mesurer l'etat de la piece est `partial` :
        voir `partially_observable_modes`.

        Les declarer explicitement est une exigence de gouvernance : un systeme
        de surveillance qui ne dit pas ce qu'il ne voit pas donne une fausse
        assurance a l'exploitant.
        """
        return [m for m in self.modes.values() if m.observabilite == "none"]

    def partially_observable_modes(self) -> list[FailureMode]:
        """Modes dont le systeme observe les conditions, jamais l'etat.

        La corrosion du faisceau se lit par l'exposition cumulee, pas par
        l'amincissement des tubes; une fuite de calandre se devine par une
        perte de debit, elle ne se mesure pas. Invoquer ces modes sur la foi
        de leur symptome est legitime — c'est ce que fait le moteur de regles.
        Les compter comme couverts serait une sur-vente; les compter comme
        aveugles effacerait la surveillance reelle qui existe.
        """
        return [m for m in self.modes.values() if m.observabilite == "partial"]

    # `mode_for_indicator(indicator)` A ETE SUPPRIMEE : aucun appelant, aucun
    # test, et un rattachement d'indicateur a un mode qui n'etait la source de
    # verite de rien. Le rattachement effectif se fait par `_MODE_BY_RESIDUAL`
    # dans le detecteur et par `modes_for_component` ici. Une troisieme voie
    # dormante n'ajoutait qu'une facon de plus de repondre differemment a la
    # meme question.

    def modes_ranked(self) -> list[FailureMode]:
        """Modes tries par criticite AMDEC decroissante."""
        return sorted(self.modes.values(), key=lambda m: m.C, reverse=True)

    def maintenance_task(self, ref: str) -> dict | None:
        """Tache du plan preventif par reference ('A'..'H')."""
        return self.plan_maintenance.get(ref)

    def task_requires_shutdown(self, ref: str | None) -> bool:
        """La tache exige-t-elle l'arret et la consignation de la ligne ?

        La reponse est lue dans le champ `etat` du plan preventif. Elle est
        centralisee ici parce que deux modules la testaient chacun par une
        comparaison de chaine : la moindre correction typographique du
        referentiel — un accent ajoute a « Arrêt process » — faisait
        silencieusement passer une intervention sous consignation pour une
        intervention realisable en marche.

        Args:
            ref: Reference de tache ('A'..'H'), ou None.

        Returns:
            Vrai si la tache impose un arret process.
        """
        if not ref:
            return False
        task = self.plan_maintenance.get(ref)
        if not task:
            return False
        etat = unicodedata.normalize("NFKD", str(task.get("etat", "")))
        etat = etat.encode("ascii", "ignore").decode("ascii").casefold()
        return "arret" in etat

    # ── Restitution pour les prompts LLM ─────────────────────────────────────

    def briefing_equipment(self) -> str:
        """Fiche equipement condensee, injectee dans les prompts des agents."""
        e = self.equipment
        return (
            f"{e['name']} — {e['id']} ({e['code']})\n"
            f"Constructeur {e['fabricant']}, size {e['size']}, "
            f"mis en production le {e['date_mise_en_production']}.\n"
            f"Atelier {e['atelier']}, site {e['site']}.\n"
            f"Echangeur a faisceau tubulaire : acide sulfurique de sechage cote calandre, "
            f"eau de mer cote tubes. Tubes en {e['materiau_tubes']}, "
            f"protection anodique par plaques sacrificielles."
        )

    def briefing_tags(self, roles: tuple[str, ...] = ("primary", "secondary", "context")) -> str:
        """Tableau markdown des tags et de leurs plages, pour les prompts."""
        lines = ["| Alias | Libelle | Unite | Plage normale | Alarmes | Confiance |",
                 "|---|---|---|---|---|---|"]
        for t in self.tags.values():
            if t.role not in roles:
                continue
            rng = t.range_operating
            rng_s = f"{rng[0]:g} – {rng[1]:g}" if rng else "n/d"
            al = []
            for k, sym in (("alarm_low_low", "LL"), ("alarm_low", "L"),
                           ("alarm_high", "H"), ("alarm_high_high", "HH")):
                v = t.threshold(k)
                if v is not None:
                    al.append(f"{sym}={v:g}")
            lines.append(
                f"| {t.alias} | {t.label} | {t.unit} | {rng_s} | "
                f"{', '.join(al) or '—'} | {t.confidence} |"
            )
        return "\n".join(lines)

    def briefing_amdec(self) -> str:
        """Tableau markdown de l'AMDEC trie par criticite, pour les prompts."""
        lines = [
            "| Code | Nature | Element | Mode | F | G | N | C | Observable | Action |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for m in self.modes_ranked():
            lines.append(
                f"| {m.code} | {m.provenance_category} | {m.element} | {m.mode} | "
                f"{m.F} | {m.G} | {m.N} | "
                f"**{m.C}** | {'oui' if m.observable else 'NON'} | {m.action_corrective} |"
            )
        return "\n".join(lines)

    def briefing_blind_spots(self) -> str:
        """Angles morts et modes partiellement observes, pour les prompts.

        Les deux categories sont enoncees SEPAREMENT et avec des consignes
        opposees. Une version precedente les fusionnait : le prompt interdisait
        de diagnostiquer la corrosion du faisceau et la fuite de calandre,
        alors que le moteur de regles leur rattache des constatations. Le
        modele recevait donc une instruction que la chaine deterministe viole
        a chaque declenchement.
        """
        lignes: list[str] = []
        aveugles = self.blind_spots()
        if aveugles:
            lignes.append("NON DETECTABLES — ne jamais les diagnostiquer :")
            lignes += [
                f"- {m.code} ({m.element} / {m.mode}, criticite {m.C}) : "
                f"aucun signal disponible ne dit rien de ce mode. "
                f"Couvert par le preventif {m.plan_maintenance_ref or '—'}."
                for m in aveugles
            ]
        partiels = self.partially_observable_modes()
        if partiels:
            lignes.append(
                "PARTIELLEMENT OBSERVES — le symptome est mesurable, l'etat de "
                "la piece ne l'est pas. Les invoquer est legitime, mais le "
                "diagnostic doit dire qu'une inspection physique reste requise :"
            )
            lignes += [
                f"- {m.code} ({m.element} / {m.mode}, criticite {m.C}) : "
                f"indicateurs {', '.join(m.indicators) or '—'}. "
                f"Couvert par le preventif {m.plan_maintenance_ref or '—'}."
                for m in partiels
            ]
        return "\n".join(lignes) or "Aucun angle mort declare."


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

    Raises:
        FileNotFoundError: Si tags.yaml ou amdec.yaml est absent.
    """
    tags_path, amdec_path = Path(tags_path), Path(amdec_path)
    for p in (tags_path, amdec_path):
        if not p.exists():
            raise FileNotFoundError(f"Fichier domaine introuvable: {p}")
    with tags_path.open(encoding="utf-8") as f:
        tags_doc = yaml.safe_load(f)
    with amdec_path.open(encoding="utf-8") as f:
        amdec_doc = yaml.safe_load(f)

    # La topologie est optionnelle : son absence degrade la representation 3D
    # mais ne doit jamais empecher la chaine de detection de demarrer.
    topology_doc: dict = {}
    topology_path = Path(topology_path)
    if topology_path.exists():
        with topology_path.open(encoding="utf-8") as f:
            topology_doc = yaml.safe_load(f) or {}

    return DomainKnowledge(tags_doc, amdec_doc, topology_doc)


if __name__ == "__main__":
    d = load_domain()
    print(d.briefing_equipment(), "\n")
    print(d.briefing_tags(), "\n")
    print(d.briefing_amdec(), "\n")
    print("ANGLES MORTS:\n" + d.briefing_blind_spots())
