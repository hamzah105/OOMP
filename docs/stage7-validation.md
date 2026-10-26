# Stage 7 validation

Client date: 2026-10-27. Workspace: D:\Desktop\OOMP. Windows PowerShell, Python 3.11.4, SQLite 3.42.0 with real FTS5.

## Executed results

| Check | Result |
| --- | --- |
| Git baseline before production edits | Clean main, d911dc99a03cc8303bce8c43b2a34dfcf60bdfc1 (Implement OOMP Stage 6) |
| Stage 1–6 baseline | 321 passed in 227.79s (3:47) |
| Complete final verbose suite | **392 passed in 365.59s (6:05)** |
| New Stage 7 cases | **71**: 18 CLI/configuration, 53 real-client integration/security cases |
| Earlier regressions | All 321 passed; all 26 earlier test files byte-for-byte unchanged |
| Schema preservation | SQLite remains v5; migration SQL tuples 1–5 have unchanged SHA-256 hashes |
| Editable optional installation | pip install --no-build-isolation -e ".[dev,mcp]" succeeded |
| Compilation | python -m compileall -q src tests examples succeeded |
| Dependencies | pip check: No broken requirements found |
| Installed entry point | oomp.exe --version: oomp 0.1.0 |
| Doctor | Stage 1 readiness OK; optional MCP SDK 2.3.0 ready; server/worker not started or falsely asserted running |
| Explicit readiness | Installed oomp.exe mcp check succeeded for configured stdio and HTTP synthetic v5 databases |
| stdio demonstration | Actual SDK Client; modern 2026-07-28; early project recovered after 105 unrelated turns; actual provenance and graph |
| HTTP demonstration | Actual SDK Client over loopback TCP, bearer authentication, same long-history recovery |
| Compatibility | SDK modern Client and legacy-mode HTTP discovery/tool invocation passed; external desktop hosts unverified |
| Final test failures / warnings | None |
| Diff whitespace | git diff --check passed |

Installed versions: oomp-memory 0.1.0; mcp 2.3.0; mcp-types 2.3.0; Pydantic 2.14.1; pytest 9.1.1; anyio 4.15.1; httpx2 2.16.0; uvicorn 0.54.0.

Ignored local evidence is recorded under .test-artifacts: stage7-baseline-20261027.txt, stage7-baseline-manifest.json, stage7-final-pytest.txt, stage7-final.xml, stage7-audit.json, stage7-demo-stdio.json and stage7-demo-http.json. PowerShell text redirection/Tee-Object uses UTF-16 in this environment. These artifacts and temporary databases are not proposed Git additions.

## What the client tests establish

Actual SDK Client contexts launch stdio subprocesses and connect through real loopback TCP sockets. The core demonstration does not depend on direct Python handler invocation: each transport retrieves an early Stage 3-extracted project memory after 105 later unrelated events and verifies its actual source and bounded packet. The standalone example also explicitly runs the existing Stage 6 worker before connecting.

Discovery includes typed input/output schemas and read-only hints. All four default tools execute over the protocol. Source metadata is the default, raw source requires read_source, and only visible supporting events can be selected or paginated. Graph output verifies actual edge IDs, orientation and evidence. Current/historical/known-at and source-retraction behavior are exercised.

Tenant and namespace isolation includes guessed foreign IDs, extra scope/principal fields, identical memory/source IDs across tenants and unchanged authorized ranking/trace after another tenant's corpus grows. Concurrent clients use independent grants. One disconnects while other reads and a separate worker writes; reopening the server preserves canonical/index state without reconnect-created indexes.

Trusted-ingest tests use a separate profile and writer grant. They check capability-specific discovery, exact HMAC host approval, missing/bad/expired/future/cross-grant proofs, role/provenance policy, principal/scope/metadata injection, equal retry and conflicting replay. Accepted writes create real Stage 2 events/outbox rows; extraction is absent until an explicit existing worker is run. Replies then report the actual completed extraction job.

Network negatives include missing/invalid/expired bearer credentials, Host rebinding, invalid Origin, duplicate Authorization, unsupported method, malformed JSON, excessive headers, declared/chunked oversized bodies and modern protocol/method/name header mismatches. Missing scope/configuration or weak/duplicate/shared secrets fail closed. Resource/concurrency limits and private exception suppression are tested. SDK resource/prompt catalogs remain empty; unused subscriptions are disabled.

SDK-free core imports and doctor/help are validated with external MCP imports deliberately blocked. No model or internet service is used by the tests. Synthetic credentials are fixtures, not live secrets.

## Reproduce on Windows

~~~powershell
$env:TMP = Join-Path $PWD ".tmp"
$env:TEMP = $env:TMP
.\.venv\Scripts\python.exe -m pip install -e ".[dev,mcp]"
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m compileall -q src tests examples
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\oomp.exe --version
.\.venv\Scripts\oomp.exe doctor
.\.venv\Scripts\python.exe examples\stage7_mcp_client.py --transport stdio
.\.venv\Scripts\python.exe examples\stage7_mcp_client.py --transport streamable-http
~~~

Set TMP/TEMP to an existing writable local directory if using a different checkout. Follow [MCP integration](mcp-integration.md) to initialize an intended database explicitly, generate a fixed-scope configuration, run mcp check, and print a host configuration. The examples themselves create temporary synthetic storage and require no personal data.

Manual assessment still needed: paste the generated absolute stdio command into a chosen installed AI host, confirm discovery and evidence presentation, configure that host's supported HTTP secret injection if applicable, check its actual prompt overhead and stop/restart it with PowerShell Ctrl+C. No installed desktop host, browser OAuth client, IPv6 listener, proxy/TLS deployment or live Ollama embedding model was tested. The configured IPv6 option is not a compatibility certification.

## Limits and stage boundary

The local preissued-bearer profile has no OAuth discovery/issuer, public endpoint, distributed deployment or encryption. Host-held approval keys represent host policy, not an independently verified human click. Approval nonces are payload-bound while equal replay is made safe by existing durable idempotency; there is no new nonce ledger. Packet budgets exclude the SDK envelope/text duplicate and host prompt.

Schema migrations and earlier tests are unchanged. No TRACE.AI files, Stage 8 adapter, benchmark or release system was added. No commit or push was performed. Implementation stops at Stage 7 for user inspection; see the [39-item report](stage-7-report.md).