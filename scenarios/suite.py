"""Runs the demonstration scenarios in scenarios/suite.yaml through the real pipeline.

    python scripts/run_suite.py          # all scenarios -> results/scenario_suite.json
Every number in a result is measured from a run made here; checks compare measurements with the
expectations written in suite.yaml.
"""
from __future__ import annotations

import copy
import hashlib
import math
import os
import time

import numpy as np
import torch
import yaml

from agents.registry import build_network_policy
from agents.supervisor import Supervisor
from policy.engine import load_profile, scenario_overrides, summary as profile_summary, validate, with_overrides
from scenarios.engine import EventFeed
from scenarios.flood_relief import build
from traffic.dataset import load_trace
from traffic.forecaster import Forecaster, gate_forecast, persistence_trace
from traffic.generator import make_trace
from utils.config import REAL_TRACE, ROOT, load_config

SUITE = os.path.join(ROOT, "scenarios", "suite.yaml")
LANGS = ("en", "ar", "hi", "ta")
_RT: dict = {}


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()[:12]


def runtime(kb=None) -> dict:
    """Models, trace and knowledge base, loaded once per process."""
    if not _RT:
        from rag.retriever import KnowledgeBase
        cfg = load_config()
        m = os.path.join(ROOT, "models")
        _RT.update(cfg=cfg, base=load_trace(REAL_TRACE), kb=kb or KnowledgeBase(cfg),
                   fc=Forecaster.load(cfg, os.path.join(m, "traffic_predictor.pt")),
                   ckpt=os.path.join(m, "bridge_ppo.pt"))
        _RT["shas"] = {"config.yaml": sha(os.path.join(ROOT, "config.yaml")), "bridge_ppo.pt": sha(_RT["ckpt"]),
                       "traffic_predictor.pt": sha(os.path.join(m, "traffic_predictor.pt"))}
    return _RT


def load_suite() -> list[dict]:
    with open(SUITE, encoding="utf8") as f:
        return yaml.safe_load(f)


def scenario_def(sid: str) -> dict:
    for s in load_suite():
        if s["id"] == sid:
            return s
    raise KeyError(f"unknown scenario {sid}")


def _finite(x):
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    if isinstance(x, dict):
        return {k: _finite(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_finite(v) for v in x]
    if isinstance(x, (np.floating, np.integer)):
        return _finite(x.item())
    return x


# ------------------------------------------------------------------ building blocks
def make_case(rt, base: dict, seed: int, profile: dict):
    """(trace, feed) for a base definition. Flood runs take the profile's operating constraint."""
    kind = base["kind"]
    if kind == "synthetic":
        return make_trace(base["traffic"], rt["base"], seed), EventFeed([])
    if kind == "flood":
        ov = scenario_overrides(profile)
        for k in ("fade_db", "traffic_scale"):
            if k in base:
                ov[k] = float(base[k])
        return build(rt["base"], ov, seed)
    raise ValueError(f"unknown base kind {kind}")


def forecast_for(rt, trace, seed: int, noise: dict | None = None) -> dict:
    """Attach the gated forecast to the trace and measure it against what actually happened (simulation ground truth)."""
    raw = rt["fc"].predict_trace(trace, 1)
    if noise:
        rng = np.random.default_rng(seed + 7919)
        a, b = noise["slots"]
        for c in noise["cells"]:
            raw[a:b, c] = np.maximum(raw[a:b, c] + noise["sigma_mbps"] * rng.standard_normal((b - a, raw.shape[2])), 0.0)
    gated = gate_forecast(trace, raw, 1) if rt["cfg"]["predictor"].get("gate") else raw
    trace.forecast = gated
    pers = persistence_trace(trace)
    truth = trace.rate[1:]
    mae = lambda f: float(np.abs(f[1:, :, 0] - truth).mean())        # noqa: E731 - one-step-ahead error
    return {"raw_mae_mbps": round(mae(raw), 3), "gated_mae_mbps": round(mae(gated), 3), "persistence_mae_mbps": round(mae(pers), 3),
            "gated_share": round(float((np.abs(gated - raw) > 1e-6).any(axis=2).mean()), 4),
            "injected_noise": noise, "note": "MAE of the one-slot-ahead forecast against simulated demand"}


def run_once(rt, trace, feed, profile, faults=None, agents_on=True, impl="bridge_ppo"):
    policy = build_network_policy(rt["cfg"], impl, rt["ckpt"])
    sup = Supervisor(rt["cfg"], policy, feed, rt["kb"], agents_on=agents_on, profile=profile, faults=faults)
    t0 = time.perf_counter()
    r = sup.run(trace)
    r["wall_s"] = round(time.perf_counter() - t0, 2)
    if impl == "bridge_ppo":
        r["model_param_sha"] = hashlib.sha256(b"".join(p.detach().numpy().tobytes() for p in policy.net.parameters())).hexdigest()[:12]
    return r


KPI_KEYS = ("throughput_mbps", "mean_delay_ms", "p95_delay_ms", "rt_sla_violation", "emergency_served_ratio", "emergency_rt_violation",
            "served_ratio", "jain_fairness", "beam_switches_per_slot", "guard_repairs", "cap_violation_slots", "human_reviews", "deliberations")


def kpis_of(r):
    return _finite({k: r["kpis"].get(k) for k in KPI_KEYS})


def series_of(r):
    recs = r["records"]
    return {"throughput_mbps": [round(h["throughput_mbps"], 1) for h in r["history"]],
            "decision": [x.decision for x in recs],
            "conflicts": [len(x.conflicts) for x in recs],
            "human_review_slots": sorted({h["slot"] for h in r["human_review"]})}


def trace_samples(r, k=4):
    """A few complete decision traces from the slots where something happened."""
    want = ("agent_failure", "validate_telemetry", "conflict_", "R1_border_power_cap", "FAIL_CLOSED", "forecast_alert")
    picked, seen_kinds = [], set()
    for rec in r["records"]:
        acts = [s["action"] for s in rec.trace]
        kind = next((w for w in want if any(a.startswith(w) for a in acts)), None)
        if kind and kind not in seen_kinds:
            seen_kinds.add(kind)
            steps = [{**s, "citations": s["citations"][:1]} for s in rec.trace]
            picked.append(_finite({"slot": rec.slot, "decision": rec.decision, "proposed": rec.proposed, "final": rec.final,
                                   "constraints": rec.constraints, "conflicts": rec.conflicts, "trace": steps, "trigger": kind}))
        if len(picked) == k:
            break
    return picked


def coordination_of(r):
    c = copy.deepcopy(r["coordination"])
    c["conflicts"] = c["conflicts"][:40]
    c["failures"] = c["failures"][:40]
    return _finite(c)


def resolve(result: dict, path: str):
    cur = result
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


OPS = {"==": lambda a, b: a == b, "<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b, ">": lambda a, b: a > b}


def evaluate_checks(result: dict, checks: list[dict]) -> list[dict]:
    out = []
    for c in checks:
        actual = resolve(result, c["metric"])
        expected = resolve(result, c["ref"]) if "ref" in c else c["value"]
        try:
            ok = actual is not None and expected is not None and bool(OPS[c["op"]](actual, expected))
        except TypeError:
            ok = False
        out.append({"metric": c["metric"], "op": c["op"], "expected": expected, "expected_from": c.get("ref"), "actual": actual,
                    "passed": ok, "why": c.get("why")})
    return out


def _profile(pid: str, base: dict):
    p = load_profile(pid)
    if "border_cap_w" in base:
        p = with_overrides(p, cap_w=base["border_cap_w"])
    return p


def _single(rt, s: dict, seed: int, pid: str) -> dict:
    base = s["base"]
    profile = _profile(pid, base)
    trace, feed = make_case(rt, base, seed, profile)
    fmetrics = forecast_for(rt, trace, seed, s.get("forecast_noise"))
    r = run_once(rt, trace, feed, profile, s.get("faults"))
    out = {"profile": profile_summary(profile), "profile_validation": validate(profile, rt["cfg"], rt["kb"]),
           "kpis": kpis_of(r), "coordination": coordination_of(r), "forecast": fmetrics, "series": series_of(r),
           "trace_samples": trace_samples(r), "human_review": _finite(r["human_review"][:8]), "wall_s": r["wall_s"],
           "model_param_sha": r.get("model_param_sha")}
    out["baselines"] = {"bridge_alone": {"label": "BRIDGE + guard, agents off", "kpis": kpis_of(run_once(rt, trace, feed, profile, agents_on=False))},
                        "reactive": {"label": "Reactive greedy + guard, agents off",
                                     "kpis": kpis_of(run_once(rt, trace, feed, profile, agents_on=False, impl="reactive_greedy"))}}
    if s.get("reference") == "no_faults":
        ref = run_once(rt, trace, feed, profile)
        out["reference"] = {"label": "Same scenario without injected faults", "kpis": kpis_of(ref)}
    out["_records"] = r["records"]
    return out


def _profiles(rt, s: dict, seed: int) -> dict:
    runs, out = {}, {}
    for pid in s["profiles"]:
        runs[pid] = _single(rt, {**s, "reference": None}, seed, pid)
    onset = min(run["profile"]["operating_constraints"]["border_power_cap"]["onset_slot"] for run in runs.values())
    first = next(iter(runs.values()))["_records"]
    same = all(all(a.proposed == b.proposed for a, b in zip(first[:onset], run["_records"][:onset])) for run in runs.values())
    for pid, run in runs.items():
        run.pop("_records")
        out[pid] = run
    return {"profiles": out, "profile_effect": {
        "pre_cap_identical": same, "cap_onset_slot": onset,
        "table": [{"profile": pid, "cap_w": run["profile"]["operating_constraints"]["border_power_cap"]["cap_w"],
                   "exemption": run["profile"]["operating_constraints"]["emergency_exemption"],
                   "emergency_served_ratio": run["kpis"]["emergency_served_ratio"], "cap_violation_slots": run["kpis"]["cap_violation_slots"],
                   "exempted_slots": run["coordination"]["exempted_slots"], "human_reviews": run["kpis"]["human_reviews"],
                   "conflicts": run["coordination"]["conflicts_by_type"], "mean_delay_ms": run["kpis"]["mean_delay_ms"]} for pid, run in out.items()]}}


def _matrix(rt, s: dict, seed: int) -> dict:
    res, shas = {}, set()
    for ctx in s["base"]["contexts"]:
        res[ctx] = {}
        for pid in s["profiles"]:
            profile = load_profile(pid)
            base = {"kind": "synthetic", "traffic": "normal"} if ctx == "normal" else {"kind": "flood"}
            trace, feed = make_case(rt, base, seed, profile)
            forecast_for(rt, trace, seed)
            r = run_once(rt, trace, feed, profile)
            shas.add(r["model_param_sha"])
            res[ctx][pid] = {"kpis": kpis_of(r), "exempted_slots": r["coordination"]["exempted_slots"],
                             "conflicts_by_type": r["coordination"]["conflicts_by_type"],
                             "human_review_by_kind": r["coordination"]["human_review_by_kind"]}
    same = lambda ctx: len({repr(v["kpis"]) for v in res[ctx].values()}) == 1          # noqa: E731
    return {"matrix": {"results": res, "model_checksums_identical": len(shas) == 1, "model_param_sha": sorted(shas),
                       "normal_identical_across_profiles": same("normal"), "flood_differs_across_profiles": not same("flood")}}


def run_custom(rt, profile_id="baseline-intl", cap_w=None, fade_db=None, seed=42, exemption=None, scale=None, with_baselines=False) -> dict:
    """A free-form flood run (used by the API and by multilingual requests)."""
    profile = with_overrides(load_profile(profile_id), cap_w=cap_w, exemption=exemption)
    base = {"kind": "flood"}
    if fade_db is not None:
        base["fade_db"] = fade_db
    if scale is not None:
        base["traffic_scale"] = scale
    v = validate(profile, rt["cfg"], None)
    if not v["valid"]:
        return {"error": "invalid profile", "profile_validation": v}
    trace, feed = make_case(rt, base, seed, profile)
    fm = forecast_for(rt, trace, seed)
    r = run_once(rt, trace, feed, profile)
    out = {"id": "custom_flood", "title": "Flood relief (custom parameters)", "seed": seed, "params": {"profile": profile_id, "cap_w": cap_w,
           "fade_db": fade_db, "exemption": exemption, "traffic_scale": scale}, "profile": profile_summary(profile), "profile_validation": v,
           "kpis": kpis_of(r), "coordination": coordination_of(r), "forecast": fm, "series": series_of(r), "trace_samples": trace_samples(r),
           "human_review": _finite(r["human_review"][:8]), "model_param_sha": r.get("model_param_sha")}
    if with_baselines:
        out["baselines"] = {"reactive": {"label": "Reactive greedy + guard, agents off",
                                         "kpis": kpis_of(run_once(rt, trace, feed, profile, agents_on=False, impl="reactive_greedy"))}}
    return out


def _multilingual(rt, s: dict, seed: int) -> dict:
    from i18n.interpret import interpret
    from i18n.explain import explain
    per, intents, kp = {}, set(), set()
    for lang, text in s["inputs"].items():
        it = interpret(text)
        p = it["params"]
        r = run_custom(rt, it["profile_id"] or "baseline-intl", p.get("cap_w"), p.get("fade_db"), p.get("seed", seed))
        intents.add(repr((it["scenario_id"], it["profile_id"], sorted(p.items()))))
        kp.add(repr(r["kpis"]))
        per[lang] = {"input": text, "interpreted": it, "kpis": r["kpis"], "explanation": explain(r, lang)}
    return {"multilingual": {"per_language": per, "same_intent": len(intents) == 1, "same_kpis": len(kp) == 1, "n_languages": len(per)}}


def run_scenario(sid: str, seed: int | None = None, profile_id: str | None = None, rt=None) -> dict:
    from i18n.explain import explain
    rt = rt or runtime()
    s = scenario_def(sid)
    seed = int(s.get("seed", 42) if seed is None else seed)
    t0 = time.perf_counter()
    meta = {k: s.get(k) for k in ("id", "title", "description", "simulated", "expected", "limitations")}
    kind = s["base"]["kind"]
    if s.get("profiles") and kind != "matrix":
        body = _profiles(rt, s, seed)
    elif kind == "matrix":
        body = _matrix(rt, s, seed)
    elif kind == "interpret":
        body = _multilingual(rt, s, seed)
    else:
        body = _single(rt, s, seed, profile_id or s.get("profile", "baseline-intl"))
        body.pop("_records", None)
    result = {**meta, "seed": seed, "base": s["base"], "faults": s.get("faults"), **body}
    result["checks"] = evaluate_checks(result, s.get("checks", []))
    result["passed"] = all(c["passed"] for c in result["checks"])
    result["reproducibility"] = {"seed": seed, "checksums": rt["shas"], "command": f"python scripts/run_suite.py --only {sid}",
                                 "deterministic": "same seed, config and checkpoints give identical KPIs (tests/test_scenarios.py)"}
    result["disclosure"] = {"is_simulation": True, "ground_truth": "simulated demand and channel from the digital twin",
                            "predictions": "forecast and BRIDGE proposals", "real_data": "pass geometry and channel of one recorded LEO pass"}
    result["explanation"] = {lang: explain(result, lang) for lang in LANGS}
    result["wall_s"] = round(time.perf_counter() - t0, 2)
    return _finite(result)
