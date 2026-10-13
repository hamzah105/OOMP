"""Validated proposals at the boundary between extraction and persistence."""

from __future__ import annotations

from typing import Protocol, Sequence

from pydantic import Field, field_validator, model_validator

from oomp.domain.enums import MemoryType
from oomp.domain.memories import EntityMention, SourceSpan
from oomp.domain.models import (
    Confidence, ContractModel, Identifier, MemoryEvent, RequestedScope, _nonblank,
)


class MemoryCandidate(RequestedScope):
    candidate_id: Identifier
    memory_type: MemoryType
    canonical_content: str = Field(min_length=1, max_length=16384)
    source_event_id: Identifier
    source_span: SourceSpan
    subject: str | None = Field(default=None, max_length=512)
    entities: tuple[EntityMention, ...] = Field(default=(), max_length=8)
    confidence: Confidence | None = None
    extraction_method: Identifier = "deterministic"

    @field_validator("canonical_content", "subject")
    @classmethod
    def nonblank_text(cls, value: str | None) -> str | None:
        return None if value is None else _nonblank(value)

    @model_validator(mode="after")
    def consistent_mentions(self) -> MemoryCandidate:
        if any(mention.source_event_id != self.source_event_id for mention in self.entities):
            raise ValueError("candidate entity mention has a different source event")
        return self


class CandidateExtractor(Protocol):
    def extract_candidates(
        self, scope: RequestedScope, event: MemoryEvent
    ) -> Sequence[MemoryCandidate]: ...


class ProcessingError(Exception):
    """A proposal failed validation before persistence; text is safe for CLI output."""


class EventNotFoundError(ProcessingError):
    """No event exists within the authorized scope."""
