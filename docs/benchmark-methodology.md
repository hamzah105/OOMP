# Benchmark methodology

Client date: 2026-10-27. Stage 9 asks whether structured, temporal associative
memory improves source-grounded retrieval and downstream answers under controlled
budgets. It allows negative results. Engineering acceptance tests and synthetic
research observations have different meanings.

## Frozen experiment boundary

`benchmarks/` is separate from production `src/oomp`. No production algorithms,
schema, MCP protocol or TRACE source are changed. Each run creates a new directory
and fresh explicitly named synthetic SQLite files. The harness has no MongoDB
dependency or production-database selector. It accepts configuration parameters,
not imported personal histories. Imports start no workers or models.

Dataset/config hashes and hypotheses are registered before the held-out run in
the ignored `frozen-registration.json` audit. Each run freezes input JSON before
query execution and records its code hash, Git commits where used, Python/OS/
SQLite/dependency versions, CPU count/architecture, seed, timings and model space.
No environment dump, account identifier, machine hostname, token or unnecessary
absolute home path belongs in a manifest. The code hash records uncommitted
benchmark code; the production Git commit alone would be insufficient.

The primary endpoint is **source-level Recall@8 on positive-source queries**,
case-macro averaged with history-cluster bootstrap. Negative queries are reported
separately, not assigned a fabricated positive recall. All scheduled methods,
queries and repetitions remain in raw records; unsuccessful positive queries
contribute zero recall/precision/MRR/nDCG/hits. Unavailable infrastructure is
explicit, cannot earn successful abstention, and cannot support a comparative
quality claim. It is not filtered away to improve a mean.

## Equal inputs and controlled capacity

All methods receive the same tenant/namespace and user-source history prefix.
`history_cutoff` and explicit `known_at` jointly bound *recording/availability*
time. Late reports use their actual fictional ingestion time, even if occurrence
is earlier. Future, assistant-only and foreign sources are excluded before index
construction. Every record carries an independently recomputable source digest;
the validator rejects different histories or budgets across methods.

Source histories are replayed through the real Stage 2 store and Stage 3
extractor. RAM observations additionally use the disclosed curated source
annotations. Every canonical-memory method sees the same resulting bodies and
source proof, including structured validity bounds. It does not receive relevance
IDs or expected answers. General graph assertions are fixture-authored inputs,
supported by actual source events; protected links pass the real Stage 4 policy
and confirmed transaction. This is not a measurement of automatic relation
discovery. Unsupported extraction remains a real limitation, not a reason to
inject query truth into OOMP.

The production packer counts complete JSON evidence, source references, IDs,
validity and returned paths in conservative **UTF-8 bytes**, capped at 12,000 in
executed comparisons. Result cap and scoring cutoff are eight. TRACE-N8 retains
all eight eligible prior user interactions in chronology; overflow is a visible
failed comparison, not silent truncation. Different representations have
different provenance/path overhead within the same ceiling. Equal ceilings do
not imply identical useful text or computational work.

For optional generation, all methods use the same neutral instruction template,
evidence-only recent-context policy, same model/options/output limit and 16,000
byte prompt ceiling. No historical methods get an additional free recent window.
The prompt ceiling plus 512 reserve and 256 overhead fits the configured 32,768
context proxy. Bytes are not the model tokenizer, output tokens and bytes are
different units, and exact tokenizer overflow cannot be certified by this proxy.
Real output and effective options are recorded; mocks never become accuracy data.

## Knowledge and validity clocks

Fictional dataset dates are immutable labels, not the machine clock. A separate
physical database is created for each eligible prefix. Explicit known-at queries
map that replay to the actual post-build OOMP recording instant; production
storage assigns timestamps naturally. No SQL clock rewrite or production
monkeypatch is used. A separate integration test appends a backdated event later
and verifies that real OOMP known-at filtering excludes it. Entity augmentation
remains disabled by production policy for explicit known-at requests. Common
prefix exclusion is a fairness guard for all methods, not a special OOMP quality
advantage. `valid_at` remains the fixture's reported validity instant.

## Statistical procedure

Methods are paired by `(case_id, repetition)` on the same immutable fixture.
For each metric, draw histories with replacement using a seeded standard-library
PRNG, retain all eligible queries/repetitions from each sampled history and compute
the case-macro mean. The 2.5th/97.5th interpolated percentiles of 2,000 resampled
means form the held-out descriptive 95% interval (smoke/live: 1,000). Paired effect
sizes are OOMP-minus-baseline recall differences resampled at the same history
level. Fewer than two histories yields a null interval. Repetitions are not new
independent histories. Missing/failed positive results retain their denominator.

The four held-out seeds generate 48 distinct synthetic streams, not 48 people or
independently authored template families. Queries from one history share a
cluster. Templates/grammar remain related across histories and splits, so the
intervals describe this generator under fixed policies. They are not evidence of
general statistical significance, a population effect or an independently blinded
final research evaluation. No thresholds are adjusted after viewing held-out
results; later tuning requires new held-out fixtures and a new run identity.

## Measurement and threats to validity

`perf_counter_ns` measures milliseconds. Separate records cover source ingestion,
combined extraction/canonicalization/persistence, curated writes, graph/topic
updates, lexical checks/index construction, summary compression, embedding/index
work and retrieval including packing. Trigger FTS time, independent
canonicalization, OOMP-internal packing and MCP transport overhead cannot be
isolated here and remain null/unmeasured. Model generation is a separate layer.
Do not subtract noisy unrelated timings and call the difference transport cost.

Method order rotates deterministically per query. First query means a prepared
adapter's first query, not a cold OS cache or cold Ollama model. Subsequent queries
are labeled warm. Single repetition supports initial distributions, not stable
hardware performance claims. Mean/median/stdev are reported with counts; p95 needs
20 samples and p99 needs 100 in the relevant phase. Successful timings are
conditioned on success; failure counts remain adjacent in the report.

SQLite file/page-object sizes are observed where `dbstat` exists. Flat vector
numeric payload is an explicitly labeled float64 approximation, not total Python
heap use. Windows peak working set is cumulative for the whole harness process;
it excludes the separate Ollama process and is not allocated to individual
methods. Inventory weight size is disk size, not model RAM. Concurrent experiment
processes can contend for the same desktop; cross-run latency should not be
treated as a controlled hardware comparison.

Canonical baselines incur shared extraction costs. OOMP additionally incurs
graph/topic and its own index costs. Raw N8/summary do not need the canonical
preprocessing merely because the harness built it for other methods. Flat vector
and OOMP embed independently with identical settings; no hidden free embedding
cache is assigned to one method. OOMP's scoped temporary BM25 corpus adds query
cost, whereas flat FTS uses its prepared single-scope index. Add preparation,
embedding and summary costs before amortized performance conclusions.

The dataset is small, formulaic and author-generated. Lexical tasks do not prove
semantic generalization. Curated temporal/graph inputs do not measure extraction
coverage. Path packing may add cost without recall gains. A lexical endpoint hit
does not prove relational reasoning. Answer exact-match/F1 cannot certify
unsupported assertions or nuanced conflicts; unscored outputs require blinded
human review. No cloud/external memory system, public deployment, AGI, infinite
context, human-memory equivalence, universal factuality or novelty claim is made.

Reproduction commands are in [the benchmark README](../benchmarks/README.md).
Actual outcomes and experiment omissions are in [validation](stage9-validation.md).
