"""Validation causale et gouvernance scientifique du système E7301.

Le corpus ne contient aucune vérité terrain de panne. La validation porte donc
sur la stabilité, la causalité temporelle, la robustesse et la charge d'alerte,
jamais sur une précision prédictive inventée.
"""

from __future__ import annotations

import io
import re
import tokenize
from dataclasses import dataclass
from pathlib import Path
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


# BORNE DU PSI — SON ORIGINE, ET CE QU'ELLE NE VAUT PAS ICI.
#
# 0,25 est la borne usuelle du Population Stability Index en SCORING DE CREDIT,
# ou les deux populations comparees sont censees etre echangeables. Le dossier
# n'argumente nulle part son transfert a des scores d'Isolation Forest, et la
# preuve de la porte `derive_de_distribution` le dit.
#
# Elle est nommee UNE SEULE FOIS, exactement pour la raison que le commentaire
# d'`alert_rate_limit` invoque douze lignes plus bas : la version precedente
# l'ecrivait DEUX fois — dans le predicat de la porte et dans la preuve
# affichee — a onze lignes d'ecart. C'est le defaut de S8-2, dans le fichier qui
# porte le principe.
PSI_LIMIT = 0.25


def _population_stability_index(
    reference: np.ndarray, observed: np.ndarray
) -> tuple[float, int]:
    """PSI sur déciles de référence, planchers rattachés à la taille d'échantillon.

    LE PLANCHER DES CELLULES VIDES N'ETAIT PAS UN LISSAGE.

    La version precedente ecrasait les deux distributions a `1e-6`, sous le mot
    « lissage ». Sur des deciles de reference — donc `ref_p = 0,1` par
    construction — une seule cellule VIDE cote observe contribue alors

        (1e-6 - 0,1) x ln(1e-6 / 0,1) = 1,1513

    soit, a elle seule, plus de quatre fois la borne de 0,25 opposee au total.
    Le PSI publie comptait donc pour l'essentiel des CELLULES VIDES multipliees
    par une constante arbitraire : le maximum publie, 3,7446, vaut 3,25 fois
    cette contribution.

    Et `1e-6` n'est pas une frequence atteignable : sur les ~1 800 heures d'une
    fenetre de test, la plus petite frequence non nulle vaut 5,6e-4. Le plancher
    est desormais la moitie d'un comptage — la correction de continuite usuelle
    — donc rattache a la taille de l'echantillon au lieu d'etre pose. Meme
    cellule vide, meme corpus : 0,589 au lieu de 1,1513.

    Le NOMBRE de cellules vides est rendu avec la valeur, parce que sans lui
    elle n'est pas interpretable : un PSI de 3,7 peut signifier une distribution
    deplacee ou trois deciles jamais visites, et ce n'est pas le meme constat.

    Args:
        reference: Échantillon qui définit les déciles.
        observed: Échantillon comparé.

    Returns:
        La valeur du PSI, et le nombre de déciles de référence que l'échantillon
        observé laisse vides.
    """
    quantiles = np.unique(np.quantile(reference, np.linspace(0, 1, 11)))
    if len(quantiles) < 3:
        return 0.0, 0
    quantiles[0], quantiles[-1] = -np.inf, np.inf
    ref_hist = np.histogram(reference, bins=quantiles)[0].astype(float)
    obs_hist = np.histogram(observed, bins=quantiles)[0].astype(float)
    n_ref = max(float(ref_hist.sum()), 1.0)
    n_obs = max(float(obs_hist.sum()), 1.0)
    ref_p = np.clip(ref_hist / n_ref, 0.5 / n_ref, None)
    obs_p = np.clip(obs_hist / n_obs, 0.5 / n_obs, None)
    psi = float(np.sum((obs_p - ref_p) * np.log(obs_p / ref_p)))
    return psi, int((obs_hist == 0).sum())


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


# Motifs qui trahissent une lecture de l'aval : decalage negatif, fenetre
# centree, remplissage par l'arriere, agregat TOTAL d'un palier — la version
# historique du detecteur de gel mesurait la longueur totale d'un palier, donc
# son extension dans le futur.
_MOTIFS_NON_CAUSAUX = re.compile(
    r"shift\(\s*-\d|center\s*=\s*True|\.bfill\(|backfill|"
    r"fillna\(\s*method\s*=\s*[\"']b|\.transform\(\s*[\"']sum[\"']"
)


def _code_sans_litteraux(source: str) -> list[str]:
    """Rend les lignes du source, chaînes et commentaires blanchis.

    La numérotation des lignes est conservée : une ligne blanchie reste une
    ligne. Le filtre précédent était `not ligne.lstrip().startswith("#")`, qui
    ne voyait ni un commentaire de fin de ligne ni, surtout, le contenu d'une
    chaîne de caractères.

    Args:
        source: Texte d'un module Python.

    Returns:
        Les lignes du module, littéraux et commentaires remplacés par des
        espaces.
    """
    lignes = [list(ligne) for ligne in source.splitlines()]
    for jeton in tokenize.generate_tokens(io.StringIO(source).readline):
        if jeton.type not in (tokenize.STRING, tokenize.COMMENT):
            continue
        (premiere, depart), (derniere, arrivee) = jeton.start, jeton.end
        for numero in range(premiere, derniere + 1):
            ligne = lignes[numero - 1]
            debut = depart if numero == premiere else 0
            fin = arrivee if numero == derniere else len(ligne)
            for colonne in range(debut, min(fin, len(ligne))):
                ligne[colonne] = " "
    return ["".join(ligne) for ligne in lignes]


def _decalages_non_causaux() -> list[str]:
    """Cherche une lecture du futur dans TOUT `src/`, `governance` compris.

    LE PERIMETRE DISAIT « TOUTE LA CHAINE » ET EXCLUAIT UN REPERTOIRE ENTIER.

    Le balayage precedent portait `if "governance" not in chemin.parts`, sans un
    mot de justification, sous un commentaire annoncant au contraire que « le
    perimetre couvre toute la chaine, pas trois fichiers ».

    La raison reelle etait mecanique, et personne ne l'avait ecrite : le motif
    contient l'alternative `backfill`, donc LA LIGNE DE SOURCE QUI PORTE LE
    MOTIF contient le mot `backfill`. Le balayage se signalait lui-meme. Les
    deux autres occurrences sont dans la docstring de `_causality_audit`, qui
    cite `bfill()` et `shift(-1)` pour expliquer ce qu'elle cherche.

    Les trois etaient donc des CHAINES DE CARACTERES, jamais du code. Blanchir
    les litteraux et les commentaires par tokenisation les fait disparaitre sans
    rien exclure : verifie, le balayage sur `src/` entier, `governance` compris,
    ne rend aucun resultat.

    L'exclusion coutait cher. `sensitivity.py`, `fouling_injection.py` et
    `judge_eval.py` produisent des chiffres publies dans le rapport; un
    `shift(-1)` introduit dans l'un d'eux n'aurait rien declenche, et la porte
    `causalite_temporelle` aurait continue d'afficher « franchie ».

    Un module illisible est declare SUSPECT, jamais ignore : un controle de
    causalite qui echoue en silence vaut moins que pas de controle du tout.

    Returns:
        `fichier:ligne` de chaque décalage trouvé dans du code exécutable.
    """
    racine = Path(__file__).parents[1]
    suspects: list[str] = []
    for chemin in sorted(racine.rglob("*.py")):
        nom = chemin.relative_to(racine).as_posix()
        try:
            lignes = _code_sans_litteraux(chemin.read_text(encoding="utf-8"))
        except (SyntaxError, tokenize.TokenError, UnicodeDecodeError) as erreur:
            suspects.append(f"{nom} : module illisible ({type(erreur).__name__})")
            continue
        suspects.extend(
            f"{nom}:{numero}"
            for numero, ligne in enumerate(lignes, 1)
            if _MOTIFS_NON_CAUSAUX.search(ligne)
        )
    return suspects


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
    fuites_de_pli: list[str],
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
        fuites_de_pli: Manquements releves PLI PAR PLI par le backtest —
            reference ou detecteur ajuste au-dela de la borne d'apprentissage,
            gap calendaire non tenu. Ils etaient auparavant resumes par un
            litteral `causal_pipeline_refit: True` que rien n'agregeait : une
            fuite dans un pli laissait la porte `causalite_temporelle` afficher
            « franchie ».

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

    # Inspection complementaire, bon marche : aucune lecture de l'aval dans le
    # code executable de la chaine — `governance` compris, voir la docstring.
    suspects = _decalages_non_causaux()
    if suspects:
        ecarts.append("décalage non causal : " + ", ".join(suspects))

    if fuites_de_pli:
        ecarts.extend(fuites_de_pli)

    return {
        "passed": not ecarts,
        "evidence": (
            "aucun décalage négatif ni fenêtre centrée dans le code exécutable "
            "de `src`, gouvernance comprise ; chaîne reconstruite et vérifiée "
            "sur trois troncatures du corpus (40, 60, 80 %)"
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
    oof_parts: list[pd.DataFrame] = []
    fuites_de_pli: list[str] = []
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
        psi, deciles_vides = _population_stability_index(train_scores, test_scores)
        rates.append(rate)

        # `causal_pipeline_refit` ETAIT UN LITTERAL `True`.
        #
        # Exactement le defaut que le commentaire des portes denonce vingt
        # lignes plus bas a propos de `causalite_temporelle` — « aucune mesure,
        # aucune possibilite d'echec » — reproduit un cran plus bas, dans le
        # detail des plis. Et `test_backtest_temporel_declare_les_limites`
        # l'affirmait : `assert all(fold["causal_pipeline_refit"] ...)`, c'est-a-dire
        # un test qui verifiait une constante.
        #
        # Ce que le nom promet est desormais MESURE, sur les trois choses qui
        # peuvent le dementir : les trois references, le detecteur, le gap.
        fin_references = max(
            pd.Timestamp(reference.train_period[1])
            for reference in (fold_refs.conductance, fold_refs.effort, fold_refs.inlet)
        )
        fin_detecteur = pd.Timestamp(detector.train_meta_["period"][1])
        gap_mesure = float((test_start - train_end) / pd.Timedelta("1h"))
        refit_causal = bool(
            fin_references <= train_end
            and fin_detecteur <= train_end
            and gap_mesure >= gap_hours
        )
        if not refit_causal:
            fuites_de_pli.append(
                f"pli {fold_no} : références ajustées jusqu'à {fin_references}, "
                f"détecteur jusqu'à {fin_detecteur}, apprentissage borné à "
                f"{train_end}, gap mesuré {nombre(gap_mesure, 1)} h pour "
                f"{gap_hours} h exigées"
            )

        # COUVERTURE SAISONNIERE DE LA FENETRE DE TEST — voir la porte
        # `derive_de_distribution`. La temperature d'eau de mer est la seule
        # entree du systeme exterieure a toute boucle de regulation (ADR-002),
        # et elle est CYCLIQUE sur douze mois. Un backtest a fenetre croissante
        # sur quatorze mois donne donc, par construction, des premiers plis dont
        # la fenetre de test extrapole hors de tout ce que l'apprentissage a vu.
        mer_train = seawater_temperature(train.index)
        mer_test = seawater_temperature(test.index)
        hors_plage = float(
            ((mer_test < mer_train.min()) | (mer_test > mer_train.max())).mean()
        )

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
            # Le gap PUBLIE etait le parametre recu, pas celui obtenu : un champ
            # qui affirme au lieu de constater, comme `causal_pipeline_refit`.
            "gap_calendar_hours": round(gap_mesure, 1),
            "threshold": round(detector.threshold_, 4),
            "test_alert_rate": round(rate, 4),
            "score_psi": round(psi, 4),
            "score_psi_empty_deciles": deciles_vides,
            "seasonal_extrapolation": round(hors_plage, 4),
            "score_p95": round(float(np.quantile(test_scores, 0.95)), 4),
            "causal_pipeline_refit": refit_causal,
        })

    audit = _feature_audit(features)
    mean_rate = float(np.mean(rates))

    # LE PSI NE MESURE UNE DERIVE QUE SUR UN PLI SAISONNIEREMENT COUVERT.
    #
    # Mesure sur le corpus, pli par pli :
    #
    #   pli | heures de test hors de la plage d'eau de mer apprise |  PSI
    #     1 |  73,8 %                                              | 1,989
    #     2 | 100,0 %                                              | 3,745
    #     3 |   5,9 %                                              | 0,580
    #     4 |   0,0 %                                              | 0,068
    #
    # La correspondance est parfaite et monotone. Le maximum publie — 3,7446,
    # celui que le rapport cite — tombe sur le SEUL pli dont la fenetre de test
    # est entierement hors de la plage d'eau de mer que l'apprentissage a vue,
    # et le minimum sur le seul pli qui n'extrapole pas du tout.
    #
    # CE QUE CELA REFUTE. La preuve affichee attribuait ce chiffre a « deux
    # excursions de sur-refroidissement » entre les deux moities de la periode.
    # Les plis 3 et 4 testent les periodes les PLUS TARDIVES, donc les plus
    # eloignees de la reference : cette explication predit qu'ils derivent le
    # plus, et ils derivent le moins, d'un facteur cinquante-cinq. Une
    # affirmation juste par ailleurs, ecrite a cote de chiffres qui la
    # dementent.
    #
    # CE QUE CELA ETABLIT. Le PSI eleve des premiers plis mesure l'ANNEE
    # INCOMPLETE de la fenetre d'apprentissage : une fenetre croissante sur
    # quatorze mois ne peut pas avoir vu un cycle entier d'eau de mer avant son
    # dernier pli. C'est une propriete du PLAN D'EXPERIENCE, pas du modele —
    # aucun commit ne la deplacera, et aucun seuil, de quelque domaine qu'il
    # vienne, n'est interpretable sur un pli qui extrapole.
    #
    # TROISIEME OCCURRENCE DU MEME MOTIF. Un denominateur qui contient des
    # essais ou rien ne pouvait etre mesure : `judge_eval` comptait des
    # mutations qui ne mutaient rien (S6-2), `fouling_injection` des fenetres
    # calmes parce que la ligne etait a l'arret (S7-1), et ce banc-ci des plis
    # qui extrapolent. La porte ne retient donc que les plis couverts.
    plis_couverts = [f for f in folds if f["seasonal_extrapolation"] <= 0.0]
    psi_couverts = [float(f["score_psi"]) for f in plis_couverts]
    max_psi = float(max(f["score_psi"] for f in folds))
    max_psi_couvert = float(max(psi_couverts)) if psi_couverts else None
    # `stable` combinait ces deux mesures par un `and`. Elles sont désormais
    # portées par deux gates distinctes — voir le commentaire de
    # `stabilite_hors_periode` plus bas — et la borne du taux d'alertes est
    # nommée ici pour n'exister qu'en un exemplaire.
    alert_rate_limit = max(0.15, contamination * 5)
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
        fuites_de_pli=fuites_de_pli,
    )
    shadow = audit["shadow_redundancy_abs_r_ge_0_80"]
    gates = [
        {
            "gate": "causalite_temporelle",
            "passed": bool(causal["passed"]),
            "evidence": causal["evidence"],
        },
        # UNE PORTE MESURAIT DEUX PROPRIETES DE NATURES DIFFERENTES.
        #
        # Elle exigeait a la fois l'absence de redondance INTERNE au modele — ce
        # qu'une modification de code peut casser en ajoutant une variable — et
        # l'absence de redondance avec une variable REGULEE HORS MODELE, qui est
        # une propriete algebrique permanente du systeme : le residu d'effort
        # EST l'ecart de consigne, ADR-001 le demontre et
        # `test_effort_de_regulation_est_redondant_et_le_declare` le verrouille
        # a `corr > 0,80` et `independent is False`.
        #
        # Consequence : la porte echouait definitivement, sur une limite que le
        # projet documente et protege. Aucun commit ne pouvait la franchir, et
        # elle bloquait la chaine d'integration avec les deux portes qui
        # attendent des donnees OCP.
        #
        # ON NE MASQUE PAS LA REDONDANCE POUR AUTANT — c'etait le defaut
        # d'origine, corrige a raison : publier « 0 paire redondante » deux
        # cents lignes au-dessus d'un -0,94 mesure etait malhonnete. Elle
        # devient une porte DISTINCTE, publiee, affichee a l'ecran, en echec, et
        # hors de `MANDATORY_GATES` : ni la promotion ni la fusion ne dependent
        # d'une propriete que le projet a choisi d'assumer plutot que de nier.
        {
            "gate": "redondance_features",
            "passed": bool(
                not audit["redundant_pairs_abs_r_ge_0_90"]
                and audit["condition_number"] is not None
            ),
            "evidence": (
                f"{len(audit['redundant_pairs_abs_r_ge_0_90'])} paire(s) redondante(s) "
                f"entre grandeurs du modèle ; conditionnement "
                f"{nombre(audit['condition_number'], 2)}"
            ),
        },
        {
            "gate": "redondance_hors_modele",
            "passed": not shadow,
            "evidence": (
                f"{len(shadow)} grandeur(s) du modèle redondante(s) avec une "
                f"variable régulée hors modèle"
                + (
                    f" — la plus forte : {shadow[0]['feature']} contre "
                    f"{shadow[0]['control_variable']}, r = "
                    f"{nombre(shadow[0]['correlation'], 3)}" if shadow else ""
                )
                + ". Propriété algébrique permanente établie par ADR-001, non "
                "corrigeable par une modification de code : publiée, jamais "
                "bloquante. Le résidu d'effort est conservé sous le nom "
                "`regulation_effort` et ne fonde aucun diagnostic d'encrassement."
            ),
        },
        # MEME STRUCTURE QUE `redondance_features` : DEUX NATURES DANS UN `and`.
        #
        # `stable` valait `mean_rate <= max(0.15, contamination*5) and max_psi <= 0.25`.
        # Sur le corpus : taux d'alertes 7,8 % contre 15 % admis — FRANCHI ; PSI
        # 3,745 contre 0,25 — echoue d'un facteur quinze. La porte n'echouait
        # donc que sur le second terme, et entrainait le premier avec elle.
        #
        # Le taux d'alertes hors periode est une propriete que le code decide :
        # changer la contamination, le seuil ou les variables le deplace. Il
        # reste donc BLOQUANT, et c'est lui le vrai garde de non-regression.
        #
        # Le PSI mesure le deplacement de la distribution des scores entre
        # apprentissage et test. Le corpus en porte un, etabli et explique au
        # § 9.2 du rapport : deux excursions de sur-refroidissement font
        # basculer le regime entre les deux moities de la periode. Aucun commit
        # ne le fera disparaitre.
        #
        # LE SEUIL DE 0,25 N'EST PAS JUSTIFIE POUR CET USAGE — et le constat
        # ouvert par la phase 0.7 est desormais tranche, PAR LA MESURE : sur
        # trois plis sur quatre, le PSI ne mesure aucune derive du modele mais
        # l'annee incomplete de la fenetre d'apprentissage. Le detail et les
        # chiffres sont au-dessus de `plis_couverts`.
        #
        # La mesure est PUBLIEE avec sa reserve, et ne bloque pas. La difference
        # avec `redondance_hors_modele` doit etre dite : cette derniere est
        # algebriquement impossible a franchir, celle-ci ne l'est pas — un
        # modele autrement concu, ou un corpus de deux ans, deplacerait ce
        # chiffre. Elle sort du blocage faute de seuil justifie et faute de plis
        # interpretables, pas faute de sens.
        {
            "gate": "stabilite_hors_periode",
            "passed": bool(mean_rate <= alert_rate_limit),
            "evidence": (
                f"alertes moyennes {pourcent(mean_rate * 100)} hors période de "
                f"référence, pour {pourcent(alert_rate_limit * 100)} "
                f"admis · dispersion du seuil {nombre(threshold_spread, 3)}"
            ),
        },
        {
            "gate": "derive_de_distribution",
            "passed": bool(
                max_psi_couvert is not None and max_psi_couvert <= PSI_LIMIT
            ),
            "evidence": (
                (
                    f"PSI max {nombre(max_psi_couvert, 3)} sur "
                    f"{len(plis_couverts)} pli(s) sur {len(folds)}, pour "
                    f"{nombre(PSI_LIMIT, 2)} admis"
                    if max_psi_couvert is not None
                    else f"aucun des {len(folds)} plis n'est mesurable"
                )
                + ". Seuls comptent les plis dont la fenêtre de test reste dans "
                "la plage d'eau de mer vue à l'apprentissage : ailleurs le PSI "
                "mesure l'année incomplète de la fenêtre croissante, non une "
                "dérive du modèle — il vaut "
                f"{nombre(max_psi, 3)} sur le pli qui extrapole le plus, et le "
                "plus tardif, qui n'extrapole pas, est le plus stable. Le seuil "
                "vient du scoring de crédit, où les populations comparées sont "
                "supposées échangeables ; son transfert à des scores d'anomalie "
                "non supervisés n'est pas argumenté. Mesure publiée, non "
                "bloquante."
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
            "max_score_psi_seasonally_covered": (
                round(max_psi_couvert, 4) if max_psi_couvert is not None else None
            ),
            "n_seasonally_covered_folds": len(plis_couverts),
            "threshold_spread": round(threshold_spread, 4),
            "regime_diagnostics": _regime_summary(oof),
            "interpretation": (
                "Les taux, le PSI et les régimes mesurent stabilité et charge "
                "d'alerte, jamais une performance de détection de panne. Le PSI "
                "d'un pli dont la fenêtre de test sort de la plage d'eau de mer "
                "apprise ne mesure aucune dérive : il mesure que la fenêtre "
                "croissante n'a pas encore vu une année complète."
            ),
        },
        deployment_gates=gates,
        limitations=[
            "Aucune vérité terrain panne/intervention GMAO n'est disponible.",
            "La période saine ne peut pas être ancrée sur une révision confirmée.",
            "Les mesures eau de mer, vibration, pression différentielle et corrosion manquent.",
            "Le modèle thermique reconstruit un proxy calculé; son R² n'est pas une preuve d'état.",
            "Le rejeu historique n'est pas une connexion DCS/PI temps réel.",
            "Le corpus couvre quatorze mois pour un cycle d'eau de mer de douze : "
            "un backtest à fenêtre croissante n'offre qu'un seul pli dont la "
            "fenêtre de test reste dans la plage de température apprise. La "
            "dérive de distribution n'est donc mesurable que sur ce pli.",
        ],
    )
