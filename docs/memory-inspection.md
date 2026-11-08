# Inspect existing episodic memories without changing the store

These are trusted local administrative reads, not remote authentication. Use the
OOMP Python environment belonging to the reviewed installation. Do not run
initialization, migration, extraction, reprocessing, indexing or ObjectMap builds
to inspect existing data. No model or TRACE/MongoDB connection is needed.

## 1. Locate the explicitly selected profile

Replace the fictional profile name and home below with the approved local values:

```powershell
$profileName = 'example-trace'
$profileHome = 'D:\oomp-private-profiles'
$configuration = oomp config --profile $profileName --home $profileHome --json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Profile inspection failed; do not initialize or repair it.' }
$settings = $configuration.settings
$settings | Select-Object database, tenant, namespace, principal
```

With `--json` and no setting-change flags, `config` reads the existing profile;
it does not update settings. It omits credential values, but its paths, scope and
secret-reference names still belong in private operator output. Do not print
`secrets.json`, load TRACE's `.env` or run `doctor --full` for this procedure.
Full doctor checks can invoke configured providers and are not required for a read.

## 2. Read episode metadata through the existing guarded snapshot

An ordinary read-only SQLite connection to a live WAL database may interact with
its sidecars. Copying only the main file can omit committed WAL data. The existing
inspection helper instead refuses a nonempty WAL, applies size/time limits,
opens the admitted original read-only and immutable, creates a disposable copy,
and checks for source changes during copying. Queries below run on that copy,
which is removed when the operation finishes. Only the temporary copy is written.

Run this from PowerShell with the variables from step 1:

```powershell
@'
import json
import sys

from oomp.product.diagnostics import inspection_snapshot
from oomp.product.profiles import ProfileStore
from oomp.product.safety import ProductError
from oomp.understanding.admin import episodes

try:
    profile = ProfileStore(sys.argv[2]).load(sys.argv[1])
    with inspection_snapshot(profile.database) as snapshot:
        result = episodes(snapshot, profile.scope, limit=20, show_content=False)
        print(json.dumps({"episodes": result}, ensure_ascii=True, indent=2))
except ProductError as error:
    print(json.dumps({"ok": False, "code": error.code}))
    raise SystemExit(2)
except Exception:
    print(json.dumps({"ok": False, "code": "inspection_failed"}))
    raise SystemExit(2)
'@ | python -I - $profileName $profileHome
```

Episode output contains IDs, source/clause counts, recording times, freshness and
an uncertainty reminder. It does not include summary text or original excerpts
without the explicit content option. IDs and timestamps can still be private.
The reader lists current eligible episode-summary groups, not every retained
clause or retired revision. It rechecks source support and the stored fingerprint;
stale, retracted or ineligible summaries can be omitted or refused. An empty
response does not by itself prove that the underlying memory tables are empty.

Stop on `wal_requires_live_status_or_offline_backup`,
`database_changed_during_snapshot`, a size/time refusal or any other error. Do not
checkpoint/delete WAL, stop writers, retry with `immutable=1` directly, initialize
the database or rebuild anything to bypass the refusal. An independently approved
WAL-consistent backup is the alternative; this guide does not create one by copying
the live main file.

The helper takes a point-in-time snapshot. Concurrent services may change their
own database/sidecars after that point; this procedure is not proof that every
file stays unchanged while other writers run.

## 3. Inspect a previously approved private snapshot with the CLI

If a WAL-consistent private snapshot already exists, point the read commands at
that snapshot, not at the active original. The placeholder below must be replaced
with that existing snapshot path:

```powershell
$inspectDb = 'D:\private-snapshot\memory.sqlite3'
$scope = @('--db', $inspectDb, '--tenant', $settings.tenant, '--namespace', $settings.namespace, '--principal', $settings.principal)
oomp understand episodes @scope --limit 20

# Copy one episode_id from the metadata output; this is an episode/topic ID.
$episodeId = 'p2episode-REPLACE-WITH-EXISTING-ID'
oomp understand inspect @scope --episode-id $episodeId

# Canonical-store listing accepts tenant/namespace, not --principal or --json.
oomp memory list --db $inspectDb --tenant $settings.tenant --namespace $settings.namespace --limit 100

# ObjectMap navigation is a separate, principal-selected stored projection.
oomp memory tree @scope --depth 7 --limit 100 --json
```

`understand episodes` and `understand inspect` print JSON without a `--json` flag.
`memory list` shows individual canonical-store records, including retained
episodic clauses; it is distinct from the episode-summary groups above. Its
limit is 1–100, so a larger store may exceed this bounded view.
`understand inspect --episode-id ... --show-content` deliberately reveals the
stored summary and supporting source metadata to the local operator. Use it only
in a private terminal when content is needed; do not paste its output into issues,
CI artifacts, screenshots or public reports. The flag does not authorize a remote
caller or establish that a remembered claim is true.

Canonical and episode-summary readers retain legacy tenant/namespace behavior.
Although the episode CLI requires `--principal`, its revision selection and
inherited summary reader are not a general principal-isolation guarantee within
a shared namespace. Use only the dedicated, approved single-owner namespace for
these local reads. `memory.context` and P3 ObjectMap reads have their separately
documented stronger principal-specific validation boundaries.

## Why an ObjectMap can be empty while episodes exist

Source events live in `events`. Retained clauses are canonical-store rows in
`memories`; P2 episodes have `memory_type='episodic'` and `p2_episode=true`.
Current and historical extractive summaries live in `mind_summary_revisions`,
with attribution manifests in `mind_summary_sources`. These layers do not require
rows in the P3 `map_objects` or `map_proofs` tables to exist.

The normal Mind handler performs extraction/acquisition, lexical/optional vector
indexing, topic consolidation and conflict review. It does not call
`ObjectMap.project_event()` or `ObjectMap.build()`. P3 projection is an explicitly
invoked operation, and read commands never populate it. Enabling Mind or Context V1
therefore does not itself materialize the hierarchy.

Zero map rows means the selected principal currently has no stored object
projection. It does not mean that source history was lost, episodes were not
persisted or retrieval necessarily has no evidence. It also does not prove that a
map was never built historically and later cleared. Do not run `build-map` or
`rebuild-map` as a diagnostic: both write the projection and require a separate
approved action. The known default multi-principal scheduling limitation remains
separate and open; this guide neither fixes nor bypasses it.

See [object inspection](object-memory-cli.md),
[episodic acquisition](mind2-design.md), [storage](storage.md) and
[privacy/retention](privacy-retention.md) for the underlying contracts.
