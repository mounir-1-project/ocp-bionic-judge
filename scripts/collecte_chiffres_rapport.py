"""
Collecte des chiffres reels du systeme, pour la bibliotheque du rapport.

Tous les chiffres de `docs/bibliotheque/partie-A.md` marques [DECLARE]
viennent des commentaires du code. Ce script les RECALCULE depuis les donnees,
pour qu'ils deviennent des mesures.

Chaque bloc est independant : si l'un echoue, les autres s'executent quand meme
et l'erreur est imprimee a sa place.

Usage :
    .\\.venv\\Scripts\\python.exe scripts\\collecte_chiffres_rapport.py

La sortie est imprimee ET ecrite dans `reports/chiffres_rapport.txt`.
"""

from __future__ import annotations

import io
import sys
import traceback
from contextlib import redirect_stderr
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SORTIE: list[str] = []


def dire(texte: str = "") -> None:
    print(texte)
    SORTIE.append(texte)


def titre(t: str) -> None:
    dire()
    dire("=" * 78)
    dire(t)
    dire("=" * 78)


def bloc(nom: str, fonction) -> None:
    """Execute un bloc en isolant son echec."""
    titre(nom)
    try:
        with redirect_stderr(io.StringIO()):
            fonction()
    except Exception:
        dire(f"[ECHEC] {nom}")
        dire(traceback.format_exc(limit=3))


# ── Construction unique de la chaine ──────────────────────────────────────────

dire("Construction de la chaine (peut prendre une a deux minutes)...")
with redirect_stderr(io.StringIO()):
    from src.pipeline import E7301Pipeline

    PIPE = E7301Pipeline(use_llm=False)
dire("Chaine prete.")


def n(x, d=2):
    """Nombre a la francaise, pour coller directement dans le rapport."""
    if x is None:
        return "—"
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


# ── 1. Ingestion ──────────────────────────────────────────────────────────────

def ingestion():
    r = PIPE.ingestion.report
    dire(f"periode            : {r['t_start']}  ->  {r['t_end']}")
    dire(f"lignes brutes      : {r['n_raw_rows']}")
    dire(f"lignes retenues    : {r['n_rows']}")
    dire(f"pas nominal        : {r['step_nominal']}")
    dire(f"tags connus        : {r['n_tags']}")
    dire(f"trous temporels    : {r['n_gaps']}")
    dire(f"doublons           : {r['n_duplicates']}")
    dire(f"hors ordre         : {r['n_out_of_order']}")
    dire(f"evenements qualite : {r['n_quality_events']}")
    dire(f"tags degrades      : {r['excluded_degraded']}")
    dire()
    dire("REPARTITION DES ETATS PROCEDE :")
    total = sum(r["state_counts"].values())
    for etat, cnt in sorted(r["state_counts"].items(), key=lambda i: -i[1]):
        dire(f"  {etat:<12} {cnt:>6} h   {100*cnt/total:>5.1f} %")
    dire()
    dire("SANTE CAPTEURS (disponibilite croissante) :")
    for row in PIPE.ingestion.sensor_health.to_dict("records"):
        dire(f"  {row['alias']:<14}{row['role']:<11}"
             f"dispo {row['availability_pct']:>6.2f} %   "
             f"{row['n_bad_timestamps']:>5} h en defaut   "
             f"gel={row['n_frozen']} sat={row['n_saturated']} "
             f"hors_plage={row['n_out_of_range']} code={row['n_quality_code']}")


# ── 2. Les trois references ───────────────────────────────────────────────────

def references():
    d = PIPE.references.to_dict()
    for cle, nom in (("conductance", "CONDUCTANCE (UA)"),
                     ("regulation_effort", "EFFORT DE REGULATION (duty)"),
                     ("inlet", "TEMPERATURE D'ENTREE")):
        r = d[cle]
        dire(f"--- {nom} ---")
        dire(f"  cible          : {r['target']}  [{r['unit']}]")
        dire(f"  periode        : {r['train_period'][0]}  ->  {r['train_period'][1]}")
        dire(f"  n heures       : {r['n_train']}")
        dire(f"  R2             : {r['r2']}")
        if r.get("naive_r2") is not None:
            dire(f"  R2 SANS apprentissage : {r['naive_r2']}")
            dire(f"  APPORT REEL DU MODELE : {r['learned_gain']}   <-- ADR-001")
        dire(f"  sigma residu   : {r['residual_std']}")
        dire(f"  regresseurs    : {r['feature_names']}")
        dire(f"  coefficients   : {r['coef']}")
        if cle == "conductance":
            dire(f"  UA moyen ref   : {r['ua_reference']} kW/K")
        dire()


# ── 3. Independance des indicateurs — le chiffre d'ADR-001 ────────────────────

def independance():
    from src.features.e7301_features import independence_report

    rep = independence_report(PIPE.features)
    for cle, v in rep.items():
        if cle == "verdict":
            continue
        dire(f"{cle:<24} r = {v['corr_control_deviation']:+.4f}   "
             f"variance partagee {v['shared_variance_pct']:>5.1f} %   "
             f"independant={v['independent']}   role={v['role']}")


# ── 4. UA mois par mois — la saisonnalite ─────────────────────────────────────

def ua_mensuel():
    run = PIPE.features[PIPE.features["process_state"].eq("RUNNING")]
    m = run[["ua_kw_per_k", "ua_expected", "T_SEAWATER", "fouling_resistance",
             "ua_residual_z"]].resample("MS").mean()
    dire(f"{'mois':<10}{'UA obs':>9}{'UA att':>9}{'T mer':>8}"
         f"{'Rf':>11}{'residu z':>10}")
    for ts, row in m.iterrows():
        dire(f"{ts:%Y-%m}   {row['ua_kw_per_k']:>8.2f} {row['ua_expected']:>8.2f} "
             f"{row['T_SEAWATER']:>7.1f} {row['fouling_resistance']:>10.5f} "
             f"{row['ua_residual_z']:>9.2f}")
    dire()
    dire(f"UA min mensuel : {m['ua_kw_per_k'].min():.2f} kW/K "
         f"({m['ua_kw_per_k'].idxmin():%B %Y})")
    dire(f"UA max mensuel : {m['ua_kw_per_k'].max():.2f} kW/K "
         f"({m['ua_kw_per_k'].idxmax():%B %Y})")


# ── 5. Detection : taux de signalement et episodes ────────────────────────────

def detection():
    from src.config import CONTAMINATION

    scores = PIPE.detector.score_series(PIPE.features)
    seuil = PIPE.detector.stat.threshold_
    running = PIPE.features["process_state"].eq("RUNNING")
    n_run = int(running.sum())
    signalees = int((scores >= seuil).sum())
    taux = 100.0 * signalees / max(n_run, 1)

    dire(f"seuil de decision      : {seuil:.4f}")
    dire(f"contamination visee    : {CONTAMINATION:.1%}")
    dire(f"heures de marche       : {n_run}")
    dire(f"heures signalees       : {signalees}")
    dire(f"TAUX DE SIGNALEMENT    : {taux:.2f} %")
    dire(f"RATIO SUR LA CIBLE     : {taux / (CONTAMINATION*100):.2f} x")
    dire()
    dire("META D'ENTRAINEMENT DU DETECTEUR :")
    for k, v in PIPE.detector.stat.train_meta_.items():
        dire(f"  {k} : {v}")
    dire()
    dire("TAUX DE SIGNALEMENT MOIS PAR MOIS :")
    from src.analytics import OperationalKPI

    kpi = OperationalKPI(PIPE.features, PIPE.domain)
    mens = kpi.monthly_flag_rate(scores, seuil)
    for ts, row in mens.iterrows():
        dire(f"  {ts:%Y-%m}   {row['part_signalee_pct']:>6.1f} %   "
             f"sur {int(row['heures_marche'])} h de marche")
    dire()
    ep = PIPE.episodes()
    dire(f"EPISODES AGREGES : {len(ep)}")
    if len(ep):
        span = (PIPE.features.index.max() - PIPE.features.index.min()).days
        dire(f"  soit {len(ep) * 30.0 / span:.2f} episodes / mois")
        dire(f"  duree mediane : {ep['duration_h'].median():.0f} h")
        dire(f"  duree max     : {ep['duration_h'].max():.0f} h")
        dire()
        dire("  Les 10 plus marques :")
        cols = ["start", "end", "duration_h", "n_hours", "margin_max", "score_max"]
        dire(ep[cols].head(10).to_string(index=False))


# ── 6. Les indicateurs d'exploitation ─────────────────────────────────────────

def indicateurs():
    from src.analytics import OperationalKPI

    kpi = OperationalKPI(PIPE.features, PIPE.domain)
    figures = kpi.summary(PIPE.ingestion.sensor_health, PIPE.episodes())
    scores = PIPE.detector.score_series(PIPE.features)
    from src.config import CONTAMINATION

    figures.append(kpi.flag_rate(scores, PIPE.detector.stat.threshold_, CONTAMINATION))
    for f in figures:
        d = f.to_dict()
        dire(f"[{d['evidence_level']:<8}] {d['label']}")
        dire(f"           {d['value']} {d['unit']}")
        dire(f"           {d['note']}")
        dire()
    dire("STABILITE DE REGULATION, MOIS PAR MOIS :")
    st = kpi.control_stability()
    for ts, row in st.iterrows():
        dire(f"  {ts:%Y-%m}   ecart moyen {row['ecart_moyen_degC']:>+7.3f} degC   "
             f"hors bande 1 degC : {row['part_hors_bande_1degC']:>5.1f} %   "
             f"({int(row['heures'])} h)")


# ── 7. Couverture du risque AMDEC ─────────────────────────────────────────────

def couverture():
    c = PIPE.domain.risk_coverage()
    dire(f"criticite totale       : {c['criticite_totale']}")
    dire(f"couverte               : {c['criticite_couverte']}  "
         f"({c['part_couverte_pct']} %)  n={c['n_modes_couverts']}")
    dire(f"partielle              : {c['criticite_partielle']}  "
         f"({c['part_partielle_pct']} %)  n={c['n_modes_partiels']}")
    dire(f"non couverte           : {c['criticite_non_couverte']}  "
         f"n={c['n_modes_aveugles']}")
    dire()
    dire("MODES PARTIELLEMENT OBSERVES :")
    for m in c["modes_partiels"]:
        dire(f"  {m['code']:<34} C={m['criticite']:<5} {m['element']} / {m['mode']}")
    dire("ANGLES MORTS :")
    for m in c["modes_aveugles"]:
        dire(f"  {m['code']:<34} C={m['criticite']:<5} preventif "
             f"{m['taches_preventives']}")


# ── 8. UN EXEMPLE TRAVAILLE DE BOUT EN BOUT ───────────────────────────────────

def exemple():
    """Le manque le plus lourd de la bibliotheque : un cas concret complet."""
    instants = PIPE.notable_timestamps(6)
    if not instants:
        dire("aucun instant notable")
        return
    # On prend l'instant dont la severite est la plus elevee.
    analyses = [(ts, PIPE.analyze_at(ts, use_llm=False)) for ts in instants]
    ordre = {"CRITICAL": 3, "WARNING": 2, "INFO": 1, "NORMAL": 0}
    ts, a = max(analyses, key=lambda p: ordre.get(p[1].decision.severity, 0))

    dire(f"INSTANT ANALYSE : {ts}")
    dire(f"etat procede    : {a.detection.process_state}")
    dire()
    dire("--- MESURES DE L'INSTANT ---")
    for k, v in a.detection.measurements.items():
        dire(f"  {k:<30} {v}")
    dire()
    dire("--- CONSTATATIONS DU DETECTEUR ---")
    for f in a.detection.findings:
        dire(f"  [{f.severity:<8}] {f.code}  (source {f.source}, "
             f"mode {f.amdec_mode or '—'})")
        dire(f"      {f.message}")
        dire(f"      preuves : {f.evidence}")
    dire()
    dire("--- ATTRIBUTION DU MODELE ---")
    dire(f"  score {a.detection.anomaly_score} / seuil "
         f"{PIPE.detector.stat.threshold_:.4f}")
    for att in a.detection.attributions:
        dire(f"  {att['feature']:<24} valeur {att['value']}  "
             f"reference {att['reference']}  contribution {att['contribution']}")
    dire()
    dire("--- DIAGNOSTIC DE L'AGENT ---")
    dire(f"  severite   : {a.decision.severity}")
    dire(f"  confiance  : {a.decision.confidence}")
    dire(f"  modes      : {a.decision.amdec_modes}")
    dire(f"  dominante  : {a.decision.lead_finding}")
    dire(f"  diagnostic : {a.decision.diagnosis}")
    dire(f"  raisonnement : {a.decision.reasoning}")
    dire()
    ra = a.decision.recommended_action
    dire("--- ACTION RECOMMANDEE ---")
    dire(f"  urgence    : {ra.urgency}")
    dire(f"  fenetre    : {ra.execution_window}")
    dire(f"  arret requis : {ra.requires_shutdown}")
    dire(f"  tache      : {ra.maintenance_task_ref}   "
         f"check-list {ra.checklist_ref}")
    dire(f"  responsable: {ra.responsible}")
    dire(f"  description: {ra.description}")
    dire()
    dire("--- VERDICT DU CONTROLEUR ---")
    v = a.verdict
    dire(f"  note globale      : {v.global_score} / 10")
    dire(f"  note deterministe : {v.deterministic_score} / 10")
    dire(f"  accord            : {v.agreement}")
    dire(f"  anomalies         : {v.flagged_issues or 'aucune'}")
    dire()
    for c in v.checks:
        dire(f"  [{'OK ' if c.passed else 'NON'}] {c.id:<22} "
             f"note {c.score:>5.2f}  poids {c.weight}")
        dire(f"        {c.label}")
        dire(f"        {c.detail}")
    dire()
    dire(f"  SYNTHESE : {v.feedback}")


# ── 9. Bancs de gouvernance (lents) ───────────────────────────────────────────

def banc_judge():
    from src.governance.judge_eval import JudgeEvaluator

    res = JudgeEvaluator(PIPE).run(n_cases=12)
    s = res.summary
    dire(f"decisions saines        : {s['n_clean']}")
    dire(f"  note moyenne          : {s['clean_score_mean']} / 10")
    dire(f"  taux de validation    : {s['clean_agreement_rate']:.1%}")
    dire(f"  FAUX POSITIFS         : {s['false_positive_rate']:.1%}")
    dire(f"cas pieges              : {s['n_traps']}")
    dire(f"  note moyenne          : {s['trap_score_mean']} / 10")
    dire(f"  RAPPEL (non-regression): {s['trap_detection_rate']:.1%}")
    dire(f"  fautes non sanctionnees: {s['trap_missed']}")
    dire(f"SEPARATION saines/fautives : {s['separation']} points")
    b = s.get("blind_mutations")
    if b:
        dire()
        dire(f"MUTATIONS NON CIBLEES (generalisation) : n={b['n']}")
        dire(f"  TAUX DE DETECTION     : {b['flagged_rate']:.1%}   <-- LE CHIFFRE HONNETE")
        dire(f"  taux de penalisation  : {b['penalised_rate']:.1%}")
        dire(f"  note moyenne          : {b['score_mean']} / 10")
    dire()
    dire("DETAIL PAR TYPE DE FAUTE :")
    dire(res.traps.to_string(index=False))
    if s["verdict_warnings"]:
        dire()
        dire("ALERTES SUR LE JUDGE :")
        for w in s["verdict_warnings"]:
            dire(f"  - {w}")


def banc_encrassement():
    from src.governance.fouling_injection import FoulingInjectionBench

    r = FoulingInjectionBench(PIPE).run().to_dict()
    dire(f"scenarios               : {r['n_cases']}")
    dire(f"taux de detection brut  : {r['detection_rate']:.1%}")
    dire(f"TAUX DE DETECTION UTILE : {r['useful_detection_rate']:.1%}   "
         f"(avancement <= {r['useful_advancement_threshold']:.0%})")
    dire(f"AVANCEMENT MEDIAN       : {r['median_advancement_at_detection']}")
    dire(f"latence mediane         : {r['median_latency_h']} h")
    dire(f"plus petite perte vue   : {r['smallest_loss_detected_pct']} %")
    dire(f"faux positifs (temoin)  : {r['false_positive_rate']:.2%} "
         f"sur {r['n_control_hours']} h de marche")
    dire()
    dire("DETAIL PAR SCENARIO :")
    dire(f"{'perte UA':>9}{'duree':>7}{'detecte':>9}{'avancement':>12}"
         f"{'latence':>9}  debut")
    for c in r["cases"]:
        dire(f"{c['perte_UA_pct']:>8.1f}%{c['duration_days']:>6}j"
             f"{str(c['detected']):>9}"
             f"{str(c['advancement_at_detection']):>12}"
             f"{str(c['latency_h']):>9}  {c['start']}")


def sensibilite():
    from src.governance.sensitivity import full_report

    r = full_report(PIPE)
    c = r["contamination"]
    dire("--- CONTAMINATION ---")
    dire(f"{'valeur':>8}{'seuil':>9}{'taux signal.':>14}{'ratio':>8}{'heures':>9}")
    for row in c["grid"]:
        dire(f"{row['contamination']:>8}{row['seuil']:>9.4f}"
             f"{row['taux_signalement_pct']:>13.2f}%{row['ratio_sur_cible']:>8}"
             f"{row['heures_signalees']:>9}")
    dire(f"  ratio moyen : {c['ratio_moyen']}   dispersion : {c['ratio_dispersion']}")
    dire()
    p = r["periode_reference"]
    dire("--- PERIODE DE REFERENCE  (LE RESULTAT LE PLUS IMPORTANT) ---")
    dire(f"{'fraction':>9}{'n ref UA':>10}{'R2 UA':>8}{'sigma UA':>10}"
         f"{'min trend':>11}{'h fouling':>11}{'part %':>9}  fin")
    for row in p["grid"]:
        dire(f"{row['fraction_reference']:>9}{row['n_heures_reference_ua']:>10}"
             f"{row['r2_ua']:>8.3f}{row['sigma_ua_kw_par_k']:>10.3f}"
             f"{str(row['min_ua_trend_sigma']):>11}"
             f"{row['heures_fouling_drift']:>11}{row['part_fouling_pct']:>9.2f}"
             f"  {row['fin_reference']}")
    dire()
    dire(f"DISPERSION de la part d'encrassement : "
         f"{p['dispersion_part_fouling_pct']} points")
    dire(f"Part a la fenetre retenue (40 %)     : "
         f"{p['part_fouling_valeur_retenue_pct']} %")
    dire(f"Sensible ?                            : {p['sensible']}")


def backtest():
    r = PIPE.validation_report()
    dire(f"revendication : {r.get('predictive_claim')}")
    dire()
    dire("PORTES DE DEPLOIEMENT :")
    for g in r.get("deployment_gates", []):
        dire(f"  [{'PASSE' if g['passed'] else 'ECHEC'}] {g['gate']}")
        for k, v in g.items():
            if k not in ("gate", "passed"):
                dire(f"        {k} : {v}")
    bt = r.get("temporal_backtest", {})
    if bt:
        dire()
        dire(f"BACKTEST TEMPOREL : {len(bt.get('folds', []))} plis")
        for f in bt.get("folds", []):
            dire(f"  {f}")


def sante():
    h = PIPE.health_report()
    dire(f"source du modele        : {h['model_source']}")
    dire(f"statut de promotion     : {h['model_promotion_status']}")
    dire(f"motif de refus          : {h['model_rejection_reason']}")
    dire(f"mode de l'agent         : {h['agent_mode']}")
    dire(f"mode du controleur      : {h['judge_mode']}")


# ── Execution ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    bloc("1. INGESTION ET QUALITE DE DONNEE", ingestion)
    bloc("2. LES TROIS REFERENCES  (ADR-001 / ADR-009)", references)
    bloc("3. INDEPENDANCE DES INDICATEURS  (ADR-001)", independance)
    bloc("4. COEFFICIENT D'ECHANGE MOIS PAR MOIS  (ADR-002)", ua_mensuel)
    bloc("5. DETECTION : SIGNALEMENT ET EPISODES", detection)
    bloc("6. INDICATEURS D'EXPLOITATION", indicateurs)
    bloc("7. COUVERTURE DU RISQUE AMDEC", couverture)
    bloc("8. EXEMPLE TRAVAILLE DE BOUT EN BOUT", exemple)
    bloc("9. ETAT DU MODELE ET DE LA CHAINE", sante)
    bloc("10. BACKTEST ET PORTES DE DEPLOIEMENT", backtest)
    bloc("11. ANALYSE DE SENSIBILITE", sensibilite)
    bloc("12. BANC D'INJECTION D'ENCRASSEMENT", banc_encrassement)
    bloc("13. BANC D'EVALUATION DU CONTROLEUR", banc_judge)

    cible = Path("reports") / "chiffres_rapport.txt"
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text("\n".join(SORTIE), encoding="utf-8")
    dire()
    dire(f"Ecrit dans {cible}")
