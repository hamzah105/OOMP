"""Input and output contracts for future memory retrieval; no retrieval engine."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any

from pydantic import BeforeValidator, Field, StrictInt, field_serializer, field_validator, model_validator

from oomp.domain.enums import MemoryStatus, MemoryType, RelationshipType
from oomp.domain.models import ContractModel, Identifier, RequestedScope, SourceReference, UtcDateTime, _check_json, _freeze_json, _nonblank, _numeric_score, _thaw_json


class RetrievalRequest(RequestedScope):
    query: str = Field(min_length=1, max_length=100_000)
    max_results: StrictInt = Field(default=8, ge=1, le=100)
    token_budget: StrictInt = Field(default=1200, ge=1, le=32768)
    as_of: UtcDateTime | None = None

    @field_validator("query")
    @classmethod
    def nonblank_query(cls, value: str) -> str:
        return _nonblank(value)


class GraphPath(ContractModel):
    node_ids: tuple[Identifier, ...] = Field(min_length=1)
    edge_ids: tuple[Identifier, ...] = ()
    relationship_types: tuple[RelationshipType, ...] = ()

    @model_validator(mode="after")
    def connected_shape(self) -> GraphPath:
        if len(self.edge_ids) != len(self.node_ids) - 1:
            raise ValueError("a graph path requires one edge between adjacent nodes")
        if len(self.relationship_types) != len(self.edge_ids):
            raise ValueError("relationship_types must match edge_ids")
        return self


class MemoryEvidence(ContractModel):
    memory_id: Identifier
    canonical_content: str = Field(min_length=1, max_length=1_000_000)
    memory_type: MemoryType
    source_references: tuple[SourceReference, ...] = Field(min_length=1)
    retrieval_score: Annotated[float, BeforeValidator(_numeric_score), Field(allow_inf_nan=False)] | None = None
    valid_from: UtcDateTime | None = None
    valid_until: UtcDateTime | None = None
    status: MemoryStatus = MemoryStatus.ACTIVE
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
        return self


class RetrievalResponse(ContractModel):
    retrieval_id: Identifier
    memories: tuple[MemoryEvidence, ...] = ()
    source_references: tuple[SourceReference, ...] = ()
    graph_paths: tuple[GraphPath, ...] = ()
    estimated_token_count: StrictInt = Field(default=0, ge=0)
