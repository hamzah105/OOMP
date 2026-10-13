# Stage 1 validation

Validation date: 2026-10-13 (Asia/Karachi). Workspace: `D:\Desktop\OOMP`. Initial inspection found an empty directory, no ancestor Git repository and no project instructions or existing license. Git was initialized locally; no remote, commit or push was created. No TRACE checkout or file was accessed or modified.

## Runtime and dependencies

The available launcher `py -3.11` runs Python 3.11.4. The bare `python` command resolved to a nonworking system command before environment activation. All actual validation used `.venv\Scripts\python.exe` or `.venv\Scripts\oomp.exe`.

Before constraint selection, the global installation reported Pydantic 2.9.2, pytest 8.3.3, setuptools 65.5.0 and no wheel. Those global packages were left unchanged. A clean workspace `.venv` was created and now contains:

| Package | Installed version | Purpose |
| --- | --- | --- |
| oomp-memory | 0.1.0 | Editable local package |
| pydantic | 2.14.1 | Runtime validated contracts |
| pytest | 9.1.1 | Development tests |
| setuptools | 84.0.0 | Packaging backend |
| wheel | 0.48.0 | Local wheel verification |

Pydantic/pytest transitive dependencies were installed by pip. SQLite adapters, model SDKs, Ollama, embedding libraries, vector databases and MCP were not installed in this environment. The build backend may use a temporary isolated build environment, kept under workspace `.tmp` for these checks.

## Executed checks

| Check | Result |
| --- | --- |
| `py -3.11 -m venv .venv` | Passed after sandbox-related ensurepip failure was rerun with approved execution |
| `.\.venv\Scripts\python.exe -m pip install --no-cache-dir -e '.[dev]'` | Passed after correcting a TOML UTF-8 BOM |
| `.\.venv\Scripts\oomp.exe --help` | Passed |
| `.\.venv\Scripts\oomp.exe --version` | Passed: `oomp 0.1.0` |
| `.\.venv\Scripts\oomp.exe doctor` | Passed: Python, distribution, Pydantic and domain/interface/retrieval imports ready |
| `.\.venv\Scripts\python.exe -m oomp --help` | Passed |
| `.\.venv\Scripts\python.exe -m pip check` | Passed: `No broken requirements found.` |
| Local wheel build, no dependency resolution/build isolation | Passed |
| TOML and installed package metadata | Passed |
| JSON schemas for all ten domain/retrieval contracts | Passed |
| Wheel source files, entry point, Apache license and Requires-Dist | Passed |
| Executing the memory-model supersession example | Passed |
| Source and test compilation | Passed: `python -m compileall -q src tests` |
| Full pytest suite | Passed: **79 passed in 1.92s**, no failures, skips or warnings |

The wheel is `.test-artifacts/wheels/oomp_memory-0.1.0-py3-none-any.whl`. Local verification artifacts, environments, bytecode and build outputs are ignored by Git. Packaging success is not a claim of publication or PyPI name ownership.

## Environmental issues and resolutions

- Sandbox process setup began failing with `helper_unknown_error: setup refresh had errors`, including permitted workspace writes. Approved escalated commands completed those actions inside OOMP; no global package or Git configuration was changed.
- Global dependency metadata initially required approved read access. Workspace environment bootstrapping initially failed under the sandbox and passed when rerun.
- Windows PowerShell's UTF-8 writer added a BOM to TOML. The first editable installation rejected it; package source/metadata and project docs were rewritten as UTF-8 without BOM and installation passed.
- Git's ownership check sees `.git` as owned by the managed sandbox account when commands run as the user. Read-only Git checks passed with a command-local `safe.directory` override. If manual Git inspection encounters the same warning, use the explicit inspected workspace for that one command:

```powershell
git -c "safe.directory=$PWD" status --short
git -c "safe.directory=$PWD" remote -v
```

No global `safe.directory` setting was added. Pip printed a newer-version notice for the venv's pip 23.1.2; upgrading pip was unnecessary for the checks that passed.

These checks demonstrate the Stage 1 contracts and local package foundation only. No storage, retrieval quality, tokenizer accuracy, LLM inference, MCP service, cross-tenant database enforcement or benchmark was tested or claimed.

Full suite command: `.\.venv\Scripts\python.exe -m pytest -v --basetemp .test-artifacts\pytest-tmp`. Exit code: 0. Full log: `.test-artifacts/pytest-stage1.txt`. Test definitions: `tests/test_stage1.py`. Stage 1 acceptance is complete; Stages 2–10 remain planned.
