"""NGO Partner endpoints - deliberately simple, mobile-friendly payloads."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.config import NGO_MIN_GUARANTEE
from app.database import get_db
from app.models import Dish, Institution, NGO, NGOAllocation, SurplusRecord, User
from app.schemas import NGOProfileUpdate, PickupUpdate

router = APIRouter(prefix="/api/ngo", tags=["ngo-partner"])
NGOUser = require_roles("ngo_partner", "super_admin")


def _ngo_id(user: User, requested: int | None) -> int:
    if user.role == "super_admin":
        if requested is None:
            raise HTTPException(400, "super_admin must specify ngo_id")
        return requested
    if user.ngo_id is None:
        raise HTTPException(400, "User is not linked to an NGO")
    if requested is not None and requested != user.ngo_id:
        raise HTTPException(403, "Cross-NGO access denied")
    return user.ngo_id


@router.get("/today")
def today(ngo_id: int | None = None, target: date | None = None,
          user: User = Depends(NGOUser), db: Session = Depends(get_db)):
    """Today's Available Surplus, scoped to this NGO's allocations."""
    nid = _ngo_id(user, ngo_id)
    target = target or date.today()
    ngo = db.get(NGO, nid)
    if ngo is None:
        raise HTTPException(404, "NGO not found")

    allocs = db.query(NGOAllocation).filter(
        NGOAllocation.ngo_id == nid,
        NGOAllocation.allocation_date == target).all()
    insts = {i.id: i for i in db.query(Institution).all()}

    by_inst: dict[int, dict] = {}
    for a in allocs:
        e = by_inst.setdefault(a.institution_id, {
            "institution_id": a.institution_id,
            "institution_name": insts[a.institution_id].name
            if a.institution_id in insts else "?",
            "pickup_slot": a.pickup_slot, "status": a.status,
            "quantity": 0, "share_pct": a.share_pct,
            "meets_guarantee": a.meets_guarantee,
            "allocation_ids": [], "items": [],
        })
        e["quantity"] += a.quantity
        e["allocation_ids"].append(a.id)
        sr = db.get(SurplusRecord, a.surplus_id)
        if sr:
            dish = db.get(Dish, sr.dish_id)
            e["items"].append({
                "dish_name": dish.name if dish else "?",
                "quantity": a.quantity, "is_veg": sr.is_veg,
                "hours_to_expiry": sr.hours_to_expiry,
            })

    total = sum(v["quantity"] for v in by_inst.values())
    return {
        "ngo": {"id": ngo.id, "name": ngo.name,
                "daily_need_meals": ngo.daily_need_meals,
                "accepts_veg_only": ngo.accepts_veg_only,
                "reliability_score": ngo.reliability_score},
        "date": target.isoformat(),
        "summary": {
            "total_meals": total,
            "need_met_pct": round(100 * total / ngo.daily_need_meals, 1)
            if ngo.daily_need_meals else 0.0,
            "institutions": len(by_inst),
            "guarantee_pct": NGO_MIN_GUARANTEE * 100,
            "all_meet_guarantee": all(v["meets_guarantee"] for v in by_inst.values())
            if by_inst else False,
            "pending_pickups": sum(1 for v in by_inst.values() if v["status"] == "scheduled"),
        },
        "pickups": sorted(by_inst.values(), key=lambda v: -v["quantity"]),
    }


@router.post("/pickups/confirm")
def confirm_pickup(payload: PickupUpdate, user: User = Depends(NGOUser),
                   db: Session = Depends(get_db)):
    """Mark allocations collected or missed; reliability updates from this."""
    if payload.status not in ("collected", "missed"):
        raise HTTPException(400, "status must be collected or missed")
    rows = db.query(NGOAllocation).filter(
        NGOAllocation.id.in_(payload.allocation_ids)).all()
    if not rows:
        raise HTTPException(404, "No matching allocations")

    nid = _ngo_id(user, rows[0].ngo_id)
    for r in rows:
        if r.ngo_id != nid:
            raise HTTPException(403, "Cross-NGO access denied")
        r.status = payload.status
        if payload.status == "collected":
            sr = db.get(SurplusRecord, r.surplus_id)
            if sr:
                sr.status = "collected"

    # Reliability is learned from behaviour rather than self-reported: it feeds
    # straight back into the allocation objective on the next run.
    ngo = db.get(NGO, nid)
    history = db.query(NGOAllocation).filter(
        NGOAllocation.ngo_id == nid,
        NGOAllocation.status.in_(["collected", "missed"])).all()
    if history:
        rate = sum(1 for h in history if h.status == "collected") / len(history)
        ngo.reliability_score = round(0.7 * ngo.reliability_score + 0.3 * rate, 3)
    db.commit()
    return {"status": "ok", "updated": len(rows),
            "new_reliability_score": ngo.reliability_score}


@router.get("/history")
def history(ngo_id: int | None = None, days: int = Query(30, ge=7, le=365),
            user: User = Depends(NGOUser), db: Session = Depends(get_db)):
    nid = _ngo_id(user, ngo_id)
    start = date.today() - timedelta(days=days)
    rows = db.query(NGOAllocation).filter(
        NGOAllocation.ngo_id == nid,
        NGOAllocation.allocation_date >= start).order_by(
        NGOAllocation.allocation_date.desc()).all()
    insts = {i.id: i.name for i in db.query(Institution).all()}

    by_date: dict[str, dict] = {}
    for r in rows:
        k = r.allocation_date.isoformat()
        e = by_date.setdefault(k, {"date": k, "quantity": 0, "institutions": set(),
                                   "status": r.status})
        e["quantity"] += r.quantity
        e["institutions"].add(insts.get(r.institution_id, "?"))
    series = [{"date": v["date"], "quantity": v["quantity"],
               "institutions": sorted(v["institutions"]), "status": v["status"]}
              for v in sorted(by_date.values(), key=lambda e: e["date"])]

    collected = sum(1 for r in rows if r.status == "collected")
    return {
        "ngo_id": nid, "window_days": days,
        "totals": {
            "meals_received": sum(r.quantity for r in rows),
            "pickups": len(rows),
            "collected": collected,
            "missed": sum(1 for r in rows if r.status == "missed"),
            "collection_rate": round(collected / len(rows), 2) if rows else None,
        },
        "daily": series,
    }


@router.get("/profile")
def profile(ngo_id: int | None = None, user: User = Depends(NGOUser),
            db: Session = Depends(get_db)):
    n = db.get(NGO, _ngo_id(user, ngo_id))
    if n is None:
        raise HTTPException(404, "NGO not found")
    return {"id": n.id, "name": n.name, "contact_person": n.contact_person,
            "phone": n.phone, "city": n.city,
            "daily_need_meals": n.daily_need_meals, "beneficiaries": n.beneficiaries,
            "accepts_veg_only": n.accepts_veg_only,
            "reliability_score": n.reliability_score, "verified": n.verified}


@router.patch("/profile")
def update_profile(payload: NGOProfileUpdate, ngo_id: int | None = None,
                   user: User = Depends(NGOUser), db: Session = Depends(get_db)):
    """NGOs maintain their own need profile, which drives the allocation weights."""
    n = db.get(NGO, _ngo_id(user, ngo_id))
    if n is None:
        raise HTTPException(404, "NGO not found")
    data = payload.model_dump(exclude_none=True)
    # Reliability is measured, never self-declared.
    data.pop("reliability_score", None)
    for k, v in data.items():
        setattr(n, k, v)
    db.commit()
    return {"status": "ok", "id": n.id, "daily_need_meals": n.daily_need_meals}
