# P4 Phase A implementation and validation

1 November 2026, Asia/Karachi. **OOMP-only implementation, offline regressions and installation validation completed for owner review.** TRACE integration and chatbot answer evaluation remain Phase B. No publication is authorized or performed.

## Baseline and preserved history

- Branch `feature/p4-context-virtualization`; parent `661e7b5ea8a5048c9da63b1ccd3515e7c9addc6a`; accepted tree `ce5914021ff0e91a41537d65823f389519df5f28`.
- The untracked, unstaged [preparation plan](P4-implementation-plan.md) remains unchanged: SHA-256 `434b40a3b9221d6bbb4c11c61195699b21f6c05a02d7bac8a1dc8cad845ad5ef`.
- The complete authoritative roadmap was reviewed during preparation and its P4 section reviewed again: SHA-256 `70c8150e167c44fe1475957c0feb9e1d814f7d0ba33db0f679bb9ba1b517cc59`.
- Initial stop evidence remains at `.test-artifacts/product-P4A-stop-20261031T195851961Z/health-stop.json`; the original stop-only report is preserved at `.test-artifacts/p4a-20261031T223437722Z/initial-stop-report.md`.
- The owner confirmed that the shutdown preceding the **1 November 00:48 PKT boot was manually initiated**. Kernel-Power 41 (`BugcheckCode=0`) and EventLog 6008 remain unclean-shutdown evidence; they do not establish a spontaneous crash or BSOD. The earlier unexplained BSOD cause remains unresolved. No Windows settings/drivers were changed.
- Fresh validation evidence uses `.test-artifacts/p4a-20261031T223437722Z/`. Earlier recovery, acceptance, benchmark, failure and experiment records were preserved. An initial artifact-setup import failure is retained in `setup-initial-stop.txt`; it preceded tests/provider calls and was corrected in the artifact-only setup script.

## Implementation

The [architecture](context-virtualization-architecture.md) and [API](context-retrieval-api.md) describe bounded intent planning, source revalidation, optional P3 navigation and whole-unit packing. `src/oomp/context/` reuses existing lexical/semantic/entity/topic fusion, rank weights, temporal governance and graph proof policy through an internal shared-session/candidate seam. Query variants share one retrieval pass and optional configured embedding operation. No schema migration or generation provider was added.

The separate `oomp.context.v1` MCP tool is disabled by default. Enabling `context_enabled` exposes `memory.context` on the existing authenticated endpoint with existing `read` and optional `read_source` grants. Existing `memory.retrieve` models remain unchanged. No listener or write authority was introduced.

The context snapshot filters tenant, namespace and explicit source principal before ranking, statistics and candidate/scan ceilings. Unknown or mixed ownership is withheld. Legacy namespace-based retrieval policy is preserved. Canonical, object, episode and original-span checks share one authorized SQLite snapshot.

A valid source link/quote alone cannot prove an arbitrary paraphrase. Admission independently reconstructs supported deterministic canonicalizations or uses the existing literal candidate validator without constructing a provider. Manually attributed evidence must equal the complete original source. Current object labels/aliases require every supporting original span; summaries require reconstructed content, fingerprint and the exact stored source manifest. Conflicts form a complete supported bundle or are withheld. Retraction and knowledge/validity-time selectors remain active.

Evidence resolutions are object snapshots, validated extractive episodes, canonical facts and explicitly authorized source evidence. Packing counts the entire serialized evidence packet in UTF-8 bytes, retains whole claims/proofs and deduplicates original event/span identity. The inherited `token_budget` name denotes conservative byte accounting, not exact tokenizer counts. The outer response and host prompt/generation reserve are outside that budget.

Vague unresolved and current-session-only requests avoid archive scans. Outcomes distinguish no match, uncertainty, incomplete indexes/coverage, unavailability and budget exclusion. Political discussion cannot establish affiliation. Static reason codes and numeric counters avoid ordinary raw-query logging; plan inspection is opt-in. Source content remains untrusted data.

## Changed files

- `src/oomp/context/{__init__,contracts,planner,engine,packing,validation,navigation}.py`.
- `src/oomp/retrieval/engine.py`, `src/oomp/storage/retrieval_store.py`.
- `src/oomp/mcp/{configuration,contracts,service,server}.py`.
- `tests/test_context_*.py`, frozen `benchmarks/context/`, `examples/context_recall_quickstart.py`, its fictional fixture/README.
- `.gitattributes`, `MANIFEST.in` and the three P4A documents. P2/P3 measurements and implementation outside the listed compatibility seams are preserved.

## Offline validation

All phases use disposable synthetic storage, unconditional startup network/model guards and sequential execution. Preflight requires 4 GiB available RAM, commit below 75%, no other Python process, no new unexplained System error and no loaded model. The only Ollama interaction is bounded read-only **GET `/api/ps` inventory**. No generation, preload, embedding request, download or cloud call is permitted.

The experimental controller samples memory/commit every 0.5 seconds, checks sampler freshness/cancellation, polls Windows errors and bounds each phase. It can stop the known child process tree. These Windows test-harness safeguards are distinct from shipped cooperative runtime cancellation/deadlines; they do not resolve the previous BSOD.

| Phase | Verified outcome |
| --- | --- |
| Initial focused contracts/budget/MCP/security/source grounding (`focused01`) | 98 passed; 0 failures/errors/skips. JUnit 42.572 s; controller 44.578 s. Predates later navigation/summary-manifest additions. |
| Expanded focused `focused02` | 101 passed, 2 failed, 0 errors/skips; 84.663 s. Both new manifest fixtures assumed a high-budget summary would remain unexpanded. The packer correctly expanded it into whole canonical detail. |
| Corrected focused `focused03` | 108 passed, 1 failed, 0 errors/skips; 94.129 s. Manifest and coverage cases passed. The new foreign-graph admission fixture accidentally selected the same first memory for both endpoints; the existing P3 self-link guard correctly rejected it. |
| Exact failing case `focused04` | 1 passed, 0 failures/errors/skips; 2.146 s. Fixture now selects distinct memories by their exact synthetic source IDs. No runtime/security assertion was weakened. |
| Final nine-episode boundary `focused05` | 1 passed, 0 failures/errors/skips; 11.784 s. A ninth eligible episode now explicitly marks the eight-candidate summary search partial while all nine original proofs remain available. |
| Existing retrieval/P3/security/provenance regressions (`related01`) | 305 passed, 0 failures/errors/skips; 529.740 s JUnit / 531.735 s controller. This preceded only the final analogous context-summary cap signal/test; the existing retrieval, storage, MCP and P3 modules stayed unchanged. |
| Evaluation integrity tests (`evaltests01`) | 6 passed, 0 failures/errors/skips; 31.165 s JUnit / 32.750 s controller. |
| Initial frozen comparison (`evaluation01`) | All 120 records completed; all 10 aggregate registered gates passed; 36.110 s controller. Source data unchanged, schema v6. Subsequent per-query review found a functional alias relevance defect despite the aggregate pass. |
| Source quickstart (`quickstart01`) | Passed, including reopen; 25.765 s controller, zero model/real embedding calls. |
| Final focused (`focused06`) | 115 passed, 0 failures/errors/skips; 128.805 s JUnit / 130.781 s controller. |
| Final related compatibility/privacy (`related02`) | 43 passed, 0 failures/errors/skips; 40.111 s JUnit / 42.047 s controller. |
| Post-correction frozen comparison (`evaluation02`) | 120 completed records; all 10 registered gates passed; 37.687 s controller. The original comparison remains preserved. |
| Full Python 3.11.4 (`full311final`) | 888 passed, 0 failures/errors/skips; 1,019.140 s JUnit / 1,021.344 s controller. Complete final source snapshot. |
| Fresh Python 3.12.6 preparation (`prepare312fixed`) | Dependency check passed; all 95 runtime modules equal current source; 20.719 s controller. |
| Full Python 3.12.6 (`full312final`) | 888 passed, 0 failures/errors/skips; 1,109.531 s JUnit / 1,112.235 s controller. Same final source snapshot. |
| Current-source wheel/sdist (`buildcandidate02`) | Passed build, Twine, package-policy/content and all 95 runtime hashes; 19.219 s controller. |
| Core-only clean installation (`cleaninstall01`) | Four passed: wheel/sdist on both Python versions; 243.610 s controller. All dependency and 95-module before/after checks passed. |
| Installed MCP (`installedmcp01`) | Two fresh wheel/core environments: 15 tests each, 0 failures/errors/skips (19.931 s / 19.496 s JUnit); 159.531 s controller. MCP 2.3.0, with explicit reuse of existing optional dependency directories. |

Exact commands, source hashes, logs, JUnit where applicable, resource samples and health observations are preserved per phase. Historical incomplete/failed phases are not counted as passes.

Independent review also corrected coverage reporting for known object/canonical-graph truncation and invalid stored summaries, retained tentative assertion uncertainty after whole-unit expansion, and moved principal admission of existing-graph P3 relations before the edge page limit. Focused coverage verifies these boundaries. The final full suites must still cover the combined source snapshot.

The review service temporarily exhausted capacity during a read-only log inspection; that command was not executed. The already-running monitored regression completed successfully. After the owner's continuation, no Python process remained, the boot was unchanged, fresh health/resource/model-inventory preflight passed, and source comparison found only the two files in the reviewed summary-cap patch differed from `focused04`. The historical records were not reset or rerun.

The first complete-suite attempt (`full311`) was deliberately stopped by the agent after 294.593 s when per-query review showed an alias response dominated by project names. It is **incomplete, not a regression pass or Windows/resource failure**. Its supported cancellation-marker path emits the legacy code `owner_cancellation` regardless of initiator; the preserved `CANCEL-full311-agent-20261101T071721934Z.json` records the actual agent initiator and semantic-defect reason. Only the controller's owned test tree was stopped, and absence of remaining Python processes was verified before continuing. Logs, source snapshot and resource evidence remain unchanged.

The first `prepare312final` wrapper invocation rejected a malformed nested JSON command list before launching any child or running the packaging helper. Its directory, original malformed `pkg-*.final.json` files and `harness-command-rejection.json` are preserved. Corrected flat string arrays were produced from the original templates using JavaScript JSON parsing/serialization in new `pkg-*.verified-final.json` files. A fresh `prepare312fixed` phase then succeeded. This artifact-only correction does not invalidate the completed source regression.

Python 3.11 final monitoring: 2,005 samples, minimum available RAM 6,254,714,880 bytes, maximum commit 41.6579%, maximum sampling gap 0.547 s, no resource abort, no new System error and no offline-guard violation. The old harness module still records its 6.75 GiB preload constant, but no preload is authorized or performed; offline admission is the separately enforced 4 GiB / below-75% policy, with the preserved 1.5 GiB / 85% runtime test stop thresholds.

Python 3.12 final monitoring: 2,185 samples, minimum available RAM 6,105,337,856 bytes, maximum commit 41.8358%, maximum gap 0.562 s, no abort, new System error or offline-guard violation. All 95 current runtime modules were verified before the suite, and both completed controllers confirmed their complete watched Python source snapshots unchanged. The 888 cases comprise the accepted 767-case baseline plus 121 P4 cases; no test was skipped.

## Public-source and staging review

The bounded native audit inspected 304 public Git-listed files (4,301,291 bytes at audit time), with zero prohibited generated/private paths, links or high-confidence credential matches. Staging was empty; the preparation-plan hash remained unchanged; protected accepted P2/P21/P3 reports, benchmark sources/results, worker/understanding/object modules, migrations and authentication code had no Git changes. `.test-artifacts` was ignored and excluded. This is a finite public-source scan, not a forensic claim about private host data.

`public-review-audit.json` is preserved with its initial false status caused solely by a stale intended-path allowlist. `public-review-audit-clarification.json` records the authorized `tests/test_context_identity_relevance.py` addition and passes with no unexpected paths. `public-whitespace-audit.json` records clean tracked `git diff --check`, 20 clean new Python files and zero source mutations.

Before any packaging helper executed, static review found that isolated Python ignores the inherited bytecode environment flag. Explicit `-I -B` was added to every nested Python command in the artifact-only helper/probe, and their original versions were preserved under unique pre-bytecode-review filenames. Reused packaging dependency directories are supplied through plain path entries; prior environment startup hooks and executables are not launched. This correction changes no shipped runtime or tested Python source.

## Packaging and installed compatibility

The first build wrapper (`buildcandidate01`) stopped before source copying because its isolated HOME did not include the real user's Git trust entry for the sandbox-owned repository. Its logs, helper snapshot, fresh tool environment and failed result remain preserved. The correction uses a per-invocation `git -c safe.directory=D:/Desktop/OOMP ls-files` for this explicitly authorized read-only source listing. No global Git configuration, ownership, Windows setting, repository history or security assertion changed. The successful build uses a distinct `candidate02` label and fresh paths.

| Validated archive | Bytes / files | SHA-256 |
| --- | --- | --- |
| `dist-candidate02/oomp_memory-0.1.0-py3-none-any.whl` | 250,196 / 102 | `071c1dd2a39c0dd6b52f343eac1753010adbfef9922276d5e0d5c652ea352b6a` |
| `dist-candidate02/oomp_memory-0.1.0.tar.gz` | 811,674 / 311 | `b39ed2c904a8fc561d4fe3d70651cab159c5c76e0b63157afadf17d35a82946d` |

Evidence lives in `pkg-build-candidate02/`, `pkg-clean-clean01/`, `pkg-mcp-mcp01/` and their guarded controller phases. Both archives have Apache-2.0 metadata and all 95 current/tested runtime modules. The sdist also contains required P4 documents, the unchanged preparation plan, example/fixture and frozen setup hash sidecar; the wheel intentionally contains runtime rather than benchmark/test/example packages. Content checks found zero private/generated payloads or high-confidence credential matches; test environments, experimental databases/ledgers, model weights and crash dumps are excluded. Existing root `dist`, `build` and historical experiment records were not reused.

The four core installs are genuinely fresh environments, with dependencies installed offline from the existing wheelhouse. Actual versions are Python 3.11.4 / 3.12.6, Pydantic 2.14.1 and pydantic-core 2.50.1. Each confirmed MCP and TRACE backend absence, dependency consistency, all 95 installed module hashes before/after probes, **14 CLI checks**, **six context queries**, stable database reopen, pet abstention and zero model/real embedding calls.

The two optional-MCP environments have fresh wheel/core installations, then plain read-only path entries to existing compatible SDK dependencies. They are **not** a claim of newly resolved isolated extras. Both checked MCP **2.3.0**, dependency consistency, 95 module hashes, 14 CLI checks, six context queries/reopen, and **15 installed MCP/v6 compatibility cases**. Combined installation smoke is **84 CLI checks, 36 context queries and six reopen checks**; the 30 installed test executions are separate from the two complete 888-case source suites. No unexecuted check is included in these counts.

The installed archive contains the report snapshot from before installation results existed. A final **documentation-only** repack uses label `final03` so the completed report can be reviewed inside the sdist. Its archive identities and byte-equivalence certificate are kept externally at `pkg-build-final03/result.json` and `final-archive-equivalence.json` to avoid a self-referential report hash. The required certificate checks every wheel payload against the actually installed `candidate02` wheel, permits only this report to differ in sdist payloads, and binds all 95 runtime modules to current source and both successful 888-test snapshots. It does not substitute new untested runtime code for the installed artifact.

The smallest source correction distinguishes source-proved alias/profile claims from project-name words after canonical entailment validation. Independently re-proved P2.1 literal alias refinements remain admitted; intentional mixed-topic queries keep their OR semantics. Five independent regression cases passed (`identity01`: 18.444 s JUnit / 20.250 s controller). No original acquisition/provider/fallback code, query expansion, rank weight, gold, threshold or budget changed. Fresh final full-suite phases will have distinct names.

## Frozen evaluation

Before ranking implementation/tuning, v1 froze 15 fictional owned source turns, two foreign controls, three sessions, 12 queries, independent gold source identities, negative controls, budgets (6,000/1,200 plus one-unit exclusion), rank weights, lexical/mock-hybrid baselines and thresholds. A separately hashed setup supplement fixes real rules/Mind/P3 setup and consented fictional sensitive-topic episodes, without changing production defaults or original gold/configuration. See `benchmarks/context/README.md`.

The run used real disposable storage, rules-only durable Mind jobs and explicit P3 projection. All 51 claimed setup jobs completed, with zero failures, retries or lost leases, including the foreign control partitions. Mock vectors measure mechanics only. Labels are developer-authored and await independent owner review. No answer model was called.

**Initial implementation results, retained before the alias correction:** `.test-artifacts/e4-223437722-v1/{result.json,per_query.jsonl,setup.json}`; guarded command/resources are in `evaluation01/`. All 120 comparisons completed: five methods, 12 queries, two budgets. No inputs, gold, thresholds, weights or budgets were changed after results were observed. The functional relevance correction was motivated by this per-query review, so its follow-up must be identified separately rather than retroactively changing these numbers.

| Method | Budget | Source recall at budget | Evidence precision | Abstention | Latency p50 / p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Existing lexical | 6,000 | 0.6944 | 0.3913 | 0.3333 | 17.85 / 28.84 |
| Existing mock hybrid | 6,000 | 0.8611 | 0.4419 | 0.3333 | 23.27 / 40.46 |
| Context lexical | 6,000 | 1.0000 | 0.8571 | 1.0000 | 44.04 / 69.44 |
| Context mock hybrid | 6,000 | 1.0000 | 0.8571 | 1.0000 | 53.06 / 170.48 |
| Context graph-depth-one | 6,000 | 1.0000 | 0.8571 | 1.0000 | 44.79 / 69.92 |
| Existing lexical | 1,200 | 0.5556 | 0.5556 | 0.3333 | 17.90 / 33.38 |
| Existing mock hybrid | 1,200 | 0.3611 | 0.6000 | 0.3333 | 20.21 / 33.86 |
| Context lexical | 1,200 | 0.6944 | 1.0000 | 1.0000 | 44.19 / 65.91 |
| Context mock hybrid | 1,200 | 0.4722 | 1.0000 | 1.0000 | 52.26 / 75.86 |
| Context graph-depth-one | 1,200 | 0.6944 | 1.0000 | 1.0000 | 45.00 / 70.32 |

Recall is macro-averaged over positive-source queries; precision is micro-averaged over selected distinct source identities. The original frozen `required_six` label includes five positive cases plus the pet abstention case: the measured positive-required recall is **5/5 cases at 1.0**, not six positive recall denominators. All three abstention controls (pet/current-only/vague) passed for every context method/budget. Source Recall@8 counts the first eight distinct source identities **after packing**; it equals Recall@budget here and is not pre-packing candidate recall.

At the primary budget, context lexical episode-query source recall and temporal correction accuracy were both 1.0. At 1,200 they fell to 0.625 and 0.3333 respectively. Episode-query source recall does not itself prove that a summary resolution was selected; whole canonical expansion is permitted. All context methods had zero cross-scope sources, independently invalid proofs, duplicate original spans or packet overflows, and provenance fidelity 1.0 under the documented pair/reference/span policy. The primary context lexical packet maximum was 4,077 bytes (mean 1,931 including empty controls); constrained maximum was 1,181 bytes (mean 763.58). The one-unit budget test preserves honest exclusion.

These results show aggregate source-selection/abstention gains on this fixed fixture, with higher latency than existing lexical retrieval. They do **not** show universal byte reduction, real embedding accuracy or final-answer improvement. Remaining false positives are explicit: the alias query includes the two project naming sources; decision and referent each include the city background source. They account for four unwanted source selections and the 0.8571 precision. Small-budget context mock hybrid is worse than context lexical (0.4722 versus 0.6944 recall); it is not promoted as the default.

Legacy namespace-scoped baselines return same-namespace foreign-principal controls. The stricter P4 ownership evaluator counts those as cross-scope/invalid-proof results; this is **not** evidence of corrupted original spans or a newly introduced legacy tenant-boundary regression. The accepted legacy contract was intentionally not changed. All context paths enforce the stronger principal policy.

The depth-one ablation produced no quality benefit and no actual additional canonical/P3 association candidates in these unanchored cases. It is not a measurement of P3 graph quality. The separate exact-Lahore navigation regression proves bounded association mechanics with an incremental nonliteral plan source. Optional expansion remains off by default.

The evaluation used 34.410 s wall / 14.109 s process CPU including setup; final process RSS 43,188,224 bytes and lifetime peak 44,568,576 bytes. The indexed SQLite file remained 1,114,112 bytes after queries: **zero read-phase growth** and unchanged source-data fingerprint. There were 47 deterministic mock embedding calls, zero real embedding/model calls. One timed pass per query gives query-mix p50/p95, not a robust production performance study.

## Post-correction frozen comparison

Final retrieval evidence is separately identified at `.test-artifacts/e4-223437722-aliasfix01/{result.json,per_query.jsonl,setup.json}`, with guarded resources in `evaluation02/`. All frozen fixture/manifest/setup hashes are identical to the first comparison. The only functional correction between the comparisons is independently source-proved alias relevance; no ranking weights, gold, budgets, thresholds, provider behavior or original acquisition code changed. This is a disclosed post-review bug fix, not an independent held-out study.

| Method | Budget | Source recall at budget | Evidence precision | Abstention | Latency p50 / p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Existing lexical | 6,000 | 0.6944 | 0.3913 | 0.3333 | 18.04 / 28.67 |
| Existing mock hybrid | 6,000 | 0.8611 | 0.4419 | 0.3333 | 21.93 / 33.91 |
| Context lexical | 6,000 | 1.0000 | 0.9231 | 1.0000 | 40.12 / 69.18 |
| Context mock hybrid | 6,000 | 1.0000 | 0.9231 | 1.0000 | 49.09 / 74.64 |
| Context graph-depth-one | 6,000 | 1.0000 | 0.9231 | 1.0000 | 41.69 / 66.88 |
| Existing lexical | 1,200 | 0.5556 | 0.5556 | 0.3333 | 17.21 / 27.55 |
| Existing mock hybrid | 1,200 | 0.3611 | 0.6000 | 0.3333 | 19.73 / 33.40 |
| Context lexical | 1,200 | 0.6944 | 1.0000 | 1.0000 | 38.93 / 64.17 |
| Context mock hybrid | 1,200 | 0.4722 | 1.0000 | 1.0000 | 48.56 / 73.25 |
| Context graph-depth-one | 1,200 | 0.6944 | 1.0000 | 1.0000 | 41.81 / 67.22 |

All 120 calls completed and source data remained unchanged. The five positive required cases retain recall 1.0, as do the nine positive queries overall at 6,000. The alias query now returns **only `p4a-alias`**, with precision 1.0 and no project naming source. The remaining two unwanted source selections are city background for decision/referent; overall context precision is 24/26 = 0.9231. No context method produced a foreign-principal/tenant source, invalid pair/reference/span, duplicate original span or byte overflow. All three abstention controls passed at both budgets.

The earlier limitations remain: context mock hybrid is worse under the constrained budget, and the graph ablation yields no quality gain or additional traversal candidates for this fixture. The separately tested anchored P3 path demonstrates mechanics only. No default semantic/graph promotion is justified. Context lexical uses a maximum 4,077-byte packet, mean 1,797.42 including empty controls; the 1,200-byte run still has maximum 1,181 and mean 763.58. No universal compression or latency benefit is claimed.

Post-correction measurement: 36.197 s wall / 13.828 s process CPU including setup; final RSS 44,208,128 bytes and lifetime peak 44,212,224 bytes. The freshly created SQLite database was 1,126,400 bytes before and after queries (zero read-phase growth). Setup file allocation varies between disposable runs; this is not a claim of storage improvement over the first setup. There were 47 deterministic mock embedding calls and zero real model/embedding calls. Each per-query timer includes retrieval plus independent proof normalization/scoring; it is not isolated engine-only latency. These are one-pass query-mix samples and developer-authored source labels, not final-answer or production-quality evidence.

## Limitations and Phase B

- Intent/topic understanding is finite deterministic English. Bounded recent hints do not establish source authority. Object anchors are literal/case-sensitive; opaque-ID resolution is absent.
- Conservative principal attribution and canonical entailment can withhold custom/legacy records. Incomplete routes cannot establish complete archive coverage.
- Whole proof-bearing units can exceed small budgets. No real embedding or language-model quality is claimed.
- Cooperative cancellation/SQLite callbacks cannot guarantee interruption of a blocked optional provider call.
- Synthetic query-mix latency is not production throughput evidence. Historical benchmarks remain separate.
- Phase B requires separately authorized TRACE discovery/opt-in, strict new response/proof validation, authoritative ownership/span checks, adaptive full-prompt allocation, uncertainty/fallback behavior and cross-session answer evaluation. TRACE/MongoDB remain untouched.

For a bounded offline reproduction, choose a never-used phase name and use the existing guarded harness rather than a private profile. For example, from this checkout:

```powershell
powershell.exe -NoProfile -NonInteractive -File .test-artifacts/p4a-20261031T223437722Z/preflight.ps1 -Phase ownerrepro01
& .test-artifacts/q4a311-223437722/Scripts/python.exe -B .test-artifacts/p4a-20261031T223437722Z/run_phase.py ownerrepro01 --select tests/test_context_identity_relevance.py
```

Do not reuse an existing result directory. The fixed comparison command is documented in `benchmarks/context/README.md`; use a new output directory and the same offline/resource guard. The quickstart requires new disposable storage and refuses an existing directory. These commands require the local test-only environments; their startup guards/resource monitors are not shipped product features.

**P4 Phase A ready for owner review.** No commit, push, merge, release, TRACE/MongoDB/private-profile change, actual model generation/embedding request/download or Phase B/P5 work has been performed. The earlier unexplained BSOD cause remains unresolved; successful offline runs are not a claim that it was fixed.
