"""Validated evidence, memory, temporal, and scope contracts."""

from __future__ import annotations

import math
from collections.abc import Mapping
from types import MappingProxyType
from datetime import datetime, timezone
from typing import Annotated, Any

from pydantic import AfterValidator, BeforeValidator, BaseModel, ConfigDict, Field, StringConstraints, field_serializer, field_validator, model_validator

from .enums import EventType, MemoryStatus, MemoryType, RelationshipType, SourceType

_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
Identifier = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=128, pattern=_ID_PATTERN)]
ExternalIdentifier = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=512)]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a UTC offset")
    return value.astimezone(timezone.utc)


UtcDateTime = Annotated[datetime, AfterValidator(_utc)]


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("text must not be blank")
    return value


def _numeric_score(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("score must be a number, not a string or boolean")
    try:
        return float(value)
    except OverflowError as error:
        raise ValueError("score is too large") from error


Confidence = Annotated[float, BeforeValidator(_numeric_score), Field(ge=0, le=1, allow_inf_nan=False)]


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value

def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value

def _check_json(value: Any, seen: set[int] | None = None) -> None:
    if seen is None:
        seen = set()
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("metadata numbers must be finite")
        return
    if isinstance(value, (list, dict)):
        identity = id(value)
        if identity in seen:
            raise ValueError("metadata contains a cycle")
        seen.add(identity)
        try:
            if isinstance(value, list):
                for item in value:
                    _check_json(item, seen)
            else:
                for key, item in value.items():
                    if not isinstance(key, str):
                        raise ValueError("metadata keys must be strings")
                    _check_json(item, seen)
        finally:
            seen.remove(identity)
        return
    raise ValueError("metadata must contain JSON-compatible values")


class ContractModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", validate_default=True)


class RequestedScope(ContractModel):
    """A client's requested tenant and namespace; no authorization claim."""

    tenant_id: Identifier
    namespace: Identifier


class AuthorizedScope(RequestedScope):
    """Scope supplied by a trusted service after authentication and policy checks."""

    principal_id: Identifier


class SourceReference(ContractModel):
    source_system: Identifier
    external_event_id: ExternalIdentifier
    timestamp: UtcDateTime
    session_id: Identifier | None = None
    turn_id: Identifier | None = None
    locator: str | None = Field(default=None, max_length=1024)

    @field_validator("external_event_id", "locator")
    @classmethod
    def nonblank_optional_text(cls, value: str | None) -> str | None:
        if value is not None:
            _nonblank(value)
        return value


class MemoryEvent(ContractModel):
    """Original source evidence; claims in content are not verified truth."""

    event_id: Identifier
    tenant_id: Identifier
    namespace: Identifier
    event_type: EventType
    source_type: SourceType
    content: str = Field(min_length=1, max_length=1_000_000)
    source_reference: SourceReference
    occurred_at: UtcDateTime
    ingested_at: UtcDateTime
    idempotency_key: Identifier | None = None
    metadata: Mapping[str, Any] = Field(default_factory=dict)

    @field_validator("content")
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
    def coherent_source(self) -> MemoryEvent:
        source_for_event = {
            EventType.USER_MESSAGE: SourceType.USER,
            EventType.ASSISTANT_MESSAGE: SourceType.ASSISTANT,
            EventType.DOCUMENT: SourceType.DOCUMENT,
            EventType.TOOL_RESULT: SourceType.TOOL,
        }
        required = source_for_event.get(self.event_type)
        if required is not None and self.source_type is not required:
            raise ValueError(f"{self.event_type.value} requires source_type {required.value}")
        return self


class MemoryNode(ContractModel):
    """Canonical derived memory with explicit evidence and temporal validity."""

    memory_id: Identifier
    tenant_id: Identifier
    namespace: Identifier
    memory_type: MemoryType
    canonical_content: str = Field(min_length=1, max_length=1_000_000)
    canonical_key: str = Field(min_length=1, max_length=512)
    source_event_ids: tuple[Identifier, ...] = Field(min_length=1)
    provenance: tuple[SourceReference, ...] = Field(min_length=1)
    confidence: Confidence | None = None
    created_at: UtcDateTime
    updated_at: UtcDateTime
    valid_from: UtcDateTime | None = None
    valid_until: UtcDateTime | None = None
    status: MemoryStatus = MemoryStatus.ACTIVE
    tags: tuple[Identifier, ...] = ()
    metadata: Mapping[str, Any] = Field(default_factory=dict)

    @field_validator("canonical_content", "canonical_key")
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
    def chronological(self) -> MemoryNode:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        if self.valid_from is not None and self.valid_until is not None and self.valid_until < self.valid_from:
            raise ValueError("valid_until cannot precede valid_from")
        return self


class MemoryEdge(ContractModel):
    """Typed relationship; graph and endpoint scope checks belong to storage."""

    edge_id: Identifier
    tenant_id: Identifier
    namespace: Identifier
    source_node_id: Identifier
    target_node_id: Identifier
    relationship_type: RelationshipType
    source_event_ids: tuple[Identifier, ...] = Field(min_length=1)
    confidence: Confidence | None = None
    created_at: UtcDateTime
    valid_from: UtcDateTime | None = None
    valid_until: UtcDateTime | None = None
    status: MemoryStatus = MemoryStatus.ACTIVE

    @model_validator(mode="after")
    def chronological(self) -> MemoryEdge:
        if self.valid_from is not None and self.valid_until is not None and self.valid_until < self.valid_from:
            raise ValueError("valid_until cannot precede valid_from")
        return self

