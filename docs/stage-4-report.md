# OOMP Stage 4 completion report

Stage 4 acceptance passed on **2026-10-15 (Asia/Karachi)**: **226 passed in 94.91s**, including all 192 prior cases. Expanded required negative assertions then passed in the seven-case temporal file (7.52s), without production changes or changed case totals. [Actual validation](stage4-validation.md).

1. **Workspace.** D:\Desktop\OOMP, independent local main repository. User commit 6dfbaeb and earlier history remain intact.

2. **Files created (16).** src/oomp/domain/{graph.py,graph_policy.py}; src/oomp/graph/{__init__.py,service.py}; src/oomp/storage/{graph_store.py,topic_store.py}; examples/stage4_temporal_graph.py; tests/test_stage4_{graph,graph_limits,temporal,topics,conflicts,cli}.py; docs/{temporal-graph.md,stage4-validation.md,stage-4-report.md}.

3. **Files modified (18).** README.md; docs/{architecture,memory-model,storage,extraction,security-model,roadmap}.md; src/oomp/cli.py; src/oomp/domain/interfaces.py; src/oomp/storage/{__init__,errors,migrations,sqlite}.py; tests/test_stage2_{storage,cli}.py; tests/test_stage3_{storage,cli,pipeline}.py. Existing MemoryNode/MemoryEdge models, enums, extraction rules, retrieval contracts, package version/dependencies and ignore rules were preserved.

4. **Schema 3.** Seven additive tables: graph_meta, memory_recordings, memory_source_recordings, memory_edges, edge_evidence, topics, topic_memberships. Six scoped indexes serve incoming/outgoing/chronological edges, reverse proof, topic children and reverse memberships. Six new triggers record memory/source inserts and protect ordinary edge/evidence mutation. Existing v1/v2 structures stay intact.

5. **Migration.** Sequential transaction adds v3 to unchanged v1/v2 SQL. Real v2 fixtures include events, memories, source links, entities, explicit aliases and associations; exact prior tuples and event-trigger SQL survive failed then successful upgrade. Reinitialization is safe; foreign/damaged/future schemas reject. Graph use requires explicit v3 initialization, with no automatic destructive reset.

6. **Graph architecture.** SQLiteGraphStore references existing canonical memories; it does not duplicate MemoryStore. GraphService orchestrates trusted local links/proposals/resolution. Provider-neutral graph values and pure graph_policy contain no SQL; persistence stays in storage. Topics remain a separate projection layer.

7. **Relationships.** All nine Stage 1 relationship types remain available. Every edge has directed memory-to-memory endpoints in one partition. ABOUT/RELATED_TO/PART_OF/DERIVED_FROM/OCCURRED_IN/SUPPORTS/DEPENDS_ON are trusted source-backed assertions; CONTRADICTS/SUPERSEDES require governed validation. No event/entity/topic ID substitutes for a memory endpoint.

8. **Identity/evidence.** Scoped logical key hashes endpoints, relation and explicit validity; stable fingerprint rejects incompatible data under an ID/key. Reusing a logical edge preserves the first ID and unions actual source-event proof. Source pairs are scoped, ordered, transactional and deduplicated, with complete SourceReferences and attachment times.

9. **Validity.** UTC-aware half-open [valid_from,valid_until) with explicit unknown bounds. Caller dates remain attributed source claims; no fact dates are manufactured from ingestion. Original node content, status and evidence are not rewritten by supersession.

10. **Known-at versus valid-at.** System recording time comes from an adapter-owned cached microsecond SQLite function invoked after the write lock; initial groups share one timestamp. known_at filters assertions and separately attached evidence, including memory proof. valid_at evaluates reported intervals and applicable supersession. Legacy original recording time stays unknown; migration observation only establishes later known existence. The model is minimal immutable-claim/append-assertion history, not unrestricted bitemporal field editing.

11. **Conflict policy.** Exact persisted user RAM-state/upgrade wording and matching canonical content support one fixed subject/attribute. It checks source attribution, selected actual proof, active/nonempty claims, values, modalities and explicit temporal compatibility. Arbitrary metadata slots, topics, different predicates, speculation and unsupported prose yield insufficient structured evidence. Different values or newer messages alone do not prove conflict.

12. **Supersession.** A supported explicit upgrade and coherent later reported change can propose SUPERSEDES from replacement to prior state. Trusted confirmation and transactional rederivation are required. Self/circular or forged reverse resolutions reject. The old claim remains persisted; effective historical status is derived from applicable visible assertions. No automatic latest-message winner.

13. **Proposal/resolution API.** propose_conflict returns ConflictAssessment with optional immutable ConflictProposal and no writes. GraphService.resolve(...,confirm=True) / SQLiteGraphStore.apply_resolution(...,confirm=True) revalidate scope, endpoints, source IDs, reason, policy version, dates and supported relation inside one transaction. Confirmation defaults off at storage. Generic edge creation cannot bypass protected relations.

14. **Topic hierarchy.** Explicit stable scoped topic IDs, immutable names/parentage, existing same-scope parent required. Self-parenting and recursive reparent attempts reject. Deterministic immediate children and bounded tree projections; no automatic topic classifier or reparent/delete workflow.

15. **Shared membership.** A scoped unique topic/memory pair references the original node. One project memory belongs to Local Models and Robotics with two memberships and one canonical ID. Assignment/reopening/concurrent retries preserve that structure.

16. **Traversal.** neighbors supports direction/relation filters; traverse uses deterministic visited-node inspection over both directions. Depth 0-10, nodes 1-500, edges at most 2000, examined edge items at most 10,000. Cycle checks cap at 1000 nodes/10,000 work and fail closed if inconclusive. General cycles are allowed; PART_OF/SUPERSEDES hierarchy cycles are rejected. Returned edges stay within returned nodes. Pages use scoped keyset cursors and strict limits.

17. **Concurrency/transactions.** BEGIN IMMEDIATE serializes integrity checks and writes across processes; composite keys/FKs protect scope and uniqueness. One connection closes per operation. Multi-query reads use a snapshot. A fault after the first proof rolls back the entire edge/evidence group. Recording times and proof budgets are consistent across initial assertion groups. [SQLite isolation](https://www.sqlite.org/isolation.html).

18. **Security.** Revalidated AuthorizedScope on graph/topic operations; requested scope/cursors/text grant no authority. SQL values are parameterized. No text execution, network/model call, cloud upload or autonomous rewriting. Default inspection exposes metadata rather than canonical content. SQLite remains plaintext; file administrators and local system clock remain trusted.

19. **CLI.** Added graph link, graph propose, graph neighbors, graph history and graph topic-tree with explicit tenant/namespace/database and relevant IDs, evidence and timestamps. Protected links require --confirm-resolution and exact source-backed rederivation. Earlier help/version/doctor/storage/memory commands pass. Local scope strings are administrative intent, not remote authentication.

20. **Actual demonstration.** Two complete runs on one file: four source events, four canonical memories, one persisted SUPERSEDES edge, one unresolved CONTRADICTS proposal, three topics and two memberships referencing one project memory. Historical old RAM state at September 10 is valid/active; September 20 shows replacement. SQLite reopening preserves all IDs/proof/branches. [Actual output](stage4-validation.md).

21. **New tests.** 34 substantive cases across six Stage 4 files: conflicts 10, temporal 7, CLI 4, graph 4, graph_limits 6, topics 3. Complex cases cover multiple acceptance invariants without inflating method counts.

22. **Complete test count.** 226 passed in 94.91s, exit 0; no failures/skips/pytest warnings. Additional explicit self/reverse-resolution and RequestedScope assertions in the existing temporal case passed on targeted rerun: seven cases in 7.52s. Production was unchanged.

23. **Regressions.** All original 192 cases remain: 79 Stage 1 + 41 Stage 2 + 72 Stage 3. Schema/future-version/object-inventory pins and event-trigger comparisons were narrowly updated for additive v3. Stage 1 file hash and migration 1/2 tuples remain unchanged. Package version 0.1.0 and dependencies are unchanged.

24. **Failures/warnings.** No unresolved failure. Development review fixed the historical valid-at bug, clock precision/grouping, bounded walk/proof behavior and a test's scheduler-specific winner assumption before acceptance. Sandbox helper/Windows command-length limitations were worked around using approved workspace operations. Git line-ending notices are documented; no global configuration changed.

25. **Manual validation.** Use the command block below and [validation](stage4-validation.md). Offline editable installation, compileall, pip check, version/doctor, schema status, demo twice and manual graph inspection all passed. Use a dedicated synthetic database.

26. **Durability evidence.** Actual file-backed reopen/new-instance tests recovered edge bodies, actual source references, scopes, topic IDs/memberships and historical state. Real v2 preservation/rollback and concurrent readers/writers passed. WAL and FULL synchronization are used where available; this is not a hardware power-loss benchmark or multi-host service.

27. **Documentation.** Seven requested existing documents updated; temporal-graph.md, stage4-validation.md and this 32-item report added. Only Stage 4 is newly marked complete. Historical Stage 1-3 reports remain historical.

28. **Limits.** RAM-only conflict grammar, explicit validity, no objective fact verification, unknown legacy recording time, operation recording rather than certified commit time, immutable topic parentage and no general relationship retraction/edit workflow. Graph history audit lists are known-at filtered while effective state applies valid-at separately. Paging is live across calls; limit failures never discard stored evidence. No semantic ranking or full entity linking.

29. **Stage 5 prerequisites.** Define lexical/vector index lifecycle and consistency, provider/index metadata, ranking-score semantics, graph/temporal uncertainty in candidate selection, cache isolation, measured token/evidence budgeting and retrieval validation. Preserve graph/source identities and proof. Stage 5 requires separate manual inspection and approval.

30. **Git.** main/6dfbaeb and history preserved. Sixteen new and eighteen modified project files, unstaged. No commit, push, remote creation, reset/history rewrite or global Git change. Existing ignore rules cover environments, secrets, SQLite/WAL/SHM, model weights, caches/logs and temporary synthetic data.

31. **TRACE.AI.** Unchanged; no TRACE file checkout/access/edit or runtime dependency was introduced.

32. **Milestone boundary.** Only Stage 4 was added. No embeddings/lexical/vector/hybrid retrieval, background Mind Agent, MCP/network transport, TRACE adapter, research benchmark, cloud deployment, frontend or release milestone was implemented. Work stops here.

~~~powershell
.\.venv\Scripts\python.exe -m pytest -v --basetemp .test-artifacts\manual-stage4-tests
.\.venv\Scripts\oomp.exe --version
.\.venv\Scripts\oomp.exe doctor
.\.venv\Scripts\python.exe examples\stage4_temporal_graph.py --db .\data\stage4-synthetic.sqlite3
.\.venv\Scripts\oomp.exe storage status --db .\data\stage4-synthetic.sqlite3
.\.venv\Scripts\oomp.exe graph neighbors --tenant tenant-stage4-example --namespace synthetic --memory-id ram-old-4 --db .\data\stage4-synthetic.sqlite3
.\.venv\Scripts\oomp.exe graph history --tenant tenant-stage4-example --namespace synthetic --memory-id ram-old-4 --valid-at 2026-09-10T00:00:00Z --db .\data\stage4-synthetic.sqlite3
.\.venv\Scripts\oomp.exe graph topic-tree --tenant tenant-stage4-example --namespace synthetic --root-topic-id ai --db .\data\stage4-synthetic.sqlite3
.\.venv\Scripts\oomp.exe graph propose --tenant tenant-stage4-example --namespace synthetic --source ram-disputed-8 --target ram-old-4 --db .\data\stage4-synthetic.sqlite3
~~~
