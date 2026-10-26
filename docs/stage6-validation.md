# Stage 6 validation

Final acceptance: **2026-10-27**, Asia/Karachi client date. Workspace: D:\Desktop\OOMP. Branch: main; HEAD remains 54591842a1ac78b1f4b1bd673c9e31b25573e023. The tree was clean before Stage 6 started on 2026-10-16. No commit or push was created.

## Executed results

| Check | Actual result |
| --- | --- |
| Pre-edit Stage 1–5 baseline | 279 passed in 147.14s |
| Final complete pytest -v | **321 passed in 221.73s (0:03:41)** |
| Earlier regressions | All 279 passed: Stage 1 79, Stage 2 41, Stage 3 72, Stage 4 34, Stage 5 53 |
| New Stage 6 coverage | 42 cases across 41 test functions in five modules |
| Final failed / skipped / warnings | 0 / 0 / 0 |
| compileall -q src tests examples | Exit 0 |
| pip check | No broken requirements found |
| oomp --version | oomp 0.1.0 |
| oomp doctor | Exit 0; contract/mind/projection/privacy imports OK; explicitly does not check database or provider |
| Standard offline example | Fresh and repeated executions both exit 0 |
| Local operator CLI | 20 commands checked, including expected refusal exits |
| Explicit queued RAM review | Three further CLI commands; three jobs completed, one durable pending proposal, zero protected edges |
| Reopened synthetic database | Schema 5, WAL, foreign_key_check empty, integrity_check ok |
| Historical migrations 1–4 | All four serialized SQL-definition hashes unchanged |
| Earlier test functions / Stage 1 file | Preserved; Stage 1 SHA-256 unchanged |
| Patch whitespace | git diff --check exit 0 |

The final suite ran with Python 3.11.4, pytest 9.1.1, Pydantic 2.14.1 and SQLite 3.42.0 with real FTS5. Runtime/build dependencies and distribution version are unchanged. Default tests and the demo use no Ollama, GPU, MCP or internet service. Provider failure/vector mechanics use explicitly labelled synthetic providers. **Live embedding inference and semantic quality remain untested**, and no model was downloaded.

## Commands actually executed

~~~powershell
$env:TMP = Join-Path $PWD '.tmp'
$env:TEMP = $env:TMP
.\.venv\Scripts\python.exe -m pytest -v --basetemp .test-artifacts\stage6-final-pass-20261027
.\.venv\Scripts\python.exe -m compileall -q src tests examples
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\oomp.exe --version
.\.venv\Scripts\oomp.exe doctor
.\.venv\Scripts\python.exe examples\stage6_background_mind.py --db .test-artifacts\stage6-manual-20261027.sqlite3
.\.venv\Scripts\python.exe examples\stage6_background_mind.py --db .test-artifacts\stage6-manual-20261027.sqlite3
~~~

Additional CLI checks used explicit database/scope and exercised storage status; mind status/backfill/jobs/summary/consolidate/work/enqueue/cancel/run-once/retry/erase-plan/erase-confirm/reviews; and Stage 5 retrieve/retrieval status. Required confirmation refusals returned nonzero without mutation. Normal summary/recall output omitted content; erasure plans omitted alias names. A second namespace source survived erasure of the main-scope event.

The separate review-job database queued inspect_conflicts through the actual CLI, ran the worker and reopened the persisted pending review. No SUPERSEDES or CONTRADICTS edge was written without confirmation. The test suite separately proves confirmed application, rejection/approval races and transaction rollback.

## Demonstration observations

| Observation | Fresh execution | Repeated execution |
| --- | --- | --- |
| Initial synthetic events newly appended | 3 | 0 |
| Initial worker claimed/completed | 9 / 9 | 0 / 0 |
| Second worker claims | 0 | 0 |
| Unchanged summary creates another revision | False | False |
| Crash claim recovered | True | True, persisted recovery |
| Synthetic provider outage observed | True | True, persisted attempt history |
| Compatible vectors / canonical records at index check | 5 / 5 | 5 / 5 |
| New conflict reviews | 1 | 0 |
| Pending review count | 1 | 1 |
| Synthetic privacy event erased in this invocation | True | False, prior tombstone respected |
| Reopened storage ready | True | True |

After the separate operator exercises, the main synthetic partition retained five source events, five canonical memories, five vectors, one summary revision, one pending review, 27 durable jobs and three erasure tombstones. The unrelated namespace source remained intact. These are functional mechanics observations, not benchmarks or real-model quality results.

## Coverage and failure injection

| Boundary | Substantive validation |
| --- | --- |
| Migration | Genuine populated v4: every old source/memory/entity/alias/graph/topic/history/FTS/vector table and trigger preserved; fresh/reinit/future/failed upgrade with actual data |
| Intake | Transactional append/outbox, duplicate/failed append, explicit bounded backfill, late occurrence and queue capacity |
| Job authority | Scoped targets, tenant/namespace isolation, typed immutable provider configuration and identity collision |
| Ownership | Two spawned processes race one claim; lease expiry/reclaim; stale acknowledgement/renewal rejected; clock sampled after writer lock |
| Crash window | A spawned process commits extraction and exits without acknowledgement; next owner replays with no duplicate canonical/evidence records |
| Retry/control | Backoff/exhaustion/allowed administrative retry, cancellation, unsupported policy, injected interruption, bounded batch/polling/busy wait and small-queue drainage |
| Extraction | Existing pipeline reused; actual provenance; assistant/secret/unsupported exclusion; correction append; default offline and embeddings disabled |
| Indexing | 16/19 partial vector coverage during outage; lexical recall retained; recovery completes coverage; unchanged vectors skip; malformed vectors terminal; SQLite-busy vector commit retries |
| Summaries | Actual direct memberships/proof/references, unchanged no-op, revision changes, historical/stale artifact labels, retraction, independent proof, scope and complete bounds |
| Governance | Pure proposals only, durable deduplication, atomic confirmed existing-policy write, rollback after edge insertion and concurrent rejection |
| Erasure | Nonmutating plan, confirmation/scope/freshness, FTS/vector/summary cleanup, shared surviving proof, cancellation/tombstones and ordinary immutability |
| Privacy races | Source erased between extraction and apply_batch, and between provider input and vector persistence; neither recreates data |
| Fail closed | Graph dependencies, withdrawn shared proof and incomplete review inventories refused |
| CLI/example | Redaction, meaningful exits, required flags/confirmation, real fresh/repeated offline SQLite example |

The final full run is authoritative. Earlier failed runs remain in ignored artifacts: they exposed an empty-table trigger test, nondeterministic collision fixture, repeat-demo maintenance ordering and obsolete schema-4 expectations. Those issues were corrected; no prior behavioral test was removed or weakened. Necessary current/future schema pins and the Stage 4 example's initialization expectation now reflect v5/v6.

## Audit artifacts and manual assessment

Ignored local evidence:

- .test-artifacts/stage6-baseline-20261016.txt and stage6-baseline-manifest.json
- .test-artifacts/stage6-final-pass-20261027.txt
- .test-artifacts/stage6-manual-fresh-20261027.txt and stage6-manual-repeat-20261027.txt
- .test-artifacts/stage6-cli-acceptance-20261027.json
- .test-artifacts/stage6-review-job-20261027.json
- .test-artifacts/stage6-durability-20261027.json
- .test-artifacts/stage6-final-audit-20261027.json

For a new manual assessment, use a fresh dedicated synthetic database and the [documented local commands](background-mind.md#local-procedures). Review the [40-item completion report](stage-6-report.md), particularly unsupported erasure dependencies, retained identifiers, physical/backup remnants and separate summary retrieval. Stage 7–10 remain unimplemented. TRACE.AI was untouched. Work stops here for manual verification; no commit or push.
