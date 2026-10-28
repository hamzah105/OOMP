"""P1 actual installed CLI/MCP/Mind acceptance, entirely in NEW synthetic storage.

    python examples/product_quickstart.py
    python examples/product_quickstart.py --directory NEW_DISPOSABLE_DIRECTORY

No TRACE, model, user profile, private database or preexisting service is used.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time


def run(directory: Path):
    from oomp.product.profiles import ProfileStore
    from oomp.product.protocol import call
    from oomp.product.lifecycle import stop, port_available
    from oomp.mcp.contracts import IngestPayload
    from oomp.mcp.authorization import approve_ingestion
    directory = directory.absolute()
    directory.mkdir(parents=True, exist_ok=False)
    home = directory/"synthetic profiles"
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", 0))
        port = connection.getsockname()[1]
    checks = []
    def cli(*arguments):
        result = subprocess.run([sys.executable, "-I", "-m", "oomp", *arguments,
            "--profile", "synthetic", "--home", str(home), "--json"],
            text=True, capture_output=True, timeout=100, cwd=directory)
        checks.append({"command": arguments[0], "exit_code": result.returncode})
        if result.returncode != 0:
            raise RuntimeError("synthetic CLI acceptance failed: "+arguments[0])
        return json.loads(result.stdout)
    cli("onboard", "--yes", "--create-credentials", "--mode", "trusted-ingest", "--approve-ingest", "--port", str(port))
    store = ProfileStore(home)
    profile = store.load("synthetic")
    try:
        runtime = cli("up", "--background")
        if set(runtime["services"]) != {"mcp", "mind"}:
            raise RuntimeError("separate processes missing")
        environment = store.environment(profile)
        grant = profile.grants()[1]["user"]
        when = datetime.now(timezone.utc)
        payload = IngestPayload(event_id="p1-synthetic-source", idempotency_key="p1-synthetic-source",
            content="I am developing a project called ProductDemo.", occurred_at=when,
            source_reference={"source_system": "approved-host", "external_event_id": "p1-synthetic-source", "timestamp": when})
        proof = approve_ingestion(grant, payload, environment[grant.ingest_approval_key_env])
        receipt = call(profile, environment, "memory.ingest",
                       {**payload.model_dump(mode="json"), "approval": proof.model_dump(mode="json")}, role="user")
        if receipt["acceptance"] != "durably_stored":
            raise RuntimeError("source was not accepted durably")
        deadline = time.monotonic()+30
        while True:
            result = call(profile, environment, "memory.retrieve", {"query": "project developing", "token_budget": 3000})
            if result["memories"]:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("separate worker did not make evidence retrievable")
            time.sleep(.2)
        if result["memories"][0]["source_event_ids"] != [payload.event_id]:
            raise RuntimeError("original source proof was not preserved")
        diagnostic = cli("doctor", "--full")
        if not diagnostic["ok"]:
            raise RuntimeError("synthetic full diagnostics failed")
        cli("status")
        cli("restart", "--background")
        persisted = call(profile, environment, "memory.retrieve", {"query": "project developing", "token_budget": 3000})
        if persisted["memories"][0]["source_event_ids"] != [payload.event_id]:
            raise RuntimeError("restart changed durable source identity")
        cli("logs")
    finally:
        stop(store, "synthetic")
    if not port_available(port):
        raise RuntimeError("owned listener remained after shutdown")
    report = {"synthetic": True, "version": "0.1.0", "schema": 5, "CLI_checks": checks,
              "separate_processes": ["mcp", "mind"], "authenticated_signed_ingestion": True,
              "source_event_ids": ["p1-synthetic-source"], "restart_preserved_source": True,
              "diagnostics_ok": True, "owned_services_stopped": True, "model_calls": 0,
              "TRACE_required": False, "existing_private_storage_used": False}
    (directory/"acceptance.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args(argv)
    if args.directory:
        report = run(args.directory)
    else:
        with TemporaryDirectory(prefix="oomp-product-demo-") as temporary:
            report = run(Path(temporary)/"demo")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
