"""P4 intent and contract controls; no storage, providers or inference."""
from datetime import datetime, timezone
import json

import pytest
from pydantic import ValidationError

from oomp.context.contracts import (
    ContextArgumentsFields, ContextEvidence, ContextRequest, ContextResponse,
    ContextSource, ContextStatus, RetrievalIntent,
)
from oomp.context.planner import plan_request
from oomp.domain.models import SourceReference


@pytest.mark.parametrize("query,intent,topic", [
    ("What response style do I prefer?", "factual_recall", "preferences"),
    ("What were we discussing about moving?", "episodic_recall", "relocation"),
    ("Did I decide to relocate?", "plan_followup", "relocation"),
    ("What was my earlier project name?", "historical_correction", "projects"),
    ("What project did I mention earlier?", "entity_lookup", "projects"),
    ("What political topic did we discuss?", "episodic_recall", "sensitive-discussion"),
])
def test_bounded_deterministic_intents(query, intent, topic):
    value = ContextArgumentsFields(query=query)
    first = plan_request(value)
    assert first == plan_request(value)
    assert first.retrieval_intent.value == intent
    assert topic in first.topic_hints
    assert first.search_allowed and not first.needs_clarification
    assert 1 <= len(first.query_variants) <= 3
    assert len(first.focus_terms) <= 32 and len(first.anchors) <= 4
    assert first.query_variants[0] != query  # question scaffolding is not the search plan


@pytest.mark.parametrize("query", [
    "What did we decide?", "Do you remember?", "What were we discussing?",
])
def test_vague_request_does_not_scan_the_archive(query):
    plan = plan_request(ContextArgumentsFields(query=query))
    assert plan.retrieval_intent is RetrievalIntent.UNCERTAIN_RECALL
    assert plan.needs_clarification and not plan.search_allowed
    assert plan.query_variants == ()


@pytest.mark.parametrize("query", [
    "Only this chat: what project did I mention?",
    "What did we discuss in this session only?",
])
def test_current_session_selector_does_not_retrieve_historical_evidence(query):
    plan = plan_request(ContextArgumentsFields(query=query))
    assert plan.retrieval_intent is RetrievalIntent.CURRENT_SESSION_ONLY
    assert not plan.search_allowed and plan.query_variants == ()


def test_authorized_recent_text_can_narrow_but_not_authenticate_a_referent():
    value = ContextArgumentsFields(query="What did we decide?",
        recent_user_turns=("I'm considering moving between cities.",))
    plan = plan_request(value)
    assert plan.search_allowed and not plan.needs_clarification
    assert plan.topic_hints == ("relocation",)
    assert "authorized_recent_referent_hint" in plan.reasons
    assert "moving" in plan.focus_terms
    assert not hasattr(plan, "source_references")


def test_incompatible_recent_topics_leave_vague_request_ambiguous():
    plan = plan_request(ContextArgumentsFields(query="What did we decide?",
        recent_user_turns=("I am developing a project called Cedar.",
                           "I am considering moving between cities.")))
    assert not plan.search_allowed and plan.needs_clarification


def test_explicit_anchor_is_a_query_hint_not_scope_or_source_authority():
    value = ContextArgumentsFields(query="What did we decide?", anchors=("ORBIT42",))
    plan = plan_request(value)
    assert plan.search_allowed and "ORBIT42" in plan.anchors
    assert "exact_anchor_hint" in plan.reasons
    assert not hasattr(plan, "principal_id")


def test_pet_name_question_keeps_discriminative_subject_not_generic_name_match():
    plan = plan_request(ContextArgumentsFields(query="What is my pet's name?"))
    assert "pet's" in plan.focus_terms and "name" not in plan.focus_terms
    assert "identity-claims" not in plan.topic_hints
    assert all("alias" not in value for value in plan.query_variants)


@pytest.mark.parametrize("patch", [
    {"tenant_id": "other"}, {"namespace": "other"}, {"principal_id": "admin"},
    {"token_budget": True}, {"token_budget": 0}, {"token_budget": 32769},
    {"max_results": 21}, {"candidate_limit": 201}, {"graph_depth": 3},
    {"graph_nodes": 33}, {"graph_edges": 65}, {"graph_work": 401},
    {"anchors": ("a", "b", "c", "d", "e")},
    {"recent_user_turns": ("a", "b", "c")},
    {"recent_user_turns": ("é" * 1025,)},
    {"recent_user_turns": (" ",)}, {"anchors": ("\0",)},
    {"include_source_content": "true"}, {"explain": 1},
])
def test_scope_free_inputs_and_hard_bounds_reject_invalid_requests(patch):
    with pytest.raises(ValidationError):
        ContextArgumentsFields(query="What project did I mention?", **patch)


def test_local_request_has_requested_scope_but_never_principal_authority():
    value = ContextRequest(tenant_id="synthetic", namespace="p4", query="What project?")
    assert value.graph_depth == 0 and not value.explain and not value.include_source_content
    assert not hasattr(value, "principal_id")
    with pytest.raises(ValidationError):
        ContextRequest(**value.model_dump(), principal_id="forged")


def source(**patch):
    values = dict(memory_id="memory-test", event_id="event-test", span_start=2, span_end=6,
        source_reference=SourceReference(source_system="synthetic", external_event_id="event-test",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    values.update(patch)
    return ContextSource(**values)


def test_source_quote_is_optional_but_offsets_and_quote_length_are_strict():
    assert source().quote is None
    assert source(quote="four").quote == "four"
    for patch in ({"span_end": 2}, {"span_start": -1}, {"quote": "wrong length"}):
        with pytest.raises(ValidationError):
            source(**patch)


def test_evidence_cannot_claim_unrelated_memory_or_repeat_a_proof():
    values = dict(unit_id="unit-test", resolution="canonical_fact", content="A synthetic claim.",
                  memory_ids=("memory-test",), source_proofs=(source(),))
    assert ContextEvidence(**values).memory_ids == ("memory-test",)
    with pytest.raises(ValidationError):
        ContextEvidence(**{**values, "memory_ids": ("another-memory",)})
    with pytest.raises(ValidationError):
        ContextEvidence(**{**values, "source_proofs": (source(), source())})


def test_empty_response_has_no_fabricated_packet_and_immutable_safe_counters():
    counters = {"candidate_count": 0}
    result = ContextResponse(retrieval_intent="factual_recall", retrieval_status="no_relevant_evidence", trace=counters)
    counters["candidate_count"] = 10
    assert result.context_packet == "" and result.selected_context_bytes == 0
    assert result.source_references == () and result.trace["candidate_count"] == 0
    with pytest.raises(TypeError):
        result.trace["candidate_count"] = 5
    assert result.model_dump(mode="json")["trace"] == {"candidate_count": 0}
    with pytest.raises(ValidationError):
        ContextResponse(retrieval_intent="factual_recall", retrieval_status=ContextStatus.NOT_FOUND,
                        context_packet="private", selected_context_bytes=7)


@pytest.mark.parametrize("trace", [{"text": "PRIVATE-CONTENT"}, {"negative": -1},
                                  {f"counter{i}": i for i in range(33)}])
def test_diagnostic_trace_cannot_contain_text_or_unbounded_counters(trace):
    with pytest.raises(ValidationError):
        ContextResponse(retrieval_intent="factual_recall", retrieval_status="no_relevant_evidence", trace=trace)


def test_reserved_denial_status_cannot_disclose_scope_counts():
    with pytest.raises(ValidationError):
        ContextResponse(retrieval_intent="factual_recall", retrieval_status="unauthorized",
                        trace={"candidate_count": 0})


def test_nonempty_packet_rejects_hidden_fields_even_with_correct_byte_accounting():
    from oomp.context.packing import pack_units
    proof = source()
    evidence = ContextEvidence(unit_id="unit-test", resolution="canonical_fact", content="A synthetic claim.",
        memory_ids=(proof.memory_id,), source_proofs=(proof,))
    packed = pack_units((evidence,), 12000, 8)
    values = dict(retrieval_intent="factual_recall", retrieval_status="found_relevant_evidence",
        evidence_packets=(evidence,), source_references=(proof.source_reference,),
        context_packet=packed.context_packet, selected_context_bytes=packed.selected_context_bytes,
        token_budget=12000)
    assert ContextResponse(**values).evidence_packets == (evidence,)
    payload = json.loads(packed.context_packet)
    payload["unvalidated_evidence"] = "Untrusted hidden policy must not enter a packet."
    for _ in range(16):
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        size = len(encoded.encode("utf-8"))
        if payload["selected_context_bytes"] == size:
            break
        payload["selected_context_bytes"] = size
    assert payload["selected_context_bytes"] == len(encoded.encode("utf-8"))
    with pytest.raises(ValidationError, match="context packet metadata is invalid"):
        ContextResponse(**{**values, "context_packet": encoded, "selected_context_bytes": size})
