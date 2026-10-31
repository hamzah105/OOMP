# MCP integration (Stage 7)

Product P1 adds [guided profiles and lifecycle](product-onboarding.md) around this
unchanged SDK/approval interface. `oomp up` supervises a separate authenticated
HTTP server and selected Mind worker; `oomp connect` is the host-owned stdio path.
The explicit manual configuration/commands below remain supported. P1 does not
patch host authentication, expose public listeners or change tool schemas.

Release note (Stage 10, 2026-10-27): runtime/SDK/tool contracts below remain
unchanged. Install the optional extra in the exact interpreter running the server
and exercise the official SDK examples. Read-only defaults, separately approved
ingestion and loopback restrictions remain required. This guide does not certify
public/proxy hosting or every desktop client. Current installed artifact checks
are in [Stage 10 validation](stage10-validation.md). TRACE has its own
[independent integration guide](https://github.com/hamzah105/trace-ai-chatbot/blob/main/docs/oomp-integration.md);
no TRACE application is bundled in OOMP's runtime. Stage 9's real embeddings do
not retroactively change this guide's historical Stage 7 measurements.

OOMP exposes its existing evidence services through the official MCP Python SDK 2.3.0. The optional dependency range is >=2.3.0,<2.4, reviewed on the client date 2026-10-27. Package version stays 0.1.0; current P3 storage uses SQLite schema v6. MCP is an adapter; it does not generate answers, initialize a database, download models or start the Mind worker.

The implemented transports are SDK stdio and stateless Streamable HTTP at /mcp on a literal loopback address. The actual SDK Client was tested with modern protocol 2026-07-28 and its legacy HTTP mode. No named desktop host or independent third-party SDK has been validated. A host that requires OAuth discovery will need another deployment profile; the implemented HTTP profile uses preissued local bearer credentials.

## Install and prepare explicitly

From D:\Desktop\OOMP in PowerShell:

~~~powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,mcp]"
.\.venv\Scripts\python.exe -m oomp --version
.\.venv\Scripts\python.exe -m oomp doctor
.\.venv\Scripts\python.exe -m oomp storage init --db ".\data\memory.sqlite3"
~~~

The base install remains Pydantic-only. Core storage, retrieval, workers, CLI help and doctor operate without the optional SDK. SDK integration tests skip when it is absent. Doctor reports the SDK version without starting a server or requiring a database.

Storage initialization is a separate local administrator action. Existing ingestion/extraction or the explicit Stage 6 worker must create canonical memories. Starting MCP against a missing, uninitialized, old or unsupported database fails without creating it.

## stdio: fixed invoking-process authority

Generate a read-only server configuration; the tenant, namespace and principal must be supplied explicitly:

~~~powershell
.\.venv\Scripts\python.exe -m oomp mcp config --format server --config ".\data\mcp-server.json" --db ".\data\memory.sqlite3" --tenant demo --namespace personal --principal local-host | Set-Content -Encoding UTF8 ".\data\mcp-server.json"
.\.venv\Scripts\python.exe -m oomp mcp check --config ".\data\mcp-server.json"
.\.venv\Scripts\python.exe -m oomp mcp config --config ".\data\mcp-server.json"
~~~

The last command prints valid JSON containing an absolute Python executable and an argument array. It edits no host configuration. Copy the generated mcpServers entry to your host's documented MCP settings and select the intended host environment. Argument arrays preserve Windows spaces; do not combine command and arguments into one shell string. No activation, shell wrapper or working-directory assumption is needed with the absolute executable and configuration path.

The host launches the equivalent of:

~~~powershell
D:\Desktop\OOMP\.venv\Scripts\python.exe -m oomp mcp serve --config "D:\Desktop\OOMP\data\mcp-server.json" --transport stdio
~~~

This process waits for MCP frames on stdin. Its stdout belongs entirely to the protocol. Diagnostics go to stderr, with safe static startup failures. The invoking process and its environment are trusted; a stdio grant authorizes one scope for that server process. No tenant claim or bearer value in tool arguments can change it. A separate process/configuration is required for another stdio scope.

Both serve and check accept an explicit --config or OOMP_MCP_CONFIG. No .env file is loaded. Relative database paths in hand-written configurations resolve against the configuration file's directory. Generated database paths are absolute. --transport is validated against grants; it cannot silently fall back to stdio authority.

## Streamable HTTP: local preissued bearer profile

Generate a separate HTTP configuration:

~~~powershell
.\.venv\Scripts\python.exe -m oomp mcp config --format server --transport streamable-http --config ".\data\mcp-http.json" --db ".\data\memory.sqlite3" --tenant demo --namespace personal --principal local-http-host | Set-Content -Encoding UTF8 ".\data\mcp-http.json"
~~~

The generated configuration names OOMP_MCP_TOKEN; it contains no credential value. Provision a random URL-safe secret of at least 32 bytes through the host's secret store or a process environment. For a temporary local PowerShell session, this captures a generated value without displaying it:

~~~powershell
$env:OOMP_MCP_TOKEN = (& .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))")
.\.venv\Scripts\python.exe -m oomp mcp check --config ".\data\mcp-http.json"
.\.venv\Scripts\python.exe -m oomp mcp serve --config ".\data\mcp-http.json" --transport streamable-http
~~~

The client must receive that same value through its trusted secret mechanism and send Authorization: Bearer VALUE on every request. It is never a URL query parameter. Restarting with a newly generated token requires updating clients. Stop with Ctrl+C. Revoke/rotate local grants by updating the trusted configuration/environment and restarting. Optional expires_at also disables a grant without restart.

Default endpoint is http://127.0.0.1:8765/mcp. Only 127.0.0.1 or ::1 may bind. Host must exactly match the configured literal address and port. Absent Origin is allowed; a supplied Origin must exactly match the configured origin allowlist, which defaults to the server's own origin. No wildcard ports, proxy trust, tunnels, browser CORS integration, TLS listener or public bind is supplied.

Generate an HTTP host-entry illustration:

~~~powershell
.\.venv\Scripts\python.exe -m oomp mcp config --transport streamable-http --config ".\data\mcp-http.json"
~~~

It prints url plus an Authorization header placeholder. The placeholder is deliberately not executable secret interpolation. Host JSON schemas and secret substitution differ; adapt this entry to the selected host's documentation. OOMP does not patch installed host applications, claim universal host support, provide an OAuth issuer or simulate OAuth consent.

For SDK Client HTTP usage:

~~~python
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

async with httpx2.AsyncClient(
    headers={"Authorization": "Bearer " + trusted_token}, trust_env=False
) as http:
    async with Client(streamable_http_client(endpoint, http_client=http)) as client:
        tools = await client.list_tools()
        result = await client.call_tool("memory.retrieve", {
            "query": "What project was the user developing?",
            "token_budget": 1200,
        })
        evidence = result.structured_content
~~~

The installed SDK v2 uses httpx2, not the older httpx client type.

## Stable tool contract

Dotted names work in the tested SDK. Discovery provides JSON input/output schemas and read-only/idempotency hints. All argument models reject extra fields. Requests cannot provide tenant_id, namespace, principal_id or an AuthorizedScope.

| Tool | Inputs and behavior |
| --- | --- |
| memory.retrieve | query (1–4096 chars), mode lexical/semantic/hybrid, max_results <=20, token_budget <=32768, known_at, valid_at/as_of, historical, allow_degraded and bounded Stage 5 graph controls. Calls the existing RetrievalEngine. |
| memory.expand | memory_id, max_depth 0–2, max_nodes 1–32, allowed_relationships, known_at, valid_at, historical. Reuses Stage 4 traversal inside one scoped SQLite read snapshot. Up to 64 edges, 400 neighbor work, 1000 returned edge proofs, cycle-safe. |
| memory.get_source | Required memory_id, optional linked event_id, known_at, include_content (default false), limit <=32 (default 8), after_event_id. Returns actual supporting events only. next_event_id is the last emitted ID to pass as after_event_id; null means finished. |
| memory.status | Empty object. Scoped canonical/lexical/vector coverage, configured embedding identity/modes and durable queue counts. No paths, tenant directory, credentials or raw content. Worker operation is explicit_separate_process; started_by_server is false. |
| memory.ingest | Absent from read-only profiles/catalogs. Trusted profile plus grant capability plus exact host approval are required. Appends immutable Stage 2 evidence and Stage 6 durable outbox intake, with no direct canonical or graph mutation. |

Retrieval returns MemoryEvidence, aligned source IDs/references, scores/reasons, paths with actual edge evidence and direction, temporal status, degraded flags, warnings, trace and context_packet. Unknown validity remains uncertain. Current retrieval uses the existing current-time policy; historical=true without valid_at requests structural history, and known_at independently bounds recording/evidence knowledge. Explicit graph expansion excludes nodes outside a requested validity instant or with no endorsed proof. Use historical=true to inspect old lineage whose endpoints are no longer current.

Source reads require an accessible memory and a genuinely linked, visible event. A guessed arbitrary event ID is insufficient. Raw event content additionally requires the read_source capability and include_content=true. Event metadata is not returned. Locators are evidence strings, never filesystem/URL fetch instructions. Content and provenance are marked untrusted data.

### Evidence budget and wire overhead

The disclosed utf8_bytes_upper_bound_v1 counter still counts only the complete serialized context_packet, including its packet envelope, provenance and selected paths. estimated_token_count equals that packet's UTF-8 byte count and stays <=token_budget. A budget too small for evidence yields the existing empty packet/zero count behavior.

The outer retrieval diagnostics, structuredContent, SDK text fallback, server metadata, HTTP framing and host/system prompts are outside token_budget. The SDK intentionally supplies both text and structured output. A host should use one representation and separately budget its final model prompt. No stage claims an enlarged native context window.

Server defaults also limit HTTP bodies/tool argument serialization to 131072 bytes, tool results to 262144 bytes before SDK-added metadata, concurrent tool calls to 4 and HTTP application requests to 8. Both byte limits can be configured up to 1 MiB. Header limits are 64 headers, 16 KiB aggregate and 8192 bytes per value. The CLI server adds uvicorn connection/header bounds. Oversized results fail explicitly; proof is not silently clipped.

## Trusted ingestion and actual intake state

Use a separate intentionally selected profile and distinct grant. Example trusted grant configuration:

~~~json
{
  "grant_id": "approved-host",
  "principal_id": "trusted-application",
  "tenant_id": "demo",
  "namespace": "personal",
  "capabilities": ["read", "ingest"],
  "bearer_token_env": "OOMP_WRITE_TOKEN",
  "ingest_approval_key_env": "OOMP_HOST_APPROVAL_KEY",
  "ingest_source_type": "user",
  "ingest_source_system": "approved-chat",
  "ingest_event_types": ["user_message"]
}
~~~

Set server profile to trusted-ingest and put the grant in http_grants, or use it as the single stdio_grant. For stdio the bearer field is unnecessary. Approval and bearer keys must be separate generated secrets. Never supply the approval key to a model, tool argument or client configuration. The trusted host must check the original source role, provenance and actual user/application approval policy before signing.

The host-only Python helper oomp.mcp.authorization.approve_ingestion signs a validated IngestPayload and Grant with HMAC-SHA256. The signature covers exact event ID, idempotency key, content, event type, provenance, occurrence time, principal, tenant/namespace, allowed source policy, nonce, issue/expiry times and a domain separator. TTL is 1–300 seconds (default 60), with at most 30 seconds future clock tolerance. MCP has no tool for minting approval.

A host assembles the payload, obtains its approval, calls approve_ingestion(grant, payload, secret), and submits payload.model_dump(mode="json") plus approval.model_dump(mode="json") as the approval field. OOMP proves possession of the separate host key; it cannot certify that a human actually clicked an approval button. The host owns that policy. Key holders can approve writes.

The server assigns tenant, namespace, source role, current ingested_at and an ingested_by audit principal. source_reference.source_system and event_type must agree with configured policy. Clients cannot inject source_type, metadata, ingested_at, scope or principal. System-source ingestion is unavailable.

An accepted result says durably_stored and returns the actual persisted event ID, current outbox pending/dispatched state and latest extraction job status when present. It never equates durable acceptance or dispatch with successful extraction. Equal retries use Stage 2 idempotency and return the original event; changed evidence conflicts. Approval nonces are payload-bound, not a separate durable one-use ledger: identical replay while approved is deliberately harmless and idempotent. After expiry a host can approve the same payload again.

Run workers separately using existing oomp mind commands. Automatic extraction, review acceptance, erasure, SQL, entity merging, arbitrary graph updates and scope mutation are unavailable as tools. Retraction and privileged erasure remain local administrative workflows.

## Demonstrate and troubleshoot

~~~powershell
.\.venv\Scripts\python.exe examples\stage7_mcp_client.py --transport stdio
.\.venv\Scripts\python.exe examples\stage7_mcp_client.py --transport streamable-http
.\.venv\Scripts\python.exe -m pytest -v
~~~

Each demo creates a synthetic temporary database at the current schema v6, explicitly runs the Stage 6 worker, appends 105 unrelated later turns, connects using an actual SDK Client, discovers tools, retrieves early project evidence, reads provenance, expands the graph and cleans up the server/files. It does not use your real memories.

For a connection failure, run mcp check with the same Python executable, config and process environment as the host. Confirm the optional SDK, existing supported schema v6 database (upgrade older databases explicitly before connection), current grant, correct transport and exact HTTP host/port/token. For empty results, inspect scoped extraction/index readiness through existing local CLI commands. Missing semantic coverage fails explicitly unless hybrid allow_degraded=true was requested. No model is installed automatically. Optional embedding configuration uses the existing loopback Ollama adapter; live embeddings remain unverified without an installed model.

## Reviewed upstream APIs

- [Official SDK v2 changes](https://py.sdk.modelcontextprotocol.io/whats-new/): MCPServer and current client APIs.
- [Official SDK tools](https://py.sdk.modelcontextprotocol.io/servers/tools/) and [structured output](https://py.sdk.modelcontextprotocol.io/servers/structured-output/).
- [SDK ASGI lifecycle](https://py.sdk.modelcontextprotocol.io/run/asgi/) and [authorization](https://py.sdk.modelcontextprotocol.io/run/authorization/).
- [Client transports](https://py.sdk.modelcontextprotocol.io/client/transports/): actual stdio and custom HTTP client use.
- [MCP 2026-07-28 transport specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports).

See [MCP security](mcp-security.md), [executed validation](stage7-validation.md), and the [39-item completion report](stage-7-report.md).
