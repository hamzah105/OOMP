# Security model

P1's additional local profile, file-permission and process-control boundaries are
documented in [product security](product-security.md). The existing memory/MCP
authority and governance rules below remain unchanged.

OOMP 0.1.0 is an alpha local research candidate. It implements scoped persistence,
source validation, bounded retrieval/workers and an optional authenticated loopback
MCP profile. It does not provide encrypted storage or a production-ready public
multi-tenant cloud service. The stage-specific sections below describe retained
controls and their historical boundaries; the current MCP boundary is Stage 7.

## Local-first operation

Core CLI diagnostics run locally and send no memory data to a provider. Core
operation requires no listener or credential. Explicit MCP operation separately
starts a configured loopback service or stdio transport with trusted grants.
The SQLite default is a local user-data directory. Embeddings are opt-in and
support only an explicitly configured literal loopback endpoint. Provider data
flow/retention and host filesystem protection remain operator responsibilities;
database encryption is not implemented.

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

## MCP boundary

MCP transport credentials and the request's authenticated principal must be checked independently of requested memory scope. Streamable HTTP requires correct authentication/audience mapping, authorization, origin validation and local-first bind defaults. Stdio trusts the invoking process/environment and still needs explicit scope policy. Transport session identifiers are not durable memory keys or authorization tokens. Only the configured service may exercise storage authority; model proposals remain inputs to validation and policy.

Stage 2 tests tenant/namespace event isolation, mismatched scopes/cursors, duplicate identity concurrency and safe storage diagnostics. Stages 4–5 add graph/vector/index isolation tests. Stage 6 adds constrained privileged local erasure; Stage 7 adds the separately configured local transport credential boundary.


## Implemented Stage 2 enforcement

Each event operation requires a trusted-service AuthorizedScope and validates its identifiers again. Append rejects an event from a different tenant or namespace before database access; get/list/count include both partition columns in SQL. RequestedScope is rejected as authority. An event source reference or metadata principal cannot elevate access. Cursor scope is checked too; cursors are not capabilities.

Scoped primary/idempotency uniqueness and explicit write transactions prevent retry duplicates. The ordinary API exposes no update/delete/replace operation, and triggers protect ordinary SQL event changes. Filesystem/SQL administrators still control the underlying plaintext database. Caller authentication is intentionally outside this local adapter.

Database paths and initialization are trusted local administrative settings, not future remotely supplied memory scopes. Read/status never creates a missing database; diagnostics expose no event contents or global tenant counts. Corrupt stored evidence produces sanitized failures. [.gitignore](../.gitignore) excludes SQLite files/sidecars, local environments and temporary artifacts. [Backup, concurrency and future privacy erasure](storage.md) describe the remaining deployment requirements.

## Stage 3 extraction trust boundary

Source content is untrusted data. The deterministic pipeline executes no text, follows no URLs and makes no network requests. Only supported user statements and eligible document claims enter default extraction; assistant/tool/system claims are excluded. User-profile candidates require user evidence. Every proposal is revalidated against an existing same-scope event and exact Unicode span, then compared with supported deterministic transformations before writes. Unknown types, invented statements, fabricated provenance, incorrect spans and scope mismatches fail closed.

Claims retain attribution and `verified: false`; the store rejects unsupported verified metadata and inconsistent attribution. This is provenance accounting, not identity verification or a claim that a statement is objectively true. Corrections remain attributed events and do not automatically retract earlier memories.

The extractor skips whole events containing recognizable passwords, API keys, secret/token assignments, bearer credentials or private-key headers. This is a limited heuristic, not a comprehensive secret scanner. Original events remain stored in Stage 2 and may still contain sensitive data. Trusted direct MemoryStore callers remain responsible for their own content policy. Skipped extraction does not imply deletion, encryption or safe publication of the original event.

Injected extractors have proposal authority only. No extraction model adapter exists; a future extraction adapter must be explicit opt-in, bounded, validated and subject to the same source grounding. Stage 5 has a separate local embedding adapter that produces vectors and has no write authority. No provider writes directly to persistence. The default operation has no internet, cloud, Ollama, GPU or arbitrary tool dependency.

All reads/writes require AuthorizedScope and include tenant and namespace in lookups and foreign keys. Canonical-memory and entity identities are scoped; there is no cross-tenant cache or identity reuse. Scope construction is a trusted in-process boundary, not an authentication mechanism. Local CLI commands use a local administrative principal and rely on machine/filesystem access. A tenant argument does not authenticate an internet user.

Memory list omits canonical content by default; `--show-content` is a deliberate trusted-debugging option. IDs, types and source IDs remain metadata and can themselves be sensitive. Database content is plaintext. No encryption, secure erasure, public API authentication, model safety certification or administrator-resistant authenticity is claimed.

## Stage 4 graph trust and historical access

All graph endpoints, evidence links, topic records, memberships, cursors and traversal steps remain inside authorized tenant and namespace. Composite foreign keys reinforce existence/scope checks. Topic membership and shared wording do not imply conflict, verification or cross-tenant identity reuse.

Structural links are attributed trusted-caller assertions. Protected conflict/supersession links require supported source-grounded policy, explicit confirmation and transactional revalidation; generic edge insertion cannot bypass governance. Unsupported grammar and unknown temporal overlap yield uncertainty. No model or source text executes tools, writes SQL or autonomously replaces a fact.

Actual recording times are assigned by storage. Historical known_at views exclude later assertions and evidence; caller-supplied backdated timestamps cannot make later writes appear known earlier. Pre-v3 original recording times are unavailable and explicitly reported as such. This is auditable local history, not a trusted external time or cryptographic authenticity service.

Graph/CLI output hides canonical content by default. IDs, edge metadata and topic names may still be sensitive. Local machine/filesystem access supplies CLI authority; a tenant argument is not remote authentication. Plaintext SQLite, administrator trust, limited secret scanning and absent encryption remain unchanged; Stage 6 adds a distinct constrained erasure path. Those graph features add no network dependency. Stage 7 separately supplies optional local MCP; TRACE remains untouched.


## Stage 5 retrieval and optional local vectors

All candidate lanes, FTS ranking statistics, vector spaces, graph steps and final provenance are partitioned before ranking and packing. Requests must match a revalidated AuthorizedScope. A single read snapshot prevents later attachments or corrections from entering historical proof mid-request. The entity lane is disabled for known_at views where association history cannot establish availability. No retrieval operation grants mutation authority.

The optional Ollama transport is disabled unless deliberately constructed/configured. It accepts literal loopback addresses, disables proxy inheritance, rejects redirects and bounds inputs, responses and timeouts. OOMP does not download models, expose a network listener or permit a cloud endpoint. The local daemon and its configured model remain trusted software. Vector validation checks numeric finiteness, norm, dimension and model identity; data-driven instructions cannot alter endpoint/configuration/scope.

Memory bodies are untrusted data in a JSON evidence packet. IDs, source references, locators and graph metadata may also be sensitive. The CLI hides content by default, including JSON output, and exposes it only through --show-content. Provider failures and ordinary diagnostics must not echo query text, memory text or response bodies. Downstream hosts remain responsible for prompt construction, tool authority and their own complete prompt token budget.

Derived vectors and FTS rows remain plaintext private data subject to any future retention/erasure policy. Fingerprints do not establish objective truth or administrator-resistant authenticity. Stage 5 itself added no deletion propagation. Stage 6 adds scoped privileged logical erasure; encryption, public remote authentication and TRACE integration remain outside the implemented boundary. Stage 7 separately supplies local MCP authentication.

## Stage 6 worker and privileged administration

Worker scope and identity come from trusted operator configuration. Job payloads and provider responses cannot authorize a new scope, relationship approval or deletion. Jobs store IDs and restricted configuration; attempts and audits expose sanitized codes/counts. Content display is an explicit local inspection option. Identifiers and source references remain potentially sensitive.

Protected conflict proposals require deliberate trusted confirmation and Stage 4 transactional revalidation. Corrections append source events. Retraction records withdrawal of endorsement without rewriting origin. Neither model output nor source instructions receive approval authority.

Erasure requires an explicit scoped event target, nonmutating dependency plan and operator confirmation of that exact plan. Cleanup, job cancellation and tombstoning are transactional. Shared canonical records with independently valid surviving evidence are preserved. Unsupported dependencies fail closed. Ordinary event mutation triggers remain globally installed; a privileged bypass is confined to the erasure transaction and restored before commit.

Source and memory existence are rechecked inside persistence transactions, preventing paused workers from recreating erased derivations. Dedicated summaries recheck their actual evidence. No source body, source-body digest or provider response is preserved in erasure audits. Logical deletion cannot remove physical remnants, backups, exports or data already returned to another process. Operators must enforce backup/export retention separately.

These local administrative APIs are not safe remote tools merely because their inputs validate. Stage 7 must implement authentication, principal/scope mapping, privilege/approval policy and transport security before external exposure. [Detailed operational boundary](background-mind.md).

## Stage 7 transport enforcement

The optional local MCP interface maps trusted HTTP bearer grants or one explicit stdio process grant to AuthorizedScope. Ordinary catalogs contain only retrieve, expand, get_source and status. Raw linked source text requires read_source; ingestion requires a trusted profile, ingest capability and a separate short-lived payload-bound host signature. Principal/scope/source-role metadata cannot be injected by a tool caller.

Exact literal loopback binding, Host/Origin checks, SDK authentication/body parsing, bounded inputs/results/concurrency, private discovery hints and static errors protect this deployment. It is a preissued local credential profile, not an OAuth issuer, remote production service or universal host connector. Canonical and source content remain untrusted data; erasure and conflict confirmation stay privileged local actions. [MCP security](mcp-security.md) specifies threats, host responsibilities and remaining limits.

## Stage 10 review and release boundary

The [focused review](security-review.md) records inspected trust boundaries,
preserved security regressions, packaging fixes and actual dependency scan scope.
Build/install tools were patched independently of runtime algorithms/dependencies.
Archive checks and passing tests are bounded evidence, not a complete security
certification. No model-controlled deletion/approval or public deployment was added.

Protect plaintext data and backups with host permissions. Logical erasure cannot
wipe SQLite free pages/WAL/FTS segments or external copies, and restoring an old
snapshot can resurrect data erased later. Follow [retention and WAL-safe recovery](privacy-retention.md).
Host prompt construction remains responsible for treating returned content as
untrusted; JSON framing alone cannot certify an LLM's injection resistance.

Use [SECURITY.md](../SECURITY.md) for sensitive reporting. Private vulnerability
reporting requires maintainer configuration; no private email, response team or
SLA is invented. Release recommendation and pending human/CI gates are in
[the release checklist](release-checklist.md).
