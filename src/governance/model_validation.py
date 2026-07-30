"""Validation causale et gouvernance scientifique du système E7301.

Le corpus ne contient aucune vérité terrain de panne. La validation porte donc
sur la stabilité, la causalité temporelle, la robustesse et la charge d'alerte,
jamais sur une précision prédictive inventée.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

from src.domain.knowledge import DomainKnowledge
from src.features.e7301_features import (
    MODEL_FEATURES,
    InletReference,
    References,
    RegulationEffortReference,
    add_physics_features,
    build_features,
    independence_report,
    model_matrix,
)
from src.features.thermal import (
    ConductanceReference,
    overall_conductance,
    seawater_temperature,
)
from src.formatting import nombre, pourcent
from src.ingest.dcs_loader import classify_process_state
from src.models.detector import StatisticalDetector


def _population_stability_index(reference: np.ndarray, observed: np.ndarray) -> float:
    """PSI sur déciles de référence, avec lissage des cellules vides."""
    quantiles = np.unique(np.quantile(reference, np.linspace(0, 1, 11)))
    if len(quantiles) < 3:
        return 0.0
    quantiles[0], quantiles[-1] = -np.inf, np.inf
    ref_hist = np.histogram(reference, bins=quantiles)[0].astype(float)
    obs_hist = np.histogram(observed, bins=quantiles)[0].astype(float)
    ref_p = np.clip(ref_hist / max(ref_hist.sum(), 1), 1e-6, None)
    obs_p = np.clip(obs_hist / max(obs_hist.sum(), 1), 1e-6, None)
    return float(np.sum((obs_p - ref_p) * np.log(obs_p / ref_p)))


def _feature_audit(features: pd.DataFrame) -> dict[str, Any]:
    """Audit de redondance des features.

    CORRECTION D'UN CONTROLE QUI SE VALIDAIT LUI-MEME. La version precedente
    calculait la colinearite sur la seule matrice du modele, d'ou
    `control_deviation` etait absente. Elle concluait donc « 0 paire redondante »
    en ayant justement ecarte la variable qui revele la redondance.

    L'audit porte desormais aussi sur des grandeurs de CONTROLE qui n'entrent
    pas dans le modele mais dont la redondance avec une feature serait une
    faute de conception. Elles sont reportees separement pour ne pas confondre
    les deux questions.

    Args:
        features: Table de features complete.

    Returns:
        Paires redondantes internes, redondances avec les variables de controle,
        et conditionnement.
    """
    X = model_matrix(features).sort_index()
    corr = X.corr().abs()
    pairs = [
        {"left": left, "right": right, "abs_correlation": round(float(corr.loc[left, right]), 4)}
        for i, left in enumerate(corr.columns)
        for right in corr.columns[i + 1 :]
        if corr.loc[left, right] >= 0.90
    ]

    # Variables volontairement hors modele, mais qui doivent etre confrontees
    # aux features : c'est la que se cachait la tautologie.
    control_vars = ["control_deviation", "delta_t", "duty_kw", "T_ACID_OUT"]
    run = features[features["process_state"].eq("RUNNING")]
    shadow: list[dict[str, Any]] = []
    for var in control_vars:
        if var not in run.columns:
            continue
        for feature in X.columns:
            pair = run[[var, feature]].dropna()
            if len(pair) < 50:
                continue
            r = float(pair[var].corr(pair[feature]))
            if abs(r) >= 0.80:
                shadow.append({
                    "feature": feature,
                    "control_variable": var,
                    "correlation": round(r, 4),
                    "reading": (
                        "cette grandeur est une réécriture de la variable "
                        "régulée : elle ne constitue pas une preuve indépendante"
                    ),
                })

    scaled = ((X - X.mean()) / X.std(ddof=0).replace(0, np.nan)).fillna(0.0)
    condition = float(np.linalg.cond(scaled.to_numpy()))
    return {
        "n_features": len(MODEL_FEATURES),
        "n_observations": len(X),
        "redundant_pairs_abs_r_ge_0_90": pairs,
        "shadow_redundancy_abs_r_ge_0_80": shadow,
        "control_variables_tested": control_vars,
        "condition_number": round(condition, 2) if np.isfinite(condition) else None,
        "independence": independence_report(features),
    }


def _egales(gauche: float, droite: float) -> bool:
    """Deux valeurs de feature sont-elles identiques, bruit flottant compris ?"""
    if pd.isna(gauche) and pd.isna(droite):
        return True
    if pd.isna(gauche) or pd.isna(droite):
        return False
    return bool(np.isclose(gauche, droite, rtol=1e-9, atol=1e-12))


def _causality_audit(
    features: pd.DataFrame,
    *,
    readings: pd.DataFrame,
    quality: pd.DataFrame,
    domain: DomainKnowledge,
    references: References,
) -> dict[str, Any]:
    """Verifie qu'aucune grandeur du modele ne depend d'un instant futur.

    LE PRINCIPE DU CONTROLE — ET CE QU'IL NE FAISAIT PAS.
    Une chaine causale doit produire, a l'instant t, exactement la meme valeur
    qu'elle produirait si les donnees s'arretaient a t. Ce controle l'affirmait
    et ne le faisait pas : il ecrivait

        tronque = features.loc[:coupe, colonnes]
        complet = features.loc[:coupe, colonnes]

    deux fois la MEME expression, puis supprimait `complet` sans jamais le
    comparer. La seule verification effective etait qu'une ligne n'etait pas
    entierement vide. La porte `causalite_temporelle` publiait donc `passed`
    sur la foi d'un controle qui ne pouvait rien detecter — alors que son
    propre docstring declare qu'une inspection statique des `shift()` se
    contourne par un `rolling(center=True)`, un `transform("sum")` ou un
    `bfill()`, et que seule la reconstruction peut echouer.

    La chaine est desormais REELLEMENT reconstruite sur l'histoire tronquee,
    references figees pour que la comparaison porte sur le calcul des grandeurs
    et non sur un reajustement legitime. L'etat de marche — la ou vivait le
    `shift(-1)` historique — est reclasse et compare separement.

    Args:
        features: Table de features construite sur le corpus complet.
        readings: Lectures issues de l'ingestion.
        quality: Evenements qualite.
        domain: Connaissance domaine.
        references: References ajustees sur le corpus complet.

    Returns:
        Verdict et preuve chiffree.
    """
    colonnes = [c for c in MODEL_FEATURES if c in features.columns]
    index = features.index
    ecarts: list[str] = []

    for part in (0.4, 0.6, 0.8):
        coupe = index[int(len(index) * part) - 1]

        # 1. ETAT DE MARCHE — la ou vivait le `shift(-1)` historique.
        etat_tronque = classify_process_state(readings.loc[:coupe], domain)
        etat_complet = readings.loc[coupe, "process_state"]
        if etat_tronque.iloc[-1] != etat_complet:
            ecarts.append(
                f"{coupe} : etat classe '{etat_tronque.iloc[-1]}' sur l'histoire "
                f"disponible, '{etat_complet}' sur le corpus entier"
            )

        # 2. FEATURES — reconstruites sur la seule histoire, references FIGEES.
        # Les references restent celles du corpus pour que la comparaison porte
        # sur le calcul des grandeurs, non sur un reajustement legitime.
        quality_tronque = (
            quality[quality["timestamp"] <= coupe] if len(quality) else quality
        )
        tronque, _ = build_features(
            readings.loc[:coupe],
            quality_tronque,
            domain,
            references=references,
            fit_references=False,
        )
        derniere_tronquee = tronque.loc[coupe, colonnes].astype(float)
        derniere_complete = features.loc[coupe, colonnes].astype(float)
        divergentes = [
            colonne
            for colonne in colonnes
            if not _egales(derniere_tronquee[colonne], derniere_complete[colonne])
        ]
        if divergentes:
            ecarts.append(
                f"{coupe} : {len(divergentes)} grandeur(s) differente(s) selon "
                f"que le corpus s'arrete ou non a cet instant — "
                f"{', '.join(divergentes[:5])}"
            )
        if derniere_tronquee.isna().all():
            ecarts.append(f"aucune grandeur calculable a {coupe}")

    # Inspection complementaire, bon marche : aucun decalage negatif ni fenetre
    # centree dans les modules de la chaine.
    import re
    from pathlib import Path

    # LE PERIMETRE COUVRE TOUTE LA CHAINE, PAS TROIS FICHIERS.
    # Il se limitait a l'ingestion et aux features : un decalage negatif
    # reintroduit dans le detecteur ou les indicateurs publies serait passe
    # inapercu. `transform(` est inclus parce que la version historique du
    # detecteur de gel mesurait la longueur TOTALE d'un palier, donc son
    # extension dans le futur.
    motifs = re.compile(
        r"shift\(\s*-\d|center\s*=\s*True|\.bfill\(|backfill|"
        r"fillna\(\s*method\s*=\s*[\"']b|\.transform\(\s*[\"']sum[\"']"
    )
    racine = Path(__file__).parents[1]
    suspects = [
        f"{chemin.relative_to(racine).as_posix()}:{n}"
        for chemin in sorted(racine.rglob("*.py"))
        if "governance" not in chemin.parts
        for n, ligne in enumerate(chemin.read_text(encoding="utf-8").splitlines(), 1)
        if motifs.search(ligne) and not ligne.lstrip().startswith("#")
    ]
    if suspects:
        ecarts.append("décalage non causal : " + ", ".join(suspects))

    return {
        "passed": not ecarts,
        "evidence": (
            "aucun décalage négatif ni fenêtre centrée dans l'ingestion et les "
            "features ; chaîne reconstruite et vérifiée sur trois troncatures "
            "du corpus (40, 60, 80 %)"
            if not ecarts else " ; ".join(ecarts)
        ),
        "anomalies": ecarts,
    }


def _regime_summary(oof: pd.DataFrame) -> list[dict[str, Any]]:
    """Décrit où le modèle dérive sans prétendre identifier une cause."""
    if oof.empty:
        return []
    data = oof.copy()
    median_t = float(data["T_ACID_IN"].median())
    median_load = float(data["LOAD_SULFUR"].median())
    data["regime"] = np.select(
        [
            (data["T_ACID_IN"] >= median_t) & (data["LOAD_SULFUR"] >= median_load),
            (data["T_ACID_IN"] >= median_t) & (data["LOAD_SULFUR"] < median_load),
            (data["T_ACID_IN"] < median_t) & (data["LOAD_SULFUR"] >= median_load),
        ],
        ["chaud_charge_haute", "chaud_charge_basse", "froid_charge_haute"],
        default="froid_charge_basse",
    )
    return [
        {
            "regime": str(name),
            "n": len(group),
            "alert_rate": round(float(group["alert"].mean()), 4),
            "score_median": round(float(group["score"].median()), 4),
        }
        for name, group in data.groupby("regime", observed=True)
    ]


@dataclass(frozen=True)
class ValidationReport:
    generated_from: dict[str, Any]
    scientific_status: str
    predictive_claim: str
    feature_audit: dict[str, Any]
    temporal_backtest: dict[str, Any]
    deployment_gates: list[dict[str, Any]]
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_from": self.generated_from,
            "scientific_status": self.scientific_status,
            "predictive_claim": self.predictive_claim,
            "feature_audit": self.feature_audit,
            "temporal_backtest": self.temporal_backtest,
            "deployment_gates": self.deployment_gates,
            "limitations": self.limitations,
        }


def validate_unsupervised_detector(
    features: pd.DataFrame,
    *,
    readings: pd.DataFrame,
    quality: pd.DataFrame,
    domain: DomainKnowledge,
    references: References,
    contamination: float,
    random_state: int,
    n_splits: int = 4,
    gap_hours: int = 24,
) -> ValidationReport:
    """Backtest de toute la chaîne sur un calendrier horaire.

    Chaque fold réajuste le modèle thermique, reconstruit les features causales,
    ajuste le scaler et l'Isolation Forest sur le passé uniquement, laisse un
    gap calendaire, puis score la fenêtre suivante.
    """
    if len(readings) < 500:
        raise ValueError("Au moins 500 observations sont requises")

    calendar = pd.date_range(readings.index.min(), readings.index.max(), freq="h")
    calendar_readings = readings.reindex(calendar)
    calendar_readings.index.name = readings.index.name or "timestamp"
    splitter = TimeSeriesSplit(n_splits=n_splits, gap=gap_hours)

    folds: list[dict[str, Any]] = []
    rates: list[float] = []
    psis: list[float] = []
    oof_parts: list[pd.DataFrame] = []
    for fold_no, (train_idx, test_idx) in enumerate(splitter.split(calendar), start=1):
        train_end = calendar[train_idx[-1]]
        test_start, test_end = calendar[test_idx[0]], calendar[test_idx[-1]]
        history = calendar_readings.loc[:test_end]
        quality_history = quality[quality["timestamp"] <= test_end] if len(quality) else quality

        physics_train = add_physics_features(history.loc[:train_end], domain)
        # Les DEUX references sont reajustees sur le seul passe du fold : sans
        # cela, la reference d'entree verrait le futur et le backtest serait faux.
        # UA exige la temperature d'eau de mer et la conductance mesuree :
        # elles sont ajoutees au sous-ensemble d'apprentissage du fold.
        physics_train = physics_train.assign(
            T_SEAWATER=seawater_temperature(physics_train.index),
        )
        physics_train["ua_kw_per_k"] = overall_conductance(
            physics_train["T_ACID_IN"], physics_train["T_ACID_OUT"],
            physics_train["rho_cp"] * physics_train["F_ACID"],
            physics_train["T_SEAWATER"],
        ).where(physics_train["process_state"].eq("RUNNING"))

        fold_refs = References(
            conductance=ConductanceReference().fit(physics_train, reference_end=train_end),
            effort=RegulationEffortReference().fit(physics_train, reference_end=train_end),
            inlet=InletReference().fit(physics_train, reference_end=train_end),
        )
        fold_features, _ = build_features(
            history,
            quality_history,
            domain,
            references=fold_refs,
            fit_references=False,
        )
        matrix = model_matrix(fold_features)
        train = matrix.loc[:train_end]
        test = matrix.loc[test_start:test_end]
        if len(train) < 100 or len(test) < 50:
            raise ValueError(f"Fold {fold_no} insuffisant: train={len(train)}, test={len(test)}")

        detector = StatisticalDetector(
            features=list(MODEL_FEATURES),
            contamination=contamination,
            random_state=random_state,
        ).fit(train)
        train_scores = detector.score(train)
        test_scores = detector.score(test)
        alert = test_scores >= detector.threshold_
        rate = float(np.mean(alert))
        psi = _population_stability_index(train_scores, test_scores)
        rates.append(rate)
        psis.append(psi)

        context = readings.reindex(test.index)[["T_ACID_IN", "LOAD_SULFUR"]]
        oof_parts.append(pd.DataFrame({
            "score": test_scores,
            "alert": alert,
            "T_ACID_IN": context["T_ACID_IN"],
            "LOAD_SULFUR": context["LOAD_SULFUR"],
        }, index=test.index).dropna())
        folds.append({
            "fold": fold_no,
            "train_period": [str(train.index.min()), str(train.index.max())],
            "reference_train_period": list(fold_refs.effort.train_period),
            "test_period": [str(test.index.min()), str(test.index.max())],
            "n_train": len(train),
            "n_test": len(test),
            "gap_calendar_hours": gap_hours,
            "threshold": round(detector.threshold_, 4),
            "test_alert_rate": round(rate, 4),
            "score_psi": round(psi, 4),
            "score_p95": round(float(np.quantile(test_scores, 0.95)), 4),
            "causal_pipeline_refit": True,
        })

    audit = _feature_audit(features)
    mean_rate = float(np.mean(rates))
    max_psi = float(max(psis))
    stable = mean_rate <= max(0.15, contamination * 5) and max_psi <= 0.25
    oof = pd.concat(oof_parts).sort_index() if oof_parts else pd.DataFrame()
    threshold_spread = float(max(f["threshold"] for f in folds) - min(f["threshold"] for f in folds))

    # LES DEUX PORTES QUI NE POUVAIENT PAS ECHOUER.
    #
    # `causalite_temporelle` etait un litteral `True` : aucune mesure, aucune
    # possibilite d'echec. Elle etait de surcroit fausse, le classement d'etat
    # procede lisant l'instant suivant.
    #
    # `redondance_features` ne comptait que les redondances INTERNES a la
    # matrice du modele, en ignorant `shadow_redundancy` — c'est-a-dire
    # exactement la variable que l'audit de redondance avait ete ecrit pour
    # exposer. Elle publiait « 0 paire redondante » deux cents lignes en dessous
    # d'un -0,94 mesure.
    #
    # Les deux sont desormais calculees. La seconde echoue, et c'est le
    # resultat correct.
    causal = _causality_audit(
        features,
        readings=readings,
        quality=quality,
        domain=domain,
        references=references,
    )
    shadow = audit["shadow_redundancy_abs_r_ge_0_80"]
    gates = [
        {
            "gate": "causalite_temporelle",
            "passed": bool(causal["passed"]),
            "evidence": causal["evidence"],
        },
        {
            "gate": "redondance_features",
            "passed": bool(
                not audit["redundant_pairs_abs_r_ge_0_90"]
                and not shadow
                and audit["condition_number"] is not None
            ),
            "evidence": (
                f"{len(audit['redundant_pairs_abs_r_ge_0_90'])} paire(s) redondante(s) "
                f"entre grandeurs du modèle, {len(shadow)} avec une variable "
                f"régulée hors modèle"
                + (
                    f" (la plus forte : {shadow[0]['feature']} contre "
                    f"{shadow[0]['control_variable']}, r = "
                    f"{nombre(shadow[0]['correlation'], 3)})" if shadow else ""
                )
                + f" ; conditionnement {nombre(audit['condition_number'], 2)}"
            ),
        },
        {
            "gate": "stabilite_hors_periode",
            "passed": bool(stable),
            "evidence": (
                f"alertes moyennes {pourcent(mean_rate * 100)} · "
                f"PSI max {nombre(max_psi, 3)} · "
                f"dispersion du seuil {nombre(threshold_spread, 3)}"
            ),
        },
        {
            "gate": "labels_gmao",
            "passed": False,
            "evidence": "aucune date de panne ou d'intervention dans le corpus disponible",
        },
        {
            "gate": "validation_externe",
            "passed": False,
            "evidence": "aucune annotation indépendante — limite définitive du corpus",
        },
    ]
    return ValidationReport(
        generated_from={
            "n_calendar_hours": len(calendar),
            "period": [str(calendar.min()), str(calendar.max())],
            "features": list(MODEL_FEATURES),
            "method": "expanding-window causal sur calendrier horaire",
            "n_splits": n_splits,
            "gap_calendar_hours": gap_hours,
            "pipeline_refit_per_fold": [
                "thermal_reference", "causal_features", "scaler",
                "isolation_forest", "threshold",
            ],
        },
        scientific_status="surveillance comportementale non supervisée, backtestée causalement",
        predictive_claim=(
            "non démontrable avec le corpus disponible; aucune AUC, précision, "
            "rappel ou réduction de panne revendiquée"
        ),
        feature_audit=audit,
        temporal_backtest={
            "folds": folds,
            "mean_test_alert_rate": round(mean_rate, 4),
            "std_test_alert_rate": round(float(np.std(rates)), 4),
            "max_score_psi": round(max_psi, 4),
            "threshold_spread": round(threshold_spread, 4),
            "regime_diagnostics": _regime_summary(oof),
            "interpretation": (
                "Les taux, le PSI et les régimes mesurent stabilité et charge "
                "d'alerte, jamais une performance de détection de panne."
            ),
        },
        deployment_gates=gates,
        limitations=[
            "Aucune vérité terrain panne/intervention GMAO n'est disponible.",
            "La période saine ne peut pas être ancrée sur une révision confirmée.",
            "Les mesures eau de mer, vibration, pression différentielle et corrosion manquent.",
            "Le modèle thermique reconstruit un proxy calculé; son R² n'est pas une preuve d'état.",
            "Le rejeu historique n'est pas une connexion DCS/PI temps réel.",
        ],
    )
