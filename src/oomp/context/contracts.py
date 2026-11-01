"""Versioned context values, separate from the legacy retrieval wire contract."""
from __future__ import annotations

from collections.abc import Mapping
import json
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, StrictBool, StrictInt, field_serializer, field_validator, model_validator

from oomp.domain.enums import RelationshipType
from oomp.domain.models import (
    ContractModel, Identifier, RequestedScope, SourceReference, UtcDateTime,
    _freeze_json, _nonblank, _numeric_score, _thaw_json,
)
from oomp.retrieval.contracts import RetrievalMode

CONTEXT_VERSION = "oomp.context.v1"
COUNTING_METHOD = "utf8_bytes_upper_bound_v1"
Text = Annotated[str, Field(strict=True, min_length=1, max_length=4096)]
Anchor = Annotated[str, Field(strict=True, min_length=1, max_length=160)]
Count = Annotated[int, Field(strict=True, ge=0)]
Score = Annotated[float, BeforeValidator(_numeric_score), Field(allow_inf_nan=False)]
TopicHint = Literal["projects", "relocation", "preferences", "identity-claims", "sensitive-discussion", "conversation"]


class RetrievalIntent(StrEnum):
    FACTUAL_RECALL = "factual_recall"
    EPISODIC_RECALL = "episodic_recall"
    PLAN_FOLLOWUP = "plan_followup"
    HISTORICAL_CORRECTION = "historical_correction"
    ENTITY_LOOKUP = "entity_lookup"
    CURRENT_SESSION_ONLY = "current_session_only"
    UNCERTAIN_RECALL = "uncertain_recall"


class ContextStatus(StrEnum):
    FOUND = "found_relevant_evidence"
    NOT_FOUND = "no_relevant_evidence"
    INDEX_INCOMPLETE = "index_incomplete"
    COVERAGE_UNKNOWN = "coverage_unknown"
    UNAVAILABLE = "unavailable"
    UNAUTHORIZED = "unauthorized"
    UNCERTAIN = "candidate_uncertain"
    BUDGET_EXCLUDED = "budget_excluded"


class EvidenceResolution(StrEnum):
    OBJECT_SNAPSHOT = "object_snapshot"
    EPISODE_SUMMARY = "episode_summary"
    CANONICAL_FACT = "canonical_fact"
    SOURCE_EVIDENCE = "source_evidence"


class ContextArgumentsFields(ContractModel):
    """Scope-free opt-in inputs; recent turns are hints, never source authority."""

    query: Text
    recent_user_turns: tuple[Text, ...] = Field(default=(), max_length=2)
    anchors: tuple[Anchor, ...] = Field(default=(), max_length=4)
    token_budget: StrictInt = Field(default=1200, ge=1, le=32768)
    max_results: StrictInt = Field(default=8, ge=1, le=20)
    mode: RetrievalMode = RetrievalMode.LEXICAL
    allow_degraded: StrictBool = False
    candidate_limit: StrictInt = Field(default=40, ge=1, le=200)
    min_semantic_similarity: Annotated[float, BeforeValidator(_numeric_score), Field(ge=0, le=1, allow_inf_nan=False)] = .2
    as_of: UtcDateTime | None = None
    known_at: UtcDateTime | None = None
    valid_at: UtcDateTime | None = None
    historical: StrictBool = False
    graph_depth: StrictInt = Field(default=0, ge=0, le=2)
    graph_nodes: StrictInt = Field(default=16, ge=1, le=32)
    graph_edges: StrictInt = Field(default=40, ge=1, le=64)
    graph_work: StrictInt = Field(default=200, ge=1, le=400)
    graph_relationships: tuple[RelationshipType, ...] = Field(default=(
        RelationshipType.RELATED_TO, RelationshipType.ABOUT, RelationshipType.SUPPORTS,
        RelationshipType.DERIVED_FROM, RelationshipType.SUPERSEDES,
        RelationshipType.CONTRADICTS, RelationshipType.DEPENDS_ON,
    ), max_length=9)
    include_source_content: StrictBool = False
    explain: StrictBool = False

    @field_validator("query")
    @classmethod
    def nonblank_query(cls, value):
        return _nonblank(value)

    @field_validator("recent_user_turns", "anchors")
    @classmethod
    def bounded_nonblank_values(cls, values):
        if any(not value.strip() or "\0" in value for value in values):
            raise ValueError("context hints must be nonblank text")
        return values

    @model_validator(mode="after")
    def context_limits(self):
        if sum(len(value.encode("utf-8")) for value in self.recent_user_turns) > 2048:
            raise ValueError("recent context exceeds 2048 UTF-8 bytes")
        if self.as_of is not None and self.valid_at is not None and self.as_of != self.valid_at:
            raise ValueError("as_of and valid_at disagree")
        return self

    @property
    def effective_valid_at(self):
        return self.valid_at if self.valid_at is not None else self.as_of


class ContextRequest(ContextArgumentsFields, RequestedScope):
    """Local request selectors; the separate AuthorizedScope remains authority."""


class QueryPlan(ContractModel):
    retrieval_intent: RetrievalIntent
    query_variants: tuple[Text, ...] = Field(default=(), max_length=3)
    anchors: tuple[Anchor, ...] = Field(default=(), max_length=4)
    focus_terms: tuple[Annotated[str, Field(min_length=1, max_length=128)], ...] = Field(default=(), max_length=32)
    topic_hints: tuple[TopicHint, ...] = Field(default=(), max_length=6)
    needs_clarification: StrictBool = False
    search_allowed: StrictBool = True
    reasons: tuple[Identifier, ...] = Field(default=(), max_length=16)


class ContextSource(ContractModel):
    memory_id: Identifier
    event_id: Identifier
    source_reference: SourceReference
    span_start: StrictInt = Field(ge=0, le=1_000_000)
    span_end: StrictInt = Field(ge=1, le=1_000_000)
    quote: str | None = Field(default=None, max_length=1_000_000)

    @model_validator(mode="after")
    def exact_span_shape(self):
        if self.span_end <= self.span_start:
            raise ValueError("source span must be nonempty")
        if self.quote is not None and len(self.quote) != self.span_end - self.span_start:
            raise ValueError("source quote does not match span length")
        return self


class ContextEvidence(ContractModel):
    unit_id: Identifier
    resolution: EvidenceResolution
    content: str = Field(min_length=1, max_length=1_000_000)
    memory_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=16)
    source_proofs: tuple[ContextSource, ...] = Field(min_length=1, max_length=16)
    object_ids: tuple[Identifier, ...] = Field(default=(), max_length=8)
    revision_id: Identifier | None = None
    source_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    assertion_kinds: tuple[Annotated[str, Field(min_length=1, max_length=64)], ...] = Field(default=(), max_length=16)
    temporal_status: str = Field(default="uncertain", min_length=1, max_length=64)
    selection_reasons: tuple[Identifier, ...] = Field(default=(), max_length=16)
    retrieval_score: Score | None = None
    derived: StrictBool = False
    uncertain: StrictBool = True

    @model_validator(mode="after")
    def proof_alignment(self):
        if set(self.memory_ids) != {proof.memory_id for proof in self.source_proofs}:
            raise ValueError("context memory identities and proofs disagree")
        if len(set(self.memory_ids)) != len(self.memory_ids):
            raise ValueError("duplicate context memory identity")
        pairs = {(proof.memory_id, proof.event_id, proof.span_start, proof.span_end) for proof in self.source_proofs}
        if len(pairs) != len(self.source_proofs):
            raise ValueError("duplicate context source proof")
        return self


class ContextResponse(ContractModel):
    context_contract_version: Literal["oomp.context.v1"] = CONTEXT_VERSION
    retrieval_intent: RetrievalIntent
    retrieval_status: ContextStatus
    evidence_packets: tuple[ContextEvidence, ...] = Field(default=(), max_length=20)
    source_references: tuple[SourceReference, ...] = Field(default=(), max_length=320)
    context_packet: str = Field(default="", max_length=32768)
    selected_context_bytes: StrictInt = Field(default=0, ge=0, le=32768)
    token_budget: StrictInt = Field(default=1200, ge=1, le=32768)
    counting_method: Literal["utf8_bytes_upper_bound_v1"] = COUNTING_METHOD
    degraded: StrictBool = False
    reasons: tuple[Identifier, ...] = Field(default=(), max_length=32)
    coverage: Literal["complete", "partial", "unknown"] = "unknown"
    trace: Mapping[Identifier, Count] = Field(default_factory=dict, max_length=32)
    query_plan: QueryPlan | None = None
    source_data_untrusted: Literal[True] = True
    budget_scope: Literal["context_packet_only"] = "context_packet_only"

    @field_validator("trace")
    @classmethod
    def immutable_counters(cls, value):
        return _freeze_json(dict(value))

    @field_serializer("trace")
    def serialize_counters(self, value):
        return _thaw_json(value)

    @model_validator(mode="after")
    def packet_accounting(self):
        if self.retrieval_status is ContextStatus.UNAUTHORIZED and (
                self.evidence_packets or self.source_references or self.trace or self.query_plan is not None):
            raise ValueError("denied context must not disclose evidence or diagnostics")
        measured = len(self.context_packet.encode("utf-8"))
        if measured != self.selected_context_bytes or measured > self.token_budget:
            raise ValueError("context packet accounting is invalid")
        if not self.evidence_packets:
            if self.context_packet or self.source_references:
                raise ValueError("empty context must have an empty packet and sources")
            return self
        packet = json.loads(self.context_packet)
        if (not isinstance(packet, dict)
                or set(packet) != {"context_contract_version", "evidence_packets", "token_budget",
                                   "counting_method", "selected_context_bytes"}
                or packet.get("context_contract_version") != CONTEXT_VERSION
                or packet.get("token_budget") != self.token_budget
                or packet.get("counting_method") != self.counting_method
                or packet.get("selected_context_bytes") != measured
                or not isinstance(packet.get("evidence_packets"), list)):
            raise ValueError("context packet metadata is invalid")
        packed = tuple(ContextEvidence.model_validate(value) for value in packet["evidence_packets"])
        if packed != self.evidence_packets:
            raise ValueError("context packet evidence differs")
        expected = tuple(dict.fromkeys(proof.source_reference for unit in self.evidence_packets for proof in unit.source_proofs))
        if expected != self.source_references:
            raise ValueError("context source references differ")
        return self
