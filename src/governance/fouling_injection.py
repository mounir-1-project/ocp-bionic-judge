"""
Banc d'injection d'encrassement — la seule metrique de detection honnete
accessible sans historique GMAO.

POURQUOI CE BANC EXISTE
----------------------------------------------------------------------------
Un audit a releve que la regle d'encrassement ne s'etait JAMAIS declenchee sur
les quatorze mois disponibles, et que le projet presentait ce zero comme un
resultat. C'est une inversion de la charge de la preuve : sans anomalie
etiquetee, on ne peut pas distinguer

    (1) il n'y a pas eu d'encrassement,
    (2) le detecteur est incapable de se declencher,
    (3) l'indicateur ne mesure pas ce qu'on croit.

Ce banc tranche entre (1) et (2). Il superpose aux donnees REELLES une rampe
d'encrassement simulee, puis mesure ce que le detecteur en fait : le detecte-t-il,
au bout de combien de temps, et a partir de quelle perte de performance.

CE QUE LE BANC NE PROUVE PAS
----------------------------------------------------------------------------
Il ne valide pas la PHYSIQUE de la signature. Il valide qu'un encrassement
CONFORME AU MODELE D'INJECTION serait vu. Si l'encrassement reel se manifeste
autrement, ce banc ne le dira pas. C'est une borne superieure de performance,
pas une garantie terrain — et le rapport le mentionne dans chaque sortie.

MODELE D'INJECTION
----------------------------------------------------------------------------
L'injection ne bricole aucune temperature. Elle degrade le COEFFICIENT
D'ECHANGE GLOBAL, et laisse la physique produire les temperatures qui en
resultent :

    UA'       = UA . (1 - severite . avancement)
    epsilon'  = 1 - exp(-UA' / C_acide)
    T_sortie' = T_entree - epsilon' . (T_entree - T_eau_de_mer)

C'est la seule construction qui garantisse que le detecteur ne reconnaisse pas
la faute par un artefact de fabrication : il voit exactement ce qu'il verrait
d'un depot reel de meme severite.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from src.domain.knowledge import DomainKnowledge
from src.features.e7301_features import build_features

# Pertes de coefficient d'echange testees, en fraction (0,20 = 20 %).
DEFAULT_SEVERITIES: tuple[float, ...] = (0.05, 0.10, 0.20, 0.30)

# Duree des rampes testees, en jours.
DEFAULT_DURATIONS_D: tuple[int, ...] = (30, 60)

# Avancement au-dela duquel une detection ne sert plus a programmer un arret.
USEFUL_ADVANCEMENT = 0.50


@dataclass
class InjectionCase:
    """Un scenario d'encrassement injecte.

    Attributes:
        severity: Perte finale de coefficient d'echange, en fraction.
        duration_days: Duree de la rampe.
        start: Debut de la rampe.
        detected: Le detecteur a-t-il emis FOULING_DRIFT ?
        detected_at: Premier instant de detection.
        latency_h: Heures ecoulees entre le debut de la rampe et la detection.
        advancement_at_detection: Avancement de l'encrassement a la detection,
            entre 0 et 1. C'est le chiffre qui compte : detecter a 0.3 laisse
            du temps pour programmer un arret, detecter a 0.95 ne sert a rien.
        peak_ua_z: Valeur maximale atteinte par l'indicateur independant.
    """

    severity: float
    duration_days: int
    start: str
    detected: bool = False
    detected_at: str | None = None
    latency_h: int | None = None
    advancement_at_detection: float | None = None
    peak_ua_z: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Representation serialisable."""
        return {
            "perte_UA_pct": round(self.severity * 100, 1),
            "duration_days": self.duration_days,
            "start": self.start,
            "detected": self.detected,
            "detected_at": self.detected_at,
            "latency_h": self.latency_h,
            "advancement_at_detection": (
                None if self.advancement_at_detection is None
                else round(self.advancement_at_detection, 3)
            ),
            "peak_ua_residual_z": round(self.peak_ua_z, 2),
        }


@dataclass
class InjectionResult:
    """Resultat complet du banc.

    Attributes:
        cases: Scenarios injectes.
        false_positive_rate: Part des heures ou le detecteur annonce un
            encrassement sur les donnees NON modifiees.
        n_control_hours: Heures du temoin.
    """

    cases: list[InjectionCase] = field(default_factory=list)
    false_positive_rate: float = 0.0
    n_control_hours: int = 0

    @property
    def detection_rate(self) -> float:
        """Part des scenarios detectes."""
        return (
            sum(1 for c in self.cases if c.detected) / len(self.cases)
            if self.cases else 0.0
        )

    @property
    def median_advancement(self) -> float | None:
        """Avancement median a la detection, sur les cas detectes."""
        values = [
            c.advancement_at_detection for c in self.cases
            if c.advancement_at_detection is not None
        ]
        return float(np.median(values)) if values else None

    @property
    def useful_detection_rate(self) -> float:
        """Part des scenarios detectes ASSEZ TOT pour servir a quelque chose.

        Un encrassement repere a 95 % de son avancement n'apporte rien : la
        degradation est deja consommee et l'arret sera subi, pas programme. Le
        seuil de 50 % correspond au delai typique de programmation d'un arret
        de ligne. C'est ce taux qu'il faut regarder, pas le taux brut.
        """
        if not self.cases:
            return 0.0
        useful = sum(
            1 for c in self.cases
            if c.advancement_at_detection is not None
            and c.advancement_at_detection <= USEFUL_ADVANCEMENT
        )
        return useful / len(self.cases)

    def to_dict(self) -> dict[str, Any]:
        """Rapport serialisable, limites comprises."""
        detected = [c for c in self.cases if c.detected]
        return {
            "method": (
                "rampe d'encrassement superposée aux données réelles ; le "
                "détecteur n'est pas réentraîné sur les données modifiées"
            ),
            "injection_model": (
                "dégradation progressive du coefficient d'échange global ; les "
                "températures résultantes sont recalculées par la physique "
                "efficacité-NTU, non imposées"
            ),
            "n_cases": len(self.cases),
            "detection_rate": round(self.detection_rate, 4),
            "useful_detection_rate": round(self.useful_detection_rate, 4),
            "useful_advancement_threshold": USEFUL_ADVANCEMENT,
            "reading": (
                "Le taux de détection brut n'est pas la bonne mesure : une "
                "dérive finit toujours par dépasser le seuil. Ce qui compte est "
                "l'AVANCEMENT auquel elle est vue. Détecter à 90 % d'avancement "
                "revient à constater la dégradation, pas à l'anticiper."
            ),
            "false_positive_rate": round(self.false_positive_rate, 4),
            "false_positive_reading": (
                "Part des heures de marche où la règle se déclenche sur les "
                "données RÉELLES, sans aucune faute injectée. Un taux élevé "
                "signifierait que le corpus contient déjà des dérives de même "
                "signature, ou que le seuil est trop bas."
            ),
            "n_control_hours": self.n_control_hours,
            "median_advancement_at_detection": (
                None if self.median_advancement is None
                else round(self.median_advancement, 3)
            ),
            "median_latency_h": (
                int(np.median([c.latency_h for c in detected])) if detected else None
            ),
            "smallest_loss_detected_pct": (
                round(min(c.severity for c in detected) * 100, 1) if detected else None
            ),
            "cases": [c.to_dict() for c in self.cases],
            "limitations": [
                "Le banc établit qu'un encrassement CONFORME AU MODÈLE D'INJECTION "
                "serait détecté ; il ne valide pas la signature physique réelle.",
                "Aucune vérité terrain n'existe : ce résultat est une borne "
                "supérieure de performance, pas une garantie d'exploitation.",
                "L'injection dégrade UA à débit d'eau de mer inchangé. La "
                "régulation réelle ouvrirait la vanne pour compenser, ce que "
                "le banc ne simule pas faute de mesure côté eau de mer : "
                "l'avancement à la détection publié ici est donc plus "
                "favorable que celui qu'on observerait en marche.",
            ],
        }


def inject_fouling(
    readings: pd.DataFrame,
    start: pd.Timestamp,
    severity: float,
    duration_days: int,
) -> tuple[pd.DataFrame, pd.Series]:
    """Superpose un encrassement PHYSIQUE a des lectures reelles.

    L'injection ne bricole pas les temperatures : elle degrade le coefficient
    d'echange global et laisse la physique produire les temperatures qui en
    resultent. Un depot reduit UA d'une fraction `severity` au terme de la
    rampe; l'efficacite de l'echangeur suit, et la temperature de sortie monte
    de ce qui n'est plus evacue :

        UA'      = UA . (1 - severity . avancement)
        epsilon' = 1 - exp(-UA' / C_acide)
        T_sortie'= T_entree - epsilon' . (T_entree - T_eau_de_mer)

    C'est la seule facon d'obtenir un cas de test que le detecteur ne pourrait
    pas reconnaitre par un artefact de construction.

    Args:
        readings: Table de lectures issue de l'ingestion.
        start: Debut de la rampe.
        severity: Perte finale de coefficient d'echange, en fraction (0,15 = 15 %).
        duration_days: Duree de la rampe.

    Returns:
        Tuple (lectures modifiees, serie d'avancement entre 0 et 1).
    """
    from src.features.e7301_features import rho_cp
    from src.features.thermal import seawater_temperature

    if not 0.0 < severity < 1.0:
        raise ValueError(
            f"severity est une FRACTION de perte de coefficient d'echange, "
            f"attendue dans ]0, 1[ — recu {severity}. Une valeur >= 1 "
            f"annulerait entierement l'echange et ne correspond a aucun "
            f"encrassement physique."
        )

    out = readings.copy()
    end = start + pd.Timedelta(days=duration_days)

    advancement = pd.Series(0.0, index=out.index)
    window = (out.index >= start) & (out.index <= end)
    if window.any():
        span = (out.index[window] - start).total_seconds() / (duration_days * 86400.0)
        advancement.loc[window] = np.clip(span, 0.0, 1.0)
    advancement.loc[out.index > end] = 1.0

    # Un echangeur a l'arret ne s'encrasse pas au meme rythme, et la mesure n'y
    # a pas de sens : seule la marche etablie est modifiee.
    running = out["process_state"].eq("RUNNING") if "process_state" in out else True
    effect = advancement.where(running, 0.0)

    t_in = out["T_ACID_IN"]
    t_out = out["T_ACID_OUT"]
    t_sea = seawater_temperature(out.index)
    capacity = rho_cp((t_in + t_out) / 2.0) * out["F_ACID"]

    driving = (t_in - t_sea).clip(lower=1.0)
    effectiveness = ((t_in - t_out) / driving).clip(1e-4, 0.999)
    ua = -np.log(1.0 - effectiveness) * capacity

    fouled = ua * (1.0 - severity * effect)
    ntu = (fouled / capacity.replace(0, np.nan)).clip(1e-4, 20.0)
    new_effectiveness = 1.0 - np.exp(-ntu)

    degraded = t_in - new_effectiveness * driving
    out["T_ACID_OUT"] = degraded.where(
        running & degraded.notna() & (degraded > t_sea), t_out
    )
    return out, advancement


class FoulingInjectionBench:
    """Mesure la capacite du detecteur a voir un encrassement simule.

    Attributes:
        pipeline: Chaine complete deja construite.
    """

    def __init__(self, pipeline: Any) -> None:
        """Initialise le banc.

        Args:
            pipeline: Instance de `E7301Pipeline`.
        """
        self.pipeline = pipeline

    @staticmethod
    def _quiet_start(
        control: pd.Series, after: pd.Timestamp, span_days: int
    ) -> pd.Timestamp | None:
        """Cherche une fenetre ou le temoin ne declenche rien.

        Sans cette precaution, la rampe demarre sur une periode ou les donnees
        reelles declenchent deja la regle, et la « detection » mesuree n'est
        attribuable a rien. C'est le defaut qu'avait la premiere version de ce
        banc : elle annoncait 100 % de detection a 0 % d'avancement.

        Args:
            control: Detections sur donnees non modifiees.
            after: Borne basse (fin de periode de reference).
            span_days: Duree calme exigee.

        Returns:
            Debut de fenetre calme, ou None s'il n'en existe aucune.
        """
        candidates = control.index[control.index >= after]
        need = pd.Timedelta(days=span_days)
        for ts in candidates:
            window = control.loc[ts : ts + need]
            if len(window) > 24 and not window.any():
                return ts
        return None

    def run(
        self,
        severities: tuple[float, ...] = DEFAULT_SEVERITIES,
        durations_days: tuple[int, ...] = DEFAULT_DURATIONS_D,
        domain: DomainKnowledge | None = None,
    ) -> InjectionResult:
        """Execute tous les scenarios et mesure le temoin.

        Args:
            severities: Pertes de coefficient d'echange testees, en fraction.
            durations_days: Durees de rampe testees.
            domain: Connaissance domaine.

        Returns:
            Resultat complet du banc.
        """
        pipe = self.pipeline
        domain = domain or pipe.domain
        readings = pipe.ingestion.readings
        quality = pipe.ingestion.quality
        ref_end = pd.Timestamp(pipe.references.inlet.train_period[1])

        result = InjectionResult()

        # ── Temoin : donnees non modifiees ────────────────────────────────
        # Ce taux est un resultat a part entiere : il dit combien de fois la
        # regle se declenche SANS qu'aucune faute ait ete injectee.
        control = self._fouling_hours(pipe.features)
        running = pipe.features["process_state"].eq("RUNNING")
        result.n_control_hours = int(running.sum())
        result.false_positive_rate = (
            float(control.sum() / running.sum()) if running.sum() else 0.0
        )

        for severity in severities:
            for duration in durations_days:
                # La rampe demarre apres la periode de reference ET dans une
                # fenetre ou le temoin est silencieux, sinon la detection n'est
                # attribuable a rien.
                start = self._quiet_start(
                    control, ref_end + pd.Timedelta(days=7), duration
                )
                if start is None:
                    logger.warning(
                        f"Aucune fenetre calme de {duration} j : scenario ignore"
                    )
                    continue

                case = InjectionCase(
                    severity=severity, duration_days=duration, start=str(start)
                )
                injected, advancement = inject_fouling(
                    readings, start, severity, duration
                )
                features, _ = build_features(
                    injected, quality, domain, reference_end=str(ref_end)
                )
                fouling = self._fouling_hours(features)

                peak = features.loc[
                    features.index >= start, "ua_residual_trend_14d"
                ].min()
                case.peak_ua_z = float(peak) if pd.notna(peak) else 0.0

                # DETECTION ATTRIBUABLE : declenchee dans le scenario injecte,
                # et pas dans le temoin au meme instant.
                control_aligned = control.reindex(features.index).fillna(False)
                attributable = fouling & ~control_aligned & (features.index >= start)
                hits = features.index[attributable]
                if len(hits):
                    first = hits[0]
                    case.detected = True
                    case.detected_at = str(first)
                    case.latency_h = int((first - start).total_seconds() // 3600)
                    case.advancement_at_detection = float(advancement.loc[first])
                result.cases.append(case)
                logger.info(
                    f"Injection {severity:.0%} de perte UA / {duration} j depuis {start} — "
                    + (
                        f"detectee a {case.advancement_at_detection:.0%} "
                        f"d'avancement ({case.latency_h} h)"
                        if case.detected else "NON DETECTEE"
                    )
                )

        return result

    @staticmethod
    def _fouling_hours(features: pd.DataFrame) -> pd.Series:
        """Heures ou la regle d'encrassement se declencherait.

        On evalue la condition de `_rule_thermal_drift` directement plutot que
        d'appeler `analyze` sur 8 800 instants : le predicat est le meme, et le
        banc reste utilisable en interactif.
        `test_le_predicat_du_banc_equivaut_a_la_regle` verrouille l'equivalence.

        La regle est deterministe et ne fait intervenir aucun etage
        statistique : le detecteur n'a donc pas a etre instancie ici.

        Args:
            features: Table de features.

        Returns:
            Serie booleenne alignee sur `features`.
        """
        from src.models.detector import DRIFT_PERSISTENCE_H, DRIFT_Z_THRESHOLD

        trend = features["ua_residual_trend_14d"]
        above = (trend <= -DRIFT_Z_THRESHOLD).fillna(False)
        # FENETRE CALENDAIRE, COMME LA REGLE.
        # Ce predicat comptait 72 LIGNES quand la regle compte desormais 72
        # HEURES. A travers un arret de ligne, les deux divergeaient — et ce
        # predicat alimente aussi la grille de sensibilite, donc un chiffre
        # publie. L'equivalence est verrouillee par
        # `test_le_predicat_du_banc_equivaut_a_la_regle`.
        persistent = (
            above.rolling(
                f"{DRIFT_PERSISTENCE_H}h", min_periods=DRIFT_PERSISTENCE_H // 2
            )
            .mean()
            > 0.8
        )
        return (
            above & persistent.fillna(False) & features["process_state"].eq("RUNNING")
        )


if __name__ == "__main__":
    import json

    from src.pipeline import E7301Pipeline

    bench = FoulingInjectionBench(E7301Pipeline(use_llm=False))
    print(json.dumps(bench.run().to_dict(), ensure_ascii=False, indent=2))
