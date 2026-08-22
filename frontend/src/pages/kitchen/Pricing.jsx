import { useEffect, useState } from "react";
import { api, money, num } from "../../api";
import Layout from "../../components/Layout";
import { Badge, Card, ErrorBox, Loading, Stat, Table } from "../../components/ui";

export default function Pricing() {
  const [data, setData] = useState(null);
  const [menu, setMenu] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);
  const [editing, setEditing] = useState({});

  const load = async () => {
    setError(null);
    try {
      const [p, m] = await Promise.all([
        api.get("/kitchen/prices"),
        api.get("/kitchen/menu"),
      ]);
      setData(p);
      setMenu(m);
    } catch (e) {
      setError(e);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const decide = async (rec, action) => {
    setBusy(rec.id);
    setError(null);
    try {
      const body = { recommendation_id: rec.id, action };
      if (action === "adjust") {
        body.adjusted_price = Number(editing[rec.id]);
      }
      await api.post("/kitchen/prices/decide", body);
      await load();
      setEditing((s) => ({ ...s, [rec.id]: undefined }));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  const recs = data?.recommendations || [];
  const pending = recs.filter((r) => r.status === "pending");
  const uplift = recs.reduce(
    (s, r) => s + (r.recommended_price - r.current_price) * r.predicted_demand,
    0
  );
  const floored = recs.filter((r) => r.floor_enforced).length;

  return (
    <Layout
      title="Menu & Pricing Approval"
      subtitle={
        data ? `${data.institution} · ${data.segment} segment · ${data.date}` : ""
      }
      actions={
        pending.length > 0 && (
          <button
            className="btn-primary"
            onClick={async () => {
              for (const r of pending) await decide(r, "approve");
            }}
          >
            Approve all ({pending.length})
          </button>
        )
      }
    >
      <ErrorBox error={error} onRetry={load} />
      {!data ? (
        <Loading />
      ) : (
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label="Recommendations" value={recs.length} sub={`${pending.length} pending`} />
            <Stat
              label="Projected daily uplift"
              value={money(uplift)}
              sub="vs current prices, at forecast volume"
              tone={uplift >= 0 ? "good" : "bad"}
            />
            <Stat
              label="Held at cost floor"
              value={floored}
              sub="cost + 20% enforced"
              tone={floored ? "warn" : "default"}
            />
            <Stat
              label="Segment"
              value={data.segment}
              sub="drives the elasticity band"
              tone="brand"
            />
          </div>

          <Card
            title="Price recommendations"
            subtitle="Every price is clamped to the segment band, then to the cost-recovery floor. The floor is applied last and cannot be overridden."
          >
            <Table
              columns={[
                {
                  key: "dish_name",
                  label: "Dish",
                  render: (r) => (
                    <div>
                      <div className="font-medium text-slate-800">{r.dish_name}</div>
                      <div className="text-xs text-slate-400">{r.category}</div>
                    </div>
                  ),
                },
                {
                  key: "current_price",
                  label: "Current",
                  align: "right",
                  render: (r) => money(r.current_price),
                },
                {
                  key: "recommended_price",
                  label: "Recommended",
                  align: "right",
                  render: (r) => (
                    <span className="font-semibold text-slate-900">
                      {money(r.recommended_price)}
                    </span>
                  ),
                },
                {
                  key: "change_pct",
                  label: "Change",
                  align: "right",
                  render: (r) => (
                    <span
                      className={
                        r.change_pct > 0
                          ? "text-emerald-600"
                          : r.change_pct < 0
                          ? "text-rose-600"
                          : "text-slate-400"
                      }
                    >
                      {r.change_pct > 0 ? "+" : ""}
                      {r.change_pct}%
                    </span>
                  ),
                },
                {
                  key: "price_floor",
                  label: "Floor",
                  align: "right",
                  render: (r) => (
                    <span className="text-xs text-slate-400">{money(r.price_floor)}</span>
                  ),
                },
                {
                  key: "predicted_demand",
                  label: "Demand",
                  align: "right",
                  render: (r) => num(r.predicted_demand),
                },
                {
                  key: "status",
                  label: "Status",
                  render: (r) =>
                    r.floor_enforced ? (
                      <Badge tone="amber">floor enforced</Badge>
                    ) : r.status === "approved" ? (
                      <Badge tone="green">approved</Badge>
                    ) : r.status === "rejected" ? (
                      <Badge tone="red">rejected</Badge>
                    ) : r.status === "adjusted" ? (
                      <Badge tone="blue">adjusted</Badge>
                    ) : (
                      <Badge>pending</Badge>
                    ),
                },
                {
                  key: "actions",
                  label: "Decision",
                  align: "right",
                  render: (r) => (
                    <div className="flex items-center justify-end gap-1.5">
                      {editing[r.id] !== undefined ? (
                        <>
                          <input
                            className="input w-24 py-1 text-right"
                            value={editing[r.id]}
                            onChange={(e) =>
                              setEditing((s) => ({ ...s, [r.id]: e.target.value }))
                            }
                          />
                          <button
                            className="btn-primary px-2 py-1"
                            disabled={busy === r.id}
                            onClick={() => decide(r, "adjust")}
                          >
                            Save
                          </button>
                          <button
                            className="btn-ghost px-2 py-1"
                            onClick={() =>
                              setEditing((s) => ({ ...s, [r.id]: undefined }))
                            }
                          >
                            ✕
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            className="btn-primary px-2.5 py-1"
                            disabled={busy === r.id}
                            onClick={() => decide(r, "approve")}
                          >
                            Approve
                          </button>
                          <button
                            className="btn-ghost px-2.5 py-1"
                            onClick={() =>
                              setEditing((s) => ({
                                ...s,
                                [r.id]: r.recommended_price,
                              }))
                            }
                          >
                            Adjust
                          </button>
                          <button
                            className="btn-danger px-2.5 py-1"
                            disabled={busy === r.id}
                            onClick={() => decide(r, "reject")}
                          >
                            Reject
                          </button>
                        </>
                      )}
                    </div>
                  ),
                },
              ]}
              rows={recs}
              empty="No recommendations — run the daily pipeline"
            />
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card
              title="Recommended menu"
              subtitle="Taste-trend scorer: popularity, momentum, satisfaction, margin, variety and weather"
            >
              <ol className="space-y-2.5">
                {(menu?.recommendations || []).slice(0, 8).map((m) => (
                  <li key={m.id} className="flex gap-3">
                    <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-100 text-xs font-semibold text-brand-700">
                      {m.rank}
                    </span>
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-slate-800">
                        {m.dish_name}
                      </div>
                      <div className="text-xs text-slate-500">{m.reason}</div>
                    </div>
                  </li>
                ))}
              </ol>
            </Card>

            <Card title="Trending this week" subtitle="Week-over-week movement">
              <div className="grid grid-cols-2 gap-5">
                <div>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-emerald-600">
                    Rising
                  </div>
                  {(menu?.trends?.rising || []).map((t) => (
                    <div key={t.dish_id} className="flex justify-between py-1 text-sm">
                      <span className="truncate text-slate-700">{t.dish_name}</span>
                      <span className="ml-2 font-medium text-emerald-600">
                        +{t.change_pct}%
                      </span>
                    </div>
                  ))}
                </div>
                <div>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-rose-600">
                    Falling
                  </div>
                  {(menu?.trends?.falling || []).map((t) => (
                    <div key={t.dish_id} className="flex justify-between py-1 text-sm">
                      <span className="truncate text-slate-700">{t.dish_name}</span>
                      <span className="ml-2 font-medium text-rose-600">
                        {t.change_pct}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          </div>
        </div>
      )}
    </Layout>
  );
}
