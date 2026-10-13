# Memory model

All contracts use Pydantic v2, reject extra fields, validate defaults and prohibit field reassignment. Evidence collections are tuples. Event and retrieval metadata are recursively immutable snapshots and serialize as ordinary JSON objects/arrays. These are validated values, not a database, authenticator or graph engine.

## Identity and scope

`Identifier` is a case-sensitive string of 1–128 ASCII characters. It starts with a letter or digit and then permits letters, digits, `.`, `_`, `:`, `-`. Empty strings, whitespace, path separators and automatic case/whitespace normalization are not accepted. Tenant, namespace, principal, event, node, edge, session, turn and idempotency identifiers use this policy. Tags are bounded identifiers too. External event/document identifiers permit other nonblank strings up to 512 characters because source systems may use different formats.

| Type | Fields | Meaning |
| --- | --- | --- |
| RequestedScope | `tenant_id`, `namespace` | Client's requested partition; untrusted authorization intent |
| AuthorizedScope | Same scope plus required `principal_id` | Trusted service supplies it after authentication and policy; construction alone proves neither |

A namespace belongs within a tenant. A principal is an actor, not a substitute for the tenant. Protocol methods carry explicit authorized scope. Cross-tenant/namespace linkage prevention, existence checks and access decisions require future service/storage implementations that can inspect both records; identifier validation alone cannot establish those facts.

## SourceReference

Required: `source_system`, `external_event_id`, `timestamp`. Optional: `session_id`, `turn_id`, `locator` (nonblank when supplied, at most 1024 characters). A document ID uses `external_event_id` rather than a separate ambiguous field. A locator can name an evidence span, page or URI; it is not fetched or executed.

Source references describe external origin. OOMP `event_id` describes an internal historical event. A node carries both internal source IDs and external provenance, enabling a future store to resolve, audit and verify links. Stage 1 requires their presence but cannot verify their external truth or database consistency.

## MemoryEvent

Required: `event_id`, `tenant_id`, `namespace`, `event_type`, `source_type`, `content`, `source_reference`, `occurred_at`, `ingested_at`. Optional: `idempotency_key` (default null), `metadata` (default empty object).

Content must be nonblank and at most 1,000,000 characters; its original spacing is preserved. Metadata must be a JSON object with string keys and JSON-compatible nested values, including null. Explicit metadata null, executable objects and NaN/infinity are rejected. Input containers are copied into immutable snapshots; mutating the caller's input cannot revise source evidence. This value-level protection is distinct from future append-only storage and erasure policy.

| EventType | Required SourceType |
| --- | --- |
| `user_message` | `user` |
| `assistant_message` | `assistant` |
| `document` | `document` |
| `tool_result` | `tool` |
| `correction` | Any declared source type |
| `feedback` | Any declared source type |

`SourceType` also includes `system`. Corrections and feedback preserve who supplied them; they do not automatically become verified user truth. Assistant assertions remain generated content even when a later memory cites them. No trust score is invented.

Occurrence records when the source event happened; ingestion records when OOMP received it. Both are required and independent. Stage 1 imposes no ordering between them, allowing imported data and explicitly represented clock skew. Future ingestion policy must decide which clock anomalies to reject or flag. Idempotency collision checking is a future storage responsibility within tenant and namespace.

## MemoryNode

Required: `memory_id`, `tenant_id`, `namespace`, `memory_type`, `canonical_content`, `canonical_key`, `source_event_ids`, `provenance`, `created_at`, `updated_at`. Optional: `confidence`, `valid_from`, `valid_until` (all default null), `status` (default active), `tags` (default empty tuple).

`canonical_content` is nonblank, at most 1,000,000 characters. `canonical_key` is nonblank, at most 512 characters, with source text preserved. `source_event_ids` and `provenance` must each contain at least one item. A confidence, when measured, is a finite number in `[0,1]`; absent confidence remains null. It is not a retrieval score or proof of truth.

`MemoryType`: `episodic`, `semantic`, `profile`, `procedural`, `project_state`, `resource`, `decision`, `topic_summary`. All use the same identity/provenance/temporal envelope; type-specific payloads can be refined when extraction exists.

A node retains its persistent identity across graph views. Topic membership uses relationships, avoiding duplicate facts just because several projects need them. Canonical keys provide a future deduplication hint; this stage does not establish uniqueness, merge facts or assign identities automatically.

`MemoryStatus`: `active`, `superseded`, `retracted`. Status describes derived state; it does not erase source events. Superseded records remain historical evidence. A current status alone cannot answer historical `as_of` queries: future retrieval must use validity and relationship history, with a defined policy for retrospectively retracted evidence.

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
    canonical_content="The user preferred Python.", canonical_key="preferred-language",
    source_event_ids=("evt-1",), provenance=(old_ref,), created_at=jan, updated_at=feb,
    valid_from=jan, valid_until=feb, status="superseded")
new = MemoryNode(**scope, memory_id="mem-2", memory_type="profile",
    canonical_content="The user prefers Rust.", canonical_key="preferred-language",
    source_event_ids=("evt-2",), provenance=(new_ref,), created_at=feb, updated_at=feb,
    valid_from=feb)
edge = MemoryEdge(**scope, edge_id="edge-1", source_node_id=new.memory_id,
    target_node_id=old.memory_id, relationship_type="SUPERSEDES",
    source_event_ids=("evt-2",), created_at=feb, valid_from=feb)
```

Both events remain unchanged. A future January-as-of lookup should consider the earlier validity; a current lookup should consider the newer evidence and supersession. The new node's unknown end does not guarantee the preference will never change. Matching canonical keys do not collapse two distinct temporal assertions automatically.

## Retrieval schemas

`RetrievalRequest` extends requested scope with nonblank `query` (at most 100,000 characters), strict integer `max_results` (default 8, range 1–100), strict integer `token_budget` (default 1200, range 1–32768), and optional UTC-aware `as_of`. Boolean, fractional, string, zero, negative and out-of-bound integer budgets/limits are rejected. Constants are Stage 1 safety limits; configurable server ceilings belong to later service policy.

`MemoryEvidence` contains `memory_id`, `canonical_content`, `memory_type`, required nonempty `source_references`, optional finite `retrieval_score` (null by default, metric range unspecified), temporal bounds, status, graph paths and JSON metadata. Scores and confidence have different meanings; schemas compute neither.

`GraphPath` contains nonempty `node_ids`, `edge_ids`, `relationship_types`. It requires `len(edge_ids) == len(node_ids)-1` and equal edge/relationship counts. A single-node path is allowed. This validates shape, not graph existence or authorized connectivity.

`RetrievalResponse` requires `retrieval_id`; memories, source references and graph paths default empty; strict nonnegative `estimated_token_count` defaults zero. An empty response is a valid payload, not a working retriever. The response has no generated-answer field. Budget compliance, scoring, actual token accounting, endpoint resolution and provenance consistency require the future retrieval/service implementation.

## Protocol boundaries

EventStore: scoped `append`/`get`; MemoryStore: scoped `put`/`get`; GraphStore: scoped `put_edge`/`edges_for`; EmbeddingProvider: `embed` returning numeric vectors; MemoryExtractor: scoped `extract` returning nodes; MemoryRetriever: scoped `retrieve` returning the response schema. The embedding provider performs a transformation, not persistent storage, and receives no implicit authorization authority. These are Python protocols, with no runtime adapter or dummy implementation.
