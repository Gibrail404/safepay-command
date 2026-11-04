"use client";
import type { ReactNode } from "react";

export function Chip({ kind, children, title }: { kind: "real" | "simulated" | "mixed" | "high" | "normal" | "open" | "done" | "neutral" | "good" | "warn"; children: ReactNode; title?: string }) {
  return <span className={`chip chip-${kind}`} title={title}>{children}</span>;
}

export function Provenance({ value }: { value: "real" | "simulated" | "mixed" }) {
  const text = value === "real" ? "Real data" : value === "simulated" ? "Simulated" : "Mixed: real and simulated";
  const tip = value === "real" ? "Comes from a real public dataset." : value === "simulated" ? "Comes from a simulator with assumed behaviour. Not evidence about real customers." : "Some parts are real and some simulated; the page says which.";
  return <Chip kind={value} title={tip}>{text}</Chip>;
}

export function Loading({ what = "Loading" }: { what?: string }) { return <div className="state" role="status">{what}…</div>; }
export function Empty({ children }: { children: ReactNode }) { return <div className="state empty">{children}</div>; }
export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div className="state error" role="alert"><p>{message}</p>{onRetry && <button type="button" className="btn" onClick={onRetry}>Try again</button>}</div>;
}
export function Card({ title, children, aside }: { title?: string; children: ReactNode; aside?: ReactNode }) {
  return <section className="card">{(title || aside) && <header className="card-head"><h2>{title}</h2>{aside}</header>}{children}</section>;
}
export function Stat({ label, value }: { label: string; value: ReactNode }) { return <div className="stat"><div className="stat-value">{value}</div><div className="stat-label">{label}</div></div>; }
