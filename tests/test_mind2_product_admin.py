"""P1 profile compatibility and explicit, bounded P2 administration."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from oomp.cli import main
from oomp.mind.worker import MindWorker
from oomp.product.models import Profile
from oomp.product.profiles import ProfileStore
from oomp.product.safety import read_json, write_json
from oomp.storage.memory_store import SQLiteMemoryStore
from oomp.storage.mind_store import SQLiteMindStore
from oomp.understanding.admin import reprocess, episodes
from oomp.understanding.contracts import ExtractionConfiguration
from oomp.understanding.engine import UnderstandingEngine
from test_mind2_acquisition import SCOPE, event, database


def test_genuine_pre_p2_profile_keeps_its_generation_identity_and_secrets(tmp_path):
    store = ProfileStore(tmp_path / "profiles")
    profile = Profile(name="legacy", database=str(store.directory("legacy") / "memory.sqlite3"))
    original = profile.model_dump(mode="json", exclude={"extraction"})
    legacy_identity = hashlib.sha256(json.dumps(original, sort_keys=True).encode()).hexdigest()
    assert profile.identity == legacy_identity
    store.create(profile, create_credentials=True)
    write_json(store.generation(profile) / "profile.json", original)
    secrets = (store.directory("legacy") / "secrets.json").read_bytes()
    assert store.load("legacy").identity == legacy_identity
    assert main(["config", "--home", str(store.home), "--profile", "legacy",
                 "--extraction-mode", "rules", "--yes", "--json"]) == 0
    changed = store.load("legacy")
    assert changed.extraction.mode == "rules"
    assert (store.directory("legacy") / "secrets.json").read_bytes() == secrets
    assert Path(changed.database) == Path(profile.database)
    assert read_json(store.generation(profile) / "profile.json") == original


def test_new_onboard_previews_rules_separately_from_embeddings_without_io(tmp_path, capsys):
    home = tmp_path / "absent"
    assert main(["onboard", "--home", str(home), "--dry-run", "--json"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["extraction"]["mode"] == "rules" and plan["extraction_route"] == "offline"
    assert not home.exists()
    assert main(["onboard", "--home", str(home), "--dry-run", "--json",
                 "--extraction-mode", "local-llm", "--extraction-model", "synthetic-generation"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["extraction"]["model"] == "synthetic-generation"
    assert plan["extraction_route"] == "explicit literal-loopback only" and not home.exists()


def test_reprocess_preview_consent_digest_and_idempotent_queue_only(tmp_path):
    first, second = event("I prefer concise replies.", "one"), event("My name is Synthetic Example.", "two")
    path = database(tmp_path, first, second)
    config = ExtractionConfiguration()
    before = SQLiteMindStore(path).status(SCOPE)
    plan = reprocess(path, SCOPE, ["one", "two"], config)
    assert plan["eligible_event_ids"] == ["one", "two"] and plan["jobs_started"] is False
    assert SQLiteMindStore(path).status(SCOPE) == before
    assert not SQLiteMemoryStore(path).list_memories(SCOPE).memories
    with pytest.raises(ValueError, match="consent_and_preview"):
        reprocess(path, SCOPE, ["one", "two"], config, apply=True, plan_digest=plan["plan_digest"])
    with pytest.raises(ValueError, match="plan_changed"):
        reprocess(path, SCOPE, ["two"], config, apply=True, consented=True, plan_digest=plan["plan_digest"])
    applied = reprocess(path, SCOPE, ["one", "two"], config, apply=True, consented=True, plan_digest=plan["plan_digest"])
    again = reprocess(path, SCOPE, ["one", "two"], config, apply=True, consented=True, plan_digest=plan["plan_digest"])
    assert applied["job_ids"] == again["job_ids"]
    assert len(SQLiteMindStore(path).list_jobs(SCOPE)) == 2
    assert not SQLiteMemoryStore(path).list_memories(SCOPE).memories
    worker = MindWorker(path, SCOPE, extraction_configuration=config)
    assert worker.run_once(max_jobs=8).failed == 0
    assert SQLiteMemoryStore(path).list_memories(SCOPE).memories


def test_reprocess_is_atomic_on_capacity_and_config_is_pinned(tmp_path):
    samples = [event("I like short replies.", f"event-{i}") for i in range(5)]
    path = database(tmp_path, *samples)
    config = ExtractionConfiguration()
    ids = [e.event_id for e in samples]
    plan = reprocess(path, SCOPE, ids, config)
    from oomp.storage.mind_store import QueueCapacityError
    # Force the normal scoped queue capacity down; every enqueue shares one tx.
    from unittest.mock import patch
    with patch.object(SQLiteMindStore, "_active_count", return_value=1000):
        with pytest.raises(QueueCapacityError):
            reprocess(path, SCOPE, ids, config, apply=True, consented=True, plan_digest=plan["plan_digest"])
    assert not SQLiteMindStore(path).list_jobs(SCOPE)
    reprocess(path, SCOPE, ids[:1], config, apply=True, consented=True,
        plan_digest=reprocess(path, SCOPE, ids[:1], config)["plan_digest"])
    worker = MindWorker(path, SCOPE, extraction_configuration=ExtractionConfiguration(retain_episodes=False))
    result = worker.run_once(max_jobs=1, dispatch_limit=1)
    assert result.failed == 1
    assert not SQLiteMemoryStore(path).list_memories(SCOPE).memories


def test_episode_inspection_is_redacted_by_default_and_sensitive_opt_in_is_topic_only(tmp_path):
    sample = event("Suppose I became prime minister one day.", "sensitive")
    path = database(tmp_path, sample)
    assert UnderstandingEngine(path).process_event(SCOPE, sample.event_id).processing.memory_ids == ()
    config = ExtractionConfiguration(sensitive_episodes=True)
    UnderstandingEngine(path, config).process_event(SCOPE, sample.event_id)
    redacted = episodes(path, SCOPE)
    assert len(redacted) == 1 and "content" not in redacted[0] and "source_event_ids" not in redacted[0]
    detail = episodes(path, SCOPE, show_content=True)
    assert "hypothetical; episodic-only" in detail[0]["content"]
    assert all(m.memory_type.value == "episodic" for m in SQLiteMemoryStore(path).list_memories(SCOPE).memories)


def test_reprocess_excludes_retracted_and_secret_sources_and_enforces_bounds(tmp_path):
    sample = event("I prefer tea.", "normal")
    secret = event("My API key is sk-synthetic-secret-only.", "secret")
    path = database(tmp_path, sample, secret)
    result = UnderstandingEngine(path).process_event(SCOPE, sample.event_id)
    from oomp.storage.mind_projection_store import SQLiteMindProjectionStore
    SQLiteMindProjectionStore(path).retract_source(SCOPE, result.processing.memory_ids[0], sample.event_id)
    plan = reprocess(path, SCOPE, ["normal", "secret"], ExtractionConfiguration())
    assert not plan["eligible_event_ids"]
    assert {e["code"] for e in plan["excluded"]} == {"source_retracted", "secret_like_source_excluded"}
    for selection in ([], ["normal"] * 101, ["normal", "normal"]):
        with pytest.raises(ValueError):
            reprocess(path, SCOPE, selection, ExtractionConfiguration())


def test_understand_cli_requires_preview_and_has_no_storage_default(tmp_path, capsys):
    sample = event("I prefer tea.")
    path = database(tmp_path, sample)
    args = ["understand", "reprocess", "--db", str(path), "--tenant", SCOPE.tenant_id,
            "--namespace", SCOPE.namespace, "--principal", SCOPE.principal_id, "--event-id", sample.event_id]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["selected_count"] == 1
    assert main([*args, "--apply", "--consented"]) == 1
    assert not SQLiteMindStore(path).list_jobs(SCOPE)
