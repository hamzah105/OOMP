# Retrieval, local embeddings and bounded evidence

Stage 5 selects persisted evidence for an external reasoning model. It does not generate a conversational answer, verify a source claim or increase any model's native context window. Default retrieval is offline and needs only the package dependencies and SQLite FTS5.

## Data flow and isolation

~~~mermaid
flowchart TD
    A[Query and trusted AuthorizedScope] --> B[Validate scope and resource limits]
    B --> C[Optional query embedding outside database snapshot]
    C --> D[One scoped read snapshot]
    D --> E[FTS5 BM25 / compatible cosine / exact entity / topic candidates]
    E --> F[Deterministic rank fusion]
    F --> G[Temporal state and bounded relevant graph paths]
    G --> H[Reranking and duplicate suppression]
    H --> I[Whole-evidence JSON packing under explicit counter]
    I --> J[RetrievalResponse and auditable context packet]
~~~

The trusted caller supplies AuthorizedScope; request tenant/namespace must match it. Constructing a scope object or passing CLI strings does not authenticate a remote user. Every lane, proof lookup and graph step uses both tenant and namespace. Stored text never controls SQL, network settings, graph policy or privileged writes. The retriever is read-only.

## Lexical search and derived index consistency

Schema 4 adds a real FTS5 index over canonical memory text. Migration backfills existing memories; transactional insert synchronization handles new memories. Explicit lexical rebuilding changes only derived rows. Canonical IDs, source rows, entity links, graph assertions and historical recording times remain intact.

Arbitrary queries are converted into bounded quoted Unicode terms rather than accepted as raw FTS query language. SQL values are parameterized. SQLite's BM25 sorts better matches first using numerically lower scores; raw BM25 and cosine values are never summed. [SQLite FTS5](https://www.sqlite.org/fts5.html#the_bm25_function).

BM25 depends on corpus-wide document statistics. To isolate ranking between scopes, this prototype builds a bounded temporary FTS5 rank corpus from the authorized partition inside the read snapshot. It does not use the shared durable index's global statistics. Corpus rows and cumulative text bytes have explicit limits; oversized scopes fail clearly. This costs temporary indexing work per request and is a local prototype boundary, not an ANN or large-corpus performance claim.

## Semantic and hybrid behavior

The existing EmbeddingProvider.embed(texts) protocol remains the transformation seam. Configuration identifies provider, model, configuration version and dimension. Embedding calls have no storage authority and execute outside the read snapshot/write transaction.

Vectors persist with scoped memory identity, provider/model/version, dimension, SHA-256 canonical-content digest and generation time. A changed digest is stale. Different model spaces are never combined, even when dimensions match. Inputs and outputs must be finite numeric vectors with a nonzero norm and expected dimension. Cosine search is a bounded exact scan; the engine applies a configurable minimum cosine of 0.2 by default before fusion. That threshold is an uncalibrated relevance heuristic, not a probability or an accuracy measurement. Orthogonal/negative fixture results are excluded by the default gate. Cosine scan capacity is explicit; exceeding capacity is an error, never a silently incomplete exhaustive search.

Lexical mode is the default. Semantic mode requires an explicit provider and a compatible complete index; it cannot silently become lexical search. Hybrid mode combines lanes and either fails on semantic prerequisites or reports an explicitly requested degraded result with warnings. Scores are ranking signals, never probabilities of truth. Confidence remains unknown without a separate measurement.

## Optional local Ollama setup

Install and run Ollama independently. Provision an embedding-capable model deliberately; OOMP never downloads a model. For example, after reviewing the model's requirements, an operator may run:

~~~powershell
ollama pull embeddinggemma
ollama list
~~~

The optional adapter uses POST /api/embed, explicit model and dimensions, bounded inputs/response, timeout and truncate:false. The latter requests an error rather than silent model-context truncation. The transport permits literal loopback addresses, disables environment proxies and rejects redirects. It has no cloud endpoint option. A local Ollama daemon and its own configuration remain trusted; OOMP cannot independently certify how another local process handles data. [Official embedding API](https://docs.ollama.com/api/embed).

No live embedding result was assumed during development. The local model inventory and actual acceptance status are recorded in [validation](stage5-validation.md). Deterministic providers in tests/examples are synthetic mechanics checks, not real semantic quality measurements. The installed llama3 chat model is not used as an embedding substitute.

## Fusion, identities and relevance

Reciprocal Rank Fusion uses rank positions rather than uncalibrated raw scores: for each distinct memory, sum weight/(60 + rank) over contributing lanes. Default weights are lexical 1, semantic 1, entity 1.5 and topic 1. Ties use stable memory identity. Entity matches are exact normalized names or explicitly evidenced aliases; similar spelling and embeddings do not establish identity. Ambiguous entity names remain separate candidates. Topic candidates come from explicit memberships, not inferred topic classification.

Graph expansion is deterministic and bounded by depth, nodes, edges and examined work. It tracks visited nodes, filters allowed relationship types, requires actual scoped endpoints/proof, and applies historical visibility to links and proof. A neighbor needs query/entity/topic relevance or a justified governed relationship; arbitrary adjacency does not add the entire neighborhood. Returned paths identify actual nodes and edges and disclose whether each directed edge was traversed forward or backward. Reranking preserves stronger direct ranks and puts distinct normalized content ahead of redundant content, while retaining canonical identities. It prefers supported temporal state and useful distinct evidence without blindly preferring recent messages or confusing similarity with verification.

## Current, historical and uncertain evidence

valid_at asks when a claim was reported applicable. known_at asks what OOMP had recorded by that system time. They are independent UTC-aware values. The legacy as_of field maps to valid_at; conflicting explicit values are rejected. Caller source timestamps never replace recording history.

Current retrieval captures one UTC now for interval checks when no explicit valid_at/as_of is supplied. historical=True with no validity instant provides an all-history structural view; known_at alone does not set fact-validity time. Current reported retrieval consumes Stage 4's governed supersession state and prefers active replacements. If relationship applicability is unknown, it preserves uncertain alternatives rather than inventing a definite winner. Historical requests can return the earlier claim. A correction or added proof recorded after known_at cannot enter the result or its graph paths. Pre-v3 original recording dates remain unknown, with only the migration observation available. Missing validity bounds remain uncertain rather than proof of permanent validity. Relevant unresolved contradictions remain attributed alternatives; retrieval creates no resolution writes.

Entity alias creation lacks a complete Stage 4 recording history. Entity aliases and memory/entity associations have no complete recording history. Historical known_at requests therefore disable the entire entity lane and disclose the limitation. Topic records and memberships do have recording timestamps and must respect the cutoff.

## Evidence budget and response boundary

The replaceable TokenCounter counts an explicitly serialized context packet. The default counts UTF-8 bytes as conservative accounting units; this is an estimate, not a universal exact tokenizer. All memory content, JSON wrappers, memory/source IDs, SourceReferences, graph proof/paths and selection explanations in that packet count toward the budget. Whole evidence items are accepted or dropped; claims and provenance are not truncated.

The response exposes estimated_token_count, token_budget, counting_method and the exact context_packet. Empty evidence has the empty-string packet and count zero, including for the compatible token_budget=1 request. Nonempty packet accounting includes its own budget/method/count wrapper and reaches a stable count. The outer transport response and diagnostic trace are outside the evidence budget. A host must count its own surrounding prompt and transport metadata if it forwards them to a model; the full HTTP/JSON response is not promised to fit a one-unit evidence budget.

max_results is an additional ceiling. If nothing fits, OOMP returns structured empty evidence. It does not fill gaps from general model knowledge. The packet is valid JSON when nonempty and treats content as untrusted data; a downstream model host still needs its own instruction and tool-authority boundary.

## Explicit and background indexing

Indexing is a deliberate local operation. It synchronizes lexical rows and optionally embeds bounded batches. Compatible unchanged digests are skipped. A malformed or failed provider batch preserves prior vectors and lexical data; counters and status expose failure and completeness. Embeddings may be incomplete after a partial multi-batch failure, so later semantic requests must check coverage.

Stage 6 supplies explicit scoped durable workers with retries, leases/fencing, backpressure, cancellation and audit. Its handlers reuse these index operations. Provider/model/version/dimension remain pinned; no configured provider means no embedding calls. MCP transport belongs to Stage 7, TRACE integration to Stage 8 and comparative benchmarking to Stage 9.

See [storage](storage.md), [temporal graph](temporal-graph.md), [security](security-model.md), [validation](stage5-validation.md) and [completion report](stage-5-report.md). Exact command examples and limits follow.


## Local capacity and deterministic planning

The storage ceilings are 10,000 lexical documents and 16 MiB canonical UTF-8 content per authorized partition, up to 10,000 compatible vectors per exact scan, 4,096 dimensions, a 4,096-character engine query with at most 32 Unicode terms, and 200 candidates per lane. Operators may lower supported storage scan/corpus limits. Stage 1's request-schema query ceiling of 100,000 remains for compatibility; the executable retriever enforces its smaller work limit.

The request defaults to 40 candidates, graph depth 1 and 16 graph nodes; result and evidence-budget defaults remain 8 and 1200. Hard request bounds remain 100 results and 32768 accounting units. Graph edges/work/relations and constructor/index/provider limits are documented with the final implementation and validation commands. These finite ceilings bound work; they are not throughput or quality measurements.


## Graph and governance limits

Request controls default to graph_depth=1 (0–2), graph_nodes=16 (1–100), graph_edges=40 (1–200) and graph_work=200 (1–1000). Up to eight ranked seeds enter graph expansion. Relationship filters can restrict expansion; depth/node/edge bounds produce an explicit truncation flag or typed limit failure, including high fan-out that cannot be materialized within the work ceiling. Paths contain actual edge evidence, forward/reverse direction and per-edge validity (including null for unknown). Irrelevant neighbors are excluded. Generic adjacency does not attach redundant paths to an already independently ranked fact and displace its essential source evidence from a small packet.

Read-only governance inspection runs even with graph_depth=0, so disabling neighborhood expansion cannot hide a relevant recorded dispute. Replacement inspection starts with the first min(40,candidate_limit) candidates and follows lineage within caps of 40 total scheduled/checked nodes, 20 adjacent replacement records per lookup and 200 examined replacement records. Known expired claims can serve as historical anchors through expired intermediates, but the final current result still needs eligible source/validity and a justified final hop. Historical lineage edges retain false validity in the path rather than being relabeled currently active. These governance paths have separate bounds from neighborhood depth. Conflict inspection caps its initial candidate set at 200, adjacency at 20 per memory, total examined conflict records at 2000, and added counterpart candidates at 40. Returned paths are limited to two per memory. Bounds fail explicitly where a complete protected inspection cannot be established. Claims remain attributed; these checks never write a resolution.

Historical/current labels and whitelisted validity/effective-status metadata appear in the counted evidence payload. A contradiction label does not erase unknown temporal applicability. Other canonical private metadata is not copied into retrieval results.

## Manual commands

Use only a dedicated synthetic database for this example:

~~~powershell
.\.venv\Scripts\python.exe examples\stage5_hybrid_retrieval.py --db .\data\stage5-synthetic.sqlite3
.\.venv\Scripts\oomp.exe memory index --tenant tenant-stage5-example --namespace synthetic --db .\data\stage5-synthetic.sqlite3
.\.venv\Scripts\oomp.exe retrieval status --tenant tenant-stage5-example --namespace synthetic --db .\data\stage5-synthetic.sqlite3
.\.venv\Scripts\oomp.exe retrieve "What project was the user developing?" --tenant tenant-stage5-example --namespace synthetic --db .\data\stage5-synthetic.sqlite3 --token-budget 1200 --json
.\.venv\Scripts\oomp.exe retrieve "test computer RAM" --tenant tenant-stage5-example --namespace synthetic --db .\data\stage5-synthetic.sqlite3 --valid-at 2026-09-10T00:00:00Z --historical --token-budget 3000 --show-content --json
.\.venv\Scripts\oomp.exe retrieve "OOMP project" --tenant tenant-stage5-example --namespace synthetic --db .\data\stage5-synthetic.sqlite3 --mode hybrid --allow-degraded --json
~~~

After deliberate local embedding-model provisioning, the optional real-model acceptance path is:

~~~powershell
.\.venv\Scripts\oomp.exe memory index --tenant tenant-stage5-example --namespace synthetic --db .\data\stage5-synthetic.sqlite3 --embedding-provider ollama --embedding-model embeddinggemma --embedding-dimension 768 --embedding-version embeddinggemma-local-r1
.\.venv\Scripts\oomp.exe retrieval status --tenant tenant-stage5-example --namespace synthetic --db .\data\stage5-synthetic.sqlite3 --embedding-provider ollama --embedding-model embeddinggemma --embedding-dimension 768 --embedding-version embeddinggemma-local-r1
.\.venv\Scripts\oomp.exe retrieve "Which effort is being built?" --tenant tenant-stage5-example --namespace synthetic --db .\data\stage5-synthetic.sqlite3 --mode hybrid --embedding-provider ollama --embedding-model embeddinggemma --embedding-dimension 768 --embedding-version embeddinggemma-local-r1 --token-budget 3000 --show-content --json
~~~

These last commands are manual instructions, not claimed executed model results. Configure the dimension actually supported by the chosen model. Standard retrieval status reports compatible vector coverage only for the explicitly selected space; without a provider it does not aggregate incompatible model spaces or invoke a model.

## Stage 6 projections and erasure

Background extraction makes new canonical memories searchable through the existing transactional lexical trigger. Maintenance checks/repairs lexical state and optionally fills a deliberately configured compatible vector space. Provider outages preserve lexical search and earlier successful vectors; status must continue to report incomplete coverage.

Dedicated topic summaries are not inserted as canonical memories or automatically packed by Stage 5 recall. Their explicit inspection has independent revision/provenance semantics. Retractions withdraw source endorsement without deleting historical events. Privileged erasure removes affected lexical/vector records and summary content before commit; future indexing reads surviving canonical records and cannot restore a deleted source. An already-open read snapshot or an external consumer may retain earlier data, which logical erasure cannot recall. [SQLite snapshot isolation](https://www.sqlite.org/isolation.html). [Background policy and operations](background-mind.md).
