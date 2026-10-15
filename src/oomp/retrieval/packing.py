"""Bounded, auditable evidence-context serialization."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol, Sequence

from .contracts import MemoryEvidence

COUNTING_METHOD = "utf8_bytes_upper_bound_v1"


class TokenCounter(Protocol):
    name: str

    def count(self, text: str) -> int: ...


class Utf8ByteCounter:
    """Conservative portable accounting proxy; no model tokenizer is claimed."""

    name = COUNTING_METHOD

    def count(self, text: str) -> int:
        return len(text.encode("utf-8"))


@dataclass(frozen=True)
class PackedEvidence:
    memories: tuple[MemoryEvidence, ...]
    context_packet: str
    estimated_token_count: int
    dropped: int


def _serialize(memories: Sequence[MemoryEvidence], budget: int, counter: TokenCounter) -> tuple[str, int]:
    payload = {
        "memories": [
            {
                **memory.model_dump(mode="json", exclude_none=True, exclude_defaults=True),
                "status": memory.status.value,
                "temporal_status": memory.temporal_status,
            }
            for memory in memories
        ],
        "token_budget": budget,
        "counting_method": counter.name,
        "estimated_token_count": 0,
    }
    count = 0
    for _ in range(16):
        payload["estimated_token_count"] = count
        packet = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        measured = counter.count(packet)
        if type(measured) is not int or measured < 0:
            raise ValueError("counter must return a nonnegative integer")
        if measured == count:
            return packet, count
        count = measured
    raise ValueError("token accounting did not converge")


def pack_evidence(
    candidates: Sequence[MemoryEvidence], token_budget: int, max_results: int, *,
    counter: TokenCounter | None = None,
) -> PackedEvidence:
    if type(token_budget) is not int or not 1 <= token_budget <= 32768:
        raise ValueError("token_budget must be an integer from 1 to 32768")
    if type(max_results) is not int or not 1 <= max_results <= 100:
        raise ValueError("max_results must be an integer from 1 to 100")
    selected_counter = counter or Utf8ByteCounter()
    if not selected_counter.name or len(selected_counter.name) > 128:
        raise ValueError("counter requires a bounded method name")
    chosen: list[MemoryEvidence] = []
    packet = ""
    count = 0
    dropped = 0
    for candidate in candidates:
        if len(chosen) >= max_results:
            dropped += 1
            continue
        if not isinstance(candidate, MemoryEvidence):
            raise TypeError("validated MemoryEvidence is required")
        trial, trial_count = _serialize((*chosen, candidate), token_budget, selected_counter)
        if trial_count > token_budget:
            dropped += 1
            continue
        chosen.append(candidate)
        packet, count = trial, trial_count
    # Empty evidence is represented by an empty context string with zero cost.
    return PackedEvidence(tuple(chosen), packet, count, dropped)