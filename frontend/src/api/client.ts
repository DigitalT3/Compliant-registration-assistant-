// Typed fetch wrapper: sends the bearer token (or, in demo mode, the demo-user header) and unwraps the error envelope.
const BASE = (import.meta.env.VITE_API_BASE as string | undefined) || "";

let demoUser = localStorage.getItem("cra.user") || "";
let token = sessionStorage.getItem("cra.token") || "";   // session storage: gone when the tab is closed

/** Remember the signed-in session token (null clears it). */
export function setToken(t: string | null) {
  token = t || "";
  if (t) sessionStorage.setItem("cra.token", t); else sessionStorage.removeItem("cra.token");
}
export const hasToken = () => !!token;

/** Forget the whole session (token and demo user). */
export function clearSession() {
  setToken(null);
  demoUser = "";
  localStorage.removeItem("cra.user");
}

const authHeaders = (): Record<string, string> =>
  token ? { Authorization: `Bearer ${token}` } : demoUser ? { "X-Demo-User": demoUser } : {};

/** Set the demo user whose role the backend enforces. */
export function setDemoUser(id: string) {
  demoUser = id;
  localStorage.setItem("cra.user", id);
}
export function getDemoUser() {
  return demoUser;
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public requestId?: string) {
    super(message);
  }
}

export async function api<T = any>(method: string, path: string, body?: unknown, params?: Record<string, any>): Promise<T> {
  const qs = params
    ? "?" + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== "" && v !== null).map(([k, v]) => [k, String(v)])).toString()
    : "";
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}${qs}`, {
      method,
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "network", "Backend not reachable");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const e = data?.error || {};
    if (res.status === 401 && (token || demoUser) && !path.startsWith("/api/auth/login")) {
      clearSession();                                   // expired or revoked: send the user back to sign-in
      window.dispatchEvent(new CustomEvent("cra:signed-out", { detail: e.code }));
    }
    throw new ApiError(res.status, e.code || "error", e.message || res.statusText, e.request_id);
  }
  return data as T;
}

export const get = <T = any>(p: string, params?: Record<string, any>) => api<T>("GET", p, undefined, params);
export const post = <T = any>(p: string, b?: unknown) => api<T>("POST", p, b ?? {});
export const put = <T = any>(p: string, b: unknown) => api<T>("PUT", p, b);

/** Download a CSV export (the demo-user header cannot be sent by a plain link). */
export async function download(path: string, filename: string, params?: Record<string, any>) {
  const qs = params ? "?" + new URLSearchParams(Object.entries(params).filter(([, v]) => v).map(([k, v]) => [k, String(v)])).toString() : "";
  const res = await fetch(`${BASE}${path}${qs}`, { headers: authHeaders() });
  if (!res.ok) {
    const e = (await res.json().catch(() => ({})))?.error || {};
    throw new ApiError(res.status, e.code || "error", e.message || res.statusText, e.request_id);
  }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}
