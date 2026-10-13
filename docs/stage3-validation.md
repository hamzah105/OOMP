# Stage 3 validation

Acceptance passed on 2026-10-14 (Asia/Karachi): **192 tests passed in 55.90 seconds**, exit 0, with no failures, skips or pytest warnings. Stage 3 stops at deterministic extraction, canonicalization, conservative entities and durable memory persistence.

## Environment and regression baseline

Workspace: D:\Desktop\OOMP. Python 3.11.4, SQLite 3.42.0, Pydantic 2.14.1, pytest 9.1.1; oomp-memory 0.1.0. Package version and dependency declarations are unchanged.

The committed Stage 2 snapshot at e792b3e passed its original **120 tests in 22.51s**, using an isolated workspace archive and explicit snapshot PYTHONPATH. An earlier baseline attempt overlapped a migration edit and failed four cases; it was discarded as an invalid baseline. The committed snapshot established the valid baseline, and the final implementation passed all cases.

The original 79 Stage 1 cases are untouched. test_stage1.py SHA-256 remains 8BD1376D546A4EB56BB4D32FDF0EE62553DE95AB888AB56EEF1467ADD6C18600. All 41 Stage 2 cases remain; five version-specific test functions had minimal expectations updated from current schema 1 to 2 and future version 2 to 3, including the exact additive object inventory. Event payload, retry, scope, immutability, rollback and concurrency assertions were retained.

## Executed checks

| Check | Actual result |
| --- | --- |
| Offline editable install, --no-index --no-deps --no-build-isolation --no-cache-dir | Passed, version 0.1.0; no dependency/model download |
| python -m pytest -v --basetemp .test-artifacts\stage3-final-pytest | 192 passed in 55.90s |
| python -m compileall -q src tests examples | Passed |
| python -m pip check | No broken requirements found |
| oomp --version / doctor | 0.1.0 / Stage 1 package readiness OK |
| Synthetic example twice on one dedicated database | 4 events, 2 memories, 1 entity; stable IDs/evidence on retry |
| storage status on manual demo | Schema 2, journal wal, ready |
| memory extract preference-1 retry | Created 0, reused 1, evidence added 0 |
| memory list default / --show-content | Default IDs/types/source IDs/counts; content only with opt-in |
| Real v1 upgrade/failure rollback, scope isolation, reopen, concurrency | Passed in full suite |

The full test log is .test-artifacts/stage3-tests-20261014.txt; the clean baseline log is .test-artifacts/stage3-baseline-clean.txt. These generated artifacts and databases are ignored.

## New acceptance coverage

72 new cases: 27 extraction, 16 pipeline, 5 CLI, 16 memory storage and 8 entities. They cover supported positive/negative preferences, explicit projects, technical claims and decisions; considering/planning versus completed actions; Unicode; questions/conditionals/speculation/secrets; role attribution; input/output limits; invalid provider proposals and source spans; scoped canonical keys; multiple memories per event and multiple events per memory; all MemoryNode fields and immutable metadata; explicit aliases, ambiguity and scoped entity reuse; real version 1 preservation/rollback; atomic multi-candidate failure; durable reopening; pagination and denied RequestedScope reads; concurrent duplicate writes and stable read snapshots; source/entity/alias caps and rollback; CLI content privacy and explicit upgrade guidance.

All original Stage 1/2 coverage remains, including separate-process event retries, fingerprints, immutable SQL triggers, commit failures, busy errors, missing read-only status and package import independence. No live Ollama, cloud service, GPU, MCP host or TRACE dependency is used.

## Actual demonstration results

First run on .test-artifacts/stage3-manual.sqlite3:

| Event | Memories created/reused | Evidence added | Entities created/reused |
| --- | --- | --- | --- |
| preference-1 | 1 / 0 | 1 | 0 / 0 |
| preference-2 | 0 / 1 | 1 | 0 / 0 |
| project-1 | 1 / 0 | 1 | 1 / 0 |
| project-2 | 0 / 1 | 1 | 0 / 1 |

Reopening returned the profile and project_state memories with two source references each. The second complete run created no additional memories/evidence/entities. The entity reused counter records actual resolution reuse.

~~~text
Stored source events: 4
Canonical memories: 2
mem-f600e007d179d3ca8bcf3e9a38a5e156967d3ed25977f86bfa1f2437b7ee6c06 type=profile evidence=2 entities=0
mem-b61cc681cd17ead8e25fd680ae1f11e5f41948f68c231645af4aeb0e3d97257e type=project_state evidence=2 entities=1
Resolved project entity: ent_8959971c5a77c4501d0c603162c5469d
~~~

## Manual verification

Use the environment executables on this Windows PC; the bare system python launcher is unusable. The example's database/scope is dedicated synthetic data.

~~~powershell
.\.venv\Scripts\python.exe -m pytest -v --basetemp .test-artifacts\manual-stage3-tests
.\.venv\Scripts\python.exe -m compileall -q src tests examples
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\oomp.exe --version
.\.venv\Scripts\oomp.exe doctor
.\.venv\Scripts\python.exe examples\stage3_memory_extraction.py --db .\data\stage3-synthetic.sqlite3
.\.venv\Scripts\oomp.exe storage status --db .\data\stage3-synthetic.sqlite3
.\.venv\Scripts\oomp.exe memory extract --tenant tenant-stage3-example --namespace synthetic --event-id preference-1 --db .\data\stage3-synthetic.sqlite3
.\.venv\Scripts\oomp.exe memory list --tenant tenant-stage3-example --namespace synthetic --db .\data\stage3-synthetic.sqlite3
.\.venv\Scripts\oomp.exe memory list --tenant tenant-stage3-example --namespace synthetic --show-content --db .\data\stage3-synthetic.sqlite3
~~~

To upgrade an existing genuine v1 OOMP database, run storage status and then explicitly storage init --db PATH. The automated migration test constructs actual migration 1 plus a real event and compares event tuples and trigger SQL before/after; its failure test confirms version/data/schema rollback. No user database was used.

## Warnings and practical limits

The sandbox helper failed to start ordinary commands; approved execution was used for workspace changes/checks. Git reports LF-to-CRLF normalization warnings for cli.py and test_stage2_cli.py; no formatting failure is implied. No pytest warning or unresolved test failure remains.

The tests prove observed local file-backed behavior, not hardware power-loss survival or performance benchmarks. Read snapshots are per call, pagination is a live view, and SQLite is intended for same-host local disk. No secret detector completeness, objective fact verification, general paraphrase equivalence, encryption, erasure, graph traversal or semantic retrieval is claimed. See [extraction](extraction.md), [storage](storage.md) and [security](security-model.md).
