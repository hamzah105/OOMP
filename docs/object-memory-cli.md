# Object memory inspection

P3 extends `oomp memory` without changing `extract`, `list` or `index`.
Install the package normally; no model or external service is required.
These are trusted local administrative commands using filesystem authority.
`--principal` selects the authorized projection; it is not authentication for
an untrusted remote caller. No new MCP grant, tool or listener is introduced.

Every object command requires `--db`, `--tenant`, `--namespace`, `--principal`.
It never discovers a personal profile or initializes a database implicitly.
Initialize a **fresh synthetic database** explicitly, or follow the existing
backup/restore procedure before any future owner-approved real upgrade.

## PowerShell fictional lifecycle

From the repository with its current package installed:

```powershell
$demo = Join-Path $PWD ('.test-artifacts\p3-demo-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff'))
python examples/object_memory_quickstart.py --directory $demo
$result = Get-Content (Join-Path $demo 'result.json') -Raw | ConvertFrom-Json
$scope = @('--db', (Join-Path $demo 'fictional.sqlite3'), '--tenant', 'object-public-demo', '--namespace', 'synthetic', '--principal', 'fictional-owner')
oomp memory tree @scope --depth 10 --limit 300 --json
oomp memory inspect $result.plan_id @scope --show-provenance --json
oomp memory explain $result.plan_id @scope --json
oomp memory history $result.plan_id @scope --show-provenance --json
oomp memory find Cedar @scope --json
oomp memory export @scope --redacted --depth 10 --limit 300 --json
```

The example refuses an existing output directory and uses the frozen fixture
with actual rules-only Mind jobs. It checks three paths to one relocation plan,
an independently stored later correction, Cedar's explicit rename to Aspen,
exact source spans, historical inspection, idempotent rebuild and database reopen.
It creates only disposable synthetic files. Keep the path short on Windows.

## Commands and limits

| Command | Behavior |
| --- | --- |
| `tree [--root ID] [--depth 0..10] [--limit 1..500]` | Unique nodes and many-parent membership edges; relations share the same snapshot; explicit `truncated` flag |
| `inspect ID` | Supported current object, parent/child memberships, associated relationships and relevant timestamps |
| `history ID` | Independently grounded assertion changes, withdrawal status and actual P2 summary revisions for episodes |
| `explain ID` | Actual bounded owner paths and object/fact/source paths; source proofs remain attributed and unverified |
| `find LABEL [--limit 1..100]` | Exact eligible label/alias lookup; ambiguity returns separate identities, no fuzzy search or P4 planning |
| `export [--redacted] [--depth N] [--limit N]` | Always redacted: opaque IDs, types, controlled structural labels and relationships; no source bodies, private labels, raw scope strings or locators |
| `build-map [--limit 1..1000] [--cursor TOKEN]` | Explicit scoped projection of existing eligible records, chronological keyset continuation |
| `rebuild-map [--limit N] [--cursor TOKEN]` | Non-destructive scoped replay preserving object anchors and meaningful proof history |

Tree defaults: depth 7, 100 nodes, 1,000 edges, 10,000 work units. A large
hierarchy needs finite branch inspection or the paginated Python API.
`truncated` and build `incomplete` must be checked. Continuation tokens are
scope-bound, not bearer credentials. Builds reject temporal filters.
All read commands accept `--known-at` and `--valid-at` with timezone-aware
ISO 8601 timestamps. Unknown validity remains unknown. Historic knowledge does
not backdate a projection that did not yet exist.

Default local views expose object labels and structural metadata, **not source
excerpts**. `inspect`, `history` and `explain` accept `--show-provenance` for
source IDs/metadata, and `--show-content` to reveal exact supporting spans and
derived summary content to the trusted operator. Source-system locators are
omitted even with these flags. Labels can themselves be private: use `export`
for a redacted shareable structure. This is redaction, not anonymization against
correlation of stable IDs. No command should be forwarded to untrusted users.

`--json` emits compact, ASCII-escaped valid JSON, preserving Unicode labels
through JSON decoding even under redirected Windows encodings. Human output is
indented JSON with readable field names and labels. Neither mode emits ANSI
color, including with `NO_COLOR`. Output is capped at 1 MiB before emission.
Failures emit a constant error code on stderr and return 1; argument errors
return argparse's 2. Error messages do not include supplied paths or source text.

## Python API

```python
from oomp.domain.models import AuthorizedScope
from oomp.objects import ObjectMap

scope = AuthorizedScope(tenant_id="object-public-demo", namespace="synthetic",
                        principal_id="fictional-owner")
objects = ObjectMap("explicit-disposable.sqlite3")
result = objects.build(scope, limit=100)
page = objects.list_objects(scope, object_type="plan", limit=20)
for obj in page.objects:
    explanation = objects.explain(scope, obj.object_id)
```

Only trusted application code may construct `AuthorizedScope`. Internal Python
objects contain provenance and spans; callers must enforce authorization and
choose redaction before displaying them. Public associations independently
validate role, endpoint types, exact source proof and scope. Generic calls cannot
mint protected corrections. `project_event(..., job=claimed_job)` checks the
actual event target and Mind lease/fence before and after the transaction.
P3 projection is explicitly invoked; it is not an automatic new Mind job type.
