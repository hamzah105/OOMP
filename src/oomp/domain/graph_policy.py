"""Conservative, source-grounded hardware claim comparison for Stage 4.

Only exact user reports about one fixed test computer and installed RAM are
supported. Proposals carry no write authority; storage rederives them before
an explicitly confirmed protected relationship is committed.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from .enums import EventType, MemoryStatus, MemoryType, RelationshipType, SourceType
from .models import (
    AuthorizedScope, ContractModel, Identifier, MemoryEvent, MemoryNode, UtcDateTime,
)

POLICY_VERSION = "hardware-ram-v1"
_RAM_STATE = re.compile(r"My test computer has (?P<value>[1-9][0-9]{0,3}) GB RAM\.")
_RAM_CHANGE = re.compile(r"I upgraded my test computer to (?P<value>[1-9][0-9]{0,3}) GB RAM\.")


class ConflictProposal(ContractModel):
    proposal_id: Identifier
    tenant_id: Identifier
    namespace: Identifier
    source_node_id: Identifier
    target_node_id: Identifier
    relationship_type: RelationshipType
    source_event_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=2)
    reason: str = Field(min_length=1, max_length=256)
    policy_version: Literal["hardware-ram-v1"] = POLICY_VERSION
    requires_confirmation: Literal[True] = True
    valid_from: UtcDateTime | None = None
    valid_until: UtcDateTime | None = None

    @model_validator(mode="after")
    def protected_relationship(self) -> ConflictProposal:
        if self.relationship_type not in {RelationshipType.CONTRADICTS, RelationshipType.SUPERSEDES}:
            raise ValueError("proposal relationship must be protected")
        if self.source_node_id == self.target_node_id:
            raise ValueError("proposal endpoints must differ")
        if len(self.source_event_ids) != len(set(self.source_event_ids)):
            raise ValueError("proposal evidence IDs must be distinct")
        if self.valid_from is not None and self.valid_until is not None:
            if self.valid_until <= self.valid_from:
                raise ValueError("proposal validity interval must be nonempty")
        return self


class ConflictAssessment(ContractModel):
    proposal: ConflictProposal | None = None
    reason: str = Field(min_length=1, max_length=256)


def _supported_claim(memory: MemoryNode, event: MemoryEvent) -> tuple[str, int] | None:
    if memory.memory_type not in {MemoryType.SEMANTIC, MemoryType.PROFILE}:
        return None
    if memory.status is not MemoryStatus.ACTIVE:
        return None
    if memory.valid_from is not None and memory.valid_until is not None and memory.valid_until <= memory.valid_from:
        return None
    if event.source_type is not SourceType.USER or event.event_type not in {
        EventType.USER_MESSAGE, EventType.CORRECTION, EventType.FEEDBACK,
    }:
        return None
    if event.event_id not in memory.source_event_ids:
        return None
    index = memory.source_event_ids.index(event.event_id)
    if index >= len(memory.provenance) or memory.provenance[index] != event.source_reference:
        return None
    if memory.metadata.get("attribution") != SourceType.USER.value:
        return None
    if memory.metadata.get("verified") is not False:
        return None
    if memory.canonical_content != event.content:
        return None
    if match := _RAM_STATE.fullmatch(event.content):
        return "state", int(match.group("value"))
    if match := _RAM_CHANGE.fullmatch(event.content):
        return "change", int(match.group("value"))
    return None


def _id(
    scope: AuthorizedScope, source: MemoryNode, target: MemoryNode,
    relationship: RelationshipType, evidence: tuple[str, ...],
    valid_from: datetime, valid_until: datetime | None,
) -> str:
    payload = [
        POLICY_VERSION, scope.tenant_id, scope.namespace,
        source.memory_id, target.memory_id, relationship.value, evidence,
        valid_from.isoformat(), valid_until.isoformat() if valid_until else None,
    ]
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return "proposal-" + digest


def propose_conflict(
    scope: AuthorizedScope,
    source: MemoryNode,
    target: MemoryNode,
    source_event: MemoryEvent,
    target_event: MemoryEvent,
) -> ConflictAssessment:
    """Compare exactly sourced claims; never mutate records or assume newer is true."""
    if not isinstance(scope, AuthorizedScope):
        raise TypeError("an AuthorizedScope from a trusted caller is required")
    authorized = AuthorizedScope.model_validate(scope.model_dump(mode="json"))
    if not isinstance(source, MemoryNode) or not isinstance(target, MemoryNode):
        raise TypeError("validated MemoryNode endpoints are required")
    if not isinstance(source_event, MemoryEvent) or not isinstance(target_event, MemoryEvent):
        raise TypeError("validated MemoryEvent evidence is required")
    source = MemoryNode.model_validate(source.model_dump(mode="json"))
    target = MemoryNode.model_validate(target.model_dump(mode="json"))
    source_event = MemoryEvent.model_validate(source_event.model_dump(mode="json"))
    target_event = MemoryEvent.model_validate(target_event.model_dump(mode="json"))
    scope_parts = (authorized.tenant_id, authorized.namespace)
    if any(
        (item.tenant_id, item.namespace) != scope_parts
        for item in (source, target, source_event, target_event)
    ):
        raise ValueError("claim scope differs from authorized scope")
    if source.memory_id == target.memory_id:
        return ConflictAssessment(reason="insufficient structured evidence: same memory")
    if source.memory_type is not target.memory_type:
        return ConflictAssessment(reason="insufficient structured evidence: different memory types")
    current = _supported_claim(source, source_event)
    prior = _supported_claim(target, target_event)
    if current is None or prior is None:
        return ConflictAssessment(reason="insufficient structured evidence: unsupported source claim")
    source_kind, source_value = current
    target_kind, target_value = prior
    if source_value == target_value:
        return ConflictAssessment(reason="compatible reported RAM values")
    if source.valid_from is None or target.valid_from is None:
        return ConflictAssessment(reason="insufficient structured evidence: unknown reported validity")
    if source_event.occurred_at < source.valid_from or target_event.occurred_at < target.valid_from:
        return ConflictAssessment(reason="insufficient structured evidence: source predates asserted validity")

    if source_kind == "change" and target_kind in {"state", "change"}:
        if source.valid_from <= target.valid_from or source_event.occurred_at <= target_event.occurred_at:
            return ConflictAssessment(reason="insufficient structured evidence: later change not established")
        if target.valid_until is not None and target.valid_until < source.valid_from:
            return ConflictAssessment(reason="insufficient structured evidence: earlier state ended before change")
        relationship = RelationshipType.SUPERSEDES
        evidence = (source_event.event_id,)
        reason = "Explicit user-reported RAM upgrade replaces an earlier reported value."
        valid_from = source.valid_from
        valid_until = source.valid_until
    elif source_kind == "state" and target_kind == "state":
        if source.valid_until is None or target.valid_until is None:
            return ConflictAssessment(reason="insufficient structured evidence: overlap is unknown")
        valid_from = max(source.valid_from, target.valid_from)
        valid_until = min(source.valid_until, target.valid_until)
        if valid_until <= valid_from:
            return ConflictAssessment(reason="reported validity intervals do not overlap")
        relationship = RelationshipType.CONTRADICTS
        evidence = (source_event.event_id, target_event.event_id)
        reason = "Incompatible user-reported RAM values overlap for the same test computer."
    else:
        return ConflictAssessment(reason="insufficient structured evidence: claim modalities differ")

    proposal = ConflictProposal(
        proposal_id=_id(
            authorized, source, target, relationship, evidence, valid_from, valid_until,
        ),
        tenant_id=authorized.tenant_id, namespace=authorized.namespace,
        source_node_id=source.memory_id, target_node_id=target.memory_id,
        relationship_type=relationship, source_event_ids=evidence,
        reason=reason, valid_from=valid_from, valid_until=valid_until,
    )
    return ConflictAssessment(proposal=proposal, reason=reason)
