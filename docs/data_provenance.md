# Dataset and model provenance

OrbitFlow v3 uses the **revised 58-cell dataset**: two offline CSV exports in `data/raw/`, 100 slots × 58 cells × 10 ms, covering three regional clusters of 19, 19 and 20 hexagonal cells (2.08 km pitch, about 217 km² of hexagon area; the brief quotes ~163 km² of covered area). **OrbitFlow does not run Sionna or OpenNTN live and has no connection to a real satellite.** The filenames indicate their origin; this repository cannot verify how they were generated.

The 19-cell dataset used up to v2.x is archived unchanged in `data/legacy_19cell/`, with its models in `models/legacy_19cell/` and results in `results/legacy_19cell/`.

| File | Columns used | Used for |
|---|---|---|
| `open_ntn_traffic_dataset.csv` | Geometry, LOS, gain, SSB/SIB/PRACH, requested rate, per-class arrival rates, hotspot flag, logged mask and power, initial queues | Pass geometry, channel and demand: the primary external test pass (`pass:recorded`) and the base for all synthetic training traces |
| `sionna_channel_dataset.csv` | Region, cell global x/y, path loss, gain, LOS, elevation, slant range | Cell map and region membership (UI, interference model); consistency check of the channel |

## Measured facts about the export (checked by `tests/test_system.py` and `tests/test_link_budget.py`)

- **Consistency:** gain, LOS, elevation and cell coordinates are identical in both files.
- **Channel:** path loss = FSPL at 20 GHz + 1.5 dB with line of sight, + 18 dB without; gain = −path loss.
- **Pass:** elevation rises from 25° to 85°. Line of sight behaves like random per-slot blockage whose probability rises through the pass: 2% of cell-slots in the first 30 slots, 95% at the end, **36% overall** (the 19-cell pass had 98%).
- **Beams and power:** every slot logs exactly **12 active beams**. The logged allocation is 12 × 8.33 W = **100 W**; OrbitFlow uses the specified **300 W** budget (25 W per beam on average, the same as 100 W / 4 beams in the 19-cell setup).
- **Demand:** every cell's requested rate ramps up through the pass. Background cells go from 0.3 to about 32 Mbps (mean 16.2); the six hotspots (cells 0–5, region 1) go from 0 to about 470 Mbps (mean 181). Total demand averages 2.0 Gbps and peaks at 4.5 Gbps. The hotspot set never changes.
- **Inconsistencies, reported not corrected:** the per-class arrival-rate columns are about 2× `requested_rate_mbps` (both are offered as test conditions: `pass:recorded` and `pass:arrivals`); `served_rate_mbps` is always 0; `subchannel_sinr_db` is −150 dB for most rows and never above −40 dB, so SINR is rebuilt by the link model.

## Synthetic demand (`traffic/generator.py`)

Calibrated to the export's pass-average levels (background 16.2 Mbps, hotspot 181 Mbps, same noise-to-level ratios as before). Synthetic demand follows the dataset's **pass envelope**: background demand rises from ~2% to ~180% of its mean as the satellite rises, as in the data. Without it, synthetic traces would put full load on slots where almost no cell is in line of sight.

## Forecaster (`traffic/forecaster.py`)

- **Input:** 12-slot window of 6 features per cell; rate normalised by 200 Mbps (was 40).
- **Output:** demand for the next 3 slots, as a correction to repeat-last.
- **Data:** five synthetic kinds, 120 episodes each, on the recorded pass geometry. Split by episode, stratified, 70/15/15, seeds 1000–5119.

## BRIDGE (`bridge/policy.py`, `bridge/train_ppo.py`)

- **Input:** 19 features per cell (`build_features`), telemetry lagged one slot. The network is permutation-equivariant, so the same architecture runs on 58 cells; it was **retrained** because demand is ~4.5× higher.
- **Output:** ordered 12 beams (Plackett-Luce) and a 300 W power split (Dirichlet).
- **Training:** train split only, model selection on validation only. Test seeds from 50000.

## Limitations

- One pass geometry across all training and test data; generalisation to other orbits is untested.
- Synthetic demand is calibrated to one export's levels, not to measured traffic.
- The two demand columns disagree by 2×, and the logged power (100 W) differs from the specified budget (300 W).
