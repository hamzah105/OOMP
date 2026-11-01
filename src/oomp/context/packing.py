"""Whole, independently proven context units under an explicit byte budget."""
from __future__ import annotations

from dataclasses import dataclass
import json
from collections.abc import Sequence

from .contracts import CONTEXT_VERSION, COUNTING_METHOD, ContextEvidence


@dataclass(frozen=True)
class PackedContext:
    evidence_packets: tuple[ContextEvidence, ...]
    context_packet: str
    selected_context_bytes: int
    dropped: int
    expanded: int


def source_keys(unit):
    """Canonical and episodic copies of one original span are one source."""
    return frozenset((p.event_id, p.span_start, p.span_end) for p in unit.source_proofs)


def serialize(units, budget):
    payload = {"context_contract_version": CONTEXT_VERSION,
               "evidence_packets": [unit.model_dump(mode="json", exclude_none=True) for unit in units],
               "token_budget": budget, "counting_method": COUNTING_METHOD,
               "selected_context_bytes": 0}
    count = 0
    for _ in range(16):
        payload["selected_context_bytes"] = count
        packet = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        measured = len(packet.encode("utf-8"))
        if measured == count:
            return packet, count
        count = measured
    raise ValueError("context_accounting_failed")


def pack_units(candidates: Sequence[ContextEvidence], token_budget: int, max_results: int, *, upgrades=()):
    if type(token_budget) is not int or not 1 <= token_budget <= 32768:
        raise ValueError("invalid_context_budget")
    if type(max_results) is not int or not 1 <= max_results <= 20:
        raise ValueError("invalid_context_result_limit")
    if len(candidates) > 240 or len(upgrades) > 240:
        raise ValueError("context_candidate_bound")
    chosen = []
    used = set()
    dropped = expanded = 0
    packet = ""
    count = 0
    for unit in candidates:
        if not isinstance(unit, ContextEvidence):
            raise TypeError("validated_context_unit_required")
        keys = source_keys(unit)
        if keys & used:
            continue
        if len(chosen) >= max_results:
            dropped += 1
            continue
        trial, cost = serialize((*chosen, unit), token_budget)
        if cost > token_budget:
            dropped += 1
            continue
        chosen.append(unit)
        used.update(keys)
        packet, count = trial, cost
    # Expansion replaces complete coarse units. No original supporting span is
    # silently lost, and no supporting event is duplicated across object paths.
    for unit in upgrades:
        if not isinstance(unit, ContextEvidence):
            raise TypeError("validated_context_unit_required")
        keys = source_keys(unit)
        overlap = [i for i, prior in enumerate(chosen) if source_keys(prior) & keys]
        if not overlap:
            continue
        prior_keys = set().union(*(source_keys(chosen[i]) for i in overlap))
        if not prior_keys <= keys or any(source_keys(old) & keys for i, old in enumerate(chosen) if i not in overlap):
            continue
        trial_units = [old for i, old in enumerate(chosen) if i not in overlap]
        trial_units.insert(min(overlap), unit)
        trial, cost = serialize(trial_units, token_budget)
        if cost <= token_budget:
            chosen, packet, count = trial_units, trial, cost
            expanded += 1
    return PackedContext(tuple(chosen), packet, count, dropped, expanded)
