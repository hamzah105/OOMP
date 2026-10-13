"""Conservative scoped entity identity and explicit alias evidence tests."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone

import pytest

from oomp.domain.memories import EntityMention, EntityType, SourceSpan
from oomp.domain.models import AuthorizedScope, MemoryEvent, RequestedScope, SourceReference
from oomp.storage import (
    AliasConflictError, EntityEvidenceError, ProvenanceMismatchError,
    SQLiteEntityStore, SQLiteEventStore, SourceEventMissingError,
)

NOW = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)


def scope(tenant="tenant-a", namespace="personal"):
    return AuthorizedScope(tenant_id=tenant, namespace=namespace, principal_id="local")


def ingest(store, event_id, content, *, tenant="tenant-a", namespace="personal"):
    source = MemoryEvent(
        event_id=event_id, tenant_id=tenant, namespace=namespace,
        event_type="user_message", source_type="user", content=content,
        source_reference=SourceReference(source_system="test", external_event_id=event_id, timestamp=NOW),
        occurred_at=NOW, ingested_at=NOW,
    )
    store.append(scope(tenant, namespace), source)
    return source


def mention(source, name, *, entity_type="project", aliases=(), quote=None):
    span = None
    if quote is not None:
        start = source.content.index(quote)
        span = SourceSpan(start=start, end=start + len(quote), quote=quote)
    return EntityMention(
        name=name, entity_type=entity_type, aliases=aliases,
        source_event_id=source.event_id, source_span=span,
    )


@pytest.fixture
def stores(tmp_path):
    path = tmp_path / "entities.sqlite3"
    events = SQLiteEventStore(path)
    events.initialize()
    return events, SQLiteEntityStore(path)


def test_explicit_alias_creation_reuse_restart_and_first_proof(stores):
    events, entities = stores
    phrase = "OOMP (Object-Oriented Context Map)"
    first = ingest(events, "e1", f"We are building {phrase}.")
    created = entities.resolve(
        scope(), mention(
            first, "OOMP", aliases=("Object-Oriented Context Map",), quote=phrase,
        ),
    )
    assert created.canonical_name == "OOMP"
    assert created.aliases == ("Object-Oriented Context Map",)
    repeated = ingest(events, "e2", "The OOMP project continues.")
    assert entities.resolve(scope(), mention(repeated, "OOMP")) == created
    expanded = ingest(events, "e3", "Object-Oriented Context Map is a project.")
    assert entities.resolve(
        scope(), mention(expanded, "Object-Oriented Context Map")
    ) == created
    reopened = SQLiteEntityStore(entities.path)
    assert reopened.get(scope(), created.entity_id) == created
    assert reopened.count_entities(scope()) == 1
    with closing(sqlite3.connect(entities.path)) as connection:
        proof = connection.execute(
            "SELECT source_event_id FROM entity_aliases WHERE entity_id=?",
            (created.entity_id,),
        ).fetchone()[0]
    assert proof == "e1"


def test_reversed_parenthetical_alias_is_supported(stores):
    events, entities = stores
    phrase = "Object-Oriented Context Map (OOMP)"
    source = ingest(events, "e1", f"The project is named {phrase}.")
    created = entities.resolve(
        scope(), mention(
            source, "Object-Oriented Context Map", aliases=("OOMP",), quote=phrase,
        ),
    )
    another = ingest(events, "e2", "OOMP is local.")
    assert entities.resolve(scope(), mention(another, "OOMP")).entity_id == created.entity_id


def test_type_qualified_identity_and_no_fuzzy_person_merge(stores):
    events, entities = stores
    source = ingest(events, "e1", "Java, Sam and Samuel are distinct names.")
    technology = entities.resolve(scope(), mention(source, "Java", entity_type="technology"))
    location = entities.resolve(scope(), mention(source, "Java", entity_type="location"))
    sam = entities.resolve(scope(), mention(source, "Sam", entity_type="person"))
    samuel = entities.resolve(scope(), mention(source, "Samuel", entity_type="person"))
    assert technology.entity_id != location.entity_id
    assert sam.entity_id != samuel.entity_id
    assert entities.count_entities(scope()) == 4


def test_unicode_nfc_casefold_and_whitespace_reuse(stores):
    events, entities = stores
    first = ingest(events, "e1", "Café is named explicitly.")
    one = entities.resolve(scope(), mention(first, "Café", entity_type=EntityType.CONCEPT))
    second = ingest(events, "e2", "Café is repeated.")
    two = entities.resolve(scope(), mention(second, "Café", entity_type=EntityType.CONCEPT))
    assert one.entity_id == two.entity_id
    assert entities.count_entities(scope()) == 1


def test_alias_conflict_never_merges_distinct_records(stores):
    events, entities = stores
    one = ingest(events, "e1", "OOMP is a project.")
    two = ingest(events, "e2", "TRACE is a project.")
    oomp = entities.resolve(scope(), mention(one, "OOMP"))
    trace = entities.resolve(scope(), mention(two, "TRACE"))
    collision = ingest(events, "e3", "OOMP (TRACE) is misleading.")
    with pytest.raises(AliasConflictError):
        entities.resolve(
            scope(), mention(collision, "OOMP", aliases=("TRACE",), quote="OOMP (TRACE)")
        )
    assert entities.count_entities(scope()) == 2
    assert entities.get(scope(), oomp.entity_id) == oomp
    assert entities.get(scope(), trace.entity_id) == trace


def test_alias_requires_literal_parenthetical_and_name_token(stores):
    events, entities = stores
    source = ingest(events, "e1", "OOMP means Object-Oriented Context Map.")
    with pytest.raises(EntityEvidenceError):
        entities.resolve(
            scope(), mention(
                source, "OOMP", aliases=("Object-Oriented Context Map",),
                quote="OOMP means Object-Oriented Context Map",
            ),
        )
    with pytest.raises(EntityEvidenceError):
        entities.resolve(scope(), mention(source, "Sam"))
    with pytest.raises(ProvenanceMismatchError):
        entities.resolve(
            scope(), EntityMention(
                name="OOMP", entity_type="project", source_event_id="e1",
                source_span=SourceSpan(start=0, end=4, quote="WRONG"),
            ),
        )
    assert entities.count_entities(scope()) == 0


def test_alias_cap_failure_rolls_back_new_proof(stores, monkeypatch):
    import oomp.storage.memory_store as module

    events, entities = stores
    monkeypatch.setattr(module, "_MAX_ALIASES", 1)
    first = ingest(events, "e1", "OOMP (Object-Oriented Context Map) is named.")
    original = entities.resolve(
        scope(), mention(
            first, "OOMP", aliases=("Object-Oriented Context Map",),
            quote="OOMP (Object-Oriented Context Map)",
        ),
    )
    second = ingest(events, "e2", "OOMP (Other Map) is named.")
    with pytest.raises(ValueError):
        entities.resolve(
            scope(), mention(second, "OOMP", aliases=("Other Map",), quote="OOMP (Other Map)")
        )
    assert entities.get(scope(), original.entity_id) == original
    assert entities.count_entities(scope()) == 1


def test_scope_isolation_and_missing_source(stores):
    events, entities = stores
    a = ingest(events, "e1", "OOMP is local.")
    b = ingest(events, "e1", "OOMP is local.", tenant="tenant-b")
    first = entities.resolve(scope(), mention(a, "OOMP"))
    second = entities.resolve(scope("tenant-b"), mention(b, "OOMP"))
    assert first.entity_id != second.entity_id
    assert entities.count_entities(scope()) == 1
    assert entities.count_entities(scope("tenant-b")) == 1
    assert entities.get(scope(), second.entity_id) is None
    with pytest.raises(SourceEventMissingError):
        entities.resolve(scope(namespace="other"), mention(a, "OOMP"))
    with pytest.raises(TypeError):
        entities.count_entities(RequestedScope(tenant_id="tenant-a", namespace="personal"))