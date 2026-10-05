"""Smart Cafeteria System - FastAPI application entry point."""
import logging
from datetime import date

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.llm import is_available
from app.bootstrap import ensure_bootstrapped
from app.config import (AUTO_BOOTSTRAP, NGO_MIN_GUARANTEE, PRICE_FLOOR_MARGIN,
                        TRIAL_DISCOUNT)
from app.database import Base, engine
from app.migrate import SchemaDriftError, migrate_schema
from app.routers import admin, auth_router, customer, kitchen, ngo

logger = logging.getLogger("smart_cafeteria.startup")

Base.metadata.create_all(engine)

# Self-heal an out-of-date database: a column added to a model after a
# database was already seeded (e.g. Dish.reference_price,
# NGOAllocation.expiry_risk) would otherwise surface as an opaque
# "sqlite3.OperationalError: no such column" the first time it's queried,
# on every dish/kitchen endpoint. See app/migrate.py for what this can and
# cannot safely fix on its own.
try:
    _migration_report = migrate_schema(engine)
    if _migration_report.drift:
        logger.warning(_migration_report.summary())
    else:
        logger.info(_migration_report.summary())
except SchemaDriftError as exc:
    logger.error(str(exc))
    raise

# A fresh clone has no database or models (both gitignored), so the tables
# above were just created empty and every demo login would 401. Seed and
# train once; a no-op whenever data and models already exist.
if AUTO_BOOTSTRAP:
    ensure_bootstrapped()

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
