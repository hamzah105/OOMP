from __future__ import annotations

import json
from datetime import datetime, timezone

from oomp.retrieval.contracts import MemoryEvidence
from oomp.retrieval.packing import Utf8ByteCounter, pack_evidence


def _memory(identity: str, content: str) -> MemoryEvidence:
    from oomp.domain.models import SourceReference
    return MemoryEvidence(
        memory_id=identity, memory_type="semantic", canonical_content=content,
        source_event_ids=("event-" + identity,),
        source_references=(SourceReference(
            source_system="test", external_event_id="source-" + identity,
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),),
        selection_reasons=("lexical",),
    )


def test_complete_evidence_packet_bytes_include_provenance_and_self_count():
    items = (_memory("mem-1", "Café project"), _memory("mem-2", "Other project"))
    both = pack_evidence(items, 32768, 2)
    parsed = json.loads(both.context_packet)
    assert len(parsed["memories"]) == 2
    assert parsed["memories"][0]["source_references"][0]["external_event_id"] == "source-mem-1"
    assert parsed["estimated_token_count"] == both.estimated_token_count
    assert both.estimated_token_count == len(both.context_packet.encode("utf-8"))
    assert both.estimated_token_count > len(both.context_packet)


def test_small_budget_is_valid_empty_and_dropping_does_not_truncate():
    items = (_memory("mem-1", "First complete assertion"), _memory("mem-2", "Second complete assertion"))
    empty = pack_evidence(items, 1, 2)
    assert empty.memories == ()
    assert empty.context_packet == ""
    assert empty.estimated_token_count == 0
    one = pack_evidence(items, pack_evidence(items[:1], 32768, 1).estimated_token_count, 2)
    assert len(one.memories) == 1
    assert one.memories[0].canonical_content == "First complete assertion"
    assert one.dropped == 1


def test_counting_method_is_declared_and_identical_runs_are_stable():
    item = _memory("mem-1", "One memory")
    first = pack_evidence((item,), 1000, 1, counter=Utf8ByteCounter())
    second = pack_evidence((item,), 1000, 1, counter=Utf8ByteCounter())
    assert first == second
    assert json.loads(first.context_packet)["counting_method"] == "utf8_bytes_upper_bound_v1"