# Security model

Stage 1 validates data shape and scope identifiers. Stage 2 implements scoped SQLite event persistence, while no network authenticator, authorizer, listener, approval service or encrypted storage is implemented. The following contracts distinguish current storage enforcement from future service policy.

## Local-first operation

CLI diagnostics run locally and send no memory data to a provider. No services bind ports and no credentials are required. The SQLite default is a local user-data directory. Future embeddings should also remain local by default. An externally configured extraction/embedding provider must be an explicit choice, with documented data flow and retention. File permissions and database encryption must be designed for the deployment; they are not present-day capabilities.

## Tenant, namespace and principal

A tenant is a durable isolation boundary; a namespace partitions memory within that tenant; a principal identifies the authenticated actor. These are distinct concepts. `RequestedScope` is client intent. `AuthorizedScope` carries validated tenant, namespace and principal identifiers that trusted service code supplies after authentication and policy evaluation.

Any caller can construct a Pydantic scope object. Its type and valid identifier format are not proof of authorization. Future endpoints must never deserialize a client-provided AuthorizedScope and accept its claimed principal as trusted. Local services also need an explicit trusted principal/scope binding, not an ambient guessed `user_id`.

Every persistent read/write, retrieval, extraction job and index operation must accept explicit authorized scope. Adapters must reject tenant or namespace mismatch before access. Storage must inspect both edge endpoint records and all referenced events inside the authorized scope before accepting links. Two syntactically valid IDs cannot enforce this referential security constraint on their own.

Cache keys, idempotency keys, canonical-key lookup, indexes, logs and graph candidates must be scoped. Isolation must hold before ranking and token selection; post-filtering an already shared candidate list is insufficient. Cross-namespace sharing needs a separately reviewed, explicit policy.

## Evidence and generated text

Documents, tool results, user messages and assistant messages are untrusted text. They may contain prompt injection, malicious links or instructions. Retrieval must return them as quoted evidence with provenance, never grant them tool authority or reinterpret their instructions as service policy. Inclusion in a prompt does not verify content.

Source/event types retain the distinction between user assertions and assistant-generated assertions. Confidence is unknown by default. An extraction model cannot self-authorize memory writes, deletion, scope expansion or permissions. Future privileged writes and destructive operations need server policy, authenticated authority and any application-required approval.

## Privacy, corrections and deletion

Keep source events immutable during ordinary corrections. Append a correction and update derived temporal state with a recorded relationship instead of rewriting history. Authorized erasure is different: private source content, derived memories, edges, embeddings, indexes, caches, logs and backups require a documented deletion/retention strategy. Tombstones must not retain the erased secret. Privacy-preserving audit metadata must be minimized and justified.

Do not put credentials or secret configuration in event metadata by default. Metadata is finite JSON, not executable objects. Unknown schema fields are rejected; future adapters must enforce payload limits and retention. Diagnostic output must avoid dumping memory text or secrets. `.gitignore` excludes local databases, indexes, environments, logs and common secrets, but ignore rules are not access control or a guarantee against disclosure.

## Future MCP assumptions

MCP transport credentials and the request's authenticated principal must be checked independently of requested memory scope. Streamable HTTP requires correct authentication/audience mapping, authorization, origin validation and local-first bind defaults. Stdio trusts the invoking process/environment and still needs explicit scope policy. Transport session identifiers are not durable memory keys or authorization tokens. Only the configured service may exercise storage authority; model proposals remain inputs to validation and policy.

Stage 2 tests tenant/namespace event isolation, mismatched scopes/cursors, duplicate identity concurrency and safe storage diagnostics. Graph/vector index leakage, privileged erasure propagation and transport credentials remain later-stage tests.


## Implemented Stage 2 enforcement

Each event operation requires a trusted-service AuthorizedScope and validates its identifiers again. Append rejects an event from a different tenant or namespace before database access; get/list/count include both partition columns in SQL. RequestedScope is rejected as authority. An event source reference or metadata principal cannot elevate access. Cursor scope is checked too; cursors are not capabilities.

Scoped primary/idempotency uniqueness and explicit write transactions prevent retry duplicates. The ordinary API exposes no update/delete/replace operation, and triggers protect ordinary SQL event changes. Filesystem/SQL administrators still control the underlying plaintext database. Caller authentication is intentionally outside this local adapter.

Database paths and initialization are trusted local administrative settings, not future remotely supplied memory scopes. Read/status never creates a missing database; diagnostics expose no event contents or global tenant counts. Corrupt stored evidence produces sanitized failures. [.gitignore](../.gitignore) excludes SQLite files/sidecars, local environments and temporary artifacts. [Backup, concurrency and future privacy erasure](storage.md) describe the remaining deployment requirements.

## Stage 3 extraction trust boundary

Source content is untrusted data. The deterministic pipeline executes no text, follows no URLs and makes no network requests. Only supported user statements and eligible document claims enter default extraction; assistant/tool/system claims are excluded. User-profile candidates require user evidence. Every proposal is revalidated against an existing same-scope event and exact Unicode span, then compared with supported deterministic transformations before writes. Unknown types, invented statements, fabricated provenance, incorrect spans and scope mismatches fail closed.

Claims retain attribution and `verified: false`; the store rejects unsupported verified metadata and inconsistent attribution. This is provenance accounting, not identity verification or a claim that a statement is objectively true. Corrections remain attributed events and do not automatically retract earlier memories.

The extractor skips whole events containing recognizable passwords, API keys, secret/token assignments, bearer credentials or private-key headers. This is a limited heuristic, not a comprehensive secret scanner. Original events remain stored in Stage 2 and may still contain sensitive data. Trusted direct MemoryStore callers remain responsible for their own content policy. Skipped extraction does not imply deletion, encryption or safe publication of the original event.

Injected extractors have proposal authority only. No implemented local model adapter, endpoint or configuration exists; a future adapter must be explicit opt-in, bounded, validated and subject to the same source grounding. No provider writes directly to persistence. The default operation has no internet, cloud, Ollama, GPU or arbitrary tool dependency.

All reads/writes require AuthorizedScope and include tenant and namespace in lookups and foreign keys. Canonical-memory and entity identities are scoped; there is no cross-tenant cache or identity reuse. Scope construction is a trusted in-process boundary, not an authentication mechanism. Local CLI commands use a local administrative principal and rely on machine/filesystem access. A tenant argument does not authenticate an internet user.

Memory list omits canonical content by default; `--show-content` is a deliberate trusted-debugging option. IDs, types and source IDs remain metadata and can themselves be sensitive. Database content is plaintext. No encryption, secure erasure, public API authentication, model safety certification or administrator-resistant authenticity is claimed.
