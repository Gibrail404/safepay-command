"use client";
import { useCallback, useEffect, useState } from "react";

export type Config = { token: string; actor: string };
export const STORAGE_KEY = "safepay-console-session";
export const SIGNED_OUT_EVENT = "safepay-signed-out";
// The server is fixed at build time. Local development sets NEXT_PUBLIC_API_URL; otherwise this is the hosted server.
export const SERVER = (process.env.NEXT_PUBLIC_API_URL || "https://safepay-command-production.up.railway.app").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

function friendly(status: number, detail: unknown): string {
  if (status === 401) return "Your session has ended. Sign in again.";
  if (status === 403) return "Your role does not allow this action.";
  if (status === 429) return "Too many requests. Wait a moment and try again.";
  if (status === 404) return "Not found.";
  if (status === 409) return typeof detail === "string" ? detail : "That conflicts with something already recorded.";
  if (status === 422 || status === 400) return typeof detail === "string" ? detail : "The request was not valid.";
  if (status >= 500) return "The server had a problem. Try again in a moment.";
  return typeof detail === "string" ? detail : "Something went wrong.";
}

export async function call<T>(cfg: Config, path: string, init: { method?: string; body?: unknown; headers?: Record<string, string> } = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(SERVER + path, {
      method: init.method ?? "GET",
      headers: { Authorization: "Bearer " + cfg.token, "X-Actor": cfg.actor || "analyst", ...(init.body ? { "Content-Type": "application/json" } : {}), ...(init.headers ?? {}) },
      body: init.body ? JSON.stringify(init.body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check your connection and try again in a moment.");
  }
  if (!res.ok) {
    let detail: unknown = null;
    try { detail = (await res.json()).detail; } catch { /* no body */ }
    if (res.status === 401 && typeof window !== "undefined") window.dispatchEvent(new Event(SIGNED_OUT_EVENT));      // an expired or revoked session sends the person back to the sign-in page
    throw new ApiError(res.status, friendly(res.status, detail));
  }
  return res.json() as Promise<T>;
}

export type Session = { token: string; user: { email: string; name: string; tenant: string; role: string } };

/** Sign in or create an account. The server's own wording is shown for these (wrong password, email already used), because it is written for people. */
export async function authenticate(mode: "login" | "signup", body: { email: string; password: string; name?: string }): Promise<Session> {
  let res: Response;
  try {
    res = await fetch(SERVER + "/v1/auth/" + mode, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check your connection and try again in a moment.");
  }
  if (!res.ok) {
    let detail: unknown = null;
    try { detail = (await res.json()).detail; } catch { /* no body */ }
    throw new ApiError(res.status, typeof detail === "string" ? detail : res.status === 429 ? "Too many attempts. Wait a minute and try again." : "That did not work. Check what you entered.");
  }
  return res.json() as Promise<Session>;
}

export async function signOutOnServer(cfg: Config): Promise<void> {
  try { await fetch(SERVER + "/v1/auth/logout", { method: "POST", headers: { Authorization: "Bearer " + cfg.token } }); } catch { /* the local sign-out still happens */ }
}

export function useApi<T>(cfg: Config | null, path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    if (!cfg || !path) return;
    setLoading(true); setError(null);
    try { setData(await call<T>(cfg, path)); } catch (e) { setError((e as Error).message); setData(null); } finally { setLoading(false); }
  }, [cfg, path]);
  useEffect(() => { load(); }, [load]);
  return { data, error, loading, reload: load };
}

export type Item = { ref: string; score: number; time_step: number | null; facts: { neighbours?: number; linked_alerts?: number } };
export type CaseRow = { id: string; title: string; status: "open" | "dispositioned"; priority: "high" | "normal"; source: string; provenance: "real" | "simulated"; has_investigation: boolean; alerts: number; max_score: number; disposition?: { decision: string; actor: string; note: string; ts: string; ai_recommendation?: string | null; overrode_ai?: boolean; override_reason?: string | null } };
export type Investigation = { trace?: Trace; recommendation: "escalate" | "review" | "abstain"; sentences: string[]; priority: string; path: "llm" | "rule" | "fallback"; provider: string | null; model: string | null; evidence: { id: string; text: string }[]; injection_flags: string[] };
export type CaseDetail = CaseRow & { items: Item[]; facts: Record<string, unknown>; investigation: Investigation | null; revealed_truth?: Record<string, number> };
export type Stats = { open: number; dispositioned: number; open_high_priority: number; labels: number };
export type ReportInfo = { name: string; title: string; provenance: "real" | "simulated" | "mixed"; available: boolean };
export type Report = ReportInfo & { markdown: string };
export type LedgerEntry = { seq: number; tenant: string; kind: string; ts: string; hash: string; prev_hash: string; payload: Record<string, unknown>; payload_canonical: string };
export type TraceStep = { id: string; label: string; status: "ok" | "skipped" | "failed" | "stopped"; ms: number; start_ms: number; detail: Record<string, any> };
export type Trace = { path?: "llm" | "fallback" | "rule"; total_ms: number; steps: TraceStep[] };
export type FrontierRow = { hold_from: number; warn_from: number; scam_money_stopped_share: number; good_payments_warned_share: number; good_payments_held_share: number; value_per_payment: number };
export type Frontier = { provenance: "simulated"; note: string; assumptions: Record<string, unknown>; rows: FrontierRow[] };
export type SimResult = { provenance: "simulated"; note: string; assumptions: Record<string, unknown>; n: number; result: FrontierRow };

export type Reason = { rule_id: string; code: string; outcome: string };
export type InterceptionState = {
  id: string; state: "asking" | "decided"; mode: "play" | "auto"; created: string;
  payment: { amount: number; currency: string; payee_age_days: number; row_ref: string; kind: string; provenance: string; trigger: string[]; risk: { risk_score: number; risk_band: string; model_version: string; model_type: string; ms: number } };
  transcript: { question: string; answer: string | null }[];
  result: null | { claims: string[]; flags: Record<string, boolean>; flags_from_ai_phrases: Record<string, boolean>; flags_from_customer_words: Record<string, boolean>; reason_text: Record<string, string>;
    decision: { outcome: string; risk_tier: string; requires_approval: boolean; policy_version: string; reasons: Reason[]; decision_id: string };
    explanation: { text: string; llm: { path?: string; model?: string | null; tokens_in?: number | null; tokens_out?: number | null } }; ledger: { seq: number; hash: string; ts: string } | null };
  trace: Trace; revealed_truth?: { is_scam: boolean; kind: string };
};
export type ScenarioInfo = { kind: string; label: string; simulated_customer: boolean };

export type Overview = {
  cases: Stats; ledger: { length: number; by_kind: Record<string, number> };
  activity_by_hour: { hour: string; total: number; by_kind: Record<string, number> }[];
  decisions: { total: number; by_outcome: Record<string, number>; top_reasons: { code: string; count: number }[] };
  ai_guardrails: { investigations: number; by_path: Record<string, number>; reached_the_ai: number; passed_first_time: number; first_pass_rate: number | null };
  interceptions: { total?: number; decided?: number; held?: number; questioned?: number };
  ai_usage_today: { requests: number; tokens: number; request_cap: number };
  recent_open_cases: CaseRow[];
};
