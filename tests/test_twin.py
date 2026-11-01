"""Test digital twin correctness: queue conservation, capacity, energy, etc."""
from __future__ import annotations

import numpy as np
import pytest

from digital_twin.environment import NTNTwin, summarise
from traffic.dataset import Trace


@pytest.fixture
def simple_trace():
    """Create a minimal test trace: 5 slots, 3 cells."""
    return Trace(
        rate=np.array([[1.0, 2.0, 3.0],
                       [1.5, 2.5, 2.0],
                       [2.0, 1.5, 1.0],
                       [1.0, 1.0, 1.0],
                       [2.0, 2.0, 2.0]], dtype=float),
        gain=np.ones((5, 3)) * 1e-18,
        los=np.ones((5, 3)),
        elev=np.full((5, 3), 45.0),
        ssb=np.array([1, 0, 1, 0, 1], dtype=float),
        sib=np.array([1, 0, 0, 0, 0], dtype=float),
        prach=np.ones(5),
        hot=np.zeros((5, 3)),
        logged_mask=np.zeros((5, 3)),
        logged_power=np.zeros((5, 3)),
        q0_rt_kb=np.array([100.0, 100.0, 100.0]),
        q0_nrt_kb=np.array([200.0, 200.0, 200.0]),
        emergency=np.zeros((5, 3)),
        forecast=None,
        events=[],
        slot_ms=10.0,
        source="test",
    )


@pytest.fixture
def cfg():
    """Minimal config for testing."""
    return {
        "seed": 7,
        "scenario": {
            "n_cells": 3,
            "slot_ms": 10,
            "k_beams": 2,
            "p_max_w": 100.0,
            "p_min_w": 2.0,
            "obs_lag_slots": 1,
        },
        "link": {
            "bandwidth_mhz": 20.0,
            "noise_figure_db": 7.0,
            "temperature_k": 290.0,
            "antenna_gain_db": 53.0,
            "interference_isolation_db": 20.0,
            "sinr_min_db": -6.0,
            "ssb_overhead": 0.05,
            "sib_overhead": 0.05,
        },
        "queues": {
            "init_backlog_ms": 20,
            "rt_share": 0.285,
            "buffer_rt_kb": 1600,
            "buffer_nrt_kb": 4000,
            "rt_delay_budget_ms": 100,
            "nrt_delay_budget_ms": 1000,
        },
        "timing_guard": {
            "ssb_max_age_slots": 40,
            "sib_max_age_slots": 80,
            "prach": "always_open",
            "border_cells": [],
            "border_power_cap_w": 0.0,
        },
        "reward": {
            "w_throughput": 1.0,
            "w_delay": 0.5,
            "w_loss": 2.0,
            "w_fairness": 0.5,
            "w_energy": 0.0,
            "w_rt_violation": 1.0,
            "w_guard_violation": 5.0,
        },
    }


def test_queue_conservation(simple_trace, cfg):
    """Queue conservation: initial + arrived == served + dropped + final (per cell, per slot)."""
    twin = NTNTwin(simple_trace, cfg)
    obs = twin.reset()
    
    for t in range(simple_trace.T):
        # Record state before step
        q_rt_before = twin.q_rt.copy()
        q_nrt_before = twin.q_nrt.copy()
        
        # Record arrivals and departures in this step
        lit = np.array([True, True, False])  # light cells 0, 1
        power = np.array([50.0, 50.0, 0.0])
        
        rec = twin.step(lit, power)
        
        # Check per-cell balance: init_q + arrived == served + dropped + final_q
        for cell in range(3):
            arrived = rec["arrived_kb"][cell]
            served = rec["served_kb"][cell]
            dropped = rec["dropped_kb"][cell]
            q_before = q_rt_before[cell] + q_nrt_before[cell]
            q_after = twin.q_rt[cell] + twin.q_nrt[cell]
            
            balance = q_before + arrived - (served + dropped + q_after)
            assert abs(balance) < 1e-6, f"Cell {cell}, slot {t}: balance = {balance}"


def test_unlit_cell_serves_zero(simple_trace, cfg):
    """Unlit cells (lit[i]=False) must have served_kb[i]==0."""
    twin = NTNTwin(simple_trace, cfg)
    obs = twin.reset()
    
    for t in range(simple_trace.T):
        lit = np.array([True, False, True])  # cell 1 is unlit
        power = np.array([33.0, 0.0, 33.0])
        
        rec = twin.step(lit, power)
        
        # Cell 1 must serve zero despite having traffic
        assert rec["served_kb"][1] < 1e-9, f"Unlit cell 1 served {rec['served_kb'][1]} > 0"


def test_capacity_zero_when_no_los(simple_trace, cfg):
    """When los[i]==0, capacity must be 0 regardless of power."""
    simple_trace.los[0, 1] = 0  # Make cell 1 invisible in slot 0
    twin = NTNTwin(simple_trace, cfg)
    obs = twin.reset()
    
    lit = np.array([True, True, True])
    power = np.array([30.0, 30.0, 30.0])
    
    rec = twin.step(lit, power)
    
    # Cell 1 is lit but has no LOS; capacity should be zero
    assert rec["cap_mbps"][1] < 1e-9, f"No-LOS cell has capacity {rec['cap_mbps'][1]} > 0"


def test_energy_calculation(simple_trace, cfg):
    """Energy (joules) must be power·slot_ms / 1000."""
    twin = NTNTwin(simple_trace, cfg)
    obs = twin.reset()
    
    lit = np.array([True, True, False])
    power = np.array([40.0, 30.0, 0.0])
    
    rec = twin.step(lit, power)
    
    expected_energy = (40.0 + 30.0) * 10.0 / 1000.0  # 70 W × 10 ms / 1000
    assert abs(rec["energy_j"] - expected_energy) < 1e-6, f"Energy mismatch: {rec['energy_j']} vs {expected_energy}"


def test_aggregate_kpis(simple_trace, cfg):
    """Test that summarise() aggregates correctly over multiple slots."""
    twin = NTNTwin(simple_trace, cfg)
    obs = twin.reset()
    
    for t in range(simple_trace.T):
        lit = np.array([True, True, False])
        power = np.array([50.0, 50.0, 0.0])
        twin.step(lit, power)
    
    kpis = summarise(twin.history, twin.slot_ms)
    
    # Throughput must be positive (traffic was served)
    assert kpis["throughput_mbps"] > 0, "No throughput"
    
    # Demand should be reasonable (total arrivals / number of slots converted to Mbps)
    # demand_mbps = arr.sum() / (n_slots * slot_ms) where slot_ms = 10 ms
    # arrivals are in KB, so arr.sum() / (n * 10 / 1000) = arr.sum() * 100 / n Mbps
    # With our test rate, total demand over 5 slots ~= (1+2+3)*10ms + (1.5+2.5+2)*10ms + ...
    assert kpis["demand_mbps"] > 1.0, "Demand seems too low"
    
    # Served ratio should be between 0 and 1 (we're serving some but not all traffic)
    assert 0 <= kpis["served_ratio"] <= 1.01, "Served ratio out of range"
    
    # Fairness (Jain) should be between 0 and 1
    assert 0 <= kpis["jain_fairness"] <= 1.01, "Jain index out of range"


def test_emergency_rt_violation_tracking(cfg):
    """Test that emergency_rt_violation is tracked correctly when emergency flags are set."""
    trace = Trace(
        rate=np.ones((5, 2)) * 10.0,
        gain=np.ones((5, 2)) * 1e-18,
        los=np.ones((5, 2)),
        elev=np.full((5, 2), 45.0),
        ssb=np.ones(5),
        sib=np.ones(5),
        prach=np.ones(5),
        hot=np.zeros((5, 2)),
        logged_mask=np.zeros((5, 2)),
        logged_power=np.zeros((5, 2)),
        q0_rt_kb=np.array([1500.0, 1500.0]),  # High initial queues
        q0_nrt_kb=np.array([3000.0, 3000.0]),
        emergency=np.zeros((5, 2)),
        forecast=None,
        events=[],
        slot_ms=10.0,
        source="test",
    )
    trace.emergency[1, 0] = 1  # Mark cell 0 as emergency at slot 1
    
    cfg["scenario"]["n_cells"] = 2
    cfg["scenario"]["k_beams"] = 2
    twin = NTNTwin(trace, cfg)
    obs = twin.reset()
    
    # Step 1: only light cell 1 (not emergency)
    twin.step(np.array([False, True]), np.array([0, 100]))
    rec1 = twin.history[-1]
    
    # Emergency SLA should be NaN (no emergency cells in the mask)
    assert np.isnan(rec1["emergency_rt_violation"]), "Should be NaN when no emergency cells"
    
    # Step 2: emergency cell is now visible; light it
    obs = twin.obs()
    if obs["emergency"][0] > 0:
        twin.step(np.array([True, False]), np.array([100, 0]))
        rec2 = twin.history[-1]
        # Emergency SLA should now be tracked (may or may not violate depending on queue depth)
        assert not np.isnan(rec2["emergency_rt_violation"]), "Should be tracked when emergency cells present"
