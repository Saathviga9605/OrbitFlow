"""Full evaluation: every number the UI shows is produced here from the held-out test split.

    python scripts/run_eval.py [--fast]
Writes results/{kpi_table,flood_mc,whatif_grid,flood_replay,kb_report,gaps}.json, results/audit/demo.jsonl,
results/human_review_queue.jsonl and copies the web bundle to dashboard/frontend/public/data.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time

import numpy as np
import torch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agents.supervisor import Supervisor  # noqa: E402
from audit.logger import AuditLogger, _clean  # noqa: E402
from bridge.baselines import LoggedPolicy, ReactiveGreedy, StaticRoundRobin  # noqa: E402
from bridge.evaluate import run_episode  # noqa: E402
from bridge.policy import BridgePolicy, HeuristicPredictive  # noqa: E402
from rag.retriever import KnowledgeBase  # noqa: E402
from scenarios.flood_relief import build  # noqa: E402
from traffic.dataset import load_trace  # noqa: E402
from traffic.forecaster import Forecaster, prepare_forecast  # noqa: E402
from traffic.generator import make_trace  # noqa: E402
from traffic.splits import create_splits  # noqa: E402
from utils.config import REAL_TRACE, load_config  # noqa: E402

KPIS = ["throughput_mbps", "served_ratio", "packet_loss", "mean_delay_ms", "p95_delay_ms", "rt_sla_violation",
        "jain_fairness", "mean_sinr_db", "beam_switches_per_slot", "guard_violation_slots"]
LOWER_BETTER = {"packet_loss", "mean_delay_ms", "p95_delay_ms", "rt_sla_violation", "beam_switches_per_slot", "guard_violation_slots"}
RESULTS = os.path.join(ROOT, "results")


def bootstrap(v, seed=0, n=2000):
    v = np.asarray(v, float)
    if len(v) < 2:
        return {"mean": float(v.mean()), "lo": float(v.mean()), "hi": float(v.mean()), "n": len(v)}
    r = np.random.default_rng(seed)
    m = v[r.integers(len(v), size=(n, len(v)))].mean(1)
    return {"mean": float(v.mean()), "lo": float(np.percentile(m, 2.5)), "hi": float(np.percentile(m, 97.5)), "n": len(v)}


def sign_test(a, b, lower_better):
    """Two-sided exact sign test of a vs b on paired episodes."""
    from math import comb
    d = (np.asarray(a) - np.asarray(b)) * (-1 if lower_better else 1)
    w, l = int((d > 1e-9).sum()), int((d < -1e-9).sum())
    n = w + l
    p = 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(0, min(w, l) + 1)) / 2 ** n)
    return {"wins": w, "losses": l, "ties": len(d) - n, "p": p}


def policies(cfg, N):
    K, P = cfg["scenario"]["k_beams"], cfg["scenario"]["p_max_w"]
    m = lambda f: os.path.join(ROOT, "models", f)
    return {
        "Static round-robin": lambda: StaticRoundRobin(N, K, P),
        "Reactive greedy": lambda: ReactiveGreedy(N, K, P),
        "Heuristic-predictive": lambda: HeuristicPredictive(cfg),
        "BRIDGE": lambda: BridgePolicy(cfg, m("bridge_ppo.pt")),
    }


def kpi_table(cfg, fc, base, fast):
    mf = create_splits(n_per_kind=12 if fast else 120, random_seed=cfg["seed"])
    out = {"meta": {"test_episodes_per_kind": int(len(mf.test_episodes) / len(mf.scenario_kinds)),
                    "note": "Mean and 95% bootstrap CI over held-out episodes. p is an exact sign test against Reactive greedy."},
           "scenarios": {}}
    pols = policies(cfg, base.N)
    for kind in mf.scenario_kinds:
        traces = [make_trace(e["kind"], base, e["seed"]) for e in mf.test_episodes if e["kind"] == kind]
        for t in traces:
            t.forecast = fc.predict_trace(t, 1)
        raw = {}
        for name, mk in pols.items():
            p = mk()
            raw[name] = [run_episode(t, cfg, p) for t in traces]
        row = {}
        for name, runs in raw.items():
            row[name] = {k: bootstrap([r[k] for r in runs]) for k in KPIS}
            if name != "Reactive greedy":
                row[name]["vs_reactive"] = {k: sign_test([r[k] for r in runs], [r[k] for r in raw["Reactive greedy"]], k in LOWER_BETTER) for k in KPIS}
        out["scenarios"][kind] = row
        print(kind, {n: (round(row[n]["mean_delay_ms"]["mean"], 1), round(row[n]["rt_sla_violation"]["mean"], 3)) for n in row}, flush=True)
    real = base
    real.forecast = fc.predict_trace(real, 1)
    row = {}
    for name, mk in pols.items():
        row[name] = {k: bootstrap([run_episode(real, cfg, mk())[k]]) for k in KPIS}
    row["Logged rule-based (non-causal)"] = {k: bootstrap([run_episode(real, cfg, LoggedPolicy(real))[k]]) for k in KPIS}
    out["scenarios"]["real_trace"] = row
    return out


def flood_run(cfg, fc, base, kb, make_policy, agents_on, seed=42, overrides=None):
    trace, feed = build(base, overrides, seed)
    trace.forecast = prepare_forecast(fc, trace, cfg)
    return trace, feed, Supervisor(cfg, make_policy(), feed, kb, agents_on=agents_on).run(trace)


def series(trace, r):
    """Per-slot data for the replay, rounded for a small web payload."""
    H = r["history"]
    return {"lit": [np.where(h["lit"])[0].tolist() for h in H],
            "power": np.round([h["power"] for h in H], 1).tolist(),
            "q_rt": np.round([h["q_rt"] for h in H], 0).tolist(),
            "q_nrt": np.round([h["q_nrt"] for h in H], 0).tolist(),
            "sinr": np.round(np.clip([h["sinr_db"] for h in H], -30, 40), 1).tolist(),
            "cap": np.round([h["cap_mbps"] for h in H], 1).tolist(),
            "throughput": np.round([h["throughput_mbps"] for h in H], 1).tolist(),
            "delay": np.round([h["delay_ms"] for h in H], 1).tolist(),
            "rt_violation": np.round([h["rt_violation"] for h in H], 3).tolist()}


def cell_coords():
    import pandas as pd
    df = pd.read_csv(os.path.join(ROOT, "data", "raw", "sionna_physics_output.csv"))
    df = df[df.slot_id == df.slot_id.min()].sort_values("cell_id")
    return [{"x": float(x), "y": float(y)} for x, y in zip(df.cell_x_m, df.cell_y_m)]


def main(fast=False):
    cfg = load_config()
    torch.manual_seed(cfg["seed"])
    np.random.seed(cfg["seed"])
    torch.set_num_threads(2)
    base = load_trace(REAL_TRACE)
    fc = Forecaster.load(cfg, os.path.join(ROOT, "models", "traffic_predictor.pt"))
    kb = KnowledgeBase(cfg)
    N = base.N
    pols = policies(cfg, N)
    bridge, reactive, static = pols["BRIDGE"], pols["Reactive greedy"], pols["Static round-robin"]


    # Latency of the decision path, measured on this machine
    trace, feed = build(base)
    t0 = time.perf_counter()
    trace.forecast = fc.predict_trace(trace, 1)
    fc_ms = (time.perf_counter() - t0) * 1000 / trace.T
    p = bridge()
    from digital_twin.environment import NTNTwin
    tw = NTNTwin(trace, cfg)
    o = tw.reset()
    t0 = time.perf_counter()
    for _ in range(100):
        p.act(o)
    br_ms = (time.perf_counter() - t0) * 10
    latency = {"forecast_ms": fc_ms, "bridge_ms": br_ms, "slot_ms": cfg["scenario"]["slot_ms"]}

    # The storyline, one controller each, same demand
    controllers = {"Static round-robin": (static, False), "Reactive greedy": (reactive, False),
                   "BRIDGE alone": (bridge, False), "OrbitFlow": (bridge, True)}
    runs = {n: flood_run(cfg, fc, base, kb, mk, on) for n, (mk, on) in controllers.items()}
    trace, feed, full = runs["OrbitFlow"]
    log = AuditLogger(os.path.join(RESULTS, "audit", "demo.jsonl"))
    log.clear()
    for rec in full["records"]:
        log.write(rec)
    with open(os.path.join(RESULTS, "human_review_queue.jsonl"), "w") as f:
        for h in full["human_review"]:
            f.write(json.dumps(_clean(h)) + "\n")

    replay = {
        "meta": {**trace.meta, "source": trace.source, "T": trace.T, "N": trace.N, "slot_ms": trace.slot_ms,
                 "k": cfg["scenario"]["k_beams"], "pmax": cfg["scenario"]["p_max_w"]},
        "cells": cell_coords(),
        "demand": np.round(trace.rate, 1).tolist(),
        "forecast_h2": np.round(trace.forecast[:, :, 2], 1).tolist(),
        "elev": np.round(trace.elev[50], 1).tolist(),
        "events": [{"id": e.id, "slot": e.slot, "kind": e.kind, "audience": e.audience, "description": e.description, "stage": e.payload.get("stage")} for e in feed.events],
        "runs": {n: {"series": series(tr, r), "kpis": r["kpis"]} for n, (tr, _, r) in runs.items()},
        "audit": [_clean(rec.to_dict()) for rec in full["records"]],
        "human_review": _clean(full["human_review"]),
        "latency": latency,
    }
    json.dump(replay, open(os.path.join(RESULTS, "flood_replay.json"), "w"), separators=(",", ":"))

    # Monte Carlo over demand noise: the storyline is not one lucky seed
    seeds = range(100, 104 if fast else 130)
    mc_keys = ["throughput_mbps", "mean_delay_ms", "rt_sla_violation", "emergency_rt_violation", "emergency_served_ratio",
               "cap_violation_slots", "jain_fairness", "packet_loss"]
    raw = {n: [flood_run(cfg, fc, base, kb, mk, on, seed=s)[2]["kpis"] for s in seeds] for n, (mk, on) in controllers.items()}
    mc = {"seeds": len(list(seeds)), "note": "Same scenario, new demand noise per seed; fade, cap and event timing fixed.",
          "controllers": {n: {k: bootstrap([x[k] for x in v]) for k in mc_keys} for n, v in raw.items()}}
    json.dump(mc, open(os.path.join(RESULTS, "flood_mc.json"), "w"), indent=1)
    print({n: {k: round(v[k]["mean"], 3) for k in mc_keys} for n, v in mc["controllers"].items()}, flush=True)

    # What-if grid: real runs of the pipeline, looked up by the sliders
    caps = [12.0, 16.0, 22.0, 30.0, 40.0, 100.0]
    fades = [0.0, 3.0, 6.0, 9.0, 12.0]
    cells = []
    ec = cfg["demo"]["event_cell"]
    for cap in caps[:2] if fast else caps:
        for fade in fades[:2] if fast else fades:
            ov = {"border_cap_w": cap, "fade_db": fade}
            row = {"cap": cap, "fade": fade, "experiment_id": f"grid:cap{cap:g}:fade{fade:g}:seed42", "config": {"border_cap_w": cap, "fade_db": fade, "seed": 42, "scenario": "flood_relief"}}
            for n, (mk, on) in (("OrbitFlow", (bridge, True)), ("BRIDGE alone", (bridge, False))):
                tr, _, r = flood_run(cfg, fc, base, kb, mk, on, overrides=ov)
                H = r["history"]
                row[n] = {**{k: r["kpis"][k] for k in ("emergency_served_ratio", "emergency_rt_violation", "cap_violation_slots", "mean_delay_ms", "human_reviews", "throughput_mbps")},
                          "q_event": np.round([float(h["q_rt"][ec] + h["q_nrt"][ec]) for h in H], 0).tolist(),
                          "reviews": _clean(r["human_review"][:3])}
            cells.append(row)
    json.dump({"caps": caps, "fades": fades, "cells": cells}, open(os.path.join(RESULTS, "whatif_grid.json"), "w"), separators=(",", ":"))

    web = os.path.join(ROOT, "dashboard", "frontend", "public", "data")
    os.makedirs(web, exist_ok=True)
    for f in ["flood_mc", "whatif_grid", "flood_replay", "kb_report", "gaps", "predictor_metrics", "multirun", "ppo_summary", "retrieval_eval"]:
        shutil.copy(os.path.join(RESULTS, f + ".json"), web)
    for f in os.listdir(os.path.join(RESULTS, "studies")):
        shutil.copy(os.path.join(RESULTS, "studies", f), os.path.join(web, "study_" + f))
    print("done", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    main(ap.parse_args().fast)
