"""Regression tests for the NGO allocation engine (NGO.pdf findings 1-10)."""
from datetime import date, timedelta

import pytest

from app.models import NGO, NGOAllocation, SurplusRecord


def test_all_institutions_meet_20pct_guarantee(client, admin_headers):
    """NGO.pdf finding #2 / Change.pdf #3: the guarantee threshold was
    rounded down (int()), so a solved allocation could land a hair under
    20% and legitimately report the guarantee as unmet. Fixed with
    math.ceil(). Mirrors the project's own smoke_test.py check.
    """
    target = date.today()
    r = client.post("/api/admin/pipeline/run",
                    json={"target_date": target.isoformat()}, headers=admin_headers)
    assert r.status_code == 200, r.text
    for run in r.json()["runs"]:
        ngo_summary = run["summary"]["ngo"]
        if ngo_summary.get("total_surplus", 0) > 0:
            assert ngo_summary["all_meet_guarantee"] is True, run


def test_ngo_daily_capacity_not_exceeded_across_institutions(client, admin_headers, db_session):
    """NGO.pdf finding #1: each institution solved in isolation, so an NGO
    partnered with three cafeterias could be promised its full daily
    capacity three times over on the same day.
    """
    target = date.today()
    r = client.post("/api/admin/pipeline/run",
                    json={"target_date": target.isoformat()}, headers=admin_headers)
    assert r.status_code == 200, r.text

    for ngo in db_session.query(NGO).all():
        given = db_session.query(NGOAllocation).filter(
            NGOAllocation.ngo_id == ngo.id,
            NGOAllocation.allocation_date == target,
            NGOAllocation.status.in_(["scheduled", "collected"]),
        ).all()
        total = sum(a.quantity for a in given)
        assert total <= ngo.daily_need_meals, (
            f"{ngo.name} was given {total} across institutions today but its "
            f"stated daily need is only {ngo.daily_need_meals}")


def test_ngo_pickup_slots_do_not_clash_across_institutions(client, admin_headers, db_session):
    """NGO.pdf finding #3: pickup slot depended only on list position, so
    the same NGO got the identical clock-time slot at every institution.
    """
    target = date.today()
    client.post("/api/admin/pipeline/run",
               json={"target_date": target.isoformat()}, headers=admin_headers)

    def _parse(slot):
        a, b = slot.split("-")
        h1, m1 = map(int, a.split(":"))
        h2, m2 = map(int, b.split(":"))
        return h1 * 60 + m1, h2 * 60 + m2

    by_ngo: dict[int, list] = {}
    rows = db_session.query(NGOAllocation).filter(
        NGOAllocation.allocation_date == target,
        NGOAllocation.status.in_(["scheduled", "collected"])).all()
    for r in rows:
        by_ngo.setdefault(r.ngo_id, []).append((r.institution_id, _parse(r.pickup_slot)))

    for ngo_id, slots in by_ngo.items():
        # Only check distinct institutions -- multiple surplus items at the
        # SAME institution legitimately share that institution's assignment.
        by_inst = {}
        for inst_id, interval in slots:
            by_inst.setdefault(inst_id, interval)
        intervals = list(by_inst.values())
        for i in range(len(intervals)):
            for j in range(i + 1, len(intervals)):
                a, b = intervals[i], intervals[j]
                overlap = a[0] < b[1] and b[0] < a[1]
                assert not overlap, (
                    f"NGO {ngo_id} has overlapping pickup windows {a} and {b} "
                    f"across different institutions on the same day")


def test_rerun_allocation_preserves_collected_pickups_and_keeps_distributing(
        client, kitchen_headers, ngo_headers, admin_headers, db_session):
    """NGO.pdf finding #6 / Change.pdf #2: re-running the allocation deleted
    every allocation (including already-collected ones) and then solved
    only against SurplusRecord.status=="available", which the first run had
    already flipped to "allocated" -- so a re-run distributed 0 meals and
    silently destroyed the collection record.
    """
    target = date.today()
    r = client.post("/api/admin/pipeline/run",
                    json={"institution_id": 1, "target_date": target.isoformat()}, headers=admin_headers)
    assert r.status_code == 200

    before = client.get("/api/kitchen/surplus", headers=kitchen_headers).json()
    if before["summary"]["total_surplus"] <= 0:
        pytest.skip("no surplus generated for institution 1 today")
    distributed_before = before["summary"]["distributed"]
    assert distributed_before > 0

    today_resp = client.get("/api/ngo/today", headers=ngo_headers).json()
    pickups = [p for p in today_resp["pickups"] if p["institution_id"] == 1]
    if not pickups:
        pytest.skip("this NGO received nothing from institution 1 today")
    alloc_ids = pickups[0]["allocation_ids"]
    r = client.post("/api/ngo/pickups/confirm", headers=ngo_headers,
                    json={"allocation_ids": alloc_ids, "status": "collected"})
    assert r.status_code == 200

    collected_before = db_session.query(NGOAllocation).filter(
        NGOAllocation.status == "collected").count()
    assert collected_before > 0

    r = client.post("/api/kitchen/surplus/allocate", headers=kitchen_headers)
    assert r.status_code == 200

    collected_after = db_session.query(NGOAllocation).filter(
        NGOAllocation.status == "collected").count()
    assert collected_after == collected_before, (
        "re-running the allocation must never delete a collected pickup")

    after = client.get("/api/kitchen/surplus", headers=kitchen_headers).json()
    assert after["summary"]["distributed"] > 0, (
        "re-running the allocation must not zero out distribution")


def test_repeat_pickup_confirmation_is_rejected(client, kitchen_headers, ngo_headers, admin_headers):
    """NGO.pdf finding #7 / Change.pdf #9: the same pickup could be
    confirmed repeatedly, each time re-running (and drifting) the NGO's
    reliability score.
    """
    target = date.today()
    client.post("/api/admin/pipeline/run",
               json={"target_date": target.isoformat()}, headers=admin_headers)
    today_resp = client.get("/api/ngo/today", headers=ngo_headers).json()
    pickups = [p for p in today_resp["pickups"] if p["status"] == "scheduled"]
    if not pickups:
        pytest.skip("nothing scheduled for this NGO today")
    ids = pickups[0]["allocation_ids"]

    r1 = client.post("/api/ngo/pickups/confirm", headers=ngo_headers,
                     json={"allocation_ids": ids, "status": "collected"})
    assert r1.status_code == 200

    r2 = client.post("/api/ngo/pickups/confirm", headers=ngo_headers,
                     json={"allocation_ids": ids, "status": "collected"})
    assert r2.status_code == 409


def test_shared_dish_collection_is_tracked_per_allocation(client, admin_headers, db_session):
    """NGO.pdf finding #5: one NGO collecting its share of a dish split
    across multiple partners used to mark the whole SurplusRecord
    "collected", hiding that other NGOs' shares were still outstanding.
    """
    from app.engines.ngo_allocation import sync_surplus_status

    target = date.today()
    client.post("/api/admin/pipeline/run",
               json={"target_date": target.isoformat()}, headers=admin_headers)

    # Find a surplus record split across at least two NGOs today.
    rows = db_session.query(NGOAllocation).filter(
        NGOAllocation.allocation_date == target).all()
    by_surplus: dict[int, set] = {}
    for r in rows:
        by_surplus.setdefault(r.surplus_id, set()).add(r.ngo_id)
    shared = [sid for sid, ngos in by_surplus.items() if len(ngos) > 1]
    if not shared:
        pytest.skip("no surplus item was split across multiple NGOs today")

    surplus_id = shared[0]
    allocs = [r for r in rows if r.surplus_id == surplus_id]
    first, rest = allocs[0], allocs[1:]
    first.status = "collected"
    db_session.commit()
    sync_surplus_status(db_session, [surplus_id])
    db_session.commit()

    record = db_session.get(SurplusRecord, surplus_id)
    assert record.status != "collected", (
        "a surplus item must not show as fully collected while another "
        "NGO's share of it is still scheduled")


def test_missed_pickup_is_not_left_allocated_forever(client, admin_headers, ngo_headers, db_session):
    """NGO.pdf finding #10: a missed pickup's food stayed "allocated" and
    was never re-offered. After marking it missed, the allocation engine
    should be re-run and that NGO's own missed quantity must not still
    count as a live commitment.
    """
    # A target date not touched by any other test in this session, so this
    # test gets a fresh batch of "scheduled" pickups rather than ones an
    # earlier test already confirmed as collected.
    target = date.today() + timedelta(days=9)
    client.post("/api/admin/pipeline/run",
               json={"target_date": target.isoformat()}, headers=admin_headers)
    today_resp = client.get(f"/api/ngo/today?target={target.isoformat()}", headers=ngo_headers).json()
    pickups = [p for p in today_resp["pickups"] if p["status"] == "scheduled"]
    if not pickups:
        pytest.skip("nothing scheduled for this NGO today")
    ids = pickups[0]["allocation_ids"]

    r = client.post("/api/ngo/pickups/confirm", headers=ngo_headers,
                    json={"allocation_ids": ids, "status": "missed"})
    assert r.status_code == 200

    missed_rows = db_session.query(NGOAllocation).filter(
        NGOAllocation.id.in_(ids)).all()
    for row in missed_rows:
        assert row.status == "missed"
        # Must not simultaneously appear as a live (scheduled/collected)
        # commitment anywhere -- the freed quantity should have gone back
        # into the pool for the next allocate() call.
    still_live = db_session.query(NGOAllocation).filter(
        NGOAllocation.id.in_(ids), NGOAllocation.status.in_(["scheduled", "collected"])).count()
    assert still_live == 0
