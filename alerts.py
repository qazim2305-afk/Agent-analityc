"""
Alert Engine — monitoron çdo event dhe krijon njoftime automatike.
Tabela: organizations (jo customers), agent_runs (jo metrics)
Thresholds: lexohen nga .env
"""
from __future__ import annotations
import os
from datetime  import datetime, timezone, timedelta
from typing    import Any

from database  import get_db

# ─── Thresholds nga .env ──────────────────────────────────────────────────────
COST_THRESHOLD    = float(os.getenv("ALERT_COST_THRESHOLD",    "10.0"))   # USD/run
LATENCY_THRESHOLD = float(os.getenv("ALERT_LATENCY_THRESHOLD", "5000.0")) # ms
ERROR_RATE_CRIT   = float(os.getenv("ALERT_ERROR_RATE_CRIT",   "0.30"))   # 30 %
ERROR_RATE_HIGH   = float(os.getenv("ALERT_ERROR_RATE_HIGH",   "0.15"))   # 15 %
MIN_SAMPLES       = 10   # minimumi i run-eve për error-rate alert


# ─── Helper: alert ekziston ende? ────────────────────────────────────────────
def _open_alert_exists(agent_id: str, alert_type: str) -> bool:
    db  = get_db()
    res = (
        db.table("alerts")
        .select("id")
        .eq("agent_id",   agent_id)
        .eq("alert_type", alert_type)
        .in_("status", ["open", "acknowledged"])
        .limit(1)
        .execute()
    )
    return bool(res.data)


# ─── Helper: krijo alert ──────────────────────────────────────────────────────
def _create_alert(agent_id: str, org_id: str,
                  alert_type: str, severity: str,
                  title: str, message: str) -> None:
    if _open_alert_exists(agent_id, alert_type):
        return   # mos dupliko

    get_db().table("alerts").insert({
        "agent_id":   agent_id,
        "org_id":     org_id,
        "alert_type": alert_type,
        "severity":   severity,
        "title":      title,
        "message":    message,
        "status":     "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


# ─── Kontrollo cost spike ─────────────────────────────────────────────────────
def _check_cost(agent_id: str, org_id: str, cost_usd: float | None) -> None:
    if cost_usd is None or cost_usd <= COST_THRESHOLD:
        return
    _create_alert(
        agent_id, org_id,
        alert_type="cost_spike",
        severity="high",
        title="Cost spike detected",
        message=f"Run cost ${cost_usd:.4f} exceeds threshold ${COST_THRESHOLD:.2f}.",
    )


# ─── Kontrollo latency spike ──────────────────────────────────────────────────
def _check_latency(agent_id: str, org_id: str, latency_ms: float | None) -> None:
    if latency_ms is None or latency_ms <= LATENCY_THRESHOLD:
        return
    _create_alert(
        agent_id, org_id,
        alert_type="high_latency",
        severity="medium",
        title="High latency detected",
        message=f"Run latency {latency_ms:.0f} ms exceeds threshold {LATENCY_THRESHOLD:.0f} ms.",
    )


# ─── Kontrollo error rate ─────────────────────────────────────────────────────
def _check_error_rate(agent_id: str, org_id: str) -> None:
    db  = get_db()
    since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    res = (
        db.table("agent_runs")                # ← agent_runs (jo metrics)
        .select("status")
        .eq("agent_id", agent_id)
        .gte("created_at", since)
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    )
    rows = res.data or []
    if len(rows) < MIN_SAMPLES:
        return

    errors     = sum(1 for r in rows if r.get("status") != "success")
    error_rate = errors / len(rows)

    if error_rate >= ERROR_RATE_CRIT:
        _create_alert(
            agent_id, org_id,
            alert_type="high_error_rate",
            severity="critical",
            title="Critical error rate",
            message=f"Error rate {error_rate*100:.1f}% in last hour "
                    f"(threshold {ERROR_RATE_CRIT*100:.0f}%).",
        )
    elif error_rate >= ERROR_RATE_HIGH:
        _create_alert(
            agent_id, org_id,
            alert_type="high_error_rate",
            severity="high",
            title="High error rate",
            message=f"Error rate {error_rate*100:.1f}% in last hour "
                    f"(threshold {ERROR_RATE_HIGH*100:.0f}%).",
        )


# ─── Main entry-point (thirrur nga webhooks.py) ───────────────────────────────
async def check_and_create_alerts(
    agent_id: str,
    org_id:   str,
    event:    Any,          # WebhookEvent ose dict
) -> None:
    """
    Thirret pas çdo run. Non-blocking (asyncio.create_task).
    event mund të jetë objekt Pydantic ose dict.
    """
    cost_usd   = getattr(event, "cost_usd",   None) or (event.get("cost_usd")   if isinstance(event, dict) else None)
    latency_ms = getattr(event, "latency_ms", None) or (event.get("latency_ms") if isinstance(event, dict) else None)

    _check_cost(agent_id,    org_id, cost_usd)
    _check_latency(agent_id, org_id, latency_ms)
    _check_error_rate(agent_id, org_id)
