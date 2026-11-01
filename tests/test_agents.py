"""The claims the demo makes about the agent layer, checked on a full flood-relief run."""
import numpy as np
import pytest

from agents.supervisor import PolicyAgent, Supervisor
from bridge.baselines import Action, Policy
from bridge.policy import HeuristicPredictive
from rag.retriever import KnowledgeBase, verify_quote
from scenarios.flood_relief import build
from utils.config import load_config


class GreedyHigh(Policy):
    """Always pushes high power at the event cell, so the cap conflict must trigger."""

    def act(self, obs):
        lit = np.zeros(19, bool)
        lit[[13, 14, 2, 5]] = True
        p = np.zeros(19)
        p[[13, 14, 2, 5]] = [55, 25, 10, 10]
        return Action(lit, p, priority=obs["rate_obs"])


KB = KnowledgeBase(load_config())


@pytest.fixture(scope="module")
def run():
    cfg = load_config()
    trace, feed = build()
    return cfg, trace, feed, Supervisor(cfg, GreedyHigh(), feed, KB).run(trace)


def test_every_slot_audited_and_cap_never_broken(run):
    cfg, trace, _, r = run
    assert [x.slot for x in r["records"]] == list(range(trace.T))
    assert r["kpis"]["cap_violation_slots"] == 0
    for rec in r["records"][50:]:
        for c in cfg["demo"]["border_cells"]:
            assert rec.final["power_w"].get(c, 0) <= cfg["demo"]["border_cap_w"] + 1e-6


def test_conflict_reaches_human_review_with_no_exemption(run):
    _, _, _, r = run
    assert r["human_review"] and any(h["kind"] == "cap_conflict" and h["slot"] >= 50 and h["capacity_lost_mbps"] > 0 for h in r["human_review"])
    steps = [s for rec in r["records"] for s in rec.trace if s["action"] == "R5_emergency_exemption"]
    assert steps and all(s["output"]["evidence_status"] == "NONE_FOUND" for s in steps)


def test_citations_are_verbatim_and_policy_is_blind_before_notice(run):
    cfg, _, feed, r = run
    kb = KB
    text = {p.chunk_id: p.text for p in kb.passages}
    cites = [c for rec in r["records"] for s in rec.trace for c in s["citations"]]
    assert cites and all(verify_quote(c["quote"], text[c["chunk_id"]]) for c in cites)
    assert PolicyAgent(feed, kb).active_cap(49) is None and PolicyAgent(feed, kb).active_cap(50) is not None
    assert all(e.kind != "policy" for e in feed.visible("network", 99))


def test_missing_documents_are_skipped_not_faked():
    ids = {p.doc_id for p in KB.passages}
    assert not ids & {d["doc_id"] for d in KB.skipped}
