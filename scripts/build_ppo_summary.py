"""Summarise BRIDGE training runs per configuration tag (results/ppo_summary.json).

    python scripts/build_ppo_summary.py            # tags: rg (BC warm start + forecast), rgnf (no forecast), scratch (no BC)
Validation KPIs come from each run's own log (validation split only; the test split is never used here).
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.config import ROOT  # noqa: E402

TAGS = {"rg": "BC warm start, forecast", "rgnf": "BC warm start, no forecast", "scratch": "PPO from scratch (no BC), forecast"}


def main():
    out = {}
    for tag, label in TAGS.items():
        runs = [json.load(open(p)) for p in sorted(glob.glob(os.path.join(ROOT, "results", "exp", f"bridge_training_{tag}_s*.json")))]
        if not runs:
            continue
        v = [r["val_kpis"] for r in runs]
        bc = [r.get("bc_val_kpis") or {} for r in runs]
        out[tag] = {"label": label, "n": len(runs),
                    "score_mean": float(np.mean([r["best_val"] for r in runs])), "score_sd": float(np.std([r["best_val"] for r in runs])),
                    "delay": float(np.mean([x["delay_ms"] for x in v])), "delay_sd": float(np.std([x["delay_ms"] for x in v])),
                    "rt": float(np.mean([x["rt_miss"] for x in v])), "rt_sd": float(np.std([x["rt_miss"] for x in v])),
                    "tp": float(np.mean([x["throughput"] for x in v])),
                    "bc_delay": float(np.mean([x["delay_ms"] for x in bc])) if all(bc) else None,
                    "bc_rt": float(np.mean([x["rt_miss"] for x in bc])) if all(bc) else None,
                    "ppo_beats_bc": [bool(r.get("ppo_beats_bc")) for r in runs],
                    "curves": [[row["val_reward"] for row in r["ppo"] if row.get("val_reward") is not None] for r in runs]}
        print(tag, {k: out[tag][k] for k in ("n", "score_mean", "delay", "rt", "ppo_beats_bc")})
    json.dump(out, open(os.path.join(ROOT, "results", "ppo_summary.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
