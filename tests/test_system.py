"""Forecasting, BRIDGE, simulation, agent and API behaviour."""
import copy
import os
import time

import numpy as np
import pytest
import torch
from fastapi.testclient import TestClient

from agents.supervisor import SafetyAgent, Supervisor
from bam.validator import BamGuard
from bridge.baselines import ReactiveGreedy
from bridge.evaluate import run_episode
from bridge.policy import BridgeNet, BridgePolicy
from digital_twin.environment import NTNTwin
from rag.retriever import KnowledgeBase
from scenarios.flood_relief import build
from traffic.dataset import load_openntn_sionna, load_trace
from traffic.forecaster import Forecaster, gate_forecast, persistence_trace
from traffic.generator import make_trace
from traffic.splits import create_splits
from utils.config import REAL_TRACE, ROOT, load_config
from utils.stats import holm, paired, summary

CFG = load_config()
BASE = load_trace(REAL_TRACE)
FC_PATH = os.path.join(ROOT, "models", "traffic_predictor.pt")
BR_PATH = os.path.join(ROOT, "models", "bridge_ppo.pt")


# ---------------------------------------------------------------- forecasting
def test_episode_split_has_no_seed_overlap_with_test_seeds():
    m = create_splits(n_per_kind=120, random_seed=CFG["seed"])
    assert not {e["seed"] for e in m.train_episodes} & {e["seed"] for e in m.test_episodes}
    assert max(e["seed"] for e in m.test_episodes) < 50000     # multi-run seeds are fresh


def test_forecaster_serialises_and_reloads_identically(tmp_path):
    a = Forecaster.load(CFG, FC_PATH)
    p = tmp_path / "f.pt"
    torch.save(a.net.state_dict(), p)
    b = Forecaster.load(CFG, str(p))
    t = make_trace("mixed", BASE, 11)
    assert np.array_equal(a.predict_trace(t), b.predict_trace(t))


def test_gradual_surge_beats_persistence_and_gate_is_causal():
    fc = Forecaster.load(CFG, FC_PATH)
    tr = copy.deepcopy(make_trace("normal", BASE, 3))
    tr.rate[:, 7] = 3.0
    tr.rate[20:40, 7] = np.linspace(3, 40, 20)
    tr.rate[40:, 7] = 40.0
    f, p = fc.predict_trace(tr), persistence_trace(tr)
    w = np.arange(25, 38)
    assert np.abs(f[w, 7, 0] - tr.rate[w, 7]).mean() < np.abs(p[w, 7, 0] - tr.rate[w, 7]).mean()
    g = gate_forecast(tr, f)
    bad = copy.deepcopy(tr)
    bad.rate[30:] = 99.0
    f2 = f.copy()
    f2[31:] = 1.0
    assert np.allclose(g[30], gate_forecast(bad, f2)[30])     # row 30 only uses forecasts and demand up to slot 29


def test_abrupt_jump_cannot_be_foreseen():
    fc = Forecaster.load(CFG, FC_PATH)
    tr = copy.deepcopy(make_trace("normal", BASE, 4))
    tr.rate[:, 9] = 2.2
    tr.rate[50:, 9] = 40.0
    f = fc.predict_trace(tr)
    assert f[50, 9, 0] < 15.0


# ---------------------------------------------------------------- BRIDGE
@pytest.fixture(scope="module")
def policy():
    return BridgePolicy(CFG, BR_PATH)


def test_action_validity_over_full_episode(policy):
    t = make_trace("block", BASE, 21)
    t.forecast = Forecaster.load(CFG, FC_PATH).predict_trace(t)
    tw = NTNTwin(t, CFG)
    o = tw.reset()
    while not tw.done:
        a = policy.act(o)
        assert a.lit.sum() == 4 and a.power.sum() == pytest.approx(100.0) and (a.power[a.lit] >= 2.0 - 1e-9).all() and not a.power[~a.lit].any()
        tw.step(a.lit, a.power)
        o = tw.obs()


def test_masked_cells_are_not_selected_when_enough_are_visible():
    f = torch.zeros(1, 19, 19)
    f[0, :, 5] = 1
    f[0, 3, 5] = 0
    z, _, _ = BridgeNet()(f)
    assert 3 not in torch.topk(z, 4).indices[0].tolist()


def test_reproducible_and_fast(policy):
    t = make_trace("mixed", BASE, 22)
    t.forecast = Forecaster.load(CFG, FC_PATH).predict_trace(t)
    assert run_episode(t, CFG, policy)["mean_delay_ms"] == run_episode(t, CFG, policy)["mean_delay_ms"]
    o = NTNTwin(t, CFG).reset()
    t0 = time.perf_counter()
    for _ in range(50):
        policy.act(o)
    assert (time.perf_counter() - t0) / 50 * 1000 < 10.0      # inside the 10 ms slot on this CPU


def test_guard_repair_never_breaks_hard_limits():
    g = BamGuard(CFG)
    o = NTNTwin(BASE, CFG).reset()
    rng = np.random.default_rng(1)
    for _ in range(300):
        lit = rng.random(19) < 0.4
        res = g.repair(lit, rng.uniform(0, 80, 19) * lit, o["guard"], 1.0, 0.0, priority=rng.random(19))
        assert res.lit.sum() <= 4 and res.power.sum() <= 100 + 1e-6


# ---------------------------------------------------------------- simulation
def test_scenario_reproducible_and_duration_is_configurable():
    a, _ = build(BASE, None, 5)
    b, _ = build(BASE, None, 5)
    assert np.array_equal(a.rate, b.rate)
    c, feed = build(BASE, {"surge_end": 45}, 5)
    assert c.emergency[44, 13] == 1 and c.emergency[45, 13] == 0
    assert next(e for e in feed.events if e.id == "recovery_start").slot == 45


def test_rain_fade_scales_gain_only_in_window_and_only_on_emergency_cells():
    a, _ = build(BASE, {"fade_db": 0.0}, 5)
    b, _ = build(BASE, {"fade_db": 6.0}, 5)
    assert b.gain[50, 13] == pytest.approx(a.gain[50, 13] * 10 ** -0.6)
    assert b.gain[40, 13] == a.gain[40, 13] and b.gain[50, 2] == a.gain[50, 2]


def test_queue_conservation_under_full_stack():
    t, feed = build(BASE, None, 6)
    r = Supervisor(CFG, ReactiveGreedy(19, 4, 100.0), feed, KB).run(t)
    H = r["history"]
    q0 = t.rate[0] * CFG["queues"]["init_backlog_ms"]
    total = q0 + sum(h["arrived_kb"] for h in H) - sum(h["served_kb"] + h["dropped_kb"] for h in H) - H[-1]["q_rt"] - H[-1]["q_nrt"]
    assert np.abs(total).max() < 1e-6


def test_second_offline_trace_loads_consistently():
    t = load_openntn_sionna(ROOT)
    assert t.rate.shape == BASE.rate.shape and np.array_equal(t.los, BASE.los) and not np.array_equal(t.rate, BASE.rate)


# ---------------------------------------------------------------- agents
KB = KnowledgeBase(CFG)


def test_emergency_transition_tapers_only_when_configured():
    cfg = copy.deepcopy(CFG)
    _, feed = build(BASE, None, 7)
    cfg["emergency"]["release"] = "abrupt"
    assert SafetyAgent(feed, cfg).recovering_cells(65) == []
    cfg["emergency"]["release"] = "taper"
    s = SafetyAgent(feed, cfg)
    assert s.recovering_cells(65) == [13, 14] and s.recovering_cells(61 + cfg["emergency"]["taper_max_slots"]) == []


def test_information_boundaries_hold_for_every_agent():
    _, feed = build(BASE, None, 7)
    assert not [e for e in feed.visible("network", 99) if e.kind in ("policy", "emergency")]
    assert not [e for e in feed.visible("safety", 99) if e.kind == "policy"]
    assert not [e for e in feed.visible("policy", 99) if e.kind == "emergency"]
    assert {e.kind for e in feed.visible("supervisor", 99)} >= {"policy", "emergency"}


def test_latency_is_measured_for_each_stage_and_agents_off_skips_them():
    t, feed = build(BASE, None, 8)
    on = Supervisor(CFG, ReactiveGreedy(19, 4, 100.0), feed, KB).run(t)["compute_ms"]
    assert all(len(on[k]) == 100 for k in ("network", "policy", "safety", "guard", "audit"))
    t, feed = build(BASE, None, 8)
    off = Supervisor(CFG, ReactiveGreedy(19, 4, 100.0), feed, KB, agents_on=False).run(t)["compute_ms"]
    assert off["policy"] == [] and len(off["guard"]) == 100     # hard validation stays on in every configuration


def test_hypothetical_cap_is_labelled_as_such():
    _, feed = build(BASE, None, 7)
    e = next(x for x in feed.events if x.kind == "policy")
    assert "HYPOTHETICAL" in e.description and "not a real law" in e.description and e.payload["hypothetical"]


# ---------------------------------------------------------------- statistics
def test_paired_statistics():
    a, b = np.arange(20.0), np.arange(20.0) + 1
    p = paired(a, b)
    assert p["mean_diff"] == -1 and p["wins_a_lower"] == 20 and p["rank_biserial"] == -1 and p["p"] < 0.001
    assert summary([1, 2, 3])["n"] == 3 and summary([1.0])["sd"] is None
    assert holm({"x": 0.01, "y": 0.04}) == {"x": 0.02, "y": 0.04}


# ---------------------------------------------------------------- API
@pytest.fixture(scope="module")
def client():
    from dashboard import api
    api._state.update(kb=KB)
    return TestClient(api.app)


def test_api_health_and_errors(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/results/definitely_missing").status_code == 404
    assert client.get("/api/results/..%2Fsecret").status_code in (400, 404)
    assert client.post("/api/simulate?cap_w=1").status_code == 422


def test_api_simulation_matches_a_direct_run(client):
    r = client.post("/api/simulate?cap_w=30&fade_db=3&seed=42").json()
    assert r["kpis"]["cap_violation_slots"] == 0 and r["experiment_id"] == "live:cap30:fade3:seed42:agents1" and r["kind"] == "newly executed simulation"
    assert r == client.post("/api/simulate?cap_w=30&fade_db=3&seed=42").json()


def test_api_ask_is_grounded(client):
    a = client.post("/api/ask", params={"q": "What does the policy node do in the ML pipeline?"}).json()
    assert a["supported"] and a["quotes"][0]["verified_verbatim"]
    n = client.post("/api/ask", params={"q": "zzzqqq xylophone"}).json()
    assert not n["supported"] and "does not support" in n["statement"]


def test_emergency_cell_is_not_dropped_when_another_is_forced_on():
    from bridge.baselines import Action, Policy

    class FourWithOneEmergency(Policy):
        def act(self, obs):
            lit = np.zeros(19, bool)
            lit[[13, 2, 5, 9]] = True
            p = np.zeros(19)
            p[[13, 2, 5, 9]] = 25.0
            return Action(lit, p, priority=np.where(np.arange(19) == 13, -5.0, 1.0))

    t, feed = build(BASE, None, 9)
    r = Supervisor(CFG, FourWithOneEmergency(), feed, KB).run(t)
    # only hard signalling deadlines may take its beam
    assert all(13 in x.final["beams"] or any("timing deadline" in n for n in x.repairs) for x in r["records"][28:61])
    assert sum(13 in x.final["beams"] for x in r["records"][28:61]) >= 30
