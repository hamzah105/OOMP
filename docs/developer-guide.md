# Developer guide

Work from the repository root using Python 3.11 or 3.12. Runtime code is in
`src/oomp`; benchmarks, examples, tests and maintainer scripts are separate.
The project is alpha: covered interfaces are intentional, but 1.0 compatibility
is not promised. [Public API status](api-reference.md).

~~~powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade "pip>=26.2.2,<27"
.\.venv\Scripts\python.exe -m pip install -e ".[dev,mcp,ui]"
.\.venv\Scripts\python.exe -m pytest -v --basetemp .test-artifacts/dev-pytest
.\.venv\Scripts\python.exe -m compileall -q src tests benchmarks examples scripts
.\.venv\Scripts\python.exe -m pip check
~~~

Tests use synthetic events, local temporary SQLite and official SDK subprocess/
loopback clients. No actual MongoDB, Ollama, downloads, cloud key or personal
history is required. Optional installed SDK tests skip in core-only environments;
the complete acceptance suite and CI test matrix install `dev,mcp,ui`. Keep temporary
output ignored and do not replace production files to run examples.

## Boundaries and changes

- Domain contracts validate scope, identity, time, finite JSON and source shape.
- SQLite adapters own SQL, transactions, referential integrity and migrations.
- Extraction proposes grounded attributed claims; it never verifies truth.
- The graph policy governs protected relationships; ordinary adjacency is not authority.
- Retrieval reads one scoped snapshot, preserves proof and packs complete evidence.
- Mind handlers reuse existing services under durable leases/fences; providers perform no writes.
- MCP maps trusted grants to scopes using the official SDK. Remote arguments cannot mint authority.
- TRACE is an independent repository. Do not add its database or application imports to core.

Use four-space Python indentation, explicit UTF-8 for text artifacts, small typed
interfaces and standard-library tools where suitable. No formatter/linter is
silently mandated. Run compilation, targeted meaningful tests and the complete
regression suite for core/security/migration changes. Do not add tests that only
mirror a low-impact implementation or inflate counts without checking behavior.

## Migrations and providers

Current storage uses SQLite schema v6. Do not edit applied migration SQL or rewrite immutable event history
to implement a new feature. Add a reviewed migration, exact preservation/rollback
fixtures and explicit supported-version validation. Initialization is a trusted
local administrative action, never a side effect of reads or MCP connection.
Back up first with [SQLite's backup procedure](privacy-retention.md).

A new embedding provider implements `embed(texts)` and exposes an explicit
`EmbeddingSpace` identity for retrieval/indexing. Pin provider/model/version/
dimension, reject malformed vectors, keep I/O outside transactions, bound work
and disclose transport/data retention. Never mix spaces or use embeddings as
identity/verification. Propose providers through an issue/PR with offline mechanics
tests and separately labeled real-model results; no automatic model download.

MCP integrations must preserve official SDK parsing, server-owned grants,
host-held signing keys, role/provenance policy, bounds and private errors. New
hosts need actual client execution and prompt-budget accounting; discovery alone
does not certify compatibility. See [MCP security](mcp-security.md).

## Build and verify a release candidate

Use a separate tools environment or explicitly install maintainer requirements:

~~~powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-release.txt
.\.venv\Scripts\python.exe -m build
.\.venv\Scripts\python.exe -m twine check dist/*
.\.venv\Scripts\python.exe scripts/check_artifacts.py dist --output .test-artifacts/artifact-inventory.json
.\.venv\Scripts\python.exe scripts/check_clean_installs.py --dist dist --output .test-artifacts/clean-installs
~~~

Use a fresh/empty build output to avoid auditing an obsolete distribution under
the same version. Clean installation checks create new environments, install each
actual archive and run `python -I scripts/verify_install.py` against its installed
package/CLI. Wheel imports must resolve inside that environment, not editable
source. Source archives intentionally include benchmarks/docs/examples; runtime
wheels contain only OOMP modules and distribution metadata/licenses. No model,
database, credentials, output runs or TRACE source belongs in either archive.

CI is validation only: read-only permissions, first-party SHA-pinned actions,
Windows/Linux × 3.11/3.12 tests and an archive/clean-install job. Remote CI status
is pending until the user pushes and GitHub executes the workflows; local YAML
checks do not establish a passing matrix. No publishing/deployment workflow is
installed. [Release checklist](release-checklist.md), [Contributing](../CONTRIBUTING.md).
