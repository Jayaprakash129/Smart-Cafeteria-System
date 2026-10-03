"""Pydantic request/response models."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator

from app.auth import ROLES

# A simple, dependency-free email shape check (no email-validator package
# required): local part, @, domain, a dot, TLD.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


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
    quantity_on_hand: float = Field(ge=0)
    expiry_date: date | None = None


class PickupUpdate(BaseModel):
    allocation_ids: list[int]
    status: str = Field(description="collected | missed")


class NGOProfileUpdate(BaseModel):
    daily_need_meals: int | None = Field(default=None, ge=0)
    beneficiaries: int | None = Field(default=None, ge=0)
    accepts_veg_only: bool | None = None
    contact_person: str | None = None
    phone: str | None = None
    # Only ever honoured on the admin endpoint (routers/admin.py); the NGO
    # self-service endpoint (routers/ngo.py) explicitly strips both before
    # applying this payload, the same way it already strips
    # reliability_score -- an NGO must never be able to self-verify or
    # reactivate/deactivate its own account.
    verified: bool | None = None
    active: bool | None = None


class OrderItemIn(BaseModel):
    dish_id: int
    quantity: int = Field(default=1, ge=1, le=50)


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
    headcount: int = Field(default=500, gt=0)
    city: str = "Chennai"
    latitude: float = 13.0827
    longitude: float = 80.2707


class UserCreate(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN)
    full_name: str
    password: str = Field(min_length=8)
    role: str
    institution_id: int | None = None
    ngo_id: int | None = None

    @field_validator("role")
    @classmethod
    def _role_whitelist(cls, v: str) -> str:
        if v not in ROLES:
            raise ValueError(f"role must be one of {ROLES}")
        return v


class PipelineRequest(BaseModel):
    institution_id: int | None = None
    target_date: date | None = None


class ActualSurplusEntry(BaseModel):
    dish_id: int
    actual_quantity: int = Field(ge=0)


class ActualSurplusUpdate(BaseModel):
    items: list[ActualSurplusEntry]
