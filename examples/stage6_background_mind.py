"""Offline, repeatable Stage 6 demonstration using synthetic SQLite evidence.

Run:
    python examples/stage6_background_mind.py --db .test-artifacts/stage6-demo.sqlite3

The provider below is a deterministic TEST FIXTURE, not model inference.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from oomp.domain.enums import EventType, MemoryType, SourceType
from oomp.domain.models import AuthorizedScope, MemoryEvent, MemoryNode, SourceReference
from oomp.mind.contracts import JobType
from oomp.mind.governance import ConflictReviewer
from oomp.mind.handlers import MindHandlers
from oomp.mind.scheduler import MindScheduler
from oomp.mind.worker import MindWorker
from oomp.providers.errors import EmbeddingProviderUnavailable
from oomp.retrieval.contracts import EmbeddingSpace, RetrievalRequest
from oomp.retrieval.engine import RetrievalEngine
from oomp.storage.memory_store import SQLiteMemoryStore
from oomp.storage.mind_projection_store import SQLiteMindProjectionStore
from oomp.storage.mind_store import SQLiteMindStore
from oomp.storage.privacy_store import SQLitePrivacyStore
from oomp.storage.sqlite import SQLiteEventStore
from oomp.storage.topic_store import SQLiteTopicStore

SCOPE = AuthorizedScope(
    tenant_id="synthetic-demo", namespace="stage6", principal_id="local-operator",
)
START = datetime(2026, 9, 1, tzinfo=timezone.utc)


def event(event_id: str, content: str, when: datetime = START) -> MemoryEvent:
    return MemoryEvent(
        tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
        event_id=event_id, event_type=EventType.USER_MESSAGE,
        source_type=SourceType.USER, content=content,
        source_reference=SourceReference(
            source_system="synthetic-stage6",
            external_event_id=event_id, timestamp=when,
        ),
        occurred_at=when, ingested_at=when,
    )


def ram_memory(event_value: MemoryEvent, memory_id: str, start: datetime, end: datetime) -> MemoryNode:
    return MemoryNode(
        tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
        memory_id=memory_id, memory_type=MemoryType.SEMANTIC,
        canonical_key="synthetic-ram:" + memory_id,
        canonical_content=event_value.content,
        source_event_ids=(event_value.event_id,),
        provenance=(event_value.source_reference,),
        created_at=event_value.ingested_at, updated_at=event_value.ingested_at,
        valid_from=start, valid_until=end,
        metadata={"attribution": "user", "verified": False},
    )


class SyntheticEmbeddingFixture:
    """Mechanics only; vectors do not represent real semantic understanding."""

    space = EmbeddingSpace(
        provider="synthetic", model="fixed-two-axis", version="demo-v1", dimension=2,
    )

    def __init__(self) -> None:
        self.fail_next = True

    def embed(self, texts):
        if self.fail_next:
            self.fail_next = False
            raise EmbeddingProviderUnavailable("synthetic provider outage")
        return tuple(
            (1.0, 0.0) if "Python" in text else (0.0, 1.0)
            for text in texts
        )


def append_once(store: SQLiteEventStore, item: MemoryEvent) -> bool:
    if store.get(SCOPE, item.event_id) is not None:
        return False
    store.append(SCOPE, item)
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=".test-artifacts/stage6-background-mind.sqlite3")
    args = parser.parse_args()
    path = Path(args.db)
    if path.name == ":memory:":
        raise ValueError("the example requires a durable file-backed SQLite database")
    store = SQLiteEventStore(path)
    schema = store.initialize()
    basics = (
        event("demo-preference", "I prefer Python."),
        event("demo-project", "I am developing a project called OOMP."),
        event("demo-local-ai", "I prefer local AI."),
    )
    inserted = sum(append_once(store, item) for item in basics)
    queue = SQLiteMindStore(path)
    pending_before = queue.status(SCOPE)["outbox_pending"]
    worker = MindWorker(path, SCOPE, worker_id="demo-worker")
    first = worker.run_once(max_jobs=32)
    memory_store = SQLiteMemoryStore(path)
    count_after = memory_store.count_memories(SCOPE)
    second = MindWorker(path, SCOPE, worker_id="demo-worker-reopened").run_once(max_jobs=32)
    assert second.claimed == 0
    assert memory_store.count_memories(SCOPE) == count_after
    assert RetrievalEngine(path).retrieve(
        SCOPE, RetrievalRequest(
            tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
            query="Python", token_budget=1200,
        ),
    ).memories

    topics = SQLiteTopicStore(path)
    topics.create_topic(SCOPE, "topic-local-ai", "Local AI")
    local_memory = next(
        item for item in memory_store.list_memories(SCOPE).memories
        if "local AI" in item.canonical_content
    )
    topics.assign_memory(SCOPE, "topic-local-ai", local_memory.memory_id)
    projections = SQLiteMindProjectionStore(path)
    summary1, summary_created = projections.consolidate_topic(SCOPE, "topic-local-ai")
    summary2, repeat_created = projections.consolidate_topic(SCOPE, "topic-local-ai")
    assert summary1 is not None and summary2.revision_id == summary1.revision_id
    assert repeat_created is False

    # A worker can restart after a claim and before acknowledgement. The
    # second claimant receives a higher fence; re-extraction reuses evidence.
    scheduler = MindScheduler(path)
    crash_job = scheduler.enqueue(
        SCOPE, JobType.EXTRACT_EVENT, "demo-preference",
        generation="crash-fixture-v1",
    )
    crash_recovered = crash_job.status.value == "completed"
    if not crash_recovered:
        now = datetime.now(timezone.utc) + timedelta(seconds=1)
        first_claim = SQLiteMindStore(path, clock=lambda: now).claim(
            SCOPE, "demo-crashed-worker", lease_seconds=10,
        )
        assert first_claim is not None and first_claim.job_id == crash_job.job_id
        later = now + timedelta(seconds=11)
        fresh_store = SQLiteMindStore(path, clock=lambda: later)
        fresh_claim = fresh_store.claim(
            SCOPE, "demo-recovery-worker", lease_seconds=10,
        )
        assert fresh_claim is not None and fresh_claim.job_id == crash_job.job_id
        assert fresh_claim.fencing_token > first_claim.fencing_token
        counts = MindHandlers(path).execute(SCOPE, fresh_claim)
        assert fresh_store.complete(
            SCOPE, fresh_claim.job_id, "demo-recovery-worker",
            fresh_claim.fencing_token, result_counts=counts,
        )
        crash_recovered = True
    assert memory_store.count_memories(SCOPE) == count_after

    # Explicitly pinned fake vectors demonstrate outage, lexical survival,
    # retry and persisted vector coverage without Ollama or network access.
    fixture = SyntheticEmbeddingFixture()
    vector_job = scheduler.enqueue(
        SCOPE, JobType.MAINTAIN_INDEX, "demo-preference",
        generation="fixture-vector-v2", priority=100,
        config={
            "include_embeddings": True, "space": fixture.space.model_dump(mode="json"),
        },
    )
    outage_seen = vector_job.attempt_count > 0
    if vector_job.status.value != "completed":
        outage = MindWorker(
            path, SCOPE, worker_id="demo-outage-worker",
            embedding_provider=fixture,
        ).run_once(max_jobs=1)
        outage_seen = outage.retried == 1
        assert RetrievalEngine(path).retrieve(
            SCOPE, RetrievalRequest(
                tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
                query="Python", token_budget=1200,
            ),
        ).memories
        recovered = MindWorker(
            path, SCOPE, worker_id="demo-vector-recovery",
            clock=lambda: datetime.now(timezone.utc) + timedelta(hours=1),
            embedding_provider=fixture,
        ).run_once(max_jobs=8)
        assert recovered.completed >= 1
    coverage = RetrievalEngine(path, provider=fixture).index_status(SCOPE)
    assert coverage.compatible_embeddings == coverage.canonical_count

    # Exact RAM claims are seeded via existing validated storage because the
    # Stage 3 extractor has no RAM grammar. Background review never approves.
    old_event = event("demo-ram-old", "My test computer has 4 GB RAM.", START)
    upgrade_at = START + timedelta(days=10)
    new_event = event(
        "demo-ram-new", "I upgraded my test computer to 12 GB RAM.", upgrade_at,
    )
    for item in (old_event, new_event):
        append_once(store, item)
    old = ram_memory(old_event, "demo-memory-ram-old", START, upgrade_at)
    new = ram_memory(new_event, "demo-memory-ram-new", upgrade_at, upgrade_at + timedelta(days=10))
    memory_store.upsert(SCOPE, old)
    memory_store.upsert(SCOPE, new)
    reviewer = ConflictReviewer(path)
    proposed = reviewer.inspect_event(SCOPE, new_event.event_id)
    pending = projections.list_reviews(SCOPE)
    assert pending and all(item.status.value == "pending" for item in pending)
    MindWorker(path, SCOPE, worker_id="demo-final-worker").run_once(max_jobs=32)

    # Manual RAM fixtures also need compatible vectors. A generation keyed to
    # the actual corpus count makes this repeatable without ignoring new rows.
    refresh = scheduler.enqueue(
        SCOPE, JobType.MAINTAIN_INDEX, "demo-preference",
        generation=f"fixture-refresh-{memory_store.count_memories(SCOPE)}", priority=100,
        config={"include_embeddings": True, "space": fixture.space.model_dump(mode="json")},
    )
    if refresh.status.value != "completed":
        MindWorker(
            path, SCOPE, worker_id="demo-fixture-refresh", embedding_provider=fixture,
        ).run_once(max_jobs=8)
    coverage = RetrievalEngine(path, provider=fixture).index_status(SCOPE)
    assert coverage.compatible_embeddings == coverage.canonical_count

    # Erasure uses a separate sole-source synthetic event. Once tombstoned,
    # rerunning this script must not append that ID again.
    erase_event = event("demo-erased-once", "I prefer disposable synthetic text.")
    with queue._read() as connection:
        tombstoned = connection.execute(
            """SELECT 1 FROM mind_erased_events
               WHERE tenant_id=? AND namespace=? AND event_id=?""",
            (SCOPE.tenant_id, SCOPE.namespace, erase_event.event_id),
        ).fetchone() is not None
    erased_now = False
    if not tombstoned:
        append_once(store, erase_event)
        MindWorker(path, SCOPE, worker_id="demo-erase-worker").run_once(max_jobs=16)
        privacy = SQLitePrivacyStore(path)
        plan = privacy.erase_plan(SCOPE, erase_event.event_id)
        if plan.blocked_reason is None:
            privacy.erase_confirm(
                SCOPE, erase_event.event_id, plan.plan_digest, confirm=True,
            )
            erased_now = True
            assert store.get(SCOPE, erase_event.event_id) is None

    reopened = SQLiteEventStore(path)
    assert reopened.status().ready
    assert SQLiteMemoryStore(path).count_memories(SCOPE) >= count_after
    print(json.dumps({
        "database": str(path), "schema": schema,
        "events_inserted_this_run": inserted,
        "outbox_pending_before_worker": pending_before,
        "worker_claimed": first.claimed,
        "worker_completed": first.completed,
        "second_worker_claimed": second.claimed,
        "canonical_memories_after_initial_worker": count_after,
        "topic_summary_revision": summary1.revision_number,
        "unchanged_consolidation_created_revision": repeat_created,
        "crash_claim_recovered": crash_recovered,
        "synthetic_provider_outage_seen": outage_seen,
        "compatible_embeddings": coverage.compatible_embeddings,
        "canonical_count_at_index_check": coverage.canonical_count,
        "new_conflict_reviews": proposed,
        "pending_conflict_reviews": len(pending),
        "erased_synthetic_event_this_run": erased_now,
        "reopened_ready": reopened.status().ready,
    }, separators=(",", ":")))


if __name__ == "__main__":
    main()
