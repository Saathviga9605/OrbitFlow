"""Run static / reactive / logged baselines on the real NTN trace and save the KPI table."""
import json
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bridge.baselines import LoggedPolicy, ReactiveGreedy, StaticRoundRobin  # noqa: E402
from bridge.evaluate import format_table, run_episode  # noqa: E402
from traffic.dataset import load_trace  # noqa: E402


def main(csv=os.path.join(ROOT, "data/raw/dynamic_ntn_dataset.csv")):
    cfg = yaml.safe_load(open(os.path.join(ROOT, "config.yaml")))
    trace = load_trace(csv)
    N, K, P = trace.N, cfg["scenario"]["k_beams"], cfg["scenario"]["p_max_w"]
    rows = {
        "Static round-robin": run_episode(trace, cfg, StaticRoundRobin(N, K, P)),
        "Reactive (lag 1 slot)": run_episode(trace, cfg, ReactiveGreedy(N, K, P)),
        "Reactive (oracle, lag 0)": run_episode(trace, cfg, ReactiveGreedy(N, K, P), lag=0),
        "Logged rule-based (ref)": run_episode(trace, cfg, LoggedPolicy(trace)),
    }
    cols = ["throughput_mbps", "served_ratio", "packet_loss", "mean_delay_ms", "rt_sla_violation",
            "jain_fairness", "mean_sinr_db", "energy_j", "guard_violation_slots"]
    print(f"demand = {rows['Static round-robin']['demand_mbps']:.1f} Mbps average over {trace.T} slots, {trace.N} cells")
    print(format_table(rows, cols))
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    json.dump(rows, open(os.path.join(ROOT, "results/baselines_dataset.json"), "w"), indent=2)


if __name__ == "__main__":
    main()
