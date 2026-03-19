ML Analytics Engine — statistika, anomali, klasterizim gabimesh,
parashikim kostoje dhe rekomandime AI.
Tabela: agent_runs (jo metrics)
"""
from __future__ import annotations
import numpy  as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing   import Any

from database import get_db

# ─── helpers ──────────────────────────────────────────────────────────────────

def _empty_stats() -> dict:
    return {
        "total_tasks": 0, "success_rate": 0.0,
        "avg_latency_ms": 0.0, "p95_latency_ms": 0.0,
        "avg_cost_usd": 0.0, "total_cost_usd": 0.0,
        "cost_per_success": 0.0,
    }


# ─── 1. Basic stats ───────────────────────────────────────────────────────────

def get_basic_stats(agent_id: str) -> dict:
    """Statistika bazë nga 1 000 run-et e fundit të agent_runs."""
    db  = get_db()
    res = (
        db.table("agent_runs")
        .select("status, latency_ms, cost_usd")
        .eq("agent_id", agent_id)
        .order("created_at", desc=True)
        .limit(1000)
        .execute()
    )
    rows = res.data or []
    if not rows:
        return _empty_stats()

    total        = len(rows)
    successes    = sum(1 for r in rows if r.get("status") == "success")
    latencies    = [r["latency_ms"] for r in rows if r.get("latency_ms") is not None]
    costs        = [r["cost_usd"]   for r in rows if r.get("cost_usd")   is not None]

    success_rate    = successes / total
    avg_latency     = float(np.mean(latencies))  if latencies else 0.0
    p95_latency     = float(np.percentile(latencies, 95)) if latencies else 0.0
    avg_cost        = float(np.mean(costs))  if costs else 0.0
    total_cost      = float(np.sum(costs))   if costs else 0.0
    cost_per_succ   = total_cost / successes if successes else 0.0

    return {
        "total_tasks":      total,
        "success_rate":     round(success_rate, 4),
        "avg_latency_ms":   round(avg_latency,  2),
        "p95_latency_ms":   round(p95_latency,  2),
        "avg_cost_usd":     round(avg_cost,      6),
        "total_cost_usd":   round(total_cost,    6),
        "cost_per_success": round(cost_per_succ, 6),
    }


# ─── 2. Anomaly detection ─────────────────────────────────────────────────────

def detect_anomalies(agent_id: str) -> list[dict]:
    """
    Isolation Forest mbi 500 run-et e fundit.
    Klasifikon: cost_spike, latency_spike, combined.
    """
    from sklearn.ensemble import IsolationForest

    db  = get_db()
    res = (
        db.table("agent_runs")
        .select("id, cost_usd, latency_ms, created_at")
        .eq("agent_id", agent_id)
        .order("created_at", desc=True)
        .limit(500)
        .execute()
    )
    rows = [r for r in (res.data or [])
            if r.get("cost_usd") is not None and r.get("latency_ms") is not None]

    if len(rows) < 20:
        return []

    X   = np.array([[r["cost_usd"], r["latency_ms"]] for r in rows])
    clf = IsolationForest(contamination=0.05, n_estimators=100,
                          random_state=42, n_jobs=-1)
    preds = clf.fit_predict(X)          # -1 = anomaly

    anomalies = []
    mean_cost    = float(np.mean(X[:, 0]))
    mean_latency = float(np.mean(X[:, 1]))

    for i, (pred, row) in enumerate(zip(preds, rows)):
        if pred == -1:
            cost_spike    = row["cost_usd"]    > mean_cost    * 2
            latency_spike = row["latency_ms"]  > mean_latency * 2
            kind = ("combined"      if cost_spike and latency_spike
                    else "cost_spike"    if cost_spike
                    else "latency_spike")
            anomalies.append({
                "run_id":     row["id"],
                "type":       kind,
                "cost_usd":   round(row["cost_usd"],   6),
                "latency_ms": round(row["latency_ms"],  1),
                "created_at": row["created_at"],
            })

    return anomalies[-10:]   # 10 më të fundit


# ─── 3. Error clustering ──────────────────────────────────────────────────────

def cluster_errors(agent_id: str) -> list[dict]:
    """Grupim gabimesh sipas error_type."""
    db  = get_db()
    res = (
        db.table("agent_runs")
        .select("error_type, cost_usd, latency_ms")
        .eq("agent_id", agent_id)
        .eq("status", "error")          # ← status='error' (jo success=False)
        .order("created_at", desc=True)
        .limit(1000)
        .execute()
    )
    rows = res.data or []
    if len(rows) < 5:
        return []

    df = pd.DataFrame(rows)
    df["error_type"].fillna("unknown", inplace=True)

    total = len(df)
    result = []
    for etype, grp in df.groupby("error_type"):
        result.append({
            "error_type":   etype,
            "count":        len(grp),
            "percentage":   round(len(grp) / total * 100, 1),
            "avg_cost_usd": round(grp["cost_usd"].mean(),   6) if "cost_usd"   in grp else 0,
            "avg_latency":  round(grp["latency_ms"].mean(), 1) if "latency_ms" in grp else 0,
        })

    return sorted(result, key=lambda x: x["count"], reverse=True)


# ─── 4. Cost forecasting ──────────────────────────────────────────────────────

def forecast_costs(agent_id: str, days: int = 30) -> list[dict]:
    """
    AutoARIMA mbi 30 ditët e fundit (min 14 pikë).
    Fallback: mesatare e 7 ditëve.
    """
    db  = get_db()
    since = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    res = (
        db.table("agent_runs")
        .select("cost_usd, created_at")
        .eq("agent_id", agent_id)
        .gte("created_at", since)
        .order("created_at")
        .execute()
    )
    rows = res.data or []
    if not rows:
        return []

    df = pd.DataFrame(rows)
    df["date"]     = pd.to_datetime(df["created_at"]).dt.date
    daily          = df.groupby("date")["cost_usd"].sum().reset_index()
    daily.columns  = ["date", "cost"]

    future_dates = [
        (datetime.now(timezone.utc).date() + timedelta(days=i+1)).isoformat()
        for i in range(days)
    ]

    if len(daily) >= 14:
        try:
            from pmdarima import auto_arima
            model    = auto_arima(daily["cost"].values, seasonal=False,
                                  suppress_warnings=True, error_action="ignore",
                                  max_p=3, max_q=3)
            forecast = model.predict(n_periods=days)
            return [
                {"date": d, "predicted_cost_usd": round(max(float(v), 0), 6)}
                for d, v in zip(future_dates, forecast)
            ]
        except Exception:
            pass   # fallback

    # Fallback: 7-day rolling average
    avg = float(daily["cost"].tail(7).mean()) if len(daily) >= 7 else float(daily["cost"].mean())
    return [{"date": d, "predicted_cost_usd": round(avg, 6)} for d in future_dates]


# ─── 5. Cost optimizer ────────────────────────────────────────────────────────

def get_cost_recommendations(agent_id: str) -> list[dict]:
    """Rekomandime konkrete bazuar mbi statistika."""
    stats = get_basic_stats(agent_id)
    recs  : list[dict] = []

    cost_per_task = stats.get("avg_cost_usd", 0.0)
    success_rate  = stats.get("success_rate",  0.0)
    total_tasks   = stats.get("total_tasks",   0)
    avg_latency   = stats.get("avg_latency_ms", 0.0)
    total_cost    = stats.get("total_cost_usd", 0.0)

    # 1) Model downgrade
    if cost_per_task > 0.05:
        recs.append({
            "type":            "model_downgrade",
            "priority":        "high",
            "title":           "Switch to a cheaper model",
            "description":     f"Avg cost/task is ${cost_per_task:.4f}. "
                               "A smaller model could cut costs ~70 %.",
            "estimated_savings": f"~${total_cost * 0.70:.2f}",
        })

    # 2) Caching
    if success_rate > 0.90 and total_tasks > 100:
        recs.append({
            "type":            "enable_caching",
            "priority":        "medium",
            "title":           "Enable response caching",
            "description":     f"Success rate {success_rate*100:.1f}% and "
                               f"{total_tasks} tasks suggest high repeatability. "
                               "Caching may cut calls 20-30 %.",
            "estimated_savings": f"~${total_cost * 0.25:.2f}",
        })

    # 3) Latency
    if avg_latency > 3000:
        recs.append({
            "type":            "latency_optimization",
            "priority":        "medium",
            "title":           "Reduce agent latency",
            "description":     f"Avg latency {avg_latency:.0f} ms exceeds 3 s. "
                               "Consider streaming or prompt compression.",
            "estimated_savings": None,
        })

    # 4) Error reduction
    if success_rate < 0.85:
        wasted = total_cost * (1 - success_rate)
        recs.append({
            "type":            "error_reduction",
            "priority":        "high",
            "title":           "Reduce error rate",
            "description":     f"Success rate {success_rate*100:.1f}% wastes "
                               f"~${wasted:.2f}. Fixing top errors could save ~70 %.",
            "estimated_savings": f"~${wasted * 0.70:.2f}",
        })

    return recs
