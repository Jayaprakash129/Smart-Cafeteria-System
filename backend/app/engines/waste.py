"""Engine 4 - Waste / Surplus Prediction (Random Forest).

Predicts how many units of a dish will be left over at close of service, which
drives three downstream decisions: the preparation quantity shown to the
kitchen manager, the waste markdown in the pricing engine, and the expected
surplus volume handed to the NGO allocation engine.

Regression rather than classification: the NGO allocator needs a quantity, not
a risk label. The label is derived from the quantity afterwards.
"""
from __future__ import annotations

import json
from datetime import date

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from app.config import MODEL_DIR
from app.engines.features import BASE_FEATURES, add_features, load_panel

MODEL_PATH = MODEL_DIR / "waste_rf.joblib"
META_PATH = MODEL_DIR / "waste_meta.json"

# Leftover share thresholds for the traffic-light shown to the kitchen.
RISK_BANDS = [(0.25, "high"), (0.12, "medium"), (0.0, "low")]


def risk_label(leftover: float, prepared: float) -> str:
    share = leftover / prepared if prepared else 0.0
    for threshold, label in RISK_BANDS:
        if share >= threshold:
            return label
    return "low"


def train(test_days: int = 30) -> dict:
    df = add_features(load_panel())
    cutoff = df["sales_date"].max() - pd.Timedelta(days=test_days)
    train_df = df[df["sales_date"] <= cutoff]
    test_df = df[df["sales_date"] > cutoff]

    # quantity_prepared is known at decision time (the kitchen chooses it), so
    # it is a legitimate feature rather than leakage.
    feats = BASE_FEATURES + ["quantity_prepared"]
    model = RandomForestRegressor(
        n_estimators=250, max_depth=16, min_samples_leaf=3,
        random_state=42, n_jobs=4,
    )
    model.fit(train_df[feats], train_df["quantity_leftover"])

    pred = np.clip(model.predict(test_df[feats]), 0, None)
    actual = test_df["quantity_leftover"].values
    mae = float(np.mean(np.abs(pred - actual)))
    rmse = float(np.sqrt(np.mean((pred - actual) ** 2)))
    ss_res = float(np.sum((actual - pred) ** 2))
    ss_tot = float(np.sum((actual - actual.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0

    # How often does the predicted risk band match the actual band?
    prep = test_df["quantity_prepared"].values
    pred_lbl = [risk_label(p, q) for p, q in zip(pred, prep)]
    true_lbl = [risk_label(a, q) for a, q in zip(actual, prep)]
    band_acc = float(np.mean([p == t for p, t in zip(pred_lbl, true_lbl)]))

    metrics = {
        "model": "RandomForestRegressor",
        "n_train": int(len(train_df)), "n_test": int(len(test_df)),
        "mae": round(mae, 3), "rmse": round(rmse, 3), "r2": round(r2, 4),
        "risk_band_accuracy": round(band_acc, 4),
        "trained_at": date.today().isoformat(),
        "feature_importance": dict(sorted(
            zip(feats, [float(x) for x in model.feature_importances_]),
            key=lambda kv: -kv[1])[:10]),
    }
    joblib.dump({"model": model, "features": feats}, MODEL_PATH)
    META_PATH.write_text(json.dumps(metrics, indent=2))
    return metrics


def get_metrics() -> dict:
    return json.loads(META_PATH.read_text()) if META_PATH.exists() else {}


def predict_waste(institution_id: int, forecasts: list[dict],
                  target: date) -> list[dict]:
    """Predict leftovers for each dish given its recommended prep quantity."""
    if not MODEL_PATH.exists():
        raise FileNotFoundError("Waste model not trained yet.")
    bundle = joblib.load(MODEL_PATH)
    model, feats = bundle["model"], bundle["features"]

    df = add_features(load_panel())
    df = df[df["institution_id"] == institution_id]
    if df.empty:
        return []

    rows, meta = [], []
    ts = pd.Timestamp(target)
    for f in forecasts:
        hist = df[df["dish_id"] == f["dish_id"]].sort_values("sales_date")
        if hist.empty:
            continue
        last = hist.iloc[-1]
        recent = hist.tail(28)
        prep = max(1, f.get("recommended_prep", 1))
        rows.append({
            "day_of_week": ts.dayofweek, "month": ts.month,
            "is_weekend": int(ts.dayofweek >= 5),
            "temperature_c": float(recent["temperature_c"].mean()),
            "rainfall_mm": float(recent["rainfall_mm"].mean()),
            "is_holiday": 0,
            "is_exam_period": int(last["is_exam_period"]),
            "footfall": float(recent["footfall"].mean()),
            "unit_price": float(f.get("unit_price", last["unit_price"])),
            "unit_cost": float(last["unit_cost"]),
            "price_ratio": float(f.get("unit_price", last["unit_price"])
                                 / max(last["base_price"], 1)),
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
            "quantity_prepared": prep,
        })
        meta.append({
            "dish_id": f["dish_id"], "dish_name": f["dish_name"],
            "prepared": prep, "unit_cost": float(last["unit_cost"]),
            "shelf_life_hours": int(last["shelf_life_hours"]),
            "is_veg": bool(last["is_veg"]),
        })

    if not rows:
        return []
    preds = np.clip(model.predict(pd.DataFrame(rows)[feats]), 0, None)

    out = []
    for m, p in zip(meta, preds):
        leftover = float(min(p, m["prepared"]))
        out.append({
            **m,
            "predicted_leftover": round(leftover, 1),
            "leftover_share": round(leftover / m["prepared"], 3) if m["prepared"] else 0.0,
            "risk_level": risk_label(leftover, m["prepared"]),
            "value_at_risk": round(leftover * m["unit_cost"], 2),
            "hours_to_expiry": max(1, m["shelf_life_hours"] - 2),
        })
    return sorted(out, key=lambda r: -r["value_at_risk"])
