"""Engine 1 - Demand Forecasting (XGBoost).

Predicts per-dish demand for a target day, then converts that point forecast
into a recommended preparation quantity using a newsvendor-style service level:
preparing exactly the mean forecast guarantees stockouts roughly half the time,
so the recommendation adds a margin proportional to the dish's own volatility.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import joblib
import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from app.config import MODEL_DIR
from app.engines.features import BASE_FEATURES, add_features, load_panel

MODEL_PATH = MODEL_DIR / "forecasting_xgb.joblib"
META_PATH = MODEL_DIR / "forecasting_meta.json"

# Service level by shelf life: short-life dishes are punished harder for
# leftovers, so they get a thinner safety margin.
SERVICE_MARGIN = {"short": 0.35, "normal": 0.55}


def train(test_days: int = 30) -> dict:
    """Train on all history except the final `test_days`, then evaluate."""
    df = add_features(load_panel())
    cutoff = df["sales_date"].max() - pd.Timedelta(days=test_days)
    train_df = df[df["sales_date"] <= cutoff]
    test_df = df[df["sales_date"] > cutoff]

    X_tr, y_tr = train_df[BASE_FEATURES], train_df["quantity_sold"]
    X_te, y_te = test_df[BASE_FEATURES], test_df["quantity_sold"]

    model = XGBRegressor(
        n_estimators=400, max_depth=6, learning_rate=0.06,
        subsample=0.85, colsample_bytree=0.85, min_child_weight=3,
        reg_lambda=1.2, objective="reg:squarederror",
        random_state=42, n_jobs=4,
    )
    model.fit(X_tr, y_tr)

    pred = np.clip(model.predict(X_te), 0, None)
    mae = float(np.mean(np.abs(pred - y_te)))
    rmse = float(np.sqrt(np.mean((pred - y_te) ** 2)))
    denom = np.where(y_te.values == 0, 1, y_te.values)
    mape = float(np.mean(np.abs((pred - y_te.values) / denom)) * 100)
    ss_res = float(np.sum((y_te.values - pred) ** 2))
    ss_tot = float(np.sum((y_te.values - y_te.values.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0

    # Baseline every evaluator asks about: "is this better than last week's mean?"
    naive = test_df["roll_7"].values
    naive_mae = float(np.mean(np.abs(naive - y_te.values)))

    residual_std = float(np.std(y_te.values - pred))

    # Per-dish relative forecast error, measured on the held-out window.
    # This is what safety stock must be sized from: the model already explains
    # the day-of-week and weather swings, so sizing from raw demand variance
    # would double-count them and systematically over-prepare.
    err_df = pd.DataFrame({
        "dish_id": test_df["dish_id"].values,
        "institution_id": test_df["institution_id"].values,
        "err": y_te.values - pred,
        "actual": y_te.values,
    })
    rel_err: dict[str, float] = {}
    for (inst, dish), grp in err_df.groupby(["institution_id", "dish_id"]):
        scale = max(float(grp["actual"].mean()), 1.0)
        rel_err[f"{int(inst)}:{int(dish)}"] = float(min(0.60, grp["err"].std() / scale))
    global_rel_err = float(np.median(list(rel_err.values()))) if rel_err else 0.20

    metrics = {
        "model": "XGBRegressor",
        "n_train": int(len(train_df)), "n_test": int(len(test_df)),
        "mae": round(mae, 3), "rmse": round(rmse, 3),
        "mape": round(mape, 2), "r2": round(r2, 4),
        "naive_roll7_mae": round(naive_mae, 3),
        "improvement_over_naive_pct": round(100 * (naive_mae - mae) / naive_mae, 2)
        if naive_mae else 0.0,
        "residual_std": round(residual_std, 3),
        "median_relative_forecast_error": round(global_rel_err, 4),
        "trained_at": date.today().isoformat(),
        "feature_importance": dict(sorted(
            zip(BASE_FEATURES, [float(x) for x in model.feature_importances_]),
            key=lambda kv: -kv[1])[:10]),
    }

    joblib.dump({"model": model, "residual_std": residual_std,
                 "rel_err": rel_err, "global_rel_err": global_rel_err}, MODEL_PATH)
    META_PATH.write_text(json.dumps(metrics, indent=2))
    return metrics


def _load():
    if not MODEL_PATH.exists():
        raise FileNotFoundError("Forecasting model not trained yet. Run training first.")
    return joblib.load(MODEL_PATH)


def get_metrics() -> dict:
    return json.loads(META_PATH.read_text()) if META_PATH.exists() else {}


def _feature_row_for(hist: pd.DataFrame, target: date, weather: dict) -> dict:
    """Build one prediction row from a dish's own history."""
    last = hist.iloc[-1]
    recent = hist.tail(28)
    ts = pd.Timestamp(target)
    return {
        "day_of_week": ts.dayofweek,
        "month": ts.month,
        "is_weekend": int(ts.dayofweek >= 5),
        "temperature_c": weather.get("temperature_c", float(recent["temperature_c"].mean())),
        "rainfall_mm": weather.get("rainfall_mm", float(recent["rainfall_mm"].mean())),
        "is_holiday": int(weather.get("is_holiday", False)),
        "is_exam_period": int(weather.get("is_exam_period", bool(last["is_exam_period"]))),
        "footfall": float(recent["footfall"].mean()),
        "unit_price": float(last["unit_price"]),
        "unit_cost": float(last["unit_cost"]),
        "price_ratio": float(last["unit_price"] / max(last["base_price"], 1)),
        "shelf_life_hours": int(last["shelf_life_hours"]),
        "spice_level": int(last["spice_level"]),
        "sweetness": int(last["sweetness"]),
        "is_veg": int(last["is_veg"]),
        "popularity_score": float(last["popularity_score"]),
        "segment_code": int(last["segment_code"]),
        "category_code": int(last["category_code"]),
        "lag_1": float(hist.iloc[-1]["quantity_sold"]),
        "lag_7": float(hist.iloc[-7]["quantity_sold"]) if len(hist) >= 7
        else float(recent["quantity_sold"].mean()),
        "roll_7": float(hist.tail(7)["quantity_sold"].mean()),
        "roll_28": float(recent["quantity_sold"].mean()),
        "roll_std_7": float(hist.tail(7)["quantity_sold"].std() or 0.0),
        "leftover_roll_7": float(hist.tail(7)["quantity_leftover"].mean()),
    }


def forecast_institution(institution_id: int, target: date,
                         weather: dict | None = None) -> list[dict]:
    """Forecast every active dish at an institution for `target`."""
    bundle = _load()
    model = bundle["model"]
    rel_err = bundle.get("rel_err", {})
    global_rel_err = bundle.get("global_rel_err", 0.20)
    weather = weather or {}

    df = add_features(load_panel())
    df = df[df["institution_id"] == institution_id]
    if df.empty:
        return []

    rows, meta = [], []
    for dish_id, hist in df.groupby("dish_id"):
        hist = hist.sort_values("sales_date")
        if hist.empty:
            continue
        rows.append(_feature_row_for(hist, target, weather))
        last = hist.iloc[-1]
        meta.append({
            "dish_id": int(dish_id),
            "dish_name": last["dish_name"],
            "category": last["category"],
            "unit_cost": float(last["unit_cost"]),
            "unit_price": float(last["unit_price"]),
            "base_price": float(last["base_price"]),
            "shelf_life_hours": int(last["shelf_life_hours"]),
        })

    X = pd.DataFrame(rows)[BASE_FEATURES]
    preds = np.clip(model.predict(X), 0, None)

    out = []
    for m, p, r in zip(meta, preds, rows):
        # Sigma of the FORECAST ERROR for this specific dish, not of demand.
        sigma = max(rel_err.get(f"{institution_id}:{m['dish_id']}", global_rel_err)
                    * float(p), 1.0)
        spread = 1.28 * sigma                      # ~80% prediction interval
        margin_key = "short" if m["shelf_life_hours"] <= 4 else "normal"
        prep = int(round(p + SERVICE_MARGIN[margin_key] * spread))
        out.append({
            **m,
            "predicted_demand": round(float(p), 1),
            "lower_bound": round(max(0.0, float(p - spread)), 1),
            "upper_bound": round(float(p + spread), 1),
            "recommended_prep": max(0, prep),
        })
    return sorted(out, key=lambda r: -r["predicted_demand"])


def forecast_week(institution_id: int, start: date | None = None) -> list[dict]:
    """Seven-day outlook used by the Demand Forecast View screen."""
    start = start or date.today()
    results = []
    for offset in range(7):
        target = start + timedelta(days=offset)
        day = forecast_institution(institution_id, target)
        results.append({
            "date": target.isoformat(),
            "day_name": target.strftime("%a"),
            "total_demand": round(sum(d["predicted_demand"] for d in day), 1),
            "total_prep": sum(d["recommended_prep"] for d in day),
            "dishes": day[:10],
        })
    return results
