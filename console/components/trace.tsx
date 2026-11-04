"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useConfig } from "@/components/providers";
import { useApi, type Trace, type TraceStep } from "@/lib/api";
import { usePrefersReducedMotion } from "@/components/motion";
import { Chip } from "@/components/ui";

const ICON: Record<TraceStep["status"], string> = { ok: "✓", failed: "✕", skipped: "–", stopped: "■" };
const WORD: Record<TraceStep["status"], string> = { ok: "Passed", failed: "Failed", skipped: "Not used", stopped: "Stopped here" };

type Phase = "idle" | "running" | "done";

/** Replays a real recorded run. Each step lights up in order. Real durations are shown on every step; the replay itself is slowed down so it can be followed. */
export function RunTrace({ trace, caseId }: { trace: Trace; caseId: string }) {
  const reduced = usePrefersReducedMotion();
  const [phases, setPhases] = useState<Phase[]>(() => trace.steps.map(() => "done"));
  const [selected, setSelected] = useState<number>(() => Math.max(0, trace.steps.findIndex((s) => s.status === "failed" || s.status === "stopped")));
  const [playing, setPlaying] = useState(false);
  const timers = useRef<number[]>([]);
  const stop = useCallback(() => { timers.current.forEach((t) => window.clearTimeout(t)); timers.current = []; }, []);
  useEffect(() => stop, [stop]);

  const replay = () => {
    stop();
    if (reduced) { setPhases(trace.steps.map(() => "done")); return; }
    setPlaying(true);
    setPhases(trace.steps.map(() => "idle"));
    let t = 120;
    trace.steps.forEach((s, i) => {
      const dwell = s.status === "skipped" ? 220 : Math.min(1500, Math.max(450, s.ms * 0.6));       // real time scaled, with a floor so quick steps are visible
      timers.current.push(window.setTimeout(() => { setPhases((p) => p.map((x, j) => (j === i ? "running" : x))); setSelected(i); }, t));
      t += dwell;
      timers.current.push(window.setTimeout(() => setPhases((p) => p.map((x, j) => (j === i ? "done" : x))), t));
    });
    timers.current.push(window.setTimeout(() => setPlaying(false), t + 100));
  };

  const step = trace.steps[selected];
  const pathNote = trace.path === "llm" ? "The AI's summary passed every check." : trace.path === "rule" ? "A fixed rule stopped the run before any AI was used." : "The AI gave no usable answer, so a safe fallback summary was used.";
  return (
    <div className="trace">
      <div className="trace-head">
        <div><strong>{pathNote}</strong> <span className="muted">Real run time: {trace.total_ms} ms. The replay is slowed down; the times on each step are the real ones.</span></div>
        <button type="button" className="btn" onClick={replay} disabled={playing}>{playing ? "Replaying…" : "Replay run"}</button>
      </div>
      <ol className="pipeline" aria-label="Steps of this run">
        {trace.steps.map((s, i) => (
          <li key={s.id} className={`tnode st-${s.status} ph-${phases[i]}${i === selected ? " selected" : ""}`}>
            {i > 0 && <span className={`tlink ${phases[i] !== "idle" ? "lit" : ""}`} aria-hidden="true"><span className="dot" /></span>}
            <button type="button" className="tbtn" onClick={() => setSelected(i)} aria-pressed={i === selected} aria-label={`${s.label}: ${WORD[s.status]}, ${s.ms} milliseconds`}>
              <span className="ring">{phases[i] === "idle" ? "" : phases[i] === "running" ? "" : ICON[s.status]}</span>
              <span className="tlabel">{s.label}</span>
              <span className="tms">{s.status === "skipped" ? "not used" : `${s.ms} ms`}</span>
            </button>
          </li>
        ))}
      </ol>
      <div className="trace-detail" aria-live="polite">
        <h3>{step.label} <Chip kind={step.status === "ok" ? "good" : step.status === "failed" || step.status === "stopped" ? "high" : "neutral"}>{WORD[step.status]}</Chip>
          {step.id === "fact_check" && step.detail.repaired && <> <Chip kind="warn">Fixed after one retry</Chip></>}</h3>
        <StepDetail step={step} caseId={caseId} />
      </div>
    </div>
  );
}

function StepDetail({ step, caseId }: { step: TraceStep; caseId: string }) {
  const d = step.detail;
  if (step.id === "facts") return <ul>{(d.facts as { id: string; text: string }[]).map((f) => <li key={f.id}><span className="cite">{f.id}</span> {f.text}</li>)}</ul>;
  if (step.id === "ai") {
    const attempts = (d.attempts ?? []) as { provider: string; ok: boolean; reason?: string; kind?: string; detail?: string; ms?: number }[];
    if (!attempts.length) return <p>{String(d.note ?? "The AI was not asked.")}{d.fallback_reason ? ` (${d.fallback_reason})` : ""}</p>;
    return (<><p className="muted">Each row is one real call.{d.model ? ` Final answer from ${d.model}.` : ""}</p>
      <div className="table-wrap"><table><thead><tr><th>Provider</th><th>Result</th><th>Time</th><th>Why</th></tr></thead><tbody>
        {attempts.map((a, i) => <tr key={i}><td>{a.provider}</td><td>{a.ok ? "Answer accepted" : "Rejected"}</td><td>{a.ms ?? 0} ms</td><td className="small">{a.ok ? "" : a.kind === "check" ? `Failed the fact check: ${a.detail ?? ""}` : a.reason ?? ""}</td></tr>)}
      </tbody></table></div></>);
  }
  if (step.id === "fact_check") {
    const issues = (d.issues ?? []) as string[];
    return (<><p>{String(d.note)}</p>{issues.length > 0 && <><p className="muted">What the checker found in rejected replies:</p><ul>{issues.map((x, i) => <li key={i} className="small">{x}</li>)}</ul></>}</>);
  }
  if (step.id === "priority") return <p>Recommendation: <strong>{String(d.recommendation)}</strong>. Priority: <strong>{String(d.priority)}</strong>. {String(d.note)}</p>;
  if (step.id === "ledger") return <LedgerLine caseId={caseId} note={String(d.note)} />;
  return <p>{String(d.note ?? "")}</p>;
}

function LedgerLine({ caseId, note }: { caseId: string; note: string }) {
  const { cfg } = useConfig();
  const { data, error } = useApi<{ seq: number; kind: string; ts: string; hash: string }[]>(cfg, `/v1/cases/${caseId}/ledger`);
  return (<><p>{note}</p>
    {error ? <p className="muted">{error}</p> : !data ? <p className="muted">Looking up the entry…</p> : data.length === 0 ? <p className="muted">No entry found.</p> :
      <ul>{data.map((e) => <li key={e.seq}>Record <strong>#{e.seq}</strong> ({e.kind.replace("case.", "")}), fingerprint <span className="mono small">{e.hash.slice(0, 16)}…</span></li>)}</ul>}
    <p><Link href="/audit">Check the chain in the audit trail →</Link></p></>);
}
