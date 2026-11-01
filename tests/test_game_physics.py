"""The game's JavaScript twin must reproduce recorded Python runs, or the score would be unfair."""
import json
import os
import shutil
import subprocess

import pytest

from utils.config import ROOT

SCRIPT = """
import fs from 'fs';
import { score, simulateRecorded } from './dashboard/frontend/src/physics.js';
const r = JSON.parse(fs.readFileSync('results/flood_replay.json', 'utf8').replace(/\\bNaN\\b/g, 'null'));
const out = {};
for (const [n, run] of Object.entries(r.runs)) {
  const h = simulateRecorded(run.series, r.phys);
  out[n] = { throughput: h.map((x) => x.throughput), delay: h.map((x) => x.delay), score: score(h, r.phys) };
}
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_js_twin_matches_recorded_python_runs(tmp_path):
    path = os.path.join(ROOT, "_physics_check.mjs")
    with open(path, "w") as f:
        f.write(SCRIPT)
    try:
        out = json.loads(subprocess.check_output(["node", path], cwd=ROOT, text=True))
    finally:
        os.remove(path)
    rec = json.load(open(os.path.join(ROOT, "results", "flood_replay.json")))
    for name, run in rec["runs"].items():
        # watts are stored to 0.1 W in the replay, so small differences are expected
        tp = abs(sum(out[name]["throughput"]) / 100 - run["kpis"]["throughput_mbps"])
        dl = abs(sum(out[name]["delay"]) / 100 - run["kpis"]["mean_delay_ms"])
        assert tp < 0.5 and dl < 0.5, (name, tp, dl)
        assert abs(out[name]["score"]["late"] - run["kpis"]["rt_sla_violation"]) < 0.01
