"""Bounded, read-only indicators. Project files are data, never launch commands."""
from __future__ import annotations

import hashlib
import importlib.metadata
from pathlib import Path
import sys

from .safety import ProductError, safe_path

TRACE_FILES = (
    "backend/services/oomp_config.py", "backend/services/oomp_client.py",
    "backend/services/oomp_publisher.py", "backend/services/oomp_diagnostics.py",
    "backend/services/oomp_contracts.py", "backend/services/oomp_security.py",
    "backend/services/oomp_context.py",
)
INDICATORS = ("pyproject.toml", "requirements.txt", "package.json", ".env.example",
              "mcp.json", ".mcp.json", "backend/main.py", "main.py", "app.py")


def discover(project: str | Path | None) -> dict:
    runtime = {"python": sys.version.split()[0], "python_supported": sys.version_info >= (3, 11)}
    try:
        runtime["mcp_sdk"] = importlib.metadata.version("mcp")
    except importlib.metadata.PackageNotFoundError:
        runtime["mcp_sdk"] = "not installed; install the optional [mcp] extra"
    if project is None:
        return {"kind": "standalone", "languages": [], "frameworks": [], "indicators": [], "existing_integration": False,
                "runtime": runtime, "provider_discovery": "not probed; no provider selected"}
    root = safe_path(project)
    if not root.is_dir():
        raise ProductError("project_missing")
    found, languages, frameworks = [], set(), set()
    for name in INDICATORS:
        file = safe_path(root / name)
        if not file.is_file():
            continue
        found.append(name)
        with file.open("rb") as handle:
            raw = handle.read(32768).lower()
        if name in {"pyproject.toml", "requirements.txt"} or name.endswith(".py"):
            languages.add("Python")
        if name == "package.json":
            languages.add("JavaScript/TypeScript")
        if b"fastapi" in raw:
            frameworks.add("FastAPI indicator (not compatibility certification)")
    trace = all(safe_path(root / n).is_file() for n in TRACE_FILES)
    mcp = any(n in found for n in ("mcp.json", ".mcp.json"))
    return {"kind": "trace" if trace else "generic-mcp" if mcp else "unknown",
            "languages": sorted(languages), "frameworks": sorted(frameworks),
            "indicators": found, "existing_integration": trace or safe_path(root / ".oomp/host.json").is_file(),
            "runtime": runtime,
            "provider_discovery": "not probed; only explicit local provider selection permits network checks"}


def project_fingerprint(root: str | Path) -> dict[str, str]:
    root = safe_path(root)
    result = {}
    for name in TRACE_FILES:
        file = safe_path(root / name)
        if not file.is_file() or file.stat().st_size > 262144:
            raise ProductError("trace_adapter_unavailable")
        result[name] = hashlib.sha256(file.read_bytes()).hexdigest()
    for name in ("backend/__init__.py", "backend/services/__init__.py", "backend/database/__init__.py"):
        file = safe_path(root / name)
        if file.is_file():
            if file.stat().st_size > 32768:
                raise ProductError("trace_adapter_unavailable")
            result[name] = hashlib.sha256(file.read_bytes()).hexdigest()
    return result
