"""Scoped conservative entity identity persistence."""

from __future__ import annotations

from pydantic import TypeAdapter

from oomp.domain.memories import EntityMention, EntityRecord
from oomp.domain.models import AuthorizedScope, Identifier
from .memory_store import SQLiteMemoryStore, _event_in_scope, _read_entity, _resolve_entity, _validate_mention
from .sqlite import _authorized, _translate_sqlite_errors

_IDENTIFIER = TypeAdapter(Identifier)


class SQLiteEntityStore(SQLiteMemoryStore):
    """Resolves explicit names and aliases inside one authorized partition."""

    @_translate_sqlite_errors
    def resolve(self, scope: AuthorizedScope, mention: EntityMention) -> EntityRecord:
        authorized = _authorized(scope)
        validated = _validate_mention(mention)
        with self._transaction() as connection:
            source = _event_in_scope(connection, authorized, validated.source_event_id)
            record, _ = _resolve_entity(connection, authorized, validated, source)
            return record

    @_translate_sqlite_errors
    def get(self, scope: AuthorizedScope, entity_id: str) -> EntityRecord | None:
        authorized = _authorized(scope)
        identifier = _IDENTIFIER.validate_python(entity_id)
        with self._read_transaction() as connection:
            return _read_entity(connection, authorized, identifier)

    @_translate_sqlite_errors
    def count_entities(self, scope: AuthorizedScope) -> int:
        authorized = _authorized(scope)
        with self._read_transaction() as connection:
            return int(connection.execute(
                "SELECT COUNT(*) FROM entities WHERE tenant_id=? AND namespace=?",
                (authorized.tenant_id, authorized.namespace),
            ).fetchone()[0])