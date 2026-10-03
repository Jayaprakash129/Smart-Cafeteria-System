"""Regression tests for Change.pdf gap items #5, #6, #10."""


# --------------------------------------------------------------------------
# #6 - cross-institution reads
# --------------------------------------------------------------------------
def test_kitchen_manager_cannot_read_global_dashboard(client, kitchen_headers):
    r = client.get("/api/admin/dashboard", headers=kitchen_headers)
    assert r.status_code == 403


def test_coordinator_cannot_read_global_dashboard(client, coordinator_headers):
    r = client.get("/api/admin/dashboard", headers=coordinator_headers)
    assert r.status_code == 403


def test_coordinator_cannot_read_institutions_directory(client, coordinator_headers):
    r = client.get("/api/admin/institutions", headers=coordinator_headers)
    assert r.status_code == 403


def test_coordinator_cannot_read_ngo_directory(client, coordinator_headers):
    r = client.get("/api/admin/ngos", headers=coordinator_headers)
    assert r.status_code == 403


def test_super_admin_can_still_read_cross_institution_pages(client, admin_headers):
    assert client.get("/api/admin/dashboard", headers=admin_headers).status_code == 200
    assert client.get("/api/admin/institutions", headers=admin_headers).status_code == 200
    assert client.get("/api/admin/ngos", headers=admin_headers).status_code == 200


def test_kitchen_manager_impact_is_scoped_to_own_institution(client, kitchen_headers, admin_headers):
    me = client.get("/api/auth/me", headers=kitchen_headers).json()
    own_id = me["institution"]["id"]
    insts = client.get("/api/admin/institutions", headers=admin_headers).json()
    other = next(i["id"] for i in insts if i["id"] != own_id)

    r_own = client.get("/api/admin/impact", headers=kitchen_headers)
    assert r_own.status_code == 200

    r_other = client.get(f"/api/admin/impact?institution_id={other}", headers=kitchen_headers)
    assert r_other.status_code == 403


def test_kitchen_manager_audit_log_is_scoped_to_own_institution(
        client, kitchen_headers, admin_headers):
    me = client.get("/api/auth/me", headers=kitchen_headers).json()
    own_name = me["institution"]["name"]
    own_id = me["institution"]["id"]
    insts = client.get("/api/admin/institutions", headers=admin_headers).json()
    other = next(i["id"] for i in insts if i["id"] != own_id)

    r_other = client.get(f"/api/admin/audit?institution_id={other}", headers=kitchen_headers)
    assert r_other.status_code == 403

    # Generate at least one entry for this institution, then make sure the
    # unfiltered call (no institution_id passed at all) still only shows
    # this caller's own institution, not every institution on the platform.
    client.post("/api/admin/pipeline/run", json={"institution_id": own_id}, headers=kitchen_headers)
    r_own = client.get("/api/admin/audit?limit=500", headers=kitchen_headers)
    assert r_own.status_code == 200
    rows = r_own.json()
    assert rows
    assert all(row["institution"] in (own_name, None) for row in rows)


def test_super_admin_impact_platform_wide_without_institution_id(client, admin_headers):
    r = client.get("/api/admin/impact", headers=admin_headers)
    assert r.status_code == 200


# --------------------------------------------------------------------------
# #5 - demo-accounts gating
# --------------------------------------------------------------------------
def test_demo_accounts_available_when_demo_mode_enabled(client):
    r = client.get("/api/auth/demo-accounts")
    assert r.status_code == 200


def test_demo_accounts_gated_when_demo_mode_disabled(client, monkeypatch):
    import app.routers.auth_router as auth_router
    monkeypatch.setattr(auth_router, "DEMO_MODE", False)
    r = client.get("/api/auth/demo-accounts")
    assert r.status_code == 404


# --------------------------------------------------------------------------
# #10 - input validation
# --------------------------------------------------------------------------
def test_order_quantity_above_bound_is_rejected(client, login):
    headers = login("user1@smartcafeteria.io", "user123")
    menu = client.get("/api/customer/menu", headers=headers).json()
    dish_id = menu["items"][0]["dish_id"]
    r = client.post("/api/customer/orders", headers=headers,
                    json={"items": [{"dish_id": dish_id, "quantity": 1000000}]})
    assert r.status_code == 422


def test_negative_inventory_quantity_is_rejected(client, kitchen_headers):
    inv = client.get("/api/kitchen/inventory", headers=kitchen_headers).json()
    item_id = inv["items"][0]["id"]
    r = client.post("/api/kitchen/inventory/update", headers=kitchen_headers,
                    json={"item_id": item_id, "quantity_on_hand": -50})
    assert r.status_code == 422


def test_create_user_password_too_short_is_rejected(client, admin_headers):
    r = client.post("/api/admin/users", headers=admin_headers,
                    json={"email": "short1@test.com", "full_name": "x",
                          "password": "123", "role": "customer"})
    assert r.status_code == 422


def test_create_user_bad_email_format_is_rejected(client, admin_headers):
    r = client.post("/api/admin/users", headers=admin_headers,
                    json={"email": "not-an-email", "full_name": "x",
                          "password": "longenough", "role": "customer"})
    assert r.status_code == 422


def test_create_user_invalid_role_is_rejected(client, admin_headers):
    r = client.post("/api/admin/users", headers=admin_headers,
                    json={"email": "wizard@test.com", "full_name": "x",
                          "password": "longenough", "role": "wizard"})
    assert r.status_code == 422


def test_create_user_duplicate_email_is_case_insensitive(client, admin_headers):
    payload = {"email": "Dup.Case@Test.com", "full_name": "x",
              "password": "longenough", "role": "customer"}
    r1 = client.post("/api/admin/users", headers=admin_headers, json=payload)
    assert r1.status_code == 200, r1.text

    r2 = client.post("/api/admin/users", headers=admin_headers,
                     json={**payload, "email": "dup.case@test.com"})
    assert r2.status_code == 409
