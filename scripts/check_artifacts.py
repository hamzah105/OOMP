"""Audit built archives; no installation, extraction, upload or network access."""
from __future__ import annotations

import argparse
import email
import hashlib
import json
import re
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

FORBIDDEN_PARTS = {".git", ".venv", ".test-artifacts", "__pycache__", "credentials", "secrets", "data", "node_modules"}
FORBIDDEN_SUFFIXES = (".pyc", ".pyo", ".db", ".sqlite", ".sqlite3", ".pem", ".key", ".gguf", ".ggml", ".safetensors", ".onnx", ".faiss", ".hnsw")
SECRETS = (
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{36,}"),
    re.compile(rb"AKIA[A-Z0-9]{16}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s+[A-Za-z0-9+/=\r\n]{64,}-----END"),
)


def safe_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or re.match(r"^[A-Za-z]:", name):
        raise ValueError("unsafe archive path")
    if FORBIDDEN_PARTS.intersection(path.parts) or "benchmarks/results/" in name:
        raise ValueError("private/generated directory in archive")
    if path.name.startswith(".env") or path.name.endswith(FORBIDDEN_SUFFIXES) or re.search(r"\.(?:sqlite3?|db)-(?:wal|shm|journal)$", path.name):
        raise ValueError("secret/database/model/cache file in archive")


def audit(path: Path):
    contents = {}
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                safe_name(member.filename)
                if not member.is_dir():
                    contents[member.filename] = archive.read(member)
        metadata_path = next(n for n in contents if n.endswith(".dist-info/METADATA"))
        required = {"oomp/__init__.py", "oomp/cli.py", "oomp/storage/migrations.py", "oomp/mcp/server.py", "oomp/mind/worker.py"}
        assert required <= contents.keys(), "missing runtime modules"
        assert any(n.endswith(".dist-info/licenses/LICENSE") for n in contents)
        assert any(n.endswith(".dist-info/licenses/NOTICE") for n in contents)
        assert not any(n.startswith(("benchmarks/", "tests/", "examples/")) for n in contents)
    else:
        with tarfile.open(path, "r:gz") as archive:
            for member in archive.getmembers():
                safe_name(member.name)
                if member.issym() or member.islnk():
                    raise ValueError("archive links are not expected")
                if member.isfile():
                    contents[member.name] = archive.extractfile(member).read()
        prefix = next(iter(contents)).split("/", 1)[0] + "/"
        required = {"LICENSE", "NOTICE", "README.md", "pyproject.toml", "examples/quickstart.py", "examples/backup_restore.py",
            "benchmarks/runner.py", "benchmarks/configs/offline.json", "docs/benchmark-methodology.md",
            "docs/getting-started.md", "docs/privacy-retention.md", "scripts/check_artifacts.py", "tests/test_stage9_metrics.py"}
        assert {prefix + n for n in required} <= contents.keys(), "missing source/research/quickstart files"
        metadata_path = prefix + "PKG-INFO"
    message = email.message_from_bytes(contents[metadata_path])
    assert message["Name"] == "oomp-memory" and message["Version"] == "0.1.0"
    assert message["License-Expression"] == "Apache-2.0"
    assert message["Requires-Python"] == ">=3.11"
    for body in contents.values():
        if any(pattern.search(body) for pattern in SECRETS):
            raise ValueError("credential-like material requires review")
    return {"artifact": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size, "files": len(contents), "license": message["License-Expression"],
        "version": message["Version"], "private_or_generated_files": 0, "high_confidence_secret_matches": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    artifacts = sorted([*args.directory.glob("*.whl"), *args.directory.glob("*.tar.gz")])
    if not any(p.suffix == ".whl" for p in artifacts) or not any(p.name.endswith(".tar.gz") for p in artifacts):
        parser.error("both a wheel and source archive are required")
    result = [audit(path) for path in artifacts]
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
