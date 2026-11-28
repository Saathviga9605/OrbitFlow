import React, { useEffect, useMemo, useRef, useState } from 'react';
import HeroScene from './Hero.jsx';
import Flow from './Flow.jsx';
import { COLORS, DotCI, HexMap, LineChart, reducedMotion } from './viz.jsx';
import { Count, DemandStrip, Dial, DocMap, Dumbbell, LabScene, ScrollBar, useApi, useReveal, Waffle } from './fx.jsx';
import Game from './Game.jsx';
import Console from './Console.jsx';
import { LangProvider, LangSwitch, useI18n } from './i18n.jsx';

const CHAPTERS = ['chase', 'loop', 'mission', 'evidence', 'lab', 'game', 'knowledge', 'ops'];
const pct = (v, d = 1) => `${(v * 100).toFixed(d)}%`;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
// Data keys used in results files -> translation keys for their display names
const CTRL = { 'Static round-robin': 'ctrl.static', 'Reactive greedy': 'ctrl.reactive', 'Heuristic-predictive': 'ctrl.rule', BC: 'ctrl.bc', 'BRIDGE no-forecast': 'ctrl.nofc', BRIDGE: 'ctrl.bridge', 'BRIDGE alone': 'ctrl.alone', OrbitFlow: 'ctrl.orbitflow' };

function More({ label, children }) {
  const { t } = useI18n();
  return <details className="more"><summary>{label ?? t('more.details')}</summary><div className="more-body">{children}</div></details>;
}

function TopNav() {
  const { t } = useI18n();
  const [on, setOn] = useState('top');
  useEffect(() => {
    const io = new IntersectionObserver((es) => es.forEach((e) => e.isIntersecting && setOn(e.target.id)), { rootMargin: '-40% 0px -55% 0px' });
    ['top', ...CHAPTERS].forEach((id) => { const el = document.getElementById(id); if (el) io.observe(el); });
    return () => io.disconnect();
  }, []);
  return (
    <nav className="topnav" aria-label={t('nav.sections')}>
      <a href="#top" className="brand" aria-label="OrbitFlow"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><circle cx="12" cy="12" r="4" fill="var(--beam)" /><ellipse cx="12" cy="12" rx="10.5" ry="4.2" fill="none" stroke="currentColor" strokeWidth="1.4" transform="rotate(-24 12 12)" /></svg>OrbitFlow</a>
      <div className="navlinks">{CHAPTERS.map((id) => <a key={id} href={`#${id}`} className={on === id ? 'on' : ''}>{t(`nav.${id}`)}</a>)}</div>
      <LangSwitch />
      <span className="simpill" title={t('nav.sim_title')}>{t('nav.sim')}</span>
    </nav>
  );
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
  const { t } = useI18n();
  const r = d.flood_replay;
  const real = d.multirun.conditions['pass:recorded'].policies;
  return (
    <header className="hero" id="top">
      <div className="hero-copy">
        <p className="kicker">{t('hero.kicker')}</p>
        <h1>{t('hero.h1a')}<br />{t('hero.h1b')}<br /><em>{t('hero.h1c')}</em></h1>
        <p className="lede">{t('hero.lede')}</p>
        <div className="hero-cta"><a className="cue" href="#loop">{t('hero.cta1')}</a><a className="cue ghost" href="#ops">{t('hero.cta2')}</a></div>
        <dl className="hero-stats">
          <div><dt>{t('hero.stat1')}</dt><dd dir="ltr"><Count to={real['Reactive greedy'].rt_sla_violation_servable.mean * 100} format={(v) => `${v.toFixed(2)}%`} /> <span>→</span> <Count to={real.BRIDGE.rt_sla_violation_servable.mean * 100} format={(v) => `${v.toFixed(2)}%`} /></dd></div>
          <div><dt>{t('hero.stat2')}</dt><dd dir="ltr"><Count to={d.study_latency.critical_path_total.mean} format={(v) => `${v.toFixed(1)} ms`} /></dd></div>
          <div><dt>{t('hero.stat3')}</dt><dd dir="ltr"><Count to={d.flood_mc.controllers['BRIDGE alone'].cap_violation_slots.mean} /> <span>→</span> {d.flood_mc.controllers.OrbitFlow.cap_violation_slots.mean.toFixed(0)}</dd></div>
        </dl>
      </div>
      <HeroScene replay={r} />
    </header>
  );
}

function Scrub({ t: slot, setT, T, playing, setPlaying, label }) {
  const { t } = useI18n();
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'center' }} dir="ltr">
      <button className="play" onClick={() => setPlaying(!playing)} aria-label={playing ? t('ctl.pause') : t('ctl.play')}>{playing ? '❚❚' : '▶'}</button>
      <input type="range" min="0" max={T - 1} value={slot} onChange={(e) => { setPlaying(false); setT(+e.target.value); }} aria-label={t('ctl.slot')} />
      <span className="mono" style={{ whiteSpace: 'nowrap', fontSize: 13 }}>{label}</span>
    </div>
  );
}

function Chase({ d }) {
  const { t } = useI18n();
  const r = d.flood_replay;
  const clock = useClock(r.meta.T, { speed: 140, start: 40, auto: false });
  const names = ['Static round-robin', 'Reactive greedy', 'BRIDGE alone'];
  const SHOW = { 'Static round-robin': t('ctrl.static'), 'Reactive greedy': t('ctrl.reactive'), 'BRIDGE alone': t('ctrl.bridge') };
  const s = clock.t;
  const qt = (n) => r.runs[n].series.q_rt[s].map((q, i) => q + r.runs[n].series.q_nrt[s][i]);
  const real = d.multirun.conditions['pass:recorded'].policies;
  return (
    <section className="ch" id="chase"><div className="wrap">
      <p className="kicker">{t('chase.kicker')}</p>
      <h2>{t('chase.h2')}</h2>
      <p className="lede">{t('chase.lede')}</p>
      <div className="bigcompare">
        <p className="note" style={{ margin: 0 }}>{t('chase.per100')}</p>
        <div className="waffles">
          <Waffle late={real['Reactive greedy'].rt_sla_violation_servable.mean} label={t('chase.late_simple')} color="var(--reactive)" />
          <Waffle late={real.BRIDGE.rt_sla_violation_servable.mean} label={t('chase.late_of')} color="var(--beam)" />
        </div>
      </div>
      <div className="panel" style={{ marginTop: 16 }}>
        <Scrub {...clock} T={r.meta.T} label={`${t('ctl.slot')} ${String(s).padStart(2, '0')} · ${s * r.meta.slot_ms} ms`} />
        <div className="grid g3" style={{ marginTop: 16 }}>
          {names.map((n) => (
            <div key={n}>
              <HexMap compact cells={r.cells} title={SHOW[n]} beams lit={r.runs[n].series.lit[s]} power={r.runs[n].series.power[s]} load={qt(n)} loadMax={900} />
              <div className="meter"><span>{t('chase.waiting')}</span><div><i style={{ width: `${Math.min(100, qt(n).reduce((a, b) => a + b, 0) / 200)}%` }} /></div><b className="mono">{(qt(n).reduce((a, b) => a + b, 0) / 1000).toFixed(1)} Mb</b></div>
              <div className="meter"><span>{t('chase.delivered')}</span><div><i className="alt" style={{ width: `${Math.min(100, r.runs[n].series.throughput[s] / 3)}%` }} /></div><b className="mono">{r.runs[n].series.throughput[s].toFixed(0)} Mbps</b></div>
            </div>
          ))}
        </div>
      </div>
      <p className="insight">{t('chase.insight', { a: pct(real['Reactive greedy'].rt_sla_violation_servable.mean, 2), b: pct(real.BRIDGE.rt_sla_violation_servable.mean, 2), c: real.BRIDGE.beam_switches_per_slot.mean.toFixed(1), e: real['Reactive greedy'].beam_switches_per_slot.mean.toFixed(1) })}</p>
    </div></section>
  );
}

function Foresee({ d }) {
  const { t } = useI18n();
  const r = d.flood_replay; const ec = r.meta.event_cell;
  const lo = 10; const hi = 40;
  const dem = r.demand.slice(lo, hi).map((x) => x[ec]);
  const fc = r.forecast_h2.slice(lo, hi).map((x) => x[ec]);
  const sc = d.predictor_metrics.scenarios;
  const sweep = useClock(hi - lo, { speed: 170, auto: true });
  const order = ['event_surge', 'mixed', 'bursty', 'block'];
  return (
    <section className="ch" id="foresee"><div className="wrap">
      <p className="kicker">{t('fore.kicker')}</p>
      <h2>{t('fore.h2')}</h2>
      <p className="lede">{t('fore.lede')}</p>
      <div className="grid g2">
        <div className="panel">
          <h4>{t('fore.ramp', { c: ec })}</h4><p className="sub">{t('fore.ramp_sub')}</p>
          <LineChart height={280} x0={lo} cursor={lo + sweep.t} xLabel={t('ctl.slot')} yLabel="Mbps" series={[{ name: t('fore.actual'), color: 'var(--ink)', values: dem }, { name: t('fore.forecast'), color: 'var(--beam)', values: fc, dash: '5 3' }]} marks={[{ x: 28, label: t('fore.emergency'), color: 'var(--critical)' }]} />
        </div>
        <div className="panel">
          <h4>{t('fore.skill')}</h4><p className="sub">{t('fore.skill_sub', { j: d.predictor_metrics.jump_mbps })}</p>
          <DotCI unit={t('fore.reduction')} format={(v) => pct(v, 0)} rows={order.map((k) => { const v = sc[k].gru_jump_skill; return { name: t(`fore.kind.${k}`), mean: v, lo: v, hi: v, n: sc[k].persistence.n_jump, color: v > 0.2 ? 'var(--orbit)' : 'var(--static)' }; })} />
          <More><p className="note">{t('fore.more')}</p></More>
        </div>
      </div>
      <p className="insight">{t('fore.insight', { a: pct(sc.event_surge.gru_jump_skill, 0) })}</p>
    </div></section>
  );
}

function Loop({ d }) {
  const { t } = useI18n();
  return (
    <section className="ch" id="loop"><div className="wrap">
      <p className="kicker">{t('loop.kicker')}</p>
      <h2>{t('loop.h2')}</h2>
      <p className="lede">{t('loop.lede')}</p>
      <Flow d={d} />
    </div></section>
  );
}

const AGENTS = ['network', 'policy', 'safety', 'supervisor'];
const STAGES = [[0, 15, 'T0', 'normal'], [15, 28, 'T1', 'ramp'], [28, 45, 'T3', 'emergency', 'hotstage'], [45, 50, 'T4', 'fade', 'hotstage'], [50, 61, 'T5', 'cap', 'capstage'], [61, 77, 'T6', 'recovery'], [77, 100, 'T7', 'normal']];

function Timeline({ t: slot, setT, setPlaying, T }) {
  const { t } = useI18n();
  const ref = useRef(null);
  const seek = (e) => { const r = ref.current.getBoundingClientRect(); setPlaying(false); setT(clamp(Math.round(((e.clientX - r.left) / r.width) * (T - 1)), 0, T - 1)); };
  return (
    <div className="timeline" dir="ltr" ref={ref} onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); seek(e); }} onPointerMove={(e) => e.buttons && seek(e)}
      role="slider" tabIndex={0} aria-label={t('ctl.slot')} aria-valuemin={0} aria-valuemax={T - 1} aria-valuenow={slot}
      onKeyDown={(e) => { if (e.key === 'ArrowRight') { setPlaying(false); setT(Math.min(T - 1, slot + 1)); } if (e.key === 'ArrowLeft') { setPlaying(false); setT(Math.max(0, slot - 1)); } }}>
      {STAGES.map(([a, b, code, k, c]) => <div key={code + k} className={`stage ${c || ''}`} style={{ left: `${a}%`, width: `${b - a}%` }}>{code} {t(`stage.${k}`)}</div>)}
      <div className="track" />
      <div className="head" style={{ left: `${(slot / (T - 1)) * 100}%` }}><b>{slot}</b></div>
    </div>
  );
}

function FloodSummary({ rec, slot }) {
  const { t, term } = useI18n();
  const last = rec.trace.filter((s) => s.agent === 'supervisor').slice(-1)[0];
  const tag = rec.decision === 'REPAIRED' ? 'warning' : 'good';
  return (
    <div className="panel floodsum">
      <p className="kicker" style={{ marginBottom: 6 }}>{t('flood.decision', { s: slot })}</p>
      <h3><span className={`tag ${tag}`}>{term(rec.decision)}</span> {t('flood.beams', { n: rec.final.beams.length, w: rec.final.p_total_w })}</h3>
      <p lang="en" dir="ltr">{last ? last.rationale : t('flood.approved')}</p>
    </div>
  );
}

function Mission({ d }) {
  const { t, term } = useI18n();
  const r = d.flood_replay; const T = r.meta.T;
  const demandMax = useMemo(() => Math.max(...r.demand.flat(), 1), [r]);
  const firstAlert = r.audit.find((a) => a.trace.some((s) => s.action === 'forecast_alert'))?.slot;
  const clock = useClock(T, { speed: 240, start: 0 });
  const { t: slot, setT, playing, setPlaying } = clock;
  const [cell, setCell] = useState(r.meta.event_cell);
  const [ctrl, setCtrl] = useState('OrbitFlow');
  const run = r.runs[ctrl].series;
  const load = run.q_rt[slot].map((q, i) => q + run.q_nrt[slot][i]);
  const emergency = slot >= 28 && slot < 61 ? r.meta.emergency_cells : [];
  const capActive = slot >= 50;
  const rec = r.audit[slot];
  const seen = (who) => r.events.filter((e) => e.slot <= slot && (who === 'supervisor' || e.audience.includes(who) || e.audience.includes('all')));
  const hidden = (who) => r.events.filter((e) => e.slot <= slot && !e.audience.includes('all') && !e.audience.includes(who)).length;
  const steps = (who) => rec.trace.filter((s) => s.agent === who);
  const cap = r.meta.border_cap_w;
  const failCount = r.audit.filter((a) => a.policy_findings.some((f) => f.status === 'FAIL')).length;
  const proposed = rec.proposed; const final = rec.final;
  const beamRows = [...new Set([...proposed.beams, ...final.beams])];
  const moments = [[0, 'calm'], [firstAlert ?? 25, 'alert'], [28, 'emergency'], [45, 'fade'], [50, 'cap'], [61, 'recovery']];
  const cites = rec.trace.flatMap((s) => s.citations);
  const nice = (txt) => txt.replace('HYPOTHETICAL operating constraint (not a real law):', 'Test limit:');
  const fresh = r.events.find((e) => e.slot === slot);
  const q = (n, c) => r.runs[n].series.q_rt.map((row, i) => row[c] + r.runs[n].series.q_nrt[i][c]);
  const st = d.study_stress_test;
  return (
    <section className="ch" id="mission" style={{ background: '#0d1115' }}><div className="wrap">
      <p className="kicker">{t('flood.kicker')}</p>
      <h2>{t('flood.h2')}</h2>
      <p className="lede">{t('flood.lede')}</p>
      <div className="panel" style={{ marginTop: 28 }}>
        <div className="chips" style={{ marginBottom: 12 }}>
          {moments.map(([s, k]) => <button key={k} className={`chip ${slot === s ? 'on' : ''}`} onClick={() => { setPlaying(false); setT(s); }}>{t(`moment.${k}`)} <span className="mono" style={{ opacity: .65 }}>{s}</span></button>)}
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }} dir="ltr">
          <button className="play" onClick={() => setPlaying(!playing)} aria-label={playing ? t('ctl.pause') : t('ctl.play')}>{playing ? '❚❚' : '▶'}</button>
          <Timeline t={slot} setT={setT} setPlaying={setPlaying} T={T} />
        </div>
      </div>
      <div className="dials panel" style={{ marginTop: 12 }}>
        <Dial value={run.throughput[slot]} max={320} label={t('flood.dial_tp')} display={`${run.throughput[slot].toFixed(0)} Mbps`} />
        <Dial value={run.delay[slot]} max={80} label={t('flood.dial_wait')} display={`${run.delay[slot].toFixed(0)} ms`} color="var(--warning)" />
        <Dial value={run.power[slot].reduce((a, b) => a + b, 0)} max={100} label={t('flood.dial_power')} display={`${run.power[slot].reduce((a, b) => a + b, 0).toFixed(0)} W`} color="var(--bridge)" />
        <div className="toastbox">{fresh ? <div key={fresh.id} className="toast" lang="en" dir="ltr"><span className="mono">slot {fresh.slot}</span> {nice(fresh.description)}</div> : <div className="note">{t('flood.into', { s: slot, ms: slot * r.meta.slot_ms })}</div>}</div>
      </div>
      <div className="panel" style={{ marginTop: 12 }}><h4>{t('flood.demand', { n: d.flood_replay.cells.length })}</h4><p className="sub">{t('flood.demand_sub')}</p>
        <DemandStrip max={demandMax} demand={r.demand[slot]} forecast={r.forecast_h2[slot]} lit={run.lit[slot]} emergency={emergency} />
      </div>
      <div className="grid g-mission" style={{ marginTop: 12 }}>
        <div className="panel">
          <div className="chips" style={{ marginBottom: 10 }}>
            {['OrbitFlow', 'BRIDGE alone', 'Reactive greedy'].map((n) => <button key={n} className={`chip ${ctrl === n ? 'on' : ''}`} onClick={() => setCtrl(n)}>{n === 'OrbitFlow' ? 'OrbitFlow' : t(CTRL[n])}</button>)}
          </div>
          <HexMap cells={r.cells} lit={run.lit[slot]} power={run.power[slot]} load={load} loadMax={900} emergency={emergency} border={r.meta.border_cells} capActive={capActive} selected={cell} onSelect={setCell} beams rainCells={slot >= 45 && slot < 61 ? r.meta.emergency_cells : []} />
          <p className="note" style={{ margin: '8px 0 0' }}><span style={{ color: 'var(--critical)' }}>▲</span> {t('legend.emergency')} · <span style={{ color: 'var(--warning)' }}>{t('legend.yellow')}</span> {t('legend.border')} · {t('legend.rest')}</p>
        </div>
        <div>
          <FloodSummary rec={rec} slot={slot} />
          <More label={t('flood.agents_more')}><div className="grid g2" style={{ marginTop: 0, gap: 8 }}>
            {AGENTS.map((id) => {
              const here = steps(id); const ev = seen(id).slice(-2); const blind = hidden(id);
              return (
                <div key={id} className={`agent ${here.length ? 'active' : ''}`}>
                  <h5>{t(`agent.${id}`)}</h5><div className="role">{t(`agent.${id}.role`)}</div>
                  {ev.map((e) => <div key={e.id} className="ev" lang="en" dir="ltr"><span className="mono" style={{ color: 'var(--ink-3)' }}>{e.slot}</span> {nice(e.description)}</div>)}
                  {here.slice(0, 3).map((s, i) => (
                    <p key={i} lang="en" dir="ltr">{s.output?.status && <span className={`tag ${s.output.status === 'FAIL' ? 'critical' : s.output.status === 'WARN' || s.output.status === 'UNVERIFIED' ? 'warning' : 'good'}`} style={{ marginRight: 5 }}>{s.output.status === 'UNVERIFIED' ? t('flood.notfound') : term(s.output.status)}</span>}{s.rationale}</p>
                  ))}
                  {blind > 0 && id !== 'supervisor' && <div className="blind">{t(blind > 1 ? 'flood.blind_many' : 'flood.blind_one', { n: blind })}</div>}
                </div>
              );
            })}
          </div></More>
          <More label={t('flood.audit_more')}><div className="panel">
            <h4>{t('flood.audit', { s: slot })} <span className={`tag ${rec.decision === 'REPAIRED' ? 'warning' : 'good'}`} style={{ marginInlineStart: 6 }}>{term(rec.decision)}</span></h4>
            <div className="scroll"><table style={{ marginTop: 6 }}><thead><tr><th>{t('tbl.cell')}</th><th className="n">{t('tbl.proposed')}</th><th className="n">{t('tbl.executed')}</th><th>{t('tbl.change')}</th></tr></thead><tbody>
              {beamRows.map((c) => { const a = proposed.power_w[c]; const b = final.power_w[c]; return (
                <tr key={c}><td className="mono">{c}{r.meta.border_cells.includes(c) ? ` (${t('tbl.border')})` : ''}</td><td className="n">{a?.toFixed(1) ?? t('tbl.dark')}</td><td className="n">{b?.toFixed(1) ?? t('tbl.dark')}</td><td>{a == null ? t('tbl.forced') : b == null ? t('tbl.dropped') : Math.abs(a - b) > 0.05 ? `${(b - a).toFixed(1)} W` : ''}</td></tr>); })}
            </tbody></table></div>
            {cites.slice(0, 1).map((c) => <div key={c.chunk_id} style={{ marginTop: 8 }}><div className="quote" lang="en" dir="ltr">“{c.quote}”</div><div className="note">{c.title}, {t('flood.section')} {c.section}. {t('flood.verified')}</div></div>)}
            {rec.trace.some((s) => s.action === 'R5_emergency_exemption') && <p className="note" style={{ margin: '8px 0 0' }}><span className="tag warning">{t('flood.notfound')}</span> {t('flood.no_exemption')}</p>}
          </div></More>
        </div>
      </div>
      <More label={t('flood.charts', { c: cell })}><div className="grid g2" style={{ marginTop: 0 }}>
        <div className="panel"><h4>{t('flood.chart_wait', { c: cell })}</h4><p className="sub">{t('flood.hover')}</p>
          <LineChart height={220} xLabel={t('ctl.slot')} yLabel="kb" cursor={slot} format={(v) => v.toFixed(0)} marks={[{ x: 28, to: 61, label: 'em', color: 'var(--critical)' }]} series={['OrbitFlow', 'BRIDGE alone', 'Reactive greedy'].map((n) => ({ name: t(CTRL[n]), color: COLORS[n], values: q(n, cell) }))} /></div>
        <div className="panel"><h4>{t('flood.chart_power', { c: cell })}</h4><p className="sub">{t('flood.chart_power_sub', { w: cap })}</p>
          <LineChart height={220} xLabel={t('ctl.slot')} yLabel="W" cursor={slot} format={(v) => v.toFixed(1)} marks={[{ x: 50, label: `${cap} W`, color: 'var(--warning)' }]} series={['OrbitFlow', 'BRIDGE alone'].map((n) => ({ name: t(CTRL[n]), color: COLORS[n], values: r.runs[n].series.power.map((p) => p[cell]) }))} /></div>
      </div></More>
      <p className="insight">{t('flood.insight', { n: failCount })}</p>
      <More label={t('stress.more', { x: st.flood_injection.spike_w })}><div className="panel">
        <h4><span className="tag warning">{t('stress.tag')}</span> {t('stress.h4')}</h4>
        <p style={{ fontSize: 14 }}>{t('stress.p', { x: st.flood_injection.spike_w, c: st.flood_injection.cell, s: st.flood_injection.slot, cap: st.flood_injection.applicable_cap_w, w: st.flood_injection.final.power_w[String(st.flood_injection.cell)] })}</p>
        <div className="scroll"><table><thead><tr><th>{t('stress.bad')}</th><th>{t('stress.caught')}</th><th>{t('tbl.executed')}</th></tr></thead><tbody>
          {st.guard_cases.map((c) => <tr key={c.case}><td style={{ whiteSpace: 'normal' }} lang="en">{c.case}</td><td className="mono">{c.failed_checks.join(', ') || 'policy cap'}</td><td className="mono" style={{ whiteSpace: 'normal' }}>{Object.entries(c.final).map(([k, v]) => `${k}: ${v} W`).join(', ')}</td></tr>)}
        </tbody></table></div>
        <p className="note" style={{ margin: '8px 0 0' }}>{t('stress.natural', { n: st.natural_bridge_power.decisions.toLocaleString(), x: st.natural_bridge_power.spike_w, p: pct(st.natural_bridge_power.share_over_spike), m: st.natural_bridge_power.max_w.toFixed(0) })}</p>
      </div></More>
    </div></section>
  );
}

const KPI_OPTS = [
  ['rt_sla_violation_servable', 'kpi.late_servable', 'kpi.late_u', (v) => pct(v, 2), true],
  ['rt_sla_violation', 'kpi.late', 'kpi.late_u', (v) => pct(v), true],
  ['mean_delay_ms', 'kpi.delay', 'ms', (v) => v.toFixed(1), true],
  ['throughput_mbps', 'kpi.tp', 'Mbps', (v) => v.toFixed(1), false],
  ['packet_loss', 'kpi.loss', '%', (v) => pct(v), true],
  ['beam_switches_per_slot', 'kpi.switch', 'kpi.switch_u', (v) => v.toFixed(2), true],
];
const SCEN = ['pass:recorded', 'pass:arrivals', 'kind:block', 'kind:event_surge', 'kind:bursty', 'kind:mixed', 'kind:normal'];
const ROBUST = ['pass:recorded', 'pass:arrivals', 'intensity:0.5', 'intensity:1.25', 'intensity:1.5', 'channel:+3dB', 'channel:-3dB', 'channel:-6dB', 'outage:0.25', 'pass_shift:20', 'init_backlog:50ms'];
const pv = (p) => (p == null ? 'n/a' : p < 0.001 ? '<0.001' : p.toFixed(3));

function Evidence({ d }) {
  const { t } = useI18n();
  const [sc, setSc] = useState('pass:recorded');
  const [kpi, setKpi] = useState('rt_sla_violation_servable');
  const C = d.multirun.conditions; const cond = C[sc];
  const opt = KPI_OPTS.find((o) => o[0] === kpi);
  const unit = opt[2].startsWith('kpi.') ? t(opt[2]) : opt[2];
  const order = ['Static round-robin', 'Reactive greedy', 'Heuristic-predictive', 'BC', 'BRIDGE no-forecast', 'BRIDGE'];
  const rows = order.map((n) => ({ name: t(CTRL[n]), color: COLORS[n] || '#c9c4b8', ...cond.policies[n][kpi] }));
  const cmp = cond.vs_reactive[kpi]?.BRIDGE;
  const mc = d.flood_mc.controllers; const ppo = d.ppo_summary;
  const em = d.study_emergency.conditions['end=61,traffic=1.0'];
  const lk = d.study_link_sensitivity.settings;
  const mcName = { 'Static round-robin': 'ctrl.static', 'Reactive greedy': 'ctrl.reactive', 'BRIDGE alone': 'ctrl.alone', OrbitFlow: 'ctrl.with_agents' };
  return (
    <section className="ch" id="evidence"><div className="wrap">
      <p className="kicker">{t('ev.kicker')}</p>
      <h2>{t('ev.h2')}</h2>
      <p className="lede">{t('ev.lede', { n: d.multirun.meta.episodes_kinds_and_passes, s: d.multirun.meta.training_seeds })}</p>
      <div className="panel" style={{ marginTop: 28 }}>
        <p className="sub">{t('ev.choose')}</p>
        <div className="filters">
          <label className="filter-label">{t('ev.group')}
            <select className="filter-select" value={sc} onChange={(e) => setSc(e.target.value)}>
              {SCEN.map((k) => <option key={k} value={k}>{t(`cond.${k}`)}</option>)}
            </select>
          </label>
          <label className="filter-label">{t('ev.compare')}
            <select className="filter-select" value={kpi} onChange={(e) => setKpi(e.target.value)}>
              {KPI_OPTS.map(([k, l]) => <option key={k} value={k}>{t(l)}</option>)}
            </select>
          </label>
        </div>
        <h4>{t(opt[1])} <span style={{ fontWeight: 400, color: 'var(--ink-3)' }}>({unit}, {t(opt[4] ? 'ev.lower' : 'ev.higher')})</span></h4>
        <p className="sub">{t('ev.ci')}</p>
        <div style={{ marginTop: 10 }}><DotCI rows={rows} format={opt[3]} unit={unit} /></div>
        {cmp && <More label={t('ev.stats_more')}>
          <p className="note">{t('ev.stats', { n: cmp.n, d: opt[3](Math.abs(cmp.mean_diff)), lo: cmp.diff_lo?.toFixed(3), hi: cmp.diff_hi?.toFixed(3), w: opt[4] ? cmp.wins_a_lower : cmp.wins_b_lower, l: opt[4] ? cmp.wins_b_lower : cmp.wins_a_lower, ties: cmp.ties, p: pv(cmp.p_holm), e: cmp.effect })}</p>
        </More>}
      </div>
      <More label={t('ev.deeper')}>
      <div className="panel" style={{ marginTop: 12 }}>
        <h4>{t('ev.harder')}</h4><p className="sub">{t('ev.harder_sub')}</p>
        <div className="grid g2" style={{ marginTop: 8 }}>
          <div><h5 className="minihead">{t('kpi.late_servable')}</h5><Dumbbell rows={ROBUST.map((k) => ({ name: t(`cond.${k}`), a: C[k].policies['Reactive greedy'].rt_sla_violation_servable.mean * 100, b: C[k].policies.BRIDGE.rt_sla_violation_servable.mean * 100 }))} unit="%" format={(v) => `${v.toFixed(2)}%`} aName={t('ctrl.simple_short')} bName="OrbitFlow" aColor="var(--reactive)" bColor="var(--beam)" /></div>
          <div><h5 className="minihead">{t('kpi.delay')}</h5><Dumbbell rows={ROBUST.map((k) => ({ name: t(`cond.${k}`), a: C[k].policies['Reactive greedy'].mean_delay_ms.mean, b: C[k].policies.BRIDGE.mean_delay_ms.mean }))} unit="ms" format={(v) => `${v.toFixed(1)}`} aName={t('ctrl.simple_short')} bName="OrbitFlow" aColor="var(--reactive)" bColor="var(--beam)" /></div>
        </div>
        <p className="insight" style={{ fontSize: 18 }}>{t('ev.harder_insight')}</p>
      </div>
      <div className="grid g2" style={{ marginTop: 12 }}>
        <div className="panel"><h4>{t('ev.cost')}</h4><p className="sub">{t('ev.cost_sub', { n: d.flood_mc.seeds })}</p>
          <div className="scroll"><table><thead><tr><th>{t('tbl.strategy')}</th><th className="n">{t('tbl.breaches')}</th><th className="n">{t('tbl.em_served')}</th><th className="n">{t('tbl.delay_ms')}</th><th className="n">{t('tbl.late')}</th></tr></thead><tbody>
            {Object.entries(mc).map(([n, m]) => <tr key={n} className={n === 'OrbitFlow' ? 'best' : ''}><td>{t(mcName[n])}</td><td className="n">{m.cap_violation_slots.mean.toFixed(1)}</td><td className="n">{pct(m.emergency_served_ratio.mean)}</td><td className="n">{m.mean_delay_ms.mean.toFixed(1)}</td><td className="n">{pct(m.rt_sla_violation.mean)}</td></tr>)}
          </tbody></table></div>
          <p className="note" style={{ marginTop: 8 }}>{t('ev.cost_note', { a: pct(em['need-based + abrupt'].emergency_served_ratio.mean, 0), b: pct(em['always + abrupt (previous)'].emergency_served_ratio.mean, 0), c: pct(em['agents off'].emergency_served_ratio.mean, 1), e: pct(em['need-based + abrupt'].emergency_served_ratio.mean, 1) })}</p>
        </div>
        <div className="panel"><h4>{t('ev.parts')}</h4><p className="sub">{t('ev.parts_sub', { n: C['pass:recorded'].policies.BRIDGE.mean_delay_ms.n })}</p>
          <div className="scroll"><table><thead><tr><th>{t('tbl.version')}</th><th className="n">{t('tbl.delay_ms')}</th><th className="n">{t('tbl.late')}</th></tr></thead><tbody>
            {['Heuristic-predictive', 'BC', 'BRIDGE no-forecast', 'BRIDGE'].map((n) => { const p = C['pass:recorded'].policies[n]; return <tr key={n} className={n === 'BRIDGE' ? 'best' : ''}><td>{t(CTRL[n])}</td><td className="n">{p.mean_delay_ms.mean.toFixed(1)}</td><td className="n">{pct(p.rt_sla_violation.mean, 2)}</td></tr>; })}
          </tbody></table></div>
          <p className="note" style={{ marginTop: 8 }}>{t('ev.parts_note', { a: ppo.scratch.delay.toFixed(1), b: ppo.rg.delay.toFixed(1), x: pct(C['pass:recorded'].policies['BRIDGE no-forecast'].rt_sla_violation_servable.mean, 2), y: pct(C['pass:recorded'].policies.BRIDGE.rt_sla_violation_servable.mean, 2) })}</p>
        </div>
      </div>
      <More label={t('ev.sens_more')}><div className="panel">
        <h4>{t('ev.sens')}</h4><p className="sub">{t('ev.sens_sub', { n: d.study_link_sensitivity.n_per_setting })}</p>
        <div className="scroll"><table><thead><tr><th>{t('tbl.setting')}</th><th className="n">{t('tbl.sinr')}</th><th className="n">{t('tbl.late_simple')}</th><th className="n">{t('tbl.late_of')}</th><th className="n">{t('tbl.delay_simple')}</th><th className="n">{t('tbl.delay_of')}</th><th className="n">{t('tbl.em_served')}</th></tr></thead><tbody>
          {Object.entries(lk).map(([n, e]) => <tr key={n}><td className="mono">{n}</td><td className="n">{e.bridge.mean_sinr_db.mean.toFixed(1)}</td><td className="n">{pct(e.reactive.rt_sla_violation.mean)}</td><td className="n">{pct(e.bridge.rt_sla_violation.mean)}</td><td className="n">{e.reactive.mean_delay_ms.mean.toFixed(1)}</td><td className="n">{e.bridge.mean_delay_ms.mean.toFixed(1)}</td><td className="n">{pct(e.flood.emergency_served_ratio.mean)}</td></tr>)}
        </tbody></table></div>
        <p className="note" style={{ marginTop: 8 }}>{t('ev.sens_note', { a: d.multirun.meta.episodes_kinds_and_passes, b: d.multirun.meta.episodes_other_conditions, s: d.multirun.meta.first_seed })}</p>
      </div></More>
      </More>
    </div></section>
  );
}

function LiveRun({ cap, fade }) {
  const { t } = useI18n();
  const up = useApi();
  const [seed, setSeed] = useState(7);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  const run = async () => {
    setBusy(true); setErr(null);
    const t0 = performance.now();
    try {
      const r = await fetch(`/api/simulate?cap_w=${cap}&fade_db=${fade}&seed=${seed}`, { method: 'POST' });
      if (!r.ok) throw new Error(`server returned ${r.status}`);
      const j = await r.json();
      setRes({ ...j, ms: performance.now() - t0 });
    } catch (e) { setErr(String(e.message)); }
    setBusy(false);
  };
  return (
    <div className="panel live" style={{ marginTop: 12 }}>
      <div className="livehead"><h4>{t('live.h4')} {up && <span className="pulse" />}</h4>
        <label style={{ fontSize: 13 }}>{t('live.seed')} <input className="seed" type="number" min="0" max="100000" value={seed} onChange={(e) => setSeed(Math.max(0, +e.target.value || 0))} /></label>
        <button className="cue" style={{ margin: 0 }} disabled={!up || busy} onClick={run}>{busy ? t('live.busy') : t('live.go', { cap: cap >= 300 ? t('lab.none') : `${cap} W`, fade })}</button>
      </div>
      {up === false && <p className="note" style={{ margin: '8px 0 0' }}>{t('api.off')} <code>python -m uvicorn dashboard.api:app --port 8000</code></p>}
      {err && <p className="note" style={{ color: 'var(--critical)' }}>{t('api.err')} {err}</p>}
      {res && <div className="stats" key={res.ms} style={{ marginTop: 12 }}>
        <div className="stat"><b>{(res.kpis.emergency_served_ratio * 100).toFixed(1)}%</b><span>{t('live.em')}</span></div>
        <div className="stat"><b>{res.kpis.mean_delay_ms.toFixed(1)} ms</b><span>{t('live.wait')}</span></div>
        <div className="stat"><b>{res.kpis.cap_violation_slots}</b><span>{t('live.breach')}</span></div>
        <div className="stat"><b>{res.kpis.human_reviews}</b><span>{t('live.human')}</span></div>
      </div>}
      {res && <p className="note" style={{ margin: '8px 0 0' }}>{t('live.done', { s: (res.ms / 1000).toFixed(1) })} <code>{res.experiment_id}</code></p>}
    </div>
  );
}

function Lab({ d }) {
  const { t } = useI18n();
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
  const capLabel = (c) => (c >= 300 ? t('lab.none') : `${c} W`);
  const sentence = () => {
    if (o.human_reviews) return t('lab.s_review', { p: pct(o.emergency_served_ratio, 0) });
    if (o.emergency_served_ratio < 0.98) return t('lab.s_fade', { p: pct(o.emergency_served_ratio, 0) });
    return `${t('lab.s_ok', { p: pct(o.emergency_served_ratio, 0) })} ${b.cap_violation_slots ? t('lab.s_breach', { n: b.cap_violation_slots }) : t('lab.s_loose')}`;
  };
  const pf = d.study_pfd_mask;
  return (
    <section className="ch" id="lab"><div className="wrap">
      <p className="kicker">{t('lab.kicker')}</p>
      <h2>{t('lab.h2')}</h2>
      <p className="lede">{t('lab.lede')}</p>
      <div className="grid g2">
        <div className="panel">
          <label style={{ display: 'block', marginBottom: 12 }}><span style={{ fontSize: 14 }}>{t('lab.cap')} <b className="mono">{capLabel(cap)}</b></span>
            <input dir="ltr" type="range" min="0" max={g.caps.length - 1} value={g.caps.indexOf(cap)} onChange={(e) => setCap(g.caps[+e.target.value])} /></label>
          <label style={{ display: 'block', marginBottom: 16 }}><span style={{ fontSize: 14 }}>{t('lab.fade')} <b className="mono">{fade} dB</b></span>
            <input dir="ltr" type="range" min="0" max={g.fades.length - 1} value={g.fades.indexOf(fade)} onChange={(e) => setFade(g.fades[+e.target.value])} /></label>
          <div className="chips" style={{ marginBottom: 10 }}>
            <button className={`chip ${metric === 'emergency_served_ratio' ? 'on' : ''}`} onClick={() => setMetric('emergency_served_ratio')}>{t('lab.m_em')}</button>
            <button className={`chip ${metric === 'mean_delay_ms' ? 'on' : ''}`} onClick={() => setMetric('mean_delay_ms')}>{t('lab.m_delay')}</button>
          </div>
          <div className="heat" dir="ltr" style={{ gridTemplateColumns: `52px repeat(${g.fades.length}, 1fr)` }}>
            <div className="ax">W \ dB</div>{g.fades.map((f) => <div key={f} className="ax">{f} dB</div>)}
            {g.caps.map((c) => <React.Fragment key={c}><div className="ax">{capLabel(c)}</div>
              {g.fades.map((f) => { const s = cell(c, f); return <button key={f} className={c === cap && f === fade ? 'on' : ''} style={{ background: s.bg, color: s.fg }} onClick={() => { setCap(c); setFade(f); }} aria-label={`${capLabel(c)}, ${f} dB: ${fmt(s.v)}`}>{fmt(s.v)}{at(c, f).OrbitFlow.human_reviews > 0 ? ' ⚑' : ''}</button>; })}
            </React.Fragment>)}
          </div>
          <p className="note" style={{ margin: '8px 0 0' }}>{t('lab.heat_note')}</p>
        </div>
        <div className="panel">
          <LabScene cap={cap} fade={fade} served={pct(o.emergency_served_ratio, 0)} />
          <h4 style={{ marginTop: 10 }}>{t('lab.this')}</h4>
          <p style={{ font: '400 20px/1.35 var(--serif)', margin: '6px 0 14px', minHeight: 82 }}>{sentence()}</p>
          <LineChart height={210} xLabel={t('ctl.slot')} yLabel="kb" format={(v) => v.toFixed(0)} marks={[{ x: 45, to: 61, label: 'fade', color: 'var(--critical)' }]} series={[{ name: 'OrbitFlow', color: COLORS.OrbitFlow, values: o.q_event }, { name: t('ctrl.alone'), color: COLORS['BRIDGE alone'], values: b.q_event }]} />
          <p className="note" style={{ margin: '6px 0 0' }}>{t('lab.chart_note', { c: d.flood_replay.meta.event_cell })} <code>{cur.experiment_id}</code></p>
          <div className="scroll"><table style={{ marginTop: 8 }}><thead><tr><th /><th className="n">{t('tbl.breaches')}</th><th className="n">{t('tbl.em_served')}</th><th className="n">{t('tbl.reviews')}</th></tr></thead><tbody>
            <tr><td>OrbitFlow</td><td className="n">{o.cap_violation_slots}</td><td className="n">{pct(o.emergency_served_ratio)}</td><td className="n">{o.human_reviews}</td></tr>
            <tr><td>{t('ctrl.alone')}</td><td className="n">{b.cap_violation_slots}</td><td className="n">{pct(b.emergency_served_ratio)}</td><td className="n">{b.human_reviews}</td></tr>
          </tbody></table></div>
        </div>
      </div>
      <More label={t('lab.live_more')}><LiveRun cap={cap} fade={fade} /></More>
      <More label={t('lab.pfd_more')}><div className="panel" style={{ marginTop: 12 }}>
        <h4>{t('lab.pfd')}</h4>
        <p className="sub">{t('lab.pfd_sub', { n: pf.n_per_setting })}</p>
        <div style={{ marginBottom: 14 }}><LineChart height={220} xLabel="dBi" yLabel="%" format={(v) => `${v.toFixed(0)}%`} yMax={105} series={[{ name: t('tbl.em_served'), color: 'var(--beam)', x: [15, 20, 25, 30], values: ['Gtx=15 dBi', 'Gtx=20 dBi', 'Gtx=25 dBi', 'Gtx=30 dBi'].map((k) => pf.settings[k].emergency_served_ratio.mean * 100) }]} /></div>
        <div className="scroll"><table><thead><tr><th>{t('tbl.gain')}</th><th className="n">{t('tbl.limit_beam')}</th><th className="n">{t('tbl.em_served')}</th><th className="n">{t('tbl.delay_ms')}</th><th className="n">{t('tbl.br_with')}</th><th className="n">{t('tbl.br_without')}</th></tr></thead><tbody>
          {Object.entries(pf.settings).map(([n, e]) => <tr key={n}><td>{n === 'no cap' ? t('lab.nolimit') : n.replace('Gtx=', '')}</td><td className="n">{e.median_cap_w ? `${e.median_cap_w.toFixed(0)} W` : '-'}</td><td className="n">{pct(e.emergency_served_ratio.mean, 0)}</td><td className="n">{e.mean_delay_ms.mean.toFixed(1)}</td><td className="n">{e.pfd_breach_slots.mean.toFixed(0)}</td><td className="n">{e.breach_slots_without_agents ? e.breach_slots_without_agents.mean.toFixed(0) : '-'}</td></tr>)}
        </tbody></table></div>
        <p className="insight" style={{ fontSize: 19 }}>{t('lab.pfd_insight', { p: pct(pf.settings['Gtx=30 dBi'].emergency_served_ratio.mean, 0) })}</p>
      <More label={t('lab.fact_more')}><div className="panel">
        <h4>{t('lab.fact', { n: d.study_factorial.n_per_cell })}</h4>
        <div className="scroll"><table><thead><tr><th>{t('tbl.rain')}</th><th>{t('tbl.test_limit')}</th><th className="n">{t('tbl.em_served')}</th><th className="n">{t('tbl.bites')}</th></tr></thead><tbody>
          {d.study_factorial.cells.map((c) => <tr key={`${c.rain_db}-${c.cap_w}`}><td>{c.rain_db} dB</td><td>{c.cap_w ? `${c.cap_w} W` : t('lab.none')}</td><td className="n">{pct(c.emergency_served_ratio.mean)}</td><td className="n">{pct(c.cap_binding_share.mean, 0)}</td></tr>)}
        </tbody></table></div>
        <p className="note" style={{ marginTop: 8 }}>{t('lab.fact_note', { p: Math.abs(d.study_factorial.interaction_served_ratio.rain12_cap8.mean * 100).toFixed(0), a: d.study_factorial.physics.sinr_ceiling_equal_beams_db.toFixed(1), b: d.study_factorial.physics.sinr_ceiling_22W_vs_78W_db.toFixed(1) })}</p>
      </div></More>
    </div></More></div></section>
  );
}

function Quote({ c }) {
  const { t } = useI18n();
  return (
    <div style={{ marginBottom: 10 }}>
      <div className="quote" lang="en" dir="ltr">“{c.quote}”</div>
      <div className="note">{c.title}{c.issuer && !c.issuer.startsWith('not stated') ? ` · ${c.issuer}` : ''} · p. {c.page} · <span className="tag good">{t('kb.verbatim')}</span></div>
    </div>
  );
}

function AskLive({ onCited }) {
  const { t } = useI18n();
  const up = useApi();
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  const ask = async (e) => {
    e.preventDefault();
    if (!q.trim()) return;
    setBusy(true); setErr(null); setRes(null);
    try {
      const r = await fetch(`/api/ask?q=${encodeURIComponent(q)}`, { method: 'POST' });
      if (!r.ok) throw new Error(`server returned ${r.status}`);
      const j = await r.json();
      setRes(j); onCited(j.quotes.map((c) => c.doc_id));
    } catch (x) { setErr(String(x.message)); }
    setBusy(false);
  };
  return (
    <div className="panel" style={{ marginTop: 12 }}><h4>{t('kb.ask_h4')} {up && <span className="pulse" />}</h4><p className="sub">{t('kb.ask_sub')}</p>
      <form className="askform" onSubmit={ask}>
        <input value={q} onChange={(e) => setQ(e.target.value)} maxLength={500} disabled={!up} placeholder={up === false ? t('kb.ask_off') : t('kb.ask_ph')} aria-label={t('kb.ask_label')} dir="auto" />
        <button className="cue" style={{ margin: 0 }} disabled={!up || busy}>{busy ? t('kb.searching') : t('kb.ask')}</button>
      </form>
      {busy && <div className="scanbar"><i /></div>}
      {up === false && <p className="note" style={{ margin: '8px 0 0' }}><code>python -m uvicorn dashboard.api:app --port 8000</code></p>}
      {err && <p className="note" style={{ color: 'var(--critical)' }}>{t('api.err')} {err}</p>}
      {res && <div style={{ marginTop: 12 }}>{res.supported ? res.quotes.map((c) => <Quote key={c.chunk_id} c={c} />) : <p className="insight" style={{ borderColor: 'var(--warning)', fontSize: 18 }}>{t('kb.unsupported')}</p>}</div>}
      <p className="note" style={{ margin: '8px 0 0' }}>{t('kb.english_only')}</p>
    </div>
  );
}

function Knowledge({ d }) {
  const { t } = useI18n();
  const k = d.kb_report; const g = d.gaps; const tot = k.totals;
  const [cited, setCited] = useState(null);
  const [q, setQ] = useState(0);
  const [fac, setFac] = useState(3);
  const [show, setShow] = useState(false);
  const s = k.questions[q]; const m = k.readiness_mapping[fac];
  const ev = k.retrieval_eval.methods;
  const docs = k.documents.filter((x) => x.chunks > 0);
  return (
    <section className="ch" id="knowledge"><div className="wrap">
      <p className="kicker">{t('kb.kicker')}</p>
      <h2>{t('kb.h2')}</h2>
      <p className="lede">{t('kb.lede')}</p>
      <div className="stats" style={{ marginTop: 24 }}>
        <div className="stat"><b><Count to={tot.evidence_eligible} /></b><span>{t('kb.s1')}</span></div>
        <div className="stat"><b><Count to={tot.pages} format={(v) => Math.round(v).toLocaleString()} /></b><span>{t('kb.s2')}</span></div>
        <div className="stat"><b>{k.citation_verification.checked - k.citation_verification.failed}/{k.citation_verification.checked}</b><span>{t('kb.s3')}</span></div>
        <div className="stat"><b>{pct(ev.bm25.section_recall_at_5, 0)}</b><span>{t('kb.s4')}</span></div>
      </div>
      <More label={t('kb.lib_more')}><div className="panel" style={{ marginTop: 12 }}><h4>{t('kb.lib')}</h4><DocMap docs={docs} active={cited ?? s.quotes.map((c) => c.doc_id)} /></div></More>
      <AskLive onCited={setCited} />
      <div className="grid g2" style={{ marginTop: 12 }}>
        <div className="panel"><h4>{t('kb.corpus')}</h4><p className="sub">{t('kb.corpus_sub')}</p>
          <label className="filter-label" style={{ margin: '8px 0 12px' }}>{t('kb.example')}
            <select className="filter-select" value={q} onChange={(e) => { setQ(+e.target.value); setCited(null); }} lang="en" dir="ltr">
              {k.questions.map((x, i) => <option key={x.query} value={i}>{x.query}</option>)}
            </select>
          </label>
          {s.supported ? s.quotes.map((c) => <Quote key={c.chunk_id} c={c} />) : <p className="insight" style={{ borderColor: 'var(--warning)', fontSize: 18 }}>{t('kb.unsupported')}</p>}
        </div>
        <More label={t('kb.ready_more')}><div className="panel" style={{ marginTop: 12 }}>
          <h4>{t('kb.ready')}</h4><p className="sub">{t('kb.ready_sub')}</p>
          <div className="chips" style={{ margin: '8px 0 12px' }} lang="en">{k.readiness_mapping.map((x, i) => <button key={x.factor} className={`chip ${fac === i ? 'on' : ''}`} onClick={() => setFac(i)}>{x.factor}</button>)}</div>
          <p className="note" style={{ margin: 0 }}>{t('kb.stated')}</p><Quote c={m.stated_in_framework} /><Quote c={m.supporting_evidence} />
          <p style={{ fontSize: 14, margin: '6px 0' }}><b>{t('kb.interp')}</b> <span lang="en">{m.interpretation}</span></p>
          <p style={{ fontSize: 14, margin: '6px 0' }}><b>{t('kb.contrib')}</b> <span lang="en">{m.orbitflow_contribution}</span></p>
        </div></More>
      </div>
      <More label={t('kb.all_more')}>
      <div className="grid g2" style={{ marginTop: 12 }}>
        <div className="panel"><h4>{t('kb.rules')}</h4><p className="sub">{t('kb.rules_sub')}</p>
          <div className="scroll"><table><thead><tr><th>{t('tbl.rule')}</th><th>{t('tbl.evidence')}</th></tr></thead><tbody>
            {k.rules.map((r) => <tr key={r.rule_id}><td style={{ whiteSpace: 'normal' }} lang="en">{r.title}</td><td><span className={`tag ${r.evidence_status === 'FOUND' ? 'good' : 'warning'}`}>{t(r.evidence_status === 'FOUND' ? 'kb.found' : 'kb.none')}</span></td></tr>)}
          </tbody></table></div>
        </div>
        <div className="panel"><h4>{t('kb.gaps')}</h4><p className="sub">{t('kb.gaps_sub')}</p>
          {g.candidates.map((c) => <p key={c.id} style={{ fontSize: 14, margin: '8px 0' }} lang="en"><span className="mono" style={{ color: 'var(--ink-3)' }}>{c.id}</span> <b>{c.title}.</b> {c.consequence}</p>)}
        </div>
      </div>
      <div className="panel" style={{ marginTop: 12 }}>
        <h4>{t('kb.methods')}</h4>
        <div className="scroll" dir="ltr"><table><thead><tr><th>{t('tbl.method')}</th><th className="n">Section recall@5</th><th className="n">Doc recall@5</th><th className="n">Precision@5</th><th className="n">MRR</th></tr></thead><tbody>
          {Object.entries(ev).map(([n, r]) => <tr key={n} className={n === 'bm25' ? 'best' : ''}><td>{n}{n === 'bm25' ? ` (${t('kb.default')})` : ''}</td><td className="n">{pct(r.section_recall_at_5, 0)}</td><td className="n">{pct(r.doc_recall_at_5, 0)}</td><td className="n">{pct(r.precision_at_5, 0)}</td><td className="n">{r.mrr.toFixed(2)}</td></tr>)}
        </tbody></table></div>
      </div>
      <div className="panel" style={{ marginTop: 12 }}>
        <button className="chip" onClick={() => setShow(!show)}>{t(show ? 'kb.hide' : 'kb.show', { n: docs.length })}</button>
        <p className="note" style={{ margin: '8px 0 0' }} lang="en" dir="ltr">Source: {k.source.repository} at {k.source.commit.slice(0, 10)}. {k.source.licence}.</p>
        {show && <div className="scroll" style={{ marginTop: 8 }}><table><thead><tr><th>{t('tbl.document')}</th><th>{t('tbl.issuer')}</th><th>{t('tbl.status')}</th><th className="n">{t('tbl.pages')}</th><th className="n">{t('tbl.chunks')}</th></tr></thead><tbody>
          {docs.map((x) => <tr key={x.doc_id}><td style={{ whiteSpace: 'normal' }} lang="en">{x.title}</td><td style={{ color: 'var(--ink-2)' }} lang="en">{x.issuer}</td><td><span className={`tag ${x.chunks === 0 ? 'critical' : x.evidence_eligible ? 'good' : 'warning'}`}>{t(x.chunks === 0 ? 'kb.st_failed' : x.evidence_eligible ? 'kb.st_evidence' : x.role === 'primary' ? 'kb.st_dup' : 'kb.st_not')}</span></td><td className="n">{x.pages}</td><td className="n">{x.chunks}</td></tr>)}
        </tbody></table></div>}
      </div>
      </More>
    </div></section>
  );
}

function Ledger() {
  const { t } = useI18n();
  return (
    <section className="ch" id="ledger"><div className="wrap">
      <p className="kicker">{t('led.kicker')}</p>
      <h2>{t('led.h2')}</h2>
      <div className="panel" style={{ marginTop: 28 }}><table className="ledger"><tbody>{[1, 2, 3, 4].map((i) => <tr key={i}><td>{t(`led.r${i}a`)}</td><td>{t(`led.r${i}b`)}</td></tr>)}</tbody></table></div>
      <More label={t('led.more')}><div className="panel" style={{ marginTop: 12 }}><h4>{t('led.repro')}</h4>
        <pre dir="ltr" style={{ margin: '8px 0 0', font: '13px/1.7 var(--mono)', color: 'var(--ink-2)', overflowX: 'auto' }}>{`pip install -r requirements.txt
python -m pytest -q tests                 # physics, guard, leakage, sampler and agent claims
python -m traffic.train_forecaster        # about 6 min on CPU
python -m bridge.train_ppo                # about 15 min; add --no-forecast for the control
python scripts/run_eval.py                # about 2 min; writes results/ and the web data
python scripts/run_suite.py               # ten demonstration scenarios`}</pre>
      </div></More>
    </div></section>
  );
}

function Shell({ d }) {
  const { t, lang } = useI18n();
  useReveal();
  return (
    <>
      <ScrollBar />
      <TopNav />
      <main>
        {lang !== 'en' && <p className="langnote">{t('note.data_english')}</p>}
        <Hero d={d} /><Chase d={d} /><Loop d={d} /><Foresee d={d} /><Mission d={d} /><Evidence d={d} /><Lab d={d} /><Game d={d} /><Knowledge d={d} /><Console d={d} /><Ledger />
        <footer>{t('footer')}</footer>
      </main>
    </>
  );
}

export default function App({ d }) {
  return <LangProvider d={d}><Shell d={d} /></LangProvider>;
}
