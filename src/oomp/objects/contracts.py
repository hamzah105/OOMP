"""P3 values describe a scoped projection, never authentication or source truth."""
from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, StrictInt, field_validator, model_validator

from oomp.domain.enums import RelationshipType
from oomp.domain.memories import SourceSpan
from oomp.domain.models import ContractModel, Identifier, SourceReference, UtcDateTime

VERSION = "object-map.v1"


class ObjectType(StrEnum):
    OWNER = "owner"
    DOMAIN = "domain"
    TOPIC = "topic"
    PERSON = "person"
    PROJECT = "project"
    PLAN = "plan"
    PLACE = "place"
    ORGANIZATION = "organization"
    EPISODE = "episode"
    CONCEPT = "concept"
    FACT = "fact"
    SOURCE_EVENT = "source_event"
    SESSION = "session"
    SUMMARY_REVISION = "summary_revision"


class ObjectMapError(ValueError):
    """Only constant content-free reason codes cross the CLI boundary."""
    def __init__(self, code="object_map_invalid"):
        self.code = code
        super().__init__(code)


class ObjectProof(ContractModel):
    proof_id: Identifier
    memory_id: Identifier
    event_id: Identifier
    source_span: SourceSpan
    source_reference: SourceReference
    occurred_at: UtcDateTime
    recorded_at: UtcDateTime
    known_at: UtcDateTime | None = None
    valid_from: UtcDateTime | None = None
    valid_until: UtcDateTime | None = None
    assertion_kind: str = Field(max_length=32)
    semantic_role: str = Field(max_length=48)
    claimed_by: Literal["user", "assistant", "document"]
    basis: Literal["source_span", "derived_navigation", "existing_graph"] = "source_span"
    verified: Literal[False] = False
    sensitivity: Literal["ordinary", "sensitive"] = "ordinary"


class MemoryObject(ContractModel):
    object_id: Identifier
    object_type: ObjectType
    canonical_label: str = Field(min_length=1, max_length=160)
    aliases: tuple[str, ...] = Field(default=(), max_length=32)
    tenant_id: Identifier
    namespace: Identifier
    principal_id: Identifier
    reference_id: Identifier | None = None
    status: Literal["structural", "claimed", "tentative", "attributed", "correction_pending", "superseded"]
    occurred_at: UtcDateTime | None = None
    recorded_at: UtcDateTime
    valid_from: UtcDateTime | None = None
    valid_until: UtcDateTime | None = None
    validity: bool | None = None
    source_proofs: tuple[ObjectProof, ...] = Field(default=(), max_length=128)
    creation_version: Literal["object-map.v1"] = VERSION


class ObjectCursor(ContractModel):
    tenant_id: Identifier
    namespace: Identifier
    principal_id: Identifier
    after_id: Identifier
    object_type: ObjectType | None = None


class ObjectPage(ContractModel):
    objects: tuple[MemoryObject, ...] = Field(default=(), max_length=500)
    next_cursor: ObjectCursor | None = None
    examined: StrictInt = Field(default=0, ge=0, le=10000)


class Membership(ContractModel):
    parent_id: Identifier
    child_id: Identifier
    role: Literal["domain", "topic", "object", "fact", "evidence", "related_plans", "referenced_objects", "episode", "revision", "session"]
    recorded_at: UtcDateTime
    proof_id: Identifier | None = None
    relation_id: Identifier | None = None
    support_proof_ids: tuple[Identifier, ...] = Field(default=(), max_length=128)
    support_relation_ids: tuple[Identifier, ...] = Field(default=(), max_length=128)


class ObjectRelation(ContractModel):
    relation_id: Identifier
    source_id: Identifier
    target_id: Identifier
    relationship_type: RelationshipType
    semantic_role: str = Field(min_length=1, max_length=48)
    basis: Literal["source_span", "derived_context", "existing_graph"]
    status: Literal["claimed", "tentative", "correction_pending", "attributed"]
    recorded_at: UtcDateTime
    valid_from: UtcDateTime | None = None
    valid_until: UtcDateTime | None = None
    proof_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=16)
    graph_edge_id: Identifier | None = None

    @model_validator(mode="after")
    def interval(self):
        if self.valid_from is not None and self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError("object_relation_invalid_interval")
        return self


class ObjectTreeNode(ContractModel):
    object: MemoryObject
    depth: StrictInt = Field(ge=0, le=10)


class ObjectTree(ContractModel):
    root_id: Identifier
    nodes: tuple[ObjectTreeNode, ...] = Field(default=(), max_length=500)
    memberships: tuple[Membership, ...] = Field(default=(), max_length=2000)
    relations: tuple[ObjectRelation, ...] = Field(default=(), max_length=2000)
    truncated: bool = False
    examined: StrictInt = Field(default=0, ge=0, le=10000)


class BuildResult(ContractModel):
    events_examined: StrictInt = Field(default=0, ge=0, le=1000)
    objects_created: StrictInt = Field(default=0, ge=0)
    proofs_added: StrictInt = Field(default=0, ge=0)
    memberships_added: StrictInt = Field(default=0, ge=0)
    relations_added: StrictInt = Field(default=0, ge=0)
    rejected: StrictInt = Field(default=0, ge=0)
    unresolved: StrictInt = Field(default=0, ge=0)
    next_event_cursor: str | None = Field(default=None, max_length=1024)
    incomplete: bool = False


STRUCTURAL_TYPES = frozenset({ObjectType.OWNER, ObjectType.DOMAIN, ObjectType.TOPIC, ObjectType.SESSION})


def bounded(value, minimum, maximum, code="object_map_bound_invalid"):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ObjectMapError(code)
    return value
