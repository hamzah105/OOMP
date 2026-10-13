# Ten-stage roadmap

This implementation stops after Stage 2. Stages 1 and 2 are implemented with acceptance checks passed. Later stages are planned work, not installed or operational capabilities.

| Stage | Name | Status | Acceptance focus |
| --- | --- | --- | --- |
| 1 | Foundation & Architecture | Implemented — acceptance checks passed | Editable independent package; domain/retrieval contracts; six protocols; offline CLI; documentation; passing tests |
| 2 | Persistent Event Storage | Implemented — acceptance checks passed | Scoped SQLite events, replay/idempotency, migrations and recovery |
| 3 | Memory Extraction & Canonicalization | Planned | Replaceable extraction, canonical identity and provenance |
| 4 | Temporal Associative Graph | Planned | Durable typed links, temporal changes and multiple views |
| 5 | Hybrid Retrieval Engine | Planned | Lexical/vector/temporal/relational search and measured budgeted evidence |
| 6 | Background Mind Engine | Planned | Resumable consolidation, conflicts and audited updates |
| 7 | MCP Server & Plug-in Integration | Planned | Official Python SDK v2, stdio/stateless HTTP and authorized scope |
| 8 | TRACE.AI Integration | Planned | External adapter without coupling OOMP's core to TRACE |
| 9 | Research Benchmarking | Planned | Fair baselines, ablations, reproducible datasets and measured results |
| 10 | Release & Research Readiness | Planned | Distribution review, compatibility, documentation and research artifacts |

Stage 1 is marked implemented only after installation, tests, CLI, imports, compilation and packaging checks actually pass. Stage 2 is marked implemented only after durable file-backed storage, scoped retry/concurrency, pagination, CLI and full regression checks pass. Retrieval engines, background workers, MCP capabilities and benchmarks remain unimplemented.


Stage 2 final validation: **120 passed in 22.18s**, including all 79 original Stage 1 cases. [Validation](stage2-validation.md) and [completion report](stage-2-report.md). Stages 3–10 remain planned.
