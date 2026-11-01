# OrbitFlow

**Predictive, safety-checked beam hopping for a LEO satellite, in simulation, with every decision audited.**

A satellite can light 4 of 19 cells per 10 ms slot on a 100 W budget. OrbitFlow forecasts demand, chooses beams with a reinforcement-learned policy, and checks each choice against hard limits and operating constraints before it runs. It is an offline simulation.

```
Observe -> Predict (GRU + gate) -> Decide (BRIDGE, PPO) -> Deliberate (4 rule-based agents + evidence) -> Guard -> Execute (twin) -> Audit
```

## Run it

```bash
cd dashboard/frontend && npm install && npx vite build && npx vite preview --port 4173   # http://localhost:4173
# or UI + API (run a built UI from the repo root):
python -m uvicorn dashboard.api:app --port 8000
# or container:
docker compose up --build                                                                 # http://localhost:8000
```

Trained models and results are included. Presenter script: [docs/demo_script.md](docs/demo_script.md). Full results, statistics and limitations: [docs/REPORT.md](docs/REPORT.md).

## Results

100 paired test runs of a recorded pass, 5 trained models, none of this data used in training.

| Strategy | Late time-critical data | Mean delay (ms) | Throughput (Mbps) |
|---|---:|---:|---:|
| Reactive greedy | 19.6% | 16.1 | 169.4 |
| **BRIDGE** | **0.6%** | **15.9** | **169.6** |

- On a second dataset (OpenNTN demand, Sionna-derived channel, offline exports): 13.7% vs 2.0%.
- Decision and safety checks: 1.4 ms mean, 2.2 ms p99, on one CPU core.
- In a flood scenario, agents reduce breaches of a hypothetical limit from 23 slots to 0, with no emergency deadline missed.

**Where it loses:** under scarce capacity its average delay is worse than Reactive (36 vs 26 ms at 150% traffic). It switches beams twice as often. In the flood, agents deliver slightly less total emergency data than no agents (94% vs 96%). All runs share one pass geometry.

## Status of the inputs

| | |
|---|---|
| **From data** | Pass geometry, channel, timing (offline datasets, see [docs/data_provenance.md](docs/data_provenance.md)); 69 real policy and regulatory documents |
| **Generated** | Training demand; the flood scenario |
| **Hypothetical** | The 22 W limit. A separate study applies ITU-R SF.358-5 as an indicative guide |
| **Provisional** | Antenna gain, bandwidth, interference, noise figure ([parameter sheet](docs/link_budget_parameters.md), awaiting ECE review) |
| **Not claimed** | Regulatory compliance, live network or Sionna integration, national AI readiness |

Agents are deterministic rules by design; there is no LLM in this system.

## Reproduce

```bash
pip install -r requirements.txt
python scripts/fetch_kb.py && python -m rag.ingest    # fetch and index the source documents
python -m rag.eval_retrieval --build-dense && python scripts/build_kb_report.py
python -m pytest -q tests
python -m traffic.train_forecaster                    # about 6 min on CPU
# BRIDGE: selected configuration is in config.yaml
for s in 1 2 3 4 5; do python -m bridge.train_ppo --tag rg_s$s --seed $s; python -m bridge.train_ppo --tag rgnf_s$s --seed $s --no-forecast; done
python scripts/run_experiments.py --tag rg --gate     # multi-run evaluation
python scripts/run_studies.py --tag rg                # emergency, factorial, flux-density, latency, stress, sensitivity
python scripts/run_eval.py                            # replay, what-if grid, copies web data
cd dashboard/frontend && npx vite build
```

## Layout

```
traffic/       forecaster, synthetic demand, splits
bridge/        BRIDGE policy, PPO + behaviour cloning, baselines
digital_twin/  queues, SINR, KPIs, explicit link budget
bam/           guardrail: hard limits and repair
agents/        Network, Policy, Safety, Supervisor; policy_rules.yaml
rag/           ingestion, retrieval, citation checks, manifest
scenarios/     event engine with information boundaries, flood relief
audit/         per-slot JSONL records
scripts/       experiments, studies, evaluation
dashboard/     FastAPI server and story UI
```

## References

- Schulman et al., "Proximal Policy Optimization Algorithms", 2017.
- Kool et al., "Stochastic Beams and Where to Find Them", ICML 2019. Gumbel-Top-K is a sampler with an exact Plackett-Luce log-probability; learning uses policy gradients.
- ITU-T Y.3172; ITU-R SF.358-5; ITU AI Ready Report 2.0. Knowledge-base sources are listed in `rag/knowledge_base/manifest.yaml`.

Code: MIT licence. Knowledge-base documents keep their publishers' terms and are fetched, not redistributed.
