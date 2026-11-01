"""Link-budget equations checked against hand-calculable references, the dataset, and the twin."""
import math

import numpy as np
import pandas as pd
import pytest

from digital_twin.channel import LinkModel
from digital_twin.link_budget import (fspl_db, link_margin_db, noise_dbw, rx_power_dbw, shannon_mbps, sinr_limit_db, snr_db)
from utils.config import REAL_TRACE, load_config


def test_fspl_reference_value():
    # 32.45 + 20 log10(1000 km) + 20 log10(20000 MHz) = 178.47 dB
    assert fspl_db(1000, 20) == pytest.approx(178.47, abs=0.03)


def test_fspl_doubles_distance_adds_6db_and_doubles_frequency_adds_6db():
    assert fspl_db(1200, 20) - fspl_db(600, 20) == pytest.approx(6.02, abs=0.01)
    assert fspl_db(600, 40) - fspl_db(600, 20) == pytest.approx(6.02, abs=0.01)


def test_noise_floor_reference():
    # kT at 290 K is -174 dBm/Hz = -204 dBW/Hz
    assert noise_dbw(1.0, 290.0, 0.0) == pytest.approx(-203.98, abs=0.02)
    assert noise_dbw(20e6, 290.0, 7.0) == pytest.approx(-203.98 + 73.01 + 7.0, abs=0.02)


def test_rx_power_units_and_rain_reduces_power_one_for_one():
    assert rx_power_dbw(100.0, 50.0, 170.0) == pytest.approx(20 + 50 - 170)
    assert rx_power_dbw(100.0, 50.0, 170.0, rain_db=6.0) == pytest.approx(rx_power_dbw(100.0, 50.0, 170.0) - 6.0)


def test_dataset_fspl_implies_20_ghz():
    d = pd.read_csv(REAL_TRACE)
    calc = d.slant_range_km.map(lambda r: fspl_db(r, 20.0))
    assert (calc - d.fspl_db).abs().max() < 0.05


def test_twin_sinr_equals_explicit_budget_without_interference():
    cfg = load_config()
    cfg["link"]["interference_isolation_db"] = 300.0      # switch interference off
    link = LinkModel(cfg)
    fspl, atm = 175.0, 3.0
    gain = 10 ** (-(fspl + atm) / 10)
    power, lit = np.array([25.0, 0.0]), np.array([True, False])
    twin = 10 * math.log10(link.sinr(power, np.array([gain, gain]), lit)[0])
    l = cfg["link"]
    explicit = snr_db(25.0, l["antenna_gain_db"], fspl, l["bandwidth_mhz"] * 1e6, l["temperature_k"], l["noise_figure_db"], atm)
    assert twin == pytest.approx(explicit, abs=1e-6)


def test_interference_ceiling_holds_in_twin():
    cfg = load_config()
    link = LinkModel(cfg)
    p = np.array([25.0, 25.0, 25.0, 25.0])
    huge = np.full(4, 1e-6)                                # noise negligible
    s = 10 * np.log10(link.sinr(p, huge, np.ones(4, bool)))
    assert s[0] == pytest.approx(sinr_limit_db(25, 75, cfg["link"]["interference_isolation_db"]), abs=0.01)


def test_rain_fade_lowers_sinr_only_when_noise_matters():
    cfg = load_config()
    link = LinkModel(cfg)
    p, lit = np.array([25.0] * 4), np.ones(4, bool)
    weak = np.full(4, 10 ** (-17.8))
    faded = weak * 10 ** (-0.6)
    assert (link.sinr(p, faded, lit) < link.sinr(p, weak, lit)).all()


def test_boundaries_capacity_zero_below_threshold_and_without_los():
    cfg = load_config()
    link = LinkModel(cfg)
    s = np.array([10 ** (cfg["link"]["sinr_min_db"] / 10) * 0.9, 10.0, 10.0])
    cap = link.capacity_mbps(s, np.array([1, 1, 0]), 0.0, 0.0)
    assert cap[0] == 0 and cap[1] > 0 and cap[2] == 0
    assert shannon_mbps(0.0, 20e6) == pytest.approx(20.0)
    assert link_margin_db(10.0, -6.0) == 16.0
