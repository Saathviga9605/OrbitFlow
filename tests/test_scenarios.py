"""Scenario suite: definitions are complete, scenarios run through the pipeline, results are reproducible."""
import pytest

from scenarios.suite import evaluate_checks, load_suite, run_scenario


def test_suite_definitions_are_complete():
    suite = load_suite()
    ids = [s["id"] for s in suite]
    assert len(ids) == len(set(ids)) == 10
    for s in suite:
        assert s["checks"] and s["expected"] and s["simulated"] and s["limitations"], s["id"]


def test_checks_fail_when_a_metric_is_missing():
    r = evaluate_checks({"kpis": {"a": 1}}, [{"metric": "kpis.b", "op": "==", "value": 0}, {"metric": "kpis.a", "op": "<=", "ref": "kpis.a"}])
    assert [c["passed"] for c in r] == [False, True]


@pytest.mark.parametrize("sid", ["S6_agent_failure", "S10_data_failure", "S7_conflicting_agents"])
def test_resilience_scenarios_show_their_expected_behaviour(rt, sid):
    r = run_scenario(sid, rt=rt)
    assert r["passed"], [c for c in r["checks"] if not c["passed"]]
    assert set(r["explanation"]) == {"en", "ar", "hi", "ta"}
    assert r["trace_samples"], "a decision trace must be available"
    assert r["disclosure"]["is_simulation"] is True


def test_scenarios_are_reproducible(rt):
    a, b = run_scenario("S1_normal", rt=rt), run_scenario("S1_normal", rt=rt)
    assert a["kpis"] == b["kpis"] and a["baselines"] == b["baselines"] and a["forecast"] == b["forecast"]
    c = run_scenario("S1_normal", seed=999, rt=rt)
    assert c["kpis"] != a["kpis"]


def test_multilingual_scenario_is_language_independent(rt):
    r = run_scenario("S8_multilingual", rt=rt)
    assert r["passed"]
    per = r["multilingual"]["per_language"]
    assert per["ar"]["explanation"] != per["en"]["explanation"]
    assert per["ar"]["kpis"] == per["en"]["kpis"] == per["hi"]["kpis"] == per["ta"]["kpis"]
