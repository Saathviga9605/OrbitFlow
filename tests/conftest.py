import pytest


@pytest.fixture(scope="session")
def kb():
    from rag.retriever import KnowledgeBase
    from utils.config import load_config
    return KnowledgeBase(load_config())


@pytest.fixture(scope="session")
def rt(kb):
    """Shared scenario runtime: models, trace and knowledge base loaded once."""
    from scenarios.suite import runtime
    return runtime(kb=kb)
