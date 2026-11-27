"""Builds the governance bundle (registry, profiles, standards, readiness, knowledge catalogue, tests).

Everything is read from machine-readable files in the repository; nothing is typed into the UI.
"""
from __future__ import annotations

import glob
import json
import os
import re

import yaml

from agents.registry import load_registry
from policy.engine import list_profiles, load_profile, summary, validate
from utils.config import ROOT

KDIR = os.path.join(ROOT, "knowledge")


def _yaml(name):
    with open(os.path.join(KDIR, name), encoding="utf8") as f:
        return yaml.safe_load(f)


def _exists(path: str) -> bool:
    return os.path.exists(os.path.join(ROOT, path.split(" ")[0]))


def test_inventory() -> list[dict]:
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "tests", "test_*.py"))):
        src = open(p, encoding="utf8").read()
        doc = re.match(r'\s*"""(.*?)"""', src, re.S)
        out.append({"file": os.path.relpath(p, ROOT).replace("\\", "/"), "tests": len(re.findall(r"^def test_", src, re.M)),
                    "about": doc.group(1).strip().splitlines()[0] if doc else ""})
    return out


def build(cfg: dict, kb=None) -> dict:
    standards = _yaml("standards_map.yaml")
    readiness = _yaml("ai_readiness_map.yaml")
    catalog = _yaml("catalog.yaml")
    kb_report = json.load(open(os.path.join(ROOT, "results", "kb_report.json"), encoding="utf8"))
    quotes = {m["factor"]: m["stated_in_framework"] for m in kb_report.get("readiness_mapping", [])}
    for f in readiness["factors"]:
        f["framework_statement"] = quotes.get(f["factor"])
        f["evidence_present"] = {e: _exists(e) for e in f["evidence"]}
    for e in standards["entries"]:
        e["evidence_present"] = {p: _exists(p) for p in e["implementation_evidence"]}
    for it in catalog["items"]:
        it["present"] = _exists(it["path"])
    profiles = []
    for pid in list_profiles():
        p = load_profile(pid)
        profiles.append({**summary(p), "governance_rules": p["governance_rules"], "validation": validate(p, cfg, kb)})
    rules = yaml.safe_load(open(os.path.join(ROOT, "agents", "policy_rules.yaml"), encoding="utf8"))
    std_by_rule: dict = {}
    for e in standards["entries"]:
        for r in e.get("kb_rules", []):
            std_by_rule.setdefault(r, []).append(e["standard"])
    alignment = []                       # standards <-> profile rules <-> enforcement <-> evidence
    for p in profiles:
        for r in p["validation"]["rules"]:
            alignment.append({"profile": p["profile_id"], "rule": r["id"], "title": r["title"], "enforcement": r["enforcement"],
                              "enforced_by": r["enforced_by"], "source_type": r["source_type"], "kb_rule": r.get("kb_rule"),
                              "evidence_status": r["evidence_status"], "standards": std_by_rule.get(r.get("kb_rule"), [])})
    manifest = yaml.safe_load(open(os.path.join(ROOT, "rag", "knowledge_base", "manifest.yaml"), encoding="utf8"))
    cats: dict = {}
    for d in manifest:
        cats[d.get("category", "other")] = cats.get(d.get("category", "other"), 0) + 1
    return {
        "registry": load_registry(),
        "profiles": profiles,
        "standards": standards,
        "readiness": readiness,
        "requirements_alignment": alignment,
        "kb_rules": [{"id": r["id"], "title": r["title"], "parameter_source": r.get("parameter_source"),
                      "standards": std_by_rule.get(r["id"], [])} for r in rules],
        "knowledge": {"catalog": catalog, "documents": len(manifest), "evidence_eligible": sum(bool(d.get("evidence_eligible")) for d in manifest),
                      "by_category": dict(sorted(cats.items(), key=lambda kv: -kv[1]))},
        "tests": test_inventory(),
    }
