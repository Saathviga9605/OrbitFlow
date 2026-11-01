# ORBITFLOW — BUILD SPECIFICATION FOR COPILOT (agent mode)

Target: ITU AI for Good Sandbox **Build-a-thon 5.0** — "Creating innovative agents in 5G". 8-hour event, 10 Oct 2026.
Project: **OrbitFlow — Predictive Traffic-Aware Beam Hopping for LEO Non-Terrestrial Networks**, with a policy-aware, auditable multi-agent layer.

---------------------------------------------------------------------------------------------------
## 0. HOW TO USE THIS FILE (read first)

1. Read sections 1–4 completely. Then build milestones **M1 → M10 in order**.
2. After each milestone: run its **ACCEPTANCE** command(s), fix failures, then `git commit -m "M<n>: ..."`.
3. **Do not rewrite** the modules listed in §3. Extend them only with the modifications listed there; keep public signatures backward compatible.
4. Do not stop to ask questions. Make a reasonable choice, append one line to `docs/ASSUMPTIONS.md`, move on.
5. CPU only. Full pipeline (data → predictor → BRIDGE → demo) must finish in **≤ 20 min** on a laptop. Every training/eval script must accept `--fast` (tiny run, < 1 min) for smoke tests.
6. Everything is seeded from `config.yaml: seed`. Same seed → same numbers.
7. Priority tags: **P0** must exist and run · **P1** should · **P2** nice · **P3** stretch (only after all P0/P1 pass).
8. The honesty rules in §8 are non-negotiable (no invented citations, no hidden synthetic data, no hiding bad results).

---------------------------------------------------------------------------------------------------
## 1. WHAT THE PROJECT IS, AND HOW IT IS SCORED

A LEO satellite can light only **K = 4** of **N = 19** ground cells per 10 ms slot, with a total power budget **Pmax = 100 W**. Demand is spatially uneven and time-varying. OrbitFlow is a closed loop:

```
Observe → Predict → Decide (BRIDGE DRL) → Validate/Repair (guardrails + policy) → Execute (digital twin) → Measure → Audit
```

A **Supervisor agent** coordinates a **Network agent** (predictor + BRIDGE), a **Policy agent** (RAG over real documents), and a **Safety agent** (priority traffic, starvation). All decisions are logged with evidence and sources.

Judges score five things. Build for these:

| Criterion | OrbitFlow artefact that answers it |
|---|---|
| Knowledge-base quality | `rag/` (M6): real documents, section-aware chunks, hybrid retrieval, coverage report, retrieval eval |
| Agent capability | `agents/` + progressive scenario (M7), KPI comparison vs baselines (§6) |
| Policy/standards **gap** identification | `agents/gap_analyzer.py` → `docs/gap_analysis.md` (M8): domain-specific gaps, global policy examples, neighbouring-region coverage |
| Auditability | `audit/` JSONL with per-step trace, source attribution, human-review flags |
| Alignment with ITU standards | `docs/y3172_mapping.md`, `docs/ai_readiness_mapping.md` (M10) |

---------------------------------------------------------------------------------------------------
## 2. GROUND TRUTH ABOUT THE DATA (do not contradict)

Source: `data/raw/dynamic_ntn_dataset.csv` — 1 satellite, **19 cells**, **100 slots × 10 ms** (a 1-second compressed pass), 1900 rows.

| Fact | Consequence |
|---|---|
| Logged policy lights exactly 4 beams/slot; power sums to 100 W | K = 4, Pmax = 100 W |
| `subchannel_sinr_db` = −30 on every row (dead column) | SINR is recomputed in `digital_twin/channel.py` |
| `prach_window_flag` = 1 on every row | No PRACH restriction modelled (see `config.yaml: timing_guard.prach`) |
| SSB flag alternates every slot (even slots = 1); SIB flag every 8th slot (slots 0, 8, 16 …) | SIB slots ⊂ SSB slots |
| Queues/HOL delays = fixed multiple of requested rate (corr 1.00); i.e. flat ~125 ms backlog on every cell | Dataset queues are NOT used; twin simulates real queues |
| RT/NRT split 28.5 % / 71.5 %; delay caps 100 ms (RT), 1000 ms (NRT) | Priority classes + delay budgets |
| Hot cell ≈ 40.3 Mbps (σ 0.56), cold ≈ 2.24 Mbps (σ 0.13) | Generator calibration |
| Hotspot sets: {0,1,2,3} slots 0–30 · {5,8,12} 31–60 · {14,15,17} 61–90 · random every slot 91–99 | Abrupt, unannounced jumps → **not forecastable** |
| Logged beam mask always contains the hotspots, filler beam random | Non-causal reference; never a deployable baseline |
| Cell 0 is the sub-satellite cell; cells 1–6 inner ring; cells 7–18 outer ring (inferred from `sub_sat_dist_km`) | Outer ring = candidate "border cells" |
| At slot 0 only cell 0 is visible (LOS); all cells visible from slot 2 | Mask non-visible cells in the policy |

**Measured forecastability** (`scripts/forecastability.py`, 3-slot-ahead error at demand jumps, smoothed-slope extrapolation vs repeat-last-value): real dataset **−13 %** (worse), block hotspots 0 %, bursty −17 %, event-surge with ramp-up **+58 %**.
→ **Prediction only helps when demand has a precursor.** The demo scenario must contain one (§M2), and the results must report both cases honestly.

---------------------------------------------------------------------------------------------------
## 3. EXISTING CODE — CONTRACTS (already in the repo and tested manually)

```
config.yaml                      all tunables (see file). Add new sections; never hard-code constants.
traffic/dataset.py               Trace dataclass; load_trace(path) -> Trace
traffic/generator.py             make_rate(kind,T,N,rng); make_trace(kind, base, seed, fading_jitter_db=1.0);
                                 make_dataset(kinds, base, n_per_kind, seed0=1000);  kinds: normal|block|event_surge|bursty|mixed
digital_twin/channel.py          LinkModel(cfg): .sinr(power_w, gain, lit) ; .capacity_mbps(sinr, los, ssb, sib) ; to_db(x)
digital_twin/environment.py      NTNTwin(trace,cfg): .reset()->obs ; .obs()->dict ; .step(lit,power)->rec ; .done ; .history
                                 summarise(history, slot_ms, extra=None) -> KPI dict
bam/validator.py                 GuardState(ssb_age, sib_age){fresh,copy,advance}; GuardResult; BamGuard(cfg){check, repair}
bridge/baselines.py              Action(lit,power,priority,info); Policy{reset,act}; StaticRoundRobin; ReactiveGreedy; LoggedPolicy
bridge/evaluate.py               run_episode(trace,cfg,policy,lag=None,keep_records=False)->KPI dict ; format_table
audit/schemas.py                 TraceStep, AuditRecord(+add_step,to_dict)
audit/logger.py                  AuditLogger(path){write,read,clear}
scripts/run_baselines.py         baselines on the real trace      scripts/forecastability.py   forecastability table
```

`Trace` fields: `rate, gain, los, elev (T,N)`, `ssb, sib, prach (T,)`, `hot, logged_mask, logged_power (T,N)`, `q0_rt_kb, q0_nrt_kb (N,)`, `slot_ms`, `source`, `meta`.
`obs` keys: `t, slot_ms, rate_obs, rate_hist, gain_obs, q_rt, q_nrt, los, elev, ssb, sib, prev_lit, prev_power, guard`.
Telemetry (`rate_obs`, `gain_obs`) is **lagged by `scenario.obs_lag_slots` = 1 slot** (E2 report delay). Geometry/LOS/SSB-SIB schedule are exact.
KPI keys: `throughput_mbps, demand_mbps, served_ratio, packet_loss, mean_delay_ms, p95_delay_ms, rt_sla_violation, jain_fairness, mean_sinr_db, energy_j, beam_switches_per_slot, useful_beam_share, guard_violation_slots, guard_repairs`.

Already fixed (do not redo): `BamGuard._normalise_power` preserves the proposed total power when ≤ Pmax (so a controller may use < Pmax to save energy) and only scales down above Pmax.

### Required modifications (do these in M1/M2)

| ID | Change |
|---|---|
| A | `Trace` gains `emergency (T,N)` (0/1, default zeros), `forecast (T,N,H) or None`, `events: list` (default `[]`). `load_trace` fills zeros. Keep `copy.deepcopy` working. |
| B | `NTNTwin.obs()` adds `emergency` (N,) and `forecast` ((N,H) or None; row `forecast[t]`). `step()` record adds `emergency_rt_violation` (fraction of emergency cells over RT budget; 0 if none). `summarise` adds `emergency_served_ratio`, `emergency_rt_violation` (NaN if no emergency). |
| C | `BamGuard.due_mask(state, ssb, sib) -> bool (N,)` public wrapper around `_due`. Add `Constraints` dataclass `{power_cap: (N,) or None (W per cell), forced_lit: bool (N,), forbidden_lit: bool (N,), min_power: (N,) or None}` and `repair(..., constraints: Constraints | None = None)`. Order inside repair: forbidden → forced (timing-due ∪ constraints.forced_lit, capped at K, most urgent first) → drop lowest priority to respect K → power floor/total → per-cell caps (excess redistributed to uncapped lit cells, never exceeding their own caps; if nowhere to put it, the excess is **not** transmitted) → min_power overrides (taken from largest uncapped beam). Existing `border_cells`/`border_power_cap_w` config keep working (they become a default `power_cap`). `GuardResult.notes` must name every change. |
| D | `bridge/evaluate.py::run_episode` accepts `constraints_fn(obs)->Constraints|None` and `callbacks` list (called after each step with `(obs, act, res, rec)`), so agents/audit can hook in. |

---------------------------------------------------------------------------------------------------
## 4. CONVENTIONS

- Python 3.11, type hints, `from __future__ import annotations`, numpy/pandas/torch only for core; no global state except seeded RNGs.
- Layout (create what is missing): `traffic/ digital_twin/ bridge/ bam/ satrrm/ agents/ rag/ scenarios/ audit/ dashboard/ scripts/ tests/ docs/ models/ results/ data/{raw,processed}`.
- Config: add sections `predictor:`, `bridge:`, `rag:`, `agents:`, `demo:` to `config.yaml` as needed. Load with one helper `utils/config.py::load_config(path=None)`.
- Logging: `logging` module, INFO to console. No `print` in library code.
- Tests: `pytest`, in `tests/`. Add `Makefile` targets: `setup data predictor bridge kb demo gaps dashboard test all`.
- Dependencies in `requirements.txt` (already listed: numpy pandas pyyaml torch scikit-learn matplotlib xgboost chromadb sentence-transformers rank-bm25 pypdf pdfplumber streamlit plotly pytest). Every optional heavy dependency needs a fallback (§M3 XGBoost→HistGradientBoosting, §M6 sentence-transformers→TF-IDF, ChromaDB→in-memory numpy index).
- Models saved under `models/` with a JSON sidecar (config used, seed, data split hashes, metrics).

---------------------------------------------------------------------------------------------------
## M1 — Hardening + tests (P0)

Implement modifications **A, B, C, D** (§3). Add `tests/`:
- `test_twin.py`: **queue conservation** per cell: `initial + arrived == served + dropped + final` (within 1e-6); unlit cell serves 0; capacity 0 when `los==0`; energy = Σpower·slot_ms/1000.
- `test_guard.py`: K enforced; floor lifted; total preserved ≤ Pmax; total scaled to Pmax if above; timing-due cell forced on at an SSB slot; power cap respected and excess redistributed; `Constraints.forced_lit` honoured; forbidden respected; all-checks PASS after repair for 1000 random proposals.
- `test_channel.py`: SINR monotone in own power; interference lowers SINR; capacity 0 below `sinr_min_db`.

**ACCEPTANCE:** `python -m pytest -q tests` green; `python scripts/run_baselines.py` prints the 4-row table.

---------------------------------------------------------------------------------------------------
## M2 — Scenarios, datasets, splits, progressive event engine (P0)

### M2.1 Generator additions (`traffic/generator.py`)
- Every kind also sets `emergency` (zeros except where specified) and returns `Trace` with `meta` containing kind/seed.
- `event_surge`/`mixed`: ramp 8–15 slots → hold 15–29 → decay 6–11 (already implemented). Add option `emergency_prob=0.5`: with that probability an event cell is flagged emergency for the hold window. (BRIDGE ignores this flag by design; see M7.)

### M2.2 Splits (`traffic/splits.py`, `scripts/make_datasets.py`)
- 5 kinds × 120 episodes (seeds `1000 + 1000*kind_idx + j`). Split **by episode**: 70 % train / 15 % val / 15 % test, deterministic, stratified by kind. Save `data/processed/{train,val,test}.npz` + `data/processed/manifest.json` (episode seeds, kind, split, sha256).
- The **real dataset is an external test set**: never used for training or model selection.
- `--fast`: 20 episodes per kind.
- `tests/test_no_leakage.py`: train/val/test seed sets are disjoint; no real-trace data in train.

### M2.3 Scripted demo scenario `flood_relief` (`scenarios/flood_relief.py`) — the story judges will see
Built on the real pass (geometry, SSB/SIB) with scripted modifications. Parameters live in `config.yaml: demo:` — `event_cell: 13`, `background_hot: [2]`, `emergency_cells: [13, 14]`, `border_cells: [13, 14, 15, 16]`, `border_cap_w: 22.0`, `fade_db: 6.0`. **Border cells are placeholders** — the ECE teammates must confirm which outer-ring cells face a neighbouring country; changing the config must change the scenario.

| Slots | Stage | What happens | Who is told |
|---|---|---|---|
| 0–14 | T0 normal | background hotspot on cell 2; others cold | everyone (telemetry) |
| 15–24 | T1 precursor | demand on cell 13 ramps 2.2 → ~15 Mbps | telemetry shows it (Network agent) |
| ~25 | T2 forecast alert | **system-generated** when forecast ≥ 2× current on any cell | Supervisor, Network |
| 28 | T3 emergency | "flood declared; cells 13,14 are emergency-priority" | **Safety agent only** |
| 30–60 | T3b surge hold | cell 13 ≈ 40 Mbps; cell 14 ≈ 15 Mbps | telemetry |
| 45–60 | T4 rain fade | gain × 10^(−fade_db/10) on cells 13,14 | telemetry (SINR drops, lagged) |
| 50 | T5 policy notice | **simulated** regulator notice: beams on border cells capped at `border_cap_w` W | **Policy agent only** |
| 61–76 | T6 recovery | surge decays; system rebalances | telemetry |
| 77–99 | normal | | |

The T5 conflict is the climax: BRIDGE (unaware of the cap, by design) proposes ≈ 50 W for the surge cell; the Policy agent flags it with citations; Safety agent objects that emergency capacity falls; Supervisor applies the cap (law wins), forces the emergency cell lit every slot at the capped power, **flags the residual capacity shortfall for human review**, and the gap analyzer records "no retrievable emergency exemption for cross-border power limits" as a gap candidate.

### M2.4 Event engine (`scenarios/engine.py`)
```python
@dataclass
class Event: id:str; slot:int; kind:str; audience:list[str]  # subset of {"all","network","policy","safety","supervisor"}
             description:str; payload:dict
class EventFeed:
    def __init__(self, events: list[Event]): ...
    def release(self, t:int) -> list[Event]            # events whose slot == t (each released exactly once)
    def visible(self, agent:str, t:int) -> list[Event] # everything released so far to that agent (or "all")
```
Information asymmetry is enforced here: an agent can only call `visible(its_name, t)`. `tests/test_events.py`: policy-only events never appear for `network`; each event released once; ordered by slot.

**ACCEPTANCE:** `python scripts/make_datasets.py --fast && python -m pytest -q tests`; `python -c "from scenarios.flood_relief import build; t,ev=build(); print(len(ev))"` prints ≥ 6.

---------------------------------------------------------------------------------------------------
## M3 — Traffic predictor (P0)

### Purpose
Forecast per-cell demand for the **next H = 3 slots**, using only observed history, and expose it to BRIDGE.

### Timing contract (critical)
With `obs_lag_slots = 1` the controller at slot `t` has seen demand up to `t−1`. The predictor outputs demand for slots **t, t+1, t+2** (steps +1…+3 beyond the last observed slot). Predictive mode requires `lag ≥ 1` (assert). Demand is exogenous (actions do not change it), so forecasts are **precomputed per trace**: `Predictor.predict_trace(trace) -> (T,N,H)` where `forecast[t]` uses only `rate[: t−lag+1]`. Store in `trace.forecast`.
**Leak test (mandatory):** `tests/test_forecast_leak.py` — corrupt `rate[t−lag+1:]` with random values; `forecast[t]` must not change.

### Inputs (per cell, window W = 12, front-padded with the first observation)
`rate/40`, first difference `Δrate/10`, window mean and std, plus two global features shared by all cells at that step: `sum(rate)/(N*40)` and the fraction of cells with positive slope. **No queues** (they depend on actions and are not available offline). Cell dimension is the batch dimension (cells share weights).

### Models (`traffic/predictor.py`, `traffic/train_predictor.py`, `traffic/evaluate.py`)
1. **Persistence** (repeat last observed value).
2. **GBM baseline**: `xgboost.XGBRegressor` if importable else `sklearn.ensemble.HistGradientBoostingRegressor`; one model per horizon on flattened window features.
3. **GRU** (primary; `--arch lstm` switch): 1 layer, hidden 64 → MLP(64→32→H). **Residual head**: output `δ_h`; prediction = `max(0, last + 40·δ_h)`, so the default behaviour is persistence and the model can only add information.
Loss: Huber on normalised values; **×5 sample weight when |target − last| > 5 Mbps** (ramps are rare; otherwise the model learns persistence). Adam 1e-3, early stop on val loss, ≤ 30 epochs, batch 512. Normalisation constants fit on train only.

### Evaluation (write `results/predictor_metrics.json` and `docs/predictor_results.md`)
Per scenario kind (test split) **and on the real dataset trace**: MAE, RMSE, MAPE (only where target > 1 Mbps), R², for each horizon; **and MAE restricted to jump windows** (|target − last| > 5 Mbps). Rows: persistence, GBM, GRU. Plot predicted vs true for one event-surge test episode (`results/figs/forecast_event.png`).
**Report honestly:** expected outcome is GRU ≈ persistence on `block`, `bursty` and the real trace and clearly better on `event_surge`/`mixed` at jumps. If it is not, say so in the results file.

### API
```python
class Predictor:
    @classmethod
    def load(cls, path="models/traffic_predictor.pt") -> "Predictor"
    def predict_window(self, rate_hist: np.ndarray) -> np.ndarray      # (N,H)
    def predict_trace(self, trace, lag:int) -> np.ndarray              # (T,N,H), leak-safe
```
**ACCEPTANCE:** `python -m traffic.train_predictor --fast && python -m traffic.evaluate --fast`; leak test passes; `models/traffic_predictor.pt` + sidecar exist.

---------------------------------------------------------------------------------------------------
## M4 — BRIDGE: the DRL controller (P0)

**BRIDGE** = *Beam-hopping with Reinforcement-learned, Dirichlet-power and Gumbel-top-K selection Engine*. One policy network outputs, jointly: **which K cells to light** (Gumbel-Top-K / Plackett-Luce), **how to split power** (Dirichlet), and optionally **how much total power to use** (Beta). Trained with PPO after a behaviour-cloning warm start.

> Accuracy note for all docs: Gumbel-Top-K here is a **sampler** with an exact Plackett-Luce log-probability (Kool et al., ICML 2019, "Stochastic Beams and Where to Find Them"). Learning uses the **score-function (policy-gradient)** estimator. Do **not** describe it as "differentiable selection".

### M4.1 State → per-cell features (`bridge/features.py`) — F = 19
Computed from `obs` (all quantities already lagged or exact as in §3). `rate_scale = 40`.

| # | Feature | Definition |
|---|---|---|
| 1 | demand | `rate_obs / 40` |
| 2 | q_rt | `q_rt / buffer_rt_kb` |
| 3 | q_nrt | `q_nrt / buffer_nrt_kb` |
| 4 | rt_age | `min( (q_rt / max(rate_obs·rt_share, 0.05)) / rt_delay_budget_ms, 3 ) / 3` |
| 5 | sinr_est | `clip(10·log10(p_eq·gain_obs·G / noise), −10, 30)/30`, `p_eq = Pmax/K` |
| 6 | los | `los` |
| 7 | elev | `elev / 90` |
| 8 | ssb_age | `min(ssb_age / ssb_max_age, 1.5)` |
| 9 | sib_age | `min(sib_age / sib_max_age, 1.5)` |
| 10 | due | `BamGuard.due_mask` as 0/1 |
| 11 | prev_lit | `prev_lit` |
| 12 | prev_power | `prev_power / Pmax` |
| 13–15 | forecast h0,h1,h2 | `forecast[:, h] / 40` (zeros if `forecast is None` or `--no-forecast`) |
| 16 | forecast_delta | `clip((forecast[:,2] − rate_obs)/40, −1, 1)` |
| 17 | ssb_slot | global flag broadcast to every cell |
| 18 | sib_slot | global flag broadcast |
| 19 | progress | `t / T` |

### M4.2 Network (`bridge/actor.py`) — about 60 k parameters
```
φ_i   = MLP_shared(f_i)              : F→64→64, ReLU          (applied to every cell; permutation-equivariant)
c     = concat( mean_i φ_i , max_i φ_i )                        (128)
h_i   = concat( φ_i , c )                                       (192)
z_i   = Linear(MLP(h_i))   beam logit               (192→64→1)
a_i   = Linear(MLP(h_i))   Dirichlet pre-activation (192→64→1)  α_i = dirichlet_offset + softplus(a_i)   (offset 1.0 → unimodal)
V     = MLP(c)             value                    (128→64→1)
(β_a, β_b) = 1 + softplus(MLP(c))   (128→32→2)      optional "power scale" head, Beta distribution
```
Mask: `z̃_i = z_i − 1e4·(1 − visible_i)` (non-visible cells are never selected unless fewer than K are visible).

### M4.3 Action (`bridge/gumbel_topk.py`, `bridge/dirichlet.py`)
**Beam selection — Gumbel-Top-K / Plackett-Luce**
```
sampling:   G_i = −log(−log U_i), U_i ~ Uniform(0,1) i.i.d.
            keys κ_i = z̃_i + G_i ;  ordered set S = (s_1,…,s_K) = top-K indices of κ in descending order
log-prob:   log π_beam(S) = Σ_{j=1..K} [ z̃_{s_j} − logsumexp_{i ∈ R_j} z̃_i ],   R_1 = all cells, R_{j+1} = R_j \ {s_j}
deterministic (eval/demo): S = argsort(z̃) descending, first K
```
**Power split — Dirichlet** over the K selected cells in the same order:
```
w ~ Dirichlet(α_{s_1},…,α_{s_K})      log π_pow = Dirichlet.log_prob(w)   (clamp w to [1e-4,1], renormalise)
deterministic: w = α_S / Σ α_S
```
**Total power — Beta (optional, `bridge.energy_head: true`)**
```
β ~ Beta(β_a, β_b),   s = s_min + (1 − s_min)·β,   s_min = 0.6 ;   P_total = s · Pmax
deterministic: β = β_a/(β_a+β_b)
```
**Mapping to watts:** `p_{s_j} = p_min + (P_total − K·p_min)·w_j` (so the guard's floor/total never has to change a compliant action).
**Joint log-prob:** `log π = log π_beam + log π_pow (+ log π_Beta)`. Entropy bonus uses a proxy: categorical entropy of `softmax(z̃)` + Dirichlet entropy (+ Beta entropy).
`tests/test_plackett_luce.py`: for N = 5, K = 3, enumerate all 60 ordered triples; probabilities from `log π_beam` **sum to 1** (1e-6); empirical frequencies of 200 k Gumbel-Top-K samples match within 1 %. `tests/test_dirichlet.py`: samples sum to 1; powers sum to `P_total`; every lit beam ≥ `p_min`.

### M4.4 Reward (per slot; weights in `config.yaml: reward`)
```
r_t =  w_throughput · clip(served_kb_total / (arrived_kb_total + 1e-6), 0, 2)
     − w_delay      · min(delay_ms / 100, 5)
     − w_loss       · dropped_kb_total / (arrived_kb_total + 1e-6)
     − w_rt_violation · rt_violation          # fraction of cells over the RT budget (twin rec)
     + w_fairness   · JainEMA                  # Jain index over per-cell served/arrived ratio, EMA α = 0.1
     − w_energy     · P_total / Pmax           # 0 by default; set 0.3 when energy_head is on
     − w_guard_violation · 1[raw proposal failed any guard check]
     − 0.05 · switches / K
```
**Penalise the raw proposal, execute the repaired one.** The guard always repairs before execution, so the environment dynamics use the repaired action, but the guard-violation penalty and the PPO log-prob use the raw action. Otherwise BRIDGE learns to lean on the repair step.

### M4.5 Training (`bridge/train.py`, `bridge/environment.py`)
- `VecBridgeEnv`: runs **B = 32 episodes in lockstep** (one `NTNTwin` + `BamGuard` each); features stacked as `[B,N,F]`; **one batched policy forward per slot**. Forecasts are precomputed (M3). Each PPO iteration draws fresh episodes: kinds weighted `event_surge .30, mixed .25, block .20, bursty .15, normal .10`, new seeds each iteration (online data, no overfitting to a fixed set), observation lag fixed at 1.
- **Stage 1 — behaviour cloning** (`bridge/teacher.py`, `bridge_bc.pt`): teacher `RTAwareForecastTeacher`:
  `score_i = 1.5·f4 + 1.0·(f2+f3) + 1.0·max(f13..f15 − f1, 0)·3 + 0.8·f10`, masked by visibility; light top-K by score; power fractions `softmax(score_S/0.5)`; total power `s=1`. BC loss = `−log π_beam(S_teacher ordered by score) − log π_pow(w_teacher smoothed 0.9·w + 0.1/K)`. 200 episodes, 5 epochs. The teacher is also **reported as a baseline** ("Heuristic-predictive") so the DRL gain over a hand-written rule is visible.
- **Stage 2 — PPO** (`bridge_ppo.pt`): GAE (γ 0.95, λ 0.95), clip 0.2, Adam 3e-4, 4 epochs, minibatch 512, value coef 0.5, entropy coefs 0.01 (beam) / 0.001 (power), grad-clip 0.5, 150 iterations (`--fast`: 5). Normalise advantages. Evaluate on the val set every 10 iterations (deterministic action); keep the best checkpoint. Log CSV + `results/figs/bridge_learning_curve.png`.
- **Ablation** `--no-forecast`: zero features 13–16, train separately → `bridge_ppo_noforecast.pt`.
- **Fallback rule:** if PPO's best val reward is below the BC policy's, ship the BC policy and say so in `docs/experiment_results.md`.
- Hyper-parameters go in `config.yaml: bridge:`.

### M4.6 Policy wrapper
```python
class BridgePolicy(Policy):                    # drop-in for bridge/baselines.Policy
    def __init__(self, ckpt, deterministic=True, use_forecast=True): ...
    def act(self, obs) -> Action               # returns lit, power, priority=z̃ logits, info={"order":..., "w":..., "P_total":..., "log_prob":...}
```

**ACCEPTANCE:** `python -m bridge.train --fast` finishes < 2 min and writes both checkpoints; `pytest tests/test_plackett_luce.py tests/test_dirichlet.py` green; `python -m bridge.evaluate --fast` prints the comparison table (§6).

---------------------------------------------------------------------------------------------------
## M5 — BAM, SatRRM-xApp, telemetry (P0 / P1)

- `bam/generator.py` (P0): `BAM` dataclass `{start_slot, lit[L,N] (0/1), power[L,N] (W), ssb[L], sib[L]}`; `BAM.from_actions(actions)`, `.to_dataframe()`, `.render_ascii()` (rows = slots, columns = cells, power in cells). L = 8 (the SIB period). Used by the dashboard and the audit log.
- `bam/validator.py`: extended in M1 (Constraints). Keep `check`/`repair` names.
- `satrrm/telemetry.py` (P0): `TelemetryReport` dict mimicking an **E2SM-KPM-style** indication (per-cell throughput, PRB/queue load, CQI/SINR, slot id) built from `obs`; JSON-serialisable. `ControlMessage` dict mimicking an **E2SM-RC-style** control request (beam mask, per-beam power). Document in the README that this is an **E2-compatible simulated interface (mapping only), not a real E2 stack**.
- `satrrm/xapp.py` (P0): `SatRRMxApp.on_telemetry(report) -> ControlMessage` runs feature building → forecast lookup → BRIDGE → guard → returns the repaired control message plus the audit stub. `satrrm/controller.py`: applies a `ControlMessage` to the twin.
- `plan_window()` (P2): roll the policy forward L slots on a twin clone using forecast demand to fill a full BAM; execute only the first row (receding horizon).

**ACCEPTANCE:** `python -c "from satrrm.xapp import SatRRMxApp"`; `tests/test_xapp_roundtrip.py`: telemetry → control → twin step gives the same KPIs as calling `BridgePolicy` directly.

---------------------------------------------------------------------------------------------------
## M6 — Knowledge base + RAG (P0)

### M6.1 Document inventory (`rag/knowledge_base/manifest.yaml`)
Team members place **real files** in `rag/knowledge_base/raw/`. Copilot must **not** download, invent or paraphrase documents. Manifest entry:
```yaml
- doc_id: itu_y3172
  title: "ITU-T Y.3172 — Architectural framework for machine learning in future networks including IMT-2020"
  issuer: ITU-T
  jurisdiction: GLOBAL            # GLOBAL | IN | NP | BD | LK | BT | PK | MM | EU | US | ...
  doc_type: standard              # standard | law | policy | strategy | regulation
  year: 2019
  file: raw/itu_y3172.pdf         # if the file is missing the doc is SKIPPED with a warning (never faked)
  priority: P0
  verified_by: ""                 # human initials once opened and checked
```
Seed the manifest with these **candidates** (status unverified; humans confirm each exists, is current and is the right version). Minimum viable set: **Y.3172, 3GPP TR 38.821, India Telecommunications Act 2023, India DPDP Act 2023, EU AI Act, one neighbouring-country telecom act**.

| Group | Candidate documents (verify before use) |
|---|---|
| ITU / global standards | ITU-T Y.3172; Y.3173 (intelligence levels); Y.3174 (data handling for ML); ITU Radio Regulations (extracts: Art. 5 allocations, Art. 22 space services); ITU Constitution (priority of safety-of-life telecoms); Tampere Convention (telecom resources for disaster mitigation); the ITU AI Readiness Framework document referenced in the brief |
| 3GPP / O-RAN | 3GPP TR 38.821 (NR solutions for NTN); TR 38.811 (NTN study); TS 38.213 (SSB/PRACH procedures); O-RAN WG3 Near-RT RIC architecture + E2 interface specs (if accessible) |
| Host (India) | Telecommunications Act 2023; Digital Personal Data Protection Act 2023; Indian Space Policy 2023; national AI governance guidance (MeitY) and NITI Aayog national AI strategy; TRAI/DoT satellite spectrum material |
| Neighbours | telecom act and data-protection / AI policy documents for Bangladesh, Nepal, Sri Lanka, Bhutan, Pakistan — **only those a human actually obtains**; missing ones are recorded as a limitation, never invented |
| Other global examples | EU AI Act (Reg. (EU) 2024/1689); European Electronic Communications Code (emergency communications); NIST AI RMF 1.0; OECD AI Principles |

### M6.2 Ingestion (`rag/ingest.py`, `rag/embeddings.py`, `rag/retriever.py`)
- Extract text per page (`pdfplumber`, fall back `pypdf`; also `.txt/.md/.html/.docx`). Detect headings/section numbers with regexes (`^\d+(\.\d+)*\s+\S`, `^Article \d+`, `^Section \d+`, `^Annex`); keep a section path.
- Chunk ≈ 800 tokens, 150 overlap, **never crossing a document boundary**, each chunk carries `{chunk_id, doc_id, title, jurisdiction, doc_type, section, page_start, page_end, text, sha256}`.
- Embeddings: `sentence-transformers` (`BAAI/bge-small-en-v1.5`, fallback `all-MiniLM-L6-v2`); **fallback to TF-IDF** (scikit-learn) if the model cannot be loaded (no internet). Vector store: ChromaDB persistent in `rag/index/`; fallback: numpy matrix + JSON.
- **Hybrid retrieval**: BM25 (`rank-bm25`) + dense cosine, fused with Reciprocal Rank Fusion (k = 60). Optional metadata filters `jurisdiction`, `doc_type`, `doc_id`.
```python
@dataclass
class Passage: chunk_id:str; doc_id:str; title:str; jurisdiction:str; section:str; page:int; text:str; score:float
def retrieve(query:str, k:int=5, jurisdiction:list[str]|None=None, doc_type:list[str]|None=None) -> list[Passage]
```
- `rag/itu_adapter.py` (P1): if the Sandbox provides **ITU reference code** for extract/structure/ingest, wrap it behind the same `ingest()` output schema and use it in preference to the local ingester. Keep the local ingester as the fallback. (The brief scores use of the ITU reference code.)

### M6.3 Quality evidence
- `rag/coverage_report.py` → `docs/kb_coverage.md`: documents ingested vs skipped, chunks per document, jurisdictions, pages, headings detected.
- `rag/gold_queries.yaml` (humans fill ≥ 15 entries: `query`, `expect_doc_id`, `expect_section_regex`) and `rag/eval_retrieval.py` → recall@5 and MRR in `docs/kb_coverage.md`. Ship a template with 3 clearly marked examples.
- `rag/citations.py`: `verify_quote(quote, chunk_text)` (normalised-whitespace containment, ≤ 25 words) and `verify_citation(cite, index)` — used by every agent output.

**ACCEPTANCE:** `python -m rag.ingest --fast` works with an empty `raw/` (prints "0 documents, nothing to index" and exits 0) and with a tiny sample `.txt`; `tests/test_rag.py` (index two toy docs, retrieve with filters, citation verifier rejects a quote that is not in the chunk).

---------------------------------------------------------------------------------------------------
## M7 — Agents, tools, progressive scenario, audit (P0)

### M7.1 LLM layer (`agents/llm.py`)
- `AGENT_MODE=deterministic` (default) or `llm`. LLM client reads `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` (OpenAI-compatible chat API); no keys in the repo.
- **The LLM never makes a control decision and never overrides the guard.** Deterministic code decides. The LLM only (a) writes the ≤ 3-sentence rationale for each trace step, (b) writes the final scenario summary, (c) drafts gap narratives. Every LLM output is JSON validated against a schema; any failure → template text. A run in `deterministic` mode must produce a complete audit log with template rationales.

### M7.2 Tools (`agents/tools.py`)
`ToolRegistry` with typed functions; every call is auto-recorded as a `TraceStep` (name, inputs, output summary, duration):
`get_network_state(obs)`, `predict_traffic()`, `run_bridge_policy(obs)`, `generate_bam(actions)`, `validate_bam(action)` (=`guard.check`), `repair_bam(action, constraints)`, `retrieve_policy(query, filters)`, `check_policy_rules(action, context)`, `run_digital_twin_step(action)`, `calculate_kpis()`, `execute_bam(action)`, `write_audit_log(record)`. Agents may only act through the registry.

### M7.3 Agents (`agents/*.py`) — different information, different mandates
| Agent | Sees | Mandate | Output |
|---|---|---|---|
| Network (`network_agent.py`) | lagged telemetry, forecast, `EventFeed.visible("network")` | maximise KPIs; **uses BRIDGE as a tool** | proposed action + rationale (features that drove it: forecast growth, RT age, due cells) |
| Policy (`policy_agent.py`) | proposed action + `visible("policy")` + KB | legal/standards compliance | per-rule verdicts (§M7.4) with citations; `constraints` to apply |
| Safety (`safety_agent.py`) | KPIs, queues, emergency flags from `visible("safety")` | protect priority (RT/emergency) traffic, prevent starvation, avoid power concentration | findings + `required_changes` (forced_lit for emergency cells with RT backlog, min power); checks: RT violation, starvation (cell dark > `starve_slots`), single-beam power share > 0.6, Jain < 0.8 |
| Supervisor (`supervisor.py`) | everything above | orchestrate, resolve conflicts, approve, audit | final action + `AuditRecord` |

### M7.4 Policy rules (`agents/policy_rules.yaml`) — auditable, human-editable
```yaml
- id: R1_border_power_cap
  title: "Power limit on beams illuminating border cells (transboundary coordination)"
  trigger: "border_cells_lit"                     # named predicate implemented in policy_agent.py
  evidence_queries:
    - "coordination of satellite beam power with neighbouring administration"
    - "power flux density limit transboundary interference"
  check: border_power_cap
  params: {cap_w: "event:policy_notice.cap_w", cells: "demo.border_cells"}
  parameter_source: scenario_notice               # the NUMBER comes from the simulated notice, not from the KB
  on_violation: clip_to_cap
- id: R2_emergency_priority
  title: "Emergency / safety-of-life traffic must keep service"
  trigger: "emergency_declared"
  evidence_queries: ["priority of emergency telecommunications safety of life", "public emergency telecommunication services priority"]
  check: emergency_served
  on_violation: force_lit
- id: R3_human_oversight_and_logging
  title: "Automated network decisions are logged and reviewable by a human"
  trigger: "always"
  evidence_queries: ["human oversight of automated decision making record keeping logging", "transparency of AI system decisions"]
  check: audit_complete
  on_violation: escalate_human
- id: R4_ntn_timing
  title: "Initial-access signalling (SSB/SIB) is protected"
  trigger: "always"
  evidence_queries: ["SSB periodicity initial access non-terrestrial network", "system information broadcast NTN"]
  check: timing_guard
  parameter_source: config_assumption             # 40/80-slot limits are OUR assumption; the document supports the concept only
  on_violation: repair_guard
```
Policy agent algorithm per triggered rule: (1) `retrieve()` for each query (k = 3); (2) run the deterministic `check`; (3) emit a verdict `{rule_id, status: PASS|FAIL|UNVERIFIED, evidence_status: FOUND|NONE_FOUND, passages:[{doc_id, section, page, quote≤25 words, score}], parameter_source, constraint}`. If `NONE_FOUND` the rule is **still enforced precautionarily**, the verdict is `UNVERIFIED`, and the omission is passed to the gap analyzer. Every quoted string is checked with `verify_quote`; a failing quote is dropped, not shown.

### M7.5 Supervisor loop (`agents/supervisor.py`)
```
for t in range(T):
    new_events = feed.release(t)
    obs        = twin.obs()
    proposal   = network.propose(obs)                      # BRIDGE
    checks     = guard.check(proposal)
    trigger    = forecast_surge(obs) or new_events or any(FAIL in checks) or kpi_breach(prev_rec) or policy_predicate_true
    if trigger:                                            # DELIBERATION (full multi-agent path)
        policy_rep = policy.review(proposal, ctx)
        safety_rep = safety.review(proposal, obs, ctx)
        constraints = merge(policy_rep.constraints, safety_rep.required_changes)   # priority below
        decision    = supervisor.resolve(...)
    else:                                                  # FAST PATH (every slot, compact audit record)
        constraints = None
    final = guard.repair(proposal, constraints)
    rec   = twin.step(final)
    audit.write(AuditRecord(...))
```
**Conflict priority:** (1) hard technical guard · (2) mandatory legal/policy · (3) safety/emergency priority · (4) network optimisation. If (2) and (3) conflict and no retrieved passage authorises an exception, the cap holds, the supervisor applies the best compliant mitigation (emergency cell forced lit every slot at the capped power), sets `human_review: true` with the quantified shortfall (Mbps), and writes it to `results/human_review_queue.jsonl`.

### M7.6 Audit completeness
Each executed slot has one `AuditRecord` (fast-path records are compact). Deliberations include a `trace` list with one step per tool call/agent verdict, `policy_findings`, `safety_findings`, `repairs`, `human_review`, `outcome` KPIs. **Chain-of-thought tracing in this system = a system-generated reasoning trace**: each step records inputs, tool, output, rule applied, sources cited and a short factual rationale. (Do not store model "private reasoning"; store evidence and rationale.)
`tests/test_audit.py`: every executed slot has a record; every policy verdict has ≥ 1 passage or `evidence_status == NONE_FOUND`; every citation passes `verify_citation`; JSONL round-trips; deliberation records have ≥ 4 trace steps.

**ACCEPTANCE:** `python scripts/run_demo.py --fast` runs the whole `flood_relief` scenario in deterministic mode, writes `results/audit/demo.jsonl`, `results/demo_run.json`, `results/human_review_queue.jsonl`; `pytest tests/test_audit.py tests/test_events.py` green.

---------------------------------------------------------------------------------------------------
## M8 — Policy / standards gap analysis (P0 — it is a scored criterion)

The brief wants **domain-specific** gaps (not country recommendations), with **relevant global policy examples**, searching the **host country and neighbouring countries**. Gap statements are therefore about the domain ("no instrument specifies X for AI-controlled NTN beam management"); countries appear as evidence and examples only.

`agents/gap_analyzer.py` + `scripts/run_gaps.py` → `results/gaps.json`, `docs/gap_analysis.md`.

**Topics** (seed list; the verdict for each comes from retrieval evidence, not from this list):
1. Emergency/priority access on NTN spectrum and beams
2. Cross-border beam spill-over and transboundary power coordination
3. Human oversight and accountability for AI-controlled radio resource management
4. Audit logging / transparency duties for automated network decisions
5. Data flows through satellite gateways (personal data, localisation)
6. Standardised interface/testing for AI-driven NTN beam hopping (3GPP / O-RAN)
7. Energy/efficiency obligations for satellite payload power
8. AI-for-social-inclusion / rural coverage obligations that satellite AI could serve

**Method per topic:** run ≥ 3 queries; retrieve top-5 with jurisdiction filters (a) host, (b) each neighbour present in the KB, (c) global/other. Compute `coverage = max fused score`, normalised per index. Classify per jurisdiction: `ADDRESSED` (≥ τ_hi), `PARTIAL` (τ_lo–τ_hi), `UNADDRESSED` (< τ_lo or no document), thresholds in `config.yaml: rag`. A gap exists when host or neighbours are `UNADDRESSED/PARTIAL` while a global example is `ADDRESSED`; also add rule-triggered gaps from the demo (`UNVERIFIED` verdicts, human-review escalations).
Record schema (Appendix A.3): `id, title, domain, statement, evidence[passages with citations], absence_evidence[queries run, jurisdictions, max scores], global_example{doc_id, section, page, quote}, regional_coverage{IN:…, NP:…}, severity, recommendation (domain-level), human_verified:false`.
An LLM (optional) may draft the `statement`/`recommendation` from the retrieved passages only; every sentence that cites must pass `verify_citation`. **All gaps ship with `human_verified: false`** and the report header must say "machine-generated candidates; verify each citation against the source document."
Also produce the **regional coverage heat-table** (topics × jurisdictions) as a Markdown table and a plotly/matplotlib figure `results/figs/gap_heatmap.png`.

**ACCEPTANCE:** `python scripts/run_gaps.py --fast` works with an empty KB (outputs a report saying "no documents indexed; no gaps can be asserted") and with a toy KB; `tests/test_gaps.py`: a topic with no evidence is never reported as ADDRESSED; no gap is emitted without either evidence or absence_evidence.

---------------------------------------------------------------------------------------------------
## M9 — Dashboard (P1) — `dashboard/app.py` (Streamlit)

Reads `results/` (replay mode: robust on stage, no live compute needed) with a "re-run scenario" button (P2). Panels: (1) **Scenario replay** — slot slider, event markers T0–T6, per-cell demand/forecast bars, beams lit (●/○), power per beam, SINR, queues; (2) **KPI comparison** — Static / Reactive / Heuristic-predictive / BRIDGE-no-forecast / BRIDGE (+ full OrbitFlow agents) bar charts with CIs; (3) **Audit explorer** — table of records, expandable trace steps, citations with doc/section/page; (4) **Human-review queue**; (5) **Policy & gaps** — gap table + heat-table; (6) **KB coverage** and retrieval metrics; (7) **Standards mapping** — Y.3172 pipeline figure. Must start with an empty `results/` and show friendly "run `make demo` first" messages. Colour-blind-safe palette, units on every axis.
**ACCEPTANCE:** `streamlit run dashboard/app.py --server.headless true` starts without exceptions on empty and on populated `results/`.

---------------------------------------------------------------------------------------------------
## M10 — Documentation, packaging, demo script (P0 docs · P1 Docker)

Generate (templates + auto-filled numbers from `results/`):
- `README.md` — what/why, quick start (`make setup && make all`), architecture figure (ASCII or PNG), results table, **limitations**, licence.
- `docs/architecture.md` — dataflow, agent roles, information asymmetry, guardrail order, E2/O-RAN mapping (**mapping only, simulated interface**).
- `docs/y3172_mapping.md` — table below. **Verify node names against the Recommendation text before publishing** (written from memory of the ML pipeline: SRC, C, PP, M, P, D, SINK, MLFO, ML sandbox, ML underlay).

| Y.3172 concept | OrbitFlow component |
|---|---|
| Source (SRC) | `NTNTwin` telemetry / simulated E2 KPM reports |
| Collector (C) | `satrrm/telemetry.py` |
| Pre-processor (PP) | `bridge/features.py`, predictor window builder |
| Model (M) | `traffic/predictor.py` GRU + `bridge/actor.py` BRIDGE |
| Policy (P) | `bam/validator.py` guardrails + `agents/policy_rules.yaml` (applied to model output before execution) |
| Distributor (D) | `satrrm/xapp.py` control message |
| Sink (SINK) | twin / O-DU scheduler (`satrrm/controller.py`) |
| ML function orchestrator (MLFO) | Supervisor agent |
| ML sandbox | digital twin + `VecBridgeEnv` (training/validation before deployment) |
| ML underlay network | the simulated NTN |

- `docs/ai_readiness_mapping.md` — one row per perspective in the brief, each with *what OrbitFlow does* and *file/evidence*: (1) open data & open-source management (open repo, data card, synthetic-data labelling, licence) · (2) generative-AI content ecosystem (LLM only drafts text; schema-validated; citation-verified) · (3) contextualisation & regional development (host + neighbouring-region gap search) · (4) AI integration in domains & cross-domain (network + emergency services + regulator agents) · (5) human interaction & supervision (human-review queue, repair/veto, audit) · (6) AI policy & implementation-opportunity identification (gap analyzer) · (7) AI for social inclusion (rural/disaster coverage use case, fairness metric) · (8) digital infrastructure & energy (energy head, `energy_j` KPI, CPU-only 60 k-parameter actor).
- `docs/model_card_predictor.md`, `docs/model_card_bridge.md`, `docs/data_card.md` — intended use, training data (**synthetic, calibrated to the supplied trace**), metrics, failure modes (abrupt hotspot jumps are unforecastable), limitations.
- `docs/experiment_results.md` (auto) — all tables/figures from §6, **including losses**.
- `docs/ASSUMPTIONS.md`, `docs/LIMITATIONS.md` — list: link budget is calibrated not measured; timing-guard limits are assumed; border cells and the regulator notice are simulated; Sionna/OpenNTN not used live (Sionna-compatible `LinkModel` interface); E2 is simulated; PRACH constant in the supplied data.
- `docs/demo_script.md` — 3-minute narration synchronised to the stages T0–T6 and the dashboard.
- `docs/pitch_outline.md` (P1) — 8-slide outline mapped to the five scoring criteria.
- `LICENSE` (Apache-2.0), `Dockerfile` (python:3.11-slim, CPU, `pip install -r requirements.txt`, default CMD `make demo`) (P1).
- **P3 only if everything else passes:** `bridge/export_onnx.py` exporting the deterministic network heads (logits, Dirichlet concentrations, Beta params) to ONNX with sampling kept outside the graph; and an `onnxruntime` parity test.

**ACCEPTANCE:** `make all` completes from a clean checkout (empty KB allowed) in ≤ 20 min and populates `results/` and `docs/`.

---------------------------------------------------------------------------------------------------
## 6. EVALUATION PROTOCOL (`bridge/evaluate.py`, `scripts/run_eval.py`)

- **Policies:** Static round-robin · Reactive (lag 1) · Reactive-oracle (lag 0; reference, not deployable) · Logged rule-based (real trace only; non-causal reference) · **Heuristic-predictive** (BC teacher) · **BRIDGE-no-forecast** · **BRIDGE (BC)** · **BRIDGE (PPO)** · **OrbitFlow full** (BRIDGE + agents + policy; only on `flood_relief`).
- **Sets:** test split of each kind (30 episodes each, seeds 9000+); the **real trace**; the scripted `flood_relief`.
- **KPIs:** throughput, served ratio, packet loss, mean/p95 delay, RT delay-budget violation, emergency RT violation, Jain fairness, mean SINR, energy, beam switches, guard repairs, plus **inference latency** (predictor ms, BRIDGE ms, total ms per slot, measured with `time.perf_counter`).
- **Statistics:** mean ± 95 % bootstrap CI over episodes; paired sign-test vs Reactive per KPI. State wins **and losses** in `docs/experiment_results.md`.
- **Expected honest outcome (verify, do not force):** on the real trace and `block`/`bursty`, prediction adds little and BRIDGE's gain comes from RT-aware cold-cell scheduling; on `event_surge`/`mixed`, forecast-aware BRIDGE beats BRIDGE-no-forecast and Reactive on delay/loss at the surge onset. If BRIDGE loses somewhere, report it.
- Figures: KPI bars with CI; per-slot time series for `flood_relief` (demand, forecast, beams, power, queue of the event cell, RT violation) with event markers; learning curve.

---------------------------------------------------------------------------------------------------
## 7. BUILD ORDER AND TIME BOX (suggested)

| Milestone | Target time | Done when |
|---|---|---|
| M1 hardening + tests | 0:30 | tests green |
| M2 data + scenario + events | 0:45 | datasets + `flood_relief` build |
| M3 predictor | 0:45 | metrics + leak test |
| M4 BRIDGE | 1:45 | BC + PPO checkpoints, PL tests, eval table |
| M5 BAM + xApp | 0:30 | round-trip test |
| M6 KB + RAG (parallel: humans collect documents) | 1:00 | coverage report |
| M7 agents + audit | 1:30 | demo run + audit tests |
| M8 gaps | 0:45 | gap report |
| M9 dashboard | 0:45 | app starts |
| M10 docs + packaging | 0:45 | `make all` |
If time runs short, cut in this order: P3 → P2 → Dockerfile → dashboard polish. **Never cut:** guard, audit, KB provenance, honest results.

---------------------------------------------------------------------------------------------------
## 8. HONESTY AND SAFETY RULES (non-negotiable)

1. **No invented sources.** Every citation must resolve to an ingested chunk (`verify_citation`). If a document is not in `raw/`, it is not in the KB and no output may claim it is. Never write article/section numbers from memory into outputs.
2. **Label synthetic data and simulated components** everywhere they appear (README, dashboard footer, audit records `source`): synthetic traffic, calibrated link budget, simulated E2, simulated regulator notice, placeholder border cells.
3. **Report negative results.** If prediction does not help on a scenario, the results table says so.
4. **The LLM cannot override technical or policy guardrails** and cannot change numbers; it only writes text that is schema- and citation-checked.
5. **Evaluation hygiene:** no training on the real trace; no model selection on the test split; forecasts use only history (leak test).
6. **Do not describe Gumbel-Top-K as differentiable selection** (§M4); do not claim "Sionna" or "OpenNTN" was used unless it actually was.
7. **Gap analysis = candidates.** `human_verified: false` until a person confirms each against the source.
8. No secrets in the repo; read keys from environment variables.

---------------------------------------------------------------------------------------------------
## 9. DEFINITION OF DONE

- [ ] `make all` green from clean checkout; `pytest -q` green
- [ ] Leak test, Plackett-Luce test, queue-conservation test, audit-completeness test pass
- [ ] `results/` contains: KPI tables (real trace, each kind, flood_relief), figures, `demo_run.json`, `audit/demo.jsonl`, `gaps.json`
- [ ] Dashboard replays `flood_relief` with events, audit trace, KPI comparison, gaps
- [ ] `docs/` complete (README, architecture, Y.3172 + AI-readiness mappings, model cards, results, gaps, assumptions, limitations, demo script)
- [ ] No claim anywhere that is contradicted by `results/`

---------------------------------------------------------------------------------------------------
## APPENDIX A — SCHEMAS

### A.1 Audit record (one per executed slot; deliberation records include `trace`)
```json
{
  "timestamp": "2026-10-10T11:42:03.120+00:00",
  "scenario": "flood_relief", "slot": 52, "model": "BRIDGE-ppo-v1",
  "state_summary": {"observed_demand_mbps": {"13": 39.8}, "forecast_demand_mbps": {"13": 41.2},
                    "rt_backlog_kb": {"13": 212.0}, "sinr_db": {"13": 8.4}, "emergency_cells": [13, 14]},
  "proposed": {"beams": [13, 2, 14, 7], "power_w": {"13": 49.7, "2": 20.1, "14": 18.0, "7": 12.2}, "p_total_w": 100.0},
  "constraints": {"beam_count": {"status": "PASS"}, "power_budget": {"status": "PASS"},
                  "timing_guard": {"status": "PASS"}, "policy_border": {"status": "FAIL", "detail": "cell 13 49.7 W > 22 W cap"}},
  "policy_findings": [{"rule_id": "R1_border_power_cap", "status": "FAIL", "evidence_status": "FOUND",
                       "parameter_source": "scenario_notice",
                       "passages": [{"doc_id": "…", "section": "…", "page": 12, "quote": "…", "score": 0.71}]}],
  "safety_findings": [{"check": "emergency_service", "status": "WARN", "detail": "cap reduces cell 13 capacity by ~9 Mbps"}],
  "final": {"beams": [13, 2, 14, 7], "power_w": {"13": 22.0, "2": 31.0, "14": 22.0, "7": 25.0}, "p_total_w": 100.0},
  "repairs": ["clipped border cells [13, 14] to 22 W (policy cap)"],
  "decision": "REPAIRED", "execution_status": "EXECUTED", "human_review": true,
  "outcome": {"throughput_mbps": 171.2, "delay_ms": 24.1, "packet_loss": 0.0, "rt_violation": 0.05},
  "trace": [{"agent": "network", "action": "run_bridge_policy", "inputs": {}, "output": {}, "rationale": "…", "citations": []}]
}
```
### A.2 Event (see M2.4) · Passage (see M6.2) · Policy verdict (see M7.4)
### A.3 Gap record
```json
{"id": "GAP-02", "title": "No documented limit linking AI-driven beam power to transboundary coordination", "domain": "NTN radio resource management",
 "statement": "…", "evidence": [{"doc_id": "…", "section": "…", "page": 0, "quote": "…"}],
 "absence_evidence": {"queries": ["…"], "jurisdictions_searched": ["IN", "NP", "BD"], "max_score_by_jurisdiction": {"IN": 0.31, "NP": 0.12}},
 "global_example": {"doc_id": "…", "section": "…", "page": 0, "quote": "…"},
 "regional_coverage": {"IN": "PARTIAL", "NP": "UNADDRESSED", "BD": "UNADDRESSED", "GLOBAL": "ADDRESSED"},
 "severity": "medium", "recommendation": "…", "human_verified": false}
```

## APPENDIX B — LLM PROMPT TEMPLATE (rationale writer; `agents/prompts/rationale.md`)
```
SYSTEM: You write short, factual audit rationales for a satellite beam-hopping controller.
Use ONLY the JSON facts provided. Do not add facts, numbers, laws or section numbers that are not in the JSON.
If the facts include passages, you may reference them only by chunk_id.
Output JSON: {"rationale": "<= 3 sentences", "cited_chunk_ids": ["…"]}
USER: <JSON with step name, inputs, output, rule verdict, passages>
```
A reply that cites a chunk_id not present in the input, or exceeds 3 sentences, is discarded and replaced by the template rationale.
