"""Synthetic Stage 4 graph, temporal, conflict, and topic demonstration.

Use --db only with a dedicated synthetic database. No model or network is used.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from oomp.domain.enums import EventType, MemoryType, RelationshipType, SourceType
from oomp.domain.graph import TemporalQuery
from oomp.domain.models import AuthorizedScope, MemoryEvent, MemoryNode, SourceReference
from oomp.graph import GraphService
from oomp.ingestion import ExtractionPipeline
from oomp.storage import SQLiteEventStore
from oomp.storage.graph_store import SQLiteGraphStore
from oomp.storage.memory_store import SQLiteMemoryStore
from oomp.storage.topic_store import SQLiteTopicStore

SCOPE = AuthorizedScope(
    tenant_id="tenant-stage4-example", namespace="synthetic",
    principal_id="example-service",
)
SEP1 = datetime(2026, 9, 1, tzinfo=timezone.utc)
SEP5 = datetime(2026, 9, 5, tzinfo=timezone.utc)
SEP10 = datetime(2026, 9, 10, tzinfo=timezone.utc)
SEP12 = datetime(2026, 9, 12, tzinfo=timezone.utc)
SEP15 = datetime(2026, 9, 15, tzinfo=timezone.utc)
SEP20 = datetime(2026, 9, 20, tzinfo=timezone.utc)
OCT10 = datetime(2026, 10, 10, tzinfo=timezone.utc)
OCT20 = datetime(2026, 10, 20, tzinfo=timezone.utc)


def event(event_id: str, content: str, when: datetime) -> MemoryEvent:
    return MemoryEvent(
        event_id=event_id, tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
        event_type=EventType.USER_MESSAGE, source_type=SourceType.USER,
        content=content,
        source_reference=SourceReference(
            source_system="synthetic-example", external_event_id=event_id,
            timestamp=when, session_id="stage4-demo", turn_id=event_id,
        ),
        occurred_at=when, ingested_at=when, idempotency_key="key-" + event_id,
        metadata={"synthetic": True},
    )


OLD_EVENT = event("hardware-old", "My test computer has 4 GB RAM.", SEP10)
NEW_EVENT = event("hardware-upgrade", "I upgraded my test computer to 12 GB RAM.", OCT10)
DISPUTED_EVENT = event("hardware-disputed", "My test computer has 8 GB RAM.", SEP12)
TOPIC_EVENT = event("project-oomp", "I am developing a project called OOMP.", OCT10)


def hardware_memory(
    memory_id: str, source: MemoryEvent, valid_from: datetime, valid_until: datetime,
) -> MemoryNode:
    created = datetime.now(timezone.utc)
    return MemoryNode(
        memory_id=memory_id, tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
        memory_type=MemoryType.SEMANTIC, canonical_key="stage4:" + memory_id,
        canonical_content=source.content,
        source_event_ids=(source.event_id,), provenance=(source.source_reference,),
        created_at=created, updated_at=created,
        valid_from=valid_from, valid_until=valid_until,
        metadata={"attribution": "user", "verified": False, "synthetic": True},
    )


def run(path: Path) -> None:
    events = SQLiteEventStore(path)
    assert events.initialize() == 4
    for source in (OLD_EVENT, NEW_EVENT, DISPUTED_EVENT, TOPIC_EVENT):
        assert events.append(SCOPE, source) == source

    memories = SQLiteMemoryStore(path)
    old = memories.upsert(SCOPE, hardware_memory("ram-old-4", OLD_EVENT, SEP1, SEP20))
    new = memories.upsert(SCOPE, hardware_memory("ram-new-12", NEW_EVENT, SEP20, OCT20))
    disputed = memories.upsert(
        SCOPE, hardware_memory("ram-disputed-8", DISPUTED_EVENT, SEP5, SEP15),
    )
    project_result = ExtractionPipeline(path).process_event(SCOPE, TOPIC_EVENT.event_id)
    assert len(project_result.memory_ids) == 1
    shared_memory_id = project_result.memory_ids[0]

    topics = SQLiteTopicStore(path)
    topics.create_topic(SCOPE, "ai", "Artificial Intelligence")
    topics.create_topic(SCOPE, "local-models", "Local Models", parent_id="ai")
    topics.create_topic(SCOPE, "robotics", "Robotics", parent_id="ai")
    topics.assign_memory(SCOPE, "local-models", shared_memory_id)
    topics.assign_memory(SCOPE, "robotics", shared_memory_id)

    service = GraphService(path)
    proposal = service.propose_conflict(SCOPE, new.memory_id, old.memory_id).proposal
    assert proposal is not None
    assert proposal.relationship_type is RelationshipType.SUPERSEDES
    graph = SQLiteGraphStore(path)
    before_edges = graph.list_edges(
        SCOPE, relationship_type=RelationshipType.SUPERSEDES,
    ).edges
    before_resolution = datetime.now(timezone.utc) if not before_edges else None
    edge = service.resolve(SCOPE, proposal, confirm=True)
    assert service.resolve(SCOPE, proposal, confirm=True).edge.edge_id == edge.edge.edge_id

    contradictions_before = graph.list_edges(
        SCOPE, relationship_type=RelationshipType.CONTRADICTS,
    ).edges
    unresolved = service.propose_conflict(SCOPE, disputed.memory_id, old.memory_id)
    assert unresolved.proposal is not None
    assert unresolved.proposal.relationship_type is RelationshipType.CONTRADICTS
    assert graph.list_edges(
        SCOPE, relationship_type=RelationshipType.CONTRADICTS,
    ).edges == contradictions_before

    reopened = GraphService(path)
    historical_old = reopened.history(SCOPE, old.memory_id, valid_at=SEP10, known_at=datetime.now(timezone.utc))
    current_new = reopened.history(SCOPE, new.memory_id, valid_at=SEP20, known_at=datetime.now(timezone.utc))
    assert historical_old.memory.valid is True
    assert current_new.memory.valid is True
    if before_resolution is not None:
        prior_view = reopened.history(SCOPE, old.memory_id, known_at=before_resolution)
        assert prior_view.memory.superseded_by == ()
    assert any(
        record.edge.edge_id == edge.edge.edge_id
        for record in reopened.history(SCOPE, old.memory_id).incoming_edges
    )
    tree = reopened.topic_tree(SCOPE, "ai")
    memberships = SQLiteTopicStore(path).memberships_for_memory(SCOPE, shared_memory_id)
    assert {member.topic_id for member in memberships} == {"local-models", "robotics"}
    assert memories.count_memories(SCOPE) == 4

    print(f"Scope: tenant={SCOPE.tenant_id} namespace={SCOPE.namespace}")
    print(f"Database: {path}")
    print(f"Source events: {events.count_events(SCOPE)}")
    print(f"Canonical memories: {memories.count_memories(SCOPE)}")
    print(
        f"Supersession edge: {edge.edge.edge_id} type={edge.edge.relationship_type.value} "
        f"evidence={len(edge.evidence)}"
    )
    print(
        f"Historical old state: memory={old.memory_id} known={historical_old.memory.known} "
        f"valid={historical_old.memory.valid}"
    )
    print(
        f"Current reported state: memory={new.memory_id} known={current_new.memory.known} "
        f"valid={current_new.memory.valid}"
    )
    print(f"Unresolved proposal: {unresolved.proposal.relationship_type.value}")
    print(f"Shared topic memory: {shared_memory_id} memberships={len(memberships)}")
    print(f"Topic tree nodes: {len(tree.nodes)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the synthetic Stage 4 temporal graph example.")
    parser.add_argument("--db", type=Path, help="dedicated persistent demonstration database path")
    args = parser.parse_args()
    if args.db is not None:
        run(args.db)
    else:
        with TemporaryDirectory(prefix="oomp-stage4-example-") as temporary_directory:
            run(Path(temporary_directory) / "events.sqlite3")


if __name__ == "__main__":
    main()
