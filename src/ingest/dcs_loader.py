"""
Ingestion des donnees DCS reelles du refroidisseur E7301 (DATA.xlsx).

Ce module fait UNE chose et la fait proprement : transformer l'export DCS brut
en une table exploitable, SANS jamais masquer un probleme de donnee.

Principe directeur — la qualite de donnee est une information, pas un dechet.
Un capteur fige ou un code `I/O Timeout` n'est pas du bruit a nettoyer : c'est
le mode de defaillance CAPTEUR_DEFAILLANT de l'AMDEC (criticite 108). On le
detecte, on l'horodate, on le tracé, et on l'exclut du calcul de performance.
Un pipeline qui ferait un `fillna(method='ffill')` sur ces donnees produirait
un systeme qui declare "tout va bien" pendant 7 mois de capteur mort.

Sorties produites :
  - `readings`     : une ligne par horodatage, une colonne par alias de tag
  - `quality`      : une ligne par (horodatage, tag) en defaut, avec le motif
  - `sensor_health`: synthese par tag (taux de dispo, periodes de gel, butees)

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from src.domain.knowledge import DomainKnowledge, Tag, load_domain, seuil
from src.formatting import duree_pas

# Un signal strictement constant pendant >= FROZEN_MIN_HOURS heures consecutives
# est considere fige. 6 h = un poste : en marche etablie, aucune temperature ou
# aucun debit reel ne reste identique au 1e-9 pres pendant un poste entier.
FROZEN_MIN_HOURS = 6
FROZEN_EPS = 1e-9

# Tolerance relative pour considerer une valeur "collee a la butee d'echelle".
SATURATION_REL_TOL = 1e-4

# Feuille du classeur designee par `tags.yaml/governance_defaults.source_location`.
DEFAULT_SHEET = "Feuil1"




# ── Resultat d'ingestion ──────────────────────────────────────────────────────

@dataclass
class IngestionResult:
    """Produit complet de l'ingestion.

    Attributes:
        readings: DataFrame indexe par timestamp, colonnes = alias de tags.
        observations: Valeurs numériques DCS observées, y compris les capteurs
            dégradés, réservées à la visualisation et jamais au modèle.
        quality: Evenements de qualite (timestamp, tag, alias, issue, detail).
        sensor_health: Synthese de sante par tag.
        report: Metriques globales de l'ingestion.
    """

    readings: pd.DataFrame
    observations: pd.DataFrame
    quality: pd.DataFrame
    sensor_health: pd.DataFrame
    report: dict[str, Any]

    def summary(self) -> str:
        """Resume texte lisible de l'ingestion."""
        r = self.report
        lines = [
            f"Periode        : {r['t_start']} -> {r['t_end']}",
            f"Echantillons   : {r['n_rows']} (pas nominal {r['step_nominal']})",
            f"Trous temporels: {r['n_gaps']}   Doublons: {r['n_duplicates']}",
            "Etats process  : " + ", ".join(f"{k}={v}" for k, v in r["state_counts"].items()),
            f"Evenements qualite: {r['n_quality_events']}",
        ]
        return "\n".join(lines)


# ── Chargement brut ───────────────────────────────────────────────────────────

def read_raw(path: str | Path, sheet: str | int | None = None) -> pd.DataFrame:
    """Lit l'export DCS brut sans aucune conversion de type.

    Les colonnes contiennent un melange de nombres et de codes qualite texte
    ('Bad', 'Configure', 'I/O Timeout'). On lit tout en `object` pour ne rien
    perdre : la separation se fait a l'etape suivante.

    Args:
        path: Chemin du fichier Excel export DCS.
        sheet: Nom ou index de la feuille. None = feuille gouvernee.

    Returns:
        DataFrame brut, colonne temporelle nommee 'TIME'.

    Raises:
        FileNotFoundError: Si le fichier est absent.
        ValueError: Si aucune colonne temporelle n'est identifiable.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Export DCS introuvable: {path}")

    # LA FEUILLE EST NOMMEE PAR LE REFERENTIEL, PAS DEVINEE PAR SA POSITION.
    # `sheet_name=0` lisait la premiere feuille quelle qu'elle soit : l'ajout
    # d'un onglet en tete de classeur aurait fait ingerer silencieusement des
    # donnees etrangeres. `tags.yaml/governance_defaults.source_location`
    # designe « Feuille Feuil1 ». On la cherche par son nom et l'on se rabat
    # sur la premiere en le disant.
    if sheet is None:
        feuilles = pd.ExcelFile(path).sheet_names
        sheet = DEFAULT_SHEET if DEFAULT_SHEET in feuilles else 0
        if sheet == 0:
            logger.warning(
                f"Feuille '{DEFAULT_SHEET}' absente de {path.name} "
                f"(feuilles: {feuilles}) — lecture de la premiere feuille"
            )
    df = pd.read_excel(path, sheet_name=sheet)
    time_col = next((c for c in df.columns if str(c).strip().upper() in {"TIME", "TIMESTAMP", "DATE"}), None)
    if time_col is None:
        raise ValueError(f"Aucune colonne temporelle dans {path} (colonnes: {list(df.columns)[:5]})")

    df = df.rename(columns={time_col: "TIME"})
    df["TIME"] = pd.to_datetime(df["TIME"], errors="coerce")
    n_bad_time = int(df["TIME"].isna().sum())
    if n_bad_time:
        logger.warning(f"{n_bad_time} horodatages illisibles supprimes")
        df = df.dropna(subset=["TIME"])
    logger.info(f"Export DCS lu: {len(df)} lignes, {df.shape[1] - 1} tags")
    return df


# ── Detection des defauts capteur ─────────────────────────────────────────────

def _detect_quality_codes(raw: pd.DataFrame, domain: DomainKnowledge) -> pd.DataFrame:
    """Extrait les codes qualite texte du DCS.

    Args:
        raw: DataFrame brut avec colonne 'TIME'.
        domain: Connaissance domaine (pour le mapping tag -> alias).

    Returns:
        DataFrame des evenements (timestamp, tag, alias, issue, detail, severity).
    """
    known = domain.quality_codes
    events: list[dict] = []
    for col in raw.columns:
        if col == "TIME" or col not in domain.tags:
            continue
        s = raw[col]
        numeric = pd.to_numeric(s, errors="coerce")
        mask = numeric.isna() & s.notna()
        if not mask.any():
            continue
        for ts, val in zip(raw.loc[mask, "TIME"], s[mask], strict=True):
            code = str(val).strip()
            meta = known.get(code, {"severity": "MEDIUM", "meaning": f"Code DCS non repertorie: {code}"})
            events.append({
                "timestamp": ts,
                "tag": col,
                "alias": domain.tags[col].alias,
                "issue": "QUALITY_CODE",
                "detail": code,
                "severity": meta["severity"],
                "meaning": meta["meaning"],
            })
    return pd.DataFrame(events)


def _structural_quality_events(
    raw: pd.DataFrame,
    known_cols: list[str],
    domain: DomainKnowledge,
) -> pd.DataFrame:
    """Trace absences, doublons et ordre temporel avant toute transformation."""
    events: list[dict[str, Any]] = []
    for col in known_cols:
        for ts in raw.loc[raw[col].isna(), "TIME"]:
            events.append({
                "timestamp": ts,
                "tag": col,
                "alias": domain.tags[col].alias,
                "issue": "MISSING_VALUE",
                "detail": "Cellule source vide",
                "severity": "MEDIUM",
                "meaning": "Valeur absente conservée comme NaN; aucune imputation",
            })
    duplicate_counts = raw["TIME"].value_counts()
    for ts, count in duplicate_counts[duplicate_counts > 1].items():
        events.append({
            "timestamp": ts,
            "tag": "*",
            "alias": "*",
            "issue": "DUPLICATE_TIMESTAMP",
            "detail": f"{int(count)} lignes; dernière ligne source conservée",
            "severity": "MEDIUM",
            "meaning": "Fusion déterministe par ordre source, tracée et non silencieuse",
        })
    out_of_order = raw["TIME"].diff().lt(pd.Timedelta(0))
    for ts in raw.loc[out_of_order, "TIME"]:
        events.append({
            "timestamp": ts,
            "tag": "*",
            "alias": "*",
            "issue": "OUT_OF_ORDER",
            "detail": "Horodatage antérieur à la ligne source précédente",
            "severity": "MEDIUM",
            "meaning": "Réordonnancement chronologique explicite après audit",
        })
    return pd.DataFrame(events)


def _detect_frozen(
    series: pd.Series,
    eligible: pd.Series | None = None,
    min_hours: int = FROZEN_MIN_HOURS,
) -> pd.Series:
    """Marque les points appartenant a une plage de signal strictement constant.

    Le masque `eligible` est essentiel : pendant un arret de ligne, un debit
    reste legitimement a 0.0 pendant des jours. Le declarer "capteur fige"
    genererait des milliers de fausses alertes instrumentation. On ne cherche
    un gel que sur les periodes ou le signal EST CENSE bouger.

    Args:
        series: Serie numerique indexee par le temps.
        eligible: Masque booleen des instants ou le gel est significatif.
                  None = tous les instants.
        min_hours: Duree minimale (en echantillons) pour declarer un gel.

    Returns:
        Serie booleenne alignee sur `series`.
    """
    s = series.astype(float)
    if eligible is None:
        eligible = pd.Series(True, index=s.index)

    # Un identifiant de palier incremente a chaque changement de valeur.
    block = (s.diff().abs() > FROZEN_EPS).cumsum()

    # LE GEL EST DECLARE A PARTIR DU MOMENT OU IL EST ETABLI, PAS AVANT.
    #
    # Une version precedente mesurait la longueur TOTALE du palier
    # (`transform("sum")`) et marquait retroactivement tous ses points, y
    # compris ceux ou l'on ne pouvait pas encore savoir que le signal allait
    # rester constant. Deux mille trois cent vingt-sept evenements FROZEN
    # etaient dates de cette facon, et ils alimentent `n_invalid_tags`, la
    # regle CAPTEUR_DEFAILLANT et le drapeau d'applicabilite du modele : la
    # chaine consommait donc une information venue du futur.
    #
    # Le compteur cumulatif ne regarde que le passe : un point est declare gele
    # au moment ou la duree ecoulee depuis le debut du palier atteint le seuil,
    # ce qui est exactement ce qu'un systeme en ligne pourrait constater.
    eff_len = eligible.groupby(block).cumsum()
    frozen = (eff_len >= min_hours) & s.notna() & eligible
    return frozen.fillna(False)


def _detect_sensor_faults(
    values: pd.DataFrame,
    domain: DomainKnowledge,
    eligible: pd.Series,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Detecte gel, saturation et sortie de plage physique.

    Args:
        values: DataFrame numerique indexe par timestamp, colonnes = tags DCS.
        domain: Connaissance domaine (plages physiques, butees).
        eligible: Masque des instants ou la ligne n'est pas a l'arret.

    Returns:
        Tuple (evenements, masque booleen des points invalides par tag).
    """
    events: list[dict] = []
    invalid = pd.DataFrame(False, index=values.index, columns=values.columns)

    for col in values.columns:
        tag: Tag = domain.tags[col]
        s = values[col]

        # 1. Butee d'echelle (saturation) — prioritaire : c'est la cause,
        #    le gel n'en est que la consequence visible.
        saturated = pd.Series(False, index=s.index)
        sat = tag.saturation_value
        if sat is not None:
            saturated = ((s - sat).abs() <= max(abs(sat) * SATURATION_REL_TOL, 1e-6)).fillna(False)
            invalid[col] |= saturated
            for ts in values.index[saturated]:
                events.append({
                    "timestamp": ts, "tag": col, "alias": tag.alias, "issue": "SATURATED",
                    "detail": f"{sat:g}", "severity": "HIGH",
                    "meaning": "Mesure collee a la butee d'echelle du transmetteur",
                })

        # 2. Hors plage physique
        out_of_range = pd.Series(False, index=s.index)
        rng = tag.range_physical
        if rng is not None:
            out_of_range = (((s < rng[0]) | (s > rng[1])) & s.notna()).fillna(False)
            invalid[col] |= out_of_range
            for ts in values.index[out_of_range]:
                events.append({
                    "timestamp": ts, "tag": col, "alias": tag.alias, "issue": "OUT_OF_RANGE",
                    "detail": f"{s.loc[ts]:.6g} hors [{rng[0]:g}, {rng[1]:g}]",
                    "severity": "HIGH", "meaning": "Valeur physiquement impossible",
                })

        # 3. Gel de signal — uniquement hors arret, et hors points deja
        #    disqualifies par la saturation (sinon on compte deux fois).
        frozen = _detect_frozen(s, eligible=eligible) & ~saturated & ~out_of_range
        invalid[col] |= frozen
        for ts in values.index[frozen]:
            events.append({
                "timestamp": ts, "tag": col, "alias": tag.alias, "issue": "FROZEN",
                "detail": f"{s.loc[ts]:.6g}", "severity": "HIGH",
                "meaning": f"Signal constant >= {FROZEN_MIN_HOURS} h en marche",
            })

    return pd.DataFrame(events), invalid


# ── Etat process ──────────────────────────────────────────────────────────────

def classify_process_state(df: pd.DataFrame, domain: DomainKnowledge) -> pd.Series:
    """Classe chaque horodatage en STOPPED / TRANSIENT / RUNNING.

    C'est l'etape la plus importante du pipeline. Sans elle, un arret planifie
    de la ligne est interprete comme une anomalie majeure du refroidisseur, et
    le systeme noie l'operateur sous des fausses alertes. Seul l'etat RUNNING
    autorise le jugement de performance de l'echangeur.

    Args:
        df: DataFrame avec les colonnes alias LOAD_SULFUR, F_ACID, T_ACID_IN.
        domain: Connaissance domaine (seuils d'arret).

    Returns:
        Serie de chaines ('STOPPED' | 'TRANSIENT' | 'RUNNING').
    """
    # UNE COLONNE ABSENTE N'EST PAS UNE ABSENCE DE CRITERE.
    # Les trois colonnes etaient lues par `df.get(...)` et chaque critere etait
    # applique « si la colonne existe ». Un export ampute d'une colonne
    # produisait donc silencieusement une classification fondee sur moins de
    # criteres — sur la decision la plus determinante du systeme, sans qu'aucun
    # message ne le signale.
    manquantes = [c for c in ("LOAD_SULFUR", "F_ACID", "T_ACID_IN") if c not in df.columns]
    if manquantes:
        raise ValueError(
            f"Classification d'etat impossible : colonne(s) absente(s) "
            f"{manquantes}. Les trois grandeurs sont requises; sans elles la "
            f"marche etablie ne peut pas etre distinguee d'un arret."
        )
    load, flow, t_in = df["LOAD_SULFUR"], df["F_ACID"], df["T_ACID_IN"]

    # LES QUATRE SEUILS VIENNENT DU REFERENTIEL, AUCUN N'EST ECRIT ICI.
    # `T_ACID_IN < 60` et `d(charge)/dt > 2` etaient codes en dur alors que
    # `tags.yaml` les decrivait en prose sous `process_states` : une correction
    # metier n'avait aucun effet. Ils sont desormais gouvernes, comme les deux
    # autres.
    #
    # Le repli utilise `is None` et non `or` : avec `or`, un seuil legitimement
    # nul aurait ete remplace par la valeur de secours.
    shutdown_load = seuil(domain.get("LOAD_SULFUR").spec.get("shutdown_below"), 8.0)
    flow_ll = seuil(domain.get("F_ACID").threshold("alarm_low_low"), 20.0)
    shutdown_temp = seuil(domain.get("T_ACID_IN").spec.get("shutdown_below"), 60.0)
    transient_rate = seuil(
        domain.get("LOAD_SULFUR").spec.get("transient_rate_per_h"), 2.0
    )

    state = pd.Series("RUNNING", index=df.index, dtype=object)

    is_down = load.fillna(0) < shutdown_load
    is_down |= flow.fillna(0) < flow_ll
    is_down |= t_in.fillna(0) < shutdown_temp

    # Transitoire : forte variation de charge, ou REPRISE apres un arret.
    #
    # LE CLASSEMENT NE LIT PLUS L'INSTANT SUIVANT.
    # Une version precedente ajoutait `is_down.shift(-1)` : l'instant t etait
    # declare TRANSIENT parce que la ligne s'arretait en t+1. C'est une lecture
    # du futur, et elle contredisait frontalement la promesse du rejeu — « a
    # l'instant t, seule la fenetre [debut, t] est transmise a la detection ».
    # Vingt-sept horodatages etaient concernes; ils etaient ecartes du modele
    # et des regles de performance sur la foi d'une information qui n'existait
    # pas encore. Aucune conclusion ne change, mais une chaine de detection ne
    # peut pas etre a demi causale.
    is_trans = load.diff().abs() > transient_rate
    is_trans |= is_down.shift(1, fill_value=False)

    state[is_trans & ~is_down] = "TRANSIENT"
    state[is_down] = "STOPPED"
    return state


# ── Pipeline complet ──────────────────────────────────────────────────────────

def ingest(
    path: str | Path,
    domain: DomainKnowledge | None = None,
    sheet: str | int | None = None,
) -> IngestionResult:
    """Pipeline d'ingestion complet de l'export DCS.

    Args:
        path: Chemin vers DATA.xlsx (ou tout export au meme format).
        domain: Connaissance domaine. Chargee par defaut si omise.
        sheet: Feuille Excel a lire. None = feuille gouvernee.

    Returns:
        IngestionResult contenant readings, quality, sensor_health et report.
    """
    domain = domain or load_domain()
    raw = read_raw(path, sheet=sheet)

    # -- Conversion numerique + colonnes connues uniquement
    known_cols = [c for c in raw.columns if c in domain.tags]
    unknown_cols = [c for c in raw.columns if c != "TIME" and c not in domain.tags]
    if unknown_cols:
        logger.warning(
            f"{len(unknown_cols)} tag(s) absent(s) du registre domaine, ignore(s): {unknown_cols}"
        )
    # -- Qualité structurelle et codes DCS avant conversion numérique.
    q_structural = _structural_quality_events(raw, known_cols, domain)
    q_codes = _detect_quality_codes(raw, domain)

    values = raw[known_cols].apply(pd.to_numeric, errors="coerce")
    values.index = pd.DatetimeIndex(raw["TIME"])

    # -- Doublons : dernière ligne dans l'ordre SOURCE, puis tri chronologique.
    n_duplicates = int(values.index.duplicated().sum())
    if n_duplicates:
        logger.warning(f"{n_duplicates} horodatage(s) duplique(s) — derniere valeur conservee")
        values = values[~values.index.duplicated(keep="last")]
    n_out_of_order = int(raw["TIME"].diff().lt(pd.Timedelta(0)).sum())
    values = values.sort_index(kind="stable")

    # -- Etat process PRELIMINAIRE, calcule sur les valeurs brutes.
    #    Necessaire avant la detection de gel : pendant un arret, un signal
    #    legitimement constant a 0 ne doit pas etre pris pour un capteur mort.
    prelim = values.rename(columns=domain.alias_map())
    prelim_state = classify_process_state(prelim, domain)
    eligible = prelim_state.ne("STOPPED")

    # -- Defauts capteur
    q_faults, invalid_mask = _detect_sensor_faults(values, domain, eligible)

    # -- Table de lecture en alias, valeurs invalides mises a NaN.
    #    On ne les remplace PAS : une donnee absente doit rester absente,
    #    sinon le modele apprend sur une invention.
    observations = values.rename(columns=domain.alias_map()).copy()
    observations.index.name = "timestamp"
    clean = values.mask(invalid_mask).rename(columns=domain.alias_map())

    # Les tags declares 'degraded' sont exclus d'office du perimetre exploitable.
    degraded_aliases = [t.alias for t in domain.tags_by_role("degraded")]
    clean = clean.drop(columns=[c for c in degraded_aliases if c in clean.columns])

    clean.index.name = "timestamp"
    clean["process_state"] = classify_process_state(clean, domain)

    # -- Trous temporels
    step = pd.Series(clean.index).diff().mode()
    step_nominal = step.iloc[0] if len(step) else pd.Timedelta("1h")
    gaps = pd.Series(clean.index).diff()
    n_gaps = int((gaps > step_nominal).sum())
    gap_events = pd.DataFrame([
        {
            "timestamp": clean.index[i],
            "tag": "*",
            "alias": "*",
            "issue": "TIME_GAP",
            "detail": str(delta),
            "severity": "MEDIUM",
            "meaning": "Trou supérieur au pas nominal; aucune ligne synthétique créée",
        }
        for i, delta in enumerate(gaps)
        if i > 0 and pd.notna(delta) and delta > step_nominal
    ])

    # -- Consolidation qualite
    quality = pd.concat(
        [d for d in (q_structural, q_codes, q_faults, gap_events) if len(d)],
        ignore_index=True,
    )
    if len(quality):
        quality = quality.sort_values("timestamp").reset_index(drop=True)
    else:
        quality = pd.DataFrame(columns=["timestamp", "tag", "alias", "issue", "detail", "severity", "meaning"])

    health = _sensor_health(values, quality, domain)

    report = {
        "source": str(path),
        "t_start": str(clean.index.min()),
        "t_end": str(clean.index.max()),
        "n_raw_rows": len(raw),
        "n_rows": len(clean),
        "n_tags": len(known_cols),
        # LE PAS EST MIS EN FORME ICI, PAS DANS LE NAVIGATEUR.
        #
        # `str(step_nominal)` publiait « 0 days 01:00:00 », la representation
        # interne d'un `Timedelta` pandas. Le poste corrigeait le tir avec sa
        # propre fonction `duree()` en JavaScript, tandis que `duree_pas()`,
        # ecrite en Python pour exactement ce cas et citee par l'ADR-011 comme
        # preuve que « la mise en forme est centralisee », n'etait appelee par
        # personne. Deux implementations d'une meme regle, dans deux langages,
        # dont la seule vivante etait celle que l'ADR dit ne pas exister — et
        # elles divergeaient deja sur les durees composees.
        "step_nominal": duree_pas(step_nominal),
        "step_nominal_iso": step_nominal.isoformat(),
        "n_gaps": n_gaps,
        "n_duplicates": n_duplicates,
        "duplicate_resolution": (
            "Dernière ligne dans l'ordre source conservée; événement "
            "DUPLICATE_TIMESTAMP enregistré"
        ),
        "n_out_of_order": n_out_of_order,
        "n_quality_events": len(quality),
        "state_counts": clean["process_state"].value_counts().to_dict(),
        "unknown_tags": unknown_cols,
        "excluded_degraded": degraded_aliases,
        "imputation_policy": "Aucune imputation globale; valeurs invalides ou absentes = NaN",
        "unit_control": (
            "Unités attendues gouvernées dans tags.yaml; DATA.xlsx ne fournit "
            "pas de métadonnée d'unité par ligne permettant un change-point d'unité"
        ),
    }
    logger.info(f"Ingestion terminee — {report['n_rows']} lignes, "
                f"{report['n_quality_events']} evenements qualite")
    return IngestionResult(clean, observations, quality, health, report)


def _sensor_health(
    values: pd.DataFrame, quality: pd.DataFrame, domain: DomainKnowledge
) -> pd.DataFrame:
    """Construit la synthese de sante par capteur.

    Args:
        values: Valeurs numeriques brutes par tag DCS.
        quality: Evenements de qualite consolides.
        domain: Connaissance domaine.

    Returns:
        DataFrame une ligne par tag, trie par disponibilite croissante.
    """
    n = len(values)
    rows = []
    for col in values.columns:
        tag = domain.tags[col]
        ev = quality[quality["tag"] == col] if len(quality) else quality
        n_bad = len(ev)
        # Disponibilite = part des horodatages SANS aucun defaut. On compte des
        # instants distincts, pas des evenements : un meme instant peut cumuler
        # plusieurs defauts (ex. sature ET hors plage) sans compter double.
        n_bad_ts = int(ev["timestamp"].nunique()) if n_bad else 0
        by_issue = ev["issue"].value_counts().to_dict() if len(ev) else {}
        rows.append({
            "tag": col,
            "alias": tag.alias,
            "role": tag.role,
            "confidence": tag.confidence,
            "availability_pct": round(100.0 * (n - n_bad_ts) / n, 2) if n else 0.0,
            "n_bad_timestamps": n_bad_ts,
            "n_events": n_bad,
            "n_quality_code": by_issue.get("QUALITY_CODE", 0),
            "n_frozen": by_issue.get("FROZEN", 0),
            "n_saturated": by_issue.get("SATURATED", 0),
            "n_out_of_range": by_issue.get("OUT_OF_RANGE", 0),
            "first_event": str(ev["timestamp"].min()) if n_bad else "",
            "last_event": str(ev["timestamp"].max()) if n_bad else "",
        })
    return pd.DataFrame(rows).sort_values("availability_pct").reset_index(drop=True)


if __name__ == "__main__":
    from src.config import DCS_EXPORT

    res = ingest(DCS_EXPORT)
    print(res.summary())
    print("\n--- SANTE CAPTEURS ---")
    print(res.sensor_health.to_string(index=False))
    print("\n--- EVENEMENTS QUALITE (extrait) ---")
    print(res.quality.head(10).to_string(index=False))
