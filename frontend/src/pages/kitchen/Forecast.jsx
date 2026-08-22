import { useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api, num } from "../../api";
import Layout from "../../components/Layout";
import { Card, ErrorBox, Loading, Stat, Table } from "../../components/ui";

export default function Forecast() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [day, setDay] = useState(0);

  useEffect(() => {
    api.get("/kitchen/forecast").then(setData).catch(setError);
  }, []);

  const week = data?.week || [];
  const m = data?.model_metrics || {};
  const sel = week[day];

  return (
    <Layout title="Demand Forecast" subtitle={data?.institution || ""}>
      <ErrorBox error={error} />
      {!data ? (
        <Loading label="Running forecasts for 7 days" />
      ) : (
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label="Model" value="XGBoost" sub={`trained ${m.trained_at || "—"}`} tone="brand" />
            <Stat label="R² (held-out)" value={m.r2 ?? "—"} sub={`MAPE ${m.mape ?? "—"}%`} tone="good" />
            <Stat
              label="vs naive baseline"
              value={`${m.improvement_over_naive_pct ?? "—"}% better`}
              sub="against rolling 7-day mean"
              tone="good"
            />
            <Stat label="Test samples" value={num(m.n_test)} sub={`${num(m.n_train)} training rows`} />
          </div>

          <Card title="Seven-day outlook" subtitle="Total predicted units per day">
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={week.map((w, i) => ({ ...w, i }))}
                  onClick={(e) => e?.activeTooltipIndex != null && setDay(e.activeTooltipIndex)}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                  <XAxis
                    dataKey="day_name"
                    tick={{ fontSize: 12, fill: "#64748b" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis tick={{ fontSize: 12, fill: "#64748b" }} axisLine={false} tickLine={false} />
                  <Tooltip
                    contentStyle={{ borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 13 }}
                    formatter={(v, k) => [num(v), k === "total_demand" ? "Forecast" : "Prepare"]}
                  />
                  <Bar dataKey="total_demand" fill="#2f8c5c" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="total_prep" fill="#aedac0" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-3 flex gap-4 text-xs text-slate-500">
              <span className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-sm bg-brand-600" /> Forecast demand
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-sm bg-brand-200" /> Recommended prep
              </span>
            </div>
          </Card>

          <Card
            title={`Dish breakdown — ${sel?.day_name || ""} ${sel?.date || ""}`}
            subtitle="Click a bar above to change day. The 80% range comes from each dish's own forecast error, not its raw demand spread."
          >
            <Table
              columns={[
                { key: "dish_name", label: "Dish" },
                { key: "category", label: "Category" },
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
              rows={sel?.dishes || []}
            />
          </Card>
        </div>
      )}
    </Layout>
  );
}
