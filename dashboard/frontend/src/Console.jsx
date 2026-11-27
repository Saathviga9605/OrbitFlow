import React, { useEffect, useMemo, useState } from 'react';
import { useApi } from './fx.jsx';

// Operations console. Everything shown comes from results/scenario_suite.json and results/governance.json
// (written by scripts/run_suite.py) or from a live API run. Nothing here is typed in by hand.

const LANGS = [['en', 'English'], ['ar', 'العربية'], ['hi', 'हिन्दी'], ['ta', 'தமிழ்']];
const TABS = ['scenarios', 'agents', 'policies', 'standards', 'validation'];
const DECISION_COLOR = { APPROVED: 'var(--line-strong)', REPAIRED: 'var(--bridge)', FALLBACK: 'var(--critical)' };
const STATUS_TAG = { implemented_in_simulation: 'good', partial: 'warning', conceptual: '', proposed: '', not_implemented: 'critical', not_applicable: '' };
const pct = (v) => (v == null ? '–' : `${(v * 100).toFixed(1)}%`);
const num = (v, d = 1) => (v == null ? '–' : Number(v).toFixed(d));

function useLang() {
  const [lang, setLang] = useState(() => { try { return localStorage.getItem('of-lang') || 'en'; } catch { return 'en'; } });
  useEffect(() => { try { localStorage.setItem('of-lang', lang); } catch { /* storage unavailable */ } }, [lang]);
  return [lang, setLang];
}

function Tag({ ok, children, kind }) {
  return <span className={`tag ${kind ?? (ok ? 'good' : 'critical')}`}>{children}</span>;
}

function DecisionStrip({ series, T }) {
  const n = series.decision.length; const w = 100 / n;
  const hr = new Set(series.human_review_slots);
  return (
    <svg viewBox="0 0 100 14" preserveAspectRatio="none" className="dstrip" role="img" aria-label={T('decision_strip')}>
      {series.decision.map((d, i) => <rect key={i} x={i * w} y={3} width={w * 0.9} height={8} fill={DECISION_COLOR[d] || 'var(--line)'}><title>{`${T('slot')} ${i}: ${d}${series.conflicts[i] ? ` · ${series.conflicts[i]} ${T('conflicts')}` : ''}`}</title></rect>)}
      {series.conflicts.map((c, i) => (c ? <rect key={`c${i}`} x={i * w} y={0} width={w * 0.9} height={2} fill="var(--warning)" /> : null))}
      {series.decision.map((_, i) => (hr.has(i) ? <rect key={`h${i}`} x={i * w} y={12} width={w * 0.9} height={2} fill="var(--beam)" /> : null))}
    </svg>
  );
}

function KpiTable({ r, T }) {
  const rows = [['OrbitFlow', r.kpis], ...Object.values(r.baselines || {}).map((b) => [b.label, b.kpis]), ...(r.reference ? [[r.reference.label, r.reference.kpis]] : [])];
  return (
    <div className="tablewrap"><table className="ops">
      <thead><tr><th /><th>{T('late')}</th><th>{T('delay')}</th><th>Mbps</th><th>{T('emergency_served')}</th><th>{T('breaches')}</th><th>{T('human_reviews')}</th></tr></thead>
      <tbody>{rows.map(([name, k]) => <tr key={name}><td>{name}</td><td className="mono">{pct(k.rt_sla_violation)}</td><td className="mono">{num(k.mean_delay_ms)} ms</td><td className="mono">{num(k.throughput_mbps)}</td><td className="mono">{k.emergency_served_ratio ? pct(k.emergency_served_ratio) : '–'}</td><td className="mono">{k.cap_violation_slots}</td><td className="mono">{k.human_reviews}</td></tr>)}</tbody>
    </table></div>
  );
}

function TraceView({ samples, T, tr }) {
  const [i, setI] = useState(0);
  if (!samples?.length) return null;
  const s = samples[Math.min(i, samples.length - 1)];
  return (
    <div className="panel" style={{ marginTop: 12 }}>
      <h4>{T('trace')}</h4>
      <div className="chips" style={{ margin: '8px 0' }}>{samples.map((x, j) => <button key={x.slot} className={`chip ${j === i ? 'on' : ''}`} onClick={() => setI(j)}>{T('slot')} {x.slot} · {x.trigger}</button>)}</div>
      <p className="note">{tr(s.decision)} · proposed {JSON.stringify(s.proposed.power_w)} W → final {JSON.stringify(s.final.power_w)} W</p>
      <ol className="steps">{s.trace.map((st, j) => (
        <li key={j}><span className="tag">{st.agent}</span> <b className="mono">{st.action}</b>{st.output?.status ? <> <Tag kind={st.output.status === 'PASS' ? 'good' : st.output.status === 'FAIL' ? 'critical' : 'warning'}>{tr(st.output.status)}</Tag></> : null}
          <div className="note">{st.rationale}</div>
          {st.citations?.[0] && <div className="quote">“{st.citations[0].quote}” <span className="note">— {st.citations[0].title}, p.{st.citations[0].page}</span></div>}
        </li>))}</ol>
    </div>
  );
}

function ScenarioBody({ r, T, tr, lang }) {
  if (r.profiles) {
    return (<div className="tablewrap"><table className="ops"><thead><tr><th>{T('profile')}</th><th>{T('cap')}</th><th>{T('exemption')}</th><th>{T('emergency_served')}</th><th>{T('breaches')}</th><th>exempted</th><th>{T('human_reviews')}</th><th>{T('delay')}</th></tr></thead>
      <tbody>{r.profile_effect.table.map((x) => <tr key={x.profile}><td className="mono">{x.profile}</td><td className="mono">{x.cap_w} W</td><td>{tr(x.exemption)}</td><td className="mono">{pct(x.emergency_served_ratio)}</td><td className="mono">{x.cap_violation_slots}</td><td className="mono">{x.exempted_slots}</td><td className="mono">{x.human_reviews}</td><td className="mono">{num(x.mean_delay_ms)} ms</td></tr>)}</tbody></table>
      <p className="note">Proposals identical before slot {r.profile_effect.cap_onset_slot}: <b>{String(r.profile_effect.pre_cap_identical)}</b>. Same seed, demand, channel and checkpoint for every row.</p></div>);
  }
  if (r.matrix) {
    const m = r.matrix.results;
    return (<div className="tablewrap"><table className="ops"><thead><tr><th>context</th>{Object.keys(m.normal).map((p) => <th key={p}>{p}</th>)}</tr></thead>
      <tbody>{Object.entries(m).map(([ctx, byP]) => <tr key={ctx}><td>{ctx}</td>{Object.values(byP).map((v, i) => <td key={i} className="mono">{pct(v.kpis.emergency_served_ratio || null)} · {num(v.kpis.mean_delay_ms)} ms · {v.kpis.human_reviews} HR · {v.exempted_slots} ex</td>)}</tr>)}</tbody></table>
      <p className="note">Model parameter checksum: <code>{r.matrix.model_param_sha.join(', ')}</code></p></div>);
  }
  if (r.multilingual) {
    return (<div className="grid g2" style={{ marginTop: 0 }}>{Object.entries(r.multilingual.per_language).map(([l, v]) => (
      <div key={l} className="panel" dir={l === 'ar' ? 'rtl' : 'ltr'} lang={l}><h4>{l}</h4><p className="quote" style={{ borderColor: 'var(--beam)' }}>{v.input}</p>
        <p className="note" dir="ltr">→ {v.interpreted.scenario_id} · {v.interpreted.profile_id} · {JSON.stringify(v.interpreted.params)} · {pct(v.kpis.emergency_served_ratio)}</p>
        <ul className="explain">{v.explanation.slice(1, -1).map((s) => <li key={s}>{s}</li>)}</ul></div>))}</div>);
  }
  return <KpiTable r={r} T={T} />;
}

function Scenarios({ suite, T, tr, lang, scen }) {
  const up = useApi();
  const [sel, setSel] = useState(0);
  const [live, setLive] = useState({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const base = suite.scenarios[sel];
  const r = live[base.id] || base;
  const run = async () => {
    setBusy(true); setErr(null);
    try {
      const x = await fetch(`/api/scenarios/${base.id}/run`, { method: 'POST' });
      if (!x.ok) throw new Error(`server returned ${x.status}`);
      const j = await x.json(); setLive({ ...live, [base.id]: { ...j, _live: true } });
    } catch (e) { setErr(String(e.message)); }
    setBusy(false);
  };
  const passed = r.checks.filter((c) => c.passed).length;
  return (
    <>
      <div className="chips" role="tablist" style={{ marginTop: 20 }}>{suite.scenarios.map((s, i) => <button key={s.id} className={`chip ${i === sel ? 'on' : ''}`} onClick={() => setSel(i)}>{s.passed ? '✓' : '✗'} {scen(s.id, s.title)}</button>)}</div>
      <div className="grid g2" style={{ marginTop: 16 }}>
        <div className="panel">
          <h4>{scen(r.id, r.title)} <Tag ok={r.passed}>{passed}/{r.checks.length} {T('observed')}</Tag> {r._live ? <Tag kind="good">{T('live')}</Tag> : <span className="note">{T('precomputed')}</span>}</h4>
          <p className="sub" dir="ltr" lang="en">{r.description}</p>
          <p className="note"><b>{T('simulated')}:</b> <span dir="ltr" lang="en">{(r.simulated || []).join('; ')}</span></p>
          <p className="note"><b>{T('expected')}:</b> <span dir="ltr" lang="en">{r.expected}</span></p>
          <h4 style={{ marginTop: 12 }}>{T('checks')}</h4>
          <ul className="checks">{r.checks.map((c) => <li key={c.metric}><Tag ok={c.passed}>{c.passed ? T('observed') : T('not_observed')}</Tag> <code dir="ltr">{c.metric} {c.op} {String(c.expected_from ? `${c.expected_from} (${c.expected})` : c.expected)}</code> → <b className="mono">{String(c.actual)}</b></li>)}</ul>
          <div className="livehead" style={{ marginTop: 12 }}>
            <button className="cue" style={{ margin: 0 }} disabled={!up || busy} onClick={run}>{busy ? T('running') : T('run_live')}</button>
            <span className="note" dir="ltr">{T('reproduce')}: <code>{r.reproducibility.command}</code> · seed {r.seed}</span>
          </div>
          {up === false && <p className="note">{T('api_off')}</p>}
          {err && <p className="note" style={{ color: 'var(--critical)' }}>{err}</p>}
        </div>
        <div className="panel">
          <h4>{T('explanation')}</h4>
          <ul className="explain">{(r.explanation[lang] || r.explanation.en).map((s) => <li key={s}>{s}</li>)}</ul>
          <p className="note"><b>{T('limitations')}:</b> <span dir="ltr" lang="en">{r.limitations}</span></p>
        </div>
      </div>
      {r.series && <div className="panel" style={{ marginTop: 12 }}><h4>{T('decision_strip')}</h4>
        <DecisionStrip series={r.series} T={T} />
        <p className="note"><span style={{ color: 'var(--line-strong)' }}>■</span> {tr('APPROVED')} <span style={{ color: 'var(--bridge)' }}>■</span> {tr('REPAIRED')} <span style={{ color: 'var(--critical)' }}>■</span> {tr('FALLBACK')} · <span style={{ color: 'var(--warning)' }}>▔</span> {T('conflicts')} · <span style={{ color: 'var(--beam)' }}>▁</span> {T('human_reviews')}</p></div>}
      <div className="panel" style={{ marginTop: 12 }}><h4>{T('metrics')}</h4><ScenarioBody r={r} T={T} tr={tr} lang={lang} />
        {r.forecast && <p className="note">Forecast MAE {num(r.forecast.gated_mae_mbps, 3)} Mbps (raw {num(r.forecast.raw_mae_mbps, 3)}, repeat-last {num(r.forecast.persistence_mae_mbps, 3)}); gate fallback on {pct(r.forecast.gated_share)} of cell-slots. {r.forecast.note}.</p>}
      </div>
      <TraceView samples={r.trace_samples} T={T} tr={tr} />
      <Interpret T={T} lang={lang} up={up} />
    </>
  );
}

function Interpret({ T, lang, up }) {
  const [text, setText] = useState('');
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const go = async (e) => {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      const x = await fetch(`/api/interpret?text=${encodeURIComponent(text)}`, { method: 'POST' });
      if (!x.ok) throw new Error(`server returned ${x.status}`);
      setRes(await x.json());
    } catch (e2) { setErr(String(e2.message)); }
    setBusy(false);
  };
  const it = res?.interpreted;
  return (
    <div className="panel" style={{ marginTop: 12 }}>
      <h4>{T('ask_label')}</h4>
      <form className="askform" onSubmit={go} style={{ marginTop: 8 }}>
        <input value={text} onChange={(e) => setText(e.target.value)} maxLength={500} placeholder="حاكِ فيضاناً مع حد قدرة 16 واط وفق ملف الإمارات" aria-label={T('ask_label')} dir="auto" />
        <button className="cue" style={{ margin: 0 }} disabled={!up || busy || !text.trim()}>{busy ? T('running') : T('ask_button')}</button>
      </form>
      {up === false && <p className="note">{T('api_off')}</p>}
      {err && <p className="note" style={{ color: 'var(--critical)' }}>{err}</p>}
      {it && <p className="note" dir="ltr">{T('interpreted_as')}: language <b>{it.language}</b> · scenario <b>{it.scenario_id ?? '–'}</b> · profile <b>{it.profile_id ?? '–'}</b> · {JSON.stringify(it.params)} · matched {JSON.stringify(it.matched_terms)} <span className="note">({it.method})</span></p>}
      {it && !it.understood && <p className="note">{T('not_understood')}</p>}
      {res?.result && <ul className="explain" dir={res.language === 'ar' ? 'rtl' : 'ltr'} lang={res.language}>{res.result.explanation[res.language].map((s) => <li key={s}>{s}</li>)}</ul>}
    </div>
  );
}

function Agents({ gov, T }) {
  const h = gov.health_snapshot?.agent_health || {};
  return (
    <div className="grid g3" style={{ marginTop: 20 }}>{gov.registry.map((a) => (
      <div key={a.id} className={`agent ${a.kind === 'agent' ? 'active' : ''}`} dir="ltr" lang="en">
        <h5>{a.name} <span className="tag">{a.kind}</span> {a.required && <span className="tag">required</span>} {!a.enabled && <span className="tag critical">disabled</span>}</h5>
        <div className="role">{a.technique}</div>
        <p><b>{T('allowed')}:</b> {a.allowed_actions.join('; ')}</p>
        <p><b>{T('prohibited')}:</b> {a.prohibited_actions.join('; ')}</p>
        <p><b>{T('failure_modes')}:</b> {a.failure_modes.join('; ')}</p>
        <p><b>{T('fallback')}:</b> <code>{a.fallback ?? '—'}</code></p>
        {h[a.id] && <p className="ev">{T('health')}: {h[a.id].calls} calls · {h[a.id].failures} failures · {h[a.id].fallbacks} fallbacks {Object.keys(h[a.id].by_kind).length ? JSON.stringify(h[a.id].by_kind) : ''}</p>}
      </div>))}
    </div>
  );
}

function Policies({ gov, T, tr }) {
  const up = useApi();
  const [i, setI] = useState(0);
  const [cap, setCap] = useState(null);
  const [ex, setEx] = useState('');
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const p = gov.profiles[i]; const v = p.validation; const bc = p.operating_constraints.border_power_cap;
  const run = async () => {
    setBusy(true);
    const q = new URLSearchParams({ profile: p.profile_id, ...(cap ? { cap_w: cap } : {}), ...(ex ? { exemption: ex } : {}) });
    try { const x = await fetch(`/api/policy/run?${q}`, { method: 'POST' }); setRes(x.ok ? await x.json() : { error: x.status }); } catch (e) { setRes({ error: String(e) }); }
    setBusy(false);
  };
  return (
    <>
      <div className="chips" style={{ marginTop: 20 }}>{gov.profiles.map((x, j) => <button key={x.profile_id} className={`chip ${j === i ? 'on' : ''}`} onClick={() => { setI(j); setRes(null); setCap(null); setEx(''); }}>{x.jurisdiction} · {x.title}</button>)}</div>
      <div className="grid g2" style={{ marginTop: 16 }}>
        <div className="panel" dir="ltr" lang="en">
          <h4>{p.title} <span className="tag warning">{p.status}</span> <span className="tag">v{p.version}</span></h4>
          <p className="sub">{T('illustrative')} · {p.effective_date} · <code>{p.file}</code> · fingerprint <code>{p.fingerprint}</code></p>
          <p className="note"><b>{T('provenance')}:</b> {p.provenance_note}</p>
          <table className="ops"><tbody>
            <tr><td>{T('cap')}</td><td className="mono">{bc.enabled ? `${bc.cap_w} W on cells ${bc.cells.join(', ')} from slot ${bc.onset_slot}` : 'off'}</td></tr>
            <tr><td>{T('exemption')}</td><td>{tr(p.operating_constraints.emergency_exemption)}</td></tr>
            <tr><td>human review after shortfall</td><td className="mono">{p.human_oversight.sustained_shortfall_slots} slots</td></tr>
            <tr><td>fail-closed cap</td><td className="mono">{p.resilience.fail_closed_cap_w} W</td></tr>
            <tr><td>conservative mode above</td><td className="mono">{pct(p.resilience.max_bad_telemetry_share)} bad telemetry</td></tr>
          </tbody></table>
          {v.conflicts.map((c) => <p key={c.id} className="note"><Tag kind="warning">{T('detected_conflicts')}</Tag> {c.between.join(' × ')} on cells {c.cells.join(', ')}: {c.resolution}</p>)}
          {v.warnings.map((w) => <p key={w} className="note"><Tag kind="warning">{T('warnings')}</Tag> {w}</p>)}
        </div>
        <div className="panel">
          <h4>{T('rules')}</h4>
          <ul className="checks" dir="ltr" lang="en">{v.rules.map((r) => <li key={r.id}><b className="mono">{r.id}</b> {r.title} <span className="tag">{r.enforcement}</span> <span className="tag">{r.source_type}</span> <Tag kind={r.evidence_status === 'FOUND' ? 'good' : r.evidence_status === 'NONE_FOUND' ? 'critical' : ''}>{r.evidence_status}</Tag>
            {r.quote && <div className="quote">“{r.quote.quote}” <span className="note">— {r.quote.title}, p.{r.quote.page}</span></div>}</li>)}</ul>
          <div className="livehead" style={{ marginTop: 12, flexWrap: 'wrap' }}>
            <label className="note">{T('cap')} <input className="seed" type="number" min="2" max="100" placeholder={bc.cap_w} value={cap ?? ''} onChange={(e) => setCap(e.target.value || null)} /></label>
            <label className="note">{T('exemption')} <select className="filter-select" style={{ width: 'auto' }} value={ex} onChange={(e) => setEx(e.target.value)}><option value="">({tr(p.operating_constraints.emergency_exemption)})</option>{['never', 'human_approval', 'automatic'].map((m) => <option key={m} value={m}>{tr(m)}</option>)}</select></label>
            <button className="cue" style={{ margin: 0 }} disabled={!up || busy} onClick={run}>{busy ? T('running') : T('run_live')}</button>
          </div>
          {up === false && <p className="note">{T('api_off')}</p>}
          {res?.kpis && <><KpiTable r={res} T={T} /><p className="note">exempted slots {res.coordination.exempted_slots} · conflicts {JSON.stringify(res.coordination.conflicts_by_type)} · {T('live')}</p></>}
          {res?.error && <p className="note" style={{ color: 'var(--critical)' }}>{JSON.stringify(res.error)}</p>}
        </div>
      </div>
    </>
  );
}

function Standards({ gov, T }) {
  const s = gov.standards; const r = gov.readiness;
  return (
    <div dir="ltr" lang="en">
      <p className="note" style={{ marginTop: 20 }}>OrbitFlow claims no certification, compliance or conformance. Status meanings: implemented in simulation · partial · conceptual · proposed · not implemented · not applicable.</p>
      <div className="tablewrap"><table className="ops">
        <thead><tr><th>{T('standard')}</th><th>{T('alignment')}</th><th>OrbitFlow</th><th>{T('gap')}</th><th>{T('next_step')}</th></tr></thead>
        <tbody>{s.entries.map((e) => <tr key={e.id}><td><b>{e.standard}</b><div className="note">{e.organization} · {e.version}{e.version_verified ? '' : ' (edition unverified)'}{e.in_knowledge_base ? ' · in corpus' : ''}</div><div className="note">{e.title}</div></td>
          <td><span className={`tag ${STATUS_TAG[e.status]}`}>{e.status.replaceAll('_', ' ')}</span></td><td className="note">{e.requirement}<br />{e.implementation_evidence.map((p) => <code key={p} style={{ display: 'block' }}>{p}</code>)}</td><td className="note">{e.not_implemented}</td><td className="note">{e.next_step}</td></tr>)}</tbody>
      </table></div>
      <h3 style={{ marginTop: 32 }}>{r.framework.title}</h3>
      <p className="note">{T('maturity_scale')}: {Object.entries(r.maturity_scale).map(([k, v]) => `${k} ${v}`).join(' · ')}</p>
      <div className="tablewrap"><table className="ops">
        <thead><tr><th>{T('factor')}</th><th>{T('maturity')}</th><th>{T('evidence')}</th><th>{T('gap')}</th></tr></thead>
        <tbody>{r.factors.map((f) => <tr key={f.factor}><td><b>{f.factor}</b>{f.framework_statement && <div className="quote">“{f.framework_statement.quote}” <span className="note">p.{f.framework_statement.page}</span></div>}</td>
          <td className="mono">{f.maturity}/5<div className="note">{r.maturity_scale[f.maturity]}</div></td><td className="note">{f.justification}<br />{f.evidence.map((p) => <code key={p} style={{ display: 'block' }}>{p}</code>)}</td><td className="note">{f.gap}</td></tr>)}</tbody>
      </table></div>
      <details className="more"><summary>Requirements alignment: profile rules × enforcement × evidence × standards</summary>
        <div className="tablewrap"><table className="ops"><thead><tr><th>profile</th><th>rule</th><th>enforcement</th><th>evidence</th><th>standards</th></tr></thead>
          <tbody>{gov.requirements_alignment.map((a) => <tr key={a.profile + a.rule}><td className="mono">{a.profile}</td><td>{a.title}</td><td>{a.enforcement} · {a.enforced_by}</td><td>{a.evidence_status}</td><td>{a.standards.join(', ') || '—'}</td></tr>)}</tbody></table></div>
      </details>
    </div>
  );
}

function Validation({ suite, gov, T, scen }) {
  const sm = suite.summary; const tests = gov.tests.reduce((a, b) => a + b.tests, 0);
  return (
    <>
      <div className="stats" style={{ marginTop: 20 }}>
        <div className="stat"><b>{sm.passed}/{sm.scenarios}</b><span>scenarios with every expected behaviour observed</span></div>
        <div className="stat"><b>{sm.checks_passed}/{sm.checks}</b><span>pre-written checks observed</span></div>
        <div className="stat"><b>{tests}</b><span>test functions in {gov.tests.length} files (python -m pytest -q tests)</span></div>
        <div className="stat"><b>{gov.knowledge.documents}</b><span>documents in the knowledge-base manifest, {gov.knowledge.evidence_eligible} evidence-eligible</span></div>
      </div>
      <div className="grid g2" style={{ marginTop: 16 }}>
        <div className="panel"><h4>{T('tab_scenarios')}</h4><div className="tablewrap"><table className="ops"><tbody>{suite.scenarios.map((s) => <tr key={s.id}><td>{scen(s.id, s.title)}</td><td><Tag ok={s.passed}>{s.checks.filter((c) => c.passed).length}/{s.checks.length}</Tag></td><td className="mono note">{s.wall_s}s</td></tr>)}</tbody></table></div>
          <p className="note">Baselines in each scenario: Reactive greedy + guard and BRIDGE + guard with agents off, on the identical trace. Checksums: <code>{JSON.stringify(suite.checksums)}</code></p></div>
        <div className="panel" dir="ltr" lang="en"><h4>{T('test_suite')}</h4><div className="tablewrap"><table className="ops"><tbody>{gov.tests.map((t) => <tr key={t.file}><td className="mono">{t.file}</td><td className="mono">{t.tests}</td><td className="note">{t.about}</td></tr>)}</tbody></table></div>
          <p className="note">Counts are read from the test sources; they show coverage, not a test run.</p></div>
      </div>
      <div className="panel" style={{ marginTop: 12 }} dir="ltr" lang="en"><h4>Knowledge catalogue</h4><div className="tablewrap"><table className="ops"><tbody>{gov.knowledge.catalog.items.map((k) => <tr key={k.path}><td className="mono">{k.path}</td><td>{k.title}</td><td><span className="tag">{k.provenance}</span></td><td className="note">{k.consumed_by.join('; ')}</td></tr>)}</tbody></table></div>
        <ul className="note">{gov.knowledge.catalog.limitations.map((l) => <li key={l}>{l}</li>)}</ul></div>
    </>
  );
}

export default function Console({ d }) {
  const [lang, setLang] = useLang();
  const [tab, setTab] = useState('scenarios');
  const loc = d[`i18n_${lang}`] || d.i18n_en;
  const T = useMemo(() => (k) => loc.ui[k] ?? d.i18n_en.ui[k] ?? k, [loc, d]);
  const tr = useMemo(() => (k) => loc.terms[k] ?? d.i18n_en.terms[k] ?? k, [loc, d]);
  const scen = useMemo(() => (id, fb) => loc.scenarios[id] ?? fb, [loc]);
  const dir = loc._meta.dir;
  return (
    <section className="ch console" id="ops" dir={dir} lang={lang}><div className="wrap">
      <div className="ophead">
        <p className="kicker">{T('kicker')}</p>
        <div className="chips" role="group" aria-label={T('language')}>{LANGS.map(([k, n]) => <button key={k} lang={k} className={`chip ${k === lang ? 'on' : ''}`} onClick={() => setLang(k)} aria-pressed={k === lang}>{n}</button>)}</div>
      </div>
      <h2>{T('title')}</h2>
      <p className="lede">{T('lede')}</p>
      <p className="note">{loc._meta.review !== 'source language' ? `${loc._meta.language}: ${loc._meta.review}. ` : ''}{T('content_note')}</p>
      <div className="chips tabs" role="tablist" style={{ marginTop: 24 }}>{TABS.map((k) => <button key={k} role="tab" aria-selected={tab === k} className={`chip ${tab === k ? 'on' : ''}`} onClick={() => setTab(k)}>{T(`tab_${k}`)}</button>)}</div>
      {tab === 'scenarios' && <Scenarios suite={d.scenario_suite} T={T} tr={tr} lang={lang} scen={scen} />}
      {tab === 'agents' && <Agents gov={d.governance} T={T} />}
      {tab === 'policies' && <Policies gov={d.governance} T={T} tr={tr} />}
      {tab === 'standards' && <Standards gov={d.governance} T={T} />}
      {tab === 'validation' && <Validation suite={d.scenario_suite} gov={d.governance} T={T} scen={scen} />}
    </div></section>
  );
}
