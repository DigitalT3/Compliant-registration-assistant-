// Typed fetch wrapper: sends the demo-user header (not production auth) and unwraps the error envelope.
const BASE = (import.meta.env.VITE_API_BASE as string | undefined) || "";

let demoUser = localStorage.getItem("cra.user") || "demo.emp.a1";

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
      headers: { "Content-Type": "application/json", "X-Demo-User": demoUser },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "network", "Backend not reachable");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const e = data?.error || {};
    throw new ApiError(res.status, e.code || "error", e.message || res.statusText, e.request_id);
  }
  return data as T;
}

export const get = <T = any>(p: string, params?: Record<string, any>) => api<T>("GET", p, undefined, params);
export const post = <T = any>(p: string, b?: unknown) => api<T>("POST", p, b ?? {});
export const put = <T = any>(p: string, b: unknown) => api<T>("PUT", p, b);
