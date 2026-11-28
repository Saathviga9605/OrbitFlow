"""Where does late time-critical data come from at 58 cells? Splits RT lateness into cell-slots that could have
been served (the cell had line of sight at some point within the RT budget window) and those that could not.

    python scripts/diagnose_late.py
"""
from __future__ import annotations

import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.baselines import ReactiveGreedy, StaticRoundRobin  # noqa: E402
from bridge.evaluate import run_episode  # noqa: E402
from bridge.policy import BridgePolicy, HeuristicPredictive  # noqa: E402
from traffic.dataset import load_trace  # noqa: E402
from traffic.forecaster import Forecaster, prepare_forecast  # noqa: E402
from traffic.generator import make_trace  # noqa: E402
from utils.config import REAL_TRACE, ROOT, load_config  # noqa: E402


def split_late(trace, hist, cfg):
    q = cfg["queues"]
    win = int(q["rt_delay_budget_ms"] / trace.slot_ms)
    T, N = trace.rate.shape
    late = np.zeros((T, N), bool)
    for t, h in enumerate(hist):
        age = h["q_rt"] / np.maximum(trace.rate[t] * q["rt_share"], 1e-6)
        late[t] = age > q["rt_delay_budget_ms"]
    los = trace.los > 0
    servable = np.zeros((T, N), bool)
    for t in range(T):
        servable[t] = los[max(0, t - win + 1):t + 1].any(axis=0)
    return {"late_all": float(late.mean()), "late_when_servable": float(late[servable].mean()),
            "late_when_unservable": float(late[~servable].mean()) if (~servable).any() else 0.0,
            "servable_share": float(servable.mean()), "unavoidable_share_of_late": float((late & ~servable).sum() / max(late.sum(), 1))}


def main():
    cfg = load_config()
    s = cfg["scenario"]
    base = load_trace(REAL_TRACE)
    fc = Forecaster.load(cfg, os.path.join(ROOT, "models", "traffic_predictor.pt"))
    ck = sorted(glob.glob(os.path.join(ROOT, "models", "exp", "bridge_ppo_rg_s*.pt")))[2]
    cknf = sorted(glob.glob(os.path.join(ROOT, "models", "exp", "bridge_ppo_rgnf_s*.pt")))[2]
    pols = {"static": StaticRoundRobin(s["n_cells"], s["k_beams"], s["p_max_w"]), "reactive": ReactiveGreedy(s["n_cells"], s["k_beams"], s["p_max_w"]),
            "heuristic": HeuristicPredictive(cfg), "bridge": BridgePolicy(cfg, ck), "bridge_nf": BridgePolicy(cfg, cknf, use_forecast=False)}
    for kind in ("normal", "event_surge", "pass"):
        rows = {n: [] for n in pols}
        for i in range(20):
            tr = base if kind == "pass" else make_trace(kind, base, 50000 + i)
            tr.forecast = prepare_forecast(fc, tr, cfg)
            for n, p in pols.items():
                k = run_episode(tr, cfg, p, keep_records=True)
                rows[n].append(split_late(tr, k["history"], cfg))
            if kind == "pass":
                break
        print(kind)
        for n, r in rows.items():
            m = {key: np.mean([x[key] for x in r]) for key in r[0]}
            print(f"  {n:<10} late_all {m['late_all']*100:5.2f}%  late|servable {m['late_when_servable']*100:5.2f}%  late|unservable {m['late_when_unservable']*100:5.2f}%  servable {m['servable_share']*100:4.1f}%  unavoidable/late {m['unavoidable_share_of_late']*100:4.1f}%")


if __name__ == "__main__":
    main()
