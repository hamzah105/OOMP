"""Opt-in P3 association candidates using its existing read-time proof policy."""
from oomp.objects.contracts import ObjectMapError
from oomp.objects.queries import ReadContext
from oomp.objects.relations import read_relation
from oomp.storage.sqlite import _timestamp


def associated_objects(objects, session, scope, initial, plan, temporal, request, check):
    roots = tuple(obj for obj in initial if set(plan.anchors) & {obj.canonical_label, *obj.aliases})
    if not request.graph_depth or not roots or not request.graph_relationships:
        return (), {}, False
    c = session._connection
    ctx = ReadContext(temporal, maximum=request.graph_work)
    ctx.objects.update((obj.object_id, obj) for obj in roots)
    visited = {obj.object_id for obj in roots[:request.graph_nodes]}
    frontier = list(sorted(visited))
    found = []
    edges = set()
    truncated = len(roots) > request.graph_nodes
    for _ in range(request.graph_depth):
        following = []
        for identifier in frontier:
            check()
            remaining = request.graph_edges - len(edges)
            if remaining <= 0:
                truncated = True
                break
            sql = '''SELECT * FROM map_relations WHERE tenant_id=? AND namespace=? AND principal_id=?
                     AND (source_id=? OR target_id=?) AND relationship_type IN ('''+','.join('?' for _ in request.graph_relationships)+')'
            args = [scope.tenant_id, scope.namespace, scope.principal_id, identifier, identifier,
                    *(kind.value for kind in request.graph_relationships)]
            if temporal.known_at is not None:
                sql += ' AND recorded_at<=?'
                args.append(_timestamp(temporal.known_at))
            owned, values = session._edge_predicate('g')
            sql += ''' AND (graph_edge_id IS NULL OR EXISTS (
                SELECT 1 FROM memory_edges g WHERE g.tenant_id=map_relations.tenant_id
                AND g.namespace=map_relations.namespace AND g.edge_id=map_relations.graph_edge_id
                AND ('''+owned+')))'
            args.extend(values)
            rows = c.execute(sql+' ORDER BY recorded_at,relation_id LIMIT ?',(*args,remaining+1)).fetchall()
            truncated |= len(rows) > remaining
            for row in rows[:remaining]:
                check()
                if ctx.budget.used >= request.graph_work:
                    truncated = True
                    break
                if row['relation_id'] in edges:
                    continue
                edges.add(row['relation_id'])
                if row['graph_edge_id'] is not None:
                    owned, values = session._edge_predicate('g')
                    if not c.execute('SELECT 1 FROM memory_edges g WHERE g.tenant_id=? AND g.namespace=? AND g.edge_id=? AND ('+owned+')',
                                     (scope.tenant_id,scope.namespace,row['graph_edge_id'],*values)).fetchone():
                        continue
                try:
                    relation = read_relation(objects,c,scope,row['relation_id'],ctx)
                    if relation is None:
                        continue
                    target = relation.target_id if relation.source_id == identifier else relation.source_id
                    if target in visited:
                        continue
                    if len(visited) >= request.graph_nodes:
                        truncated = True
                        continue
                    obj = objects._get(c,scope,target,ctx)
                except ObjectMapError:
                    truncated = True
                    continue
                if obj is not None:
                    visited.add(target)
                    following.append(target)
                    found.append(obj)
        frontier = following
        if not frontier or truncated:
            break
    return tuple(found), {'p3_association_edges':len(edges),'p3_association_nodes':len(visited),
                          'p3_association_work':min(ctx.budget.used,request.graph_work),
                          'p3_association_truncated':int(truncated)}, True
