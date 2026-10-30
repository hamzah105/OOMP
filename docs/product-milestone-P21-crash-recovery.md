# P2.1 interruption and Windows crash recovery

30 October 2026, Asia/Karachi. **Recovery is complete; real-model acceptance
remains unproved.** The owner's emergency recovery request supersedes the
interrupted [Issue #2](https://github.com/hamzah105/OOMP/issues/2) experiment.
No generation, model loading, full regression suite or benchmark was resumed
during recovery. Work stops here for owner review.

## 1. Git state after restart

- Repository: D:\Desktop\OOMP.
- Branch: feature/mind2-p2-review.
- HEAD: 248fecc851f6e0eb5335790cb79a8f6d40110a90, unchanged.
- Initial recovery status: two modified tracked files and three new files.
- git diff --check passed; Git emitted ordinary LF-to-CRLF notices.
- No reset, checkout, clean, stash, commit, push, merge or publication occurred.

The existing PR's [Actions run 40950580457](https://github.com/hamzah105/OOMP/actions/runs/40950580457)
passed Windows/Ubuntu Python 3.11/3.12 and distribution checks for committed
baseline 248fecc. Those results do **not** validate this uncommitted P2.1 patch.

## 2. Recovered implementation

| Recovered path | Existing unfinished change |
| --- | --- |
| src/oomp/understanding/providers.py | Remove schema duplication from prompt text; clarify classification fields; numeric attempt diagnostics; separate empty/truncated/invalid output codes; check call/circuit budgets under the request lock |
| src/oomp/understanding/engine.py | Report source_retracted when withdrawal prevents a commit during inference |
| examples/mind2_model_acceptance.py | Explicit synthetic rules/model comparison with durable jobs, exact evidence, reopen verification and incremental-proof acceptance |
| tests/test_mind2_model_acceptance.py | Mocked provider, fallback, validation, retraction, accounting and resource-bound regressions |
| tests/test_mind2_model_example.py | Mocked acceptance, duplicate, unavailable-service and explicit warmup accounting checks |

All five files were copied with hashes to the ignored task directory
.test-artifacts/product-P21-20261030/recovery-preserved/. Its working-tree.patch
preserves the tracked diff; the three new files are preserved as files.
Subsequent verification confirmed all five source files still match that snapshot.
No product source changes were necessary during recovery.

The reviewed patch preserves independent source/span/role validation, privacy
preflight, deterministic fallback, immutable evidence and transactional
source/lease/fencing checks. Extraction still has a maximum 60-second deadline,
one outstanding provider request, bounded context/output/bytes, a circuit breaker
and a 1,000-call provider-instance budget. No schema migration was introduced.
These conclusions are a focused review and small regression result, not full
release acceptance.

## 3. Incomplete and superseded artifacts

The initial inventory found 47 task artifact files; inspected JSON files parsed
successfully. No damaged Python syntax or unresolved source conflict was found.
Existing generated files were retained.

- live-procedure/ contains interrupted synthetic rules/model storage with no
  final acceptance.json. It supplies no completed acceptance result.
- live-four-explicit-fields/ also lacks a final acceptance.json. The revised
  field-clarification prompt has no verified completed live result.
- live-four-warmup/acceptance.json is a complete **failed** incremental acceptance
  run. Its result is preserved unchanged.
- acceptance:true files under model-example-tests*/ were generated with
  mocked HTTP replies. They are regression fixtures, not real-model success.
- dist/ and prepare312/ contain a pre-interruption wheel and offline Python
  3.12 installation. Comparing its recorded 79-module hashes with current source
  finds one mismatch: understanding/providers.py. That package snapshot predates
  the last prompt edit and must not be used as current-source acceptance evidence.
- No completed P2.1 full-suite result was found or claimed. The separate original
  P2 report records historical full-suite results.

Recovery harness failures and successful retry outputs are retained separately.
Fresh test output/temp paths prevented overwriting earlier test artifacts.
No old synthetic database was opened to reconstruct missing inference counts.

## 4. Preserved model findings

These are **pre-recovery** observations, not new recovery experiments.
The installed service reported Ollama 0.40.13 and Llama 3 8B Q4_0,
llama3:latest, digest:

365c0bd3c000a25d28ddbf732fe1c6add414de7275464c4e4d1c3b5fcb5d8ad1

No model download was performed.

| Preserved observation | Measured result |
| --- | --- |
| Tiny generation request, eight-token cap, 60-second deadline | Timed out before the first token |
| Longer, bounded loading diagnostic | 108.03 s total; load 104.55 s; prompt evaluation 1.94 s; generation 1.00 s |
| Original prompt with duplicated schema | Timed out at 60.02 s with no streamed token observed |
| Compact structured request after loading | 19.50 s total; first token 1.81 s; 48 output tokens; structured reply returned |
| Completed four-event actual Mind comparison | Four generation calls and four proposals; one accepted duplicate; three rejected; zero refinements; zero incremental model proofs |

The four fixed cases were a tea preference, a numbered-steps request, a claimed
alias and an assistant statement. In that completed run, extraction deadlines were
60 seconds, output cap 128 tokens, context 4,096, threads two, temperature zero,
seed zero and keep_alive 30 seconds. An explicitly requested empty-prompt preload
was recorded separately at 60.83 seconds; it supplied no extraction proposal.

| Event | Generation elapsed | Accepted / rejected | Current-event result |
| --- | ---: | ---: | --- |
| Preference | 42.34 s | 1 / 0 | extraction_completed; equal to rules output |
| Response-style request | 18.89 s | 0 / 1 | model_candidates_rejected |
| Claimed alias | 19.31 s | 0 / 1 | model_candidates_rejected |
| Assistant statement | 17.78 s | 0 / 1 | model_candidates_rejected |

An inspected synthetic diagnostic reply confused predicate and category
(project/procedural). This motivated the final prompt-field clarification;
validation was not weakened. That clarification remains live-untested.

Cold loading is a measured timeout bottleneck. Structured generation is possible,
but valid incremental extraction is not established. Prompt caching, service
version changes and available RAM affect timings; these observations are not a
controlled performance or model-quality benchmark. The original frozen P2
benchmark and Stage 9 results were not overwritten.

## 5. Windows crash evidence

Read-only inspection covered System events between 00:30 and 05:00 Pakistan time
on 30 October, and a bounded Application-error query.

- WER SystemErrorReporting event 1001 at 01:53:30 reports bugcheck 0x00000050.
- Kernel-Power event 41 at 01:53:11 records decimal BugcheckCode 80, also 0x50.
- Event 6008 records an unexpected previous shutdown at 01:30:26. Reboot/log
  timestamps and the owner's approximate 01:40 estimate differ; the exact moment
  and active workload must not be inferred from the estimate alone.
- WER says a dump was saved at C:\Windows\MEMORY.DMP. The recovery metadata lookup
  returned PathNotFound. C:\Windows\Minidump exists, but listing its files was
  denied. Individual dump existence/timestamps could not be verified.
- No dump was opened, copied or uploaded.
- Additional events include RealtekWlanU failing to start because a file was
  missing, a Defender service termination at 02:00, an Application Error event at
  01:59:53, and TPM/DCOM entries. They do not establish the BSOD's cause.
  Defender was subsequently confirmed Running.

Microsoft describes 0x50 as an invalid system-memory reference and lists several
possible software, driver, storage and hardware causes. A stop code alone does
not identify the failing component. See Microsoft's
[0x50 debugger reference](https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/bug-check-0x50--page-fault-in-nonpaged-area).
No faulting driver or hardware defect was identified here. The reported Codex
gray screen was not reproduced or assigned a cause.

## 6. Resource and stability observations

The workstation has an Intel i5-4690, four cores/four logical processors and
approximately 11.95 GiB usable physical RAM. Recovery began with approximately
4.85 GiB free; after the example tests approximately 4.91 GiB was free.
No further freeze or resource exhaustion was observed during these small checks.
This is not a hardware stability certification.

Automatic pagefile management is disabled. Read-only WMI reported allocations
of 5,632 MiB on C: and 2,432 MiB on E:, with current usage four and 68 MiB
respectively. This snapshot cannot establish pre-crash commit pressure.
Free disk space was approximately 15.50 GiB on C:, 106.22 GiB on D: and
106.58 GiB on E:.

The NVIDIA GT 620 reports 1 GiB VRAM, driver 23.21.13.9135 and WMI status OK.
nvidia-smi was unavailable. No GPU diagnostic or stress test was run.
Earlier Ollama metadata reported zero VRAM allocation for the model; a historical
free-RAM sample fell to about 0.50 GiB during model loading. This is evidence of
limited headroom during that experiment, **not proof that resource pressure
caused the kernel fault**.

At the initial recovery check there was no Python process or llama-server runner.
Only idle Ollama processes were present (PIDs 9020 and 12220, approximately 35 and
18 MiB working sets). Larger observed processes were Code, Chrome, Defender and
memory compression. No unrelated process or service was terminated.

## 7. Safe work completed during recovery

Preserved the patch and new files; inspected source and task artifact integrity;
collected bounded system/event/dump-metadata observations; checked current
processes, RAM, pagefiles, disks and GPU metadata; and ran small offline checks.
The only new repository document is this report. Additional recovery scripts,
snapshots, JSON and JUnit evidence remain in the ignored P2.1 artifact directory.

System settings, drivers, registry, pagefiles, credentials and private storage
were not changed. TRACE source and conversations were not accessed. No repair,
rebooting diagnostic, model service startup, model download or new LLM request
was performed during recovery.

## 8. Lightweight offline validation

Windows CPython 3.11.4, using the workspace environment. Execution was sequential.
A recovery-only harness allowed connections solely to ephemeral localhost HTTP
servers created by these tests; it blocked port 11434 and other endpoints.
Only isolated Python snapshot-reader subprocesses were permitted. Example tests
mock both provider and transport calls, including the optional warmup request.

| Check | Result |
| --- | --- |
| Five changed Python files: AST syntax and imports | Passed |
| New mocked provider tests | 14 passed, 9.33 s |
| New synthetic example/accounting tests | 11 passed, 16.68 s |
| Selected existing provenance/privacy/role/lease/timeout checks | 11 passed, 5.97 s |
| Total completed tests | **36 passed; zero failures/errors/skips; all three runs exited 0** |
| Real Ollama connections during completed runs | **Zero** |
| Unexpected network/process attempts during completed runs | **Zero** |

Coverage includes malformed and truncated JSON, empty proposals, timeout and
unavailable codes, accepted rules duplicates, independent candidate rejection,
exact reopened evidence, secret/injection exclusions, scope/principal rejection,
assistant attribution, retraction during inference, cancellation, expiration,
erasure, replacement leases and absolute slow-drip deadlines.

Exact recovery commands, from the repository root, were:

    .\.venv\Scripts\python.exe .test-artifacts\product-P21-20261030\recovery_offline.py syntax
    .\.venv\Scripts\python.exe .test-artifacts\product-P21-20261030\recovery_offline.py provider
    .\.venv\Scripts\python.exe .test-artifacts\product-P21-20261030\recovery_offline.py example
    .\.venv\Scripts\python.exe .test-artifacts\product-P21-20261030\recovery_offline.py boundaries

The harness records exact pytest node selections, unique temporary paths and
JUnit paths. recovery-verification.json aggregates their results and hashes.
Initial harness attempts encountered two harness-only problems: a Popen guard
conflicted with optional plugin import, then the guard prevented JUnit's Windows
hostname/version query. These are preserved in recovery-harness-initial.json
and recovery-harness-junit.json. The corrected harness preserves Popen as a class,
disables unused plugin autoload and uses a non-identifying JUnit hostname.
Those attempts are not counted as successful test runs or product failures.

## 9. Deliberately not executed

No real Ollama generation/chat, warmup, loading of another model, full 682-plus
suite, 240-turn model benchmark, concurrent test run, Python 3.12 suite,
package rebuild, lifecycle service launch, GPU benchmark, hardware stress test,
disk repair, driver installation, memory diagnostic or crash reproduction.
The ordinary P2 lifecycle and full regression release gates remain outstanding
for the changed patch. Hosted CI for the uncommitted patch is also outstanding.

## 10. Current acceptance status

The implementation is preserved and passes the selected offline checks.
The runtime prompt-field clarification and latest live run are unfinished.
The completed real-model run demonstrates generation and one independently
validated duplicate, **not a persisted incremental model-generated memory**.
Fallback output and mocked acceptance:true artifacts cannot close Issue #2.
The requested full P2.1 model-acceptance report remains deferred.

## 11. Memory-safe future strategy and operator actions

1. Review this report and the recovered diff. Keep routine operation on the
   already-supported deterministic rules path while model work is suspended.
2. Investigate the confirmed OS fault and post-reboot Defender termination
   locally with a qualified operator. Verify dump availability/permissions and
   assess driver, RAM and storage evidence before selecting a remedy. Crash dumps
   may contain sensitive memory; analysis or sharing requires a separate decision.
3. Confirm stable normal operation and sufficient memory headroom before
   authorizing more intensive testing. No settings or diagnostic reboot is
   implicitly authorized by this report.
4. Explicitly authorize any future inference and full regression resumption.
   Schedule only one bounded synthetic request at a time with no competing
   benchmark/test process, record load separately from inference, monitor host
   memory/commit and abort on renewed instability. Do not raise production
   extraction deadlines to mask slow loading.
5. Reconcile the stale Python 3.12 wheel with the approved source before later
   installed-package validation. Then run the deferred full/lifecycle gates.
6. If 8B remains impractical, consider a smaller generation model only after
   separate download approval. It is an untested alternative, not a measured
   remedy or an acceptance claim.

The existing synthetic helper's optional bounded preload is a manual experimental
facility, not an automatic readiness policy or daemon. It was not invoked during
recovery and is not authorization to resume loading. P3/P4 remain outside scope.
No further model execution or full-system benchmarking proceeds without owner
review and renewed explicit authorization.
