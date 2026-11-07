"""Explicit managed context opt-in preserves old profile identities and grants."""
import hashlib
import json

import pytest

from oomp.cli import main
from oomp.product.models import Profile
from oomp.product.profiles import ProfileStore
from oomp.product.safety import read_json, write_json
from oomp.understanding.contracts import ExtractionConfiguration


@pytest.mark.parametrize("extraction", [None, ExtractionConfiguration(mode="rules")])
def test_pre_context_profile_load_keeps_generation_identity_and_defaults_disabled(tmp_path, extraction):
    store = ProfileStore(tmp_path / "profiles")
    profile = Profile(name="legacy", database=str(store.directory("legacy") / "memory.sqlite3"), extraction=extraction)
    historical = profile.model_dump(mode="json", exclude={"context_enabled"})
    if extraction is None:
        historical.pop("extraction")
    old_identity = hashlib.sha256(json.dumps(historical, sort_keys=True).encode()).hexdigest()
    assert profile.identity == old_identity
    store.create(profile, create_credentials=True)
    write_json(store.generation(profile) / "profile.json", historical)
    secrets = (store.directory("legacy") / "secrets.json").read_bytes()
    loaded = store.load("legacy")
    assert loaded.identity == old_identity and loaded.context_enabled is None
    assert loaded.server().context_enabled is False
    assert (store.directory("legacy") / "secrets.json").read_bytes() == secrets


def test_managed_context_onboard_enable_preserve_disable_without_changing_grants(tmp_path, capsys):
    home = tmp_path / "profiles"
    common = ["--home", str(home), "--profile", "context-demo", "--plain", "--json"]
    assert main(["onboard", *common, "--context", "--no-mind", "--no-provider", "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["context_enabled"] is True
    assert not home.exists()
    assert main(["onboard", *common, "--context", "--no-mind", "--no-provider",
                 "--yes", "--create-credentials"]) == 0
    capsys.readouterr()
    store = ProfileStore(home)
    enabled = store.load("context-demo")
    assert enabled.context_enabled is True and enabled.server().context_enabled is True
    assert read_json(store.generation(enabled) / "server.json")["context_enabled"] is True
    assert enabled.server().profile == "read-only" and enabled.read_source is False
    assert enabled.server().http_grants[0].capabilities == ("read",)
    before = (store.directory(enabled.name) / "secrets.json").read_bytes()
    grants = enabled.grants()
    assert main(["config", *common, "--port", "18979", "--yes"]) == 0
    capsys.readouterr()
    assert store.load(enabled.name).context_enabled is True
    assert main(["reconfigure", *common, "--no-context", "--yes"]) == 0
    capsys.readouterr()
    disabled = store.load(enabled.name)
    assert disabled.context_enabled is False and disabled.server().context_enabled is False
    assert disabled.grants() == grants and disabled.database == enabled.database
    assert read_json(store.generation(disabled) / "server.json")["context_enabled"] is False
    assert (store.directory(enabled.name) / "secrets.json").read_bytes() == before


def test_context_rejects_non_boolean_profile_values(tmp_path):
    with pytest.raises(ValueError):
        Profile(name="strict", database=str(tmp_path / "memory.sqlite3"), context_enabled="true")
