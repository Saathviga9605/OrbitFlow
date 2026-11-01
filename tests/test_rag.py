"""Knowledge base: real-corpus provenance plus toy-fixture behaviour. Fixtures are labelled synthetic and only used here."""
import glob
import hashlib
import os

import pytest

from rag.ingest import DOCS, chunk_pages, extract_pages
from rag.retriever import KnowledgeBase, answer, best_quote, cite, validate_citations, verify_quote
from utils.config import load_config

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "kb")
CFG = load_config()
KB = KnowledgeBase(CFG)


@pytest.fixture(scope="module")
def toy():
    man, chunks = [], []
    for f in sorted(glob.glob(os.path.join(FIX, "*.md"))):
        did = os.path.basename(f)[:-3]
        cs = chunk_pages(extract_pages(f))
        man.append({"doc_id": did, "title": did, "chunks": len(cs), "evidence_eligible": True})
        chunks += [{"chunk_id": f"{did}#{i}", "doc_id": did, **c} for i, c in enumerate(cs)]
    return KnowledgeBase(CFG, chunks=chunks, manifest=man)


def test_corpus_is_the_real_repository_with_full_provenance():
    assert len(KB.manifest) == 67 and len(KB.ingested) >= 60
    assert not any(d["doc_id"].startswith("sim_") for d in KB.manifest)
    for d in KB.manifest:
        assert d["source_repository"].endswith("ITUAIReadiness") and len(d["sha256"]) == 64 and d["source_path"].endswith(d["filename"])


def test_checksums_match_source_files():
    if not os.path.isdir(DOCS):
        pytest.skip("source not fetched")
    d = next(x for x in KB.manifest if x["doc_id"] == "t_rec_y_3172_201906_i_pdf_e")
    path = os.path.join(DOCS, "AI_Use_Cases", d["filename"])
    assert hashlib.sha256(open(path, "rb").read()).hexdigest() == d["sha256"]


def test_summaries_and_sample_files_are_never_evidence():
    roles = {d["filename"]: d["evidence_eligible"] for d in KB.manifest}
    assert not roles["sample_national_strategy_saudi.txt"] and not roles["EU_AI_Act_summary.txt"] and not roles["ITU-T_Y.3172_summary.txt"]
    ids = {d["doc_id"] for d in KB.manifest if not d["evidence_eligible"]}
    assert not {p.doc_id for p in KB.evidence("artificial intelligence national strategy", 50)} & ids


def test_failed_documents_are_reported_not_faked():
    failed = {d["filename"] for d in KB.skipped}
    assert all(d["extraction"].startswith("failed") for d in KB.skipped)
    assert not {p.doc_id for p in KB.passages} & {d["doc_id"] for d in KB.skipped} and failed


def test_duplicate_detection_flags_contained_chapters():
    d = next(x for x in KB.manifest if x["doc_id"] == "unctad_tir2025_ch3_ai_opportunities")
    assert any(o["doc_id"] == "technology_and_innovation_report_2025" for o in d["overlaps"])


def test_sections_and_pages_are_preserved():
    pages = [(1, "1 Scope\nThis applies to networks of many kinds. It has several limits.\n\n2 Definitions\nA term means a thing here in this text.")]
    c = chunk_pages(pages)
    assert [x["section"] for x in c] == ["1 Scope", "2 Definitions"]
    p3172 = [p for p in KB.passages if p.doc_id == "t_rec_y_3172_201906_i_pdf_e" and "P (policy)" in p.text]
    assert p3172 and p3172[0].page_start > 1


def test_verbatim_quote_validation():
    assert verify_quote("Beams   illuminating\nlisted", "Beams illuminating listed cells")
    assert not verify_quote("Beams illuminating every cell", "Beams illuminating listed cells")
    assert not verify_quote("", "anything")


def test_quotes_are_substrings_of_their_chunk(toy):
    for p in toy.retrieve("emergency priority", 3):
        assert verify_quote(best_quote(p, "emergency priority"), p.text)


def test_citation_validator_rejects_invented_clause():
    p = KB.retrieve("policy node", 1, doc_ids={"t_rec_y_3172_201906_i_pdf_e"})[0]
    good = cite(p, best_quote(p, "policy node"))
    fake = {**good, "quote": "Operators shall cap beam power at 22 W."}
    assert validate_citations(KB, [good]) == [] and validate_citations(KB, [fake]) == [fake]
    assert validate_citations(KB, [{**good, "chunk_id": "nope#1"}])


def test_unsupported_claim_says_so():
    a = answer(KB, "Is emergency traffic exempt from a cross-border beam power limit?", ["exempt|waive|derogat", "power limit|power cap|transmit power|beam power"])
    assert not a.supported and not a.quotes and "does not support" in a.statement


def test_supported_answer_cites_y3172():
    a = answer(KB, "What does the policy node do?", ["polic"], doc_ids={"t_rec_y_3172_201906_i_pdf_e"})
    assert a.supported and all(q["verified_verbatim"] and q["page"] >= 1 and q["kind"] == "quotation" for q in a.quotes)
