"""Real Stage 6 engine integration over file-backed synthetic SQLite."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from oomp.domain.enums import EventType, MemoryType, SourceType
from oomp.domain.models import AuthorizedScope, MemoryEvent, MemoryNode, SourceReference
from oomp.mind.contracts import JobType, ReviewStatus
from oomp.mind.governance import ConflictReviewer
from oomp.mind.scheduler import MindScheduler
from oomp.mind.worker import MindWorker
from oomp.retrieval.contracts import RetrievalRequest
from oomp.retrieval.engine import RetrievalEngine
from oomp.storage.graph_store import SQLiteGraphStore
from oomp.storage.memory_store import SQLiteMemoryStore
from oomp.storage.mind_projection_store import SQLiteMindProjectionStore
from oomp.storage.mind_store import SQLiteMindStore
from oomp.storage.sqlite import SQLiteEventStore
from oomp.storage.topic_store import SQLiteTopicStore

SCOPE = AuthorizedScope(tenant_id="tenant-a", namespace="personal", principal_id="operator")
T = datetime(2026, 10, 1, tzinfo=timezone.utc)


def source(event_id: str, content: str, when: datetime = T) -> MemoryEvent:
    return MemoryEvent(
        tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
        event_id=event_id, event_type=EventType.USER_MESSAGE,
        source_type=SourceType.USER, content=content,
        source_reference=SourceReference(
            source_system="synthetic-test", external_event_id=event_id,
            timestamp=when,
        ),
        occurred_at=when, ingested_at=when,
    )


def db(tmp_path: Path) -> Path:
    path = tmp_path / "mind.sqlite3"
    assert SQLiteEventStore(path).initialize() == 5
    return path


def memory_node(event: MemoryEvent, memory_id: str, valid_from: datetime, valid_until: datetime) -> MemoryNode:
    return MemoryNode(
        tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
        memory_id=memory_id, memory_type=MemoryType.SEMANTIC,
        canonical_key="ram:" + memory_id, canonical_content=event.content,
        source_event_ids=(event.event_id,), provenance=(event.source_reference,),
        created_at=event.ingested_at, updated_at=event.ingested_at,
        valid_from=valid_from, valid_until=valid_until,
        metadata={"attribution": "user", "verified": False},
    )


def test_event_outbox_worker_reopen_and_retrieval(tmp_path: Path) -> None:
    path = db(tmp_path)
    events = SQLiteEventStore(path)
    events.append(SCOPE, source("event-1", "I prefer Python."))
    queue = SQLiteMindStore(path)
    assert queue.status(SCOPE)["outbox_pending"] == 1
    first = MindWorker(path, SCOPE, worker_id="worker-a").run_once(max_jobs=8)
    assert (first.claimed, first.completed, first.dispatched) == (3, 3, 1)
    memory = SQLiteMemoryStore(path).list_memories(SCOPE).memories[0]
    assert memory.source_event_ids == ("event-1",)
    reopened = MindWorker(path, SCOPE, worker_id="worker-b")
    again = reopened.run_once(max_jobs=8)
    assert again.claimed == 0
    assert SQLiteMemoryStore(path).count_memories(SCOPE) == 1
    result = RetrievalEngine(path).retrieve(
        SCOPE, RetrievalRequest(
            tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
            query="Python", token_budget=1200,
        ),
    )
    assert any(item.memory_id == memory.memory_id for item in result.memories)


def test_versioned_summary_shared_proof_and_historical_retraction(tmp_path: Path) -> None:
    path = db(tmp_path)
    events = SQLiteEventStore(path)
    events.append(SCOPE, source("event-1", "I prefer Python."))
    events.append(SCOPE, source("event-2", "I prefer Python.", T + timedelta(days=1)))
    worker = MindWorker(path, SCOPE)
    assert worker.run_once(max_jobs=10).completed >= 4
    memory = SQLiteMemoryStore(path).list_memories(SCOPE).memories[0]
    assert set(memory.source_event_ids) == {"event-1", "event-2"}
    SQLiteTopicStore(path).create_topic(SCOPE, "topic-1", "Programming")
    SQLiteTopicStore(path).assign_memory(SCOPE, "topic-1", memory.memory_id)
    projections = SQLiteMindProjectionStore(path)
    first, created = projections.consolidate_topic(SCOPE, "topic-1")
    assert created and first is not None and len(first.sources) == 2
    assert all(source.verified is False for source in first.sources)
    again, created = projections.consolidate_topic(SCOPE, "topic-1")
    assert not created and again.revision_id == first.revision_id
    cutoff = datetime.now(timezone.utc)
    assert projections.retract_source(SCOPE, memory.memory_id, "event-1")
    current, created = projections.consolidate_topic(SCOPE, "topic-1")
    assert created and current is not None and current.revision_number == 2
    assert current.source_event_ids == ("event-2",)
    assert projections.get_summary(SCOPE, "topic-1", known_at=cutoff).revision_id == first.revision_id
    assert projections.get_summary(SCOPE, "topic-1").revision_id == current.revision_id
    response = RetrievalEngine(path).retrieve(
        SCOPE, RetrievalRequest(
            tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
            query="Python", token_budget=1200,
        ),
    )
    assert len(response.memories) == 1
    assert response.memories[0].source_event_ids == ("event-2",)


def test_conflict_review_is_nonmutating_until_atomic_approval(tmp_path: Path) -> None:
    path = db(tmp_path)
    old_event = source("event-old", "My test computer has 4 GB RAM.", T)
    new_at = T + timedelta(days=10)
    new_event = source("event-new", "I upgraded my test computer to 12 GB RAM.", new_at)
    events = SQLiteEventStore(path)
    memories = SQLiteMemoryStore(path)
    for event in (old_event, new_event):
        events.append(SCOPE, event)
    old = memory_node(old_event, "memory-old", T, T + timedelta(days=10))
    new = memory_node(new_event, "memory-new", new_at, new_at + timedelta(days=10))
    memories.put(SCOPE, old)
    memories.put(SCOPE, new)
    reviewer = ConflictReviewer(path)
    assert reviewer.inspect_event(SCOPE, new_event.event_id) == 1
    assert SQLiteGraphStore(path).list_edges(SCOPE).edges == ()
    review = SQLiteMindProjectionStore(path).list_reviews(SCOPE)[0]
    assert review.status is ReviewStatus.PENDING
    decided = reviewer.approve(SCOPE, review.proposal_id)
    assert decided.status is ReviewStatus.APPROVED
    assert len(SQLiteGraphStore(path).list_edges(SCOPE).edges) == 1
    assert reviewer.approve(SCOPE, review.proposal_id).status is ReviewStatus.APPROVED
    # Retraction of the upgrade's selected proof removes its current
    # supersession effect, without deleting the auditable historical edge.
    assert SQLiteMindProjectionStore(path).retract_source(
        SCOPE, new.memory_id, new_event.event_id,
    )
    from oomp.domain.graph import TemporalQuery
    state = SQLiteGraphStore(path).memory_state(SCOPE, old.memory_id, TemporalQuery())
    assert state.effective_status.value == "active"
    assert len(SQLiteGraphStore(path).list_edges(SCOPE).edges) == 1


def test_pinned_embedding_jobs_require_opt_in_and_matching_provider(tmp_path: Path) -> None:
    path = db(tmp_path)
    SQLiteEventStore(path).append(SCOPE, source("event-1", "I prefer Python."))
    scheduler = MindScheduler(path)
    with pytest.raises(ValueError):
        scheduler.enqueue(
            SCOPE, JobType.MAINTAIN_INDEX, "event-1", generation="manual-1",
            config={"include_embeddings": True},
        )
    job = scheduler.enqueue(
        SCOPE, JobType.MAINTAIN_INDEX, "event-1", generation="manual-2",
        config={"include_embeddings": True, "space": {
            "provider": "synthetic", "model": "test", "version": "v1", "dimension": 2,
        }},
    )
    assert job.config["space"]["provider"] == "synthetic"
    result = MindWorker(path, SCOPE).run_once(max_jobs=1)
    assert result.failed == 1
    assert SQLiteMindStore(path).get_job(SCOPE, job.job_id).last_error_code == "validation_error"
