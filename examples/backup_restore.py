"""Synthetic, WAL-safe backup/recovery using Python's SQLite online backup API.

This example is local administrator code, not an MCP tool. It refuses overwrite.
    python examples/backup_restore.py --directory data/backup-demo
"""
from __future__ import annotations

from oomp.storage.migrations import SCHEMA_VERSION

import argparse
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from oomp.ingestion import ExtractionPipeline
from oomp.storage import SQLiteEventStore
if __package__:
    from .quickstart import SCOPE, source
else:
    from quickstart import SCOPE, source


def backup_new(source_path: Path, destination_path: Path) -> None:
    """Snapshot a trusted existing SQLite database into a NEW destination.

    Ordinary file copying can omit live WAL commits. backup() reads the complete
    committed SQLite view. A failed output is not a verified restore candidate.
    """
    source_path, destination_path = source_path.resolve(), destination_path.resolve()
    if not source_path.is_file() or source_path == destination_path:
        raise ValueError("a distinct existing source database is required")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(destination_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    with closing(sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True)) as origin:
        with closing(sqlite3.connect(destination_path)) as target:
            origin.backup(target, pages=128, sleep=0.05)
            if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise RuntimeError("backup integrity check failed")


def run(directory: Path) -> dict:
    directory.mkdir(parents=True, exist_ok=False)
    original_path = directory / "source.sqlite3"
    store = SQLiteEventStore(original_path)
    store.initialize()
    first = source("backup-first", "I am developing a project called BackupDemo.")
    second = source("backup-wal-commit", "I prefer amber mode.", 1)
    store.append(SCOPE, first)
    # A separate open connection keeps WAL state alive across the later commit.
    with closing(sqlite3.connect(original_path)) as keeper:
        assert keeper.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        store.append(SCOPE, second)
        ExtractionPipeline(original_path).process_event(SCOPE, first.event_id)
        assert Path(str(original_path) + "-wal").stat().st_size > 0
        backup_path = directory / "snapshot.sqlite3"
        restored_path = directory / "restored.sqlite3"
        backup_new(original_path, backup_path)
        backup_new(backup_path, restored_path)
    restored = SQLiteEventStore(restored_path)
    assert restored.status().ready and restored.status().schema_version == SCHEMA_VERSION
    assert restored.get(SCOPE, first.event_id) == first
    assert restored.get(SCOPE, second.event_id) == second
    return {"synthetic": True, "source_events": 2, "restored_events": restored.count_events(SCOPE),
        "committed_wal_event_recovered": True, "schema": SCHEMA_VERSION, "backup_api": "sqlite3.Connection.backup",
        "overwrite_allowed": False, "cryptographic_secure_deletion_claimed": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, help="new disposable example directory")
    args = parser.parse_args(argv)
    if args.directory is not None:
        result = run(args.directory)
    else:
        with TemporaryDirectory(prefix="oomp-backup-") as temporary:
            result = run(Path(temporary) / "demo")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
