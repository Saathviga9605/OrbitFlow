import React, { useEffect, useMemo, useRef, useState } from 'react';

export const COLORS = {
  OrbitFlow: 'var(--orbit)', 'BRIDGE alone': 'var(--bridge)', BRIDGE: 'var(--bridge)', 'BRIDGE no-forecast': 'var(--static)',
  'Reactive greedy': 'var(--reactive)', 'Static round-robin': '#7d8791', 'Heuristic-predictive': '#c9c4b8', BC: '#a8a39a',
};
export const reducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

export function useWidth() {
  const ref = useRef(null);
  const [w, setW] = useState(600);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

const ticks = (lo, hi, n = 4) => {
  const step0 = (hi - lo) / n || 1;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0);
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(6));
  return out;
};

/** Multi-series line chart with a crosshair tooltip. One y axis, recessive grid, direct labels. */
export function LineChart({ series, height = 240, xLabel, yLabel, marks = [], cursor, onHover, format = (v) => v.toFixed(1), x0 = 0, yMax, yMin }) {
  const [ref, w] = useWidth();
  const [hover, setHover] = useState(null);
  const m = { l: 44, r: series.length <= 4 ? 96 : 12, t: 12, b: 34 };
  const n = series[0].values.length;
  const xs = series[0].x || series[0].values.map((_, i) => i + x0);
  const all = series.flatMap((s) => s.values.filter((v) => v != null));
  const hi = yMax ?? Math.max(...all, 1e-6) * 1.08;
  const lo = yMin ?? Math.min(0, ...all);
  const X = (x) => m.l + ((x - xs[0]) / (xs[n - 1] - xs[0] || 1)) * (w - m.l - m.r);
  const Y = (v) => height - m.b - ((v - lo) / (hi - lo || 1)) * (height - m.t - m.b);
  const path = (vals) => { let d = ''; let pen = false; vals.forEach((v, i) => { if (v == null) { pen = false; return; } d += `${pen ? 'L' : 'M'}${X(xs[i]).toFixed(1)} ${Y(v).toFixed(1)}`; pen = true; }); return d; };
  const move = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const f = (e.clientX - r.left - m.l) / (w - m.l - m.r);
    const i = Math.max(0, Math.min(n - 1, Math.round(f * (n - 1))));
    setHover(i); onHover?.(xs[i]);
  };
  // spread end labels so they never collide
  const ends = series.map((s) => ({ s, y: Y([...s.values].reverse().find((v) => v != null) ?? 0) })).sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 14) ends[i].y = ends[i - 1].y + 14;
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      {series.length > 1 && <div className="legend">{series.map((s) => <span key={s.name}><i style={{ background: s.color }} />{s.name}</span>)}</div>}
      <svg width={w} height={height} onPointerMove={move} onPointerLeave={() => { setHover(null); }} role="img" aria-label={`${yLabel} over ${xLabel}: ${series.map((s) => s.name).join(', ')}`} style={{ display: 'block', touchAction: 'pan-y' }}>
        {ticks(lo, hi).map((t) => <g key={t}><line x1={m.l} x2={w - m.r} y1={Y(t)} y2={Y(t)} stroke="var(--line)" /><text x={m.l - 7} y={Y(t) + 4} textAnchor="end" fill="var(--ink-3)" fontSize="11" fontFamily="var(--mono)">{t}</text></g>)}
        {ticks(xs[0], xs[n - 1], w < 420 ? 4 : 8).map((t) => <text key={t} x={X(t)} y={height - m.b + 15} textAnchor="middle" fill="var(--ink-3)" fontSize="11" fontFamily="var(--mono)">{t}</text>)}
        <text x={w - m.r} y={height - 3} textAnchor="end" fill="var(--ink-3)" fontSize="11">{xLabel}</text>
        <text x={m.l} y={9} fill="var(--ink-3)" fontSize="11">{yLabel}</text>
        {marks.map((k) => k.to != null
          ? <rect key={k.label} x={X(k.x)} width={Math.max(0, X(k.to) - X(k.x))} y={m.t} height={height - m.t - m.b} fill={k.color} opacity=".1" />
          : <g key={k.label}><line x1={X(k.x)} x2={X(k.x)} y1={m.t} y2={height - m.b} stroke={k.color} strokeDasharray="3 3" /><text x={X(k.x) + 4} y={m.t + 10} fill={k.color} fontSize="11">{k.label}</text></g>)}
        {series.map((s) => <path key={s.name} d={path(s.values)} fill="none" stroke={s.color} strokeWidth={s.width || 2} strokeDasharray={s.dash} strokeLinejoin="round" />)}
        {series.length <= 4 && ends.map(({ s, y }) => <text key={s.name} x={w - m.r + 6} y={y + 4} fill="var(--ink-2)" fontSize="11">{s.name.length > 14 ? s.name.slice(0, 13) + '…' : s.name}</text>)}
        {cursor != null && <line x1={X(cursor)} x2={X(cursor)} y1={m.t} y2={height - m.b} stroke="var(--beam)" />}
        {hover != null && <line x1={X(xs[hover])} x2={X(xs[hover])} y1={m.t} y2={height - m.b} stroke="var(--ink-3)" />}
        {hover != null && series.map((s) => s.values[hover] != null && <circle key={s.name} cx={X(xs[hover])} cy={Y(s.values[hover])} r="4" fill={s.color} stroke="var(--surface)" strokeWidth="2" />)}
      </svg>
      {hover != null && (
        <div className="tip" style={{ left: Math.min(X(xs[hover]) + 10, w - 170), top: 26 }}>
          <div style={{ color: 'var(--ink-3)' }}>{xLabel} {xs[hover]}</div>
          {series.map((s) => s.values[hover] != null && <div key={s.name}><i style={{ display: 'inline-block', width: 8, height: 8, background: s.color, marginRight: 6 }} />{s.name}: <b className="mono">{format(s.values[hover])}</b></div>)}
        </div>
      )}
    </div>
  );
}

/** Mean with 95% CI per controller, on a shared scale. */
export function DotCI({ rows, format, unit }) {
  const [ref, w] = useWidth();
  const [hover, setHover] = useState(null);
  const lab = Math.min(150, w * 0.36);
  const R = 62;
  const lo = Math.min(0, ...rows.map((r) => r.lo));
  const hi = Math.max(...rows.map((r) => r.hi), 1e-6) * 1.03;
  const X = (v) => lab + ((v - lo) / (hi - lo || 1)) * (w - lab - R);
  const rh = 34;
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <svg width={w} height={rows.length * rh + 8} role="img" aria-label={`Comparison, ${unit}`} style={{ display: 'block' }}>
        {ticks(lo, hi, 4).map((t) => <line key={t} x1={X(t)} x2={X(t)} y1={0} y2={rows.length * rh} stroke="var(--line)" />)}
        {rows.map((r, i) => (
          <g key={r.name} onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)}>
            <rect x={0} y={i * rh} width={w} height={rh} fill="transparent" />
            <text x={0} y={i * rh + 21} fill="var(--ink)" fontSize="13">{r.name}</text>
            <line x1={X(r.lo)} x2={X(r.hi)} y1={i * rh + 17} y2={i * rh + 17} stroke={r.color} strokeWidth="2" />
            <line x1={lab} x2={X(r.mean)} y1={i * rh + 17} y2={i * rh + 17} stroke={r.color} strokeWidth="1" opacity=".3" />
            <circle cx={X(r.mean)} cy={i * rh + 17} r="6" fill={r.color} stroke="var(--surface)" strokeWidth="2" />
            <text x={w - 2} y={i * rh + 21} textAnchor="end" fill="var(--ink)" fontSize="13" fontFamily="var(--mono)">{format(r.mean)}</text>
          </g>
        ))}
      </svg>
      {hover != null && <div className="tip" style={{ left: lab, top: hover * rh + rh }}>{rows[hover].name}: <b className="mono">{format(rows[hover].mean)}</b> {unit} (95% CI {format(rows[hover].lo)} to {format(rows[hover].hi)}, n={rows[hover].n})</div>}
    </div>
  );
}

const hexPath = (cx, cy, r) => Array.from({ length: 6 }, (_, i) => {
  const a = Math.PI / 6 + (i * Math.PI) / 3;
  return `${(cx + r * Math.cos(a)).toFixed(1)},${(cy + r * Math.sin(a)).toFixed(1)}`;
}).join(' ');

/** The 19-cell footprint, at real cell coordinates. Fill = backlog; ring + label = lit beam and watts. */
export function HexMap({ cells, lit, power, load, loadMax, emergency = [], border = [], capActive, selected, onSelect, title, compact }) {
  const geo = useMemo(() => {
    const xs = cells.map((c) => c.x); const ys = cells.map((c) => c.y);
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2; const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
    const d = Math.min(...cells.slice(1).map((c) => Math.hypot(c.x - cells[0].x, c.y - cells[0].y)));
    const k = 100 / (d / 2 * 1.155 * 1.0 * 2);        // one hex radius maps to ~50 units
    return cells.map((c) => ({ x: (c.x - cx) * k, y: -(c.y - cy) * k })).map((c) => c);
  }, [cells]);
  const r = useMemo(() => {
    const d = Math.min(...geo.slice(1).map((c) => Math.hypot(c.x - geo[0].x, c.y - geo[0].y)));
    return (d / Math.sqrt(3)) * 0.97;
  }, [geo]);
  const vb = useMemo(() => {
    const pad = r * 1.25;
    const x0 = Math.min(...geo.map((c) => c.x)) - pad; const x1 = Math.max(...geo.map((c) => c.x)) + pad;
    const y0 = Math.min(...geo.map((c) => c.y)) - pad; const y1 = Math.max(...geo.map((c) => c.y)) + pad;
    return `${x0} ${y0} ${x1 - x0} ${y1 - y0}`;
  }, [geo, r]);
  const litSet = new Set(lit);
  return (
    <div>
      {title && <h4 style={{ margin: '0 0 6px', font: '600 14px var(--sans)' }}>{title}</h4>}
      <svg viewBox={vb} style={{ width: '100%', display: 'block', maxHeight: compact ? 300 : 460 }} role="img"
        aria-label={`Footprint: beams on cells ${lit.join(', ')}${emergency.length ? `; emergency cells ${emergency.join(', ')}` : ''}`}>
        {geo.map((g, i) => {
          const f = Math.min(1, (load[i] || 0) / loadMax);
          const isLit = litSet.has(i);
          const em = emergency.includes(i); const bd = border.includes(i);
          const fill = `rgb(${Math.round(26 + f * 165)},${Math.round(31 + f * 92)},${Math.round(37 + f * 15)})`;
          return (
            <g key={i} onClick={onSelect ? () => onSelect(i) : undefined} style={{ cursor: onSelect ? 'pointer' : 'default' }}>
              <title>{`Cell ${i}: backlog ${Math.round(load[i] || 0)} kb${isLit ? `, lit at ${power?.[i]?.toFixed(1)} W` : ', dark'}${em ? ', emergency' : ''}${bd ? ', border cell' : ''}`}</title>
              <polygon points={hexPath(g.x, g.y, r)} fill={fill} stroke={bd ? 'var(--warning)' : 'var(--bg)'} strokeWidth={bd ? (capActive ? 3 : 1.5) : 2} strokeDasharray={bd && !capActive ? '5 4' : undefined} />
              {isLit && <polygon points={hexPath(g.x, g.y, r * 0.8)} fill="rgba(95,227,192,.2)" stroke="var(--beam)" strokeWidth="3.5" style={{ filter: 'drop-shadow(0 0 5px rgba(95,227,192,.75))' }} />}
              {selected === i && <polygon points={hexPath(g.x, g.y, r * 0.99)} fill="none" stroke="var(--ink)" strokeWidth="2" />}
              {em && <text x={g.x} y={g.y - r * 0.42} textAnchor="middle" fill="var(--critical)" fontSize={r * 0.42} fontWeight="700" style={{ pointerEvents: 'none' }}>▲</text>}
              <text x={g.x} y={g.y + (isLit ? r * 0.02 : r * 0.14)} textAnchor="middle" fill="var(--ink-2)" fontSize={r * 0.34} fontFamily="var(--mono)" style={{ pointerEvents: 'none' }}>{i}</text>
              {isLit && power && <text x={g.x} y={g.y + r * 0.42} textAnchor="middle" fill="var(--ink)" fontWeight="600" fontSize={r * 0.36} fontFamily="var(--mono)" style={{ pointerEvents: 'none' }}>{power[i].toFixed(0)}W</text>}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
