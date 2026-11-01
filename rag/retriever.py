"""Retrieval over the real corpus. Default is BM25, the best method on rag/gold_queries.yaml (results/retrieval_eval.json).

Hybrid (BM25 + TF-IDF with Reciprocal Rank Fusion) and dense vectors stay available for comparison.

Every passage resolves to a chunk from an ingested file and carries its provenance. `retrieve` searches everything;
`evidence` only returns evidence-eligible primary documents (never summaries, sample files or duplicates).
"""
from __future__ import annotations

import gzip
import json
import os
import re
from dataclasses import asdict, dataclass, field

import numpy as np
import yaml
from scipy import sparse
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "index", "chunks.jsonl.gz")
MANIFEST = os.path.join(HERE, "knowledge_base", "manifest.yaml")
DENSE = os.path.join(HERE, "index", "dense_bge.npy")
DENSE_MODEL = "BAAI/bge-small-en-v1.5"
TOKEN = re.compile(r"[a-z0-9]+")


@dataclass
class Passage:
    chunk_id: str
    doc_id: str
    title: str
    issuer: str
    role: str
    section: str
    page_start: int
    page_end: int
    text: str
    source_path: str = ""
    sha256: str = ""
    score: float = 0.0
    cosine: float = 0.0
    evidence_eligible: bool = True


class KnowledgeBase:
    def __init__(self, cfg: dict, chunks: list[dict] | None = None, manifest: list[dict] | None = None, use_dense: bool = False):
        self.r = cfg["rag"]
        if manifest is None:
            with open(MANIFEST, encoding="utf8") as f:
                manifest = yaml.safe_load(f)
        if chunks is None:
            with gzip.open(INDEX, "rt", encoding="utf8") as f:
                chunks = [json.loads(line) for line in f]
        self.manifest = manifest
        by_id = {d["doc_id"]: d for d in manifest}
        self.passages = []
        for c in chunks:
            d = by_id[c["doc_id"]]
            self.passages.append(Passage(c["chunk_id"], c["doc_id"], d["title"], d.get("issuer", ""), d.get("role", "primary"), c.get("section", ""),
                                         c.get("page_start", 1), c.get("page_end", 1), c["text"], d.get("source_path", ""), d.get("sha256", ""),
                                         evidence_eligible=bool(d.get("evidence_eligible", True))))
        self.ingested = [d for d in manifest if d.get("chunks", 0) > 0]
        self.skipped = [d for d in manifest if d.get("chunks", 0) == 0]
        docs = [f"{p.section} {p.section} {p.text}" for p in self.passages]
        self.tfidf_vec = TfidfVectorizer(sublinear_tf=True, stop_words="english", ngram_range=(1, 2), min_df=1, token_pattern=r"[A-Za-z0-9][A-Za-z0-9\-\.]*[A-Za-z0-9]|[A-Za-z0-9]")
        self.tfidf = self.tfidf_vec.fit_transform(docs)
        self.count_vec = CountVectorizer(stop_words="english", token_pattern=r"[A-Za-z0-9][A-Za-z0-9\-\.]*[A-Za-z0-9]|[A-Za-z0-9]")
        tf = self.count_vec.fit_transform(docs).tocsc().astype(np.float32)
        dl = np.asarray(tf.sum(axis=1)).ravel()
        k1, b = 1.5, 0.75
        norm = k1 * (1 - b + b * dl / max(dl.mean(), 1.0))
        coo = tf.tocoo()
        data = coo.data * (k1 + 1) / (coo.data + norm[coo.row])
        df = np.asarray((tf > 0).sum(axis=0)).ravel()
        idf = np.log(1 + (len(docs) - df + 0.5) / (df + 0.5))
        self.bm25 = sparse.csr_matrix((data * idf[coo.col], (coo.row, coo.col)), shape=tf.shape)
        self.eligible = np.array([p.evidence_eligible for p in self.passages], bool)
        self.dense = None
        self._model = None
        if use_dense and os.path.exists(DENSE):
            self.dense = np.load(DENSE)

    def _scores(self, query: str, method: str) -> list[np.ndarray]:
        out = []
        if method in ("hybrid", "tfidf", "hybrid_dense"):
            out.append((self.tfidf @ self.tfidf_vec.transform([query]).T).toarray().ravel())
        if method in ("hybrid", "bm25", "hybrid_dense"):
            q = (self.count_vec.transform([query]) > 0).astype(np.float32)
            out.append((self.bm25 @ q.T).toarray().ravel())
        if method in ("dense", "hybrid_dense"):
            if self._model is None:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(DENSE_MODEL)
            v = self._model.encode(["Represent this sentence for searching relevant passages: " + query], normalize_embeddings=True)[0]
            out.append(self.dense @ v)
        return out

    def retrieve(self, query: str, k: int = 5, method: str = "bm25", eligible_only: bool = False, doc_ids: set | None = None) -> list[Passage]:
        if not self.passages:
            return []
        scores = self._scores(query, method)
        rrf = np.zeros(len(self.passages))
        for s in scores:
            order = np.argpartition(-s, min(500, len(s) - 1))[:500]
            order = order[np.argsort(-s[order])]
            for rank, i in enumerate(order):
                if s[i] > 0:
                    rrf[i] += 1.0 / (self.r["rrf_k"] + rank + 1)
        cos = (self.tfidf @ self.tfidf_vec.transform([query]).T).toarray().ravel()
        out, seen = [], set()
        for i in np.argsort(-rrf):
            if rrf[i] <= 0 or len(out) == k:
                break
            p = self.passages[i]
            key = p.text[:200]
            if key in seen or (eligible_only and not self.eligible[i]) or (doc_ids and p.doc_id not in doc_ids):
                continue
            seen.add(key)
            out.append(Passage(**{**asdict(p), "score": float(rrf[i]), "cosine": float(cos[i])}))
        return out

    def evidence(self, query: str, k: int = 3, must: list[str] | None = None, pool: int = 60, doc_ids: set | None = None) -> list[Passage]:
        """Passages that may count as evidence: eligible source, minimum similarity, every required pattern present."""
        out = []
        for p in self.retrieve(query, pool, eligible_only=True, doc_ids=doc_ids):
            if p.cosine >= self.r["found_min_cosine"] and all(re.search(m, p.text, re.I) for m in (must or [])):
                out.append(p)
                if len(out) == k:
                    break
        return out

    def chunk_text(self, chunk_id: str) -> str | None:
        if not hasattr(self, "_by_id"):
            self._by_id = {p.chunk_id: p for p in self.passages}
        p = self._by_id.get(chunk_id)
        return p.text if p else None


def _norm(s: str) -> str:
    return " ".join(s.split()).lower()


def verify_quote(quote: str, text: str) -> bool:
    return bool(quote.strip()) and len(quote.split()) <= 40 and _norm(quote) in _norm(text)


def best_quote(p: Passage, query: str, max_words: int = 30, must: list[str] | None = None) -> str:
    """The sentence sharing most words with the query (and containing required terms). Always a verbatim substring."""
    q = set(TOKEN.findall(query.lower()))
    sentences = re.split(r"(?<=[.!?;])\s+", p.text)

    def fit(s):
        return (sum(bool(re.search(m, s, re.I)) for m in (must or [])), len(q & set(TOKEN.findall(s.lower()))))
    words = max(sentences, key=fit).split()
    if len(words) <= max_words:
        return " ".join(words)
    # keep the window around the first required term or query word
    joined = " ".join(words)
    found = next((x for x in (re.search(m, joined, re.I) for m in (must or [])) if x), None)
    hit = len(joined[:found.start()].split()) if found else None      # required terms may span several words
    if hit is None:
        hit = next((i for i, w in enumerate(words) if w.lower().strip(",.;:") in q), 0)
    start = max(0, min(hit - 8, len(words) - max_words))
    window = " ".join(words[start:start + max_words])
    return window


@dataclass
class GroundedAnswer:
    query: str
    supported: bool
    statement: str
    quotes: list = field(default_factory=list)
    unsupported_claims: list = field(default_factory=list)


def cite(p: Passage, quote: str) -> dict:
    return {"chunk_id": p.chunk_id, "doc_id": p.doc_id, "title": p.title, "issuer": p.issuer, "section": p.section, "page": p.page_start,
            "source_path": p.source_path, "sha256": p.sha256[:16], "quote": quote, "verified_verbatim": verify_quote(quote, p.text),
            "kind": "quotation", "score": round(p.score, 4), "cosine": round(p.cosine, 3)}


def answer(kb: KnowledgeBase, query: str, must: list[str] | None = None, k: int = 3, doc_ids: set | None = None) -> GroundedAnswer:
    """Extractive, source-grounded answer: quotations only. It says so when the corpus does not support the claim."""
    quotes, seen = [], set()
    for p in kb.evidence(query, k * 3, must, doc_ids=doc_ids):
        q = best_quote(p, query, must=must)
        if q not in seen and verify_quote(q, p.text) and all(re.search(m, q, re.I) for m in (must or [])):
            seen.add(q)                        # an unverifiable or off-point quote is dropped, never shown
            quotes.append(cite(p, q))
    quotes = quotes[:k]
    if not quotes:
        return GroundedAnswer(query, False, "The knowledge base does not support this claim: no eligible passage met the evidence test.")
    return GroundedAnswer(query, True, f"{len(quotes)} verified quotation(s) follow. Any interpretation of them is OrbitFlow's, not the source's.", quotes)


def validate_citations(kb: KnowledgeBase, citations: list[dict]) -> list[dict]:
    """Return the citations that do not resolve to an ingested chunk or whose quote is not verbatim in it."""
    bad = []
    for c in citations:
        text = kb.chunk_text(c.get("chunk_id", ""))
        if text is None or not verify_quote(c.get("quote", ""), text):
            bad.append(c)
    return bad
