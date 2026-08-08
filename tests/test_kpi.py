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
    """Une grandeur passant par un artefact ajusté n'est pas une mesure."""
    assert kpi.measurement_availability(
        pipeline.ingestion.sensor_health
    ).evidence_level == "observed"
    assert kpi.corrosion_exposure().evidence_level == "observed"

    # CE TEST NE JUSTIFIAIT QUE LA MOITIÉ DU CRITÈRE QU'IL QUALIFIE.
    #
    # Il affirmait : « le régime de sur-refroidissement se lit sur l'écart de
    # consigne mesuré : c'est une observation », et concluait `observed`.
    # L'écart de consigne est bien mesuré — mais ce n'est pas le critère.
    # `overcooling_regime` exige DEUX conditions, et sa propre docstring le
    # dit : « plus d'un demi-degré sous consigne ET une dérive confirmée de la
    # référence ».
    #
    #     sustained = (dev < -0.5) & (trend > 1.0)
    #
    # `trend` est `regulation_effort_trend_14d`, le résidu de la référence
    # d'effort — donc d'une régression apprise sur la période de référence,
    # dont `src.governance.sensitivity` chiffre l'effet du choix. La seconde
    # moitié du critère, celle que la justification passait sous silence, est
    # exactement ce qui rend l'indicateur dérivé.
    #
    # Retirer les MWh a bien supprimé un registre économique injustifiable ;
    # cela n'a pas transformé la grandeur restante en mesure.
    assert kpi.overcooling_regime().evidence_level == "derived"


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


def test_le_niveau_de_preuve_distingue_reellement_deux_natures(pipeline):
    """`evidence_level` était devenu une constante, et son exemple un fantôme.

    L'en-tête du module citait « énergie évacuée en excès » comme exemple de
    grandeur `derived`. C'est le chiffre que `overcooling_regime` explique
    avoir retiré. Le seul producteur de `derived` ayant disparu, les six
    indicateurs annonçaient tous `observed` — le champ ne distinguait plus
    rien.

    Et le défaut n'était pas décoratif : trois indicateurs passent par un
    artefact ajusté et se déclaraient mesures. La charge d'alertes — **4,1
    épisodes par mois**, soit `58 × 30 / 424 jours` — est un résultat de modèle,
    pas un comptage. Le projet a longtemps cité « ~5 » : la valeur était fausse
    de 22 % en plus d'être mal qualifiée, et qualifier un chiffre ne le vérifie
    pas.

    Ce contrôle exige les deux natures dans la même restitution, et vérifie
    par analyse du source que tout indicateur lisant une grandeur issue d'un
    ajustement est marqué `derived`.
    """
    import ast
    import inspect

    from src.analytics import OperationalKPI

    kpi = OperationalKPI(pipeline.features, pipeline.domain)
    figures = kpi.summary(pipeline.ingestion.sensor_health, pipeline.episodes())
    niveaux = {f.evidence_level for f in figures}
    assert niveaux == {"observed", "derived"}, (
        f"la restitution ne porte plus qu'une seule nature de résultat : "
        f"{sorted(niveaux)}. Un champ qui ne prend qu'une valeur ne distingue "
        f"rien et laisse croire à une graduation."
    )

    # Toute grandeur issue d'un ajustement — résidu de référence, score ou
    # épisode du détecteur — doit être déclarée `derived`.
    # `threshold` NE FIGURE PAS DANS CETTE LISTE, ET C'EST DÉLIBÉRÉ.
    # Le mot désigne deux choses opposées dans ce dépôt : le seuil APPRIS du
    # détecteur, et `Tag.threshold("alarm_low")`, qui lit une valeur gouvernée
    # dans `tags.yaml`. Le retenir comme marqueur accusait `corrosion_exposure`
    # — qui ne lit que les données et le référentiel — d'être un résultat de
    # modèle. Un contrôle qui produit un faux positif sur une figure correcte
    # sera désactivé au premier échec, et ne protégera plus rien.
    # `scores` suffit à désigner les méthodes qui lisent le détecteur.
    ISSUES_D_UN_AJUSTEMENT = (
        "regulation_effort_trend_14d", "ua_residual", "t_in_residual",
        "duty_expected", "ua_expected", "episodes", "scores",
    )
    for nom, methode in inspect.getmembers(OperationalKPI, inspect.isfunction):
        if nom.startswith("_"):
            continue
        source = inspect.getsource(methode)
        if not any(marqueur in source for marqueur in ISSUES_D_UN_AJUSTEMENT):
            continue
        arbre = ast.parse(source.lstrip())
        declares = {
            kw.value.value
            for noeud in ast.walk(arbre)
            if isinstance(noeud, ast.Call)
            and getattr(noeud.func, "id", "") == "Figure"
            for kw in noeud.keywords
            if kw.arg == "evidence_level" and isinstance(kw.value, ast.Constant)
        }
        assert declares <= {"derived"}, (
            f"`{nom}` lit une grandeur issue d'un ajustement et se déclare "
            f"{sorted(declares - {'derived'})} : c'est présenter un résultat "
            f"de modèle comme une mesure."
        )
