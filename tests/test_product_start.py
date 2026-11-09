"""Synthetic default selection, guided startup and truthful status controls."""
from contextlib import nullcontext
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from oomp.cli import main
from oomp.product import lifecycle, start
from oomp.product.models import Profile
from oomp.product.profiles import ProfileStore
from oomp.product.safety import ProductError, private_permissions
from oomp.storage.migrations import SCHEMA_VERSION


def fixture_profile(tmp_path, name="fictional", **changes):
    store = ProfileStore(tmp_path / "p")
    profile = Profile(name=name, database=str(store.directory(name) / "memory.sqlite3"), **changes)
    store.create(profile, create_credentials=True)
    return store, profile


@pytest.fixture
def pin(tmp_path, monkeypatch):
    path = tmp_path / "config" / "start-selection.json"
    monkeypatch.setattr(start, "selection_path", lambda: path)
    return path


def running(profile, **changes):
    roles = {"mcp"} | ({"mind"} if profile.mind else set()) | ({"publication"} if profile.publication else set())
    return {"profile": profile.name, "state": "running", "ownership_verified": True,
            "services": {role: {"ready": True, "alive": True, "last_error_code": None} for role in roles}, **changes}


def handoff_stubs(monkeypatch):
    from oomp.product import handoff
    monkeypatch.setattr(handoff, "ensure_connection", lambda *args, **kwargs: {"configured": True})
    monkeypatch.setattr(handoff, "prepare_environment", lambda *args, **kwargs: nullcontext())
    return handoff


def test_remember_is_private_idempotent_and_never_rotates_profile(tmp_path, pin):
    store, profile = fixture_profile(tmp_path)
    paths = [store.directory(profile.name)/"active.json", store.directory(profile.name)/"secrets.json", Path(profile.database)]
    before = {path: path.read_bytes() for path in paths}
    assert start.remember(store, profile)
    raw = pin.read_bytes()
    assert private_permissions(pin)
    assert not start.remember(store, profile)
    assert pin.read_bytes() == raw
    chosen = start.resolve_selection()
    assert chosen[0].home == store.home and chosen[1] == profile.name
    assert {path: path.read_bytes() for path in paths} == before
    values = store.environment(profile)
    assert all(value not in raw.decode() for value in values.values())


def test_explicit_selection_is_not_replaced_by_saved_default(tmp_path, pin):
    store, profile = fixture_profile(tmp_path)
    start.remember(store, profile)
    chosen, name = start.resolve_selection(str(tmp_path / "another"), "specific")
    assert chosen.home == tmp_path / "another" and name == "specific"


def test_default_selection_creates_private_child_without_restricting_existing_parent(tmp_path, monkeypatch):
    from oomp.product.safety import private_permissions
    shared = tmp_path / "existing-application"
    shared.mkdir()
    before = shared.stat().st_mode
    monkeypatch.setattr(start, "default_home", lambda: shared / "profiles")
    store, profile = fixture_profile(tmp_path)
    assert start.remember(store, profile)
    assert start.selection_path() == shared / "startup" / "selection.json"
    assert private_permissions(shared / "startup")
    assert private_permissions(start.selection_path())
    assert shared.stat().st_mode == before
    assert start.resolve_selection()[1] == profile.name


def test_selection_replacement_needs_explicit_approval(tmp_path, pin):
    store, profile = fixture_profile(tmp_path)
    other = Profile(name="second", database=str(store.directory("second") / "memory.sqlite3"))
    store.create(other, create_credentials=True)
    start.remember(store, profile)
    before = pin.read_bytes()
    with pytest.raises(ProductError, match="explicit_replacement_required"):
        start.remember(store, other)
    assert pin.read_bytes() == before
    assert start.remember(store, other, replace=True)
    assert start.resolve_selection()[1] == "second"


def test_saved_authority_tampering_is_rejected(tmp_path, pin):
    store, profile = fixture_profile(tmp_path)
    start.remember(store, profile)
    # Simulate a replaced generation; ordinary config does not permit this.
    store._generation(profile.model_copy(update={"principal": "foreign-principal"}))
    with pytest.raises(ProductError, match="selected_profile_authority_changed"):
        start.resolve_selection()


def test_operational_configuration_preserves_saved_authority(tmp_path, pin):
    store, profile = fixture_profile(tmp_path)
    start.remember(store, profile)
    store.update(profile.model_copy(update={"context_enabled": True, "port": 18988}))
    assert start.resolve_selection()[1] == profile.name


def test_no_selection_does_not_scan_or_adopt_private_profiles(tmp_path, pin, monkeypatch):
    monkeypatch.setattr(ProfileStore, "load", lambda *args: pytest.fail("unexpected profile inspection"))
    assert start.resolve_selection() is None
    fallback = start.resolve_selection(fallback=True)
    assert fallback[1] == "local" and not pin.exists()


def test_reuses_authenticated_running_supervisor_without_start_or_mongo_lookup(tmp_path, monkeypatch):
    store, profile = fixture_profile(tmp_path)
    handoff = handoff_stubs(monkeypatch)
    monkeypatch.setattr(lifecycle, "control", lambda *args: running(profile))
    monkeypatch.setattr(lifecycle, "start", lambda *args, **kwargs: pytest.fail("duplicate process launch"))
    monkeypatch.setattr(handoff, "prepare_environment", lambda *args: pytest.fail("running profile does not need Mongo URI"))
    monkeypatch.setattr(start, "probe_runtime", lambda *args: ({"schema_version": SCHEMA_VERSION}, {"memory.status"}))
    before = (store.directory(profile.name)/"secrets.json").read_bytes()
    result = start.launch(store, profile)
    assert result["mcp_verified"] and result["database_ready"]
    assert (store.directory(profile.name)/"secrets.json").read_bytes() == before


def test_stopped_profile_uses_existing_managed_background_start(tmp_path, monkeypatch):
    store, profile = fixture_profile(tmp_path)
    handoff_stubs(monkeypatch)
    monkeypatch.setattr(lifecycle, "control", lambda *args: {"state": "stopped"})
    calls = []
    monkeypatch.setattr(lifecycle, "start", lambda actual, selected, **kwargs:
                        calls.append((actual, selected, kwargs)) or running(profile))
    monkeypatch.setattr(start, "probe_runtime", lambda *args: ({"schema_version": SCHEMA_VERSION}, set()))
    start.launch(store, profile)
    assert calls == [(store, profile, {"background": True})]


@pytest.mark.parametrize("state", ["unverified", "missing_worker", "warning"])
def test_uncertain_or_degraded_components_never_report_start_success(tmp_path, monkeypatch, state):
    store, profile = fixture_profile(tmp_path)
    handoff_stubs(monkeypatch)
    report = running(profile)
    if state == "unverified":
        report.update(state="unverified", ownership_verified=False)
    elif state == "missing_worker":
        report["services"].pop("mind")
    else:
        report["services"]["mind"]["last_error_code"] = "work_warning"
    monkeypatch.setattr(lifecycle, "control", lambda *args: report)
    monkeypatch.setattr(lifecycle, "start", lambda *args, **kwargs: pytest.fail("unsafe launch"))
    monkeypatch.setattr(start, "probe_runtime", lambda *args: pytest.fail("unexpected success probe"))
    with pytest.raises(ProductError):
        start.launch(store, profile)


def test_missing_context_tool_is_not_a_context_v1_success(tmp_path, monkeypatch):
    store, profile = fixture_profile(tmp_path, context_enabled=True)
    handoff_stubs(monkeypatch)
    monkeypatch.setattr(lifecycle, "control", lambda *args: running(profile))
    monkeypatch.setattr(start, "probe_runtime", lambda *args: ({"schema_version": SCHEMA_VERSION}, {"memory.status"}))
    with pytest.raises(ProductError, match="configured_context_tool_unavailable"):
        start.launch(store, profile)


def test_bare_status_and_stop_use_only_saved_profile(tmp_path, pin, monkeypatch, capsys):
    store, profile = fixture_profile(tmp_path)
    start.remember(store, profile)
    selected = []
    monkeypatch.setattr(lifecycle, "control", lambda actual, name:
                        selected.append((actual.home, name)) or running(profile))
    monkeypatch.setattr(lifecycle, "stop", lambda actual, name:
                        selected.append((actual.home, name)) or {"profile": name, "state": "stopped"})
    assert main(["status", "--json"]) == 0
    assert main(["stop", "--json"]) == 0
    assert selected == [(store.home, profile.name), (store.home, profile.name)]
    assert "stopped" in capsys.readouterr().out


def test_no_setup_noninteractive_does_not_create_anything(tmp_path, pin, capsys):
    assert main(["start", "--json"]) == 1
    assert "setup_required" in capsys.readouterr().out
    assert not pin.parent.exists()


def test_full_doctor_uses_pinned_profile_without_rebinding(tmp_path, pin, monkeypatch, capsys):
    from oomp.product import diagnostics
    store, profile = fixture_profile(tmp_path)
    start.remember(store, profile)
    selected = []
    def diagnose(actual, name, *, full):
        selected.append((actual.home, name, full))
        return {"ok": True, "profile": name}
    monkeypatch.setattr(diagnostics, "diagnose", diagnose)
    assert main(["doctor", "--full", "--json"]) == 0
    assert selected == [(store.home, profile.name, True)]
    assert json.loads(capsys.readouterr().out)["profile"] == profile.name


class ScriptUI:
    def __init__(self, confirms):
        self.confirms = iter(confirms)
        self.output = []
    def welcome(self): pass
    def line(self, *args): self.output.append(args)
    def text(self, *args): return "000000000000000000000001"
    def choose(self, *args): return "Read-only"
    def confirm(self, *args): return next(self.confirms)
    def preview(self, value): self.output.append(value)


def test_fictional_first_setup_validates_exact_owner_before_credentials(tmp_path, monkeypatch, pin):
    from oomp.product import handoff
    store = ProfileStore(tmp_path / "p")
    project = tmp_path / "trace-project"
    project.mkdir()
    monkeypatch.setattr(start, "_trace_project", lambda *args: project)
    monkeypatch.setattr(handoff, "inspect_trace", lambda *args:
        {"python": sys.executable, "mongo_configured": True, "mongo_database": "fictional", "mongo_uri_env": "OOMP_TRACE_MONGO_URI"})
    owners = []
    monkeypatch.setattr(handoff, "validate_trace_owner", lambda actual, python, owner:
        owners.append(owner) or True)
    args = SimpleNamespace(project=str(project), profile="fictional")
    ui = ScriptUI([True, True, True])
    profile = start.wizard(args, store, ui)
    assert owners == ["000000000000000000000001"]
    assert profile.owner_id == owners[0] and profile.context_enabled is True
    assert profile.mode == "read-only" and profile.publication is False
    assert profile.provider is None and profile.extraction.mode == "rules"
    assert profile.namespace == "dedicated"
    secrets = store.environment(profile)
    assert len(secrets) == len(set(secrets.values())) == 2
    assert not any(value in json.dumps(ui.output) for value in secrets.values())


def test_invalid_owner_or_cancelled_setup_leaves_no_profile(tmp_path, monkeypatch, pin):
    from oomp.product import handoff
    project = tmp_path / "trace-project"
    project.mkdir()
    monkeypatch.setattr(start, "_trace_project", lambda *args: project)
    monkeypatch.setattr(handoff, "inspect_trace", lambda *args:
        {"python": "unused", "mongo_configured": True})
    monkeypatch.setattr(handoff, "validate_trace_owner", lambda *args: False)
    store = ProfileStore(tmp_path / "p")
    with pytest.raises(ProductError, match="trace_owner_not_found"):
        start.wizard(SimpleNamespace(project=str(project), profile="fictional"), store, ScriptUI([True]))
    assert not store.home.exists()
    with pytest.raises(ProductError, match="cancelled_no_changes"):
        start.wizard(SimpleNamespace(project=str(project), profile="fictional"), store, ScriptUI([False]))
    assert not store.home.exists()


def test_first_setup_is_remembered_and_second_start_does_not_ask_again(tmp_path, monkeypatch, pin):
    from oomp.product import handoff
    project = tmp_path / "trace-project"
    project.mkdir()
    monkeypatch.setattr(start, "_trace_project", lambda *args: project)
    monkeypatch.setattr(handoff, "inspect_trace", lambda *args:
        {"python": sys.executable, "mongo_configured": True, "mongo_database": "fictional", "mongo_uri_env": "OOMP_TRACE_MONGO_URI"})
    owners = []
    monkeypatch.setattr(handoff, "validate_trace_owner", lambda actual, python, owner:
        owners.append(owner) or True)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    launched = []
    monkeypatch.setattr(start, "launch", lambda store, profile, **kwargs:
        launched.append(profile) or {**running(profile), "context_verified": True, "integration": {"configured": True}})
    args = SimpleNamespace(project=str(project), profile="fictional", home=str(tmp_path/"p"),
        remember=False, replace_default=False, approve_trace_integration=False, json=False)
    assert start.command(args, ScriptUI([True, True, True])) == 0
    store = ProfileStore(args.home)
    secret_path = store.directory("fictional")/"secrets.json"
    before = secret_path.read_bytes()
    assert start.command(SimpleNamespace(**{**vars(args), "profile": None, "home": None}), ScriptUI([])) == 0
    assert owners == ["000000000000000000000001"]
    assert launched[0] == launched[1]
    assert secret_path.read_bytes() == before


def test_start_redacts_unexpected_exception_text(tmp_path, pin, monkeypatch, capsys):
    store, profile = fixture_profile(tmp_path)
    monkeypatch.setattr(start, "launch", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("secret-do-not-log")))
    assert main(["start", "--home", str(store.home), "--profile", profile.name, "--json"]) == 1
    output = capsys.readouterr()
    assert "secret-do-not-log" not in output.out + output.err
    assert "invalid_configuration_or_operation" in output.out
