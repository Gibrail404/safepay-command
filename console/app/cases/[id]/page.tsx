"use client";
import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useConfig } from "@/components/providers";
import { call, useApi, type CaseDetail, type Investigation } from "@/lib/api";
import { Card, Chip, ErrorBox, Loading, Provenance } from "@/components/ui";
import { labelOf } from "../page";

function Sentence({ text, evidence }: { text: string; evidence: Investigation["evidence"] }) {
  const parts = text.split(/(\[E\d+(?:\s*,\s*E\d+)*\])/g);
  return <p>{parts.map((p, i) => {
    const m = p.match(/^\[(E\d+(?:\s*,\s*E\d+)*)\]$/);
    if (!m) return <span key={i}>{p}</span>;
    return <span key={i}>{m[1].split(/\s*,\s*/).map((id) => <span key={id} className="cite" title={evidence.find((e) => e.id === id)?.text ?? "unknown evidence"}>{id}</span>)}</span>;
  })}</p>;
}

function Investigator({ id, inv, onDone }: { id: string; inv: Investigation | null; onDone: () => void }) {
  const { cfg, canAct } = useConfig();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const run = async () => { setBusy(true); setErr(null); try { await call(cfg, `/v1/cases/${id}/investigate`, { method: "POST" }); onDone(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } };
  const how = !inv ? null : inv.path === "llm" ? `Written by an AI model (${inv.model})` : inv.path === "rule" ? "Fixed rule, no AI used: the evidence was too thin" : "Safe plain-text summary: the AI reply did not pass the fact check, or no AI was available";
  return (
    <Card title="Investigation summary" aside={<button type="button" className="btn" onClick={run} disabled={busy || !canAct} title={canAct ? undefined : "Your role is read-only"}>{busy ? "Working…" : inv ? "Run again" : "Run investigation"}</button>}>
      {err && <ErrorBox message={err} />}
      {!inv ? <p className="muted">No summary yet. The summary is written from structured facts only and every sentence cites the fact it uses. It can raise a case&apos;s priority but never lower or close it.</p> : (
        <>
          <p><Chip kind={inv.recommendation === "escalate" ? "high" : inv.recommendation === "review" ? "normal" : "neutral"}>{inv.recommendation === "escalate" ? "Recommends escalating" : inv.recommendation === "review" ? "Recommends a normal review" : "Not enough evidence to recommend"}</Chip> <span className="muted">{how}</span></p>
          {inv.sentences.map((s, i) => <Sentence key={i} text={s} evidence={inv.evidence} />)}
          <details><summary>Facts behind the summary</summary><ul>{inv.evidence.map((e) => <li key={e.id}><span className="cite">{e.id}</span> {e.text}</li>)}</ul></details>
        </>)}
    </Card>
  );
}

function Decision({ c, onDone }: { c: CaseDetail; onDone: () => void }) {
  const { cfg, canAct } = useConfig();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const send = async (decision: string, sure: string) => {
    if (!window.confirm(sure)) return;
    setBusy(true); setErr(null);
    try { await call(cfg, `/v1/cases/${c.id}/disposition`, { method: "POST", body: { decision, note } }); onDone(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  if (c.status === "dispositioned" && c.disposition) {
    const truth = c.revealed_truth;
    return (
      <Card title="Decision">
        <p><Chip kind="done">{labelOf(c.disposition.decision)}</Chip> by {c.disposition.actor} on {new Date(c.disposition.ts).toLocaleString()}</p>
        {c.disposition.note && <p>Note: {c.disposition.note}</p>}
        {truth && <><h3>What the dataset says (revealed after your decision)</h3>
          <div className="table-wrap"><table><thead><tr><th>Transaction</th><th>Dataset label</th></tr></thead><tbody>
            {c.items.map((it) => <tr key={it.ref}><td className="mono">{it.ref}</td><td>{truth[it.ref] === 1 ? "Illicit" : truth[it.ref] === 0 ? "Licit" : "Unknown (not labelled in the dataset)"}</td></tr>)}
          </tbody></table></div>
          <p className="muted">The labels come from the dataset itself. They were hidden until a decision was recorded.</p></>}
      </Card>
    );
  }
  return (
    <Card title="Your decision">
      {err && <ErrorBox message={err} />}
      {!canAct && <p className="muted">Your role is read-only, so you can look but not decide.</p>}
      <label className="stack">Note (optional, kept in the audit trail)<textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} rows={2} /></label>
      <div className="row">
        <button type="button" className="btn danger" disabled={busy || !canAct} onClick={() => send("confirmed_illicit", "Record this case as confirmed illicit? This also records a label for each alert and cannot be changed.")}>Confirm illicit</button>
        <button type="button" className="btn" disabled={busy || !canAct} onClick={() => send("dismissed_licit", "Dismiss this case as licit? This also records a label for each alert and cannot be changed.")}>Dismiss as licit</button>
        <button type="button" className="btn" disabled={busy || !canAct} onClick={() => send("escalated", "Escalate this case? No labels are recorded.")}>Escalate</button>
      </div>
    </Card>
  );
}

export default function CaseDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { cfg } = useConfig();
  const { data, error, loading, reload } = useApi<CaseDetail>(cfg, `/v1/cases/${id}`);
  if (loading && !data) return <Loading what="Loading case" />;
  if (error || !data) return <ErrorBox message={error ?? "Not found."} onRetry={reload} />;
  return (
    <>
      <p><Link href="/cases">← All cases</Link></p>
      <h1>{data.title}</h1>
      <p className="chips"><Chip kind={data.priority === "high" ? "high" : "normal"}>{data.priority === "high" ? "High priority" : "Normal priority"}</Chip> <Chip kind={data.status === "open" ? "open" : "done"}>{data.status === "open" ? "Open" : "Decided"}</Chip> <Provenance value={data.provenance} /> <span className="muted">{String(data.facts.dataset ?? data.source)}</span></p>
      <Card title={`Alerts in this case (${data.items.length})`}>
        <div className="table-wrap"><table>
          <thead><tr><th>Transaction</th><th>Time step</th><th>Model score</th><th>Linked transactions</th><th>Linked alerts</th></tr></thead>
          <tbody>{data.items.map((it) => <tr key={it.ref}><td className="mono">{it.ref}</td><td>{it.time_step ?? "n/a"}</td><td>{it.score.toFixed(2)}</td><td>{it.facts.neighbours ?? "n/a"}</td><td>{it.facts.linked_alerts ?? 0}</td></tr>)}</tbody>
        </table></div>
      </Card>
      <Investigator id={data.id} inv={data.investigation} onDone={reload} />
      <Decision c={data} onDone={reload} />
    </>
  );
}
