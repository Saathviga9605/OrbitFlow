# What the NTN dataset actually contains (for the whole team)

Source: `dynamic_ntn_dataset.csv` — 1 satellite, 19 cells, 100 slots x 10 ms (a 1-second pass).

| Finding | Consequence |
|---|---|
| Logged policy always lights exactly 4 beams; power sums to 100 W each slot | K = 4, Pmax = 100 W |
| `subchannel_sinr_db` is -30 on every row | SINR is recomputed in `digital_twin/channel.py` from `channel_gain_magnitude` |
| `prach_window_flag` is 1 on every row | No PRACH restriction modelled until someone explains it |
| SSB flag alternates every slot; SIB flag every 8th slot | Timing guard uses these as the SSB/SIB schedule |
| Queues and HOL delays are a fixed multiple of requested rate (corr 1.00) | They do not react to scheduling, so the twin simulates its own queues |
| RT vs NRT queues (28.5% / 71.5%), delay caps 100 ms / 1000 ms | Used as priority classes and delay budgets |
| Hotspots: {0,1,2,3} slots 0-30, {5,8,12} 31-60, {14,15,17} 61-90, random every slot after 91 | Abrupt, unannounced jumps |
| Hot cell ~ 40.3 Mbps, cold ~ 2.24 Mbps | Generator calibration |
| Logged mask always includes the hotspots, fills the rest randomly | Non-causal reference, not a deployable baseline |

## Forecastability (scripts/forecastability.py)
Error at demand jumps, 3 slots ahead: smoothed-slope extrapolation vs repeating the last value.

| Scenario | Gain from forecasting |
|---|---|
| Real dataset | -13% (worse) |
| Block hotspots (dataset-like) | 0% |
| Bursty | -17% (worse) |
| Event surge (ramp-up precursor) | +58% |

Prediction pays off only when demand has a precursor. The demo scenario must contain one.

## Assumptions to confirm with the ECE teammates (config.yaml)
1. Link budget: `antenna_gain_db` was calibrated so a lit beam sees ~11 dB mean SINR. Replace with the real budget.
2. Timing guard: every cell must reach an SSB slot within 40 slots and a SIB slot within 80 slots.
3. What `prach_window_flag = 1` on every row means.
4. Which cells are border cells (footprint spills into a neighbouring country) for the policy scenario.
