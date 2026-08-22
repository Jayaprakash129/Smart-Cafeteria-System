import { useEffect, useState } from "react";
import {
  Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { api, money, num } from "../../api";
import Layout from "../../components/Layout";
import { Card, ErrorBox, Loading, Stat, Table } from "../../components/ui";

export default function Reports() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [days, setDays] = useState(30);

  useEffect(() => {
    setData(null);
    api.get(`/kitchen/reports?days=${days}`).then(setData).catch(setError);
  }, [days]);

  const t = data?.totals;
  const daily = (data?.daily || []).map((d) => ({
    ...d,
    label: d.date.slice(5),
  }));

  return (
    <Layout
      title="Sales & Profit Report"
      subtitle={data ? `${data.institution} · ${data.segment} segment` : ""}
      actions={
        <select
          className="input w-auto py-1.5"
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
        >
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
          <option value={365}>Last year</option>
        </select>
      }
    >
      <ErrorBox error={error} />
      {!data ? (
        <Loading />
      ) : (
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            <Stat label="Revenue" value={money(t.revenue)} sub={`${num(t.units_sold)} units sold`} />
            <Stat label="Profit" value={money(t.profit)} sub={`${t.margin_pct}% margin`} tone="good" />
            <Stat label="Cost" value={money(t.cost)} sub="ingredients prepared" />
            <Stat
              label="Waste"
              value={`${t.waste_pct}%`}
              sub={`${num(t.units_wasted)} units`}
              tone={t.waste_pct > 15 ? "bad" : t.waste_pct > 10 ? "warn" : "good"}
            />
            <Stat label="Window" value={`${days}d`} sub={`${daily.length} service days`} />
          </div>

          <Card title="Revenue and profit" subtitle="Daily trend across the selected window">
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={daily}>
                  <defs>
                    <linearGradient id="rev" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#2f8c5c" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#2f8c5c" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                  <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} minTickGap={20} />
                  <YAxis tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} />
                  <Tooltip
                    contentStyle={{ borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 13 }}
                    formatter={(v, k) => [money(v), k]}
                  />
                  <Area type="monotone" dataKey="revenue" stroke="#2f8c5c" fill="url(#rev)" strokeWidth={2} />
                  <Area type="monotone" dataKey="profit" stroke="#0284c7" fill="none" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card title="Waste percentage" subtitle="Leftover units as a share of everything prepared">
            <div className="h-52">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={daily}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                  <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} minTickGap={20} />
                  <YAxis tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} unit="%" />
                  <Tooltip
                    contentStyle={{ borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 13 }}
                    formatter={(v) => [`${v}%`, "Waste"]}
                  />
                  <Line type="monotone" dataKey="waste_pct" stroke="#f59e0b" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card title="Most profitable dishes" subtitle="Ranked by contribution over the window">
            <Table
              columns={[
                { key: "dish_name", label: "Dish" },
                { key: "sold", label: "Sold", align: "right", render: (r) => num(r.sold) },
                { key: "revenue", label: "Revenue", align: "right", render: (r) => money(r.revenue) },
                { key: "cost", label: "Cost", align: "right", render: (r) => money(r.cost) },
                {
                  key: "profit",
                  label: "Profit",
                  align: "right",
                  render: (r) => (
                    <span className={r.profit >= 0 ? "font-medium text-emerald-600" : "font-medium text-rose-600"}>
                      {money(r.profit)}
                    </span>
                  ),
                },
                { key: "leftover", label: "Wasted", align: "right", render: (r) => num(r.leftover) },
              ]}
              rows={data.top_dishes}
            />
          </Card>
        </div>
      )}
    </Layout>
  );
}
