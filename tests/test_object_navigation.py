"""Real SQLite read snapshots, shared memberships and privacy withdrawal."""
from contextlib import closing
from datetime import datetime,timedelta,timezone
import sqlite3

import pytest

from oomp.domain.graph import TemporalQuery
from oomp.domain.models import RequestedScope
from oomp.objects.contracts import ObjectMapError,ObjectType
from oomp.objects.queries import ObjectQueries
from oomp.storage.mind_projection_store import SQLiteMindProjectionStore
from test_object_storage import SCOPE,setup,put_alias


def populated(path):
    _,event,memory=setup(path)
    store=ObjectQueries(path)
    with store._graph_transaction() as c:identifier,proof=put_alias(c,store,event,memory)
    return store,event,memory,identifier,proof


def test_shared_object_has_one_identity_and_original_proof_through_both_paths(tmp_path):
    store,event,memory,identifier,proof=populated(tmp_path/'multi.sqlite3')
    with store._graph_transaction() as c:
        root=next(row[0] for row in c.execute("SELECT object_id FROM map_objects WHERE object_type='owner'"))
        domain=store.registry(c,SCOPE,ObjectType.DOMAIN,'discussions',structural_label='Discussions')
        topic=store.registry(c,SCOPE,ObjectType.TOPIC,'referenced-people',structural_label='Referenced people')
        store.membership(c,SCOPE,root,domain,'domain')
        store.membership(c,SCOPE,domain,topic,'topic')
        store.membership(c,SCOPE,topic,identifier,'object',proof_id=proof)
    result=store.tree(SCOPE,max_nodes=50)
    assert not result.truncated
    assert sum(node.object.object_id==identifier for node in result.nodes)==1
    assert sum(edge.child_id==identifier for edge in result.memberships)==2
    alias=store.get_object(SCOPE,identifier)
    assert alias.object_type is ObjectType.PERSON and alias.canonical_label=='Maple Finch'
    assert len(alias.source_proofs)==1 and alias.source_proofs[0].event_id==event.event_id
    assert not alias.source_proofs[0].verified


def test_pages_and_foreign_cursor_never_expand_authority(tmp_path):
    store,_,_,identifier,_=populated(tmp_path/'pages.sqlite3')
    page=store.list_objects(SCOPE,limit=1)
    ids=[]
    while True:
        ids.extend(obj.object_id for obj in page.objects)
        if page.next_cursor is None:break
        page=store.list_objects(SCOPE,limit=1,cursor=page.next_cursor)
    assert ids==sorted(set(ids)) and identifier in ids
    other=SCOPE.model_copy(update={'principal_id':'other'})
    first=store.list_objects(SCOPE,limit=1)
    with pytest.raises(ObjectMapError,match='cursor_scope'):
        store.list_objects(other,cursor=first.next_cursor)
    assert store.get_object(other,identifier) is None and not store.tree(other).nodes
    with pytest.raises(TypeError):store.get_object(RequestedScope(tenant_id='p3',namespace='synthetic'),identifier)


@pytest.mark.parametrize('arguments',[{'max_nodes':True},{'max_depth':11},{'max_edges':0},{'max_work':10001}])
def test_invalid_traversal_bounds_rejected(tmp_path,arguments):
    store,*_=populated(tmp_path/'bounds.sqlite3')
    with pytest.raises(ObjectMapError):store.tree(SCOPE,**arguments)


def test_small_budgets_disclose_truncation_and_never_return_orphan_edges(tmp_path):
    store,*_=populated(tmp_path/'bounded.sqlite3')
    for args in ({'max_depth':0},{'max_nodes':1},{'max_work':1}):
        result=store.tree(SCOPE,**args)
        assert result.truncated and len(result.nodes)==1
        ids={node.object.object_id for node in result.nodes}
        assert all(edge.parent_id in ids and edge.child_id in ids for edge in result.memberships)


def test_withdrawn_proof_cannot_leave_visible_object_or_membership(tmp_path):
    path=tmp_path/'withdrawn.sqlite3'
    store,event,memory,identifier,_=populated(path)
    before=datetime.now(timezone.utc)
    SQLiteMindProjectionStore(path).retract_source(SCOPE,memory.memory_id,event.event_id)
    assert store.get_object(SCOPE,identifier) is None
    assert all(node.object.object_id!=identifier for node in store.tree(SCOPE).nodes)
    prior=store.get_object(SCOPE,identifier,query=TemporalQuery(known_at=before))
    assert prior is not None and prior.source_proofs[0].event_id==event.event_id


def test_independent_second_proof_retains_same_object_and_membership(tmp_path):
    path=tmp_path/'independent.sqlite3'
    store,event,memory,identifier,_=populated(path)
    _,second,same=setup(path,event_id='e2')
    with store._graph_transaction() as c:
        same_id,_=put_alias(c,store,second,same)
    assert same_id==identifier and len(store.get_object(SCOPE,identifier).source_proofs)==2
    SQLiteMindProjectionStore(path).retract_source(SCOPE,memory.memory_id,event.event_id)
    alias=store.get_object(SCOPE,identifier)
    assert alias is not None and [p.event_id for p in alias.source_proofs]==['e2']
    assert any(edge.child_id==identifier for edge in store.tree(SCOPE).memberships)


def test_forged_cached_label_is_rejected_against_original_evidence(tmp_path):
    path=tmp_path/'tamper.sqlite3'
    store,_,_,identifier,proof=populated(path)
    with closing(sqlite3.connect(path)) as c,c:
        c.execute("UPDATE map_proofs SET label='FORGED PRIVATE VALUE' WHERE proof_id=?",(proof,))
    with pytest.raises(ObjectMapError) as error:store.get_object(SCOPE,identifier)
    assert 'FORGED PRIVATE VALUE' not in str(error.value)


def test_known_time_before_projection_cannot_invent_backdated_identity(tmp_path):
    store,_,_,identifier,_=populated(tmp_path/'known.sqlite3')
    assert store.get_object(SCOPE,identifier,query=TemporalQuery(known_at=datetime(2020,1,1,tzinfo=timezone.utc))) is None
