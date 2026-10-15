"""Stage 4 topic hierarchy and projection persistence tests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from oomp.domain.models import AuthorizedScope, MemoryEvent, MemoryNode, SourceReference
from oomp.storage import (
    GraphLimitError, MemoryNotFoundError, SQLiteEventStore, SQLiteMemoryStore,
    SQLiteTopicStore, TopicConflictError, TopicNotFoundError,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def scope(tenant="t", namespace="n"):
    return AuthorizedScope(tenant_id=tenant, namespace=namespace, principal_id="local")


@pytest.fixture
def topics(tmp_path):
    path = tmp_path / "topics.sqlite3"
    events, memories, store = SQLiteEventStore(path), SQLiteMemoryStore(path), SQLiteTopicStore(path)
    assert events.initialize() == 4
    ref = SourceReference(source_system="test", external_event_id="e1", timestamp=NOW)
    source = MemoryEvent(
        event_id="e1", tenant_id="t", namespace="n",
        event_type="user_message", source_type="user",
        content="Shared memory.", source_reference=ref,
        occurred_at=NOW, ingested_at=NOW,
    )
    events.append(scope(), source)
    memory = MemoryNode(
        memory_id="m1", tenant_id="t", namespace="n",
        memory_type="semantic", canonical_content="Shared memory.",
        canonical_key="shared", source_event_ids=("e1",), provenance=(ref,),
        created_at=NOW, updated_at=NOW,
        metadata={"attribution": "user", "verified": False},
    )
    memories.upsert(scope(), memory)
    return store, memory


def test_one_memory_in_two_branches_survives_restart(topics):
    store, memory = topics
    root = store.create_topic(scope(), "ai", "Artificial Intelligence")
    local = store.create_topic(scope(), "local", "Local Models", parent_id="ai")
    robotics = store.create_topic(scope(), "robotics", "Robotics", parent_id="ai")
    assert store.create_topic(scope(), "ai", "Artificial Intelligence") == root
    assert store.list_children(scope(), "ai") == (local, robotics)
    first = store.assign_memory(scope(), "local", memory.memory_id)
    second = store.assign_memory(scope(), "robotics", memory.memory_id)
    assert store.assign_memory(scope(), "local", memory.memory_id) == first
    reopened = SQLiteTopicStore(store.path)
    memberships = reopened.memberships_for_memory(scope(), memory.memory_id)
    assert {item.topic_id for item in memberships} == {"local", "robotics"}
    assert len({item.memory_id for item in memberships}) == 1
    tree = reopened.topic_tree(scope(), "ai")
    assert [item.topic.topic_id for item in tree.nodes] == ["ai", "local", "robotics"]
    assert tree.nodes[1].memory_ids == tree.nodes[2].memory_ids == ("m1",)
    assert not tree.truncated
    assert reopened.count_memories(scope()) == 1
    assert first.recorded_at <= second.recorded_at


def test_topic_identity_parent_cycles_scope_and_missing_endpoints(topics):
    store, memory = topics
    store.create_topic(scope(), "root", "Root")
    store.create_topic(scope(), "child", "Child", parent_id="root")
    with pytest.raises(TopicConflictError):
        store.create_topic(scope(), "self", "Self", parent_id="self")
    with pytest.raises(TopicConflictError):
        store.create_topic(scope(), "root", "Root", parent_id="child")
    with pytest.raises(TopicNotFoundError):
        store.create_topic(scope(), "orphan", "Orphan", parent_id="missing")
    with pytest.raises(TopicNotFoundError):
        store.assign_memory(scope("other"), "root", "m1")
    with pytest.raises(MemoryNotFoundError):
        store.assign_memory(scope(), "root", "absent")
    with pytest.raises(TopicNotFoundError):
        store.list_children(scope("other"), "root")
    assert store.get_topic(scope("other"), "root") is None
    assert store.get_topic(scope(), "orphan") is None
    assert store.memberships_for_memory(scope(), "m1") == ()


def test_bounded_topic_tree_and_concurrent_membership_retry(topics):
    store, memory = topics
    store.create_topic(scope(), "root", "Root")
    store.create_topic(scope(), "a", "A", parent_id="root")
    store.create_topic(scope(), "b", "B", parent_id="root")
    store.create_topic(scope(), "a1", "A1", parent_id="a")
    def assign(_):
        return SQLiteTopicStore(store.path).assign_memory(scope(), "a", memory.memory_id)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert len(set(pool.map(assign, range(4)))) == 1
    assert len(store.memberships_for_memory(scope(), "m1")) == 1
    shallow = store.topic_tree(scope(), "root", max_depth=0)
    assert [item.topic.topic_id for item in shallow.nodes] == ["root"]
    assert shallow.truncated
    narrow = store.topic_tree(scope(), "root", max_nodes=2)
    assert [item.topic.topic_id for item in narrow.nodes] == ["root", "a"]
    assert narrow.truncated
    budget = store.topic_tree(scope(), "a", max_memberships=0)
    assert budget.truncated and budget.nodes[0].memory_ids == ()
    with pytest.raises(GraphLimitError):
        store.list_children(scope(), "root", limit=1)
    with pytest.raises(ValueError):
        store.topic_tree(scope(), "root", max_nodes=True)