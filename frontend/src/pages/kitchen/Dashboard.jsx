import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, money, num } from "../../api";
import Layout from "../../components/Layout";
import { Badge, Card, ErrorBox, Loading, Stat, Table } from "../../components/ui";

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [running, setRunning] = useState(false);
  const [run, setRun] = useState(null);

  const load = async () => {
    setError(null);
    try {
      setData(await api.get("/kitchen/dashboard"));
    } catch (e) {
      setError(e);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const runPipeline = async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await api.post("/admin/pipeline/run", {});
      setRun(res.runs[0]);
      await load();
    } catch (e) {
      setError(e);
    } finally {
      setRunning(false);
    }
  };

  const k = data?.kpis;

  return (
    <Layout
      title="Today's Dashboard"
      subtitle={data ? `${data.institution.name} · ${data.date}` : "Loading"}
      actions={
        <button onClick={runPipeline} disabled={running} className="btn-primary">
          {running ? "Running agents…" : "▶ Run daily pipeline"}
        </button>
      }
    >
      <ErrorBox error={error} onRetry={load} />
      {!data && !error ? (
        <Loading />
      ) : (
        data && (
          <div className="space-y-5">
            {run && (
              <div className="card card-pad border-brand-200 bg-brand-50/60">
                <div className="mb-2 flex items-center gap-2">
                  <Badge tone="brand">Agent run {run.run_id}</Badge>
                  <span className="text-xs text-slate-500">
                    {run.trace.length} agents · {run.duration_ms} ms ·{" "}
                    {run.briefing_source}
                  </span>
                </div>
                <p className="text-sm leading-relaxed text-slate-700">{run.briefing}</p>
              </div>
            )}

            {data.alerts?.length > 0 && (
              <div className="grid gap-2 sm:grid-cols-2">
                {data.alerts.map((a, i) => (
                  <div
                    key={i}
                    className={`rounded-lg border px-4 py-2.5 text-sm ${
                      a.level === "danger"
                        ? "border-rose-200 bg-rose-50 text-rose-800"
                        : a.level === "warning"
                        ? "border-amber-200 bg-amber-50 text-amber-800"
                        : "border-sky-200 bg-sky-50 text-sky-800"
                    }`}
                  >
                    {a.message}
                  </div>
                ))}
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <Stat
                icon="📈"
                label="Forecast demand today"
                value={num(k.forecast_units)}
                sub={`prepare ${num(k.recommended_prep)} units`}
                tone="brand"
              />
              <Stat
                icon="💰"
                label="Yesterday's profit"
                value={money(k.yesterday_profit)}
                sub={`on ${money(k.yesterday_revenue)} revenue`}
                tone="good"
              />
              <Stat
                icon="♻️"
                label="Predicted waste"
                value={`${num(k.predicted_waste_units)} units`}
                sub={`${money(k.value_at_risk)} at risk`}
                tone="warn"
              />
              <Stat
                icon="🤝"
                label="Surplus for NGOs"
                value={`${num(k.surplus_units)} meals`}
                sub={`yesterday's waste ${k.yesterday_waste_pct}%`}
                tone="default"
              />
            </div>

            <div className="grid gap-4 lg:grid-cols-3">
              <Card
                className="lg:col-span-2"
                title="Top forecast dishes"
                subtitle="Predicted demand with recommended preparation quantity"
                action={
                  <Link to="/kitchen/forecast" className="btn-ghost">
                    Full forecast
                  </Link>
                }
              >
                <Table
                  columns={[
                    { key: "dish_name", label: "Dish" },
                    {
                      key: "predicted_demand",
                      label: "Forecast",
                      align: "right",
                      render: (r) => num(r.predicted_demand),
                    },
                    {
                      key: "range",
                      label: "80% range",
                      align: "right",
                      render: (r) => (
                        <span className="text-slate-400">
                          {num(r.lower_bound)}–{num(r.upper_bound)}
                        </span>
                      ),
                    },
                    {
                      key: "recommended_prep",
                      label: "Prepare",
                      align: "right",
                      render: (r) => (
                        <span className="font-medium text-brand-700">
                          {num(r.recommended_prep)}
                        </span>
                      ),
                    },
                  ]}
                  rows={data.top_forecasts}
                  empty="No forecast yet — run the daily pipeline"
                />
              </Card>

              <Card title="Pending decisions" subtitle="Waiting on your approval">
                <div className="space-y-3">
                  <ActionRow
                    to="/kitchen/pricing"
                    label="Price recommendations"
                    count={k.pending_price_approvals}
                    icon="💰"
                  />
                  <ActionRow
                    to="/kitchen/offers"
                    label="Trial-conversion offers"
                    count={k.pending_offers}
                    icon="🎯"
                  />
                  <ActionRow
                    to="/kitchen/surplus"
                    label="Surplus handoff"
                    count={k.surplus_units}
                    unit="meals"
                    icon="♻️"
                  />
                </div>
              </Card>
            </div>
          </div>
        )
      )}
    </Layout>
  );
}

function ActionRow({ to, label, count, unit = "", icon }) {
  return (
    <Link
      to={to}
      className="flex items-center justify-between rounded-lg border border-slate-200 px-3.5 py-3 transition-colors hover:border-brand-300 hover:bg-brand-50/40"
    >
      <span className="flex items-center gap-2.5 text-sm text-slate-700">
        <span>{icon}</span>
        {label}
      </span>
      <span
        className={`text-sm font-semibold ${
          count > 0 ? "text-brand-700" : "text-slate-300"
        }`}
      >
        {num(count)} {unit}
      </span>
    </Link>
  );
}
