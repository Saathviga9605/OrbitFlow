"""Flood-relief storyline on the real pass geometry. Demand script, notice and border cells are SIMULATED.

  0-14   T0  normal, steady background hotspots
  15-29  T1  demand on the event cell ramps (the precursor a forecaster can use)
  ~25    T2  forecast alert: raised by the supervisor from the live forecast, not scripted
  28     T3  emergency declared: told to the Safety agent (and Supervisor) only
  30-60  T3b surge hold: event cell ~40 Mbps, neighbour ~15 Mbps
  45-60  T4  rain fade on the emergency cells
  50     T5  hypothetical operating constraint: border-cell power cap, told to the Policy agent (and Supervisor) only
  61-76  T6  recovery
  77-99  T7  normal
"""
from __future__ import annotations

import copy

import numpy as np

from scenarios.engine import Event, EventFeed
from traffic.dataset import Trace, load_trace
from traffic.generator import COLD, COLD_STD, HOT, HOT_STD
from utils.config import REAL_TRACE, load_config


def build(base_trace: Trace | None = None, config: dict | None = None, seed: int = 42) -> tuple[Trace, EventFeed]:
    """`config` overrides config.yaml:demo, so changing border cells or the cap changes the scenario."""
    base = base_trace if base_trace is not None else load_trace(REAL_TRACE)
    d = {**load_config()["demo"], **(config or {})}
    trace = copy.deepcopy(base)
    rng = np.random.default_rng(seed)
    T, N = trace.rate.shape
    assert T == 100 and N == 19, f"Expected 100x19 trace, got {T}x{N}"
    ev, em = int(d["event_cell"]), [int(c) for c in d["emergency_cells"]]
    second = next((c for c in em if c != ev), ev)
    end = int(d.get("surge_end", 61))                # first slot after the surge; lets experiments vary the duration
    scale = float(d.get("traffic_scale", 1.0))

    trace.rate = np.maximum(COLD + COLD_STD * rng.standard_normal((T, N)), 0.3)
    trace.hot = np.zeros((T, N))
    trace.emergency = np.zeros((T, N))
    for c in d["background_hot"]:
        trace.rate[:, c] = HOT + HOT_STD * rng.standard_normal(T)
        trace.hot[:, c] = 1

    trace.rate[15:25, ev] = np.linspace(2.2, 15.0, 10)
    trace.rate[25:30, ev] = np.linspace(18.0, 36.0, 5)
    hold = np.arange(30, end)
    trace.rate[hold, ev] = HOT + HOT_STD * rng.standard_normal(len(hold))
    trace.rate[hold, second] = 15.0 + 0.5 * rng.standard_normal(len(hold))
    d1, d2 = min(16, T - end), min(9, T - end)
    trace.rate[end:end + d1, ev] = np.linspace(30.0, 5.0, d1)
    trace.rate[end:end + d2, second] = np.linspace(12.0, 3.0, d2)
    trace.rate = np.maximum(trace.rate * scale, 0.3)
    trace.hot[hold, ev] = 1
    trace.emergency[28:end, em] = 1

    fade = 10 ** (-float(d["fade_db"]) / 10)
    for c in em:
        trace.gain[45:end, c] *= fade
    trace.logged_mask = np.zeros_like(base.logged_mask)
    trace.logged_power = np.zeros_like(base.logged_power)
    trace.source = "scenario:flood_relief (real pass geometry, simulated demand and events)"
    trace.meta = {"kind": "flood_relief", "seed": seed, "event_cell": ev, "emergency_cells": em,
                  "border_cells": [int(c) for c in d["border_cells"]], "border_cap_w": float(d["border_cap_w"]),
                  "fade_db": float(d["fade_db"])}

    events = [
        Event("normal_start", 0, "state", ["all"], f"Normal operation; steady hotspots on cells {list(d['background_hot'])}.",
              {"stage": "T0"}),
        Event("demand_precursor", 15, "demand", ["network"], f"Telemetry: demand on cell {ev} starts climbing.",
              {"stage": "T1", "cell": ev}),
        Event("emergency_declared", 28, "emergency", ["safety", "supervisor"],
              f"Flood declared: cells {em} carry emergency-priority traffic.", {"stage": "T3", "cells": em}),
        Event("channel_fade", 45, "fade", ["all"], f"Rain fade of {d['fade_db']:.0f} dB on cells {em}.",
              {"stage": "T4", "cells": em, "fade_db": float(d["fade_db"])}),
        Event("border_power_cap", 50, "policy", ["policy", "supervisor"],
              f"HYPOTHETICAL operating constraint (not a real law): beams on border cells {d['border_cells']} capped at {d['border_cap_w']:.0f} W.",
              {"stage": "T5", "cells": [int(c) for c in d["border_cells"]], "cap_w": float(d["border_cap_w"]),
               "hypothetical": True}),
        Event("recovery_start", end, "state", ["all"], "Emergency demand receding.", {"stage": "T6"}),
        Event("normal_restored", end + 16, "state", ["all"], "Network back to normal operation.", {"stage": "T7"}),
    ]
    return trace, EventFeed(events)
