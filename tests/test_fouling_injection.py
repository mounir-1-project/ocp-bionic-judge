"""
Banc d'injection d'encrassement.

Ce banc repond a la seule question que le projet ne savait pas traiter : le
detecteur verrait-il un encrassement s'il s'en produisait un ? La regle ne
s'etant jamais declenchee sur les donnees reelles, rien ne permettait de
distinguer « il n'y a pas eu d'encrassement » de « le detecteur ne peut pas
se declencher ».

Ces tests verrouillent la METHODE autant que le resultat : l'injection doit
demarrer dans une fenetre silencieuse, et la detection doit etre attribuable a
la faute injectee.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.governance.fouling_injection import (
    USEFUL_ADVANCEMENT,
    FoulingInjectionBench,
    inject_fouling,
)
from tests.helpers import sans_accents


@pytest.fixture(scope="module")
def bench(pipeline):
    return FoulingInjectionBench(pipeline)


@pytest.fixture(scope="module")
def result(bench):
    return bench.run(severities=(0.10, 0.30), durations_days=(60,))


# ── Modele d'injection ────────────────────────────────────────────────────────

def test_injection_rechauffe_l_entree_progressivement(pipeline):
    """La rampe doit monter progressivement, pas d'un coup."""
    readings = pipeline.ingestion.readings
    start = pd.Timestamp(readings.index[len(readings) // 2])
    injected, advancement = inject_fouling(readings, start, severity=0.30,
                                           duration_days=30)

    assert advancement.max() == pytest.approx(1.0)
    assert advancement.loc[:start].max() == 0.0

    # L'injection agit sur la sortie, via la physique : rien avant la rampe,
    # une sortie plus chaude ensuite puisque l'echangeur evacue moins.
    delta = (injected["T_ACID_OUT"] - readings["T_ACID_OUT"]).dropna()
    assert delta.loc[:start].abs().max() == pytest.approx(0.0, abs=1e-9)
    assert delta.max() > 2.0


def test_injection_ne_touche_pas_les_arrets(pipeline):
    """Un echangeur a l'arret ne doit pas se voir appliquer la rampe."""
    readings = pipeline.ingestion.readings
    start = pd.Timestamp(readings.index[len(readings) // 3])
    injected, _ = inject_fouling(readings, start, severity=0.40, duration_days=30)

    stopped = readings["process_state"].ne("RUNNING")
    diff = (injected.loc[stopped, "T_ACID_OUT"] - readings.loc[stopped, "T_ACID_OUT"])
    assert diff.abs().max() == pytest.approx(0.0, abs=1e-9)


def test_la_degradation_est_monotone(pipeline):
    """Plus l'encrassement avance, plus la sortie est chaude.

    C'est la propriete qui garantit que l'injection est physique : un depot ne
    se resorbe pas tout seul.
    """
    readings = pipeline.ingestion.readings
    start = pd.Timestamp(readings.index[len(readings) // 3])
    injected, advancement = inject_fouling(readings, start, severity=0.40,
                                           duration_days=40)
    delta = (injected["T_ACID_OUT"] - readings["T_ACID_OUT"])
    running = readings["process_state"].eq("RUNNING")

    early = delta[running & (advancement > 0.1) & (advancement < 0.3)].mean()
    late = delta[running & (advancement > 0.8)].mean()
    assert late > early > 0


# ── Methode du banc ───────────────────────────────────────────────────────────

def test_l_injection_demarre_dans_une_fenetre_silencieuse(bench, result):
    """LE POINT DE METHODE.

    Si la rampe demarre la ou les donnees reelles declenchent deja la regle, la
    detection mesuree n'est attribuable a rien. La premiere version de ce banc
    annoncait ainsi 100 % de detection a 0 % d'avancement — un resultat vide.
    """
    control = bench._fouling_hours(bench.pipeline.features)
    for case in result.cases:
        start = pd.Timestamp(case.start)
        window = control.loc[start : start + pd.Timedelta(days=case.duration_days)]
        assert not window.any(), (
            f"la rampe demarre le {start} alors que le temoin declenche deja"
        )


def test_le_temoin_mesure_les_declenchements_sans_faute(result):
    """Le taux sur donnees non modifiees est un resultat, pas un detail."""
    assert result.n_control_hours > 5000
    # `0 <= taux <= 1` est une tautologie : un taux est toujours dans [0, 1].
    # Ce qui doit etre verrouille est le NIVEAU. Sur la periode de reference
    # retenue, la regle ne se declenche sur aucune heure non modifiee : un
    # temoin qui se declencherait rendrait toute detection inattribuable, et le
    # banc lui-meme inexploitable puisque `_quiet_start` ne trouverait aucune
    # fenetre silencieuse.
    assert result.false_positive_rate < 0.02, (
        f"temoin bruyant ({result.false_positive_rate:.1%}) : la detection "
        f"mesuree ne serait plus attribuable a la faute injectee"
    )
    assert result.to_dict()["false_positive_reading"]


# ── Resultats ─────────────────────────────────────────────────────────────────

def test_un_encrassement_franc_est_detecte(result):
    """Une perte de 30 % de UA doit etre vue : sinon le detecteur est inutile."""
    fort = [c for c in result.cases if c.severity >= 0.30]
    assert fort, "scenario fort absent"
    assert all(c.detected for c in fort)


def test_la_detection_est_tardive_et_le_projet_le_dit(result):
    """Le chiffre honnete n'est pas le taux brut mais l'avancement a la detection.

    Sur ce corpus, la detection intervient tard : elle constate la degradation
    plus qu'elle ne l'anticipe. Ce test fige ce constat pour empecher de
    presenter le taux de detection brut comme une performance.
    """
    assert result.detection_rate > result.useful_detection_rate or (
        result.useful_detection_rate == result.detection_rate == 1.0
    )
    assert result.median_advancement is not None
    payload = result.to_dict()
    assert payload["useful_advancement_threshold"] == USEFUL_ADVANCEMENT
    assert "n'est pas la bonne mesure" in payload["reading"]


def test_une_perte_plus_forte_est_vue_plus_tot(result):
    """Propriete de coherence : plus la perte est franche, plus tot on la voit."""
    par_severite = {
        c.severity: c.advancement_at_detection
        for c in result.cases
        if c.advancement_at_detection is not None
    }
    if len(par_severite) >= 2:
        faible = par_severite[min(par_severite)]
        fort = par_severite[max(par_severite)]
        assert fort <= faible + 1e-9, (
            "une perte plus forte devrait etre detectee a un avancement moindre"
        )


def test_le_predicat_du_banc_equivaut_a_la_regle(pipeline):
    """LE TEST QUE LE CODE PRETENDAIT AVOIR.

    `_fouling_hours` evalue directement la condition de `_rule_thermal_drift`
    plutot que d'appeler `analyze` sur 8 800 instants, et son docstring
    affirmait qu'« un test verrouille cette equivalence ». Ce test n'existait
    pas. Deux predicats qui doivent coincider et que rien ne compare finissent
    par diverger — d'autant que celui du banc alimente desormais aussi
    l'analyse de sensibilite, donc un chiffre publie.

    L'equivalence est verifiee sur un echantillon d'instants couvrant les trois
    etats de marche.
    """
    from src.governance.fouling_injection import FoulingInjectionBench

    feats = pipeline.features
    predicat = FoulingInjectionBench._fouling_hours(feats)

    # Echantillon deterministe, suffisamment large pour couvrir les trois etats
    # et les instants ou la tendance est definie.
    instants = list(feats.index[::311])
    assert len(instants) > 20

    ecarts = []
    for ts in instants:
        regle = any(
            f.code == "FOULING_DRIFT"
            for f in pipeline.detector.rules.evaluate(feats.loc[ts], feats.loc[:ts])
        )
        if bool(predicat.loc[ts]) != regle:
            ecarts.append((str(ts), bool(predicat.loc[ts]), regle))

    assert not ecarts, (
        "le predicat du banc diverge de la regle sur "
        f"{len(ecarts)} instant(s) : {ecarts[:3]}"
    )


def test_les_limites_sont_declarees(result):
    """Le banc ne doit jamais etre presente comme une validation terrain.

    La comparaison ignore les accents : elle porte sur le FOND des limites
    declarees, pas sur leur typographie, que `test_typographie` verifie
    separement. Sans cette precaution, accentuer correctement un texte casse le
    test qui le protege — et l'equipe apprend a ne plus l'accentuer.
    """
    limites = result.to_dict()["limitations"]
    assert len(limites) >= 3
    joined = sans_accents(" ".join(limites))
    assert "borne superieure" in joined
    assert "verite terrain" in joined
    # La limite la plus importante : le banc ne simule pas la compensation par
    # la vanne d'eau de mer, donc il est OPTIMISTE.
    assert "favorable" in joined
