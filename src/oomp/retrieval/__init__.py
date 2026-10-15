"""Scoped retrieval contracts and lazily loaded operational engine."""

from .contracts import (
    EmbeddingSpace, GraphPath, MemoryEvidence, RetrievalMode, RetrievalRequest,
    RetrievalResponse, RetrievalTrace,
)

__all__ = [
    "EmbeddingSpace", "GraphPath", "MemoryEvidence", "RetrievalMode",
    "RetrievalRequest", "RetrievalResponse", "RetrievalTrace", "RetrievalEngine",
]


def __getattr__(name: str):
    if name == "RetrievalEngine":
        from .engine import RetrievalEngine
        return RetrievalEngine
    raise AttributeError(name)