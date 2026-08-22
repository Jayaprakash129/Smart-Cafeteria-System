import { num } from "../api";

export function Card({ title, subtitle, action, children, className = "" }) {
  return (
    <div className={`card ${className}`}>
      {(title || action) && (
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-3.5">
          <div>
            {title && <h3 className="font-semibold text-slate-800">{title}</h3>}
            {subtitle && <p className="mt-0.5 text-sm text-slate-500">{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      <div className="card-pad">{children}</div>
    </div>
  );
}

export function Stat({ label, value, sub, tone = "default", icon }) {
  const tones = {
    default: "text-slate-900",
    good: "text-emerald-600",
    warn: "text-amber-600",
    bad: "text-rose-600",
    brand: "text-brand-600",
  };
  return (
    <div className="card card-pad">
      <div className="flex items-center gap-2 text-sm text-slate-500">
        {icon && <span className="text-base">{icon}</span>}
        {label}
      </div>
      <div className={`mt-1.5 text-2xl font-semibold tracking-tight ${tones[tone]}`}>
        {value}
      </div>
      {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

export function Badge({ children, tone = "slate" }) {
  const tones = {
    slate: "bg-slate-100 text-slate-700",
    green: "bg-emerald-100 text-emerald-700",
    red: "bg-rose-100 text-rose-700",
    amber: "bg-amber-100 text-amber-800",
    blue: "bg-sky-100 text-sky-700",
    brand: "bg-brand-100 text-brand-700",
  };
  return <span className={`badge ${tones[tone]}`}>{children}</span>;
}

export function Table({ columns, rows, empty = "No data" }) {
  if (!rows?.length) {
    return <div className="py-10 text-center text-sm text-slate-400">{empty}</div>;
  }
  return (
    <div className="-mx-5 overflow-x-auto">
      <table className="min-w-full">
        <thead className="bg-slate-50">
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={`th ${c.align === "right" ? "text-right" : ""}`}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r, i) => (
            <tr key={r.id ?? i} className="hover:bg-slate-50/70">
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={`td ${c.align === "right" ? "text-right tabular-nums" : ""}`}
                >
                  {c.render ? c.render(r) : r[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Loading({ label = "Loading" }) {
  return (
    <div className="flex items-center gap-3 py-16 text-slate-400">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-brand-500" />
      <span className="text-sm">{label}…</span>
    </div>
  );
}

export function ErrorBox({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
      <div className="font-medium">Something went wrong</div>
      <div className="mt-0.5">{String(error.message || error)}</div>
      {onRetry && (
        <button onClick={onRetry} className="btn-ghost mt-2">
          Try again
        </button>
      )}
    </div>
  );
}

export function Bar({ value, max, tone = "brand" }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  const tones = {
    brand: "bg-brand-500",
    amber: "bg-amber-500",
    rose: "bg-rose-500",
    sky: "bg-sky-500",
  };
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
      <div className={`h-full rounded-full ${tones[tone]}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Progress({ label, value, max, hint, tone }) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-sm">
        <span className="text-slate-600">{label}</span>
        <span className="font-medium tabular-nums text-slate-800">
          {num(value)}
          {hint && <span className="ml-1 text-xs font-normal text-slate-400">{hint}</span>}
        </span>
      </div>
      <Bar value={value} max={max} tone={tone} />
    </div>
  );
}
