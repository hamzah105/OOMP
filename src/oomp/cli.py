"""Minimal local diagnostics for the Stage 1 package."""

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="oomp",
        description="OOMP Stage 1 contract and environment tools",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("doctor", help="check installed package and runtime readiness")
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return doctor()
    parser.print_help()
    return 0
