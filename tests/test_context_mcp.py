"""Opt-in context over the real MCP boundary and disposable synthetic storage."""
from datetime import datetime, timezone
import builtins
import json
import sys

import pytest

pytest.importorskip("mcp", reason="install [mcp] for context protocol acceptance")
from mcp import Client, StdioServerParameters

from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
from oomp.mcp.authorization import GrantResolver
from oomp.mcp.configuration import ServerConfiguration
from oomp.mcp.contracts import ContextArguments, RetrieveArguments
from oomp.mcp.errors import BoundaryError
from oomp.mcp.service import MemoryService
from oomp.objects.service import ObjectMap
from oomp.storage.sqlite import SQLiteEventStore
from oomp.understanding.engine import UnderstandingEngine
from test_stage7_mcp import (
    READ_TOOLS, TOKEN_RAW, assert_error, configuration, http_client,
    reader, run, running_http,
)

SCOPE = AuthorizedScope(tenant_id="tenant", namespace="personal", principal_id="host-a")
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def append(path, scope, identifier, content):
    event = MemoryEvent(event_id=identifier, tenant_id=scope.tenant_id, namespace=scope.namespace,
        event_type="user_message", source_type="user", content=content,
        occurred_at=NOW, ingested_at=NOW, metadata={"ingested_by": scope.principal_id},
        source_reference=SourceReference(source_system="synthetic-context", external_event_id=identifier,
            timestamp=NOW, session_id="synthetic-context-session", turn_id=identifier))
    store = SQLiteEventStore(path)
    store.append(scope, event)
    UnderstandingEngine(path).process_event(scope, event.event_id)
    ObjectMap(path).build(scope, limit=100)
    return event


@pytest.fixture
def context_db(tmp_path):
    path = tmp_path / "context.sqlite3"
    SQLiteEventStore(path).initialize()
    event = append(path, SCOPE, "owned-style", "I prefer concise technical explanations.")
    append(path, SCOPE.model_copy(update={"principal_id": "other-principal"}),
           "foreign-principal", "I prefer PRIVATE-OTHER-PRINCIPAL responses.")
    append(path, SCOPE.model_copy(update={"tenant_id": "another-tenant"}),
           "foreign-tenant", "I prefer PRIVATE-OTHER-TENANT responses.")
    return path, event


def test_context_is_disabled_by_default_and_legacy_catalog_is_unchanged(context_db):
    path, _ = context_db
    config = configuration(path, http=True)
    assert config.context_enabled is False
    async def scenario():
        async with http_client(config) as client:
            assert {tool.name for tool in (await client.list_tools()).tools} == READ_TOOLS
            assert_error(await client.call_tool("memory.context", {"query": "What response style?"}), "not_found")
    with running_http(config):
        run(scenario())


def test_opt_in_stdio_context_contract_and_principal_isolation(context_db, tmp_path):
    path, event = context_db
    config = configuration(path, context_enabled=True)
    file = tmp_path / "context-server.json"
    file.write_text(config.model_dump_json(), encoding="utf-8")
    async def scenario():
        async with Client(StdioServerParameters(command=sys.executable, args=[
            "-B", "-m", "oomp", "mcp", "serve", "--config", str(file)])) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            assert set(tools) == READ_TOOLS | {"memory.context"}
            tool = tools["memory.context"]
            assert tool.annotations.read_only_hint and not tool.annotations.destructive_hint
            assert tool.input_schema["additionalProperties"] is False
            assert not {"tenant_id", "namespace", "principal_id"} & set(tool.input_schema["properties"])
            result = await client.call_tool("memory.context", {"query": "What response style do I prefer?", "token_budget": 12000})
            assert not result.is_error
            value = result.structured_content
            assert value["context_contract_version"] == "oomp.context.v1"
            assert value["budget_scope"] == "context_packet_only" and value["source_data_untrusted"]
            assert value["evidence_packets"]
            assert value.get("query_plan") is None
            assert len(value["context_packet"].encode("utf-8")) == value["selected_context_bytes"] <= 12000
            assert json.loads(value["context_packet"])["evidence_packets"]
            proofs = [p for unit in value["evidence_packets"] for p in unit["source_proofs"]]
            assert {p["event_id"] for p in proofs} == {event.event_id}
            assert all(p.get("quote") is None for p in proofs)
            assert "PRIVATE-OTHER-" not in result.model_dump_json()
    run(scenario())


def test_context_rejects_client_scope_and_raw_content_without_grant(context_db):
    path, _ = context_db
    config = configuration(path, http=True, context_enabled=True)
    async def scenario():
        async with http_client(config) as client:
            for field in ("tenant_id", "namespace", "principal_id"):
                assert_error(await client.call_tool("memory.context", {
                    "query": "What response style?", field: "foreign"}), "invalid_parameters")
            assert_error(await client.call_tool("memory.context", {
                "query": "What response style?", "include_source_content": True}), "forbidden")
            malformed = await client.call_tool("memory.context", {
                "query": "PRIVATE-QUERY-MUST-NOT-LEAK", "token_budget": 0})
            assert_error(malformed, "invalid_parameters")
            assert "PRIVATE-QUERY-MUST-NOT-LEAK" not in malformed.model_dump_json()
    with running_http(config):
        run(scenario())


def test_authorized_raw_source_and_explicit_explanation_use_original_proofs(context_db):
    path, event = context_db
    config = configuration(path, http=True, context_enabled=True,
        http_grants=(reader(raw=True, token="TOKEN_RAW"),))
    async def scenario():
        async with http_client(config, TOKEN_RAW) as client:
            result = await client.call_tool("memory.context", {
                "query": "What response style do I prefer?", "token_budget": 12000,
                "include_source_content": True, "explain": True})
            assert not result.is_error
            value = result.structured_content
            assert value["query_plan"] is not None
            proofs = [p for unit in value["evidence_packets"] for p in unit["source_proofs"]]
            assert proofs
            for proof in proofs:
                assert proof["event_id"] == event.event_id
                assert proof["quote"] == event.content[proof["span_start"]:proof["span_end"]]
    with running_http(config):
        run(scenario())


def test_disabled_direct_service_context_cannot_import_or_run_orchestrator(context_db, monkeypatch):
    path, _ = context_db
    config = configuration(path)
    resolver = GrantResolver(config, environ={})
    service = MemoryService(config, resolver)
    # Disabled check must happen before the lazy engine import or any selection.
    original_import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        if name == "oomp.context.engine":
            raise AssertionError("disabled context attempted to import the orchestrator")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    with pytest.raises(BoundaryError, match="not_found"):
        service.context(config.stdio_grant, ContextArguments(query="What response style?"))


def test_context_opt_in_does_not_change_existing_retrieve_result(context_db):
    path, _ = context_db
    disabled = configuration(path)
    enabled = ServerConfiguration.model_validate({**disabled.model_dump(mode="json"), "context_enabled": True})
    old_service = MemoryService(disabled, GrantResolver(disabled, environ={}))
    new_service = MemoryService(enabled, GrantResolver(enabled, environ={}))
    query = RetrieveArguments(query="prefer technical", token_budget=12000, graph_depth=0)
    before = old_service.retrieve(disabled.stdio_grant, query).model_dump(mode="json")
    after = new_service.retrieve(enabled.stdio_grant, query).model_dump(mode="json")
    assert before == after
    assert "context_contract_version" not in after and "evidence_packets" not in after
