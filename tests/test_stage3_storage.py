"""Stage 3 schema, canonical memory, provenance, and batch transaction tests."""

from __future__ import annotations

import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from oomp.domain.memories import EntityMention, EntityType, MemoryCursor, MemoryWrite, SourceSpan
from oomp.domain.models import AuthorizedScope, MemoryEvent, MemoryNode, RequestedScope, SourceReference
from oomp.storage import (
    AliasConflictError, DatabaseMissingError, MemoryConflictError,
    ProvenanceMismatchError, SchemaUpgradeRequiredError, ScopeMismatchError,
    SourceEventMissingError, SQLiteEntityStore, SQLiteEventStore, SQLiteMemoryStore,
    StorageCorruptionError, StorageUnavailableError, UnsupportedSchemaVersionError,
)
from oomp.storage.migrations import MIGRATION_1, MIGRATION_2, verify_v1
from oomp.storage.sqlite import _canonical_json, _fingerprint, _timestamp

NOW = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)


def scope(tenant="tenant-a", namespace="personal"):
    return AuthorizedScope(tenant_id=tenant, namespace=namespace, principal_id="local")


def source_ref(external_id="external-1"):
    return SourceReference(source_system="test", external_event_id=external_id, timestamp=NOW)


def event(event_id="e1", *, tenant="tenant-a", namespace="personal", content="I prefer Python.", role="user"):
    return MemoryEvent(
        event_id=event_id, tenant_id=tenant, namespace=namespace,
        event_type="user_message" if role == "user" else "assistant_message",
        source_type=role, content=content, source_reference=source_ref(event_id),
        occurred_at=NOW, ingested_at=NOW,
    )


def node(
    source: MemoryEvent, *, memory_id="m1", key="preference.python",
    content="User prefers Python.", memory_type="profile", sources=None,
    metadata=None, **changes,
):
    evidence = sources or (source,)
    fields = dict(
        memory_id=memory_id, tenant_id=source.tenant_id, namespace=source.namespace,
        memory_type=memory_type, canonical_content=content, canonical_key=key,
        source_event_ids=tuple(item.event_id for item in evidence),
        provenance=tuple(item.source_reference for item in evidence),
        created_at=NOW, updated_at=NOW,
        metadata=metadata if metadata is not None else {"attribution": source.source_type.value, "verified": False},
    )
    fields.update(changes)
    return MemoryNode(**fields)


@pytest.fixture
def stores(tmp_path):
    path = tmp_path / "data" / "oomp.sqlite3"
    events = SQLiteEventStore(path)
    memories = SQLiteMemoryStore(path)
    assert events.initialize() == 2
    return events, memories


def add(events, source):
    events.append(scope(source.tenant_id, source.namespace), source)
    return source


def test_schema_v2_fresh_repeat_and_future_rejection(stores):
    events, memories = stores
    assert events.status().schema_version == 2
    assert events.status().ready
    assert events.initialize() == 2
    with closing(sqlite3.connect(events.path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    with closing(sqlite3.connect(events.path)) as connection, connection:
        connection.execute("PRAGMA user_version=3")
    assert not events.status().ready
    with pytest.raises(UnsupportedSchemaVersionError):
        events.initialize()


def _make_genuine_v1(path, source):
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys=ON")
        for statement in MIGRATION_1:
            connection.execute(statement)
        connection.execute("PRAGMA user_version=1")
        connection.execute(
            """INSERT INTO events (
                tenant_id, namespace, event_id, event_type, source_type, content,
                source_reference_json, occurred_at, ingested_at, idempotency_key,
                metadata_json, payload_fingerprint
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                source.tenant_id, source.namespace, source.event_id,
                source.event_type.value, source.source_type.value, source.content,
                _canonical_json(source.source_reference.model_dump(mode="json")),
                _timestamp(source.occurred_at), _timestamp(source.ingested_at),
                source.idempotency_key, _canonical_json(source.model_dump(mode="json")["metadata"]),
                _fingerprint(source),
            ),
        )
        assert verify_v1(connection)


def test_genuine_v1_event_is_readable_and_upgrades_without_change(tmp_path):
    path = tmp_path / "old.sqlite3"
    original = event()
    _make_genuine_v1(path, original)
    old = SQLiteEventStore(path)
    assert old.get(scope(), "e1") == original
    status = old.status()
    assert status.schema_version == 1 and not status.ready
    assert "upgrade" in status.message
    with pytest.raises(SchemaUpgradeRequiredError):
        SQLiteMemoryStore(path).count_memories(scope())
    with closing(sqlite3.connect(path)) as connection:
        before = connection.execute("SELECT * FROM events").fetchone()
        triggers_before = dict(connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='trigger'"
        ))
    assert old.initialize() == 2
    with closing(sqlite3.connect(path)) as connection:
        after = connection.execute("SELECT * FROM events").fetchone()
        triggers_after = dict(connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='trigger'"
        ))
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert after == before
    assert triggers_after == triggers_before
    assert old.get(scope(), "e1") == original
    assert old.initialize() == 2


def test_failed_v2_migration_preserves_genuine_v1_rows_and_triggers(tmp_path, monkeypatch):
    from oomp.storage import migrations

    path = tmp_path / "old.sqlite3"
    original = event()
    _make_genuine_v1(path, original)
    monkeypatch.setitem(migrations.MIGRATIONS, 2, MIGRATION_2 + ("CREATE TABLE memories (bad TEXT)",))
    with pytest.raises(StorageUnavailableError):
        SQLiteEventStore(path).initialize()
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert verify_v1(connection)
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
    assert SQLiteEventStore(path).get(scope(), "e1") == original
    monkeypatch.setitem(migrations.MIGRATIONS, 2, MIGRATION_2)
    assert SQLiteEventStore(path).initialize() == 2


def test_memory_roundtrip_preserves_all_fields_and_deep_metadata(stores):
    events, memories = stores
    source = add(events, event())
    data = {"nested": {"items": [1, 2.0, "Ω"]}}
    original = node(
        source, status="active", confidence=0.75, tags=("python",),
        valid_from=NOW, valid_until=NOW + timedelta(days=2), metadata=data,
    )
    data["nested"]["items"].append("caller mutation")
    assert original.metadata["nested"]["items"] == (1, 2.0, "Ω")
    assert memories.upsert(scope(), original) == original
    reopened = SQLiteMemoryStore(memories.path)
    assert reopened.get(scope(), "m1") == original
    assert reopened.find_by_canonical_key(scope(), original.canonical_key) == original
    assert reopened.count_memories(scope()) == 1
    assert json.loads(original.model_dump_json())["metadata"]["nested"]["items"] == [1, 2.0, "Ω"]


def test_many_to_many_provenance_and_stable_canonical_identity(stores):
    events, memories = stores
    first = add(events, event("e1"))
    second = add(events, event("e2"))
    old = node(first)
    assert memories.upsert(scope(), old) == old
    duplicate = node(second, memory_id="m-other")
    merged = memories.upsert(scope(), duplicate)
    assert merged.memory_id == "m1"
    assert merged.source_event_ids == ("e1", "e2")
    assert merged.provenance == (first.source_reference, second.source_reference)
    assert merged.updated_at >= old.updated_at
    assert memories.upsert(scope(), duplicate) == merged
    assert memories.count_memories(scope()) == 1
    second_memory = node(first, memory_id="m2", key="decision.local", content="Use local storage.", memory_type="decision")
    memories.upsert(scope(), second_memory)
    assert memories.get(scope(), "m2").source_event_ids == ("e1",)
    assert events.get(scope(), "e1") == first


def test_memory_conflicts_and_distinct_negated_claims(stores):
    events, memories = stores
    source = add(events, event())
    memories.upsert(scope(), node(source))
    with pytest.raises(MemoryConflictError):
        memories.upsert(scope(), node(source, memory_id="m-new", content="User dislikes Python."))
    with pytest.raises(MemoryConflictError):
        memories.upsert(scope(), node(source, key="changed-key"))
    opposite = node(
        source, memory_id="m-negated", key="preference.not-python",
        content="User does not prefer Python.",
    )
    memories.upsert(scope(), opposite)
    assert memories.count_memories(scope()) == 2
    with pytest.raises(MemoryConflictError):
        memories.upsert(scope(), node(source, memory_id="m1", key="preference.not-python"))


def test_missing_forged_and_cross_scope_sources_fail_closed(stores):
    events, memories = stores
    first = add(events, event())
    other_tenant = add(events, event("e2", tenant="tenant-b"))
    other_namespace = add(events, event("e3", namespace="project"))
    for missing in (other_tenant, other_namespace):
        forged = node(first, memory_id="forged", sources=(missing,))
        with pytest.raises(SourceEventMissingError):
            memories.upsert(scope(), forged)
    absent = node(first, memory_id="missing", source_event_ids=("absent",), provenance=(source_ref("absent"),))
    with pytest.raises(SourceEventMissingError):
        memories.upsert(scope(), absent)
    bad_reference = node(first, memory_id="bad-ref", provenance=(source_ref("different"),))
    with pytest.raises(ProvenanceMismatchError):
        memories.upsert(scope(), bad_reference)
    assert memories.count_memories(scope()) == 0


def test_profile_trust_and_attribution_checked_against_all_sources(stores):
    events, memories = stores
    user = add(events, event())
    assistant = add(events, event("assistant-1", role="assistant", content="The user prefers Python."))
    with pytest.raises(ProvenanceMismatchError):
        memories.upsert(scope(), node(assistant, memory_type="profile"))
    with pytest.raises(ProvenanceMismatchError):
        memories.upsert(scope(), node(user, metadata={"verified": True}))
    with pytest.raises(ProvenanceMismatchError):
        memories.upsert(scope(), node(user, metadata={"attribution": "assistant", "verified": False}))
    memories.upsert(scope(), node(user))
    with pytest.raises(ProvenanceMismatchError):
        memories.attach_evidence(scope(), "m1", assistant.event_id)
    assert memories.get(scope(), "m1").source_event_ids == ("e1",)


def test_scoped_reads_bounds_and_keyset_pages(stores):
    events, memories = stores
    first = add(events, event())
    for i in range(5):
        memories.upsert(scope(), node(
            first, memory_id=f"m-{i}", key=f"key-{i}", content=f"Claim {i}",
            created_at=NOW + timedelta(microseconds=i),
            updated_at=NOW + timedelta(microseconds=i),
        ))
    ids = []
    cursor = None
    while True:
        page = memories.list_memories(scope(), limit=2, after=cursor)
        ids.extend(memory.memory_id for memory in page.memories)
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    assert ids == [f"m-{i}" for i in range(5)]
    assert memories.count_memories(scope()) == 5
    assert memories.count_memories(scope("tenant-b")) == 0
    assert memories.get(scope("tenant-b"), "m-0") is None
    assert memories.find_by_canonical_key(scope(namespace="project"), "key-0") is None
    for limit in (0, -1, 101, True, 2.5, "2"):
        with pytest.raises(ValueError):
            memories.list_memories(scope(), limit=limit)
    with pytest.raises(TypeError):
        memories.get(RequestedScope(tenant_id="tenant-a", namespace="personal"), "m-0")
    foreign = MemoryCursor(tenant_id="tenant-b", namespace="personal", created_at=NOW, memory_id="m-0")
    with pytest.raises(ScopeMismatchError):
        memories.list_memories(scope(), after=foreign)


def test_attach_evidence_is_idempotent_and_bounded(stores):
    events, memories = stores
    first = add(events, event())
    second = add(events, event("e2"))
    memories.upsert(scope(), node(first))
    updated = memories.attach_evidence(scope(), "m1", second.event_id)
    assert updated.source_event_ids == ("e1", "e2")
    assert memories.attach_evidence(scope(), "m1", second.event_id) == updated
    assert memories.count_memories(scope()) == 1
    with pytest.raises(SourceEventMissingError):
        memories.attach_evidence(scope(), "m1", "absent")


def test_read_snapshot_stays_consistent_during_evidence_append(stores, monkeypatch):
    events, memories = stores
    if events.status().journal_mode != "wal":
        pytest.skip("concurrent reader snapshot requires WAL")
    first = add(events, event("e1"))
    second = add(events, event("e2"))
    original = memories.upsert(scope(), node(first))
    entered = threading.Event()
    proceed = threading.Event()
    results = []
    errors = []
    real_read = SQLiteMemoryStore._read_memory

    def paused_read(connection, authorized, row):
        if threading.current_thread().name == "snapshot-reader":
            entered.set()
            assert proceed.wait(5)
        return real_read(connection, authorized, row)

    monkeypatch.setattr(SQLiteMemoryStore, "_read_memory", staticmethod(paused_read))

    def read_once():
        try:
            results.append(memories.get(scope(), "m1"))
        except Exception as error:
            errors.append(error)

    reader = threading.Thread(target=read_once, name="snapshot-reader")
    reader.start()
    try:
        assert entered.wait(5)
        updated = memories.attach_evidence(scope(), "m1", second.event_id)
    finally:
        proceed.set()
        reader.join(timeout=5)
    assert not reader.is_alive()
    assert not errors
    assert results == [original]
    assert updated.source_event_ids == ("e1", "e2")
    assert memories.get(scope(), "m1") == updated


def test_concurrent_duplicate_memory_upserts_union_evidence(stores):
    events, memories = stores
    sources = [add(events, event(f"e{i}")) for i in range(6)]
    candidates = [node(source, memory_id=f"candidate-{i}") for i, source in enumerate(sources)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda item: memories.upsert(scope(), item), candidates))
    assert len({result.memory_id for result in results}) == 1
    assert memories.count_memories(scope()) == 1
    merged = memories.get(scope(), results[0].memory_id)
    assert set(merged.source_event_ids) == {source.event_id for source in sources}


def test_source_cap_rejects_whole_new_memory(stores, monkeypatch):
    import oomp.storage.memory_store as module

    events, memories = stores
    sources = [add(events, event(f"e{i}")) for i in range(3)]
    monkeypatch.setattr(module, "_MAX_SOURCES", 2)
    candidate = node(sources[0], sources=tuple(sources))
    with pytest.raises(ValueError):
        memories.upsert(scope(), candidate)
    assert memories.count_memories(scope()) == 0


def test_entity_link_cap_rolls_back_memory_and_entities(stores, monkeypatch):
    import oomp.storage.memory_store as module

    events, memories = stores
    source = add(events, event(content="OOMP and TRACE are named projects."))
    monkeypatch.setattr(module, "_MAX_ENTITIES_PER_MEMORY", 1)
    write = MemoryWrite(
        memory=node(source, memory_type="project_state", content="Projects are named."),
        entities=(
            EntityMention(name="OOMP", entity_type="project", source_event_id=source.event_id),
            EntityMention(name="TRACE", entity_type="project", source_event_id=source.event_id),
        ),
    )
    with pytest.raises(ValueError):
        memories.apply_batch(scope(), source.event_id, (write,))
    assert memories.count_memories(scope()) == 0
    assert SQLiteEntityStore(memories.path).count_entities(scope()) == 0


def test_apply_batch_is_atomic_after_second_write_fails(stores):
    events, memories = stores
    source = add(events, event(content="OOMP (Object-Oriented Context Map) is local."))
    span_text = "OOMP (Object-Oriented Context Map)"
    mention = EntityMention(
        name="OOMP", entity_type=EntityType.PROJECT,
        aliases=("Object-Oriented Context Map",),
        source_event_id=source.event_id,
        source_span=SourceSpan(start=0, end=len(span_text), quote=span_text),
    )
    first = MemoryWrite(
        memory=node(source, memory_id="first", key="first", content="Project OOMP exists.", memory_type="project_state"),
        entities=(mention,),
    )
    second = MemoryWrite(
        memory=node(source, memory_id="second", key="second", content="Another claim.", memory_type="semantic"),
        source_span=SourceSpan(start=0, end=4, quote="WRONG"),
    )
    with pytest.raises(ProvenanceMismatchError):
        memories.apply_batch(scope(), source.event_id, (first, second))
    reopened = SQLiteMemoryStore(memories.path)
    assert reopened.count_memories(scope()) == 0
    assert SQLiteEntityStore(memories.path).count_entities(scope()) == 0
    assert events.get(scope(), source.event_id) == source


def test_apply_batch_counts_retry_and_entity_links(stores):
    events, memories = stores
    source = add(events, event(content="OOMP (Object-Oriented Context Map) is local."))
    quote = "OOMP (Object-Oriented Context Map)"
    span = SourceSpan(start=0, end=len(quote), quote=quote)
    mention = EntityMention(
        name="OOMP", entity_type="project", aliases=("Object-Oriented Context Map",),
        source_event_id=source.event_id, source_span=span,
    )
    write = MemoryWrite(
        memory=node(source, content="OOMP is local.", memory_type="project_state"),
        source_span=span, entities=(mention,),
    )
    first = memories.apply_batch(scope(), source.event_id, (write,))
    assert (first.candidates_extracted, first.memories_created, first.memories_reused) == (1, 1, 0)
    assert (first.evidence_links_added, first.entities_created, first.entities_reused) == (1, 1, 0)
    assert first.memory_ids == ("m1",)
    second = memories.apply_batch(scope(), source.event_id, (write,))
    assert (second.memories_created, second.memories_reused, second.evidence_links_added) == (0, 1, 0)
    assert (second.entities_created, second.entities_reused) == (0, 1)
    assert memories.list_entities(scope(), "m1")[0].canonical_name == "OOMP"
    assert memories.count_memories(scope()) == 1