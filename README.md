# OrbitFlow

**Predictive, policy-aware beam hopping for a LEO satellite, with every decision audited.**

A satellite can light 4 of 19 cells per 10 ms slot on a 100 W budget. OrbitFlow forecasts demand, chooses beams with a learned policy, and checks each choice against law, safety and hard technical limits before it runs.

```
Observe → Predict (GRU) → Decide (BRIDGE, PPO) → Deliberate (4 agents + RAG) → Guard → Execute (twin) → Audit
```

## Run the demo

```bash
cd dashboard/frontend && npm install && npx vite build && npx vite preview --port 4173
# or serve UI and API together, from the repo root:
python -m uvicorn dashboard.api:app --port 8000
```

The UI is static and needs no server, which makes it reliable on stage. Trained models and results are already in the repo. The presenter script is in [docs/demo_script.md](docs/demo_script.md).

## Results

All numbers come from `scripts/run_eval.py`. Synthetic rows use 18 held-out episodes per scenario. The real pass is one external episode, never used for training or model selection.

| Real pass | Throughput (Mbps) | Mean delay (ms) | RT deadline misses | Proposals failing guard (slots) |
|---|---:|---:|---:|---:|
| Static round-robin | 117.5 | 97.9 | 1.9% | 0 |
| Reactive greedy | 169.7 | 16.2 | 20.7% | 8 |
| Heuristic-predictive | 166.0 | 30.8 | 0.8% | 0 |
| BRIDGE no-forecast | 169.2 | 21.0 | 0.8% | 0 |
| **BRIDGE** | **169.8** | **14.1** | **0.7%** | **0** |
| Logged rule-based (non-causal reference) | 166.2 | 45.0 | 40.6% | 22 |

Flood relief, over 30 demand-noise seeds:

| Controller | Cap breach slots | Emergency served | Mean delay (ms) | RT misses |
|---|---:|---:|---:|---:|
| Reactive greedy | 21.8 | 99.3% | 15.4 | 18.3% |
| BRIDGE alone | 22.1 | 96.3% | 14.0 | 0.1% |
| **OrbitFlow (BRIDGE + agents)** | **0** | **101.2%** | 23.2 | 7.6% |

Served can exceed 100% because the initial backlog is cleared along with new arrivals.

Forecast error at demand jumps, against repeat-last: **71% lower on surges with a ramp, 2% on abrupt block switches and on the real pass.** Inference takes about 1 ms on CPU within a 10 ms slot.

### Where it loses

- BRIDGE has higher mean delay than Reactive on bursty traffic (0 wins, 18 losses).
- The forecast input makes BRIDGE worse on bursty traffic. Its largest gain is on block traffic, where the forecaster adds almost nothing; that gain is unexplained.
- Agents cost performance: delay rises from 14 to 23 ms and RT misses from 0.1% to 7.6% in flood relief.
- Emergency priority ends abruptly at slot 61, causing a backlog spike. It should taper.
- PPO improves only modestly on its behaviour-cloned start (validation reward 130.1 to 134.2).

## What is real, and what is not

| | |
|---|---|
| **Real** | Pass geometry, channel gains, SSB/SIB schedule and the test pass, from the supplied dataset |
| **Synthetic** | Training and test demand, calibrated to the dataset's hot and cold levels |
| **Simulated** | The flood, regulator notice, 22 W cap, border cells and operator procedures |
| **Assumed** | Link budget (calibrated to about 11 dB mean SINR), 40/80-slot signalling limits |
| **Not built** | LLM agents (agents are deterministic rules), neural embeddings (retrieval is BM25 + TF-IDF), a live E2/O-RAN interface, a real legal corpus |

To add real sources, put the files in `rag/knowledge_base/raw/` under the names in `rag/knowledge_base/manifest.yaml`, then rerun `scripts/run_eval.py`. Missing documents are skipped and reported, never faked.

## Layout

```
traffic/       forecaster, synthetic demand, splits
bridge/        BRIDGE policy, PPO + behaviour cloning, baselines
digital_twin/  queues, SINR, KPIs
bam/           guardrail: hard limits and repair
agents/        Network, Policy, Safety, Supervisor; policy_rules.yaml
rag/           ingestion, hybrid retrieval, citation checks, knowledge base
scenarios/     event engine with information asymmetry, flood relief
audit/         per-slot JSONL records
scripts/       run_eval.py: every number in the UI
dashboard/     FastAPI server and the story UI
```

## Reproduce

```bash
pip install -r requirements.txt
python -m pytest -q tests                 # 59 tests
python -m traffic.train_forecaster        # about 6 min on CPU
python -m bridge.train_ppo                # about 15 min
python -m bridge.train_ppo --no-forecast
python scripts/run_eval.py                # about 2 min
cd dashboard/frontend && npx vite build
```

## References

- Schulman et al., "Proximal Policy Optimization Algorithms", 2017.
- Kool et al., "Stochastic Beams and Where to Find Them", ICML 2019. Gumbel-Top-K here is a sampler with an exact Plackett-Luce log-probability; learning uses policy gradients.
- Cho et al., "Learning Phrase Representations using RNN Encoder-Decoder", 2014.

MIT licence.
