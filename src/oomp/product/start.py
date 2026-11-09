"""Guided managed startup with an explicit persistent local profile selection."""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import socket
import sys

from .models import Profile
from .profiles import ProfileStore, default_home
from .safety import ProductError, file_lock, private_directory, read_json, safe_path, write_json


def selection_path() -> Path:
    # The existing application directory may contain public files. Create our
    # own private child rather than changing its ACL or accepting broad access.
    return safe_path(default_home().parent / "startup" / "selection.json")


def _binding(store, profile):
    # Operational settings may change through config; owner/data/grant authority
    # must never silently rebind the saved default to another identity.
    fields = ("adapter", "project", "database", "owner_id", "tenant", "namespace",
              "principal", "mode", "read_source", "publication", "host_python", "approved_project")
    authority = {field: getattr(profile, field) for field in fields}
    return {"format_version": 1, "home": str(store.home), "profile": profile.name,
            "authority_sha256": hashlib.sha256(json.dumps(authority, sort_keys=True).encode()).hexdigest()}


def remember(store, profile, *, replace=False, path=None):
    """Pin an operator-selected profile; never modify the profile or credentials."""
    path = safe_path(path) if path is not None else selection_path()
    value = _binding(store, profile)
    private_directory(path.parent)
    with file_lock(path.with_name("start-selection.lock")):
        if path.exists():
            previous = read_json(path)
            if previous == value:
                return False
            if not replace:
                raise ProductError("start_selection_exists_explicit_replacement_required")
        write_json(path, value)
    return True


def resolve_selection(home=None, name=None, *, path=None, fallback=False):
    """Explicit selectors win; bare invocations use only the approved saved pin."""
    if home is not None or name is not None:
        return ProfileStore(home), name or "local"
    path = safe_path(path) if path is not None else selection_path()
    if not path.exists():
        if fallback:
            return ProfileStore(), "local"
        return None
    value = read_json(path)
    if (not isinstance(value, dict) or set(value) != {"format_version", "home", "profile", "authority_sha256"}
            or type(value["format_version"]) is not int or value["format_version"] != 1):
        raise ProductError("invalid_start_selection")
    store = ProfileStore(value["home"])
    profile = store.load(value["profile"])
    if _binding(store, profile) != value:
        raise ProductError("selected_profile_authority_changed")
    return store, profile.name


def _trace_project(value=None):
    from .discovery import discover
    if value:
        root = safe_path(value)
        if discover(root)["kind"] != "trace":
            raise ProductError("trace_adapter_unavailable")
        return root
    current = Path.cwd()
    # A few public project-layout candidates, never an unbounded disk search.
    candidates = (current, current / "TRACE", current.parent / "TRACE",
                  current.parent / "VU BS-CS" / "CS619" / "TRACE")
    for candidate in candidates:
        try:
            if candidate.is_dir() and discover(candidate)["kind"] == "trace":
                return safe_path(candidate)
        except ProductError:
            continue
    return None


def _new_port():
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", 0))
        return connection.getsockname()[1]


def wizard(args, store, ui):
    """Create only an explicitly approved fresh single-owner TRACE profile."""
    from .discovery import project_fingerprint
    from .handoff import inspect_trace, validate_trace_owner
    from oomp.understanding.contracts import ExtractionConfiguration

    ui.welcome()
    ui.line("PASS", "Python environment detected: " + sys.version.split()[0])
    project = _trace_project(args.project)
    if project is None:
        project = _trace_project(ui.text("TRACE project directory"))
    ui.line("PASS", "TRACE project detected.")
    inspection = inspect_trace(project)
    if not inspection.get("mongo_configured"):
        raise ProductError("trace_mongo_configuration_missing")
    ui.line("PASS", "MongoDB configuration detected; no conversation records read.")
    if not ui.confirm("Connect OOMP with this TRACE project?"):
        raise ProductError("cancelled_no_changes")
    name = args.profile or "trace"
    if (store.directory(name) / "active.json").exists():
        raise ProductError("profile_exists_choose_it_explicitly")
    owner = ui.text("TRACE user ID (the selected user record will be validated)")
    if not validate_trace_owner(project, inspection["python"], owner):
        raise ProductError("trace_owner_not_found")
    authority = ui.choose("Memory integration", ("Read-only", "Read + approved conversation publication"), "Read-only")
    publication = authority == "Read + approved conversation publication"
    context = ui.confirm("Enable advanced context retrieval?")
    if publication and not ui.confirm("Approve the separate publication worker for this selected TRACE project?"):
        raise ProductError("cancelled_no_changes")
    profile = Profile(name=name, adapter="trace", project=str(project),
        database=str(store.directory(name) / "memory.sqlite3"), owner_id=owner,
        tenant="local-" + name, namespace="dedicated", principal="trace-owner",
        mode="trusted-ingest" if publication else "read-only", port=_new_port(),
        mind=True, extraction=ExtractionConfiguration(mode="rules"), context_enabled=context,
        publication=publication, host_python=inspection["python"] if publication else None,
        approved_project=project_fingerprint(project) if publication else {},
        mongo_database=inspection["mongo_database"] if publication else None,
        mongo_uri_env=inspection["mongo_uri_env"] if publication else None)
    ui.preview({**store.preview(profile), "owner_record_validated": True,
                "single_owner": True, "real_model_selected": False})
    if not ui.confirm("Create this isolated profile and separate secure credentials?"):
        raise ProductError("cancelled_no_changes")
    store.create(profile, create_credentials=True)
    return profile


def probe_runtime(profile, environment):
    """A fresh authenticated official-SDK check; no recall or source-content query."""
    from .protocol import session
    async def operation():
        async with session(profile, environment, timeout=4) as client:
            result = await client.call_tool("memory.status", {})
            if result.is_error or not isinstance(result.structured_content, dict):
                raise ProductError("invalid_mcp_status")
            listing = await client.list_tools()
            return result.structured_content, {tool.name for tool in listing.tools}
    try:
        return asyncio.run(asyncio.wait_for(operation(), 6))
    except ProductError:
        raise
    except Exception:
        raise ProductError("mcp_handshake_or_authorization_failed") from None


def launch(store, profile, *, approve_trace=False, ui=None):
    from . import lifecycle
    from .handoff import ensure_connection, prepare_environment
    if profile.transport != "streamable-http":
        raise ProductError("start_requires_managed_http_use_up_for_stdio")
    integration = {"configured": False}
    if profile.adapter == "trace":
        integration = ensure_connection(store, profile, approve=approve_trace, interactive_ui=ui)
    current = lifecycle.control(store, profile.name)
    if current.get("state") == "running" and current.get("ownership_verified"):
        result = current
    else:
        with prepare_environment(store, profile):
            result = lifecycle.start(store, profile, background=True)
    expected = {"mcp"} | ({"mind"} if profile.mind else set()) | ({"publication"} if profile.publication else set())
    if (result.get("state") != "running" or not result.get("ownership_verified")
            or not expected.issubset(result.get("services", {}))
            or any(not service.get("ready") or service.get("last_error_code")
                   for service in result.get("services", {}).values())):
        raise ProductError("managed_services_not_ready")
    status, tools = probe_runtime(profile, store.environment(profile))
    from oomp.storage.migrations import SCHEMA_VERSION
    if status.get("schema_version") != SCHEMA_VERSION:
        raise ProductError("database_schema_not_ready")
    context = profile.context_enabled is True and "memory.context" in tools
    if profile.context_enabled is True and not context:
        raise ProductError("configured_context_tool_unavailable")
    return {**result, "home": str(store.home), "integration": integration,
            "context_verified": context, "database_ready": True, "mcp_verified": True,
            "retrieval_api": "context_v1" if context else "retrieve"}


def command(args, ui):
    interactive = sys.stdin.isatty() and not args.json
    resolved = resolve_selection(args.home, args.profile)
    created = False
    if resolved is None:
        if not interactive:
            raise ProductError("setup_required_run_oomp_start_interactively")
        store = ProfileStore(args.home)
        profile = wizard(args, store, ui)
        created = True
    else:
        store, name = resolved
        try:
            profile = store.load(name)
        except ProductError as error:
            if error.code != "profile_missing" or not interactive:
                raise
            profile = wizard(args, store, ui)
            created = True
    if args.project and profile.project != str(safe_path(args.project)):
        raise ProductError("project_not_bound_to_selected_profile")
    if args.replace_default and not (created or args.remember):
        raise ProductError("replace_default_requires_remember")
    if created or args.remember:
        pin = selection_path()
        if pin.exists() and read_json(pin) != _binding(store, profile) and not args.replace_default:
            raise ProductError("start_selection_exists_explicit_replacement_required")
    result = launch(store, profile, approve_trace=args.approve_trace_integration,
                    ui=ui if interactive else None)
    if created or args.remember:
        remember(store, profile, replace=args.replace_default)
    if args.json:
        print(json.dumps(result))
    else:
        ui.welcome()
        if result.get("stale_runtime_recovered"):
            ui.line("WARN", "Previous OOMP supervisor exited without completing shutdown.")
            ui.line("PASS", "Stale runtime safely recovered.")
        ui.line("PASS", "OOMP Running")
        for role, label in (("mcp", "MCP Server"), ("mind", "Mind Worker"), ("publication", "TRACE Publisher")):
            item = result["services"].get(role)
            ui.line("PASS" if item and item.get("ready") else "NOT TESTED",
                    label + (" Connected" if role == "mcp" and item else " Running" if item else " Not selected"))
        ui.line("PASS", "Memory Retrieval " + ("Context V1" if result["context_verified"] else "Legacy retrieval"))
        ui.line("PASS", "Local Database Ready")
        ui.line("PASS" if result["integration"].get("configured") else "NOT TESTED", "TRACE Integration " +
                ("Configured" if result["integration"].get("configured") else "Not selected"))
        if profile.adapter == "trace":
            ui.line("", "Next: open the TRACE terminal and run: uvicorn backend.app:app --reload")
        selected = resolve_selection()
        default_matches = selected is not None and selected[0].home == store.home and selected[1] == profile.name
        ui.line("", "Stop owned services with: oomp stop" if default_matches else
                "Stop owned services using oomp stop with this same --home and --profile.")
    return 0
