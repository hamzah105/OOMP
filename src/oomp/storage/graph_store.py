"""Scoped, evidence-backed SQLite memory graph and temporal inspection."""
from __future__ import annotations

import hashlib
import sqlite3
from collections import deque
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from typing import Iterator, Sequence

from pydantic import TypeAdapter, ValidationError

from oomp.domain.enums import MemoryStatus, RelationshipType
from oomp.domain.graph import (
    EdgeCursor, EdgeEvidence, EdgePage, EdgeRecord, GraphHistory, MemoryState,
    TemporalQuery, TraversalResult,
)
from oomp.domain.graph_policy import ConflictProposal, propose_conflict
from oomp.domain.models import AuthorizedScope, Identifier, MemoryEdge, UtcDateTime
from .errors import (
    GraphConflictError, GraphLimitError, MemoryNotFoundError,
    ProvenanceMismatchError, SchemaUpgradeRequiredError, ScopeMismatchError,
    StoredGraphCorruptionError,
)
from .memory_store import SQLiteMemoryStore, _event_in_scope
from .migrations import user_version
from .sqlite import _authorized, _canonical_json, _timestamp, _translate_sqlite_errors

_ID = TypeAdapter(Identifier)
_TIME = TypeAdapter(UtcDateTime)
_MAX_EVIDENCE = 1000
_MAX_RESULT_EVIDENCE = 10000
_PROTECTED = {RelationshipType.CONTRADICTS, RelationshipType.SUPERSEDES}


def _edge_key(edge: MemoryEdge) -> str:
    payload = (
        edge.tenant_id, edge.namespace, edge.source_node_id, edge.target_node_id,
        edge.relationship_type.value,
        _timestamp(edge.valid_from) if edge.valid_from else None,
        _timestamp(edge.valid_until) if edge.valid_until else None,
    )
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _edge_fingerprint(edge: MemoryEdge) -> str:
    payload = edge.model_dump(
        mode="json", exclude={"edge_id", "source_event_ids", "created_at"}
    )
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _valid_at(start: datetime | None, end: datetime | None, instant: datetime | None) -> bool | None:
    if instant is None:
        return None
    if start is not None and instant < start:
        return False
    if end is not None and instant >= end:
        return False
    if start is None or end is None:
        return None
    return True


def _source_retracted(
    connection: sqlite3.Connection, scope: AuthorizedScope,
    memory_id: str, event_id: str, known_at: datetime | None = None,
) -> bool:
    if user_version(connection) < 5:
        return False
    sql = """SELECT 1 FROM mind_retractions
             WHERE tenant_id=? AND namespace=? AND memory_id=? AND event_id=?"""
    args: list[object] = [scope.tenant_id, scope.namespace, memory_id, event_id]
    if known_at is not None:
        sql += " AND recorded_at<=?"
        args.append(_timestamp(known_at))
    sql += " LIMIT 1"
    if connection.execute(sql, args).fetchone() is not None:
        return True
    from oomp.understanding.episodes import source_retracted, source_acquired
    return source_retracted(connection, scope, event_id, known_at) and source_acquired(
        connection, scope, event_id, known_at,
    )


def _edge_endorsed(
    connection: sqlite3.Connection, scope: AuthorizedScope,
    record: EdgeRecord, known_at: datetime | None = None,
) -> bool:
    if user_version(connection) < 5:
        return True
    edge = record.edge

    def linked_and_endorsed(memory_id: str, event_id: str) -> bool:
        linked = connection.execute(
            """SELECT 1 FROM memory_sources WHERE tenant_id=? AND namespace=?
                 AND memory_id=? AND event_id=?""",
            (scope.tenant_id, scope.namespace, memory_id, event_id),
        ).fetchone()
        return linked is not None and not _source_retracted(
            connection, scope, memory_id, event_id, known_at,
        )

    def has_endorsed_source(memory_id: str) -> bool:
        rows = connection.execute(
            """SELECT event_id FROM memory_sources
               WHERE tenant_id=? AND namespace=? AND memory_id=? LIMIT ?""",
            (scope.tenant_id, scope.namespace, memory_id, _MAX_EVIDENCE + 1),
        ).fetchall()
        if len(rows) > _MAX_EVIDENCE:
            raise GraphLimitError("endorsement evidence exceeds complete bound")
        return any(not _source_retracted(connection, scope, memory_id, row["event_id"], known_at) for row in rows)

    ids = edge.source_event_ids
    if edge.relationship_type is RelationshipType.SUPERSEDES:
        return (
            len(ids) == 1
            and linked_and_endorsed(edge.source_node_id, ids[0])
            and has_endorsed_source(edge.target_node_id)
        )
    if edge.relationship_type is RelationshipType.CONTRADICTS:
        return (
            len(ids) == 2
            and linked_and_endorsed(edge.source_node_id, ids[0])
            and linked_and_endorsed(edge.target_node_id, ids[1])
        )
    for event_id in ids:
        links = connection.execute(
            """SELECT memory_id FROM memory_sources
               WHERE tenant_id=? AND namespace=? AND event_id=?
                 AND memory_id IN (?,?)""",
            (scope.tenant_id, scope.namespace, event_id,
             edge.source_node_id, edge.target_node_id),
        ).fetchall()
        if links and not any(
            linked_and_endorsed(row["memory_id"], event_id) for row in links
        ):
            return False
    return True


class SQLiteGraphStore(SQLiteMemoryStore):
    """Immutable edge assertions over existing canonical memories."""

    @staticmethod
    def _require_v3(connection: sqlite3.Connection) -> None:
        SQLiteMemoryStore._require_v2(connection)
        if user_version(connection) < 3:
            raise SchemaUpgradeRequiredError("graph storage requires explicit schema version 3 initialization")

    @contextmanager
    def _graph_transaction(self) -> Iterator[sqlite3.Connection]:
        with closing(self._connect("rw")) as connection:
            self._require_v3(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.execute("COMMIT")
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    @contextmanager
    def _graph_read(self) -> Iterator[sqlite3.Connection]:
        with closing(self._connect("ro")) as connection:
            connection.execute("BEGIN")
            try:
                self._require_v3(connection)
                yield connection
            finally:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")

    @staticmethod
    def _validated_edge(edge: MemoryEdge) -> MemoryEdge:
        if not isinstance(edge, MemoryEdge):
            raise TypeError("a MemoryEdge is required")
        result = MemoryEdge.model_validate(edge.model_dump(mode="json"))
        if result.status is not MemoryStatus.ACTIVE:
            raise GraphConflictError("new edge assertions must be active")
        if len(result.source_event_ids) != len(set(result.source_event_ids)):
            raise ProvenanceMismatchError("edge source event IDs must be distinct")
        if len(result.source_event_ids) > _MAX_EVIDENCE:
            raise GraphLimitError("edge evidence limit exceeded")
        return result

    @staticmethod
    def _read_edge(
        connection: sqlite3.Connection, scope: AuthorizedScope, row: sqlite3.Row,
        known_at: datetime | None = None,
    ) -> EdgeRecord | None:
        try:
            sql = """SELECT event_id, ordinal, recorded_at FROM edge_evidence
                     WHERE tenant_id=? AND namespace=? AND edge_id=?"""
            values: list[object] = [scope.tenant_id, scope.namespace, row["edge_id"]]
            if known_at is not None:
                sql += " AND recorded_at<=?"
                values.append(_timestamp(known_at))
            sql += " ORDER BY ordinal LIMIT 1001"
            links = connection.execute(sql, values).fetchall()
            if len(links) > _MAX_EVIDENCE:
                raise ValueError("edge evidence limit exceeded")
            if not links:
                if known_at is None:
                    raise ValueError("stored edge has no evidence")
                return None
            evidence = tuple(
                EdgeEvidence(
                    event_id=link["event_id"],
                    source_reference=_event_in_scope(connection, scope, link["event_id"]).source_reference,
                    recorded_at=_TIME.validate_python(link["recorded_at"]),
                )
                for link in links
            )
            if known_at is None and [link["ordinal"] for link in links] != list(range(len(links))):
                raise ValueError("edge evidence order invalid")
            edge = MemoryEdge.model_validate({
                "edge_id": row["edge_id"], "tenant_id": row["tenant_id"],
                "namespace": row["namespace"], "source_node_id": row["source_node_id"],
                "target_node_id": row["target_node_id"],
                "relationship_type": row["relationship_type"],
                "source_event_ids": tuple(item.event_id for item in evidence),
                "confidence": row["confidence"], "created_at": row["created_at"],
                "valid_from": row["valid_from"], "valid_until": row["valid_until"],
                "status": row["status"],
            })
            if _edge_key(edge) != row["logical_key"] or _edge_fingerprint(edge) != row["payload_fingerprint"]:
                raise ValueError("edge identity mismatch")
            for field in ("created_at", "recorded_at", "valid_from", "valid_until"):
                value = getattr(edge, field) if field != "recorded_at" else _TIME.validate_python(row[field])
                if value is not None and _timestamp(value) != row[field]:
                    raise ValueError("noncanonical edge timestamp")
            return EdgeRecord(
                edge=edge, recorded_at=_TIME.validate_python(row["recorded_at"]),
                recorded_by=row["recorded_by"], evidence=evidence,
                reason=row["reason"], policy_version=row["policy_version"],
            )
        except (ValueError, TypeError, KeyError, ValidationError, ProvenanceMismatchError):
            raise StoredGraphCorruptionError("stored edge failed validation") from None

    @staticmethod
    def _exists_memory(connection: sqlite3.Connection, scope: AuthorizedScope, memory_id: str) -> bool:
        return connection.execute(
            "SELECT 1 FROM memories WHERE tenant_id=? AND namespace=? AND memory_id=?",
            (scope.tenant_id, scope.namespace, memory_id),
        ).fetchone() is not None

    @staticmethod
    def _check_cycle(
        connection: sqlite3.Connection, scope: AuthorizedScope, edge: MemoryEdge
    ) -> None:
        if edge.relationship_type not in {RelationshipType.PART_OF, RelationshipType.SUPERSEDES}:
            return
        if edge.source_node_id == edge.target_node_id:
            raise GraphConflictError("hierarchy or supersession cannot link a node to itself")
        visited = {edge.target_node_id}
        frontier = deque([edge.target_node_id])
        work = 0
        while frontier:
            current = frontier.popleft()
            remaining = 10000 - work
            if remaining <= 0:
                raise GraphLimitError("hierarchy cycle check work budget exceeded")
            rows = connection.execute(
                """SELECT target_node_id FROM memory_edges
                   WHERE tenant_id=? AND namespace=? AND relationship_type=?
                     AND source_node_id=? ORDER BY target_node_id LIMIT ?""",
                (scope.tenant_id, scope.namespace, edge.relationship_type.value,
                 current, min(remaining + 1, 1001)),
            ).fetchall()
            if len(rows) > min(remaining, 1000):
                raise GraphLimitError("hierarchy cycle check fanout exceeded")
            work += len(rows)
            for row in rows:
                target = row[0]
                if target == edge.source_node_id:
                    raise GraphConflictError("hierarchy or supersession cycle is forbidden")
                if target not in visited:
                    if len(visited) >= 1000:
                        raise GraphLimitError("hierarchy cycle check exceeded 1000 nodes")
                    visited.add(target)
                    frontier.append(target)
    def _add_in_transaction(
        self, connection: sqlite3.Connection, scope: AuthorizedScope, edge: MemoryEdge,
        *, protected: bool = False, reason: str | None = None,
        policy_version: str | None = None,
    ) -> EdgeRecord:
        if (edge.tenant_id, edge.namespace) != (scope.tenant_id, scope.namespace):
            raise ScopeMismatchError("edge scope differs from authorized scope")
        if edge.relationship_type in _PROTECTED and not protected:
            raise GraphConflictError("protected relations require validated resolution")
        if not self._exists_memory(connection, scope, edge.source_node_id):
            raise MemoryNotFoundError("edge source memory is missing")
        if not self._exists_memory(connection, scope, edge.target_node_id):
            raise MemoryNotFoundError("edge target memory is missing")
        for event_id in edge.source_event_ids:
            _event_in_scope(connection, scope, event_id)
        observed = connection.execute("SELECT oomp_recorded_at()").fetchone()[0]
        key = _edge_key(edge)
        fingerprint = _edge_fingerprint(edge)
        by_id = connection.execute(
            "SELECT * FROM memory_edges WHERE tenant_id=? AND namespace=? AND edge_id=?",
            (scope.tenant_id, scope.namespace, edge.edge_id),
        ).fetchone()
        by_key = connection.execute(
            "SELECT * FROM memory_edges WHERE tenant_id=? AND namespace=? AND logical_key=?",
            (scope.tenant_id, scope.namespace, key),
        ).fetchone()
        if by_id is not None and by_key is not None and by_id["edge_id"] != by_key["edge_id"]:
            raise GraphConflictError("edge ID and logical relation identify different records")
        existing = by_id or by_key
        if existing is not None:
            if existing["payload_fingerprint"] != fingerprint:
                raise GraphConflictError("edge identity conflicts with stored relation")
            if existing["reason"] != reason or existing["policy_version"] != policy_version:
                raise GraphConflictError("edge audit identity conflicts with stored relation")
            stored = self._read_edge(connection, scope, existing)
            if stored is None:
                raise StoredGraphCorruptionError("stored edge has no evidence")
            known = set(stored.edge.source_event_ids)
            ordinal = len(known)
            edge_id = stored.edge.edge_id
        else:
            self._check_cycle(connection, scope, edge)
            connection.execute(
                """INSERT INTO memory_edges (
                    tenant_id, namespace, edge_id, source_node_id, target_node_id,
                    relationship_type, logical_key, confidence, created_at, recorded_at,
                    recorded_by, valid_from, valid_until, status, reason, policy_version,
                    payload_fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope.tenant_id, scope.namespace, edge.edge_id, edge.source_node_id,
                    edge.target_node_id, edge.relationship_type.value, key,
                    edge.confidence, _timestamp(edge.created_at), observed, scope.principal_id,
                    _timestamp(edge.valid_from) if edge.valid_from else None,
                    _timestamp(edge.valid_until) if edge.valid_until else None,
                    edge.status.value, reason, policy_version, fingerprint,
                ),
            )
            known = set()
            ordinal = 0
            edge_id = edge.edge_id
        if len(known | set(edge.source_event_ids)) > _MAX_EVIDENCE:
            raise GraphLimitError("edge evidence limit exceeded")
        for event_id in edge.source_event_ids:
            if event_id in known:
                continue
            connection.execute(
                """INSERT INTO edge_evidence
                   (tenant_id, namespace, edge_id, event_id, ordinal, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (scope.tenant_id, scope.namespace, edge_id, event_id, ordinal, observed),
            )
            known.add(event_id)
            ordinal += 1
        row = connection.execute(
            "SELECT * FROM memory_edges WHERE tenant_id=? AND namespace=? AND edge_id=?",
            (scope.tenant_id, scope.namespace, edge_id),
        ).fetchone()
        assert row is not None
        result = self._read_edge(connection, scope, row)
        assert result is not None
        return result

    @_translate_sqlite_errors
    def add_edge(self, scope: AuthorizedScope, edge: MemoryEdge) -> EdgeRecord:
        authorized = _authorized(scope)
        incoming = self._validated_edge(edge)
        with self._graph_transaction() as connection:
            return self._add_in_transaction(connection, authorized, incoming)

    def put_edge(self, scope: AuthorizedScope, edge: MemoryEdge) -> None:
        self.add_edge(scope, edge)

    @_translate_sqlite_errors
    def get_edge(self, scope: AuthorizedScope, edge_id: str) -> EdgeRecord | None:
        authorized = _authorized(scope)
        identifier = _ID.validate_python(edge_id)
        with self._graph_read() as connection:
            row = connection.execute(
                "SELECT * FROM memory_edges WHERE tenant_id=? AND namespace=? AND edge_id=?",
                (authorized.tenant_id, authorized.namespace, identifier),
            ).fetchone()
            return None if row is None else self._read_edge(connection, authorized, row)

    def _list_in_connection(
        self, connection: sqlite3.Connection, scope: AuthorizedScope, *,
        source_node_id: str | None = None, target_node_id: str | None = None,
        relationship_type: RelationshipType | None = None, limit: int = 100,
        after: EdgeCursor | None = None, known_at: datetime | None = None,
    ) -> EdgePage:
        sql = "SELECT * FROM memory_edges WHERE tenant_id=? AND namespace=?"
        values: list[object] = [scope.tenant_id, scope.namespace]
        for column, value in (("source_node_id", source_node_id), ("target_node_id", target_node_id)):
            if value is not None:
                sql += f" AND {column}=?"
                values.append(value)
        if relationship_type is not None:
            sql += " AND relationship_type=?"
            values.append(relationship_type.value)
        if known_at is not None:
            sql += """ AND recorded_at<=? AND EXISTS (
                SELECT 1 FROM edge_evidence ev
                WHERE ev.tenant_id=memory_edges.tenant_id AND ev.namespace=memory_edges.namespace
                  AND ev.edge_id=memory_edges.edge_id AND ev.recorded_at<=?)"""
            values.extend((_timestamp(known_at), _timestamp(known_at)))
        if after is not None:
            sql += " AND (recorded_at, edge_id) > (?, ?)"
            values.extend((_timestamp(after.recorded_at), after.edge_id))
        sql += " ORDER BY recorded_at, edge_id LIMIT ?"
        values.append(limit + 1)
        rows = connection.execute(sql, values).fetchall()
        collected: list[EdgeRecord] = []
        proof_count = 0
        for row in rows[:limit]:
            record = self._read_edge(connection, scope, row, known_at)
            if record is None:
                continue
            proof_count += len(record.evidence)
            if proof_count > _MAX_RESULT_EVIDENCE:
                raise GraphLimitError("graph result evidence budget exceeded")
            collected.append(record)
        edges = tuple(collected)
        next_cursor = None
        if len(rows) > limit:
            row = rows[limit - 1]
            next_cursor = EdgeCursor(
                tenant_id=scope.tenant_id, namespace=scope.namespace,
                recorded_at=_TIME.validate_python(row["recorded_at"]), edge_id=row["edge_id"],
            )
        return EdgePage(edges=edges, next_cursor=next_cursor)

    @_translate_sqlite_errors
    def list_edges(
        self, scope: AuthorizedScope, *, source_node_id: str | None = None,
        target_node_id: str | None = None,
        relationship_type: RelationshipType | None = None,
        limit: int = 100, after: EdgeCursor | None = None,
    ) -> EdgePage:
        authorized = _authorized(scope)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("edge page limit must be an integer from 1 to 100")
        source = _ID.validate_python(source_node_id) if source_node_id is not None else None
        target = _ID.validate_python(target_node_id) if target_node_id is not None else None
        relation = RelationshipType(relationship_type) if relationship_type is not None else None
        cursor = None
        if after is not None:
            if not isinstance(after, EdgeCursor):
                raise TypeError("an EdgeCursor is required")
            cursor = EdgeCursor.model_validate(after.model_dump(mode="json"))
            if (cursor.tenant_id, cursor.namespace) != (authorized.tenant_id, authorized.namespace):
                raise ScopeMismatchError("edge cursor scope differs from authorized scope")
        with self._graph_read() as connection:
            return self._list_in_connection(
                connection, authorized, source_node_id=source, target_node_id=target,
                relationship_type=relation, limit=limit, after=cursor,
            )
    def _neighbors_in_connection(
        self, connection: sqlite3.Connection, scope: AuthorizedScope, node_id: str, *,
        direction: str, allowed_relationships: tuple[RelationshipType, ...] | None,
        limit: int, known_at: datetime | None = None,
    ) -> tuple[EdgeRecord, ...]:
        predicate = {
            "outgoing": "source_node_id=?", "incoming": "target_node_id=?",
            "both": "(source_node_id=? OR target_node_id=?)",
        }[direction]
        sql = f"SELECT * FROM memory_edges WHERE tenant_id=? AND namespace=? AND {predicate}"
        values: list[object] = [scope.tenant_id, scope.namespace, node_id]
        if direction == "both":
            values.append(node_id)
        if allowed_relationships is not None:
            if not allowed_relationships:
                return ()
            sql += " AND relationship_type IN (" + ",".join("?" for _ in allowed_relationships) + ")"
            values.extend(item.value for item in allowed_relationships)
        if known_at is not None:
            sql += """ AND recorded_at<=? AND EXISTS (
                SELECT 1 FROM edge_evidence ev
                WHERE ev.tenant_id=memory_edges.tenant_id AND ev.namespace=memory_edges.namespace
                  AND ev.edge_id=memory_edges.edge_id AND ev.recorded_at<=?)"""
            values.extend((_timestamp(known_at), _timestamp(known_at)))
        sql += " ORDER BY recorded_at, edge_id LIMIT ?"
        values.append(limit + 1)
        rows = connection.execute(sql, values).fetchall()
        if len(rows) > limit:
            raise GraphLimitError("graph fanout exceeds the requested complete bound")
        collected: list[EdgeRecord] = []
        proof_count = 0
        for row in rows:
            record = self._read_edge(connection, scope, row, known_at)
            if record is None:
                continue
            proof_count += len(record.evidence)
            if proof_count > _MAX_RESULT_EVIDENCE:
                raise GraphLimitError("graph result evidence budget exceeded")
            collected.append(record)
        return tuple(collected)

    @_translate_sqlite_errors
    def neighbors(
        self, scope: AuthorizedScope, node_id: str, *, direction: str = "both",
        allowed_relationships: tuple[RelationshipType, ...] | None = None,
        limit: int = 100,
    ) -> tuple[EdgeRecord, ...]:
        authorized = _authorized(scope)
        identifier = _ID.validate_python(node_id)
        if direction not in {"incoming", "outgoing", "both"}:
            raise ValueError("direction must be incoming, outgoing, or both")
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("neighbor limit must be an integer from 1 to 1000")
        relations = None if allowed_relationships is None else tuple(RelationshipType(item) for item in allowed_relationships)
        with self._graph_read() as connection:
            if not self._exists_memory(connection, authorized, identifier):
                raise MemoryNotFoundError("graph memory is missing")
            return self._neighbors_in_connection(
                connection, authorized, identifier, direction=direction,
                allowed_relationships=relations, limit=limit,
            )

    def edges_for(self, scope: AuthorizedScope, node_id: str) -> Sequence[MemoryEdge]:
        return tuple(record.edge for record in self.neighbors(scope, node_id, limit=1000))

    @_translate_sqlite_errors
    def traverse(
        self, scope: AuthorizedScope, node_id: str, *, max_depth: int = 2,
        max_nodes: int = 100,
        allowed_relationships: tuple[RelationshipType, ...] | None = None,
        query: TemporalQuery | None = None,
    ) -> TraversalResult:
        authorized = _authorized(scope)
        identifier = _ID.validate_python(node_id)
        if type(max_depth) is not int or not 0 <= max_depth <= 10:
            raise ValueError("max_depth must be an integer from 0 to 10")
        if type(max_nodes) is not int or not 1 <= max_nodes <= 500:
            raise ValueError("max_nodes must be an integer from 1 to 500")
        relations = None if allowed_relationships is None else tuple(RelationshipType(item) for item in allowed_relationships)
        temporal = None
        if query is not None:
            if not isinstance(query, TemporalQuery):
                raise TypeError("a TemporalQuery is required")
            temporal = TemporalQuery.model_validate(query.model_dump(mode="json"))
        with self._graph_read() as connection:
            return self._traverse_in_connection(
                connection, authorized, identifier, max_depth=max_depth,
                max_nodes=max_nodes, allowed_relationships=relations, query=temporal,
            )

    def _traverse_in_connection(
        self, connection: sqlite3.Connection, scope: AuthorizedScope, identifier: str, *,
        max_depth: int, max_nodes: int,
        allowed_relationships: tuple[RelationshipType, ...] | None = None,
        query: TemporalQuery | None = None, max_edges: int = 2000,
        max_work: int = 10000, max_proof: int = _MAX_RESULT_EVIDENCE,
    ) -> TraversalResult:
        """Existing structural traversal, optionally projected in the caller's snapshot."""
        if not self._exists_memory(connection, scope, identifier):
            raise MemoryNotFoundError("graph memory is missing")
        eligibility: dict[str, bool] = {}

        def eligible(node_id: str) -> bool:
            if query is None:
                return True
            if node_id not in eligibility:
                state = self._memory_state_in_connection(connection, scope, node_id, query)
                eligibility[node_id] = (
                    state.known is True and bool(state.evidence) and state.valid is not False
                    and state.effective_status is not MemoryStatus.RETRACTED
                )
            return eligibility[node_id]

        def visible(record: EdgeRecord) -> bool:
            if query is None:
                return True
            return (
                _edge_endorsed(connection, scope, record, query.known_at)
                and _valid_at(record.edge.valid_from, record.edge.valid_until, query.valid_at) is not False
            )

        if not eligible(identifier):
            raise MemoryNotFoundError("graph memory is unavailable at the requested time")
        visited = {identifier}
        ordered = [identifier]
        edge_records: dict[str, EdgeRecord] = {}
        frontier = deque([(identifier, 0)])
        work = proof_count = 0
        truncated = False
        while frontier:
            current, depth = frontier.popleft()
            if depth >= max_depth and query is None:
                rows = connection.execute(
                    """SELECT source_node_id, target_node_id FROM memory_edges
                       WHERE tenant_id=? AND namespace=?
                         AND (source_node_id=? OR target_node_id=?) LIMIT 1001""",
                    (scope.tenant_id, scope.namespace, current, current),
                ).fetchall()
                if len(rows) > 1000:
                    raise GraphLimitError("graph depth frontier fanout exceeded")
                if any((row[1] if row[0] == current else row[0]) not in visited for row in rows):
                    truncated = True
                continue
            remaining = max_work - work
            if remaining <= 0:
                raise GraphLimitError("graph traversal work budget exceeded")
            neighbors = self._neighbors_in_connection(
                connection, scope, current, direction="both",
                allowed_relationships=allowed_relationships,
                known_at=query.known_at if query else None,
                limit=min(1000, remaining),
            )
            work += len(neighbors)
            if work > max_work:
                raise GraphLimitError("graph traversal work budget exceeded")
            for record in neighbors:
                if not visible(record):
                    continue
                other = record.edge.target_node_id if record.edge.source_node_id == current else record.edge.source_node_id
                if not eligible(other):
                    continue
                if depth >= max_depth:
                    if other not in visited:
                        truncated = True
                    continue
                if other not in visited and len(visited) >= max_nodes:
                    truncated = True
                    continue
                if record.edge.edge_id not in edge_records:
                    proof_count += len(record.evidence)
                    if proof_count > max_proof:
                        raise GraphLimitError("graph traversal evidence budget exceeded")
                    edge_records[record.edge.edge_id] = record
                if len(edge_records) > max_edges:
                    raise GraphLimitError("graph traversal edge budget exceeded")
                if other in visited:
                    continue
                visited.add(other)
                ordered.append(other)
                frontier.append((other, depth + 1))
        return TraversalResult(
            start_node_id=identifier, node_ids=tuple(ordered),
            edges=tuple(edge_records.values()), truncated=truncated,
        )

    def _memory_state_in_connection(
        self, connection: sqlite3.Connection, scope: AuthorizedScope,
        memory_id: str, query: TemporalQuery,
    ) -> MemoryState:
        row = connection.execute(
            """SELECT m.*, r.recorded_at AS system_recorded_at FROM memories m
               JOIN memory_recordings r
                 ON r.tenant_id=m.tenant_id AND r.namespace=m.namespace AND r.memory_id=m.memory_id
               WHERE m.tenant_id=? AND m.namespace=? AND m.memory_id=?""",
            (scope.tenant_id, scope.namespace, memory_id),
        ).fetchone()
        if row is None:
            raise MemoryNotFoundError("memory is missing from authorized scope")
        start = _TIME.validate_python(row["valid_from"]) if row["valid_from"] else None
        end = _TIME.validate_python(row["valid_until"]) if row["valid_until"] else None
        recorded = _TIME.validate_python(row["system_recorded_at"]) if row["system_recorded_at"] else None
        history_start = _TIME.validate_python(
            connection.execute("SELECT history_start FROM graph_meta WHERE id=1").fetchone()[0]
        )
        legacy = recorded is None
        if query.known_at is None:
            known: bool | None = True
        elif legacy:
            known = True if query.known_at >= history_start else None
        else:
            known = recorded <= query.known_at
        evidence: list[EdgeEvidence] = []
        source_count = 0
        if known is True:
            sql = """SELECT s.event_id, r.recorded_at FROM memory_sources s
                     JOIN memory_source_recordings r
                       ON r.tenant_id=s.tenant_id AND r.namespace=s.namespace
                      AND r.memory_id=s.memory_id AND r.event_id=s.event_id
                     WHERE s.tenant_id=? AND s.namespace=? AND s.memory_id=?"""
            values: list[object] = [scope.tenant_id, scope.namespace, memory_id]
            if query.known_at is not None:
                sql += " AND (r.recorded_at<=? OR (r.recorded_at IS NULL AND ?<=?))"
                values.extend((_timestamp(query.known_at), _timestamp(history_start), _timestamp(query.known_at)))
            sql += " ORDER BY s.ordinal LIMIT 1001"
            rows = connection.execute(sql, values).fetchall()
            if len(rows) > _MAX_EVIDENCE:
                raise GraphLimitError("historical memory evidence limit exceeded")
            source_count = len(rows)
            for item in rows:
                if _source_retracted(
                    connection, scope, memory_id, item["event_id"], query.known_at,
                ):
                    continue
                source = _event_in_scope(connection, scope, item["event_id"])
                evidence.append(EdgeEvidence(
                    event_id=source.event_id, source_reference=source.source_reference,
                    recorded_at=_TIME.validate_python(item["recorded_at"]) if item["recorded_at"] else None,
                ))
        retracted_all = known is True and not evidence and source_count > 0
        if known is True and not evidence and not retracted_all:
            known = None
        incoming = ()
        if known is True and evidence:
            page = self._list_in_connection(
                connection, scope, target_node_id=memory_id,
                relationship_type=RelationshipType.SUPERSEDES,
                limit=100, known_at=query.known_at,
            )
            if page.next_cursor is not None:
                raise GraphLimitError("supersession history exceeds complete bound")
            incoming = tuple(
                record for record in page.edges
                if _edge_endorsed(connection, scope, record, query.known_at)
            )
            if len(evidence) + sum(len(item.evidence) for item in incoming) > _MAX_RESULT_EVIDENCE:
                raise GraphLimitError("historical state evidence budget exceeded")
        applicable = []
        uncertain_supersession = False
        for record in incoming:
            relation_valid = _valid_at(record.edge.valid_from, record.edge.valid_until, query.valid_at)
            if query.valid_at is None or relation_valid is True:
                applicable.append(record.edge.source_node_id)
            elif relation_valid is None:
                uncertain_supersession = True
        superseded = tuple(applicable)
        valid = _valid_at(start, end, query.valid_at) if known is True else None
        effective_status = (
            MemoryStatus.RETRACTED if retracted_all else
            None if known is not True or (uncertain_supersession and not superseded) else
            MemoryStatus.SUPERSEDED if superseded else MemoryStatus(row["status"])
        )
        return MemoryState(
            memory_id=memory_id, known=known, valid=valid,
            effective_status=effective_status, recorded_at=recorded,
            superseded_by=superseded,
            source_event_ids=tuple(item.event_id for item in evidence),
            evidence=tuple(evidence), legacy_recording_unknown=legacy,
        )

    @_translate_sqlite_errors
    def memory_state(
        self, scope: AuthorizedScope, memory_id: str,
        query: TemporalQuery = TemporalQuery(),
    ) -> MemoryState:
        authorized = _authorized(scope)
        identifier = _ID.validate_python(memory_id)
        if not isinstance(query, TemporalQuery):
            raise TypeError("a TemporalQuery is required")
        validated = TemporalQuery.model_validate(query.model_dump(mode="json"))
        with self._graph_read() as connection:
            return self._memory_state_in_connection(connection, authorized, identifier, validated)

    @_translate_sqlite_errors
    def history(
        self, scope: AuthorizedScope, node_id: str,
        query: TemporalQuery = TemporalQuery(),
    ) -> GraphHistory:
        authorized = _authorized(scope)
        identifier = _ID.validate_python(node_id)
        if not isinstance(query, TemporalQuery):
            raise TypeError("a TemporalQuery is required")
        validated = TemporalQuery.model_validate(query.model_dump(mode="json"))
        with self._graph_read() as connection:
            state = self._memory_state_in_connection(connection, authorized, identifier, validated)
            if state.known is not True:
                return GraphHistory(memory=state)
            incoming = self._list_in_connection(
                connection, authorized, target_node_id=identifier,
                limit=100, known_at=validated.known_at,
            )
            outgoing = self._list_in_connection(
                connection, authorized, source_node_id=identifier,
                limit=100, known_at=validated.known_at,
            )
            if incoming.next_cursor is not None or outgoing.next_cursor is not None:
                raise GraphLimitError("graph history exceeds complete bound")
            if (len(state.evidence) + sum(len(item.evidence) for item in incoming.edges)
                    + sum(len(item.evidence) for item in outgoing.edges)) > _MAX_RESULT_EVIDENCE:
                raise GraphLimitError("graph history evidence budget exceeded")
            return GraphHistory(
                memory=state, incoming_edges=incoming.edges, outgoing_edges=outgoing.edges
            )
    def _apply_resolution_in_transaction(
        self, connection: sqlite3.Connection, scope: AuthorizedScope,
        proposal: ConflictProposal,
    ) -> EdgeRecord:
        authorized = _authorized(scope)
        if not isinstance(proposal, ConflictProposal):
            raise TypeError("a ConflictProposal is required")
        incoming = ConflictProposal.model_validate(proposal.model_dump(mode="json"))
        if (incoming.tenant_id, incoming.namespace) != (authorized.tenant_id, authorized.namespace):
            raise ScopeMismatchError("proposal scope differs from authorized scope")
        source_row = connection.execute(
            "SELECT * FROM memories WHERE tenant_id=? AND namespace=? AND memory_id=?",
            (authorized.tenant_id, authorized.namespace, incoming.source_node_id),
        ).fetchone()
        target_row = connection.execute(
            "SELECT * FROM memories WHERE tenant_id=? AND namespace=? AND memory_id=?",
            (authorized.tenant_id, authorized.namespace, incoming.target_node_id),
        ).fetchone()
        if source_row is None or target_row is None:
            raise MemoryNotFoundError("resolution endpoint memory is missing")
        source = self._read_memory(connection, authorized, source_row)
        target = self._read_memory(connection, authorized, target_row)
        source_event = _event_in_scope(connection, authorized, incoming.source_event_ids[0])
        if _source_retracted(
            connection, authorized, source.memory_id, source_event.event_id,
        ):
            raise GraphConflictError("resolution source evidence was retracted")
        if source_event.event_id not in source.source_event_ids:
            raise ProvenanceMismatchError("resolution source event is not linked to memory")
        target_ids = (
            incoming.source_event_ids[1:] if incoming.relationship_type is RelationshipType.CONTRADICTS
            else target.source_event_ids
        )
        matched = False
        for target_id in target_ids:
            if target_id not in target.source_event_ids:
                continue
            if _source_retracted(
                connection, authorized, target.memory_id, target_id,
            ):
                continue
            target_event = _event_in_scope(connection, authorized, target_id)
            assessment = propose_conflict(
                authorized, source, target, source_event, target_event
            )
            if assessment.proposal == incoming:
                matched = True
                break
        if not matched:
            raise GraphConflictError("resolution is unsupported by current source evidence")
        edge = MemoryEdge(
            edge_id="edge-" + incoming.proposal_id,
            tenant_id=authorized.tenant_id, namespace=authorized.namespace,
            source_node_id=incoming.source_node_id,
            target_node_id=incoming.target_node_id,
            relationship_type=incoming.relationship_type,
            source_event_ids=incoming.source_event_ids,
            created_at=datetime.now(timezone.utc),
            valid_from=incoming.valid_from, valid_until=incoming.valid_until,
        )
        return self._add_in_transaction(
            connection, authorized, edge, protected=True,
            reason=incoming.reason, policy_version=incoming.policy_version,
        )
    @_translate_sqlite_errors
    def apply_resolution(
        self, scope: AuthorizedScope, proposal: ConflictProposal, *,
        confirm: bool = False,
    ) -> EdgeRecord:
        authorized = _authorized(scope)
        if confirm is not True:
            raise GraphConflictError("explicit confirmation is required")
        if not isinstance(proposal, ConflictProposal):
            raise TypeError("a ConflictProposal is required")
        incoming = ConflictProposal.model_validate(proposal.model_dump(mode="json"))
        if (incoming.tenant_id, incoming.namespace) != (authorized.tenant_id, authorized.namespace):
            raise ScopeMismatchError("proposal scope differs from authorized scope")
        with self._graph_transaction() as connection:
            return self._apply_resolution_in_transaction(connection, authorized, incoming)
