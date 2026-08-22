"""Engines 2 & 3 - Dynamic Segment Pricing and the hard Price Floor.

Economics
---------
Under constant-elasticity demand D(p) = D0 * (p/p0)^e, daily profit is

    pi(p) = (p - c) * D0 * (p / p0)^e

Setting d(pi)/dp = 0 gives the unconstrained profit-maximising price

    p* = c * e / (e + 1)        (valid only for e < -1, i.e. elastic demand)

For an *inelastic* segment (-1 < e < 0, which is our corporate case at
e = -0.6) the first-order condition has no interior maximum: profit rises
monotonically with price. Unbounded markup is neither realistic nor
defensible, so the segment ceiling is what makes the model well-posed. This is
exactly the fairness concern the survey paper raises about segment pricing,
handled explicitly rather than ignored.

Two hard constraints are then applied, in this order:
  1. Segment band     - price stays within [floor_mult, ceiling_mult] x base
  2. Cost-recovery floor - price is never below unit_cost * (1 + 20%)

The floor is applied last and unconditionally, so no discount, elasticity
estimate or waste markdown can ever push a price below cost recovery.
"""
from __future__ import annotations

from datetime import date

from app.config import PRICE_FLOOR_MARGIN, SEGMENT_PRICING


def price_floor(unit_cost: float) -> float:
    """The inviolable cost-recovery floor: cost + 20%."""
    return round(unit_cost * (1.0 + PRICE_FLOOR_MARGIN), 2)


def enforce_floor(price: float, unit_cost: float) -> tuple[float, bool]:
    """Clamp `price` up to the floor. Returns (final_price, was_enforced)."""
    floor = price_floor(unit_cost)
    if price < floor:
        return floor, True
    return round(price, 2), False


def optimal_price(unit_cost: float, base_price: float, segment: str,
                  waste_risk: float = 0.0, demand_ratio: float = 1.0) -> dict:
    """Recommend a price for one dish in one segment.

    waste_risk    : 0-1, predicted leftover share. High risk pulls price down.
    demand_ratio  : forecast demand / recent average. >1 means demand is running
                    hot, which supports a firmer price.
    """
    cfg = SEGMENT_PRICING.get(segment, SEGMENT_PRICING["college"])
    e = cfg["elasticity"]
    lo = base_price * cfg["floor_mult"]
    hi = base_price * cfg["ceiling_mult"]

    if e < -1.0:
        # Elastic segment: interior optimum exists.
        target = unit_cost * e / (e + 1.0)
        basis = "elastic-optimum"
    else:
        # Inelastic segment: profit is monotone increasing, so the segment
        # ceiling binds. Stated explicitly rather than silently clamped.
        target = hi
        basis = "inelastic-ceiling-bound"

    # Demand pressure: firm up when demand runs hot, soften when it runs cold.
    target *= 1.0 + 0.08 * max(-1.0, min(1.0, demand_ratio - 1.0))

    # Waste pressure: shift stock before it expires, but never below the floor.
    if waste_risk > 0.15:
        target *= 1.0 - min(0.18, (waste_risk - 0.15) * 0.9)

    banded = max(lo, min(hi, target))
    final, floored = enforce_floor(banded, unit_cost)

    margin_pct = 100.0 * (final - unit_cost) / unit_cost if unit_cost else 0.0
    delta_pct = 100.0 * (final - base_price) / base_price if base_price else 0.0

    reasons = [f"segment={segment} (elasticity {e})", basis]
    if demand_ratio > 1.08:
        reasons.append(f"demand running {100*(demand_ratio-1):.0f}% above average")
    elif demand_ratio < 0.92:
        reasons.append(f"demand running {100*(1-demand_ratio):.0f}% below average")
    if waste_risk > 0.15:
        reasons.append(f"waste risk {100*waste_risk:.0f}% -> markdown applied")
    if banded in (lo, hi):
        reasons.append("clamped to segment band")
    if floored:
        reasons.append("PRICE FLOOR ENFORCED (cost + 20%)")

    return {
        "recommended_price": final,
        "price_floor": price_floor(unit_cost),
        "segment_band": [round(lo, 2), round(hi, 2)],
        "floor_enforced": floored,
        "margin_pct": round(margin_pct, 1),
        "change_vs_base_pct": round(delta_pct, 1),
        "basis": basis,
        "rationale": "; ".join(reasons),
    }


def recommend_prices(forecasts: list[dict], segment: str,
                     waste_by_dish: dict[int, float] | None = None) -> list[dict]:
    """Produce a price recommendation per forecast row."""
    waste_by_dish = waste_by_dish or {}
    out = []
    for f in forecasts:
        demand = max(f.get("predicted_demand", 0.0), 0.0)
        prep = max(f.get("recommended_prep", 1), 1)
        waste_risk = waste_by_dish.get(f["dish_id"])
        if waste_risk is None:
            waste_risk = max(0.0, (prep - demand) / prep)

        roll = f.get("roll_7_demand") or demand
        demand_ratio = demand / roll if roll else 1.0

        rec = optimal_price(
            unit_cost=f["unit_cost"], base_price=f["base_price"],
            segment=segment, waste_risk=waste_risk, demand_ratio=demand_ratio,
        )
        projected_profit = (rec["recommended_price"] - f["unit_cost"]) * demand
        current_profit = (f["unit_price"] - f["unit_cost"]) * demand
        out.append({
            "dish_id": f["dish_id"],
            "dish_name": f["dish_name"],
            "category": f.get("category"),
            "unit_cost": f["unit_cost"],
            "current_price": f["unit_price"],
            "predicted_demand": demand,
            "waste_risk": round(waste_risk, 3),
            "projected_profit": round(projected_profit, 2),
            "profit_uplift": round(projected_profit - current_profit, 2),
            **rec,
        })
    return out


def apply_discount(original_price: float, unit_cost: float,
                   discount_pct: float) -> dict:
    """Apply a promotional discount, refusing to breach the cost floor.

    This is the shared guard used by the Trial-Conversion Engine: the headline
    discount is honoured only to the extent the floor allows, and any shortfall
    is reported rather than hidden.
    """
    naive = original_price * (1.0 - discount_pct)
    final, floored = enforce_floor(naive, unit_cost)
    effective = (original_price - final) / original_price if original_price else 0.0
    return {
        "original_price": round(original_price, 2),
        "requested_discount_pct": round(discount_pct * 100, 1),
        "offer_price": final,
        "effective_discount_pct": round(effective * 100, 1),
        "price_floor": price_floor(unit_cost),
        "floor_enforced": floored,
        "margin_retained": round(final - unit_cost, 2),
    }
