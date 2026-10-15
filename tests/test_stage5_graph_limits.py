"""Bounded graph retrieval over persisted synthetic cycles and direct lexical facts."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from oomp.domain.enums import RelationshipType
from oomp.domain.models import AuthorizedScope, MemoryEvent, MemoryNode, SourceReference
from oomp.graph import GraphService
from oomp.retrieval.contracts import RetrievalRequest
from oomp.retrieval.engine import RetrievalEngine
from oomp.storage import GraphLimitError, SQLiteEventStore, SQLiteMemoryStore

SCOPE=AuthorizedScope(tenant_id="graph-retrieval",namespace="synthetic",principal_id="pytest")
NOW=datetime(2026,1,1,tzinfo=timezone.utc)


def _memory(path, identity, content):
    source=MemoryEvent(
        event_id=f"event-{identity}",tenant_id=SCOPE.tenant_id,namespace=SCOPE.namespace,
        event_type="user_message",source_type="user",content=content,
        source_reference=SourceReference(
            source_system="synthetic",external_event_id=f"event-{identity}",timestamp=NOW,
        ),occurred_at=NOW,ingested_at=NOW,
    )
    SQLiteEventStore(path).append(SCOPE,source)
    node=MemoryNode(
        memory_id=identity,tenant_id=SCOPE.tenant_id,namespace=SCOPE.namespace,
        memory_type="semantic",canonical_key=f"key:{identity}",canonical_content=content,
        source_event_ids=(source.event_id,),provenance=(source.source_reference,),
        created_at=NOW,updated_at=NOW,metadata={"attribution":"user","verified":False},
    )
    return SQLiteMemoryStore(path).upsert(SCOPE,node)


def _request(**changes):
    return RetrievalRequest(
        tenant_id=SCOPE.tenant_id,namespace=SCOPE.namespace,query="OOMP",
        candidate_limit=1,max_results=8,token_budget=4000,**changes,
    )


def _cyclic_graph(path):
    SQLiteEventStore(path).initialize()
    seed=_memory(path,"seed","OOMP OOMP OOMP central project memory.")
    near=_memory(path,"near","OOMP supporting detail.")
    far=_memory(path,"far","OOMP second-hop detail.")
    unrelated=_memory(path,"unrelated","Bananas are yellow.")
    dependent=_memory(path,"dependent","OOMP depends on this task.")
    graph=GraphService(path)
    graph.link(SCOPE,seed.memory_id,near.memory_id,RelationshipType.RELATED_TO,(seed.source_event_ids[0],))
    graph.link(SCOPE,near.memory_id,far.memory_id,RelationshipType.RELATED_TO,(near.source_event_ids[0],))
    graph.link(SCOPE,far.memory_id,near.memory_id,RelationshipType.RELATED_TO,(far.source_event_ids[0],))
    graph.link(SCOPE,seed.memory_id,unrelated.memory_id,RelationshipType.RELATED_TO,(unrelated.source_event_ids[0],))
    graph.link(SCOPE,seed.memory_id,dependent.memory_id,RelationshipType.DEPENDS_ON,(dependent.source_event_ids[0],))
    return RetrievalEngine(path)


def test_depth_cycle_simple_paths_relation_filter_and_irrelevant_branch(tmp_path):
    engine=_cyclic_graph(tmp_path/"cycles.sqlite3")
    zero=engine.retrieve(SCOPE,_request(graph_depth=0))
    assert [item.memory_id for item in zero.memories]==["seed"]
    one=engine.retrieve(SCOPE,_request(graph_depth=1))
    one_ids={item.memory_id for item in one.memories}
    assert "seed" in one_ids and "near" in one_ids and "dependent" in one_ids
    assert "far" not in one_ids and "unrelated" not in one_ids
    two=engine.retrieve(SCOPE,_request(graph_depth=2))
    two_ids={item.memory_id for item in two.memories}
    assert "far" in two_ids and "unrelated" not in two_ids
    far=next(item for item in two.memories if item.memory_id=="far")
    assert any(path.node_ids==("seed","near","far") for path in far.graph_paths)
    assert all(len(path.node_ids)==len(set(path.node_ids))
               for item in two.memories for path in item.graph_paths)
    assert all(path.edge_evidence and all(path.edge_evidence)
               for item in two.memories for path in item.graph_paths)
    related=engine.retrieve(
        SCOPE,_request(graph_depth=2,graph_relationships=(RelationshipType.RELATED_TO,)),
    )
    assert "dependent" not in {item.memory_id for item in related.memories}
    depends=engine.retrieve(
        SCOPE,_request(graph_depth=1,graph_relationships=(RelationshipType.DEPENDS_ON,)),
    )
    assert {item.memory_id for item in depends.memories}=={"seed","dependent"}


def test_small_node_edge_and_work_limits_signal_truncation_or_fail(tmp_path):
    engine=_cyclic_graph(tmp_path/"limits.sqlite3")
    node_limited=engine.retrieve(SCOPE,_request(graph_depth=2,graph_nodes=1))
    assert [item.memory_id for item in node_limited.memories]==["seed"]
    assert node_limited.retrieval_trace.graph_truncated
    assert "graph_expansion_truncated" in node_limited.warnings
    edge_limited=engine.retrieve(SCOPE,_request(graph_depth=2,graph_edges=1))
    assert edge_limited.retrieval_trace.graph_truncated
    assert edge_limited.retrieval_trace.graph_expanded_candidates <= 1
    with pytest.raises(GraphLimitError):
        engine.retrieve(SCOPE,_request(graph_depth=2,graph_work=1))


def test_default_budget_keeps_two_direct_lexical_facts_and_graph_does_not_lower_rank(tmp_path):
    path=tmp_path/"direct.sqlite3"
    SQLiteEventStore(path).initialize()
    _memory(path,"primary","OOMP project design uses Python.")
    _memory(path,"peer","OOMP project tests verify retrieval.")
    GraphService(path).link(
        SCOPE,"primary","peer",RelationshipType.RELATED_TO,("event-primary",),
    )
    engine=RetrievalEngine(path)
    direct=RetrievalRequest(
        tenant_id=SCOPE.tenant_id,namespace=SCOPE.namespace,query="OOMP project",
        graph_depth=0,
    )
    linked=RetrievalRequest(
        tenant_id=SCOPE.tenant_id,namespace=SCOPE.namespace,query="OOMP project",
        graph_depth=1,
    )
    baseline=engine.retrieve(SCOPE,direct)
    expanded=engine.retrieve(SCOPE,linked)
    assert {item.memory_id for item in baseline.memories}=={"primary","peer"}
    assert {item.memory_id for item in expanded.memories}=={"primary","peer"}
    baseline_scores={item.memory_id:item.retrieval_score for item in baseline.memories}
    expanded_scores={item.memory_id:item.retrieval_score for item in expanded.memories}
    assert all(expanded_scores[key]>=baseline_scores[key] for key in baseline_scores)
    assert expanded.token_budget==1200 and expanded.estimated_token_count<=1200
    assert all(item.source_event_ids for item in expanded.memories)
