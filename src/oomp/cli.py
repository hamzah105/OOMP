"""Local package and event-storage diagnostics."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
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
    parser.print_help()
    return 0
