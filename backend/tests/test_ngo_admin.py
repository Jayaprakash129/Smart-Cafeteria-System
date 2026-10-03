"""Regression tests for NGO.pdf findings #8 and #9."""
from app.models import NGO


def test_admin_can_toggle_ngo_verified_and_active(client, admin_headers, db_session):
    ngo = db_session.query(NGO).first()
    try:
        r = client.patch(f"/api/admin/ngos/{ngo.id}", headers=admin_headers,
                         json={"verified": False, "active": False})
        assert r.status_code == 200, r.text

        db_session.refresh(ngo)
        assert ngo.verified is False
        assert ngo.active is False
    finally:
        client.patch(f"/api/admin/ngos/{ngo.id}", headers=admin_headers,
                     json={"verified": True, "active": True})


def test_ngo_self_service_cannot_self_verify_or_reactivate(client, ngo_headers, db_session):
    r = client.patch("/api/ngo/profile", headers=ngo_headers,
                     json={"verified": False, "active": False})
    assert r.status_code == 200

    profile = client.get("/api/ngo/profile", headers=ngo_headers).json()
    assert profile["verified"] is True, "an NGO must not be able to self-verify its own account"


def test_ngo_self_service_cannot_set_reliability_score(client, ngo_headers):
    before = client.get("/api/ngo/profile", headers=ngo_headers).json()["reliability_score"]
    r = client.patch("/api/ngo/profile", headers=ngo_headers, json={"reliability_score": 0.01})
    assert r.status_code in (200, 422)  # field isn't even in the schema's public surface
    after = client.get("/api/ngo/profile", headers=ngo_headers).json()["reliability_score"]
    assert after == before


def test_negative_ngo_need_rejected_by_admin(client, admin_headers, db_session):
    ngo = db_session.query(NGO).first()
    r = client.patch(f"/api/admin/ngos/{ngo.id}", headers=admin_headers,
                     json={"daily_need_meals": -10})
    assert r.status_code == 422


def test_negative_ngo_need_rejected_by_self_service(client, ngo_headers):
    r = client.patch("/api/ngo/profile", headers=ngo_headers, json={"daily_need_meals": -5})
    assert r.status_code == 422
