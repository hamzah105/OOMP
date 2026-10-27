# Troubleshooting

Run commands from the checkout/source-archive root unless using an installed
`oomp` command. Use `.venv\Scripts\python.exe` on Windows when activation or the
bare Python launcher resolves to an unintended interpreter.

| Symptom | Check / action |
| --- | --- |
| Import or command missing | Install the reviewed source/wheel in the same environment. Compare `python -m pip --version` and `python -m oomp --version`; no TRACE dependency should be required. |
| Python/FTS not ready | Use Python 3.11+ with SQLite FTS5. `oomp doctor` checks package readiness; `oomp storage status --db PATH` checks a particular store. A doctor result does not assert a running worker/provider. |
| Database missing/uninitialized | Verify the explicit path, `OOMP_DB_PATH` and permissions. Reads do not create files. Deliberately initialize/migrate an intended store with `oomp storage init --db PATH`, after a consistent backup. |
| Foreign/newer schema | Stop and inspect versions/backup. Never reset or delete the database to bypass compatibility checks. Current schema is v5. |
| Busy/locked | Stop duplicate writers/long transactions, use bounded retries and local-disk storage. WAL is same-host coordination, not distributed access. Do not copy a live main file alone. |
| Event exists but no memory | Inspect source role, supported extraction grammar and explicit worker/job status. `memory extract` operates on an already stored event; accepted MCP ingestion does not run extraction automatically. |
| Empty retrieval | Check authorized tenant/namespace, canonical count, query terms, temporal eligibility, whole-evidence budget and index status. Unsupported wording can be a real miss; do not invent a result. |
| Semantic request fails | Confirm explicit provider/model/dimension/version and complete compatible embeddings. No automatic pull or silent semantic-to-lexical substitution occurs. Use deliberate hybrid degradation only when that behavior is acceptable. |
| Missing MCP imports | Install `.[mcp]` in the interpreter launching the server/client. CLI help and core operation should still work without it. SDK range is 2.3.x; unrelated future SDKs are not certified. |
| MCP unauthorized/forbidden | Verify the configured transport/grant, separate host signing key for writes, current bearer secret, expiry, exact Host/Origin and source-role policy. Do not paste tokens into URLs, logs or public issues. |
| MCP port/listener problem | Bind only the configured literal loopback address, inspect port conflicts, run `oomp mcp check --config PATH`; readiness does not initialize a missing DB. Stdio stdout belongs to MCP frames. |
| Host differs from sample | Use its actual documented command/argument/secret scheme. Only the exercised SDK clients are certified; generated host JSON is an illustration, not universal host compatibility. |
| Erasure blocked | Review the dependency plan and documented unsupported cases. Do not disable immutable triggers or remove proof manually to force a success response. |
| Benchmark output exists | Choose a new output path. Runs are never silently overwritten or resumed into duplicate counts. Partial runs stay partial. |
| Offline benchmark vectors unavailable | Expected without explicit real-model opt-in. Raw scheduled zeros/availability flags are not live vector-quality measurements. |
| Build omits research files | Build from the Stage 10 manifest/source candidate; inspect actual archives with `scripts/check_artifacts.py`. Do not upload a stale artifact left in `dist`. |

For a reproducible bug report include package/Python/SQLite/SDK versions, the
command shape, sanitized error code and a minimal synthetic fixture. Exclude
private contents, credentials, home paths and actual databases. Follow
[SECURITY.md](../SECURITY.md) for sensitive issues; private reporting setup is a
maintainer gate, not an invented support team or guaranteed response SLA.
