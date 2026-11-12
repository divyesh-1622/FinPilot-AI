export const API: string = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export const getToken = (): string | null =>
  typeof window === "undefined" ? null : localStorage.getItem("fp_token");
export const setToken = (t: string): void => localStorage.setItem("fp_token", t);
export const clearToken = (): void => localStorage.removeItem("fp_token");

export async function api<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...((opts.headers as Record<string, string>) ?? {}) };
  const token = getToken();
  if (token) headers.Authorization = "Bearer " + token;
  if (opts.body && !(opts.body instanceof FormData)) headers["Content-Type"] = "application/json";

  const r = await fetch(API + path, { ...opts, headers });
  if (r.status === 401 || r.status === 403) {
    clearToken();
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new Error("Session expired");
  }
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(typeof d.detail === "string" ? d.detail : "Request failed: " + path);
  }
  return r.json();
}