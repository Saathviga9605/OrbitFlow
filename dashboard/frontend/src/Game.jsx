import React, { useEffect, useMemo, useRef, useState } from 'react';
import { HexMap } from './viz.jsx';
import { newState, playerPower, score, simulateRecorded, step } from './physics.js';
import { useI18n } from './i18n.jsx';

const SPEEDS = [['relaxed', 700], ['normal', 400], ['hard', 200]];
const pct = (v, d = 1) => `${(v * 100).toFixed(d)}%`;

export default function Game({ d }) {
  const { t: tr } = useI18n();
  const r = d.flood_replay; const p = r.phys;
  const ai = useMemo(() => simulateRecorded(r.runs.OrbitFlow.series, p), [r, p]);
  const aiFinal = useMemo(() => score(ai, p), [ai, p]);
  const [phase, setPhase] = useState('ready');
  const [speed, setSpeed] = useState(400);
  // start with the known hotspots and the flood cells, up to the beam count
  const [picked, setPicked] = useState(() => [...new Set([...(r.meta.background_hot || []), r.meta.event_cell, ...r.meta.emergency_cells])].slice(0, p.k));
  const [, force] = useState(0);
  const sim = useRef(newState(p));
  const pickedRef = useRef(picked);
  pickedRef.current = picked;
  const t = Math.min(sim.current.t, p.rate.length - 1);

  useEffect(() => {
    if (phase !== 'play') return undefined;
    const id = setInterval(() => {
      const s = sim.current; const cells = pickedRef.current;
      if (s.t >= p.rate.length) { setPhase('done'); return; }
      const lit = new Array(p.rate[0].length).fill(false);
      cells.forEach((c) => { lit[c] = true; });
      step(s, p, lit, playerPower(cells, s.t, p));
      force((v) => v + 1);
      if (s.t >= p.rate.length) setPhase('done');
    }, speed);
    return () => clearInterval(id);
  }, [phase, speed, p]);

  const toggle = (c) => setPicked((x) => (x.includes(c) ? x.filter((y) => y !== c) : x.length < p.k ? [...x, c] : [...x.slice(1), c]));
  const start = () => { sim.current = newState(p); setPhase('play'); force((v) => v + 1); };
  const load = sim.current.qRt.map((q, i) => q + sim.current.qNrt[i]);
  const you = score(sim.current.history, p);
  const aiNow = score(ai.slice(0, sim.current.t), p);
  const emergency = t >= p.emergency_from && t < p.emergency_to ? p.emergency_cells : [];
  const power = playerPower(picked, t, p);
  const event = [...r.events].reverse().find((e) => e.slot <= t);
  const rows = [
    [tr('game.r_em'), you.emergency, aiFinal.emergency, (v) => pct(v), false],
    [tr('game.r_late'), you.late, aiFinal.late, (v) => pct(v), true],
    [tr('game.r_wait'), you.delay, aiFinal.delay, (v) => `${v.toFixed(1)} ms`, true],
    [tr('game.r_tp'), you.throughput, aiFinal.throughput, (v) => `${v.toFixed(0)} Mbps`, false],
  ];
  const wins = rows.filter(([, a, b, , low]) => (low ? a < b : a > b)).length;
  const verdict = tr(wins >= 3 ? 'game.win' : wins === 2 ? 'game.draw' : 'game.lose');
  const slowBy = Math.round(speed / p.slot_ms);

  return (
    <section className="ch" id="game"><div className="wrap">
      <p className="kicker">{tr('game.kicker')}</p>
      <h2>{tr('game.h2')}</h2>
      <p className="lede">{tr('game.lede', { n: slowBy, k: p.k })}</p>
      <div className="game panel" style={{ marginTop: 28 }}>
        <div>
          <HexMap cells={r.cells} lit={picked} power={power} load={load} loadMax={900} emergency={emergency} border={r.meta.border_cells} capActive={t >= p.cap_slot} rainCells={t >= 45 && t < p.emergency_to ? p.emergency_cells : []} beams onSelect={toggle} />
          <p className="note" style={{ textAlign: 'center', margin: '6px 0 0' }}>{tr('game.tap')}</p>
        </div>
        <div>
          <div className="gamebar"><span className="mono">{phase === 'ready' ? tr('game.ready') : `${tr('ctl.slot')} ${sim.current.t} / ${p.rate.length}`}</span><div><i style={{ width: `${(sim.current.t / p.rate.length) * 100}%` }} /></div></div>
          {phase === 'ready' && <div className="gamestart">
            <div className="chips">{SPEEDS.map(([l, v]) => <button key={l} className={`chip ${speed === v ? 'on' : ''}`} onClick={() => setSpeed(v)}>{tr(`game.speed.${l}`)}</button>)}</div>
            <button className="cue" onClick={start}>{tr('game.start')}</button>
          </div>}
          {phase === 'play' && <>
            {event && <div key={event.id} className="toast" style={{ margin: '12px 0' }} lang="en" dir="ltr">{event.description.replace('HYPOTHETICAL operating constraint (not a real law):', 'New limit:')}</div>}
            <div className="vs"><span /><b>{tr('game.you')}</b><b>{tr('game.ai_so_far')}</b></div>
            {[[tr('game.late'), you.late, aiNow.late, (v) => pct(v)], [tr('game.r_wait'), you.delay, aiNow.delay, (v) => `${v.toFixed(0)} ms`], [tr('game.em'), you.emergency, aiNow.emergency, (v) => pct(v, 0)]].map(([l, a, b, f]) => <div key={l} className="vs"><span>{l}</span><b className="mono">{f(a)}</b><b className="mono">{f(b)}</b></div>)}
            <button className="chip" style={{ marginTop: 12 }} onClick={() => setPhase('paused')}>{tr('ctl.pause')}</button>
          </>}
          {phase === 'paused' && <div className="gamestart"><button className="cue" onClick={() => setPhase('play')}>{tr('game.resume')}</button></div>}
          {phase === 'done' && <div className="result">
            <h3>{verdict}</h3>
            <table style={{ marginTop: 12 }}><thead><tr><th /><th className="n">{tr('game.you')}</th><th className="n">OrbitFlow</th></tr></thead><tbody>
              {rows.map(([l, a, b, f, low]) => { const win = low ? a < b : a > b; return <tr key={l}><td>{l}</td><td className="n" style={{ color: win ? 'var(--beam)' : undefined }}>{f(a)}</td><td className="n" style={{ color: win ? undefined : 'var(--beam)' }}>{f(b)}</td></tr>; })}
            </tbody></table>
            <p className="note">{tr('game.note', { ms: d.study_latency.critical_path_total.mean.toFixed(1) })}</p>
            <button className="cue" onClick={start}>{tr('game.again')}</button>
          </div>}
        </div>
      </div>
    </div></section>
  );
}
