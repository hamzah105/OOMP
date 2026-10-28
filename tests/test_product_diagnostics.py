"""P1 diagnostic measurements, no mutation, and stable redacted output."""
from __future__ import annotations

from contextlib import closing
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sqlite3

import pytest

from oomp.cli import main
from oomp.product.diagnostics import diagnose, inspection_snapshot, synthetic_probe
from oomp.product.models import Profile
from oomp.product.profiles import ProfileStore
from oomp.product.safety import ProductError, write_json
from test_product_profiles import setup_profile


def hash_tree(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def check(report, name):
    return next(c for c in report["checks"] if c["id"] == name)


def test_synthetic_diagnostic_executes_real_worker_and_source_provenance():
    report = synthetic_probe()
    assert report["source_proofs"] == 1 and report["model_calls"] == 0
    assert 0 < report["evidence_bytes"] <= report["budget_bytes"]


def test_full_doctor_does_not_write_profile_database_or_sidecars(tmp_path, monkeypatch):
    import oomp.product.diagnostics as module
    store, profile = setup_profile(tmp_path)
    monkeypatch.setattr(module, "synthetic_probe", lambda: {"fixture": True})
    before = hash_tree(store.home)
    report = diagnose(store, "test", full=True)
    assert check(report, "storage")["outcome"] == "PASS"
    assert check(report, "index.offline")["details"]["canonical"] == 0
    assert check(report, "mcp")["outcome"] == "FAIL"  # TCP/listener availability was not assumed
    assert check(report, "mind")["outcome"] == "WARN"
    assert check(report, "provider")["outcome"] == "NOT TESTED"
    assert hash_tree(store.home) == before
    raw = json.dumps(report)
    assert not any(v in raw for v in store.environment(profile).values())


def test_wal_is_not_ignored_or_mutated_by_offline_diagnostics(tmp_path):
    store, profile = setup_profile(tmp_path)
    database = Path(profile.database)
    with closing(sqlite3.connect(database)) as writer:
        writer.execute("CREATE TABLE synthetic_probe(value)")
        writer.execute("INSERT INTO synthetic_probe VALUES (1)")
        writer.commit()
        before = hash_tree(store.home)
        with pytest.raises(ProductError, match="wal_requires_live_status_or_offline_backup"):
            with inspection_snapshot(database):
                pytest.fail("an incomplete immutable snapshot must not be presented as current")
        assert hash_tree(store.home) == before


def test_missing_database_is_not_initialized_or_recreated(tmp_path, monkeypatch):
    import oomp.product.diagnostics as module
    store, profile = setup_profile(tmp_path)
    Path(profile.database).unlink()
    monkeypatch.setattr(module, "synthetic_probe", lambda: {})
    report = diagnose(store, "test", full=True)
    assert check(report, "storage")["outcome"] == "FAIL"
    assert not Path(profile.database).exists()


def test_future_schema_is_rejected_without_migration(tmp_path, monkeypatch):
    import oomp.product.diagnostics as module
    store, profile = setup_profile(tmp_path)
    with closing(sqlite3.connect(profile.database)) as connection:
        connection.execute("PRAGMA user_version=999")
    before = hash_tree(store.home)
    monkeypatch.setattr(module, "synthetic_probe", lambda: {})
    report = diagnose(store, "test", full=True)
    assert check(report, "storage")["outcome"] == "FAIL"
    assert hash_tree(store.home) == before


def test_machine_diagnostics_invalid_profile_is_safe_and_stable(tmp_path, capsys):
    home = tmp_path/"missing"
    result = main(["doctor", "--full", "--profile", "absent", "--home", str(home), "--json"])
    report = json.loads(capsys.readouterr().out)
    assert result == 1 and report["schema_version"] == 1
    assert report["ok"] is False and report["summary"]["FAIL"] > 0
    assert check(report, "profile")["code"] == "profile_or_credentials_invalid"
    assert not home.exists()


def test_missing_optional_sdk_is_not_a_passing_check(tmp_path, monkeypatch):
    import oomp.product.diagnostics as module
    version = importlib.metadata.version
    def missing(name):
        if name == "mcp":
            raise importlib.metadata.PackageNotFoundError(name)
        return version(name)
    monkeypatch.setattr(importlib.metadata, "version", missing)
    report = diagnose(ProfileStore(tmp_path/"profiles"))
    assert check(report, "package.mcp")["outcome"] == "NOT TESTED"


def test_incompatible_interpreter_is_a_failure(tmp_path, monkeypatch):
    import oomp.product.diagnostics as module
    monkeypatch.setattr(module.sys, "version_info", (3, 10, 0))
    report = diagnose(ProfileStore(tmp_path/"profiles"))
    assert check(report, "python")["outcome"] == "FAIL" and not report["ok"]


def test_bad_runtime_file_never_leaks_values_or_breaks_json(tmp_path, monkeypatch):
    import oomp.product.diagnostics as module
    store, _ = setup_profile(tmp_path)
    secret = "SECRET_SENTINEL_"+"X"*43
    write_json(store.directory("test")/"runtime.json", {"token": secret, "port": "bad", "run_id": "bad"})
    monkeypatch.setattr(module, "synthetic_probe", lambda: {})
    report = diagnose(store, "test", full=True)
    assert check(report, "runtime.state")["outcome"] == "FAIL"
    assert secret not in json.dumps(report)


def test_opted_in_provider_failure_preserves_lexical_diagnostic_path(tmp_path, monkeypatch):
    import oomp.product.diagnostics as module
    from oomp.providers.ollama import OllamaEmbeddingProvider
    store, _ = setup_profile(tmp_path, provider={"model": "synthetic-not-downloaded", "dimension": 2,
                                               "version": "synthetic-test", "endpoint": "http://127.0.0.1:11434"})
    monkeypatch.setattr(module, "synthetic_probe", lambda: {})
    monkeypatch.setattr(OllamaEmbeddingProvider, "embed", lambda *_: (_ for _ in ()).throw(RuntimeError("provider absent")))
    report = diagnose(store, "test", full=True)
    assert check(report, "provider")["outcome"] == "WARN"
    assert check(report, "storage")["outcome"] == "PASS"


@pytest.mark.parametrize("endpoint", ["http://0.0.0.0:11434", "http://example.com:11434", "https://127.0.0.1:11434"])
def test_provider_cannot_escape_approved_literal_loopback(endpoint, tmp_path):
    with pytest.raises(ValueError):
        Profile(name="test", database=str(tmp_path/"db.sqlite3"), provider={
            "model": "synthetic", "dimension": 2, "version": "fixture", "endpoint": endpoint})


def test_stdio_connect_failure_keeps_stdout_reserved_for_protocol(tmp_path, capsys):
    assert main(["connect", "--home", str(tmp_path/"missing"), "--json"]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "FAIL" in captured.err
