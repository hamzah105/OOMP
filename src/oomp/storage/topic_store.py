"""Scoped, immutable single-parent topic projection over canonical memories."""
from __future__ import annotations

import sqlite3
from collections import deque
from datetime import datetime
from pydantic import TypeAdapter

from oomp.domain.graph import TopicMembership, TopicRecord, TopicTree, TopicTreeNode
from oomp.domain.models import AuthorizedScope, Identifier, UtcDateTime, _nonblank
from .errors import GraphLimitError, MemoryNotFoundError, TopicConflictError, TopicNotFoundError
from .graph_store import SQLiteGraphStore
from .sqlite import _authorized, _translate_sqlite_errors

_ID = TypeAdapter(Identifier)
_TIME = TypeAdapter(UtcDateTime)


class SQLiteTopicStore(SQLiteGraphStore):
    """Topic parenthood is fixed at creation; membership never copies a memory."""

    @staticmethod
    def _read_topic(row: sqlite3.Row) -> TopicRecord:
        return TopicRecord(
            topic_id=row["topic_id"], tenant_id=row["tenant_id"],
            namespace=row["namespace"], name=row["name"], parent_id=row["parent_id"],
            recorded_at=_TIME.validate_python(row["recorded_at"]),
        )

    @staticmethod
    def _topic_row(
        connection: sqlite3.Connection, scope: AuthorizedScope, topic_id: str
    ) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT * FROM topics WHERE tenant_id=? AND namespace=? AND topic_id=?",
            (scope.tenant_id, scope.namespace, topic_id),
        ).fetchone()

    @_translate_sqlite_errors
    def create_topic(
        self, scope: AuthorizedScope, topic_id: str, name: str,
        parent_id: str | None = None,
    ) -> TopicRecord:
        authorized = _authorized(scope)
        identifier = _ID.validate_python(topic_id)
        parent = _ID.validate_python(parent_id) if parent_id is not None else None
        if not isinstance(name, str) or len(name) > 512:
            raise ValueError("topic name must be text up to 512 characters")
        _nonblank(name)
        if parent == identifier:
            raise TopicConflictError("a topic cannot parent itself")
        with self._graph_transaction() as connection:
            existing = self._topic_row(connection, authorized, identifier)
            if existing is not None:
                if existing["name"] != name or existing["parent_id"] != parent:
                    raise TopicConflictError("topic identity has immutable name and parent")
                return self._read_topic(existing)
            if parent is not None and self._topic_row(connection, authorized, parent) is None:
                raise TopicNotFoundError("parent topic is missing from authorized scope")
            connection.execute(
                """INSERT INTO topics
                   (tenant_id, namespace, topic_id, name, parent_id, recorded_at)
                   VALUES (?, ?, ?, ?, ?, oomp_recorded_at())""",
                (authorized.tenant_id, authorized.namespace, identifier, name, parent),
            )
            result = self._topic_row(connection, authorized, identifier)
            assert result is not None
            return self._read_topic(result)

    @_translate_sqlite_errors
    def get_topic(self, scope: AuthorizedScope, topic_id: str) -> TopicRecord | None:
        authorized = _authorized(scope)
        identifier = _ID.validate_python(topic_id)
        with self._graph_read() as connection:
            row = self._topic_row(connection, authorized, identifier)
            return None if row is None else self._read_topic(row)

    @_translate_sqlite_errors
    def list_children(
        self, scope: AuthorizedScope, topic_id: str, *, limit: int = 100
    ) -> tuple[TopicRecord, ...]:
        authorized = _authorized(scope)
        identifier = _ID.validate_python(topic_id)
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("child limit must be an integer from 1 to 1000")
        with self._graph_read() as connection:
            if self._topic_row(connection, authorized, identifier) is None:
                raise TopicNotFoundError("topic is missing from authorized scope")
            rows = connection.execute(
                """SELECT * FROM topics WHERE tenant_id=? AND namespace=? AND parent_id=?
                   ORDER BY topic_id LIMIT ?""",
                (authorized.tenant_id, authorized.namespace, identifier, limit + 1),
            ).fetchall()
            if len(rows) > limit:
                raise GraphLimitError("topic children exceed complete bound")
            return tuple(self._read_topic(row) for row in rows)

    @_translate_sqlite_errors
    def assign_memory(
        self, scope: AuthorizedScope, topic_id: str, memory_id: str
    ) -> TopicMembership:
        authorized = _authorized(scope)
        topic = _ID.validate_python(topic_id)
        memory = _ID.validate_python(memory_id)
        with self._graph_transaction() as connection:
            if self._topic_row(connection, authorized, topic) is None:
                raise TopicNotFoundError("topic is missing from authorized scope")
            if not self._exists_memory(connection, authorized, memory):
                raise MemoryNotFoundError("topic memory is missing from authorized scope")
            connection.execute(
                """INSERT OR IGNORE INTO topic_memberships
                   (tenant_id, namespace, topic_id, memory_id, recorded_at)
                   VALUES (?, ?, ?, ?, oomp_recorded_at())""",
                (authorized.tenant_id, authorized.namespace, topic, memory),
            )
            row = connection.execute(
                """SELECT recorded_at FROM topic_memberships
                   WHERE tenant_id=? AND namespace=? AND topic_id=? AND memory_id=?""",
                (authorized.tenant_id, authorized.namespace, topic, memory),
            ).fetchone()
            assert row is not None
            return TopicMembership(
                topic_id=topic, memory_id=memory,
                recorded_at=_TIME.validate_python(row["recorded_at"]),
            )

    @_translate_sqlite_errors
    def memberships_for_memory(
        self, scope: AuthorizedScope, memory_id: str, *, limit: int = 1000
    ) -> tuple[TopicMembership, ...]:
        authorized = _authorized(scope)
        memory = _ID.validate_python(memory_id)
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("membership limit must be an integer from 1 to 1000")
        with self._graph_read() as connection:
            if not self._exists_memory(connection, authorized, memory):
                raise MemoryNotFoundError("topic memory is missing from authorized scope")
            rows = connection.execute(
                """SELECT topic_id, recorded_at FROM topic_memberships
                   WHERE tenant_id=? AND namespace=? AND memory_id=?
                   ORDER BY topic_id LIMIT ?""",
                (authorized.tenant_id, authorized.namespace, memory, limit + 1),
            ).fetchall()
            if len(rows) > limit:
                raise GraphLimitError("topic memberships exceed complete bound")
            return tuple(TopicMembership(
                topic_id=row["topic_id"], memory_id=memory,
                recorded_at=_TIME.validate_python(row["recorded_at"]),
            ) for row in rows)
    @_translate_sqlite_errors
    def topic_tree(
        self, scope: AuthorizedScope, topic_id: str, *, max_depth: int = 3,
        max_nodes: int = 100, max_memberships: int = 1000,
    ) -> TopicTree:
        authorized = _authorized(scope)
        root = _ID.validate_python(topic_id)
        if type(max_depth) is not int or not 0 <= max_depth <= 10:
            raise ValueError("max_depth must be an integer from 0 to 10")
        if type(max_nodes) is not int or not 1 <= max_nodes <= 500:
            raise ValueError("max_nodes must be an integer from 1 to 500")
        if type(max_memberships) is not int or not 0 <= max_memberships <= 1000:
            raise ValueError("max_memberships must be an integer from 0 to 1000")
        with self._graph_read() as connection:
            if self._topic_row(connection, authorized, root) is None:
                raise TopicNotFoundError("topic is missing from authorized scope")
            frontier = deque([(root, 0)])
            visited: set[str] = set()
            result: list[TopicTreeNode] = []
            used_memberships = 0
            truncated = False
            while frontier:
                current, depth = frontier.popleft()
                if current in visited:
                    raise TopicConflictError("topic parent cycle detected in stored data")
                visited.add(current)
                row = self._topic_row(connection, authorized, current)
                if row is None:
                    raise TopicConflictError("stored topic parent is missing")
                remaining = max_memberships - used_memberships
                memberships = connection.execute(
                    """SELECT memory_id FROM topic_memberships
                       WHERE tenant_id=? AND namespace=? AND topic_id=?
                       ORDER BY memory_id LIMIT ?""",
                    (authorized.tenant_id, authorized.namespace, current, remaining + 1),
                ).fetchall()
                if len(memberships) > remaining:
                    truncated = True
                    memberships = memberships[:remaining]
                memory_ids = tuple(item[0] for item in memberships)
                used_memberships += len(memory_ids)
                result.append(TopicTreeNode(
                    topic=self._read_topic(row), depth=depth, memory_ids=memory_ids
                ))
                if depth >= max_depth:
                    if connection.execute(
                        "SELECT 1 FROM topics WHERE tenant_id=? AND namespace=? AND parent_id=? LIMIT 1",
                        (authorized.tenant_id, authorized.namespace, current),
                    ).fetchone() is not None:
                        truncated = True
                    continue
                child_rows = connection.execute(
                    """SELECT topic_id FROM topics WHERE tenant_id=? AND namespace=? AND parent_id=?
                       ORDER BY topic_id LIMIT 501""",
                    (authorized.tenant_id, authorized.namespace, current),
                ).fetchall()
                if len(child_rows) > 500:
                    raise GraphLimitError("topic fanout exceeds 500")
                for child in child_rows:
                    if len(result) + len(frontier) >= max_nodes:
                        truncated = True
                        continue
                    frontier.append((child[0], depth + 1))
            return TopicTree(
                root_topic_id=root, nodes=tuple(result), truncated=truncated
            )