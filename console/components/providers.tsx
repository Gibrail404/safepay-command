"use client";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { STORAGE_KEY, call, type Config } from "@/lib/api";

const Ctx = createContext<{ cfg: Config; setCfg: (c: Config | null) => void; role: string | null; canAct: boolean } | null>(null);
export function useConfig() { const v = useContext(Ctx); if (!v) throw new Error("outside provider"); return v; }

function Connect({ onSave }: { onSave: (c: Config) => void }) {
  const [url, setUrl] = useState("http://127.0.0.1:8000");
  const [key, setKey] = useState("");
  const [actor, setActor] = useState("");
  return (
    <main className="narrow">
      <h1>Connect to a SafePay server</h1>
      <p className="muted">This console shows only what the server returns. Enter the server address, your API key and the name that should appear on your decisions. They stay in this browser tab&apos;s storage.</p>
      <form className="card form" onSubmit={(e) => { e.preventDefault(); onSave({ url: url.trim(), key: key.trim(), actor: actor.trim() }); }}>
        <label>Server address<input value={url} onChange={(e) => setUrl(e.target.value)} required inputMode="url" /></label>
        <label>API key<input value={key} onChange={(e) => setKey(e.target.value)} required type="password" autoComplete="off" /></label>
        <label>Your name (recorded on every decision)<input value={actor} onChange={(e) => setActor(e.target.value)} required maxLength={64} /></label>
        <button className="btn primary" type="submit">Connect</button>
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
    try { const raw = sessionStorage.getItem(STORAGE_KEY); if (raw) setCfgState(JSON.parse(raw)); } catch { /* storage unavailable */ }
    setReady(true);
  }, []);
  useEffect(() => {
    if (!cfg) { setRole(null); return; }
    call<{ role: string }>(cfg, "/v1/whoami").then((w) => setRole(w.role)).catch(() => setRole(null));
  }, [cfg]);
  const setCfg = (c: Config | null) => { setCfgState(c); try { c ? sessionStorage.setItem(STORAGE_KEY, JSON.stringify(c)) : sessionStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ } };
  if (!ready) return <div className="state" role="status">Loading…</div>;
  if (!cfg) return <Connect onSave={setCfg} />;
  const nav = [["/cases", "Cases"], ["/lab", "Decision Lab"], ["/reports", "Reports"], ["/audit", "Audit trail"]] as const;
  return (
    <Ctx.Provider value={{ cfg, setCfg, role, canAct: role !== "viewer" }}>
      <header className="topbar">
        <strong className="brand">SafePay Command</strong>
        <nav aria-label="Main">{nav.map(([href, label]) => <Link key={href} href={href} className={path.startsWith(href) ? "active" : ""}>{label}</Link>)}</nav>
        <span className="who">{cfg.actor}{role ? ` (${role})` : ""} · <button type="button" className="linklike" onClick={() => setCfg(null)}>Disconnect</button></span>
      </header>
      <main>{children}</main>
    </Ctx.Provider>
  );
}
