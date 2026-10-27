# Getting started

Use a checkout or unpacked source archive, Python 3.11+ and SQLite with FTS5.
The core package is independent of TRACE. Keep private data outside the source
tree in a directory whose filesystem permissions you control.

Before the maintainer pushes the release-preparation commit, the new guides and
examples exist only in the local candidate/source archive. Fresh environment and
artifact installation were tested locally; no remote clone is claimed to include
uncommitted files.

## Windows source installation

From the project root:

~~~powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade "pip>=26.2.2,<27"
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\oomp.exe doctor
.\.venv\Scripts\python.exe examples/quickstart.py --db data/first-demo.sqlite3
~~~

The example initializes a **new** file, appends a synthetic user event, uses
`ExtractionPipeline.process_event`, checks the lexical index, appends unrelated
observations and retrieves the old project with its source proof. Existing files
are refused. A repeated trial must choose a new name or omit `--db` for a fresh
temporary example. Never point an example at a private production database.

Inspect the persisted synthetic result:

~~~powershell
.\.venv\Scripts\oomp.exe storage status --db data/first-demo.sqlite3
.\.venv\Scripts\oomp.exe memory list --db data/first-demo.sqlite3 --tenant synthetic-quickstart --namespace demo
.\.venv\Scripts\oomp.exe retrieve "What project am I developing?" --db data/first-demo.sqlite3 --tenant synthetic-quickstart --namespace demo --token-budget 3000 --show-content --json
~~~

Source ingestion is currently a Python API or separately approved MCP operation;
there is no invented `oomp event add` command. The example prints original source
IDs/references; `SQLiteEventStore.get(scope, event_id)` returns the original event.
All printed content here is fictional. Default CLI listing/retrieval hides text.

## Minimal Python usage

See [examples/quickstart.py](../examples/quickstart.py) for the complete executable
construction. The important operations, with an existing authorized `scope` and
validated `event`, are:

~~~python
from oomp.storage import SQLiteEventStore
from oomp.ingestion import ExtractionPipeline
from oomp.retrieval.engine import RetrievalEngine
from oomp.retrieval.contracts import RetrievalRequest

store = SQLiteEventStore("data/my-authorized-memory.sqlite3")
store.initialize()  # explicit creation/migration, not performed on reads
store.append(scope, event)
ExtractionPipeline(store.path).process_event(scope, event.event_id)
engine = RetrievalEngine(store.path)
engine.index(scope)
result = engine.retrieve(scope, RetrievalRequest(
    tenant_id=scope.tenant_id, namespace=scope.namespace,
    query="project developing", token_budget=3000,
))
original = store.get(scope, event.event_id)
~~~

This block illustrates API calls; `scope` must be issued by trusted application
code and `event` must include actual role, timestamps and source reference. A
caller-created `AuthorizedScope` does not authenticate a network user.

## Optional operations

Install `.[mcp]` for the official SDK/HTTP server; `.[dev,mcp]` adds tests.
Benchmark code uses the core dependencies and ships in the source archive rather
than the runtime wheel; execute it from that archive's root. Maintainer tools live
in `requirements-release.txt`, outside core runtime requirements.

~~~powershell
.\.venv\Scripts\python.exe -m pip install ".[dev,mcp]"
.\.venv\Scripts\python.exe examples/stage6_background_mind.py --db data/mind-example.sqlite3
.\.venv\Scripts\python.exe examples/stage7_mcp_client.py --transport stdio
.\.venv\Scripts\python.exe examples/stage7_mcp_client.py --transport streamable-http
~~~

For an intended initialized store, `oomp mind run-once --db PATH --tenant TENANT
--namespace NAMESPACE --max-jobs 16` performs a bounded pass. `mind status` shows
remaining/retry work; acceptance into the event store is not extraction completion.
No worker starts on import or MCP connection. Existing examples use synthetic
data; the Stage 6 example's vectors are labeled mechanics fixtures, not live models.

Only explicit semantic/hybrid retrieval uses a configured local embedding model.
The model must already be installed and compatible. OOMP never pulls weights;
missing semantic infrastructure is an error or an explicitly requested hybrid
degradation. [Retrieval options](retrieval.md), [MCP setup](mcp-integration.md).

## Installed distributions and other platforms

For reviewed local builds, install `dist/oomp_memory-0.1.0-py3-none-any.whl` or
`dist/oomp_memory-0.1.0.tar.gz` with `python -m pip install PATH`. Do not assume
`pip install oomp-memory` is available from PyPI. The name check during Stage 10
found no project at the official JSON/simple endpoints; that does not reserve a
name or guarantee that PyPI will permit registration.

On a POSIX shell the equivalent environment commands use `python3.11 -m venv
.venv` and `.venv/bin/python`. The configured CI targets Windows/Linux 3.11/3.12;
local validation status is in [Stage 10 validation](stage10-validation.md).
Linux commands/matrix must not be described as passed before execution. Current
local acceptance is on Windows; no Linux runtime is installed on this desktop.

Use [backup/retention guidance](privacy-retention.md) before storing important
data. [Troubleshooting](troubleshooting.md) covers FTS, paths, SDK and empty recall.
