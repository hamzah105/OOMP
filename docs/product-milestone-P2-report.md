# Product Milestone P2: Mind 2 implementation and acceptance report

29 October 2026. This report describes an uncommitted local candidate for owner
review. P2 improves memory acquisition and episodic evidence. It does not deliver
P3's object hierarchy, P4's context virtualization or P5's publication workflow.

Improved rules substantially exceed the legacy extractor on the frozen synthetic
fixture. The labels are **Codex drafts pending independent human review**. The
actual installed local model was called, but produced no usable proposals in the
full evaluation; its quality scores therefore measure rules fallback. Successful
real-model extraction acceptance remains an outstanding gate. Final local suites
passed **682/682 tests on both Python 3.11 and 3.12**, including the fresh
installed-wheel check. Independent label review and hosted CI remain pending.

## 1. Starting Git state and baseline

The starting checkout was clean `main` at
`7528aff011cd33c7d6482eae068ead65779351ba`; the inspected upstream and live GitHub
`main` matched. Before source changes, Windows Python 3.11.4 passed all **575**
existing tests in **553.56 seconds**. The historical split was 515 pre-P1 tests
and 60 P1 tests. No commit, push, publication or deployment is part of this work.

[P1 stabilization](product-milestone-P1-stabilization.md) records the inspected
Actions failures, binary Windows SID comparison fix, resolved executable test
fixture and early project-selection wizard validation. Its gate passed 76 tests
on both Python 3.11.4 and 3.12.6 before P2 implementation began. Wheel and source
archive clean installs passed at that gate. Hosted Windows/Ubuntu CI remains
pending owner review and an authorized future push.

## 2. Actual implementation scope

The new `src/oomp/understanding/` package provides versioned proposal contracts,
clause segmentation, conservative rules, independent validation, optional
loopback Ollama generation, governed persistence, bounded episodes and local
administration. Existing Mind workers and product profiles carry its explicit
configuration. `benchmarks/mind2/` supplies a frozen synthetic corpus and an
end-to-end worker evaluation.

Supported distinctions include user-claimed aliases, preferences, prospective
plans, tentative consideration, questions, quoted material, assistant statements,
hypotheticals, focus changes and reviewable corrections. A declarative sentence
can survive a question elsewhere in the message. Exact source clauses are kept;
the engine does not verify a legal identity, infer a relocation decision or erase
history when conversational focus changes. Interpretation remains bounded and
largely rule-defined, rather than general natural-language understanding.

New test modules are `test_mind2_acquisition.py`,
`test_mind2_providers_workers.py`, `test_mind2_product_admin.py`,
`test_mind2_governance.py`, `test_mind2_evaluation.py` and
`test_mind2_example.py`. P1 adds `test_product_stabilization.py` and adjusts the
existing TRACE fixture. Integration changes are confined to OOMP's product,
Mind, projection-store and CLI surfaces; TRACE application code is outside scope.

The complete review inventory contains **17 modified tracked files and 38 new
files (55 paths)**. The local
`.test-artifacts/product-P2-20261029/review-inventory.json` also records hashes
for all 79 tested runtime Python modules and the unchanged HEAD.

Modified tracked files:

```text
README.md
src/oomp/cli.py
src/oomp/mind/cli.py
src/oomp/mind/contracts.py
src/oomp/mind/handlers.py
src/oomp/mind/worker.py
src/oomp/product/cli.py
src/oomp/product/diagnostics.py
src/oomp/product/models.py
src/oomp/product/profiles.py
src/oomp/product/safety.py
src/oomp/product/services.py
src/oomp/storage/graph_store.py
src/oomp/storage/mind_projection_store.py
src/oomp/storage/mind_store.py
src/oomp/storage/privacy_store.py
tests/test_product_trace.py
```

New files:

```text
.gitattributes
benchmarks/mind2/README.md
benchmarks/mind2/__init__.py
benchmarks/mind2/concordance.py
benchmarks/mind2/fixtures/v1/annotation-schema.json
benchmarks/mind2/fixtures/v1/manifest.json
benchmarks/mind2/fixtures/v1/sessions.json
benchmarks/mind2/results/2026-10-29/manifest.json
benchmarks/mind2/results/2026-10-29/mode-A.json
benchmarks/mind2/results/2026-10-29/mode-B.json
benchmarks/mind2/results/2026-10-29/mode-C.json
benchmarks/mind2/results/2026-10-29/rules-concordance.json
benchmarks/mind2/results/2026-10-29/run.json
benchmarks/mind2/results/2026-10-29/summary.json
benchmarks/mind2/run.py
docs/mind2-design.md
docs/product-milestone-P1-stabilization.md
docs/product-milestone-P2-report.md
examples/mind2_quickstart.py
src/oomp/understanding/__init__.py
src/oomp/understanding/admin.py
src/oomp/understanding/cli.py
src/oomp/understanding/contracts.py
src/oomp/understanding/engine.py
src/oomp/understanding/episodes.py
src/oomp/understanding/providers.py
src/oomp/understanding/quoted.py
src/oomp/understanding/rules.py
src/oomp/understanding/storage.py
src/oomp/understanding/transport.py
src/oomp/understanding/validator.py
tests/test_mind2_acquisition.py
tests/test_mind2_evaluation.py
tests/test_mind2_example.py
tests/test_mind2_governance.py
tests/test_mind2_product_admin.py
tests/test_mind2_providers_workers.py
tests/test_product_stabilization.py
```

## 3. Provider and extraction architecture

`ExtractionProvider.propose(scope, event)` returns typed untrusted proposals and
has no database or operational authority. Rules are independently usable offline.
The legacy extractor remains the default for existing profiles and manual worker
commands; newly onboarded product profiles choose improved rules unless an
operator explicitly selects the local model.

The implemented model provider is Ollama at an explicitly configured literal
loopback HTTP address, normally `http://127.0.0.1:11434`. Hostnames, external
addresses, credentials in URLs, redirects and proxies are unsupported. OOMP does
not download weights, start Ollama or call an external model API. The protocol is
the extension seam for a separately authorized future API implementation; no
external API integration is shipped in P2. Extraction and embedding configuration
are independent: a vector model is not assumed to generate memory candidates.

`mind2.v1`, `mind2.candidate.v1`, `mind2.validator.v1` and `mind2.prompt.v2`
identify the configuration, proposal, validator and prompt contracts. Default
bounds are 8,192 input characters, 16 candidates, 512 characters per clause,
1,024 output tokens and a 20-second request deadline. Configuration permits at
most 16,384 input characters, 2,048 output tokens and 60 seconds. The provider
also checks request/context/response budgets, permits one outstanding request,
opens a 30-second circuit after three failures and limits calls to 1,000 per
provider instance. Client limits do not guarantee server CPU/RAM usage or
immediate cancellation of server-side inference.

## 4. Candidate validation model

Candidates include a stable ID, trusted scope coordinates, source event/span,
speaker attribution, literal object, predicate/category, assertion kind,
importance, sensitivity, temporal marker, proposal status and provider/model
version. Validity stays uncertain and confidence calibration stays uncalibrated.
One candidate references one event and one exact clause. The object must equal
the source quote; free model paraphrases are refused.

The independent validator checks the contract and count limits, tenant,
namespace, principal, source ID, source role, exact Unicode offsets, supported
clause boundaries, content identity, provider identity, semantic classification,
privacy policy and duplicates. A small anchored allowlist permits model proposals
to recognize additional literal alias/preference/plan forms beyond rules. It does
not permit inferred profile attributes or authority based on model confidence.

Persistence re-reads the actual stored event and validates again inside the write
transaction. It rejects changed/missing/inaccessible evidence and retracted
sources, and checks the running job's owner, fencing token and lease both before
writes and before commit. Provider output cannot create credentials, change
policy, authorize an action or override source governance.

## 5. Episodic-memory architecture

Each retained clause has an attributed episodic record with source timestamp,
exact text, assertion kind and promotion decision. Durable user claims can also
have a canonical record. Low-salience discussion stays episodic; corrections
carry a review decision in their episodic metadata. Aliases remain
unauthenticated display claims. Assistant and document material remains
attributed discussion rather than user-profile truth.

Promotion is a published policy rather than a learned importance score:

| Source-grounded interpretation | Retention decision |
| --- | --- |
| Explicit/tentative user preference, alias, plan or project | Canonical claim plus episode when enabled; tentativeness remains explicit |
| Supported ordinary explicit semantic statement | Canonical claim plus episode when enabled |
| Ordinary correction/update | Episode marked for operator review |
| Question, hypothetical, quoted/assistant material or low-salience discussion | Attributed episode only |
| Sensitive material | Excluded by default; attributed episode only with opt-in |
| Detected secret, instruction attack or operator exclusion | No derived acquisition/model forwarding |

Rules assign durable importance to recognized preference templates, normal
importance to aliases/plans/projects and low importance to ordinary discussion.
Allowed model refinements preserve the conservative base importance. This is not a
scientifically validated score. Repetition learning, evidence-count ranking and
recency-weighted promotion are not implemented in P2.

Episodes group by authorized principal, source session, 30-minute interval and a
small keyword topic projection. A topic holds at most 16 clauses and about 4,000
characters; overflow is sharded. Existing topic membership and summary revision
tables produce chronological extractive summaries under
`episode-extractive.v1`, ordered by source occurrence, ingestion, event and span.
Each summary carries its source dependencies. Reads recheck live evidence and
retractions; no separate ungoverned memory store is introduced.

This is a bounded source projection. It has no inferred topic hierarchy, semantic
topic resolver, automatic decision resolution or full P3/P4 architecture.
Tentative, question and review clauses remain visibly unresolved. Explicit local
episode inspection complements existing retrieval APIs.
Keyword grouping is deliberately coarse: physical-object movement can share a
`relocation` label with a moving-house discussion. No topic-purity or general
conversation-understanding claim follows from these groupings.

## 6. Persistent schema changes

**No migration or schema increment was needed; SQLite remains v5.** P2 reuses
`memories`, `memory_sources`, `topics`, `topic_memberships`,
`mind_summary_revisions` and `mind_summary_sources`, with versioned metadata and
policy values. Supported legacy statements retain legacy canonicalization and
stable canonical IDs. New claims and event-specific episodic IDs are deterministic
and scope-bound. Source events remain immutable.

There is no automatic scan or reprocessing of existing private history. Reprocess
administration accepts only an explicit selection of 1–100 event IDs, produces a
preview digest, and requires the same digest plus an assertion of existing source
consent before atomically enqueueing work. It does not start a worker. Existing
backup, retraction and erasure governance remains applicable.

## 7. Privacy and security review

Secret-like content, detected instruction attacks and operator-excluded terms
are excluded before model inference. Sensitive-topic episodes are disabled by
default; explicit opt-in retains attributed discussion without inferred political,
ethnic, medical or criminal profile truths. Sensitive terms and injection checks
are conservative heuristics and can exclude legitimate discussion. These filters
are not a comprehensive secret detector or a proof against prompt injection.
They suppress derived acquisition and model forwarding; they do not erase raw
text already ingested into the immutable source-event log. Source retention and
operator-controlled erasure remain separate governance responsibilities.

Stored conversation data and model replies remain untrusted. Only a trusted local
`AuthorizedScope`, source authority and established write governance authorize
derived writes. Native Windows DACL checks remain fail-closed, and POSIX private
permission requirements remain unchanged by the stabilization patch. Normal
diagnostics and logs expose operational codes and counts; episode content requires
explicit `--show-content` inspection. No new public endpoint or MCP write
authority is added. SQLite remains plaintext, protected by host permissions.

Synthetic regression coverage exercises forged scope/role/span/output, model
failure, prompt injection, secrets, assistant attribution, duplicate work, lease
loss and source retraction/erasure. These are local engineering checks, not an
independent penetration test or a claim of universal security.

An internal regression review found and resolved concrete boundary defects:
later clauses inside quotations, code, reported speech or conditional context
could otherwise lose their original attribution; common medical, religious and
party terms needed conservative sensitivity defaults; and withdrawal needed to
apply across P2-derived support even when episodes were disabled or an existing
legacy canonical ID was reused. Event-level acquisition provenance now supports
central endorsement checks, historical `known_at` handling, protected graph
relationships and raw-target support. A P2 event's withdrawal applies across
its derived support without deleting the source event or withdrawing independent
support from other events. Regressions and a follow-up review rechecked these
specific fixes; this does not establish comprehensive sensitive-data detection.

## 8. Worker integration and failure handling

Configured extraction runs within existing durable `EXTRACT_EVENT` Mind jobs.
Inference occurs outside SQLite transactions and outside TRACE's chat path.
Rules execute before the optional model; unavailable, malformed or refused model
output produces bounded degradation and preserves valid deterministic work.
Accepted clauses, provenance, topic membership and summary revisions commit
atomically. Existing job retries, leases, fencing and follow-up indexing remain
in use. Configuration identity is pinned for explicitly reprocessed jobs.

Replay uses stable source/candidate/memory IDs. The evaluation observed zero new
candidate records from replay and zero exact-content duplicate canonical memories
in all modes. No failed extraction jobs were observed in the measured evaluation;
mode C recorded 224 degraded extraction jobs. Degraded completion does not mean
model capability was verified.

## 9. CLI, configuration and disposable verification

Product onboarding/configuration supports `--extraction-mode legacy|rules|local-llm`,
`--extraction-model`, `--extraction-endpoint`, `--extraction-timeout`,
`--retain-episodes`/`--no-retain-episodes`, sensitive-episode opt-in and explicit
`--exclude-memory-term` exclusions. Existing profiles retain their profile
identity and legacy mode until changed by the operator.

`oomp doctor --full` separates rules/validator readiness, local configuration,
reachability and a synthetic extraction capability probe, queue counts and
episodic availability. Reachability is not successful generation; warnings for an
optional provider do not invalidate the offline extractor. `oomp understand`
adds scoped `episodes`, `inspect` and preview/digest-bound `reprocess` commands.
Plain, JSON, non-TTY and `NO_COLOR` paths remain available.

P2 corrections are inspectable evidence marked for review; they do not create a
general semantic correction-approval queue. Existing `mind reviews` retains its
narrow supported conflict policy. Operators can append actual correction events
and explicitly withdraw evidence with `mind retract --memory-id ... --event-id
... --confirm`, using the trusted local scope. See [background governance](background-mind.md)
for review/retraction commands and the separate digest-confirmed erasure workflow.

From a reviewed source checkout with dependencies installed, use new disposable
paths. These examples never select the owner's ordinary profile or old database:

```powershell
$runTag = [guid]::NewGuid().ToString('N')
$trialDirectory = Join-Path $env:TEMP "oomp-p2-$runTag"
.\.venv\Scripts\python.exe examples/product_quickstart.py --directory $trialDirectory
$memoryDirectory = Join-Path $env:TEMP "oomp-mind2-demo-$runTag"
.\.venv\Scripts\python.exe examples/mind2_quickstart.py --directory $memoryDirectory
.\.venv\Scripts\python.exe -m pytest tests/test_product_stabilization.py tests/test_mind2_acquisition.py tests/test_mind2_providers_workers.py tests/test_mind2_product_admin.py tests/test_mind2_governance.py tests/test_mind2_evaluation.py tests/test_mind2_example.py
$rulesResults = Join-Path $env:TEMP "oomp-mind2-rules-$runTag"
.\.venv\Scripts\python.exe -m benchmarks.mind2.run --modes A B --output $rulesResults
```

To inspect the new setup options without creating a profile:

```powershell
.\.venv\Scripts\oomp.exe onboard --help
.\.venv\Scripts\oomp.exe config --help
.\.venv\Scripts\oomp.exe understand episodes --help
.\.venv\Scripts\oomp.exe understand reprocess --help
```

With an already-installed generation model and a running local Ollama selected
by the operator, a separate synthetic evaluation is explicit:

```powershell
$modelResults = Join-Path $env:TEMP ("oomp-mind2-model-" + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m benchmarks.mind2.run --modes C --local-model llama3:latest --endpoint http://127.0.0.1:11434 --output $modelResults
```

No command above downloads a model. The benchmark refuses an existing output
directory. The quickstart exercises P1 lifecycle; the benchmark uses the actual
Mind worker to exercise P2 acquisition.

The [offline Mind 2 quickstart](../examples/mind2_quickstart.py) needs no services,
network, TRACE or model. Its observed acceptance used 12 fictional source events,
created 13 memories and four episode summaries, excluded three events from
derived acquisition and made zero model calls. It checks immutable provenance,
mixed alias/question handling, tentative chronological discussion, reviewable
updates, assistant attribution, low-salience context, replay, retrieval and source
withdrawal. Existing output directories are refused. Without `--directory`, it
uses and removes temporary storage automatically.

## 10. Synthetic dataset and annotation status

`mind2.corpus.v1` contains **30 multi-turn sessions, 240 input turns and 247
annotated opportunities**: 224 positive opportunities and 23 negative controls.
The fixture covers ordinary preferences, alias claims, projects, relocation,
changing plans, informal wording, questions, low-salience events, hypothetical and
sensitive discussion, assistant/quoted authority, missing information, attacks,
synthetic secrets, replay, foreign scope and retracted evidence.

All labels are **Codex drafts, pending independent human/owner review**. They are
not independently annotated ground truth. Fixture SHA-256 values are frozen:

| Fixture | SHA-256 |
| --- | --- |
| `sessions.json` | `c8ec3dccca6f5d4667401bcb20d661e3881bd11dec6fe25c10dc50ff71e1a257` |
| `annotation-schema.json` | `1f0240ff780913eb3e0868697f766831bddd83fed9fb5c073e18c31911172ea1` |

The runner verifies manifest hashes. It uses identical inputs and scoring in all
modes. Exact event/span/role/assertion/category/predicate/retention must match; a
wrong typed interpretation counts as both FP and FN. Excluded and unanswerable
opportunities stay in the denominator. Replays reuse event IDs. The run records
240 scored input rows and 239 extraction jobs, including explicit replay/retraction
work and foreign-scope controls. Episode coverage requires the
exact live source span in an episodic record, independently of typed matching.

## 11. Actual precision, recall and provenance results

The [preserved evaluation](../benchmarks/mind2/results/2026-10-29/summary.json)
uses the frozen draft labels. Percentages below are rounded; raw JSON retains
counts, per-opportunity predictions and failures.

| Metric | A: legacy rules | B: improved rules | C: local model configured, rules fallback |
| --- | ---: | ---: | ---: |
| TP / FP / FN | 30 / 4 / 194 | 212 / 8 / 12 | 212 / 8 / 12 |
| Candidate precision | 88.24% | 96.36% | 96.36% |
| Candidate recall | 13.39% | 94.64% | 94.64% |
| Candidate F1 | 23.26% | 95.50% | 95.50% |
| Useful episode coverage | 0 / 224 | 220 / 224 (98.21%) | 220 / 224 (98.21%) |
| Accepted provenance and source-span validity | 34 / 34 | 220 / 220 | 220 / 220 |
| Incorrect user-profile attribution | 0 | 0 | 0 |
| False-positive canonical promotion | 4 | 0 | 0 |
| Sensitive inference violations | 2 | 0 | 0 |
| Corrections handled | 0 / 20 | 19 / 20 | 19 / 20 |
| Unauthorized cross-scope writes | 0 | 0 | 0 |
| Exact-content duplicate canonical memories | 0 / 31 | 0 / 57 | 0 / 57 |

B meets the initial 95% precision, 85% recall, 100% accepted provenance and zero
unauthorized-write/assistant-profile-promotion targets on this draft fixture.
A misses precision and recall. C meets aggregate quality targets through B's
fallback; it does **not** establish successful model extraction. Exact source
grounding establishes provenance, not the truth of a conversational assertion.

The timed full comparison preceded the final security hardening. A preserved
[rules concordance check](../benchmarks/mind2/results/2026-10-29/rules-concordance.json)
then compared the current pure rules/validator output against recorded B for all
240 input rows and 247 opportunities, applying the fixture's scope/retraction
controls. It found **zero mismatches**. This supports unchanged rules predictions
on this corpus; it is not a new worker persistence, timing or model-inference
experiment. Additional security cases absent from the frozen corpus have focused
regression coverage rather than silently amended labels.

## 12. Rules-only versus actual local-model comparison

Mode C contacted the already-installed **`llama3:latest`, Llama 3 8B, Q4_0** via
**Ollama 0.40.11**. Model digest:
`365c0bd3c000a25d28ddbf732fe1c6add414de7275464c4e4d1c3b5fcb5d8ad1`.
The route was literal loopback and all input was synthetic. No model was
downloaded and no paid API was invoked.

The full run made **25 actual generation requests**, yielded **zero model
proposals, zero accepted model candidates and zero model refinements**, and
recorded **224 degraded jobs out of 239 extraction jobs**. Request timeouts and
the failure circuit prevented useful generation. The benchmark's observation
`code` was a provider's last code and could persist on later skipped events; it
must not be interpreted as a count of fresh timed-out network requests. The
runner now records the current event's acquisition result, with a regression for
stale provider status. Original measured JSON is preserved unchanged.

Controlled provider tests validate structured responses and narrow additional
literal interpretations, but are not real-model acceptance. The measured model
added latency and no demonstrated quality gain. A successful isolated capability
probe and a fresh full model evaluation are required before claiming real-model
memory extraction success or superiority over improved rules.

A separate follow-up used the actual Mind worker, the synthetic user event
`I prefer tea.`, a 60-second deadline and only 128 output tokens. Its single
generation request also timed out. Worker elapsed time was **60.89 seconds**;
the job completed through rules with one candidate, two source-backed memories
and one episode revision, zero model proposals and no failed/retried/lost-lease
job. This is further measured model-capability failure with successful fallback,
not a model success. The ignored
`.test-artifacts/product-P2-20261029/model-capability-60/result.json` records the
exact probe configuration, source-code hashes at startup and synthetic metadata.
This follow-up does not replace or alter the preserved full-run results.

## 13. Test results and environment details

All executed environments were local **Windows**, with CPython **3.11.4** and
**3.12.6**, using pytest **9.1.1** and **9.2.0** respectively for the final suites.
The evaluation used Python 3.11.4, SQLite **3.42.0**, and four logical CPUs.
No local Linux runtime or successful hosted matrix is claimed. The final
collection contains **575 existing tests, 16 P1 stabilization regressions and
91 P2 tests: 682 total**.

| Check | Actual result |
| --- | --- |
| Unmodified full baseline, Python 3.11.4 | 575 passed, 553.56 s |
| P1 gate, Python 3.11.4 | 76 passed, 105.40 s |
| P1 gate, Python 3.12.6 | 76 passed, 100.83 s |
| P1 wheel/sdist build, metadata and separate clean installs | Passed, including `twine check` and `pip check` |
| P2 refinement subset | 67 passed |
| Final focused P2/security subset | 89 passed, 24.14 s |
| Current benchmark/evaluation regressions | 4 passed |
| Existing privacy, maintenance and diagnostic regressions | 55 passed, 60.26 s |
| Offline Mind 2 quickstart acceptance/refusal regression | 1 passed, 20.56 s |
| Full Python 3.11.4 suite, first P2 run | 653 passed, 1,312.05 s |
| Full Python 3.12.6 suite, first P2 run | 647 passed, 6 lifecycle failures, 1,284.39 s; stale installed-package version mismatch, superseded below |
| Final full Python 3.11.4 suite | **682 passed, 815.04 s; exit 0** |
| Final full Python 3.12.6 suite, fresh installed wheel | **682 passed, 780.38 s; exit 0; no failures/errors/skips** |
| Final runtime wheel/sdist build, metadata/archive audit and separate clean core installs | Passed; build, `twine check`, archive audit and both clean-install checks exited 0 |
| Fresh Python 3.12 extras/dependency/bytecode checks | Passed; installation, `pip check` and `compileall` exited 0 |
| Installed Python 3.12 wheel/runtime equivalence | All 79 runtime Python modules byte-identical to the tested source; no changed paths |
| Follow-up real-model worker probe, 60-second deadline / 128 output tokens | Generation timed out; one job completed by rules fallback in 60.89 s |
| Remote Windows/Ubuntu Python 3.11/3.12 Actions matrix | Pending; no push authorized |

The first 3.12 run reused an environment with an older installed P1 package.
Its six lifecycle failures are retained as an environment-version mismatch,
superseded by the fresh wheel installation with `PYTHONPATH` cleared and all 682
tests passing. An isolated in-memory probe confirmed the cause: the older
installed `Profile` had no `extraction` field and rejected `extraction: null`
with `extra_forbidden`; the fresh P2 wheel accepted the identical payload. The
probe created no database and is recorded in
`python312-environment-probe.json` under the local evidence directory.
The final full suites include the existing lifecycle, permission,
credential isolation, schema/migration, temporal governance, retry/lease,
privacy/erasure and CLI regressions. They establish local Windows compatibility;
they do not establish a successful remote Ubuntu run.

Tests use disposable synthetic databases and credentials. Final logs/JUnit XML
are `full-311-final.txt/.xml` and `full-312-final.txt/.xml`; fresh installed-wheel
completion records source-hash equivalence. Build/install and operational
artifacts are held under the ignored `.test-artifacts/product-P2-20261029/`
directory. Only privacy-safe synthetic evaluation JSON is included in the
repository. Archive/install validation covers the final tested runtime code;
subsequent documentation-only review snapshots retain that runtime hash boundary.

## 14. CPU, RAM, latency and cost measurements

These are single-run observations, not isolated performance benchmarks. Other
validation work ran concurrently, so elapsed time includes contention. Wall time
includes real worker extraction and ordinary follow-up jobs. Per-extraction
latency excludes unrelated jobs. RSS is sampled from the Python client only;
Ollama CPU/RAM/GPU, whole-machine energy and monetary cost were not measured.

| Measurement | A | B | C |
| --- | ---: | ---: | ---: |
| Full run wall seconds | 534.82 | 740.04 | 1,011.48 |
| Extraction p50 seconds | 0.0056 | 0.7130 | 0.6036 |
| Extraction p95 seconds | 1.3082 | 1.9003 | 21.3655 |
| Python client CPU seconds | 20.56 | 71.13 | 68.94 |
| Python client sampled peak RSS, MiB | 37.49 | 38.49 | 40.15 |
| Actual model invocations | 0 | 0 | 25 |
| Paid external API invocations | 0 | 0 | 0 |

The configured model is approximately 4.66 GB on disk; this is not its measured
resident memory. Failed inference can continue consuming provider resources after
the client deadline. Zero paid calls is not a zero-cost CPU/energy claim.

## 15. Known limitations and target failures

B/C still have 12 missed or mistyped opportunities and eight false candidate
interpretations. Misses include natural procedural preferences (`Please use
numbered steps`, `I'd rather get a checklist`, `Remember that I like ...`),
sensitive/hypothetical/update precedence and legitimate authority discussion
excluded by broad attack detection. Quote detection can mistake an ordinary
question containing `according to` for quoted material. One correction remains
unhandled under the exact typed labels. Candidate false positives are distinct
from false canonical promotion: the latter was zero in B/C.

Model-added interpretation is deliberately constrained by independent literal
checks. This limits linguistic coverage even with a stronger model. The real
model did not produce usable proposals in the full run, so the desired model
capability remains unverified. Rules handle only bounded English forms and a few
documented typo variants. Keyword topic windows cannot fully resolve references,
topic continuations, temporal dates or conversation conclusions. Corrections
require review and do not automatically supersede or delete prior claims.
The provider's stricter context budget can refuse input that fits the general
event character limit; increasing that limit does not guarantee model coverage.

The corpus is small, synthetic and partly roadmap-seeded; draft-label scores may
reflect author choices and cannot establish performance on genuine conversations.
No confidence calibration, independent human benchmark, production TRACE memory
sync, multi-model comparison or general benchmark superiority is claimed.

## 16. Preservation audit

The implementation retains schema v5, existing canonical access, source-event
authority, established authenticated MCP ingestion, governed approvals and
asynchronous durable jobs. Historical roadmap/stage reports and frozen Stage 9
artifacts are outside the edit set. No TRACE application source, real MongoDB
records, ordinary private OOMP databases or existing credentials were selected
for writes. No automatic private-history processing, credential rotation, public
listening endpoint, foundation-model training, model download, commit or push was
performed.

The captured SHA-256 preservation audit reports **81 TRACE tracked files, nine
existing data files, 372 frozen Stage 9 result files and 57 historical
documentation/workflow/package-contract files unchanged**. TRACE's working tree
was clean and its starting HEAD `af202ef43daf70280d2e8915210816f788e8aff1`
was preserved. OOMP HEAD still matched the starting commit. The audit hashed
inventoried files and did not open private databases with SQLite. Its local
evidence is `.test-artifacts/product-P2-20261029/preservation-audit.json`.
Final full-suite lifecycle and fresh installed-wheel acceptance passed as
recorded in section 13, including all 79 runtime module hashes matching.
The starting snapshot and audit are private local artifacts; database copies are
not published with the synthetic result JSON.

## 17. P3 prerequisites and deferred architecture

Before any later milestone, review the draft labels, resolve real-model
generation/capability failures, inspect the passing local compatibility,
clean-install and preservation evidence, and run the authorized hosted CI matrix.
Use the existing source-linked episode and proposal contracts as inputs to later
design rather than treating model output as verified knowledge.

P3's hierarchical object map, cross-episode reference resolution and richer
relationships need their own design/review. P4 retrieval policy, context
virtualization, TRACE prompt allocation and a full retrieval redesign are
deferred. P5 release/publication remains owner-controlled. P2 introduces no
autonomous erasure or identity rewrite. Work stops for owner review of this
candidate; those future milestones are not implemented here.
