"""Integration tests for source-grounded, retry-safe Stage 3 processing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from oomp.domain.enums import EventType, MemoryType, SourceType
from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
from oomp.ingestion import DeterministicExtractor, EventNotFoundError, ExtractionPipeline, ProcessingError
from oomp.storage import SQLiteEventStore
from oomp.storage.memory_store import SQLiteMemoryStore

NOW = datetime(2026, 1, 2, 10, tzinfo=timezone.utc)
SCOPE = AuthorizedScope(tenant_id="tenant-a", namespace="personal", principal_id="test-service")


def event(
    content: str, event_id: str, *,
    tenant_id: str = "tenant-a", namespace: str = "personal",
    event_type: EventType = EventType.USER_MESSAGE,
    source_type: SourceType = SourceType.USER,
) -> MemoryEvent:
    timestamp = NOW + timedelta(minutes=int(event_id.rsplit("-", 1)[-1]) if event_id[-1].isdigit() else 0)
    return MemoryEvent(
        event_id=event_id, tenant_id=tenant_id, namespace=namespace,
        event_type=event_type, source_type=source_type, content=content,
        source_reference=SourceReference(
            source_system="synthetic-test", external_event_id=event_id,
            timestamp=timestamp, session_id="session-1",
        ),
        occurred_at=timestamp, ingested_at=timestamp,
    )


def new_database(tmp_path: Path) -> Path:
    database = tmp_path / "memory.sqlite3"
    assert SQLiteEventStore(database).initialize() == 4
    return database


def test_repeated_event_and_separate_evidence_reuse_one_memory(tmp_path: Path) -> None:
    database = new_database(tmp_path)
    events = [event("I prefer Python.", "event-1"), event("I prefer Python.", "event-2")]
    source_store = SQLiteEventStore(database)
    for source in events:
        source_store.append(SCOPE, source)
    pipeline = ExtractionPipeline(database)
    first = pipeline.process_event(SCOPE, "event-1")
    retry = pipeline.process_event(SCOPE, "event-1")
    second = pipeline.process_event(SCOPE, "event-2")
    assert (first.memories_created, first.evidence_links_added) == (1, 1)
    assert (retry.memories_created, retry.memories_reused, retry.evidence_links_added) == (0, 1, 0)
    assert (second.memories_created, second.memories_reused, second.evidence_links_added) == (0, 1, 1)
    reopened = SQLiteMemoryStore(database)
    assert reopened.count_memories(SCOPE) == 1
    memory = reopened.list_memories(SCOPE).memories[0]
    assert memory.memory_type is MemoryType.PROFILE
    assert memory.canonical_content == "User prefers Python."
    assert set(memory.source_event_ids) == {"event-1", "event-2"}
    assert set(memory.provenance) == {source.source_reference for source in events}
    assert memory.metadata["verified"] is False


def test_multiple_supported_statements_in_one_event(tmp_path: Path) -> None:
    database = new_database(tmp_path)
    source = event("I prefer Python. I am developing a project called OOMP.", "event-1")
    SQLiteEventStore(database).append(SCOPE, source)
    result = ExtractionPipeline(database).process_event(SCOPE, source.event_id)
    assert result.candidates_extracted == 2
    assert result.memories_created == 2
    assert result.evidence_links_added == 2
    memories = SQLiteMemoryStore(database).list_memories(SCOPE).memories
    assert {memory.memory_type for memory in memories} == {MemoryType.PROFILE, MemoryType.PROJECT_STATE}
    assert all(memory.source_event_ids == (source.event_id,) for memory in memories)


def test_missing_or_foreign_source_is_not_processed(tmp_path: Path) -> None:
    database = new_database(tmp_path)
    pipeline = ExtractionPipeline(database)
    with pytest.raises(EventNotFoundError):
        pipeline.process_event(SCOPE, "missing-event")
    source = event("I prefer Python.", "event-1", tenant_id="tenant-b")
    other_scope = AuthorizedScope(tenant_id="tenant-b", namespace="personal", principal_id="test-service")
    SQLiteEventStore(database).append(other_scope, source)
    with pytest.raises(EventNotFoundError):
        pipeline.process_event(SCOPE, source.event_id)
    assert SQLiteMemoryStore(database).count_memories(SCOPE) == 0


@pytest.mark.parametrize(
    ("content", "event_type", "source_type"),
    [
        ("The user prefers Java.", EventType.ASSISTANT_MESSAGE, SourceType.ASSISTANT),
        ("I prefer Python. My password is secret.", EventType.USER_MESSAGE, SourceType.USER),
        ("I prefer Python.\nSECRET=synthetic-private-value", EventType.USER_MESSAGE, SourceType.USER),
        ("Maybe I will start a company.", EventType.USER_MESSAGE, SourceType.USER),
        ("Should I prefer Java?", EventType.USER_MESSAGE, SourceType.USER),
    ],
)
def test_ineligible_events_return_empty_results_without_losing_sources(
    tmp_path: Path, content: str, event_type: EventType, source_type: SourceType,
) -> None:
    database = new_database(tmp_path)
    source = event(content, "event-1", event_type=event_type, source_type=source_type)
    SQLiteEventStore(database).append(SCOPE, source)
    result = ExtractionPipeline(database).process_event(SCOPE, source.event_id)
    assert result.event_id == source.event_id
    assert result.candidates_extracted == result.memories_created == 0
    assert result.reason
    assert SQLiteEventStore(database).get(SCOPE, source.event_id) == source
    assert SQLiteMemoryStore(database).count_memories(SCOPE) == 0


class ProposedExtractor:
    def __init__(self, proposals):
        self.proposals = proposals

    def extract_candidates(self, scope, event):
        return self.proposals


@pytest.mark.parametrize(
    "change",
    [
        {"memory_type": "invented"},
        {"canonical_content": "User prefers Java."},
        {"source_event_id": "other-event"},
        {"tenant_id": "tenant-b"},
        {"namespace": "other"},
        {"source_span": {"start": 0, "end": 2, "quote": "no"}},
        {"confidence": 0.9},
    ],
)
def test_untrusted_proposal_cannot_invent_or_redirect_memory(tmp_path: Path, change: dict) -> None:
    database = new_database(tmp_path)
    source = event("I prefer Python.", "event-1")
    SQLiteEventStore(database).append(SCOPE, source)
    candidate = DeterministicExtractor().extract_candidates(SCOPE, source)[0]
    payload = {**candidate.model_dump(mode="json"), **change}
    pipeline = ExtractionPipeline(database, extractor=ProposedExtractor((payload,)))
    with pytest.raises(ProcessingError):
        pipeline.process_event(SCOPE, source.event_id)
    assert SQLiteMemoryStore(database).count_memories(SCOPE) == 0


def test_overlarge_and_partially_bad_candidate_batch_never_writes(tmp_path: Path) -> None:
    database = new_database(tmp_path)
    source = event("I prefer Python. I plan to build a robot.", "event-1")
    SQLiteEventStore(database).append(SCOPE, source)
    valid = DeterministicExtractor().extract_candidates(SCOPE, source)
    too_many = ExtractionPipeline(database, extractor=ProposedExtractor(valid * 17))
    with pytest.raises(ProcessingError, match="output limit"):
        too_many.process_event(SCOPE, source.event_id)
    bad_second = {**valid[1].model_dump(mode="json"), "canonical_content": "User completed a robot."}
    partial = ExtractionPipeline(database, extractor=ProposedExtractor((valid[0], bad_second)))
    with pytest.raises(ProcessingError):
        partial.process_event(SCOPE, source.event_id)
    assert SQLiteMemoryStore(database).count_memories(SCOPE) == 0
