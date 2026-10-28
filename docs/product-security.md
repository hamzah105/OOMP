# P1 local operations: trust, privacy and recovery

P1 preserves schema v5 and all MCP approval/authorization contracts. New setup,
profile and lifecycle operations are **trusted local administrator** commands.
A CLI scope string is not network authentication. No new model-facing approval,
policy, backfill or erasure tool exists. [Earlier security model](security-model.md)
and [privacy/backup limits](privacy-retention.md) still apply.

## Profile and secret storage

Defaults are `%LOCALAPPDATA%\OOMP\profiles` on Windows,
`~/Library/Application Support/OOMP/profiles` on macOS, and
`$XDG_CONFIG_HOME/oomp/profiles` or `~/.config/oomp/profiles` on POSIX. `--home`
and `OOMP_PROFILE_HOME` are explicit overrides. Do not use shared/network storage
or commit this directory. SQLite and these files are plaintext; host/disk security
and backup access remain operator responsibilities. This is not encrypted storage.

Each profile has versioned public-in-the-local-store settings, atomically selected
generations, a separately protected secret file (or environment references),
owned-process state, setup claims, bounded safe logs and an optional export
receipt. “Public settings” means no secret **values**, not that paths/owner IDs
are appropriate to publish. Protect all profile files and backups.

New directories/files get owner-only POSIX 0700/0600 or an explicit protected
Windows DACL granting only the current user and SYSTEM. Existing unsafe profile
paths fail closed; the tool does not tighten permissions on arbitrary application
ancestors. Linked/reparse paths, private-file hardlinks and traversal are refused.
Local administrators/SYSTEM, compromised interpreters or hostile dependencies
remain outside this local-process protection boundary.

Random credential creation requires explicit confirmation. Read, owner,
role-specific bearer and role-specific signing credentials are distinct.
Configuration/status/normal logs/dry-run plans show references or safe codes,
never values. Existing credentials are not rotated automatically. Environment
mode requires the named variables to already contain valid distinct secrets;
they are not copied into profile files. Do not put secret values into process
arguments, bug reports or shell history.

Onboard refuses an existing database and creates only a new explicit file, with
no import/backfill of old conversations. Repeated setup preserves credentials,
sources and indexes. Reconfiguration changes operational settings; changing owner,
scope, write authority or storage requires another approved profile. Generated
read grants omit raw-source permission unless `--read-source` is explicit.

## Discovery, host integration and execution

Discovery reads only a bounded list of indicator files under the selected root.
It never imports discovered Python, executes package scripts, follows paths
outside the root, reads `.env`/credentials or trusts instructions in file content.
Indicators are not framework support guarantees. Providers are not contacted by
discovery; a deliberately selected local provider can be exercised by full doctor
using fixed synthetic text. No model is downloaded and no private text is used.
Separately, a running managed Mind worker with a selected provider enables
automatic embedding on new extraction, sending those canonical texts to the
chosen loopback service. Provider selection is an explicit opt-in; provider
retention and host access are separate responsibilities. Disable it with a
confirmed `config --no-provider` after stopping the profile.

Host adapters/templates are generated inside the private profile by default.
Export requires a separately previewed new JSON target. Existing host configs,
auth, dependency manifests, `.env`, `.gitignore` and Git state are not patched.
Reversal removes only the same-file, same-byte owned export; it preserves
preexisting, modified or replaced files and never removes the database or keys.

`oomp host --approve-host -- ARGV...` is an explicit operator-code execution
boundary. The supplied program receives credential values in its environment;
review that program and its logs. It is not callable by a model or inferred from
project files. Independently installed interpreters/dependencies are trusted.

Optional TRACE publication requires explicit owner, writer approval, project-code
approval, host interpreter and local Mongo reference/database. Pinned adapter and
package-bootstrap hashes catch changes to those files; they do **not** attest
every transitive import or installed dependency. The child uses TRACE's existing
publication policy/work generator, not an alternate approval implementation.
A child-only database dependency facade binds the publisher's legacy helper to
the explicitly chosen connection and prevents default `.env` loading. No actual
TRACE source/auth/configuration is altered. Real TRACE during P1 was reference-only.
Managed publication requires an explicitly selected regular-file interpreter
with host dependencies installed. Linked interpreter paths are refused by the
same path policy; that optional role was exercised on Windows, not Linux/macOS.

## Process ownership and service limits

`up` is foreground by default. Background operation is explicit, without OS
service/autorun installation. MCP, Mind and the optional approved publisher are
separate processes. API, MongoDB and Ollama remain independently owned. Literal
IPv4 loopback MCP and an authenticated bounded loopback control socket are the
only managed listeners; no public bind, arbitrary discovered command or broad
proxy/origin exception is added.

A held OS lock protects lifecycle/configuration. Control uses a random per-run
credential and instance ID stored in private state. PIDs are informational.
Stale files/PID reuse never authorize signals; down authenticates the supervisor,
which stops only retained child handles. A parent's death closes child pipes and
requests shutdown. Forced process termination is bounded and can leave durable
work leased; existing fences/retries handle recovery. There is no unbounded
automatic restart loop. Host/process readiness does not prove final memory quality.

Raw child stderr is not copied into ordinary product logs; safe codes/counts are
used. Log output reads at most 32 KiB and returns a bounded latest slice; a log
rotates at 1 MiB with one prior file. Diagnostic snapshots never initialize or
migrate the private store, and active WAL is not misrepresented as an up-to-date
immutable main-file view. Full doctor may create/delete its own temporary
synthetic store. A dependency scan and tests are not independent penetration tests.

## Upgrade and interrupted configuration

Stop the profile, inspect the installed version/interpreter and back up the data
using SQLite's online backup API. Protect profile/secret backups separately.
Upgrade from a reviewed source/wheel; no registry publication is assumed.
Run basic doctor, review configuration, start and run full diagnostics. Existing
CLI/MCP tools remain available for advanced manual recovery. A package upgrade
does not implicitly migrate a memory DB. A new unsupported profile format fails
closed instead of being silently rewritten.

Active settings use an atomic generation pointer. A failed new generation leaves
the prior pointer usable. Interrupted initial setup retains a pending profile and
claim for its newly created database; `onboard --resume` requires confirmation and
checks the same file identity. Missing/replaced credentials are not regenerated;
unknown or nonready nonempty databases require manual review. Never “recover” by
deleting real data, disabling SQLite triggers or copying only a live main DB.

When changing Python environments, inspect the stdio client's absolute executable
and regenerate the template from the intended installed interpreter after stopping
the profile (an explicit confirmed config update, including the same port, refreshes
the derived files). Do not retain an executable pointing to a removed environment.
Restoring old memory backups can resurrect erased data; reconcile retention and
later erasures before serving them. P1 does not change the constrained erasure
workflow or claim secure physical deletion.
