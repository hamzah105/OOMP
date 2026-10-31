"""Stage 6 migration, durable intake, scoped claims and lease recovery."""
from __future__ import annotations

from oomp.storage.migrations import SCHEMA_VERSION

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest

from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
from oomp.mind.contracts import JobStatus, JobType
from oomp.storage.errors import IdempotencyConflictError, StorageUnavailableError, UnsupportedSchemaVersionError, ScopeMismatchError
from oomp.storage.mind_store import (
    InvalidJobTransitionError, JobConflictError, LostLeaseError,
    QueueCapacityError, SQLiteMindStore,
)
from oomp.storage.migrations import (
    MIGRATION_1, MIGRATION_2, MIGRATION_3, MIGRATION_4, MIGRATION_5,
    verify_v4, verify_v6,
)
from oomp.storage.sqlite import SQLiteEventStore


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def scope(tenant="tenant", namespace="personal"):
    return AuthorizedScope(tenant_id=tenant,namespace=namespace,principal_id="operator")


def event(identity="e1", *, tenant="tenant", namespace="personal", content="My test computer has 4 GB RAM."):
    return MemoryEvent(
        event_id=identity,tenant_id=tenant,namespace=namespace,
        event_type="user_message",source_type="user",content=content,
        source_reference=SourceReference(
            source_system="synthetic",external_event_id=identity,timestamp=NOW,
        ),occurred_at=NOW,ingested_at=NOW,idempotency_key="key-"+identity,
    )


def old_v4(path):
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.create_function("oomp_recorded_at",0,lambda:"2026-01-01T00:00:00.000000Z")
        for statement in (*MIGRATION_1,*MIGRATION_2,*MIGRATION_3,*MIGRATION_4):
            connection.execute(statement)
        connection.execute("PRAGMA user_version=4")
        assert verify_v4(connection)


def test_fresh_and_genuine_v4_migration_preserves_data_and_guards(tmp_path):
    path=tmp_path/"old.sqlite3"
    old_v4(path)
    original=event()
    SQLiteEventStore(path).append(scope(),original)
    with closing(sqlite3.connect(path)) as connection:
        prior=tuple(connection.execute("SELECT * FROM events").fetchall())
        fts=tuple(connection.execute("SELECT * FROM memory_fts_docs").fetchall())
    store=SQLiteMindStore(path)
    assert store.status().schema_version==4 and not store.status().ready
    assert store.initialize()==SCHEMA_VERSION
    assert store.initialize()==SCHEMA_VERSION
    assert store.status().ready
    with closing(sqlite3.connect(path)) as connection:
        assert verify_v6(connection)
        assert connection.execute("PRAGMA foreign_key_check").fetchall()==[]
        assert tuple(connection.execute("SELECT * FROM events").fetchall())==prior
        assert tuple(connection.execute("SELECT * FROM memory_fts_docs").fetchall())==fts
        assert connection.execute("SELECT COUNT(*) FROM mind_event_outbox").fetchone()[0]==0
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM events")
    assert store.backfill_events(scope(),limit=1)==1
    assert store.backfill_events(scope(),limit=1)==0
    assert store.status(scope())["events_pending_extraction"]==1


def test_failed_v5_migration_rolls_back_exact_v4(tmp_path,monkeypatch):
    path=tmp_path/"rollback.sqlite3"
    old_v4(path)
    SQLiteEventStore(path).append(scope(),event(content="I prefer Python."))
    from oomp.ingestion.pipeline import ExtractionPipeline
    from oomp.storage.memory_store import SQLiteMemoryStore
    original_memory = ExtractionPipeline(path).process_event(scope(),"e1").memory_ids[0]
    import oomp.storage.migrations as migrations
    monkeypatch.setitem(migrations.MIGRATIONS,5,MIGRATION_5+("CREATE TABLE events (bad TEXT)",))
    with pytest.raises(StorageUnavailableError):
        SQLiteMindStore(path).initialize()
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0]==4
        assert verify_v4(connection)
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='mind_jobs'").fetchone() is None
    assert SQLiteMemoryStore(path).get(scope(),original_memory).source_event_ids == ("e1",)


def test_future_schema_rejected(tmp_path):
    path=tmp_path/"future.sqlite3"
    with closing(sqlite3.connect(path)) as connection,connection:
        connection.execute(f"PRAGMA user_version={SCHEMA_VERSION+1}")
    with pytest.raises(UnsupportedSchemaVersionError):
        SQLiteMindStore(path).initialize()


def test_append_outbox_duplicates_failed_append_and_late_occurrence(tmp_path):
    store=SQLiteMindStore(tmp_path/"intake.sqlite3")
    store.initialize()
    old=event("old")
    late=event("late")
    late=late.model_copy(update={"occurred_at":NOW-timedelta(days=90)})
    store.append(scope(),old)
    store.append(scope(),old)
    with pytest.raises(IdempotencyConflictError):
        store.append(scope(),event("old",content="Different fact."))
    store.append(scope(),late)
    assert store.status(scope())["outbox_pending"]==2
    assert store.dispatch_outbox(scope(),limit=1)==1
    assert store.dispatch_outbox(scope(),limit=10)==1
    assert store.dispatch_outbox(scope(),limit=10)==0
    assert {j.target_id for j in store.list_jobs(scope())}=={"old","late"}
    assert store.status(scope())["events_pending_extraction"]==2


def test_capacity_keeps_outbox_and_job_idempotency_collision(tmp_path):
    store=SQLiteMindStore(tmp_path/"cap.sqlite3",max_pending=4)
    store.initialize()
    for identity in ("e1","e2","e3","e4"):
        store.append(scope(),event(identity))
    assert store.dispatch_outbox(scope(),limit=4)==2
    assert store.status(scope())["outbox_pending"]==2
    first=store.list_jobs(scope())[0]
    with pytest.raises(JobConflictError):
        store.enqueue(scope(),JobType.EXTRACT_EVENT,"event",
            "e1" if first.target_id != "e1" else "e2",
            idempotency_key=first.idempotency_key,policy_version="extract.v1")
    store.enqueue(scope(),JobType.INSPECT_CONFLICTS,"event","e2",
        idempotency_key="inspect-e2",policy_version="inspect.v1",priority=10)
    store.enqueue(scope(),JobType.MAINTAIN_INDEX,"event","e2",
        idempotency_key="index-e2",policy_version="index.v1",priority=10)
    with pytest.raises(QueueCapacityError):
        store.enqueue(scope(),JobType.INSPECT_CONFLICTS,"event","e3",
            idempotency_key="inspect-e3",policy_version="inspect.v1")
    assert store.status(scope())["outbox_pending"]==2


def test_scoped_job_target_and_typed_config(tmp_path):
    store=SQLiteMindStore(tmp_path/"scope.sqlite3")
    store.initialize()
    store.append(scope(),event())
    other=scope("other")
    assert store.get_job(other,"missing") is None
    with pytest.raises(ScopeMismatchError):
        store.enqueue(other,JobType.EXTRACT_EVENT,"event","e1",
            idempotency_key="wrong",policy_version="extract.v1")
    with pytest.raises(ValueError):
        store.enqueue(scope(),JobType.EXTRACT_EVENT,"event","e1",
            idempotency_key="bad-config",policy_version="extract.v1",
            config={"secret":"never persist"})
    good=store.enqueue(scope(),JobType.MAINTAIN_INDEX,"event","e1",
        idempotency_key="index-e1",policy_version="index.v1",
        config={"include_embeddings":True,"space":{
            "provider":"test","model":"tiny","version":"v1","dimension":2,
        }})
    assert good.config["space"]["dimension"]==2
    assert store.list_jobs(other)==()
    assert store.status(other)["queued"]==0


def test_lease_reclaim_fences_stale_completion_and_heartbeat(tmp_path):
    now=[NOW]
    path=tmp_path/"lease.sqlite3"
    a=SQLiteMindStore(path,clock=lambda:now[0])
    b=SQLiteMindStore(path,clock=lambda:now[0])
    a.initialize()
    a.append(scope(),event())
    a.dispatch_outbox(scope())
    first=a.claim(scope(),"worker-a",lease_seconds=3)
    assert first and first.attempt_count==1
    assert a.renew(scope(),first.job_id,"worker-a",first.fencing_token,lease_seconds=3)
    now[0]+=timedelta(seconds=4)
    replacement=b.claim(scope(),"worker-b",lease_seconds=3)
    assert replacement and replacement.fencing_token>first.fencing_token
    with pytest.raises(LostLeaseError):
        a.complete(scope(),first.job_id,"worker-a",first.fencing_token)
    with pytest.raises(LostLeaseError):
        a.renew(scope(),first.job_id,"worker-a",first.fencing_token)
    assert b.complete(scope(),replacement.job_id,"worker-b",replacement.fencing_token)
    assert SQLiteMindStore(path).get_job(scope(),first.job_id).status is JobStatus.COMPLETED
    assert a.attempt_count(scope(),first.job_id)==2


def test_retry_backoff_exhaustion_and_operator_retry(tmp_path):
    now=[NOW]
    store=SQLiteMindStore(tmp_path/"retry.sqlite3",clock=lambda:now[0])
    store.initialize()
    store.append(scope(),event())
    store.dispatch_outbox(scope(),max_attempts=2)
    first=store.claim(scope(),"worker")
    assert first
    failed=store.fail(scope(),first.job_id,"worker",first.fencing_token,
        error_code="provider_unavailable",retryable=True)
    assert failed.status is JobStatus.RETRY_WAIT
    assert store.claim(scope(),"worker") is None
    now[0]+=timedelta(seconds=1)
    second=store.claim(scope(),"worker")
    assert second and second.attempt_count==2
    failed=store.fail(scope(),second.job_id,"worker",second.fencing_token,
        error_code="provider_unavailable",retryable=True)
    assert failed.status is JobStatus.FAILED
    retried=store.retry(scope(),failed.job_id)
    assert retried.status is JobStatus.QUEUED and retried.max_attempts==3
    assert store.claim(scope(),"worker").attempt_count==3


def test_permanent_failure_cancel_and_sanitized_error(tmp_path):
    store=SQLiteMindStore(tmp_path/"transitions.sqlite3")
    store.initialize()
    store.append(scope(),event())
    store.dispatch_outbox(scope())
    job=store.claim(scope(),"worker")
    with pytest.raises(ValueError):
        store.fail(scope(),job.job_id,"worker",job.fencing_token,error_code="secret from source")
    terminal=store.fail(scope(),job.job_id,"worker",job.fencing_token,
        error_code="validation_error",retryable=False)
    assert terminal.status is JobStatus.FAILED
    with pytest.raises(InvalidJobTransitionError):
        store.retry(scope(),job.job_id)
    with pytest.raises(InvalidJobTransitionError):
        store.cancel(scope(),job.job_id)


def test_last_attempt_expiry_terminalizes_without_poison_loop(tmp_path):
    now=[NOW]
    store=SQLiteMindStore(tmp_path/"expiry.sqlite3",clock=lambda:now[0])
    store.initialize()
    store.append(scope(),event())
    store.dispatch_outbox(scope(),max_attempts=1)
    job=store.claim(scope(),"worker",lease_seconds=1)
    now[0]+=timedelta(seconds=2)
    assert store.claim(scope(),"replacement") is None
    assert store.get_job(scope(),job.job_id).status is JobStatus.FAILED
    assert store.status(scope())["last_error_code"]=="lease_expired"


def test_clock_sampled_after_sqlite_writer_lock(tmp_path):
    clock=[NOW]
    path=tmp_path/"clock.sqlite3"
    store=SQLiteMindStore(path,clock=lambda:clock[0],busy_timeout_ms=5000)
    store.initialize()
    store.append(scope(),event())
    store.dispatch_outbox(scope())
    job=store.claim(scope(),"worker-a",lease_seconds=1)
    entered=threading.Event()
    original_connect=store._connect
    def signal_connect(mode):
        connection=original_connect(mode)
        if mode=="rw":
            entered.set()
        return connection
    store._connect=signal_connect
    with closing(sqlite3.connect(path,timeout=5,isolation_level=None)) as blocker:
        blocker.execute("BEGIN IMMEDIATE")
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(store.renew,scope(),job.job_id,"worker-a",
                    job.fencing_token,lease_seconds=10)
                assert entered.wait(timeout=2)
                clock[0]+=timedelta(seconds=2)
                blocker.execute("COMMIT")
                with pytest.raises(LostLeaseError):
                    future.result(timeout=5)
        finally:
            if blocker.in_transaction:
                blocker.execute("ROLLBACK")
    replacement=store.claim(scope(),"worker-b",lease_seconds=3)
    assert replacement and replacement.lease_expires_at==clock[0]+timedelta(seconds=3)