"""
Webhook receiver — merr events nga SDK dhe i ruan në Supabase.
Tabela: organizations, api_keys, agents, agent_runs
"""
from fastapi import APIRouter, HTTPException, Header
from typing import Optional
import hashlib
import asyncio
from datetime import datetime, timezone

from database import get_db
from models import WebhookEvent, WebhookResponse
from alerts import check_and_create_alerts

router = APIRouter()


def _hash_key(raw_key: str) -> str:
    """SHA-256 hash i API key."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def _validate_api_key(raw_key: str) -> dict:
    """
    Valido API key dhe kthe org_id.
    Kërkon në tabelën api_keys kolonën key_hash.
    """
    db = get_db()
    key_hash = _hash_key(raw_key)

    result = (
        db.table("api_keys")
        .select("id, org_id, is_active, name")
        .eq("key_hash", key_hash)
        .eq("is_active", True)
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")

    # Përditëso last_used_at
    db.table("api_keys").update(
        {"last_used_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", result.data["id"]).execute()

    return result.data


async def _get_or_create_agent(org_id: str, agent_name: str) -> str:
    """Kthe agent_id ekzistues ose krijo të ri."""
    db = get_db()

    # Kërko ekzistues
    existing = (
        db.table("agents")
        .select("id")
        .eq("org_id", org_id)
        .eq("name", agent_name)
        .single()
        .execute()
    )

    if existing.data:
        return existing.data["id"]

    # Krijo të ri
    new_agent = (
        db.table("agents")
        .insert({
            "org_id": org_id,
            "name": agent_name,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        .execute()
    )

    return new_agent.data[0]["id"]


@router.post("/events", response_model=WebhookResponse)
async def receive_event(
    event: WebhookEvent,
    authorization: Optional[str] = Header(None)
):
    """
    Merr një event nga SDK dhe e ruan si agent_run.
    Headers: Authorization: Bearer ok_live_xxx
    """
    # Auth
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    raw_key = authorization.replace("Bearer ", "").strip()
    api_key_data = await _validate_api_key(raw_key)
    org_id = api_key_data["org_id"]

    # Gjej ose krijo agent
    agent_id = await _get_or_create_agent(org_id, event.agent_name)

    # Vendos timestamp
    run_time = event.timestamp or datetime.now(timezone.utc).isoformat()

    # Ruan run në agent_runs
    db = get_db()
    run_result = db.table("agent_runs").insert({
        "agent_id":      agent_id,
        "org_id":        org_id,
        "status":        event.status,           # 'success' | 'error' | 'timeout' | 'running'
        "latency_ms":    event.latency_ms,
        "input_tokens":  event.input_tokens,     # ← input_tokens (jo tokens_input)
        "output_tokens": event.output_tokens,    # ← output_tokens (jo tokens_output)
        "cost_usd":      event.cost_usd,
        "error_message": event.error_message,
        "error_type":    event.error_type,
        "trace_id":      event.trace_id,
        "session_id":    event.session_id,
        "metadata":      event.metadata,
        "started_at":    event.started_at or run_time,
        "ended_at":      event.ended_at or run_time,
        "created_at":    run_time,
    }).execute()

    run_id = run_result.data[0]["id"] if run_result.data else None

    # Check alerts async (non-blocking)
    asyncio.create_task(
        check_and_create_alerts(agent_id, org_id, event)
    )

    return WebhookResponse(
        status="ok",
        message="Event received and stored",
        agent_id=agent_id,
        run_id=run_id
    )
