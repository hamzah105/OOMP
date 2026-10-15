"""Stage 4 SQLite graph migration, identity, scope, and history checks."""
from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest

from oomp.domain.graph import TemporalQuery
from oomp.domain.models import AuthorizedScope, MemoryEdge, MemoryEvent, MemoryNode, SourceReference
from oomp.storage import (
    GraphConflictError, GraphLimitError, MemoryNotFoundError, SQLiteEventStore,
    SQLiteGraphStore, SQLiteMemoryStore, SQLiteEntityStore, ScopeMismatchError, SourceEventMissingError,
    StorageUnavailableError,
)
from oomp.storage.migrations import MIGRATION_1, MIGRATION_2, MIGRATION_3, verify_v2
from oomp.storage.memory_store import _memory_fingerprint
from oomp.storage.sqlite import _canonical_json, _fingerprint, _timestamp

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def scope(tenant="tenant", namespace="ns"):
    return AuthorizedScope(tenant_id=tenant, namespace=namespace, principal_id="tester")


def event(event_id, *, tenant="tenant", namespace="ns", content="A"):
    ref = SourceReference(source_system="test", external_event_id=event_id, timestamp=NOW)
    return MemoryEvent(
        event_id=event_id, tenant_id=tenant, namespace=namespace,
        event_type="user_message", source_type="user", content=content,
        source_reference=ref, occurred_at=NOW, ingested_at=NOW,
    )


def node(source, memory_id, *, valid_from=None, valid_until=None):
    return MemoryNode(
        memory_id=memory_id, tenant_id=source.tenant_id, namespace=source.namespace,
        memory_type="semantic", canonical_key=memory_id, canonical_content=source.content,
        source_event_ids=(source.event_id,), provenance=(source.source_reference,),
        created_at=NOW, updated_at=NOW,
        valid_from=valid_from, valid_until=valid_until,
        metadata={"attribution": "user", "verified": False},
    )


def edge(source, target, source_event, *, edge_id="edge-1", relation="RELATED_TO",
         valid_from=None, valid_until=None):
    return MemoryEdge(
        edge_id=edge_id, tenant_id=source.tenant_id, namespace=source.namespace,
        source_node_id=source.memory_id, target_node_id=target.memory_id,
        relationship_type=relation, source_event_ids=(source_event.event_id,),
        created_at=NOW, valid_from=valid_from, valid_until=valid_until,
    )


@pytest.fixture
def graph(tmp_path):
    path = tmp_path / "graph.sqlite3"
    events, memories, links = SQLiteEventStore(path), SQLiteMemoryStore(path), SQLiteGraphStore(path)
    assert events.initialize() == 4
    first, second = event("e1", content="First."), event("e2", content="Second.")
    for source in (first, second):
        events.append(scope(), source)
    left, right = node(first, "m1"), node(second, "m2")
    memories.upsert(scope(), left)
    memories.upsert(scope(), right)
    return events, memories, links, (left, right), (first, second)


def test_fresh_schema_recording_triggers_and_restart(graph):
    events, memories, links, (left, right), (first, _) = graph
    with closing(sqlite3.connect(events.path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT COUNT(*) FROM memory_recordings").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM memory_source_recordings").fetchone()[0] == 2
    original = links.add_edge(scope(), edge(left, right, first))
    assert original.recorded_at == original.evidence[0].recorded_at
    assert SQLiteGraphStore(events.path).get_edge(scope(), original.edge.edge_id) == original
    assert events.initialize() == 4
    with closing(sqlite3.connect(events.path)) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE memory_edges SET status='retracted' WHERE edge_id='edge-1'")


def test_genuine_v2_with_memory_migrates_and_failed_upgrade_rolls_back(tmp_path, monkeypatch):
    path = tmp_path / "old.sqlite3"
    source = event("old", content="OOMP (Object-Oriented Context Map).")
    memory = node(source, "legacy")
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys=ON")
        for statement in (*MIGRATION_1, *MIGRATION_2):
            connection.execute(statement)
        connection.execute("PRAGMA user_version=2")
        connection.execute(
            """INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                source.tenant_id, source.namespace, source.event_id,
                source.event_type.value, source.source_type.value, source.content,
                _canonical_json(source.source_reference.model_dump(mode="json")),
                _timestamp(source.occurred_at), _timestamp(source.ingested_at),
                None, "{}", _fingerprint(source),
            ),
        )
        connection.execute(
            """INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                memory.tenant_id, memory.namespace, memory.memory_id,
                memory.memory_type.value, memory.canonical_key,
                memory.canonical_content, memory.status.value,
                _timestamp(memory.created_at), _timestamp(memory.updated_at),
                None, None, None, "[]",
                _canonical_json(memory.model_dump(mode="json")["metadata"]),
                _memory_fingerprint(memory),
            ),
        )
        connection.execute(
            """INSERT INTO memory_sources VALUES (?,?,?,?,?,?,?)""",
            (scope().tenant_id, scope().namespace, memory.memory_id, source.event_id,
             0, None, "manual"),
        )
        connection.execute(
            "INSERT INTO entities VALUES (?,?,?,?,?,?,?)",
            ("tenant", "ns", "entity-old", "project", "OOMP", "oomp", _timestamp(NOW)),
        )
        connection.execute(
            "INSERT INTO entity_aliases VALUES (?,?,?,?,?,?,?)",
            ("tenant", "ns", "project", "object-oriented context map",
             "Object-Oriented Context Map", "entity-old", "old"),
        )
        connection.execute(
            "INSERT INTO memory_entities VALUES (?,?,?,?)",
            ("tenant", "ns", "legacy", "entity-old"),
        )
        assert verify_v2(connection)
    tables = ("events", "memories", "memory_sources", "entities", "entity_aliases", "memory_entities")
    with closing(sqlite3.connect(path)) as connection:
        before = {table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in tables}
        event_triggers = connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND name GLOB 'events_*' ORDER BY name"
        ).fetchall()
    old = SQLiteEventStore(path)
    assert old.status().schema_version == 2 and not old.status().ready
    import oomp.storage.migrations as migrations
    monkeypatch.setitem(migrations.MIGRATIONS, 3, MIGRATION_3 + ("CREATE TABLE memories (bad TEXT)",))
    with pytest.raises(StorageUnavailableError):
        old.initialize()
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert verify_v2(connection)
        assert connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 1
        assert {table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in tables} == before
    monkeypatch.setitem(migrations.MIGRATIONS, 3, MIGRATION_3)
    assert old.initialize() == 4
    with closing(sqlite3.connect(path)) as connection:
        assert {table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in tables} == before
        assert connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND name GLOB 'events_*' ORDER BY name"
        ).fetchall() == event_triggers
    assert old.get(scope(), source.event_id) == source
    assert SQLiteMemoryStore(path).get(scope(), memory.memory_id) == memory
    assert SQLiteEntityStore(path).get(scope(), "entity-old").aliases == ("Object-Oriented Context Map",)
    assert SQLiteMemoryStore(path).list_entities(scope(), "legacy")[0].entity_id == "entity-old"
    state = SQLiteGraphStore(path).memory_state(
        scope(), memory.memory_id, TemporalQuery(known_at=NOW)
    )
    assert state.known is None and state.source_event_ids == ()
    current = SQLiteGraphStore(path).memory_state(scope(), memory.memory_id)
    assert current.known is True and current.legacy_recording_unknown
    assert current.evidence[0].recorded_at is None


def test_edge_retry_new_proof_and_scope_boundaries(graph):
    events, memories, links, (left, right), (first, second) = graph
    initial = links.add_edge(scope(), edge(left, right, first))
    retry = edge(left, right, first, edge_id="other", relation="RELATED_TO")
    assert links.add_edge(scope(), retry).edge.edge_id == "edge-1"
    additional = edge(left, right, second, edge_id="third")
    merged = links.add_edge(scope(), additional)
    assert merged.edge.source_event_ids == ("e1", "e2")
    assert links.add_edge(scope(), additional) == merged
    assert len(links.list_edges(scope()).edges) == 1
    with pytest.raises(GraphConflictError):
        links.add_edge(scope(), edge(left, right, first, relation="RELATED_TO",
                                     valid_from=NOW, edge_id="edge-1"))
    with pytest.raises(GraphConflictError):
        links.add_edge(scope(), edge(left, right, first, relation="CONTRADICTS"))
    with pytest.raises(MemoryNotFoundError):
        links.add_edge(scope(), edge(left, node(first, "absent"), first, edge_id="absent-edge"))
    with pytest.raises(ScopeMismatchError):
        links.add_edge(scope("other"), edge(left, right, first, edge_id="scope-edge"))
    with pytest.raises(SourceEventMissingError):
        links.add_edge(scope(), edge(left, right, event("missing"), edge_id="missing-edge"))
    assert links.get_edge(scope("other"), "edge-1") is None


def test_cycles_traversal_filters_and_concurrent_retries(graph):
    events, memories, links, (left, right), (first, second) = graph
    third = node(first, "m3")
    memories.upsert(scope(), third)
    def write(i):
        return SQLiteGraphStore(events.path).add_edge(
            scope(), edge(left, right, first, edge_id=f"parallel-{i}")
        ).edge.edge_id
    with ThreadPoolExecutor(max_workers=4) as pool:
        winners = set(pool.map(write, range(4)))
        assert len(winners) == 1 and winners <= {f"parallel-{i}" for i in range(4)}
    links.add_edge(scope(), edge(right, third, second, edge_id="edge-23", relation="PART_OF"))
    with pytest.raises(GraphConflictError):
        links.add_edge(scope(), edge(third, right, first, edge_id="edge-32", relation="PART_OF"))
    links.add_edge(scope(), edge(third, left, first, edge_id="edge-31"))
    assert links.traverse(scope(), "m1", max_depth=0).node_ids == ("m1",)
    result = links.traverse(scope(), "m1", max_depth=2, max_nodes=2)
    assert len(result.node_ids) == 2 and result.truncated
    assert all(
        item.edge.source_node_id in result.node_ids and item.edge.target_node_id in result.node_ids
        for item in result.edges
    )
    filtered = links.traverse(
        scope(), "m1", max_depth=3, allowed_relationships=("PART_OF",)
    )
    assert filtered.node_ids == ("m1",)
    with pytest.raises(ValueError):
        links.traverse(scope(), "m1", max_depth=True)