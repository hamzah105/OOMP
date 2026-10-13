"""Stage 1 contract and CLI behavior tests; no external services required."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from oomp import __version__
from oomp import cli
from oomp.domain.enums import EventType, MemoryStatus, MemoryType, RelationshipType, SourceType
from oomp.domain.models import (
    AuthorizedScope,
    MemoryEdge,
    MemoryEvent,
    MemoryNode,
    RequestedScope,
    SourceReference,
)
from oomp.retrieval.contracts import GraphPath, MemoryEvidence, RetrievalRequest, RetrievalResponse

NOW = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)


def reference(**changes):
    fields = dict(source_system="local", external_event_id="source-1", timestamp=NOW)
    fields.update(changes)
    return SourceReference(**fields)


def event(**changes):
    fields = dict(
        event_id="event-1", tenant_id="tenant-1", namespace="personal",
        event_type=EventType.USER_MESSAGE, source_type=SourceType.USER,
        content="I prefer Python.", source_reference=reference(),
        occurred_at=NOW, ingested_at=NOW,
    )
    fields.update(changes)
    return MemoryEvent(**fields)


def node(**changes):
    fields = dict(
        memory_id="memory-1", tenant_id="tenant-1", namespace="personal",
        memory_type=MemoryType.PROFILE, canonical_content="Prefers Python",
        canonical_key="language.preference", source_event_ids=("event-1",),
        provenance=(reference(),), created_at=NOW, updated_at=NOW,
    )
    fields.update(changes)
    return MemoryNode(**fields)


def edge(**changes):
    fields = dict(
        edge_id="edge-1", tenant_id="tenant-1", namespace="personal",
        source_node_id="memory-1", target_node_id="topic-1",
        relationship_type=RelationshipType.ABOUT,
        source_event_ids=("event-1",), created_at=NOW,
    )
    fields.update(changes)
    return MemoryEdge(**fields)


def evidence(**changes):
    fields = dict(
        memory_id="memory-1", canonical_content="Prefers Python",
        memory_type=MemoryType.PROFILE, source_references=(reference(),),
    )
    fields.update(changes)
    return MemoryEvidence(**fields)


@pytest.mark.parametrize(
    ("event_type", "source_type"),
    [
        (EventType.USER_MESSAGE, SourceType.USER),
        (EventType.ASSISTANT_MESSAGE, SourceType.ASSISTANT),
        (EventType.DOCUMENT, SourceType.DOCUMENT),
        (EventType.TOOL_RESULT, SourceType.TOOL),
        (EventType.CORRECTION, SourceType.USER),
        (EventType.FEEDBACK, SourceType.USER),
    ],
)
def test_event_types_and_source_roles(event_type, source_type):
    assert event(event_type=event_type, source_type=source_type).event_type is event_type


@pytest.mark.parametrize(
    ("event_type", "wrong_source"),
    [
        (EventType.USER_MESSAGE, SourceType.ASSISTANT),
        (EventType.ASSISTANT_MESSAGE, SourceType.USER),
        (EventType.DOCUMENT, SourceType.TOOL),
        (EventType.TOOL_RESULT, SourceType.DOCUMENT),
    ],
)
def test_original_source_role_is_not_silently_mislabelled(event_type, wrong_source):
    with pytest.raises(ValidationError):
        event(event_type=event_type, source_type=wrong_source)


def test_event_requires_content_reference_and_valid_identity():
    for changes in (
        {"content": " \n "}, {"source_reference": None},
        {"event_id": ""}, {"event_id": "invalid/path"},
        {"event_type": "unknown"}, {"tenant_id": " tenant"},
    ):
        with pytest.raises(ValidationError):
            event(**changes)
    assert event(content="  exact source text  ").content == "  exact source text  "


def test_source_reference_fields_and_utc_timestamp():
    ref = reference(session_id="session-1", turn_id="turn-1", locator="p. 2")
    assert ref.timestamp == NOW
    assert ref.session_id == "session-1"
    for changes in (
        {"source_system": ""}, {"external_event_id": "  "},
        {"timestamp": NOW.replace(tzinfo=None)}, {"session_id": "bad/path"},
        {"locator": "  "},
    ):
        with pytest.raises(ValidationError):
            reference(**changes)


@pytest.mark.parametrize("memory_type", list(MemoryType))
def test_every_memory_type_is_a_valid_canonical_node(memory_type):
    assert node(memory_type=memory_type).memory_type is memory_type


@pytest.mark.parametrize("relationship_type", list(RelationshipType))
def test_every_relationship_type_is_a_valid_edge(relationship_type):
    assert edge(relationship_type=relationship_type).relationship_type is relationship_type


@pytest.mark.parametrize("status", list(MemoryStatus))
def test_memory_and_edge_statuses(status):
    assert node(status=status).status is status
    assert edge(status=status).status is status


def test_memory_identity_provenance_and_uncertainty():
    memory = node()
    assert memory.confidence is None
    assert memory.source_event_ids == ("event-1",)
    assert memory.provenance == (reference(),)
    for changes in (
        {"memory_id": "bad/path"}, {"canonical_content": " "},
        {"canonical_key": " "}, {"source_event_ids": ()},
        {"provenance": ()}, {"status": "unverified"}, {"memory_type": "guess"},
    ):
        with pytest.raises(ValidationError):
            node(**changes)


def test_edge_requires_evidence_and_valid_relationship():
    assert edge().confidence is None
    for changes in (
        {"source_event_ids": ()}, {"relationship_type": "IS_A"},
        {"source_node_id": ""}, {"status": "deleted"},
    ):
        with pytest.raises(ValidationError):
            edge(**changes)


@pytest.mark.parametrize("bad", [-0.01, 1.01, float("nan"), float("inf"), True, "0.5"])
def test_confidence_rejects_invalid_or_unmeasured_values(bad):
    with pytest.raises(ValidationError):
        node(confidence=bad)
    with pytest.raises(ValidationError):
        edge(confidence=bad)


def test_confidence_accepts_measured_numeric_boundaries():
    assert node(confidence=0).confidence == 0.0
    assert edge(confidence=1).confidence == 1.0


@pytest.mark.parametrize("factory", [event, node, edge, reference])
def test_naive_timestamps_are_rejected(factory):
    field = {
        event: "occurred_at", node: "created_at",
        edge: "created_at", reference: "timestamp",
    }[factory]
    with pytest.raises(ValidationError):
        factory(**{field: NOW.replace(tzinfo=None)})


def test_temporal_order_and_half_open_validity():
    with pytest.raises(ValidationError):
        node(updated_at=NOW - timedelta(seconds=1))
    for factory in (node, edge, evidence):
        with pytest.raises(ValidationError):
            factory(valid_from=NOW, valid_until=NOW - timedelta(microseconds=1))
        assert factory(valid_from=NOW, valid_until=NOW).valid_until == NOW
        assert factory(valid_from=None, valid_until=None).valid_from is None


def test_all_timestamps_normalize_to_utc_and_json_z():
    offset = timezone(timedelta(hours=5))
    local = NOW.astimezone(offset)
    ref = reference(timestamp=local)
    source = event(source_reference=ref, occurred_at=local, ingested_at=local)
    memory = node(created_at=local, updated_at=local, valid_from=local, valid_until=local)
    assert source.occurred_at == NOW
    assert source.occurred_at.utcoffset() == timedelta(0)
    assert source.ingested_at == NOW
    assert memory.valid_from == NOW
    assert "+05:00" not in source.model_dump_json()
    assert "2026-01-02T03:04:00Z" in source.model_dump_json()
    assert MemoryEvent.model_validate_json(source.model_dump_json()) == source
    assert MemoryNode.model_validate_json(memory.model_dump_json()) == memory


def test_event_occurrence_and_ingestion_are_independent():
    later = NOW + timedelta(days=3)
    source = event(ingested_at=later)
    assert source.occurred_at == NOW
    assert source.ingested_at == later


@pytest.mark.parametrize("value", ["", " ", "bad/path", ".hidden", "x" * 129])
def test_invalid_scope_components_rejected(value):
    for field in ("tenant_id", "namespace"):
        with pytest.raises(ValidationError):
            RequestedScope(**{"tenant_id": "tenant-1", "namespace": "personal", field: value})
    with pytest.raises(ValidationError):
        AuthorizedScope(tenant_id="tenant-1", namespace="personal", principal_id=value)


def test_requested_and_authorized_scopes_are_distinct():
    requested = RequestedScope(tenant_id="tenant-1", namespace="personal")
    authorized = AuthorizedScope(tenant_id="tenant-1", namespace="personal", principal_id="alice")
    assert not hasattr(requested, "principal_id")
    assert authorized.principal_id == "alice"
    with pytest.raises(ValidationError):
        AuthorizedScope(tenant_id="tenant-1", namespace="personal")


def test_metadata_defaults_are_independent_and_explicit_null_is_invalid():
    first, second = event(), event(event_id="event-2")
    assert first.metadata == second.metadata == {}
    with pytest.raises(TypeError):
        first.metadata["new"] = 1
    with pytest.raises(ValidationError):
        event(metadata=None)


def test_metadata_is_deeply_immutable_detached_and_roundtrips():
    data = {"nested": {"items": [1, {"ok": True}]}}
    source = event(metadata=data)
    data["nested"]["items"].append("later")
    assert source.metadata["nested"]["items"] == (1, {"ok": True})
    with pytest.raises(TypeError):
        source.metadata["nested"]["items"][1]["ok"] = False
    wire = source.model_dump_json()
    assert json.loads(wire)["metadata"]["nested"]["items"] == [1, {"ok": True}]
    assert MemoryEvent.model_validate_json(wire) == source


def test_metadata_rejects_non_json_values_nonfinite_numbers_and_cycles():
    cycle = []
    cycle.append(cycle)
    for metadata in (
        {"bad": float("nan")}, {"bad": float("inf")},
        {"bad": {1}}, {"bad": cycle}, {1: "not a string key"},
    ):
        with pytest.raises(ValidationError):
            event(metadata=metadata)


def test_event_and_memory_are_frozen():
    with pytest.raises(ValidationError):
        event().content = "rewritten"
    with pytest.raises(ValidationError):
        node().canonical_content = "rewritten"


def test_retrieval_request_defaults_and_utc_as_of():
    request = RetrievalRequest(
        tenant_id="tenant-1", namespace="personal", query="What language?"
    )
    assert request.max_results == 8
    assert request.token_budget == 1200
    assert request.as_of is None
    local = NOW.astimezone(timezone(timedelta(hours=5)))
    assert RetrievalRequest(**request.model_dump(exclude={"as_of"}), as_of=local).as_of == NOW


@pytest.mark.parametrize("value", [0, -1, 101, True, 2.5, "8"])
def test_invalid_result_limits(value):
    with pytest.raises(ValidationError):
        RetrievalRequest(tenant_id="tenant-1", namespace="personal", query="q", max_results=value)


@pytest.mark.parametrize("value", [0, -1, 32769, True, 2.5, "1200"])
def test_invalid_token_budgets(value):
    with pytest.raises(ValidationError):
        RetrievalRequest(tenant_id="tenant-1", namespace="personal", query="q", token_budget=value)


def test_query_and_as_of_validation():
    for query in ("", " \n "):
        with pytest.raises(ValidationError):
            RetrievalRequest(tenant_id="tenant-1", namespace="personal", query=query)
    with pytest.raises(ValidationError):
        RetrievalRequest(
            tenant_id="tenant-1", namespace="personal", query="q",
            as_of=NOW.replace(tzinfo=None),
        )


def test_empty_retrieval_response_and_nonnegative_count():
    response = RetrievalResponse(retrieval_id="ret-1")
    assert response.memories == response.source_references == response.graph_paths == ()
    assert response.estimated_token_count == 0
    assert RetrievalResponse.model_validate_json(response.model_dump_json()) == response
    for count in (-1, True, "1"):
        with pytest.raises(ValidationError):
            RetrievalResponse(retrieval_id="ret-1", estimated_token_count=count)


def test_evidence_requires_sources_and_path_shape():
    path = GraphPath(
        node_ids=("memory-1", "topic-1"), edge_ids=("edge-1",),
        relationship_types=(RelationshipType.ABOUT,),
    )
    result = evidence(graph_paths=(path,), retrieval_score=3)
    assert result.retrieval_score == 3.0
    assert result.source_references == (reference(),)
    assert MemoryEvidence.model_validate_json(result.model_dump_json()) == result
    for changes in (
        {"source_references": ()}, {"retrieval_score": True},
        {"retrieval_score": "0.5"}, {"retrieval_score": float("nan")},
    ):
        with pytest.raises(ValidationError):
            evidence(**changes)
    with pytest.raises(ValidationError):
        GraphPath(node_ids=("one", "two"))
    with pytest.raises(ValidationError):
        GraphPath(node_ids=("one",), edge_ids=("edge-1",), relationship_types=(RelationshipType.ABOUT,))


def test_retrieval_evidence_metadata_is_frozen():
    result = evidence(metadata={"nested": [1, 2]})
    with pytest.raises(TypeError):
        result.metadata["new"] = 1
    assert json.loads(result.model_dump_json())["metadata"] == {"nested": [1, 2]}


def _run_cli(*arguments):
    return subprocess.run(
        [sys.executable, "-m", "oomp", *arguments],
        capture_output=True, text=True, check=False,
    )


def test_cli_help_version_doctor_and_module_entrypoint():
    help_result = _run_cli("--help")
    assert help_result.returncode == 0
    assert "doctor" in help_result.stdout
    version_result = _run_cli("--version")
    assert version_result.returncode == 0
    assert __version__ in version_result.stdout
    doctor_result = _run_cli("doctor")
    assert doctor_result.returncode == 0
    assert "Stage 1 package readiness: OK" in doctor_result.stdout
    assert "pydantic:" in doctor_result.stdout
    assert _run_cli().returncode == 0


def test_doctor_fails_for_incompatible_dependency(monkeypatch, capsys):
    real_version = cli.importlib.metadata.version
    monkeypatch.setattr(
        cli.importlib.metadata, "version",
        lambda name: "1.10.0" if name == "pydantic" else real_version(name),
    )
    assert cli.doctor() == 1
    assert "requires >=2.9,<3" in capsys.readouterr().out


def test_doctor_fails_when_contract_import_fails(monkeypatch, capsys):
    real_import = cli.importlib.import_module

    def fail_one(name):
        if name == "oomp.domain.models":
            raise ImportError("test failure")
        return real_import(name)

    monkeypatch.setattr(cli.importlib, "import_module", fail_one)
    assert cli.doctor() == 1
    assert "import failed" in capsys.readouterr().out


def test_core_imports_need_no_trace_ollama_or_provider_modules():
    code = """
import importlib.abc
import sys
class BlockOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.lower().split('.')[0] in {'trace', 'ollama', 'openai', 'anthropic', 'langchain', 'llama_index'}:
            raise RuntimeError('provider import: ' + fullname)
sys.meta_path.insert(0, BlockOptional())
import oomp.domain.models
import oomp.domain.interfaces
import oomp.retrieval.contracts
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr