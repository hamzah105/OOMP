# P4 preparation: context virtualization and recall

31 October 2026, Asia/Karachi. **Proposal for owner review; P4 is not implemented.**

## Verified baseline

- Local `main` and `origin/main`: `661e7b5ea8a5048c9da63b1ccd3515e7c9addc6a`.
- New local branch: `feature/p4-context-virtualization`, at that same commit.
- Accepted P3 integration tree: `ce5914021ff0e91a41537d65823f389519df5f28`.
- [Post-merge CI](https://github.com/hamzah105/OOMP/actions/runs/41178945077): all five jobs passed. This preparation did not rerun regressions or benchmarks.
- All 88 runtime modules match accepted Git contents and have identical parsed syntax. Existing `core.autocrlf=true` converted checkout line endings in 32 modules: 56 raw hashes match the previous worktree snapshot; all 32 differences are explained by LF/CRLF conversion. Earlier raw-hash evidence is preserved, not relabeled as a new test run.
- Eight frozen Mind 2 manifest entries and the P3 relocation fixture hash still match. Previous P2.1/P3 reports, the 1,000-event result, failed runs and integration evidence remain in place.
- TRACE was inspected read-only at `af202ef43daf70280d2e8915210816f788e8aff1`, on clean `main`. No host code, configuration, credentials or MongoDB data was changed or executed.

The complete five-milestone reference was read from `D:\Hamza\roadmap.md`, SHA-256 `70c8150e167c44fe1475957c0feb9e1d814f7d0ba33db0f679bb9ba1b517cc59`. Its historical schema-v5/no-model-extraction baseline is superseded by accepted P2.1/P3; its proposed P4 requirements remain the planning reference. The historical [ten-stage roadmap](roadmap.md) remains separate.

## Audit findings

| Area | Current implementation and P4 gap |
| --- | --- |
| Recall | [RetrievalEngine](../src/oomp/retrieval/engine.py) already combines scoped BM25, optional exact-space vectors, entity/topic lanes, RRF, bounded graph traversal, temporal governance and diversity. Add intent and episode/object selection around these mechanisms; preserve the existing retriever. |
| Navigation | [Object queries](../src/oomp/objects/queries.py) provide exact label/alias lookup, validated proofs, hierarchy, relations and history. The map is explicitly materialized, not automatically current or integrated into retrieval. Missing projection coverage cannot mean no memory exists. |
| Episodes | [Episode storage](../src/oomp/understanding/episodes.py) has extractive revisions, chronological source manifests and fingerprints. Summaries are not automatically Stage 5 retrieval items. Stale or retracted support must be revalidated before use. |
| Evidence | [Packing](../src/oomp/retrieval/packing.py) accepts whole memories and counts the serialized packet, including provenance. `token_budget` defaults to UTF-8 byte accounting, not an exact model tokenizer; the outer response and host prompt are outside that budget. |
| MCP | [Wire models](../src/oomp/mcp/contracts.py) are strict. Current tools expose canonical retrieval/expansion/source/status, not P3 navigation or a context planner. Raw source content requires `read_source`; read operations do not migrate schemas. |
| TRACE | Its committed integration/security guides, wire models and adapter were inspected. It sends the current question with `graph_depth=0`, validates a strict response and exact configured evidence budget, and independently checks Mongo owner/session/role/event identities. Its full latest-eight prompt is capped before retrieval. The actual fallback says an answer is absent from current-session memory; avoid repeating the roadmap's older wording as a literal current implementation. |

## Proposed OOMP design

1. **Separate, opt-in contract.** Propose a read-only `memory.context` tool with a versioned request/result, disabled for existing profiles until explicitly enabled. Keep `memory.retrieve`, its defaults, response fields and legacy TRACE behavior unchanged. Inputs contain a bounded question, optional recent referents/anchors, temporal selectors and budgets; tenant, namespace, principal, credentials and policy remain server-derived. No new write authority or default database migration is proposed.
2. **Bounded intent planning.** Deterministically distinguish fact lookup, prior discussion, change/history, decision follow-up, current-chat-only and ambiguous requests. Start with at most three query variants, four explicit anchors and two recent user turns totaling at most 2,048 UTF-8 bytes. Recent text is an ephemeral relevance hint, never persisted proof or an instruction. Ambiguous follow-ups request clarification rather than scanning all memory or inventing a referent.
3. **Reuse hybrid recall in one view.** Prepare any explicitly configured query embedding outside the database snapshot, then evaluate canonical, entity/topic, episode and exact object-anchor lanes in one consistent scoped read view. Introduce narrow internal snapshot adapters where needed; do not merge results from independently timed snapshots and treat them as one view. Share candidate, scan, graph, provider-call and deadline budgets across variants. Deduplicate by original memory/event/proof identity so multiple hierarchy paths do not count as independent evidence.
4. **Multi-resolution evidence.** Use relevant topic/episode snapshots for coarse selection, then expand selected objects into episode revisions, whole canonical claims and permitted source detail. Every derived unit carries its kind, revision/fingerprint, complete supporting IDs/references, attribution, uncertainty and temporal state. Revalidate current/as-of support; skip stale summaries with a disclosed reason and use valid underlying evidence. A summary is a derived view, not a new verified canonical fact. Never remove necessary proof to make a summary fit; choose a smaller independently supported unit or report exclusion.
5. **Explicit outcomes.** Distinguish `found_relevant_evidence`, `no_relevant_evidence`, `index_incomplete`, `coverage_unknown`, `unavailable`, `candidate_uncertain` and `budget_excluded`, with bounded coverage/degradation details. Authentication failure remains a boundary error without existence-revealing counts. An empty packed result with eligible candidates is a budget outcome, not no match. Missing/stale vectors or an unverified object projection cannot establish archive completeness.
6. **Preserve uncertainty.** Scores remain uncalibrated ranking signals. Preserve claimed, tentative, hypothetical, quoted, assistant-originated, disputed and superseded distinctions. Recent governed corrections can outrank history; a P3 `correction_review` association alone cannot supersede a claim. Preserve `known_at`/`valid_at`. Pack necessary conflicting alternatives as a complete uncertainty bundle or withhold a definitive answer when the bundle cannot fit. Do not infer sensitive affiliations from episode topics.

Initial ceilings should stay within existing limits: 4,096 query characters, 20 returned evidence units, 200 combined governed candidates, MCP graph depth <=2/nodes <=32/edges <=64/work <=400; existing lexical corpus/vector scan and P3 object/proof ceilings still apply. Multiple variants must not multiply those ceilings. A smaller elapsed-time budget must fit inside the host's configured total deadline. Semantic retrieval remains explicitly configured; missing providers retain existing fail/degrade semantics. Graph expansion stays opt-in until an ablation demonstrates benefit.

Capture one current/as-of policy time and propagate the same temporal selectors through every lane. Context reads must not build projections, refresh summaries, enqueue jobs, backfill events or mutate durable indexes. Incomplete projections produce disclosed fallback/coverage outcomes, not implicit maintenance.

Principal handling needs explicit tests: legacy canonical retrieval primarily authorizes tenant/namespace, while P3 objects include principal in their partition. The new context path must enforce grant-derived provenance/principal policy across every lane. Principal-less legacy records require an explicit trusted policy; do not infer a mapping from names or silently change v1 retrieval semantics. TRACE's documented reader/user/assistant grants share `trace-host`, but that must not become an assumption for other hosts.

## Later host work: separate TRACE authorization required

TRACE changes are proposed here only. Keep its MCP boundary, owner authentication, authoritative Mongo records, completion/publication policy, feedback workflow and signed ingest envelope intact.

- Replace the enabled-mode pre-retrieval latest-eight size rejection with a deterministic allocator over bounded, complete exchanges. Reserve fixed instructions, the current message, required feedback, output and safety first; select recent complete exchanges and compact older admitted session material extractively with source pointers and explicit omissions. Keep an impossible minimum request as a clear 413; never split a claim/negation or silently discard all recent context.
- Enforce both the serialized prompt-byte cap and `count(prompt) + generation_reserve + safety <= configured context allowance`. Declare the counting method; the current byte proxy is approximate. Allocate OOMP evidence from remaining capacity within configured ceilings; if none remains, skip retrieval with `budget_excluded`. A new client must validate against the actual per-request budget, rather than v1's fixed configured-budget equality.
- Negotiate the new tool explicitly and independently validate its version, packet accounting, summary manifests and every source/path proof against the real authenticated Mongo owner, session, role, exclusion and deterministic event identity. OOMP grant mapping remains primary authority; response labels are not signed scope attestations. Never import OOMP internals into TRACE or fetch arbitrary source locators.
- Distinguish disabled memory, successful empty recall, incomplete indexes, unavailable service and uncertain evidence in enabled-mode prompts. Keep historical evidence separate from recent utterances and application policy. Optional UI provenance should use natural concise disclosure, with internal identifiers reserved for requested inspection.
- Add a functioning second generic Python MCP host example using synthetic owner-linked records and independent wire validation. Give it separate grants/workspace by default; shared names cannot merge host identities.

## Delivery order and likely paths, after approval

| Step | Reviewable change |
| --- | --- |
| 1 | Freeze a new synthetic P4 fixture/gold annotation version, baseline measurements and contract/security cases. Do not overwrite Stage 9, Mind 2 or P3 results. |
| 2 | Add proposed `src/oomp/context/` contracts/planner/selection/packing modules; make only necessary internal read-session changes in retrieval/object queries. Start lexical/rules-only with schema v6. |
| 3 | Add opt-in MCP models/service/tool wiring and a generic host example; prove the old client and old tools remain compatible. An index or schema extension requires a separate justified migration design before implementation. |
| 4 | Add `tests/test_context_*.py` and a distinct `benchmarks/context/` fixture/configuration/report area; validate budgets, uncertainty and lane ablations before enabling additional lanes by default. |
| 5 | With separate TRACE approval, update `chat_orchestrator.py`, `oomp_context.py`, `oomp_client.py`, `oomp_contracts.py`, necessary config, host tests and integration docs. Keep current chat response/publication behavior compatible. |

## Synthetic evaluation and acceptance

- Use a development three-session replay plus separately reviewed held-out histories: S0 project; S1 alias/preference, robot plan, tentative relocation/options/criterion, topic drift and corrections; S2 specific and vague recall/history questions. Include unrelated questions, unknown pet name, political-topic-only recall and assistant/quoted/hypothetical negative controls. No real conversations or private database copies.
- Compare the unchanged current retriever, flat lexical/latest-eight baselines and proposed P4 under identical persisted inputs, questions and budgets. Separate intent, episode, object/graph and allocator ablations. A deterministic embedding stub proves mechanics only; real semantic quality requires a separately authorized provider evaluation.
- Report query-level source Recall@budget, provenance fidelity, abstention/false positives, temporal correctness, selected/dropped/expanded evidence, prompt and packet bytes/counting units, p50/p95 latency, RAM/CPU/disk and failure denominators. Test long-session recovery and impossible single-message rejection, including Unicode and proof/wrapper overhead.
- Require zero cross-owner/principal disclosures, no fabricated/invalid accepted proofs and no budget overflow. Exercise retraction/erasure, stale summaries/vectors, wrong credentials, mutated manifests, timeouts, cancellation, prompt injection, duplicate paths and a conflict bundle that cannot fit.
- Pre-register relevance/answer-quality thresholds after baseline measurement and before held-out tuning; do not worsen abstention/false-positive rates. Mocked answers cannot establish real answer-quality gains. A real cross-session answer-quality exit claim remains pending separate safe host/model authorization; preparation or offline mechanics alone cannot certify the full roadmap outcome.

## Preserved safety and stop boundary

No inference, preload, embedding request, download, host execution, profile migration, database operation, benchmark run or regression suite was performed for this preparation. Only this planning document is added; no runtime code is changed or published.

Future offline validation must retain the model/network-access guard, short fresh disposable roots, separate result/ledger directories, sequential focused tests before complete Python 3.11 then 3.12 suites, and resource/process/cancellation monitoring. Stop on instability, uncertain ownership, failed/stale monitoring or cancellation, available RAM below 1.5 GiB, or commit use reaching 85%. Do not automatically retry a failed experiment. Any separately approved model preload must also pass the existing 6.75 GiB RAM-admission reserve; never weaken it to run P4.

These monitoring controls are experimental-harness safeguards unless separately implemented and tested as runtime features. The earlier BSOD cause remains unidentified; the owner-confirmed manual restart is not evidence of a spontaneous crash. Preserve all previous ledgers, stopped/failed records and frozen measurements. Owner review is the next step; implementation, TRACE edits, live-model acceptance, commit/push/merge and P5 remain outside this preparation.
