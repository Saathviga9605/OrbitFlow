"""Residual GRU demand forecaster (spec M3): default behaviour is persistence, it can only add information.

Timing contract: at slot t the controller has seen demand up to t-lag; forecast[t] predicts t, t+1, t+2.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn

RATE_SCALE = 40.0
N_INPUT = 6


def window_features(rate: np.ndarray, window: int) -> np.ndarray:
    """(T, N) observed demand -> (T, N, W, 6) inputs, where row t only uses rate[:t+1]."""
    T, N = rate.shape
    pad = np.concatenate([np.repeat(rate[:1], window - 1, axis=0), rate], axis=0)
    idx = np.arange(window)[None, :] + np.arange(T)[:, None]
    win = np.transpose(pad[idx], (0, 2, 1))                  # (T, N, W)
    diff = np.diff(win, axis=2, prepend=win[:, :, :1])
    mean = win.mean(axis=2, keepdims=True)
    std = win.std(axis=2, keepdims=True)
    total = win.sum(axis=1, keepdims=True) / (N * RATE_SCALE)
    rising = (diff > 0).mean(axis=1, keepdims=True)
    return np.stack([
        win / RATE_SCALE, diff / 10.0,
        np.broadcast_to(mean / RATE_SCALE, win.shape), np.broadcast_to(std / 10.0, win.shape),
        np.broadcast_to(total, win.shape), np.broadcast_to(rising, win.shape),
    ], axis=-1).astype(np.float32)


class ResidualGRU(nn.Module):
    def __init__(self, hidden: int = 64, horizon: int = 3):
        super().__init__()
        self.gru = nn.GRU(N_INPUT, hidden, batch_first=True)
        self.head = nn.Sequential(nn.Linear(hidden, 32), nn.ReLU(), nn.Linear(32, horizon))
        nn.init.zeros_(self.head[-1].weight)
        nn.init.zeros_(self.head[-1].bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, h = self.gru(x)
        return self.head(h[-1])            # normalised residual over the last observation


class Forecaster:
    name = "GRU (residual)"

    def __init__(self, cfg: dict):
        p = cfg["predictor"]
        self.window, self.horizon = p["window"], p["horizon"]
        self.net = ResidualGRU(p["hidden"], p["horizon"])

    @classmethod
    def load(cls, cfg: dict, path: str) -> "Forecaster":
        f = cls(cfg)
        f.net.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
        f.net.eval()
        return f

    @torch.no_grad()
    def predict_trace(self, trace, lag: int = 1) -> np.ndarray:
        """(T, N, H); forecast[t] uses only rate[:t-lag+1] (tests/test_forecast_leak.py)."""
        T, N = trace.rate.shape
        obs_idx = np.maximum(np.arange(T) - lag, 0)
        feats = window_features(trace.rate, self.window)[obs_idx]        # row t is what was seen at t-lag
        last = trace.rate[obs_idx]
        delta = self.net(torch.from_numpy(feats.reshape(T * N, self.window, N_INPUT))).numpy()
        pred = last[..., None] + RATE_SCALE * delta.reshape(T, N, self.horizon)
        return np.maximum(pred, 0.0).astype(np.float32)


def persistence_trace(trace, lag: int = 1, horizon: int = 3) -> np.ndarray:
    last = trace.rate[np.maximum(np.arange(trace.T) - lag, 0)]
    return np.repeat(last[..., None], horizon, axis=-1)


def gate_forecast(trace, forecast: np.ndarray, lag: int = 1, window: int = 5, limit_mbps: float = 5.0) -> np.ndarray:
    """Causal uncertainty gate: a cell whose recent forecast error is large falls back to repeat-last.

    The error at slot t only compares earlier forecasts with demand already observed by t-lag.
    """
    T, N, H = forecast.shape
    out = forecast.copy()
    last = trace.rate[np.maximum(np.arange(T) - lag, 0)]
    err = np.abs(forecast[:, :, 0] - trace.rate)     # err[o] = |forecast made for slot o - demand at slot o|
    for t in range(T):
        o = t - lag
        if o < 0:
            continue
        recent = err[max(0, o - window + 1):o + 1].mean(axis=0)
        mask = recent > limit_mbps
        out[t, mask] = last[t, mask][:, None]
    return out


def prepare_forecast(fc: "Forecaster", trace, cfg: dict) -> np.ndarray:
    f = fc.predict_trace(trace, 1)
    return gate_forecast(trace, f, 1) if cfg["predictor"].get("gate") else f
