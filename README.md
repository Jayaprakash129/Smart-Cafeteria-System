# Smart Cafeteria System

AI-driven demand forecasting, segment-aware dynamic pricing, waste prevention and
equitable multi-NGO surplus redistribution for institutional cafeterias.

Implements the architecture in `DOCS/` (the 2026-08-19 FastAPI/agentic design) as a
working, verifiable system: 3 trained ML models, a constrained optimiser, a
7-agent orchestration pipeline, a 40-endpoint REST API with role-based access
control, and a React dashboard covering all five roles.

---

## Quick start

Requires **Python 3.10+** (the models use `X | None` type-hint syntax) and
**Node 20+**. Run both commands below from the repository root, in two
terminals.

**Terminal 1 — backend**

```bash
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && python -m uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — frontend**

```bash
cd frontend && npm install && npm run dev
```

Open **http://localhost:5173**. API docs at **http://localhost:8000/docs**.

If the database is missing or you want a clean slate:

```bash
cd backend && python -m app.seed && python -c "from app.engines import forecasting,waste,trial_conversion; forecasting.train(); waste.train(); trial_conversion.train()"
```

Verify everything works (48 checks):

```bash
cd backend && python smoke_test.py
```

Run the automated regression suite (isolated temp database, never touches
the data above — see `backend/tests/`):

```bash
cd backend && pip install pytest && python -m pytest tests/ -v
```

### Configuration

Sensible defaults are built in for local/demo use; override any of these via
environment variables for anything beyond that:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///backend/data/smart_cafeteria.db` | SQLAlchemy connection string (Postgres-swappable) |
| `MODEL_DIR` | `backend/models_store` | Where trained `.joblib` models are read/written |
| `JWT_SECRET` | a fixed demo string | **Set this in any shared or production deployment** |
| `DEMO_MODE` | `true` | Gates `GET /api/auth/demo-accounts`, which otherwise lists every role's password unauthenticated. Set to `false` outside local demo use |

---

## Demo accounts

| Role | Email | Password |
|---|---|---|
| Kitchen Manager (corporate) | `kitchen.corporate@smartcafeteria.io` | `kitchen123` |
| Kitchen Manager (college) | `kitchen.college@smartcafeteria.io` | `kitchen123` |
| Super Admin | `admin@smartcafeteria.io` | `admin123` |
| NGO Partner | `ngo1@smartcafeteria.io` | `ngo123` |
| Coordinator | `coord.corporate@smartcafeteria.io` | `coord123` |
| Customer **with a live offer** | `user127@smartcafeteria.io` | `user123` |

The login screen has one-click buttons for each role.

---

## Suggested demo route (8 minutes)

1. **Kitchen Manager → Today's Dashboard.** Click **▶ Run daily pipeline**. All
   seven agents execute in ~3 seconds and a briefing appears. Point out the agent
   trace: live weather → forecast → waste → pricing → menu → offers → NGO.
2. **Menu & Pricing.** Try **Adjust** on any dish and enter a below-cost price —
   the server rejects it. *The floor binds the human, not just the algorithm.*
3. **Trial Offers.** Show the funnel: visitors yesterday → who bought the best
   seller → who didn't. Only the non-buyers get discounted.
4. **Surplus & NGO.** Four partners, all meeting the 20% guarantee, 100% coverage.
   Note that veg-only NGOs receive only 🟢 items — a hard dietary constraint.
5. **NGO Partner login.** Same allocation from the recipient's side; confirm a
   pickup and watch the reliability score update.
6. **Customer login** (`user127`) — the personalised offer banner appears on the
   menu; place an order and the discount applies automatically.
7. **Super Admin → Engines** for live model metrics, **→ Impact** for the headline
   numbers, **→ Audit Log** for every decision the system made.

---

## Measured results

All figures produced by `smoke_test.py` and `/api/admin/impact` against the
generated dataset (365 days, 3 institutions, 29,044 daily sales rows).

| Metric | Value | Why it matters |
|---|---|---|
| Forecast R² (held-out) | **0.866** | 30-day time-based holdout, no leakage |
| Forecast MAPE | **18.9%** | per-dish daily demand |
| **Improvement over naive baseline** | **39.7%** | vs rolling 7-day mean — the heuristic a real cafeteria uses |
| Waste model R² | **0.847** | leftover units, Random Forest |
| Trial-conversion AUC | **0.751** | on observed non-buyer → buyer events |
| **Lift vs blanket discounting** | **2.02×** | top-20% targeting beats discounting everyone |
| Recommended over-preparation | **12.2–12.7%** | vs **14.2%** baseline → waste reduction |
| Surplus redistributed | **99.4%** | across all institutions |
| NGO 20% guarantee | **satisfied** | every selected partner, every run |
| Price floor violations | **0** | across all recommendations and discounts |

---

## Architecture

```
React + Vite + Tailwind  (5 role-scoped dashboards)
            │  REST + JWT
FastAPI  ── Auth/RBAC ── 40 endpoints across 5 roles
            │
Agent layer:  Supervisor → Context → Forecast → Waste → Pricing
                        → Menu → Offer → NGO   (audit-logged)
            │
Engines:  XGBoost (demand) · RandomForest (waste) · GradientBoosting
          (conversion) · constrained pricing · hybrid menu scorer
          · OR-Tools CP-SAT (NGO allocation)
            │
SQLAlchemy ORM → SQLite (Postgres-swappable: change one connection string)
            │
External: Open-Meteo live weather (free, keyless, with offline fallback)
```

### The three hard constraints

1. **Cost-recovery floor** — `price ≥ unit_cost × 1.20`, applied *last* and
   unconditionally. No discount, elasticity estimate or waste markdown can breach
   it, and the API rejects a manager's manual override that would.
2. **NGO 20% guarantee** — every selected partner receives at least 20% of the
   day's allocatable surplus, *capped by its own stated capacity*.
3. **Dietary** — vegetarian-only NGOs never receive non-vegetarian surplus.

---

## Design decisions worth defending in a viva

**Why synthetic data.** No public dataset carries unit cost, quantity prepared,
quantity leftover, institution segment, or NGO need profiles — precisely the
columns the Price Floor, Waste and NGO engines consume. UCI Online Retail is UK
giftware e-commerce; training a canteen forecaster on it invites an unanswerable
question. The survey paper names synthetic generation as the sanctioned response
to this gap. Every generative assumption is documented in `backend/app/seed.py`.

**Why the LLM decides nothing.** Prices come from constrained optimisation,
allocations from CP-SAT, forecasts from XGBoost. The LLM only narrates decisions
already made, so the system is deterministic, reproducible and auditable, and it
degrades to templated briefings when Ollama is absent (as it is here).

**Safety stock is sized from forecast error, not demand variance.** Demand has a
coefficient of variation of ~0.50, but most of that is the weekday/Saturday swing
the model *already predicts*. Sizing safety stock from raw demand variance
double-counts it and inflates over-preparation to ~44% — worsening the very waste
the project exists to reduce. Per-dish held-out forecast error brings it to ~12%.

**The 20% guarantee has a failure mode, and it is handled.** With 5 partners,
5 × 20% = 100%, which forces an equal split and leaves nothing to optimise; so the
guarantee applies to the partners *selected* for that day's run. Worse, on a
high-surplus day, 20% of surplus can exceed a small NGO's capacity — disqualifying
it and *reducing* the number of partners served, inverting the policy's intent.
Capping the guarantee by capacity raised measured coverage from ~76% to 99.4%.

**Inelastic segments have no interior price optimum.** Under constant elasticity,
`p* = c·e/(e+1)` is valid only for `e < −1`. The corporate segment (`e = −0.6`)
has no maximum — profit rises monotonically with price. The segment ceiling is
what makes the model well-posed, and it is the mechanism that answers the paper's
own fairness concern about differentiated pricing.

---

## Known limitations (state these before an examiner finds them)

- **Data is synthetic.** Metrics validate that the pipeline learns real structure,
  not that it will hit these numbers in a live cafeteria.
- **SQLite, not PostgreSQL.** A deadline decision. SQLAlchemy makes it a
  connection-string change; no query or model would alter.
- **Ollama not installed**, so briefings are templated. The integration is written
  and probes on startup.
- **Pricing and Promotion engines remain thinly evidenced** in the survey paper's
  own words. The code implements them rigorously, but the literature review needs
  ~6–8 sources on dynamic retail pricing and multi-agent coordination before the
  novelty claim is as defensible as the other four engines.
- **Conversion labels are observational**, not from a randomised holdout, so the
  2.02× lift is a targeting-quality measure, not a causal treatment effect.

---

## Layout

```
backend/
  app/
    config.py         business rules (floor %, guarantee %, segment bands)
    models.py         19 SQLAlchemy tables
    auth.py           JWT + pbkdf2 + role guards + tenancy scoping
    seed.py           synthetic dataset generator (documented assumptions)
    engines/
      features.py     shared lag/rolling feature engineering
      forecasting.py  XGBoost demand + newsvendor prep quantity
      pricing.py      elasticity optimum, segment bands, cost floor
      waste.py        RandomForest leftover prediction
      recommendation.py  hybrid taste-trend menu scorer
      trial_conversion.py  non-buyer detection + conversion classifier
      ngo_allocation.py    OR-Tools CP-SAT equitable allocation
    agents/graph.py   supervisor + 7 agents, audit-logged
    agents/llm.py     optional Ollama narration
    external/weather.py  Open-Meteo with offline fallback
    routers/          auth, kitchen, admin, ngo, customer
  smoke_test.py       48 end-to-end checks
  tests/              pytest regression suite, isolated temp DB
frontend/src/
  pages/kitchen/      dashboard, pricing, forecast, inventory, offers, surplus, reports
  pages/admin/        global dashboard, institutions, NGOs, engines, impact, audit
  pages/ngo/          today, history, need profile
  pages/customer/     menu, offers, orders, profile
```
