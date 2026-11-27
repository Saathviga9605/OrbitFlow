"""Standards, readiness and knowledge-catalogue files: valid statuses, real evidence paths, real documents."""
import json
import os

import yaml

from utils.config import ROOT

K = os.path.join(ROOT, "knowledge")
load = lambda n: yaml.safe_load(open(os.path.join(K, n), encoding="utf8"))       # noqa: E731
MANIFEST = {d["doc_id"] for d in yaml.safe_load(open(os.path.join(ROOT, "rag", "knowledge_base", "manifest.yaml"), encoding="utf8"))}
RULES = {r["id"] for r in yaml.safe_load(open(os.path.join(ROOT, "agents", "policy_rules.yaml"), encoding="utf8"))}


def _exists(p):
    return os.path.exists(os.path.join(ROOT, p.split(" ")[0]))


def test_standards_entries_are_honest_and_evidenced():
    s = load("standards_map.yaml")
    for e in s["entries"]:
        assert e["status"] in s["statuses"], e["id"]
        assert e["not_implemented"], f"{e['id']} must state what is not implemented"
        for p in e["implementation_evidence"]:
            assert _exists(p), f"{e['id']}: {p}"
        if e["in_knowledge_base"]:
            assert e["in_knowledge_base"] in MANIFEST, e["id"]
        assert set(e.get("kb_rules", [])) <= RULES, e["id"]
        if e["status"] == "implemented_in_simulation":
            assert e["implementation_evidence"], e["id"]
    text = open(os.path.join(K, "standards_map.yaml"), encoding="utf8").read().lower()
    assert "claims no certification" in text


def test_readiness_mapping_uses_framework_factors_and_defined_maturity():
    r = load("ai_readiness_map.yaml")
    factors = {m["factor"] for m in json.load(open(os.path.join(ROOT, "results", "kb_report.json"), encoding="utf8"))["readiness_mapping"]}
    assert r["framework"]["doc_id"] in MANIFEST
    for f in r["factors"]:
        assert f["factor"] in factors
        assert f["maturity"] in r["maturity_scale"]
        assert f["maturity"] < 4, "nothing here is externally validated or operational"
        assert f["justification"] and f["gap"]
        for p in f["evidence"]:
            assert _exists(p), f"{f['factor']}: {p}"


def test_catalogue_paths_exist():
    for it in load("catalog.yaml")["items"]:
        assert _exists(it["path"]), it["path"]
        assert it["provenance"] in ("official", "research", "synthetic", "illustrative", "assumption", "developer")
