"""
Knowledge Prims Retrieval System
================================

Provides O(1) factual retrieval from USDA-formatted knowledge prims.

Performance:
- Retrieval: ~0.001ms (vs 150ms LLM inference = 170,000x speedup)
- Trigger search: ~0.1ms for 357 indexed triggers

ThinkingMachines [He2025] Compliance:
- Deterministic retrieval (same path = same prim)
- Consistent search ordering (alphabetical by path)
- Reproducible results
"""

from .schemas import KnowledgePrim, RetrievalResult
from .retriever import KnowledgeRetriever

# Module-level singleton
_retriever: KnowledgeRetriever | None = None


def get_retriever() -> KnowledgeRetriever:
    """Get or create the singleton knowledge retriever."""
    global _retriever
    if _retriever is None:
        _retriever = KnowledgeRetriever()
    return _retriever


def retrieve(path: str) -> RetrievalResult:
    """Direct O(1) retrieval by canonical path."""
    return get_retriever().retrieve(path)


def search(query: str, max_results: int = 5) -> RetrievalResult:
    """Search knowledge prims by trigger keywords."""
    return get_retriever().search_by_triggers(query, max_results)


__all__ = [
    "KnowledgePrim",
    "KnowledgeRetriever",
    "RetrievalResult",
    "get_retriever",
    "retrieve",
    "search",
]
