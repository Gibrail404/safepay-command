"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useConfig } from "@/components/providers";
import { call, type LedgerEntry } from "@/lib/api";
import { usePrefersReducedMotion } from "@/components/motion";
import { Card, Chip, ErrorBox, Loading } from "@/components/ui";

const WINDOW = 10;
const KIND: Record<string, string> = { "case.imported": "Cases imported", "case.investigated": "Investigated", "case.dispositioned": "Decided", "event": "Event", "decision": "Decision" };

async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** A harmless edit to a payload: changes the first text value, or the first number. Used only on the in-browser copy. */
function tamper(text: string): string {
  const s = text.replace(/"([a-z_]+)":"([^"]*)"/, (_m, k, v) => `"${k}":"${v}X"`);
  return s !== text ? s : text.replace(/(\d+)/, (n) => String(Number(n) + 1));
}

type View = { shown: string; computed: string; status: "ok" | "content" | "link" | "untrusted" };

export function LedgerDemo() {
  const { cfg } = useConfig();
  const reduced = usePrefersReducedMotion();
  const [blocks, setBlocks] = useState<LedgerEntry[] | null>(null);
  const [head, setHead] = useState<string>("");
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [edited, setEdited] = useState<Record<number, string>>({});
  const [rewritten, setRewritten] = useState<number[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [view, setView] = useState<View[]>([]);
  const [running, setRunning] = useState(false);
  const timers = useRef<number[]>([]);

  const load = useCallback(async () => {
    setError(null);
    try {
      if (!window.isSecureContext || !crypto.subtle) throw new Error("Your browser can only compute hashes on a secure page (https or localhost).");
      const v = await call<{ checked: number; head_hash: string }>(cfg, "/v1/audit/verify");
      const after = Math.max(0, v.checked - WINDOW);
      const rows = await call<LedgerEntry[]>(cfg, `/v1/audit?after_seq=${after}&limit=${WINDOW}`);
      setBlocks(rows); setHead(v.head_hash); setTotal(v.checked); setEdited({}); setRewritten([]); setSelected(null);
    } catch (e) { setError((e as Error).message); }
  }, [cfg]);
  useEffect(() => { load(); return () => timers.current.forEach((t) => window.clearTimeout(t)); }, [load]);

  // Recompute every fingerprint in the browser from the exact strings the server hashed.
  useEffect(() => {
    if (!blocks || blocks.length === 0) return;
    let cancelled = false;
    (async () => {
      const out: View[] = [];
      let prevShown = blocks[0].prev_hash;
      let broken = false;
      for (let i = 0; i < blocks.length; i++) {
        const b = blocks[i];
        const rew = rewritten.includes(b.seq);
        const prevUsed = rew ? prevShown : b.prev_hash;
        const computed = await sha256(`${prevUsed}|${b.tenant}|${b.kind}|${b.ts}|${edited[b.seq] ?? b.payload_canonical}`);
        const shown = rew ? computed : b.hash;
        let status: View["status"] = computed !== shown ? "content" : i > 0 && prevUsed !== prevShown ? "link" : "ok";
        if (broken) status = "untrusted";
        else if (status !== "ok") broken = true;
        out.push({ shown, computed, status });
        prevShown = shown;
      }
      if (!cancelled) setView(out);
    })();
    return () => { cancelled = true; };
  }, [blocks, edited, rewritten]);

  if (error) return <Card title="Try to tamper with it"><ErrorBox message={error} onRetry={load} /></Card>;
  if (!blocks || view.length !== blocks.length) return <Card title="Try to tamper with it"><Loading what="Checking the chain in your browser" /></Card>;
  if (blocks.length === 0) return <Card title="Try to tamper with it"><p className="muted">Nothing is recorded yet, so there is nothing to tamper with.</p></Card>;

  const firstBad = view.findIndex((v) => v.status === "content" || v.status === "link");
  const lastIsHead = blocks[blocks.length - 1].seq === total;
  const headOk = !lastIsHead || view[view.length - 1].shown === head;
  const selBlock = selected !== null ? blocks.find((b) => b.seq === selected) : undefined;

  const doTamper = () => { if (selBlock) setEdited((e) => ({ ...e, [selBlock.seq]: tamper(e[selBlock.seq] ?? selBlock.payload_canonical) })); };
  const coverTracks = () => {
    if (!selBlock) return;
    const seqs = blocks.filter((b) => b.seq >= selBlock.seq).map((b) => b.seq);
    if (reduced) { setRewritten(seqs); return; }
    setRunning(true);
    seqs.forEach((q, i) => timers.current.push(window.setTimeout(() => { setRewritten((r) => [...r, q]); if (i === seqs.length - 1) setRunning(false); }, 450 * (i + 1))));
  };
  const reset = () => { timers.current.forEach((t) => window.clearTimeout(t)); timers.current = []; setEdited({}); setRewritten([]); setRunning(false); };

  return (
    <Card title="Try to tamper with it" aside={<Chip kind="good" title="Computed by your browser with SHA-256">Checked in your browser</Chip>}>
      <p className="muted">Your browser has just re-computed every fingerprint below from the exact text the server recorded. Pick a record, change it on <strong>your own copy</strong> and watch what breaks. Nothing is sent to the server and the real ledger is untouched.</p>
      <div className={`verdict ${firstBad >= 0 || !headOk ? "bad" : "good"}`} role="status">
        {firstBad >= 0 ? <>Chain breaks at record <strong>#{blocks[firstBad].seq}</strong>: {view[firstBad].status === "content" ? "its content no longer matches its fingerprint." : "it no longer links to the record before it."} Everything after it can no longer be trusted.</>
          : !headOk ? <>Every record links to the one before, <strong>but the last fingerprint no longer matches the one the server saved separately.</strong> Rewriting history is detected even if every hash is recomputed.</>
          : <>All {blocks.length} records verify in your browser{lastIsHead ? ", and the last fingerprint matches the one the server saved." : "."}</>}
      </div>
      <ol className="chain" aria-label="Most recent ledger records">
        {blocks.map((b, i) => {
          const v = view[i];
          const changed = edited[b.seq] !== undefined;
          return (
            <li key={b.seq} className={`blk bs-${v.status}${selected === b.seq ? " sel" : ""}`}>
              {i > 0 && <span className={`blink bs-${view[i].status === "link" ? "link" : "ok"}`} aria-hidden="true" />}
              <button type="button" onClick={() => setSelected(b.seq)} aria-pressed={selected === b.seq} aria-label={`Record ${b.seq}, ${KIND[b.kind] ?? b.kind}, ${v.status === "ok" ? "verified" : v.status === "untrusted" ? "not trusted" : "broken"}`}>
                <span className="blk-top"><strong>#{b.seq}</strong><span className="blk-state">{v.status === "ok" ? "✓ verified" : v.status === "untrusted" ? "? not trusted" : "✕ broken"}</span></span>
                <span className="blk-kind">{KIND[b.kind] ?? b.kind}{changed ? " (edited copy)" : ""}</span>
                <span className="mono small">fingerprint {v.shown.slice(0, 8)}…</span>
                <span className="mono small muted">follows {(rewritten.includes(b.seq) && i > 0 ? view[i - 1].shown : b.prev_hash).slice(0, 8)}…</span>
              </button>
            </li>);
        })}
        <li className={`blk head ${headOk ? "bs-ok" : "bs-content"}`}><span className="blink" aria-hidden="true" /><div className="headbox"><strong>Saved head</strong><span className="mono small">{head.slice(0, 8)}…</span><span className="small muted">kept separately by the server</span></div></li>
      </ol>
      <p className={`headline ${headOk ? "" : "mismatch"}`}>Last fingerprint in your copy: <span className="mono small">{view[view.length - 1].shown.slice(0, 16)}…</span> · Fingerprint the server saved separately: <span className="mono small">{head.slice(0, 16)}…</span> · <strong>{!lastIsHead ? "not comparable (newer records exist)" : headOk ? "match" : "MISMATCH"}</strong></p>
      <div className="row">
        <button type="button" className="btn danger" onClick={doTamper} disabled={!selBlock || running}>{selBlock ? `Change record #${selBlock.seq} on my copy` : "Pick a record first"}</button>
        <button type="button" className="btn" onClick={coverTracks} disabled={!selBlock || edited[selBlock?.seq ?? -1] === undefined || running}>{running ? "Rewriting…" : "Let the attacker cover their tracks"}</button>
        <button type="button" className="btn" onClick={reset}>Reset</button>
      </div>
      {selBlock && edited[selBlock.seq] !== undefined && <details open><summary>What was changed in #{selBlock.seq}</summary><p className="small mono">was: {selBlock.payload_canonical}</p><p className="small mono">now: {edited[selBlock.seq]}</p></details>}
    </Card>
  );
}
