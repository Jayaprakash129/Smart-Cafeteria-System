"""Pydantic request/response models."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class PriceDecision(BaseModel):
    recommendation_id: int
    action: str = Field(description="approve | reject | adjust")
    adjusted_price: float | None = None


class MenuDecision(BaseModel):
    recommendation_id: int
    action: str = Field(description="approve | reject")


class OfferDecision(BaseModel):
    offer_ids: list[int]
    action: str = Field(description="approve | reject")


class InventoryUpdate(BaseModel):
    item_id: int
    quantity_on_hand: float
    expiry_date: date | None = None


class PickupUpdate(BaseModel):
    allocation_ids: list[int]
    status: str = Field(description="collected | missed")


class NGOProfileUpdate(BaseModel):
    daily_need_meals: int | None = None
    beneficiaries: int | None = None
    accepts_veg_only: bool | None = None
    contact_person: str | None = None
    phone: str | None = None


class OrderItemIn(BaseModel):
    dish_id: int
    quantity: int = 1


class OrderCreate(BaseModel):
    items: list[OrderItemIn]
    channel: str = "app"


class FeedbackCreate(BaseModel):
    dish_id: int
    rating: int = Field(ge=1, le=5)
    comment: str | None = None


class InstitutionCreate(BaseModel):
    name: str
    segment: str
    headcount: int = 500
    city: str = "Chennai"
    latitude: float = 13.0827
    longitude: float = 80.2707


class UserCreate(BaseModel):
    email: str
    full_name: str
    password: str
    role: str
    institution_id: int | None = None
    ngo_id: int | None = None


class PipelineRequest(BaseModel):
    institution_id: int | None = None
    target_date: date | None = None
