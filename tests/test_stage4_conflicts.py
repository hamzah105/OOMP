"""Pure conservative conflict policy tests for exact user hardware evidence."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from oomp.domain.enums import EventType, MemoryType, RelationshipType, SourceType
from oomp.domain.graph_policy import ConflictProposal, propose_conflict
from oomp.domain.models import AuthorizedScope, MemoryEvent, MemoryNode, SourceReference

SCOPE = AuthorizedScope(tenant_id="tenant-a", namespace="personal", principal_id="trusted-test")
SEP1 = datetime(2026, 9, 1, tzinfo=timezone.utc)
SEP10 = datetime(2026, 9, 10, tzinfo=timezone.utc)
SEP20 = datetime(2026, 9, 20, tzinfo=timezone.utc)
OCT10 = datetime(2026, 10, 10, tzinfo=timezone.utc)
OCT20 = datetime(2026, 10, 20, tzinfo=timezone.utc)


def source(
    event_id: str, text: str, occurred_at: datetime,
    *, tenant_id: str = "tenant-a", namespace: str = "personal",
) -> MemoryEvent:
    return MemoryEvent(
        event_id=event_id, tenant_id=tenant_id, namespace=namespace,
        event_type=EventType.USER_MESSAGE, source_type=SourceType.USER,
        content=text,
        source_reference=SourceReference(
            source_system="synthetic-test", external_event_id=event_id,
            timestamp=occurred_at,
        ),
        occurred_at=occurred_at, ingested_at=occurred_at,
    )


def memory(
    memory_id: str, event: MemoryEvent,
    *, valid_from: datetime | None, valid_until: datetime | None,
    content: str | None = None, metadata: dict | None = None,
) -> MemoryNode:
    return MemoryNode(
        memory_id=memory_id, tenant_id=event.tenant_id, namespace=event.namespace,
        memory_type=MemoryType.SEMANTIC,
        canonical_key="test:" + memory_id,
        canonical_content=event.content if content is None else content,
        source_event_ids=(event.event_id,), provenance=(event.source_reference,),
        created_at=event.ingested_at, updated_at=event.ingested_at,
        valid_from=valid_from, valid_until=valid_until,
        metadata={"attribution": "user", "verified": False} if metadata is None else metadata,
    )


def hardware_pair():
    old_event = source("event-old", "My test computer has 4 GB RAM.", SEP10)
    new_event = source("event-new", "I upgraded my test computer to 12 GB RAM.", OCT10)
    old = memory("memory-old", old_event, valid_from=SEP1, valid_until=SEP20)
    new = memory("memory-new", new_event, valid_from=SEP20, valid_until=OCT20)
    return new, old, new_event, old_event


def test_explicit_hardware_upgrade_proposes_confirmed_supersession_without_mutation() -> None:
    new, old, new_event, old_event = hardware_pair()
    assessment = propose_conflict(SCOPE, new, old, new_event, old_event)
    proposal = assessment.proposal
    assert proposal is not None
    assert proposal.relationship_type is RelationshipType.SUPERSEDES
    assert proposal.source_event_ids == (new_event.event_id,)
    assert proposal.source_node_id == new.memory_id
    assert proposal.target_node_id == old.memory_id
    assert proposal.valid_from == SEP20
    assert proposal.requires_confirmation is True
    assert proposal.policy_version == "hardware-ram-v1"
    assert propose_conflict(SCOPE, new, old, new_event, old_event).proposal == proposal
    assert old.status.value == new.status.value == "active"


def test_overlapping_exact_states_propose_unresolved_contradiction() -> None:
    first_event = source("event-1", "My test computer has 4 GB RAM.", SEP10)
    second_event = source("event-2", "My test computer has 12 GB RAM.", OCT10)
    first = memory("memory-1", first_event, valid_from=SEP1, valid_until=OCT20)
    second = memory("memory-2", second_event, valid_from=SEP20, valid_until=OCT20)
    assessment = propose_conflict(SCOPE, second, first, second_event, first_event)
    assert assessment.proposal is not None
    assert assessment.proposal.relationship_type is RelationshipType.CONTRADICTS
    assert assessment.proposal.source_event_ids == ("event-2", "event-1")
    assert assessment.proposal.valid_from == SEP20
    assert assessment.proposal.valid_until == OCT20


@pytest.mark.parametrize(
    "new_bounds,old_bounds",
    [
        ((None, OCT20), (SEP1, SEP20)),
        ((SEP20, None), (SEP1, None)),
        ((OCT20, None), (SEP1, SEP20)),
    ],
)
def test_missing_or_nonoverlapping_validity_does_not_invent_conflict(new_bounds, old_bounds) -> None:
    first_event = source("event-1", "My test computer has 4 GB RAM.", SEP10)
    second_event = source("event-2", "My test computer has 12 GB RAM.", OCT20)
    first = memory("memory-1", first_event, valid_from=old_bounds[0], valid_until=old_bounds[1])
    second = memory("memory-2", second_event, valid_from=new_bounds[0], valid_until=new_bounds[1])
    assessment = propose_conflict(SCOPE, second, first, second_event, first_event)
    assert assessment.proposal is None
    assert assessment.reason


def test_different_predicate_and_modality_stay_uncertain() -> None:
    new, old, _, old_event = hardware_pair()
    for text in (
        "I prefer Python.",
        "I am considering buying 12 GB RAM.",
        "My test computer might have 12 GB RAM.",
        "I upgraded my other computer to 12 GB RAM.",
    ):
        other_event = source("event-other", text, OCT10)
        other = memory("memory-other", other_event, valid_from=SEP20, valid_until=OCT20)
        assert propose_conflict(SCOPE, other, old, other_event, old_event).proposal is None


def test_spoofed_metadata_slot_or_mismatched_content_cannot_create_proposal() -> None:
    new, old, new_event, old_event = hardware_pair()
    spoofed = memory(
        "memory-new", new_event, valid_from=SEP20, valid_until=OCT20,
        content="My test computer has 12 GB RAM.",
        metadata={
            "attribution": "user", "verified": False,
            "subject": "test computer", "attribute": "installed_ram_gb", "value": 12,
        },
    )
    assert propose_conflict(SCOPE, spoofed, old, new_event, old_event).proposal is None
    unlabelled = memory(
        "memory-new", new_event, valid_from=SEP20, valid_until=OCT20, metadata={},
    )
    assert propose_conflict(SCOPE, unlabelled, old, new_event, old_event).proposal is None


def test_scope_and_confirmation_contract_fail_closed() -> None:
    new, old, new_event, old_event = hardware_pair()
    foreign = AuthorizedScope(tenant_id="other", namespace="personal", principal_id="trusted-test")
    with pytest.raises(ValueError):
        propose_conflict(foreign, new, old, new_event, old_event)
    proposal = propose_conflict(SCOPE, new, old, new_event, old_event).proposal
    assert proposal is not None
    for changes in (
        {"relationship_type": "RELATED_TO"},
        {"requires_confirmation": False},
        {"source_node_id": proposal.target_node_id},
    ):
        with pytest.raises(ValidationError):
            ConflictProposal.model_validate({**proposal.model_dump(mode="json"), **changes})


def test_selected_later_source_evidence_and_upgrade_chain_are_supported() -> None:
    second, old, second_event, old_event = hardware_pair()
    repeated = source("event-repeat", second_event.content, OCT10)
    fields = second.model_dump(mode="json")
    fields["source_event_ids"] = [second_event.event_id, repeated.event_id]
    fields["valid_until"] = datetime(2026, 11, 1, tzinfo=timezone.utc).isoformat()
    fields["provenance"] = [
        second_event.source_reference.model_dump(mode="json"),
        repeated.source_reference.model_dump(mode="json"),
    ]
    second_with_proof = MemoryNode.model_validate(fields)
    third_event = source(
        "event-third", "I upgraded my test computer to 16 GB RAM.",
        datetime(2026, 11, 10, tzinfo=timezone.utc),
    )
    third = memory(
        "memory-third", third_event,
        valid_from=datetime(2026, 11, 1, tzinfo=timezone.utc),
        valid_until=datetime(2026, 12, 1, tzinfo=timezone.utc),
    )
    assessment = propose_conflict(SCOPE, third, second_with_proof, third_event, repeated)
    assert assessment.proposal is not None
    assert assessment.proposal.relationship_type is RelationshipType.SUPERSEDES


def test_inactive_or_empty_validity_never_enters_conflict_policy() -> None:
    new, old, new_event, old_event = hardware_pair()
    retired_fields = old.model_dump(mode="json")
    retired_fields["status"] = "retracted"
    retired = MemoryNode.model_validate(retired_fields)
    assert propose_conflict(SCOPE, new, retired, new_event, old_event).proposal is None
    empty_fields = old.model_dump(mode="json")
    empty_fields["valid_until"] = SEP1.isoformat()
    empty = MemoryNode.model_validate(empty_fields)
    assert propose_conflict(SCOPE, new, empty, new_event, old_event).proposal is None