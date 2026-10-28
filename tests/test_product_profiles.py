"""P1 private configuration, read-only discovery and consent regressions."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import socket
import sys

import pytest

from oomp.cli import main
from oomp.product.discovery import discover, TRACE_FILES
from oomp.product.models import Profile
from oomp.product.profiles import ProfileStore
from oomp.product.safety import ProductError, private_permissions, profile_name, safe_path


def setup_profile(tmp_path, **changes):
    store = ProfileStore(tmp_path / "private profiles سلام")
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", 0))
        port = connection.getsockname()[1]
    data = {"name": "test", "port": port, "database": str(store.directory("test") / "memory.sqlite3"), **changes}
    profile = Profile(**data)
    store.create(profile, create_credentials=True)
    return store, profile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("name", ["../escape", "a/b", "a\\b", "CON", "nul", "com1", "", "a"*33, "with space"])
def test_profile_names_cannot_escape_or_select_windows_devices(name):
    with pytest.raises(ProductError):
        profile_name(name)


def test_profile_setup_is_private_idempotent_and_never_rotates(tmp_path):
    store, profile = setup_profile(tmp_path)
    files = [store.directory("test")/"active.json", store.directory("test")/"secrets.json", Path(profile.database)]
    before = {str(p): digest(p) for p in files}
    assert all(private_permissions(p) for p in files)
    assert store.load("test") == profile
    assert store.create(profile, create_credentials=True) is False
    assert {str(p): digest(p) for p in files} == before
    environment = store.environment(profile)
    assert len(set(environment.values())) == len(environment)
    assert not any(v in json.dumps(store.preview(profile)) for v in environment.values())


def test_setup_refuses_any_existing_database_and_preserves_bytes(tmp_path):
    store = ProfileStore(tmp_path/"profiles")
    database = tmp_path/"do not alter.sqlite3"
    database.write_bytes(b"private unrelated bytes")
    profile = Profile(name="test", database=str(database))
    with pytest.raises(ProductError, match="existing_database_refused"):
        store.create(profile, create_credentials=True)
    assert database.read_bytes() == b"private unrelated bytes"
    assert not (store.directory("test")/"secrets.json").exists()


def test_interrupted_setup_resumes_only_claimed_file_without_secret_rotation(tmp_path, monkeypatch):
    from oomp.storage import SQLiteEventStore
    store = ProfileStore(tmp_path/"profiles")
    profile = Profile(name="test", database=str(store.directory("test")/"memory.sqlite3"))
    real_initialize = SQLiteEventStore.initialize
    with monkeypatch.context() as patch:
        patch.setattr(SQLiteEventStore, "initialize", lambda *_: (_ for _ in ()).throw(RuntimeError("interruption")))
        with pytest.raises(RuntimeError):
            store.create(profile, create_credentials=True)
    secret_hash = digest(store.directory("test")/"secrets.json")
    assert not (store.directory("test")/"active.json").exists()
    assert store.resume("test") == profile
    assert digest(store.directory("test")/"secrets.json") == secret_hash
    assert SQLiteEventStore(profile.database).status().schema_version == 5


def test_interrupted_setup_cannot_adopt_replaced_database(tmp_path, monkeypatch):
    from oomp.storage import SQLiteEventStore
    store = ProfileStore(tmp_path/"profiles")
    database = store.directory("test")/"memory.sqlite3"
    profile = Profile(name="test", database=str(database))
    with monkeypatch.context() as patch:
        patch.setattr(SQLiteEventStore, "initialize", lambda *_: (_ for _ in ()).throw(RuntimeError()))
        with pytest.raises(RuntimeError):
            store.create(profile, create_credentials=True)
    replacement = database.with_name("replacement.sqlite3")
    replacement.write_bytes(b"foreign data must survive")
    os.replace(replacement, database)
    with pytest.raises(ProductError, match="database_ownership_unverified"):
        store.resume("test")
    assert database.read_bytes() == b"foreign data must survive"


def test_atomic_generation_failure_preserves_active_config_and_credentials(tmp_path, monkeypatch):
    import oomp.product.profiles as module
    store, old = setup_profile(tmp_path)
    new = Profile.model_validate({**old.model_dump(mode="json"), "port": 19999})
    active = digest(store.directory("test")/"active.json")
    secret = digest(store.directory("test")/"secrets.json")
    real = module.write_json
    def interrupted(path, value):
        if path.name == "active.json":
            raise RuntimeError("simulated power loss before commit")
        return real(path, value)
    with monkeypatch.context() as patch:
        patch.setattr(module, "write_json", interrupted)
        with pytest.raises(RuntimeError):
            store.update(new)
    assert store.load("test") == old
    assert digest(store.directory("test")/"active.json") == active
    assert digest(store.directory("test")/"secrets.json") == secret
    store.update(new)
    assert store.load("test") == new


def test_config_cannot_rebind_data_scope_or_write_authority(tmp_path):
    store, profile = setup_profile(tmp_path)
    updated = Profile.model_validate({**profile.model_dump(mode="json"), "tenant": "other-owner"})
    with pytest.raises(ProductError, match="identity_change_requires_new_profile"):
        store.update(updated)
    assert store.load("test") == profile


def test_environment_secret_references_and_duplicate_values(tmp_path, monkeypatch):
    store = ProfileStore(tmp_path/"profiles")
    profile = Profile(name="test", database=str(store.directory("test")/"memory.sqlite3"),
                      mode="trusted-ingest", secret_source="environment")
    for index, role in enumerate(profile.secret_roles()):
        monkeypatch.setenv(profile.reference(role), chr(65+index)*43)
    store.create(profile)
    assert not (store.directory("test")/"secrets.json").exists()
    monkeypatch.setenv(profile.reference("user_approval"), os.environ[profile.reference("read_token")])
    with pytest.raises(ProductError, match="credentials_missing_or_not_distinct"):
        store.environment(profile)


def test_discovery_is_bounded_read_only_and_never_executes_project_code(tmp_path):
    project = tmp_path/"untrusted project"
    project.mkdir()
    marker = tmp_path/"executed"
    (project/"main.py").write_text(f"from fastapi import FastAPI\nopen({str(marker)!r}, 'w').write('bad')", encoding="utf-8")
    (project/"requirements.txt").write_text("fastapi\n", encoding="utf-8")
    (project/".env").write_text("PRIVATE_SENTINEL_"+"S"*43, encoding="utf-8")
    before = {p.name: digest(p) for p in project.iterdir()}
    result = discover(project)
    assert result["kind"] == "unknown" and result["languages"] == ["Python"]
    assert result["frameworks"] and ".env" not in result["indicators"]
    assert "PRIVATE_SENTINEL" not in json.dumps(result)
    assert not marker.exists()
    assert {p.name: digest(p) for p in project.iterdir()} == before


def test_discovery_recognizes_trace_indicators_and_generic_mcp_without_claiming_runtime(tmp_path):
    for name in TRACE_FILES:
        file = tmp_path/name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("# synthetic layout only", encoding="utf-8")
    assert discover(tmp_path)["kind"] == "trace"
    assert "not probed" in discover(tmp_path)["provider_discovery"]
    (tmp_path/TRACE_FILES[0]).unlink()
    (tmp_path/"mcp.json").write_text('{}')
    assert discover(tmp_path)["kind"] == "generic-mcp"


def test_linked_directories_and_hardlinks_are_refused(tmp_path):
    target, linked = tmp_path/"target", tmp_path/"linked"
    target.mkdir()
    if os.name == "nt":
        completed = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(linked), str(target)], capture_output=True)
        assert completed.returncode == 0, "test junction could not be created in disposable storage"
    else:
        linked.symlink_to(target, target_is_directory=True)
    with pytest.raises(ProductError, match="linked_path_refused"):
        discover(linked)
    first, second = target/"first", target/"second"
    first.write_bytes(b"owned fixture")
    os.link(first, second)
    with pytest.raises(ProductError, match="linked_path_refused"):
        safe_path(second)


def test_unsafe_or_overlong_profile_paths_fail_before_setup(tmp_path):
    with pytest.raises(ProductError, match="unsafe_path"):
        safe_path(tmp_path/"bad\x1b[31mpath")
    if os.name == "nt":
        home = tmp_path/("long"*35)
        with pytest.raises(ProductError, match="profile_path_too_long_use_shorter_home"):
            ProfileStore(home).directory("test")
        assert not home.exists()


def test_onboard_dry_run_and_noninteractive_confirmation_do_not_create_files(tmp_path, capsys, monkeypatch):
    home = tmp_path/"not created"
    assert main(["onboard", "--home", str(home), "--dry-run", "--json"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["services_started"] is False and not home.exists()
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert main(["onboard", "--home", str(home), "--plain"]) == 1
    assert not home.exists()


def test_unknown_and_absent_projects_are_actionable_without_any_setup(tmp_path, capsys):
    home = tmp_path/"profiles"
    unknown = tmp_path/"unknown"
    unknown.mkdir()
    assert main(["onboard", "--project", str(unknown), "--home", str(home), "--yes", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["code"] == "unknown_project_choose_generic_or_standalone"
    assert not home.exists()
    assert main(["onboard", "--project", str(unknown/"missing"), "--home", str(home), "--dry-run", "--json"]) == 1
    assert not home.exists()


def test_wizard_cancellation_leaves_no_profile_or_credentials(tmp_path, capsys, monkeypatch):
    from oomp.product.ui import UI
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(UI, "choose", lambda self, label, choices, default=None: default or choices[0])
    monkeypatch.setattr(UI, "text", lambda self, label, default="": default)
    monkeypatch.setattr(UI, "confirm", lambda *_: False)
    home = tmp_path/"cancelled"
    assert main(["onboard", "--home", str(home), "--plain"]) == 1
    assert "cancelled_no_changes" in capsys.readouterr().out
    assert not home.exists()


def test_optional_ui_absence_and_no_color_have_plain_recovery(tmp_path, monkeypatch, capsys):
    from oomp.product.ui import UI
    monkeypatch.setenv("NO_COLOR", "")
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    ui = UI()
    ui.welcome()
    ui.line("PASS", "synthetic")
    assert ui.plain and "\x1b" not in capsys.readouterr().out
    monkeypatch.delenv("NO_COLOR")
    monkeypatch.setitem(sys.modules, "rich.console", None)
    ui = UI()
    assert ui.plain


def test_export_uninstall_never_claims_or_removes_existing_host_files(tmp_path):
    project = tmp_path/"generic"
    project.mkdir()
    store, profile = setup_profile(tmp_path, adapter="generic-mcp", project=str(project))
    output = project/"host-template.json"
    output.write_bytes(b"existing host config")
    with pytest.raises(ProductError, match="existing_host_file_preserved"):
        store.exported_template(profile, output, apply=True)
    assert output.read_bytes() == b"existing host config"
    output.unlink()
    store.exported_template(profile, output, apply=True)
    assert output.is_file()
    store.uninstall("test")
    assert output.is_file()
    output.write_bytes(output.read_bytes()+b"\n")
    with pytest.raises(ProductError, match="modified_host_artifact_preserved"):
        store.uninstall("test", apply=True)
    assert output.is_file()


def test_export_repeated_then_uninstall_only_removes_owned_template(tmp_path):
    project = tmp_path/"generic"
    project.mkdir()
    store, profile = setup_profile(tmp_path, adapter="generic-mcp", project=str(project))
    output = project/"template.json"
    store.exported_template(profile, output, apply=True)
    before = digest(output)
    store.exported_template(profile, output, apply=True)
    assert digest(output) == before
    store.uninstall("test", apply=True)
    assert not output.exists() and Path(profile.database).exists()
    assert store.environment(profile)


def test_identical_unowned_export_is_preserved_on_uninstall(tmp_path):
    project = tmp_path/"generic"
    project.mkdir()
    store, profile = setup_profile(tmp_path, adapter="generic-mcp", project=str(project))
    output = project/"existing.json"
    output.write_bytes((store.generation(profile)/"client.json").read_bytes())
    store.exported_template(profile, output, apply=True)
    assert not (store.directory("test")/"integration-receipt.json").exists()
    store.uninstall("test", apply=True)
    assert output.exists()


def test_replaced_host_template_is_not_owned_even_when_bytes_match(tmp_path):
    project = tmp_path/"generic"
    project.mkdir()
    store, profile = setup_profile(tmp_path, adapter="generic-mcp", project=str(project))
    output = project/"client.json"
    store.exported_template(profile, output, apply=True)
    replacement = project/"replacement.json"
    replacement.write_bytes(output.read_bytes())
    os.replace(replacement, output)
    with pytest.raises(ProductError, match="modified_host_artifact_preserved"):
        store.uninstall("test", apply=True)
    assert output.exists()


def test_actual_optional_keyboard_selection_and_cancellation(monkeypatch):
    questionary = pytest.importorskip("questionary", reason="install [ui] for actual keyboard menus")
    pytest.importorskip("rich", reason="install [ui] for terminal rendering")
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput
    from oomp.product.ui import UI
    original = questionary.select
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    with create_pipe_input() as pipe:
        def select(*args, **kwargs):
            return original(*args, **kwargs, input=pipe, output=DummyOutput())
        monkeypatch.setattr(questionary, "select", select)
        ui = UI()
        assert ui.console is not None and not ui.plain
        pipe.send_text("\x1b[B\r")
        assert ui.choose("Synthetic selection", ("First", "Second")) == "Second"
        pipe.send_text("\x03")
        with pytest.raises(KeyboardInterrupt):
            ui.choose("Synthetic cancellation", ("First", "Second"))
