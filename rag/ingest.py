"""Ingest the real corpus (CrashingGuru/ITUAIReadiness InputDocs) into a provenance-preserving chunk index.

    python -m rag.ingest [--limit N]
Reads rag/knowledge_base/_source (see scripts/fetch_kb.py); writes rag/knowledge_base/manifest.yaml and rag/index/chunks.jsonl.gz.
Chunk text is verbatim source text with whitespace normalised. Files that fail extraction are reported, never replaced.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import re

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "knowledge_base", "_source")
DOCS = os.path.join(SOURCE, "simulation", "server", "knowledge", "InputDocs")
MANIFEST = os.path.join(HERE, "knowledge_base", "manifest.yaml")
INDEX = os.path.join(HERE, "index", "chunks.jsonl.gz")
REPO = "https://github.com/CrashingGuru/ITUAIReadiness"
COMMIT = "84010da9e9c443afcceeccb86d1700a662223395"
LICENCE = "MIT (repository licence, Copyright (c) 2026 Vishnu Ram OV); individual documents keep their publishers' terms"

HEADING = re.compile(r"^(?!Chapter \d+$)((\d+(\.\d+){0,3}\.?|[IVX]+\.|[A-Z]\.\d*)\s+[A-Z][^.]{2,90}|(Article|Section|Chapter|Clause|Annex|Appendix|Pillar|Principle)\s+[\dIVXA-Z]+\b.{0,80}|[A-Z][A-Z &,:/\-]{6,80})$")
ISSUERS = [("ITU-T", "ITU-T"), ("ITU", "ITU"), ("AI_Ready", "ITU"), ("KSA.T", "ITU"), ("WAIC", "ITU"), ("Innovate-for", "ITU"), ("UNCTAD", "UNCTAD"), ("Technology and Innovation", "UNCTAD"),
           ("WTO", "WTO"), ("WHO", "WHO"), ("UN_", "United Nations"), ("Governing AI", "United Nations"), ("G7", "G7"), ("G20", "G20"), ("GPAI", "GPAI"), ("ASEAN", "ASEAN"),
           ("African_Union", "African Union"), ("Smart_Africa", "Smart Africa"), ("DCO", "Digital Cooperation Organization"), ("CCIA", "CCIA"), ("PAI", "Partnership on AI"),
           ("Turing", "The Alan Turing Institute"), ("Digital Progress", "World Bank"), ("CGEE", "CGEE (Brazil)"), ("AI for the Good of All", "not stated in repository index"), ("List_of_natl", "ITU AI Governance Report list"),
           ("Kigali", "Global AI Summit on Africa"), ("Windhoek", "UNESCO / Southern Africa statement"), ("MERCOSUR", "MERCOSUR"), ("Santiago", "Latin American declaration signatories"), ("Montevideo", "Montevideo declaration signatories"), ("SEE_Turkiye", "South East Europe and Turkiye signatories"), ("France_", "Government of France coalition"), ("AI Impact Summit", "India AI Impact Summit")] + [
    (c, f"Government of {n}") for c, n in (("USA", "the United States"), ("US_AI", "the United States"), ("UK_", "the United Kingdom"), ("China", "China"), ("Japan", "Japan"), ("India", "India"), ("Singapore", "Singapore"), ("Saudi", "Saudi Arabia"), ("Egypt", "Egypt"), ("Kenya", "Kenya"), ("Zambia", "Zambia"), ("Brazil", "Brazil"), ("Korea", "the Republic of Korea"), ("Peru", "Peru"), ("Estonia", "Estonia"), ("Spain", "Spain"), ("Turkiye", "Turkiye"), ("Rwanda", "Rwanda"), ("Nigeria", "Nigeria"))]
STOP_EVIDENCE = re.compile(r"^(sample_|.*_summary\.txt$)", re.I)


def inputs_table() -> dict:
    """filename -> (type, description), exactly as the source repository's Inputs.md states them."""
    out = {}
    with open(os.path.join(DOCS, "Inputs.md"), encoding="utf8") as f:
        for line in f:
            m = re.match(r"\|\s*\d+\s*\|\s*`([^`]+)`\s*\|\s*`?([^|`]*)`?\s*\|\s*(.*?)\s*\|\s*$", line)
            if m:
                out[m.group(1)] = (m.group(2).strip(), m.group(3).replace("**", "").strip())
    return out


def extract_pages(path: str) -> list[tuple[int, str]]:
    low = path.lower()
    if low.endswith(".pdf"):
        try:
            import pypdfium2
            d = pypdfium2.PdfDocument(path)
            return [(i + 1, d[i].get_textpage().get_text_range()) for i in range(len(d))]
        except Exception:                                         # some PDFs only open with the second parser
            import pypdf
            r = pypdf.PdfReader(path)
            return [(i + 1, r.pages[i].extract_text() or "") for i in range(len(r.pages))]
    if low.endswith(".docx"):
        import docx
        doc = docx.Document(path)
        parts = [p.text for p in doc.paragraphs]
        for t in doc.tables:
            parts += [" | ".join(c.text.strip() for c in r.cells) for r in t.rows]
        return [(1, "\n".join(parts))]
    with open(path, encoding="utf8", errors="replace") as f:
        return [(1, f.read())]


SENT = re.compile(r"(?<=[.;:!?])\s+(?=[\"'(A-Z0-9])")


def clean(line: str) -> str:
    return " ".join(line.replace("­", "").replace("￾", "").replace("\x02", "").split())


def chunk_pages(pages, words=180, overlap=30) -> list[dict]:
    """Greedy sentence packing inside a section: a clause is never cut mid-sentence unless it alone exceeds `words`."""
    chunks, section, buf, n, start = [], "", [], 0, 1

    def flush(keep=False):
        nonlocal buf, n, start
        if buf:
            chunks.append({"section": section, "page_start": start, "page_end": page, "text": " ".join(buf)})
        if keep and buf:
            tail, c = [], 0
            for s in reversed(buf):
                c += len(s.split())
                tail.insert(0, s)
                if c >= overlap:
                    break
            buf, n = tail, sum(len(s.split()) for s in tail)
            start = page
        else:
            buf, n = [], 0

    page = 1
    for page, text in pages:
        para: list[str] = []
        lines = [clean(x) for x in text.splitlines()]

        def add_para():
            nonlocal n, start
            if not para:
                return
            for s in SENT.split(" ".join(para)):
                w = s.split()
                for i in range(0, max(len(w), 1), words):         # only pathological run-ons are cut
                    piece = " ".join(w[i:i + words])
                    if not piece:
                        continue
                    if n + len(piece.split()) > words and buf:
                        flush(keep=True)
                    if not buf:
                        start = page
                    buf.append(piece)
                    n += len(piece.split())
            para.clear()

        for ln in lines:
            if not ln:
                add_para()
            elif HEADING.match(ln) and len(ln.split()) <= 14:
                add_para()
                flush()
                section = ln
            else:
                para.append(ln)
        add_para()
    flush()
    return [c for c in chunks if len(c["text"].split()) >= 8]


def shingles(text: str) -> set:
    w = re.findall(r"[a-z0-9]+", text.lower())[:60000]
    return {hash(" ".join(w[i:i + 6])) for i in range(0, max(len(w) - 6, 0), 3)}


def main(limit=None):
    table = inputs_table()
    files = []
    for root, _, names in os.walk(DOCS):
        files += [os.path.join(root, n) for n in names if n != "Inputs.md"]
    files.sort()
    if limit:
        files = files[:limit]
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    manifest, all_chunks, sigs, shas = [], [], {}, {}
    for path in files:
        rel = os.path.relpath(path, DOCS).replace("\\", "/")
        name = os.path.basename(path)
        raw = open(path, "rb").read()
        sha = hashlib.sha256(raw).hexdigest()
        typ, desc = table.get(name, ("unlisted", ""))
        issuer = next((v for k, v in ISSUERS if k.lower() in name.lower()), "")
        year = re.search(r"(19|20)\d\d", f"{desc} {name}")
        role = "secondary_summary" if STOP_EVIDENCE.match(name) else "primary"
        e = {"doc_id": re.sub(r"[^a-z0-9]+", "_", os.path.splitext(name)[0].lower()).strip("_"), "filename": name,
             "title": desc.split(". ")[0] if desc else os.path.splitext(name)[0].replace("_", " "),
             "description": desc, "doc_type": typ, "category": rel.split("/")[0], "issuer": issuer or "not stated in repository index",
             "issuer_basis": "inferred from filename" if issuer else "none", "year": int(year.group()) if year else None,
             "year_basis": "first year in repository index or filename" if year else "none", "source_repository": REPO, "source_commit": COMMIT,
             "source_path": f"simulation/server/knowledge/InputDocs/{rel}", "licence": LICENCE, "role": role, "ingested_at": now,
             "sha256": sha, "bytes": len(raw), "verification": "machine-ingested; not human-verified"}
        try:
            pages = extract_pages(path)
            chars = sum(len(t) for _, t in pages)
            chunks = chunk_pages(pages)
            low = sum(len(t.strip()) < 40 for _, t in pages)
            e.update(pages=len(pages), chars=chars, chunks=len(chunks), low_text_pages=low,
                     extraction="failed_no_text" if chars < 200 else ("partial_low_text_pages" if low > 0.3 * len(pages) else "ok"))
            for i, c in enumerate(chunks):
                all_chunks.append({"chunk_id": f"{e['doc_id']}#{i}", "doc_id": e["doc_id"], **c})
            sigs[e["doc_id"]] = shingles(" ".join(t for _, t in pages))
        except Exception as ex:                                   # corrupted files are reported, never faked
            e.update(pages=0, chars=0, chunks=0, low_text_pages=0, extraction=f"failed: {type(ex).__name__}: {ex}"[:200])
        e["duplicate_of"] = shas.get(sha)
        shas.setdefault(sha, e["doc_id"])
        manifest.append(e)
        print(f"{e['extraction'][:12]:12} {e['pages']:5}p {e['chunks']:5}c {name}", flush=True)
    ids = list(sigs)
    for e in manifest:
        a = sigs.get(e["doc_id"])
        overlaps = []
        for b in ids:
            if a and b != e["doc_id"] and sigs[b]:
                cover = len(a & sigs[b]) / max(len(a), 1)
                if cover > 0.3:
                    overlaps.append({"doc_id": b, "share_of_this_doc": round(cover, 2)})
        e["overlaps"] = overlaps
    for e in manifest:                                            # a contained copy never counts twice as evidence
        e["evidence_eligible"] = e["role"] == "primary" and e["chunks"] > 0 and not e["duplicate_of"]
    os.makedirs(os.path.dirname(INDEX), exist_ok=True)
    with gzip.open(INDEX, "wt", encoding="utf8") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    with open(MANIFEST, "w", encoding="utf8") as f:
        f.write("# GENERATED by rag/ingest.py from the actual repository contents. Do not edit by hand.\n")
        yaml.safe_dump(manifest, f, sort_keys=False, allow_unicode=True, width=160)
    print(len(manifest), "files", len(all_chunks), "chunks", sum(e["pages"] for e in manifest), "pages")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    main(ap.parse_args().limit)
