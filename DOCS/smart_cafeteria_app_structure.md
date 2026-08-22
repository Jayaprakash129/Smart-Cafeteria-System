# Smart Cafeteria System — Application Structure, Roles & Page Flow

This document answers three questions together, since they're one system:
1. **Who uses the platform** (roles, who they are in real life, how they get access)
2. **What pages exist**, grouped by role, with exactly what each page does
3. **How navigation flows** — what a session looks like end to end for each role

---

## 1. Roles — Who Is Involved and How They Access the Platform

| # | Role | Who this is in real life | Access point | Auth method |
|---|------|---------------------------|---------------|--------------|
| 1 | **Super Admin** | You / the platform-owning team running Smart Cafeteria across all client institutions | Web dashboard (desktop-first) | Email + password + 2FA |
| 2 | **Kitchen Manager** | The person physically running a cafeteria at one corporate office / college / school | Web dashboard (desktop, tablet-friendly for kitchen use) | Email/phone + password, invited by Super Admin |
| 3 | **Institution Coordinator** *(optional, but recommended)* | HR rep at a corporate client, or admin office staff at a college/school — the client-side point of contact | Web dashboard (lightweight, view-only + approvals) | Invited by Super Admin, email + password |
| 4 | **NGO Partner / Distributor** | Staff at each partnered NGO who need to know what surplus food is available and pick it up | Web dashboard (simple, mobile-responsive) + optional mobile app | Invited by Super Admin after NGO onboarding/verification |
| 5 | **End Customer (Employee / Student)** | The actual person buying food at the counter or ordering ahead | Mobile app (primary) or web ordering page (fallback) | Phone number + OTP, or institution SSO/ID card link |

**Why the End Customer role matters technically:** your Trial-Conversion Engine (Module 8) needs to know *who* bought *what* yesterday, so it can target *non-buyers* today. Without individual customer accounts, you can only approximate this at the segment level, not the individual level. Decide early whether you want:
- **Full personalization** → requires login (phone/OTP or ID card scan at counter), OR
- **Simplified/anonymized version** → track by counter/segment only, and be upfront in your paper that this is a scoped limitation with "individual personalization" as future work.

For a final-year project, the **simplified version is safer and still demoable** — recommend starting there and upgrading to full login-based tracking only if time allows in Phase 2.

---

## 2. Pages by Role

### A. Super Admin — Pages

| Page | What it does |
|------|--------------|
| **Login / 2FA** | Entry point, secured with two-factor auth since this role has full system access |
| **Global Dashboard (Home)** | Cross-institution overview: total profit today, total waste reduced, total NGO meals donated, active institutions, alerts needing attention |
| **Institution Management** | Add/edit/deactivate client institutions; assign segment (Corporate/College/School); set base margin targets per segment |
| **User Management** | Invite/manage Kitchen Managers, Institution Coordinators, NGO Partners; assign roles/permissions |
| **Global Pricing Rules** | Set platform-wide constraints — the hard price floor formula (cost + 20%), segment ceiling ranges, discount caps |
| **NGO Partner Management** | Onboard/verify NGOs, set their need profile, reliability score, minimum 20% guarantee status |
| **Model & Engine Monitoring** | Health/status of each ML engine (Forecasting, Pricing, Matching, Trial-Conversion) — accuracy metrics, last retrain date |
| **Platform Analytics** | Aggregated reporting across all institutions — profit uplift %, waste reduction %, NGO distribution fairness, exportable reports for the project paper |
| **Audit Log / Agent Actions** *(Phase 2)* | Every autonomous agent decision, with approve/reject queue for high-impact actions |
| **Settings** | Platform-level config: notification rules, API keys, backup/export |

**Navigation flow:** Login → Global Dashboard → drill into any institution → Institution Management or Analytics → back to Global Dashboard. Super Admin rarely touches day-to-day kitchen operations; this role is oversight + configuration.

---

### B. Kitchen Manager — Pages

| Page | What it does |
|------|--------------|
| **Login** | Institution-scoped login — sees only their own cafeteria's data |
| **Today's Dashboard (Home)** | The core daily screen: today's recommended menu, recommended prices per dish, forecasted demand, current stock alerts, any floor-price overrides flagged |
| **Menu & Pricing Approval** | Shows system-recommended dishes (from Taste-Trend Matching Engine) + system-recommended prices (from Pricing Engine) with an Approve / Adjust / Reject action per dish |
| **Inventory & Stock** | Current stock levels, near-expiry flags, manual stock entry/update form |
| **Demand Forecast View** | Chart/table of predicted demand per dish for today and the coming week |
| **Trial-Conversion Offers** | Shows yesterday's best-seller, the auto-generated non-buyer list, and the proposed 25% (or elasticity-adjusted) discount — with approve/edit controls |
| **Surplus & NGO Handoff** | At end of day: how much surplus exists, which NGOs it's been split to (20% minimum each), pickup status/confirmation |
| **Sales & Profit Report (This Institution)** | Daily/weekly/monthly profit, cost breakdown, waste %, specific to their own cafeteria |
| **Notifications / Alerts** | Anomalies flagged by the system — e.g. "forecast deviation is unusually high today," "floor price overrode a discount" |
| **Settings/Profile** | Their own account, cafeteria operating hours, contact info |

**Navigation flow:** Login → Today's Dashboard → Menu & Pricing Approval (start of day) → Inventory checks through the day → Trial-Conversion Offers (mid-day, based on yesterday's data) → Surplus & NGO Handoff (end of day) → Sales & Profit Report (review). This is the most-used role — design this flow to require the fewest clicks, since a kitchen manager is busy.

---

### C. Institution Coordinator — Pages *(optional role, lighter access)*

| Page | What it does |
|------|--------------|
| **Login** | Scoped to their institution, read-mostly access |
| **Overview Dashboard** | High-level view of their cafeteria's performance — profit, popular dishes, satisfaction trends — without kitchen-operations detail |
| **Budget & Billing** | If the platform charges the institution, or if the institution subsidizes meals — billing summary, invoices |
| **Feedback Summary** | Aggregated employee/student feedback and satisfaction scores |
| **Approvals (optional)** | For institutions that want sign-off on major price changes before the Kitchen Manager finalizes them |

**Navigation flow:** Login → Overview Dashboard → drill into Budget/Billing or Feedback as needed. This role exists mainly for transparency to the client, not daily operations — keep it thin so it doesn't become a second full app to build.

---

### D. NGO Partner / Distributor — Pages

| Page | What it does |
|------|--------------|
| **Login** | NGO-scoped login |
| **Today's Available Surplus** | What food is available today, from which institution(s), quantity, and their guaranteed 20%-minimum share |
| **Pickup Scheduling / Confirmation** | Confirm pickup time/window, mark as collected once done |
| **Distribution History** | Past pickups — what was received, when, from where — useful for their own reporting and for your NGO-fairness analytics |
| **Need Profile / Preferences** | NGO updates what kind of food / how much they typically need, which feeds the allocation algorithm's need-weighting |
| **Notifications** | Alerts when new surplus becomes available or a pickup window is closing |

**Navigation flow:** Login → Today's Available Surplus → Pickup Scheduling → (after pickup) mark confirmed → Distribution History for their own records. Keep this extremely simple — NGO staff are not power users and may access this on a basic phone browser.

---

### E. End Customer (Employee / Student) — Pages *(mobile-first)*

| Page | What it does |
|------|--------------|
| **Login/OTP** | Phone number + OTP, or institution ID linkage |
| **Today's Menu** | Browse today's dishes with prices, dietary tags (veg/non-veg, spicy/sweet lean), and any active trial-discount offers personalized to them |
| **Order / Pre-Order** | Place an order for pickup, or pre-order for a specific time slot |
| **Order History** | Past orders — this is also the data source that powers the Trial-Conversion Engine's non-buyer detection |
| **Offers / Trial Discounts** | If they're flagged as a "didn't try yesterday's best-seller" customer, this is where the 25% offer surfaces |
| **Feedback** | Rate a dish/meal — feeds Analytics and indirectly the Taste-Matching Engine |
| **Profile** | Basic account info, saved payment method if applicable |

**Navigation flow:** Login/OTP → Today's Menu (with any personalized offer banner at top) → Order → confirmation → (later) Feedback prompt → Order History available anytime from a bottom nav bar.

---

## 3. Full Sitemap — How Roles Connect

```
                         ┌─────────────────────┐
                         │   Landing / Login    │
                         │  (role auto-detected  │
                         │   or role selector)   │
                         └──────────┬───────────┘
              ┌───────────┬─────────┼─────────┬───────────────┐
              ▼           ▼         ▼         ▼               ▼
        Super Admin   Kitchen   Institution   NGO          End Customer
        Dashboard     Manager   Coordinator   Partner      (mobile app)
                       Dashboard  Dashboard    Dashboard
              │           │         │         │               │
   ┌──────────┼───┐   ┌───┼────┐   │     ┌───┼────┐    ┌─────┼─────┐
   ▼          ▼   ▼   ▼   ▼    ▼   ▼     ▼        ▼    ▼     ▼     ▼
Institution  User Global  Menu  Inventory Trial  Surplus Overview Budget
Mgmt         Mgmt  Rules  Approval        Conv.   /NGO   Dashboard
                                                  Handoff
```

**Cross-role data flow (this is the part worth putting in your architecture diagram for the paper):**
- End Customer orders → feed Demand Forecasting Engine (Module 3) and Trial-Conversion Engine (Module 8)
- Kitchen Manager approvals → feed back into Pricing Engine (Module 4) as ground-truth correction signal
- Surplus data from Kitchen Manager → NGO Distribution Engine (Module 9) → surfaces on NGO Partner's dashboard
- Institution Coordinator only *reads* aggregated data — never writes into any engine directly
- Super Admin sets the *rules* (floor price %, segment ceilings) that constrain every other role's screen

---

## 4. Modern App Navigation Pattern (Recommended)

For a polished final-year demo, use this consistent pattern across all dashboards (Admin, Kitchen Manager, Institution Coordinator, NGO):

- **Left sidebar** — persistent navigation between major pages (Dashboard, Menu, Inventory, Reports, Settings), collapsible on tablet
- **Top bar** — current institution name (for multi-institution roles), notification bell, profile menu
- **Main content area** — the page itself, using cards + charts, not dense tables (this is where "polish" is judged)
- **Breadcrumbs** on drill-down pages (e.g. Institution Management → [Institution Name] → Pricing Rules)

For the End Customer mobile app:
- **Bottom tab bar** — Menu, Orders, Offers, Profile (4 tabs max, standard mobile pattern)
- **Top banner** on Menu page for active personalized offers — this is your Trial-Conversion Engine's most visible UI touchpoint, make it prominent

---

## 5. Minimum Viable Page Set (If Time Is Tight)

If Phase 1 timeline gets compressed, here's the priority order — build these first, since they're what a live demo and viva will actually be judged on:

1. Kitchen Manager: Today's Dashboard + Menu & Pricing Approval
2. Kitchen Manager: Inventory & Stock
3. Kitchen Manager: Trial-Conversion Offers
4. Kitchen Manager: Surplus & NGO Handoff
5. NGO Partner: Today's Available Surplus + Pickup Confirmation
6. Super Admin: Global Dashboard + Institution Management
7. End Customer: Today's Menu + Order (even a simplified version, since it's your data source)

Institution Coordinator pages and Super Admin's deeper analytics/audit pages can be thinner or deferred to Phase 2 without hurting completeness — evaluators will notice if the *operational* loop (Kitchen Manager ↔ Customer ↔ NGO) is weak, less so if the *oversight* layer (Coordinator, deep Admin analytics) is minimal.

---

## Next Steps Worth Deciding

- Whether End Customer login is phone+OTP (simplest, most realistic to build) or tied to institution ID/SSO (more "enterprise," more setup work)
- Whether Institution Coordinator is a real role in your build or just mentioned in the paper as a "supported future role" to save build time
- Confirm with your team which member (per your A/B/C/D split) owns which set of pages, so UI work doesn't bottleneck on your Docs & Frontend Lead alone
