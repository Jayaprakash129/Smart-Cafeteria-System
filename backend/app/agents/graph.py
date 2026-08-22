"""Agentic orchestration layer - the Supervisor and its six specialist agents.

The daily pipeline is a directed graph with real data dependencies, which is
why it is orchestrated rather than merely scripted:

        ContextAgent (weather, calendar)
               |
        ForecastAgent  -----------------+
               |                        |
        WasteAgent (needs prep qty)     |
               |                        |
        PricingAgent (needs waste risk + demand)
               |
        MenuAgent (needs prices + trends)
               |
        OfferAgent (needs yesterday's best seller)
               |
        NGOAgent (needs predicted surplus)
               |
        Supervisor -> briefing + audit trail

Every agent writes an AgentAction row, so the Audit Log page can show exactly
what the system decided, why, how long it took, and what it touched. Failures
are captured per-agent: one failing agent degrades its own step rather than
collapsing the run.
"""
from __future__ import annotations

import traceback
import uuid
from datetime import date, timedelta
from time import perf_counter

from sqlalchemy.orm import Session

from app.agents.llm import build_briefing_prompt, narrate
from app.config import TRIAL_DISCOUNT
from app.engines import forecasting, ngo_allocation, recommendation, trial_conversion, waste
from app.engines.pricing import recommend_prices
from app.external.weather import get_forecast
from app.models import (
    AgentAction, DemandForecast, Dish, Institution, MenuRecommendation,
    PriceRecommendation, SurplusRecord, TrialOffer, WastePrediction,
)


class AgentRun:
    """Carries shared state between agents and records the audit trail."""

    def __init__(self, db: Session, institution: Institution, target: date):
        self.db = db
        self.institution = institution
        self.target = target
        self.run_id = uuid.uuid4().hex[:12]
        self.state: dict = {}
        self.trace: list[dict] = []
        self.errors: list[str] = []

    def log(self, agent: str, action: str, detail: str = "",
            records: int = 0, ms: int = 0, status: str = "success") -> None:
        row = AgentAction(
            institution_id=self.institution.id, run_id=self.run_id,
            agent_name=agent, action=action, detail=detail[:2000],
            records_affected=records, duration_ms=ms, status=status,
        )
        self.db.add(row)
        self.trace.append({
            "agent": agent, "action": action, "detail": detail,
            "records_affected": records, "duration_ms": ms, "status": status,
        })


def _step(run: AgentRun, name: str, action: str):
    """Decorator-ish helper: time an agent step and capture its failure."""
    class _Ctx:
        def __enter__(self):
            self.t0 = perf_counter()
            return self

        def __exit__(self, exc_type, exc, tb):
            ms = int((perf_counter() - self.t0) * 1000)
            if exc is not None:
                run.errors.append(f"{name}: {exc}")
                run.log(name, action, f"FAILED: {exc}\n{traceback.format_exc()[:600]}",
                        0, ms, "error")
                return True          # suppress so the pipeline continues
            run.log(name, action, self.detail, self.records, ms)
            return False

        detail = ""
        records = 0
    return _Ctx()


# --------------------------------------------------------------------------
# Individual agents
# --------------------------------------------------------------------------
def context_agent(run: AgentRun) -> None:
    """Fetch real weather + calendar context for the target day."""
    with _step(run, "ContextAgent", "fetch_context") as ctx:
        wx = get_forecast(run.institution.latitude, run.institution.longitude,
                          run.target)
        run.state["weather"] = wx
        ctx.detail = (f"temp={wx.get('temperature_c')}C rain={wx.get('rainfall_mm')}mm "
                      f"source={wx.get('source')}")
        ctx.records = 1


def forecast_agent(run: AgentRun) -> None:
    with _step(run, "ForecastAgent", "predict_demand") as ctx:
        rows = forecasting.forecast_institution(
            run.institution.id, run.target, run.state.get("weather", {}))
        run.state["forecasts"] = rows

        run.db.query(DemandForecast).filter(
            DemandForecast.institution_id == run.institution.id,
            DemandForecast.forecast_date == run.target).delete()
        for r in rows:
            run.db.add(DemandForecast(
                institution_id=run.institution.id, dish_id=r["dish_id"],
                forecast_date=run.target, predicted_demand=r["predicted_demand"],
                lower_bound=r["lower_bound"], upper_bound=r["upper_bound"],
                recommended_prep=r["recommended_prep"],
            ))
        total = sum(r["predicted_demand"] for r in rows)
        ctx.detail = f"{len(rows)} dishes, total predicted demand {total:.0f} units"
        ctx.records = len(rows)


def waste_agent(run: AgentRun) -> None:
    with _step(run, "WasteAgent", "predict_surplus") as ctx:
        rows = waste.predict_waste(run.institution.id,
                                   run.state.get("forecasts", []), run.target)
        run.state["waste"] = rows

        run.db.query(WastePrediction).filter(
            WastePrediction.institution_id == run.institution.id,
            WastePrediction.target_date == run.target).delete()
        for r in rows:
            run.db.add(WastePrediction(
                institution_id=run.institution.id, dish_id=r["dish_id"],
                target_date=run.target, predicted_leftover=r["predicted_leftover"],
                risk_level=r["risk_level"], hours_to_expiry=r["hours_to_expiry"],
            ))
        at_risk = sum(r["value_at_risk"] for r in rows)
        high = sum(1 for r in rows if r["risk_level"] == "high")
        ctx.detail = f"{high} high-risk dishes, Rs.{at_risk:,.0f} of stock at risk"
        ctx.records = len(rows)


def pricing_agent(run: AgentRun) -> None:
    with _step(run, "PricingAgent", "recommend_prices") as ctx:
        waste_map = {r["dish_id"]: r["leftover_share"]
                     for r in run.state.get("waste", [])}
        rows = recommend_prices(run.state.get("forecasts", []),
                                run.institution.segment, waste_map)
        run.state["prices"] = rows

        run.db.query(PriceRecommendation).filter(
            PriceRecommendation.institution_id == run.institution.id,
            PriceRecommendation.target_date == run.target).delete()
        for r in rows:
            run.db.add(PriceRecommendation(
                institution_id=run.institution.id, dish_id=r["dish_id"],
                target_date=run.target, current_price=r["current_price"],
                recommended_price=r["recommended_price"],
                price_floor=r["price_floor"], floor_enforced=r["floor_enforced"],
                segment=run.institution.segment, rationale=r["rationale"],
                status="pending",
            ))
        uplift = sum(r["profit_uplift"] for r in rows)
        floored = sum(1 for r in rows if r["floor_enforced"])
        ctx.detail = (f"{len(rows)} prices, projected uplift Rs.{uplift:,.0f}, "
                      f"{floored} floor-enforced")
        ctx.records = len(rows)


def menu_agent(run: AgentRun) -> None:
    with _step(run, "MenuAgent", "recommend_menu") as ctx:
        rows = recommendation.recommend_menu(
            run.institution.id, run.target, top_n=12,
            weather=run.state.get("weather", {}))
        run.state["menu"] = rows

        run.db.query(MenuRecommendation).filter(
            MenuRecommendation.institution_id == run.institution.id,
            MenuRecommendation.target_date == run.target).delete()
        for r in rows:
            run.db.add(MenuRecommendation(
                institution_id=run.institution.id, dish_id=r["dish_id"],
                target_date=run.target, score=r["score"], rank=r["rank"],
                reason=r["reason"], status="pending",
            ))
        ctx.detail = "top picks: " + ", ".join(r["dish_name"] for r in rows[:5])
        ctx.records = len(rows)


def offer_agent(run: AgentRun) -> None:
    with _step(run, "OfferAgent", "generate_trial_offers") as ctx:
        result = trial_conversion.generate_offers(
            run.institution.id, run.target, discount_pct=TRIAL_DISCOUNT)
        run.state["offers"] = result

        run.db.query(TrialOffer).filter(
            TrialOffer.institution_id == run.institution.id,
            TrialOffer.offer_date == run.target).delete()
        for o in result.get("offers", []):
            run.db.add(TrialOffer(
                institution_id=run.institution.id, customer_id=o["customer_id"],
                dish_id=o["dish_id"], offer_date=run.target,
                discount_pct=o["discount_pct"] / 100.0,
                original_price=o["original_price"], offer_price=o["offer_price"],
                floor_enforced=o["floor_enforced"],
                conversion_probability=o["conversion_probability"],
                status="pending",
            ))
        s = result.get("summary", {})
        bs = result.get("best_seller", {})
        ctx.detail = (f"best seller '{bs.get('dish_name')}': {s.get('non_buyers', 0)} "
                      f"non-buyers -> {s.get('offers_generated', 0)} offers, "
                      f"{s.get('expected_conversions', 0)} expected conversions")
        ctx.records = s.get("offers_generated", 0)


def ngo_agent(run: AgentRun) -> None:
    """Materialise predicted surplus, then solve the allocation."""
    with _step(run, "NGOAgent", "allocate_surplus") as ctx:
        existing = run.db.query(SurplusRecord).filter(
            SurplusRecord.institution_id == run.institution.id,
            SurplusRecord.surplus_date == run.target).all()

        if not existing:
            # Convert the waste engine's predictions into surplus records.
            dishes = {d.id: d for d in run.db.query(Dish).filter(
                Dish.institution_id == run.institution.id).all()}
            for w in run.state.get("waste", []):
                qty = int(round(w["predicted_leftover"]))
                if qty <= 0:
                    continue
                d = dishes.get(w["dish_id"])
                if d is None:
                    continue
                rec = SurplusRecord(
                    institution_id=run.institution.id, dish_id=w["dish_id"],
                    surplus_date=run.target, quantity=qty, unit_cost=d.unit_cost,
                    hours_to_expiry=w["hours_to_expiry"], is_veg=d.is_veg,
                    status="available")
                run.db.add(rec)
                existing.append(rec)
            run.db.flush()

        result = ngo_allocation.allocate(
            run.db, run.institution.id, run.target,
            surplus=[s for s in existing if s.status == "available"], persist=True)
        run.state["ngo"] = result
        ctx.detail = (f"{result.get('distributed', 0)}/{result.get('total_surplus', 0)} "
                      f"units to {result.get('partners_selected', 0)} NGOs "
                      f"({result.get('coverage_pct', 0)}% coverage)")
        ctx.records = result.get("partners_selected", 0)


# --------------------------------------------------------------------------
# Supervisor
# --------------------------------------------------------------------------
PIPELINE = [context_agent, forecast_agent, waste_agent, pricing_agent,
            menu_agent, offer_agent, ngo_agent]


def run_daily_pipeline(db: Session, institution_id: int,
                       target: date | None = None) -> dict:
    """Execute the full supervised agent pipeline for one institution."""
    target = target or date.today()
    inst = db.get(Institution, institution_id)
    if inst is None:
        raise ValueError(f"Institution {institution_id} not found")

    run = AgentRun(db, inst, target)
    t0 = perf_counter()
    for agent in PIPELINE:
        agent(run)
    db.commit()

    summary = build_summary(run)
    total_ms = int((perf_counter() - t0) * 1000)

    briefing = narrate(build_briefing_prompt(summary),
                       fallback=template_briefing(summary))
    run.log("Supervisor", "daily_briefing",
            f"pipeline complete in {total_ms}ms via {briefing['source']}",
            len(run.trace), total_ms,
            "success" if not run.errors else "partial")
    db.commit()

    return {
        "run_id": run.run_id,
        "institution": {"id": inst.id, "name": inst.name, "segment": inst.segment},
        "target_date": target.isoformat(),
        "duration_ms": total_ms,
        "status": "success" if not run.errors else "partial",
        "errors": run.errors,
        "briefing": briefing["text"],
        "briefing_source": briefing["source"],
        "summary": summary,
        "trace": run.trace,
    }


def build_summary(run: AgentRun) -> dict:
    f = run.state.get("forecasts", [])
    w = run.state.get("waste", [])
    p = run.state.get("prices", [])
    m = run.state.get("menu", [])
    o = run.state.get("offers", {}) or {}
    n = run.state.get("ngo", {}) or {}
    wx = run.state.get("weather", {}) or {}

    return {
        "institution": run.institution.name,
        "segment": run.institution.segment,
        "date": run.target.isoformat(),
        "weather": {"temperature_c": wx.get("temperature_c"),
                    "rainfall_mm": wx.get("rainfall_mm"),
                    "source": wx.get("source")},
        "demand": {
            "dishes_forecast": len(f),
            "total_predicted_units": round(sum(r["predicted_demand"] for r in f), 1),
            "total_recommended_prep": sum(r["recommended_prep"] for r in f),
            "top_dishes": [r["dish_name"] for r in f[:5]],
        },
        "waste": {
            "high_risk_dishes": sum(1 for r in w if r["risk_level"] == "high"),
            "predicted_leftover_units": round(sum(r["predicted_leftover"] for r in w), 1),
            "value_at_risk_inr": round(sum(r["value_at_risk"] for r in w), 2),
        },
        "pricing": {
            "recommendations": len(p),
            "projected_profit_uplift_inr": round(sum(r["profit_uplift"] for r in p), 2),
            "floor_enforced_count": sum(1 for r in p if r["floor_enforced"]),
            "avg_margin_pct": round(
                sum(r["margin_pct"] for r in p) / len(p), 1) if p else 0.0,
        },
        "menu": {"top_recommendations": [r["dish_name"] for r in m[:5]]},
        "offers": o.get("summary", {}),
        "best_seller": o.get("best_seller", {}),
        "ngo": {
            "total_surplus": n.get("total_surplus", 0),
            "distributed": n.get("distributed", 0),
            "coverage_pct": n.get("coverage_pct", 0),
            "partners": n.get("partners_selected", 0),
            "all_meet_guarantee": n.get("all_meet_guarantee", False),
            "meals_value_inr": n.get("meals_value_inr", 0),
        },
    }


def template_briefing(s: dict) -> str:
    """Deterministic briefing used when no LLM is available."""
    d, w, p = s["demand"], s["waste"], s["pricing"]
    o, n = s.get("offers", {}), s["ngo"]
    parts = [
        f"Forecast for {s['date']} at {s['institution']} ({s['segment']}): "
        f"{d['total_predicted_units']:.0f} units across {d['dishes_forecast']} dishes; "
        f"prepare {d['total_recommended_prep']} units. Top sellers expected: "
        f"{', '.join(d['top_dishes'][:3])}.",
        f"Pricing proposes {p['recommendations']} adjustments worth "
        f"Rs.{p['projected_profit_uplift_inr']:,.0f} in additional margin, with "
        f"{p['floor_enforced_count']} held at the cost-recovery floor.",
        f"Waste risk: {w['high_risk_dishes']} dishes flagged high, "
        f"Rs.{w['value_at_risk_inr']:,.0f} of stock at risk.",
    ]
    if o.get("offers_generated"):
        bs_name = s.get("best_seller", {}).get("dish_name") or "the best seller"
        parts.append(
            f"Trial-conversion targets {o['offers_generated']} non-buyers of "
            f"{bs_name}, expecting {o.get('expected_conversions', 0)} conversions.")
    parts.append(
        f"Surplus plan: {n['distributed']} of {n['total_surplus']} units routed to "
        f"{n['partners']} NGO partners ({n['coverage_pct']}% coverage), "
        f"guarantee {'satisfied' if n['all_meet_guarantee'] else 'NOT satisfied'}.")
    return " ".join(parts)
