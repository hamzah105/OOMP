# Stage 10 validation — 2026-10-27

Status: **local conditional alpha research candidate**. Version **0.1.0**, package
**oomp-memory**, license **Apache-2.0**, SQLite **v5**. No commit, push, tag,
GitHub Release, PyPI upload or public deployment was performed. See the
[40-item report](stage-10-report.md), [security review](security-review.md) and
[human release gates](release-checklist.md).

## Baseline and test acceptance

The initially clean OOMP main HEAD, origin/main and live remote main were all
`ca7f6e6e1c28807f3d32881e2fc5ea5a6a7e7207`. This includes the reconciled remote
LICENSE commits. All Stage 9 source/reports/output were present. The existing suite
was executed **before edits: 498 passed in 463.66s**.

| Executed environment | Final complete suite (JUnit time) | Failures / errors / skipped |
| --- | --- | --- |
| Windows, CPython 3.11.4, source development environment | **515 passed in 799.35s** | 0 / 0 / 0 |
| Windows, CPython 3.12.6, clean wheel installation with dev/MCP extras | **515 passed in 805.26s** | 0 / 0 / 0 |

The 515 cases comprise **498 preserved cases plus 17 release cases**. Earlier
intermediate full runs also passed 514/514 before the Stage 5 example regression
was added. Neither intermediate run is substituted for final acceptance. Existing
33 test files and 55 runtime Python files remain byte-identical to baseline.

Baseline SQLite was 3.42.0; Pydantic 2.14.1, pytest 9.1.1, MCP/mcp-types 2.3.0,
AnyIO 4.15.1 and uvicorn 0.54.0 were inspected. Runtime/extras constraints are
unchanged. The interpreter versions above establish compatibility; use currently
patched supported Python/SQLite/OS versions for deployment. Other Python versions
and local Linux execution were not validated.

## Distributions and independent installation

`python -m build`, `twine check` and archive-policy validation passed for
`dist/oomp_memory-0.1.0-py3-none-any.whl` and
`dist/oomp_memory-0.1.0.tar.gz`. The final rebuild includes this completed report.
Exact final SHA-256, byte/file counts and license fields are recorded separately in
`.test-artifacts/stage10/artifact-inventory.json`; these self-containing source
reports intentionally do not embed their own source-archive hash.

A fresh non-editable installation directly from the source checkout also passed
the isolated core-only CLI/event/provenance verifier on Python 3.12.6. Both final
archives were installed into separate new core-only environments using
`scripts/check_clean_installs.py`. Each passed `pip check`, actual installed CLI
checks and a persisted event → extraction → indexing → evidence/provenance → reopen
flow. The verifier uses `python -I`, outside the checkout, and asserts the package
comes from the environment's site-packages. Core-only installations have neither
MCP nor TRACE/backend installed. Python 3.12 additionally exercised the wheel with
optional MCP/dev dependencies, actual protocol clients and the complete suite.

Final archive checks reject unsafe/private paths, databases/WALs, caches, model
weights, result directories and high-confidence credential patterns. None were
found. This bounded scan is not proof that every possible secret pattern is absent.
LICENSE and NOTICE are included in both distributions. The sdist includes intended
benchmark source/configs, examples, documentation, scripts and tests; generated raw
benchmark outputs remain excluded. Runtime modules and intended source members are
compared to their current source bytes in the final freshness audit.

## Executed synthetic acceptance

All nine installed-wheel example conditions passed on Python 3.12.6: quickstart,
WAL-safe backup/restore, Stages 2–6, MCP stdio and MCP Streamable HTTP. Stage 6
covers bounded explicit worker/restart behavior. The official SDK negotiated
protocol **2026-07-28** for both transports. Read-only startup does not start a
worker. Existing complete suites retain trusted-ingestion separation, hostile
HTTP/stdio input, source permissions, tenant isolation, erasure and lease-fencing
regressions. No live model service, model download, TRACE process, MongoDB or
private source data was used.

Quickstart recovers an early synthetic fact after 12 later unrelated events,
outside the latest eight, with original provenance and a bounded evidence packet.
Backup validation keeps a WAL connection open, commits an event, uses SQLite's
online backup API and verifies it in a restored new database. Existing destinations
are refused. Full database backup crosses all stored scopes; administrators must
protect backups and reconcile erasure after restoration.

The benchmark smoke ran twice with seed 13, development split, size 16,
long-history and negative-control scenarios, five methods, byte budget 12,000 and
100 bootstrap samples: **2 histories, 8 queries and 40 records per run**, with
identical non-timing metrics/status/source rankings and **zero model calls**.
These are repeated executions of the same two histories, not four independent
samples. Dataset hash `b4f320b9a6771ba45c1bb3c1e5ed706c57a1d7b0312f96854166006ce8d33f64`;
config hash `6d5e72eec6deae92c354de05882804015c333a0859d98f4958c9e9af5afada9b`.
No Stage 9 result was regenerated or changed to improve outcomes.

## Security, supply chain and isolated repairs

The focused source/test review covers storage/migrations, source grounding,
graph authorization, retrieval bounds/model spaces, worker fences/erasure and MCP
credentials/permissions/Host/Origin limits. It is not an independent penetration
test. No core security API or algorithm was weakened or redesigned.

The initial dependency scan reported **15 advisory entries in two tools**, with
eight distinct advisory IDs (duplicate pip IDs included). pip 23.1.2 and
setuptools 84.0.0 were patched to **26.2.2 / 84.2.1** in local tooling; the backend
requires setuptools >=84.1,<85. Final pip-audit **2.10.1** scans of base and clean
Python 3.12 dependencies reported **zero known advisories**. Both skip the local,
unpublished `oomp-memory` package, which has no PyPI advisory record. This does not
scan CPython/SQLite, model weights or all source logic. Runtime dependency ranges
were preserved; no broad runtime upgrade was performed.

Other isolated repairs: explicit sdist manifest (the baseline omitted benchmark
code/docs/examples despite shipping Stage 9 tests); Stage 5 example assertion and
printed schema corrected from v4 to existing v5; one literal formatting placeholder
in Stage 9 validation replaced by its already recorded **87,334,912-byte** value.
The failing pre-repair example regression and first failed installed example log
are retained; the repaired example and regression pass. Earlier stage reports,
all 372 frozen benchmark files, nine existing database/WAL files and all 81 tracked
TRACE files remain hash-identical. TRACE HEAD/status remain unchanged and clean.

## CI and manual gates

The workflow has Windows/Linux × Python 3.11/3.12 test jobs and an Ubuntu build /
metadata / archive / clean-install job. It uses first-party SHA-pinned checkout
and setup-python, contents:read, no persisted checkout credentials, synthetic
fixtures and no publish/deployment job or secrets. Local YAML parsing and
structural security/matrix checks passed. **GitHub Actions has not run**, because
the candidate has not been committed/pushed. **Linux was not executed locally**;
no usable WSL distribution was installed. Package installation uses package-index
access; the runtime tests require no remote model/private service.

Public repository issues and Apache-2.0 were verified. Private vulnerability
reporting was not verified/configured; enabling it or establishing a real
confidential contact is a pre-publication gate. Official PyPI JSON/simple endpoints
for the exact name returned 404 during preparation, which is not a reservation or
future availability guarantee. Human license/attribution review, candidate
acceptance, account rights and actual remote CI results remain required.

## Commands and evidence

The following checks were executed; output destinations must be fresh on rerun.
Raw local logs, XML, scanner results and synthetic databases live under ignored
`.test-artifacts/stage10/`, not in the release source or wheel.

~~~powershell
# Workspace: D:\Desktop\OOMP. All data/output paths below are disposable.
.\.venv\Scripts\python.exe -m pytest -v --basetemp .test-artifacts/stage10/acceptance-pytest311 --junitxml=.test-artifacts/stage10/tests311-final.xml
.\.test-artifacts\stage10\python312\Scripts\python.exe -m pytest -v --basetemp .test-artifacts/stage10/acceptance-pytest312 --junitxml=.test-artifacts/stage10/tests312-final.xml
.\.venv\Scripts\python.exe -m compileall -q src tests benchmarks examples scripts
.\.venv\Scripts\python.exe -m pip check
.\.test-artifacts\stage10\python312\Scripts\python.exe -m pip check
.\.venv\Scripts\oomp.exe doctor
git diff --check
.\.test-artifacts\stage10\tools\Scripts\python.exe -m build
.\.test-artifacts\stage10\tools\Scripts\python.exe -m twine check dist/*
.\.venv\Scripts\python.exe scripts/check_artifacts.py dist --output .test-artifacts/stage10/artifact-inventory.json
.\.venv\Scripts\python.exe scripts/check_clean_installs.py --dist dist --output .test-artifacts/stage10/clean-installs-final-docs
.\.test-artifacts\stage10\python312\Scripts\python.exe -I scripts/verify_install.py --output .test-artifacts/stage10/python312-installed-flow-final-docs
# Scanner is isolated from the application environments.
.\.test-artifacts\stage10\tools\Scripts\python.exe -m pip_audit --path .venv/Lib/site-packages --format json --output .test-artifacts/stage10/dependency-audit-patched.json
.\.test-artifacts\stage10\tools\Scripts\python.exe -m pip_audit --path .test-artifacts/stage10/python312/Lib/site-packages --format json --output .test-artifacts/stage10/dependency-audit-python312.json
~~~

The final wheel was reinstalled with `--force-reinstall --no-deps` before the final
Python 3.12 verifier. Installed example invocations are below; the recorded runner
resolved absolute paths, removed PYTHONPATH, set disposable TEMP/TMP and executed
from outside the checkout. These examples import the installed runtime, not src.

~~~powershell
$releasePython = '.\.test-artifacts\stage10\python312\Scripts\python.exe'
# Use fresh paths; existing quickstart and backup destinations are refused.
& $releasePython examples/quickstart.py --db .test-artifacts/stage10/installed-examples/quickstart.sqlite3
& $releasePython examples/backup_restore.py --directory .test-artifacts/stage10/installed-examples/backup-demo
& $releasePython examples/stage2_event_roundtrip.py --db .test-artifacts/stage10/installed-examples/stage2.sqlite3
& $releasePython examples/stage3_memory_extraction.py --db .test-artifacts/stage10/installed-examples/stage3.sqlite3
& $releasePython examples/stage4_temporal_graph.py --db .test-artifacts/stage10/installed-examples/stage4.sqlite3
& $releasePython examples/stage5_hybrid_retrieval.py --db .test-artifacts/stage10/installed-examples/stage5-final.sqlite3
& $releasePython examples/stage6_background_mind.py --db .test-artifacts/stage10/installed-examples/stage6.sqlite3
& $releasePython examples/stage7_mcp_client.py --transport stdio
& $releasePython examples/stage7_mcp_client.py --transport streamable-http
.\.venv\Scripts\python.exe -m benchmarks.runner --config .test-artifacts/stage10/benchmark-smoke-config.json --output .test-artifacts/stage10/benchmark-smoke-first
.\.venv\Scripts\python.exe -m benchmarks.runner --config .test-artifacts/stage10/benchmark-smoke-config.json --output .test-artifacts/stage10/benchmark-smoke-second
~~~

The smoke's ignored config is captured alongside its hash. Portable reproduction
from shipped configs is documented in [benchmark reproduction](benchmark-reproduction.md).
Evidence files: `baseline.json`, `baseline-tests.xml`, `tests311-final.xml`,
`tests312-final.xml`, `final-static-checks.json`, `preservation-audit.json`,
`example-validation-final.json`, `benchmark-reproduction.json`,
`dependency-audit-*.json`, `workflow-validation.json`, `build-final.txt`,
`twine-check-final.txt`, `artifact-inventory.json`, `archive-freshness.json`,
`clean-installs-final-docs/clean-installs.json`,
`source-installed-flow/installation.json` and
`python312-installed-flow-final-docs/installation.json`.

Compilation, both `pip check` commands, `oomp doctor` and `git diff --check` passed.
Build emits harmless manifest no-match warnings for optional `.yaml` and excluded
private/generated patterns; all 186 intended source files were verified in the
archive. Git reports LF-to-CRLF normalization notices for two edited text files.
No final test failures/errors/skips were recorded. Initial old-tool advisories and
the stale example failure were repaired and retained as evidence. No unresolved
critical code/licensing flaw was identified within this bounded review; the
publication gates above still apply.
