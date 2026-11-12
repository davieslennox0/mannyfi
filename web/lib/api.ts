// Thin client for the MannyFi server. The session token lives in
// localStorage; it only proves "this browser signed in", and expires server-side.

// Empty = same origin (production: Caddy routes /api, /mcp and OAuth to the server).
// For local dev set NEXT_PUBLIC_API_URL=http://localhost:8760.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

const TOKEN_KEY = "mf.session";
const ACCOUNT_KEY = "mf.account";

export function saveSession(token: string, account: string) {
  try {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(ACCOUNT_KEY, account);
  } catch {}
  notify();
}

function notify() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event("mf-session"));
}

export function clearSession() {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(ACCOUNT_KEY);
  } catch {}
  notify();
}

export function getSession(): { token: string; account: string } | null {
  try {
    const token = localStorage.getItem(TOKEN_KEY);
    const account = localStorage.getItem(ACCOUNT_KEY);
    return token && account ? { token, account } : null;
  } catch {
    return null;
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit & { auth?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (init.auth) {
    const s = getSession();
    if (!s) throw new ApiError(401, "not signed in");
    headers.authorization = `Bearer ${s.token}`;
  }
  const res = await fetch(`${API_URL}${path}`, { ...init, headers: { ...headers, ...(init.headers as object) } });
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {}
  if (!res.ok) {
    const detail = (body as { detail?: string } | null)?.detail;
    throw new ApiError(res.status, detail ?? `request failed (${res.status})`);
  }
  return body as T;
}

export type OrderLeg = {
  index: number;
  symbol: string;
  status: string;
  spend: string;
  receive_estimate: string;
  min_receive: string;
  cost_pct: string | null;
  execution?: string;
  intent_hash?: string;
  sign: { standard: "nep413"; recipient: string; nonce: string; message: string };
};

export type Order = {
  signatures_needed: number;
  batch?: {
    status: string;
    tx_hash: string | null;
    sign: { standard: "nep413"; recipient: string; nonce: string; message: string };
  };
  order_id: string;
  basket_id: string;
  side: "buy" | "sell";
  status: string;
  expires_at: number;
  summary?: string;
  legs: OrderLeg[];
  errors?: Record<string, string>;
};
