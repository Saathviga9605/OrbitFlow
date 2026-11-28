# OrbitFlow 3.0: Hackathon Readiness Report

Every number below comes from files in `results/`. OrbitFlow is an offline simulation. It has no connection to a real satellite, does not run Sionna or OpenNTN live, and does not establish regulatory compliance.

## V3. The 58-cell dataset (current)

Version 3 moves OrbitFlow from 19 cells / 4 beams / 100 W to the revised dataset: **58 cells in three regional clusters (~163 km²), 12 beams, 300 W**. Sections A–I below the line are the 19-cell (v2.1) report, kept unchanged for history; their numbers do not apply to v3.

### V3.1 What the data says (see `docs/data_provenance.md`)

- 100 slots × 58 cells × 10 ms; 12 beams logged in every slot; logged power 12 × 8.33 W = 100 W, against the 300 W specification (OrbitFlow uses 300 W).
- **Line of sight in 36% of cell-slots** (2% early in the pass, 95% at the end), against 98% in the 19-cell pass. Path loss is FSPL(20 GHz) + 1.5 dB with LOS and +18 dB without.
- Demand ramps through the pass: six fixed hotspots (cells 0–5, mean 181 Mbps, peak ~470) and background cells (mean 16.2 Mbps).
- Reported, not corrected: arrival-rate columns are ~2× the requested rate (both are test conditions), `served_rate_mbps` is always 0, and the SINR column is unusable.

### V3.2 Model changes

| Change | Why |
|---|---|
| Bandwidth 20 → 80 MHz (`scripts/calibrate_link.py`, baselines only) | Served demand for non-learning baselines saturates near 80 MHz; NLOS stays undecodable, as in the export |
| Distance-aware interference isolation: 20 dB adjacent, +5 dB per ring, 40 dB floor | With 12 beams, "every beam leaks at −20 dB" capped every cell near 9.6 dB SINR even 15 km apart |
| Synthetic demand follows the pass envelope; levels recalibrated (16.2 / 181 Mbps) | Otherwise synthetic load lands on slots where almost no cell has LOS |
| Demand thresholds scaled ×4.5 (forecast jump 22.5 Mbps, gate 22.5, alert floor 45, state drift 45 / 36 Mbps) | Same relative sensitivity at the new demand level |
| New KPI `rt_sla_violation_servable` | Counts late RT data only where an equal-share beam could have decoded the cell within the 100 ms window |
| Forecaster and BRIDGE retrained (5 seeds each for BC+forecast, BC+no forecast, scratch) | Demand ~4.5× higher, 3× more beams |

### V3.3 Why the headline KPI changed

About 97% of late time-critical data in the 58-cell pass comes from cells that no beam could decode at that moment (`scripts/diagnose_late.py`). Every competent scheduler therefore sits at 12–13% total lateness, and differences between them are hidden. The UI and this report lead with the serviceable KPI and always show total lateness next to it.

### V3.4 Network evaluation (100 paired episodes, 5 training seeds, Holm-corrected Wilcoxon)

Recorded pass:

| Controller | Late, serviceable | Late, all | Mean delay | Throughput | Switches/slot |
|---|---:|---:|---:|---:|---:|
| Fixed rotation | 36.27% | 38.0% | 128.6 ms | 830 Mbps | 11.54 |
| Reactive greedy | 1.35% | 12.7% | 81.8 ms | 1256 Mbps | 7.20 |
| Hand-written predictive rule | **1.07%** | 12.5% | 83.1 ms | 1246 Mbps | 7.28 |
| Behaviour clone | 1.19% | 12.5% | 82.4 ms | 1267 Mbps | 7.16 |
| BRIDGE, no forecast | 1.96% | 13.1% | 87.6 ms | 1136 Mbps | 7.45 |
| BRIDGE | 1.20% | 12.5% | 83.4 ms | 1233 Mbps | 7.34 |

BRIDGE vs Reactive (serviceable): −0.14 points (95% CI −0.16 to −0.12), 92 wins / 8 losses, p_holm < 0.001, r = −0.97.

All conditions, serviceable late data, Reactive → BRIDGE (best controller in brackets):

| Condition | Reactive | BRIDGE | Best |
|---|---:|---:|---|
| normal | 0.64% | 0.54% | BRIDGE no-forecast |
| block | 1.43% | 1.22% | BRIDGE no-forecast |
| event surge | 0.73% | 0.62% | BRIDGE no-forecast |
| bursty | 1.48% | **1.88%** | BRIDGE no-forecast |
| mixed | 0.84% | 0.74% | BRIDGE no-forecast |
| recorded pass | 1.35% | 1.20% | Hand-written rule |
| arrivals column | 10.87% | 8.59% | Behaviour clone |
| traffic ×0.5 | 0.83% | 0.83% (tie, p = 0.92) | Hand-written rule |
| traffic ×0.75 | 1.10% | 1.01% | Hand-written rule |
| traffic ×1.25 | 1.78% | **2.14%** | Hand-written rule |
| traffic ×1.5 | 2.16% | **2.35%** | Hand-written rule |
| channel −6 dB | 2.81% | **3.10%** | Hand-written rule |
| channel −3 dB | 1.88% | 1.55% | Hand-written rule |
| channel +3 dB | 6.91% | 6.83% | Hand-written rule |
| outage 10% | 2.92% | 2.74% | Hand-written rule |
| outage 25% | 6.19% | 5.63% | BRIDGE |
| pass shift −20 | 3.68% | 3.45% | BRIDGE no-forecast |
| pass shift +20 | 3.84% | 3.86% (tie, p = 0.32) | Hand-written rule |
| initial backlog 5 ms | 1.33% | 1.18% | Hand-written rule |
| initial backlog 50 ms | 1.33% | 1.18% | Hand-written rule |

Summary: BRIDGE is lower than Reactive in 14 of 20 conditions, tied in 2, worse in 4. Mean delay is higher than Reactive's in all 20, by 1.3–14 ms. **BRIDGE is not the best controller in v3**: the hand-written predictive rule or the no-forecast BRIDGE is lowest in most conditions. (Serviceable lateness can rise when the channel improves, because more cell-slots become serviceable.)

### V3.5 Why BRIDGE no longer dominates

1. **Little headroom.** Most lateness is unavoidable (no line of sight); what remains is ~1% of cell-slots.
2. **An easier allocation problem per beam.** 12 beams for 58 cells with six fixed hotspots: covering the hotspots and whichever cells have LOS already captures most of the value.
3. **A weaker forecast.** The GRU is worse than repeat-last on the recorded pass (MAE 2.82 vs 1.53; gradient boosting 0.68) and on random bursts (4.38 vs 3.59). It cuts surge-jump error by 76%.
4. **PPO barely moved from its warm start.** With BC + forecast, PPO beat BC on validation in 2 of 5 seeds; without forecast and from scratch, 5 of 5.
5. **One pass geometry.** Shifting the pass by 20 slots removes the advantage.

Planned next (not yet done): reward on serviceable lateness, pass-shift and LOS augmentation in training, and a forecaster retrained on pass dynamics or gated off when uncertain. If they do not help, v3 stays as reported here.

### V3.6 Training (validation split only)

| Setup | Validation score | Delay | RT miss (all) | PPO beat BC |
|---|---:|---:|---:|---|
| BC warm start + forecast (deployed) | −100.9 | 65.7 ms | 13.56% | 2 / 5 |
| BC warm start, no forecast | −97.9 | 64.6 ms | 13.46% | 5 / 5 |
| From scratch + forecast | −104.7 | 66.9 ms | 13.62% | 5 / 5 |

The deployed checkpoint (`bridge_ppo_rg_s3`) was chosen before the test runs because its forecast variant was slightly better on the serviceable KPI on validation.

### V3.7 Flood scenario (30 runs) and safety

| Controller | Limit breaches (slots) | Emergency data served | Emergency RT late | Mean delay |
|---|---:|---:|---:|---:|
| Fixed rotation | 21.0 | 7.2% | 77.3% | 163.4 ms |
| Reactive greedy | 27.1 | 29.2% | 30.3% | 111.0 ms |
| BRIDGE alone | 23.0 | 25.6% | 21.7% | 115.5 ms |
| **OrbitFlow** | **0** | 22.0% | 25.8% | 116.5 ms |

The emergency cells are often out of line of sight, so no controller serves much of their data. The agents' contribution is keeping to the limit; they give up some emergency throughput to do it. Need-based and every-slot emergency service deliver about the same (23.4% vs 23.5%); agents off serve 27.2% with 23.4 breach slots.

Stress test: a forced 150 W proposal on cell 23 is cut to the 22 W limit and a human review is raised. Unprompted, BRIDGE puts ≥150 W on one beam in 10.6% of 20,000 decisions (max 250 W). On a busy hotspot with no limit this is reasonable, and it is why the limit is checked every slot.

Latency of decision + checks: 2.03 ms mean, 2.67 ms p99, 7.4 ms max (1,000 decisions, one CPU core).

Scenario suite: 10 / 10 scenarios, 35 / 35 checks. S9 now compares network KPIs only; the stricter UAE-style profile reviews 10 decisions in normal traffic against 7 for the others while executing identical actions, and that count is reported separately.

Tests: 171 passing.

---

# Archive: OrbitFlow 2.1 report (19 cells, 4 beams, 100 W)


The figures in this archive came from files now in `results/legacy_19cell/`. OrbitFlow is an offline simulation. It has no connection to a real satellite, does not run Sionna or OpenNTN live, and does not establish regulatory compliance.

## Blocker register

| Blocker | Previous state | Correction | Validation |
|---|---|---|---|
| Simulated corpus | 3 invented documents presented as the knowledge base | 69 real documents ingested; simulated files moved to test fixtures | `tests/test_rag.py`, 46/46 citations verbatim |
| Single-pass headline | 20.7% vs 0.7% from one episode | 100 paired episodes on each pass, 13 further conditions | `results/multirun.json` |
| Unverified link budget | Calibrated values with no parameter record | Independent equations, parameter sheet, sensitivity runs | `tests/test_link_budget.py`, `docs/link_budget_parameters.md` |
| "PPO barely helps" | Judged on a reward dominated by near-constant terms | Compared on KPIs; 8-variant sweep, then 5 seeds per candidate | `results/ppo_summary.json` |
| Bursty traffic loss | BRIDGE slower than Reactive | Forecast uncertainty gate and reward rebalance | 14.8 vs 15.6 ms, n=100 |
| "Agent overhead" | Assumed to be agent compute | Traced to always-on emergency beams; made need-based | 34.0 to 18.1 ms, `studies/emergency.json` |
| Slot 61 backlog spike | Blamed on abrupt priority end | Taper tested and rejected; need-based service reduced it | Peak 1243 to 837 kb |
| 22 W "legal cap" | Described as law | Relabelled hypothetical; added study using a real ITU-R limit | `tests/test_system.py`, `studies/pfd_mask.json` |
| Unused datasets | OpenNTN and Sionna files unused by any result | Used as a second test trace | `pass:arrivals` |
| Emergency cell dropped | Guard could drop one emergency cell to force another, and audit text misreported it | Emergency cells outrank others when dropping; text reports actual state | `tests/test_system.py` |
| PDF chunking | A line such as "1 MHz band:" became a false heading, splitting clauses | Heading rules tightened | `tests/test_rag.py` |
| Docker untested | Never built | Built and run; health, simulate and UI all responded | Manual run, this session |

## A. Architecture

```
Observe (lagged telemetry) -> Predict (residual GRU + uncertainty gate) -> Decide (BRIDGE, PPO)
   -> Deliberate (Network, Policy, Safety, Supervisor) -> Guard (hard limits) -> Execute (digital twin) -> Audit (JSONL)
```

Evidence is retrieved once at start-up, so retrieval is outside the per-slot path. Agents are deterministic rules; no LLM is used anywhere. The guard always runs, in every configuration. Priority order: hard limits, then operating constraints, then safety, then optimisation.

## B. Knowledge base

- **Sources:** `CrashingGuru/ITUAIReadiness` at commit `84010da`, directory `simulation/server/knowledge/InputDocs` (MIT repository licence; documents keep their publishers' terms), plus four team-supplied documents: ITU-R SF.358-5, S.1503-4, S.524-8 and FCC 26-26.
- **Totals:** 71 files, 69 ingested, 4,105 pages, 11,790 chunks. 63 can count as evidence.
- **Failed in both PDF parsers:** `China_AI_Security_Governance_Framework_2025.pdf` (stream ended unexpectedly) and `Kenya_AI_Strategy_2025-2030.pdf` (invalid `/Pages` object). No OCR tool was available.
- **Excluded from evidence:** `*_summary.txt` and `sample_*.txt`; the source repository itself labels the samples as estimated test data.
- **Near-duplicates flagged:** UNCTAD chapters 3 and 4 overlap the full report.
- **Provenance:** 71/71 documents have checksum and source path. Issuer and year are partly inferred from filenames, and each entry says so. See `rag/knowledge_base/manifest.yaml`.

### Retrieval evaluation (33 developer-written queries)

| Method | Section recall@5 | Doc recall@5 | Precision@5 | MRR | Median ms |
|---|---:|---:|---:|---:|---:|
| **BM25 (default)** | 93.9% | 97.0% | 64.8% | 0.81 | 26 |
| Hybrid + dense | 90.9% | 93.9% | 67.3% | 0.75 | 100 |
| BM25 + TF-IDF | 84.8% | 90.9% | 61.8% | 0.76 | 41 |
| TF-IDF | 81.8% | 87.9% | 53.9% | 0.67 | 34 |
| Dense (bge-small) | 78.8% | 87.9% | 57.0% | 0.71 | 61 |

One query is about 3 percentage points, so the top two are not clearly separated. BM25 was chosen because it is at least as good and needs no neural model. The set was written by the developer, not independent judges.

### Rule evidence

- **Found:** satellite emissions limited by flux density (SF.358-5); flux-density mask (SF.358-5); NGSO limits in 19.7-20.2 GHz (FCC 26-26, US); human oversight and traceability (ASEAN guide); policy node and sandbox (Y.3172).
- **None found (gap candidates, not human-verified):** emergency traffic priority on network resources; SSB/SIB signalling protection; emergency exemption from a power limit. These are gaps in this corpus, not findings about the law.

### ITU AI Readiness mapping

Factor names come from ITU's *AI Ready* Report 2.0. Full verified quotes are in `results/kb_report.json`. This mapping does not claim OrbitFlow establishes readiness.

| Factor | Exact framework statement | OrbitFlow's contribution | Confidence |
|---|---|---|---|
| Open data | "Accessibility and quality of datasets for analysis of AI applications." | Documents datasets, dead columns and synthetic demand | Medium |
| Research | "Collaboration between domain-specific and AI research communities." | Reproducible experiments and negative results | Medium |
| Deployment | "Infrastructure and ecosystem readiness for AI deployment." | Measures compute against the slot time; nothing deployed | Low |
| Standards | "Ensuring trust, interoperability, and compliance." | Design mapping to the Y.3172 policy node; not conformance | High |
| Open source | "Enabling rapid adoption through an open developer ecosystem." | Code, seeds and configs available | Medium |
| Sandbox | "Platforms for AI experimentation and validation." | Digital twin in the ML-sandbox role; provisional parameters | High |

## C. Link budget

Equations pass reference tests: FSPL 178.47 dB at 1000 km and 20 GHz; noise −174 dBm/Hz at 290 K. The twin matches an independent budget to 1e-6 dB. The dataset's FSPL column implies a 20 GHz carrier within 0.05 dB. **Antenna gain, bandwidth, isolation, noise figure and minimum SINR remain assumed.** See `docs/link_budget_parameters.md`.

### Sensitivity (one at a time, n=30, BRIDGE not retrained)

Late data improves against Reactive in every setting. Delay does not:

| Setting | Late data: Reactive vs BRIDGE | Delay ms: Reactive vs BRIDGE |
|---|---:|---:|
| Nominal | 12.0% vs 0.1% | 15.1 vs 14.3 |
| Gain 47 dB | 14.7% vs 2.7% | 21.7 vs 29.0 |
| Gain 56 dB | 11.8% vs 0.0% | 14.7 vs 12.8 |
| Bandwidth 10 MHz | 20.6% vs 7.8% | 38.5 vs 53.8 |
| Bandwidth 40 MHz | 11.7% vs 0.0% | 14.5 vs 12.0 |
| Isolation 15 dB | 12.6% vs 0.7% | 16.1 vs 21.2 |

Full results, including emergency service under each setting, are in `results/studies/link_sensitivity.json`.

### Flux-density study (indicative)

ITU-R SF.358-5 recommends limits of −115 to −105 dB(W/m²) in any 1 MHz. Its listed bands stop at 19.7 GHz and our carrier is 20.0 GHz, its own note says definitive limits are in the Radio Regulations (not in the corpus), and transmit gain is unknown. n=30 per row.

| Assumed Tx gain | Median cap per beam | Emergency served | Delay ms | Breaches: with / without agents |
|---|---:|---:|---:|---:|
| No limit | n/a | 95.2% | 15.8 | n/a |
| 15 dBi | 80 W | 95.2% | 15.8 | 0 / 0 |
| 20 dBi | 25 W | 94.9% | 16.8 | 0 / 58 |
| 25 dBi | 8 W | 82.3% | 36.6 | 0 / 96 |
| 30 dBi | 2.5 W | 45.0% | 98.3 | 0 / 100 |

**Open question:** the true transmit gain decides whether this limit is harmless or dominant.

## D. ML

### Forecaster

Residual GRU against repeat-last and gradient boosting, on 18 test episodes per kind and the real pass.

| Scenario | Jump-error reduction vs repeat-last | Overall MAE: repeat-last / GRU / GBM (Mbps) |
|---|---:|---:|
| Gradual surge | 71% | 0.35 / 0.35 / 0.53 |
| Surge + steady | 72% | 0.37 / 0.37 / 0.59 |
| Bursty | 43% | 2.63 / 3.18 / 2.84 |
| Block (abrupt) | 2% | 0.87 / 0.99 / 1.31 |
| Real pass | 2% | 1.66 / 1.80 / 2.07 |
| Normal | n/a | 0.29 / 0.30 / 0.22 |

Value is concentrated at ramps. Overall MAE is equal or worse than repeat-last, and GBM wins on calm traffic.

### PPO and behaviour cloning

The earlier "PPO barely helps" came from the reward: its 1.3/slot was mostly constant terms. On validation KPIs, 5 seeds each:

| Variant | Delay ms | RT miss | Selection score (lower is better) |
|---|---:|---:|---:|
| Behaviour clone only | 22.9 | 0.15% | n/a |
| Base PPO | 16.2 | 0.23% | 2.16 ± 0.10 |
| From scratch, no cloning | 15.2 | 0.21% | 2.00 ± 0.41 |
| Forecast gate | 16.1 | 0.11% | 1.56 ± 0.09 |
| **Gate + rebalanced reward (selected)** | **15.8** | **0.11%** | **1.54 ± 0.08** |

The rule, `delay/16 + RT miss/0.2%`, was fixed before results were seen and uses validation data only. The top two are within noise. Also swept: gamma 0.99, lower entropy, higher learning rate, all with one seed and no clear gain. Hard limits stay in the guard, not the reward. Energy is not optimised: power stays near 100 W.

**Behaviour cloning:** demonstrations were 99.8–100% valid with balanced coverage (each cell picked 18–25% of the time). The clone matches its teacher on 81–95% of beams. The teacher's weakness is that it serves backlog evenly, which gives 30+ ms delay on hotspot traffic. PPO from scratch reaches similar results, so cloning is a useful head start, not essential.

## E. Network evaluation

Recorded pass with noise and fading replicates, n=100, 5 training seeds averaged per episode.

| Strategy | Late data | Delay ms | Throughput Mbps |
|---|---:|---:|---:|
| Fixed rotation | 1.95% | 98.0 | 117.4 |
| Reactive | 19.64% | 16.1 | 169.4 |
| Hand-written rule | 0.76% | 30.8 | 166.4 |
| Behaviour clone | 0.76% | 32.3 | 167.1 |
| BRIDGE, no forecast | 0.46% | 18.4 | 169.2 |
| **BRIDGE** | **0.57%** | **15.9** | **169.6** |

- **Headline:** the 20.7% vs 0.7% single-pass result generalises: 19.6% vs 0.6% over 100 replicates, and 13.7% vs 2.0% on the second dataset. Those replicates share one geometry, so they aren't independent passes.
- **Forecast value:** significant delay cut on the recorded pass (−2.5 ms) and block traffic (−3.2 ms), negligible on gradual surges (−0.04 ms), where a forecast should help most. So the mechanism is not simply "seeing ramps", and it's not established. It slightly worsens late data on the recorded pass (+0.12 points).
- **Bursty traffic:** BRIDGE 14.8 vs Reactive 15.6 ms; the loss is gone. Diagnosis: forecast errors at burst edges (GRU MAE worse than repeat-last here). The gate and reward address it; with the earlier single-seed model it was 17.6 ms.
- **Where BRIDGE loses:** when capacity is scarce, delay is worse than Reactive: second dataset (18.4 vs 16.3), 125% traffic (23.1 vs 18.1), 150% traffic (36.1 vs 25.6), 6 dB worse signal (40.1 vs 28.3), and 25% blocked links (19.7 vs 16.3). It also doubles beam switching (3.4 vs 1.7 per slot) and normal load is effectively tied. Switching overhead is not modelled in the twin, so this cost is unmeasured.

### Agent overhead

Compute, 1,000 decisions on one core: **2.14 ms mean, 3.46 ms p99, 5.27 ms max** on the evaluation laptop (1.43 ms mean on the original desktop), within the 10 ms slot. BRIDGE 1.25, guard 0.81, Policy 0.03, Safety 0.05 ms; audit 0.10 ms outside the decision. Precomputing avoids about 24 ms per live retrieval. Python on a desktop is not a real-time guarantee.

The 14 to 23 ms rise was queueing, from lighting emergency cells every slot. Flood relief, end=61, n=30:

| Mode | Delay ms | RT misses | Emergency served | Emergency RT miss | Peak backlog after end (kb) |
|---|---:|---:|---:|---:|---:|
| Always + abrupt (previous) | 27.0 | 7.1% | 101.3% | 0% | 1243 |
| Always + taper | 27.9 | 7.2% | 101.3% | 0% | 1226 |
| **Need-based + abrupt (selected)** | **15.9** | **0.0%** | **94.4%** | **0%** | **837** |
| Need-based + taper | 16.3 | 0.0% | 94.4% | 0% | 845 |
| Agents off | 15.6 | 0.0% | 96.3% | 0% | 757 |

**Trade-offs:** need-based delivers less total emergency data than always-on (92.8% vs 101%) and about the same as agents off (92.7%), while no emergency deadline was missed. The agents buy constraint compliance (22.8 breach slots to 0) at about 0.65 ms of mean delay; before the guard fix in docs/OPERATIONS.md §12, that cost was about 2 ms. Always-on mode stays configurable if an operator values emergency volume. Taper added nothing. The same pattern held across durations of 45, 61 and 80 slots and traffic of 75–125%.

### Rain and resource limits

Factorial with paired seeds, n=30 per cell. Emergency data served:

| Rain \ Cap | None | 22 W | 8 W |
|---|---:|---:|---:|
| 0 dB | 97.3% | 97.0% | 94.1% |
| 6 dB | 95.2% | 94.4% | 88.8% |
| 12 dB | 87.9% | 84.8% | 73.4% |

- Effects compound: the 12 dB and 8 W interaction is −11.3 points beyond the sum of the separate effects.
- 22 W binds in about half of the capped slots yet costs under 1 point in clear sky, because signal quality is interference-limited: 25 W to 22 W moves the ceiling only from 15.2 to 14.5 dB, and capacity grows with its logarithm.
- All of this depends on provisional link values, and rain is a flat scenario input, not an ITU-R rain model.

### Constraint stress test (controlled, not part of the flood)

`scripts/run_studies.py` injects 50 W on cell 13. At slot 52: 22 W cap, Policy FAIL, executed 22 W, rest redistributed. 0 breaches. Other cases: 200 W total scaled to 100 W; 6 beams reduced to 4; 0.5 W lifted to 2 W. **BRIDGE produces 50 W or more unprompted in 0.28% of 20,000 decisions (max 84 W).** The original scripted clash rarely arises because power concentration gains little capacity.

## F. Statistics

- **Runs:** 100 paired episodes per scenario and pass, 50 for 13 other conditions; 30 for flood studies. 5 training seeds. Test seeds from 50000, disjoint from split seeds 1000–5119. Flood seeds from 100.
- **Number of runs:** chosen for feasibility; the resulting CI half-width on late data (about 0.1 points on the recorded pass) is far smaller than the effect.
- **Reported:** mean, SD, median, bootstrap 95% CI, n in `results/multirun.json`.
- **Tests:** Wilcoxon signed-rank (differences often skewed or tied, so no normality assumption), with Holm correction across policies, rank-biserial r and Cohen's dz.
- **Headline test:** BRIDGE vs Reactive, late data, recorded pass: 100/100 episodes better, Holm p < 0.001, r = −1.0. Mean difference −19.1 points (CI −19.2 to −19.0).
- **Caution:** with this many paired episodes, tiny differences reach significance. Normal-load delay differs by 0.05 ms at p < 0.001, which is meaningless. Replicates share geometry, so p-values do not extend to other passes or orbits.

## G. Remaining limitations

- **Provisional:** antenna gain, bandwidth, isolation, noise figure, minimum SINR, signalling limits. **No ECE review has happened.**
- **Simulated:** flood, emergency timing, rain fade, 22 W cap, border cells, all synthetic demand.
- **One geometry:** the same compressed 1-second pass and 2 km cells throughout. Generalisation to other orbits is untested.
- **Not modelled:** beam-switching overhead, MCS tables (Shannon is optimistic), polarisation and implementation losses, multi-satellite handover.
- **Not built:** LLM features (deliberately absent), live E2/O-RAN, S.1503 EPFD checks.
- **Knowledge base:** no Radio Regulations, 3GPP or O-RAN documents; two failed PDFs; no human verification; FCC 26-26 is US-only and its rule status should be checked. Retrieval does not establish compliance.
- **UI:** what-if grid uses seed 42 per cell; only the API runs new simulations. No automated browser test beyond the screenshot script.

## I. Submission checklist

| Item | Status |
|---|---|
| Functional application | Done; loads with no console errors, desktop and mobile |
| Backend | Done; API tests pass |
| Frontend | Done; static build |
| Model training | Done; 5 seeds, logs in `results/exp/` |
| Evaluation reproducibility | Scripts and seeds available; the full pipeline was run in stages, not from one clean checkout |
| Real knowledge base | Done; two PDFs failed |
| Link-budget validation | Equations done; **values await ECE review** |
| Constraint correctness | Done; 0 breaches in the runs tested |
| Agent auditability | Done; every slot recorded |
| Scenario reproducibility | Done; tested |
| Documentation | Done |
| Docker build | Done; built and run once |
| Demo readiness | Done; **rehearsal still needed** |
| Human legal review | **Not done** |
