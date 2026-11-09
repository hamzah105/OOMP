"""Managed, rules-only submission walkthrough in an explicitly NEW directory.

Uses five new fictional sources, signed MCP intake, a separate Mind worker,
object CLI inspection and context retrieval. No TRACE, MongoDB or model runs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

# Resolve the neighboring public example even with Python's isolated (-I) mode.
_host_spec = importlib.util.spec_from_file_location("submission_public_host", Path(__file__).with_name("generic_context_host.py"))
_host = importlib.util.module_from_spec(_host_spec)
_host_spec.loader.exec_module(_host)
reference, validate_context, validate_source = _host.reference, _host.validate_context, _host.validate_source


SOURCES = (
    ("submission-project", "S0", "I am developing a project called LUMENDEMO."),
    ("submission-alias", "S0", "I use Cedar Finch as my personal alias."),
    ("submission-style", "S0", "Please keep your replies concise and use numbered steps when a list is useful."),
    ("submission-proposal", "S1", "I may relocate from Alder Bay to Pine Harbor. I have not moved."),
    ("submission-cancellation", "S1", "Correction: I cancelled the relocation and decided not to move to Pine Harbor. I still live in Alder Bay."),
)
QUERIES = (
    ("project", "What project did I mention earlier?", {"submission-project"}),
    ("alias", "Which personal alias did I state?", {"submission-alias"}),
    ("style", "How did I ask for answers to be formatted?", {"submission-style"}),
    ("relocation", "What happened to my relocation plan?", {"submission-proposal", "submission-cancellation"}),
    ("unknown-pet", "What is my pet's name?", set()),
)


class DemoError(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise DemoError(code)


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, ensure_ascii=True, indent=2)
        output.write("\n")


def run(directory):
    from oomp.mcp.authorization import approve_ingestion
    from oomp.mcp.contracts import IngestPayload
    from oomp.product.lifecycle import port_available, stop
    from oomp.product.profiles import ProfileStore
    from oomp.product.protocol import call
    from oomp.storage.migrations import SCHEMA_VERSION

    directory = Path(directory).resolve()
    require(directory.parent.is_dir(), "new_directory_parent_required")
    directory.mkdir(exist_ok=False)
    home, checks = directory / "p", []
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    def record(name, **values):
        entry = {"step": name, **values}
        checks.append(entry)
        with (directory / "progress.jsonl").open("a", encoding="utf-8") as output:
            output.write(json.dumps(entry, ensure_ascii=True) + "\n")

    def command(arguments, name, *, environment=None):
        completed = subprocess.run([sys.executable, "-I", "-m", "oomp", *arguments], cwd=directory,
            env=environment, text=True, capture_output=True, timeout=100,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        record(name, exit_code=completed.returncode)
        require(completed.returncode == 0, "managed_cli_step_failed")
        result = json.loads(completed.stdout)
        write_json(directory / (name + ".json"), result)
        return result

    def managed(operation, *arguments, name=None, environment=None):
        return command([operation, "--profile", "submission", "--home", str(home), "--json", *arguments],
                       name or operation, environment=environment)

    project = Path(__file__).resolve().parents[1]
    setup = ("--adapter", "generic-mcp", "--project", str(project), "--mode", "trusted-ingest",
             "--approve-ingest", "--tenant", "submission-fictional", "--namespace", "dedicated",
             "--principal", "fictional-owner", "--port", str(port), "--context",
             "--mind", "--extraction-mode", "rules", "--no-provider")
    managed("onboard", *setup, "--dry-run", name="onboard-preview")
    managed("onboard", *setup, "--yes", "--create-credentials")
    store = ProfileStore(home)
    profile = store.load("submission")
    require(profile.context_enabled is True and profile.extraction.mode == "rules"
            and profile.provider is None and not profile.read_source, "rules_only_profile_required")
    grants = profile.server().http_grants
    require({grant.principal_id for grant in grants} == {profile.principal}
            and {grant.namespace for grant in grants} == {profile.namespace}, "single_principal_namespace_required")
    originals, queries, checked_sources = {}, [], set()
    try:
        runtime = managed("up", "--background")
        require(set(runtime["services"]) == {"mcp", "mind"}
                and all(item["ready"] for item in runtime["services"].values()), "separate_services_not_ready")
        environment = store.environment(profile)
        writer = profile.grants()[1]["user"]
        base = datetime.now(timezone.utc) - timedelta(days=2)
        for index, (event_id, session, content) in enumerate(SOURCES):
            when = base + timedelta(days=1 if session == "S1" else 0, minutes=index)
            payload = IngestPayload(event_id=event_id, idempotency_key=event_id, content=content, occurred_at=when,
                source_reference={"source_system": "approved-host", "external_event_id": event_id,
                    "session_id": "submission-" + session, "turn_id": "turn-" + event_id, "timestamp": when})
            approval = approve_ingestion(writer, payload, environment[writer.ingest_approval_key_env])
            receipt = call(profile, environment, "memory.ingest", {
                **payload.model_dump(mode="json"), "approval": approval.model_dump(mode="json")}, role="user")
            require(receipt.get("acceptance") == "durably_stored", "signed_source_not_durable")
            originals[event_id] = payload.model_dump(mode="json")
        # Save only authored fictional originals, never approval signatures or credentials.
        write_json(directory / "fictional-sources.json", list(originals.values()))
        record("signed-intake", accepted=len(originals))
        deadline = time.monotonic() + 40
        while True:
            readiness = call(profile, environment, "memory.status")
            jobs = readiness["jobs"]
            require(not jobs["failed"], "mind_job_failed")
            if not any(jobs[key] for key in ("queued", "running", "retry_wait", "outbox_pending", "events_pending_extraction")):
                break
            require(time.monotonic() < deadline, "mind_readiness_deadline")
            time.sleep(.25)
        write_json(directory / "memory-ready.json", readiness)
        record("mind-drained", model_provider_selected=False)

        scope = ["--db", profile.database, "--tenant", profile.tenant, "--namespace", profile.namespace,
                 "--principal", profile.principal, "--json"]
        built = command(["memory", "build-map", *scope, "--limit", "100"], "object-build")
        require(not built["incomplete"], "object_build_incomplete")
        tree = command(["memory", "tree", *scope, "--limit", "100", "--depth", "10"], "object-tree")
        require(not tree["truncated"], "object_tree_truncated")
        found = command(["memory", "find", "LUMENDEMO", *scope], "object-find-project")
        require(len(found["objects"]) == 1 and not found["truncated"], "project_object_missing")
        project_id = found["objects"][0]["object_id"]
        inspected = command(["memory", "inspect", project_id, *scope, "--show-provenance"], "object-inspect-project")
        require("submission-project" in {proof["event_id"] for proof in inspected["object"]["source_proofs"]},
                "project_object_proof_missing")

        def query(name, question, expected, *, budget=6000):
            data = call(profile, environment, "memory.context", {
                "query": question, "token_budget": budget, "max_results": 8,
                "include_source_content": False, "graph_depth": 0,
            }, timeout=8)
            write_json(directory / ("context-" + name + ".json"), data)
            proofs = validate_context(data, budget, 8)
            event_ids = {proof["event_id"] for proof in proofs}
            if expected is not None:
                require(event_ids == expected, "query_original_sources_disagree")
            supports = []
            for proof in proofs:
                original = originals.get(proof["event_id"])
                require(original is not None and reference(original["source_reference"]) == proof["source_reference"],
                        "original_source_identity_mismatch")
                start, end = proof["span_start"], proof["span_end"]
                require(0 <= start < end <= len(original["content"]), "original_source_span_invalid")
                supports.append({"memory_id": proof["memory_id"], "event_id": proof["event_id"],
                    "span_start": start, "span_end": end, "source_session": proof["source_reference"]["session_id"],
                    "original_span_sha256": hashlib.sha256(original["content"][start:end].encode("utf-8")).hexdigest()})
                identity = (proof["memory_id"], proof["event_id"])
                if identity not in checked_sources:
                    linked = call(profile, environment, "memory.get_source", {
                        "memory_id": identity[0], "event_id": identity[1], "include_content": False, "limit": 1})
                    validate_source(linked, proof)
                    require(linked["sources"][0]["source_type"] == "user"
                            and linked["sources"][0]["event_type"] == "user_message", "original_source_role_mismatch")
                    checked_sources.add(identity)
            if expected == set():
                require(data["retrieval_status"] in {"no_relevant_evidence", "candidate_uncertain"}, "unsupported_pet_claim")
            if name == "relocation":
                require(data["retrieval_status"] == "candidate_uncertain"
                        and any(unit["uncertain"] or unit["temporal_status"] in {"tentative", "correction_pending"}
                                for unit in data["evidence_packets"]), "relocation_uncertainty_lost")
            result = {"query_id": name, "query": question, "request_session": "S2", "status": data["retrieval_status"],
                      "source_event_ids": sorted(event_ids), "source_proofs": supports,
                      "packet_bytes": data["selected_context_bytes"], "token_budget": data["token_budget"],
                      "coverage": data["coverage"], "reasons": data["reasons"]}
            queries.append(result)
            record("context-" + name, status=data["retrieval_status"], packet_bytes=data["selected_context_bytes"])
            return result

        for name, question, expected in QUERIES:
            query(name, question, expected)
        long_query = " ".join(["Please recap the project, my alias, reply preference and relocation correction."] * 32)
        limited = query("small-budget", long_query, None, budget=96)
        require(limited["status"] in {"budget_excluded", "candidate_uncertain", "coverage_unknown", "index_incomplete"}
                and limited["packet_bytes"] == 0, "bounded_query_must_report_exclusion_or_uncertainty")

        host_environment = {**os.environ, "MCP_ENDPOINT": profile.server().endpoint}
        independent = managed("host", "--approve-host", "--", sys.executable, "-B",
            str(Path(__file__).with_name("generic_context_host.py")), QUERIES[0][1], "--get-source",
            "--token-env", profile.reference("read_token"), name="independent-host", environment=host_environment)
        require(independent["source_proofs"] > 0 and independent["linked_source_checked"], "independent_host_proof_missing")
        diagnostics = managed("doctor", "--full")
        require(diagnostics["ok"], "full_diagnostics_failed")
        managed("status", name="status-before-restart")
        managed("restart", "--background")
        reopened = query("project-after-restart", QUERIES[0][1], QUERIES[0][2])
        require(reopened["source_proofs"] == queries[0]["source_proofs"], "restart_changed_source_proofs")
        managed("status", name="status-after-restart")
    finally:
        try:
            managed("down")
        except Exception:
            stop(store, profile.name)
            raise
    require(port_available(port), "owned_listener_remained_after_shutdown")
    report = {"result": "pass", "fictional": True, "schema_version": SCHEMA_VERSION,
              "directory": str(directory), "profile_home": str(home), "profile": profile.name,
              "database": profile.database, "mcp_endpoint": profile.server().endpoint,
              "scope": {"tenant": profile.tenant, "namespace": profile.namespace, "principal": profile.principal},
              "project_object_id": project_id, "source_sessions": ["S0", "S1"], "query_session": "S2",
              "session_meaning": "Original source references S0/S1; fresh SDK requests labeled S2 in this demo ledger only.",
              "source_events": len(originals), "signed_intake": True, "separate_processes": ["mcp", "mind"],
              "queries": queries, "linked_source_metadata_checks": len(checked_sources),
              "independent_sdk_host": independent, "diagnostics_ok": diagnostics["ok"],
              "restart_preserved_original_proofs": True, "owned_services_stopped": True,
              "model_calls": 0, "embedding_provider_selected": False, "extraction_mode": "rules",
              "TRACE_started": False, "existing_private_storage_used": False, "steps": checks,
              "limitations": "Fictional retrieval/provenance and bounded accounting only; no real chatbot answer or long model conversation."}
    write_json(directory / "acceptance.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path, help="NEW short disposable directory; parent must exist")
    args = parser.parse_args(argv)
    try:
        report = run(args.directory)
    except Exception as error:
        code = str(error) if isinstance(error, DemoError) else "submission_demo_failed"
        print(json.dumps({"result": "failed", "code": code, "error_type": type(error).__name__}), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
