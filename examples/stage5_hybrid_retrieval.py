"""Synthetic, offline Stage 5 lexical/temporal/graph/budget retrieval demonstration.

The optional semantic lane below uses rule-based test vectors only. It makes no
claim about a real embedding model's semantic accuracy or measured performance.
Use --db only with a dedicated synthetic database.
"""

from __future__ import annotations

from oomp.storage.migrations import SCHEMA_VERSION

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from oomp.domain.enums import EventType, MemoryType, RelationshipType, SourceType
from oomp.domain.models import AuthorizedScope, MemoryEvent, MemoryNode, SourceReference
from oomp.graph import GraphService
from oomp.ingestion import ExtractionPipeline
from oomp.retrieval.contracts import EmbeddingSpace, RetrievalRequest
from oomp.retrieval.engine import RetrievalEngine
from oomp.storage import SQLiteEventStore
from oomp.storage.memory_store import SQLiteMemoryStore

SCOPE = AuthorizedScope(
    tenant_id="tenant-stage5-example", namespace="synthetic",
    principal_id="example-service",
)
JAN1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
JAN5 = datetime(2026, 1, 5, tzinfo=timezone.utc)
SEP10 = datetime(2026, 9, 10, tzinfo=timezone.utc)
SEP15 = datetime(2026, 9, 15, tzinfo=timezone.utc)
DEC31 = datetime(2100, 1, 1, tzinfo=timezone.utc)


def event(event_id: str, content: str, when: datetime) -> MemoryEvent:
    return MemoryEvent(
        event_id=event_id, tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
        event_type=EventType.USER_MESSAGE, source_type=SourceType.USER,
        content=content,
        source_reference=SourceReference(
            source_system="stage5-synthetic", external_event_id=event_id,
            timestamp=when, session_id="synthetic-history", turn_id=event_id,
        ),
        occurred_at=when, ingested_at=when, idempotency_key="key-" + event_id,
        metadata={"synthetic": True},
    )


class SyntheticEmbeddingProvider:
    """Fixture vectors exercise persistence and routing, not semantic accuracy."""

    space = EmbeddingSpace(
        provider="synthetic", model="stage5-rule-vectors", version="1", dimension=2,
    )

    def embed(self, texts):
        return tuple(
            (1.0, 0.0) if "OOMP" in text or "effort" in text else (0.0, 1.0)
            for text in texts
        )


def direct_memory(
    memory_id: str, source: MemoryEvent, *,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
) -> MemoryNode:
    created = datetime.now(timezone.utc)
    return MemoryNode(
        memory_id=memory_id, tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
        memory_type=MemoryType.SEMANTIC, canonical_key="stage5:" + memory_id,
        canonical_content=source.content,
        source_event_ids=(source.event_id,), provenance=(source.source_reference,),
        created_at=created, updated_at=created,
        valid_from=valid_from, valid_until=valid_until,
        metadata={"attribution": "user", "verified": False, "synthetic": True},
    )


def request(query: str, **options) -> RetrievalRequest:
    return RetrievalRequest(
        tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
        query=query, **options,
    )


def run(path: Path) -> None:
    events = SQLiteEventStore(path)
    assert events.initialize() == SCHEMA_VERSION
    original = event("project-original", "I am developing a project called OOMP.", JAN1)
    old = event("ram-old-event", "My test computer has 4 GB RAM.", JAN5)
    upgraded = event("ram-upgrade-event", "I upgraded my test computer to 12 GB RAM.", SEP15)
    related = event("project-related-event", "Project retrieval notes support memory inspection.", JAN5)
    unrelated = event("unrelated-event", "Tea is a beverage.", JAN5)
    for item in (original, old, upgraded, related, unrelated):
        events.append(SCOPE, item)
    extraction = ExtractionPipeline(path).process_event(SCOPE, original.event_id)
    assert len(extraction.memory_ids) == 1
    project_id = extraction.memory_ids[0]
    for number in range(105):
        events.append(
            SCOPE,
            event(
                f"later-{number:03d}", f"Unrelated synthetic interaction {number}.",
                JAN5 + timedelta(seconds=number + 1),
            ),
        )

    memories = SQLiteMemoryStore(path)
    for identity, source, start, end in (
        ("ram-old-4", old, JAN1, SEP15),
        ("ram-new-12", upgraded, SEP15, DEC31),
        ("project-related", related, None, None),
        ("unrelated-tea", unrelated, None, None),
    ):
        memories.upsert(
            SCOPE, direct_memory(identity, source, valid_from=start, valid_until=end),
        )

    graph = GraphService(path)
    proposal = graph.propose_conflict(SCOPE, "ram-new-12", "ram-old-4").proposal
    assert proposal is not None and proposal.relationship_type is RelationshipType.SUPERSEDES
    graph.resolve(SCOPE, proposal, confirm=True)
    graph.link(
        SCOPE, project_id, "project-related", RelationshipType.RELATED_TO,
        (original.event_id,),
    )
    graph.link(
        SCOPE, "project-related", "unrelated-tea", RelationshipType.RELATED_TO,
        (related.event_id,),
    )

    engine = RetrievalEngine(path)
    first_index = engine.index(SCOPE)
    second_index = engine.index(SCOPE)
    latest_eight = events.list_events(SCOPE, limit=1000).events[-8:]
    assert original.event_id not in {item.event_id for item in latest_eight}
    long_history = engine.retrieve(SCOPE, request("What project was the user developing?"))
    assert project_id in {item.memory_id for item in long_history.memories}
    assert any(original.event_id in item.source_event_ids for item in long_history.memories)

    fixture_engine = RetrievalEngine(path, provider=SyntheticEmbeddingProvider())
    fixture_index = fixture_engine.index(SCOPE, include_embeddings=True)
    synthetic_semantic = fixture_engine.retrieve(
        SCOPE, request("Which effort is being built?", mode="semantic"),
    )
    assert synthetic_semantic.retrieval_trace.semantic_candidates > 0

    current_ram = engine.retrieve(SCOPE, request("test computer RAM", token_budget=2000))
    earlier_ram = engine.retrieve(
        SCOPE, request("test computer RAM", valid_at=SEP10, historical=True, token_budget=2000),
    )
    assert "ram-new-12" in {item.memory_id for item in current_ram.memories}
    assert "ram-old-4" not in {item.memory_id for item in current_ram.memories}
    assert "ram-old-4" in {item.memory_id for item in earlier_ram.memories}
    assert "ram-new-12" not in {item.memory_id for item in earlier_ram.memories}

    graph_result = engine.retrieve(
        SCOPE, request("OOMP project", candidate_limit=1, graph_depth=2, graph_nodes=8,
                       token_budget=3000),
    )
    assert project_id in {item.memory_id for item in graph_result.memories}
    assert "project-related" in {item.memory_id for item in graph_result.memories}
    assert "unrelated-tea" not in {item.memory_id for item in graph_result.memories}
    assert any(item.graph_paths for item in graph_result.memories)

    strict = engine.retrieve(SCOPE, request("OOMP project", token_budget=1200))
    assert strict.estimated_token_count <= strict.token_budget
    assert strict.context_packet
    assert strict.estimated_token_count == len(strict.context_packet.encode("utf-8"))
    assert len(strict.memories) < len(graph_result.memories)
    assert strict.retrieval_trace.budget_dropped > 0
    assert strict.memories[0].source_event_ids == (original.event_id,)

    print(f"Database: {path}")
    print(f"Schema: 5; source events: {events.count_events(SCOPE)}")
    print(f"Original event outside latest eight: {original.event_id not in {item.event_id for item in latest_eight}}")
    print(f"Long-history retrieved memory: {project_id} source={original.event_id}")
    print(f"Lexical indexing: first={first_index.lexical_indexed} retry_skipped={second_index.lexical_skipped}")
    print(f"Semantic fixture: synthetic vectors, candidates={synthetic_semantic.retrieval_trace.semantic_candidates}, indexed={fixture_index.embeddings_indexed}")
    print(f"Current RAM: {[item.memory_id for item in current_ram.memories]}")
    print(f"Earlier RAM: {[item.memory_id for item in earlier_ram.memories]}")
    print(f"Graph linked memory and proof: {any(item.graph_paths for item in graph_result.memories)}")
    print(f"Strict evidence budget: {strict.estimated_token_count}/{strict.token_budget} bytes, memories={len(strict.memories)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run synthetic offline Stage 5 retrieval demonstration.")
    parser.add_argument("--db", type=Path, help="dedicated persistent synthetic database path")
    args = parser.parse_args()
    if args.db is None:
        with TemporaryDirectory(prefix="oomp-stage5-example-") as directory:
            run(Path(directory) / "events.sqlite3")
    else:
        run(args.db)


if __name__ == "__main__":
    main()
