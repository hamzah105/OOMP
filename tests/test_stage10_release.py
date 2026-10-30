from __future__ import annotations

from oomp.storage.migrations import SCHEMA_VERSION

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from examples.backup_restore import backup_new, run as backup_demo
from examples.quickstart import run as quickstart, SCOPE, source
from scripts.check_artifacts import safe_name
from oomp.storage import SQLiteEventStore


def test_quickstart_persists_extracts_retrieves_original_provenance(tmp_path):
    report = quickstart(tmp_path / "quickstart.sqlite3", later_turns=9)
    assert report["source_events"] == 10 and report["earlier_fact_outside_recent_eight"]
    assert report["source_event_ids"] == ["early-project"]
    assert report["source_references"][0]["external_event_id"] == "early-project"
    assert report["context_bytes"] <= report["budget"] and report["model_calls"] == 0


def test_quickstart_refuses_existing_database_without_mutation(tmp_path):
    path = tmp_path / "existing.sqlite3"
    path.write_bytes(b"existing unrelated data")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="new disposable"):
        quickstart(path)
    assert path.read_bytes() == before


def test_backup_recovers_a_committed_live_wal_and_schema(tmp_path):
    report = backup_demo(tmp_path / "backup")
    assert report["committed_wal_event_recovered"] and report["restored_events"] == 2
    assert report["schema"] == SCHEMA_VERSION and not report["cryptographic_secure_deletion_claimed"]


def test_backup_refuses_existing_destination_and_preserves_source(tmp_path):
    path = tmp_path / "source.sqlite3"; store = SQLiteEventStore(path); store.initialize()
    event = source("backup-source", "I prefer amber mode.")
    store.append(SCOPE, event)
    destination = tmp_path / "existing.sqlite3"; destination.write_bytes(b"keep this file")
    before = destination.read_bytes()
    with pytest.raises(FileExistsError):
        backup_new(path, destination)
    assert destination.read_bytes() == before and store.get(SCOPE, event.event_id) == event


def test_backup_rejects_same_or_missing_source(tmp_path):
    path = tmp_path / "missing.sqlite3"
    with pytest.raises(ValueError):
        backup_new(path, tmp_path / "new.sqlite3")
    assert not path.exists() and not (tmp_path / "new.sqlite3").exists()
    SQLiteEventStore(path).initialize()
    with pytest.raises(ValueError):
        backup_new(path, path)


@pytest.mark.parametrize("name", [
    "../../outside.py", "/absolute/secret", "C:/private/secret", "folder\\private.py",
    "package/.env", "package/credentials/secret.json", "package/data/events.sqlite3",
    "package/benchmarks/results/run/manifest.json", "package/weights.gguf", "package/events.sqlite3-wal",
])
def test_artifact_policy_rejects_private_and_unsafe_members(name):
    with pytest.raises(ValueError):
        safe_name(name)


def test_artifact_policy_allows_public_synthetic_research_source():
    for name in ("oomp_memory-0.1.0/benchmarks/configs/offline.json", "oomp/storage/migrations.py",
                 "oomp_memory-0.1.0/docs/examples/stage9-results.json"):
        safe_name(name)


def test_preserved_stage5_example_runs_against_current_schema(tmp_path, capsys):
    from examples.stage5_hybrid_retrieval import run
    run(tmp_path / "stage5-compatible.sqlite3")
    output = capsys.readouterr().out
    assert "Schema: 5" in output
    assert "Original event outside latest eight: True" in output
    assert "Graph linked memory and proof: True" in output
