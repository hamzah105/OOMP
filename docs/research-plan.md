# Research plan

OOMP is a research direction. Stage 9 now provides initial internal synthetic
retrieval measurements through a separate reproducible harness. These observations
do not establish novelty, universal superiority or independently replicated
answer-quality improvements. Stage 1–8 engineering acceptance tests and Stage 9
research measurements remain distinct.

## Candidate hypotheses

- Canonical reusable nodes could reduce evidence duplication compared with storing the same fact in separate topic trees.
- Explicit provenance and supersession could improve current-fact accuracy when preferences or project state change.
- Combining lexical, vector, temporal and relational signals could retrieve useful evidence missed by a single index under the same prompt budget.
- Graph-view projections could improve topic navigation without constraining associative links to a physical tree.
- Background consolidation could reduce stale/conflicting evidence, while risking information loss and write amplification.

Each hypothesis requires a measured comparison and may be disproven. A bounded evidence budget optimizes supplied context; it does not increase a model's context-window capacity.

## Baselines

Compare last-N conversation windows (including eight interactions for TRACE), flat lexical retrieval, vector-only retrieval, combined lexical/vector retrieval without graph signals, and summary-only memory. Add temporal filtering and graph expansion as controlled ablations where faithful production switches exist. Keep datasets, embedding/extraction models, prompts and evidence budgets comparable.

Test provider independence across adapters without treating a change of generation model as a memory architecture improvement. Include oracle evidence selection as a clearly separate analysis reference.

## Datasets and design

Use consented or synthetic multi-session event streams with stable source IDs and labeled facts. Include changed preferences, contradictory assertions, assistant hallucinations, delayed ingestion, missing validity, multi-project relevance, corrections, deletion and separate tenants. Hold out users/projects and later sessions to limit temporal/identity leakage. Keep source-event splits intact so overlapping turns and extraction outputs do not leak between train and evaluation.

Define current-time and historical `as_of` questions separately. Record ground-truth supporting event IDs and uncertainty. Establish an annotation rubric and inter-annotator agreement before confidence/factuality claims. Report dataset licenses, consent, minimization and erasure handling.

## Research measurements

| Area | Candidate measures |
| --- | --- |
| Evidence | Precision/recall at K, MRR/nDCG when labels permit, supporting-event recall |
| Temporal quality | Current-fact accuracy, stale evidence rate, historical-as-of correctness |
| Provenance | Citation correctness, evidence coverage, unsupported assertion rate |
| Budget | Actual tokenizer count, budget violations, useful evidence per token |
| Efficiency | Latency distributions, index/storage footprint, update/write cost |
| Canonicalization | Duplicate rate, false merges/splits, conflict retention |
| Reliability/privacy | Replay correctness, recovery, isolation leakage, deletion propagation |

Generated answer quality is downstream and must be reported separately from evidence quality. Estimated token counts are not exact accounting; define a tokenizer and measure framing/serialization overhead before claiming strict budget compliance.

## Reporting

Record hypotheses and analysis choices before comparisons. Publish configuration, dependency/model versions, seeds where applicable, hardware, sample counts, uncertainty intervals and failures. Repeat runs when stochastic extraction affects outcomes. Report negative results/ablations, and separate engineering tests from memory experiments.

Stage 9 implements [the research harness](../benchmarks/README.md),
[frozen hypotheses](../benchmarks/claims.json), [methodology](benchmark-methodology.md),
[datasets](benchmark-datasets.md), [baseline/ablation definitions](benchmark-baselines.md)
and [metric formulas](benchmark-metrics.md). Actual executed observations, including
unsupported/missing experiments, are recorded in [validation](stage9-validation.md)
and the [completion report](stage-9-report.md). Source recall does not imply answer
accuracy. The deterministic extractive summary does not represent all learned
summarizers; curated temporal input does not measure automatic temporal extraction.

The Stage 10 research handoff should obtain independent fixture authorship,
broader split/template disjointness, exact tokenizer measurement, repeated isolated
latency trials, larger real-embedding evaluations and blinded human review of real
generated answers. No external Mem0/Zep/GraphRAG measurements or paid/cloud calls
are invented. Any method tuning after viewing this held-out sample requires a new
independent evaluation rather than reusing favorable results as unbiased evidence.

