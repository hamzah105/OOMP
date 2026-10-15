"""Deterministic reciprocal-rank fusion over independently ranked candidate lanes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from oomp.domain.models import Identifier
from pydantic import TypeAdapter

_ID = TypeAdapter(Identifier)
_DEFAULT_WEIGHTS = {"lexical": 1.0, "semantic": 1.0, "entity": 1.5, "topic": 1.0}


@dataclass(frozen=True)
class FusedCandidate:
    memory_id: str
    score: float
    reasons: tuple[str, ...]


def fuse_ranked(
    lanes: Mapping[str, Sequence[str]], *,
    weights: Mapping[str, float] | None = None,
    k: int = 60,
) -> tuple[FusedCandidate, ...]:
    """RRF score is sum(weight / (k + one-based rank)); it is not a probability."""
    if type(k) is not int or not 1 <= k <= 1000:
        raise ValueError("RRF k must be an integer from 1 to 1000")
    import math
    selected_weights = dict(_DEFAULT_WEIGHTS if weights is None else weights)
    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}
    for lane, ids in lanes.items():
        weight = selected_weights.get(lane)
        if weight is None or type(weight) not in (int, float) or not math.isfinite(weight) or weight <= 0:
            raise ValueError("every retrieval lane requires a positive finite weight")
        if len(ids) > 200:
            raise ValueError("candidate lane exceeds 200 items")
        seen: set[str] = set()
        for rank, raw_id in enumerate(ids, 1):
            memory_id = _ID.validate_python(raw_id)
            if memory_id in seen:
                continue
            seen.add(memory_id)
            scores[memory_id] = scores.get(memory_id, 0.0) + weight / (k + rank)
            reasons.setdefault(memory_id, []).append(lane)
    return tuple(
        FusedCandidate(memory_id, scores[memory_id], tuple(reasons[memory_id]))
        for memory_id in sorted(scores, key=lambda item: (-scores[item], item))
    )