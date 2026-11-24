import React, { useState } from "react";
import { DAY, money, date } from "./api.js";

const W = 920, H = 300, PAD = { l: 68, r: 20, t: 14, b: 30 };
const toTs = s => new Date(s + "T12:00:00Z").getTime() / 1000;

function xTicks(t0, t1) {
  const span = t1 - t0;
  const every = span > 3 * 365 * DAY ? 12 : span > 365 * DAY ? 6 : 2;
  const d0 = new Date(t0 * 1000);
  const out = [];
  for (let mo = Math.floor((d0.getUTCFullYear() * 12 + d0.getUTCMonth()) / every) * every; ; mo += every) {
    const t = Date.UTC(Math.floor(mo / 12), mo % 12, 1) / 1000;
    if (t > t1) break;
    if (t >= t0) out.push(t);
  }
  return out;
}

export default function Chart({ hist, pred }) {
  const [range, setRange] = useState("all");
  const [tip, setTip] = useState(null);
  const pts = hist.points;
  if (!pts.length) return <div className="chart-empty">No price history yet.</div>;

  const now = hist.now;
  let t0 = pts[0].ts;
  if (range === "1y") t0 = Math.max(t0, now - 365 * DAY);
  if (range === "3y") t0 = Math.max(t0, now - 1095 * DAY);

  const next = pred?.available ? pred.next_drop : null;
  const fwd = next ? Math.max(0, Math.round(toTs(next.end) - now)) + 14 * DAY : 0;
  const t1 = now + Math.min(fwd, 200 * DAY);

  const lastBefore = [...pts].reverse().find(q => q.ts < t0);
  const vis = pts.filter(p => p.ts >= t0 || p === lastBefore);
  const maxV = Math.max(...vis.map(p => p.initial)) * 1.08;
  const x  = t => PAD.l + ((t - t0) / (t1 - t0 || 1)) * (W - PAD.l - PAD.r);
  const y  = v => H - PAD.b - (v / maxV) * (H - PAD.t - PAD.b);
  const cx = t => Math.min(Math.max(x(t), PAD.l), W - PAD.r);

  const seq = vis.map((p, i) => ({
    ...p,
    a: Math.max(p.ts, t0),
    b: Math.min(i + 1 < vis.length ? vis[i + 1].ts : now, t1),
  }));

  let basePath = "", finPath = "", areaPath = "";
  seq.forEach((p, i) => {
    basePath += `${i ? "L" : "M"}${cx(p.a)},${y(p.initial)}L${cx(p.b)},${y(p.initial)}`;
    finPath  += `${i ? "L" : "M"}${cx(p.a)},${y(p.final)}L${cx(p.b)},${y(p.final)}`;
    if (p.discount > 0)
      areaPath += `M${cx(p.a)},${y(p.initial)}L${cx(p.b)},${y(p.initial)}L${cx(p.b)},${y(p.final)}L${cx(p.a)},${y(p.final)}Z`;
  });
  const hikes = seq.filter((p, i) => i > 0 && vis[i].initial > vis[i - 1].initial);

  let fc = null;
  if (next) {
    const s = toTs(next.start), e = toTs(next.end);
    const xs = Math.max(x(Math.max(s, now)), x(now));
    const xe = Math.min(x(e), W - PAD.r);
    const [lo, hi] = next.price_range;
    fc = {
      xs, xe: Math.max(xe, xs + 6),
      yTop: y(hi), h: Math.max(y(lo) - y(hi), 4),
      yMid: y(next.expected_price),
      label: `forecast ≈ ${money(next.expected_price, hist.currency, hist.divisor)}`,
    };
  }

  const onMove = ev => {
    const r = ev.currentTarget.ownerSVGElement.getBoundingClientRect();
    const px = ((ev.clientX - r.left) / r.width) * W;
    const t = t0 + ((px - PAD.l) / (W - PAD.l - PAD.r)) * (t1 - t0);
    if (t > now) return setTip(null);
    const p = [...pts].reverse().find(q => q.ts <= t) || pts[0];
    setTip({ left: Math.min(ev.clientX - r.left + 12, r.width - 160), t: Math.round(t), p });
  };

  const M = v => money(v, hist.currency, hist.divisor);

  return (
    <div className="chart-wrap">
      <div className="chart-controls">
        {[["1y","1 Year"],["3y","3 Years"],["all","All Time"]].map(([k, l]) => (
          <button key={k} className={`filter-chip${range === k ? " active" : ""}`} onClick={() => setRange(k)}>{l}</button>
        ))}
        <span className="chart-legend">── price  ┄ base  ▲ hike  ▬ forecast</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Price history">
        {[0,1,2,3,4].map(i => {
          const v = (maxV / 1.08) * (i / 4);
          return (
            <g key={i}>
              <line x1={PAD.l} x2={W-PAD.r} y1={y(v)} y2={y(v)} stroke="var(--border)" strokeWidth="1" />
              <text x={PAD.l - 7} y={y(v) + 4} textAnchor="end">{M(Math.round(v))}</text>
            </g>
          );
        })}
        {xTicks(t0, t1).map(t => (
          <text key={t} x={x(t)} y={H - 9} textAnchor="middle">
            {new Date(t * 1000).toLocaleDateString(undefined, { month: "short", year: "2-digit", timeZone: "UTC" })}
          </text>
        ))}
        <path d={areaPath} fill="var(--green)" opacity=".15" />
        <path d={basePath} fill="none" stroke="var(--border)" strokeDasharray="4 4" strokeWidth="1.2" />
        <path d={finPath} fill="none" stroke="var(--blue)" strokeWidth="2.2" />
        {hikes.map(p => (
          <polygon key={p.ts} fill="var(--red)"
            points={`${cx(p.a)},${y(p.initial)-9} ${cx(p.a)-5},${y(p.initial)-1} ${cx(p.a)+5},${y(p.initial)-1}`} />
        ))}
        <line x1={x(now)} x2={x(now)} y1={PAD.t} y2={H-PAD.b} stroke="var(--muted)" strokeDasharray="3 5" />
        <text x={x(now)+4} y={PAD.t+11} fill="var(--muted)" fontSize="10">today</text>
        {fc && (
          <g>
            <rect x={fc.xs} y={fc.yTop} width={fc.xe - fc.xs} height={fc.h} fill="var(--amber)" opacity=".2" rx="3" />
            <line x1={fc.xs} x2={fc.xe} y1={fc.yMid} y2={fc.yMid} stroke="var(--amber)" strokeWidth="2.2" strokeDasharray="5 3" />
            <text x={Math.min(fc.xs+65, W-PAD.r)} y={fc.yTop-6} textAnchor="end" fill="var(--amber)" fontSize="11">{fc.label}</text>
          </g>
        )}
        <rect x={PAD.l} y={PAD.t} width={W-PAD.l-PAD.r} height={H-PAD.t-PAD.b}
              fill="transparent" style={{cursor:"crosshair"}}
              onMouseMove={onMove} onMouseLeave={() => setTip(null)} />
      </svg>
      {tip && (
        <div className="chart-tip" style={{ left: tip.left, top: 12 }}>
          <strong>{new Date(tip.t * 1000).toLocaleDateString(undefined, { year:"numeric", month:"short", day:"numeric" })}</strong>
          <br />
          {M(tip.p.final)}{tip.p.discount ? ` (−${tip.p.discount}%)` : ""}
        </div>
      )}
    </div>
  );
}
