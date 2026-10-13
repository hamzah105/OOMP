# Architecture

## Purpose and current boundary

OOMP is an independent external memory library, not a chatbot or an application-specific conversation database. Its output will be evidence, source references and retrieval metadata. Applications remain responsible for composing prompts and generating final answers. Stage 1 implements contracts and a CLI only.

```mermaid
flowchart LR
    A[Authorized source events] --> B[Durable event store: planned]
    B --> C[Extraction and canonicalization: planned]
    C --> D[Canonical memory records: planned]
    D --> E[Temporal associative graph: planned]
    D --> F[Lexical and vector indexes: planned]
    E --> G[Budgeted evidence retrieval: planned]
    F --> G
    G --> H[Application or MCP client: planned]
```

## Architectural contracts

1. **Immutable source evidence.** Events preserve what was observed, by whom, when and where. A changed derived fact does not rewrite the earlier source. A future append-only store must support auditable corrections, while authorized erasure can remove protected content and dependent material. Immutability never overrides privacy or authorized deletion requirements.
2. **Canonical identity.** A memory object retains its own ID. Multiple topic memberships use edges and views, without duplicating the same fact. Canonical keys assist future deduplication but are not a global authorization domain or a promise that semantic identity is already solved.
3. **Temporal relationships.** Historical facts can coexist. Validity intervals, statuses and SUPERSEDES/CONTRADICTS edges allow future retrieval to distinguish current, conflicting and historical evidence. Unknown validity is not permanent truth.
4. **Multiple graph views.** A topic tree is a projection of a richer graph. PART_OF can support hierarchy; RELATED_TO and other relationships may contain cycles. There is no universal acyclicity invariant.
5. **Provider independence.** Domain schemas and protocols have no OpenAI, Anthropic, Ollama, LangChain, LlamaIndex or TRACE types. Adapters translate provider-specific inputs at the boundary.
6. **Evidence output.** Retrieval selects evidence, not a generated final answer. Scores and confidence remain absent unless a defined measurement supplies them.
7. **Explicit authorized scope.** Every future persistent operation receives an authorized tenant/namespace scope. Client identifiers alone are not authorization.
8. **Explicit state.** Memory identity and scope are independent of transport connections. A session, socket or MCP host is not durable memory state.

## Components and dependency direction

`domain.models` and `domain.enums` define validated values; `retrieval.contracts` defines the prospective `memory.retrieve` payloads. `domain.interfaces` defines EventStore, MemoryStore, GraphStore, EmbeddingProvider, MemoryExtractor and MemoryRetriever protocols. They have signatures only. A future service layer will validate policy and resolve provenance before calling replaceable adapters.

Protocols are synchronous in this stage to keep local boundaries small. Async service/transport adapters may be introduced later when actual I/O warrants them; no background execution or scheduling semantics are implied. Protocol conformance does not automatically enforce policy. Implementations must compare requested scope with authorized scope and verify object scope, endpoints and evidence references inside the authorized partition.

## Storage versus indexes

Planned SQLite storage is the durable source for events, canonical objects, relationships and processing state. Lexical/vector indexes will be derived, replaceable acceleration structures. Rebuilding an index must not change source identities or erase provenance. Namespace isolation applies to index lookups, caches, candidate selection and final evidence, not just a last response filter.

Idempotency is scoped to tenant and namespace. A future append operation should return the same event for an identical replay and reject conflicting reuse of an event ID or idempotency key. Transactions, locking, crash recovery, migrations and deletion propagation are Stage 2+ decisions; none is implemented here.

## Planned consolidation

The Stage 6 background engine may merge duplicate candidates, refine topic summaries and resolve stale derived state. It must operate on explicit authorized scope, preserve provenance, record which extraction/version produced changes, and remain resumable after failure. It must not manufacture verified truth from an assistant assertion or silently destroy earlier evidence.

## MCP and application boundaries

Stage 7 will use the official MCP Python SDK v2, exposing memory operations through stdio and stateless Streamable HTTP. As checked on 2026-10-13, the official SDK documents v2 as its stable line. No MCP package is installed in the OOMP environment. Revalidate the SDK and protocol requirements when building that adapter. [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).

Authentication, authorization, input size limits, approval for privileged writes, server-side scope mapping, origin validation and safe binding belong to OOMP's service/transport boundary. MCP compatibility does not itself establish tenant authorization. Stdio inherits a local process trust boundary; HTTP requires explicit authenticated principals. Neither transport holds memory state.

TRACE.AI is the proposed first external integration in Stage 8. Its application's working conversation window remains an application concern. An adapter may ingest authorized events and retrieve evidence without embedding TRACE-specific classes in OOMP. This repository has no TRACE source, checkout or dependency, and this stage modifies no TRACE files.

## Decisions to revisit

Confirm durable ID generation and idempotency collision behavior; canonical-key uniqueness; principals/roles and authorization policy; extraction span/version provenance; edge endpoint entity kinds; tombstone and erasure policy; configurable request bounds; tokenizer accounting; embedding compatibility metadata; sync/async I/O requirements; and MCP version/transport deployment settings before their respective stages.

