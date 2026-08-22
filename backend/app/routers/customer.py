"""End Customer (employee / student) endpoints - mobile-first payloads."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.database import get_db
from app.models import (
    DailySales, Dish, Feedback, Institution, MenuRecommendation, Order,
    OrderItem, TrialOffer, User,
)
from app.schemas import FeedbackCreate, OrderCreate

router = APIRouter(prefix="/api/customer", tags=["customer"])
CustomerUser = require_roles("customer", "super_admin")


def _require_institution(user: User) -> int:
    if user.institution_id is None:
        raise HTTPException(400, "Customer is not attached to an institution")
    return user.institution_id


@router.get("/menu")
def menu(target: date | None = None, user: User = Depends(CustomerUser),
         db: Session = Depends(get_db)):
    """Today's Menu, with any personalised offer surfaced at the top."""
    inst_id = _require_institution(user)
    target = target or date.today()
    inst = db.get(Institution, inst_id)

    dishes = db.query(Dish).filter(Dish.institution_id == inst_id,
                                   Dish.active == True).all()  # noqa: E712
    recs = {r.dish_id: r for r in db.query(MenuRecommendation).filter(
        MenuRecommendation.institution_id == inst_id,
        MenuRecommendation.target_date == target).all()}

    offers = {o.dish_id: o for o in db.query(TrialOffer).filter(
        TrialOffer.customer_id == user.id,
        TrialOffer.offer_date == target,
        TrialOffer.status.in_(["pending", "approved"])).all()}

    ratings = {}
    for f in db.query(Feedback).filter(Feedback.institution_id == inst_id).all():
        ratings.setdefault(f.dish_id, []).append(f.rating)

    items = []
    for d in dishes:
        offer = offers.get(d.id)
        rl = ratings.get(d.id, [])
        items.append({
            "dish_id": d.id, "name": d.name, "category": d.category,
            "is_veg": d.is_veg, "spice_level": d.spice_level,
            "sweetness": d.sweetness, "price": d.base_price,
            "avg_rating": round(sum(rl) / len(rl), 1) if rl else None,
            "n_ratings": len(rl),
            "recommended": d.id in recs,
            "recommendation_rank": recs[d.id].rank if d.id in recs else None,
            "offer": {
                "offer_id": offer.id,
                "offer_price": offer.offer_price,
                "original_price": offer.original_price,
                "discount_pct": round(offer.discount_pct * 100, 1),
            } if offer else None,
        })

    items.sort(key=lambda r: (r["recommendation_rank"] is None,
                              r["recommendation_rank"] or 0))
    return {
        "institution": inst.name if inst else "", "date": target.isoformat(),
        "active_offers": len(offers),
        "categories": sorted({i["category"] for i in items}),
        "items": items,
    }


@router.get("/offers")
def my_offers(user: User = Depends(CustomerUser), db: Session = Depends(get_db)):
    """Offers / Trial Discounts screen."""
    rows = db.query(TrialOffer).filter(
        TrialOffer.customer_id == user.id).order_by(
        TrialOffer.offer_date.desc()).limit(30).all()
    dishes = {d.id: d for d in db.query(Dish).all()}
    return [{
        "id": o.id, "dish_id": o.dish_id,
        "dish_name": dishes[o.dish_id].name if o.dish_id in dishes else "?",
        "offer_date": o.offer_date.isoformat(),
        "original_price": o.original_price, "offer_price": o.offer_price,
        "discount_pct": round(o.discount_pct * 100, 1),
        "savings": round(o.original_price - o.offer_price, 2),
        "status": o.status,
        "is_active": o.status in ("pending", "approved")
        and o.offer_date >= date.today(),
    } for o in rows]


@router.post("/orders")
def place_order(payload: OrderCreate, user: User = Depends(CustomerUser),
                db: Session = Depends(get_db)):
    """Place an order, honouring any personalised offer automatically."""
    inst_id = _require_institution(user)
    if not payload.items:
        raise HTTPException(400, "Order must contain at least one item")

    today = date.today()
    offers = {o.dish_id: o for o in db.query(TrialOffer).filter(
        TrialOffer.customer_id == user.id,
        TrialOffer.offer_date == today,
        TrialOffer.status.in_(["pending", "approved"])).all()}

    order = Order(institution_id=inst_id, customer_id=user.id, order_date=today,
                  placed_at=datetime.utcnow(), status="completed",
                  channel=payload.channel, total_amount=0.0)
    db.add(order)
    db.flush()

    total = 0.0
    lines = []
    for item in payload.items:
        dish = db.get(Dish, item.dish_id)
        if dish is None or dish.institution_id != inst_id:
            raise HTTPException(404, f"Dish {item.dish_id} not available here")
        if item.quantity < 1:
            raise HTTPException(400, "Quantity must be at least 1")

        offer = offers.get(dish.id)
        price = offer.offer_price if offer else dish.base_price
        discount = (dish.base_price - price) if offer else 0.0
        if offer:
            offer.status = "redeemed"

        db.add(OrderItem(order_id=order.id, dish_id=dish.id, quantity=item.quantity,
                         unit_price=price, unit_cost=dish.unit_cost,
                         discount_applied=discount))
        total += price * item.quantity
        lines.append({"dish_id": dish.id, "dish_name": dish.name,
                      "quantity": item.quantity, "unit_price": price,
                      "offer_applied": bool(offer)})

    order.total_amount = round(total, 2)
    db.commit()
    return {"status": "ok", "order_id": order.id,
            "total_amount": order.total_amount, "items": lines}


@router.get("/orders")
def my_orders(limit: int = Query(20, le=100), user: User = Depends(CustomerUser),
              db: Session = Depends(get_db)):
    orders = db.query(Order).filter(Order.customer_id == user.id).order_by(
        Order.order_date.desc(), Order.id.desc()).limit(limit).all()
    dishes = {d.id: d for d in db.query(Dish).all()}
    out = []
    for o in orders:
        items = db.query(OrderItem).filter(OrderItem.order_id == o.id).all()
        out.append({
            "order_id": o.id, "date": o.order_date.isoformat(),
            "channel": o.channel, "status": o.status,
            "total_amount": o.total_amount,
            "items": [{
                "dish_id": i.dish_id,
                "dish_name": dishes[i.dish_id].name if i.dish_id in dishes else "?",
                "quantity": i.quantity, "unit_price": i.unit_price,
                "discount_applied": i.discount_applied,
            } for i in items],
        })
    return out


@router.post("/feedback")
def submit_feedback(payload: FeedbackCreate, user: User = Depends(CustomerUser),
                    db: Session = Depends(get_db)):
    inst_id = _require_institution(user)
    dish = db.get(Dish, payload.dish_id)
    if dish is None or dish.institution_id != inst_id:
        raise HTTPException(404, "Dish not found at this institution")
    db.add(Feedback(institution_id=inst_id, dish_id=payload.dish_id,
                    customer_id=user.id, rating=payload.rating,
                    comment=payload.comment))
    db.commit()
    return {"status": "ok", "dish_id": payload.dish_id, "rating": payload.rating}


@router.get("/profile")
def profile(user: User = Depends(CustomerUser), db: Session = Depends(get_db)):
    inst = db.get(Institution, user.institution_id) if user.institution_id else None
    start = date.today() - timedelta(days=30)
    orders = db.query(Order).filter(Order.customer_id == user.id,
                                    Order.order_date >= start).all()
    offers = db.query(TrialOffer).filter(TrialOffer.customer_id == user.id).all()
    return {
        "id": user.id, "full_name": user.full_name, "email": user.email,
        "phone": user.phone,
        "institution": {"id": inst.id, "name": inst.name, "segment": inst.segment}
        if inst else None,
        "stats_30d": {
            "orders": len(orders),
            "total_spend": round(sum(o.total_amount for o in orders), 2),
            "avg_order_value": round(
                sum(o.total_amount for o in orders) / len(orders), 2) if orders else 0.0,
            "offers_received": len(offers),
            "offers_redeemed": sum(1 for o in offers if o.status == "redeemed"),
        },
    }
