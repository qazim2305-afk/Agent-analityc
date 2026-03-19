"""
Pydantic models — struktura e të dhënave që Orientim SDK dërgon.
Sinkronizuar me app/api/ingest/run/route.ts (Vercel).
"""
from pydantic import BaseModel, Field, validator
from typing   import Optional, Dict, Any, Literal
from datetime import datetime
from enum     import Enum


# ── Enums ──────────────────────────────────────────────────────────────────────
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


class RunStatus(str, Enum):
    SUCCESS = "success"
    ERROR   = "error"
    TIMEOUT = "timeout"
    RUNNING = "running"


class ErrorType(str, Enum):
    TIMEOUT        = "timeout"
    RATE_LIMIT     = "rate_limit"
    INVALID_OUTPUT = "invalid_output"
    TOOL_FAILURE   = "tool_failure"


# ── WebhookEvent — sinkronizuar me ingest/run/route.ts ─────────────────────────
class WebhookEvent(BaseModel):
    """
    Payload nga SDK → POST /webhooks/events
    Fusha identike me TrackRunPayload në ingest/run/route.ts
    """
    # Required
    agent_name:    str         = Field(...,    alias="agentName",  example="invoice-processor")
    status:        RunStatus   = Field(...,    example="success")

    # Optional metrics
    latency_ms:    Optional[float] = Field(None, alias="latencyMs",    ge=0)
    input_tokens:  Optional[int]   = Field(None, alias="inputTokens",  ge=0)
    output_tokens: Optional[int]   = Field(None, alias="outputTokens", ge=0)
    cost_usd:      Optional[float] = Field(None, alias="costUsd",      ge=0)

    # Optional error info
    error_message: Optional[str]       = Field(None, alias="errorMessage")
    error_type:    Optional[ErrorType] = Field(None, alias="errorType")

    # Optional trace/session
    trace_id:   Optional[str] = Field(None, alias="traceId")
    session_id: Optional[str] = Field(None, alias="sessionId")

    # Optional metadata & timestamps
    metadata:   Dict[str, Any] = Field(default_factory=dict)
    started_at: Optional[str]  = Field(None, alias="startedAt")
    ended_at:   Optional[str]  = Field(None, alias="endedAt")
    timestamp:  Optional[str]  = None

    class Config:
        populate_by_name = True   # pranon si 'agentName' edhe 'agent_name'

    @validator("cost_usd", pre=True, always=True)
    def auto_calculate_cost(cls, v, values):
        """Nëse cost_usd është 0 ose None por ka tokens, kalkulon automatikisht."""
        if not v:
            tokens_in  = values.get("input_tokens",  0) or 0
            tokens_out = values.get("output_tokens", 0) or 0
            if tokens_in > 0 or tokens_out > 0:
                return round(
                    (tokens_in  / 1_000_000 * 5.0) +
                    (tokens_out / 1_000_000 * 15.0),
                    6
                )
        return v


# ── Webhook Response ────────────────────────────────────────────────────────────
class WebhookResponse(BaseModel):
    status:   str
    message:  str
    agent_id: str
    run_id:   Optional[str] = None


# ── Analytics Response ──────────────────────────────────────────────────────────
class AnalyticsResponse(BaseModel):
    agent_id:        str
    stats:           Dict[str, Any]
    anomalies:       list
    error_clusters:  list
    recommendations: list


# ── Alert Model ─────────────────────────────────────────────────────────────────
class AlertCreate(BaseModel):
    agent_id:     str
    org_id:       str
    alert_type:   AlertType
    severity:     AlertSeverity
    title:        str
    message:      str
    metric_value: Optional[float] = None
    threshold:    Optional[float] = None
