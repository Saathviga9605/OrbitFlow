"""Targeted studies: emergency transition, rain x cap factorial, agent overhead, stress test, link sensitivity, BC diagnostics.

    python scripts/run_studies.py [--n 30] [--tag final] [--only NAME]
Writes results/studies/*.json. Paired by demand seed throughout.
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

OUT = os.path.join(ROOT, "results", "studies")
_G: dict = {}


def _init(tag):
    import torch
    from rag.retriever import KnowledgeBase
    from traffic.dataset import load_trace
    from traffic.forecaster import Forecaster
    torch.set_num_threads(1)
    cfg = load_config()
    _G.update(cfg=cfg, base=load_trace(REAL_TRACE), kb=KnowledgeBase(cfg), fc=Forecaster.load(cfg, os.path.join(ROOT, "models", "traffic_predictor.pt")),
              ckpts=sorted(glob.glob(os.path.join(ROOT, "models", "exp", f"bridge_ppo_{tag}_s*.pt"))) or [os.path.join(ROOT, "models", "bridge_ppo.pt")])


def flood_kpis(args):
    """One flood-relief run. args = (seed, overrides, agents_on, emergency_cfg, link_cfg)."""
    from agents.supervisor import Supervisor
    from bridge.policy import BridgePolicy
    from scenarios.flood_relief import build
    from traffic.forecaster import prepare_forecast
    seed, ov, on, em, link = args
    cfg = copy.deepcopy(_G["cfg"])
    cfg["emergency"].update(em or {})
    cfg["link"].update(link or {})
    tr, feed = build(_G["base"], ov, seed)
    tr.forecast = prepare_forecast(_G["fc"], tr, cfg)
    ckpt = _G["ckpts"][seed % len(_G["ckpts"])]
    r = Supervisor(cfg, BridgePolicy(cfg, ckpt), feed, _G["kb"], agents_on=on).run(tr)
    H, k = r["history"], r["kpis"]
    q = np.array([h["q_rt"] + h["q_nrt"] for h in H])
    end = (ov or {}).get("surge_end", 61)
    em_cells = tr.meta["emergency_cells"]
    others = [c for c in range(tr.N) if c not in em_cells]
    rate = np.maximum(tr.rate * cfg["queues"]["rt_share"], 1e-6)
    rt_age = np.array([h["q_rt"] for h in H]) / rate
    wnd = rt_age[28:end]
    prop = np.array([[x.proposed["power_w"].get(c, 0.0) for c in range(tr.N)] for x in r["records"]])
    border, cap = tr.meta["border_cells"], tr.meta["border_cap_w"]
    capacity = np.array([h["cap_mbps"] for h in H])
    return {**{m: k[m] for m in ("throughput_mbps", "mean_delay_ms", "p95_delay_ms", "rt_sla_violation", "emergency_served_ratio", "emergency_rt_violation", "cap_violation_slots", "human_reviews", "jain_fairness", "packet_loss")},
            "peak_backlog_after_end": float(q[end:min(end + 20, tr.T), tr.meta["event_cell"]].max()),
            "backlog_total_after_end": float(q[end:min(end + 20, tr.T)].sum(1).mean()),
            "other_cells_rt_miss": float((rt_age[:, others] > cfg["queues"]["rt_delay_budget_ms"]).mean()),
            "emergency_rt_miss_window": float((wnd[:, em_cells] > cfg["queues"]["rt_delay_budget_ms"]).mean()),
            "emergency_capacity_mbps": float(capacity[45:end, em_cells[0]].mean()),
            "cap_binding_share": float((prop[50:, border] > cap + 1e-6).any(axis=1).mean()),
            "max_proposed_w": float(prop.max()),
            "proposal_max_border_w": float(prop[50:, border].max()),
            "mean_sinr_db": k["mean_sinr_db"], "compute_ms": {s: float(np.mean(v)) if v else 0.0 for s, v in r["compute_ms"].items()}}


def _table(rows: list[dict], keys) -> dict:
    return {k: summary([r[k] for r in rows]) for k in keys}


def emergency(ex, n):
    """Variants x durations x traffic. Includes the agents-off control."""
    variants = {"always + abrupt (previous)": dict(mode="always", release="abrupt"), "always + taper": dict(mode="always", release="taper"),
                "need-based + abrupt": dict(mode="need_based", release="abrupt"), "need-based + taper": dict(mode="need_based", release="taper")}
    conds = [(e, s) for e in (45, 61, 80) for s in (0.75, 1.0, 1.25)]
    keys = ["mean_delay_ms", "rt_sla_violation", "emergency_served_ratio", "emergency_rt_miss_window", "other_cells_rt_miss", "peak_backlog_after_end", "backlog_total_after_end", "cap_violation_slots", "jain_fairness"]
    out = {"n_per_cell": n, "conditions": {}}
    for e, s in conds:
        ov = {"surge_end": e, "traffic_scale": s}
        raw = {name: list(ex.map(flood_kpis, [(100 + i, ov, True, v, None) for i in range(n)])) for name, v in variants.items()}
        raw["agents off"] = list(ex.map(flood_kpis, [(100 + i, ov, False, None, None) for i in range(n)]))
        c = {name: _table(rows, keys) for name, rows in raw.items()}
        base = raw["always + abrupt (previous)"]
        c["vs_previous"] = {name: {k: paired([x[k] for x in raw[name]], [x[k] for x in base]) for k in ("mean_delay_ms", "peak_backlog_after_end", "emergency_rt_miss_window", "rt_sla_violation")} for name in variants if name != "always + abrupt (previous)"}
        out["conditions"][f"end={e},traffic={s}"] = c
        print(e, s, {name: (round(c[name]["mean_delay_ms"]["mean"], 1), round(c[name]["peak_backlog_after_end"]["mean"]), round(c[name]["emergency_rt_miss_window"]["mean"], 3), round(c[name]["rt_sla_violation"]["mean"], 3)) for name in raw}, flush=True)
    json.dump(out, open(os.path.join(OUT, "emergency.json"), "w"), indent=1)


def factorial(ex, n):
    """Rain x cap. Interaction = (rain+cap - rain) - (cap - clear), on paired seeds."""
    rains, caps = (0.0, 6.0, 12.0), (100.0, 22.0, 8.0)
    keys = ["emergency_served_ratio", "emergency_capacity_mbps", "mean_delay_ms", "rt_sla_violation", "emergency_rt_miss_window", "cap_binding_share", "proposal_max_border_w", "max_proposed_w", "mean_sinr_db", "cap_violation_slots"]
    raw = {}
    for r in rains:
        for c in caps:
            raw[(r, c)] = list(ex.map(flood_kpis, [(100 + i, {"fade_db": r, "border_cap_w": c}, True, None, None) for i in range(n)]))
    cells = [{"rain_db": r, "cap_w": None if c == 100 else c, **_table(raw[(r, c)], keys)} for (r, c) in raw]
    K = "emergency_served_ratio"
    effect = lambda a, b: paired([x[K] for x in raw[a]], [x[K] for x in raw[b]])
    inter = {}
    for r in (6.0, 12.0):
        for c in (22.0, 8.0):
            d = [(raw[(r, c)][i][K] - raw[(r, 100.0)][i][K]) - (raw[(0.0, c)][i][K] - raw[(0.0, 100.0)][i][K]) for i in range(n)]
            inter[f"rain{r:.0f}_cap{c:.0f}"] = {**summary(d), **{k: v for k, v in paired(d, np.zeros(n)).items() if k in ("p", "rank_biserial", "test")}}
    from digital_twin.link_budget import sinr_limit_db
    out = {"n_per_cell": n, "cells": cells, "main_effects": {"rain 6 dB alone": effect((6.0, 100.0), (0.0, 100.0)), "rain 12 dB alone": effect((12.0, 100.0), (0.0, 100.0)),
                                                              "cap 22 W alone": effect((0.0, 22.0), (0.0, 100.0)), "cap 8 W alone": effect((0.0, 8.0), (0.0, 100.0))},
           "interaction_served_ratio": inter, "labels": {"cap": "Hypothetical operating constraint. No rule in the corpus sets this number."},
           "physics": {"sinr_ceiling_equal_beams_db": sinr_limit_db(25, 75, _G_cfg()["link"]["interference_isolation_db"]),
                       "sinr_ceiling_22W_vs_78W_db": sinr_limit_db(22, 78, _G_cfg()["link"]["interference_isolation_db"]),
                       "sinr_ceiling_8W_vs_92W_db": sinr_limit_db(8, 92, _G_cfg()["link"]["interference_isolation_db"])}}
    json.dump(out, open(os.path.join(OUT, "factorial.json"), "w"), indent=1)
    print({f"r{c['rain_db']}c{c['cap_w']}": (round(c[K]["mean"], 3), round(c["cap_binding_share"]["mean"], 2), round(c["emergency_capacity_mbps"]["mean"], 1), round(c["proposal_max_border_w"]["mean"], 1)) for c in cells}, flush=True)


def _G_cfg():
    return load_config()


def _pfd_task(args):
    """Flood relief with a physics-derived per-cell, per-slot cap from the SF.358-5 mask. No 22 W notice."""
    from agents.supervisor import Supervisor
    from bridge.policy import BridgePolicy
    from digital_twin.link_budget import pfd_power_cap_w
    from scenarios.flood_relief import build
    from traffic.dataset import load_slant_km
    from traffic.forecaster import prepare_forecast
    seed, gtx, on = args
    cfg = _G["cfg"]
    tr, feed = build(_G["base"], {"border_cap_w": 100.0}, seed)
    tr.forecast = prepare_forecast(_G["fc"], tr, cfg)
    if gtx is not None:
        km = load_slant_km()
        tr.meta["pfd_cap_w"] = np.array([[pfd_power_cap_w(tr.elev[t, c], gtx, km[t, c], cfg["link"]["bandwidth_mhz"]) for c in range(tr.N)] for t in range(tr.T)])
    r = Supervisor(cfg, BridgePolicy(cfg, _G["ckpts"][seed % len(_G["ckpts"])]), feed, _G["kb"], agents_on=on).run(tr)
    k = r["kpis"]
    H = r["history"]
    return {**{m: k[m] for m in ("emergency_served_ratio", "mean_delay_ms", "throughput_mbps", "served_ratio", "rt_sla_violation", "packet_loss", "pfd_breach_slots", "pfd_binding_slots", "human_reviews", "mean_sinr_db")},
            "mean_total_w": float(np.mean([h["power"].sum() for h in H])), "median_cap_w": float(np.median(tr.meta["pfd_cap_w"])) if gtx is not None else None}


def pfd_study(ex, n):
    gains = (None, 15.0, 20.0, 25.0, 30.0)
    keys = ["emergency_served_ratio", "mean_delay_ms", "throughput_mbps", "served_ratio", "rt_sla_violation", "packet_loss", "pfd_breach_slots", "pfd_binding_slots", "human_reviews", "mean_sinr_db", "mean_total_w"]
    out = {"label": "INDICATIVE. Mask from ITU-R SF.358-5 recommends 1.5. Its listed bands stop at 19.7 GHz and OrbitFlow's carrier is 20.0 GHz; the definitive limits are in the Radio Regulations, which are not in the corpus. Tx gain is assumed because config.yaml lumps Tx and Rx gain.", "n_per_setting": n, "settings": {}}
    base = None
    for g in gains:
        rows = list(ex.map(_pfd_task, [(100 + i, g, True) for i in range(n)]))
        e = _table(rows, keys)
        e["median_cap_w"] = rows[0]["median_cap_w"]
        if g is None:
            base = rows
        else:
            e["delay_vs_no_cap"] = paired([r["mean_delay_ms"] for r in rows], [r["mean_delay_ms"] for r in base])
            e["emergency_vs_no_cap"] = paired([r["emergency_served_ratio"] for r in rows], [r["emergency_served_ratio"] for r in base])
        if g is not None:
            off = list(ex.map(_pfd_task, [(100 + i, g, False) for i in range(n)]))
            e["breach_slots_without_agents"] = summary([r["pfd_breach_slots"] for r in off])
        out["settings"]["no cap" if g is None else f"Gtx={g:g} dBi"] = e
        print(g, rows[0]["median_cap_w"], {k: round(e[k]["mean"], 3) for k in keys}, flush=True)
    json.dump(out, open(os.path.join(OUT, "pfd_mask.json"), "w"), indent=1)


def latency(n):
    """Compute time per stage, single process, separate from queueing delay in the twin."""
    _init(_TAG)
    import time
    from agents.supervisor import Supervisor
    from bridge.policy import BridgePolicy
    from rag.retriever import answer
    from scenarios.flood_relief import build
    from traffic.forecaster import prepare_forecast
    cfg = _G["cfg"]
    samples = {}
    fc_ms = []
    decision_totals = []
    for i in range(n):
        tr, feed = build(_G["base"], None, 100 + i)
        t0 = time.perf_counter()
        tr.forecast = prepare_forecast(_G["fc"], tr, cfg)
        fc_ms.append((time.perf_counter() - t0) * 1000 / tr.T)
        r = Supervisor(cfg, BridgePolicy(cfg, _G["ckpts"][0]), feed, _G["kb"], agents_on=True).run(tr)
        for s, v in r["compute_ms"].items():
            samples.setdefault(s, []).extend(v)
        decision_totals.extend(np.sum([r["compute_ms"][s] for s in ("network", "policy", "safety", "guard")], axis=0).tolist())
    t0 = time.perf_counter()
    KB_q = [answer(_G["kb"], "human oversight of automated AI decisions") for _ in range(5)]
    retr = (time.perf_counter() - t0) * 200
    stat = lambda v: {"mean": float(np.mean(v)), "p50": float(np.median(v)), "p99": float(np.percentile(v, 99)), "max": float(np.max(v)), "n": len(v)}
    out = {"note": "Wall-clock compute on one CPU core with Python; not real-time guarantees. Queueing delay is a separate network KPI.",
           "stages": {s: stat(v) for s, v in samples.items()}, "forecast_per_slot_ms": stat(fc_ms), "critical_path_total": stat(decision_totals),
           "live_retrieval_ms_if_not_cached": retr, "slot_ms": cfg["scenario"]["slot_ms"]}
    json.dump(out, open(os.path.join(OUT, "latency.json"), "w"), indent=1)
    print({k: round(v["mean"], 3) for k, v in out["stages"].items()}, out["critical_path_total"], retr, flush=True)


def stress():
    """CONTROLLED stress test: the 50 W proposals are injected by this script, BRIDGE did not produce them."""
    _init(_TAG)
    from agents.supervisor import Supervisor
    from bam.validator import BamGuard, Constraints, GuardState
    from bridge.baselines import Action, Policy
    from bridge.policy import BridgePolicy
    from digital_twin.environment import NTNTwin
    from scenarios.flood_relief import build
    from traffic.forecaster import prepare_forecast
    cfg = _G["cfg"]

    class Injected(Policy):
        name = "Injected 50 W proposal"

        def act(self, obs):
            lit = np.zeros(19, bool)
            lit[[13, 2, 5, 9]] = True
            p = np.zeros(19)
            p[[13, 2, 5, 9]] = [50.0, 20.0, 15.0, 15.0]
            return Action(lit, p, priority=obs["rate_obs"])

    tr, feed = build(_G["base"], None, 42)
    tr.forecast = prepare_forecast(_G["fc"], tr, cfg)
    r = Supervisor(cfg, Injected(), feed, _G["kb"], agents_on=True).run(tr)
    rec = r["records"][52].to_dict()
    cases = []
    g = BamGuard(cfg)
    st = GuardState.fresh(19)
    cap = np.full(19, np.inf)
    cap[cfg["demo"]["border_cells"]] = cfg["demo"]["border_cap_w"]

    def case(name, lit_cells, watts, constraints=None):
        lit = np.zeros(19, bool)
        lit[lit_cells] = True
        p = np.zeros(19)
        p[lit_cells] = watts
        before = g.check(lit, p, st, 1.0, 0.0)
        res = g.repair(lit, p, st, 1.0, 0.0, priority=np.arange(19, dtype=float), constraints=constraints)
        cases.append({"case": name, "proposed": {int(c): float(w) for c, w in zip(lit_cells, watts)}, "failed_checks": [k for k, v in before.items() if v["status"] == "FAIL"],
                      "final": {int(c): round(float(res.power[c]), 2) for c in np.where(res.lit)[0]}, "notes": res.notes, "total_w": round(float(res.power.sum()), 2), "final_ok": res.ok,
                      "cap_respected": bool((res.power <= cap + 1e-6).all()) if constraints else None})
    case("50 W on a capped border cell", [13, 2, 5, 9], [50, 20, 15, 15], Constraints(power_cap=cap))
    case("200 W total, over the 100 W budget", [1, 2, 3, 4], [50, 50, 50, 50])
    case("6 beams when only 4 are allowed", [1, 2, 3, 4, 5, 6], [15, 15, 15, 15, 15, 15])
    case("0.5 W beam under the 2 W floor", [1, 2, 3, 4], [0.5, 33, 33, 33])

    # Would BRIDGE ever propose 50 W on its own? Look across many episodes and kinds.
    from traffic.generator import make_trace
    shares = []
    for ck in _G["ckpts"]:
        pol = BridgePolicy(cfg, ck)
        for i in range(40):
            t = make_trace(["normal", "block", "event_surge", "bursty", "mixed"][i % 5], _G["base"], 60000 + i)
            t.forecast = prepare_forecast(_G["fc"], t, cfg)
            tw = NTNTwin(t, cfg)
            o = tw.reset()
            while not tw.done:
                a = pol.act(o)
                shares.append(float(a.power.max()))
                tw.step(a.lit, a.power)
                o = tw.obs()
    shares = np.array(shares)
    out = {"label": "CONTROLLED CONSTRAINT STRESS TEST. Proposals are injected by scripts/run_studies.py. Not produced by BRIDGE; not part of the flood-relief replay.",
           "flood_injection": {"slot": 52, "applicable_cap_w": cfg["demo"]["border_cap_w"], "cap_status": "hypothetical operating constraint", "proposed": rec["proposed"], "constraints": rec["constraints"],
                               "policy_findings": [{k: f[k] for k in ("rule_id", "status", "evidence_status", "detail")} for f in rec["policy_findings"]], "final": rec["final"], "repairs": rec["repairs"], "decision": rec["decision"]},
           "run_summary": {"cap_violation_slots": r["kpis"]["cap_violation_slots"], "human_reviews": r["kpis"]["human_reviews"], "first_review": r["human_review"][0] if r["human_review"] else None},
           "guard_cases": cases,
           "natural_bridge_power": {"episodes": len(_G["ckpts"]) * 40, "decisions": len(shares), "max_w": float(shares.max()), "p99_w": float(np.percentile(shares, 99)), "median_max_beam_w": float(np.median(shares)), "share_over_50w": float((shares >= 50).mean()), "share_over_22w": float((shares > 22).mean()),
                                    "explanation": "Capacity grows with the log of SINR and interference sets a ceiling, so concentrating power gains little and costs other beams. Large shares are rare but do occur."}}
    json.dump(out, open(os.path.join(OUT, "stress_test.json"), "w"), indent=1)
    print(out["natural_bridge_power"], cases[0], out["run_summary"], flush=True)


def _sens_task(args):
    from bridge.baselines import ReactiveGreedy
    from bridge.evaluate import run_episode
    from bridge.policy import BridgePolicy
    from traffic.forecaster import prepare_forecast
    from traffic.generator import make_trace
    kind, seed, link = args
    cfg = copy.deepcopy(_G["cfg"])
    cfg["link"].update(link)
    t = make_trace(kind, _G["base"], seed)
    t.forecast = prepare_forecast(_G["fc"], t, cfg)
    keys = ("mean_sinr_db", "throughput_mbps", "served_ratio", "mean_delay_ms", "rt_sla_violation", "packet_loss", "beam_switches_per_slot", "energy_j")
    a = run_episode(t, cfg, ReactiveGreedy(19, 4, 100.0))
    b = run_episode(t, cfg, BridgePolicy(cfg, _G["ckpts"][seed % len(_G["ckpts"])]))
    return {"reactive": {k: a[k] for k in keys}, "bridge": {k: b[k] for k in keys}}


def sensitivity(ex, n):
    """One-at-a-time ranges. BRIDGE keeps its nominal training, so this also measures robustness to link mismatch."""
    ranges = {"nominal": {}, **{f"antenna_gain_db={v}": {"antenna_gain_db": v} for v in (47.0, 50.0, 56.0)}, **{f"bandwidth_mhz={v}": {"bandwidth_mhz": v} for v in (10.0, 15.0, 40.0)},
              **{f"interference_isolation_db={v}": {"interference_isolation_db": v} for v in (15.0, 25.0, 30.0)}, **{f"noise_figure_db={v}": {"noise_figure_db": v} for v in (3.0, 10.0)}, **{f"sinr_min_db={v}": {"sinr_min_db": v} for v in (-3.0, 0.0)}}
    out = {"n_per_setting": n, "kind": "block + mixed", "settings": {}}
    for name, link in ranges.items():
        tasks = [(k, 70000 + i, link) for k in ("block", "mixed") for i in range(n // 2)]
        rows = list(ex.map(_sens_task, tasks))
        entry = {p: {k: summary([r[p][k] for r in rows]) for k in rows[0][p]} for p in ("reactive", "bridge")}
        entry["rt_miss_bridge_vs_reactive"] = paired([r["bridge"]["rt_sla_violation"] for r in rows], [r["reactive"]["rt_sla_violation"] for r in rows])
        entry["delay_bridge_vs_reactive"] = paired([r["bridge"]["mean_delay_ms"] for r in rows], [r["reactive"]["mean_delay_ms"] for r in rows])
        flood = list(ex.map(flood_kpis, [(100 + i, None, True, None, link) for i in range(n // 2)]))
        entry["flood"] = _table(flood, ["emergency_served_ratio", "mean_delay_ms", "emergency_rt_miss_window"])
        out["settings"][name] = entry
        print(name, round(entry["bridge"]["mean_sinr_db"]["mean"], 1), round(entry["bridge"]["throughput_mbps"]["mean"], 1), "rt", round(entry["reactive"]["rt_sla_violation"]["mean"], 3), round(entry["bridge"]["rt_sla_violation"]["mean"], 3), "dly", round(entry["reactive"]["mean_delay_ms"]["mean"], 1), round(entry["bridge"]["mean_delay_ms"]["mean"], 1), "em", round(entry["flood"]["emergency_served_ratio"]["mean"], 3), flush=True)
    json.dump(out, open(os.path.join(OUT, "link_sensitivity.json"), "w"), indent=1)


def bc_diagnostics():
    """Demonstrations: action validity, cell coverage, power patterns, teacher-vs-clone agreement, unseen performance."""
    _init(_TAG)
    from bam.validator import BamGuard
    from bridge.policy import BridgePolicy, HeuristicPredictive
    from digital_twin.environment import NTNTwin
    from traffic.forecaster import prepare_forecast
    from traffic.generator import make_trace
    cfg = _G["cfg"]
    bc_ck = sorted(glob.glob(os.path.join(ROOT, "models", "exp", f"bridge_bc_{_TAG}_s*.pt")))
    teacher = HeuristicPredictive(cfg)
    bc = BridgePolicy(cfg, bc_ck[0]) if bc_ck else None
    guard = BamGuard(cfg)
    rows = {}
    for kind in ("normal", "block", "event_surge", "bursty", "mixed"):
        sel, power_share, valid, overlap, hot_hit, n = np.zeros(19), [], [], [], [], 0
        for i in range(30):
            t = make_trace(kind, _G["base"], 80000 + i)
            t.forecast = prepare_forecast(_G["fc"], t, cfg)
            tw = NTNTwin(t, cfg)
            o = tw.reset()
            while not tw.done:
                a = teacher.act(o)
                chk = guard.check(a.lit, a.power, o["guard"], o["ssb"], o["sib"])
                valid.append(all(c["status"] == "PASS" for c in chk.values()))
                sel += a.lit
                power_share.append(float(a.power.max() / a.power.sum()))
                top = set(np.argsort(-t.rate[o["t"]])[:4].tolist())
                hot_hit.append(len(top & set(np.where(a.lit)[0].tolist())) / 4)
                if bc:
                    overlap.append(len(set(np.where(bc.act(o).lit)[0].tolist()) & set(np.where(a.lit)[0].tolist())) / 4)
                n += 1
                res = guard.repair(a.lit, a.power, o["guard"], o["ssb"], o["sib"], priority=a.priority)
                tw.step(res.lit, res.power)
                o = tw.obs()
        rows[kind] = {"decisions": n, "valid_share": float(np.mean(valid)), "cell_selection_share_min": float(sel.min() / sel.sum() * 4), "cell_selection_share_max": float(sel.max() / sel.sum() * 4),
                      "max_beam_power_share_mean": float(np.mean(power_share)), "hottest4_coverage": float(np.mean(hot_hit)), "bc_teacher_beam_overlap": float(np.mean(overlap)) if overlap else None}
        print(kind, rows[kind], flush=True)
    json.dump({"teacher": "HeuristicPredictive, the hand-written rule the clone imitates", "kinds": rows}, open(os.path.join(OUT, "bc_diagnostics.json"), "w"), indent=1)


_TAG = "final"


def main(n, tag, only):
    global _TAG
    _TAG = tag
    os.makedirs(OUT, exist_ok=True)
    run = lambda x: only is None or x == only
    if run("latency"):
        latency(max(n // 3, 2))
    if run("stress"):
        stress()
    if run("bc"):
        bc_diagnostics()
    with ProcessPoolExecutor(14, initializer=_init, initargs=(tag,)) as ex:
        if run("pfd"):
            pfd_study(ex, n)
        if run("factorial"):
            _G.setdefault("cfg", load_config())
            factorial(ex, n)
        if run("emergency"):
            emergency(ex, n)
        if run("sensitivity"):
            sensitivity(ex, n)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--tag", default="final")
    ap.add_argument("--only")
    a = ap.parse_args()
    main(a.n, a.tag, a.only)
