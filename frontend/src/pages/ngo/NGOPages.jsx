import { useEffect, useState } from "react";
import { api, num } from "../../api";
import Layout from "../../components/Layout";
import { Badge, Bar, Card, ErrorBox, Loading, Stat, Table } from "../../components/ui";

/* --------------------------------------------------------------- Today */
export function NGOToday() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);

  const load = () => api.get("/ngo/today").then(setData).catch(setError);
  useEffect(() => {
    load();
  }, []);

  const confirm = async (pickup, status) => {
    setBusy(pickup.institution_id);
    setError(null);
    try {
      await api.post("/ngo/pickups/confirm", {
        allocation_ids: pickup.allocation_ids,
        status,
      });
      await load();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  const s = data?.summary;

  return (
    <Layout
      title="Today's Available Surplus"
      subtitle={data ? `${data.ngo.name} · ${data.date}` : ""}
    >
      <ErrorBox error={error} onRetry={load} />
      {!data ? (
        <Loading />
      ) : (
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label="Meals allocated" value={num(s.total_meals)} sub={`from ${s.institutions} cafeteria(s)`} tone="brand" />
            <Stat
              label="Your daily need"
              value={num(data.ngo.daily_need_meals)}
              sub={`${s.need_met_pct}% met today`}
              tone={s.need_met_pct >= 80 ? "good" : "warn"}
            />
            <Stat
              label="Guarantee"
              value={s.all_meet_guarantee ? "Met" : "Below"}
              sub={
                s.guarantee_pool === "vegetarian"
                  ? `minimum ${s.guarantee_pct}% of vegetarian surplus`
                  : `minimum ${s.guarantee_pct}% share`
              }
              tone={s.all_meet_guarantee ? "good" : "warn"}
            />
            <Stat label="Pending pickups" value={s.pending_pickups} sub="awaiting collection" />
          </div>

          {data.ngo.accepts_veg_only && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm text-emerald-800">
              Your profile is set to <strong>vegetarian only</strong> — the allocation
              engine never assigns you non-vegetarian surplus.
            </div>
          )}

          <div className="space-y-4">
            {data.pickups.map((p) => (
              <Card
                key={p.institution_id}
                title={p.institution_name}
                subtitle={`Pickup window ${p.pickup_slot} · ${p.share_pct}% of that cafeteria's surplus`}
                action={
                  p.status === "scheduled" ? (
                    <div className="flex gap-2">
                      <button
                        className="btn-ghost"
                        disabled={busy === p.institution_id}
                        onClick={() => confirm(p, "missed")}
                      >
                        Can't collect
                      </button>
                      <button
                        className="btn-primary"
                        disabled={busy === p.institution_id}
                        onClick={() => confirm(p, "collected")}
                      >
                        ✓ Mark collected
                      </button>
                    </div>
                  ) : (
                    <Badge tone={p.status === "collected" ? "green" : p.status === "mixed" ? "amber" : "red"}>
                      {p.status}
                    </Badge>
                  )
                }
              >
                <div className="mb-3 flex items-baseline gap-3">
                  <span className="text-2xl font-semibold text-slate-900">
                    {num(p.quantity)}
                  </span>
                  <span className="text-sm text-slate-500">meals</span>
                  {p.meets_guarantee && <Badge tone="green">guarantee met</Badge>}
                </div>
                <Table
                  columns={[
                    { key: "dish_name", label: "Dish" },
                    { key: "quantity", label: "Qty", align: "right", render: (r) => num(r.quantity) },
                    {
                      key: "is_veg",
                      label: "Type",
                      render: (r) => (r.is_veg ? <Badge tone="green">veg</Badge> : <Badge tone="red">non-veg</Badge>),
                    },
                    {
                      key: "hours_to_expiry",
                      label: "Best before",
                      align: "right",
                      render: (r) => (
                        <span className={r.hours_to_expiry <= 2 ? "font-medium text-rose-600" : ""}>
                          {r.hours_to_expiry}h
                        </span>
                      ),
                    },
                  ]}
                  rows={p.items}
                />
              </Card>
            ))}
            {!data.pickups.length && (
              <Card>
                <div className="py-10 text-center text-sm text-slate-400">
                  No surplus allocated to you today.
                </div>
              </Card>
            )}
          </div>
        </div>
      )}
    </Layout>
  );
}

/* ------------------------------------------------------------- History */
export function NGOHistory() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get("/ngo/history?days=30").then(setData).catch(setError);
  }, []);

  const t = data?.totals;

  return (
    <Layout title="Distribution History" subtitle="Your record of received donations">
      <ErrorBox error={error} />
      {!data ? (
        <Loading />
      ) : (
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label="Meals received (30d)" value={num(t.meals_received)} tone="brand" />
            <Stat label="Pickups" value={t.pickups} sub={`${t.collected} collected`} />
            <Stat label="Missed" value={t.missed} tone={t.missed ? "warn" : "good"} />
            <Stat
              label="Collection rate"
              value={t.collection_rate != null ? `${(t.collection_rate * 100).toFixed(0)}%` : "—"}
              sub="drives your reliability score"
              tone="good"
            />
          </div>

          <Card title="Daily receipts" subtitle="Meals received per day over the window">
            <Table
              columns={[
                { key: "date", label: "Date" },
                { key: "quantity", label: "Meals", align: "right", render: (r) => num(r.quantity) },
                {
                  key: "institutions",
                  label: "From",
                  render: (r) => r.institutions.join(", "),
                },
                {
                  key: "status",
                  label: "Status",
                  render: (r) =>
                    r.status === "mixed" ? (
                      <span className="flex flex-wrap gap-1">
                        {Object.entries(r.status_counts || {}).map(([st, n]) => (
                          <Badge key={st} tone={st === "collected" ? "green" : st === "missed" ? "red" : "slate"}>
                            {st} ×{n}
                          </Badge>
                        ))}
                      </span>
                    ) : (
                      <Badge tone={r.status === "collected" ? "green" : r.status === "missed" ? "red" : "slate"}>
                        {r.status}
                      </Badge>
                    ),
                },
              ]}
              rows={[...(data.daily || [])].reverse()}
            />
          </Card>
        </div>
      )}
    </Layout>
  );
}

/* ------------------------------------------------------------- Profile */
export function NGOProfile() {
  const [data, setData] = useState(null);
  const [form, setForm] = useState({});
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = () =>
    api.get("/ngo/profile").then((d) => {
      setData(d);
      setForm({
        daily_need_meals: d.daily_need_meals,
        beneficiaries: d.beneficiaries,
        accepts_veg_only: d.accepts_veg_only,
        contact_person: d.contact_person,
        phone: d.phone,
      });
    }).catch(setError);

  useEffect(() => {
    load();
  }, []);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.patch("/ngo/profile", {
        ...form,
        daily_need_meals: Number(form.daily_need_meals),
        beneficiaries: Number(form.beneficiaries),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
      await load();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Layout title="Need Profile" subtitle="These values feed directly into the allocation engine">
      <ErrorBox error={error} />
      {!data ? (
        <Loading />
      ) : (
        <div className="max-w-2xl space-y-5">
          <Card title={data.name} subtitle={`${data.city} · ${data.verified ? "verified partner" : "pending verification"}`}>
            <div className="space-y-4">
              <Field label="Contact person">
                <input className="input" value={form.contact_person || ""} onChange={(e) => setForm((f) => ({ ...f, contact_person: e.target.value }))} />
              </Field>
              <Field label="Phone">
                <input className="input" value={form.phone || ""} onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} />
              </Field>
              <Field label="Daily need (meals)" hint="Caps how much you can be allocated in one day">
                <input type="number" className="input" value={form.daily_need_meals ?? ""} onChange={(e) => setForm((f) => ({ ...f, daily_need_meals: e.target.value }))} />
              </Field>
              <Field label="Beneficiaries served" hint="Used to weight need urgency against other partners">
                <input type="number" className="input" value={form.beneficiaries ?? ""} onChange={(e) => setForm((f) => ({ ...f, beneficiaries: e.target.value }))} />
              </Field>
              <label className="flex items-center gap-2.5 text-sm text-slate-700">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-slate-300"
                  checked={!!form.accepts_veg_only}
                  onChange={(e) => setForm((f) => ({ ...f, accepts_veg_only: e.target.checked }))}
                />
                Accept vegetarian food only
              </label>

              <div className="flex items-center gap-3 pt-2">
                <button className="btn-primary" disabled={busy} onClick={save}>
                  {busy ? "Saving…" : "Save profile"}
                </button>
                {saved && <span className="text-sm text-emerald-600">Saved ✓</span>}
              </div>
            </div>
          </Card>

          <Card title="Reliability score" subtitle="Measured from your pickup history — it cannot be edited">
            <div className="flex items-center gap-4">
              <span className="text-3xl font-semibold text-slate-900">
                {(data.reliability_score * 100).toFixed(0)}%
              </span>
              <div className="flex-1">
                <Bar value={data.reliability_score * 100} max={100} tone={data.reliability_score > 0.85 ? "brand" : "amber"} />
                <p className="mt-2 text-xs text-slate-500">
                  Confirming pickups promptly raises this score, which increases your
                  priority in future allocations.
                </p>
              </div>
            </div>
          </Card>
        </div>
      )}
    </Layout>
  );
}

function Field({ label, hint, children }) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-slate-700">{label}</label>
      {children}
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </div>
  );
}
