"""Stage 3 local CLI and repeatable example behavior."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from oomp.domain.enums import EventType, SourceType
from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
from oomp.storage import SQLiteEventStore
from oomp.storage.migrations import MIGRATIONS

NOW = datetime(2026, 1, 2, 10, tzinfo=timezone.utc)
SCOPE = AuthorizedScope(tenant_id="tenant-cli", namespace="personal", principal_id="test-service")


def cli(*arguments: str, database: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["OOMP_DB_PATH"] = str(database)
    return subprocess.run(
        [sys.executable, "-m", "oomp", *arguments],
        capture_output=True, text=True, check=False, env=environment,
    )


def source() -> MemoryEvent:
    return MemoryEvent(
        event_id="event-1", tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
        event_type=EventType.USER_MESSAGE, source_type=SourceType.USER,
        content="I prefer Python.",
        source_reference=SourceReference(
            source_system="synthetic-test", external_event_id="event-1", timestamp=NOW,
        ),
        occurred_at=NOW, ingested_at=NOW,
    )


def test_extract_and_list_hide_content_until_opted_in(tmp_path: Path) -> None:
    database = tmp_path / "cli.sqlite3"
    assert SQLiteEventStore(database).initialize() == 2
    SQLiteEventStore(database).append(SCOPE, source())
    extract = cli(
        "memory", "extract", "--tenant", SCOPE.tenant_id, "--namespace", SCOPE.namespace,
        "--event-id", "event-1", "--db", str(database), database=database,
    )
    assert extract.returncode == 0, extract.stderr
    result = json.loads(extract.stdout)
    assert result["memories_created"] == 1
    assert result["evidence_links_added"] == 1
    assert "User prefers Python." not in extract.stdout

    listed = cli(
        "memory", "list", "--tenant", SCOPE.tenant_id, "--namespace", SCOPE.namespace,
        "--db", str(database), database=database,
    )
    assert listed.returncode == 0, listed.stderr
    record = json.loads(listed.stdout.splitlines()[0])
    assert record["memory_type"] == "profile"
    assert record["evidence_count"] == 1
    assert record["source_event_ids"] == ["event-1"]
    assert "canonical_content" not in record

    visible = cli(
        "memory", "list", "--tenant", SCOPE.tenant_id, "--namespace", SCOPE.namespace,
        "--db", str(database), "--show-content", database=database,
    )
    assert visible.returncode == 0
    assert json.loads(visible.stdout.splitlines()[0])["canonical_content"] == "User prefers Python."


def test_cli_scope_and_missing_database_fail_closed(tmp_path: Path) -> None:
    missing = tmp_path / "absent" / "events.sqlite3"
    absent = cli(
        "memory", "list", "--tenant", "tenant-cli", "--namespace", "personal",
        "--db", str(missing), database=missing,
    )
    assert absent.returncode == 1
    assert not missing.parent.exists()
    database = tmp_path / "scoped.sqlite3"
    SQLiteEventStore(database).initialize()
    SQLiteEventStore(database).append(SCOPE, source())
    foreign = cli(
        "memory", "extract", "--tenant", "tenant-other", "--namespace", "personal",
        "--event-id", "event-1", "--db", str(database), database=database,
    )
    assert foreign.returncode == 1
    assert "I prefer Python" not in foreign.stdout + foreign.stderr
    empty_list = cli(
        "memory", "list", "--tenant", "tenant-other", "--namespace", "personal",
        "--db", str(database), database=database,
    )
    assert empty_list.returncode == 0
    assert empty_list.stdout == ""


def test_invalid_limit_and_existing_cli_commands(tmp_path: Path) -> None:
    database = tmp_path / "unused.sqlite3"
    invalid = cli(
        "memory", "list", "--tenant", "tenant-cli", "--namespace", "personal",
        "--limit", "0", "--db", str(database), database=database,
    )
    assert invalid.returncode == 1
    assert not database.exists()
    assert "memory" in cli("--help", database=database).stdout
    assert "extract" in cli("memory", "--help", database=database).stdout
    assert cli("--version", database=database).returncode == 0
    assert "Stage 1 package readiness: OK" in cli("doctor", database=database).stdout


def test_example_repeats_without_new_memory_or_entity(tmp_path: Path) -> None:
    database = tmp_path / "demo" / "events.sqlite3"
    script = Path(__file__).resolve().parents[1] / "examples" / "stage3_memory_extraction.py"
    for _ in range(2):
        completed = subprocess.run(
            [sys.executable, str(script), "--db", str(database)],
            capture_output=True, text=True, check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert "Stored source events: 4" in completed.stdout
        assert "Canonical memories: 2" in completed.stdout
        assert "type=profile evidence=2" in completed.stdout
        assert "type=project_state evidence=2 entities=1" in completed.stdout


def test_version_one_requires_explicit_upgrade(tmp_path: Path) -> None:
    database = tmp_path / "v1.sqlite3"
    with closing(sqlite3.connect(database)) as connection:
        with connection:
            for statement in MIGRATIONS[1]:
                connection.execute(statement)
            connection.execute("PRAGMA user_version = 1")
    result = cli(
        "memory", "list", "--tenant", SCOPE.tenant_id, "--namespace", SCOPE.namespace,
        "--db", str(database), database=database,
    )
    assert result.returncode == 1
    assert "oomp storage init --db <path>" in result.stderr
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1