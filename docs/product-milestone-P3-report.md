# P3 object-memory map: local implementation review

Development branch: `feature/p3-object-memory-map`. Parent:
`29ceb96c85055e624783df27123d93e91b187148`. Local acceptance preceded owner
publication approval. On 31 October the owner authorized documentation correction,
one reviewed P3 commit, a dedicated-branch push and a stacked draft PR. No merge,
release, TRACE change or P4/P5 implementation is authorized.

**P3 ready for owner review.** On 31 October
(Asia/Karachi), the owner confirmed that the recorded shutdown/restart was
manual and authorized continued work. The Kernel-Power 41 / EventLog 6008
evidence is retained; it is not classified as a confirmed spontaneous crash or
BSOD. A fresh read-only preflight found the same boot, no new critical/error
records since the stop check, zero loaded models and 6,506,414,080 available RAM
bytes. The completed validation and packaging results are recorded below.

## Predecessor gate and architecture

Before branching or editing runtime code, the GitHub integration verified the
exact accepted SHA locally/remotely and its successful
[Actions run 41034632588](https://github.com/hamzah105/OOMP/actions/runs/41034632588).
Windows 3.11/3.12, Ubuntu 3.11/3.12 and build/clean-install jobs all passed.
PR #1 was open, draft and unmerged, with no review comments. No PR or remote
state was changed. The initial tracked worktree and index were clean.

The inventory and pre-code design are in [object-memory-architecture.md](object-memory-architecture.md).
P3 adds six normalized schema-v6 tables and eight indexes rather than replacing
events, memories, graph edges, episodes, summaries or worker infrastructure.
Historical migration SQL 1–5 is hash-preserved. Source-backed proofs use foreign
keys to existing exact memory-source pairs. IDs include tenant, namespace and
trusted principal plus immutable anchors; labels can change without new IDs.
Membership is a bounded DAG, with several paths to one object and one set of
canonical evidence. Association is never truth or authentication.

Controlled relations reuse ABOUT, RELATED_TO and DERIVED_FROM. Existing approved
graph edges may be referenced with their original type/evidence/validity.
Candidate/origin/criterion links require exact supported roles and actual P2
episode context. Work context also requires an explicit unique project name.
Correction review stays pending; no automatic protected supersession is added.

The object layer reuses P2 episodes and actual summary revisions/source
manifests, preserving session chronology and derived-summary attribution.
Occurrence, recording, source knowledge and supported validity remain separate.
Historical reads do not invent a projection before it was recorded. Retraction
revalidates support on reads; unsupported labels, memberships and relations
disappear without waiting for replay. Confirmed erasure cascades proof labels
through existing source-link foreign keys. Opaque unsupported anchors may remain.

## Source inventory and scope

- `src/oomp/objects/`: contracts, source-pattern policy, proof storage, bounded
  queries/history/explanation/export, independently validated relations, explicit
  projection service and CLI.
- `src/oomp/storage/object_migrations.py`: additive v6; `migrations.py`,
  `sqlite.py` and the privacy schema-verifier dispatch recognize it.
- `src/oomp/cli.py`: delegates new object commands; existing argument contracts
  remain. `MANIFEST.in` includes only the public synthetic fixture assets.
- Existing examples, install check and tests that mean current schema use
  `SCHEMA_VERSION`; genuine historical fixtures retain historical versions.
- `tests/test_object*.py`: migration, source/security, DAG, lifecycle, views,
  graph compatibility, privacy and fencing cases.
- `examples/object_memory_quickstart.py`, frozen JSON/README fixture;
  [CLI guide](object-memory-cli.md) and architecture/report documents.

No new dependencies, provider, prompt, rules fallback, credential handling,
MCP grants/listeners or default background job type is added. Projection is
explicit; actual fixture extraction runs through existing rules-only Mind jobs.
Optional projection job context is checked against the real event target and
Mind lease/fence before and after the same write transaction.

## Fictional relocation acceptance

Fixture SHA-256:
`72423795715b94d5d0098920303855c4c6b4c925490e77f29a60073d3d671b2a`.
Twelve wholly fictional turns cover a claimed city, tentative relocation,
Lahore/Islamabad candidates, explicit Infrastructure criterion for project Cedar,
question, assistant claim, hypothetical, quotation, sensitive topic, later
intention correction and explicit Cedar→Aspen rename.

The tested paths resolve the same plan ID:

1. Owner → Plans → Relocation → Potential relocation.
2. Owner → Places → Locations → Islamabad → Related plans → the same plan.
3. Owner → Episodes → Discussions → City comparison → Referenced objects → the same plan.

The later `not to move this year` intention is independently evidenced, marked
`correction_pending`, and retains the earlier tentative proof and historical
view. Cedar→Aspen preserves project identity and Cedar as a sourced alias.
No completed move is invented. Assistant, hypothetical, quoted, question and
sensitive turns create no typed user attribute. Canonical memory/source counts
and original events remain unchanged by projection. Rebuild/reopen and repeated
ingestion preserve identity and proof counts. Ambiguous same-label aliases and
identical names across tenants stay separate.

The quickstart verifies these assertions with actual Mind jobs and disposable
SQLite files. [Safe PowerShell commands](object-memory-cli.md) use a fresh short
output path; no Ollama, TRACE, MongoDB or external AI is required.

## Offline validation ledger

Machine-local evidence is under `.test-artifacts/product-P3-20261030/`, with
JUnit, stdout/stderr, source snapshot, runtime hashes, resource samples and
Windows health records. Previous recovery/acceptance artifacts are preserved.

| Phase | Verified result |
| --- | --- |
| Pre-change P2/Mind/temporal/privacy baseline | 140 passed |
| P3 focused map/views | 45 passed |
| Final migration/privacy/graph/reference checks | 21 passed |
| 1,000-event controlled evaluation | Passed; 1,000 events, 989 distinct project IDs, stable replay/reopen |
| Original full Windows Python 3.11 regression | **697 passed, 61 failed**, 758 total; 825.10 s pytest / 826.953 s controller; preserved |
| Resumed compatibility smoke | 12 passed; 22.780 s pytest |
| Resumed related storage/MCP/lifecycle regression | 176 passed; 303.475 s pytest / 306.047 s controller |
| Final full Windows Python 3.11 regression | **767 passed**, zero failures/errors/skips; 852.116 s JUnit / 854.312 s controller |
| Full Windows Python 3.12 regression | **767 passed**, zero failures/errors/skips; 865.263 s JUnit / 868.172 s controller |
| Final archive and four clean installations | Four passed; 56 CLI checks; wheel/sdist content, dependency and source-equivalence audits passed |

Focused counts overlap; they are not summed as unique new tests. No interrupted
or failing run counts as passed. All runs are sequential, synthetic, guarded
against real model/network access, with isolated startup hooks only in task QA
environments. The original developer startup environment remains unmodified.

Development failures are preserved: a shared-entity erasure fixture correctly
encountered `unsupported_shared_proof`; the positive test was changed to a
supported shared plan and a refusal test added. View tests initially confused
the basis value `source_span` with an exposed source-span field; assertions now
inspect actual keys. Example serialization was corrected from Pydantic to the
existing worker dataclass. Lease/graph test setup was corrected to enqueue its
job and choose the actual second event's memory. Invalid job contracts now emit
a constant object-context error. Graph erasure testing confirmed the baseline
`graph_dependency` refusal; no privilege or assertion was weakened. An
unnecessary experimental graph-delete cascade was removed before final checks.

| Preserved failed development run | Passed / failed | Cause and follow-up |
| --- | --- | --- |
| `focus-privacy` | 34 / 1 | Shared entity-linked source refused by existing privacy guard; supported positive fixture plus refusal regression passed in `focus-privacy-r2` (36/0) |
| `focus-views` | 41 / 4 | Two field-vs-value assertions, absent enqueued job, worker dataclass serialization; corrected before the 45/0 focused run |
| `focus-view-fixes` | 3 / 1 | Malformed job rejected by contract before the expected object error; normalized constant context error and independently tested wrong target/fence |
| `focus-graph-final` | 16 / 3 | Fixture selected first memory twice, and append result was incorrectly treated as a duplicate-result object |
| `focus-graph-fixed` | 18 / 1 | Test expected graph-linked erasure to be allowed; baseline policy correctly returned `graph_dependency` |

The final `focus-compat-final` run passed all 21 cases after preserving those
policy refusals and fixing only the fixtures and independent reference checks.
No failed attempt was overwritten or presented as final proof. `focus-views`
was also followed by a fixed-source run; it is not used as final snapshot proof.

### Full-suite compatibility failure and recovery boundary

The first full Python 3.11 run completed at `2026-10-30T12:00:43.114652Z`.
Its complete stdout, JUnit and resource records remain in `full311/`.
It recorded zero offline-guard violation and no resource/Windows monitor abort;
minimum available RAM was 6,545,752,064 bytes and maximum commit ratio 37.3095%.

Verified failures:

- `tests/test_stage2_storage.py::test_fresh_initialization_version_wal_and_repeated_init_preserve_rows`:
  the exact schema-name whitelist lacks the fourteen additive P3 table/index
  names. Actual schema version is correctly 6. Extend the whitelist explicitly;
  do not remove or loosen it to accept arbitrary objects.
- MCP and dependent product lifecycle tests: `MemoryService.__init__` at
  `src/oomp/mcp/service.py:31` still requires schema 5, rejecting every ready v6
  database with `BoundaryError("storage_unavailable")`. This is a missing
  compatibility change, not a Windows path-length failure. Seven lifecycle
  cases and the MCP client cases consequently fail.
- Review also identified v5-only/default status in `mcp/contracts.py`, and stale
  v5 reports in `mcp/cli.py` and `product/diagnostics.py`. These were unresolved
  when the original run stopped; the resumed correction is described below.

At the original stop, the smallest pending correction was to use the supported schema version for
MCP admission, report the actual version consistently while retaining deliberate
legacy-v5 response compatibility, and extend the exact inventory whitelist.
Then rerun those focused storage/MCP/lifecycle cases before a fresh sequential
full 3.11 run, source-matched 3.12 run and packaging. Authorization, typed input,
ingest approval, future-schema rejection, source validation and fencing must
remain enforced. Do not reuse prior result directories or source snapshots.

The session initially paused when automatic approval review could not run a
read command because of an account usage limit. On continuation, no Python
test/model-runner process remained. The health check then found a new boot at
`2026-10-31T00:19:59.5005240+05:00` and new Kernel-Power 41 / EventLog 6008
records around 00:20 local time, more than seven hours after the suite finished.
Service Control Manager 7000 and TPM-WMI 1801 errors were also present. No cause
is inferred from their IDs. The machine had 5,367,021,568 available RAM bytes
at the resumed check. Stop evidence is preserved separately as
`resume-stop-20261030T193357Z.json`; previous logs, ledgers and snapshots remain.
The later owner clarification identifies this restart as manual. It removes
that historical stop as a blocker; any separate unexplained instability still
requires an immediate stop. The original stop evidence and 697/61 result remain
unchanged. New validation uses a separate timestamped directory and fresh paths.

### Resumed schema compatibility changes

New evidence directory: `.test-artifacts/product-P3-resume-20261030T194119Z/`.
It records the owner's manual-restart confirmation, the fresh health/resource
preflight and hashes of 303 prior P3 artifact files. Nothing in the earlier
result directory is reused or overwritten. Guard hooks are isolated in fresh
task environments; the developer environment is unchanged.

The exact resumed source/test changes are:

| File | Correction |
| --- | --- |
| `src/oomp/mcp/service.py` | Admission requires ready storage at `SCHEMA_VERSION`; status explicitly reports that version |
| `src/oomp/mcp/contracts.py` | Status response enum explicitly accepts legacy 5 and current 6, defaults to 6; other versions remain invalid |
| `src/oomp/mcp/cli.py` | Successful readiness output reports current supported version |
| `src/oomp/product/diagnostics.py` | Synthetic diagnostic reports its actual initialization result |
| `tests/test_stage2_storage.py` | Exact whitelist explicitly adds all fourteen P3 table/index names |
| `tests/test_product_diagnostics.py` | Actual source-backed diagnostic must report current schema |
| `tests/test_object_mcp_compatibility.py` | Nine cases cover current service/CLI status, legacy wire parsing, unknown versions and no implicit database adoption/migration |

Wire shape, grants, capabilities and ingestion-approval requirements are
unchanged. Accepting a v5 response does not admit a v5 database: explicit upgrade
is still required. Old clients restricted to v5 responses need the current
package to consume v6 status. Future database versions remain rejected without
migration. This response-enum extension is documented in the architecture guide.

The initial 12-case run passed the formerly failing exact inventory, actual SDK
stdio discovery/retrieval/provenance, authenticated read/write lifecycle and all
nine new compatibility cases. Related regression and both full suites subsequently passed; their separate result records are retained.

## Bounded evaluation against the same flat records

The resumed changes concern MCP admission/status, diagnostic version reporting
and test expectations only. Object projection, migrations, extraction, Mind and
the fixture are unchanged from the measured source snapshot. The 1,000-event
evaluation is therefore retained, not repeated; final hashing will confirm this
scope before completion.

The evaluation used exactly 1,000 synthetic events: the twelve frozen turns
through real rules-only Mind jobs and 988 explicit project claims through the
existing deterministic extraction pipeline. No embedding/model provider or full
benchmark suite was used. The pre-projection flat baseline and mapped database
contained the same 1,000 events, 1,001 memories, 1,001 memory-source proofs and
zero original graph edges. Projecting did not create or rewrite canonical evidence.

The map contained 3,018 objects, 3,018 object proofs, 5,049 memberships, 5,084
membership supports and 1,027 associations. All 989 expected project identities
were distinct, with distinct labels and exact original source proof: zero
observed project false merges. Six checked candidate/origin/criterion/work
associations matched the frozen ground truth, with zero observed false
associations in that small subset. This is not a population-level error estimate.
Five negative turn categories produced zero typed attribute proofs. The plan had
twelve supported owner paths, including all three mandatory routes, and two
direct fact/evidence paths. Correction history, retraction, foreign-tenant denial,
zero-growth replay and database reopen all passed. Two-principal/tenant
same-name isolation and ambiguity are additionally covered by focused tests.

| Measurement | Actual result |
| --- | --- |
| Existing deterministic ingestion, 988 additional events | 331.048 s |
| Projection, 1,000 events over bounded pages | 22.074 s |
| Non-destructive replay, 1,000 events | 21.117 s; zero new objects/proofs/memberships/relations |
| Flat memory lookup, warm 25 samples, p50 / p95 | 4.061 / 4.907 ms |
| Object lookup with proof validation, warm 25, p50 / p95 | 9.901 / 10.572 ms |
| Bounded explanation, warm 25, p50 / p95 | 361.226 / 444.033 ms |
| Flat schema-v6 backup / mapped checkpointed SQLite | 3,932,160 / 16,781,312 bytes |
| Evaluation process peak working set | 49,733,632 bytes |

The flat database already has empty schema-v6 tables. Lookup and explanation
do different work; these timings are not a speedup claim. The measured utility
is typed multi-parent navigation with original proofs, at added storage/read
cost. No 10,000-record test, answer-quality metric, generalization or large-scale
performance claim is made. Input manifest, result, progress and native resource
samples are preserved under `.test-artifacts/e3-1000/` and the guarded
`product-P3-20261030/eval-1000/` controller directory.

## Privacy and operational review

Automatic approval review rejected a proposed extension to privileged erasure
planning/cleanup because it could alter irreversible deletion behavior. That
proposal was not applied. The implemented alternative retains the existing erasure
procedure and refusals, uses source-proof foreign keys for derived label cleanup,
and hides unsupported semantic navigation. Only its schema verifier recognizes
v6. No approval bypass or extra deletion step is included.

CLI source content requires explicit trusted-local opt-in. Routine tree/inspect
omit source bodies; redacted export also omits private labels, raw scope IDs and
locators. Stable hashes can be correlated and do not promise anonymization.
MCP authorization, worker fencing and source immutability remain unchanged.
Synthetic erasure tests do not make a cryptographic secure-deletion claim.

Host: Windows 10 Pro 10.0.19045, Intel i5-4690 (four cores/threads), about 11.95 GiB
visible RAM. Evaluation admission recorded 6,859,776,000 available bytes, unchanged
boot and zero loaded models. Only read-only model-list metadata was queried;
generation/preload/download/unload/cloud AI calls remain zero. Resource monitors
sample RAM/commit and poll Windows errors, aborting on low memory, ≥85% commit,
stale monitoring or model-access violations. These are isolated harness controls,
not shipped runtime protection. The previous BSOD root cause is still unknown.

## Limits and owner review

This is bounded deterministic object navigation, not general natural-language
entity resolution. Recognizers cover a small set of explicit English patterns;
unrecognized source-backed claims remain attributed facts. Identity requires
exact scoped evidence; fuzzy similarity and embeddings never merge objects.
Corrections require review and do not automatically supersede protected memories.
Explicit builds/replays are required; no automatic private-data backfill occurs.

Limits include 5,000 registry objects per principal partition, 128 proofs per
object, 16 relation/summary proofs, 32 memories per event, 1,000 build events per
page and 10,000 read-work units. Tree maximum is 500 nodes/depth 10; larger maps
need finite branch navigation and pagination. Oversized source contexts fail
explicitly. Old opaque registry anchors can persist after erasure; physical
SQLite pages/backups remain governed by existing retention/backup procedures.

No improved chatbot accuracy, infinite context, broad model acceptance or
large-scale superiority is claimed. The controlled evaluation measures local
mechanics, not P4 retrieval/answer quality. P4 context virtualization, adaptive
TRACE prompting and P5 release/marketing remain deferred. At local acceptance, successful hosted CI referred to the exact P2.1 predecessor.
New P3 hosted CI is reviewed after the separately authorized branch push and draft PR.

Owner sign-off requires reviewing the migration/authority boundaries, bounded
pattern coverage, evidence results and final package inventory. At local acceptance, no changes were
staged or committed. All resumed regression and distribution checks below passed. The owner-confirmed manual restart is not
an active blocker; a separate unexplained stability event would require a stop.


## Final resumed verification

Python 3.11.4 with pytest 9.1.1 and Python 3.12.6 with pytest 9.2.0 each passed
the complete suite: 767 cases (707 original plus 60 P3 cases), with zero skips.
Both used pydantic 2.14.1 and MCP SDK 2.3.0 for optional integration tests. The
3.11 environment tested current editable source; the fresh 3.12 environment
tested the newly built wheel, with all 88 installed runtime module hashes
matching the captured source. Suites were sequential, offline and synthetic.

Four further fresh core-only installations covered wheel and sdist on each
Python version. Each passed dependency checks, all 88 runtime hashes, eight
existing CLI contracts, the P2 rules/provenance/replay/retraction lifecycle,
the P3 real-Mind three-path/correction/reopen example and six installed P3 CLI
commands (tree, inspect, history, explain, redacted export and exact alias find).
That is 32 existing plus 24 P3 CLI checks, 56 total. Core operation does not
require the optional MCP SDK or a model provider. Archive checks verified
metadata/license/content and excluded private/generated databases, model files,
credentials and test environments. Final report-bearing archives are checked
again for current report bytes and payload equivalence; archive hashes live in
the machine-local ledger to avoid self-referential hashes in this report.

The two full-suite monitors recorded at least 6,742,863,872 available RAM bytes and at most 32.9156% system commit. No monitoring abort, new Windows error or offline model/network violation occurred. These measurements do not establish a BSOD fix. The owner-confirmed manual restart remains historical evidence, with no new spontaneous crash claimed.

The final read-only audit confirmed 88 current runtime modules and all captured validation-source hashes, 71 unchanged original runtime modules, 287 preserved prior acceptance artifacts and 303 preserved prior P3 files. All 47 checked scale-runtime paths and 6 scale artifact files remain unchanged; no repeat 1,000-event evaluation was needed. Provider prompts/fallback, source validation, authorization, retraction and lease/fencing remain intact. No real TRACE/MongoDB/private memory records or credentials were accessed, and no real model generation, preload, download or cloud AI call was made.

At local acceptance, no file was staged and HEAD remained the accepted P2.1
parent on the dedicated P3 branch. No commit, push, merge or release had been
performed at that point. The subsequent owner approval permits one reviewed P3
commit, a dedicated-branch push and a draft PR stacked on `feature/mind2-p2-review`.
The resulting commit, remote SHA and actual hosted-CI conclusions are recorded
with the PR and publication ledger, rather than embedding a self-referential
commit hash here. No merge, release or P4 work is authorized.

Evidence: `compat-smoke/`, `compat-related/`, `full311/`, `full312/`,
`runtime-snapshot.json`, `prepare312/`, `build-tested/`, `build-final/`,
`clean-installs-short/clean-installs.json`, `final-audit.json` and the final
archive-equivalence ledger in the separately identified resumed directory.
Final review archives are in `dist-review-final/`; current-report and payload
equivalence are recorded in `report-packaging-final/final-package-equivalence.json`.
The original 697/61 result and all previous failures are retained as history.

## Owner-approved publication review

The tested 64-file implementation was reconciled with Git status before any
staging. Before the EOF cleanup below, all 88 runtime modules and 162 captured
validation-source files matched the accepted snapshot. The two 767-case full suites, four clean installs,
56 CLI checks and existing 1,000-event evaluation therefore remain applicable.
No full suite, heavy scale benchmark or real-model experiment was repeated.

The API introduction now states SQLite schema v6. Current-schema wording was
also corrected in README and six existing operational/MCP/developer guides. P1's
historical v5 baseline, Stage 6's v5 outbox introduction, historical migration
SQL 1–5 and the measured Stage 9/P2 v5 research baseline remain accurate.
Current MCP admission requires supported v6 storage; parsing a legacy v5 status
response does not admit or automatically migrate a v5 database. Future schemas
remain rejected. No authorization, erasure, worker or extraction policy changed.

Eight current-document files and retained legacy-wire/historical references
passed the focused documentation check. The new guarded publication run passed
36 package-content, migration and MCP compatibility cases with zero skips.
Wheel and sdist are rebuilt with the corrected documentation before staging;
the publication gate requires all 88 runtime hashes to match accepted source,
safe archive contents and `git diff --check`. These results are preserved under
`.test-artifacts/product-P3-publish-20261030T223057Z/`.

A nonblocking cosmetic limitation remains in the accepted runtime: a generic
MCP failure hint and a preserved Stage 5 example banner still mention v5.
Actual admission/status/doctor schema checks use v6. Those tested runtime bytes
were deliberately not changed during this documentation-only approval step.
This does not weaken future-version rejection or any authority boundary.

The final reviewed set contains 70 paths: the original 64-file P3 set plus
six existing guides (`background-mind`, `mcp-integration`, `mcp-security`,
`product-onboarding`, `product-security`, `developer-guide`). Apart from the explicitly approved EOF cleanup below, source, tests and
fixture bytes are unchanged by this approval step. Only explicit reviewed paths may be staged;
test artifacts, private data, credentials, model weights and crash dumps are
excluded. PR #1 remains an unmerged draft and is not altered by P3 publication.

### Explicitly approved EOF cleanup

The complete staged diff exposed one extra blank line at EOF in
`src/oomp/objects/__init__.py`; the earlier unstaged diff check had not inspected
new untracked files. Commit/push were held, and the failed check and original
staged patch were preserved. The owner then explicitly approved removing only
that blank line and running fresh focused/hash/package verification.

Exactly one final LF byte was removed. The other 87 runtime file hashes remain
identical. Original init SHA-256: `f7ae8f932d3d47e1ea8f09c629e7c858758aa493f773e83e8c85e91af9078d67`.
Approved init SHA-256: `4df11ae8d2cfd9433c4c8706a1cd394f058334798d426a926cd0085f6f640ca5`.
Both Python 3.11 and 3.12 produced identical ASTs and identical compiled code
before and after the cleanup. No import, export, executable statement, policy,
source proof or worker behavior changed. The fresh focused run passed
**45 cases**, with zero failures/errors/skips, in
246.133 seconds (JUnit). Rebuilt archives must match the new
88-module approved whitespace snapshot before commit, and the staged diff check
must pass without suppressing or weakening whitespace checks.

The original 767/767 full-suite and four-install/56-CLI evidence is retained
against its original byte snapshot; it is not relabeled as a new full run.
The documented AST/compiled-code equivalence plus fresh focused and package
checks justify this owner-approved nonfunctional change. The heavy 1,000-event
evaluation and actual model inference were not repeated. Hosted CI separately
tests the exact published commit after the approved push and draft PR.

## Complete reviewed publication inventory (70 files)

- `.gitattributes`
- `MANIFEST.in`
- `README.md`
- `docs/api-reference.md`
- `docs/background-mind.md`
- `docs/developer-guide.md`
- `docs/mcp-integration.md`
- `docs/mcp-security.md`
- `docs/object-memory-architecture.md`
- `docs/object-memory-cli.md`
- `docs/product-milestone-P3-report.md`
- `docs/product-onboarding.md`
- `docs/product-security.md`
- `examples/backup_restore.py`
- `examples/fixtures/README.md`
- `examples/fixtures/object_relocation_v1.json`
- `examples/mind2_model_acceptance.py`
- `examples/mind2_quickstart.py`
- `examples/object_memory_quickstart.py`
- `examples/product_quickstart.py`
- `examples/quickstart.py`
- `examples/stage4_temporal_graph.py`
- `examples/stage5_hybrid_retrieval.py`
- `scripts/verify_install.py`
- `src/oomp/cli.py`
- `src/oomp/mcp/cli.py`
- `src/oomp/mcp/contracts.py`
- `src/oomp/mcp/service.py`
- `src/oomp/objects/__init__.py`
- `src/oomp/objects/cli.py`
- `src/oomp/objects/contracts.py`
- `src/oomp/objects/policy.py`
- `src/oomp/objects/queries.py`
- `src/oomp/objects/relations.py`
- `src/oomp/objects/service.py`
- `src/oomp/objects/storage.py`
- `src/oomp/product/diagnostics.py`
- `src/oomp/storage/migrations.py`
- `src/oomp/storage/object_migrations.py`
- `src/oomp/storage/privacy_store.py`
- `src/oomp/storage/sqlite.py`
- `tests/test_mind2_example.py`
- `tests/test_mind2_governance.py`
- `tests/test_object_graph_compatibility.py`
- `tests/test_object_mcp_compatibility.py`
- `tests/test_object_migrations.py`
- `tests/test_object_navigation.py`
- `tests/test_object_privacy.py`
- `tests/test_object_projection.py`
- `tests/test_object_storage.py`
- `tests/test_object_views.py`
- `tests/test_product_diagnostics.py`
- `tests/test_product_profiles.py`
- `tests/test_stage10_release.py`
- `tests/test_stage2_cli.py`
- `tests/test_stage2_storage.py`
- `tests/test_stage3_cli.py`
- `tests/test_stage3_pipeline.py`
- `tests/test_stage3_storage.py`
- `tests/test_stage4_graph.py`
- `tests/test_stage4_graph_limits.py`
- `tests/test_stage4_temporal.py`
- `tests/test_stage4_topics.py`
- `tests/test_stage5_integration.py`
- `tests/test_stage5_storage.py`
- `tests/test_stage6_acceptance.py`
- `tests/test_stage6_engine.py`
- `tests/test_stage6_maintenance.py`
- `tests/test_stage6_privacy.py`
- `tests/test_stage6_storage.py`
