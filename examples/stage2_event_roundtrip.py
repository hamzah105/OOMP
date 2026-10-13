"""Synthetic SQLite event ingestion and restart demonstration.

Run with `python examples/stage2_event_roundtrip.py` for an isolated temporary
database, or add `--db PATH` to use a dedicated local demonstration database
across separate executions.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from oomp.domain.enums import EventType, SourceType
from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
from oomp.storage import SQLiteEventStore
from oomp.storage.errors import IdempotencyConflictError

SCOPE = AuthorizedScope(
    tenant_id="tenant-demo",
    namespace="examples",
    principal_id="example-service",
)


def instant(hour: int, minute: int) -> datetime:
    return datetime(2026, 1, 2, hour, minute, tzinfo=timezone.utc)


def example_event(
    *,
    event_id: str,
    external_event_id: str,
    content: str,
    occurred_at: datetime,
    ingested_at: datetime,
    idempotency_key: str,
) -> MemoryEvent:
    return MemoryEvent(
        event_id=event_id,
        tenant_id=SCOPE.tenant_id,
        namespace=SCOPE.namespace,
        event_type=EventType.USER_MESSAGE,
        source_type=SourceType.USER,
        content=content,
        source_reference=SourceReference(
            source_system="synthetic-example",
            external_event_id=external_event_id,
            timestamp=occurred_at,
            session_id="demo-session",
            turn_id=external_event_id,
        ),
        occurred_at=occurred_at,
        ingested_at=ingested_at,
        idempotency_key=idempotency_key,
        metadata={"example": {"synthetic": True, "sequence": external_event_id}},
    )


def run(database_path: Path) -> None:
    store = SQLiteEventStore(database_path)
    store.initialize()
    first = example_event(
        event_id="demo-event-1",
        external_event_id="demo-turn-1",
        content="The user prefers Python for local AI development.",
        occurred_at=instant(10, 0),
        ingested_at=instant(10, 5),
        idempotency_key="demo-idempotency-1",
    )
    second = example_event(
        event_id="demo-event-2",
        external_event_id="demo-turn-2",
        content="The user is planning a robotics project.",
        occurred_at=instant(10, 2),
        ingested_at=instant(10, 4),
        idempotency_key="demo-idempotency-2",
    )
    # Ingest out of occurrence order to show that reads sort by source time.
    assert store.append(SCOPE, second) == second
    assert store.append(SCOPE, first) == first
    count_before_retry = store.count_events(SCOPE)

    retry = example_event(
        event_id="demo-retry-id",
        external_event_id="demo-turn-1",
        content=first.content,
        occurred_at=first.occurred_at,
        ingested_at=instant(11, 0),
        idempotency_key=first.idempotency_key or "demo-idempotency-1",
    )
    assert store.append(SCOPE, retry) == first
    assert store.count_events(SCOPE) == count_before_retry

    conflict = example_event(
        event_id="demo-conflict-id",
        external_event_id="demo-turn-1",
        content="The user prefers a different language.",
        occurred_at=first.occurred_at,
        ingested_at=instant(11, 1),
        idempotency_key=first.idempotency_key or "demo-idempotency-1",
    )
    try:
        store.append(SCOPE, conflict)
    except IdempotencyConflictError:
        pass
    else:
        raise AssertionError("Conflicting idempotency key was accepted")
    assert store.count_events(SCOPE) == count_before_retry
    assert store.get(SCOPE, first.event_id) == first

    # Every store operation closes its SQLite connection. A new instance
    # demonstrates that the events survive beyond the writing instance.
    reopened = SQLiteEventStore(database_path)
    page = reopened.list_events(SCOPE, limit=100)
    demonstration_events = [event for event in page.events if event.event_id in {first.event_id, second.event_id}]
    assert demonstration_events == [first, second]
    assert reopened.get(SCOPE, first.event_id) == first
    assert reopened.get(SCOPE, second.event_id) == second

    print(f"Database: {database_path}")
    print(f"Scoped event count: {reopened.count_events(SCOPE)}")
    print(f"Retry resolved to original event: {first.event_id}")
    print("Conflicting retry rejected; original event retained")
    print("Events in occurrence order:")
    for event in demonstration_events:
        print(f"  {event.occurred_at.isoformat()} {event.event_id}: {event.content}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a synthetic Stage 2 event-storage example.")
    parser.add_argument("--db", type=Path, help="dedicated persistent demonstration database path")
    args = parser.parse_args()
    if args.db is not None:
        run(args.db)
    else:
        with TemporaryDirectory(prefix="oomp-stage2-example-") as temporary_directory:
            run(Path(temporary_directory) / "events.sqlite3")


if __name__ == "__main__":
    main()
