# Public API and compatibility

P1's additive local administrator CLI is documented in [product CLI](product-cli.md).
Its diagnostic JSON format and profile settings have format version 1. These are
operational settings, not a memory database migration or new network authority.
Existing domain, retrieval, worker and MCP signatures below remain unchanged.

Distribution `oomp-memory`, Python import `oomp`, version 0.1.0, SQLite schema v6.
This is an alpha API reference, not a promise of 1.0 stability. Public contracts
below have regression coverage. Private helpers, SQL layout, scheduler internals
and research-file schemas are experimental implementation details.

| Surface | Import / operations |
| --- | --- |
| Domain | `oomp.domain.models`: `AuthorizedScope`, `RequestedScope`, `MemoryEvent`, `SourceReference`, `MemoryNode`, `MemoryEdge`; enums in `oomp.domain.enums` |
| Source store | `oomp.storage.SQLiteEventStore(path=None, *, busy_timeout_ms=5000)`; explicit `initialize() -> int`, `status()`, `append(scope, event)`, `get(scope, event_id)`, `list_events(scope, *, limit=100, after=None)`, `count_events(scope)` |
| Extraction | `oomp.ingestion.ExtractionPipeline(path=None, *, extractor=None).process_event(scope, event_id)` |
| Canonical memories | `oomp.storage.memory_store.SQLiteMemoryStore`; `get`, `list_memories`, `find_by_canonical_key`, `attach_evidence`, `list_entities`; `upsert` is trusted local administration, not a remote injection API |
| Graph | `oomp.graph.GraphService`; `link(scope, source_node_id, target_node_id, relationship_type, source_event_ids, *, valid_from=None, valid_until=None)`; `propose_conflict`, `resolve(scope, proposal, *, confirm)` and bounded/history/topic reads |
| Retrieval | `oomp.retrieval.engine.RetrievalEngine(path=None, *, provider=None)`; `index(scope, *, batch_size=16, include_embeddings=False)`, `index_status(scope)`, `retrieve(scope, request)` |
| Retrieval values | `oomp.retrieval.contracts.RetrievalRequest`, `RetrievalResponse`, `MemoryEvidence`, `GraphPath`, `EmbeddingSpace`; immutable/extra-forbidden Pydantic values |
| Optional vectors | `oomp.providers.ollama.OllamaEmbeddingProvider(*, model, dimension, endpoint='http://127.0.0.1:11434', timeout_seconds=15.0, version='ollama-api-embed-v1', ...)`; explicit construction, no automatic calls |
| Background work | `oomp.mind.scheduler.MindScheduler`, `oomp.mind.worker.MindWorker`, `oomp.mind.handlers.MindHandlers`; explicit local orchestration; exact bounded usage in [the Stage 6 example](../examples/stage6_background_mind.py) |

`AuthorizedScope` requires tenant, namespace and principal but is not an
authentication token. All stores revalidate actual partition/proof. Constructors
do not create databases. Equal scoped event retries preserve original identity;
conflicting evidence raises a typed storage error. Unsupported/foreign/newer
schemas fail, rather than being reset. [Storage](storage.md).

`RetrievalRequest` requires tenant, namespace and query. Defaults: lexical mode,
8 results, 1,200 UTF-8 accounting units, 40 candidates, neighborhood depth 1.
Depth 0–2 and result/evidence/work bounds are validated. `valid_at` asks reported
applicability; `known_at` asks recorded knowledge. `historical` does not grant
cross-scope access. Missing validity remains uncertain. Semantic mode requires
compatible complete vectors; hybrid degradation is explicit. Scores are ranking
signals, not truth probabilities. `context_packet` contains counted evidence;
the outer response/MCP and application prompt overhead are additional.

## CLI and wire contracts

`oomp` and `python -m oomp` expose the same command tree: `doctor`, `storage`,
`memory`, `graph`, `retrieve`, `retrieval`, `mind`, `mcp`. Use `--help` at each
level for the authoritative flags. Content display is opt-in. Missing/invalid
operations have nonzero exits with sanitized messages. No command implicitly
starts a worker, downloads a model or initializes storage on read.

MCP names remain `memory.retrieve`, `memory.expand`, `memory.get_source`,
`memory.status`; optional `memory.ingest` requires the trusted-ingest profile,
write grant and separate payload-bound approval. No remote erase, raw SQL, merge
or conflict-approval tool exists. JSON schemas reject extra fields; caller scope
is never accepted from tool arguments. Default source lookup omits raw content.
SDK compatibility is `mcp>=2.3.0,<2.4`; actual protocol/client evidence and
configuration schemas are in [MCP integration](mcp-integration.md).

P3 storage is schema v6. MCP service admission requires a ready database at the
current supported schema, and current `memory.status`/`mcp check` output reports
6. The `StatusResult.schema_version` response enum accepts only 5 and 6 so a
current client can still validate a legacy v5 server response. This does not
admit or automatically migrate an old database, and future versions remain
rejected. Clients whose response contract accepts only 5 must upgrade before
reading v6 status. Grants, capabilities, approval and message shape are unchanged.

`oomp.objects.ObjectMap` provides explicit scoped, bounded build, lookup,
membership, history, explanation and redacted export. It reuses existing source
records and does not call a provider or create remote MCP authority. See the
[object architecture](object-memory-architecture.md) and [CLI/API guide](object-memory-cli.md).

Schema migration version, package version, SDK version and MCP protocol version
are different numbers. Future 0.1.x fixes should preserve covered behavior where
possible; a breaking externally consumed change requires explicit documentation
and maintainer review. New schema versions must be additive/migrated, with older
data preserved. No gratuitous rename or breaking production API change was made
in release preparation. Research adapters/configs are versioned experimental
artifacts and should be frozen with hashes for each run.
