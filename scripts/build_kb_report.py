"""Knowledge-base report: inventory, retrieval evaluation, rule evidence, readiness mapping, gap candidates.

    python scripts/build_kb_report.py
Quotes come only from retrieval and are checked verbatim; a mapping row with no verified quote fails the build.
"""
from __future__ import annotations

import json
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rag.retriever import KnowledgeBase, answer, validate_citations  # noqa: E402
from utils.config import load_config  # noqa: E402

FRAMEWORK = {"ai_ready_framework_2025"}
Y3172 = {"t_rec_y_3172_201906_i_pdf_e"}
# factor names are the framework's. `relevance` is OrbitFlow's interpretation; `orbitflow` is OrbitFlow's own contribution.
MAPPING = [
    dict(factor="Open data", must=["datasets"], q="Open data accessibility and quality of datasets for analysis of AI applications", support_q="data collection cleaning labeling public data openness", support_must=["data"], support_docs=FRAMEWORK,
         relevance="Beam-hopping AI depends on demand and channel data, which is rarely open for satellite networks.", orbitflow="Documents its three offline datasets, dead columns and synthetic demand in docs/REPORT.md.", confidence="medium"),
    dict(factor="Research", must=["research"], q="Research collaboration between domain-specific and AI research communities", support_q="domain-specific research advancements AI research balance", support_must=["research"], support_docs=FRAMEWORK,
         relevance="OrbitFlow combines radio resource management with reinforcement learning.", orbitflow="Reproducible experiments with baselines, ablations and published negative results.", confidence="medium"),
    dict(factor="Deployment", must=["deployment"], q="Deployment infrastructure and ecosystem readiness for AI deployment", support_q="ML pipeline deployment in network underlay SINK", support_must=["policy|sink"], support_docs=Y3172,
         relevance="A controller only matters if it fits the decision interval of the network it runs on.", orbitflow="Measures compute per slot against the 10 ms interval on CPU. Offline simulation only; nothing is deployed.", confidence="low"),
    dict(factor="Standards", must=["interoperability"], q="Standards ensuring trust interoperability and compliance", support_q="application of policies to the output of the model node", support_must=["polic"], support_docs=Y3172,
         relevance="The Y.3172 policy node corresponds to OrbitFlow's guard between model output and execution.", orbitflow="Maps its pipeline to Y.3172 node names. This is a design mapping, not a conformance claim.", confidence="high"),
    dict(factor="Open source", must=["open developer|open source"], q="Open source and code enabling rapid adoption through an open developer ecosystem", support_q="open-source technologies lower entry barriers for AI adoption", support_must=["open.source"], support_docs=FRAMEWORK,
         relevance="Open code lets others re-run and challenge the results.", orbitflow="All code, seeds and configs are in the repository; every headline reproduces from scripts.", confidence="medium"),
    dict(factor="Sandbox", must=["sandbox"], q="Sandbox platforms for AI experimentation and validation", support_q="ML sandbox train test evaluate before deploying in a live network", support_must=["sandbox"], support_docs=Y3172,
         relevance="The digital twin plays the sandbox role: policies are tested before any live use.", orbitflow="Digital twin, what-if lab and stress test. The twin is a simulator with provisional link parameters.", confidence="high"),
]
QUESTIONS = [
    ("What does Y.3172 say the policy node does?", ["polic"], Y3172), ("How should the level of human oversight be decided?", ["human oversight"], None),
    ("What should an AI audit trail capture?", ["audit trail|traceab"], None), ("What is an ML sandbox?", ["sandbox"], Y3172),
    ("What are the AI Readiness factors?", ["factor"], FRAMEWORK), ("Is emergency traffic exempt from a cross-border beam power limit?", ["exempt|waive|derogat", "power limit|power cap|transmit power|beam power"], None),
    ("What is the maximum satellite beam EIRP allowed over a border?", ["EIRP|power flux", "satellite"], None),
]
GAPS = {"R1_border_power_cap": ("Beam power limits for cross-border satellite coverage", "OrbitFlow's cap stays a hypothetical operating constraint."),
        "R2_emergency_priority": ("Priority for emergency traffic on network resources", "OrbitFlow's emergency priority is a design choice, not derived from the corpus."),
        "R4_signalling": ("Initial-access signalling protection for NTN", "The 40/80-slot limits stay configuration assumptions."),
        "R5_emergency_exemption": ("Emergency exemption from a power limit", "The supervisor keeps the constraint and refers conflicts to a human.")}


def main():
    kb = KnowledgeBase(load_config())
    rules = yaml.safe_load(open(os.path.join(ROOT, "agents", "policy_rules.yaml"), encoding="utf8"))
    all_cites = []
    verdicts = []
    for r in rules:
        a = answer(kb, r["query"], r.get("must"), doc_ids=set(r["doc_ids"]) if r.get("doc_ids") else None)
        all_cites += a.quotes
        verdicts.append({"rule_id": r["id"], "title": r["title"], "evidence_status": "FOUND" if a.supported else "NONE_FOUND", "passages": a.quotes, "parameter_source": r["parameter_source"], "query": r["query"], "must": r.get("must")})
    mapping = []
    for m in MAPPING:
        direct = answer(kb, m["q"], m["must"], k=1, doc_ids=FRAMEWORK)
        sup = answer(kb, m["support_q"], m["support_must"], k=1, doc_ids=m["support_docs"])
        assert direct.supported and sup.supported, m["factor"]
        all_cites += direct.quotes + sup.quotes
        mapping.append({"factor": m["factor"], "stated_in_framework": direct.quotes[0], "supporting_evidence": sup.quotes[0], "interpretation": m["relevance"], "orbitflow_contribution": m["orbitflow"], "confidence": m["confidence"]})
    qa = []
    for q, must, docs in QUESTIONS:
        a = answer(kb, q, must, doc_ids=docs)
        all_cites += a.quotes
        qa.append({"query": q, "supported": a.supported, "statement": a.statement, "quotes": a.quotes})
    bad = validate_citations(kb, all_cites)
    assert not bad, bad
    eligible = sum(bool(d["evidence_eligible"]) for d in kb.manifest)
    prov = sum(all(d.get(k) for k in ("sha256", "source_path", "source_commit", "filename")) for d in kb.manifest)
    report = {"source": {"repository": kb.manifest[0]["source_repository"], "commit": kb.manifest[0]["source_commit"], "directory": "simulation/server/knowledge/InputDocs", "licence": kb.manifest[0]["licence"]},
              "totals": {"files": len(kb.manifest), "ingested": len(kb.ingested), "failed": len(kb.skipped), "evidence_eligible": eligible, "pages": sum(d["pages"] for d in kb.manifest), "chunks": len(kb.passages), "chars": sum(d["chars"] for d in kb.manifest), "provenance_complete": prov},
              "documents": [{k: d.get(k) for k in ("doc_id", "filename", "title", "issuer", "issuer_basis", "year", "year_basis", "doc_type", "category", "role", "pages", "chunks", "extraction", "evidence_eligible", "overlaps", "sha256")} for d in kb.manifest],
              "failed": [{"filename": d["filename"], "reason": d["extraction"]} for d in kb.skipped],
              "retrieval_eval": json.load(open(os.path.join(ROOT, "results", "retrieval_eval.json"))),
              "index": {"default_method": "bm25", "implementation": "scipy sparse BM25 (k1 1.5, b 0.75) over section-aware sentence-packed chunks", "dense_kept_for_comparison": "BAAI/bge-small-en-v1.5"},
              "citation_verification": {"checked": len(all_cites), "failed": len(bad), "method": "whitespace-normalised containment in the source chunk, at most 40 words"},
              "rules": verdicts, "readiness_mapping": mapping, "questions": qa,
              "limitations": ["Issuer and year metadata are inferred from filenames and the repository's index, not checked against each document.", "Two PDFs failed in both parsers and no OCR tool is available.", "The corpus is AI policy; it has no spectrum regulation, 3GPP or O-RAN documents.", "Gold queries were written by the developer, n=30.", "Nothing has been verified by a human or legal reviewer. Retrieval does not establish compliance."]}
    json.dump(report, open(os.path.join(ROOT, "results", "kb_report.json"), "w"), indent=1)
    gaps = {"human_verified": False, "header": "Machine-generated candidates. These are gaps in this corpus, not findings about the law.",
            "candidates": [{"id": f"GAP-{i+1:02d}", "rule_id": v["rule_id"], "title": GAPS[v["rule_id"]][0], "statement": f"No eligible passage in {eligible} documents met the evidence test for: {v['query']}.", "consequence": GAPS[v["rule_id"]][1],
                            "absence_evidence": {"query": v["query"], "must": v["must"]}, "human_verified": False}
                           for i, v in enumerate(x for x in verdicts if x["evidence_status"] == "NONE_FOUND" and x["rule_id"] in GAPS)]}
    json.dump(gaps, open(os.path.join(ROOT, "results", "gaps.json"), "w"), indent=1)
    print(report["totals"], report["citation_verification"], [v["evidence_status"] for v in verdicts], [q["supported"] for q in qa])
    for m in mapping:
        print(m["factor"], "|", m["stated_in_framework"]["quote"][:90], "|", m["supporting_evidence"]["quote"][:90])


if __name__ == "__main__":
    main()
