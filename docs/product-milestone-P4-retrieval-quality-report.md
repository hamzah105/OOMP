# P4 retrieval-quality correction: upstream typing stop

Status: **STOP FOR OWNER REVIEW — no retrieval or extraction runtime patch applied.**

The approved read-only investigation confirmed that the expected alias exists as source-backed episodic text, but was never correctly typed as a personal-alias claim. This triggers the assignment's explicit condition: “If the missing alias or another expected source was never correctly extracted, identify that upstream defect explicitly and stop for review before expanding into P2 extraction changes.”

## Baseline and inspection

- Local branch: `feature/p4-retrieval-quality`, created from clean OOMP main `d34bfbbbec44b0e016ddc41da1a7e27a45d45a68`.
- TRACE remains unchanged at `dcfda75325be0254232c1f1342601692ce18f937`.
- Existing measured acceptance: 123/130 assertions, 9/12 required scenario outcomes, recall 12/16 and precision 12/23.
- Actual fictional snapshot inspected: `D:\gr-1103205910\memory.sqlite3`, opened `mode=ro` with `PRAGMA query_only=ON`. Its 37 events, 55 memories and 55 source links were inspected. No original experimental source/private database was opened, no worker/extractor ran, and no index or fixture was rebuilt.
- Five frozen queries were diagnostically replayed through the accepted installed runtime. Instrumentation recorded actual lexical/ranked candidate IDs, ownership/temporal/source-entailment checks, relevance decisions, context units and final trace counters. This additional diagnostic work is not a retrieval-latency benchmark or a new MCP experiment.

Machine-readable evidence: `.test-artifacts/p4-quality-20261105T201740Z/results/persisted-source-audit.json`. Preserved successful live reference: `.test-artifacts/p4-final-20261105T195329Z/P4-acceptance-report.md` and `measured-results.json`.

## Confirmed upstream alias gap

The original user event is `trace-0eafc1816eadccefc434af6d79204a27335f18c6495c9e23d49dbe23d79e8787`. Its memory `mem-63e7cacc4518272c0ebf3c37487f8f50a75199eab12e809d7e7afcd677af351f` has the exact valid Unicode-character span `[0,56)`:

> In this fictional test, I use NOVA as my personal alias.

Persisted fields are `memory_type=episodic`, `predicate=stated`, `category=episodic`, `promotion=episodic-only`, `promotion_reason=low_salience_or_unsupported_form`, `canonicalization_version=p2.1`, `principal_id=trace-owner`. There is **no validated profile/alias memory for this source**. The `p2.1` version label does not imply that its predicate was refined to `alias`.

The actual classifier returns the same generic episodic fields. `understanding/rules.py` recognizes anchored forms such as “My alias is”, “Call me” and “I go by”; this source form does not match. The exact source is therefore stored, not lost, but the required alias semantics were not extracted.

The alias memory is present in both lexical and ranked candidates. Its owner, temporal state, source entailment and exact spans pass. It fails only the typed-identity relevance gate in `context/engine.py::_claim_relevant`, which requires a profile/alias classification or an independently validated P2.1 literal refinement. Existing identity-relevance tests deliberately preserve this distinction. A keyword-only exception here would hide the upstream gap.

The response preference and original relocation proposal also survive as generic `stated` episodic memories. Their source text is available, but the stored metadata does not identify a preference or prospective plan. This is another classification limitation; it does not mean these sources were absent from storage.

## Exact stage diagnosis of the five failures

| Failure | Persisted evidence and actual stage | Packing/ownership conclusion |
|---|---|---|
| Alias | The exact alias clause is stored and enters lexical/ranked candidates; source checks pass; typed-alias relevance rejects it. Seven eligible candidates become zero context-relevant memories. | Not a missing source, ownership/temporal rejection, or budget loss. Upstream alias typing is missing. |
| Continuity: preference | `Please keep your replies concise and use three bullets when a list is helpful.` is stored with a valid full source span. It is absent from both lexical and ranked candidates; direct source checks pass, but the current relevance predicate also rejects this wording. | Candidate-generation **and** relevance vocabulary gaps; no budget exclusion. |
| Continuity: relocation proposal | `I may relocate ... only a tentative plan.` and `I have not moved.` are stored. Neither enters lexical/ranked candidates. Both pass ownership, temporal, source-entailment and direct context relevance checks. | Candidate-generation failure; not filtered by ownership/temporal policy and not lost during packing. |
| Project-not-alias | Both the original project clause and `ORBIT42 is the project name, not my personal alias.` are stored and ranked. Source checks pass; an identity-only plan rejects them because they are not alias claims. Nine eligible candidates become zero relevant context memories. | P4 contrast/refutation intent gap, not absent evidence or packing. |
| Pet | Plan is `pet called`; the project clause matches the generic word `called`. Three eligible candidates become one context unit containing the unrelated project. | Relevance false positive; valid owner/proof does not establish relevance to a pet. |
| Foreign negative | Query includes pet/MISO and relocation. The plan selects the relocation topic; topic relevance accepts partial relocation evidence without satisfying the other query constraints. Nine eligible candidates become four relevant context units. | Authorized evidence only, but insufficient conjunctive/abstention handling; not foreign-owner leakage. |

Continuity's three-variant cap is reached after the primary query and the first two topic expansions, so later facets do not receive their own expansions. The generated terms lack `replies` and the proposal's `relocate`/`plan` wording. FTS token matching does not supply those morphological or semantic variants automatically. The imperative `Recap` is also incorrectly treated as an entity anchor; simply requiring every detected anchor would introduce another failure.

All five diagnostic responses have `context_budget_dropped=0`. Continuity produces and packs all seven context candidates. Missing expected source pairs are not the result of finite-packet packing.

## Before/after status

No candidate correction was applied or tested. The following **before** metrics are the unchanged measured live baseline, separately computed for raw, TRACE-accepted and final-selected user-source IDs; those three stages happened to have identical R/P. `—` means an undefined denominator, not a perfect score.

| Scenario | Before required outcome | Before R/P at each stage | After |
|---|---|---|---|
| project | PASS, with extra nongold sources | 100% / 33.3% | NOT TESTED |
| alias | FAIL | 0% / — | NOT TESTED |
| style | PASS | 100% / 100% | NOT TESTED |
| robot | PASS, with extra nongold sources | 100% / 33.3% | NOT TESTED |
| relocation | PASS, with extra nongold source | 100% / 66.7% | NOT TESTED |
| infrastructure | PASS | 100% / 100% | NOT TESTED |
| continuity | FAIL | 66.7% / 66.7% | NOT TESTED |
| unicode | PASS | 100% / 100% | NOT TESTED |
| political | Topic/proof policy PASS; answer quality unmeasured | 100% / 100% | NOT TESTED |
| pet | Policy checks PASS; relevance false positive | — / 0% | NOT TESTED |
| project-not-alias | FAIL | 0% / — | NOT TESTED |
| foreign | Isolation checks PASS; relevance false positives | — / 0% | NOT TESTED |

Aggregate before: raw **75.00% recall / 52.17% precision**; TRACE-accepted **75.00% / 52.17%**; final-selected **75.00% / 52.17%**. No after-improvement claim is made. The original 12 scenarios and 16 gold source/query pairs are unchanged.

## Work completed and stop boundary

- Completed: source/code review, new local branch, actual persisted-source inventory and five bounded diagnostic query replays. Source ownership, temporal eligibility and proof entailment were checked directly for each expected user-source memory. Snapshot main hash before/after remains `542489748f897369058b030de6d5a3f46a4de223e50a896006b9a6c1d39fac3e`.
- Changes: this report only in the product tree; diagnostic script/results in ignored `.test-artifacts`. No OOMP/TRACE runtime, extraction, scheduler, fixture or gold change.
- Validation: one successful read-only diagnostic execution, five instrumented queries; **no new product regression tests or full suites run**, because the upstream-stop condition was met before implementation. An initial diagnostic-output-directory failure and its source/logs were preserved; the corrected diagnostic passed. No actual model or MCP request occurred.
- Not started: paraphrase preregistration, candidate source patch, candidate package build/install, focused/regression suite, controlled candidate-runtime experiment, or second-host demonstration. The candidate live allowance has not been consumed.

Owner review is needed to resolve the scope boundary: whether to authorize a focused P2 extraction/validation correction for the demonstrated literal alias/preference/plan forms, or an explicitly designed source-discussion retrieval contract that does not promote untyped episodes into alias facts. Neither is silently included in this P4 patch. Any later controlled reprojection must be separately explicit; the existing frozen projection must not be repaired in place to manufacture a pass.

After that decision, P4 work should address bounded balanced query expansion, anchored contrast evidence and negative/conjunctive relevance, with separately preregistered paraphrases and independent negatives before a new single live candidate run. This is a proposed next scope, not implemented work.

Gate A remains incomplete. Gate C remains NOT TESTED. Gate B real-model evaluation remains NOT TESTED and separately approval-gated. The default multi-principal worker scheduling defect remains OPEN; the earlier manual enqueue workaround did not fix it. No commit, push, merge, inference, private data, deployment, release or P5 work occurred. Stop for owner review.
