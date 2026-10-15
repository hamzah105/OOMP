# Stage 4 validation

Acceptance passed on **2026-10-15 (Asia/Karachi)**: **226 tests passed in 94.91 seconds**, exit 0. No failures, skips or pytest warnings remain. Production code was then unchanged while the existing seven-case temporal file gained explicit self/circular-supersession and untrusted-scope assertions; that file passed again in **7.52 seconds**. Test method totals remain 226.

## Environment and baseline

Workspace D:\Desktop\OOMP; main at user commit 6dfbaeb. Python 3.11.4, SQLite 3.42.0, Pydantic 2.14.1, pytest 9.1.1; oomp-memory 0.1.0. Version and dependencies are unchanged.

The unchanged committed Stage 3 baseline passed **192 tests in 53.50s** before implementation. Migrations 1 and 2 compare exactly with the committed baseline tuples. The original Stage 1 test file SHA-256 remains 8BD1376D546A4EB56BB4D32FDF0EE62553DE95AB888AB56EEF1467ADD6C18600.

All 192 prior cases remain. Existing tests received only current/future schema pins, additive object inventory expectations and event-trigger comparison filtering appropriate to new recording/edge triggers. Original event, memory, proof, idempotency, scope, rollback and concurrency assertions remain.

## Executed checks

| Check | Actual result |
| --- | --- |
| Offline editable installation with --no-index --no-deps --no-build-isolation --no-cache-dir | Passed, 0.1.0; no downloads |
| python -m pytest -v --basetemp .test-artifacts\stage4-final-pytest | 226 passed in 94.91s |
| Expanded required negative assertions in existing temporal test file | 7 passed in 7.52s; production unchanged |
| compileall -q src tests examples | Passed |
| pip check | No broken requirements found |
| oomp --version / doctor | 0.1.0 / package readiness OK |
| Synthetic Stage 4 example twice on one SQLite file | Passed; durable identities/counts preserved |
| storage status on manual demo | Schema 3, wal, ready |
| graph neighbors/history/topic-tree/propose | Passed; IDs/evidence/state without canonical content |
| Migration SQL/Stage 1 hash comparison and AST runtime dependency check | Passed; only standard library, oomp and pydantic imports |
| Real v2 upgrade/rollback, complete prior record preservation, scope and concurrency | Passed in suite |

Full log: .test-artifacts/stage4-tests-20261015.txt. Baseline log: .test-artifacts/stage4-baseline-20261014.txt. Actual manual output: .test-artifacts/stage4-manual-20261015.txt. These artifacts and synthetic databases are ignored.

## Exact test inventory

| Module group | Cases |
| --- | --- |
| Original Stage 1 | 79 |
| Stage 2 storage / CLI | 33 / 8 |
| Stage 3 extraction / pipeline / CLI / storage / entities | 27 / 16 / 5 / 16 / 8 |
| Stage 4 conflicts / temporal / CLI | 10 / 7 / 4 |
| Stage 4 graph / graph limits / topics | 4 / 6 / 3 |
| Total | 226 |

Stage 4 adds **34 substantive cases**. Several integration cases assert multiple related acceptance invariants rather than inflating counts with isolated trivial assertions.

Coverage includes actual v2 event/memory/source/entity/alias/association preservation and failed migration rollback; fresh/repeated schema 3 initialization; future-version rejection retained from prior suites; edge typing, endpoints, missing/foreign evidence and logical identity conflicts; additional source proof and retries; concurrent edge/membership writers; source/evidence immutability; complete bounded pages/neighbors and node/depth/relationship traversal filters; legitimate cycles versus invalid hierarchy; source-grounded conflict slots and modality uncertainty; explicit confirmation and rejected forged/self/reverse resolutions; overlapping unresolved contradictions; known_at exclusion of later correction/evidence; valid_at interval boundaries; legacy unknown recording time; shared canonical memory in two persisted topic branches; default CLI privacy and no network/model dependency.

The rollback fault uses a connection-local TEMP trigger to fail the second proof insertion after the edge and first proof have been written; both groups roll back and a clean retry succeeds. A live read snapshot remains at one proof while another connection commits a second proof. The aggregate-proof test uses a small injected read budget and proves failure does not truncate durable evidence.

## Actual synthetic results

Dedicated scope tenant-stage4-example / synthetic, database .test-artifacts/stage4-manual.sqlite3:

~~~text
Source events: 4
Canonical memories: 4
Supersession edge: edge-proposal-1963c45ef419d1eb0add61000aaabff426138f620264a186901249269c3b256e type=SUPERSEDES evidence=1
Historical old state: memory=ram-old-4 known=True valid=True
Current reported state: memory=ram-new-12 known=True valid=True
Unresolved proposal: CONTRADICTS
Shared topic memory: mem-90c6ba3f1b3b0396b0609611577e5441ee68653cf704c88c983047e3f35b70ab memberships=2
Topic tree nodes: 3
~~~

Both complete example runs returned these persisted identities and counts. They did not duplicate source events, memories, the supersession or topic pairs. The dispute remains an advisory proposal unless explicitly committed.

Manual graph history for ram-old-4 at September 10 returned valid=true, effective_status=active, superseded_by=[]. At September 20 it returned valid=false, effective_status=superseded and ram-new-12 as replacement. Its source event hardware-old remains available. Incoming/outgoing history lists retain known audit assertions and their explicit validity, including assertions not applicable at the requested valid_at; effective state evaluates that date separately.

The topic projection returned ai with local-models and robotics children, both referencing exactly the same project memory ID. No copied MemoryNode was created.

## Manual commands

~~~powershell
.\.venv\Scripts\python.exe -m pytest -v --basetemp .test-artifacts\manual-stage4-tests
.\.venv\Scripts\python.exe -m compileall -q src tests examples
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\oomp.exe --version
.\.venv\Scripts\oomp.exe doctor
.\.venv\Scripts\python.exe examples\stage4_temporal_graph.py --db .\data\stage4-synthetic.sqlite3
.\.venv\Scripts\oomp.exe storage status --db .\data\stage4-synthetic.sqlite3
.\.venv\Scripts\oomp.exe graph neighbors --tenant tenant-stage4-example --namespace synthetic --memory-id ram-old-4 --db .\data\stage4-synthetic.sqlite3
.\.venv\Scripts\oomp.exe graph history --tenant tenant-stage4-example --namespace synthetic --memory-id ram-old-4 --valid-at 2026-09-10T00:00:00Z --db .\data\stage4-synthetic.sqlite3
.\.venv\Scripts\oomp.exe graph topic-tree --tenant tenant-stage4-example --namespace synthetic --root-topic-id ai --db .\data\stage4-synthetic.sqlite3
.\.venv\Scripts\oomp.exe graph propose --tenant tenant-stage4-example --namespace synthetic --source ram-disputed-8 --target ram-old-4 --db .\data\stage4-synthetic.sqlite3
~~~

For an existing genuine v2 database, explicitly run storage init --db PATH to upgrade; reads never migrate implicitly. The migration suite constructs real v2 DDL and records, compares all old application-table tuples and event-trigger SQL, tests failure rollback and then upgrades successfully. No real user database or TRACE files were used.

## Warnings and limits

No unresolved functional failure remains. During development, a concurrent-write test incorrectly assumed thread 0 must win; the test now verifies one valid retained ID without scheduler assumptions. Version/inventory expectations were adapted to additive schema 3. Review found and corrected historical-date filtering, initial evidence timestamps and aggregate proof bounds before the final suite.

The environment's sandbox helper could not launch ordinary commands; approved execution was used for workspace checks/edits. A Windows command-length limit was handled with split writes. Git emits LF-to-CRLF normalization notices for some changed files; diff validation is recorded separately. None is a pytest warning.

These results establish observed local file-backed behavior, not hardware power-loss simulation or performance benchmarks. The clock is local system time at operation recording, not a certified commit timestamp. Legacy original recording times are unknown; source validity is not inferred from ingestion. SQLite remains plaintext, and direct filesystem administrators remain trusted. See [temporal graph](temporal-graph.md), [security](security-model.md) and [storage](storage.md).

Final handoff checks passed: git diff --check (exit 0), all documentation relative links, 18 modified/16 new project files with zero staged files, preserved main/6dfbaeb, and ignore matches for .env, .venv, SQLite/WAL/SHM, model weights, caches, logs and synthetic artifacts. No remotes are configured. Git emitted eight LF-to-CRLF normalization notices; no global settings were changed.
