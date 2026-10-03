"""Central configuration for the Smart Cafeteria System."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
MODEL_DIR = Path(os.environ.get("MODEL_DIR", str(BASE_DIR / "models_store")))
DATA_DIR.mkdir(exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# SQLAlchemy ORM keeps this Postgres-swappable: replace with
# postgresql+psycopg://user:pass@host/db and nothing else changes.
# Overridable via env var so the test suite (and production) can point at a
# different database without touching the live demo data.
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR / 'smart_cafeteria.db'}")

# Read from the environment in production; the literal default only applies
# to the local/demo deployment described in the README.
JWT_SECRET = os.environ.get("JWT_SECRET", "smart-cafeteria-fyp-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_MINUTES = 60 * 12

# GET /api/auth/demo-accounts lists every demo password unauthenticated.
# The login screen doesn't actually call it (the demo credentials are
# hard-coded client-side), so it is disabled by default and only enabled
# deliberately for a local demo via DEMO_MODE=true.
DEMO_MODE = os.environ.get("DEMO_MODE", "true").lower() in ("1", "true", "yes")

# ---- Business rules from the project specification ----------------------
# Hard cost-recovery floor: no price may ever fall below cost + 20%.
PRICE_FLOOR_MARGIN = 0.20
# Every active NGO partner is guaranteed at least this share of daily surplus.
NGO_MIN_GUARANTEE = 0.20
# Trial-conversion discount offered to non-buyers of yesterday's best seller.
TRIAL_DISCOUNT = 0.25

# Segment-aware pricing bands (multiplier applied to base price, then clamped
# by the price floor). Corporate is price-inelastic/premium, college is
# trend-sensitive, school is highly price-sensitive.
SEGMENT_PRICING = {
    "corporate": {"floor_mult": 1.00, "ceiling_mult": 1.45, "elasticity": -0.6},
    "college":   {"floor_mult": 0.90, "ceiling_mult": 1.20, "elasticity": -1.3},
    "school":    {"floor_mult": 0.80, "ceiling_mult": 1.05, "elasticity": -2.1},
}

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
