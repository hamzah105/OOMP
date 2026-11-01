"""P4 owner-filtered reads over fresh synthetic stores; no provider calls."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from oomp.domain.enums import MemoryStatus, RelationshipType
from oomp.domain.graph import TemporalQuery
from oomp.domain.models import AuthorizedScope, MemoryEdge, MemoryEvent, MemoryNode, SourceReference
from oomp.graph import GraphService
from oomp.storage.errors import EmbeddingSpaceError, GraphLimitError, MemoryNotFoundError, RetrievalLimitError
from oomp.storage.graph_store import SQLiteGraphStore
from oomp.storage.memory_store import SQLiteMemoryStore
from oomp.storage.mind_projection_store import SQLiteMindProjectionStore
from oomp.storage.retrieval_store import SQLiteRetrievalStore, content_digest
from oomp.storage.sqlite import SQLiteEventStore
from oomp.retrieval.contracts import EmbeddingSpace


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
OWNER = AuthorizedScope(tenant_id="p4-security", namespace="synthetic", principal_id="owner")
OTHER = OWNER.model_copy(update={"principal_id": "another-owner"})
SPACE = EmbeddingSpace(provider="synthetic", model="owner-fixture", version="1", dimension=2)


@pytest.fixture
def path(tmp_path):
    result = tmp_path / "synthetic.sqlite3"
    assert SQLiteEventStore(result).initialize() == 6
    return result


def add(path, identifier, *, scope=OWNER, text=None, event_owner=True,
        memory_owner=None, source_ids=None, canonical_id=None, valid_from=None, valid_until=None,
        when=NOW, source_metadata=None):
    text = text or f"Synthetic project {identifier} uses a technical notebook."
    event = MemoryEvent(event_id="event-" + identifier, tenant_id=scope.tenant_id,
        namespace=scope.namespace, event_type="user_message", source_type="user", content=text,
        source_reference=SourceReference(source_system="synthetic-p4-security",
            external_event_id=identifier, timestamp=when), occurred_at=when, ingested_at=when,
        metadata=(source_metadata if source_metadata is not None else
                  {"ingested_by": scope.principal_id} if event_owner else {}))
    sources = SQLiteEventStore(path)
    sources.append(scope, event)
    events = (event,) if source_ids is None else tuple(sources.get(scope, item) for item in source_ids)
    metadata = {"attribution": "user", "verified": False}
    if memory_owner is not None:
        metadata["principal_id"] = memory_owner
    memory = MemoryNode(memory_id=canonical_id or "memory-" + identifier,
        tenant_id=scope.tenant_id, namespace=scope.namespace, memory_type="semantic",
        canonical_key=canonical_id or "synthetic:" + identifier, canonical_content=text,
        source_event_ids=tuple(item.event_id for item in events),
        provenance=tuple(item.source_reference for item in events),
        created_at=when, updated_at=when, valid_from=valid_from, valid_until=valid_until,
        metadata=metadata)
    return event, SQLiteMemoryStore(path).upsert(scope, memory)


def vector(path, memory, scope=OWNER):
    return SQLiteRetrievalStore(path).put_embedding_batch(scope, SPACE,
        ((memory.memory_id, content_digest(memory.canonical_content), (1.0, 0.0)),))


def edge(path, identifier, first, second, event, *, actor=OWNER):
    value = MemoryEdge(edge_id=identifier, tenant_id=actor.tenant_id, namespace=actor.namespace,
        source_node_id=first.memory_id, target_node_id=second.memory_id,
        relationship_type=RelationshipType.RELATED_TO, source_event_ids=(event.event_id,), created_at=NOW)
    return SQLiteGraphStore(path).add_edge(actor, value)


def test_principal_filter_precedes_corpus_and_bm25_limits(path):
    _, own = add(path, "owner")
    store = SQLiteRetrievalStore(path, max_lexical_docs=1)
    with store.read_snapshot(OWNER, principal_only=True) as session:
        before = session.lexical("technical", limit=1)
        assert [item.memory_id for item in before] == [own.memory_id]
    for index in range(4):
        add(path, f"foreign-{index}", scope=OTHER, text="Technical technical project " + str(index))
    with store.read_snapshot(OWNER) as legacy:
        with pytest.raises(RetrievalLimitError):
            legacy.lexical("technical", limit=1)
    with store.read_snapshot(OWNER, principal_only=True) as session:
        assert session.lexical("technical", limit=1) == before
        assert session.index_status().canonical_count == 1
        assert session.index_status().lexical_count == 1


def test_legacy_unknown_principal_remains_available_only_in_legacy_mode(path):
    source, memory = add(path, "unmapped", event_owner=False)
    store = SQLiteRetrievalStore(path)
    with store.read_snapshot(OWNER) as legacy:
        assert legacy.memory(memory.memory_id) is not None
        assert legacy.lexical("notebook")
    with store.read_snapshot(OWNER, principal_only=True) as session:
        assert not session.owns_event(source.event_id)
        assert not session.owns_memory(memory.memory_id)
        assert session.memory(memory.memory_id) is None
        assert session.lexical("notebook") == ()
        with pytest.raises(MemoryNotFoundError):
            session.memory_state(memory.memory_id, TemporalQuery())


@pytest.mark.parametrize("principal", [None, True, 1, "another-owner", ["owner"], {"principal": "owner"}])
def test_source_owner_requires_an_exact_explicit_string(path, principal):
    source, memory = add(path, "unowned", source_metadata={"ingested_by": principal})
    with SQLiteRetrievalStore(path).read_snapshot(OWNER, principal_only=True) as session:
        assert not session.owns_event(source.event_id)
        assert not session.owns_memory(memory.memory_id)
        assert session.lexical("notebook") == ()


@pytest.mark.parametrize("principal", ["owner", "another-owner", ""])
def test_explicit_memory_principal_cannot_override_source_owner(path, principal):
    _, memory = add(path, "principal", memory_owner=principal)
    with SQLiteRetrievalStore(path).read_snapshot(OWNER, principal_only=True) as session:
        assert session.owns_memory(memory.memory_id) is (principal == OWNER.principal_id)


def test_same_namespace_foreign_and_other_tenant_records_are_invisible(path):
    _, own = add(path, "owner")
    foreign_source, foreign = add(path, "foreign", scope=OTHER)
    tenant = OWNER.model_copy(update={"tenant_id": "another-tenant"})
    _, foreign_tenant = add(path, "foreign-tenant", scope=tenant)
    with SQLiteRetrievalStore(path).read_snapshot(OWNER, principal_only=True) as session:
        assert session.memory(own.memory_id) is not None
        assert session.memory(foreign.memory_id) is None
        assert session.memory(foreign_tenant.memory_id) is None
        assert not session.owns_event(foreign_source.event_id)
        assert session.index_status().canonical_count == 1


def test_one_foreign_proof_withholds_entire_mixed_memory(path):
    own_event, _ = add(path, "first")
    foreign_event, _ = add(path, "foreign", scope=OTHER)
    _, mixed = add(path, "mixed", source_ids=(own_event.event_id, foreign_event.event_id))
    with SQLiteRetrievalStore(path).read_snapshot(OWNER) as legacy:
        assert len(legacy.memory(mixed.memory_id).source_event_ids) == 2
    with SQLiteRetrievalStore(path).read_snapshot(OWNER, principal_only=True) as session:
        assert not session.owns_memory(mixed.memory_id)
        assert session.memory(mixed.memory_id) is None


@pytest.mark.parametrize("cache", ["absent", "stale", "invalid"])
def test_foreign_vectors_do_not_affect_completeness_or_scan_limits(path, cache):
    _, own = add(path, "owner")
    _, foreign = add(path, "foreign", scope=OTHER)
    vector(path, own)
    if cache != "absent":
        vector(path, foreign, OTHER)
        with closing(sqlite3.connect(path)) as connection, connection:
            if cache == "stale":
                connection.execute("UPDATE memory_embeddings SET content_digest=? WHERE memory_id=?",
                    ("0" * 64, foreign.memory_id))
            else:
                connection.execute("UPDATE memory_embeddings SET vector_blob=? WHERE memory_id=?",
                    (b"invalid-synthetic-cache", foreign.memory_id))
    with SQLiteRetrievalStore(path).read_snapshot(OWNER, principal_only=True) as session:
        assert [item.memory_id for item in session.semantic((1.0, 0.0), SPACE,
            scan_limit=1, limit=1)] == [own.memory_id]
        status = session.index_status(SPACE)
        assert status.canonical_count == status.compatible_embeddings == 1
        assert status.stale_embeddings == 0


def test_owner_missing_or_stale_vectors_still_fail_closed(path):
    _, own = add(path, "owner")
    _, other = add(path, "second-owned")
    vector(path, own)
    with SQLiteRetrievalStore(path).read_snapshot(OWNER, principal_only=True) as session:
        with pytest.raises(EmbeddingSpaceError, match="incomplete"):
            session.semantic((1.0, 0.0), SPACE)
    vector(path, other)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("UPDATE memory_embeddings SET content_digest=? WHERE memory_id=?",
            ("0" * 64, other.memory_id))
    with SQLiteRetrievalStore(path).read_snapshot(OWNER, principal_only=True) as session:
        with pytest.raises(EmbeddingSpaceError, match="stale"):
            session.semantic((1.0, 0.0), SPACE)


def test_entity_membership_filter_is_applied_before_candidate_limit(path):
    _, own = add(path, "owner")
    foreign = [add(path, f"foreign-{i}", scope=OTHER)[1] for i in range(3)]
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("""INSERT INTO entities
            (tenant_id,namespace,entity_id,entity_type,canonical_name,normalized_name,created_at)
            VALUES (?,?,?,'project','Shared fixture','shared fixture',?)""",
            (OWNER.tenant_id, OWNER.namespace, "entity-shared", "2026-01-01T00:00:00.000000Z"))
        connection.executemany("INSERT INTO memory_entities VALUES (?,?,?,?)",
            [(OWNER.tenant_id, OWNER.namespace, m.memory_id, "entity-shared") for m in [own, *foreign]])
    with SQLiteRetrievalStore(path).read_snapshot(OWNER, principal_only=True) as session:
        assert [hit.memory_id for hit in session.entity_candidates(("Shared fixture",), limit=1)] == [own.memory_id]
    with SQLiteRetrievalStore(path).read_snapshot(OWNER) as legacy:
        with pytest.raises(RetrievalLimitError):
            legacy.entity_candidates(("Shared fixture",), limit=1)


def test_foreign_alias_source_cannot_add_a_retrieval_signal(path):
    _, own = add(path, "owner")
    foreign, _ = add(path, "foreign", scope=OTHER)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("INSERT INTO entities VALUES (?,?,?,'project','Owner entity','owner entity',?)",
            (OWNER.tenant_id, OWNER.namespace, "entity-owner", "2026-01-01T00:00:00.000000Z"))
        connection.execute("INSERT INTO memory_entities VALUES (?,?,?,?)",
            (OWNER.tenant_id, OWNER.namespace, own.memory_id, "entity-owner"))
        connection.execute("INSERT INTO entity_aliases VALUES (?,?,?,'foreign alias','Foreign alias',?,?)",
            (OWNER.tenant_id, OWNER.namespace, "project", "entity-owner", foreign.event_id))
    with SQLiteRetrievalStore(path).read_snapshot(OWNER, principal_only=True) as session:
        assert session.entity_candidates(("Foreign alias",)) == ()


def test_foreign_topic_catalog_and_memberships_do_not_consume_owner_limits(path):
    _, own = add(path, "owner")
    _, foreign = add(path, "foreign", scope=OTHER)
    with closing(sqlite3.connect(path)) as connection, connection:
        topics = [(OWNER.tenant_id, OWNER.namespace, f"a-foreign-{i}", "Other topic", None,
            "2026-01-01T00:00:00.000000Z") for i in range(501)]
        topics.append((OWNER.tenant_id, OWNER.namespace, "z-owner", "Owner topic", None,
            "2026-01-01T00:00:00.000000Z"))
        connection.executemany("INSERT INTO topics VALUES (?,?,?,?,?,?)", topics)
        connection.executemany("INSERT INTO topic_memberships VALUES (?,?,?,?,?)",
            [(OWNER.tenant_id, OWNER.namespace, f"a-foreign-{i}", foreign.memory_id,
              "2026-01-01T00:00:00.000000Z") for i in range(501)] +
            [(OWNER.tenant_id, OWNER.namespace, "z-owner", own.memory_id, "2026-01-01T00:00:00.000000Z"),
             (OWNER.tenant_id, OWNER.namespace, "z-owner", foreign.memory_id, "2026-01-01T00:00:00.000000Z")])
    with SQLiteRetrievalStore(path).read_snapshot(OWNER) as legacy:
        with pytest.raises(RetrievalLimitError, match="catalog"):
            legacy.topic_candidates(("Owner topic",), limit=1)
    with SQLiteRetrievalStore(path).read_snapshot(OWNER, principal_only=True) as session:
        assert [hit.memory_id for hit in session.topic_candidates(("Owner topic",), limit=1)] == [own.memory_id]


def test_graph_filter_precedes_fanout_and_keeps_owner_relation(path):
    own_source, own = add(path, "owner")
    _, related = add(path, "related-owner")
    foreign_source, foreign = add(path, "foreign", scope=OTHER)
    allowed = edge(path, "edge-owner", own, related, own_source)
    edge(path, "edge-foreign", foreign, own, foreign_source, actor=OTHER)
    with SQLiteRetrievalStore(path).read_snapshot(OWNER) as legacy:
        with pytest.raises(GraphLimitError):
            legacy.neighbors(own.memory_id, limit=1)
    with SQLiteRetrievalStore(path).read_snapshot(OWNER, principal_only=True) as session:
        records = session.neighbors(own.memory_id, limit=1)
        assert [item.edge.edge_id for item in records] == [allowed.edge.edge_id]
        result = session.traverse(own.memory_id, max_depth=1, max_nodes=3,
            allowed_relationships=(RelationshipType.RELATED_TO,), query=TemporalQuery())
        assert set(result.node_ids) == {own.memory_id, related.memory_id}
        assert session.neighbors(foreign.memory_id) == ()


def test_foreign_edge_proof_is_rejected_even_with_owned_endpoints_and_actor(path):
    _, first = add(path, "first-owner")
    _, second = add(path, "second-owner")
    foreign_source, _ = add(path, "foreign-proof", scope=OTHER)
    edge(path, "foreign-source-edge", first, second, foreign_source)
    with SQLiteRetrievalStore(path).read_snapshot(OWNER, principal_only=True) as session:
        assert session.neighbors(first.memory_id) == ()
        assert session.memory_state(first.memory_id, TemporalQuery()).effective_status is MemoryStatus.ACTIVE


@pytest.mark.parametrize("replacement_scope,actor,expected", [
    (OWNER, OWNER, True), (OTHER, OWNER, False), (OWNER, OTHER, False),
])
def test_supersession_governance_is_principal_filtered_before_state(path, replacement_scope, actor, expected):
    _, old = add(path, "old", text="My test computer has 4 GB RAM.",
        valid_from=NOW, valid_until=NOW + timedelta(days=30))
    _, new = add(path, "new", scope=replacement_scope, text="I upgraded my test computer to 12 GB RAM.",
        valid_from=NOW + timedelta(days=1), valid_until=NOW + timedelta(days=30), when=NOW + timedelta(days=1))
    graph = GraphService(path)
    proposal = graph.propose_conflict(actor, new.memory_id, old.memory_id).proposal
    assert proposal is not None
    committed = graph.resolve(actor, proposal, confirm=True)
    query = TemporalQuery(valid_at=NOW + timedelta(days=2))
    with SQLiteRetrievalStore(path).read_snapshot(OWNER) as legacy:
        assert legacy.memory_state(old.memory_id, query).effective_status is MemoryStatus.SUPERSEDED
    with SQLiteRetrievalStore(path).read_snapshot(OWNER, principal_only=True) as session:
        state = session.memory_state(old.memory_id, query)
        assert state.superseded_by == ((new.memory_id,) if expected else ())
        assert state.effective_status is (MemoryStatus.SUPERSEDED if expected else MemoryStatus.ACTIVE)
        earlier = session.memory_state(old.memory_id, TemporalQuery(valid_at=query.valid_at,
            known_at=committed.recorded_at - timedelta(microseconds=1)))
        assert earlier.superseded_by == ()


def test_retraction_is_not_revived_by_owned_lexical_or_vector_indexes(path):
    event, memory = add(path, "owner")
    vector(path, memory)
    SQLiteMindProjectionStore(path).retract_source(OWNER, memory.memory_id, event.event_id)
    with SQLiteRetrievalStore(path).read_snapshot(OWNER, principal_only=True) as session:
        assert session.lexical("notebook") == ()
        assert session.semantic((1.0, 0.0), SPACE) == ()
        assert session.memory_state(memory.memory_id, TemporalQuery()).effective_status is MemoryStatus.RETRACTED


def test_shared_snapshot_stays_read_only_and_does_not_mix_later_commits(path):
    _, first = add(path, "first")
    store = SQLiteRetrievalStore(path)
    with store.read_snapshot(OWNER, principal_only=True) as session:
        assert [hit.memory_id for hit in session.lexical("notebook")] == [first.memory_id]
        _, second = add(path, "second")
        assert session.memory(second.memory_id) is None
        assert session.index_status().canonical_count == 1
        assert session._connection.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError):
            session._connection.execute("CREATE TABLE unauthorized_write (value TEXT)")
        assert session._connection.total_changes == 0
    with store.read_snapshot(OWNER, principal_only=True) as fresh:
        assert fresh.memory(second.memory_id) is not None
        assert fresh.index_status().canonical_count == 2
