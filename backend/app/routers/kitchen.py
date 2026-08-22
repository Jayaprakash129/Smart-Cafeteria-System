"""Kitchen Manager endpoints - the most-used role in the system."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles, scoped_institution_id
from app.database import get_db
from app.engines import forecasting, recommendation
from app.engines.ngo_allocation import allocate
from app.models import (
    AgentAction, DailySales, DemandForecast, Dish, Feedback, Ingredient,
    Institution, InventoryItem, MenuRecommendation, NGOAllocation,
    PriceRecommendation, SurplusRecord, TrialOffer, User, WastePrediction,
)
from app.schemas import (
    InventoryUpdate, MenuDecision, OfferDecision, PriceDecision,
)

router = APIRouter(prefix="/api/kitchen", tags=["kitchen-manager"])
KitchenUser = require_roles("kitchen_manager", "super_admin", "coordinator")


def _inst(db: Session, user: User, requested: int | None) -> Institution:
    inst_id = scoped_institution_id(user, requested)
    inst = db.get(Institution, inst_id)
    if inst is None:
        raise HTTPException(404, "Institution not found")
    return inst


@router.get("/dashboard")
def dashboard(institution_id: int | None = None, target: date | None = None,
              user: User = Depends(KitchenUser), db: Session = Depends(get_db)):
    """Today's Dashboard - the single screen a kitchen manager lives on."""
    inst = _inst(db, user, institution_id)
    target = target or date.today()
    yesterday = target - timedelta(days=1)

    forecasts = db.query(DemandForecast).filter(
        DemandForecast.institution_id == inst.id,
        DemandForecast.forecast_date == target).all()
    prices = db.query(PriceRecommendation).filter(
        PriceRecommendation.institution_id == inst.id,
        PriceRecommendation.target_date == target).all()
    wastes = db.query(WastePrediction).filter(
        WastePrediction.institution_id == inst.id,
        WastePrediction.target_date == target).all()
    offers = db.query(TrialOffer).filter(
        TrialOffer.institution_id == inst.id,
        TrialOffer.offer_date == target).all()
    surplus = db.query(SurplusRecord).filter(
        SurplusRecord.institution_id == inst.id,
        SurplusRecord.surplus_date == target).all()

    dishes = {d.id: d for d in db.query(Dish).filter(Dish.institution_id == inst.id).all()}

    # Yesterday's realised performance
    y_rows = db.query(DailySales).filter(
        DailySales.institution_id == inst.id,
        DailySales.sales_date == yesterday).all()
    y_revenue = sum(r.revenue for r in y_rows)
    y_cost = sum(r.unit_cost * r.quantity_prepared for r in y_rows)
    y_sold = sum(r.quantity_sold for r in y_rows)
    y_left = sum(r.quantity_leftover for r in y_rows)

    low_stock = db.query(InventoryItem).filter(
        InventoryItem.institution_id == inst.id,
        InventoryItem.quantity_on_hand <= InventoryItem.reorder_level).count()
    expiring = db.query(InventoryItem).filter(
        InventoryItem.institution_id == inst.id,
        InventoryItem.expiry_date != None,  # noqa: E711
        InventoryItem.expiry_date <= target + timedelta(days=3)).count()

    alerts = []
    if low_stock:
        alerts.append({"level": "warning",
                       "message": f"{low_stock} ingredients at or below reorder level"})
    if expiring:
        alerts.append({"level": "warning",
                       "message": f"{expiring} ingredient batches expire within 3 days"})
    high_risk = [w for w in wastes if w.risk_level == "high"]
    if high_risk:
        alerts.append({"level": "danger",
                       "message": f"{len(high_risk)} dishes at high waste risk today"})
    floored = [p for p in prices if p.floor_enforced]
    if floored:
        alerts.append({"level": "info",
                       "message": f"{len(floored)} prices held at the cost-recovery floor"})
    if not forecasts:
        alerts.append({"level": "info",
                       "message": "No plan generated for today yet - run the daily pipeline"})

    return {
        "institution": {"id": inst.id, "name": inst.name, "segment": inst.segment},
        "date": target.isoformat(),
        "kpis": {
            "forecast_units": round(sum(f.predicted_demand for f in forecasts), 1),
            "recommended_prep": sum(f.recommended_prep for f in forecasts),
            "pending_price_approvals": sum(1 for p in prices if p.status == "pending"),
            "pending_offers": sum(1 for o in offers if o.status == "pending"),
            "surplus_units": sum(s.quantity for s in surplus),
            "predicted_waste_units": round(sum(w.predicted_leftover for w in wastes), 1),
            "value_at_risk": round(sum(
                w.predicted_leftover * dishes[w.dish_id].unit_cost
                for w in wastes if w.dish_id in dishes), 2),
            "yesterday_revenue": round(y_revenue, 2),
            "yesterday_profit": round(y_revenue - y_cost, 2),
            "yesterday_waste_pct": round(100 * y_left / (y_sold + y_left), 1)
            if (y_sold + y_left) else 0.0,
        },
        "alerts": alerts,
        "top_forecasts": sorted([
            {"dish_id": f.dish_id,
             "dish_name": dishes[f.dish_id].name if f.dish_id in dishes else "?",
             "predicted_demand": round(f.predicted_demand, 1),
             "recommended_prep": f.recommended_prep,
             "lower_bound": round(f.lower_bound, 1),
             "upper_bound": round(f.upper_bound, 1)}
            for f in forecasts], key=lambda r: -r["predicted_demand"])[:10],
    }


@router.get("/forecast")
def forecast(institution_id: int | None = None, days: int = Query(7, ge=1, le=14),
             user: User = Depends(KitchenUser), db: Session = Depends(get_db)):
    inst = _inst(db, user, institution_id)
    return {"institution": inst.name,
            "week": forecasting.forecast_week(inst.id)[:days],
            "model_metrics": forecasting.get_metrics()}


@router.get("/prices")
def prices(institution_id: int | None = None, target: date | None = None,
           user: User = Depends(KitchenUser), db: Session = Depends(get_db)):
    """Menu & Pricing Approval queue."""
    inst = _inst(db, user, institution_id)
    target = target or date.today()
    rows = db.query(PriceRecommendation).filter(
        PriceRecommendation.institution_id == inst.id,
        PriceRecommendation.target_date == target).all()
    dishes = {d.id: d for d in db.query(Dish).filter(Dish.institution_id == inst.id).all()}
    forecasts = {f.dish_id: f for f in db.query(DemandForecast).filter(
        DemandForecast.institution_id == inst.id,
        DemandForecast.forecast_date == target).all()}

    out = []
    for r in rows:
        d = dishes.get(r.dish_id)
        demand = forecasts[r.dish_id].predicted_demand if r.dish_id in forecasts else 0.0
        out.append({
            "id": r.id, "dish_id": r.dish_id,
            "dish_name": d.name if d else "?", "category": d.category if d else "",
            "unit_cost": r.price_floor / 1.2,
            "current_price": r.current_price,
            "recommended_price": r.recommended_price,
            "price_floor": r.price_floor,
            "floor_enforced": r.floor_enforced,
            "change_pct": round(100 * (r.recommended_price - r.current_price)
                                / r.current_price, 1) if r.current_price else 0.0,
            "predicted_demand": round(demand, 1),
            "projected_margin": round((r.recommended_price - r.price_floor / 1.2) * demand, 2),
            "segment": r.segment, "rationale": r.rationale,
            "status": r.status, "approved_price": r.approved_price,
        })
    return {"institution": inst.name, "segment": inst.segment,
            "date": target.isoformat(), "recommendations": out}


@router.post("/prices/decide")
def decide_price(decision: PriceDecision,
                 user: User = Depends(require_roles("kitchen_manager", "super_admin")),
                 db: Session = Depends(get_db)):
    r = db.get(PriceRecommendation, decision.recommendation_id)
    if r is None:
        raise HTTPException(404, "Recommendation not found")
    scoped_institution_id(user, r.institution_id)

    if decision.action == "approve":
        r.status, r.approved_price = "approved", r.recommended_price
    elif decision.action == "reject":
        r.status, r.approved_price = "rejected", r.current_price
    elif decision.action == "adjust":
        if decision.adjusted_price is None:
            raise HTTPException(400, "adjusted_price is required to adjust")
        # The floor binds the human too: a manager cannot approve a
        # below-cost price, which is the point of an enforced constraint.
        if decision.adjusted_price < r.price_floor:
            raise HTTPException(
                400,
                f"Adjusted price {decision.adjusted_price} is below the "
                f"cost-recovery floor of {r.price_floor}")
        r.status, r.approved_price = "adjusted", decision.adjusted_price
    else:
        raise HTTPException(400, "action must be approve, reject or adjust")

    # Apply the approved price to the live menu.
    dish = db.get(Dish, r.dish_id)
    if dish and r.approved_price:
        dish.base_price = r.approved_price
    db.add(AgentAction(
        institution_id=r.institution_id, run_id="manual",
        agent_name="KitchenManager", action=f"price_{decision.action}",
        detail=f"dish={r.dish_id} price={r.approved_price} by user={user.id}",
        records_affected=1))
    db.commit()
    return {"status": "ok", "recommendation_id": r.id, "new_status": r.status,
            "approved_price": r.approved_price}


@router.get("/menu")
def menu(institution_id: int | None = None, target: date | None = None,
         user: User = Depends(KitchenUser), db: Session = Depends(get_db)):
    inst = _inst(db, user, institution_id)
    target = target or date.today()
    rows = db.query(MenuRecommendation).filter(
        MenuRecommendation.institution_id == inst.id,
        MenuRecommendation.target_date == target).order_by(MenuRecommendation.rank).all()
    dishes = {d.id: d for d in db.query(Dish).filter(Dish.institution_id == inst.id).all()}
    return {
        "institution": inst.name,
        "date": target.isoformat(),
        "recommendations": [{
            "id": r.id, "dish_id": r.dish_id,
            "dish_name": dishes[r.dish_id].name if r.dish_id in dishes else "?",
            "category": dishes[r.dish_id].category if r.dish_id in dishes else "",
            "score": round(r.score, 4), "rank": r.rank,
            "reason": r.reason, "status": r.status,
        } for r in rows],
        "trends": recommendation.trending_dishes(inst.id),
    }


@router.post("/menu/decide")
def decide_menu(decision: MenuDecision,
                user: User = Depends(require_roles("kitchen_manager", "super_admin")),
                db: Session = Depends(get_db)):
    r = db.get(MenuRecommendation, decision.recommendation_id)
    if r is None:
        raise HTTPException(404, "Recommendation not found")
    scoped_institution_id(user, r.institution_id)
    if decision.action not in ("approve", "reject"):
        raise HTTPException(400, "action must be approve or reject")
    r.status = "approved" if decision.action == "approve" else "rejected"
    db.commit()
    return {"status": "ok", "new_status": r.status}


@router.get("/inventory")
def inventory(institution_id: int | None = None,
              user: User = Depends(KitchenUser), db: Session = Depends(get_db)):
    inst = _inst(db, user, institution_id)
    rows = db.query(InventoryItem).filter(InventoryItem.institution_id == inst.id).all()
    ing = {i.id: i for i in db.query(Ingredient).all()}
    today = date.today()
    out = []
    for r in rows:
        i = ing.get(r.ingredient_id)
        days_left = (r.expiry_date - today).days if r.expiry_date else None
        out.append({
            "id": r.id, "ingredient_id": r.ingredient_id,
            "name": i.name if i else "?", "unit": i.unit if i else "",
            "cost_per_unit": i.cost_per_unit if i else 0.0,
            "quantity_on_hand": r.quantity_on_hand,
            "reorder_level": r.reorder_level,
            "expiry_date": r.expiry_date.isoformat() if r.expiry_date else None,
            "days_to_expiry": days_left,
            "status": ("expired" if days_left is not None and days_left < 0
                       else "expiring" if days_left is not None and days_left <= 3
                       else "low" if r.quantity_on_hand <= r.reorder_level
                       else "ok"),
            "stock_value": round(r.quantity_on_hand * (i.cost_per_unit if i else 0), 2),
        })
    out.sort(key=lambda r: {"expired": 0, "expiring": 1, "low": 2, "ok": 3}[r["status"]])
    return {"institution": inst.name, "items": out,
            "total_stock_value": round(sum(r["stock_value"] for r in out), 2)}


@router.post("/inventory/update")
def update_inventory(payload: InventoryUpdate,
                     user: User = Depends(require_roles("kitchen_manager", "super_admin")),
                     db: Session = Depends(get_db)):
    item = db.get(InventoryItem, payload.item_id)
    if item is None:
        raise HTTPException(404, "Inventory item not found")
    scoped_institution_id(user, item.institution_id)
    item.quantity_on_hand = payload.quantity_on_hand
    if payload.expiry_date:
        item.expiry_date = payload.expiry_date
    db.commit()
    return {"status": "ok", "item_id": item.id,
            "quantity_on_hand": item.quantity_on_hand}


@router.get("/offers")
def offers(institution_id: int | None = None, target: date | None = None,
           user: User = Depends(KitchenUser), db: Session = Depends(get_db)):
    """Trial-Conversion Offers screen."""
    inst = _inst(db, user, institution_id)
    target = target or date.today()
    rows = db.query(TrialOffer).filter(
        TrialOffer.institution_id == inst.id,
        TrialOffer.offer_date == target).order_by(
        TrialOffer.conversion_probability.desc()).all()
    dishes = {d.id: d for d in db.query(Dish).filter(Dish.institution_id == inst.id).all()}
    users = {u.id: u for u in db.query(User).filter(User.role == "customer").all()}

    best = recommendation.best_seller(inst.id, target - timedelta(days=1))
    expected = sum(r.conversion_probability for r in rows)
    return {
        "institution": inst.name, "date": target.isoformat(),
        "best_seller": best,
        "summary": {
            "offers": len(rows),
            "pending": sum(1 for r in rows if r.status == "pending"),
            "approved": sum(1 for r in rows if r.status == "approved"),
            "expected_conversions": round(expected, 1),
            "expected_revenue": round(sum(
                r.offer_price * r.conversion_probability for r in rows), 2),
            "floor_enforced": any(r.floor_enforced for r in rows),
        },
        "offers": [{
            "id": r.id, "customer_id": r.customer_id,
            "customer_name": users[r.customer_id].full_name
            if r.customer_id in users else f"User {r.customer_id}",
            "dish_id": r.dish_id,
            "dish_name": dishes[r.dish_id].name if r.dish_id in dishes else "?",
            "original_price": r.original_price, "offer_price": r.offer_price,
            "discount_pct": round(r.discount_pct * 100, 1),
            "floor_enforced": r.floor_enforced,
            "conversion_probability": round(r.conversion_probability, 4),
            "status": r.status,
        } for r in rows],
    }


@router.post("/offers/decide")
def decide_offers(decision: OfferDecision,
                  user: User = Depends(require_roles("kitchen_manager", "super_admin")),
                  db: Session = Depends(get_db)):
    if decision.action not in ("approve", "reject"):
        raise HTTPException(400, "action must be approve or reject")
    rows = db.query(TrialOffer).filter(TrialOffer.id.in_(decision.offer_ids)).all()
    for r in rows:
        scoped_institution_id(user, r.institution_id)
        r.status = "approved" if decision.action == "approve" else "rejected"
    db.commit()
    return {"status": "ok", "updated": len(rows), "action": decision.action}


@router.get("/surplus")
def surplus(institution_id: int | None = None, target: date | None = None,
            user: User = Depends(KitchenUser), db: Session = Depends(get_db)):
    """Surplus & NGO Handoff screen."""
    inst = _inst(db, user, institution_id)
    target = target or date.today()
    records = db.query(SurplusRecord).filter(
        SurplusRecord.institution_id == inst.id,
        SurplusRecord.surplus_date == target).all()
    allocs = db.query(NGOAllocation).filter(
        NGOAllocation.institution_id == inst.id,
        NGOAllocation.allocation_date == target).all()
    dishes = {d.id: d for d in db.query(Dish).filter(Dish.institution_id == inst.id).all()}

    by_ngo: dict[int, dict] = {}
    for a in allocs:
        e = by_ngo.setdefault(a.ngo_id, {
            "ngo_id": a.ngo_id, "ngo_name": a.ngo.name if a.ngo else "?",
            "contact_person": a.ngo.contact_person if a.ngo else "",
            "phone": a.ngo.phone if a.ngo else "",
            "quantity": 0, "share_pct": a.share_pct,
            "meets_guarantee": a.meets_guarantee, "pickup_slot": a.pickup_slot,
            "status": a.status, "items": [], "allocation_ids": [],
        })
        e["quantity"] += a.quantity
        e["allocation_ids"].append(a.id)
        sr = db.get(SurplusRecord, a.surplus_id)
        if sr:
            e["items"].append({
                "dish_name": dishes[sr.dish_id].name if sr.dish_id in dishes else "?",
                "quantity": a.quantity, "is_veg": sr.is_veg,
                "hours_to_expiry": sr.hours_to_expiry})

    total = sum(r.quantity for r in records)
    distributed = sum(a.quantity for a in allocs)
    return {
        "institution": inst.name, "date": target.isoformat(),
        "summary": {
            "total_surplus": total, "distributed": distributed,
            "unallocated": total - distributed,
            "coverage_pct": round(100 * distributed / total, 1) if total else 0.0,
            "partners": len(by_ngo),
            "all_meet_guarantee": all(v["meets_guarantee"] for v in by_ngo.values())
            if by_ngo else False,
            "meals_value": round(sum(
                r.quantity * r.unit_cost for r in records), 2),
        },
        "surplus_items": [{
            "id": r.id, "dish_id": r.dish_id,
            "dish_name": dishes[r.dish_id].name if r.dish_id in dishes else "?",
            "quantity": r.quantity, "is_veg": r.is_veg,
            "hours_to_expiry": r.hours_to_expiry, "status": r.status,
            "value": round(r.quantity * r.unit_cost, 2),
        } for r in records],
        "allocations": sorted(by_ngo.values(), key=lambda v: -v["quantity"]),
    }


@router.post("/surplus/allocate")
def run_allocation(institution_id: int | None = None, target: date | None = None,
                   user: User = Depends(require_roles("kitchen_manager", "super_admin")),
                   db: Session = Depends(get_db)):
    """Re-run the OR-Tools allocation on demand."""
    inst = _inst(db, user, institution_id)
    target = target or date.today()
    db.query(NGOAllocation).filter(
        NGOAllocation.institution_id == inst.id,
        NGOAllocation.allocation_date == target).delete()
    db.commit()
    return allocate(db, inst.id, target, persist=True)


@router.get("/reports")
def reports(institution_id: int | None = None, days: int = Query(30, ge=7, le=365),
            user: User = Depends(KitchenUser), db: Session = Depends(get_db)):
    """Sales & Profit report for this institution."""
    inst = _inst(db, user, institution_id)
    start = date.today() - timedelta(days=days)
    rows = db.query(DailySales).filter(
        DailySales.institution_id == inst.id,
        DailySales.sales_date >= start).all()
    dishes = {d.id: d for d in db.query(Dish).filter(Dish.institution_id == inst.id).all()}

    daily: dict[str, dict] = {}
    for r in rows:
        k = r.sales_date.isoformat()
        e = daily.setdefault(k, {"date": k, "revenue": 0.0, "cost": 0.0,
                                 "sold": 0, "leftover": 0})
        e["revenue"] += r.revenue
        e["cost"] += r.unit_cost * r.quantity_prepared
        e["sold"] += r.quantity_sold
        e["leftover"] += r.quantity_leftover
    series = sorted(daily.values(), key=lambda e: e["date"])
    for e in series:
        e["profit"] = round(e["revenue"] - e["cost"], 2)
        e["revenue"] = round(e["revenue"], 2)
        e["cost"] = round(e["cost"], 2)
        e["waste_pct"] = round(100 * e["leftover"] / (e["sold"] + e["leftover"]), 1) \
            if (e["sold"] + e["leftover"]) else 0.0

    by_dish: dict[int, dict] = {}
    for r in rows:
        e = by_dish.setdefault(r.dish_id, {
            "dish_id": r.dish_id,
            "dish_name": dishes[r.dish_id].name if r.dish_id in dishes else "?",
            "sold": 0, "revenue": 0.0, "cost": 0.0, "leftover": 0})
        e["sold"] += r.quantity_sold
        e["revenue"] += r.revenue
        e["cost"] += r.unit_cost * r.quantity_prepared
        e["leftover"] += r.quantity_leftover
    for e in by_dish.values():
        e["profit"] = round(e["revenue"] - e["cost"], 2)
        e["revenue"] = round(e["revenue"], 2)
        e["cost"] = round(e["cost"], 2)

    total_rev = sum(e["revenue"] for e in series)
    total_cost = sum(e["cost"] for e in series)
    total_sold = sum(e["sold"] for e in series)
    total_left = sum(e["leftover"] for e in series)
    return {
        "institution": inst.name, "segment": inst.segment, "window_days": days,
        "totals": {
            "revenue": round(total_rev, 2), "cost": round(total_cost, 2),
            "profit": round(total_rev - total_cost, 2),
            "margin_pct": round(100 * (total_rev - total_cost) / total_rev, 1)
            if total_rev else 0.0,
            "units_sold": total_sold, "units_wasted": total_left,
            "waste_pct": round(100 * total_left / (total_sold + total_left), 1)
            if (total_sold + total_left) else 0.0,
        },
        "daily": series,
        "top_dishes": sorted(by_dish.values(), key=lambda e: -e["profit"])[:15],
    }


@router.get("/feedback")
def feedback_summary(institution_id: int | None = None,
                     user: User = Depends(KitchenUser), db: Session = Depends(get_db)):
    inst = _inst(db, user, institution_id)
    rows = db.query(
        Feedback.dish_id, func.avg(Feedback.rating), func.count(Feedback.id)
    ).filter(Feedback.institution_id == inst.id).group_by(Feedback.dish_id).all()
    dishes = {d.id: d for d in db.query(Dish).filter(Dish.institution_id == inst.id).all()}
    out = [{"dish_id": d_id,
            "dish_name": dishes[d_id].name if d_id in dishes else "?",
            "avg_rating": round(float(avg), 2), "n_ratings": int(n)}
           for d_id, avg, n in rows]
    out.sort(key=lambda r: -r["avg_rating"])
    overall = sum(r["avg_rating"] * r["n_ratings"] for r in out) / \
        max(1, sum(r["n_ratings"] for r in out))
    return {"institution": inst.name, "overall_rating": round(overall, 2),
            "best": out[:5], "worst": out[-5:][::-1], "all": out}
