"""Synthetic, repeatable Stage 3 memory extraction and persistence example."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from oomp.domain.enums import EventType, MemoryType, SourceType
from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
from oomp.ingestion import ExtractionPipeline
from oomp.storage import SQLiteEventStore
from oomp.storage.entity_store import SQLiteEntityStore
from oomp.storage.memory_store import SQLiteMemoryStore

SCOPE = AuthorizedScope(
    tenant_id="tenant-stage3-example", namespace="synthetic",
    principal_id="example-service",
)


def source_event(event_id: str, content: str, minute: int) -> MemoryEvent:
    timestamp = datetime(2026, 1, 2, 10, minute, tzinfo=timezone.utc)
    return MemoryEvent(
        event_id=event_id, tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
        event_type=EventType.USER_MESSAGE, source_type=SourceType.USER,
        content=content,
        source_reference=SourceReference(
            source_system="synthetic-example",
            external_event_id=event_id,
            timestamp=timestamp,
            session_id="stage3-demo",
            turn_id=event_id,
        ),
        occurred_at=timestamp, ingested_at=timestamp,
        idempotency_key="key-" + event_id,
        metadata={"synthetic": True},
    )


EVENTS = (
    source_event("preference-1", "I prefer Python.", 0),
    source_event("preference-2", "I prefer Python.", 1),
    source_event(
        "project-1",
        "I am developing a project called OOMP (Object-Oriented Context Map).", 2,
    ),
    source_event("project-2", "I am developing a project called OOMP.", 3),
)


def run(path: Path) -> None:
    event_store = SQLiteEventStore(path)
    event_store.initialize()
    pipeline = ExtractionPipeline(path)
    print(f"Scope: tenant={SCOPE.tenant_id} namespace={SCOPE.namespace}")
    for source in EVENTS:
        assert event_store.append(SCOPE, source) == source
        result = pipeline.process_event(SCOPE, source.event_id)
        assert result.candidates_extracted == 1
        print(result.model_dump_json())

    # A new instance reads persisted memories and their full evidence sets.
    memory_store = SQLiteMemoryStore(path)
    page = memory_store.list_memories(SCOPE)
    memories = {memory.memory_type: memory for memory in page.memories}
    assert len(memories) == memory_store.count_memories(SCOPE) == 2
    profile = memories[MemoryType.PROFILE]
    project = memories[MemoryType.PROJECT_STATE]
    assert set(profile.source_event_ids) == {"preference-1", "preference-2"}
    assert set(project.source_event_ids) == {"project-1", "project-2"}
    assert len(profile.provenance) == len(project.provenance) == 2
    entities = memory_store.list_entities(SCOPE, project.memory_id)
    assert len(entities) == 1
    assert SQLiteEntityStore(path).count_entities(SCOPE) == 1

    print(f"Database: {path}")
    print(f"Stored source events: {SQLiteEventStore(path).count_events(SCOPE)}")
    print(f"Canonical memories: {memory_store.count_memories(SCOPE)}")
    for memory in page.memories:
        linked = memory_store.list_entities(SCOPE, memory.memory_id)
        print(
            f"{memory.memory_id} type={memory.memory_type.value} "
            f"evidence={len(memory.source_event_ids)} entities={len(linked)}"
        )
    print(f"Resolved project entity: {entities[0].entity_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run synthetic Stage 3 extraction.")
    parser.add_argument("--db", type=Path, help="dedicated persistent demonstration database path")
    args = parser.parse_args()
    if args.db is not None:
        run(args.db)
    else:
        with TemporaryDirectory(prefix="oomp-stage3-example-") as temporary_directory:
            run(Path(temporary_directory) / "events.sqlite3")


if __name__ == "__main__":
    main()
