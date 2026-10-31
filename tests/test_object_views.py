"""Offline views, ambiguous identity and CLI permission/redaction boundaries."""
from contextlib import closing
import json
import os
import re
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from oomp.domain.enums import RelationshipType
from oomp.objects import ObjectMap,ObjectMapError
from oomp.mind.contracts import JobType
from oomp.storage.mind_projection_store import SQLiteMindProjectionStore
from oomp.storage.mind_store import SQLiteMindStore,LostLeaseError
from test_object_projection import fictional,process
from test_object_storage import SCOPE,setup


@pytest.fixture
def case(tmp_path):
    path=tmp_path/'views.sqlite3'
    scope,sources,worker,events=fictional(path)
    process(sources,worker,scope,events[:10])
    graph=ObjectMap(path);graph.build(scope,limit=100)
    process(sources,worker,scope,events[10:]);graph.build(scope,limit=100)
    plan,=graph.list_objects(scope,object_type='plan').objects
    return path,scope,graph,plan


def test_history_explanation_and_actual_summary_revisions(case):
    _,scope,graph,plan=case
    history=graph.history(scope,plan.object_id)
    assert [item['label'] for item in history['changes']]==['Potential relocation','not to move this year']
    assert history['changes'][-1]['status']=='correction_pending'
    explanation=graph.explain(scope,plan.object_id,max_paths=16,max_work=10000)
    assert len(explanation['navigation_paths'])>=3 and len(explanation['evidence_paths'])==2
    assert {p['event_id'] for p in explanation['direct_source_proofs']}=={'p3-plan','p3-correction'}
    assert explanation['association_is_not_truth'] and not explanation['truncated']
    episode=next(obj for obj in graph.list_objects(scope,object_type='episode').objects if obj.canonical_label=='City comparison')
    revisions=graph.history(scope,episode.object_id)['summary_revisions']
    assert len(revisions)>=2 and all(row['source_event_ids'] for row in revisions)
    assert revisions[-1]['basis']=='derived_extractive_summary'


def test_redacted_export_keeps_relationships_without_labels_sources_or_scope(case):
    _,scope,graph,plan=case
    result=graph.export_redacted(scope,max_nodes=300)
    encoded=json.dumps(result)
    assert result['redacted'] and not result['truncated'] and result['relations']
    assert any(obj['object_id']==plan.object_id and obj['label'] is None for obj in result['objects'])
    assert not re.search(r'"source_span"\s*:',encoded)
    for secret in ('Karachi','Islamabad','Cedar','Aspen','not to move','fictional-owner','public-synthetic-p3'):
        assert secret not in encoded
    assert not graph.export_redacted(scope.model_copy(update={'principal_id':'other'}))['objects']


def test_exact_alias_lookup_and_retraction_hide_current_but_retain_auditable_history(case):
    path,scope,graph,plan=case
    current,=graph.find_objects(scope,'Aspen')[0]
    alias,=graph.find_objects(scope,'Cedar')[0]
    assert current.object_id==alias.object_id
    assert graph.find_objects(scope,'aspen')[0]==()
    for proof in plan.source_proofs:SQLiteMindProjectionStore(path).retract_source(scope,proof.memory_id,proof.event_id)
    assert graph.get_object(scope,plan.object_id) is None
    assert all(item['status']=='withdrawn' for item in graph.history(scope,plan.object_id)['changes'])
    assert not graph.history(scope,plan.object_id)['current_supported']
    assert not graph.relations(scope,plan.object_id)[0]
    graph.rebuild(scope,limit=100)
    assert graph.get_object(scope,plan.object_id) is None


def test_protected_or_unsupported_association_cannot_be_invented(case):
    _,scope,graph,plan=case
    project,=graph.list_objects(scope,object_type='project').objects
    proofs=(project.source_proofs[0].proof_id,plan.source_proofs[0].proof_id)
    for kind,role in ((RelationshipType.SUPERSEDES,'existing_graph'),(RelationshipType.CONTRADICTS,'correction_review'),
                      (RelationshipType.RELATED_TO,'imagined_relation')):
        with pytest.raises(ObjectMapError):graph.associate(scope,project.object_id,plan.object_id,kind,role,proofs)
    episode=graph.list_objects(scope,object_type='episode').objects[0]
    fact=next(obj for obj in graph.list_objects(scope,object_type='fact').objects if obj.source_proofs[0].event_id=='p3-city')
    with pytest.raises(ObjectMapError,match='context_relation_required'):
        graph.add_membership(scope,episode.object_id,fact.object_id,'fact',proof_id=fact.source_proofs[0].proof_id)


def test_forged_relation_basis_is_rejected_without_echoing_source(case):
    path,scope,graph,plan=case
    relation=next(r for r in graph.relations(scope,plan.object_id)[0] if r.basis=='derived_context')
    with closing(sqlite3.connect(path)) as c,c:c.execute("UPDATE map_relations SET basis='source_span' WHERE relation_id=?",(relation.relation_id,))
    with pytest.raises(ObjectMapError,match='object_relation_basis_invalid'):graph.relations(scope,plan.object_id)


def test_ambiguous_aliases_unicode_org_and_owner_isolation(tmp_path):
    path=tmp_path/'identities.sqlite3'
    setup(path,'My test alias is Maple Finch.')
    setup(path,'Call me Maple Finch.',event_id='e2')
    setup(path,'My test alias is زارا.',event_id='unicode')
    setup(path,'I work for Juniper Labs.',event_id='org')
    setup(path,'I plan to build a paper model.',event_id='goal')
    other=SCOPE.model_copy(update={'tenant_id':'other'})
    setup(path,'My test alias is Maple Finch.',scope=other,event_id='e1')
    graph=ObjectMap(path);graph.build(SCOPE);graph.build(other)
    aliases,more=graph.find_objects(SCOPE,'Maple Finch')
    assert len(aliases)==2 and not more and all(not proof.verified for obj in aliases for proof in obj.source_proofs)
    assert len(graph.find_objects(SCOPE,'زارا')[0])==1
    assert graph.list_objects(SCOPE,object_type='organization').objects[0].canonical_label=='Juniper Labs'
    assert graph.list_objects(SCOPE,object_type='plan').objects[0].canonical_label=='build a paper model'
    foreign,=graph.find_objects(other,'Maple Finch')[0]
    assert foreign.object_id not in {obj.object_id for obj in aliases}


def invoke(case,command,*flags):
    path,scope,_,_=case
    return subprocess.run([sys.executable,'-m','oomp','memory',command,*flags,'--db',str(path),
        '--tenant',scope.tenant_id,'--namespace',scope.namespace,'--principal',scope.principal_id,'--json'],
        capture_output=True,text=True,encoding='utf-8',timeout=45,env={**os.environ,'NO_COLOR':'1'})


def test_cli_views_redaction_and_content_opt_in(case):
    _,_,_,plan=case
    for name in ('inspect','history','explain'):
        basic=invoke(case,name,plan.object_id)
        assert basic.returncode==0,basic.stderr
        assert not re.search(r'"source_span"\s*:',basic.stdout) and 'source_reference' not in basic.stdout and '\x1b' not in basic.stdout
        proof=invoke(case,name,plan.object_id,'--show-provenance')
        assert proof.returncode==0 and 'p3-plan' in proof.stdout and not re.search(r'"source_span"\s*:',proof.stdout)
        content=invoke(case,name,plan.object_id,'--show-content')
        assert content.returncode==0 and 'source_span' in content.stdout
    export=invoke(case,'export','--redacted','--limit','300','--depth','10')
    assert export.returncode==0 and json.loads(export.stdout)['redacted']
    assert 'Karachi' not in export.stdout and 'Aspen' not in export.stdout
    tree=invoke(case,'tree','--limit','300','--depth','10')
    assert tree.returncode==0 and not json.loads(tree.stdout)['truncated']
    assert not re.search(r'"source_span"\s*:',tree.stdout)
    bad=invoke(case,'inspect','a-confidential-invalid-object')
    assert bad.returncode==1 and 'confidential' not in bad.stderr and not bad.stdout
    bounded=invoke(case,'tree','--depth','999')
    assert bounded.returncode==1 and 'object_map_bound_invalid' in bounded.stderr


def test_public_projection_rejects_stale_lease_and_wrong_target(tmp_path):
    path=tmp_path/'job.sqlite3'
    _,event,_=setup(path)
    jobs=SQLiteMindStore(path)
    jobs.enqueue(SCOPE,JobType.EXTRACT_EVENT,'event',event.event_id,idempotency_key='p3-public-fence',policy_version='extract.v1')
    job=jobs.claim(SCOPE,'p3-review-worker',lease_seconds=60)
    assert job is not None
    graph=ObjectMap(path)
    with pytest.raises(ObjectMapError,match='context_invalid'):
        graph.project_event(SCOPE,event.event_id,job=job.model_copy(update={'target_type':'topic'}))
    with pytest.raises(ObjectMapError,match='target_mismatch'):
        graph.project_event(SCOPE,event.event_id,job=job.model_copy(update={'target_id':'other'}))
    with pytest.raises(LostLeaseError):graph.project_event(SCOPE,event.event_id,job=job.model_copy(update={'fencing_token':job.fencing_token+1}))
    with closing(sqlite3.connect(path)) as c:assert c.execute('SELECT COUNT(*) FROM map_objects').fetchone()[0]==0


def test_public_synthetic_example_uses_fresh_directory_and_reopens(tmp_path):
    script=Path(__file__).resolve().parents[1]/'examples/object_memory_quickstart.py'
    directory=tmp_path/'demo'
    run=subprocess.run([sys.executable,str(script),'--directory',str(directory)],capture_output=True,text=True,timeout=90)
    assert run.returncode==0,run.stderr
    report=json.loads(run.stdout)
    assert report['reopen_stable'] and all(report['three_paths'].values()) and report['model_calls']==0
    assert report['current_status']=='correction_pending' and report['source_proofs']==2
    again=subprocess.run([sys.executable,str(script),'--directory',str(directory)],capture_output=True,text=True,timeout=15)
    assert again.returncode!=0
