"""Produit les figures du mémoire E7301, toutes depuis les données réelles.

POURQUOI UN SCRIPT ET PAS DES IMAGES

Une figure produite à la main est un chiffre de plus qui dérive. Celles-ci sont
recalculées depuis `data/raw/DATA.xlsx` et les artefacts de `reports/` à chaque
exécution : si une valeur change dans la chaîne, la figure change avec elle.

Chaque figure porte **sa source en pied**, de sorte qu'un lecteur du mémoire
puisse la refaire.

Sortie : `reports/figures/` — un PNG par figure, plus `MANIFESTE.md` qui
récapitule ce que chacune montre et d'où elle vient.

Usage :
    python scripts/generer_figures.py            # toutes les figures possibles
    python scripts/generer_figures.py --liste    # ce qui serait produit

Certaines figures exigent l'étage statistique (`scikit-learn`). Si la
bibliothèque manque, elles sont **déclarées manquantes**, jamais remplacées par
une approximation.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if __package__ in {None, ""}:
    sys.path.insert(0, str(RACINE))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter

SORTIE = RACINE / "reports" / "figures"
RAPPORTS = RACINE / "reports"

# ── Charte ───────────────────────────────────────────────────────────────────
#
# Reprise du poste (ADR-008) mais transposee pour l'IMPRESSION : fond blanc,
# traits plus sombres. Les teintes procede gardent leur sens — ambre pour
# l'acide, turquoise pour l'eau de mer — parce qu'un lecteur qui a vu l'ecran
# doit retrouver le meme code dans le rapport.
ACIDE = "#b05a28"
MER = "#1d7f96"
ALERTE = "#c8791a"
FAUTE = "#b4322a"
OK = "#2e8b6b"
ENCRE = "#1d2325"
ENCRE2 = "#55666a"
TRAIT = "#d5dcde"

plt.rcParams.update({
    "figure.dpi": 110,
    "savefig.dpi": 200,
    "savefig.bbox": "tight",
    "font.size": 9.5,
    "axes.edgecolor": ENCRE2,
    "axes.labelcolor": ENCRE,
    "axes.titlesize": 11,
    "axes.titleweight": "bold",
    "axes.grid": True,
    "grid.color": TRAIT,
    "grid.linewidth": 0.7,
    "text.color": ENCRE,
    "xtick.color": ENCRE2,
    "ytick.color": ENCRE2,
    "legend.frameon": False,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})


def fr(x, decimales: int = 2) -> str:
    """Nombre en notation française — DÉLÉGUÉ, jamais réimplémenté.

    La première version de ce script recopiait la conversion : virgule
    décimale, séparateur de milliers, zéros de fin. C'est exactement le défaut
    FMT-1 de `src/notifications/redaction.py`, dont le commentaire dit que
    « le module qui invoque la règle de centralisation ne peut pas être celui
    qui l'enfreint ». ADR-011, règle 2.

    `src.formatting.nombre` porte l'espace fine insécable U+202F et le nombre
    de décimales demandé. On l'appelle.
    """
    from src.formatting import nombre
    return nombre(x, decimales)


def _tick(v, _pos=None) -> str:
    """Graduation d'axe : entière si elle l'est, sinon une décimale."""
    from src.formatting import nombre
    return nombre(v, 0 if float(v).is_integer() else 1)


VIRGULE = FuncFormatter(_tick)

_manifeste: list[tuple[str, str, str]] = []


def poser(fig, numero: int, titre: str, source: str, bas: float = -0.02) -> None:
    """Écrit la figure sur disque et l'inscrit au manifeste."""
    fig.text(
        0.005, bas, f"Source : {source}",
        fontsize=7, color=ENCRE2, style="italic", va="top",
    )
    nom = f"F{numero:02d}-{titre.lower().replace(' ', '-').replace(chr(39), '-')}.png"
    nom = "".join(c for c in nom if c.isalnum() or c in "-._")
    chemin = SORTIE / nom
    fig.savefig(chemin)
    plt.close(fig)
    _manifeste.append((f"F{numero}", titre, nom))
    print(f"  F{numero:<3} {titre:<52} {nom}")


# ── Chargement ───────────────────────────────────────────────────────────────

def charger():
    """Chaîne complète, sans l'étage statistique."""
    from src.domain.knowledge import load_domain
    from src.features.e7301_features import build_features
    from src.ingest.dcs_loader import ingest

    domaine = load_domain()
    ingestion = ingest(str(RACINE / "data" / "raw" / "DATA.xlsx"), domaine)
    features, references = build_features(
        ingestion.readings, ingestion.quality, domaine
    )
    return domaine, ingestion, features, references


def artefact(nom: str):
    chemin = RAPPORTS / nom
    if not chemin.exists():
        return None
    return json.loads(chemin.read_text(encoding="utf-8"))


# ── Figures ──────────────────────────────────────────────────────────────────

def f03_distribution_sortie(features: pd.DataFrame) -> None:
    """La bande de 3 °C qui condamne l'approche générique."""
    run = features[features["process_state"].eq("RUNNING")]
    serie = run["T_ACID_OUT"].dropna()
    p01, p99 = serie.quantile(0.01), serie.quantile(0.99)

    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    ax.hist(serie, bins=90, color=ACIDE, alpha=0.85, edgecolor="white", linewidth=0.3)
    ax.axvline(66.0, color=ENCRE, linestyle="--", linewidth=1.3)
    ax.axvspan(p01, p99, color=MER, alpha=0.10)
    ax.annotate(
        f"P1–P99 : {fr(p01, 1)} – {fr(p99, 1)} °C\nsoit {fr(p99 - p01, 1)} °C d'amplitude",
        xy=(p01, ax.get_ylim()[1] * 0.72), fontsize=9, color=ENCRE,
        bbox=dict(boxstyle="round,pad=0.4", fc="white", ec=TRAIT),
    )
    ax.annotate("consigne 66 °C", xy=(66.0, ax.get_ylim()[1] * 0.95),
                xytext=(6, 0), textcoords="offset points", fontsize=8, color=ENCRE)
    ax.set_xlabel("Température de sortie acide (°C)")
    ax.set_ylabel("Heures de marche établie")
    ax.set_title("La variable de sortie est régulée : elle ne porte pas l'encrassement")
    ax.xaxis.set_major_formatter(VIRGULE)
    poser(fig, 3, "Distribution de la temperature de sortie acide",
          f"DATA.xlsx, {len(serie)} h de marche établie · features.T_ACID_OUT")


def f04_ua_observe_attendu(features: pd.DataFrame) -> None:
    """UA observé contre attendu, avec la saisonnalité d'eau de mer."""
    run = features[features["process_state"].eq("RUNNING")]
    d = run[["ua_kw_per_k", "ua_expected", "T_SEAWATER"]].dropna()
    lissee = d.rolling("7D").mean()

    fig, (haut, bas) = plt.subplots(
        2, 1, figsize=(8.4, 5.0), sharex=True,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.12},
    )
    haut.plot(d.index, d["ua_kw_per_k"], color=ACIDE, linewidth=0.35, alpha=0.30)
    haut.plot(lissee.index, lissee["ua_kw_per_k"], color=ACIDE, linewidth=1.8,
              label="UA observé (moyenne 7 j)")
    haut.plot(lissee.index, lissee["ua_expected"], color=ENCRE, linewidth=1.4,
              linestyle="--", label="UA attendu par la référence")
    haut.set_ylabel("Coefficient d'échange (kW/K)")
    haut.set_title("Le coefficient d'échange suit l'eau de mer — la référence retire cette part")
    haut.legend(loc="upper left")
    haut.yaxis.set_major_formatter(VIRGULE)

    bas.plot(lissee.index, lissee["T_SEAWATER"], color=MER, linewidth=1.6)
    bas.fill_between(lissee.index, lissee["T_SEAWATER"], color=MER, alpha=0.12)
    bas.set_ylabel("Eau de mer\n(°C)")
    # L'ECHELLE COMMENCE A LA DONNEE, PAS A ZERO. Une amplitude de 5 degC
    # tracee de 0 a 22 se lit comme une droite : le panneau existe precisement
    # pour montrer cette amplitude.
    marge = (lissee["T_SEAWATER"].max() - lissee["T_SEAWATER"].min()) * 0.25
    bas.set_ylim(lissee["T_SEAWATER"].min() - marge, lissee["T_SEAWATER"].max() + marge)
    bas.yaxis.set_major_formatter(VIRGULE)
    poser(fig, 4, "Coefficient d'echange observe contre attendu",
          "features.ua_kw_per_k / ua_expected · climatologie de Safi (ADR-002)")


def f05_climatologie(features: pd.DataFrame) -> None:
    """La seule entrée du système extérieure à toute boucle de régulation."""
    from src.features.thermal import seawater_temperature

    jours = pd.date_range("2024-01-01", "2024-12-31", freq="D")
    mer = seawater_temperature(jours)

    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    ax.plot(jours, mer, color=MER, linewidth=2.0)
    ax.fill_between(jours, mer, mer.min(), color=MER, alpha=0.12)
    imin, imax = int(np.argmin(mer)), int(np.argmax(mer))
    for i, texte in ((imin, f"{fr(mer.iloc[imin], 1)} °C"), (imax, f"{fr(mer.iloc[imax], 1)} °C")):
        ax.annotate(texte, xy=(jours[i], mer.iloc[i]), xytext=(0, 8),
                    textcoords="offset points", ha="center", fontsize=9,
                    color=ENCRE, fontweight="bold")
    ax.set_ylabel("Température d'eau de mer (°C)")
    ax.set_title("Climatologie de Safi — l'entrée qu'aucune boucle de régulation ne déplace")
    ax.yaxis.set_major_formatter(VIRGULE)
    poser(fig, 5, "Climatologie de l-eau de mer a Safi",
          "src/features/thermal.py — seawater_temperature(), tags.yaml/external_inputs")


def f06_nuage_circulaire(features: pd.DataFrame) -> float:
    """LA figure du mémoire : le résidu de duty EST l'écart de consigne."""
    run = features[features["process_state"].eq("RUNNING")]
    d = run[["duty_kw", "duty_expected", "control_deviation"]].dropna()
    residu = d["duty_kw"] - d["duty_expected"]
    ecart = d["control_deviation"]
    r = float(residu.corr(ecart))

    pente, ordonnee = np.polyfit(ecart, residu, 1)
    xs = np.linspace(ecart.min(), ecart.max(), 100)

    fig, ax = plt.subplots(figsize=(7.0, 5.0))
    ax.scatter(ecart, residu, s=4, color=ACIDE, alpha=0.16, edgecolors="none")
    ax.plot(xs, pente * xs + ordonnee, color=FAUTE, linewidth=2.0)
    ax.axhline(0, color=TRAIT, linewidth=1)
    ax.axvline(0, color=TRAIT, linewidth=1)

    ax.text(
        0.03, 0.05,
        f"r = {fr(r, 3)}\n"
        f"r² = {fr(r * r, 3)}  —  {fr(100 * r * r, 1)} % de variance partagée\n"
        f"n = {fr(len(d), 0)} heures de marche établie",
        transform=ax.transAxes, fontsize=11, color=ENCRE, va="bottom",
        bbox=dict(boxstyle="round,pad=0.55", fc="white", ec=FAUTE, linewidth=1.4),
    )
    ax.set_xlabel("Écart à la consigne  (T sortie − 66 °C)")
    ax.set_ylabel("Résidu de puissance thermique  (observé − attendu, kW)")
    ax.set_title("Le résidu de duty n'est pas un indicateur : c'est l'écart de consigne réécrit")
    ax.xaxis.set_major_formatter(VIRGULE)
    ax.yaxis.set_major_formatter(VIRGULE)
    poser(fig, 6, "Nuage residu de duty contre ecart de consigne",
          "features.duty_kw − duty_expected × control_deviation · marche établie · ADR-001")
    return r


def f07_couverture_amdec(domaine) -> None:
    """Trois degrés, pas deux."""
    c = domaine.risk_coverage()
    # LA PART NON COUVERTE SE LIT, ELLE NE SE DEDUIT PAS. Calculer
    # `100 - couverte - partielle` donne 51,3 la ou le domaine mesure 51,2 :
    # l'arrondi des deux premieres se reporte sur la troisieme. Un pour cent de
    # rien du tout, mais c'est un chiffre de plus qui ne vient pas de la source.
    part_non_couverte = 100.0 * c["criticite_non_couverte"] / c["criticite_totale"]
    parts = [c["part_couverte_pct"], c["part_partielle_pct"], part_non_couverte]
    libelles = [
        f"détecté\n{fr(parts[0], 1)} %",
        f"conditions surveillées\nsans mesure d'état\n{fr(parts[1], 1)} %",
        f"non couvert —\nplan préventif\n{fr(parts[2], 1)} %",
    ]
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    coins, _ = ax.pie(
        parts, colors=[OK, ALERTE, "#9aa7ab"], startangle=90,
        wedgeprops=dict(width=0.42, edgecolor="white", linewidth=2),
    )
    for coin, texte in zip(coins, libelles):
        angle = np.deg2rad((coin.theta1 + coin.theta2) / 2)
        ax.annotate(texte, xy=(0.79 * np.cos(angle), 0.79 * np.sin(angle)),
                    ha="center", va="center", fontsize=8.5, color=ENCRE)
    ax.text(0, 0.08, fr(c["criticite_couverte"], 0), ha="center",
            fontsize=20, fontweight="bold", color=ENCRE)
    ax.text(0, -0.13, f"sur {fr(c['criticite_totale'], 0)}\nde criticité AMDEC",
            ha="center", fontsize=8.5, color=ENCRE2)
    ax.set_title("Les deux modes les plus critiques sont hors de portée du système")
    poser(fig, 7, "Couverture du risque AMDEC",
          "src/domain/amdec.yaml — DomainKnowledge.risk_coverage()")


def f10_notes_du_judge() -> None:
    """La grandeur qui compte est l'écart, pas le taux."""
    sains = pd.read_csv(RAPPORTS / "judge_eval_clean.csv")
    pieges = pd.read_csv(RAPPORTS / "judge_eval_traps.csv")
    resume = artefact("judge_eval_summary.json") or {}

    fig, ax = plt.subplots(figsize=(7.8, 4.4))
    ordonnes = pieges.sort_values("score_mean")
    y = np.arange(len(ordonnes))
    ax.barh(y, ordonnes["score_mean"], color=FAUTE, alpha=0.80, height=0.62)
    ax.set_yticks(y)
    ax.set_yticklabels(ordonnes["trap"], fontsize=8)
    note_saine = float(sains["score"].mean())
    ax.axvline(note_saine, color=OK, linewidth=2.0)
    ax.annotate(f"cas sains : {fr(note_saine, 2)}/10", xy=(note_saine, len(y) - 0.4),
                xytext=(-6, 0), textcoords="offset points", ha="right",
                fontsize=9, color=OK, fontweight="bold")
    ecart = resume.get("separation")
    if ecart is not None:
        ax.set_title(
            f"Écart de discrimination : {fr(ecart, 2)} points — c'est la mesure qui vaut"
        )
    else:
        ax.set_title("Note du contrôleur par type de faute injectée")
    ax.set_xlabel("Note moyenne du contrôleur (sur 10) — plus bas, plus ferme")
    ax.set_xlim(0, 10)
    ax.xaxis.set_major_formatter(VIRGULE)
    ax.grid(axis="y", visible=False)
    poser(fig, 10, "Note du controleur par faute injectee",
          "reports/judge_eval_traps.csv et judge_eval_clean.csv")


def f_independance(features: pd.DataFrame) -> None:
    """Figure ajoutée : les trois candidats indicateurs, côte à côte."""
    run = features[features["process_state"].eq("RUNNING")]
    lignes = [
        ("regulation_effort_z", "Effort de régulation", FAUTE,
         "conduite — jamais une preuve"),
        ("ua_residual_z", "Écart de coefficient d'échange", ACIDE,
         "diagnostic — partiellement confondu"),
        ("t_in_residual_z", "Écart de température d'entrée", MER,
         "contexte amont — indépendant"),
    ]
    # ECHELLE PARTAGEE. Les trois grandeurs sont en ECARTS-TYPES : les tracer
    # sur trois echelles differentes deforme la seule chose que cette figure
    # montre, la FORME du nuage. Une droite serree et une bande verticale ne se
    # comparent que sur un axe commun.
    fig, axes = plt.subplots(1, 3, figsize=(10.4, 3.9), sharey=True)
    for ax, (col, titre, couleur, lecture) in zip(axes, lignes):
        p = run[[col, "control_deviation"]].dropna()
        r = float(p[col].corr(p["control_deviation"]))
        ax.scatter(p["control_deviation"], p[col], s=3, color=couleur,
                   alpha=0.13, edgecolors="none")
        ax.set_title(f"{titre}\nr = {fr(r, 3)}   ({fr(100 * r * r, 1)} % partagé)",
                     fontsize=9.5)
        ax.set_xlabel("Écart à la consigne (°C)")
        ax.text(0.5, -0.34, lecture, transform=ax.transAxes, ha="center",
                fontsize=8, color=ENCRE2, style="italic")
        ax.xaxis.set_major_formatter(VIRGULE)
        ax.yaxis.set_major_formatter(VIRGULE)
    axes[0].set_ylabel("Grandeur, en écarts-types")
    axes[0].set_ylim(-7, 7)
    fig.suptitle(
        "Aucun des trois n'est parfait — UA porte le diagnostic parce qu'il est "
        "le seul construit sur ce que l'encrassement dégrade",
        fontsize=10, y=1.04,
    )
    fig.subplots_adjust(bottom=0.30)
    poser(fig, 18, "Independance des trois indicateurs candidats",
          "features · marche établie · independence_report()", bas=-0.14)


def f_qualite_capteurs(ingestion) -> None:
    """Figure ajoutée : la qualité de donnée est une information, pas un déchet."""
    sante = ingestion.sensor_health.sort_values("availability_pct")
    fig, ax = plt.subplots(figsize=(7.4, 4.2))
    couleurs = [
        FAUTE if v < 70 else (ALERTE if v < 95 else OK)
        for v in sante["availability_pct"]
    ]
    y = np.arange(len(sante))
    ax.barh(y, sante["availability_pct"], color=couleurs, height=0.62, alpha=0.88)
    ax.set_yticks(y)
    ax.set_yticklabels(sante["alias"], fontsize=8)
    for i, (v, alias) in enumerate(zip(sante["availability_pct"], sante["alias"])):
        ax.text(v + 1, i, f"{fr(v, 1)} %", va="center", fontsize=8, color=ENCRE2)
    ax.axvline(95, color=ENCRE2, linestyle=":", linewidth=1)
    ax.set_xlabel("Disponibilité de la mesure (%)")
    ax.set_xlim(0, 108)
    ax.set_title("Deux capteurs sont exclus du périmètre — et le poste le montre")
    ax.grid(axis="y", visible=False)
    ax.xaxis.set_major_formatter(VIRGULE)
    poser(fig, 19, "Disponibilite des douze capteurs",
          "IngestionResult.sensor_health — src/ingest/dcs_loader.py")


def f_psi_extrapolation() -> None:
    """Figure ajoutée : le PSI mesure la couverture saisonnière, pas une dérive."""
    rapport = artefact("model_validation.json")
    if not rapport:
        return
    plis = rapport["temporal_backtest"]["folds"]
    x = [f["seasonal_extrapolation"] * 100 for f in plis]
    y = [f["score_psi"] for f in plis]
    n = [f["fold"] for f in plis]

    fig, ax = plt.subplots(figsize=(7.0, 4.6))
    # LA LIGNE SUIT L'ABSCISSE, PAS L'ORDRE DES PLIS. Tracee dans l'ordre
    # 1-2-3-4 elle zigzague, ce qui suggere exactement le contraire de ce que
    # la figure demontre : la correspondance est MONOTONE en extrapolation.
    ordre = np.argsort(x)
    ax.plot([x[i] for i in ordre], [y[i] for i in ordre],
            color=ENCRE2, linewidth=1.0, linestyle=":", zorder=1)
    ax.scatter(x, y, s=150, color=ACIDE, zorder=3, edgecolors="white", linewidth=1.5)
    for xi, yi, ni in zip(x, y, n):
        ax.annotate(f"pli {ni} — {fr(yi, 3)}", xy=(xi, yi), xytext=(0, 15),
                    textcoords="offset points", ha="center", fontsize=9,
                    color=ENCRE, fontweight="bold")
    ax.set_xlim(-6, 108)
    ax.set_ylim(-0.25, max(y) * 1.22)
    limite = 0.25
    ax.axhline(limite, color=FAUTE, linestyle="--", linewidth=1.3)
    ax.annotate("limite 0,25 — issue du scoring de crédit,\ntransfert non argumenté",
                xy=(max(x) * 0.98, limite), xytext=(0, 8), textcoords="offset points",
                ha="right", fontsize=8, color=FAUTE)
    ax.set_xlabel("Part de la fenêtre de test hors de la plage d'eau de mer apprise (%)")
    ax.set_ylabel("PSI des scores")
    ax.set_title("Le PSI mesure la couverture saisonnière du découpage,\nnon une dérive du procédé")
    ax.xaxis.set_major_formatter(VIRGULE)
    ax.yaxis.set_major_formatter(VIRGULE)
    poser(fig, 20, "PSI contre extrapolation saisonniere",
          "reports/model_validation.json — temporal_backtest.folds")


# ── Orchestration ────────────────────────────────────────────────────────────

def main() -> int:
    SORTIE.mkdir(parents=True, exist_ok=True)
    print(f"Figures E7301 — {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    print(f"sortie : {SORTIE}\n")

    domaine, ingestion, features, _ = charger()
    print()

    f03_distribution_sortie(features)
    f04_ua_observe_attendu(features)
    f05_climatologie(features)
    r = f06_nuage_circulaire(features)
    f07_couverture_amdec(domaine)
    f10_notes_du_judge()
    f_independance(features)
    f_qualite_capteurs(ingestion)
    f_psi_extrapolation()

    manquantes = [
        ("F1", "Schéma de l'échangeur et position des capteurs",
         "schéma, à produire hors script"),
        ("F2", "Chaîne de traitement de DATA.xlsx au poste",
         "schéma, à produire hors script"),
        ("F8", "Banc d'injection — avancement à la détection",
         "exige l'étage statistique et une exécution du banc"),
        ("F9", "Sensibilité à la période de référence",
         "exige l'étage statistique"),
        ("F11", "Taux horaire de signalement mois par mois",
         "exige l'étage statistique"),
        ("F12–F17", "Captures du poste opérateur",
         "exigent le service démarré et un navigateur"),
    ]

    lignes = [
        "# Figures du mémoire E7301",
        "",
        f"Produites le {datetime.now(timezone.utc).strftime('%d/%m/%Y')} par "
        "`scripts/generer_figures.py`.",
        "",
        f"**r mesuré pour la figure 6 : {fr(r, 3)}** — c'est la valeur qui titre la figure.",
        "",
        "## Produites",
        "",
        "| # | figure | fichier |",
        "|---|---|---|",
    ]
    lignes += [f"| {n} | {t} | `{f}` |" for n, t, f in _manifeste]
    lignes += ["", "## Non produites, et pourquoi", "",
               "| # | figure | raison |", "|---|---|---|"]
    lignes += [f"| {n} | {t} | {raison} |" for n, t, raison in manquantes]
    lignes += [
        "",
        "> Une figure absente est déclarée absente. Aucune n'est remplacée par "
        "une approximation ni par un schéma dessiné à la main qui prétendrait "
        "être une mesure.",
        "",
    ]
    (SORTIE / "MANIFESTE.md").write_text("\n".join(lignes), encoding="utf-8")

    print()
    print(f"  {len(_manifeste)} figure(s) produite(s), {len(manquantes)} déclarée(s) manquante(s)")
    print(f"  → {SORTIE / 'MANIFESTE.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
