# Product milestone P1 — executed report

Prepared **2026-10-29 (Asia/Karachi)**. Scope: **P1 only**. OOMP remains
**0.1.0 / Apache-2.0 / SQLite v5**, an alpha local product candidate. No P2–P5
implementation, commit, push, release, public deployment or package publication.
Work stops for owner review. [Operator guide](product-onboarding.md),
[CLI/diagnostic contract](product-cli.md), [security/recovery](product-security.md).

## 1. Starting Git state

OOMP `D:\Desktop\OOMP` began clean on `main` at
`e4b1b64109a92dc83c7c27d24e129f2f5cb54d8a` (Implement OOMP Stage 10).
Its tracked origin/main had the same SHA, with ahead/behind **0/0**. The remote
URL is https://github.com/hamzah105/OOMP. No fetch/live remote reconciliation,
reset, history rewrite or Git mutation was performed by P1. Upstream status is
reported from inspected local tracking state, not a new remote CI assertion.
TRACE began and remains clean at `af202ef43daf70280d2e8915210816f788e8aff1`.
The attached product roadmap was read in full; historical `docs/roadmap.md`
remains byte-identical and is not replaced by the new P1–P5 proposal.

## 2. Baseline tests and environment

Before source edits, **515 passed in 490.43s**, exit 0, zero failures/errors/skips.
Baseline XML/text, initial Git state and hashes are in ignored
`.test-artifacts/product-P1-20261029/`. The primary environment is Windows,
CPython **3.11.4**, SQLite **3.42.0**, Pydantic **2.14.1**, pytest **9.1.1**,
MCP/mcp-types **2.3.0**, uvicorn **0.54.0**, pip **26.2.2** and setuptools
**84.2.1**. Rich/Questionary were absent before P1. Independent compatibility
was exercised in a fresh **CPython 3.12.6** environment with an actual built wheel.
These interpreter patch versions establish compatibility, not runtime-security
endorsement; deploy on currently patched supported Python/SQLite/OS versions.

## 3. Final implementation

P1 adds guided/previewed setup, bounded read-only discovery, protected profiles,
new-database creation, credential references, atomic configuration generations,
explicit service ownership, lifecycle/status/logs, structured diagnostics and
reversible host templates. Defaults are standalone, literal IPv4 loopback HTTP,
read-only, lexical-only, no original-source text permission and a separately
supervised Mind worker. No worker or model starts on import/setup/discovery.
A real synthetic example exercises signed intake through the managed services,
canonicalization/indexing, source proof, restart and shutdown.

The core engine is reused. No new extraction grammar/LLM extractor, episode or
object-tree architecture, retrieval strategy, adaptive host prompt or benchmark
campaign was implemented. Existing domain/approval/schema contracts remain intact.

## 4. Architecture and process decisions

`src/oomp/product/` contains settings/safety/discovery/UI, the additive CLI,
profiles, bounded SDK probes, supervision/children and a fixed TRACE bridge.
`oomp up` is foreground by default. `--background` explicitly detaches an owning
supervisor and waits for readiness. MCP, Mind and the optional approved publisher
are separate retained subprocess handles; host API, MongoDB and Ollama remain
independently owned. No autorun/OS service/public listener is installed.

A held OS file lock serializes setup/config/lifecycle. Private per-run credentials
and instance IDs authenticate a bounded loopback control socket. PIDs are
informational: stale/PID-reused state cannot authorize a signal. Shutdown uses
owned child stdin messages/EOF, then bounded termination of retained handles.
A child crash/start failure stops its siblings; restart is explicit. Heartbeat and
work progress are distinct, with 180-second worker progress supervision. Startup,
control requests, child output, log sizes, provider calls and shutdown are bounded.
No arbitrary discovered project command is executed. The operator-only `host`
command requires explicit argv/approval.

## 5. New commands and behavior

| Command | Behavior |
| --- | --- |
| `onboard [--project PATH]` | Wizard or explicit unattended setup; preview, dry-run and distinct credential/write/host approvals |
| `config`, `reconfigure` | Inspect settings/references; atomic operational edits without secret rotation or identity rebind |
| `up [--background]` | Explicit supervision; actual authenticated SDK status before readiness |
| `down`, `restart` | Stop owned processes gracefully; preserve durable data and credentials |
| `status`, `logs` | Authenticated liveness/ownership/progress and bounded safe operational codes |
| `doctor --full [--json]` | Measured environment/profile/storage/worker/MCP/index/provider checks plus isolated synthetic proof |
| `install --project PATH` | Connect an installed distribution by generating/optionally exporting a reference template |
| `uninstall-integration --dry-run` | Preview removal of only an unchanged same-file owned export |
| `connect` | Host-owned stdio MCP with protocol-only stdout and no implicit worker |
| `host --approve-host -- ARGV...` | Run an explicit reviewed host command with profile credentials in its environment |

Existing working commands/arguments and bare `doctor` behavior are preserved.
Diagnostic format v1 reports PASS/WARN/FAIL/NOT TESTED; `ok` means no FAIL, not
that every optional surface was exercised. Details and exit codes are documented
in [the CLI reference](product-cli.md). HTTP remains the default; a stdio profile's
MCP process belongs to its host and is not falsely advertised as supervised/tested.

## 6. Exact changed paths

**21 new files:**

- `docs/product-cli.md`
- `docs/product-milestone-P1-report.md`
- `docs/product-onboarding.md`
- `docs/product-security.md`
- `examples/product_quickstart.py`
- `src/oomp/product/__init__.py`
- `src/oomp/product/cli.py`
- `src/oomp/product/diagnostics.py`
- `src/oomp/product/discovery.py`
- `src/oomp/product/lifecycle.py`
- `src/oomp/product/models.py`
- `src/oomp/product/profiles.py`
- `src/oomp/product/protocol.py`
- `src/oomp/product/safety.py`
- `src/oomp/product/services.py`
- `src/oomp/product/trace_service.py`
- `src/oomp/product/ui.py`
- `tests/test_product_diagnostics.py`
- `tests/test_product_lifecycle.py`
- `tests/test_product_profiles.py`
- `tests/test_product_trace.py`

**16 modified tracked files:**

- `.github/workflows/ci.yml`
- `CHANGELOG.md`
- `CONTRIBUTING.md`
- `README.md`
- `THIRD_PARTY_NOTICES.md`
- `docs/api-reference.md`
- `docs/background-mind.md`
- `docs/developer-guide.md`
- `docs/getting-started.md`
- `docs/limitations.md`
- `docs/mcp-integration.md`
- `docs/privacy-retention.md`
- `docs/security-model.md`
- `docs/troubleshooting.md`
- `pyproject.toml`
- `src/oomp/cli.py`

Changes remain uncommitted on the starting main HEAD. No unrelated preexisting
working-tree edits were present. Generated logs, environments, synthetic databases,
raw acceptance artifacts and distributions are ignored, not committed sources.

## 7. Dependencies and supply chain

Core remains `pydantic>=2.9,<3`; existing dev/MCP constraints and console entry
point are unchanged. The optional `[ui]` extra pins **Rich 15.0.0** and
**Questionary 2.1.1**, both MIT metadata, compatible with the tested interpreters.
Their installed transitive UI versions include prompt_toolkit 3.0.53, wcwidth
0.9.4, markdown-it-py 4.2.0 and mdurl 0.1.2. No UI implementation is vendored and
no TUI dependency is required by core. Exact metadata/license-file inventory is
saved separately, rather than assuming licenses for all future dependency versions.

Selection used [Rich's primary terminal/NO_COLOR documentation](https://rich.readthedocs.io/en/latest/console.html)
and [Questionary's primary keyboard/cancellation API](https://questionary.readthedocs.io/en/stable/pages/advanced.html),
official PyPI metadata and actual installation/keyboard execution. No Typer/CLI
rewrite was needed; argparse preserves earlier commands.

pip-audit **2.10.1** returned exit 0 / **zero known advisories** for both actual
resolved environments: 45 records in 3.11 and
43 in 3.12. The local `oomp-memory` project was skipped in
both because it has no matching PyPI advisory record; this does not certify its
source. Scanner scope excludes CPython/SQLite/OS, provider weights and all logic
vulnerabilities. No broad runtime dependency upgrade or model download occurred.

## 8. Security and privacy review

New files use protected current-user/SYSTEM Windows DACLs or owner-only POSIX
modes. Profile names/paths reject traversal, linked/reparse paths and private-file
hardlinks. Custom database parents must already be private. Existing data and
credentials are never silently overwritten/adopted. Interrupted setup checks its
new-file claim; unused incomplete generations do not replace active configuration.
Host exports require explicit confirmation and are reversed only with matching
file identity and digest; modified/replaced/unowned files remain intact.

Normal output/logs/plans contain references/counts/codes, not secret values or
private source text. Raw child stderr is not copied to operational logs. Read,
owner and role-specific bearer/signing values are distinct. Read-only/source and
signed-ingest boundaries were exercised with actual SDK clients. Worker crashes
and stale state do not create a privileged erasure/approval path.

Doctor never initializes/migrates/overwrites a private database. It uses bounded
immutable main-file snapshots only when WAL is absent/empty and stable; nonempty
WAL is NOT TESTED offline, with current live SDK status checked separately.
Synthetic diagnostic writes use a separate temporary database. The normal user
`%LOCALAPPDATA%\OOMP\trace-local.sqlite3` was never selected/opened for P1 setup,
smoke or repair. No real TRACE `.env`, credentials, Mongo records or conversation
backfill was used. Local administrators and explicitly approved host code remain
trusted; plaintext storage, physical erasure/backup limits and local HTTP trust
are unchanged. This was a focused engineering review, not a penetration test.

## 9. Configuration and compatibility

Profile format **1** is separate from memory schema **5**. Settings use platform
user-data/configuration paths or explicit `--home` / `OOMP_PROFILE_HOME`; OOMP
loads no ambient `.env`. New random credentials require confirmation, while
existing keys persist through idempotent setup/restart/config changes. Environment
mode stores references rather than copying secret values. No migration of existing
owners/scopes or database schema is performed.

Managed HTTP binds only 127.0.0.1. TRACE requires explicit owner and HTTP, with
separate role/source grants matching its existing wire contract. Provider selection
is explicit and local-only; managed Mind then enables automatic embedding of
newly extracted canonical text to that selected loopback provider. Doctor uses
only fixed synthetic text for provider probing. Lexical profiles make no model calls.
Source-text permission remains off unless selected; TRACE uses its own Mongo
provenance validator and does not require an invented get_source path.

## 10. Executed tests, counts, failures and skips

| Complete run | Result | JUnit elapsed | Failures/errors/skips |
| --- | --- | --- | --- |
| Pre-edit Python 3.11 baseline | **515 passed** | 490.43s (pytest summary) | 0/0/0 |
| Final Python 3.11 source environment | **575 passed** | 812.13s | 0/0/0 |
| Final Python 3.12 installed-wheel environment | **575 passed** | 810.10s | 0/0/0 |

The 60 new cases cover discovery/nonexecution, profiles/ACLs, secret references,
interruption/recovery, atomic config failure, linked paths/devices, cancellation,
actual optional arrow menus/Ctrl+C, no-color/missing UI, no-mutation diagnostics,
missing SDK/interpreter/provider, schemas, invalid credentials/scope, actual signed
MCP/Mind/provenance, independent-port collision, duplicate starts, stale state/PID
reuse, failed/crashed worker cleanup, Ctrl+C cleanup branch, stdio and the complete
public synthetic example/restart. All 34 original test files remain unchanged.
The Ctrl+C supervisor test injects Python KeyboardInterrupt at the ready boundary;
it is not a claim that an unattended shell generated a literal keyboard keypress.

Earlier complete 575/575 runs also passed before the final file-plan tightening;
focused batches passed 41, then 49 and 57 cases as coverage grew. The final
post-review TRACE policy subset passed eight cases. Genuine findings corrected:
shutdown's transient control-close/stopped-record race; the background launcher's
missing explicitly selected Mongo reference. A fixture initially called
get_source, which TRACE's existing client intentionally disallows; the fixture
was corrected to its actual Mongo provenance validator, without changing TRACE.
A PowerShell 5.1 stdin Unicode-literal issue and inherited NO_COLOR in a test
harness were corrected; actual Unicode paths and the actual menu then passed.
A later full run exposed a Windows MAX_PATH boundary in the atomic temporary filename. Compact temporary names and a UTF-16 path-budget preflight fixed it; the previously failing claimed setup resumed without credential rotation, and its two-case focused regression passed. The failed full-run logs remain retained. No final accepted test failures/errors/skips remain. Build manifest no-match warnings and
Git LF/CRLF normalization notices are informational; artifact members are audited.

## 11. Fresh installation and packaging

Wheel and sdist are built under `dist/product-P1/`; existing Stage 10 distributions
are not overwritten. `twine check`, archive policy/metadata/license checks and
source/member byte freshness passed. Both final artifacts were installed in
separate new core-only environments using the release verifier: isolated import,
legacy CLI/source-to-proof flow and dependency consistency passed without TRACE,
MCP or UI in core. Additional core-only P1 checks exercised help, dry-run setup,
JSON diagnostics and clean failure/cleanup when optional MCP was unavailable.

The separate fresh Python 3.12 wheel environment includes dev/MCP/UI; imports are
asserted inside site-packages, not a source-tree substitute. Its complete suite,
actual lifecycle example and final installed verifier passed. The same final
runtime modules are compared byte-for-byte to source and the tested candidate.
Final artifact names/hashes/bytes/member counts are saved externally in
`.test-artifacts/product-P1-20261029/artifact-inventory.json`; the self-containing
sdist report does not embed its own hash. No database/WAL, model weight, private
generated directory or high-confidence credential pattern was found in the bounded
archive scan. Such scanning is not proof of absence of every possible secret.

## 12. Synthetic MCP and Mind integration

`examples/product_quickstart.py` uses only fresh temporary/explicit-new directories,
including a tested Unicode path with spaces. It configures a synthetic trusted
profile, invokes actual CLI up/background, submits an exactly approved user event,
waits for separate durable Mind extraction/indexing, retrieves original IDs/proof,
runs full doctor, restarts without identity loss and shuts down. No real model
call is made. Raw source and installed acceptance reports are retained separately.
Read-only, unauthorized token/scope, unsigned/reader writes, worker startup failure,
crash and listener cleanup are separate negative regressions, not inferred passes.

## 13. TRACE compatibility findings

The optional publisher was exercised as a **third supervised subprocess** using
an explicitly approved disposable copy of tracked TRACE integration modules and
in-memory Mongo emulation. No real Mongo/API/Ollama service was used or required.
The bridge reuses TRACE Publisher and its existing work generator, with explicit
local connection/database selection and a child-only legacy database facade that
prevents default `.env` loading. Hash checks cover adapter/bootstrap files, not a
complete software supply-chain attestation.

The actual independent TRACE client negotiated **2026-07-28**, read the published
memory and used its actual `validate_provenance` function against synthetic
owner-linked Mongo rows. Positive/negative owner credential checks, wrong-owner
proof and wrong MCP token checks passed. Host code imported no OOMP internal
module. API/OAuth browser login and live generation were not executed; full doctor
correctly reports host login NOT TESTED.

Measured command times in that prepared local fixture: onboard
**1.250s**, up-to-ready
**6.484s**,
full doctor **2.688s**,
down **3.359s**.
The earlier five-terminal experience was user-reported and not timed comparably.
This demonstrates one managed launch for selected OOMP-owned services, not an
independent fresh-user setup-time study or a five-minute guarantee.
All 81 real TRACE tracked files and its clean starting HEAD remain unchanged.

## 14. Verified output and local commands

The fixture's actual `doctor --full --json` returned `ok:true`, **22 PASS, zero
WARN/FAIL, two NOT TESTED** (no provider and host login unexercised). Standalone
acceptance similarly checks actual authenticated readiness and source proof;
NOT TESTED/empty optional surfaces are not represented as success.
Machine output is safe structured data; normal menu output respects NO_COLOR.

~~~powershell
# Run from D:\Desktop\OOMP; basetemp/output paths must be fresh on rerun.
.\.venv\Scripts\python.exe -m pytest -v --basetemp .test-artifacts/product-P1-20261029/a311 --junitxml=.test-artifacts/product-P1-20261029/tests311-accepted.xml
.\.test-artifacts\product-P1-20261029\python312\Scripts\python.exe -m pytest -v --basetemp .test-artifacts/product-P1-20261029/a312 --junitxml=.test-artifacts/product-P1-20261029/tests312-accepted.xml
.\.venv\Scripts\python.exe -m compileall -q src tests benchmarks examples scripts
.\.venv\Scripts\python.exe -m pip check
.\.test-artifacts\product-P1-20261029\python312\Scripts\python.exe -m pip check
.\.venv\Scripts\oomp.exe doctor
.\.test-artifacts\stage10\tools\Scripts\python.exe -m build --outdir dist/product-P1
.\.test-artifacts\stage10\tools\Scripts\python.exe -m twine check dist/product-P1/*
.\.venv\Scripts\python.exe scripts/check_artifacts.py dist/product-P1 --output .test-artifacts/product-P1-20261029/artifact-inventory.json
.\.venv\Scripts\python.exe scripts/check_clean_installs.py --dist dist/product-P1 --output .test-artifacts/product-P1-20261029/clean-installs-final
.\.test-artifacts\product-P1-20261029\python312\Scripts\python.exe -I scripts/verify_install.py --output .test-artifacts/product-P1-20261029/python312-installed-final
.\.test-artifacts\product-P1-20261029\python312\Scripts\python.exe examples/product_quickstart.py --directory .test-artifacts/product-P1-20261029/installed-product-final
.\.test-artifacts\stage10\tools\Scripts\python.exe -m pip_audit --path .venv/Lib/site-packages --format json --output .test-artifacts/product-P1-20261029/dependency-audit-311.json --cache-dir .test-artifacts/product-P1-20261029/audit-cache
.\.test-artifacts\stage10\tools\Scripts\python.exe -m pip_audit --path .test-artifacts/product-P1-20261029/python312/Lib/site-packages --format json --output .test-artifacts/product-P1-20261029/dependency-audit-312.json --cache-dir .test-artifacts/product-P1-20261029/audit-cache
git diff --check
~~~

Manual review without touching a normal profile:

~~~powershell
.\.venv\Scripts\oomp.exe onboard --profile p1-review --dry-run --plain
.\.venv\Scripts\python.exe examples/product_quickstart.py
~~~

To experience the actual guided setup, separately run `oomp onboard --profile
NAME` and review the displayed plan. That creates a new per-user profile only
when confirmed. Use [the operator guide](product-onboarding.md) for foreground/
background operation, a selected project or a deliberately approved TRACE fixture.

Evidence includes `baseline.json`, baseline/full JUnit/text logs,
`trace-fixture-validation.json`, `ui-validation.json`, `preservation-audit.json`,
`dependency-audit-*.json`, `dependency-inventory.json`, `workflow-validation.json`,
`documentation-audit.json`, `final-static-checks.json`, `artifact-inventory.json`,
`archive-freshness.json`, `clean-installs-final/clean-installs.json`,
`core-product-validation.json`, `python312-installed-final/installation.json`
and `installed-product-final/acceptance.json` under the ignored artifact root.

## 15. Limitations and deferred functionality

Actual local validation is Windows on the two interpreters above. **Linux/macOS
were not executed locally and remote GitHub Actions was not run by P1.** The CI
matrix remains Windows/Ubuntu × 3.11/3.12 and now installs the optional UI as well;
local YAML/permission/SHA/matrix checks passed. Configured jobs are not CI results.
No WSL distribution was available for Linux acceptance.

This is local administrator tooling: plaintext stores, trusted host/interpreter
code, loopback assumptions, bounded SQLite and existing secret/extraction/erasure
limitations remain. Linked host interpreter paths are refused; the optional managed
TRACE role was exercised with a regular Windows interpreter. A named desktop/browser
host, live external provider/model availability, real Mongo server/OAuth/API,
independent fresh-user trial, all forced-shutdown delivery scenarios and OS/runtime
security certification were not established. Stdio belongs to its host; generic
framework discovery is an indicator/template, not universal auto-integration.
No OS service manager, public transport, arbitrary auto-patching or automatic
legacy data migration is provided.

## 16. Unresolved issues and acceptance boundaries

No unresolved failing local acceptance test or known scanned dependency advisory
remains in scope. Remote/Linux validation and an actual external-host/provider
operational sign-off remain **unexecuted checks**, not claimed successes. Real
TRACE stayed reference-only as requested; its private deployment was not converted
or certified. The mocked Mongo fixture verifies actual publication/auth/proof
logic but does not certify live database connectivity/topology.

The preservation audit verifies 54 existing engine modules (all except the
intentionally extended root CLI), 34 original test files, 25 benchmark source/config
files, 18 historical report/validation/roadmap files, nine workspace data files,
372 frozen benchmark artifacts and 81 TRACE tracked files against baseline.
Existing runtime/MCP constraints, Apache-2.0 and v5 migration source are unchanged.
Normal personal AppData memory was not selected for tests; preservation is based
on not opening/targeting it, not an invented pre/post content audit.

## 17. Recommendation and P2 prerequisites

**P1 local implementation is ready for owner review**, with the explicit platform
and external-service limits above. Review the diff, run the disposable example,
inspect the report/operational threat boundaries and confirm that the new workflow
meets the intended developer experience. Before claiming Linux/CI compatibility,
run and inspect the actual matrix after a separately authorized commit/push.
Before any real TRACE transition, separately approve its owner/configuration,
credentials, backup and operational procedure; P1 did not alter that deployment.

P2 requires separate owner authorization and an agreed synthetic/source-grounded
quality fixture/provider policy. Preserve existing scopes, source roles, approval,
erasure and immutable history when considering it. No P2 fixture, extractor,
episode schema or later milestone was implemented here. No commit, push, package
upload, release, public deployment or automatic continuation follows this report.
