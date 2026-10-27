# OOMP — Object-Oriented Context Map

OOMP is a local research memory library for AI applications. It persists source
events, derives attributed canonical memories, maintains temporal relationships
and returns bounded evidence with original provenance. An application can recall
an older project fact after it leaves its recent conversation window, while
retaining changed and disputed claims for inspection.

OOMP returns **evidence, not an answer**. It does not enlarge a model's context
window, verify that a user's assertion is true or guarantee protection against
prompt injection. Version **0.1.0** is an **alpha research release candidate**,
licensed under [Apache-2.0](https://github.com/hamzah105/OOMP/blob/main/LICENSE). Publication is a maintainer decision; this
repository does not claim a reserved or published PyPI name.

## Implemented today

- SQLite v5 source history, scoped idempotency and additive migrations.
- Conservative offline extraction, canonical identity and explicit project aliases.
- Source-backed temporal graph/topics and narrow governed RAM conflict/supersession policy.
- FTS5/BM25 retrieval, optional local Ollama vectors, rank fusion and bounded evidence packing.
- Explicit durable Mind workers, restart-safe jobs, extractive projections and privileged local erasure.
- Optional official-SDK MCP over stdio or authenticated loopback HTTP; writes require separate host approval.
- Independent [TRACE integration](https://github.com/hamzah105/trace-ai-chatbot) and reproducible synthetic benchmarks.

Core operation needs Python 3.11+, SQLite with FTS5 and Pydantic. It needs no
TRACE, MongoDB, model, GPU, API key or network service. Models and MCP are optional.
See [limitations](https://github.com/hamzah105/OOMP/blob/main/docs/limitations.md) before using private or important data.

## Install from source and try it

From PowerShell, with Git and Python installed:

These clone instructions target the reviewed candidate after the maintainer pushes
it. Until then, use the current local checkout or unpacked source archive; remote
main does not acquire uncommitted release files automatically.

~~~powershell
git clone https://github.com/hamzah105/OOMP.git
cd OOMP
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade "pip>=26.2.2,<27"
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\oomp.exe --version
.\.venv\Scripts\oomp.exe doctor
.\.venv\Scripts\python.exe examples/quickstart.py --db data/quickstart.sqlite3
.\.venv\Scripts\oomp.exe retrieve "What project am I developing?" --tenant synthetic-quickstart --namespace demo --db data/quickstart.sqlite3 --token-budget 3000 --show-content --json
~~~

The quickstart requires a **new disposable path**. It stores a fictional project,
extracts/indexes its canonical memory, appends twelve unrelated observations and
retrieves the early fact with its actual source reference after reopening SQLite.
Omitting `--db` uses a temporary database. Scope strings here are local
administrator intent, not remote authentication. `--show-content` deliberately
reveals synthetic evidence; ordinary CLI inspection hides content by default.

[Getting started](https://github.com/hamzah105/OOMP/blob/main/docs/getting-started.md) explains the Python API, explicit
database initialization and optional installation. The wheel contains the runtime
package; the source archive also contains docs, tests, examples and benchmarks.

## Background work and MCP

Workers start only when explicitly invoked. A bounded offline demonstration uses
a separate synthetic database:

~~~powershell
.\.venv\Scripts\python.exe examples/stage6_background_mind.py --db data/mind-demo.sqlite3
.\.venv\Scripts\oomp.exe mind status --db data/mind-demo.sqlite3 --tenant synthetic-demo --namespace stage6
.\.venv\Scripts\python.exe -m pip install ".[mcp]"
.\.venv\Scripts\python.exe examples/stage7_mcp_client.py --transport stdio
.\.venv\Scripts\python.exe examples/stage7_mcp_client.py --transport streamable-http
~~~

The MCP examples use the official SDK Client and disposable storage/listeners.
They need no Ollama or TRACE and do not expose a public server. Follow
[MCP configuration and tools](https://github.com/hamzah105/OOMP/blob/main/docs/mcp-integration.md) for explicit scope, origin,
credential provisioning, read-only grants and separately signed ingestion.
Compatibility with every desktop host is not claimed.

## Reproduce the research

Run from a checkout or extracted source archive:

~~~powershell
.\.venv\Scripts\python.exe -m pip install ".[dev,mcp]"
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m benchmarks.runner --action plan --config benchmarks/configs/offline.json
.\.venv\Scripts\python.exe -m benchmarks.runner --config benchmarks/configs/offline.json --output benchmarks/results/my-smoke
.\.venv\Scripts\python.exe -m benchmarks.runner --action validate --run benchmarks/results/my-smoke
~~~

Every result path must be new. Default experiments are offline; real embeddings
and generated answers require separate explicit opt-in. No model is downloaded.
See [benchmark reproduction](https://github.com/hamzah105/OOMP/blob/main/docs/benchmark-reproduction.md) for frozen seeds,
baselines, source-level scoring, costs, uncertainty and failure accounting.

Stage 9's selected synthetic held-out comparison measured Recall@8 of **0.9286**
for OOMP, **0.7857** for flat lexical and **0.2381** for latest-eight memory on
112 positive queries. Recent-fact controls tied, neighborhood expansion gave no
measured recall/path gain, and curated temporal inputs limit generalization. In a
small real embedding sample, flat vectors and hybrid OOMP both recovered four
positive cases and both returned evidence on all four unanswerable cases.
**Live LLaMA answer-quality evaluation was not executed.** These are internal
retrieval observations, not universal superiority or final-answer accuracy.
[Original results and uncertainty](https://github.com/hamzah105/OOMP/blob/main/docs/stage9-validation.md),
[reviewed JSON](https://github.com/hamzah105/OOMP/blob/main/docs/examples/stage9-results.json).

## Guides and project status

| Task | Guide |
| --- | --- |
| First use / examples | [Getting started](https://github.com/hamzah105/OOMP/blob/main/docs/getting-started.md) |
| Public interfaces and compatibility | [API reference](https://github.com/hamzah105/OOMP/blob/main/docs/api-reference.md) |
| Development / providers / migrations | [Developer guide](https://github.com/hamzah105/OOMP/blob/main/docs/developer-guide.md), [Contributing](https://github.com/hamzah105/OOMP/blob/main/CONTRIBUTING.md) |
| Storage and backup / erasure | [Privacy and retention](https://github.com/hamzah105/OOMP/blob/main/docs/privacy-retention.md) |
| Trust boundaries | [Security model](https://github.com/hamzah105/OOMP/blob/main/docs/security-model.md), [Report a vulnerability](https://github.com/hamzah105/OOMP/blob/main/SECURITY.md) |
| Troubleshooting | [Troubleshooting](https://github.com/hamzah105/OOMP/blob/main/docs/troubleshooting.md) |
| Research design / manuscript | [Research plan](https://github.com/hamzah105/OOMP/blob/main/docs/research-plan.md), [Paper draft](https://github.com/hamzah105/OOMP/blob/main/docs/research-paper-draft.md) |
| Release evidence and pending gates | [Release checklist](https://github.com/hamzah105/OOMP/blob/main/docs/release-checklist.md), [Stage 10 validation](https://github.com/hamzah105/OOMP/blob/main/docs/stage10-validation.md) |
| Milestone history | [Roadmap](https://github.com/hamzah105/OOMP/blob/main/docs/roadmap.md), [Changelog](https://github.com/hamzah105/OOMP/blob/main/CHANGELOG.md) |

Default deployment is local-first, with plaintext SQLite protected by host file
permissions. SQLite is not a distributed database; public/proxy/cloud MCP hosting
needs further security engineering. A budget counts selected evidence and does
not certify a larger context window. [Stage 10's report](https://github.com/hamzah105/OOMP/blob/main/docs/stage-10-report.md)
separates local acceptance from configured-but-unexecuted GitHub CI and pending
human publication decisions. No release/push/upload is automatic.
