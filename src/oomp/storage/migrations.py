"""Transactional, sequential SQLite schema migrations for source events only."""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

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

MIGRATIONS: dict[int, tuple[str, ...]] = {1: MIGRATION_1}


def user_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def is_empty_unowned_database(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE name NOT GLOB 'sqlite_*' LIMIT 1"
    ).fetchone()
    return row is None


def verify_v1(connection: sqlite3.Connection) -> bool:
    required = {
        ("table", "events"),
        ("index", "events_idempotency_key"),
        ("index", "events_chronological"),
        ("trigger", "events_no_update"),
        ("trigger", "events_no_delete"),
    }
    objects = {
        (row[0], row[1])
        for row in connection.execute(
            "SELECT type, name FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'"
        )
    }
    if objects != required:
        return False
    expected_sql = {
        ("table", "events"): MIGRATION_1[0],
        ("index", "events_idempotency_key"): MIGRATION_1[1],
        ("index", "events_chronological"): MIGRATION_1[2],
        ("trigger", "events_no_update"): MIGRATION_1[3],
        ("trigger", "events_no_delete"): MIGRATION_1[4],
    }
    actual_sql = {
        (row[0], row[1]): row[2]
        for row in connection.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'"
        )
    }
    normalize = lambda sql: " ".join(sql.split()).upper()
    if any(normalize(actual_sql.get(key, "")) != normalize(expected)
           for key, expected in expected_sql.items()):
        return False
    columns = connection.execute("PRAGMA table_info(events)").fetchall()
    names = tuple(column[1] for column in columns)
    if names != (
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
        actual = tuple(row[2] for row in connection.execute(f"PRAGMA index_info({index})"))
        if actual != expected:
            return False
    triggers = {
        row[0]: row[1].upper()
        for row in connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND name LIKE 'events_no_%'"
        )
    }
    if not all(("BEFORE UPDATE ON EVENTS" in triggers.get("events_no_update", ""),
                "BEFORE DELETE ON EVENTS" in triggers.get("events_no_delete", ""))):
        return False
    return True