# Memory model

All contracts use Pydantic v2, reject extra fields, validate defaults and prohibit field reassignment. Evidence collections are tuples. Event, memory and retrieval metadata are recursively immutable snapshots and serialize as ordinary JSON objects/arrays. These domain values remain provider independent. Stage 2 persists MemoryEvent through a separate SQLite adapter; Stage 3 persists canonical MemoryNode values and conservative entity associations; Stage 4 supplies scoped graph persistence and structural/history inspection; public authentication remains unimplemented.

## Identity and scope

`Identifier` is a case-sensitive string of 1–128 ASCII characters. It starts with a letter or digit and then permits letters, digits, `.`, `_`, `:`, `-`. Empty strings, whitespace, path separators and automatic case/whitespace normalization are not accepted. Tenant, namespace, principal, event, node, edge, session, turn and idempotency identifiers use this policy. Tags are bounded identifiers too. External event/document identifiers permit other nonblank strings up to 512 characters because source systems may use different formats.

| Type | Fields | Meaning |
| --- | --- | --- |
| RequestedScope | `tenant_id`, `namespace` | Client's requested partition; untrusted authorization intent |
| AuthorizedScope | Same scope plus required `principal_id` | Trusted service supplies it after authentication and policy; construction alone proves neither |

A namespace belongs within a tenant. A principal is an actor, not a substitute for the tenant. Protocol methods carry explicit authorized scope. Stage 3 storage verifies existence and scope of every source/entity link; authentication and access grants require a trusted service; identifier validation alone cannot establish those facts.

## SourceReference

Required: `source_system`, `external_event_id`, `timestamp`. Optional: `session_id`, `turn_id`, `locator` (nonblank when supplied, at most 1024 characters). A document ID uses `external_event_id` rather than a separate ambiguous field. A locator can name an evidence span, page or URI; it is not fetched or executed.

Source references describe external origin. OOMP `event_id` describes an internal historical event. A node carries both internal source IDs and external provenance, enabling storage to resolve, audit and verify links. Stage 1 requires their presence but cannot verify their external truth or database consistency.

## MemoryEvent

Required: `event_id`, `tenant_id`, `namespace`, `event_type`, `source_type`, `content`, `source_reference`, `occurred_at`, `ingested_at`. Optional: `idempotency_key` (default null), `metadata` (default empty object).

Content must be nonblank and at most 1,000,000 characters; its original spacing is preserved. Metadata must be a JSON object with string keys and JSON-compatible nested values, including null. Explicit metadata null, executable objects and NaN/infinity are rejected. Input containers are copied into immutable snapshots; mutating the caller's input cannot revise source evidence. This value-level protection is supplemented by Stage 2 append-only storage and UPDATE/DELETE triggers. Privileged erasure remains future work.

| EventType | Required SourceType |
| --- | --- |
| `user_message` | `user` |
| `assistant_message` | `assistant` |
| `document` | `document` |
| `tool_result` | `tool` |
| `correction` | Any declared source type |
| `feedback` | Any declared source type |

`SourceType` also includes `system`. Corrections and feedback preserve who supplied them; they do not automatically become verified user truth. Assistant assertions remain generated content even when a later memory cites them. No trust score is invented.

Occurrence records when the source event happened; ingestion records when OOMP received it. Both are required and independent. Stage 1 imposes no ordering between them, allowing imported data and explicitly represented clock skew. Future ingestion policy must decide which clock anomalies to reject or flag. Stage 2 enforces idempotency within tenant and namespace and preserves the original ingestion time on an equivalent retry. See the storage guide for the exact logical fingerprint.

## MemoryNode

Required: `memory_id`, `tenant_id`, `namespace`, `memory_type`, `canonical_content`, `canonical_key`, `source_event_ids`, `provenance`, `created_at`, `updated_at`. Optional: `confidence`, `valid_from`, `valid_until` (all default null), `status` (default active), `tags` (default empty tuple), `metadata` (default empty deeply immutable JSON object).

`canonical_content` is nonblank, at most 1,000,000 characters. `canonical_key` is nonblank, at most 512 characters, with source text preserved. `source_event_ids` and `provenance` must each contain at least one item. A confidence, when measured, is a finite number in `[0,1]`; absent confidence remains null. It is not a retrieval score or proof of truth.

`MemoryType`: `episodic`, `semantic`, `profile`, `procedural`, `project_state`, `resource`, `decision`, `topic_summary`. All use the same identity/provenance/temporal envelope; Stage 3 deterministic extraction produces profile, project_state, semantic, decision and episodic values for documented constructions. The other types remain valid domain/store values without default extraction rules.

A node retains its persistent identity across graph views. Topic membership uses relationships, avoiding duplicate facts just because several projects need them. Stage 3 assigns a versioned scoped hash of conservative normalized content, memory type and attribution and enforces scoped canonical-key uniqueness. It merges equivalent records' evidence, preserving the first memory ID; conflicting content under one key is rejected.

`MemoryStatus`: `active`, `superseded`, `retracted`. Status describes derived state; it does not erase source events. Superseded records remain historical evidence. A current status alone cannot answer historical `as_of` queries: retrieval must use validity and relationship history, with a defined policy for retrospectively retracted evidence.

## MemoryEdge

Required: `edge_id`, `tenant_id`, `namespace`, `source_node_id`, `target_node_id`, `relationship_type`, nonempty `source_event_ids`, `created_at`. Optional: `confidence`, `valid_from`, `valid_until` (null), `status` (active).

`RelationshipType`: `ABOUT`, `RELATED_TO`, `PART_OF`, `DERIVED_FROM`, `OCCURRED_IN`, `SUPPORTS`, `CONTRADICTS`, `SUPERSEDES`, `DEPENDS_ON`.

An edge is directed from source to target. `SUPERSEDES` points from the newer node to the earlier node. Cycles and self-links are not universally forbidden; relation-specific structural constraints belong to later graph policy. Endpoints are canonical node IDs in this foundation. Additional graph entity kinds require explicit contracts later. Evidence IDs and confidence follow the same validation as nodes.

## Temporal policy

- Every supplied timestamp must be timezone-aware. Naive Python datetimes and naive ISO strings are rejected; no host-local timezone is guessed.
- Aware timestamps normalize to `datetime.timezone.utc`, preserving the instant. JSON output uses ISO 8601 with `Z`, including fractional seconds when present.
- `updated_at >= created_at` on nodes. `valid_until >= valid_from` whenever both endpoints exist, on nodes, edges and retrieval evidence.
- Validity is interpreted as a half-open interval `[valid_from, valid_until)`. Equal endpoints denote an empty interval. A null endpoint means unspecified/unknown, not an assertion of permanent truth; retrieval must define a policy for unknown bounds.
- Record creation/update times, real-world validity, source-reference time, occurrence and ingestion are separate concepts. Historical fields have no automatic current-time defaults.
- Frozen values should be replaced by newly validated records when derived state changes. Pydantic `model_construct` and unchecked `model_copy(update=...)` are trusted-programmer escape hatches, not validation or authorization interfaces; future external/service inputs must use validated construction.

## Superseded fact example

This example constructs schemas in memory only; it writes no database and performs no retrieval.

```python
from datetime import datetime, timezone
from oomp.domain.models import MemoryEvent, MemoryNode, MemoryEdge, SourceReference

jan = datetime(2026, 1, 10, tzinfo=timezone.utc)
feb = datetime(2026, 2, 15, tzinfo=timezone.utc)
scope = dict(tenant_id="tenant-demo", namespace="personal")
old_ref = SourceReference(source_system="chat", external_event_id="turn-1", timestamp=jan)
new_ref = SourceReference(source_system="chat", external_event_id="turn-2", timestamp=feb)
old_event = MemoryEvent(**scope, event_id="evt-1", event_type="user_message",
    source_type="user", content="I prefer Python.", source_reference=old_ref,
    occurred_at=jan, ingested_at=jan)
new_event = MemoryEvent(**scope, event_id="evt-2", event_type="correction",
    source_type="user", content="I now prefer Rust.", source_reference=new_ref,
    occurred_at=feb, ingested_at=feb)
old = MemoryNode(**scope, memory_id="mem-1", memory_type="profile",
    canonical_content="The user preferred Python.", canonical_key="preferred-language:jan",
    source_event_ids=("evt-1",), provenance=(old_ref,), created_at=jan, updated_at=feb,
    valid_from=jan, valid_until=feb, status="superseded")
new = MemoryNode(**scope, memory_id="mem-2", memory_type="profile",
    canonical_content="The user prefers Rust.", canonical_key="preferred-language:feb",
    source_event_ids=("evt-2",), provenance=(new_ref,), created_at=feb, updated_at=feb,
    valid_from=feb)
edge = MemoryEdge(**scope, edge_id="edge-1", source_node_id=new.memory_id,
    target_node_id=old.memory_id, relationship_type="SUPERSEDES",
    source_event_ids=("evt-2",), created_at=feb, valid_from=feb)
```

Both events remain unchanged. A future January-as-of lookup should consider the earlier validity; a current lookup should consider the newer evidence and supersession. The new node's unknown end does not guarantee the preference will never change. Use separate canonical keys for distinct assertions. The Stage 3 store rejects conflicting content under a reused key and does not implement automatic temporal supersession.

## Retrieval schemas

`RetrievalRequest` extends requested scope with nonblank `query` (at most 100,000 characters), strict integer `max_results` (default 8, range 1–100), strict integer `token_budget` (default 1200, range 1–32768), and optional UTC-aware `as_of`. Boolean, fractional, string, zero, negative and out-of-bound integer budgets/limits are rejected. Constants are Stage 1 safety limits; configurable server ceilings belong to later service policy.

`MemoryEvidence` contains `memory_id`, `canonical_content`, `memory_type`, required nonempty `source_references`, optional finite `retrieval_score` (null by default, metric range unspecified), temporal bounds, status, graph paths and JSON metadata. Scores and confidence have different meanings; schemas compute neither.

`GraphPath` contains nonempty `node_ids`, `edge_ids`, `relationship_types`. It requires `len(edge_ids) == len(node_ids)-1` and equal edge/relationship counts. A single-node path is allowed. This validates shape, not graph existence or authorized connectivity.

`RetrievalResponse` requires `retrieval_id`; memories, source references and graph paths default empty; strict nonnegative `estimated_token_count` defaults zero. An empty response is valid when there is no supported evidence or no whole evidence item fits the selected budget. The response has no generated-answer field. Stage 5 implements budget compliance, scoring, endpoint resolution and provenance checks. Its expanded fields and accounting boundary are documented in [retrieval](retrieval.md).

## Protocol boundaries

EventStore: scoped `append`/`get`/`list_events`/`count_events`; MemoryStore: scoped `put`/`get`/`find_by_canonical_key`/`list_memories`/`attach_evidence`; GraphStore: scoped `put_edge`/`edges_for`; EmbeddingProvider: `embed` returning numeric vectors; MemoryExtractor: scoped `extract` returning nodes; MemoryRetriever: scoped `retrieve` returning the response schema. The embedding provider performs a transformation, not persistent storage, and receives no implicit authorization authority. These are Python protocols; EventStore has a real SQLite adapter, MemoryStore and deterministic MemoryExtractor are implemented in Stage 3; GraphStore receives a SQLite implementation in Stage 4; Stage 5 implements embedding and retrieval adapters while retaining those protocol boundaries.

## Stage 2 event pages and persisted evidence

`oomp.domain.events.EventCursor` extends requested scope with occurrence time, ingestion time and event ID. It describes a keyset position and confers no access rights. `EventPage` contains a tuple of original MemoryEvent values and an optional next cursor. The adapter checks cursor tenant and namespace against AuthorizedScope and reads at most a bounded page.

Persisted event fields use the exact Stage 1 contract, including source_type, SourceReference and deeply immutable metadata after reconstruction. There is no duplicate storage-domain event model. All historical values survive reopen, and equivalent retry ingestion preserves the first persisted ID/time. [Exact schema, ordering and retry policy](storage.md).

## Stage 3 derived evidence and entity values

MemoryCandidate is the intermediate extraction value, with required source event ID and an exact SourceSpan (Python Unicode character offsets and verbatim quote). Its confidence is null unless a defined measurement exists. OOMP verifies allowed transformations of that quote before persistence. Candidate IDs identify proposals; stable canonical memory IDs are computed separately.

MemoryNode metadata stores source attribution, `verified: false` and canonicalization version for the default pipeline. The store refuses `verified: true` and rejects attribution inconsistent with attached events; profile evidence must be user-sourced. These checks prevent source relabeling but do not verify objective truth or prove who authored an event.

Memory source IDs and SourceReferences are reconstructed together in evidence insertion order from actual same-scope events. One source may support several memories and one memory may accumulate several sources. A new evidence link changes updated_at; a no-op retry preserves timestamps. Source occurrence time is not an inferred fact-validity interval.

EntityMention provides a name, explicit type, source event, optional source span and explicitly evidenced aliases. EntityRecord has a stable scoped ID, canonical/normalized names, type, aliases and creation time. Resolution normalizes NFC, whitespace and case within the same scope and type. Parenthetical alias evidence may reuse a single entity; similar spellings or names of different types do not imply identity. SourceSpan, MemoryWrite, ProcessingResult, MemoryCursor and MemoryPage are provider-neutral values in `domain.memories`.

## Stage 4 relationship and historical projections

MemoryEdge continues to mean a directed memory-to-memory relationship. Existing fields and invariants are preserved. Storage adds actual system recording time, recording principal and complete supporting SourceReferences in separate graph records. Source event IDs remain evidence links, never graph endpoints.

Persisted assertions are immutable and initially active. Effective superseded/disputed state is derived from visible governed assertions rather than rewriting canonical MemoryNode content or original source evidence. Stage 4 adds no arbitrary status edit/delete API.

Source validity [valid_from,valid_until) and system recorded_at are distinct. Unknown validity and pre-v3 recording times remain unknown; created_at/ingested_at do not silently become historical fact or knowledge dates. Historical views filter both relationship and evidence availability. A minimal temporal projection is not a general revision log for every node field.

Conflict proposals are validated, provider-neutral values that grant no authority. Applying a supported proposal requires trusted AuthorizedScope, deliberate confirmation and revalidation against actual source evidence. Topics and memberships form explicit scoped projections that preserve canonical memory IDs. See [temporal graph](temporal-graph.md).


## Stage 5 retrieval projections

RetrievalRequest keeps Stage 1 defaults and integer bounds, including token_budget=1. Stage 5 adds mode and explicit known_at/valid_at controls, resource limits and deliberate degraded-hybrid policy. as_of maps to reported validity, never system recording time. MemoryEvidence adds actual supporting event identities, selection reasons and temporal uncertainty without replacing canonical MemoryNode. Returned references use the eligible recording-time evidence projection, not unfiltered present-day provenance.

RetrievalResponse carries real lane counts, mode/degradation warnings, estimated_token_count, token_budget, counting_method and the actual serialized context packet. Its evidence budget includes the complete packet wrappers/IDs/provenance/paths; outer diagnostics are separate. Empty evidence has a zero-length packet. Retrieval scores are deterministic ranking signals, not claim confidence or verification. Existing schema-only callers retain compatible defaults. [Exact behavior](retrieval.md).
