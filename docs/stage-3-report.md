# OOMP Stage 3 completion report

Stage 3 acceptance passed on 2026-10-14 (Asia/Karachi): **192 tests passed in 55.90 seconds**. Work stops after Memory Extraction & Canonicalization. [Exact validation](stage3-validation.md).

1. **Workspace confirmation.** D:\Desktop\OOMP, independent local repository on main. User history e792b3e / 44fa795 was preserved. No TRACE files were accessed or modified.

2. **Files created (17).** src/oomp/domain/memories.py; src/oomp/ingestion/{__init__.py,contracts.py,extraction.py,canonicalization.py,pipeline.py}; src/oomp/storage/{memory_store.py,entity_store.py}; examples/stage3_memory_extraction.py; tests/test_stage3_{extraction,storage,entities,pipeline,cli}.py; docs/{extraction.md,stage3-validation.md,stage-3-report.md}. No empty provider packages were introduced.

3. **Files modified (16).** .gitignore; README.md; docs/{architecture,memory-model,storage,security-model,roadmap}.md; src/oomp/cli.py; src/oomp/domain/{models,interfaces}.py; src/oomp/storage/{__init__,errors,migrations,sqlite}.py; tests/test_stage2_{storage,cli}.py. Original enums, retrieval contracts, Stage 1 tests, package version/dependencies and historical reports remain unchanged.

4. **Stage 3 architecture.** Immutable scoped events -> bounded deterministic proposals -> candidate/source grounding -> conservative canonical identity -> atomic memory/evidence/entity persistence. Domain values are provider neutral; extraction and orchestration contain no SQL. Graph/retrieval/embedding protocols remain contracts.

5. **SQLite version 2 schema.** The original events table/indexes/triggers stay intact. Adds memories (all node fields, tags/metadata JSON and fingerprint), memory_sources (ordered many-to-many evidence/span/method), entities, entity_aliases (explicit first source proof), memory_entities (associations). Scoped keys, unique canonical keys and composite foreign keys enforce partition consistency. No vectors or graph edges.

6. **Migration behavior.** Sequential registry adds migration 2 to unchanged migration 1. Fresh initialization runs both transactionally. A genuine v1 schema is validated before upgrade; event rows/fingerprints/triggers survive unchanged. Repeated initialization is safe. Foreign/damaged/future versions fail closed. Migration failure rolls back version/schema/data. Valid v1 event reads remain possible, but status requests explicit upgrade and memory APIs require v2.

7. **Extraction pipeline.** ExtractionPipeline.process_event(scope,event_id) revalidates AuthorizedScope, retrieves the original event, applies eligibility, validates all proposals against independently recognized source-grounded transformations, derives MemoryWrite values and invokes one atomic apply_batch. Empty extraction returns a reason/counters; the source remains stored. Provider failure or invalid second candidate writes nothing.

8. **Supported memory types.** Default extraction produces profile, project_state, semantic, decision and episodic. Existing procedural/resource/topic_summary domain values remain valid for trusted storage callers without default extraction rules. Confidence and fact validity bounds remain null unless supplied under a separate trusted policy; the pipeline invents neither.

9. **Deterministic rules.** Explicit I prefer / do not prefer / don't prefer, developing a project called NAME (optional parenthetical alias), named-subject uses assertion, We decided to, considering buying, plan to and purchased. Negation/modality remain distinct. Questions, uncertainty/conditional markers, unsupported prose, ineligible roles and obvious secrets are skipped. [Exact grammar and limitations](extraction.md).

10. **Optional model status.** Unimplemented provider transport. CandidateExtractor and strict MemoryCandidate provide the adapter interface; fake-provider tests validate malformed/invented output without live Ollama. No endpoint, model/timeout configuration, cloud provider, weights or download exists. Default extraction is offline.

11. **Canonical identity.** Version 1 uses NFC, collapsed whitespace and normalized terminal periods without arbitrary casefold/paraphrase rewriting. SHA-256 of compact UTF-8 JSON [tenant,namespace,type,source_type,canonical_content] yields v1:<digest> and mem-<digest>. Attribution and verification=false metadata are retained.

12. **Deduplication.** Equivalent normalized supported claims reuse the first scoped memory ID and union evidence. Negated, speculative versus completed, differently attributed/typed/scoped or differently worded unsupported paraphrases stay separate. Stable-payload conflicts under a canonical key, or competing ID/key records, reject without overwrite.

13. **Entity rules.** Type and scope qualify NFC/whitespace/casefold name equality. Default extraction proposes only explicitly named projects. Literal name evidence and parenthetical aliases can reuse one stable entity; alias collisions identifying different existing records reject. Sam/Samuel and typed Java identities remain distinct. IDs are ent_ plus 32 SHA-256 hex digits of scoped initial normalized identity. Aliases never broadly rewrite memory keys.

14. **Provenance storage.** Scoped many-to-many source pairs retain insertion order, exact spans where supplied and extraction method. Node readback reconstructs source IDs and full references from actual events. Fabricated/missing/cross-scope sources and altered SourceReferences fail. First evidence records are preserved on retry; no source content is rewritten.

15. **MemoryStore API.** put, upsert, get, find_by_canonical_key, list_memories, count_memories, attach_evidence, list_entities; apply_batch owns atomic pipeline persistence. EntityStore supplies resolve/get/count_entities. Constructors do not create files; initialize is explicit. Nodes/pages/cursors/results are validated immutable values.

16. **Transaction boundaries.** One BEGIN IMMEDIATE per event covers all memories, entities, evidence and association links. Failure rolls back the entire derived batch while leaving independent event ingestion intact. Fresh independent connections close per operation. Read calls use an explicit SQLite snapshot so concurrent evidence additions cannot mix node timestamps and proof sets. [SQLite transaction reference](https://www.sqlite.org/lang_transaction.html).

17. **Idempotency.** Reprocessing yields reused memories/entities and zero new source pairs; unique association pairs prevent duplicates. Equivalent new source events add proof to the retained memory. No-op retries preserve timestamps; newly attached evidence updates updated_at. SQLite uniqueness and transactions protect concurrent callers.

18. **Scope/authorization.** Every persistent operation requires a revalidated trusted AuthorizedScope; requested scope/cursors/object scopes cannot grant authority. Both tenant and namespace constrain queries and foreign keys. No cross-tenant canonical/entity identity reuse. Constructing a scope model does not authenticate a principal. [SQLite scoped foreign-key mechanism](https://www.sqlite.org/foreignkeys.html).

19. **CLI added.** memory extract with explicit tenant/namespace/event-id/db; memory list with tenant/namespace/db, bounded limit and opt-in show-content. Default output exposes IDs/types/source IDs/counts, omitting canonical/raw content. Prior help/version/doctor/storage init/status remain operational. Valid v1 memory commands provide explicit storage-init guidance.

20. **Actual demo output.** Four synthetic source events produce exactly two memories (profile/project_state), each with two source references, and one explicitly aliased OOMP project entity. Reopening and a second process run retain the same IDs/counts. On the first run, preference/project repeats report reused=1 and evidence-added=1; reruns report evidence-added=0. Full actual identifiers/output appear in [validation](stage3-validation.md).

21. **New tests.** 72 cases across five Stage 3 modules: 27 extraction, 16 pipeline, 5 CLI, 16 storage, 8 entities. Includes real v1 upgrade/failure, complete node/provenance roundtrip, aliases/scopes, canonical conflicts, multi-candidate rollback, concurrent writes/read snapshots, caps, provider validation, privacy and durable repeat demos.

22. **Exact total count.** 192 passed in 55.90s, exit 0: 79 Stage 1 + 41 Stage 2 + 72 Stage 3. No failures, skips or pytest warnings. Full log .test-artifacts/stage3-tests-20261014.txt. Offline editable installation, compileall, pip check and manual commands also passed.

23. **Failures/warnings.** No unresolved validation failure. An early overlapping baseline attempt was discarded; the isolated committed baseline then passed all 120. Sandbox helper errors required approved execution. Git emits line-ending normalization warnings for two existing test/CLI files; no global configuration was changed. No model/network dependency warning is hidden.

24. **Existing regressions.** All original 120 cases remain. Five schema-version-specific Stage 2 functions had only legitimate version/inventory expectations updated. Stage 1 test SHA-256 stays 8BD1376D546A4EB56BB4D32FDF0EE62553DE95AB888AB56EEF1467ADD6C18600. Migration 1 SQL is unchanged.

25. **Resources.** 16,384-character extraction input, first 32 recognized candidates, provider maximum 32 proposals, eight candidate entity hints, 1-100 memory pages, 1000 source links/memory, 64 aliases/entity and 64 entity associations/memory. Overflow fails atomically rather than losing existing proof. Evidence validation streams source contents; no full history/model/GPU aggregation. No latency or benchmark superiority claim.

26. **Security limitations.** Source-attributed unverified claims; no execution, SQL interpolation or cloud upload. Secret detection is a limited heuristic and the immutable event log may contain sensitive originals. Direct storage callers own semantic content policy; ExtractionPipeline supplies default grounding. SQLite is plaintext with filesystem-administrator trust, no encryption/secure erasure/public authentication. Identifiers themselves can be sensitive.

27. **Manual verification.** Run the validation command block or the commands below. Use the dedicated synthetic database and actual example scope. Use storage init explicitly for v1 upgrades. No user conversations/credentials were used.

28. **Documentation.** Six required existing documents updated, with extraction.md, stage3-validation.md and this 31-item report added. Exact constructions, identity, evidence, alias rules, schema/migration, retry/transaction policy, unimplemented model status, local trust and Stage 4 assumptions are documented. Historical Stage 1/2 reports remain historical.

29. **Git status.** main at user HEAD e792b3e preserved; 16 modified and 17 new project files, unstaged. No commit, push, remote, reset/history rewrite or global Git change. No remote is configured. Environments, credentials, SQLite/WAL/SHM, model weights, caches/logs and synthetic temporary data remain ignored.

30. **Stage 4 prerequisites.** Define durable semantic edge/endpoints and provenance, scoped relationship policies, temporal validity/conflict/supersession governance, bounded traversal, cycle handling, transaction/durability behavior and canonicalization-version compatibility. Entity associations are not a completed graph. Preserve events and complete proof; do not infer objective truth from source claims.

31. **Stage boundary.** Only Stage 3 was added to the completed Stage 1/2 foundation. No graph engine, vector/hybrid search, jobs/Mind Agent, MCP server, TRACE integration, benchmark, cloud deployment or release work was implemented. TRACE remains untouched. Work stops here.

~~~powershell
.\.venv\Scripts\python.exe -m pytest -v --basetemp .test-artifacts\manual-stage3-tests
.\.venv\Scripts\oomp.exe --version
.\.venv\Scripts\oomp.exe doctor
.\.venv\Scripts\python.exe examples\stage3_memory_extraction.py --db .\data\stage3-synthetic.sqlite3
.\.venv\Scripts\oomp.exe storage status --db .\data\stage3-synthetic.sqlite3
.\.venv\Scripts\oomp.exe memory extract --tenant tenant-stage3-example --namespace synthetic --event-id preference-1 --db .\data\stage3-synthetic.sqlite3
.\.venv\Scripts\oomp.exe memory list --tenant tenant-stage3-example --namespace synthetic --db .\data\stage3-synthetic.sqlite3
.\.venv\Scripts\oomp.exe memory list --tenant tenant-stage3-example --namespace synthetic --show-content --db .\data\stage3-synthetic.sqlite3
~~~
