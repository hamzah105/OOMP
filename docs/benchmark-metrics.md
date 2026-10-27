# Metric definitions

Let `R` be the labeled relevant source-event ID set. Flatten evidence in returned
order, using each canonical object's stable source order, and deduplicate source
IDs globally to obtain ranking `S`. Internal memory IDs do not define relevance.
A consolidated object can legitimately recover several actual sources. Evaluate
the first `k=8` distinct source IDs; missing ranks are zeros.

This is source-event completeness, not unique-fact or answer accuracy. An answer
can be supported by one of several corroborating sources even when event recall
is below one. Flat canonical baselines receive the same consolidated source lists.

| Metric | Definition |
| --- | --- |
| Recall@k | `|S[:k] ∩ R| / |R|` on positive queries. |
| Precision@k | `|S[:k] ∩ R| / k`, including missing ranks. |
| MRR | `1 / first relevant source rank`, or zero if absent. |
| nDCG@k | `sum(binary relevance / log2(rank+1)) / ideal DCG`, with ideal length `min(k, |R|)`. |
| Evidence hit | At least one relevant source in the first k. |
| Provenance correctness | Returned distinct IDs resolving to the eligible prefix divided by all returned distinct IDs; null on empty. Exact source references are also checked before scoring. |
| Query coverage | Successful nonempty retrieval divided by all scheduled queries; this is coverage, not correctness. |
| Correct empty | Successful empty retrieval on unanswerable cases. Infrastructure failure/unavailability gets zero. |
| False memory match | Nonempty successful retrieval on an unanswerable case. Topical but non-answering evidence counts conservatively as a false match here. |

Positive recall/precision/MRR/nDCG/hit are **null** on negative queries, so a
large negative set cannot inflate positive retrieval quality. Failed/unavailable/
invalid positive rows have zero scores and remain in counts. Empty provenance is
undefined, not perfect provenance. Invalid budget, source, reference or packet
accounting marks the comparison invalid before scoring; such evidence cannot
earn credit. Run validation checks the full case × method × repetition rectangle,
input digests, scope-prefix digests, equal budget and absence of duplicate rows.

N8 and the extractive summary always supply stored context without query-based
selection. Their nonempty result on a negative query is therefore a consequence
of policy. Empty-result metrics compare retrieval behavior and cannot establish
that a downstream N8/summary model would answer unsupported questions incorrectly.

## Temporal evidence and paths

Current-state, historical-state, superseded-claim and late-arrival metrics are
reported separately by task. Temporal evidence correctness requires **all**
required sources and no explicitly forbidden state source. It is not generated
answer correctness: retrieving an old source does not imply that the model
claimed it was current. Known-at fidelity checks source visibility against the
frozen prefix. The independent store integration test also verifies a later
recorded backdated event cannot appear in an earlier real known-at view.

Disputed queries require both competing claims. `conflict_evidence_coverage`
measures source retention; `conflict_labeling` also requires production
`contradicted` labels on the relevant evidence. Raw unannotated alternatives do
not receive automatic conflict-labeling credit. The unsupported uncertain-RAM
query has a separate temporal-abstention metric. Unknown validity is preserved.

Required multi-hop pairs come from actual fixture graph links. Returned paths
must identify existing stored edge IDs, matching node endpoints, relationship
types, traversal orientation and nonempty exact source-proof sets. Duplicate
segments do not add credit. Relevant hops recovered counts distinct required
pairs recovered by valid segments. Chain completion additionally requires all
relevant endpoint sources. Direct lexical retrieval of every endpoint with no
returned relationship proof earns source recall but **zero chain completion**.

Path validity is valid returned segments / all returned segments (zero when a
required path is absent). Irrelevant expansion is segments outside the required
chain, including invalid segments, / all returned segments. Source-proof
retention checks exact original proof. Three-hop requirements are labeled
separately from configured depth two; disconnected or invented paths cannot
become success through a correct answer string.

Structured path metrics require an adapter that exposes explicit paths. Flat
baselines may return relationship statements as text from which a model could
reason. Their lack of structured paths must not be presented as proof of failed
multi-hop answers. Use path completion primarily for the controlled OOMP
neighborhood ablation, alongside source recall and separately measured answers.

## Answers, uncertainty and timing

Optional real generated output has normalized exact match and multiset token F1,
maximized over distinct acceptable references. Normalize case and word tokens;
remove bracketed source citations for EM/F1 and score citation alignment
separately. `F1 = 2 × token overlap / (answer length + reference length)`.
Correct abstention recognizes a small explicit phrase set (`UNKNOWN`,
`insufficient evidence`, `not in current session memory`, `I do not know`). This
set is limited; richer semantically valid answers require human review.

A failed model call always gets zero EM/F1/abstention, never a correct synthetic
answer. Citation alignment checks bracketed IDs against supplied evidence; it
does not prove the cited content entails the prose. Unsupported assertion rate
and nuanced contradiction answer correctness remain null unless human review is
provided. No LLM judge is used. Reference string overlap is not universal
factuality. Mock generator tests are harness tests, not model measurements.

Aggregate intervals and paired effects use the seeded history-cluster bootstrap
described in [methodology](benchmark-methodology.md). One history has no interval;
the held-out four-seed sample does not support broad significance claims. Metrics
and their denominators are reported by category, task and recent-window
availability, alongside failures/unavailable rows. Latency distributions use
observed successful samples, counts and explicit first/warm phase labels;
unobserved timings are null. Tail percentiles require 20/100 samples for p95/p99.

Exact machine-readable definitions are included in every run manifest. The raw
records retain both returned synthetic packets and source IDs so another analyst
can audit the scored evidence instead of trusting a headline number.
