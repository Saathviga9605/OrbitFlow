"""Test BAM guardrail constraint satisfaction and repair logic."""
from __future__ import annotations

import numpy as np
import pytest

from bam.validator import BamGuard, Constraints, GuardState


@pytest.fixture
def cfg():
    """Minimal config for testing."""
    return {
        "scenario": {
            "n_cells": 5,
            "k_beams": 2,
            "p_max_w": 100.0,
            "p_min_w": 5.0,
        },
        "timing_guard": {
            "ssb_max_age_slots": 40,
            "sib_max_age_slots": 80,
            "border_cells": [4],
            "border_power_cap_w": 30.0,
        },
    }


@pytest.fixture
def guard(cfg):
    return BamGuard(cfg)


def test_k_enforced(guard):
    """Proposing > K beams must be reduced to K."""
    lit = np.array([True, True, True, False, False])  # 3 beams, K=2
    power = np.array([25, 25, 25, 0, 0])
    state = GuardState.fresh(5)
    
    result = guard.repair(lit, power, state, ssb=1, sib=1)
    
    assert result.lit.sum() == 2, f"Expected 2 lit beams, got {result.lit.sum()}"
    assert result.ok, "Result should be OK after repair"


def test_power_floor_respected(guard):
    """Every lit beam must have power >= p_min."""
    lit = np.array([True, True, False, False, False])
    power = np.array([1.0, 1.0, 0, 0, 0])  # Below p_min=5.0
    state = GuardState.fresh(5)
    
    result = guard.repair(lit, power, state, ssb=1, sib=1)
    
    lit_cells = np.where(result.lit)[0]
    for cell in lit_cells:
        assert result.power[cell] >= 5.0 - 1e-9, f"Cell {cell} power {result.power[cell]} < 5.0"
    assert result.ok, "Result should be OK"


def test_total_power_capped(guard):
    """Total power must not exceed p_max."""
    lit = np.array([True, True, True, True, True])
    power = np.ones(5) * 50.0  # Total = 250 W, way above Pmax=100
    state = GuardState.fresh(5)
    
    result = guard.repair(lit, power, state, ssb=1, sib=1)
    
    # Repair should reduce beams to K=2
    assert result.lit.sum() <= 2, "Should have <= K beams"
    assert result.power.sum() <= 100.0 + 1e-6, f"Total power {result.power.sum()} > 100"
    assert result.ok, "Result should be OK"


def test_timing_due_cells_forced_on(guard):
    """Cells due for SSB/SIB must be lit even if not proposed."""
    state = GuardState.fresh(5)
    # SSB period is 2, max age is 40, so (age + 2 > 40) => age > 38 => age >= 39
    state.ssb_age = np.array([39, 10, 5, 0, 30])  # Cell 0 is due (age >= 39)
    
    lit = np.array([False, True, True, False, False])  # Cell 0 not lit but due
    power = np.array([0, 30, 30, 0, 0])
    
    result = guard.repair(lit, power, state, ssb=1, sib=0)
    
    # Cell 0 should be forced on despite not being proposed
    assert result.lit[0], "Due cell 0 should be forced on"
    assert result.ok, "Result should be OK"


def test_timing_due_urgency_ranking(guard):
    """If more cells are due than K, keep the most urgent."""
    state = GuardState.fresh(5)
    state.ssb_age = np.array([39, 39, 5, 1, 1])  # Cells 0,1 are very urgent (near 40-slot deadline)
    
    lit = np.array([False, False, False, False, False])
    power = np.array([0, 0, 0, 0, 0])
    
    result = guard.repair(lit, power, state, ssb=1, sib=0)
    
    # Should select the 2 most urgent: cells 0 and 1
    assert result.lit[0], "Most urgent cell 0 should be lit"
    assert result.lit[1], "Second-most urgent cell 1 should be lit"
    assert result.lit.sum() == 2, f"Should have exactly K=2 beams, got {result.lit.sum()}"
    assert result.ok, "Result should be OK"


def test_power_redistribution_after_beam_drop(guard):
    """When beams are dropped, power should be redistributed to remaining beams."""
    lit = np.array([True, True, True, False, False])  # 3 lit
    power = np.array([30, 30, 30, 0, 0])  # Total 90
    state = GuardState.fresh(5)
    
    result = guard.repair(lit, power, state, ssb=1, sib=1)
    
    # Should keep 2 beams
    assert result.lit.sum() == 2
    # Total power should be redistributed to the remaining beams, but not exceed Pmax
    lit_cells = np.where(result.lit)[0]
    for cell in lit_cells:
        assert result.power[cell] >= 5.0 - 1e-9, f"Redistributed power below floor: {result.power[cell]}"
    assert result.power.sum() <= 100.0 + 1e-6
    assert result.ok


def test_border_power_cap_applied(guard):
    """Border cells must respect the border_power_cap."""
    lit = np.array([True, True, False, False, True])  # Cell 4 is border cell
    power = np.array([30, 30, 0, 0, 50])  # Cell 4 exceeds cap of 30 W
    state = GuardState.fresh(5)
    
    result = guard.repair(lit, power, state, ssb=1, sib=1)
    
    # Cell 4 power should be capped at 30 W
    assert result.power[4] <= 30.0 + 1e-9, f"Border cell power {result.power[4]} exceeds cap 30"
    assert result.ok


def test_dynamic_constraints_power_cap(guard):
    """Dynamic power_cap constraint should override static config."""
    lit = np.array([True, True, False, False, False])
    power = np.array([50, 50, 0, 0, 0])
    state = GuardState.fresh(5)
    
    # Set dynamic constraint: cell 0 max 20 W, cell 1 max 40 W
    constraints = Constraints(power_cap=np.array([20, 40, 0, 0, 0]))
    
    result = guard.repair(lit, power, state, ssb=1, sib=1, constraints=constraints)
    
    assert result.power[0] <= 20.0 + 1e-9, "Cell 0 exceeds dynamic cap"
    assert result.power[1] <= 40.0 + 1e-9, "Cell 1 exceeds dynamic cap"
    assert result.ok


def test_forbidden_cells_never_lit(guard):
    """Forbidden cells must never be lit, even if proposed."""
    lit = np.array([True, True, True, False, False])
    power = np.array([30, 30, 30, 0, 0])
    state = GuardState.fresh(5)
    
    constraints = Constraints(forbidden_lit=np.array([False, True, False, False, False]))
    
    result = guard.repair(lit, power, state, ssb=1, sib=1, constraints=constraints)
    
    assert not result.lit[1], "Forbidden cell 1 should be off"
    assert result.ok


def test_forced_lit_override(guard):
    """Forced_lit cells must be lit despite low priority."""
    lit = np.array([False, False, False, False, False])
    power = np.array([0, 0, 0, 0, 0])
    state = GuardState.fresh(5)
    
    constraints = Constraints(forced_lit=np.array([True, True, False, False, False]))
    priority = np.array([0, 0, 100, 100, 100])  # Cells 0,1 lowest priority
    
    result = guard.repair(lit, power, state, ssb=0, sib=0, priority=priority, constraints=constraints)
    
    # Despite low priority, cells 0,1 must be forced on
    assert result.lit[0], "Forced cell 0 must be lit"
    assert result.lit[1], "Forced cell 1 must be lit"
    assert result.lit.sum() == 2, "Only forced cells should be lit (K=2)"
    assert result.ok


def test_min_power_constraint(guard):
    """min_power constraint should be respected."""
    lit = np.array([True, True, False, False, False])
    power = np.array([50, 50, 0, 0, 0])
    state = GuardState.fresh(5)
    
    constraints = Constraints(min_power=np.array([20, 30, 0, 0, 0]))
    
    result = guard.repair(lit, power, state, ssb=1, sib=1, constraints=constraints)
    
    # Lit cells should meet their min_power requirements
    if result.lit[0]:
        assert result.power[0] >= 20.0 - 1e-9, "Cell 0 below min_power"
    if result.lit[1]:
        assert result.power[1] >= 30.0 - 1e-9, "Cell 1 below min_power"
    assert result.ok


def test_random_proposals_always_valid(guard):
    """After repair, 1000 random proposals should all be valid."""
    np.random.seed(42)
    state = GuardState.fresh(5)
    
    for trial in range(1000):
        # Random proposal
        lit = np.random.rand(5) > 0.5
        power = np.random.rand(5) * 100
        
        result = guard.repair(lit, power, state, ssb=1, sib=0)
        
        # Check all invariants
        assert result.lit.sum() <= 2, f"Trial {trial}: too many beams lit"
        assert result.power.sum() <= 100.0 + 1e-6, f"Trial {trial}: power exceeds Pmax"
        lit_cells = np.where(result.lit)[0]
        for cell in lit_cells:
            assert result.power[cell] >= 5.0 - 1e-9, f"Trial {trial}: cell {cell} below floor"
        assert result.ok, f"Trial {trial}: not OK"


def test_check_identifies_violations(guard):
    """check() should identify violations that repair() fixes."""
    lit = np.array([True, True, True, True, False])  # 4 beams, K=2
    power = np.array([30, 30, 30, 30, 0])
    state = GuardState.fresh(5)
    
    before = guard.check(lit, power, state, ssb=1, sib=1)
    
    # Should report violations
    assert before["beam_count"]["status"] == "FAIL", "Should detect too many beams"
    assert before["power_budget"]["status"] == "FAIL", "Should detect power budget"
    
    # After repair, all should pass
    result = guard.repair(lit, power, state, ssb=1, sib=1)
    assert result.ok, "Repair should fix all violations"
    assert all(c["status"] == "PASS" for c in result.checks.values())


def test_due_mask_public_method(guard):
    """Public due_mask() should return same mask as internal _due()."""
    state = GuardState.fresh(5)
    # SSB period = 2, max_age = 40, so due when (age + 2 > 40) => age >= 39
    state.ssb_age = np.array([39, 5, 39, 2, 10])
    
    due_mask = guard.due_mask(state, ssb=1, sib=0)
    
    # Cells 0 and 2 should be due (age >= 39)
    assert due_mask[0], "Cell 0 should be due"
    assert due_mask[2], "Cell 2 should be due"
    assert not due_mask[1], "Cell 1 should not be due"
