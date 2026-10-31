"""Source-backed object primitives and rollback; no model or private data."""
from contextlib import closing
from datetime import datetime,timedelta,timezone
import sqlite3

import pytest

from oomp.domain.models import AuthorizedScope,MemoryEvent,SourceReference
from oomp.objects.contracts import ObjectMapError,ObjectType
from oomp.objects.storage import ObjectStorage
from oomp.storage.memory_store import SQLiteMemoryStore
from oomp.storage.mind_store import SQLiteMindStore,LostLeaseError
from oomp.storage.sqlite import SQLiteEventStore
from oomp.mind.contracts import JobType
from oomp.understanding.engine import UnderstandingEngine

NOW=datetime(2026,1,1,tzinfo=timezone.utc)
SCOPE=AuthorizedScope(tenant_id='p3',namespace='synthetic',principal_id='owner')


def setup(path,text='My test alias is Maple Finch.',*,scope=SCOPE,event_id='e1'):
    event=MemoryEvent(event_id=event_id,tenant_id=scope.tenant_id,namespace=scope.namespace,
        event_type='user_message',source_type='user',content=text,
        source_reference=SourceReference(source_system='public-synthetic',external_event_id=event_id,timestamp=NOW,session_id='s1'),
        occurred_at=NOW,ingested_at=NOW,metadata={'ingested_by':scope.principal_id})
    source=SQLiteEventStore(path)
    source.initialize();source.append(scope,event)
    UnderstandingEngine(path).process_event(scope,event_id)
    memories=SQLiteMemoryStore(path).list_memories(scope).memories
    memory=next(m for m in memories if m.metadata.get('p2_episode') is not True)
    return ObjectStorage(path),event,memory


def rooted(c,store,scope=SCOPE):
    owner=store.registry(c,scope,ObjectType.OWNER,'root',structural_label='Owner')
    domain=store.registry(c,scope,ObjectType.DOMAIN,'profile',structural_label='Profile')
    topic=store.registry(c,scope,ObjectType.TOPIC,'claimed-aliases',structural_label='Claimed aliases')
    store.membership(c,scope,owner,domain,'domain')
    store.membership(c,scope,domain,topic,'topic')
    return owner,domain,topic


def put_alias(c,store,event,memory,scope=SCOPE):
    _,_,topic=rooted(c,store,scope)
    identifier=store.registry(c,scope,ObjectType.PERSON,['memory',memory.memory_id],reference=memory.memory_id)
    span=store.stored_span(c,scope,memory.memory_id,event.event_id)
    start=event.content.index('Maple Finch')
    proof=store.put_proof(c,scope,identifier,memory,event,span,role='claimed_alias',label='Maple Finch',label_start=start,label_end=start+11)
    store.membership(c,scope,topic,identifier,'object',proof_id=proof)
    return identifier,proof


def test_object_proof_persists_exact_original_span_and_unverified_alias(tmp_path):
    path=tmp_path/'proof.sqlite3'
    store,event,memory=setup(path)
    with store._graph_transaction() as c:
        store.require_objects(c)
        identifier,proof=put_alias(c,store,event,memory)
    with store._graph_read() as c:
        row=c.execute('SELECT * FROM map_proofs WHERE proof_id=?',(proof,)).fetchone()
        actual,label,withdrawn=store.validate_proof(c,SCOPE,row)
        assert actual.event_id==event.event_id and actual.memory_id==memory.memory_id
        assert actual.source_span.quote==event.content[actual.source_span.start:actual.source_span.end]
        assert label=='Maple Finch' and not actual.verified and not withdrawn
        assert store.raw_object(c,SCOPE,identifier)['reference_id']==memory.memory_id
        assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert SQLiteEventStore(path).get(SCOPE,event.event_id)==event


@pytest.mark.parametrize('change',[
    {'label':'Invented name'}, {'label_start':0}, {'role':'authenticated_name'},
    {'label_end':999},
])
def test_forged_object_labels_and_predicates_roll_back_atomically(tmp_path,change):
    path=tmp_path/'forged.sqlite3'
    store,event,memory=setup(path)
    with pytest.raises(ObjectMapError),store._graph_transaction() as c:
        identifier=store.registry(c,SCOPE,ObjectType.PERSON,'claim',reference=memory.memory_id)
        span=store.stored_span(c,SCOPE,memory.memory_id,event.event_id)
        data={'role':'claimed_alias','label':'Maple Finch','label_start':17,'label_end':28}
        data.update(change)
        store.put_proof(c,SCOPE,identifier,memory,event,span,**data)
    with closing(sqlite3.connect(path)) as c:assert c.execute('SELECT COUNT(*) FROM map_objects').fetchone()[0]==0


def test_same_namespace_different_principal_cannot_borrow_object_or_source(tmp_path):
    path=tmp_path/'principal.sqlite3'
    store,event,memory=setup(path)
    with store._graph_transaction() as c:identifier,_=put_alias(c,store,event,memory)
    other=SCOPE.model_copy(update={'principal_id':'other'})
    with store._graph_read() as c:assert store.raw_object(c,other,identifier) is None
    with pytest.raises(ObjectMapError),store._graph_transaction() as c:
        other_id=store.registry(c,other,ObjectType.PERSON,'claim')
        span=store.stored_span(c,SCOPE,memory.memory_id,event.event_id)
        store.put_proof(c,other,other_id,memory,event,span,role='claimed_alias',label='Maple Finch',label_start=17,label_end=28)


def test_hierarchy_cycle_foreign_endpoint_and_invalid_membership_rejected(tmp_path):
    store,event,memory=setup(tmp_path/'cycles.sqlite3')
    with store._graph_transaction() as c:
        root,domain,topic=rooted(c,store)
        second=store.registry(c,SCOPE,ObjectType.TOPIC,'second',structural_label='Second')
        store.membership(c,SCOPE,topic,second,'topic')
        with pytest.raises(ObjectMapError,match='hierarchy_cycle'):
            store.membership(c,SCOPE,second,topic,'topic')
        with pytest.raises(ObjectMapError):store.membership(c,SCOPE,topic,root,'topic')
        with pytest.raises(ObjectMapError):store.membership(c,SCOPE,topic,'missing','object',proof_id='missing')
        with pytest.raises(ObjectMapError):store.membership(c,SCOPE,root,topic,'domain')


def test_expired_job_fence_rolls_back_projection_effects(tmp_path):
    path=tmp_path/'fencing.sqlite3'
    store,event,memory=setup(path)
    clock=[NOW]
    jobs=SQLiteMindStore(path,clock=lambda:clock[0])
    jobs.enqueue(SCOPE,JobType.EXTRACT_EVENT,'event',event.event_id,idempotency_key='p3-test',policy_version='extract.v1')
    job=jobs.claim(SCOPE,'owner-worker',lease_seconds=10)
    store=ObjectStorage(path,clock=lambda:clock[0])
    with pytest.raises(LostLeaseError),store._graph_transaction() as c:
        store._guard_job(c,SCOPE,job)
        put_alias(c,store,event,memory)
        clock[0]+=timedelta(seconds=11)
        store._guard_job(c,SCOPE,job)
    with closing(sqlite3.connect(path)) as c:assert c.execute('SELECT COUNT(*) FROM map_objects').fetchone()[0]==0
