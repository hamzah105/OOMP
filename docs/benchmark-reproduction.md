# Reproducing the research artifacts

There are three distinct kinds of evidence:

1. Engineering tests validate implementation contracts.
2. Retrieval experiments compare evidence under frozen synthetic conditions.
3. Generated-answer experiments evaluate real model output separately.

Stage 9 executed the first two and a context-only TRACE/MCP study. It did not
execute the live LLaMA answer-quality comparison. Preserve this distinction when
preparing presentations, papers or release notes.

## Frozen study

The source archive includes `benchmarks/`, configs, generator and original reports.
The wheel intentionally contains only runtime OOMP. From the checkout or extracted
source root, after installing core/dev dependencies:

~~~powershell
.\.venv\Scripts\python.exe -m benchmarks.runner --action plan --config benchmarks/configs/offline.json
.\.venv\Scripts\python.exe -m benchmarks.runner --config benchmarks/configs/offline.json --output benchmarks/results/new-smoke
.\.venv\Scripts\python.exe -m benchmarks.runner --action validate --run benchmarks/results/new-smoke
.\.venv\Scripts\python.exe -m benchmarks.runner --config benchmarks/configs/multi-seed.json --output benchmarks/results/new-heldout
~~~

The smoke has six 128-observation histories, 20 queries and 100 scheduled records.
The held-out configuration has 48 generated streams, four seeds, sizes 16/128,
160 queries and nine methods (1,440 records). Its ablations share the same data;
they are not new independent observations. Primary comparison uses 112 positive
queries; 48 negatives score separately. Frozen dataset hashes are in
[stage9-results.json](examples/stage9-results.json). Timing/model output can vary;
generated fixtures and deterministic non-timing scores should reproduce under the
same implementation/settings. No post-result threshold tuning is claimed as unbiased.

Results include frozen config/dataset JSON, source/canonical hashes, commit/code
identity, per-query records (including missing infrastructure/failures), actual
preparation/query costs, complete evidence packets, aggregate JSON, CSV and a
report. Every output path must be new. Partial/interrupted runs remain labeled;
aggregation never silently drops failed queries. Original large local result
folders are ignored and are not distributed as a private database snapshot.

## Optional real comparisons

~~~powershell
.\.venv\Scripts\python.exe -m benchmarks.runner --config benchmarks/configs/full-local.json --enable-embeddings --output benchmarks/results/new-embeddings
~~~

This uses only an already installed healthy embedding model; no weights are pulled.
The recorded model/digest/dimension/configuration must match between flat vector
and OOMP. Without infrastructure, rows are unavailable, not successful synthetic
substitutes. Real embedding Stage 9 results were a small validation sample: four
positive queries from one positive history and four negatives. Flat vector and
hybrid OOMP both had full positive recall and nonempty false matches on every
negative. No superiority or interval from that single positive history is justified.

`python -m benchmarks.trace_compare --config benchmarks/configs/offline.json
--trace-workspace TRACE_PATH --output NEW_PATH` exercises actual MCP/proof/context
functions with synthetic in-memory Mongo fixtures, graph depth zero and six
matched prompt conditions. It does not execute a real chat/login route or model
answers. TRACE remains external and read-only. See its
[independent integration repository](https://github.com/hamzah105/trace-ai-chatbot).

The separate `--action answer --enable-generation` command in
[the benchmark README](../benchmarks/README.md) uses actual TRACE generation with
fixed options. It must be explicitly chosen, records raw model output and requires
independent human review for unsupported assertions/open-ended correctness.
It was not executed for Stage 9 or silently substituted during release hardening.

## What the measurements support

Selected held-out source Recall@8: N8/summary 0.2381, flat lexical 0.7857, full
OOMP 0.9286. Seeded history-cluster intervals are descriptive and conditional on
related authored templates. Recent controls tied at 1.0; disabling neighborhoods
did not reduce recall, and default complete supported paths were 0/16. Entity/topic
ablation reduced recall to 0.7857 on the alias/topic workload. Temporal benefits
use explicit curated RAM validity/proof, not general language understanding.

Budgets count complete UTF-8 evidence JSON, not exact model tokens; retrieval
scores are not answer accuracy. Source completeness is not unique-fact accuracy,
and flat textual relations can support reasoning without an explicit graph-path
field. Precomputation, summary updates and embeddings have measured costs that
must be included in amortized comparisons. Concurrent desktop runs, one repetition,
four seeds and restricted templates prevent broad speed/significance claims.

Read [methodology](benchmark-methodology.md), [datasets](benchmark-datasets.md),
[baselines](benchmark-baselines.md), [metrics](benchmark-metrics.md),
[original validation](stage9-validation.md) and the [manuscript draft](research-paper-draft.md).
No external Mem0/Zep/GraphRAG performance figures were measured by OOMP. A future
comparison needs actual adapters/versions, matching permissions/budgets and real
outputs. No paid/cloud service is part of default reproduction.
