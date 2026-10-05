"""First-run bootstrap: seed an empty database and train missing models.

The SQLite database and the trained `.joblib` models are build outputs and
are deliberately gitignored (see the root .gitignore). On a fresh clone,
`Base.metadata.create_all()` at startup therefore creates every table
*empty*: the API boots cleanly, but there are no users, so every demo login
fails with "401 Incorrect email or password" even with the correct
credentials -- and the forecasting/waste endpoints fail for lack of models.
It only ever "worked" on the machine where `python -m app.seed` had been
run by hand.

ensure_bootstrapped() closes that gap. It is called once at FastAPI startup
and is a no-op on any machine that already has data and models, so it never
touches an existing database. Disable it with AUTO_BOOTSTRAP=false (the test
suite does, since it seeds its own isolated instance).
"""
from __future__ import annotations

import logging

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import User

logger = logging.getLogger("smart_cafeteria.bootstrap")


def _has_users() -> bool:
    with SessionLocal() as db:
        return (db.scalar(select(func.count()).select_from(User)) or 0) > 0


def ensure_bootstrapped() -> dict:
    """Seed the database if it has no users, then train any missing model."""
    # Imported lazily: these pull in numpy/pandas/sklearn/xgboost, which a
    # normal (already bootstrapped) startup has no reason to pay for here.
    from app.engines import forecasting, trial_conversion, waste

    report = {"seeded": False, "trained": []}

    seeded_now = False
    if not _has_users():
        logger.warning("Database has no users (fresh clone?) -- seeding the "
                       "demo dataset. This runs once and takes ~15s.")
        from app.seed import seed_all
        seed_all(verbose=False)
        seeded_now = report["seeded"] = True

    # A freshly seeded database invalidates any models trained on a
    # different one, so retrain all of them in that case.
    for name, engine_mod in (("forecasting", forecasting), ("waste", waste),
                             ("trial_conversion", trial_conversion)):
        if seeded_now or not engine_mod.MODEL_PATH.exists():
            logger.warning("Training %s model (first run)...", name)
            engine_mod.train()
            report["trained"].append(name)

    if report["seeded"] or report["trained"]:
        logger.warning("Bootstrap complete: %s", report)
    return report
