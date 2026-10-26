# Ten-stage roadmap

This implementation stops after Stage 7. Stages 1–6 retain their accepted baseline; Stage 7 validation and manual assessment are recorded below. Later stages are planned work, not installed or operational capabilities.

| Stage | Name | Status | Acceptance focus |
| --- | --- | --- | --- |
| 1 | Foundation & Architecture | Implemented — acceptance checks passed | Editable independent package; domain/retrieval contracts; six protocols; offline CLI; documentation; passing tests |
| 2 | Persistent Event Storage | Implemented — acceptance checks passed | Scoped SQLite events, replay/idempotency, migrations and recovery |
| 3 | Memory Extraction & Canonicalization | Implemented - acceptance checks passed | Offline grounded extraction, scoped canonical identities, complete evidence and conservative entities |
| 4 | Temporal Associative Graph | Implemented - acceptance checks passed | Typed evidence-backed edges, temporal history, conservative governance and shared topic projections |
| 5 | Hybrid Retrieval Engine | Implemented - acceptance checks passed | Scoped SQLite FTS5/vector/temporal/graph recall, opt-in local embeddings and counted evidence packets |
| 6 | Background Mind Engine | Implemented — acceptance checks passed | Durable intake/jobs, restart recovery, bounded maintenance, summary revisions, governed reviews and privileged privacy administration |
| 7 | MCP Server & Plug-in Integration | Implemented; see Stage 7 validation | Official SDK 2.3.0, stdio/stateless loopback HTTP, scoped reads and host-approved ingestion |
| 8 | TRACE.AI Integration | Planned | External adapter without coupling OOMP's core to TRACE |
| 9 | Research Benchmarking | Planned | Fair baselines, ablations, reproducible datasets and measured results |
| 10 | Release & Research Readiness | Planned | Distribution review, compatibility, documentation and research artifacts |

Stage 1 is marked implemented only after installation, tests, CLI, imports, compilation and packaging checks actually pass. Stage 2 is marked implemented only after durable file-backed storage, scoped retry/concurrency, pagination, CLI and full regression checks pass. Stage 3 is marked implemented after real v1 migration/rollback, canonical-memory/entity durability, per-event atomicity, provenance/scopes, CLI, offline example and full regressions passed. Stage 4 is marked implemented after v2 preservation/rollback, edge/topic durability, source-grounded confirmed resolution, historical knowledge/validity, bounded traversal, scoped concurrency and full regressions passed. Stage 5 adds bounded retrieval and optional local embeddings after migration, scope, temporal, budget, provider-failure, CLI and full regression checks. Stage 6 acceptance adds explicit workers and durable maintenance; Stage 7 separately adds MCP capabilities; benchmarks remain planned.


Stage 2 final validation: **120 passed in 22.18s**, including all 79 original Stage 1 cases. [Validation](stage2-validation.md) and [completion report](stage-2-report.md). Stages 6–10 remain planned.

Stage 3 final validation: **192 passed in 55.90s**, including all 120 earlier cases. [Validation](stage3-validation.md) and [completion report](stage-3-report.md). Work stops here.

Stage 4 final validation: **226 passed in 94.91s**, including all 192 prior cases. Additional explicit self/circular-supersession and untrusted-scope assertions passed in the seven-case temporal file (7.52s), with production unchanged. [Validation](stage4-validation.md) and [completion report](stage-4-report.md). This records the Stage 4 checkpoint; Stage 5 acceptance follows below.


Stage 5 final validation (2026-10-16 client date): **279 passed in 139.16s**, including all 226 prior cases and 53 new cases. Offline persistent long-history retrieval, scoped FTS5, vectors, temporal state/lineage, graph limits, packet accounting and CLI checks passed. Live Ollama embeddings remain pending installation of an embedding model; mock adapter validation and synthetic vector mechanics passed. [Validation](stage5-validation.md) and [completion report](stage-5-report.md). Work stops for manual assessment. No Stage 6 work, commit or push.

Stage 6 baseline (2026-10-16 client date): **279 passed in 147.14s** before production changes, from clean main commit 5459184. Final Stage 6 acceptance, limitations and manual procedures are recorded in [validation](stage6-validation.md) and the [40-item report](stage-6-report.md). Stages 7–10 remain planned. No commit or push is authorized.

Stage 6 final validation (2026-10-27 client date): **321 passed in 221.73s**, including all 279 earlier cases and 42 new cases. Real SQLite migration, atomic process claims, crash replay, bounded retries/maintenance, versioned evidence-backed summaries, governed reviews, source retraction and constrained privileged erasure passed. Compilation, dependency/version/doctor checks and fresh/repeated synthetic demonstrations passed. Live-model inference remains untested. [Validation](stage6-validation.md) and [40-item report](stage-6-report.md). Work stops for manual verification. Stages 7–10 remain planned; no TRACE change, commit or push.

Stage 7 baseline (2026-10-27 client date): **321 passed in 227.79s** before production edits, from clean main commit d911dc9. Stage 7 adds only the optional local SDK adapter, configuration and host-approval boundary; SQLite stays v5. Final acceptance results and compatibility limits are in [validation](stage7-validation.md) and the [39-item report](stage-7-report.md). Stages 8–10 remain planned. Stop for manual assessment; no TRACE changes, commit or push.

Stage 7 final validation: **392 passed in 365.59s**, preserving all 321 earlier cases and adding 71. Both actual SDK stdio and HTTP long-history demos passed; modern protocol 2026-07-28 and SDK legacy HTTP were exercised. Compilation, dependencies, installed CLI/doctor, readiness and migration/test hash preservation passed. No final test warnings. External desktop hosts and live embeddings remain unverified. See [validation](stage7-validation.md) and [report](stage-7-report.md).