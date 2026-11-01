"""Three-session context recall using fresh synthetic storage and no model.

The fictional scope explicitly consents to attributed political-topic episodes.
This is a retrieval/provenance demonstration, not a chatbot answer benchmark.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path

from oomp.context.contracts import ContextRequest
from oomp.context.engine import ContextEngine
from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
from oomp.mind.worker import MindWorker
from oomp.objects import ObjectMap
from oomp.storage.sqlite import SQLiteEventStore
from oomp.understanding.contracts import ExtractionConfiguration

FIXTURE_SHA256 = "d761e12a246084104a9f7113c28b3ad99853afdff72b0d842417674f476e7ae9"
QUESTIONS = (
    ("project", "What project did I mention earlier?"),
    ("moving", "What were we discussing about moving?"),
    ("decision", "Did I decide to relocate?"),
    ("style", "What response style do I prefer?"),
    ("earlier-name", "What was my earlier project name?"),
    ("pet", "What is my pet's name?"),
)


def load_fixture():
    path = Path(__file__).parent / "fixtures" / "context_recall_v1.json"
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != FIXTURE_SHA256:
        raise ValueError("context_quickstart_fixture_hash_mismatch")
    fixture = json.loads(raw)
    if fixture.get("synthetic") is not True:
        raise ValueError("synthetic_fixture_required")
    return fixture


def run(directory):
    fixture = load_fixture()
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / "fictional.sqlite3"
    scope = AuthorizedScope.model_validate(fixture["scope"])
    source = SQLiteEventStore(path)
    schema = source.initialize()
    worker = MindWorker(path, scope, extraction_configuration=ExtractionConfiguration(
        mode="rules", retain_episodes=True, sensitive_episodes=True,
    ))
    base = datetime.fromisoformat(fixture["base_time"])
    originals = {}
    for index, turn in enumerate(fixture["turns"]):
        when = base + timedelta(days=turn["session"], minutes=index)
        event = MemoryEvent(
            event_id=turn["id"], tenant_id=scope.tenant_id, namespace=scope.namespace,
            event_type=turn["role"] + "_message", source_type=turn["role"], content=turn["text"],
            source_reference=SourceReference(
                source_system=fixture["source_system"], external_event_id=turn["id"],
                timestamp=when, session_id="p4a-session-" + str(turn["session"]),
                turn_id="p4a-turn-" + str(index),
            ), occurred_at=when, ingested_at=when, metadata={"ingested_by": scope.principal_id},
        )
        source.append(scope, event)
        originals[event.event_id] = event
    jobs = []
    for _ in range(4):
        completed = worker.run_once(max_jobs=100)
        jobs.append(asdict(completed))
        if completed.failed or completed.retried or completed.lost_lease:
            raise ValueError("synthetic_context_mind_job_failed")
        if completed.claimed == 0:
            break
    else:
        raise ValueError("synthetic_context_job_limit")
    if worker.handlers.understanding.provider is not None:
        raise ValueError("synthetic_context_rules_only_required")
    graph = ObjectMap(path)
    built = graph.build(scope, limit=100)
    if built.incomplete:
        raise ValueError("synthetic_context_projection_incomplete")
    results = []
    engine = ContextEngine(path)
    for name, question in QUESTIONS:
        result = engine.retrieve(scope, ContextRequest(
            tenant_id=scope.tenant_id, namespace=scope.namespace,
            query=question, token_budget=6000, graph_depth=0, explain=True,
        ))
        supports = []
        for unit in result.evidence_packets:
            for proof in unit.source_proofs:
                event = source.get(scope, proof.event_id)
                if event is None or event.source_reference != proof.source_reference:
                    raise ValueError("synthetic_context_source_mismatch")
                if not 0 <= proof.span_start < proof.span_end <= len(event.content):
                    raise ValueError("synthetic_context_span_invalid")
                if proof.quote is not None and event.content[proof.span_start:proof.span_end] != proof.quote:
                    raise ValueError("synthetic_context_quote_mismatch")
                supports.append((proof.event_id, proof.span_start, proof.span_end))
        if len(set(supports)) != len(supports):
            raise ValueError("synthetic_context_duplicate_source_support")
        if result.selected_context_bytes != len(result.context_packet.encode("utf-8")) or result.selected_context_bytes > 6000:
            raise ValueError("synthetic_context_budget_invalid")
        if name == "pet" and result.evidence_packets:
            raise ValueError("synthetic_context_unsupported_pet")
        results.append({
            "query_id": name, "question": question,
            "intent": result.retrieval_intent, "status": result.retrieval_status,
            "source_event_ids": list(dict.fromkeys(event_id for event_id, _, _ in supports)),
            "resolutions": list(dict.fromkeys(unit.resolution for unit in result.evidence_packets)),
            "selected_context_bytes": result.selected_context_bytes,
            "token_budget": result.token_budget, "counting_method": result.counting_method,
            "degraded": result.degraded, "reasons": result.reasons,
        })
    reopened = ContextEngine(path).retrieve(scope, ContextRequest(
        tenant_id=scope.tenant_id, namespace=scope.namespace,
        query=QUESTIONS[1][1], token_budget=6000,
    ))
    moving = next(item for item in results if item["query_id"] == "moving")
    reopened_ids = list(dict.fromkeys(proof.event_id for unit in reopened.evidence_packets for proof in unit.source_proofs))
    if reopened_ids != moving["source_event_ids"]:
        raise ValueError("synthetic_context_reopen_changed_proofs")
    if any(source.get(scope, event_id) != event for event_id, event in originals.items()):
        raise ValueError("synthetic_context_source_changed")
    document = {
        "synthetic": True, "fixture_sha256": FIXTURE_SHA256, "schema_version": schema,
        "source_events": len(originals), "sessions": 3,
        "extraction": {"mode": "rules", "sensitive_episodes": True, "consent": "fictional topic-only fixture"},
        "jobs": jobs, "projection": built.model_dump(mode="json"), "queries": results,
        "reopen_stable": True, "model_calls": 0, "real_embedding_calls": 0,
        "scope_of_claim": "Synthetic source retrieval/provenance only; no final chatbot answer or real semantic-model quality measurement.",
    }
    with (directory / "result.json").open("x", encoding="utf-8", newline="\n") as output:
        json.dump(document, output, ensure_ascii=True, indent=2)
        output.write("\n")
    return document


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path, help="fresh short disposable synthetic directory")
    print(json.dumps(run(parser.parse_args().directory), ensure_ascii=True, indent=2))
