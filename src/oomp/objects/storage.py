"""Transactional object primitives over original memory/source proof links."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json

from pydantic import TypeAdapter

from oomp.domain.enums import MemoryStatus
from oomp.domain.graph import TemporalQuery
from oomp.domain.memories import SourceSpan
from oomp.domain.models import Identifier
from oomp.storage.errors import SchemaUpgradeRequiredError
from oomp.storage.graph_store import _source_retracted, _valid_at
from oomp.storage.memory_store import _event_in_scope
from oomp.storage.migrations import user_version
from oomp.storage.sqlite import _authorized, _canonical_json, _timestamp
from oomp.understanding.rules import classify
from oomp.understanding.storage import UnderstandingStore
from .contracts import ObjectMapError, ObjectProof, ObjectType, STRUCTURAL_TYPES, VERSION
from .policy import episode_label, seeds, source_allowed

ID=TypeAdapter(Identifier)
MAX_OBJECTS=5000
MAX_PROOFS=128
MAX_WORK=10000


def scoped(scope):
    scope=_authorized(scope)
    return scope,(scope.tenant_id,scope.namespace,scope.principal_id)


def digest(value):
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def object_id(scope, kind, anchor):
    _,partition=scoped(scope)
    return "obj-"+digest([VERSION,*partition,str(kind),anchor])


class ReadBudget:
    def __init__(self, maximum=MAX_WORK):
        self.maximum=maximum
        self.used=0

    def charge(self, count=1):
        self.used+=count
        if self.used>self.maximum:
            raise ObjectMapError("object_map_work_limit")


class ObjectStorage(UnderstandingStore):
    @staticmethod
    def require_objects(c):
        if user_version(c)<6:
            raise SchemaUpgradeRequiredError("object_map_requires_explicit_schema_6_initialization")

    def registry(self,c,scope,kind,anchor,*,reference=None,structural_label=None,counts=None):
        scope,partition=scoped(scope)
        kind=ObjectType(kind)
        if (structural_label is not None)!=(kind in STRUCTURAL_TYPES):
            raise ObjectMapError("object_structural_label_invalid")
        if structural_label is not None and (not structural_label.strip() or len(structural_label)>160
                or any(ord(char)<32 for char in structural_label)):
            raise ObjectMapError("object_label_invalid")
        identifier=object_id(scope,kind,anchor)
        prior=c.execute("SELECT * FROM map_objects WHERE tenant_id=? AND namespace=? AND principal_id=? AND object_id=?",
                        (*partition,identifier)).fetchone()
        if prior is not None:
            if (prior['object_type'],prior['anchor_key'],prior['reference_id'],prior['structural_label'])!=(kind.value,digest(anchor),reference,structural_label):
                raise ObjectMapError("object_identity_conflict")
            return identifier
        count=c.execute("SELECT COUNT(*) FROM map_objects WHERE tenant_id=? AND namespace=? AND principal_id=?",partition).fetchone()[0]
        if count>=MAX_OBJECTS:raise ObjectMapError("object_partition_capacity")
        c.execute("""INSERT INTO map_objects (tenant_id,namespace,principal_id,object_id,object_type,
                  anchor_key,reference_id,structural_label,recorded_at,creation_version)
                  VALUES (?,?,?,?,?,?,?,?,oomp_recorded_at(),?)""",
                  (*partition,identifier,kind.value,digest(anchor),reference,structural_label,VERSION))
        if counts is not None:counts['objects_created']+=1
        return identifier

    def raw_object(self,c,scope,identifier):
        _,partition=scoped(scope)
        return c.execute("SELECT * FROM map_objects WHERE tenant_id=? AND namespace=? AND principal_id=? AND object_id=?",
                         (*partition,ID.validate_python(identifier))).fetchone()

    def stored_span(self,c,scope,memory_id,event_id):
        row=c.execute("""SELECT source_span_json FROM memory_sources
                     WHERE tenant_id=? AND namespace=? AND memory_id=? AND event_id=?""",
                     (scope.tenant_id,scope.namespace,memory_id,event_id)).fetchone()
        if row is None or row['source_span_json'] is None:return None
        try:return SourceSpan.model_validate_json(row['source_span_json'])
        except (ValueError,TypeError):raise ObjectMapError("object_source_span_invalid") from None

    def validate_proof(self,c,scope,row,query=None,*,budget=None,include_withdrawn=False,cache=None):
        """Independent read/commit check; stored projection labels have no authority."""
        query=query or TemporalQuery()
        if budget is not None:budget.charge()
        if query.known_at is not None and row['recorded_at']>_timestamp(query.known_at):return None
        obj=self.raw_object(c,scope,row['object_id'])
        if obj is None:raise ObjectMapError("object_proof_orphan")
        memory_row=c.execute("SELECT * FROM memories WHERE tenant_id=? AND namespace=? AND memory_id=?",
                             (scope.tenant_id,scope.namespace,row['memory_id'])).fetchone()
        if memory_row is None:return None
        cache=cache if cache is not None else {}
        memories=cache.setdefault('memories',{})
        if row['memory_id'] not in memories:
            memories[row['memory_id']]=self._read_memory(c,scope,memory_row)
            if budget is not None:budget.charge(len(memories[row['memory_id']].source_event_ids))
        memory=memories[row['memory_id']]
        if memory.metadata.get('principal_id',scope.principal_id)!=scope.principal_id:return None
        event=_event_in_scope(c,scope,row['event_id'])
        if not source_allowed(scope,event):return None
        span=self.stored_span(c,scope,memory.memory_id,event.event_id)
        if span is None or (span.start,span.end)!=(row['span_start'],row['span_end']) or event.content[span.start:span.end]!=span.quote:
            raise ObjectMapError("object_source_span_invalid")
        states=cache.setdefault('states',{})
        state_key=(memory.memory_id,query.known_at,query.valid_at)
        if state_key not in states:states[state_key]=self._memory_state_in_connection(c,scope,memory.memory_id,query)
        state=states[state_key]
        withdrawn=_source_retracted(c,scope,memory.memory_id,event.event_id,query.known_at)
        if not include_withdrawn and (withdrawn or event.event_id not in state.source_event_ids or state.effective_status not in {MemoryStatus.ACTIVE,MemoryStatus.SUPERSEDED}):return None
        if query.known_at is not None and state.known is not True:return None
        if _valid_at(memory.valid_from,memory.valid_until,query.valid_at) is False:return None
        fields=classify(event,span)
        if fields['assertion_kind']!=row['assertion_kind']:
            raise ObjectMapError("object_assertion_invalid")
        kind=ObjectType(obj['object_type'])
        if (kind is ObjectType.FACT and obj['reference_id']!=memory.memory_id or
                kind is ObjectType.SOURCE_EVENT and obj['reference_id']!=event.event_id):
            raise ObjectMapError('object_reference_not_grounded')
        role=row['semantic_role']
        fixed={
            'fact':(ObjectType.FACT,'Attributed claim'),
            'source':(ObjectType.SOURCE_EVENT,'Original source'),
            'episode':(ObjectType.EPISODE,episode_label(span.quote)),
        }
        if role=='summary_revision':
            revision=c.execute("SELECT * FROM mind_summary_revisions WHERE tenant_id=? AND namespace=? AND revision_id=?",
                               (scope.tenant_id,scope.namespace,obj['reference_id'])).fetchone()
            if revision is None:return None
            cutoff=_timestamp(query.known_at) if query.known_at else None
            if cutoff is not None and revision['recorded_at']>cutoff:return None
            if revision['retired_at'] is not None and (cutoff is None or revision['retired_at']<=cutoff):return None
            # Check the actual existing summary/source manifest, not its label.
            self._read_summary(c,scope,revision)
            from oomp.understanding.episodes import EPISODE_POLICY, episode_snapshot
            if revision['policy_version']!=EPISODE_POLICY:raise ObjectMapError('object_summary_policy_invalid')
            _,content,fingerprint=episode_snapshot(self,c,scope,revision['topic_id'],known_at=query.known_at)
            if revision['source_fingerprint']!=fingerprint or revision['content']!=content:
                raise ObjectMapError('object_summary_source_changed')
            fixed[role]=(ObjectType.SUMMARY_REVISION,'Summary revision '+str(revision['revision_number']))
        if role=='episode' and (memory.metadata.get('p2_episode') is not True or c.execute(
                'SELECT 1 FROM topic_memberships WHERE tenant_id=? AND namespace=? AND topic_id=? AND memory_id=?',
                (scope.tenant_id,scope.namespace,obj['reference_id'],memory.memory_id)).fetchone() is None):
            raise ObjectMapError('object_episode_reference_invalid')
        if role in fixed:
            if (kind,row['label'])!=fixed[role] or row['basis']!='derived_navigation' or row['label_start'] is not None:
                raise ObjectMapError("object_derived_label_invalid")
        else:
            eligible=[seed for seed in seeds(event,span) if
                (seed.kind,seed.role,seed.label,seed.label_start,seed.label_end)==
                (kind,role,row['label'],row['label_start'],row['label_end'])]
            if not eligible or row['basis']!=('source_span' if eligible[0].label_start is not None else 'derived_navigation'):
                raise ObjectMapError("object_label_not_source_grounded")
        recording=c.execute("""SELECT recorded_at FROM memory_source_recordings
                             WHERE tenant_id=? AND namespace=? AND memory_id=? AND event_id=?""",
                             (scope.tenant_id,scope.namespace,memory.memory_id,event.event_id)).fetchone()
        proof=ObjectProof(proof_id=row['proof_id'],memory_id=memory.memory_id,event_id=event.event_id,
            source_span=span,source_reference=event.source_reference,occurred_at=event.occurred_at,
            recorded_at=row['recorded_at'],known_at=recording[0] if recording else None,
            valid_from=memory.valid_from,valid_until=memory.valid_until,
            assertion_kind=fields['assertion_kind'],semantic_role=role,claimed_by=event.source_type.value,basis=row['basis'],sensitivity=fields['sensitivity'])
        return proof,row['label'],withdrawn

    def put_proof(self,c,scope,identifier,memory,event,span,*,role,label,label_start=None,label_end=None,counts=None):
        _,partition=scoped(scope)
        identifier=ID.validate_python(identifier)
        proof_id='objproof-'+digest([identifier,memory.memory_id,event.event_id,span.start,span.end,role,label_start,label_end])
        fields=classify(event,span)
        data=dict(proof_id=proof_id,object_id=identifier,memory_id=memory.memory_id,event_id=event.event_id,
            span_start=span.start,span_end=span.end,label=label,label_start=label_start,label_end=label_end,
            semantic_role=role,assertion_kind=fields['assertion_kind'],basis='source_span' if label_start is not None else 'derived_navigation',
            recorded_at=c.execute('SELECT oomp_recorded_at()').fetchone()[0])
        if self.validate_proof(c,scope,data) is None:raise ObjectMapError('object_proof_not_endorsed')
        prior=c.execute("SELECT * FROM map_proofs WHERE tenant_id=? AND namespace=? AND principal_id=? AND proof_id=?",
                        (*partition,proof_id)).fetchone()
        if prior is not None:
            if any(prior[key]!=value for key,value in data.items() if key!='recorded_at'):
                raise ObjectMapError('object_proof_conflict')
            return proof_id
        count=c.execute("SELECT COUNT(*) FROM map_proofs WHERE tenant_id=? AND namespace=? AND principal_id=? AND object_id=?",
                        (*partition,identifier)).fetchone()[0]
        if count>=MAX_PROOFS:raise ObjectMapError('object_proof_limit')
        names=tuple(data)
        c.execute('INSERT INTO map_proofs (tenant_id,namespace,principal_id,'+','.join(names)+') VALUES ('+
                  ','.join('?' for _ in range(3+len(names)))+')',(*partition,*(data[name] for name in names)))
        if counts is not None:counts['proofs_added']+=1
        return proof_id

    def membership(self,c,scope,parent,child,role,*,proof_id=None,relation_id=None,counts=None):
        _,partition=scoped(scope)
        first,last=self.raw_object(c,scope,parent),self.raw_object(c,scope,child)
        if first is None or last is None:raise ObjectMapError('membership_scope_or_endpoint_invalid')
        if parent==child or last['object_type']=='owner':raise ObjectMapError('hierarchy_cycle')
        source,target=ObjectType(first['object_type']),ObjectType(last['object_type'])
        allowed=(
            role=='domain' and source is ObjectType.OWNER and target is ObjectType.DOMAIN or
            role=='session' and source is ObjectType.OWNER and target is ObjectType.SESSION or
            role=='topic' and source in {ObjectType.DOMAIN,ObjectType.TOPIC} and target is ObjectType.TOPIC or
            role=='object' and source is ObjectType.TOPIC and target not in STRUCTURAL_TYPES or
            role=='fact' and source not in STRUCTURAL_TYPES|{ObjectType.FACT,ObjectType.SOURCE_EVENT} and target is ObjectType.FACT or
            role=='evidence' and source in {ObjectType.FACT,ObjectType.EPISODE,ObjectType.SUMMARY_REVISION} and target is ObjectType.SOURCE_EVENT or
            role=='related_plans' and source in {ObjectType.PLACE,ObjectType.PROJECT} and target is ObjectType.TOPIC or
            role=='referenced_objects' and source is ObjectType.EPISODE and target is ObjectType.TOPIC or
            role=='episode' and source is ObjectType.SESSION and target is ObjectType.EPISODE or
            role=='revision' and source is ObjectType.EPISODE and target is ObjectType.SUMMARY_REVISION
        )
        if not allowed:raise ObjectMapError('membership_type_invalid')
        if role not in {'domain','topic','session'} and proof_id is None:
            raise ObjectMapError('membership_proof_required')
        if proof_id is not None:
            proof=c.execute('SELECT * FROM map_proofs WHERE tenant_id=? AND namespace=? AND principal_id=? AND proof_id=?',
                            (*partition,proof_id)).fetchone()
            validated=self.validate_proof(c,scope,proof) if proof is not None else None
            if validated is None:raise ObjectMapError('membership_proof_invalid')
            if role=='object' and proof['object_id']!=child:
                raise ObjectMapError('membership_proof_endpoint_invalid')
            if role=='fact' and (proof['object_id'] not in {parent,child} or proof['memory_id']!=last['reference_id']):
                raise ObjectMapError('membership_fact_proof_invalid')
            if role=='evidence' and (proof['object_id']!=parent or proof['event_id']!=last['reference_id']):
                raise ObjectMapError('membership_source_proof_invalid')
            if role in {'related_plans','referenced_objects','revision','episode'} and proof['object_id'] not in {parent,child}:
                raise ObjectMapError('membership_proof_endpoint_invalid')
            if role=='episode' and ('session-'+digest(validated[0].source_reference.session_id))!=first['reference_id']:
                raise ObjectMapError('membership_session_invalid')
            if role in {'related_plans','referenced_objects'} and last['reference_id']!=parent:
                raise ObjectMapError('membership_container_invalid')
            if role=='revision':
                revision=c.execute('SELECT topic_id FROM mind_summary_revisions WHERE tenant_id=? AND namespace=? AND revision_id=?',
                                   (scope.tenant_id,scope.namespace,last['reference_id'])).fetchone()
                if revision is None or revision[0]!=first['reference_id']:raise ObjectMapError('membership_episode_revision_invalid')
        if role=='object' and first['structural_label'] in {'Related plans','Referenced objects'}:
            relation=c.execute('SELECT source_id,target_id FROM map_relations WHERE tenant_id=? AND namespace=? AND principal_id=? AND relation_id=?',
                               (*partition,relation_id)).fetchone() if relation_id else None
            if relation is None or tuple(relation)!=(first['reference_id'],child):
                raise ObjectMapError('membership_context_relation_required')
        if relation_id is not None and c.execute('SELECT 1 FROM map_relations WHERE tenant_id=? AND namespace=? AND principal_id=? AND relation_id=?',
                                                (*partition,relation_id)).fetchone() is None:
            raise ObjectMapError('membership_relation_invalid')
        if role=='fact' and proof['object_id']==child:
            relation=c.execute('SELECT source_id,target_id FROM map_relations WHERE tenant_id=? AND namespace=? AND principal_id=? AND relation_id=?',
                               (*partition,relation_id)).fetchone() if relation_id else None
            if relation is None or tuple(relation)!=(parent,child):
                raise ObjectMapError('membership_context_relation_required')
        if relation_id is not None:
            from .queries import ReadContext
            from .relations import read_relation
            if read_relation(self,c,scope,relation_id,ReadContext()) is None:
                raise ObjectMapError('membership_relation_not_endorsed')
        prior=c.execute('SELECT role FROM map_memberships WHERE tenant_id=? AND namespace=? AND principal_id=? AND parent_id=? AND child_id=?',
                        (*partition,parent,child)).fetchone()
        if prior is not None:
            if prior['role']!=role:raise ObjectMapError('membership_role_conflict')
            self._membership_support(c,partition,parent,child,proof_id,relation_id)
            return False
        visited,queue,work=set(),[child],0
        while queue:
            node=queue.pop()
            if node==parent:raise ObjectMapError('hierarchy_cycle')
            if node in visited:continue
            visited.add(node)
            rows=c.execute('SELECT child_id FROM map_memberships WHERE tenant_id=? AND namespace=? AND principal_id=? AND parent_id=? LIMIT ?',
                           (*partition,node,MAX_WORK-work+1)).fetchall()
            work+=len(rows)+1
            if work>MAX_WORK:raise ObjectMapError('hierarchy_cycle_check_limit')
            queue.extend(row[0] for row in rows)
        c.execute('''INSERT INTO map_memberships
                  (tenant_id,namespace,principal_id,parent_id,child_id,role,recorded_at)
                  VALUES (?,?,?,?,?,?,oomp_recorded_at())''',(*partition,parent,child,role))
        self._membership_support(c,partition,parent,child,proof_id,relation_id)
        if counts is not None:counts['memberships_added']+=1
        return True

    @staticmethod
    def _membership_support(c,partition,parent,child,proof_id,relation_id):
        if proof_id is None:return
        support_id='objsupport-'+digest([parent,child,proof_id,relation_id])
        c.execute('''INSERT OR IGNORE INTO map_membership_supports
                  (tenant_id,namespace,principal_id,support_id,parent_id,child_id,proof_id,relation_id,recorded_at)
                  VALUES (?,?,?,?,?,?,?,?,oomp_recorded_at())''',
                  (*partition,support_id,parent,child,proof_id,relation_id))
