# Link-budget parameter sheet (for ECE review)

**Status: provisional. No value here has been reviewed or approved by the ECE team.** To replace a value, edit `link:` in `config.yaml` and rerun `scripts/calibrate_link.py`, `scripts/run_experiments.py` and `scripts/run_studies.py`.

Version 3 targets the revised 58-cell dataset (12 beams, 300 W). The bandwidth sweep is in `results/link_calibration.json`; per-parameter sensitivity is in `results/studies/link_sensitivity.json`.

| Parameter | Current value | Unit | Source | Class | Recommended validation | Sensitivity |
|---|---:|---|---|---|---|---|
| Carrier frequency | 20 | GHz | Implied by the Sionna `path_loss_db` and `slant_range_km` (LOS loss = FSPL(20 GHz) + 1.5 dB exactly) | Derived | Confirm against the scenario definition | Already inside the gain |
| Slant range | 602–1429 | km | Dataset `slant_range_km` | Dataset | Check against orbit altitude | Inside the gain |
| Elevation angle | 25–85 | deg | Dataset | Dataset | Check against ephemeris | Inside the gain |
| Path loss, LOS | FSPL + 1.5 | dB | Sionna export | Dataset | Ask the author what the 1.5 dB covers (atmosphere?) | Inside the gain |
| Path loss, NLOS | FSPL + 18 | dB | Sionna export (flat extra loss) | Dataset | Confirm the blockage model | Decides NLOS decodability |
| Channel gain | −path loss | linear | Dataset | Dataset | None beyond the test | Inside the gain |
| Total antenna gain (Tx + Rx) | 53 | dB | Unchanged from v2 (calibrated for 11–15 dB on a lit beam at 20 MHz) | **Assumed** | Replace with real EIRP and G/T | See results |
| Bandwidth per beam | **80** | MHz | **Chosen by sweep (was 20)**: served demand for a non-learning baseline saturates near 80 MHz; LOS beam ≈ 9 dB SNR at 25 W; NLOS falls below the decode threshold, as the dataset's own SINR column records | **Assumed** | Confirm the carrier plan (Ka-band LEO user beams are commonly tens to hundreds of MHz) | High: capacity scales directly |
| Interference isolation, adjacent beam | 20 | dB | Chosen (unchanged) | **Assumed** | Replace with beam-pattern side-lobe data | See results |
| Isolation per further hex ring | **5** | dB | **New in v3** | **Assumed** | Replace with a coupling matrix from the antenna pattern | Medium |
| Isolation floor (distant beams) | **40** | dB | **New in v3** | **Assumed** | As above | Low |
| LOS required to decode | **false** | — | **New in v3**: SINR decides; the export gives an explicit NLOS gain | Choice | Confirm the blockage interpretation | Low at 80 MHz (NLOS is undecodable anyway) |
| Noise figure | 7 | dB | Chosen | **Assumed** | Replace with terminal spec | See results |
| Noise temperature | 290 | K | Standard reference | Assumed | Replace with system temperature | Tied to noise figure |
| Minimum decodable SINR | −6 | dB | Chosen | **Assumed** | Replace with an MCS table | See results |
| SSB / SIB overhead | 5% / 5% | capacity | Chosen | **Assumed** | Derive from NR numerology | Low |
| Spectral efficiency | Shannon bound | bit/s/Hz | Formula, no implementation margin | **Optimistic** | Replace with an MCS curve | Overstates capacity |
| Rain fade | 0–12 | dB | Scenario input, flat in time over emergency cells | **Hypothetical** | ITU-R rain model and site data | See results |
| Total power | **300** | W | **Project specification.** The dataset's logged allocation sums to 100 W (12 × 8.33 W) | Specified | Confirm payload limit | Fixed |
| Per-beam floor | 2 | W | Unchanged | Derived | Confirm | Low |

## Equations

Implemented independently in `digital_twin/link_budget.py` and tested against `digital_twin/channel.py` in `tests/test_link_budget.py`.

- FSPL = 20 log10(4πd/λ). Reference: 178.47 dB at 1000 km and 20 GHz.
- Prx(dBW) = Ptx(dBW) + G_total − path loss − L_rain.
- N(dBW) = 10 log10(kTB) + NF. Reference: −174 dBm/Hz at 290 K.
- SINR_i = S_i / (N + g_i·G·Σ_j ε_ij·P_j), with ε_ij = 10^(−iso_ij/10) and iso_ij = min(20 + 5·(rings_ij − 1), 40) dB.
- Capacity = B log2(1 + SINR) × (1 − overhead), and 0 below the minimum SINR.

## Why the interference model changed

With 12 beams, the v2 rule (every other beam leaks at −20 dB) caps every cell at about 9.6 dB SINR even when the other beams are 15 km away in another region. The distance rule keeps −20 dB for adjacent beams and lets far beams barely interact. Ring distance uses the median nearest-neighbour spacing (2.08 km), because cells overlap where the three regions meet.

## Known oddities to review

- The pass is compressed: elevation moves from 25° to 85° in one second of slots.
- Line of sight flickers per cell and slot, like random blockage, rather than following terrain.
- Interference uses the victim cell's own gain, not a full beam-pattern coupling.
