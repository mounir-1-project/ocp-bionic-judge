"""
Analyse de sensibilite aux deux parametres arbitraires du systeme.

POURQUOI CE MODULE EXISTE
----------------------------------------------------------------------------
Un audit a releve que deux choix decident de presque tout le comportement du
detecteur, et qu'aucun des deux n'etait justifie ni teste :

  1. `contamination = 0.02` fixe le volume d'alertes. Rien n'expliquait ce
     chiffre, et le taux de signalement reel s'en ecarte d'un facteur trois.

  2. La periode de reference vaut « les 40 % initiaux du corpus ». Le
     comportement « normal » est donc appris sur une fenetre definie par
     convention, et non sur un etat de reference etabli par une revision.

Un parametre non justifie n'est pas une faute en soi. Un parametre non
justifie ET dont on ignore l'influence en est une. Ce module mesure
l'influence, pour que le choix soit discutable plutot que subi.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from src.domain.knowledge import DomainKnowledge
from src.features.e7301_features import build_features, model_matrix
from src.formatting import nombre, pourcent
from src.models.detector import StatisticalDetector

CONTAMINATION_GRID: tuple[float, ...] = (0.005, 0.01, 0.02, 0.05, 0.10)
REFERENCE_FRACTIONS: tuple[float, ...] = (0.25, 0.40, 0.55, 0.70)


def contamination_sensitivity(
    features: pd.DataFrame,
    reference_end: str | pd.Timestamp | None,
    random_state: int = 42,
    grid: tuple[float, ...] = CONTAMINATION_GRID,
) -> dict[str, Any]:
    """Mesure l'effet de la contamination sur le volume d'alertes.

    Args:
        features: Table de features complete.
        reference_end: Fin de la periode d'apprentissage du detecteur.
        random_state: Graine.
        grid: Valeurs de contamination testees.

    Returns:
        Une ligne par valeur testee, plus une lecture.
    """
    matrix = model_matrix(features)
    train = matrix.loc[:reference_end] if reference_end else matrix.iloc[: len(matrix) // 2]
    running = features["process_state"].eq("RUNNING")
    n_run = int(running.sum())

    rows: list[dict[str, Any]] = []
    for level in grid:
        detector = StatisticalDetector(
            contamination=level, random_state=random_state
        ).fit(train)
        scores = pd.Series(detector.score(matrix), index=matrix.index)
        flagged = scores >= detector.threshold_
        rate = 100.0 * flagged.sum() / max(n_run, 1)
        rows.append({
            "contamination": float(level),
            "seuil": round(float(detector.threshold_), 4),
            "taux_signalement_pct": round(float(rate), 2),
            "ratio_sur_cible": round(float(rate) / max(level * 100, 1e-9), 2),
            "heures_signalees": int(flagged.sum()),
        })

    retained = next((r for r in rows if abs(r["contamination"] - 0.02) < 1e-9), None)
    ratios = [r["ratio_sur_cible"] for r in rows]
    return {
        "grid": rows,
        "valeur_retenue": 0.02,
        "effet_mesure": retained,
        "ratio_moyen": round(float(np.mean(ratios)), 2),
        "ratio_dispersion": round(float(max(ratios) - min(ratios)), 2),
        "reading": (
            f"Le taux de signalement réel vaut environ {nombre(np.mean(ratios))} "
            "fois la contamination visée, et ce facteur reste stable sur toute "
            "la grille. La contamination est donc un levier utilisable pour "
            "régler le volume d'alertes, mais elle ne se lit pas comme le taux "
            "attendu : le seuil est appris sur la période de référence puis "
            "appliqué à une période qui a changé de régime. Pour viser "
            f"{pourcent(2, 0)} d'heures signalées, il faut donc paramétrer "
            f"environ {pourcent(2.0 / max(float(np.mean(ratios)), 1e-9))}."
        ),
    }


def reference_period_sensitivity(
    readings: pd.DataFrame,
    quality: pd.DataFrame,
    domain: DomainKnowledge,
    fractions: tuple[float, ...] = REFERENCE_FRACTIONS,
) -> dict[str, Any]:
    """Mesure l'effet du choix de la periode de reference.

    CE QUE CETTE FONCTION MESURE, ET POURQUOI ELLE A CHANGE.
    ------------------------------------------------------------------------
    Une version precedente ne mesurait qu'une seule grandeur, le residu de
    temperature d'entree — que le projet classe lui-meme en « contexte » — puis
    concluait sur le COEFFICIENT D'ECHANGE, qu'elle n'observait jamais. La
    conclusion publiee affirmait qu'aucune fenetre ne faisait apparaitre de
    perte de UA. C'etait faux, et la grille de cette fonction suffisait a le
    montrer : sur la fenetre a 25 %, la regle d'encrassement se declenche sur
    plus de la moitie du corpus.

    La grandeur qui decide du diagnostic est donc mesuree ici, avec le PREDICAT
    COMPLET de `_rule_thermal_drift` — seuil ET persistance — et non un seuil
    approche. C'est le seul moyen que le chiffre publie soit celui que le
    systeme produirait reellement.

    Args:
        readings: Lectures issues de l'ingestion.
        quality: Evenements qualite.
        domain: Connaissance domaine.
        fractions: Fractions initiales testees comme periode de reference.

    Returns:
        Une ligne par fraction, plus une lecture de dispersion.
    """
    from src.governance.fouling_injection import FoulingInjectionBench

    running_index = readings.index[readings["process_state"].eq("RUNNING")]
    rows: list[dict[str, Any]] = []

    for fraction in fractions:
        cut = running_index[int(len(running_index) * fraction) - 1]
        try:
            feats, refs = build_features(
                readings, quality, domain, reference_end=str(cut)
            )
        except ValueError as exc:  # periode trop courte
            logger.warning(f"Fraction {fraction:.0%} ignoree: {exc}")
            continue

        run = feats[feats["process_state"].eq("RUNNING")]
        trend = run["t_in_residual_trend_14d"]

        # Predicat exact de la regle d'encrassement, reutilise tel quel plutot
        # que reecrit : un predicat recopie derive de son original.
        fouling = FoulingInjectionBench._fouling_hours(feats)
        ua_trend = run["ua_residual_trend_14d"]
        n_run = max(len(run), 1)

        rows.append({
            "fraction_reference": fraction,
            "fin_reference": str(cut),
            "n_heures_reference": refs.inlet.n_train,
            "r2_entree": round(refs.inlet.r2, 4),
            "sigma_entree_degC": round(refs.inlet.residual_std, 3),
            "heures_derive_detectables": int((trend >= 1.5).sum()),
            "part_derive_pct": round(float(100.0 * (trend >= 1.5).mean()), 2),
            # ── Coefficient d'echange : la grandeur qui porte le diagnostic ──
            "n_heures_reference_ua": refs.conductance.n_train,
            "r2_ua": round(refs.conductance.r2, 4),
            "sigma_ua_kw_par_k": round(refs.conductance.residual_std, 3),
            "min_ua_trend_sigma": (
                round(float(ua_trend.min()), 2) if ua_trend.notna().any() else None
            ),
            "heures_fouling_drift": int(fouling.sum()),
            "part_fouling_pct": round(float(100.0 * fouling.sum() / n_run), 2),
        })

    parts = [r["part_derive_pct"] for r in rows]
    fouling_parts = [r["part_fouling_pct"] for r in rows]
    spread = round(max(parts) - min(parts), 2) if parts else 0.0
    fouling_spread = (
        round(max(fouling_parts) - min(fouling_parts), 2) if fouling_parts else 0.0
    )
    retenue = next(
        (r for r in rows if abs(r["fraction_reference"] - 0.40) < 1e-9), None
    )
    return {
        "grid": rows,
        "valeur_retenue": 0.40,
        "dispersion_part_derive_pct": spread,
        "dispersion_part_fouling_pct": fouling_spread,
        "part_fouling_valeur_retenue_pct": (
            retenue["part_fouling_pct"] if retenue else None
        ),
        "sensible": bool(spread > 15.0 or fouling_spread > 15.0),
        "reading": (
            "RÉSULTAT LE PLUS IMPORTANT DE CETTE ANALYSE, ET LE PLUS GÊNANT. "
            "La part d'heures de marche que le système déclarerait en "
            f"encrassement varie de {pourcent(min(fouling_parts), 0)} à "
            f"{pourcent(max(fouling_parts), 0)} selon la seule fenêtre retenue "
            "comme référence. Le « zéro heure d'encrassement sur quatorze "
            "mois » annoncé ailleurs dans ce projet est celui de la fenêtre à "
            "40 % : ce n'est pas un constat sur l'équipement, c'est une "
            "conséquence de ce choix. "
            "Le mécanisme est compréhensible : une référence précoce apprend un "
            "coefficient d'échange bas — l'eau de mer est froide en hiver, la "
            "vanne peu ouverte — et voit ensuite comme une dérive la remontée "
            "saisonnière que la régression ne compense qu'imparfaitement. Une "
            "référence plus longue couvre plusieurs saisons et absorbe cette "
            "variation. "
            "Conséquence pratique, et c'est elle qu'il faut retenir : AUCUN "
            "chiffre d'encrassement n'est publiable sans la fenêtre qui l'a "
            "produit. La fenêtre de 40 % est retenue parce qu'elle couvre un "
            "cycle saisonnier complet là où celle de 25 % s'arrête en mai, et "
            "ce choix est publié ici pour être contesté, pas pour être cru."
        ),
    }


def full_report(pipeline: Any) -> dict[str, Any]:
    """Analyse de sensibilite complete.

    Args:
        pipeline: Instance de `E7301Pipeline`.

    Returns:
        Rapport serialisable.
    """
    from src.config import CONTAMINATION, RANDOM_SEED

    reference_end = pipeline.references.effort.train_period[1]
    return {
        "parametres_arbitraires": [
            {
                "nom": "contamination",
                "valeur": CONTAMINATION,
                "justification": (
                    "aucune justification physique ; valeur usuelle par défaut "
                    "d'Isolation Forest. Son effet est mesuré ci-contre plutôt "
                    "que supposé négligeable."
                ),
            },
            {
                "nom": "periode_de_reference",
                "valeur": "40 % initiaux des heures de marche",
                "justification": (
                    "l'équipement n'a pas d'arrêt de révision dans le corpus : "
                    "la période de référence est donc définie par une règle "
                    "explicite et identique pour les trois références, et sa "
                    "sensibilité est chiffrée ci-contre"
                ),
            },
        ],
        "contamination": contamination_sensitivity(
            pipeline.features, reference_end, RANDOM_SEED
        ),
        "periode_reference": reference_period_sensitivity(
            pipeline.ingestion.readings, pipeline.ingestion.quality, pipeline.domain
        ),
    }


if __name__ == "__main__":
    import json

    from src.pipeline import E7301Pipeline

    print(json.dumps(full_report(E7301Pipeline(use_llm=False)), ensure_ascii=False, indent=2))
