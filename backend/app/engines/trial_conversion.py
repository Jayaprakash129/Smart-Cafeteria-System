"""Engine 6 - Trial-Conversion.

The mechanism the project is built around:

  1. Identify yesterday's best-selling dish at an institution.
  2. Identify customers who were *present* (they bought something) but did
     **not** buy that dish - the non-buyers. Targeting people who never visit
     is wasted spend; targeting people who already buy it is margin given away
     for nothing. The non-buyer set is the only group where a discount can
     actually change behaviour.
  3. Score each non-buyer's probability of converting, using a trained
     classifier over their own purchase history.
  4. Offer the discount only where it is likely to work, and never below the
     cost-recovery floor.

Step 2 is what requires per-customer identity, and is why the project uses
individual customer accounts rather than anonymous counter tracking.

The classifier learns from observed history: for every (customer, dish, day)
where the customer did not buy dish X on day t but did visit, did they go on to
buy X within the next 7 days? That is the empirical conversion event.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sqlalchemy import create_engine

from app.config import DATABASE_URL, MODEL_DIR, TRIAL_DISCOUNT
from app.engines.pricing import apply_discount

MODEL_PATH = MODEL_DIR / "trial_conversion_gb.joblib"
META_PATH = MODEL_DIR / "trial_conversion_meta.json"

FEATURES = [
    "visits_28d", "distinct_dishes_28d", "avg_spend", "total_spend_28d",
    "category_affinity", "dish_ever_bought", "days_since_last_visit",
    "same_category_share", "veg_match", "price_vs_avg_spend", "dish_popularity",
]


def _load_orders(engine) -> pd.DataFrame:
    q = """
        SELECT o.id AS order_id, o.customer_id, o.institution_id, o.order_date,
               oi.dish_id, oi.quantity, oi.unit_price,
               d.category, d.is_veg, d.name AS dish_name
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        JOIN dishes d ON d.id = oi.dish_id
        WHERE o.customer_id IS NOT NULL
    """
    df = pd.read_sql(q, engine)
    df["order_date"] = pd.to_datetime(df["order_date"])
    return df


def _customer_features(hist: pd.DataFrame, cust_id: int, dish_row: dict,
                       as_of: pd.Timestamp) -> dict:
    """Build the feature vector for one (customer, dish) pair as of a date."""
    past = hist[(hist.customer_id == cust_id) & (hist.order_date < as_of)]
    window = past[past.order_date >= as_of - pd.Timedelta(days=28)]

    visits = window["order_date"].nunique()
    spend = float((window["unit_price"] * window["quantity"]).sum())
    n_orders = max(1, window["order_id"].nunique())
    cat_rows = window[window.category == dish_row["category"]]

    return {
        "visits_28d": float(visits),
        "distinct_dishes_28d": float(window["dish_id"].nunique()),
        "avg_spend": spend / n_orders,
        "total_spend_28d": spend,
        "category_affinity": float(len(cat_rows)) / max(1, len(window)),
        "dish_ever_bought": float((past.dish_id == dish_row["dish_id"]).any()),
        "days_since_last_visit": float(
            (as_of - past["order_date"].max()).days) if not past.empty else 99.0,
        "same_category_share": float(cat_rows["quantity"].sum())
        / max(1.0, float(window["quantity"].sum())),
        "veg_match": 1.0 if dish_row["is_veg"] else float(
            (window.is_veg == 0).any()),
        "price_vs_avg_spend": dish_row["unit_price"] / max(1.0, spend / n_orders),
        "dish_popularity": dish_row.get("popularity", 0.5),
    }


def train(lookback_days: int = 40) -> dict:
    """Train the conversion classifier on observed non-buyer -> buyer events."""
    engine = create_engine(DATABASE_URL)
    hist = _load_orders(engine)
    if hist.empty:
        raise ValueError("No order history available to train on.")

    dishes = pd.read_sql(
        "SELECT id AS dish_id, name, category, is_veg, popularity_score "
        "FROM dishes", engine).set_index("dish_id")

    latest = hist["order_date"].max()
    start = latest - pd.Timedelta(days=lookback_days)
    # Leave a 7-day outcome window at the end so labels are observable.
    eval_days = pd.date_range(start, latest - pd.Timedelta(days=7), freq="D")

    rows, labels = [], []
    rng = np.random.default_rng(42)

    for day in eval_days:
        day_orders = hist[hist.order_date == day]
        if day_orders.empty:
            continue
        for inst_id, inst_day in day_orders.groupby("institution_id"):
            # Best seller that day at that institution
            top = inst_day.groupby("dish_id")["quantity"].sum().idxmax()
            if top not in dishes.index:
                continue
            d = dishes.loc[top]
            buyers = set(inst_day[inst_day.dish_id == top].customer_id)
            visitors = set(inst_day.customer_id)
            non_buyers = list(visitors - buyers)
            if not non_buyers:
                continue
            # Subsample to keep training tractable
            sample = rng.choice(non_buyers, size=min(12, len(non_buyers)),
                                replace=False)

            future = hist[(hist.order_date > day)
                          & (hist.order_date <= day + pd.Timedelta(days=7))
                          & (hist.dish_id == top)]
            converted = set(future.customer_id)

            price = float(inst_day[inst_day.dish_id == top]["unit_price"].mean())
            dish_row = {"dish_id": int(top), "category": d["category"],
                        "is_veg": bool(d["is_veg"]), "unit_price": price,
                        "popularity": float(d["popularity_score"])}
            for cid in sample:
                rows.append(_customer_features(hist, int(cid), dish_row, day))
                labels.append(int(cid in converted))

    if len(set(labels)) < 2:
        raise ValueError("Training data has only one class; widen the lookback.")

    X = pd.DataFrame(rows)[FEATURES]
    y = np.array(labels)
    split = int(len(X) * 0.75)
    X_tr, X_te, y_tr, y_te = X[:split], X[split:], y[:split], y[split:]

    model = GradientBoostingClassifier(
        n_estimators=220, max_depth=3, learning_rate=0.06,
        subsample=0.9, random_state=42)
    model.fit(X_tr, y_tr)

    proba = model.predict_proba(X_te)[:, 1]
    auc = float(roc_auc_score(y_te, proba)) if len(set(y_te)) > 1 else 0.5
    acc = float(np.mean((proba >= 0.5).astype(int) == y_te))
    base_rate = float(y.mean())

    # Lift @ top 20%: how much better than blanket discounting?
    k = max(1, int(len(proba) * 0.20))
    top_idx = np.argsort(-proba)[:k]
    lift = float(y_te[top_idx].mean() / base_rate) if base_rate > 0 else 1.0

    metrics = {
        "model": "GradientBoostingClassifier",
        "n_samples": int(len(X)), "n_train": int(len(X_tr)), "n_test": int(len(X_te)),
        "base_conversion_rate": round(base_rate, 4),
        "auc": round(auc, 4), "accuracy": round(acc, 4),
        "lift_at_top20pct": round(lift, 3),
        "trained_at": date.today().isoformat(),
        "feature_importance": dict(sorted(
            zip(FEATURES, [float(x) for x in model.feature_importances_]),
            key=lambda kv: -kv[1])[:8]),
    }
    joblib.dump(model, MODEL_PATH)
    META_PATH.write_text(json.dumps(metrics, indent=2))
    return metrics


def get_metrics() -> dict:
    return json.loads(META_PATH.read_text()) if META_PATH.exists() else {}


def generate_offers(institution_id: int, target: date, max_offers: int = 60,
                    min_probability: float = 0.10,
                    discount_pct: float = TRIAL_DISCOUNT) -> dict:
    """Produce targeted trial offers for the non-buyers of yesterday's best seller."""
    engine = create_engine(DATABASE_URL)
    hist = _load_orders(engine)
    hist = hist[hist.institution_id == institution_id]
    if hist.empty:
        return {"offers": [], "summary": {"reason": "no order history"}}

    yesterday = pd.Timestamp(target - timedelta(days=1))
    day_orders = hist[hist.order_date == yesterday]
    if day_orders.empty:
        yesterday = hist["order_date"].max()
        day_orders = hist[hist.order_date == yesterday]

    top_id = day_orders.groupby("dish_id")["quantity"].sum().idxmax()
    dish = pd.read_sql(
        "SELECT id, name, category, is_veg, unit_cost, base_price, popularity_score "
        "FROM dishes WHERE id = %d" % int(top_id), engine).iloc[0]

    price = float(day_orders[day_orders.dish_id == top_id]["unit_price"].mean())
    buyers = set(day_orders[day_orders.dish_id == top_id].customer_id)
    visitors = set(day_orders.customer_id)
    non_buyers = sorted(visitors - buyers)

    pricing = apply_discount(price, float(dish["unit_cost"]), discount_pct)

    dish_row = {"dish_id": int(top_id), "category": dish["category"],
                "is_veg": bool(dish["is_veg"]), "unit_price": price,
                "popularity": float(dish["popularity_score"])}

    model = joblib.load(MODEL_PATH) if MODEL_PATH.exists() else None
    names = pd.read_sql(
        "SELECT id, full_name, email FROM users WHERE role = 'customer'",
        engine).set_index("id")

    scored = []
    for cid in non_buyers:
        feats = _customer_features(hist, int(cid), dish_row, yesterday)
        if model is not None:
            prob = float(model.predict_proba(pd.DataFrame([feats])[FEATURES])[0, 1])
        else:
            # Transparent fallback if the classifier has not been trained.
            prob = min(0.9, 0.15 + 0.25 * feats["category_affinity"]
                       + 0.02 * feats["visits_28d"])
        scored.append((int(cid), prob, feats))

    scored.sort(key=lambda t: -t[1])
    selected = [s for s in scored if s[1] >= min_probability][:max_offers]

    offers = []
    for cid, prob, feats in selected:
        offers.append({
            "customer_id": cid,
            "customer_name": names.loc[cid, "full_name"] if cid in names.index else f"User {cid}",
            "dish_id": int(top_id), "dish_name": dish["name"],
            "original_price": pricing["original_price"],
            "offer_price": pricing["offer_price"],
            "discount_pct": pricing["effective_discount_pct"],
            "floor_enforced": pricing["floor_enforced"],
            "conversion_probability": round(prob, 4),
            "visits_28d": int(feats["visits_28d"]),
            "category_affinity": round(feats["category_affinity"], 3),
        })

    expected_conversions = sum(o["conversion_probability"] for o in offers)
    margin_each = pricing["offer_price"] - float(dish["unit_cost"])
    return {
        "best_seller": {
            "dish_id": int(top_id), "dish_name": dish["name"],
            "units_sold": int(day_orders[day_orders.dish_id == top_id]["quantity"].sum()),
            "date": yesterday.date().isoformat(),
        },
        "pricing": pricing,
        "offers": offers,
        "summary": {
            "visitors_yesterday": len(visitors),
            "bought_best_seller": len(buyers),
            "non_buyers": len(non_buyers),
            "offers_generated": len(offers),
            "expected_conversions": round(expected_conversions, 1),
            "expected_revenue": round(expected_conversions * pricing["offer_price"], 2),
            "expected_margin": round(expected_conversions * margin_each, 2),
            "avg_probability": round(
                float(np.mean([o["conversion_probability"] for o in offers])), 4)
            if offers else 0.0,
        },
    }
