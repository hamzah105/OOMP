"""Independent claim/label/conflict grounding over disposable real source stores."""
from datetime import datetime, timedelta, timezone

import pytest

from oomp.context.contracts import ContextEvidence, ContextRequest
from oomp.context.engine import ContextEngine
from oomp.context.packing import pack_units
from oomp.domain.memories import SourceSpan
from oomp.domain.models import AuthorizedScope, MemoryEvent, MemoryNode, SourceReference
from oomp.graph import GraphService
from oomp.objects.service import ObjectMap
from oomp.storage.memory_store import SQLiteMemoryStore
from oomp.storage.sqlite import SQLiteEventStore
from oomp.understanding.engine import UnderstandingEngine

OWNER = AuthorizedScope(tenant_id="p4-grounding", namespace="synthetic", principal_id="owner")
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def original(path, identifier, content, *, minute=0):
    when = NOW + timedelta(minutes=minute)
    event = MemoryEvent(event_id="event-"+identifier, tenant_id=OWNER.tenant_id, namespace=OWNER.namespace,
        event_type="user_message", source_type="user", content=content, occurred_at=when, ingested_at=when,
        metadata={"ingested_by": OWNER.principal_id}, source_reference=SourceReference(
            source_system="synthetic-grounding", external_event_id="interaction-"+identifier,
            timestamp=when, session_id="grounding-session", turn_id=identifier))
    SQLiteEventStore(path).append(OWNER, event)
    return event


def manual(path, event, identifier, *, content=None, span=None, validity=False):
    """A valid quote/link is deliberately insufficient to prove a paraphrase."""
    span = span or SourceSpan(start=0, end=len(event.content), quote=event.content)
    memory = MemoryNode(memory_id="claim-"+identifier, tenant_id=OWNER.tenant_id, namespace=OWNER.namespace,
        memory_type="semantic", canonical_key="manual:"+identifier,
        canonical_content=event.content if content is None else content,
        source_event_ids=(event.event_id,), provenance=(event.source_reference,),
        created_at=event.occurred_at, updated_at=event.occurred_at,
        valid_from=NOW if validity else None, valid_until=NOW+timedelta(days=365) if validity else None,
        metadata={"attribution": "user", "verified": False})
    store = SQLiteMemoryStore(path)
    with store._transaction() as connection:
        result, _, _ = store._upsert_in_transaction(connection, OWNER, memory,
            source_spans={event.event_id: span}, extraction_method="synthetic-manual")
    return result


def request(query, **kwargs):
    return ContextRequest(tenant_id=OWNER.tenant_id, namespace=OWNER.namespace, query=query,
                          token_budget=kwargs.pop("token_budget", 32768), **kwargs)


@pytest.fixture
def path(tmp_path):
    result = tmp_path / "grounding.sqlite3"
    SQLiteEventStore(result).initialize()
    return result


def test_valid_source_quote_does_not_prove_an_invented_canonical_claim(path):
    event = original(path, "style", "I prefer concise technical explanations.")
    forged = manual(path, event, "invented", content=
        "User prefers concise technical explanations and owns a pet called FORGED-EMBER.")
    assert SQLiteMemoryStore(path).get(OWNER, forged.memory_id) is not None
    result = ContextEngine(path).retrieve(OWNER, request("What response style do I prefer?"))
    assert not result.evidence_packets
    assert "FORGED-EMBER" not in result.model_dump_json()


def test_complete_exact_attributed_source_can_still_be_returned(path):
    event = original(path, "exact-style", "I prefer concise technical explanations.")
    memory = manual(path, event, "exact")
    result = ContextEngine(path).retrieve(OWNER, request("What response style do I prefer?"))
    assert any(memory.memory_id in unit.memory_ids for unit in result.evidence_packets)
    assert {p.event_id for u in result.evidence_packets for p in u.source_proofs} == {event.event_id}


def test_arbitrary_exact_substring_cannot_remove_a_source_negation(path):
    event = original(path, "negated", "I do not prefer lengthy explanations.")
    quote = "prefer lengthy explanations."
    start = event.content.index(quote)
    manual(path, event, "cropped-negation", content=quote,
        span=SourceSpan(start=start, end=start+len(quote), quote=quote))
    result = ContextEngine(path).retrieve(OWNER, request("What response style do I prefer?"))
    assert not result.evidence_packets
    assert result.retrieval_status.value != "found_relevant_evidence"


def test_renamed_object_snapshot_cannot_publish_aliases_without_all_admitted_proofs(path):
    first = original(path, "project", "I am developing a project called Cedar.")
    renamed = original(path, "renamed", "My project Cedar is now called Aspen.", minute=1)
    acquisition = UnderstandingEngine(path)
    acquisition.process_event(OWNER, first.event_id)
    acquisition.process_event(OWNER, renamed.event_id)
    objects = ObjectMap(path)
    objects.build(OWNER, limit=100)
    project, = objects.list_objects(OWNER, object_type="project").objects
    assert project.canonical_label == "Aspen" and "Cedar" in project.aliases
    assert {p.event_id for p in project.source_proofs} == {first.event_id, renamed.event_id}
    result = ContextEngine(path).retrieve(OWNER, request("What were we discussing about Aspen?"))
    assert result.evidence_packets
    for unit in result.evidence_packets:
        if unit.resolution.value == "object_snapshot" and project.object_id in unit.object_ids:
            assert {p.event_id for p in unit.source_proofs} == {first.event_id, renamed.event_id}
    assert not any(unit.resolution.value == "object_snapshot" and project.object_id in unit.object_ids
                   for unit in result.evidence_packets)


def chain(path, *, copies=False):
    events, memories = [], []
    for index, (key, value) in enumerate((("a", 8), ("b", 16), ("c", 32))):
        event = original(path, key, f"My test computer has {value} GB RAM.", minute=index)
        events.append(event)
        memories.append(manual(path, event, key, validity=True))
        if copies:
            UnderstandingEngine(path).process_event(OWNER, event.event_id)
    service = GraphService(path)
    for first, second in ((0, 1), (1, 2)):
        proposal = service.propose_conflict(OWNER, memories[first].memory_id, memories[second].memory_id).proposal
        assert proposal is not None and proposal.relationship_type.value == "CONTRADICTS"
        service.resolve(OWNER, proposal, confirm=True)
    if copies:
        ObjectMap(path).build(OWNER, limit=100)
    return events, memories


def test_direct_conflict_component_includes_third_claim_beyond_initial_candidate(path):
    events, _ = chain(path)
    result = ContextEngine(path).retrieve(OWNER, request("What did my test computer report for RAM?",
        candidate_limit=1, valid_at=NOW+timedelta(days=1)))
    groups = [unit for unit in result.evidence_packets if unit.temporal_status == "contradicted"]
    assert len(groups) == 1
    assert {proof.event_id for proof in groups[0].source_proofs} == {event.event_id for event in events}
    assert result.retrieval_status.value == "candidate_uncertain"


def test_tiny_budget_cannot_bypass_conflict_bundle_through_episode_or_leaf_copy(path):
    events, memories = chain(path, copies=True)
    engine = ContextEngine(path)
    query = "What did my test computer report for RAM?"
    wide = engine.retrieve(OWNER, request(query, valid_at=NOW+timedelta(days=1)))
    group, = [unit for unit in wide.evidence_packets if unit.temporal_status == "contradicted"]
    assert {proof.event_id for proof in group.source_proofs} == {event.event_id for event in events}
    first = memories[0]
    proof, = [p for p in group.source_proofs if p.memory_id == first.memory_id]
    probe = ContextEvidence(unit_id="leaf-capacity-probe", resolution="canonical_fact", content=first.canonical_content,
        memory_ids=(first.memory_id,), source_proofs=(proof,), assertion_kinds=("explicit",), temporal_status="contradicted")
    budget = pack_units((probe,), 32768, 8).selected_context_bytes + 128
    assert budget < wide.selected_context_bytes
    assert pack_units((probe,), budget, 8).evidence_packets
    narrow = engine.retrieve(OWNER, request(query, valid_at=NOW+timedelta(days=1), token_budget=budget))
    assert narrow.evidence_packets == () and narrow.context_packet == ""
    assert narrow.retrieval_status.value in {"budget_excluded", "candidate_uncertain"}
