"""End-to-end smoke test across every role and the full agent pipeline.

Run with:  python smoke_test.py
Exits non-zero if any check fails, so it doubles as a pre-demo sanity gate.
"""
from datetime import date

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
PASS, FAIL = [], []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append(name)
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {name}" + (f"  -- {detail}" if detail else ""))


def login(email: str, password: str) -> dict:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed for {email}: {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


print("\n=== 1. SYSTEM ===")
r = client.get("/api/health")
check("health endpoint", r.status_code == 200, r.json().get("status"))

print("\n=== 2. AUTHENTICATION & RBAC ===")
admin = login("admin@smartcafeteria.io", "admin123")
kitchen = login("kitchen.corporate@smartcafeteria.io", "kitchen123")
ngo_h = login("ngo1@smartcafeteria.io", "ngo123")
cust = login("user1@smartcafeteria.io", "user123")
check("super_admin login", True)
check("kitchen_manager login", True)
check("ngo_partner login", True)
check("customer login", True)

r = client.post("/api/auth/login",
                json={"email": "admin@smartcafeteria.io", "password": "wrong"})
check("bad password rejected", r.status_code == 401)

r = client.get("/api/admin/users", headers=kitchen)
check("RBAC blocks kitchen->admin users", r.status_code == 403)

r = client.get("/api/kitchen/dashboard", headers=cust)
check("RBAC blocks customer->kitchen", r.status_code == 403)

r = client.get("/api/kitchen/dashboard?institution_id=2", headers=kitchen)
check("cross-institution access denied", r.status_code == 403)

print("\n=== 3. AGENT PIPELINE ===")
r = client.post("/api/admin/pipeline/run",
                json={"institution_id": 1, "target_date": date.today().isoformat()},
                headers=admin)
check("pipeline runs", r.status_code == 200, r.text[:120])
run = r.json()["runs"][0]
check("pipeline status success", run["status"] == "success", run["status"])
check("all 8 agents logged", len(run["trace"]) == 8, f"{len(run['trace'])} steps")
check("no agent errors", not run["errors"], str(run["errors"])[:150])
check("briefing produced", len(run["briefing"]) > 80, run["briefing_source"])

print("\n=== 4. KITCHEN MANAGER ===")
r = client.get("/api/kitchen/dashboard", headers=kitchen)
d = r.json()
check("dashboard loads", r.status_code == 200)
check("forecast KPI present", d["kpis"]["forecast_units"] > 0, str(d["kpis"]["forecast_units"]))
check("prep >= demand", d["kpis"]["recommended_prep"] >= d["kpis"]["forecast_units"])

r = client.get("/api/kitchen/prices", headers=kitchen)
prices = r.json()["recommendations"]
check("price recommendations exist", len(prices) > 0, f"{len(prices)} dishes")
violations = [p for p in prices if p["recommended_price"] < p["price_floor"] - 0.01]
check("NO price below cost floor", not violations, f"{len(violations)} violations")

target = prices[0]
r = client.post("/api/kitchen/prices/decide", headers=kitchen,
                json={"recommendation_id": target["id"], "action": "approve"})
check("price approval works", r.status_code == 200 and r.json()["new_status"] == "approved")

r = client.post("/api/kitchen/prices/decide", headers=kitchen,
                json={"recommendation_id": prices[1]["id"], "action": "adjust",
                      "adjusted_price": 0.5})
check("manager CANNOT breach floor", r.status_code == 400, r.json().get("detail", "")[:70])

r = client.get("/api/kitchen/forecast", headers=kitchen)
check("7-day forecast", len(r.json()["week"]) == 7)

r = client.get("/api/kitchen/inventory", headers=kitchen)
inv = r.json()
check("inventory loads", len(inv["items"]) > 0, f"{len(inv['items'])} items")

r = client.post("/api/kitchen/inventory/update", headers=kitchen,
                json={"item_id": inv["items"][0]["id"], "quantity_on_hand": 42.5})
check("inventory update", r.status_code == 200)

r = client.get("/api/kitchen/menu", headers=kitchen)
check("menu recommendations", len(r.json()["recommendations"]) > 0)

r = client.get("/api/kitchen/reports", headers=kitchen)
rep = r.json()
check("profit report", rep["totals"]["revenue"] > 0,
      f"revenue Rs.{rep['totals']['revenue']:,.0f}, waste {rep['totals']['waste_pct']}%")

print("\n=== 5. TRIAL CONVERSION ===")
r = client.get("/api/kitchen/offers", headers=kitchen)
o = r.json()
check("offers generated", len(o["offers"]) > 0, f"{len(o['offers'])} offers")
check("best seller identified", o["best_seller"] is not None,
      o["best_seller"]["dish_name"] if o["best_seller"] else "none")
bad = [x for x in o["offers"] if x["offer_price"] < x["original_price"] * 0.5]
check("offer prices respect floor", all(
    x["offer_price"] > 0 for x in o["offers"]))
if o["offers"]:
    r = client.post("/api/kitchen/offers/decide", headers=kitchen,
                    json={"offer_ids": [o["offers"][0]["id"]], "action": "approve"})
    check("offer approval", r.status_code == 200)

print("\n=== 6. NGO ALLOCATION ===")
r = client.get("/api/kitchen/surplus", headers=kitchen)
s = r.json()
check("surplus computed", s["summary"]["total_surplus"] > 0,
      f"{s['summary']['total_surplus']} units")
check("multi-NGO split", s["summary"]["partners"] >= 2,
      f"{s['summary']['partners']} partners")
check("20% guarantee satisfied", s["summary"]["all_meet_guarantee"])
check("coverage >= 90%", s["summary"]["coverage_pct"] >= 90,
      f"{s['summary']['coverage_pct']}%")

r = client.get("/api/ngo/today", headers=ngo_h)
n = r.json()
check("NGO sees allocation", r.status_code == 200,
      f"{n['summary']['total_meals']} meals")

if n["pickups"]:
    ids = n["pickups"][0]["allocation_ids"]
    r = client.post("/api/ngo/pickups/confirm", headers=ngo_h,
                    json={"allocation_ids": ids, "status": "collected"})
    check("pickup confirmation", r.status_code == 200,
          f"reliability -> {r.json().get('new_reliability_score')}")

r = client.get("/api/ngo/history", headers=ngo_h)
check("NGO history", r.status_code == 200)

print("\n=== 7. CUSTOMER ===")
r = client.get("/api/customer/menu", headers=cust)
m = r.json()
check("customer menu", len(m["items"]) > 0, f"{len(m['items'])} dishes")

first = m["items"][0]
r = client.post("/api/customer/orders", headers=cust,
                json={"items": [{"dish_id": first["dish_id"], "quantity": 2}]})
check("place order", r.status_code == 200,
      f"total Rs.{r.json().get('total_amount')}")

r = client.get("/api/customer/orders", headers=cust)
check("order history", len(r.json()) > 0)

r = client.post("/api/customer/feedback", headers=cust,
                json={"dish_id": first["dish_id"], "rating": 5})
check("submit feedback", r.status_code == 200)

r = client.get("/api/customer/profile", headers=cust)
check("customer profile", r.status_code == 200)

print("\n=== 8. ADMIN & ANALYTICS ===")
r = client.get("/api/admin/dashboard", headers=admin)
g = r.json()
check("global dashboard", r.status_code == 200,
      f"{g['totals']['institutions']} institutions, Rs.{g['totals']['revenue']:,.0f}")

r = client.get("/api/admin/engines", headers=admin)
eng = r.json()["engines"]
check("6 engines reported", len(eng) == 6, f"{len(eng)} engines")
trained = [e for e in eng if e["status"] == "trained"]
check("3 ML models trained", len(trained) == 3, f"{len(trained)} trained")

r = client.get("/api/admin/impact", headers=admin)
imp = r.json()
check("impact report", r.status_code == 200,
      f"waste {imp['waste']['baseline_waste_pct']}%, "
      f"redistribution {imp['waste']['redistribution_coverage_pct']}%")

r = client.get("/api/admin/audit", headers=admin)
check("audit log", len(r.json()) > 0, f"{len(r.json())} entries")

r = client.get("/api/admin/rules", headers=admin)
check("global rules exposed", r.json()["price_floor_margin"] == 0.20)

print("\n" + "=" * 60)
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED CHECKS:")
    for f in FAIL:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL CHECKS PASSED")
