// The digital twin's slot equations in JavaScript, so the game runs the same physics as digital_twin/environment.py.
// tests/test_game_physics.py replays recorded Python runs through this file and compares the results.

export function newState(p) {
  const init = p.rate[0].map((r) => r * p.init_backlog_ms);
  return { t: 0, qRt: init.map((k) => k * p.rt_share), qNrt: init.map((k) => k * (1 - p.rt_share)), history: [] };
}

export function step(s, p, lit, power) {
  const { t } = s;
  const N = lit.length;
  const rate = p.rate[t]; const gain = p.gain_db[t].map((g) => 10 ** (g / 10));
  const total = power.reduce((a, b, i) => a + (lit[i] ? b : 0), 0);
  const overhead = 1 - p.ssb_overhead * p.ssb[t] - p.sib_overhead * p.sib[t];
  const arrived = []; const served = []; const dropped = []; const cap = [];
  for (let c = 0; c < N; c++) {
    const arr = rate[c] * p.slot_ms;
    s.qRt[c] += arr * p.rt_share;
    s.qNrt[c] += arr * (1 - p.rt_share);
    const own = lit[c] ? power[c] : 0;
    const sinr = lit[c] ? (own * gain[c] * p.gain_lin) / (p.noise_w + p.eps * p.gain_lin * gain[c] * (total - own)) : 0;
    const mbps = sinr >= p.sinr_min && p.los[t][c] > 0 ? (p.bw_hz * Math.log2(1 + sinr) * overhead) / 1e6 : 0;
    const capKb = mbps * p.slot_ms;
    const srvRt = Math.min(s.qRt[c], capKb);
    const srvNrt = Math.min(s.qNrt[c], capKb - srvRt);
    s.qRt[c] -= srvRt; s.qNrt[c] -= srvNrt;
    const dropRt = Math.max(s.qRt[c] - p.buffer_rt, 0); const dropNrt = Math.max(s.qNrt[c] - p.buffer_nrt, 0);
    s.qRt[c] -= dropRt; s.qNrt[c] -= dropNrt;
    arrived.push(arr); served.push(srvRt + srvNrt); dropped.push(dropRt + dropNrt); cap.push(mbps);
  }
  const rateSum = Math.max(rate.reduce((a, b) => a + b, 0), 1e-6);
  const qSum = s.qRt.reduce((a, b) => a + b, 0) + s.qNrt.reduce((a, b) => a + b, 0);
  let over = 0;
  for (let c = 0; c < N; c++) if (s.qRt[c] / Math.max(rate[c] * p.rt_share, 1e-6) > p.rt_budget) over++;
  const rec = { t, arrived, served, dropped, cap, delay: qSum / rateSum, rtViolation: over / N, throughput: served.reduce((a, b) => a + b, 0) / p.slot_ms };
  s.history.push(rec);
  s.t += 1;
  return rec;
}

/** Equal split across picked cells, then the same test limit the agents enforce from slot 50, excess moved to other beams. */
export function playerPower(cells, t, p) {
  const power = new Array(p.rate[0].length).fill(0);
  if (!cells.length) return power;
  let free = [...cells]; let budget = p.pmax;
  if (t >= p.cap_slot) {
    const capped = cells.filter((c) => p.border_cells.includes(c));
    capped.forEach((c) => { const w = Math.min(p.cap_w, p.pmax / cells.length); power[c] = w; budget -= w; });
    free = cells.filter((c) => !capped.includes(c));
    if (!free.length) return power;                                // nowhere to move the excess: it is not transmitted
  }
  free.forEach((c) => { power[c] = budget / free.length; });
  return power;
}

export function score(hist, p) {
  const em = p.emergency_cells;
  let arr = 0; let srv = 0;
  hist.forEach((h) => { if (h.t >= p.emergency_from && h.t < p.emergency_to) em.forEach((c) => { arr += h.arrived[c]; srv += h.served[c]; }); });
  const mean = (f) => hist.reduce((a, h) => a + f(h), 0) / Math.max(hist.length, 1);
  return { emergency: srv / Math.max(arr, 1e-9), late: mean((h) => h.rtViolation), delay: mean((h) => h.delay), throughput: mean((h) => h.throughput) };
}

/** Re-run a recorded controller through the same equations, so both players are scored identically. */
export function simulateRecorded(run, p) {
  const s = newState(p);
  const N = p.rate[0].length;
  for (let t = 0; t < p.rate.length; t++) {
    const lit = new Array(N).fill(false);
    run.lit[t].forEach((c) => { lit[c] = true; });
    step(s, p, lit, run.power[t]);
  }
  return s.history;
}
