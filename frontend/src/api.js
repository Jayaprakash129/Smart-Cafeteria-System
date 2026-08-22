const TOKEN_KEY = "sc_token";
const USER_KEY = "sc_user";

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

async function request(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`/api${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401) {
    clearSession();
    window.location.hash = "#/login";
    throw new Error("Session expired - please sign in again");
  }
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    throw new Error(data?.detail || `Request failed (${res.status})`);
  }
  return data;
}

export const api = {
  get: (p) => request(p),
  post: (p, body) => request(p, { method: "POST", body }),
  patch: (p, body) => request(p, { method: "PATCH", body }),

  login: async (email, password) => {
    const data = await request("/auth/login", {
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
