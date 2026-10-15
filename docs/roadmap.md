# Ten-stage roadmap

This implementation stops after Stage 5. Stages 1-5 are implemented with acceptance checks passed. Later stages are planned work, not installed or operational capabilities.

| Stage | Name | Status | Acceptance focus |
| --- | --- | --- | --- |
| 1 | Foundation & Architecture | Implemented — acceptance checks passed | Editable independent package; domain/retrieval contracts; six protocols; offline CLI; documentation; passing tests |
| 2 | Persistent Event Storage | Implemented — acceptance checks passed | Scoped SQLite events, replay/idempotency, migrations and recovery |
| 3 | Memory Extraction & Canonicalization | Implemented - acceptance checks passed | Offline grounded extraction, scoped canonical identities, complete evidence and conservative entities |
| 4 | Temporal Associative Graph | Implemented - acceptance checks passed | Typed evidence-backed edges, temporal history, conservative governance and shared topic projections |
| 5 | Hybrid Retrieval Engine | Implemented - acceptance checks passed | Scoped SQLite FTS5/vector/temporal/graph recall, opt-in local embeddings and counted evidence packets |
| 6 | Background Mind Engine | Planned | Resumable consolidation, conflicts and audited updates |
| 7 | MCP Server & Plug-in Integration | Planned | Official Python SDK v2, stdio/stateless HTTP and authorized scope |
| 8 | TRACE.AI Integration | Planned | External adapter without coupling OOMP's core to TRACE |
| 9 | Research Benchmarking | Planned | Fair baselines, ablations, reproducible datasets and measured results |
| 10 | Release & Research Readiness | Planned | Distribution review, compatibility, documentation and research artifacts |

Stage 1 is marked implemented only after installation, tests, CLI, imports, compilation and packaging checks actually pass. Stage 2 is marked implemented only after durable file-backed storage, scoped retry/concurrency, pagination, CLI and full regression checks pass. Stage 3 is marked implemented after real v1 migration/rollback, canonical-memory/entity durability, per-event atomicity, provenance/scopes, CLI, offline example and full regressions passed. Stage 4 is marked implemented after v2 preservation/rollback, edge/topic durability, source-grounded confirmed resolution, historical knowledge/validity, bounded traversal, scoped concurrency and full regressions passed. Stage 5 adds bounded retrieval and optional local embeddings after migration, scope, temporal, budget, provider-failure, CLI and full regression checks. Background workers, MCP capabilities and benchmarks remain planned.


Stage 2 final validation: **120 passed in 22.18s**, including all 79 original Stage 1 cases. [Validation](stage2-validation.md) and [completion report](stage-2-report.md). Stages 6–10 remain planned.

Stage 3 final validation: **192 passed in 55.90s**, including all 120 earlier cases. [Validation](stage3-validation.md) and [completion report](stage-3-report.md). Work stops here.

Stage 4 final validation: **226 passed in 94.91s**, including all 192 prior cases. Additional explicit self/circular-supersession and untrusted-scope assertions passed in the seven-case temporal file (7.52s), with production unchanged. [Validation](stage4-validation.md) and [completion report](stage-4-report.md). This records the Stage 4 checkpoint; Stage 5 acceptance follows below.


Stage 5 final validation (2026-10-16 client date): **279 passed in 139.16s**, including all 226 prior cases and 53 new cases. Offline persistent long-history retrieval, scoped FTS5, vectors, temporal state/lineage, graph limits, packet accounting and CLI checks passed. Live Ollama embeddings remain pending installation of an embedding model; mock adapter validation and synthetic vector mechanics passed. [Validation](stage5-validation.md) and [completion report](stage-5-report.md). Work stops for manual assessment. No Stage 6 work, commit or push.
