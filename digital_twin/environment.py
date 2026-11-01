"""NTN digital twin: steps a demand/channel trace slot by slot under a beam+power decision.

Per slot:  arrivals -> SINR -> capacity -> serve RT first, then NRT -> overflow drops -> KPIs.
The controller sees telemetry that is `obs_lag_slots` old (E2 report delay); geometry
(elevation, LOS) and the SSB/SIB schedule are ephemeris/config and are known exactly.
"""
from __future__ import annotations

import copy

import numpy as np

from bam.validator import GuardState
from digital_twin.channel import LinkModel, to_db
from traffic.dataset import Trace


class NTNTwin:
    def __init__(self, trace: Trace, cfg: dict):
        self.trace = trace
        self.cfg = cfg
        s, q = cfg["scenario"], cfg["queues"]
        self.N, self.T = trace.N, trace.T
        self.K = int(s["k_beams"])
        self.p_max = float(s["p_max_w"])
        self.slot_ms = float(trace.slot_ms)
        self.lag = int(s["obs_lag_slots"])
        self.rt_share = float(q["rt_share"])
        self.buf_rt = float(q["buffer_rt_kb"])
        self.buf_nrt = float(q["buffer_nrt_kb"])
        self.rt_budget = float(q["rt_delay_budget_ms"])
        self.link = LinkModel(cfg)
        self.reset()

    # ------------------------------------------------------------------ state
    def reset(self) -> dict:
        self.t = 0
        init_kb = self.trace.rate[0] * float(self.cfg["queues"]["init_backlog_ms"])   # Mbps x ms = kb
        self.q_rt = init_kb * self.rt_share
        self.q_nrt = init_kb * (1 - self.rt_share)
        self.guard_state = GuardState.fresh(self.N)
        self.prev_lit = np.zeros(self.N, bool)
        self.prev_power = np.zeros(self.N)
        self.history: list[dict] = []
        return self.obs()

    @property
    def done(self) -> bool:
        return self.t >= self.T

    def obs(self) -> dict:
        t, tr = self.t, self.trace
        tc = min(t, self.T - 1)            # terminal observation re-uses the last slot
        ti = max(tc - self.lag, 0)
        return {
            "t": t,
            "slot_ms": self.slot_ms,
            "rate_obs": tr.rate[ti].copy(),                 # last demand the controller has seen
            "rate_hist": tr.rate[: ti + 1].copy(),          # observed demand history (for the predictor)
            "gain_obs": tr.gain[ti].copy(),                 # lagged CSI
            "q_rt": self.q_rt.copy(),
            "q_nrt": self.q_nrt.copy(),
            "los": tr.los[tc].copy(),                       # ephemeris
            "elev": tr.elev[tc].copy(),                     # ephemeris
            "ssb": float(tr.ssb[tc]),
            "sib": float(tr.sib[tc]),
            "prev_lit": self.prev_lit.copy(),
            "prev_power": self.prev_power.copy(),
            "guard": self.guard_state.copy(),
            "emergency": tr.emergency[tc].copy(),           # emergency priority flags
            "forecast": tr.forecast[tc].copy() if tr.forecast is not None else None,  # demand forecast if available
        }

    # ------------------------------------------------------------------- step
    def step(self, lit: np.ndarray, power: np.ndarray) -> dict:
        t, tr = self.t, self.trace
        lit = np.asarray(lit, bool)
        power = np.where(lit, np.asarray(power, float), 0.0)

        arr_kb = tr.rate[t] * self.slot_ms                  # 1 Mbps = 1 kb/ms
        self.q_rt += arr_kb * self.rt_share
        self.q_nrt += arr_kb * (1 - self.rt_share)

        sinr = self.link.sinr(power, tr.gain[t], lit)
        cap_mbps = self.link.capacity_mbps(sinr, tr.los[t], tr.ssb[t], tr.sib[t])
        cap_kb = cap_mbps * self.slot_ms
        srv_rt = np.minimum(self.q_rt, cap_kb)
        srv_nrt = np.minimum(self.q_nrt, cap_kb - srv_rt)
        self.q_rt -= srv_rt
        self.q_nrt -= srv_nrt

        drop_rt = np.maximum(self.q_rt - self.buf_rt, 0.0)
        drop_nrt = np.maximum(self.q_nrt - self.buf_nrt, 0.0)
        self.q_rt -= drop_rt
        self.q_nrt -= drop_nrt

        rate_sum = max(float(tr.rate[t].sum()), 1e-6)
        delay_ms = float((self.q_rt + self.q_nrt).sum() / rate_sum)          # Little's law, system level
        rt_delay_cell = self.q_rt / np.maximum(tr.rate[t] * self.rt_share, 1e-6)
        rt_viol = float((rt_delay_cell > self.rt_budget).mean())
        
        # Emergency SLA violation: fraction of emergency cells over RT budget
        emergency_cells = tr.emergency[t] > 0
        if emergency_cells.any():
            emergency_rt_viol = float((rt_delay_cell[emergency_cells] > self.rt_budget).mean())
        else:
            emergency_rt_viol = float("nan")

        served = srv_rt + srv_nrt
        rec = {
            "t": t,
            "lit": lit.copy(),
            "power": power.copy(),
            "sinr_db": to_db(sinr),
            "cap_mbps": cap_mbps,
            "arrived_kb": arr_kb,
            "served_kb": served,
            "served_rt_kb": srv_rt,
            "dropped_kb": drop_rt + drop_nrt,
            "q_rt": self.q_rt.copy(),
            "q_nrt": self.q_nrt.copy(),
            "delay_ms": delay_ms,
            "rt_violation": rt_viol,
            "emergency_rt_violation": emergency_rt_viol,
            "throughput_mbps": float(served.sum() / self.slot_ms),
            "energy_j": float(power.sum() * self.slot_ms / 1000.0),
            "switches": int((lit & ~self.prev_lit).sum()),
        }
        self.guard_state.advance(lit, float(tr.ssb[t]), float(tr.sib[t]))
        self.prev_lit, self.prev_power = lit.copy(), power.copy()
        self.history.append(rec)
        self.t += 1
        return rec


def summarise(history: list[dict], slot_ms: float, extra: dict | None = None) -> dict:
    """Episode KPIs from a list of per-slot records."""
    arr = np.sum([h["arrived_kb"] for h in history], axis=0)
    srv = np.sum([h["served_kb"] for h in history], axis=0)
    drop = np.sum([h["dropped_kb"] for h in history], axis=0)
    ratio = srv / np.maximum(arr, 1e-9)
    jain = float(ratio.sum() ** 2 / (len(ratio) * (ratio ** 2).sum() + 1e-12))
    sinr_lit = np.concatenate([h["sinr_db"][h["lit"] & (h["cap_mbps"] > 0)] for h in history] or [np.array([])])
    n = len(history)
    
    # Emergency metrics
    emergency_rt_viols = [h["emergency_rt_violation"] for h in history if not np.isnan(h["emergency_rt_violation"])]
    emergency_served_kbs = [h["served_kb"] for h in history]  # per-cell served
    
    out = {
        "throughput_mbps": float(np.mean([h["throughput_mbps"] for h in history])),
        "demand_mbps": float(arr.sum() / (n * slot_ms)),
        "served_ratio": float(srv.sum() / max(arr.sum(), 1e-9)),
        "packet_loss": float(drop.sum() / max(arr.sum(), 1e-9)),
        "mean_delay_ms": float(np.mean([h["delay_ms"] for h in history])),
        "p95_delay_ms": float(np.percentile([h["delay_ms"] for h in history], 95)),
        "rt_sla_violation": float(np.mean([h["rt_violation"] for h in history])),
        "emergency_rt_violation": float(np.mean(emergency_rt_viols)) if emergency_rt_viols else float("nan"),
        "jain_fairness": jain,
        "mean_sinr_db": float(sinr_lit.mean()) if len(sinr_lit) else float("nan"),
        "energy_j": float(np.sum([h["energy_j"] for h in history])),
        "beam_switches_per_slot": float(np.mean([h["switches"] for h in history])),
        "useful_beam_share": float(np.mean([(h["served_kb"][h["lit"]] > 0).mean() if h["lit"].any() else 0.0 for h in history])),
    }
    if extra:
        out.update(extra)
    return out
