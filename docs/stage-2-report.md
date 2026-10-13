# OOMP Stage 2 completion report

Stage 2 acceptance passed on 2026-10-14 (Asia/Karachi): **120 tests passed in 22.18 seconds**, including all original 79 Stage 1 cases. Work stops after Persistent Event Storage.

1. **Workspace.** `D:\Desktop\OOMP`, independent of TRACE. Existing user commit `44fa795` on main was preserved. No TRACE checkout/file was accessed or modified.

2. **Files created (13).** `src/oomp/storage/__init__.py`, `config.py`, `errors.py`, `migrations.py`, `sqlite.py`; `src/oomp/domain/events.py`; `tests/test_stage2_storage.py`; `tests/test_stage2_cli.py`; `examples/stage2_event_roundtrip.py`; `sample.env`; `docs/storage.md`; `docs/stage2-validation.md`; this `docs/stage-2-report.md`. Temporary databases, logs and environments are ignored artifacts, not source files.

3. **Files modified (8).** `.gitignore`, `README.md`, `docs/architecture.md`, `docs/memory-model.md`, `docs/security-model.md`, `docs/roadmap.md`, `src/oomp/cli.py`, `src/oomp/domain/interfaces.py`. The original test module, domain models/enums/retrieval schemas, version/dependencies and research hypotheses were unchanged.

4. **SQLite architecture.** MemoryEvent → provider-neutral EventStore → SQLiteEventStore → a configurable file-backed SQLite database. SQL exists only in storage/migrations; domain and CLI contain no SQL. Each operation opens/closes its own connection and returns validated immutable domain values, with no process cache or shared persistent connection.

5. **Schema.** Version 1 has one `events` table: tenant_id, namespace, event_id, event_type, source_type, content, source_reference_json, occurred_at, ingested_at, idempotency_key, metadata_json, payload_fingerprint. All columns are TEXT; only the key is nullable. Primary identity is tenant/namespace/event_id; non-null keys are unique within tenant/namespace. The chronological index matches the scoped ordering. UPDATE/DELETE triggers protect ordinary immutability; no memory/graph placeholder tables exist.

6. **Migration/versioning.** PRAGMA user_version=1, sequential transactional trusted SQL registry, rollback on failure, no executescript implicit commits. Repeated initialization preserves existing records. Foreign/uninitialized/invalid/future schemas fail explicitly instead of being reset. Future schema upgrades require a migration and corresponding schema validation; no version 2 is implemented.

7. **EventStore API.** Original `append(scope,event)->MemoryEvent` and `get(scope,event_id)->MemoryEvent|None` preserved. Added `list_events(scope,*,limit=100,after=None)->EventPage` and `count_events(scope)->int`; EventCursor/EventPage are independent domain contracts. Explicit `initialize()->1` and metadata-only `status()` belong to the adapter.

8. **Immutability.** No ordinary update/delete/replace methods. Original content, source type, provenance, occurrence and ingestion values remain unchanged after retries. Trigger replacement and privacy erasure require a future separately authorized capability; administrators can still manipulate the physical database.

9. **Idempotency.** An equivalent event-ID/key replay returns the first persisted record. A new retry ID or ingestion timestamp does not add a row when a stable key matches. Changed stable evidence or conflicting dual identifiers raise IdempotencyConflictError. Changed/new non-null keys cannot be attached as silent aliases to existing events; omitted-key replay by stable event ID is allowed.

10. **Fingerprint.** SHA-256 of canonical sorted/compact finite JSON including tenant, namespace, event/source type, exact content, full provenance, occurrence time and all metadata. Excludes event_id, ingested_at and idempotency_key. Array order, whitespace, Unicode and numeric 1 versus 1.0 remain meaningful. No embedding/similarity deduplication or truth verification. Reuse a stable scoped ID or key; fresh unlinked IDs are not globally deduplicated.

11. **Authorization.** Every event operation requires and revalidates a trusted-service AuthorizedScope. Event/cursor tenant and namespace must agree before database access. Every data query constrains both partition columns. RequestedScope or metadata principal claims grant no authority. Authentication/grants are future service concerns, not proven by constructing a model.

12. **Ordering/pagination.** Occurred-at, ingested-at and event-ID ascending, with fixed six-digit UTC time encoding. Strict page size 1–1000, default 100; scoped keyset tuple comparisons fetch at most limit+1 rows. Cursor scopes are checked. A live scan can miss newly inserted backdated events behind its cursor; start a new scan to see them.

13. **Concurrency.** Independent connections, FK checks, bounded busy timeout (default 5000 ms), explicit BEGIN IMMEDIATE, transactional commits/rollback and database uniqueness constraints. WAL uses synchronous FULL; fallback uses EXTRA. No process-local lock is the correctness mechanism. Same-host/local-disk use; no cloud/multi-host synchronization.

14. **Durable restart results.** Real file-backed single/multiple event tests reopened completely new store instances and recovered full validated content, IDs, references, nested metadata and normalized timestamps. Separate example runs retained exactly two synthetic events.

15. **CLI.** Added `oomp storage init --db PATH` and `oomp storage status --db PATH`, also available through python -m. Missing status exits 1 without creating parent/database. Init/status report schema/readiness; status also reports existence/accessibility/journal, never event text/global counts. Help/version/doctor/module entry remain working; doctor still diagnoses the package separately.

16. **Configuration.** Explicit path > OOMP_DB_PATH > platform user-data default. Windows: LOCALAPPDATA/OOMP/events.sqlite3, with home AppData/Local fallback. Constructor does not create files; initialization is explicit. Blank overrides/:memory: rejected. sample.env is illustrative, not automatically loaded. All validation databases stayed inside the workspace.

17. **New tests.** 33 storage cases and 8 CLI cases. Coverage includes scope/provenance/metadata/time roundtrip, schema/reinit/rollback, deterministic chronological/keyset order, every retry/conflict pattern, corruption sanitization, busy/commit-failure rollback, thread/two-process duplicate writes, missing read-only status and repeated synthetic examples.

18. **Exact final count.** `120 passed in 22.18s`, exit 0; 79 original + 41 new. No failures, skips or pytest warnings. Full log: `.test-artifacts/stage2-tests-20261014.txt`. Source/test/example compilation, dependency check, explicit offline editable installation and manual CLI/example validation also passed. [Validation details](stage2-validation.md).

19. **Failures/warnings.** Sandbox helper startup failures were handled by approved execution; command-local Git ownership override used, no global changes. Git emitted LF→CRLF normalization warnings for two files; diff check passed. Pip's optional upgrade notice required no update. Review defects were fixed before the final passing suite; no unresolved failure remains.

20. **Successful insertion/retrieval example.** [stage2_event_roundtrip.py](../examples/stage2_event_roundtrip.py) ingested demo-event-2 before demo-event-1, reopened and returned demo-event-1 at 10:00 followed by demo-event-2 at 10:02, both synthetic statements with full references/metadata. Scoped count was 2.

21. **Duplicate example.** demo-retry-id reused demo-idempotency-1 and changed ingestion time. Append returned demo-event-1 and count remained 2, preserving the first event's timestamp/identity.

22. **Conflict example.** A different statement reused demo-idempotency-1. The example caught IdempotencyConflictError, verified the original content remained, and count stayed 2. Its output explicitly confirms rejection.

23. **Manual commands.** See the block below. Use a dedicated synthetic demo database. Direct environment executables avoid activation/bare-launcher issues on this machine.

24. **Documentation.** README, architecture, memory model, security and roadmap updated; [storage guide](storage.md) documents schema, path/config/API/retries/pages/concurrency/backups/privacy; new validation/report preserve the exact results. Stage 1 reports and research hypotheses remain historical/unchanged. Only Stages 1 and 2 are marked implemented.

25. **Security assumptions/limits.** Scope is issued by trusted caller; no network authentication, encryption, privileged deletion or protection against filesystem administrators. The database contains plaintext evidence; fingerprints are not signatures. Status validates schema/accessibility, not all row content. Use consistent SQLite backups, not an uncoordinated copy of an active WAL main file. Pagination is not a scan-wide snapshot; no semantic retrieval/model/graph/MCP capability exists. No memory-performance or research superiority claim is made.

26. **Git.** Main/44fa795 preserved; 8 modified and 13 new project files, unstaged. No automatic commit, remote or push. Databases/WAL/SHM, environments, logs and generated pytest directories remain ignored; no real user data or credentials were staged.

27. **Original regressions.** All 79 original cases pass and test_stage1.py SHA-256 is unchanged: 8BD1376D546A4EB56BB4D32FDF0EE62553DE95AB888AB56EEF1467ADD6C18600. Stage 1 invariants and package version 0.1.0 remain intact.

28. **Stage boundary.** Only Stage 2 was added to the completed Stage 1 foundation. No Stage 3 extraction or any later-stage feature was implemented. TRACE.AI was untouched. No GitHub remote/push was created.

```powershell
.\.venv\Scripts\python.exe -m pytest -v --basetemp .test-artifacts\manual-stage2-tests
.\.venv\Scripts\oomp.exe --version
.\.venv\Scripts\oomp.exe doctor
.\.venv\Scripts\oomp.exe storage init --db .\data\events.sqlite3
.\.venv\Scripts\oomp.exe storage status --db .\data\events.sqlite3
.\.venv\Scripts\python.exe examples\stage2_event_roundtrip.py --db .\data\synthetic-demo.sqlite3
git -c "safe.directory=$PWD" status --short
git -c "safe.directory=$PWD" remote -v
```
