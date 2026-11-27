"""Coordinator behaviour under agent failure, malformed output, timeouts and corrupted telemetry."""
import numpy as np
import pytest

from agents.supervisor import Faults, Supervisor
from bridge.baselines import Action, Policy
from policy.engine import load_profile
from scenarios.suite import forecast_for, make_case, run_once


@pytest.fixture(scope="module")
def flood(rt):
    prof = load_profile("baseline-intl")
    trace, feed = make_case(rt, {"kind": "flood"}, 42, prof)
    forecast_for(rt, trace, 42)
    return prof, trace, feed


def _run(rt, flood, faults):
    prof, trace, feed = flood
    return run_once(rt, trace, feed, prof, faults)


def test_no_faults_means_no_failures_and_no_fallback(rt, flood):
    r = _run(rt, flood, None)
    c = r["coordination"]
    assert c["failures"] == [] and c["fallback_slots"] == 0 and c["data_quality"]["degraded_slots"] == 0
    assert all(rec.decision in ("APPROVED", "REPAIRED") for rec in r["records"])


@pytest.mark.parametrize("mode", ["exception", "malformed", "timeout"])
def test_network_failure_uses_fallback_and_is_traced(rt, flood, mode):
    r = _run(rt, flood, {"network": {"mode": mode, "slots": [20, 25]}})
    assert [rec.decision for rec in r["records"][20:25]] == ["FALLBACK"] * 5
    assert r["coordination"]["agent_health"]["network"]["by_kind"] == {mode: 5}
    steps = [s["action"] for s in r["records"][20].trace]
    assert "agent_failure" in steps and "fallback_reactive_greedy" in steps
    assert r["coordination"]["human_review_by_kind"].get("agent_failure") == 1      # escalated once per failure episode
    assert len(r["records"]) == 100


def test_policy_agent_down_fails_closed_even_before_the_notice(rt, flood):
    r = _run(rt, flood, {"policy": {"mode": "exception", "slots": [30, 40]}})
    for rec in r["records"][30:40]:                     # notice arrives at slot 50, but fail-closed caps already
        assert all(rec.final["power_w"].get(c, 0) <= 22.0 + 1e-6 for c in (13, 14, 15, 16))
    assert r["coordination"]["agent_health"]["policy"]["failures"] == 10


def test_safety_agent_down_protects_every_emergency_cell(rt, flood):
    r = _run(rt, flood, {"safety": {"mode": "exception", "slots": [30, 35]}})
    for rec in r["records"][30:35]:
        assert {13, 14} <= set(rec.final["beams"])


def test_corrupt_telemetry_is_imputed_and_never_reaches_the_guard(rt, flood):
    r = _run(rt, flood, {"telemetry": [{"mode": "nan", "slots": [30, 35], "cells": [13, 14]},
                                       {"mode": "stale", "slots": [60, 70], "cells": list(range(10))}]})
    dq = r["coordination"]["data_quality"]
    assert dq["degraded_slots"] == 5 + 8                 # stale is detected once the report is older than 3 slots
    assert dq["conservative_slots"] == 8                 # 10 of 19 cells stale > 25% threshold
    assert all(np.isfinite(list(rec.final["power_w"].values())).all() for rec in r["records"])
    assert any(s["agent"] == "data_validator" for s in r["records"][30].trace)
    assert r["coordination"]["human_review_by_kind"].get("data_degradation") == 1


def test_validator_is_identity_on_clean_observations(rt, flood):
    prof, trace, feed = flood
    from agents.registry import build_network_policy
    sup = Supervisor(rt["cfg"], build_network_policy(rt["cfg"]), feed, rt["kb"], profile=prof)
    sup._last_good = None
    obs = {"rate_obs": np.ones(19), "forecast": np.ones((19, 3))}
    out, dq = sup._validate_obs(obs, 0)
    assert out is obs and dq is None


class Broken(Policy):
    def act(self, obs):
        return Action(np.zeros(5, bool), np.zeros(5), np.zeros(5))


def test_a_structurally_wrong_policy_is_contained(rt, flood):
    prof, trace, feed = flood
    r = Supervisor(rt["cfg"], Broken(), feed, rt["kb"], profile=prof).run(trace)
    assert r["coordination"]["fallback_slots"] == 100 and r["kpis"]["cap_violation_slots"] == 0


def test_fault_windows_are_half_open():
    f = Faults({"network": [{"mode": "timeout", "slots": [3, 5]}]})
    assert [f.mode("network", t) for t in range(2, 6)] == [None, "timeout", "timeout", None]
