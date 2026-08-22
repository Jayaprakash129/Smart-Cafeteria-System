"""Synthetic Smart Cafeteria dataset generator.

Why synthetic: no public dataset carries the columns this system needs
(unit cost, quantity prepared, quantity leftover, institution segment, NGO
need profiles). The survey paper names synthetic generation as the sanctioned
answer to this gap. Every generative assumption below is explicit and
documented so the dataset is reproducible and defensible rather than magic.

Generative model for daily demand of dish d at institution i on day t:

    demand = base_footfall(i,t)
           * share(d)                 # dish popularity within its category
           * dow_factor(t, segment)   # day-of-week behaviour differs by segment
           * weather_factor(d, t)     # hot days -> cold drinks; rain -> hot snacks
           * season_factor(d, t)      # annual seasonality
           * exam_factor(d, i, t)     # college: snacks up, full meals down
           * trend(d, t)              # slow popularity drift, so trends exist
           * price_effect(d, segment) # segment-specific elasticity
           * noise                    # lognormal multiplicative noise

Preparation deliberately over-shoots demand (kitchens hedge against stockouts),
which is what creates the leftover/waste signal the Waste engine learns.
"""
from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta

import numpy as np
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import SEGMENT_PRICING
from app.database import Base, SessionLocal, engine
from app.models import (
    DailySales, Dish, DishIngredient, Feedback, Ingredient, Institution,
    InventoryItem, NGO, Order, OrderItem, SurplusRecord, User,
)

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

HISTORY_DAYS = 365          # aggregate daily sales history
INDIVIDUAL_ORDER_DAYS = 45  # per-customer order rows (powers trial-conversion)

# --------------------------------------------------------------------------
# Catalogue: (name, category, veg, spice, sweet, unit_cost INR, shelf_life_h,
#             base_share, weather_sensitivity)
# weather_sensitivity: +ve = sells more when hot, -ve = sells more when cold/rainy
# --------------------------------------------------------------------------
DISH_CATALOGUE = [
    ("Idli",                 "breakfast", True,  1, 0, 12.0, 5,  1.00, -0.10),
    ("Masala Dosa",          "breakfast", True,  2, 0, 22.0, 4,  1.20, -0.15),
    ("Ven Pongal",           "breakfast", True,  1, 0, 18.0, 5,  0.70, -0.20),
    ("Medu Vada",            "breakfast", True,  2, 0, 10.0, 4,  0.80, -0.10),
    ("Rava Upma",            "breakfast", True,  1, 0, 14.0, 5,  0.50, -0.10),
    ("Poori Masala",         "breakfast", True,  2, 0, 20.0, 4,  0.60, -0.10),
    ("Chapati Kurma",        "breakfast", True,  2, 0, 19.0, 6,  0.65, -0.05),

    ("South Indian Meals",   "main",      True,  2, 0, 45.0, 5,  1.50,  0.00),
    ("Chicken Biryani",      "main",      False, 3, 0, 78.0, 6,  1.40, -0.05),
    ("Veg Biryani",          "main",      True,  3, 0, 52.0, 6,  1.00, -0.05),
    ("Curd Rice",            "main",      True,  0, 0, 20.0, 4,  0.75,  0.35),
    ("Lemon Rice",           "main",      True,  1, 0, 22.0, 5,  0.60,  0.15),
    ("Sambar Rice",          "main",      True,  2, 0, 24.0, 5,  0.70, -0.10),
    ("Veg Fried Rice",       "main",      True,  2, 0, 38.0, 5,  0.85,  0.00),
    ("Hakka Noodles",        "main",      True,  2, 0, 36.0, 5,  0.80,  0.00),
    ("Paneer Butter Masala", "main",      True,  2, 0, 62.0, 6,  0.70, -0.05),
    ("Chicken Curry Meals",  "main",      False, 3, 0, 85.0, 5,  0.90, -0.05),

    ("Samosa",               "snack",     True,  2, 0,  9.0, 6,  1.10, -0.20),
    ("Onion Bajji",          "snack",     True,  3, 0,  8.0, 4,  0.85, -0.30),
    ("Aloo Bonda",           "snack",     True,  2, 0,  8.5, 4,  0.70, -0.25),
    ("Veg Puff",             "snack",     True,  1, 0, 12.0, 8,  0.95, -0.10),
    ("Grilled Sandwich",     "snack",     True,  1, 0, 26.0, 4,  0.75,  0.05),
    ("Veg Cutlet",           "snack",     True,  2, 0, 14.0, 5,  0.55, -0.15),
    ("Sundal",               "snack",     True,  1, 0,  7.0, 5,  0.45,  0.10),

    ("Filter Coffee",        "beverage",  True,  0, 1,  7.0, 2,  1.60, -0.35),
    ("Masala Tea",           "beverage",  True,  1, 1,  6.0, 2,  1.50, -0.40),
    ("Buttermilk",           "beverage",  True,  0, 0,  8.0, 3,  0.80,  0.55),
    ("Fresh Lime Juice",     "beverage",  True,  0, 2, 10.0, 3,  0.75,  0.60),
    ("Badam Milk",           "beverage",  True,  0, 3, 15.0, 3,  0.50,  0.20),
    ("Sweet Lassi",          "beverage",  True,  0, 3, 16.0, 3,  0.55,  0.45),

    ("Gulab Jamun",          "dessert",   True,  0, 4, 11.0, 8,  0.70,  0.00),
    ("Semiya Payasam",       "dessert",   True,  0, 4, 13.0, 5,  0.45, -0.05),
    ("Vanilla Ice Cream",    "dessert",   True,  0, 3, 18.0, 2,  0.60,  0.70),
    ("Carrot Halwa",         "dessert",   True,  0, 4, 20.0, 6,  0.40, -0.15),
]

INGREDIENTS = [
    ("Rice", "kg", 55.0), ("Urad Dal", "kg", 120.0), ("Toor Dal", "kg", 145.0),
    ("Wheat Flour", "kg", 45.0), ("Semolina", "kg", 48.0), ("Potato", "kg", 30.0),
    ("Onion", "kg", 38.0), ("Tomato", "kg", 34.0), ("Chicken", "kg", 220.0),
    ("Paneer", "kg", 340.0), ("Curd", "kg", 60.0), ("Milk", "l", 54.0),
    ("Cooking Oil", "l", 140.0), ("Sugar", "kg", 45.0), ("Coffee Powder", "kg", 420.0),
    ("Tea Powder", "kg", 300.0), ("Mixed Vegetables", "kg", 42.0), ("Ghee", "kg", 560.0),
    ("Coconut", "kg", 50.0), ("Spice Mix", "kg", 260.0), ("Noodles", "kg", 95.0),
    ("Lemon", "kg", 60.0), ("Carrot", "kg", 40.0), ("Chana", "kg", 90.0),
]

INSTITUTIONS = [
    # name, segment, headcount, participation (fraction eating per day), lat, lon
    ("Zenithra Tech Park Cafeteria", "corporate", 1400, 0.62, 12.9698, 80.2437),
    ("Anna Institute of Technology", "college",   2600, 0.48, 13.0108, 80.2350),
    ("St. Mary's Matriculation School", "school", 1200, 0.71, 13.0836, 80.2101),
]

NGOS = [
    ("Annadhanam Trust",        "R. Lakshmi",   "9840112233", 320, 380, 0.93, False),
    ("Seva Bharathi Chennai",   "K. Murugan",   "9840223344", 240, 300, 0.88, True),
    ("Hope Foundation",         "A. Fathima",   "9840334455", 180, 210, 0.81, False),
    ("Karunai Illam Shelter",   "S. Prakash",   "9840445566", 150, 165, 0.76, True),
    ("Uzhavan Community Kitchen","D. Vetri",    "9840556677", 200, 240, 0.69, False),
]

FIRST_NAMES = ["Arun", "Divya", "Karthik", "Meena", "Rahul", "Sneha", "Vijay", "Priya",
               "Ganesh", "Anitha", "Suresh", "Kavya", "Naveen", "Deepa", "Ashwin",
               "Nithya", "Bharath", "Swathi", "Manoj", "Revathi", "Sanjay", "Harini"]
LAST_NAMES = ["Kumar", "Raj", "Menon", "Iyer", "Nair", "Reddy", "Pillai", "Sharma",
              "Krishnan", "Balaji", "Venkat", "Subramani"]

# 2025-26 style holiday set (month, day)
HOLIDAYS = {(1, 1), (1, 14), (1, 15), (1, 26), (3, 14), (4, 14), (5, 1),
            (8, 15), (9, 5), (10, 2), (10, 20), (10, 21), (11, 1), (12, 25)}


def is_holiday(d: date) -> bool:
    return (d.month, d.day) in HOLIDAYS


def is_exam_period(d: date) -> bool:
    """College exam windows: late April-May and late November-December."""
    return (d.month == 4 and d.day >= 20) or d.month == 5 and d.day <= 15 \
        or (d.month == 11 and d.day >= 20) or (d.month == 12 and d.day <= 10)


def synth_weather(d: date) -> tuple[float, float]:
    """Chennai-like climate: hot Apr-Jun, north-east monsoon Oct-Dec."""
    doy = d.timetuple().tm_yday
    temp = 29.5 + 5.0 * math.sin(2 * math.pi * (doy - 100) / 365) + np.random.normal(0, 1.6)
    monsoon = 1.0 if d.month in (10, 11, 12) else (0.45 if d.month in (6, 7, 8, 9) else 0.12)
    rain = float(np.random.gamma(1.4, 6.0) * monsoon) if random.random() < monsoon * 0.6 else 0.0
    return round(float(temp), 1), round(rain, 1)


def dow_factor(d: date, segment: str) -> float:
    """Attendance rhythm differs by segment; Sunday is closed everywhere."""
    dow = d.weekday()  # 0=Mon
    if dow == 6:
        return 0.0
    if segment == "corporate":
        # Hybrid work: Tue-Thu peak, Friday sharply down, Saturday minimal.
        return [1.02, 1.12, 1.14, 1.05, 0.74, 0.18, 0.0][dow]
    if segment == "college":
        # Steady weekdays, light Saturday.
        return [1.06, 1.05, 1.04, 1.03, 0.98, 0.55, 0.0][dow]
    # school: uniform weekdays, half-day Saturday
    return [1.04, 1.03, 1.03, 1.02, 1.01, 0.62, 0.0][dow]


def build_dishes_for(segment: str) -> list[tuple]:
    """Menu breadth and price positioning vary by segment."""
    if segment == "corporate":
        return DISH_CATALOGUE                     # full premium menu
    if segment == "college":
        return [x for x in DISH_CATALOGUE if x[0] != "Paneer Butter Masala"]
    # School: no non-veg, no coffee/tea, simpler menu
    return [x for x in DISH_CATALOGUE
            if x[2] and x[0] not in ("Filter Coffee", "Masala Tea", "Hakka Noodles",
                                     "Paneer Butter Masala", "Sweet Lassi")]


def price_for(segment: str, unit_cost: float) -> float:
    """Base retail price by segment positioning, always above the cost floor."""
    markup = {"corporate": 2.05, "college": 1.72, "school": 1.48}[segment]
    price = unit_cost * markup
    # Round to a tidy currency step so the UI looks like a real menu board.
    step = 5 if price >= 25 else 1
    return float(max(unit_cost * 1.25, round(price / step) * step))


def reset_database() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def seed_all(verbose: bool = True) -> dict:
    reset_database()
    db: Session = SessionLocal()
    stats: dict[str, int] = {}
    today = date.today()
    start = today - timedelta(days=HISTORY_DAYS)

    # ---------------- Ingredients ----------------
    ing_objs = [Ingredient(name=n, unit=u, cost_per_unit=c) for n, u, c in INGREDIENTS]
    db.add_all(ing_objs)
    db.flush()
    ing_ids = [i.id for i in ing_objs]

    # ---------------- Institutions, dishes, inventory ----------------
    institutions: list[Institution] = []
    for name, segment, headcount, participation, lat, lon in INSTITUTIONS:
        inst = Institution(
            name=name, segment=segment, headcount=headcount,
            latitude=lat, longitude=lon, city="Chennai",
            opening_time="07:30" if segment != "corporate" else "08:00",
            closing_time="17:00" if segment == "school" else "19:00",
        )
        inst.participation = participation  # transient, used below
        db.add(inst)
        institutions.append(inst)
    db.flush()

    all_dishes: dict[int, list[Dish]] = {}
    dish_meta: dict[int, tuple] = {}   # dish_id -> catalogue row
    for inst in institutions:
        rows = build_dishes_for(inst.segment)
        dishes = []
        for (name, cat, veg, spice, sweet, cost, shelf, share, wsens) in rows:
            # Segment-specific cost drift: corporate buys better inputs.
            cost_adj = cost * {"corporate": 1.10, "college": 1.0, "school": 0.88}[inst.segment]
            d = Dish(
                institution_id=inst.id, name=name, category=cat, is_veg=veg,
                spice_level=spice, sweetness=sweet,
                unit_cost=round(cost_adj, 2),
                base_price=price_for(inst.segment, cost_adj),
                shelf_life_hours=shelf,
                popularity_score=round(min(0.99, share / 1.6), 3),
            )
            db.add(d)
            dishes.append(d)
        db.flush()
        for d, row in zip(dishes, rows):
            dish_meta[d.id] = row
        all_dishes[inst.id] = dishes

        # Recipes: 3-5 ingredients per dish
        for d in dishes:
            for iid in random.sample(ing_ids, k=random.randint(3, 5)):
                db.add(DishIngredient(dish_id=d.id, ingredient_id=iid,
                                      quantity=round(random.uniform(0.03, 0.25), 3)))
        # Inventory
        for iid in ing_ids:
            db.add(InventoryItem(
                institution_id=inst.id, ingredient_id=iid,
                quantity_on_hand=round(random.uniform(2, 60), 2),
                reorder_level=round(random.uniform(4, 12), 2),
                expiry_date=today + timedelta(days=random.randint(1, 40)),
            ))
    db.commit()
    stats["dishes"] = sum(len(v) for v in all_dishes.values())

    # ---------------- Users ----------------
    users_to_add = [
        User(email="admin@smartcafeteria.io", full_name="Platform Super Admin",
             hashed_password=hash_password("admin123"), role="super_admin"),
    ]
    for inst in institutions:
        slug = inst.segment
        users_to_add += [
            User(email=f"kitchen.{slug}@smartcafeteria.io",
                 full_name=f"Kitchen Manager - {inst.name}",
                 hashed_password=hash_password("kitchen123"),
                 role="kitchen_manager", institution_id=inst.id),
            User(email=f"coord.{slug}@smartcafeteria.io",
                 full_name=f"Coordinator - {inst.name}",
                 hashed_password=hash_password("coord123"),
                 role="coordinator", institution_id=inst.id),
        ]
    db.add_all(users_to_add)
    db.flush()

    # NGOs + their portal logins
    ngo_objs = []
    for name, contact, phone, need, benef, rel, vegonly in NGOS:
        n = NGO(name=name, contact_person=contact, phone=phone,
                daily_need_meals=need, beneficiaries=benef,
                reliability_score=rel, accepts_veg_only=vegonly,
                latitude=13.0 + random.uniform(-0.09, 0.09),
                longitude=80.23 + random.uniform(-0.09, 0.09))
        db.add(n)
        ngo_objs.append(n)
    db.flush()
    for idx, n in enumerate(ngo_objs, start=1):
        db.add(User(email=f"ngo{idx}@smartcafeteria.io", full_name=n.contact_person,
                    hashed_password=hash_password("ngo123"),
                    role="ngo_partner", ngo_id=n.id))

    # Customers with individual identities -> enables per-customer targeting
    customers: dict[int, list[User]] = {}
    cust_counter = 0
    for inst in institutions:
        n_cust = {"corporate": 160, "college": 220, "school": 120}[inst.segment]
        batch = []
        for _ in range(n_cust):
            cust_counter += 1
            fn = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            u = User(email=f"user{cust_counter}@smartcafeteria.io", full_name=fn,
                     hashed_password=hash_password("user123"), role="customer",
                     institution_id=inst.id,
                     phone=f"98{random.randint(10000000, 99999999)}")
            db.add(u)
            batch.append(u)
        customers[inst.id] = batch
    db.commit()
    stats["users"] = db.query(User).count()
    stats["ngos"] = len(ngo_objs)

    # ---------------- Daily sales history ----------------
    sales_rows: list[dict] = []
    for inst in institutions:
        dishes = all_dishes[inst.id]
        seg = inst.segment
        elasticity = SEGMENT_PRICING[seg]["elasticity"]
        participation = dict((n, p) for n, s, h, p, la, lo in INSTITUTIONS)[inst.name]

        # Per-dish slow popularity drift so the trend engine has something real
        trend_phase = {d.id: random.uniform(0, 2 * math.pi) for d in dishes}
        trend_amp = {d.id: random.uniform(0.05, 0.30) for d in dishes}

        for day_offset in range(HISTORY_DAYS):
            d_date = start + timedelta(days=day_offset)
            dow_f = dow_factor(d_date, seg)
            if dow_f == 0.0:
                continue
            holiday = is_holiday(d_date)
            exam = is_exam_period(d_date) and seg == "college"
            if holiday:
                if seg == "school":
                    continue                    # schools shut on holidays
                dow_f *= 0.25                   # skeleton crew in corporate/college
            temp, rain = synth_weather(d_date)

            footfall = int(inst.headcount * participation * dow_f
                           * np.random.normal(1.0, 0.06))
            footfall = max(20, footfall)

            for dsh in dishes:
                (_, cat, veg, spice, sweet, base_cost, shelf, share, wsens) = dish_meta[dsh.id]

                # --- multiplicative demand model -------------------------
                cat_take = {"breakfast": 0.30, "main": 0.42, "snack": 0.34,
                            "beverage": 0.38, "dessert": 0.14}[cat]

                weather_f = 1.0 + wsens * ((temp - 30.0) / 6.0)
                if rain > 4:
                    # Rain pushes people indoors toward hot snacks and drinks
                    weather_f *= 1.16 if cat in ("snack", "beverage") else 0.94
                weather_f = max(0.45, weather_f)

                doy = d_date.timetuple().tm_yday
                season_f = 1.0 + 0.10 * math.sin(2 * math.pi * (doy + trend_phase[dsh.id]) / 365)

                exam_f = 1.0
                if exam:
                    exam_f = 1.28 if cat in ("snack", "beverage") else 0.80

                t_norm = day_offset / HISTORY_DAYS
                trend_f = 1.0 + trend_amp[dsh.id] * math.sin(
                    2 * math.pi * t_norm + trend_phase[dsh.id])

                # Price effect: actual price wobbles around base, elasticity bites
                price = dsh.base_price * np.random.normal(1.0, 0.035)
                price = max(dsh.unit_cost * 1.2, round(price, 2))
                price_f = (price / dsh.base_price) ** elasticity

                noise = float(np.random.lognormal(0, 0.19))

                demand = (footfall * cat_take * (share / 1.6) * weather_f
                          * season_f * exam_f * trend_f * price_f * noise)
                demand = max(0.0, demand)
                sold = int(round(demand))

                # Kitchens over-prepare to avoid stockouts -> this is the waste
                # signal. Over-preparation is worse for short-shelf-life items.
                hedge = 1.10 + (0.10 if shelf <= 4 else 0.04) + np.random.normal(0, 0.05)
                prepared = int(round(max(sold, demand * max(1.0, hedge))))
                sold = min(sold, prepared)
                leftover = prepared - sold

                sales_rows.append(dict(
                    institution_id=inst.id, dish_id=dsh.id, sales_date=d_date,
                    quantity_prepared=prepared, quantity_sold=sold,
                    quantity_leftover=leftover,
                    unit_price=round(price, 2), unit_cost=dsh.unit_cost,
                    revenue=round(price * sold, 2),
                    temperature_c=temp, rainfall_mm=rain,
                    is_holiday=holiday, is_exam_period=exam,
                    day_of_week=d_date.weekday(), footfall=footfall,
                ))

    db.bulk_insert_mappings(DailySales, sales_rows)
    db.commit()
    stats["daily_sales"] = len(sales_rows)

    # ---------------- Individual orders (recent window) ----------------
    # These give the Trial-Conversion Engine per-customer purchase histories.
    order_rows: list[dict] = []
    item_rows: list[dict] = []
    order_id = 0
    recent_start = today - timedelta(days=INDIVIDUAL_ORDER_DAYS)

    sales_index: dict[tuple, list[dict]] = {}
    for r in sales_rows:
        if r["sales_date"] >= recent_start:
            sales_index.setdefault((r["institution_id"], r["sales_date"]), []).append(r)

    for inst in institutions:
        cust_list = customers[inst.id]
        # Each customer has a persistent taste bias -> repeat purchase patterns
        favourites = {c.id: random.sample([d.id for d in all_dishes[inst.id]],
                                          k=random.randint(3, 6)) for c in cust_list}
        loyalty = {c.id: random.betavariate(2.2, 2.0) for c in cust_list}

        for day_offset in range(INDIVIDUAL_ORDER_DAYS):
            d_date = recent_start + timedelta(days=day_offset)
            day_rows = sales_index.get((inst.id, d_date))
            if not day_rows:
                continue
            price_of = {r["dish_id"]: r["unit_price"] for r in day_rows}
            cost_of = {r["dish_id"]: r["unit_cost"] for r in day_rows}
            available = [r["dish_id"] for r in day_rows if r["quantity_sold"] > 0]
            if not available:
                continue

            for c in cust_list:
                # Probability this customer eats here today
                if random.random() > loyalty[c.id] * 0.85:
                    continue
                order_id += 1
                n_items = random.choices([1, 2, 3], weights=[0.45, 0.40, 0.15])[0]
                # 70% chance of picking from their favourites -> realistic loyalty
                picks = []
                for _ in range(n_items):
                    if random.random() < 0.70:
                        cand = [f for f in favourites[c.id] if f in price_of]
                        picks.append(random.choice(cand) if cand else random.choice(available))
                    else:
                        picks.append(random.choice(available))
                total = 0.0
                for did in set(picks):
                    qty = picks.count(did)
                    up = price_of[did]
                    total += up * qty
                    item_rows.append(dict(order_id=order_id, dish_id=did, quantity=qty,
                                          unit_price=up, unit_cost=cost_of[did],
                                          discount_applied=0.0))
                order_rows.append(dict(
                    id=order_id, institution_id=inst.id, customer_id=c.id,
                    order_date=d_date,
                    placed_at=datetime.combine(d_date, datetime.min.time())
                    + timedelta(hours=random.randint(8, 16), minutes=random.randint(0, 59)),
                    status="completed", total_amount=round(total, 2),
                    channel=random.choices(["counter", "app"], weights=[0.62, 0.38])[0],
                ))

    db.bulk_insert_mappings(Order, order_rows)
    db.bulk_insert_mappings(OrderItem, item_rows)
    db.commit()
    stats["orders"] = len(order_rows)
    stats["order_items"] = len(item_rows)

    # ---------------- Feedback ----------------
    fb_rows = []
    for inst in institutions:
        for dsh in all_dishes[inst.id]:
            share = dish_meta[dsh.id][7]
            for _ in range(random.randint(4, 14)):
                # Popular dishes rate higher, with noise
                mean = 2.9 + 1.4 * min(1.0, share / 1.6)
                rating = int(max(1, min(5, round(np.random.normal(mean, 0.85)))))
                fb_rows.append(dict(
                    institution_id=inst.id, dish_id=dsh.id,
                    customer_id=random.choice(customers[inst.id]).id,
                    rating=rating, comment=None, created_at=datetime.utcnow(),
                ))
    db.bulk_insert_mappings(Feedback, fb_rows)
    db.commit()
    stats["feedback"] = len(fb_rows)

    # ---------------- Today's surplus (for the NGO demo path) -------------
    yesterday = today - timedelta(days=1)
    surplus_rows = []
    for inst in institutions:
        recent = [r for r in sales_rows
                  if r["institution_id"] == inst.id and r["sales_date"] == yesterday
                  and r["quantity_leftover"] > 3]
        for r in recent:
            dsh = next(d for d in all_dishes[inst.id] if d.id == r["dish_id"])
            surplus_rows.append(SurplusRecord(
                institution_id=inst.id, dish_id=r["dish_id"], surplus_date=today,
                quantity=int(r["quantity_leftover"]), unit_cost=r["unit_cost"],
                hours_to_expiry=max(1, dsh.shelf_life_hours - 2),
                is_veg=dsh.is_veg, status="available",
            ))
    db.add_all(surplus_rows)
    db.commit()
    stats["surplus_records"] = len(surplus_rows)

    db.close()
    if verbose:
        print("=== Smart Cafeteria synthetic dataset generated ===")
        for k, v in stats.items():
            print(f"  {k:18s} {v:,}")
    return stats


if __name__ == "__main__":
    seed_all()
