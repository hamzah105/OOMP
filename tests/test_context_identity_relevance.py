"""Identity relevance follows proved claims rather than generic name keywords."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import sqlite3

from oomp.context.contracts import ContextRequest
from oomp.context.engine import ContextEngine
from oomp.domain.memories import SourceSpan
from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
from oomp.mind.worker import MindWorker
from oomp.objects.service import ObjectMap
from oomp.storage.memory_store import SQLiteMemoryStore
from oomp.storage.sqlite import SQLiteEventStore
from oomp.understanding.contracts import ExtractionConfiguration
from oomp.understanding.rules import classify, proposal_for
from oomp.understanding.storage import UnderstandingStore
from oomp.understanding.validator import CandidateValidator


OWNER = AuthorizedScope(tenant_id="identity-relevance", namespace="synthetic", principal_id="owner")
NOW = datetime(2026, 2, 1, tzinfo=timezone.utc)
ALIAS = ("alias", "My alias is Harbor Finch.")
PROJECT = ("project", "I am developing a project called Lantern.")
RENAME = ("rename", "My project Lantern is now called Drift.")


def build(path, turns):
    source = SQLiteEventStore(path)
    source.initialize()
    events = {}
    for index, (identifier, content) in enumerate(turns):
        when = NOW + timedelta(minutes=index)
        event = MemoryEvent(event_id=identifier, tenant_id=OWNER.tenant_id, namespace=OWNER.namespace,
            event_type="user_message", source_type="user", content=content,
            occurred_at=when, ingested_at=when, metadata={"ingested_by": OWNER.principal_id},
            source_reference=SourceReference(source_system="synthetic-identity-relevance",
                external_event_id=identifier, timestamp=when, session_id="identity-session",
                turn_id=identifier))
        source.append(OWNER, event)
        events[identifier] = event
    worker = MindWorker(path, OWNER, extraction_configuration=ExtractionConfiguration(mode="rules"))
    run = worker.run_once(max_jobs=100)
    assert run.completed >= len(events) and not any((run.failed, run.retried, run.lost_lease))
    assert worker.handlers.understanding.provider is None
    assert not ObjectMap(path).build(OWNER, limit=100).incomplete
    return events


def request(query="What alias did I introduce?"):
    return ContextRequest(tenant_id=OWNER.tenant_id, namespace=OWNER.namespace, query=query,
                          token_budget=32768, max_results=20)


def sources(path, result, events):
    identifiers = set()
    with closing(sqlite3.connect(path)) as connection:
        for unit in result.evidence_packets:
            for proof in unit.source_proofs:
                event = events[proof.event_id]
                row = connection.execute("SELECT source_span_json FROM memory_sources "
                    "WHERE tenant_id=? AND namespace=? AND memory_id=? AND event_id=?",
                    (OWNER.tenant_id, OWNER.namespace, proof.memory_id, proof.event_id)).fetchone()
                assert row is not None
                span = json.loads(row[0])
                assert (proof.span_start, proof.span_end) == (span["start"], span["end"])
                assert span["quote"] == event.content[proof.span_start:proof.span_end]
                assert proof.source_reference == event.source_reference and proof.quote is None
                identifiers.add(proof.event_id)
    return identifiers


def test_alias_query_excludes_source_grounded_project_names_and_rename(tmp_path):
    path = tmp_path / "alias.sqlite3"
    events = build(path, (ALIAS, PROJECT, RENAME))
    result = ContextEngine(path).retrieve(OWNER, request())
    assert sources(path, result, events) == {"alias"}
    assert "Harbor Finch" in result.context_packet
    assert "Lantern" not in result.context_packet and "Drift" not in result.context_packet


def test_project_names_alone_cannot_answer_an_alias_query(tmp_path):
    path = tmp_path / "project-only.sqlite3"
    events = build(path, (PROJECT, RENAME))
    result = ContextEngine(path).retrieve(OWNER, request())
    assert sources(path, result, events) == set()
    assert not result.evidence_packets and not result.context_packet
    assert result.retrieval_status.value in {"no_relevant_evidence", "candidate_uncertain"}


def test_independently_validated_literal_p21_alias_remains_retrievable_without_provider(tmp_path, monkeypatch):
    def forbidden_provider(*args, **kwargs):
        raise AssertionError("offline_identity_test_must_not_construct_provider")

    monkeypatch.setattr("oomp.understanding.providers.OllamaExtractor", forbidden_provider)
    path = tmp_path / "literal-refinement.sqlite3"
    events = build(path, (("literal-alias", "My friends call me Harbor Finch."), PROJECT))
    event = events["literal-alias"]
    span = SourceSpan(start=0, end=len(event.content), quote=event.content)
    baseline = classify(event, span)
    assert (baseline["predicate"], baseline["memory_category"]) == ("stated", "episodic")
    # This is a pure validated fixture proposal, with no model construction,
    # request or generated output. It exercises an existing P2.1 literal form.
    config = ExtractionConfiguration(mode="local-llm", model="offline-literal-fixture")
    proposed = proposal_for(OWNER, event, span, provider="ollama", model=config.model,
                           hints={"predicate": "alias", "memory_category": "profile"})
    assert CandidateValidator(config).validate(OWNER, event, (proposed,)) == (proposed,)
    processing, _ = UnderstandingStore(path).commit(OWNER, event, (proposed,), config)
    assert processing.memories_created == 1
    aliases = [memory for memory in SQLiteMemoryStore(path).list_memories(OWNER).memories
               if memory.metadata.get("predicate") == "alias"]
    assert len(aliases) == 1 and aliases[0].metadata["category"] == "profile"
    result = ContextEngine(path).retrieve(OWNER, request())
    assert sources(path, result, events) == {"literal-alias"}
    assert any(aliases[0].memory_id in unit.memory_ids for unit in result.evidence_packets)


def test_explicit_mixed_alias_and_project_query_keeps_both_claim_types(tmp_path):
    path = tmp_path / "mixed.sqlite3"
    events = build(path, (ALIAS, PROJECT, RENAME))
    result = ContextEngine(path).retrieve(OWNER, request("What alias and project names did I introduce?"))
    assert sources(path, result, events) == {"alias", "project", "rename"}


def test_project_recall_and_project_name_history_keep_their_source_proofs(tmp_path):
    path = tmp_path / "history.sqlite3"
    events = build(path, (ALIAS, PROJECT, RENAME))
    engine = ContextEngine(path)
    for query in ("What project did I mention?", "What was my earlier project name?"):
        result = engine.retrieve(OWNER, request(query))
        assert sources(path, result, events) == {"project", "rename"}
    assert result.retrieval_intent.value == "historical_correction"
