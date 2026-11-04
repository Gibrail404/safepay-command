"use client";
import Link from "next/link";
import { useConfig } from "@/components/providers";
import { useApi, type ReportInfo } from "@/lib/api";
import { Card, Empty, ErrorBox, Loading, Provenance } from "@/components/ui";

export default function ReportsPage() {
  const { cfg } = useConfig();
  const { data, error, loading, reload } = useApi<ReportInfo[]>(cfg, "/v1/reports");
  return (
    <>
      <h1>Reports</h1>
      <p className="muted">Every number below was produced by a command in the repository, not typed by hand. The chip says whether the data is real or simulated.</p>
      <Card>
        {loading ? <Loading what="Loading reports" /> : error ? <ErrorBox message={error} onRetry={reload} /> : !data || data.length === 0 ? <Empty>No reports.</Empty> : (
          <ul className="plain">{data.map((r) => <li key={r.name}>{r.available ? <Link href={`/reports/${r.name}`}>{r.title}</Link> : <span>{r.title}</span>} <Provenance value={r.provenance} /> {!r.available && <span className="muted">not generated on this server</span>}</li>)}</ul>)}
      </Card>
    </>
  );
}
