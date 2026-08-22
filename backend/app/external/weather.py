"""Open-Meteo weather integration.

The only genuinely external live data source in the system. Free, keyless, and
documented, which is why it was chosen over commercial weather APIs.

Weather matters to this project measurably: in the operating dataset, cold
beverages sell roughly 3x more on days above 32C than below 28C, while hot
beverages invert that ratio. The forecasting engine consumes temperature and
rainfall directly as features.

Falls back to a seasonal climatological estimate when the network is
unavailable, so a demo never depends on connectivity. The source is always
reported so the UI can show whether a number is live or estimated.
"""
from __future__ import annotations

import math
from datetime import date

import httpx

from app.config import OPEN_METEO_URL

_cache: dict[tuple, dict] = {}


def _climatology(lat: float, target: date) -> dict:
    """Seasonal fallback tuned to coastal South-Indian conditions."""
    doy = target.timetuple().tm_yday
    temp = 29.5 + 5.0 * math.sin(2 * math.pi * (doy - 100) / 365)
    rain = 6.0 if target.month in (10, 11, 12) else (2.5 if target.month in (6, 7, 8, 9) else 0.4)
    return {
        "temperature_c": round(temp, 1),
        "rainfall_mm": round(rain, 1),
        "humidity_pct": 74.0,
        "source": "climatology-fallback",
        "date": target.isoformat(),
    }


def get_forecast(latitude: float, longitude: float, target: date) -> dict:
    """Daily weather for one location and date, with graceful degradation."""
    key = (round(latitude, 2), round(longitude, 2), target.isoformat())
    if key in _cache:
        return _cache[key]

    try:
        r = httpx.get(OPEN_METEO_URL, params={
            "latitude": latitude, "longitude": longitude,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "timezone": "auto",
            "start_date": target.isoformat(), "end_date": target.isoformat(),
        }, timeout=6.0)
        r.raise_for_status()
        d = r.json()["daily"]
        tmax, tmin = d["temperature_2m_max"][0], d["temperature_2m_min"][0]
        out = {
            "temperature_c": round((tmax + tmin) / 2, 1),
            "temperature_max_c": tmax,
            "temperature_min_c": tmin,
            "rainfall_mm": round(d["precipitation_sum"][0] or 0.0, 1),
            "source": "open-meteo",
            "date": target.isoformat(),
        }
    except Exception:
        out = _climatology(latitude, target)

    _cache[key] = out
    return out
