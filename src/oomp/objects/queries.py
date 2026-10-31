"""Bounded snapshot navigation; every exposed node rechecks current evidence."""
from __future__ import annotations

from collections import deque
from datetime import datetime,timezone

from oomp.domain.graph import TemporalQuery
from oomp.storage.sqlite import _timestamp, _translate_sqlite_errors
from .contracts import (MemoryObject,Membership,ObjectCursor,ObjectMapError,ObjectPage,
    ObjectTree,ObjectTreeNode,ObjectType,STRUCTURAL_TYPES,bounded)
from .policy import status_for
from .storage import ID,MAX_OBJECTS,MAX_PROOFS,MAX_WORK,ObjectStorage,ReadBudget,object_id,scoped


class ReadContext:
    def __init__(self,query=None,maximum=MAX_WORK):
        if query is not None and not isinstance(query,TemporalQuery):raise ObjectMapError('object_temporal_query_required')
        self.query=TemporalQuery.model_validate(query.model_dump()) if query is not None else TemporalQuery()
        self.budget=ReadBudget(maximum)
        self.objects={}
        self.proofs={}
        self.relations={}
        self.cache={}


class ObjectQueries(ObjectStorage):
    def _proof(self,c,scope,row,ctx):
        key=row['proof_id']
        if key not in ctx.proofs:
            ctx.proofs[key]=self.validate_proof(c,scope,row,ctx.query,budget=ctx.budget,cache=ctx.cache)
        return ctx.proofs[key]

    def _get(self,c,scope,identifier,ctx):
        identifier=ID.validate_python(identifier)
        if identifier in ctx.objects:return ctx.objects[identifier]
        ctx.budget.charge()
        row=self.raw_object(c,scope,identifier)
        ctx.objects[identifier]=None
        if row is None:return None
        if ctx.query.known_at is not None and row['recorded_at']>_timestamp(ctx.query.known_at):return None
        _,partition=scoped(scope)
        rows=c.execute('SELECT * FROM map_proofs WHERE tenant_id=? AND namespace=? AND principal_id=? AND object_id=? ORDER BY proof_id LIMIT ?',
                       (*partition,identifier,MAX_PROOFS+1)).fetchall()
        if len(rows)>MAX_PROOFS:raise ObjectMapError('object_proof_limit')
        selected=[value for proof in rows if (value:=self._proof(c,scope,proof,ctx)) is not None]
        kind=ObjectType(row['object_type'])
        if not selected and kind not in STRUCTURAL_TYPES:return None
        if kind is ObjectType.TOPIC and row['reference_id'] is not None:
            # Context folders cannot outlive their source-backed parent view.
            if self._get(c,scope,row['reference_id'],ctx) is None:return None
        if kind is ObjectType.SESSION:
            children=c.execute('SELECT child_id FROM map_memberships WHERE tenant_id=? AND namespace=? AND principal_id=? AND parent_id=? ORDER BY child_id LIMIT 129',
                               (*partition,identifier)).fetchall()
            if len(children)>128:raise ObjectMapError('object_session_episode_limit')
            if not any(self._get(c,scope,child[0],ctx) is not None for child in children):return None
        if kind is ObjectType.SUMMARY_REVISION:
            actual={(value[0].memory_id,value[0].event_id) for value in selected}
            expected=set(tuple(link) for link in c.execute(
                'SELECT memory_id,event_id FROM mind_summary_sources WHERE tenant_id=? AND namespace=? AND revision_id=? LIMIT 17',
                (scope.tenant_id,scope.namespace,row['reference_id'])))
            if actual!=expected:return None
        if selected:
            selected.sort(key=lambda item:(item[0].occurred_at,item[0].recorded_at,item[0].event_id,item[0].source_span.start,item[0].proof_id))
            proof,label,_=selected[-1]
            aliases=tuple(dict.fromkeys(item[1] for item in selected if item[1]!=label))
            if len(aliases)>32:raise ObjectMapError('object_alias_limit')
            status=status_for(proof.assertion_kind,proof.semantic_role)
            if proof.sensitivity=='sensitive':status='attributed'
            from oomp.domain.enums import MemoryStatus
            if ctx.cache['states'][(proof.memory_id,ctx.query.known_at,ctx.query.valid_at)].effective_status is MemoryStatus.SUPERSEDED:
                status='superseded'
            occurred,valid_from,valid_until=proof.occurred_at,proof.valid_from,proof.valid_until
            from oomp.storage.graph_store import _valid_at
            validity=_valid_at(valid_from,valid_until,ctx.query.valid_at)
        else:
            label=row['structural_label']
            aliases=()
            status='structural'
            occurred=valid_from=valid_until=validity=None
        if kind is not ObjectType.OWNER and c.execute(
                'SELECT 1 FROM map_memberships WHERE tenant_id=? AND namespace=? AND principal_id=? AND child_id=? LIMIT 1',
                (*partition,identifier)).fetchone() is None:
            raise ObjectMapError('object_hierarchy_orphan')
        value=MemoryObject(object_id=identifier,object_type=kind,canonical_label=label,aliases=aliases,
            tenant_id=scope.tenant_id,namespace=scope.namespace,principal_id=scope.principal_id,
            reference_id=row['reference_id'],status=status,occurred_at=occurred,recorded_at=row['recorded_at'],
            valid_from=valid_from,valid_until=valid_until,validity=validity,
            source_proofs=tuple(item[0] for item in selected),creation_version=row['creation_version'])
        ctx.objects[identifier]=value
        return value

    @_translate_sqlite_errors
    def get_object(self,scope,identifier,*,query=None):
        scope,_=scoped(scope)
        with self._graph_read() as c:
            self.require_objects(c)
            return self._get(c,scope,identifier,ReadContext(query))

    @_translate_sqlite_errors
    def list_objects(self,scope,*,object_type=None,limit=100,cursor=None,query=None):
        scope,partition=scoped(scope)
        bounded(limit,1,500)
        kind=ObjectType(object_type) if object_type is not None else None
        after=''
        if cursor is not None:
            if not isinstance(cursor,ObjectCursor):raise ObjectMapError('object_cursor_invalid')
            cursor=ObjectCursor.model_validate(cursor.model_dump())
            if (cursor.tenant_id,cursor.namespace,cursor.principal_id,cursor.object_type)!=(*partition,kind):
                raise ObjectMapError('object_cursor_scope_or_filter_mismatch')
            after=cursor.after_id
        with self._graph_read() as c:
            self.require_objects(c)
            sql='SELECT object_id FROM map_objects WHERE tenant_id=? AND namespace=? AND principal_id=? AND object_id>?'
            args=[*partition,after]
            if kind is not None:sql+=' AND object_type=?';args.append(kind.value)
            rows=c.execute(sql+' ORDER BY object_id LIMIT ?',(*args,MAX_OBJECTS+1)).fetchall()
            if len(rows)>MAX_OBJECTS:raise ObjectMapError('object_partition_capacity')
            ctx=ReadContext(query)
            selected=[]
            for row in rows:
                value=self._get(c,scope,row[0],ctx)
                if value is not None:selected.append(value)
                if len(selected)>limit:break
            next_cursor=None
            if len(selected)>limit:
                selected=selected[:limit]
                next_cursor=ObjectCursor(tenant_id=scope.tenant_id,namespace=scope.namespace,principal_id=scope.principal_id,
                                         after_id=selected[-1].object_id,object_type=kind)
            return ObjectPage(objects=tuple(selected),next_cursor=next_cursor,examined=ctx.budget.used)

    @_translate_sqlite_errors
    def find_objects(self,scope,label,*,object_type=None,limit=100,query=None):
        scope,partition=scoped(scope)
        bounded(limit,1,100)
        if not isinstance(label,str) or not label.strip() or len(label)>160:raise ObjectMapError('object_label_query_invalid')
        kind=ObjectType(object_type) if object_type is not None else None
        with self._graph_read() as c:
            self.require_objects(c)
            rows=c.execute('''SELECT DISTINCT o.object_id FROM map_objects o LEFT JOIN map_proofs p
                            ON p.tenant_id=o.tenant_id AND p.namespace=o.namespace AND p.principal_id=o.principal_id AND p.object_id=o.object_id
                            WHERE o.tenant_id=? AND o.namespace=? AND o.principal_id=?
                              AND (p.label=? OR o.structural_label=?) ORDER BY o.object_id LIMIT 129''',
                            (*partition,label,label)).fetchall()
            if len(rows)>128:raise ObjectMapError('object_named_match_limit')
            ctx=ReadContext(query)
            selected=[]
            for row in rows:
                value=self._get(c,scope,row[0],ctx)
                if value is not None and (kind is None or value.object_type is kind) and label in (value.canonical_label,*value.aliases):
                    selected.append(value)
            return tuple(selected[:limit]),len(selected)>limit

    def _member(self,c,scope,row,ctx):
        ctx.budget.charge()
        if ctx.query.known_at is not None and row['recorded_at']>_timestamp(ctx.query.known_at):return None
        if self._get(c,scope,row['parent_id'],ctx) is None or self._get(c,scope,row['child_id'],ctx) is None:return None
        _,partition=scoped(scope)
        supports=c.execute('''SELECT s.*,p.object_id AS proof_object FROM map_membership_supports s
                            JOIN map_proofs p ON p.tenant_id=s.tenant_id AND p.namespace=s.namespace
                              AND p.principal_id=s.principal_id AND p.proof_id=s.proof_id
                            WHERE s.tenant_id=? AND s.namespace=? AND s.principal_id=?
                              AND s.parent_id=? AND s.child_id=? ORDER BY s.support_id LIMIT ?''',
                            (*partition,row['parent_id'],row['child_id'],MAX_PROOFS+1)).fetchall()
        if len(supports)>MAX_PROOFS:raise ObjectMapError('membership_support_limit')
        selected=[]
        for support in supports:
            if ctx.query.known_at is not None and support['recorded_at']>_timestamp(ctx.query.known_at):continue
            ctx.budget.charge()
            proof=c.execute('SELECT * FROM map_proofs WHERE tenant_id=? AND namespace=? AND principal_id=? AND proof_id=?',
                            (*partition,support['proof_id'])).fetchone()
            if proof is None or self._proof(c,scope,proof,ctx) is None:continue
            if support['relation_id'] is not None:
                from .relations import read_relation
                if read_relation(self,c,scope,support['relation_id'],ctx) is None:continue
            selected.append(support)
        if not selected and row['role'] not in {'domain','topic','session'}:return None
        return Membership(parent_id=row['parent_id'],child_id=row['child_id'],role=row['role'],recorded_at=row['recorded_at'],
            proof_id=selected[0]['proof_id'] if selected else None,
            relation_id=selected[0]['relation_id'] if selected else None,
            support_proof_ids=tuple(dict.fromkeys(s['proof_id'] for s in selected)),
            support_relation_ids=tuple(dict.fromkeys(s['relation_id'] for s in selected if s['relation_id'])))

    @_translate_sqlite_errors
    def memberships(self,scope,identifier,*,direction='children',limit=100,query=None):
        scope,partition=scoped(scope)
        identifier=ID.validate_python(identifier)
        bounded(limit,1,500)
        if direction not in {'children','parents'}:raise ObjectMapError('membership_direction_invalid')
        column='parent_id' if direction=='children' else 'child_id'
        with self._graph_read() as c:
            self.require_objects(c)
            ctx=ReadContext(query)
            if self._get(c,scope,identifier,ctx) is None:return (),False
            rows=c.execute('SELECT * FROM map_memberships WHERE tenant_id=? AND namespace=? AND principal_id=? AND '+column+'=? ORDER BY parent_id,child_id LIMIT ?',
                           (*partition,identifier,MAX_WORK+1)).fetchall()
            if len(rows)>MAX_WORK:raise ObjectMapError('membership_scan_limit')
            selected=[]
            for row in rows:
                value=self._member(c,scope,row,ctx)
                if value is not None:selected.append(value)
                if len(selected)>limit:return tuple(selected[:limit]),True
            return tuple(selected),False

    @_translate_sqlite_errors
    def tree(self,scope,*,root_id=None,max_depth=7,max_nodes=100,max_edges=300,max_work=3000,query=None):
        scope,partition=scoped(scope)
        bounded(max_depth,0,10);bounded(max_nodes,1,500);bounded(max_edges,1,2000);bounded(max_work,1,MAX_WORK)
        root=ID.validate_python(root_id) if root_id is not None else object_id(scope,ObjectType.OWNER,'root')
        with self._graph_read() as c:
            self.require_objects(c)
            ctx=ReadContext(query,max_work)
            queue=deque([(root,0)])
            selected={}
            edges=[]
            truncated=False
            while queue:
                identifier,depth=queue.popleft()
                if identifier in selected:continue
                if len(selected)>=max_nodes:truncated=True;break
                try:
                    value=self._get(c,scope,identifier,ctx)
                    if value is None:continue
                    selected[identifier]=ObjectTreeNode(object=value,depth=depth)
                    rows=c.execute('SELECT * FROM map_memberships WHERE tenant_id=? AND namespace=? AND principal_id=? AND parent_id=? ORDER BY child_id LIMIT ?',
                                   (*partition,identifier,max_work-ctx.budget.used+1)).fetchall()
                    if depth==max_depth:
                        truncated=truncated or bool(rows)
                        continue
                    for row in rows:
                        if len(edges)>=max_edges:truncated=True;break
                        edge=self._member(c,scope,row,ctx)
                        if edge is not None:
                            edges.append(edge)
                            queue.append((edge.child_id,depth+1))
                except ObjectMapError as error:
                    if error.code!='object_map_work_limit':raise
                    truncated=True;break
            # Never return edges pointing to nodes excluded by a finite budget.
            edges=[edge for edge in edges if edge.parent_id in selected and edge.child_id in selected]
            relations=[]
            from .relations import read_relation
            try:
                for identifier in sorted(selected):
                    if ctx.budget.used>=max_work:truncated=True;break
                    rows=c.execute('SELECT relation_id,target_id FROM map_relations WHERE tenant_id=? AND namespace=? AND principal_id=? AND source_id=? ORDER BY relation_id LIMIT ?',
                                   (*partition,identifier,max_work-ctx.budget.used+1)).fetchall()
                    for row in rows:
                        ctx.budget.charge()
                        if row['target_id'] not in selected:continue
                        value=read_relation(self,c,scope,row['relation_id'],ctx)
                        if value is not None:relations.append(value)
                        if len(relations)>=2000:truncated=True;break
                    if len(relations)>=2000:break
            except ObjectMapError as error:
                if error.code!='object_map_work_limit':raise
                truncated=True
            return ObjectTree(root_id=root,nodes=tuple(selected.values()),memberships=tuple(edges),
                              relations=tuple(relations),truncated=truncated,examined=min(ctx.budget.used,max_work))

    @_translate_sqlite_errors
    def relations(self,scope,identifier,*,limit=100,query=None):
        scope,partition=scoped(scope)
        identifier=ID.validate_python(identifier)
        bounded(limit,1,100)
        from .relations import read_relation
        with self._graph_read() as c:
            self.require_objects(c)
            ctx=ReadContext(query)
            if self._get(c,scope,identifier,ctx) is None:return (),False
            rows=c.execute('''SELECT relation_id FROM map_relations WHERE tenant_id=? AND namespace=? AND principal_id=?
                            AND (source_id=? OR target_id=?) ORDER BY relation_id LIMIT 1001''',
                            (*partition,identifier,identifier)).fetchall()
            if len(rows)>1000:raise ObjectMapError('object_relation_scan_limit')
            values=[]
            for row in rows:
                value=read_relation(self,c,scope,row[0],ctx)
                if value is not None:values.append(value)
                if len(values)>limit:return tuple(values[:limit]),True
            return tuple(values),False

    @_translate_sqlite_errors
    def history(self,scope,identifier,*,query=None):
        scope,partition=scoped(scope)
        identifier=ID.validate_python(identifier)
        with self._graph_read() as c:
            self.require_objects(c)
            ctx=ReadContext(query)
            obj=self.raw_object(c,scope,identifier)
            if obj is None:return None
            rows=c.execute('SELECT * FROM map_proofs WHERE tenant_id=? AND namespace=? AND principal_id=? AND object_id=? ORDER BY recorded_at,proof_id LIMIT 129',
                           (*partition,identifier)).fetchall()
            if len(rows)>128:raise ObjectMapError('object_history_limit')
            changes=[]
            for row in rows:
                value=self.validate_proof(c,scope,row,ctx.query,budget=ctx.budget,include_withdrawn=True,cache=ctx.cache)
                if value is None:continue
                proof,label,withdrawn=value
                changes.append({'label':label,'proof':proof.model_dump(mode='json'),
                    'status':'withdrawn' if withdrawn else status_for(proof.assertion_kind,proof.semantic_role)})
            changes.sort(key=lambda item:(item['proof']['occurred_at'],item['proof']['recorded_at'],item['proof']['proof_id']))
            revisions=[]
            if obj['object_type']=='episode':
                from oomp.understanding.episodes import EPISODE_POLICY,episode_snapshot
                rows=c.execute('SELECT * FROM mind_summary_revisions WHERE tenant_id=? AND namespace=? AND topic_id=? AND policy_version=? ORDER BY revision_number LIMIT 65',
                               (scope.tenant_id,scope.namespace,obj['reference_id'],EPISODE_POLICY)).fetchall()
                if len(rows)>64:raise ObjectMapError('object_revision_history_limit')
                for row in rows:
                    if ctx.query.known_at is not None and row['recorded_at']>_timestamp(ctx.query.known_at):continue
                    revision=self._read_summary(c,scope,row)
                    _,content,fingerprint=episode_snapshot(self,c,scope,obj['reference_id'],known_at=revision.recorded_at)
                    if content!=revision.content or fingerprint!=revision.source_fingerprint:
                        raise ObjectMapError('object_summary_history_invalid')
                    revisions.append({'revision_id':revision.revision_id,'revision_number':revision.revision_number,
                        'recorded_at':revision.recorded_at.isoformat(),'retired_at':revision.retired_at.isoformat() if revision.retired_at else None,
                        'source_event_ids':revision.source_event_ids,'source_memory_ids':revision.source_memory_ids,
                        'basis':'derived_extractive_summary','content':revision.content})
            return {'object_id':identifier,'object_type':obj['object_type'],'changes':changes,'summary_revisions':revisions,
                    'current_supported':self._get(c,scope,identifier,ctx) is not None}

    @_translate_sqlite_errors
    def explain(self,scope,identifier,*,max_paths=8,max_depth=10,max_work=4000,query=None):
        scope,partition=scoped(scope)
        identifier=ID.validate_python(identifier)
        bounded(max_paths,1,16);bounded(max_depth,1,10);bounded(max_work,1,10000)
        with self._graph_read() as c:
            self.require_objects(c)
            ctx=ReadContext(query,max_work)
            value=self._get(c,scope,identifier,ctx)
            if value is None:return None
            root=object_id(scope,ObjectType.OWNER,'root')
            queue=deque([(identifier,)])
            paths=[]
            truncated=False
            try:
                while queue and len(paths)<max_paths:
                    path=queue.popleft()
                    if path[-1]==root:paths.append(tuple(reversed(path)));continue
                    if len(path)>max_depth:truncated=True;continue
                    rows=c.execute('SELECT * FROM map_memberships WHERE tenant_id=? AND namespace=? AND principal_id=? AND child_id=? ORDER BY parent_id LIMIT ?',
                                   (*partition,path[-1],max_work-ctx.budget.used+1)).fetchall()
                    for row in rows:
                        edge=self._member(c,scope,row,ctx)
                        if edge is None:continue
                        if edge.parent_id in path:raise ObjectMapError('hierarchy_cycle')
                        queue.append(path+(edge.parent_id,))
                truncated=truncated or bool(queue)
            except ObjectMapError as error:
                if error.code!='object_map_work_limit':raise
                truncated=True
            evidence_paths=[]
            try:
                direct=c.execute('SELECT * FROM map_memberships WHERE tenant_id=? AND namespace=? AND principal_id=? AND parent_id=? ORDER BY child_id LIMIT 129',
                                 (*partition,identifier)).fetchall()
                if len(direct)>128:raise ObjectMapError('object_explanation_fanout_limit')
                for row in direct:
                    first=self._member(c,scope,row,ctx)
                    if first is None:continue
                    if first.role=='evidence':evidence_paths.append((identifier,first.child_id))
                    if first.role not in {'fact','revision'}:continue
                    linked=c.execute("SELECT * FROM map_memberships WHERE tenant_id=? AND namespace=? AND principal_id=? AND parent_id=? AND role='evidence' ORDER BY child_id LIMIT 129",
                                     (*partition,first.child_id)).fetchall()
                    if len(linked)>128:raise ObjectMapError('object_explanation_fanout_limit')
                    for item in linked:
                        last=self._member(c,scope,item,ctx)
                        if last is not None:evidence_paths.append((identifier,first.child_id,last.child_id))
            except ObjectMapError as error:
                if error.code!='object_map_work_limit':raise
                truncated=True
            return {'object':value.model_dump(mode='json'),'navigation_paths':paths,
                    'evidence_paths':evidence_paths,'direct_source_proofs':[p.model_dump(mode='json') for p in value.source_proofs],
                    'association_is_not_truth':True,'truncated':truncated,'examined':min(ctx.budget.used,max_work)}

    def export_redacted(self,scope,*,max_nodes=100,max_depth=10,query=None):
        from .storage import digest
        from .policy import DOMAINS
        safe_labels={'Owner','Conversation session','Plans and goals','Related plans','Referenced objects'}|{
            label for pair in DOMAINS.values() for label in pair}
        scope,partition=scoped(scope)
        result=self.tree(scope,max_nodes=max_nodes,max_depth=max_depth,max_edges=2000,max_work=10000,query=query)
        return {'schema':'object-map-export.v1','redacted':True,'scope_fingerprint':digest(partition),
            'objects':[{'object_id':n.object.object_id,'object_type':n.object.object_type.value,'status':n.object.status,
                        'label':n.object.canonical_label if n.object.object_type in STRUCTURAL_TYPES and n.object.canonical_label in safe_labels else None}
                       for n in result.nodes],
            'memberships':[{'parent_id':edge.parent_id,'child_id':edge.child_id,'role':edge.role} for edge in result.memberships],
            'relations':[{'relation_id':rel.relation_id,'source_id':rel.source_id,'target_id':rel.target_id,
                          'relationship_type':rel.relationship_type.value,'semantic_role':rel.semantic_role,
                          'basis':rel.basis,'status':rel.status,'proof_ids':rel.proof_ids} for rel in result.relations],
            'truncated':result.truncated,'source_bodies_exported':False,'private_labels_exported':False}
