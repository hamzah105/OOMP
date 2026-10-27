# OOMP — Object-Oriented Context Map

OOMP is an independent, provider-neutral research project for long-term AI memory. Its intended architecture transforms raw experience into typed, canonical, conflict-aware memory objects, organizes them in a multi-view temporal graph, and returns bounded evidence through hybrid lexical, vector, temporal and relational retrieval.

Potential uses include persistent project context, changing user preferences, documented decisions, and evidence-backed agent memory across compatible applications. Stage 1 supplies the contracts, Stage 2 adds durable source-event history, and Stage 3 derives conservative, attributed canonical memories.

## Current scope

Stage 1 is implemented and acceptance-verified (79 tests passed). It includes validated domain and retrieval schemas, six replaceable component protocols, an offline diagnostic CLI, unit tests, and architectural, security and research documentation. Stage 2 adds a SQLite event store, scoped idempotent ingestion, chronological pages and storage diagnostics (acceptance verified: 120 total tests passed, including all original 79). Stage 3 acceptance passed: **192 tests**, including the original 120. It adds deterministic offline extraction, schema version 2 canonical-memory/entity persistence, scoped evidence deduplication, and synchronous atomic processing. Its validation results are recorded in [Stage 3 validation](docs/stage3-validation.md). Stage 4 acceptance passed: **226 total tests**, including all 192 prior cases. It adds a typed temporal graph, explicit topic projections, bounded structural traversal and conservative conflict governance; its results are recorded in [Stage 4 validation](docs/stage4-validation.md). Stage 5 acceptance passed: **279 total tests**, including all 226 prior cases. Stage 5 adds offline lexical retrieval, explicit local semantic/hybrid modes, derived SQLite v4 indexes and bounded evidence packing. Its implementation and validation are documented in [retrieval](docs/retrieval.md) and [Stage 5 validation](docs/stage5-validation.md). Stage 6 acceptance passed: **321 total tests**, including all 279 prior cases. It adds explicit durable workers, scoped outbox/jobs, versioned extractive summaries and local governance/privacy administration. Its results are recorded in [Stage 6 validation](docs/stage6-validation.md). Stage 7 adds an optional official-SDK MCP adapter with stdio, authenticated loopback stateless HTTP, read-only discovery and separately approved ingestion. See [MCP integration](docs/mcp-integration.md) and [Stage 7 validation](docs/stage7-validation.md). Stage 8 integration is implemented independently in TRACE; Stage 9 research and its optional generation bridge are described below. Dashboards remain future work. A token budget limits selected evidence; it does not enlarge an LLM's native context window.

The Python import is `oomp`; local distribution metadata uses `oomp-memory` version `0.1.0`. This does not assert ownership or reservation of a PyPI name. OOMP's production package does not import TRACE.AI. Stage 8 is implemented in TRACE's independent repository; Stage 9 adds the separate synthetic research harness described below.

## Windows development setup

Use Python 3.11 or newer and PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest -v
oomp --help
oomp --version
oomp doctor
python -m oomp --help
```

Activation is optional. If PowerShell activation is restricted, or `python` resolves to an unusable system launcher, use the environment's executable directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\oomp.exe --help
.\.venv\Scripts\oomp.exe --version
.\.venv\Scripts\oomp.exe doctor
.\.venv\Scripts\python.exe -m oomp --help
```

Installation may download the small Python dependencies. Once installed, commands and tests require no network service, external database server, model, GPU, MCP host, or cloud credentials. Storage and extraction tests create temporary SQLite files. Storage configuration is optional; see `sample.env` and the storage guide. OOMP does not auto-load environment files.

`doctor` checks this foundation's Python compatibility, installed Pydantic dependency, package imports, and local readiness. Its exit code is nonzero when required checks fail. Use `storage status` separately to inspect Stage 2 storage. Doctor does not create or require a database and does not exercise retrieval, an embedding model or an MCP service.

## Package layout

```text
src/oomp/
    __init__.py
    __main__.py
    cli.py
    domain/
        __init__.py
        enums.py
        models.py
        interfaces.py
        events.py
        memories.py
        graph.py
        graph_policy.py
    retrieval/
        __init__.py
        contracts.py
        engine.py
        fusion.py
        packing.py
    providers/
        ollama.py
    mind/
        cli.py
        contracts.py
        scheduler.py
        worker.py
        handlers.py
        consolidation.py
        governance.py
    ingestion/
        contracts.py
        extraction.py
        canonicalization.py
        pipeline.py
    graph/
        __init__.py
        service.py
    storage/
        __init__.py
        config.py
        errors.py
        migrations.py
        sqlite.py
        memory_store.py
        entity_store.py
        graph_store.py
        topic_store.py
        retrieval_store.py
        mind_store.py
        mind_projection_store.py
        privacy_store.py
tests/
docs/
```

The domain owns identity, provenance, scope and temporal validation. Retrieval owns typed requests, evidence and graph-path metadata. Protocols define service boundaries; Stage 2 implements EventStore with a SQLite adapter. Stage 3 implements MemoryStore and deterministic MemoryExtractor, with provider-neutral candidate/entity contracts and separate SQLite persistence. Stage 4 implements scoped graph storage and structural inspection. Stage 5 implements MemoryRetriever and an optional loopback Ollama embedding adapter behind the existing embedding protocol. CLI code depends on these contracts, while the domain has no provider SDK or application dependency.

## Dependencies

Runtime: Python `>=3.11`, Pydantic `>=2.9,<3`. Development: pytest `>=8,<10`. Build backend: setuptools `>=77`, supporting modern license metadata. `argparse`, datetime, enums and protocols come from the standard library. See [pyproject.toml](pyproject.toml) for the source of constraints.

SQLite now uses the standard library, with no added package dependency. Optional local embedding models run separately through Ollama; vector persistence and cosine search use the standard library. Optional extraction providers remain future work. The Stage 7 MCP transport is an optional extra. No model or provider SDK is a compulsory runtime dependency. Recheck compatibility and security at each stage; see [architecture](docs/architecture.md).

## Tests and verification

```powershell
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pip check
git status --short
git remote -v
```

Tests cover event/source consistency, provenance, identity validation, memory and relationship enums, confidence, timestamps and intervals, JSON round trips and metadata, bounded retrieval contracts, CLI behavior, and import independence. See [the validation report](docs/validation.md) for the actual environment, commands and results.

## Documentation and roadmap

- [SQLite events, canonical memories, migration and retry policy](docs/storage.md)
- [Deterministic extraction, canonical identity and entity aliases](docs/extraction.md)
- [Temporal graph, topics and conflict governance](docs/temporal-graph.md)
- [Hybrid retrieval, indexing and evidence budgets](docs/retrieval.md)
- [Background Mind Engine](docs/background-mind.md)
- [Stage 6 validation](docs/stage6-validation.md)
- [Complete Stage 6 report](docs/stage-6-report.md)
- [Stage 5 validation](docs/stage5-validation.md)
- [Complete Stage 5 report](docs/stage-5-report.md)
- [Stage 4 validation](docs/stage4-validation.md)
- [Complete Stage 4 report](docs/stage-4-report.md)
- [Stage 3 validation](docs/stage3-validation.md)
- [Complete Stage 3 report](docs/stage-3-report.md)
- [Architecture](docs/architecture.md)
- [Memory model and temporal example](docs/memory-model.md)
- [Security and tenancy](docs/security-model.md)
- [Research plan](docs/research-plan.md)
- [Detailed ten-stage roadmap](docs/roadmap.md)
- [Complete Stage 1 report](docs/stage-1-report.md)
- [Stage 2 validation](docs/stage2-validation.md)
- [Complete Stage 2 report](docs/stage-2-report.md)

| Stage | Work |
| --- | --- |
| 1 | Foundation & Architecture |
| 2 | Persistent Event Storage |
| 3 | Memory Extraction & Canonicalization |
| 4 | Temporal Associative Graph |
| 5 | Hybrid Retrieval Engine |
| 6 | Background Mind Engine |
| 7 | MCP Server & Plug-in Integration |
| 8 | TRACE.AI Integration |
| 9 | Research Benchmarking |
| 10 | Release & Research Readiness |

The roadmap records completion only after acceptance checks pass. No novelty, retrieval quality or benchmark superiority is claimed. Licensed under [Apache-2.0](LICENSE).


## Stage 2 local event history

Construct `SQLiteEventStore(path)`, explicitly `initialize()`, then use an authorized scope with `append`, `get`, `list_events` and `count_events`. Reads return the validated Stage 1 MemoryEvent with its original provenance. Equal retries return the original record; conflicts never overwrite it. Page sizes are bounded and keyset cursors are scope checked. See the storage guide for exact payload equivalence and concurrency limits.

```powershell
.\.venv\Scripts\oomp.exe storage init --db .\data\events.sqlite3
.\.venv\Scripts\oomp.exe storage status --db .\data\events.sqlite3
.\.venv\Scripts\python.exe examples\stage2_event_roundtrip.py --db .\data\synthetic-demo.sqlite3
```

Without `--db`, `OOMP_DB_PATH` overrides the platform user-data default. Missing `storage status` returns nonzero and creates no database. Storage diagnostics expose no event content. The example uses synthetic data and can be rerun. This is reliable event history, not intelligent associative recall.

## Stage 3 canonical memory extraction

The default pipeline reads one scoped source event, validates conservative candidates and their exact evidence spans, computes scoped canonical identities, resolves explicit project names, and commits memories, evidence and entity links together. Equivalent memories reuse the first ID and accumulate source events; reprocessing the same event adds no duplicate rows. Claims remain attributed and unverified. No model, internet connection or GPU is needed.

~~~powershell
.\.venv\Scripts\python.exe examples\stage3_memory_extraction.py --db .\data\stage3-synthetic.sqlite3
.\.venv\Scripts\oomp.exe storage status --db .\data\stage3-synthetic.sqlite3
.\.venv\Scripts\oomp.exe memory list --tenant tenant-stage3-example --namespace synthetic --db .\data\stage3-synthetic.sqlite3
~~~

The example uses synthetic records and verifies persisted results after reopening. Use its printed scope and event IDs when trying `memory extract --tenant TENANT --namespace NAMESPACE --event-id EVENT_ID --db PATH`. Memory listing omits canonical content unless the trusted local operator supplies `--show-content`. Tenant strings do not authenticate a caller: these local administrative commands rely on machine/filesystem access. Memory commands require explicitly initialized schema 2 or later; graph commands require schema 3 or later; use `storage init` to upgrade a genuine version 1 database without replacing its events.

Stage 3 coverage is deliberately narrow. Exact/conservatively normalized identity is implemented; unrestricted paraphrase equivalence, independent fact verification, general semantic equivalence and full entity linking are not. Stage 4 adds explicit evidence-backed temporal relationships without expanding the extractor.

## Stage 4 temporal associative graph

Canonical memories can participate in persistent typed memory-to-memory relationships and appear in multiple explicit topic branches without duplication. Structural neighbors/traversal and historical views remain scoped and bounded. Valid reported time and system knowledge time are separate; unknown legacy recording dates and unknown validity stay explicit.

Conflict inspection proposes changes without writing. Applying supported CONTRADICTS or SUPERSEDES relationships requires trusted scope, explicit confirmation and source-policy revalidation in the storage transaction. A newer message alone never establishes supersession. Original claims and evidence remain intact.

The [synthetic Stage 4 example](examples/stage4_temporal_graph.py) demonstrates evolving RAM claims, one memory in two topic branches and an unresolved contradiction. See [the temporal graph guide](docs/temporal-graph.md) for API, CLI, migration and limitations. Graph inspection supplies structure; Stage 5 applies relevance, temporal filtering and packet budgets before returning evidence.


## Stage 5 long-term recall

The default retriever searches persisted canonical memories through real SQLite FTS5/BM25 and augments them with exact identities, explicit topics and bounded relevant graph paths. It returns source-attributed evidence under a disclosed context budget. Semantic/hybrid modes require explicit local embedding configuration and compatible durable vectors; standard tests and the synthetic example run without any model or network service.

~~~powershell
.\.venv\Scripts\python.exe examples\stage5_hybrid_retrieval.py --db .\data\stage5-synthetic.sqlite3
.\.venv\Scripts\oomp.exe retrieve --help
.\.venv\Scripts\oomp.exe memory index --help
.\.venv\Scripts\oomp.exe retrieval status --help
~~~

The example compares an early project fact with a latest-eight-only view after more than 100 later synthetic events, then demonstrates synthetic vector mechanics, governed RAM history, graph relevance and whole-evidence budget drops. Synthetic vectors do not measure real semantic quality. The default UTF-8-byte counter measures the actual evidence JSON; the outer diagnostic response and host prompt overhead are separate. CLI content display requires --show-content. See [retrieval](docs/retrieval.md) for limits, optional Ollama setup and manual commands, and [validation](docs/stage5-validation.md) for actual executed results.

## Stage 6 controlled background work

Events enter a transactional SQLite outbox. An explicitly configured scoped worker dispatches durable jobs, reuses the existing extraction pipeline and maintains indexes. Leases, fencing, bounded retries and canonical/evidence idempotency support restart-safe at-least-once execution. Workers do not start on import. Embeddings remain opt-in; default operation needs no model, network service or GPU.

Consolidation creates dedicated evidence-backed topic revisions without changing canonical facts. Background conflict inspection records reviews; protected relationships still require trusted confirmation through Stage 4. Corrections append new source events. Privileged local erasure requires a dependency plan and explicit confirmation, preserves independent evidence and rejects unsupported dependency cases.

~~~powershell
.\.venv\Scripts\python.exe examples\stage6_background_mind.py --db .\data\stage6-synthetic.sqlite3
.\.venv\Scripts\oomp.exe mind --help
~~~

See [background behavior and privacy limits](docs/background-mind.md), [executed acceptance checks](docs/stage6-validation.md) and the [40-item Stage 6 report](docs/stage-6-report.md). Summary artifacts are inspected explicitly; Stage 5 retrieval continues to return canonical evidence.

## Stage 7 local MCP access

Install the optional adapter with python -m pip install -e ".[dev,mcp]". Read-only tools expose existing retrieval, bounded temporal graph expansion, linked provenance and scoped readiness. Trusted ingestion needs a separate server profile, capability and host-signed approval. SQLite stays v5 and no worker starts with the server.

~~~powershell
.\.venv\Scripts\python.exe examples\stage7_mcp_client.py --transport stdio
.\.venv\Scripts\python.exe examples\stage7_mcp_client.py --transport streamable-http
.\.venv\Scripts\python.exe -m oomp mcp --help
~~~

These synthetic examples run actual SDK clients, recover early memory after 105 later turns, and clean up their temporary storage/listeners. Configure your own existing database and explicit scope using the [Windows connection guide](docs/mcp-integration.md). Host configuration generation prints placeholders without editing host applications. Tested compatibility is the official SDK Client (modern and legacy HTTP), not every desktop AI host. See [security](docs/mcp-security.md), [validation](docs/stage7-validation.md) and the [39-item report](docs/stage-7-report.md) for that checkpoint.

## Stage 9 reproducible research

The independent TRACE repository now has its optional Stage 8 MCP integration.
Stage 9 leaves both production codebases and private databases unchanged. The
separate [benchmark harness](benchmarks/README.md) compares latest-eight,
deterministic extractive summary, flat FTS5, optional real vectors and the actual
OOMP engine on frozen synthetic histories. It scores actual source IDs, temporal
evidence and supported graph paths; generated-answer quality is a separate,
explicitly enabled experiment.

~~~powershell
.\.venv\Scripts\python.exe -m benchmarks.runner --action plan --config benchmarks/configs/offline.json
.\.venv\Scripts\python.exe -m benchmarks.runner --config benchmarks/configs/offline.json --output benchmarks/results/my-smoke
.\.venv\Scripts\python.exe -m benchmarks.runner --action validate --run benchmarks/results/my-smoke
~~~

Runs preserve raw results, frozen configuration/dataset hashes, preparation and
query costs, failures, model availability and seeded history-cluster uncertainty.
No model is downloaded; no personal histories are imported. Read
[methodology](docs/benchmark-methodology.md), [datasets](docs/benchmark-datasets.md),
[baselines](docs/benchmark-baselines.md), [metrics](docs/benchmark-metrics.md),
[executed validation](docs/stage9-validation.md) and the
[42-item Stage 9 report](docs/stage-9-report.md). These are initial internal
synthetic results, with negative findings and limitations, not general superiority
or state-of-the-art claims. Stage 10 release work remains pending manual review.
