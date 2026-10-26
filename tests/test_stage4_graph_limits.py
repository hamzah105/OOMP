"""Bounded graph reads and all-or-nothing edge writes."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pytest

from oomp.domain.graph import EdgeCursor
from oomp.domain.models import AuthorizedScope, MemoryEdge, MemoryEvent, MemoryNode, SourceReference
from oomp.storage import SQLiteEventStore, SQLiteGraphStore, SQLiteMemoryStore
import oomp.storage.graph_store as graph_store_module
from oomp.storage.errors import (
    GraphLimitError, MemoryNotFoundError, ScopeMismatchError,
    SourceEventMissingError, StorageUnavailableError,
)

SCOPE = AuthorizedScope(tenant_id="limit-tenant", namespace="graph", principal_id="tester")
WHEN = datetime(2026, 1, 1, tzinfo=timezone.utc)


def source(event_id: str) -> MemoryEvent:
    return MemoryEvent(
        event_id=event_id, tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
        event_type="user_message", source_type="user", content="Synthetic assertion.",
        source_reference=SourceReference(
            source_system="test", external_event_id=event_id, timestamp=WHEN,
        ),
        occurred_at=WHEN, ingested_at=WHEN,
    )


def memory(memory_id: str, event: MemoryEvent) -> MemoryNode:
    return MemoryNode(
        memory_id=memory_id, tenant_id=event.tenant_id, namespace=event.namespace,
        memory_type="semantic", canonical_key="limit:" + memory_id,
        canonical_content=event.content,
        source_event_ids=(event.event_id,), provenance=(event.source_reference,),
        created_at=WHEN, updated_at=WHEN,
    )


def edge(edge_id: str, target_id: str, evidence: tuple[str, ...]) -> MemoryEdge:
    return MemoryEdge(
        edge_id=edge_id, tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
        source_node_id="root", target_node_id=target_id,
        relationship_type="RELATED_TO", source_event_ids=evidence,
        created_at=WHEN,
    )


@pytest.fixture
def fixture(tmp_path: Path):
    path = tmp_path / "limits.sqlite3"
    events = SQLiteEventStore(path)
    assert events.initialize() == 5
    first, second = source("proof-1"), source("proof-2")
    for item in (first, second):
        events.append(SCOPE, item)
    memories = SQLiteMemoryStore(path)
    for memory_id in ("root", "a", "b", "c"):
        memories.upsert(SCOPE, memory(memory_id, first))
    return path, SQLiteGraphStore(path)


def test_second_evidence_failure_rolls_back_edge_and_first_evidence(fixture, monkeypatch) -> None:
    path, graph = fixture
    connect = graph._connect

    def connection_with_fault(mode: str):
        connection = connect(mode)
        if mode == "rw":
            connection.execute(
                """CREATE TEMP TRIGGER test_fail_second_proof
                   BEFORE INSERT ON main.edge_evidence
                   WHEN NEW.event_id='proof-2'
                   BEGIN SELECT RAISE(ABORT, 'test failure'); END"""
            )
        return connection

    monkeypatch.setattr(graph, "_connect", connection_with_fault)
    with pytest.raises(StorageUnavailableError):
        graph.add_edge(SCOPE, edge("partial", "a", ("proof-1", "proof-2")))
    monkeypatch.setattr(graph, "_connect", connect)
    assert graph.list_edges(SCOPE).edges == ()
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM memory_edges").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM edge_evidence").fetchone()[0] == 0
    committed = graph.add_edge(SCOPE, edge("partial", "a", ("proof-1", "proof-2")))
    assert committed.edge.source_event_ids == ("proof-1", "proof-2")


def test_complete_fanout_bound_and_stable_edge_pagination(fixture) -> None:
    _, graph = fixture
    for memory_id in ("a", "b", "c"):
        graph.add_edge(SCOPE, edge("to-" + memory_id, memory_id, ("proof-1",)))
    with pytest.raises(GraphLimitError):
        graph.neighbors(SCOPE, "root", direction="outgoing", limit=2)
    first = graph.list_edges(SCOPE, source_node_id="root", limit=2)
    assert len(first.edges) == 2 and first.next_cursor is not None
    second = graph.list_edges(SCOPE, source_node_id="root", limit=2, after=first.next_cursor)
    assert len(second.edges) == 1 and second.next_cursor is None
    assert {item.edge.edge_id for item in (*first.edges, *second.edges)} == {
        "to-a", "to-b", "to-c",
    }
    assert graph.traverse(SCOPE, "root", max_depth=1, max_nodes=2).truncated


def test_oversized_evidence_batch_is_rejected_before_write(fixture) -> None:
    _, graph = fixture
    evidence = tuple(f"proof-{number}" for number in range(1001))
    with pytest.raises(GraphLimitError):
        graph.add_edge(SCOPE, edge("too-many", "a", evidence))
    assert graph.list_edges(SCOPE).edges == ()


def test_foreign_endpoint_evidence_cursor_and_reads_fail_scoped(fixture) -> None:
    path, graph = fixture
    foreign = AuthorizedScope(
        tenant_id=SCOPE.tenant_id, namespace="foreign",
        principal_id="tester",
    )
    foreign_event = MemoryEvent.model_validate({
        **source("foreign-proof").model_dump(mode="json"),
        "namespace": foreign.namespace,
    })
    SQLiteEventStore(path).append(foreign, foreign_event)
    SQLiteMemoryStore(path).upsert(foreign, memory("foreign-node", foreign_event))
    with pytest.raises(MemoryNotFoundError):
        graph.add_edge(SCOPE, edge("wrong-endpoint", "foreign-node", ("proof-1",)))
    with pytest.raises(SourceEventMissingError):
        graph.add_edge(SCOPE, edge("wrong-proof", "a", (foreign_event.event_id,)))
    assert graph.get_edge(foreign, "wrong-proof") is None
    with pytest.raises(MemoryNotFoundError):
        graph.neighbors(foreign, "root")

    graph.add_edge(SCOPE, edge("first", "a", ("proof-1",)))
    graph.add_edge(SCOPE, edge("second", "b", ("proof-1",)))
    cursor = graph.list_edges(SCOPE, limit=1).next_cursor
    assert cursor is not None
    with pytest.raises(ScopeMismatchError):
        graph.list_edges(foreign, after=cursor)
    forged = EdgeCursor(
        tenant_id=foreign.tenant_id, namespace=foreign.namespace,
        recorded_at=cursor.recorded_at, edge_id=cursor.edge_id,
    )
    with pytest.raises(ScopeMismatchError):
        graph.list_edges(SCOPE, after=forged)


def test_read_transaction_keeps_one_proof_snapshot_during_writer_addition(fixture) -> None:
    path, graph = fixture
    first = graph.add_edge(SCOPE, edge("shared", "a", ("proof-1",)))
    with graph._graph_read() as connection:
        row = connection.execute(
            """SELECT * FROM memory_edges
               WHERE tenant_id=? AND namespace=? AND edge_id=?""",
            (SCOPE.tenant_id, SCOPE.namespace, first.edge.edge_id),
        ).fetchone()
        assert row is not None
        newer = SQLiteGraphStore(path).add_edge(
            SCOPE, edge("different-request-id", "a", ("proof-2",)),
        )
        older = graph._read_edge(connection, SCOPE, row)
        assert older is not None
        assert older.edge.source_event_ids == ("proof-1",)
    assert newer.edge.source_event_ids == ("proof-1", "proof-2")
    assert graph.get_edge(SCOPE, "shared").edge.source_event_ids == (
        "proof-1", "proof-2",
    )

def test_aggregate_read_proof_budget_rejects_complete_result(fixture, monkeypatch) -> None:
    _, graph = fixture
    for target in ("a", "b"):
        graph.add_edge(SCOPE, edge("proofs-to-" + target, target, ("proof-1", "proof-2")))
    monkeypatch.setattr(graph_store_module, "_MAX_RESULT_EVIDENCE", 3)
    with pytest.raises(GraphLimitError, match="evidence budget"):
        graph.list_edges(SCOPE)
    with pytest.raises(GraphLimitError, match="evidence budget"):
        graph.neighbors(SCOPE, "root")
    assert len(graph.get_edge(SCOPE, "proofs-to-a").evidence) == 2
    assert len(graph.get_edge(SCOPE, "proofs-to-b").evidence) == 2