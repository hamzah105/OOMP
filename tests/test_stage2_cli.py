"""Subprocess checks for Stage 2 storage diagnostics and synthetic example."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest


def cli(*arguments: str, env_path: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["OOMP_DB_PATH"] = str(env_path)
    return subprocess.run(
        [sys.executable, "-m", "oomp", *arguments],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


def test_missing_status_is_read_only_and_reports_unready(tmp_path: Path) -> None:
    database = tmp_path / "missing-parent" / "events.sqlite3"
    result = cli("storage", "status", "--db", str(database), env_path=tmp_path / "unused.sqlite3")
    assert result.returncode == 1
    assert "Exists: no" in result.stdout
    assert "Storage readiness: NOT READY" in result.stdout
    assert not database.parent.exists()


def test_explicit_init_and_status_are_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "nested" / "events.sqlite3"
    environment_database = tmp_path / "environment.sqlite3"
    first = cli("storage", "init", "--db", str(database), env_path=environment_database)
    second = cli("storage", "init", "--db", str(database), env_path=environment_database)
    status = cli("storage", "status", "--db", str(database), env_path=environment_database)
    assert first.returncode == second.returncode == status.returncode == 0
    assert "Schema version: 1" in first.stdout
    assert "Schema version: 1" in status.stdout
    assert "Exists: yes" in status.stdout
    assert "Accessible: yes" in status.stdout
    assert "Storage readiness: OK" in status.stdout
    assert database.is_file()
    assert not environment_database.exists()


def test_environment_database_path_used_without_explicit_flag(tmp_path: Path) -> None:
    database = tmp_path / "environment" / "events.sqlite3"
    init = cli("storage", "init", env_path=database)
    status = cli("storage", "status", env_path=database)
    assert init.returncode == status.returncode == 0
    assert str(database) in init.stdout
    assert str(database) in status.stdout
    assert database.is_file()


@pytest.mark.parametrize("future_version", [2, 999])
def test_future_schema_diagnostic_does_not_migrate(tmp_path: Path, future_version: int) -> None:
    database = tmp_path / "future.sqlite3"
    with closing(sqlite3.connect(database)) as connection:
        with connection:
            connection.execute(f"PRAGMA user_version = {future_version}")
    status = cli("storage", "status", "--db", str(database), env_path=database)
    assert status.returncode == 1
    assert "Storage readiness: NOT READY" in status.stdout
    assert "Traceback" not in status.stdout + status.stderr
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == future_version


def test_corrupt_database_diagnostic_is_bounded(tmp_path: Path) -> None:
    database = tmp_path / "corrupt.sqlite3"
    marker = "sensitive-event-content"
    database.write_text(marker, encoding="utf-8")
    status = cli("storage", "status", "--db", str(database), env_path=database)
    assert status.returncode == 1
    combined = status.stdout + status.stderr
    assert "NOT READY" in combined or "failed" in combined
    assert "Traceback" not in combined
    assert marker not in combined


def test_stage1_cli_commands_and_storage_help(tmp_path: Path) -> None:
    database = tmp_path / "unused.sqlite3"
    help_result = cli("--help", env_path=database)
    storage_help = cli("storage", "--help", env_path=database)
    version = cli("--version", env_path=database)
    doctor = cli("doctor", env_path=database)
    module_entry = cli(env_path=database)
    assert all(result.returncode == 0 for result in (help_result, storage_help, version, doctor, module_entry))
    assert "storage" in help_result.stdout
    assert "init" in storage_help.stdout
    assert "status" in storage_help.stdout
    assert "0.1.0" in version.stdout
    assert "Stage 1 package readiness: OK" in doctor.stdout
    assert not database.exists()


def test_example_survives_separate_runs_and_retries(tmp_path: Path) -> None:
    database = tmp_path / "example" / "events.sqlite3"
    script = Path(__file__).resolve().parents[1] / "examples" / "stage2_event_roundtrip.py"
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, str(script), "--db", str(database)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "Scoped event count: 2" in result.stdout
        assert "Retry resolved to original event: demo-event-1" in result.stdout
        assert result.stdout.index("demo-event-1:") < result.stdout.index("demo-event-2:")
    assert database.is_file()
    status = cli("storage", "status", "--db", str(database), env_path=database)
    assert status.returncode == 0
    assert "The user prefers Python" not in status.stdout
    assert "The user is planning" not in status.stdout
