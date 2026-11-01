"""Opt-in P3 associations and stored-summary manifests over public synthetic data."""
from contextlib import closing
from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3

import pytest

from oomp.context.contracts import ContextRequest
from oomp.context.engine import ContextEngine
from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
from oomp.mind.worker import MindWorker
from oomp.objects.service import ObjectMap
from oomp.storage.mind_projection_store import SQLiteMindProjectionStore
from oomp.storage.sqlite import SQLiteEventStore
from oomp.understanding.contracts import ExtractionConfiguration


FIXTURE = Path(__file__).resolve().parents[1] / "examples/fixtures/object_relocation_v1.json"


def build(path, *, indices=range(10), project=True):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["synthetic"] and fixture["version"] == "object-relocation.v1"
    scope = AuthorizedScope(tenant_id=fixture["tenant"], namespace=fixture["namespace"],
                            principal_id=fixture["principal"])
    store = SQLiteEventStore(path)
    store.initialize()
    when = datetime.fromisoformat(fixture["base_time"])
    events = {}
    for index in indices:
        turn = fixture["turns"][index]
        stamp = when + timedelta(minutes=index)
        event = MemoryEvent(event_id=turn["id"], tenant_id=scope.tenant_id, namespace=scope.namespace,
            event_type=turn["role"]+"_message", source_type=turn["role"], content=turn["text"],
            occurred_at=stamp, ingested_at=stamp, metadata={"ingested_by": scope.principal_id},
            source_reference=SourceReference(source_system="public-synthetic-p3",
                external_event_id=turn["id"], timestamp=stamp, session_id=fixture["session"],
                turn_id="turn-"+str(index)))
        store.append(scope, event)
        events[event.event_id] = event
    worker = MindWorker(path, scope, extraction_configuration=ExtractionConfiguration(mode="rules"))
    run = worker.run_once(max_jobs=100)
    assert not any((run.failed, run.retried, run.lost_lease)) and run.completed >= len(events)
    assert worker.handlers.understanding.provider is None
    objects = ObjectMap(path)
    if project:
        assert not objects.build(scope, limit=100).incomplete
    return scope, events, objects


def request(scope, *, query="What were we discussing about Lahore?", **values):
    return ContextRequest(tenant_id=scope.tenant_id, namespace=scope.namespace, query=query,
        token_budget=32768, max_results=20, graph_nodes=32, graph_edges=64, graph_work=400,
        **values)


def proof_events(result):
    return {proof.event_id for unit in result.evidence_packets for proof in unit.source_proofs}


def test_exact_place_anchor_opt_in_adds_source_grounded_nonliteral_plan(tmp_path):
    path = tmp_path / "associations.sqlite3"
    scope, events, objects = build(path)
    plan, = objects.list_objects(scope, object_type="plan").objects
    assert "Lahore" not in events["p3-plan"].content
    assert {proof.event_id for proof in plan.source_proofs} == {"p3-plan"}
    engine = ContextEngine(path)
    default = engine.retrieve(scope, request(scope))
    expanded = engine.retrieve(scope, request(scope, graph_depth=1, include_source_content=True))
    assert "p3-plan" not in proof_events(default)
    assert default.trace.get("p3_graph_lane", 0) == 0
    assert default.trace.get("p3_association_edges", 0) == 0
    assert expanded.trace["p3_graph_lane"] == 1
    assert 0 < expanded.trace["p3_association_edges"] <= 64
    assert expanded.trace["p3_association_nodes"] <= 32
    assert expanded.trace["p3_association_work"] <= 400
    assert "p3-plan" in proof_events(expanded)
    assert expanded.retrieval_status.value == "candidate_uncertain"
    for unit in expanded.evidence_packets:
        for proof in unit.source_proofs:
            event = events[proof.event_id]
            assert event.source_type == "user"
            assert proof.source_reference == event.source_reference
            assert 0 <= proof.span_start < proof.span_end <= len(event.content)
            assert proof.quote == event.content[proof.span_start:proof.span_end]
    assert all(proof.quote is None for unit in default.evidence_packets for proof in unit.source_proofs)


def test_p3_associations_cannot_cross_principal(tmp_path):
    path = tmp_path / "principal.sqlite3"
    scope, events, _ = build(path)
    foreign = scope.model_copy(update={"principal_id": "other-synthetic-reader"})
    result = ContextEngine(path).retrieve(foreign, request(foreign, graph_depth=2))
    assert not result.evidence_packets and not result.source_references
    assert not proof_events(result) & events.keys()
    assert result.trace.get("p3_association_edges", 0) == 0
    assert result.trace.get("p3_graph_lane", 0) == 0


def test_retracted_target_proof_cannot_return_through_p3_association(tmp_path):
    path = tmp_path / "retracted.sqlite3"
    scope, _, objects = build(path)
    plan, = objects.list_objects(scope, object_type="plan").objects
    engine = ContextEngine(path)
    assert "p3-plan" in proof_events(engine.retrieve(scope, request(scope, graph_depth=1)))
    for proof in plan.source_proofs:
        assert SQLiteMindProjectionStore(path).retract_source(scope, proof.memory_id, proof.event_id)
    assert objects.get_object(scope, plan.object_id) is None
    result = engine.retrieve(scope, request(scope, graph_depth=2))
    assert "p3-plan" not in proof_events(result)
    assert all(plan.object_id not in unit.object_ids for unit in result.evidence_packets)


@pytest.mark.parametrize("delete_all", [False, True], ids=["missing-member", "empty-manifest"])
def test_summary_manifest_must_exist_and_match_current_support(tmp_path, delete_all):
    path = tmp_path / "manifest.sqlite3"
    # P2 summaries are valid without optional P3 materialization. Omitting the
    # map here isolates summary admission from legitimate whole-object upgrades.
    scope, _, _ = build(path, indices=(2, 3), project=False)
    query = request(scope, query="What were we discussing about moving candidates?")
    engine = ContextEngine(path)
    before = engine.retrieve(scope, query)
    summaries = [unit for unit in before.evidence_packets if unit.resolution.value == "episode_summary"]
    assert summaries, before.model_dump_json()
    revision = summaries[0].revision_id
    assert revision is not None
    with closing(sqlite3.connect(path)) as connection:
        keys = connection.execute("SELECT memory_id,event_id FROM mind_summary_sources "
            "WHERE tenant_id=? AND namespace=? AND revision_id=? ORDER BY memory_id,event_id",
            (scope.tenant_id, scope.namespace, revision)).fetchall()
        assert len(keys) >= 2
        selected = keys if delete_all else keys[:1]
        connection.executemany("DELETE FROM mind_summary_sources WHERE tenant_id=? AND namespace=? "
            "AND revision_id=? AND memory_id=? AND event_id=?",
            [(scope.tenant_id, scope.namespace, revision, *key) for key in selected])
        connection.commit()
    after = engine.retrieve(scope, query)
    assert all(unit.revision_id != revision for unit in after.evidence_packets)
    assert after.trace.get("summary_excluded", 0) >= 1
    assert "summary_support_stale_or_not_relevant" in after.reasons
