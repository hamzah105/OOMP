"""Transactional, sequential SQLite migrations for events and canonical memories."""

from __future__ import annotations

import sqlite3
from datetime import datetime

SCHEMA_VERSION = 5

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

_V4_OBJECTS = {
    ("table", "memory_fts_docs"), ("index", "memory_fts_docs_scope"),
    ("table", "memory_fts"),
    *(("table", f"memory_fts_{suffix}") for suffix in ("config", "content", "data", "docsize", "idx")),
    ("trigger", "memories_fts_insert"),
    ("table", "embedding_spaces"), ("table", "memory_embeddings"),
    ("index", "memory_embeddings_space"),
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


def verify_v1(connection: sqlite3.Connection, *, allow_v2: bool = False, allow_v3: bool = False, allow_v4: bool = False, allow_v5: bool = False) -> bool:
    actual = _objects(connection)
    expected_keys = _V1_OBJECTS | (_V2_OBJECTS if allow_v2 else set()) | (_V3_OBJECTS if allow_v3 else set()) | (_V4_OBJECTS if allow_v4 else set()) | (_V5_OBJECTS if allow_v5 else set())
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


def verify_v2(connection: sqlite3.Connection, *, allow_v3: bool = False, allow_v4: bool = False, allow_v5: bool = False) -> bool:
    if not verify_v1(connection, allow_v2=True, allow_v3=allow_v3, allow_v4=allow_v4, allow_v5=allow_v5):
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

# Stage 4 adds graph assertions and independent system-observed recording times.
# MIGRATION_1 and MIGRATION_2 intentionally remain byte-for-byte unchanged.
MIGRATION_3: tuple[str, ...] = (
    """CREATE TABLE graph_meta (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        history_start TEXT NOT NULL
    )""",
    """INSERT INTO graph_meta (id, history_start)
       VALUES (1, oomp_recorded_at())""",
    """CREATE TABLE memory_recordings (
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL, memory_id TEXT NOT NULL,
        recorded_at TEXT,
        PRIMARY KEY (tenant_id, namespace, memory_id),
        FOREIGN KEY (tenant_id, namespace, memory_id)
            REFERENCES memories (tenant_id, namespace, memory_id)
    ) WITHOUT ROWID""",
    """INSERT INTO memory_recordings (tenant_id, namespace, memory_id, recorded_at)
       SELECT tenant_id, namespace, memory_id, NULL FROM memories""",
    """CREATE TABLE memory_source_recordings (
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL,
        memory_id TEXT NOT NULL, event_id TEXT NOT NULL, recorded_at TEXT,
        PRIMARY KEY (tenant_id, namespace, memory_id, event_id),
        FOREIGN KEY (tenant_id, namespace, memory_id, event_id)
            REFERENCES memory_sources (tenant_id, namespace, memory_id, event_id)
    ) WITHOUT ROWID""",
    """INSERT INTO memory_source_recordings
       (tenant_id, namespace, memory_id, event_id, recorded_at)
       SELECT tenant_id, namespace, memory_id, event_id, NULL FROM memory_sources""",
    """CREATE TRIGGER memories_record_insert AFTER INSERT ON memories BEGIN
       INSERT INTO memory_recordings (tenant_id, namespace, memory_id, recorded_at)
       VALUES (NEW.tenant_id, NEW.namespace, NEW.memory_id,
               oomp_recorded_at());
       END""",
    """CREATE TRIGGER memory_sources_record_insert AFTER INSERT ON memory_sources BEGIN
       INSERT INTO memory_source_recordings
           (tenant_id, namespace, memory_id, event_id, recorded_at)
       VALUES (NEW.tenant_id, NEW.namespace, NEW.memory_id, NEW.event_id,
               oomp_recorded_at());
       END""",
    """CREATE TABLE memory_edges (
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL, edge_id TEXT NOT NULL,
        source_node_id TEXT NOT NULL, target_node_id TEXT NOT NULL,
        relationship_type TEXT NOT NULL, logical_key TEXT NOT NULL,
        confidence REAL, created_at TEXT NOT NULL, recorded_at TEXT NOT NULL,
        recorded_by TEXT NOT NULL, valid_from TEXT, valid_until TEXT,
        status TEXT NOT NULL, reason TEXT, policy_version TEXT,
        payload_fingerprint TEXT NOT NULL CHECK (length(payload_fingerprint) = 64),
        PRIMARY KEY (tenant_id, namespace, edge_id),
        UNIQUE (tenant_id, namespace, logical_key),
        FOREIGN KEY (tenant_id, namespace, source_node_id)
            REFERENCES memories (tenant_id, namespace, memory_id),
        FOREIGN KEY (tenant_id, namespace, target_node_id)
            REFERENCES memories (tenant_id, namespace, memory_id)
    ) WITHOUT ROWID""",
    """CREATE INDEX memory_edges_outgoing
       ON memory_edges (tenant_id, namespace, source_node_id, relationship_type, recorded_at, edge_id)""",
    """CREATE INDEX memory_edges_incoming
       ON memory_edges (tenant_id, namespace, target_node_id, relationship_type, recorded_at, edge_id)""",
    """CREATE INDEX memory_edges_chronological
       ON memory_edges (tenant_id, namespace, recorded_at, edge_id)""",
    """CREATE TABLE edge_evidence (
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL, edge_id TEXT NOT NULL,
        event_id TEXT NOT NULL, ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
        recorded_at TEXT NOT NULL,
        PRIMARY KEY (tenant_id, namespace, edge_id, event_id),
        UNIQUE (tenant_id, namespace, edge_id, ordinal),
        FOREIGN KEY (tenant_id, namespace, edge_id)
            REFERENCES memory_edges (tenant_id, namespace, edge_id),
        FOREIGN KEY (tenant_id, namespace, event_id)
            REFERENCES events (tenant_id, namespace, event_id)
    ) WITHOUT ROWID""",
    """CREATE INDEX edge_evidence_event
       ON edge_evidence (tenant_id, namespace, event_id, edge_id)""",
    """CREATE TABLE topics (
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL, topic_id TEXT NOT NULL,
        name TEXT NOT NULL CHECK (name <> ''), parent_id TEXT, recorded_at TEXT NOT NULL,
        PRIMARY KEY (tenant_id, namespace, topic_id),
        FOREIGN KEY (tenant_id, namespace, parent_id)
            REFERENCES topics (tenant_id, namespace, topic_id)
    ) WITHOUT ROWID""",
    """CREATE INDEX topics_children
       ON topics (tenant_id, namespace, parent_id, topic_id)""",
    """CREATE TABLE topic_memberships (
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL,
        topic_id TEXT NOT NULL, memory_id TEXT NOT NULL, recorded_at TEXT NOT NULL,
        PRIMARY KEY (tenant_id, namespace, topic_id, memory_id),
        FOREIGN KEY (tenant_id, namespace, topic_id)
            REFERENCES topics (tenant_id, namespace, topic_id),
        FOREIGN KEY (tenant_id, namespace, memory_id)
            REFERENCES memories (tenant_id, namespace, memory_id)
    ) WITHOUT ROWID""",
    """CREATE INDEX topic_memberships_memory
       ON topic_memberships (tenant_id, namespace, memory_id, topic_id)""",
    """CREATE TRIGGER memory_edges_no_update BEFORE UPDATE ON memory_edges BEGIN
       SELECT RAISE(ABORT, 'graph edges are immutable');
       END""",
    """CREATE TRIGGER memory_edges_no_delete BEFORE DELETE ON memory_edges BEGIN
       SELECT RAISE(ABORT, 'graph edges are immutable');
       END""",
    """CREATE TRIGGER edge_evidence_no_update BEFORE UPDATE ON edge_evidence BEGIN
       SELECT RAISE(ABORT, 'edge evidence is immutable');
       END""",
    """CREATE TRIGGER edge_evidence_no_delete BEFORE DELETE ON edge_evidence BEGIN
       SELECT RAISE(ABORT, 'edge evidence is immutable');
       END""",
)

_V3_OBJECTS = {
    ("table", "graph_meta"),
    ("table", "memory_recordings"),
    ("table", "memory_source_recordings"),
    ("trigger", "memories_record_insert"),
    ("trigger", "memory_sources_record_insert"),
    ("table", "memory_edges"),
    ("index", "memory_edges_outgoing"),
    ("index", "memory_edges_incoming"),
    ("index", "memory_edges_chronological"),
    ("table", "edge_evidence"),
    ("index", "edge_evidence_event"),
    ("table", "topics"),
    ("index", "topics_children"),
    ("table", "topic_memberships"),
    ("index", "topic_memberships_memory"),
    ("trigger", "memory_edges_no_update"),
    ("trigger", "memory_edges_no_delete"),
    ("trigger", "edge_evidence_no_update"),
    ("trigger", "edge_evidence_no_delete"),
}


def verify_v3(connection: sqlite3.Connection, *, allow_v4: bool = False, allow_v5: bool = False) -> bool:
    if not verify_v2(connection, allow_v3=True, allow_v4=allow_v4, allow_v5=allow_v5):
        return False
    keys = (
        ("table", "graph_meta"), ("table", "memory_recordings"),
        ("table", "memory_source_recordings"), ("trigger", "memories_record_insert"),
        ("trigger", "memory_sources_record_insert"), ("table", "memory_edges"),
        ("index", "memory_edges_outgoing"), ("index", "memory_edges_incoming"),
        ("index", "memory_edges_chronological"), ("table", "edge_evidence"),
        ("index", "edge_evidence_event"), ("table", "topics"),
        ("index", "topics_children"), ("table", "topic_memberships"),
        ("index", "topic_memberships_memory"), ("trigger", "memory_edges_no_update"),
        ("trigger", "memory_edges_no_delete"), ("trigger", "edge_evidence_no_update"),
        ("trigger", "edge_evidence_no_delete"),
    )
    statements = tuple(statement for statement in MIGRATION_3 if statement.lstrip().upper().startswith(("CREATE TABLE", "CREATE INDEX", "CREATE TRIGGER")))
    if not _matches_sql(_objects(connection), dict(zip(keys, statements, strict=True))):
        return False
    for table in ("memory_recordings", "memory_source_recordings", "memory_edges",
                  "edge_evidence", "topics", "topic_memberships"):
        if not list(connection.execute(f"PRAGMA foreign_key_list({table})")):
            return False
    row = connection.execute("SELECT history_start FROM graph_meta WHERE id=1").fetchone()
    if row is None or not isinstance(row[0], str) or len(row[0]) != 27:
        return False
    try:
        return datetime.strptime(row[0], "%Y-%m-%dT%H:%M:%S.%fZ").strftime("%Y-%m-%dT%H:%M:%S.%fZ") == row[0]
    except ValueError:
        return False
MIGRATION_4: tuple[str, ...] = (
    """CREATE TABLE memory_fts_docs (
        doc_id INTEGER PRIMARY KEY,
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL, memory_id TEXT NOT NULL,
        UNIQUE (tenant_id, namespace, memory_id),
        FOREIGN KEY (tenant_id, namespace, memory_id)
            REFERENCES memories (tenant_id, namespace, memory_id)
    )""",
    """CREATE INDEX memory_fts_docs_scope
       ON memory_fts_docs (tenant_id, namespace, doc_id)""",
    """CREATE VIRTUAL TABLE memory_fts USING fts5(
        canonical_content, tokenize='unicode61')""",
    """INSERT INTO memory_fts_docs (tenant_id, namespace, memory_id)
       SELECT tenant_id, namespace, memory_id FROM memories
       ORDER BY tenant_id, namespace, memory_id""",
    """INSERT INTO memory_fts (rowid, canonical_content)
       SELECT d.doc_id, m.canonical_content FROM memory_fts_docs d
       JOIN memories m ON m.tenant_id=d.tenant_id
                     AND m.namespace=d.namespace AND m.memory_id=d.memory_id""",
    """CREATE TRIGGER memories_fts_insert AFTER INSERT ON memories BEGIN
       INSERT INTO memory_fts_docs (tenant_id, namespace, memory_id)
       VALUES (NEW.tenant_id, NEW.namespace, NEW.memory_id);
       INSERT INTO memory_fts (rowid, canonical_content)
       VALUES (last_insert_rowid(), NEW.canonical_content);
       END""",
    """CREATE TABLE embedding_spaces (
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL,
        provider TEXT NOT NULL, model TEXT NOT NULL, config_version TEXT NOT NULL,
        dimension INTEGER NOT NULL CHECK (dimension BETWEEN 1 AND 4096),
        PRIMARY KEY (tenant_id, namespace, provider, model, config_version)
    ) WITHOUT ROWID""",
    """CREATE TABLE memory_embeddings (
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL, memory_id TEXT NOT NULL,
        provider TEXT NOT NULL, model TEXT NOT NULL, config_version TEXT NOT NULL,
        dimension INTEGER NOT NULL CHECK (dimension BETWEEN 1 AND 4096),
        content_digest TEXT NOT NULL CHECK (length(content_digest) = 64),
        vector_blob BLOB NOT NULL, generated_at TEXT NOT NULL,
        PRIMARY KEY (tenant_id, namespace, memory_id, provider, model, config_version),
        FOREIGN KEY (tenant_id, namespace, memory_id)
            REFERENCES memories (tenant_id, namespace, memory_id),
        FOREIGN KEY (tenant_id, namespace, provider, model, config_version)
            REFERENCES embedding_spaces (tenant_id, namespace, provider, model, config_version)
    ) WITHOUT ROWID""",
    """CREATE INDEX memory_embeddings_space
       ON memory_embeddings (tenant_id, namespace, provider, model, config_version, memory_id)""",
)


def verify_v4(connection: sqlite3.Connection, *, allow_v5: bool = False) -> bool:
    if not verify_v3(connection, allow_v4=True, allow_v5=allow_v5):
        return False
    actual = _objects(connection)
    keys = (
        ("table", "memory_fts_docs"), ("index", "memory_fts_docs_scope"),
        ("table", "memory_fts"), ("trigger", "memories_fts_insert"),
        ("table", "embedding_spaces"), ("table", "memory_embeddings"),
        ("index", "memory_embeddings_space"),
    )
    statements = tuple(statement for statement in MIGRATION_4 if statement.lstrip().upper().startswith(("CREATE TABLE", "CREATE INDEX", "CREATE VIRTUAL TABLE", "CREATE TRIGGER")))
    if not _matches_sql(actual, dict(zip(keys, statements, strict=True))):
        return False
    for table in ("memory_fts_docs", "memory_embeddings"):
        if not list(connection.execute(f"PRAGMA foreign_key_list({table})")):
            return False
    shadows = {
        ("table", "memory_fts_config"): "CREATE TABLE 'memory_fts_config'(k PRIMARY KEY, v) WITHOUT ROWID",
        ("table", "memory_fts_content"): "CREATE TABLE 'memory_fts_content'(id INTEGER PRIMARY KEY, c0)",
        ("table", "memory_fts_data"): "CREATE TABLE 'memory_fts_data'(id INTEGER PRIMARY KEY, block BLOB)",
        ("table", "memory_fts_docsize"): "CREATE TABLE 'memory_fts_docsize'(id INTEGER PRIMARY KEY, sz BLOB)",
        ("table", "memory_fts_idx"): "CREATE TABLE 'memory_fts_idx'(segid, term, pgno, PRIMARY KEY(segid, term)) WITHOUT ROWID",
    }
    if not _matches_sql(actual, shadows):
        return False
    try:
        connection.execute("SELECT rowid FROM memory_fts LIMIT 1").fetchone()
    except sqlite3.Error:
        return False
    return True


MIGRATIONS: dict[int, tuple[str, ...]] = {1: MIGRATION_1, 2: MIGRATION_2, 3: MIGRATION_3, 4: MIGRATION_4}

# Stage 6 adds durable intake, scoped jobs, projections and private erasure markers.
# Historical migrations remain unchanged.
MIGRATION_5: tuple[str, ...] = (
    """CREATE TABLE mind_event_outbox (
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL, event_id TEXT NOT NULL,
        inserted_at TEXT NOT NULL, dispatched_at TEXT,
        PRIMARY KEY (tenant_id, namespace, event_id),
        FOREIGN KEY (tenant_id, namespace, event_id)
            REFERENCES events (tenant_id, namespace, event_id)
    ) WITHOUT ROWID""",
    """CREATE INDEX mind_outbox_pending
       ON mind_event_outbox (tenant_id, namespace, dispatched_at, inserted_at, event_id)""",
    """CREATE TRIGGER events_mind_outbox_insert AFTER INSERT ON events BEGIN
       INSERT INTO mind_event_outbox
           (tenant_id, namespace, event_id, inserted_at)
       VALUES (NEW.tenant_id, NEW.namespace, NEW.event_id, oomp_recorded_at());
       END""",
    """CREATE TABLE mind_erased_events (
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL, event_id TEXT NOT NULL,
        idempotency_key TEXT, erased_at TEXT NOT NULL, operation_id TEXT NOT NULL,
        operator_id TEXT NOT NULL,
        PRIMARY KEY (tenant_id, namespace, event_id)
    ) WITHOUT ROWID""",
    """CREATE UNIQUE INDEX mind_erased_event_keys
       ON mind_erased_events (tenant_id, namespace, idempotency_key)
       WHERE idempotency_key IS NOT NULL""",
    """CREATE TRIGGER events_mind_erasure_guard BEFORE INSERT ON events
       WHEN EXISTS (
           SELECT 1 FROM mind_erased_events e
           WHERE e.tenant_id=NEW.tenant_id AND e.namespace=NEW.namespace
             AND (e.event_id=NEW.event_id OR
                  (NEW.idempotency_key IS NOT NULL AND e.idempotency_key=NEW.idempotency_key))
       ) BEGIN
       SELECT RAISE(ABORT, 'erased source event cannot be reinserted');
       END""",
    """CREATE TABLE mind_jobs (
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL, job_id TEXT NOT NULL,
        job_type TEXT NOT NULL, target_type TEXT NOT NULL, target_id TEXT NOT NULL,
        idempotency_key TEXT NOT NULL, status TEXT NOT NULL
            CHECK (status IN ('queued','running','retry_wait','completed','failed','cancelled')),
        priority INTEGER NOT NULL CHECK (priority BETWEEN -100 AND 100),
        attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
        max_attempts INTEGER NOT NULL CHECK (max_attempts BETWEEN 1 AND 20),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, available_at TEXT NOT NULL,
        lease_owner TEXT, lease_expires_at TEXT,
        fencing_token INTEGER NOT NULL DEFAULT 0 CHECK (fencing_token >= 0),
        policy_version TEXT NOT NULL, config_json TEXT NOT NULL,
        last_error_code TEXT,
        PRIMARY KEY (tenant_id, namespace, job_id),
        UNIQUE (tenant_id, namespace, idempotency_key),
        CHECK ((lease_owner IS NULL) = (lease_expires_at IS NULL)),
        CHECK ((status = 'running') = (lease_owner IS NOT NULL))
    ) WITHOUT ROWID""",
    """CREATE INDEX mind_jobs_ready
       ON mind_jobs (tenant_id, namespace, status, available_at, priority DESC, job_id)""",
    """CREATE INDEX mind_jobs_lease
       ON mind_jobs (tenant_id, namespace, status, lease_expires_at, job_id)""",
    """CREATE INDEX mind_jobs_target
       ON mind_jobs (tenant_id, namespace, target_type, target_id, job_id)""",
    """CREATE TABLE mind_job_attempts (
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL, job_id TEXT NOT NULL,
        attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
        fencing_token INTEGER NOT NULL CHECK (fencing_token >= 1),
        worker_id TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT,
        status TEXT NOT NULL CHECK (status IN ('running','completed','retry_wait','failed','expired','cancelled')),
        error_code TEXT,
        PRIMARY KEY (tenant_id, namespace, job_id, attempt_number),
        UNIQUE (tenant_id, namespace, job_id, fencing_token),
        FOREIGN KEY (tenant_id, namespace, job_id)
            REFERENCES mind_jobs (tenant_id, namespace, job_id)
    ) WITHOUT ROWID""",
    """CREATE INDEX mind_attempts_worker
       ON mind_job_attempts (tenant_id, namespace, worker_id, started_at, job_id)""",
    """CREATE TABLE mind_maintenance_audit (
        audit_id INTEGER PRIMARY KEY,
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL,
        job_id TEXT, operation_type TEXT NOT NULL, policy_version TEXT NOT NULL,
        actor_id TEXT NOT NULL, recorded_at TEXT NOT NULL,
        status TEXT NOT NULL, error_code TEXT, affected_count INTEGER NOT NULL
            CHECK (affected_count >= 0),
        target_type TEXT, target_id TEXT,
        FOREIGN KEY (tenant_id, namespace, job_id)
            REFERENCES mind_jobs (tenant_id, namespace, job_id)
    )""",
    """CREATE INDEX mind_audit_scope
       ON mind_maintenance_audit (tenant_id, namespace, recorded_at, audit_id)""",
    """CREATE TABLE mind_summary_revisions (
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL,
        revision_id TEXT NOT NULL, topic_id TEXT NOT NULL,
        revision_number INTEGER NOT NULL CHECK (revision_number >= 1),
        content TEXT NOT NULL CHECK (content <> '' AND length(content) <= 4096),
        source_fingerprint TEXT NOT NULL CHECK (length(source_fingerprint) = 64),
        policy_version TEXT NOT NULL, recorded_at TEXT NOT NULL, retired_at TEXT,
        PRIMARY KEY (tenant_id, namespace, revision_id),
        UNIQUE (tenant_id, namespace, topic_id, revision_number),
        FOREIGN KEY (tenant_id, namespace, topic_id)
            REFERENCES topics (tenant_id, namespace, topic_id)
    ) WITHOUT ROWID""",
    """CREATE UNIQUE INDEX mind_summary_current
       ON mind_summary_revisions (tenant_id, namespace, topic_id)
       WHERE retired_at IS NULL""",
    """CREATE TABLE mind_summary_sources (
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL,
        revision_id TEXT NOT NULL, memory_id TEXT NOT NULL, event_id TEXT NOT NULL,
        PRIMARY KEY (tenant_id, namespace, revision_id, memory_id, event_id),
        FOREIGN KEY (tenant_id, namespace, revision_id)
            REFERENCES mind_summary_revisions (tenant_id, namespace, revision_id),
        FOREIGN KEY (tenant_id, namespace, memory_id, event_id)
            REFERENCES memory_sources (tenant_id, namespace, memory_id, event_id)
    ) WITHOUT ROWID""",
    """CREATE INDEX mind_summary_sources_memory
       ON mind_summary_sources (tenant_id, namespace, memory_id, event_id, revision_id)""",
    """CREATE TABLE mind_review_proposals (
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL, proposal_id TEXT NOT NULL,
        source_memory_id TEXT NOT NULL, target_memory_id TEXT NOT NULL,
        relationship_type TEXT NOT NULL, source_event_ids_json TEXT NOT NULL,
        reason TEXT NOT NULL, policy_version TEXT NOT NULL, status TEXT NOT NULL
            CHECK (status IN ('pending','approved','rejected')),
        recorded_at TEXT NOT NULL, decision_at TEXT, decided_by TEXT,
        PRIMARY KEY (tenant_id, namespace, proposal_id),
        FOREIGN KEY (tenant_id, namespace, source_memory_id)
            REFERENCES memories (tenant_id, namespace, memory_id),
        FOREIGN KEY (tenant_id, namespace, target_memory_id)
            REFERENCES memories (tenant_id, namespace, memory_id)
    ) WITHOUT ROWID""",
    """CREATE INDEX mind_reviews_pending
       ON mind_review_proposals (tenant_id, namespace, status, recorded_at, proposal_id)""",
    """CREATE TABLE mind_retractions (
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL,
        memory_id TEXT NOT NULL, event_id TEXT NOT NULL,
        recorded_at TEXT NOT NULL, reason_code TEXT NOT NULL,
        operator_id TEXT NOT NULL,
        PRIMARY KEY (tenant_id, namespace, memory_id, event_id, recorded_at),
        FOREIGN KEY (tenant_id, namespace, memory_id, event_id)
            REFERENCES memory_sources (tenant_id, namespace, memory_id, event_id)
    ) WITHOUT ROWID""",
    """CREATE INDEX mind_retractions_memory
       ON mind_retractions (tenant_id, namespace, memory_id, recorded_at, event_id)""",
)


_V5_OBJECTS = {
    ("table", "mind_event_outbox"), ("index", "mind_outbox_pending"),
    ("trigger", "events_mind_outbox_insert"),
    ("table", "mind_erased_events"), ("index", "mind_erased_event_keys"),
    ("trigger", "events_mind_erasure_guard"),
    ("table", "mind_jobs"), ("index", "mind_jobs_ready"),
    ("index", "mind_jobs_lease"), ("index", "mind_jobs_target"),
    ("table", "mind_job_attempts"), ("index", "mind_attempts_worker"),
    ("table", "mind_maintenance_audit"), ("index", "mind_audit_scope"),
    ("table", "mind_summary_revisions"), ("index", "mind_summary_current"),
    ("table", "mind_summary_sources"), ("index", "mind_summary_sources_memory"),
    ("table", "mind_review_proposals"), ("index", "mind_reviews_pending"),
    ("table", "mind_retractions"), ("index", "mind_retractions_memory"),
}


def verify_v5(connection: sqlite3.Connection) -> bool:
    if not verify_v4(connection, allow_v5=True):
        return False
    actual = _objects(connection)
    keys = (
        ("table", "mind_event_outbox"), ("index", "mind_outbox_pending"),
        ("trigger", "events_mind_outbox_insert"),
        ("table", "mind_erased_events"), ("index", "mind_erased_event_keys"),
        ("trigger", "events_mind_erasure_guard"),
        ("table", "mind_jobs"), ("index", "mind_jobs_ready"),
        ("index", "mind_jobs_lease"), ("index", "mind_jobs_target"),
        ("table", "mind_job_attempts"), ("index", "mind_attempts_worker"),
        ("table", "mind_maintenance_audit"), ("index", "mind_audit_scope"),
        ("table", "mind_summary_revisions"), ("index", "mind_summary_current"),
        ("table", "mind_summary_sources"), ("index", "mind_summary_sources_memory"),
        ("table", "mind_review_proposals"), ("index", "mind_reviews_pending"),
        ("table", "mind_retractions"), ("index", "mind_retractions_memory"),
    )
    statements = tuple(s for s in MIGRATION_5 if s.lstrip().upper().startswith(
        ("CREATE TABLE", "CREATE INDEX", "CREATE UNIQUE INDEX", "CREATE TRIGGER")
    ))
    if not _matches_sql(actual, dict(zip(keys, statements, strict=True))):
        return False
    for table in ("mind_event_outbox", "mind_job_attempts", "mind_summary_revisions",
                  "mind_summary_sources", "mind_review_proposals", "mind_retractions"):
        if not list(connection.execute(f"PRAGMA foreign_key_list({table})")):
            return False
    return True


MIGRATIONS[5] = MIGRATION_5