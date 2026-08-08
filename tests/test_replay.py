"""Rejeu DCS — causalité, instants incontournables, décimation.

`src/realtime/replay.py` porte la promesse d'honnêteté du projet — « le
simulateur ne voit jamais le futur » — et n'avait **aucun test**. C'est le seul
module de la chaîne dans ce cas.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.pipeline import Analysis
from src.realtime.replay import DCSReplay, _compact


def _analyse(pipeline, table, ts) -> Analysis:
    """Rejoue les trois étages sur la table fournie, sans LLM."""
    detection = pipeline.detector.analyze(table, ts)
    decision = pipeline.agent.analyze(detection, use_llm=False)
    verdict = pipeline.judge.judge(decision, table, use_llm=False)
    return Analysis(detection, decision, verdict)


def _instants_de_marche(pipeline) -> list:
    """Trois horodatages en marche établie, répartis sur le corpus."""
    table = pipeline.features
    marche = table.index[table["process_state"].eq("RUNNING")]
    assert len(marche) > 500, "corpus trop court pour ce contrôle"
    return [marche[int(len(marche) * part)] for part in (0.35, 0.6, 0.85)]


def test_le_rejeu_ne_lit_jamais_l_aval(pipeline):
    """À l'instant t, le résultat ne doit pas dépendre de ce qui suit t.

    CE QUE CE CONTROLE VERROUILLE, ET POURQUOI IL EST ICI PLUTOT QU'AILLEURS.

    L'en-tête de `replay.py` affirmait que « seule la fenêtre [début, t] est
    transmise à la détection ». Le module ne transmet en réalité aucune fenêtre :
    `pipeline.analyze_at(ts)` passe la table ENTIÈRE à ses trois étages, et la
    troncature a lieu deux couches plus bas, dans `detector.analyze` et
    `_recent_exceedances`.

    La propriété est vraie — mais par la discipline des appelés, pas par
    construction. C'est la situation de S7-2. Un consommateur ajouté à
    `analyze_at` qui lirait un quantile sur la table entière la romprait sans
    que rien ne le signale.

    Le contrôle est donc COMPORTEMENTAL, sur le modèle de
    `model_validation._causality_audit` : la même analyse est rejouée sur la
    table complète et sur la table tronquée à `t`, et les deux doivent rendre
    exactement le même résultat.

    Note : ce contrôle était VACUEUX avant la correction du cache de faits du
    Judge (S14-2). Sa clé ne portait que l'horodatage, donc le second appel
    recevait les faits calculés lors du premier — quelle que soit la table.
    """
    table = pipeline.features
    for ts in _instants_de_marche(pipeline):
        complet = _compact(_analyse(pipeline, table, ts))
        tronque = _compact(_analyse(pipeline, table.loc[:ts], ts))
        assert tronque == complet, (
            f"{ts} : l'analyse dépend de données postérieures à cet instant. "
            f"La promesse d'en-tête de `replay.py` est rompue."
        )


def test_un_franchissement_de_seuil_est_analyse_malgre_la_decimation(pipeline):
    """La décimation ne doit pas escamoter un franchissement de seuil.

    CE TEST ÉTAIT UNE TAUTOLOGIE — je l'avais écrit ainsi en S14. Il calculait

        ordinaires = set(index[::pas])
        rejoues    = set(index[index.isin(ordinaires | obligatoires)])
        assert not (obligatoires & set(index)) - rejoues

    c'est-à-dire qu'il **réimplémentait la sélection de `run_sync`**, puis
    vérifiait sa propre réimplémentation. `isin` garantit par construction que
    tout élément d'`obligatoires` présent dans l'index se retrouve dans
    `rejoues` : l'assertion ne pouvait pas échouer, quel que soit le code du
    rejeu. C'est la règle 4 de la méthode du dépôt — *ne réimplémente pas pour
    tester, importe le prédicat réel* — enfreinte par le test censé la servir.

    Le contrôle passe désormais par `run_sync`, donc par le vrai chemin de
    sélection. Il vise l'instant que le motif de `_instants_incontournables`
    documente : le seul horodatage critique de quatorze mois, dont la position
    n'est pas multiple du pas d'allègement.
    """
    replay = DCSReplay(pipeline, speed=1e9, analyze_every=7)
    obligatoires = sorted(replay._obligatoires)
    assert obligatoires, "aucun franchissement de seuil détecté sur le corpus"

    # On choisit un franchissement dont la POSITION n'est pas multiple du pas :
    # c'est exactement le cas que la décimation faisait disparaître.
    index = list(pipeline.features.index)
    cible = next(
        (ts for ts in obligatoires
         if ts in pipeline.features.index and index.index(ts) % 7 != 0),
        None,
    )
    if cible is None:
        pytest.skip("aucun franchissement en position non multiple du pas")

    # Rejeu démarré peu avant la cible, borné : on éprouve le chemin réel.
    depart = index[max(0, index.index(cible) - 3)]
    cible_replay = DCSReplay(
        pipeline, speed=1e9, start=str(depart), analyze_every=7
    )
    analyses = list(cible_replay.run_sync(limit=6))
    # COMPARER DES INSTANTS, PAS DEUX ECRITURES D'INSTANTS.
    # `DetectionResult.timestamp` est une chaine ISO 8601 — « 2024-01-15T15:00:00 »
    # — tandis que `str(pd.Timestamp)` rend « 2024-01-15 15:00:00 ». Une premiere
    # version de ce test comparait les deux chaines et echouait sur le separateur,
    # en accusant le rejeu d'avoir saute un franchissement qu'il avait analyse.
    # C'est le meme piege que `sans_accents` traite pour le texte : on normalise
    # avant de comparer, sinon le controle mesure la mise en forme.
    instants = {pd.Timestamp(a.detection.timestamp) for a in analyses}

    assert pd.Timestamp(cible) in instants, (
        f"le franchissement du {cible} n'a pas été analysé alors que sa "
        f"position n'est pas multiple du pas d'allègement {7} : la garantie "
        f"de `_instants_incontournables` ne tient pas dans `run_sync`"
    )



def test_une_limite_de_zero_ne_rejoue_rien(pipeline):
    """`limit=0` demande zéro instant, pas le corpus entier.

    `if limit:` est l'idiome que `src.domain.knowledge.seuil` existe pour
    abolir : il teste la fausseté au lieu de l'absence. La signature annonce
    `int | None`, donc `0` est une demande légitime — et elle rejouait les
    dix mille heures.
    """
    replay = DCSReplay(pipeline, speed=1e9, analyze_every=500)
    assert list(replay.run_sync(limit=0)) == []
    assert replay.state.n_processed == 0

    deux = list(replay.run_sync(limit=2))
    assert len(deux) == 2


def test_la_vitesse_publiee_est_celle_qui_est_appliquee(pipeline):
    """Le pas d'allègement ne doit pas entrer dans la temporisation.

    Le délai valait `analyze_every / speed` appliqué à chaque heure de process :
    la vitesse effective était `speed / analyze_every`, pendant que l'API
    publiait `speed`. Un facteur trois sur le seul réglage que l'exploitant
    manipule.
    """
    replay = DCSReplay(pipeline, speed=120.0, analyze_every=3)
    assert replay.snapshot()["speed_hours_per_second"] == pytest.approx(120.0)
    replay.set_speed(45.0)
    assert replay.snapshot()["speed_hours_per_second"] == pytest.approx(45.0)
    with pytest.raises(ValueError):
        replay.set_speed(0)
