"""Frozen denominators and honest scoring, including errors and negatives."""
from __future__ import annotations

import pytest

from benchmarks.mind2.run import load_corpus, _score


def test_corpus_is_frozen_varied_multiturn_and_explicitly_unreviewed():
    corpus, manifest = load_corpus()
    assert len(corpus["sessions"]) == 30
    labels = [l for s in corpus["sessions"] for e in s["events"] for l in e["labels"]]
    assert len(labels) == 247 and len({l["opportunity_id"] for l in labels}) == 247
    assert manifest["opportunities"] == len(labels) and len(manifest["files"]) == 2
    assert all(len(s["events"]) == 8 for s in corpus["sessions"])
    assert all(l["annotation_author"] == "Codex" for l in labels)
    assert all(l["review_status"] == "draft-pending-independent-human-review" for l in labels)
    assert len({s["theme"] for s in corpus["sessions"]}) == 30
    assert any(e.get("replay_of") is not None for s in corpus["sessions"] for e in s["events"])
    assert any(e.get("foreign_scope") for s in corpus["sessions"] for e in s["events"])
    assert any(e.get("retracted") for s in corpus["sessions"] for e in s["events"])


def test_failed_and_excluded_opportunities_are_not_removed_from_denominators():
    corpus, _ = load_corpus()
    rows = [{"theme": session["theme"], "labels": item["labels"], "predictions": []}
        for session in corpus["sessions"] for item in session["events"]]
    report = _score(rows)
    expected = sum(l["useful_candidate"] for r in rows for l in r["labels"])
    excluded = sum(not l["useful_candidate"] for r in rows for l in r["labels"])
    assert report["false_negatives"] == expected and report["true_negatives"] == excluded
    assert report["candidate_recall"] == report["candidate_precision"] == 0
    assert report["accepted_provenance_rate"] is None
    assert report["useful_episode_coverage"] == 0


def test_mistyped_candidate_counts_both_false_positive_and_false_negative():
    corpus, _ = load_corpus()
    label = corpus["sessions"][0]["events"][0]["labels"][0]
    prediction = {"start": label["start"], "end": label["end"], "quote": label["quote"],
        "predicate": "alias", "category": "profile", "assertion": "explicit", "retention": "canonical",
        "role": "user", "episodic": False, "provenance_ok": True}
    score = _score([{"theme": "synthetic", "labels": [label], "predictions": [prediction]}])
    assert score["true_positives"] == 0 and score["false_positives"] == score["false_negatives"] == 1


def test_benchmark_records_current_degradation_code_instead_of_stale_provider_state(tmp_path):
    from benchmarks.mind2.run import RecordingHandlers
    from oomp.mind.worker import MindWorker
    from oomp.understanding.contracts import ExtractionConfiguration
    from oomp.understanding.transport import ExtractionUnavailable
    from test_mind2_acquisition import SCOPE, event, database
    sample = event("I prefer tea.")
    path = database(tmp_path, sample)
    class CircuitOpen:
        last_code = "stale_status"
        def propose(self, *_):
            raise ExtractionUnavailable("extraction_circuit_open")
    handlers = RecordingHandlers(path, extraction_configuration=ExtractionConfiguration(), extraction_provider=CircuitOpen())
    assert MindWorker(path, SCOPE, handlers=handlers).run_once(max_jobs=1).completed == 1
    assert handlers.observations[0]["code"] == "extraction_circuit_open"
