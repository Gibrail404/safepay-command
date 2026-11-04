"use client";
import { useConfig } from "@/components/providers";
import { useApi, type LedgerEntry } from "@/lib/api";
import { Card, Chip, Empty, ErrorBox, Loading } from "@/components/ui";

export default function AuditPage() {
  const { cfg } = useConfig();
  const verify = useApi<{ ok: boolean; checked: number; reason: string | null; bad_seq: number | null }>(cfg, "/v1/audit/verify");
  const entries = useApi<LedgerEntry[]>(cfg, "/v1/audit?limit=100");
  return (
    <>
      <h1>Audit trail</h1>
      <p className="muted">Every import, investigation and decision is written to a tamper-evident chain: each entry includes the fingerprint of the one before it.</p>
      <Card title="Integrity check">
        {verify.loading ? <Loading what="Checking the chain" /> : verify.error ? <ErrorBox message={verify.error} onRetry={verify.reload} /> : verify.data && (
          verify.data.ok ? <p><Chip kind="good">Chain intact</Chip> {verify.data.checked} entries checked.</p> : <p><Chip kind="high">Chain broken</Chip> {verify.data.reason} (entry {verify.data.bad_seq})</p>)}
      </Card>
      <Card title="Recent entries (oldest first, up to 100)">
        {entries.loading ? <Loading what="Loading entries" /> : entries.error ? <ErrorBox message={entries.error} onRetry={entries.reload} /> : !entries.data || entries.data.length === 0 ? <Empty>Nothing has been recorded yet.</Empty> : (
          <div className="table-wrap"><table><thead><tr><th>#</th><th>What happened</th><th>When</th><th>Details</th><th>Fingerprint</th></tr></thead>
            <tbody>{entries.data.map((e) => <tr key={e.seq}><td>{e.seq}</td><td>{e.kind.replace("case.", "").replace(".", " ")}</td><td>{new Date(e.ts).toLocaleString()}</td><td className="mono small">{summary(e)}</td><td className="mono small">{e.hash.slice(0, 12)}</td></tr>)}</tbody></table></div>)}
      </Card>
    </>
  );
}

function summary(e: LedgerEntry): string {
  const p = e.payload as Record<string, unknown>;
  if (e.kind === "case.dispositioned") return `${p.actor} → ${p.decision} (${p.labels_written} labels)`;
  if (e.kind === "case.investigated") return `${p.path}: ${p.recommendation}`;
  if (e.kind === "case.imported") return `${p.count} cases`;
  return Object.keys(p).slice(0, 3).join(", ");
}
