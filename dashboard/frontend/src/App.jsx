import React, { useEffect, useMemo, useRef, useState } from 'react';
import Globe from './Globe.jsx';
import { COLORS, DotCI, HexMap, LineChart, reducedMotion } from './viz.jsx';

const CHAPTERS = [
  ['top', 'The problem'], ['chase', 'Three ways to choose'], ['foresee', 'Seeing demand coming'], ['loop', 'How it decides'],
  ['mission', 'A flood, second by second'], ['evidence', 'Does it work?'], ['lab', 'Try it yourself'], ['knowledge', 'The rulebook'], ['ledger', 'How we know'],
];
const pct = (v, d = 1) => `${(v * 100).toFixed(d)}%`;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

function More({ label = 'See the technical details', children }) {
  return <details className="more"><summary>{label}</summary><div className="more-body">{children}</div></details>;
}

function Rail() {
  const [on, setOn] = useState('top');
  useEffect(() => {
    const io = new IntersectionObserver((es) => es.forEach((e) => e.isIntersecting && setOn(e.target.id)), { rootMargin: '-45% 0px -50% 0px' });
    CHAPTERS.forEach(([id]) => { const el = document.getElementById(id); if (el) io.observe(el); });
    return () => io.disconnect();
  }, []);
  return <nav className="rail" aria-label="Chapters">{CHAPTERS.map(([id, label], i) => <a key={id} href={`#${id}`} className={on === id ? 'on' : ''} aria-label={label}>{i}<span>{label}</span></a>)}</nav>;
}

function useClock(T, { speed = 110, start = 0, auto = false } = {}) {
  const [t, setT] = useState(start);
  const [playing, setPlaying] = useState(auto && !reducedMotion());
  useEffect(() => {
    if (!playing) return undefined;
    const id = setInterval(() => setT((v) => (v + 1) % T), speed);
    return () => clearInterval(id);
  }, [playing, T, speed]);
  return { t, setT, playing, setPlaying };
}

function Hero({ d }) {
  const r = d.flood_replay;
  const real = d.kpi_table.scenarios.real_trace;
  return (
    <header className="hero" id="top">
      <Globe cells={r.cells} lit={r.runs.OrbitFlow.series.lit} />
      <div className="copy">
        <p className="kicker">OrbitFlow · LEO beam hopping</p>
        <h1>One satellite. Nineteen cells. Four beams. Ten milliseconds to choose.</h1>
        <p className="lede">A satellite can only serve a few areas at a time. In a disaster, the people who need a connection most compete with everyone else. OrbitFlow learns where to point the beams, sees demand coming, and checks every decision against safety rules before it happens.</p>
        <div className="stats">
          <div className="stat"><b>{pct(real['Reactive greedy'].rt_sla_violation.mean)} → {pct(real.BRIDGE.rt_sla_violation.mean)}</b><span>late deliveries of time-critical data, compared with a simple scheduler, on a recorded pass it never trained on</span></div>
          <div className="stat"><b>{r.latency.bridge_ms.toFixed(1)} ms</b><span>to make a decision on an ordinary CPU, with {r.meta.slot_ms} ms available</span></div>
          <div className="stat"><b>{d.flood_mc.controllers['BRIDGE alone'].cap_violation_slots.mean.toFixed(0)} → {d.flood_mc.controllers.OrbitFlow.cap_violation_slots.mean.toFixed(0)}</b><span>rule breaches in a test scenario, without and with the safety agents</span></div>
        </div>
        <a className="cue" href="#chase">See how it works ↓</a>
      </div>
    </header>
  );
}

function Scrub({ t, setT, T, playing, setPlaying, label }) {
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
      <button className="play" onClick={() => setPlaying(!playing)} aria-label={playing ? 'Pause' : 'Play'}>{playing ? '❚❚' : '▶'}</button>
      <input type="range" min="0" max={T - 1} value={t} onChange={(e) => { setPlaying(false); setT(+e.target.value); }} aria-label="Slot" />
      <span className="mono" style={{ whiteSpace: 'nowrap', fontSize: 13 }}>{label}</span>
    </div>
  );
}

function Chase({ d }) {
  const r = d.flood_replay;
  const clock = useClock(r.meta.T, { speed: 140, start: 30, auto: true });
  const names = ['Static round-robin', 'Reactive greedy', 'BRIDGE alone'];
  const { t } = clock;
  const qt = (n) => r.runs[n].series.q_rt[t].map((q, i) => q + r.runs[n].series.q_nrt[t][i]);
  const real = d.kpi_table.scenarios.real_trace;
  return (
    <section className="ch" id="chase"><div className="wrap">
      <p className="kicker">Chapter 1 · Three ways to choose</p>
      <h2>A fixed rotation drowns the busy cells. A greedy one forgets the quiet ones.</h2>
      <p className="lede">Each hexagon is an area on the ground. Glowing ones have a beam right now. Orange means people there are waiting for data. Same demand, three different decision-makers.</p>
      <div className="panel" style={{ marginTop: 28 }}>
        <Scrub {...clock} T={r.meta.T} label={`slot ${String(t).padStart(2, '0')} · ${t * r.meta.slot_ms} ms`} />
        <div className="grid g3" style={{ marginTop: 16 }}>
          {names.map((n) => (
            <div key={n}>
              <HexMap compact cells={r.cells} title={n} lit={r.runs[n].series.lit[t]} power={r.runs[n].series.power[t]} load={qt(n)} loadMax={900} />
              <p className="mono" style={{ fontSize: 13, margin: '6px 0 0' }}>backlog {qt(n).reduce((a, b) => a + b, 0).toFixed(0)} kb · {r.runs[n].series.throughput[t].toFixed(0)} Mbps</p>
            </div>
          ))}
        </div>
      </div>
      <p className="insight">Delay alone flatters the greedy scheduler. On the real pass it matches BRIDGE on throughput, yet {pct(real['Reactive greedy'].rt_sla_violation.mean)} of cell-slots miss the real-time budget, because cold cells wait while it chases hotspots. BRIDGE keeps that to {pct(real.BRIDGE.rt_sla_violation.mean)} by giving up beam stability: {real.BRIDGE.beam_switches_per_slot.mean.toFixed(1)} switches per slot against {real['Reactive greedy'].beam_switches_per_slot.mean.toFixed(1)}.</p>
    </div></section>
  );
}

function Foresee({ d }) {
  const r = d.flood_replay; const ec = r.meta.event_cell;
  const lo = 10; const hi = 40;
  const dem = r.demand.slice(lo, hi).map((x) => x[ec]);
  const fc = r.forecast_h2.slice(lo, hi).map((x) => x[ec]);
  const sc = d.predictor_metrics.scenarios;
  const order = [['event_surge', 'Surge with a ramp'], ['mixed', 'Surge plus steady hotspot'], ['bursty', 'Random bursts'], ['block', 'Abrupt block switches'], ['real_trace', 'Real pass (abrupt)']];
  return (
    <section className="ch" id="foresee"><div className="wrap">
      <p className="kicker">Chapter 2 · Seeing demand coming</p>
      <h2>Forecasting buys time only when demand gives a warning.</h2>
      <p className="lede">When demand builds up gradually, OrbitFlow can see it coming and act early. When it jumps from nothing, no forecast can help, and we show that too.</p>
      <div className="grid g2">
        <div className="panel">
          <h4>The flood ramp, cell {ec}</h4><p className="sub">The forecast shown at each slot is its estimate for two slots later, made from lagged telemetry.</p>
          <LineChart height={280} x0={lo} xLabel="slot" yLabel="Mbps" series={[{ name: 'Actual demand', color: 'var(--ink)', values: dem }, { name: 'Forecast', color: 'var(--beam)', values: fc, dash: '5 3' }]} marks={[{ x: 28, label: 'emergency declared', color: 'var(--critical)' }]} />
        </div>
        <div className="panel">
          <h4>Error reduction at demand jumps, against repeat-last</h4><p className="sub">Held-out test episodes, MAE on targets more than 5 Mbps from the last observation.</p>
          <DotCI unit="reduction" format={(v) => pct(v, 0)} rows={order.map(([k, name]) => { const v = sc[k].gru_jump_skill; return { name, mean: v, lo: v, hi: v, n: sc[k].persistence.n_jump, color: v > 0.2 ? 'var(--orbit)' : 'var(--static)' }; })} />
          <More><p className="note">The forecaster is a small GRU neural network that predicts three 10 ms slots ahead from delayed measurements. Over all slots, including calm ones, it is no better than repeating the last value, and worse on bursty and block traffic. Its value is concentrated at ramps. A gradient-boosted baseline was also tested and lost on most scenarios.</p></More>
        </div>
      </div>
      <p className="insight">A forecaster cannot see a hotspot that appears from nothing. It cut surge error by {pct(sc.event_surge.gru_jump_skill, 0)}, and by only {pct(sc.real_trace.gru_jump_skill, 0)} on the real pass.</p>
    </div></section>
  );
}

const PIPE = [
  ['Observe', 'digital_twin', 'Lagged telemetry', 'Demand and channel state arrive one slot old. Geometry and SSB/SIB timing are known exactly from ephemeris and configuration.', 'digital_twin/environment.py'],
  ['Predict', 'GRU', '3 slots ahead', 'A residual GRU forecasts each cell’s demand. A leak test proves a forecast never changes when future demand is corrupted.', 'traffic/forecaster.py · tests/test_forecast_leak.py'],
  ['Decide', 'BRIDGE', 'PPO policy', 'The same small network scores every cell. Gumbel-Top-K samples 4 beams with an exact Plackett-Luce probability, and a Dirichlet splits the power.', 'bridge/policy.py · bridge/train_ppo.py'],
  ['Deliberate', '4 agents', 'Different knowledge', 'Network, Policy and Safety each see only their own events, and the Supervisor resolves conflicts. These agents are deterministic code, with no LLM in the loop.', 'agents/supervisor.py · scenarios/engine.py'],
  ['Retrieve', 'Hybrid RAG', 'BM25 + TF-IDF', 'Rules look for evidence in the knowledge base with reciprocal rank fusion. A quote that is not verbatim in its source is dropped.', 'rag/retriever.py · agents/policy_rules.yaml'],
  ['Guard', 'BamGuard', 'Hard limits', 'Beam count, power budget, floor, signalling deadlines and caps are enforced last. Raw model output never reaches the twin.', 'bam/validator.py'],
  ['Audit', 'JSONL', 'Every slot', 'Each slot records what was proposed, what ran, the rule applied and its sources. Conflicts go to a human review queue.', 'audit/ · results/audit/demo.jsonl'],
];

function Loop({ d }) {
  const [i, setI] = useState(2);
  const [title, tech, tag, text, files] = PIPE[i];
  return (
    <section className="ch" id="loop"><div className="wrap">
      <p className="kicker">Chapter 3 · How it decides</p>
      <h2>The AI suggests. Safety checks have the last word.</h2>
      <p className="lede">This happens 100 times a second. Select a step to see what it does.</p>
      <div className="pipe" style={{ marginTop: 28 }} role="tablist">
        {PIPE.map((p, k) => <button key={p[0]} role="tab" aria-selected={i === k} className={i === k ? 'on' : ''} onClick={() => setI(k)}><small>{String(k + 1).padStart(2, '0')}</small><b>{p[0]}</b><small>{p[1]}</small></button>)}
      </div>
      <div className="panel" style={{ marginTop: 8 }}>
        <h3>{title} <span className="tag" style={{ marginLeft: 6, verticalAlign: 3 }}>{tag}</span></h3>
        <p style={{ margin: '8px 0', maxWidth: '60em' }}>{text}</p>
        <More label="Where this lives in the code"><code>{files}</code></More>
      </div>
      <p className="note" style={{ marginTop: 12 }}>Measured on this CPU: forecast {d.flood_replay.latency.forecast_ms.toFixed(2)} ms per slot, BRIDGE {d.flood_replay.latency.bridge_ms.toFixed(2)} ms per decision, {d.bridge_training.n_params.toLocaleString()} parameters. Agent and guard time are not included.</p>
    </div></section>
  );
}

const AGENTS = [
  ['network', 'Network', 'Telemetry, forecast. Maximises KPIs with BRIDGE.'],
  ['policy', 'Policy', 'Notices, knowledge base. Checks legality.'],
  ['safety', 'Safety', 'Emergency declarations, KPIs. Protects priority traffic.'],
  ['supervisor', 'Supervisor', 'Sees all. Guard > law > safety > optimisation.'],
];
const STAGES = [[0, 15, 'T0 normal'], [15, 28, 'T1 ramp'], [28, 45, 'T3 emergency', 'hotstage'], [45, 50, 'T4 fade', 'hotstage'], [50, 61, 'T5 cap', 'capstage'], [61, 77, 'T6 recovery'], [77, 100, 'T7 normal']];

function Timeline({ t, setT, setPlaying, T }) {
  const ref = useRef(null);
  const seek = (e) => { const r = ref.current.getBoundingClientRect(); setPlaying(false); setT(clamp(Math.round(((e.clientX - r.left) / r.width) * (T - 1)), 0, T - 1)); };
  return (
    <div className="timeline" ref={ref} onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); seek(e); }} onPointerMove={(e) => e.buttons && seek(e)}
      role="slider" tabIndex={0} aria-label="Scenario slot" aria-valuemin={0} aria-valuemax={T - 1} aria-valuenow={t}
      onKeyDown={(e) => { if (e.key === 'ArrowRight') { setPlaying(false); setT(Math.min(T - 1, t + 1)); } if (e.key === 'ArrowLeft') { setPlaying(false); setT(Math.max(0, t - 1)); } }}>
      {STAGES.map(([a, b, l, c]) => <div key={l} className={`stage ${c || ''}`} style={{ left: `${a}%`, width: `${b - a}%` }}>{l}</div>)}
      <div className="track" />
      <div className="head" style={{ left: `${(t / (T - 1)) * 100}%` }}><b>{t}</b></div>
    </div>
  );
}

function Mission({ d }) {
  const r = d.flood_replay; const T = r.meta.T;
  const firstAlert = r.audit.find((a) => a.trace.some((s) => s.action === 'forecast_alert'))?.slot;
  const clock = useClock(T, { speed: 240, start: 0 });
  const { t, setT, playing, setPlaying } = clock;
  const [cell, setCell] = useState(r.meta.event_cell);
  const [ctrl, setCtrl] = useState('OrbitFlow');
  const run = r.runs[ctrl].series;
  const load = run.q_rt[t].map((q, i) => q + run.q_nrt[t][i]);
  const emergency = t >= 28 && t < 61 ? r.meta.emergency_cells : [];
  const capActive = t >= 50;
  const rec = r.audit[t];
  const seen = (who) => r.events.filter((e) => e.slot <= t && (who === 'supervisor' || e.audience.includes(who) || e.audience.includes('all')));
  const hidden = (who) => r.events.filter((e) => e.slot <= t && !e.audience.includes('all') && !e.audience.includes(who)).length;
  const steps = (who) => rec.trace.filter((s) => s.agent === who);
  const cap = r.meta.border_cap_w;
  const failCount = r.audit.filter((a) => a.policy_findings.some((f) => f.status === 'FAIL')).length;
  const proposed = rec.proposed; const final = rec.final;
  const beamRows = [...new Set([...proposed.beams, ...final.beams])];
  const moments = [[0, 'Calm'], [firstAlert ?? 25, 'Forecast alert'], [28, 'Emergency declared'], [45, 'Rain fade'], [50, 'Cap arrives'], [61, 'Recovery ends priority'], [63, 'Backlog spike']];
  const cites = rec.trace.flatMap((s) => s.citations);
  const q = (n, c) => r.runs[n].series.q_rt.map((row, i) => row[c] + r.runs[n].series.q_nrt[i][c]);
  return (
    <section className="ch" id="mission" style={{ background: '#0d1115' }}><div className="wrap">
      <p className="kicker">Chapter 4 · A flood, second by second</p>
      <h2>One second of a flood, as each agent saw it.</h2>
      <p className="lede">Press play or jump to a moment. Four software agents each know only part of the picture, like departments in a control room. This is a test scenario built on a recorded satellite pass.</p>
      <div className="panel" style={{ marginTop: 28 }}>
        <div className="chips" style={{ marginBottom: 12 }}>
          {moments.map(([s, l]) => <button key={l} className={`chip ${t === s ? 'on' : ''}`} onClick={() => { setPlaying(false); setT(s); }}>{l} <span className="mono" style={{ opacity: .65 }}>{s}</span></button>)}
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
          <button className="play" onClick={() => setPlaying(!playing)} aria-label={playing ? 'Pause' : 'Play'}>{playing ? '❚❚' : '▶'}</button>
          <Timeline t={t} setT={setT} setPlaying={setPlaying} T={T} />
        </div>
      </div>
      <div className="grid g-mission" style={{ marginTop: 12 }}>
        <div className="panel">
          <div className="chips" style={{ marginBottom: 10 }}>
            {['OrbitFlow', 'BRIDGE alone', 'Reactive greedy'].map((n) => <button key={n} className={`chip ${ctrl === n ? 'on' : ''}`} onClick={() => setCtrl(n)}>{n}</button>)}
          </div>
          <HexMap cells={r.cells} lit={run.lit[t]} power={run.power[t]} load={load} loadMax={900} emergency={emergency} border={r.meta.border_cells} capActive={capActive} selected={cell} onSelect={setCell} />
          <p className="note" style={{ margin: '8px 0 0' }}><span style={{ color: 'var(--critical)' }}>▲</span> emergency · <span style={{ color: 'var(--warning)' }}>yellow outline</span> border cell, solid once capped · warmer = more backlog · select a cell to chart it</p>
        </div>
        <div>
          <div className="grid g2" style={{ marginTop: 0, gap: 8 }}>
            {AGENTS.map(([id, name, role]) => {
              const here = steps(id); const ev = seen(id).slice(-2); const blind = hidden(id);
              return (
                <div key={id} className={`agent ${here.length ? 'active' : ''}`}>
                  <h5>{name}</h5><div className="role">{role}</div>
                  {ev.map((e) => <div key={e.id} className="ev"><span className="mono" style={{ color: 'var(--ink-3)' }}>{e.slot}</span> {e.description}</div>)}
                  {here.slice(0, 3).map((s, i) => (
                    <p key={i}>{s.output?.status && <span className={`tag ${s.output.status === 'FAIL' ? 'critical' : s.output.status === 'WARN' || s.output.status === 'UNVERIFIED' ? 'warning' : 'good'}`} style={{ marginRight: 5 }}>{s.output.status}</span>}{s.rationale}</p>
                  ))}
                  {blind > 0 && id !== 'supervisor' && <div className="blind">Not told about {blind} event{blind > 1 ? 's' : ''} already released.</div>}
                </div>
              );
            })}
          </div>
          <More label="See the audit record for this moment"><div className="panel">
            <h4>Audit record, slot {t} <span className={`tag ${rec.decision === 'REPAIRED' ? 'warning' : 'good'}`} style={{ marginLeft: 6 }}>{rec.decision}</span></h4>
            <div className="scroll"><table style={{ marginTop: 6 }}><thead><tr><th>Cell</th><th className="n">Proposed W</th><th className="n">Executed W</th><th>Change</th></tr></thead><tbody>
              {beamRows.map((c) => { const a = proposed.power_w[c]; const b = final.power_w[c]; return (
                <tr key={c}><td className="mono">{c}{r.meta.border_cells.includes(c) ? ' (border)' : ''}</td><td className="n">{a?.toFixed(1) ?? 'dark'}</td><td className="n">{b?.toFixed(1) ?? 'dark'}</td><td>{a == null ? 'forced on' : b == null ? 'dropped' : Math.abs(a - b) > 0.05 ? `${(b - a).toFixed(1)} W` : ''}</td></tr>); })}
            </tbody></table></div>
            {cites.slice(0, 1).map((c) => <div key={c.chunk_id} style={{ marginTop: 8 }}><div className="quote">“{c.quote}”</div><div className="note">{c.title}, section {c.section}. Verified verbatim against the source.</div></div>)}
            {rec.trace.some((s) => s.action === 'R5_emergency_exemption') && <p className="note" style={{ margin: '8px 0 0' }}><span className="tag warning">UNVERIFIED</span> The search for an emergency exemption from a power limit found nothing in the corpus.</p>}
          </div></More>
        </div>
      </div>
      <div className="grid g2" style={{ marginTop: 12 }}>
        <div className="panel"><h4>Backlog at cell {cell}</h4><p className="sub">Data waiting, by controller. Hover to read a slot.</p>
          <LineChart height={220} xLabel="slot" yLabel="kb" cursor={t} format={(v) => v.toFixed(0)} marks={[{ x: 28, to: 61, label: 'em', color: 'var(--critical)' }]} series={['OrbitFlow', 'BRIDGE alone', 'Reactive greedy'].map((n) => ({ name: n, color: COLORS[n], values: q(n, cell) }))} /></div>
        <div className="panel"><h4>Power on cell {cell}</h4><p className="sub">Watts per slot. The dashed line is the {cap} W cap on border cells from slot 50.</p>
          <LineChart height={220} xLabel="slot" yLabel="W" cursor={t} format={(v) => v.toFixed(1)} marks={[{ x: 50, label: `${cap} W cap`, color: 'var(--warning)' }]} series={['OrbitFlow', 'BRIDGE alone'].map((n) => ({ name: n, color: COLORS[n], values: r.runs[n].series.power.map((p) => p[cell]) }))} /></div>
      </div>
      <p className="insight">The clash we scripted was BRIDGE demanding far more than the cap. What happened was subtler. BRIDGE spreads its power, so the Policy agent repaired {failCount} slots of modest overshoot, usually not on an emergency cell, and at these settings nothing was sent for human review. The replay also exposes a flaw: priority ends at slot 61 while cell 13 is still busy, so its backlog spikes.</p>
    </div></section>
  );
}

const KPI_OPTS = [
  ['rt_sla_violation', 'RT deadline misses', '% of cell-slots', (v) => pct(v), true],
  ['mean_delay_ms', 'Mean delay', 'ms', (v) => v.toFixed(1), true],
  ['throughput_mbps', 'Throughput', 'Mbps', (v) => v.toFixed(1), false],
  ['packet_loss', 'Packet loss', '%', (v) => pct(v), true],
  ['guard_violation_slots', 'Proposals failing the guard', 'slots', (v) => v.toFixed(1), true],
  ['beam_switches_per_slot', 'Beam switches', 'per slot', (v) => v.toFixed(2), true],
];
const SCEN = [['real_trace', 'Real pass'], ['block', 'Block'], ['event_surge', 'Surge'], ['mixed', 'Mixed'], ['bursty', 'Bursty'], ['normal', 'Normal']];

function Evidence({ d }) {
  const [sc, setSc] = useState('real_trace');
  const [kpi, setKpi] = useState('rt_sla_violation');
  const row = d.kpi_table.scenarios[sc];
  const opt = KPI_OPTS.find((o) => o[0] === kpi);
  const names = Object.keys(row);
  const rows = names.map((n) => ({ name: n, color: COLORS[n] || '#7d8791', ...row[n][kpi] }));
  const curve = d.bridge_training.ppo.filter((p) => p.val_reward != null);
  const curve2 = d.bridge_training_noforecast.ppo.filter((p) => p.val_reward != null);
  const mc = d.flood_mc.controllers;
  const sig = (n, k) => row[n]?.vs_reactive?.[k];
  const lossRows = useMemo(() => {
    const out = [];
    Object.entries(d.kpi_table.scenarios).forEach(([s, r]) => {
      if (s === 'real_trace') return;
      KPI_OPTS.slice(0, 2).forEach(([k, label]) => {
        const v = r.BRIDGE.vs_reactive?.[k];
        const nf = r['BRIDGE no-forecast'][k]; const b = r.BRIDGE[k];
        if (b.mean > nf.mean * 1.02 + 1e-4) out.push(`${s}: BRIDGE has worse ${label[0].toLowerCase() === 'r' ? label : label.toLowerCase()} than its no-forecast control (${opt && k === 'mean_delay_ms' ? `${b.mean.toFixed(1)} vs ${nf.mean.toFixed(1)} ms` : `${pct(b.mean)} vs ${pct(nf.mean)}`})`);
        if (v && v.losses > v.wins && v.p < 0.05) out.push(`${s}: BRIDGE loses to Reactive on ${label.toLowerCase()} (${v.wins} wins, ${v.losses} losses, p=${v.p.toExponential(1)})`);
      });
    });
    return out;
  }, [d, opt]);
  return (
    <section className="ch" id="evidence"><div className="wrap">
      <p className="kicker">Chapter 5 · Does it work?</p>
      <h2>We tested it on situations it had never seen, including where it loses.</h2>
      <p className="lede">{d.kpi_table.meta.test_episodes_per_kind} held-out episodes per synthetic scenario. Dots are means, bars are 95% bootstrap intervals. The real pass is a single episode, so it has no interval.</p>
      <div className="panel" style={{ marginTop: 28 }}>
        <div className="chips" style={{ marginBottom: 8 }}>{SCEN.map(([k, l]) => <button key={k} className={`chip ${sc === k ? 'on' : ''}`} onClick={() => setSc(k)}>{l}</button>)}</div>
        <div className="chips" style={{ marginBottom: 16 }}>{KPI_OPTS.map(([k, l]) => <button key={k} className={`chip ${kpi === k ? 'on' : ''}`} onClick={() => setKpi(k)}>{l}</button>)}</div>
        <h4>{opt[1]} <span style={{ fontWeight: 400, color: 'var(--ink-3)' }}>({opt[2]}, {opt[4] ? 'lower' : 'higher'} is better)</span></h4>
        <div style={{ marginTop: 10 }}><DotCI rows={rows} format={opt[3]} unit={opt[2]} /></div>
        {sig('BRIDGE', kpi) && <p className="note" style={{ margin: '10px 0 0' }}>BRIDGE vs Reactive, paired by episode: {sig('BRIDGE', kpi).wins} wins, {sig('BRIDGE', kpi).losses} losses, {sig('BRIDGE', kpi).ties} ties, exact sign test p = {sig('BRIDGE', kpi).p < 0.001 ? sig('BRIDGE', kpi).p.toExponential(1) : sig('BRIDGE', kpi).p.toFixed(3)}.</p>}
      </div>
      <div className="grid g2" style={{ marginTop: 12 }}>
        <div className="panel"><h4>Learning curve</h4><p className="sub">Deterministic validation reward per episode. Iteration 0 is the behaviour-cloned start, so PPO’s gain over the hand-written teacher is small but real.</p>
          <LineChart height={240} x0={0} yMin={Math.floor(Math.min(...curve.map((c) => c.val_reward), ...curve2.map((c) => c.val_reward)) - 1)} xLabel="PPO iteration" yLabel="reward (axis does not start at 0)" format={(v) => v.toFixed(1)} series={[{ name: 'With forecast', color: 'var(--bridge)', x: curve.map((c) => c.iter), values: curve.map((c) => c.val_reward) }, { name: 'No forecast', color: 'var(--static)', values: curve2.map((c) => c.val_reward) }]} />
        </div>
        <div className="panel"><h4>What the agents cost and buy</h4><p className="sub">Flood relief over {d.flood_mc.seeds} demand-noise seeds. Fade, cap and timing are fixed.</p>
          <div className="scroll"><table><thead><tr><th>Controller</th><th className="n">Cap breach slots</th><th className="n">Emergency served</th><th className="n">Mean delay ms</th><th className="n">RT misses</th></tr></thead><tbody>
            {Object.entries(mc).map(([n, m]) => <tr key={n} className={n === 'OrbitFlow' ? 'best' : ''}><td>{n}</td><td className="n">{m.cap_violation_slots.mean.toFixed(1)}</td><td className="n">{pct(m.emergency_served_ratio.mean)}</td><td className="n">{m.mean_delay_ms.mean.toFixed(1)}</td><td className="n">{pct(m.rt_sla_violation.mean)}</td></tr>)}
          </tbody></table></div>
          <p className="insight" style={{ fontSize: 17 }}>Compliance is not free. The agents remove every breach and protect the emergency cells, but delay rises from {mc['BRIDGE alone'].mean_delay_ms.mean.toFixed(0)} to {mc.OrbitFlow.mean_delay_ms.mean.toFixed(0)} ms and RT misses from {pct(mc['BRIDGE alone'].rt_sla_violation.mean)} to {pct(mc.OrbitFlow.rt_sla_violation.mean)} overall. The likely cause: forcing two beams onto emergency cells leaves two for the other seventeen.</p>
          <p className="note">Served can exceed 100%: the twin starts with a backlog, which is cleared alongside new arrivals.</p>
        </div>
      </div>
      <div className="panel" style={{ marginTop: 12 }}>
        <h4>Where BRIDGE loses</h4>
        <ul style={{ margin: '8px 0 0', paddingLeft: 18, fontSize: 14 }}>{lossRows.map((l) => <li key={l}>{l}</li>)}<li>On normal load every controller but the fixed rotation is effectively tied. There is nothing to optimise.</li><li>The forecast’s benefit is uneven. Its largest delay gain is on block traffic, where the forecaster itself adds almost nothing, so treat that gain as unexplained, not as proof that prediction works there.</li></ul>
      </div>
    </div></section>
  );
}

function Lab({ d }) {
  const g = d.whatif_grid;
  const [cap, setCap] = useState(22); const [fade, setFade] = useState(6);
  const [metric, setMetric] = useState('emergency_served_ratio');
  const at = (c, f) => g.cells.find((x) => x.cap === c && x.fade === f);
  const cur = at(cap, fade); const o = cur.OrbitFlow; const b = cur['BRIDGE alone'];
  const vals = g.cells.map((c) => c.OrbitFlow[metric] ?? 0);
  const lo = Math.min(...vals); const hi = Math.max(...vals);
  const cell = (c, f) => {
    const v = at(c, f).OrbitFlow[metric] ?? 0; const n = hi > lo ? (v - lo) / (hi - lo) : 0;
    const k = metric === 'emergency_served_ratio' ? n : 1 - n;     // brighter is always better
    return { bg: `rgb(${Math.round(24 + k * 15)},${Math.round(36 + k * 139)},${Math.round(38 + k * 101)})`, fg: k > 0.55 ? '#071210' : '#ece7dc', v };
  };
  const fmt = metric === 'emergency_served_ratio' ? (v) => `${(v * 100).toFixed(0)}` : (v) => v.toFixed(1);
  const sentence = () => {
    if (o.human_reviews) return `The supervisor referred this case to a human. ${o.reviews?.[0]?.reason || ''} Emergency cells received ${pct(o.emergency_served_ratio, 0)} of arrivals.`;
    if (o.emergency_served_ratio < 0.98) return `Emergency service drops to ${pct(o.emergency_served_ratio, 0)} without a sustained shortfall alarm: capacity dips intermittently. Fade is the cause; loosening the cap barely changes it.`;
    return `Emergency cells stay served at ${pct(o.emergency_served_ratio, 0)}. ${b.cap_violation_slots ? `Without agents, BRIDGE would breach this cap in ${b.cap_violation_slots} slots.` : 'This cap is loose enough that BRIDGE never reaches it.'}`;
  };
  return (
    <section className="ch" id="lab"><div className="wrap">
      <p className="kicker">Chapter 6 · Try it yourself</p>
      <h2>Tighten the law. Worsen the storm. See which one hurts.</h2>
      <p className="lede">Move the sliders. Each square is a complete simulation run, already computed, not an estimate.</p>
      <div className="grid g2">
        <div className="panel">
          <label style={{ display: 'block', marginBottom: 12 }}><span style={{ fontSize: 14 }}>Power limit near the border (hypothetical): <b className="mono">{cap === 100 ? 'none' : `${cap} W`}</b></span>
            <input type="range" min="0" max={g.caps.length - 1} value={g.caps.indexOf(cap)} onChange={(e) => setCap(g.caps[+e.target.value])} /></label>
          <label style={{ display: 'block', marginBottom: 16 }}><span style={{ fontSize: 14 }}>Rain fade: <b className="mono">{fade} dB</b></span>
            <input type="range" min="0" max={g.fades.length - 1} value={g.fades.indexOf(fade)} onChange={(e) => setFade(g.fades[+e.target.value])} /></label>
          <div className="chips" style={{ marginBottom: 10 }}>
            <button className={`chip ${metric === 'emergency_served_ratio' ? 'on' : ''}`} onClick={() => setMetric('emergency_served_ratio')}>Emergency served %</button>
            <button className={`chip ${metric === 'mean_delay_ms' ? 'on' : ''}`} onClick={() => setMetric('mean_delay_ms')}>Mean delay ms</button>
          </div>
          <div className="heat" style={{ gridTemplateColumns: `52px repeat(${g.fades.length}, 1fr)` }}>
            <div className="ax">cap \ fade</div>{g.fades.map((f) => <div key={f} className="ax">{f} dB</div>)}
            {g.caps.map((c) => <React.Fragment key={c}><div className="ax">{c === 100 ? 'none' : `${c} W`}</div>
              {g.fades.map((f) => { const s = cell(c, f); return <button key={f} className={c === cap && f === fade ? 'on' : ''} style={{ background: s.bg, color: s.fg }} onClick={() => { setCap(c); setFade(f); }} aria-label={`Cap ${c} watts, fade ${f} dB: ${fmt(s.v)}`}>{fmt(s.v)}{at(c, f).OrbitFlow.human_reviews > 0 ? ' ⚑' : ''}</button>; })}
            </React.Fragment>)}
          </div>
          <p className="note" style={{ margin: '8px 0 0' }}>Brighter is better. ⚑ marks a run with a human-review referral.</p>
        </div>
        <div className="panel">
          <h4>This run</h4>
          <p style={{ font: '400 20px/1.35 var(--serif)', margin: '6px 0 14px', minHeight: 82 }}>{sentence()}</p>
          <LineChart height={210} xLabel="slot" yLabel="kb" format={(v) => v.toFixed(0)} marks={[{ x: 45, to: 61, label: 'fade', color: 'var(--critical)' }]} series={[{ name: 'OrbitFlow', color: COLORS.OrbitFlow, values: o.q_event }, { name: 'BRIDGE alone', color: COLORS['BRIDGE alone'], values: b.q_event }]} />
          <p className="note" style={{ margin: '6px 0 0' }}>Backlog at the surge cell, cell {d.flood_replay.meta.event_cell}.</p>
          <div className="scroll"><table style={{ marginTop: 8 }}><thead><tr><th /><th className="n">Cap breach slots</th><th className="n">Emergency served</th><th className="n">Human reviews</th></tr></thead><tbody>
            <tr><td>OrbitFlow</td><td className="n">{o.cap_violation_slots}</td><td className="n">{pct(o.emergency_served_ratio)}</td><td className="n">{o.human_reviews}</td></tr>
            <tr><td>BRIDGE alone</td><td className="n">{b.cap_violation_slots}</td><td className="n">{pct(b.emergency_served_ratio)}</td><td className="n">{b.human_reviews}</td></tr>
          </tbody></table></div>
        </div>
      </div>
      <p className="insight">Read the grid by column and then by row. Emergency service falls with fade and barely moves with the cap, at least in this link budget. A flood plan should budget for rain before it argues over watts.</p>
    </div></section>
  );
}

function Quote({ c }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div className="quote">“{c.quote}”</div>
      <div className="note">{c.title}{c.issuer && !c.issuer.startsWith('not stated') ? ` · ${c.issuer}` : ''} · {c.section ? `${c.section} · ` : ''}p. {c.page} · <span className="tag good">verbatim verified</span></div>
    </div>
  );
}

function Knowledge({ d }) {
  const k = d.kb_report; const g = d.gaps; const t = k.totals;
  const [q, setQ] = useState(0);
  const [fac, setFac] = useState(3);
  const [show, setShow] = useState(false);
  const s = k.questions[q]; const m = k.readiness_mapping[fac];
  const ev = k.retrieval_eval.methods;
  return (
    <section className="ch" id="knowledge"><div className="wrap">
      <p className="kicker">Chapter 7 · The rulebook</p>
      <h2>It reads real policy documents, quotes them exactly, and admits when they don’t say.</h2>
      <p className="lede">The knowledge base is the ITU AI Readiness training repository at a pinned commit: {t.ingested} of {t.files} files, {t.pages.toLocaleString()} pages, {t.chunks.toLocaleString()} chunks. It covers AI policy, not spectrum law, so it can support how OrbitFlow is structured, but not the value of a power cap.</p>
      <div className="stats" style={{ marginTop: 24 }}>
        <div className="stat"><b>{t.evidence_eligible}</b><span>documents that can count as evidence; summaries and sample files cannot</span></div>
        <div className="stat"><b>{t.failed}</b><span>PDFs failed both parsers, and are reported rather than replaced</span></div>
        <div className="stat"><b>{k.citation_verification.checked - k.citation_verification.failed}/{k.citation_verification.checked}</b><span>citations found verbatim in their source chunk</span></div>
        <div className="stat"><b>{pct(ev.bm25.section_recall_at_5, 0)}</b><span>section recall@5 with BM25 on {ev.bm25.n} developer-written queries</span></div>
      </div>
      <div className="grid g2">
        <div className="panel"><h4>Ask the corpus</h4><p className="sub">Recorded answers. These are extractive: quotations only, with no generated text.</p>
          <div className="chips" style={{ margin: '8px 0 12px' }}>{k.questions.map((x, i) => <button key={x.query} className={`chip ${q === i ? 'on' : ''}`} onClick={() => setQ(i)}>{x.query}</button>)}</div>
          {s.supported ? s.quotes.map((c) => <Quote key={c.chunk_id} c={c} />) : <p className="insight" style={{ borderColor: 'var(--warning)', fontSize: 18 }}>{s.statement}</p>}
        </div>
        <div className="panel"><h4>ITU AI Readiness factors</h4><p className="sub">The factor names and first quote are the framework’s. Interpretation and contribution are ours. This does not show that OrbitFlow establishes readiness or compliance.</p>
          <div className="chips" style={{ margin: '8px 0 12px' }}>{k.readiness_mapping.map((x, i) => <button key={x.factor} className={`chip ${fac === i ? 'on' : ''}`} onClick={() => setFac(i)}>{x.factor}</button>)}</div>
          <p className="note" style={{ margin: 0 }}>Stated in the source</p><Quote c={m.stated_in_framework} /><Quote c={m.supporting_evidence} />
          <p style={{ fontSize: 14, margin: '6px 0' }}><b>Our interpretation:</b> {m.interpretation}</p>
          <p style={{ fontSize: 14, margin: '6px 0' }}><b>OrbitFlow’s contribution:</b> {m.orbitflow_contribution}</p>
          <span className="tag">mapping confidence: {m.confidence}</span>
        </div>
      </div>
      <More label="See rule evidence, gaps, retrieval tests and all documents">
      <div className="grid g2" style={{ marginTop: 12 }}>
        <div className="panel"><h4>Rule evidence</h4><p className="sub">Rules stay enforced as operating constraints when the corpus is silent.</p>
          <div className="scroll"><table><thead><tr><th>Rule</th><th>Evidence</th></tr></thead><tbody>
            {k.rules.map((r) => <tr key={r.rule_id}><td style={{ whiteSpace: 'normal' }}>{r.title}</td><td><span className={`tag ${r.evidence_status === 'FOUND' ? 'good' : 'warning'}`}>{r.evidence_status === 'FOUND' ? 'found' : 'none found'}</span></td></tr>)}
          </tbody></table></div>
        </div>
        <div className="panel"><h4>Gap candidates <span className="tag warning" style={{ marginLeft: 4 }}>not human-verified</span></h4><p className="sub">{g.header}</p>
          {g.candidates.map((c) => <p key={c.id} style={{ fontSize: 14, margin: '8px 0' }}><span className="mono" style={{ color: 'var(--ink-3)' }}>{c.id}</span> <b>{c.title}.</b> {c.consequence}</p>)}
        </div>
      </div>
      <div className="panel" style={{ marginTop: 12 }}>
        <h4>Retrieval methods compared</h4><p className="sub">{k.retrieval_eval.note}</p>
        <div className="scroll"><table><thead><tr><th>Method</th><th className="n">Section recall@5</th><th className="n">Doc recall@5</th><th className="n">Precision@5</th><th className="n">MRR</th></tr></thead><tbody>
          {Object.entries(ev).map(([n, r]) => <tr key={n} className={n === 'bm25' ? 'best' : ''}><td>{n}{n === 'bm25' ? ' (default)' : ''}</td><td className="n">{pct(r.section_recall_at_5, 0)}</td><td className="n">{pct(r.doc_recall_at_5, 0)}</td><td className="n">{pct(r.precision_at_5, 0)}</td><td className="n">{r.mrr.toFixed(2)}</td></tr>)}
        </tbody></table></div>
      </div>
      <div className="panel" style={{ marginTop: 12 }}>
        <button className="chip" onClick={() => setShow(!show)}>{show ? 'Hide' : 'Show'} all {t.files} documents</button>
        <p className="note" style={{ margin: '8px 0 0' }}>Source: {k.source.repository} at {k.source.commit.slice(0, 10)}. {k.source.licence}. Issuer and year are inferred where marked in the manifest.</p>
        {show && <div className="scroll" style={{ marginTop: 8 }}><table><thead><tr><th>Document</th><th>Issuer</th><th>Status</th><th className="n">Pages</th><th className="n">Chunks</th></tr></thead><tbody>
          {k.documents.map((x) => <tr key={x.doc_id}><td style={{ whiteSpace: 'normal' }}>{x.title}</td><td style={{ color: 'var(--ink-2)' }}>{x.issuer}</td><td><span className={`tag ${x.chunks === 0 ? 'critical' : x.evidence_eligible ? 'good' : 'warning'}`}>{x.chunks === 0 ? 'failed' : x.evidence_eligible ? 'evidence' : x.role === 'primary' ? 'duplicate' : 'not evidence'}</span></td><td className="n">{x.pages}</td><td className="n">{x.chunks}</td></tr>)}
        </tbody></table></div>}
      </div>
      </More>
    </div></section>
  );
}

function Ledger({ d }) {
  const rows = [
    ['From real data', 'The satellite’s path, signal conditions and timing come from the supplied offline NTN datasets. The rulebook is 65 real documents from the ITU AI Readiness repository.'],
    ['Measured by us', 'Every chart: all results are computed by running the software, with fixed seeds, and can be reproduced.'],
    ['Generated for testing', 'Training traffic is generated to match the dataset’s levels. The flood is a test scenario. The 22 W limit is a hypothetical constraint, not a real law.'],
    ['Awaiting engineering review', 'Antenna gain, bandwidth and interference values are provisional until reviewed by RF engineers.'],
    ['Not built', 'This is a simulation, not connected to a real satellite. The agents use fixed rules rather than an LLM, by design: time-critical safety decisions should be predictable.'],
  ];
  return (
    <section className="ch" id="ledger"><div className="wrap">
      <p className="kicker">Chapter 8 · How we know</p>
      <h2>Where every number comes from, and how to check it.</h2>
      <div className="panel" style={{ marginTop: 28 }}><table className="ledger"><tbody>{rows.map(([a, b]) => <tr key={a}><td>{a}</td><td>{b}</td></tr>)}</tbody></table></div>
      <div className="panel" style={{ marginTop: 12 }}><h4>Reproduce every number</h4>
        <pre style={{ margin: '8px 0 0', font: '13px/1.7 var(--mono)', color: 'var(--ink-2)', overflowX: 'auto' }}>{`pip install -r requirements.txt
python -m pytest -q tests                 # physics, guard, leakage, sampler and agent claims
python -m traffic.train_forecaster        # about 6 min on CPU
python -m bridge.train_ppo                # about 15 min; add --no-forecast for the control
python scripts/run_eval.py                # about 2 min; writes results/ and the web data`}</pre>
      </div>
    </div></section>
  );
}

export default function App({ d }) {
  return (
    <>
      <Rail />
      <main>
        <Hero d={d} /><Chase d={d} /><Foresee d={d} /><Loop d={d} /><Mission d={d} /><Evidence d={d} /><Lab d={d} /><Knowledge d={d} /><Ledger d={d} />
        <footer>OrbitFlow. Synthetic demand and simulated events are labelled throughout. Not an operational system.</footer>
      </main>
    </>
  );
}
