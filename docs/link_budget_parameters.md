# Link-budget parameter sheet (for ECE review)

**Status: provisional. No value here has been reviewed or approved by the ECE team.** To replace a value, edit `link:` in `config.yaml` and rerun `scripts/run_experiments.py` and `scripts/run_studies.py`.

Sensitivity results are in `results/studies/link_sensitivity.json`.

| Parameter | Current value | Unit | Source | Class | Recommended validation | Sensitivity |
|---|---:|---|---|---|---|---|
| Carrier frequency | 20 | GHz | Implied by dataset `fspl_db` and `slant_range_km` (agrees within 0.05 dB) | Derived | Confirm against the scenario definition | Already inside the dataset gain |
| Slant range | 510–1380 | km | Dataset `slant_range_km` | Dataset | Check against orbit altitude | Inside the gain |
| Elevation angle | 21.7–85 | deg | Dataset | Dataset | Check against ephemeris | Inside the gain and LOS |
| Free-space path loss | Dataset value | dB | Dataset; matches 20 log10(4πd/λ) | Derived | None beyond the test | Inside the gain |
| Atmospheric loss | Dataset value | dB | Dataset `atm_loss_db`; model unknown | Dataset | Ask the dataset's author for the model | Inside the gain |
| Channel gain | Dataset value | linear | Dataset; about -(FSPL + atmosphere) with 2.1 dB spread | Dataset | Confirm fading model | Inside the gain |
| Total antenna gain (Tx + Rx) | 53 | dB | **Calibrated so a lit beam sees about 11–15 dB** | **Assumed** | Replace with real EIRP and G/T | See results |
| Bandwidth per beam | 20 | MHz | **Chosen** | **Assumed** | Confirm carrier plan | High: capacity scales directly |
| Interference isolation | 20 | dB | **Chosen** | **Assumed** | Replace with beam pattern side-lobe data | See results |
| Noise figure | 7 | dB | **Chosen** | **Assumed** | Replace with terminal spec | See results |
| Noise temperature | 290 | K | Standard reference value | Assumed | Replace with system temperature | Tied to noise figure |
| Minimum decodable SINR | -6 | dB | **Chosen** | **Assumed** | Replace with MCS table | See results |
| SSB / SIB overhead | 5% / 5% | capacity | **Chosen** | **Assumed** | Derive from NR numerology | Low |
| Spectral efficiency | Shannon bound | bit/s/Hz | Formula, no implementation margin | **Optimistic** | Replace with MCS-based curve | Overstates capacity |
| Rain fade | 0–12 | dB | Scenario input, flat in time over emergency cells | **Hypothetical** | Replace with an ITU-R rain model and site data | See results |
| Polarisation loss | Not modelled | dB | Absent | **Missing** | Add if relevant | Unknown |
| Implementation loss | Not modelled | dB | Absent | **Missing** | Add to the budget | Unknown |
| Total power | 100 | W | Dataset logged power sums to 100 W | Dataset | Confirm payload limit | Fixed |
| Per-beam floor | 2 | W | Dataset minimum is about 2 W | Derived | Confirm | Low |

## Equations

Implemented independently in `digital_twin/link_budget.py` and tested against `digital_twin/channel.py` in `tests/test_link_budget.py`.

- FSPL = 20 log10(4πd/λ). Reference: 178.47 dB at 1000 km and 20 GHz.
- Prx(dBW) = Ptx(dBW) + G_total − FSPL − L_atm − L_rain.
- N(dBW) = 10 log10(kTB) + NF. Reference: −174 dBm/Hz at 290 K.
- SINR = S / (N + ε·g·G·Σ other beam powers), where ε is the isolation as a linear ratio.
- Capacity = B log2(1 + SINR) × (1 − overhead), and 0 below the minimum SINR or without line of sight.

## Known oddities to review

- Dataset cells are about 2 km apart (`cell_x_m` spacing 2078 m), while each slot's elevation moves widely within one second. The pass is compressed. A real LEO footprint has far larger cells.
- Interference uses the victim cell's own gain, not a beam-pattern coupling matrix.
- The dataset's `subchannel_sinr_db` is a constant -30 and is unused.
