from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from oomp.cli import main
from oomp.domain.enums import EventType, MemoryType, RelationshipType, SourceType
from oomp.domain.models import AuthorizedScope, MemoryEvent, MemoryNode, SourceReference
from oomp.graph import GraphService
from oomp.ingestion import ExtractionPipeline
from oomp.retrieval.contracts import EmbeddingSpace, RetrievalRequest
from oomp.retrieval.engine import RetrievalEngine, RetrievalUnavailableError
from oomp.storage import SQLiteEventStore
from oomp.storage.memory_store import SQLiteMemoryStore

SCOPE = AuthorizedScope(tenant_id="retrieval-test", namespace="synthetic", principal_id="pytest")
NOW = datetime.now(timezone.utc)


def source_event(event_id: str, content: str, *, when: datetime = NOW) -> MemoryEvent:
    return MemoryEvent(
        event_id=event_id, tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
        event_type=EventType.USER_MESSAGE, source_type=SourceType.USER,
        content=content,
        source_reference=SourceReference(
            source_system="synthetic-test", external_event_id=event_id, timestamp=when,
        ), occurred_at=when, ingested_at=when,
    )


def request(query: str, **changes) -> RetrievalRequest:
    return RetrievalRequest(
        tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace, query=query, **changes,
    )


class DeterministicTestProvider:
    """Synthetic vectors test routing only; they do not measure semantic quality."""

    space = EmbeddingSpace(provider="synthetic", model="rule-fixture", version="1", dimension=2)

    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return tuple(
            (1.0, 0.0) if "OOMP" in text or "effort" in text
            else (0.0, 1.0)
            for text in texts
        )


def _project_database(path: Path):
    events = SQLiteEventStore(path)
    assert events.initialize() == 5
    original = source_event("project-original", "I am developing a project called OOMP.")
    events.append(SCOPE, original)
    result = ExtractionPipeline(path).process_event(SCOPE, original.event_id)
    assert len(result.memory_ids) == 1
    return events, result.memory_ids[0]


def test_real_lexical_index_long_history_and_unrelated_query(tmp_path: Path):
    path = tmp_path / "history.sqlite3"
    events, project_id = _project_database(path)
    for number in range(105):
        events.append(SCOPE, source_event(f"later-{number}", f"Synthetic later turn number {number}.", when=NOW + timedelta(seconds=number + 1)))
    latest = events.list_events(SCOPE, limit=1000).events[-8:]
    assert "project-original" not in {item.event_id for item in latest}
    engine = RetrievalEngine(path)
    status = engine.index_status(SCOPE)
    assert status.canonical_count == status.lexical_count == 1
    response = engine.retrieve(SCOPE, request("What project was the user developing?"))
    assert [item.memory_id for item in response.memories] == [project_id]
    assert response.memories[0].source_event_ids == ("project-original",)
    assert response.estimated_token_count == len(response.context_packet.encode("utf-8"))
    assert response.estimated_token_count <= response.token_budget
    assert engine.retrieve(SCOPE, request("What is the capital of France?")).memories == ()


def test_semantic_fixture_retrieval_and_zero_similarity_rejection(tmp_path: Path):
    path = tmp_path / "semantic.sqlite3"
    _project_database(path)
    provider = DeterministicTestProvider()
    engine = RetrievalEngine(path, provider=provider)
    indexed = engine.index(SCOPE, include_embeddings=True)
    assert indexed.embeddings_indexed == 1
    assert engine.index(SCOPE, include_embeddings=True).embeddings_skipped == 1
    result = engine.retrieve(SCOPE, request("Which effort is being built?", mode="semantic"))
    assert len(result.memories) == 1
    assert result.retrieval_trace.semantic_candidates == 1
    assert engine.retrieve(SCOPE, request("Unrelated matter?", mode="semantic")).memories == ()
    assert provider.calls >= 3


def test_strict_missing_semantic_and_explicit_hybrid_degradation(tmp_path: Path):
    path = tmp_path / "missing-semantic.sqlite3"
    _project_database(path)
    engine = RetrievalEngine(path)
    with pytest.raises(RetrievalUnavailableError):
        engine.retrieve(SCOPE, request("OOMP", mode="semantic"))
    with pytest.raises(RetrievalUnavailableError):
        engine.retrieve(SCOPE, request("OOMP", mode="hybrid"))
    degraded = engine.retrieve(SCOPE, request("OOMP", mode="hybrid", allow_degraded=True))
    assert degraded.degraded is True
    assert degraded.retrieval_trace.semantic_candidates == 0
    assert len(degraded.memories) == 1


def test_cli_default_redacts_claim_and_packet_even_on_json(tmp_path: Path, capsys):
    path = tmp_path / "cli.sqlite3"
    _project_database(path)
    args = [
        "retrieve", "What project was the user developing?",
        "--tenant", SCOPE.tenant_id, "--namespace", SCOPE.namespace,
        "--db", str(path), "--json",
    ]
    assert main(args) == 0
    raw = capsys.readouterr().out
    data = json.loads(raw)
    assert data["memories"]
    assert "canonical_content" not in data["memories"][0]
    assert "context_packet" not in data
    assert "User is developing" not in raw
    assert main(args + ["--show-content"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert "canonical_content" in data["memories"][0]
    assert data["context_packet"]


def test_cli_validation_error_does_not_repeat_private_query(tmp_path: Path, capsys):
    secret = "private query marker"
    assert main([
        "retrieve", secret, "--tenant", SCOPE.tenant_id,
        "--namespace", SCOPE.namespace, "--db", str(tmp_path / "x.sqlite3"),
        "--as-of", "2026-01-01T00:00:00Z", "--valid-at", "2026-02-01T00:00:00Z",
    ]) == 1
    error = capsys.readouterr().err
    assert secret not in error
    assert "Invalid retrieval options" in error


def test_cli_index_status_and_strict_semantic_hint(tmp_path: Path, capsys):
    path = tmp_path / "cli-index.sqlite3"
    _project_database(path)
    scope_args = ["--tenant", SCOPE.tenant_id, "--namespace", SCOPE.namespace, "--db", str(path)]
    assert main(["memory", "index", *scope_args]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["lexical_indexed"] + first["lexical_skipped"] == 1
    assert main(["memory", "index", *scope_args]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["lexical_indexed"] == 0
    assert second["lexical_skipped"] == 1
    assert main(["retrieval", "status", *scope_args]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["canonical_count"] == status["lexical_count"] == 1
    assert main(["retrieve", "OOMP", *scope_args, "--mode", "semantic", "--json"]) == 1
    error = capsys.readouterr().err
    assert "explicit provider and complete compatible index" in error
    assert "OOMP" not in error


def _hardware(path: Path, *, old_end, new_end):
    events = SQLiteEventStore(path)
    assert events.initialize() == 5
    old = source_event(
        "hardware-old", "My test computer has 4 GB RAM.",
        when=datetime(2026, 1, 5, tzinfo=timezone.utc),
    )
    new = source_event(
        "hardware-new", "I upgraded my test computer to 12 GB RAM.",
        when=datetime(2026, 9, 16, tzinfo=timezone.utc),
    )
    for item in (old, new):
        events.append(SCOPE, item)
    memories = SQLiteMemoryStore(path)
    for identity, item, start, end in (
        ("ram-old-4", old, datetime(2026, 1, 1, tzinfo=timezone.utc), old_end),
        ("ram-new-12", new, datetime(2026, 9, 15, tzinfo=timezone.utc), new_end),
    ):
        created = datetime.now(timezone.utc)
        memories.upsert(SCOPE, MemoryNode(
            memory_id=identity, tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
            memory_type=MemoryType.SEMANTIC, canonical_key="test:" + identity,
            canonical_content=item.content, source_event_ids=(item.event_id,),
            provenance=(item.source_reference,), created_at=created, updated_at=created,
            valid_from=start, valid_until=end,
            metadata={"attribution": "user", "verified": False},
        ))
    graph = GraphService(path)
    proposal = graph.propose_conflict(SCOPE, "ram-new-12", "ram-old-4").proposal
    assert proposal is not None
    graph.resolve(SCOPE, proposal, confirm=True)
    return graph


def test_current_and_historical_ram_keep_actual_source_and_edge_direction(tmp_path: Path):
    path = tmp_path / "ram.sqlite3"
    _hardware(
        path,
        old_end=datetime(2026, 9, 15, tzinfo=timezone.utc),
        new_end=datetime(2100, 1, 1, tzinfo=timezone.utc),
    )
    engine = RetrievalEngine(path)
    current = engine.retrieve(SCOPE, request("test computer RAM", token_budget=3000))
    assert {item.memory_id for item in current.memories} == {"ram-new-12"}
    assert current.memories[0].source_event_ids == ("hardware-new",)
    capped = engine.retrieve(SCOPE, request(
        "My test computer has 4 GB RAM", candidate_limit=1,
        graph_depth=0, token_budget=3000,
    ))
    assert [item.memory_id for item in capped.memories] == ["ram-new-12"]
    assert capped.memories[0].source_event_ids == ("hardware-new",)
    assert any(path.node_ids == ("ram-old-4", "ram-new-12") for path in capped.memories[0].graph_paths)
    historical = engine.retrieve(
        SCOPE, request("test computer RAM", valid_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
                       historical=True, token_budget=3000),
    )
    assert {item.memory_id for item in historical.memories} == {"ram-old-4"}
    assert historical.memories[0].source_event_ids == ("hardware-old",)
    # The governed edge points new -> old, even when traversed from old to new.
    with engine.store.read_snapshot(SCOPE) as session:
        records = session.neighbors("ram-old-4", allowed_relationships=(RelationshipType.SUPERSEDES,))
        assert records[0].edge.source_node_id == "ram-new-12"


def test_expired_replacement_chain_reaches_current_head_from_one_old_seed(tmp_path: Path):
    path = tmp_path / "ram-chain.sqlite3"
    graph = _hardware(
        path,
        old_end=datetime(2026, 9, 15, tzinfo=timezone.utc),
        new_end=datetime(2026, 10, 2, tzinfo=timezone.utc),
    )
    newest = source_event(
        "hardware-newest", "I upgraded my test computer to 16 GB RAM.",
        when=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    SQLiteEventStore(path).append(SCOPE, newest)
    created = datetime.now(timezone.utc)
    SQLiteMemoryStore(path).upsert(SCOPE, MemoryNode(
        memory_id="ram-newest-16", tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
        memory_type=MemoryType.SEMANTIC, canonical_key="test:ram-newest-16",
        canonical_content=newest.content, source_event_ids=(newest.event_id,),
        provenance=(newest.source_reference,), created_at=created, updated_at=created,
        valid_from=datetime(2026, 10, 1, tzinfo=timezone.utc),
        valid_until=datetime(2100, 1, 1, tzinfo=timezone.utc),
        metadata={"attribution": "user", "verified": False},
    ))
    proposal = graph.propose_conflict(SCOPE, "ram-newest-16", "ram-new-12").proposal
    assert proposal is not None
    graph.resolve(SCOPE, proposal, confirm=True)
    engine = RetrievalEngine(path)
    query = "My test computer has 4 GB RAM"
    with engine.store.read_snapshot(SCOPE) as session:
        assert session.lexical(query, limit=1)[0].memory_id == "ram-old-4"
    result = engine.retrieve(SCOPE, request(
        query, candidate_limit=1, graph_depth=0, token_budget=4000,
    ))
    assert [item.memory_id for item in result.memories] == ["ram-newest-16"]
    assert result.memories[0].source_event_ids == ("hardware-newest",)
    assert any(path.node_ids == ("ram-old-4", "ram-new-12", "ram-newest-16")
               for path in result.memories[0].graph_paths)

def test_unknown_supersession_keeps_both_claims_and_counts_uncertainty(tmp_path: Path):
    path = tmp_path / "uncertain.sqlite3"
    _hardware(path, old_end=None, new_end=None)
    response = RetrievalEngine(path).retrieve(
        SCOPE, request("test computer RAM", graph_depth=0, token_budget=4000),
    )
    assert {item.memory_id for item in response.memories} == {"ram-old-4", "ram-new-12"}
    assert "supersession_validity_uncertain" in response.warnings
    old = next(item for item in response.memories if item.memory_id == "ram-old-4")
    assert old.temporal_status == "uncertain"
    assert any(path.edge_validity == (None,) for path in old.graph_paths)
    assert "supersession_validity_uncertain" in response.context_packet


def test_known_at_uses_only_then_recorded_source_evidence(tmp_path: Path):
    path = tmp_path / "known.sqlite3"
    events, memory_id = _project_database(path)
    cutoff = datetime.now(timezone.utc)
    later = source_event("later-proof", "I am developing a project called OOMP.")
    events.append(SCOPE, later)
    ExtractionPipeline(path).process_event(SCOPE, later.event_id)
    memory = SQLiteMemoryStore(path).get(SCOPE, memory_id)
    assert memory is not None and len(memory.source_event_ids) == 2
    historical = RetrievalEngine(path).retrieve(
        SCOPE, request("OOMP project", known_at=cutoff, token_budget=2000),
    )
    assert len(historical.memories) == 1
    assert historical.memories[0].source_event_ids == ("project-original",)
    assert "historical_entity_index_unavailable" in historical.warnings


def test_explicit_alias_entity_lane_and_graph_direction(tmp_path: Path):
    path = tmp_path / "alias-graph.sqlite3"
    events = SQLiteEventStore(path)
    events.initialize()
    original = source_event(
        "alias-project",
        "I am developing a project called OOMP (Object-Oriented Context Map).",
    )
    events.append(SCOPE, original)
    project_id = ExtractionPipeline(path).process_event(SCOPE, original.event_id).memory_ids[0]
    related = source_event("project-related", "Project retrieval notes support memory inspection.")
    events.append(SCOPE, related)
    created = datetime.now(timezone.utc)
    SQLiteMemoryStore(path).upsert(SCOPE, MemoryNode(
        memory_id="project-related", tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
        memory_type=MemoryType.SEMANTIC, canonical_key="test:related",
        canonical_content=related.content, source_event_ids=(related.event_id,),
        provenance=(related.source_reference,), created_at=created, updated_at=created,
        metadata={"attribution": "user", "verified": False},
    ))
    GraphService(path).link(
        SCOPE, project_id, "project-related", RelationshipType.RELATED_TO,
        (original.event_id,),
    )
    engine = RetrievalEngine(path)
    alias = engine.retrieve(
        SCOPE, request("Object-Oriented Context Map", graph_depth=0, token_budget=2000),
    )
    assert [item.memory_id for item in alias.memories] == [project_id]
    assert any(reason.startswith("entity:") for reason in alias.memories[0].selection_reasons)
    reverse = engine.retrieve(
        SCOPE, request("retrieval notes", graph_depth=1, token_budget=4000),
    )
    assert any(item.memory_id == project_id for item in reverse.memories) is False
    # Querying a shared project term allows expansion and shows actual orientation.
    linked = engine.retrieve(
        SCOPE, request("project", candidate_limit=1, graph_depth=1, token_budget=4000),
    )
    assert any(
        path.edge_directions == ("reverse",)
        for item in linked.memories for path in item.graph_paths
    ) or any(
        path.edge_directions == ("forward",)
        for item in linked.memories for path in item.graph_paths
    )


def test_confirmed_unresolved_contradiction_visible_without_graph_expansion(tmp_path: Path):
    path = tmp_path / "dispute.sqlite3"
    events = SQLiteEventStore(path)
    events.initialize()
    first = source_event("claim-four", "My test computer has 4 GB RAM.")
    second = source_event("claim-eight", "My test computer has 8 GB RAM.")
    events.append(SCOPE, first)
    events.append(SCOPE, second)
    memories = SQLiteMemoryStore(path)
    for identity, item in (("claim-4", first), ("claim-8", second)):
        created = datetime.now(timezone.utc)
        memories.upsert(SCOPE, MemoryNode(
            memory_id=identity, tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
            memory_type=MemoryType.SEMANTIC, canonical_key="test:" + identity,
            canonical_content=item.content, source_event_ids=(item.event_id,),
            provenance=(item.source_reference,), created_at=created, updated_at=created,
            valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
            valid_until=datetime(2100, 1, 1, tzinfo=timezone.utc),
            metadata={"attribution": "user", "verified": False},
        ))
    graph = GraphService(path)
    proposal = graph.propose_conflict(SCOPE, "claim-8", "claim-4").proposal
    assert proposal is not None and proposal.relationship_type is RelationshipType.CONTRADICTS
    graph.resolve(SCOPE, proposal, confirm=True)
    response = RetrievalEngine(path).retrieve(
        SCOPE, request("test computer RAM", graph_depth=0, token_budget=4000),
    )
    assert {item.memory_id for item in response.memories} == {"claim-4", "claim-8"}
    assert all(item.temporal_status == "contradicted" for item in response.memories)
    assert all(item.graph_paths for item in response.memories)
    assert all(
        item.graph_paths[0].edge_evidence[0]
        for item in response.memories
    )