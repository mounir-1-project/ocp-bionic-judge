"""
Detection d'anomalies du refroidisseur E7301 — moteur de regles + modele statistique.

ETAGE 1 — MOTEUR DE REGLES (deterministe, ancre sur l'AMDEC)
    Chaque regle encode une signature de mode de defaillance issue de
    `amdec.yaml`. Verifiable, tracable, ne peut pas halluciner.

ETAGE 2 — MODELE STATISTIQUE (Isolation Forest)
    Il capte ce que les regles n'anticipent pas : les combinaisons anormales
    de variables qui, prises une a une, restent dans les tolerances.

Les deux etages sont FUSIONNES : le score final retient la severite la plus
elevee, et les preuves des deux etages sont conservees.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, Literal

import joblib
import numpy as np
import pandas as pd
from loguru import logger
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from core.knowledge.knowledge import DomainKnowledge, load_domain, seuil
from core.features.e7301_features import MODEL_FEATURES, References

Severity = Literal["NORMAL", "INFO", "WARNING", "CRITICAL"]
SEVERITY_ORDER: dict[str, int] = {"NORMAL": 0, "INFO": 1, "WARNING": 2, "CRITICAL": 3}

# Constantes de detection
DRIFT_PERSISTENCE_H = 72
DRIFT_Z_THRESHOLD = 1.5
CONC_DROP_SUSPICIOUS = 0.35
CONC_DROP_CRITICAL = 0.80
MODEL_PERSIST_WIN = 6
MODEL_PERSIST_MIN = 3
SENSOR_FAULT_WARNING_COUNT = 2
EPISODE_MAX_GAP_H = 6
EPISODE_MIN_DURATION_H = 3


def _fenetre_calendaire(history: pd.DataFrame, heures: int) -> pd.DataFrame:
    """Sous-ensemble de l'historique couvrant les dernieres `heures` heures."""
    if history.empty:
        return history
    borne = history.index[-1] - pd.Timedelta(hours=heures)
    return history.loc[history.index > borne]


# ── Structures ────────────────────────────────────────────────────────────────

@dataclass
class Finding:
    """Une constatation elementaire produite par une regle ou par le modele."""

    code: str
    source: Literal["RULE", "MODEL"]
    severity: Severity
    amdec_mode: str | None
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class DetectionResult:
    """Sortie complete de la detection pour un horodatage."""

    timestamp: str
    process_state: str
    severity: Severity
    anomaly_score: float
    model_is_anomaly: bool
    findings: list[Finding] = field(default_factory=list)
    attributions: list[dict[str, Any]] = field(default_factory=list)
    measurements: dict[str, float] = field(default_factory=dict)
    data_quality: dict[str, Any] = field(default_factory=dict)

    @property
    def amdec_modes(self) -> list[str]:
        """Modes AMDEC distincts invoques par les constatations."""
        return sorted({f.amdec_mode for f in self.findings if f.amdec_mode})

    def to_dict(self) -> dict[str, Any]:
        """Representation serialisable."""
        d = asdict(self)
        d["amdec_modes"] = self.amdec_modes
        return d


# ── Etage 1 : moteur de regles ────────────────────────────────────────────────

class RuleEngine:
    """Regles deterministes derivees des signatures AMDEC."""

    def __init__(self, domain: DomainKnowledge) -> None:
        self.domain = domain

    def evaluate(self, row: pd.Series, history: pd.DataFrame) -> list[Finding]:
        """Applique toutes les regles a un horodatage."""
        out: list[Finding] = []

        # Hors marche : une seule constatation
        if row.get("process_state") != "RUNNING":
            out.append(Finding(
                code="NOT_RUNNING", source="RULE", severity="INFO", amdec_mode=None,
                message=(
                    f"Ligne à l'arrêt (état {row.get('process_state')}). La "
                    f"surveillance de performance de l'échangeur est suspendue."
                ),
                evidence={"LOAD_SULFUR": _f(row.get("LOAD_SULFUR")),
                          "F_ACID": _f(row.get("F_ACID"))},
            ))
            return out

        out += self._rule_sensor_health(row)
        out += self._rule_control_loss(row, history)
        out += self._rule_thermal_drift(row, history)
        out += self._rule_concentration(row, history)
        out += self._rule_temperature_corrosion(row)
        out += self._rule_flow_anomaly(row)
        return out

    def _rule_sensor_health(self, row: pd.Series) -> list[Finding]:
        """Mode CAPTEUR_DEFAILLANT — la base de mesure est-elle fiable ?"""
        n_bad = float(row.get("n_invalid_tags") or 0)
        if n_bad <= 0:
            return []
        sev: Severity = (
            "WARNING" if n_bad >= SENSOR_FAULT_WARNING_COUNT else "INFO"
        )
        return [Finding(
            code="SENSOR_FAULT", source="RULE", severity=sev,
            amdec_mode="CAPTEUR_DEFAILLANT",
            message=f"{int(n_bad)} point(s) de mesure en défaut à cet instant "
                    f"(code qualité, gel de signal ou butée d'échelle).",
            evidence={"n_invalid_tags": n_bad},
        )]

    def _rule_control_loss(self, row: pd.Series, history: pd.DataFrame) -> list[Finding]:
        """Perte de controle de la temperature de sortie acide."""
        tag = self.domain.get("T_ACID_OUT")
        t_out = _f(row.get("T_ACID_OUT"))
        if t_out is None:
            return []
        hh = seuil(tag.threshold("alarm_high_high"), 72.0)
        h = seuil(tag.threshold("alarm_high"), 68.0)
        band = tag.control_band if tag.control_band is not None else (63.0, 68.0)

        if t_out >= hh:
            return [Finding(
                code="CONTROL_LOSS_CRITICAL", source="RULE", severity="CRITICAL",
                amdec_mode="FAISCEAU_BOUCHAGE",
                message=f"Température de sortie acide à {_n(t_out)} °C, au-dessus du "
                        f"seuil HH ({_n(hh)} °C). L'échangeur ne tient plus sa consigne.",
                evidence={"T_ACID_OUT": t_out, "seuil_HH": hh,
                          "consigne": tag.setpoint,
                          "control_deviation": _f(row.get("control_deviation"))},
            )]
        if t_out >= h:
            return [Finding(
                code="CONTROL_LOSS", source="RULE", severity="WARNING",
                amdec_mode="FAISCEAU_BOUCHAGE",
                message=f"Température de sortie acide à {_n(t_out)} °C, hors bande de "
                        f"régulation [{_n(band[0])}, {_n(band[1])}] °C.",
                evidence={"T_ACID_OUT": t_out, "seuil_H": h,
                          "control_deviation": _f(row.get("control_deviation"))},
            )]
        return []

    def _fouling_warning_sigma(self) -> float:
        """Seuil de deficit UA pour passage en WARNING."""
        mode = self.domain.modes.get("FAISCEAU_BOUCHAGE")
        gouverne = mode.signature.get("warning_sigma") if mode else None
        return max(seuil(gouverne, 3.0), DRIFT_Z_THRESHOLD)

    def _rule_thermal_drift(self, row: pd.Series, history: pd.DataFrame) -> list[Finding]:
        """Derives thermiques lentes — degradation et conduite."""
        out: list[Finding] = []
        ua_z = _f(row.get("ua_residual_trend_14d"))
        effort = _f(row.get("regulation_effort_trend_14d"))
        dev = _f(row.get("control_deviation"))

        fenetre = _fenetre_calendaire(history, DRIFT_PERSISTENCE_H)

        # Degradation : perte de coefficient d'echange, persistante
        if ua_z is not None:
            recent = fenetre["ua_residual_trend_14d"].dropna()
            if len(recent) >= DRIFT_PERSISTENCE_H // 2:
                persistent = (recent <= -DRIFT_Z_THRESHOLD).mean() > 0.8
                if ua_z <= -DRIFT_Z_THRESHOLD and persistent:
                    grave = ua_z <= -self._fouling_warning_sigma()
                    sev: Severity = "WARNING" if grave else "INFO"
                    corroborated = effort is not None and effort <= -DRIFT_Z_THRESHOLD
                    fouling = _f(row.get("fouling_resistance"))
                    out.append(Finding(
                        code="FOULING_DRIFT", source="RULE", severity=sev,
                        amdec_mode="FAISCEAU_BOUCHAGE",
                        message=(
                            f"Coefficient d'échange global inférieur de "
                            f"{_n(abs(ua_z), 2)} sigma à sa référence sur 14 jours, "
                            f"maintenu depuis plus de {DRIFT_PERSISTENCE_H} h. "
                            f"UA mesuré {_n(row.get('ua_kw_per_k'))} kW/K "
                            f"pour {_n(row.get('ua_expected'))} attendu"
                            + (f", soit une résistance d'encrassement de "
                               f"{_n(fouling, 4, signe=True)} K/kW. " if fouling is not None else ". ")
                            + (" Déficit au-delà de "
                               f"{_n(self._fouling_warning_sigma())} sigma : à qualifier."
                               if grave else
                               " Déficit encore modéré : à surveiller.")
                            + (" L'effort de régulation évolue dans le même sens, "
                               "sans valeur de preuve." if corroborated else "")
                        ),
                        evidence={
                            "ua_residual_trend_14d": ua_z,
                            "ua_kw_per_k": _f(row.get("ua_kw_per_k")),
                            "ua_expected": _f(row.get("ua_expected")),
                            "fouling_resistance": fouling,
                            "T_SEAWATER": _f(row.get("T_SEAWATER")),
                            "regulation_effort_trend_14d": effort,
                            "fenetre_h": DRIFT_PERSISTENCE_H,
                            "heures_mesurees_dans_la_fenetre": len(recent),
                            "part_sous_le_seuil": round(
                                float((recent <= -DRIFT_Z_THRESHOLD).mean()), 3
                            ),
                            "corrobore": corroborated,
                        },
                    ))

        # Conduite : sur-refroidissement installe
        if effort is not None:
            recent_e = fenetre["regulation_effort_trend_14d"].dropna()
            if (
                len(recent_e) >= DRIFT_PERSISTENCE_H // 2
                and effort >= DRIFT_Z_THRESHOLD
                and (recent_e >= DRIFT_Z_THRESHOLD).mean() > 0.8
            ):
                rappel = (
                    f"Rappel de lecture — cet indicateur est une réécriture de "
                    f"l'écart de consigne ({_n(dev, 2, signe=True)} °C), pas une preuve "
                    f"indépendante. " if dev is not None else
                    "Rappel de lecture — cet indicateur est une réécriture de "
                    "l'écart de consigne, pas une preuve indépendante. "
                )
                out.append(Finding(
                    code="OVERCOOLING_REGIME", source="RULE", severity="INFO",
                    amdec_mode=None,
                    message=(
                        f"Effort de régulation durablement excédentaire "
                        f"({_n(effort, 2, signe=True)} sigma sur 14 jours) : la ligne sur-refroidit. "
                        + rappel
                        + "Ce n'est pas une dégradation de l'appareil."
                    ),
                    evidence={
                        "regulation_effort_trend_14d": effort,
                        "control_deviation": dev,
                        "note": "indicateur redondant avec control_deviation (r = -0.94)",
                    },
                ))
        return out

    def _rule_concentration(self, row: pd.Series, history: pd.DataFrame) -> list[Finding]:
        """Titre acide — le signal le plus critique (mode FAISCEAU_FUITE)."""
        out: list[Finding] = []
        tag = self.domain.get("C_ACID_1100")
        tag2 = self.domain.get("C_ACID_1200")
        c = _f(row.get("conc_min"))
        drop = _f(row.get("conc_drop_24h"))
        spread = _f(row.get("conc_spread"))

        if c is not None:
            ll = seuil(tag.threshold("alarm_low_low"), 97.0)
            lo = seuil(tag.threshold("alarm_low"), 98.0)
            if c <= ll:
                out.append(Finding(
                    code="CONC_LOW_LOW", source="RULE", severity="CRITICAL",
                    amdec_mode="FAISCEAU_FUITE",
                    message=f"Titre acide à {_n(c, 2)} %, sous le seuil LL ({_n(ll)} %). "
                            f"Dilution majeure — suspicion d'entrée d'eau de mer.",
                    evidence={"conc_min": c, "seuil_LL": ll, "conc_drop_24h": drop},
                ))
            elif c <= lo:
                out.append(Finding(
                    code="CONC_LOW", source="RULE", severity="WARNING",
                    amdec_mode="FAISCEAU_CORROSION",
                    message=f"Titre acide à {_n(c, 2)} %, sous spécification ({_n(lo)} %). "
                            f"Conditions favorisant la corrosion des tubes 904L.",
                    evidence={"conc_min": c, "seuil_L": lo},
                ))

        if drop is not None and drop <= -CONC_DROP_CRITICAL:
            out.append(Finding(
                code="CONC_DROP_SEVERE", source="RULE", severity="CRITICAL",
                amdec_mode="FAISCEAU_FUITE",
                message=f"Chute de titre de {_n(abs(drop), 2)} point(s) en 24 h. "
                        f"Cinétique incompatible avec une dérive d'analyseur.",
                evidence={"conc_drop_24h": drop, "conc_min": c},
            ))
        elif drop is not None and drop <= -CONC_DROP_SUSPICIOUS:
            out.append(Finding(
                code="CONC_DROP", source="RULE", severity="WARNING",
                amdec_mode="FAISCEAU_FUITE",
                message=f"Baisse de titre de {_n(abs(drop), 2)} point(s) en 24 h. "
                        f"À confirmer par prélèvement laboratoire.",
                evidence={"conc_drop_24h": drop, "conc_min": c},
            ))

        drift_z = _f(row.get("conc_bias_drift_z"))
        k = float(tag2.spec.get("cross_check_k_sigma", 4.0))
        if drift_z is not None and abs(drift_z) > k:
            bias = float(tag2.spec.get("cross_check_expected_bias", 0.0))
            out.append(Finding(
                code="CONC_BIAS_DRIFT", source="RULE", severity="WARNING",
                amdec_mode="CAPTEUR_DEFAILLANT",
                message=f"L'écart entre les deux analyseurs de titre s'éloigne de "
                        f"{_n(abs(drift_z))} écarts-types de sa valeur habituelle.",
                evidence={"conc_spread": spread, "conc_bias_drift_z": drift_z,
                          "biais_normal": bias,
                          "C_ACID_1100": _f(row.get("C_ACID_1100")),
                          "C_ACID_1200": _f(row.get("C_ACID_1200"))},
            ))
        return out

    def _rule_temperature_corrosion(self, row: pd.Series) -> list[Finding]:
        """Temperature d'entree acide excessive — mode FAISCEAU_CORROSION."""
        tag = self.domain.get("T_ACID_IN")
        t = _f(row.get("T_ACID_IN"))
        if t is None:
            return []
        hh = seuil(tag.threshold("alarm_high_high"), 105.0)
        h = seuil(tag.threshold("alarm_high"), 100.0)
        if t >= hh:
            return [Finding(
                code="T_IN_HIGH_HIGH", source="RULE", severity="CRITICAL",
                amdec_mode="FAISCEAU_CORROSION",
                message=f"Température d'entrée acide à {_n(t)} °C (seuil HH {_n(hh)} °C). "
                        f"Risque direct de perte d'épaisseur des tubes.",
                evidence={"T_ACID_IN": t, "seuil_HH": hh},
            )]
        if t >= h:
            return [Finding(
                code="T_IN_HIGH", source="RULE", severity="WARNING",
                amdec_mode="FAISCEAU_CORROSION",
                message=f"Température d'entrée acide à {_n(t)} °C (seuil H {_n(h)} °C). "
                        f"Exposition thermique au-delà du domaine nominal.",
                evidence={"T_ACID_IN": t, "seuil_H": h},
            )]
        return []

    def _rule_flow_anomaly(self, row: pd.Series) -> list[Finding]:
        """Debit acide anormal — vitesse de circulation et depot."""
        tag = self.domain.get("F_ACID")
        f = _f(row.get("F_ACID"))
        if f is None:
            return []
        ll = seuil(tag.threshold("alarm_low_low"), 20.0)
        lo = seuil(tag.threshold("alarm_low"), 35.0)
        if f <= ll:
            return [Finding(
                code="FLOW_LOW_LOW", source="RULE", severity="CRITICAL",
                amdec_mode="CALANDRE_FUITE",
                message=f"Débit acide à {_n(f)} m³/h (seuil LL {_n(ll)} m³/h). "
                        f"Perte de circulation avérée.",
                evidence={"F_ACID": f, "seuil_LL": ll, "LOAD_SULFUR": _f(row.get("LOAD_SULFUR"))},
            )]
        if f <= lo:
            return [Finding(
                code="FLOW_LOW", source="RULE", severity="WARNING",
                amdec_mode="CALANDRE_FUITE",
                message=f"Débit acide à {_n(f)} m³/h (seuil L {_n(lo)} m³/h). "
                        f"Vitesse de circulation réduite.",
                evidence={"F_ACID": f, "seuil_L": lo},
            )]
        return []


# Libelles et unites des features
_FEATURE_LABELS: dict[str, tuple[str, str, int]] = {
    "ua_residual_z": ("l'écart de coefficient d'échange", " sigma", 2),
    "ua_residual_trend_14d": ("la tendance du coefficient d'échange", " sigma", 2),
    "ua_kw_per_k": ("le coefficient d'échange global", " kW/K", 1),
    "fouling_resistance": ("la résistance d'encrassement", " K/kW", 4),
    "regulation_effort_z": ("l'effort de régulation", " sigma", 2),
    "t_in_residual_z": ("le niveau thermique d'entrée", " sigma", 2),
    "conc_min": ("le titre acide", " %", 2),
    "conc_bias_drift_z": ("l'écart entre analyseurs de titre", " sigma", 1),
    "conc_drop_24h": ("la variation de titre sur 24 h", " point", 2),
    "flow_per_load": ("le débit acide rapporté à la charge", " m³/h par t/h", 2),
    "d_t_out": ("la variation horaire de sortie acide", " degC", 2),
    "d_conc": ("la variation horaire de titre", " point", 3),
    "t_out_local_z": ("la sortie acide face à ses 24 h", " sigma", 2),
    "t_in_local_z": ("l'entrée acide face à ses 24 h", " sigma", 2),
}


def _label(feature: str) -> str:
    """Libelle metier d'une feature."""
    return _FEATURE_LABELS.get(feature, (feature, "", 3))[0]


def _pretty(feature: str, value: Any) -> str:
    """Formate une valeur de feature avec son unite."""
    x = _f(value)
    if x is None:
        return "valeur absente"
    _, unit, digits = _FEATURE_LABELS.get(feature, (feature, "", 3))
    return _n(x, digits, signe=(unit == " sigma")) + unit


def _n(valeur: Any, decimales: int = 1, signe: bool = False) -> str:
    """Nombre en notation francaise pour messages d'exploitant."""
    from core.formatting import nombre

    x = _f(valeur)
    texte = nombre(x, decimales)
    return f"+{texte}" if signe and x is not None and x >= 0 else texte


def _f(v: Any) -> float | None:
    """Convertit en float en preservant None pour les valeurs manquantes."""
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(x) else round(x, 4)


# ── Etage 2 : modele statistique ──────────────────────────────────────────────

class StatisticalDetector:
    """Isolation Forest sur les features physiques, avec attribution exacte."""

    def __init__(
        self,
        features: list[str] | None = None,
        contamination: float = 0.02,
        random_state: int = 42,
    ) -> None:
        self.features = list(features or MODEL_FEATURES)
        self.contamination = contamination
        self.random_state = random_state
        self.scaler = StandardScaler()
        self.model = IsolationForest(
            n_estimators=300,
            contamination=contamination,
            max_samples=1024,
            random_state=random_state,
            n_jobs=-1,
        )
        self.baseline_: np.ndarray | None = None
        self.score_center_: float = 0.0
        self.score_scale_: float = 1.0
        self.threshold_: float = 0.5
        self.fitted_: bool = False
        self.train_meta_: dict[str, Any] = {}

    def fit(self, X: pd.DataFrame) -> StatisticalDetector:
        """Ajuste le modele sur la periode de reference."""
        missing = [c for c in self.features if c not in X.columns]
        if missing:
            raise ValueError(f"Features absentes de la matrice: {missing}")
        Xv = X[self.features].to_numpy(dtype=float)
        if len(Xv) < 100:
            raise ValueError(f"Trop peu d'echantillons: {len(Xv)}")

        Z = self.scaler.fit_transform(Xv)
        self.model.set_params(max_samples=min(1024, len(Xv)))
        self.model.fit(Z)

        raw = -self.model.score_samples(Z)
        self.score_center_ = float(np.median(raw))
        mad = float(np.median(np.abs(raw - self.score_center_)))
        self.score_scale_ = max(1.4826 * mad, float(raw.std()), 1e-9)
        self.baseline_ = np.median(Xv, axis=0)
        self.threshold_ = float(np.quantile(self._normalize(raw), 1.0 - self.contamination))
        self.raw_sigma_ = max(float(raw.std()), 1e-9)
        self.raw_threshold_ = float(np.quantile(raw, 1.0 - self.contamination))
        self.fitted_ = True
        self.train_meta_ = {
            "n_train": len(Xv),
            "period": [str(X.index.min()), str(X.index.max())],
            "contamination": self.contamination,
            "threshold": self.threshold_,
            "features": self.features,
        }
        logger.info(
            f"Isolation Forest ajuste — n={len(Xv)}, seuil={self.threshold_:.3f}"
        )
        return self

    def _normalize(self, raw: np.ndarray) -> np.ndarray:
        """Calibration monotone robuste par sigmoide."""
        z = np.clip((raw - self.score_center_) / self.score_scale_, -60.0, 60.0)
        return 1.0 / (1.0 + np.exp(-z))

    def score(self, X: pd.DataFrame) -> np.ndarray:
        """Score d'anomalie normalise dans [0, 1]."""
        self._check_fitted()
        Z = self.scaler.transform(X[self.features].to_numpy(dtype=float))
        return self._normalize(-self.model.score_samples(Z))

    def margin_sigma(self, X: pd.DataFrame) -> np.ndarray:
        """Depassement du seuil, en ecarts-types de la reference."""
        self._check_fitted()
        Z = self.scaler.transform(X[self.features].to_numpy(dtype=float))
        raw = -self.model.score_samples(Z)
        return (raw - self.raw_threshold_) / self.raw_sigma_

    def attribute(self, x: pd.Series, top_k: int = 5) -> list[dict[str, Any]]:
        """Attribution par occlusion exacte, feature par feature."""
        self._check_fitted()
        if self.baseline_ is None:
            raise RuntimeError("Baseline absente")
        v = x[self.features].to_numpy(dtype=float).reshape(1, -1)

        variants = np.repeat(v, len(self.features), axis=0)
        for i in range(len(self.features)):
            variants[i, i] = self.baseline_[i]
        batch = np.vstack([v, variants])
        scores = self._normalize(-self.model.score_samples(self.scaler.transform(batch)))
        base_score, occluded = float(scores[0]), scores[1:]

        rows = [{
            "feature": name,
            "value": _f(v[0, i]),
            "reference": _f(self.baseline_[i]),
            "contribution": round(base_score - float(occluded[i]), 4),
            "score_if_normal": round(float(occluded[i]), 4),
        } for i, name in enumerate(self.features)]
        rows.sort(key=lambda r: r["contribution"], reverse=True)
        return rows[:top_k]

    def _check_fitted(self) -> None:
        if not self.fitted_:
            raise RuntimeError("StatisticalDetector non ajuste — appeler fit() d'abord")


# ── Detecteur consolide ───────────────────────────────────────────────────────

class CoolerAnomalyDetector:
    """Detecteur complet : regles AMDEC + Isolation Forest + explicabilite."""

    def __init__(
        self,
        domain: DomainKnowledge | None = None,
        stat: StatisticalDetector | None = None,
        references: References | None = None,
    ) -> None:
        self.domain = domain or load_domain()
        self.rules = RuleEngine(self.domain)
        self.stat = stat or StatisticalDetector()
        self.references = references
        self._scores: pd.Series | None = None
        self._scores_key: tuple[int, Any, Any, float] | None = None
        self._margins: pd.Series | None = None
        self._margins_key: tuple[int, Any, Any, float] | None = None

    def fit(self, features: pd.DataFrame, reference_end: str | None = None) -> CoolerAnomalyDetector:
        """Ajuste l'etage statistique sur la periode de reference."""
        from core.features.e7301_features import model_matrix
        from core.features.thermal import reference_cutoff

        X = model_matrix(features)
        borne = (
            pd.Timestamp(reference_end)
            if reference_end
            else reference_cutoff(features)
        )
        X = X[X.index <= borne]
        self.stat.fit(X)
        self.invalidate_cache()
        return self

    def analyze(self, features: pd.DataFrame, timestamp: pd.Timestamp | str) -> DetectionResult:
        """Analyse un horodatage precis."""
        ts = pd.Timestamp(timestamp)
        if ts not in features.index:
            raise KeyError(f"Horodatage absent des donnees: {ts}")
        row = features.loc[ts]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[-1]
        history = features.loc[:ts]

        findings = self.rules.evaluate(row, history)

        # Etage statistique
        score, is_anom, attributions = 0.0, False, []
        usable = (
            row.get("process_state") == "RUNNING"
            and self.stat.fitted_
            and not row[self.stat.features].isna().any()
        )
        if usable:
            x = row[self.stat.features].to_frame().T
            score = float(self.stat.score(x)[0])
            is_anom = score >= self.stat.threshold_
            if is_anom:
                attributions = self.stat.attribute(row)
                top = attributions[0]
                n_recent, n_scorables = self._recent_exceedances(features, ts)
                persistent = n_recent >= MODEL_PERSIST_MIN
                findings.append(Finding(
                    code="MODEL_ANOMALY" if persistent else "MODEL_ANOMALY_ISOLATED",
                    source="MODEL",
                    severity="WARNING" if persistent else "INFO",
                    amdec_mode=(
                        self._mode_for_feature(top["feature"], row)
                        if persistent else None
                    ),
                    message=(
                        f"Combinaison de grandeurs inhabituelle, écart persistant : "
                        f"{n_recent} heure(s) atypique(s) sur {n_scorables}. "
                        f"Contribution dominante : {_label(top['feature'])} à "
                        f"{_pretty(top['feature'], top['value'])} contre "
                        f"{_pretty(top['feature'], top['reference'])} en référence."
                        if persistent else
                        f"Point isolé atypique : {n_recent} heure(s) sur {n_scorables}. "
                        f"Surveiller sans agir."
                    ),
                    evidence={"anomaly_score": round(score, 4),
                              "threshold": round(self.stat.threshold_, 4),
                              "top_feature": top["feature"],
                              "persistent": persistent},
                ))
        elif row.get("process_state") == "RUNNING" and self.stat.fitted_:
            findings.append(Finding(
                code="MODEL_UNAVAILABLE", source="MODEL", severity="INFO", amdec_mode=None,
                message="Modèle statistique non applicable : grandeur d'entrée manquante.",
                evidence={"missing": [c for c in self.stat.features if pd.isna(row.get(c))]},
            ))

        severity = _max_severity([f.severity for f in findings])

        return DetectionResult(
            timestamp=ts.isoformat(),
            process_state=str(row.get("process_state")),
            severity=severity,
            anomaly_score=round(score, 4),
            model_is_anomaly=bool(is_anom),
            findings=findings,
            attributions=attributions,
            measurements={
                k: _f(row.get(k))
                for k in ("LOAD_SULFUR", "F_ACID", "T_ACID_IN", "T_ACID_OUT",
                          "C_ACID_1100", "C_ACID_1200", "conc_min", "conc_spread",
                          "delta_t", "duty_kw",
                          "duty_expected", "regulation_effort_z",
                          "regulation_effort_trend_14d", "control_deviation",
                          "T_SEAWATER", "ua_kw_per_k", "ua_expected",
                          "ua_residual_z", "fouling_resistance")
                if _f(row.get(k)) is not None
            },
            data_quality={
                "n_invalid_tags": int(row.get("n_invalid_tags") or 0),
                "model_applicable": bool(usable),
            },
        )

    def _recent_exceedances(self, features: pd.DataFrame, ts: pd.Timestamp) -> tuple[int, int]:
        """Heures atypiques et heures scorables sur la fenetre calendaire."""
        s = self.score_series(features)
        borne = pd.Timestamp(ts) - pd.Timedelta(hours=MODEL_PERSIST_WIN)
        win = s.loc[(s.index > borne) & (s.index <= ts)]
        if win.empty:
            return 0, 0
        return int((win >= self.stat.threshold_).sum()), len(win)

    def score_series(self, features: pd.DataFrame) -> pd.Series:
        """Score d'anomalie sur toute la periode."""
        from core.features.e7301_features import model_matrix

        key = self._cache_key(features)
        if self._scores is not None and self._scores_key == key:
            return self._scores

        X = model_matrix(features)
        self._scores = pd.Series(self.stat.score(X), index=X.index, name="anomaly_score")
        self._scores_key = key
        return self._scores

    def _cache_key(self, features: pd.DataFrame) -> tuple[int, Any, Any, float]:
        """Empreinte d'une table de features pour la memorisation."""
        if not len(features):
            return (0, None, None, 0.0)
        colonnes = [c for c in self.stat.features if c in features.columns]
        empreinte = (
            float(np.nansum(features[colonnes].to_numpy(dtype=float)))
            if colonnes else 0.0
        )
        return (len(features), features.index[0], features.index[-1], empreinte)

    def invalidate_cache(self) -> None:
        """Force le recalcul des scores."""
        self._scores = None
        self._scores_key = None
        self._margins = None
        self._margins_key = None

    def episodes(
        self,
        features: pd.DataFrame,
        max_gap_h: int = EPISODE_MAX_GAP_H,
        min_duration_h: int = EPISODE_MIN_DURATION_H,
    ) -> pd.DataFrame:
        """Agrege les heures atypiques en episodes exploitables."""
        s = self.score_series(features)
        margins = self.margin_series(features)
        flagged = s[s >= self.stat.threshold_]
        colonnes = ["start", "end", "duration_h", "n_hours", "margin_max",
                    "margin_mean", "score_max", "score_mean", "peak_at"]
        if flagged.empty:
            return pd.DataFrame(columns=colonnes)

        gaps = flagged.index.to_series().diff() > pd.Timedelta(hours=max_gap_h)
        group = gaps.cumsum()
        rows = []
        for _, chunk in flagged.groupby(group):
            duration = int((chunk.index.max() - chunk.index.min()) / pd.Timedelta("1h")) + 1
            if duration < min_duration_h:
                continue
            marge = margins.reindex(chunk.index).dropna()
            rows.append({
                "start": chunk.index.min(),
                "end": chunk.index.max(),
                "duration_h": duration,
                "n_hours": len(chunk),
                "margin_max": round(float(marge.max()), 2) if len(marge) else 0.0,
                "margin_mean": round(float(marge.mean()), 2) if len(marge) else 0.0,
                "score_max": round(float(chunk.max()), 4),
                "score_mean": round(float(chunk.mean()), 4),
                "peak_at": chunk.idxmax(),
            })
        return (pd.DataFrame(rows)
                .sort_values("margin_max", ascending=False)
                .reset_index(drop=True))

    def margin_series(self, features: pd.DataFrame) -> pd.Series:
        """Marge en sigma sur toute la periode."""
        from core.features.e7301_features import model_matrix

        key = self._cache_key(features)
        if self._margins is not None and self._margins_key == key:
            return self._margins

        X = model_matrix(features)
        self._margins = pd.Series(
            self.stat.margin_sigma(X), index=X.index, name="margin_sigma"
        )
        self._margins_key = key
        return self._margins

    _MODE_BY_RESIDUAL: ClassVar[dict[str, tuple[str, float]]] = {
        "ua_residual_z": ("FAISCEAU_BOUCHAGE", 1.5),
        "conc_bias_drift_z": ("CAPTEUR_DEFAILLANT", 4.0),
    }
    _MODE_BY_THRESHOLD: ClassVar[dict[str, tuple[str, str, str]]] = {
        "conc_min": ("FAISCEAU_CORROSION", "C_ACID_1100", "alarm_low"),
    }
    _FEATURES_SANS_ACCUSATION: ClassVar[frozenset[str]] = frozenset({
        "conc_drop_24h", "d_conc", "flow_per_load",
    })

    def _mode_for_feature(self, feature: str, row: pd.Series) -> str | None:
        """Rattache une feature dominante a un mode AMDEC."""
        if feature in self._MODE_BY_RESIDUAL:
            mode, min_sigma = self._MODE_BY_RESIDUAL[feature]
            value = _f(row.get(feature))
            if value is None:
                return None
            return mode if abs(value) >= min_sigma else None

        if feature in self._FEATURES_SANS_ACCUSATION:
            return None

        if feature in self._MODE_BY_THRESHOLD:
            mode, tag_name, threshold_name = self._MODE_BY_THRESHOLD[feature]
            value = _f(row.get(feature))
            limit = self.domain.get(tag_name).threshold(threshold_name)
            if value is None or limit is None:
                return None
            return mode if value <= limit else None

        return None

    def save(self, path: str | Path) -> Path:
        """Serialise le detecteur complet."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({
            "stat": self.stat,
            "references": self.references,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "features": MODEL_FEATURES,
        }, path)
        logger.info(f"Detecteur sauvegarde: {path}")
        return path

    @classmethod
    def load(cls, path: str | Path, domain: DomainKnowledge | None = None) -> CoolerAnomalyDetector:
        """Recharge un detecteur serialise."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Modele introuvable: {path}.")
        bundle = joblib.load(path)
        return cls(domain=domain, stat=bundle["stat"], references=bundle.get("references"))


def _max_severity(severities: list[str]) -> Severity:
    """Retourne la severite la plus elevee."""
    if not severities:
        return "NORMAL"
    return max(severities, key=lambda s: SEVERITY_ORDER.get(s, 0))  # type: ignore[return-value]
