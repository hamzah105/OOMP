# Privacy, retention, backup and recovery

OOMP is local-first and stores **plaintext** data. SQLite, WAL/SHM files, derived
indexes and backups need host filesystem protection. CLI tenant strings and a
constructed `AuthorizedScope` are not network authentication. The loopback MCP
grant profile is separate from administrator access and is not a production
cloud security design. [Security model](security-model.md).

## What persists and what can leave the process

| Data | Persistence / exposure |
| --- | --- |
| Source events | Original content, role, timestamps, source references, scope, metadata and idempotency evidence |
| Canonical memory | Attributed unverified claims, exact source links/spans, entities and explicit aliases |
| Graph and topics | Scoped endpoints, relationship proof, recording history, reported validity and explicit memberships |
| Retrieval indexes | FTS documents and optional model/version/dimension-qualified vector blobs |
| Background state | Outbox, durable jobs/attempts, leases/fences, extractive summary revisions, conflict reviews and minimal audits |
| Privacy state | Retractions, constrained erasure audits and replay-protection tombstones/identifiers |

Explicit path selection overrides `OOMP_DB_PATH`, which overrides the platform
default. Windows defaults to `%LOCALAPPDATA%\OOMP\events.sqlite3`; macOS to
`~/Library/Application Support/OOMP/events.sqlite3`; Linux to
`$XDG_DATA_HOME/oomp/events.sqlite3` or `~/.local/share/oomp/events.sqlite3`.
No `.env` is automatically loaded. `sample.env` is documentation only.

Offline extraction/retrieval sends nothing to a model. Deliberately configured
Ollama embeddings send selected canonical text/query text to a literal loopback
HTTP service; that service and its retention/configuration remain trusted external
software. No model is downloaded. MCP can disclose selected evidence to its
authorized host; raw linked source content additionally requires `read_source`
and explicit inclusion. A host/generator may retain returned data independently.

Secret filtering is a limited extraction heuristic. It **does not remove the
original event**, encrypt a database or establish that no secret exists. Avoid
ingesting credentials. Logs are designed to use codes/counts, but IDs, source
references, topic names and copied diagnostics can still be sensitive. `--show-content`
is an intentional local disclosure. Never publish your database, embeddings,
tokens, .env, output runs or backup files. Ignore rules are not access control;
inspect tracked files and built archives before distribution.

## Corrections, erasure and retention

Ordinary events are immutable. Corrections append new evidence; only supported,
source-grounded and explicitly confirmed governance creates protected conflict or
supersession links. Retraction withdraws endorsement while retaining source history.
Dedicated summary artifacts and vectors remain derived representations, not truth.

Privileged local erasure uses `oomp mind erase-plan --db PATH --tenant TENANT
--namespace NAMESPACE --event-id EVENT_ID`, then explicit `erase-confirm` with the
same event and returned plan digest plus `--confirm`. Consult `--help` and review
the dependency plan first. No MCP/model-controlled erase tool exists.

The transaction rechecks dependencies, removes supported affected source/derived
representations, invalidates summaries/vectors/indexes and blocks replay through
tombstones. Unsupported graph-dependent/shared cases fail closed. Do not bypass
those blocks by manually disabling triggers. Worker effects revalidate actual
source existence and cannot revive a deleted source through ordinary replay.

Logical deletion cannot recall data returned earlier, remove external exports,
erase old backups, guarantee removal from SQLite free pages/FTS segments/WAL/SHM,
or establish cryptographic secure deletion. Audits/tombstone identifiers remain
where required. There is no automatic retention/pruning daemon: administrators
must define how long events, attempts, projections, exports and backups remain.
Apply an approved retention policy to every copy and dependent application.

## Consistent backup

A full SQLite backup includes **all tenants/namespaces in that file**. It is an
administrator operation, not a scoped tenant export. Protect the destination
directory and any off-machine storage with appropriate ACLs/encryption/retention.
The core package does not provide encrypted storage.

Do not copy only a live main `.sqlite3` file: committed transactions may still be
in its WAL. Use SQLite's online backup API, which reads a consistent committed
database view, or a fully stopped/checkpointed procedure with independently
verified shutdown. The supplied helper refuses an existing destination:

~~~python
from pathlib import Path
from examples.backup_restore import backup_new

backup_new(Path("PRIVATE_AUTHORIZED_SOURCE.sqlite3"), Path("NEW_PRIVATE_BACKUP.sqlite3"))
~~~

Run this from the source root with an installed OOMP package. The uppercase names
are placeholders, not executed release-validation paths. `backup_new` uses
`sqlite3.Connection.backup` and `PRAGMA quick_check`; it does not perform ordinary
file copying. File mode 0600 is a POSIX intent, not a Windows ACL guarantee.
Administrators must protect the Windows destination directory themselves.
A failed output is not a verified backup; retain it separately for diagnosis.
Record the package/schema version and a checksum, and protect any separately
needed application/grant configuration without storing secrets in public logs.
[Python SQLite backup reference](https://docs.python.org/3.11/library/sqlite3.html#sqlite3.Connection.backup).

The executed synthetic demonstration creates only new disposable files and
proves recovery while a separate connection retains committed WAL state:

~~~powershell
.\.venv\Scripts\python.exe examples/backup_restore.py --directory data/backup-demo
~~~

## Restore safely

Stop producers, Mind workers and MCP/application readers before switching stores.
Keep the original file/copies for an authorized recovery window; never overwrite a
live database or mix unrelated main/WAL/SHM sets. Restore with `backup_new` into a
**new path**, run `PRAGMA quick_check`, inspect `SQLiteEventStore(new_path).status()`
and verify expected synthetic/authorized source counts, provenance and retrieval
before changing configured paths. Restore tests should use copies, not originals.
Never run examples that seed/erase data against the restored private store.

A snapshot predating an erasure can resurrect previously deleted data. Before
serving the restored file, reconcile later erasures/retention decisions and review
pending jobs, leases and provider configuration. Do not assume tombstones created
after the backup exist in the restored snapshot. Revoke/rotate any compromised
credentials separately. Backup consistency is not an encryption or remote
deployment certification.
