# P5 submission report

7 November 2026 (Asia/Karachi). Submission-focused alpha work, not a release or
completion of every research requirement in the five-stage product roadmap.
Base: `d34bfbbbec44b0e016ddc41da1a7e27a45d45a68`, branch
`feature/p4-retrieval-quality`. TRACE remains unchanged at
`dcfda75325be0254232c1f1342601692ce18f937`.

## Implemented scope

Managed profiles now explicitly opt into the existing `memory.context` tool with
`--context` / `--no-context`. The nullable setting preserves older profile
generation identities and stays disabled by default; omitted reconfiguration
preserves the stored choice. Database identity, authentication, ingestion
approval, grants and legacy source-read policy are unchanged.

The public official-SDK generic host performs bounded read-only context and
metadata-source checks, rejects malformed packets and suppresses sensitive SDK
exception/log output. It imports no OOMP/TRACE internals. These structural checks
do not replace the source owner's authoritative validation.

The new public managed demo creates five fresh fictional sources in a dedicated
single-principal namespace, uses signed intake and rules-only extraction, then
exercises context, ObjectMap, diagnostics and restart/shutdown. It does not start
TRACE, physical MongoDB, Ollama, embeddings or a model. The manual guide separates
this demo from historical Gate A/C and from a real chatbot answer evaluation.

Submission uses one principal per namespace and a dedicated fresh database.
The demo checks its generated grants against that restriction. This is not a
general scheduler fix or universal database enforcement. The default shared-queue
principal-projection defect remains open; legacy `memory.get_source` remains
tenant/namespace scoped.

## Source changes and retained evidence

P4 quality changes retained and previously validated:
`understanding/rules.py`, `context/validation.py`, `objects/storage.py`,
`context/planner.py`, `context/engine.py` under `src/oomp/`.
New P5 runtime changes are confined to `product/models.py`, `product/cli.py`,
and `product/profiles.py`. There are 95 runtime modules in the candidate.

Public additions include `examples/generic_context_host.py`,
`examples/submission_demo.py`, host/profile regression tests, frozen query-control
fixtures and the submission/manual/acceptance documentation. `MANIFEST.in`
includes the reviewed controls; `README.md` and limitations link this record.
The genuine old-profile fixture omits the new nullable field as well as extraction.

Historical acceptance reports, interrupted/failed results, single-use ledgers,
Windows health evidence and recovery snapshots remain preserved. Gates A/C were
not repeated. P4 Gate B was bounded and incomplete; see
[P4 final acceptance](P4-FINAL-ACCEPTANCE.md) for every measured denominator.

## Focused offline validation

Evidence: `.test-artifacts/submission-20261106T151910Z/`.

| Executed phase | Result |
| --- | --- |
| Python 3.11 initial focused run | 94 passed, one failed, stopped at first failure |
| Exact failed lifecycle test after launcher repair | 1 passed, 9.856 s JUnit elapsed |
| Remaining lifecycle / TRACE tests | 16 passed, one deliberately deselected already-passed case; 65.70 s pytest elapsed |
| Python 3.11 unique focused total | 111 passed across those runs; not a fresh full regression |
| Python 3.12 same focused selection | 111 passed in 112.01 s; no skips |
| Public managed demo | PASS in 45.234 s; five signed sources, seven context queries, six linked-source metadata checks, ObjectMap, restart and shutdown |
| TRACE / other read-only manual CLI commands | Six commands passed; no TRACE process or profile created |
| Fresh wheel / sdist | Built with cached setuptools84.2.1; 95 runtime modules byte-matched in both archives; Apache-2.0 metadata and content/credential-pattern audits passed |
| Python 3.11 clean wheel / sdist installs | Two fresh core-only environments; dependency checks and16 actual CLI checks passed |
| Python 3.12 clean wheel / sdist installs | Two fresh core-only environments; dependency checks and16 actual CLI checks passed |

The initial failure was test-launcher configuration, not a path guard or product
regression. The supervisor correctly removed test-only environment variables;
the new launcher relied on one for its startup hook. An isolated child reproduced
exit 119, `fresh_offline_startup_configuration_failed`. The new disposable
launchers now pin the exact approved dependency list in their own startup hook,
matching the previously accepted approach. Both interpreter startup probes and
the original failed test passed. The product environment filter was not weakened.
Original logs/JUnit and pre-repair launcher bytes were retained.

The public demo's project, alias and style packets were respectively 1,009,
983 and 1,028 bytes. Relocation returned three original-source proofs with
`candidate_uncertain` in 2,279 bytes. Unknown pet returned no evidence; the long
query's 96-byte budget excluded whole units and returned zero packet bytes.
Original proofs survived restart. Full doctor reported 24 PASS, zero WARN/FAIL
and four NOT TESTED checks for unselected model/provider paths. The owned listener
was released. Current-city recall was not separately certified by this demo.
Demo minimum available RAM was 6,021,038,080 bytes; maximum commit 41.4995%.

Tests use fresh short Windows temporary paths, synthetic storage and an offline
guard blocking Ollama, physical MongoDB, external network and model subprocesses.
Suites are sequential with native owned-process cleanup and resource/health
monitoring. These monitors are experimental validation infrastructure, not shipped
runtime protection. Historical BSOD resolution is not claimed.

Historical unchanged-source evidence remains 968 unique Python 3.11 passes across
bounded segments, and 173 focused Python 3.12 passes. Neither is relabeled as a
new complete suite. The retained base-main hosted matrix has five successful
jobs in [run 41347026380](https://github.com/hamzah105/OOMP/actions/runs/41347026380).
The current unpushed candidate has no hosted Windows/Linux result.

## Submission and remaining gates

All four isolated installations imported OOMP from their fresh environment,
compiled and hash-matched all95 runtime modules, and had only the declared core
dependencies. No historical dependency directories, editable checkout or old
startup hooks were on their import paths. Optional MCP dependencies were reused
only for the separate guarded demo and focused tests, not misreported as a clean
core install. Installation was offline from previously cached wheels.

The public-source audit covered320 explicitly inventoried files, zero detected
high-confidence credential matches, the frozen query-controls checksum and pinned
Gate A/C evidence. The scan is not comprehensive credential detection. No private
database, credential file, TRACE source, model weight or generated environment
belongs in the staged inventory or archives.

The final documentation update is sealed into fresh distribution storage:
`.test-artifacts/submission-seal-20261107-r2/`. Its final package audit must verify
that only this report, readiness and documentation whitespace differ from the
already clean-installed source archives; all95 runtime modules, dependency
metadata and remaining archive members must agree. Clean installations are not
repeated for those documentation-only differences. The immutable final hashes,
comparison and installation evidence are retained with the submission package.

Submission location: `dist/OOMP-submission-20261107.zip`. It contains the wheel,
source archive (source/requirements/examples/docs/tests), selected small fictional
evaluation inputs/results, JUnit evidence and validation manifests. It excludes
databases, profiles/secrets, `.env`, model weights, environments, crash dumps and
entire experimental directories. `validation/submission-validation.json` records
the final executed gates and source/packaging equivalence, avoiding a circular
attempt to put an archive's own hash inside that archive.

No commit or push has occurred as of this source report's freeze. The authorized
local commit and final archive receipt are recorded after validation outside the
immutable source report. Push, merge, publication, deployment and release remain
unauthorized.

P4 Gate B remains incomplete, with no demonstrated answer-quality superiority.
Independent pilot users, independent/blinded answer adjudication, public
LongMemEval validation and controlled external Mem0/Graphiti comparisons remain
pending. New browser TRACE/MongoDB and real long-conversation model checks were
not run. See [manual testing](MANUAL-TESTING.md) and
[submission readiness](SUBMISSION-READINESS.md) for the exact bounded scope.
