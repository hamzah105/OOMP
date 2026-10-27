# Baselines and supported ablations

All methods have the same eligible user-source prefix, frozen query, scope and
12,000-byte evidence ceiling in executed runs. Complete production evidence JSON
counts toward capacity, including source proof and path overhead. No expected
answer or relevant-source list is supplied to an adapter.

| Adapter | Actual implementation and limits |
| --- | --- |
| TRACE-N8 | Last eight eligible prior user observations in chronological order, query-independent. No earlier source, OOMP retrieval or learned summary. Overflow fails visibly. The separate pure actual TRACE formatter bridge retains its original instructions; this source-only study is not a Mongo chat-route execution. |
| Rolling summary | Offline deterministic extractive compression every four eligible observations. Exact normalized duplicate text retains the most recent source. Recency-prioritized whole evidence fits a fixed storage budget; pending observations are incorporated at query time. The latest eight retained items fit the result ceiling and return chronologically. Positive/negative corrections coexist if capacity permits; no semantic reconciliation. Construction/update cost is measured. This does not represent all learned summaries. |
| Flat lexical | Prepared, single-scope SQLite FTS5/BM25 over the exact common canonical corpus. Unicode literal OR terms and a disclosed stoplist; stable ID tie break. No graph/entity/topic lane or governed temporal replacement. Validity is visible data but does not rerank/filter. Index construction cost and persisted size are measured. |
| Flat vector | Exact normalized cosine scan over the same canonical text as OOMP, dimension/model/config checks, finite nonzero float64 vectors and threshold 0.2. No relationship or temporal assistance. Embeddings use the same production Ollama provider, without download; index/embedding cost is measured independently. Missing infrastructure is unavailable, not a successful synthetic comparison. |
| Full OOMP | Actual Stage 3 extraction/canonicalization, Stage 4 graph/topic/governed policy, Stage 5 engine/fusion/diversity/packer, with graph depth two, default 40 candidates, eight outputs. Offline mode is lexical plus actual entity/topic/graph/temporal lanes. Live primary mode is hybrid with the same embedding space as flat vector. No second OOMP retriever is implemented. |

Shared preprocessing creates canonical memories once using the real pipeline;
curated RAM input is explicitly labeled and shared with flat search/vector. N8 and
summary use raw eligible observations with the same source validity annotations.
All source IDs resolve to actual persisted events. Canonical duplicates can carry
multiple proof IDs; scoring uses those IDs, not an adapter's internal memory ID.
Graph assertions receive actual source proof; protected ones pass production
governance. This evaluates retrieval given those structures, not their automatic
discovery cost or general extraction accuracy.

## Faithful evaluation-only switches

| Ablation | Meaning |
| --- | --- |
| A0 full | Same source/corpus/budget and mode as primary. |
| A1 `oomp_no_graph` | Existing request `graph_depth=0`. Governed replacement/conflict inspection remains active, as production requires. This disables neighborhood expansion, not all governance-related graph reads. |
| A2 `oomp_no_augmentation` | Evaluation-only read-session wrapper returns empty entity/topic candidate lanes while delegating all other scoped reads to the real store. No production writes, global monkeypatch or ranking copy. |
| A3 `oomp_lexical` | Existing lexical mode, retaining other production lanes. It is an intentional identical-control configuration when full is already lexical; it becomes a meaningful semantic-lane ablation in the live hybrid run. |
| A4 `oomp_semantic` | Existing semantic mode with the same real embedding model/configuration. It keeps production temporal/graph safeguards. Unavailable offline; synthetic vectors test mechanics only. |
| A5 temporal off | Not faithfully supported by a production switch. Not executed. The flat lexical comparator lacks governed temporal filtering, but changes other components too, so it is not a causal isolated temporal ablation. The reserved adapter name reports unavailable. |
| A6 projection/consolidation off | Not applicable: Stage 6 dedicated summary artifacts are not consumed by Stage 5 retrieval. No artificial effect is introduced. |
| A7 fusion off | No supported production switch; not executed. Reserved adapter name reports unavailable. Copying/replacing the production planner merely to create this experiment would violate the milestone boundary. |

The benchmark adapter wrappers never disable tenant, source endorsement,
known-at, evidence validation, conflict safety or privileged-write policy.
Untrusted conversation/injection strings cannot change options or execute tools.
The actual Mind worker is not a second benchmark algorithm: synchronous production
extraction is used, and projections unused by retrieval are not assigned invented
benefits. No new consolidation/release/MCP feature is added.

## Separate TRACE experimental layer

The existing read-only workspace's latest-eight loader filters by Mongo session
and owner, sorts descending timestamp then reverses, and includes feedback.
Enabled Stage 8 retrieval calls the official SDK over HTTP with graph depth zero,
validates linked Mongo proof, composes bounded evidence plus the same recent
eight, and calls `generate_response`. Its response timing includes retrieval and
generation, while delivery is separate. Stage 9 does not alter that pipeline.

`adapters.trace` supplies a validated read-only formatter and actual generation
function bridge. Controlled generation uses identical evidence-only instructions
for all memory methods. A full application experiment must separately compare
original TRACE-N8, TRACE-N8+OOMP and a matched-total-budget condition, retain real
Stage 8 MCP/provenance checks and report any extra information capacity. These
full chat-route and live-generation conditions are **pending**, not inferred from
the core retrieval experiment or Stage 8's earlier smoke checks. The Stage 8
production source remains unchanged.

The executable `python -m benchmarks.trace_compare` provides a separate
context-only study. It uses a fresh synthetic OOMP database, actual authenticated
Stage 7 HTTP server, actual TRACE MCP client/wire/provenance/composer modules and
the original TRACE loader/formatter compiled against an in-memory mock Mongo
fixture. It compares N8, N8+OOMP and N8+flat lexical, plus common neutral-template
versions under one total prompt byte ceiling. Original production N8 and enabled
instructions differ; matched versions control that template difference. Added
historical information is the treatment, not an equal-information claim. The
flat comparator receives the same historical corpus and capacity, with a positive
rank-only score assigned solely for TRACE composer eligibility. Source mapping
uses stable synthetic ObjectIds and TRACE role IDs; no real owner credentials,
private chat history or actual MongoDB writes are used. Model calls remain zero.

The context study can demonstrate actual transport/proof/context compatibility,
retain all eight recent observations and expose prompt bytes. It cannot demonstrate
answer accuracy, owner-login/route behavior or real Mongo durability. Client total
latency includes SDK imports/initialization as well as transport, server retrieval
and validation; it is not isolated MCP transport overhead.

Future Mem0/Zep/GraphRAG adapters must implement the documented `MemoryAdapter`
protocol with frozen actual versions, scope/cost/permission disclosures and real
outputs. None is installed or measured here; default runs make no paid/cloud calls.
