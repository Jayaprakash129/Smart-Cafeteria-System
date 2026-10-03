import { useEffect, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  api, clearSession, getSelectedInstitution, getUser, setSelectedInstitution,
} from "../api";

const NAV = {
  super_admin: [
    { to: "/admin", label: "Global Dashboard", icon: "🌐" },
    { to: "/admin/institutions", label: "Institutions", icon: "🏢" },
    { to: "/admin/ngos", label: "NGO Partners", icon: "🤝" },
    { to: "/admin/engines", label: "Engines & Models", icon: "⚙️" },
    { to: "/admin/impact", label: "Impact Report", icon: "📈" },
    { to: "/admin/audit", label: "Agent Audit Log", icon: "📝" },
    { to: "/kitchen", label: "Kitchen View", icon: "🍳" },
  ],
  kitchen_manager: [
    { to: "/kitchen", label: "Today's Dashboard", icon: "📊" },
    { to: "/kitchen/pricing", label: "Menu & Pricing", icon: "💰" },
    { to: "/kitchen/forecast", label: "Demand Forecast", icon: "📈" },
    { to: "/kitchen/inventory", label: "Inventory", icon: "📦" },
    { to: "/kitchen/offers", label: "Trial Offers", icon: "🎯" },
    { to: "/kitchen/surplus", label: "Surplus & NGO", icon: "♻️" },
    { to: "/kitchen/reports", label: "Sales & Profit", icon: "📄" },
  ],
  coordinator: [
    { to: "/kitchen", label: "Overview", icon: "📊" },
    { to: "/kitchen/reports", label: "Performance", icon: "📄" },
    { to: "/admin/impact", label: "Impact", icon: "📈" },
  ],
  ngo_partner: [
    { to: "/ngo", label: "Today's Surplus", icon: "🍲" },
    { to: "/ngo/history", label: "Distribution History", icon: "🗂️" },
    { to: "/ngo/profile", label: "Need Profile", icon: "⚙️" },
  ],
  customer: [
    { to: "/app", label: "Today's Menu", icon: "🍽️" },
    { to: "/app/offers", label: "My Offers", icon: "🎁" },
    { to: "/app/orders", label: "My Orders", icon: "🧾" },
    { to: "/app/profile", label: "Profile", icon: "👤" },
  ],
};

const ROLE_LABEL = {
  super_admin: "Super Admin",
  kitchen_manager: "Kitchen Manager",
  coordinator: "Institution Coordinator",
  ngo_partner: "NGO Partner",
  customer: "Student / Employee",
};

function SidebarContent({ user, links, onNavigate, onSignOut }) {
  return (
    <>
      <div className="flex items-center gap-2.5 border-b border-slate-100 px-5 py-4">
        <span className="text-xl">🍽️</span>
        <div>
          <div className="text-sm font-semibold leading-tight text-slate-800">
            Smart Cafeteria
          </div>
          <div className="text-xs text-slate-400">AI Operations Platform</div>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 p-3">
        {links.map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            onClick={onNavigate}
            end={l.to === "/kitchen" || l.to === "/admin" || l.to === "/ngo" || l.to === "/app"}
            className={({ isActive }) =>
              `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                isActive
                  ? "bg-brand-50 font-medium text-brand-700"
                  : "text-slate-600 hover:bg-slate-50"
              }`
            }
          >
            <span className="text-base">{l.icon}</span>
            {l.label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-slate-100 p-3">
        <div className="rounded-lg bg-slate-50 px-3 py-2.5">
          <div className="truncate text-sm font-medium text-slate-700">
            {user?.full_name}
          </div>
          <div className="text-xs text-slate-500">{ROLE_LABEL[user?.role]}</div>
        </div>
        <button onClick={onSignOut} className="btn-ghost mt-2 w-full">
          Sign out
        </button>
      </div>
    </>
  );
}

/** Lets a super_admin (who isn't pinned to one institution) pick which
 * cafeteria the Kitchen Manager pages should act on -- without this, those
 * pages had no institution to scope to and the API rejected them outright. */
function InstitutionSwitcher() {
  const [institutions, setInstitutions] = useState(null);
  const [selected, setSelected] = useState(getSelectedInstitution());

  useEffect(() => {
    api.get("/admin/institutions").then((rows) => {
      setInstitutions(rows);
      // The Kitchen pages auto-pick the first active institution the
      // moment they make their own API call, via the same localStorage key
      // -- but that happens concurrently with this component mounting, so
      // reading localStorage here first can race and show a blank
      // selector even though the page below already loaded real data.
      // Resolve to the same default independently rather than depending on
      // which of the two finishes first.
      const current = getSelectedInstitution();
      if (current != null) {
        setSelected(current);
      } else if (rows?.length) {
        const first = rows.find((r) => r.active) || rows[0];
        setSelectedInstitution(first.id);
        setSelected(first.id);
      }
    }).catch(() => setInstitutions([]));
  }, []);

  if (!institutions || institutions.length === 0) return null;

  return (
    <select
      className="input w-auto py-1.5 text-xs"
      value={selected ?? ""}
      onChange={(e) => {
        const id = Number(e.target.value);
        setSelectedInstitution(id);
        setSelected(id);
        window.location.reload();
      }}
    >
      <option value="" disabled>
        Select institution…
      </option>
      {institutions.map((i) => (
        <option key={i.id} value={i.id}>
          {i.name}
        </option>
      ))}
    </select>
  );
}

export default function Layout({ children, title, subtitle, actions }) {
  const user = getUser();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const links = NAV[user?.role] || [];

  const signOut = () => {
    clearSession();
    navigate("/login");
  };

  const showInstitutionSwitcher =
    user?.role === "super_admin" && location.pathname.startsWith("/kitchen");

  const context =
    user?.institution?.name || user?.ngo?.name || "Platform-wide";

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-200 bg-white lg:flex">
        <SidebarContent user={user} links={links} onSignOut={signOut} />
      </aside>

      {/* Mobile navigation: below the lg breakpoint the sidebar above is
          hidden entirely with nothing to replace it, which left customers,
          NGOs and every other role with no way to navigate or sign out on a
          phone. This header button + slide-over drawer fills that gap. */}
      {mobileOpen && (
        <div className="fixed inset-0 z-30 lg:hidden">
          <div
            className="absolute inset-0 bg-slate-900/40"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="absolute inset-y-0 left-0 flex w-72 flex-col bg-white shadow-xl">
            <SidebarContent
              user={user}
              links={links}
              onNavigate={() => setMobileOpen(false)}
              onSignOut={signOut}
            />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
          <div className="flex items-center justify-between gap-4 px-4 py-3.5 sm:px-6">
            <div className="flex min-w-0 items-center gap-3">
              <button
                className="btn-ghost -ml-1 px-2 py-2 lg:hidden"
                aria-label="Open navigation menu"
                onClick={() => setMobileOpen(true)}
              >
                ☰
              </button>
              <div className="min-w-0">
                <h1 className="truncate text-lg font-semibold text-slate-900">{title}</h1>
                {subtitle && (
                  <p className="truncate text-sm text-slate-500">{subtitle}</p>
                )}
              </div>
            </div>
            <div className="flex items-center gap-3">
              {showInstitutionSwitcher && <InstitutionSwitcher />}
              {actions}
              <div className="hidden rounded-lg bg-slate-100 px-3 py-1.5 text-xs text-slate-600 sm:block">
                {context}
              </div>
            </div>
          </div>
        </header>

        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
