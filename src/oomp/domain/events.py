"""Validated bounded chronological event pages."""

from __future__ import annotations

from pydantic import Field

from .models import ContractModel, Identifier, MemoryEvent, RequestedScope, UtcDateTime


class EventCursor(RequestedScope):
    """Keyset position within one requested tenant and namespace."""

    occurred_at: UtcDateTime
    ingested_at: UtcDateTime
    event_id: Identifier


class EventPage(ContractModel):
    events: tuple[MemoryEvent, ...] = ()
    next_cursor: EventCursor | None = None