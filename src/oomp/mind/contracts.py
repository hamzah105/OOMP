"""Validated, content-free contracts for durable mind work."""

from __future__ import annotations

from enum import StrEnum
from collections.abc import Mapping
from typing import Any

from pydantic import Field, StrictBool, StrictInt, field_serializer, field_validator, model_validator

from oomp.domain.models import (
    ContractModel, Identifier, SourceReference, UtcDateTime, _check_json, _freeze_json, _thaw_json,
)


class JobType(StrEnum):
    EXTRACT_EVENT = "extract_event"
    MAINTAIN_INDEX = "maintain_index"
    CONSOLIDATE_TOPIC = "consolidate_topic"
    INSPECT_CONFLICTS = "inspect_conflicts"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MindJob(ContractModel):
    job_id: Identifier
    tenant_id: Identifier
    namespace: Identifier
    job_type: JobType
    target_type: Identifier
    target_id: Identifier
    idempotency_key: Identifier
    status: JobStatus
    priority: StrictInt = Field(default=0, ge=-100, le=100)
    attempt_count: StrictInt = Field(default=0, ge=0)
    max_attempts: StrictInt = Field(default=3, ge=1, le=20)
    created_at: UtcDateTime
    updated_at: UtcDateTime
    available_at: UtcDateTime
    lease_owner: Identifier | None = None
    lease_expires_at: UtcDateTime | None = None
    fencing_token: StrictInt = Field(default=0, ge=0)
    policy_version: Identifier
    config: Mapping[str, Any] = Field(default_factory=dict)
    last_error_code: Identifier | None = None

    @field_validator("config")
    @classmethod
    def bounded_config(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise ValueError("job config must be a mapping")
        data = dict(value)
        _check_json(data)
        if len(str(data)) > 1024:
            raise ValueError("job configuration exceeds bound")
        return _freeze_json(data)

    @field_serializer("config")
    def serialize_config(self, value: Mapping[str, Any]) -> dict[str, Any]:
        return _thaw_json(value)

    @model_validator(mode="after")
    def valid_lease(self) -> MindJob:
        if self.updated_at < self.created_at:
            raise ValueError("job update precedes creation")
        if self.lease_expires_at is not None and self.lease_expires_at <= self.updated_at:
            raise ValueError("running job lease must extend beyond update time")
        if (self.lease_owner is None) != (self.lease_expires_at is None):
            raise ValueError("lease owner and expiry must be paired")
        if self.status is JobStatus.RUNNING and self.lease_owner is None:
            raise ValueError("running job must have a lease")
        if self.status is not JobStatus.RUNNING and self.lease_owner is not None:
            raise ValueError("non-running job cannot have a lease")
        if self.attempt_count > self.max_attempts:
            raise ValueError("attempt count exceeds configured maximum")
        expected_target = "topic" if self.job_type is JobType.CONSOLIDATE_TOPIC else "event"
        if self.target_type != expected_target:
            raise ValueError("job target type is incompatible with handler")
        if self.job_type is JobType.MAINTAIN_INDEX:
            if set(self.config) - {"include_embeddings", "space"}:
                raise ValueError("unsupported index job configuration")
            enabled = self.config.get("include_embeddings", False)
            if type(enabled) is not bool:
                raise ValueError("include_embeddings must be boolean")
            if enabled:
                from oomp.retrieval.contracts import EmbeddingSpace
                if set(self.config) != {"include_embeddings", "space"}:
                    raise ValueError("explicit embedding space is required")
                raw = self.config["space"]
                if not isinstance(raw, Mapping):
                    raise ValueError("embedding space must be a mapping")
                EmbeddingSpace.model_validate(dict(raw))
            elif "space" in self.config:
                raise ValueError("embedding space requires explicit opt-in")
        elif self.config:
            raise ValueError("this job type does not accept configuration")
        return self


class SummarySource(ContractModel):
    memory_id: Identifier
    event_id: Identifier
    source_reference: SourceReference
    attribution: str = Field(min_length=1, max_length=32)
    verified: StrictBool
    validity: str = Field(min_length=1, max_length=32)


class SummaryRevision(ContractModel):
    revision_id: Identifier
    tenant_id: Identifier
    namespace: Identifier
    topic_id: Identifier
    revision_number: StrictInt = Field(ge=1)
    content: str = Field(min_length=1, max_length=4096)
    source_memory_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=16)
    source_event_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=1000)
    sources: tuple[SummarySource, ...] = Field(min_length=1, max_length=1000)
    freshness: str = Field(default="current", pattern="^(current|recorded_projection|stale)$")
    source_fingerprint: str = Field(min_length=64, max_length=64)
    policy_version: Identifier
    recorded_at: UtcDateTime
    retired_at: UtcDateTime | None = None


class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewRecord(ContractModel):
    proposal_id: Identifier
    tenant_id: Identifier
    namespace: Identifier
    source_node_id: Identifier
    target_node_id: Identifier
    source_event_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=2)
    relationship_type: str
    reason: str = Field(min_length=1, max_length=256)
    policy_version: Identifier
    status: ReviewStatus = ReviewStatus.PENDING
    recorded_at: UtcDateTime
    decision_at: UtcDateTime | None = None
    decided_by: Identifier | None = None
