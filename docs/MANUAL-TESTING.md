# Manual submission walkthrough

This guide separates the new public managed demonstration from the preserved
acceptance runs. The new demonstration uses five newly authored fictional texts,
rules-only extraction and no model or embedding provider. It starts only its own
disposable OOMP MCP/Mind processes. It does not start TRACE, MongoDB or Ollama,
read a saved conversation, select a normal private profile or reuse a Gate A
fixture. The independent client call inside it is a P5 example smoke check;
the accepted Gate C record remains unchanged.

## Prerequisites and a fresh Windows directory

Use the reviewed checkout and the source-matched guarded Python 3.11 launcher
verified below. It reuses the already installed approved dependencies, including
MCP 2.3, and pins this checkout as its source. These commands install or
download nothing. Run one acceptance/demo workload at a time after the current
resource preflight permits it; do not overlap a model evaluation.

```powershell
Set-Location 'D:\Desktop\OOMP'
$py = 'D:\os-sub-1106\test311\Scripts\python.exe'
& $py -B -m oomp --version
New-Item -ItemType Directory -Path '.test-artifacts' -Force | Out-Null
$demo = 'D:\os-demo-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff')
& $py -B examples\submission_demo.py --directory $demo
```

`--directory` is mandatory. Its parent must exist and the target must be new.
Use a short path on Windows. An existing target is refused; choose a new name
when preserving a failed attempt. The demonstration retains its fictional
database and private profile under `$demo\p`, including generated credentials.
Keep that directory private and out of source archives; inspect the credential-free
JSON reports individually instead of printing `secrets.json` or environments.

The script previews onboarding, creates one fresh dedicated namespace/principal,
explicitly enables `--context --extraction-mode rules --no-provider`, and grants
signed user-event intake only for these fictional sources. It then runs managed
`up --background`, bounded Mind readiness, actual object CLI operations, MCP
context/source calls, the public SDK host, full diagnostics, status, restart and
`down`. It verifies that its owned listener is released. It does not grant
`read_source`; linked provenance uses `memory.get_source(include_content=false)`.

## Expected behavior and observation status

The new demo **PASSED** in `D:\os-demo-1107-r1` in 45.234 seconds under the
owned-process controller. The following table records that actual run. To inspect
it without rerunning the demo, set `$demo = 'D:\os-demo-1107-r1'`.
For another owner-run demonstration, use a new directory and that attempt's
`acceptance.json`, `progress.jsonl`,
`context-*.json`, object reports, diagnostics and lifecycle reports as evidence.
A nonzero exit or absent final `acceptance.json` is not a pass.

| Check | Expected result | New demo observation |
| --- | --- | --- |
| Sources | Five signed fictional user sources; source sessions S0/S1 | PASS; worker drained, 15 completed jobs, zero failed |
| Project recall | LUMENDEMO, proof `submission-project` | PASS; `found_relevant_evidence`, 1,009 bytes |
| Personal alias | Cedar Finch, proof `submission-alias`; project name cannot substitute | PASS; 983 bytes |
| Reply style | Concise numbered steps, proof `submission-style` | PASS; 1,028 bytes |
| Relocation | Tentative Alder Bay → Pine Harbor and later cancellation; both original sources, uncertainty retained | PASS; `candidate_uncertain`, three proofs, 2,279 bytes; current-city recall not separately certified |
| Unknown pet | Empty evidence and packet; no relevant evidence or explicit uncertainty | PASS; `no_relevant_evidence`, zero bytes |
| Small packet budget | Long bounded query, 96-byte packet allowance; whole evidence excluded or honest uncertainty, zero clipped evidence | PASS; `budget_excluded`, zero bytes |
| Provenance/accounting | Original source references, role/event identity, Unicode code-point bounds and exact UTF-8 packet byte count | PASS; six linked-source metadata checks |
| Object map | Explicit build/tree/find/inspect of source-backed LUMENDEMO object | PASS |
| Public SDK host | Context and metadata-only source check through its reader environment | PASS; one proof, 1,009 bytes |
| Restart/shutdown | Same original proofs after restart; owned services stopped | PASS; same proof, listener released |

Full doctor returned 24 PASS, zero WARN/FAIL and four NOT TESTED checks for the
deliberately unselected model/provider. Six additional read-only CLI commands
(version, config, tree, inspect, find and TRACE onboard dry-run) passed using the
same launcher. The demo's longer query exercises evidence accounting, not an
interactive long chatbot conversation.

The launcher path above is specific to this preserved workstation validation.
It is not included in the submission archive. On another machine, install the
included wheel with the declared `[mcp]` dependencies in a fresh Python 3.11/3.12
environment, use that environment's Python for `$py`, and run from the extracted
source root containing `examples`. Optional dependency installation may require
an approved package index/cache; no model download is required. Current clean
install evidence distinguishes core-only checks from the reused-SDK demo.

Source-reference sessions are `submission-S0` and `submission-S1`. The report
labels fresh query requests **S2** for explanation; S2 is not a tool argument or
an authenticated session identity. Each MCP request opens a fresh official-SDK
client lifecycle and reads the previously ingested sources. This demonstrates
retrieval across source sessions, not a new browser conversation or a long real
LLaMA chat. The 96-byte field is a packet-byte allowance despite its inherited
`token_budget` name; it is not measured tokenizer output or a model context size.

```powershell
$result = Get-Content -LiteralPath (Join-Path $demo 'acceptance.json') -Raw | ConvertFrom-Json
$result | Select-Object result, source_events, extraction_mode, model_calls, diagnostics_ok, owned_services_stopped
$result.queries | Select-Object query_id, status, packet_bytes, token_budget, source_event_ids
$scope = @('--db', $result.database, '--tenant', $result.scope.tenant, '--namespace', $result.scope.namespace, '--principal', $result.scope.principal)
& $py -B -m oomp memory tree @scope --depth 10 --limit 100 --json
& $py -B -m oomp memory inspect $result.project_object_id @scope --show-provenance --json
& $py -B -m oomp memory find LUMENDEMO @scope --json
```

These object commands are trusted local administrative operations over this
fresh fictional database. A selected principal is not remote authentication.
They do not build or repair a projection implicitly; the demo explicitly called
`memory build-map` first. Original source claims remain attributed claims, not
verified external facts. A passing `doctor` means no FAIL checks; an unselected
provider or unexercised host login can correctly remain NOT TESTED.

## Inspect and exercise the independent public host

The completed demo has already stopped its services. The following optional
operator actions restart only that same disposable profile, inspect readiness,
run the public client and stop it again:

```powershell
& $py -B -m oomp config --profile submission --home $result.profile_home --json
& $py -B -m oomp up --profile submission --home $result.profile_home --background
& $py -B -m oomp status --profile submission --home $result.profile_home --json
& $py -B -m oomp doctor --profile submission --home $result.profile_home --full --json
$env:MCP_ENDPOINT = $result.mcp_endpoint
$client = 'D:\Desktop\OOMP\examples\generic_context_host.py'
& $py -B -m oomp host --profile submission --home $result.profile_home --approve-host -- $py -B $client 'What project did I mention earlier?' --token-env OOMP_SUBMISSION_READ_TOKEN --get-source
& $py -B -m oomp down --profile submission --home $result.profile_home
```

The CLI passes a private reader environment to the reviewed host command. No
credential is pasted into the command, URL or output. The client imports no
OOMP/TRACE modules and reads no database. It checks packet/version/proof
structure and prints counts/status only. See [generic host usage](generic-context-host.md)
for direct endpoint/environment use and its source-authority limitations.
`--context` / `--no-context` are explicit managed configuration choices; old and
default profiles keep the tool disabled. Stop services before configuration changes.

## TRACE connection review: read-only plan only

TRACE's public integration instructions were read at
`D:\Desktop\VU BS-CS\CS619\TRACE\docs\oomp-integration.md`, together with
`docs\oomp-p4b-fictional-quickstart.md`, `docs\P4B-implementation-plan.md` and
`docs\product-milestone-P4B-report.md`. Its `.env` and private MongoDB were not
read or modified. A root `.env.example` was absent during this inspection.

The following exact command previews a **read-only configuration plan** against
that public project path. Its owner ID and scope are fictional placeholders;
they do not identify or authorize an existing TRACE user. The fresh home remains
uncreated because `--dry-run` is used. The command starts no external service,
creates no credential and performs no owner login:

```powershell
$tracePlanHome = 'D:\os-trace-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff')
& $py -B -m oomp onboard --profile trace-review --home $tracePlanHome --project 'D:\Desktop\VU BS-CS\CS619\TRACE' --adapter trace --owner-id '000000000000000000000001' --tenant submission-trace-review --namespace dedicated-review --principal fictional-owner --mode read-only --transport streamable-http --port 18765 --context --extraction-mode rules --no-provider --no-mind --dry-run --json
```

For a separately authorized interactive deployment, TRACE's existing trusted
server environment selects `TRACE_OOMP_RETRIEVAL_API=context_v1` and an existing
enabled `TRACE_OOMP_MODE` (`retrieve` or `retrieve_and_ingest`). The selector alone
does not enable memory. The public guide documents `TRACE_OOMP_URL`,
`TRACE_OOMP_TRACE_ORIGIN`, the pinned `TRACE_OOMP_OWNER_ID`, dedicated tenant /
namespace / principal mapping, `TRACE_OOMP_READ_TOKEN` and the separate
`TRACE_OOMP_OWNER_KEY`. Reference credential names and trusted secret provisioning;
never copy real values into this guide or substitute an arbitrary HTTP owner ID.
Managed TRACE profile `host` environments supply the existing references without
editing TRACE `.env`. Raw-source permission is unnecessary because TRACE checks
original records against its authoritative owner/session/role Mongo sources.

Actual authorized TRACE ↔ OOMP MCP evidence remains the preserved Gate A run.
An interactive browser TRACE recall test and physical MongoDB connection were
**NOT REPEATED in this submission sprint**. The new public managed demo does not
certify login, TRACE routing, MongoDB, final model answers, or general multi-user
deployment. Use the accepted Gate A report for that recorded authentication /
provenance evidence, and TRACE's own guide for any separately authorized live
deployment. The automated demo never launches TRACE.
