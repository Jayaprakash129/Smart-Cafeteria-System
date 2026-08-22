import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

const HOME = {
  super_admin: "/admin",
  kitchen_manager: "/kitchen",
  coordinator: "/kitchen",
  ngo_partner: "/ngo",
  customer: "/app",
};

const QUICK = [
  { role: "Kitchen Manager", email: "kitchen.corporate@smartcafeteria.io", password: "kitchen123", note: "Corporate cafeteria — the main operational role", icon: "🍳" },
  { role: "Super Admin", email: "admin@smartcafeteria.io", password: "admin123", note: "Cross-institution oversight & engine monitoring", icon: "🌐" },
  { role: "NGO Partner", email: "ngo1@smartcafeteria.io", password: "ngo123", note: "Annadhanam Trust — surplus pickup portal", icon: "🤝" },
  { role: "Student / Employee", email: "user1@smartcafeteria.io", password: "user123", note: "Mobile ordering with personalised offers", icon: "🍽️" },
  { role: "Kitchen (College)", email: "kitchen.college@smartcafeteria.io", password: "kitchen123", note: "Trend-sensitive segment", icon: "🎓" },
  { role: "Coordinator", email: "coord.corporate@smartcafeteria.io", password: "coord123", note: "Client-side read-only view", icon: "📋" },
];

export default function Login() {
  const [email, setEmail] = useState("kitchen.corporate@smartcafeteria.io");
  const [password, setPassword] = useState("kitchen123");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  const submit = async (e, creds) => {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await api.login(
        creds?.email ?? email,
        creds?.password ?? password
      );
      navigate(HOME[user.role] || "/app");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-100 via-white to-brand-50 p-6">
      <div className="grid w-full max-w-5xl gap-6 lg:grid-cols-2">
        <div className="card card-pad">
          <div className="mb-6 flex items-center gap-3">
            <span className="text-3xl">🍽️</span>
            <div>
              <h1 className="text-xl font-semibold text-slate-900">Smart Cafeteria</h1>
              <p className="text-sm text-slate-500">
                AI-driven forecasting, pricing & surplus redistribution
              </p>
            </div>
          </div>

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">
                Email
              </label>
              <input
                className="input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="username"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">
                Password
              </label>
              <input
                className="input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>

            {error && (
              <div className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">
                {error}
              </div>
            )}

            <button className="btn-primary w-full" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <p className="mt-5 text-xs leading-relaxed text-slate-400">
            Role-based access control is enforced server-side: each role sees only its
            own institution's data, and cross-institution requests are rejected.
          </p>
        </div>

        <div className="card card-pad">
          <h2 className="font-semibold text-slate-800">Demo accounts</h2>
          <p className="mb-4 mt-0.5 text-sm text-slate-500">
            One click signs you in as that role.
          </p>
          <div className="space-y-2">
            {QUICK.map((q) => (
              <button
                key={q.email}
                onClick={(e) => submit(e, q)}
                disabled={busy}
                className="flex w-full items-start gap-3 rounded-lg border border-slate-200 p-3 text-left transition-colors hover:border-brand-300 hover:bg-brand-50/50 disabled:opacity-50"
              >
                <span className="text-lg">{q.icon}</span>
                <span className="min-w-0">
                  <span className="block text-sm font-medium text-slate-800">
                    {q.role}
                  </span>
                  <span className="block truncate text-xs text-slate-500">{q.note}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
