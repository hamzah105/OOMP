"""Explicit, bounded materialization of the source-backed object map."""
from __future__ import annotations

import json

from oomp.domain.enums import RelationshipType
from oomp.domain.graph import TemporalQuery
from oomp.mind.contracts import MindJob,JobType
from oomp.storage.graph_store import _source_retracted
from oomp.storage.memory_store import _event_in_scope
from oomp.storage.sqlite import _timestamp,_translate_sqlite_errors
from .contracts import BuildResult,ObjectMapError,ObjectType,bounded
from .policy import DOMAINS,episode_label,seeds,source_allowed
from .queries import ObjectQueries,ReadContext
from .relations import contexts,put_relation,shared_context
from .storage import ID,MAX_PROOFS,digest,scoped


def counters():
    return {name:0 for name in ('events_examined','objects_created','proofs_added','memberships_added','relations_added','rejected','unresolved')}


class ObjectMap(ObjectQueries):
    def _root(self,c,scope,counts):
        return self.registry(c,scope,ObjectType.OWNER,'root',structural_label='Owner',counts=counts)

    def _default(self,c,scope,identifier,kind,proof,counts,*,role=None):
        owner=self._root(c,scope,counts)
        domain_name,topic_name=DOMAINS[kind]
        if kind is ObjectType.PLAN and role in {'relocation_plan','plan_correction'}:topic_name='Relocation'
        elif kind is ObjectType.PLAN:topic_name='Plans and goals'
        domain=self.registry(c,scope,ObjectType.DOMAIN,['domain',domain_name],structural_label=domain_name,counts=counts)
        topic=self.registry(c,scope,ObjectType.TOPIC,['domain-topic',domain_name,topic_name],structural_label=topic_name,counts=counts)
        self.membership(c,scope,owner,domain,'domain',counts=counts)
        self.membership(c,scope,domain,topic,'topic',counts=counts)
        self.membership(c,scope,topic,identifier,'object',proof_id=proof,counts=counts)

    def _named(self,c,scope,kind,label,ctx,*,event=None):
        _,partition=scoped(scope)
        rows=c.execute('''SELECT DISTINCT p.* FROM map_proofs p JOIN map_objects o
                        ON o.tenant_id=p.tenant_id AND o.namespace=p.namespace AND o.principal_id=p.principal_id AND o.object_id=p.object_id
                        WHERE p.tenant_id=? AND p.namespace=? AND p.principal_id=? AND o.object_type=? AND p.label=?
                        ORDER BY p.proof_id LIMIT 129''',(*partition,kind.value,label)).fetchall()
        if len(rows)>MAX_PROOFS:raise ObjectMapError('object_named_match_limit')
        selected={}
        for row in rows:
            value=self._proof(c,scope,row,ctx)
            if value is None:continue
            if event is not None:
                if value[0].occurred_at>event.occurred_at:continue
                if value[0].event_id!=event.event_id and not contexts(c,scope,value[0].event_id,ctx)&contexts(c,scope,event.event_id,ctx):continue
            selected.setdefault(row['object_id'],row['proof_id'])
        return selected

    def _plan(self,c,scope,event,ctx):
        _,partition=scoped(scope)
        topics=tuple(sorted(contexts(c,scope,event.event_id,ctx)))
        restriction='p.event_id=?'
        values=[event.event_id]
        if topics:
            restriction+=' OR EXISTS (SELECT 1 FROM memory_sources s JOIN topic_memberships t ON t.tenant_id=s.tenant_id AND t.namespace=s.namespace AND t.memory_id=s.memory_id WHERE s.tenant_id=p.tenant_id AND s.namespace=p.namespace AND s.event_id=p.event_id AND t.topic_id IN ('+','.join('?' for _ in topics)+'))'
            values.extend(topics)
        rows=c.execute('''SELECT p.* FROM map_proofs p JOIN map_objects o
                        ON o.tenant_id=p.tenant_id AND o.namespace=p.namespace AND o.principal_id=p.principal_id AND o.object_id=p.object_id
                        WHERE p.tenant_id=? AND p.namespace=? AND p.principal_id=? AND o.object_type='plan'
                          AND p.semantic_role='relocation_plan' AND ('''+restriction+
                          ') ORDER BY p.recorded_at,p.proof_id LIMIT 129',(*partition,*values)).fetchall()
        if len(rows)>MAX_PROOFS:raise ObjectMapError('object_context_plan_limit')
        selected={}
        for row in rows:
            value=self._proof(c,scope,row,ctx)
            if value is None or value[0].occurred_at>event.occurred_at:continue
            if value[0].event_id==event.event_id or contexts(c,scope,value[0].event_id,ctx)&contexts(c,scope,event.event_id,ctx):
                selected.setdefault(row['object_id'],row['proof_id'])
        return next(iter(selected.items())) if len(selected)==1 else None

    def _context_membership(self,c,scope,parent,child,parent_proof,child_proof,role,relation,counts):
        label='Related plans' if role=='related_plans' else 'Referenced objects'
        topic=self.registry(c,scope,ObjectType.TOPIC,[role,parent],reference=parent,structural_label=label,counts=counts)
        self.membership(c,scope,parent,topic,role,proof_id=parent_proof,counts=counts)
        self.membership(c,scope,topic,child,'object',proof_id=child_proof,relation_id=relation,counts=counts)

    def _typed(self,c,scope,event,memory,span,seed,fact,fact_proof,counts):
        ctx=ReadContext()
        identifier=None
        if seed.previous_label is not None:
            matches=self._named(c,scope,seed.kind,seed.previous_label,ctx)
            if len(matches)!=1:counts['unresolved']+=1;return None
            identifier=next(iter(matches))
        elif seed.role=='plan_correction':
            plan=self._plan(c,scope,event,ctx)
            if plan is None:counts['unresolved']+=1;return None
            identifier=plan[0]
        elif seed.kind in {ObjectType.PLACE,ObjectType.CONCEPT}:
            matches=self._named(c,scope,seed.kind,seed.label,ctx,event=event)
            if len(matches)==1:identifier=next(iter(matches))
            elif len(matches)>1:counts['unresolved']+=1
        if identifier is None:
            anchor=['memory',memory.memory_id] if seed.kind in {ObjectType.PERSON,ObjectType.PROJECT,ObjectType.PLAN} else [
                'source-mention',event.event_id,span.start,seed.label_start,seed.kind.value]
            identifier=self.registry(c,scope,seed.kind,anchor,reference=memory.memory_id,counts=counts)
        proof=self.put_proof(c,scope,identifier,memory,event,span,role=seed.role,label=seed.label,
                             label_start=seed.label_start,label_end=seed.label_end,counts=counts)
        self._default(c,scope,identifier,seed.kind,proof,counts,role=seed.role)
        self.membership(c,scope,identifier,fact,'fact',proof_id=proof,counts=counts)
        if seed.role in {'candidate_place','origin_place','decision_criterion','plan_correction'}:
            plan=self._plan(c,scope,event,ReadContext())
            if plan is None:counts['unresolved']+=1
            else:
                plan_id,plan_proof=plan
                if seed.role=='plan_correction':
                    put_relation(self,c,scope,fact,plan_id,RelationshipType.RELATED_TO,'correction_review',
                                 (fact_proof,plan_proof),counts=counts)
                else:
                    role={'candidate_place':'candidate_for','origin_place':'origin','decision_criterion':'decision_criterion'}[seed.role]
                    relation=put_relation(self,c,scope,identifier,plan_id,RelationshipType.RELATED_TO,role,(proof,plan_proof),counts=counts)
                    if seed.kind is ObjectType.PLACE:
                        self._context_membership(c,scope,identifier,plan_id,proof,plan_proof,'related_plans',relation,counts)
                    if seed.role=='decision_criterion':
                        import re
                        match=re.search(r'\bfor project (?P<name>[\w][\w .\u2019\'-]{0,79}?)[.!?]*$',span.quote,re.I)
                        if match:
                            projects=self._named(c,scope,ObjectType.PROJECT,match['name'].rstrip(' .!?'),ReadContext())
                            if len(projects)==1:
                                project_id,project_proof=next(iter(projects.items()))
                                put_relation(self,c,scope,project_id,plan_id,RelationshipType.RELATED_TO,'work_context',
                                             (project_proof,plan_proof,proof),counts=counts)
                            else:counts['unresolved']+=1
        return identifier,proof

    def _source(self,c,scope,event,memory,span,counts):
        _,partition=scoped(scope)
        source=self.registry(c,scope,ObjectType.SOURCE_EVENT,['source',event.event_id],reference=event.event_id,counts=counts)
        rows=c.execute('''SELECT * FROM map_proofs WHERE tenant_id=? AND namespace=? AND principal_id=?
                        AND object_id=? AND span_start=? AND span_end=? AND semantic_role='source' ORDER BY proof_id LIMIT 129''',
                        (*partition,source,span.start,span.end)).fetchall()
        if len(rows)>128:raise ObjectMapError('object_source_proof_limit')
        proof=next((row['proof_id'] for row in rows if self.validate_proof(c,scope,row) is not None),None)
        if proof is None:
            proof=self.put_proof(c,scope,source,memory,event,span,role='source',label='Original source',counts=counts)
        self._default(c,scope,source,ObjectType.SOURCE_EVENT,proof,counts)
        return source,proof

    def _summary(self,c,scope,episode,topic,counts):
        from oomp.understanding.episodes import EPISODE_POLICY
        revision=c.execute('''SELECT * FROM mind_summary_revisions WHERE tenant_id=? AND namespace=?
                            AND topic_id=? AND retired_at IS NULL AND policy_version=?''',
                            (scope.tenant_id,scope.namespace,topic,EPISODE_POLICY)).fetchone()
        if revision is None:return
        identifier=self.registry(c,scope,ObjectType.SUMMARY_REVISION,['revision',revision['revision_id']],
                                 reference=revision['revision_id'],counts=counts)
        rows=c.execute('SELECT memory_id,event_id FROM mind_summary_sources WHERE tenant_id=? AND namespace=? AND revision_id=? ORDER BY memory_id,event_id LIMIT 17',
                       (scope.tenant_id,scope.namespace,revision['revision_id'])).fetchall()
        if not rows or len(rows)>16:raise ObjectMapError('object_summary_source_limit')
        for row in rows:
            event=_event_in_scope(c,scope,row['event_id'])
            memory_row=c.execute('SELECT * FROM memories WHERE tenant_id=? AND namespace=? AND memory_id=?',
                                 (scope.tenant_id,scope.namespace,row['memory_id'])).fetchone()
            memory=self._read_memory(c,scope,memory_row)
            span=self.stored_span(c,scope,memory.memory_id,event.event_id)
            if span is None:raise ObjectMapError('object_summary_span_missing')
            proof=self.put_proof(c,scope,identifier,memory,event,span,role='summary_revision',
                                 label='Summary revision '+str(revision['revision_number']),counts=counts)
            self._default(c,scope,identifier,ObjectType.SUMMARY_REVISION,proof,counts)
            self.membership(c,scope,episode,identifier,'revision',proof_id=proof,counts=counts)
            source,_=self._source(c,scope,event,memory,span,counts)
            self.membership(c,scope,identifier,source,'evidence',proof_id=proof,counts=counts)

    def _episodes(self,c,scope,event,episode_records,fact,fact_proof,typed,counts):
        for memory,span in episode_records:
            topics=c.execute('SELECT topic_id FROM topic_memberships WHERE tenant_id=? AND namespace=? AND memory_id=? ORDER BY topic_id LIMIT 17',
                             (scope.tenant_id,scope.namespace,memory.memory_id)).fetchall()
            if len(topics)>16:raise ObjectMapError('object_episode_membership_limit')
            for topic_row in topics:
                topic=topic_row[0]
                if not topic.startswith('p2episode-'):continue
                episode=self.registry(c,scope,ObjectType.EPISODE,['episode',topic],reference=topic,counts=counts)
                proof=self.put_proof(c,scope,episode,memory,event,span,role='episode',label=episode_label(span.quote),counts=counts)
                self._default(c,scope,episode,ObjectType.EPISODE,proof,counts)
                session=event.source_reference.session_id
                if session is not None:
                    session_object=self.registry(c,scope,ObjectType.SESSION,['session',session],reference='session-'+digest(session),
                                                 structural_label='Conversation session',counts=counts)
                    self.membership(c,scope,self._root(c,scope,counts),session_object,'session',counts=counts)
                    self.membership(c,scope,session_object,episode,'episode',proof_id=proof,counts=counts)
                about=put_relation(self,c,scope,episode,fact,RelationshipType.ABOUT,'about',(proof,fact_proof),counts=counts)
                self.membership(c,scope,episode,fact,'fact',proof_id=fact_proof,relation_id=about,counts=counts)
                for identifier,object_proof in typed:
                    relation=put_relation(self,c,scope,episode,identifier,RelationshipType.ABOUT,'about',
                                          (proof,object_proof),counts=counts)
                    self._context_membership(c,scope,episode,identifier,proof,object_proof,'referenced_objects',relation,counts)
                self._summary(c,scope,episode,topic,counts)

    def _project(self,c,scope,event_id,counts):
        event=_event_in_scope(c,scope,event_id)
        counts['events_examined']+=1
        if not source_allowed(scope,event):counts['rejected']+=1;return
        rows=c.execute('''SELECT m.* FROM memories m JOIN memory_sources s ON s.tenant_id=m.tenant_id
                        AND s.namespace=m.namespace AND s.memory_id=m.memory_id
                        WHERE m.tenant_id=? AND m.namespace=? AND s.event_id=? ORDER BY m.memory_id LIMIT 33''',
                        (scope.tenant_id,scope.namespace,event_id)).fetchall()
        if len(rows)>32:raise ObjectMapError('object_event_memory_limit')
        groups={}
        for row in rows:
            memory=self._read_memory(c,scope,row)
            if memory.metadata.get('principal_id',scope.principal_id)!=scope.principal_id:continue
            span=self.stored_span(c,scope,memory.memory_id,event_id)
            if span is None:counts['rejected']+=1;continue
            if event.content[span.start:span.end]!=span.quote:raise ObjectMapError('object_source_span_invalid')
            state=self._memory_state_in_connection(c,scope,memory.memory_id,TemporalQuery())
            if _source_retracted(c,scope,memory.memory_id,event_id) or event_id not in state.source_event_ids:continue
            groups.setdefault((span.start,span.end),[]).append((memory,span))
        for key,records in sorted(groups.items()):
            records.sort(key=lambda item:(item[0].metadata.get('p2_episode') is True,item[0].memory_id))
            memory,span=records[0]
            fact=self.registry(c,scope,ObjectType.FACT,['memory',memory.memory_id],reference=memory.memory_id,counts=counts)
            fact_proof=self.put_proof(c,scope,fact,memory,event,span,role='fact',label='Attributed claim',counts=counts)
            self._default(c,scope,fact,ObjectType.FACT,fact_proof,counts)
            source,source_proof=self._source(c,scope,event,memory,span,counts)
            self.membership(c,scope,fact,source,'evidence',proof_id=fact_proof,counts=counts)
            put_relation(self,c,scope,fact,source,RelationshipType.DERIVED_FROM,'derivation',
                         (fact_proof,source_proof),counts=counts)
            typed=[]
            for seed in seeds(event,span):
                value=self._typed(c,scope,event,memory,span,seed,fact,fact_proof,counts)
                if value:typed.append(value)
            episodes=[pair for pair in records if pair[0].metadata.get('p2_episode') is True]
            self._episodes(c,scope,event,episodes,fact,fact_proof,typed,counts)

    def _job(self,c,scope,job,event_id):
        if job is None:return
        if not isinstance(job,MindJob):raise ObjectMapError('object_job_context_invalid')
        try:current=MindJob.model_validate(job.model_dump())
        except (ValueError,TypeError):raise ObjectMapError('object_job_context_invalid') from None
        if (current.tenant_id,current.namespace)!=(scope.tenant_id,scope.namespace) or current.job_type is not JobType.EXTRACT_EVENT or current.target_type!='event' or current.target_id!=event_id:
            raise ObjectMapError('object_job_target_mismatch')
        row=c.execute('SELECT target_type,target_id FROM mind_jobs WHERE tenant_id=? AND namespace=? AND job_id=?',
                      (scope.tenant_id,scope.namespace,current.job_id)).fetchone()
        if row is None or tuple(row)!=('event',event_id):raise ObjectMapError('object_job_target_mismatch')
        self._guard_job(c,scope,current)

    @_translate_sqlite_errors
    def project_event(self,scope,event_id,*,job=None):
        scope,_=scoped(scope)
        event_id=ID.validate_python(event_id)
        counts=counters()
        with self._graph_transaction() as c:
            self.require_objects(c)
            self._job(c,scope,job,event_id)
            self._project(c,scope,event_id,counts)
            self._job(c,scope,job,event_id)
        return BuildResult(**counts)

    @_translate_sqlite_errors
    def build(self,scope,*,limit=100,cursor=None):
        scope,partition=scoped(scope)
        bounded(limit,1,1000)
        position=None
        if cursor is not None:
            try:
                values=json.loads(cursor)
                if not isinstance(values,list) or len(values)!=6 or tuple(values[:3])!=partition:raise ValueError()
                from pydantic import TypeAdapter
                from oomp.domain.models import UtcDateTime
                position=(_timestamp(TypeAdapter(UtcDateTime).validate_python(values[3])),
                          _timestamp(TypeAdapter(UtcDateTime).validate_python(values[4])),ID.validate_python(values[5]))
            except (ValueError,TypeError):raise ObjectMapError('object_build_cursor_invalid') from None
        counts=counters()
        with self._graph_transaction() as c:
            self.require_objects(c)
            sql='SELECT event_id,occurred_at,ingested_at FROM events WHERE tenant_id=? AND namespace=?'
            args=[scope.tenant_id,scope.namespace]
            if position is not None:sql+=' AND (occurred_at,ingested_at,event_id)>(?,?,?)';args.extend(position)
            rows=c.execute(sql+' ORDER BY occurred_at,ingested_at,event_id LIMIT ?',(*args,limit+1)).fetchall()
            for row in rows[:limit]:self._project(c,scope,row['event_id'],counts)
            continuation=json.dumps([*partition,*tuple(rows[limit-1])[-2:],rows[limit-1]['event_id']],separators=(',',':')) if len(rows)>limit else None
        return BuildResult(**counts,next_event_cursor=continuation,incomplete=len(rows)>limit)

    def rebuild(self,scope,*,limit=100,cursor=None):
        """Re-materialize only this scoped projection; retain identity/history rows."""
        return self.build(scope,limit=limit,cursor=cursor)

    @_translate_sqlite_errors
    def associate(self,scope,source_id,target_id,relationship_type,semantic_role,proof_ids,*,graph_edge_id=None):
        scope,_=scoped(scope)
        with self._graph_transaction() as c:
            self.require_objects(c)
            return put_relation(self,c,scope,source_id,target_id,relationship_type,semantic_role,proof_ids,graph_edge_id=graph_edge_id)

    @_translate_sqlite_errors
    def add_membership(self,scope,parent_id,child_id,role,*,proof_id=None,relation_id=None):
        scope,_=scoped(scope)
        with self._graph_transaction() as c:
            self.require_objects(c)
            return self.membership(c,scope,parent_id,child_id,role,proof_id=proof_id,relation_id=relation_id)
