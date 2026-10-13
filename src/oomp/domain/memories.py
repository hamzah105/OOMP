"""Stage 3 memory, evidence, and conservative entity contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field, StrictInt, StringConstraints, field_validator, model_validator

from .models import (
    ContractModel, Identifier, MemoryNode, RequestedScope, UtcDateTime, _nonblank,
)


class EntityType(StrEnum):
    PERSON = "person"
    PROJECT = "project"
    ORGANIZATION = "organization"
    TECHNOLOGY = "technology"
    LOCATION = "location"
    CONCEPT = "concept"


Name = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=512)]


class SourceSpan(ContractModel):
    start: StrictInt = Field(ge=0)
    end: StrictInt = Field(gt=0)
    quote: str = Field(min_length=1, max_length=16384)

    @field_validator("quote")
    @classmethod
    def nonblank_quote(cls, value: str) -> str:
        return _nonblank(value)

    @model_validator(mode="after")
    def ordered(self) -> SourceSpan:
        if self.end <= self.start:
            raise ValueError("source span end must exceed start")
        return self


class EntityMention(ContractModel):
    name: Name
    entity_type: EntityType
    aliases: tuple[Name, ...] = Field(default=(), max_length=8)
    source_event_id: Identifier
    source_span: SourceSpan | None = None

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        return _nonblank(value)

    @field_validator("aliases")
    @classmethod
    def nonblank_aliases(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for alias in value:
            _nonblank(alias)
        return value


class EntityRecord(ContractModel):
    entity_id: Identifier
    tenant_id: Identifier
    namespace: Identifier
    entity_type: EntityType
    canonical_name: Name
    normalized_name: Name
    aliases: tuple[Name, ...] = Field(default=(), max_length=64)
    created_at: UtcDateTime

    @field_validator("canonical_name", "normalized_name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        return _nonblank(value)


class MemoryCursor(RequestedScope):
    created_at: UtcDateTime
    memory_id: Identifier


class MemoryPage(ContractModel):
    memories: tuple[MemoryNode, ...] = ()
    next_cursor: MemoryCursor | None = None


class MemoryWrite(ContractModel):
    memory: MemoryNode
    entities: tuple[EntityMention, ...] = Field(default=(), max_length=32)
    source_span: SourceSpan | None = None
    extraction_method: Identifier = "deterministic"


class ProcessingResult(ContractModel):
    event_id: Identifier
    candidates_extracted: StrictInt = Field(default=0, ge=0)
    memories_created: StrictInt = Field(default=0, ge=0)
    memories_reused: StrictInt = Field(default=0, ge=0)
    evidence_links_added: StrictInt = Field(default=0, ge=0)
    entities_created: StrictInt = Field(default=0, ge=0)
    entities_reused: StrictInt = Field(default=0, ge=0)
    skipped_candidates: StrictInt = Field(default=0, ge=0)
    memory_ids: tuple[Identifier, ...] = Field(default=(), max_length=32)
    reason: str | None = Field(default=None, max_length=512)

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value: str | None) -> str | None:
        return None if value is None else _nonblank(value)