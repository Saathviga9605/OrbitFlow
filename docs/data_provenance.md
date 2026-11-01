# Dataset and model provenance

All three datasets are offline CSV exports in `data/raw/`: 100 slots × 19 cells × 10 ms. **OrbitFlow does not run Sionna or OpenNTN live and has no connection to a real satellite.** The filenames suggest their origin; this repository cannot verify how they were generated.

| File | Columns used | Used for |
|---|---|---|
| `dynamic_ntn_dataset.csv` | Geometry, LOS, gain, SSB/SIB, requested rate, logged mask and power | Pass geometry and channel for all synthetic training; the primary external test pass |
| `open_ntn_l2_output.csv` | Requested rate, hotspot flag, SSB/SIB/PRACH flags, initial queues | Demand of the second test pass (`pass:openntn_sionna`). **Not used in training** |
| `sionna_physics_output.csv` | Gain, LOS, elevation, cell x/y | Channel of the second test pass; cell map in the UI. **Not used in training** |

Measured relationships: geometry and LOS are identical across files. Gain correlation between the dynamic and Sionna files is 0.69, with 2.1 dB spread. Rate correlation between the dynamic and OpenNTN files is 0.53. The second pass is a different realisation of the same geometry, **not an independent satellite pass**.

Before version 2.1, the OpenNTN and Sionna files played no part in any result.

## Forecaster (`traffic/forecaster.py`)

- **Input:** 12-slot window of 6 features per cell: demand, difference, window mean and spread, network load, share of rising cells.
- **Output:** demand for the next 3 slots, as a correction to repeat-last.
- **Data:** synthetic demand from `traffic/generator.py` (calibrated to the dataset's hot and cold levels) on the dynamic pass geometry. Five kinds, 120 episodes each.
- **Split:** by episode, stratified by kind, 70/15/15. Seeds 1000–5119. The pass is the same in all splits, so **generalisation to other orbits is untested**.

## BRIDGE (`bridge/policy.py`, `bridge/train_ppo.py`)

- **Input:** 19 features per cell (`build_features`), with telemetry lagged one slot.
- **Output:** ordered 4 beams (Plackett-Luce) and a power split (Dirichlet).
- **Training:** train split only, selection on validation only.
- **Test:** seeds from 50000 upward, the second pass and perturbed real passes.

Training configurations and logs are in `results/exp/`.

## Limitations

- One pass geometry across all training and test data.
- Synthetic demand is calibrated to one dataset's levels, not to measured traffic.
- Dataset queues are a fixed multiple of rate, so the twin simulates its own.
