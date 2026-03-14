"""
Pydantic models — përcakton strukturën e të dhënave.
Çdo request dhe response kalon nëpër këto modele.
"""
from pydantic import BaseModel, Field, validator
from typing   import Optional, Dict, Any
from datetime import datetime
from enum     import Enum


# ── Enums ──────────────────────────────────────────────────────────────────
class AlertSeverity(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


class AlertType(str, Enum):
    COST_SPIKE      = "cost_spike"
    HIGH_LATENCY    = "high_latency"
    HIGH_ERROR_RATE = "high_error_rate"
    LOW_SUCCESS     = "low_success_rate"
    ANOMALY         = "anomaly_detected"


# ── Webhook Event (vjen nga SDK) ───────────────────────────────────────────
class WebhookEvent(BaseModel):
    """
    Ky është payload-i që SDK dërgon tek ne.
    Çdo field është saktësisht si e kemi dizajnuar në SDK.
    """
    agentId:       str   = Field(..., example="email-bot-1")
    success:       bool  = Field(..., example=True)
    latency:       float = Field(..., gt=0, example=1200.0)
    cost:          float = Field(0.0,  ge=0, example=0.05)
    errorMessage:  Optional[str]  = None
    errorType:     Optional[str]  = None
    taskType:      Optional[str]  = None
    tokensInput:   Optional[int]  = None
    tokensOutput:  Optional[int]  = None
    userRating:    Optional[int]  = Field(None, ge=1, le=5)
    metadata:      Dict[str, Any] = Field(default_factory=dict)
    eventId:       str            = Field(..., example="uuid-here")
    timestamp:     str            = Field(..., example="2026-03-14T10:00:00Z")
    sdkVersion:    str            = Field("1.0.0")

    @validator("cost", pre=True, always=True)
    def auto_calculate_cost(cls, v, values):
        """
        Nëse cost është 0 por kemi tokens,
        kalkulojmë cost automatikisht.
        """
        if v == 0.0:
            tokens_in  = values.get("tokensInput",  0) or 0
            tokens_out = values.get("tokensOutput", 0) or 0
            if tokens_in > 0 or tokens_out > 0:
                return round(
                    (tokens_in  / 1_000_000 * 5.0) +
                    (tokens_out / 1_000_000 * 15.0),
                    6
                )
        return v


# ── Agent Create ───────────────────────────────────────────────────────────
class AgentCreate(BaseModel):
    name:       str            = Field(..., example="Email Bot")
    modelUsed:  Optional[str]  = Field(None, example="gpt-4o")
    tags:       list           = Field(default_factory=list)


# ── Analytics Response ─────────────────────────────────────────────────────
class AnalyticsResponse(BaseModel):
    agentId:          str
    totalTasks:       int
    successRate:      float
    avgLatencyMs:     float
    avgCostPerTask:   float
    totalCostUsd:     float
    anomalies:        list
    errorClusters:    list
    costForecast:     list
    recommendations:  list
    alerts:           list


# ── Alert Model ────────────────────────────────────────────────────────────
class AlertCreate(BaseModel):
    agentId:     str
    customerId:  str
    alertType:   AlertType
    severity:    AlertSeverity
    title:       str
    message:     str
    metricValue: Optional[float] = None
    threshold:   Optional[float] = None
