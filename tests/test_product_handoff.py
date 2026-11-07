"""Private reference-only handoff; synthetic storage, no host process or network."""
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

import pytest

from oomp.product import handoff
from oomp.product.models import Profile
from oomp.product.profiles import ProfileStore
from oomp.product.safety import ProductError, private_permissions, read_json, restrict


@pytest.fixture
def profile_pair(tmp_path):
    project = tmp_path/'TRACE'
    project.mkdir()
    store = ProfileStore(tmp_path/'p')
    profile = Profile(name='trace', adapter='trace', project=str(project),
        database=str(store.directory('trace')/'memory.sqlite3'), tenant='fictional',
        namespace='dedicated', principal='owner', owner_id='000000000000000000000001',
        context_enabled=True)
    store.create(profile, create_credentials=True)
    return store, profile


def test_new_handoff_requires_exact_approval_and_never_changes_profile(profile_pair):
    store, profile = profile_pair
    paths = [store.directory(profile.name)/'secrets.json', store.directory(profile.name)/'active.json',
             store.generation(profile)/'profile.json']
    before = {path: path.read_bytes() for path in paths}
    target = Path(profile.project)/handoff.LOCAL_FILE
    with pytest.raises(ProductError, match='trace_file_creation_approval_required'):
        handoff.configure_trace(store, profile)
    assert not target.exists()
    created = handoff.configure_trace(store, profile, approve=True)
    assert created['configured'] and created['changed'] and private_permissions(target)
    payload = read_json(target)
    values = store.environment(profile)
    text = target.read_text()
    assert all(value not in text for value in values.values())
    body = {key: value for key, value in payload.items() if key != 'signature'}
    expected = hmac.new(values[profile.reference('owner_key')].encode(), handoff._canonical(body), hashlib.sha256).hexdigest()
    assert payload['signature'] == expected and payload['owner_id'] == profile.owner_id
    assert handoff.configure_trace(store, profile) == {**created, 'changed': False}
    assert before == {path: path.read_bytes() for path in paths}


def test_foreign_or_changed_handoff_is_preserved_even_with_approval(profile_pair):
    store, profile = profile_pair
    target = Path(profile.project)/handoff.LOCAL_FILE
    target.write_text('{"owner_id":"someone-else"}')
    restrict(target)
    before = target.read_bytes()
    with pytest.raises(ProductError, match='trace_handoff_changed_requires_review'):
        handoff.configure_trace(store, profile, approve=True)
    assert target.read_bytes() == before


def test_declined_interactive_handoff_has_no_side_effect(profile_pair):
    store, profile = profile_pair
    class UI:
        def preview(self, value):
            self.path = value['path']
        def confirm(self, message):
            assert self.path.endswith(handoff.LOCAL_FILE)
            return False
    with pytest.raises(ProductError, match='trace_file_creation_approval_required'):
        handoff.ensure_connection(store, profile, interactive_ui=UI())
    assert not (Path(profile.project)/handoff.LOCAL_FILE).exists()


def test_prepare_environment_is_narrow_ephemeral_and_conflict_safe(profile_pair, monkeypatch):
    store, profile = profile_pair
    profile = profile.model_copy(update={'publication': True, 'mongo_uri_env': 'HANDOFF_TEST_URI', 'mongo_database': 'fictional'})
    monkeypatch.setattr(handoff, '_trace_query', lambda *a: {'mongo_database':'fictional', 'mongo_uri':'mongodb://127.0.0.1:27017/'})
    monkeypatch.delenv('HANDOFF_TEST_URI', raising=False)
    with handoff.prepare_environment(store, profile):
        assert os.environ['HANDOFF_TEST_URI'] == 'mongodb://127.0.0.1:27017/'
    assert 'HANDOFF_TEST_URI' not in os.environ
    monkeypatch.setenv('HANDOFF_TEST_URI', 'mongodb://127.0.0.1:27018/')
    with pytest.raises(ProductError, match='trace_mongo_reference_conflict'):
        with handoff.prepare_environment(store, profile):
            pytest.fail('conflicting reference accepted')
    assert os.environ['HANDOFF_TEST_URI'].endswith(':27018/')


def test_selected_owner_only_inspection_and_python_mismatch(profile_pair, monkeypatch):
    store, profile = profile_pair
    calls = []
    def inspect(project, arguments):
        calls.append(arguments)
        return {'python':'synthetic', 'mongo_database':'fictional', 'mongo_uri_env':'OOMP_TRACE_MONGO_URI',
                'mongo_configured':True, 'owner_validated':True, 'must_not_escape':'private'}
    monkeypatch.setattr(handoff, '_trace_query', inspect)
    data = handoff.inspect_trace(profile.project, profile.owner_id)
    assert calls == [['--inspect', '--owner-id', profile.owner_id]]
    assert 'must_not_escape' not in data
    with pytest.raises(ProductError, match='trace_owner_id_invalid'):
        handoff.inspect_trace(profile.project, 'guess-another-user')
    with pytest.raises(ProductError, match='trace_python_mismatch'):
        handoff.validate_trace_owner(profile.project, Path(profile.project)/'unexpected.exe', profile.owner_id)


def test_arbitrary_host_helper_is_never_executed(profile_pair):
    store, profile = profile_pair
    with pytest.raises(ProductError, match='reviewed_trace_bootstrap_required'):
        handoff.inspect_trace(profile.project)


def test_localhost_reference_becomes_literal_without_losing_credentials_or_options(profile_pair, monkeypatch):
    from oomp.product.lifecycle import publication_uri
    store, profile = profile_pair
    profile = profile.model_copy(update={'publication':True, 'mongo_uri_env':'HANDOFF_TEST_URI', 'mongo_database':'fictional'})
    source='mongodb://fictional%40user:fictional%3Apassword@localhost:27017/fictional?directConnection=true'
    expected=source.replace('@localhost:', '@127.0.0.1:')
    monkeypatch.setattr(handoff, '_trace_query', lambda *a:{'mongo_database':'fictional','mongo_uri':source})
    monkeypatch.setenv('HANDOFF_TEST_URI',source)
    with handoff.prepare_environment(store,profile):
        assert publication_uri(profile)==expected
    assert os.environ['HANDOFF_TEST_URI']==source


@pytest.mark.parametrize('value', ['mongodb://example.com:27017/', 'mongodb://127.0.0.1:27017,example.com:27017/'])
def test_literal_reference_correction_never_admits_foreign_or_multiple_hosts(value):
    with pytest.raises(ProductError,match='explicit_local_mongo_reference_required'):
        handoff._literal_publication_uri(value)


def test_doctor_resolves_only_approved_publisher_reference_and_restores_environment(tmp_path, monkeypatch):
    project=tmp_path/'TRACE';project.mkdir()
    store=ProfileStore(tmp_path/'p')
    profile=Profile(name='trace',adapter='trace',project=str(project),
        database=str(store.directory('trace')/'memory.sqlite3'),mode='trusted-ingest',
        owner_id='000000000000000000000001',publication=True,host_python=sys.executable,
        approved_project={'reviewed':'1'*64},mongo_uri_env='HANDOFF_TEST_URI',mongo_database='fictional')
    store.create(profile,create_credentials=True)
    calls=[]
    monkeypatch.setattr(handoff,'_trace_query',lambda *args:
        calls.append(args) or {'mongo_database':'fictional','mongo_uri':'mongodb://localhost:27017/'})
    monkeypatch.delenv('HANDOFF_TEST_URI',raising=False)
    with handoff.diagnostic_environment(store,profile.name):
        assert 'HANDOFF_TEST_URI' not in os.environ
    assert not calls
    handoff.configure_trace(store,profile,approve=True)
    with handoff.diagnostic_environment(store,profile.name):
        assert os.environ['HANDOFF_TEST_URI']=='mongodb://127.0.0.1:27017/'
    assert len(calls)==1 and 'HANDOFF_TEST_URI' not in os.environ
    target=project/handoff.LOCAL_FILE
    invalid=read_json(target);invalid['owner_id']='000000000000000000000002'
    target.write_text(json.dumps(invalid))
    with pytest.raises(ProductError,match='trace_handoff_changed_requires_review'):
        with handoff.diagnostic_environment(store,profile.name):
            pytest.fail('changed approval was accepted')
    assert len(calls)==1 and 'HANDOFF_TEST_URI' not in os.environ
