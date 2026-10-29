"""P1 TRACE adapter policy; synthetic layout only, never the private workspace."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from oomp.cli import main
from oomp.product.discovery import TRACE_FILES, project_fingerprint
from oomp.product.lifecycle import validate_publication
from oomp.product.models import Profile
from oomp.product.profiles import ProfileStore
from oomp.product.safety import ProductError


def layout(root):
    for name in (*TRACE_FILES, "backend/__init__.py", "backend/services/__init__.py"):
        file = root/name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("# synthetic marker, not a running TRACE application\n", encoding="utf-8")
    return root


def test_trace_credentials_match_existing_wire_roles_and_owner_without_env_edits(tmp_path):
    project = layout(tmp_path/"synthetic TRACE")
    original_env = project/".env"
    original_env.write_bytes(b"PRIVATE_EXISTING_SENTINEL=keep-this\n")
    store = ProfileStore(tmp_path/"profiles")
    profile = Profile(name="trace", adapter="trace", project=str(project),
        database=str(store.directory("trace")/"memory.sqlite3"), tenant="p1-synthetic-owner", namespace="personal",
        principal="trace-host", owner_id="000000000000000000000001", mode="trusted-ingest", read_source=True)
    store.create(profile, create_credentials=True)
    environment = store.host_environment(profile)
    assert environment["TRACE_OOMP_MODE"] == "retrieve_and_ingest"
    assert environment["TRACE_OOMP_OWNER_ID"] == profile.owner_id
    assert environment["TRACE_OOMP_READ_TOKEN"] != environment["TRACE_OOMP_OWNER_KEY"]
    writers = json.loads(Path(environment["TRACE_OOMP_WRITER_CONFIG"]).read_text())
    assert set(writers) == {"user", "assistant", "feedback"}
    for role, grant in writers.items():
        assert grant["source_type"] == ("assistant" if role == "assistant" else "user")
        assert grant["event_types"] == ["feedback" if role == "feedback" else role+"_message"]
        assert grant["tenant_id"] == profile.tenant and grant["principal_id"] == profile.principal
        assert environment[grant["approval_key_env"]] != environment[grant["bearer_token_env"]]
    assert original_env.read_bytes() == b"PRIVATE_EXISTING_SENTINEL=keep-this\n"
    assert not any(p.name == "client.json" for p in project.rglob("*"))
    assert not any(v in json.dumps(store.preview(profile)) for v in store.environment(profile).values())


@pytest.mark.parametrize("change", [{"owner_id": None}, {"transport": "stdio"}])
def test_trace_requires_explicit_owner_and_http(tmp_path, change):
    data = dict(name="trace", adapter="trace", project=str(tmp_path), database=str(tmp_path/"new.sqlite3"),
                owner_id="synthetic-owner", read_source=True)
    with pytest.raises(ValueError):
        Profile(**(data | change))


def test_trace_does_not_need_raw_source_capability_for_mongo_provenance(tmp_path):
    profile = Profile(name="trace", adapter="trace", project=str(tmp_path), database=str(tmp_path/"new.sqlite3"),
                      owner_id="synthetic-owner")
    assert profile.grants()[0].capabilities == ("read",)


def test_managed_publication_requires_pinned_explicit_host_approval(tmp_path, capsys):
    project = layout(tmp_path/"TRACE clone")
    home = tmp_path/"not-created"
    args = ["onboard", "--profile", "trace", "--home", str(home), "--project", str(project),
        "--adapter", "trace", "--owner-id", "synthetic", "--read-source", "--mode", "trusted-ingest", "--approve-ingest",
        "--publication", "--host-python", str(Path(sys.executable).resolve()), "--mongo-uri-env", "P1_TEST_MONGO",
        "--mongo-database", "p1_test", "--yes", "--json"]
    assert main(args) == 1
    assert json.loads(capsys.readouterr().out)["code"] == "publication_approval_required"
    assert not home.exists()
    assert main([*args, "--approve-host", "--dry-run"]) == 0
    assert not home.exists()


def test_changed_approved_bootstrap_fails_closed_before_host_execution(tmp_path):
    project = layout(tmp_path/"synthetic")
    profile = Profile(name="trace", adapter="trace", project=str(project), database=str(tmp_path/"new.sqlite3"),
        owner_id="synthetic-owner", read_source=True, mode="trusted-ingest", publication=True,
        host_python=str(Path(sys.executable).resolve()), approved_project=project_fingerprint(project),
        mongo_uri_env="P1_TEST_MONGO", mongo_database="p1_test")
    validate_publication(profile)
    (project/"backend/__init__.py").write_text("raise RuntimeError('changed code must not execute')\n")
    with pytest.raises(ProductError, match="approved_host_code_changed_or_unavailable"):
        validate_publication(profile)


def test_no_host_execution_without_operator_argv_approval(tmp_path, capsys):
    project = layout(tmp_path/"synthetic")
    store = ProfileStore(tmp_path/"profiles")
    profile = Profile(name="trace", adapter="trace", project=str(project), database=str(store.directory("trace")/"db.sqlite3"),
                      owner_id="synthetic-owner", read_source=True)
    store.create(profile, create_credentials=True)
    marker = tmp_path/"must-not-exist"
    args = ["host", "--profile", "trace", "--home", str(store.home), "--json", "--",
            sys.executable, "-c", f"open({str(marker)!r},'w').write('unapproved')"]
    assert main(args) == 1
    assert not marker.exists()
    assert "explicit_host_execution_approval_required" in capsys.readouterr().out


def test_only_explicit_mongo_reference_survives_background_environment_sanitization(tmp_path, monkeypatch):
    from oomp.product.lifecycle import child_environment, publication_uri
    project = layout(tmp_path/"synthetic")
    store = ProfileStore(tmp_path/"profiles")
    profile = Profile(name="trace", adapter="trace", project=str(project), database=str(store.directory("trace")/"db.sqlite3"),
        owner_id="synthetic-owner", read_source=True, mode="trusted-ingest", publication=True,
        host_python=str(Path(sys.executable).resolve()), approved_project=project_fingerprint(project), mongo_uri_env="P1_TEST_MONGO", mongo_database="synthetic")
    store.create(profile, create_credentials=True)
    monkeypatch.setenv("P1_TEST_MONGO", "mongodb://127.0.0.1:27017/")
    monkeypatch.setenv("MONGO_URI", "PRIVATE_UNRELATED_REFERENCE")
    monkeypatch.setenv("PYTHONPATH", "UNTRUSTED_IMPORT_PATH")
    environment = child_environment(store, profile)
    assert environment["P1_TEST_MONGO"] == publication_uri(profile)
    assert "MONGO_URI" not in environment and "PYTHONPATH" not in environment
    monkeypatch.setenv("P1_TEST_MONGO", "mongodb://outside.example:27017/")
    with pytest.raises(ProductError, match="explicit_local_mongo_reference_required"):
        publication_uri(profile)
