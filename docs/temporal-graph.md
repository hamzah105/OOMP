# Temporal associative graph

Stage 4 adds structural graph inspection over the existing canonical SQLite memories. A graph relationship connects two MemoryNode IDs. A topic is a projection record, and a membership references an existing canonical memory. Events, entities, topics and memories remain distinct kinds of records.

No lexical/vector search, semantic ranking, token-budget packing, background consolidation, model resolver, network API or MCP transport is implemented.

## Assertions, identity and evidence

All nine existing relationship types are retained: ABOUT, RELATED_TO, PART_OF, DERIVED_FROM, OCCURRED_IN, SUPPORTS, CONTRADICTS, SUPERSEDES and DEPENDS_ON. Both endpoints are canonical memories in the same authorized tenant and namespace. Event or entity IDs cannot substitute for memory endpoints.

An assertion preserves its MemoryEdge fields, storage recording time, trusted recording principal and actual source evidence. The logical identity includes scope, directed endpoints, relationship type and explicit validity bounds. Reusing a logical relationship retains the first edge ID and attaches new evidence; changing stable data under an existing edge ID is a conflict. Input record creation times are not used as system recording times.

Source IDs must exist inside the authorized partition. Evidence attachment is transactional and deduplicated by scoped edge/event pair. Readback resolves actual SourceReferences rather than accepting invented copies. Every evidence attachment has its own recording time, allowing historical views to exclude proof added later.

General relationship creation is a trusted administrative assertion backed by source references. OOMP does not prove the meaning of arbitrary RELATED_TO or SUPPORTS statements. CONTRADICTS and SUPERSEDES use a stricter source-grounded governance path and cannot bypass it through generic edge insertion.

Only initial active assertions are accepted by this stage's persistence policy. No update, delete, silent retraction or automatic MemoryNode-status overwrite API is supplied. The graph remains auditable because accepted assertions and their supporting evidence remain present.

## Two temporal questions

valid_at asks about reported real-world validity. known_at asks which assertions and evidence OOMP had recorded by a system-clock cutoff. These are independent UTC-aware timestamps. Caller-supplied MemoryNode.created_at and MemoryEvent.ingested_at retain their original semantics; they do not establish trustworthy system knowledge time.

Validity uses half-open intervals [valid_from,valid_until). An explicit upper bound excludes the exact end instant. Missing validity bounds are unknown, not assertions of permanent truth. A query with insufficient bounds reports that uncertainty instead of claiming a timeless fact. Source occurrence and recording dates do not automatically supply fact-validity dates.

New memory/source links and graph assertions receive recording timestamps inside their persistence transaction. Backdated source events therefore do not appear in a known_at view from before the actual write. An edge recorded later is excluded from an earlier knowledge view even when its claimed valid_from is earlier. Supporting events added to an existing edge or memory later are also excluded.

Pre-v3 records do not have an authoritative original recording clock. Migration preserves this as unknown and records a history-start observation. Views earlier than that observation cannot reconstruct legacy knowledge precisely. The system must return an explicit incomplete/unknown result rather than invent original insertion dates. Seeing a legacy record at migration establishes its existence by that observation; it does not establish its first recording date.

This is minimal temporal history over immutable claim bodies and append-only graph assertions, not a complete general bitemporal versioning system. There is no retroactive arbitrary fact editing or revision of every field. Database administrators can bypass application invariants; the clock is the local system clock, not an authenticated external time service. Timestamps record writes within transactions rather than hardware-certified commit instants.

## Conflict identification

The default comparison policy intentionally supports a tiny recognizable domain. It requires actual user-source statements and consistent canonical memory content:

~~~text
My test computer has N GB RAM.
I upgraded my test computer to N GB RAM.
~~~

It compares the same reported computer and installed-RAM attribute under the same scope and conditions. It does not manufacture slots from arbitrary metadata, topic membership, embeddings or model output. Assistant assertions are not promoted into authoritative user state. Plans, uncertainty, different subjects/predicates or unsupported source constructions produce an explicit insufficient-structured-evidence result.

Different values are not sufficient by themselves. A contradiction needs compatible assertions and explicit overlapping validity. Unknown end dates cannot be assumed to overlap forever. A newer source or a more recent ingestion date does not prove that its claim is true.

A supersession proposal requires an explicit supported upgrade/change statement, compatible old/new subjects and attributes, different values, and a coherent later change time supplied as explicit validity. The parser does not infer that time merely from event occurrence. It preserves original claims and evidence.

## Proposals and trusted resolution

Inspection produces a validated proposal or an uncertainty result without changing persistence. A proposal identifies scoped memory endpoints, relationship candidate, supporting source IDs, explicit validity, policy version and reason, and requires confirmation.

Applying a proposal requires trusted AuthorizedScope and deliberate confirmation. The store rereads the actual endpoints and source events and rederives the supported policy decision inside the same write transaction. Modifying IDs, evidence, relation, dates or policy fields cannot create an unsupported resolution. A repeated valid application reuses the existing relationship.

A SUPERSEDES edge points from the replacement to the older memory. Effective historical status is derived from visible, applicable assertions. The older memory body and source references remain intact. An unresolved CONTRADICTS assertion remains a dispute; no automatic winner or supersession is chosen.

Confirmation is an API/CLI governance boundary for trusted local callers. It is not remote-user authentication and does not grant a model direct write authority.

## Topic projections and hierarchy rules

Topics are explicitly created with stable scoped identities. A child refers to an existing same-scope parent. Parentage is immutable in this stage; no reparent/delete workflow is implemented. Topic cycles and self-parenting are rejected.

A membership associates a topic with an existing same-scope memory. A memory can have many memberships without a copied MemoryNode, changed canonical key or duplicated evidence. Membership retries preserve the first pair and recording details. Projections provide deterministic child and membership ordering with explicit resource limits.

A tree result is a bounded projection, not the complete associative graph. The same memory ID can appear beneath Local Models and Robotics. Topics are not automatically inferred from every source sentence, and topic overlap does not imply contradiction.

PART_OF memory edges and SUPERSEDES chains also reject self-links and directed cycles. General associative cycles such as A RELATED_TO B, B RELATED_TO C, C RELATED_TO A are allowed. Hierarchy validation is serialized with insertion and fails closed when its bounded cycle check cannot establish safety.

## Scope, transactions and traversal

Every operation revalidates AuthorizedScope and checks tenant and namespace on objects, cursors, endpoints, source events and SQL lookups. Composite foreign keys reinforce those checks. Topic strings, cursor positions and event content grant no authority.

All edge/evidence groups and governed resolutions use one BEGIN IMMEDIATE transaction. A failure rolls back the whole operation. Independent connections close after use; database constraints and serialized writes establish consistency across processes. Multi-query reads use one snapshot. [SQLite isolation](https://www.sqlite.org/isolation.html).

Traversal is deterministic structural inspection: visited-node tracking, depth/node/edge/work ceilings, relationship and direction filters, and scope checks at every step. High fan-out and cycles cannot cause an unbounded walk. A bound returns an explicit truncated result or a typed limit failure. It is not a semantic retriever.

Keyset pages have bounded sizes and scope/filter validation. Paging is a live view, not one snapshot across an entire multi-call scan. A later-arriving item behind a cursor may require restarting the scan.

## Migration and privacy

Schema version 3 is additive to the unchanged v1/v2 migration definitions. It preserves all events, event triggers, canonical IDs/content, memory-source links, entity IDs and aliases. New graph/history/topic tables and scoped indexes are verified before commit. Failed upgrade rolls back to the genuine previous schema and data; unsupported future or malformed schemas are rejected.

The database remains plaintext. Provenance and fingerprints protect API consistency, not objective truth, cryptographic authenticity or filesystem administrators. No encryption or secure erasure is claimed. Local CLI operations rely on trusted machine access and hide canonical content by default; identifiers and topic names may themselves be sensitive.

The Stage 4 example uses synthetic RAM claims and explicitly supplied validity, shared topic memberships and an unresolved dispute. It does not expand the Stage 3 extractor to force unsupported grammar into extraction. Trusted MemoryStore creation supplies genuine stored source references.

## Retrieval integration

Stage 5 reuses these scoped identities, typed relationships, evidence, temporal filters and bounded structural inspection. Its implemented index consistency, provider/model compatibility, rank semantics, uncertainty handling, evidence budgets and partition isolation are documented in [retrieval](retrieval.md). Graph inspection alone does not establish semantic relevance or enlarge an LLM context window.

See [storage](storage.md), [memory model](memory-model.md), [extraction](extraction.md), [security](security-model.md), [Stage 4 validation](stage4-validation.md) and [completion report](stage-4-report.md).

## Storage layout and public inspection boundary

| Record | Purpose |
| --- | --- |
| graph_meta | Start of reliable Stage 4 history observation |
| memory_recordings | System recording time for new memories; null for legacy original recording times |
| memory_source_recordings | Recording time of each memory/evidence attachment, independent of source timestamps |
| memory_edges | Immutable typed memory endpoints, logical key, claimed validity, recording principal/time and governance metadata |
| edge_evidence | Ordered source-event pairs with their attachment times |
| topics | Scoped immutable parent/name records |
| topic_memberships | Scoped topic/memory pairs referencing the original canonical node |

The original events, memories, memory_sources, entities, entity_aliases and memory_entities structures are retained. New AFTER INSERT triggers capture recording times for memory/source inserts through existing Stage 3 APIs. Edge and evidence immutability triggers protect ordinary SQL updates/deletes. [SQLite trigger behavior](https://www.sqlite.org/lang_createtrigger.html).

SQLiteGraphStore preserves GraphStore.put_edge and edges_for. Additional scoped methods expose add/get/list edges, immediate neighbors, bounded traversal, memory state/history and confirmed resolution. EdgeRecord keeps the original MemoryEdge and actual SourceReferences with per-attachment recording times. MemoryState returns temporal knowledge/validity and evidence without copying a current full MemoryNode into a historical result.

SQLiteTopicStore supplies explicit topic creation, children, membership and bounded projection operations. GraphService provides a local orchestration boundary for ordinary links, advisory conflict proposals and confirmed resolution. Read current canonical content separately through MemoryStore when deliberately needed; a historical view does not silently import its later evidence.

To inspect which candidate facts were known at a cutoff, enumerate existing scoped bounded MemoryStore pages and inspect each candidate through memory_state/history with known_at. This stage supplies structural primitives rather than an unbounded history-wide or semantic query engine.

## Exact inspection semantics and limits

GraphHistory's incoming/outgoing lists are audit assertions filtered by known_at; their explicit validity bounds remain visible. MemoryState.valid evaluates the memory's own claimed interval at valid_at, and effective_status/superseded_by apply only a visible supersession whose interval is established at that instant. An unknown replacement interval can make effective status unknown. With no valid_at, effective status describes the latest recorded structural assertions rather than proving validity now. An unresolved contradiction does not mark either memory superseded.

MemoryState.known is true, false or null: established knowledge, not recorded by the cutoff, or insufficient legacy recording information. valid is null when no date is requested or validity is insufficient. Evidence and recorded_at accompany that result. Canonical content is intentionally obtained separately through the trusted memory API.

The recording clock is the adapter-owned SQLite function oomp_recorded_at(). It captures actual microsecond UTC on first use after the write lock and reuses that instant for the connection's write operation, including its initial evidence group. This avoids millisecond truncation and partially visible initial groups in historical projections. Version 3 writes must use OOMP's connection setup, which registers this function; raw external SQLite writers would need the same trusted setup. Reads and backups do not require writing through a model or network service.

| Operation | Bound |
| --- | --- |
| Edge pages | Strict 1-100 records with scoped keyset cursor |
| Complete immediate neighbors | Strict 1-1000; excessive fan-out raises GraphLimitError |
| Structural traversal | Depth 0-10, nodes 1-500, at most 2000 edges and 10,000 examined edge items |
| Hierarchy cycle validation | At most 1000 nodes and 10,000 examined edge items; inconclusive safety fails closed |
| Evidence per edge | At most 1000 source pairs |
| Aggregated graph proof | At most 10,000 evidence items per bounded inspection result/budget |
| Complete per-node history | At most 100 incoming and 100 outgoing assertions |
| Topic projection | Depth 0-10, nodes 1-500, memberships 0-1000 |

Neighbors support incoming, outgoing and both directions plus relationship filters; traversal follows both directions with relationship filtering. Complete bounded calls raise a typed limit error when completeness cannot be promised. Projection/traversal cutoffs expose truncated. A returned traversal edge has both endpoints among returned node IDs.

## Local commands

~~~powershell
.\.venv\Scripts\python.exe examples\stage4_temporal_graph.py --db .\data\stage4-synthetic.sqlite3
.\.venv\Scripts\oomp.exe storage status --db .\data\stage4-synthetic.sqlite3
.\.venv\Scripts\oomp.exe graph neighbors --tenant tenant-stage4-example --namespace synthetic --memory-id ram-old-4 --db .\data\stage4-synthetic.sqlite3
.\.venv\Scripts\oomp.exe graph history --tenant tenant-stage4-example --namespace synthetic --memory-id ram-old-4 --valid-at 2026-09-10T00:00:00Z --db .\data\stage4-synthetic.sqlite3
.\.venv\Scripts\oomp.exe graph topic-tree --tenant tenant-stage4-example --namespace synthetic --root-topic-id ai --db .\data\stage4-synthetic.sqlite3
.\.venv\Scripts\oomp.exe graph propose --tenant tenant-stage4-example --namespace synthetic --source ram-disputed-8 --target ram-old-4 --db .\data\stage4-synthetic.sqlite3
~~~

The proposal command writes nothing. Deliberately recording the supported unresolved contradiction uses an explicit local governance flag:

~~~powershell
.\.venv\Scripts\oomp.exe graph link --tenant tenant-stage4-example --namespace synthetic --source ram-disputed-8 --target ram-old-4 --relationship CONTRADICTS --event-id hardware-disputed --event-id hardware-old --confirm-resolution --db .\data\stage4-synthetic.sqlite3
~~~

This records a dispute with both source references; it does not choose a winner. Repeating the command reuses the same logical edge. Ordinary links use the same command without confirm-resolution and require actual source IDs. UTC offsets are required for supplied timestamps. No graph command prints canonical memory content by default.

Use storage init --db PATH explicitly to upgrade an existing genuine v2 OOMP database. Graph reads and commands never initialize or migrate implicitly. Keep demonstration data separate from real history.


## Stage 5 retrieval consumer

Stage 5 consumes the graph through the same scoped read snapshot as lexical/entity/topic/vector candidate lookup. It applies known_at to memories, attached evidence, relationships, relationship proof, topics and memberships, and applies valid_at independently. as_of is a compatibility alias for valid_at. Original pre-v3 recording time and open validity bounds remain uncertain.

Current reported retrieval follows governed replacement relationships; historical evidence remains available with its original source. Relevant unresolved contradictions remain alternatives rather than an automatic winner. Returned graph paths refer to actual visible, scoped edges and proof. Expansion has explicit depth/node/edge/work bounds and a relevance gate; structural adjacency alone does not add unrelated branches. Retrieval writes no relationships and cannot bypass Stage 4 confirmation/policy.

Historical known_at requests disable the entity expansion lane because entity aliases and memory/entity associations lack a complete recording-time history. Topic/membership clocks are available and are filtered. This is an explicit conservative limitation rather than inferred historical identity. [Retrieval policy and limits](retrieval.md).

## Stage 6 maintenance and endorsement

The worker records bounded durable review proposals from the existing pure policy; it does not automatically insert protected CONTRADICTS or SUPERSEDES edges. Trusted approval must pass the existing confirmed resolution transaction. Unsupported semantic relationships remain unsupported; the extraction grammar is unchanged.

Dedicated topic summary revisions use explicit memberships and real source proof. Their revision history does not fabricate SUPERSEDES edges and is inspected separately from canonical recall. Recording time governs known_at. Retraction invalidates affected support and projections while retaining original events. Privileged erasure can remove private historical proof and summaries; graph-dependent erasure cases that cannot be safely cleaned are rejected. [Background governance and privacy](background-mind.md).
