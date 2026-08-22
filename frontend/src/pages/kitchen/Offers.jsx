import { useEffect, useState } from "react";
import { api, money, num } from "../../api";
import Layout from "../../components/Layout";
import { Badge, Card, ErrorBox, Loading, Stat, Table } from "../../components/ui";

export default function Offers() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState(new Set());

  const load = async () => {
    setError(null);
    try {
      const d = await api.get("/kitchen/offers");
      setData(d);
      setSelected(new Set(d.offers.filter((o) => o.status === "pending").map((o) => o.id)));
    } catch (e) {
      setError(e);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const decide = async (action) => {
    setBusy(true);
    setError(null);
    try {
      await api.post("/kitchen/offers/decide", {
        offer_ids: [...selected],
        action,
      });
      await load();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const toggle = (id) =>
    setSelected((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });

  const s = data?.summary;
  const bs = data?.best_seller;

  return (
    <Layout
      title="Trial-Conversion Offers"
      subtitle={data ? `${data.institution} · ${data.date}` : ""}
      actions={
        selected.size > 0 && (
          <>
            <button className="btn-ghost" disabled={busy} onClick={() => decide("reject")}>
              Reject
            </button>
            <button
              className="btn-primary"
              disabled={busy}
              onClick={() => decide("approve")}
            >
              Approve {selected.size} offer{selected.size === 1 ? "" : "s"}
            </button>
          </>
        )
      }
    >
      <ErrorBox error={error} onRetry={load} />
      {!data ? (
        <Loading />
      ) : (
        <div className="space-y-5">
          <div className="card card-pad border-brand-200 bg-brand-50/50">
            <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-500">
                  Yesterday's best seller
                </div>
                <div className="mt-0.5 text-lg font-semibold text-slate-900">
                  {bs?.dish_name || "—"}
                </div>
                <div className="text-sm text-slate-500">
                  {num(bs?.quantity_sold)} units sold
                </div>
              </div>
              <div className="hidden h-10 w-px bg-slate-200 sm:block" />
              <p className="max-w-xl text-sm leading-relaxed text-slate-600">
                Offers go only to customers who <strong>visited yesterday but did
                not buy this dish</strong>. Targeting people who already bought it
                gives away margin for nothing; targeting people who never visit
                wastes the discount entirely.
              </p>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label="Offers generated" value={s.offers} sub={`${s.pending} pending`} tone="brand" />
            <Stat
              label="Expected conversions"
              value={num(s.expected_conversions, 1)}
              sub="sum of modelled probabilities"
              tone="good"
            />
            <Stat
              label="Expected revenue"
              value={money(s.expected_revenue)}
              sub="at the discounted price"
            />
            <Stat
              label="Cost floor"
              value={s.floor_enforced ? "Enforced" : "Not binding"}
              sub="discount never breaches cost + 20%"
              tone={s.floor_enforced ? "warn" : "default"}
            />
          </div>

          <Card
            title="Targeted non-buyers"
            subtitle="Ranked by modelled conversion probability — the classifier scores each customer from their own purchase history"
          >
            <Table
              columns={[
                {
                  key: "sel",
                  label: "",
                  render: (r) => (
                    <input
                      type="checkbox"
                      className="h-4 w-4 rounded border-slate-300"
                      checked={selected.has(r.id)}
                      onChange={() => toggle(r.id)}
                    />
                  ),
                },
                { key: "customer_name", label: "Customer" },
                { key: "dish_name", label: "Dish" },
                {
                  key: "original_price",
                  label: "Normal",
                  align: "right",
                  render: (r) => (
                    <span className="text-slate-400 line-through">
                      {money(r.original_price)}
                    </span>
                  ),
                },
                {
                  key: "offer_price",
                  label: "Offer",
                  align: "right",
                  render: (r) => (
                    <span className="font-semibold text-brand-700">
                      {money(r.offer_price)}
                    </span>
                  ),
                },
                {
                  key: "discount_pct",
                  label: "Discount",
                  align: "right",
                  render: (r) => (
                    <span>
                      {r.discount_pct}%
                      {r.floor_enforced && (
                        <span className="ml-1 text-xs text-amber-600">(capped)</span>
                      )}
                    </span>
                  ),
                },
                {
                  key: "conversion_probability",
                  label: "P(convert)",
                  align: "right",
                  render: (r) => {
                    const p = r.conversion_probability;
                    const tone =
                      p > 0.3 ? "green" : p > 0.15 ? "amber" : "slate";
                    return <Badge tone={tone}>{(p * 100).toFixed(1)}%</Badge>;
                  },
                },
                {
                  key: "status",
                  label: "Status",
                  render: (r) =>
                    r.status === "approved" ? (
                      <Badge tone="green">approved</Badge>
                    ) : r.status === "redeemed" ? (
                      <Badge tone="blue">redeemed</Badge>
                    ) : r.status === "rejected" ? (
                      <Badge tone="red">rejected</Badge>
                    ) : (
                      <Badge>pending</Badge>
                    ),
                },
              ]}
              rows={data.offers}
              empty="No offers — run the daily pipeline"
            />
          </Card>
        </div>
      )}
    </Layout>
  );
}
