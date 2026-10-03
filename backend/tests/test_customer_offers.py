"""Regression tests for Change.pdf gap item #7 (trial offers)."""
from datetime import date

import pytest

from app.models import TrialOffer, User


def _generate_pending_offer(client, admin_headers, db_session, institution_id=1):
    target = date.today()
    r = client.post("/api/admin/pipeline/run",
                    json={"institution_id": institution_id, "target_date": target.isoformat()},
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    offer = db_session.query(TrialOffer).filter(
        TrialOffer.institution_id == institution_id,
        TrialOffer.offer_date == target,
        TrialOffer.status == "pending").first()
    return offer, target


def test_pending_offer_not_visible_or_redeemable_before_approval(
        client, admin_headers, login, db_session):
    offer, target = _generate_pending_offer(client, admin_headers, db_session)
    if offer is None:
        pytest.skip("no pending offers were generated today")

    customer = db_session.get(User, offer.customer_id)
    cust_headers = login(customer.email, "user123")

    menu = client.get("/api/customer/menu", headers=cust_headers).json()
    item = next(i for i in menu["items"] if i["dish_id"] == offer.dish_id)
    assert item["offer"] is None, "an unapproved offer must not be shown to the customer"

    r = client.post("/api/customer/orders", headers=cust_headers,
                    json={"items": [{"dish_id": offer.dish_id, "quantity": 1}]})
    assert r.status_code == 200
    assert r.json()["items"][0]["unit_price"] == item["price"], (
        "a pending (unapproved) offer must not be honoured at checkout")


def test_approved_offer_discounts_exactly_one_unit(
        client, admin_headers, kitchen_headers, login, db_session):
    """Audit finding: ordering 15 units of the offer dish discounted all 15;
    the trial incentive must only ever discount the first unit.
    """
    offer, target = _generate_pending_offer(client, admin_headers, db_session)
    if offer is None:
        pytest.skip("no pending offers were generated today")

    r = client.post("/api/kitchen/offers/decide", headers=kitchen_headers,
                    json={"offer_ids": [offer.id], "action": "approve"})
    assert r.status_code == 200, r.text

    customer = db_session.get(User, offer.customer_id)
    cust_headers = login(customer.email, "user123")

    menu = client.get("/api/customer/menu", headers=cust_headers).json()
    item = next(i for i in menu["items"] if i["dish_id"] == offer.dish_id)
    assert item["offer"] is not None

    r = client.post("/api/customer/orders", headers=cust_headers,
                    json={"items": [{"dish_id": offer.dish_id, "quantity": 5}]})
    assert r.status_code == 200, r.text
    order_id = r.json()["order_id"]

    orders = client.get("/api/customer/orders", headers=cust_headers).json()
    order = next(o for o in orders if o["order_id"] == order_id)
    discounted = [i for i in order["items"] if i["discount_applied"] > 0]
    full_price = [i for i in order["items"] if i["discount_applied"] == 0]

    assert len(discounted) == 1
    assert discounted[0]["quantity"] == 1
    assert full_price and full_price[0]["quantity"] == 4
    assert full_price[0]["unit_price"] > discounted[0]["unit_price"]
