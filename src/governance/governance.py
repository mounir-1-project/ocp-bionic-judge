"""
Métriques de gouvernance IA — surveille si le système se comporte bien.
Calcule la confiance moyenne du Judge, le taux de désaccord, etc.
sur 3 fenêtres temporelles (1h, 24h, 7j).

Author: Mounir Sanbouli
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from loguru import logger
from sqlalchemy import text

from src.config import GEMINI_MODEL  # noqa: F401 — ensures load_dotenv() called
from src.db import get_engine

# Re-export so tests can do: from src.governance.governance import compute_psi
from src.models.drift_detector import compute_psi  # noqa: F401


CONFIDENCE_THRESHOLD   = 0.70
DISAGREEMENT_THRESHOLD = 0.30
WINDOWS = {"1h": 1, "24h": 24, "7d": 168}

# Cooldown: GOVERNANCE_REPORT rows are written to audit_log at most once every
# _REPORT_COOLDOWN_MINUTES per time-window.  Without this, a browser tab polling
# every 30 s produces 120 audit_log inserts/hour — polluting the audit trail.
_REPORT_COOLDOWN_MINUTES: int = 10
_last_report_write: dict[str, datetime] = {}  # window → last write time (in-process)


def compute_metrics(window: str = "24h", db_path=None) -> dict:
    """Compute governance metrics for a given time window.

    Args:
        window: One of '1h', '24h', '7d'.
        db_path: Optional SQLAlchemy engine or path (used in tests).

    Returns:
        Dict of metric names to values, with alert flags.
    """
    hours  = WINDOWS.get(window, 24)
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    from sqlalchemy.engine import Engine
    if isinstance(db_path, Engine):
        engine = db_path
    else:
        engine = get_engine()

    with engine.connect() as conn:
        evaluations = pd.read_sql(
            text("SELECT * FROM judge_evaluations WHERE timestamp >= :cut"),
            conn, params={"cut": cutoff},
        )
        audit = pd.read_sql(
            text("SELECT * FROM audit_log WHERE timestamp >= :cut AND severity IN ('WARNING','CRITICAL')"),
            conn, params={"cut": cutoff},
        )
        decisions = pd.read_sql(
            text("SELECT * FROM ml_decisions WHERE created_at >= :cut"),
            conn, params={"cut": cutoff},
        )

    metrics: dict = {
        "window": window, "computed_at": datetime.now().isoformat(),
        "n_evaluations": len(evaluations), "n_decisions": len(decisions), "alerts": [],
    }

    if evaluations.empty:
        logger.warning(f"No evaluations in window={window}")
        metrics["status"] = "no_data"
        return metrics

    mean_confidence   = evaluations["global_score"].mean() / 10.0
    disagreement_rate = 1.0 - evaluations["agreement"].mean()
    score_drift       = (evaluations.sort_values("timestamp")["global_score"].std()
                         if len(evaluations) > 2 else 0.0)
    compliance_rate   = (evaluations["compliance_score"] >= 7.0).mean()
    critical_count    = int(len(audit[audit["severity"] == "CRITICAL"]))

    metrics.update({
        "mean_judge_confidence": round(float(mean_confidence), 4),
        "disagreement_rate":     round(float(disagreement_rate), 4),
        "judge_score_drift":     round(float(score_drift), 4),
        "ocp_compliance_rate":   round(float(compliance_rate), 4),
        "critical_unresolved":   critical_count,
    })

    per_machine = (
        evaluations.groupby("machine_id")
        .agg(
            mean_score=("global_score", "mean"),
            disagreement_rate=("agreement", lambda x: 1 - x.mean()),
            n_evals=("global_score", "count"),
        )
        .round(3)
        .to_dict(orient="index")
    )
    metrics["per_machine"] = per_machine

    # Alerts
    if mean_confidence < CONFIDENCE_THRESHOLD:
        alert = {
            "type": "LOW_CONFIDENCE", "value": mean_confidence,
            "threshold": CONFIDENCE_THRESHOLD,
            "message": f"Judge confidence {mean_confidence:.1%} below {CONFIDENCE_THRESHOLD:.0%}",
        }
        metrics["alerts"].append(alert)
        logger.warning(f"GOVERNANCE ALERT: {alert['message']}")

    if disagreement_rate > DISAGREEMENT_THRESHOLD:
        alert = {
            "type": "HIGH_DISAGREEMENT", "value": disagreement_rate,
            "threshold": DISAGREEMENT_THRESHOLD,
            "message": f"Disagreement {disagreement_rate:.1%} above {DISAGREEMENT_THRESHOLD:.0%}",
        }
        metrics["alerts"].append(alert)
        logger.warning(f"GOVERNANCE ALERT: {alert['message']}")

    if critical_count > 5:
        metrics["alerts"].append({
            "type": "CRITICAL_BACKLOG", "value": critical_count,
            "message": f"{critical_count} unresolved critical alerts",
        })

    # Save to audit_log — throttled by cooldown to avoid audit log pollution.
    # Alerts are always written (real events). GOVERNANCE_REPORT is rate-limited.
    now_dt = datetime.now()
    cooldown_expired = (
        window not in _last_report_write
        or (now_dt - _last_report_write[window]).total_seconds() > _REPORT_COOLDOWN_MINUTES * 60
    )

    with engine.begin() as conn:
        # Always write actionable alerts (these are rare, important events)
        for alert in metrics.get("alerts", []):
            conn.execute(text("""
                INSERT INTO audit_log (timestamp, event_type, action, details, severity)
                VALUES (:ts, :et, :ac, :det, :sev)
            """), {
                "ts": metrics["computed_at"], "et": "GOVERNANCE_ALERT",
                "ac": alert["type"], "det": json.dumps(alert), "sev": "WARNING",
            })
        # Write GOVERNANCE_REPORT only if cooldown has elapsed (prevents 30s polling spam)
        if cooldown_expired:
            conn.execute(text("""
                INSERT INTO audit_log (timestamp, event_type, action, details, severity)
                VALUES (:ts, :et, :ac, :det, :sev)
            """), {
                "ts": metrics["computed_at"], "et": "GOVERNANCE_REPORT",
                "ac": f"window={window} n_evals={metrics['n_evaluations']}",
                "det": json.dumps({k: v for k, v in metrics.items() if k != "per_machine"}),
                "sev": "INFO",
            })
            _last_report_write[window] = now_dt
            logger.debug(f"Governance report written for window={window}")

    logger.info(
        f"[Governance {window}] conf={mean_confidence:.1%} | "
        f"disagree={disagreement_rate:.1%} | alerts={len(metrics['alerts'])}"
    )
    return metrics


def get_all_windows() -> dict[str, dict]:
    """Compute governance metrics for all time windows.

    Returns:
        Dict mapping window label to metrics dict.
    """
    return {w: compute_metrics(window=w) for w in WINDOWS}


if __name__ == "__main__":
    for window, metrics in get_all_windows().items():
        print(f"\n{'='*40}\nWindow: {window}")
        print(f"  Confidence  : {metrics.get('mean_judge_confidence', 'N/A')}")
        print(f"  Disagreement: {metrics.get('disagreement_rate', 'N/A')}")
        print(f"  Alerts      : {len(metrics.get('alerts', []))}")
