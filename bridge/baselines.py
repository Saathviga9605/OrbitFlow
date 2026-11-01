"""Baseline controllers. Each policy maps a twin observation to a beam/power proposal."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Action:
    lit: np.ndarray        # (N,) bool
    power: np.ndarray      # (N,) W
    priority: np.ndarray   # (N,) ranking the guard uses if it must drop a beam
    info: dict | None = None


class Policy:
    name = "policy"

    def reset(self) -> None:  # noqa: D401
        pass

    def act(self, obs: dict) -> Action:
        raise NotImplementedError


class StaticRoundRobin(Policy):
    """Fixed hopping pattern: K cells per slot cycling through all cells, equal power."""
    name = "Static (round-robin)"

    def __init__(self, n_cells: int, k: int, p_max: float):
        self.N, self.K, self.p_max = n_cells, k, p_max

    def act(self, obs: dict) -> Action:
        t = obs["t"]
        idx = (t * self.K + np.arange(self.K)) % self.N
        lit = np.zeros(self.N, bool)
        lit[idx] = True
        power = np.where(lit, self.p_max / self.K, 0.0)
        return Action(lit, power, priority=np.zeros(self.N))


class ReactiveGreedy(Policy):
    """Uses only current/observed state: light the K cells with the largest expected backlog."""
    name = "Reactive (greedy on backlog)"

    def __init__(self, n_cells: int, k: int, p_max: float, rt_weight: float = 2.0):
        self.N, self.K, self.p_max, self.rt_w = n_cells, k, p_max, rt_weight

    def scores(self, obs: dict) -> np.ndarray:
        expected = obs["q_rt"] * self.rt_w + obs["q_nrt"] + obs["rate_obs"] * obs["slot_ms"]
        return np.where(obs["los"] > 0, expected, 0.0)

    def act(self, obs: dict) -> Action:
        s = self.scores(obs)
        idx = np.argsort(-s)[: self.K]
        lit = np.zeros(self.N, bool)
        lit[idx] = True
        w = np.sqrt(np.maximum(s, 1e-9)) * lit
        power = w / w.sum() * self.p_max
        return Action(lit, power, priority=s)


class LoggedPolicy(Policy):
    """The rule-based allocation stored in the dataset. NON-CAUSAL: it switches on the same
    slot the hotspot appears, so it is a reference, not a deployable baseline."""
    name = "Logged rule-based (non-causal reference)"

    def __init__(self, trace):
        self.trace = trace

    def act(self, obs: dict) -> Action:
        t = obs["t"]
        lit = self.trace.logged_mask[t] > 0
        return Action(lit, self.trace.logged_power[t].copy(), priority=self.trace.rate[t].copy())
