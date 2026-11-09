"""Literal P2 corrections and exact historical proof compatibility; synthetic only."""
from datetime import datetime, timezone

import pytest

from oomp.context.validation import legacy_episode_entails_memory, source_entails_memory
from oomp.domain.memories import SourceSpan
from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
from oomp.ingestion.canonicalization import canonicalize
from oomp.ingestion.extraction import _extract_statement
from oomp.objects.contracts import ObjectMapError, ObjectType
from oomp.objects.storage import ObjectStorage
from oomp.storage.memory_store import SQLiteMemoryStore, _memory_fingerprint
from oomp.storage.sqlite import SQLiteEventStore
from oomp.understanding.contracts import ExtractionConfiguration
from oomp.understanding.rules import (
    RulesExtractor, classify, classify_legacy, clauses, promotion, proposal_for,
)
from oomp.understanding.storage import _new_node, candidate_writes
from oomp.understanding.validator import CandidateRejected, CandidateValidator


SCOPE = AuthorizedScope(tenant_id="p4-literal-quality", namespace="synthetic", principal_id="owner")
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
ALIAS = "In this fictional test, I use NOVA as my personal alias."
STYLE = "Please keep your replies concise and use three bullets when a list is helpful."
PLAN = "I may relocate from Cedar Bay to Larch Haven next spring, but this is only a tentative plan."


def event(text, *, role="user", identifier="source-1"):
    return MemoryEvent(event_id=identifier, tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
        event_type="document" if role == "document" else role + "_message", source_type=role,
        content=text, occurred_at=NOW, ingested_at=NOW, metadata={"ingested_by": SCOPE.principal_id},
        source_reference=SourceReference(source_system="public-synthetic", external_event_id=identifier,
            timestamp=NOW, session_id="literal-quality-session"))


def old_episode(sample, span=None):
    span = span or clauses(sample.content)[0]
    original = proposal_for(SCOPE, sample, span, hints=classify_legacy(sample, span))
    return _new_node(SCOPE, sample, original, episode=True)


@pytest.mark.parametrize("text,predicate,category,assertion", [
    (ALIAS, "alias", "profile", "explicit"),
    ("I use Harbor Finch as my display alias.", "alias", "profile", "explicit"),
    ("In this synthetic test, I use Élan as my alias.", "alias", "profile", "explicit"),
    (STYLE, "preference", "procedural", "explicit"),
    ("Keep your answers brief.", "preference", "procedural", "explicit"),
    ("Please make your explanations clear and include examples.", "preference", "procedural", "explicit"),
    (PLAN, "plan", "prospective", "tentative"),
    ("I might travel to Alder Harbor next autumn.", "plan", "prospective", "tentative"),
    ("I could build a small observatory next year.", "plan", "prospective", "tentative"),
])
def test_anchored_literal_forms_produce_independently_validated_candidates(text, predicate, category, assertion):
    sample = event(text)
    candidate, = RulesExtractor().propose(SCOPE, sample)
    assert (candidate.predicate, candidate.memory_category, candidate.assertion_kind) == (predicate, category, assertion)
    assert promotion(candidate) == ("canonical", "explicit_user_claim")
    assert CandidateValidator().validate(SCOPE, sample, (candidate,)) == (candidate,)
    span, = candidate.source_spans
    assert span.quote == text[span.start:span.end] == candidate.object
    writes = candidate_writes(SCOPE, sample, candidate, ExtractionConfiguration())
    assert len(writes) == 2
    assert all(source_entails_memory(SCOPE, sample, write.source_span, write.memory) for write in writes)


def test_literal_alias_is_an_unverified_display_claim_without_identity_authority():
    sample = event(ALIAS)
    candidate, = RulesExtractor().propose(SCOPE, sample)
    canonical, episode = candidate_writes(SCOPE, sample, candidate, ExtractionConfiguration())
    assert canonical.memory.memory_type.value == "profile"
    for write in (canonical, episode):
        assert write.memory.metadata["attribution"] == "user"
        assert write.memory.metadata["verified"] is False
        assert write.memory.metadata["authenticated"] is False
        assert write.memory.metadata["identity_claim"] == "display-alias"
        assert write.memory.metadata["validity"] == "uncertain"


@pytest.mark.parametrize("text,role,assertion", [
    ('“I use Nova as my personal alias.”', "user", "quoted"),
    ('Mara said I use Nova as my personal alias.', "user", "quoted"),
    ("If I use Nova as my personal alias, we can test it.", "user", "hypothetical"),
    ("Suppose I may relocate next spring.", "user", "hypothetical"),
    ("I may relocate if the offer arrives.", "user", "hypothetical"),
    ("Please keep your replies concise?", "user", "question"),
    ("Maybe please keep your replies concise.", "user", "uncertain"),
    ("I use Nova as my personal alias.", "assistant", "assistant-originated"),
    ("I may relocate next spring.", "document", "quoted"),
])
def test_existing_attribution_and_nonassertion_guards_precede_literal_recognition(text, role, assertion):
    sample = event(text, role=role)
    candidates = RulesExtractor().propose(SCOPE, sample)
    assert candidates
    assert all(p.assertion_kind == assertion and promotion(p)[0] == "episodic-only" for p in candidates)
    assert all(p.predicate == "stated" for p in candidates)
    CandidateValidator().validate(SCOPE, sample, candidates)


@pytest.mark.parametrize("text", [
    "My friend may relocate next spring.",
    "The instructions mention aliases and concise replies.",
    "I may have moved last spring.",
    "I use Nova or Star as my personal alias.",
    "I use my friend's name as my alias.",
    "I use some alias as my personal alias.",
    "Please keep the window concise.",
])
def test_word_mentions_third_parties_ambiguous_aliases_and_completed_forms_are_not_promoted(text):
    candidate, = RulesExtractor().propose(SCOPE, event(text))
    assert candidate.predicate == "stated"
    assert promotion(candidate)[0] == "episodic-only"


def test_existing_third_party_semantic_claim_is_not_a_speaker_alias_or_verified_identity():
    sample = event("Mara uses Nova as her personal alias.")
    span, = clauses(sample.content)
    # The original grammar preserves the entire third-party sentence as a
    # semantic claim without assigning it to the speaker's personal identity.
    original = classify_legacy(sample, span)
    assert (original["predicate"], original["memory_category"], original["sensitivity"]) == ("stated", "semantic", "ordinary")
    assert classify(sample, span) == original
    baseline_candidate = _extract_statement(sample, span)
    assert baseline_candidate is not None and baseline_candidate.subject is None
    baseline = canonicalize(baseline_candidate, sample, now=NOW)
    assert baseline.canonical_content == sample.content
    assert baseline.memory_type.value == "semantic"
    assert baseline.metadata == {"attribution": "user", "verified": False, "canonicalization_version": "1"}

    candidate, = RulesExtractor().propose(SCOPE, sample)
    assert CandidateValidator().validate(SCOPE, sample, (candidate,)) == (candidate,)
    writes = candidate_writes(SCOPE, sample, candidate, ExtractionConfiguration())
    canonical, episode = writes
    assert _memory_fingerprint(canonical.memory) == _memory_fingerprint(baseline)
    assert canonical.memory.canonical_key == baseline.canonical_key
    assert _memory_fingerprint(episode.memory) == _memory_fingerprint(old_episode(sample))
    for write in writes:
        assert write.memory.memory_type.value != "profile"
        assert write.memory.metadata["verified"] is False
        assert "identity_claim" not in write.memory.metadata and "authenticated" not in write.memory.metadata
        assert source_entails_memory(SCOPE, sample, span, write.memory)
    assert source_entails_memory(SCOPE, sample, span, baseline)

    # Both deterministic and hypothetical model proposals must reject turning
    # this exact third-party source into a profile/alias for the speaker.
    for provider, config in (("rules", ExtractionConfiguration()),
            ("ollama", ExtractionConfiguration(mode="local-llm", model="synthetic-offline"))):
        forged = proposal_for(SCOPE, sample, span, provider=provider, model=config.model,
            hints={"predicate": "alias", "memory_category": "profile"})
        with pytest.raises(CandidateRejected, match="candidate_semantics_unsupported"):
            CandidateValidator(config).validate(SCOPE, sample, (forged,))
        assert not source_entails_memory(SCOPE, sample, span, _new_node(SCOPE, sample, forged, episode=False))


def test_sensitive_literal_source_retains_the_existing_opt_in_episode_boundary():
    sample = event("I may relocate for cancer therapy next spring.")
    assert RulesExtractor().propose(SCOPE, sample) == ()
    candidate, = RulesExtractor(ExtractionConfiguration(sensitive_episodes=True)).propose(SCOPE, sample)
    assert candidate.sensitivity == "sensitive"
    assert candidate.predicate == "stated"
    assert promotion(candidate) == ("episodic-only", "sensitive_topic_only")


def test_unicode_span_offsets_and_clauses_remain_exact_without_event_rewriting():
    sample = event("Café note. In this fictional test, I use Élan as my personal alias. Another statement.")
    candidates = RulesExtractor().propose(SCOPE, sample)
    alias, = [p for p in candidates if p.predicate == "alias"]
    span, = alias.source_spans
    assert span.start == sample.content.index("In this")
    assert span.end == sample.content.index(" Another")
    assert span.quote == sample.content[span.start:span.end]
    assert span.start != len(sample.content[:span.start].encode("utf-8"))
    assert len(candidates) == 3
    CandidateValidator().validate(SCOPE, sample, candidates)


@pytest.mark.parametrize("change", [
    {"principal_id": "other"}, {"claimed_by": "assistant"},
    {"assertion_kind": "explicit"}, {"memory_category": "profile"},
    {"predicate": "alias"},
])
def test_provider_cannot_change_authority_or_tentative_plan_semantics(change):
    sample = event(PLAN)
    candidate, = RulesExtractor().propose(SCOPE, sample)
    payload = candidate.model_dump(mode="json")
    payload.update(change)
    with pytest.raises(CandidateRejected):
        CandidateValidator().validate(SCOPE, sample, (payload,))


def test_partial_span_cannot_remove_the_modal_plan_qualification():
    sample = event(PLAN)
    candidate, = RulesExtractor().propose(SCOPE, sample)
    payload = candidate.model_dump(mode="json")
    start = sample.content.index("relocate")
    payload["source_spans"] = [{"start": start, "end": len(sample.content), "quote": sample.content[start:]}]
    payload["object"] = sample.content[start:]
    payload["assertion_kind"] = "explicit"
    with pytest.raises(CandidateRejected):
        CandidateValidator().validate(SCOPE, sample, (payload,))


@pytest.mark.parametrize("text,old_assertion", [(ALIAS, "explicit"), (STYLE, "explicit"),
    (PLAN, "explicit"), ("I might travel to Alder Harbor next autumn.", "uncertain")])
def test_exact_old_generic_episodes_remain_independently_source_entailing(text, old_assertion):
    sample = event(text)
    span, = clauses(text)
    memory = old_episode(sample, span)
    assert memory.metadata["assertion_kind"] == old_assertion
    assert memory.metadata["category"] == "episodic" and memory.metadata["predicate"] == "stated"
    assert classify(sample, span) != classify_legacy(sample, span)
    assert legacy_episode_entails_memory(SCOPE, sample, span, memory)
    assert source_entails_memory(SCOPE, sample, span, memory)
    candidate, = RulesExtractor().propose(SCOPE, sample)
    for write in candidate_writes(SCOPE, sample, candidate, ExtractionConfiguration()):
        assert not legacy_episode_entails_memory(SCOPE, sample, span, write.memory)
        assert source_entails_memory(SCOPE, sample, span, write.memory)


@pytest.mark.parametrize("change", [
    {"canonical_content": "User definitely moved to Larch Haven."},
    {"canonical_key": "p2:forged"}, {"tags": ("invented",)},
    {"metadata": {"verified": False, "canonicalization_version": "p2.1", "p2_episode": True}},
    {"assertion_kind": "tentative"}, {"category": "prospective"},
    {"predicate": "plan"}, {"promotion": "canonical"}, {"principal_id": "other"},
])
def test_legacy_compatibility_never_trusts_changed_claims_keys_or_metadata(change):
    sample = event(PLAN)
    span, = clauses(sample.content)
    memory = old_episode(sample)
    if any(key in {"canonical_content", "canonical_key", "tags", "metadata"} for key in change):
        tampered = memory.model_copy(update=change)
    else:
        tampered = memory.model_copy(update={"metadata": {**memory.metadata, **change}})
    assert not legacy_episode_entails_memory(SCOPE, sample, span, tampered)
    assert not source_entails_memory(SCOPE, sample, span, tampered)


def test_legacy_compatibility_requires_the_whole_exact_clause_and_authorized_source():
    sample = event(PLAN)
    memory = old_episode(sample)
    span, = clauses(sample.content)
    assert not legacy_episode_entails_memory(SCOPE.model_copy(update={"principal_id": "other"}), sample, span, memory)
    cropped = SourceSpan(start=2, end=span.end, quote=sample.content[2:])
    assert not legacy_episode_entails_memory(SCOPE, sample, cropped, memory)
    unrelated = event(PLAN, identifier="unrelated-source")
    assert not legacy_episode_entails_memory(SCOPE, unrelated, span, memory)
    unchanged = event("The synthetic sky is blue.")
    assert not legacy_episode_entails_memory(SCOPE, unchanged, clauses(unchanged.content)[0], old_episode(unchanged))


def test_existing_validated_literal_model_procedure_keeps_its_canonical_fingerprint():
    sample = event(STYLE)
    span, = clauses(sample.content)
    old_fields = {**classify_legacy(sample, span), "predicate": "preference", "memory_category": "procedural"}
    old_model = proposal_for(SCOPE, sample, span, provider="ollama", model="synthetic-offline", hints=old_fields)
    memory = _new_node(SCOPE, sample, old_model, episode=False)
    assert memory.metadata["importance"] == "low"
    assert not legacy_episode_entails_memory(SCOPE, sample, span, memory)
    assert source_entails_memory(SCOPE, sample, span, memory)


def persist(path, sample, memory):
    events = SQLiteEventStore(path)
    events.initialize()
    events.append(SCOPE, sample)
    with SQLiteMemoryStore(path)._transaction() as connection:
        stored, _, _ = SQLiteMemoryStore(path)._upsert_in_transaction(connection, SCOPE, memory,
            source_spans={sample.event_id: clauses(sample.content)[0]}, extraction_method="mind2.rules.v1")
    return stored


def fact_proof(store, sample, memory):
    with store._graph_transaction() as connection:
        store.require_objects(connection)
        identifier = store.registry(connection, SCOPE, ObjectType.FACT,
            ["memory", memory.memory_id], reference=memory.memory_id)
        span = store.stored_span(connection, SCOPE, memory.memory_id, sample.event_id)
        proof_id = store.put_proof(connection, SCOPE, identifier, memory, sample, span,
            role="fact", label="Attributed claim")
    with store._graph_read() as connection:
        return dict(connection.execute("SELECT * FROM map_proofs WHERE proof_id=?", (proof_id,)).fetchone())


def test_p3_old_explicit_plan_proof_survives_exact_episode_revalidation(tmp_path, monkeypatch):
    sample = event(PLAN)
    path = tmp_path / "old-plan.sqlite3"
    memory = persist(path, sample, old_episode(sample))
    store = ObjectStorage(path)
    # Simulate the accepted old projection, without touching any old database.
    with monkeypatch.context() as historic:
        historic.setattr("oomp.objects.storage.classify", classify_legacy)
        row = fact_proof(store, sample, memory)
    assert row["assertion_kind"] == "explicit"
    assert classify(sample, clauses(sample.content)[0])["assertion_kind"] == "tentative"
    with store._graph_read() as connection:
        proof, label, withdrawn = store.validate_proof(connection, SCOPE, row)
        assert proof.assertion_kind == "explicit" and label == "Attributed claim" and not withdrawn
        assert proof.source_span.quote == PLAN and proof.event_id == sample.event_id
        with pytest.raises(ObjectMapError, match="object_assertion_invalid"):
            store.validate_proof(connection, SCOPE, {**row, "assertion_kind": "quoted"})


def test_p3_old_assertion_cannot_authorize_a_tampered_claim(tmp_path, monkeypatch):
    sample = event(PLAN)
    path = tmp_path / "tampered-plan.sqlite3"
    old = old_episode(sample)
    forged = old.model_copy(update={"memory_id": "forged-plan", "canonical_content": "User definitely moved."})
    memory = persist(path, sample, forged)
    store = ObjectStorage(path)
    # The historic API admitted exact span links without validating a claim's
    # full fingerprint; the new assertion compatibility must not inherit that.
    with monkeypatch.context() as historic:
        historic.setattr("oomp.objects.storage.classify", classify_legacy)
        row = fact_proof(store, sample, memory)
    with store._graph_read() as connection, pytest.raises(ObjectMapError, match="object_assertion_invalid"):
        store.validate_proof(connection, SCOPE, row)


def test_p3_new_typed_plan_proof_requires_the_new_tentative_assertion(tmp_path):
    sample = event(PLAN)
    candidate, = RulesExtractor().propose(SCOPE, sample)
    _, episode = candidate_writes(SCOPE, sample, candidate, ExtractionConfiguration())
    path = tmp_path / "new-plan.sqlite3"
    memory = persist(path, sample, episode.memory)
    store = ObjectStorage(path)
    row = fact_proof(store, sample, memory)
    assert row["assertion_kind"] == "tentative"
    with store._graph_read() as connection:
        proof, _, _ = store.validate_proof(connection, SCOPE, row)
        assert proof.assertion_kind == "tentative"
        with pytest.raises(ObjectMapError, match="object_assertion_invalid"):
            store.validate_proof(connection, SCOPE, {**row, "assertion_kind": "explicit"})
