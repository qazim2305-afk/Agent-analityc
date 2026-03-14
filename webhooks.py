"""
Webhook receiver — merr events nga SDK.
Ky është endpoint-i kryesor: POST /webhooks/events
"""
from fastapi    import APIRouter, Header, HTTPException, Depends
from database   import get_db
from models     import WebhookEvent
from alerts     import check_and_create_alerts
import hashlib

router = APIRouter()


# ── API Key Validation ─────────────────────────────────────────────────────
async def validate_api_key(
    authorization: str = Header(..., example="Bearer ck_live_xxxx")
) -> dict:
    """
    Validon API key nga header.
    Çdo request nga SDK duhet të ketë këtë header.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="❌ Format i gabuar. Përdor: Bearer ck_live_xxxx"
        )

    api_key = authorization.replace("Bearer ", "").strip()

    # Hash the key dhe kërko në Supabase
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    db       = get_db()
    result   = (
        db.table("customers")
        .select("id, company, plan")
        .eq("api_key_hash", key_hash)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=401,
            detail="❌ API key i pavlefshëm"
        )

    return result.data[0]   # {"id": "...", "company": "...", "plan": "..."}


# ── Main Webhook Endpoint ──────────────────────────────────────────────────
@router.post("/webhooks/events")
async def receive_event(
    event:    WebhookEvent,
    customer: dict = Depends(validate_api_key)
):
    """
    Merr event nga SDK dhe e ruan në Supabase.
    
    Flow:
    1. Valido API key        ✅
    2. Gjej ose krijo agent  ✅
    3. Ruaj metric           ✅
    4. Kontrollo për alerts  ✅
    5. Kthe konfirmim        ✅
    """
    db          = get_db()
    customer_id = customer["id"]

    # ── Step 1: Gjej ose Krijo Agent ──────────────────────────────────────
    agent = _get_or_create_agent(
        db          = db,
        agent_name  = event.agentId,
        customer_id = customer_id
    )
    agent_id = agent["id"]

    # ── Step 2: Ruaj Metric në Supabase ───────────────────────────────────
    metric_data = {
        "agent_id":      agent_id,
        "customer_id":   customer_id,
        "success":       event.success,
        "latency_ms":    event.latency,
        "cost_usd":      event.cost,
        "tokens_input":  event.tokensInput  or 0,
        "tokens_output": event.tokensOutput or 0,
        "error_message": event.errorMessage,
        "error_type":    event.errorType,
        "task_type":     event.taskType,
        "user_rating":   event.userRating,
        "timestamp":     event.timestamp,
    }

    db.table("metrics").insert(metric_data).execute()

    # ── Step 3: Kontrollo për Alerts (async) ──────────────────────────────
    await check_and_create_alerts(
        db          = db,
        agent_id    = agent_id,
        customer_id = customer_id,
        event       = event
    )

    return {
        "status":  "ok",
        "message": "✅ Event u regjistrua me sukses",
        "agentId": agent_id
    }


# ── Helper: Get or Create Agent ───────────────────────────────────────────
def _get_or_create_agent(db, agent_name: str, customer_id: str) -> dict:
    """
    Nëse agent ekziston → ktheje.
    Nëse nuk ekziston → krijoje automatikisht.
    """
    result = (
        db.table("agents")
        .select("id, name")
        .eq("customer_id", customer_id)
        .eq("name", agent_name)
        .execute()
    )

    if result.data:
        return result.data[0]

    # Krijo agent të ri automatikisht
    new_agent = (
        db.table("agents")
        .insert({
            "name":        agent_name,
            "customer_id": customer_id,
            "status":      "active"
        })
        .execute()
    )
    return new_agent.data[0]
