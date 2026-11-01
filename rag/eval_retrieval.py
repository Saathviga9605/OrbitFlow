"""Compare retrieval methods on rag/gold_queries.yaml. Writes results/retrieval_eval.json.

    python -m rag.eval_retrieval [--build-dense]
Doc recall = right document in top k. Section recall = a chunk from a right doc matching the expected wording in top k.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time

import numpy as np
import yaml

from rag.retriever import DENSE, DENSE_MODEL, KnowledgeBase, Passage
from utils.config import ROOT, load_config


def build_dense(kb):
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(DENSE_MODEL)
    v = m.encode([f"{p.section}. {p.text}" for p in kb.passages], normalize_embeddings=True, batch_size=64, show_progress_bar=False)
    np.save(DENSE, v.astype(np.float32))


def evaluate(kb, gold, method, k=5):
    rows, times = [], []
    for g in gold:
        t0 = time.perf_counter()
        res = kb.retrieve(g["q"], k, method=method)
        times.append((time.perf_counter() - t0) * 1000)
        doc = ["any" in g["docs"] or p.doc_id in g["docs"] for p in res]
        sec = [d and bool(re.search(g["match"], p.text)) for d, p in zip(doc, res)]
        first = next((i for i, s in enumerate(sec) if s), None)
        rows.append({"q": g["q"], "doc_hit": any(doc), "section_hit": any(sec), "precision": sum(sec) / k, "rr": 0 if first is None else 1 / (first + 1)})
    return {"precision_at_5": float(np.mean([r["precision"] for r in rows])), "section_recall_at_5": float(np.mean([r["section_hit"] for r in rows])),
            "doc_recall_at_5": float(np.mean([r["doc_hit"] for r in rows])), "mrr": float(np.mean([r["rr"] for r in rows])),
            "latency_ms_median": float(np.median(times)), "misses": [r["q"] for r in rows if not r["section_hit"]], "n": len(rows)}


def main(build=False):
    cfg = load_config()
    kb = KnowledgeBase(cfg)
    if build or not os.path.exists(DENSE):
        build_dense(kb)
    kb = KnowledgeBase(cfg, use_dense=True)
    gold = yaml.safe_load(open(os.path.join(ROOT, "rag", "gold_queries.yaml"), encoding="utf8"))
    ids = {d["doc_id"] for d in kb.manifest}
    missing = [d for g in gold for d in g["docs"] if d != "any" and d not in ids]
    assert not missing, f"gold set names unknown documents: {missing}"
    out = {"note": "Gold set written by the developer after reading the corpus; n is small, treat differences of a few queries as noise.",
           "methods": {m: evaluate(kb, gold, m) for m in ("bm25", "tfidf", "hybrid", "dense", "hybrid_dense")}}
    json.dump(out, open(os.path.join(ROOT, "results", "retrieval_eval.json"), "w"), indent=1)
    for m, r in out["methods"].items():
        print(m, {k: round(v, 3) for k, v in r.items() if isinstance(v, float)}, r["misses"][:4])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-dense", action="store_true")
    main(ap.parse_args().build_dense)
