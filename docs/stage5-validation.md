# Stage 5 validation

Workspace: D:\Desktop\OOMP. Baseline date: 2026-10-15; final acceptance: 2026-10-16 (Asia/Karachi client dates). Package version remains 0.1.0. The Stage 4 working tree was already uncommitted; a complete local ignored snapshot of its 67 project files was saved before Stage 5 changes. No Git commit, staging, push, remote or history rewrite was performed.

## Executed baseline

Before production edits:

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp .test-artifacts\stage5-clean-baseline
~~~

Result: **226 passed in 146.82s**, exit 0. All prior Stage 1–4 cases passed. Raw output: .test-artifacts/stage5-baseline-20261015.txt.

The actual Python SQLite runtime is 3.42.0. An in-memory CREATE VIRTUAL TABLE USING fts5 and MATCH/bm25 probe succeeded (sample rank -1e-06). This is an availability check, not a performance benchmark. Historical migrations 1–3 remain AST-identical to the preserved Stage 4 source. Stage 1 test SHA256 remains 8bd1376d546a4eb56bb4d32fdf0ee62553de95ab888ab56eef1467add6c18600.

## Local model status

A local service listens at 127.0.0.1:11434. The executed ollama list command found only llama3:latest (4.7 GB), a chat model. No embedding-capable model was installed, no model was downloaded, and no live embedding inference was called. Live Ollama embedding acceptance is **pending** deliberate embedding-model setup. Automated provider tests mock transport and validate the real adapter's request/response handling. Synthetic vectors do not measure semantic quality.

## Final acceptance

Final verbose command:

~~~powershell
.\.venv\Scripts\python.exe -m pytest -v --basetemp .test-artifacts\stage5-final-20261016 --junitxml=.test-artifacts\stage5-final-20261016-results.xml
~~~

Result: **279 passed in 139.16s**, exit 0; no failures, skips or pytest warnings. Raw verbose output: .test-artifacts/stage5-final-20261016-pytest.txt. JUnit XML verifies Stage 1:79, Stage 2:41, Stage 3:72, Stage 4:34 and Stage 5:53. All pre-existing test function names remain; no regression case was removed or renamed. New coverage is 53 cases across 37 methods, grouped by related acceptance invariants.

| New module | Cases |
| --- | ---: |
| test_stage5_budget.py | 3 |
| test_stage5_failures.py | 10 |
| test_stage5_fusion.py | 2 |
| test_stage5_graph_limits.py | 3 |
| test_stage5_integration.py | 12 |
| test_stage5_provider.py | 15 |
| test_stage5_storage.py | 8 |

Fresh persistent offline example:

~~~text
Database: data\stage5-acceptance.sqlite3
Schema: 4; source events: 110
Original event outside latest eight: True
Long-history retrieved memory: mem-12197aed24208ca3676bf1a070b5bde4e1975ec1535873d54c498ff8136d33a9 source=project-original
Lexical indexing: first=0 retry_skipped=5
Semantic fixture: synthetic vectors, candidates=1, indexed=5
Current RAM: ['ram-new-12']
Earlier RAM: ['ram-old-4']
Graph linked memory and proof: True
Strict evidence budget: 785/1200 bytes, memories=1
~~~

A second run against the same data/stage5-acceptance.sqlite3 succeeded with 110 source events/five canonical memories retained and zero new synthetic vectors (five unchanged vectors reused). Logs: .test-artifacts/stage5-example-fresh-final.txt and stage5-example-retry-final.txt. A later final-code run also passed. This is synthetic functional validation, not measured real-model semantic quality.

| Executed check | Result |
| --- | --- |
| Offline editable install with --no-index --no-cache-dir --no-build-isolation --no-deps | Succeeded; package/dependencies unchanged |
| python -m compileall -q src tests examples | Passed after final source changes |
| python -m pip check | No broken requirements found |
| oomp --version | oomp 0.1.0 |
| oomp doctor | Python/package/Pydantic/import checks OK |
| Genuine v3 upgrade, preserved rows, rollback, future rejection/reinit | Passed |
| FTS5 backfill/inserts/rebuild, Unicode/literal syntax/ties | Passed |
| Vector model spaces, invalid inputs, stale digest, reopen and failed batches | Passed |
| Cross-tenant/namespace isolation and WAL snapshot during a writer | Passed |
| Current/historical RAM, known-at proof, unknown validity, conflicts and supersession chains | Passed |
| Graph cycles/depth/nodes/edges/work/relations/relevance/proof | Passed |
| Exact packet bytes/provenance/JSON, strict drops and tiny empty results | Passed |
| CLI default/JSON content privacy and sanitized error hints | Passed |
| Explicit hybrid degradation / strict semantic without provider | Degraded flag true / expected exit 1 |
| Forced lexical rebuild / unchanged embedding retry | Five rows rebuilt; compared canonical/graph/proof/vector rows unchanged |
| Ignore rules for DB/WAL/SHM, models/caches, secrets, environment/artifacts | Passed |

The final manual CLI audit used the real executable and dedicated synthetic data. It verified the project packet at 730/1200 bytes, current RAM12 versus historical RAM4, empty tiny-budget packet, five persisted synthetic vectors and safe mode failures. Commands/results are stored in .test-artifacts/stage5-cli-acceptance.json. The example's separate strict query packs one memory at 785/1200 bytes and records dropped evidence.

Development checks found obsolete schema-3 CLI/demo assertions and a stale-seed lineage case not covered by the first green run. The version pins were updated narrowly and the lineage correction received a dedicated regression before the final 279-case acceptance. Earlier failed/intermediate logs remain in ignored artifacts; no unresolved failure remains. Git reports existing LF/CRLF normalization notices, with diff --check passing and no global Git changes.

## Manual acceptance commands

~~~powershell
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m compileall -q src tests examples
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\oomp.exe --version
.\.venv\Scripts\oomp.exe doctor
.\.venv\Scripts\python.exe examples\stage5_hybrid_retrieval.py --db .\data\stage5-acceptance.sqlite3
.\.venv\Scripts\oomp.exe memory index --tenant tenant-stage5-example --namespace synthetic --db .\data\stage5-acceptance.sqlite3
.\.venv\Scripts\oomp.exe retrieval status --tenant tenant-stage5-example --namespace synthetic --db .\data\stage5-acceptance.sqlite3
.\.venv\Scripts\oomp.exe retrieve "What project was the user developing?" --tenant tenant-stage5-example --namespace synthetic --db .\data\stage5-acceptance.sqlite3 --token-budget 1200 --json
.\.venv\Scripts\oomp.exe retrieve "test computer RAM" --tenant tenant-stage5-example --namespace synthetic --db .\data\stage5-acceptance.sqlite3 --valid-at 2026-09-10T00:00:00Z --historical --token-budget 3000 --show-content --json
~~~

Optional real-model commands are documented in [retrieval](retrieval.md). They are pending manual provisioning and are not part of the executed success claims. No Stage 6 worker/MCP/TRACE integration or benchmark superiority claim was added; no commit/push was performed.


See [retrieval](retrieval.md) for accounting/security boundaries and [completion report](stage-5-report.md) for the 37 requested report items.
