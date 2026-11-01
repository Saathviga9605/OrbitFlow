import React, { useEffect, useRef, useState } from 'react';
import { reducedMotion, useWidth } from './viz.jsx';

/** Adds .in to every revealable element once it scrolls into view. */
export function useReveal() {
  useEffect(() => {
    const els = document.querySelectorAll('.kicker, h2, .lede, .insight, .panel, .stats, .pipe, .bigcompare');
    const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { rootMargin: '0px 0px -8% 0px' });
    els.forEach((el) => { el.classList.add('reveal'); io.observe(el); });
    return () => io.disconnect();
  }, []);
}

export function ScrollBar() {
  const ref = useRef(null);
  useEffect(() => {
    const on = () => {
      const h = document.documentElement;
      if (ref.current) ref.current.style.transform = `scaleX(${h.scrollTop / Math.max(h.scrollHeight - h.clientHeight, 1)})`;
    };
    window.addEventListener('scroll', on, { passive: true });
    return () => window.removeEventListener('scroll', on);
  }, []);
  return <div className="scrollbar" ref={ref} />;
}

/** Counts up to `to` the first time it becomes visible. */
export function Count({ to, format = (v) => v.toFixed(0), ms = 1300 }) {
  const ref = useRef(null);
  const [v, setV] = useState(reducedMotion() ? to : 0);
  useEffect(() => {
    if (reducedMotion()) return undefined;
    let raf;
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return;
      io.disconnect();
      const t0 = performance.now();
      const tick = (now) => {
        const k = Math.min(1, (now - t0) / ms);
        setV(to * (1 - (1 - k) ** 3));
        if (k < 1) raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    });
    if (ref.current) io.observe(ref.current);
    return () => { io.disconnect(); cancelAnimationFrame(raf); };
  }, [to, ms]);
  return <span ref={ref}>{format(v)}</span>;
}

/** 100 message dots: how many arrive late. The fastest way to read the headline. */
export function Waffle({ late, label, color }) {
  const n = Math.round(late * 100);
  return (
    <div className="waffle-wrap">
      <div className="waffle" role="img" aria-label={`${label}: about ${n} of 100 late`}>
        {Array.from({ length: 100 }, (_, i) => <i key={i} className={i >= 100 - n ? 'late' : ''} style={{ transitionDelay: `${i * 9}ms`, '--c': color }} />)}
      </div>
      <div className="waffle-num"><b><Count to={late * 100} format={(v) => `${v.toFixed(1)}%`} /></b><span>{label}</span></div>
    </div>
  );
}

/** Two dots per row joined by a line: where each strategy lands, and which way the gap points. */
export function Dumbbell({ rows, unit, format, aName, bName, aColor, bColor, lowerBetter = true }) {
  const [ref, w] = useWidth();
  const [hover, setHover] = useState(null);
  const lab = Math.min(170, w * 0.36);
  const hi = Math.max(...rows.flatMap((r) => [r.a, r.b])) * 1.06;
  const X = (v) => lab + (v / hi) * (w - lab - 18);
  const rh = 30;
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <div className="legend"><span><i style={{ background: aColor }} />{aName}</span><span><i style={{ background: bColor }} />{bName}</span></div>
      <svg width={w} height={rows.length * rh + 22} role="img" aria-label={`${aName} vs ${bName}, ${unit}`} style={{ display: 'block' }}>
        {[0, 0.5, 1].map((f) => <g key={f}><line x1={X(hi * f / 1.06)} x2={X(hi * f / 1.06)} y1={0} y2={rows.length * rh} stroke="var(--line)" /><text x={X(hi * f / 1.06)} y={rows.length * rh + 15} textAnchor="middle" fontSize="11" fill="var(--ink-3)" fontFamily="var(--mono)">{format(hi * f / 1.06)}</text></g>)}
        {rows.map((r, i) => {
          const y = i * rh + 15; const good = lowerBetter ? r.b <= r.a : r.b >= r.a;
          return (
            <g key={r.name} onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)}>
              <rect x={0} y={i * rh} width={w} height={rh} fill={hover === i ? 'var(--raised)' : 'transparent'} />
              <text x={2} y={y + 4} fontSize="13" fill="var(--ink)">{r.name}</text>
              <line className="dumb-line" x1={X(r.a)} x2={X(r.b)} y1={y} y2={y} stroke={good ? 'var(--orbit)' : 'var(--reactive)'} strokeWidth="3" style={{ animationDelay: `${i * 60}ms` }} />
              <circle className="dumb-dot" cx={X(r.a)} cy={y} r="6" fill={aColor} stroke="var(--surface)" strokeWidth="2" />
              <circle className="dumb-dot" cx={X(r.b)} cy={y} r="6" fill={bColor} stroke="var(--surface)" strokeWidth="2" />
            </g>
          );
        })}
      </svg>
      {hover != null && <div className="tip" style={{ left: lab, top: hover * rh + 58 }}>{rows[hover].name}: {aName} <b className="mono">{format(rows[hover].a)}</b>, {bName} <b className="mono">{format(rows[hover].b)}</b> {unit}</div>}
    </div>
  );
}

/** Live demand strip: one bar per cell, a tick for the forecast, glow when a beam is on it. */
export function DemandStrip({ demand, forecast, lit, emergency, max = 45 }) {
  return (
    <div className="strip" role="img" aria-label="Demand per area">
      {demand.map((d, i) => (
        <div key={i} className={`bar ${lit.includes(i) ? 'on' : ''} ${emergency.includes(i) ? 'em' : ''}`} title={`Area ${i}: ${d.toFixed(1)} Mbps now, ${forecast[i].toFixed(1)} forecast`}>
          <i style={{ height: `${Math.min(100, (d / max) * 100)}%` }} />
          <u style={{ bottom: `${Math.min(100, (forecast[i] / max) * 100)}%` }} />
          <span>{i}</span>
        </div>
      ))}
    </div>
  );
}

/** Semi-circular dial. */
export function Dial({ value, max, label, display, color = 'var(--beam)' }) {
  const a = Math.min(1, value / max);
  const len = Math.PI * 40;
  return (
    <div className="dial">
      <svg viewBox="0 0 100 58" role="img" aria-label={`${label}: ${display}`}>
        <path d="M10 52 A40 40 0 0 1 90 52" fill="none" stroke="var(--line-strong)" strokeWidth="7" strokeLinecap="round" />
        <path d="M10 52 A40 40 0 0 1 90 52" fill="none" stroke={color} strokeWidth="7" strokeLinecap="round" strokeDasharray={`${a * len} ${len}`} style={{ transition: 'stroke-dasharray .25s' }} />
      </svg>
      <b className="mono">{display}</b><span>{label}</span>
    </div>
  );
}

/** One dot per document, grouped by category. */
export function DocMap({ docs }) {
  const [h, setH] = useState(null);
  const groups = [...new Set(docs.map((d) => d.category))];
  const NAME = { AI_Strategies: 'AI strategies and policy', AI_Use_Cases: 'Standards and use cases', Regulatory_Supplement: 'Satellite regulation' };
  return (
    <div className="docmap">
      {groups.map((g) => (
        <div key={g}><h5>{NAME[g] || g}</h5><div className="docs">
          {docs.filter((d) => d.category === g).map((d, i) => { const s = 8 + Math.sqrt(d.pages) * 1.5; return <i key={d.doc_id} style={{ width: s, height: s, animationDelay: `${i * 18}ms` }} onPointerEnter={() => setH(d)} onPointerLeave={() => setH(null)} />; })}
        </div></div>
      ))}
      <p className="note" style={{ minHeight: 22, margin: '10px 0 0' }}>{h ? `${h.title} · ${h.pages} pages` : 'Hover a dot. Bigger means more pages.'}</p>
    </div>
  );
}
