"""Transactional, sequential SQLite migrations for events and canonical memories."""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 2

CREATE_EVENTS = """
CREATE TABLE events (
    tenant_id TEXT NOT NULL,
    namespace TEXT NOT NULL,
    event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source_type TEXT NOT NULL,
    content TEXT NOT NULL,
    source_reference_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    idempotency_key TEXT,
    metadata_json TEXT NOT NULL,
    payload_fingerprint TEXT NOT NULL,
    PRIMARY KEY (tenant_id, namespace, event_id),
    CHECK (length(tenant_id) > 0),
    CHECK (length(namespace) > 0),
    CHECK (length(event_id) > 0),
    CHECK (content <> ''),
    CHECK (length(payload_fingerprint) = 64)
) WITHOUT ROWID
"""

MIGRATION_1: tuple[str, ...] = (
    CREATE_EVENTS,
    """CREATE UNIQUE INDEX events_idempotency_key
       ON events (tenant_id, namespace, idempotency_key)
       WHERE idempotency_key IS NOT NULL""",
    """CREATE INDEX events_chronological
       ON events (tenant_id, namespace, occurred_at, ingested_at, event_id)""",
    """CREATE TRIGGER events_no_update
       BEFORE UPDATE ON events BEGIN
       SELECT RAISE(ABORT, 'source events are immutable');
       END""",
    """CREATE TRIGGER events_no_delete
       BEFORE DELETE ON events BEGIN
       SELECT RAISE(ABORT, 'source events are immutable');
       END""",
)

MIGRATION_2: tuple[str, ...] = (
    """CREATE TABLE memories (
        tenant_id TEXT NOT NULL,
        namespace TEXT NOT NULL,
        memory_id TEXT NOT NULL,
        memory_type TEXT NOT NULL,
        canonical_key TEXT NOT NULL,
        canonical_content TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        valid_from TEXT,
        valid_until TEXT,
        confidence REAL,
        tags_json TEXT NOT NULL,
        metadata_json TEXT NOT NULL,
        payload_fingerprint TEXT NOT NULL,
        PRIMARY KEY (tenant_id, namespace, memory_id),
        UNIQUE (tenant_id, namespace, canonical_key),
        CHECK (canonical_content <> ''),
        CHECK (canonical_key <> ''),
        CHECK (length(payload_fingerprint) = 64)
    ) WITHOUT ROWID""",
    """CREATE INDEX memories_chronological
       ON memories (tenant_id, namespace, created_at, memory_id)""",
    """CREATE TABLE memory_sources (
        tenant_id TEXT NOT NULL,
        namespace TEXT NOT NULL,
        memory_id TEXT NOT NULL,
        event_id TEXT NOT NULL,
        ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
        source_span_json TEXT,
        extraction_method TEXT NOT NULL,
        PRIMARY KEY (tenant_id, namespace, memory_id, event_id),
        UNIQUE (tenant_id, namespace, memory_id, ordinal),
        FOREIGN KEY (tenant_id, namespace, memory_id)
            REFERENCES memories (tenant_id, namespace, memory_id),
        FOREIGN KEY (tenant_id, namespace, event_id)
            REFERENCES events (tenant_id, namespace, event_id)
    ) WITHOUT ROWID""",
    """CREATE INDEX memory_sources_event
       ON memory_sources (tenant_id, namespace, event_id, memory_id)""",
    """CREATE TABLE entities (
        tenant_id TEXT NOT NULL,
        namespace TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        canonical_name TEXT NOT NULL,
        normalized_name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (tenant_id, namespace, entity_id),
        UNIQUE (tenant_id, namespace, entity_type, normalized_name)
    ) WITHOUT ROWID""",
    """CREATE TABLE entity_aliases (
        tenant_id TEXT NOT NULL,
        namespace TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        normalized_alias TEXT NOT NULL,
        alias_name TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        source_event_id TEXT NOT NULL,
        PRIMARY KEY (tenant_id, namespace, entity_type, normalized_alias),
        FOREIGN KEY (tenant_id, namespace, entity_id)
            REFERENCES entities (tenant_id, namespace, entity_id),
        FOREIGN KEY (tenant_id, namespace, source_event_id)
            REFERENCES events (tenant_id, namespace, event_id)
    ) WITHOUT ROWID""",
    """CREATE TABLE memory_entities (
        tenant_id TEXT NOT NULL,
        namespace TEXT NOT NULL,
        memory_id TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        PRIMARY KEY (tenant_id, namespace, memory_id, entity_id),
        FOREIGN KEY (tenant_id, namespace, memory_id)
            REFERENCES memories (tenant_id, namespace, memory_id),
        FOREIGN KEY (tenant_id, namespace, entity_id)
            REFERENCES entities (tenant_id, namespace, entity_id)
    ) WITHOUT ROWID""",
    """CREATE INDEX memory_entities_entity
       ON memory_entities (tenant_id, namespace, entity_id, memory_id)""",
)

MIGRATIONS: dict[int, tuple[str, ...]] = {1: MIGRATION_1, 2: MIGRATION_2}


def user_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def is_empty_unowned_database(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE name NOT GLOB 'sqlite_*' LIMIT 1"
    ).fetchone()
    return row is None


_V1_OBJECTS = {
    ("table", "events"),
    ("index", "events_idempotency_key"),
    ("index", "events_chronological"),
    ("trigger", "events_no_update"),
    ("trigger", "events_no_delete"),
}
_V2_OBJECTS = {
    ("table", "memories"),
    ("index", "memories_chronological"),
    ("table", "memory_sources"),
    ("index", "memory_sources_event"),
    ("table", "entities"),
    ("table", "entity_aliases"),
    ("table", "memory_entities"),
    ("index", "memory_entities_entity"),
}


def _objects(connection: sqlite3.Connection) -> dict[tuple[str, str], str]:
    return {
        (row[0], row[1]): row[2] or ""
        for row in connection.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'"
        )
    }


def _matches_sql(actual: dict[tuple[str, str], str], expected: dict[tuple[str, str], str]) -> bool:
    normalize = lambda sql: " ".join(sql.split()).upper()
    return all(normalize(actual.get(key, "")) == normalize(sql) for key, sql in expected.items())


def verify_v1(connection: sqlite3.Connection, *, allow_v2: bool = False) -> bool:
    actual = _objects(connection)
    expected_keys = _V1_OBJECTS | (_V2_OBJECTS if allow_v2 else set())
    if set(actual) != expected_keys:
        return False
    expected_sql = {
        ("table", "events"): MIGRATION_1[0],
        ("index", "events_idempotency_key"): MIGRATION_1[1],
        ("index", "events_chronological"): MIGRATION_1[2],
        ("trigger", "events_no_update"): MIGRATION_1[3],
        ("trigger", "events_no_delete"): MIGRATION_1[4],
    }
    if not _matches_sql(actual, expected_sql):
        return False
    columns = connection.execute("PRAGMA table_info(events)").fetchall()
    if tuple(column[1] for column in columns) != (
        "tenant_id", "namespace", "event_id", "event_type", "source_type",
        "content", "source_reference_json", "occurred_at", "ingested_at",
        "idempotency_key", "metadata_json", "payload_fingerprint",
    ):
        return False
    if tuple(column[5] for column in columns[:3]) != (1, 2, 3):
        return False
    index_rows = {
        row[1]: row for row in connection.execute("PRAGMA index_list(events)")
    }
    unique = index_rows.get("events_idempotency_key")
    chronological = index_rows.get("events_chronological")
    if unique is None or unique[2] != 1 or unique[4] != 1:
        return False
    if chronological is None or chronological[2] != 0:
        return False
    for index, expected in (
        ("events_idempotency_key", ("tenant_id", "namespace", "idempotency_key")),
        ("events_chronological", ("tenant_id", "namespace", "occurred_at", "ingested_at", "event_id")),
    ):
        actual_columns = tuple(row[2] for row in connection.execute(f"PRAGMA index_info({index})"))
        if actual_columns != expected:
            return False
    return True


def verify_v2(connection: sqlite3.Connection) -> bool:
    if not verify_v1(connection, allow_v2=True):
        return False
    actual = _objects(connection)
    expected_sql = dict(zip(
        (
            ("table", "memories"), ("index", "memories_chronological"),
            ("table", "memory_sources"), ("index", "memory_sources_event"),
            ("table", "entities"), ("table", "entity_aliases"),
            ("table", "memory_entities"), ("index", "memory_entities_entity"),
        ),
        MIGRATION_2,
        strict=True,
    ))
    if not _matches_sql(actual, expected_sql):
        return False
    for table in ("memory_sources", "entity_aliases", "memory_entities"):
        if not list(connection.execute(f"PRAGMA foreign_key_list({table})")):
            return False
    return True
