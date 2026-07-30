"""
Features physiques du refroidisseur E7301 — jumeau numerique thermique.

Pourquoi pas de features generiques ?
----------------------------------------------------------------------------
La v1 de ce projet calculait des z-scores et des rolling stats sur des capteurs
generiques. Sur cet equipement, cette approche echoue pour une raison physique
precise : LA TEMPERATURE DE SORTIE ACIDE EST REGULEE. Sa distribution reelle
est P1 = 63.7 degC, P99 = 66.6 degC, soit une bande de 3 degC sur 14 mois. Un
z-score sur ce signal ne detecte rien tant que la regulation tient — et quand
elle lache, il est deja trop tard.

CORRECTION MAJEURE — CE QUE LE RESIDU DE DUTY MESURE REELLEMENT
----------------------------------------------------------------------------
La version precedente affirmait que l'encrassement « se lit sur l'effort, pas
sur le resultat », l'effort etant le residu du duty thermique. Cette
affirmation est FAUSSE, et l'erreur est algebrique.

Le duty est calcule par definition :

    duty = rho.cp . F . (T_in - T_out)

La reference le regresse sur F, T_in, la charge, le titre, et le produit
F x T_in. Or T_out est REGULEE (ecart-type 0.8 degC sur 14 mois), donc

    duty ~ rho.cp . F . T_in  -  rho.cp . 66 . F

est deja une combinaison lineaire de deux regresseurs presents. La regression
ne modelise pas l'echangeur : elle retrouve sa propre definition. Mesure a
l'appui, sur ce corpus :

    R2 de la reference apprise .................... 0.968
    R2 d'une formule SANS apprentissage ........... 0.962
    apport reel du modele appris .................. 0.006
    correlation(residu, ecart de consigne) ....... -0.94
    variance du residu expliquee par l'ecart seul . 88 %

Ces chiffres ne sont pas figes dans ce commentaire : ils sont RECALCULES a
chaque ajustement (`naive_r2`, `learned_gain`) et publies dans le manifeste,
et `independence_report()` mesure la correlation. Un test echoue si la
redondance disparait sans que l'analyse soit reprise.

Le residu de duty N'EST PAS un indicateur independant : c'est l'ecart de
consigne change de signe et pondere par le debit. Il est donc renomme
`regulation_effort` — c'est ce qu'il mesure — et il n'est plus jamais presente
comme une preuve distincte de l'ecart de consigne.

CE QUI PORTE LE DIAGNOSTIC
----------------------------------------------------------------------------
Un indicateur de degradation doit porter sur la grandeur que la degradation
attaque. Pour un echangeur, c'est le COEFFICIENT D'ECHANGE GLOBAL UA. Il est
calcule dans `src.features.thermal` a partir de la temperature d'eau de mer,
donnee climatologique exterieure a l'atelier, par la methode efficacite-NTU.
C'est lui qui declenche FOULING_DRIFT.

Deux grandeurs l'accompagnent, chacune avec son role et sa limite mesuree :

    ua_residual_z ......... indicateur de diagnostic. r = -0.54 avec l'ecart
                            de consigne : partiellement confondu, parce que
                            la vanne d'eau de mer n'est pas instrumentee et
                            agit sur le meme UA apparent. Voir `thermal`.
    regulation_effort_z ... mesure de CONDUITE, jamais de degradation.
                            r = -0.94 : c'est l'ecart de consigne reecrit.
    t_in_residual_z ....... niveau thermique du circuit amont. r = +0.03,
                            donc porteur d'information nouvelle, mais CONFONDU
                            cote procede : une derive de l'entree peut venir
                            du refroidisseur comme de la tour de sechage. Il
                            ne prouve rien seul; il contextualise.

ARCHITECTURE
----------------------------------------------------------------------------
  1. Features physiques      — duty, efficacite, ecart de regulation
  2. Coefficient d'echange   — UA, son residu, la resistance d'encrassement.
                               C'est l'etage qui porte le diagnostic.
  3. Effort de regulation    — residu du duty, ASSUME comme redondant avec
                               l'ecart de consigne, conserve pour la conduite
  4. Reference d'entree      — niveau thermique amont a charge donnee
  5. Features statistiques   — evenements rapides (fuite, a-coup)

Les trois references sont ajustees sur la MEME periode de reference : les
premiers 40 % des heures de marche etablie a defaut de date de revision. Ce
choix est arbitraire et son effet est quantifie par `src.governance.sensitivity`.

Toutes les features de performance sont NaN hors marche etablie : juger la
performance d'un echangeur a l'arret n'a aucun sens.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

import numpy as np
import pandas as pd
from loguru import logger

from src.domain.knowledge import DomainKnowledge, load_domain, seuil
from src.features.thermal import (
    ConductanceReference,
    add_conductance_features,
    overall_conductance,
    reference_cutoff,
    seawater_temperature,
)

# ── Proprietes physiques de l'acide de sechage ───────────────────────────────
#
# PROPRIETES EVALUEES A LA TEMPERATURE, ET RESULTAT MESURE.
# La version precedente figeait rho.cp a 1800 kg/m3 x 1.42 kJ/(kg.K). On
# soupconnait un biais dependant de la temperature, puisque rho et cp du
# H2SO4 98 % varient tous deux sur la plage exploitee.
#
# MESURE : ils varient en SENS OPPOSES et se compensent presque. Sur 66-95 degC,
# rho baisse d'environ 1.8 % et cp monte d'environ 1.5 %, si bien que leur
# PRODUIT ne bouge que de ~0.2 %. La correlation est conservee parce qu'elle
# est plus juste, mais ce raffinement ne doit pas etre presente comme une
# correction significative : il ne change pas les conclusions. Un test fige ce
# constat pour empecher de le sur-vendre.
#
# Correlations retenues, lineaires sur 20-120 degC pour H2SO4 98 % :
#   rho(T) = 1857 - 1.03 T      kg/m3
#   cp(T)  = 1.363 + 7.5e-4 T   kJ/(kg.K)
#
# Ces droites sont ajustees sur les tables de reference publiees pour l'acide
# sulfurique concentre (Perry, Chemical Engineers' Handbook, section proprietes
# des solutions H2SO4-H2O). L'incertitude de tabulation est de l'ordre de 1 %
# sur rho et de 2 % sur cp. PORTEE DE CETTE INCERTITUDE : rho.cp intervient en
# facteur commun de duty_kw et de la capacite thermique C utilisee pour UA. Une
# erreur d'echelle de 2 % deplace UA et UA_attendu DANS LE MEME RAPPORT, donc
# laisse le residu normalise inchange. Elle ne se propage donc pas au
# diagnostic : elle n'affecte que la lecture en valeur absolue des kW affiches.
RHO_A, RHO_B = 1857.0, -1.03
CP_A, CP_B = 1.363, 7.5e-4

# Valeur figee de l'ancienne implementation, conservee comme REPERE de
# non-regression : `rho_cp` evalue a la temperature doit rester dans son
# voisinage sur toute la plage exploitee, faute de quoi le raffinement aurait
# change les conclusions au lieu de les preciser. Le commentaire precedent
# annoncait des tests qui ne l'utilisaient pas; c'est desormais le cas.
# Unite : kW.h/(m3.K), comme la sortie de `rho_cp`.
RHO_CP_ACID_REFERENCE = 1800.0 * 1.42 / 3600.0


def rho_cp(temperature_c: pd.Series | float) -> pd.Series | float:
    """Produit rho.cp de l'acide 98 % a la temperature moyenne de l'echangeur.

    Args:
        temperature_c: Temperature en degres Celsius.

    Returns:
        rho.cp exprime en kW.h/(m3.K), directement multipliable par un debit
        en m3/h et un ecart en K pour obtenir des kW.
    """
    rho = RHO_A + RHO_B * temperature_c
    cp = CP_A + CP_B * temperature_c
    return rho * cp / 3600.0


SHORT_WINDOW = "24h"   # durée calendaire, pas nombre de lignes
LONG_WINDOW = "14D"    # idem : robuste aux trous et aux arrêts

# Liste ordonnee des features livrees au modele ML.
#
# Les grandeurs retirees restent disponibles pour l'affichage et les regles
# metier, mais ne sont plus injectees ensemble dans l'Isolation Forest :
# - regulation_effort et sa version standardisee sont strictement colineaires ;
# - delta_t et approach_ratio portent presque la meme information ;
# - duty_kw, duty_per_load et les regresseurs de la reference se recouvrent ;
# - control_deviation et l'effort de regulation sont le MEME signal (voir plus haut).
#
# `t_in_residual_z` est le seul indicateur de degradation independant de la
# variable regulee. Il est donc ajoute explicitement.
#
# LES MOYENNES GLISSANTES 14 JOURS N'ENTRENT PAS DANS LE MODELE.
# C'est une correction de conception. Donner une tendance lente a un detecteur
# de points atypiques garantit que TOUTE heure d'une periode derivee sera
# signalee : le taux de signalement passait alors de 10 % a 17 %, et a 65 %
# sur le mois d'octobre. Une derive lente n'est pas une succession de points
# anormaux, c'est UN evenement — et c'est le role des regles de persistance
# (`_rule_thermal_drift`) de le dire une fois, pas celui du modele de le
# repeter a chaque heure.
#
# Repartition des roles :
#   modele statistique  -> combinaisons instantanees inhabituelles
#   regles de derive    -> tendances lentes, avec exigence de persistance
MODEL_FEATURES: list[str] = [
    "ua_residual_z",
    "regulation_effort_z",
    "t_in_residual_z",
    "conc_min",
    "conc_bias_drift_z",
    "conc_drop_24h",
    "flow_per_load",
    "d_t_out",
    "d_conc",
    "t_out_local_z",
    "t_in_local_z",
]


# ── Features physiques ────────────────────────────────────────────────────────

def add_physics_features(df: pd.DataFrame, domain: DomainKnowledge) -> pd.DataFrame:
    """Ajoute les grandeurs thermiques interpretables par un ingenieur fiabilite.

    Args:
        df: DataFrame issu de l'ingestion (colonnes = alias, + process_state).
        domain: Connaissance domaine.

    Returns:
        Copie de `df` enrichie des colonnes physiques.
    """
    out = df.copy()
    running = out["process_state"].eq("RUNNING")

    t_in, t_out = out["T_ACID_IN"], out["T_ACID_OUT"]
    flow, load = out["F_ACID"], out["LOAD_SULFUR"]

    # Ecart de temperature aux bornes du refroidisseur — le travail brut fait
    # par l'echangeur.
    out["delta_t"] = (t_in - t_out).where(running)

    # Puissance thermique evacuee. Q = rho.cp(T).V.dT, avec rho.cp evalue a la
    # temperature MOYENNE du fluide dans l'appareil : figer cette constante
    # introduisait un biais correle a la temperature.
    t_mean = (t_in + t_out) / 2.0
    out["rho_cp"] = rho_cp(t_mean).where(running)
    out["duty_kw"] = (out["rho_cp"] * flow * out["delta_t"]).where(running)

    # Duty ramene a la charge de la ligne : neutralise l'effet d'allure.
    # Sans cette normalisation, une montee en cadence ressemble a une derive.
    out["duty_per_load"] = (out["duty_kw"] / load.replace(0, np.nan)).where(running)

    # Ratio d'approche : part de la chaleur disponible reellement extraite.
    # Proxy sans mesure d'eau de mer, mais monotone avec l'efficacite reelle.
    out["approach_ratio"] = (out["delta_t"] / t_in.replace(0, np.nan)).where(running)

    # Ecart a la consigne de regulation — signal de perte de controle.
    sp = seuil(domain.get("T_ACID_OUT").setpoint, 66.0)
    out["control_deviation"] = (t_out - sp).where(running)

    # Debit acide ramene a la charge — detecte une perte de debit non expliquee
    # par l'allure (piste CALANDRE_FUITE / pompe).
    out["flow_per_load"] = (flow / load.replace(0, np.nan)).where(running)

    # Titre acide.
    #
    # CORRECTION D'UNE ERREUR DE CONCEPTION INITIALE. La premiere version
    # prenait min(AI1100, AI1200) au nom d'une "approche conservative", en
    # supposant les deux analyseurs redondants. L'analyse des donnees montre
    # qu'ils ne le sont pas : correlation +0.35 seulement en marche etablie,
    # et AI1200 systematiquement plus bas de 0.124 point. Resultat, AI1200
    # etait le minimum dans 94.9 % des cas et le min() se reduisait a un seul
    # capteur, tout en donnant l'illusion d'une securite par redondance.
    #
    # On expose donc les deux circuits separement, et l'ecart devient un
    # indicateur a part entiere : ce n'est pas sa valeur absolue qui compte,
    # mais sa STABILITE. Un biais constant est normal ; un biais qui derive
    # signale un analyseur qui part.
    c1, c2 = out["C_ACID_1100"], out["C_ACID_1200"]
    out["conc_spread"] = c2 - c1                      # signe conserve : le sens de la derive informe

    # `conc_min` reste le titre gouvernant pour la corrosion — c'est bien le
    # plus bas des deux qui determine l'agressivite du milieu — mais le nom
    # ne doit plus laisser croire a une redondance.
    out["conc_min"] = pd.concat([c1, c2], axis=1).min(axis=1)
    # Décalage calendaire : un trou d'acquisition ne doit pas transformer
    # "24 lignes" en une durée supérieure à 24 heures.
    out["conc_drop_24h"] = out["conc_min"] - out["conc_min"].shift(freq="24h")

    # Derive de l'ecart inter-analyseurs, en nombre d'ecarts-types par rapport
    # au biais normal declare dans le referentiel.
    tag2 = domain.get("C_ACID_1200")
    bias = float(tag2.spec.get("cross_check_expected_bias", 0.0))
    sigma = float(tag2.spec.get("cross_check_bias_sigma", 0.1)) or 0.1
    out["conc_bias_drift_z"] = ((out["conc_spread"] - bias) / sigma).where(running)

    return out


# ── References lineaires ──────────────────────────────────────────────────────

@dataclass
class LinearReference:
    """Reference lineaire apprise sur une periode reputee saine.

    Une regression lineaire sur termes physiques est preferee a un modele
    complexe pour trois raisons : (1) elle est explicable devant un exploitant,
    (2) elle ne peut pas apprendre la degradation elle-meme et la masquer,
    (3) ses coefficients sont verifiables par le controleur de coherence.

    Attributes:
        coef: Coefficients ajustes.
        feature_names: Noms des regresseurs.
        residual_std: Ecart-type des residus sur la periode de reference.
        n_train: Nombre d'echantillons d'apprentissage.
        train_period: Bornes temporelles de la reference.
        r2: Coefficient de determination sur la reference.
        naive_r2: R2 d'une reconstruction SANS apprentissage. Il mesure la part
            du R2 qui vient de la definition de la cible et non du modele.
    """

    coef: np.ndarray | None = None
    feature_names: list[str] = field(default_factory=list)
    residual_std: float = 1.0
    n_train: int = 0
    train_period: tuple[str, str] = ("", "")
    r2: float = 0.0
    naive_r2: float | None = None

    # A definir par les sous-classes.
    TARGET: ClassVar[str] = ""
    REGRESSORS: ClassVar[list[str]] = []
    LABEL: ClassVar[str] = ""
    UNIT: ClassVar[str] = ""

    def _design(self, df: pd.DataFrame) -> np.ndarray:
        """Matrice de regression. Redefinie par les sous-classes si besoin."""
        cols = [df[c].to_numpy(dtype=float) for c in self.REGRESSORS]
        return np.column_stack([*cols, np.ones(len(df))])

    def _naive(self, df: pd.DataFrame) -> np.ndarray | None:
        """Reconstruction sans apprentissage, pour mesurer l'apport reel."""
        return None

    def fit(
        self, df: pd.DataFrame, reference_end: str | pd.Timestamp | None = None
    ) -> LinearReference:
        """Ajuste la reference sur une periode reputee saine.

        Args:
            df: DataFrame enrichi des features physiques.
            reference_end: Fin de la periode de reference. Par defaut, les
                premiers 40 % des heures de marche etablie. Ce choix est
                ARBITRAIRE faute de date de revision communiquee par OCP;
                `src.governance.model_validation` en quantifie la sensibilite.

        Returns:
            self, ajuste.

        Raises:
            ValueError: Si la periode de reference est trop courte (< 200 h).
        """
        ok = df["process_state"].eq("RUNNING") & df[self.TARGET].notna()
        for c in self.REGRESSORS:
            ok &= df[c].notna()
        train = df[ok]

        # LA BORNE EST COMMUNE AUX TROIS REFERENCES, ET ELLE N'EST PAS ECRITE ICI.
        # Ce repli decoupait `0.40` en dur APRES application du masque
        # d'eligibilite propre a cette reference : les trois s'arretaient a des
        # instants differents. La borne vient desormais de `reference_cutoff`,
        # calculee une fois sur les heures de marche etablie.
        borne = (
            pd.Timestamp(reference_end)
            if reference_end is not None
            else reference_cutoff(df)
        )
        train = train[train.index <= borne]

        if len(train) < 200:
            raise ValueError(
                f"Periode de reference trop courte pour {type(self).__name__}: "
                f"{len(train)} h (min 200)"
            )

        X = self._design(train)
        y = train[self.TARGET].to_numpy(dtype=float)
        self.coef, *_ = np.linalg.lstsq(X, y, rcond=None)

        resid = y - X @ self.coef
        self.residual_std = float(resid.std()) or 1.0
        self.r2 = float(1.0 - resid.var() / y.var()) if y.var() > 0 else 0.0
        self.n_train = len(train)
        self.train_period = (str(train.index.min()), str(train.index.max()))

        naive = self._naive(train)
        if naive is not None and y.var() > 0:
            self.naive_r2 = float(1.0 - (y - naive).var() / y.var())

        logger.info(
            f"{self.LABEL} ajustee — n={self.n_train} h "
            f"({self.train_period[0]} -> {self.train_period[1]}), "
            f"R2={self.r2:.3f}"
            + (f" (dont {self.naive_r2:.3f} sans apprentissage)"
               if self.naive_r2 is not None else "")
            + f", sigma={self.residual_std:.2f} {self.UNIT}"
        )
        return self

    def predict(self, df: pd.DataFrame) -> pd.Series:
        """Valeur attendue pour les conditions d'exploitation observees.

        Args:
            df: DataFrame contenant les regresseurs.

        Returns:
            Serie attendue (NaN si une entree manque ou hors marche etablie).

        Raises:
            RuntimeError: Si la reference n'a pas ete ajustee.
        """
        if self.coef is None:
            raise RuntimeError(f"{type(self).__name__} non ajustee — appeler fit()")
        ok = df["process_state"].eq("RUNNING")
        for c in self.REGRESSORS:
            ok &= df[c].notna()
        pred = pd.Series(np.nan, index=df.index, dtype=float)
        if ok.any():
            pred.loc[ok] = self._design(df[ok]) @ self.coef
        return pred

    def to_dict(self) -> dict[str, Any]:
        """Serialise la reference pour l'audit et la persistance."""
        return {
            "label": self.LABEL,
            "target": self.TARGET,
            "unit": self.UNIT,
            "coef": None if self.coef is None else [float(c) for c in self.coef],
            "feature_names": self.feature_names,
            "residual_std": self.residual_std,
            "r2": self.r2,
            "naive_r2": self.naive_r2,
            "learned_gain": (
                None if self.naive_r2 is None else round(self.r2 - self.naive_r2, 4)
            ),
            "n_train": self.n_train,
            "train_period": list(self.train_period),
        }


@dataclass
class RegulationEffortReference(LinearReference):
    """Effort de regulation — anciennement presente comme « jumeau thermique ».

    ATTENTION, LECTURE OBLIGATOIRE AVANT D'UTILISER SON RESIDU.

    La cible est `duty_kw = rho.cp . F . (T_in - T_out)`, et les regresseurs
    contiennent F, T_in et F x T_in. Comme T_out est regulee, la cible est
    presque une combinaison lineaire des regresseurs : le R2 eleve de cette
    reference est en tres grande partie ALGEBRIQUE, pas physique. Le champ
    `naive_r2` mesure cette part.

    Son residu vaut approximativement `-rho.cp . F . (T_out - consigne)`, soit
    l'ecart de consigne change de signe et pondere par le debit. Il est donc
    utile comme mesure d'EFFORT DE REGULATION, mais il ne constitue jamais une
    preuve independante de l'ecart de consigne. Pour un indicateur reellement
    independant, voir `InletReference`.
    """

    TARGET: ClassVar[str] = "duty_kw"
    REGRESSORS: ClassVar[list[str]] = ["LOAD_SULFUR", "F_ACID", "T_ACID_IN", "conc_min"]
    LABEL: ClassVar[str] = "Reference d'effort de regulation"
    UNIT: ClassVar[str] = "kW"

    def _design(self, df: pd.DataFrame) -> np.ndarray:
        cols = [df[c].to_numpy(dtype=float) for c in self.REGRESSORS]
        inter = df["F_ACID"].to_numpy(dtype=float) * df["T_ACID_IN"].to_numpy(dtype=float)
        return np.column_stack([*cols, inter, np.ones(len(df))])

    def _naive(self, df: pd.DataFrame) -> np.ndarray | None:
        """Duty reconstruit en figeant la sortie a sa mediane — zero apprentissage.

        Si ce R2 approche celui du modele, c'est que la reference ne fait que
        retrouver la definition de sa cible.
        """
        t_out_ref = float(df["T_ACID_OUT"].median())
        return (
            df["rho_cp"].to_numpy(dtype=float)
            * df["F_ACID"].to_numpy(dtype=float)
            * (df["T_ACID_IN"].to_numpy(dtype=float) - t_out_ref)
        )

    def fit(self, df, reference_end=None):
        super().fit(df, reference_end)
        self.feature_names = [*self.REGRESSORS, "F_ACID*T_ACID_IN", "const"]
        return self


@dataclass
class InletReference(LinearReference):
    """Reference de temperature d'entree — le seul residu independant.

    POURQUOI CELLE-CI ET PAS UNE AUTRE.
    La boucle de regulation contraint la sortie acide, donc tout indicateur
    construit dessus est aveugle ou redondant. La temperature d'ENTREE, elle,
    est libre : ecart-type 2,0 degC en marche etablie. Si le refroidisseur perd
    de la capacite, le circuit acide se stabilise plus haut et l'entree derive
    vers le haut A CHARGE ET DEBIT CONSTANTS.

    Mesure sur ce corpus : correlation entre ce residu et l'ecart de consigne
    = +0.03. C'est bien une information nouvelle, contrairement au residu de
    l'effort de regulation (-0.94).

    LIMITE A ENONCER SANS DETOUR : cet indicateur est CONFONDU. Une derive de
    l'entree peut provenir du refroidisseur comme de la tour de sechage ou de
    tout autre organe amont. Il ne prouve pas l'encrassement; il etablit qu'a
    conditions egales le circuit travaille plus chaud. Sans mesure cote eau de
    mer, aucune attribution certaine n'est possible.
    """

    TARGET: ClassVar[str] = "T_ACID_IN"
    REGRESSORS: ClassVar[list[str]] = ["LOAD_SULFUR", "F_ACID"]
    LABEL: ClassVar[str] = "Reference de temperature d'entree"
    UNIT: ClassVar[str] = "degC"

    def _design(self, df: pd.DataFrame) -> np.ndarray:
        load = df["LOAD_SULFUR"].to_numpy(dtype=float)
        flow = df["F_ACID"].to_numpy(dtype=float)
        return np.column_stack([load, flow, load * flow, np.ones(len(df))])

    def fit(self, df, reference_end=None):
        super().fit(df, reference_end)
        self.feature_names = [*self.REGRESSORS, "LOAD_SULFUR*F_ACID", "const"]
        return self


@dataclass
class References:
    """Les trois references du systeme, transportees ensemble.

    Attributes:
        conductance: Coefficient d'echange global UA. C'est la reference qui
            porte le diagnostic d'encrassement, parce que c'est la seule
            ancree sur une grandeur exterieure a l'atelier — la temperature
            de l'eau de mer.
        effort: Effort de regulation. Conservee pour le diagnostic de conduite,
            jamais pour l'encrassement : elle reecrit l'ecart de consigne.
        inlet: Niveau thermique d'entree a charge donnee. Signal de contexte
            sur le circuit acide amont.
    """

    conductance: ConductanceReference
    effort: RegulationEffortReference
    inlet: InletReference

    def to_dict(self) -> dict[str, Any]:
        """Serialise les references pour l'audit."""
        return {
            "conductance": self.conductance.to_dict(),
            "regulation_effort": self.effort.to_dict(),
            "inlet": self.inlet.to_dict(),
            "hierarchy": (
                "L'encrassement se diagnostique sur le coefficient d'echange "
                "global. L'effort de regulation mesure la conduite, pas l'etat "
                "de la surface d'echange."
            ),
        }


def add_reference_features(df: pd.DataFrame, refs: References) -> pd.DataFrame:
    """Ajoute les residus des deux references et leurs tendances 14 jours.

    Args:
        df: DataFrame enrichi des features physiques.
        refs: References ajustees.

    Returns:
        Copie enrichie de `df`.
    """
    out = df.copy()

    # 1. Effort de regulation — redondant avec l'ecart de consigne, et nomme
    #    en consequence pour qu'aucune lecture ne puisse le prendre pour une
    #    preuve independante.
    expected = refs.effort.predict(out)
    out["duty_expected"] = expected
    out["regulation_effort"] = out["duty_kw"] - expected
    out["regulation_effort_z"] = out["regulation_effort"] / refs.effort.residual_std
    out["regulation_effort_trend_14d"] = (
        out["regulation_effort_z"].rolling(LONG_WINDOW, min_periods=112).mean()
    )

    # 2. Reference d'entree — indicateur de degradation independant.
    t_in_expected = refs.inlet.predict(out)
    out["t_in_expected"] = t_in_expected
    out["t_in_residual"] = out["T_ACID_IN"] - t_in_expected
    out["t_in_residual_z"] = out["t_in_residual"] / refs.inlet.residual_std
    # Une derive lente et persistante est la signature recherchee; un pic isole
    # ne l'est pas. La fenetre est calendaire pour resister aux arrets.
    out["t_in_residual_trend_14d"] = (
        out["t_in_residual_z"].rolling(LONG_WINDOW, min_periods=112).mean()
    )
    return out


# ── Features statistiques ─────────────────────────────────────────────────────

def add_dynamic_features(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute variations instantanees et deviations locales.

    Ces features captent les evenements RAPIDES (a-coup, fuite, decrochage de
    regulation), la ou le jumeau capte les derives LENTES.

    Args:
        df: DataFrame enrichi.

    Returns:
        Copie enrichie de `df`.
    """
    out = df.copy()
    running = out["process_state"].eq("RUNNING")

    # Une reprise après arrêt ne doit pas être comparée au dernier point avant
    # l'arrêt. Les différences sont calculées à l'intérieur de chaque segment
    # continu de marche établie.
    run_segment = running.ne(running.shift(fill_value=False)).cumsum()
    out["d_t_out"] = out["T_ACID_OUT"].where(running).groupby(run_segment).diff()
    out["d_conc"] = out["conc_min"].where(running).groupby(run_segment).diff()

    for col, name in (("T_ACID_OUT", "t_out_local_z"), ("T_ACID_IN", "t_in_local_z")):
        s = out[col].where(running)
        mu = s.rolling(SHORT_WINDOW, min_periods=6).mean()
        sd = s.rolling(SHORT_WINDOW, min_periods=6).std()
        out[name] = (s - mu) / sd.replace(0, np.nan)

    return out


def add_quality_features(
    df: pd.DataFrame, quality: pd.DataFrame, domain: DomainKnowledge
) -> pd.DataFrame:
    """Ajoute le nombre de tags EN PERIMETRE en defaut a chaque horodatage.

    Cette feature n'est pas un artefact technique : elle porte le mode AMDEC
    CAPTEUR_DEFAILLANT (criticite 108). Elle permet aussi au Judge de savoir
    que le diagnostic s'appuie sur une base de mesure degradee.

    Restriction essentielle : on ne compte QUE les tags du perimetre de
    surveillance. TI5303-4X est sature depuis aout 2024 et PHI5306X-3 a ete
    fige 1900 h ; ces deux capteurs sont deja declares hors perimetre dans
    `tags.yaml`. Les recompter a chaque heure reviendrait a marquer 7 mois de
    donnees comme "degradees" et a noyer les vrais defauts de mesure — le
    systeme crierait au loup en permanence et deviendrait inutilisable.
    Ils sont signales une fois, dans la synthese de sante capteurs.

    Args:
        df: DataFrame enrichi.
        quality: Table des evenements qualite issue de l'ingestion.
        domain: Connaissance domaine (pour identifier le perimetre).

    Returns:
        Copie enrichie de `df`.
    """
    out = df.copy()
    in_scope = {t.tag for t in domain.model_tags}
    if len(quality):
        q = quality[quality["tag"].isin(in_scope)]
        counts = q.groupby("timestamp")["tag"].nunique() if len(q) else pd.Series(dtype=float)
        out["n_invalid_tags"] = counts.reindex(out.index).fillna(0).astype(float)
    else:
        out["n_invalid_tags"] = 0.0
    return out


# ── Pipeline ──────────────────────────────────────────────────────────────────

def build_features(
    readings: pd.DataFrame,
    quality: pd.DataFrame,
    domain: DomainKnowledge | None = None,
    references: References | None = None,
    fit_references: bool = True,
    reference_end: str | pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, References]:
    """Construit le jeu de features complet.

    Args:
        readings: Table de lectures issue de l'ingestion.
        quality: Table des evenements qualite.
        domain: Connaissance domaine (chargee par defaut).
        references: References deja ajustees (mode inference).
        fit_references: Ajuster de nouvelles references (mode entrainement).
        reference_end: Fin de la periode de reference.

    Returns:
        Tuple (DataFrame de features, references utilisees).
    """
    domain = domain or load_domain()

    df = add_physics_features(readings, domain)

    # Cote froid : la temperature d'eau de mer vient de la climatologie de Safi.
    # C'est la seule grandeur du systeme qui ne depend d'aucune boucle de
    # regulation de l'atelier, et c'est elle qui rend UA interpretable.
    df["T_SEAWATER"] = seawater_temperature(df.index)
    df["ua_kw_per_k"] = overall_conductance(
        df["T_ACID_IN"], df["T_ACID_OUT"],
        df["rho_cp"] * df["F_ACID"], df["T_SEAWATER"],
    ).where(df["process_state"].eq("RUNNING"))

    if fit_references or references is None:
        references = References(
            conductance=ConductanceReference().fit(df, reference_end),
            effort=RegulationEffortReference().fit(df, reference_end),
            inlet=InletReference().fit(df, reference_end),
        )
    df = add_conductance_features(df, references.conductance)
    df = add_reference_features(df, references)
    df = add_dynamic_features(df)
    df = add_quality_features(df, quality, domain)

    missing = [c for c in MODEL_FEATURES if c not in df.columns]
    if missing:
        raise RuntimeError(f"Features manquantes apres construction: {missing}")

    logger.info(f"Features construites — {len(df)} lignes, {len(MODEL_FEATURES)} features modele")
    return df, references


def model_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Extrait la matrice livree au modele, restreinte a la marche etablie.

    Les lignes en arret ou en transitoire sont ecartees : le detecteur
    n'apprend et ne juge que la marche etablie. Les instants transitoires sont
    traites en amont par des regles deterministes, pas par le modele.

    Args:
        df: DataFrame de features complet.

    Returns:
        Sous-DataFrame indexe par timestamp, colonnes = MODEL_FEATURES.
    """
    running = df["process_state"].eq("RUNNING")
    X = df.loc[running, MODEL_FEATURES]
    return X.dropna()


def independence_report(df: pd.DataFrame) -> dict[str, Any]:
    """Mesure a quel point chaque residu est redondant avec la variable regulee.

    Ce controle existe parce que la version precedente presentait le residu de
    duty comme un indicateur independant alors qu'il vaut, a l'algebre pres,
    l'ecart de consigne pondere par le debit. Le chiffre est desormais calcule,
    publie et verifie par un test.

    Args:
        df: DataFrame de features complet.

    Returns:
        Correlations avec `control_deviation` et verdict d'independance.
    """
    roles = {
        "ua_residual_z": (
            "diagnostic",
            "Indicateur d'encrassement. Partiellement confondu : la vanne "
            "d'eau de mer n'est pas instrumentée et agit sur le même UA "
            "apparent. Le banc d'injection chiffre le retard qui en résulte.",
        ),
        "regulation_effort_z": (
            "conduite",
            "Réécriture de l'écart de consigne pondérée par le débit. Ne "
            "constitue jamais une preuve d'encrassement.",
        ),
        "t_in_residual_z": (
            "contexte",
            "Niveau thermique du circuit amont à charge donnée. Indépendant "
            "de la variable régulée, mais confondu côté procédé : une dérive "
            "peut venir du refroidisseur comme de la tour de séchage.",
        ),
    }
    run = df[df["process_state"].eq("RUNNING")]
    out: dict[str, Any] = {}
    for name, (role, reading) in roles.items():
        if name not in run.columns:
            continue
        pair = run[[name, "control_deviation"]].dropna()
        r = float(pair[name].corr(pair["control_deviation"])) if len(pair) > 2 else float("nan")
        out[name] = {
            "role": role,
            "corr_control_deviation": round(r, 4),
            "shared_variance_pct": round(100.0 * r * r, 1),
            "independent": bool(abs(r) < 0.30),
            "reading": reading,
        }
    out["verdict"] = (
        "Le diagnostic d'encrassement est porté par le résidu de coefficient "
        "d'échange, seul indicateur construit sur la grandeur que "
        "l'encrassement dégrade. Sa confusion résiduelle avec l'écart de "
        "consigne est mesurée et publiée plutôt que niée. L'effort de "
        "régulation n'entre dans aucune condition de déclenchement ni de "
        "gradation : il est cité comme contexte, et sa valeur de preuve est "
        "nulle. La gradation de l'alerte d'encrassement porte sur le déficit "
        "de coefficient d'échange lui-même, dont le seuil est gouverné dans "
        "amdec.yaml."
    )
    return out


if __name__ == "__main__":
    from src.config import DCS_EXPORT
    from src.ingest.dcs_loader import ingest

    res = ingest(DCS_EXPORT)
    feats, refs = build_features(res.readings, res.quality)
    X = model_matrix(feats)
    print(f"\nMatrice modele: {X.shape}")
    print(feats[["delta_t", "duty_kw", "regulation_effort_z",
                 "t_in_residual_z", "t_in_residual_trend_14d",
                 "control_deviation", "conc_min"]]
          .resample("MS").mean().round(3).to_string())
    print("\nIndependance :")
    for k, v in independence_report(feats).items():
        print(f"  {k}: {v}")
