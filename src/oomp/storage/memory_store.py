"""Scoped canonical memory persistence and atomic event extraction writes."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import unicodedata
from collections.abc import Iterator, Sequence
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from typing import Any

from pydantic import TypeAdapter, ValidationError

from oomp.domain.enums import MemoryType, SourceType
from oomp.domain.memories import (
    EntityMention, EntityRecord, MemoryCursor, MemoryPage, MemoryWrite,
    ProcessingResult, SourceSpan,
)
from oomp.domain.models import AuthorizedScope, Identifier, MemoryEvent, MemoryNode
from .errors import (
    AliasConflictError, EntityEvidenceError, MemoryConflictError,
    MemoryNotFoundError, ProvenanceMismatchError, SchemaUpgradeRequiredError,
    ScopeMismatchError, SourceEventMissingError, StoredMemoryCorruptionError,
)
from .migrations import user_version
from .sqlite import (
    SQLiteEventStore, _authorized, _canonical_json, _timestamp,
    _translate_sqlite_errors,
)

_IDENTIFIER = TypeAdapter(Identifier)
_MAX_SOURCES = 1000
_MAX_ALIASES = 64
_MAX_ENTITIES_PER_MEMORY = 64


def _validate_node(value: MemoryNode) -> MemoryNode:
    if not isinstance(value, MemoryNode):
        raise TypeError("a MemoryNode is required")
    return MemoryNode.model_validate(value.model_dump(mode="json"))


def _validate_mention(value: EntityMention) -> EntityMention:
    if not isinstance(value, EntityMention):
        raise TypeError("an EntityMention is required")
    return EntityMention.model_validate(value.model_dump(mode="json"))


def _validate_write(value: MemoryWrite) -> MemoryWrite:
    if not isinstance(value, MemoryWrite):
        raise TypeError("a MemoryWrite is required")
    return MemoryWrite.model_validate(value.model_dump(mode="json"))


def _normalize_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split()).casefold()


def _contains_name(text: str, name: str) -> bool:
    normalized = unicodedata.normalize("NFC", text).casefold()
    parts = unicodedata.normalize("NFC", name).casefold().split()
    if not parts:
        return False
    expression = r"(?<![\w-])" + r"\s+".join(re.escape(part) for part in parts) + r"(?![\w-])"
    return re.search(expression, normalized) is not None


def _check_span(event: MemoryEvent, span: SourceSpan) -> None:
    if span.end > len(event.content) or event.content[span.start:span.end] != span.quote:
        raise ProvenanceMismatchError("source span does not match stored event text")


def _alias_proof(name: str, aliases: tuple[str, ...], quote: str) -> bool:
    primary = _normalize_name(name)
    pairs = {
        (_normalize_name(match.group(1)), _normalize_name(match.group(2)))
        for match in re.finditer(r"([^(),\n]{1,512}?)\s*\(\s*([^(),\n]{1,512}?)\s*\)", quote)
    }
    return all(
        (primary, _normalize_name(alias)) in pairs
        or (_normalize_name(alias), primary) in pairs
        for alias in aliases
    )


def _memory_fingerprint(node: MemoryNode) -> str:
    payload = node.model_dump(
        mode="json",
        exclude={"memory_id", "source_event_ids", "provenance", "created_at", "updated_at"},
    )
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _entity_id(scope: AuthorizedScope, entity_type: str, normalized_name: str) -> str:
    payload = _canonical_json((scope.tenant_id, scope.namespace, entity_type, normalized_name))
    return "ent_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _event_in_scope(
    connection: sqlite3.Connection, scope: AuthorizedScope, event_id: str
) -> MemoryEvent:
    row = connection.execute(
        "SELECT * FROM events WHERE tenant_id=? AND namespace=? AND event_id=?",
        (scope.tenant_id, scope.namespace, event_id),
    ).fetchone()
    if row is None:
        raise SourceEventMissingError("source event is missing from authorized scope")
    return SQLiteEventStore._decode(row)


def _validate_claim(node: MemoryNode, roles: Sequence[SourceType]) -> None:
    metadata = node.metadata
    if "verified" in metadata and metadata["verified"] is not False:
        raise ProvenanceMismatchError("derived memory cannot claim verification")
    attribution = metadata.get("attribution")
    if attribution is not None and any(role.value != attribution for role in roles):
        raise ProvenanceMismatchError("memory attribution conflicts with source roles")
    if node.memory_type is MemoryType.PROFILE and any(
        role is not SourceType.USER for role in roles
    ):
        raise ProvenanceMismatchError("profile memory requires user source events")


def _read_entity(
    connection: sqlite3.Connection, scope: AuthorizedScope, entity_id: str
) -> EntityRecord | None:
    row = connection.execute(
        "SELECT * FROM entities WHERE tenant_id=? AND namespace=? AND entity_id=?",
        (scope.tenant_id, scope.namespace, entity_id),
    ).fetchone()
    if row is None:
        return None
    try:
        aliases = tuple(
            item[0] for item in connection.execute(
                """SELECT alias_name FROM entity_aliases
                   WHERE tenant_id=? AND namespace=? AND entity_id=?
                   ORDER BY normalized_alias LIMIT 65""",
                (scope.tenant_id, scope.namespace, entity_id),
            )
        )
        if len(aliases) > _MAX_ALIASES:
            raise ValueError("too many stored aliases")
        record = EntityRecord.model_validate({
            "entity_id": row["entity_id"], "tenant_id": row["tenant_id"],
            "namespace": row["namespace"], "entity_type": row["entity_type"],
            "canonical_name": row["canonical_name"],
            "normalized_name": row["normalized_name"],
            "aliases": aliases, "created_at": row["created_at"],
        })
        if _timestamp(record.created_at) != row["created_at"]:
            raise ValueError("noncanonical entity timestamp")
        if _normalize_name(record.canonical_name) != record.normalized_name:
            raise ValueError("entity name mismatch")
        return record
    except (ValueError, TypeError, KeyError, ValidationError):
        raise StoredMemoryCorruptionError("stored entity failed validation") from None


def _resolve_entity(
    connection: sqlite3.Connection,
    scope: AuthorizedScope,
    mention: EntityMention,
    source: MemoryEvent,
) -> tuple[EntityRecord, bool]:
    if mention.source_event_id != source.event_id:
        raise ProvenanceMismatchError("entity mention source differs from event")
    text = source.content
    if mention.source_span is not None:
        _check_span(source, mention.source_span)
        text = mention.source_span.quote
    if not _contains_name(text, mention.name):
        raise EntityEvidenceError("entity name lacks literal source evidence")
    if mention.aliases:
        if mention.source_span is None or not _alias_proof(mention.name, mention.aliases, text):
            raise EntityEvidenceError("entity aliases lack explicit parenthetical source evidence")

    normalized = _normalize_name(mention.name)
    if not normalized:
        raise EntityEvidenceError("entity name normalizes to blank")
    names = {normalized, *(_normalize_name(alias) for alias in mention.aliases)}
    matches: set[str] = set()
    for name in names:
        for row in connection.execute(
            """SELECT entity_id FROM entities
               WHERE tenant_id=? AND namespace=? AND entity_type=? AND normalized_name=?""",
            (scope.tenant_id, scope.namespace, mention.entity_type.value, name),
        ):
            matches.add(row[0])
        for row in connection.execute(
            """SELECT entity_id FROM entity_aliases
               WHERE tenant_id=? AND namespace=? AND entity_type=? AND normalized_alias=?""",
            (scope.tenant_id, scope.namespace, mention.entity_type.value, name),
        ):
            matches.add(row[0])
    if len(matches) > 1:
        raise AliasConflictError("explicit aliases identify distinct existing entities")

    created = False
    if matches:
        entity_id = next(iter(matches))
        record = _read_entity(connection, scope, entity_id)
        if record is None:
            raise StoredMemoryCorruptionError("entity alias points to a missing record")
    else:
        entity_id = _entity_id(scope, mention.entity_type.value, normalized)
        existing = _read_entity(connection, scope, entity_id)
        if existing is not None:
            raise AliasConflictError("entity identity collides with an existing record")
        connection.execute(
            """INSERT INTO entities (
                tenant_id, namespace, entity_id, entity_type,
                canonical_name, normalized_name, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                scope.tenant_id, scope.namespace, entity_id, mention.entity_type.value,
                mention.name, normalized, _timestamp(datetime.now(timezone.utc)),
            ),
        )
        record = _read_entity(connection, scope, entity_id)
        created = True

    assert record is not None
    alias_names = (mention.name, *mention.aliases)
    aliases_found = [
        row[0] for row in connection.execute(
            """SELECT normalized_alias FROM entity_aliases
               WHERE tenant_id=? AND namespace=? AND entity_id=? LIMIT 65""",
            (scope.tenant_id, scope.namespace, entity_id),
        )
    ]
    if len(aliases_found) > _MAX_ALIASES:
        raise StoredMemoryCorruptionError("stored entity exceeds alias limit")
    existing_aliases = set(aliases_found)
    additions: list[tuple[str, str]] = []
    for alias_name in alias_names:
        alias = _normalize_name(alias_name)
        if alias == record.normalized_name or alias in existing_aliases:
            continue
        if alias not in {item[0] for item in additions}:
            additions.append((alias, alias_name))
    if len(existing_aliases) + len(additions) > _MAX_ALIASES:
        raise ValueError("entity alias limit exceeded")
    for alias, alias_name in additions:
        connection.execute(
            """INSERT INTO entity_aliases (
                tenant_id, namespace, entity_type, normalized_alias,
                alias_name, entity_id, source_event_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                scope.tenant_id, scope.namespace, mention.entity_type.value,
                alias, alias_name, entity_id, source.event_id,
            ),
        )
    result = _read_entity(connection, scope, entity_id)
    assert result is not None
    return result, created


class SQLiteMemoryStore(SQLiteEventStore):
    """Canonical memory storage; all claims remain source-attributed and unverified."""

    @staticmethod
    def _require_v2(connection: sqlite3.Connection) -> None:
        SQLiteEventStore._require_schema(connection)
        if user_version(connection) < 2:
            raise SchemaUpgradeRequiredError("memory storage requires explicit schema version 2 initialization")

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with closing(self._connect("rw")) as connection:
            self._require_v2(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.execute("COMMIT")
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    @contextmanager
    def _read_transaction(self) -> Iterator[sqlite3.Connection]:
        with closing(self._connect("ro")) as connection:
            connection.execute("BEGIN")
            try:
                self._require_v2(connection)
                yield connection
            finally:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")

    @staticmethod
    def _read_memory(
        connection: sqlite3.Connection, scope: AuthorizedScope, row: sqlite3.Row
    ) -> MemoryNode:
        try:
            links = connection.execute(
                """SELECT event_id, ordinal, source_span_json FROM memory_sources
                   WHERE tenant_id=? AND namespace=? AND memory_id=?
                   ORDER BY ordinal LIMIT 1001""",
                (scope.tenant_id, scope.namespace, row["memory_id"]),
            ).fetchall()
            if not links or len(links) > _MAX_SOURCES:
                raise ValueError("invalid evidence count")
            if [link["ordinal"] for link in links] != list(range(len(links))):
                raise ValueError("invalid evidence order")
            source_ids: list[str] = []
            references = []
            roles: list[SourceType] = []
            for link in links:
                source_event = _event_in_scope(connection, scope, link["event_id"])
                if link["source_span_json"] is not None:
                    span = SourceSpan.model_validate(json.loads(link["source_span_json"]))
                    _check_span(source_event, span)
                source_ids.append(source_event.event_id)
                references.append(source_event.source_reference)
                roles.append(source_event.source_type)
                del source_event
            memory = MemoryNode.model_validate({
                "memory_id": row["memory_id"], "tenant_id": row["tenant_id"],
                "namespace": row["namespace"], "memory_type": row["memory_type"],
                "canonical_key": row["canonical_key"],
                "canonical_content": row["canonical_content"],
                "status": row["status"], "created_at": row["created_at"],
                "updated_at": row["updated_at"], "valid_from": row["valid_from"],
                "valid_until": row["valid_until"], "confidence": row["confidence"],
                "tags": json.loads(row["tags_json"]),
                "metadata": json.loads(row["metadata_json"]),
                "source_event_ids": tuple(source_ids),
                "provenance": tuple(references),
            })
            _validate_claim(memory, roles)
            if _memory_fingerprint(memory) != row["payload_fingerprint"]:
                raise ValueError("memory fingerprint mismatch")
            for field in ("created_at", "updated_at", "valid_from", "valid_until"):
                value = getattr(memory, field)
                if value is not None and _timestamp(value) != row[field]:
                    raise ValueError("noncanonical memory timestamp")
            return memory
        except (ValueError, TypeError, KeyError, ValidationError, SourceEventMissingError,
                ProvenanceMismatchError, StoredMemoryCorruptionError):
            raise StoredMemoryCorruptionError("stored memory failed validation") from None

    def _upsert_in_transaction(
        self,
        connection: sqlite3.Connection,
        scope: AuthorizedScope,
        memory: MemoryNode,
        *,
        source_spans: dict[str, SourceSpan] | None = None,
        extraction_method: str = "manual",
    ) -> tuple[MemoryNode, bool, int]:
        if (memory.tenant_id, memory.namespace) != (scope.tenant_id, scope.namespace):
            raise ScopeMismatchError("memory scope differs from authorized scope")
        if len(memory.source_event_ids) != len(set(memory.source_event_ids)):
            raise ProvenanceMismatchError("memory source IDs must be distinct")
        if len(memory.source_event_ids) > _MAX_SOURCES:
            raise ValueError("memory source limit exceeded")
        if len(memory.source_event_ids) != len(memory.provenance):
            raise ProvenanceMismatchError("source IDs and references must align")
        roles: list[SourceType] = []
        for event_id, reference in zip(memory.source_event_ids, memory.provenance, strict=True):
            source_event = _event_in_scope(connection, scope, event_id)
            if reference != source_event.source_reference:
                raise ProvenanceMismatchError("memory provenance differs from original source event")
            roles.append(source_event.source_type)
            if source_spans and event_id in source_spans:
                _check_span(source_event, source_spans[event_id])
            del source_event
        _validate_claim(memory, roles)
        by_id = connection.execute(
            "SELECT * FROM memories WHERE tenant_id=? AND namespace=? AND memory_id=?",
            (scope.tenant_id, scope.namespace, memory.memory_id),
        ).fetchone()
        by_key = connection.execute(
            "SELECT * FROM memories WHERE tenant_id=? AND namespace=? AND canonical_key=?",
            (scope.tenant_id, scope.namespace, memory.canonical_key),
        ).fetchone()
        if by_id is not None and by_key is not None and by_id["memory_id"] != by_key["memory_id"]:
            raise MemoryConflictError("memory ID and canonical key identify different records")
        existing = by_id or by_key
        fingerprint = _memory_fingerprint(memory)
        created = False
        if existing is not None:
            if existing["payload_fingerprint"] != fingerprint:
                raise MemoryConflictError("canonical memory identity conflicts with stored content")
            stored = self._read_memory(connection, scope, existing)
            memory_id = stored.memory_id
            ordinal = len(stored.source_event_ids)
            if len(set(stored.source_event_ids) | set(memory.source_event_ids)) > _MAX_SOURCES:
                raise ValueError("memory source limit exceeded")
        else:
            connection.execute(
                """INSERT INTO memories (
                    tenant_id, namespace, memory_id, memory_type,
                    canonical_key, canonical_content, status, created_at, updated_at,
                    valid_from, valid_until, confidence, tags_json, metadata_json,
                    payload_fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    memory.tenant_id, memory.namespace, memory.memory_id,
                    memory.memory_type.value, memory.canonical_key,
                    memory.canonical_content, memory.status.value,
                    _timestamp(memory.created_at), _timestamp(memory.updated_at),
                    _timestamp(memory.valid_from) if memory.valid_from else None,
                    _timestamp(memory.valid_until) if memory.valid_until else None,
                    memory.confidence,
                    _canonical_json(memory.model_dump(mode="json")["tags"]),
                    _canonical_json(memory.model_dump(mode="json")["metadata"]),
                    fingerprint,
                ),
            )
            memory_id = memory.memory_id
            ordinal = 0
            created = True
            stored = None
        known = set(stored.source_event_ids) if stored is not None else set()
        links_added = 0
        for source in memory.source_event_ids:
            if source in known:
                continue
            span = source_spans.get(source) if source_spans else None
            connection.execute(
                """INSERT INTO memory_sources (
                    tenant_id, namespace, memory_id, event_id,
                    ordinal, source_span_json, extraction_method
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope.tenant_id, scope.namespace, memory_id, source,
                    ordinal,
                    _canonical_json(span.model_dump(mode="json")) if span else None,
                    extraction_method,
                ),
            )
            known.add(source)
            ordinal += 1
            links_added += 1
        if stored is not None and links_added:
            current = datetime.now(timezone.utc)
            updated = max(current, stored.created_at, stored.updated_at)
            connection.execute(
                """UPDATE memories SET updated_at=?
                   WHERE tenant_id=? AND namespace=? AND memory_id=?""",
                (_timestamp(updated), scope.tenant_id, scope.namespace, memory_id),
            )
        row = connection.execute(
            "SELECT * FROM memories WHERE tenant_id=? AND namespace=? AND memory_id=?",
            (scope.tenant_id, scope.namespace, memory_id),
        ).fetchone()
        assert row is not None
        return self._read_memory(connection, scope, row), created, links_added

    @_translate_sqlite_errors
    def put(self, scope: AuthorizedScope, memory: MemoryNode) -> None:
        self.upsert(scope, memory)

    @_translate_sqlite_errors
    def upsert(self, scope: AuthorizedScope, memory: MemoryNode) -> MemoryNode:
        authorized = _authorized(scope)
        validated = _validate_node(memory)
        with self._transaction() as connection:
            result, _, _ = self._upsert_in_transaction(connection, authorized, validated)
            return result

    @_translate_sqlite_errors
    def get(self, scope: AuthorizedScope, memory_id: str) -> MemoryNode | None:
        authorized = _authorized(scope)
        identifier = _IDENTIFIER.validate_python(memory_id)
        with self._read_transaction() as connection:
            row = connection.execute(
                "SELECT * FROM memories WHERE tenant_id=? AND namespace=? AND memory_id=?",
                (authorized.tenant_id, authorized.namespace, identifier),
            ).fetchone()
            return None if row is None else self._read_memory(connection, authorized, row)

    @_translate_sqlite_errors
    def find_by_canonical_key(self, scope: AuthorizedScope, canonical_key: str) -> MemoryNode | None:
        authorized = _authorized(scope)
        if not isinstance(canonical_key, str) or not canonical_key.strip() or len(canonical_key) > 512:
            raise ValueError("canonical key must be nonblank and at most 512 characters")
        with self._read_transaction() as connection:
            row = connection.execute(
                "SELECT * FROM memories WHERE tenant_id=? AND namespace=? AND canonical_key=?",
                (authorized.tenant_id, authorized.namespace, canonical_key),
            ).fetchone()
            return None if row is None else self._read_memory(connection, authorized, row)

    @_translate_sqlite_errors
    def list_memories(
        self, scope: AuthorizedScope, *, limit: int = 100, after: MemoryCursor | None = None
    ) -> MemoryPage:
        authorized = _authorized(scope)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer from 1 to 100")
        cursor = None
        if after is not None:
            if not isinstance(after, MemoryCursor):
                raise TypeError("a MemoryCursor is required")
            cursor = MemoryCursor.model_validate(after.model_dump(mode="json"))
            if (cursor.tenant_id, cursor.namespace) != (authorized.tenant_id, authorized.namespace):
                raise ScopeMismatchError("memory cursor scope differs from authorized scope")
        query = "SELECT * FROM memories WHERE tenant_id=? AND namespace=?"
        values: list[Any] = [authorized.tenant_id, authorized.namespace]
        if cursor is not None:
            query += " AND (created_at, memory_id) > (?, ?)"
            values.extend((_timestamp(cursor.created_at), cursor.memory_id))
        query += " ORDER BY created_at, memory_id LIMIT ?"
        values.append(limit + 1)
        with self._read_transaction() as connection:
            rows = connection.execute(query, values).fetchall()
            memories = tuple(self._read_memory(connection, authorized, row) for row in rows[:limit])
            next_cursor = None
            if len(rows) > limit:
                last = memories[-1]
                next_cursor = MemoryCursor(
                    tenant_id=authorized.tenant_id, namespace=authorized.namespace,
                    created_at=last.created_at, memory_id=last.memory_id,
                )
            return MemoryPage(memories=memories, next_cursor=next_cursor)

    @_translate_sqlite_errors
    def count_memories(self, scope: AuthorizedScope) -> int:
        authorized = _authorized(scope)
        with self._read_transaction() as connection:
            return int(connection.execute(
                "SELECT COUNT(*) FROM memories WHERE tenant_id=? AND namespace=?",
                (authorized.tenant_id, authorized.namespace),
            ).fetchone()[0])

    @_translate_sqlite_errors
    def attach_evidence(self, scope: AuthorizedScope, memory_id: str, event_id: str) -> MemoryNode:
        authorized = _authorized(scope)
        memory_identifier = _IDENTIFIER.validate_python(memory_id)
        event_identifier = _IDENTIFIER.validate_python(event_id)
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM memories WHERE tenant_id=? AND namespace=? AND memory_id=?",
                (authorized.tenant_id, authorized.namespace, memory_identifier),
            ).fetchone()
            if row is None:
                raise MemoryNotFoundError("memory is missing from authorized scope")
            existing = self._read_memory(connection, authorized, row)
            if event_identifier in existing.source_event_ids:
                return existing
            source = _event_in_scope(connection, authorized, event_identifier)
            fields = existing.model_dump(mode="json")
            fields["source_event_ids"] = [*existing.source_event_ids, source.event_id]
            fields["provenance"] = [
                *(reference.model_dump(mode="json") for reference in existing.provenance),
                source.source_reference.model_dump(mode="json"),
            ]
            combined = MemoryNode.model_validate(fields)
            result, _, _ = self._upsert_in_transaction(connection, authorized, combined)
            return result

    @_translate_sqlite_errors
    def list_entities(self, scope: AuthorizedScope, memory_id: str) -> tuple[EntityRecord, ...]:
        authorized = _authorized(scope)
        identifier = _IDENTIFIER.validate_python(memory_id)
        with self._read_transaction() as connection:
            ids = [
                row[0] for row in connection.execute(
                    """SELECT entity_id FROM memory_entities
                       WHERE tenant_id=? AND namespace=? AND memory_id=?
                       ORDER BY entity_id LIMIT 65""",
                    (authorized.tenant_id, authorized.namespace, identifier),
                )
            ]
            if len(ids) > _MAX_ENTITIES_PER_MEMORY:
                raise StoredMemoryCorruptionError("memory entity link limit exceeded")
            records = tuple(_read_entity(connection, authorized, entity_id) for entity_id in ids)
            if any(record is None for record in records):
                raise StoredMemoryCorruptionError("memory entity link is invalid")
            return records  # type: ignore[return-value]

    @_translate_sqlite_errors
    def apply_batch(
        self, scope: AuthorizedScope, event_id: str, writes: Sequence[MemoryWrite]
    ) -> ProcessingResult:
        authorized = _authorized(scope)
        source_id = _IDENTIFIER.validate_python(event_id)
        if not isinstance(writes, Sequence) or isinstance(writes, (str, bytes)) or len(writes) > 32:
            raise ValueError("writes must be a sequence of at most 32 MemoryWrite values")
        validated = tuple(_validate_write(write) for write in writes)
        for write in validated:
            if write.memory.source_event_ids != (source_id,):
                raise ProvenanceMismatchError("batch memory must cite exactly its source event")
            if any(mention.source_event_id != source_id for mention in write.entities):
                raise ProvenanceMismatchError("entity mention must cite batch source event")
        with self._transaction() as connection:
            source = _event_in_scope(connection, authorized, source_id)
            memories_created = memories_reused = evidence_links_added = 0
            entities_created = entities_reused = 0
            memory_ids: list[str] = []
            for write in validated:
                if write.memory.provenance != (source.source_reference,):
                    raise ProvenanceMismatchError("batch provenance differs from source event")
                if write.source_span is not None:
                    _check_span(source, write.source_span)
                memory, created, added = self._upsert_in_transaction(
                    connection, authorized, write.memory,
                    source_spans={source_id: write.source_span} if write.source_span else None,
                    extraction_method=write.extraction_method,
                )
                memories_created += int(created)
                memories_reused += int(not created)
                evidence_links_added += added
                for mention in write.entities:
                    entity, entity_created = _resolve_entity(connection, authorized, mention, source)
                    entities_created += int(entity_created)
                    entities_reused += int(not entity_created)
                    link_exists = connection.execute(
                        """SELECT 1 FROM memory_entities
                           WHERE tenant_id=? AND namespace=? AND memory_id=? AND entity_id=?""",
                        (authorized.tenant_id, authorized.namespace, memory.memory_id, entity.entity_id),
                    ).fetchone()
                    if link_exists is None:
                        link_count = connection.execute(
                            """SELECT COUNT(*) FROM memory_entities
                               WHERE tenant_id=? AND namespace=? AND memory_id=?""",
                            (authorized.tenant_id, authorized.namespace, memory.memory_id),
                        ).fetchone()[0]
                        if link_count >= _MAX_ENTITIES_PER_MEMORY:
                            raise ValueError("memory entity link limit exceeded")
                        connection.execute(
                            """INSERT INTO memory_entities
                               (tenant_id, namespace, memory_id, entity_id)
                               VALUES (?, ?, ?, ?)""",
                            (authorized.tenant_id, authorized.namespace, memory.memory_id, entity.entity_id),
                        )
                if memory.memory_id not in memory_ids:
                    memory_ids.append(memory.memory_id)
            return ProcessingResult(
                event_id=source_id, candidates_extracted=len(validated),
                memories_created=memories_created, memories_reused=memories_reused,
                evidence_links_added=evidence_links_added,
                entities_created=entities_created, entities_reused=entities_reused,
                memory_ids=tuple(memory_ids),
            )