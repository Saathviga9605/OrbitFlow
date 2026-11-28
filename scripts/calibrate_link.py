"""Link calibration sweep for the 58-cell dataset (results/link_calibration.json).

    python scripts/calibrate_link.py
For each candidate beam bandwidth, runs the reactive and static baselines (guard in the loop) on
the recorded pass, the flood storyline and synthetic normal traffic, and reports demand served,
late time-critical data and SINR. The chosen value and the reason are recorded in config.yaml and
docs/link_budget_parameters.md. No learned model is involved, so the choice cannot favour BRIDGE.
"""
from __future__ import annotations

import copy
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.baselines import ReactiveGreedy, StaticRoundRobin  # noqa: E402
from bridge.evaluate import run_episode  # noqa: E402
from digital_twin.channel import LinkModel  # noqa: E402
from scenarios.flood_relief import build  # noqa: E402
from traffic.dataset import load_trace  # noqa: E402
from traffic.generator import make_trace  # noqa: E402
from utils.config import REAL_TRACE, ROOT, load_config  # noqa: E402


def main():
    base_cfg = load_config()
    base = load_trace(REAL_TRACE)
    s = base_cfg["scenario"]
    out = {"note": "Baselines only. served = served/arrived; late = RT SLA violation share.", "rows": []}
    los = base.los > 0
    out["demand_share_on_los_cells"] = float((base.rate * los).sum() / base.rate.sum())
    for bw in (40.0, 60.0, 80.0, 100.0, 120.0):
        for req in (False,):
            cfg = copy.deepcopy(base_cfg)
            cfg["link"]["bandwidth_mhz"] = bw
            cfg["link"]["require_los"] = req
            link = LinkModel(cfg)
            p_eq = s["p_max_w"] / s["k_beams"]
            snr = p_eq * base.gain * link.gain_lin / link.noise_w
            row = {"bandwidth_mhz": bw, "require_los": req,
                   "snr_db_los_median": float(10 * np.log10(np.median(snr[los]))),
                   "snr_db_nlos_median": float(10 * np.log10(np.median(snr[~los]))),
                   "nlos_decodable_share": float((snr[~los] >= link.sinr_min).mean())}
            traces = {"pass": base, "flood": build(base, None, 42)[0], "normal": make_trace("normal", base, 101), "event_surge": make_trace("event_surge", base, 202)}
            for name, tr in traces.items():
                for pname, pol in (("reactive", ReactiveGreedy(s["n_cells"], s["k_beams"], s["p_max_w"])), ("static", StaticRoundRobin(s["n_cells"], s["k_beams"], s["p_max_w"]))):
                    k = run_episode(tr, cfg, pol)
                    row[f"{name}.{pname}"] = {m: round(float(k[m]), 4) for m in ("served_ratio", "rt_sla_violation", "mean_delay_ms", "throughput_mbps", "demand_mbps", "mean_sinr_db")}
            out["rows"].append(row)
            print(bw, req, {k: (v if not isinstance(v, dict) else (v["served_ratio"], v["rt_sla_violation"], round(v["mean_delay_ms"], 1))) for k, v in row.items() if k not in ("bandwidth_mhz", "require_los")})
    json.dump(out, open(os.path.join(ROOT, "results", "link_calibration.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
