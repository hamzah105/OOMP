# Research plan

OOMP is a research direction, not a demonstrated improvement. No novelty, experimental superiority or memory-performance benchmark result is claimed. Stage 1 tests schema/CLI correctness; it measures no retrieval quality.

## Candidate hypotheses

- Canonical reusable nodes could reduce evidence duplication compared with storing the same fact in separate topic trees.
- Explicit provenance and supersession could improve current-fact accuracy when preferences or project state change.
- Combining lexical, vector, temporal and relational signals could retrieve useful evidence missed by a single index under the same prompt budget.
- Graph-view projections could improve topic navigation without constraining associative links to a physical tree.
- Background consolidation could reduce stale/conflicting evidence, while risking information loss and write amplification.

Each hypothesis requires a measured comparison and may be disproven. A bounded evidence budget optimizes supplied context; it does not increase a model's context-window capacity.

## Baselines

Compare last-N conversation windows (including eight interactions for the future TRACE adapter), flat lexical retrieval, vector-only retrieval, combined lexical/vector retrieval without graph signals, and summary-only memory. Add temporal filtering and graph expansion as controlled ablations. Keep datasets, embedding/extraction models, prompts and evidence budgets comparable.

Test provider independence across adapters without treating a change of generation model as a memory architecture improvement. Include oracle evidence selection as a clearly separate analysis reference.

## Datasets and design

Use consented or synthetic multi-session event streams with stable source IDs and labeled facts. Include changed preferences, contradictory assertions, assistant hallucinations, delayed ingestion, missing validity, multi-project relevance, corrections, deletion and separate tenants. Hold out users/projects and later sessions to limit temporal/identity leakage. Keep source-event splits intact so overlapping turns and extraction outputs do not leak between train and evaluation.

Define current-time and historical `as_of` questions separately. Record ground-truth supporting event IDs and uncertainty. Establish an annotation rubric and inter-annotator agreement before confidence/factuality claims. Report dataset licenses, consent, minimization and erasure handling.

## Future metrics

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

Record hypotheses and analysis choices before comparisons. Publish configuration, dependency/model versions, seeds where applicable, hardware, sample counts, uncertainty intervals and failures. Repeat runs when stochastic extraction affects outcomes. Report negative results/ablations, and separate engineering tests from memory experiments. Dataset and benchmark implementation begins in Stage 9 after preceding functionality exists.

