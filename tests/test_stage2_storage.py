"""Real file-backed Stage 2 SQLite event-store integration tests."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from oomp.domain.events import EventCursor
from oomp.domain.models import AuthorizedScope, MemoryEvent, RequestedScope, SourceReference
from oomp.storage import (
    DatabaseMissingError,
    DatabaseUninitializedError,
    ForeignDatabaseError,
    IdempotencyConflictError,
    ScopeMismatchError,
    SQLiteEventStore,
    StorageBusyError,
    StorageCorruptionError,
    StorageUnavailableError,
    StoredEventCorruptionError,
    UnsupportedSchemaVersionError,
)
from oomp.storage.migrations import MIGRATION_1

NOW = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)


def scope(tenant="tenant-a", namespace="personal"):
    return AuthorizedScope(tenant_id=tenant, namespace=namespace, principal_id="local-test")


def event(**changes):
    values = dict(
        event_id="event-1", tenant_id="tenant-a", namespace="personal",
        event_type="user_message", source_type="user", content="Synthetic evidence.",
        source_reference=SourceReference(
            source_system="test", external_event_id="external-1",
            session_id="session-1", turn_id="turn-1", locator="paragraph 2", timestamp=NOW,
        ),
        occurred_at=NOW, ingested_at=NOW, idempotency_key="delivery-1",
        metadata={"nested": {"items": [1, 2.0, None, "Ω"]}},
    )
    values.update(changes)
    return MemoryEvent(**values)


@pytest.fixture
def store(tmp_path):
    result = SQLiteEventStore(tmp_path / "data" / "events.sqlite3")
    result.initialize()
    return result


def test_config_constructor_and_missing_status_are_read_only(tmp_path, monkeypatch):
    path = tmp_path / "missing" / "events.sqlite3"
    monkeypatch.setenv("OOMP_DB_PATH", str(path))
    selected = SQLiteEventStore()
    assert selected.path == path.resolve()
    status = selected.status()
    assert not status.exists and not status.ready and not status.accessible
    assert status.schema_version is None and status.journal_mode is None
    assert not path.parent.exists()
    with pytest.raises(DatabaseMissingError):
        selected.count_events(scope())
    explicit = SQLiteEventStore(tmp_path / "explicit.db")
    assert explicit.path != selected.path
    monkeypatch.setenv("OOMP_DB_PATH", " ")
    with pytest.raises(ValueError):
        SQLiteEventStore()
    with pytest.raises(ValueError):
        SQLiteEventStore(":memory:")
    for timeout in (-1, 60001, True, "5000"):
        with pytest.raises(ValueError):
            SQLiteEventStore(path, busy_timeout_ms=timeout)


def test_fresh_initialization_version_wal_and_repeated_init_preserve_rows(tmp_path):
    path = tmp_path / "nested" / "events.db"
    store = SQLiteEventStore(path)
    assert not path.parent.exists()
    assert store.initialize() == 2
    assert path.is_file()
    status = store.status()
    assert status.exists and status.accessible and status.ready
    assert status.schema_version == 2
    assert status.journal_mode in {"wal", "delete", "truncate", "persist"}
    with closing(sqlite3.connect(path)) as connection, connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        objects = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'"
            )
        }
        assert objects == {
            "events", "events_idempotency_key", "events_chronological",
            "events_no_update", "events_no_delete",
            "memories", "memories_chronological", "memory_sources",
            "memory_sources_event", "entities", "entity_aliases",
            "memory_entities", "memory_entities_entity",
        }
    stored = store.append(scope(), event())
    assert store.initialize() == 2
    assert store.get(scope(), "event-1") == stored
    assert store.count_events(scope()) == 1


def test_negative_schema_version_is_invalid_without_initialize_mutation(tmp_path):
    path = tmp_path / "negative.db"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("PRAGMA user_version=-1")
    store = SQLiteEventStore(path)
    status = store.status()
    assert status.exists and status.accessible and status.schema_version == -1
    assert not status.ready
    with pytest.raises(StorageCorruptionError):
        store.initialize()
    with closing(sqlite3.connect(path)) as connection, connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == -1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"


def test_future_unowned_and_structurally_damaged_schemas_fail_closed(tmp_path):
    future_path = tmp_path / "future.db"
    with closing(sqlite3.connect(future_path)) as connection, connection:
        connection.execute("PRAGMA user_version=3")
    future = SQLiteEventStore(future_path)
    status = future.status()
    assert status.exists and status.accessible and status.schema_version == 3 and not status.ready
    with pytest.raises(UnsupportedSchemaVersionError):
        future.initialize()
    with closing(sqlite3.connect(future_path)) as connection, connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3

    foreign_path = tmp_path / "foreign.db"
    with closing(sqlite3.connect(foreign_path)) as connection, connection:
        connection.execute("CREATE TABLE sqliteXunrelated (x TEXT)")
    foreign = SQLiteEventStore(foreign_path)
    assert not foreign.status().ready
    with pytest.raises(ForeignDatabaseError):
        foreign.initialize()
    with closing(sqlite3.connect(foreign_path)) as connection, connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='sqliteXunrelated'").fetchone()

    valid = SQLiteEventStore(tmp_path / "valid.db")
    valid.initialize()
    with closing(sqlite3.connect(valid.path)) as connection, connection:
        connection.execute("DROP TRIGGER events_no_delete")
    assert not valid.status().ready
    with pytest.raises(StorageCorruptionError):
        valid.initialize()


def test_failed_migration_rolls_back_schema_and_version(tmp_path, monkeypatch):
    from oomp.storage import migrations

    path = tmp_path / "rollback.db"
    monkeypatch.setitem(migrations.MIGRATIONS, 1, MIGRATION_1 + ("CREATE TABLE events (x TEXT)",))
    with pytest.raises(StorageUnavailableError):
        SQLiteEventStore(path).initialize()
    with closing(sqlite3.connect(path)) as connection, connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        names = list(connection.execute(
            "SELECT name FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'"
        ))
        assert names == []
    monkeypatch.setitem(migrations.MIGRATIONS, 1, MIGRATION_1)
    assert SQLiteEventStore(path).initialize() == 2


def test_reopen_preserves_complete_event_and_multiple_records(store):
    first = event()
    second = event(
        event_id="event-2", idempotency_key="delivery-2",
        content="Second synthetic event.", occurred_at=NOW + timedelta(minutes=1),
        source_reference=SourceReference(
            source_system="document", external_event_id="doc/2",
            locator="page 4", timestamp=NOW + timedelta(minutes=1),
        ),
        metadata={"flag": True, "amount": 1.0},
    )
    store.append(scope(), first)
    store.append(scope(), second)
    reopened = SQLiteEventStore(store.path)
    assert reopened.get(scope(), "event-1") == first
    assert reopened.get(scope(), "event-2") == second
    assert reopened.list_events(scope()).events == (first, second)
    assert reopened.count_events(scope()) == 2
    assert reopened.get(scope(), "missing") is None
    assert first.source_reference.session_id == reopened.get(scope(), "event-1").source_reference.session_id
    assert reopened.get(scope(), "event-1").metadata["nested"]["items"] == (1, 2.0, None, "Ω")


def test_utc_offset_occurrence_ingestion_and_nul_text_roundtrip(store):
    plus_five = timezone(timedelta(hours=5))
    occurred = NOW.astimezone(plus_five)
    ingested = (NOW + timedelta(days=1)).astimezone(plus_five)
    original = event(
        content="\x00preserved source text",
        occurred_at=occurred, ingested_at=ingested,
        source_reference=SourceReference(
            source_system="test", external_event_id="x", timestamp=occurred,
        ),
    )
    store.append(scope(), original)
    saved = SQLiteEventStore(store.path).get(scope(), original.event_id)
    assert saved == original
    assert saved.occurred_at == NOW
    assert saved.ingested_at == NOW + timedelta(days=1)
    assert saved.source_reference.timestamp == NOW
    with closing(sqlite3.connect(store.path)) as connection, connection:
        row = connection.execute("SELECT occurred_at, ingested_at FROM events").fetchone()
        assert row == ("2026-01-02T03:04:00.000000Z", "2026-01-03T03:04:00.000000Z")


def test_extreme_supported_years_sort_and_roundtrip(store):
    first = datetime(1, 1, 1, tzinfo=timezone.utc)
    last = datetime(9999, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc)
    late = event(event_id="last", idempotency_key="k-last", occurred_at=last)
    early = event(event_id="first", idempotency_key="k-first", occurred_at=first)
    store.append(scope(), late)
    store.append(scope(), early)
    assert [item.event_id for item in store.list_events(scope()).events] == ["first", "last"]
    assert store.get(scope(), "first").occurred_at == first
    assert store.get(scope(), "last").occurred_at == last
    with closing(sqlite3.connect(store.path)) as connection, connection:
        stamps = [row[0] for row in connection.execute(
            "SELECT occurred_at FROM events ORDER BY occurred_at"
        )]
    assert stamps[0].startswith("0001-")
    assert stamps[1].startswith("9999-")


def test_chronological_order_ties_and_fixed_width_microseconds(store):
    entries = [
        event(event_id="late", idempotency_key="k-late", occurred_at=NOW + timedelta(minutes=2)),
        event(event_id="fraction", idempotency_key="k-fraction", occurred_at=NOW + timedelta(microseconds=1)),
        event(event_id="zero-b", idempotency_key="k-zero-b"),
        event(event_id="zero-a", idempotency_key="k-zero-a"),
        event(event_id="tie-ingested", idempotency_key="k-tie", ingested_at=NOW + timedelta(seconds=1)),
    ]
    for item in entries:
        store.append(scope(), item)
    assert [item.event_id for item in store.list_events(scope()).events] == [
        "zero-a", "zero-b", "tie-ingested", "fraction", "late",
    ]


def test_idempotent_retries_return_original_without_row_change(store):
    first = event()
    assert store.append(scope(), first) == first
    assert store.append(scope(), first) == first
    retry = event(event_id="retry-2", ingested_at=NOW + timedelta(days=1))
    assert store.append(scope(), retry) == first
    reordered_metadata = event(
        event_id="retry-3", ingested_at=NOW + timedelta(days=2),
        metadata={"nested": {"items": [1, 2.0, None, "Ω"]}},
    )
    assert store.append(scope(), reordered_metadata) == first
    assert store.count_events(scope()) == 1
    assert store.get(scope(), "retry-2") is None


@pytest.mark.parametrize(
    "changes",
    [
        {"content": "Synthetic evidence. "},
        {"event_type": "feedback", "source_type": "user"},
        {"source_type": "assistant", "event_type": "assistant_message"},
        {"source_reference": SourceReference(source_system="test", external_event_id="other", timestamp=NOW)},
        {"occurred_at": NOW + timedelta(microseconds=1)},
        {"metadata": {"nested": {"items": [1, 2, None, "Ω"]}}},
        {"metadata": {"nested": {"items": [1, 2.0, None, "Ω", "new"]}}},
    ],
)
def test_shared_key_changed_logical_payload_conflicts(store, changes):
    store.append(scope(), event())
    retry = event(event_id="retry", ingested_at=NOW + timedelta(days=1), **changes)
    with pytest.raises(IdempotencyConflictError):
        store.append(scope(), retry)
    assert store.count_events(scope()) == 1


def test_metadata_key_order_does_not_change_logical_fingerprint(store):
    original = event(
        metadata={"z": 1, "a": {"beta": 2, "alpha": 3}},
    )
    store.append(scope(), original)
    retry = event(
        event_id="retry-reordered",
        ingested_at=NOW + timedelta(seconds=1),
        metadata={"a": {"alpha": 3, "beta": 2}, "z": 1},
    )
    assert store.append(scope(), retry) == original
    assert store.count_events(scope()) == 1


def test_same_event_id_changed_payload_or_key_conflicts(store):
    store.append(scope(), event())
    with pytest.raises(IdempotencyConflictError):
        store.append(scope(), event(content="changed"))
    with pytest.raises(IdempotencyConflictError):
        store.append(scope(), event(idempotency_key="new-key"))
    assert store.append(scope(), event(idempotency_key=None, ingested_at=NOW + timedelta(days=1))) == event()
    assert store.count_events(scope()) == 1


def test_existing_event_cannot_gain_new_idempotency_alias(store):
    original = event(idempotency_key=None)
    store.append(scope(), original)
    with pytest.raises(IdempotencyConflictError):
        store.append(scope(), event(idempotency_key="new-alias"))
    assert store.get(scope(), original.event_id) == original


def test_dual_identifier_collision_conflicts_even_when_payload_matches(store):
    first = event(event_id="first", idempotency_key="key-first")
    second = event(event_id="second", idempotency_key="key-second")
    store.append(scope(), first)
    store.append(scope(), second)
    with pytest.raises(IdempotencyConflictError):
        store.append(scope(), event(event_id="first", idempotency_key="key-second"))
    assert store.count_events(scope()) == 2


def test_fresh_ids_without_shared_key_are_not_globally_deduplicated(store):
    store.append(scope(), event(event_id="a", idempotency_key=None))
    store.append(scope(), event(event_id="b", idempotency_key=None))
    assert store.count_events(scope()) == 2


def test_tenant_namespace_external_id_and_key_isolation(store):
    a = event()
    b = event(tenant_id="tenant-b")
    c = event(namespace="project")
    store.append(scope(), a)
    store.append(scope("tenant-b"), b)
    store.append(scope(namespace="project"), c)
    assert store.count_events(scope()) == 1
    assert store.count_events(scope("tenant-b")) == 1
    assert store.count_events(scope(namespace="project")) == 1
    assert store.get(scope(), "event-1") == a
    assert store.get(scope("tenant-b"), "event-1") == b
    assert store.get(scope(namespace="project"), "event-1") == c
    assert store.get(scope("tenant-z"), "event-1") is None
    assert store.list_events(scope("tenant-z")).events == ()


def test_scope_and_cursor_are_validated_before_database_access(tmp_path, store):
    missing = SQLiteEventStore(tmp_path / "not-created.db")
    with pytest.raises(TypeError):
        missing.append(RequestedScope(tenant_id="tenant-a", namespace="personal"), event())
    with pytest.raises(TypeError):
        missing.get(RequestedScope(tenant_id="tenant-a", namespace="personal"), "event-1")
    with pytest.raises(ScopeMismatchError):
        missing.append(scope("tenant-b"), event())
    assert not missing.path.exists()
    with pytest.raises(ScopeMismatchError):
        store.append(scope(namespace="other"), event())
    forged = scope().model_copy(update={"tenant_id": "bad/path"})
    with pytest.raises(ValidationError):
        store.count_events(forged)
    unchecked = event().model_copy(update={"tenant_id": "bad/path"})
    with pytest.raises(ValidationError):
        store.append(scope(), unchecked)
    foreign_cursor = EventCursor(
        tenant_id="tenant-b", namespace="personal",
        occurred_at=NOW, ingested_at=NOW, event_id="event-1",
    )
    with pytest.raises(ScopeMismatchError):
        missing.list_events(scope(), after=foreign_cursor)
    bad_cursor = foreign_cursor.model_copy(update={"event_id": "bad/path"})
    with pytest.raises(ValidationError):
        store.list_events(scope(), after=bad_cursor)


def test_keyset_pages_are_bounded_and_scope_specific(store):
    for i in range(7):
        store.append(scope(), event(
            event_id=f"e-{i}", idempotency_key=f"k-{i}",
            occurred_at=NOW + timedelta(microseconds=i),
        ))
    seen = []
    after = None
    while True:
        page = store.list_events(scope(), limit=2, after=after)
        assert len(page.events) <= 2
        seen.extend(item.event_id for item in page.events)
        if page.next_cursor is None:
            break
        assert page.next_cursor.tenant_id == "tenant-a"
        assert page.next_cursor.namespace == "personal"
        after = page.next_cursor
    assert seen == [f"e-{i}" for i in range(7)]
    assert store.list_events(scope(), limit=1000).next_cursor is None
    for invalid in (0, -1, 1001, True, 2.0, "2"):
        with pytest.raises(ValueError):
            store.list_events(scope(), limit=invalid)


def test_immutable_events_have_no_public_mutation_api_and_sql_triggers(store):
    assert not hasattr(store, "update_event")
    assert not hasattr(store, "delete_event")
    assert not hasattr(store, "replace_event")
    store.append(scope(), event())
    with closing(sqlite3.connect(store.path)) as connection, connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE events SET content='altered'")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM events")
    assert store.get(scope(), "event-1") == event()


def test_malformed_json_has_sanitized_error_and_no_content_leak(store):
    store.append(scope(), event())
    with closing(sqlite3.connect(store.path)) as connection, connection:
        connection.execute("DROP TRIGGER events_no_update")
        connection.execute(
            "UPDATE events SET source_reference_json=? WHERE event_id='event-1'",
            ("SENSITIVE SOURCE TEXT {broken",),
        )
        connection.execute(MIGRATION_1[3])
    assert store.status().ready
    with pytest.raises(StoredEventCorruptionError) as captured:
        store.get(scope(), "event-1")
    rendered = "".join(traceback.format_exception(captured.value))
    assert "SENSITIVE SOURCE TEXT" not in str(captured.value)
    assert "SENSITIVE SOURCE TEXT" not in rendered


def test_failed_commit_rolls_back_insert_closes_connection_and_allows_retry(store, monkeypatch):
    import oomp.storage.sqlite as storage_sqlite

    closed = []

    class CommitFailureConnection(sqlite3.Connection):
        fail_commit = True

        def execute(self, statement, parameters=()):
            if statement == "COMMIT" and self.fail_commit:
                self.fail_commit = False
                raise sqlite3.OperationalError("simulated commit failure")
            return super().execute(statement, parameters)

        def close(self):
            closed.append(self)
            return super().close()

    real_connect = sqlite3.connect

    def connect_with_commit_failure(*args, **kwargs):
        return real_connect(*args, factory=CommitFailureConnection, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(storage_sqlite.sqlite3, "connect", connect_with_commit_failure)
        with pytest.raises(StorageUnavailableError):
            store.append(scope(), event())
    assert len(closed) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        closed[0].execute("SELECT 1")
    reopened = SQLiteEventStore(store.path)
    assert reopened.count_events(scope()) == 0
    assert reopened.get(scope(), "event-1") is None
    assert reopened.append(scope(), event()) == event()
    assert reopened.count_events(scope()) == 1


def test_locked_database_is_typed_failure_and_has_no_partial_row(store):
    holder = sqlite3.connect(store.path, isolation_level=None)
    try:
        holder.execute("BEGIN IMMEDIATE")
        waiting = SQLiteEventStore(store.path, busy_timeout_ms=25)
        with pytest.raises(StorageBusyError):
            waiting.append(scope(), event())
    finally:
        holder.execute("ROLLBACK")
        holder.close()
    assert store.count_events(scope()) == 0
    assert store.append(scope(), event()) == event()


def test_threaded_duplicate_writers_use_sqlite_constraints(store):
    retries = [
        event(event_id=f"retry-{i}", ingested_at=NOW + timedelta(seconds=i))
        for i in range(8)
    ]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda item: store.append(scope(), item), retries))
    assert len({result.event_id for result in results}) == 1
    assert store.count_events(scope()) == 1
    assert store.get(scope(), results[0].event_id) == results[0]


def test_two_processes_share_idempotency_through_database(store):
    code = """
import sys
from datetime import datetime, timezone
from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
from oomp.storage import SQLiteEventStore
path, event_id = sys.argv[1:]
now = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)
item = MemoryEvent(
    tenant_id='tenant-a', namespace='personal', event_id=event_id,
    event_type='user_message', source_type='user', content='synthetic',
    source_reference=SourceReference(source_system='test', external_event_id='shared', timestamp=now),
    occurred_at=now, ingested_at=now, idempotency_key='same-delivery',
)
result = SQLiteEventStore(path).append(
    AuthorizedScope(tenant_id='tenant-a', namespace='personal', principal_id='test'), item,
)
print(result.event_id)
"""
    commands = [
        [sys.executable, "-c", code, str(store.path), "process-a"],
        [sys.executable, "-c", code, str(store.path), "process-b"],
    ]
    children = [subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for cmd in commands]
    results = [child.communicate(timeout=15) for child in children]
    assert all(child.returncode == 0 for child in children), results
    assert len({result[0].strip() for result in results}) == 1
    assert store.count_events(scope()) == 1


def test_connections_close_after_each_operation_on_windows(store):
    store.append(scope(), event())
    assert store.get(scope(), "event-1")
    assert store.list_events(scope()).events
    assert store.count_events(scope()) == 1
    assert store.status().ready
    if os.name == "nt":
        renamed = store.path.with_name("renamed.sqlite3")
        store.path.rename(renamed)
        renamed.rename(store.path)
    assert store.get(scope(), "event-1") == event()


def test_uninitialized_database_reads_fail_without_creating_schema(tmp_path):
    path = tmp_path / "empty.db"
    sqlite3.connect(path).close()
    store = SQLiteEventStore(path)
    assert not store.status().ready
    with pytest.raises(DatabaseUninitializedError):
        store.get(scope(), "event-1")
    with closing(sqlite3.connect(path)) as connection, connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0