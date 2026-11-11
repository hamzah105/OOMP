"""Foreground supervision with authenticated loopback control and held OS locks.

Only retained Popen handles may be terminated. PIDs in state are informational;
stale state or PID reuse never authorizes a signal to an unrelated process.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import socket
import socketserver
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

from .discovery import project_fingerprint
from .child_status import CODES, checked_failure, checked_status, failure_detail
from .profiles import ProfileStore
from .safety import (ProductError, file_lock, private_directory, private_permissions,
                     read_json, restrict, safe_path, write_json)

_CODES = CODES


def child_environment(store, profile):
    environment = {k: v for k, v in os.environ.items() if k in {
        "PATH", "SystemRoot", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LOCALAPPDATA", "APPDATA",
        "USERPROFILE", "HOME", "LANG", "LC_ALL", "COMSPEC", "PATHEXT"}}
    environment.update(store.host_environment(profile))
    if profile.publication and profile.mongo_uri_env:
        environment[profile.mongo_uri_env] = os.environ.get(profile.mongo_uri_env, "")
    environment["PYTHONUNBUFFERED"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["NO_COLOR"] = "1"
    return environment


def process_options():
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def port_available(port):
    with socket.socket() as connection:
        if os.name == "nt":
            connection.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            connection.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def publication_uri(profile):
    value = os.environ.get(profile.mongo_uri_env or "", "")
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "mongodb" or parsed.hostname not in {"127.0.0.1", "::1"}
                or "," in parsed.netloc or parsed.fragment or parsed.port is not None and not 1 <= parsed.port <= 65535):
            raise ValueError()
    except ValueError:
        raise ProductError("explicit_local_mongo_reference_required") from None
    return value


def control(store, name, operation="status"):
    path = store.directory(name) / "runtime.json"
    if not path.exists():
        return {"profile": name, "state": "stopped", "ownership_verified": False, "services": {}}
    try:
        state = read_json(path)
    except FileNotFoundError:
        return {"profile": name, "state": "stopped", "ownership_verified": False, "services": {}}
    except (ValueError, UnicodeError) as error:
        if isinstance(error, ProductError):
            raise
        raise ProductError("invalid_runtime_state") from None
    if not isinstance(state, dict):
        raise ProductError("invalid_runtime_state")
    if state.get("stopped") is True:
        result = {"profile": name, "state": "failed" if state.get("failed") else "stopped",
                "ownership_verified": False, "services": {}, "last_error_code": state.get("last_error_code")}
        if "failure" in state:
            try:
                result["failure"] = checked_failure(state["failure"])
            except (ValueError, TypeError):
                raise ProductError("invalid_runtime_state") from None
        return result
    if (type(state.get("port")) is not int or not 1024 <= state["port"] <= 65535
            or not isinstance(state.get("token"), str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{43}", state["token"])
            or not isinstance(state.get("run_id"), str)
            or not re.fullmatch(r"[a-f0-9]{32}", state["run_id"])):
        raise ProductError("invalid_runtime_state")
    try:
        with socket.create_connection(("127.0.0.1", state["port"]), timeout=2) as connection:
            connection.settimeout(2)
            connection.sendall(json.dumps({"operation": operation, "token": state["token"],
                                           "run_id": state["run_id"]}).encode()+b"\n")
            with connection.makefile("rb") as stream:
                raw = stream.readline(16385)
        if len(raw) > 16384:
            raise ValueError()
        result = json.loads(raw)
        if result.pop("run_id", None) != state["run_id"] or result.get("profile") != name:
            raise ValueError()
        return result
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {"profile": name, "state": "unverified", "ownership_verified": False,
                "services": {}, "last_error_code": "stale_state_or_supervisor_unavailable"}


@contextmanager
def _checked_lock(path):
    # file_lock creates private new files, but deliberately restricts existing
    # ones. Recovery must reject unsafe existing permissions rather than repair
    # evidence before deciding whether it is safe to retire it.
    path = safe_path(path)
    private_directory(path.parent)
    if path.exists() and not private_permissions(path):
        raise ProductError("private_permissions_required")
    with file_lock(path):
        yield


def _process_gone(pid):
    """Definite exit only; never request termination rights or send a signal.

    POSIX signal zero is only a presence/permission probe. It must never be
    used on Windows, where os.kill has different termination semantics.
    """
    if os.name == "nt":
        import ctypes as c
        from ctypes import wintypes as w
        api = c.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        api.OpenProcess.restype = w.HANDLE
        api.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        api.WaitForSingleObject.restype = w.DWORD
        api.CloseHandle.argtypes = [w.HANDLE]
        handle = api.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE only
        if not handle:
            if c.get_last_error() == 87:  # positive PID no longer exists
                return True
            raise ProductError("stale_process_liveness_unavailable")
        try:
            result = api.WaitForSingleObject(handle, 0)
            if result in (0, 258):  # signalled exit / WAIT_TIMEOUT (still alive)
                return result == 0
            raise ProductError("stale_process_liveness_unavailable")
        finally:
            api.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except (OSError, OverflowError):
        raise ProductError("stale_process_liveness_unavailable") from None
    return False


def _runtime_snapshot(path, profile, *, allow_stopped=False):
    path = safe_path(path)
    try:
        before = path.stat()
        state = read_json(path)
        with path.open("rb") as handle:
            raw = handle.read(65537)
        after = path.stat()
        identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if identity(before) != identity(after):
            raise ProductError("runtime_state_changed_retry")
        if len(raw) > 65536 or json.loads(raw) != state:
            raise ProductError("runtime_state_changed_retry")
        required = {"pid", "port", "token", "run_id", "configuration", "stopped"}
        if (not isinstance(state, dict) or not required <= set(state)
                or set(state) - required - {"failed", "last_error_code", "failure"}
                or type(state.get("pid")) is not int or not 0 < state["pid"] <= 0xFFFFFFFF
                or type(state.get("port")) is not int or not 1024 <= state["port"] <= 65535
                or not isinstance(state.get("token"), str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{43}", state["token"])
                or not isinstance(state.get("run_id"), str)
                or not re.fullmatch(r"[a-f0-9]{32}", state["run_id"])
                or not isinstance(state.get("configuration"), str)
                or not re.fullmatch(r"[a-f0-9]{64}", state["configuration"])
                or type(state.get("stopped")) is not bool
                or state["stopped"] and not allow_stopped
                or not state["stopped"] and state["configuration"] != profile.identity
                or "failed" in state and type(state["failed"]) is not bool
                or state.get("last_error_code") is not None and (
                    not isinstance(state["last_error_code"], str)
                    or not re.fullmatch(r"[a-z0-9_]{1,128}", state["last_error_code"]))):
            raise ProductError("invalid_runtime_state")
        if "failure" in state:
            checked_failure(state["failure"])
        if not private_permissions(path):
            raise ProductError("private_permissions_required")
        return state, (identity(after), raw)
    except FileNotFoundError:
        raise ProductError("runtime_state_changed_retry") from None
    except (ValueError, UnicodeError) as error:
        if isinstance(error, ProductError):
            raise
        raise ProductError("invalid_runtime_state") from None
    except OSError:
        raise ProductError("stale_runtime_unreadable") from None


def _stale_evidence(store, profile, snapshot):
    path = store.directory(profile.name) / "runtime.json"
    if _runtime_snapshot(path, profile) != snapshot:
        raise ProductError("runtime_state_changed_retry")
    if store.load(profile.name) != profile:
        raise ProductError("configuration_changed_retry")
    if not _process_gone(snapshot[0]["pid"]):
        # Includes PID reuse. A live PID is never an automatic recovery grant.
        raise ProductError("stale_supervisor_alive_or_pid_reused")
    if not port_available(snapshot[0]["port"]):
        raise ProductError("stale_control_port_in_use")
    if profile.transport == "streamable-http" and not port_available(profile.port):
        raise ProductError("port_in_use_no_process_changed")
    if control(store, profile.name)["state"] != "unverified":
        raise ProductError("runtime_state_changed_retry")
    # Probes can take time. A different unverified record is still a race, not
    # permission to archive the replacement. All compliant writers also hold
    # operation.lock; recheck the bytes and filesystem identity at retirement.
    if _runtime_snapshot(path, profile) != snapshot:
        raise ProductError("runtime_state_changed_retry")


def _archive_stale(store, profile, snapshot):
    """Atomic retirement under both locks; tokens never leave private storage."""
    directory = store.directory(profile.name)
    try:
        history = private_directory(directory / "history")
        target = history / ("recovery-" + secrets.token_hex(12))
        # Exclusive directory creation: never overwrite a previous receipt.
        target.mkdir(mode=0o700)
        restrict(target)
        private_directory(target)
        _stale_evidence(store, profile, snapshot)
        os.replace(safe_path(directory / "runtime.json"), safe_path(target / "runtime.json"))
    except OSError:
        raise ProductError("stale_runtime_archive_failed") from None


def _recover_stale_locked(store, profile):
    snapshot = _runtime_snapshot(store.directory(profile.name) / "runtime.json", profile)
    with _checked_lock(store.directory(profile.name) / "operation.lock"):
        _stale_evidence(store, profile, snapshot)
        _archive_stale(store, profile, snapshot)
    return True


def recover_stale(store, profile):
    """Retire only proven dead state. This does not start or change a profile."""
    with _checked_lock(store.directory(profile.name) / "launch.lock"):
        current = control(store, profile.name)
        if current["state"] != "unverified":
            return False
        return _recover_stale_locked(store, profile)


def stop(store, name):
    result = control(store, name, "stop")
    if result["state"] == "unverified":
        raise ProductError("ownership_unverified_no_process_signalled")
    if not result.get("ownership_verified"):
        return result
    deadline = time.monotonic()+20
    while time.monotonic() < deadline:
        time.sleep(.1)
        result = control(store, name)
        # The control socket closes before the final record/OS lock. A temporary
        # connection failure is neither proof of shutdown nor a stale-PID grant.
        if result["state"] in {"stopped", "failed"} and not result.get("ownership_verified"):
            try:
                with file_lock(store.directory(name) / "operation.lock"):
                    return result
            except ProductError as error:
                if error.code != "profile_busy":
                    raise
    raise ProductError("shutdown_timeout")


def logs(store, name, limit=40):
    path = safe_path(store.directory(name) / "operations.log")
    if not path.exists():
        return []
    from .safety import private_permissions
    if not private_permissions(path):
        raise ProductError("private_permissions_required")
    # Logging is capped at 1 MiB; never read an unbounded user-supplied file.
    with path.open("rb") as handle:
        handle.seek(max(0, path.stat().st_size-32768))
        lines = handle.read(32768).splitlines()
    allowed = {"supervisor_start", "supervisor_ready", "supervisor_stop", "service_failed",
               "child_exit", "work_warning", "startup_failed", "forced_stop"}
    result = []
    for raw in lines:
        try:
            item = json.loads(raw)
            if item.get("code") in allowed and item.get("role") in {None, "mcp", "mind", "publication"}:
                row = {k: item[k] for k in ("at", "code", "role") if k in item}
                if "failure" in item:
                    row["failure"] = checked_failure(item["failure"])
                result.append(row)
        except (ValueError, TypeError):
            continue
    return result[-limit:]


class Supervisor:
    def __init__(self, store, profile):
        self.store, self.profile = store, profile
        self.directory = store.directory(profile.name)
        self.children = {}
        self.readers = {}
        self.health = {}
        self.guard = threading.Lock()
        self.shutdown = threading.Event()
        self.run_id = secrets.token_hex(16)
        self.token = secrets.token_urlsafe(32)
        self.state = "starting"
        self.failed = False
        self.last_error = None
        self.failure = None
        self.starting_role = "supervisor"

    def log(self, code, role=None, *, failure=None):
        path = safe_path(self.directory / "operations.log")
        if path.exists() and path.stat().st_size >= 1048576:
            old = safe_path(self.directory / "operations.previous.log")
            os.replace(path, old)
        descriptor = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        restrict(path)
        entry = {"at": datetime.now(timezone.utc).isoformat(), "code": code, "role": role}
        if failure is not None:
            entry["failure"] = checked_failure(failure)
        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry)+"\n")

    def snapshot(self):
        with self.guard:
            services = {}
            for role, process in self.children.items():
                info = self.health.get(role, {})
                age = time.monotonic()-info.get("heartbeat", time.monotonic())
                progress_age = time.monotonic()-info.get("progress", time.monotonic())
                exit_code = process.poll()
                alive = exit_code is None
                services[role] = {"pid": process.pid, "alive": alive,
                    "ready": bool(info.get("ready")) and not info.get("fatal") and alive and age < 12 and (role == "mcp" or progress_age < 180),
                    "heartbeat_age_seconds": round(age, 2), "last_error_code": info.get("error"),
                    "exit_code": exit_code, "stage": info.get("stage", "supervision"),
                    "reason": info.get("reason")}
                services[role]["progress_age_seconds"] = round(progress_age, 2)
        return {"profile": self.profile.name, "state": self.state, "ownership_verified": True,
                "services": services, "last_error_code": self.last_error, "run_id": self.run_id,
                "stdio": "host-owned; use oomp connect" if self.profile.transport == "stdio" else None,
                "external_services": "host API, MongoDB and Ollama are independently owned",
                **({"failure": self.failure} if self.failure is not None else {})}

    def first_failure(self, snapshot):
        # A reported fatal error is decisive even if shutdown/foreign library
        # threads keep the owned process alive. Heartbeats cannot erase it.
        candidates = [(role, item) for role, item in snapshot["services"].items() if not item["ready"]]
        candidates.sort(key=lambda pair: not self.health.get(pair[0], {}).get("fatal", False))
        for role, item in candidates:
            if self.health.get(role, {}).get("fatal"):
                kind = "protocol_failure" if item["last_error_code"] == "invalid_child_status" else "child_reported_failure"
                reason = item["reason"] or "unknown_error"
            elif item["exit_code"] is not None:
                kind, reason = "process_exit", "process_exited"
            elif item["heartbeat_age_seconds"] >= 12:
                kind, reason = "heartbeat_timeout", "heartbeat_timeout"
            elif role != "mcp" and item["progress_age_seconds"] >= 180:
                kind, reason = "progress_timeout", "progress_timeout"
            else:
                kind, reason = "child_not_ready", "child_not_ready"
            return failure_detail(role, kind, item["stage"], reason, item["exit_code"])
        return None

    def reader(self, role, process):
        while True:
            raw = process.stdout.readline(4097)
            if not raw:
                return
            try:
                if len(raw) > 4096:
                    raise ValueError()
                value = checked_status(json.loads(raw))
                code = value.get("code")
                if code not in _CODES:
                    raise ValueError()
                with self.guard:
                    entry = self.health[role]
                    entry["heartbeat"] = time.monotonic()
                    if "stage" in value:
                        entry["stage"] = value["stage"]
                    if code == "ready":
                        entry["ready"] = True
                        entry["progress"] = time.monotonic()
                    if code == "work_complete":
                        entry["progress"] = time.monotonic()
                        if not value.get("failed") and not value.get("lost_lease") and not entry.get("fatal"):
                            entry.pop("error", None)
                            entry.pop("reason", None)
                    if code in {"service_failed", "work_warning"}:
                        entry["error"] = code
                        entry["reason"] = value.get("reason", "unknown_error")
                    if code == "service_failed":
                        entry["fatal"] = True
                        entry["ready"] = False
                if code in {"service_failed", "work_warning"}:
                    detail = failure_detail(role, "child_reported_failure" if code == "service_failed" else "work_warning", value.get("stage", "supervision"),
                                            value.get("reason", "unknown_error"), process.poll())
                    self.log(code, role, failure=detail)
            except (ValueError, TypeError, AttributeError):
                with self.guard:
                    self.health[role]["error"] = "invalid_child_status"
                    self.health[role].update(fatal=True, ready=False, reason="invalid_child_status", stage="supervision")
                return

    def spawn(self, role):
        self.starting_role = role
        profile = self.profile
        environment = child_environment(self.store, profile)
        if role == "publication":
            validate_publication(profile)
            environment[profile.mongo_uri_env] = publication_uri(profile)
            command = [profile.host_python, str(Path(__file__).with_name("trace_service.py")),
                "--project", profile.project, "--mongo-reference", profile.mongo_uri_env,
                "--database", profile.mongo_database]
        else:
            command = [sys.executable, "-I", "-m", "oomp.product.services", "--role", role,
                       "--profile", profile.name, "--home", str(self.store.home)]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, cwd=self.directory, env=environment, **process_options())
        with self.guard:
            self.children[role] = process
            self.health[role] = {"ready": False, "heartbeat": time.monotonic()}
        thread = threading.Thread(target=self.reader, args=(role, process), daemon=True)
        self.readers[role] = thread
        thread.start()

    def wait_ready(self, role, seconds=25):
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline and not self.shutdown.is_set():
            if self.children[role].poll() is not None:
                raise ProductError("child_startup_failed")
            with self.guard:
                if self.health[role].get("fatal"):
                    raise ProductError("child_startup_failed")
                if self.health[role]["ready"]:
                    return
            time.sleep(.05)
        raise ProductError("startup_timeout")

    def close_children(self):
        for process in reversed(list(self.children.values())):
            if process.poll() is None:
                try:
                    process.stdin.write(b"stop\n")
                    process.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
        deadline = time.monotonic()+7
        for role, process in reversed(list(self.children.items())):
            try:
                process.wait(timeout=max(.1, deadline-time.monotonic()))
            except subprocess.TimeoutExpired:
                # Retained owned handle, never a PID obtained from disk.
                self.log("forced_stop", role)
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            self.readers[role].join(2)
            process.stdin.close()
            process.stdout.close()

    def run(self, *, background=False):
        profile = self.profile
        with file_lock(self.directory / "operation.lock"):
            # Even direct/internal launches may not overwrite an unretired
            # active record. Only the locked launcher can prove/retire it.
            runtime = self.directory / "runtime.json"
            if runtime.exists():
                previous, _ = _runtime_snapshot(runtime, profile, allow_stopped=True)
                if previous["stopped"] is not True:
                    raise ProductError("ownership_unverified_no_process_signalled")
            if profile != self.store.load(profile.name):
                raise ProductError("configuration_changed_retry")
            self.store.environment(profile)
            if profile.publication:
                validate_publication(profile)
                publication_uri(profile)
            from oomp.storage import SQLiteEventStore
            if not SQLiteEventStore(profile.database).status().ready:
                raise ProductError("storage_not_ready")
            if profile.transport == "streamable-http" and not port_available(profile.port):
                raise ProductError("port_in_use_no_process_changed")
            supervisor = self
            class Handler(socketserver.StreamRequestHandler):
                def handle(self):
                    self.request.settimeout(2)
                    try:
                        raw = self.rfile.readline(1025)
                        value = json.loads(raw) if len(raw) <= 1024 else {}
                        if (not secrets.compare_digest(value.get("token", ""), supervisor.token)
                                or value.get("run_id") != supervisor.run_id
                                or value.get("operation") not in {"status", "stop"}):
                            return
                        result = supervisor.snapshot()
                        self.wfile.write(json.dumps(result).encode()+b"\n")
                        if value["operation"] == "stop":
                            supervisor.shutdown.set()
                    except (OSError, ValueError, TypeError):
                        return
            class ControlServer(socketserver.ThreadingTCPServer):
                daemon_threads = True
                allow_reuse_address = False
                slots = threading.BoundedSemaphore(8)
                def process_request(self, request, address):
                    if not self.slots.acquire(blocking=False):
                        self.shutdown_request(request)
                        return
                    try:
                        super().process_request(request, address)
                    except BaseException:
                        self.slots.release()
                        raise
                def process_request_thread(self, request, address):
                    try:
                        super().process_request_thread(request, address)
                    finally:
                        self.slots.release()
                def handle_error(self, request, address):
                    pass
            control_server = ControlServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=control_server.serve_forever, kwargs={"poll_interval": .1}, daemon=True)
            thread.start()
            state = {"run_id": self.run_id, "token": self.token, "port": control_server.server_address[1],
                     "pid": os.getpid(), "configuration": profile.identity, "stopped": False}
            recorded = False
            try:
                write_json(self.directory / "runtime.json", state)
                recorded = True
                self.log("supervisor_start")
                if profile.transport == "streamable-http":
                    self.spawn("mcp")
                    self.wait_ready("mcp")
                    from .protocol import call
                    data = call(profile, self.store.environment(profile))
                    if "read" not in data.get("capabilities", []):
                        raise ProductError("mcp_authorization_failed")
                if profile.mind:
                    self.spawn("mind")
                    self.wait_ready("mind")
                if profile.publication:
                    self.spawn("publication")
                    self.wait_ready("publication")
                self.state = "running"
                self.log("supervisor_ready")
                if not background:
                    print("PASS OOMP services ready. Ctrl+C stops owned services.", flush=True)
                while not self.shutdown.wait(.2):
                    snapshot = self.snapshot()
                    failure = self.first_failure(snapshot)
                    if failure is not None:
                        self.failed = True
                        self.last_error = "owned_service_crashed_or_unresponsive"
                        self.failure = failure
                        self.log("child_exit", failure["role"], failure=failure)
                        break
            except KeyboardInterrupt:
                pass
            except Exception as error:
                self.failed = True
                self.last_error = error.code if isinstance(error, ProductError) else "startup_failed_check_doctor_and_logs"
                self.failure = self.first_failure(self.snapshot()) or failure_detail(
                    self.starting_role, "startup_failure", "startup", "unknown_error")
                self.log("startup_failed", self.starting_role if self.starting_role != "supervisor" else None,
                         failure=self.failure)
            finally:
                self.state = "stopping"
                try:
                    self.close_children()
                finally:
                    self.state = "failed" if self.failed else "stopped"
                    control_server.shutdown()
                    control_server.server_close()
                    thread.join(2)
                if recorded:
                    if read_json(runtime) != state:
                        raise ProductError("runtime_state_changed_retry")
                    if self.failure is not None and self.failure["role"] in self.children:
                        self.failure = checked_failure({**self.failure,
                            "exit_code": self.children[self.failure["role"]].poll()})
                    write_json(runtime, {**state, "stopped": True, "failed": self.failed,
                                         "last_error_code": self.last_error,
                                         **({"failure": self.failure} if self.failure is not None else {})})
                self.log("supervisor_stop")
            return 1 if self.failed else 0


def validate_publication(profile):
    if (not profile.publication or not profile.project or not profile.host_python
            or not safe_path(profile.host_python).is_file()
            or project_fingerprint(profile.project) != profile.approved_project):
        raise ProductError("approved_host_code_changed_or_unavailable")


def _start_background(store, profile):
    # Caller holds launch.lock, never operation.lock: the child needs that lock.
    if profile.publication:
        validate_publication(profile)
        publication_uri(profile)
    # Explicit background option only. Startup remains bounded and observed.
    environment = child_environment(store, profile)
    process = subprocess.Popen([sys.executable, "-I", "-m", "oomp.product.lifecycle",
        "--profile", profile.name, "--home", str(store.home), "--expected-configuration", profile.identity], stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=store.directory(profile.name),
        env=environment, **process_options())
    try:
        deadline = time.monotonic()+80
        while time.monotonic() < deadline:
            if process.poll() is not None:
                if store.load(profile.name) != profile:
                    raise ProductError("configuration_changed_retry")
                raise ProductError("startup_failed_check_doctor_and_logs")
            current = control(store, profile.name)
            if current.get("ownership_verified") and current["state"] == "running":
                return current
            time.sleep(.1)
        raise ProductError("startup_timeout")
    except BaseException:
        # Cancellation, changed state and malformed replies must not leak this
        # launcher's child. Do not re-read a mutable runtime file to choose a
        # shutdown target: even an authenticated replacement may be unrelated.
        if process.poll() is None:
            # Only the retained Popen handle authorizes termination. Its pipe
            # EOF stops owned services; in-flight work retains lease/fencing.
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        raise


def start(store, profile, *, background=False):
    with _checked_lock(store.directory(profile.name) / "launch.lock"):
        current = control(store, profile.name)
        if current.get("ownership_verified"):
            if current["state"] == "running":
                return current
            raise ProductError("profile_busy")
        recovered = current["state"] == "unverified" and _recover_stale_locked(store, profile)
        runtime = store.directory(profile.name) / "runtime.json"
        if not recovered and runtime.exists():
            _runtime_snapshot(runtime, profile, allow_stopped=True)
        if background:
            result = _start_background(store, profile)
            if recovered:
                result = {**result, "stale_runtime_recovered": True}
            return result
    # Foreground supervision retains operation.lock for its lifetime, but must
    # not prevent other callers from checking an authenticated running owner.
    return Supervisor(store, profile).run()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--home", required=True)
    parser.add_argument("--expected-configuration")
    args = parser.parse_args()
    try:
        store = ProfileStore(args.home)
        profile = store.load(args.profile)
        if args.expected_configuration is not None and args.expected_configuration != profile.identity:
            raise ProductError("configuration_changed_retry")
        return Supervisor(store, profile).run(background=True)
    except BaseException:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
