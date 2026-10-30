"""Synthetic model/fallback accounting and real-worker persistence boundaries.

HTTP fixtures emulate Ollama for regressions; they are not real-model acceptance.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from oomp.mind.handlers import MindHandlers
from oomp.mind.worker import MindWorker
from oomp.storage.memory_store import SQLiteMemoryStore
from oomp.storage.mind_projection_store import SQLiteMindProjectionStore
from oomp.understanding.contracts import ExtractionConfiguration
from oomp.understanding.engine import UnderstandingEngine
from oomp.understanding.providers import OllamaExtractor
from oomp.understanding.rules import RulesExtractor, promotion
from oomp.understanding.transport import ExtractionUnavailable
from test_mind2_acquisition import SCOPE, database, event
from test_mind2_providers_workers import http_fixture


def response(*candidates, **changes):
    return {"model": "synthetic", "done": True,
            "response": json.dumps({"candidates": candidates}), **changes}


def preference(quote):
    return {"quote": quote, "predicate": "preference",
            "memory_category": "procedural", "assertion_kind": "explicit"}


class RecordingHandlers(MindHandlers):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        process = self.understanding.process_event
        def record(*args, **kwargs):
            self.acquisition = process(*args, **kwargs)
            return self.acquisition
        self.understanding.process_event = record

    def execute(self, scope, job):
        counts = super().execute(scope, job)
        self.counts = counts
        return counts


def test_http_model_refinement_is_persisted_by_mind_and_survives_reopen(tmp_path):
    sample = event("Please use numbered setup steps.")
    path = database(tmp_path, sample)
    rules = RulesExtractor().propose(SCOPE, sample)
    assert len(rules) == 1 and promotion(rules[0])[0] == "episodic-only"
    with http_fixture(response(preference(sample.content))) as (endpoint, calls):
        config = ExtractionConfiguration(mode="local-llm", model="synthetic", endpoint=endpoint)
        handlers = RecordingHandlers(path, extraction_configuration=config)
        run = MindWorker(path, SCOPE, handlers=handlers).run_once(max_jobs=1)
    assert run.completed == 1 and run.failed == run.lost_lease == 0
    assert len(calls) == 1
    assert handlers.counts["model_calls"] == handlers.counts["model_proposals"] == 1
    assert handlers.counts["model_accepted"] == handlers.counts["model_refinements"] == 1
    assert handlers.counts["model_rejected"] == handlers.counts["extraction_degraded"] == 0
    reopened = SQLiteMemoryStore(path)
    records = reopened.list_memories(SCOPE).memories
    assert len(records) == 2
    canonical = next(item for item in records if item.memory_type.value == "procedural")
    assert canonical.metadata["verified"] is False
    assert canonical.source_event_ids == (sample.event_id,)
    assert canonical.provenance == (sample.source_reference,)
    with sqlite3.connect(path) as connection:
        evidence = connection.execute(
            "SELECT source_span_json,extraction_method FROM memory_sources WHERE memory_id=?",
            (canonical.memory_id,),
        ).fetchone()
    assert json.loads(evidence[0]) == {"start": 0, "end": len(sample.content), "quote": sample.content}
    assert evidence[1].startswith("mind2.ollama.v1.")
    # Restarting in offline rules mode preserves the model-backed claim and proof.
    assert UnderstandingEngine(path).process_event(SCOPE, sample.event_id).processing.memories_created == 0
    assert SQLiteMemoryStore(path).get(SCOPE, canonical.memory_id) == canonical


def test_mixed_model_proposals_keep_independent_rejection_and_rules_output(tmp_path):
    sample = event("Please use numbered setup steps. The weather is warm.")
    path = database(tmp_path, sample)
    candidates = [preference("Please use numbered setup steps."), preference("The weather is warm.")]
    with http_fixture(response(*candidates)) as (endpoint, _):
        config = ExtractionConfiguration(mode="local-llm", model="synthetic", endpoint=endpoint)
        result = UnderstandingEngine(path, config).process_event(SCOPE, sample.event_id)
    assert result.model_proposals == 2 and result.model_accepted == result.model_rejected == 1
    assert result.model_refinements == 1 and result.degraded
    assert result.code == "model_candidates_rejected"
    records = SQLiteMemoryStore(path).list_memories(SCOPE).memories
    assert len(records) == 3
    assert sum(item.memory_type.value == "procedural" for item in records) == 1
    assert sum(item.memory_type.value == "episodic" for item in records) == 2


@pytest.mark.parametrize("code", ["extraction_provider_timeout", "extraction_provider_unavailable"])
def test_current_transport_failure_preserves_fallback_without_stale_success(tmp_path, monkeypatch, code):
    import oomp.understanding.providers as module
    sample = event("I prefer tea.")
    path = database(tmp_path, sample)
    config = ExtractionConfiguration(mode="local-llm", model="synthetic")
    provider = OllamaExtractor(config)
    provider.last_code = "extraction_completed"
    def unavailable(*args, **kwargs):
        raise ExtractionUnavailable(code)
    monkeypatch.setattr(module, "request_json", unavailable)
    result = UnderstandingEngine(path, config, provider=provider).process_event(SCOPE, sample.event_id)
    assert result.code == code and result.degraded
    assert result.model_calls == 1
    assert result.model_proposals == result.model_accepted == result.model_refinements == 0
    assert result.processing.memories_created == 2


def test_empty_model_output_is_never_counted_as_model_acceptance(tmp_path):
    sample = event("I prefer tea.")
    path = database(tmp_path, sample)
    with http_fixture(response()) as (endpoint, _):
        config = ExtractionConfiguration(mode="local-llm", model="synthetic", endpoint=endpoint)
        result = UnderstandingEngine(path, config).process_event(SCOPE, sample.event_id)
    assert result.model_calls == 1
    assert result.degraded and result.code == "extraction_no_candidates"
    assert result.model_proposals == result.model_accepted == result.model_rejected == result.model_refinements == 0
    assert result.processing.memories_created == 2


def test_retraction_during_inference_blocks_valid_model_refinement(tmp_path, monkeypatch):
    import oomp.understanding.providers as module
    sample = event("Please use numbered setup steps.")
    path = database(tmp_path, sample)
    initial = UnderstandingEngine(path).process_event(SCOPE, sample.event_id)
    before = SQLiteMemoryStore(path).list_memories(SCOPE).memories
    assert len(before) == 1 and before[0].memory_type.value == "episodic"
    def retract_during_generation(*args, **kwargs):
        # A separate write here also proves inference holds no SQLite transaction.
        SQLiteMindProjectionStore(path).retract_source(SCOPE, initial.processing.memory_ids[0], sample.event_id)
        return response(preference(sample.content))
    monkeypatch.setattr(module, "request_json", retract_during_generation)
    config = ExtractionConfiguration(mode="local-llm", model="synthetic")
    handlers = RecordingHandlers(path, extraction_configuration=config)
    run = MindWorker(path, SCOPE, handlers=handlers).run_once(max_jobs=1)
    assert run.completed == 1 and run.failed == run.lost_lease == 0
    assert handlers.counts["model_accepted"] == 1
    assert handlers.counts["memories_created"] == handlers.counts["evidence_links_added"] == 0
    assert handlers.acquisition.code == "source_retracted"
    assert SQLiteMemoryStore(path).list_memories(SCOPE).memories == before


@pytest.mark.parametrize("raw,done_reason,code", [
    ('{"candidates":[', "stop", "extraction_candidates_invalid"),
    ('{"candidates":"invalid"}', "stop", "extraction_candidates_invalid"),
    ('{"candidates":[]}', "length", "extraction_output_truncated"),
    ('{"candidates":[', "length", "extraction_output_truncated"),
])
def test_wire_failure_reason_distinguishes_truncation_and_invalid_candidates(tmp_path, raw, done_reason, code):
    sample = event("I prefer tea.")
    path = database(tmp_path, sample)
    with http_fixture(response(response=raw, done_reason=done_reason)) as (endpoint, _):
        config = ExtractionConfiguration(mode="local-llm", model="synthetic", endpoint=endpoint)
        result = UnderstandingEngine(path, config).process_event(SCOPE, sample.event_id)
    assert result.code == code and result.degraded
    assert result.model_calls == 1
    assert result.model_proposals == result.model_accepted == result.model_refinements == 0
    assert result.processing.memories_created == 2


def test_model_metrics_are_bounded_numeric_and_reset_on_current_preflight(monkeypatch):
    import oomp.understanding.providers as module
    config = ExtractionConfiguration(mode="local-llm", model="synthetic")
    provider = OllamaExtractor(config)
    sample = event("Please use numbered setup steps.")
    document = response(preference(sample.content), total_duration=1_000_000_000,
                        load_duration=200_000_000, prompt_eval_count=12,
                        prompt_eval_duration=100_000_000, eval_count=30,
                        eval_duration=700_000_000, context=[99],
                        hidden_private_output="must never become diagnostics")
    monkeypatch.setattr(module, "request_json", lambda *args, **kwargs: document)
    assert len(provider.propose(SCOPE, sample)) == 1
    assert provider.last_metrics and provider.last_metrics["elapsed_seconds"] >= 0
    assert all(type(value) in (int, float) for value in provider.last_metrics.values())
    assert "must never" not in repr(provider.last_metrics)
    assert "context" not in provider.last_metrics and "hidden_private_output" not in provider.last_metrics
    with pytest.raises(ExtractionUnavailable, match="secret_like_source_excluded"):
        provider.propose(SCOPE, event("My API key is sk-synthetic-only-123456789."))
    assert provider.last_metrics == {}
    assert provider.last_code == "secret_like_source_excluded"


def test_preflight_budget_does_not_count_as_inference_or_open_circuit(monkeypatch):
    import oomp.understanding.providers as module
    provider = OllamaExtractor(ExtractionConfiguration(mode="local-llm", model="synthetic"))
    sample = event("Please use numbered setup steps.")
    calls = []
    def generate(*args, **kwargs):
        calls.append(1)
        return response(preference(sample.content))
    monkeypatch.setattr(module, "request_json", generate)
    provider.calls = 999
    assert len(provider.propose(SCOPE, sample)) == 1
    for _ in range(4):
        with pytest.raises(ExtractionUnavailable, match="extraction_call_budget_exhausted"):
            provider.propose(SCOPE, sample)
        assert provider.last_code == "extraction_call_budget_exhausted"
        assert provider.last_metrics == {}
    assert provider.calls == 1000 and len(calls) == 1
    assert provider.failures == 0 and provider.open_until == 0


def test_busy_provider_falls_back_without_an_extra_call(tmp_path):
    sample = event("I prefer tea.")
    path = database(tmp_path, sample)
    config = ExtractionConfiguration(mode="local-llm", model="synthetic")
    provider = OllamaExtractor(config)
    assert provider._lock.acquire(blocking=False)
    try:
        result = UnderstandingEngine(path, config, provider=provider).process_event(SCOPE, sample.event_id)
    finally:
        provider._lock.release()
    assert result.degraded and result.code == "extraction_concurrency_limit"
    assert result.model_calls == provider.calls == 0
    assert result.model_proposals == result.model_accepted == 0
    assert result.processing.memories_created == 2


def test_failed_call_discards_prior_generation_metrics(monkeypatch):
    import oomp.understanding.providers as module
    config = ExtractionConfiguration(mode="local-llm", model="synthetic")
    provider = OllamaExtractor(config)
    sample = event("Please use numbered setup steps.")
    monkeypatch.setattr(module, "request_json", lambda *args, **kwargs:
                        response(preference(sample.content), eval_count=50, eval_duration=1_000_000_000))
    assert len(provider.propose(SCOPE, sample)) == 1
    def timeout(*args, **kwargs):
        raise ExtractionUnavailable("extraction_provider_timeout")
    monkeypatch.setattr(module, "request_json", timeout)
    with pytest.raises(ExtractionUnavailable, match="extraction_provider_timeout"):
        provider.propose(SCOPE, sample)
    assert provider.last_code == "extraction_provider_timeout"
    assert set(provider.last_metrics) == {"elapsed_seconds"}
    assert provider.last_metrics["elapsed_seconds"] >= 0
