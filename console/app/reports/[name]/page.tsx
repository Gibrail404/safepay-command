"use client";
import { useParams } from "next/navigation";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useConfig } from "@/components/providers";
import { useApi, type Report } from "@/lib/api";
import { ErrorBox, Loading, Provenance } from "@/components/ui";

export default function ReportPage() {
  const { name } = useParams<{ name: string }>();
  const { cfg } = useConfig();
  const { data, error, loading, reload } = useApi<Report>(cfg, `/v1/reports/${name}`);
  if (loading) return <Loading what="Loading report" />;
  if (error || !data) return <ErrorBox message={error ?? "Not found."} onRetry={reload} />;
  return (
    <>
      <p><Link href="/reports">← All reports</Link></p>
      <p><Provenance value={data.provenance} /></p>
      <article className="report"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ img: () => null, table: (p) => <div className="table-wrap"><table {...p} /></div> }}>{data.markdown}</ReactMarkdown></article>
    </>
  );
}
