"""Validated structural graph, topic, and historical inspection values."""

from __future__ import annotations

from pydantic import Field, StrictInt, field_validator, model_validator

from .enums import MemoryStatus
from .models import (
    ContractModel, Identifier, MemoryEdge, RequestedScope, SourceReference,
    UtcDateTime, _nonblank,
)


class EdgeEvidence(ContractModel):
    event_id: Identifier
    source_reference: SourceReference
    recorded_at: UtcDateTime | None = None


class EdgeRecord(ContractModel):
    edge: MemoryEdge
    recorded_at: UtcDateTime
    recorded_by: Identifier
    evidence: tuple[EdgeEvidence, ...] = Field(min_length=1, max_length=1000)
    reason: str | None = Field(default=None, max_length=1024)
    policy_version: Identifier | None = None

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value: str | None) -> str | None:
        return None if value is None else _nonblank(value)

    @model_validator(mode="after")
    def aligned_evidence(self) -> EdgeRecord:
        ids = tuple(item.event_id for item in self.evidence)
        if ids != self.edge.source_event_ids or len(ids) != len(set(ids)):
            raise ValueError("edge evidence must match source event IDs in order")
        return self


class EdgeCursor(RequestedScope):
    recorded_at: UtcDateTime
    edge_id: Identifier


class EdgePage(ContractModel):
    edges: tuple[EdgeRecord, ...] = ()
    next_cursor: EdgeCursor | None = None


class TraversalResult(ContractModel):
    start_node_id: Identifier
    node_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=500)
    edges: tuple[EdgeRecord, ...] = Field(default=(), max_length=2000)
    truncated: bool = False


class TopicRecord(ContractModel):
    topic_id: Identifier
    tenant_id: Identifier
    namespace: Identifier
    name: str = Field(min_length=1, max_length=512)
    parent_id: Identifier | None = None
    recorded_at: UtcDateTime

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        return _nonblank(value)


class TopicMembership(ContractModel):
    topic_id: Identifier
    memory_id: Identifier
    recorded_at: UtcDateTime


class TopicTreeNode(ContractModel):
    topic: TopicRecord
    depth: StrictInt = Field(ge=0, le=10)
    memory_ids: tuple[Identifier, ...] = Field(default=(), max_length=1000)


class TopicTree(ContractModel):
    root_topic_id: Identifier
    nodes: tuple[TopicTreeNode, ...] = Field(default=(), max_length=500)
    truncated: bool = False


class TemporalQuery(ContractModel):
    valid_at: UtcDateTime | None = None
    known_at: UtcDateTime | None = None


class MemoryState(ContractModel):
    memory_id: Identifier
    known: bool | None
    valid: bool | None
    effective_status: MemoryStatus | None = None
    recorded_at: UtcDateTime | None = None
    superseded_by: tuple[Identifier, ...] = Field(default=(), max_length=1000)
    source_event_ids: tuple[Identifier, ...] = Field(default=(), max_length=1000)
    evidence: tuple[EdgeEvidence, ...] = Field(default=(), max_length=1000)
    legacy_recording_unknown: bool = False

    @model_validator(mode="after")
    def aligned_evidence(self) -> MemoryState:
        if tuple(item.event_id for item in self.evidence) != self.source_event_ids:
            raise ValueError("memory evidence must match source event IDs")
        return self


class GraphHistory(ContractModel):
    memory: MemoryState
    incoming_edges: tuple[EdgeRecord, ...] = Field(default=(), max_length=100)
    outgoing_edges: tuple[EdgeRecord, ...] = Field(default=(), max_length=100)