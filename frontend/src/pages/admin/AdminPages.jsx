import { useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { api, money, num } from "../../api";
import Layout from "../../components/Layout";
import { Badge, Card, ErrorBox, Loading, Stat, Table } from "../../components/ui";

const COLORS = ["#2f8c5c", "#4fa877", "#7fc39c", "#aedac0", "#d6ecdf"];

/* ---------------------------------------------------------------- Dashboard */
export function AdminDashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () => api.get("/admin/dashboard").then(setData).catch(setError);
  useEffect(() => {
    load();
  }, []);

  const runAll = async () => {
    setBusy(true);
    try {
      await api.post("/admin/pipeline/run", {});
      await load();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const t = data?.totals;
  const fairness = data?.ngo_fairness;

  return (
    <Layout
      title="Global Dashboard"
      subtitle="Across all client institutions"
      actions={
        <button className="btn-primary" disabled={busy} onClick={runAll}>
          {busy ? "Running…" : "▶ Run pipeline (all sites)"}
        </button>
      }
    >
      <ErrorBox error={error} onRetry={load} />
      {!data ? (
        <Loading />
      ) : (
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label="Total profit (30d)" value={money(t.profit)} sub={`${t.margin_pct}% margin`} tone="good" />
            <Stat label="Revenue" value={money(t.revenue)} sub={`${num(t.units_sold)} units`} />
            <Stat label="Waste rate" value={`${t.waste_pct}%`} sub="of everything prepared" tone={t.waste_pct > 15 ? "bad" : "warn"} />
            <Stat label="Meals donated" value={num(t.meals_donated)} sub={`${t.ngo_partners} NGO partners`} tone="brand" />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2" title="Institution performance" subtitle="Profit and waste by site">
              <Table
                columns={[
                  {
                    key: "name",
                    label: "Institution",
                    render: (r) => (
                      <div>
                        <div className="font-medium text-slate-800">{r.name}</div>
                        <div className="text-xs text-slate-400">
                          {r.segment} · {num(r.headcount)} people
                        </div>
                      </div>
                    ),
                  },
                  { key: "revenue", label: "Revenue", align: "right", render: (r) => money(r.revenue) },
                  {
                    key: "profit",
                    label: "Profit",
                    align: "right",
                    render: (r) => <span className="font-medium text-emerald-600">{money(r.profit)}</span>,
                  },
                  { key: "margin_pct", label: "Margin", align: "right", render: (r) => `${r.margin_pct}%` },
                  {
                    key: "waste_pct",
                    label: "Waste",
                    align: "right",
                    render: (r) => (
                      <Badge tone={r.waste_pct > 15 ? "red" : r.waste_pct > 10 ? "amber" : "green"}>
                        {r.waste_pct}%
                      </Badge>
                    ),
                  },
                ]}
                rows={data.institutions}
              />
            </Card>

            <Card
              title="NGO distribution equity"
              subtitle={`Gini ${fairness?.gini_coefficient ?? "—"} (0 = perfectly equal)`}
            >
              <div className="h-52">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={fairness?.partners || []}
                      dataKey="quantity"
                      nameKey="ngo_name"
                      innerRadius={45}
                      outerRadius={78}
                      paddingAngle={2}
                    >
                      {(fairness?.partners || []).map((_, i) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v, n) => [`${num(v)} meals`, n]} contentStyle={{ borderRadius: 8, fontSize: 13 }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="mt-2 space-y-1">
                {(fairness?.partners || []).map((p, i) => (
                  <div key={p.ngo_id} className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2 truncate text-slate-600">
                      <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: COLORS[i % COLORS.length] }} />
                      <span className="truncate">{p.ngo_name}</span>
                    </span>
                    <span className="ml-2 shrink-0 font-medium text-slate-800">{p.share_pct}%</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
      )}
    </Layout>
  );
}

/* ------------------------------------------------------------ Institutions */
export function Institutions() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get("/admin/institutions").then(setRows).catch(setError);
  }, []);

  return (
    <Layout title="Institution Management" subtitle="Client sites on the platform">
      <ErrorBox error={error} />
      {!rows ? (
        <Loading />
      ) : (
        <Card title="Institutions">
          <Table
            columns={[
              { key: "name", label: "Name" },
              {
                key: "segment",
                label: "Segment",
                render: (r) => <Badge tone="brand">{r.segment}</Badge>,
              },
              { key: "city", label: "City" },
              { key: "headcount", label: "Headcount", align: "right", render: (r) => num(r.headcount) },
              { key: "dishes", label: "Dishes", align: "right" },
              { key: "customers", label: "Customers", align: "right", render: (r) => num(r.customers) },
              { key: "staff", label: "Staff", align: "right" },
              {
                key: "active",
                label: "Status",
                render: (r) => (r.active ? <Badge tone="green">active</Badge> : <Badge tone="red">inactive</Badge>),
              },
            ]}
            rows={rows}
          />
        </Card>
      )}
    </Layout>
  );
}

/* --------------------------------------------------------------------- NGOs */
export function NGOPartners() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get("/admin/ngos").then(setRows).catch(setError);
  }, []);

  return (
    <Layout title="NGO Partner Management" subtitle="Verified recipients and their reliability">
      <ErrorBox error={error} />
      {!rows ? (
        <Loading />
      ) : (
        <Card title="Partners" subtitle="Reliability is measured from actual pickup behaviour, never self-reported">
          <Table
            columns={[
              {
                key: "name",
                label: "NGO",
                render: (r) => (
                  <div>
                    <div className="font-medium text-slate-800">{r.name}</div>
                    <div className="text-xs text-slate-400">{r.contact_person} · {r.phone}</div>
                  </div>
                ),
              },
              { key: "daily_need_meals", label: "Daily need", align: "right", render: (r) => num(r.daily_need_meals) },
              { key: "beneficiaries", label: "Beneficiaries", align: "right", render: (r) => num(r.beneficiaries) },
              { key: "meals_30d", label: "Meals (30d)", align: "right", render: (r) => num(r.meals_30d) },
              { key: "pickups_30d", label: "Pickups", align: "right" },
              {
                key: "reliability_score",
                label: "Reliability",
                align: "right",
                render: (r) => (
                  <Badge tone={r.reliability_score > 0.85 ? "green" : r.reliability_score > 0.7 ? "amber" : "red"}>
                    {(r.reliability_score * 100).toFixed(0)}%
                  </Badge>
                ),
              },
              {
                key: "accepts_veg_only",
                label: "Dietary",
                render: (r) => (r.accepts_veg_only ? <Badge tone="green">veg only</Badge> : <Badge>any</Badge>),
              },
            ]}
            rows={rows}
          />
        </Card>
      )}
    </Layout>
  );
}

/* ------------------------------------------------------------------ Engines */
export function Engines() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () => api.get("/admin/engines").then(setData).catch(setError);
  useEffect(() => {
    load();
  }, []);

  const retrain = async () => {
    setBusy(true);
    try {
      await api.post("/admin/models/retrain", {});
      await load();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Layout
      title="Engines & Model Monitoring"
      subtitle="Health and measured accuracy of every intelligence-layer component"
      actions={
        <button className="btn-primary" disabled={busy} onClick={retrain}>
          {busy ? "Retraining…" : "↻ Retrain all models"}
        </button>
      }
    >
      <ErrorBox error={error} onRetry={load} />
      {!data ? (
        <Loading />
      ) : (
        <div className="space-y-5">
          <div className="rounded-lg border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-900">
            <strong>LLM narration:</strong>{" "}
            {data.llm_narration.ollama_available
              ? "Ollama connected — briefings are LLM-written."
              : "Ollama not running — briefings use deterministic templates."}{" "}
            {data.llm_narration.note}.
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            {data.engines.map((e) => (
              <Card key={e.name} title={e.name} subtitle={e.type}>
                <div className="mb-3">
                  <Badge tone={e.status === "trained" ? "green" : e.status === "operational" ? "blue" : "slate"}>
                    {e.status}
                  </Badge>
                </div>
                <dl className="space-y-1.5">
                  {Object.entries(e.metrics || {})
                    .filter(([k]) => k !== "feature_importance")
                    .map(([k, v]) => (
                      <div key={k} className="flex justify-between gap-4 text-sm">
                        <dt className="text-slate-500">{k.replace(/_/g, " ")}</dt>
                        <dd className="text-right font-medium tabular-nums text-slate-800">
                          {typeof v === "object" ? JSON.stringify(v) : String(v)}
                        </dd>
                      </div>
                    ))}
                </dl>
                {e.metrics?.feature_importance && (
                  <div className="mt-4 border-t border-slate-100 pt-3">
                    <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
                      Top features
                    </div>
                    {Object.entries(e.metrics.feature_importance).slice(0, 5).map(([k, v]) => (
                      <div key={k} className="mb-1.5">
                        <div className="flex justify-between text-xs text-slate-600">
                          <span>{k.replace(/_/g, " ")}</span>
                          <span className="tabular-nums">{(v * 100).toFixed(1)}%</span>
                        </div>
                        <div className="mt-0.5 h-1.5 overflow-hidden rounded-full bg-slate-100">
                          <div className="h-full bg-brand-500" style={{ width: `${v * 100}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            ))}
          </div>
        </div>
      )}
    </Layout>
  );
}

/* ------------------------------------------------------------------- Impact */
export function Impact() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get("/admin/impact").then(setData).catch(setError);
  }, []);

  return (
    <Layout title="Impact Report" subtitle="Headline outcome metrics for the project paper">
      <ErrorBox error={error} />
      {!data ? (
        <Loading />
      ) : (
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label="Surplus redistributed" value={`${data.waste.redistribution_coverage_pct}%`} sub={`${num(data.waste.surplus_redistributed)} of ${num(data.waste.surplus_total)} meals`} tone="good" />
            <Stat label="Waste rate" value={`${data.waste.baseline_waste_pct}%`} sub={`${num(data.waste.units_wasted)} units`} tone="warn" />
            <Stat label="Profit" value={money(data.profit.profit)} sub={`${data.profit.margin_pct}% margin`} tone="good" />
            <Stat label="Meals donated" value={num(data.social.meals_donated)} sub={`${data.social.ngo_partners_served} partners served`} tone="brand" />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card title="Forecast quality">
              <Metric label="R² (held-out)" value={data.model_quality.forecast_r2} />
              <Metric label="MAPE" value={`${data.model_quality.forecast_mape}%`} />
              <Metric
                label="Improvement over naive baseline"
                value={`${data.model_quality.forecast_improvement_over_naive_pct}%`}
                highlight
              />
              <p className="mt-3 text-xs leading-relaxed text-slate-500">
                Baseline is the rolling 7-day mean — the standard "what did we sell
                last week" heuristic a cafeteria would otherwise use.
              </p>
            </Card>

            <Card title="Trial conversion">
              <Metric label="Offers issued" value={num(data.conversion.offers_issued)} />
              <Metric label="Expected conversions" value={num(data.conversion.expected_conversions, 1)} />
              <Metric label="Model AUC" value={data.conversion.model_auc} />
              <Metric label="Lift vs blanket discount" value={`${data.conversion.lift_vs_blanket_discount}×`} highlight />
              <p className="mt-3 text-xs leading-relaxed text-slate-500">
                Targeting the top 20% by modelled probability converts this many times
                better than discounting everyone equally.
              </p>
            </Card>

            <Card title="Distribution equity">
              <Metric label="Gini coefficient" value={data.social.fairness.gini_coefficient} highlight />
              <Metric label="Active partners" value={data.social.fairness.active_partners} />
              <Metric label="Total allocated" value={num(data.social.fairness.total_allocated)} />
              <p className="mt-3 text-xs leading-relaxed text-slate-500">
                0 means surplus is split perfectly evenly; 1 means a single NGO
                receives everything — the practice this system replaces.
              </p>
            </Card>
          </div>

          <Card title="Price floor enforcement" subtitle="The constraint that makes dynamic pricing safe">
            <div className="flex flex-wrap gap-8">
              <Metric label="Recommendations issued" value={num(data.profit.price_recommendations_issued)} />
              <Metric label="Held at cost + 20% floor" value={num(data.profit.floor_enforced_count)} highlight />
            </div>
          </Card>
        </div>
      )}
    </Layout>
  );
}

function Metric({ label, value, highlight }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-slate-100 py-2 last:border-0">
      <span className="text-sm text-slate-600">{label}</span>
      <span className={`font-semibold tabular-nums ${highlight ? "text-brand-600" : "text-slate-900"}`}>
        {value ?? "—"}
      </span>
    </div>
  );
}

/* -------------------------------------------------------------------- Audit */
export function Audit() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get("/admin/audit?limit=150").then(setRows).catch(setError);
  }, []);

  return (
    <Layout title="Agent Audit Log" subtitle="Every autonomous decision the system has made">
      <ErrorBox error={error} />
      {!rows ? (
        <Loading />
      ) : (
        <Card title="Recent agent actions" subtitle={`${rows.length} entries`}>
          <Table
            columns={[
              {
                key: "agent",
                label: "Agent",
                render: (r) => (
                  <div>
                    <div className="font-medium text-slate-800">{r.agent}</div>
                    <div className="text-xs text-slate-400">{r.action}</div>
                  </div>
                ),
              },
              { key: "institution", label: "Institution", render: (r) => r.institution || "—" },
              {
                key: "detail",
                label: "Detail",
                render: (r) => <span className="text-xs text-slate-600">{r.detail?.slice(0, 110)}</span>,
              },
              { key: "records_affected", label: "Records", align: "right" },
              { key: "duration_ms", label: "Time", align: "right", render: (r) => `${num(r.duration_ms)} ms` },
              {
                key: "status",
                label: "Status",
                render: (r) => (
                  <Badge tone={r.status === "success" ? "green" : r.status === "error" ? "red" : "amber"}>
                    {r.status}
                  </Badge>
                ),
              },
              {
                key: "run_id",
                label: "Run",
                render: (r) => <span className="font-mono text-xs text-slate-400">{r.run_id}</span>,
              },
            ]}
            rows={rows}
          />
        </Card>
      )}
    </Layout>
  );
}
