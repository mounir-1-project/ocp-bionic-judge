"""
Detection d'anomalies du refroidisseur E7301 — moteur de regles + modele statistique.

Architecture en deux etages, volontairement.
----------------------------------------------------------------------------
ETAGE 1 — MOTEUR DE REGLES (deterministe, ancre sur l'AMDEC)
    Chaque regle encode une signature de mode de defaillance issue de
    `amdec.yaml`. Elle est verifiable, tracable, et ne peut pas halluciner.
    C'est ce qui donne au systeme sa credibilite devant un exploitant : toute
    alerte se rattache a une ligne de l'AMDEC de 2019.

ETAGE 2 — MODELE STATISTIQUE (Isolation Forest)
    Il capte ce que les regles n'anticipent pas : les combinaisons anormales
    de variables qui, prises une a une, restent dans les tolerances. C'est la
    valeur ajoutee du ML ici — pas de remplacer les seuils, mais de voir ce
    qu'aucun seuil univarie ne peut voir.

Les deux etages sont FUSIONNES, pas mis en concurrence : le score final retient
la severite la plus elevee, et les preuves des deux etages sont conservees.
Un ecart entre les deux (regle silencieuse / modele alarmiste, ou l'inverse)
est lui-meme une information transmise au Judge.

Explicabilite
----------------------------------------------------------------------------
L'attribution par defaut est une OCCLUSION EXACTE : pour chaque feature, on
recalcule le score du modele en remplacant cette feature par sa valeur mediane
de reference. La chute de score mesure la contribution reelle de la feature
a l'anomalie. C'est exact (pas d'approximation), deterministe, sans dependance
lourde, et directement interpretable : "si le duty avait ete normal, le score
serait tombe de 0.81 a 0.34". SHAP est utilise a la place s'il est installe.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, Literal

import joblib
import numpy as np
import pandas as pd
from loguru import logger
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from src.domain.knowledge import DomainKnowledge, load_domain, seuil
from src.features.e7301_features import MODEL_FEATURES, References

Severity = Literal["NORMAL", "INFO", "WARNING", "CRITICAL"]
SEVERITY_ORDER: dict[str, int] = {"NORMAL": 0, "INFO": 1, "WARNING": 2, "CRITICAL": 3}

# Persistance minimale (en heures) exigee avant de declarer une derive lente.
# Une derive d'encrassement s'installe sur des semaines : exiger 72 h de
# persistance elimine les faux positifs dus a un a-coup d'exploitation.
DRIFT_PERSISTENCE_H = 72
DRIFT_Z_THRESHOLD = 1.5

# Chute de titre acide consideree comme suspecte sur 24 h (points de %).
CONC_DROP_SUSPICIOUS = 0.35
CONC_DROP_CRITICAL = 0.80

# Persistance exigee avant qu'un depassement du modele statistique devienne une
# alerte : au moins MODEL_PERSIST_MIN heures anormales sur les MODEL_PERSIST_WIN
# dernieres. Sans cette regle, le modele emet une alerte par heure atypique et
# l'operateur en recoit des milliers — le systeme devient inutilisable et sera
# desactive en salle de controle. Une anomalie de procede reelle dure ; un point
# isole est le plus souvent un artefact d'acquisition.
MODEL_PERSIST_WIN = 6
MODEL_PERSIST_MIN = 3

# Nombre de points de mesure en defaut a partir duquel la base est declaree
# degradee plutot que simplement incomplete.
SENSOR_FAULT_WARNING_COUNT = 2

# Agregation des heures atypiques en episodes exploitables : trou tolere entre
# deux heures d'un meme episode, et duree minimale retenue.
EPISODE_MAX_GAP_H = 6
EPISODE_MIN_DURATION_H = 3


def _fenetre_calendaire(history: pd.DataFrame, heures: int) -> pd.DataFrame:
    """Sous-ensemble de l'historique couvrant les `heures` dernieres heures.

    Les fenetres de persistance etaient exprimees en NOMBRE DE LIGNES
    (`tail(72)`). A travers un arret de ligne ou un trou d'acquisition, 72
    lignes couvrent plusieurs semaines : la regle affirmait une persistance de
    72 heures sur une fenetre qui n'en representait pas 72, et publiait un
    nombre de lignes sous l'etiquette `persistance_h`.

    Args:
        history: Historique indexe par le temps, borne incluse a l'instant juge.
        heures: Profondeur calendaire de la fenetre.

    Returns:
        Sous-DataFrame couvrant `]t - heures, t]`.
    """
    if history.empty:
        return history
    borne = history.index[-1] - pd.Timedelta(hours=heures)
    return history.loc[history.index > borne]


# ── Structures ────────────────────────────────────────────────────────────────

@dataclass
class Finding:
    """Une constatation elementaire produite par une regle ou par le modele.

    Attributes:
        code: Identifiant court de la constatation.
        source: 'RULE' ou 'MODEL'.
        severity: Severite propre a la constatation.
        amdec_mode: Code du mode de defaillance AMDEC rattache (ou None).
        message: Formulation lisible destinee a l'exploitant.
        evidence: Valeurs mesurees ayant declenche la constatation.
    """

    code: str
    source: Literal["RULE", "MODEL"]
    severity: Severity
    amdec_mode: str | None
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class DetectionResult:
    """Sortie complete de la detection pour un horodatage.

    Attributes:
        timestamp: Horodatage analyse (ISO 8601).
        process_state: RUNNING / TRANSIENT / STOPPED.
        severity: Severite consolidee.
        anomaly_score: Score du modele statistique, normalise dans [0, 1].
        model_is_anomaly: Verdict binaire du modele statistique.
        findings: Constatations des deux etages.
        attributions: Contribution de chaque feature au score (decroissante).
        measurements: Valeurs des grandeurs cles a cet instant.
        data_quality: Etat de la base de mesure (tags en defaut).
    """

    timestamp: str
    process_state: str
    severity: Severity
    anomaly_score: float
    model_is_anomaly: bool
    findings: list[Finding] = field(default_factory=list)
    attributions: list[dict[str, Any]] = field(default_factory=list)
    measurements: dict[str, float] = field(default_factory=dict)
    data_quality: dict[str, Any] = field(default_factory=dict)

    @property
    def amdec_modes(self) -> list[str]:
        """Modes AMDEC distincts invoques par les constatations."""
        return sorted({f.amdec_mode for f in self.findings if f.amdec_mode})

    def to_dict(self) -> dict[str, Any]:
        """Representation serialisable (API, base de donnees, prompts LLM)."""
        d = asdict(self)
        d["amdec_modes"] = self.amdec_modes
        return d


# ── Etage 1 : moteur de regles ────────────────────────────────────────────────

class RuleEngine:
    """Regles deterministes derivees des signatures AMDEC.

    Chaque regle repond a une question qu'un ingenieur fiabilite se poserait
    devant les courbes, et cite les valeurs qui motivent sa reponse.
    """

    def __init__(self, domain: DomainKnowledge) -> None:
        """Initialise le moteur.

        Args:
            domain: Connaissance domaine (seuils, modes AMDEC).
        """
        self.domain = domain

    def evaluate(self, row: pd.Series, history: pd.DataFrame) -> list[Finding]:
        """Applique toutes les regles a un horodatage.

        Args:
            row: Ligne de features a l'instant analyse.
            history: Fenetre d'historique precedant cet instant (bornes incluses).

        Returns:
            Liste des constatations declenchees.
        """
        out: list[Finding] = []

        # HORS MARCHE : une seule constatation, et rien d'autre.
        #
        # Emettre en plus SENSOR_FAULT a l'arret revenait a rattacher le mode
        # CAPTEUR_DEFAILLANT a un message d'arret de ligne : l'interface
        # affichait « ligne en etat STOPPED » sous l'etiquette d'une
        # defaillance capteur, ce qui est une accusation sans fondement. Un
        # signal fige a l'arret est d'ailleurs le comportement attendu, et
        # l'ingestion le sait deja (masque `eligible`).
        if row.get("process_state") != "RUNNING":
            out.append(Finding(
                code="NOT_RUNNING", source="RULE", severity="INFO", amdec_mode=None,
                message=(
                    f"Ligne à l'arrêt (état {row.get('process_state')}). La "
                    f"surveillance de performance de l'échangeur est suspendue : "
                    f"aucun diagnostic de dégradation n'est formulable à partir "
                    f"de mesures prises hors marche établie."
                ),
                evidence={"LOAD_SULFUR": _f(row.get("LOAD_SULFUR")),
                          "F_ACID": _f(row.get("F_ACID"))},
            ))
            return out

        out += self._rule_sensor_health(row)

        out += self._rule_control_loss(row, history)
        out += self._rule_thermal_drift(row, history)
        out += self._rule_concentration(row, history)
        out += self._rule_temperature_corrosion(row)
        out += self._rule_flow_anomaly(row)
        return out

    # -- Regles ---------------------------------------------------------------

    def _rule_sensor_health(self, row: pd.Series) -> list[Finding]:
        """Mode CAPTEUR_DEFAILLANT — la base de mesure est-elle fiable ?"""
        n_bad = float(row.get("n_invalid_tags") or 0)
        if n_bad <= 0:
            return []
        sev: Severity = (
            "WARNING" if n_bad >= SENSOR_FAULT_WARNING_COUNT else "INFO"
        )
        return [Finding(
            code="SENSOR_FAULT", source="RULE", severity=sev,
            amdec_mode="CAPTEUR_DEFAILLANT",
            message=f"{int(n_bad)} point(s) de mesure en défaut à cet instant "
                    f"(code qualité, gel de signal ou butée d'échelle). Le "
                    f"diagnostic s'appuie sur une base de mesure dégradée.",
            evidence={"n_invalid_tags": n_bad},
        )]

    def _rule_control_loss(self, row: pd.Series, history: pd.DataFrame) -> list[Finding]:
        """Perte de controle de la temperature de sortie acide.

        C'est la manifestation TERMINALE de l'encrassement : l'echangeur ne
        parvient plus a tenir sa consigne. Severe par construction.
        """
        tag = self.domain.get("T_ACID_OUT")
        t_out = _f(row.get("T_ACID_OUT"))
        if t_out is None:
            return []
        hh = seuil(tag.threshold("alarm_high_high"), 72.0)
        h = seuil(tag.threshold("alarm_high"), 68.0)
        band = tag.control_band if tag.control_band is not None else (63.0, 68.0)

        if t_out >= hh:
            return [Finding(
                code="CONTROL_LOSS_CRITICAL", source="RULE", severity="CRITICAL",
                amdec_mode="FAISCEAU_BOUCHAGE",
                message=f"Température de sortie acide à {_n(t_out)} °C, au-dessus du "
                        f"seuil HH ({_n(hh)} °C). L'échangeur ne tient plus sa consigne "
                        f"de {_n(tag.setpoint)} °C : la boucle froide a consommé toute "
                        f"sa marge, la capacité d'échange est insuffisante.",
                evidence={"T_ACID_OUT": t_out, "seuil_HH": hh,
                          "consigne": tag.setpoint,
                          "control_deviation": _f(row.get("control_deviation"))},
            )]
        if t_out >= h:
            return [Finding(
                code="CONTROL_LOSS", source="RULE", severity="WARNING",
                amdec_mode="FAISCEAU_BOUCHAGE",
                message=f"Température de sortie acide à {_n(t_out)} °C, hors bande de "
                        f"régulation [{_n(band[0])}, {_n(band[1])}] °C. Début de perte "
                        f"de contrôle à surveiller.",
                evidence={"T_ACID_OUT": t_out, "seuil_H": h,
                          "control_deviation": _f(row.get("control_deviation"))},
            )]
        return []

    def _fouling_warning_sigma(self) -> float:
        """Deficit de coefficient d'echange faisant passer l'alerte en WARNING.

        Le seuil vit dans `amdec.yaml`, sous la signature du mode
        FAISCEAU_BOUCHAGE : c'est une donnee de gouvernance, modifiable par le
        service fiabilite sans qu'une ligne de code change.

        M-1 — LE SEUL ENDROIT DU DEPOT QUI ENFREIGNAIT SA PROPRE REGLE.

        Cette methode ecrivait `(...) or 3.0`, et nommait le resultat `seuil`.
        Deux fautes superposees, sur six lignes.

        L'idiome `or` est precisement celui que `src.domain.knowledge.seuil`
        existe pour abolir : sa docstring dit « le repli teste l'absence, pas
        la faussete » et cite les douze endroits ou il avait ete remplace. Ici
        un `warning_sigma: 0` gouverne dans `amdec.yaml` — reglage parfaitement
        legitime signifiant « toute perte de coefficient d'echange persistante
        passe en WARNING » — serait devenu 3.0 sans le moindre avertissement.

        Et la variable locale s'appelait `seuil`, donc masquait la fonction
        importee ligne 49 : dans cette portee, la fonction qui corrige le
        defaut etait inaccessible sous son propre nom.

        Returns:
            Seuil en ecarts-types, toujours superieur au seuil de declenchement.
        """
        mode = self.domain.modes.get("FAISCEAU_BOUCHAGE")
        gouverne = mode.signature.get("warning_sigma") if mode else None
        return max(seuil(gouverne, 3.0), DRIFT_Z_THRESHOLD)

    def _rule_thermal_drift(self, row: pd.Series, history: pd.DataFrame) -> list[Finding]:
        """Derives thermiques lentes — degradation et conduite.

        CETTE REGLE A ETE REECRITE APRES UN AUDIT QUI A INVALIDE SA VERSION
        PRECEDENTE. Celle-ci croisait le residu de duty et l'ecart de consigne
        comme s'il s'agissait de deux preuves concordantes. Ce sont en realite
        deux ecritures de la MEME grandeur : le residu de duty vaut, a l'algebre
        pres, `-rho.cp . F . (T_out - consigne)`, et leur correlation mesuree
        sur ce corpus est de -0.94. La conjonction ne pouvait donc pas echouer,
        et ne verifiait rien.

        La regle repose desormais sur deux signaux de natures differentes :

          DEGRADATION (FAISCEAU_BOUCHAGE)
              portee par `ua_residual_trend_14d`, residu du COEFFICIENT
              D'ECHANGE GLOBAL. UA est calcule par la methode efficacite-NTU
              a partir de la temperature d'eau de mer, donnee climatologique
              exterieure a l'atelier et independante de toute boucle de
              regulation. Une baisse persistante de UA a conditions egales est
              la definition meme de l'encrassement.
              L'effort de regulation ne sert que de CORROBORATION; seul, il ne
              declenche rien.

          CONDUITE (pas un mode de defaillance)
              effort de regulation durablement excedentaire : la ligne
              sur-refroidit. Ce n'est pas une degradation de l'appareil.
        """
        out: list[Finding] = []
        ua_z = _f(row.get("ua_residual_trend_14d"))
        effort = _f(row.get("regulation_effort_trend_14d"))
        dev = _f(row.get("control_deviation"))

        # LA PERSISTANCE SE COMPTE EN HEURES, PAS EN LIGNES.
        # `tail(72)` retenait les 72 dernieres LIGNES de l'historique. A travers
        # un arret de ligne ou un trou d'acquisition, ces 72 lignes couvrent
        # plusieurs semaines : le message affirmait « maintenu depuis plus de
        # 72 h » sur une fenetre qui n'en representait pas 72, et la preuve
        # `persistance_h` publiait un nombre de lignes sous un nom d'heures.
        # Les features utilisent deja des fenetres calendaires pour cette
        # raison exacte; les regles de persistance s'y alignent.
        fenetre = _fenetre_calendaire(history, DRIFT_PERSISTENCE_H)

        # ── Degradation : perte de coefficient d'echange, persistante ─────
        if ua_z is not None:
            recent = fenetre["ua_residual_trend_14d"].dropna()
            if len(recent) >= DRIFT_PERSISTENCE_H // 2:
                persistent = (recent <= -DRIFT_Z_THRESHOLD).mean() > 0.8
                if ua_z <= -DRIFT_Z_THRESHOLD and persistent:
                    # LA GRADATION SE FONDE SUR LA GRANDEUR DIAGNOSTIQUE.
                    #
                    # Une version precedente faisait dependre le passage en
                    # WARNING d'une corroboration par l'effort de regulation,
                    # exigeant `effort <= -1.5 sigma`. Cet indicateur ne
                    # descend jamais sous -0,99 sigma sur ce corpus, quelle que
                    # soit la periode de reference : la severite WARNING etait
                    # STRUCTURELLEMENT INATTEIGNABLE, et un test l'affirmait
                    # pourtant en forcant une valeur que les donnees ne
                    # produisent pas.
                    #
                    # Deux fautes en une. D'abord un seuil non atteignable, donc
                    # une branche morte. Ensuite une incoherence de fond : le
                    # projet declare partout que l'effort de regulation « ne
                    # constitue jamais une preuve d'encrassement », puis lui
                    # confiait la gradation de l'alerte d'encrassement.
                    #
                    # La severite depend desormais de l'ampleur du deficit de
                    # coefficient d'echange lui-meme, seuil gouverne dans
                    # `amdec.yaml`. L'effort de regulation reste cite, comme
                    # element de contexte, et jamais comme condition.
                    grave = ua_z <= -self._fouling_warning_sigma()
                    sev: Severity = "WARNING" if grave else "INFO"
                    corroborated = effort is not None and effort <= -DRIFT_Z_THRESHOLD
                    fouling = _f(row.get("fouling_resistance"))
                    out.append(Finding(
                        code="FOULING_DRIFT", source="RULE", severity=sev,
                        amdec_mode="FAISCEAU_BOUCHAGE",
                        message=(
                            f"Coefficient d'échange global inférieur de "
                            f"{_n(abs(ua_z), 2)} sigma à sa référence sur 14 jours, "
                            f"à débit, température et eau de mer donnés, maintenu "
                            f"depuis plus de {DRIFT_PERSISTENCE_H} h. "
                            f"UA mesuré {_n(row.get('ua_kw_per_k'))} kW/K "
                            f"pour {_n(row.get('ua_expected'))} attendu"
                            + (f", soit une résistance d'encrassement de "
                               f"{_n(fouling, 4, signe=True)} K/kW. " if fouling is not None else ". ")
                            + "La surface d'échange transmet moins bien qu'à l'état "
                              "de référence : signature d'un dépôt sur le faisceau."
                            + (f" Déficit au-delà de "
                               f"{_n(self._fouling_warning_sigma())} sigma : à "
                               f"qualifier par le service fiabilité."
                               if grave else
                               " Déficit encore modéré : à surveiller, pas à traiter.")
                            + (" L'effort de régulation évolue dans le même sens, "
                               "sans valeur de preuve." if corroborated else "")
                        ),
                        evidence={
                            "ua_residual_trend_14d": ua_z,
                            "ua_kw_per_k": _f(row.get("ua_kw_per_k")),
                            "ua_expected": _f(row.get("ua_expected")),
                            "fouling_resistance": fouling,
                            "T_SEAWATER": _f(row.get("T_SEAWATER")),
                            "regulation_effort_trend_14d": effort,
                            # LA CORRECTION DE LA FENETRE N'AVAIT PAS ETE
                            # PORTEE JUSQU'A LA PREUVE PUBLIEE.
                            #
                            # Le commentaire trente lignes plus haut dit que
                            # `persistance_h` « publiait un nombre de lignes
                            # sous un nom d'heures », et la fenetre est bien
                            # devenue calendaire. Mais le champ continuait de
                            # valoir `len(recent)`, c'est-a-dire le nombre
                            # d'heures OU LA TENDANCE ETAIT CALCULABLE dans la
                            # fenetre — donc toujours un compte de lignes, avec
                            # toujours le meme nom.
                            #
                            # Les deux grandeurs sont maintenant distinctes et
                            # nommees pour ce qu'elles sont : la profondeur de
                            # la fenetre est une constante calendaire, le
                            # nombre d'heures mesurees est ce que la base de
                            # donnee a fourni a l'interieur.
                            "fenetre_h": DRIFT_PERSISTENCE_H,
                            "heures_mesurees_dans_la_fenetre": len(recent),
                            "part_sous_le_seuil": round(
                                float((recent <= -DRIFT_Z_THRESHOLD).mean()), 3
                            ),
                            "corrobore": corroborated,
                        },
                    ))

        # ── Conduite : sur-refroidissement installe ───────────────────────
        if effort is not None:
            recent_e = fenetre["regulation_effort_trend_14d"].dropna()
            if (
                len(recent_e) >= DRIFT_PERSISTENCE_H // 2
                and effort >= DRIFT_Z_THRESHOLD
                and (recent_e >= DRIFT_Z_THRESHOLD).mean() > 0.8
            ):
                # L'ECART DE CONSIGNE PEUT MANQUER ALORS QUE L'EFFORT EXISTE.
                # `regulation_effort_trend_14d` est une tendance sur 14 jours :
                # elle survit a un horodatage ou la temperature de sortie est
                # en defaut, ce que `control_deviation` ne fait pas. La mise en
                # forme du message supposait les deux presents et levait un
                # TypeError sur l'instant concerne, ce qui interrompait
                # l'analyse au lieu de la degrader.
                rappel = (
                    f"Rappel de lecture — cet indicateur est une réécriture de "
                    f"l'écart de consigne ({_n(dev, 2, signe=True)} °C), pas une preuve "
                    f"indépendante. " if dev is not None else
                    "Rappel de lecture — cet indicateur est une réécriture de "
                    "l'écart de consigne, indisponible à cet instant, pas une "
                    "preuve indépendante. "
                )
                out.append(Finding(
                    code="OVERCOOLING_REGIME", source="RULE", severity="INFO",
                    amdec_mode=None,
                    message=(
                        f"Effort de régulation durablement excédentaire "
                        f"({_n(effort, 2, signe=True)} sigma sur 14 jours) : la ligne sur-refroidit. "
                        + rappel
                        + "Ce n'est pas une dégradation de l'appareil "
                          "mais un régime de conduite."
                    ),
                    evidence={
                        "regulation_effort_trend_14d": effort,
                        "control_deviation": dev,
                        "note": "indicateur redondant avec control_deviation (r = -0.94)",
                    },
                ))
        return out

    def _rule_concentration(self, row: pd.Series, history: pd.DataFrame) -> list[Finding]:
        """Titre acide — le signal le plus critique (mode FAISCEAU_FUITE).

        Une fuite tube introduit de l'eau de mer dans l'acide : le titre chute
        et ne remonte pas. On distingue une chute BRUTALE ET DURABLE (fuite)
        d'une simple derive analyseur.
        """
        out: list[Finding] = []
        tag = self.domain.get("C_ACID_1100")
        tag2 = self.domain.get("C_ACID_1200")
        c = _f(row.get("conc_min"))
        drop = _f(row.get("conc_drop_24h"))
        spread = _f(row.get("conc_spread"))

        if c is not None:
            ll = seuil(tag.threshold("alarm_low_low"), 97.0)
            lo = seuil(tag.threshold("alarm_low"), 98.0)
            if c <= ll:
                out.append(Finding(
                    code="CONC_LOW_LOW", source="RULE", severity="CRITICAL",
                    amdec_mode="FAISCEAU_FUITE",
                    message=f"Titre acide à {_n(c, 2)} %, sous le seuil LL ({_n(ll)} %). "
                            f"Dilution majeure — suspicion d'entrée d'eau de mer par "
                            f"percement de tube jusqu'à preuve du contraire.",
                    evidence={"conc_min": c, "seuil_LL": ll, "conc_drop_24h": drop},
                ))
            elif c <= lo:
                out.append(Finding(
                    code="CONC_LOW", source="RULE", severity="WARNING",
                    amdec_mode="FAISCEAU_CORROSION",
                    message=f"Titre acide à {_n(c, 2)} %, sous spécification ({_n(lo)} %). "
                            f"Conditions favorisant la corrosion des tubes 904L — "
                            f"l'exposition cumulée réduit la durée de vie du faisceau.",
                    evidence={"conc_min": c, "seuil_L": lo},
                ))

        if drop is not None and drop <= -CONC_DROP_CRITICAL:
            out.append(Finding(
                code="CONC_DROP_SEVERE", source="RULE", severity="CRITICAL",
                amdec_mode="FAISCEAU_FUITE",
                message=f"Chute de titre de {_n(abs(drop), 2)} point(s) en 24 h. Cinétique "
                        f"incompatible avec une dérive d'analyseur : traiter comme "
                        f"une suspicion de fuite tube.",
                evidence={"conc_drop_24h": drop, "conc_min": c},
            ))
        elif drop is not None and drop <= -CONC_DROP_SUSPICIOUS:
            out.append(Finding(
                code="CONC_DROP", source="RULE", severity="WARNING",
                amdec_mode="FAISCEAU_FUITE",
                message=f"Baisse de titre de {_n(abs(drop), 2)} point(s) en 24 h. À "
                        f"confirmer par prélèvement laboratoire avant conclusion.",
                evidence={"conc_drop_24h": drop, "conc_min": c},
            ))

        # Derive de l'ecart inter-analyseurs.
        #
        # Ancienne regle : seuil absolu de 0.6 point sur |AI1100 - AI1200|,
        # justifie par une supposee redondance des deux mesures. L'analyse a
        # montre que ces analyseurs suivent deux circuits distincts, avec un
        # biais normal de -0.124 point (ecart-type 0.079). Le seuil de 0.6
        # representait donc 6 sigma et ne se declenchait que 19 heures sur 14
        # mois : il ne servait a rien.
        #
        # Nouvelle regle : on surveille la STABILITE du biais. Un ecart qui
        # s'ecarte de sa valeur habituelle de plus de k sigma signale un
        # analyseur qui derive, bien avant qu'un seuil absolu ne bouge.
        drift_z = _f(row.get("conc_bias_drift_z"))
        k = float(tag2.spec.get("cross_check_k_sigma", 4.0))
        if drift_z is not None and abs(drift_z) > k:
            bias = float(tag2.spec.get("cross_check_expected_bias", 0.0))
            out.append(Finding(
                code="CONC_BIAS_DRIFT", source="RULE", severity="WARNING",
                amdec_mode="CAPTEUR_DEFAILLANT",
                message=f"L'écart entre les deux analyseurs de titre s'éloigne de "
                        f"{_n(abs(drift_z))} écarts-types de sa valeur habituelle "
                        f"({_n(bias, 3, signe=True)} point). Écart mesuré : {_n(spread, 3, signe=True)} point. "
                        f"Un des deux analyseurs dérive — le diagnostic sur le titre "
                        f"acide doit être confirmé par prélèvement laboratoire.",
                evidence={"conc_spread": spread, "conc_bias_drift_z": drift_z,
                          "biais_normal": bias,
                          "C_ACID_1100": _f(row.get("C_ACID_1100")),
                          "C_ACID_1200": _f(row.get("C_ACID_1200"))},
            ))
        return out

    def _rule_temperature_corrosion(self, row: pd.Series) -> list[Finding]:
        """Temperature d'entree acide excessive — mode FAISCEAU_CORROSION."""
        tag = self.domain.get("T_ACID_IN")
        t = _f(row.get("T_ACID_IN"))
        if t is None:
            return []
        hh = seuil(tag.threshold("alarm_high_high"), 105.0)
        h = seuil(tag.threshold("alarm_high"), 100.0)
        if t >= hh:
            return [Finding(
                code="T_IN_HIGH_HIGH", source="RULE", severity="CRITICAL",
                amdec_mode="FAISCEAU_CORROSION",
                message=f"Température d'entrée acide à {_n(t)} °C (seuil HH {_n(hh)} °C). "
                        f"La vitesse de corrosion du 904L croît fortement dans cette "
                        f"plage : risque direct de perte d'épaisseur des tubes.",
                evidence={"T_ACID_IN": t, "seuil_HH": hh},
            )]
        if t >= h:
            return [Finding(
                code="T_IN_HIGH", source="RULE", severity="WARNING",
                amdec_mode="FAISCEAU_CORROSION",
                message=f"Température d'entrée acide à {_n(t)} °C (seuil H {_n(h)} °C). "
                        f"Exposition thermique au-delà du domaine nominal.",
                evidence={"T_ACID_IN": t, "seuil_H": h},
            )]
        return []

    def _rule_flow_anomaly(self, row: pd.Series) -> list[Finding]:
        """Debit acide anormal — vitesse de circulation et depot."""
        tag = self.domain.get("F_ACID")
        f = _f(row.get("F_ACID"))
        if f is None:
            return []
        ll = seuil(tag.threshold("alarm_low_low"), 20.0)
        lo = seuil(tag.threshold("alarm_low"), 35.0)
        # LE MODE EST LE MEME AUX DEUX NIVEAUX.
        # Une version precedente rattachait le seuil LL a CALANDRE_FUITE et le
        # seuil L a FAISCEAU_BOUCHAGE : le meme symptome accusait deux pieces
        # differentes selon son intensite, ce qui n'a aucun sens. Une perte de
        # debit acide se constate; elle ne designe pas sa cause. Les deux
        # niveaux renvoient donc au mode de perte de circulation, et le message
        # enonce les causes possibles sans trancher.
        if f <= ll:
            return [Finding(
                code="FLOW_LOW_LOW", source="RULE", severity="CRITICAL",
                amdec_mode="CALANDRE_FUITE",
                message=f"Débit acide à {_n(f)} m³/h (seuil LL {_n(ll)} m³/h) alors que "
                        f"la ligne est en marche. Perte de circulation avérée : "
                        f"pompe, vanne de régulation ou fuite calandre. Le "
                        f"refroidisseur ne peut plus évacuer sa charge.",
                evidence={"F_ACID": f, "seuil_LL": ll, "LOAD_SULFUR": _f(row.get("LOAD_SULFUR"))},
            )]
        if f <= lo:
            return [Finding(
                code="FLOW_LOW", source="RULE", severity="WARNING",
                amdec_mode="CALANDRE_FUITE",
                message=f"Débit acide à {_n(f)} m³/h (seuil L {_n(lo)} m³/h). Une vitesse "
                        f"de circulation réduite favorise en outre le dépôt de "
                        f"sulfates dans les tubes.",
                evidence={"F_ACID": f, "seuil_L": lo},
            )]
        return []


# Libelles et unites des features, pour que les messages destines a
# l'exploitant ne contiennent jamais de nom de variable informatique.
# Le nombre de decimales est celui qui a un sens metier : afficher un titre
# acide avec quatre decimales suggere une precision que l'analyseur n'a pas.
_FEATURE_LABELS: dict[str, tuple[str, str, int]] = {
    "ua_residual_z": ("l'écart de coefficient d'échange", " sigma", 2),
    "ua_residual_trend_14d": ("la tendance du coefficient d'échange", " sigma", 2),
    "ua_kw_per_k": ("le coefficient d'échange global", " kW/K", 1),
    "fouling_resistance": ("la résistance d'encrassement", " K/kW", 4),
    "regulation_effort_z": ("l'effort de régulation", " sigma", 2),
    "t_in_residual_z": ("le niveau thermique d'entrée", " sigma", 2),
    "conc_min": ("le titre acide", " %", 2),
    "conc_bias_drift_z": ("l'écart entre analyseurs de titre", " sigma", 1),
    "conc_drop_24h": ("la variation de titre sur 24 h", " point", 2),
    "flow_per_load": ("le débit acide rapporté à la charge", " m³/h par t/h", 2),
    "d_t_out": ("la variation horaire de sortie acide", " degC", 2),
    "d_conc": ("la variation horaire de titre", " point", 3),
    "t_out_local_z": ("la sortie acide face à ses 24 h", " sigma", 2),
    "t_in_local_z": ("l'entrée acide face à ses 24 h", " sigma", 2),
}


def _label(feature: str) -> str:
    """Libelle metier d'une feature, pour les messages a l'exploitant."""
    return _FEATURE_LABELS.get(feature, (feature, "", 3))[0]


def _pretty(feature: str, value: Any) -> str:
    """Formate une valeur de feature avec son unite et sa precision utile.

    Meme correction que `_n` : cette fonction rendait « -2.41 sigma » et
    « 98.36 % » dans le message MODEL_ANOMALY et dans le raisonnement de
    l'agent. Elle passe par la mise en forme centralisee.
    """
    x = _f(value)
    if x is None:
        return "valeur absente"
    _, unit, digits = _FEATURE_LABELS.get(feature, (feature, "", 3))
    return _n(x, digits, signe=(unit == " sigma")) + unit


def _n(valeur: Any, decimales: int = 1, signe: bool = False) -> str:
    """Nombre destine a un message d'exploitant, en notation francaise.

    LE PLUS GROS ANGLE MORT TYPOGRAPHIQUE DU DEPOT.

    `src/formatting.py` s'ouvre sur cette phrase : « un test parcourt les
    sorties du systeme pour verifier qu'aucun nombre n'echappe a la regle ».
    Elle etait fausse pour la plus grande surface de texte du projet.

    Chaque message de regle formatait ses valeurs par f-string —
    `f"...{t_out:.1f} °C"` — et rendait donc « 66.3 °C », point decimal
    anglais compris, dans une interface entierement francaise. Ces messages
    sont le premier texte que l'exploitant lit : ils remplissent le journal du
    rejeu, la carte de diagnostic, le registre d'alarmes et les courriels
    d'escalade.

    POURQUOI LE CONTROLE NE L'A PAS VU. Deux tests se partagent la
    typographie. `test_les_messages_de_detection_sont_accentues` regarde bien
    ces messages, mais ne cherche que des accents. `test_aucun_point_decimal_
    dans_les_textes_affiches` cherche bien le point decimal, mais
    n'echantillonne que les indicateurs, l'analyse de sensibilite et le
    backtest — jamais une constatation. Chaque test couvrait la moitie du
    probleme, et l'intersection etait vide.

    Args:
        valeur: Grandeur a formater. `None` et NaN donnent un tiret cadratin.
        decimales: Decimales conservees.
        signe: Forcer le signe explicite, pour les ecarts et les residus.

    Returns:
        Chaine en notation francaise, virgule decimale.
    """
    from src.formatting import nombre

    x = _f(valeur)
    texte = nombre(x, decimales)
    return f"+{texte}" if signe and x is not None and x >= 0 else texte


def _f(v: Any) -> float | None:
    """Convertit en float en preservant None pour les valeurs manquantes.

    Args:
        v: Valeur quelconque.

    Returns:
        Le float correspondant, ou None si la valeur est absente ou NaN.
    """
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(x) else round(x, 4)


# ── Etage 2 : modele statistique ──────────────────────────────────────────────

class StatisticalDetector:
    """Isolation Forest sur les features physiques, avec attribution exacte.

    Attributes:
        features: Ordre des features attendu en entree.
        contamination: Part d'anomalies supposee dans la reference.
        random_state: Graine, pour la reproductibilite exigee par la gouvernance.
    """

    def __init__(
        self,
        features: list[str] | None = None,
        contamination: float = 0.02,
        random_state: int = 42,
    ) -> None:
        """Initialise le detecteur.

        Args:
            features: Colonnes utilisees. Par defaut MODEL_FEATURES.
            contamination: Taux d'anomalies suppose dans la periode de reference.
            random_state: Graine aleatoire.
        """
        self.features = list(features or MODEL_FEATURES)
        self.contamination = contamination
        self.random_state = random_state
        self.scaler = StandardScaler()
        self.model = IsolationForest(
            n_estimators=300,
            contamination=contamination,
            max_samples=1024,
            random_state=random_state,
            n_jobs=-1,
        )
        self.baseline_: np.ndarray | None = None   # medianes de reference
        self.score_center_: float = 0.0
        self.score_scale_: float = 1.0
        self.threshold_: float = 0.5
        self.fitted_: bool = False
        self.train_meta_: dict[str, Any] = {}

    def fit(self, X: pd.DataFrame) -> StatisticalDetector:
        """Ajuste le modele sur la periode de reference.

        Args:
            X: Matrice de features (marche etablie uniquement, sans NaN).

        Returns:
            self, ajuste.

        Raises:
            ValueError: Si la matrice est vide ou incomplete.
        """
        missing = [c for c in self.features if c not in X.columns]
        if missing:
            raise ValueError(f"Features absentes de la matrice: {missing}")
        Xv = X[self.features].to_numpy(dtype=float)
        if len(Xv) < 100:
            raise ValueError(f"Trop peu d'echantillons pour ajuster le detecteur: {len(Xv)}")

        Z = self.scaler.fit_transform(Xv)
        self.model.set_params(max_samples=min(1024, len(Xv)))
        self.model.fit(Z)

        raw = -self.model.score_samples(Z)   # plus grand = plus anormal
        self.score_center_ = float(np.median(raw))
        mad = float(np.median(np.abs(raw - self.score_center_)))
        # L'ECHELLE NE DESCEND JAMAIS SOUS L'ECART-TYPE.
        # Avec `1.4826 * MAD` seul, l'echelle valait 0.050 alors que la queue
        # de distribution s'etend sur 0.30 : la sigmoide saturait, et 1.3 % des
        # heures ressortaient a 1.0000 sans qu'aucune ne puisse etre distinguee
        # d'une autre. Le tableau des « episodes les plus severes » affichait
        # alors douze fois la meme valeur.
        self.score_scale_ = max(1.4826 * mad, float(raw.std()), 1e-9)
        self.baseline_ = np.median(Xv, axis=0)
        self.threshold_ = float(np.quantile(self._normalize(raw), 1.0 - self.contamination))
        # Bornes brutes conservees pour la MARGE, seule grandeur non bornee du
        # detecteur : voir `margin_sigma`.
        self.raw_sigma_ = max(float(raw.std()), 1e-9)
        self.raw_threshold_ = float(np.quantile(raw, 1.0 - self.contamination))
        self.fitted_ = True
        self.train_meta_ = {
            "n_train": len(Xv),
            "period": [str(X.index.min()), str(X.index.max())],
            "contamination": self.contamination,
            "threshold": self.threshold_,
            "features": self.features,
        }
        logger.info(
            f"Isolation Forest ajuste — n={len(Xv)} "
            f"({self.train_meta_['period'][0]} -> {self.train_meta_['period'][1]}), "
            f"seuil={self.threshold_:.3f}"
        )
        return self

    def _normalize(self, raw: np.ndarray) -> np.ndarray:
        """Calibration monotone robuste sans écrêtage aux extrema d'apprentissage.

        Une sigmoïde centrée sur la médiane et mise à l'échelle par la MAD
        conserve l'ordre et la magnitude relative des dépassements, là où un
        min-max tronqué rendait tous les points au-delà du maximum égaux à 1.
        """
        z = np.clip((raw - self.score_center_) / self.score_scale_, -60.0, 60.0)
        return 1.0 / (1.0 + np.exp(-z))

    def score(self, X: pd.DataFrame) -> np.ndarray:
        """Score d'anomalie normalise dans [0, 1].

        Args:
            X: Matrice de features.

        Returns:
            Tableau de scores.

        Raises:
            RuntimeError: Si le modele n'est pas ajuste.
        """
        self._check_fitted()
        Z = self.scaler.transform(X[self.features].to_numpy(dtype=float))
        return self._normalize(-self.model.score_samples(Z))

    def margin_sigma(self, X: pd.DataFrame) -> np.ndarray:
        """Depassement du seuil, en ecarts-types de la reference.

        POURQUOI CETTE GRANDEUR EXISTE.
        Le score normalise sert a DECIDER : au-dessus du seuil, le point est
        atypique. Il ne sert pas a CLASSER, parce que toute transformation
        bornee ecrase la queue de distribution — c'est-a-dire precisement la
        zone ou un exploitant a besoin de distinguer un episode d'un autre.

        La marge, elle, n'est pas bornee :

            marge = (score brut - seuil brut) / ecart-type de la reference

        Elle se lit directement — « +3,2 sigma au-dessus du seuil » — elle
        conserve l'ordre, et deux episodes tres marques restent distincts.
        C'est elle qui trie le tableau des episodes.

        Args:
            X: Matrice de features.

        Returns:
            Tableau de marges en sigma. Negatif sous le seuil.

        Raises:
            RuntimeError: Si le modele n'est pas ajuste.
        """
        self._check_fitted()
        Z = self.scaler.transform(X[self.features].to_numpy(dtype=float))
        raw = -self.model.score_samples(Z)
        return (raw - self.raw_threshold_) / self.raw_sigma_

    def attribute(self, x: pd.Series, top_k: int = 5) -> list[dict[str, Any]]:
        """Attribution par occlusion exacte, feature par feature.

        Pour chaque feature, on remplace sa valeur par la mediane de reference
        et on recalcule le score. La baisse obtenue est la contribution reelle
        de cette feature a l'anomalie : "si cette grandeur avait ete normale,
        le score serait tombe de X a Y".

        Args:
            x: Vecteur de features d'un instant.
            top_k: Nombre de contributions a retourner.

        Returns:
            Liste triee par contribution decroissante.
        """
        self._check_fitted()
        if self.baseline_ is None:
            raise RuntimeError("Baseline absente malgre un detecteur declare ajuste")
        v = x[self.features].to_numpy(dtype=float).reshape(1, -1)

        # Le point de reference et ses N variantes occluses partent dans UN
        # seul appel a la foret. Deux appels separes doublaient inutilement le
        # cout fixe de sklearn, qui domine largement le temps de calcul.
        variants = np.repeat(v, len(self.features), axis=0)
        for i in range(len(self.features)):
            variants[i, i] = self.baseline_[i]
        batch = np.vstack([v, variants])
        scores = self._normalize(-self.model.score_samples(self.scaler.transform(batch)))
        base_score, occluded = float(scores[0]), scores[1:]

        rows = [{
            "feature": name,
            "value": _f(v[0, i]),
            "reference": _f(self.baseline_[i]),
            "contribution": round(base_score - float(occluded[i]), 4),
            "score_if_normal": round(float(occluded[i]), 4),
        } for i, name in enumerate(self.features)]
        rows.sort(key=lambda r: r["contribution"], reverse=True)
        return rows[:top_k]

    def _check_fitted(self) -> None:
        """Verifie que le modele est ajuste.

        Raises:
            RuntimeError: Si fit() n'a pas ete appele.
        """
        if not self.fitted_:
            raise RuntimeError("StatisticalDetector non ajuste — appeler fit() d'abord")


# ── Detecteur consolide ───────────────────────────────────────────────────────

class CoolerAnomalyDetector:
    """Detecteur complet : regles AMDEC + Isolation Forest + explicabilite.

    Attributes:
        domain: Connaissance domaine.
        rules: Moteur de regles.
        stat: Detecteur statistique.
        references: Les trois references thermiques ajustees — conductance,
            effort de regulation, entree. Elles sont transportees avec le
            detecteur parce qu'un artefact serialise doit pouvoir rejouer
            exactement les residus sur lesquels il a appris.
    """

    def __init__(
        self,
        domain: DomainKnowledge | None = None,
        stat: StatisticalDetector | None = None,
        references: References | None = None,
    ) -> None:
        """Initialise le detecteur consolide.

        Args:
            domain: Connaissance domaine (chargee par defaut).
            stat: Detecteur statistique (cree par defaut).
            references: References thermiques deja ajustees. Ce parametre
                s'appelait `twin` dans la documentation de cette classe, nom
                d'un objet qui n'existe plus : la signature documentait donc un
                argument absent et taisait celui qui est reellement accepte.
        """
        self.domain = domain or load_domain()
        self.rules = RuleEngine(self.domain)
        self.stat = stat or StatisticalDetector()
        self.references = references
        # Cache des scores, indexe par horodatage. Le score est une fonction
        # PURE et deterministe des features : le memoriser ne change aucun
        # resultat, cela evite seulement de repasser dans la foret a chaque
        # appel. Sans ce cache, analyser un instant coutait 38 ms dont 27 ms
        # de rescorage redondant (persistance + attribution).
        self._scores: pd.Series | None = None
        self._scores_key: tuple[int, Any, Any, float] | None = None
        self._margins: pd.Series | None = None
        self._margins_key: tuple[int, Any, Any, float] | None = None

    def fit(self, features: pd.DataFrame, reference_end: str | None = None) -> CoolerAnomalyDetector:
        """Ajuste l'etage statistique sur la periode de reference.

        Args:
            features: DataFrame de features complet.
            reference_end: Fin de la periode de reference. Par defaut, les
                           premiers 40% de la marche etablie.

        Returns:
            self, ajuste.
        """
        from src.features.e7301_features import model_matrix
        from src.features.thermal import reference_cutoff

        X = model_matrix(features)
        # LA MEME BORNE QUE LES TROIS REFERENCES THERMIQUES.
        # Ce decoupage utilisait `0.40` en dur sur la matrice du modele, deja
        # filtree et deja debarrassee de ses trous : l'etage statistique
        # apprenait donc sur une fenetre differente de celle des references
        # dont il consomme les residus.
        borne = (
            pd.Timestamp(reference_end)
            if reference_end
            else reference_cutoff(features)
        )
        X = X[X.index <= borne]
        self.stat.fit(X)
        # LE CACHE DE SCORES SURVIVAIT AU RE-ENTRAINEMENT.
        #
        # `score_series` memorise ses resultats sous une cle qui ne decrit que
        # les DONNEES — longueur et bornes de l'index — jamais le modele. Deux
        # ajustements successifs du meme detecteur sur les memes features
        # produisent donc la meme cle : les scores de l'ancien modele etaient
        # renvoyes tels quels, et le nouvel entrainement restait sans effet
        # observable. Le balayage de sensibilite et tout re-entrainement en
        # session sont exactement dans ce cas.
        #
        # `invalidate_cache()` existait deja, avec pour docstring « a appeler
        # apres tout re-entrainement ». Rien ne l'appelait : la methode etait
        # l'aveu du defaut, laissee debranchee.
        self.invalidate_cache()
        return self

    def analyze(self, features: pd.DataFrame, timestamp: pd.Timestamp | str) -> DetectionResult:
        """Analyse un horodatage precis.

        Args:
            features: DataFrame de features complet (doit contenir l'historique).
            timestamp: Instant a analyser.

        Returns:
            DetectionResult consolide.

        Raises:
            KeyError: Si l'horodatage est absent du DataFrame.
        """
        ts = pd.Timestamp(timestamp)
        if ts not in features.index:
            raise KeyError(f"Horodatage absent des donnees: {ts}")
        row = features.loc[ts]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[-1]
        history = features.loc[:ts]

        findings = self.rules.evaluate(row, history)

        # Etage statistique — uniquement en marche etablie et sur donnees completes.
        score, is_anom, attributions = 0.0, False, []
        usable = (
            row.get("process_state") == "RUNNING"
            and self.stat.fitted_
            and not row[self.stat.features].isna().any()
        )
        if usable:
            x = row[self.stat.features].to_frame().T
            score = float(self.stat.score(x)[0])
            is_anom = score >= self.stat.threshold_
            if is_anom:
                attributions = self.stat.attribute(row)
                top = attributions[0]
                n_recent, n_scorables = self._recent_exceedances(features, ts)
                persistent = n_recent >= MODEL_PERSIST_MIN
                findings.append(Finding(
                    code="MODEL_ANOMALY" if persistent else "MODEL_ANOMALY_ISOLATED",
                    source="MODEL",
                    severity="WARNING" if persistent else "INFO",
                    amdec_mode=(
                        self._mode_for_feature(top["feature"], row)
                        if persistent else None
                    ),
                    message=(
                        f"Combinaison de grandeurs inhabituelle par rapport à la "
                        f"période de référence, et l'écart persiste : {n_recent} "
                        f"heure(s) atypique(s) sur les {n_scorables} exploitable(s) "
                        f"des {MODEL_PERSIST_WIN} dernières heures. "
                        f"Contribution dominante : {_label(top['feature'])} à "
                        f"{_pretty(top['feature'], top['value'])} contre "
                        f"{_pretty(top['feature'], top['reference'])} en référence. "
                        f"Le modèle signale la combinaison, il ne désigne pas de "
                        f"cause : voir les constatations déterministes ci-dessus."
                        if persistent else
                        f"Point isolé atypique : {n_recent} heure(s) atypique(s) sur "
                        f"les {n_scorables} exploitable(s) des {MODEL_PERSIST_WIN} "
                        f"dernières heures. Trop "
                        f"bref pour conclure à une anomalie de procédé — "
                        f"surveiller sans agir."
                    ),
                    evidence={"anomaly_score": round(score, 4),
                              "threshold": round(self.stat.threshold_, 4),
                              "top_feature": top["feature"],
                              f"heures_atypiques_sur_{MODEL_PERSIST_WIN}h": n_recent,
                              f"heures_exploitables_sur_{MODEL_PERSIST_WIN}h": n_scorables,
                              "persistent": persistent},
                ))
        elif row.get("process_state") == "RUNNING" and self.stat.fitted_:
            findings.append(Finding(
                code="MODEL_UNAVAILABLE", source="MODEL", severity="INFO", amdec_mode=None,
                message="Modèle statistique non applicable : au moins une grandeur "
                        "d'entrée est manquante à cet instant (capteur en défaut). "
                        "Seules les règles déterministes s'appliquent.",
                evidence={"missing": [c for c in self.stat.features if pd.isna(row.get(c))]},
            ))

        severity = _max_severity([f.severity for f in findings])

        return DetectionResult(
            timestamp=ts.isoformat(),
            process_state=str(row.get("process_state")),
            severity=severity,
            anomaly_score=round(score, 4),
            model_is_anomaly=bool(is_anom),
            findings=findings,
            attributions=attributions,
            # `conc_min` figure ici parce que trois listes de restitution le
            # citent — le dossier de faits de l'agent, sa selection de valeurs
            # et le prompt du LLM. Il en etait absent : le titre acide, qui
            # gouverne la corrosion du 904L, n'apparaissait donc dans AUCUN
            # diagnostic nominal, et le controleur ne pouvait pas verifier une
            # valeur de titre citee par le LLM.
            measurements={
                k: _f(row.get(k))
                for k in ("LOAD_SULFUR", "F_ACID", "T_ACID_IN", "T_ACID_OUT",
                          "C_ACID_1100", "C_ACID_1200", "conc_min", "conc_spread",
                          "delta_t", "duty_kw",
                          "duty_expected", "regulation_effort_z",
                          "regulation_effort_trend_14d", "control_deviation",
                          "T_SEAWATER", "ua_kw_per_k", "ua_expected",
                          "ua_residual_z", "fouling_resistance")
                if _f(row.get(k)) is not None
            },
            data_quality={
                "n_invalid_tags": int(row.get("n_invalid_tags") or 0),
                "model_applicable": bool(usable),
            },
        )

    def _recent_exceedances(self, features: pd.DataFrame, ts: pd.Timestamp) -> tuple[int, int]:
        """Heures atypiques et heures scorables sur la fenetre calendaire.

        `tail(MODEL_PERSIST_WIN)` retenait les six derniers instants SCORABLES,
        qui peuvent s'etaler sur des semaines a travers un arret : le message
        affichait « 3 des 6 dernieres heures sont atypiques » sur une fenetre
        qui n'en couvrait pas six. Les deux compteurs sont desormais rendus,
        pour que le message dise ce qu'il mesure.

        Args:
            features: DataFrame de features complet.
            ts: Instant analyse (inclus).

        Returns:
            Couple (heures atypiques, heures scorables) sur les
            MODEL_PERSIST_WIN dernieres heures calendaires.
        """
        s = self.score_series(features)
        borne = pd.Timestamp(ts) - pd.Timedelta(hours=MODEL_PERSIST_WIN)
        win = s.loc[(s.index > borne) & (s.index <= ts)]
        if win.empty:
            return 0, 0
        return int((win >= self.stat.threshold_).sum()), len(win)

    def score_series(self, features: pd.DataFrame) -> pd.Series:
        """Score d'anomalie sur toute la periode, indexe par le temps.

        Le resultat est memorise : il ne depend que du contenu de `features`
        et du modele ajuste, tous deux immuables pendant une session d'analyse.

        Args:
            features: DataFrame de features complet.

        Returns:
            Serie des scores (uniquement sur la marche etablie exploitable).
        """
        from src.features.e7301_features import model_matrix

        key = self._cache_key(features)
        if self._scores is not None and self._scores_key == key:
            return self._scores

        X = model_matrix(features)
        self._scores = pd.Series(self.stat.score(X), index=X.index, name="anomaly_score")
        self._scores_key = key
        return self._scores

    def _cache_key(self, features: pd.DataFrame) -> tuple[int, Any, Any, float]:
        """Empreinte d'une table de features, pour la memorisation des scores.

        UNE CLE QUI NE DECRIT QUE L'INDEX NE DISTINGUE PAS DEUX TABLES.

        La cle valait `(longueur, premier horodatage, dernier horodatage)`.
        Deux tables construites sur la MEME periode avec le MEME nombre de
        lignes mais des valeurs differentes — c'est exactement ce que produit
        le banc d'injection d'encrassement, qui superpose une rampe aux
        donnees reelles sans toucher a l'index — recevaient donc la meme cle,
        et la seconde se voyait servir les scores de la premiere.

        Le banc n'exploite pas ce chemin aujourd'hui : il evalue le predicat de
        la regle deterministe et ne sollicite jamais l'etage statistique. Rien
        ne garantit qu'il en restera ainsi, et un piege qui ne se declenche pas
        encore reste un piege — d'autant qu'il rendrait un resultat FAUX sans
        rien signaler.

        La somme des features du modele suffit a separer deux contenus. Elle
        coute une milliseconde sur dix mille lignes, contre plusieurs dizaines
        pour la foret que le cache evite.

        Args:
            features: Table de features complete.

        Returns:
            Tuple hachable decrivant l'index ET le contenu.
        """
        if not len(features):
            return (0, None, None, 0.0)
        colonnes = [c for c in self.stat.features if c in features.columns]
        empreinte = (
            float(np.nansum(features[colonnes].to_numpy(dtype=float)))
            if colonnes else 0.0
        )
        return (len(features), features.index[0], features.index[-1], empreinte)

    def invalidate_cache(self) -> None:
        """Force le recalcul des scores au prochain appel.

        A appeler apres tout re-entrainement ou tout ajout de donnees.
        """
        self._scores = None
        self._scores_key = None
        self._margins = None
        self._margins_key = None

    def episodes(
        self,
        features: pd.DataFrame,
        max_gap_h: int = EPISODE_MAX_GAP_H,
        min_duration_h: int = EPISODE_MIN_DURATION_H,
    ) -> pd.DataFrame:
        """Agrege les heures atypiques en episodes exploitables.

        Un exploitant ne traite pas 530 points d'alarme : il traite 58
        episodes. Cette agregation est ce qui rend le systeme
        utilisable en salle de controle. Les episodes trop brefs sont ecartes.

        Args:
            features: DataFrame de features complet.
            max_gap_h: Trou maximal toleré entre deux heures d'un meme episode.
            min_duration_h: Duree minimale pour retenir un episode.

        Returns:
            DataFrame des episodes (debut, fin, duree, score max/moyen, pic).
        """
        s = self.score_series(features)
        margins = self.margin_series(features)
        flagged = s[s >= self.stat.threshold_]
        colonnes = ["start", "end", "duration_h", "n_hours", "margin_max",
                    "margin_mean", "score_max", "score_mean", "peak_at"]
        if flagged.empty:
            return pd.DataFrame(columns=colonnes)

        gaps = flagged.index.to_series().diff() > pd.Timedelta(hours=max_gap_h)
        group = gaps.cumsum()
        rows = []
        for _, chunk in flagged.groupby(group):
            duration = int((chunk.index.max() - chunk.index.min()) / pd.Timedelta("1h")) + 1
            if duration < min_duration_h:
                continue
            marge = margins.reindex(chunk.index).dropna()
            rows.append({
                "start": chunk.index.min(),
                "end": chunk.index.max(),
                "duration_h": duration,
                "n_hours": len(chunk),
                # LE TRI SE FAIT SUR LA MARGE, PAS SUR LE SCORE.
                # Le score sature : tous les episodes ressortaient a 1,0000 et
                # la colonne de tri du tableau « episodes les plus severes »
                # etait identique sur toutes les lignes.
                "margin_max": round(float(marge.max()), 2) if len(marge) else 0.0,
                "margin_mean": round(float(marge.mean()), 2) if len(marge) else 0.0,
                "score_max": round(float(chunk.max()), 4),
                "score_mean": round(float(chunk.mean()), 4),
                "peak_at": chunk.idxmax(),
            })
        return (pd.DataFrame(rows)
                .sort_values("margin_max", ascending=False)
                .reset_index(drop=True))

    def margin_series(self, features: pd.DataFrame) -> pd.Series:
        """Marge en sigma sur toute la periode, indexee par le temps.

        Args:
            features: DataFrame de features complet.

        Returns:
            Serie des marges (uniquement sur la marche etablie exploitable).
        """
        from src.features.e7301_features import model_matrix

        key = self._cache_key(features)
        if self._margins is not None and self._margins_key == key:
            return self._margins

        X = model_matrix(features)
        self._margins = pd.Series(
            self.stat.margin_sigma(X), index=X.index, name="margin_sigma"
        )
        self._margins_key = key
        return self._margins

    # Rattachement d'une feature dominante a un mode AMDEC.
    #
    # DEUX FAMILLES, ET UNE SEULE PEUT ACCUSER UNE PIECE.
    #
    # 1. RESIDUS NORMALISES. Leur ecart A LA VALEUR ATTENDUE est, par
    #    construction, le diagnostic lui-meme. Un residu de UA a -2 sigma
    #    signifie « l'echangeur transmet moins bien qu'il ne le devrait » : le
    #    rattachement au faisceau est licite. La materialite est exprimee en
    #    sigma.
    #
    # 2. GRANDEURS A SEUIL. Le titre acide, le debit et les temperatures ont
    #    des seuils d'exploitation qui font foi. Le modele statistique peut
    #    trouver leur valeur inhabituelle SANS qu'elle soit hors specification :
    #    98,36 % de titre pour une reference a 98,60 % est atypique, ce n'est
    #    pas de la corrosion. Ces features ne portent donc d'accusation que si
    #    le seuil metier est effectivement franchi — auquel cas la regle
    #    deterministe correspondante s'est deja declenchee et porte le
    #    diagnostic. Le modele ne double pas la regle, il ne l'invente pas.
    #
    # 3. INDICATEURS DE CONDUITE. L'effort de regulation et l'ecart de consigne
    #    ne designent aucune piece : ils decrivent l'action de la boucle.
    #
    # LA TABLE NE COUVRE QUE DES FEATURES QUE LE MODELE PEUT DESIGNER.
    # Elle contenait `ua_residual_trend_14d`, `fouling_resistance` et
    # `n_invalid_tags` — trois grandeurs absentes de `MODEL_FEATURES`, donc
    # jamais retournees par l'attribution : trois entrees sur cinq etaient
    # inatteignables et donnaient l'illusion d'une couverture plus large.
    # `test_le_rattachement_ne_cite_que_des_features_du_modele` verrouille
    # desormais l'inclusion dans `MODEL_FEATURES`.
    _MODE_BY_RESIDUAL: ClassVar[dict[str, tuple[str, float]]] = {
        "ua_residual_z": ("FAISCEAU_BOUCHAGE", 1.5),
        "conc_bias_drift_z": ("CAPTEUR_DEFAILLANT", 4.0),
    }
    # M-3 — LA CORRECTION CI-DESSUS N'AVAIT PAS ETE PORTEE A LA TABLE JUMELLE.
    #
    # `_MODE_BY_THRESHOLD` portait quatre entrees, dont trois avec un tag et un
    # seuil VIDES :
    #
    #     "conc_drop_24h": ("FAISCEAU_FUITE",  "", "")
    #     "d_conc":        ("FAISCEAU_FUITE",  "", "")
    #     "flow_per_load": ("CALANDRE_FUITE",  "", "")
    #
    # `_mode_for_feature` sort sur `if not tag_name: return None` : trois entrees
    # sur quatre rendaient invariablement `None`. La table paraissait rattacher
    # quatre grandeurs a trois modes de defaillance, et n'en rattachait qu'une —
    # exactement la « couverture illusoire » que le commentaire condamne quinze
    # lignes plus haut, dans la table d'a cote.
    #
    # LE COMPORTEMENT ETAIT JUSTE, C'EST LA FORME QUI MENTAIT. Ces trois
    # grandeurs sont des variations, et la regle deterministe correspondante
    # porte deja son seuil de materialite : le modele ne doit pas la doubler.
    # Les supprimer aurait efface cette DECISION et laisse croire a un oubli —
    # un futur relecteur les aurait rattachees. Elles sont donc declarees pour
    # ce qu'elles sont, dans un ensemble qui porte son nom, et la table ne
    # contient plus que ce qui peut reellement accuser.
    _MODE_BY_THRESHOLD: ClassVar[dict[str, tuple[str, str, str]]] = {
        # feature -> (mode, tag du referentiel, seuil a franchir)
        "conc_min": ("FAISCEAU_CORROSION", "C_ACID_1100", "alarm_low"),
    }

    # Grandeurs de variation qui ne portent DELIBEREMENT aucune accusation : la
    # regle deterministe correspondante porte deja son seuil de materialite.
    _FEATURES_SANS_ACCUSATION: ClassVar[frozenset[str]] = frozenset({
        "conc_drop_24h",
        "d_conc",
        "flow_per_load",
    })

    def _mode_for_feature(self, feature: str, row: pd.Series) -> str | None:
        """Rattache une feature dominante a un mode AMDEC, si c'est justifie.

        Args:
            feature: Nom de la feature dominante de l'attribution.
            row: Ligne de features de l'instant analyse.

        Returns:
            Code de mode AMDEC, ou None quand aucune accusation n'est fondee.
        """
        if feature in self._MODE_BY_RESIDUAL:
            mode, min_sigma = self._MODE_BY_RESIDUAL[feature]
            value = _f(row.get(feature))
            if value is None:
                return None
            return mode if abs(value) >= min_sigma else None

        if feature in self._FEATURES_SANS_ACCUSATION:
            # Grandeur de variation : la regle deterministe correspondante porte
            # deja son propre seuil de materialite. Voir M-3.
            return None

        if feature in self._MODE_BY_THRESHOLD:
            mode, tag_name, threshold_name = self._MODE_BY_THRESHOLD[feature]
            value = _f(row.get(feature))
            limit = self.domain.get(tag_name).threshold(threshold_name)
            if value is None or limit is None:
                return None
            return mode if value <= limit else None

        return None

    # -- Persistance ----------------------------------------------------------

    def save(self, path: str | Path) -> Path:
        """Serialise le detecteur complet.

        Args:
            path: Chemin du fichier .joblib.

        Returns:
            Le chemin ecrit.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({
            "stat": self.stat,
            "references": self.references,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "features": MODEL_FEATURES,
        }, path)
        logger.info(f"Detecteur sauvegarde: {path}")
        return path

    @classmethod
    def load(cls, path: str | Path, domain: DomainKnowledge | None = None) -> CoolerAnomalyDetector:
        """Recharge un detecteur serialise.

        Args:
            path: Chemin du fichier .joblib.
            domain: Connaissance domaine (rechargee par defaut).

        Returns:
            Detecteur pret a l'emploi.

        Raises:
            FileNotFoundError: Si le fichier est absent.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Modele introuvable: {path}. Lancer `make train`.")
        bundle = joblib.load(path)
        return cls(domain=domain, stat=bundle["stat"], references=bundle.get("references"))


def _max_severity(severities: list[str]) -> Severity:
    """Retourne la severite la plus elevee d'une liste.

    Args:
        severities: Liste de severites.

    Returns:
        La plus elevee, ou 'NORMAL' si la liste est vide.
    """
    if not severities:
        return "NORMAL"
    return max(severities, key=lambda s: SEVERITY_ORDER.get(s, 0))  # type: ignore[return-value]


if __name__ == "__main__":
    from src.config import DCS_EXPORT
    from src.features.e7301_features import build_features
    from src.ingest.dcs_loader import ingest

    res = ingest(DCS_EXPORT)
    feats, refs = build_features(res.readings, res.quality)
    det = CoolerAnomalyDetector(references=refs).fit(feats)

    scores = det.score_series(feats)
    n_flag = int((scores >= det.stat.threshold_).sum())
    print(f"\nScores: n={len(scores)}, seuil={det.stat.threshold_:.3f}, "
          f"heures atypiques={n_flag} ({100 * n_flag / len(scores):.1f}%)")

    ep = det.episodes(feats)
    print(f"\nEPISODES agreges: {len(ep)}")
    print(ep.head(15).to_string(index=False))

    print("\nDetail des 8 episodes les plus marques:")
    for _, e in ep.head(8).iterrows():
        r = det.analyze(feats, e["peak_at"])
        codes = ", ".join(f"{f.code}({f.severity})" for f in r.findings)
        print(f"  {e['peak_at']} | {r.severity:8s} | {e['duration_h']:4d} h | "
              f"score={r.anomaly_score:.3f} | {codes}")
