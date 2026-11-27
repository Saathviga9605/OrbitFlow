"""Policy profiles: externalised, versioned, validated configuration for one country/operator/context.

The prediction model, BRIDGE policy and guard never read a profile. A profile only changes
  * the operating constraint the Policy agent receives (border cap cells, value, onset),
  * how the Supervisor resolves a cap-vs-emergency conflict (exemption mode),
  * safety thresholds, human-review triggers and fail-safe behaviour.
So "same traffic + same model proposal + different profile -> different validation/permitted action"
is testable (tests/test_policy_profiles.py) and visible in results/scenario_suite.json.
"""
from __future__ import annotations

import copy
import glob
import hashlib
import json
import os

import yaml

from utils.config import ROOT

PROFILE_DIR = os.path.join(ROOT, "policy", "profiles")
RULES = os.path.join(ROOT, "agents", "policy_rules.yaml")
EXEMPTION_MODES = ("never", "human_approval", "automatic")
STATUSES = ("ILLUSTRATIVE", "VERIFIED", "DRAFT")
SOURCE_TYPES = ("official", "research", "illustrative", "assumption", "synthetic")
ENFORCEMENT = ("software", "configuration", "documented")
REQUIRED = ("profile_id", "title", "jurisdiction", "version", "effective_date", "status", "provenance_note",
            "operating_constraints", "safety", "human_oversight", "resilience", "governance_rules")


class PolicyValidationError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def list_profiles() -> list[str]:
    return sorted(yaml.safe_load(open(p, encoding="utf8"))["profile_id"] for p in glob.glob(os.path.join(PROFILE_DIR, "*.yaml")))


def load_profile(profile_id: str) -> dict:
    for p in glob.glob(os.path.join(PROFILE_DIR, "*.yaml")):
        with open(p, encoding="utf8") as f:
            d = yaml.safe_load(f)
        if d.get("profile_id") == profile_id:
            d["_file"] = os.path.relpath(p, ROOT).replace("\\", "/")
            return d
    raise KeyError(f"unknown policy profile: {profile_id}; available: {list_profiles()}")


def fingerprint(profile: dict) -> str:
    clean = {k: v for k, v in profile.items() if not k.startswith("_")}
    return hashlib.sha256(json.dumps(clean, sort_keys=True, default=str).encode()).hexdigest()[:12]


def with_overrides(profile: dict, cap_w: float | None = None, exemption: str | None = None) -> dict:
    """Operator customisation without editing the file. The result is marked as a derived profile."""
    p = copy.deepcopy(profile)
    if cap_w is not None:
        p["operating_constraints"]["border_power_cap"]["cap_w"] = float(cap_w)
    if exemption is not None:
        p["operating_constraints"]["emergency_exemption"] = exemption
    if cap_w is not None or exemption is not None:
        p["version"] = f"{p['version']}+custom"
        p["status"] = "DRAFT"
    return p


def _num(d: dict, key: str, lo: float, hi: float, errors: list, where: str):
    v = d.get(key)
    if not isinstance(v, (int, float)) or isinstance(v, bool) or not lo <= v <= hi:
        errors.append(f"{where}.{key} must be a number in [{lo}, {hi}], got {v!r}")


def validate(profile: dict, cfg: dict, kb=None) -> dict:
    """Schema checks, cross-field conflicts and (with a knowledge base) evidence status for each rule."""
    errors, warnings, conflicts = [], [], []
    for k in REQUIRED:
        if k not in profile:
            errors.append(f"missing field: {k}")
    if errors:
        return {"valid": False, "errors": errors, "warnings": warnings, "conflicts": conflicts, "rules": []}
    n, p_min, p_max = cfg["scenario"]["n_cells"], cfg["scenario"]["p_min_w"], cfg["scenario"]["p_max_w"]
    if profile["status"] not in STATUSES:
        errors.append(f"status must be one of {STATUSES}")
    oc = profile["operating_constraints"]
    cap = oc.get("border_power_cap", {})
    if not isinstance(cap.get("enabled"), bool):
        errors.append("operating_constraints.border_power_cap.enabled must be true or false")
    cells = cap.get("cells", [])
    if not isinstance(cells, list) or not all(isinstance(c, int) and 0 <= c < n for c in cells):
        errors.append(f"border_power_cap.cells must be cell indices in [0, {n - 1}]")
    _num(cap, "cap_w", 0.0, p_max, errors, "border_power_cap")
    _num(cap, "onset_slot", 0, 99, errors, "border_power_cap")
    if oc.get("emergency_exemption") not in EXEMPTION_MODES:
        errors.append(f"emergency_exemption must be one of {EXEMPTION_MODES}")
    _num(profile["safety"], "max_beam_share", 0.1, 1.0, errors, "safety")
    _num(profile["safety"], "starve_slots", 1, 1000, errors, "safety")
    ho = profile["human_oversight"]
    _num(ho, "sustained_shortfall_slots", 1, 100, errors, "human_oversight")
    for k in ("escalate_on_agent_failure", "escalate_on_data_degradation"):
        if not isinstance(ho.get(k), bool):
            errors.append(f"human_oversight.{k} must be true or false")
    rs = profile["resilience"]
    _num(rs, "fail_closed_cap_w", 0.0, p_max, errors, "resilience")
    _num(rs, "decision_budget_ms", 0.1, 1000, errors, "resilience")
    _num(rs, "max_bad_telemetry_share", 0.0, 1.0, errors, "resilience")
    _num(rs, "state_drift_mbps", 0.1, 1000, errors, "resilience")
    known_rules = {r["id"]: r for r in yaml.safe_load(open(RULES, encoding="utf8"))}
    ids = [r.get("id") for r in profile["governance_rules"]]
    if len(ids) != len(set(ids)):
        errors.append("governance rule ids must be unique")
    for r in profile["governance_rules"]:
        if r.get("enforcement") not in ENFORCEMENT:
            errors.append(f"{r.get('id')}: enforcement must be one of {ENFORCEMENT}")
        if r.get("source_type") not in SOURCE_TYPES:
            errors.append(f"{r.get('id')}: source_type must be one of {SOURCE_TYPES}")
        if r.get("kb_rule") and r["kb_rule"] not in known_rules:
            errors.append(f"{r.get('id')}: kb_rule {r['kb_rule']} is not in agents/policy_rules.yaml")
    if errors:
        return {"valid": False, "errors": errors, "warnings": warnings, "conflicts": conflicts, "rules": []}

    # cross-field conflicts: detected, explained and given a stated resolution
    if cap["enabled"] and cap["cap_w"] < p_min:
        errors.append(f"border cap {cap['cap_w']} W is below the per-beam floor {p_min} W: a capped cell could never be lit")
    if rs["fail_closed_cap_w"] < p_min:
        errors.append(f"fail-closed cap {rs['fail_closed_cap_w']} W is below the per-beam floor {p_min} W")
    if cap["enabled"] and rs["fail_closed_cap_w"] > cap["cap_w"]:
        warnings.append(f"fail-closed cap ({rs['fail_closed_cap_w']} W) is looser than the normal cap ({cap['cap_w']} W): "
                        "losing the Policy agent would relax the constraint")
    em = set(cfg["demo"]["emergency_cells"])
    overlap = sorted(em & set(cells)) if cap["enabled"] else []
    mode = oc["emergency_exemption"]
    if overlap:
        resolution = {"never": "cap binds; reduced emergency capacity is logged as a conflict and not escalated",
                      "human_approval": "cap binds; every slot it reduces an emergency beam is sent for human review",
                      "automatic": "emergency cells are exempt from the cap; each exempted slot is logged"}[mode]
        conflicts.append({"id": "CAP_VS_EMERGENCY", "between": ["operating_constraints.border_power_cap", "safety.emergency_priority"],
                          "cells": overlap, "resolution": resolution})
        if mode == "never" and not ho["escalate_on_agent_failure"]:
            warnings.append("cap binds on emergency cells with no exemption and no escalation path")
    rules = []
    for r in profile["governance_rules"]:
        entry = {k: r.get(k) for k in ("id", "title", "enforcement", "enforced_by", "source_type", "kb_rule")}
        entry["evidence_status"], entry["quote"] = "NOT_CHECKED", None
        spec = known_rules.get(r.get("kb_rule")) if r.get("kb_rule") else r.get("evidence")
        if kb is not None and spec:
            from rag.retriever import answer
            res = answer(kb, spec["query"], spec.get("must"), doc_ids=set(spec["doc_ids"]) if spec.get("doc_ids") else None)
            entry["evidence_status"] = "FOUND" if res.supported else "NONE_FOUND"
            entry["quote"] = res.quotes[0] if res.quotes else None
        elif not spec:
            entry["evidence_status"] = "NO_SOURCE"
        rules.append(entry)
    if mode == "automatic":
        r5 = next((r for r in rules if r.get("kb_rule") == "R5_emergency_exemption"), None)
        if r5 is None or r5["evidence_status"] != "FOUND":
            warnings.append("automatic emergency exemption has no supporting passage in the knowledge base (R5): "
                            "it is an operator choice, not a sourced rule")
    return {"valid": not errors, "errors": errors, "warnings": warnings, "conflicts": conflicts, "rules": rules}


def scenario_overrides(profile: dict) -> dict:
    """What a profile changes in the flood-relief scenario's policy notice (config.yaml:demo keys)."""
    cap = profile["operating_constraints"]["border_power_cap"]
    if not cap["enabled"]:
        return {"cap_enabled": False}
    return {"border_cells": list(cap["cells"]), "border_cap_w": float(cap["cap_w"]), "cap_slot": int(cap["onset_slot"])}


def runtime_config(profile: dict, cfg: dict) -> dict:
    """A config copy with the profile's safety thresholds applied. Model sections are untouched."""
    c = copy.deepcopy(cfg)
    c["agents"]["max_beam_share"] = float(profile["safety"]["max_beam_share"])
    c["agents"]["starve_slots"] = int(profile["safety"]["starve_slots"])
    return c


def summary(profile: dict) -> dict:
    keys = ("profile_id", "title", "jurisdiction", "operator", "deployment_context", "version", "effective_date", "status", "provenance_note")
    return {**{k: profile.get(k) for k in keys}, "fingerprint": fingerprint(profile), "file": profile.get("_file"),
            "operating_constraints": profile["operating_constraints"], "safety": profile["safety"],
            "human_oversight": profile["human_oversight"], "resilience": profile["resilience"]}
