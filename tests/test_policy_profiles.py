"""Policy profiles: validation, conflict detection, and 'same traffic + same model + different profile -> different permitted action'."""
import copy

import pytest

from policy.engine import list_profiles, load_profile, validate, with_overrides
from scenarios.suite import forecast_for, kpis_of, make_case, run_once
from utils.config import load_config

CFG = load_config()


def test_all_shipped_profiles_load_and_validate(kb):
    assert set(list_profiles()) >= {"baseline-intl", "ae-demo", "in-demo"}
    for pid in list_profiles():
        v = validate(load_profile(pid), CFG, kb)
        assert v["valid"], v["errors"]
        assert load_profile(pid)["status"] == "ILLUSTRATIVE"          # none is presented as a verified legal profile


@pytest.mark.parametrize("mutate, needle", [
    (lambda p: p["operating_constraints"].__setitem__("emergency_exemption", "sometimes"), "emergency_exemption"),
    (lambda p: p["operating_constraints"]["border_power_cap"].__setitem__("cap_w", 1.0), "below the per-beam floor"),
    (lambda p: p["operating_constraints"]["border_power_cap"].__setitem__("cells", [3, 99]), "cell indices"),
    (lambda p: p["governance_rules"].append({"id": "X", "enforcement": "software", "source_type": "official", "kb_rule": "R99"}), "R99"),
    (lambda p: p.pop("resilience"), "missing field: resilience"),
    (lambda p: p["human_oversight"].__setitem__("escalate_on_agent_failure", "yes"), "true or false"),
])
def test_invalid_profiles_are_rejected_with_a_reason(mutate, needle):
    p = copy.deepcopy(load_profile("baseline-intl"))
    mutate(p)
    v = validate(p, CFG)
    assert not v["valid"]
    assert any(needle in e for e in v["errors"]), v["errors"]


def test_cap_vs_emergency_conflict_is_detected_with_a_resolution():
    for pid, word in (("baseline-intl", "human review"), ("ae-demo", "not escalated"), ("in-demo", "exempt")):
        c = validate(load_profile(pid), CFG)["conflicts"]
        assert c and c[0]["id"] == "CAP_VS_EMERGENCY" and word in c[0]["resolution"]


def test_looser_fail_closed_cap_and_unsourced_exemption_warn(kb):
    p = with_overrides(load_profile("in-demo"), cap_w=10.0)
    v = validate(p, CFG, kb)
    assert any("looser" in w for w in v["warnings"])
    assert any("R5" in w for w in v["warnings"])
    assert p["status"] == "DRAFT" and p["version"].endswith("+custom")


@pytest.fixture(scope="module")
def three(rt):
    out = {}
    for pid in ("baseline-intl", "ae-demo", "in-demo"):
        prof = load_profile(pid)
        trace, feed = make_case(rt, {"kind": "flood"}, 42, prof)
        forecast_for(rt, trace, 42)
        out[pid] = run_once(rt, trace, feed, prof)
    return out


def test_baseline_profile_reproduces_the_original_system(rt, three):
    from scenarios.flood_relief import build
    trace, feed = build(rt["base"], None, 42)
    forecast_for(rt, trace, 42)
    assert kpis_of(run_once(rt, trace, feed, None)) == kpis_of(three["baseline-intl"])


def test_same_traffic_different_profile_changes_the_permitted_action(three):
    b, ae, ind = three["baseline-intl"], three["ae-demo"], three["in-demo"]
    for t in range(50):                                   # before the cap notice the model sees and proposes the same thing
        assert b["records"][t].proposed == ae["records"][t].proposed == ind["records"][t].proposed
    assert ind["coordination"]["exempted_slots"] > 0 and b["coordination"]["exempted_slots"] == 0
    assert any(v["status"] == "EXEMPT" for r in ind["records"] for v in r.policy_findings)
    # UAE demo: cap binds, no exemption, cap conflicts are logged but not escalated
    assert ae["coordination"]["exemption_mode"] == "never"
    assert "cap_conflict" not in ae["coordination"]["human_review_by_kind"]
    assert "cap_conflict" in b["coordination"]["human_review_by_kind"]
    lower = [r.final["power_w"].get(c, 0) for r in ae["records"][50:61] for c in (13, 14, 15, 16)]
    assert max(lower) <= 16.0 + 1e-6
    for r in (b, ae):
        assert r["kpis"]["cap_violation_slots"] == 0
