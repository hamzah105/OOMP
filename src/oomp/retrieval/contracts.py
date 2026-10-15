"""Validated requests, provider identity, and evidence packets for retrieval."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Any

from pydantic import (
    BeforeValidator, Field, StrictBool, StrictInt, field_serializer,
    field_validator, model_validator,
)

from oomp.domain.enums import MemoryStatus, MemoryType, RelationshipType
from oomp.domain.models import (
    ContractModel, Identifier, RequestedScope, SourceReference, UtcDateTime,
    _check_json, _freeze_json, _nonblank, _numeric_score, _thaw_json,
)


class RetrievalMode(StrEnum):
    LEXICAL = "lexical"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class EmbeddingSpace(ContractModel):
    """A vector space is compatible only when every identity component matches."""

    provider: Identifier
    model: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    version: Identifier
    dimension: StrictInt = Field(ge=1, le=4096)


class RetrievalRequest(RequestedScope):
    query: str = Field(min_length=1, max_length=100_000)
    max_results: StrictInt = Field(default=8, ge=1, le=100)
    token_budget: StrictInt = Field(default=1200, ge=1, le=32768)
    as_of: UtcDateTime | None = None
    mode: RetrievalMode = RetrievalMode.LEXICAL
    known_at: UtcDateTime | None = None
    valid_at: UtcDateTime | None = None
    historical: StrictBool = False
    allow_degraded: StrictBool = False
    candidate_limit: StrictInt = Field(default=40, ge=1, le=200)
    min_semantic_similarity: Annotated[float, BeforeValidator(_numeric_score), Field(ge=0, le=1, allow_inf_nan=False)] = 0.2
    graph_depth: StrictInt = Field(default=1, ge=0, le=2)
    graph_nodes: StrictInt = Field(default=16, ge=1, le=100)
    graph_edges: StrictInt = Field(default=40, ge=1, le=200)
    graph_work: StrictInt = Field(default=200, ge=1, le=1000)
    graph_relationships: tuple[RelationshipType, ...] = (
        RelationshipType.RELATED_TO, RelationshipType.ABOUT, RelationshipType.SUPPORTS,
        RelationshipType.DERIVED_FROM, RelationshipType.SUPERSEDES,
        RelationshipType.CONTRADICTS, RelationshipType.DEPENDS_ON,
    )

    @field_validator("query")
    @classmethod
    def nonblank_query(cls, value: str) -> str:
        return _nonblank(value)

    @model_validator(mode="after")
    def compatible_time(self) -> RetrievalRequest:
        if self.as_of is not None and self.valid_at is not None and self.as_of != self.valid_at:
            raise ValueError("as_of and valid_at disagree")
        return self

    @property
    def effective_valid_at(self) -> UtcDateTime | None:
        return self.valid_at if self.valid_at is not None else self.as_of


class GraphPath(ContractModel):
    node_ids: tuple[Identifier, ...] = Field(min_length=1)
    edge_ids: tuple[Identifier, ...] = ()
    relationship_types: tuple[RelationshipType, ...] = ()
    edge_evidence: tuple[tuple[SourceReference, ...], ...] = ()
    edge_directions: tuple[str, ...] = ()
    edge_validity: tuple[bool | None, ...] = ()

    @model_validator(mode="after")
    def connected_shape(self) -> GraphPath:
        if len(self.edge_ids) != len(self.node_ids) - 1:
            raise ValueError("a graph path requires one edge between adjacent nodes")
        if len(self.relationship_types) != len(self.edge_ids):
            raise ValueError("relationship_types must match edge_ids")
        if self.edge_directions and (len(self.edge_directions) != len(self.edge_ids) or any(item not in {"forward", "reverse"} for item in self.edge_directions)):
            raise ValueError("edge_directions must match edge_ids and orientation")
        if self.edge_validity and len(self.edge_validity) != len(self.edge_ids):
            raise ValueError("edge_validity must match edge_ids")
        if self.edge_evidence and len(self.edge_evidence) != len(self.edge_ids):
            raise ValueError("edge_evidence must match edge_ids")
        return self


class MemoryEvidence(ContractModel):
    memory_id: Identifier
    canonical_content: str = Field(min_length=1, max_length=1_000_000)
    memory_type: MemoryType
    source_references: tuple[SourceReference, ...] = Field(min_length=1)
    source_event_ids: tuple[Identifier, ...] = ()
    retrieval_score: Annotated[float, BeforeValidator(_numeric_score), Field(allow_inf_nan=False)] | None = None
    valid_from: UtcDateTime | None = None
    valid_until: UtcDateTime | None = None
    status: MemoryStatus = MemoryStatus.ACTIVE
    temporal_status: str = Field(default="uncertain", min_length=1, max_length=64)
    selection_reasons: tuple[str, ...] = Field(default=(), max_length=16)
    graph_paths: tuple[GraphPath, ...] = ()
    metadata: Mapping[str, Any] = Field(default_factory=dict)

    @field_validator("canonical_content")
    @classmethod
    def nonblank_content(cls, value: str) -> str:
        return _nonblank(value)

    @field_validator("metadata")
    @classmethod
    def json_metadata(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        _check_json(dict(value))
        return _freeze_json(dict(value))

    @field_serializer("metadata")
    def serialize_metadata(self, value: Mapping[str, Any]) -> dict[str, Any]:
        return _thaw_json(value)

    @model_validator(mode="after")
    def chronological(self) -> MemoryEvidence:
        if self.valid_from is not None and self.valid_until is not None and self.valid_until < self.valid_from:
            raise ValueError("valid_until cannot precede valid_from")
        if self.source_event_ids and len(self.source_event_ids) != len(self.source_references):
            raise ValueError("source IDs and references must align")
        return self


class RetrievalTrace(ContractModel):
    lexical_candidates: StrictInt = Field(default=0, ge=0)
    semantic_candidates: StrictInt = Field(default=0, ge=0)
    entity_candidates: StrictInt = Field(default=0, ge=0)
    topic_candidates: StrictInt = Field(default=0, ge=0)
    graph_expanded_candidates: StrictInt = Field(default=0, ge=0)
    governed_conflict_candidates: StrictInt = Field(default=0, ge=0)
    eligible_candidates: StrictInt = Field(default=0, ge=0)
    packed_memories: StrictInt = Field(default=0, ge=0)
    budget_dropped: StrictInt = Field(default=0, ge=0)
    graph_truncated: StrictBool = False
    diversity_reordered: StrictInt = Field(default=0, ge=0)


class RetrievalResponse(ContractModel):
    retrieval_id: Identifier
    memories: tuple[MemoryEvidence, ...] = ()
    source_references: tuple[SourceReference, ...] = ()
    graph_paths: tuple[GraphPath, ...] = ()
    estimated_token_count: StrictInt = Field(default=0, ge=0)
    token_budget: StrictInt = Field(default=1200, ge=1, le=32768)
    counting_method: str = "utf8_bytes_upper_bound_v1"
    context_packet: str = ""
    retrieval_mode: RetrievalMode = RetrievalMode.LEXICAL
    degraded: StrictBool = False
    warnings: tuple[str, ...] = ()
    retrieval_trace: RetrievalTrace = Field(default_factory=RetrievalTrace)