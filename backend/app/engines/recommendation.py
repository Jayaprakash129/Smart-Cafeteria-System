"""Engine 5 - Taste-Trend Menu Recommendation.

A hybrid content + popularity + trend scorer, in the spirit of the hybrid
recommenders surveyed in Section II-B of the paper, adapted from
"what will this individual like" to "what should this cafeteria cook tomorrow".

Score for dish d at institution i on day t is a weighted blend of:

    popularity   - recent sales volume, normalised within the institution
    trend        - short-window momentum vs the longer baseline (rising dishes
                   score higher; this is the trend-analysis function)
    satisfaction - mean customer feedback rating
    profit       - contribution margin per unit, normalised
    freshness    - penalty for repetition, so the menu rotates instead of
                   serving the same eight dishes forever
    context      - weather and exam-period affinity for the target day

Weights differ by segment: colleges are trend-sensitive, corporate favours
satisfaction and margin, schools favour familiarity and cost.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import create_engine

from app.config import DATABASE_URL

SEGMENT_WEIGHTS = {
    "corporate": {"popularity": 0.26, "trend": 0.14, "satisfaction": 0.24,
                  "profit": 0.22, "freshness": 0.09, "context": 0.05},
    "college":   {"popularity": 0.24, "trend": 0.30, "satisfaction": 0.16,
                  "profit": 0.13, "freshness": 0.12, "context": 0.05},
    "school":    {"popularity": 0.34, "trend": 0.08, "satisfaction": 0.22,
                  "profit": 0.16, "freshness": 0.14, "context": 0.06},
}


def _norm(s: pd.Series) -> pd.Series:
    lo, hi = s.min(), s.max()
    if hi - lo < 1e-9:
        return pd.Series(0.5, index=s.index)
    return (s - lo) / (hi - lo)


def recommend_menu(institution_id: int, target: date, top_n: int = 12,
                   weather: dict | None = None) -> list[dict]:
    """Rank dishes for the target day, returning the top `top_n` with reasons."""
    engine = create_engine(DATABASE_URL)
    weather = weather or {}

    dishes = pd.read_sql(
        "SELECT * FROM dishes WHERE institution_id = %d AND active = 1"
        % institution_id, engine)
    if dishes.empty:
        return []
    segment = pd.read_sql(
        "SELECT segment FROM institutions WHERE id = %d" % institution_id,
        engine)["segment"].iloc[0]
    w = SEGMENT_WEIGHTS.get(segment, SEGMENT_WEIGHTS["college"])

    sales = pd.read_sql(
        "SELECT dish_id, sales_date, quantity_sold, quantity_leftover, "
        "unit_price, unit_cost FROM daily_sales WHERE institution_id = %d"
        % institution_id, engine)
    sales["sales_date"] = pd.to_datetime(sales["sales_date"])

    fb = pd.read_sql(
        "SELECT dish_id, AVG(rating) AS avg_rating, COUNT(*) AS n_ratings "
        "FROM feedback WHERE institution_id = %d GROUP BY dish_id"
        % institution_id, engine)

    latest = sales["sales_date"].max()
    short_win = sales[sales["sales_date"] > latest - pd.Timedelta(days=7)]
    long_win = sales[sales["sales_date"] > latest - pd.Timedelta(days=28)]

    short_avg = short_win.groupby("dish_id")["quantity_sold"].mean()
    long_avg = long_win.groupby("dish_id")["quantity_sold"].mean()

    # Freshness: how many of the last 7 service days did this dish appear on?
    served_recently = short_win.groupby("dish_id")["sales_date"].nunique()
    days_in_window = max(1, short_win["sales_date"].nunique())

    rows = []
    for _, d in dishes.iterrows():
        did = int(d["id"])
        pop = float(long_avg.get(did, 0.0))
        s_avg = float(short_avg.get(did, pop))
        # Momentum: short-window mean vs long-window mean, centred on 0
        trend = (s_avg - pop) / pop if pop > 0 else 0.0
        rating = float(fb.loc[fb.dish_id == did, "avg_rating"].iloc[0]) \
            if (fb.dish_id == did).any() else 3.5
        margin = float(d["base_price"] - d["unit_cost"])
        repetition = float(served_recently.get(did, 0)) / days_in_window

        # Context affinity for the target day
        ctx = 0.0
        temp = weather.get("temperature_c")
        if temp is not None:
            if d["category"] == "beverage" and temp > 32:
                ctx += 0.6
            if d["category"] == "dessert" and temp > 33:
                ctx += 0.4
            if d["category"] == "snack" and temp < 27:
                ctx += 0.3
        if weather.get("rainfall_mm", 0) > 4 and d["category"] in ("snack", "beverage"):
            ctx += 0.5
        if weather.get("is_exam_period") and d["category"] in ("snack", "beverage"):
            ctx += 0.4

        rows.append({
            "dish_id": did, "dish_name": d["name"], "category": d["category"],
            "is_veg": bool(d["is_veg"]), "unit_cost": float(d["unit_cost"]),
            "base_price": float(d["base_price"]),
            "_pop": pop, "_trend": trend, "_rating": rating,
            "_margin": margin, "_repetition": repetition, "_ctx": ctx,
        })

    df = pd.DataFrame(rows)
    df["popularity_n"] = _norm(df["_pop"])
    df["trend_n"] = _norm(df["_trend"])
    df["satisfaction_n"] = _norm(df["_rating"])
    df["profit_n"] = _norm(df["_margin"])
    df["freshness_n"] = 1.0 - _norm(df["_repetition"])
    df["context_n"] = _norm(df["_ctx"]) if df["_ctx"].max() > 0 else 0.0

    df["score"] = (
        w["popularity"] * df["popularity_n"] + w["trend"] * df["trend_n"]
        + w["satisfaction"] * df["satisfaction_n"] + w["profit"] * df["profit_n"]
        + w["freshness"] * df["freshness_n"] + w["context"] * df["context_n"]
    )
    df = df.sort_values("score", ascending=False).reset_index(drop=True)

    out = []
    for rank, r in df.head(top_n).iterrows():
        reasons = []
        if r["_trend"] > 0.08:
            reasons.append(f"trending up {100*r['_trend']:.0f}% this week")
        elif r["_trend"] < -0.08:
            reasons.append(f"cooling off {100*abs(r['_trend']):.0f}% this week")
        if r["popularity_n"] > 0.7:
            reasons.append("consistently high volume")
        if r["_rating"] >= 4.2:
            reasons.append(f"rated {r['_rating']:.1f}/5")
        if r["profit_n"] > 0.7:
            reasons.append(f"strong margin (Rs.{r['_margin']:.0f}/unit)")
        if r["freshness_n"] > 0.6:
            reasons.append("not served recently - adds variety")
        if r["_ctx"] > 0.3:
            reasons.append("suits forecast weather/campus conditions")
        if not reasons:
            reasons.append("balanced all-round score")

        out.append({
            "dish_id": int(r["dish_id"]), "dish_name": r["dish_name"],
            "category": r["category"], "is_veg": bool(r["is_veg"]),
            "unit_cost": round(float(r["unit_cost"]), 2),
            "base_price": round(float(r["base_price"]), 2),
            "score": round(float(r["score"]), 4),
            "rank": int(rank) + 1,
            "trend_pct": round(float(r["_trend"]) * 100, 1),
            "avg_rating": round(float(r["_rating"]), 2),
            "reason": "; ".join(reasons),
            "segment_weights": w,
        })
    return out


def trending_dishes(institution_id: int, top_n: int = 5) -> list[dict]:
    """Pure trend view: biggest week-over-week movers, up and down."""
    engine = create_engine(DATABASE_URL)
    sales = pd.read_sql(
        "SELECT s.dish_id, s.sales_date, s.quantity_sold, d.name AS dish_name "
        "FROM daily_sales s JOIN dishes d ON d.id = s.dish_id "
        "WHERE s.institution_id = %d" % institution_id, engine)
    sales["sales_date"] = pd.to_datetime(sales["sales_date"])
    latest = sales["sales_date"].max()

    this_wk = sales[sales["sales_date"] > latest - pd.Timedelta(days=7)]
    prev_wk = sales[(sales["sales_date"] <= latest - pd.Timedelta(days=7))
                    & (sales["sales_date"] > latest - pd.Timedelta(days=14))]
    a = this_wk.groupby(["dish_id", "dish_name"])["quantity_sold"].mean()
    b = prev_wk.groupby(["dish_id", "dish_name"])["quantity_sold"].mean()

    rows = []
    for key in a.index:
        prev = float(b.get(key, 0.0))
        curr = float(a[key])
        if prev < 1:
            continue
        rows.append({
            "dish_id": int(key[0]), "dish_name": key[1],
            "this_week_avg": round(curr, 1), "last_week_avg": round(prev, 1),
            "change_pct": round(100 * (curr - prev) / prev, 1),
        })
    rows.sort(key=lambda r: -r["change_pct"])
    return {"rising": rows[:top_n], "falling": rows[-top_n:][::-1]}


def best_seller(institution_id: int, day: date) -> dict | None:
    """Yesterday's best-selling dish - the anchor for trial-conversion offers."""
    engine = create_engine(DATABASE_URL)
    q = ("SELECT s.dish_id, d.name AS dish_name, s.quantity_sold, s.unit_price, "
         "s.unit_cost FROM daily_sales s JOIN dishes d ON d.id = s.dish_id "
         "WHERE s.institution_id = %d AND s.sales_date = '%s' "
         "ORDER BY s.quantity_sold DESC LIMIT 1" % (institution_id, day.isoformat()))
    df = pd.read_sql(q, engine)
    if df.empty:
        # Fall back to the most recent day that has data
        alt = pd.read_sql(
            "SELECT MAX(sales_date) AS d FROM daily_sales WHERE institution_id = %d"
            % institution_id, engine)["d"].iloc[0]
        if alt is None:
            return None
        return best_seller(institution_id, pd.to_datetime(alt).date())
    r = df.iloc[0]
    return {
        "dish_id": int(r["dish_id"]), "dish_name": r["dish_name"],
        "quantity_sold": int(r["quantity_sold"]),
        "unit_price": float(r["unit_price"]), "unit_cost": float(r["unit_cost"]),
        "date": day.isoformat(),
    }
