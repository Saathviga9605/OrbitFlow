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
  const real = d.multirun.conditions['pass:dynamic_ntn'].policies;
  return (
    <header className="hero" id="top">
      <Globe cells={r.cells} lit={r.runs.OrbitFlow.series.lit} />
      <div className="copy">
        <p className="kicker">OrbitFlow · LEO beam hopping</p>
        <h1>One satellite. Nineteen cells. Four beams. Ten milliseconds to choose.</h1>
        <p className="lede">A satellite can only serve a few areas at a time. In a disaster, the people who need a connection most compete with everyone else. OrbitFlow learns where to point the beams, sees demand coming, and checks every decision against safety rules before it happens.</p>
        <div className="stats">
          <div className="stat"><b>{pct(real['Reactive greedy'].rt_sla_violation.mean)} → {pct(real.BRIDGE.rt_sla_violation.mean)}</b><span>time-critical data arriving late, simple scheduler vs OrbitFlow, over {real.BRIDGE.rt_sla_violation.n} test runs of a recorded pass</span></div>
          <div className="stat"><b>{d.study_latency.critical_path_total.mean.toFixed(1)} ms</b><span>to decide and run every safety check on one CPU core, with {r.meta.slot_ms} ms available</span></div>
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
  const real = d.multirun.conditions['pass:dynamic_ntn'].policies;
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
      <p className="insight">The simple scheduler looks fast on average, but it forgets quiet areas: {pct(real['Reactive greedy'].rt_sla_violation.mean)} of time-critical data arrives late. OrbitFlow keeps that to {pct(real.BRIDGE.rt_sla_violation.mean)} at the same throughput. The price is more beam switching: {real.BRIDGE.beam_switches_per_slot.mean.toFixed(1)} switches per slot against {real['Reactive greedy'].beam_switches_per_slot.mean.toFixed(1)}.</p>
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
  ['Retrieve', 'RAG', 'BM25, precomputed', 'Rules look up evidence in real documents ahead of time, so reading never slows a decision. A quote that is not verbatim in its source is dropped.', 'rag/retriever.py · agents/policy_rules.yaml'],
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
      <p className="note" style={{ marginTop: 12 }}>Measured on one CPU core, {d.study_latency.critical_path_total.n} decisions: {d.study_latency.critical_path_total.mean.toFixed(2)} ms on average, {d.study_latency.critical_path_total.p99.toFixed(2)} ms at the 99th percentile. Policy and Safety agents take {(d.study_latency.stages.policy.mean + d.study_latency.stages.safety.mean).toFixed(2)} ms of that. The agents are fixed rules, with no LLM in the loop. This is Python on a desktop, not a real-time guarantee.</p>
    </div></section>
  );
}

const AGENTS = [
  ['network', 'Network', 'Telemetry, forecast. Maximises KPIs with BRIDGE.'],
  ['policy', 'Policy', 'Notices, documents. Checks the rules.'],
  ['safety', 'Safety', 'Emergency declarations, KPIs. Protects priority traffic.'],
  ['supervisor', 'Supervisor', 'Sees all. Hard limits > constraints > safety > optimisation.'],
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
  const moments = [[0, 'Calm'], [firstAlert ?? 25, 'Forecast alert'], [28, 'Emergency declared'], [45, 'Rain fade'], [50, 'Cap arrives'], [61, 'Recovery']];
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
        <div className="panel"><h4>Data waiting in area {cell}</h4><p className="sub">Hover to read any moment.</p>
          <LineChart height={220} xLabel="slot" yLabel="kb" cursor={t} format={(v) => v.toFixed(0)} marks={[{ x: 28, to: 61, label: 'em', color: 'var(--critical)' }]} series={['OrbitFlow', 'BRIDGE alone', 'Reactive greedy'].map((n) => ({ name: n, color: COLORS[n], values: q(n, cell) }))} /></div>
        <div className="panel"><h4>Power on cell {cell}</h4><p className="sub">Watts per slot. The dashed line is the {cap} W cap on border cells from slot 50.</p>
          <LineChart height={220} xLabel="slot" yLabel="W" cursor={t} format={(v) => v.toFixed(1)} marks={[{ x: 50, label: `${cap} W cap`, color: 'var(--warning)' }]} series={['OrbitFlow', 'BRIDGE alone'].map((n) => ({ name: n, color: COLORS[n], values: r.runs[n].series.power.map((p) => p[cell]) }))} /></div>
      </div>
      <p className="insight">Across this replay the Policy agent trimmed {failCount} proposals and no limit was broken. Emergency cells are given a beam whenever their data starts to age, not in every slot, which keeps the other areas served.</p>
      <More label="See a deliberate safety test: what happens if the AI proposes 50 W?"><div className="panel">
        <h4><span className="tag warning">Controlled stress test</span> Injected on purpose, not part of the flood above</h4>
        <p style={{ fontSize: 14 }}>A script forces a 50 W proposal on cell 13 at slot {d.study_stress_test.flood_injection.slot}. Limit: {d.study_stress_test.flood_injection.applicable_cap_w} W ({d.study_stress_test.flood_injection.cap_status}). Executed: <b className="mono">{d.study_stress_test.flood_injection.final.power_w['13']} W</b>, with the remainder moved to other beams and a human review raised.</p>
        <div className="scroll"><table><thead><tr><th>Bad proposal</th><th>Caught by</th><th>Executed</th></tr></thead><tbody>
          {d.study_stress_test.guard_cases.map((c) => <tr key={c.case}><td style={{ whiteSpace: 'normal' }}>{c.case}</td><td className="mono">{c.failed_checks.join(', ') || 'policy cap'}</td><td className="mono" style={{ whiteSpace: 'normal' }}>{Object.entries(c.final).map(([k, v]) => `${k}: ${v} W`).join(', ')}</td></tr>)}
        </tbody></table></div>
        <p className="note" style={{ margin: '8px 0 0' }}>Would BRIDGE do this unprompted? Across {d.study_stress_test.natural_bridge_power.decisions.toLocaleString()} decisions in all traffic types, {pct(d.study_stress_test.natural_bridge_power.share_over_50w)} proposed 50 W or more on one beam (largest {d.study_stress_test.natural_bridge_power.max_w.toFixed(0)} W). It is rare, which is why the check must stay.</p>
      </div></More>
    </div></section>
  );
}

const KPI_OPTS = [
  ['rt_sla_violation', 'Late time-critical data', '% of cell-slots', (v) => pct(v), true],
  ['mean_delay_ms', 'Average delay', 'ms', (v) => v.toFixed(1), true],
  ['throughput_mbps', 'Data delivered', 'Mbps', (v) => v.toFixed(1), false],
  ['packet_loss', 'Data lost', '%', (v) => pct(v), true],
  ['beam_switches_per_slot', 'Beam switching', 'per slot', (v) => v.toFixed(2), true],
];
const SCEN = [['pass:dynamic_ntn', 'Recorded pass'], ['pass:openntn_sionna', 'Second dataset'], ['kind:block', 'Sudden hotspots'], ['kind:event_surge', 'Gradual surge'], ['kind:bursty', 'Random bursts'], ['kind:mixed', 'Surge + steady'], ['kind:normal', 'Calm']];
const ROBUST = [['pass:dynamic_ntn', 'Recorded pass'], ['pass:openntn_sionna', 'Second dataset'], ['intensity:0.5', 'Half the traffic'], ['intensity:1.25', '125% traffic'], ['intensity:1.5', '150% traffic'], ['channel:+3dB', 'Signal 3 dB better'], ['channel:-3dB', 'Signal 3 dB worse'], ['channel:-6dB', 'Signal 6 dB worse'], ['outage:0.25', '25% of links blocked'], ['pass_shift:20', 'Pass timing shifted'], ['init_backlog:50ms', 'Starts congested']];
const pv = (p) => (p == null ? 'n/a' : p < 0.001 ? '<0.001' : p.toFixed(3));

function Evidence({ d }) {
  const [sc, setSc] = useState('pass:dynamic_ntn');
  const [kpi, setKpi] = useState('rt_sla_violation');
  const C = d.multirun.conditions; const cond = C[sc];
  const opt = KPI_OPTS.find((o) => o[0] === kpi);
  const order = ['Static round-robin', 'Reactive greedy', 'Heuristic-predictive', 'BC', 'BRIDGE no-forecast', 'BRIDGE'];
  const NAME = { 'Static round-robin': 'Fixed rotation', 'Reactive greedy': 'Simple scheduler', 'Heuristic-predictive': 'Hand-written rule', BC: 'AI copying the rule', 'BRIDGE no-forecast': 'AI without forecast', BRIDGE: 'OrbitFlow AI' };
  const rows = order.map((n) => ({ name: NAME[n], color: COLORS[n] || '#c9c4b8', ...cond.policies[n][kpi] }));
  const cmp = cond.vs_reactive[kpi]?.BRIDGE;
  const mc = d.flood_mc.controllers; const ppo = d.ppo_summary;
  const em = d.study_emergency.conditions['end=61,traffic=1.0'];
  const lk = d.study_link_sensitivity.settings;
  const LAB = { 'bandwidth_mhz=10': 0 };
  return (
    <section className="ch" id="evidence"><div className="wrap">
      <p className="kicker">Chapter 5 · Does it work?</p>
      <h2>Mostly yes. Here is where it wins, and where it doesn’t.</h2>
      <p className="lede">Every strategy faced the same {d.multirun.meta.episodes_kinds_and_passes} test situations, none used in training. OrbitFlow’s scores are averaged over {d.multirun.meta.training_seeds} separately trained models, so one lucky training run can’t flatter it.</p>
      <div className="panel" style={{ marginTop: 28 }}>
        <div className="chips" style={{ marginBottom: 8 }}>{SCEN.map(([k, l]) => <button key={k} className={`chip ${sc === k ? 'on' : ''}`} onClick={() => setSc(k)}>{l}</button>)}</div>
        <div className="chips" style={{ marginBottom: 16 }}>{KPI_OPTS.map(([k, l]) => <button key={k} className={`chip ${kpi === k ? 'on' : ''}`} onClick={() => setKpi(k)}>{l}</button>)}</div>
        <h4>{opt[1]} <span style={{ fontWeight: 400, color: 'var(--ink-3)' }}>({opt[2]}, {opt[4] ? 'lower' : 'higher'} is better)</span></h4>
        <div style={{ marginTop: 10 }}><DotCI rows={rows} format={opt[3]} unit={opt[2]} /></div>
        {cmp && <p className="note" style={{ margin: '10px 0 0' }}>OrbitFlow vs simple scheduler, same {cmp.n} situations: difference {opt[3](Math.abs(cmp.mean_diff))} (95% CI {cmp.diff_lo?.toFixed(3)} to {cmp.diff_hi?.toFixed(3)}), {opt[4] ? cmp.wins_a_lower : cmp.wins_b_lower} better, {opt[4] ? cmp.wins_b_lower : cmp.wins_a_lower} worse, {cmp.ties} tied. Wilcoxon signed-rank, Holm-corrected p {pv(cmp.p_holm)}; effect size {cmp.effect}.</p>}
      </div>
      <div className="panel" style={{ marginTop: 12 }}>
        <h4>Stress-testing the headline</h4><p className="sub">Does the win survive harder conditions? Bars would hide it, so here is the table. The real-world parameters here are provisional.</p>
        <div className="scroll"><table><thead><tr><th>Condition</th><th className="n">Late data: simple</th><th className="n">Late data: OrbitFlow</th><th className="n">Delay ms: simple</th><th className="n">Delay ms: OrbitFlow</th><th>Delay verdict</th></tr></thead><tbody>
          {ROBUST.map(([k, l]) => { const p = C[k].policies; const dv = p.BRIDGE.mean_delay_ms.mean - p['Reactive greedy'].mean_delay_ms.mean; const sig = (C[k].vs_reactive.mean_delay_ms.BRIDGE.p_holm ?? 1) < 0.05; return (
            <tr key={k}><td>{l}</td><td className="n">{pct(p['Reactive greedy'].rt_sla_violation.mean)}</td><td className="n">{pct(p.BRIDGE.rt_sla_violation.mean)}</td><td className="n">{p['Reactive greedy'].mean_delay_ms.mean.toFixed(1)}</td><td className="n">{p.BRIDGE.mean_delay_ms.mean.toFixed(1)}</td><td>{!sig ? <span className="tag">no clear difference</span> : dv < 0 ? <span className="tag good">OrbitFlow faster</span> : <span className="tag warning">OrbitFlow slower</span>}</td></tr>); })}
        </tbody></table></div>
        <p className="insight" style={{ fontSize: 18 }}>Late data falls in every row. Average delay is the catch: when capacity gets scarce, OrbitFlow protects deadlines at the cost of a longer average wait.</p>
      </div>
      <div className="grid g2" style={{ marginTop: 12 }}>
        <div className="panel"><h4>What the safety agents cost</h4><p className="sub">Flood scenario, {d.flood_mc.seeds} runs. “Agents” includes the new need-based emergency service.</p>
          <div className="scroll"><table><thead><tr><th>Strategy</th><th className="n">Limit breaches</th><th className="n">Emergency data served</th><th className="n">Delay ms</th><th className="n">Late data</th></tr></thead><tbody>
            {Object.entries(mc).map(([n, m]) => <tr key={n} className={n === 'OrbitFlow' ? 'best' : ''}><td>{n === 'Static round-robin' ? 'Fixed rotation' : n === 'Reactive greedy' ? 'Simple scheduler' : n === 'BRIDGE alone' ? 'AI, no agents' : 'OrbitFlow, with agents'}</td><td className="n">{m.cap_violation_slots.mean.toFixed(1)}</td><td className="n">{pct(m.emergency_served_ratio.mean)}</td><td className="n">{m.mean_delay_ms.mean.toFixed(1)}</td><td className="n">{pct(m.rt_sla_violation.mean)}</td></tr>)}
          </tbody></table></div>
          <p className="note" style={{ marginTop: 8 }}>The earlier 14 to 23 ms “agent overhead” was not computing time. It came from giving emergency cells a beam in every slot, which starved other areas. The trade-off: need-based service delivers less emergency data overall ({pct(em['need-based + abrupt'].emergency_served_ratio.mean, 0)} vs {pct(em['always + abrupt (previous)'].emergency_served_ratio.mean, 0)}), while emergency deadlines were still met in both. In this scenario the agents’ gain is keeping to the limit, not delivering more emergency data.</p>
        </div>
        <div className="panel"><h4>What each part of the AI adds</h4><p className="sub">Recorded pass, {C['pass:dynamic_ntn'].policies.BRIDGE.mean_delay_ms.n} runs.</p>
          <div className="scroll"><table><thead><tr><th>Version</th><th className="n">Delay ms</th><th className="n">Late data</th></tr></thead><tbody>
            {['Heuristic-predictive', 'BC', 'BRIDGE no-forecast', 'BRIDGE'].map((n) => { const p = C['pass:dynamic_ntn'].policies[n]; return <tr key={n} className={n === 'BRIDGE' ? 'best' : ''}><td>{NAME[n]}</td><td className="n">{p.mean_delay_ms.mean.toFixed(1)}</td><td className="n">{pct(p.rt_sla_violation.mean, 2)}</td></tr>; })}
          </tbody></table></div>
          <p className="note" style={{ marginTop: 8 }}>Reinforcement learning halves the delay of the rule it started from. The forecast cuts delay further, with little change in late data. Training from scratch also reached low delay on validation ({ppo.scratch.delay.toFixed(1)} ms vs {ppo.rg.delay.toFixed(1)} ms), so copying the rule is a useful start but not essential.</p>
        </div>
      </div>
      <More label="See the full methods and engineering sensitivity"><div className="panel">
        <h4>If the provisional radio numbers are wrong</h4><p className="sub">Same trained AI, one parameter changed at a time, {d.study_link_sensitivity.n_per_setting} runs each. Values await engineering review.</p>
        <div className="scroll"><table><thead><tr><th>Setting</th><th className="n">Signal quality dB</th><th className="n">Late: simple</th><th className="n">Late: OrbitFlow</th><th className="n">Delay: simple</th><th className="n">Delay: OrbitFlow</th><th className="n">Emergency served</th></tr></thead><tbody>
          {Object.entries(lk).map(([n, e]) => <tr key={n}><td className="mono">{n}</td><td className="n">{e.bridge.mean_sinr_db.mean.toFixed(1)}</td><td className="n">{pct(e.reactive.rt_sla_violation.mean)}</td><td className="n">{pct(e.bridge.rt_sla_violation.mean)}</td><td className="n">{e.reactive.mean_delay_ms.mean.toFixed(1)}</td><td className="n">{e.bridge.mean_delay_ms.mean.toFixed(1)}</td><td className="n">{pct(e.flood.emergency_served_ratio.mean)}</td></tr>)}
        </tbody></table></div>
        <p className="note" style={{ marginTop: 8 }}>Episodes per condition: {d.multirun.meta.episodes_kinds_and_passes} (scenarios, passes), {d.multirun.meta.episodes_other_conditions} (others). Seeds from {d.multirun.meta.first_seed}. Perturbed recorded passes share one geometry, so they are not independent satellite passes. Full statistics are in results/multirun.json and docs/REPORT.md.</p>
      </div></More>
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
      <h2>Tighten the limit. Worsen the storm. See which one hurts.</h2>
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
          <p className="note" style={{ margin: '6px 0 0' }}>Data waiting in the surge area, cell {d.flood_replay.meta.event_cell}. Precomputed run <code>{cur.experiment_id}</code></p>
          <div className="scroll"><table style={{ marginTop: 8 }}><thead><tr><th /><th className="n">Cap breach slots</th><th className="n">Emergency served</th><th className="n">Human reviews</th></tr></thead><tbody>
            <tr><td>OrbitFlow</td><td className="n">{o.cap_violation_slots}</td><td className="n">{pct(o.emergency_served_ratio)}</td><td className="n">{o.human_reviews}</td></tr>
            <tr><td>BRIDGE alone</td><td className="n">{b.cap_violation_slots}</td><td className="n">{pct(b.emergency_served_ratio)}</td><td className="n">{b.human_reviews}</td></tr>
          </tbody></table></div>
        </div>
      </div>
      <div className="panel" style={{ marginTop: 12 }}>
        <h4>What real regulations imply <span className="tag warning" style={{ marginLeft: 4 }}>indicative</span></h4>
        <p className="sub">Regulators limit power reaching the ground, not watts per beam. This applies the ITU-R SF.358-5 limit per area and per moment, for different assumed antenna gains. {d.study_pfd_mask.n_per_setting} runs each.</p>
        <div className="scroll"><table><thead><tr><th>Assumed satellite antenna gain</th><th className="n">Typical limit per beam</th><th className="n">Emergency data served</th><th className="n">Delay ms</th><th className="n">Breaches with agents</th><th className="n">Breaches without</th></tr></thead><tbody>
          {Object.entries(d.study_pfd_mask.settings).map(([n, e]) => <tr key={n}><td>{n === 'no cap' ? 'No limit applied' : n.replace('Gtx=', '')}</td><td className="n">{e.median_cap_w ? `${e.median_cap_w.toFixed(0)} W` : '-'}</td><td className="n">{pct(e.emergency_served_ratio.mean, 0)}</td><td className="n">{e.mean_delay_ms.mean.toFixed(1)}</td><td className="n">{e.pfd_breach_slots.mean.toFixed(0)}</td><td className="n">{e.breach_slots_without_agents ? e.breach_slots_without_agents.mean.toFixed(0) : '-'}</td></tr>)}
        </tbody></table></div>
        <p className="insight" style={{ fontSize: 19 }}>A loose limit barely matters, which is what the grid above shows. A realistic one can dominate: at 30 dBi, emergency service falls to {pct(d.study_pfd_mask.settings['Gtx=30 dBi'].emergency_served_ratio.mean, 0)}. The satellite’s real antenna gain is the most valuable number still missing.</p>
        <p className="note">{d.study_pfd_mask.label}</p>
      </div>
      <More label="See why, and how rain and limits combine"><div className="panel">
        <h4>Rain × power limit, {d.study_factorial.n_per_cell} paired runs per cell</h4>
        <div className="scroll"><table><thead><tr><th>Rain fade</th><th>Limit (hypothetical)</th><th className="n">Emergency served</th><th className="n">Slots where limit bites</th></tr></thead><tbody>
          {d.study_factorial.cells.map((c) => <tr key={`${c.rain_db}-${c.cap_w}`}><td>{c.rain_db} dB</td><td>{c.cap_w ? `${c.cap_w} W` : 'none'}</td><td className="n">{pct(c.emergency_served_ratio.mean)}</td><td className="n">{pct(c.cap_binding_share.mean, 0)}</td></tr>)}
        </tbody></table></div>
        <p className="note" style={{ marginTop: 8 }}>The effects compound: at 12 dB and 8 W, the combined loss is {Math.abs(d.study_factorial.interaction_served_ratio.rain12_cap8.mean * 100).toFixed(0)} points beyond the sum of each alone. A 22 W limit rarely hurts because signal quality is capped by interference between beams: going from 25 W to 22 W moves that ceiling only from {d.study_factorial.physics.sinr_ceiling_equal_beams_db.toFixed(1)} to {d.study_factorial.physics.sinr_ceiling_22W_vs_78W_db.toFixed(1)} dB, and capacity grows only with the logarithm of it.</p>
      </div></More>
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
      <p className="lede">The rulebook is the ITU AI Readiness document repository plus four ITU-R and FCC documents: {t.ingested} of {t.files} files, {t.pages.toLocaleString()} pages, {t.chunks.toLocaleString()} chunks. It joins AI-policy documents with four satellite regulatory documents, so it can support both how OrbitFlow is structured and how real power limits work.</p>
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
    ['From real data', 'The satellite’s path, signal conditions and timing come from the supplied offline NTN datasets. The rulebook is real documents: the ITU AI Readiness repository plus ITU-R and FCC satellite documents.'],
    ['Measured by us', 'Every chart: all results are computed by running the software, with fixed seeds, and can be reproduced.'],
    ['Generated for testing', 'Training traffic is generated to match the dataset’s levels. The flood is a test scenario. The 22 W limit is a hypothetical constraint; the flux-density study uses a real ITU-R limit as an indicative guide. None of this shows regulatory compliance.'],
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
