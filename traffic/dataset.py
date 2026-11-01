"""Load the NTN CSV into dense (T, N) arrays the digital twin can step through."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class Trace:
    rate: np.ndarray            # (T, N) requested rate, Mbps
    gain: np.ndarray            # (T, N) linear channel gain (path loss + fading)
    los: np.ndarray             # (T, N) 1 = visible
    elev: np.ndarray            # (T, N) elevation, degrees
    ssb: np.ndarray             # (T,) 1 = SSB slot
    sib: np.ndarray             # (T,) 1 = SIB slot
    prach: np.ndarray           # (T,)
    hot: np.ndarray             # (T, N) ground-truth hotspot flag
    logged_mask: np.ndarray     # (T, N) beam mask logged in the dataset
    logged_power: np.ndarray    # (T, N) power logged in the dataset, W
    q0_rt_kb: np.ndarray        # (N,) initial RT queue
    q0_nrt_kb: np.ndarray       # (N,) initial NRT queue
    emergency: np.ndarray       # (T, N) emergency priority flag (0/1, default zeros)
    forecast: np.ndarray | None # (T, N, H) demand forecast or None if not available
    events: list                # List of events relevant to this trace
    slot_ms: float
    source: str = "dataset"
    meta: dict = field(default_factory=dict)

    @property
    def T(self) -> int:
        return self.rate.shape[0]

    @property
    def N(self) -> int:
        return self.rate.shape[1]


def load_trace(path: str) -> Trace:
    df = pd.read_csv(path).sort_values(["slot_id", "cell_id"])

    def piv(col: str, fill_value: float = 0.0) -> np.ndarray:
        """Pivot a column to (slot, cell) array. If column doesn't exist, return zeros."""
        if col not in df.columns:
            T = int(df.slot_id.max()) + 1
            N = int(df.cell_id.max()) + 1
            return np.full((T, N), fill_value, dtype=float)
        return df.pivot(index="slot_id", columns="cell_id", values=col).to_numpy(dtype=float)

    def per_slot(col: str, fill_value: float = 0.0) -> np.ndarray:
        """Get per-slot value. If column doesn't exist, return default."""
        if col not in df.columns:
            T = int(df.slot_id.max()) + 1
            return np.full(T, fill_value, dtype=float)
        return df.groupby("slot_id")[col].first().to_numpy(dtype=float)

    # Determine slot_ms: if timestamp_ms exists, calculate it; otherwise default to 10 ms
    if "timestamp_ms" in df.columns:
        slot_ms = float(np.diff(np.sort(df["timestamp_ms"].unique())).mean())
    else:
        slot_ms = 10.0  # Default: 10 ms per slot

    first = df[df.slot_id == df.slot_id.min()].sort_values("cell_id")
    T = int(df.slot_id.max()) + 1
    N = int(df.cell_id.max()) + 1
    
    return Trace(
        rate=piv("requested_rate_mbps"),
        gain=piv("channel_gain_magnitude"),
        los=piv("los_visibility_flag"),
        elev=piv("elevation_angle_deg"),
        ssb=per_slot("ssb_active_flag"),
        sib=per_slot("sib_active_flag"),
        prach=per_slot("prach_window_flag"),
        hot=piv("is_hotspot"),
        logged_mask=piv("active_beam_mask"),
        logged_power=piv("power_allocation_watts"),
        q0_rt_kb=first.queue_length_rt_kb.to_numpy(dtype=float) if "queue_length_rt_kb" in df.columns else np.zeros(N),
        q0_nrt_kb=first.queue_length_nrt_kb.to_numpy(dtype=float) if "queue_length_nrt_kb" in df.columns else np.zeros(N),
        emergency=np.zeros((T, N), dtype=float),
        forecast=None,
        events=[],
        slot_ms=slot_ms,
        source=str(path),
    )


def load_openntn_sionna(root: str) -> Trace:
    """Second offline trace: demand and flags from open_ntn_l2_output.csv, gain and geometry from sionna_physics_output.csv.

    Both are simulator exports. Nothing here runs Sionna or OpenNTN live.
    """
    import os
    o = pd.read_csv(os.path.join(root, "data", "raw", "open_ntn_l2_output.csv")).sort_values(["slot_id", "cell_id"])
    p = pd.read_csv(os.path.join(root, "data", "raw", "sionna_physics_output.csv")).sort_values(["slot_id", "cell_id"])
    piv = lambda d, c: d.pivot(index="slot_id", columns="cell_id", values=c).to_numpy(dtype=float)
    first = o[o.slot_id == o.slot_id.min()]
    T, N = piv(o, "requested_rate_mbps").shape
    flag = lambda c: o.groupby("slot_id")[c].first().to_numpy(dtype=float)
    return Trace(rate=piv(o, "requested_rate_mbps"), gain=piv(p, "channel_gain_magnitude"), los=piv(p, "los_visibility_flag"), elev=piv(p, "elevation_angle_deg"),
                 ssb=flag("ssb_active_flag"), sib=flag("sib_active_flag"), prach=flag("prach_window_flag"), hot=piv(o, "is_hotspot"),
                 logged_mask=np.zeros((T, N)), logged_power=np.zeros((T, N)), q0_rt_kb=first.queue_length_rt_kb.to_numpy(dtype=float),
                 q0_nrt_kb=first.queue_length_nrt_kb.to_numpy(dtype=float), emergency=np.zeros((T, N)), forecast=None, events=[], slot_ms=10.0,
                 source="open_ntn_l2_output.csv + sionna_physics_output.csv")


def load_slant_km(path: str | None = None) -> np.ndarray:
    """(T, N) slant range from the dataset, for flux-density calculations."""
    import os
    path = path or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw", "dynamic_ntn_dataset.csv")
    df = pd.read_csv(path)
    return df.pivot(index="slot_id", columns="cell_id", values="slant_range_km").to_numpy(dtype=float)
