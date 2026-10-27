"""Synthetic event -> canonical memory -> bounded evidence, with no model or TRACE.

Run from a checkout or extracted source archive using an installed OOMP package:
    python examples/quickstart.py --db data/quickstart.sqlite3
The optional path must be new. Omitting it uses a temporary disposable database.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
from oomp.ingestion import ExtractionPipeline
from oomp.retrieval.contracts import RetrievalRequest
from oomp.retrieval.engine import RetrievalEngine
from oomp.storage import SQLiteEventStore

SCOPE = AuthorizedScope(tenant_id="synthetic-quickstart", namespace="demo", principal_id="local-operator")
START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def source(event_id: str, content: str, offset: int = 0) -> MemoryEvent:
    when = START + timedelta(minutes=offset)
    return MemoryEvent(
        event_id=event_id, tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
        event_type="user_message", source_type="user", content=content,
        source_reference=SourceReference(source_system="synthetic-quickstart", external_event_id=event_id,
                                         timestamp=when, session_id="demo-session", turn_id=event_id),
        occurred_at=when, ingested_at=when, idempotency_key=event_id, metadata={"synthetic": True},
    )


def run(path: Path, later_turns: int = 12) -> dict:
    if path.exists():
        raise ValueError("quickstart requires a new disposable database path")
    if type(later_turns) is not int or not 9 <= later_turns <= 128:
        raise ValueError("later_turns must be 9 to 128")
    events = SQLiteEventStore(path)
    assert events.initialize() == 5
    original = source("early-project", "I am developing a project called ReleaseDemo.")
    events.append(SCOPE, original)
    extraction = ExtractionPipeline(path).process_event(SCOPE, original.event_id)
    assert len(extraction.memory_ids) == 1
    for number in range(1, later_turns + 1):
        events.append(SCOPE, source(f"later-{number}", f"Synthetic unrelated conversation turn {number}.", number))
    engine = RetrievalEngine(path)
    engine.index(SCOPE)  # Derived lexical check; no embeddings or model call.
    result = engine.retrieve(SCOPE, RetrievalRequest(tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
        query="What project am I developing?", token_budget=3000))
    assert result.memories and original.event_id in result.memories[0].source_event_ids
    assert result.estimated_token_count == len(result.context_packet.encode("utf-8")) <= 3000
    recent = events.list_events(SCOPE, limit=1000).events[-8:]
    assert original.event_id not in {e.event_id for e in recent}
    reopened = SQLiteEventStore(path)
    assert reopened.get(SCOPE, original.event_id) == original
    return {"synthetic": True, "schema": 5, "source_events": reopened.count_events(SCOPE),
        "earlier_fact_outside_recent_eight": True, "memory_id": result.memories[0].memory_id,
        "canonical_content": result.memories[0].canonical_content,
        "source_event_ids": list(result.memories[0].source_event_ids),
        "source_references": [r.model_dump(mode="json") for r in result.memories[0].source_references],
        "context_bytes": result.estimated_token_count, "budget": result.token_budget,
        "model_calls": 0, "retrieval_is_an_answer": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, help="new disposable database path; an existing file is refused")
    args = parser.parse_args(argv)
    if args.db is not None:
        output = run(args.db)
    else:
        with TemporaryDirectory(prefix="oomp-quickstart-") as directory:
            output = run(Path(directory) / "demo.sqlite3")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
