"""
Alert Engine — kontrollon çdo event dhe gjeneron alerts.
5 lloje alertesh: cost spike, high latency, 
high error rate, low success, anomaly.
"""
from database import get_db
from models   import AlertType, AlertSeverity
from dotenv   import load_dotenv
import os

load_dotenv()

# ── Thresholds nga .env ────────────────────────────────────────────────────
COST_THRESHOLD      = float(os.getenv("ALERT_COST_THRESHOLD",      "10.0"))
LATENCY_THRESHOLD   = float(os.getenv("ALERT_LATENCY_THRESHOLD",   "5000.0"))
ERROR_RATE_THRESHOLD= float(os.getenv("ALERT_ERROR_RATE_THRESHOLD", "0.15"))


async def check_and_create_alerts(
    db, agent_id: str, customer_id: str, event
) -> None:
    """
    Kontrollo çdo event për probleme të mundshme.
    Gjenero alert nëse diçka shkon keq.
    """

    # ── Alert 1: Cost Spike ────────────────────────────────────────────────
    if event.cost > COST_THRESHOLD:
        await _create_alert(
            db          = db,
            agent_id    = agent_id,
            customer_id = customer_id,
            alert_type  = AlertType.COST_SPIKE,
            severity    = AlertSeverity.HIGH,
            title       = f"💸 Cost Spike: ${event.cost:.2f} per task",
            message     = (
                f"Agent '{event.agentId}' shpenzoi ${event.cost:.2f} "
                f"për një task — mbi limitin prej ${COST_THRESHOLD}."
            ),
            metric_value = event.cost,
            threshold    = COST_THRESHOLD
        )

    # ── Alert 2: High Latency ──────────────────────────────────────────────
    if event.latency > LATENCY_THRESHOLD:
        await _create_alert(
            db          = db,
            agent_id    = agent_id,
            customer_id = customer_id,
            alert_type  = AlertType.HIGH_LATENCY,
            severity    = AlertSeverity.MEDIUM,
            title       = f"⏱️ Latency e Lartë: {event.latency:.0f}ms",
            message     = (
                f"Agent '{event.agentId}' mori {event.latency:.0f}ms "
                f"— mbi limitin prej {LATENCY_THRESHOLD:.0f}ms."
            ),
            metric_value = event.latency,
            threshold    = LATENCY_THRESHOLD
        )

    # ── Alert 3: Error Rate (bazuar në 100 tasks të fundit) ───────────────
    await _check_error_rate(db, agent_id, customer_id, event.agentId)


async def _check_error_rate(
    db, agent_id: str, customer_id: str, agent_name: str
) -> None:
    """
    Kontrollo error rate në 100 tasks e fundit.
    Nëse > 15% → gjenero alert.
    """
    result = (
        db.table("metrics")
        .select("success")
        .eq("agent_id", agent_id)
        .order("timestamp", desc=True)
        .limit(100)
        .execute()
    )

    if not result.data or len(result.data) < 10:
        return   # Jo mjaftueshëm të dhëna

    total       = len(result.data)
    failures    = sum(1 for m in result.data if not m["success"])
    error_rate  = failures / total

    if error_rate > ERROR_RATE_THRESHOLD:
        severity = (
            AlertSeverity.CRITICAL if error_rate > 0.30
            else AlertSeverity.HIGH
        )
        db      = get_db()
        await _create_alert(
            db           = db,
            agent_id     = agent_id,
            customer_id  = customer_id,
            alert_type   = AlertType.HIGH_ERROR_RATE,
            severity     = severity,
            title        = f"🔴 Error Rate: {error_rate:.0%}",
            message      = (
                f"Agent '{agent_name}' ka {error_rate:.0%} error rate "
                f"në {total} tasks e fundit."
            ),
            metric_value = error_rate,
            threshold    = ERROR_RATE_THRESHOLD
        )


async def _create_alert(
    db, agent_id: str, customer_id: str,
    alert_type: AlertType, severity: AlertSeverity,
    title: str, message: str,
    metric_value: float = None, threshold: float = None
) -> None:
    """
    Ruaj alert në Supabase.
    Kontrollo duplikate — mos krijo të njëjtin alert dy herë.
    """
    # Kontrollo nëse ekziston alert i pazgjidhur i të njëjtit lloj
    existing = (
        db.table("alerts")
        .select("id")
        .eq("agent_id",   agent_id)
        .eq("alert_type", alert_type.value)
        .eq("resolved",   False)
        .execute()
    )

    if existing.data:
        return   # Alert ekziston tashmë

    # Krijo alert të ri
    db.table("alerts").insert({
        "agent_id":     agent_id,
        "customer_id":  customer_id,
        "alert_type":   alert_type.value,
        "severity":     severity.value,
        "title":        title,
        "message":      message,
        "metric_value": metric_value,
        "threshold":    threshold,
        "resolved":     False,
    }).execute()
