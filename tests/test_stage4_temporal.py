"""Stage 4 service integration across scoped graph and temporal history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from oomp.domain.enums import EventType, MemoryStatus, MemoryType, RelationshipType, SourceType
from oomp.domain.graph import TemporalQuery
from oomp.domain.graph_policy import ConflictProposal
from oomp.domain.models import AuthorizedScope, MemoryEvent, MemoryNode, RequestedScope, SourceReference
from oomp.graph import GraphService
from oomp.storage import SQLiteEventStore
from oomp.storage.errors import GraphConflictError, MemoryNotFoundError
from oomp.storage.graph_store import SQLiteGraphStore
from oomp.storage.memory_store import SQLiteMemoryStore

SCOPE = AuthorizedScope(tenant_id="tenant-a", namespace="personal", principal_id="trusted-test")
SEP1 = datetime(2026, 9, 1, tzinfo=timezone.utc)
SEP10 = datetime(2026, 9, 10, tzinfo=timezone.utc)
SEP20 = datetime(2026, 9, 20, tzinfo=timezone.utc)
OCT10 = datetime(2026, 10, 10, tzinfo=timezone.utc)
OCT20 = datetime(2026, 10, 20, tzinfo=timezone.utc)


def event(event_id: str, text: str, when: datetime) -> MemoryEvent:
    return MemoryEvent(
        event_id=event_id, tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
        event_type=EventType.USER_MESSAGE, source_type=SourceType.USER,
        content=text, source_reference=SourceReference(
            source_system="synthetic-test", external_event_id=event_id, timestamp=when,
        ),
        occurred_at=when, ingested_at=when,
    )


def node(
    memory_id: str, source: MemoryEvent,
    valid_from: datetime, valid_until: datetime,
) -> MemoryNode:
    recorded = datetime.now(timezone.utc)
    return MemoryNode(
        memory_id=memory_id, tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
        memory_type=MemoryType.SEMANTIC, canonical_key="test:" + memory_id,
        canonical_content=source.content,
        source_event_ids=(source.event_id,), provenance=(source.source_reference,),
        created_at=recorded, updated_at=recorded,
        valid_from=valid_from, valid_until=valid_until,
        metadata={"attribution": "user", "verified": False},
    )


def setup_hardware(tmp_path: Path):
    database = tmp_path / "graph.sqlite3"
    assert SQLiteEventStore(database).initialize() == 5
    old_event = event("event-old", "My test computer has 4 GB RAM.", SEP10)
    new_event = event("event-new", "I upgraded my test computer to 12 GB RAM.", OCT10)
    source_store = SQLiteEventStore(database)
    source_store.append(SCOPE, old_event)
    source_store.append(SCOPE, new_event)
    memories = SQLiteMemoryStore(database)
    old = memories.upsert(SCOPE, node("memory-old", old_event, SEP1, SEP20))
    new = memories.upsert(SCOPE, node("memory-new", new_event, SEP20, OCT20))
    return database, old, new, old_event, new_event


def test_proposal_is_read_only_and_confirmed_resolution_is_durable(tmp_path: Path) -> None:
    database, old, new, old_event, new_event = setup_hardware(tmp_path)
    service = GraphService(database)
    assessment = service.propose_conflict(SCOPE, new.memory_id, old.memory_id)
    proposal = assessment.proposal
    assert proposal is not None
    assert proposal.relationship_type is RelationshipType.SUPERSEDES
    graph = SQLiteGraphStore(database)
    assert graph.list_edges(SCOPE).edges == ()
    with pytest.raises((GraphConflictError, ValueError)):
        service.resolve(SCOPE, proposal, confirm=False)
    assert graph.list_edges(SCOPE).edges == ()

    before_resolution = datetime.now(timezone.utc)
    committed = service.resolve(SCOPE, proposal, confirm=True)
    repeated = GraphService(database).resolve(SCOPE, proposal, confirm=True)
    assert repeated.edge.edge_id == committed.edge.edge_id
    assert repeated.edge.source_event_ids == (new_event.event_id,)
    assert committed.policy_version == "hardware-ram-v1"
    assert committed.recorded_by == SCOPE.principal_id
    assert SQLiteEventStore(database).get(SCOPE, old_event.event_id) == old_event

    earlier = GraphService(database).history(
        SCOPE, old.memory_id, valid_at=SEP10, known_at=before_resolution,
    )
    assert earlier.memory.valid is True
    assert earlier.incoming_edges == ()
    later = GraphService(database).history(
        SCOPE, old.memory_id, valid_at=SEP10, known_at=datetime.now(timezone.utc),
    )
    assert len(later.incoming_edges) == 1
    assert later.incoming_edges[0].edge.relationship_type is RelationshipType.SUPERSEDES
    assert later.memory.effective_status is MemoryStatus.ACTIVE
    assert later.memory.superseded_by == ()
    changed = GraphService(database).history(
        SCOPE, old.memory_id, valid_at=SEP20, known_at=datetime.now(timezone.utc),
    )
    assert changed.memory.effective_status is MemoryStatus.SUPERSEDED
    assert changed.memory.superseded_by == (new.memory_id,)
    before_commit = GraphService(database).history(
        SCOPE, old.memory_id, valid_at=SEP20, known_at=before_resolution,
    )
    assert before_commit.memory.effective_status is MemoryStatus.ACTIVE
    assert before_commit.memory.superseded_by == ()
    assert SQLiteMemoryStore(database).get(SCOPE, old.memory_id) == old


def test_tampered_resolution_and_foreign_scope_fail_closed(tmp_path: Path) -> None:
    database, old, new, old_event, new_event = setup_hardware(tmp_path)
    service = GraphService(database)
    proposal = service.propose_conflict(SCOPE, new.memory_id, old.memory_id).proposal
    assert proposal is not None
    tampered = ConflictProposal.model_validate({
        **proposal.model_dump(mode="json"), "reason": "fabricated policy reason",
    })
    with pytest.raises(GraphConflictError):
        service.resolve(SCOPE, tampered, confirm=True)
    assert SQLiteGraphStore(database).list_edges(SCOPE).edges == ()
    foreign = AuthorizedScope(tenant_id="tenant-b", namespace="personal", principal_id="trusted-test")
    with pytest.raises(MemoryNotFoundError):
        service.propose_conflict(foreign, new.memory_id, old.memory_id)

    committed = service.resolve(SCOPE, proposal, confirm=True)
    with pytest.raises(ValueError):
        ConflictProposal.model_validate({
            **proposal.model_dump(mode="json"),
            "target_node_id": proposal.source_node_id,
        })
    reverse = ConflictProposal.model_validate({
        **proposal.model_dump(mode="json"),
        "source_node_id": old.memory_id,
        "target_node_id": new.memory_id,
        "source_event_ids": (old_event.event_id,),
    })
    with pytest.raises(GraphConflictError):
        service.resolve(SCOPE, reverse, confirm=True)
    graph = SQLiteGraphStore(database)
    assert graph.list_edges(SCOPE).edges == (committed,)
    assert graph.get_edge(SCOPE, committed.edge.edge_id) == committed
    assert SQLiteEventStore(database).get(SCOPE, old_event.event_id) == old_event
    assert SQLiteEventStore(database).get(SCOPE, new_event.event_id) == new_event

    requested = RequestedScope(tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace)
    with pytest.raises(TypeError):
        graph.get_edge(requested, committed.edge.edge_id)
    with pytest.raises(TypeError):
        service.history(requested, old.memory_id)


def test_generic_link_and_bounded_neighbors_use_real_evidence(tmp_path: Path) -> None:
    database, old, new, _, new_event = setup_hardware(tmp_path)
    service = GraphService(database)
    linked = service.link(
        SCOPE, new.memory_id, old.memory_id,
        RelationshipType.RELATED_TO, (new_event.event_id,),
    )
    retry = service.link(
        SCOPE, new.memory_id, old.memory_id,
        RelationshipType.RELATED_TO, (new_event.event_id,),
    )
    assert linked.edge.edge_id == retry.edge.edge_id
    assert len(service.neighbors(SCOPE, old.memory_id, limit=1)) == 1
    assert SQLiteGraphStore(database).traverse(
        SCOPE, old.memory_id, max_depth=1, max_nodes=2,
    ).node_ids == (old.memory_id, new.memory_id)
    with pytest.raises(ValueError):
        service.link(
            SCOPE, new.memory_id, old.memory_id,
            RelationshipType.SUPERSEDES, (new_event.event_id,),
        )


def test_generic_edge_identity_normalizes_offset_and_rejects_string_evidence(tmp_path: Path) -> None:
    database, old, new, _, new_event = setup_hardware(tmp_path)
    service = GraphService(database)
    first = service.link(
        SCOPE, new.memory_id, old.memory_id, RelationshipType.RELATED_TO,
        (new_event.event_id,), valid_from=SEP20,
    )
    second = service.link(
        SCOPE, new.memory_id, old.memory_id, RelationshipType.RELATED_TO,
        (new_event.event_id,), valid_from=SEP20.astimezone(timezone(timedelta(hours=5))),
    )
    assert second.edge.edge_id == first.edge.edge_id
    with pytest.raises(TypeError):
        service.link(
            SCOPE, new.memory_id, old.memory_id,
            RelationshipType.RELATED_TO, new_event.event_id,
        )

def test_confirmed_contradiction_reopens_without_superseding_either_claim(tmp_path: Path) -> None:
    database, old, _, old_event, _ = setup_hardware(tmp_path)
    disputed_event = event("event-disputed", "My test computer has 8 GB RAM.", SEP10)
    SQLiteEventStore(database).append(SCOPE, disputed_event)
    disputed = SQLiteMemoryStore(database).upsert(
        SCOPE, node("memory-disputed", disputed_event, SEP1, SEP20),
    )
    service = GraphService(database)
    proposal = service.propose_conflict(SCOPE, disputed.memory_id, old.memory_id).proposal
    assert proposal is not None
    assert proposal.relationship_type is RelationshipType.CONTRADICTS
    assert proposal.source_event_ids == (disputed_event.event_id, old_event.event_id)
    assert SQLiteGraphStore(database).list_edges(SCOPE).edges == ()

    committed = service.resolve(SCOPE, proposal, confirm=True)
    reopened = GraphService(database)
    repeated = reopened.resolve(SCOPE, proposal, confirm=True)
    assert repeated.edge.edge_id == committed.edge.edge_id
    assert repeated.edge.source_event_ids == proposal.source_event_ids
    assert tuple(item.event_id for item in repeated.evidence) == proposal.source_event_ids
    assert len(SQLiteGraphStore(database).list_edges(SCOPE).edges) == 1
    for memory_id in (old.memory_id, disputed.memory_id):
        state = reopened.history(
            SCOPE, memory_id, valid_at=SEP10, known_at=datetime.now(timezone.utc),
        ).memory
        assert state.effective_status is MemoryStatus.ACTIVE
        assert state.superseded_by == ()


def test_confirmed_resolution_can_gain_rederived_independent_source_proof(tmp_path: Path) -> None:
    database, old, new, _, first_upgrade = setup_hardware(tmp_path)
    service = GraphService(database)
    first_proposal = service.propose_conflict(SCOPE, new.memory_id, old.memory_id).proposal
    assert first_proposal is not None
    first_edge = service.resolve(SCOPE, first_proposal, confirm=True)
    second_upgrade = event(
        "event-new-second-proof", first_upgrade.content,
        OCT10 + timedelta(days=1),
    )
    SQLiteEventStore(database).append(SCOPE, second_upgrade)
    extended = SQLiteMemoryStore(database).upsert(
        SCOPE, node(new.memory_id, second_upgrade, SEP20, OCT20),
    )
    assert extended.source_event_ids == (first_upgrade.event_id, second_upgrade.event_id)

    second_proposal = GraphService(database).propose_conflict(
        SCOPE, new.memory_id, old.memory_id,
        source_event_id=second_upgrade.event_id,
    ).proposal
    assert second_proposal is not None
    assert second_proposal.source_event_ids == (second_upgrade.event_id,)
    second_edge = GraphService(database).resolve(SCOPE, second_proposal, confirm=True)
    assert second_edge.edge.edge_id == first_edge.edge.edge_id
    assert second_edge.edge.source_event_ids == (
        first_upgrade.event_id, second_upgrade.event_id,
    )
    assert len(SQLiteGraphStore(database).list_edges(SCOPE).edges) == 1
    again = GraphService(database).resolve(SCOPE, second_proposal, confirm=True)
    assert again.edge.source_event_ids == second_edge.edge.source_event_ids


def test_known_at_excludes_later_memory_source_proof(tmp_path: Path) -> None:
    database, old, _, first_report, _ = setup_hardware(tmp_path)
    initial = GraphService(database).history(SCOPE, old.memory_id).memory
    assert initial.source_event_ids == (first_report.event_id,)
    cutoff = datetime.now(timezone.utc)
    second_report = event(
        "event-old-second-proof", first_report.content,
        SEP10 + timedelta(days=1),
    )
    SQLiteEventStore(database).append(SCOPE, second_report)
    SQLiteMemoryStore(database).upsert(
        SCOPE, node(old.memory_id, second_report, SEP1, SEP20),
    )

    prior = GraphService(database).history(SCOPE, old.memory_id, known_at=cutoff).memory
    current = GraphService(database).history(SCOPE, old.memory_id).memory
    assert prior.source_event_ids == (first_report.event_id,)
    assert tuple(item.event_id for item in prior.evidence) == prior.source_event_ids
    assert current.source_event_ids == (first_report.event_id, second_report.event_id)
    assert tuple(item.event_id for item in current.evidence) == current.source_event_ids