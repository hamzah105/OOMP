"""Reason-coded, non-mutating diagnostics; synthetic writes are isolated."""
from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timezone
import importlib.metadata
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import sys
from tempfile import TemporaryDirectory
import time

from oomp import __version__
from .safety import ProductError, private_permissions, safe_path

OUTCOMES = ("PASS", "WARN", "FAIL", "NOT TESTED")


def synthetic_probe():
    from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
    from oomp.storage import SQLiteEventStore
    from oomp.mind.worker import MindWorker
    from oomp.retrieval.engine import RetrievalEngine
    from oomp.retrieval.contracts import RetrievalRequest
    with TemporaryDirectory(prefix="oomp-diagnostic-") as directory:
        path = Path(directory)/"synthetic.sqlite3"
        scope = AuthorizedScope(tenant_id="p1-diagnostic", namespace="synthetic", principal_id="local-doctor")
        when = datetime.now(timezone.utc)
        event = MemoryEvent(event_id="p1-probe", tenant_id=scope.tenant_id, namespace=scope.namespace,
            event_type="user_message", source_type="user", content="I am developing a project called DiagnosticDemo.",
            occurred_at=when, ingested_at=when, source_reference=SourceReference(
                source_system="p1-diagnostic", external_event_id="p1-probe", timestamp=when))
        store = SQLiteEventStore(path)
        store.initialize()
        store.append(scope, event)
        worker = MindWorker(path, scope)
        for _ in range(4):
            work = worker.run_once(max_jobs=4)
            if work.failed or work.lost_lease:
                raise ProductError("synthetic_worker_failed")
        engine = RetrievalEngine(path)
        result = engine.retrieve(scope, RetrievalRequest(tenant_id=scope.tenant_id,
            namespace=scope.namespace, query="project developing", token_budget=3000))
        if (not result.memories or result.memories[0].source_event_ids != (event.event_id,)
                or result.memories[0].source_references != (event.source_reference,)
                or result.estimated_token_count > 3000):
            raise ProductError("synthetic_provenance_failed")
        return {"source_proofs": 1, "schema": 5, "model_calls": 0,
                "evidence_bytes": result.estimated_token_count, "budget_bytes": 3000}


def _stamp(database):
    result = []
    for name in (database, Path(str(database)+"-wal")):
        try:
            info = name.stat()
            result.append((info.st_ino, info.st_size, info.st_mtime_ns))
        except FileNotFoundError:
            result.append(None)
    return result


@contextmanager
def inspection_snapshot(database):
    """No SQLite connection with write-capable WAL/SHM access to the original.

    immutable mode intentionally ignores WAL, so an active/nonempty WAL is NOT
    inspected this way. Never pass a private DB to initialize(), even to repair.
    """
    database = safe_path(database)
    if not database.is_file():
        raise ProductError("database_missing")
    wal = safe_path(str(database)+"-wal")
    if wal.exists() and wal.stat().st_size:
        raise ProductError("wal_requires_live_status_or_offline_backup")
    if database.stat().st_size > 128*1024*1024:
        raise ProductError("offline_snapshot_size_bound")
    before = _stamp(database)
    deadline = time.monotonic()+3
    def progress(*_):
        if time.monotonic() > deadline:
            raise ProductError("offline_snapshot_time_bound")
    with TemporaryDirectory(prefix="oomp-inspection-") as directory:
        target = Path(directory)/"snapshot.sqlite3"
        with closing(sqlite3.connect(database.as_uri()+"?mode=ro&immutable=1", uri=True)) as source:
            with closing(sqlite3.connect(target)) as destination:
                source.backup(destination, pages=128, progress=progress)
        if before != _stamp(database):
            raise ProductError("database_changed_during_snapshot")
        yield target


def diagnose(store, name=None, *, full=False):
    from .safety import profile_name
    if name is not None:
        profile_name(name)
    checks = []
    def add(identity, outcome, code, recommendation="", details=None):
        checks.append({"id": identity, "outcome": outcome, "code": code,
                       "recommendation": recommendation, "details": details or {}})
    add("python", "PASS" if sys.version_info >= (3, 11) else "FAIL", "python_compatibility",
        details={"version": sys.version.split()[0]})
    add("platform", "PASS" if os.name in {"nt", "posix"} else "WARN", "local_platform_detected",
        details={"system": platform.system(), "support": "runtime checks; not cross-platform certification"})
    for package in ("oomp-memory", "pydantic", "mcp"):
        try:
            version = importlib.metadata.version(package)
            good = (version == __version__ if package == "oomp-memory" else
                    version.startswith("2.3.") if package == "mcp" else
                    (2, 9) <= tuple(int(n) for n in version.split(".")[:2]) < (3, 0))
            add("package."+package, "PASS" if good else "FAIL", "package_version_checked", details={"version": version})
        except importlib.metadata.PackageNotFoundError:
            add("package."+package, "NOT TESTED" if package == "mcp" and not full else "FAIL",
                "dependency_missing", 'Install the reviewed package with the [mcp] extra when serving MCP.')
    try:
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.execute("CREATE VIRTUAL TABLE probe USING fts5(body)")
        add("sqlite.fts5", "PASS", "fts5_executed", details={"version": sqlite3.sqlite_version})
    except sqlite3.Error:
        add("sqlite.fts5", "FAIL", "fts5_unavailable", "Use a Python SQLite build with FTS5.")
    profile = None
    if full or name is not None:
        try:
            profile = store.load(name or "local")
            add("profile", "PASS", "profile_valid")
            store.environment(profile)
            add("credentials", "PASS", "credential_references_present_and_distinct")
        except Exception:
            add("profile", "FAIL", "profile_or_credentials_invalid",
                "Run oomp config --profile NAME; incomplete setup requires onboard --resume. Values are not displayed.")
    if full and profile is not None:
        from .lifecycle import control, port_available, validate_publication, publication_uri
        directory = store.directory(profile.name)
        try:
            permission_ok = private_permissions(directory) and private_permissions(Path(profile.database))
            add("permissions", "PASS" if permission_ok else "FAIL", "private_profile_and_database_permissions",
                "Protect profile/data directories with OS access controls; do not expose plaintext backups.")
            free = shutil.disk_usage(Path(profile.database).parent).free
            add("disk", "PASS" if free >= 100*1024*1024 else "WARN", "free_space_checked", details={"free_bytes": free})
        except Exception:
            add("permissions", "FAIL", "path_or_permissions_unavailable", "Review the configured paths without changing a real database.")
        from oomp.storage import SQLiteEventStore
        from oomp.storage.mind_store import SQLiteMindStore
        from oomp.retrieval.engine import RetrievalEngine
        try:
            with inspection_snapshot(profile.database) as snapshot:
                status = SQLiteEventStore(snapshot).status()
                add("storage", "PASS" if status.ready else "FAIL", "schema_checked_without_migration",
                    "Explicitly back up and review any required migration; doctor never migrates.",
                    {"schema_version": status.schema_version})
                if status.ready:
                    queue = SQLiteMindStore(snapshot).status(profile.scope)
                    index = RetrievalEngine(snapshot).index_status(profile.scope)
                    add("index.offline", "PASS" if index.lexical_count == index.canonical_count and not index.lexical_stale else "WARN",
                        "offline_index_coverage", details={"canonical": index.canonical_count, "lexical": index.lexical_count,
                                                          "lexical_stale": index.lexical_stale})
                    add("queue.offline", "WARN" if queue["failed"] or queue["events_pending_extraction"] else "PASS",
                        "offline_queue_counts", details={k: queue[k] for k in ("failed", "queued", "events_pending_extraction",
                            "outbox_pending", "oldest_pending_age_seconds")})
        except ProductError as error:
            outcome = "FAIL" if error.code == "database_missing" else "NOT TESTED"
            add("storage", outcome, error.code, "Use live authenticated MCP status, or stop writers and inspect a consistent offline backup.")
        except Exception:
            add("storage", "FAIL", "storage_invalid_or_unsupported", "Review the path/schema; no repair was attempted.")
        try:
            runtime = control(store, profile.name)
        except Exception:
            runtime = {"state": "unverified", "ownership_verified": False, "services": {}}
            add("runtime.state", "FAIL", "invalid_runtime_state", "Review owned profile state; no PID is signalled.")
        owned = runtime.get("ownership_verified", False)
        healthy = owned and runtime["state"] == "running" and all(s["ready"] for s in runtime["services"].values())
        add("supervisor", "PASS" if healthy else "WARN", "owned_supervisor_checked",
            "Run oomp up --profile NAME, or inspect logs; stale PIDs do not authorize stopping processes.",
            {"state": runtime["state"], "ownership_verified": owned})
        mind = runtime.get("services", {}).get("mind", {})
        add("mind", "PASS" if mind.get("ready") else "WARN" if profile.mind else "NOT TESTED",
            "worker_heartbeat_checked" if profile.mind else "worker_not_selected",
            "Enable/start the configured Mind worker; durable intake is not extraction completion.",
            {"alive": bool(mind.get("alive")), "ready": bool(mind.get("ready")),
             "last_error_code": mind.get("last_error_code")})
        if profile.transport == "streamable-http":
            available = port_available(profile.port)
            add("port", "PASS" if owned or available else "WARN", "port_ownership_checked",
                "Choose another port; OOMP never stops an independently owned listener.",
                {"available": available, "owned_supervisor": owned})
            try:
                from .protocol import call
                result = call(profile, store.environment(profile))
                # Typed validation rejects foreign/corrupt response shapes before
                # copying any remote strings into diagnostics.
                from oomp.mcp.contracts import StatusResult
                typed = StatusResult.model_validate(result)
                if typed.read_only is not True or "ingest" in typed.capabilities:
                    raise ProductError("unexpected_read_grant_authority")
                add("mcp", "PASS", "authenticated_mcp_status_executed", details={"schema_version": typed.schema_version})
                index = typed.index
                add("index.live", "PASS" if index.canonical_count == index.lexical_count and not index.lexical_stale else "WARN",
                    "live_index_coverage", details=index.model_dump())
                add("queue.live", "WARN" if typed.jobs.failed or typed.jobs.events_pending_extraction else "PASS",
                    "live_queue_counts", details=typed.jobs.model_dump())
            except Exception:
                add("mcp", "FAIL", "mcp_handshake_or_authorization_failed",
                    "Start the profile, install [mcp], and check credential references/port ownership.")
        else:
            add("mcp", "NOT TESTED", "stdio_is_host_owned", "Run oomp connect from a compatible SDK host; up does not impersonate that host.")
        if profile.provider is None:
            add("provider", "NOT TESTED", "lexical_only_no_provider_selected")
        else:
            try:
                provider = profile.provider.construct_provider()
                provider.timeout_seconds = min(3, provider.timeout_seconds)
                vectors = provider.embed(["Synthetic OOMP diagnostic input."])
                if len(vectors) != 1 or len(vectors[0]) != profile.provider.dimension:
                    raise ValueError()
                add("provider", "PASS", "local_synthetic_embedding_dimension_checked", details={"dimension": len(vectors[0])})
            except Exception:
                add("provider", "WARN", "selected_provider_unavailable_or_incompatible",
                    "Start the independently operated provider and verify the selected model. No weights are downloaded.")
        if profile.adapter == "trace":
            from .discovery import discover
            try:
                matched = discover(profile.project)["kind"] == "trace"
                add("trace.layout", "PASS" if matched else "FAIL", "trace_adapter_layout_checked")
            except Exception:
                add("trace.layout", "FAIL", "trace_project_unavailable")
            add("trace.owner_auth", "NOT TESTED", "host_login_not_exercised",
                "Launch the independent host with oomp host, then authenticate its pinned owner. Profile syntax is not login verification.")
            if profile.publication:
                try:
                    validate_publication(profile)
                    publication_uri(profile)
                    state = runtime.get("services", {}).get("publication", {})
                    add("trace.publication", "PASS" if state.get("ready") else "WARN", "publication_process_checked",
                        "Set the explicit local Mongo environment reference and run the approved profile.",
                        {"alive": bool(state.get("alive")), "ready": bool(state.get("ready"))})
                except Exception:
                    add("trace.publication", "FAIL", "approved_host_code_changed_or_unavailable")
            else:
                add("trace.publication", "NOT TESTED", "publication_not_selected")
    if full:
        try:
            add("synthetic", "PASS", "isolated_worker_retrieval_provenance_executed", details=synthetic_probe())
        except Exception:
            add("synthetic", "FAIL", "isolated_synthetic_probe_failed", "Inspect the installed package and test suite; private storage was not used.")
    summary = {outcome: sum(c["outcome"] == outcome for c in checks) for outcome in OUTCOMES}
    return {"schema_version": 1, "oomp_version": __version__, "profile": name,
            "ok": summary["FAIL"] == 0, "summary": summary, "checks": checks}
