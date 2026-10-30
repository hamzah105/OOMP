"""Existing erasure API, fresh pytest-owned synthetic storage only.

These tests do not change privileged deletion behavior or open a user profile.
"""
from contextlib import closing
import sqlite3

import pytest

from oomp.objects.contracts import ObjectType
from oomp.objects.service import ObjectMap
from oomp.storage.privacy_store import SQLitePrivacyStore,ErasureBlockedError
from oomp.storage.sqlite import SQLiteEventStore
from test_object_storage import SCOPE,setup


def project(path,*,scope=SCOPE,text='My test alias is Maple Finch.',event_id='e1'):
    assert path.parent.is_dir() and not path.is_dir()
    _,event,memory=setup(path,text=text,scope=scope,event_id=event_id)
    graph=ObjectMap(path);graph.build(scope,limit=100)
    return graph,event,memory


def test_existing_confirmed_erasure_removes_labels_and_hides_unsupported_anchors(tmp_path):
    path=tmp_path/'synthetic-erasure.sqlite3'
    graph,event,_=project(path)
    alias,=graph.list_objects(SCOPE,object_type='person').objects
    privacy=SQLitePrivacyStore(path)
    plan=privacy.erase_plan(SCOPE,event.event_id)
    assert plan.blocked_reason is None
    privacy.erase_confirm(SCOPE,event.event_id,plan.plan_digest,confirm=True)
    assert graph.get_object(SCOPE,alias.object_id) is None
    assert not graph.list_objects(SCOPE,object_type='person').objects
    assert all(node.object.object_type not in {ObjectType.PERSON,ObjectType.EPISODE,ObjectType.SUMMARY_REVISION,ObjectType.SESSION}
               for node in graph.tree(SCOPE).nodes)
    with closing(sqlite3.connect(path)) as c:
        assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
        for table, in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'map_%'"):
            rows=c.execute('SELECT * FROM '+table).fetchall()
            assert all('Maple Finch' not in str(row) for row in rows)
        # Opaque anchors are allowed; no source text/label is stored in them.
        assert c.execute('SELECT COUNT(*) FROM map_proofs').fetchone()[0]==0
    assert SQLiteEventStore(path).get(SCOPE,event.event_id) is None


def test_erasure_preserves_independently_supported_object_identity(tmp_path):
    path=tmp_path/'synthetic-independent.sqlite3'
    text='I plan to build a paper model.'
    graph,first,_=project(path,text=text)
    _,second,_=project(path,text=text,event_id='e2')
    original,=graph.list_objects(SCOPE,object_type='plan').objects
    assert {p.event_id for p in original.source_proofs}=={'e1','e2'}
    privacy=SQLitePrivacyStore(path)
    plan=privacy.erase_plan(SCOPE,first.event_id)
    assert plan.blocked_reason is None
    privacy.erase_confirm(SCOPE,first.event_id,plan.plan_digest,confirm=True)
    surviving=graph.get_object(SCOPE,original.object_id)
    assert surviving is not None and surviving.canonical_label=='build a paper model'
    assert [proof.event_id for proof in surviving.source_proofs]==['e2']
    assert any(node.object.object_id==original.object_id for node in graph.tree(SCOPE).nodes)
    assert SQLiteEventStore(path).get(SCOPE,second.event_id)==second


def test_existing_shared_entity_erasure_refusal_is_preserved(tmp_path):
    path=tmp_path/'synthetic-entity-refusal.sqlite3'
    text='I am developing a project called Cedar.'
    graph,first,_=project(path,text=text)
    project(path,text=text,event_id='e2')
    original,=graph.list_objects(SCOPE,object_type='project').objects
    privacy=SQLitePrivacyStore(path)
    plan=privacy.erase_plan(SCOPE,first.event_id)
    assert plan.blocked_reason=='unsupported_shared_proof'
    with pytest.raises(ErasureBlockedError):
        privacy.erase_confirm(SCOPE,first.event_id,plan.plan_digest,confirm=True)
    assert graph.get_object(SCOPE,original.object_id)==original
    assert SQLiteEventStore(path).get(SCOPE,first.event_id)==first


def test_other_tenant_same_label_survives_source_erasure(tmp_path):
    path=tmp_path/'synthetic-partitions.sqlite3'
    graph,first,_=project(path)
    other=SCOPE.model_copy(update={'tenant_id':'another-synthetic-owner'})
    _,second,_=project(path,scope=other)
    alias,=graph.list_objects(other,object_type='person').objects
    own,=graph.list_objects(SCOPE,object_type='person').objects
    assert alias.object_id!=own.object_id
    privacy=SQLitePrivacyStore(path)
    plan=privacy.erase_plan(SCOPE,first.event_id)
    privacy.erase_confirm(SCOPE,first.event_id,plan.plan_digest,confirm=True)
    assert graph.get_object(other,alias.object_id).canonical_label=='Maple Finch'
    assert graph.get_object(SCOPE,alias.object_id) is None
    assert SQLiteEventStore(path).get(other,second.event_id)==second


def test_erasure_rollback_restores_source_and_all_cascaded_projection_proofs(tmp_path,monkeypatch):
    path=tmp_path/'synthetic-rollback.sqlite3'
    graph,event,_=project(path)
    alias,=graph.list_objects(SCOPE,object_type='person').objects
    before=graph.get_object(SCOPE,alias.object_id)
    privacy=SQLitePrivacyStore(path)
    plan=privacy.erase_plan(SCOPE,event.event_id)
    import oomp.storage.privacy_store as module
    monkeypatch.setattr(module,'verify_v6',lambda _:False)
    with pytest.raises(ErasureBlockedError):
        privacy.erase_confirm(SCOPE,event.event_id,plan.plan_digest,confirm=True)
    assert graph.get_object(SCOPE,alias.object_id)==before
    assert SQLiteEventStore(path).get(SCOPE,event.event_id)==event
    with closing(sqlite3.connect(path)) as c:
        assert c.execute("SELECT name FROM sqlite_master WHERE name='events_no_delete'").fetchone()
        assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
