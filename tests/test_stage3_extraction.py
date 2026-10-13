"""Focused tests for conservative Stage 3 extraction and textual identity."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from oomp.domain.enums import EventType, MemoryType, SourceType
from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
from oomp.ingestion.canonicalization import canonical_key, canonicalize, normalize_content
from oomp.ingestion.contracts import MemoryCandidate
from oomp.ingestion.extraction import DeterministicExtractor

NOW = datetime(2026, 1, 2, 10, tzinfo=timezone.utc)
SCOPE = AuthorizedScope(tenant_id="tenant-a", namespace="personal", principal_id="test-service")


def event(
    content: str, *, event_id: str = "event-1",
    event_type: EventType = EventType.USER_MESSAGE,
    source_type: SourceType = SourceType.USER,
    tenant_id: str = "tenant-a", namespace: str = "personal",
) -> MemoryEvent:
    return MemoryEvent(
        event_id=event_id, tenant_id=tenant_id, namespace=namespace,
        event_type=event_type, source_type=source_type, content=content,
        source_reference=SourceReference(
            source_system="synthetic-test", external_event_id=event_id, timestamp=NOW,
        ),
        occurred_at=NOW, ingested_at=NOW,
    )


@pytest.mark.parametrize(
    ("content", "expected_type", "expected_content"),
    [
        ("I prefer Python for local AI development.", MemoryType.PROFILE,
         "User prefers Python for local AI development."),
        ("I do not prefer Python.", MemoryType.PROFILE,
         "User does not prefer Python."),
        ("I don't prefer Python.", MemoryType.PROFILE,
         "User does not prefer Python."),
        ("I am developing a project called OOMP.", MemoryType.PROJECT_STATE,
         "User is developing a project called OOMP."),
        ("I am considering buying a 3D printer.", MemoryType.PROJECT_STATE,
         "User is considering buying a 3D printer."),
        ("I plan to build a robot.", MemoryType.PROJECT_STATE,
         "User plans to build a robot."),
        ("I purchased a 3D printer.", MemoryType.EPISODIC,
         "User purchased a 3D printer."),
        ("OOMP uses an independent SQLite-backed memory store.", MemoryType.SEMANTIC,
         "OOMP uses an independent SQLite-backed memory store."),
        ("We decided to keep OOMP independent from TRACE.", MemoryType.DECISION,
         "We decided to keep OOMP independent from TRACE."),
    ],
)
def test_supported_statements(content: str, expected_type: MemoryType, expected_content: str) -> None:
    source = event(content)
    candidates = DeterministicExtractor().extract_candidates(SCOPE, source)
    assert len(candidates) == 1
    assert candidates[0].memory_type is expected_type
    assert candidates[0].canonical_content == expected_content
    assert candidates[0].confidence is None
    assert candidates[0].source_event_id == source.event_id
    assert source.content[candidates[0].source_span.start:candidates[0].source_span.end] == candidates[0].source_span.quote


@pytest.mark.parametrize(
    "content",
    [
        "Should we keep OOMP independent from TRACE?",
        "Maybe I will start a robotics company someday.",
        "I might purchase a 3D printer.",
        "I could prefer Python.",
        "If I prefer Python, I will use it.",
        "I prefer Python if it is installed.",
        "We talked about project plans.",
        "The user founded a robotics company.",
        "What if I prefer Python? I prefer Rust.",
        "I prefer Python. My API key is abc123.",
        "I prefer Python.\nSECRET=synthetic-private-value",
        "I prefer Python. token:synthetic-private-value",
        "I prefer Python. -----BEGIN PRIVATE KEY-----",
    ],
)
def test_unsupported_uncertain_questions_and_secrets_are_not_promoted(content: str) -> None:
    assert DeterministicExtractor().extract_candidates(SCOPE, event(content)) == ()


def test_two_statements_have_independent_unicode_source_spans() -> None:
    source = event("  I prefer Café.  I am developing a project called OOMP (Object-Oriented Context Map).")
    candidates = DeterministicExtractor().extract_candidates(SCOPE, source)
    assert [candidate.memory_type for candidate in candidates] == [MemoryType.PROFILE, MemoryType.PROJECT_STATE]
    for candidate in candidates:
        span = candidate.source_span
        assert source.content[span.start:span.end] == span.quote
    mention = candidates[1].entities[0]
    assert mention.name == "OOMP"
    assert mention.aliases == ("Object-Oriented Context Map",)
    assert mention.source_span is not None
    assert source.content[mention.source_span.start:mention.source_span.end] == mention.source_span.quote
    assert mention.source_span.quote == "OOMP (Object-Oriented Context Map)"


def test_source_roles_and_document_attribution() -> None:
    extractor = DeterministicExtractor()
    assistant = event(
        "The user prefers Java.", event_type=EventType.ASSISTANT_MESSAGE,
        source_type=SourceType.ASSISTANT,
    )
    tool = event(
        "OOMP uses SQLite.", event_type=EventType.TOOL_RESULT, source_type=SourceType.TOOL,
    )
    document = event(
        "OOMP uses SQLite.", event_type=EventType.DOCUMENT,
        source_type=SourceType.DOCUMENT,
    )
    document_preference = event(
        "I prefer Python.", event_type=EventType.DOCUMENT,
        source_type=SourceType.DOCUMENT,
    )
    assert extractor.extract_candidates(SCOPE, assistant) == ()
    assert extractor.extract_candidates(SCOPE, tool) == ()
    assert extractor.extract_candidates(SCOPE, document_preference) == ()
    candidate = extractor.extract_candidates(SCOPE, document)[0]
    memory = canonicalize(candidate, document, now=NOW)
    assert memory.memory_type is MemoryType.SEMANTIC
    assert memory.metadata["attribution"] == "document"
    assert memory.metadata["verified"] is False


def test_canonical_identity_is_scoped_and_preserves_negation_modality() -> None:
    extractor = DeterministicExtractor()
    positive = event(" I   prefer  Python. ")
    equivalent = event("I prefer Python.", event_id="event-2")
    negative = event("I do not prefer Python.")
    considering = event("I am considering buying a 3D printer.")
    purchased = event("I purchased a 3D printer.")
    key = canonical_key(extractor.extract_candidates(SCOPE, positive)[0], positive)
    assert key == canonical_key(extractor.extract_candidates(SCOPE, equivalent)[0], equivalent)
    assert key != canonical_key(extractor.extract_candidates(SCOPE, negative)[0], negative)
    assert canonical_key(extractor.extract_candidates(SCOPE, considering)[0], considering) != (
        canonical_key(extractor.extract_candidates(SCOPE, purchased)[0], purchased)
    )
    other = event("I prefer Python.", tenant_id="tenant-b")
    other_scope = AuthorizedScope(tenant_id="tenant-b", namespace="personal", principal_id="test-service")
    assert key != canonical_key(extractor.extract_candidates(other_scope, other)[0], other)
    assert normalize_content(" Cafe\u0301  is   useful ") == "Café is useful."


def test_source_scope_and_candidate_contract_fail_closed() -> None:
    source = event("I prefer Python.")
    foreign = AuthorizedScope(tenant_id="tenant-b", namespace="personal", principal_id="test-service")
    with pytest.raises(ValueError):
        DeterministicExtractor().extract_candidates(foreign, source)
    valid = DeterministicExtractor().extract_candidates(SCOPE, source)[0].model_dump(mode="json")
    for changes in (
        {"memory_type": "invented"}, {"source_span": None},
        {"source_event_id": None}, {"confidence": "0.9"},
    ):
        with pytest.raises(ValidationError):
            MemoryCandidate.model_validate({**valid, **changes})


def test_input_and_output_bounds_and_pure_memory_extractor() -> None:
    extractor = DeterministicExtractor()
    too_long = event("I prefer " + "x" * 16_384)
    assert extractor.extract_candidates(SCOPE, too_long) == ()
    many = event(" ".join("I prefer Python." for _ in range(40)))
    assert len(extractor.extract_candidates(SCOPE, many)) == 32
    source = event("I prefer Python.")
    memories = extractor.extract(SCOPE, (source,))
    assert len(memories) == 1
    assert memories[0].source_event_ids == (source.event_id,)
    assert memories[0].provenance == (source.source_reference,)
    assert memories[0].confidence is None
    assert memories[0].valid_from is None
    assert memories[0].valid_until is None
