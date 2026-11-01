"""BRIDGE: permutation-equivariant actor-critic with Gumbel-Top-K beams and Dirichlet power.

Gumbel-Top-K is a SAMPLER with an exact Plackett-Luce log-probability (Kool et al., 2019);
learning uses the score-function policy gradient. It is not differentiable selection.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Dirichlet

from bam.validator import BamGuard
from bridge.baselines import Action, Policy

N_FEATURES = 19
FORECAST_FEATURES = [12, 13, 14, 15]
RATE_SCALE = 40.0
MASK = 1e4


def build_features(obs: dict, cfg: dict, guard: BamGuard, link, T: int, use_forecast: bool = True) -> np.ndarray:
    """(N, 19) features. Telemetry is already lagged by the twin; nothing here sees the future."""
    s, q, g = cfg["scenario"], cfg["queues"], cfg["timing_guard"]
    rate = obs["rate_obs"]
    N = len(rate)
    p_eq = s["p_max_w"] / s["k_beams"]
    f = np.zeros((N, N_FEATURES), dtype=np.float32)
    f[:, 0] = rate / RATE_SCALE
    f[:, 1] = obs["q_rt"] / q["buffer_rt_kb"]
    f[:, 2] = obs["q_nrt"] / q["buffer_nrt_kb"]
    age = obs["q_rt"] / np.maximum(rate * q["rt_share"], 0.05)
    f[:, 3] = np.minimum(age / q["rt_delay_budget_ms"], 3.0) / 3.0
    snr = p_eq * obs["gain_obs"] * link.gain_lin / link.noise_w
    f[:, 4] = np.clip(10 * np.log10(np.maximum(snr, 1e-9)), -10, 30) / 30.0
    f[:, 5] = obs["los"]
    f[:, 6] = obs["elev"] / 90.0
    f[:, 7] = np.minimum(obs["guard"].ssb_age / g["ssb_max_age_slots"], 1.5)
    f[:, 8] = np.minimum(obs["guard"].sib_age / g["sib_max_age_slots"], 1.5)
    f[:, 9] = guard.due_mask(obs["guard"], obs["ssb"], obs["sib"])
    f[:, 10] = obs["prev_lit"]
    f[:, 11] = obs["prev_power"] / s["p_max_w"]
    fc = obs.get("forecast")
    if use_forecast and fc is not None:
        f[:, 12:15] = fc[:, :3] / RATE_SCALE
        f[:, 15] = np.clip((fc[:, 2] - rate) / RATE_SCALE, -1, 1)
    f[:, 16] = obs["ssb"]
    f[:, 17] = obs["sib"]
    f[:, 18] = obs["t"] / T
    return f


class BridgeNet(nn.Module):
    def __init__(self, hidden: int = 64, dirichlet_offset: float = 1.0):
        super().__init__()
        self.offset = dirichlet_offset
        self.phi = nn.Sequential(nn.Linear(N_FEATURES, hidden), nn.ReLU(), nn.Linear(hidden, hidden), nn.ReLU())
        ctx = hidden * 3
        self.beam = nn.Sequential(nn.Linear(ctx, hidden), nn.ReLU(), nn.Linear(hidden, 1))
        self.conc = nn.Sequential(nn.Linear(ctx, hidden), nn.ReLU(), nn.Linear(hidden, 1))
        self.value = nn.Sequential(nn.Linear(hidden * 2, hidden), nn.ReLU(), nn.Linear(hidden, 1))

    def forward(self, f: torch.Tensor):
        """f: (B, N, F) -> logits (B, N), alpha (B, N), value (B,)."""
        phi = self.phi(f)
        c = torch.cat([phi.mean(1), phi.max(1).values], -1)
        h = torch.cat([phi, c[:, None, :].expand(-1, f.shape[1], -1)], -1)
        z = self.beam(h).squeeze(-1) - MASK * (1 - f[:, :, 5])
        alpha = self.offset + F.softplus(self.conc(h).squeeze(-1))
        return z, alpha, self.value(c).squeeze(-1)


def sample_topk(z: torch.Tensor, k: int) -> torch.Tensor:
    u = torch.rand_like(z).clamp(1e-9, 1 - 1e-9)
    return torch.topk(z - torch.log(-torch.log(u)), k, dim=-1).indices


def plackett_luce_logprob(z: torch.Tensor, order: torch.Tensor) -> torch.Tensor:
    """Exact log P(ordered selection). z (B, N), order (B, K)."""
    remaining = z.clone()
    lp = torch.zeros(z.shape[0], device=z.device)
    rows = torch.arange(z.shape[0])
    for j in range(order.shape[1]):
        s = order[:, j]
        lp = lp + z[rows, s] - torch.logsumexp(remaining, dim=-1)
        remaining = remaining.clone()
        remaining[rows, s] = -1e9
    return lp


def power_logprob(alpha: torch.Tensor, order: torch.Tensor, w: torch.Tensor):
    a = alpha.gather(1, order)
    d = Dirichlet(a)
    w = w.clamp(1e-4, 1.0)
    w = w / w.sum(-1, keepdim=True)
    return d.log_prob(w), d.entropy()


def to_watts(w: np.ndarray, p_min: float, p_total: float) -> np.ndarray:
    w = np.asarray(w, dtype=float)       # float32 network output would overshoot Pmax by rounding
    return p_min + (p_total - len(w) * p_min) * (w / w.sum())


class BridgePolicy(Policy):
    """Drop-in controller. Its priority output is what the guard uses if it must drop a beam."""

    def __init__(self, cfg: dict, ckpt: str, use_forecast: bool = True, name: str = "BRIDGE (PPO)"):
        from digital_twin.channel import LinkModel
        self.cfg, self.use_forecast, self.name = cfg, use_forecast, name
        self.net = BridgeNet(dirichlet_offset=cfg["bridge"]["dirichlet_offset"])
        self.net.load_state_dict(torch.load(ckpt, map_location="cpu", weights_only=True))
        self.net.eval()
        self.guard, self.link = BamGuard(cfg), LinkModel(cfg)
        self.K = cfg["scenario"]["k_beams"]
        self.pmax, self.pmin = cfg["scenario"]["p_max_w"], cfg["scenario"]["p_min_w"]
        self.T = 100

    @torch.no_grad()
    def act(self, obs: dict) -> Action:
        f = build_features(obs, self.cfg, self.guard, self.link, self.T, self.use_forecast)
        z, alpha, _ = self.net(torch.from_numpy(f)[None])
        z, alpha = z[0].numpy(), alpha[0].numpy()
        order = np.argsort(-z)[: self.K]
        w = alpha[order] / alpha[order].sum()
        lit = np.zeros(len(z), bool)
        lit[order] = True
        power = np.zeros(len(z))
        power[order] = to_watts(w, self.pmin, self.pmax)
        return Action(lit, power, priority=z, info={"order": order.tolist(), "logits": z})


class HeuristicPredictive(Policy):
    """Hand-written rule using the same features: the BC teacher, reported so DRL's gain over a rule is visible."""
    name = "Heuristic-predictive"

    def __init__(self, cfg: dict, use_forecast: bool = True):
        from digital_twin.channel import LinkModel
        self.cfg, self.use_forecast = cfg, use_forecast
        self.guard, self.link = BamGuard(cfg), LinkModel(cfg)
        self.K = cfg["scenario"]["k_beams"]
        self.pmax, self.pmin = cfg["scenario"]["p_max_w"], cfg["scenario"]["p_min_w"]

    def score(self, f: np.ndarray) -> np.ndarray:
        s = 1.5 * f[:, 3] + f[:, 1] + f[:, 2] + 3.0 * np.maximum(f[:, 12:15].max(1) - f[:, 0], 0) + 0.8 * f[:, 9]
        return np.where(f[:, 5] > 0, s, -1e3)

    def act(self, obs: dict) -> Action:
        f = build_features(obs, self.cfg, self.guard, self.link, 100, self.use_forecast)
        s = self.score(f)
        order = np.argsort(-s)[: self.K]
        e = np.exp((s[order] - s[order].max()) / 0.5)
        w = e / e.sum()
        lit = np.zeros(len(s), bool)
        lit[order] = True
        power = np.zeros(len(s))
        power[order] = to_watts(w, self.pmin, self.pmax)
        return Action(lit, power, priority=s, info={"order": order.tolist(), "w": w, "f": f})
