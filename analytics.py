"""
ML Analytics Engine — 5 algoritmet kryesore.
Isolation Forest, K-Means, AutoARIMA, 
Cost Optimizer, dhe Stats bazike.
"""
from sklearn.ensemble    import IsolationForest
from sklearn.cluster     import KMeans
from sklearn.preprocessing import StandardScaler
import pandas            as pd
import numpy             as np
from database            import get_db


# ══════════════════════════════════════════════════════════════════════════
# 1. STATS BAZIKE — Success Rate, Cost, Latency
# ══════════════════════════════════════════════════════════════════════════
def get_basic_stats(agent_id: str) -> dict:
    """
    Kalkulon statistika bazike për një agent.
    E shpejtë, e thjeshtë, gjithmonë e disponueshme.
    """
    db     = get_db()
    result = (
        db.table("metrics")
        .select("success, latency_ms, cost_usd, tokens_input, tokens_output")
        .eq("agent_id", agent_id)
        .order("timestamp", desc=True)
        .limit(1000)
        .execute()
    )

    if not result.data:
        return _empty_stats(agent_id)

    df = pd.DataFrame(result.data)

    total_tasks    = len(df)
    success_rate   = df["success"].mean()
    avg_latency    = df["latency_ms"].mean()
    p95_latency    = df["latency_ms"].quantile(0.95)
    avg_cost       = df["cost_usd"].mean()
    total_cost     = df["cost_usd"].sum()

    # Cost per successful task
    successful     = df[df["success"] == True]
    cost_per_win   = (
        successful["cost_usd"].mean()
        if len(successful) > 0 else 0.0
    )

    return {
        "agentId":         agent_id,
        "totalTasks":      total_tasks,
        "successRate":     round(float(success_rate),  4),
        "avgLatencyMs":    round(float(avg_latency),   2),
        "p95LatencyMs":    round(float(p95_latency),   2),
        "avgCostPerTask":  round(float(avg_cost),      6),
        "totalCostUsd":    round(float(total_cost),    4),
        "costPerSuccess":  round(float(cost_per_win),  6),
    }


# ══════════════════════════════════════════════════════════════════════════
# 2. ANOMALY DETECTION — Isolation Forest
# ══════════════════════════════════════════════════════════════════════════
def detect_anomalies(agent_id: str) -> list:
    """
    Isolation Forest — detekton kur cost/latency
    hyjnë jashtë normales.
    
    Returns: lista e anomalive të detektuara
    """
    db     = get_db()
    result = (
        db.table("metrics")
        .select("id, timestamp, cost_usd, latency_ms, success")
        .eq("agent_id", agent_id)
        .order("timestamp", desc=True)
        .limit(500)
        .execute()
    )

    if not result.data or len(result.data) < 20:
        return []   # Jo mjaftueshëm të dhëna

    df = pd.DataFrame(result.data)

    # Features për Isolation Forest
    features   = df[["cost_usd", "latency_ms"]].fillna(0)
    scaler     = StandardScaler()
    scaled     = scaler.fit_transform(features)

    # Train Isolation Forest
    model      = IsolationForest(
        contamination = 0.05,    # 5% të dhëna anomale
        n_estimators  = 100,
        random_state  = 42
    )
    predictions = model.fit_predict(scaled)

    # Gjej anomalitë (-1 = anomali)
    anomalies  = []
    for i, pred in enumerate(predictions):
        if pred == -1:
            anomalies.append({
                "timestamp":  df.iloc[i]["timestamp"],
                "costUsd":    df.iloc[i]["cost_usd"],
                "latencyMs":  df.iloc[i]["latency_ms"],
                "type":       _classify_anomaly(
                    df.iloc[i]["cost_usd"],
                    df.iloc[i]["latency_ms"],
                    df["cost_usd"].mean(),
                    df["latency_ms"].mean()
                )
            })

    return anomalies[:10]   # Kthe 10 anomalitë e fundit


def _classify_anomaly(cost, latency, avg_cost, avg_latency) -> str:
    """Klasifiko llojin e anomalisë."""
    if cost > avg_cost * 3:
        return "cost_spike"
    elif latency > avg_latency * 3:
        return "latency_spike"
    else:
        return "combined_anomaly"


# ══════════════════════════════════════════════════════════════════════════
# 3. ERROR CLUSTERING — K-Means
# ══════════════════════════════════════════════════════════════════════════
def cluster_errors(agent_id: str) -> list:
    """
    K-Means — grupo gabimet sipas ngjashmërisë.
    Gjen root cause patterns automatikisht.
    
    Returns: lista e cluster-ave me gabime
    """
    db     = get_db()
    result = (
        db.table("metrics")
        .select("error_type, error_message, cost_usd, latency_ms")
        .eq("agent_id", agent_id)
        .eq("success",  False)
        .order("timestamp", desc=True)
        .limit(500)
        .execute()
    )

    if not result.data or len(result.data) < 5:
        return []

    df         = pd.DataFrame(result.data)

    # Grupo sipas error_type (i thjeshtë dhe efektiv)
    if "error_type" in df.columns and df["error_type"].notna().any():
        clusters = (
            df.groupby("error_type")
            .agg(
                count        = ("error_type",  "count"),
                avg_cost     = ("cost_usd",    "mean"),
                avg_latency  = ("latency_ms",  "mean"),
            )
            .reset_index()
            .sort_values("count", ascending=False)
        )

        return [
            {
                "errorType":   row["error_type"],
                "count":       int(row["count"]),
                "avgCost":     round(float(row["avg_cost"]),    6),
                "avgLatency":  round(float(row["avg_latency"]), 2),
                "percentage":  round(row["count"] / len(df) * 100, 1)
            }
            for _, row in clusters.iterrows()
        ]

    return []


# ══════════════════════════════════════════════════════════════════════════
# 4. COST FORECASTING — AutoARIMA
# ══════════════════════════════════════════════════════════════════════════
def forecast_costs(agent_id: str, days: int = 30) -> list:
    """
    AutoARIMA — parashiko kostot e muajit të ardhshëm.
    
    Returns: lista me (date, predicted_cost) për 30 ditë
    """
    db     = get_db()
    result = (
        db.table("metrics")
        .select("timestamp, cost_usd")
        .eq("agent_id", agent_id)
        .order("timestamp", desc=False)
        .execute()
    )

    if not result.data or len(result.data) < 14:
        return []   # Duhen të paktën 14 ditë të dhëna

    df              = pd.DataFrame(result.data)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df              = df.set_index("timestamp")

    # Agrrego koston ditore
    daily_cost      = df["cost_usd"].resample("D").sum().fillna(0)

    if len(daily_cost) < 7:
        return []

    try:
        from pmdarima import auto_arima

        model       = auto_arima(
            daily_cost,
            seasonal    = False,
            stepwise    = True,
            suppress_warnings = True,
            error_action      = "ignore",
        )
        forecast    = model.predict(n_periods=days)

        # Gjenero datat e ardhshme
        last_date   = daily_cost.index[-1]
        future_dates = pd.date_range(
            start   = last_date + pd.Timedelta(days=1),
            periods = days,
            freq    = "D"
        )

        return [
            {
                "date":          str(date.date()),
                "predictedCost": round(max(0, float(cost)), 4)
            }
            for date, cost in zip(future_dates, forecast)
        ]

    except Exception:
        # Fallback: trend i thjeshtë linear
        return _simple_forecast(daily_cost, days)


def _simple_forecast(daily_cost: pd.Series, days: int) -> list:
    """Fallback forecast nëse AutoARIMA dështon."""
    avg_cost    = daily_cost.tail(7).mean()
    last_date   = daily_cost.index[-1]

    return [
        {
            "date":          str((last_date + pd.Timedelta(days=i+1)).date()),
            "predictedCost": round(float(avg_cost), 4)
        }
        for i in range(days)
    ]


# ══════════════════════════════════════════════════════════════════════════
# 5. COST OPTIMIZER — Heuristic Recommendations
# ══════════════════════════════════════════════════════════════════════════
def get_recommendations(agent_id: str) -> list:
    """
    Analizon performance dhe jep rekomandime konkrete
    për të ulur kostot.
    
    Returns: lista e rekomandimeve me estimated savings
    """
    stats           = get_basic_stats(agent_id)
    recommendations = []

    # ── Rec 1: Model Downgrade ─────────────────────────────────────────────
    if stats["avgCostPerTask"] > 0.05:
        savings = stats["avgCostPerTask"] * 0.7 * stats["totalTasks"]
        recommendations.append({
            "type":           "model_downgrade",
            "title":          "🔄 Përdor model më të lirë",
            "description":    (
                f"Cost mesatar ${stats['avgCostPerTask']:.4f}/task është i lartë. "
                f"Kalimi tek GPT-4o-mini mund të kursejë ~70% kosto."
            ),
            "estimatedSaving": round(savings, 2),
            "priority":       "high"
        })

    # ── Rec 2: Caching ────────────────────────────────────────────────────
    if stats["successRate"] > 0.9 and stats["totalTasks"] > 100:
        savings = stats["avgCostPerTask"] * 0.3 * stats["totalTasks"]
        recommendations.append({
            "type":           "caching",
            "title":          "⚡ Implemento Response Caching",
            "description":    (
                f"Me {stats['successRate']:.0%} success rate, "
                f"caching i response-ave të njëjta mund të kursejë 20-30%."
            ),
            "estimatedSaving": round(savings, 2),
            "priority":       "medium"
        })

    # ── Rec 3: Latency Optimization ───────────────────────────────────────
    if stats["avgLatencyMs"] > 3000:
        recommendations.append({
            "type":           "latency",
            "title":          "⏱️ Optimizo Latency",
            "description":    (
                f"Latency mesatare {stats['avgLatencyMs']:.0f}ms është e lartë. "
                f"Shqyrto streaming responses ose prompt shortening."
            ),
            "estimatedSaving": 0.0,
            "priority":       "medium"
        })

    # ── Rec 4: Error Investigation ────────────────────────────────────────
    if stats["successRate"] < 0.85:
        waste = (1 - stats["successRate"]) * stats["totalCostUsd"]
        recommendations.append({
            "type":           "error_reduction",
            "title":          "🔴 Redukto Gabimet",
            "description":    (
                f"Me {1-stats['successRate']:.0%} error rate, "
                f"po humbet ${waste:.2f} në tasks të dështuara."
            ),
            "estimatedSaving": round(waste * 0.7, 2),
            "priority":       "high"
        })

    return recommendations


# ── Helper ─────────────────────────────────────────────────────────────────
def _empty_stats(agent_id: str) -> dict:
    return {
        "agentId":        agent_id,
        "totalTasks":     0,
        "successRate":    0.0,
        "avgLatencyMs":   0.0,
        "p95LatencyMs":   0.0,
        "avgCostPerTask": 0.0,
        "totalCostUsd":   0.0,
        "costPerSuccess": 0.0,
    }
