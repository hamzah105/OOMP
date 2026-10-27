# Third-party materials and dependency scope

OOMP project source/examples/synthetic generator are distributed under
Apache-2.0; see LICENSE and NOTICE. The runtime wheel does not vendor dependency
source, SDK distributions, model weights, private conversations or proprietary
datasets. Installing dependencies obtains separately licensed distributions;
their own metadata/license files remain authoritative.

Inspected direct/SDK dependency metadata during local preparation:

| Distribution | Inspected version | Declared license metadata |
| --- | --- | --- |
| pydantic | 2.14.1 | MIT expression |
| mcp / mcp-types | 2.3.0 | MIT classifiers and LICENSE files |
| uvicorn | 0.54.0 | BSD-3-Clause expression |
| pytest (development) | 9.1.1 | MIT expression |

This is the resolved local inventory, not an assertion about every future version
allowed by a dependency range. No dependency implementation is embedded in the
OOMP wheel; validate licenses again if future packaging begins vendoring code.

The runtime depends on Pydantic; MCP/uvicorn are optional, and pytest is a
development dependency. Release tools (build, twine, pip-audit, PyYAML) are separate.
The exact resolved versions and their installed license metadata are recorded in
the Stage 10 dependency inventory/audit, not inferred from package names. Future
vendoring or redistribution must review those actual versions and preserve any
required notices. This file does not relicense dependencies as Apache-2.0.

SQLite comes from the Python/runtime distribution rather than bundled OOMP
database binaries. Optional Ollama models are independently installed by the
operator; their license, hardware and retention obligations are separate. OOMP
never downloads or distributes those weights. Research comparisons did not copy
Mem0, Zep or GraphRAG code or datasets into the package.

Documentation links to official APIs and verified primary research publications.
Examples exercise public APIs without bundling third-party implementation code.
The community conduct text is project-authored rather than an unattributed copy
of a separately licensed template. Human release review must confirm attribution
and contribution rights; no claim of an external legal certification is made.
