"""Additive product commands; no changes to existing manual CLI contracts."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from .profiles import ProfileStore
from .models import Profile
from .safety import ProductError, safe_path
from .ui import UI

COMMANDS = {"onboard", "config", "reconfigure", "up", "down", "restart", "status", "logs",
            "install", "uninstall-integration", "connect", "host"}


def configure(subparsers, doctor):
    for command in ("full", "json", "plain"):
        doctor.add_argument("--"+command, action="store_true")
    doctor.add_argument("--profile")
    doctor.add_argument("--home", help="profile root override; or OOMP_PROFILE_HOME")
    for name in sorted(COMMANDS):
        parser = subparsers.add_parser(name, help={
            "onboard": "preview and create an explicitly approved local profile",
            "config": "inspect or change profile operations settings",
            "reconfigure": "alias for config; does not rotate credentials",
            "up": "supervise owned services (foreground by default)",
            "down": "stop only an authenticated owning supervisor",
            "restart": "stop owned services and start the same profile",
            "status": "inspect authenticated supervisor ownership and service health",
            "logs": "show bounded safe operational codes",
            "install": "connect an installed OOMP package: preview/export a host template",
            "uninstall-integration": "preview/remove only unchanged owned template files",
            "connect": "run a host-owned MCP stdio server using a stored profile",
            "host": "run an explicitly supplied host command with private profile environment",
        }[name])
        parser.add_argument("--profile", default=None if name == "onboard" else "local")
        parser.add_argument("--home", help="profile root override; or OOMP_PROFILE_HOME")
        parser.add_argument("--plain", action="store_true")
        parser.add_argument("--json", action="store_true")
        if name in {"onboard", "config", "reconfigure", "install", "uninstall-integration"}:
            parser.add_argument("--dry-run", action="store_true")
            parser.add_argument("--yes", action="store_true", help="confirm the displayed plan; never implies grant or host-code approval")
        if name in {"onboard", "config", "reconfigure"}:
            parser.add_argument("--port", type=int)
            parser.add_argument("--transport", choices=("streamable-http", "stdio"))
            parser.add_argument("--mind", action=argparse.BooleanOptionalAction, default=None)
            parser.add_argument("--embedding-model")
            parser.add_argument("--embedding-dimension", type=int)
            parser.add_argument("--embedding-endpoint", default="http://127.0.0.1:11434")
            parser.add_argument("--no-provider", action="store_true")
        if name == "onboard":
            parser.add_argument("--project")
            parser.add_argument("--adapter", choices=("standalone", "generic-mcp", "trace"))
            parser.add_argument("--database", help="NEW database only; parent must already exist")
            parser.add_argument("--tenant")
            parser.add_argument("--namespace", default="personal")
            parser.add_argument("--principal", default="local-host")
            parser.add_argument("--mode", choices=("read-only", "trusted-ingest"), default=None)
            parser.add_argument("--approve-ingest", action="store_true")
            parser.add_argument("--read-source", action="store_true", help="explicitly permit linked original source text; disabled by default")
            parser.add_argument("--create-credentials", action="store_true")
            parser.add_argument("--secret-source", choices=("file", "environment"), default="file")
            parser.add_argument("--owner-id")
            parser.add_argument("--host-origin", default="http://127.0.0.1:8000")
            parser.add_argument("--publication", action="store_true")
            parser.add_argument("--approve-host", action="store_true")
            parser.add_argument("--host-python")
            parser.add_argument("--mongo-uri-env")
            parser.add_argument("--mongo-database")
            parser.add_argument("--resume", action="store_true", help="resume only this profile's previously claimed setup; never rotate secrets")
        if name in {"up", "restart"}:
            parser.add_argument("--background", action="store_true", help="explicitly detach the owning supervisor and wait for readiness")
        if name == "install":
            parser.add_argument("--project", required=True)
            parser.add_argument("--output", help="optional NEW reference-only host template; existing host configs are preserved")
        if name == "host":
            parser.add_argument("--approve-host", action="store_true", help="approve execution of the supplied argv and selected project code")
            parser.add_argument("host_argv", nargs=argparse.REMAINDER, help="operator-reviewed command after --; never discovered from project files")


def _provider(args, original=None):
    if args.no_provider:
        return None
    if args.embedding_model is not None or args.embedding_dimension is not None:
        from oomp.mcp.configuration import EmbeddingConfiguration
        if not args.embedding_model or args.embedding_dimension is None:
            raise ProductError("embedding_model_and_dimension_required")
        return EmbeddingConfiguration(model=args.embedding_model, dimension=args.embedding_dimension,
            endpoint=args.embedding_endpoint, version="ollama-api-embed-v1")
    return original


def _confirmed(args, ui):
    if args.dry_run:
        return False
    if args.yes:
        return True
    if not sys.stdin.isatty():
        raise ProductError("confirmation_required_use_yes_or_dry_run")
    if not ui.confirm("Apply exactly these changes?"):
        raise ProductError("cancelled_no_changes")
    return True


def _onboard(args, store, ui):
    from .discovery import discover, project_fingerprint
    if args.resume:
        name = args.profile or "local"
        ui.preview({"profile": name, "operation": "resume only previously claimed setup; never rotate secrets or adopt a foreign database"})
        if _confirmed(args, ui):
            store.resume(name)
            ui.line("PASS", "Profile setup resumed.")
        return 0
    inspection = discover(args.project)
    interactive = sys.stdin.isatty() and not args.yes and not args.dry_run
    if not args.json:
        ui.welcome()
        ui.preview({"discovery": inspection})
    name = args.profile or (ui.text("Profile name", "local") if interactive else "local")
    adapter = args.adapter or (inspection["kind"] if inspection["kind"] != "unknown" else None)
    if interactive:
        adapter = ui.choose("Connection type (generic templates do not certify arbitrary frameworks)",
                            ("standalone", "generic-mcp", "trace"), adapter or "standalone")
    if adapter is None:
        raise ProductError("unknown_project_choose_generic_or_standalone")
    if adapter == "trace" and inspection["kind"] != "trace":
        raise ProductError("trace_adapter_unavailable")
    mode = args.mode or (ui.choose("Memory authority", ("read-only", "trusted-ingest")) if interactive else "read-only")
    if mode == "trusted-ingest" and not (args.approve_ingest or interactive):
        raise ProductError("ingestion_approval_required")
    transport = args.transport or (ui.choose("Local transport", ("streamable-http", "stdio")) if interactive else "streamable-http")
    mind = args.mind if args.mind is not None else (ui.choose("Start bounded Mind worker with this profile?", ("Yes", "No")) == "Yes" if interactive else True)
    database = args.database or str(store.directory(name)/"memory.sqlite3")
    if interactive and not args.database:
        database = ui.text("New storage file (existing databases are refused)", database)
    tenant = args.tenant or (ui.text("Dedicated tenant", "local-"+name) if interactive else "local-"+name)
    namespace = ui.text("Namespace", args.namespace) if interactive else args.namespace
    principal = ui.text("Host principal", args.principal) if interactive else args.principal
    port = args.port
    if interactive and transport == "streamable-http" and port is None:
        port = int(ui.text("Literal-loopback MCP port", 8765))
    owner = args.owner_id
    if adapter == "trace" and interactive and not owner:
        owner = ui.text("Pinned authorized TRACE owner ID (not inferred from repository)")
    read_source = args.read_source
    if interactive:
        read_source = ui.confirm("Permit linked original source text? Optional; TRACE checks provenance against its own Mongo sources.")
    provider = _provider(args)
    if interactive and provider is None and not args.no_provider:
        if ui.choose("Embedding provider (no downloads)", ("Skip: lexical only", "Opt in to local Ollama")) != "Skip: lexical only":
            from oomp.mcp.configuration import EmbeddingConfiguration
            provider = EmbeddingConfiguration(model=ui.text("Already installed embedding model"),
                dimension=int(ui.text("Expected embedding dimension")), version="ollama-api-embed-v1")
    publication = args.publication
    if interactive and adapter == "trace":
        publication = ui.choose("Manage the approved TRACE publication worker?", ("No", "Yes")) == "Yes"
        if publication:
            ui.line("WARN", "This executes trusted host code and publishes only already approved owner rows to this profile.")
            args.approve_host = ui.confirm("Approve this project code for the fixed publication worker?")
            args.host_python = args.host_python or ui.text("Explicit host Python executable")
            args.mongo_uri_env = args.mongo_uri_env or ui.text("Environment reference for an explicit local Mongo URI", "OOMP_TRACE_MONGO_URI")
            args.mongo_database = args.mongo_database or ui.text("Explicit Mongo database name (not inferred)")
    if publication and not args.approve_host:
        raise ProductError("publication_approval_required")
    profile = Profile(name=name, adapter=adapter, project=str(safe_path(args.project)) if args.project and adapter != "standalone" else None,
        database=database, transport=transport, mode=mode, tenant=tenant, namespace=namespace,
        principal=principal, port=8765 if port is None else port, mind=mind, read_source=read_source, provider=provider,
        secret_source=args.secret_source, owner_id=owner if adapter == "trace" else None,
        host_origin=args.host_origin, publication=publication, host_python=args.host_python,
        approved_project=project_fingerprint(args.project) if publication else {},
        mongo_uri_env=args.mongo_uri_env, mongo_database=args.mongo_database)
    plan = {**store.preview(profile), "discovery": inspection,
            "event_policy": "no backfill; exact signed host-approved events only" if mode == "trusted-ingest" else "no ingestion grant"}
    if args.json and args.dry_run:
        print(json.dumps(plan))
        return 0
    if args.json:
        print(json.dumps({"plan": plan}), file=sys.stderr)
    else:
        ui.preview(plan)
    create = args.create_credentials
    if interactive and args.secret_source == "file" and not (store.directory(name)/"active.json").exists():
        create = ui.confirm("Create new random credentials in the private profile store? Existing values are never rotated.")
    if _confirmed(args, ui):
        changed = store.create(profile, create_credentials=create)
        if args.json:
            print(json.dumps({"profile": name, "created": changed, "services_started": False}))
        else:
            ui.line("PASS", "Profile created." if changed else "Profile unchanged; existing data and credentials preserved.")
            ui.line("", f"Next: oomp up --profile {name}; oomp doctor --full --profile {name}")
    return 0


def command(args):
    ui = UI(plain=args.plain)
    try:
        store = ProfileStore(args.home)
        if args.command == "onboard":
            return _onboard(args, store, ui)
        if args.command in {"down", "status", "logs"}:
            from .lifecycle import control, stop, logs
            result = logs(store, args.profile) if args.command == "logs" else stop(store, args.profile) if args.command == "down" else control(store, args.profile)
            if args.json or args.command == "logs":
                print(json.dumps(result))
            else:
                ui.runtime(result)
            failed = isinstance(result, dict) and (result.get("state") in {"failed", "unverified"}
                or result.get("state") == "running" and any(not s.get("ready") for s in result.get("services", {}).values()))
            return 1 if failed else 0
        profile = store.load(args.profile)
        if args.command in {"config", "reconfigure"}:
            changes = {key: getattr(args, key) for key in ("port", "mind", "transport") if getattr(args, key) is not None}
            provider = _provider(args, profile.provider)
            if provider != profile.provider:
                changes["provider"] = provider.model_dump(mode="json") if provider else None
            if not changes and sys.stdin.isatty() and not args.json and not args.dry_run:
                selected = ui.choose("Setting to change", ("Inspect only", "Port", "Mind worker"))
                if selected == "Port":
                    changes["port"] = int(ui.text("Loopback port", profile.port))
                elif selected == "Mind worker":
                    changes["mind"] = ui.choose("Mind worker", ("Enabled", "Disabled"), "Enabled" if profile.mind else "Disabled") == "Enabled"
            plan = {"profile": profile.name, "settings": {k: v for k,v in profile.model_dump(mode="json").items()
                        if k not in {"owner_id", "approved_project"}}, "proposed": changes,
                    "secret_references": [profile.reference(r) for r in profile.secret_roles()],
                    "credential_rotation": False}
            if args.json:
                print(json.dumps(plan))
            else:
                ui.preview(plan)
            if changes and _confirmed(args, ui):
                updated = Profile.model_validate({**profile.model_dump(mode="json"), **changes})
                store.update(updated)
                if not args.json:
                    ui.line("PASS", "Settings committed atomically; credentials and database preserved.")
            return 0
        if args.command in {"up", "restart"}:
            from .lifecycle import start, stop
            if args.json and not args.background:
                raise ProductError("json_up_requires_background")
            if args.command == "restart":
                stop(store, profile.name)
            if not args.json:
                ui.welcome()
                ui.line("", "Starting owned services; readiness requires an authenticated MCP check.")
            result = start(store, profile, background=args.background)
            if isinstance(result, int):
                return result
            print(json.dumps(result)) if args.json else ui.runtime(result)
            return 0
        if args.command == "connect":
            if profile.transport != "stdio":
                raise ProductError("connect_requires_stdio_profile")
            os.environ.update(store.environment(profile))
            from oomp.mcp.cli import _sdk_ready
            _sdk_ready()
            from oomp.mcp.server import serve
            serve(profile.server())
            return 0
        if args.command == "install":
            from .discovery import discover
            root = safe_path(args.project)
            inspection = discover(root)
            if profile.project != str(root):
                raise ProductError("project_not_bound_to_profile")
            plan = store.exported_template(profile, Path(args.output) if args.output else None)
            if args.json:
                print(json.dumps({**plan, "discovery": inspection}))
            else:
                ui.preview({**plan, "discovery": inspection})
            if args.output and _confirmed(args, ui):
                store.exported_template(profile, Path(args.output), apply=True)
            return 0
        if args.command == "uninstall-integration":
            plan = store.uninstall(profile.name)
            print(json.dumps(plan)) if args.json else ui.preview(plan)
            if _confirmed(args, ui):
                store.uninstall(profile.name, apply=True)
            return 0
        if args.command == "host":
            if not args.approve_host or not profile.project:
                raise ProductError("explicit_host_execution_approval_required")
            argv = args.host_argv
            if argv and argv[0] == "--":
                argv = argv[1:]
            if not argv:
                raise ProductError("explicit_host_command_required")
            environment = dict(os.environ)
            environment.update(store.host_environment(profile))
            # argv originates in the operator invocation, never discovered JSON,
            # .env, package scripts, model output or a profile launch command.
            return subprocess.call(argv, cwd=safe_path(profile.project), env=environment)
        raise ProductError("unknown_product_command")
    except (KeyboardInterrupt, EOFError):
        if args.command != "connect":
            ui.line("WARN", "Cancelled. No unapproved setup changes were applied.")
        return 130
    except Exception as error:
        code = error.code if isinstance(error, ProductError) else "invalid_configuration_or_operation"
        recommendation = "Review --help, run onboard --dry-run or doctor --full; existing databases/credentials are not repaired or rotated."
        if args.command == "connect":
            print("FAIL "+code+". "+recommendation, file=sys.stderr)
        elif args.json:
            print(json.dumps({"ok": False, "code": code, "recommendation": recommendation}))
        else:
            ui.line("FAIL", code+". "+recommendation)
        return 1
