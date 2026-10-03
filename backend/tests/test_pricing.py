"""Regression tests for the pricing engine (Change.pdf gap items #1 and #8)."""
from datetime import date, timedelta


def test_price_does_not_ratchet_upward_across_daily_approvals(client, kitchen_headers, admin_headers):
    """Audit finding: approving a recommendation every day compounded the
    price by ~45%/day because the segment band was anchored to the live
    (manager-mutated) base_price. It must now be anchored to the dish's
    fixed reference_price, so repeated approvals stay within a stable band.
    """
    institution_id = 1
    dish_id = None
    recommended_sequence = []

    for offset in range(4):
        target = date.today() + timedelta(days=offset)
        r = client.post("/api/admin/pipeline/run",
                        json={"institution_id": institution_id, "target_date": target.isoformat()},
                        headers=admin_headers)
        assert r.status_code == 200, r.text

        prices = client.get(f"/api/kitchen/prices?target={target.isoformat()}",
                            headers=kitchen_headers).json()["recommendations"]
        assert prices
        if dish_id is None:
            dish_id = prices[0]["dish_id"]
        rec = next(p for p in prices if p["dish_id"] == dish_id)
        recommended_sequence.append(rec["recommended_price"])

        r = client.post("/api/kitchen/prices/decide", headers=kitchen_headers,
                        json={"recommendation_id": rec["id"], "action": "approve"})
        assert r.status_code == 200, r.text

    growth = (recommended_sequence[-1] - recommended_sequence[0]) / recommended_sequence[0]
    assert growth < 0.10, (
        f"price ratcheted {growth:.1%} over {len(recommended_sequence)} daily "
        f"approvals: {recommended_sequence}")


def test_manual_price_adjustment_rejects_below_floor(client, kitchen_headers, admin_headers):
    target = date.today()
    client.post("/api/admin/pipeline/run",
                json={"institution_id": 1, "target_date": target.isoformat()}, headers=admin_headers)
    prices = client.get("/api/kitchen/prices", headers=kitchen_headers).json()["recommendations"]
    rec = prices[0]
    r = client.post("/api/kitchen/prices/decide", headers=kitchen_headers,
                    json={"recommendation_id": rec["id"], "action": "adjust", "adjusted_price": 0.5})
    assert r.status_code == 400


def test_manual_price_adjustment_rejects_above_segment_ceiling(client, kitchen_headers, admin_headers):
    """Audit finding: only the floor was checked on manual adjustment, so an
    arbitrary high price (e.g. Rs.9,99,999) was silently accepted.
    """
    target = date.today()
    client.post("/api/admin/pipeline/run",
                json={"institution_id": 1, "target_date": target.isoformat()}, headers=admin_headers)
    prices = client.get("/api/kitchen/prices", headers=kitchen_headers).json()["recommendations"]
    rec = prices[0]
    r = client.post("/api/kitchen/prices/decide", headers=kitchen_headers,
                    json={"recommendation_id": rec["id"], "action": "adjust",
                          "adjusted_price": 999999})
    assert r.status_code == 400
