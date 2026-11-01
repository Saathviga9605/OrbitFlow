"""Multi-run evaluation matrix. Every policy gets the SAME episode per seed, so all comparisons are paired.

    python scripts/run_experiments.py [--n 100] [--tag final] [--workers 14]
Writes results/multirun.json. Fresh test seeds start at 50000, disjoint from the train/val/test split seeds (1000-5119).
BRIDGE rows average over training seeds per episode, so the spread from re-training is part of the result (also reported).
"""
from __future__ import annotations

import argparse
import copy
import glob
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from utils.config import REAL_TRACE, load_config  # noqa: E402
from utils.stats import effect_label, holm, paired, summary  # noqa: E402

KPIS = ["throughput_mbps", "served_ratio", "packet_loss", "mean_delay_ms", "p95_delay_ms", "rt_sla_violation", "jain_fairness",
        "mean_sinr_db", "beam_switches_per_slot", "energy_j", "guard_violation_slots", "guard_repairs"]
SPECS = {
    # name: (base, n_multiplier, perturbation)
    **{f"kind:{k}": dict(kind=k) for k in ("normal", "block", "event_surge", "bursty", "mixed")},
    "pass:dynamic_ntn": dict(pass_="dynamic"),
    "pass:openntn_sionna": dict(pass_="openntn"),
    **{f"intensity:{s}": dict(pass_="dynamic", scale=s) for s in (0.5, 0.75, 1.25, 1.5)},
    **{f"channel:{c:+d}dB": dict(pass_="dynamic", channel=c) for c in (-6, -3, 3)},
    **{f"outage:{o}": dict(pass_="dynamic", outage=o) for o in (0.1, 0.25)},
    **{f"pass_shift:{s}": dict(pass_="dynamic", shift=s) for s in (-20, 20)},
    **{f"init_backlog:{b}ms": dict(pass_="dynamic", backlog=b) for b in (5, 50)},
}
_W: dict = {}


def _init(tag, gate):
    import torch
    from bridge.baselines import ReactiveGreedy, StaticRoundRobin
    from bridge.policy import BridgePolicy, HeuristicPredictive
    from traffic.dataset import load_openntn_sionna, load_trace
    from traffic.forecaster import Forecaster
    torch.set_num_threads(1)
    cfg = load_config()
    cfg["predictor"]["gate"] = gate
    m = os.path.join(ROOT, "models", "exp")
    pols = {"Static round-robin": StaticRoundRobin(19, 4, 100.0), "Reactive greedy": ReactiveGreedy(19, 4, 100.0), "Heuristic-predictive": HeuristicPredictive(cfg)}
    groups = {"BC": sorted(glob.glob(os.path.join(m, f"bridge_bc_{tag}_s*.pt"))),
              "BRIDGE": sorted(glob.glob(os.path.join(m, f"bridge_ppo_{tag}_s*.pt"))),
              "BRIDGE no-forecast": sorted(glob.glob(os.path.join(m, f"bridge_ppo_{tag}nf_s*.pt")))}
    _W.update(cfg=cfg, pols=pols, base=load_trace(REAL_TRACE), alt=load_openntn_sionna(ROOT), fc=Forecaster.load(cfg, os.path.join(ROOT, "models", "traffic_predictor.pt")),
              seeded={g: [BridgePolicy(cfg, f, use_forecast=g != "BRIDGE no-forecast", name=g) for f in fs] for g, fs in groups.items()})


def build_trace(spec: dict, seed: int):
    from traffic.generator import make_trace
    rng = np.random.default_rng(seed)
    base = _W["alt"] if spec.get("pass_") == "openntn" else _W["base"]
    if "kind" in spec:
        t = make_trace(spec["kind"], _W["base"], seed)
    else:
        t = copy.deepcopy(base)                                        # real demand profile, small measurement noise + fading draw
        t.rate = np.maximum(t.rate * (1 + 0.03 * rng.standard_normal(t.rate.shape)), 0.1)
        t.gain = t.gain * 10 ** (1.0 * rng.standard_normal(t.gain.shape) / 10)
    if spec.get("scale"):
        t.rate = t.rate * spec["scale"]
    if spec.get("channel"):
        t.gain = t.gain * 10 ** (spec["channel"] / 10)
    if spec.get("outage"):
        t.los = t.los * (rng.random(t.los.shape) > spec["outage"])
    if spec.get("shift"):
        for f in ("gain", "los", "elev"):
            setattr(t, f, np.roll(getattr(t, f), spec["shift"], axis=0))
    return t


def run_task(args):
    from bridge.evaluate import run_episode
    from traffic.forecaster import prepare_forecast
    name, spec, seed = args
    cfg = copy.deepcopy(_W["cfg"])
    cfg["queues"]["init_backlog_ms"] = spec.get("backlog") or cfg["queues"]["init_backlog_ms"]
    t = build_trace(spec, seed)
    t.forecast = prepare_forecast(_W["fc"], t, cfg)
    row = {n: _kpis(run_episode(t, cfg, p)) for n, p in _W["pols"].items()}
    per_seed = {}
    for g, ps in _W["seeded"].items():
        rs = [_kpis(run_episode(t, cfg, p)) for p in ps]
        if rs:
            row[g] = {k: float(np.mean([r[k] for r in rs])) for k in KPIS}
            per_seed[g] = [r["rt_sla_violation"] for r in rs], [r["mean_delay_ms"] for r in rs]
    return name, seed, row, per_seed


def _kpis(r):
    return {k: float(r.get(k, np.nan)) for k in KPIS}


def main(n=100, tag="final", workers=14, gate=False):
    tasks = [(name, spec, 50000 + i) for name, spec in SPECS.items() for i in range(n if name.startswith(("kind", "pass:")) else max(n // 2, 2))]
    results: dict = {}
    seeds_rt: dict = {}
    with ProcessPoolExecutor(workers, initializer=_init, initargs=(tag, gate)) as ex:
        for name, seed, row, ps in ex.map(run_task, tasks, chunksize=8):
            results.setdefault(name, []).append(row)
            for g, (rt, dl) in ps.items():
                seeds_rt.setdefault(name, {}).setdefault(g, {"rt": [], "delay": []})
                seeds_rt[name][g]["rt"].append(rt)
                seeds_rt[name][g]["delay"].append(dl)
    out = {"meta": {"episodes_kinds_and_passes": n, "episodes_other_conditions": max(n // 2, 2), "first_seed": 50000, "training_seeds": len(next(iter(seeds_rt.values()))["BRIDGE"]["rt"][0]),
                    "rationale": "n chosen so the 95% CI half-width on RT-miss difference is small next to the effect (see ci_halfwidth). Episodes are paired across policies.",
                    "correction": "Holm over the policies compared per condition and KPI."}, "conditions": {}}
    for name, rows in results.items():
        pols = list(rows[0])
        cond = {"policies": {p: {k: summary([r[p][k] for r in rows]) for k in KPIS} for p in pols}, "vs_reactive": {}, "vs_bridge_nf": {}, "vs_bc": {}}
        for k in ("rt_sla_violation", "mean_delay_ms", "p95_delay_ms", "throughput_mbps", "packet_loss", "beam_switches_per_slot"):
            cmp = {p: paired([r[p][k] for r in rows], [r["Reactive greedy"][k] for r in rows]) for p in pols if p != "Reactive greedy"}
            adj = holm({p: c["p"] for p, c in cmp.items()})
            for p, c in cmp.items():
                c["p_holm"] = adj.get(p)
                c["effect"] = effect_label(c["rank_biserial"])
            cond["vs_reactive"][k] = cmp
            if "BRIDGE no-forecast" in pols:
                cond["vs_bridge_nf"][k] = paired([r["BRIDGE"][k] for r in rows], [r["BRIDGE no-forecast"][k] for r in rows])
                cond["vs_bc"][k] = paired([r["BRIDGE"][k] for r in rows], [r["BC"][k] for r in rows])
        s = seeds_rt.get(name, {}).get("BRIDGE")
        if s:
            cond["bridge_across_training_seeds"] = {"rt_miss": np.mean(s["rt"], axis=0).round(5).tolist(), "delay_ms": np.mean(s["delay"], axis=0).round(3).tolist()}
        s = seeds_rt.get(name, {}).get("BRIDGE no-forecast")
        if s:
            cond["nf_across_training_seeds"] = {"rt_miss": np.mean(s["rt"], axis=0).round(5).tolist(), "delay_ms": np.mean(s["delay"], axis=0).round(3).tolist()}
        out["conditions"][name] = cond
        p = cond["policies"]
        print(name, {x: (round(p[x]["rt_sla_violation"]["mean"], 4), round(p[x]["mean_delay_ms"]["mean"], 1)) for x in p}, flush=True)
    json.dump(out, open(os.path.join(ROOT, "results", "multirun.json"), "w"), indent=1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--tag", default="final")
    ap.add_argument("--workers", type=int, default=14)
    ap.add_argument("--gate", action="store_true")
    a = ap.parse_args()
    main(a.n, a.tag, a.workers, a.gate)
