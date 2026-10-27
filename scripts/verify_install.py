"""Run with a clean installed environment (prefer python -I), outside source imports.

Checks actual entry points and the installed package, not a source-tree substitute.
The caller chooses an output directory for disposable synthetic evidence.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


def verify(output: Path, expect_core_only: bool = False):
    import oomp
    output.mkdir(parents=True, exist_ok=False)
    package_path = Path(oomp.__file__).resolve()
    assert package_path.is_relative_to(Path(sys.prefix).resolve()), "package was not imported from the isolated installation"
    assert importlib.metadata.version("oomp-memory") == oomp.__version__ == "0.1.0"
    if expect_core_only:
        assert importlib.util.find_spec("mcp") is None and importlib.util.find_spec("backend") is None
    executable = Path(sys.executable).parent / ("oomp.exe" if os.name == "nt" else "oomp")
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment["OOMP_DB_PATH"] = str(output / "must-not-be-created.sqlite3")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    commands = [["--help"], ["--version"], ["doctor"], ["storage", "--help"], ["memory", "--help"],
        ["retrieve", "--help"], ["mind", "--help"], ["mcp", "--help"]]
    checks = []
    for arguments in commands:
        result = subprocess.run([str(executable), *arguments], cwd=output, env=environment,
            text=True, capture_output=True, timeout=30)
        assert result.returncode == 0, "installed CLI contract failed: " + " ".join(arguments)
        checks.append({"arguments": arguments, "exit_code": result.returncode})
    assert not (output / "must-not-be-created.sqlite3").exists()
    from datetime import datetime, timezone
    from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
    from oomp.ingestion import ExtractionPipeline
    from oomp.retrieval.contracts import RetrievalRequest
    from oomp.retrieval.engine import RetrievalEngine
    from oomp.storage import SQLiteEventStore
    scope = AuthorizedScope(tenant_id="release-synthetic", namespace="test", principal_id="local-verifier")
    when = datetime(2026, 1, 1, tzinfo=timezone.utc)
    event = MemoryEvent(event_id="installed-wheel-event", tenant_id=scope.tenant_id, namespace=scope.namespace,
        event_type="user_message", source_type="user", content="I am developing a project called InstalledDemo.",
        occurred_at=when, ingested_at=when, source_reference=SourceReference(source_system="release-check",
            external_event_id="installed-wheel-event", timestamp=when))
    path = output / "synthetic.sqlite3"
    store = SQLiteEventStore(path); assert store.initialize() == 5
    store.append(scope, event); ExtractionPipeline(path).process_event(scope, event.event_id)
    engine = RetrievalEngine(path); engine.index(scope)
    response = engine.retrieve(scope, RetrievalRequest(tenant_id=scope.tenant_id, namespace=scope.namespace, query="project developing"))
    assert response.memories and response.memories[0].source_event_ids == (event.event_id,)
    assert response.memories[0].source_references == (event.source_reference,)
    assert response.estimated_token_count == len(response.context_packet.encode()) <= response.token_budget
    assert SQLiteEventStore(path).get(scope, event.event_id) == event
    report = {"version": oomp.__version__, "python": sys.version.split()[0], "installed_from_site_packages": True,
        "core_only": expect_core_only, "cli_checks": checks, "schema": 5,
        "synthetic_flow": "persisted/extracted/indexed/retrieved/reopened", "TRACE_required": False,
        "MCP_installed": importlib.util.find_spec("mcp") is not None, "model_calls": 0}
    (output / "installation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--core-only", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(verify(args.output, args.core_only), indent=2))


if __name__ == "__main__":
    main()
