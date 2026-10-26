"""Stage 7: real official SDK stdio/TCP clients and authority boundaries."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

import pytest

pytest.importorskip("mcp", reason="install .[mcp] for optional integration tests")
import httpx2
import uvicorn
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client

from oomp.domain.enums import EventType
from oomp.domain.models import MemoryEdge
from oomp.domain.graph import TemporalQuery
from oomp.mcp.authorization import approve_ingestion
from oomp.mcp.configuration import Grant, ServerConfiguration
from oomp.mcp.contracts import IngestPayload
from oomp.mcp.server import build_server, build_http_app
from oomp.retrieval.engine import RetrievalEngine
from oomp.storage import SQLiteEventStore, SQLiteMemoryStore, SQLiteGraphStore
from oomp.storage.mind_store import SQLiteMindStore
from oomp.mind.worker import MindWorker
from test_stage5_storage import add_memory, scope
from test_stage6_storage import event

TOKEN_A = "A" * 43
TOKEN_B = "B" * 43
TOKEN_RAW = "R" * 43
TOKEN_WRITER = "W" * 43
APPROVAL_KEY = "K" * 43
ENVIRONMENT = {"TOKEN_A": TOKEN_A, "TOKEN_B": TOKEN_B, "TOKEN_RAW": TOKEN_RAW,
               "TOKEN_WRITER": TOKEN_WRITER, "APPROVAL_KEY": APPROVAL_KEY}
READ_TOOLS = {"memory.retrieve", "memory.expand", "memory.get_source", "memory.status"}


def reader(identity="a", tenant="tenant", namespace="personal", raw=False, token="TOKEN_A"):
    return Grant(grant_id=identity, principal_id="host-" + identity, tenant_id=tenant,
                 namespace=namespace, capabilities=("read", "read_source") if raw else ("read",),
                 bearer_token_env=token)


def writer():
    return Grant(grant_id="writer", principal_id="host-writer", tenant_id="tenant", namespace="personal",
                 bearer_token_env="TOKEN_WRITER", capabilities=("read", "ingest"),
                 ingest_approval_key_env="APPROVAL_KEY", ingest_source_type="user",
                 ingest_source_system="approved-host", ingest_event_types=("user_message",))


def free_port():
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", 0))
        return connection.getsockname()[1]


def configuration(db, *, http=False, trusted=False, **values):
    grants = (reader(), reader("b", "other", token="TOKEN_B"),
              reader("raw", raw=True, token="TOKEN_RAW"))
    if trusted:
        grants += (writer(),)
    base = dict(database=str(db), transport="streamable-http" if http else "stdio",
                profile="trusted-ingest" if trusted else "read-only",
                stdio_grant=None if http else (writer() if trusted else reader()),
                http_grants=grants if http else (), port=free_port())
    base.update(values)
    return ServerConfiguration(**base)


@pytest.fixture
def populated(tmp_path):
    path = tmp_path / "memory with spaces.sqlite3"
    SQLiteEventStore(path).initialize()
    one = add_memory(path, "oomp", "I am working on OOMP, a temporal memory project.")
    two = add_memory(path, "python", "OOMP uses Python and SQLite.")
    add_memory(path, "private", "FOREIGN-TENANT-SECRET OOMP.", scope("other"))
    add_memory(path, "namespace", "FOREIGN-NAMESPACE-SECRET OOMP.", scope(namespace="work"))
    graph = SQLiteGraphStore(path)
    graph.add_edge(scope(), MemoryEdge(
        edge_id="project-python", tenant_id="tenant", namespace="personal",
        source_node_id=one.memory_id, target_node_id=two.memory_id,
        relationship_type="RELATED_TO", source_event_ids=("event-oomp",),
        created_at=datetime.now(timezone.utc),
    ))
    RetrievalEngine(path).index(scope())
    RetrievalEngine(path).index(scope("other"))
    return path, one, two


@contextmanager
def running_http(config):
    server = build_server(config, environ=ENVIRONMENT)
    runner = uvicorn.Server(uvicorn.Config(
        build_http_app(server), host=config.host, port=config.port,
        access_log=False, log_level="critical", server_header=False, proxy_headers=False,
        h11_max_incomplete_event_size=16384,
    ))
    thread = threading.Thread(target=runner.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not runner.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(.01)
    assert runner.started, "loopback server did not start"
    try:
        yield server
    finally:
        runner.should_exit = True
        thread.join(10)
        assert not thread.is_alive(), "MCP server did not shut down"


@asynccontextmanager
async def http_client(config, token=TOKEN_A, mode="auto"):
    async with httpx2.AsyncClient(
        headers={"Authorization": "Bearer " + token}, trust_env=False, timeout=10,
    ) as transport_client:
        transport = streamable_http_client(config.endpoint, http_client=transport_client)
        async with Client(transport, mode=mode) as client:
            yield client


def run(coroutine):
    return asyncio.run(asyncio.wait_for(coroutine, 30))


def assert_error(result, code):
    assert result.is_error
    assert result.structured_content["error"]["code"] == code
    serialized = result.model_dump_json()
    for private in ("FOREIGN-", "Traceback", "memory with spaces", APPROVAL_KEY, TOKEN_A):
        assert private not in serialized
    return result.structured_content


def payload(identity="approved"):
    now = datetime.now(timezone.utc)
    return IngestPayload(
        event_id=identity, idempotency_key="idem-" + identity, content="I prefer Python.",
        occurred_at=now,
        source_reference={"source_system": "approved-host", "external_event_id": identity,
                          "timestamp": now, "locator": "untrusted://do-not-fetch"},
    )


def approved_arguments(value=None, grant=None, now=None):
    value = value or payload()
    proof = approve_ingestion(grant or writer(), value, APPROVAL_KEY, now=now)
    return {**value.model_dump(mode="json"), "approval": proof.model_dump(mode="json")}


def test_actual_stdio_discovery_structured_retrieval_sources_and_graph(populated, tmp_path):
    path, one, two = populated
    config = configuration(path)
    file = tmp_path / "server config.json"
    file.write_text(config.model_dump_json(), encoding="utf-8")
    async def scenario():
        parameters = StdioServerParameters(command=sys.executable, args=[
            "-m", "oomp", "mcp", "serve", "--config", str(file)])
        async with Client(parameters) as client:
            catalog = await client.list_tools()
            assert catalog.cache_scope == "private" and catalog.ttl_ms == 0
            tools = catalog.tools
            assert (await client.list_resources()).resources == []
            assert (await client.list_prompts()).prompts == []
            from mcp.shared.exceptions import MCPError
            with pytest.raises(MCPError) as failure:
                await client.read_resource("file:///PRIVATE-REQUEST")
            assert "PRIVATE-REQUEST" not in str(failure.value)
            with pytest.raises(MCPError):
                await client.get_prompt("PRIVATE-REQUEST")
            assert {t.name for t in tools} == READ_TOOLS
            for tool in tools:
                assert tool.input_schema["additionalProperties"] is False
                assert "tenant_id" not in tool.input_schema.get("properties", {})
                assert tool.output_schema
                assert tool.annotations.read_only_hint is True
            assert client.protocol_version == "2026-07-28"
            result = await client.call_tool("memory.retrieve", {"query": "OOMP", "token_budget": 12000})
            assert not result.is_error
            data = result.structured_content
            ids = {m["memory_id"] for m in data["memories"]}
            assert one.memory_id in ids and two.memory_id in ids
            assert "FOREIGN-" not in result.model_dump_json()
            assert data["budget_scope"] == "context_packet_only"
            assert len(data["context_packet"].encode("utf-8")) == data["estimated_token_count"] <= 12000
            source = (await client.call_tool("memory.get_source", {"memory_id": one.memory_id})).structured_content
            assert source["sources"][0]["event_id"] == "event-oomp"
            assert source["sources"][0]["content"] is None
            expanded = await client.call_tool("memory.expand", {"memory_id": one.memory_id})
            assert not expanded.is_error
            assert {m["memory_id"] for m in expanded.structured_content["memories"]} == {one.memory_id, two.memory_id}
            assert expanded.structured_content["edges"][0]["edge_id"] == "project-python"
    run(scenario())


def test_actual_http_discovery_scope_and_raw_source_capability(populated):
    path, one, _ = populated
    config = configuration(path, http=True)
    async def scenario():
        async with http_client(config) as client:
            assert {t.name for t in (await client.list_tools()).tools} == READ_TOOLS
            status = (await client.call_tool("memory.status", {})).structured_content
            assert status["index"]["canonical_count"] == 2
            assert status["mind_worker_started_by_server"] is False
            assert_error(await client.call_tool("memory.get_source", {
                "memory_id": one.memory_id, "include_content": True}), "forbidden")
            assert_error(await client.call_tool("memory.expand", {"memory_id": "mem-private"}), "not_found")
        async with http_client(config, TOKEN_B) as client:
            found = await client.call_tool("memory.retrieve", {"query": "OOMP", "token_budget": 12000})
            assert {m["memory_id"] for m in found.structured_content["memories"]} == {"mem-private"}
            assert_error(await client.call_tool("memory.get_source", {"memory_id": one.memory_id}), "not_found")
        async with http_client(config, TOKEN_RAW) as client:
            source = await client.call_tool("memory.get_source", {"memory_id": one.memory_id, "include_content": True})
            assert source.structured_content["sources"][0]["content"] == one.canonical_content
    with running_http(config):
        run(scenario())


@pytest.mark.parametrize("name,arguments", [
    ("memory.status", {"tenant_id": "other"}),
    ("memory.retrieve", {"query": "OOMP", "namespace": "work"}),
    ("memory.retrieve", {"query": "OOMP", "principal_id": "admin"}),
    ("memory.retrieve", {"query": "OOMP", "max_results": True}),
    ("memory.retrieve", {"query": "OOMP", "graph_depth": 3}),
    ("memory.retrieve", {"query": "OOMP", "token_budget": 32769}),
    ("memory.retrieve", {"query": " "}),
    ("memory.retrieve", {"query": "x" * 4097}),
    ("memory.retrieve", {"query": "OOMP", "known_at": "2026-10-01"}),
    ("memory.expand", {"memory_id": "../events"}),
    ("memory.expand", {"memory_id": "mem-oomp", "max_nodes": 33}),
    ("memory.get_source", {"event_id": "event-oomp"}),
    ("memory.get_source", {"memory_id": "mem-oomp", "include_content": "true"}),
    ("memory.get_source", {"memory_id": "mem-oomp", "limit": 33}),
])
def test_typed_input_rejection_over_actual_http(populated, name, arguments):
    config = configuration(populated[0], http=True)
    async def scenario():
        async with http_client(config) as client:
            assert_error(await client.call_tool(name, arguments), "invalid_parameters")
    with running_http(config):
        run(scenario())


@pytest.mark.parametrize("name", ["memory.erase", "memory.sql", "memory.merge_entities",
                                 "memory.approve_conflict", "memory.change_scope", "memory.ingest"])
def test_forbidden_tools_are_not_discovered_or_callable(populated, name):
    config = configuration(populated[0], http=True)
    async def scenario():
        async with http_client(config) as client:
            assert name not in {t.name for t in (await client.list_tools()).tools}
            assert_error(await client.call_tool(name, {}), "not_found")
    with running_http(config):
        run(scenario())


def test_http_missing_invalid_and_expired_credentials(populated):
    expired = reader("expired", token="TOKEN_A").model_copy(update={
        "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)})
    config = configuration(populated[0], http=True, http_grants=(expired,))
    async def scenario():
        async with httpx2.AsyncClient(trust_env=False) as client:
            for headers in ({}, {"Authorization": "Bearer wrong"}, {"Authorization": "Bearer " + TOKEN_A}):
                result = await client.post(config.endpoint, headers=headers, content=b"{}")
                assert result.status_code == 401
                assert "Bearer" in result.headers["www-authenticate"]
                assert result.headers["cache-control"] == "no-store"
    with running_http(config):
        run(scenario())


def test_http_host_origin_duplicates_methods_and_body_limits(populated):
    config = configuration(populated[0], http=True, max_request_bytes=1024)
    async def scenario():
        headers = {"Authorization": "Bearer " + TOKEN_A}
        async with httpx2.AsyncClient(trust_env=False) as client:
            result = await client.post(config.endpoint, headers={**headers, "Host": "rebind.example"}, content="{}")
            assert result.status_code == 421
            result = await client.post(config.endpoint, headers={**headers, "Origin": "http://evil.example"}, content="{}")
            assert result.status_code == 403
            result = await client.post(config.endpoint, headers=[
                *headers.items(), ("Authorization", "Bearer " + TOKEN_B)], content="{}")
            assert result.status_code == 400
            result = await client.put(config.endpoint, headers=headers, content="{}")
            assert result.status_code == 405
            result = await client.post(config.endpoint, headers={
                **headers, "Content-Type": "application/json"}, content=b"x" * 1025)
            assert result.status_code == 413
            async def chunks():
                yield b"x" * 800
                yield b"x" * 800
            result = await client.post(config.endpoint, headers={
                **headers, "Content-Type": "application/json"}, content=chunks())
            assert result.status_code == 413
            result = await client.post(config.endpoint + "?token=secret", headers=headers, content="{}")
            assert result.status_code == 404
            result = await client.post(config.endpoint, headers={**headers,
                "Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
                content=b'{"jsonrpc":')
            assert result.status_code == 400
    with running_http(config):
        run(scenario())


def test_approved_http_ingest_is_idempotent_and_never_starts_worker(populated):
    path, _, _ = populated
    config = configuration(path, http=True, trusted=True)
    args = approved_arguments()
    async def scenario():
        async with http_client(config) as reader_client:
            assert {t.name for t in (await reader_client.list_tools()).tools} == READ_TOOLS
            assert_error(await reader_client.call_tool("memory.ingest", args), "not_found")
        async with http_client(config, TOKEN_WRITER) as client:
            assert {t.name for t in (await client.list_tools()).tools} == READ_TOOLS | {"memory.ingest"}
            for _ in range(2):
                result = await client.call_tool("memory.ingest", args)
                assert not result.is_error, result
                assert result.structured_content["outbox_state"] == "pending"
                assert result.structured_content["latest_extraction_job_status"] is None
                assert result.structured_content["worker_started_by_request"] is False
            stored = SQLiteEventStore(path).get(scope(), "approved")
            assert stored.metadata["ingested_by"] == "host-writer"
            assert stored.source_type.value == "user"
            assert SQLiteMemoryStore(path).count_memories(scope()) == 2
            await asyncio.to_thread(MindWorker(path, scope()).run_once, max_jobs=16)
            status = await client.call_tool("memory.status", {})
            assert status.structured_content["index"]["canonical_count"] >= 3
            retried = await client.call_tool("memory.ingest", args)
            assert retried.structured_content["latest_extraction_job_status"] == "completed"
    with running_http(config):
        run(scenario())
    assert SQLiteEventStore(path).get(scope(), "approved") is not None


@pytest.mark.parametrize("mutation,code", [
    ("missing", "invalid_parameters"), ("signature", "forbidden"), ("content", "forbidden"),
    ("expired", "forbidden"), ("future", "forbidden"), ("other-grant", "forbidden"),
    ("source_type", "invalid_parameters"), ("tenant_id", "invalid_parameters"),
    ("namespace", "invalid_parameters"), ("principal_id", "invalid_parameters"),
    ("metadata", "invalid_parameters"), ("ingested_at", "invalid_parameters"),
    ("role-policy", "forbidden"), ("source-policy", "forbidden"),
])
def test_ingest_requires_exact_host_approval_and_trusted_role(populated, mutation, code):
    config = configuration(populated[0], http=True, trusted=True)
    args = approved_arguments()
    if mutation == "missing":
        del args["approval"]
    elif mutation == "signature":
        args["approval"]["signature"] = "0" * 64
    elif mutation == "content":
        args["content"] = "I prefer JavaScript."
    elif mutation in {"expired", "future"}:
        offset = -timedelta(minutes=10) if mutation == "expired" else timedelta(minutes=10)
        args = approved_arguments(now=datetime.now(timezone.utc) + offset)
    elif mutation == "other-grant":
        other = writer().model_copy(update={"grant_id": "someone-else", "principal_id": "another-host"})
        args = approved_arguments(grant=other)
    elif mutation == "role-policy":
        value = payload().model_copy(update={"event_type": EventType.ASSISTANT_MESSAGE})
        args = approved_arguments(value)
    elif mutation == "source-policy":
        value = payload()
        value = value.model_copy(update={"source_reference": value.source_reference.model_copy(update={"source_system": "unapproved"})})
        args = approved_arguments(value)
    else:
        args[mutation] = {"attribution": "user"} if mutation == "metadata" else "spoofed"
    async def scenario():
        async with http_client(config, TOKEN_WRITER) as client:
            assert_error(await client.call_tool("memory.ingest", args), code)
    with running_http(config):
        run(scenario())
    assert SQLiteEventStore(populated[0]).get(scope(), "approved") is None


def test_ingest_conflicting_replay_is_sanitized(populated):
    config = configuration(populated[0], http=True, trusted=True)
    value = payload()
    changed = value.model_copy(update={"content": "I prefer Go."})
    async def scenario():
        async with http_client(config, TOKEN_WRITER) as client:
            assert not (await client.call_tool("memory.ingest", approved_arguments(value))).is_error
            assert_error(await client.call_tool("memory.ingest", approved_arguments(changed)), "conflict")
    with running_http(config):
        run(scenario())

@pytest.mark.parametrize("transport", ["stdio", "streamable-http"])
def test_long_history_recovers_early_project_over_real_client(tmp_path, transport):
    from oomp.ingestion import ExtractionPipeline
    path = tmp_path / "history.sqlite3"
    events = SQLiteEventStore(path)
    events.initialize()
    early = event("early-project", content="I am developing a project called OOMP.")
    events.append(scope(), early)
    extracted = ExtractionPipeline(path).process_event(scope(), early.event_id)
    assert len(extracted.memory_ids) == 1
    for number in range(105):
        later = event("later-" + str(number), content=f"Synthetic unrelated turn number {number}.")
        events.append(scope(), later)
    assert early.event_id not in {e.event_id for e in events.list_events(scope(), limit=1000).events[-8:]}
    config = configuration(path, http=transport == "streamable-http")
    file = tmp_path / "history server config.json"
    file.write_text(config.model_dump_json(), encoding="utf-8")
    async def assess(client):
        result = await client.call_tool("memory.retrieve", {"query": "What project was the user developing?",
                                                           "token_budget": 1200})
        assert not result.is_error
        data = result.structured_content
        assert [m["memory_id"] for m in data["memories"]] == list(extracted.memory_ids)
        assert data["memories"][0]["source_event_ids"] == [early.event_id]
        assert "OOMP" in data["memories"][0]["canonical_content"]
        assert "answer" not in data
        assert len(data["context_packet"].encode("utf-8")) == data["estimated_token_count"] <= 1200
        unrelated = await client.call_tool("memory.retrieve", {"query": "Capital of France?"})
        assert unrelated.structured_content["memories"] == []
    async def stdio():
        async with Client(StdioServerParameters(command=sys.executable, args=[
            "-m", "oomp", "mcp", "serve", "--config", str(file)])) as client:
            await assess(client)
    async def http():
        async with http_client(config) as client:
            await assess(client)
    if transport == "stdio":
        run(stdio())
    else:
        with running_http(config):
            run(http())


def test_temporal_graph_current_historical_and_known_at(populated):
    from test_stage4_conflicts import memory
    from oomp.graph import GraphService
    path = populated[0]
    old_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    change_at = old_at + timedelta(days=10)
    future = datetime.now(timezone.utc) + timedelta(days=365)
    old_event = event("old-ram", content="My test computer has 4 GB RAM.").model_copy(update={
        "occurred_at": old_at, "source_reference": event("old-ram").source_reference.model_copy(update={"timestamp": old_at})})
    new_event = event("new-ram", content="I upgraded my test computer to 12 GB RAM.").model_copy(update={
        "occurred_at": change_at, "source_reference": event("new-ram").source_reference.model_copy(update={"timestamp": change_at})})
    for value in (old_event, new_event):
        SQLiteEventStore(path).append(scope(), value)
    old = memory("old-ram-memory", old_event, valid_from=old_at, valid_until=change_at)
    new = memory("new-ram-memory", new_event, valid_from=change_at, valid_until=future)
    for value in (old, new):
        SQLiteMemoryStore(path).upsert(scope(), value)
    cutoff = datetime.now(timezone.utc)
    graph = GraphService(path)
    proposal = graph.propose_conflict(scope(), new.memory_id, old.memory_id).proposal
    assert proposal is not None
    edge = graph.resolve(scope(), proposal, confirm=True)
    config = configuration(path, http=True)
    async def scenario():
        async with http_client(config) as client:
            current = await client.call_tool("memory.retrieve", {"query": "RAM", "token_budget": 12000})
            assert {m["memory_id"] for m in current.structured_content["memories"]} == {new.memory_id}
            past = await client.call_tool("memory.retrieve", {"query": "RAM", "valid_at": "2026-01-05T00:00:00Z",
                                                           "token_budget": 12000})
            assert {m["memory_id"] for m in past.structured_content["memories"]} == {old.memory_id}
            assert_error(await client.call_tool("memory.expand", {"memory_id": old.memory_id}), "not_found")
            expanded = await client.call_tool("memory.expand", {"memory_id": old.memory_id, "historical": True})
            data = expanded.structured_content
            assert {m["memory_id"] for m in data["memories"]} == {old.memory_id, new.memory_id}
            assert data["edges"][0]["edge_id"] == edge.edge.edge_id
            linked = next(m for m in data["memories"] if m["memory_id"] == new.memory_id)
            assert linked["graph_paths"][0]["edge_directions"] == ["reverse"]
            assert linked["graph_paths"][0]["edge_evidence"][0][0]["external_event_id"] == "new-ram"
            before = await client.call_tool("memory.expand", {"memory_id": old.memory_id,
                "historical": True, "known_at": cutoff.isoformat()})
            assert before.structured_content["edges"] == []
            unknown = await client.call_tool("memory.get_source", {"memory_id": old.memory_id,
                "known_at": old_at.isoformat()})
            assert_error(unknown, "not_found")
    with running_http(config):
        run(scenario())


def test_source_must_be_linked_and_pagination_uses_real_evidence(populated):
    path, one, _ = populated
    second = event("second-proof", content=one.canonical_content)
    SQLiteEventStore(path).append(scope(), second)
    updated = one.model_copy(update={
        "source_event_ids": one.source_event_ids + (second.event_id,),
        "provenance": one.provenance + (second.source_reference,)})
    SQLiteMemoryStore(path).upsert(scope(), updated)
    config = configuration(path, http=True)
    async def scenario():
        async with http_client(config) as client:
            for event_id in ("event-python", "event-private", "missing"):
                assert_error(await client.call_tool("memory.get_source", {
                    "memory_id": one.memory_id, "event_id": event_id}), "not_found")
            first = (await client.call_tool("memory.get_source", {"memory_id": one.memory_id,
                                                                "limit": 1})).structured_content
            assert first["sources"][0]["event_id"] == "event-oomp"
            assert first["next_event_id"] == "event-oomp"
            second_page = (await client.call_tool("memory.get_source", {
                "memory_id": one.memory_id, "limit": 1, "after_event_id": first["next_event_id"]})).structured_content
            assert second_page["sources"][0]["event_id"] == "second-proof"
            assert second_page["next_event_id"] is None
    with running_http(config):
        run(scenario())


def test_semantic_failure_explicit_degradation_and_empty_budget(populated):
    config = configuration(populated[0], http=True)
    async def scenario():
        async with http_client(config) as client:
            for mode in ("semantic", "hybrid"):
                assert_error(await client.call_tool("memory.retrieve", {"query": "OOMP", "mode": mode}),
                             "embedding_unavailable")
            degraded = await client.call_tool("memory.retrieve", {
                "query": "OOMP", "mode": "hybrid", "allow_degraded": True, "token_budget": 12000})
            assert degraded.structured_content["degraded"] is True
            assert degraded.structured_content["warnings"]
            assert degraded.structured_content["memories"]
            empty = await client.call_tool("memory.retrieve", {"query": "OOMP", "token_budget": 1})
            assert empty.structured_content["memories"] == []
            assert empty.structured_content["context_packet"] == ""
            assert empty.structured_content["estimated_token_count"] == 0
    with running_http(config):
        run(scenario())


def test_concurrent_scopes_disconnect_and_worker_writes_do_not_duplicate_indexes(populated):
    path = populated[0]
    config = configuration(path, http=True)
    # Finish the fixture's explicit intake before measuring reconnect behavior.
    MindWorker(path, scope()).run_once(max_jobs=16)
    before = SQLiteMemoryStore(path).count_memories(scope())
    expected_a = {m.memory_id for m in SQLiteMemoryStore(path).list_memories(scope()).memories}
    SQLiteEventStore(path).append(scope(), event("concurrent-worker", content="I prefer Rust."))
    async def scoped(token, expected):
        async with http_client(config, token) as client:
            for _ in range(3):
                result = await client.call_tool("memory.retrieve", {"query": "OOMP", "token_budget": 12000})
                assert not result.is_error
                assert {m["memory_id"] for m in result.structured_content["memories"]} == expected
    async def short():
        async with http_client(config) as client:
            assert not (await client.call_tool("memory.status", {})).is_error
        # This disconnect occurs while the independent scoped clients continue.
    async def scenario():
        await asyncio.gather(
            scoped(TOKEN_A, expected_a),
            scoped(TOKEN_B, {"mem-private"}), short(),
            asyncio.to_thread(MindWorker(path, scope()).run_once, max_jobs=16),
        )
        async with http_client(config) as client:
            result = await client.call_tool("memory.retrieve", {"query": "Rust"})
            assert any("Rust" in m["canonical_content"] for m in result.structured_content["memories"])
    with running_http(config):
        run(scenario())
    after = SQLiteMemoryStore(path).count_memories(scope())
    assert after == before + 1
    # Restart with the same durable storage. No MCP connection creates an index.
    with running_http(config):
        async def reopened():
            async with http_client(config) as client:
                result = await client.call_tool("memory.status", {})
                assert result.structured_content["index"]["canonical_count"] == after
                assert result.structured_content["index"]["lexical_count"] == after
        run(reopened())


def test_concurrency_limit_is_nonblocking_and_internal_errors_are_sanitized(populated, monkeypatch, caplog):
    config = configuration(populated[0], http=True, max_concurrent_calls=1)
    entered, release = threading.Event(), threading.Event()
    with running_http(config) as server:
        original = server.service.retrieval.retrieve
        def blocked(*args):
            entered.set()
            assert release.wait(10)
            return original(*args)
        monkeypatch.setattr(server.service.retrieval, "retrieve", blocked)
        async def slow():
            async with http_client(config) as client:
                return await client.call_tool("memory.retrieve", {"query": "OOMP"})
        async def probe():
            assert await asyncio.to_thread(entered.wait, 10)
            async with http_client(config) as client:
                try:
                    assert_error(await client.call_tool("memory.status", {}), "busy")
                finally:
                    release.set()
        async def scenario():
            first, _ = await asyncio.gather(slow(), probe())
            assert not first.is_error
            def broken(*args):
                raise RuntimeError("PRIVATE-DATABASE-PATH SECRET-CONTENT " + TOKEN_A)
            monkeypatch.setattr(server.service.retrieval, "retrieve", broken)
            async with http_client(config) as client:
                result = await client.call_tool("memory.retrieve", {"query": "PRIVATE-QUERY"})
                assert_error(result, "internal_error")
                assert "PRIVATE-" not in result.model_dump_json()
        run(scenario())
    assert "PRIVATE-" not in caplog.text


def test_result_size_and_graph_bounds_fail_without_truncating_evidence(populated):
    config = configuration(populated[0], http=True, max_result_bytes=4096)
    async def scenario():
        async with http_client(config) as client:
            large = await client.call_tool("memory.retrieve", {"query": "OOMP", "token_budget": 12000})
            assert_error(large, "resource_limit")
            small = await client.call_tool("memory.expand", {"memory_id": "mem-oomp", "max_nodes": 1})
            assert small.structured_content["truncated"] is True
            assert len(small.structured_content["memories"]) == 1
            assert small.structured_content["edges"] == []
    with running_http(config):
        run(scenario())


def test_sdk_legacy_http_mode_on_stateless_transport(populated):
    config = configuration(populated[0], http=True)
    async def scenario():
        async with http_client(config, mode="legacy") as client:
            assert client.protocol_version != "2026-07-28"
            assert {t.name for t in (await client.list_tools()).tools} == READ_TOOLS
            assert not (await client.call_tool("memory.status", {})).is_error
    with running_http(config):
        run(scenario())


def test_http_cli_process_restart_and_secret_free_logs(populated, tmp_path):
    config = configuration(populated[0], http=True)
    file = tmp_path / "HTTP server config.json"
    file.write_text(config.model_dump_json(), encoding="utf-8")
    output = tmp_path / "server-output.txt"
    command = [sys.executable, "-m", "oomp", "mcp", "serve", "--config", str(file)]
    async def probe():
        async with http_client(config) as client:
            result = await client.call_tool("memory.retrieve", {"query": "OOMP", "token_budget": 12000})
            assert {m["memory_id"] for m in result.structured_content["memories"]} == {"mem-oomp", "mem-python"}
    with output.open("wb") as log:
        for _ in range(2):
            process = subprocess.Popen(command, stdout=log, stderr=log, env={**os.environ, **ENVIRONMENT},
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        pytest.fail("CLI server exited before readiness")
                    try:
                        with socket.create_connection((config.host, config.port), timeout=.1):
                            break
                    except OSError:
                        time.sleep(.05)
                else:
                    pytest.fail("CLI server readiness timeout")
                run(probe())
            finally:
                process.terminate()
                process.wait(10)
    logged = output.read_text(encoding="utf-8")
    assert not logged.strip(), logged

def test_identical_ids_and_foreign_statistics_never_change_authorized_ranking(populated):
    path = populated[0]
    config = configuration(path, http=True)
    async def scenario():
        async with http_client(config) as client:
            arguments = {"query": "OOMP", "token_budget": 12000}
            before = (await client.call_tool("memory.retrieve", arguments)).structured_content
            await asyncio.to_thread(add_memory, path, "oomp",
                "FOREIGN-SAME-ID-SECRET OOMP OOMP OOMP OOMP.", scope("other"))
            after = (await client.call_tool("memory.retrieve", arguments)).structured_content
            assert before["memories"] == after["memories"]
            assert before["retrieval_trace"] == after["retrieval_trace"]
            assert "FOREIGN-" not in json.dumps(after)
        async with http_client(config, TOKEN_B) as client:
            result = await client.call_tool("memory.retrieve", {"query": "OOMP", "token_budget": 12000})
            assert any(m["memory_id"] == "mem-oomp" and "FOREIGN-SAME-ID" in m["canonical_content"]
                       for m in result.structured_content["memories"])
    with running_http(config):
        run(scenario())


def test_sdk_rejects_protocol_and_routing_header_mismatches(populated):
    from mcp_types import PROTOCOL_VERSION_META_KEY, CLIENT_CAPABILITIES_META_KEY
    config = configuration(populated[0], http=True)
    async def scenario():
        headers = {
            "Authorization": "Bearer " + TOKEN_A, "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2026-07-28", "MCP-Method": "tools/call", "MCP-Name": "memory.status",
        }
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "memory.status", "arguments": {}, "_meta": {
                PROTOCOL_VERSION_META_KEY: "2026-07-28", CLIENT_CAPABILITIES_META_KEY: {}}}}
        async with httpx2.AsyncClient(trust_env=False) as client:
            good = await client.post(config.endpoint, headers=headers, json=body)
            assert good.status_code == 200
            assert good.json()["result"]["structuredContent"]["read_only"] is True
            for changed in (
                {"MCP-Method": "tools/list"}, {"MCP-Name": "memory.ingest"},
                {"MCP-Protocol-Version": "2099-01-01"},
            ):
                bad = await client.post(config.endpoint, headers={**headers, **changed}, json=body)
                assert bad.status_code == 400
                assert "error" in bad.json()
            oversized = await client.post(config.endpoint, headers={
                **headers, "X-Private": "a" * 9000}, json=body)
            assert oversized.status_code == 431
    with running_http(config):
        run(scenario())


def test_retracted_proof_is_not_exposed_as_current_source_or_graph(populated):
    from oomp.storage.mind_projection_store import SQLiteMindProjectionStore
    path, one, _ = populated
    cutoff = datetime.now(timezone.utc)
    SQLiteMindProjectionStore(path).retract_source(scope(), one.memory_id, "event-oomp", reason_code="evidence_withdrawn")
    config = configuration(path, http=True)
    async def scenario():
        async with http_client(config) as client:
            assert_error(await client.call_tool("memory.get_source", {"memory_id": one.memory_id}), "not_found")
            assert_error(await client.call_tool("memory.expand", {"memory_id": one.memory_id}), "not_found")
            before = await client.call_tool("memory.get_source", {"memory_id": one.memory_id, "known_at": cutoff.isoformat()})
            assert before.structured_content["sources"][0]["event_id"] == "event-oomp"
    with running_http(config):
        run(scenario())