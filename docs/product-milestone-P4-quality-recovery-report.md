# P4 quality recovery — final measured results and stop report

Date: 6 November 2026 (Asia/Karachi). **Gate A PASS; Gate C FAIL;
Gate B NOT TESTED. P4 is not complete. Stopped for owner review.**

The narrow source corrections and their single authorized candidate experiment
are complete. The new authenticated TRACE/MCP experiment passed all 137 required
checks and all twelve frozen scenarios, recovering all 16 expected source/query
pairs. The separately authorized independent-host attempt failed and was not
retried. No real-model inference occurred.

A later documentation-only continuation detected new Windows System errors.
They block further execution under the existing exact-event safety policy;
they occurred after the completed experiments and are recorded separately below.
Only existing evidence was read and this report updated after that block.

## Scope, source and preserved evidence

OOMP remains on `feature/p4-retrieval-quality`, with uncommitted changes based on
`d34bfbbbec44b0e016ddc41da1a7e27a45d45a68`. TRACE remains unchanged at
`dcfda75325be0254232c1f1342601692ce18f937`. No commit, staging, push, PR, merge,
deployment, release or P5 work was performed.

Evidence root: `.test-artifacts/p4-quality-recovery-20261105T203249Z/` (called
`QA` below). The fresh disposable lab is `D:\gq-1105203249`. Historical reports,
ledgers, failed attempts, original snapshots and the separate retraction copy
were preserved. `product-milestone-P4-retrieval-quality-report.md` remains the
original diagnosis. The interrupted version of this report is also preserved
byte-for-byte as `QA/report-before-final-review-20261106T1435Z.md`.

The original twelve scenarios, sixteen gold source/query pairs and fictional
source fixture were not modified. The original frozen fixture SHA-256 is
`a60a32b9abb04fc06386ae808cfaf10def98a134d71c530b64103a269a8109ba`.
Sixteen separately frozen paraphrase/negative controls have SHA-256
`ba8b915bfc24d763f8ece5fd1c2a22b7df63729d46e09ee2f416da617c7e95d1`.

## Implementation and independent source proofs

| Literal user statement | Original P2 classification | Corrected classification |
| --- | --- | --- |
| `In this fictional test, I use NOVA as my personal alias.` | Generic episode/stated | Profile/alias, explicit, user-attributed, unverified and unauthenticated |
| `Please keep your replies concise and use three bullets when a list is helpful.` | Generic episode/stated | Procedural/preference, explicit user request |
| `I may relocate from Cedar Bay to Larch Haven next spring, but this is only a tentative plan.` | Generic episode/stated | Prospective/plan, tentative; no completed-move claim |

The actual new database independently verified these three classifications,
their exact Unicode spans (respectively 0–56, 0–78 and 0–92), source event IDs,
user role, principal, sensitivity and unverified attribution. Existing role,
quote, question, hypothetical and sensitivity checks precede the new grammar.
Literal third-party statements retain their original semantics; the legacy
technical parser keeps the literal sentence with `subject=None`. It does not
make that third party the speaker's personal alias.

`rules.py` retains the original classifier as `classify_legacy`.
`context/validation.py` reconstructs eligible old generic episodic nodes using
that original classifier and requires the complete canonical fingerprint and
key. `objects/storage.py` permits historical assertion compatibility only
through the same independent reconstruction. Metadata alone never establishes
source entailment. Exact event IDs, spans and source authority remain required;
no database schema or migration was changed.

The bounded planner now interleaves topic/variant terms instead of exhausting
the term budget on the first facet (at most 32 terms and three variants).
Relevance checks distinguish typed alias/preference evidence, anchored
project-versus-alias questions, relocation/infrastructure/robot/pet domains and
each clause of a bounded conjunction (at most eight clauses). Unsupported
conjunctions remain uncertain with no evidence. A regression also showed that
literal relocation-candidate discussion must remain admissible for queries
explicitly asking about those candidates; that narrow compatibility fix is
covered by the unchanged existing summary tests and a new negative test.
No gold source IDs, archive-wide scans or new model calls drive selection.

Changed runtime files are exactly `understanding/rules.py`,
`context/validation.py`, `objects/storage.py`, `context/planner.py` and
`context/engine.py` under `src/oomp/`. Other public changes are `MANIFEST.in`,
the two new quality test modules, the separate quality-control JSON/checksum,
and this report. The prior diagnosis remains preserved. Authentication, grants,
legacy retrieval contracts, worker leases/fencing and schema/migration code
were not changed.

## Offline regression and package evidence

All suites ran sequentially on disposable synthetic storage with a model/network
guard. No real Ollama, cloud or physical MongoDB call was permitted.

| Validation | Actual result and qualification |
| --- | --- |
| Python 3.11.4 applicable complete test inventory | **968 unique passing tests**, zero failures/skips in the verified coverage union |
| Single full-suite command `regression311-09` | Hit its fixed 1,100-second deadline after 761 observed passes; no finalized JUnit for that prefix |
| Remaining bounded 3.11 segment | **207 passed**, 249.14 s; complete JUnit and node-ID journal, zero overlap with the prefix |
| Python 3.12.6 compatibility selection | **173 passed**, 372.946 s; nine extraction/governance/source/context/security/object/migration files, not a complete 3.12 suite |
| Related 3.11 context regressions | **50 passed**, 123.84 s; overlaps the complete inventory |
| Experimental harness policy/SQLite guard tests | **42 tests + 75 subtests passed**; JUnit records 117 cases, 0.894 s |
| New public quality tests | 53 extraction cases and 27 retrieval cases, included in the results above |

`QA/regression311-coverage.json` verifies collection order, 761 + 207 unique
passes, no overlap, no skips and unchanged runtime hashes. This is complete
inventory coverage across bounded segments, not a claim that one uninterrupted
full-suite invocation passed. The historical failed assertions, collection and
stdio-launcher failures, and the timeout remain in their original files. Focused
runs overlap: their counts must not be added into a new total. No guard violation
was recorded. The pure JSON measurement postprocessor was not executed during
the final continuation after the new health block.

The isolated candidate wheel and sdist were built from the final tested public
snapshot using cached setuptools 84.2.1, without downloads. All 95 runtime
modules match current tested source, both archives and the installed candidate;
307 public sdist files were byte checked. The source snapshot contains 308
reviewed public files. Archives contain no private/generated database, model,
environment, credentials or crash artifacts. The new frozen quality fixture is
included in the sdist.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `oomp_memory-0.1.0-py3-none-any.whl` | 254187 | `6c2f7b429b21d2510d7567cc7ee306bef1a5dcd5529af5646b579b6e42363694` |
| `oomp_memory-0.1.0.tar.gz` | 825757 | `ee05e22de08eb701c2ba093dd3c208615f422edabb7d0b6d6b8ca64862bb1569` |

`QA/package-install.json` records a fresh isolated target install of that local
wheel (`--no-index --no-deps --no-compile`), all 95 runtime modules compiled on
3.11, source equality, candidate-only OOMP import origins and three successful
CLI help checks. Existing hash-verified dependencies were reused; they were not
reinstalled. This does not claim separate clean wheel and sdist installations
on both Python versions. This final report postdates the packaged snapshot;
runtime source has not changed since packaging.

## Fresh fictional projection and Gate A

The actual authenticated TRACE publisher admitted 37 fictional events to a new
schema-v6 database. The real rules-only Mind worker completed 112 jobs/attempts
in ten bounded batches; each attempt retained fencing token 1, with no failed,
retrying or active leases at completion. Recorded worker scheduling elapsed
time is 119.547 seconds. The final projection has **58 memories, 58 source-proof
sets, 58 links and 58 lexical documents**: 51 episodic, one procedural, four
project-state and two profile memories. Four scoped ObjectMaps were built and
independently checked. SQLite integrity was `ok`, with zero foreign-key
violations; the database was 2,150,400 bytes.

The known default multi-principal scheduler defect was reproduced and remains
**OPEN**. One previously approved explicit extraction enqueue was used for the
single frozen foreign-principal event. It is an experimental workaround, not a
scheduler repair. The 112 jobs include that extra extraction job.

The first actual `memory.context` smoke for `What is my ORBIT42 project?` returned
`found_relevant_evidence`, two TRACE-accepted original-source proofs and a
2,152-byte packet in **538.6475 ms**. The original fictional interaction was
`000000000000000000001001`; source `p4b-source-project`, event
`trace-7e7a313703d5543770e4052ff72a2901089041f42e328a8bcee443f2b9b9e24a`.
TRACE validated exact spans 0–58 and 59–110 against its fictional authoritative
record. This is a semantic retrieval/provenance pass, beyond HTTP success.

All twelve real TRACE/MCP scenario results follow. Recall and precision count
unique user-role source/query pairs. The two empty-gold controls have undefined
precision, not invented perfect precision. Raw, TRACE-accepted and final
prompt-selected source counts agree for each row.

| Frozen scenario | Outcome | Gold recovered | Selected precision | Packet bytes | Prompt bytes |
| --- | --- | --- | --- | ---: | ---: |
| Project | PASS | 1/1 | 1/1 | 2152 | 3830 |
| Explicit alias | PASS | 1/1 | 1/1 | 1132 | 3990 |
| Reply style | PASS | 1/1 | 1/2 | 2124 | 5262 |
| Robot plan | PASS | 1/1 | 1/1 | 2132 | 4958 |
| Tentative relocation plus correction | PASS | 2/2 | 2/2 | 4165 | 6605 |
| Infrastructure discussion | PASS | 1/1 | 1/1 | 1186 | 5573 |
| Multi-facet continuity | PASS | 6/6 | 6/7 | 11052 | 12676 |
| Unicode evidence | PASS | 1/1 | 1/1 | 1149 | 6322 |
| Political topic without affiliation inference | PASS | 1/1 | 1/1 | 1169 | 6780 |
| Unsupported pet question | PASS, no evidence | 0/0 | undefined | 0 | 6101 |
| Project is not personal alias | PASS | 1/1 | 1/1 | 2152 | 7673 |
| Foreign-principal question | PASS, uncertain/no evidence | 0/0 | undefined | 0 | 6850 |

| Evidence stage | Recall | Precision | Non-gold source/query pairs |
| --- | --- | --- | ---: |
| Raw OOMP retrieval | 16/16 (100%) | 16/18 (88.89%) | 2 |
| TRACE independently accepted | 16/16 (100%) | 16/18 (88.89%) | 2 |
| Final prompt selection | 16/16 (100%) | 16/18 (88.89%) | 2 |
| Historical accepted-runtime baseline, unchanged | 12/16 (75%) | 12/23 (52.17%) | 11 |

The two current non-gold pairs are the valid synthetic `gate-a-retraction`
preference source selected for reply-style and continuity queries. Its proofs
are valid, but it is outside the frozen gold sets, so both count against
precision. No claim of zero false positives is made. Historical baseline
required outcomes were 9/12; this candidate achieved 12/12.

Across the twelve requests, direct MCP timings were 105.942–284.582 ms; observed
MCP time inside TRACE was 47–234 ms, and full synthetic route timings were
110.988–334.261 ms. These are distinct measurements including separate calls,
not a real-model latency benchmark. All packet and prompt checks passed:
maximum evidence packet 11,052 bytes under 12,000; maximum prompt 12,676 bytes
under 32,768, with configured generation reserve 512 and safety overhead 256.
Current-message bytes, complete recent exchanges, feedback, original-source
shapes/roles, correction chronology, uncertainty and source-policy assertions
passed. Fifteen deterministic fake-generator calls captured prompts across the
matrix; actual model answer correctness remains unmeasured.

All **137/137** Gate A assertions passed, including bearer authentication,
tenant/namespace/principal context isolation, rejected caller scope overrides,
read-only ingest and raw-content denial, TRACE owner/session authentication,
tampered event/session/role/timestamp and Unicode offset rejection, unsupported
proof authority, exclusion, actual budget omission, feedback retention, legacy
413 reproduction versus finite adaptive prompt allocation, mandatory-context
overrun, actual retraction on the separate copy, disabled/outage truthful
fallback, legacy compatibility and restart/reopen. This preserves the documented
legacy namespace contract described below; it does not claim all legacy tools
provide the stronger context principal boundary.

`QA/candidate-integration-result.json` records Gate A success, all owned services
stopped, no remaining listeners or cleanup failures and unchanged baseline SHA
`206af1066b860784ff4ad3ded1295a99168292e9656ebcbbb3dd0d7cbbf7c47d`.

## Gate C failed once: legacy boundary mismatch

The separately claimed generic-host ledger was consumed once. The official SDK
host used no OOMP or TRACE internal imports, a separate synthetic identity and
read grant. Its positive context and own-source assertions completed before
the failing cross-principal legacy source check. The controller recorded
`RuntimeError: generic_host_child_failed`; the child recorded an
`ExceptionGroup`. No nested exception or source-response body was preserved,
so the exact inner assertion is not asserted as captured evidence.

Static review establishes the test-contract mismatch: the generic identity was
`gate-a/fictional/trace-foreign`, sharing the primary reader's tenant and
namespace. `generic_host.py` required a cross-principal `memory.get_source`
denial. The accepted legacy endpoint uses `read_snapshot(scope)` with
`principal_only=False`; memory and event lookups enforce tenant/namespace, not
principal. This legacy behavior is explicitly documented in the P4A report.
The captured sequence ends after the cross-principal source lookup, with both
own and cross-source HTTP responses 1,796 bytes. The most likely inner failure
is therefore `generic_cross_principal_source_not_denied`; that remains an
inference supported by code and sequence, not a saved nested traceback.

**Gate C is FAIL / NOT ACCEPTED.** Later generic-host negative checks did not
execute and are not claimed as passed. The minimum proposed correction is a
second host in an existing distinct fictional tenant or namespace with its
matching separate read grant, testing the actual legacy boundary, while
retaining the stronger principal-only assertions for `memory.context`. This
correction is not implemented or retested here. Do not change the accepted
runtime contract merely to make this demonstration green. A fresh live attempt
requires owner authorization and health disposition; no automatic retry occurred.

Both owned Gate C processes exited, no listeners/cleanup failures remained,
all 95 runtime modules and sealed inputs were preserved, the baseline hash was
unchanged and Gate A evidence retained SHA-256
`585b4d8427300572a38f215a867fa1729b2eaf418d9741f876133e373c164460`.

## Safety, final health block and remaining gates

The existing experimental controller kept admission at 4 GiB available RAM,
commit below 75% and 2 GiB free disk, stopping below 1.5 GiB RAM or at 85% commit.
Native PID creation stamps, Windows Job ownership, loopback listener checks,
cancellation, bounded logs/database, resource polling and System-error polling
remained active. Gate A took 202.313 seconds, with minimum available RAM
6,660,317,184 bytes and maximum commit ratio 0.3656784. Gate C took 7.078 seconds,
minimum RAM 6,747,443,200 bytes and maximum commit ratio 0.3606025.

The experimental SQLite guard admits only the exact pinned lexical `:memory:`
call and accepted FTS5 probe, plus narrowly owned synthetic operations; unrelated
disk paths, URI variants and private databases remain denied. Existing owned
dependency RECORD checks were reused without installation. No real MongoDB,
private OOMP profile, `.env` credential, external model service, Ollama generation,
preload, download or Windows configuration change occurred. Historical artifacts
were not deleted. Monitoring, process containment and polling cancellation are
experimental harness functionality, not newly shipped runtime protection.

At final review, the boot session was `2026-11-06T14:23:53.5000000Z`. Read-only
health inspection found these later System errors, outside prior exact-event
owner dispositions:

- TPM-WMI 1801 at `2026-11-06T14:30:11.3672266Z` (19:30:11 PKT): Secure Boot
  CA/keys need updating.
- Service Control Manager 7000 at `2026-11-06T14:24:14.8093113Z` (19:24:14 PKT):
  `RealtekWlanU` failed to start because the specified file was not found.

These are recorded in `QA/final-review-health-block-20261106T1430Z.json`.
No new test, application process or experiment was launched after detection.
The changed boot session and those messages are not classified as a confirmed
spontaneous crash or BSOD. Prior owner-confirmed manual restarts and exact TPM
dispositions remain intact; no Windows stability or BSOD-resolution claim is made.

Gate B remains **NOT TESTED**. Its preparation is the unchanged twelve-scenario,
sixteen-pair fictional workload, captured source-verified prompts and historical
baseline, to be evaluated with a fixed model/configuration and separately
authorized RAM/commit/load/generation budgets. Real cross-session answer quality,
abstention, corrections and latency must be scored separately from retrieval.
No inference is authorized or scheduled by this report.

Remaining limitations are the failed independent-host demonstration, the new
health block, the open default multi-principal scheduler defect, two non-gold
source/query selections, heuristic language coverage, incomplete full-3.12
regression coverage and unmeasured real-model answer quality. No hosted CI or
publication was attempted for this uncommitted candidate. **STOP for owner
review; do not describe full P4 as accepted.**

---

## Preserved interrupted checkpoints (superseded by results above)

The following text records earlier states, including pending results and a
subsequently corrected test interpretation. It is historical, not the current
acceptance status. The complete original bytes are separately archived as noted
above.

# Historical P4 quality recovery — offline validation in progress

Date: 6 November 2026 (Asia/Karachi). **Not an acceptance result.**

Owner subsequently freed memory. The fresh check admitted execution with
6,911,746,048 bytes available RAM, 35.4% commit and zero new System errors.
The earlier blocked checkpoint below is retained as history. Final acceptance
and packaging results are still pending.

The current recovery is on `feature/p4-retrieval-quality`, based on OOMP
`d34bfbbbec44b0e016ddc41da1a7e27a45d45a68`. TRACE remains at
`dcfda75325be0254232c1f1342601692ce18f937`; its source was not modified.
The prior diagnostic report, accepted fictional snapshots and historical ledgers
remain separate and unchanged. Nothing has been committed or published.

## Implemented, awaiting regression validation

- `src/oomp/understanding/rules.py`: anchored literal user alias, reply-style
  request and modal-plan forms. Claimed aliases remain attributed and unverified;
  modal plans remain tentative. Existing role, quote, question, hypothetical and
  sensitivity checks precede the additions.
- `src/oomp/context/validation.py`: exact reconstruction of old generic P2.1
  episodes under the frozen original classifier. Full node fingerprint and
  canonical key must match; old metadata alone cannot establish entailment.
- `src/oomp/objects/storage.py`: historical assertion compatibility requires that
  same independent reconstruction. No schema or migration change.
- `src/oomp/context/planner.py` and `engine.py`: balanced bounded query expansion,
  typed alias/preference relevance, anchored project/alias contrast, domain
  relevance and per-conjunct domain/anchor coverage. Incomplete conjunctions
  withhold evidence. Existing retrieval limits and source authorization remain.
- `MANIFEST.in`: explicitly includes the new frozen quality-control fixture in
  the sdist so its new tests are reproducible from an archive.

These changes have received source review, **not completed test acceptance**.
The deterministic heuristic remains limited to supported literal language forms.

## Frozen controls and exact offline result

The original twelve scenarios, sixteen expected source/query pairs and original
fictional source fixture were not edited. Sixteen separate paraphrase/negative
controls were frozen before measurement in
`tests/fixtures/p4_quality/v1/query-controls.json`:

`ba8b915bfc24d763f8ece5fd1c2a22b7df63729d46e09ee2f416da617c7e95d1`

New extraction tests contain 53 cases; new retrieval tests contain 26 cases,
including two additional independent conjunct-anchor negatives without changing
the frozen sixteen-control file. The experimental wrapper also has twelve
unexecuted pure policy tests in the fresh ignored QA directory.

The first Python 3.11.4 extraction run completed **52 passed, 1 failed**, no skips.
Evidence:

`.test-artifacts/p4-quality-recovery-20261105T203249Z/results/offline-extraction-focused311-01.xml`

The failed new assertion expected `Mara uses Nova as her personal alias.` to be
episodic-only. Inspection established that the unchanged original technical
statement parser already represents it as a literal third-party semantic record
with subject `Mara`, not the speaker's profile/alias. Only the new test was
corrected: it now requires identical historical/current canonical fingerprints,
literal third-party attribution, no verified identity authority, independent
source entailment and rejection of forged speaker-alias proposals. The original
failure record is preserved. **The corrected test has not been rerun.**

The next retrieval test was denied before a child was launched. The unchanged
controller requires at least 4 GiB available RAM, commit below 75% and 2 GiB free
disk for admission; it stops below 1.5 GiB RAM or at 85% commit during execution.
The observed available RAM was 2,612,686,848 bytes (2.43 GiB), then
2,662,027,264 bytes (2.48 GiB); commit was approximately 58.6% and disk remained
above 100 GiB. No threshold was weakened and no unrelated process was stopped.

Evidence: `resource-admission-block.json` in the same QA directory. No full
regression, Python 3.12 run, package build or installation has occurred.

## Health and experiment preparation

The accepted health checkpoint was reused. An initial overly broad historical
query additionally returned a Service Control Manager 7000 event at
`2026-11-04T22:03:16.7584932Z`, before that accepted checkpoint; that failed check
is preserved in `fresh-health-disposition.json`. The corrected continuation
check found **zero new System errors since the previously accepted
`2026-11-05T20:03:56.024279Z` checkpoint**, recorded in
`essential-preflight.json`. No new historical event was dispositioned and no
Windows setting, service, driver or firmware was changed. The earlier
owner-confirmed manual restart and exact TPM-WMI dispositions remain historical
evidence; this does not establish that any BSOD cause was resolved.

Fresh experimental paths were prepared:

- QA: `.test-artifacts/p4-quality-recovery-20261105T203249Z/`
- Disposable lab: `D:\gq-1105203249`

The lab contains copied frozen input files and new synthetic grant descriptors;
secrets are intended to exist only in owned child environments during execution.
The existing safety harness was adapted for the authorized fresh projection and
dynamic memory inventory. **No candidate wheel, SQLite database, execution ledger,
authenticated server or rules-worker projection has been created or run.** The
prepared harness still requires its offline verification before live use.

## Acceptance status and remaining work

| Check | Current candidate result |
| --- | --- |
| Real authenticated context retrieval | NOT TESTED |
| Twelve frozen scenario outcomes | NOT TESTED — 0/12 executed |
| TRACE proof validation and bounded prompts | NOT TESTED |
| Security/failure/retraction/legacy/reopen matrix | NOT TESTED |
| Fresh projection inventory | NOT CREATED |
| Gate A | NOT ACCEPTED — offline validation blocked |
| Independent generic MCP host, Gate C | NOT TESTED; conditional on Gate A |
| Real-model answer evaluation, Gate B | NOT TESTED; no inference authorized |

Historical accepted-runtime measurements remain **12/16 source-query recall**,
**12/23 precision**, and **9/12 required scenario outcomes**; they are not results
for this candidate. No new recall, precision, latency or token-budget claim can
be made yet.

The default multi-principal scheduler defect remains open. If validation resumes,
the fresh fictional projection must use only the explicitly approved single
foreign-event enqueue workaround and report it separately. No scheduler fix is
included here.

Resume with sufficient available RAM, rerun the corrected extraction tests and
new retrieval/policy controls sequentially, then complete applicable regressions
before packaging. Only after those pass may the single-use authenticated
candidate experiment run. Preserve all existing failures and use fresh result
labels. A failed live experiment must not automatically retry. No private
profiles, real MongoDB, Ollama, cloud services, P5 or publication actions are
authorized by this checkpoint.

## Resumed offline validation history

All outputs use fresh labels under the same preserved QA directory; no live
execution ledger has been consumed.

- `quality-focused311-02`: 90 passed, 1 failed, 16 subtests passed. All 26 new
  retrieval cases and the then-existing twelve experimental policy tests passed.
  The remaining new extraction test incorrectly expected the legacy technical
  candidate's `subject` field to contain `Mara`. The existing parser leaves that
  field unset and preserves the literal third-party sentence. The corrected
  test retains fingerprint, independent entailment and forged-alias rejection.
- `literal-failure311-03`: that isolated corrected test passed.
- `regression311-01`: collection stopped because the fresh isolated harness
  omitted the repository root needed for the `benchmarks` Python package.
  Only the new harness path was corrected; `collection311-02` then collected
  all 967 tests present at that point.
- `regression311-03`: 77 passed, 1 failed. The MCP SDK filters parent environment
  paths, so its stock stdio child could not import OOMP. A fresh no-pip thin
  launcher now executes only the new offline startup hook, adds current source
  and approved existing native dependencies, and leaves historical startup
  hooks inert. `stdio311-04` passed the exact isolated failing test. No dependency
  package was installed or downloaded.
- `regression311-05`: 85 passed, 1 failed. This exposed a product compatibility
  issue: a valid source saying two places "are candidates" was excluded from
  an existing moving-candidates episode summary. Relevance now admits that
  literal discussion support only when a relocation query explicitly requests
  candidates. No plan/assertion classification, manifest or source check changed.
- `summary-fix311-06`: zero tests executed; a target name had just been replaced
  by the final lightweight negative test. This invocation error is preserved.
  `summary-fix311-07` passed both existing manifest cases, the new pure negative
  and six independent-host policy tests.
- `context-related311-08`: all **50** navigation, summary-admission, source-proof,
  isolation, identity relevance and coverage tests passed in 123.84 seconds.

The runtime correction adds one pure retrieval test, making the new extraction
and retrieval test counts 53 and 27 respectively. The original frozen sixteen
independent controls remain unchanged. The complete Python 3.11 run on this
corrected source is `regression311-09`; its final result is pending.

The resource monitor and offline model-access guard remain experimental harness
functionality. They are not newly shipped runtime protection, and do not prove
that the historical Windows instability was resolved.
