"""File-backed, scoped, append-only SQLite source event store."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeVar

from pydantic import TypeAdapter, ValidationError

from oomp.domain.events import EventCursor, EventPage
from oomp.domain.models import AuthorizedScope, Identifier, MemoryEvent
from .config import database_path
from .errors import (
    DatabaseMissingError,
    DatabaseUninitializedError,
    ForeignDatabaseError,
    IdempotencyConflictError,
    ScopeMismatchError,
    StorageBusyError,
    StorageCorruptionError,
    StorageError,
    StorageUnavailableError,
    StoredEventCorruptionError,
    UnsupportedSchemaVersionError,
)
from .migrations import MIGRATIONS, SCHEMA_VERSION, is_empty_unowned_database, user_version, verify_v1


@dataclass(frozen=True)
class StorageStatus:
    path: Path
    exists: bool
    accessible: bool
    schema_version: int | None
    journal_mode: str | None
    ready: bool
    message: str


_EVENT_ID = TypeAdapter(Identifier)
_F = TypeVar("_F", bound=Callable[..., Any])


def _translate_sqlite_errors(method: _F) -> _F:
    @wraps(method)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            return method(*args, **kwargs)
        except sqlite3.Error as error:
            code = getattr(error, "sqlite_errorname", "")
            if code.startswith(("SQLITE_BUSY", "SQLITE_LOCKED")):
                raise StorageBusyError("SQLite event store is busy") from error
            if code.startswith(("SQLITE_CORRUPT", "SQLITE_NOTADB")):
                raise StorageCorruptionError("SQLite database file is invalid") from error
            raise StorageUnavailableError("SQLite event store operation failed") from error
        except OSError as error:
            raise StorageUnavailableError("SQLite database path is unavailable") from error

    return wrapped  # type: ignore[return-value]


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _fingerprint(event: MemoryEvent) -> str:
    payload = event.model_dump(mode="json", exclude={"event_id", "ingested_at", "idempotency_key"})
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _authorized(scope: AuthorizedScope) -> AuthorizedScope:
    if not isinstance(scope, AuthorizedScope):
        raise TypeError("an AuthorizedScope from a trusted caller is required")
    return AuthorizedScope.model_validate(scope.model_dump(mode="json"))


def _validated_event(event: MemoryEvent) -> MemoryEvent:
    if not isinstance(event, MemoryEvent):
        raise TypeError("a MemoryEvent is required")
    return MemoryEvent.model_validate(event.model_dump(mode="json"))


def _validated_cursor(cursor: EventCursor) -> EventCursor:
    if not isinstance(cursor, EventCursor):
        raise TypeError("an EventCursor is required")
    return EventCursor.model_validate(cursor.model_dump(mode="json"))


class SQLiteEventStore:
    """One connection per operation; caller supplies an already-authorized scope."""

    def __init__(self, path: str | os.PathLike[str] | None = None, *, busy_timeout_ms: int = 5000) -> None:
        if type(busy_timeout_ms) is not int or not 0 <= busy_timeout_ms <= 60_000:
            raise ValueError("busy_timeout_ms must be an integer from 0 to 60000")
        self.path = database_path(path)
        self.busy_timeout_ms = busy_timeout_ms

    def _connect(self, mode: str) -> sqlite3.Connection:
        if mode not in {"ro", "rw", "rwc"}:
            raise ValueError("invalid SQLite connection mode")
        if mode != "rwc" and not self.path.is_file():
            raise DatabaseMissingError("SQLite event database is missing")
        uri = f"{self.path.as_uri()}?mode={mode}"
        connection = sqlite3.connect(
            uri, uri=True, isolation_level=None, timeout=self.busy_timeout_ms / 1000
        )
        try:
            connection.row_factory = sqlite3.Row
            connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
            connection.execute("PRAGMA foreign_keys = ON")
            if mode == "ro":
                connection.execute("PRAGMA query_only = ON")
            else:
                journal = connection.execute("PRAGMA journal_mode").fetchone()[0]
                connection.execute(f"PRAGMA synchronous = {'FULL' if journal.lower() == 'wal' else 'EXTRA'}")
            return connection
        except BaseException:
            connection.close()
            raise

    @staticmethod
    def _require_schema(connection: sqlite3.Connection) -> None:
        version = user_version(connection)
        if version < 0:
            raise StorageCorruptionError("SQLite event schema version is invalid")
        if version > SCHEMA_VERSION:
            raise UnsupportedSchemaVersionError("SQLite event schema version is newer than supported")
        if version == 0:
            if is_empty_unowned_database(connection):
                raise DatabaseUninitializedError("SQLite event database is not initialized")
            raise ForeignDatabaseError("unversioned database contains non-OOMP objects")
        if version != SCHEMA_VERSION or not verify_v1(connection):
            raise StorageCorruptionError("SQLite event schema does not match version 1")

    @staticmethod
    def _set_wal_and_synchronous(connection: sqlite3.Connection) -> None:
        journal = str(connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]).lower()
        connection.execute(f"PRAGMA synchronous = {'FULL' if journal == 'wal' else 'EXTRA'}")

    @_translate_sqlite_errors
    def initialize(self) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        mode = "rw" if self.path.exists() else "rwc"
        with closing(self._connect(mode)) as connection:
            version = user_version(connection)
            if version < 0:
                raise StorageCorruptionError("SQLite event schema version is invalid")
            if version > SCHEMA_VERSION:
                raise UnsupportedSchemaVersionError("SQLite event schema version is newer than supported")
            if version == 0 and not is_empty_unowned_database(connection):
                raise ForeignDatabaseError("unversioned database contains non-OOMP objects")
            if version == SCHEMA_VERSION and not verify_v1(connection):
                raise StorageCorruptionError("SQLite event schema does not match version 1")
            self._set_wal_and_synchronous(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                version = user_version(connection)
                if version < 0:
                    raise StorageCorruptionError("SQLite event schema version is invalid")
                if version > SCHEMA_VERSION:
                    raise UnsupportedSchemaVersionError("SQLite event schema version is newer than supported")
                if version == 0 and not is_empty_unowned_database(connection):
                    raise ForeignDatabaseError("unversioned database contains non-OOMP objects")
                for target in range(version + 1, SCHEMA_VERSION + 1):
                    for statement in MIGRATIONS[target]:
                        connection.execute(statement)
                    connection.execute(f"PRAGMA user_version = {target}")
                self._require_schema(connection)
                connection.execute("COMMIT")
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
        return SCHEMA_VERSION

    def status(self) -> StorageStatus:
        if not self.path.is_file():
            return StorageStatus(self.path, self.path.exists(), False, None, None, False, "database is missing")
        try:
            with closing(self._connect("ro")) as connection:
                version = user_version(connection)
                journal = str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()
                if version < 0:
                    return StorageStatus(self.path, True, True, version, journal, False, "schema version is invalid")
                if version > SCHEMA_VERSION:
                    return StorageStatus(self.path, True, True, version, journal, False, "schema version is unsupported")
                if version == 0:
                    message = "database is uninitialized" if is_empty_unowned_database(connection) else "database is not an OOMP database"
                    return StorageStatus(self.path, True, True, 0, journal, False, message)
                if not verify_v1(connection):
                    return StorageStatus(self.path, True, True, version, journal, False, "schema structure is invalid")
                return StorageStatus(self.path, True, True, version, journal, True, "ready")
        except (sqlite3.Error, OSError, StorageError):
            return StorageStatus(self.path, True, False, None, None, False, "database is unavailable or invalid")

    @staticmethod
    def _decode(row: sqlite3.Row) -> MemoryEvent:
        try:
            source_reference = json.loads(row["source_reference_json"])
            metadata = json.loads(row["metadata_json"])
            event = MemoryEvent.model_validate({
                "tenant_id": row["tenant_id"],
                "namespace": row["namespace"],
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "source_type": row["source_type"],
                "content": row["content"],
                "source_reference": source_reference,
                "occurred_at": row["occurred_at"],
                "ingested_at": row["ingested_at"],
                "idempotency_key": row["idempotency_key"],
                "metadata": metadata,
            })
            if _timestamp(event.occurred_at) != row["occurred_at"] or _timestamp(event.ingested_at) != row["ingested_at"]:
                raise ValueError("noncanonical timestamp")
            if _fingerprint(event) != row["payload_fingerprint"]:
                raise ValueError("fingerprint mismatch")
            return event
        except (ValueError, TypeError, KeyError, ValidationError, OverflowError) as error:
            raise StoredEventCorruptionError("stored event failed validation") from None

    @_translate_sqlite_errors
    def append(self, scope: AuthorizedScope, event: MemoryEvent) -> MemoryEvent:
        authorized = _authorized(scope)
        incoming = _validated_event(event)
        if (incoming.tenant_id, incoming.namespace) != (authorized.tenant_id, authorized.namespace):
            raise ScopeMismatchError("event scope differs from authorized scope")
        fingerprint = _fingerprint(incoming)
        with closing(self._connect("rw")) as connection:
            self._require_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                by_id = connection.execute(
                    "SELECT * FROM events WHERE tenant_id=? AND namespace=? AND event_id=?",
                    (authorized.tenant_id, authorized.namespace, incoming.event_id),
                ).fetchone()
                by_key = None
                if incoming.idempotency_key is not None:
                    by_key = connection.execute(
                        "SELECT * FROM events WHERE tenant_id=? AND namespace=? AND idempotency_key=?",
                        (authorized.tenant_id, authorized.namespace, incoming.idempotency_key),
                    ).fetchone()
                if by_id is not None and by_key is not None and by_id["event_id"] != by_key["event_id"]:
                    raise IdempotencyConflictError("event ID and idempotency key identify different stored events")
                existing = by_id or by_key
                if existing is not None:
                    stored = self._decode(existing)
                    if fingerprint != existing["payload_fingerprint"]:
                        raise IdempotencyConflictError("event identity or idempotency key conflicts with stored evidence")
                    if by_id is not None and incoming.idempotency_key is not None and incoming.idempotency_key != stored.idempotency_key:
                        raise IdempotencyConflictError("event ID cannot acquire or change an idempotency key")
                    result = stored
                else:
                    connection.execute(
                        """INSERT INTO events (
                            tenant_id, namespace, event_id, event_type, source_type, content,
                            source_reference_json, occurred_at, ingested_at, idempotency_key,
                            metadata_json, payload_fingerprint
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            incoming.tenant_id, incoming.namespace, incoming.event_id,
                            incoming.event_type.value, incoming.source_type.value, incoming.content,
                            _canonical_json(incoming.source_reference.model_dump(mode="json")),
                            _timestamp(incoming.occurred_at), _timestamp(incoming.ingested_at),
                            incoming.idempotency_key, _canonical_json(incoming.model_dump(mode="json")["metadata"]),
                            fingerprint,
                        ),
                    )
                    result = incoming
                connection.execute("COMMIT")
                return result
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    @_translate_sqlite_errors
    def get(self, scope: AuthorizedScope, event_id: str) -> MemoryEvent | None:
        authorized = _authorized(scope)
        validated_id = _EVENT_ID.validate_python(event_id)
        with closing(self._connect("ro")) as connection:
            self._require_schema(connection)
            row = connection.execute(
                "SELECT * FROM events WHERE tenant_id=? AND namespace=? AND event_id=?",
                (authorized.tenant_id, authorized.namespace, validated_id),
            ).fetchone()
            return None if row is None else self._decode(row)

    @_translate_sqlite_errors
    def list_events(
        self, scope: AuthorizedScope, *, limit: int = 100, after: EventCursor | None = None
    ) -> EventPage:
        authorized = _authorized(scope)
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("limit must be an integer from 1 to 1000")
        cursor = _validated_cursor(after) if after is not None else None
        if cursor is not None and (cursor.tenant_id, cursor.namespace) != (authorized.tenant_id, authorized.namespace):
            raise ScopeMismatchError("cursor scope differs from authorized scope")
        sql = "SELECT * FROM events WHERE tenant_id=? AND namespace=?"
        parameters: list[Any] = [authorized.tenant_id, authorized.namespace]
        if cursor is not None:
            sql += " AND (occurred_at, ingested_at, event_id) > (?, ?, ?)"
            parameters.extend((_timestamp(cursor.occurred_at), _timestamp(cursor.ingested_at), cursor.event_id))
        sql += " ORDER BY occurred_at, ingested_at, event_id LIMIT ?"
        parameters.append(limit + 1)
        with closing(self._connect("ro")) as connection:
            self._require_schema(connection)
            rows = connection.execute(sql, parameters).fetchall()
            events = tuple(self._decode(row) for row in rows[:limit])
            more = len(rows) > limit
            next_cursor = None
            if more:
                last = events[-1]
                next_cursor = EventCursor(
                    tenant_id=authorized.tenant_id, namespace=authorized.namespace,
                    occurred_at=last.occurred_at, ingested_at=last.ingested_at,
                    event_id=last.event_id,
                )
            return EventPage(events=events, next_cursor=next_cursor)

    @_translate_sqlite_errors
    def count_events(self, scope: AuthorizedScope) -> int:
        authorized = _authorized(scope)
        with closing(self._connect("ro")) as connection:
            self._require_schema(connection)
            return int(connection.execute(
                "SELECT COUNT(*) FROM events WHERE tenant_id=? AND namespace=?",
                (authorized.tenant_id, authorized.namespace),
            ).fetchone()[0])