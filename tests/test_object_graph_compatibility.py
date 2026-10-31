"""Existing graph-backed projections cannot obstruct approved source erasure."""
from contextlib import closing
import json
import sqlite3

import pytest

from oomp.domain.enums import RelationshipType
from oomp.graph import GraphService
from oomp.objects import ObjectMap,ObjectMapError
from oomp.objects.cli import emit
from oomp.storage.privacy_store import SQLitePrivacyStore,ErasureBlockedError
from oomp.storage.memory_store import SQLiteMemoryStore
from oomp.storage.sqlite import SQLiteEventStore
from test_object_storage import SCOPE,setup


def linked(path):
    _,first,one=setup(path,'My test alias is Maple Finch.')
    setup(path,'I plan to build a paper model.',event_id='e2')
    two=next(memory for memory in SQLiteMemoryStore(path).list_memories(SCOPE).memories
             if 'e2' in memory.source_event_ids and memory.metadata.get('p2_episode') is not True)
    graph=ObjectMap(path);graph.build(SCOPE)
    facts=graph.list_objects(SCOPE,object_type='fact').objects
    left=next(obj for obj in facts if obj.reference_id==one.memory_id)
    right=next(obj for obj in facts if obj.reference_id==two.memory_id)
    edge=GraphService(path).link(SCOPE,one.memory_id,two.memory_id,'RELATED_TO',(first.event_id,))
    relation=graph.associate(SCOPE,left.object_id,right.object_id,RelationshipType.RELATED_TO,'existing_graph',
        (left.source_proofs[0].proof_id,right.source_proofs[0].proof_id),graph_edge_id=edge.edge.edge_id)
    return graph,first,left,right,relation


def test_existing_graph_erasure_refusal_remains_enforced_after_projection(tmp_path):
    path=tmp_path/'synthetic-graph-erasure.sqlite3'
    graph,event,left,right,relation=linked(path)
    assert any(row.relation_id==relation for row in graph.relations(SCOPE,left.object_id)[0])
    privacy=SQLitePrivacyStore(path)
    plan=privacy.erase_plan(SCOPE,event.event_id)
    assert plan.blocked_reason=='graph_dependency'
    with pytest.raises(ErasureBlockedError):
        privacy.erase_confirm(SCOPE,event.event_id,plan.plan_digest,confirm=True)
    assert graph.get_object(SCOPE,left.object_id) is not None
    assert graph.get_object(SCOPE,right.object_id) is not None
    assert SQLiteEventStore(path).get(SCOPE,event.event_id)==event
    with closing(sqlite3.connect(path)) as c:
        assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert c.execute('SELECT 1 FROM map_relations WHERE relation_id=?',(relation,)).fetchone() is not None


def test_existing_graph_interval_cannot_be_fabricated(tmp_path):
    path=tmp_path/'synthetic-interval.sqlite3'
    graph,_,left,_,relation=linked(path)
    with closing(sqlite3.connect(path)) as c,c:
        c.execute("UPDATE map_relations SET valid_from='2026-01-01T00:00:00.000000Z' WHERE relation_id=?",(relation,))
    with pytest.raises(ObjectMapError,match='validity_not_grounded'):graph.relations(SCOPE,left.object_id)


def test_unicode_cli_output_is_lossless_json_without_terminal_escapes(capsys):
    emit({'label':'زارا 東京'},True)
    output=capsys.readouterr().out
    assert output.isascii() and '\x1b' not in output and json.loads(output)['label']=='زارا 東京'


def test_repeated_source_ingestion_and_map_replay_do_not_duplicate_proofs(tmp_path):
    path=tmp_path/'synthetic-repeat.sqlite3'
    _,event,_=setup(path)
    graph=ObjectMap(path);graph.build(SCOPE)
    initial=graph.list_objects(SCOPE,limit=500).model_dump(mode='json')
    original=SQLiteEventStore(path).append(SCOPE,event)
    assert original==event and SQLiteEventStore(path).count_events(SCOPE)==1
    replay=graph.rebuild(SCOPE)
    assert replay.objects_created==replay.proofs_added==replay.memberships_added==replay.relations_added==0
    assert graph.list_objects(SCOPE,limit=500).model_dump(mode='json')==initial


@pytest.mark.parametrize('kind',['fact','source_event'])
def test_source_and_fact_registry_references_are_independently_grounded(tmp_path,kind):
    path=tmp_path/'synthetic-reference.sqlite3'
    setup(path)
    graph=ObjectMap(path);graph.build(SCOPE)
    obj=graph.list_objects(SCOPE,object_type=kind).objects[0]
    with closing(sqlite3.connect(path)) as c,c:
        c.execute("UPDATE map_objects SET reference_id='forged-reference' WHERE object_id=?",(obj.object_id,))
    with pytest.raises(ObjectMapError,match='reference_not_grounded'):graph.get_object(SCOPE,obj.object_id)
