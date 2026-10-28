# Product CLI and diagnostics reference

Existing `storage`, `memory`, `graph`, `retrieve`, `retrieval`, `mind` and `mcp`
commands/arguments remain supported. `oomp --version` remains 0.1.0. Bare
`oomp doctor` retains the earlier package-only readiness contract.

| Command | Implemented behavior |
| --- | --- |
| `onboard [--project PATH]` | Read-only bounded discovery, guided choices and a complete file plan before confirmed setup |
| `onboard --dry-run [--json]` | Plan only; creates no profile, database or credential |
| `onboard --resume` | Explicit recovery of the profile's claimed interrupted setup, without secret rotation |
| `config`, `reconfigure` | Inspect or atomically update port, worker, transport and optional existing-model settings |
| `up` | Foreground supervisor; actual HTTP MCP authorization check followed by selected worker readiness |
| `up --background` | Explicit background supervisor; bounded launch wait, not an OS service installation |
| `status` | Authenticated ownership, retained child liveness, heartbeats/progress and safe last codes |
| `logs` | Bounded safe operational events, no subprocess stderr, source text or secret values |
| `down` | Authenticate the live supervisor and request graceful stop; no state-file PID signalling |
| `restart [--background]` | Stop/restart the same profile with preserved data and credentials |
| `doctor --full [--json]` | Real non-destructive profile/storage/runtime/index/provider checks and a disposable synthetic probe |
| `install --project PATH` | Locate the profile's reference-only host template; optional confirmed new-file export |
| `uninstall-integration --dry-run` | Plan removal of only a verified unchanged owned export; never deletes data/config/secrets |
| `connect` | Host-owned stdio MCP, with protocol-only stdout and no implicit Mind startup |
| `host --approve-host -- ARGV...` | Execute explicit trusted-operator argv with host credential references populated; never discovered commands |

Product commands accept `--profile NAME`, `--home PATH` and `--plain`; machine
output is available with `--json`. The default profile is `local`. Profile names
are 1–32 lowercase ASCII letters/digits/underscore/hyphen starting with a letter;
Windows device names are refused. `--home` overrides `OOMP_PROFILE_HOME`, then
the platform user configuration location. Paths may contain spaces/Unicode;
symlinks, junctions/reparse points, hardlinked private files and traversal are
refused. No ambient `.env` is loaded by OOMP.

On Windows the complete generation/atomic-file path must fit the supported
MAX_PATH budget, counted in UTF-16 units. Overlong profiles are refused before
setup with `profile_path_too_long_use_shorter_home`; choose a shorter `--home`
rather than changing system policy or deleting data. Compact atomic filenames
allow normal nested Unicode/space-containing profile paths within that budget.

Onboarding flags include `--adapter standalone|generic-mcp|trace`, `--database
NEW_PATH`, `--tenant`, `--namespace`, `--principal`, `--transport`, `--port`
(1024–65535), `--mode read-only|trusted-ingest`, `--approve-ingest`,
`--read-source`, `--mind` / `--no-mind`, `--secret-source file|environment`,
`--create-credentials` and the explicit optional TRACE settings documented in
[onboarding](product-onboarding.md). A custom database parent must already exist
and be private; P1 does not chmod arbitrary host directories. Defaults use the
private profile directory.

Apply operations show a preview, default to cancellation and require interactive
confirmation or `--yes`. No service starts during onboarding/install/config.
`--json` onboarding puts its pre-apply reference-only plan on **stderr** and its
result on stdout; `--dry-run --json` emits just the plan on stdout. Config/export
JSON describes the proposed operation; exit status determines whether a requested
apply succeeded. `connect` reserves stdout entirely for MCP even on failure.
`up --json` requires `--background` so that stdout can contain a complete result.

Lifecycle/configuration mutations are serialized with a held OS file lock. Stop
the profile before reconfiguration/export/uninstall. A stale state file yields
`unverified`, never permission to signal its recorded PID. Startup checks the
port without evicting an independent service. Successful `down` waits for the
final stopped record and released lock. A crashed child stops its siblings;
restart is explicit, without an unlimited restart loop.

Shutdown sends a message through each parent-owned stdin pipe. Parent death/EOF
also requests child shutdown. After a seven-second shared grace period, only
retained owned subprocess handles may be terminated, then forcibly killed after
two more seconds if needed. This can interrupt an active job; the existing durable
lease/fencing/retry mechanisms, not process memory, govern recovery. A heartbeat
alone does not prove work completion: progress age is exposed and non-MCP work
stalled beyond 180 seconds fails supervision. Control is authenticated loopback
IPC with eight concurrent request slots, two-second reads and bounded messages.

## Diagnostic output

`oomp doctor --full --profile local --json` returns schema version **1**:

~~~json
{
  "schema_version": 1,
  "oomp_version": "0.1.0",
  "profile": "local",
  "ok": false,
  "summary": {"PASS": 0, "WARN": 0, "FAIL": 1, "NOT TESTED": 0},
  "checks": [{
    "id": "profile",
    "outcome": "FAIL",
    "code": "profile_or_credentials_invalid",
    "recommendation": "Review the profile without exposing credentials.",
    "details": {}
  }]
}
~~~

This is an illustrative shape, not an executed result. Each check has an ID,
outcome, safe reason code, actionable recommendation and typed count/version
details. The summary counts the checks; `ok` means no FAIL, **not** that every
optional surface was tested. New check IDs may be added in format v1; consumers
should match IDs/codes and tolerate new checks. Do not parse colored prose.

Checks cover interpreter/package versions, actual in-memory SQLite FTS5, profile
validity, credential presence/distinctness, paths/permissions/disk, unchanged
schema readiness, canonical/index coverage, queue counts/age, supervisor and worker
ownership/health, port occupancy, actual SDK authentication/status, selected local
embedding dimensions, TRACE layout/approved publisher and isolated synthetic
worker/retrieval/provenance. Host login is NOT TESTED until separately exercised.
No live private event is appended by doctor and no private database is migrated.

Offline inspection copies only a bounded immutable main-file snapshot into a
temporary directory. A nonempty WAL is deliberately NOT TESTED through that
path, because immutable mode ignores WAL. Live authenticated `memory.status`
supplies current index/queue counts when the server is running. The snapshot is
bounded to 128 MiB/three seconds and rejects changes during copying. It is a
diagnostic convenience, not a replacement for [WAL-safe backup](privacy-retention.md).

| Outcome / code | Interpretation and next action |
| --- | --- |
| FAIL `profile_or_credentials_invalid` | Inspect `config`, environment references and private permissions; use explicit resume for pending setup |
| FAIL `mcp_handshake_or_authorization_failed` | Start the profile; inspect optional SDK, credential references and listener ownership |
| `port_in_use_no_process_changed` | Choose another port or have the independent owner stop its service |
| `profile_busy` | Stop the owning supervisor before a configuration/integration mutation |
| `profile_path_too_long_use_shorter_home` | Choose a shorter private profile root; no database needs to be erased or reset |
| `ownership_unverified_no_process_signalled` | Inspect logs/state and port; never kill a PID merely because a file names it |
| WARN pending/failed queue counts | Inspect existing `mind status/jobs`; acceptance is not extraction completion |
| NOT TESTED WAL / snapshot bound | Use live status, or a consistent authorized offline backup; no private repair was attempted |
| WARN provider unavailable/incompatible | Start the independently owned provider/model, or choose lexical-only; no weights are downloaded |
| NOT TESTED host login / stdio / no provider | That surface was not exercised or was not selected; it is not a PASS |

Product operational failures return 1, argument parsing returns 2, and Ctrl+C/EOF
prompts return 130 (declining confirmation returns 1). Successful operations
return 0. `status` returns 1 for
failed/unverified ownership or a nonready running child. `doctor` returns 1 when
any check FAILs and 0 with explicitly reported WARN/NOT TESTED states otherwise.
`down` retains a previously failed run's failure state for inspection; stopping
after a crash does not erase its diagnostic history.
