"""Independent host validation and public SDK wiring; no server or model runs."""
from copy import deepcopy
import asyncio
import builtins
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "examples/generic_context_host.py"


def load_host():
    spec = importlib.util.spec_from_file_location("generic_context_host_example", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HOST = load_host()
TOKEN = "synthetic-example-bearer-" + "x" * 32
ENVIRONMENT = {"MCP_BEARER_TOKEN": TOKEN}


def omit_none(value):
    if isinstance(value, dict):
        return {key: omit_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [omit_none(item) for item in value]
    return value


def seal(data):
    packet = {"context_contract_version": HOST.VERSION, "counting_method": HOST.COUNTING,
              "token_budget": data["token_budget"], "evidence_packets": omit_none(data["evidence_packets"]),
              "selected_context_bytes": 0}
    for _ in range(16):
        encoded = json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
        measured = len(encoded.encode("utf-8"))
        if packet["selected_context_bytes"] == measured:
            data.update(context_packet=encoded, selected_context_bytes=measured)
            return data
        packet["selected_context_bytes"] = measured
    raise AssertionError("test packet accounting failed")


@pytest.fixture
def context():
    reference = {"source_system": "synthetic-example", "external_event_id": "event-1",
                 "timestamp": "2026-01-01T00:00:00Z", "session_id": None, "turn_id": None, "locator": None}
    proof = {"memory_id": "memory-1", "event_id": "event-1", "source_reference": reference,
             "span_start": 0, "span_end": 14, "quote": None}
    unit = {"unit_id": "unit-1", "resolution": "canonical_fact", "content": "I prefer café.",
            "memory_ids": ["memory-1"], "source_proofs": [proof], "object_ids": [], "revision_id": None,
            "source_fingerprint": None, "assertion_kinds": ["explicit"], "temporal_status": "current",
            "selection_reasons": [], "retrieval_score": None, "derived": False, "uncertain": False}
    return seal({"context_contract_version": HOST.VERSION, "counting_method": HOST.COUNTING,
                 "budget_scope": "context_packet_only", "source_data_untrusted": True,
                 "retrieval_status": "found_relevant_evidence", "token_budget": 6000,
                 "evidence_packets": [unit], "source_references": [reference]})


def fake_sdk(monkeypatch, context, *, linked=None, error=None, names=("memory.context", "memory.get_source")):
    seen = {"calls": []}
    transport = object()

    class HTTP:
        def __init__(self, **kwargs):
            seen["http"] = kwargs
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            pass

    def streamable_http_client(endpoint, *, http_client):
        seen["endpoint"] = endpoint
        assert isinstance(http_client, HTTP)
        return transport

    class Client:
        def __init__(self, supplied):
            assert supplied is transport
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            pass
        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name=name) for name in names])
        async def call_tool(self, name, arguments):
            seen["calls"].append((name, arguments))
            if error:
                raise error
            return SimpleNamespace(is_error=False, structured_content=context if name == "memory.context" else linked)

    modules = {name: ModuleType(name) for name in ("httpx2", "mcp", "mcp.client", "mcp.client.streamable_http")}
    modules["httpx2"].AsyncClient = HTTP
    modules["mcp"].Client = Client
    modules["mcp.client.streamable_http"].streamable_http_client = streamable_http_client
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    return seen


def test_import_is_inert_and_does_not_import_server_or_sdk(monkeypatch):
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        assert name.split(".")[0] not in {"oomp", "trace", "mcp", "httpx2"}
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    assert load_host().VERSION == HOST.VERSION


def test_sdk_read_only_calls_use_env_bearer_and_validate_optional_source(monkeypatch, context):
    proof = context["evidence_packets"][0]["source_proofs"][0]
    linked = {"memory_id": proof["memory_id"], "source_data_untrusted": True, "next_event_id": None,
              "sources": [{"event_id": proof["event_id"], "event_type": "user_message", "source_type": "user",
                           "source_reference": proof["source_reference"], "occurred_at": "2026-01-01T00:00:00Z",
                           "ingested_at": "2026-01-01T00:00:00Z", "content": None}]}
    seen = fake_sdk(monkeypatch, context, linked=linked)
    result = asyncio.run(HOST.read_context("What is my preference?", environment=ENVIRONMENT, get_source=True))
    assert seen["endpoint"] == HOST.DEFAULT_ENDPOINT
    assert seen["http"] == {"headers": {"Authorization": "Bearer " + TOKEN}, "trust_env": False,
                            "timeout": 5, "follow_redirects": False}
    assert seen["calls"] == [
        ("memory.context", {"query": "What is my preference?", "token_budget": 6000, "max_results": 8,
                            "include_source_content": False}),
        ("memory.get_source", {"memory_id": "memory-1", "event_id": "event-1", "include_content": False, "limit": 1}),
    ]
    assert result["linked_source_checked"] is True and result["source_proofs"] == 1
    assert TOKEN not in json.dumps(result) and "café" not in json.dumps(result)
    assert result["packet_bytes"] > len(context["context_packet"])


@pytest.mark.parametrize("endpoint", ["http://example.com/mcp", "http://localhost/mcp", "https://127.0.0.1/mcp",
                                     "http://127.0.0.1:0/mcp", "http://127.0.0.1/mcp?token=secret",
                                     "http://user:secret@127.0.0.1/mcp", "http://127.0.0.1/mcp#secret"])
def test_unsafe_endpoints_are_rejected_before_sdk_import(endpoint, monkeypatch):
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        assert name not in {"mcp", "httpx2"}
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    with pytest.raises(HOST.HostError):
        asyncio.run(HOST.read_context("query", environment={**ENVIRONMENT, "MCP_ENDPOINT": endpoint}))


@pytest.mark.parametrize("change", ["version", "bytes", "boolean_bytes", "packet_evidence", "proof_memory",
                                   "proof_span", "raw_quote", "reference", "missing_proof", "duplicate_proof"])
def test_malformed_packet_and_proofs_fail_closed_before_source_call(change, monkeypatch, context):
    unit = context["evidence_packets"][0]
    if change == "version":
        context["context_contract_version"] = "future.context.v9"
    elif change == "bytes":
        context["selected_context_bytes"] -= 1
    elif change == "boolean_bytes":
        context["selected_context_bytes"] = True
    elif change == "packet_evidence":
        unit["content"] = "Different unsupported content"
    elif change == "reference":
        context["source_references"] = []
    else:
        proof = unit["source_proofs"][0]
        if change == "proof_memory":
            proof["memory_id"] = "other-memory"
        elif change == "proof_span":
            proof["span_start"] = True
        elif change == "raw_quote":
            proof["quote"] = "I prefer café."
        elif change == "missing_proof":
            unit["source_proofs"] = []
        elif change == "duplicate_proof":
            unit["source_proofs"].append(deepcopy(proof))
        seal(context)
    seen = fake_sdk(monkeypatch, context)
    with pytest.raises(HOST.HostError):
        asyncio.run(HOST.read_context("query", environment=ENVIRONMENT, get_source=True))
    assert [name for name, _ in seen["calls"]] == ["memory.context"]


def test_duplicate_json_keys_are_rejected(context):
    packet = context["context_packet"].replace('"context_contract_version":',
        '"context_contract_version":"ignored","context_contract_version":', 1)
    context.update(context_packet=packet, selected_context_bytes=len(packet.encode("utf-8")))
    with pytest.raises(HOST.HostError, match="duplicate_json_key"):
        HOST.validate_context(context, 6000, 8)


def test_empty_context_skips_optional_source_lookup(monkeypatch):
    empty = {"context_contract_version": HOST.VERSION, "counting_method": HOST.COUNTING,
             "budget_scope": "context_packet_only", "source_data_untrusted": True,
             "retrieval_status": "no_relevant_evidence", "token_budget": 6000,
             "evidence_packets": [], "source_references": [], "context_packet": "", "selected_context_bytes": 0}
    seen = fake_sdk(monkeypatch, empty)
    result = asyncio.run(HOST.read_context("query", environment=ENVIRONMENT, get_source=True))
    assert result["linked_source_checked"] is False and len(seen["calls"]) == 1


def test_missing_context_tool_fails_without_calling_another_tool(monkeypatch, context):
    seen = fake_sdk(monkeypatch, context, names=("memory.retrieve",))
    with pytest.raises(HOST.HostError, match="required_read_tool_unavailable"):
        asyncio.run(HOST.read_context("query", environment=ENVIRONMENT))
    assert seen["calls"] == []


def test_main_suppresses_sensitive_sdk_exception_text(monkeypatch, context, capsys):
    monkeypatch.setenv("MCP_BEARER_TOKEN", TOKEN)
    fake_sdk(monkeypatch, context, error=RuntimeError("server echoed Bearer " + TOKEN))
    assert HOST.main(["query"]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == "generic_context_host_failed\n"
    assert TOKEN not in captured.out + captured.err


def test_main_suppresses_sdk_logs_and_restores_callers_logging(monkeypatch, capsys):
    import logging
    previous = logging.root.manager.disable
    async def noisy_sdk(*args, **kwargs):
        logging.getLogger('mcp').error('Untrusted SDK text Bearer ' + TOKEN)
        raise RuntimeError('Untrusted failure ' + TOKEN)
    monkeypatch.setattr(HOST, 'read_context', noisy_sdk)
    assert HOST.main(['query']) == 1
    captured = capsys.readouterr()
    assert captured.out == '' and captured.err == 'generic_context_host_failed\n'
    assert logging.root.manager.disable == previous
