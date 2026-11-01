"""Run a policy through the twin with the guardrail in the loop and report KPIs."""
from __future__ import annotations

import copy

import numpy as np

from bam.validator import BamGuard, Constraints
from digital_twin.environment import NTNTwin, summarise


def run_episode(trace, cfg: dict, policy, lag: int | None = None, keep_records: bool = False, 
                constraints_fn=None, callbacks=None) -> dict:
    """Run a policy through the twin with the guardrail in the loop and report KPIs.
    
    Args:
        trace: Trace object
        cfg: Configuration dict
        policy: Policy object with .reset() and .act() methods
        lag: Optional override for obs_lag_slots
        keep_records: If True, store detailed per-slot records
        constraints_fn: Optional callable(obs) -> Constraints | None for dynamic constraints
        callbacks: Optional list of callables(obs, act, res, rec) fired after each step
    """
    cfg = copy.deepcopy(cfg)
    if lag is not None:
        cfg["scenario"]["obs_lag_slots"] = lag
    twin = NTNTwin(trace, cfg)
    guard = BamGuard(cfg)
    policy.reset()
    obs = twin.reset()
    repairs = guard_fail_before = 0
    records = []
    while not twin.done:
        act = policy.act(obs)
        
        # Get dynamic constraints if provided
        constraints = None
        if constraints_fn is not None:
            constraints = constraints_fn(obs)
        
        before = guard.check(act.lit, act.power, obs["guard"], obs["ssb"], obs["sib"])
        res = guard.repair(act.lit, act.power, obs["guard"], obs["ssb"], obs["sib"], priority=act.priority, constraints=constraints)
        failed = [k for k, v in before.items() if v["status"] == "FAIL"]
        guard_fail_before += int(bool(failed))
        repairs += int(res.repaired)
        rec = twin.step(res.lit, res.power)
        
        # Fire callbacks if provided
        if callbacks:
            for cb in callbacks:
                cb(obs, act, res, rec)
        
        if keep_records:
            records.append({"t": obs["t"], "proposed_lit": np.where(act.lit)[0].tolist(),
                            "final_lit": np.where(res.lit)[0].tolist(), "failed_before": failed,
                            "notes": res.notes, "final_ok": res.ok})
        obs = twin.obs()
    out = summarise(twin.history, twin.slot_ms,
                    {"guard_violation_slots": guard_fail_before, "guard_repairs": repairs})
    if keep_records:
        out["records"] = records
        out["history"] = twin.history
    return out


def format_table(rows: dict[str, dict], cols: list[str]) -> str:
    w = max(len(k) for k in rows) + 2
    head = "policy".ljust(w) + "".join(c[:14].rjust(15) for c in cols)
    lines = [head, "-" * len(head)]
    for name, r in rows.items():
        lines.append(name.ljust(w) + "".join(f"{r[c]:15.3f}" for c in cols))
    return "\n".join(lines)
