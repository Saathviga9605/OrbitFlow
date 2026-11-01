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

from audit.schemas import AuditRecord, TraceStep
from bam.validator import BamGuard, Constraints
from digital_twin.environment import NTNTwin, summarise
from rag.retriever import KnowledgeBase, answer

RULES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "policy_rules.yaml")


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
            if growth[c] > 3:
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


class Supervisor:
    def __init__(self, cfg, policy, feed, kb: KnowledgeBase, agents_on: bool = True, model: str = "BRIDGE-ppo"):
        self.cfg, self.feed, self.kb, self.agents_on, self.model = cfg, feed, kb, agents_on, model
        self.network, self.policy_agent = NetworkAgent(policy, feed), PolicyAgent(feed, kb)
        self.safety = SafetyAgent(feed, cfg)
        self.guard = BamGuard(cfg)

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
        while not twin.done:
            t = obs["t"]
            new_events = self.feed.release(t)
            t0 = clock()
            act = self.network.propose(obs)
            lat["network"].append(clock() - t0)
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
                hit = np.where((ratio >= self.cfg["agents"]["forecast_alert_ratio"]) & (f > 10.0))[0]
                if len(hit):
                    alerted = True
                    c = int(hit[np.argmax(f[hit])])
                    alert = {"cell": c, "forecast": float(f[c]), "current": float(cur[c])}

            verdicts, cap_arr, findings, forced = [], None, [], np.zeros(N, bool)
            if self.agents_on:
                t0 = clock()
                verdicts, cap_arr = self.policy_agent.review(act, t, N)
                lat["policy"].append(clock() - t0)
                t0 = clock()
                findings, forced = self.safety.review(act, obs, t, N)
                lat["safety"].append(clock() - t0)
            policy_fail = any(v["status"] == "FAIL" for v in verdicts)
            safety_warn = any(f["status"] == "WARN" for f in findings)
            guard_fail = any(c["status"] == "FAIL" for c in checks.values())
            deliberate = self.agents_on and bool(new_events or alert or policy_fail or safety_warn or guard_fail)

            constraints = Constraints(power_cap=cap_arr, forced_lit=forced) if self.agents_on else None
            prio = act.priority
            if self.agents_on and self.safety.emergency_cells(t):      # if a beam must go, it is never an emergency cell's
                prio = np.array(act.priority, dtype=float).copy()
                prio[self.safety.emergency_cells(t)] += 1e6
            t0 = clock()
            res = self.guard.repair(act.lit, act.power, obs["guard"], obs["ssb"], obs["sib"], priority=prio, constraints=constraints)
            lat["guard"].append(clock() - t0)

            cap_now = self._true_cap(t)
            pfd = trace.meta.get("pfd_cap_w")
            if pfd is not None:
                pfd_breach += int((res.power > pfd[t] + 1e-6).any())
                pfd_bind += int((act.lit & (act.power > pfd[t] + 1e-9)).any())
            if cap_now is not None:
                cap_violations += int(any(res.lit[c] and res.power[c] > cap_now["cap_w"] + 1e-6 for c in cap_now["cells"]))
            repairs += int(res.repaired)
            exec_rec = twin.step(res.lit, res.power)

            human = None
            if self.agents_on and policy_fail:
                human = self._shortfall(twin, trace, t, res, exec_rec, act)
                if human:
                    review.append(human)
            if self.agents_on and human is None:
                human = self._sustained(trace, t, exec_rec)
                if human:
                    review.append(human)
            t0 = clock()
            if deliberate:
                deliberations += 1
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
                rec.add_step(TraceStep("guard", "repair", output={"ok": res.ok}, rationale="; ".join(res.notes) or "No change needed."))
                rec.add_step(TraceStep("supervisor", "resolve", output={"human_review": bool(human)},
                                       rationale=self._resolve_text(policy_fail, safety_warn, guard_fail, human)))
            self.safety.observe(res.lit)
            rec.policy_findings, rec.safety_findings = verdicts, findings
            rec.final, rec.repairs = _action(res.lit, res.power), res.notes
            rec.decision = "REPAIRED" if res.repaired else "APPROVED"
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
        return {"kpis": kpis, "records": records, "history": twin.history, "human_review": review,
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
