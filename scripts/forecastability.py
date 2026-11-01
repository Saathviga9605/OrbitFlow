"""How forecastable is demand? Compare persistence vs 2-point linear extrapolation, h slots ahead.

If extrapolation does not beat persistence, a learned predictor has nothing to exploit."""
import os
import sys

import numpy as np
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from traffic.dataset import load_trace  # noqa: E402
from traffic.generator import make_trace  # noqa: E402


def errors(rate: np.ndarray, h: int = 3, w: int = 4, jump: float = 5.0):
    """MAE of persistence vs smoothed-slope extrapolation, h slots ahead, counted only where
    demand actually moves by more than `jump` Mbps (the moments a forecast has to get right)."""
    T = rate.shape[0]
    x = np.arange(w) - (w - 1) / 2.0
    pers, extr = [], []
    for t in range(w, T - h):
        win = rate[t - w + 1: t + 1]
        slope = (x[:, None] * (win - win.mean(0))).sum(0) / (x ** 2).sum()
        pred = np.maximum(rate[t] + h * slope, 0)
        target = rate[t + h]
        moving = np.abs(target - rate[t]) > jump
        if moving.any():
            pers.append(np.abs(rate[t] - target)[moving])
            extr.append(np.abs(pred - target)[moving])
    if not pers:
        return float("nan"), float("nan")
    return np.concatenate(pers).mean(), np.concatenate(extr).mean()


def main():
    base = load_trace(os.path.join(ROOT, "data/raw/dynamic_ntn_dataset.csv"))
    print(f"{'scenario':<22}{'persist MAE@jumps':>17}{'extrap MAE@jumps':>19}{'gain':>8}")
    p, e = errors(base.rate)
    print(f"{'real dataset':<22}{p:17.3f}{e:19.3f}{(1 - e / p) * 100:7.0f}%")
    for kind in ["block", "event_surge", "mixed", "bursty"]:
        ps, es = [], []
        for s in range(30):
            p, e = errors(make_trace(kind, base, 500 + s).rate)
            ps.append(p), es.append(e)
        p, e = np.mean(ps), np.mean(es)
        print(f"{'synthetic ' + kind:<22}{p:17.3f}{e:19.3f}{(1 - e / p) * 100:7.0f}%")


if __name__ == "__main__":
    main()
