"""Local package and event-storage diagnostics."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import re
import sys

from . import __version__


def doctor() -> int:
    healthy = True
    print(f"OOMP {__version__}")
    python_ok = sys.version_info >= (3, 11)
    print(f"Python: {sys.version.split()[0]} ({'OK' if python_ok else 'requires 3.11+'})")
    healthy &= python_ok

    try:
        installed_oomp = importlib.metadata.version("oomp-memory")
        package_ok = installed_oomp == __version__
        print(f"oomp-memory: {installed_oomp} ({'OK' if package_ok else 'version mismatch'})")
        healthy &= package_ok
    except importlib.metadata.PackageNotFoundError:
        print("oomp-memory: not installed")
        healthy = False

    try:
        pydantic_version = importlib.metadata.version("pydantic")
        match = re.fullmatch(
            r"(\d+)\.(\d+)(?:\.(\d+))?(?:\.post\d+)?(?:\+[A-Za-z0-9.]+)?",
            pydantic_version,
        )
        dependency_ok = bool(match and (int(match[1]), int(match[2])) >= (2, 9) and int(match[1]) < 3)
        print(f"pydantic: {pydantic_version} ({'OK' if dependency_ok else 'requires >=2.9,<3'})")
        healthy &= dependency_ok
    except importlib.metadata.PackageNotFoundError:
        print("pydantic: not installed")
        healthy = False

    for module in ("oomp.domain.models", "oomp.domain.interfaces", "oomp.retrieval.contracts"):
        try:
            importlib.import_module(module)
            print(f"{module}: import OK")
        except ImportError as error:
            print(f"{module}: import failed ({error})")
            healthy = False

    print(f"Stage 1 package readiness: {'OK' if healthy else 'FAILED'}")
    return 0 if healthy else 1


def storage_init(database_path: str | None) -> int:
    """Create or migrate the local event database on explicit request."""
    from .storage import SQLiteEventStore
    from .storage.errors import StorageError

    try:
        store = SQLiteEventStore(database_path)
        version = store.initialize()
    except (StorageError, OSError, ValueError) as error:
        print(f"Storage initialization failed ({type(error).__name__}).", file=sys.stderr)
        return 1
    print(f"Database: {store.path}")
    print(f"Schema version: {version}")
    print("Storage readiness: OK")
    return 0


def storage_status(database_path: str | None) -> int:
    """Inspect an existing database without creating files or directories."""
    from .storage import SQLiteEventStore
    from .storage.errors import StorageError

    try:
        status = SQLiteEventStore(database_path).status()
    except (StorageError, OSError, ValueError) as error:
        print(f"Storage status failed ({type(error).__name__}).", file=sys.stderr)
        return 1
    print(f"Database: {status.path}")
    print(f"Exists: {'yes' if status.exists else 'no'}")
    print(f"Accessible: {'yes' if status.accessible else 'no'}")
    print(f"Schema version: {status.schema_version if status.schema_version is not None else 'unknown'}")
    print(f"Journal mode: {status.journal_mode if status.journal_mode else 'unknown'}")
    print(f"Storage readiness: {'OK' if status.ready else 'NOT READY'}")
    if status.message:
        print(f"Status: {status.message}")
    return 0 if status.ready else 1


def memory_extract(database_path: str | None, tenant: str, namespace: str, event_id: str) -> int:
    """Process one stored event using trusted local-machine scope authority."""
    from .domain.models import AuthorizedScope
    from .ingestion import ExtractionPipeline, ProcessingError
    from .storage.errors import SchemaUpgradeRequiredError, StorageError

    try:
        scope = AuthorizedScope(
            tenant_id=tenant, namespace=namespace, principal_id="local-cli"
        )
        result = ExtractionPipeline(database_path).process_event(scope, event_id)
    except (StorageError, ProcessingError, OSError, ValueError, TypeError) as error:
        if isinstance(error, SchemaUpgradeRequiredError):
            print("Run oomp storage init --db <path> to upgrade the database.", file=sys.stderr)
        print(f"Memory extraction failed ({type(error).__name__}).", file=sys.stderr)
        return 1
    print(result.model_dump_json())
    return 0


def memory_list(
    database_path: str | None, tenant: str, namespace: str, *,
    limit: int, show_content: bool,
) -> int:
    """List scoped memory identifiers and provenance; content requires opt-in."""
    from .domain.models import AuthorizedScope
    from .storage.errors import SchemaUpgradeRequiredError, StorageError
    from .storage.memory_store import SQLiteMemoryStore

    if not 1 <= limit <= 100:
        print("Memory list limit must be from 1 to 100.", file=sys.stderr)
        return 1
    try:
        scope = AuthorizedScope(
            tenant_id=tenant, namespace=namespace, principal_id="local-cli"
        )
        page = SQLiteMemoryStore(database_path).list_memories(scope, limit=limit)
    except (StorageError, OSError, ValueError, TypeError) as error:
        if isinstance(error, SchemaUpgradeRequiredError):
            print("Run oomp storage init --db <path> to upgrade the database.", file=sys.stderr)
        print(f"Memory listing failed ({type(error).__name__}).", file=sys.stderr)
        return 1
    for memory in page.memories:
        record = {
            "memory_id": memory.memory_id,
            "memory_type": memory.memory_type.value,
            "source_event_ids": list(memory.source_event_ids),
            "evidence_count": len(memory.source_event_ids),
        }
        if show_content:
            record["canonical_content"] = memory.canonical_content
        print(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    if page.next_cursor is not None:
        print(f"More memories available after: {page.next_cursor.memory_id}")
    return 0

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="oomp",
        description="OOMP contract, environment, and local storage tools",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("doctor", help="check installed package and runtime readiness")
    storage_parser = subparsers.add_parser("storage", help="inspect or initialize the local event database")
    storage_commands = storage_parser.add_subparsers(dest="storage_command")
    init_parser = storage_commands.add_parser("init", help="initialize or migrate the event database")
    init_parser.add_argument("--db", metavar="PATH", help="database path (overrides OOMP_DB_PATH)")
    status_parser = storage_commands.add_parser("status", help="inspect database readiness without creating it")
    status_parser.add_argument("--db", metavar="PATH", help="database path (overrides OOMP_DB_PATH)")
    memory_parser = subparsers.add_parser("memory", help="extract and inspect local canonical memories")
    memory_commands = memory_parser.add_subparsers(dest="memory_command")
    extract_parser = memory_commands.add_parser("extract", help="extract memories from one stored event")
    extract_parser.add_argument("--tenant", required=True)
    extract_parser.add_argument("--namespace", required=True)
    extract_parser.add_argument("--event-id", required=True)
    extract_parser.add_argument("--db", metavar="PATH", help="database path (overrides OOMP_DB_PATH)")
    list_parser = memory_commands.add_parser("list", help="list memory IDs and evidence in one scope")
    list_parser.add_argument("--tenant", required=True)
    list_parser.add_argument("--namespace", required=True)
    list_parser.add_argument("--db", metavar="PATH", help="database path (overrides OOMP_DB_PATH)")
    list_parser.add_argument("--limit", type=int, default=100, metavar="N")
    list_parser.add_argument("--show-content", action="store_true", help="print canonical content for trusted local inspection")
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return doctor()
    if args.command == "storage":
        if args.storage_command == "init":
            return storage_init(args.db)
        if args.storage_command == "status":
            return storage_status(args.db)
        storage_parser.print_help()
        return 0
    if args.command == "memory":
        if args.memory_command == "extract":
            return memory_extract(args.db, args.tenant, args.namespace, args.event_id)
        if args.memory_command == "list":
            return memory_list(
                args.db, args.tenant, args.namespace,
                limit=args.limit, show_content=args.show_content,
            )
        memory_parser.print_help()
        return 0
    parser.print_help()
    return 0
