"""
Tests des features physiques, des references et du detecteur.

Le point le plus important teste ici n'est plus le signe du residu de duty —
un audit a montre que ce residu vaut, a l'algebre pres, l'ecart de consigne
change de signe, et qu'un test croisant les deux ne pouvait donc pas echouer.

Ce qui est verrouille desormais :
  - la redondance du residu de duty est MESUREE et declaree, pas niee ;
  - le residu de temperature d'entree est bien independant de la boucle ;
  - l'encrassement n'est annonce que sur ce residu independant.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.features.e7301_features import (
    MODEL_FEATURES,
    InletReference,
    RegulationEffortReference,
    add_physics_features,
    independence_report,
    model_matrix,
    rho_cp,
)
from src.governance.model_validation import validate_unsupervised_detector
from src.models.detector import RuleEngine, StatisticalDetector
from tests.helpers import sans_accents

# ── Features physiques ────────────────────────────────────────────────────────

def test_toutes_les_features_modele_presentes(features):
    """Le jeu de features doit contenir toutes les colonnes attendues."""
    feats, _ = features
    for c in MODEL_FEATURES:
        assert c in feats.columns, f"feature manquante: {c}"


def test_delta_t_positif_en_marche(features):
    """Un refroidisseur qui fonctionne doit toujours abaisser la temperature."""
    feats, _ = features
    dt = feats.loc[feats["process_state"].eq("RUNNING"), "delta_t"].dropna()
    assert (dt > 0).mean() > 0.99, "delta_t negatif : l'echangeur rechaufferait l'acide"


def test_features_de_performance_nulles_a_larret(features):
    """Juger la performance d'un echangeur a l'arret n'a aucun sens."""
    feats, _ = features
    stopped = feats[feats["process_state"].eq("STOPPED")]
    # `duty_per_load` figurait ici : c'etait son SEUL lecteur dans tout le
    # depot. Une colonne dont l'unique consommateur est le test qui verifie
    # qu'elle existe ne mesure rien; elle a ete retiree avec `approach_ratio`.
    for c in ("delta_t", "duty_kw", "flow_per_load", "control_deviation"):
        assert stopped[c].isna().all(), f"{c} calcule pendant un arret"


def test_duty_croit_avec_le_debit(domain):
    """Le duty doit augmenter avec le debit, a ecart de temperature constant."""
    idx = pd.date_range("2024-06-01", periods=10, freq="h")
    df = pd.DataFrame({
        "T_ACID_IN": 94.0, "T_ACID_OUT": 66.0,
        "F_ACID": np.linspace(40, 80, 10), "LOAD_SULFUR": 18.0,
        "C_ACID_1100": 98.7, "C_ACID_1200": 98.6,
        "process_state": "RUNNING",
    }, index=idx)
    out = add_physics_features(df, domain)
    assert out["duty_kw"].is_monotonic_increasing


# ── Proprietes physiques ──────────────────────────────────────────────────────

def test_rho_cp_varie_peu_car_les_deux_effets_se_compensent():
    """Resultat mesure, contraire a l'intuition qui avait motive la correction.

    On soupconnait un biais dependant de la temperature, rho et cp variant tous
    deux sur la plage 66-95 degC. La mesure montre qu'ils varient en SENS
    OPPOSES et se compensent presque : le produit rho.cp ne bouge que de ~0.2 %.

    La correlation est conservee — elle est plus juste que la constante — mais
    le projet ne doit PAS presenter ce raffinement comme une correction
    significative. Ce test fige le constat pour empecher de le sur-vendre.
    """
    froid, chaud = rho_cp(66.0), rho_cp(95.0)
    assert froid != chaud
    ecart = abs(chaud - froid) / froid
    assert ecart < 0.01, f"variation inattendue de rho.cp: {ecart:.3%}"

    # Chaque terme varie bien, lui, de plusieurs pour cent.
    from src.features.e7301_features import CP_A, CP_B, RHO_A, RHO_B

    assert abs((RHO_A + RHO_B * 95) - (RHO_A + RHO_B * 66)) / (RHO_A + RHO_B * 66) > 0.01
    assert abs((CP_A + CP_B * 95) - (CP_A + CP_B * 66)) / (CP_A + CP_B * 66) > 0.01


# ── References ────────────────────────────────────────────────────────────────

def test_reference_effort_ajustee(features):
    """La reference d'effort doit s'ajuster et declarer sa part algebrique."""
    _, refs = features
    effort = refs.effort
    assert effort.r2 > 0.85
    assert effort.n_train > 1000
    assert effort.residual_std > 0
    # Le R2 eleve vient de la definition de la cible, pas du modele. Ce chiffre
    # doit rester publie : c'est lui qui empeche de re-vendre le R2 comme preuve.
    assert effort.naive_r2 is not None
    assert effort.naive_r2 > 0.85, "la part non apprise doit rester visible"
    assert effort.r2 - effort.naive_r2 < 0.10, (
        "si le modele apportait vraiment beaucoup, l'analyse d'origine serait a revoir"
    )


def test_reference_entree_ajustee(features):
    """La reference d'entree doit s'ajuster sur un signal libre, donc plus bruite."""
    _, refs = features
    inlet = refs.inlet
    assert 0.2 < inlet.r2 < 0.95, (
        "un R2 tres eleve signalerait une nouvelle tautologie"
    )
    assert inlet.residual_std > 0.5, "residu trop serre pour une variable libre"


def test_effort_de_regulation_est_redondant_et_le_declare(features):
    """LE TEST QUI VERROUILLE LA CORRECTION D'AUDIT.

    Le residu de duty vaut approximativement -rho.cp.F.(T_out - consigne). Il
    n'est donc PAS independant de la variable regulee. Ce test echoue si
    quelqu'un tente de le presenter comme tel, et il documente le chiffre.
    """
    feats, _ = features
    report = independence_report(feats)
    effort = report["regulation_effort_z"]
    assert abs(effort["corr_control_deviation"]) > 0.80, (
        "la redondance mesuree a change : reprendre l'analyse avant de conclure"
    )
    assert effort["independent"] is False


def test_residu_d_entree_est_independant_de_la_boucle(features):
    """Le seul indicateur autorise a fonder une suspicion de degradation."""
    feats, _ = features
    inlet = independence_report(feats)["t_in_residual_z"]
    assert abs(inlet["corr_control_deviation"]) < 0.30
    assert inlet["independent"] is True


def test_reference_refuse_une_periode_trop_courte(features):
    """Ajuster sur trop peu d'heures doit echouer clairement."""
    feats, _ = features
    with pytest.raises(ValueError, match="trop courte"):
        RegulationEffortReference().fit(feats, reference_end="2024-01-02")


def test_reference_non_ajustee_refuse_de_predire(features):
    """Predire sans avoir ajuste doit lever une erreur explicite."""
    feats, _ = features
    with pytest.raises(RuntimeError, match="non ajustee"):
        InletReference().predict(feats)


def test_les_trois_references_partagent_la_meme_periode(features):
    """LE TEST QU'ADR-009 AFFIRMAIT AVOIR.

    ADR-009 conclut par « un test verrouille l'alignement : si une reference
    retrouvait une periode differente des autres, il echoue ». Ce test
    n'existait pas, et l'alignement n'etait pas tenu : chaque `fit` decoupait
    40 % APRES son propre masque d'eligibilite, si bien que les trois
    references s'arretaient a 17 h, 18 h et 21 h du meme jour.

    La borne est desormais calculee une fois sur les heures de marche etablie.
    Les effectifs restent legitimement differents — chaque reference ecarte ses
    propres trous — mais la fenetre temporelle doit etre identique : c'est elle
    qui protege de la fuite de donnees.
    """
    _, refs = features
    fins = {
        "conductance": refs.conductance.train_period[1],
        "effort": refs.effort.train_period[1],
        "inlet": refs.inlet.train_period[1],
    }
    debuts = {
        "conductance": refs.conductance.train_period[0],
        "effort": refs.effort.train_period[0],
        "inlet": refs.inlet.train_period[0],
    }
    assert len(set(fins.values())) == 1, (
        f"les trois references s'arretent a des instants differents : {fins}"
    )
    assert len(set(debuts.values())) == 1, (
        f"les trois references demarrent a des instants differents : {debuts}"
    )


def test_la_borne_de_reference_est_definie_a_un_seul_endroit():
    """Aucun `0.40` en dur ne doit subsister dans la chaine de reference.

    La constante etait recopiee dans `LinearReference.fit` et dans
    `CoolerAnomalyDetector.fit` alors qu'ADR-009 affirme qu'elle est « definie
    une fois ». Trois copies d'un parametre qui decide du resultat central du
    projet finissent par diverger.
    """
    import ast
    from pathlib import Path

    racine = Path(__file__).resolve().parents[1]
    fautifs = []
    for chemin in (
        racine / "src/features/e7301_features.py",
        racine / "src/features/thermal.py",
        racine / "src/models/detector.py",
    ):
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        # La seule occurrence legitime est la definition de la constante.
        lignes_de_definition = {
            noeud.lineno
            for noeud in ast.walk(arbre)
            if isinstance(noeud, ast.Assign)
            and any(
                isinstance(cible, ast.Name) and cible.id == "REFERENCE_FRACTION"
                for cible in noeud.targets
            )
        }
        for noeud in ast.walk(arbre):
            if (
                isinstance(noeud, ast.Constant)
                and isinstance(noeud.value, float)
                and noeud.value == 0.40
                and noeud.lineno not in lignes_de_definition
            ):
                fautifs.append(f"{chemin.name}:{noeud.lineno}")
    assert not fautifs, f"fraction de reference recopiee en dur : {fautifs}"


def test_rho_cp_reste_proche_de_l_ancienne_constante_figee():
    """Le raffinement doit preciser les conclusions, pas les changer.

    `RHO_CP_ACID_REFERENCE` etait declaree « conservee pour les tests de
    non-regression » et n'etait utilisee par aucun test. Elle sert desormais de
    repere : sur toute la plage exploitee, l'evaluation a la temperature doit
    rester dans le voisinage de l'ancienne constante, faute de quoi le passage
    de l'une a l'autre aurait deplace les kW affiches.
    """
    from src.features.e7301_features import RHO_CP_ACID_REFERENCE

    for temperature in (66.0, 80.0, 95.0):
        ecart = abs(rho_cp(temperature) - RHO_CP_ACID_REFERENCE) / RHO_CP_ACID_REFERENCE
        assert ecart < 0.05, (
            f"rho.cp({temperature} degC) s'ecarte de {ecart:.1%} de la constante "
            f"figee : le raffinement change les conclusions au lieu de les preciser"
        )


def test_residus_centres_sur_la_periode_de_reference(features):
    """Sur leur periode d'apprentissage, les deux residus doivent etre centres."""
    feats, refs = features
    for col, ref in (
        ("regulation_effort_z", refs.effort),
        ("t_in_residual_z", refs.inlet),
    ):
        sub = feats.loc[: ref.train_period[1], col].dropna()
        assert abs(sub.mean()) < 0.35, f"{col} decentre: {sub.mean():.3f}"


# ── Moteur de regles ──────────────────────────────────────────────────────────

def _row(**kw):
    """Construit une ligne de features de marche etablie, surchargée au besoin.

    Args:
        **kw: Valeurs a surcharger.

    Returns:
        Serie pandas representant un instant.
    """
    base = {
        "process_state": "RUNNING", "T_ACID_IN": 94.0, "T_ACID_OUT": 66.0,
        "F_ACID": 56.0, "LOAD_SULFUR": 18.5, "conc_min": 98.7,
        "conc_spread": -0.124, "conc_bias_drift_z": 0.0,
        "conc_drop_24h": 0.0, "control_deviation": 0.0,
        "regulation_effort_trend_14d": 0.0, "duty_kw": 1200.0,
        "duty_expected": 1200.0, "n_invalid_tags": 0,
        "t_in_residual_trend_14d": 0.0, "t_in_expected": 94.0,
        "ua_residual_trend_14d": 0.0, "ua_kw_per_k": 19.0,
        "ua_expected": 19.0, "fouling_resistance": 0.0, "T_SEAWATER": 19.0,
    }
    base.update(kw)
    return pd.Series(base)


def _hist(effort: float = 0.0, ua: float = 0.0, n: int = 100) -> pd.DataFrame:
    """Historique constant des tendances suivies.

    Args:
        effort: Tendance de l'effort de regulation.
        ua: Tendance du residu de coefficient d'echange.
        n: Nombre d'heures.

    Returns:
        DataFrame d'historique.
    """
    # L'HISTORIQUE DOIT PORTER UN INDEX TEMPOREL.
    #
    # Ce constructeur laissait l'index entier par defaut, ce qui suffisait tant
    # que la persistance se comptait en LIGNES (`tail(72)`). Depuis qu'elle se
    # compte en HEURES, `_fenetre_calendaire` soustrait un `Timedelta` de la
    # derniere borne : sur un index entier, cela leve
    # `TypeError: unsupported operand type(s) for -: 'int' and 'Timedelta'`.
    #
    # Le defaut etait dans le TEST, pas dans le code : en exploitation,
    # `history` est toujours une tranche de `features`, donc indexee par le
    # temps. Un repli sur le comptage de lignes aurait reintroduit en silence
    # exactement le defaut que la fenetre calendaire corrige.
    return pd.DataFrame(
        {
            "regulation_effort_trend_14d": [effort] * n,
            "ua_residual_trend_14d": [ua] * n,
            "t_in_residual_trend_14d": [0.0] * n,
        },
        index=pd.date_range("2024-06-01", periods=n, freq="h"),
    )


def test_situation_nominale_ne_declenche_rien(domain):
    """Des conditions normales ne doivent produire aucune constatation."""
    findings = RuleEngine(domain).evaluate(_row(), _hist(0.0))
    assert not findings


def test_perte_de_controle_critique(domain):
    """Une sortie acide au-dessus du seuil HH doit etre CRITICAL."""
    findings = RuleEngine(domain).evaluate(_row(T_ACID_OUT=74.0), _hist(0.0))
    codes = {f.code: f for f in findings}
    assert "CONTROL_LOSS_CRITICAL" in codes
    assert codes["CONTROL_LOSS_CRITICAL"].severity == "CRITICAL"
    assert codes["CONTROL_LOSS_CRITICAL"].amdec_mode == "FAISCEAU_BOUCHAGE"


def test_encrassement_annonce_sur_le_coefficient_d_echange(domain):
    """L'encrassement n'est annonce que sur la derive de UA, jamais sur l'effort."""
    findings = RuleEngine(domain).evaluate(
        _row(ua_residual_trend_14d=-2.4, regulation_effort_trend_14d=-2.0,
             ua_kw_per_k=16.2, ua_expected=19.0, fouling_resistance=0.009),
        _hist(effort=-2.0, ua=-2.4),
    )
    codes = {f.code: f for f in findings}
    assert "FOULING_DRIFT" in codes
    assert codes["FOULING_DRIFT"].amdec_mode == "FAISCEAU_BOUCHAGE"
    # La grandeur en cause doit etre nommee dans le message meme. La
    # comparaison ignore les accents : elle porte sur le fond du message, pas
    # sur sa typographie, que `test_typographie` verifie separement.
    assert "coefficient d'echange" in sans_accents(codes["FOULING_DRIFT"].message)


def test_la_gradation_de_l_encrassement_porte_sur_ua(domain):
    """LE TEST QUI EMPECHE UNE BRANCHE MORTE.

    La severite passait en WARNING sur corroboration par l'effort de
    regulation, avec un seuil de -1,5 sigma. Cet indicateur ne descend jamais
    sous -0,99 sigma sur le corpus : la branche WARNING etait inatteignable, et
    la version precedente de ce test l'affirmait pourtant en forcant -2,0.

    Un test qui ne peut passer qu'avec une valeur que les donnees ne
    produisent pas ne verifie rien. La gradation porte desormais sur le
    deficit de coefficient d'echange, et le seuil vient du referentiel.
    """
    seuil = float(domain.modes["FAISCEAU_BOUCHAGE"].signature["warning_sigma"])
    engine = RuleEngine(domain)

    modere = engine.evaluate(
        _row(ua_residual_trend_14d=-(seuil - 1.0), regulation_effort_trend_14d=-2.0),
        _hist(effort=-2.0, ua=-(seuil - 1.0)),
    )
    grave = engine.evaluate(
        _row(ua_residual_trend_14d=-(seuil + 0.5), regulation_effort_trend_14d=0.0),
        _hist(effort=0.0, ua=-(seuil + 0.5)),
    )
    assert {f.code: f for f in modere}["FOULING_DRIFT"].severity == "INFO"
    # L'effort de regulation vaut zero ici : il ne conditionne plus rien.
    assert {f.code: f for f in grave}["FOULING_DRIFT"].severity == "WARNING"


def test_le_seuil_de_gradation_est_atteignable_par_les_donnees(features):
    """Un seuil que le corpus ne franchit jamais est une branche morte.

    Ce test mesure le domaine REELLEMENT atteint par l'indicateur qui gradue
    l'alerte, et echoue si le seuil de gouvernance en sort. C'est le controle
    qui manquait : sans lui, un seuil peut redevenir inatteignable en silence.
    """
    from src.domain.knowledge import load_domain

    feats, _ = features
    run = feats[feats["process_state"].eq("RUNNING")]
    atteint = run["ua_residual_trend_14d"].dropna()
    assert len(atteint) > 1000

    seuil = float(load_domain().modes["FAISCEAU_BOUCHAGE"].signature["warning_sigma"])
    # Le seuil doit rester dans l'ordre de grandeur de ce que l'indicateur
    # produit. On n'exige pas qu'il soit franchi sur CE corpus — l'equipement
    # peut etre sain — mais qu'il reste du meme ordre que la dispersion
    # observee, sans quoi la branche est morte par construction.
    dispersion = float(atteint.std())
    assert 0 < seuil <= 8.0 * dispersion, (
        f"seuil de gradation {seuil} sigma hors de portee : l'indicateur a un "
        f"ecart-type de {dispersion:.2f} sigma sur le corpus"
    )


def test_effort_de_regulation_seul_ne_declare_pas_un_encrassement(domain):
    """LE TEST QUI EMPECHE LA RECHUTE.

    Un deficit d'effort de regulation, sans derive de l'entree, ne prouve rien :
    il redit seulement que la sortie est au-dessus de sa consigne. L'annoncer
    comme un encrassement conduirait a programmer un nettoyage haute pression —
    plusieurs jours d'arret de ligne — sur la foi d'un signal redondant.
    """
    findings = RuleEngine(domain).evaluate(
        _row(regulation_effort_trend_14d=-2.6, control_deviation=1.8, T_ACID_OUT=67.8),
        _hist(effort=-2.6, ua=0.0),
    )
    assert "FOULING_DRIFT" not in {f.code for f in findings}


def test_sur_refroidissement_est_un_regime_de_conduite(domain):
    """Un exces d'effort n'est pas une degradation, et le message doit le dire."""
    findings = RuleEngine(domain).evaluate(
        _row(regulation_effort_trend_14d=2.6, control_deviation=-1.7, T_ACID_OUT=64.3),
        _hist(effort=2.6, ua=0.0),
    )
    codes = {f.code: f for f in findings}
    assert "FOULING_DRIFT" not in codes
    assert "OVERCOOLING_REGIME" in codes
    assert codes["OVERCOOLING_REGIME"].amdec_mode is None
    assert "redondant" in codes["OVERCOOLING_REGIME"].evidence["note"]


def test_derive_non_persistante_ignoree(domain):
    """Un ecart bref ne doit pas etre annonce comme une derive d'encrassement."""
    # Index horaire, pour la meme raison que dans `_hist` : la persistance se
    # mesure en heures et `_fenetre_calendaire` soustrait un `Timedelta`.
    # Les dix dernieres heures portent l'ecart, les soixante-deux precedentes
    # de la fenetre de 72 h sont nominales — la derive n'est donc pas installee.
    hist = pd.DataFrame(
        {
            "regulation_effort_trend_14d": [0.0] * 100,
            "ua_residual_trend_14d": [0.0] * 90 + [-2.5] * 10,
            "t_in_residual_trend_14d": [0.0] * 100,
        },
        index=pd.date_range("2024-06-01", periods=100, freq="h"),
    )
    findings = RuleEngine(domain).evaluate(_row(ua_residual_trend_14d=-2.5), hist)
    assert "FOULING_DRIFT" not in {f.code for f in findings}


def test_chute_de_titre_traitee_comme_fuite(domain):
    """Une chute brutale de titre doit remonter le mode FAISCEAU_FUITE."""
    findings = RuleEngine(domain).evaluate(
        _row(conc_min=98.4, conc_drop_24h=-1.1), _hist(0.0)
    )
    codes = {f.code: f for f in findings}
    assert "CONC_DROP_SEVERE" in codes
    assert codes["CONC_DROP_SEVERE"].severity == "CRITICAL"
    assert codes["CONC_DROP_SEVERE"].amdec_mode == "FAISCEAU_FUITE"


def test_biais_normal_entre_analyseurs_ne_declenche_rien(domain):
    """L'ecart HABITUEL entre les deux analyseurs ne doit pas alerter.

    Les deux analyseurs suivent des circuits distincts et presentent un biais
    permanent de -0.124 point. Le prendre pour une anomalie generait une alerte
    a chaque heure de marche.
    """
    findings = RuleEngine(domain).evaluate(
        _row(conc_spread=-0.124, conc_bias_drift_z=0.0), _hist(0.0)
    )
    assert "CONC_BIAS_DRIFT" not in {f.code for f in findings}


def test_derive_du_biais_entre_analyseurs_est_detectee(domain):
    """Un ecart qui s'eloigne de sa valeur habituelle signale un analyseur qui part.

    C'est le test qui remplace l'ancien seuil absolu de 0.6 point : celui-ci
    representait 6 sigma et ne se declenchait donc pratiquement jamais.
    """
    findings = RuleEngine(domain).evaluate(
        _row(conc_spread=0.3, conc_bias_drift_z=5.4), _hist(0.0)
    )
    codes = {f.code: f for f in findings}
    assert "CONC_BIAS_DRIFT" in codes
    assert codes["CONC_BIAS_DRIFT"].amdec_mode == "CAPTEUR_DEFAILLANT"
    assert codes["CONC_BIAS_DRIFT"].severity == "WARNING"


def test_conc_min_ne_pretend_plus_etre_une_redondance(features):
    """Le titre gouvernant suit AI1200, et le systeme doit l'assumer.

    AI1200 est inferieur a AI1100 dans 94.9 % des cas : un min() des deux
    revient a n'utiliser qu'un capteur. Ce test verrouille le constat pour
    qu'aucune evolution future ne reintroduise l'illusion de redondance.
    """
    feats, _ = features
    run = feats[feats["process_state"].eq("RUNNING")].dropna(
        subset=["C_ACID_1100", "C_ACID_1200"]
    )
    part = (run["C_ACID_1200"] < run["C_ACID_1100"]).mean()
    assert part > 0.85, (
        f"AI1200 n'est le minimum que dans {part:.1%} des cas — le biais entre "
        f"analyseurs a change, revoir cross_check_expected_bias dans tags.yaml"
    )


def test_temperature_entree_excessive_lie_a_la_corrosion(domain):
    """Une entree acide trop chaude releve du mode corrosion."""
    findings = RuleEngine(domain).evaluate(_row(T_ACID_IN=106.0), _hist(0.0))
    codes = {f.code: f for f in findings}
    assert codes["T_IN_HIGH_HIGH"].amdec_mode == "FAISCEAU_CORROSION"


def test_arret_suspend_la_surveillance_de_performance(domain):
    """A l'arret, aucune regle de performance ne doit s'appliquer."""
    findings = RuleEngine(domain).evaluate(
        _row(process_state="STOPPED", T_ACID_OUT=80.0), _hist(0.0)
    )
    codes = {f.code for f in findings}
    assert codes == {"NOT_RUNNING"}


# ── Detecteur statistique ─────────────────────────────────────────────────────

def test_detecteur_refuse_trop_peu_dechantillons():
    """Ajuster sur trop peu de donnees doit echouer clairement."""
    X = pd.DataFrame(np.zeros((10, len(MODEL_FEATURES))), columns=MODEL_FEATURES)
    with pytest.raises(ValueError, match="Trop peu"):
        StatisticalDetector().fit(X)


def test_detecteur_non_ajuste_refuse_de_scorer():
    """Scorer sans ajustement doit lever une erreur explicite."""
    X = pd.DataFrame(np.zeros((5, len(MODEL_FEATURES))), columns=MODEL_FEATURES)
    with pytest.raises(RuntimeError, match="non ajuste"):
        StatisticalDetector().score(X)


def test_scores_bornes(pipeline):
    """Les scores doivent rester dans [0, 1] pour etre interpretables."""
    s = pipeline.detector.score_series(pipeline.features)
    assert s.min() >= 0.0 and s.max() <= 1.0


def test_taux_dalerte_operationnellement_supportable(pipeline):
    """Le systeme ne doit pas alarmer en permanence.

    Un detecteur qui signale plus d'un tiers des heures est ignore en salle de
    controle : sa valeur pratique devient nulle, quelle que soit sa precision.
    """
    s = pipeline.detector.score_series(pipeline.features)
    rate = float((s >= pipeline.detector.stat.threshold_).mean())
    assert rate < 0.35, f"taux d'alerte trop eleve: {rate:.1%}"


def test_agregation_en_episodes(pipeline):
    """Les heures atypiques doivent etre regroupees en episodes exploitables."""
    ep = pipeline.episodes()
    assert len(ep) > 0
    assert len(ep) < 300, "trop d'episodes pour etre traites par un exploitant"
    assert (ep["duration_h"] >= 3).all()
    assert ep["score_max"].is_monotonic_decreasing


def test_le_rattachement_ne_cite_que_des_features_du_modele():
    """Une entree portant sur une grandeur hors modele est inatteignable.

    `_MODE_BY_RESIDUAL` citait `ua_residual_trend_14d`, `fouling_resistance` et
    `n_invalid_tags`, absentes de `MODEL_FEATURES` : l'attribution ne peut
    jamais les retourner comme contribution dominante. Trois entrees sur cinq
    ne servaient a rien tout en suggerant une couverture plus large.
    """
    from src.models.detector import CoolerAnomalyDetector

    hors_modele = (
        set(CoolerAnomalyDetector._MODE_BY_RESIDUAL)
        | set(CoolerAnomalyDetector._MODE_BY_THRESHOLD)
        | set(CoolerAnomalyDetector._FEATURES_SANS_ACCUSATION)
    ) - set(MODEL_FEATURES)
    assert not hors_modele, (
        f"rattachements portant sur des grandeurs hors MODEL_FEATURES, donc "
        f"jamais atteignables : {sorted(hors_modele)}"
    )


def test_toute_entree_de_rattachement_peut_reellement_accuser(domain):
    """M-3 — Ce test verrouillait l'appartenance, pas l'ATTEIGNABILITÉ.

    `_MODE_BY_THRESHOLD` portait quatre entrées, dont trois avec un tag et un
    seuil vides. `_mode_for_feature` sort sur `if not tag_name: return None` :
    trois sur quatre rendaient invariablement `None`. La table paraissait
    rattacher quatre grandeurs à trois modes de défaillance et n'en rattachait
    qu'une — la « couverture illusoire » que le commentaire voisin condamne, à
    quinze lignes de son propre correctif.

    Le comportement était juste ; c'est la forme qui mentait. Les trois
    grandeurs de variation sont désormais déclarées pour ce qu'elles sont, dans
    `_FEATURES_SANS_ACCUSATION`, et la table ne contient plus que ce qui peut
    réellement accuser.

    Ce contrôle exige les trois propriétés qui manquaient : chaque entrée porte
    un tag et un seuil non vides, ce seuil existe dans le référentiel, et les
    deux ensembles sont disjoints.
    """
    from src.models.detector import CoolerAnomalyDetector

    inertes = {
        feature
        for feature, (_, tag, seuil) in CoolerAnomalyDetector._MODE_BY_THRESHOLD.items()
        if not tag or not seuil
    }
    assert not inertes, (
        f"entrées qui ne peuvent jamais accuser : {sorted(inertes)}. Soit leur "
        f"donner un tag et un seuil, soit les déclarer dans "
        f"`_FEATURES_SANS_ACCUSATION`."
    )

    introuvables = {
        f"{feature} -> {tag}.{seuil}"
        for feature, (_, tag, seuil) in CoolerAnomalyDetector._MODE_BY_THRESHOLD.items()
        if domain.get(tag).threshold(seuil) is None
    }
    assert not introuvables, (
        f"seuils absents du référentiel, donc rattachement inatteignable : "
        f"{sorted(introuvables)}"
    )

    modes_cites = {
        mode for mode, _, _ in CoolerAnomalyDetector._MODE_BY_THRESHOLD.values()
    } | {mode for mode, _ in CoolerAnomalyDetector._MODE_BY_RESIDUAL.values()}
    inconnus = modes_cites - set(domain.modes)
    assert not inconnus, f"modes AMDEC inexistants cités : {sorted(inconnus)}"

    chevauchement = (
        set(CoolerAnomalyDetector._MODE_BY_THRESHOLD)
        & CoolerAnomalyDetector._FEATURES_SANS_ACCUSATION
    )
    assert not chevauchement, (
        f"une grandeur ne peut pas à la fois accuser et ne pas accuser : "
        f"{sorted(chevauchement)}"
    )


def test_la_severite_imposee_par_l_amdec_correspond_a_ce_que_les_regles_emettent(domain):
    """`severite_immediate` était une détermination de gouvernance sans effet.

    `amdec.yaml` déclare `signature.severite_immediate` pour deux modes :
    CRITICAL pour FAISCEAU_FUITE, WARNING pour CAPTEUR_DEFAILLANT. Le champ
    est chargé par `FailureMode.immediate_severity` — et **aucun appelant ne
    le lisait**. Le service fiabilité pouvait donc le corriger dans le
    référentiel sans que rien ne change dans la chaîne.

    L'appliquer comme plancher casserait une gradation voulue : `CONC_DROP`
    est délibérément WARNING (« à confirmer par prélèvement laboratoire »)
    alors qu'il porte FAISCEAU_FUITE. La sémantique juste est donc : la
    sévérité déclarée est celle que le mode atteint AU PLUS HAUT.

    Ce test l'établit par analyse du source de `RuleEngine`, sans exécuter
    aucune règle : il lit les `Finding(...)` construits, apparie `amdec_mode`
    et `severity`, et compare au référentiel. Une règle qu'on abaisserait ou
    qu'on relèverait sans reprendre l'AMDEC fait échouer ce test.
    """
    import ast
    import inspect

    from src.models.detector import SEVERITY_ORDER, RuleEngine

    arbre = ast.parse(inspect.getsource(RuleEngine))
    par_mode: dict[str, set[str]] = {}
    for noeud in ast.walk(arbre):
        if not (isinstance(noeud, ast.Call)
                and isinstance(noeud.func, ast.Name)
                and noeud.func.id == "Finding"):
            continue
        args = {kw.arg: kw.value for kw in noeud.keywords}
        mode, severite = args.get("amdec_mode"), args.get("severity")
        if not (isinstance(mode, ast.Constant) and isinstance(severite, ast.Constant)):
            continue  # sévérité calculée ou mode déduit : hors de portée statique
        if mode.value:
            par_mode.setdefault(mode.value, set()).add(severite.value)

    assert par_mode, "aucune construction de Finding lisible : l'analyse a dérivé"

    for code, mode in domain.modes.items():
        imposee = mode.immediate_severity
        if imposee is None:
            continue
        emises = par_mode.get(code)
        assert emises, (
            f"{code} impose une sévérité {imposee} dans amdec.yaml, mais aucune "
            f"règle ne lui rattache de constatation : la détermination est morte."
        )
        atteinte = max(emises, key=lambda s: SEVERITY_ORDER[s])
        assert atteinte == imposee, (
            f"{code} : amdec.yaml impose {imposee}, les règles plafonnent à "
            f"{atteinte} (sévérités émises : {sorted(emises)})."
        )


def test_attribution_somme_a_quelque_chose_dinterpretable(pipeline):
    """L'attribution doit designer des features reelles et ordonnees."""
    ep = pipeline.episodes()
    r = pipeline.detector.analyze(pipeline.features, ep.iloc[0]["peak_at"])
    if r.attributions:
        contribs = [a["contribution"] for a in r.attributions]
        assert contribs == sorted(contribs, reverse=True)
        assert all(a["feature"] in MODEL_FEATURES for a in r.attributions)


def test_reproductibilite(features):
    """Deux entrainements avec la meme graine doivent donner le meme seuil."""
    feats, _ = features
    X = model_matrix(feats).iloc[:2000]
    a = StatisticalDetector(random_state=42).fit(X)
    b = StatisticalDetector(random_state=42).fit(X)
    assert a.threshold_ == pytest.approx(b.threshold_)
    np.testing.assert_allclose(a.score(X.iloc[:50]), b.score(X.iloc[:50]))


def test_horodatage_inconnu_leve_une_erreur(pipeline):
    """Analyser un instant absent doit echouer explicitement."""
    with pytest.raises(KeyError):
        pipeline.detector.analyze(pipeline.features, "2030-01-01")


def test_features_modele_non_redondantes(features):
    """Le modèle ne doit pas compter deux fois la même grandeur physique."""
    feats, _ = features
    corr = model_matrix(feats).corr().abs()
    pairs = [
        (left, right, corr.loc[left, right])
        for i, left in enumerate(corr.columns)
        for right in corr.columns[i + 1:]
        if corr.loc[left, right] >= 0.90
    ]
    assert not pairs, f"features redondantes: {pairs}"


def test_backtest_temporel_declare_les_limites(features, ingestion, domain):
    """La validation mesure la stabilité sans inventer de performance de panne."""
    feats, refs = features
    report = validate_unsupervised_detector(
        feats,
        readings=ingestion.readings,
        quality=ingestion.quality,
        domain=domain,
        references=refs,
        contamination=0.02,
        random_state=42,
        n_splits=3,
    ).to_dict()
    assert len(report["temporal_backtest"]["folds"]) == 3
    assert "non démontrable" in report["predictive_claim"]
    labels_gate = next(
        gate for gate in report["deployment_gates"] if gate["gate"] == "labels_gmao"
    )
    assert labels_gate["passed"] is False

    # CETTE ASSERTION VERIFIAIT UNE CONSTANTE. `causal_pipeline_refit` etait un
    # litteral `True` dans le dictionnaire de pli : le test ne pouvait pas
    # echouer, quoi qu'il arrive a la chaine. C'est le defaut que le fichier
    # denonce lui-meme a propos de la porte `causalite_temporelle`, reproduit
    # un cran plus bas et verrouille par un test complice.
    #
    # Le champ est desormais MESURE — fin d'ajustement des trois references, du
    # detecteur, et gap calendaire reellement obtenu. L'assertion porte donc.
    plis = report["temporal_backtest"]["folds"]
    assert all(fold["causal_pipeline_refit"] for fold in plis)
    for fold in plis:
        assert fold["gap_calendar_hours"] >= 24
        assert 0.0 <= fold["seasonal_extrapolation"] <= 1.0
        assert fold["score_psi_empty_deciles"] >= 0

    # Une fuite de pli doit remonter jusqu'a la porte, pas rester dans le
    # detail : elle n'etait agregee nulle part.
    causal_gate = next(
        gate for gate in report["deployment_gates"] if gate["gate"] == "causalite_temporelle"
    )
    assert causal_gate["passed"] is True
