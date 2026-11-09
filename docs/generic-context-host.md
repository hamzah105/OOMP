# Generic context host example

[`examples/generic_context_host.py`](../examples/generic_context_host.py) is an
independent read-only host using the official installed MCP 2.3 SDK public
`Client`, `streamable_http_client` and `httpx2.AsyncClient` APIs. It imports no
OOMP modules, starts no services or models, opens no database and writes no files.
The existing `[mcp]` environment is required; the example installs nothing.

It calls `memory.context` and, with `--get-source`, checks metadata for the first
proof using `memory.get_source` with `include_content: false`. It prints only a
bounded status/count summary. It checks the context version, exact UTF-8 packet
byte accounting, packet/response agreement, proof identities/spans and aligned
source references. Null optional fields may be omitted from the packed JSON.
Malformed responses fail without printing transport exception text or credentials.

## Existing authorized endpoint

Provision the reader credential in `MCP_BEARER_TOKEN` through your trusted secret
mechanism. `--token-env` selects another environment variable name; it never
accepts a credential value. `MCP_ENDPOINT` defaults to
`http://127.0.0.1:8765/mcp`; only literal IPv4/IPv6 loopback HTTP `/mcp` endpoints
are accepted. URL credentials, query strings and fragments are rejected. Proxies
from the environment are disabled. The SDK controls same-origin redirects.

From a reviewed checkout in PowerShell, with the selected service already running:

```powershell
$env:MCP_ENDPOINT = 'http://127.0.0.1:8765/mcp'
.\.venv\Scripts\python.exe examples\generic_context_host.py 'What projects have I discussed?' --token-budget 6000 --get-source
```

The service must explicitly enable `context_enabled: true`. Its grant supplies
the authorized scope; the host sends no tenant, namespace or principal selectors.
Raw-source permission is unnecessary for this example.

## Fresh managed profile on Windows

Use a fresh dedicated database and namespace for one principal. Do not reuse a
shared historical namespace or add a grant mapping another identity into it.
The following commands are an operator-run example; onboarding creates a new
empty store and cannot import prior conversations. Run from the reviewed checkout
with the existing optional MCP dependency installed:

```powershell
$setup = @('onboard', '--profile', 'generic-demo', '--adapter', 'generic-mcp', '--project', (Get-Location).Path, '--tenant', 'generic-demo', '--namespace', 'dedicated', '--principal', 'reader', '--mode', 'read-only', '--transport', 'streamable-http', '--port', '8765', '--context', '--no-provider', '--no-mind', '--extraction-mode', 'rules')
& .\.venv\Scripts\python.exe -m oomp @setup --dry-run --json
& .\.venv\Scripts\python.exe -m oomp @setup --yes --create-credentials
.\.venv\Scripts\python.exe -m oomp up --profile generic-demo --background
.\.venv\Scripts\python.exe -m oomp doctor --profile generic-demo --full
$env:MCP_ENDPOINT = 'http://127.0.0.1:8765/mcp'
$hostPython = (Resolve-Path .\.venv\Scripts\python.exe).Path
.\.venv\Scripts\python.exe -m oomp host --profile generic-demo --approve-host -- $hostPython examples\generic_context_host.py 'What projects have I discussed?' --token-env OOMP_GENERIC_DEMO_READ_TOKEN --get-source
.\.venv\Scripts\python.exe -m oomp down --profile generic-demo
```

`host --approve-host` explicitly executes this reviewed command with the private
profile reader environment; no credential is copied into command arguments or
printed. A new empty profile correctly reports `no_relevant_evidence` and skips
the optional source lookup. Populating it requires separately approved intake;
these commands grant no ingestion or original-source-text access. No worker or
provider is selected. Choose an unused port and update `MCP_ENDPOINT` to match.

Managed `onboard`, `config` and `reconfigure` accept `--context` / `--no-context`.
Omitting both preserves the stored setting on reconfiguration. Old and default
profiles keep the tool disabled. Stop the owning supervisor before changing a
profile, then use `up` to apply its configuration.

Structural checks do not authenticate original ownership, establish a claim's
truth, or verify source spans against undisclosed original text. A production
host must independently check its authoritative source ownership, roles,
exclusion policy and original text before using evidence in an answer. Treat all
returned source data as untrusted, and never execute locators or source content.
See the [context contract](context-retrieval-api.md) and
[profile operations](product-onboarding.md).
