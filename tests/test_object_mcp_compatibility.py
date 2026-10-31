"""Schema-v6 admission and truthful status without new authority or migration."""
from contextlib import closing
import hashlib
import json
from types import SimpleNamespace
import sqlite3

import pytest

pytest.importorskip('mcp',reason='install [mcp] for schema boundary integration')
from oomp.mcp.authorization import GrantResolver
from oomp.mcp.cli import mcp_command
from oomp.mcp.configuration import Grant,ServerConfiguration
from oomp.mcp.contracts import StatusArguments,StatusResult
from oomp.mcp.errors import BoundaryError
from oomp.mcp.service import MemoryService
from oomp.storage.migrations import SCHEMA_VERSION
from oomp.storage.sqlite import SQLiteEventStore
from test_object_migrations import v5_fixture


def configuration(path):
    grant=Grant(grant_id='synthetic-read',principal_id='synthetic-owner',tenant_id='synthetic',
                namespace='p3-compat',capabilities=('read',))
    return ServerConfiguration(database=str(path),transport='stdio',profile='read-only',stdio_grant=grant)


def status_payload():
    return {'read_only':True,'capabilities':['read'],'retrieval_modes':['lexical'],
        'index':{'canonical_count':0,'lexical_count':0,'lexical_stale':0,
                 'compatible_embeddings':None,'stale_embeddings':None},
        'jobs':{key:0 for key in ('queued','running','retry_wait','completed','failed','cancelled',
            'outbox_pending','events_pending_extraction','outstanding_review_proposals')}}


@pytest.mark.parametrize('version',[5,6])
def test_status_contract_explicitly_accepts_legacy_and_current_wire_versions(version):
    value=StatusResult.model_validate({**status_payload(),'schema_version':version})
    assert value.schema_version==version and value.mind_worker_started_by_server is False


@pytest.mark.parametrize('version',[4,7,999])
def test_status_contract_does_not_accept_unspecified_schema_versions(version):
    with pytest.raises(ValueError):StatusResult.model_validate({**status_payload(),'schema_version':version})


@pytest.mark.parametrize('version',[SCHEMA_VERSION+1,999])
def test_mcp_rejects_future_schema_without_modifying_or_migrating_it(tmp_path,version):
    path=tmp_path/'synthetic-future.sqlite3'
    SQLiteEventStore(path).initialize()
    with closing(sqlite3.connect(path)) as c,c:c.execute(f'PRAGMA user_version={version}')
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    config=configuration(path)
    with pytest.raises(BoundaryError,match='storage_unavailable'):
        MemoryService(config,GrantResolver(config,environ={}))
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before


def test_legacy_wire_support_does_not_implicitly_upgrade_a_v5_database(tmp_path):
    path=tmp_path/'synthetic-v5.sqlite3'
    v5_fixture(path)
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    config=configuration(path)
    with pytest.raises(BoundaryError,match='storage_unavailable'):
        MemoryService(config,GrantResolver(config,environ={}))
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before


def test_actual_service_and_cli_report_admitted_current_schema(tmp_path,capsys):
    path=tmp_path/'synthetic-current.sqlite3'
    assert SQLiteEventStore(path).initialize()==SCHEMA_VERSION
    config=configuration(path)
    service=MemoryService(config,GrantResolver(config,environ={}))
    status=service.status(config.stdio_grant,StatusArguments())
    assert status.schema_version==SCHEMA_VERSION and status.read_only
    assert status.capabilities==('read',) and not status.mind_worker_started_by_server
    file=tmp_path/'synthetic-config.json'
    file.write_text(config.model_dump_json(),encoding='utf-8')
    assert mcp_command(SimpleNamespace(mcp_command='check',config=str(file),transport='stdio'))==0
    result=json.loads(capsys.readouterr().out)
    assert result['schema_version']==SCHEMA_VERSION and result['ready'] and not result['mind_worker_started']
