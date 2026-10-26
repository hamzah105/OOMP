"""Stage 6 acceptance: populated migrations, processes and bounded recovery."""
from __future__ import annotations

import json
import multiprocessing
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import timedelta
from threading import Barrier

import pytest

from test_stage6_storage import NOW, event, old_v4, scope
from test_stage5_storage import add_memory
from test_stage6_engine import SCOPE, T, source, memory_node

from oomp.domain.models import MemoryEdge
from oomp.domain.memories import EntityMention, SourceSpan
from oomp.ingestion.pipeline import ExtractionPipeline
from oomp.mind.contracts import JobStatus, JobType, ReviewStatus
from oomp.mind.governance import ConflictReviewer
from oomp.mind.handlers import MindHandlers
from oomp.mind.scheduler import MindScheduler
from oomp.mind.worker import MindWorker, WorkerRun
from oomp.retrieval.contracts import EmbeddingSpace, RetrievalRequest
from oomp.retrieval.engine import RetrievalEngine
from oomp.storage import SQLiteEntityStore, SQLiteGraphStore, SQLiteMemoryStore, SQLiteRetrievalStore, SQLiteTopicStore
from oomp.storage.errors import StorageBusyError, StorageUnavailableError
from oomp.storage.mind_store import SQLiteMindStore, LostLeaseError, InvalidJobTransitionError
from oomp.storage.mind_projection_store import SQLiteMindProjectionStore
from oomp.storage.sqlite import SQLiteEventStore
from oomp.storage.migrations import verify_v5
from oomp.storage.retrieval_store import content_digest


def _process_claim(path, gate, output, worker, crash=False):
    queue = SQLiteMindStore(path, clock=lambda: NOW)
    gate.wait(15)
    job = queue.claim(scope(), worker, lease_seconds=30)
    if crash and job is not None:
        ExtractionPipeline(path).process_event(scope(), job.target_id)
        os._exit(0)
    output.put(None if job is None else (job.job_id, job.fencing_token))


def _nodes_for_review(path):
    old = source("old-claim", "My test computer has 4 GB RAM.", T)
    new_at = T + timedelta(days=2)
    new = source("new-claim", "I upgraded my test computer to 12 GB RAM.", new_at)
    events = SQLiteEventStore(path)
    for item in (old, new):
        events.append(SCOPE, item)
    memories = SQLiteMemoryStore(path)
    memories.put(SCOPE, memory_node(old, "old-memory", T, new_at))
    memories.put(SCOPE, memory_node(new, "new-memory", new_at, new_at + timedelta(days=5)))
    reviewer = ConflictReviewer(path)
    assert reviewer.inspect_event(SCOPE, new.event_id) == 1
    return SQLiteMindProjectionStore(path).list_reviews(SCOPE)[0]


def test_populated_genuine_v4_preserves_every_old_table_and_trigger(tmp_path):
    path = tmp_path / "real-v4.sqlite3"
    old_v4(path)
    one = add_memory(path, "project", "OOMP (Object-Oriented Context Map).")
    two = add_memory(path, "tool", "OOMP uses Python.")
    events = SQLiteEventStore(path)
    proof = events.get(scope(), "event-project")
    entity = SQLiteEntityStore(path).resolve(scope(), EntityMention(
        name="OOMP", entity_type="project", aliases=("Object-Oriented Context Map",),
        source_event_id=proof.event_id,
        source_span=SourceSpan(start=0, end=len(proof.content), quote=proof.content),
    ))
    with closing(sqlite3.connect(path)) as c, c:
        c.execute("INSERT INTO memory_entities VALUES (?,?,?,?)",
                  ("tenant", "personal", one.memory_id, entity.entity_id))
    SQLiteGraphStore(path).add_edge(scope(), MemoryEdge(
        edge_id="old-link", tenant_id="tenant", namespace="personal",
        source_node_id=one.memory_id, target_node_id=two.memory_id,
        relationship_type="RELATED_TO", source_event_ids=(proof.event_id,), created_at=NOW,
    ))
    topics = SQLiteTopicStore(path)
    topics.create_topic(scope(), "old-topic", "OOMP")
    topics.assign_memory(scope(), "old-topic", one.memory_id)
    space = EmbeddingSpace(provider="fixture", model="two-axis", version="v1", dimension=2)
    index = SQLiteRetrievalStore(path)
    index.put_embedding_batch(scope(), space, (
        (one.memory_id, content_digest(one.canonical_content), (1., 0.)),
        (two.memory_id, content_digest(two.canonical_content), (0., 1.)),
    ))
    with closing(sqlite3.connect(path)) as c:
        names = [r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        before = {name: sorted(c.execute(f'SELECT * FROM "{name}"').fetchall(), key=repr)
                  for name in names}
        triggers = dict(c.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'"))
    assert SQLiteEventStore(path).initialize() == 5
    with closing(sqlite3.connect(path)) as c:
        assert verify_v5(c) and not c.execute("PRAGMA foreign_key_check").fetchall()
        for name, rows in before.items():
            assert sorted(c.execute(f'SELECT * FROM "{name}"').fetchall(), key=repr) == rows
        for name, sql in triggers.items():
            assert c.execute("SELECT sql FROM sqlite_master WHERE name=?", (name,)).fetchone()[0] == sql
    assert index.index_status(scope(), space).compatible_embeddings == 2
    with index.read_snapshot(scope()) as read:
        assert read.lexical("OOMP") and read.neighbors(one.memory_id)
    queue = SQLiteMindStore(path)
    assert queue.backfill_events(scope(), limit=1) == 1
    assert queue.backfill_events(scope(), limit=1) == 1
    assert queue.backfill_events(scope(), limit=1) == 0


def test_separate_processes_exclude_claim_and_recover_expired_owner(tmp_path):
    path = tmp_path / "process-claims.sqlite3"
    queue = SQLiteMindStore(path, clock=lambda: NOW)
    queue.initialize()
    queue.append(scope(), event())
    queue.dispatch_outbox(scope())
    context = multiprocessing.get_context("spawn")
    gate, output = context.Event(), context.Queue()
    children = [context.Process(target=_process_claim, args=(str(path), gate, output, name))
                for name in ("process-a", "process-b")]
    try:
        for child in children:
            child.start()
        gate.set()
        results = [output.get(timeout=20), output.get(timeout=20)]
        for child in children:
            child.join(10)
            assert child.exitcode == 0
        claims = [value for value in results if value is not None]
        assert len(claims) == 1
        first = queue.get_job(scope(), claims[0][0])
        replacement = SQLiteMindStore(path, clock=lambda: NOW + timedelta(seconds=31))
        second = replacement.claim(scope(), "process-replacement")
        assert second.fencing_token > first.fencing_token
        with pytest.raises(LostLeaseError):
            replacement.complete(scope(), first.job_id, first.lease_owner, first.fencing_token)
        assert replacement.complete(scope(), second.job_id, "process-replacement", second.fencing_token)
    finally:
        for child in children:
            if child.is_alive():
                child.terminate()
                child.join(5)
        output.close()
        output.join_thread()


def test_process_dies_after_derived_commit_before_ack_then_replay_is_idempotent(tmp_path):
    path = tmp_path / "crash-window.sqlite3"
    queue = SQLiteMindStore(path, clock=lambda: NOW)
    queue.initialize()
    queue.append(scope(), event(content="I prefer Python."))
    queue.dispatch_outbox(scope())
    context = multiprocessing.get_context("spawn")
    gate, output = context.Event(), context.Queue()
    child = context.Process(target=_process_claim, args=(str(path), gate, output, "dead-worker", True))
    try:
        child.start()
        gate.set()
        child.join(20)
        assert child.exitcode == 0
        assert SQLiteMemoryStore(path).count_memories(scope()) == 1
        later = NOW + timedelta(seconds=31)
        fresh = SQLiteMindStore(path, clock=lambda: later)
        claimed = fresh.claim(scope(), "resumed")
        assert claimed.attempt_count == 2
        counts = MindHandlers(path, clock=lambda: later).execute(scope(), claimed)
        assert counts["memories_created"] == 0 and counts["evidence_links_added"] == 0
        fresh.complete(scope(), claimed.job_id, "resumed", claimed.fencing_token, result_counts=counts)
        MindWorker(path, scope(), clock=lambda: later).run_once(max_jobs=8)
        assert SQLiteMemoryStore(path).count_memories(scope()) == 1
        assert all(j.status is JobStatus.COMPLETED for j in fresh.list_jobs(scope()))
    finally:
        if child.is_alive():
            child.terminate()
            child.join(5)
        output.close()
        output.join_thread()


def test_small_queue_drains_intake_and_all_downstream_work_without_capacity_failure(tmp_path):
    path = tmp_path / "backpressure.sqlite3"
    queue = SQLiteMindStore(path, clock=lambda: NOW, max_pending=4)
    queue.initialize()
    for i in range(10):
        queue.append(scope(), event(f"source-{i}", content=f"I prefer item{i}."))
    worker = MindWorker(path, scope(), clock=lambda: NOW, max_pending=4)
    for _ in range(20):
        run = worker.run_once(max_jobs=5)
        assert not run.failed and not run.retried and not run.lost_lease
        status = queue.status(scope())
        assert sum(status[k] for k in ("queued", "running", "retry_wait")) <= 4
        if status["events_pending_extraction"] == 0 and status["queued"] == 0:
            break
    assert queue.status(scope())["completed"] == 30
    assert queue.status(scope())["outbox_pending"] == 0
    assert SQLiteMemoryStore(path).count_memories(scope()) == 10


def test_interruption_after_effects_releases_lease_and_replays_without_duplicate_proof(tmp_path):
    path = tmp_path / "interrupted.sqlite3"
    clock = [NOW]
    queue = SQLiteMindStore(path, clock=lambda: clock[0])
    queue.initialize()
    queue.append(scope(), event(content="I prefer Python."))

    class InterruptAfterWrite:
        def execute(self, authorized, job):
            MindHandlers(path, clock=lambda: clock[0]).execute(authorized, job)
            raise KeyboardInterrupt()

    worker = MindWorker(path, scope(), clock=lambda: clock[0], handlers=InterruptAfterWrite())
    with pytest.raises(KeyboardInterrupt):
        worker.run_once(max_jobs=1)
    extraction = next(j for j in queue.list_jobs(scope()) if j.job_type is JobType.EXTRACT_EVENT)
    assert extraction.status is JobStatus.RETRY_WAIT
    assert extraction.last_error_code == "worker_interrupted"
    clock[0] += timedelta(seconds=2)
    result = MindWorker(path, scope(), clock=lambda: clock[0]).run_once(max_jobs=8)
    assert result.failed == 0
    node = SQLiteMemoryStore(path).list_memories(scope()).memories[0]
    assert node.source_event_ids == ("e1",)
    assert queue.get_job(scope(), extraction.job_id).status is JobStatus.COMPLETED


def test_polling_busy_backoff_stop_and_batch_bounds_are_deterministic(tmp_path, monkeypatch):
    worker = MindWorker(tmp_path / "unopened.sqlite3", scope())
    calls, waits = [], []

    def attempt(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise StorageBusyError("synthetic busy")
        return WorkerRun()

    monkeypatch.setattr(worker, "run_once", attempt)
    monkeypatch.setattr("oomp.mind.worker.time.sleep", waits.append)
    assert worker.work(max_cycles=2, poll_seconds=.25).claimed == 0
    assert len(calls) == 2 and waits == [.25]
    worker.work(max_cycles=2, stop=lambda: True)
    assert len(calls) == 2
    with pytest.raises(ValueError):
        worker.work(poll_seconds=0)
    with pytest.raises(ValueError):
        MindWorker(tmp_path / "unopened.sqlite3", scope()).run_once(max_jobs=101)


def test_unsupported_policy_and_cancelled_claim_cannot_be_acknowledged_or_retried(tmp_path):
    path = tmp_path / "policies.sqlite3"
    queue = SQLiteMindStore(path)
    queue.initialize()
    queue.append(scope(), event())
    poison = queue.enqueue(scope(), JobType.EXTRACT_EVENT, "event", "e1",
                           idempotency_key="old-policy", policy_version="extract.v999")
    assert queue.claim(scope(), "worker", accepted_policy_versions=("extract.v1",)) is None
    assert queue.get_job(scope(), poison.job_id).last_error_code == "unsupported_policy"
    with pytest.raises(InvalidJobTransitionError):
        queue.retry(scope(), poison.job_id)
    queue.dispatch_outbox(scope())
    claim = queue.claim(scope(), "worker")
    cancelled = queue.cancel(scope(), claim.job_id)
    assert cancelled.status is JobStatus.CANCELLED
    with pytest.raises(LostLeaseError):
        queue.complete(scope(), claim.job_id, "worker", claim.fencing_token)
    with pytest.raises(InvalidJobTransitionError):
        queue.retry(scope(), claim.job_id)


def test_governed_approval_rollback_and_concurrent_rejection_stay_consistent(tmp_path, monkeypatch):
    path = tmp_path / "governance.sqlite3"
    SQLiteEventStore(path).initialize()
    review = _nodes_for_review(path)
    store = SQLiteMindProjectionStore(path)
    original = store._apply_resolution_in_transaction

    def fail_after_edge(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic crash before decision")

    monkeypatch.setattr(store, "_apply_resolution_in_transaction", fail_after_edge)
    with pytest.raises(RuntimeError):
        store.approve_review(SCOPE, review.proposal_id)
    assert not SQLiteGraphStore(path).list_edges(SCOPE).edges
    assert store.get_review(SCOPE, review.proposal_id).status is ReviewStatus.PENDING
    barrier = Barrier(2)

    def decide(approve):
        barrier.wait(timeout=5)
        reviewer = ConflictReviewer(path)
        try:
            value = reviewer.approve(SCOPE, review.proposal_id) if approve else reviewer.reject(SCOPE, review.proposal_id)
            return value.status
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(decide, True), pool.submit(decide, False)
        results = (a.result(timeout=15), b.result(timeout=15))
    assert sum(result is not None for result in results) == 1
    decided = SQLiteMindProjectionStore(path).get_review(SCOPE, review.proposal_id)
    edges = SQLiteGraphStore(path).list_edges(SCOPE).edges
    assert len(edges) == (1 if decided.status is ReviewStatus.APPROVED else 0)