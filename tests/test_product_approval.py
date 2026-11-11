"""Fictional metadata-only approval and interrupted-transaction recovery."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys

import pytest

from oomp.cli import main
from oomp.product import approval, handoff, lifecycle, start
from oomp.product.discovery import TRACE_FILES, project_fingerprint
from oomp.product.models import Profile
from oomp.product.profiles import ProfileStore
from oomp.product.safety import ProductError, private_permissions, read_json, write_json


def free_port():
    with socket.socket() as endpoint:
        endpoint.bind(("127.0.0.1", 0))
        return endpoint.getsockname()[1]


@pytest.fixture
def pair(tmp_path, monkeypatch):
    project = tmp_path/"TRACE"
    for filename in TRACE_FILES:
        path = project/filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"# fictional reviewed source\n")
    pin = tmp_path/"selection"/"selection.json"
    monkeypatch.setattr(start, "selection_path", lambda: pin)
    store = ProfileStore(tmp_path/"p")
    profile = Profile(name="fictional", adapter="trace", project=str(project),
        database=str(store.directory("fictional")/"memory.sqlite3"), owner_id="0"*24,
        mode="trusted-ingest", tenant="fictional", namespace="dedicated", principal="owner",
        publication=True, host_python=str(Path(sys.executable).resolve()),
        mongo_uri_env="FICTIONAL_MONGO", mongo_database="fictional",
        port=free_port(), host_origin="http://127.0.0.1:"+str(free_port()),
        approved_project=project_fingerprint(project), context_enabled=True)
    store.create(profile, create_credentials=True)
    handoff.configure_trace(store, profile, approve=True)
    start.remember(store, profile)
    changed = project/"backend/services/oomp_publisher.py"
    old_source = changed.read_bytes()
    changed.write_bytes(old_source+b"# reviewed repair\n")
    return store, profile, changed, old_source


def approve(pair):
    store, old, *_ = pair
    plan = approval.refresh(store, old.name)
    return approval.refresh(store, old.name, expected_plan=plan["plan_sha256"])


def critical(store, profile):
    paths = approval._targets(store, profile)
    paths["secrets"] = store.directory(profile.name)/"secrets.json"
    paths["database"] = Path(profile.database)
    return {k: v.read_bytes() for k, v in paths.items()}


def test_preview_is_read_only_and_requires_exact_plan(pair):
    store, old, *_ = pair
    before = critical(store, old)
    plan = approval.refresh(store, old.name)
    assert plan["changed_sources"].keys() == {"backend/services/oomp_publisher.py"}
    assert not plan["credentials_rotated"] and not plan["database_access"]
    with pytest.raises(ProductError, match="approval_plan_changed"):
        approval.refresh(store, old.name, expected_plan="0"*64)
    assert critical(store, old) == before
    assert not (store.directory(old.name)/"history").exists()


def test_refresh_preserves_authority_credentials_data_and_old_signed_artifacts(pair, monkeypatch):
    import sqlite3
    store, old, *_ = pair
    before = critical(store, old)
    parent_private = private_permissions(Path(old.project))
    old_files = {n: (store.generation(old)/n).read_bytes() for n in approval.GENERATION_FILES}
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: pytest.fail("approval opened SQLite"))
    monkeypatch.setattr(socket.socket, "connect", lambda *a, **k: pytest.fail("approval connected to a service"))
    result = approve(pair)
    new = store.load(old.name)
    assert new.identity != old.identity
    assert {**old.model_dump(), "approved_project": new.approved_project} == new.model_dump()
    assert old.grants() == new.grants() and old.server() == new.server()
    assert critical(store, new)["secrets"] == before["secrets"]
    assert critical(store, new)["database"] == before["database"]
    assert {n: (store.generation(old)/n).read_bytes() for n in old_files} == old_files
    assert handoff.preview_trace(store, new)["configured"]
    assert start.resolve_selection()[1] == old.name
    assert private_permissions(Path(old.project)) == parent_private
    record = read_json(store.directory(old.name)/"history"/result["transaction"]/"transaction.json")
    assert approval._document(record["before"]["handoff"]) == before["handoff"]
    assert approval._document(record["before"]["selection"]) == before["selection"]
    assert all(v not in json.dumps(result) for v in store.environment(new).values())


def test_exact_rollback_requires_old_source_and_restores_original_bytes(pair):
    store, old, changed, original = pair
    before = critical(store, old)
    result = approve(pair)
    with pytest.raises(ProductError, match="approval_restore_old_source_first"):
        approval.rollback(store, old.name, result["transaction"])
    changed.write_bytes(original)
    plan = approval.rollback(store, old.name, result["transaction"])
    approval.rollback(store, old.name, result["transaction"], expected_plan=plan["plan_sha256"])
    assert store.load(old.name) == old and critical(store, old) == before
    assert handoff.preview_trace(store, old)["configured"]
    assert start.resolve_selection()[1] == old.name


@pytest.mark.parametrize("after_write", [1, 2, 3, 4])
def test_interruption_is_fail_closed_and_explicitly_recoverable(pair, monkeypatch, after_write):
    store, old, changed, original = pair
    before = critical(store, old)
    real_switch = approval._switch
    def interrupted(*args):
        real_write = approval._write
        calls = []
        def write(path, data):
            real_write(path, data)
            calls.append(path)
            if len(calls) == after_write:
                raise OSError("synthetic interruption")
        with monkeypatch.context() as scoped:
            scoped.setattr(approval, "_write", write)
            real_switch(*args)
    monkeypatch.setattr(approval, "_switch", interrupted)
    with pytest.raises(OSError, match="synthetic interruption"):
        approve(pair)
    with pytest.raises(ProductError, match="approval_transaction_incomplete"):
        store.load(old.name)
    transaction = read_json(store.directory(old.name)/approval.PENDING)["transaction"]
    monkeypatch.setattr(approval, "_switch", real_switch)
    changed.write_bytes(original)
    plan = approval.rollback(store, old.name, transaction)
    approval.rollback(store, old.name, transaction, expected_plan=plan["plan_sha256"])
    assert store.load(old.name) == old and critical(store, old) == before


@pytest.mark.parametrize("negative", ["running", "reused_pid", "mcp_port", "trace_port", "launch_lock", "operation_lock"])
def test_live_uncertain_and_concurrent_owners_are_never_changed(pair, monkeypatch, negative):
    store, old, *_ = pair
    before = critical(store, old)
    if negative in {"running", "reused_pid"}:
        state = {"pid": 123, "port": free_port(), "token": "X"*43, "run_id": "a"*32,
                 "configuration": old.identity, "stopped": negative != "running"}
        write_json(store.directory(old.name)/"runtime.json", state)
        monkeypatch.setattr(lifecycle, "_process_gone", lambda _: False)
        with pytest.raises(ProductError, match="approval_requires_stopped_services"):
            approval.refresh(store, old.name)
    elif negative in {"mcp_port", "trace_port"}:
        from urllib.parse import urlsplit
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", old.port if negative == "mcp_port" else urlsplit(old.host_origin).port))
            listener.listen()
            with pytest.raises(ProductError, match="approval_requires_free_ports"):
                approval.refresh(store, old.name)
    else:
        filename = "launch.lock" if negative == "launch_lock" else "operation.lock"
        with lifecycle._checked_lock(store.directory(old.name)/filename):
            with pytest.raises(ProductError, match="profile_busy"):
                approval.refresh(store, old.name)
    assert critical(store, old) == before


@pytest.mark.parametrize("changed_input", ["handoff", "selection", "credentials", "generation", "source"])
def test_preview_does_not_authorize_later_changed_inputs(pair, changed_input):
    store, old, changed, *_ = pair
    plan = approval.refresh(store, old.name)
    if changed_input == "source":
        changed.write_bytes(changed.read_bytes()+b"# unreviewed\n")
    else:
        path = {"handoff": Path(old.project)/handoff.LOCAL_FILE,
                "selection": start.selection_path(), "credentials": store.directory(old.name)/"secrets.json",
                "generation": store.generation(old)/"client.json"}[changed_input]
        data = read_json(path)
        if changed_input == "selection":
            data["authority_sha256"] = "0"*64
        elif changed_input == "credentials":
            first = next(iter(data)); data[first] = "Z"*43
        else:
            data["unexpected"] = True
        path.write_bytes(approval._raw(data))  # intentional tamper of this private fixture file
    before = (store.directory(old.name)/"active.json").read_bytes()
    with pytest.raises(ProductError):
        approval.refresh(store, old.name, expected_plan=plan["plan_sha256"])
    assert (store.directory(old.name)/"active.json").read_bytes() == before


def test_unrelated_saved_default_is_preserved(pair):
    store, old, *_ = pair
    write_json(start.selection_path(), {"format_version": 1, "profile": "another", "home": "elsewhere", "authority_sha256": "a"*64})
    before = start.selection_path().read_bytes()
    assert not approve(pair)["update_saved_default"]
    assert start.selection_path().read_bytes() == before


@pytest.mark.parametrize("tamper", ["journal", "active", "credentials"])
def test_rollback_never_overwrites_unrecognized_metadata(pair, tamper):
    store, old, changed, original = pair
    result = approve(pair)
    changed.write_bytes(original)
    path = (store.directory(old.name)/"history"/result["transaction"]/"transaction.json" if tamper == "journal"
            else store.directory(old.name)/("active.json" if tamper == "active" else "secrets.json"))
    data = read_json(path)
    if tamper == "journal": data["state"] = "tampered"
    elif tamper == "active": data["generation"] = "0"*64
    else: data[next(iter(data))] = "Y"*43
    write_json(path, data)
    before = path.read_bytes()
    with pytest.raises(ProductError):
        approval.rollback(store, old.name, result["transaction"])
    assert path.read_bytes() == before


def test_cli_requires_explicit_exact_plan_and_round_trips(pair, capsys):
    store, old, *_ = pair
    args = ["approve-project", "--home", str(store.home), "--profile", old.name, "--json"]
    assert main([*args, "--yes"]) != 0
    capsys.readouterr()
    assert main([*args, "--dry-run"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert main([*args, "--yes", "--expected-plan", plan["plan_sha256"]]) == 0
    assert json.loads(capsys.readouterr().out)["applied"]
