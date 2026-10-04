const TOKEN_KEY = "sc_token";
const USER_KEY = "sc_user";
const INSTITUTION_KEY = "sc_admin_institution";

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const getUser = () => {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || "null");
  } catch {
    return null;
  }
};

export function setSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

// A super_admin isn't pinned to one institution, so the Kitchen-role pages
// (which never pass institution_id themselves) have nothing to scope to and
// previously 400'd with "super_admin must specify institution_id" the
// moment a super_admin opened "Kitchen View". getSelectedInstitution /
// setSelectedInstitution back an explicit picker (see Layout.jsx); when
// nothing has been picked yet, ensureInstitutionId() below falls back to
// the first active institution automatically.
export const getSelectedInstitution = () => {
  const v = localStorage.getItem(INSTITUTION_KEY);
  return v ? Number(v) : null;
};
export const setSelectedInstitution = (id) => {
  if (id == null) localStorage.removeItem(INSTITUTION_KEY);
  else localStorage.setItem(INSTITUTION_KEY, String(id));
};

let defaultInstitutionPromise = null;
async function ensureInstitutionId() {
  const existing = getSelectedInstitution();
  if (existing != null) return existing;
  if (!defaultInstitutionPromise) {
    defaultInstitutionPromise = rawRequest("/admin/institutions")
      .then((rows) => {
        const first = (rows || []).find((r) => r.active) || rows?.[0];
        if (first) setSelectedInstitution(first.id);
        return first?.id ?? null;
      })
      .catch(() => null);
  }
  return defaultInstitutionPromise;
}

function appendQueryParam(path, key, value) {
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}${key}=${encodeURIComponent(value)}`;
}

// Raw fetch wrapper with no institution auto-injection, used internally so
// ensureInstitutionId() itself doesn't recurse into request().
async function rawRequest(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error("Server unreachable - check that the backend is running.");
  }

  // A 401 only means the session has actually expired when a token was sent
  // with the request. Without this check, a wrong password on the login
  // screen itself (which also returns 401, with no token attached) was
  // being shown as "Session expired - please sign in again" instead of the
  // real "Incorrect email or password".
  if (res.status === 401 && token) {
    clearSession();
    window.location.hash = "#/login";
    throw new Error("Session expired - please sign in again");
  }

  const text = await res.text();
  // Check res.ok and parse defensively: an unhandled backend exception (a
  // bare 500) returns a plain-text body like "Internal Server Error", not
  // JSON. Parsing that unconditionally used to throw "Unexpected token
  // 'I'... is not valid JSON" -- a confusing error about the error -- instead
  // of surfacing the actual status code and response body.
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      if (!res.ok) {
        throw new Error(`Request failed (${res.status}): ${text.slice(0, 300)}`);
      }
      // A 2xx with a non-JSON body isn't expected from this API; fall
      // through and return null rather than crashing the caller.
    }
  }
  if (!res.ok) {
    throw new Error(formatApiError(data, res.status));
  }
  return data;
}

function formatApiError(data, status) {
  const detail = data?.detail;
  if (typeof detail === "string") return detail;
  // FastAPI/Pydantic 422 responses carry detail as a list of
  // {loc, msg, type} objects, which previously rendered as the literal
  // string "[object Object]" in the UI.
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : null;
        return field ? `${field}: ${d.msg}` : d.msg;
      })
      .join("; ");
  }
  return `Request failed (${status})`;
}

async function request(path, opts = {}) {
  const user = getUser();
  const isKitchenPath = path.startsWith("/kitchen");
  if (user?.role === "super_admin" && isKitchenPath && !path.includes("institution_id=")) {
    const instId = await ensureInstitutionId();
    if (instId != null) path = appendQueryParam(path, "institution_id", instId);
  }
  return rawRequest(path, opts);
}

export const api = {
  get: (p) => request(p),
  post: (p, body) => request(p, { method: "POST", body }),
  patch: (p, body) => request(p, { method: "PATCH", body }),

  login: async (email, password) => {
    const data = await rawRequest("/auth/login", {
      method: "POST",
      body: { email, password },
    });
    setSession(data.access_token, data.user);
    return data.user;
  },
  demoAccounts: () => request("/auth/demo-accounts"),
};

export const money = (n) =>
  `₹${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

export const num = (n, d = 0) =>
  Number(n || 0).toLocaleString("en-IN", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  });
