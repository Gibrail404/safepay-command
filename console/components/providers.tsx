"use client";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { SIGNED_OUT_EVENT, STORAGE_KEY, authenticate, call, signOutOnServer, type Config } from "@/lib/api";

const Ctx = createContext<{ cfg: Config; setCfg: (c: Config | null) => void; role: string | null; canAct: boolean } | null>(null);
export function useConfig() { const v = useContext(Ctx); if (!v) throw new Error("outside provider"); return v; }

function SignIn({ onSave }: { onSave: (c: Config) => void }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const signup = mode === "signup";
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError(null);
    try {
      const s = await authenticate(mode, { email: email.trim(), password, ...(signup ? { name: name.trim() } : {}) });
      onSave({ token: s.token, actor: s.user.name });
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  return (
    <main className="narrow">
      <h1>{signup ? "Create an account" : "Sign in to SafePay Command"}</h1>
      <p className="muted">This console shows only what the server returns. Your name is recorded on every decision you make.</p>
      <form className="card form" onSubmit={submit}>
        {signup && <label>Your name<input value={name} onChange={(e) => setName(e.target.value)} required maxLength={64} autoComplete="name" /></label>}
        <label>Email<input value={email} onChange={(e) => setEmail(e.target.value)} required type="email" autoComplete="email" /></label>
        <label>Password{signup && " (at least 8 characters)"}<input value={password} onChange={(e) => setPassword(e.target.value)} required type="password" minLength={signup ? 8 : undefined} maxLength={128} autoComplete={signup ? "new-password" : "current-password"} /></label>
        {error && <p role="alert" className="error-text">{error}</p>}
        <button className="btn primary" type="submit" disabled={busy}>{busy ? "Please wait…" : signup ? "Create account" : "Sign in"}</button>
        <p className="muted">{signup ? "Already have an account?" : "New here?"} <button type="button" className="linklike" onClick={() => { setMode(signup ? "login" : "signup"); setError(null); }}>{signup ? "Sign in" : "Create an account"}</button></p>
      </form>
    </main>
  );
}

export function Providers({ children }: { children: ReactNode }) {
  const [cfg, setCfgState] = useState<Config | null>(null);
  const [ready, setReady] = useState(false);
  const [role, setRole] = useState<string | null>(null);
  const path = usePathname();
  useEffect(() => {
    try { const raw = localStorage.getItem(STORAGE_KEY); if (raw) setCfgState(JSON.parse(raw)); } catch { /* storage unavailable */ }
    setReady(true);
    const out = () => setCfg(null);
    window.addEventListener(SIGNED_OUT_EVENT, out);
    return () => window.removeEventListener(SIGNED_OUT_EVENT, out);
  }, []);
  useEffect(() => {
    if (!cfg) { setRole(null); return; }
    call<{ role: string }>(cfg, "/v1/whoami").then((w) => setRole(w.role)).catch(() => setRole(null));
  }, [cfg]);
  const setCfg = (c: Config | null) => { setCfgState(c); try { c ? localStorage.setItem(STORAGE_KEY, JSON.stringify(c)) : localStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ } };
  if (!ready) return <div className="state" role="status">Loading…</div>;
  if (!cfg) return <SignIn onSave={setCfg} />;
  const nav = [["/overview", "Overview"], ["/interception", "Interception"], ["/cases", "Cases"], ["/lab", "Decision Lab"], ["/reports", "Reports"], ["/audit", "Audit trail"]] as const;
  return (
    <Ctx.Provider value={{ cfg, setCfg, role, canAct: role !== "viewer" }}>
      <header className="topbar">
        <strong className="brand">SafePay Command</strong>
        <nav aria-label="Main">{nav.map(([href, label]) => <Link key={href} href={href} className={path.startsWith(href) ? "active" : ""}>{label}</Link>)}</nav>
        <span className="who">{cfg.actor}{role ? ` (${role})` : ""} · <button type="button" className="linklike" onClick={() => { signOutOnServer(cfg); setCfg(null); }}>Sign out</button></span>
      </header>
      <main>{children}</main>
    </Ctx.Provider>
  );
}
