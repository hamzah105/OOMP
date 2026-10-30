"""Frozen fictional P3 lifecycle. Explicit fresh directory; rules only."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path

from oomp.domain.graph import TemporalQuery
from oomp.domain.models import AuthorizedScope,MemoryEvent,SourceReference
from oomp.mind.worker import MindWorker
from oomp.objects import ObjectMap
from oomp.storage.sqlite import SQLiteEventStore
from oomp.understanding.contracts import ExtractionConfiguration

FIXTURE_SHA256='72423795715b94d5d0098920303855c4c6b4c925490e77f29a60073d3d671b2a'


def load_fixture():
    path=Path(__file__).parent/'fixtures/object_relocation_v1.json'
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=FIXTURE_SHA256:raise ValueError('synthetic_fixture_hash_mismatch')
    fixture=json.loads(raw)
    if fixture.get('synthetic') is not True:raise ValueError('synthetic_fixture_required')
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
    return scope,events


def navigation_paths(tree,target):
    children={}
    for edge in tree.memberships:children.setdefault(edge.parent_id,[]).append(edge.child_id)
    result=[]
    pending=[(tree.root_id,)]
    while pending:
        path=pending.pop()
        if path[-1]==target:result.append(path);continue
        if len(path)>10:raise ValueError('synthetic_path_limit')
        pending.extend(path+(child,) for child in children.get(path[-1],()) if child not in path)
        if len(pending)>1000:raise ValueError('synthetic_path_limit')
    return result


def run(directory):
    directory=Path(directory).resolve()
    directory.mkdir(parents=True,exist_ok=False)
    path=directory/'fictional.sqlite3'
    scope,events=load_fixture()
    sources=SQLiteEventStore(path);version=sources.initialize()
    worker=MindWorker(path,scope,extraction_configuration=ExtractionConfiguration(mode='rules'))
    def ingest(batch):
        for event in batch:sources.append(scope,event)
        result=worker.run_once(max_jobs=100)
        if result.failed or result.retried or result.lost_lease:raise ValueError('synthetic_mind_job_failed')
        if worker.handlers.understanding.provider is not None:raise ValueError('rules_only_required')
        return asdict(result)
    first=ingest(events[:10])
    graph=ObjectMap(path);built=graph.build(scope,limit=100)
    plan,=graph.list_objects(scope,object_type='plan').objects
    project,=graph.list_objects(scope,object_type='project').objects
    tree=graph.tree(scope,max_depth=10,max_nodes=300,max_edges=1000,max_work=10000)
    if tree.truncated:raise ValueError('synthetic_tree_incomplete')
    by_id={n.object.object_id:n.object for n in tree.nodes}
    routes=navigation_paths(tree,plan.object_id)
    labels=[[by_id[key].canonical_label for key in route] for route in routes]
    checks={'plans':any('Plans' in route for route in labels),
        'places':any('Islamabad' in route and 'Related plans' in route for route in labels),
        'episodes':any('City comparison' in route and 'Referenced objects' in route for route in labels)}
    if not all(checks.values()):raise ValueError('synthetic_three_path_failure')
    before=datetime.now(timezone.utc)
    second=ingest(events[10:]);graph.build(scope,limit=100)
    updated=graph.get_object(scope,plan.object_id)
    old=graph.get_object(scope,plan.object_id,query=TemporalQuery(known_at=before))
    renamed=graph.get_object(scope,project.object_id)
    if updated.status!='correction_pending' or old.status!='tentative' or renamed.canonical_label!='Aspen':
        raise ValueError('synthetic_history_failed')
    replay=graph.rebuild(scope,limit=100)
    if any((replay.objects_created,replay.proofs_added,replay.relations_added,replay.memberships_added)):
        raise ValueError('synthetic_replay_changed_identity')
    reopened=ObjectMap(path).get_object(scope,plan.object_id)
    if reopened!=updated:raise ValueError('synthetic_reopen_changed_object')
    for proof in updated.source_proofs:
        event=sources.get(scope,proof.event_id)
        if event.content[proof.source_span.start:proof.source_span.end]!=proof.source_span.quote:raise ValueError('synthetic_span_mismatch')
    redacted=graph.export_redacted(scope,max_nodes=300)
    (directory/'redacted.json').write_text(json.dumps(redacted,ensure_ascii=True,indent=2),encoding='utf-8')
    result={'synthetic':True,'schema_version':version,'fixture_sha256':FIXTURE_SHA256,'events':len(events),
        'scope':scope.model_dump(mode='json'),'plan_id':plan.object_id,'project_id':project.object_id,
        'three_paths':checks,'path_labels':labels,'current_status':updated.status,'historical_status':old.status,
        'project_label':renamed.canonical_label,'aliases':renamed.aliases,'source_event_ids':[p.event_id for p in updated.source_proofs],
        'source_proofs':len(updated.source_proofs),'model_calls':0,'first_jobs':first,'correction_jobs':second,
        'build':built.model_dump(mode='json'),'replay':replay.model_dump(mode='json'),
        'reopen_stable':True,'explanation_paths':len(graph.explain(scope,plan.object_id)['evidence_paths'])}
    (directory/'result.json').write_text(json.dumps(result,ensure_ascii=True,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',required=True,type=Path,help='fresh short disposable synthetic directory')
    args=parser.parse_args()
    print(json.dumps(run(args.directory),ensure_ascii=True))
