"""Synthetic demand scenarios, calibrated to the real NTN trace.

Calibration from open_ntn_traffic_dataset.csv (58 cells): hotspot ~ 181 Mbps (pass mean; slot-to-slot noise ~2.2),
background cell ~ 16.2 Mbps (pass mean), 6 hotspots at a time. In the export every cell's demand ramps up through
the pass; the generator uses pass-average levels and the same noise-to-level ratios as the 19-cell calibration. The satellite pass (elevation, LOS, SSB/SIB schedule,
channel gain) is re-used from the real trace; only demand and fading jitter are randomised.

Scenario kinds
  normal       balanced load, no hotspots
  block        dataset-like: 3-4 hotspots that switch abruptly every ~30 slots (NOT forecastable)
  event_surge  hotspots with a ramp-up precursor, hold, and decay (forecastable)
  bursty       short random bursts on random cells
  mixed        one steady background hotspot + an event surge elsewhere (demo scenario)
"""
from __future__ import annotations

import copy

import numpy as np

from traffic.dataset import Trace

COLD, HOT = 16.2, 181.0
COLD_STD, HOT_STD = 0.9, 2.2


def _base_noise(T: int, N: int, rng) -> np.ndarray:
    return np.maximum(COLD + COLD_STD * rng.standard_normal((T, N)), 0.05 * COLD)


def _stamp(rate, hot, cell, lo, hi, profile):
    hi = min(hi, rate.shape[0])
    prof = profile[: hi - lo]
    lift = COLD + (HOT - COLD) * prof
    rate[lo:hi, cell] = np.maximum(rate[lo:hi, cell], lift + HOT_STD * rng_noise(len(prof)))
    hot[lo:hi, cell] = np.maximum(hot[lo:hi, cell], (prof > 0.5).astype(float))


_rng_state = {"rng": np.random.default_rng(0)}


def rng_noise(n: int) -> np.ndarray:
    return _rng_state["rng"].standard_normal(n)


def _event_profile(ramp: int, hold: int, decay: int) -> np.ndarray:
    up = np.linspace(0.05, 1.0, ramp)
    down = np.linspace(1.0, 0.05, decay)
    return np.concatenate([up, np.ones(hold), down])


def make_rate(kind: str, T: int, N: int, rng) -> tuple[np.ndarray, np.ndarray]:
    _rng_state["rng"] = rng
    rate = _base_noise(T, N, rng)
    hot = np.zeros((T, N))
    if kind == "normal":
        rate *= 1.5                                   # balanced, a bit busier than the background level
    elif kind == "block":
        t = 0
        while t < T:
            dur = int(rng.integers(25, 36))
            for c in rng.choice(N, int(rng.integers(3, 5)), replace=False):
                _stamp(rate, hot, c, t, t + dur, np.ones(dur))
            t += dur
    elif kind in ("event_surge", "mixed"):
        if kind == "mixed":
            _stamp(rate, hot, int(rng.integers(N)), 0, T, np.ones(T))   # steady background hotspot
        for c in rng.choice(N, int(rng.integers(2, 4)), replace=False):
            ramp, hold, decay = int(rng.integers(8, 16)), int(rng.integers(15, 30)), int(rng.integers(6, 12))
            start = int(rng.integers(10, max(11, T - ramp - hold - decay - 5)))
            prof = _event_profile(ramp, hold, decay)
            _stamp(rate, hot, c, start, start + len(prof), prof)
    elif kind == "bursty":
        for c in range(N):
            t = 0
            while t < T:
                if rng.random() < 0.03:
                    dur, mag = int(rng.integers(3, 9)), rng.uniform(10, 40)
                    rate[t:t + dur, c] += mag
                    hot[t:t + dur, c] = 1
                    t += dur
                t += 1
    else:
        raise ValueError(f"unknown scenario kind: {kind}")
    return rate, hot


def demand_envelope(base: Trace) -> np.ndarray:
    """(T,) pass envelope of background demand, mean 1. In the 58-cell export every cell's requested rate
    ramps up as the satellite rises (traffic is handed to it as it becomes the serving satellite), from
    ~2% to ~180% of the pass mean. Synthetic demand follows the same envelope so that, as in the data,
    load grows with visibility instead of arriving while almost no cell is in line of sight."""
    hot = base.hot.max(axis=0) > 0 if base.hot is not None else np.zeros(base.N, bool)
    cold = base.rate[:, ~hot] if (~hot).any() else base.rate
    env = np.median(cold, axis=1)
    return env / max(env.mean(), 1e-9)


def make_trace(kind: str, base: Trace, seed: int, fading_jitter_db: float = 1.0) -> Trace:
    rng = np.random.default_rng(seed)
    rate, hot = make_rate(kind, base.T, base.N, rng)
    rate = np.maximum(rate * demand_envelope(base)[:, None], 0.05 * COLD)
    t = copy.deepcopy(base)
    t.rate, t.hot = rate, hot
    t.gain = base.gain * 10 ** (fading_jitter_db * rng.standard_normal(base.gain.shape) / 10)
    t.logged_mask = np.zeros_like(base.logged_mask)
    t.logged_power = np.zeros_like(base.logged_power)
    t.source = f"synthetic:{kind}:seed{seed}"
    t.meta = {"kind": kind, "seed": seed}
    return t


def make_dataset(kinds: list[str], base: Trace, n_per_kind: int, seed0: int = 1000) -> list[Trace]:
    out = []
    for i, k in enumerate(kinds):
        for j in range(n_per_kind):
            out.append(make_trace(k, base, seed0 + 1000 * i + j))
    return out
