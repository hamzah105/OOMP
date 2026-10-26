# MCP security boundary

Stage 7 adds a local interoperability boundary, using the official SDK for MCP framing, request parsing, transport lifecycle and bearer authentication middleware. The default tool profile is read-only. This is a single-machine development deployment, not a hardened public multi-user service or a full OAuth authorization server.

## Authority and data flow

~~~mermaid
flowchart LR
    H[Trusted host configuration and secret store] --> A[Grant resolver]
    C[Untrusted tool arguments] --> V[Bounded extra-forbid input models]
    B[HTTP bearer credential or fixed stdio process grant] --> A
    A --> S[Server-owned AuthorizedScope]
    V --> T[Scoped service adapter]
    S --> T
    T --> R[Existing retrieval / temporal graph / source / queue services]
    R --> D[SQLite v5]
    P[Separate host approval key] --> I[Payload-bound ingest approval verification]
    A --> I
    V --> I
    I --> E[Stage 2 append and durable Stage 6 outbox]
    E --> D
~~~

Configuration is trusted input, not model input. It selects principal, tenant, namespace, capabilities, source role and optional embedding identity. HTTP credentials resolve to configured grants; MCP session IDs, request metadata, cookies, caller-supplied principal claims and tool arguments never supply scope. Stdio uses one explicit process grant and trusts its launching process/environment.

Equal IDs in different tenants remain separate identities. SQL proof lookups and ranking reuse the existing scoped core. A guessed source ID must also belong to the requested accessible memory. Neither global tenant statistics nor database paths appear in status. read_source is independent of ordinary canonical evidence read permission.

## Transport controls

| Threat | Implemented control |
| --- | --- |
| Unauthenticated network request | Official SDK BearerAuthBackend, AccessToken with endpoint audience and subject, RequireAuthMiddleware, request-local auth context; missing/invalid/expired credentials return 401. |
| Credential switching or scope spoofing | Resolver independently verifies grant identity and capability on each tool call. No fallback from HTTP to stdio; extra argument keys rejected before SDK coercion. |
| Accidental remote listener | Configuration accepts only literal 127.0.0.1 or ::1; uvicorn proxy headers disabled. No tunnel, automatic publication, OAuth issuer or public bind. |
| DNS rebinding or browser cross-origin request | Exact Host address/port and exact configured Origin checks before SDK processing, plus SDK transport-security settings. Invalid Host 421; invalid Origin 403. No wildcard host/port/origin. |
| Header ambiguity or excessive requests | Critical duplicate headers rejected; bounded header count/bytes, request concurrency and uvicorn connection parsing. SDK validates protocol/method/name header agreement against body metadata. |
| Large declared/chunked body | Official SDK body-limit middleware rejects before protocol dispatch, including incrementally accumulated chunked bodies. Default 128 KiB, maximum 1 MiB. |
| Expensive graph/lookup request | Stage 5 query/candidate/packet bounds plus tighter MCP graph and result caps, cycle-safe scoped traversal. Busy/resource_limit are explicit tool failures. |
| Sensitive diagnostics | Static application errors; no validation input echo, SQL, private exception text or traceback. CLI access logs off; SDK diagnostics at critical level. Protocol stdout has no OOMP banner. |
| Discovery shared across credentials | Private zero-TTL SDK cache hints and HTTP Cache-Control: no-store / Vary: Authorization. Unused SDK subscriptions disabled. |
| Unsupported capability | Four read tools, separately gated ingest. Resource/prompt lists empty and reads unavailable; no remote admin/erasure/SQL/conflict-approval surface. |

HTTP authentication is a deliberately local preissued opaque-token profile. There is no OAuth metadata/authorization/consent flow, TLS endpoint, reverse-proxy deployment or automatic browser client configuration. Hosts demanding standards-based OAuth discovery are not supported by this profile. A future public service would need its own reviewed authentication, network and operations design.

Tokens are environment-backed URL-safe secrets of 43–256 characters, generated from at least 32 random bytes. Syntax validation cannot measure randomness; administrators must generate real random values. Tokens are compared by constant-time digest comparison, and duplicate credential mappings fail at startup. File configuration contains environment-variable names only. Never commit secrets or pass tokens in query strings. Configuration and database files still contain sensitive scope information; protect them using local filesystem permissions.

Grant expiry is checked during verification and tool dispatch. Restart for configuration/token revocation or rotation. A read already authorized may finish while a grant is being revoked; responses represent the existing bounded snapshot semantics.

## Ingest: capability is necessary but insufficient

Ingest requires trusted-ingest server profile, an ingest grant, configured coherent source/event policy and a short-lived signature from a separate trusted-host key. Merely knowing a writer bearer token cannot mint approval. Read-only grants never discover or call this tool, including on a trusted-ingest server.

The approval signs an exact validated event, principal, scope, source policy, nonce and expiry using domain-separated HMAC-SHA256. Content, provenance, role policy, event ID and idempotency-key changes invalidate it. Expired/future or cross-grant approvals fail. The signer must first verify the real original source and required approval policy; a signature establishes host-key possession, not objectively verified truth or proof of a human click.

Models see the tool schema and may ask to call it if a host exposes it. The host must keep the signing key out of model context and use the host-only approve_ingestion API only after its policy succeeds. The server must have its verification key through trusted deployment configuration. A compromised host or machine administrator can obtain keys and bypass the intended approval process; this is outside the stated process trust boundary.

Server-side event construction prevents source_type, ingested_at, arbitrary metadata, principal or scope injection. Provenance.source_system must match the grant. System-source events are unavailable. A tool-origin or assistant-origin host needs its own accurately labeled grant; it must not relabel model assertions as user evidence.

Stage 2 fingerprint/idempotency protects repeated approvals and network retries. Nonces bind the proof but are not separately persisted as one-use grants: replay of the identical approved payload is intentionally idempotent. A host can reapprove the same evidence after expiry. Durable acceptance means the real Stage 6 outbox exists; it does not mean the worker has run, extracted a fact or approved a conflict.

## Evidence and prompt injection

Source and canonical text, locators, topic names and provenance can contain malicious instructions or inaccurate assertions. They are returned as untrusted evidence, never executed or installed as policy. The server performs no answer generation and never fetches a locator. Hosts must preserve this data/instruction distinction when composing prompts.

Canonical retrieval can reveal authorized sensitive facts even without read_source. Granting read grants access to the selected namespace's canonical evidence; read_source adds raw linked event text and deserves narrower distribution. No general-purpose secret-redaction guarantee is asserted. Existing conservative extraction filters are limited, and privileged direct storage can contain arbitrary source claims.

Known-at/valid-at filtering preserves Stage 4/5 uncertainty rather than inventing old knowledge. Retractions exclude unendorsed proof from current source and graph reads; explicit historical access can return previously endorsed evidence. In-flight reads follow SQLite snapshot semantics. Privileged erasure remains the local Stage 6 constrained workflow; it is never model callable.

The evidence counter covers context_packet only. SDK text and structured forms duplicate data, so hosts must budget the complete chosen representation and their own prompt. Independent result/body caps control adapter resources without silently clipping evidence.

## Error and testing policy

Successful tool results validate against the advertised Pydantic output schema. Application failures return isError with a structured error containing code, static message and retryable flag. Codes are invalid_parameters, unauthorized, forbidden, not_found, conflict, storage_unavailable, embedding_unavailable, resource_limit, busy and internal_error. Unknown/foreign identifiers share the same not_found behavior. Protocol-level errors remain official SDK errors; HTTP security rejections use appropriate status codes.

Real SDK stdio and TCP clients test disclosure boundaries, identical cross-tenant IDs, scoped ranking, raw-source capability, extra-field injection, proof tampering/expiry/cross-grant use, idempotency, concurrent reads/workers, restart, Host/Origin, malformed/protocol headers, declared/chunked bodies and safe output/logging. See [validation](stage7-validation.md).

SQLite remains plaintext and local administration is trusted. TLS, encryption at rest, OS credential storage, per-principal rate limits, distributed token revocation, remote identities, OAuth discovery, durable approval-nonce accounting and external desktop-host compatibility are not supplied by this milestone. No model-controlled source erasure, scope change or graph approval is exposed.