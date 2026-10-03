import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import { getUser } from "./api";

import Login from "./pages/Login";
import Dashboard from "./pages/kitchen/Dashboard";
import Pricing from "./pages/kitchen/Pricing";
import Forecast from "./pages/kitchen/Forecast";
import Inventory from "./pages/kitchen/Inventory";
import Offers from "./pages/kitchen/Offers";
import Surplus from "./pages/kitchen/Surplus";
import Reports from "./pages/kitchen/Reports";
import {
  AdminDashboard, Audit, Engines, Impact, Institutions, NGOPartners,
} from "./pages/admin/AdminPages";
import { NGOHistory, NGOProfile, NGOToday } from "./pages/ngo/NGOPages";
import {
  CustomerMenu, CustomerOffers, CustomerOrders, CustomerProfile,
} from "./pages/customer/CustomerPages";

const HOME = {
  super_admin: "/admin",
  kitchen_manager: "/kitchen",
  coordinator: "/kitchen",
  ngo_partner: "/ngo",
  customer: "/app",
};

function Protected({ roles, children }) {
  const user = getUser();
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) {
    return <Navigate to={HOME[user.role] || "/login"} replace />;
  }
  return children;
}

function Landing() {
  const user = getUser();
  return <Navigate to={user ? HOME[user.role] || "/app" : "/login"} replace />;
}

const STAFF = ["kitchen_manager", "super_admin", "coordinator"];
// Cross-institution pages (global dashboard, institution/NGO directories) are
// super_admin only -- the backend now enforces this too, but a coordinator
// should never even see the links or land on a 403 page client-side.
const ADMIN = ["super_admin"];
// Impact and the audit log are scoped server-side to the caller's own
// institution for non-admins, so a coordinator can safely view these.
const IMPACT_AUDIT = ["super_admin", "coordinator"];

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<Landing />} />

        {/* Kitchen Manager */}
        <Route path="/kitchen" element={<Protected roles={STAFF}><Dashboard /></Protected>} />
        <Route path="/kitchen/pricing" element={<Protected roles={STAFF}><Pricing /></Protected>} />
        <Route path="/kitchen/forecast" element={<Protected roles={STAFF}><Forecast /></Protected>} />
        <Route path="/kitchen/inventory" element={<Protected roles={STAFF}><Inventory /></Protected>} />
        <Route path="/kitchen/offers" element={<Protected roles={STAFF}><Offers /></Protected>} />
        <Route path="/kitchen/surplus" element={<Protected roles={STAFF}><Surplus /></Protected>} />
        <Route path="/kitchen/reports" element={<Protected roles={STAFF}><Reports /></Protected>} />

        {/* Super Admin */}
        <Route path="/admin" element={<Protected roles={ADMIN}><AdminDashboard /></Protected>} />
        <Route path="/admin/institutions" element={<Protected roles={ADMIN}><Institutions /></Protected>} />
        <Route path="/admin/ngos" element={<Protected roles={ADMIN}><NGOPartners /></Protected>} />
        <Route path="/admin/engines" element={<Protected roles={ADMIN}><Engines /></Protected>} />
        <Route path="/admin/impact" element={<Protected roles={IMPACT_AUDIT}><Impact /></Protected>} />
        <Route path="/admin/audit" element={<Protected roles={IMPACT_AUDIT}><Audit /></Protected>} />

        {/* NGO Partner */}
        <Route path="/ngo" element={<Protected roles={["ngo_partner", "super_admin"]}><NGOToday /></Protected>} />
        <Route path="/ngo/history" element={<Protected roles={["ngo_partner", "super_admin"]}><NGOHistory /></Protected>} />
        <Route path="/ngo/profile" element={<Protected roles={["ngo_partner", "super_admin"]}><NGOProfile /></Protected>} />

        {/* End Customer */}
        <Route path="/app" element={<Protected roles={["customer", "super_admin"]}><CustomerMenu /></Protected>} />
        <Route path="/app/offers" element={<Protected roles={["customer", "super_admin"]}><CustomerOffers /></Protected>} />
        <Route path="/app/orders" element={<Protected roles={["customer", "super_admin"]}><CustomerOrders /></Protected>} />
        <Route path="/app/profile" element={<Protected roles={["customer", "super_admin"]}><CustomerProfile /></Protected>} />

        <Route path="*" element={<Landing />} />
      </Routes>
    </HashRouter>
  );
}
