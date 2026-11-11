"""Owned synthetic child failures, finite diagnostics and bounded recovery."""
from __future__ import annotations

import io
import json
import subprocess
import sys
import threading
import time
import types

import pytest

from oomp.product import lifecycle, trace_service
from oomp.product.child_status import checked_failure, checked_status, failure_detail
from oomp.product.safety import ProductError, write_json
from test_product_profiles import setup_profile


def test_empty_lock_contention_never_writes_into_another_owners_locked_byte(tmp_path, monkeypatch):
    from oomp.product import safety
    safety.restrict(tmp_path)
    path = tmp_path/"startup.lock"
    path.touch()
    safety.restrict(path)
    waiting, attempted, done = threading.Event(), threading.Event(), threading.Event()
    outcomes = []
    original = safety.os.fdopen
    class Handle:
        def __init__(self, stream): self.stream = stream
        def __getattr__(self, name): return getattr(self.stream, name)
        def write(self, value):
            if threading.current_thread().name == "lock-contender":
                waiting.set()
                assert attempted.wait(5)
            return self.stream.write(value)
    monkeypatch.setattr(safety.os, "fdopen", lambda *a, **k: Handle(original(*a, **k)))
    def contender():
        try:
            with safety.file_lock(path): outcomes.append("owned")
        except ProductError as error: outcomes.append(error.code)
        except BaseException as error: outcomes.append(type(error).__name__)
        finally: done.set()
    worker = threading.Thread(target=contender, name="lock-contender")
    worker.start()
    try:
        assert waiting.wait(5)
        try:
            with safety.file_lock(path):
                outcomes.append("owned")
                attempted.set()
                assert done.wait(5)
        except ProductError as error:
            outcomes.append(error.code)
        finally:
            attempted.set()
    finally:
        attempted.set()
        worker.join(6)
    assert not worker.is_alive()
    assert sorted(outcomes) == ["owned", "profile_busy"]
    assert path.read_bytes() == b"0" and safety.private_permissions(path)


class Process:
    pid = 123
    def __init__(self, rows=(), code=None):
        self.stdout = io.BytesIO(b"".join(json.dumps(row).encode()+b"\n" for row in rows))
        self.code = code
    def poll(self):
        return self.code


def supervisor(tmp_path, process=None):
    store, profile = setup_profile(tmp_path)
    managed = lifecycle.Supervisor(store, profile)
    process = process or Process()
    managed.children["publication"] = process
    managed.health["publication"] = {"ready": True, "heartbeat": time.monotonic(),
        "progress": time.monotonic(), "stage": "reconcile"}
    return managed, process


def test_fatal_status_is_immediately_unready_even_with_later_heartbeat(tmp_path):
    managed, process = supervisor(tmp_path, Process([
        {"code": "service_failed", "stage": "reconcile", "reason": "mongo_connection_failed"},
        {"code": "heartbeat"}, {"code": "work_complete"}]))
    managed.reader("publication", process)
    snapshot = managed.snapshot()
    assert not snapshot["services"]["publication"]["ready"]
    assert snapshot["services"]["publication"]["alive"]
    detail = managed.first_failure(snapshot)
    assert detail == failure_detail("publication", "child_reported_failure", "reconcile", "mongo_connection_failed")


@pytest.mark.parametrize("code,heartbeat,progress,kind", [
    (7, 0, 0, "process_exit"), (None, 20, 0, "heartbeat_timeout"),
    (None, 0, 181, "progress_timeout")])
def test_exit_heartbeat_and_progress_are_distinct(tmp_path, code, heartbeat, progress, kind):
    managed, process = supervisor(tmp_path, Process(code=code))
    managed.health["publication"].update(heartbeat=time.monotonic()-heartbeat,
        progress=time.monotonic()-progress)
    detail = managed.first_failure(managed.snapshot())
    assert detail["kind"] == kind and detail["exit_code"] == code


@pytest.mark.parametrize("bad", [
    {"code": "service_failed", "reason": "SYNTHETIC_SECRET"},
    {"code": "service_failed", "stage": []},
    {"code": "heartbeat", "token": "SYNTHETIC_SECRET"},
    {"code": "work_complete", "completed": True},
    {"code": ["service_failed"]}])
def test_child_diagnostics_reject_untrusted_values_without_echo(tmp_path, bad):
    managed, process = supervisor(tmp_path, Process([bad]))
    managed.reader("publication", process)
    detail = managed.first_failure(managed.snapshot())
    assert detail["reason"] == "invalid_child_status"
    assert "SYNTHETIC_SECRET" not in json.dumps(managed.snapshot())


def test_warning_keeps_readiness_but_cannot_fake_completed_progress(tmp_path):
    managed, process = supervisor(tmp_path, Process([
        {"code": "work_warning", "stage": "reconcile", "reason": "mongo_connection_failed", "retry_attempt": 1}]))
    progress = managed.health["publication"]["progress"]
    managed.reader("publication", process)
    assert managed.snapshot()["services"]["publication"]["ready"]
    assert managed.health["publication"]["progress"] == progress
    managed.health["publication"]["progress"] -= 181
    assert managed.first_failure(managed.snapshot())["kind"] == "progress_timeout"


def test_failure_survives_shutdown_metadata_and_safe_recovery_parser(tmp_path):
    managed, _ = supervisor(tmp_path)
    detail = failure_detail("publication", "child_reported_failure", "reconcile", "mongo_connection_failed", 7)
    state = {"pid": 123, "port": 23456, "token": "X"*43, "run_id": "a"*32,
        "configuration": managed.profile.identity, "stopped": True, "failed": True,
        "last_error_code": "owned_service_crashed_or_unresponsive", "failure": detail}
    path = managed.directory/"runtime.json"
    write_json(path, state)
    assert lifecycle.control(managed.store, managed.profile.name)["failure"] == detail
    assert lifecycle._runtime_snapshot(path, managed.profile, allow_stopped=True)[0] == state
    managed.log("child_exit", "publication", failure=detail)
    assert lifecycle.logs(managed.store, managed.profile.name)[-1]["failure"] == detail
    assert "X"*43 not in json.dumps(lifecycle.logs(managed.store, managed.profile.name))
    write_json(path, {**state, "failure": {**detail, "reason": "SYNTHETIC_SECRET"}})
    with pytest.raises(ProductError, match="invalid_runtime_state"):
        lifecycle.control(managed.store, managed.profile.name)


def test_actual_crashing_owned_child_has_sanitized_role_stage_and_exit(tmp_path):
    managed, _ = supervisor(tmp_path)
    command = "import json; print(json.dumps({'code':'service_failed','stage':'reconcile','reason':'mongo_connection_failed'}),flush=True); raise SystemExit(7)"
    process = subprocess.Popen([sys.executable, "-I", "-c", command], stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL)
    managed.children["publication"] = process
    try:
        managed.reader("publication", process)
        assert process.wait(5) == 7
        detail = managed.first_failure(managed.snapshot())
        assert detail == failure_detail("publication", "child_reported_failure", "reconcile", "mongo_connection_failed", 7)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(5)
        process.stdout.close()


class Stop:
    def __init__(self): self.stopped = False; self.waits = []
    def is_set(self): return self.stopped
    def set(self): self.stopped = True
    def wait(self, seconds):
        if threading.current_thread() is not threading.main_thread():
            return True
        self.waits.append(seconds)
        return self.stopped


def bridge_fixture(monkeypatch, errors):
    """No external host import or database/socket operation in unit tests."""
    mongo_error = type("PyMongoError", (Exception,), {})
    connection_error = type("ConnectionFailure", (mongo_error,), {})
    mongo = types.ModuleType("pymongo")
    errors_module = types.ModuleType("pymongo.errors")
    errors_module.ConnectionFailure, errors_module.PyMongoError = connection_error, mongo_error
    class Client:
        def __init__(self, *args, **kwargs): self.admin = self
        def command(self, *args): pass
        def __getitem__(self, name): return object()
        def close(self): pass
    mongo.MongoClient = Client
    publisher_module = types.ModuleType("backend.services.oomp_publisher")
    class Publisher:
        def __init__(self, *args): pass
        def reconcile(self, **kwargs):
            if errors:
                error = errors.pop(0)
                if error == "connection": raise connection_error("SYNTHETIC_SECRET_URI")
                if error == "operation": raise mongo_error("SYNTHETIC_SECRET_SOURCE")
                raise RuntimeError("SYNTHETIC_SECRET_UNKNOWN")
            return {"next_after_id": None}
        def drain(self, **kwargs): return {"results": []}
    publisher_module.Publisher = Publisher
    config_module = types.ModuleType("backend.services.oomp_config")
    config_module.get_configuration = lambda: types.SimpleNamespace(mode="retrieve_and_ingest")
    work_module = types.ModuleType("backend.services.oomp_diagnostics")
    def work(publisher, **kwargs):
        while True:
            publisher.reconcile()
            yield {"delivery": publisher.drain()}
    work_module.work = work
    for name, module in {"pymongo": mongo, "pymongo.errors": errors_module,
        "backend.services.oomp_publisher": publisher_module,
        "backend.services.oomp_config": config_module,
        "backend.services.oomp_diagnostics": work_module}.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setenv("TEST_MONGO", "mongodb://127.0.0.1:1/")
    return Stop()


def test_transient_mongo_failure_recovers_with_bounded_backoff_and_true_progress(tmp_path, monkeypatch):
    stop = bridge_fixture(monkeypatch, ["connection", "connection"])
    events = []
    def emit(code, **fields):
        events.append({"code": code, **fields})
        if code == "work_complete": stop.set()
    trace_service.run(str(tmp_path), "TEST_MONGO", "synthetic", stop, emit)
    assert [row["code"] for row in events] == ["ready", "work_warning", "work_warning", "work_complete"]
    assert stop.waits == [.5, 1.0]
    assert all(checked_status(row) for row in events)
    assert "SYNTHETIC_SECRET" not in json.dumps(events)


@pytest.mark.parametrize("errors,reason,waits", [
    (["connection"]*3, "mongo_connection_failed", [.5, 1.0]),
    (["operation"], "mongo_operation_failed", []),
    (["unknown"], "unknown_error", [])])
def test_exhausted_or_permanent_bridge_failure_is_not_retried_forever(tmp_path, monkeypatch, errors, reason, waits):
    stop = bridge_fixture(monkeypatch, errors)
    events = []
    with pytest.raises(trace_service.PublicationFailure) as caught:
        trace_service.run(str(tmp_path), "TEST_MONGO", "synthetic", stop, lambda code, **fields: events.append({"code": code, **fields}))
    assert caught.value.stage == "reconcile" and caught.value.reason == reason
    assert stop.waits == waits
    assert not any(row["code"] == "work_complete" for row in events)
    assert "SYNTHETIC_SECRET" not in str(caught.value)
