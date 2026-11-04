"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useConfig } from "@/components/providers";
import { useApi, type Overview } from "@/lib/api";
import { Card, Chip, Empty, ErrorBox, Loading, Stat } from "@/components/ui";

const KIND_LABEL: Record<string, string> = { "case.imported": "Cases imported", "case.investigated": "Investigated", "case.dispositioned": "Decided", decision: "Payment decisions", event: "Events" };
const KIND_COLOR: Record<string, string> = { "case.imported": "#8a96ad", "case.investigated": "#1f5fd6", "case.dispositioned": "#0f7a4b", decision: "#d9822b", event: "#9b59b6" };
const OUTCOME = [["allow", "Allowed", "#0f7a4b"], ["warn", "Warning", "#d9822b"], ["hold", "Held", "#c0392b"], ["block", "Blocked", "#7b1d16"]] as const;
const REASON: Record<string, string> = { LARGE_AMOUNT: "Large amount", NEW_PAYEE_LARGE_AMOUNT: "New payee, large amount", MODEL_RISK_ELEVATED: "Model risk elevated", MODEL_RISK_HIGH: "Model risk high", THIRD_PARTY_INSTRUCTED_NEW_PAYEE: "Someone told the customer to pay a new payee", PRESSURE_OR_SECRECY: "Pressure or secrecy", UNKNOWN_PAYEE_CLAIM: "Customer does not know the payee", SCREENING_HIT_CONFIRMED: "Sanctions match" };

export default function OverviewPage() {
  const { cfg } = useConfig();
  const { data, error, loading, reload } = useApi<Overview>(cfg, "/v1/overview");
  const [shown, setShown] = useState(false);
  useEffect(() => { if (data) { const t = window.setTimeout(() => setShown(true), 60); return () => window.clearTimeout(t); } }, [data]);
  if (loading && !data) return <><h1>Overview</h1><Loading what="Loading the overview" /></>;
  if (error || !data) return <><h1>Overview</h1><ErrorBox message={error ?? "Nothing to show."} onRetry={reload} /></>;
  const g = data.ai_guardrails;
  const rate = g.first_pass_rate;
  const R = 52, C = 2 * Math.PI * R;
  const maxHour = Math.max(1, ...data.activity_by_hour.map((h) => h.total));
  const kinds = Object.keys(data.ledger.by_kind);
  const dTotal = data.decisions.total;
  return (
    <>
      <h1>Overview</h1>
      <p className="muted">Everything here is counted from what this server has really recorded. Nothing is estimated or invented.</p>
      <div className="stats">
        <Stat label="Open cases" value={data.cases.open} />
        <Stat label="Open, high priority" value={data.cases.open_high_priority} />
        <Stat label="Payment decisions recorded" value={dTotal} />
        <Stat label="Audit ledger records" value={data.ledger.length} />
      </div>
      <div className="ov-grid">
        <Card title="AI guardrails">
          <div className="gauge-row">
            <svg viewBox="0 0 130 130" className="gauge" role="img" aria-label={rate === null ? "No AI summaries yet" : `${Math.round(rate * 100)} percent of AI answers passed the fact check first time`}>
              <circle cx="65" cy="65" r={R} className="g-track" />
              <circle cx="65" cy="65" r={R} className="g-fill" strokeDasharray={C} strokeDashoffset={shown && rate !== null ? C * (1 - rate) : C} transform="rotate(-90 65 65)" />
              <text x="65" y="63" textAnchor="middle" className="g-num">{rate === null ? "–" : `${Math.round(rate * 100)}%`}</text>
              <text x="65" y="82" textAnchor="middle" className="g-sub">first time · n={g.reached_the_ai}</text>
            </svg>
            <div>
              <p><strong>AI answers that passed the fact check on the first try.</strong> A low number means retries or fallbacks, never that a wrong answer got through.</p>
              <ul className="plain">
                <li>{g.investigations} case summaries in total</li><li>{g.passed_first_time} written by the AI and passed first time</li>
                <li>{g.by_path.fallback ?? 0} used the safe fallback text</li><li>{g.by_path.rule ?? 0} stopped by a fixed rule, no AI used</li>
              </ul>
            </div>
          </div>
          <p className="small muted">AI calls today: {data.ai_usage_today.requests} of {data.ai_usage_today.request_cap} allowed.</p>
          <div className="meter" aria-hidden="true"><span style={{ width: shown ? `${Math.min(100, (100 * data.ai_usage_today.requests) / data.ai_usage_today.request_cap)}%` : "0%" }} /></div>
        </Card>
        <Card title="Audit ledger activity, last 24 hours">
          {data.activity_by_hour.every((h) => h.total === 0) ? <Empty>Nothing was recorded in the last 24 hours.</Empty> : (
            <>
              <svg viewBox="0 0 480 170" className="bars" role="img" aria-label="Ledger records per hour over the last 24 hours">
                {data.activity_by_hour.map((h, i) => {
                  let y = 150;
                  return <g key={h.hour}><title>{`${h.hour.slice(11, 13)}:00 — ${h.total} record(s)`}</title>
                    {kinds.map((k) => { const n = h.by_kind[k] ?? 0; if (!n) return null; const ht = shown ? (130 * n) / maxHour : 0; y -= ht;
                      return <rect key={k} x={8 + i * 19.2} y={y} width={14} height={ht} rx={2} fill={KIND_COLOR[k] ?? "#888"} style={{ transition: `height .6s ease ${i * 18}ms, y .6s ease ${i * 18}ms` }} />; })}
                    {i % 6 === 0 && <text x={8 + i * 19.2} y={166} className="tick">{h.hour.slice(11, 13)}h</text>}</g>;
                })}
              </svg>
              <p className="chips small">{kinds.map((k) => <span key={k}><i className="swatch" style={{ background: KIND_COLOR[k] ?? "#888" }} />{KIND_LABEL[k] ?? k} ({data.ledger.by_kind[k]})</span>)}</p>
            </>)}
        </Card>
        <Card title="Payment decisions">
          {dTotal === 0 ? <Empty>No payment decisions yet. Try the <Link href="/interception">Interception</Link> page.</Empty> : (
            <>
              {OUTCOME.map(([k, label, color]) => { const n = data.decisions.by_outcome[k] ?? 0; return (
                <div key={k} className="hbar"><span className="hl">{label}</span><span className="ht"><span style={{ width: shown ? `${(100 * n) / dTotal}%` : "0%", background: color }} /></span><span className="hv">{n}</span></div>); })}
              <h3>Most common reasons</h3>
              {data.decisions.top_reasons.length === 0 ? <p className="muted">No rule fired yet.</p> : data.decisions.top_reasons.map((r) => (
                <div key={r.code} className="hbar"><span className="hl">{REASON[r.code] ?? r.code}</span><span className="ht"><span style={{ width: shown ? `${(100 * r.count) / dTotal}%` : "0%", background: "#1f5fd6" }} /></span><span className="hv">{r.count}</span></div>))}
            </>)}
          {data.interceptions.total ? <p className="small muted">Of {data.interceptions.total} interception runs, {data.interceptions.questioned ?? 0} were asked questions and {data.interceptions.held ?? 0} were held or blocked.</p> : null}
        </Card>
        <Card title="Open cases to look at">
          {data.recent_open_cases.length === 0 ? <Empty>No open cases.</Empty> : (
            <div className="table-wrap"><table><thead><tr><th>Case</th><th>Priority</th><th>Highest score</th></tr></thead><tbody>
              {data.recent_open_cases.map((c) => <tr key={c.id}><td><Link href={`/cases/${c.id}`}>{c.title}</Link></td><td><Chip kind={c.priority === "high" ? "high" : "normal"}>{c.priority}</Chip></td><td>{c.max_score.toFixed(2)}</td></tr>)}
            </tbody></table></div>)}
        </Card>
      </div>
    </>
  );
}
