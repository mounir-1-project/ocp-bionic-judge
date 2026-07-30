"""
Coefficient d'échange global du refroidisseur E7301.

CE QUE CE MODULE RÉSOUT
----------------------------------------------------------------------------
L'état de la surface d'échange se lit sur le coefficient d'échange global UA.
Toute grandeur construite sur la seule sortie acide est soit aveugle — la
régulation la maintient — soit une réécriture de l'écart de consigne.

Calculer UA exige la température du fluide froid. Elle n'est pas dans l'export
DCS. Elle est néanmoins connue : le refroidisseur est refroidi à l'eau de mer,
à Safi, sur la côte atlantique marocaine, dont la climatologie mensuelle est
documentée et stable d'une année sur l'autre. Le courant des Canaries et
l'upwelling côtier y maintiennent une eau fraîche, de 17 °C en février-mars à
22 °C en septembre.

MÉTHODE
----------------------------------------------------------------------------
1. TEMPÉRATURE D'EAU DE MER — climatologie mensuelle de Safi, interpolée au jour.

2. EFFICACITÉ puis NTU. Le débit d'eau de mer est très supérieur au débit
   acide en capacité thermique : le côté froid se comporte comme une source
   isotherme. On a donc directement

       epsilon = (T_acide_entrée - T_acide_sortie) / (T_acide_entrée - T_eau)
       NTU     = -ln(1 - epsilon)
       UA      = C_acide . NTU

   Cette formulation évite la moyenne logarithmique et sa singularité quand
   les écarts aux deux extrémités se rapprochent.

3. NORMALISATION AUX CONDITIONS. UA dépend légitimement du régime : le débit
   acide gouverne la turbulence côté calandre (terme en débit^0,8, forme de
   Dittus-Boelter), la viscosité de l'acide chute avec la température, et la
   température d'eau de mer fixe le point de fonctionnement de la boucle
   froide. Une référence linéaire apprend UA(débit, température moyenne, eau
   de mer) sur la PÉRIODE DE RÉFÉRENCE UNIQUEMENT ; le RÉSIDU est l'indicateur.

4. RÉSISTANCE D'ENCRASSEMENT. Rf = 1/UA - 1/UA_attendu, en K/kW, où UA_attendu
   est la valeur prédite AUX CONDITIONS DE L'INSTANT. Une valeur positive et
   croissante signale une surface qui transmet moins bien qu'elle ne le devrait.

CE QUE UA EST — ET CE QU'IL N'EST PAS
----------------------------------------------------------------------------
Le débit d'eau de mer n'est pas instrumenté, et c'est LUI que la régulation
manipule pour tenir la consigne de 66 °C. La grandeur calculée ici est donc un
UA APPARENT, produit de deux facteurs :

    UA_apparent  =  état de la surface d'échange  x  action de la boucle froide

La conséquence doit être énoncée franchement : tant que la vanne d'eau de mer
conserve de la marge, elle compense un début d'encrassement et UA_apparent ne
bouge pas. L'indicateur devient sensible quand cette marge se consomme. C'est
pourquoi le banc d'injection (`src.governance.fouling_injection`) ne publie pas
un taux de détection mais l'AVANCEMENT auquel la détection survient : c'est la
mesure de ce retard, et c'est le chiffre honnête.

La signature de cette dépendance est visible dans les données : UA_apparent
suit la température d'eau de mer (13,8 kW/K en janvier, 21,9 en septembre),
parce qu'une eau plus chaude oblige la vanne à s'ouvrir davantage. La
régression retire cette part saisonnière ; le résidu est ce qui reste.

INDÉPENDANCE MESURÉE (corrélation avec l'écart de consigne, marche établie)
----------------------------------------------------------------------------
    regulation_effort_z ...... -0,94   (88 % de variance partagée — redondant)
    ua_residual_z ............ -0,54   (29 % — partiellement confondu)
    t_in_residual_z .......... +0,03   (0,1 % — indépendant, mais confondu
                                        côté procédé : voir InletReference)

Aucun de ces indicateurs n'est parfait, et le projet ne prétend pas le
contraire. UA est retenu pour porter le diagnostic parce qu'il est le seul
dont la grandeur mesurée soit celle que l'encrassement dégrade, et le seul
ancré sur une donnée extérieure à l'atelier.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

import numpy as np
import pandas as pd
from loguru import logger

# ── Climatologie de l'eau de mer, Safi (Atlantique marocain) ─────────────────
#
# Moyennes mensuelles de temperature de surface, en degres Celsius. Le regime
# est domine par le courant des Canaries et l'upwelling cotier : l'eau reste
# fraiche et l'amplitude annuelle est modeste, environ 5 degC. La prise d'eau
# d'un refroidisseur industriel est immergee, donc encore plus stable que la
# surface : ces valeurs constituent une borne haute de l'amplitude reelle.
SEAWATER_MONTHLY_C: dict[int, float] = {
    1: 17.5, 2: 17.0, 3: 17.2, 4: 17.8, 5: 18.6, 6: 19.6,
    7: 20.6, 8: 21.6, 9: 22.0, 10: 21.2, 11: 19.8, 12: 18.4,
}

# Ecart de temperature minimal exige aux bornes pour qu'un calcul d'efficacite
# ait un sens. En dessous, l'echangeur ne travaille pas.
MIN_APPROACH_K = 1.0

# Bornes de l'efficacite. La borne basse evite un logarithme de zero, la borne
# haute une division par zero dans -ln(1 - eps). Toute troncature effective est
# comptee et journalisee : voir `overall_conductance`.
EFFECTIVENESS_MIN = 1e-4
EFFECTIVENESS_MAX = 0.999

# Part des heures de marche etablie servant de periode de reference lorsque
# aucune date de revision n'est fournie. Valeur commune aux trois references du
# systeme; `src.governance.sensitivity` en quantifie l'effet.
REFERENCE_FRACTION = 0.40


def reference_cutoff(
    df: pd.DataFrame, fraction: float = REFERENCE_FRACTION
) -> pd.Timestamp:
    """Borne de fin de la periode de reference, commune aux trois references.

    POURQUOI CETTE FONCTION EXISTE.
    Chaque `fit` decoupait `train.iloc[: int(len(train) * 0.40)]` APRES avoir
    applique son propre masque d'eligibilite. Or ces masques different : la
    conductance exige `ua_kw_per_k`, l'effort exige `duty_kw` et `conc_min`,
    l'entree n'exige que la charge et le debit. Les trois references
    s'arretaient donc a des instants differents — mesure : 2024-07-13 17:00,
    18:00 et 21:00 — alors qu'ADR-009 affirme qu'elles « partagent la meme
    regle ET la meme periode ». La regle etait partagee, la periode non.

    La borne est desormais calculee UNE fois sur les heures de marche etablie,
    independamment de toute disponibilite de mesure, puis appliquee telle
    quelle aux trois. Les effectifs d'apprentissage restent legitimement
    differents — chaque reference ecarte ses propres trous — mais la fenetre
    temporelle est identique, ce qui est la propriete qui protege de la fuite
    de donnees.

    La formule reprend celle de `src.governance.sensitivity`, qui coupait deja
    sur les heures de marche : les deux modules ne peuvent plus diverger.

    Args:
        df: Table contenant la colonne `process_state`.
        fraction: Part des heures de marche etablie retenue comme reference.

    Returns:
        Horodatage de fin de periode, inclus.

    Raises:
        ValueError: Si aucune heure de marche etablie n'est disponible.
    """
    running = df.index[df["process_state"].eq("RUNNING")]
    if not len(running):
        raise ValueError(
            "Aucune heure de marche etablie : la periode de reference ne peut "
            "pas etre determinee."
        )
    position = max(0, int(len(running) * fraction) - 1)
    return running[position]


def seawater_temperature(index: pd.DatetimeIndex) -> pd.Series:
    """Temperature d'eau de mer au jour de l'annee, par interpolation.

    L'interpolation est cyclique : decembre est voisin de janvier, ce qui
    evite la marche d'escalier au passage d'annee.

    Args:
        index: Horodatages.

    Returns:
        Serie de temperatures en degres Celsius.
    """
    anchors = np.array([pd.Timestamp(2001, m, 15).dayofyear for m in range(1, 13)])
    values = np.array([SEAWATER_MONTHLY_C[m] for m in range(1, 13)])
    return pd.Series(
        np.interp(
            index.dayofyear.values,
            np.r_[anchors - 365, anchors, anchors + 365],
            np.r_[values, values, values],
        ),
        index=index,
        name="T_SEAWATER",
    )


def overall_conductance(
    t_acid_in: pd.Series,
    t_acid_out: pd.Series,
    capacity_rate: pd.Series,
    t_seawater: pd.Series,
) -> pd.Series:
    """Coefficient d'echange global UA, par la methode efficacite-NTU.

    Args:
        t_acid_in: Temperature d'entree acide, degC.
        t_acid_out: Temperature de sortie acide, degC.
        capacity_rate: Capacite thermique du flux acide, kW/K.
        t_seawater: Temperature d'eau de mer, degC.

    Returns:
        Serie de UA en kW/K, NaN quand l'echangeur ne travaille pas.
    """
    driving = t_acid_in - t_seawater
    cooled = t_acid_in - t_acid_out
    usable = (driving > MIN_APPROACH_K) & (cooled > MIN_APPROACH_K)

    brute = cooled / driving.where(driving > MIN_APPROACH_K)
    effectiveness = brute.clip(EFFECTIVENESS_MIN, EFFECTIVENESS_MAX)

    # UN ECRETAGE SUR LA GRANDEUR DE DIAGNOSTIC NE PEUT PAS ETRE SILENCIEUX.
    # La borne haute plafonne NTU a -ln(1 - 0,999) = 6,9, donc UA lui-meme.
    # Tant qu'elle n'est jamais atteinte, elle protege d'une division par zero;
    # si elle l'etait, le coefficient d'echange serait tronque sans que rien ne
    # le dise, et le residu d'encrassement s'en trouverait fausse. On compte
    # donc les ecretages effectifs et on les journalise.
    ecretes = int(((brute > EFFECTIVENESS_MAX) & usable).sum())
    if ecretes:
        logger.warning(
            f"Efficacite ecretee a {EFFECTIVENESS_MAX} sur {ecretes} instant(s) "
            f"de marche : le coefficient d'echange y est plafonne et son residu "
            f"n'est pas interpretable."
        )
    return (capacity_rate * ntu_de(effectiveness)).where(usable)


def ntu_de(effectiveness: pd.Series) -> pd.Series:
    """Nombre d'unites de transfert correspondant a une efficacite donnee."""
    return -np.log(1.0 - effectiveness)


@dataclass
class ConductanceReference:
    """Reference de UA aux conditions d'exploitation.

    UA varie legitimement avec le regime : le debit acide gouverne la
    turbulence, et la viscosite de l'acide chute avec la temperature. Cette
    reference apprend cette dependance sur une periode saine; ce qui reste
    apres soustraction est attribuable a l'etat de la surface d'echange.

    Attributes:
        coef: Coefficients ajustes.
        feature_names: Noms des regresseurs.
        residual_std: Ecart-type du residu sur la reference, kW/K.
        ua_reference: UA moyen de la periode de reference, kW/K.
        n_train: Nombre d'heures d'apprentissage.
        train_period: Bornes de la periode de reference.
        r2: Coefficient de determination.
    """

    coef: np.ndarray | None = None
    feature_names: list[str] = field(default_factory=list)
    residual_std: float = 1.0
    ua_reference: float = 0.0
    n_train: int = 0
    train_period: tuple[str, str] = ("", "")
    r2: float = 0.0

    # Exposant de Dittus-Boelter sur le nombre de Reynolds, donc sur le debit.
    FLOW_EXPONENT: ClassVar[float] = 0.8

    @staticmethod
    def _design(df: pd.DataFrame) -> np.ndarray:
        """Matrice de regression : turbulence, viscosite, source froide."""
        flow = df["F_ACID"].to_numpy(dtype=float)
        t_mean = (
            df["T_ACID_IN"].to_numpy(dtype=float) + df["T_ACID_OUT"].to_numpy(dtype=float)
        ) / 2.0
        return np.column_stack([
            np.power(np.clip(flow, 1e-6, None), ConductanceReference.FLOW_EXPONENT),
            t_mean,
            df["T_SEAWATER"].to_numpy(dtype=float),
            np.ones(len(df)),
        ])

    def fit(
        self, df: pd.DataFrame, reference_end: str | pd.Timestamp | None = None
    ) -> ConductanceReference:
        """Ajuste la reference sur une periode saine.

        Args:
            df: Table contenant UA et les conditions d'exploitation.
            reference_end: Fin de la periode de reference.

        Returns:
            self, ajuste.

        Raises:
            ValueError: Si la periode de reference est trop courte.
        """
        ok = df["process_state"].eq("RUNNING") & df["ua_kw_per_k"].notna()
        for column in ("F_ACID", "T_ACID_IN", "T_ACID_OUT", "T_SEAWATER"):
            ok &= df[column].notna()
        train = df[ok]

        # LA REFERENCE NE DOIT JAMAIS VOIR TOUT LE CORPUS.
        # Une version precedente omettait ce repli : faute de date de revision,
        # `reference_end` valait None et la reference etait ajustee sur les
        # quatorze mois. Elle apprenait alors comme normale la degradation
        # qu'elle est censee detecter, et le residu ne pouvait plus deriver.
        # Les trois references du systeme partagent desormais la meme regle.
        borne = (
            pd.Timestamp(reference_end)
            if reference_end is not None
            else reference_cutoff(df)
        )
        train = train[train.index <= borne]

        if len(train) < 200:
            raise ValueError(
                f"Periode de reference trop courte pour UA : {len(train)} h (min 200)"
            )

        design = self._design(train)
        target = train["ua_kw_per_k"].to_numpy(dtype=float)
        self.coef, *_ = np.linalg.lstsq(design, target, rcond=None)

        residual = target - design @ self.coef
        self.residual_std = float(residual.std()) or 1.0
        self.r2 = float(1.0 - residual.var() / target.var()) if target.var() > 0 else 0.0
        self.ua_reference = float(target.mean())
        self.n_train = len(train)
        self.train_period = (str(train.index.min()), str(train.index.max()))
        self.feature_names = ["F_ACID^0.8", "T_acide_moyenne", "T_eau_de_mer", "const"]

        logger.info(
            f"Reference de conductance ajustee — n={self.n_train} h, "
            f"UA={self.ua_reference:.2f} kW/K, R2={self.r2:.3f}, "
            f"sigma={self.residual_std:.2f} kW/K"
        )
        return self

    def predict(self, df: pd.DataFrame) -> pd.Series:
        """UA attendu aux conditions observees.

        Args:
            df: Table des conditions d'exploitation.

        Returns:
            Serie de UA attendu, kW/K.

        Raises:
            RuntimeError: Si la reference n'a pas ete ajustee.
        """
        if self.coef is None:
            raise RuntimeError("ConductanceReference non ajustee — appeler fit()")
        ok = df["process_state"].eq("RUNNING")
        for column in ("F_ACID", "T_ACID_IN", "T_ACID_OUT", "T_SEAWATER"):
            ok &= df[column].notna()
        out = pd.Series(np.nan, index=df.index, dtype=float)
        if ok.any():
            out.loc[ok] = self._design(df[ok]) @ self.coef
        return out

    def to_dict(self) -> dict[str, Any]:
        """Serialise la reference pour l'audit."""
        return {
            "label": "Reference de coefficient d'echange global",
            "target": "ua_kw_per_k",
            "unit": "kW/K",
            "coef": None if self.coef is None else [float(c) for c in self.coef],
            "feature_names": self.feature_names,
            "residual_std": round(self.residual_std, 4),
            "ua_reference": round(self.ua_reference, 3),
            "r2": round(self.r2, 4),
            "n_train": self.n_train,
            "train_period": list(self.train_period),
            "seawater_source": (
                "Climatologie mensuelle de Safi, cote atlantique marocaine "
                "(17,0 degC en fevrier a 22,0 degC en septembre)"
            ),
        }


def add_conductance_features(df: pd.DataFrame, reference: ConductanceReference) -> pd.DataFrame:
    """Ajoute UA, son residu normalise, sa tendance et la resistance d'encrassement.

    Args:
        df: Table enrichie des features physiques et de `T_SEAWATER`.
        reference: Reference de conductance ajustee.

    Returns:
        Copie enrichie de `df`.
    """
    out = df.copy()
    expected = reference.predict(out)
    out["ua_expected"] = expected
    out["ua_residual"] = out["ua_kw_per_k"] - expected
    out["ua_residual_z"] = out["ua_residual"] / reference.residual_std

    # Une derive d'encrassement s'installe sur des semaines. La fenetre est
    # calendaire pour resister aux arrets de ligne.
    out["ua_residual_trend_14d"] = (
        out["ua_residual_z"].rolling("14D", min_periods=112).mean()
    )

    # Resistance d'encrassement, en K/kW. C'est la grandeur que suit un
    # ingenieur fiabilite pour arbitrer la date du prochain nettoyage.
    #
    # LE TERME DE COMPARAISON EST UA_ATTENDU, PAS LA MOYENNE DE REFERENCE.
    # Une version precedente ecrivait Rf = 1/UA - 1/UA_moyen. Comme UA varie
    # legitimement d'un facteur 1,6 avec le debit et la saison, cette
    # difference mesurait surtout le regime : sur ce corpus, sa correlation
    # avec le debit atteignait -0,76 et avec UA attendu -0,90. Autrement dit,
    # une simple baisse de debit se lisait comme un encrassement.
    # En comparant a la valeur attendue AUX CONDITIONS DE L'INSTANT, ces
    # correlations tombent a +0,13 et +0,08 : ce qui reste est attribuable a
    # la surface d'echange.
    out["fouling_resistance"] = (1.0 / out["ua_kw_per_k"]) - (1.0 / expected)
    out["fouling_resistance_trend_14d"] = (
        out["fouling_resistance"].rolling("14D", min_periods=112).mean()
    )
    return out
