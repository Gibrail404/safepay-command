"use client";
import { useEffect, useRef, useState } from "react";
import { useConfig } from "@/components/providers";
import { call, useApi, type Frontier, type FrontierRow, type SimResult } from "@/lib/api";
import { useCountTo } from "@/components/motion";
import { Card, ErrorBox, Loading, Provenance } from "@/components/ui";

const W = 640, H = 380, PL = 58, PR = 18, PT = 18, PB = 52;
const px = (v: number) => PL + (v / 40) * (W - PL - PR);          // x axis: good payments held, 0 to 40 %
const py = (v: number) => H - PB - (v / 100) * (H - PT - PB);      // y axis: scam money stopped, 0 to 100 %

function Num({ value, digits = 0, suffix = "" }: { value: number; digits?: number; suffix?: string }) {
  const v = useCountTo(value);
  return <>{v.toFixed(digits)}{suffix}</>;
}

export default function LabPage() {
  const { cfg } = useConfig();
  const [warn, setWarn] = useState(0.8);
  const [hold, setHold] = useState(1.6);
  const frontier = useApi<Frontier>(cfg, "/v1/simulations/frontier?n=100000&seed=0");
  const [sim, setSim] = useState<SimResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const seq = useRef(0);

  useEffect(() => {
    const mine = ++seq.current;
    setBusy(true);
    const t = window.setTimeout(async () => {
      try {
        const r = await call<SimResult>(cfg, "/v1/simulations", { method: "POST", body: { warn_from: warn, hold_from: hold, n: 100000, seed: 0 } });
        if (mine === seq.current) { setSim(r); setError(null); }
      } catch (e) { if (mine === seq.current) setError((e as Error).message); }
      finally { if (mine === seq.current) setBusy(false); }
    }, 300);
    return () => window.clearTimeout(t);
  }, [cfg, warn, hold]);

  const rows: FrontierRow[] = frontier.data ? [...frontier.data.rows].sort((a, b) => a.good_payments_held_share - b.good_payments_held_share) : [];
  const best = rows.length ? rows.reduce((a, b) => (b.value_per_payment > a.value_per_payment ? b : a)) : null;
  const r = sim?.result;
  const path = rows.map((p, i) => `${i ? "L" : "M"}${px(p.good_payments_held_share * 100).toFixed(1)},${py(p.scam_money_stopped_share * 100).toFixed(1)}`).join(" ");

  return (
    <>
      <h1>Decision Lab</h1>
      <p><Provenance value="simulated" /> <span className="muted">Simulated payments with assumed scam behaviour. Amounts follow the real ULB card data. Not evidence about real customers.</span></p>
      <p>Every good payment you pause costs a customer some friction. Every scam you miss costs money. Move the two thresholds and see the trade-off for a simple policy: <strong>warn</strong> payments from one suspicion score, and <strong>hold</strong> them from a higher one. The simulator runs 100,000 payments with a fixed seed, so the same sliders always give the same answer.</p>
      <Card title="Your policy">
        <div className="sliders">
          <label>Warn from score <strong>{warn.toFixed(1)}</strong>
            <input type="range" min={0} max={3.5} step={0.1} value={warn} onChange={(e) => { const v = Number(e.target.value); setWarn(v); if (v > hold) setHold(v); }} aria-label="Warn from score" /></label>
          <label>Hold from score <strong>{hold.toFixed(1)}</strong>
            <input type="range" min={0} max={3.5} step={0.1} value={hold} onChange={(e) => { const v = Number(e.target.value); setHold(v); if (v < warn) setWarn(v); }} aria-label="Hold from score" /></label>
        </div>
        {error ? <ErrorBox message={error} /> : (
          <div className="stats" aria-busy={busy}>
            <div className="stat"><div className="stat-value">{r ? <Num value={r.scam_money_stopped_share * 100} suffix="%" /> : "…"}</div><div className="stat-label">Scam money stopped</div></div>
            <div className="stat"><div className="stat-value">{r ? <Num value={r.good_payments_held_share * 100} digits={1} suffix="%" /> : "…"}</div><div className="stat-label">Good payments held</div></div>
            <div className="stat"><div className="stat-value">{r ? <Num value={r.good_payments_warned_share * 100} digits={1} suffix="%" /> : "…"}</div><div className="stat-label">Good payments warned</div></div>
            <div className="stat"><div className="stat-value">{r ? <Num value={r.value_per_payment} digits={2} /> : "…"}</div><div className="stat-label">Value per payment (closer to 0 is better)</div></div>
          </div>)}
      </Card>
      <Card title="The trade-off">
        {frontier.loading ? <Loading what="Running the simulator" /> : frontier.error ? <ErrorBox message={frontier.error} onRetry={frontier.reload} /> : (
          <>
            <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Scam money stopped against good payments held. Your policy is the large dot.">
              {[0, 20, 40, 60, 80, 100].map((t) => <g key={t}><line x1={PL} x2={W - PR} y1={py(t)} y2={py(t)} className="grid" /><text x={PL - 8} y={py(t) + 4} textAnchor="end" className="tick">{t}%</text></g>)}
              {[0, 10, 20, 30, 40].map((t) => <g key={t}><line x1={px(t)} x2={px(t)} y1={PT} y2={H - PB} className="grid" /><text x={px(t)} y={H - PB + 18} textAnchor="middle" className="tick">{t}%</text></g>)}
              <text x={(PL + W - PR) / 2} y={H - 8} textAnchor="middle" className="axis">Good payments held (more friction →)</text>
              <text transform={`translate(14 ${(PT + H - PB) / 2}) rotate(-90)`} textAnchor="middle" className="axis">Scam money stopped</text>
              <path d={path} className="curve" />
              {rows.map((p) => <circle key={p.hold_from} cx={px(p.good_payments_held_share * 100)} cy={py(p.scam_money_stopped_share * 100)} r={3.5} className="refdot"><title>{`Hold from ${p.hold_from >= 90 ? "never" : p.hold_from}: stops ${(p.scam_money_stopped_share * 100).toFixed(0)}% of scam money, holds ${(p.good_payments_held_share * 100).toFixed(1)}% of good payments`}</title></circle>)}
              {best && <g><circle cx={px(best.good_payments_held_share * 100)} cy={py(best.scam_money_stopped_share * 100)} r={8} className="bestring" />
                <text x={px(best.good_payments_held_share * 100)} y={py(best.scam_money_stopped_share * 100) + 26} textAnchor="middle" className="bestlabel">lowest total cost on this curve</text></g>}
              {r && <g className="marker" style={{ transform: `translate(${px(r.good_payments_held_share * 100)}px, ${py(r.scam_money_stopped_share * 100)}px)` }}><circle r={9} className="halo" /><circle r={6} className="you" /></g>}
            </svg>
            <p className="muted small">The curve is a family of reference policies (warn a fixed 0.4 below hold). Your policy is the large dot and may sit off the curve. {best && <>Among the reference points, holding from <strong>{best.hold_from}</strong> has the best value per payment ({best.value_per_payment.toFixed(2)}).</>}</p>
            <details><summary>Show the numbers</summary>
              <div className="table-wrap"><table><thead><tr><th>Hold from</th><th>Scam money stopped</th><th>Good held</th><th>Good warned</th><th>Value per payment</th></tr></thead><tbody>
                {rows.map((p) => <tr key={p.hold_from}><td>{p.hold_from >= 90 ? "never" : p.hold_from}</td><td>{(p.scam_money_stopped_share * 100).toFixed(0)}%</td><td>{(p.good_payments_held_share * 100).toFixed(1)}%</td><td>{(p.good_payments_warned_share * 100).toFixed(1)}%</td><td>{p.value_per_payment.toFixed(2)}</td></tr>)}
              </tbody></table></div></details>
            <details><summary>Assumptions used (all simulated)</summary><pre className="small">{JSON.stringify(frontier.data?.assumptions, null, 1)}</pre></details>
          </>)}
      </Card>
    </>
  );
}
