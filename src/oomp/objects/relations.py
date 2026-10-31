"""Association proposals are independently grounded again on every read/write."""
from __future__ import annotations

import json
import re

from oomp.domain.enums import RelationshipType
from oomp.storage.graph_store import _edge_endorsed,_valid_at
from oomp.storage.sqlite import _timestamp
from .contracts import ObjectMapError,ObjectRelation,ObjectType
from .storage import ID,digest,scoped


def contexts(c,scope,event_id,ctx):
    cache=ctx.cache.setdefault('contexts',{})
    if event_id not in cache:
        rows=c.execute('''SELECT t.topic_id,m.metadata_json FROM topic_memberships t
                        JOIN memories m ON m.tenant_id=t.tenant_id AND m.namespace=t.namespace AND m.memory_id=t.memory_id
                        JOIN memory_sources s ON s.tenant_id=m.tenant_id AND s.namespace=m.namespace AND s.memory_id=m.memory_id
                        WHERE t.tenant_id=? AND t.namespace=? AND s.event_id=? AND t.topic_id LIKE 'p2episode-%' LIMIT 65''',
                        (scope.tenant_id,scope.namespace,event_id)).fetchall()
        if len(rows)>64:raise ObjectMapError('object_episode_context_limit')
        ctx.budget.charge(len(rows))
        try:
            cache[event_id]={row['topic_id'] for row in rows if json.loads(row['metadata_json']).get('p2_episode') is True
                and json.loads(row['metadata_json']).get('principal_id',scope.principal_id)==scope.principal_id}
        except (ValueError,TypeError):raise ObjectMapError('object_episode_context_invalid') from None
    return cache[event_id]


def shared_context(c,scope,first,second,ctx):
    return first.event_id==second.event_id or bool(contexts(c,scope,first.event_id,ctx)&contexts(c,scope,second.event_id,ctx))


def unique_project(store,c,scope,label,identifier,ctx):
    rows=c.execute('''SELECT p.* FROM map_proofs p JOIN map_objects o
                    ON o.tenant_id=p.tenant_id AND o.namespace=p.namespace AND o.principal_id=p.principal_id AND o.object_id=p.object_id
                    WHERE p.tenant_id=? AND p.namespace=? AND p.principal_id=? AND o.object_type='project' AND p.label=? LIMIT 129''',
                    (scope.tenant_id,scope.namespace,scope.principal_id,label)).fetchall()
    if len(rows)>128:raise ObjectMapError('object_named_match_limit')
    return {row['object_id'] for row in rows if store._proof(c,scope,row,ctx) is not None}=={identifier}


def validate_semantics(store,c,scope,source,target,relation_type,role,proofs,ctx,graph_edge_id=None):
    """No similarity scores, model labels or caller descriptions justify a link."""
    own=[(row,value[0]) for row,value in proofs if row['object_id']==source.object_id]
    other=[(row,value[0]) for row,value in proofs if row['object_id']==target.object_id]
    if not own or not other:return False
    if role=='existing_graph':
        if graph_edge_id is None:return False
        row=c.execute('SELECT * FROM memory_edges WHERE tenant_id=? AND namespace=? AND edge_id=?',
                      (scope.tenant_id,scope.namespace,graph_edge_id)).fetchone()
        if row is None:return False
        record=store._read_edge(c,scope,row)
        edge=record.edge
        if ctx.query.known_at is not None and record.recorded_at>ctx.query.known_at:return False
        return (edge.source_node_id==source.reference_id and edge.target_node_id==target.reference_id
                and edge.relationship_type is relation_type and _edge_endorsed(c,scope,record,ctx.query.known_at)
                and _valid_at(edge.valid_from,edge.valid_until,ctx.query.valid_at) is not False
                and set(edge.source_event_ids)<=set(value[0].event_id for _,value in proofs))
    if graph_edge_id is not None or relation_type in {RelationshipType.SUPERSEDES,RelationshipType.CONTRADICTS}:
        return False
    if role=='derivation':
        return (relation_type is RelationshipType.DERIVED_FROM and source.object_type is ObjectType.FACT
                and target.object_type is ObjectType.SOURCE_EVENT and
                any(a.memory_id==source.reference_id and a.event_id==target.reference_id==b.event_id
                    for _,a in own for _,b in other))
    if role in {'candidate_for','origin','decision_criterion'}:
        expected_kind=ObjectType.CONCEPT if role=='decision_criterion' else ObjectType.PLACE
        expected_role={'candidate_for':'candidate_place','origin':'origin_place','decision_criterion':'decision_criterion'}[role]
        return (relation_type is RelationshipType.RELATED_TO and source.object_type is expected_kind
                and target.object_type is ObjectType.PLAN and
                any(a.semantic_role==expected_role and b.semantic_role=='relocation_plan'
                    and shared_context(c,scope,a,b,ctx) for _,a in own for _,b in other))
    if role=='about':
        return (relation_type is RelationshipType.ABOUT and source.object_type is ObjectType.EPISODE
                and target.object_type not in {ObjectType.OWNER,ObjectType.DOMAIN,ObjectType.TOPIC,ObjectType.SOURCE_EVENT}
                and any(a.semantic_role=='episode' and source.reference_id in contexts(c,scope,b.event_id,ctx)
                        for _,a in own for _,b in other))
    if role=='correction_review':
        from .policy import seeds
        from oomp.storage.memory_store import _event_in_scope
        return (relation_type is RelationshipType.RELATED_TO and source.object_type is ObjectType.FACT
                and target.object_type is ObjectType.PLAN and any(
                    a.occurred_at>=b.occurred_at and shared_context(c,scope,a,b,ctx)
                    and any(seed.role=='plan_correction' for seed in seeds(_event_in_scope(c,scope,a.event_id),a.source_span))
                    for _,a in own for _,b in other if b.semantic_role=='relocation_plan'))
    if role=='work_context':
        criteria=[value[0] for row,value in proofs if value[0].semantic_role=='decision_criterion']
        return (relation_type is RelationshipType.RELATED_TO and source.object_type is ObjectType.PROJECT
                and target.object_type is ObjectType.PLAN and any(
                    shared_context(c,scope,criterion,plan,ctx) and 'relocation' in criterion.source_span.quote.casefold()
                    and re.search(r'\bfor project '+re.escape(row['label'])+r'(?=[.!?]*$)',criterion.source_span.quote)
                    and unique_project(store,c,scope,row['label'],source.object_id,ctx)
                    for row,project in own for _,plan in other for criterion in criteria
                    if project.semantic_role in {'project_name','project_rename'} and plan.semantic_role=='relocation_plan'))
    return False


def read_relation(store,c,scope,identifier,ctx):
    identifier=ID.validate_python(identifier)
    if identifier in ctx.relations:return ctx.relations[identifier]
    ctx.budget.charge()
    ctx.relations[identifier]=None
    _,partition=scoped(scope)
    row=c.execute('SELECT * FROM map_relations WHERE tenant_id=? AND namespace=? AND principal_id=? AND relation_id=?',
                  (*partition,identifier)).fetchone()
    if row is None:return None
    if ctx.query.known_at is not None and row['recorded_at']>_timestamp(ctx.query.known_at):return None
    if _valid_at(row['valid_from'],row['valid_until'],_timestamp(ctx.query.valid_at) if ctx.query.valid_at else None) is False:return None
    source=store._get(c,scope,row['source_id'],ctx)
    target=store._get(c,scope,row['target_id'],ctx)
    if source is None or target is None:return None
    rows=c.execute('''SELECT p.* FROM map_relation_proofs s JOIN map_proofs p
                    ON p.tenant_id=s.tenant_id AND p.namespace=s.namespace AND p.principal_id=s.principal_id AND p.proof_id=s.proof_id
                    WHERE s.tenant_id=? AND s.namespace=? AND s.principal_id=? AND s.relation_id=? ORDER BY p.proof_id LIMIT 17''',
                    (*partition,identifier)).fetchall()
    if len(rows)!=row['proof_count'] or len(rows)>16:return None
    proofs=[]
    for proof in rows:
        value=store._proof(c,scope,proof,ctx)
        if value is None:return None
        proofs.append((proof,value))
    try:kind=RelationshipType(row['relationship_type'])
    except ValueError:raise ObjectMapError('object_relation_type_invalid') from None
    expected_basis=('existing_graph' if row['graph_edge_id'] else 'derived_context' if row['semantic_role'] in {'about','correction_review'}
                    else 'source_span' if len({value[0].event_id for _,value in proofs})==1 else 'derived_context')
    if row['basis']!=expected_basis:raise ObjectMapError('object_relation_basis_invalid')
    if row['graph_edge_id'] is None and (row['valid_from'] is not None or row['valid_until'] is not None):
        raise ObjectMapError('object_relation_validity_not_grounded')
    if row['graph_edge_id'] is not None:
        graph=c.execute('SELECT valid_from,valid_until FROM memory_edges WHERE tenant_id=? AND namespace=? AND edge_id=?',
                        (scope.tenant_id,scope.namespace,row['graph_edge_id'])).fetchone()
        if graph is None or (row['valid_from'],row['valid_until'])!=tuple(graph):
            raise ObjectMapError('object_relation_validity_not_grounded')
    if not validate_semantics(store,c,scope,source,target,kind,row['semantic_role'],proofs,ctx,row['graph_edge_id']):
        raise ObjectMapError('object_relation_not_grounded')
    statuses={source.status,target.status}
    status=('correction_pending' if row['semantic_role']=='correction_review' or 'correction_pending' in statuses
            else 'tentative' if 'tentative' in statuses else 'attributed' if 'attributed' in statuses else 'claimed')
    value=ObjectRelation(relation_id=identifier,source_id=source.object_id,target_id=target.object_id,
        relationship_type=kind,semantic_role=row['semantic_role'],basis=row['basis'],status=status,
        recorded_at=row['recorded_at'],valid_from=row['valid_from'],valid_until=row['valid_until'],
        proof_ids=tuple(proof['proof_id'] for proof,_ in proofs),graph_edge_id=row['graph_edge_id'])
    ctx.relations[identifier]=value
    return value


def put_relation(store,c,scope,source_id,target_id,relation_type,role,proof_ids,*,graph_edge_id=None,counts=None):
    from .queries import ReadContext
    scope,partition=scoped(scope)
    try:kind=RelationshipType(relation_type)
    except ValueError:raise ObjectMapError('object_relation_type_invalid') from None
    proof_ids=tuple(sorted(set(ID.validate_python(value) for value in proof_ids)))
    if not 1<=len(proof_ids)<=16 or source_id==target_id:raise ObjectMapError('object_relation_bounds_invalid')
    ctx=ReadContext()
    source,target=store._get(c,scope,source_id,ctx),store._get(c,scope,target_id,ctx)
    if source is None or target is None:raise ObjectMapError('object_relation_endpoint_invalid')
    proofs=[]
    for proof_id in proof_ids:
        row=c.execute('SELECT * FROM map_proofs WHERE tenant_id=? AND namespace=? AND principal_id=? AND proof_id=?',
                      (*partition,proof_id)).fetchone()
        value=store._proof(c,scope,row,ctx) if row is not None else None
        if value is None:raise ObjectMapError('object_relation_proof_invalid')
        proofs.append((row,value))
    if not validate_semantics(store,c,scope,source,target,kind,role,proofs,ctx,graph_edge_id):
        raise ObjectMapError('object_relation_not_grounded')
    identifier='objrel-'+digest([source_id,target_id,kind.value,role,proof_ids,graph_edge_id])
    prior=c.execute('SELECT 1 FROM map_relations WHERE tenant_id=? AND namespace=? AND principal_id=? AND relation_id=?',
                    (*partition,identifier)).fetchone()
    if prior:return identifier
    count=c.execute('SELECT COUNT(*) FROM map_relations WHERE tenant_id=? AND namespace=? AND principal_id=?',partition).fetchone()[0]
    if count>=10000:raise ObjectMapError('object_relation_capacity')
    status='correction_pending' if role=='correction_review' else ('tentative' if 'tentative' in {source.status,target.status}
        else 'attributed' if 'attributed' in {source.status,target.status} else 'claimed')
    basis=('existing_graph' if graph_edge_id else 'derived_context' if role in {'about','correction_review'}
           else 'source_span' if len({value[0].event_id for _,value in proofs})==1 else 'derived_context')
    valid_from=valid_until=None
    if graph_edge_id:
        graph=c.execute('SELECT valid_from,valid_until FROM memory_edges WHERE tenant_id=? AND namespace=? AND edge_id=?',
                        (scope.tenant_id,scope.namespace,graph_edge_id)).fetchone()
        valid_from,valid_until=graph
    c.execute('''INSERT INTO map_relations (tenant_id,namespace,principal_id,relation_id,source_id,target_id,
              relationship_type,semantic_role,basis,status,proof_count,recorded_at,valid_from,valid_until,graph_edge_id)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,oomp_recorded_at(),?,?,?)''',
              (*partition,identifier,source_id,target_id,kind.value,role,basis,status,len(proof_ids),valid_from,valid_until,graph_edge_id))
    for proof_id in proof_ids:
        c.execute('INSERT INTO map_relation_proofs (tenant_id,namespace,principal_id,relation_id,proof_id) VALUES (?,?,?,?,?)',
                  (*partition,identifier,proof_id))
    if counts is not None:counts['relations_added']+=1
    return identifier
