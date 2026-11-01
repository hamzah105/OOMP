"""P4 whole-evidence budgets and cooperative stop paths; synthetic data only."""
from datetime import datetime, timezone
from itertools import count
import json

import pytest

from oomp.context.contracts import ContextEvidence, ContextRequest, ContextSource
from oomp.context.engine import ContextEngine
from oomp.context.packing import pack_units, source_keys
from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
from oomp.objects.service import ObjectMap
from oomp.storage.retrieval_store import SQLiteRetrievalStore
from oomp.storage.sqlite import SQLiteEventStore
from oomp.understanding.engine import UnderstandingEngine

OWNER = AuthorizedScope(tenant_id="p4-budget", namespace="synthetic", principal_id="owner")
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_store(path, content="I prefer concise technical explanations."):
    event = MemoryEvent(event_id="budget-source", tenant_id=OWNER.tenant_id, namespace=OWNER.namespace,
        event_type="user_message", source_type="user", content=content, occurred_at=NOW, ingested_at=NOW,
        metadata={"ingested_by": OWNER.principal_id},
        source_reference=SourceReference(source_system="synthetic-budget", external_event_id="budget-source",
            timestamp=NOW, session_id="budget-session", turn_id="budget-source"))
    store = SQLiteEventStore(path)
    store.initialize()
    store.append(OWNER, event)
    UnderstandingEngine(path).process_event(OWNER, event.event_id)
    ObjectMap(path).build(OWNER, limit=100)
    return event


def request(query="What response style do I prefer?", **values):
    return ContextRequest(tenant_id=OWNER.tenant_id, namespace=OWNER.namespace, query=query, **values)


def unit(content="I decided not to relocate.", *, key="one", event_id="source-one", original=None, resolution="canonical_fact"):
    original = content if original is None else original
    proof = ContextSource(memory_id="memory-"+key, event_id=event_id, span_start=0, span_end=len(original),
        source_reference=SourceReference(source_system="synthetic-pack", external_event_id=event_id, timestamp=NOW))
    return ContextEvidence(unit_id="unit-"+key, resolution=resolution, content=content,
        memory_ids=(proof.memory_id,), source_proofs=(proof,), assertion_kinds=("explicit",),
        temporal_status="current_reported", uncertain=False,
        derived=resolution in {"object_snapshot", "episode_summary"})


def test_one_byte_packet_budget_omits_whole_claim_and_negation():
    claim = unit()
    packed = pack_units((claim,), 1, 8)
    assert packed.evidence_packets == () and packed.context_packet == ""
    assert packed.selected_context_bytes == 0 and packed.dropped == 1
    larger = pack_units((claim,), 12000, 8)
    assert larger.evidence_packets == (claim,)
    assert json.loads(larger.context_packet)["evidence_packets"][0]["content"] == "I decided not to relocate."


def test_utf8_accounting_includes_unicode_proofs_and_wrapper():
    claim = unit("I prefer café examples in 日本語. 🙂")
    packed = pack_units((claim,), 12000, 8)
    parsed = json.loads(packed.context_packet)
    assert packed.selected_context_bytes == len(packed.context_packet.encode("utf-8")) > len(packed.context_packet)
    assert parsed["selected_context_bytes"] == packed.selected_context_bytes
    assert parsed["token_budget"] == 12000
    assert parsed["counting_method"] == "utf8_bytes_upper_bound_v1"
    assert parsed["evidence_packets"][0]["content"] == claim.content
    assert packed.selected_context_bytes > len(claim.content.encode("utf-8"))


def test_same_original_span_is_not_counted_again_through_another_object_path():
    first = unit()
    alias = unit(key="another-memory")
    packed = pack_units((first, alias), 12000, 8)
    assert packed.evidence_packets == (first,)
    assert len(set().union(*(source_keys(value) for value in packed.evidence_packets))) == 1


def test_expansion_replaces_coarse_unit_only_when_complete_detail_fits():
    original = "I decided not to relocate. " + "More attributed context. " * 100
    coarse = unit("Relocation discussion snapshot.", original=original, resolution="object_snapshot")
    detail = unit(original, resolution="source_evidence")
    wide = pack_units((coarse,), 12000, 8, upgrades=(detail,))
    assert wide.evidence_packets == (detail,) and wide.expanded == 1
    assert source_keys(wide.evidence_packets[0]) == source_keys(coarse)
    initial = pack_units((coarse,), 12000, 8)
    narrow = pack_units((coarse,), initial.selected_context_bytes+20, 8, upgrades=(detail,))
    assert narrow.evidence_packets == (coarse,) and narrow.expanded == 0
    assert json.loads(narrow.context_packet)["evidence_packets"][0]["content"] == coarse.content


@pytest.mark.parametrize("budget,limit", [(0, 8), (32769, 8), (True, 8), (1200, 0), (1200, 21), (1200, True)])
def test_packer_rejects_invalid_hard_limits(budget, limit):
    with pytest.raises(ValueError):
        pack_units((unit(),), budget, limit)


def test_eligible_evidence_too_large_for_budget_is_not_reported_as_no_match(tmp_path):
    path = tmp_path / "tiny.sqlite3"
    make_store(path)
    response = ContextEngine(path).retrieve(OWNER, request(token_budget=1))
    assert response.retrieval_status.value == "budget_excluded"
    assert response.evidence_packets == () and response.context_packet == ""
    assert response.selected_context_bytes == 0


def test_engine_quote_detail_is_explicit_and_preserves_exact_original_span(tmp_path):
    path = tmp_path / "quotes.sqlite3"
    event = make_store(path, "I prefer concise technical explanations with café examples.")
    engine = ContextEngine(path)
    default = engine.retrieve(OWNER, request(token_budget=12000))
    explicit = engine.retrieve(OWNER, request(token_budget=12000, include_source_content=True))
    assert default.evidence_packets and explicit.evidence_packets
    assert all(proof.quote is None for value in default.evidence_packets for proof in value.source_proofs)
    for value in explicit.evidence_packets:
        for proof in value.source_proofs:
            assert proof.quote == event.content[proof.span_start:proof.span_end]
    assert explicit.selected_context_bytes == len(explicit.context_packet.encode("utf-8"))


@pytest.mark.parametrize("query", ["What did we decide?", "Only this chat: what response style do I prefer?"])
def test_vague_and_current_only_requests_do_not_scan_durable_history(tmp_path, monkeypatch, query):
    path = tmp_path / "no-scan.sqlite3"
    make_store(path)
    def forbidden(*args, **kwargs):
        raise AssertionError("request must not open an archive retrieval snapshot")
    monkeypatch.setattr(SQLiteRetrievalStore, "read_snapshot", forbidden)
    result = ContextEngine(path).retrieve(OWNER, request(query))
    assert result.evidence_packets == () and result.context_packet == ""
    assert result.retrieval_status.value != "found_relevant_evidence"


def test_cancelled_request_returns_safe_unavailable_without_scan(tmp_path, monkeypatch):
    path = tmp_path / "cancel.sqlite3"
    make_store(path)
    def forbidden(*args, **kwargs):
        raise AssertionError("cancelled request scanned archive")
    monkeypatch.setattr(SQLiteRetrievalStore, "read_snapshot", forbidden)
    result = ContextEngine(path, cancelled=lambda: True).retrieve(OWNER, request())
    assert result.retrieval_status.value == "unavailable"
    assert "context_cancelled" in result.reasons
    assert result.evidence_packets == ()


def test_total_deadline_is_deterministic_and_checked_before_scan(tmp_path, monkeypatch):
    path = tmp_path / "deadline.sqlite3"
    make_store(path)
    def forbidden(*args, **kwargs):
        raise AssertionError("expired request scanned archive")
    monkeypatch.setattr(SQLiteRetrievalStore, "read_snapshot", forbidden)
    clock = count(0, 10).__next__
    result = ContextEngine(path, deadline_seconds=1, clock=clock).retrieve(OWNER, request())
    assert result.retrieval_status.value == "unavailable"
    assert "context_deadline" in result.reasons
    assert result.evidence_packets == ()
