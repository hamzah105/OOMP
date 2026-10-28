"""P1 actual SDK clients, owned processes, crash/stop/restart and authority."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import socket
import sys
import threading
import time

import pytest
pytest.importorskip("mcp", reason="install [mcp] to exercise real product services")
from mcp import Client, StdioServerParameters

from oomp.product.lifecycle import Supervisor, control, stop, port_available, logs
from oomp.product.models import Profile
from oomp.product.protocol import call
from oomp.product.safety import ProductError, read_json, write_json
from oomp.mcp.authorization import approve_ingestion
from oomp.mcp.contracts import IngestPayload
from test_product_profiles import setup_profile, digest


def free_port():
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", 0))
        return connection.getsockname()[1]


@contextmanager
def owned_services(store, profile):
    supervisor = Supervisor(store, profile)
    outcomes = []
    def run():
        try:
            outcomes.append(supervisor.run(background=True))
        except BaseException as error:
            outcomes.append(error)
    thread = threading.Thread(target=run)
    thread.start()
    try:
        deadline = time.monotonic()+40
        while supervisor.state == "starting" and thread.is_alive() and time.monotonic()<deadline:
            time.sleep(.05)
        assert supervisor.state == "running", outcomes
        yield supervisor, thread
    finally:
        supervisor.shutdown.set()
        thread.join(20)
        assert not thread.is_alive(), "owned supervisor did not terminate"
        assert all(p.poll() is not None for p in supervisor.children.values()), "owned subprocess leaked"
        assert port_available(profile.port)


def approved_event(profile, environment, name="managed-test"):
    now = datetime.now(timezone.utc)
    payload = IngestPayload(event_id=name, idempotency_key=name,
        content="I am developing a project called ManagedDemo.", occurred_at=now,
        source_reference={"source_system": "approved-host", "external_event_id": name, "timestamp": now})
    grant = profile.grants()[1]["user"]
    return {**payload.model_dump(mode="json"), "approval": approve_ingestion(
        grant, payload, environment[grant.ingest_approval_key_env]).model_dump(mode="json")}


def await_fact(profile, environment):
    deadline = time.monotonic()+20
    while time.monotonic()<deadline:
        result = call(profile, environment, "memory.retrieve", {"query": "project developing", "token_budget": 3000})
        if result["memories"]:
            return result
        time.sleep(.1)
    pytest.fail("separate worker did not make accepted evidence retrievable")


def test_authenticated_ingest_separate_worker_proof_authority_and_shutdown(tmp_path):
    store, profile = setup_profile(tmp_path, port=free_port(), mode="trusted-ingest")
    env = store.environment(profile)
    with owned_services(store, profile):
        state = control(store, "test")
        assert state["ownership_verified"] and set(state["services"]) == {"mcp", "mind"}
        arguments = approved_event(profile, env)
        receipt = call(profile, env, "memory.ingest", arguments, role="user")
        assert receipt["acceptance"] == "durably_stored" and receipt["worker_started_by_request"] is False
        result = await_fact(profile, env)
        assert result["memories"][0]["source_event_ids"] == ["managed-test"]
        assert result["estimated_token_count"] <= 3000
        with pytest.raises(ProductError):
            call(profile, env, "memory.retrieve", {"query": "project", "tenant_id": "unauthorized"})
        with pytest.raises(ProductError):
            call(profile, env, "memory.ingest", arguments)  # read token cannot ingest
        unsigned = {k: v for k, v in arguments.items() if k != "approval"}
        with pytest.raises(ProductError):
            call(profile, env, "memory.ingest", unsigned, role="user")
        invalid = {**env, profile.reference("read_token"): "X"*43}
        with pytest.raises(ProductError):
            call(profile, invalid)
        output = json.dumps(state)+json.dumps(logs(store, "test"))
        assert not any(secret in output for secret in env.values())
        assert stop(store, "test")["state"] == "stopped"
    assert control(store, "test")["state"] == "stopped"


def test_worker_crash_stops_siblings_and_same_profile_recovers_without_data_loss(tmp_path):
    store, profile = setup_profile(tmp_path, port=free_port(), mode="trusted-ingest")
    env = store.environment(profile)
    secret_hash = digest(store.directory("test")/"secrets.json")
    with owned_services(store, profile) as (supervisor, thread):
        call(profile, env, "memory.ingest", approved_event(profile, env), role="user")
        await_fact(profile, env)
        old_run = supervisor.run_id
        supervisor.children["mind"].kill()  # retained test-owned child handle
        thread.join(15)
        assert not thread.is_alive() and supervisor.failed
        assert supervisor.children["mcp"].poll() is not None
    with owned_services(store, profile) as (recovered, _):
        assert recovered.run_id != old_run
        assert await_fact(profile, env)["memories"][0]["source_event_ids"] == ["managed-test"]
    assert digest(store.directory("test")/"secrets.json") == secret_hash


def test_duplicate_start_and_reconfiguration_are_blocked_while_owned(tmp_path):
    store, profile = setup_profile(tmp_path, port=free_port())
    with owned_services(store, profile):
        with pytest.raises(ProductError, match="profile_busy"):
            Supervisor(store, profile).run(background=True)
        changed = Profile.model_validate({**profile.model_dump(mode="json"), "port": free_port()})
        with pytest.raises(ProductError, match="profile_busy"):
            store.update(changed)
        assert store.load("test") == profile


def test_port_collision_never_stops_the_independent_listener(tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        store, profile = setup_profile(tmp_path, port=port)
        with pytest.raises(ProductError, match="port_in_use_no_process_changed"):
            Supervisor(store, profile).run(background=True)
        assert listener.fileno() >= 0 and not port_available(port)
        assert not (store.directory("test")/"runtime.json").exists()


def test_stale_pid_and_invalid_control_credential_never_authorize_a_signal(tmp_path, monkeypatch):
    import os
    store, profile = setup_profile(tmp_path, port=free_port())
    write_json(store.directory("test")/"runtime.json", {"pid": os.getpid(), "run_id": secrets.token_hex(16),
        "token": secrets.token_urlsafe(32), "port": free_port(), "stopped": False})
    monkeypatch.setattr(os, "kill", lambda *_: pytest.fail("PID from state must never be signalled"))
    assert control(store, "test")["state"] == "unverified"
    with pytest.raises(ProductError, match="ownership_unverified_no_process_signalled"):
        stop(store, "test")
    with owned_services(store, profile):
        runtime = read_json(store.directory("test")/"runtime.json")
        with socket.create_connection(("127.0.0.1", runtime["port"]), timeout=2) as connection:
            connection.sendall(json.dumps({"operation": "stop", "run_id": runtime["run_id"], "token": "wrong"}).encode()+b"\n")
            assert connection.recv(1) == b""
        assert control(store, "test")["state"] == "running"


def test_startup_worker_failure_cleans_up_mcp_and_never_reports_ready(tmp_path, monkeypatch):
    store, profile = setup_profile(tmp_path, port=free_port())
    supervisor = Supervisor(store, profile)
    original = supervisor.wait_ready
    def failing(role, seconds=25):
        if role == "mind":
            supervisor.children[role].kill()
            supervisor.children[role].wait(timeout=5)
        return original(role, seconds)
    monkeypatch.setattr(supervisor, "wait_ready", failing)
    assert supervisor.run(background=True) == 1
    assert all(p.poll() is not None for p in supervisor.children.values())
    assert "supervisor_ready" not in {row["code"] for row in logs(store, "test")}
    assert control(store, "test")["state"] == "failed"
    assert port_available(profile.port)


def test_ctrl_c_shutdown_branch_reaps_owned_children(tmp_path, monkeypatch):
    store, profile = setup_profile(tmp_path, port=free_port())
    supervisor = Supervisor(store, profile)
    original = supervisor.log
    def keyboard_interrupt(code, role=None):
        original(code, role)
        if code == "supervisor_ready":
            raise KeyboardInterrupt()
    monkeypatch.setattr(supervisor, "log", keyboard_interrupt)
    assert supervisor.run() == 0
    assert all(p.poll() is not None for p in supervisor.children.values())
    assert control(store, "test")["state"] == "stopped"


def test_read_only_stdio_profile_is_host_owned_and_does_not_start_mind(tmp_path):
    store, profile = setup_profile(tmp_path, transport="stdio")
    async def client():
        parameters = StdioServerParameters(command=sys.executable, args=["-m", "oomp", "connect",
            "--profile", "test", "--home", str(store.home)])
        async with Client(parameters) as connection:
            tools = await connection.list_tools()
            assert "memory.ingest" not in {t.name for t in tools.tools}
            status = await connection.call_tool("memory.status", {})
            assert not status.is_error
            data = status.structured_content
            assert data["read_only"] and data["capabilities"] == ["read"]
            assert data["mind_worker_started_by_server"] is False
    asyncio.run(asyncio.wait_for(client(), 20))
    assert control(store, "test")["state"] == "stopped"


def test_public_product_example_uses_fresh_storage_and_cleans_up(tmp_path):
    from examples.product_quickstart import run
    directory = tmp_path/"public example with spaces سلام"
    report = run(directory)
    assert report["authenticated_signed_ingestion"] and report["restart_preserved_source"]
    assert report["owned_services_stopped"] and report["model_calls"] == 0
    before = (directory/"acceptance.json").read_bytes()
    with pytest.raises(FileExistsError):
        run(directory)
    assert (directory/"acceptance.json").read_bytes() == before
