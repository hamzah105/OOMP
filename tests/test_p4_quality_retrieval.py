"""Independent frozen controls for bounded, source-grounded P4 recall.

The controls were registered before the quality implementation or measurement.
All projections are made through rules-only Mind jobs over fictional events.
"""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from oomp.context.contracts import ContextRequest
from oomp.context.engine import ContextEngine, _relevant
from oomp.context.planner import bounded_query_terms, plan_request
from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
from oomp.mind.worker import MindWorker
from oomp.objects.service import ObjectMap
from oomp.retrieval.contracts import RetrievalRequest
from oomp.retrieval.engine import RetrievalEngine
from oomp.storage.memory_store import SQLiteMemoryStore
from oomp.storage.sqlite import SQLiteEventStore
from oomp.understanding.contracts import ExtractionConfiguration


CONTROL_PATH = Path(__file__).parent / "fixtures/p4_quality/v1/query-controls.json"
CONTROL_SHA256 = "ba8b915bfc24d763f8ece5fd1c2a22b7df63729d46e09ee2f416da617c7e95d1"
CONTROLS = json.loads(CONTROL_PATH.read_text(encoding="utf-8"))
OWNER = AuthorizedScope(tenant_id="p4-quality-controls", namespace="fictional", principal_id="owner")
NOW = datetime(2026, 3, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def forbid_model_provider(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("synthetic_quality_controls_must_not_construct_model_provider")

    monkeypatch.setattr("oomp.understanding.providers.OllamaExtractor", forbidden)


def build(path, sources):
    store = SQLiteEventStore(path)
    store.initialize()
    events = {}
    for index, turn in enumerate(sources):
        when = NOW + timedelta(minutes=index)
        event = MemoryEvent(event_id=turn["id"], tenant_id=OWNER.tenant_id, namespace=OWNER.namespace,
            event_type="user_message", source_type="user", content=turn["text"],
            occurred_at=when, ingested_at=when, metadata={"ingested_by": OWNER.principal_id},
            source_reference=SourceReference(source_system="synthetic-p4-quality-controls",
                external_event_id=turn["id"], timestamp=when, session_id="controls-session",
                turn_id=turn["id"]))
        store.append(OWNER, event)
        events[event.event_id] = event
    worker = MindWorker(path, OWNER, extraction_configuration=ExtractionConfiguration(mode="rules"))
    run = worker.run_once(max_jobs=100)
    assert run.completed >= len(events) and not any((run.failed, run.retried, run.lost_lease))
    assert worker.handlers.understanding.provider is None
    assert not ObjectMap(path).build(OWNER, limit=100).incomplete
    return events


def request(query, scope=OWNER, **values):
    return ContextRequest(tenant_id=scope.tenant_id, namespace=scope.namespace, query=query,
                          token_budget=32768, max_results=20, explain=True, **values)


def source_ids(path, result, events):
    identifiers = set()
    with closing(sqlite3.connect(path)) as connection:
        for packet in result.evidence_packets:
            for proof in packet.source_proofs:
                event = events[proof.event_id]
                row = connection.execute("SELECT source_span_json FROM memory_sources "
                    "WHERE tenant_id=? AND namespace=? AND memory_id=? AND event_id=?",
                    (OWNER.tenant_id, OWNER.namespace, proof.memory_id, proof.event_id)).fetchone()
                assert row is not None
                span = json.loads(row[0])
                assert 0 <= proof.span_start < proof.span_end <= len(event.content)
                assert (proof.span_start, proof.span_end) == (span["start"], span["end"])
                assert span["quote"] == event.content[proof.span_start:proof.span_end]
                assert proof.source_reference == event.source_reference
                assert proof.quote is None
                identifiers.add(proof.event_id)
    return identifiers


@pytest.mark.parametrize("query", [
    "How should you explain technical topics to me?",
    "How do you teach concepts to me?",
    "How would you present technical concepts to me?",
])
def test_explanation_style_paraphrases_admit_only_preference_sources(query):
    plan = plan_request(request(query))
    assert "preferences" in plan.topic_hints
    assert _relevant("I prefer concise technical explanations.", plan)
    assert not _relevant("I am developing a project called Cedar.", plan)
    assert len(bounded_query_terms(plan)) <= 32


@pytest.mark.parametrize("query", [
    "Explain TCP congestion control.",
    "Where should I put my technical notebook?",
    "How should a robot explain technical topics to others?",
])
def test_ordinary_technical_questions_do_not_activate_personal_explanation_recall(query):
    assert "preferences" not in plan_request(request(query)).topic_hints


def test_natural_explanation_question_returns_exact_grounded_preference(tmp_path):
    path = tmp_path/"style.sqlite3"
    events = build(path, ({"id":"style", "text":"I prefer concise technical explanations."},
                         {"id":"project", "text":"I am developing a project called Cedar."}))
    query = ContextRequest.model_validate({**request("How should you explain technical topics to me?").model_dump(),
                                           "token_budget":1200})
    result = ContextEngine(path).retrieve(OWNER, query)
    assert source_ids(path, result, events) == {"style"}


def test_independent_controls_keep_their_registered_bytes_and_expected_sources():
    assert hashlib.sha256(CONTROL_PATH.read_bytes()).hexdigest() == CONTROL_SHA256
    checksum = CONTROL_PATH.with_suffix(".sha256").read_text(encoding="ascii").split()[0]
    assert checksum == CONTROL_SHA256
    assert CONTROLS["fictional"] and CONTROLS["version"] == "p4-quality-controls.v1"
    assert len(CONTROLS["queries"]) == 16
    assert all(set(case["expected"]) <= {source["id"] for source in CONTROLS["sources"]}
               for case in CONTROLS["queries"])


@pytest.mark.parametrize("case", CONTROLS["queries"], ids=lambda case: case["id"])
def test_registered_paraphrases_and_negative_controls_have_exact_source_proofs(tmp_path, case):
    path = tmp_path / "controls.sqlite3"
    events = build(path, CONTROLS["sources"])
    result = ContextEngine(path).retrieve(OWNER, request(case["query"]))
    assert source_ids(path, result, events) == set(case["expected"]), result.model_dump_json()
    assert result.selected_context_bytes <= result.token_budget
    assert "Recap" not in result.query_plan.anchors
    if not case["expected"]:
        assert not result.context_packet and not result.evidence_packets
        assert result.retrieval_status.value in {"no_relevant_evidence", "candidate_uncertain"}


def test_balanced_expansion_preserves_all_facets_within_existing_query_limits():
    plan = plan_request(request("Recap the project, my alias, robot, reply preference and relocation correction."))
    terms = bounded_query_terms(plan)
    assert len(plan.query_variants) <= 3 and len(plan.focus_terms) <= 32
    assert len(terms) <= 32 and len(plan.anchors) <= 4
    assert not plan.anchors
    assert {"project", "alias", "robot", "replies", "relocate", "plan"} <= set(terms)
    assert set(plan.topic_hints) == {"projects", "identity-claims", "preferences", "relocation"}


def test_long_primary_query_cannot_starve_later_requested_facets():
    query = " ".join(f"detail{index}" for index in range(30)) + " project alias robot reply preference relocation"
    plan = plan_request(request(query))
    terms = set(bounded_query_terms(plan))
    assert len(terms) <= 32
    assert {"project", "alias", "robot", "replies", "relocate", "plan"} <= terms


def test_anchored_alias_contrast_keeps_project_predicate_and_source_identity(tmp_path):
    path = tmp_path / "contrast.sqlite3"
    events = build(path, CONTROLS["sources"])
    result = ContextEngine(path).retrieve(OWNER, request("Is Lantern my personal alias?"))
    assert source_ids(path, result, events) == {"project"}
    admitted = {memory_id for packet in result.evidence_packets for memory_id in packet.memory_ids}
    memories = {memory.memory_id: memory for memory in SQLiteMemoryStore(path).list_memories(OWNER).memories}
    assert admitted
    assert all(memories[identifier].metadata.get("predicate") != "alias" for identifier in admitted)
    assert "Harbor Finch" not in result.context_packet


def test_entity_anchor_does_not_match_a_longer_project_label(tmp_path):
    path = tmp_path / "anchor-boundary.sqlite3"
    events = build(path, ({"id": "project", "text": "I am developing a project called Lanternfish."},))
    result = ContextEngine(path).retrieve(OWNER, request("What project named Lantern did I introduce?"))
    assert source_ids(path, result, events) == set()


def test_conjunction_can_use_multiple_independently_grounded_owned_sources(tmp_path):
    path = tmp_path / "conjunction.sqlite3"
    events = build(path, (
        {"id": "pet", "text": "My pet cat is called Bramble."},
        {"id": "move", "text": "I decided not to move to Stonehaven. I still live in Westmere."},
    ))
    result = ContextEngine(path).retrieve(OWNER, request("Is my pet Bramble and did I move to Stonehaven?"))
    assert source_ids(path, result, events) == {"pet", "move"}
    assert "conjunctive_query_unanswered" not in result.reasons


@pytest.mark.parametrize("pet_text,move_text,query", [
    ("My pet cat is called Clover and lives in Stonehaven.",
     "I decided not to move to Stonehaven.",
     "Is my pet Bramble and did I move to Stonehaven?"),
    ("My pet cat is called Bramble.",
     "I may move to Stonehaven with Bramble next winter.",
     "Is my pet Bramble and did I move to Eastport?"),
])
def test_conjunct_entity_cannot_be_satisfied_by_another_clauses_anchor(tmp_path, pet_text, move_text, query):
    path = tmp_path / "conjunct-anchor.sqlite3"
    events = build(path, ({"id":"pet", "text":pet_text}, {"id":"move", "text":move_text}))
    result = ContextEngine(path).retrieve(OWNER, request(query))
    assert source_ids(path, result, events) == set()
    assert not result.context_packet
    assert "conjunctive_query_unanswered" in result.reasons


def test_missing_conjunct_cannot_be_filled_by_another_principals_projection(tmp_path):
    path = tmp_path / "foreign.sqlite3"
    events = build(path, (
        {"id": "move", "text": "I decided not to move to Stonehaven. I still live in Westmere."},
    ))
    foreign = OWNER.model_copy(update={"principal_id": "foreign-owner"})
    when = NOW + timedelta(days=1)
    event = MemoryEvent(event_id="foreign-pet", tenant_id=OWNER.tenant_id, namespace=OWNER.namespace,
        event_type="user_message", source_type="user", content="My pet cat is called Bramble.",
        occurred_at=when, ingested_at=when, metadata={"ingested_by": foreign.principal_id},
        source_reference=SourceReference(source_system="synthetic-p4-quality-controls",
            external_event_id="foreign-pet", timestamp=when, session_id="foreign-session", turn_id="foreign-pet"))
    SQLiteEventStore(path).append(foreign, event)
    worker = MindWorker(path, foreign, extraction_configuration=ExtractionConfiguration(mode="rules"))
    run = worker.run_once(max_jobs=100)
    assert not any((run.failed, run.retried, run.lost_lease))
    assert not ObjectMap(path).build(foreign, limit=100).incomplete
    result = ContextEngine(path).retrieve(OWNER, request("Is my pet Bramble and did I move to Stonehaven?"))
    assert source_ids(path, result, events) == set()
    assert "conjunctive_query_unanswered" in result.reasons
    assert "foreign-pet" not in result.context_packet


def test_context_planning_does_not_change_legacy_retrieval_or_persisted_memories(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    events = build(path, CONTROLS["sources"])
    legacy = RetrievalEngine(path)
    query = RetrievalRequest(tenant_id=OWNER.tenant_id, namespace=OWNER.namespace,
                             query="project Lantern", token_budget=32768, max_results=20)
    before = legacy.retrieve(OWNER, query)
    memories_before = SQLiteMemoryStore(path).list_memories(OWNER)
    result = ContextEngine(path).retrieve(OWNER, request("Is Lantern my personal alias?"))
    assert source_ids(path, result, events) == {"project"}
    after = legacy.retrieve(OWNER, query)
    assert after.memories == before.memories
    assert after.source_references == before.source_references
    assert SQLiteMemoryStore(path).list_memories(OWNER) == memories_before


def test_candidate_support_cannot_establish_a_move_or_admit_unrequested_place_lists():
    candidates = "Pineport and Stonehaven are candidates."
    completed = plan_request(request("Did I move to Stonehaven?"))
    unqualified = plan_request(request("What were we discussing about moving?"))
    requested = plan_request(request("What were we discussing about moving candidates?"))
    assert not _relevant(candidates, completed)
    assert not _relevant(candidates, unqualified)
    assert not _relevant("Pineport and Stonehaven are places.", requested)
