# Stage 9 validation

Client date: 2026-10-27. Initial internal synthetic evaluation; production OOMP and TRACE code are unchanged.

Final acceptance: **498 passed in 430.57s (0:07:10)**. **106 new tests**, all **392 original regressions** preserved. No skipped tests.

## Executed experiments

| Experiment | Histories | Queries | Records | Successful | Unavailable | Failed/invalid |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| stage9-offline-smoke | 6 | 20 | 100 | 80 | 20 | 0 |
| stage9-heldout | 48 | 160 | 1440 | 1120 | 320 | 0 |
| stage9-live-embeddings | 2 | 8 | 56 | 56 | 0 | 0 |

Experiments B (primary comparison) and C (ablations) share the same 160 held-out cases and dataset hash in one run; they are not counted as independent duplicated data. Across A/B-C/D there are **1,596 scheduled records**, including **1,256 successful** and **340 explicitly unavailable**. No failed/invalid records were removed. The held-out run has four seeds, 48 distinct generated histories, 112 positive queries from 40 histories and 48 negatives from 24 histories; these subsets overlap by history.

The context-only TRACE study adds **4 queries × 6 prompt conditions** on a 128-observation synthetic history. Actual authenticated HTTP MCP protocol 2026-07-28, TRACE wire/proof/composition functions and the original recent-eight loader/formatter ran successfully using only in-memory mock Mongo. Model calls and real MongoDB writes: **zero**. This is separate from retrieval-table counts and does not establish live answer accuracy.

## Held-out retrieval

All means below use positive-source queries (k=8), not negative-query accuracy. Intervals use 2,000 seeded history-cluster resamples. Unavailable offline methods have scheduled zero scores in raw denominators but are shown as unavailable, not measured quality.

| Method | Recall@8 | Descriptive 95% interval | Warm median ms |
| --- | ---: | --- | ---: |
| trace_n8 | 0.2381 | [0.1584, 0.3248] | 1.2407 |
| rolling_summary | 0.2381 | [0.1584, 0.3248] | 1.1363 |
| flat_lexical | 0.7857 | [0.7083, 0.8559] | 0.3669 |
| flat_vector | unavailable offline | not a measured comparison | unavailable |
| oomp_full | 0.9286 | [0.8880, 0.9655] | 9.9438 |
| oomp_no_graph | 0.9286 | [0.8880, 0.9655] | 9.5099 |
| oomp_no_augmentation | 0.7857 | [0.7083, 0.8559] | 8.8136 |
| oomp_lexical | 0.9286 | [0.8880, 0.9655] | 10.2907 |
| oomp_semantic | unavailable offline | not a measured comparison | unavailable |

Paired OOMP-minus-N8 recall difference: **0.6905**, interval [0.6012, 0.7817]. OOMP-minus-flat-lexical: **0.1429**, interval [0.0973, 0.1909]. These conditional synthetic intervals do not establish general significance or independent replication.

## Supported effects and negative findings

- All executed non-vector offline methods score 1.0 recall on the eight recent-preference controls. OOMP receives no unique credit for facts already in the working window.
- Full OOMP and neighborhood-off both score the same recall. Both have **0/16 complete supported multi-hop chains** at default candidate settings. Endpoints are often found lexically; ordinary paths for independently ranked endpoints are not attached. A separate real-engine mechanics test with one seed candidate validates a genuine two-hop proof chain, without changing the experiment's default 40 candidates.
- Removing entity/topic lanes reduces mean recall from 0.9286 to 0.7857 on this generator; alias-only and topic cases explain the difference. The identical lexical control matches full OOMP offline.
- Current-state evidence correctness is 1.0 for full OOMP versus 0.0 for flat lexical on eight curated cases. Historical evidence correctness is 1.0 for both. OOMP retains and labels both competing claims in eight structured disputes. These are narrow, explicitly annotated RAM-policy fixtures, not general temporal extraction or authoritative factual verification.
- Offline lexical modes fail the long-history paraphrase template. Long-history means are N8/summary 0.25, flat lexical 0.50 and OOMP 0.75 across 32 queries. Exact/alias retrieval must not be described as semantic generalization.
- In the real embedding validation sample, flat vector, hybrid OOMP and OOMP semantic each recover all four positive cases (**1.0 recall**, one positive history, interval not estimable). All three also return nonempty evidence on **all four unanswerable cases**. The live sample shows no vector-versus-OOMP recall advantage and poor false-match control at the frozen threshold.
- Query-independent N8/summary always provide recent context, so their empty-result metrics describe policy, not whether a downstream model would correctly abstain.

## Models, timing and resources

Real embeddings used `embeddinggemma:latest`, digest `85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1`, dimension 768, float64 normalization, cosine threshold 0.2 and configuration `stage9-ollama-embed-v1` for both systems. Weight inventory size: 621875917 bytes (disk, not RAM). No model download. LLaMA answer evaluation is available by explicit CLI opt-in but **was not executed in Stage 9**; no answer-accuracy measurements are reported.

Observed held-out warm medians: N8 1.2407 ms, summary 1.1364 ms, flat lexical 0.3670 ms and OOMP 9.9438 ms. Successful first-query/warm counts are 64/96 per executed offline method. p95 is available; neither phase has 100 samples, so p99 is null. First query is not a certified cold OS/model cache. Statistical analysis writing is outside manifest execution-wall timings.

Source, extraction/canonicalization/persistence, curated writes, graph/topic work, lexical indexing/checks, summary compression and embedding/index costs are in each `corpus_costs.jsonl`. These costs must be included before amortized speed claims. Independent canonicalization, trigger FTS time, OOMP-internal packing and isolated transport overhead remain unobserved/null. Held-out whole-harness peak working set: 87,334,912 bytes; separate Ollama memory is excluded. SQLite file/page sizes and approximate vector payload sizes are recorded.

The smoke, held-out and embedding runs overlapped in execution; part of the first full test pass also overlapped on this four-logical-CPU Windows desktop. This limits latency/preparation-cost comparability across runs. Within each run all methods used the same host and deterministically rotated query order. No hardware-independent performance claim is made. A model health probe precedes timed embeddings; cold load and server-side caches are not isolated.

The TRACE context study measured client-total times of 17,632.3278 ms on first optional SDK import and about 61–66 ms on later calls. Its five-second protocol deadline excludes first SDK import/setup; these numbers do not isolate pure transport overhead. Direct early-fact N8/OOMP prompt sizes were 1,611/2,934 bytes, with a 16,000-byte shared ceiling. Matched neutral-template sizes were 1,084/2,121 bytes. OOMP intentionally supplies more historical information; the same-capacity flat lexical condition is included. All six conditions retained the recent eight.

## Integrity, errors and limitations

Deep audit revalidated **all 1,596 records**, recomputed their metrics, checked actual canonical/raw bodies, references, scopes, budgets, frozen hashes and the record rectangle. All 81 TRACE tracked files, 55 original OOMP production files, 28 earlier test files and 9 existing database files match their pre-edit hashes. Both Git HEADs are unchanged. Compilation, `pip check` and `git diff --check` passed. Git emitted an informational LF-to-CRLF notice for the modified research-plan Markdown; it is not a test failure.

Development caught and repaired summary recency truncation, the Windows memory handle signature, zero-row/interrupted analysis reporting and source-body grounding validation. One initial smoke could not finalize its resource report and is excluded as incomplete; it was not overwritten. A preliminary full pass had 492 passes and one benchmark-only guard failure after the new explicit in-memory TRACE fixture layer was added; the guard was narrowed to prohibit real MongoDB dependencies while allowing that named mock worker. The final complete acceptance pass supersedes it. No production defect/algorithm repair or hidden threshold tuning was performed.

The frozen main runs record code hash `258b46be226ed86377b37aa724f03707511ba00a029754dffe343876be4dff19`. Later changes were limited to invalid/empty/interrupted reporting guards and an independent TRACE context adapter. Their code hash differs from the final tree; the original run manifests remain intact, and every stored metric/body was independently revalidated under the final guards. Dataset/config hashes and retrieval settings were not changed after registration.

The 512/1024 scaling configuration, isolated temporal/consolidation/fusion-off ablations, full FastAPI owner/chat workflow, real paired LLaMA generations, blinded human answer review and external Mem0/Zep/GraphRAG measurements remain pending/not executed. Stage 6 summary projections are not consumed by the production retriever, so a projection-off gain is not invented. Related generator templates, curated structures, one repetition and only four held-out seeds limit generalization. No LLM judge, public deployment, release packaging, commit or push.

## Reproduction and artifacts

See [the benchmark README](../benchmarks/README.md) for all stable commands. Executed local raw folders are `benchmarks/results/stage9-offline-smoke`, `stage9-heldout`, `stage9-live-embeddings` and `stage9-trace-context`. Each retrieval folder includes frozen input JSON, manifest, per-query JSONL, preparation costs, SQLite data, aggregate JSON, CSV and Markdown. Outputs are ignored and never silently overwritten. The reviewed [machine-readable summary](examples/stage9-results.json) preserves measured summaries/hashes; raw personal data is not present.

Ignored audit evidence: `.test-artifacts/stage9/baseline.json`, `frozen-registration.json`, `integrity-audit.json`, `acceptance-tests.xml` and UTF-16 `acceptance-tests.txt`. The [42-item completion report](stage-9-report.md) records exact scope and handoff. Stage 10 remains pending manual review.
