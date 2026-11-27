"""Agent registry: declared responsibilities, permissions and fallbacks, plus factories for replaceable parts."""
from __future__ import annotations

import os

import yaml

from utils.config import ROOT

REGISTRY = os.path.join(ROOT, "agents", "registry.yaml")
REQUIRED_FIELDS = ("id", "kind", "name", "implementation", "technique", "enabled", "required", "inputs", "outputs",
                   "allowed_actions", "prohibited_actions", "failure_modes", "fallback")
NETWORK_IMPLS = ("bridge_ppo", "heuristic_predictive", "reactive_greedy")


def load_registry(path: str | None = None) -> list[dict]:
    with open(path or REGISTRY, encoding="utf8") as f:
        entries = yaml.safe_load(f)
    errors = []
    ids = [e.get("id") for e in entries]
    if len(ids) != len(set(ids)):
        errors.append("registry ids must be unique")
    for e in entries:
        missing = [k for k in REQUIRED_FIELDS if k not in e]
        if missing:
            errors.append(f"{e.get('id')}: missing {missing}")
        if e.get("required") and not e.get("enabled"):
            errors.append(f"{e.get('id')}: a required entry cannot be disabled")
        if e.get("kind") not in ("agent", "component"):
            errors.append(f"{e.get('id')}: kind must be agent or component")
    if errors:
        raise ValueError("; ".join(errors))
    return entries


def entry(entries: list[dict], rid: str) -> dict:
    return next(e for e in entries if e["id"] == rid)


def build_network_policy(cfg: dict, impl: str = "bridge_ppo", ckpt: str | None = None):
    """Replace the Network agent's decision-maker without touching the rest of the pipeline."""
    from bridge.baselines import ReactiveGreedy
    from bridge.policy import BridgePolicy, HeuristicPredictive
    s = cfg["scenario"]
    if impl == "bridge_ppo":
        return BridgePolicy(cfg, ckpt or os.path.join(ROOT, "models", "bridge_ppo.pt"))
    if impl == "heuristic_predictive":
        return HeuristicPredictive(cfg)
    if impl == "reactive_greedy":
        return ReactiveGreedy(s["n_cells"], s["k_beams"], s["p_max_w"])
    raise ValueError(f"unknown network implementation {impl}; choose from {NETWORK_IMPLS}")


def build_fallback(cfg: dict, name: str):
    """Fallback decision-maker for the Network agent. It must not depend on the forecaster or a model file."""
    from bridge.baselines import ReactiveGreedy, StaticRoundRobin
    s = cfg["scenario"]
    if name == "reactive_greedy":
        return ReactiveGreedy(s["n_cells"], s["k_beams"], s["p_max_w"])
    if name == "static_round_robin":
        return StaticRoundRobin(s["n_cells"], s["k_beams"], s["p_max_w"])
    raise ValueError(f"unknown fallback {name}")
