import { useEffect, useState } from "react";
import { api, money, num } from "../../api";
import Layout from "../../components/Layout";
import { Badge, Card, ErrorBox, Loading, Stat, Table } from "../../components/ui";

const TONE = { expired: "red", expiring: "amber", low: "amber", ok: "green" };

export default function Inventory() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [edit, setEdit] = useState({});
  const [busy, setBusy] = useState(null);

  const load = () => api.get("/kitchen/inventory").then(setData).catch(setError);
  useEffect(() => {
    load();
  }, []);

  const save = async (item) => {
    setBusy(item.id);
    setError(null);
    try {
      await api.post("/kitchen/inventory/update", {
        item_id: item.id,
        quantity_on_hand: Number(edit[item.id]),
      });
      setEdit((s) => ({ ...s, [item.id]: undefined }));
      await load();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  const items = data?.items || [];
  const counts = items.reduce((a, i) => ({ ...a, [i.status]: (a[i.status] || 0) + 1 }), {});

  return (
    <Layout title="Inventory & Stock" subtitle={data?.institution || ""}>
      <ErrorBox error={error} onRetry={load} />
      {!data ? (
        <Loading />
      ) : (
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label="Stock value" value={money(data.total_stock_value)} sub={`${items.length} ingredients`} />
            <Stat label="Below reorder" value={counts.low || 0} sub="need restocking" tone={counts.low ? "warn" : "good"} />
            <Stat label="Expiring ≤3 days" value={counts.expiring || 0} sub="use or lose" tone={counts.expiring ? "warn" : "good"} />
            <Stat label="Expired" value={counts.expired || 0} sub="remove from stock" tone={counts.expired ? "bad" : "good"} />
          </div>

          <Card title="Ingredient stock" subtitle="Sorted by urgency — expired first, then expiring, then below reorder level">
            <Table
              columns={[
                {
                  key: "name",
                  label: "Ingredient",
                  render: (r) => (
                    <div>
                      <div className="font-medium text-slate-800">{r.name}</div>
                      <div className="text-xs text-slate-400">{money(r.cost_per_unit)}/{r.unit}</div>
                    </div>
                  ),
                },
                {
                  key: "quantity_on_hand",
                  label: "On hand",
                  align: "right",
                  render: (r) =>
                    edit[r.id] !== undefined ? (
                      <div className="flex items-center justify-end gap-1.5">
                        <input
                          className="input w-24 py-1 text-right"
                          value={edit[r.id]}
                          onChange={(e) => setEdit((s) => ({ ...s, [r.id]: e.target.value }))}
                        />
                        <button className="btn-primary px-2 py-1" disabled={busy === r.id} onClick={() => save(r)}>
                          ✓
                        </button>
                        <button className="btn-ghost px-2 py-1" onClick={() => setEdit((s) => ({ ...s, [r.id]: undefined }))}>
                          ✕
                        </button>
                      </div>
                    ) : (
                      <button
                        className="tabular-nums hover:text-brand-600 hover:underline"
                        onClick={() => setEdit((s) => ({ ...s, [r.id]: r.quantity_on_hand }))}
                      >
                        {num(r.quantity_on_hand, 1)} {r.unit}
                      </button>
                    ),
                },
                { key: "reorder_level", label: "Reorder at", align: "right", render: (r) => num(r.reorder_level, 1) },
                {
                  key: "expiry",
                  label: "Expiry",
                  align: "right",
                  render: (r) =>
                    r.days_to_expiry == null ? (
                      <span className="text-slate-300">—</span>
                    ) : (
                      <span className={r.days_to_expiry <= 3 ? "text-amber-600" : "text-slate-500"}>
                        {r.days_to_expiry < 0 ? "expired" : `${r.days_to_expiry}d`}
                      </span>
                    ),
                },
                { key: "stock_value", label: "Value", align: "right", render: (r) => money(r.stock_value) },
                { key: "status", label: "Status", render: (r) => <Badge tone={TONE[r.status]}>{r.status}</Badge> },
              ]}
              rows={items}
            />
            <p className="mt-3 text-xs text-slate-400">
              Click any quantity to update it directly.
            </p>
          </Card>
        </div>
      )}
    </Layout>
  );
}
