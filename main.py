"""
Orientim Analytics Backend — FastAPI application entry-point.
Endpoints:
  POST /webhooks/events       → merr runs nga SDK
  GET  /analytics/{agent_id}  → statistika + anomali + klasterizim + forecast
  GET  /health                → health-check për Render
"""
from fastapi             import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib          import asynccontextmanager
import os

from database  import get_db
from webhooks  import router as webhook_router
from analytics import (
    get_basic_stats,
    detect_anomalies,
    cluster_errors,
    forecast_costs,
    get_cost_recommendations,
)

# ── App ───────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("✅ Orientim Analytics Backend started")
    yield
    print("👋 Orientim Analytics Backend stopped")

app = FastAPI(
    title       = "Orientim Analytics API",
    description = "Privacy-first AI agent monitoring backend",
    version     = "1.0.0",
    lifespan    = lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "https://orientim.vercel.app,http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ALLOWED_ORIGINS,
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(webhook_router, prefix="/webhooks", tags=["Webhooks"])


# ── Analytics endpoints ───────────────────────────────────────────────────────
@app.get("/analytics/{agent_id}/stats", tags=["Analytics"])
async def agent_stats(agent_id: str):
    """Statistika bazë: success rate, latency, cost."""
    return get_basic_stats(agent_id)


@app.get("/analytics/{agent_id}/anomalies", tags=["Analytics"])
async def agent_anomalies(agent_id: str):
    """Isolation Forest: cost_spike, latency_spike, combined."""
    return {"anomalies": detect_anomalies(agent_id)}


@app.get("/analytics/{agent_id}/errors", tags=["Analytics"])
async def agent_errors(agent_id: str):
    """Klasterizim gabimesh sipas error_type."""
    return {"error_clusters": cluster_errors(agent_id)}


@app.get("/analytics/{agent_id}/forecast", tags=["Analytics"])
async def agent_forecast(agent_id: str, days: int = 30):
    """Parashikim kostoje (AutoARIMA ose 7-day avg) për `days` ditë."""
    if days < 1 or days > 90:
        raise HTTPException(status_code=400, detail="days must be between 1 and 90")
    return {"forecast": forecast_costs(agent_id, days)}


@app.get("/analytics/{agent_id}/recommendations", tags=["Analytics"])
async def agent_recommendations(agent_id: str):
    """Rekomandime kostoje: model downgrade, caching, latency, error reduction."""
    return {"recommendations": get_cost_recommendations(agent_id)}


@app.get("/analytics/{agent_id}", tags=["Analytics"])
async def agent_full_analytics(agent_id: str):
    """Të gjitha analytics-et e bashkuara (stats + anomalies + errors + recommendations)."""
    return {
        "agent_id":       agent_id,
        "stats":          get_basic_stats(agent_id),
        "anomalies":      detect_anomalies(agent_id),
        "error_clusters": cluster_errors(agent_id),
        "recommendations":get_cost_recommendations(agent_id),
    }


# ── Health-check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health():
    """Render e thërret këtë endpoint për health monitoring."""
    try:
        db = get_db()
        db.table("agents").select("id").limit(1).execute()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status":   "ok" if db_status == "connected" else "degraded",
        "database": db_status,
        "version":  "1.0.0",
    }


# ── Dev runner ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
