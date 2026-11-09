"""Synthetic stale-supervisor recovery: private evidence, OS locks and owned crash."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from oomp.product import lifecycle, safety, start
from oomp.product.models import Profile
from oomp.product.profiles import ProfileStore
from oomp.product.safety import ProductError, file_lock, private_permissions, read_json, write_json


def free_port():
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", 0))
        return connection.getsockname()[1]


def synthetic_profile(tmp_path, **changes):
    store = ProfileStore(tmp_path / "p")
    profile = Profile(name="synthetic", port=free_port(),
        database=str(store.directory("synthetic") / "memory.sqlite3"), **changes)
    store.create(profile, create_credentials=True)
    return store, profile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preserved_files(store, profile):
    directory = store.directory(profile.name)
    files = [Path(profile.database), directory / "active.json", directory / "secrets.json"]
    files.extend(store.generation(profile).glob("*.json"))
    files.extend(path for path in (Path(profile.database + "-wal"), Path(profile.database + "-shm")) if path.exists())
    if profile.project:
        handoff = Path(profile.project) / ".oomp.local.json"
        if handoff.exists():
            files.append(handoff)
    return {path: digest(path) for path in files}


def assert_preserved(before):
    # Compare digests, never put raw synthetic runtime/credential values into a
    # failed assertion or JUnit payload.
    assert all(path.exists() and digest(path) == value for path, value in before.items())


@pytest.fixture
def exited_pid():
    process = subprocess.Popen([sys.executable, "-I", "-c", "pass"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    process.wait(timeout=10)
    return process.pid


def orphan(store, profile, recorded_pid, **changes):
    control_port = free_port()
    while control_port == profile.port:
        control_port = free_port()
    state = {"pid": recorded_pid, "port": control_port, "token": secrets.token_urlsafe(32),
        "run_id": secrets.token_hex(16), "configuration": profile.identity, "stopped": False}
    state.update(changes)
    path = store.directory(profile.name) / "runtime.json"
    write_json(path, state)
    return path, state


def archives(store, profile):
    return sorted((store.directory(profile.name) / "history").glob("recovery-*/runtime.json"))


@contextmanager
def operation_lock_holder(path):
    """The second process owns the real byte-range/flock handle, not a marker."""
    code = ("import sys; from pathlib import Path; "
        "from oomp.product.safety import file_lock; "
        "guard=file_lock(Path(sys.argv[1])); guard.__enter__(); "
        "print('locked', flush=True); sys.stdin.buffer.read(1); guard.__exit__(None,None,None)")
    process = subprocess.Popen([sys.executable, "-I", "-c", code, str(path)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        ready = []
        reader = threading.Thread(target=lambda: ready.append(process.stdout.readline(32)), daemon=True)
        reader.start()
        reader.join(10)
        assert len(ready) == 1 and ready[0].strip() == b"locked", "owned lock helper did not acquire the OS lock"
        yield process
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            # Only the handle returned for this test-created helper is signalled.
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()


def test_native_liveness_distinguishes_current_and_exited_owned_process(exited_pid):
    assert lifecycle._process_gone(os.getpid()) is False
    assert lifecycle._process_gone(exited_pid) is True


def test_dead_record_is_archived_privately_without_touching_profile_or_data(tmp_path, exited_pid, capsys):
    project = tmp_path / "synthetic-trace"
    project.mkdir()
    store, profile = synthetic_profile(tmp_path, adapter="trace", project=str(project),
        owner_id="000000000000000000000001")
    # These synthetic sentinels make any accidental DB/WAL/SHM access or handoff
    # regeneration observable; recovery is not a database-opening operation.
    for path in [Path(profile.database + "-wal"), Path(profile.database + "-shm"), project / ".oomp.local.json"]:
        path.write_bytes(b"synthetic recovery must preserve these bytes")
        safety.restrict(path)
    before = preserved_files(store, profile)
    path, state = orphan(store, profile, exited_pid)
    original_hash = digest(path)
    assert lifecycle.recover_stale(store, profile) is True
    archived = archives(store, profile)
    assert len(archived) == 1 and not path.exists()
    assert digest(archived[0]) == original_hash
    assert private_permissions(archived[0])
    assert private_permissions(archived[0].parent)
    assert private_permissions(archived[0].parent.parent)
    assert_preserved(before)
    assert lifecycle.recover_stale(store, profile) is False
    assert len(archives(store, profile)) == 1
    output = capsys.readouterr()
    if state["token"] in output.out + output.err:
        pytest.fail("a runtime token was disclosed")


def test_absent_or_gracefully_finalized_record_needs_no_retirement(tmp_path, exited_pid):
    store, profile = synthetic_profile(tmp_path)
    assert lifecycle.recover_stale(store, profile) is False
    path, _ = orphan(store, profile, exited_pid, stopped=True, failed=False, last_error_code=None)
    before = digest(path)
    assert lifecycle.recover_stale(store, profile) is False
    assert digest(path) == before and not archives(store, profile)


@pytest.mark.parametrize("change", [
    {"pid": True}, {"pid": 0}, {"pid": -1}, {"pid": 1.5}, {"pid": 2**32},
    {"port": True}, {"port": 0}, {"port": 65536}, {"token": {}}, {"token": "short"},
    {"run_id": None}, {"run_id": "x"*32}, {"configuration": "0"*64},
    {"stopped": "false"}, {"unexpected": "synthetic"},
])
def test_malformed_or_foreign_runtime_is_never_retired(tmp_path, exited_pid, change):
    store, profile = synthetic_profile(tmp_path)
    path, _ = orphan(store, profile, exited_pid, **change)
    before = digest(path)
    with pytest.raises(ProductError, match="invalid_runtime_state"):
        lifecycle.recover_stale(store, profile)
    assert digest(path) == before and not archives(store, profile)


@pytest.mark.parametrize("payload", [b"{", b"[]", b"null", b"\xff"])
def test_corrupt_runtime_is_a_static_safe_error(tmp_path, payload):
    store, profile = synthetic_profile(tmp_path)
    path = store.directory(profile.name) / "runtime.json"
    write_json(path, {})
    path.write_bytes(payload)
    before = digest(path)
    with pytest.raises(ProductError, match="invalid_runtime_state"):
        lifecycle.recover_stale(store, profile)
    assert digest(path) == before and not archives(store, profile)


def test_live_or_reused_pid_is_not_a_recovery_grant(tmp_path, monkeypatch):
    store, profile = synthetic_profile(tmp_path)
    path, _ = orphan(store, profile, os.getpid())
    before = digest(path)
    monkeypatch.setattr(subprocess.Popen, "terminate", lambda *_: pytest.fail("unverified PID signalled"))
    monkeypatch.setattr(subprocess.Popen, "kill", lambda *_: pytest.fail("unverified PID signalled"))
    with pytest.raises(ProductError, match="stale_supervisor_alive_or_pid_reused"):
        lifecycle.recover_stale(store, profile)
    assert digest(path) == before and not archives(store, profile)


def test_inaccessible_or_unknown_process_evidence_fails_closed(tmp_path, exited_pid, monkeypatch):
    store, profile = synthetic_profile(tmp_path)
    path, _ = orphan(store, profile, exited_pid)
    before = digest(path)
    def unavailable(pid):
        raise ProductError("stale_process_liveness_unavailable")
    monkeypatch.setattr(lifecycle, "_process_gone", unavailable)
    with pytest.raises(ProductError, match="stale_process_liveness_unavailable"):
        lifecycle.recover_stale(store, profile)
    assert digest(path) == before and not archives(store, profile)


@pytest.mark.parametrize("occupied", ["control", "mcp"])
def test_independent_occupied_port_is_never_stopped_or_rebound(tmp_path, exited_pid, occupied):
    store, profile = synthetic_profile(tmp_path)
    path, state = orphan(store, profile, exited_pid)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", state["port"] if occupied == "control" else profile.port))
        listener.listen()
        before = digest(path)
        expected = "stale_control_port_in_use" if occupied == "control" else "port_in_use_no_process_changed"
        with pytest.raises(ProductError, match=expected):
            lifecycle.recover_stale(store, profile)
        assert listener.fileno() >= 0
        assert digest(path) == before and not archives(store, profile)


@pytest.mark.parametrize("name", ["operation.lock", "launch.lock"])
def test_actual_interprocess_os_lock_blocks_retirement(tmp_path, exited_pid, name):
    store, profile = synthetic_profile(tmp_path)
    path, _ = orphan(store, profile, exited_pid)
    before = digest(path)
    with operation_lock_holder(path.with_name(name)) as owner:
        with pytest.raises(ProductError, match="profile_busy"):
            lifecycle.recover_stale(store, profile)
        assert owner.poll() is None
        assert digest(path) == before and not archives(store, profile)
    assert lifecycle.recover_stale(store, profile) is True


@pytest.mark.parametrize("same_bytes", [False, True])
def test_runtime_changed_immediately_before_retirement_is_preserved(tmp_path, exited_pid, monkeypatch, same_bytes):
    store, profile = synthetic_profile(tmp_path)
    path, state = orphan(store, profile, exited_pid)
    original = lifecycle._archive_stale
    changed_hash = []
    def replace_record(*args, **kwargs):
        write_json(path, state if same_bytes else {**state, "run_id": secrets.token_hex(16)})
        changed_hash.append(digest(path))
        return original(*args, **kwargs)
    monkeypatch.setattr(lifecycle, "_archive_stale", replace_record)
    with pytest.raises(ProductError, match="runtime_state_changed_retry"):
        lifecycle.recover_stale(store, profile)
    assert changed_hash and digest(path) == changed_hash[0]
    assert not archives(store, profile)


def test_runtime_replaced_during_control_probe_is_not_retired(tmp_path, exited_pid, monkeypatch):
    store, profile = synthetic_profile(tmp_path)
    path, state = orphan(store, profile, exited_pid)
    original = lifecycle.control
    calls, replacement = [], []
    def replace_during_probe(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(True)
        if len(calls) == 2:
            write_json(path, {**state, "run_id": secrets.token_hex(16)})
            replacement.append(digest(path))
        return result
    monkeypatch.setattr(lifecycle, "control", replace_during_probe)
    with pytest.raises(ProductError, match="runtime_state_changed_retry"):
        lifecycle.recover_stale(store, profile)
    assert replacement and digest(path) == replacement[0]
    assert not archives(store, profile)


def test_pid_evidence_is_rechecked_before_retirement(tmp_path, exited_pid, monkeypatch):
    store, profile = synthetic_profile(tmp_path)
    path, _ = orphan(store, profile, exited_pid)
    before = digest(path)
    answers = iter([True, False])
    monkeypatch.setattr(lifecycle, "_process_gone", lambda *_: next(answers))
    with pytest.raises(ProductError, match="stale_supervisor_alive_or_pid_reused"):
        lifecycle.recover_stale(store, profile)
    assert digest(path) == before and not archives(store, profile)


def test_concurrent_recovery_has_one_retirement_and_no_record_overwrite(tmp_path, exited_pid):
    store, profile = synthetic_profile(tmp_path)
    path, _ = orphan(store, profile, exited_pid)
    before = digest(path)
    barrier = threading.Barrier(2)
    def recover():
        barrier.wait(timeout=5)
        try:
            return lifecycle.recover_stale(store, profile)
        except ProductError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(recover) for _ in range(2)]
        outcomes = [future.result(timeout=15) for future in futures]
    assert outcomes.count(True) == 1
    assert all(item is True or item is False or item == "profile_busy" for item in outcomes)
    assert len(archives(store, profile)) == 1
    assert digest(archives(store, profile)[0]) == before


def test_archive_filesystem_failure_preserves_record_and_releases_both_locks(tmp_path, exited_pid, monkeypatch):
    store, profile = synthetic_profile(tmp_path)
    path, _ = orphan(store, profile, exited_pid)
    before = digest(path)
    def unavailable(*args, **kwargs):
        raise OSError("synthetic archive failure")
    monkeypatch.setattr(lifecycle.os, "replace", unavailable)
    with pytest.raises(ProductError, match="stale_runtime_archive_failed"):
        lifecycle.recover_stale(store, profile)
    assert digest(path) == before and not archives(store, profile)
    with file_lock(path.with_name("launch.lock")), file_lock(path.with_name("operation.lock")):
        pass


def test_archive_permission_failure_never_moves_record(tmp_path, exited_pid, monkeypatch):
    store, profile = synthetic_profile(tmp_path)
    path, _ = orphan(store, profile, exited_pid)
    before = digest(path)
    original = lifecycle.private_directory
    def reject_history(directory):
        if Path(directory).name == "history":
            raise ProductError("private_permissions_required")
        return original(directory)
    monkeypatch.setattr(lifecycle, "private_directory", reject_history)
    with pytest.raises(ProductError, match="private_permissions_required"):
        lifecycle.recover_stale(store, profile)
    assert digest(path) == before and not archives(store, profile)


def test_unsafe_existing_lock_permissions_are_rejected_without_repair(tmp_path, exited_pid, monkeypatch):
    store, profile = synthetic_profile(tmp_path)
    path, _ = orphan(store, profile, exited_pid)
    before = digest(path)
    lock = path.with_name("operation.lock")
    original = lifecycle.private_permissions
    monkeypatch.setattr(lifecycle, "private_permissions", lambda candidate:
        False if Path(candidate) == lock else original(candidate))
    with pytest.raises(ProductError, match="private_permissions_required"):
        lifecycle.recover_stale(store, profile)
    assert digest(path) == before and not archives(store, profile)


def test_hardlinked_runtime_is_rejected_without_touching_either_name(tmp_path, exited_pid):
    store, profile = synthetic_profile(tmp_path)
    path, _ = orphan(store, profile, exited_pid)
    other = path.with_name("linked-runtime.json")
    os.link(path, other)
    before = digest(path)
    with pytest.raises(ProductError, match="linked_path_refused"):
        lifecycle.recover_stale(store, profile)
    assert digest(path) == digest(other) == before and not archives(store, profile)


def test_interruption_after_atomic_retirement_allows_safe_subsequent_attempt(tmp_path, exited_pid, monkeypatch):
    store, profile = synthetic_profile(tmp_path)
    path, _ = orphan(store, profile, exited_pid)
    before = digest(path)
    original = lifecycle.os.replace
    def interrupt_after_move(*args, **kwargs):
        original(*args, **kwargs)
        raise KeyboardInterrupt()
    with monkeypatch.context() as patch:
        patch.setattr(lifecycle.os, "replace", interrupt_after_move)
        with pytest.raises(KeyboardInterrupt):
            lifecycle.recover_stale(store, profile)
    assert not path.exists() and len(archives(store, profile)) == 1
    assert digest(archives(store, profile)[0]) == before
    assert lifecycle.recover_stale(store, profile) is False
    with file_lock(path.with_name("launch.lock")), file_lock(path.with_name("operation.lock")):
        pass


def wait_until(predicate, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.05)
    pytest.fail("owned synthetic lifecycle condition did not complete before its deadline")


@pytest.mark.parametrize("pin", ["matching", "mismatched", "omitted"])
def test_child_supervisor_rejects_a_changed_configuration_pin(tmp_path, monkeypatch, pin):
    store, profile = synthetic_profile(tmp_path)
    calls = []
    class CheckedSupervisor:
        def __init__(self, actual, selected):
            assert actual.home == store.home and selected == profile
            calls.append("constructed")
        def run(self, **kwargs):
            calls.append(kwargs)
            return 0
    monkeypatch.setattr(lifecycle, "Supervisor", CheckedSupervisor)
    arguments = ["oomp.product.lifecycle", "--home", str(store.home), "--profile", profile.name]
    if pin != "omitted":
        arguments.extend(["--expected-configuration", profile.identity if pin == "matching" else "0"*64])
    monkeypatch.setattr(sys, "argv", arguments)
    assert lifecycle.main() == (1 if pin == "mismatched" else 0)
    assert calls == ([] if pin == "mismatched" else ["constructed", {"background": True}])


def test_initial_supervisor_log_failure_closes_control_socket_and_releases_os_lock(tmp_path, monkeypatch):
    store, profile = synthetic_profile(tmp_path)
    supervisor = lifecycle.Supervisor(store, profile)
    original = supervisor.log
    def fail_initial_log(code, role=None):
        if code == "supervisor_start":
            raise OSError("synthetic logging failure")
        return original(code, role)
    monkeypatch.setattr(supervisor, "log", fail_initial_log)
    monkeypatch.setattr(supervisor, "spawn", lambda *_: pytest.fail("service started after initial logging failure"))
    assert supervisor.run(background=True) == 1
    runtime = read_json(store.directory(profile.name) / "runtime.json")
    assert runtime.get("stopped") is True and runtime.get("failed") is True
    assert lifecycle.port_available(runtime["port"])
    assert lifecycle.control(store, profile.name).get("state") == "failed"
    with file_lock(store.directory(profile.name) / "operation.lock"):
        pass


@pytest.mark.parametrize("failure", ["probe", "schema", "context"])
def test_recovery_is_not_reported_successful_before_all_normal_probes_pass(tmp_path, monkeypatch, failure):
    from oomp.storage.migrations import SCHEMA_VERSION
    store, profile = synthetic_profile(tmp_path, context_enabled=True)
    report = {"profile": profile.name, "state": "running", "ownership_verified": True,
        "stale_runtime_recovered": True,
        "services": {role: {"ready": True, "alive": True} for role in ("mcp", "mind")}}
    monkeypatch.setattr(lifecycle, "control", lambda *_: {"state": "unverified"})
    monkeypatch.setattr(lifecycle, "start", lambda *args, **kwargs: report)
    def probe(*args):
        if failure == "probe":
            raise ProductError("mcp_handshake_or_authorization_failed")
        return {"schema_version": SCHEMA_VERSION if failure == "context" else -1}, set()
    monkeypatch.setattr(start, "probe_runtime", probe)
    class SilentUI:
        def __init__(self):
            self.rows = []
        def welcome(self):
            self.rows.append("welcome")
        def line(self, *args):
            self.rows.append(args)
    ui = SilentUI()
    args = SimpleNamespace(home=str(store.home), profile=profile.name, json=False,
        project=None, replace_default=False, remember=False, approve_trace_integration=False)
    with pytest.raises(ProductError):
        start.command(args, ui)
    assert ui.rows == []


def test_background_probe_failure_signals_only_its_retained_launch_handle(tmp_path, monkeypatch):
    store, profile = synthetic_profile(tmp_path)
    calls, replacement = [], []
    runtime = store.directory(profile.name) / "runtime.json"
    class OwnedHandle:
        finished = False
        def poll(self):
            return 0 if self.finished else None
        def terminate(self):
            calls.append("retained-terminate")
        def wait(self, timeout):
            assert timeout == 5
            calls.append("retained-wait")
            self.finished = True
            return 0
        def kill(self):
            pytest.fail("unexpected extra signal")
    owned = OwnedHandle()
    monkeypatch.setattr(lifecycle.subprocess, "Popen", lambda *args, **kwargs: owned)
    monkeypatch.setattr(lifecycle, "stop", lambda *_: pytest.fail("mutable runtime selected a shutdown target"))
    monkeypatch.setattr(lifecycle.os, "kill", lambda *_: pytest.fail("a runtime PID was signalled"))
    def replaced_control(*args, **kwargs):
        orphan(store, profile, os.getpid())
        replacement.append(digest(runtime))
        raise ProductError("runtime_state_changed_retry")
    monkeypatch.setattr(lifecycle, "control", replaced_control)
    with pytest.raises(ProductError, match="runtime_state_changed_retry"):
        lifecycle._start_background(store, profile)
    assert calls == ["retained-terminate", "retained-wait"]
    assert owned.finished and replacement and digest(runtime) == replacement[0]


@pytest.mark.parametrize("code,guidance", [
    ("stale_supervisor_alive_or_pid_reused", "Owner exit is unproven"),
    ("runtime_state_changed_retry", "Runtime state changed"),
    ("stale_runtime_archive_failed", "Private runtime archival failed"),
])
def test_cli_recovery_error_uses_static_actionable_guidance_without_exception_text(monkeypatch, capsys, code, guidance):
    from oomp.cli import main
    def rejected(*args, **kwargs):
        error = ProductError(code)
        error.args = ("synthetic-runtime-token-do-not-display",)
        raise error
    monkeypatch.setattr(start, "command", rejected)
    assert main(["start", "--json"]) == 1
    captured = capsys.readouterr()
    if "synthetic-runtime-token-do-not-display" in captured.out + captured.err:
        pytest.fail("private exception detail was disclosed")
    result = json.loads(captured.out)
    assert result.get("ok") is False and result.get("code") == code
    assert guidance in result.get("recommendation", "")
    assert "Preserve" in result.get("recommendation", "") or "preserve" in result.get("recommendation", "")


def test_concurrent_start_has_one_owned_supervisor_and_one_worker_set(tmp_path, monkeypatch):
    pytest.importorskip("mcp", reason="install [mcp] for actual synthetic concurrent startup")
    store, profile = synthetic_profile(tmp_path)
    original_popen = subprocess.Popen
    owned = []
    def retain_supervisor(command, *args, **kwargs):
        process = original_popen(command, *args, **kwargs)
        if isinstance(command, (list, tuple)) and "oomp.product.lifecycle" in command:
            owned.append(process)
        return process
    monkeypatch.setattr(lifecycle.subprocess, "Popen", retain_supervisor)
    barrier = threading.Barrier(2)
    def launch():
        barrier.wait(timeout=5)
        try:
            report = start.launch(store, profile)
            return report.get("state")
        except ProductError as error:
            return error.code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(launch) for _ in range(2)]
            outcomes = [future.result(timeout=100) for future in futures]
        assert "running" in outcomes
        assert all(item in {"running", "profile_busy"} for item in outcomes)
        assert len(owned) == 1
        status = lifecycle.control(store, profile.name)
        assert status.get("ownership_verified") and status.get("state") == "running"
        services = status.get("services", {})
        assert set(services) == {"mcp", "mind"}
        assert len({item["pid"] for item in services.values()}) == 2
        assert all(item.get("ready") and item.get("alive") for item in services.values())
        assert not archives(store, profile)
    finally:
        try:
            lifecycle.stop(store, profile.name)
        finally:
            for process in owned:
                if process.poll() is None:
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                process.wait(timeout=10)


def test_real_supervisor_crash_is_recovered_by_saved_default_start(tmp_path, monkeypatch):
    pytest.importorskip("mcp", reason="install [mcp] for actual synthetic crash/restart acceptance")
    store, profile = synthetic_profile(tmp_path, context_enabled=True)
    protected = [store.directory(profile.name) / "active.json", store.directory(profile.name) / "secrets.json"]
    before = {path: digest(path) for path in protected}
    owned = []
    original_popen = subprocess.Popen
    def retain_supervisor(command, *args, **kwargs):
        process = original_popen(command, *args, **kwargs)
        if isinstance(command, (list, tuple)) and "oomp.product.lifecycle" in command:
            owned.append(process)
        return process
    monkeypatch.setattr(lifecycle.subprocess, "Popen", retain_supervisor)
    runtime = store.directory(profile.name) / "runtime.json"
    old_child_pids = []
    try:
        first = start.launch(store, profile)
        assert first.get("state") == "running" and first.get("mcp_verified")
        assert first.get("database_ready") and first.get("context_verified")
        assert len(owned) == 1
        old_record = read_json(runtime)
        old_id = old_record["run_id"]
        old_control_port = old_record["port"]
        old_child_pids = [item["pid"] for item in first["services"].values()]
        again = start.launch(store, profile)
        assert again.get("ownership_verified") and len(owned) == 1
        assert read_json(runtime)["run_id"] == old_id
        # This is the retained test-created supervisor handle, never a disk PID.
        owned[0].kill()
        owned[0].wait(timeout=5)
        wait_until(lambda: all(lifecycle._process_gone(pid) for pid in old_child_pids))
        wait_until(lambda: lifecycle.port_available(profile.port))
        # Linux TIME_WAIT after the earlier authenticated control exchanges can
        # outlive the listener. Do not weaken the product's strict bind probe;
        # wait for the synthetic fixture to meet its required admission state.
        wait_until(lambda: lifecycle.port_available(old_control_port), seconds=90)
        assert read_json(runtime).get("stopped") is False
        old_hash = digest(runtime)
        selection = store.home.parent / "startup" / "selection.json"
        start.remember(store, profile, path=selection)
        environment = {**os.environ, "OOMP_PROFILE_HOME": str(store.home)}
        command = [sys.executable, "-I", "-m", "oomp", "start", "--json"]
        process = original_popen(command, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
        try:
            stdout, stderr = process.communicate(timeout=100)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
        assert process.returncode == 0, "saved-default synthetic start failed"
        report = json.loads(stdout)
        assert report.get("stale_runtime_recovered") is True
        assert report.get("mcp_verified") and report.get("database_ready") and report.get("context_verified")
        assert report.get("ownership_verified") and report.get("state") == "running"
        assert set(report.get("services", {})) == {"mcp", "mind"}
        assert all(item.get("ready") and item.get("alive") for item in report["services"].values())
        assert read_json(runtime)["run_id"] != old_id
        assert len(archives(store, profile)) == 1 and digest(archives(store, profile)[0]) == old_hash
        current_token = read_json(runtime)["token"].encode()
        if current_token in stdout + stderr:
            pytest.fail("a control token was disclosed by the start command")
        assert_preserved(before)
        assert lifecycle.stop(store, profile.name).get("state") == "stopped"
        restarted = start.launch(store, profile)
        assert restarted.get("mcp_verified") and not restarted.get("stale_runtime_recovered")
        assert len(archives(store, profile)) == 1
    finally:
        try:
            lifecycle.stop(store, profile.name)
        finally:
            for process in owned:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=10)
    assert all(lifecycle._process_gone(pid) for pid in old_child_pids)
    assert lifecycle.port_available(profile.port)
    assert_preserved(before)
