# OOMP Stage 5 completion report

Final acceptance date: 2026-10-16 (Asia/Karachi client date). This report covers Stage 5 changes relative to the preserved Stage 4 working tree. Historical Stage 1–4 reports remain historical.

1. **Workspace.** D:\Desktop\OOMP; independent Python 3.11+ package oomp / distribution oomp-memory, version 0.1.0. The pre-edit 226-case baseline passed and the 67-file uncommitted Stage 4 tree was preserved in ignored local artifacts.

2. **Files created (17).** [docs/retrieval.md](retrieval.md); [docs/stage-5-report.md](stage-5-report.md); [docs/stage5-validation.md](stage5-validation.md); [examples/stage5_hybrid_retrieval.py](../examples/stage5_hybrid_retrieval.py); [src/oomp/providers/__init__.py](../src/oomp/providers/__init__.py); [src/oomp/providers/ollama.py](../src/oomp/providers/ollama.py); [src/oomp/retrieval/engine.py](../src/oomp/retrieval/engine.py); [src/oomp/retrieval/fusion.py](../src/oomp/retrieval/fusion.py); [src/oomp/retrieval/packing.py](../src/oomp/retrieval/packing.py); [src/oomp/storage/retrieval_store.py](../src/oomp/storage/retrieval_store.py); [tests/test_stage5_budget.py](../tests/test_stage5_budget.py); [tests/test_stage5_failures.py](../tests/test_stage5_failures.py); [tests/test_stage5_fusion.py](../tests/test_stage5_fusion.py); [tests/test_stage5_graph_limits.py](../tests/test_stage5_graph_limits.py); [tests/test_stage5_integration.py](../tests/test_stage5_integration.py); [tests/test_stage5_provider.py](../tests/test_stage5_provider.py); [tests/test_stage5_storage.py](../tests/test_stage5_storage.py).

3. **Files modified (25).** [.gitignore](../.gitignore); [README.md](../README.md); [docs/architecture.md](architecture.md); [docs/memory-model.md](memory-model.md); [docs/roadmap.md](roadmap.md); [docs/security-model.md](security-model.md); [docs/storage.md](storage.md); [docs/temporal-graph.md](temporal-graph.md); [examples/stage4_temporal_graph.py](../examples/stage4_temporal_graph.py); [src/oomp/cli.py](../src/oomp/cli.py); [src/oomp/retrieval/__init__.py](../src/oomp/retrieval/__init__.py); [src/oomp/retrieval/contracts.py](../src/oomp/retrieval/contracts.py); [src/oomp/storage/__init__.py](../src/oomp/storage/__init__.py); [src/oomp/storage/errors.py](../src/oomp/storage/errors.py); [src/oomp/storage/migrations.py](../src/oomp/storage/migrations.py); [src/oomp/storage/sqlite.py](../src/oomp/storage/sqlite.py); [tests/test_stage2_cli.py](../tests/test_stage2_cli.py); [tests/test_stage2_storage.py](../tests/test_stage2_storage.py); [tests/test_stage3_cli.py](../tests/test_stage3_cli.py); [tests/test_stage3_pipeline.py](../tests/test_stage3_pipeline.py); [tests/test_stage3_storage.py](../tests/test_stage3_storage.py); [tests/test_stage4_graph.py](../tests/test_stage4_graph.py); [tests/test_stage4_graph_limits.py](../tests/test_stage4_graph_limits.py); [tests/test_stage4_temporal.py](../tests/test_stage4_temporal.py); [tests/test_stage4_topics.py](../tests/test_stage4_topics.py). Prior tests retain every test function; version/object-inventory pins and the Stage 4 demo were adjusted for additive schema 4.

4. **SQLite v4 schema.** Added memory_fts_docs, memory_fts and its five FTS5 shadow tables, memories_fts_insert, embedding_spaces, memory_embeddings, and scoped mapping/vector indexes. Composite foreign keys preserve scope and canonical identity. Existing events, memory bodies, provenance, entities, graph and recording history remain canonical.

5. **Migration results.** Genuine v3 fixtures containing events, memories, linked entities/explicit aliases, edge proof, topics/memberships and recording history upgrade without changing prior rows. Failed v4 migration rolls back to valid v3; fresh/repeated initialization, foreign keys and future-version rejection pass. Migration 1–3 SQL ASTs remain unchanged.

6. **FTS5 architecture.** Runtime SQLite 3.42.0 supports real FTS5 and BM25. Migration backfills persistent content; a transactional insert trigger synchronizes new memories. Bounded per-scope temporary FTS5 ranking avoids cross-tenant BM25 statistics. Rebuild affects only derived rows in resumable batch transactions. Missing FTS5 yields explicit diagnostics.

7. **Embedding provider.** ConfiguredEmbeddingProvider extends the original embed(texts) protocol with EmbeddingSpace identity: provider, model, configuration version and dimension. Core retrieval has no Ollama-specific dependency. Provider I/O occurs outside database snapshots and write locks.

8. **Ollama adapter status.** Implemented opt-in POST /api/embed using standard-library HTTP, explicit dimensions and truncate:false. Literal loopback HTTP, no proxies/redirects, bounded input/output/timeouts, strict model/count/dimension/finiteness/norm checks, sanitized failures. Live embedding verification remains pending: the local inventory contained only llama3:latest, which was not used for embeddings. Nothing was downloaded.

9. **Embedding persistence.** Scoped float64 vector blobs include memory ID, provider/model/version, dimension, SHA-256 canonical-content digest and generation timestamp. Entire batches validate before writes. Compatible unchanged content is skipped; stale or incomplete indexes fail clearly. Overflow-safe cosine uses scaled unit vectors; model spaces are never mixed.

10. **Lexical behavior.** Parameterized SQL and literal quoted Unicode terms handle arbitrary FTS punctuation safely. Runtime queries cap at 4096 characters/32 terms, with deterministic BM25 ties. The basic planner removes common English boilerplate/noise; it has no general intent understanding or stemming. Unicode, backfill, inserts, ties, rebuilding and scope isolation are tested.

11. **Semantic behavior.** Explicit provider plus compatible coverage is required. Exact cosine scan is bounded and complete within supported capacity. A configurable default minimum cosine of 0.2 is an uncalibrated relevance heuristic. Semantic mode never silently becomes lexical; hybrid degradation requires allow_degraded and reports warnings/counts.

12. **Fusion.** RRF sums weight/(60+rank), with default lexical/semantic/topic weights 1 and entity weight 1.5. Duplicate IDs merge and stable IDs break ties. Graph and governed-state ranking signals remain deterministic. Scores describe selection order, never truth probabilities or measured claim confidence.

13. **Entity/topic lookup.** Exact scoped NFC/whitespace/case-normalized names and explicit Stage 3 aliases influence recall; similar spelling/embeddings never merge identities. Explicit topic memberships support projection lookup. Historical known_at requests disable entity expansion because association/alias recording history is incomplete; topic and membership clocks are filtered.

14. **Graph expansion.** Relevance-gated, cycle-safe neighborhood expansion has request-controlled depth/nodes/edges/work and relationship filters. Returned paths carry actual proof, direction and edge validity. Direct matches avoid redundant generic paths that would displace essential evidence. Protected governance inspection has separate bounded limits and remains active when neighborhood depth is zero.

15. **Temporal retrieval.** known_at filters actual system-recorded assertions and attached proof; valid_at evaluates reported validity independently. The compatible as_of field maps to valid_at and conflicting values reject. Unknown bounds/legacy recording time remain explicit in the counted payload. No retrieval operation writes a conflict relationship.

16. **Current versus history.** Default current retrieval captures UTC now, excludes expired/future claims and follows validated supersession. Even a single expired lexical seed can reach the current head through bounded historical lineage; old/intermediate claims are not returned as current. Unknown applicability preserves uncertain alternatives. Historical structural or explicit-validity views retain earlier source evidence; unresolved recorded contradictions stay visible.

17. **Reranking/diversity.** Stronger direct ranks are retained. Deterministic ordering puts distinct whitespace/case-normalized content ahead of redundant content while preserving identities and provenance. There is no blind recency preference, learned reranker or promotion of assistant text to verified user truth.

18. **Budget accounting.** Replaceable TokenCounter defaults to UTF-8-byte conservative accounting, not a universal tokenizer. The exact context_packet includes JSON wrappers, IDs, references, temporal metadata, reasons and paths; its self-reported count converges and stays within budget. Whole candidates are dropped, never truncated. Empty evidence is an empty string/count zero. Outer transport diagnostics and host prompt overhead are outside this evidence budget.

19. **Request/response schemas.** Original defaults and fields remain compatible, including token_budget=1. Added mode, known_at/valid_at/history/degradation and resource controls; EmbeddingSpace and real trace counts; actual event IDs, reasons, temporal labels, direction/validity/proof on paths; token_budget, counting_method and context_packet. No generated-answer field or private canonical metadata is copied.

20. **CLI.** Added memory index, retrieve QUERY and retrieval status. Existing commands pass. Scope/db/mode/limits/time controls, JSON, explicit local-provider/model/dimension/version flags and meaningful sanitized hints are available. Default readable and JSON output hide canonical content and the context packet; --show-content is deliberate local inspection.

21. **Example output.** The real persistent offline example passed fresh and repeated runs:

~~~text
Schema: 4; source events: 110
Original event outside latest eight: True
Long-history source: project-original
Canonical memories: 5
Synthetic vector indexing: fresh 5, repeat 0 (unchanged vectors reused)
Current RAM: ['ram-new-12']
Earlier RAM: ['ram-old-4']
Graph linked memory and proof: True
Strict evidence budget: 785/1200 bytes, memories=1
~~~

22. **Long-history result.** The extracted original project memory is mem-12197aed24208ca3676bf1a070b5bde4e1975ec1535873d54c498ff8136d33a9, supported by project-original. It remains retrievable after 105 later synthetic interactions, outside the latest eight. This proves persisted lexical recall for the fixture, not broad semantic intelligence.

23. **Index/reindex behavior.** Triggers had already synchronized all five lexical rows, so explicit retry reports zero changed/five skipped. Five synthetic vectors persist across processes and are skipped unchanged on repeat. Forced lexical rebuilding preserves every compared canonical, graph, evidence and vector row. Multi-batch provider failure retains prior committed vectors/lexical rows; status and warnings expose incomplete coverage.

24. **Isolation/security.** AuthorizedScope is revalidated and matched to the request before access; every lane and proof uses tenant plus namespace before ranking/packing. One read snapshot prevents mixed historical evidence. Stored instructions execute nothing and confer no mutation authority. CLI scope strings are local administrative intent, not remote authentication. SQLite/indexes remain plaintext; filesystem administrators and local daemon/clock remain trusted.

25. **Resources.** Default/hard bounds include 10,000 documents/vectors and 16 MiB canonical UTF-8 content per scope, 4096 dimensions, 200 candidates per lane, 100 results and 32768 budget units. Default neighborhood limits are depth1/nodes16/edges40/work200; hard limits 2/100/200/1000. Embedding batches are at most16 in orchestration, inputs at most16384 characters, response at most4MB and timeout at most120s. Preflight stops at capacity before wide content loads. See [retrieval](retrieval.md) for separate governance limits. No throughput/superiority benchmark is claimed.

26. **New tests.** 53 Stage 5 cases across 37 test methods in seven modules. Parametrized invalid inputs cover distinct validation paths; related invariants share fixture tests. Per-file counts: test_stage5_budget.py:3; test_stage5_failures.py:10; test_stage5_fusion.py:2; test_stage5_graph_limits.py:3; test_stage5_integration.py:12; test_stage5_provider.py:15; test_stage5_storage.py:8.

27. **Exact full result.** **279 passed in 139.16s**, exit 0. No failed/skipped cases or pytest warnings. Full verbose output and JUnit XML are in ignored .test-artifacts/stage5-final-20261016-* files. [Validation details](stage5-validation.md).

28. **Regressions.** All 226 prior cases pass: Stage1 79 + Stage2 41 + Stage3 72 + Stage4 34. No prior test function was removed or renamed. Stage 1 test SHA256 remains 8bd1376d546a4eb56bb4d32fdf0ee62553de95ab888ab56eef1467add6c18600. Foundational models/enums, package version/dependencies and historical migration SQL are preserved.

29. **Errors/warnings.** No unresolved failure. An initial full run exposed obsolete schema-3 CLI/demo assertions; these were narrowly updated. Review corrected scoped BM25 isolation, preflight/vector overflow, temporal proof, graph direction/rank/budget behavior and stale-seed lineage before final acceptance. Git emits existing LF/CRLF notices; no global configuration changed. Optional live-model validation is pending as described above.

30. **Actual live embedding tests.** None. The local Ollama model inventory was inspected, but no live embedding inference or chat-model substitute ran. Mock transport tests exercise the real adapter; example semantic vectors are explicitly synthetic.

31. **Exact manual acceptance commands.** Run from the workspace; data must remain synthetic:

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
.\.venv\Scripts\oomp.exe retrieve "test computer RAM" --tenant tenant-stage5-example --namespace synthetic --db .\data\stage5-acceptance.sqlite3 --as-of 2026-09-10T00:00:00Z --historical --token-budget 3000 --show-content --json
~~~

Optional real Ollama provisioning/index/search commands are in [retrieval](retrieval.md#optional-local-ollama-setup); they remain manual and unexecuted.

32. **Documentation.** Updated README, architecture, memory model, storage, temporal graph, security and roadmap. Added retrieval.md, stage5-validation.md and this report. Validation distinguishes real executed checks from optional model setup. Stage 1–4 reports were preserved.

33. **Known limits.** Bounded temporary per-scope FTS ranking has rebuild cost; exact vectors are not ANN. Query planning and diversity are simple rules. No general entity linking, objective verification, certified timestamps or complete historical entity-association history. The byte counter is model-independent accounting, not exact tokenizer equivalence. Operators must version/pin mutable local model configurations. No encryption/erasure workflow or remote service exists. Real embedding quality remains unmeasured.

34. **Stage 6 prerequisites.** Define durable scoped jobs/cursors, provider/version pinning, retries/backpressure, cancellation, process-failure recovery, index completeness/staleness policy and audited policy-controlled consolidation. Background work must preserve source/proof and cannot invent verification or bypass Stage 4 governance.

35. **Git.** main at 6dfbaeb48f66bdaa47fe68ce01da09e92290a303 is preserved. Stage 4 dirty work and the Stage 5 delta remain unstaged. Current full working tree: 21 modified tracked files and 33 untracked files, including preserved Stage 4 work. No commit, push, remote creation, reset, history rewrite or global Git edit. Ignore checks cover DB/WAL/SHM, embeddings/models/caches, secrets, environments and synthetic artifacts.

36. **TRACE.AI.** Untouched. No TRACE checkout/file access/edit, runtime dependency or integration was introduced.

37. **Milestone boundary.** Only Stage 5 was implemented. No Stage 6 worker, Stage 7 MCP/network server, TRACE adapter, benchmark superiority claim, frontend or release pipeline was added. Work stops for the user's manual assessment; no commit or push.