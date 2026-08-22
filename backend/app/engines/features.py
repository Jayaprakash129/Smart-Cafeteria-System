"""Shared feature engineering for the forecasting and waste engines.

Both engines consume the same panel (institution x dish x day), so the lag /
rolling features are built once here and reused. Lags are computed strictly
from *past* rows within each (institution, dish) series, which is what keeps
the time-based evaluation honest rather than leaking future information.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import create_engine

from app.config import DATABASE_URL

BASE_FEATURES = [
    "day_of_week", "month", "is_weekend", "temperature_c", "rainfall_mm",
    "is_holiday", "is_exam_period", "footfall", "unit_price", "unit_cost",
    "price_ratio", "shelf_life_hours", "spice_level", "sweetness", "is_veg",
    "popularity_score", "segment_code", "category_code",
    "lag_1", "lag_7", "roll_7", "roll_28", "roll_std_7", "leftover_roll_7",
]

CATEGORY_CODES = {"breakfast": 0, "main": 1, "snack": 2, "beverage": 3, "dessert": 4}
SEGMENT_CODES = {"corporate": 0, "college": 1, "school": 2}


def load_panel(db_url: str = DATABASE_URL) -> pd.DataFrame:
    """Load the joined sales panel with dish and institution attributes."""
    engine = create_engine(db_url)
    query = """
        SELECT s.*, d.name AS dish_name, d.category, d.cuisine, d.is_veg,
               d.spice_level, d.sweetness, d.shelf_life_hours,
               d.popularity_score, d.base_price,
               i.segment, i.name AS institution_name, i.headcount
        FROM daily_sales s
        JOIN dishes d ON d.id = s.dish_id
        JOIN institutions i ON i.id = s.institution_id
    """
    df = pd.read_sql(query, engine)
    df["sales_date"] = pd.to_datetime(df["sales_date"])
    return df.sort_values(["institution_id", "dish_id", "sales_date"]).reset_index(drop=True)


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Attach calendar, encoding and lag/rolling features to the panel."""
    df = df.copy()
    df["month"] = df["sales_date"].dt.month
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    df["is_holiday"] = df["is_holiday"].astype(int)
    df["is_exam_period"] = df["is_exam_period"].astype(int)
    df["is_veg"] = df["is_veg"].astype(int)
    df["segment_code"] = df["segment"].map(SEGMENT_CODES).fillna(0).astype(int)
    df["category_code"] = df["category"].map(CATEGORY_CODES).fillna(0).astype(int)
    df["price_ratio"] = df["unit_price"] / df["base_price"].replace(0, 1)

    grp = df.groupby(["institution_id", "dish_id"], sort=False)["quantity_sold"]
    df["lag_1"] = grp.shift(1)
    df["lag_7"] = grp.shift(7)
    # shift(1) before rolling so today's own value never enters its own feature
    df["roll_7"] = grp.shift(1).rolling(7, min_periods=1).mean().reset_index(drop=True)
    df["roll_28"] = grp.shift(1).rolling(28, min_periods=1).mean().reset_index(drop=True)
    df["roll_std_7"] = grp.shift(1).rolling(7, min_periods=2).std().reset_index(drop=True)

    lgrp = df.groupby(["institution_id", "dish_id"], sort=False)["quantity_leftover"]
    df["leftover_roll_7"] = lgrp.shift(1).rolling(7, min_periods=1).mean().reset_index(drop=True)

    # Cold-start rows fall back to the series mean rather than being dropped.
    for col in ["lag_1", "lag_7", "roll_7", "roll_28", "leftover_roll_7"]:
        df[col] = df[col].fillna(df.groupby(["institution_id", "dish_id"])["quantity_sold"]
                                 .transform("mean"))
    df["roll_std_7"] = df["roll_std_7"].fillna(0.0)
    return df.fillna(0.0)


def build_training_frame() -> pd.DataFrame:
    return add_features(load_panel())
