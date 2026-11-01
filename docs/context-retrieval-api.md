# Opt-in context retrieval API

P4 Phase A implementation reference. See the [P4A report](product-milestone-P4A-report.md) for exact offline regression, packaging and measurement status. This document does not claim TRACE integration or chatbot answer-quality acceptance.

## Compatibility and authorization

`memory.context` is a separate `oomp.context.v1` contract. Existing `memory.retrieve` arguments, output model, defaults and packet format remain unchanged. Existing server configurations default to `context_enabled: false`; the new tool is absent from discovery and calls receive the existing sanitized `not_found` error until explicitly enabled.

The tool uses the existing MCP endpoint, authentication, grant resolver, request/result limits and concurrency limiter. It adds no listener, credential, write capability or public transport. A server operator enables the tool; the authenticated grant still supplies tenant, namespace and principal. No such authority fields are accepted in tool arguments. All configured grants already require `read`; requesting original source detail additionally requires `read_source`. Ingestion approval, worker ownership/fencing and privileged erasure remain separate existing boundaries.

For an explicitly selected synthetic server configuration, opt in with the additional trusted configuration property:

```json
{
  "database": "ABSOLUTE_PATH_TO_DISPOSABLE_SYNTHETIC_DATABASE",
  "transport": "stdio",
  "context_enabled": true,
  "stdio_grant": {
    "grant_id": "synthetic-context-reader",
    "principal_id": "synthetic-owner",
    "tenant_id": "synthetic",
    "namespace": "context-example",
    "capabilities": ["read"]
  }
}
```

Initialize only disposable storage deliberately. Context reads do not initialize/migrate a database, materialize a P3 map, refresh a summary, enqueue a job, backfill events or repair an index. Current service admission still requires ready schema v6. Historical wire-status parsing does not authorize an older database upgrade. See [MCP integration](mcp-integration.md) and [security](mcp-security.md) for transport and credential provisioning.

## Request

The scope-free MCP model is `ContextArguments` (`ContextArgumentsFields` in the core package). Unknown fields are rejected. Proposed host adapters must discover and explicitly select this tool rather than changing the existing TRACE client implicitly.

| Field | Default and bound |
| --- | --- |
| `query` | Required nonblank text; at most 4,096 characters. |
| `recent_user_turns` | Empty; at most two nonblank turns, 2,048 UTF-8 bytes combined. Authorized caller-supplied relevance hints, never persisted source proof. |
| `anchors` | Empty; at most four explicit literal labels, each at most 160 characters. Hints must resolve inside the actual grant. Opaque object-ID resolution is not implemented in Phase A. |
| `token_budget` | 1,200; 1–32,768 UTF-8 accounting units. |
| `max_results` | 8; at most 20 evidence units. |
| `mode`, `allow_degraded` | `lexical`, `false`; semantic/hybrid require deliberate compatible-provider configuration or explicit supported degradation. |
| `candidate_limit` | 40; 1–200. Query variants share admitted work rather than multiplying the limit. |
| `min_semantic_similarity` | 0.2; uncalibrated ranking threshold, not truth probability. |
| `known_at`, `valid_at`, `as_of` | Optional offset-aware UTC timestamps. `as_of` aliases validity time; disagreement with `valid_at` is rejected. |
| `historical` | `false`; existing knowledge-time/validity semantics remain distinct. |
| `graph_depth` | 0; 0–2. Neighborhood expansion is opt-in. |
| `graph_nodes`, `graph_edges`, `graph_work` | 16/40/200; maximum 32/64/400. Existing storage/proof ceilings still apply. |
| `graph_relationships` | Existing supported relationship enum; at most nine filters. Similarity cannot invent governed relations. |
| `include_source_content` | `false`; an actual MCP `read_source` grant is also required. |
| `explain` | `false`; explicitly requests the bounded query plan. Ordinary responses and logs do not expose query variants. |

Example request, not a measured result:

```json
{
  "query": "What were we discussing about moving?",
  "token_budget": 6000,
  "max_results": 8,
  "graph_depth": 0,
  "explain": false
}
```

Deterministic intents are `factual_recall`, `episodic_recall`, `plan_followup`, `historical_correction`, `entity_lookup`, `current_session_only` and `uncertain_recall`. An unresolved vague referent cannot trigger an archive-wide scan. Current-session-only intent does not search historical storage. Topic hints remain discussion labels, never inferred nationality, affiliation or personal beliefs.

Neighborhood expansion is disabled by default. With a matching explicit exact label anchor, nonzero `graph_depth` and allowed relationship types, the context path follows source-validated P3 associations in the existing authorized read snapshot. The P3 walk uses the requested node/edge/work ceilings and knowledge/validity checks; protected backing graph edges also require the authorized actor. Its associated memories may be relevant without repeating the literal label, but must independently pass source validation. For such a request the P3 association lane replaces optional canonical-neighbor expansion rather than multiplying separate graph budgets. Without an eligible exact anchor, existing canonical graph policy remains applicable where requested. Required complete contradiction checks still apply at depth zero. These mechanics alone do not establish an evaluation benefit.

## Response and evidence units

`ContextResponse` returns `context_contract_version`, `retrieval_intent`, `retrieval_status`, `evidence_packets`, aligned `source_references`, `context_packet`, `selected_context_bytes`, `token_budget`, `counting_method`, `degraded`, bounded reason codes, coverage and numeric trace counters. `query_plan` is absent/null unless explicitly requested. The response always marks `source_data_untrusted: true` and `budget_scope: context_packet_only`.

Each `ContextEvidence` has an opaque `unit_id`, a resolution (`object_snapshot`, `episode_summary`, `canonical_fact` or `source_evidence`), whole `content`, up to 16 memory IDs and independently validated source proofs, optional object/revision/fingerprint identifiers, assertion/temporal labels, selection reasons, ranking score and derived/uncertain flags.

Each proof binds `memory_id`, `event_id`, the original `SourceReference` and exact Python Unicode-code-point offsets `span_start`/`span_end`. Its optional `quote` is omitted/null by default. Canonical evidence content remains readable evidence under the existing `read` policy; hiding raw quote detail does not mean the canonical claim itself is redacted. Explicit raw-source detail requires both the request flag and `read_source` at MCP. A trusted in-process caller is responsible for its own authorization before setting that flag.

Hosts must independently check their authoritative source ownership, source-system/role/event/session identity, span validity and exclusion policy before using received evidence. An object label, derived summary, similarity score or response scope label cannot authenticate a user or verify a claim. Original source locators are never fetched.

A valid quote/link alone cannot justify an arbitrary canonical paraphrase. The context path independently re-proves supported canonicalizations using existing deterministic acquisition rules and the literal source validator; that source-proof operation constructs no model provider. A manually attributed record is admissible only as a complete exact original source, with the fixed unverified-attribution metadata. A substring that drops a source's negation is not a substitute. Object snapshots are omitted unless every supporting event/span behind their current labels, aliases and status is admitted. Exact object-label lookup retains P3's literal/case-sensitive behavior; this is separate from lexical token matching.

For an identity/alias topic, final relevance requires a source-grounded `alias` predicate and `profile` category. `source_entails_memory` runs first; the gate then accepts deterministic source classification or an already independently re-proved P2.1 literal alias refinement. This preserves supported forms such as "My friends call me ..." without granting authority to unverified metadata. Generic project-name/rename occurrences of `name` or `called` cannot answer an alias-only question. Deliberate mixed-topic queries retain OR semantics, allowing independently relevant alias and project claims together.

Episode summaries require an existing revision whose content and source fingerprint still match eligible episode members. The bounded persisted `mind_summary_sources` memory/event manifest must exactly match that reconstructed support. Deleted or partial manifests cause the revision to be withheld; a read never reconstructs and trusts the missing manifest or writes a replacement.

Tentative assertion labels retain uncertainty across object snapshots, canonical bundles and source-detail upgrades. A compact view or expansion cannot establish that a proposed action happened.

## Outcomes, uncertainty and accounting

| Primary status | Meaning |
| --- | --- |
| `found_relevant_evidence` | Eligible source-grounded evidence was selected; read its uncertainty labels. |
| `no_relevant_evidence` | No admitted relevant evidence was found; not a claim that no historical data exists. |
| `index_incomplete` | A needed index/projection is incomplete; reasons describe the affected route. |
| `coverage_unknown` | Coverage cannot establish a complete result. |
| `unavailable` | Retrieval could not complete, including a bounded deadline/cancellation path. |
| `candidate_uncertain` | The request/evidence is ambiguous, tentative, disputed or otherwise insufficient for a definite claim. |
| `budget_excluded` | Eligible evidence did not fit the available packet budget; this is not no match. |
| `unauthorized` | Access denied. MCP uses existing sanitized authentication/authorization errors instead of returning scoped counts or evidence. |

`coverage` (`complete`, `partial`, `unknown`) and static `reasons` qualify the primary status. `trace` is limited to 32 nonnegative numeric counters, not raw questions or personal content. An explicit explanation exposes at most three query variants, four anchors, 32 focus terms, bounded topic hints and reasons. It is trusted diagnostic data and is not installed as model policy.

Known object-candidate truncation or invalid candidates use `object_candidate_coverage_incomplete` and partial coverage. Canonical graph truncation becomes numeric `canonical_graph_truncated: 1` with `canonical_graph_expansion_incomplete`; bounded P3 truncation also makes coverage partial. A `context_graph_limit` failure returns `index_incomplete`, partial coverage and no partial packet. An invalid persisted summary manifest, content or fingerprint uses `episode_summary_coverage_incomplete` and partial coverage. A valid summary omitted only because its support was irrelevant or unselected is a selection outcome, not index corruption; the diagnostic distinguishes invalid stored support from nonselection.

The `utf8_bytes_upper_bound_v1` counter measures the **entire serialized `context_packet`**, including complete units, all required proofs and its accounting wrapper. `selected_context_bytes` equals its actual UTF-8 byte length and cannot exceed `token_budget`. This inherited field name does not claim exact tokenizer counts. The outer MCP/JSON envelope, diagnostic plan and host prompt overhead are outside this packet budget; hosts must budget their full prompt and generation reserve separately.

Units are admitted whole or excluded. Expansion replaces a complete coarse unit only when the complete supporting detail fits; it cannot quietly remove negation, competing claims or necessary proof. Repeated paths to the same original event/span do not create independent source evidence. Empty evidence uses an empty-string packet and zero byte cost. Stale summaries, retracted support and unknown validity cannot silently become confirmed current facts.

## Local API and limits of Phase A

OOMP's trusted in-process API is `ContextEngine(path, provider=None, deadline_seconds=5.0, clock=..., cancelled=None).retrieve(scope, request)`. Local `ContextRequest` includes requested tenant/namespace; the separate validated `AuthorizedScope` remains authority. Constructing that value does not authenticate a remote user. The engine's bounded deadline and cooperative cancellation are not Windows RAM/commit monitoring or a guarantee of immediate cancellation inside another process/provider.

TRACE currently continues to call the unchanged v1 tool. Adaptive recent-prompt allocation, its dynamic evidence-budget validation, new summary/proof wire validation, truthful enabled-mode fallback and optional UI disclosure require separate Phase B implementation and approval. No TRACE changes or final chatbot answer-quality claims are included here. The [P4A report](product-milestone-P4A-report.md) records actual test/evaluation results, packaging status and remaining limitations.
