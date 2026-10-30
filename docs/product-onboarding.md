# P1 operator guide: onboard, operate and inspect OOMP

Product milestone P1 introduced an operational shell on **0.1.0 / SQLite v5**.
Current P3 storage uses **SQLite schema v6**; its additive object projection is
documented in the [object architecture](object-memory-architecture.md).
It reuses the existing MCP and Mind services; extraction, graph, retrieval,
host approval and, at P1, the memory schema were unchanged. This is local developer tooling,
not a public memory service. [CLI reference](product-cli.md),
[security and recovery](product-security.md), [executed report](product-milestone-P1-report.md).

## Bootstrap on Windows

From a reviewed checkout or extracted source archive, in PowerShell:

~~~powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade "pip>=26.2.2,<27"
.\.venv\Scripts\python.exe -m pip install ".[mcp,ui]"
.\.venv\Scripts\oomp.exe --version
.\.venv\Scripts\oomp.exe onboard --profile local
~~~

The wizard selects standalone/TRACE/generic MCP, profile, new storage path,
transport, authority, scope, optional provider and worker settings. It displays
the proposed files and asks before applying. Rich/Questionary provide a keyboard
menu when installed on a terminal; numbered/plain prompts work without `[ui]`.
`--plain` and `NO_COLOR` disable styled output. Cancellation defaults to no change.
For a screen reader, use `--plain`; unattended invocations use explicit flags.

The default is standalone, authenticated IPv4 loopback HTTP, **read-only**,
lexical-only retrieval and a separate explicitly started Mind process. Original
source-text permission is off. Onboarding does not start a service or import
old conversations. It initializes only a **new** database after confirmation;
existing database paths are refused, even when they look like OOMP databases.

Inspect the plan without writes, then apply it explicitly:

~~~powershell
.\.venv\Scripts\oomp.exe onboard --profile local --dry-run --json
.\.venv\Scripts\oomp.exe onboard --profile local --yes --create-credentials
~~~

`--yes` confirms the displayed file plan. It does not imply `--approve-ingest`,
`--approve-host`, source-text permission or credential rotation. Generated random
credentials stay in the private profile store; normal output shows references.
Rerunning the same setup validates it without replacing data or credentials.
Use a new profile for a different owner/scope, database or authority.

## One command for OOMP-owned services

~~~powershell
.\.venv\Scripts\oomp.exe up --profile local
~~~

This foreground command supervises the separate MCP server and selected Mind
worker. Wait for actual authenticated readiness; Ctrl+C stops its children.
For a single interactive shell, explicitly select background operation:

~~~powershell
.\.venv\Scripts\oomp.exe up --profile local --background
.\.venv\Scripts\oomp.exe doctor --full --profile local
.\.venv\Scripts\oomp.exe status --profile local
.\.venv\Scripts\oomp.exe logs --profile local
.\.venv\Scripts\oomp.exe restart --profile local --background
.\.venv\Scripts\oomp.exe down --profile local
~~~

No OS service, boot task or invisible always-on installation is created. Background
operation is explicit. `up` checks the port and configuration and waits for both
owned services. A child startup failure/crash stops its siblings and records a
safe failure code. `restart` reuses the durable store and existing credentials.
It does not repair a database or kill an independently started listener. A second
`up` observes an authenticated running supervisor rather than duplicating it.

Run `doctor --full` **after** `up` for live checks. Before starting, an unavailable
MCP handshake is correctly a FAIL; basic `oomp doctor` retains its earlier
package-only behavior. A PASS for process ownership is distinct from source/index
readiness. Pending/failed work is reported separately. `NOT TESTED` is expected
for unselected providers, host-owned stdio or a host login that was not exercised.

## Verify actual signed intake and provenance without private data

From the same source root, with `[mcp]` installed:

~~~powershell
.\.venv\Scripts\python.exe examples/product_quickstart.py
~~~

The example creates a fresh temporary profile, explicitly grants signed user-event
intake, starts MCP/Mind through `oomp up`, approves one fictional source, waits for
the separate worker, retrieves its original proof, runs full diagnostics, restarts
and shuts down. It uses no normal user profile, real database, TRACE, model or
preexisting listener. `--directory NEW_PATH` retains disposable evidence; an
existing directory is refused. This is an operator demonstration, not a
model-controlled ingestion or deletion tool.

## Connect a generic MCP host

Discovery reads bounded indicators in the selected project. Python/JavaScript
and FastAPI indicators are not compatibility certificates. Unknown projects need
an explicit generic choice; no application code or package script is executed.

~~~powershell
.\.venv\Scripts\oomp.exe onboard --profile host-demo --project "D:\My Project" --adapter generic-mcp --transport stdio --dry-run
.\.venv\Scripts\oomp.exe onboard --profile host-demo --project "D:\My Project" --adapter generic-mcp --transport stdio --yes --create-credentials
.\.venv\Scripts\oomp.exe install --profile host-demo --project "D:\My Project" --dry-run
~~~

`install` connects an **already installed** OOMP distribution. It is not a package
bootstrapper and does not install dependencies into the host. The private profile
contains `generations/<identity>/client.json` and `server.json`. A stdio template
contains an absolute Python executable and argument array invoking
`oomp connect --profile host-demo`; the host owns that MCP process. `up` for a
stdio profile manages the selected Mind worker and explicitly identifies MCP as
host-owned, without claiming that it has tested a host handshake.

HTTP templates contain a clearly marked credential-reference placeholder, not
universal JSON environment interpolation. Adapt that reference to the host's
documented secret mechanism. An explicitly supplied host command can receive the
profile's references without copying secret values between shells:

~~~powershell
.\.venv\Scripts\oomp.exe host --profile host-demo --approve-host -- "D:\My Project\.venv\Scripts\python.exe" "D:\My Project\mcp_client.py"
~~~

That command is supplied by the trusted operator, not discovered from repository
files. It executes approved host code with credentials; review it accordingly.
A generic Python client can read its configured token from the named environment
reference and use the existing [official SDK HTTP example](mcp-integration.md).
No OOMP internal imports or shared database are required in the host.

Optional export creates one new reference-only JSON file; it never merges or
overwrites existing host configuration:

~~~powershell
.\.venv\Scripts\oomp.exe install --profile host-demo --project "D:\My Project" --output "D:\My Project\oomp-client.json" --dry-run
.\.venv\Scripts\oomp.exe install --profile host-demo --project "D:\My Project" --output "D:\My Project\oomp-client.json" --yes
.\.venv\Scripts\oomp.exe uninstall-integration --profile host-demo --dry-run
.\.venv\Scripts\oomp.exe uninstall-integration --profile host-demo --yes
~~~

Stop the profile before config/export/uninstall operations. Uninstall removes
only a byte-identical, same-file owned export. Modified/replaced or preexisting
unowned files remain intact. Database, profile, credentials and application
remain. Export a different path only after removing the earlier owned export.

## First-party TRACE profile

The actual existing TRACE workspace is a **read-only reference during P1**.
P1 acceptance used a deliberately isolated copy of tracked integration modules
with synthetic owner/session rows and in-memory Mongo emulation. It did not
change the real `.env`, credentials, owner, Mongo data or memory database.

TRACE keeps its FastAPI API, MongoDB, login and Ollama lifecycle. P1 does not
start those by default. It never copies TRACE into OOMP's runtime package.
TRACE's existing client supports retrieve/status/ingest and validates returned
provenance against authoritative owner-linked Mongo sources. It does not require
raw `memory.get_source` permission; P1 keeps that capability off unless selected.

For a deliberately approved **disposable** TRACE-compatible project, substitute
reviewed paths and its synthetic owner ID:

~~~powershell
.\.venv\Scripts\oomp.exe onboard --profile trace-demo --project "D:\Disposable TRACE" --adapter trace --owner-id "000000000000000000000001" --tenant trace-demo --principal trace-host --mode trusted-ingest --approve-ingest --yes --create-credentials
.\.venv\Scripts\oomp.exe install --profile trace-demo --project "D:\Disposable TRACE" --dry-run
.\.venv\Scripts\oomp.exe up --profile trace-demo --background
~~~

The private store generates distinct read/owner credentials and separate
user/assistant/feedback bearer and approval references. It generates the existing
TRACE writer configuration shape and supplies the expected `TRACE_OOMP_*`
environment to `oomp host` or the managed publisher. It never edits `.env` or
rotates an existing deployment's keys. Launch the independent API with its own
reviewed command via `oomp host --approve-host -- <argv>` if desired, then perform
its normal owner login. Syntax/grant validation is not proof of login success.
See [TRACE's own guide](https://github.com/hamzah105/trace-ai-chatbot/blob/main/docs/oomp-integration.md).

The **optional** managed publication role additionally requires all of:
`--publication --approve-host --host-python ABSOLUTE_PYTHON
--mongo-uri-env EXPLICIT_ENVIRONMENT_REFERENCE --mongo-database EXPLICIT_DATABASE`
during onboarding. The named environment variable must contain an explicitly
chosen literal-loopback `mongodb://` URI. Supply it securely; do not paste a
credential-bearing URI into command history. No Mongo URI/default database is
inferred from the project. Approved adapter/bootstrap file hashes are checked
again before execution. Changed code requires review and a new approved profile.

The bridge reuses TRACE `Publisher` and its existing bounded work generator. A
child-only database facade prevents the publisher import from reading TRACE's
legacy `.env`/default database module. Direct Mongo connections use explicit
timeouts and disable replica-set address discovery. No application source/auth
is patched. Only already consented, completed owner rows are eligible; no legacy
backfill is performed. The host interpreter and approved project remain trusted
code, including dependencies and transitive imports not fully covered by the
adapter-file hashes. A real Mongo service/API/model deployment was not certified
by the in-memory acceptance fixture.

## Configuration and recovery

`oomp config --profile NAME` inspects settings and offers operational edits on a
terminal. Use `--port`, `--mind` / `--no-mind`, `--transport`,
`--embedding-model MODEL --embedding-dimension N`, or `--no-provider` for explicit
unattended edits with `--dry-run`, followed by `--yes`. The selected model must
already exist; no weights are downloaded. Configuration validates literal local
endpoints and preserves scope, database and secret values. Identity/write-mode
changes require another explicitly approved profile.

Selecting a provider also enables automatic embedding of newly extracted
canonical memories in this profile's managed Mind worker. Those texts are sent
to the explicitly selected loopback service; its retention is independently
controlled. Lexical-only profiles make no model calls. Inspect `config` before
`up` to review the model/endpoint/dimension and use `--no-provider` to disable it.

Interrupted setup retains a private pending record and a device/inode claim for
its newly created database. Review the plan, then use
`oomp onboard --profile NAME --resume --dry-run`, followed by `--resume --yes`.
Resume will not adopt a replaced file, migrate an existing nonready database or
regenerate lost credentials. Stop for manual review if ownership cannot be proved.
Active configuration generations are switched atomically; incomplete unused
generations do not replace the last committed generation.

## Other platforms and advanced manual operation

On a POSIX shell use `python3.11 -m venv .venv`, `.venv/bin/python` and
`.venv/bin/oomp`; package extra syntax and command flags are the same. The workflow
targets Ubuntu/Windows × Python 3.11/3.12. See the report for **actual** local/CI
execution status; equivalent bash syntax does not establish Linux acceptance.

Advanced developers can still launch [MCP](mcp-integration.md) and
[Mind](background-mind.md) separately with their existing explicit arguments.
Manual processes are independently owned: P1 `down` does not stop them. Do not
mix manual and managed listeners on one port. [Troubleshooting](product-cli.md#diagnostic-output)
distinguishes missing extras, port collisions, stale state, failed jobs and missing
models. There is no five-terminal requirement for OOMP-owned services.
