"""
Indicateurs d'exploitation.

Ces tests remplacent l'ancienne suite economique. Ils verifient une propriete
differente et plus utile : qu'aucun indicateur ne repose sur une hypothese, et
que chacun reste calculable a partir des seules donnees mesurees.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.analytics import Figure, OperationalKPI


@pytest.fixture(scope="module")
def kpi(pipeline):
    return OperationalKPI(pipeline.features, pipeline.domain)


def test_les_indicateurs_sont_tous_produits(kpi, pipeline):
    figures = kpi.summary(pipeline.ingestion.sensor_health, pipeline.episodes())
    assert len(figures) == 4
    assert all(isinstance(f, Figure) for f in figures)
    for f in figures:
        assert f.label
        assert f.unit
        assert f.note
        assert f.evidence_level in {"observed", "derived"}


def test_le_niveau_de_preuve_est_declare_pour_chaque_indicateur(kpi, pipeline):
    """Une grandeur passant par la reference thermique n'est pas une mesure."""
    assert kpi.measurement_availability(pipeline.ingestion.sensor_health).evidence_level == "observed"
    assert kpi.corrosion_exposure().evidence_level == "observed"
    # Le regime de sur-refroidissement se lit sur l'ecart de consigne mesure :
    # c'est une observation. La version precedente le publiait en MWh, ce qui
    # en faisait une grandeur DERIVEE de la reference thermique — et ouvrait
    # une discussion de cout que ce projet n'a pas les donnees pour tenir.
    assert kpi.overcooling_regime().evidence_level == "observed"


def test_la_disponibilite_ne_porte_que_sur_le_perimetre(kpi, pipeline):
    """Les capteurs declares defaillants ne doivent pas ecraser la moyenne.

    TI5303-4X est sature depuis aout 2024 et PHI5306X-3 a ete fige 1 900 h.
    Les inclure ferait tomber la disponibilite affichee sous 80 % et masquerait
    l'etat reel des capteurs reellement surveilles.
    """
    figure = kpi.measurement_availability(pipeline.ingestion.sensor_health)
    assert 90.0 < figure.value <= 100.0
    assert figure.unit == "%"


def test_la_charge_d_alertes_est_ramenee_au_mois(kpi, pipeline):
    """Un systeme qui sature l'exploitant sera desactive, quelle que soit sa performance."""
    figure = kpi.alert_load(pipeline.episodes())
    assert figure.unit == "épisodes/mois"
    assert 0 < figure.value < 60


def test_la_charge_d_alertes_supporte_l_absence_d_episode(kpi):
    figure = kpi.alert_load(pd.DataFrame())
    assert figure.value == 0.0
    assert "Aucun épisode" in figure.note


def test_la_stabilite_de_regulation_est_mensuelle(kpi):
    stability = kpi.control_stability()
    assert not stability.empty
    assert set(stability.columns) == {
        "ecart_moyen_degC", "part_hors_bande_1degC", "heures",
    }
    assert stability["part_hors_bande_1degC"].between(0, 100).all()


def test_le_sur_refroidissement_exige_une_derive_installee(kpi):
    """Compter chaque ecart negatif reviendrait a compter le bruit de regulation."""
    figure = kpi.overcooling_regime()
    assert 0.0 <= figure.value <= 100.0
    assert figure.unit == "% du temps de marche"


def test_le_sur_refroidissement_ne_se_presente_plus_en_energie(kpi):
    """Publier des MWh appelle une question de cout sans reponse defendable.

    L'eau de mer circule de toute facon et la pompe ne module pas : la seule
    grandeur que le projet peut etablir est la part du temps passee sous
    consigne, qui est un reglage de conduite.
    """
    figure = kpi.overcooling_regime()
    assert "MWh" not in figure.unit
    assert "MWh" not in figure.note
    assert "conduite" in figure.note.lower() or figure.value == 0.0


def test_aucun_indicateur_ne_porte_de_montant(kpi, pipeline):
    """Le perimetre du stage est technique : aucune valorisation monetaire."""
    figures = kpi.summary(pipeline.ingestion.sensor_health, pipeline.episodes())
    interdits = {"MAD", "EUR", "USD", "DH", "dirham", "euro"}
    for f in figures:
        rendu = f.to_dict()
        assert not interdits & set(str(rendu).split())
        for mot in ("cout", "coût", "gain", "economie", "économie"):
            assert mot not in rendu["label"].lower()
