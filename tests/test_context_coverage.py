"""Incomplete bounded routes must not claim complete archive coverage."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import sqlite3

import pytest

from oomp.context.contracts import ContextRequest
from oomp.context.engine import ContextEngine
from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
from oomp.mind.worker import MindWorker
from oomp.objects.service import ObjectMap
from oomp.storage.errors import GraphLimitError
from oomp.storage.sqlite import SQLiteEventStore
from oomp.understanding.contracts import ExtractionConfiguration


OWNER = AuthorizedScope(tenant_id="p4-coverage", namespace="synthetic", principal_id="owner")
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def engine(tmp_path):
    path = tmp_path / "coverage.sqlite3"
    store = SQLiteEventStore(path)
    store.initialize()
    store.append(OWNER, MemoryEvent(event_id="coverage-project", tenant_id=OWNER.tenant_id,
        namespace=OWNER.namespace, event_type="user_message", source_type="user",
        content="I am developing a project called Cedar.", occurred_at=NOW, ingested_at=NOW,
        metadata={"ingested_by": OWNER.principal_id}, source_reference=SourceReference(
            source_system="synthetic-coverage", external_event_id="coverage-project",
            timestamp=NOW, session_id="coverage-session", turn_id="coverage-turn")))
    worker = MindWorker(path, OWNER, extraction_configuration=ExtractionConfiguration(mode="rules"))
    run = worker.run_once(max_jobs=100)
    assert run.completed and not any((run.failed, run.retried, run.lost_lease))
    assert worker.handlers.understanding.provider is None
    assert not ObjectMap(path).build(OWNER, limit=100).incomplete
    return ContextEngine(path)


def request():
    return ContextRequest(tenant_id=OWNER.tenant_id, namespace=OWNER.namespace,
        query="What project were we discussing?", token_budget=12000)


@pytest.mark.parametrize("counter", ["object_candidate_truncated", "object_invalid"])
def test_incomplete_object_route_marks_otherwise_valid_result_partial(engine, monkeypatch, counter):
    original = engine._object_candidates

    def incomplete(session, objects, scope, plan, temporal, incoming, trace, check):
        result = original(session, objects, scope, plan, temporal, incoming, trace, check)
        trace[counter] = 1
        return result

    monkeypatch.setattr(engine, "_object_candidates", incomplete)
    result = engine.retrieve(OWNER, request())
    assert result.evidence_packets
    assert result.coverage == "partial" and result.trace[counter] == 1
    assert "object_candidate_coverage_incomplete" in result.reasons


def test_legacy_graph_truncated_boolean_is_preserved_as_partial_counter(engine, monkeypatch):
    original = engine.base._retrieve

    def truncated(*args, **kwargs):
        result = original(*args, **kwargs)
        return result.model_copy(update={"retrieval_trace": result.retrieval_trace.model_copy(
            update={"graph_truncated": True})})

    monkeypatch.setattr(engine.base, "_retrieve", truncated)
    result = engine.retrieve(OWNER, request())
    assert result.evidence_packets and result.coverage == "partial"
    assert result.trace["canonical_graph_truncated"] == 1
    assert "canonical_graph_expansion_incomplete" in result.reasons


def test_graph_limit_reports_incomplete_index_without_partial_evidence(engine, monkeypatch):
    def limited(*args, **kwargs):
        raise GraphLimitError("synthetic_graph_limit")

    monkeypatch.setattr(engine.base, "_retrieve", limited)
    result = engine.retrieve(OWNER, request())
    assert result.retrieval_status.value == "index_incomplete"
    assert result.coverage == "partial" and not result.evidence_packets
    assert "context_graph_limit" in result.reasons


def test_invalid_stored_summary_manifest_reports_partial_coverage(engine):
    before = engine.retrieve(OWNER, request())
    assert before.coverage == "complete" and not before.trace.get("summary_invalid", 0)
    with closing(sqlite3.connect(engine.path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM mind_summary_sources").fetchone()[0] > 0
        connection.execute("DELETE FROM mind_summary_sources")
        connection.commit()
    after = engine.retrieve(OWNER, request())
    assert after.coverage == "partial" and after.trace.get("summary_invalid", 0) >= 1
    assert "episode_summary_coverage_incomplete" in after.reasons
    assert all(unit.resolution.value != "episode_summary" for unit in after.evidence_packets)


def test_nine_real_episode_candidates_report_partial_summary_search(tmp_path):
    path = tmp_path / "summary-cap.sqlite3"
    source = SQLiteEventStore(path)
    source.initialize()
    events = {}
    for index in range(9):
        identifier = "sensor-source-" + str(index)
        when = NOW + timedelta(minutes=index)
        event = MemoryEvent(event_id=identifier, tenant_id=OWNER.tenant_id,
            namespace=OWNER.namespace, event_type="user_message", source_type="user",
            content="We discussed sensor calibration for instrument " + str(index) + ".",
            occurred_at=when, ingested_at=when, metadata={"ingested_by": OWNER.principal_id},
            source_reference=SourceReference(source_system="synthetic-summary-cap",
                external_event_id=identifier, timestamp=when,
                session_id="sensor-session-" + str(index), turn_id=identifier))
        source.append(OWNER, event)
        events[identifier] = event
    worker = MindWorker(path, OWNER,
        extraction_configuration=ExtractionConfiguration(mode="rules"))
    run = worker.run_once(max_jobs=100)
    assert run.completed >= 9 and not any((run.failed, run.retried, run.lost_lease))
    assert worker.handlers.understanding.provider is None
    assert not ObjectMap(path).build(OWNER, limit=100).incomplete
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM mind_summary_revisions "
            "WHERE retired_at IS NULL").fetchone()[0] == 9
        assert connection.execute("SELECT COUNT(DISTINCT topic_id) FROM topic_memberships").fetchone()[0] == 9
    incoming = ContextRequest(tenant_id=OWNER.tenant_id, namespace=OWNER.namespace,
        query="What were we discussing about sensor calibration?", token_budget=32768,
        max_results=20, candidate_limit=40)
    result = ContextEngine(path).retrieve(OWNER, incoming)
    assert result.coverage == "partial"
    assert result.trace["summary_candidate_truncated"] == 1
    assert "episode_summary_search_incomplete" in result.reasons
    assert not result.trace.get("object_candidate_truncated", 0)
    assert not result.trace.get("object_invalid", 0)
    assert not result.trace.get("summary_invalid", 0)
    assert sum(unit.resolution.value == "episode_summary" for unit in result.evidence_packets) == 8
    proofs = [proof for unit in result.evidence_packets for proof in unit.source_proofs]
    assert {proof.event_id for proof in proofs} == set(events)
    assert len(proofs) == len({(proof.event_id, proof.span_start, proof.span_end) for proof in proofs})
    with closing(sqlite3.connect(path)) as connection:
        for proof in proofs:
            event = events[proof.event_id]
            row = connection.execute("SELECT source_span_json FROM memory_sources "
                "WHERE tenant_id=? AND namespace=? AND memory_id=? AND event_id=?",
                (OWNER.tenant_id, OWNER.namespace, proof.memory_id, proof.event_id)).fetchone()
            assert row is not None
            span = json.loads(row[0])
            assert (proof.span_start, proof.span_end) == (span["start"], span["end"])
            assert span["quote"] == event.content[proof.span_start:proof.span_end] == event.content
            assert proof.source_reference == event.source_reference and proof.quote is None
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT COUNT(*) FROM mind_summary_revisions "
            "WHERE retired_at IS NULL").fetchone()[0] == 9
