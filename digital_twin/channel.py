"""Link-budget channel model (Sionna-compatible interface, no live Sionna dependency).

SINR is rebuilt from the dataset's `channel_gain_magnitude` (linear path loss + fading, Sionna export)
and the transmit power the controller chooses. Swap `antenna_gain_db` / bandwidth for the ECE link budget.

Interference (config `link.isolation_model`):
  uniform   every other lit beam leaks into a cell at `interference_isolation_db` (the 19-cell model)
  distance  adjacent beams leak at `interference_isolation_db`; each further hex ring adds
            `isolation_per_ring_db`, capped at `isolation_floor_db`. Used for the 58-cell, three-region
            footprint, where uniform leakage across ~15 km would cap every cell's SINR at ~9.6 dB.
Decodability (config `link.require_los`): true = a cell without line of sight is never served (19-cell model);
false = SINR alone decides, using the Sionna NLOS gain in the dataset (about 19 dB below LOS).
"""
from __future__ import annotations

import numpy as np

K_BOLTZMANN = 1.380649e-23


def isolation_matrix(coords, adjacent_db: float, per_ring_db: float, floor_db: float) -> np.ndarray:
    """(N, N) linear leakage eps[i, j] from a beam on cell j into cell i (0 on the diagonal)."""
    xy = np.array([[c["x"], c["y"]] for c in coords], dtype=float)
    d = np.hypot(*(xy[:, None, :] - xy[None, :, :]).transpose(2, 0, 1))
    nn = np.where(d > 0, d, np.inf).min(axis=1)
    pitch = float(np.median(nn))           # median nearest-neighbour distance: region seams have closer, overlapping cells
    rings = np.maximum(np.round(d / pitch), 1.0)                       # 1 = adjacent cell
    iso_db = np.minimum(adjacent_db + per_ring_db * (rings - 1), floor_db)
    eps = 10 ** (-iso_db / 10)
    np.fill_diagonal(eps, 0.0)
    return eps


class LinkModel:
    _EPS_CACHE: dict = {}

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
        self.require_los = bool(link.get("require_los", True))
        self.eps_mat = None
        if link.get("isolation_model", "uniform") == "distance":
            key = (link["interference_isolation_db"], link["isolation_per_ring_db"], link["isolation_floor_db"])
            if key not in self._EPS_CACHE:
                from traffic.dataset import load_cell_coords
                self._EPS_CACHE[key] = isolation_matrix(load_cell_coords(), *key)
            self.eps_mat = self._EPS_CACHE[key]

    def interference(self, p: np.ndarray, gain: np.ndarray) -> np.ndarray:
        if self.eps_mat is not None and self.eps_mat.shape[0] == len(p):
            return self.gain_lin * gain * (self.eps_mat @ p)
        return self.eps * self.gain_lin * gain * (p.sum() - p)

    def sinr(self, power_w: np.ndarray, gain: np.ndarray, lit: np.ndarray) -> np.ndarray:
        """Per-cell SINR (linear). Unlit cells return 0."""
        p = np.where(lit, power_w, 0.0)
        signal = p * gain * self.gain_lin
        return np.where(lit, signal / (self.noise_w + self.interference(p, gain)), 0.0)

    def capacity_mbps(self, sinr: np.ndarray, los: np.ndarray, ssb: float, sib: float) -> np.ndarray:
        decodable = sinr >= self.sinr_min
        if self.require_los:
            decodable &= los > 0
        overhead = 1.0 - self.ssb_oh * ssb - self.sib_oh * sib
        cap = self.bw_hz * np.log2(1.0 + sinr) / 1e6 * overhead
        return np.where(decodable, cap, 0.0)


def to_db(x: np.ndarray) -> np.ndarray:
    return 10 * np.log10(np.maximum(x, 1e-12))
