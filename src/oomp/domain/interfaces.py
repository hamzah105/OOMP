"""Implementation boundaries for later stages. These protocols perform no I/O."""

from __future__ import annotations

from typing import Protocol, Sequence

from .models import AuthorizedScope, MemoryEdge, MemoryEvent, MemoryNode
from oomp.retrieval.contracts import RetrievalRequest, RetrievalResponse


class EventStore(Protocol):
    def append(self, scope: AuthorizedScope, event: MemoryEvent) -> MemoryEvent: ...
    def get(self, scope: AuthorizedScope, event_id: str) -> MemoryEvent | None: ...


class MemoryStore(Protocol):
    def put(self, scope: AuthorizedScope, memory: MemoryNode) -> None: ...
    def get(self, scope: AuthorizedScope, memory_id: str) -> MemoryNode | None: ...


class GraphStore(Protocol):
    def put_edge(self, scope: AuthorizedScope, edge: MemoryEdge) -> None: ...
    def edges_for(self, scope: AuthorizedScope, node_id: str) -> Sequence[MemoryEdge]: ...


class EmbeddingProvider(Protocol):
    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class MemoryExtractor(Protocol):
    def extract(self, scope: AuthorizedScope, events: Sequence[MemoryEvent]) -> Sequence[MemoryNode]: ...


class MemoryRetriever(Protocol):
    def retrieve(self, scope: AuthorizedScope, request: RetrievalRequest) -> RetrievalResponse: ...
