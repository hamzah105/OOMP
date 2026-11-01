"""Frozen P4A source scoring and real three-session storage acceptance."""
from __future__ import annotations

from contextlib import closing
import json
import sqlite3

import pytest

from benchmarks.context.runner import (
    build_synthetic, load_frozen, normalize_result, score_record, source_data_fingerprint,
)
from oomp.context.contracts import ContextRequest
from oomp.context.engine import ContextEngine


def test_frozen_context_preregistration_has_independent_gold_and_negative_controls():
    fixture, policy, setup, manifest, hashes = load_frozen()
    assert len(fixture["turns"]) == manifest["owned_source_events"] == 15
    assert len(policy["queries"]) == manifest["queries"] == 12
    assert len(fixture["foreign_turns"]) == 2
    assert set(hashes) == {"manifest", "three-session.json", "preregistration.json", "setup-policy.json"}
    pet = next(query for query in policy["queries"] if query["id"] == "pet")
    assert pet["abstain"] and not pet["allowed_source_event_ids"]
    assert setup["extraction"]["sensitive_episodes"] is True
    assert setup["extraction"]["mode"] == "rules"
    assert "fictional" in setup["extraction"]["sensitivity_consent"]
    assert policy["budgets"] == {"primary": 6000, "constrained": 1200, "tiny_exclusion": 1}


def test_source_metrics_deduplicate_paths_and_count_irrelevant_evidence():
    query = {
        "id": "moving", "required_source_event_ids": ["a", "b"],
        "allowed_source_event_ids": ["a", "b"], "abstain": False,
        "expected_intent_category": "episodic_recall",
    }
    result = score_record(query, {
        "source_event_ids": ["a", "a", "foreign"], "invalid_source_proofs": 0,
        "retrieval_status": "found_relevant_evidence",
    })
    assert result["source_recall_at_budget"] == .5
    assert result["source_recall_at_k"] == .5
    assert result["evidence_precision"] == .5
    assert result["returned_distinct_sources"] == 2
    assert result["false_positive_sources"] == 1


def test_failed_query_cannot_receive_abstention_or_provenance_credit():
    query = {
        "id": "pet", "required_source_event_ids": [], "allowed_source_event_ids": [],
        "abstain": True, "expected_intent_category": "missing_information",
    }
    result = score_record(query, {
        "source_event_ids": [], "invalid_source_proofs": 0,
        "retrieval_status": "unavailable", "operation_failed": True,
    })
    assert result["correct_abstention"] == result["provenance_fidelity"] == 0
    assert result["source_recall_at_budget"] is None


@pytest.fixture(scope="module")
def three_session(tmp_path_factory):
    fixture, policy, setup, _, _ = load_frozen()
    path = tmp_path_factory.mktemp("c4") / "s.sqlite3"
    return path, build_synthetic(path, fixture, policy, setup)


def _request(scope, query, **changes):
    return ContextRequest(tenant_id=scope.tenant_id, namespace=scope.namespace, query=query,
                          token_budget=6000, **changes)


def test_real_mind_projection_context_proofs_and_reopen(three_session):
    path, case = three_session
    scope = case["scope"]
    before = source_data_fingerprint(path)
    assert case["schema_version"] == 6
    assert all(run["failed"] == run["retried"] == run["lost_lease"] == 0 for run in case["worker_runs"])
    request = _request(scope, "What response style do I prefer?")
    first = ContextEngine(path).retrieve(scope, request)
    normalized = normalize_result(path, first, scope, case["events"])
    assert "p4a-style" in normalized["source_event_ids"]
    assert normalized["invalid_source_proofs"] == 0
    assert not normalized["cross_scope_sources"]
    assert not normalized["duplicate_original_source_spans"]
    assert first.selected_context_bytes == len(first.context_packet.encode("utf-8")) <= 6000
    reopened = ContextEngine(path).retrieve(scope, request)
    assert reopened.evidence_packets == first.evidence_packets
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
    assert source_data_fingerprint(path) == before


def test_unknown_pet_and_foreign_principal_cannot_borrow_source(three_session):
    path, case = three_session
    scope = case["scope"]
    result = ContextEngine(path).retrieve(scope, _request(scope, "What is my pet's name?"))
    assert result.evidence_packets == ()
    assert result.retrieval_status in {"no_relevant_evidence", "candidate_uncertain"}
    different = scope.model_copy(update={"principal_id": "unlinked-principal"})
    rejected = ContextEngine(path).retrieve(different, _request(different, "What response style do I prefer?"))
    assert rejected.evidence_packets == ()


def test_tiny_budget_is_disclosed_exclusion_with_no_partial_claim(three_session):
    path, case = three_session
    scope = case["scope"]
    request = _request(scope, "What response style do I prefer?").model_copy(update={"token_budget": 1})
    result = ContextEngine(path).retrieve(scope, request)
    assert result.evidence_packets == () and result.context_packet == ""
    assert result.selected_context_bytes == 0
    assert result.retrieval_status == "budget_excluded"
