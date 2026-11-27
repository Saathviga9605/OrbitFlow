"""Agent registry: contracts are complete, required parts cannot be disabled, implementations are replaceable."""
import copy

import numpy as np
import pytest

from agents.registry import NETWORK_IMPLS, build_network_policy, entry, load_registry
from agents.supervisor import Supervisor
from policy.engine import load_profile
from scenarios.suite import forecast_for, make_case


def test_registry_entries_have_full_contracts():
    reg = load_registry()
    ids = {e["id"] for e in reg}
    assert {"network", "policy", "safety", "supervisor", "guard", "forecaster", "data_validator", "explainer"} <= ids
    for e in reg:
        assert e["allowed_actions"] and e["prohibited_actions"] and e["inputs"] and e["outputs"]
    assert entry(reg, "guard")["required"] and entry(reg, "guard")["kind"] == "component"


def test_required_entries_cannot_be_disabled(tmp_path):
    import yaml
    reg = load_registry()
    entry(reg, "guard")["enabled"] = False
    p = tmp_path / "r.yaml"
    p.write_text(yaml.safe_dump(reg), encoding="utf8")
    with pytest.raises(ValueError, match="cannot be disabled"):
        load_registry(str(p))


@pytest.mark.parametrize("impl", NETWORK_IMPLS)
def test_network_agent_is_replaceable(rt, impl):
    prof = load_profile("baseline-intl")
    trace, feed = make_case(rt, {"kind": "flood"}, 42, prof)
    forecast_for(rt, trace, 42)
    r = Supervisor(rt["cfg"], build_network_policy(rt["cfg"], impl, rt["ckpt"]), feed, rt["kb"], profile=prof).run(trace)
    assert len(r["records"]) == 100 and r["kpis"]["cap_violation_slots"] == 0 and r["coordination"]["fallback_slots"] == 0


def test_disabling_the_policy_agent_removes_its_verdicts(rt):
    prof = load_profile("baseline-intl")
    trace, feed = make_case(rt, {"kind": "flood"}, 42, prof)
    forecast_for(rt, trace, 42)
    reg = copy.deepcopy(load_registry())
    entry(reg, "policy")["enabled"] = False
    r = Supervisor(rt["cfg"], build_network_policy(rt["cfg"], "bridge_ppo", rt["ckpt"]), feed, rt["kb"], profile=prof, registry=reg).run(trace)
    assert r["coordination"]["agents_enabled"] == {"policy": False, "safety": True}
    assert all(not rec.policy_findings for rec in r["records"])
    assert r["coordination"]["agent_health"]["policy"]["calls"] == 0
    assert np.isfinite(r["kpis"]["mean_delay_ms"])
