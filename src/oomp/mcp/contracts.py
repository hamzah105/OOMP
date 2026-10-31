"""Bounded MCP-facing values. Authority fields are deliberately absent from inputs."""
from __future__ import annotations

from copy import deepcopy
from typing import Literal
from pydantic import Field, StrictBool, StrictInt, create_model, field_validator, model_validator

from oomp.domain.enums import EventType, RelationshipType
from oomp.domain.models import ContractModel, Identifier, SourceReference, UtcDateTime, _nonblank
from oomp.retrieval.contracts import RetrievalRequest, RetrievalResponse, MemoryEvidence


class _RetrieveBase(ContractModel):
    query: str = Field(min_length=1, max_length=4096)

    @field_validator("query")
    @classmethod
    def nonblank(cls, value):
        return _nonblank(value)

    @model_validator(mode="after")
    def compatible_time(self):
        if self.as_of is not None and self.valid_at is not None and self.as_of != self.valid_at:
            raise ValueError("as_of and valid_at disagree")
        return self


# Retain the Stage 5 field constraints/defaults without publishing requested scope.
_fields = {
    name: (field.annotation, deepcopy(field))
    for name, field in RetrievalRequest.model_fields.items()
    if name not in {"tenant_id", "namespace", "query"}
}
_fields.update({
    "max_results": (StrictInt, Field(default=8, ge=1, le=20)),
    "graph_nodes": (StrictInt, Field(default=16, ge=1, le=32)),
    "graph_edges": (StrictInt, Field(default=40, ge=1, le=64)),
    "graph_work": (StrictInt, Field(default=200, ge=1, le=400)),
    "graph_relationships": (
        tuple[RelationshipType, ...],
        Field(default=RetrievalRequest.model_fields["graph_relationships"].default, max_length=9),
    ),
})
RetrieveArguments = create_model("RetrieveArguments", __base__=_RetrieveBase,
                                 __module__=__name__, **_fields)


class RetrieveResult(RetrievalResponse):
    source_data_untrusted: Literal[True] = True
    budget_scope: Literal["context_packet_only"] = "context_packet_only"


class ExpandArguments(ContractModel):
    memory_id: Identifier
    max_depth: StrictInt = Field(default=1, ge=0, le=2)
    max_nodes: StrictInt = Field(default=16, ge=1, le=32)
    allowed_relationships: tuple[RelationshipType, ...] = Field(
        default=tuple(RelationshipType), max_length=9,
    )
    known_at: UtcDateTime | None = None
    valid_at: UtcDateTime | None = None
    historical: StrictBool = False


class ExpandedEdge(ContractModel):
    edge_id: Identifier
    source_node_id: Identifier
    target_node_id: Identifier
    relationship_type: RelationshipType
    source_event_ids: tuple[Identifier, ...]
    source_references: tuple[SourceReference, ...]
    recorded_at: UtcDateTime
    valid_from: UtcDateTime | None = None
    valid_until: UtcDateTime | None = None
    valid: bool | None = None


class ExpandResult(ContractModel):
    memory_id: Identifier
    memories: tuple[MemoryEvidence, ...] = Field(max_length=32)
    edges: tuple[ExpandedEdge, ...] = Field(max_length=64)
    truncated: StrictBool
    source_data_untrusted: Literal[True] = True
    operation: Literal["structural_expansion"] = "structural_expansion"


class SourceArguments(ContractModel):
    memory_id: Identifier
    event_id: Identifier | None = None
    include_content: StrictBool = False
    known_at: UtcDateTime | None = None
    limit: StrictInt = Field(default=8, ge=1, le=32)
    after_event_id: Identifier | None = None


class SourceEvidence(ContractModel):
    event_id: Identifier
    event_type: EventType
    source_type: str
    source_reference: SourceReference
    occurred_at: UtcDateTime
    ingested_at: UtcDateTime
    content: str | None = None


class SourceResult(ContractModel):
    memory_id: Identifier
    sources: tuple[SourceEvidence, ...] = Field(max_length=32)
    next_event_id: Identifier | None = None
    source_data_untrusted: Literal[True] = True


class StatusArguments(ContractModel):
    pass


class IndexInformation(ContractModel):
    canonical_count: StrictInt
    lexical_count: StrictInt
    lexical_stale: StrictInt
    compatible_embeddings: StrictInt | None = None
    stale_embeddings: StrictInt | None = None


class EmbeddingIdentity(ContractModel):
    provider: str
    model: str
    version: str
    dimension: StrictInt


class QueueInformation(ContractModel):
    queued: StrictInt
    running: StrictInt
    retry_wait: StrictInt
    completed: StrictInt
    failed: StrictInt
    cancelled: StrictInt
    outbox_pending: StrictInt
    events_pending_extraction: StrictInt
    outstanding_review_proposals: StrictInt


class StatusResult(ContractModel):
    # Accept the historical v5 response when reading old server results. New
    # servers explicitly report their admitted schema; no future version is
    # silently accepted by this wire contract.
    schema_version: Literal[5, 6] = 6
    read_only: StrictBool
    capabilities: tuple[str, ...]
    retrieval_modes: tuple[str, ...]
    embedding_space: EmbeddingIdentity | None = None
    index: IndexInformation
    jobs: QueueInformation
    mind_worker_started_by_server: Literal[False] = False
    mind_worker_operation: Literal["explicit_separate_process"] = "explicit_separate_process"


class ApprovalProof(ContractModel):
    issued_at: UtcDateTime
    expires_at: UtcDateTime
    nonce: Identifier
    signature: str = Field(pattern=r"^[a-f0-9]{64}$")


class IngestPayload(ContractModel):
    event_id: Identifier
    idempotency_key: Identifier
    event_type: EventType = EventType.USER_MESSAGE
    content: str = Field(min_length=1, max_length=16384)
    source_reference: SourceReference
    occurred_at: UtcDateTime

    @field_validator("content")
    @classmethod
    def nonblank_content(cls, value):
        return _nonblank(value)


class IngestArguments(IngestPayload):
    approval: ApprovalProof


class IngestResult(ContractModel):
    event_id: Identifier
    acceptance: Literal["durably_stored"] = "durably_stored"
    outbox_state: Literal["pending", "dispatched"]
    latest_extraction_job_status: str | None = None
    worker_started_by_request: Literal[False] = False
