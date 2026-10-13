# OOMP — Object-Oriented Context Map

OOMP is an independent, provider-neutral research project for long-term AI memory. Its intended architecture transforms raw experience into typed, canonical, conflict-aware memory objects, organizes them in a multi-view temporal graph, and returns bounded evidence through hybrid lexical, vector, temporal and relational retrieval.

Potential uses include persistent project context, changing user preferences, documented decisions, and evidence-backed agent memory across compatible applications. These are future use cases; Stage 1 supplies the contracts and Stage 2 adds durable source-event history.

## Current scope

Stage 1 is implemented and acceptance-verified (79 tests passed). It includes validated domain and retrieval schemas, six replaceable component protocols, an offline diagnostic CLI, unit tests, and architectural, security and research documentation. Stage 2 adds a SQLite event store, scoped idempotent ingestion, chronological pages and storage diagnostics (acceptance verified: 120 total tests passed, including all original 79). There is no extraction model, graph engine, search ranking, background worker, MCP server, TRACE adapter, inference, or dashboard. A token budget limits selected evidence; it does not enlarge an LLM's native context window.

The Python import is `oomp`; local distribution metadata uses `oomp-memory` version `0.1.0`. This does not assert ownership or reservation of a PyPI name. OOMP does not import or modify TRACE.AI. Its eventual adapter belongs at an external integration boundary.

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

Installation may download the small Python dependencies. Once installed, commands and tests require no network service, external database server, model, GPU, MCP host, or cloud credentials. Stage 2 tests create temporary SQLite files. Storage configuration is optional; see `sample.env` and the storage guide. OOMP does not auto-load environment files.

`doctor` checks this foundation's Python compatibility, installed Pydantic dependency, package imports, and local readiness. Its exit code is nonzero when required checks fail. Use `storage status` separately to inspect Stage 2 storage. Doctor does not create or require a database and does not report future retrieval/MCP services as operational.

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
    retrieval/
        __init__.py
        contracts.py
    storage/
        __init__.py
        config.py
        errors.py
        migrations.py
        sqlite.py
tests/
docs/
```

The domain owns identity, provenance, scope and temporal validation. Retrieval owns typed requests, evidence and graph-path metadata. Protocols define service boundaries; Stage 2 implements EventStore with a SQLite adapter. Other components remain contracts. CLI code depends on these contracts, while the domain has no provider SDK or application dependency.

## Dependencies

Runtime: Python `>=3.11`, Pydantic `>=2.9,<3`. Development: pytest `>=8,<10`. Build backend: setuptools `>=77`, supporting modern license metadata. `argparse`, datetime, enums and protocols come from the standard library. See [pyproject.toml](pyproject.toml) for the source of constraints.

SQLite now uses the standard library, with no added package dependency. Planned dependencies remain separate: a local embedding model and replaceable vector indexes, optional extraction providers, and the official MCP Python SDK v2 in Stage 7. They are not runtime dependencies today. Recheck compatibility and security at each stage; see [architecture](docs/architecture.md).

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

- [SQLite event storage and exact retry policy](docs/storage.md)
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
