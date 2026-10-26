# Stage 7 completion report

Client date 2026-10-27. Stage 7 only. **392 tests passed in 365.59s**, including all **321** earlier cases and **71** new cases; no final test warnings. SQLite remains v5. No commit, push or TRACE change.

1. **Workspace and Git baseline.** Worked only in D:\Desktop\OOMP. Verified a clean main branch at d911dc99a03cc8303bce8c43b2a34dfcf60bdfc1, Implement OOMP Stage 6. Ran all 321 baseline cases before production edits: 227.79s. No existing user changes required preservation.

2. **Files created (15).** Eight optional adapter files: src/oomp/mcp/__init__.py, configuration.py, contracts.py, authorization.py, errors.py, service.py, server.py and cli.py. Four documents: docs/mcp-integration.md, docs/mcp-security.md, docs/stage7-validation.md and this docs/stage-7-report.md. Added examples/stage7_mcp_client.py, tests/test_stage7_cli.py and tests/test_stage7_mcp.py.

3. **Files modified (11).** pyproject.toml; src/oomp/cli.py; src/oomp/storage/graph_store.py, retrieval_store.py and mind_store.py; README.md; docs/architecture.md, security-model.md, retrieval.md, background-mind.md and roadmap.md. No earlier test file, domain/extraction algorithm, migration SQL or package version changed.

4. **SDK version installed.** Official mcp 2.3.0 and mcp-types 2.3.0, verified against the official current SDK and installed in the workspace virtual environment. Optional extra constrains mcp>=2.3.0,<2.4 and uvicorn>=0.31.1,<1. Editable installation with dev,mcp succeeded. Base package runtime dependency remains Pydantic.

5. **Protocol and compatibility.** Actual clients negotiated modern protocol 2026-07-28. SDK Client(mode="legacy") also completed HTTP discovery/status against the stateless server. Dotted names work. This certifies the exercised official SDK paths, not arbitrary versions, languages or desktop hosts.

6. **Architecture.** SDK-independent trusted configuration/wire models/host approvals feed a thin MemoryService. A public MCPServer subclass registers real SDK functions, provides grant-specific discovery, validates original arguments, bounds calls/results and sanitizes errors. Official SDK implements protocol parsing, serialization and transports; no custom JSON-RPC server was written. Core modules import no SDK types.

7. **stdio.** Explicit fixed process grant, absolute config/database resolution, SDK-managed stdin/stdout lifecycle and no OOMP stdout banners. Missing configuration/scope/database fails without initialization. Actual subprocess clients exercise discovery, evidence, sources, graph and errors, then disconnect cleanly. Invoking process/environment are trusted.

8. **HTTP.** SDK stateless Streamable HTTP app at /mcp, JSON responses, exact SDK lifespan delegation and official bearer/auth-context middleware. uvicorn binds literal loopback with proxy trust/access logs disabled and resource bounds. Real TCP clients, concurrent contexts and separate CLI process restart were tested; listeners are cleaned up.

9. **Tool registry.** Four default tools: memory.retrieve, memory.expand, memory.get_source and memory.status. Optional memory.ingest is registered only under trusted-ingest and advertised only to ingest-capable grants. Discovery carries strict schemas, read-only/idempotency annotations and private zero-TTL hints. No erasure, SQL, merge, scope mutation or conflict approval tool. Resources/prompts are empty/unavailable; subscriptions disabled.

10. **Retrieval.** Uses Stage 5 RetrievalEngine with server-owned scope, existing lexical/semantic/hybrid, graph/temporal policy, provenance, degraded flags and packing. MCP tightens query/results/graph bounds. Returns evidence rather than a final answer. token_budget covers context_packet only; SDK structured/text duplicates, diagnostics and host prompts need separate accounting.

11. **Graph expansion.** Reuses Stage 4 traversal through a generic connection helper, within one retrieval read snapshot. Limits depth 2, nodes 32, edges 64, neighbor work 400 and returned edge proof 1000. Presentation paths contain actual IDs, relationship types, directions, provenance and validity. Cycles, temporal eligibility, current retraction and bounded truncation preserve existing policies.

12. **Source access.** Requires an accessible memory and actual linked visible proof. Optional event filtering cannot fetch unrelated evidence. Defaults to metadata/reference fields with content null; raw event text needs read_source plus include_content. Bounded pagination returns next_event_id for after_event_id. Locators are never fetched and raw event metadata is omitted.

13. **Operational status.** Scoped canonical/lexical/vector coverage, optional embedding identity, available modes and durable queue counts. No database path, credentials, global tenant directory or private content. Explicitly reports that this server starts no worker and workers operate separately; it does not claim a worker is running.

14. **Ingestion authorization.** Requires trusted-ingest profile, authenticated/fixed host grant, ingest capability, coherent configured source/event policy and exact short-lived host HMAC approval. The separate key is never exposed by an MCP signing tool. The host must verify original role and its approval policy before signing. OOMP authenticates host-key possession, not a human click. Equal replay remains durably idempotent; nonce proofs have no separate one-use ledger.

15. **Tenant/namespace mapping.** Trusted grants produce AuthorizedScope. Tool arguments cannot provide tenant, namespace, principal, source role or authorization objects. HTTP subject/resource/grant matching is request-local; no transport session supplies memory identity. Cross-tenant equal IDs and ranking remain isolated.

16. **Authentication configuration.** Stdio has one explicit grant. HTTP requires configured environment-backed random bearer secrets for all grants, no anonymous fallback. Endpoint audience, principal, capabilities and optional expiry are checked. Weak syntax, missing/duplicate secrets or bearer/approval key reuse fail closed. Configuration generators emit names/placeholders, never credential values; no arbitrary config code/.env is loaded.

17. **Origin/Host protections.** Literal 127.0.0.1 or ::1 only. Exact Host including configured port, exact local Origin allowlist and SDK DNS-rebinding checks. Duplicate critical headers, excess header count/bytes, URL query credentials, unsupported path/method and excess declared/chunked body rejected. Browser CORS/OAuth and proxy/public deployment are not provided.

18. **Structured outputs.** Pydantic return models generate SDK output schemas and actual structuredContent. Text fallback is the SDK's normal duplicate representation. Evidence is marked untrusted; validity uncertainty, current/history and degraded state are preserved. Oversized results fail explicitly instead of clipping proof or inventing success.

19. **Errors.** Stable structured tool codes cover invalid_parameters, unauthorized, forbidden, not_found, conflict, storage_unavailable, embedding_unavailable, resource_limit, busy and internal_error. Static messages omit private input, storage paths, SQL, token values and tracebacks. SDK retains protocol-level error semantics; HTTP authentication/security uses appropriate status codes.

20. **Mind integration.** Approved ingest calls existing Stage 2 append, atomically creating the real v5 outbox. Reply contains persisted event ID, pending/dispatched state and actual latest extraction job status. No automatic worker, extraction or review acceptance. Explicit worker execution changes reported state and makes new canonical evidence retrievable. Concurrent worker writes/replay retain existing WAL and idempotency behavior.

21. **Database/schema.** No migration or new table. SQLite remains schema v5; migration SQL tuples 1–5 match captured baseline hashes. Generic additions only: connection-aware optional temporal traversal, bounded read-session traversal and scoped event_intake_status inspection. Existing event immutability, scoped proof and Stage 6 privacy remain authoritative.

22. **CLI.** Added oomp mcp serve, config and check with explicit config/transport validation and safe nonzero errors. Config generation works without the SDK. Doctor optionally reports SDK readiness without requiring it or asserting a server. All old CLI tests still pass. Installed Windows executable readiness succeeded for stdio and HTTP.

23. **Host configurations.** Generates valid mcpServers stdio JSON using absolute Python/config paths and argument arrays. HTTP illustration contains actual configured URL and a literal host-supplied-secret placeholder. It never edits host settings or prints environment values. Hosts differ in HTTP/secret configuration; these examples are not a universal schema claim.

24. **Successful stdio demo.** examples/stage7_mcp_client.py --transport stdio explicitly seeds synthetic events, runs Stage 6, appends 105 unrelated turns and connects with SDK Client. Recovered User is developing a project called OOMP with early-event provenance, bounded bytes and actual graph evidence. Temporary storage/subprocess cleaned up.

25. **Successful HTTP demo.** The same example with --transport streamable-http launches a separate loopback CLI server, uses a generated process-local bearer credential and performs actual SDK discovery/retrieval/source/expansion/status. It recovered the early project with protocol 2026-07-28, and cleaned up the process and temporary files.

26. **Multi-tenant evidence.** SDK tests reject guessed foreign memory/source IDs, foreign graph roots and scope/principal injection. Identical source/memory IDs in two tenants produce only each authorized partition's evidence. Growing another tenant's corpus leaves Tenant A memory ranking/trace unchanged. Separate namespace and concurrent credential tests pass.

27. **Negative/security tests.** Bad/expired/missing tokens; forbidden raw source and hidden writes; unsafe bind/origin configuration; invalid Host/Origin; duplicate Authorization; header/body bounds including chunked; protocol routing mismatch; malformed JSON/typed values; approval missing/tampered/expired/future/cross-grant; role/source policy; injected scope/audit metadata; conflicting replay; resource/busy/error disclosure; missing database non-creation and source retraction.

28. **New test count.** 71 new cases: 18 CLI/configuration and 53 SDK integration/security cases. Parameterization covers materially different authorization and boundary failures. No earlier test was edited or weakened.

29. **Total passing tests.** Final complete python -m pytest -v: **392 passed in 365.59s (6:05)**. Verbose output and JUnit are recorded in ignored .test-artifacts. Compilation, pip check, installed version/doctor, two readiness checks and both demos also passed.

30. **Previous regressions.** All 321 Stage 1–6 cases pass, including the 79 original foundation cases. All 26 baseline test files remain byte-for-byte identical. Stage 1 test SHA-256 remains 8bd1376d546a4eb56bb4d32fdf0ee62553de95ab888ab56eef1467add6c18600. Migration tuple hashes remain identical.

31. **Failures/warnings.** No failures, errors, skips or warnings in the final installed-extra suite. Development fixture/signature/enum assertions were corrected before final validation; no known failing test remains. Live embeddings and named external hosts are unverified rather than marked passing. pip's optional upgrade notice did not affect dependency checks.

32. **Windows manual commands.** From this checkout, run .\.venv\Scripts\python.exe -m pip install -e ".[dev,mcp]", .\.venv\Scripts\python.exe -m pytest -v, .\.venv\Scripts\oomp.exe doctor and both examples listed above. Follow the integration guide's explicit storage init, mcp config and mcp check commands for your own scope, then test the generated absolute command inside your chosen host. Actual host UI, HTTP secret injection and interactive Ctrl+C assessment remain manual.

33. **Documentation.** Added [connection/configuration/tool guide](mcp-integration.md), [MCP security model](mcp-security.md), [executed validation/manual checklist](stage7-validation.md) and this report. Updated README, architecture, security, retrieval, background-mind and roadmap with the implemented boundary and remaining limits. Official SDK/API/spec links are included; no universal client claim.

34. **Deployment limits.** Local machine, plaintext SQLite, trusted administrator, optional loopback model provider and generated preissued bearer profile only. No OAuth issuer/discovery, TLS/proxy/public service, encryption, multi-server coordination, automatic secret store, distributed revocation or per-principal rate controls. Outer MCP/host overhead is outside evidence budget. IPv6 option and live Ollama inference were not exercised.

35. **Actual external client compatibility.** The official SDK Client is an actual external protocol client: stdio subprocess and TCP HTTP both exercised; legacy-mode HTTP also passed. No Claude Desktop, Cursor, VS Code/Copilot, other installed AI host, browser client or other language SDK was available/tested. Compatibility with them remains unverified.

36. **Stage 8 prerequisites.** User inspection/acceptance of this boundary first; then separately inspect TRACE.AI's actual supported client APIs, host lifecycle and source-role/approval facilities. Define authenticated scope, secret provisioning, prompt-budget accounting, provenance/temporal presentation and failure handling for that external adapter. OOMP core must stay independent. No TRACE inspection or implementation was performed in this milestone.

37. **Git status.** HEAD remains d911dc9 on main. Final intended changes are the 11 modified and 15 new files listed above; temporary credentials/configuration, database/sidecars, venv, wheels, logs and test artifacts remain ignored. No unrelated changes, commit, push, remote creation, reset, history rewrite or global Git change.

38. **TRACE untouched.** No TRACE.AI files or workspace were opened or modified. No TRACE dependency/import/adapter was added. All writes were within the OOMP workspace and authorized temporary artifacts.

39. **Stage boundary and stop.** Only Stage 7 was implemented. Stage 8 integration, Stage 9 research benchmarks and Stage 10 release automation remain planned. Work stops here for user inspection and manual assessment; no automatic commit or push.