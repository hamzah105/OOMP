"""Stage 5 SQLite migration, FTS5, vector durability and scope tests."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone

import pytest

from oomp.domain.graph import TemporalQuery
from oomp.domain.memories import EntityMention, SourceSpan
from oomp.domain.models import AuthorizedScope, MemoryEdge, MemoryEvent, MemoryNode, SourceReference
from oomp.retrieval.contracts import EmbeddingSpace
from oomp.storage import (
    EmbeddingSpaceError, RetrievalLimitError, SQLiteEntityStore, SQLiteEventStore,
    SQLiteGraphStore, SQLiteMemoryStore, SQLiteRetrievalStore, SQLiteTopicStore,
    StorageUnavailableError, UnsupportedSchemaVersionError,
)
from oomp.storage.migrations import MIGRATION_1, MIGRATION_2, MIGRATION_3, MIGRATION_4, verify_v3, verify_v4
from oomp.storage.retrieval_store import content_digest

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def scope(tenant="tenant", namespace="personal"):
    return AuthorizedScope(tenant_id=tenant, namespace=namespace, principal_id="test")


def add_memory(path, name, content, authorized=None):
    authorized = authorized or scope()
    source = MemoryEvent(
        event_id=f"event-{name}", tenant_id=authorized.tenant_id,
        namespace=authorized.namespace, event_type="user_message",
        source_type="user", content=content,
        source_reference=SourceReference(
            source_system="synthetic", external_event_id=f"event-{name}", timestamp=NOW,
        ), occurred_at=NOW, ingested_at=NOW,
    )
    saved = SQLiteEventStore(path).append(authorized, source)
    node = MemoryNode(
        memory_id=f"mem-{name}", tenant_id=authorized.tenant_id,
        namespace=authorized.namespace, memory_type="semantic",
        canonical_key=f"key-{name}", canonical_content=content,
        source_event_ids=(saved.event_id,), provenance=(saved.source_reference,),
        created_at=NOW, updated_at=NOW,
        metadata={"attribution": "user", "verified": False},
    )
    return SQLiteMemoryStore(path).upsert(authorized, node)


def genuine_v3(path):
    with closing(sqlite3.connect(path)) as c, c:
        c.execute("PRAGMA foreign_keys=ON")
        c.create_function("oomp_recorded_at", 0, lambda: "2026-01-01T00:00:00.000000Z")
        for statement in (*MIGRATION_1, *MIGRATION_2, *MIGRATION_3):
            c.execute(statement)
        c.execute("PRAGMA user_version=3")
        assert verify_v3(c)


def test_genuine_v3_graph_alias_topic_and_history_survive_v4(tmp_path):
    path = tmp_path / "upgrade.sqlite3"
    genuine_v3(path)
    first = add_memory(path, "oomp", "OOMP (Object-Oriented Context Map).")
    second = add_memory(path, "python", "Python is used by OOMP.")
    alias_event = SQLiteEventStore(path).get(scope(), "event-oomp")
    assert alias_event is not None
    project = SQLiteEntityStore(path).resolve(scope(), EntityMention(
        name="OOMP", entity_type="project", aliases=("Object-Oriented Context Map",),
        source_event_id=alias_event.event_id,
        source_span=SourceSpan(start=0,end=len(alias_event.content),quote=alias_event.content),
    ))
    with closing(sqlite3.connect(path)) as c,c:
        c.execute("PRAGMA foreign_keys=ON")
        c.execute(
            "INSERT INTO memory_entities VALUES (?,?,?,?)",
            ("tenant","personal",first.memory_id,project.entity_id),
        )
    link = SQLiteGraphStore(path).add_edge(scope(), MemoryEdge(
        edge_id="edge-1",tenant_id="tenant",namespace="personal",
        source_node_id=first.memory_id,target_node_id=second.memory_id,
        relationship_type="RELATED_TO",source_event_ids=("event-oomp",),
        created_at=NOW,
    ))
    topic_store = SQLiteTopicStore(path)
    topic_store.create_topic(scope(),"topic-1","OOMP")
    membership = topic_store.assign_memory(scope(),"topic-1",first.memory_id)
    with closing(sqlite3.connect(path)) as c:
        old = {name: c.execute(f"SELECT * FROM {name} ORDER BY 1").fetchall() for name in (
            "events","memories","memory_sources","entities","entity_aliases",
            "memory_entities","memory_edges","edge_evidence","topics","topic_memberships",
            "graph_meta","memory_recordings","memory_source_recordings",
        )}
    store = SQLiteRetrievalStore(path)
    assert store.status().schema_version == 3 and not store.status().ready
    assert store.initialize() == 4
    assert store.initialize() == 4
    assert store.status().ready
    with closing(sqlite3.connect(path)) as c:
        assert verify_v4(c)
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []
        for name, rows in old.items():
            assert c.execute(f"SELECT * FROM {name} ORDER BY 1").fetchall() == rows
    with store.read_snapshot(scope()) as snapshot:
        assert snapshot.lexical("OOMP",limit=10)
        assert snapshot.topic_candidates(["OOMP"])[0].memory_id == first.memory_id
        assert snapshot.memory_state(first.memory_id,TemporalQuery()).source_event_ids == ("event-oomp",)
        assert snapshot.neighbors(first.memory_id)[0].edge.edge_id == link.edge.edge_id
    assert SQLiteTopicStore(path).assign_memory(scope(),"topic-1",first.memory_id) == membership
    assert SQLiteEntityStore(path).count_entities(scope()) == 1
    assert SQLiteMemoryStore(path).list_entities(scope(),first.memory_id)[0].entity_id == project.entity_id


def test_failed_v4_migration_rolls_back_genuine_v3(tmp_path, monkeypatch):
    path = tmp_path / "rollback.sqlite3"
    genuine_v3(path)
    first = add_memory(path,"older","Older source evidence.")
    import oomp.storage.migrations as migrations
    monkeypatch.setitem(migrations.MIGRATIONS,4,MIGRATION_4+("CREATE TABLE memories (bad TEXT)",))
    with pytest.raises(StorageUnavailableError):
        SQLiteEventStore(path).initialize()
    with closing(sqlite3.connect(path)) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 3
        assert verify_v3(c)
        assert c.execute("SELECT name FROM sqlite_master WHERE name='memory_fts'").fetchone() is None
    assert SQLiteMemoryStore(path).get(scope(),first.memory_id) == first


def test_future_version_rejected_and_fresh_v4_idempotent(tmp_path):
    path=tmp_path/"fresh.sqlite3"
    store=SQLiteEventStore(path)
    assert store.initialize()==4
    assert store.initialize()==4
    with closing(sqlite3.connect(path)) as c,c:
        assert verify_v4(c)
        c.execute("PRAGMA user_version=5")
    with pytest.raises(UnsupportedSchemaVersionError):
        store.initialize()


def test_fts_backfill_new_insert_rebuild_and_scoped_ranking(tmp_path):
    path=tmp_path/"fts.sqlite3"
    genuine_v3(path)
    first=add_memory(path,"first","The user develops OOMP.")
    store=SQLiteRetrievalStore(path)
    store.initialize()
    with store.read_snapshot(scope()) as read:
        assert read.lexical("OOMP")[0].memory_id==first.memory_id
        initial=read.lexical("OOMP")[0].score
    second=add_memory(path,"second","OOMP uses Python.")
    with store.read_snapshot(scope()) as read:
        expected=read.lexical("OOMP")
        assert {h.memory_id for h in expected}=={first.memory_id,second.memory_id}
    for i in range(6):
        add_memory(path,f"foreign-{i}","OOMP "*20,scope("other"))
        add_memory(path,f"namespace-{i}","OOMP "*20,scope("tenant","other"))
    with store.read_snapshot(scope()) as read:
        assert read.lexical("OOMP")==expected
        for arbitrary in ('"OOMP") OR *', 'NEAR OR "OOMP" MATCH (', '"; DROP TABLE memories; -- OOMP'):
            assert {hit.memory_id for hit in read.lexical(arbitrary)}=={first.memory_id,second.memory_id}
        assert read.lexical('""()')==()
        assert read.lexical('NEAR OR *')==()
    unicode_scope=scope("tenant","unicode")
    for identity in ("unicode-a","unicode-b"):
        add_memory(path,identity,"Caf\u00e9 \u6771\u4eac \u0627\u0631\u062f\u0648.",unicode_scope)
    with store.read_snapshot(unicode_scope) as read:
        for term in ("Caf\u00e9","\u6771\u4eac","\u0627\u0631\u062f\u0648"):
            hits=read.lexical(term)
            assert tuple(hit.memory_id for hit in hits)==("mem-unicode-a","mem-unicode-b")
            assert hits[0].score==hits[1].score
    assert store.index_lexical(scope(),batch_size=1)==(0,2)
    assert store.rebuild_lexical(scope(),batch_size=1)==2
    assert SQLiteMemoryStore(path).get(scope(),first.memory_id)==first
    assert initial < 0


def test_vector_space_complete_scan_reopen_and_invalid_batches(tmp_path):
    path=tmp_path/"vectors.sqlite3"
    store=SQLiteRetrievalStore(path)
    store.initialize()
    one=add_memory(path,"one","A project called OOMP.")
    two=add_memory(path,"two","Python is the tool.")
    space=EmbeddingSpace(provider="test",model="tiny",version="v1",dimension=2)
    with pytest.raises(EmbeddingSpaceError):
        with store.read_snapshot(scope()) as read:
            read.semantic([1.0,0.0],space)
    page=store.embedding_index_plan(scope(),space,batch_size=1)
    assert len(page.memories)==1 and page.next_cursor is not None
    assert len(store.pending_embeddings(scope(),space,(one,two)))==2
    with pytest.raises(EmbeddingSpaceError):
        store.put_embedding_batch(scope(),space,(
            (one.memory_id,content_digest(one.canonical_content),[1.0,0.0]),
            (two.memory_id,content_digest(two.canonical_content),[0.0,float("nan")]),
        ))
    assert store.index_status(scope(),space).compatible_embeddings==0
    assert store.put_embedding_batch(scope(),space,(
        (one.memory_id,content_digest(one.canonical_content),[1.0,0.0]),
        (two.memory_id,content_digest(two.canonical_content),[0.0,1.0]),
    ))==(2,0)
    assert store.pending_embeddings(scope(),space,(one,two))==()
    assert store.put_embedding_batch(scope(),space,(
        (one.memory_id,content_digest(one.canonical_content),[1.0,0.0]),
    ))==(0,1)
    reopened=SQLiteRetrievalStore(path)
    with reopened.read_snapshot(scope()) as read:
        assert tuple(hit.memory_id for hit in read.semantic([1.0,0.0],space))==(one.memory_id,two.memory_id)
        assert read.semantic([1e308,1e308],space)[0].score > 0
    different_namespace=scope("tenant","other")
    foreign=add_memory(path,"other-ns","Unrelated vector.",different_namespace)
    assert reopened.put_embedding_batch(different_namespace,space,(
        (foreign.memory_id,content_digest(foreign.canonical_content),[1.0,0.0]),
    ))==(1,0)
    with reopened.read_snapshot(scope()) as read:
        assert all(hit.memory_id != foreign.memory_id for hit in read.semantic([1.0,0.0],space))
    other=EmbeddingSpace(provider="test",model="different",version="v1",dimension=2)
    with pytest.raises(EmbeddingSpaceError):
        with reopened.read_snapshot(scope()) as read:
            read.semantic([1.0,0.0],other)


def test_vector_strict_numeric_digest_and_limits(tmp_path):
    path=tmp_path/"limits.sqlite3"
    store=SQLiteRetrievalStore(path,max_lexical_docs=1,max_lexical_bytes=32,max_vector_scan=1)
    store.initialize()
    one=add_memory(path,"one","This is a memory.")
    space=EmbeddingSpace(provider="test",model="tiny",version="v1",dimension=2)
    digest=content_digest(one.canonical_content)
    for bad in ([True,1.0],["1",1.0],[0.0,0.0],[1.0,float("inf")]):
        with pytest.raises(EmbeddingSpaceError):
            store.put_embedding_batch(scope(),space,((one.memory_id,digest,bad),))
    with pytest.raises(EmbeddingSpaceError):
        store.put_embedding_batch(scope(),space,((one.memory_id,"0"*64,[1.0,0.0]),))
    assert store.put_embedding_batch(scope(),space,((one.memory_id,digest,[1.0,0.0]),))==(1,0)
    add_memory(path,"two","Another memory.")
    with store.read_snapshot(scope()) as read:
        with pytest.raises(RetrievalLimitError):
            read.lexical("memory")
        with pytest.raises(RetrievalLimitError):
            read.semantic([1.0,0.0],space)


def test_historical_snapshot_excludes_future_memory_and_entity_lane(tmp_path):
    path=tmp_path/"history.sqlite3"
    store=SQLiteRetrievalStore(path)
    store.initialize()
    memory=add_memory(path,"future","OOMP exists.")
    with closing(sqlite3.connect(path)) as c:
        recorded=c.execute("SELECT recorded_at FROM memory_recordings WHERE memory_id=?",(memory.memory_id,)).fetchone()[0]
    before=datetime.fromisoformat(recorded.replace("Z","+00:00")).replace(year=2025)
    with store.read_snapshot(scope()) as read:
        assert read.lexical("OOMP",known_at=before)==()
        assert read.entity_candidates(["OOMP"],known_at=before)==()
        assert read.memory_state(memory.memory_id,TemporalQuery(known_at=before)).known is False
        first_ids=tuple(hit.memory_id for hit in read.lexical("OOMP"))
        later=add_memory(path,"later","Another OOMP fact.")
        assert tuple(hit.memory_id for hit in read.lexical("OOMP"))==first_ids
        assert read.memory(later.memory_id) is None
    with store.read_snapshot(scope()) as read:
        assert later.memory_id in {hit.memory_id for hit in read.lexical("OOMP")}


def test_stale_vectors_and_lexical_byte_ceiling(tmp_path):
    path=tmp_path/"stale.sqlite3"
    store=SQLiteRetrievalStore(path,max_lexical_bytes=24)
    store.initialize()
    memory=add_memory(path,"one","Small OOMP memory.")
    space=EmbeddingSpace(provider="test",model="tiny",version="v1",dimension=2)
    store.put_embedding_batch(scope(),space,(
        (memory.memory_id,content_digest(memory.canonical_content),[1.0,0.0]),
    ))
    with closing(sqlite3.connect(path)) as c,c:
        c.execute("UPDATE memory_embeddings SET content_digest=? WHERE memory_id=?",("0"*64,memory.memory_id))
    assert store.index_status(scope(),space).stale_embeddings==1
    with pytest.raises(EmbeddingSpaceError):
        with store.read_snapshot(scope()) as read:
            read.semantic([1.0,0.0],space)
    add_memory(path,"two","Another very long OOMP memory statement.")
    with pytest.raises(RetrievalLimitError):
        with store.read_snapshot(scope()) as read:
            read.lexical("OOMP")
