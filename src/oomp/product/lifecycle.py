"""Foreground supervision with authenticated loopback control and held OS locks.

Only retained Popen handles may be terminated. PIDs in state are informational;
stale state or PID reuse never authorizes a signal to an unrelated process.
"""
from __future__ import annotations

import argparse
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
from .profiles import ProfileStore
from .safety import ProductError, file_lock, private_directory, read_json, restrict, safe_path, write_json

_CODES = {"ready", "heartbeat", "work_warning", "work_complete", "service_failed"}


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
    state = read_json(path)
    if state.get("stopped") is True:
        return {"profile": name, "state": "failed" if state.get("failed") else "stopped",
                "ownership_verified": False, "services": {}, "last_error_code": state.get("last_error_code")}
    if (type(state.get("port")) is not int or not 1024 <= state["port"] <= 65535
            or not re.fullmatch(r"[A-Za-z0-9_-]{43}", state.get("token", ""))
            or not re.fullmatch(r"[a-f0-9]{32}", state.get("run_id", ""))):
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
    except (OSError, ValueError, KeyError):
        return {"profile": name, "state": "unverified", "ownership_verified": False,
                "services": {}, "last_error_code": "stale_state_or_supervisor_unavailable"}


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
                result.append({k: item[k] for k in ("at", "code", "role") if k in item})
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

    def log(self, code, role=None):
        path = safe_path(self.directory / "operations.log")
        if path.exists() and path.stat().st_size >= 1048576:
            old = safe_path(self.directory / "operations.previous.log")
            os.replace(path, old)
        descriptor = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        restrict(path)
        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "code": code, "role": role})+"\n")

    def snapshot(self):
        with self.guard:
            services = {}
            for role, process in self.children.items():
                info = self.health.get(role, {})
                age = time.monotonic()-info.get("heartbeat", time.monotonic())
                progress_age = time.monotonic()-info.get("progress", time.monotonic())
                alive = process.poll() is None
                services[role] = {"pid": process.pid, "alive": alive,
                    "ready": bool(info.get("ready")) and alive and age < 12 and (role == "mcp" or progress_age < 180),
                    "heartbeat_age_seconds": round(age, 2), "last_error_code": info.get("error")}
                services[role]["progress_age_seconds"] = round(progress_age, 2)
        return {"profile": self.profile.name, "state": self.state, "ownership_verified": True,
                "services": services, "last_error_code": self.last_error, "run_id": self.run_id,
                "stdio": "host-owned; use oomp connect" if self.profile.transport == "stdio" else None,
                "external_services": "host API, MongoDB and Ollama are independently owned"}

    def reader(self, role, process):
        while True:
            raw = process.stdout.readline(4097)
            if not raw:
                return
            try:
                if len(raw) > 4096:
                    raise ValueError()
                value = json.loads(raw)
                code = value.get("code")
                if code not in _CODES:
                    raise ValueError()
                with self.guard:
                    entry = self.health[role]
                    entry["heartbeat"] = time.monotonic()
                    if code == "ready":
                        entry["ready"] = True
                        entry["progress"] = time.monotonic()
                    if code == "work_complete":
                        entry["progress"] = time.monotonic()
                        if not value.get("failed") and not value.get("lost_lease"):
                            entry.pop("error", None)
                    if code in {"service_failed", "work_warning"}:
                        entry["error"] = code
                if code in {"service_failed", "work_warning"}:
                    self.log(code, role)
            except (ValueError, TypeError, AttributeError):
                with self.guard:
                    self.health[role]["error"] = "invalid_child_status"
                self.failed = True
                self.shutdown.set()
                return

    def spawn(self, role):
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
            write_json(self.directory / "runtime.json", state)
            self.log("supervisor_start")
            try:
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
                    if any(not item["ready"] for item in snapshot["services"].values()):
                        self.failed = True
                        self.last_error = "owned_service_crashed_or_unresponsive"
                        self.log("child_exit")
                        break
            except KeyboardInterrupt:
                pass
            except Exception as error:
                self.failed = True
                self.last_error = error.code if isinstance(error, ProductError) else "startup_failed_check_doctor_and_logs"
                self.log("startup_failed")
            finally:
                self.state = "stopping"
                self.close_children()
                self.state = "failed" if self.failed else "stopped"
                control_server.shutdown()
                control_server.server_close()
                thread.join(2)
                write_json(self.directory / "runtime.json", {**state, "stopped": True, "failed": self.failed,
                                                           "last_error_code": self.last_error})
                self.log("supervisor_stop")
            return 1 if self.failed else 0


def validate_publication(profile):
    if (not profile.publication or not profile.project or not profile.host_python
            or not safe_path(profile.host_python).is_file()
            or project_fingerprint(profile.project) != profile.approved_project):
        raise ProductError("approved_host_code_changed_or_unavailable")


def start(store, profile, *, background=False):
    if profile.publication:
        validate_publication(profile)
        publication_uri(profile)
    current = control(store, profile.name)
    if current.get("ownership_verified"):
        if current["state"] == "running":
            return current
        raise ProductError("profile_busy")
    if not background:
        return Supervisor(store, profile).run()
    # Explicit background option only. Startup remains bounded and observed.
    environment = child_environment(store, profile)
    process = subprocess.Popen([sys.executable, "-I", "-m", "oomp.product.lifecycle",
        "--profile", profile.name, "--home", str(store.home)], stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=store.directory(profile.name),
        env=environment, **process_options())
    deadline = time.monotonic()+80
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ProductError("startup_failed_check_doctor_and_logs")
        current = control(store, profile.name)
        if current.get("ownership_verified") and current["state"] == "running":
            return current
        time.sleep(.1)
    # This is the launcher-owned supervisor handle, not a state-file PID.
    try:
        stop(store, profile.name)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
    raise ProductError("startup_timeout")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--home", required=True)
    args = parser.parse_args()
    try:
        store = ProfileStore(args.home)
        return Supervisor(store, store.load(args.profile)).run(background=True)
    except BaseException:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
