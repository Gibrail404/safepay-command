"use client";
import { useState } from "react";
import Link from "next/link";
import { useConfig } from "@/components/providers";
import { useApi, type CaseRow, type Stats } from "@/lib/api";
import { Card, Chip, Empty, ErrorBox, Loading, Provenance, Stat } from "@/components/ui";

const PAGE = 25;

export default function CasesPage() {
  const { cfg } = useConfig();
  const [status, setStatus] = useState<"" | "open" | "dispositioned">("open");
  const [offset, setOffset] = useState(0);
  const stats = useApi<Stats>(cfg, "/v1/cases/stats");
  const list = useApi<{ total: number; cases: CaseRow[] }>(cfg, `/v1/cases?limit=${PAGE}&offset=${offset}${status ? `&status=${status}` : ""}`);
  return (
    <>
      <h1>Cases</h1>
      <div className="stats">
        {stats.data ? <>
          <Stat label="Open cases" value={stats.data.open} />
          <Stat label="Open, high priority" value={stats.data.open_high_priority} />
          <Stat label="Decided" value={stats.data.dispositioned} />
          <Stat label="Labels collected" value={stats.data.labels} />
        </> : stats.error ? <ErrorBox message={stats.error} onRetry={stats.reload} /> : <Loading what="Loading counts" />}
      </div>
      <Card title="Queue" aside={
        <label className="inline">Show
          <select value={status} onChange={(e) => { setStatus(e.target.value as typeof status); setOffset(0); }}>
            <option value="open">Open cases</option><option value="dispositioned">Decided cases</option><option value="">All cases</option>
          </select>
        </label>}>
        {list.loading ? <Loading what="Loading cases" /> : list.error ? <ErrorBox message={list.error} onRetry={list.reload} /> :
          !list.data || list.data.cases.length === 0 ? <Empty>No cases here yet. Cases appear when alerts are imported into this server.</Empty> : (
            <>
              <div className="table-wrap"><table>
                <thead><tr><th>Case</th><th>Priority</th><th>Alerts</th><th>Highest score</th><th>Data</th><th>Status</th></tr></thead>
                <tbody>{list.data.cases.map((c) => (
                  <tr key={c.id}>
                    <td><Link href={`/cases/${c.id}`}>{c.title}</Link></td>
                    <td><Chip kind={c.priority === "high" ? "high" : "normal"}>{c.priority === "high" ? "High" : "Normal"}</Chip></td>
                    <td>{c.alerts}</td><td>{c.max_score.toFixed(2)}</td>
                    <td><Provenance value={c.provenance} /></td>
                    <td>{c.status === "open" ? <Chip kind="open">Open</Chip> : <Chip kind="done">{labelOf(c.disposition?.decision)}</Chip>}</td>
                  </tr>))}</tbody>
              </table></div>
              <div className="pager">
                <button type="button" className="btn" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
                <span>{offset + 1} to {Math.min(offset + PAGE, list.data.total)} of {list.data.total}</span>
                <button type="button" className="btn" disabled={offset + PAGE >= list.data.total} onClick={() => setOffset(offset + PAGE)}>Next</button>
              </div>
            </>)}
      </Card>
    </>
  );
}

export function labelOf(decision?: string) {
  return decision === "confirmed_illicit" ? "Confirmed illicit" : decision === "dismissed_licit" ? "Dismissed" : decision === "escalated" ? "Escalated" : "Decided";
}
