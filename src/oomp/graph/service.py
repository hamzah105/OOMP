"""Trusted local graph orchestration over scoped SQLite stores."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from os import PathLike
from typing import Sequence

from oomp.domain.enums import RelationshipType
from oomp.domain.graph import GraphHistory, TemporalQuery, TopicTree
from oomp.domain.graph_policy import ConflictAssessment, ConflictProposal, propose_conflict
from oomp.domain.models import AuthorizedScope, MemoryEdge
from oomp.storage.errors import MemoryNotFoundError, SourceEventMissingError
from oomp.storage.graph_store import SQLiteGraphStore
from oomp.storage.memory_store import SQLiteMemoryStore
from oomp.storage.sqlite import SQLiteEventStore
from oomp.storage.topic_store import SQLiteTopicStore


def _authorized(scope: AuthorizedScope) -> AuthorizedScope:
    if not isinstance(scope, AuthorizedScope):
        raise TypeError("an AuthorizedScope from a trusted caller is required")
    return AuthorizedScope.model_validate(scope.model_dump(mode="json"))


def _edge_id(
    scope: AuthorizedScope, source_id: str, target_id: str,
    relationship: RelationshipType,
    valid_from: datetime | None, valid_until: datetime | None,
) -> str:
    def timestamp(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("edge validity timestamps must include a UTC offset")
        return value.astimezone(timezone.utc).isoformat()

    payload = [
        scope.tenant_id, scope.namespace, source_id, target_id, relationship.value,
        timestamp(valid_from), timestamp(valid_until),
    ]
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return "edge-" + digest


class GraphService:
    """The service owns proposal checks; SQLite owns durable validation and execution."""

    def __init__(self, path: str | PathLike[str] | None = None) -> None:
        self.events = SQLiteEventStore(path)
        self.memories = SQLiteMemoryStore(path)
        self.graph = SQLiteGraphStore(path)
        self.topics = SQLiteTopicStore(path)

    def link(
        self, scope: AuthorizedScope, source_node_id: str, target_node_id: str,
        relationship_type: RelationshipType | str,
        source_event_ids: Sequence[str],
        *, valid_from: datetime | None = None, valid_until: datetime | None = None,
    ):
        """Write ordinary evidence-backed edges; governed types use resolve()."""
        authorized = _authorized(scope)
        relation = RelationshipType(relationship_type)
        if relation in {RelationshipType.CONTRADICTS, RelationshipType.SUPERSEDES}:
            raise ValueError("protected relationships require a confirmed conflict proposal")
        if not isinstance(source_event_ids, Sequence) or isinstance(source_event_ids, (str, bytes)):
            raise TypeError("source_event_ids must be a bounded sequence")
        if not 1 <= len(source_event_ids) <= 1000:
            raise ValueError("source_event_ids must contain 1 to 1000 events")
        evidence = tuple(source_event_ids)
        if not evidence:
            raise ValueError("at least one source event is required")
        edge = MemoryEdge(
            edge_id=_edge_id(
                authorized, source_node_id, target_node_id, relation,
                valid_from, valid_until,
            ),
            tenant_id=authorized.tenant_id, namespace=authorized.namespace,
            source_node_id=source_node_id, target_node_id=target_node_id,
            relationship_type=relation, source_event_ids=evidence,
            created_at=datetime.now(timezone.utc), valid_from=valid_from,
            valid_until=valid_until,
        )
        return self.graph.add_edge(authorized, edge)

    def propose_conflict(
        self, scope: AuthorizedScope, source_node_id: str, target_node_id: str,
        *, source_event_id: str | None = None, target_event_id: str | None = None,
    ) -> ConflictAssessment:
        """Read and compare selected original evidence; this never writes."""
        authorized = _authorized(scope)
        source = self.memories.get(authorized, source_node_id)
        target = self.memories.get(authorized, target_node_id)
        if source is None or target is None:
            raise MemoryNotFoundError("a proposed endpoint is missing from the authorized scope")
        if source_event_id is None:
            source_event_id = source.source_event_ids[0]
        if target_event_id is None:
            target_event_id = target.source_event_ids[0]
        if source_event_id not in source.source_event_ids or target_event_id not in target.source_event_ids:
            return ConflictAssessment(reason="insufficient structured evidence: selected source is not linked")
        source_event = self.events.get(authorized, source_event_id)
        target_event = self.events.get(authorized, target_event_id)
        if source_event is None or target_event is None:
            raise SourceEventMissingError("a proposed source event is missing from the authorized scope")
        return propose_conflict(authorized, source, target, source_event, target_event)

    def resolve(self, scope: AuthorizedScope, proposal: ConflictProposal, *, confirm: bool):
        """Revalidated, explicitly confirmed protected edge commit."""
        return self.graph.apply_resolution(_authorized(scope), proposal, confirm=confirm)

    def neighbors(
        self, scope: AuthorizedScope, node_id: str, *, direction: str = "both",
        allowed_relationships: tuple[RelationshipType, ...] | None = None,
        limit: int = 100,
    ):
        return self.graph.neighbors(
            _authorized(scope), node_id, direction=direction,
            allowed_relationships=allowed_relationships, limit=limit,
        )

    def history(
        self, scope: AuthorizedScope, node_id: str,
        *, valid_at: datetime | None = None, known_at: datetime | None = None,
    ) -> GraphHistory:
        return self.graph.history(
            _authorized(scope), node_id,
            TemporalQuery(valid_at=valid_at, known_at=known_at),
        )

    def topic_tree(
        self, scope: AuthorizedScope, topic_id: str, *,
        max_depth: int = 3, max_nodes: int = 100, max_memberships: int = 1000,
    ) -> TopicTree:
        return self.topics.topic_tree(
            _authorized(scope), topic_id, max_depth=max_depth,
            max_nodes=max_nodes, max_memberships=max_memberships,
        )
