"""Smart Cafeteria System - FastAPI application entry point."""
from datetime import date

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.llm import is_available
from app.config import NGO_MIN_GUARANTEE, PRICE_FLOOR_MARGIN, TRIAL_DISCOUNT
from app.database import Base, engine
from app.routers import admin, auth_router, customer, kitchen, ngo

Base.metadata.create_all(engine)

app = FastAPI(
    title="Smart Cafeteria System API",
    description=(
        "AI-driven demand forecasting, segment-aware pricing, waste prevention "
        "and equitable multi-NGO surplus redistribution for institutional "
        "cafeterias.\n\n"
        "**Demo logins** are listed at `GET /api/auth/demo-accounts`."
    ),
    version="1.0.0",
)

# The Vite dev server and any local origin during the demo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(kitchen.router)
app.include_router(admin.router)
app.include_router(ngo.router)
app.include_router(customer.router)


@app.get("/api/health", tags=["system"])
def health():
    return {
        "status": "ok",
        "date": date.today().isoformat(),
        "business_rules": {
            "price_floor": f"unit_cost * (1 + {PRICE_FLOOR_MARGIN})",
            "ngo_min_guarantee": NGO_MIN_GUARANTEE,
            "trial_discount": TRIAL_DISCOUNT,
        },
        "llm_narration_available": is_available(),
    }


@app.get("/", tags=["system"])
def root():
    return {"service": "Smart Cafeteria System", "docs": "/docs",
            "health": "/api/health"}
