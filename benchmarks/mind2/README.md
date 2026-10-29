# Mind 2 acquisition evaluation

This benchmark compares legacy deterministic extraction (A), improved clause
rules (B), and improved rules plus explicitly configured local Ollama extraction
(C). It runs source events through OOMP's actual durable Mind worker and scores
the resulting live source-backed records. It measures acquisition and episode
coverage, not answer quality or P4 retrieval/context virtualization.

## Frozen inputs and scoring

[`fixtures/v1/manifest.json`](fixtures/v1/manifest.json) freezes
`mind2.corpus.v1`: 30 synthetic multi-turn sessions, 240 input turns and 247
annotated opportunities, including 224 positives and 23 negative controls.
**All labels are Codex drafts pending independent human/owner review. They are
not independently verified ground truth.** No genuine TRACE history is included.

The manifest verifies SHA-256 of the corpus and annotation schema. Any reviewed
label changes require a new version; do not overwrite this frozen fixture or
report improved results as the same benchmark.

Matching requires exact event/span/role/assertion/category/predicate/retention.
A wrong typed interpretation counts as both FP and FN. Negative, excluded,
foreign-scope, replayed and retracted opportunities remain in every mode. Replay
uses the same event ID. The measured run records 240 scored input rows and 239
extraction jobs, including replay/retraction work and foreign-scope controls.
Episode coverage requires the exact live quote/span in an episodic record;
candidate classification can be wrong while that episode is still covered.
Provenance validity checks exact evidence, not truth of the user statement.
The duplicate metric counts exact-content duplicate canonical records and also
reports records newly created by replay; it is not semantic deduplication.

## Reproduce on disposable storage

Use the reviewed source checkout or source archive, with OOMP installed into the
selected Python environment. Every output directory must be new. The runner
creates synthetic SQLite databases only within that output directory and never
scans profiles, TRACE or private databases.

```powershell
$trialOutput = Join-Path $env:TEMP ("oomp-mind2-" + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m benchmarks.mind2.run --modes A B --output $trialOutput
```

Mode C requires an already-installed generation model and a local Ollama service
chosen by the operator. No model is selected or downloaded automatically:

```powershell
$modelOutput = Join-Path $env:TEMP ("oomp-mind2-local-" + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m benchmarks.mind2.run --modes A B C --local-model llama3:latest --endpoint http://127.0.0.1:11434 --timeout 20 --output $modelOutput
```

Only literal-loopback HTTP endpoints are accepted. C sends the synthetic input
to that local provider. Extraction models are separate from embedding models.
The output includes `run.json` (environment, fixture/prompt hashes and selected
model metadata), `summary.json`, per-mode JSON (predictions, misses and worker
observations) and disposable per-mode databases. Publish only inspected synthetic
JSON; databases, logs and normal profiles are not required for score review.

For a smaller offline acceptance demonstration with exact source proofs, replay
and retraction checks, run the [Mind 2 quickstart](../../examples/mind2_quickstart.py):

```powershell
.\.venv\Scripts\python.exe examples/mind2_quickstart.py
```

It removes its temporary storage after completion. An explicit `--directory`
keeps the synthetic acceptance files and must name a new path. The verified run
used 12 source events, 13 memories, four summaries, three excluded events and
zero model calls.

## Measured run: 29 October 2026

[`results/2026-10-29/`](results/2026-10-29/) preserves the actual JSON from local
Windows Python 3.11.4 / SQLite 3.42.0. All 247 opportunities were scored in each
mode. The run used four logical CPUs and Ollama 0.40.11's already-installed
`llama3:latest` (Llama 3 8B, Q4_0). Model and prompt digests are in `run.json`.
The timed comparison preceded final security hardening. The additional
[`rules-concordance.json`](results/2026-10-29/rules-concordance.json) compares
current pure rules/validator predictions against recorded B for all 240 input
rows and 247 opportunities, with zero mismatches. It establishes policy output
concordance on this fixture, not fresh persistence, timing or inference results.
The five original evaluation JSON files remain byte-for-byte unchanged; the
result manifest adds the concordance artifact's hash.

| Metric | A: legacy | B: improved rules | C: local model configured |
| --- | ---: | ---: | ---: |
| TP / FP / FN | 30 / 4 / 194 | 212 / 8 / 12 | 212 / 8 / 12 |
| Candidate precision | 88.24% | 96.36% | 96.36% |
| Candidate recall | 13.39% | 94.64% | 94.64% |
| Candidate F1 | 23.26% | 95.50% | 95.50% |
| Useful episode coverage | 0 / 224 | 220 / 224 | 220 / 224 |
| Accepted provenance/span validity | 34 / 34 | 220 / 220 | 220 / 220 |
| False canonical promotions / sensitive violations | 4 / 2 | 0 / 0 | 0 / 0 |
| Correction success | 0 / 20 | 19 / 20 | 19 / 20 |
| Unauthorized writes / assistant profile promotions | 0 / 0 | 0 / 0 | 0 / 0 |
| Actual model invocations | 0 | 0 | 25 |
| Model proposals / accepted / refinements | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| Degraded extraction jobs | 0 / 239 | 0 / 239 | 224 / 239 |
| Extraction p50 / p95, seconds | 0.0056 / 1.3082 | 0.7130 / 1.9003 | 0.6036 / 21.3655 |
| Full wall seconds | 534.82 | 740.04 | 1,011.48 |

**C's quality is rules fallback, not successful real-model extraction.** Actual
generation requests timed out and the circuit degraded later jobs; the local
model added no accepted proposals or measured quality improvement. Provider
observation codes may retain the last request's code across skipped events;
count actual calls and job degradation separately. Controlled provider fixtures
must not be described as real-model successes.
The current runner records each event's result rather than stale provider status;
the preserved measured JSON intentionally retains the original observations.

A separate one-event worker probe (`I prefer tea.`) with a 60-second deadline
and 128 output tokens also timed out (60.89 seconds worker elapsed). It completed
through rules with no model proposals. That ignored local probe is additional
failure evidence; it does not alter the preserved full-run JSON or its scores.

B passes the initial precision/recall/provenance targets on draft labels; A
misses precision and recall. B/C retain 12 misses/mistyped opportunities, eight
false candidate interpretations and one missed correction. Miss categories
include natural procedural preference wording, sensitive/hypothetical precedence
and legitimate discussion blocked by conservative attack detection. This is not
an independent or general conversational benchmark result.

Timing is observational: concurrent validation work confounds comparisons. CPU
seconds (A/B/C: 20.56/71.13/68.94) and sampled peak RSS (37.49/38.49/40.15 MiB)
measure only the Python client. Ollama CPU/RAM/GPU and energy were not measured.
No paid API was invoked; monetary cost was not measured. See the
[P2 report](../../docs/product-milestone-P2-report.md) for architecture, regression
evidence, known limitations and remaining owner-review gates.

Final local Windows regression validation passed 682 tests on both Python 3.11.4
and a fresh Python 3.12.6 installed wheel; distribution and clean-install checks
also passed. Hosted CI and independent label review remain pending. Episode
topics are coarse keyword/time projections: object movement can share a
relocation label. Coverage does not measure topic purity or general conversation
understanding.
