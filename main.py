"""
AgentAnalytics — FastAPI Backend
Entry point i gjithë aplikacionit.
"""
from fastapi            import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from database           import get_db
from models             import AgentCreate, AnalyticsResponse
from webhooks           import router as webhook_router, validate_api_key
from analytics          import (
    get_basic_stats,
    detect_anomalies,
    cluster_errors,
    forecast_costs,
    get_recommendations,
)
import os

# ── App Initialization ─────────────────────────────────────────────────────
app = FastAPI(
    title       = "AgentAnalytics API",
    description = "Real-time observability for AI agents",
    version     = "1.0.0",
)

# ── CORS — lejon Dashboard (Vercel) të komunikojë ─────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],   # Në production: vendos Vercel URL
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ── Include Routers ────────────────────────────────────────────────────────
app.include_router(webhook_router)


# ══════════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ══════════════════════════════════════════════════════════════════════════
@app.get("/")
async def health_check():
    return {
        "status":  "✅ AgentAnalytics API is running",
        "version": "1.0.0",
        "docs":    "/docs"
    }


# ══════════════════════════════════════════════════════════════════════════
# AGENTS ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════
@app.get("/agents")
async def get_agents(customer: dict = Depends(validate_api_key)):
    """Kthe të gjithë agjentët e klientit."""
    db     = get_db()
    result = (
        db.table("agents")
        .select("*")
        .eq("customer_id", customer["id"])
        .order("created_at", desc=True)
        .execute()
    )
    return {"agents": result.data}


@app.post("/agents")
async def create_agent(
    agent:    AgentCreate,
    customer: dict = Depends(validate_api_key)
):
    """Krijo një agent të ri manualisht."""
    db     = get_db()
    result = (
        db.table("agents")
        .insert({
            "name":        agent.name,
            "customer_id": customer["id"],
            "model_used":  agent.modelUsed,
            "tags":        agent.tags,
            "status":      "active",
        })
        .execute()
    )
    return {"agent": result.data[0]}


# ══════════════════════════════════════════════════════════════════════════
# METRICS ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════
@app.get("/metrics/{agent_id}")
async def get_metrics(
    agent_id: str,
    limit:    int  = 100,
    customer: dict = Depends(validate_api_key)
):
    """Kthe metrics për një agent specifik."""
    db     = get_db()
    result = (
        db.table("metrics")
        .select("*")
        .eq("agent_id",   agent_id)
        .eq("customer_id", customer["id"])
        .order("timestamp", desc=True)
        .limit(limit)
        .execute()
    )
    return {"metrics": result.data}


# ══════════════════════════════════════════════════════════════════════════
# ANALYTICS ENDPOINTS — ML Algorithms
# ══════════════════════════════════════════════════════════════════════════
@app.get("/analytics/{agent_id}")
async def get_analytics(
    agent_id: str,
    customer: dict = Depends(validate_api_key)
):
    """
    Kthe analizën e plotë për një agent:
    stats, anomalies, clusters, forecast, recommendations.
    """
    return {
        "stats":           get_basic_stats(agent_id),
        "anomalies":       detect_anomalies(agent_id),
        "errorClusters":   cluster_errors(agent_id),
        "costForecast":    forecast_costs(agent_id),
        "recommendations": get_recommendations(agent_id),
    }


# ══════════════════════════════════════════════════════════════════════════
# ALERTS ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════
@app.get("/alerts")
async def get_alerts(
    resolved: bool = False,
    customer: dict = Depends(validate_api_key)
):
    """Kthe të gjitha alerts aktive."""
    db     = get_db()
    result = (
        db.table("alerts")
        .select("*")
        .eq("customer_id", customer["id"])
        .eq("resolved",    resolved)
        .order("created_at", desc=True)
        .execute()
    )
    return {"alerts": result.data}


@app.patch("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    customer: dict = Depends(validate_api_key)
):
    """Shëno një alert si të zgjidhur."""
    db = get_db()
    db.table("alerts").update({"resolved": True}).eq("id", alert_id).execute()
    return {"status": "✅ Alert u zgjidh"}


# ══════════════════════════════════════════════════════════════════════════
# RUN
# ══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
