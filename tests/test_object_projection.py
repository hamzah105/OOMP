"""Frozen fictional relocation through actual rules-only Mind jobs and SQLite."""
from contextlib import closing
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import sqlite3

from oomp.domain.graph import TemporalQuery
from oomp.domain.models import AuthorizedScope,MemoryEvent,SourceReference
from oomp.mind.worker import MindWorker
from oomp.objects.contracts import ObjectType
from oomp.objects.service import ObjectMap
from oomp.storage.memory_store import SQLiteMemoryStore
from oomp.storage.sqlite import SQLiteEventStore
from oomp.understanding.contracts import ExtractionConfiguration

FIXTURE=Path(__file__).resolve().parents[1]/'examples/fixtures/object_relocation_v1.json'


def fictional(path):
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'))
    assert fixture['synthetic'] and fixture['version']=='object-relocation.v1'
    scope=AuthorizedScope(tenant_id=fixture['tenant'],namespace=fixture['namespace'],principal_id=fixture['principal'])
    when=datetime.fromisoformat(fixture['base_time'])
    events=[]
    for index,turn in enumerate(fixture['turns']):
        timestamp=when+timedelta(minutes=index)
        events.append(MemoryEvent(event_id=turn['id'],tenant_id=scope.tenant_id,namespace=scope.namespace,
            event_type=turn['role']+'_message',source_type=turn['role'],content=turn['text'],
            source_reference=SourceReference(source_system='public-synthetic-p3',external_event_id=turn['id'],
                timestamp=timestamp,session_id=fixture['session'],turn_id='turn-'+str(index)),
            occurred_at=timestamp,ingested_at=timestamp,metadata={'ingested_by':scope.principal_id}))
    source=SQLiteEventStore(path);source.initialize()
    worker=MindWorker(path,scope,extraction_configuration=ExtractionConfiguration(mode='rules'))
    return scope,source,worker,tuple(events)


def process(source,worker,scope,events):
    for event in events:source.append(scope,event)
    run=worker.run_once(max_jobs=100)
    assert not any((run.failed,run.retried,run.lost_lease)) and run.completed>=len(events)
    assert worker.handlers.understanding.provider is None
    return run


def paths(tree,target):
    children={}
    for edge in tree.memberships:children.setdefault(edge.parent_id,[]).append(edge.child_id)
    result=[]
    queue=[(tree.root_id,)]
    while queue:
        path=queue.pop(0)
        if path[-1]==target:result.append(path);continue
        assert len(path)<=11
        queue.extend(path+(child,) for child in children.get(path[-1],()) if child not in path)
    return result


def test_three_paths_resolve_one_plan_with_real_original_source_proofs(tmp_path):
    path=tmp_path/'relocation.sqlite3'
    scope,source,worker,events=fictional(path)
    process(source,worker,scope,events[:10])
    before=SQLiteMemoryStore(path).count_memories(scope)
    with closing(sqlite3.connect(path)) as c:
        old_proofs=c.execute('SELECT * FROM memory_sources ORDER BY memory_id,event_id').fetchall()
    graph=ObjectMap(path)
    result=graph.build(scope,limit=100)
    assert not result.incomplete and result.objects_created>0
    plan,=graph.list_objects(scope,object_type=ObjectType.PLAN).objects
    assert plan.status=='tentative' and plan.canonical_label=='Potential relocation'
    assert {p.event_id for p in plan.source_proofs}=={'p3-plan'}
    tree=graph.tree(scope,max_depth=10,max_nodes=300,max_edges=1000,max_work=10000)
    assert not tree.truncated
    by_id={node.object.object_id:node.object for node in tree.nodes}
    labels=[[by_id[node].canonical_label for node in route] for route in paths(tree,plan.object_id)]
    assert any('Plans' in route for route in labels)
    assert any('Places' in route and 'Islamabad' in route and 'Related plans' in route for route in labels)
    assert any('Episodes' in route and 'City comparison' in route and 'Referenced objects' in route for route in labels)
    assert SQLiteMemoryStore(path).count_memories(scope)==before
    with closing(sqlite3.connect(path)) as c:
        assert c.execute('SELECT * FROM memory_sources ORDER BY memory_id,event_id').fetchall()==old_proofs
        assert c.execute("SELECT COUNT(*) FROM mind_maintenance_audit WHERE operation_type='mind2.model_calls' AND affected_count>0").fetchone()[0]==0
    for event in events[:10]:assert source.get(scope,event.event_id)==event
    for obj in graph.list_objects(scope,limit=500).objects:
        for proof in obj.source_proofs:
            original=source.get(scope,proof.event_id)
            assert original.content[proof.source_span.start:proof.source_span.end]==proof.source_span.quote
            if obj.object_type in {ObjectType.PLAN,ObjectType.PLACE,ObjectType.PROJECT,ObjectType.PERSON,ObjectType.CONCEPT}:
                assert proof.event_id not in {'p3-assistant','p3-hypothetical','p3-quoted','p3-question','p3-sensitive'}


def test_correction_history_and_explicit_project_rename_preserve_ids(tmp_path):
    path=tmp_path/'history.sqlite3'
    scope,source,worker,events=fictional(path)
    process(source,worker,scope,events[:10])
    graph=ObjectMap(path);graph.build(scope,limit=100)
    initial,=graph.list_objects(scope,object_type='plan').objects
    project,=graph.list_objects(scope,object_type='project').objects
    earlier=datetime.now(timezone.utc)
    process(source,worker,scope,events[10:])
    graph.build(scope,limit=100)
    current,=graph.list_objects(scope,object_type='plan').objects
    renamed,=graph.list_objects(scope,object_type='project').objects
    assert current.object_id==initial.object_id and current.status=='correction_pending'
    assert current.canonical_label=='not to move this year'
    assert {proof.event_id for proof in current.source_proofs}=={'p3-plan','p3-correction'}
    old=graph.get_object(scope,initial.object_id,query=TemporalQuery(known_at=earlier))
    assert old.canonical_label=='Potential relocation' and old.status=='tentative'
    assert renamed.object_id==project.object_id and renamed.canonical_label=='Aspen' and 'Cedar' in renamed.aliases
    assert graph.get_object(scope,project.object_id,query=TemporalQuery(known_at=earlier)).canonical_label=='Cedar'
    ids={obj.object_id for obj in graph.list_objects(scope,limit=500).objects}
    replay=graph.rebuild(scope,limit=100)
    assert replay.objects_created==replay.proofs_added==replay.relations_added==replay.memberships_added==0
    assert {obj.object_id for obj in ObjectMap(path).list_objects(scope,limit=500).objects}==ids
    assert all(source.get(scope,event.event_id)==event for event in events)
