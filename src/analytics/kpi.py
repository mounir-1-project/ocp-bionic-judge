"""
Indicateurs d'exploitation du refroidisseur E7301.

Ce module ne contient AUCUNE hypothese economique. Chaque grandeur qu'il
produit se calcule directement sur les donnees DCS ingerees et sur le
referentiel metier. Un chiffre sorti d'ici peut etre recalcule par un tiers
a partir de `DATA.xlsx` et de `tags.yaml`, sans rien d'autre.

Le champ `evidence_level` distingue deux natures de resultat :

  observed  la grandeur est lue directement dans les donnees et dans le
            referentiel : disponibilite des mesures, heures d'exposition aux
            conditions corrosives. Un tiers la recalcule avec `DATA.xlsx` et
            `tags.yaml`, sans rien d'autre.
  derived   la grandeur passe par un artefact AJUSTE — l'une des trois
            references thermiques, ou le detecteur statistique. Elle herite
            donc du choix de la periode de reference, dont
            `src.governance.sensitivity` chiffre l'effet.

Cette distinction n'est pas cosmetique : une grandeur `derived` herite des
limites du modele de reference et ne doit jamais etre presentee comme une
mesure.

KPI-1 — LE CHAMP ETAIT DEVENU UNE CONSTANTE, ET SON EXEMPLE UN FANTOME.
Cet en-tete citait « energie evacuee en exces » comme exemple de grandeur
`derived`. C'est precisement le chiffre que `overcooling_regime` explique
avoir RETIRE, en MWh, parce qu'il « deplacait un constat de conduite vers un
registre economique que ce projet n'a pas les donnees pour traiter ». Le seul
producteur de `derived` ayant disparu, les six indicateurs annoncaient tous
`observed` : le champ ne distinguait plus rien, et sa documentation renvoyait
a une grandeur qui n'existe plus.

Le defaut n'etait pas seulement decoratif. Trois indicateurs passent par un
artefact ajuste et se declaraient `observed` :

  overcooling_regime  lit `regulation_effort_trend_14d`, residu de la
                      reference d'effort — donc d'une regression apprise.
  alert_load          compte des episodes issus des scores de l'Isolation
                      Forest. Le « ~5 episodes par mois » cite ailleurs dans
                      le projet est un resultat de modele, pas un comptage.
  flag_rate           compare des scores a un seuil, tous deux appris.

Les presenter comme des mesures est exactement ce que le paragraphe ci-dessus
interdit. `test_le_niveau_de_preuve_distingue_reellement_deux_natures`
verrouille la correction.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.domain.knowledge import DomainKnowledge, load_domain, seuil
from src.formatting import heures, nombre, pourcent, unite


@dataclass
class Figure:
    """Un resultat chiffre et sa lecture.

    Attributes:
        label: Intitule lisible par un exploitant.
        value: Valeur calculee.
        unit: Unite du resultat.
        note: Precision de lecture — comment le chiffre a ete obtenu.
        evidence_level: `observed` (lu dans les donnees) ou `derived`
            (passe par la reference thermique).
    """

    label: str
    value: float
    unit: str
    note: str = ""
    evidence_level: str = "observed"

    def to_dict(self) -> dict[str, Any]:
        """Representation serialisable pour l'API."""
        return {
            "label": self.label,
            "value": round(float(self.value), 2),
            "unit": self.unit,
            "note": self.note,
            "evidence_level": self.evidence_level,
        }


class OperationalKPI:
    """Indicateurs calcules uniquement sur les donnees, sans hypothese.

    Ils repondent a des questions que l'exploitant se pose reellement :
    mes mesures sont-elles disponibles, combien d'evenements ce systeme va-t-il
    me demander de traiter, mon faisceau vieillit-il plus vite que prevu,
    est-ce que je refroidis plus que necessaire.

    Attributes:
        f: Table de features complete.
        domain: Connaissance domaine.
        run: Sous-ensemble en marche etablie — seul etat ou juger la performance.
    """

    def __init__(self, features: pd.DataFrame, domain: DomainKnowledge | None = None) -> None:
        """Initialise le calcul des KPI.

        Args:
            features: Table de features issue du pipeline.
            domain: Connaissance domaine.
        """
        self.f = features
        self.domain = domain or load_domain()
        self.run = features[features["process_state"].eq("RUNNING")]

    def control_stability(self, freq: str = "MS") -> pd.DataFrame:
        """Stabilite de la regulation de temperature de sortie acide.

        L'indicateur de conduite le plus parlant du systeme : la part du temps
        pendant laquelle la sortie acide s'ecarte de plus de 1 degC de sa
        consigne. Sur les donnees observees il passe de 0 % (janvier, juin,
        decembre) a plus de 90 % (octobre) — un ecart qu'aucun tableau de bord
        actuel ne fait apparaitre.

        Args:
            freq: Frequence d'agregation pandas.

        Returns:
            DataFrame indexe par periode.
        """
        dev = self.run["control_deviation"].dropna()
        if dev.empty:
            return pd.DataFrame()
        g = dev.groupby(pd.Grouper(freq=freq))
        out = pd.DataFrame({
            "ecart_moyen_degC": g.mean().round(3),
            "part_hors_bande_1degC": (g.apply(lambda s: (s.abs() > 1.0).mean() * 100)).round(1),
            "heures": g.size(),
        })
        return out.dropna()

    def measurement_availability(self, ingestion_health: pd.DataFrame) -> Figure:
        """Disponibilite moyenne des capteurs du perimetre de surveillance.

        Args:
            ingestion_health: Table sensor_health issue de l'ingestion.

        Returns:
            Figure observee.
        """
        scope = ingestion_health[ingestion_health["role"].isin(["primary", "secondary"])]
        return Figure(
            label="Disponibilité moyenne des mesures du périmètre",
            value=float(scope["availability_pct"].mean()),
            unit="%",
            note=f"Calculée sur {len(scope)} capteurs surveillés, "
                 f"{nombre(int(scope['n_bad_timestamps'].sum()), 0)} horodatages "
                 f"en défaut au total. Un horodatage en défaut est écarté du "
                 f"calcul de performance, jamais comblé par interpolation.",
            evidence_level="observed",
        )

    def corrosion_exposure(self) -> Figure:
        """Heures cumulees passees dans des conditions favorisant la corrosion.

        Ni le titre acide sous specification ni la temperature excessive ne
        declenchent une alarme a eux seuls, mais leur CUMUL determine la duree
        de vie du faisceau 904L. Cet indicateur est celui qui interesse le
        service Fiabilite pour arbitrer la date de la prochaine mesure
        d'epaisseurs par courant de Foucault.

        Returns:
            Figure observee.
        """
        c_low = seuil(self.domain.get("C_ACID_1100").threshold("alarm_low"), 98.0)
        t_high = seuil(self.domain.get("T_ACID_IN").threshold("alarm_high"), 100.0)
        mask = (self.run["conc_min"] < c_low) | (self.run["T_ACID_IN"] > t_high)
        hours = int(mask.fillna(False).sum())
        total = len(self.run)
        share = hours / max(total, 1)
        # Un indicateur proche de zero EST un resultat : il etablit que la
        # duree de vie du faisceau n'est pas entamee par les conditions de
        # conduite sur cette periode, et deplace la question vers l'age et
        # l'erosion, que seules les mesures d'epaisseur trancheront.
        lecture = (
            "Sur cette période, la conduite n'expose pratiquement jamais le "
            "faisceau à des conditions agressives : le vieillissement observé "
            "relève de l'âge et de l'érosion, non du régime de marche."
            if share < 0.01 else
            "Exposition significative : à reporter dans l'arbitrage de la "
            "prochaine mesure d'épaisseurs par courant de Foucault."
        )
        return Figure(
            label="Exposition cumulée à des conditions corrosives",
            value=float(hours),
            unit="h",
            note=f"{heures(hours)} sur {heures(total)} de marche "
                 f"({pourcent(share * 100, 2)}). Critères : titre inférieur à "
                 f"{pourcent(c_low, 1)} ou entrée acide supérieure à "
                 f"{unite(t_high, '°C', 0)}. {lecture}",
            evidence_level="observed",
        )

    def overcooling_regime(self) -> Figure:
        """Part du temps de marche passee durablement sous la consigne.

        POURQUOI CE CHIFFRE, ET PAS UNE ENERGIE.
        Une version precedente publiait ce constat en MWh « evacues en exces ».
        La formulation etait trompeuse a deux titres. D'abord parce qu'elle
        appelle immediatement la question du cout, a laquelle la reponse
        honnete est « presque rien » : l'eau de mer circule de toute facon et
        la pompe ne module pas, seule la vanne s'ouvre. Ensuite parce qu'elle
        deplacait un constat de CONDUITE vers un registre economique que ce
        projet n'a pas les donnees pour traiter.

        Le fait interessant n'est pas une quantite d'energie, c'est la part du
        temps ou la boucle tient un point de fonctionnement plus froid que sa
        consigne. C'est un reglage, et un reglage se corrige.

        La definition est stricte : un ecart simplement negatif compterait le
        bruit de regulation autour du point de consigne. On exige plus d'un
        demi-degre sous consigne ET une derive confirmee de la reference,
        c'est-a-dire un regime installe et non une oscillation.

        Returns:
            Figure observee.
        """
        dev = self.run["control_deviation"]
        trend = self.run["regulation_effort_trend_14d"]
        sustained = ((dev < -0.5) & (trend > 1.0)).fillna(False)
        hours = int(sustained.sum())
        total = len(self.run)
        if not hours:
            return Figure(
                label="Marche durablement sous consigne",
                value=0.0,
                unit="% du temps de marche",
                note="Aucun régime de sur-refroidissement installé sur la période.",
                evidence_level="derived",
            )
        mean_dev = float(dev[sustained].mean())
        return Figure(
            label="Marche durablement sous consigne",
            value=100.0 * hours / max(total, 1),
            unit="% du temps de marche",
            note=f"{heures(hours)} sur {heures(total)} de marche, à "
                 f"{unite(abs(mean_dev), '°C')} sous la consigne en moyenne "
                 f"(critère : écart inférieur à -0,5 °C et dérive de la "
                 f"référence au-delà de +1 sigma). Constat de conduite, pas de "
                 f"dégradation : la vanne d'eau de mer travaille plus qu'il "
                 f"n'est nécessaire, ce qui consomme par avance la marge "
                 f"disponible pour compenser un futur encrassement.",
            evidence_level="derived",
        )

    def alert_load(self, episodes: pd.DataFrame) -> Figure:
        """Charge de travail induite par le systeme pour l'exploitant.

        Un systeme qui genere plus d'alertes que l'equipe ne peut en traiter
        sera desactive, quelle que soit sa performance statistique. Ce KPI
        mesure sa soutenabilite.

        Args:
            episodes: Table des episodes agreges.

        Returns:
            Figure observee.
        """
        if episodes.empty:
            return Figure(
                label="Charge d'alertes",
                value=0.0,
                unit="épisodes/mois",
                note="Aucun épisode sur la période.",
                evidence_level="derived",
            )
        span_days = (self.f.index.max() - self.f.index.min()).days or 1
        per_month = len(episodes) * 30.0 / span_days
        return Figure(
            label="Charge d'alertes pour l'exploitant",
            value=float(per_month),
            unit="épisodes/mois",
            note=f"{len(episodes)} épisodes sur {nombre(span_days, 0)} jours, "
                 f"durée médiane {heures(episodes['duration_h'].median())}. "
                 f"À lire avec le taux horaire de signalement : l'agrégation en "
                 f"épisodes rend la charge soutenable, elle ne réduit pas le "
                 f"bruit sous-jacent.",
            evidence_level="derived",
        )

    def flag_rate(self, scores: pd.Series, threshold: float, contamination: float) -> Figure:
        """Part des heures de marche que le systeme signale reellement.

        INDICATEUR AJOUTE APRES AUDIT. Le projet calibrait le detecteur sur une
        contamination de 2 % et n'affichait que la charge d'episodes agreges
        (~5 par mois), ce qui donnait l'impression d'un systeme sobre. Le taux
        HORAIRE reel est cinq fois superieur au parametre de conception, et
        depasse 40 % sur certains mois. Un operateur devant un poste ou quatre
        heures sur dix sont signalees cesse de regarder l'ecran.

        Ce chiffre doit etre affiche a cote de la charge d'episodes, faute de
        quoi l'agregation masque le probleme qu'elle pretend resoudre.

        Args:
            scores: Serie de scores du detecteur.
            threshold: Seuil de decision.
            contamination: Contamination visee a la calibration.

        Returns:
            Figure observee.
        """
        running = self.f["process_state"].eq("RUNNING")
        flagged = (scores >= threshold) & running
        n_run = int(running.sum())
        rate = 100.0 * flagged.sum() / max(n_run, 1)
        ratio = rate / max(contamination * 100.0, 1e-9)
        return Figure(
            label="Taux horaire de signalement en marche",
            value=float(rate),
            unit="%",
            note=f"{heures(int(flagged.sum()))} signalées sur "
                 f"{heures(n_run)} de marche, soit {nombre(ratio)} fois la "
                 f"contamination de calibration ({pourcent(contamination * 100, 0)}). "
                 f"Le seuil est appris sur la période de référence puis appliqué "
                 f"à l'ensemble : hors référence, le taux dérive. C'est le "
                 f"chiffre qui décide si un opérateur continue de regarder "
                 f"l'écran.",
            evidence_level="derived",
        )

    def monthly_flag_rate(self, scores: pd.Series, threshold: float) -> pd.DataFrame:
        """Taux de signalement mois par mois — la ou la moyenne ment.

        Args:
            scores: Serie de scores du detecteur.
            threshold: Seuil de decision.

        Returns:
            DataFrame indexe par mois.
        """
        running = self.f["process_state"].eq("RUNNING")
        flagged = ((scores >= threshold) & running)[running]
        if flagged.empty:
            return pd.DataFrame()
        grouped = flagged.groupby(pd.Grouper(freq="MS"))
        return pd.DataFrame({
            "part_signalee_pct": (grouped.mean() * 100).round(1),
            "heures_marche": grouped.size(),
        }).dropna()

    def summary(self, ingestion_health: pd.DataFrame, episodes: pd.DataFrame) -> list[Figure]:
        """Tous les KPI, dans l'ordre de lecture pour un exploitant.

        Args:
            ingestion_health: Table sensor_health.
            episodes: Table des episodes.

        Returns:
            Liste de Figure.
        """
        return [
            self.measurement_availability(ingestion_health),
            self.alert_load(episodes),
            self.corrosion_exposure(),
            self.overcooling_regime(),
        ]
