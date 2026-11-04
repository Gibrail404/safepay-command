"use client";
import type { Item } from "@/lib/api";

/** The real links between the alerts of one case, drawn as a small network. Positions are only a layout (a circle); the lines and scores are the data. */
export function AlertNetwork({ items, links }: { items: Item[]; links: string[][] }) {
  const W = 560, H = 300, cx = W / 2, cy = H / 2, R = Math.min(120, 24 + items.length * 9);
  const pos = new Map(items.map((it, i) => { const a = (2 * Math.PI * i) / items.length - Math.PI / 2; return [it.ref, { x: cx + R * 1.5 * Math.cos(a), y: cy + R * Math.sin(a), it }] as const; }));
  const edges = links.filter(([a, b]) => pos.has(a) && pos.has(b));
  const color = (s: number) => (s >= 0.95 ? "#c0392b" : s >= 0.8 ? "#d9822b" : "#8a96ad");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="network" role="img" aria-label={`${items.length} alerts and ${edges.length} direct links between them`}>
      {edges.map(([a, b], i) => { const p = pos.get(a)!, q = pos.get(b)!; return <line key={i} x1={p.x} y1={p.y} x2={q.x} y2={q.y} className="nlink" style={{ animationDelay: `${i * 40}ms` }} />; })}
      {[...pos.values()].map(({ x, y, it }, i) => (
        <g key={it.ref} className="nnode" style={{ animationDelay: `${i * 60}ms` }}>
          <title>{`Transaction ${it.ref}: score ${it.score.toFixed(2)}, ${it.facts.neighbours ?? 0} linked transactions`}</title>
          <circle cx={x} cy={y} r={7 + it.score * 7} fill={color(it.score)} fillOpacity={0.85} stroke="var(--panel)" strokeWidth={2} />
          <text x={x} y={y + 22 + it.score * 4} textAnchor="middle" className="tick">…{it.ref.slice(-4)}</text>
        </g>))}
    </svg>
  );
}
