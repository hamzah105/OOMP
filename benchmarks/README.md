# OOMP synthetic research benchmark

This Stage 9 harness evaluates evidence retrieval separately from generated answers.
It is a research workspace, outside the installed `src/oomp` package. It imports
the existing production engine, extractor, stores, graph policy and evidence packer;
it supplies no replacement OOMP ranking algorithm. Default runs are offline,
sequential and bounded. Only generated fictional conversations are accepted.

From the repository root, PowerShell:

~~~powershell
.\.venv\Scripts\python.exe -m benchmarks.runner --action plan --config benchmarks/configs/offline.json
.\.venv\Scripts\python.exe -m benchmarks.runner --action generate --config benchmarks/configs/offline.json --output benchmarks/results/my-fixtures
.\.venv\Scripts\python.exe -m benchmarks.runner --config benchmarks/configs/offline.json --output benchmarks/results/my-smoke
.\.venv\Scripts\python.exe -m benchmarks.runner --action validate --run benchmarks/results/my-smoke
.\.venv\Scripts\python.exe -m benchmarks.runner --action aggregate --run benchmarks/results/my-smoke --output benchmarks/results/my-analysis
.\.venv\Scripts\python.exe -m benchmarks.runner --config benchmarks/configs/multi-seed.json --output benchmarks/results/my-heldout
~~~

Every output must be a **new directory**. Run directories contain frozen
`config.json`, `dataset.json`, `manifest.json`, append/flushed `per_query.jsonl`,
`corpus_costs.jsonl`, disposable persisted SQLite databases, `aggregate.json`,
`metrics.csv` and `report.md`. A failed/interrupted run is not resumed or silently
overwritten. `--allow-partial` permits explicitly labeled inspection; it never
promotes a partial run to complete. Keep the entire run folder for reproduction.
Generated results/databases are ignored. Small reviewed summaries are in
[the validation record](../docs/stage9-validation.md).

The default smoke has 6 histories, 20 cases, 128 interactions/history and five
methods (100 records). The held-out configuration has 48 histories, four seeds,
sizes 16/128 and 160 cases. It executes the baseline comparison and supported
ablations together (1,440 records), avoiding duplicate corpus setup. The separate
`ablations.json` regenerates the **same dataset hash** with an ablation-only method
selection. `scales.json` exposes 16/64/128/512/1024 interaction scaling; inspect its
plan before running. Configuration JSON rejects unknown fields, unsupported
sizes, excessive workloads, mismatched budgets and graph depth above two.

Optional real embeddings, using only an already installed healthy local model:

~~~powershell
.\.venv\Scripts\python.exe -m benchmarks.runner --action plan --config benchmarks/configs/full-local.json
.\.venv\Scripts\python.exe -m benchmarks.runner --config benchmarks/configs/full-local.json --enable-embeddings --output benchmarks/results/my-real-embeddings
~~~

This bounded configuration has 2 histories, 8 queries and 7 methods (56 records).
Flat vector and OOMP use the same `embeddinggemma:latest`, dimension 768,
configuration identity, complete canonical corpus, finite/nonzero float64
normalization, cosine threshold 0.2 and evidence ceiling. Model inventory/digest
and a health probe are checked; no model is downloaded. Without explicit opt-in
or compatible infrastructure, vector/semantic rows say **unavailable**. Their
zeros stay in scheduled denominators, but are never presented as executed quality
comparisons. Hybrid mode fails explicitly when prerequisites are missing.

Optional controlled live answer evaluation, through TRACE's actual generation
function, requires a separate explicit action:

~~~powershell
.\.venv\Scripts\python.exe -m benchmarks.runner --action answer --run benchmarks/results/my-real-embeddings --trace-workspace "D:\Desktop\VU BS-CS\CS619\TRACE" --enable-generation --output benchmarks/results/my-live-answers
~~~

The config caps this action at 14 calls: at most two complete seven-method paired
cases. It can take many minutes on CPU. It uses the existing TRACE environment
read-only, a subprocess with bytecode disabled, and an evaluation HTTP wrapper
around actual `generate_response`. The wrapper pins local `/api/generate`, model,
temperature 0.2, output 140, `num_ctx=32768` and seed 42 for every method. It sends
real requests, never synthetic model answers. Every method receives the same
neutral evidence-only template and total byte cap; no oracle labels or additional
recent context are supplied. This controlled layer is **not** the full Stage 8
chat/Mongo/provenance/MCP pipeline. That separate application comparison remains
pending unless explicitly executed and documented. No TRACE source or MongoDB
record is written. The pure original TRACE formatter can also be inspected through
`adapters.trace.trace_original_prompt` without importing its database modules.

A separate optional **context-only** experiment exercises the actual TRACE MCP
client, wire validation, source-provenance checks and composer, using a real OOMP
HTTP server and a synthetic in-memory Mongo fixture:

~~~powershell
.\.venv\Scripts\python.exe -m benchmarks.trace_compare --config benchmarks/configs/offline.json --trace-workspace "D:\Desktop\VU BS-CS\CS619\TRACE" --output benchmarks/results/my-trace-context
~~~

It uses the actual latest-eight loader/formatter with an in-memory database seam,
normalizes fixture source IDs to TRACE's documented owner/interaction/role mapping,
and creates only fresh OOMP SQLite files under its output. TRACE-N8,
TRACE-N8+OOMP and TRACE-N8+flat lexical retain the same eight recent observations.
Matched neutral-template versions share one total prompt ceiling; OOMP's added
historical information and production instruction-template differences remain
explicit. Synthetic mock Mongo is not real Mongo persistence. This command makes
**zero model calls** and does not execute FastAPI chat/login/publication, so
prompt evidence presence still does not establish answer accuracy. TRACE's
environment needs its existing optional/dev dependencies (`mcp`, `mongomock`).

Read [methodology](../docs/benchmark-methodology.md),
[datasets](../docs/benchmark-datasets.md),
[baseline definitions](../docs/benchmark-baselines.md),
[metric formulas](../docs/benchmark-metrics.md) and
[the Stage 9 report](../docs/stage-9-report.md). Hypotheses and primary analysis
choices were registered in [claims.json](claims.json). Synthetic provider tests
validate harness mechanics; they are never live semantic or answer-accuracy data.

Future external adapters implement `MemoryAdapter.retrieve(Case) -> Result` and
receive the same authorized `Prepared` prefix. Mem0, Zep and GraphRAG have not
been installed, called or measured. Any service credentials, paid calls, versions,
permissions and additional compute require an independent explicit experiment.
