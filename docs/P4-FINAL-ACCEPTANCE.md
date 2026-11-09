# P4 final acceptance record

Recorded 7 November 2026 (Asia/Karachi). **P4 is partially accepted, not complete:**
Gates A and C retain their accepted local experimental passes; Gate B completed
only a bounded subset and remains **INCOMPLETE**. No general model-quality,
production-readiness or public benchmark claim follows from these results.

## Preserved interoperability acceptance

| Gate | Accepted result | Evidence |
| --- | --- | --- |
| A: authenticated TRACE ↔ OOMP | PASS: 137/137 checks, 12/12 frozen scenarios, original-source recall 16/16, precision 16/18 | [Quality recovery report](product-milestone-P4-quality-recovery-report.md) |
| C: independent official-SDK host | PASS: 18/18 checks, 13 host calls; distinct scope/grant, context proofs, negative controls and owned shutdown | [Gate C recovery report](product-milestone-P4-gate-C-recovery-report.md) |
| B: real LLaMA cross-session answers | INCOMPLETE: 22 successful generations, one timeout, 41 not tested out of 64 planned | Measured results below |

Gates A/C, ingestion, projections and their accepted databases were not repeated
for the submission sprint. Gate A distinguishes raw retrieval from TRACE-accepted
evidence and final prompt selection; an HTTP success alone is not acceptance.
Gate C tests the documented legacy tenant/namespace source-read boundary and the
stronger principal-specific `memory.context` boundary separately.

Preserved Gate A result SHA-256:
`585b4d8427300572a38f215a867fa1729b2eaf418d9741f876133e373c164460`.
Preserved Gate C result SHA-256:
`982ec3a50525eee5237f5ca84c0a3f0dda3e23a75a7cd00b818b755eaa9263aa`.
The fictional baseline database remains
`206af1066b860784ff4ad3ded1295a99168292e9656ebcbbb3dd0d7cbbf7c47d`.

## Gate B: bounded measured attempt

The single-use attempt started at `2026-11-06T15:26:41.395820Z` (20:26:41 PKT).
Local evidence is retained under
`.test-artifacts/submission-20261106T151910Z/`, including the preregistration,
workload, prompts, original answers, per-request timings, resource ledger,
single-use ledger, explicit manual labels and existing scorer output.

| Setting | Actual value |
| --- | --- |
| Ollama | 0.40.15 |
| Installed model | `llama3:latest`, Llama 3 8B Q4_0 |
| Model digest | `365c0bd3c000a25d28ddbf732fe1c6add414de7275464c4e4d1c3b5fcb5d8ad1` |
| Identical generation options | `num_ctx=4096`, `num_predict=64`, `num_thread=2`, `num_gpu=0`, `temperature=0`, `seed=0` |
| Retention / deadlines | `keep_alive=90s`; preload 150 s, per generation 120 s, total 1,200 s including preload, cleanup reserve 15 s |
| Requests | One preload, 23 generation attempts, one unload; no retry/download |
| Preload / total elapsed | 48.328 s / 1,185.469 s |
| Final stop | `guarded_http_deadline_exceeded` during flat-lexical infrastructure case under remaining total budget |
| Resource observations | 2,318 samples; minimum available RAM 2,004,393,984 bytes (1.867 GiB); maximum system commit 66.2221%; maximum sample gap 0.875 s |
| Cleanup | Model unload verified; final model list empty; user-owned Ollama server/application left running |

RAM admission remained 6.75 GiB, with 1.5 GiB RAM / 85% commit stop limits and
monitor/cancellation/ownership checks. No RAM/commit stop, monitor failure or new
Windows critical event was observed during this attempt. These Windows process,
resource and polling safeguards are experimental harness functionality, not a
claim of shipped runtime protection or a resolved historical BSOD.

All arms used identical questions, policy prefix and output limit. The frozen
workload has 12 original cases plus four held-out wordings over the same source
subjects. The latest-eight arm has the one genuine active-session exchange
available in that frozen workload, not eight invented turns. Flat lexical uses
approved original texts in disposable in-memory BM25; OOMP uses exact accepted
historical context captures. This is **packet replay**, not a new live retrieval
measurement or an independent source corpus. The held-out cases were not reached.

### Answer results

Five cases completed across all four arms: project, alias, style, robot and
relocation. These paired counts must not be extrapolated to the unrun cases.

| Arm | Correct / five paired cases | Returned answers | Failed requests | Not tested / 16 | Unsupported claims among returned answers | Mean answer latency, returned answers |
| --- | --- | --- | --- | --- | --- | --- |
| No historical memory | 0/5 | 6 | 0 | 10 | 1 | 38.372 s |
| Latest-eight | 0/5 | 6 | 0 | 10 | 2 | 37.547 s |
| Flat lexical | 3/5 | 5 | 1 | 10 | 0 | 58.100 s |
| OOMP lexical packet replay | 3/5 | 5 | 0 | 11 | 0 | 68.747 s |

Flat lexical answered project, alias and robot correctly; OOMP answered project,
style and robot correctly. OOMP failed alias recall despite valid supplied NOVA
source evidence. Latency means cover the stated unequal sets of returned
answers, exclude failed/unrun calls and are not a controlled speed comparison.

The relocation question exposes a rubric distinction. Flat answered that no
move occurred and the plan was tentative; OOMP answered that no move occurred
and the plan was cancelled. Both fail the full frozen rubric, which also asks
for the tentative-to-cancelled sequence and current Cedar Bay. OOMP's direct
no-move/cancellation answer is recorded as partial temporal success, not silently
converted into a full-rubric pass. Across four returned relocation answers:
two explicitly deny a completed move, one names cancellation, none names the
current city, and none asserts a completed move. Full-rubric completions: zero.

The original pet, political, foreign-owner and premise-negative cases, and all
four held-out cases, were **NOT TESTED**. Their correct-abstention rates are
undefined; they are not 100% or zero-error results. Manual labels are explicit,
conservative provisional Codex review using the existing frozen scorer.
Independent human/blinded adjudication is pending, and no formal answer-quality
acceptance threshold was preregistered. No answer-quality superiority or
statistical significance has been demonstrated.

Prompt lengths were 2,454–10,615 UTF-8 bytes under a 32,768-byte preparation cap.
Twenty-five prompts exceeded the conservative 4,096-byte proxy; bytes are not
tokens. Actual model token accounting was captured where returned, but an
independent tokenizer/native truncation certification was unavailable. The
64-token response cap also cut some answers. These are comparison limitations.

### Reproduction identities

| Frozen input | SHA-256 |
| --- | --- |
| Original synthetic source fixture | `a60a32b9abb04fc06386ae808cfaf10def98a134d71c530b64103a269a8109ba` |
| Workload | `6ddbc0ffb093a14bccdf0ef318351dbce5c90bf9f2a60aa81f4b986d851ed631` |
| Prompt bundle | `f47a1204ae5d1226444c0125dadc4dbf91ca50c50dcba7797ddac0875bb72094` |
| Preregistration | `5c774df7c77307120bfa196490bee5680a07a09896a3324f182429eeee0c7508` |

The retained `evaluate_answers.py` scorer is unchanged. Its output and
`answers-reviewed.jsonl` preserve missing/error/not-tested rows in planned
denominators. Do not rerun the single-use live controller to regenerate this
record. Further inference needs a separately bounded, authorized attempt.

## Remaining product and research gates

The default multi-principal shared-queue scheduling defect remains **OPEN**.
Submission operates one principal per dedicated namespace/database. Legacy
`memory.get_source` remains namespace scoped; separate untrusted hosts need
separate scopes/grants. No legacy permission or scheduler behavior was changed.

P5 submission preparation does not retroactively complete P4 Gate B. Independent
pilot users, independent human review, public benchmark validation and controlled
external Mem0/Graphiti comparisons remain pending. See
[submission readiness](SUBMISSION-READINESS.md) and the
[manual guide](MANUAL-TESTING.md) for the bounded alpha submission scope.
