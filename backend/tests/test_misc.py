"""Smaller regression checks: forecast performance refactor and fairness
reporting (NGO.pdf finding #13)."""
import time

from app.engines import forecasting
from app.engines.ngo_allocation import fairness_report


def test_forecast_week_returns_seven_days_and_is_reasonably_fast(db_session):
    """Change.pdf #13: forecast_week used to reload the model and rebuild
    the full feature panel on every one of its 7 iterations. It should now
    do that once. Not a strict timing assertion (sandboxes vary), just a
    generous upper bound that would catch a regression back to ~7x cost.
    """
    t0 = time.perf_counter()
    week = forecasting.forecast_week(1)
    elapsed = time.perf_counter() - t0
    assert len(week) == 7
    assert all("dishes" in day for day in week)
    assert elapsed < 10.0, f"forecast_week took {elapsed:.1f}s, expected roughly 1 day's worth of work"


def test_fairness_report_counts_ngos_with_zero_allocations(client, admin_headers, db_session):
    """NGO.pdf finding #13: an NGO that received nothing in the window
    disappeared from the Gini calculation entirely, flattering the score.
    """
    from app.models import NGO

    client.post("/api/admin/pipeline/run", json={}, headers=admin_headers)
    report = fairness_report(db_session, days=30)
    active_ngo_count = db_session.query(NGO).filter(
        NGO.active == True, NGO.verified == True).count()  # noqa: E712
    assert report["active_partners"] == active_ngo_count
    assert len(report["partners"]) == active_ngo_count
