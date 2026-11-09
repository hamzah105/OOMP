# Product roadmap: P1–P5

Updated **8 November 2026**. This is the maintained public product roadmap,
derived from the five-stage proposal prepared on **28 October 2026** and reconciled
against current source and dated implementation reports. It is separate from the
[original Stage 1–10 engineering history](roadmap.md), which remains unchanged.

Proposed targets are not measured results. Local acceptance, hosted CI, model
quality, independent usability and release decisions are different gates.

## Direction

**OOMP — Memory beyond the context window.**

Build a local-first memory layer that keeps expanding source history outside a
model's finite context, retrieves relevant attributed evidence and exposes how
objects, plans and discussions connect over time. OOMP does not increase a model's
native window, guarantee factual truth, reproduce human biology or promise
perfect recall. Models, SQLite storage and host applications remain independent.

| Milestone | Status | Evidence |
| --- | --- | --- |
| P1 · guided operation | Implemented and locally validated | [P1](product-milestone-P1-report.md), [startup validation](local-start-validation.md) |
| P2 / P2.1 · conversational understanding | Implemented; quality validation remains narrow | [P2](product-milestone-P2-report.md), [P2.1](product-milestone-P21-model-acceptance.md) |
| P3 · object-oriented memory | Implemented and validated at recorded snapshots | [P3](product-milestone-P3-report.md) |
| P4 · context virtualization | Implemented components; acceptance incomplete | [P4A](product-milestone-P4A-report.md), [final gates](P4-FINAL-ACCEPTANCE.md) |
| P5 · product/research validation | Submission-focused work implemented; broader gates pending | [P5](P5-SUBMISSION-REPORT.md), [readiness](SUBMISSION-READINESS.md) |

## P1 — Guided setup and owned lifecycle

**Scope:** installable CLI, read-only project discovery, explicit host/configuration
approval, private persistent profiles, distinct credentials, onboarding preview,
diagnostics and separately supervised MCP/Mind processes. Optional approved TRACE
publication stays separate from its independently owned API, MongoDB and Ollama.

**Implemented:** `onboard`, configuration, `up/status/logs/down/restart`, and
`start/stop` with a saved approved selection. The TRACE handoff uses private signed
references, preserves existing owner/grants and avoids repeated secret copying.
The current local two-terminal path has actual startup/health and focused tests.

**Remaining validation:** repeatable independent fresh-user installations,
accessibility/usability observations beyond exercised fixtures, additional host
support and broader platform validation of the newest startup patch. The
one-command workflow is not certification of arbitrary project auto-patching.

## P2 — Natural conversational acquisition

**Scope:** bounded source clauses, claims/preferences/plans, tentative and quoted
assertions, reviewable corrections, attributed discussion episodes, privacy
exclusions, optional provider proposals and independent source validation.

**Implemented:** deterministic fallback, optional explicitly configured local
Ollama extraction, exact spans, role/scope checks, durable Mind processing,
source-linked episodes and preview-first administrative reprocessing. Sensitive
discussion is not automatically promoted into personal beliefs or identity.

**Evidence:** P2 includes a frozen synthetic acquisition study whose labels are
drafts pending independent review. P2.1 passed one controlled real-model case:
one incremental source-grounded procedural memory survived persistence/reopen.
That result does not establish cold-load reliability or broad semantic coverage.

**Remaining gates:** independent annotation/adjudication, broader natural-language
and uncertainty coverage, controlled rules/model comparisons, resource/latency
measurement over representative workloads and reproducible provider quality.
No arbitrary external model API integration or automatic sensitive profiling is
claimed as implemented.

## P3 — Hierarchical objects and temporal associations

**Scope:** stable typed identities, source-backed aliases, many-parent navigational
hierarchies, typed graph links, episodic summary lineage, distinct knowledge/validity
times and bounded inspection. The hierarchy is a projection over a graph.

**Implemented:** additive schema v6, explicit projection/replay, source-proof
foreign keys, navigation from multiple paths to the same object, cautious identity
handling and trusted-local CLI inspection/export. Historical source/graph/worker
contracts remain in place. Object reads do not implicitly build a projection.

**Evidence:** the recorded full Python 3.11/3.12 snapshots each passed 767 tests;
the P3 report separates scale experiments, compatibility recovery, packaging and
publication checks. These are not a current full-suite count.

**Remaining limits:** no universal ontology, automatic semantic entity merge,
distributed graph backend or demonstrated million-node scale. Optional graph
expansion needs measured benefit rather than an assumption that more edges help.

## P4 — Context virtualization and host interoperability

**Scope:** bounded recall intent and query hints; lexical, optional semantic/hybrid,
entity/topic/episode signals; multiple evidence resolutions; source revalidation;
whole-unit budget packing; explicit uncertainty/failure states. TRACE adds adaptive
prompt allocation, authoritative provenance checks and truthful fallback states.

**Implemented:** opt-in `oomp.context.v1`, preserved legacy retrieval, principal-aware
context admission and a separate public generic MCP host. Evidence budgets count
UTF-8 packet bytes rather than exact model tokens. TRACE retains complete-source,
feedback and correction constraints within its own finite prompt allocation.

**Accepted local gates:** A passed 137/137 checks and all 12 frozen scenarios,
with source recall 16/16 and precision 16/18. C passed 18/18 independent-host checks.

**Incomplete gate B:** the bounded local-model answer evaluation returned 22
answers, one timeout and 41 unrun cases out of 64 planned. Five complete paired
cases scored 3/5 for both OOMP packet replay and flat lexical. Negative/held-out
answer controls were not reached. No answer-quality superiority or full P4 exit
is claimed.

**Remaining gates:** completed controlled final-answer evaluation, independent
answer review, meaningful negative/abstention and temporal accuracy, honest
latency/resource comparisons and broader host validation. The default
multi-principal shared-queue projection defect remains open; submission operates
one principal per dedicated namespace/profile. Legacy source reads retain their
documented tenant/namespace boundary.

## P5 — Reproducible product and research validation

**Scope:** reliable installation/upgrade/recovery, Windows/Linux CI, clean archives,
dependency and secret controls, usable documentation, independent pilot setups,
versioned benchmarks and evidence-based release decisions.

**Implemented submission work:** reviewed public examples and manual guides,
explicit context configuration, synthetic restart/provenance demonstrations,
wheel/sdist checks and four core clean installations. Dated reports distinguish
current focused checks, older regression snapshots and exact hosted CI commits.

**Pending full-roadmap gates:** independent fresh-user pilots; independently
reviewed answer labels; license/version-pinned public benchmark validation such as
LongMemEval; reproducible, controlled Mem0/Graphiti comparisons where comparable;
broader current-source platform checks; and separately authorized release/package
publication. Proposed setup-time or quality targets have not become guarantees.

## Rules that continue across milestones

- Preserve original sources, provenance and historical results; changes of mind
  are not implicit deletion or factual verification.
- Keep tenant/namespace/principal authority, consent, signed ingestion, retraction
  and privileged erasure boundaries explicit. Host applications own authentication.
- Remain local by default. Models and embeddings require deliberate configuration;
  no automatic weight downloads or undisclosed personal-text export.
- Bound providers, jobs, retrieval lanes, graph traversal and evidence packets.
  Scores and links are not probabilities of truth or permission to execute text.
- Separate synthetic, live, hosted and independent evidence. Report failures,
  missing controls and uncertainty instead of relabeling partial work as complete.
- Keep OOMP and TRACE independent. Public remote hosting, new storage backends,
  automatic identity migration and release/publication require their own review.

See [limitations](limitations.md), [security](security-model.md),
[release checklist](release-checklist.md) and [current submission readiness](SUBMISSION-READINESS.md).
