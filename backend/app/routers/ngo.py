"""NGO Partner endpoints - deliberately simple, mobile-friendly payloads."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.config import NGO_MIN_GUARANTEE
from app.database import get_db
from app.engines.ngo_allocation import allocate, sync_surplus_status
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
            "pickup_slot": a.pickup_slot, "status_counts": {},
            "quantity": 0, "share_pct": a.share_pct,
            "meets_guarantee": a.meets_guarantee,
            "allocation_ids": [], "items": [],
        })
        e["quantity"] += a.quantity
        e["allocation_ids"].append(a.id)
        e["status_counts"][a.status] = e["status_counts"].get(a.status, 0) + 1
        sr = db.get(SurplusRecord, a.surplus_id)
        if sr:
            dish = db.get(Dish, sr.dish_id)
            e["items"].append({
                "dish_name": dish.name if dish else "?",
                "quantity": a.quantity, "is_veg": sr.is_veg,
                "hours_to_expiry": sr.hours_to_expiry,
            })
    # A pickup can span multiple dishes that are not all confirmed in the
    # same action; show a single "status" only when every part agrees, and
    # "mixed" otherwise rather than silently reporting just the first row's.
    for e in by_inst.values():
        e["status"] = (next(iter(e["status_counts"]))
                       if len(e["status_counts"]) == 1 else "mixed")

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
            # Which surplus pool the guarantee percentage above is measured
            # against -- a veg-only NGO's 20% is of the *vegetarian* surplus
            # only, not the cafeteria's total surplus, and showing a bare
            # "18% of surplus" next to "guarantee met" otherwise reads as
            # contradictory.
            "guarantee_pool": "vegetarian" if ngo.accepts_veg_only else "total",
            "all_meet_guarantee": all(v["meets_guarantee"] for v in by_inst.values())
            if by_inst else False,
            "pending_pickups": sum(1 for v in by_inst.values() if v["status"] == "scheduled"),
        },
        "pickups": sorted(by_inst.values(), key=lambda v: -v["quantity"]),
    }


@router.post("/pickups/confirm")
def confirm_pickup(payload: PickupUpdate, user: User = Depends(NGOUser),
                   db: Session = Depends(get_db)):
    """Mark allocations collected or missed; reliability updates from this.

    Only allocations still in "scheduled" state can be confirmed -- without
    this guard the same pickup could be confirmed over and over, each time
    re-running the reliability-score update and making it drift (observed:
    0.93 -> 0.98 -> 0.68 -> 0.78 from repeated confirmations of one pickup).
    """
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

    actionable = [r for r in rows if r.status == "scheduled"]
    if not actionable:
        raise HTTPException(
            409, "These pickups have already been confirmed and cannot be changed")

    affected: set[tuple[int, date]] = set()
    for r in actionable:
        r.status = payload.status
        affected.add((r.institution_id, r.allocation_date))
    db.flush()
    sync_surplus_status(db, [r.surplus_id for r in actionable])

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

    # A missed pickup's food must not simply sit "allocated" and wasted --
    # re-run the allocation for every (institution, date) touched by a miss
    # so the freed quantity is immediately re-offered to another NGO.
    if payload.status == "missed":
        for institution_id, allocation_date in affected:
            db.query(NGOAllocation).filter(
                NGOAllocation.institution_id == institution_id,
                NGOAllocation.allocation_date == allocation_date,
                NGOAllocation.status == "scheduled").delete()
            db.commit()
            allocate(db, institution_id, allocation_date, persist=True)
            surplus_ids = [s.id for s in db.query(SurplusRecord).filter(
                SurplusRecord.institution_id == institution_id,
                SurplusRecord.surplus_date == allocation_date).all()]
            sync_surplus_status(db, surplus_ids)
            db.commit()

    return {"status": "ok", "updated": len(actionable),
            "skipped_already_settled": len(rows) - len(actionable),
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
                                   "status_counts": {}})
        e["quantity"] += r.quantity
        e["institutions"].add(insts.get(r.institution_id, "?"))
        e["status_counts"][r.status] = e["status_counts"].get(r.status, 0) + 1
    series = [{
        "date": v["date"], "quantity": v["quantity"],
        "institutions": sorted(v["institutions"]),
        "status_counts": v["status_counts"],
        # Backward-compatible single-status summary: the day's one status if
        # every pickup that day shares it, otherwise "mixed" -- previously
        # this field silently showed only the first row's status even when a
        # day held a mix of collected and missed pickups.
        "status": next(iter(v["status_counts"])) if len(v["status_counts"]) == 1 else "mixed",
    } for v in sorted(by_date.values(), key=lambda e: e["date"])]

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
    # Reliability is measured, never self-declared, and verification/active
    # status are platform-governance decisions -- an NGO must not be able to
    # self-verify or reactivate/deactivate its own account through the
    # profile form it otherwise shares with the admin endpoint.
    for guarded in ("reliability_score", "verified", "active"):
        data.pop(guarded, None)
    for k, v in data.items():
        setattr(n, k, v)
    db.commit()
    return {"status": "ok", "id": n.id, "daily_need_meals": n.daily_need_meals}
