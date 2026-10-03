"""SQLAlchemy domain models for the Smart Cafeteria System.

Layers mirror the architecture in DOCS/: operational/data entities feed the
intelligence-layer engines, whose outputs are persisted back here so every
recommendation is auditable.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# --------------------------------------------------------------------------
# Identity & tenancy
# --------------------------------------------------------------------------
class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    # One of: corporate | college | school -- drives every pricing decision.
    segment: Mapped[str] = mapped_column(String(20), index=True)
    city: Mapped[str] = mapped_column(String(80), default="Chennai")
    latitude: Mapped[float] = mapped_column(Float, default=13.0827)
    longitude: Mapped[float] = mapped_column(Float, default=80.2707)
    headcount: Mapped[int] = mapped_column(Integer, default=500)
    opening_time: Mapped[str] = mapped_column(String(10), default="08:00")
    closing_time: Mapped[str] = mapped_column(String(10), default="18:00")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    users: Mapped[list["User"]] = relationship(back_populates="institution")
    dishes: Mapped[list["Dish"]] = relationship(back_populates="institution")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    hashed_password: Mapped[str] = mapped_column(String(255))
    # super_admin | kitchen_manager | coordinator | ngo_partner | customer
    role: Mapped[str] = mapped_column(String(30), index=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    institution_id: Mapped[int | None] = mapped_column(ForeignKey("institutions.id"), nullable=True)
    ngo_id: Mapped[int | None] = mapped_column(ForeignKey("ngos.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    institution: Mapped["Institution | None"] = relationship(back_populates="users")


# --------------------------------------------------------------------------
# Menu, recipes, inventory
# --------------------------------------------------------------------------
class Dish(Base):
    __tablename__ = "dishes"

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(40))        # breakfast|main|snack|beverage|dessert
    cuisine: Mapped[str] = mapped_column(String(40), default="south_indian")
    is_veg: Mapped[bool] = mapped_column(Boolean, default=True)
    spice_level: Mapped[int] = mapped_column(Integer, default=2)   # 0-4
    sweetness: Mapped[int] = mapped_column(Integer, default=1)     # 0-4
    # Cost to produce one unit -- the basis of the cost+20% price floor.
    unit_cost: Mapped[float] = mapped_column(Float)
    base_price: Mapped[float] = mapped_column(Float)
    # Fixed anchor for the segment pricing band, set once at creation and
    # never mutated by approvals. The pricing engine must band around this,
    # not around base_price -- base_price changes every time a manager
    # approves a recommendation, and anchoring the band to a value the
    # engine itself just moved compounds a price increase every single day
    # it runs (a "price ratchet").
    reference_price: Mapped[float] = mapped_column(Float, default=0.0)
    shelf_life_hours: Mapped[int] = mapped_column(Integer, default=6)
    popularity_score: Mapped[float] = mapped_column(Float, default=0.5)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    institution: Mapped["Institution"] = relationship(back_populates="dishes")
    ingredients: Mapped[list["DishIngredient"]] = relationship(
        back_populates="dish", cascade="all, delete-orphan"
    )


class Ingredient(Base):
    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    unit: Mapped[str] = mapped_column(String(20), default="kg")
    cost_per_unit: Mapped[float] = mapped_column(Float, default=50.0)


class DishIngredient(Base):
    __tablename__ = "dish_ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"), index=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    quantity: Mapped[float] = mapped_column(Float, default=0.1)

    dish: Mapped["Dish"] = relationship(back_populates="ingredients")
    ingredient: Mapped["Ingredient"] = relationship()


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"), index=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    quantity_on_hand: Mapped[float] = mapped_column(Float, default=0.0)
    reorder_level: Mapped[float] = mapped_column(Float, default=5.0)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    ingredient: Mapped["Ingredient"] = relationship()


# --------------------------------------------------------------------------
# Transactions
# --------------------------------------------------------------------------
class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    order_date: Mapped[date] = mapped_column(Date, index=True)
    placed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(20), default="completed")
    total_amount: Mapped[float] = mapped_column(Float, default=0.0)
    channel: Mapped[str] = mapped_column(String(20), default="counter")   # counter|app

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Float)
    unit_cost: Mapped[float] = mapped_column(Float)
    discount_applied: Mapped[float] = mapped_column(Float, default=0.0)

    order: Mapped["Order"] = relationship(back_populates="items")
    dish: Mapped["Dish"] = relationship()


class DailySales(Base):
    """Per-dish per-day aggregate: the training table for every ML engine."""
    __tablename__ = "daily_sales"
    __table_args__ = (UniqueConstraint("institution_id", "dish_id", "sales_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"), index=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"), index=True)
    sales_date: Mapped[date] = mapped_column(Date, index=True)
    quantity_prepared: Mapped[int] = mapped_column(Integer, default=0)
    quantity_sold: Mapped[int] = mapped_column(Integer, default=0)
    quantity_leftover: Mapped[int] = mapped_column(Integer, default=0)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    revenue: Mapped[float] = mapped_column(Float, default=0.0)
    # Contextual features consumed by the forecasting engine
    temperature_c: Mapped[float] = mapped_column(Float, default=30.0)
    rainfall_mm: Mapped[float] = mapped_column(Float, default=0.0)
    is_holiday: Mapped[bool] = mapped_column(Boolean, default=False)
    is_exam_period: Mapped[bool] = mapped_column(Boolean, default=False)
    day_of_week: Mapped[int] = mapped_column(Integer, default=0)
    footfall: Mapped[int] = mapped_column(Integer, default=0)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"), index=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    rating: Mapped[int] = mapped_column(Integer, default=4)   # 1-5
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# --------------------------------------------------------------------------
# Intelligence-layer outputs (persisted so every decision is auditable)
# --------------------------------------------------------------------------
class DemandForecast(Base):
    __tablename__ = "demand_forecasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"), index=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"), index=True)
    forecast_date: Mapped[date] = mapped_column(Date, index=True)
    predicted_demand: Mapped[float] = mapped_column(Float)
    lower_bound: Mapped[float] = mapped_column(Float, default=0.0)
    upper_bound: Mapped[float] = mapped_column(Float, default=0.0)
    recommended_prep: Mapped[int] = mapped_column(Integer, default=0)
    model_version: Mapped[str] = mapped_column(String(40), default="xgb-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PriceRecommendation(Base):
    __tablename__ = "price_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"), index=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"), index=True)
    target_date: Mapped[date] = mapped_column(Date, index=True)
    current_price: Mapped[float] = mapped_column(Float)
    recommended_price: Mapped[float] = mapped_column(Float)
    price_floor: Mapped[float] = mapped_column(Float)
    floor_enforced: Mapped[bool] = mapped_column(Boolean, default=False)
    segment: Mapped[str] = mapped_column(String(20))
    rationale: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|approved|rejected|adjusted
    approved_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MenuRecommendation(Base):
    __tablename__ = "menu_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"), index=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"), index=True)
    target_date: Mapped[date] = mapped_column(Date, index=True)
    score: Mapped[float] = mapped_column(Float)
    rank: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TrialOffer(Base):
    """Trial-Conversion Engine output: targeted discount for a non-buyer."""
    __tablename__ = "trial_offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"), index=True)
    offer_date: Mapped[date] = mapped_column(Date, index=True)
    discount_pct: Mapped[float] = mapped_column(Float, default=0.25)
    original_price: Mapped[float] = mapped_column(Float)
    offer_price: Mapped[float] = mapped_column(Float)
    floor_enforced: Mapped[bool] = mapped_column(Boolean, default=False)
    conversion_probability: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|approved|redeemed|expired
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WastePrediction(Base):
    __tablename__ = "waste_predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"), index=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"), index=True)
    target_date: Mapped[date] = mapped_column(Date, index=True)
    predicted_leftover: Mapped[float] = mapped_column(Float)
    risk_level: Mapped[str] = mapped_column(String(20), default="low")  # low|medium|high
    hours_to_expiry: Mapped[int] = mapped_column(Integer, default=6)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# --------------------------------------------------------------------------
# Surplus & NGO distribution
# --------------------------------------------------------------------------
class NGO(Base):
    __tablename__ = "ngos"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    contact_person: Mapped[str] = mapped_column(String(120), default="")
    phone: Mapped[str] = mapped_column(String(20), default="")
    city: Mapped[str] = mapped_column(String(80), default="Chennai")
    latitude: Mapped[float] = mapped_column(Float, default=13.05)
    longitude: Mapped[float] = mapped_column(Float, default=80.25)
    # Self-reported daily need (meals) -- feeds the allocation objective.
    daily_need_meals: Mapped[int] = mapped_column(Integer, default=100)
    beneficiaries: Mapped[int] = mapped_column(Integer, default=100)
    # 0-1 pickup reliability, learned from completed vs missed pickups.
    reliability_score: Mapped[float] = mapped_column(Float, default=0.8)
    accepts_veg_only: Mapped[bool] = mapped_column(Boolean, default=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class SurplusRecord(Base):
    __tablename__ = "surplus_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"), index=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"), index=True)
    surplus_date: Mapped[date] = mapped_column(Date, index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    hours_to_expiry: Mapped[int] = mapped_column(Integer, default=4)
    is_veg: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="available")  # available|allocated|collected

    dish: Mapped["Dish"] = relationship()


class NGOAllocation(Base):
    __tablename__ = "ngo_allocations"

    id: Mapped[int] = mapped_column(primary_key=True)
    surplus_id: Mapped[int] = mapped_column(ForeignKey("surplus_records.id"), index=True)
    ngo_id: Mapped[int] = mapped_column(ForeignKey("ngos.id"), index=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"), index=True)
    allocation_date: Mapped[date] = mapped_column(Date, index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    share_pct: Mapped[float] = mapped_column(Float, default=0.0)
    meets_guarantee: Mapped[bool] = mapped_column(Boolean, default=True)
    # True when no pickup slot could be found before this item's predicted
    # expiry -- surfaced to the kitchen/NGO rather than silently dropped.
    expiry_risk: Mapped[bool] = mapped_column(Boolean, default=False)
    pickup_slot: Mapped[str] = mapped_column(String(40), default="18:00-19:00")
    status: Mapped[str] = mapped_column(String(20), default="scheduled")  # scheduled|collected|missed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    ngo: Mapped["NGO"] = relationship()
    surplus: Mapped["SurplusRecord"] = relationship()


class AgentAction(Base):
    """Audit log of every autonomous agent decision."""
    __tablename__ = "agent_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int | None] = mapped_column(ForeignKey("institutions.id"), nullable=True)
    run_id: Mapped[str] = mapped_column(String(40), index=True)
    agent_name: Mapped[str] = mapped_column(String(60), index=True)
    action: Mapped[str] = mapped_column(String(120))
    detail: Mapped[str] = mapped_column(Text, default="")
    records_affected: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="success")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
