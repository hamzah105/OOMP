"""The explicit local-model demo must distinguish model evidence from fallback."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def _example():
    path = Path(__file__).resolve().parents[1] / "examples" / "mind2_model_acceptance.py"
    spec = importlib.util.spec_from_file_location("mind2_public_model_example", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("has_candidate", [True, False])
def test_model_demo_requires_incremental_persisted_model_evidence(tmp_path, monkeypatch, has_candidate):
    import oomp.understanding.providers as providers
    import oomp.understanding.transport as transport

    requests = []

    def synthetic_http(endpoint, path, **kwargs):
        requests.append(path)
        assert endpoint == "http://127.0.0.1:11434"
        if path == "/api/version":
            return {"version": "synthetic-version"}
        if path == "/api/tags":
            return {"models": [{"name": "synthetic", "digest": "a" * 64,
                                 "size": 123, "details": {"quantization_level": "synthetic"}}]}
        assert path == "/api/generate"
        candidates = [{"quote": "Please use numbered setup steps.", "predicate": "preference",
                       "memory_category": "procedural", "assertion_kind": "explicit"}]
        return {"model": "synthetic", "done": True, "done_reason": "stop",
                "response": json.dumps({"candidates": candidates if has_candidate else []}),
                "eval_count": 25, "eval_duration": 100_000_000}

    monkeypatch.setattr(transport, "request_json", synthetic_http)
    monkeypatch.setattr(providers, "request_json", synthetic_http)
    directory = tmp_path / "new model example"
    report = _example().run(directory, model="synthetic", cases=["procedure"])
    assert requests == ["/api/version", "/api/tags", "/api/generate"]
    assert report["acceptance"] is has_candidate
    assert report["model"]["model_accepted"] == int(has_candidate)
    assert report["model"]["model_refinements"] == int(has_candidate)
    assert report["incremental_model_proofs"] == int(has_candidate)
    assert report["model"]["model_calls"] == 1
    assert report["rules"]["model_calls"] == 0
    assert report["rules"]["canonical_ids"] == []
    assert report["model"]["restart_verified"] is True
    assert report["rules"]["restart_verified"] is True
    assert report["source_events"] == 1
    assert report["ollama"]["digest"] == "a" * 64
    assert report == json.loads((directory / "acceptance.json").read_text(encoding="utf-8"))
    assert report["model_downloads"] == 0
    assert report["existing_private_storage_used"] is report["services_started"] is False


def test_model_demo_refuses_existing_storage_before_any_provider_access(tmp_path, monkeypatch, capsys):
    import oomp.understanding.transport as transport

    def forbidden(*args, **kwargs):
        raise AssertionError("existing output must be rejected before network access")

    monkeypatch.setattr(transport, "request_json", forbidden)
    directory = tmp_path / "existing private-looking directory"
    directory.mkdir()
    sentinel = directory / "do-not-read.txt"
    sentinel.write_text("untouched", encoding="utf-8")
    result = _example().main(["--directory", str(directory), "--model", "synthetic"])
    assert result == 1
    assert json.loads(capsys.readouterr().out) == {"acceptance": False, "code": "new_directory_required"}
    assert sentinel.read_text(encoding="utf-8") == "untouched"
    assert tuple(directory.iterdir()) == (sentinel,)


def test_model_demo_records_unavailable_service_without_attempting_model_generation(tmp_path, monkeypatch):
    import oomp.understanding.transport as transport

    def unavailable(*args, **kwargs):
        raise transport.ExtractionUnavailable("extraction_provider_unavailable")

    monkeypatch.setattr(transport, "request_json", unavailable)
    directory = tmp_path / "new unavailable example"
    report = _example().run(directory, model="synthetic")
    assert report["acceptance"] is False
    assert report["code"] == "extraction_provider_unavailable"
    assert "model" not in report
    assert tuple(path.name for path in directory.iterdir()) == ("acceptance.json",)


@pytest.mark.parametrize("has_candidate", [True, False])
def test_explicit_warmup_is_empty_separate_and_cannot_supply_acceptance(tmp_path, monkeypatch, has_candidate):
    import oomp.understanding.providers as providers
    import oomp.understanding.transport as transport

    calls = []
    candidate = {"quote": "Please use numbered setup steps.", "predicate": "preference",
                 "memory_category": "procedural", "assertion_kind": "explicit"}

    def synthetic_http(endpoint, path, **kwargs):
        calls.append((path, kwargs))
        assert endpoint == "http://127.0.0.1:11434"
        if path == "/api/version":
            return {"version": "synthetic-version"}
        if path == "/api/tags":
            return {"models": [{"name": "synthetic", "digest": "a" * 64}]}
        assert path == "/api/generate"
        is_warmup = kwargs["payload"]["prompt"] == ""
        # Even a candidate-shaped load reply is not an extraction proposal.
        candidates = [candidate] if is_warmup or has_candidate else []
        return {"model": "synthetic", "done": True, "done_reason": "stop",
                "response": json.dumps({"candidates": candidates}),
                "eval_count": 999 if is_warmup else 25,
                "eval_duration": 100_000_000, "private_output": "excluded from metrics"}

    monkeypatch.setattr(transport, "request_json", synthetic_http)
    monkeypatch.setattr(providers, "request_json", synthetic_http)
    report = _example().run(tmp_path / "new warmup example", model="synthetic",
                            cases=["procedure"], timeout=1, warmup_timeout=180)
    assert [path for path, _ in calls] == ["/api/version", "/api/tags", "/api/generate", "/api/generate"]
    warmup = calls[2][1]
    assert warmup["timeout"] == 180
    assert warmup["payload"] == {"model": "synthetic", "prompt": "", "stream": False,
        "keep_alive": "30s", "options": {"num_ctx": 4096, "num_thread": 2, "num_predict": 1}}
    assert calls[3][1]["timeout"] == report["configuration"]["timeout_seconds"] == 1
    assert report["warmup"]["code"] == "model_load_completed"
    assert report["warmup"]["timeout_seconds"] == 180
    assert report["warmup"]["metrics"]["eval_count"] == 999
    assert "private_output" not in report["warmup"]["metrics"]
    assert report["model"]["model_calls"] == 1
    assert report["model"]["model_proposals"] == report["model"]["model_accepted"] == int(has_candidate)
    assert report["model"]["events"][0]["inference_metrics"]["eval_count"] == 25
    assert report["incremental_model_proofs"] == int(has_candidate)
    assert report["acceptance"] is has_candidate


@pytest.mark.parametrize("timeout", [0, 181, True, 1.5])
def test_warmup_bound_is_explicit_and_checked_before_any_provider_call(tmp_path, monkeypatch, timeout):
    import oomp.understanding.transport as transport

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid warmup budget must not contact a provider")

    monkeypatch.setattr(transport, "request_json", forbidden)
    with pytest.raises(ValueError, match="warmup_timeout_must_be_1_to_180_seconds"):
        _example().run(tmp_path / "invalid warmup budget", model="synthetic", warmup_timeout=timeout)


def test_accepted_model_duplicate_of_rules_is_not_incremental_acceptance(tmp_path, monkeypatch):
    import oomp.understanding.providers as providers
    import oomp.understanding.transport as transport

    def synthetic_http(endpoint, path, **kwargs):
        if path == "/api/version":
            return {"version": "synthetic-version"}
        if path == "/api/tags":
            return {"models": [{"name": "synthetic", "digest": "a" * 64}]}
        assert path == "/api/generate"
        return {"model": "synthetic", "done": True, "done_reason": "stop",
                "response": json.dumps({"candidates": [{"quote": "I prefer tea.",
                    "predicate": "preference", "memory_category": "profile", "assertion_kind": "explicit"}]})}

    monkeypatch.setattr(transport, "request_json", synthetic_http)
    monkeypatch.setattr(providers, "request_json", synthetic_http)
    report = _example().run(tmp_path / "new duplicate example", model="synthetic", cases=["preference"])
    assert report["model"]["model_calls"] == 1
    assert report["model"]["model_proposals"] == report["model"]["model_accepted"] == 1
    assert report["model"]["model_rejected"] == report["model"]["model_refinements"] == 0
    assert report["model_persisted_proofs"] == 0  # Equal-rank rules proposal keeps its original proof method.
    assert report["incremental_canonical_ids"] == []
    assert report["incremental_model_proofs"] == 0
    assert report["acceptance"] is False
    assert report["code"] == "model_incremental_acceptance_failed"
