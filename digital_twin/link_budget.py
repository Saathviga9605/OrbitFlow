"""Explicit link budget, independent of the twin's LinkModel, so the two can be checked against each other.

Downlink, per beam:  Prx_dBW = Ptx_dBW + G_total_dB - FSPL_dB - L_atm_dB - L_rain_dB
Noise:               N_dBW   = 10 log10(k T B) + NF_dB
The dataset's channel_gain_magnitude is a linear power gain equal to -(FSPL + L_atm) plus fading, so the twin's
signal term p * gain * G_total is this same equation. G_total lumps Tx and Rx antenna gain: it is NOT measured.
"""
from __future__ import annotations

import math

SPEED_OF_LIGHT = 299_792_458.0
K_BOLTZMANN = 1.380649e-23


def fspl_db(distance_km: float, freq_ghz: float) -> float:
    d, lam = distance_km * 1e3, SPEED_OF_LIGHT / (freq_ghz * 1e9)
    return 20 * math.log10(4 * math.pi * d / lam)


def noise_dbw(bandwidth_hz: float, temperature_k: float, nf_db: float) -> float:
    return 10 * math.log10(K_BOLTZMANN * temperature_k * bandwidth_hz) + nf_db


def rx_power_dbw(ptx_w: float, g_total_db: float, fspl: float, atm_db: float = 0.0, rain_db: float = 0.0) -> float:
    return 10 * math.log10(ptx_w) + g_total_db - fspl - atm_db - rain_db


def snr_db(ptx_w, g_total_db, fspl, bandwidth_hz, temperature_k, nf_db, atm_db=0.0, rain_db=0.0) -> float:
    return rx_power_dbw(ptx_w, g_total_db, fspl, atm_db, rain_db) - noise_dbw(bandwidth_hz, temperature_k, nf_db)


def sinr_limit_db(p_own_w: float, p_others_w: float, isolation_db: float) -> float:
    """Interference ceiling with no noise: SINR cannot exceed this however strong the link."""
    return 10 * math.log10(p_own_w / max(p_others_w, 1e-12)) + isolation_db


def link_margin_db(sinr_db_value: float, required_db: float) -> float:
    return sinr_db_value - required_db


def shannon_mbps(sinr_db_value: float, bandwidth_hz: float, overhead: float = 0.0) -> float:
    return bandwidth_hz * math.log2(1 + 10 ** (sinr_db_value / 10)) * (1 - overhead) / 1e6


def sf358_pfd_limit_db(elevation_deg: float) -> float:
    """ITU-R SF.358-5 recommends 1.5 mask, dB(W/m2) in any 1 MHz: -115 up to 5 deg, rising 0.5 dB/deg to -105 at 25 deg."""
    if elevation_deg <= 5:
        return -115.0
    if elevation_deg <= 25:
        return -115.0 + 0.5 * (elevation_deg - 5)
    return -105.0


def pfd_db_per_mhz(ptx_w: float, gtx_dbi: float, distance_km: float, bandwidth_mhz: float) -> float:
    """Free-space flux density at the surface, spread evenly over the carrier. SF.358-5 recommends 2 sets free-space conditions."""
    return 10 * math.log10(ptx_w) + gtx_dbi - 10 * math.log10(4 * math.pi * (distance_km * 1e3) ** 2) - 10 * math.log10(bandwidth_mhz)


def pfd_power_cap_w(elevation_deg: float, gtx_dbi: float, distance_km: float, bandwidth_mhz: float) -> float:
    """Largest beam power whose surface flux density stays within the SF.358-5 mask."""
    db = sf358_pfd_limit_db(elevation_deg) - gtx_dbi + 10 * math.log10(4 * math.pi * (distance_km * 1e3) ** 2) + 10 * math.log10(bandwidth_mhz)
    return 10 ** (db / 10)
