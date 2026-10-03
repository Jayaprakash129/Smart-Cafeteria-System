import { useEffect, useState } from "react";
import { api, money, num } from "../../api";
import Layout from "../../components/Layout";
import { Badge, Bar, Card, ErrorBox, Loading, Stat, Table } from "../../components/ui";

export default function Surplus() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [actuals, setActuals] = useState({});
  const [savingActuals, setSavingActuals] = useState(false);

  const load = async () => {
    setError(null);
    try {
      setData(await api.get("/kitchen/surplus"));
    } catch (e) {
      setError(e);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const reallocate = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.post("/kitchen/surplus/allocate", {});
      await load();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  // The surplus shown here starts as the morning's *predicted* leftovers.
  // This lets the kitchen correct it to what was actually left at close of
  // service and immediately re-solve the allocation from the real numbers.
  const saveActuals = async () => {
    const items = Object.entries(actuals)
      .filter(([, v]) => v !== "" && v !== undefined)
      .map(([dish_id, v]) => ({ dish_id: Number(dish_id), actual_quantity: Number(v) }));
    if (!items.length) return;
    setSavingActuals(true);
    setError(null);
    try {
      await api.post("/kitchen/surplus/actual", { items });
      setActuals({});
      await load();
    } catch (e) {
      setError(e);
    } finally {
      setSavingActuals(false);
    }
  };

  const s = data?.summary;

  return (
    <Layout
      title="Surplus & NGO Handoff"
      subtitle={data ? `${data.institution} · ${data.date}` : ""}
      actions={
        <div className="flex items-center gap-2">
          {Object.keys(actuals).length > 0 && (
            <button className="btn-ghost" disabled={savingActuals} onClick={saveActuals}>
              {savingActuals ? "Saving…" : "Save actuals & reallocate"}
            </button>
          )}
          <button className="btn-primary" disabled={busy} onClick={reallocate}>
            {busy ? "Solving…" : "↻ Re-run allocation"}
          </button>
        </div>
      }
    >
      <ErrorBox error={error} onRetry={load} />
      {!data ? (
        <Loading />
      ) : (
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Stat
              label="Total surplus"
              value={`${num(s.total_surplus)} meals`}
              sub={money(s.meals_value)}
            />
            <Stat
              label="Redistributed"
              value={`${s.coverage_pct}%`}
              sub={`${num(s.distributed)} meals to ${s.partners} NGOs`}
              tone="good"
            />
            <Stat
              label="NGO partners"
              value={s.partners}
              sub="multi-recipient split"
              tone="brand"
            />
            <Stat
              label="20% guarantee"
              value={s.all_meet_guarantee ? "Satisfied" : "Breached"}
              sub="every partner meets its floor"
              tone={s.all_meet_guarantee ? "good" : "bad"}
            />
          </div>

          <Card
            title="Allocation plan"
            subtitle="Solved with OR-Tools CP-SAT: conservation, dietary, capacity and the 20% guarantee are hard constraints; need-satisfaction with max-min fairness is the objective"
          >
            <div className="space-y-4">
              {data.allocations.map((a) => (
                <div
                  key={a.ngo_id}
                  className="rounded-lg border border-slate-200 p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-slate-800">{a.ngo_name}</span>
                        {a.meets_guarantee ? (
                          <Badge tone="green">guarantee met</Badge>
                        ) : (
                          <Badge tone="red">below guarantee</Badge>
                        )}
                        <Badge tone={a.status === "collected" ? "blue" : "slate"}>
                          {a.status}
                        </Badge>
                        {a.expiry_risk && <Badge tone="red">pickup may be after expiry</Badge>}
                      </div>
                      <div className="mt-0.5 text-xs text-slate-500">
                        {a.contact_person} · {a.phone} · pickup {a.pickup_slot}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-lg font-semibold text-slate-900">
                        {num(a.quantity)} meals
                      </div>
                      <div className="text-xs text-slate-500">
                        {a.share_pct}% of today's surplus
                        {a.guarantee_pool === "vegetarian" && (
                          <span className="block text-slate-400">
                            20% guarantee measured against vegetarian surplus only
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="mt-3">
                    <Bar value={a.share_pct} max={100} tone="brand" />
                  </div>

                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {a.items.map((it, i) => (
                      <span
                        key={i}
                        className="rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-600"
                      >
                        {it.dish_name} × {it.quantity}
                        {it.is_veg ? " 🟢" : " 🔴"}
                        <span className="ml-1 text-slate-400">
                          {it.hours_to_expiry}h left
                        </span>
                      </span>
                    ))}
                  </div>
                </div>
              ))}
              {!data.allocations.length && (
                <div className="py-10 text-center text-sm text-slate-400">
                  No allocation yet — run the daily pipeline
                </div>
              )}
            </div>
          </Card>

          <Card title="Surplus inventory" subtitle="Unsold stock recovered at close of service">
            <Table
              columns={[
                { key: "dish_name", label: "Dish" },
                {
                  key: "quantity",
                  label: "Qty",
                  align: "right",
                  render: (r) => num(r.quantity),
                },
                {
                  key: "is_veg",
                  label: "Type",
                  render: (r) =>
                    r.is_veg ? (
                      <Badge tone="green">veg</Badge>
                    ) : (
                      <Badge tone="red">non-veg</Badge>
                    ),
                },
                {
                  key: "hours_to_expiry",
                  label: "Expires in",
                  align: "right",
                  render: (r) => (
                    <span className={r.hours_to_expiry <= 2 ? "text-rose-600" : ""}>
                      {r.hours_to_expiry}h
                    </span>
                  ),
                },
                {
                  key: "value",
                  label: "Value",
                  align: "right",
                  render: (r) => money(r.value),
                },
                {
                  key: "status",
                  label: "Status",
                  render: (r) => <Badge tone={r.status === "collected" ? "blue" : "slate"}>{r.status}</Badge>,
                },
                {
                  key: "actual",
                  label: "Actual leftover",
                  align: "right",
                  render: (r) => (
                    <input
                      type="number"
                      min="0"
                      placeholder={r.quantity}
                      className="input w-24 py-1 text-right"
                      value={actuals[r.dish_id] ?? ""}
                      onChange={(e) =>
                        setActuals((s) => ({ ...s, [r.dish_id]: e.target.value }))
                      }
                    />
                  ),
                },
              ]}
              rows={data.surplus_items}
              empty="No surplus recorded today"
            />
          </Card>
        </div>
      )}
    </Layout>
  );
}
