"""Privileged Stage 6 erasure and nonresurrection tests."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone

import pytest

from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
from oomp.ingestion.pipeline import ExtractionPipeline
from oomp.storage.errors import StorageUnavailableError, ScopeMismatchError
from oomp.storage.memory_store import SQLiteMemoryStore
from oomp.storage.mind_store import SQLiteMindStore
from oomp.storage.privacy_store import (
    ErasureBlockedError, SQLitePrivacyStore, StaleErasurePlanError,
)
from oomp.storage.retrieval_store import SQLiteRetrievalStore
from oomp.storage.topic_store import SQLiteTopicStore


NOW=datetime(2026,1,1,tzinfo=timezone.utc)


def scope(tenant="tenant",namespace="personal"):
    return AuthorizedScope(tenant_id=tenant,namespace=namespace,principal_id="privacy-admin")


def source(identity, *, tenant="tenant",namespace="personal",text="I prefer tea."):
    return MemoryEvent(
        event_id=identity,tenant_id=tenant,namespace=namespace,
        event_type="user_message",source_type="user",content=text,
        source_reference=SourceReference(
            source_system="synthetic",external_event_id=identity,timestamp=NOW,
        ),occurred_at=NOW,ingested_at=NOW,idempotency_key="key-"+identity,
    )


def setup(path, identities=("e1",), tenant="tenant", namespace="personal"):
    store=SQLitePrivacyStore(path)
    store.initialize()
    authorized=scope(tenant,namespace)
    result=[]
    for identity in identities:
        store.append(authorized,source(identity,tenant=tenant,namespace=namespace))
        result.append(ExtractionPipeline(path).process_event(authorized,identity))
    return store,result


def test_plan_nonmutating_confirm_explicit_and_retrieval_empty(tmp_path):
    path=tmp_path/"privacy.sqlite3"
    store,results=setup(path)
    memory_id=results[0].memory_ids[0]
    store.append(scope(),source("protected",text="Ordinary retained evidence."))
    plan=store.erase_plan(scope(),"e1")
    assert plan.delete_memory_ids==(memory_id,)
    assert plan.affected_fts_docs==1 and plan.blocked_reason is None
    assert store.get(scope(),"e1") is not None
    with pytest.raises(ValueError):
        store.erase_confirm(scope(),"e1",plan.plan_digest)
    assert store.get(scope(),"e1") is not None
    result=store.erase_confirm(scope(),"e1",plan.plan_digest,confirm=True)
    assert result.deleted_memories==1
    assert store.get(scope(),"e1") is None
    assert SQLiteMemoryStore(path).get(scope(),memory_id) is None
    with SQLiteRetrievalStore(path).read_snapshot(scope()) as read:
        assert read.lexical("tea")==()
    with closing(sqlite3.connect(path)) as c,c:
        assert c.execute("PRAGMA foreign_key_check").fetchall()==[]
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("DELETE FROM events")
    with pytest.raises(StorageUnavailableError):
        store.append(scope(),source("e1"))


def test_shared_canonical_proof_survives_and_summary_invalidated(tmp_path):
    path=tmp_path/"shared.sqlite3"
    store,results=setup(path,("e1","e2"))
    assert results[0].memory_ids==results[1].memory_ids
    memory_id=results[0].memory_ids[0]
    topic=SQLiteTopicStore(path)
    topic.create_topic(scope(),"topic-tea","Tea")
    topic.assign_memory(scope(),"topic-tea",memory_id)
    from oomp.storage.mind_projection_store import SQLiteMindProjectionStore
    projections=SQLiteMindProjectionStore(path)
    summary,created=projections.consolidate_topic(scope(),"topic-tea")
    assert created and summary and set(summary.source_event_ids)=={"e1","e2"}
    plan=store.erase_plan(scope(),"e1")
    assert plan.delete_memory_ids==() and plan.detach_memory_ids==(memory_id,)
    assert plan.delete_summary_revision_ids==(summary.revision_id,)
    assert plan.blocked_reason is None
    result=store.erase_confirm(scope(),"e1",plan.plan_digest,confirm=True)
    assert result.detached_memories==1 and result.deleted_summary_revisions==1
    survivor=SQLiteMemoryStore(path).get(scope(),memory_id)
    assert survivor and survivor.source_event_ids==("e2",)
    assert projections.get_summary(scope(),"topic-tea") is None
    revised,created=projections.consolidate_topic(scope(),"topic-tea")
    assert created and revised and revised.source_event_ids==("e2",)
    with SQLiteRetrievalStore(path).read_snapshot(scope()) as read:
        assert read.lexical("tea")[0].memory_id==memory_id


def test_stale_plan_rejected_after_new_shared_evidence(tmp_path):
    path=tmp_path/"stale.sqlite3"
    store,results=setup(path)
    old=store.erase_plan(scope(),"e1")
    store.append(scope(),source("e2"))
    ExtractionPipeline(path).process_event(scope(),"e2")
    with pytest.raises(StaleErasurePlanError):
        store.erase_confirm(scope(),"e1",old.plan_digest,confirm=True)
    assert store.get(scope(),"e1") is not None


def test_erasure_cancels_queued_job_and_tombstone_blocks_resurrection(tmp_path):
    path=tmp_path/"jobs.sqlite3"
    store,_=setup(path)
    assert store.dispatch_outbox(scope())==1
    job=store.list_jobs(scope())[0]
    plan=store.erase_plan(scope(),"e1")
    assert plan.cancel_job_ids==(job.job_id,)
    store.erase_confirm(scope(),"e1",plan.plan_digest,confirm=True)
    assert store.get_job(scope(),job.job_id).status.value=="cancelled"
    assert store.claim(scope(),"worker") is None
    assert store.backfill_events(scope())==0
    with pytest.raises(StorageUnavailableError):
        store.append(scope(),source("e1"))
    with pytest.raises(StorageUnavailableError):
        store.append(scope(),source("other",text="I prefer tea.").model_copy(
            update={"idempotency_key":"key-e1"},
        ))


def test_other_scope_intact_and_wrong_scope_plan_rejected(tmp_path):
    path=tmp_path/"isolated.sqlite3"
    store,_=setup(path)
    other=scope("other")
    store.append(other,source("e1",tenant="other"))
    with pytest.raises(ScopeMismatchError):
        store.erase_plan(other,"missing")
    plan=store.erase_plan(scope(),"e1")
    store.erase_confirm(scope(),"e1",plan.plan_digest,confirm=True)
    assert store.get(other,"e1") is not None


def test_failure_after_trigger_drop_rolls_back_everything(tmp_path,monkeypatch):
    path=tmp_path/"rollback.sqlite3"
    store,_=setup(path)
    plan=store.erase_plan(scope(),"e1")
    import oomp.storage.privacy_store as privacy
    monkeypatch.setattr(privacy,"verify_v6",lambda _:False)
    with pytest.raises(ErasureBlockedError):
        store.erase_confirm(scope(),"e1",plan.plan_digest,confirm=True)
    assert store.get(scope(),"e1") is not None
    with closing(sqlite3.connect(path)) as c,c:
        assert c.execute("SELECT name FROM sqlite_master WHERE name='events_no_delete'").fetchone()
        assert c.execute("SELECT COUNT(*) FROM mind_erased_events").fetchone()[0]==0
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("DELETE FROM events")