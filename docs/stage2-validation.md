# Stage 2 validation

Validated on 2026-10-14, Asia/Karachi, in `D:\Desktop\OOMP`. The existing Stage 1 commit was `44fa795` on `main`; the working tree was clean before this task. TRACE.AI was not accessed or modified. No commit, staging, remote, push or global Git security change was performed.

## Environment

Python 3.11.4, SQLite 3.42.0, Pydantic 2.14.1, pytest 9.1.1; package `oomp-memory` remains 0.1.0. Stage 2 adds no dependency: SQLite comes from Python's standard library. Validation used `.venv\Scripts\python.exe` and `.venv\Scripts\oomp.exe` directly.

## Executed results

| Check | Actual result |
| --- | --- |
| Original Stage 1 baseline | 79 passed in 1.87s |
| Complete final pytest suite | **120 passed in 22.18s**, exit 0; no failures, skips or warnings |
| Stage 1 regression subset within final suite | All 79 passed; original test file unchanged |
| New Stage 2 tests within final suite | 33 storage cases and 8 CLI cases passed |
| File-backed reopen | Single and multiple events preserved IDs/content/full references/metadata/UTC timestamps |
| Durable retries/conflicts | Equivalent retries returned original record; conflicting IDs/keys rejected; count unchanged |
| Concurrent writers | Eight-thread shared-key test and two independent subprocess writers stored one event and returned one winner |
| Transaction failure | Injected COMMIT failure after INSERT rolled back the row, closed the connection and allowed a safe retry |
| Locked SQLite | Typed busy error, no partial row; retry worked after lock release |
| Migration rollback | Failed migration left version 0 and no partial schema; successful retry initialized version 1 |
| Scope enforcement | Tenant/namespace isolation, requested-scope rejection and mismatched event/cursor rejection passed |
| Pagination | Bounded keyset pages, deterministic ties/fractional times and supported extreme years passed |
| Missing status | Exit 1, no database or parent directory created |
| Explicit storage init/status | Exit 0, schema 1, journal `wal`, ready |
| Version and doctor | Exit 0, `oomp 0.1.0`, Stage 1 package readiness OK |
| Example in two separate executions | Two chronological synthetic events, count 2 on both runs, duplicate resolved to original, conflict rejected |
| Python compilation | `compileall -q src tests examples` passed |
| Dependency consistency | `pip check`: No broken requirements found |
| Editable installation, index/version check disabled | Passed using only existing local build/runtime dependencies |
| Git whitespace/ignore rules | diff check passed; .env, databases/WAL/SHM, environments and test artifacts ignored |

Full suite command and log:

```powershell
.\.venv\Scripts\python.exe -m pytest -v --basetemp .test-artifacts\stage2-final-20261014
```

Log: `.test-artifacts/stage2-tests-20261014.txt`. The actual tool invocation retained the log with Tee-Object and set TMP/TEMP to workspace `.tmp`.

Offline installation verification:

```powershell
.\.venv\Scripts\python.exe -m pip install --no-index --disable-pip-version-check --no-deps --no-build-isolation --no-cache-dir -e .
```

Both manual demonstration databases were workspace-local and Git-ignored: `.test-artifacts/stage2-manual-20261014/events.sqlite3` and `.test-artifacts/stage2-demo-20261014.sqlite3`. No real user-data directory was initialized. The example contained synthetic data only.

The original test-file SHA-256 remained `8BD1376D546A4EB56BB4D32FDF0EE62553DE95AB888AB56EEF1467ADD6C18600`. Stage 1 domain models/enums/retrieval contracts, pyproject metadata and research hypotheses were unchanged. Only EventStore gained compatible listing/counting methods and separate pagination contracts.

## Issues and limits

The managed sandbox process helper continued to fail before launching commands; approved execution completed the requested workspace actions. Read-only Git inspection used `git -c "safe.directory=$PWD" ...`, without changing global configuration. Git warned that LF would be normalized to CRLF for `.gitignore` and `src/oomp/cli.py`; the whitespace check still exited 0. An initial install displayed pip's optional upgrade notice; the explicitly offline verification disabled that check.

Review found and corrected omitted-key retry handling, negative schema reporting, literal SQLite internal-name filtering, nested metadata key-order coverage, and early-year timestamp formatting before the final suite. No unresolved implementation or test failure remains.

Tests establish scoped durable ingestion and chronological history, not semantic retrieval or associative-memory quality. Hardware power-loss, disk-full recovery, arbitrary administrator tampering, network filesystems, all supported Python versions, privileged erasure and transport authentication were not validated. The local adapter trusts service-issued AuthorizedScope; status checks schema/accessibility, not every stored row's integrity. Stages 3–10 remain unimplemented.
