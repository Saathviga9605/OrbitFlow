"""Link-budget channel model (Sionna-compatible interface, no live Sionna dependency).

The dataset's `subchannel_sinr_db` is constant -30, so SINR is rebuilt here from the
dataset's `channel_gain_magnitude` (linear path loss + fading) and the transmit power
the controller chooses. Swap `antenna_gain_db` / bandwidth for the ECE link budget.
"""
from __future__ import annotations

import numpy as np

K_BOLTZMANN = 1.380649e-23


class LinkModel:
    def __init__(self, cfg: dict):
        link = cfg["link"]
        self.bw_hz = link["bandwidth_mhz"] * 1e6
        self.gain_lin = 10 ** (link["antenna_gain_db"] / 10)
        nf = 10 ** (link["noise_figure_db"] / 10)
        self.noise_w = K_BOLTZMANN * link["temperature_k"] * self.bw_hz * nf
        self.eps = 10 ** (-link["interference_isolation_db"] / 10)
        self.sinr_min = 10 ** (link["sinr_min_db"] / 10)
        self.ssb_oh = link["ssb_overhead"]
        self.sib_oh = link["sib_overhead"]

    def sinr(self, power_w: np.ndarray, gain: np.ndarray, lit: np.ndarray) -> np.ndarray:
        """Per-cell SINR (linear). Unlit cells return 0."""
        p = np.where(lit, power_w, 0.0)
        signal = p * gain * self.gain_lin
        interf = self.eps * self.gain_lin * gain * (p.sum() - p)
        return np.where(lit, signal / (self.noise_w + interf), 0.0)

    def capacity_mbps(self, sinr: np.ndarray, los: np.ndarray, ssb: float, sib: float) -> np.ndarray:
        decodable = (sinr >= self.sinr_min) & (los > 0)
        overhead = 1.0 - self.ssb_oh * ssb - self.sib_oh * sib
        cap = self.bw_hz * np.log2(1.0 + sinr) / 1e6 * overhead
        return np.where(decodable, cap, 0.0)


def to_db(x: np.ndarray) -> np.ndarray:
    return 10 * np.log10(np.maximum(x, 1e-12))
