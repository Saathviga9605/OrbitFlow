import React, { useState } from 'react';
import { reducedMotion, useWidth } from './viz.jsx';
import { useI18n } from './i18n.jsx';

// Interactive flowchart of the decision loop. Roles and permissions come from agents/registry.yaml
// (results/governance.json); latencies from results/studies/latency.json.

const NODES = [
  // id, label, tech, x, y, kind, registry id, latency key, role, code
  ['telemetry', 'Telemetry', 'one slot late', 80, 230, 'data', null, null, 'Demand, queues and channel state from the twin, one 10 ms slot old. Geometry and signalling timing are known exactly.', 'digital_twin/environment.py'],
  ['validator', 'Validate', 'NaN · stale', 235, 230, 'component', 'data_validator', null, 'Bad or stale reports get their last good value; too much bad data switches the slot to conservative mode.', 'agents/supervisor.py · _validate_obs'],
  ['forecaster', 'Forecast', 'GRU + gate', 390, 230, 'component', 'forecaster', null, 'Predicts each cell three slots ahead. Falls back to repeat-last when its recent error is high. Leak-tested.', 'traffic/forecaster.py'],
  ['network', 'Decide', 'BRIDGE · PPO', 545, 230, 'agent', 'network', 'network', 'Scores every cell, picks 4 beams and splits 100 W. Proposes only; it cannot execute.', 'bridge/policy.py'],
  ['fallback', 'Fallback planner', 'reactive greedy', 545, 385, 'component', null, null, 'Takes over when the Network agent crashes, returns malformed output or times out. No model, no forecast.', 'agents/registry.py · build_fallback'],
  ['kb', 'Knowledge base', '69 docs · BM25', 545, 75, 'data', null, null, 'Evidence is retrieved once at start-up, so reading documents never slows a decision. Quotes must be verbatim.', 'rag/retriever.py'],
  ['policy', 'Policy agent', 'rules + evidence', 745, 75, 'agent', 'policy', 'policy', 'Checks the proposal against operating constraints and returns verdicts with citations. Fails closed if unavailable.', 'agents/supervisor.py · PolicyAgent'],
  ['profile', 'Policy profile', 'per country', 945, 75, 'data', null, null, 'Cap, emergency exemption, escalation and fail-safe values for one context. Changing it never touches the model.', 'policy/profiles/*.yaml'],
  ['safety', 'Safety agent', 'emergency first', 745, 385, 'agent', 'safety', 'safety', 'Requires emergency cells to be lit when their data starts to age. Watches starvation and power concentration.', 'agents/supervisor.py · SafetyAgent'],
  ['supervisor', 'Supervisor', 'resolve · escalate', 745, 230, 'agent', 'supervisor', null, 'Detects and types conflicts, applies fallbacks and resolves by fixed precedence: limits > constraints > safety > optimisation.', 'agents/supervisor.py · Supervisor'],
  ['guard', 'Guard', 'hard limits', 945, 230, 'component', 'guard', 'guard', 'Enforces beam count, power budget, floors, signalling deadlines and caps. Raw model output never reaches the network.', 'bam/validator.py'],
  ['audit', 'Audit + review', 'every slot', 945, 385, 'data', null, 'audit', 'Records what was proposed, what ran, conflicts and sources. Conflicts and failures go to a human review queue.', 'audit/ · results/human_review_queue.jsonl'],
  ['twin', 'Execute', 'digital twin', 1100, 230, 'data', null, null, 'Queues, interference-aware SINR and KPIs. Simulation only: nothing here touches a real satellite.', 'digital_twin/'],
];
const EDGES = [
  ['telemetry', 'validator'], ['validator', 'forecaster'], ['forecaster', 'network'], ['network', 'supervisor'],
  ['fallback', 'supervisor', 'dash'], ['kb', 'policy'], ['profile', 'policy'], ['profile', 'supervisor'],
  ['policy', 'supervisor'], ['safety', 'supervisor'], ['supervisor', 'guard'], ['guard', 'twin'], ['guard', 'audit'], ['supervisor', 'audit'],
];
const KIND = { agent: 'var(--beam)', component: 'var(--bridge)', data: 'var(--ink-3)' };

export default function Flow({ d }) {
  const { t } = useI18n();
  const [box, w] = useWidth();
  const vertical = w < 640;
  const [sel, setSel] = useState('network');
  const W = vertical ? 470 : 1180; const H = vertical ? 1180 : 520;
  const nw = vertical ? 132 : 140; const nh = 56;
  const col = { 75: 400, 230: 235, 385: 70 };
  const P = Object.fromEntries(NODES.map((n) => [n[0], vertical ? { x: col[n[4]], y: n[3] } : { x: n[3], y: n[4] }]));
  const node = NODES.find((n) => n[0] === sel);
  const reg = d.governance?.registry?.find((r) => r.id === node[6]);
  const lat = node[7] && d.study_latency.stages[node[7]];
  const anchor = (a, b) => {
    const A = P[a]; const B = P[b]; const dx = B.x - A.x; const dy = B.y - A.y;
    const out = (p, s) => (Math.abs(dx) * nh > Math.abs(dy) * nw ? { x: p.x + s * Math.sign(dx) * nw / 2, y: p.y } : { x: p.x, y: p.y + s * Math.sign(dy) * nh / 2 });
    return [out(A, 1), out(B, -1)];
  };
  const main = vertical ? `M${P.telemetry.x},${P.telemetry.y} L${P.twin.x},${P.twin.y}` : `M${P.telemetry.x},${P.telemetry.y} L${P.twin.x},${P.twin.y}`;
  const loop = vertical
    ? `M${P.twin.x + nw / 2},${P.twin.y} C${W - 6},${P.twin.y} ${W - 6},${P.telemetry.y} ${P.telemetry.x + nw / 2},${P.telemetry.y}`
    : `M${P.twin.x},${P.twin.y + nh / 2} C${P.twin.x},${H + 40} ${P.telemetry.x},${H + 40} ${P.telemetry.x},${P.telemetry.y + nh / 2}`;
  const still = reducedMotion();
  // squeeze a label into the node only when its estimated width would overflow (long Tamil/Hindi words)
  const fit = (txt, size, perChar) => (txt.length * perChar > nw - 20 ? { textLength: nw - 20, lengthAdjust: 'spacingAndGlyphs' } : {});
  return (
    <div className="flow" ref={box}>
      <svg dir="ltr" viewBox={`0 0 ${W} ${H}`} className="flow-svg" role="group" aria-label={t('flow.aria')}>
        <defs><marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="currentColor" /></marker></defs>
        {!vertical && <path d={loop} className="edge loop" markerEnd="url(#arr)" />}
        {!vertical && <text x={(P.telemetry.x + P.twin.x) / 2} y={H - 12} className="edge-label">{t('flow.next')}</text>}
        {EDGES.map(([a, b, dash]) => {
          const [s, e] = anchor(a, b); const on = sel === a || sel === b;
          return <line key={a + b} x1={s.x} y1={s.y} x2={e.x} y2={e.y} className={`edge ${on ? 'on' : ''} ${dash ? 'dash' : ''}`} markerEnd="url(#arr)" />;
        })}
        {!still && <>
          <circle r="5" className="packet"><animateMotion dur="5s" repeatCount="indefinite" path={main} /></circle>
          {!vertical && <circle r="4" className="packet ret"><animateMotion dur="5s" begin="2.5s" repeatCount="indefinite" path={loop} /></circle>}
        </>}
        {NODES.map(([id, , , , , kind]) => {
          const p = P[id];
          return (
            <g key={id} className={`node ${sel === id ? 'on' : ''} k-${kind}`} transform={`translate(${p.x - nw / 2},${p.y - nh / 2})`} onClick={() => setSel(id)}
              tabIndex={0} role="button" aria-pressed={sel === id} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && setSel(id)}>
              <rect width={nw} height={nh} rx="6" />
              <rect width="3" height={nh} rx="1.5" fill={KIND[kind]} />
              <text x="13" y="24" className="n-label" {...fit(t(`node.${id}`), 15, 8.4)}>{t(`node.${id}`)}</text>
              <text x="13" y="42" className="n-tech" {...fit(t(`node.${id}.tech`), 11.5, 7)}>{t(`node.${id}.tech`)}</text>
            </g>
          );
        })}
      </svg>
      <aside className="flow-detail" aria-live="polite">
        <p className="kicker" style={{ color: KIND[node[5]] }}>{t(`flow.kind.${node[5]}`)}</p>
        <h3>{t(`node.${node[0]}`)}</h3>
        <p>{t(`node.${node[0]}.role`, { k: d.flood_replay.phys.k, w: d.flood_replay.phys.pmax })}</p>
        {lat && <p className="flow-lat"><b className="mono">{lat.mean.toFixed(2)} ms</b> {t('flow.mean')} · {lat.p99.toFixed(2)} ms p99</p>}
        {reg && <dl>
          <dt>{t('flow.can')}</dt><dd lang="en">{reg.allowed_actions.join(' · ')}</dd>
          <dt>{t('flow.cannot')}</dt><dd lang="en">{reg.prohibited_actions.join(' · ')}</dd>
          {reg.fallback && <><dt>{t('flow.fails')}</dt><dd className="mono">{reg.fallback}</dd></>}
        </dl>}
        <code dir="ltr">{node[9]}</code>
      </aside>
    </div>
  );
}
