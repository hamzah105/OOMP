# P2.1 controlled local-model acceptance

30 October 2026, Asia/Karachi. **The fresh owner-approved experiment passed the
single-case real-model acceptance gate.** One actual Ollama proposal was
independently validated and persisted as a new procedural memory beyond the
rules-only episode. Reopen verification and owned-model unload succeeded.
This is a narrow synthetic integration result, not full release acceptance.

## Final offline stabilization and review: 30 October 2026

**P2.1 ready for owner commit review.** This conclusion is limited to the
accepted P2.1 scope. The owner accepted the single-case live result recorded
below; this finalization made **zero
Ollama requests**, including metadata, preload, generation and unload, and no
model downloads. No runtime implementation change was necessary. This section
supersedes the earlier historical statements about deferred regressions, the
stale Python 3.12 wheel and the live-untested v4 prompt as current status. The
historical measurements and stopped results remain preserved.

The branch remains `feature/mind2-p2-review`, HEAD
`248fecc851f6e0eb5335790cb79a8f6d40110a90`. All **79 runtime Python modules**
match the owner-accepted source hashes. The six other uncommitted P2.1 files,
including the crash report, are unchanged; only this acceptance report is updated.
All **287 inventoried previous acceptance artifacts** were checked byte for byte
and retained. Experimental ledger directories were neither reset nor reused.

### Offline tests and the Windows path correction

Tests ran one suite at a time with synthetic storage and independent Windows
RAM/commit monitoring. A temporary unconditional test-environment `sitecustomize`
audit guard blocked port 11434, model executable launches, and external socket
connections while permitting loopback test fixtures. It also loaded in isolated
`python -I` processes and product children whose environment is filtered.
The supervisor would stop its owned test tree immediately on a guard violation,
resource/monitor failure or a new System critical/error event. **No blocked
attempt occurred.** No test implicitly reached a real model provider.

| Sequential check | Exact result | JUnit duration |
| --- | --- | ---: |
| Focused Mind 2 / P2.1, Python 3.11.4 | **116 passed**, 0 failures/errors/skips | 73.446 s |
| Affected synthetic product lifecycle after path correction | **1 passed**, 0 failures/errors/skips | 21.514 s |
| Complete regression, Python 3.11.4 | **707 passed**, 0 failures/errors/skips | 583.429 s |
| Recovery lifecycle / authorization / path-security subset, Python 3.11.4 | **43 passed**, 0 failures/errors/skips | 68.806 s |
| Complete regression, fresh Python 3.12 installed wheel | **707 passed**, 0 failures/errors/skips | 580.707 s |
| Final pytest/build temporary-path policy, Python 3.11.4 | **7 passed**, 0 failures/errors/skips | 0.436 s |

The two final complete runs each contain the same 707 cases; the focused rows
overlap those cases. The recovery subset additionally includes five task-local
harness tests for the original MAX_PATH rejection and all four short-root
choices. These artifact-only checks do not change the 707 product cases.
The completed 3.11 run was recovered after the interruption; it was not repeated
after the additional requested recovery subset because no runtime source changed.
Python 3.11 uses the existing source environment. Python 3.12 uses a **new environment installed from
the freshly rebuilt wheel**, with dev/MCP/UI extras; its installed 79 runtime
module hashes match current source, both archives and the accepted snapshot.
The old installed P2 wheel was used only as a base interpreter to create the new
environment, never as the package under test. The actual new interpreter is
`3.12.6 (tags/v3.12.6:a4a2d2b, Sep  6 2024, 20:11:23) [MSC v.1940 64 bit (AMD64)]`.

Two earlier run records are retained separately and are not relabelled passes:

- `full311/` ended before a final result and had no surviving test process on
  resumption. Its termination cause is unestablished; it is not counted.
- `full311-resumed/` completed **706 passed / 1 failed** in
  581.562 s. The synthetic public lifecycle example's
  generated profile path was **275 UTF-16 units**. A pure path check confirmed
  the existing `profile_path_too_long_use_shorter_home` rejection at the 260-unit
  guard. Moving only disposable pytest storage to shorter fresh paths made that
  exact test and both subsequent full suites pass. The path guard and runtime
  were not changed. Original failed logs and `path-diagnosis.json` are retained.
  The original traceback is `RuntimeError: synthetic CLI acceptance failed:
  onboard` in `examples/product_quickstart.py:40`, called by
  `tests/test_product_lifecycle.py:216`. The exact failing temporary root was
  `D:/Desktop/OOMP/.test-artifacts/product-P21-final-20261029T225548Z/full311-resumed/temporary/test_public_product_example_us0`.
  The correction is confined to the ignored test supervisor's fresh short
  `--basetemp` choices; new task-local tests prevent repeating that harness error.

| Passing phase | Monitor samples | Minimum available RAM | Peak system commit | Maximum sample gap |
| --- | ---: | ---: | ---: | ---: |
| focused | 149 | 7.034 GiB | 33.688% | 0.531 s |
| focused-path | 47 | 6.232 GiB | 33.936% | 0.516 s |
| full311-short | 1149 | 6.299 GiB | 33.455% | 0.562 s |
| related-recovery | 140 | 6.271 GiB | 33.728% | 0.578 s |
| full312 | 1145 | 5.915 GiB | 35.451% | 0.547 s |
| packaging-path | 4 | 6.273 GiB | 33.862% | 0.516 s |

No passing phase crossed the 1.5 GiB RAM floor, 85% commit ceiling or 2-second
monitor freshness limit. The same Windows boot remained active, and the monitors
recorded no new critical/error System event. **The earlier BSOD cause remains
unidentified; these offline passes do not establish a BSOD fix.** Existing
Windows cancellation failures and successful experimental monitoring evidence
remain unchanged.

### Security, provenance and compatibility review

The provider retains only six allowlisted bounded integer timing/token metrics
and client elapsed time. It does not retain prompts, replies, context or
credentials in these diagnostics. Metrics reset for a new acquired attempt;
request budgets and circuit updates use the same lock. The v4 prompt uses
consistent category/predicate/assertion ordering and sends the structured schema
once through `format`. Empty, truncated, invalid and excessive proposals retain
explicit failure codes and deterministic rules fallback.

Source quotation/span, user/assistant attribution, predicate/category/assertion,
scope/principal and sensitivity are independently validated. Model output cannot
grant identity or source authority. Storage still rechecks immutable evidence,
retraction/erasure and worker lease/fencing transactionally before commit. The
source-retracted result code and regression tests are preserved. No schema,
privacy, authentication, source validator or worker fencing change was made in
this finalization. Synthetic lifecycle checks verify source references, exact
spans, replay without duplicate growth and retraction behavior after persistence.
All validation storage and profiles were disposable and synthetic. No private
OOMP database, real TRACE workspace/conversation or MongoDB record was accessed
or modified; credentials were not exposed.

**The resource sampler and polling HTTP cancellation wrapper belong to ignored
experimental artifacts. They are not shipped production features.** Shipped
`understanding/transport.py` remains the existing timer/socket-shutdown transport;
client limits cannot guarantee immediate server-side cancellation or bound model
server CPU/RAM. The observed Windows blocked-read limitation is retained and
must not be presented as repaired by this patch.

### Rebuilt distribution and clean installations

The distribution was rebuilt from current source using the existing local
builder, with `--no-isolation` and package indexes disabled. Forty-four already
cached dependency wheels supplied the offline wheelhouse; no dependency or model
download was performed. Twine metadata checks, package-path/content checks and
`pip check` passed. Python 3.12 full-suite extras were installed offline from that
fresh wheel, replacing the stale package as a test target.

| Archive audit | Files | Private/generated members | High-confidence credential matches |
| --- | ---: | ---: | ---: |
| oomp_memory-0.1.0-py3-none-any.whl | 86 | 0 | 0 |
| oomp_memory-0.1.0.tar.gz | 257 | 0 | 0 |

**Four new core-only installations passed**, sequentially: wheel and sdist on
Python 3.11 and on 3.12. Each imports from its own site-packages under `-I`, has
no MCP/TRACE dependency, passes `pip check`, matches all 79 accepted runtime
hashes, and passes eight actual CLI contracts (**32 total**). All four also pass
synthetic persist/extract/index/retrieve/reopen checks and the rules-only Mind 2
lifecycle (**four of each**), with zero model calls. No existing database or real
conversation is used. Schema remains 5; package version remains 0.1.0 and Python
requirement remains >=3.11.

After these results were written, the final distribution was rebuilt to include
this report in the source archive. Final archive checks verify current report
bytes and identical runtime/package payloads relative to the tested build,
apart from this documentation update. Archive hashes and detailed command logs
live in the local evidence directory to avoid a self-referential report hash.

### Evidence, staging safety and owner decision

Final offline evidence is under
`.test-artifacts/product-P21-final-20261029T225548Z/`. It contains the starting
snapshot, prior-artifact hashes, interrupted and failed run logs, passing JUnit
and monitor records, offline dependency inventory, rebuilt archives, installed
module comparisons, four clean-install/lifecycle reports and final preservation
audit. Short disposable pytest roots are separately ignored under
`.test-artifacts/fp21-20261030`, `f311-20261030` and `f312-20261030`.
The additional recovery subset used `.test-artifacts/rp21-20261030`.

The initial `clean-installs/` record is preserved as **failed**, after its first
wheel installation passed: the 3.11 sdist build could not create its wheel at a
**265 UTF-16 unit** pip ephemeral-cache path (`Errno 2`). The correction changed
only the ignored harness's `TEMP`/`TMP` to the fresh short
`.test-artifacts/ct21-20261030` root. Seven task-local path-policy tests then
passed, and the sdist was checked first in the new `clean-installs-short/`
directory before completing all four installations. The same sdist and unchanged
runtime were used. The original build error, measured path and both result sets
remain retained; no product guard or package source was weakened.

The recorded sequential commands were:

```powershell
.\.venv\Scripts\python.exe .test-artifacts\product-P21-final-20261029T225548Z\run_tests.py focused --python D:\Desktop\OOMP\.venv\Scripts\python.exe
.\.venv\Scripts\python.exe .test-artifacts\product-P21-final-20261029T225548Z\run_tests.py focused-path --python D:\Desktop\OOMP\.venv\Scripts\python.exe
.\.venv\Scripts\python.exe .test-artifacts\product-P21-final-20261029T225548Z\run_tests.py full311-short --python D:\Desktop\OOMP\.venv\Scripts\python.exe
.\.venv\Scripts\python.exe .test-artifacts\product-P21-final-20261029T225548Z\run_tests.py related-recovery --python D:\Desktop\OOMP\.venv\Scripts\python.exe
.\.venv\Scripts\python.exe .test-artifacts\product-P21-final-20261029T225548Z\prepare_tested_package.py --execute-after-full311-pass
.\.venv\Scripts\python.exe .test-artifacts\product-P21-final-20261029T225548Z\run_tests.py full312 --python D:\Desktop\OOMP\.test-artifacts\product-P21-final-20261029T225548Z\py312\Scripts\python.exe
.\.venv\Scripts\python.exe .test-artifacts\product-P21-final-20261029T225548Z\run_tests.py packaging-path --python D:\Desktop\OOMP\.venv\Scripts\python.exe
.\.venv\Scripts\python.exe .test-artifacts\product-P21-final-20261029T225548Z\verify_final_packages.py --dist .test-artifacts\product-P21-final-20261029T225548Z\dist-tested --execute-after-full-suites-pass
```

These are execution records, not instructions to overwrite existing evidence.
The phase directories refuse reuse. Future offline reproduction requires fresh
result/storage directories, the same fail-closed model guard in each test
environment, and short Windows pytest paths. The task-owned guard is removed
from the original developer environment after validation; it remains with the
disposable test environments. **Do not rerun any live controller or reset a
single-use ledger.** No further live model experiment is authorized here.

The Git index remains empty. The reviewable change set is exactly the seven
P2.1 paths listed in the preserved history. Archive audits and a bounded
high-confidence credential-pattern scan of those files found no credentials;
synthetic secret test strings are intentional. Generated artifacts, databases,
profile credentials and model files are excluded from distributions and the
Git change set. Pattern scanning is not a formal proof of secret absence.

Recommendation: after owner review, make an explicitly allowlisted seven-file
P2.1 commit, then obtain owner authorization before pushing and check hosted CI.
Avoid `git add .` or force-adding experimental artifacts. **No staging, commit,
push, merge, TRACE change, Windows/driver change, heavy benchmark or P3/P4 work
was performed.** Hosted CI and current online dependency-advisory checks have
not run for this uncommitted patch.

Remaining limits are the single prompt-adjacent synthetic live case, unproved
general extraction quality and repeated reliability, unproved cold/default
20-second behavior, server-side cancellation/resource limits, the established
Windows path limit, and the unidentified BSOD cause. The narrow P2.1 acceptance
and offline compatibility criteria passed; broad model or release safety is not
claimed. Work stops for owner review.

## Fresh owner-approved experiment: passed

The separately authorized experiment is
.test-artifacts/product-P21-owner-20261029T222605Z/
(created 30 October at 03:26:05 Pakistan time; the directory uses UTC).
The preceding recovery snapshots, stopped-run sentinel and experimental ledgers
were retained. All seven uncommitted files and their hashes were snapshotted
before this attempt. Branch remained feature/mind2-p2-review at
248fecc851f6e0eb5335790cb79a8f6d40110a90.

No runtime source changed during this owner-approved attempt. The controller
copied the already-tested ownership/cancellation machinery into the fresh
directory, strengthened the guard's immediate preload admission check to
**6.75 GiB**, explicitly tracked the rules-only verifier's owned child process,
and required successful unload verification. No unrelated Python process was
whitelisted. Six pure ownership checks and current process metadata passed
before the one live controller invocation.

### Windows and resource gates

At 03:28:07, read-only preflight reported 7,356 MiB available RAM, 32.44% system
commit usage, no loaded model and no unrelated Python workload. The current
virtualenv launcher/interpreter parent-child relationship and executable paths
passed the corrected ownership guard. No new critical/error System event or
Application Error/Hang event was found in the inspected post-recovery window.
The last boot remained 01:52:56. The earlier 0x50 cause is still unidentified.

| Recorded safety evidence | Actual value |
| --- | ---: |
| Required preload admission | At least 6.75 GiB |
| Minimum independently sampled admission RAM | 7.22 GiB |
| Required during-run available-RAM floor | 1.5 GiB |
| Minimum available RAM during preload / whole run | **2.400 GiB** (2,577,063,936 bytes) |
| Minimum available RAM during extraction | 2.467 GiB |
| Maximum system commit usage | **57.405%**, below the 85% stop threshold |
| Commit limit | 21,291,085,824 bytes |
| Monitor samples / intended interval | 191 / 0.5 s |
| Maximum observed sample gap | 0.656 s, below the 2 s freshness ceiling |
| Resource, ownership or monitor abort | None |
| After-cleanup available RAM / commit usage | 7.408 GiB / 34.02% |

Physical availability and system commit were monitored separately by the native
sampler. A concurrent observer checked loaded-model metadata and periodically
rechecked Windows events and process ownership. The previously verified polling
HTTP reader enforced cancellation and absolute deadlines. No safety threshold
was weakened. These observations do not establish that the Windows BSOD was fixed.

### Exact model, configuration and timing

The already-installed model was **llama3:latest, Llama 3 8B Q4_0**, via
**Ollama 0.40.13** at http://127.0.0.1:11434. The verified digest was:

365c0bd3c000a25d28ddbf732fe1c6add414de7275464c4e4d1c3b5fcb5d8ad1

There was no download, provider substitution or cloud call. The prompt was
mind2.prompt.v4, SHA-256:
fdd9585490a2903ae8cf0c8852bcd29c426dbc85503950c454123d09b4d94c2d.

| Operation / configuration | Actual evidence |
| --- | --- |
| Empty-prompt preload | **One**, completed in **48.641 s**, reason load |
| Preload deadline / finite keep_alive | 150 s / 90 s |
| Synthetic extraction-generation request | **One**, with no retry |
| Extraction client elapsed | **43.266 s** |
| Ollama-reported extraction total | 43.185786 s |
| Prompt evaluation | 300 tokens / 33.034716 s |
| Output generation | 32 tokens / 10.123772 s |
| Model load within the extraction request | 0.003997 s; preload was recorded separately |
| Extraction deadline / output-token cap | 60 s / 128 tokens |
| Context / threads / temperature / seed | 4,096 / 2 / 0 / 0 |
| Candidate cap / extraction keep_alive | 16 / existing 30 s |
| Genuine Mind extraction job elapsed | 43.422 s, including source checks and persistence |
| Owned-model unload control request | **One**, completed in 0.016 s, reason unload |

The production extraction deadline was not increased. This success used an
explicitly preloaded model and the existing maximum 60-second configuration; it
does not validate cold loading or the default 20-second extraction deadline.

### Rules, actual model output and independent validation

Both modes processed the identical frozen s01-e03 sentence:

> Please use numbered steps for setup.

The immutable fixture SHA-256 remains
c8ec3dccca6f5d4667401bcb20d661e3881bd11dec6fe25c10dc50ff71e1a257.
Its labels remain Codex drafts pending independent review.

| Stage | Verified interpretation or effect |
| --- | --- |
| Improved rules alone | episodic / stated / explicit; one episode, no canonical memory |
| Actual Ollama proposal | procedural / preference / explicit |
| Independent validator | candidate_validated; exact user source, span [0,36), ordinary sensitivity, authorized scope and principal |
| Genuine Mind persistence | Existing episode retained, plus one new procedural canonical memory |

The validator, privacy checks and source/worker authority were unchanged.
The model did not supply source authority or authenticated identity. Exact
quotation, speaker, predicate, category, assertion, sensitivity, event ID,
scope and principal were checked independently; the commit revalidated stored
evidence, retractions and job lease/fencing.

| Actual accounting | Count |
| --- | ---: |
| Model-origin proposals | **1** |
| Independently accepted proposals | **1** |
| Rejected proposals | **0** |
| Rules-equivalent duplicate proposals | **0** |
| Model interpretation refinements | **1** |
| Genuinely incremental persisted canonical memories | **1** |
| Incremental canonical Ollama proof links | **1** |
| Degraded fallback / failed / retried / lost-lease jobs | **0 / 0 / 0 / 0** |

The canonical memory is
mem-972dab7c108fadbd1e8f8385a1c82d853ff53b01107b1731d7a46898ff2a2c36,
linked to the new synthetic user event p21-model-procedure. Its proof uses
mind2.ollama.v1.5a5947544aa8a0ac and the exact source span [0,36).
The source is ordinary, the assertion explicit and verified remains false.
The model database contains two records: the same episode found in rules-only
mode and this additional procedural memory. Thus neither fallback output nor a
valid rules duplicate supplies the acceptance result.

Each mode completed its three genuine Mind jobs once, without error. A separate
isolated Python process reopened each disposable database and verified its
source/memory/proof hash; a fresh idle worker made no repeat inference call.
An additional read-only SQLite inspection confirmed matching immutable source
fingerprints/references, the retained episode, new canonical proof, and completed
attempt/fencing records. No existing private database was selected.

### Cleanup, lightweight verification and evidence

The model was absent from the initial loaded-model list and loaded by this
experiment. Only that owned model received the bounded keep_alive:0 unload
control request. Ollama returned done:true with reason unload, and the final
loaded-model list was empty. cleanup_verified is true. All guarded socket handles
were cleaned up. The Ollama service and unrelated processes were not stopped.

After unload, **five targeted offline tests passed in 7.31 s**, exit 0, with no
failures/errors/skips and zero real Ollama connections. They cover actual-worker
proof/reopen behavior using mocked HTTP, rejection of duplicate-only acceptance,
retraction during inference, stale-metric reset and expired-lease fencing.
No benchmark or full regression suite was run.

The exact single live invocation was:

    .\.venv\Scripts\python.exe .test-artifacts\product-P21-owner-20261029T222605Z\controlled_run.py --run

The subsequent lightweight invocation was:

    .\.venv\Scripts\python.exe .test-artifacts\product-P21-owner-20261029T222605Z\post_verify.py post

The fresh controller ledger is single-use and must not be deleted or reused.
Key local evidence in that directory is baseline.json, reviewed-controller.json,
windows-snapshots.jsonl, memory-samples.jsonl, request-ledger.jsonl,
controlled-result.json, live-one/acceptance.json, the new disposable rules/model
databases, post-test JSON/JUnit records and owner-verified-summary.json.
All 79 runtime modules, the frozen fixture and inventoried previous ledgers
remain byte-identical to the starting snapshot. Only this report is updated
after the experiment.

### Scope of this pass

The minimum genuine source-backed, incremental, durable model-acceptance criterion
passed for **one selected synthetic case**. The case is close to the prompt's
procedural example; this is not an independent generalization or corpus-quality
result. It does not establish default-deadline suitability, repeated reliability,
cross-machine safety, a repaired BSOD, general language coverage or release
readiness. Full regressions, current installed-package checks and hosted CI
remain deferred under the owner's explicit scope.

No production source edits, Windows configuration changes, TRACE changes,
credential changes, private migrations, commits, pushes, merges or P3 work were
performed during this attempt. The one preload and one generation budget is
consumed. No additional model request will be made; work stops for owner review.

## Previous limited resumption: preserved history

The remainder records the earlier stopped attempt. Its measurements and zero-call
outcome are historical and do not describe the successful owner-approved run above.

30 October 2026, Asia/Karachi. **Stopped at process-ownership preflight; real-model
acceptance remains unproved.** No model preload or extraction request occurred.
The preflight falsely classified this workspace's virtualenv launcher as another
Python workload. Its ownership rule was corrected and checked offline, but live
execution was not retried, following the owner's stop-after-blocked-gate boundary.

The owner authorized at most one separately counted preload and two synthetic
extraction requests, subject to Windows stability and resource gates. This
experiment is further limited to **one extraction request**, with no retry.
No full benchmark, full regression suite, new model download, Windows setting
change, TRACE modification, private-data migration, commit or push is authorized.

The recovered branch is feature/mind2-p2-review at
248fecc851f6e0eb5335790cb79a8f6d40110a90. The preserved six-file working state
is snapshotted under
.test-artifacts/product-P21-resume-20261029T215903Z/snapshot/.
The original [crash recovery report](product-milestone-P21-crash-recovery.md)
and historical model results are retained unchanged.

Only a demonstrated prompt inconsistency was fixed during resumption:
mind2.prompt.v4 consistently names memory_category/predicate/assertion_kind.
Examples include prospective/plan/tentative and episodic/stated/question.
The source validator, persistence authority, production extraction deadline,
context size and deterministic fallback are unchanged by this correction.

The pre-inference offline subset passed **48 tests** sequentially:
14 mocked-provider tests, 11 example/accounting tests and 23 selected
source-span, privacy, role, replay and lease/fencing checks. No Ollama
connections occurred during those tests. Syntax/import checks also passed.
The full regression suite remains deliberately unexecuted.

Initial read-only preflight showed approximately 7.5 GiB available physical RAM,
31% system commit usage, no Python worker, no loaded Ollama model and no new
critical/error System event since recovery. Installed Ollama is 0.40.13;
llama3:latest is Llama 3 8B Q4_0 with digest
365c0bd3c000a25d28ddbf732fe1c6add414de7275464c4e4d1c3b5fcb5d8ad1.
The earlier 0x50 cause remains unidentified; this is not a BSOD fix.

The selected immutable synthetic fixture is s01-e03:
“Please use numbered steps for setup.”
Its draft label is procedural/preference/explicit/canonical. Fixture SHA-256:
c8ec3dccca6f5d4667401bcb20d661e3881bd11dec6fe25c10dc50ff71e1a257.
Rules must first be verified to return only episodic/stated/explicit before
any model operation.

The experimental harness is separate from product runtime. It requires
4.5 GiB minimum before loading plus an additional estimated 8B allocation
reserve, monitors physical availability and system commit independently every
0.5 seconds, aborts below 1.5 GiB or at 85% commit, and treats monitoring failure
or stale samples as an abort. The 85% threshold is stricter than the owner's
90% ceiling. These are provisional gates, not crash-prevention guarantees.

Two offline cancellation checks exposed that Windows socket shutdown did not
promptly wake a blocked HTTP response-body read. **No model was loaded during
these failures.** Live execution remains gated on a successful polling-reader
cancellation test and native monitor smoke check. Failed traces are retained.

## Verified stopped-run result

The single controller invocation returned unexpected_python_workload before
performing metadata queries, loading, inference or creating synthetic Mind-job
storage. Earlier read-only version/tags/loaded-model queries supplied the
installed-model facts above.

A separate read-only diagnostic identified two related Python processes:
the current interpreter and its low-memory workspace virtualenv launcher parent.
The controller had allowed only its own PID. The correction now allows that
specific parent only when its PID relationship and executable path match the
current workspace interpreter. It also recognizes the bounded, controller-owned
virtualenv/base-interpreter chain used for restart verification. An unrelated
Python process, including one using the same executable path, still blocks.
Six pure ownership regressions passed, and a subsequent read-only process
snapshot found no unrelated Python PID. No resource threshold was reduced.

The original stopped result and one-use run sentinel remain intact. There was
no second controller execution, no inference retry and no ledger reset.

| Operation or result | This resumption |
| --- | --- |
| Controlled preload operations | **0** |
| Synthetic extraction-generation requests | **0** |
| Second extraction request | Not executed |
| Model unloading operations | 0; this run never owned a loaded model |
| Load duration / inference duration / generated tokens | Not measured; operations were not run |
| Model proposals / accepted / rejected / duplicates | 0 / 0 / 0 / 0; no model acquisition was executed |
| True incremental model candidates / persisted model proofs | **0 / 0** |
| Real-model persistence/restart acceptance | Not tested in this resumption |
| Real-model failure or fallback code | Not applicable; preflight stopped before acquisition |
| Controller stop code | unexpected_python_workload, diagnosed as an owned-launcher false positive |
| Required real-model acceptance | **Not passed** |

The pure deterministic check on the exact frozen sentence independently
confirmed episodic/stated/explicit with episodic-only retention and zero
canonical candidates. This establishes the chosen baseline miss; it is not
evidence of model improvement. Mocked tests prove that a valid model refinement
would require new source-backed persistence and reopen checks, while a valid
rules duplicate cannot satisfy incremental acceptance.

## Windows and resource evidence

The last boot remained 01:52:56 Pakistan time, matching recovery. Bounded,
read-only queries found no new critical/error System event or Application
Error/Hang event since 02:20. This does not resolve the earlier 0x50 cause
or certify Windows/hardware stability. No raw crash dump was accessed.

Initial available physical memory was approximately 7.5 GiB and system commit
usage approximately 31%. The final read-only ownership snapshot recorded
7,110 MiB available (6.94 GiB) and 33.07% commit use, with a commit limit of
21,291,085,824 bytes. Initial free disk space was approximately 15.5 GiB on C:,
106 GiB on D: and 106 GiB on E:. Read-only Ollama preflight showed no loaded model.

The native monitor smoke check collected two valid samples: minimum available
RAM approximately 6.98 GiB and maximum commit ratio 32.79%. These are **offline
monitor readings, not memory measurements during model loading**. There is no
resumed load-time RAM minimum to report.

The intended gates were:

- At least 4.5 GiB available before loading.
- An additional conservative 8B allocation admission reserve of 6.75 GiB
  available, based on roughly 5 GiB model allocation plus the 1.5 GiB floor
  and 0.25 GiB margin.
- Independent physical-availability and system-commit sampling every 0.5 s.
- Abort below 1.5 GiB, at or above 85% commit, on invalid/failed sampling or a
  sample older than 2 s.
- Watch for another model/Python workload or new Windows errors; abort rather
  than continuing through fallback.

The monitor uses Microsoft's documented
[GetPerformanceInfo](https://learn.microsoft.com/en-us/windows/win32/api/psapi/nf-psapi-getperformanceinfo)
page counters, with
[physical availability and commit](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-performance_information)
recorded separately. Sample and query failures are fail-closed.

The experimental polling HTTP wrapper preserves the established JSON request,
byte limits and exact candidate validation. It polls response reads at most
every 0.2 s, checks cancellation and absolute deadlines, and retains an owned
reader handle through Connection:close. Corrected offline tests interrupted a
delayed response in **0.641 s**, verified normal JSON reception and absolute
timeouts, and verified handle cleanup. This wrapper is an experiment artifact;
it is not a new shipped production transport or a guarantee against kernel faults.

## Configuration planned, not exercised

The selected installed model was verified through literal-loopback read-only
Ollama APIs. No cloud API or new model was selected. The planned preload cap
was 150 s, informed by the historical 104.55 s load, counted separately from
extraction. Production extraction's existing maximum 60 s was not increased.
Planned extraction limits were 128 output tokens, 4,096 context, two threads,
temperature zero, seed zero and at most 16 proposals for one short source clause.
Planned keep_alive values were finite: 90 s for preload and the existing 30 s
for extraction. None of these generation settings were exercised in this run.

Cleanup would target only this experiment's model using Ollama's supported
[keep_alive:0 unload operation](https://docs.ollama.com/faq), following completed
or cancelled client work. No model was loaded, so no unload request was needed.
No unrelated process was closed, and the Ollama service was not stopped.

## Changed files and preservation

The recovered six files were snapshotted before edits. Comparing snapshot hashes
shows only providers.py changed during this resumption, for the consistent v4
prompt mapping. All five other recovered files remain byte-identical, including
the crash-recovery report. This new acceptance report is the additional
repository document.

The complete current uncommitted repository inventory is:

    src/oomp/understanding/providers.py
    src/oomp/understanding/engine.py
    examples/mind2_model_acceptance.py
    tests/test_mind2_model_acceptance.py
    tests/test_mind2_model_example.py
    docs/product-milestone-P21-crash-recovery.md
    docs/product-milestone-P21-model-acceptance.md

Provider diagnostics and the source-retraction result fix are preserved from
the preceding P2.1 work. The source validator, authentication, scope/principal
checks, privacy filtering, source spans, retraction/erasure and transactional
worker lease/fencing checks were not weakened. No schema migration occurred.
No private OOMP database, TRACE source/conversation or credential was accessed
or modified. Historical P2/Stage 9 benchmark outputs were not regenerated.

New ignored artifacts include the preserved snapshot, resource sampler,
polling HTTP wrapper, single-use controller, offline harness, process-ownership
diagnostics, numeric memory traces and result JSON/JUnit records. They remain
under the timestamped resumption directory above. The two failed offline socket
checks and first stopped controller result are preserved rather than relabelled
as successful runs.

## Offline checks and exact execution

Windows CPython 3.11.4. Execution was sequential; the offline test harness
blocked Ollama and external endpoints, allowing only test-owned ephemeral HTTP
fixtures. No model was called implicitly.

| Check | Result |
| --- | --- |
| Syntax and imports of changed Python files | Passed |
| Mocked-provider regressions | 14 passed, 9.12 s |
| Example/accounting regressions | 11 passed, 16.41 s |
| Source-span/privacy/role/replay/lease subset | 23 passed, 6.89 s |
| Total pytest subset | **48 passed, no failures/errors/skips, all runs exit 0** |
| Resource-gate/cancellation/native-monitor checks | Six passed; zero Ollama connections |
| Guarded normal-JSON/deadline/cleanup checks | Two passed; zero Ollama connections |
| Process-ownership pure checks | Six passed, plus read-only live metadata confirmation |

Exact commands were run from the repository root, individually/sequentially:

    .\.venv\Scripts\python.exe .test-artifacts\product-P21-resume-20261029T215903Z\offline.py syntax
    .\.venv\Scripts\python.exe .test-artifacts\product-P21-resume-20261029T215903Z\offline.py provider
    .\.venv\Scripts\python.exe .test-artifacts\product-P21-resume-20261029T215903Z\offline.py example
    .\.venv\Scripts\python.exe .test-artifacts\product-P21-resume-20261029T215903Z\offline.py boundaries
    .\.venv\Scripts\python.exe .test-artifacts\product-P21-resume-20261029T215903Z\guard_selftest.py
    .\.venv\Scripts\python.exe .test-artifacts\product-P21-resume-20261029T215903Z\http_smoke.py
    .\.venv\Scripts\python.exe .test-artifacts\product-P21-resume-20261029T215903Z\controlled_run.py --run
    .\.venv\Scripts\python.exe .test-artifacts\product-P21-resume-20261029T215903Z\inspect_python_ownership.py
    .\.venv\Scripts\python.exe .test-artifacts\product-P21-resume-20261029T215903Z\ownership_check.py

The controller command above stopped at preflight; it made zero generation
requests. Its one-use sentinel intentionally prevents rerunning that ledger.
Do not delete it to force another attempt. A setup command initially encountered
a shell-quoting error before tests; a file-based setup script corrected it.
No product failure or test result is attributed to that command.

offline-summary.json, verified-summary.json and controlled-result.json aggregate
the passing subset, resource/ownership evidence, actual operation counts and
current source hashes. Individual pytest records contain the exact test nodes,
temporary paths and JUnit outputs.

## Historical findings, limitations and next step

The historical cold load of 104.55 s, compact generation of 19.50 s and
four-proposal run remain unchanged. That completed actual Mind run accepted
one rules duplicate, rejected three proposals and added zero incremental model
memories. No new result supersedes it.

The v4 prompt is offline-tested but still live-untested. The chosen corpus
labels are Codex drafts pending independent review, and this one selected case
would not establish broad extraction quality even if a later model attempt
succeeds. The earlier Python 3.12 installed-wheel snapshot remains stale relative
to the latest prompt. Full regressions, installed-package/lifecycle checks and
hosted CI for this uncommitted patch remain deferred by the current scope.

No BSOD fix, model success, superior benchmark score or release readiness is
claimed. After owner review, a newly authorized controlled attempt should use a
fresh timestamped directory, preserve the prior ledger, retain the corrected
strict process-ownership check, recheck Windows/resources, and retain the same
one-preload/one-generation/no-retry boundary. No smaller-model download or
system-setting change is implied. Work stops here; P3 is not started.
