# SQLite event storage — Stage 2

Stage 2 supplies a durable source-event log using Python's standard-library `sqlite3`. It stores original evidence and supports scoped chronological reads. It does not extract facts, build graphs, perform semantic search, generate summaries, run background jobs or expose MCP/network services.

## Configuration and initialization

`SQLiteEventStore(path=None, *, busy_timeout_ms=5000)` resolves configuration without opening a connection or creating a directory. Path precedence is explicit path/CLI `--db`, then `OOMP_DB_PATH`, then a platform user-data directory. Windows defaults to `%LOCALAPPDATA%\OOMP\events.sqlite3`, falling back to the user's `AppData\Local`; macOS uses `~/Library/Application Support/OOMP/events.sqlite3`, and other platforms use `$XDG_DATA_HOME/oomp/events.sqlite3` or `~/.local/share/oomp/events.sqlite3`. Production code contains no absolute machine-specific paths. Relative explicit/environment paths are resolved against the current directory. An empty explicit override or `:memory:` is rejected; this adapter is file-backed.

Only explicit `initialize()` creates parent directories and a new database. Append requires an existing initialized database. Read/status operations use a SQLite read-only URI and never create a missing database or parent. SQLite can require WAL/SHM coordination files for an existing WAL database; read-only mode is not a promise that the SQLite runtime never touches such sidecars. Do not use `immutable=1` to inspect an actively written database.

`sample.env` is illustrative. OOMP reads process environment variables and does not automatically load `.env` files. CLI diagnostics show path, existence, accessibility, schema version, journal mode and readiness, with no event contents or global event counts. A missing/unready database returns a nonzero status. Readiness checks schema and accessibility, not every stored row or fingerprint. `doctor` remains a package diagnostic and neither initializes nor requires storage.

## Original schema version 1

Version 1 has one application table, `events`. Version 2 retains it unchanged and adds the Stage 3 tables documented below:

| Column | Meaning |
| --- | --- |
| tenant_id, namespace, event_id | Composite event identity and isolation boundary |
| event_type, source_type, content | Original Stage 1 source evidence |
| source_reference_json | Full structured external provenance |
| occurred_at, ingested_at | Independent normalized UTC timestamps |
| idempotency_key | Optional retry identity within the scope |
| metadata_json | Immutable JSON evidence metadata |
| payload_fingerprint | SHA-256 of the stable logical payload |

The composite primary key is `(tenant_id, namespace, event_id)`. A partial unique index enforces `(tenant_id, namespace, idempotency_key)` when the key is non-null. The chronological index begins with tenant/namespace and then occurrence time, ingestion time and event ID. Ordinary API writes are parameterized SQL inserts.

Database timestamps use six fractional digits and UTC `Z` so text ordering exactly preserves chronological order, including whole seconds versus microseconds. JSON provenance/metadata is canonicalized with sorted object keys; domain reconstruction returns the original normalized instants and deeply immutable JSON values. Reads validate stored events and their logical fingerprints and fail with a sanitized error for malformed JSON, invalid domain values or mismatched fingerprints.

## Migration policy

The current `PRAGMA user_version` is 2. Version 0 is initialized only if the database contains no unrelated application objects. Schema identity/structure is checked before use; existing foreign or unsupported future schemas are rejected without resets or dropped tables. Repeated initialization preserves events.

Migrations are a sequential registry of trusted SQL statements. Statements and the version update execute in an explicit transaction; failures roll back schema/data/version changes. `executescript()` is deliberately avoided because Python 3.11 commits a pending transaction before running it. The mechanism supports future incremental migrations, and Stage 3 registers additive migration 2 after the unchanged migration 1. [Python sqlite3 transaction control](https://docs.python.org/3.11/library/sqlite3.html#transaction-control).

UPDATE and DELETE triggers protect ordinary event immutability. A future explicitly authorized migration/erasure workflow may need to replace those triggers transactionally. No ordinary update, delete, replace or privileged erasure API is implemented. Database/filesystem administrators can bypass logical protections; these are not an authenticity guarantee against administrators.

## Exact idempotency policy

The logical fingerprint includes tenant, namespace, event type, source type, verbatim content, the complete source reference, normalized occurrence time, and all metadata. It excludes event ID, ingestion time and idempotency key. Serialization sorts object keys recursively, preserves array order and Unicode/text spacing, and rejects non-finite JSON numbers. There is no semantic similarity or Unicode normalization; JSON numbers `1` and `1.0` remain distinct. Keep volatile transport/retry counters outside source metadata.

| Retry | Outcome |
| --- | --- |
| New scoped event ID and unused key | Insert and return the persisted event |
| Same scoped event ID, equivalent logical payload | Return the first persisted record, preserving original ingestion time |
| Same scoped idempotency key, equivalent payload, new temporary ID/ingestion time | Return the first persisted record; add no row |
| Same event ID or key, changed logical payload | Raise `IdempotencyConflictError`; leave original unchanged |
| Event ID and key resolve to different rows | Conflict, even when both payloads happen to match |
| Existing event ID plus a changed/new non-null key | Conflict; no silent idempotency alias is attached |
| Existing event ID with omitted key | Equivalent retry may return the original |
| Same IDs/keys in a different tenant or namespace | Independent records |

Deduplication requires reuse of a stable scoped event ID or idempotency key. A source's external event ID alone is not a global unique key. Fresh IDs with no shared retry key are not automatically deduplicated. Fingerprints define exact equivalence and detect accidental logical-payload corruption; they do not authenticate evidence or verify truth.

## Authorized API and pagination

The original EventStore `append(scope, event)` and `get(scope, event_id)` signatures are preserved. The protocol adds `list_events(scope, *, limit=100, after=None)` and `count_events(scope)`; all require an `AuthorizedScope` supplied by trusted service code. The boundary revalidates event/scope values and rejects event/cursor tenant or namespace mismatch before access. RequestedScope and event metadata cannot grant authority. Get returns `None` for an absent event in the authorized scope.

`list_events` returns an `EventPage` with an immutable tuple of events and an optional `EventCursor`. Both are defined in `oomp.domain.events`, without SQLite dependencies. The cursor contains tenant, namespace and the last event's ordering keys; it is a position, not an authorization token. Page size is a strict integer from 1 to 1000. SQL reads at most limit+1 rows using the scoped chronological index.

Ordering is `occurred_at ASC, ingested_at ASC, event_id ASC`. The next page selects tuples strictly after the cursor. This avoids offset shifts and duplicate records from ordinary insertion before a page. Paging is a live view, not a scan-wide snapshot: a later-arriving event whose key precedes the cursor will require a fresh scan to be seen. There is no unbounded/global list API or semantic query.

## Concurrency, resources and durability

Every operation creates and closes its own connection before returning; no store object retains a connection. A new instance therefore reads persisted state, not a process cache. Separate threads/processes can use independent connections. Foreign keys are enabled; busy timeout defaults to 5000 ms and can be explicitly set from 0 to 60000. A timeout produces a typed busy error, without partial event rows.

Append and migration use `BEGIN IMMEDIATE`. Scoped uniqueness constraints remain the final protection, rather than a process-local lock. WAL is requested when supported, with synchronous FULL; a rollback-journal fallback uses synchronous EXTRA. Errors are not hidden as successful writes. The actual mode is available in status. Power-loss behavior ultimately depends on the filesystem/device correctly honoring synchronization; restart tests do not simulate hardware failures. [SQLite durability settings](https://www.sqlite.org/pragma.html#pragma_synchronous).

Use a local disk. SQLite WAL coordination requires processes on the same host and does not support a network filesystem. This is not a multi-host synchronization service. [SQLite WAL documentation](https://www.sqlite.org/wal.html).

## Backup and privacy

Use SQLite's online backup API or an established consistent snapshot while the database is active. Copying only the main file during WAL writes can omit committed transactions that remain in the WAL; do not independently discard a live WAL/SHM file. Stop writers and perform a coordinated checkpoint/copy if using offline file backups. A backup command is not implemented in this stage. [SQLite online backup](https://www.sqlite.org/backup.html).

The database contains source text and metadata in plaintext. Tenant filtering protects service operations, not a person with direct filesystem/SQL access. Restrict file access and plan encryption/retention for deployment. Authorized privacy erasure must eventually remove protected content and dependent material from records, indexes, caches and backups; append-only correction is distinct from deletion. No erasure capability is claimed today.

## Windows commands

```powershell
$env:OOMP_DB_PATH = Join-Path $PWD 'data\events.sqlite3'
.\.venv\Scripts\oomp.exe storage status
.\.venv\Scripts\oomp.exe storage init
.\.venv\Scripts\oomp.exe storage status
.\.venv\Scripts\python.exe examples\stage2_event_roundtrip.py --db .\data\synthetic-demo.sqlite3
.\.venv\Scripts\python.exe -m pytest -v --basetemp .test-artifacts\pytest-stage2
```

The first status intentionally reports missing/unready without creating a database. The example uses synthetic records and a dedicated demonstration scope/database; it is safe to rerun. Tests use temporary file-backed databases, never the real user-data directory. Stage 2 acceptance passed: **120 tests in 22.18s**, including all original 79 cases. See [the actual validation record](stage2-validation.md) and [completion report](stage-2-report.md).

## Current schema version 2

| Table | Role and constraints |
| --- | --- |
| memories | Full MemoryNode scalar fields, tags/metadata JSON and stable-payload fingerprint; scoped ID primary key and scoped canonical-key uniqueness |
| memory_sources | Many-to-many memory/event evidence, insertion ordinal, optional exact source-span JSON and extraction method; scoped foreign keys to both records |
| entities | Scoped stable entity ID, type, canonical/normalized name and created_at; scoped type/name uniqueness |
| entity_aliases | Scoped type/normalized-alias uniqueness, display name, entity ID and originating event ID; scoped foreign keys |
| memory_entities | Unique scoped memory/entity pair, with scoped foreign keys to both records |

Chronological memory, reverse source and reverse entity indexes serve bounded lookups. These are entity associations, without graph-edge or vector tables. Foreign keys are enabled on each connection before transactions; composite references include both tenant and namespace. [SQLite foreign-key requirements](https://www.sqlite.org/foreignkeys.html).

Fresh initialize runs migrations 1 and 2 in one explicit transaction. A genuine version 1 database is structurally validated before upgrade; its event data, fingerprints, indexes and immutability triggers are preserved. Unsupported future/foreign/damaged schemas are rejected. A failed migration 2 leaves version 1 and its events intact. Repeated initialize is safe. Read-only status reports a valid version 1 database as needing an explicit upgrade; memory operations never initialize or migrate implicitly.

## Memory and entity APIs

`SQLiteMemoryStore` implements `put(scope,node)`, `get(scope,id)`, `find_by_canonical_key(scope,key)`, `list_memories(scope,limit=100,after=None)` and `attach_evidence(scope,memory_id,event_id)`. `upsert` returns the retained memory identity, `count_memories` is scoped, and `list_entities` returns linked entity records. Nodes are revalidated, including actual source existence and exact SourceReference correspondence. An equivalent insert unions evidence; conflicting canonical key/content or competing ID/key identities fail without overwriting.

Memory pages use `(created_at,memory_id)` ascending keyset order and strict sizes 1-100, fetching limit+1 nodes. Cursors must match AuthorizedScope. Pages are live views, not scan-wide snapshots. Each reconstructed memory is bounded to 1000 evidence links. Per-event batches contain at most 32 candidates; entity alias sets and per-memory entity associations are bounded to 64. Exceeding a bound raises an error and rolls back rather than dropping evidence.

`SQLiteEntityStore.resolve(scope,mention)`, `get` and `count_entities` require authorized scope. Explicit alias evidence must come from an actual same-scope event. Resolution matches normalized names and aliases within an entity type. If supplied names already identify different entities, the operation rejects the ambiguous merge. No general entity merge/deletion API exists.

## Per-event atomic processing

`apply_batch(scope,event_id,writes)` uses one connection and BEGIN IMMEDIATE for all derived rows: entity resolution, memory insert/reuse, evidence and entity links. SQLite allows a single writer and BEGIN IMMEDIATE may fail when another writer holds the database; the configured busy timeout bounds waiting. Any failure rolls back the batch, and the independent immutable event remains stored. [SQLite transaction semantics](https://www.sqlite.org/lang_transaction.html).

Canonical fingerprints compare stable content/type/key/status/validity/confidence/tags/metadata, excluding record times and accumulated proof. Evidence attachment preserves created_at and advances updated_at only for a new link. Reprocessing the same event creates no duplicate canonical memory, source pair or entity pair. A new event expressing the same supported claim adds evidence to the first memory ID. No inferred supersession, deletion or unbounded scan API is supplied.

Stage 3 memory text, metadata and entity names are plaintext, just like source events. Constraints and fingerprints protect API consistency, not physical database administrators or tamper-proof authenticity.
