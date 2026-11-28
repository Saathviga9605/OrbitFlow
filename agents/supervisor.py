"""Multi-agent control layer. Deterministic: no agent here uses an LLM, and none can bypass the guard.

Each agent sees only what EventFeed.visible() releases to it:
  Network     telemetry + forecast, proposes with BRIDGE
  Policy      proposal + policy notices + knowledge base; returns verdicts with verified citations
  Safety      KPIs + emergency declarations; returns required changes
  Supervisor  everything; resolves conflicts in the order guard > law > safety > optimisation
"""
from __future__ import annotations

import os
import time

import numpy as np
import yaml

from agents.registry import build_fallback, load_registry
from audit.schemas import AuditRecord, TraceStep
from bam.validator import BamGuard, Constraints
from bridge.baselines import Action
from digital_twin.environment import NTNTwin, summarise
from rag.retriever import KnowledgeBase, answer

RULES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "policy_rules.yaml")
RATE_REF = 181.0    # hotspot level of the dataset (traffic/generator.py HOT); rationale wording only


class NetworkAgent:
    def __init__(self, policy, feed):
        self.policy, self.feed = policy, feed

    def propose(self, obs):
        return self.policy.act(obs)

    def rationale(self, obs, act) -> str:
        lit = np.where(act.lit)[0]
        parts = []
        if obs.get("forecast") is not None:
            growth = obs["forecast"][:, 2] - obs["rate_obs"]
            c = int(np.argmax(growth))
            if growth[c] > 0.075 * RATE_REF:
                parts.append(f"forecast sees cell {c} rising {growth[c]:.1f} Mbps within 3 slots")
        rt = obs["q_rt"]
        worst = int(np.argmax(rt))
        parts.append(f"largest RT backlog is cell {worst} ({rt[worst]:.0f} kb)")
        return f"Lights {lit.tolist()}: " + "; ".join(parts) + "."


class PolicyAgent:
    def __init__(self, feed, kb: KnowledgeBase):
        self.feed, self.kb = feed, kb
        with open(RULES, encoding="utf8") as f:
            self.rules = {r["id"]: r for r in yaml.safe_load(f)}
        self._cache: dict = {}
        self.pfd_cap = None
        for rid in self.rules:                       # evidence is precomputed so retrieval never runs in the slot's critical path
            self.evidence(rid)

    def evidence(self, rule_id: str) -> tuple[str, list[dict]]:
        if rule_id not in self._cache:
            r = self.rules[rule_id]
            res = answer(self.kb, r["query"], r.get("must"), doc_ids=set(r["doc_ids"]) if r.get("doc_ids") else None)
            self._cache[rule_id] = ("FOUND" if res.supported else "NONE_FOUND", res.quotes)
        return self._cache[rule_id]

    def active_cap(self, t):
        for e in reversed(self.feed.visible("policy", t)):
            if e.kind == "policy":
                return e.payload
        return None

    def review(self, act, t, n):
        verdicts, cap_arr = [], None
        cap = self.active_cap(t)
        if self.pfd_cap is not None:
            cap_arr = self.pfd_cap[t].copy()
            over = np.where(act.lit & (act.power > cap_arr + 1e-9))[0].tolist()
            ev, pas = self.evidence("R8_pfd_mask")
            verdicts.append({"rule_id": "R8_pfd_mask", "status": "FAIL" if over else "PASS", "evidence_status": ev, "passages": pas, "parameter_source": "sf358_indicative",
                             "detail": f"cells {over} over the flux-density power cap" if over else "within the flux-density power cap"})
        if cap:
            cap_arr = np.full(n, np.inf) if cap_arr is None else cap_arr
            cap_arr[cap["cells"]] = np.minimum(cap_arr[cap["cells"]], cap["cap_w"])
            over = [int(c) for c in cap["cells"] if act.lit[c] and act.power[c] > cap["cap_w"] + 1e-9]
            ev, pas = self.evidence("R1_border_power_cap")
            verdicts.append({"rule_id": "R1_border_power_cap", "status": "FAIL" if over else "PASS", "evidence_status": ev,
                             "passages": pas, "parameter_source": "hypothetical_constraint",
                             "detail": f"cells {over} exceed {cap['cap_w']:.0f} W" if over else f"within {cap['cap_w']:.0f} W cap"})
        return verdicts, cap_arr


class SafetyAgent:
    def __init__(self, feed, cfg):
        self.feed, self.a, self.e = feed, cfg["agents"], cfg["emergency"]
        self.rt_share, self.budget = cfg["queues"]["rt_share"], cfg["queues"]["rt_delay_budget_ms"]
        self.dark = None

    def emergency_cells(self, t):
        cells: list = []
        if not any(e.id == "recovery_start" for e in self.feed.visible("safety", t)):
            for e in self.feed.visible("safety", t):
                if e.kind == "emergency":
                    cells += e.payload["cells"]
        return sorted(set(cells))

    def recovering_cells(self, t):
        """Cells stepping down after the emergency: priority fades instead of ending in one slot."""
        ended = [e for e in self.feed.visible("safety", t) if e.id == "recovery_start"]
        if self.e["release"] != "taper" or not ended or t - ended[0].slot >= self.e["taper_max_slots"]:
            return []
        return sorted({c for e in self.feed.visible("safety", t) if e.kind == "emergency" for c in e.payload["cells"]})

    def _aged(self, obs, cells):
        """Cells whose real-time backlog has used up `age_trigger` of the delay budget (from lagged telemetry)."""
        age = obs["q_rt"] / np.maximum(obs["rate_obs"] * self.rt_share, 0.05)
        return [c for c in cells if age[c] >= self.e["age_trigger"] * self.budget]

    def review(self, act, obs, t, n):
        findings = []
        forced = np.zeros(n, bool)
        em = self.emergency_cells(t)
        if em:
            need = em if self.e["mode"] == "always" else self._aged(obs, em)
            forced[need] = True
            miss = [c for c in em if not act.lit[c]]
            bad = [c for c in need if not act.lit[c]]
            findings.append({"check": "emergency_service", "status": "WARN" if bad else "PASS",
                             "detail": f"proposal leaves emergency cells {bad} dark while they need service" if bad
                             else f"emergency cells {em} protected" + (f" (cells {miss} can wait this slot)" if miss else "")})
        rec = self.recovering_cells(t)
        if rec:
            need = self._aged(obs, rec)
            forced[need] = True
            if need:
                findings.append({"check": "recovery_transition", "status": "WARN" if any(not act.lit[c] for c in need) else "PASS",
                                 "detail": f"draining backlog on recovering cells {need}"})
        share = float(act.power.max() / max(act.power.sum(), 1e-9))
        if share > self.a["max_beam_share"]:
            findings.append({"check": "power_concentration", "status": "WARN", "detail": f"one beam holds {share:.0%} of power"})
        if self.dark is not None and (self.dark >= self.a["starve_slots"]).any():
            findings.append({"check": "starvation", "status": "WARN", "detail": f"cells {np.where(self.dark >= self.a['starve_slots'])[0].tolist()} dark too long"})
        return findings, forced

    def observe(self, lit):
        self.dark = np.where(lit, 0, (self.dark if self.dark is not None else np.zeros(len(lit))) + 1)


def _action(lit, power):
    return {"beams": np.where(lit)[0].tolist(), "power_w": {int(c): round(float(power[c]), 2) for c in np.where(lit)[0]},
            "p_total_w": round(float(power.sum()), 2)}


class Faults:
    """Injected failures for resilience scenarios: {agent: spec or [spec, ...]}, spec = {"mode": ..., "slots": [start, end)}.

    network: exception | malformed | timeout     policy, safety: exception
    telemetry: nan | negative | stale, with optional "cells" (stale freezes values and ages the report)
    """
    def __init__(self, spec: dict | None):
        self.spec = {k: (v if isinstance(v, list) else [v]) for k, v in (spec or {}).items()}
        self._frozen: dict = {}

    def active(self, agent: str, t: int) -> list:
        return [f for f in self.spec.get(agent, []) if f["slots"][0] <= t < f["slots"][1]]

    def mode(self, agent: str, t: int):
        a = self.active(agent, t)
        return a[0]["mode"] if a else None

    def telemetry(self, obs: dict, t: int) -> dict:
        specs = self.active("telemetry", t)
        if not specs:
            return obs
        obs = dict(obs)
        rate = np.asarray(obs["rate_obs"], float).copy()
        age = np.ones(len(rate))                     # normal reports are one slot old (telemetry lag)
        for f in specs:
            cells = np.asarray(f.get("cells", range(len(rate))), int)
            if f["mode"] == "nan":
                rate[cells] = np.nan
            elif f["mode"] == "negative":
                rate[cells] = -1.0
            elif f["mode"] == "stale":
                key = id(f)
                if key not in self._frozen:
                    self._frozen[key] = rate.copy()
                age[cells] = t - f["slots"][0] + 2
                rate[cells] = self._frozen[key][cells]
            else:
                raise ValueError(f"unknown telemetry fault {f['mode']}")
        if (age > 1).any():
            obs["telemetry_age_slots"] = age
        obs["rate_obs"] = rate
        return obs


class Supervisor:
    MAX_REPORT_AGE = 3          # slots; an older telemetry report is stale

    def __init__(self, cfg, policy, feed, kb: KnowledgeBase, agents_on: bool = True, model: str = "BRIDGE-ppo",
                 profile: dict | None = None, faults: dict | None = None, registry: list | None = None):
        if profile is not None:
            from policy.engine import runtime_config
            cfg = runtime_config(profile, cfg)
        self.cfg, self.feed, self.kb, self.agents_on, self.model = cfg, feed, kb, agents_on, model
        self.profile = profile
        self.network, self.policy_agent = NetworkAgent(policy, feed), PolicyAgent(feed, kb)
        self.safety = SafetyAgent(feed, cfg)
        self.guard = BamGuard(cfg)
        self.reg = {e["id"]: e for e in (registry if registry is not None else load_registry())}
        self.policy_on = agents_on and self.reg["policy"]["enabled"]
        self.safety_on = agents_on and self.reg["safety"]["enabled"]
        self.fallback_name = self.reg["network"]["fallback"]
        self.fallback = build_fallback(cfg, self.fallback_name)
        self.faults = Faults(faults)
        rs = (profile or {}).get("resilience", {})
        ho = (profile or {}).get("human_oversight", {})
        oc = (profile or {}).get("operating_constraints", {})
        self.exemption = oc.get("emergency_exemption", "human_approval")
        self.sustained_limit = int(ho.get("sustained_shortfall_slots", 5))
        self.escalate_failure = bool(ho.get("escalate_on_agent_failure", True))
        self.escalate_data = bool(ho.get("escalate_on_data_degradation", True))
        cap = oc.get("border_power_cap", {})
        self.fail_closed_cells = [int(c) for c in cap.get("cells", cfg["demo"]["border_cells"])]
        self.fail_closed_cap = float(rs.get("fail_closed_cap_w", cfg["demo"]["border_cap_w"]))
        self.budget_ms = float(rs.get("decision_budget_ms", cfg["scenario"]["slot_ms"]))
        self.max_bad_share = float(rs.get("max_bad_telemetry_share", 0.25))
        self.drift_mbps = float(rs.get("state_drift_mbps", 45.0))

    # ------------------------------------------------------------ coordination helpers
    def _validate_obs(self, obs, t):
        """Telemetry validator: invalid or stale cells get their last good value and lose their forecast."""
        rate = np.asarray(obs["rate_obs"], float)
        bad = ~np.isfinite(rate) | (rate < 0)
        age = obs.get("telemetry_age_slots")
        stale = (np.asarray(age) > self.MAX_REPORT_AGE) & ~bad if age is not None else np.zeros(len(rate), bool)
        mask = bad | stale
        if self._last_good is None:
            self._last_good = np.where(bad, 0.0, rate)
        if not mask.any():
            self._last_good = rate.copy()
            return obs, None
        obs = dict(obs)
        imputed = np.where(mask, self._last_good, rate)
        self._last_good = imputed.copy()
        obs["rate_obs"] = imputed
        share = float(mask.mean())
        conservative = share > self.max_bad_share
        if obs.get("forecast") is not None:
            fc = obs["forecast"].copy()
            fc[mask] = imputed[mask, None]
            if conservative:                        # too much is unknown: the forecast is not trusted anywhere
                fc = np.repeat(imputed[:, None], fc.shape[1], axis=1)
            obs["forecast"] = fc
        return obs, {"slot": t, "invalid_cells": np.where(bad)[0].tolist(), "stale_cells": np.where(stale)[0].tolist(),
                     "bad_share": round(share, 3), "conservative": conservative}

    @staticmethod
    def _check_action(act, n):
        if not isinstance(act, Action):
            raise ValueError("proposal is not an Action")
        for name in ("lit", "power", "priority"):
            v = np.asarray(getattr(act, name))
            if v.shape != (n,):
                raise ValueError(f"proposal.{name} has shape {v.shape}, expected ({n},)")
        if not np.isfinite(np.asarray(act.power, float)).all() or (np.asarray(act.power) < 0).any():
            raise ValueError("proposal power is non-finite or negative")
        if not np.isfinite(np.asarray(act.priority, float)).all():
            raise ValueError("proposal priority is non-finite")

    def _propose(self, obs, t, n):
        h = self.health["network"]
        h["calls"] += 1
        mode = self.faults.mode("network", t)
        try:
            if mode == "exception":
                raise RuntimeError("injected fault: Network agent raised an exception")
            if mode == "timeout":
                raise TimeoutError(f"injected fault: no proposal within the {self.budget_ms:g} ms decision budget")
            t0 = time.perf_counter()
            act = self.network.propose(obs)
            if (time.perf_counter() - t0) * 1000 > self.budget_ms:
                h["budget_overruns"] += 1          # recorded, not acted on: replacing on wall-clock time would break reproducibility
            if mode == "malformed":
                act = Action(np.asarray(act.lit)[:-2], np.full(n, np.nan), act.priority)
            self._check_action(act, n)
            return act, None
        except Exception as e:                       # noqa: BLE001 - every Network agent failure is contained here
            kind = "timeout" if isinstance(e, TimeoutError) else "malformed" if isinstance(e, ValueError) else "exception"
            h["failures"] += 1
            h["fallbacks"] += 1
            h["by_kind"][kind] = h["by_kind"].get(kind, 0) + 1
            act = self.fallback.act(obs)
            self._check_action(act, n)
            return act, {"agent": "network", "kind": kind, "error": str(e)[:200], "fallback": self.fallback_name}

    def _fail_closed(self, act, t, n, err):
        """Policy agent unavailable: apply the profile's fail-closed cap to the border cells, whether or not a notice is active."""
        h = self.health["policy"]
        h["failures"] += 1
        h["fallbacks"] += 1
        cap_arr = np.full(n, np.inf)
        if self.policy_agent.pfd_cap is not None:
            cap_arr = self.policy_agent.pfd_cap[t].copy()
        cells = self.fail_closed_cells
        cap_arr[cells] = np.minimum(cap_arr[cells], self.fail_closed_cap)
        over = [int(c) for c in cells if act.lit[c] and act.power[c] > self.fail_closed_cap + 1e-9]
        v = {"rule_id": "FAIL_CLOSED", "status": "FAIL" if over else "PASS", "evidence_status": "N/A", "passages": [],
             "parameter_source": "profile.resilience.fail_closed_cap_w",
             "detail": f"Policy agent unavailable ({err}); fail-closed cap {self.fail_closed_cap:g} W on cells {cells}"
                       + (f"; cells {over} reduced" if over else "")}
        return [v], cap_arr, {"agent": "policy", "kind": "exception", "error": str(err)[:200], "fallback": "fail_closed_cap"}

    def _safety_fallback(self, t, n, err):
        h = self.health["safety"]
        h["failures"] += 1
        h["fallbacks"] += 1
        forced = np.zeros(n, bool)
        em = self.safety.emergency_cells(t)
        forced[em] = True                            # protect every declared emergency cell (mode "always")
        f = {"check": "safety_unavailable", "status": "WARN", "detail": f"Safety agent unavailable ({err}); all emergency cells {em} forced on"}
        return [f], forced, {"agent": "safety", "kind": "exception", "error": str(err)[:200], "fallback": "protect_all_emergency_cells"}

    def run(self, trace, scenario="flood_relief"):
        self.policy_agent.pfd_cap = trace.meta.get("pfd_cap_w")
        twin = NTNTwin(trace, self.cfg)
        self.network.policy.reset()
        obs = twin.reset()
        N, records, review, deliberations = trace.N, [], [], 0
        self._short_run = 0
        alerted, cap_violations, repairs = False, 0, 0
        pfd_breach = pfd_bind = 0
        lat = {k: [] for k in ("network", "policy", "safety", "guard", "audit")}
        clock = time.perf_counter
        self.health = {a: {"calls": 0, "failures": 0, "fallbacks": 0, "by_kind": {}, "budget_overruns": 0} for a in ("network", "policy", "safety")}
        self._last_good = None
        conflicts, failures, dq_log, exempted = [], [], [], 0
        prev_fail, prev_conservative = set(), False
        while not twin.done:
            t = obs["t"]
            new_events = self.feed.release(t)
            obs, dq = self._validate_obs(self.faults.telemetry(obs, t), t)
            if dq:
                dq_log.append(dq)
            t0 = clock()
            act, net_fail = self._propose(obs, t, N)
            lat["network"].append(clock() - t0)
            slot_fail = [net_fail] if net_fail else []
            checks = self.guard.check(act.lit, act.power, obs["guard"], obs["ssb"], obs["sib"])
            rec = AuditRecord(scenario=scenario, slot=t, model=self.model,
                              state_summary=self._state(obs), proposed=_action(act.lit, act.power), constraints=checks, final={})
            for e in new_events:
                rec.add_step(TraceStep("event", e.kind, output={"id": e.id, "audience": e.audience, "stage": e.payload.get("stage")}, rationale=e.description))

            alert = None
            if obs.get("forecast") is not None and not alerted:
                f, cur = obs["forecast"][:, 2], np.maximum(obs["rate_obs"], 1.0)
                ratio = f / cur
                # 10 Mbps floor: a doubling of a cold cell's 2 Mbps is noise, not a surge
                hit = np.where((ratio >= self.cfg["agents"]["forecast_alert_ratio"]) & (f > self.cfg["agents"].get("forecast_alert_floor_mbps", 45.0)))[0]
                if len(hit):
                    alerted = True
                    c = int(hit[np.argmax(f[hit])])
                    alert = {"cell": c, "forecast": float(f[c]), "current": float(cur[c])}

            verdicts, cap_arr, findings, forced = [], None, [], np.zeros(N, bool)
            if self.policy_on:
                t0 = clock()
                self.health["policy"]["calls"] += 1
                try:
                    if self.faults.mode("policy", t):
                        raise RuntimeError("injected fault: Policy agent unavailable")
                    verdicts, cap_arr = self.policy_agent.review(act, t, N)
                except Exception as e:               # noqa: BLE001
                    verdicts, cap_arr, f = self._fail_closed(act, t, N, e)
                    slot_fail.append(f)
                lat["policy"].append(clock() - t0)
            if self.safety_on:
                t0 = clock()
                self.health["safety"]["calls"] += 1
                try:
                    if self.faults.mode("safety", t):
                        raise RuntimeError("injected fault: Safety agent unavailable")
                    findings, forced = self.safety.review(act, obs, t, N)
                except Exception as e:               # noqa: BLE001
                    findings, forced, f = self._safety_fallback(t, N, e)
                    slot_fail.append(f)
                lat["safety"].append(clock() - t0)
            exempt = []
            notice = self.policy_agent.active_cap(t) if self.policy_on else None
            if notice and cap_arr is not None and self.exemption == "automatic" and not any(f["agent"] == "policy" for f in slot_fail):
                exempt = [c for c in self.safety.emergency_cells(t) if c in notice["cells"]]
                if exempt:
                    cap_arr = cap_arr.copy()
                    base = self.policy_agent.pfd_cap[t] if self.policy_agent.pfd_cap is not None else np.full(N, np.inf)
                    cap_arr[exempt] = base[exempt]   # the exemption lifts the border cap only, never a flux-density limit
                    exempted += 1
                    for v in verdicts:
                        if v["rule_id"] == "R1_border_power_cap" and v["status"] == "FAIL":
                            over = [int(c) for c in notice["cells"] if act.lit[c] and act.power[c] > notice["cap_w"] + 1e-9]
                            if set(over) <= set(exempt):
                                v["status"] = "EXEMPT"
                                v["detail"] += f"; profile grants an emergency exemption to cells {exempt}"
            policy_fail = any(v["status"] == "FAIL" for v in verdicts)
            safety_warn = any(f["status"] == "WARN" for f in findings)
            protected = np.zeros(N, bool)
            if self.agents_on:
                protected[self.safety.emergency_cells(t)] = True
            slot_conf = []
            if self.agents_on:
                caps = cap_arr if cap_arr is not None else np.full(N, np.inf)
                if policy_fail:
                    slot_conf.append({"type": "network_vs_policy", "cells": [int(c) for c in np.where(act.lit & (act.power > caps + 1e-9))[0]],
                                      "resolution": "operating constraint outranks optimisation: power reduced by the guard"})
                need = np.where(forced & ~act.lit)[0]
                if len(need):
                    slot_conf.append({"type": "network_vs_safety", "cells": [int(c) for c in need],
                                      "resolution": "safety outranks optimisation: cells forced on"})
                cl = np.where(protected & act.lit & (act.power > caps + 1e-9))[0]
                if len(cl):
                    res_txt = {"never": "cap binds (profile: no exemption); logged, not escalated",
                               "human_approval": "cap binds; escalated to human review",
                               "automatic": "cap binds"}[self.exemption]
                    slot_conf.append({"type": "policy_vs_safety", "cells": [int(c) for c in cl], "resolution": res_txt})
                if exempt:
                    slot_conf.append({"type": "policy_vs_safety", "cells": exempt, "resolution": "profile exemption: border cap lifted for emergency cells"})
            constraints = Constraints(
                power_cap=cap_arr,
                forced_lit=forced,
                protected_lit=protected,
            ) if self.agents_on else None
            checks = self.guard.check(act.lit, act.power, obs["guard"], obs["ssb"], obs["sib"], constraints)
            rec.constraints = checks
            guard_fail = any(c["status"] == "FAIL" for c in checks.values())
            deliberate = self.agents_on and bool(new_events or alert or policy_fail or safety_warn or guard_fail or slot_fail or dq or slot_conf)

            prio = act.priority
            t0 = clock()
            res = self.guard.repair(act.lit, act.power, obs["guard"], obs["ssb"], obs["sib"], priority=prio, constraints=constraints)
            lat["guard"].append(clock() - t0)

            cap_now = self._true_cap(t)
            pfd = trace.meta.get("pfd_cap_w")
            if pfd is not None:
                pfd_breach += int((res.power > pfd[t] + 1e-6).any())
                pfd_bind += int((act.lit & (act.power > pfd[t] + 1e-9)).any())
            if cap_now is not None:
                cap_violations += int(any(res.lit[c] and res.power[c] > cap_now["cap_w"] + 1e-6 for c in cap_now["cells"] if c not in exempt))
            repairs += int(res.repaired)
            exec_rec = twin.step(res.lit, res.power)

            actual = exec_rec["arrived_kb"] / trace.slot_ms
            drift = np.where(res.lit & (np.abs(actual - obs["rate_obs"]) > self.drift_mbps))[0]
            if self.agents_on and len(drift):
                slot_conf.append({"type": "state_drift", "cells": [int(c) for c in drift],
                                  "resolution": "demand changed between observation and execution; recorded (the decision used lagged telemetry)"})
            for c in slot_conf:
                c["slot"] = t
            conflicts += slot_conf
            for f in slot_fail:
                failures.append({**f, "slot": t})
            human = None
            fail_now = {f["agent"] for f in slot_fail}
            if self.agents_on and self.escalate_failure and fail_now - prev_fail:
                human = {"kind": "agent_failure", "slot": t, "agents": sorted(fail_now - prev_fail),
                         "reason": "; ".join(f"{f['agent']} {f['kind']} -> {f['fallback']}" for f in slot_fail if f["agent"] in fail_now - prev_fail)}
                review.append(human)
            prev_fail = fail_now
            cons = bool(dq and dq["conservative"])
            if self.agents_on and self.escalate_data and cons and not prev_conservative and human is None:
                human = {"kind": "data_degradation", "slot": t, "cells": dq["invalid_cells"] + dq["stale_cells"],
                         "reason": f"{dq['bad_share']:.0%} of telemetry invalid or stale; running in conservative mode"}
                review.append(human)
            prev_conservative = cons
            if self.agents_on and policy_fail and self.exemption != "never" and human is None:
                human = self._shortfall(twin, trace, t, res, exec_rec, act)
                if human:
                    review.append(human)
            if self.agents_on and human is None:
                human = self._sustained(trace, t, exec_rec, self.sustained_limit)
                if human:
                    review.append(human)
            t0 = clock()
            if deliberate:
                deliberations += 1
                if dq:
                    rec.add_step(TraceStep("data_validator", "validate_telemetry", output=dq,
                                           rationale=("Conservative mode: forecast replaced by last good values everywhere. " if dq["conservative"] else "")
                                           + f"Imputed last good value on cells {dq['invalid_cells'] + dq['stale_cells']}."))
                for f in slot_fail:
                    rec.add_step(TraceStep("supervisor", "agent_failure", output=f, rationale=f"{f['agent']} agent {f['kind']}: {f['error']}. Fallback: {f['fallback']}."))
                if net_fail:
                    rec.add_step(TraceStep("network", f"fallback_{self.fallback_name}", output=rec.proposed, rationale="Deterministic fallback proposal (no model, no forecast)."))
                else:
                    rec.add_step(TraceStep("network", "run_bridge_policy", output=rec.proposed, rationale=self.network.rationale(obs, act)))
                if alert:
                    rec.add_step(TraceStep("supervisor", "forecast_alert", output=alert,
                                           rationale=f"Forecast for cell {alert['cell']} is {alert['forecast']:.1f} Mbps against {alert['current']:.1f} Mbps observed."))
                for v in verdicts:
                    rec.add_step(TraceStep("policy", v["rule_id"], output={"status": v["status"], "evidence_status": v["evidence_status"]},
                                           rationale=v["detail"], citations=v["passages"]))
                    if v["status"] == "FAIL":
                        ev, pas = self.policy_agent.evidence("R6_ml_policy_before_sink")
                        rec.add_step(TraceStep("policy", "R6_ml_policy_before_sink", output={"status": "PASS", "evidence_status": ev},
                                               rationale="Model output passes a policy function before execution. The source supports this mechanism, not the cap's value.", citations=pas[:1]))
                        ev, pas = self.policy_agent.evidence("R5_emergency_exemption")
                        rec.add_step(TraceStep("policy", "R5_emergency_exemption", output={"status": "UNVERIFIED", "evidence_status": ev},
                                               rationale="Searched the corpus for an emergency exemption from a power limit: none found." if ev == "NONE_FOUND" else "Exemption passages found; see citations.", citations=pas))
                for f in findings:
                    if f["status"] == "WARN" or new_events:
                        rec.add_step(TraceStep("safety", f["check"], output={"status": f["status"]}, rationale=f["detail"]))
                rec.add_step(TraceStep(
                    "guard",
                    "repair",
                    output={"ok": res.ok, "checks": res.checks},
                    rationale="; ".join(res.notes) or "No change needed.",
                ))
                for c in slot_conf:
                    rec.add_step(TraceStep("supervisor", f"conflict_{c['type']}", output={"cells": c["cells"]}, rationale=c["resolution"]))
                rec.add_step(TraceStep("supervisor", "resolve", output={"human_review": bool(human)},
                                       rationale=self._resolve_text(policy_fail, safety_warn, guard_fail, human)))
            self.safety.observe(res.lit)
            rec.policy_findings, rec.safety_findings = verdicts, findings
            rec.final, rec.repairs = _action(res.lit, res.power), res.notes
            rec.conflicts = slot_conf
            rec.decision = "FALLBACK" if net_fail else ("REPAIRED" if res.repaired else "APPROVED")
            rec.execution_status = "EXECUTED"
            rec.outcome = {"throughput_mbps": exec_rec["throughput_mbps"], "delay_ms": exec_rec["delay_ms"],
                           "rt_violation": exec_rec["rt_violation"], "human_review": bool(human), "deliberated": deliberate}
            records.append(rec)
            lat["audit"].append(clock() - t0)
            obs = twin.obs()
        kpis = summarise(twin.history, twin.slot_ms, {"guard_repairs": repairs})
        em_mask = trace.emergency > 0
        arr = np.array([h["arrived_kb"] for h in twin.history])
        srv = np.array([h["served_kb"] for h in twin.history])
        kpis["emergency_served_ratio"] = float(srv[em_mask].sum() / max(arr[em_mask].sum(), 1e-9))
        kpis["cap_violation_slots"] = cap_violations
        kpis["pfd_breach_slots"], kpis["pfd_binding_slots"] = pfd_breach, pfd_bind
        kpis["human_reviews"] = len(review)
        kpis["deliberations"] = deliberations
        by_type: dict = {}
        for c in conflicts:
            by_type[c["type"]] = by_type.get(c["type"], 0) + 1
        coordination = {
            "profile": (self.profile or {}).get("profile_id"), "exemption_mode": self.exemption,
            "agents_enabled": {"policy": self.policy_on, "safety": self.safety_on},
            "agent_health": self.health, "failures": failures[:200], "conflicts": conflicts[:300], "conflicts_by_type": by_type,
            "exempted_slots": exempted, "fallback_slots": sum(1 for f in failures if f["agent"] == "network"),
            "data_quality": {"degraded_slots": len(dq_log), "conservative_slots": sum(d["conservative"] for d in dq_log),
                             "imputed_cell_slots": sum(len(d["invalid_cells"]) + len(d["stale_cells"]) for d in dq_log)},
            "human_review_by_kind": {k: sum(1 for h in review if h["kind"] == k) for k in sorted({h["kind"] for h in review})},
        }
        return {"kpis": kpis, "records": records, "history": twin.history, "human_review": review, "coordination": coordination,
                "compute_ms": {k: (np.array(v) * 1000).tolist() for k, v in lat.items()}}

    def _sustained(self, trace, t, rec, limit=5):
        """Emergency capacity below demand for `limit` slots in a row, whatever the cause (fade, cap)."""
        em = self.safety.emergency_cells(t)
        lit_em = [c for c in em if rec["lit"][c]]
        want = float(rec["arrived_kb"][em].sum() / trace.slot_ms) if em else 0.0
        got = float(rec["cap_mbps"][lit_em].sum()) if lit_em else 0.0
        self._short_run = self._short_run + 1 if em and got < want else 0
        if self._short_run != limit:
            return None
        return {"kind": "sustained_shortfall", "slot": t, "cells": em, "demand_mbps": round(want, 1), "capacity_mbps": round(got, 1),
                "capacity_lost_mbps": 0.0, "shortfall_mbps": round(want - got, 1), "proposed_w": {}, "final_w": {},
                "reason": f"Emergency capacity has been below demand for {limit} slots."}

    def _true_cap(self, t):
        for e in reversed(self.feed.events):
            if e.kind == "policy" and e.slot <= t:
                return e.payload
        return None

    def _shortfall(self, twin, trace, t, res, rec, act):
        em = self.safety.emergency_cells(t)
        capped = [c for c in em if act.lit[c] and act.power[c] > res.power[c] + 1e-6]
        if not capped:
            return None
        link = twin.link
        uncapped = link.capacity_mbps(link.sinr(act.power, trace.gain[t], act.lit), trace.los[t], trace.ssb[t], trace.sib[t])
        want = float(np.sum(rec["arrived_kb"][capped]) / trace.slot_ms)
        got = float(np.sum(rec["cap_mbps"][capped]))
        return {"kind": "cap_conflict", "slot": t, "cells": capped, "dark_after_repair": [c for c in capped if not res.lit[c]], "demand_mbps": round(want, 1), "capacity_mbps": round(got, 1),
                "capacity_lost_mbps": round(float(np.sum(uncapped[capped])) - got, 1),
                "shortfall_mbps": round(max(want - got, 0.0), 1), "proposed_w": {c: round(float(act.power[c]), 1) for c in capped},
                "final_w": {c: round(float(res.power[c]), 1) for c in capped},
                "reason": "Operating constraint conflicts with emergency service and no exemption passage was found in the corpus."}

    @staticmethod
    def _resolve_text(policy_fail, safety_warn, guard_fail, human):
        if human and human["kind"] in ("agent_failure", "data_degradation"):
            return f"{human['reason']}; sent for human review."
        if human and human["kind"] == "sustained_shortfall":
            return f"{human['reason']} {human['shortfall_mbps']} Mbps short; sent for human review."
        if policy_fail and human:
            state = f"emergency cells {human['dark_after_repair']} went dark this slot" if human.get("dark_after_repair") else "emergency cells stay lit at the capped power"
            return (f"Constraint holds (it outranks optimisation and is treated as binding): {state}. "
                    f"Cap costs {human['capacity_lost_mbps']} Mbps of capacity, {human['shortfall_mbps']} Mbps below demand; sent for human review.")
        if policy_fail:
            return "Cap applied; no emergency cell was reduced."
        if safety_warn:
            return "Safety priority applied: emergency cells forced on."
        if guard_fail:
            return "Guard repaired the proposal before execution."
        return "Proposal approved."

    def _state(self, obs):
        s = {"observed_demand_mbps": np.round(obs["rate_obs"], 1).tolist(),
             "rt_backlog_kb": np.round(obs["q_rt"], 0).tolist()}
        if obs.get("forecast") is not None:
            s["forecast_mbps"] = np.round(obs["forecast"][:, 2], 1).tolist()
        return s
