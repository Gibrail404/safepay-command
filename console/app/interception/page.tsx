"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useConfig } from "@/components/providers";
import { call, useApi, type InterceptionState, type ScenarioInfo, type TraceStep } from "@/lib/api";
import { RunTrace } from "@/components/trace";
import { Card, Chip, ErrorBox, Loading } from "@/components/ui";

const OUTCOME: Record<string, { label: string; kind: "good" | "warn" | "high"; text: string }> = {
  allow: { label: "Allowed", kind: "good", text: "The payment goes ahead." },
  warn: { label: "Warning", kind: "warn", text: "The payment can go ahead after a warning." },
  hold: { label: "Held for review", kind: "high", text: "The payment is paused and a person checks it." },
  block: { label: "Blocked", kind: "high", text: "The payment cannot be sent." },
};
const FLAG_TEXT: Record<string, string> = { third_party_instructed: "Someone else told the customer to pay", urgency: "Urgency", secrecy: "Secrecy", unknown_payee: "Does not know the payee" };
const bandKind = (b: string) => (b === "high" ? "high" : b === "elevated" ? "warn" : "good") as "high" | "warn" | "good";

export default function InterceptionPage() {
  const { cfg, canAct } = useConfig();
  const scenarios = useApi<ScenarioInfo[]>(cfg, "/v1/interceptions/scenarios");
  const [kind, setKind] = useState("scam_uncoached");
  const [mode, setMode] = useState<"play" | "auto">("play");
  const [seed, setSeed] = useState(1);
  const [st, setSt] = useState<InterceptionState | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [st?.transcript.length, busy]);

  const start = async (nextSeed = seed) => {
    setBusy(mode === "auto" ? "Playing the customer and asking the questions… this takes several seconds with a live AI model." : "Scoring the payment…");
    setError(null); setSt(null); setDraft("");
    try { setSt(await call<InterceptionState>(cfg, "/v1/interceptions", { method: "POST", body: { kind, seed: nextSeed, mode } })); }
    catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  };
  const send = async () => {
    if (!st || !draft.trim()) return;
    const text = draft.trim();
    setBusy("Reading your answer…"); setError(null); setDraft("");
    setSt({ ...st, transcript: st.transcript.map((t, i) => (i === st.transcript.length - 1 ? { ...t, answer: text } : t)) });
    try { setSt(await call<InterceptionState>(cfg, `/v1/interceptions/${st.id}/answer`, { method: "POST", body: { text } })); }
    catch (e) { setError((e as Error).message); setDraft(text); try { setSt(await call<InterceptionState>(cfg, `/v1/interceptions/${st.id}`)); } catch { /* keep what we have */ } }
    finally { setBusy(null); }
  };
  const again = () => { const s = seed + 1; setSeed(s); start(s); };

  const p = st?.payment;
  const last = st?.transcript[st.transcript.length - 1];
  const waitingForCustomer = st && st.state === "asking" && mode === "play" && last && last.answer === null;

  return (
    <>
      <h1>Interception</h1>
      <p>One payment, start to finish: a risk score, up to three questions to the customer, the warning signs their answers show, the policy decision, a message to the customer, and the audit record. <strong>The AI reads and asks; the model scores; the policy engine decides.</strong> The AI can never approve or block a payment, and what the customer says can only add friction.</p>
      <Card title="Choose a scenario">
        {scenarios.loading ? <Loading /> : scenarios.error ? <ErrorBox message={scenarios.error} onRetry={scenarios.reload} /> : (
          <>
            <div className="scen-grid" role="radiogroup" aria-label="Scenario">
              {(scenarios.data ?? []).map((s) => (
                <button key={s.kind} type="button" role="radio" aria-checked={kind === s.kind} className={`scen${kind === s.kind ? " on" : ""}`} onClick={() => setKind(s.kind)}>{s.label}</button>))}
            </div>
            <div className="row">
              <label className="inline"><input type="radio" name="mode" checked={mode === "play"} onChange={() => setMode("play")} /> I answer as the customer</label>
              <label className="inline"><input type="radio" name="mode" checked={mode === "auto"} onChange={() => setMode("auto")} /> Play the customer for me</label>
              <button type="button" className="btn primary" onClick={() => start()} disabled={!canAct || !!busy}>{canAct ? "Start this payment" : "Your role is read-only"}</button>
            </div>
            <p className="muted small">Each scenario uses a real held-out card transaction scored by the real model. The payee&apos;s age and everything the customer says are simulated. Whether it is a scam stays hidden until the decision.</p>
          </>)}
      </Card>
      {error && <ErrorBox message={error} />}
      {busy && !st && <Loading what={busy} />}
      {st && p && (
        <>
          <Card title="The payment" aside={<span className="chips"><Chip kind="real" title={p.provenance}>Real transaction and model</Chip> <Chip kind="simulated">Simulated payee and customer</Chip></span>}>
            <div className="stats">
              <div className="stat"><div className="stat-value">{p.currency} {p.amount.toFixed(0)}</div><div className="stat-label">Amount</div></div>
              <div className="stat"><div className="stat-value">{p.payee_age_days === 0 ? "today" : `${p.payee_age_days} day${p.payee_age_days === 1 ? "" : "s"}`}</div><div className="stat-label">Payee first seen</div></div>
              <div className="stat"><div className="stat-value"><Chip kind={bandKind(p.risk.risk_band)}>{p.risk.risk_band}</Chip></div><div className="stat-label">Model risk band (score {p.risk.risk_score.toFixed(5)})</div></div>
            </div>
            <p className="muted small">{p.trigger.length ? `Questions are asked because: ${p.trigger.join(" ")}` : "No reason to add friction, so the payment goes straight to the policy."}</p>
          </Card>
          {st.transcript.length > 0 && (
            <Card title="Conversation with the customer">
              <div className="chat" aria-live="polite">
                {st.transcript.map((t, i) => (
                  <div key={i}>
                    <div className="bubble q"><span className="who">Bank</span>{t.question}</div>
                    {t.answer !== null && <div className="bubble a"><span className="who">{mode === "play" ? "You" : "Simulated customer"}</span>{t.answer}</div>}
                  </div>))}
                {busy && <div className="bubble q typing"><span className="who">Bank</span>{busy}</div>}
                <div ref={endRef} />
              </div>
              {waitingForCustomer && !busy && (
                <form className="row" onSubmit={(e) => { e.preventDefault(); send(); }}>
                  <input aria-label="Your answer" value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={500} placeholder="Type the customer's answer" style={{ flex: 1, minWidth: 220 }} autoFocus />
                  <button type="submit" className="btn primary" disabled={!draft.trim()}>Send</button>
                </form>)}
            </Card>)}
          {st.state === "decided" && st.result && <DecisionCards st={st} onAgain={again} />}
          <Card title="Every step, with real times">
            <RunTrace key={`${st.id}-${st.trace.steps.length}`} trace={st.trace} headline={st.state === "decided" ? `Decision: ${OUTCOME[st.result?.decision.outcome ?? "allow"]?.label}.` : "The payment is waiting for the customer's answer."} renderDetail={(s) => <Detail step={s} st={st} />} />
          </Card>
        </>)}
    </>
  );
}

function DecisionCards({ st, onAgain }: { st: InterceptionState; onAgain: () => void }) {
  const r = st.result!;
  const o = OUTCOME[r.decision.outcome] ?? OUTCOME.allow;
  const held = r.decision.outcome === "hold" || r.decision.outcome === "block";
  const truth = st.revealed_truth;
  const flagged = Object.entries(r.flags).filter(([, v]) => v).map(([k]) => k);
  return (
    <>
      <Card title="Decision">
        <p className="decision"><Chip kind={o.kind}>{o.label}</Chip> <span>{o.text}</span></p>
        {r.decision.reasons.length > 0 ? <ul>{r.decision.reasons.map((x) => <li key={x.rule_id}><strong>{x.code.replace(/_/g, " ").toLowerCase()}</strong> ({x.outcome}){r.reason_text[x.code] ? `: ${r.reason_text[x.code]}` : ""}</li>)}</ul> : <p className="muted">No policy rule fired.</p>}
        <p><strong>Warning signs in the answers:</strong> {flagged.length ? flagged.map((k) => <span key={k}><Chip kind="warn">{FLAG_TEXT[k] ?? k}</Chip>{" "}</span>) : <span className="muted">none found</span>}</p>
        <h3>Message to the customer</h3>
        <blockquote>{r.explanation.text}</blockquote>
        {r.ledger && <p className="muted small">Recorded as ledger entry <strong>#{r.ledger.seq}</strong>, fingerprint <span className="mono">{r.ledger.hash.slice(0, 16)}…</span> · policy <span className="mono">{r.decision.policy_version.slice(0, 10)}</span> · <Link href="/audit">check the chain</Link></p>}
      </Card>
      {truth && (
        <Card title="What this scenario really was (revealed after the decision)">
          <p><Chip kind={truth.is_scam ? "high" : "good"}>{truth.is_scam ? "A scam" : "A genuine payment"}</Chip> {truth.is_scam ? (held ? "The policy held a real scam." : "The policy let a scam through. A customer coached by the scammer can give a convincing story, and the model alone cannot see it.") : held ? "A genuine payment was held: friction for a good customer." : "A genuine payment went through."}</p>
          <p className="muted small">One example proves nothing about performance. The <Link href="/reports/interception">comparison report</Link> measures this on many held-out scenarios.</p>
          <button type="button" className="btn" onClick={onAgain}>Try another example of this scenario</button>
        </Card>)}
    </>
  );
}

function Detail({ step, st }: { step: TraceStep; st: InterceptionState }) {
  const d = step.detail;
  if (step.id === "payment") return <p>{d.currency} {Number(d.amount).toFixed(2)} to a payee first seen {d.payee_age_days} day(s) ago. Reference <span className="mono">{String(d.reference)}</span>. {String(d.note)}</p>;
  if (step.id === "risk") return <p>Calibrated risk score <strong>{Number(d.score).toFixed(6)}</strong>, band <strong>{String(d.band)}</strong>. Model {String(d.model_type)} version <span className="mono">{String(d.model_version)}</span>, scored in {step.ms} ms. The policy reads the band, never the raw score.</p>;
  if (step.id === "trigger") return <p>{String(d.note)} {(d.reasons as string[]).join(" ")}</p>;
  if (step.id === "questions") {
    const turns = d.turns as { question: string; answer: string | null; ms: number; llm: { path?: string; model?: string | null; tokens_in?: number | null; tokens_out?: number | null } }[];
    return (<><p className="muted">Each question is written by the AI and checked by rules (one polite question, no credentials, no accusation, no repeats). If it fails the check, a fixed question is used.</p>
      <div className="table-wrap"><table><thead><tr><th>Question</th><th>Written by</th><th>Time</th><th>Tokens</th></tr></thead><tbody>
        {turns.map((t, i) => <tr key={i}><td>{t.question}</td><td>{t.llm.path === "llm" ? t.llm.model : "fixed question bank"}</td><td>{t.ms} ms</td><td>{t.llm.tokens_in != null ? `${t.llm.tokens_in} in, ${t.llm.tokens_out} out` : "none"}</td></tr>)}
      </tbody></table></div></>);
  }
  if (step.id === "flags") {
    const ai = d.from_ai_phrases as Record<string, boolean>, raw = d.from_customer_words as Record<string, boolean>;
    return (<><p>{String(d.note)}</p>
      <div className="table-wrap"><table><thead><tr><th>Warning sign</th><th>In phrases the AI quoted</th><th>In the customer&apos;s own words (keyword rules)</th></tr></thead><tbody>
        {Object.keys(FLAG_TEXT).map((k) => <tr key={k}><td>{FLAG_TEXT[k]}</td><td>{ai[k] ? "yes" : "no"}</td><td>{raw[k] ? "yes" : "no"}</td></tr>)}
      </tbody></table></div>
      {(d.claims as string[]).length > 0 && <p className="small">Phrases the AI quoted (each must be word for word from the customer): {(d.claims as string[]).map((c, i) => <q key={i}>{c} </q>)}</p>}</>);
  }
  if (step.id === "policy") return <><p>Outcome <strong>{String(d.outcome)}</strong>, tier {String(d.risk_tier)}{d.requires_approval ? ", needs a human approval" : ""}. Policy version <span className="mono">{String(d.policy_version).slice(0, 12)}</span>, decision <span className="mono">{String(d.decision_id)}</span>.</p>
    <ul>{(d.reasons as { rule_id: string; code: string }[]).map((r) => <li key={r.rule_id}>{r.rule_id}: {r.code}</li>)}</ul></>;
  if (step.id === "explain") { const l = d.llm as { path?: string; model?: string | null; tokens_in?: number | null; tokens_out?: number | null }; return <><p>{String(d.text)}</p><p className="muted small">{l.path === "llm" ? `Written by ${l.model} and fact-checked${l.tokens_in != null ? ` (${l.tokens_in} tokens in, ${l.tokens_out} out)` : ""}.` : "Safe template text: no AI answer passed the fact check, or no AI was available."}</p></>; }
  if (step.id === "ledger") return <p>{d.seq ? <>Decision recorded as entry <strong>#{String(d.seq)}</strong>, fingerprint <span className="mono">{String(d.hash).slice(0, 24)}…</span>. </> : String(d.note)}<Link href="/audit">Check the chain in the audit trail →</Link></p>;
  return null;
}
