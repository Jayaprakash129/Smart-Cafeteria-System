"""Super Admin and Institution Coordinator endpoints."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.agents.graph import run_daily_pipeline
from app.auth import hash_password, require_roles, scoped_institution_id
from app.config import NGO_MIN_GUARANTEE, PRICE_FLOOR_MARGIN, SEGMENT_PRICING, TRIAL_DISCOUNT
from app.database import get_db
from app.engines import forecasting, trial_conversion, waste
from app.engines.ngo_allocation import fairness_report
from app.models import (
    AgentAction, DailySales, Dish, Institution, NGO, NGOAllocation,
    PriceRecommendation, SurplusRecord, TrialOffer, User,
)
from app.schemas import InstitutionCreate, NGOProfileUpdate, PipelineRequest, UserCreate

router = APIRouter(prefix="/api/admin", tags=["super-admin"])
AdminUser = require_roles("super_admin")
AnyStaff = require_roles("super_admin", "kitchen_manager", "coordinator")


@router.get("/dashboard")
def global_dashboard(days: int = Query(30, ge=7, le=365),
                     user: User = Depends(AdminUser), db: Session = Depends(get_db)):
    """Cross-institution overview -- super-admin only.

    This aggregates every institution's revenue in one response; a kitchen
    manager or coordinator from institution A must not be able to read
    institution B's numbers through it.
    """
    start = date.today() - timedelta(days=days)
    institutions = db.query(Institution).filter(Institution.active == True).all()  # noqa: E712

    per_inst = []
    tot_rev = tot_cost = tot_sold = tot_left = 0.0
    for inst in institutions:
        rows = db.query(DailySales).filter(
            DailySales.institution_id == inst.id,
            DailySales.sales_date >= start).all()
        rev = sum(r.revenue for r in rows)
        cost = sum(r.unit_cost * r.quantity_prepared for r in rows)
        sold = sum(r.quantity_sold for r in rows)
        left = sum(r.quantity_leftover for r in rows)
        tot_rev += rev
        tot_cost += cost
        tot_sold += sold
        tot_left += left
        per_inst.append({
            "id": inst.id, "name": inst.name, "segment": inst.segment,
            "headcount": inst.headcount,
            "revenue": round(rev, 2), "profit": round(rev - cost, 2),
            "margin_pct": round(100 * (rev - cost) / rev, 1) if rev else 0.0,
            "units_sold": sold,
            "waste_pct": round(100 * left / (sold + left), 1) if (sold + left) else 0.0,
        })

    allocs = db.query(NGOAllocation).filter(NGOAllocation.allocation_date >= start).all()
    meals_donated = sum(a.quantity for a in allocs)

    return {
        "window_days": days,
        "totals": {
            "institutions": len(institutions),
            "revenue": round(tot_rev, 2),
            "profit": round(tot_rev - tot_cost, 2),
            "margin_pct": round(100 * (tot_rev - tot_cost) / tot_rev, 1) if tot_rev else 0.0,
            "units_sold": tot_sold,
            "waste_pct": round(100 * tot_left / (tot_sold + tot_left), 1)
            if (tot_sold + tot_left) else 0.0,
            "meals_donated": meals_donated,
            "ngo_partners": db.query(NGO).filter(NGO.active == True).count(),  # noqa: E712
            "customers": db.query(User).filter(User.role == "customer").count(),
        },
        "institutions": per_inst,
        "ngo_fairness": fairness_report(db, days),
    }


@router.get("/institutions")
def list_institutions(user: User = Depends(AdminUser), db: Session = Depends(get_db)):
    """Every client institution -- super-admin only (names, headcounts and
    customer/staff counts for sites the caller may not belong to)."""
    rows = db.query(Institution).all()
    return [{
        "id": i.id, "name": i.name, "segment": i.segment, "city": i.city,
        "headcount": i.headcount, "active": i.active,
        "opening_time": i.opening_time, "closing_time": i.closing_time,
        "dishes": db.query(Dish).filter(Dish.institution_id == i.id).count(),
        "staff": db.query(User).filter(User.institution_id == i.id,
                                       User.role != "customer").count(),
        "customers": db.query(User).filter(User.institution_id == i.id,
                                           User.role == "customer").count(),
    } for i in rows]


@router.post("/institutions")
def create_institution(payload: InstitutionCreate,
                       user: User = Depends(AdminUser), db: Session = Depends(get_db)):
    if payload.segment not in SEGMENT_PRICING:
        raise HTTPException(400, f"segment must be one of {list(SEGMENT_PRICING)}")
    if db.query(Institution).filter(Institution.name == payload.name).first():
        raise HTTPException(409, "An institution with that name already exists")
    inst = Institution(**payload.model_dump())
    db.add(inst)
    db.commit()
    return {"status": "ok", "id": inst.id, "name": inst.name}


@router.patch("/institutions/{institution_id}/toggle")
def toggle_institution(institution_id: int, user: User = Depends(AdminUser),
                       db: Session = Depends(get_db)):
    inst = db.get(Institution, institution_id)
    if inst is None:
        raise HTTPException(404, "Institution not found")
    inst.active = not inst.active
    db.commit()
    return {"status": "ok", "id": inst.id, "active": inst.active}


@router.get("/users")
def list_users(role: str | None = None, institution_id: int | None = None,
               limit: int = Query(100, le=500),
               user: User = Depends(AdminUser), db: Session = Depends(get_db)):
    q = db.query(User)
    if role:
        q = q.filter(User.role == role)
    if institution_id:
        q = q.filter(User.institution_id == institution_id)
    rows = q.limit(limit).all()
    insts = {i.id: i.name for i in db.query(Institution).all()}
    return [{"id": u.id, "email": u.email, "full_name": u.full_name,
             "role": u.role, "active": u.active,
             "institution": insts.get(u.institution_id)} for u in rows]


@router.post("/users")
def create_user(payload: UserCreate, user: User = Depends(AdminUser),
                db: Session = Depends(get_db)):
    # Compare case-insensitively against the same normalised form that gets
    # stored below -- otherwise "Admin@x.com" and "admin@x.com" both pass
    # this check as "distinct" and then collide on the column's actual
    # unique constraint, surfacing as an unhandled 500 instead of a 409.
    email_norm = payload.email.lower().strip()
    if db.query(User).filter(User.email == email_norm).first():
        raise HTTPException(409, "Email already registered")
    u = User(email=email_norm, full_name=payload.full_name,
             hashed_password=hash_password(payload.password), role=payload.role,
             institution_id=payload.institution_id, ngo_id=payload.ngo_id)
    db.add(u)
    db.commit()
    return {"status": "ok", "id": u.id, "email": u.email, "role": u.role}


@router.get("/ngos")
def list_ngos(user: User = Depends(AdminUser), db: Session = Depends(get_db)):
    """NGO partner directory -- super-admin only (includes phone numbers and
    contact names that a kitchen manager or coordinator has no need to see)."""
    start = date.today() - timedelta(days=30)
    rows = db.query(NGO).all()
    out = []
    for n in rows:
        allocs = db.query(NGOAllocation).filter(
            NGOAllocation.ngo_id == n.id,
            NGOAllocation.allocation_date >= start).all()
        collected = sum(1 for a in allocs if a.status == "collected")
        out.append({
            "id": n.id, "name": n.name, "contact_person": n.contact_person,
            "phone": n.phone, "city": n.city,
            "daily_need_meals": n.daily_need_meals,
            "beneficiaries": n.beneficiaries,
            "reliability_score": n.reliability_score,
            "accepts_veg_only": n.accepts_veg_only,
            "verified": n.verified, "active": n.active,
            "meals_30d": sum(a.quantity for a in allocs),
            "pickups_30d": len(allocs),
            "collection_rate": round(collected / len(allocs), 2) if allocs else None,
        })
    return sorted(out, key=lambda r: -r["meals_30d"])


@router.patch("/ngos/{ngo_id}")
def update_ngo(ngo_id: int, payload: NGOProfileUpdate,
               user: User = Depends(AdminUser), db: Session = Depends(get_db)):
    n = db.get(NGO, ngo_id)
    if n is None:
        raise HTTPException(404, "NGO not found")
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(n, k, v)
    db.commit()
    return {"status": "ok", "id": n.id}


@router.get("/rules")
def global_rules(user: User = Depends(AnyStaff)):
    """The platform-wide constraints every other role operates inside."""
    return {
        "price_floor_margin": PRICE_FLOOR_MARGIN,
        "price_floor_formula": "unit_cost * (1 + 0.20)",
        "ngo_min_guarantee": NGO_MIN_GUARANTEE,
        "trial_discount": TRIAL_DISCOUNT,
        "segment_pricing": SEGMENT_PRICING,
        "notes": [
            "The cost-recovery floor is applied last and unconditionally: no "
            "discount, elasticity estimate or waste markdown can breach it.",
            "The NGO guarantee is capped by each partner's stated capacity, so "
            "a high-surplus day cannot disqualify smaller partners.",
        ],
    }


@router.get("/engines")
def engine_status(user: User = Depends(AnyStaff)):
    """Model & Engine Monitoring page."""
    from app.agents.llm import is_available
    return {
        "engines": [
            {"name": "Demand Forecasting", "type": "XGBoost Regressor",
             "status": "trained" if forecasting.get_metrics() else "untrained",
             "metrics": forecasting.get_metrics()},
            {"name": "Waste / Surplus Prediction", "type": "Random Forest Regressor",
             "status": "trained" if waste.get_metrics() else "untrained",
             "metrics": waste.get_metrics()},
            {"name": "Trial Conversion", "type": "Gradient Boosting Classifier",
             "status": "trained" if trial_conversion.get_metrics() else "untrained",
             "metrics": trial_conversion.get_metrics()},
            {"name": "Dynamic Segment Pricing", "type": "Constrained optimisation",
             "status": "rule-based", "metrics": {
                 "basis": "constant-elasticity profit maximisation",
                 "hard_constraint": "cost + 20% floor"}},
            {"name": "Taste-Trend Menu Recommendation", "type": "Hybrid scorer",
             "status": "rule-based", "metrics": {
                 "signals": "popularity, trend, satisfaction, margin, freshness, context"}},
            {"name": "NGO Allocation", "type": "OR-Tools CP-SAT",
             "status": "operational", "metrics": {
                 "constraints": "conservation, dietary, capacity, 20% guarantee",
                 "objective": "weighted need satisfaction with max-min fairness"}},
        ],
        "llm_narration": {"ollama_available": is_available(),
                          "note": "LLM narrates decisions only; it never makes them"},
    }


@router.post("/pipeline/run")
def run_pipeline(payload: PipelineRequest,
                 user: User = Depends(require_roles("super_admin", "kitchen_manager")),
                 db: Session = Depends(get_db)):
    """Trigger the agent pipeline for one institution or all of them."""
    target = payload.target_date or date.today()
    if payload.institution_id:
        ids = [payload.institution_id]
    elif user.role == "super_admin":
        ids = [i.id for i in db.query(Institution).filter(
            Institution.active == True).all()]  # noqa: E712
    else:
        ids = [user.institution_id]

    runs = []
    for iid in ids:
        if user.role != "super_admin" and iid != user.institution_id:
            continue
        runs.append(run_daily_pipeline(db, iid, target))
    return {"runs_completed": len(runs), "target_date": target.isoformat(),
            "runs": runs}


@router.post("/models/retrain")
def retrain(user: User = Depends(AdminUser)):
    """Retrain all three learned models against current data."""
    return {
        "forecasting": forecasting.train(),
        "waste": waste.train(),
        "trial_conversion": trial_conversion.train(),
    }


@router.get("/audit")
def audit_log(limit: int = Query(100, le=500), run_id: str | None = None,
              institution_id: int | None = None,
              user: User = Depends(AnyStaff), db: Session = Depends(get_db)):
    """Agent decision audit trail.

    A super_admin may view any institution or the whole platform at once;
    everyone else is pinned to their own institution's entries regardless of
    what institution_id they pass, so a kitchen manager cannot browse
    another cafeteria's agent actions.
    """
    q = db.query(AgentAction)
    if run_id:
        q = q.filter(AgentAction.run_id == run_id)
    if user.role != "super_admin":
        q = q.filter(AgentAction.institution_id == scoped_institution_id(user, institution_id))
    elif institution_id:
        q = q.filter(AgentAction.institution_id == institution_id)
    rows = q.order_by(AgentAction.id.desc()).limit(limit).all()
    insts = {i.id: i.name for i in db.query(Institution).all()}
    return [{
        "id": r.id, "run_id": r.run_id, "agent": r.agent_name,
        "action": r.action, "detail": r.detail,
        "records_affected": r.records_affected, "duration_ms": r.duration_ms,
        "status": r.status, "institution": insts.get(r.institution_id),
        "created_at": r.created_at.isoformat(),
    } for r in rows]


@router.get("/impact")
def impact_report(days: int = Query(30, ge=7, le=365), institution_id: int | None = None,
                  user: User = Depends(AnyStaff), db: Session = Depends(get_db)):
    """Headline outcome metrics - the numbers for the project paper.

    A super_admin with no institution_id gets the platform-wide figures (the
    original behaviour); anyone else is scoped to their own institution
    regardless of what they pass, since this previously summed revenue and
    waste across every institution for any staff role that asked.
    """
    scope_id = institution_id if user.role == "super_admin" else scoped_institution_id(user, institution_id)
    start = date.today() - timedelta(days=days)

    sales_q = db.query(DailySales).filter(DailySales.sales_date >= start)
    alloc_q = db.query(NGOAllocation).filter(NGOAllocation.allocation_date >= start)
    surplus_q = db.query(SurplusRecord).filter(SurplusRecord.surplus_date >= start)
    offers_q = db.query(TrialOffer).filter(TrialOffer.offer_date >= start)
    price_q = db.query(PriceRecommendation).filter(PriceRecommendation.target_date >= start)
    if scope_id is not None:
        sales_q = sales_q.filter(DailySales.institution_id == scope_id)
        alloc_q = alloc_q.filter(NGOAllocation.institution_id == scope_id)
        surplus_q = surplus_q.filter(SurplusRecord.institution_id == scope_id)
        offers_q = offers_q.filter(TrialOffer.institution_id == scope_id)
        price_q = price_q.filter(PriceRecommendation.institution_id == scope_id)

    rows = sales_q.all()
    sold = sum(r.quantity_sold for r in rows)
    left = sum(r.quantity_leftover for r in rows)
    prepared = sum(r.quantity_prepared for r in rows)
    revenue = sum(r.revenue for r in rows)
    cost = sum(r.unit_cost * r.quantity_prepared for r in rows)

    allocs = alloc_q.all()
    surplus = surplus_q.all()
    total_surplus = sum(s.quantity for s in surplus)
    donated = sum(a.quantity for a in allocs)

    offers = offers_q.all()
    price_recs = price_q.all()

    fc = forecasting.get_metrics()
    tc = trial_conversion.get_metrics()

    return {
        "window_days": days,
        "waste": {
            "baseline_waste_pct": round(100 * left / prepared, 2) if prepared else 0.0,
            "units_wasted": left,
            "surplus_redistributed": donated,
            "surplus_total": total_surplus,
            "redistribution_coverage_pct": round(100 * donated / total_surplus, 1)
            if total_surplus else 0.0,
        },
        "profit": {
            "revenue": round(revenue, 2), "cost": round(cost, 2),
            "profit": round(revenue - cost, 2),
            "margin_pct": round(100 * (revenue - cost) / revenue, 1) if revenue else 0.0,
            "price_recommendations_issued": len(price_recs),
            "floor_enforced_count": sum(1 for p in price_recs if p.floor_enforced),
        },
        "social": {
            "meals_donated": donated,
            "ngo_partners_served": len({a.ngo_id for a in allocs}),
            "fairness": fairness_report(db, days),
        },
        "conversion": {
            "offers_issued": len(offers),
            "expected_conversions": round(
                sum(o.conversion_probability for o in offers), 1),
            "model_auc": tc.get("auc"),
            "lift_vs_blanket_discount": tc.get("lift_at_top20pct"),
        },
        "model_quality": {
            "forecast_r2": fc.get("r2"), "forecast_mape": fc.get("mape"),
            "forecast_improvement_over_naive_pct": fc.get("improvement_over_naive_pct"),
        },
    }
