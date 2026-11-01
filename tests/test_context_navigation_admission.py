"""P3 graph permission admission happens before the requested edge limit."""
from oomp.context.contracts import ContextRequest, QueryPlan, RetrievalIntent
from oomp.context.engine import _Objects
from oomp.context.navigation import associated_objects
from oomp.domain.enums import RelationshipType
from oomp.domain.graph import TemporalQuery
from oomp.graph import GraphService
from oomp.objects import ObjectMap
from oomp.objects.queries import ReadContext
from oomp.storage.retrieval_store import SQLiteRetrievalStore
from oomp.storage.memory_store import SQLiteMemoryStore
from test_object_storage import SCOPE, setup


def test_foreign_graph_actor_cannot_consume_owner_p3_edge_limit(tmp_path):
    path = tmp_path / "synthetic-navigation-admission.sqlite3"
    _, root_event, root_memory = setup(path, event_id="root-source")
    setup(path, "I plan to build a paper model.", event_id="foreign-target")
    setup(path, "I prefer concise technical explanations.", event_id="allowed-target")
    memories = SQLiteMemoryStore(path).list_memories(SCOPE).memories
    foreign_target_memory = next(m for m in memories if "foreign-target" in m.source_event_ids
                                 and m.metadata.get('p2_episode') is not True)
    allowed_memory = next(m for m in memories if "allowed-target" in m.source_event_ids
                          and m.metadata.get('p2_episode') is not True)
    graph = ObjectMap(path)
    graph.build(SCOPE, limit=100)
    facts = {obj.reference_id: obj for obj in graph.list_objects(SCOPE, object_type="fact").objects}
    root = facts[root_memory.memory_id]
    rejected = facts[foreign_target_memory.memory_id]
    allowed = facts[allowed_memory.memory_id]
    service = GraphService(path)
    other_actor = SCOPE.model_copy(update={"principal_id": "different-operator"})

    def associate(target, actor):
        edge = service.link(actor, root.reference_id, target.reference_id,
            RelationshipType.RELATED_TO, (root_event.event_id,))
        relation = graph.associate(SCOPE, root.object_id, target.object_id,
            RelationshipType.RELATED_TO, "existing_graph",
            (root.source_proofs[0].proof_id, target.source_proofs[0].proof_id),
            graph_edge_id=edge.edge.edge_id)
        return relation

    # Both associations pass the existing P3 proof policy. The new context
    # policy excludes the first graph actor before counting a one-edge page.
    denied_relation = associate(rejected, other_actor)
    allowed_relation = associate(allowed, SCOPE)
    assert {item.relation_id for item in graph.relations(SCOPE, root.object_id)[0]} >= {
        denied_relation, allowed_relation}

    request = ContextRequest(tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
        query="Find the associated claim.", anchors=(root.canonical_label,),
        graph_depth=1, graph_nodes=3, graph_edges=1, graph_work=400,
        graph_relationships=(RelationshipType.RELATED_TO,))
    plan = QueryPlan(retrieval_intent=RetrievalIntent.ENTITY_LOOKUP,
        anchors=request.anchors, query_variants=(request.query,))
    temporal = TemporalQuery()
    with SQLiteRetrievalStore(path).read_snapshot(SCOPE, principal_only=True) as session:
        rows = session._connection.execute("""SELECT relation_id FROM map_relations
            WHERE tenant_id=? AND namespace=? AND principal_id=? AND source_id=?
              AND relationship_type='RELATED_TO' ORDER BY recorded_at,relation_id""",
            (SCOPE.tenant_id, SCOPE.namespace, SCOPE.principal_id, root.object_id)).fetchall()
        assert [row[0] for row in rows] == [denied_relation, allowed_relation]
        objects = _Objects(path, session)
        root = objects._get(session._connection, SCOPE, root.object_id, ReadContext(temporal))
        found, trace, enabled = associated_objects(objects, session, SCOPE,
            (root,), plan, temporal, request, lambda: None)
    assert enabled
    assert [obj.object_id for obj in found] == [allowed.object_id]
    assert rejected.object_id not in {obj.object_id for obj in found}
    assert trace["p3_association_edges"] == 1
    assert trace["p3_association_nodes"] == 2
    assert trace["p3_association_truncated"] == 0
