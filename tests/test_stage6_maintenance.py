"""Offline Stage 6 maintenance, privacy race and operator acceptance tests."""
from __future__ import annotations

from oomp.storage.migrations import SCHEMA_VERSION

import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from test_stage6_storage import NOW, scope, event
from test_stage6_privacy import setup, source as privacy_source
from test_stage6_engine import SCOPE, T, source, memory_node
from oomp.cli import main
from oomp.domain.models import AuthorizedScope
from oomp.domain.enums import EventType, SourceType
from oomp.domain.graph import TemporalQuery
from oomp.ingestion.pipeline import ExtractionPipeline
from oomp.mind.contracts import JobStatus, JobType
from oomp.mind.governance import ConflictReviewer
from oomp.mind.scheduler import MindScheduler
from oomp.mind.worker import MindWorker
from oomp.providers.errors import EmbeddingProviderUnavailable
from oomp.retrieval.contracts import EmbeddingSpace, RetrievalRequest
from oomp.retrieval.engine import RetrievalEngine
from oomp.storage.errors import ScopeMismatchError, SourceEventMissingError, MemoryNotFoundError
from oomp.storage.graph_store import SQLiteGraphStore
from oomp.storage.memory_store import SQLiteMemoryStore
from oomp.storage.mind_projection_store import SQLiteMindProjectionStore
from oomp.storage.mind_store import SQLiteMindStore
from oomp.storage.privacy_store import SQLitePrivacyStore, ErasureBlockedError
from oomp.storage.retrieval_store import SQLiteRetrievalStore, content_digest
from oomp.storage.sqlite import SQLiteEventStore
from oomp.storage.topic_store import SQLiteTopicStore


class EmbeddingFixture:
    space = EmbeddingSpace(provider="synthetic", model="two-axis", version="v1", dimension=2)

    def __init__(self):
        self.calls = 0
        self.invalid = False

    def embed(self, texts):
        self.calls += 1
        if self.calls == 2:
            raise EmbeddingProviderUnavailable("synthetic outage with private details")
        if self.invalid:
            return [(float("nan"), 0.) for _ in texts]
        return [(1., 0.) for _ in texts]


def request(authorized, query="tea", **kwargs):
    return RetrievalRequest(tenant_id=authorized.tenant_id, namespace=authorized.namespace,
                            query=query, token_budget=6000, **kwargs)


def test_embedding_outage_preserves_partial_vectors_lexical_recall_and_skips_unchanged(tmp_path):
    path = tmp_path / "partial.sqlite3"
    clock = [NOW]
    queue = SQLiteMindStore(path, clock=lambda: clock[0])
    queue.initialize()
    for i in range(19):
        queue.append(scope(), event(f"e-{i}", content=f"I prefer item{i}."))
        ExtractionPipeline(path).process_event(scope(), f"e-{i}")
    provider = EmbeddingFixture()
    scheduler = MindScheduler(path, clock=lambda: clock[0])
    config = {"include_embeddings": True, "space": provider.space.model_dump(mode="json")}
    job = scheduler.enqueue(scope(), JobType.MAINTAIN_INDEX, "e-0",
                            generation="outage", config=config, priority=100)
    worker = MindWorker(path, scope(), clock=lambda: clock[0], embedding_provider=provider)
    assert worker.run_once(max_jobs=1).retried == 1
    status = SQLiteRetrievalStore(path).index_status(scope(), provider.space)
    assert status.compatible_embeddings == 16 and status.canonical_count == 19
    assert queue.get_job(scope(), job.job_id).last_error_code == "provider_unavailable"
    assert RetrievalEngine(path).retrieve(scope(), request(scope(), "item0")).memories
    clock[0] += timedelta(seconds=2)
    assert worker.run_once(max_jobs=1).completed == 1
    assert SQLiteRetrievalStore(path).index_status(scope(), provider.space).compatible_embeddings == 19
    calls = provider.calls
    scheduler.enqueue(scope(), JobType.MAINTAIN_INDEX, "e-0", generation="unchanged",
                      config=config, priority=100)
    assert worker.run_once(max_jobs=1).completed == 1
    assert provider.calls == calls
    queue.append(scope(), event("e-new", content="I prefer another item."))
    ExtractionPipeline(path).process_event(scope(), "e-new")
    provider.invalid = True
    bad = scheduler.enqueue(scope(), JobType.MAINTAIN_INDEX, "e-new", generation="invalid",
                            config=config, priority=100)
    assert worker.run_once(max_jobs=1).failed == 1
    assert queue.get_job(scope(), bad.job_id).last_error_code == "provider_invalid"
    assert SQLiteRetrievalStore(path).index_status(scope(), provider.space).compatible_embeddings == 19


def test_background_eligibility_corrections_default_offline_and_no_implicit_embedding(tmp_path, monkeypatch):
    path = tmp_path / "eligibility.sqlite3"
    queue = SQLiteMindStore(path)
    queue.initialize()
    values = (
        event("user", content="I prefer Python."),
        event("assistant", content="I prefer Rust.").model_copy(update={
            "event_type": EventType.ASSISTANT_MESSAGE, "source_type": SourceType.ASSISTANT}),
        event("secret", content="I prefer Kotlin. password=hunter2"),
        event("unsupported", content="Unrecognized ordinary conversation."),
        event("correction", content="I prefer tea.").model_copy(update={"event_type": EventType.CORRECTION}),
    )
    for value in values:
        queue.append(scope(), value)

    class ForbiddenProvider:
        space = EmbeddingFixture.space
        def embed(self, texts):
            raise AssertionError("embedding was not opted in")

    def no_network(*args, **kwargs):
        raise AssertionError("offline worker attempted network")
    monkeypatch.setattr("urllib.request.OpenerDirector.open", no_network)
    run = MindWorker(path, scope(), embedding_provider=ForbiddenProvider()).run_once(max_jobs=32)
    assert run.failed == 0
    memories = SQLiteMemoryStore(path).list_memories(scope()).memories
    assert {node.canonical_content for node in memories} == {"User prefers Python.", "User prefers tea."}
    assert all(node.metadata["verified"] is False for node in memories)
    assert queue.get(scope(), "user").content == "I prefer Python."
    assert queue.get(scope(), "correction").event_type.value == "correction"
    assert queue.status(scope())["events_pending_extraction"] == 0


def test_summary_membership_change_history_scope_and_complete_bounds(tmp_path):
    path = tmp_path / "summaries.sqlite3"
    store, results = setup(path)
    topics = SQLiteTopicStore(path)
    topics.create_topic(scope(), "topic", "Drinks")
    topics.assign_memory(scope(), "topic", results[0].memory_ids[0])
    projections = SQLiteMindProjectionStore(path)
    first, _ = projections.consolidate_topic(scope(), "topic")
    store.append(scope(), privacy_source("e2", text="I prefer coffee."))
    second_memory = ExtractionPipeline(path).process_event(scope(), "e2").memory_ids[0]
    topics.assign_memory(scope(), "topic", second_memory)
    cutoff = datetime.now(timezone.utc)
    assert projections.get_summary(scope(), "topic") is None
    historical = projections.get_summary(scope(), "topic", known_at=cutoff)
    assert historical.revision_id == first.revision_id and historical.freshness == "stale"
    with pytest.raises(ValueError):
        projections.consolidate_topic(scope(), "topic", max_sources=1)
    with pytest.raises(ValueError):
        projections.consolidate_topic(scope(), "topic", max_chars=128)
    second, created = projections.consolidate_topic(scope(), "topic")
    assert created and second.revision_number == 2 and len(second.source_memory_ids) == 2
    assert {item.event_id for item in second.sources} == {"e1", "e2"}
    assert all(not item.verified and item.validity == "uncertain" for item in second.sources)
    other = scope("other")
    store.append(other, privacy_source("foreign", tenant="other", text="I prefer private coffee."))
    foreign = ExtractionPipeline(path).process_event(other, "foreign").memory_ids[0]
    with pytest.raises(MemoryNotFoundError):
        topics.assign_memory(scope(), "topic", foreign)
    assert all(item.event_id != "foreign" for item in projections.get_summary(scope(), "topic").sources)


def test_all_source_retraction_excludes_current_recall_and_keeps_prior_knowledge(tmp_path):
    path = tmp_path / "withdrawn.sqlite3"
    store, results = setup(path)
    memory_id = results[0].memory_ids[0]
    cutoff = datetime.now(timezone.utc)
    projections = SQLiteMindProjectionStore(path)
    assert projections.retract_source(scope(), memory_id, "e1")
    assert not projections.retract_source(scope(), memory_id, "e1")
    assert store.get(scope(), "e1") is not None
    assert not RetrievalEngine(path).retrieve(scope(), request(scope())).memories
    historical = RetrievalEngine(path).retrieve(scope(), request(scope(), known_at=cutoff))
    assert historical.memories[0].source_event_ids == ("e1",)
    state = SQLiteGraphStore(path).memory_state(scope(), memory_id)
    assert state.effective_status.value == "retracted"
    with pytest.raises(ValueError):
        projections.retract_source(scope(), memory_id, "e1", reason_code="private-secret")


def test_erasure_removes_vectors_all_contaminated_revisions_and_preserves_other_scope(tmp_path):
    path = tmp_path / "derived.sqlite3"
    store, results = setup(path)
    original = SQLiteMemoryStore(path).get(scope(), results[0].memory_ids[0])
    index = SQLiteRetrievalStore(path)
    space = EmbeddingFixture.space
    index.put_embedding_batch(scope(), space, (
        (original.memory_id, content_digest(original.canonical_content), (1., 0.)),
    ))
    topics = SQLiteTopicStore(path)
    topics.create_topic(scope(), "topic", "Drinks")
    topics.assign_memory(scope(), "topic", original.memory_id)
    projections = SQLiteMindProjectionStore(path)
    first, _ = projections.consolidate_topic(scope(), "topic")
    store.append(scope(), privacy_source("e2", text="I prefer coffee."))
    second_id = ExtractionPipeline(path).process_event(scope(), "e2").memory_ids[0]
    topics.assign_memory(scope(), "topic", second_id)
    second, _ = projections.consolidate_topic(scope(), "topic")
    other = scope("other")
    store.append(other, privacy_source("e1", tenant="other"))
    other_id = ExtractionPipeline(path).process_event(other, "e1").memory_ids[0]
    plan = store.erase_plan(scope(), "e1")
    assert plan.affected_embeddings == 1
    assert set(plan.delete_summary_revision_ids) == {first.revision_id, second.revision_id}
    store.erase_confirm(scope(), "e1", plan.plan_digest, confirm=True)
    with closing(sqlite3.connect(path)) as c:
        assert c.execute("SELECT COUNT(*) FROM memory_embeddings WHERE tenant_id='tenant'").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM mind_summary_revisions WHERE tenant_id='tenant'").fetchone()[0] == 0
        assert not c.execute("PRAGMA foreign_key_check").fetchall()
    assert not RetrievalEngine(path).retrieve(scope(), request(scope())).memories
    assert SQLiteMemoryStore(path).get(other, other_id) is not None
    assert SQLiteMemoryStore(path).get(scope(), second_id) is not None


@pytest.mark.parametrize("operation", ["extraction", "embedding"])
def test_paused_effect_after_erasure_cannot_restore_source_or_derived_rows(tmp_path, operation):
    path = tmp_path / (operation + ".sqlite3")
    store = SQLitePrivacyStore(path)
    store.initialize()
    store.append(scope(), privacy_source("e1"))
    pipeline = ExtractionPipeline(path)
    if operation == "extraction":
        apply = pipeline.memory_store.apply_batch

        def erase_then_apply(*args, **kwargs):
            plan = store.erase_plan(scope(), "e1")
            store.erase_confirm(scope(), "e1", plan.plan_digest, confirm=True)
            return apply(*args, **kwargs)

        pipeline.memory_store.apply_batch = erase_then_apply
        with pytest.raises(SourceEventMissingError):
            pipeline.process_event(scope(), "e1")
    else:
        pipeline.process_event(scope(), "e1")

        class ErasingProvider:
            space = EmbeddingFixture.space
            def embed(self, texts):
                plan = store.erase_plan(scope(), "e1")
                store.erase_confirm(scope(), "e1", plan.plan_digest, confirm=True)
                return [(1., 0.) for _ in texts]
        report = RetrievalEngine(path, provider=ErasingProvider()).index(scope(), include_embeddings=True)
        assert report.embeddings_failed == 1
    assert store.get(scope(), "e1") is None
    assert SQLiteMemoryStore(path).count_memories(scope()) == 0
    with closing(sqlite3.connect(path)) as c:
        for table in ("memory_fts_docs", "memory_embeddings", "memories", "memory_sources"):
            assert c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_shared_retracted_proof_and_graph_dependencies_fail_closed(tmp_path):
    path = tmp_path / "blocked.sqlite3"
    store, results = setup(path, ("e1", "e2"))
    memory_id = results[0].memory_ids[0]
    SQLiteMindProjectionStore(path).retract_source(scope(), memory_id, "e2")
    plan = store.erase_plan(scope(), "e1")
    assert plan.blocked_reason == "unsupported_shared_proof"
    with pytest.raises(ErasureBlockedError):
        store.erase_confirm(scope(), "e1", plan.plan_digest, confirm=True)
    assert store.get(scope(), "e1") is not None
    from oomp.domain.models import MemoryEdge
    store.append(scope(), privacy_source("e3", text="I prefer coffee."))
    other = ExtractionPipeline(path).process_event(scope(), "e3").memory_ids[0]
    SQLiteGraphStore(path).add_edge(scope(), MemoryEdge(
        edge_id="dependent", tenant_id="tenant", namespace="personal",
        source_node_id=memory_id, target_node_id=other, relationship_type="RELATED_TO",
        source_event_ids=("e3",), created_at=NOW,
    ))
    graph_plan = store.erase_plan(scope(), "e3")
    assert graph_plan.blocked_reason == "graph_dependency"
    with pytest.raises(ErasureBlockedError):
        store.erase_confirm(scope(), "e3", graph_plan.plan_digest, confirm=True)


def test_erasure_review_scan_refuses_incomplete_dependency_inventory(tmp_path, monkeypatch):
    path = tmp_path / "review-bound.sqlite3"
    store = SQLitePrivacyStore(path)
    store.initialize()
    store.append(SCOPE, source("private", "I prefer tea."))
    ExtractionPipeline(path).process_event(SCOPE, "private")
    events = (
        source("ram-a", "My test computer has 4 GB RAM."),
        source("ram-b", "My test computer has 8 GB RAM."),
    )
    for i, value in enumerate(events):
        store.append(SCOPE, value)
        SQLiteMemoryStore(path).put(SCOPE, memory_node(value, f"ram-{i}", T, T + timedelta(days=5)))
    reviewer = ConflictReviewer(path)
    reviewer.inspect_event(SCOPE, "ram-a")
    reviewer.inspect_event(SCOPE, "ram-b")
    assert len(SQLiteMindProjectionStore(path).list_reviews(SCOPE)) == 2
    monkeypatch.setattr("oomp.storage.privacy_store._MAX_DEPENDENCIES", 1)
    with pytest.raises(ErasureBlockedError, match="dependency_limit"):
        store.erase_plan(SCOPE, "private")
    assert store.get(SCOPE, "private") is not None


def test_cli_redacts_aliases_requires_confirmation_and_returns_failure_for_failed_job(tmp_path, capsys):
    path = tmp_path / "cli.sqlite3"
    store = SQLitePrivacyStore(path)
    store.initialize()
    store.append(scope(), event("project", content="I am developing a project called Classified (Secret Name)."))
    ExtractionPipeline(path).process_event(scope(), "project")
    common = ["--db", str(path), "--tenant", "tenant", "--namespace", "personal"]
    assert main(["mind", "erase-plan", "--event-id", "project", *common]) == 0
    output = capsys.readouterr()
    plan = json.loads(output.out)
    assert "secret name" not in output.out.lower() and "classified" not in output.out.lower()
    assert plan["delete_alias_count"] >= 1 and "delete_alias_keys" not in plan
    assert main(["mind", "erase-confirm", "--event-id", "project",
                 "--plan-digest", plan["plan_digest"], *common]) == 1
    capsys.readouterr()
    assert store.get(scope(), "project") is not None
    assert main(["mind", "status", *common]) == 0
    json.loads(capsys.readouterr().out)
    queue = SQLiteMindStore(path)
    job = queue.enqueue(scope(), JobType.MAINTAIN_INDEX, "event", "project",
                        idempotency_key="no-provider", policy_version="index.v1", priority=100,
                        config={"include_embeddings": True, "space": EmbeddingFixture.space.model_dump(mode="json")})
    assert main(["mind", "run-once", "--max-jobs", "1", *common]) == 1
    assert json.loads(capsys.readouterr().out)["failed"] == 1
    assert queue.get_job(scope(), job.job_id).status is JobStatus.FAILED
    with pytest.raises(SystemExit) as missing:
        main(["mind", "status", "--tenant", "tenant", "--namespace", "personal"])
    assert missing.value.code == 2
    capsys.readouterr()
    assert main(["mind", "erase-confirm", "--event-id", "project",
                 "--plan-digest", store.erase_plan(scope(), "project").plan_digest, "--confirm", *common]) == 0
    capsys.readouterr()
    assert store.get(scope(), "project") is None


def test_standard_example_runs_fresh_and_again_against_real_sqlite(tmp_path):
    path = tmp_path / "demo.sqlite3"
    script = Path(__file__).resolve().parents[1] / "examples" / "stage6_background_mind.py"
    outputs = []
    for _ in range(2):
        result = subprocess.run([sys.executable, str(script), "--db", str(path)],
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
        outputs.append(json.loads(result.stdout))
    assert outputs[0]["schema"] == SCHEMA_VERSION and outputs[0]["crash_claim_recovered"]
    assert outputs[0]["synthetic_provider_outage_seen"]
    assert outputs[0]["erased_synthetic_event_this_run"]
    assert outputs[1]["events_inserted_this_run"] == 0
    assert outputs[1]["second_worker_claimed"] == 0
    assert outputs[1]["unchanged_consolidation_created_revision"] is False
    assert outputs[1]["erased_synthetic_event_this_run"] is False
    assert outputs[1]["reopened_ready"]

def test_vector_commit_busy_retries_without_mislabeling_provider_response(tmp_path, monkeypatch):
    from oomp.storage.errors import StorageBusyError
    path = tmp_path / "vector-busy.sqlite3"
    queue = SQLiteMindStore(path, clock=lambda: NOW)
    queue.initialize()
    queue.append(scope(), event(content="I prefer tea."))
    ExtractionPipeline(path).process_event(scope(), "e1")

    class StableProvider:
        space = EmbeddingFixture.space
        def embed(self, texts):
            return [(1., 0.) for _ in texts]

    original = SQLiteRetrievalStore.put_embedding_batch
    attempts = []

    def busy_once(self, *args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise StorageBusyError("synthetic busy")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(SQLiteRetrievalStore, "put_embedding_batch", busy_once)
    provider = StableProvider()
    job = MindScheduler(path, clock=lambda: NOW).enqueue(
        scope(), JobType.MAINTAIN_INDEX, "e1", generation="busy", priority=100,
        config={"include_embeddings": True, "space": provider.space.model_dump(mode="json")},
    )
    assert MindWorker(path, scope(), clock=lambda: NOW, embedding_provider=provider).run_once(max_jobs=1).retried == 1
    assert queue.get_job(scope(), job.job_id).last_error_code == "storage_busy"
    assert MindWorker(path, scope(), clock=lambda: NOW + timedelta(seconds=2),
                      embedding_provider=provider).run_once(max_jobs=1).completed == 1
    assert SQLiteRetrievalStore(path).index_status(scope(), provider.space).compatible_embeddings == 1


def test_namespace_partition_and_immutable_provider_configuration(tmp_path):
    path = tmp_path / "namespaces.sqlite3"
    queue = SQLiteMindStore(path)
    queue.initialize()
    a, b = scope(), scope(namespace="other")
    queue.append(a, event(content="I prefer tea."))
    queue.append(b, event(namespace="other", content="I prefer coffee."))
    job = MindScheduler(path).enqueue(
        a, JobType.MAINTAIN_INDEX, "e1", generation="pinned",
        config={"include_embeddings": True, "space": EmbeddingFixture.space.model_dump(mode="json")},
    )
    with pytest.raises(TypeError):
        job.config["space"]["dimension"] = 3
    assert queue.get_job(b, job.job_id) is None
    assert queue.list_jobs(b) == ()
    queue.cancel(a, job.job_id)
    assert MindWorker(path, a).run_once(max_jobs=8).failed == 0
    assert SQLiteMemoryStore(path).count_memories(b) == 0
    assert queue.status(b)["outbox_pending"] == 1
    assert MindWorker(path, b).run_once(max_jobs=8).failed == 0
    one = SQLiteMemoryStore(path).list_memories(a).memories[0]
    two = SQLiteMemoryStore(path).list_memories(b).memories[0]
    assert one.memory_id != two.memory_id
    assert not RetrievalEngine(path).retrieve(a, request(a, "coffee")).memories
    assert not RetrievalEngine(path).retrieve(b, request(b, "tea")).memories