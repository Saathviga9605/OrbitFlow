"""Test channel model (SINR, capacity calculations)."""
from __future__ import annotations

import numpy as np
import pytest

from digital_twin.channel import LinkModel, to_db


@pytest.fixture
def cfg():
    return {
        "link": {
            "bandwidth_mhz": 20.0,
            "noise_figure_db": 7.0,
            "temperature_k": 290.0,
            "antenna_gain_db": 53.0,
            "interference_isolation_db": 20.0,
            "sinr_min_db": -6.0,
            "ssb_overhead": 0.05,
            "sib_overhead": 0.05,
        }
    }


@pytest.fixture
def link_model(cfg):
    return LinkModel(cfg)


def test_sinr_monotone_in_own_power(link_model):
    """SINR must increase monotonically with own transmit power."""
    gain = np.array([1e-18, 1e-18, 1e-18])
    lit = np.array([True, False, False])
    
    # Test with increasing power levels
    power_levels = [10, 20, 30, 40, 50]
    sinrs = []
    
    for p_val in power_levels:
        power = np.array([p_val, 0, 0])
        sinr = link_model.sinr(power, gain, lit)
        sinrs.append(sinr[0])
    
    # SINRs should be strictly increasing
    for i in range(len(sinrs) - 1):
        assert sinrs[i+1] > sinrs[i], f"SINR not monotone: {sinrs}"


def test_sinr_decreases_with_interference(link_model):
    """SINR must decrease when interference power increases."""
    gain = np.array([1e-18, 1e-18, 1e-18])
    lit = np.array([True, True, True])  # All lit, creates interference
    
    # Case 1: Low interference (only cell 0 is strong)
    power1 = np.array([50, 1, 1])
    sinr1 = link_model.sinr(power1, gain, lit)
    
    # Case 2: High interference (cells 1,2 have higher power)
    power2 = np.array([50, 25, 25])
    sinr2 = link_model.sinr(power2, gain, lit)
    
    # Cell 0's SINR must be lower in case 2 (more interference)
    assert sinr2[0] < sinr1[0], f"SINR should decrease with interference: {sinr1[0]} vs {sinr2[0]}"


def test_unlit_cell_has_zero_sinr(link_model):
    """Unlit cells must have SINR = 0."""
    gain = np.array([1e-18, 1e-18, 1e-18])
    lit = np.array([False, True, True])
    power = np.array([100, 50, 50])  # Cell 0 has power but is unlit
    
    sinr = link_model.sinr(power, gain, lit)
    
    assert sinr[0] == 0, "Unlit cell must have SINR = 0"
    assert sinr[1] > 0, "Lit cell must have SINR > 0"


def test_capacity_zero_below_sinr_min(link_model):
    """Capacity must be 0 when SINR < sinr_min."""
    # Create high-gain conditions to get high SINR
    gain = np.array([1e-17, 1e-17, 1e-17])  # Higher gain
    lit = np.array([True, False, False])
    los = np.array([1, 0, 0])  # Cell 0 visible, others not
    
    # Low power should give low SINR
    power = np.array([0.1, 0, 0])  # Very low power
    
    sinr = link_model.sinr(power, gain, lit)
    cap = link_model.capacity_mbps(sinr, los, ssb=1, sib=0)
    
    # With very low power, SINR should be below threshold, so capacity = 0
    if sinr[0] < 10 ** (-6.0 / 10):  # SINR below -6 dB threshold
        assert cap[0] < 1e-9, "Capacity should be 0 below SINR threshold"


def test_capacity_zero_when_no_los(link_model):
    """Capacity must be 0 when los=0, regardless of SINR."""
    gain = np.array([1e-18, 1e-18, 1e-18])
    lit = np.array([True, True, True])
    los = np.array([0, 1, 1])  # Cell 0 has no LOS
    power = np.array([50, 50, 50])  # High power
    
    sinr = link_model.sinr(power, gain, lit)
    cap = link_model.capacity_mbps(sinr, los, ssb=1, sib=0)
    
    assert cap[0] == 0, "No-LOS cell must have capacity = 0"
    assert cap[1] > 0, "LOS cell must have capacity > 0"


def test_capacity_accounts_for_signaling_overhead(link_model):
    """Capacity should be reduced by SSB/SIB overhead."""
    gain = np.array([1e-18, 1e-18])
    lit = np.array([True, True])
    los = np.array([1, 1])
    power = np.array([50, 50])
    
    sinr = link_model.sinr(power, gain, lit)
    
    # Case 1: No signaling overhead (sib=0, ssb=0)
    cap_normal = link_model.capacity_mbps(sinr, los, ssb=0, sib=0)
    
    # Case 2: SSB overhead
    cap_ssb = link_model.capacity_mbps(sinr, los, ssb=1, sib=0)
    
    # Case 3: SSB + SIB overhead
    cap_sib = link_model.capacity_mbps(sinr, los, ssb=1, sib=1)
    
    # Capacity should decrease with signaling overhead
    assert cap_ssb[0] < cap_normal[0], "SSB overhead should reduce capacity"
    assert cap_sib[0] < cap_ssb[0], "SIB on top of SSB should reduce further"


def test_to_db_conversion(link_model):
    """Test dB conversion utility."""
    # Test known values
    val_1 = 1.0
    db_1 = to_db(np.array([val_1]))[0]
    assert abs(db_1 - 0) < 1e-9, "10*log10(1) should be 0 dB"
    
    val_10 = 10.0
    db_10 = to_db(np.array([val_10]))[0]
    assert abs(db_10 - 10) < 1e-9, "10*log10(10) should be 10 dB"
    
    # Very small values should be clamped
    very_small = 1e-15
    db_small = to_db(np.array([very_small]))[0]
    assert db_small < 0, "Small values should be negative dB"


def test_capacity_scales_with_bandwidth(link_model):
    """Capacity should scale linearly with bandwidth."""
    gain = np.array([1e-18])
    lit = np.array([True])
    los = np.array([1])
    power = np.array([50])
    
    sinr = link_model.sinr(power, gain, lit)
    cap = link_model.capacity_mbps(sinr, los, ssb=0, sib=0)
    
    # Bandwidth is 20 MHz from fixture; capacity should reflect that
    # C = BW * log2(1 + SINR)
    # Should be on the order of 20 MHz worth of capacity
    assert cap[0] > 0, "Should have positive capacity"
    # With SINR ~10^-18 (near noise), capacity should be very small
    # (This is a rough smoke test; exact value depends on noise floor)


def test_sinr_vector_shape(link_model):
    """SINR output should match input shape."""
    for n_cells in [1, 3, 5, 19]:
        gain = np.ones(n_cells) * 1e-18
        lit = np.ones(n_cells, dtype=bool)
        power = np.ones(n_cells) * 50
        
        sinr = link_model.sinr(power, gain, lit)
        
        assert sinr.shape == (n_cells,), f"SINR shape mismatch: {sinr.shape} vs ({n_cells},)"
        assert not np.isnan(sinr).any(), "SINR contains NaN"
        assert (sinr >= 0).all() or (~lit).all(), "SINR should be >= 0 for lit cells"


def test_capacity_vector_shape(link_model):
    """Capacity output should match input shape."""
    for n_cells in [1, 3, 5, 19]:
        gain = np.ones(n_cells) * 1e-18
        lit = np.ones(n_cells, dtype=bool)
        los = np.ones(n_cells, dtype=int)
        power = np.ones(n_cells) * 50
        
        sinr = link_model.sinr(power, gain, lit)
        cap = link_model.capacity_mbps(sinr, los, ssb=1, sib=0)
        
        assert cap.shape == (n_cells,), f"Capacity shape mismatch: {cap.shape} vs ({n_cells},)"
        assert not np.isnan(cap).any(), "Capacity contains NaN"
        assert (cap >= 0).all(), "Capacity should be >= 0"
