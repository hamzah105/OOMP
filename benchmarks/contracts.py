"""Frozen synthetic fixtures and pre-registered, bounded experimental settings."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from oomp.domain.models import MemoryEvent, MemoryNode, UtcDateTime


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CuratedMemory(Frozen):
    """Explicitly authored structured input, NOT a claim of automatic extraction."""
    source_id: str
    valid_from: UtcDateTime | None = None
    valid_until: UtcDateTime | None = None


class Link(Frozen):
    source_event: str
    target_event: str
    evidence_events: tuple[str, ...]
    relation: Literal["RELATED_TO", "DEPENDS_ON", "SUPERSEDES", "CONTRADICTS"]


class Topic(Frozen):
    topic_id: str
    name: str
    source_events: tuple[str, ...]


class History(Frozen):
    history_id: str
    split: Literal["development", "validation", "heldout"]
    seed: int
    category: str
    tenant_id: str
    namespace: str = "synthetic-stage9"
    events: tuple[MemoryEvent, ...]
    curated: tuple[CuratedMemory, ...] = ()
    links: tuple[Link, ...] = ()
    topics: tuple[Topic, ...] = ()


class Case(Frozen):
    case_id: str
    history_id: str
    category: str
    query: str = Field(min_length=1, max_length=4096)
    history_cutoff: UtcDateTime
    valid_at: UtcDateTime | None = None
    known_at: UtcDateTime | None = None
    historical: bool = False
    expected_answers: tuple[str, ...] = ()
    relevant_source_event_ids: tuple[str, ...] = ()
    forbidden_source_event_ids: tuple[str, ...] = ()
    answerability: Literal["answerable", "unanswerable", "disputed"]
    latest_eight_available: bool
    fact_distance: int | None = None
    # Ordered edge requirements are source-event endpoint pairs, not invented IDs.
    required_chain: tuple[tuple[str, str], ...] = ()
    required_hops: int = Field(default=0, ge=0, le=3)
    fixture_layer: Literal["extracted", "curated_temporal", "trusted_graph"] = "extracted"
    semantic_label: Literal["direct", "paraphrase", "alias", "not_applicable"] = "not_applicable"


class Dataset(Frozen):
    version: Literal["stage9-synthetic-v1"] = "stage9-synthetic-v1"
    histories: tuple[History, ...]
    cases: tuple[Case, ...]


METHODS = (
    "trace_n8", "rolling_summary", "flat_lexical", "flat_vector", "oomp_full",
    "oomp_no_graph", "oomp_no_augmentation", "oomp_lexical", "oomp_semantic",
    "flat_no_temporal", "oomp_no_fusion",
)


class Config(Frozen):
    version: Literal[1] = 1
    name: str = Field(pattern=r"^[a-z0-9-]{1,64}$")
    split: Literal["development", "validation", "heldout"] = "development"
    seeds: tuple[int, ...] = Field(min_length=1, max_length=12)
    sizes: tuple[int, ...] = Field(default=(128,), min_length=1, max_length=5)
    categories: tuple[str, ...] = ("long_history", "temporal", "contradiction", "multihop", "negative", "noisy")
    methods: tuple[str, ...] = ("trace_n8", "rolling_summary", "flat_lexical", "flat_vector", "oomp_full")
    evidence_budget: int = Field(default=6000, ge=256, le=32768)
    max_results: int = Field(default=8, ge=1, le=20)
    metric_k: int = Field(default=8, ge=1, le=100)
    summary_budget: int = Field(default=6000, ge=256, le=32768)
    summary_update_every: int = Field(default=4, ge=1, le=32)
    graph_depth: int = Field(default=2, ge=0, le=2)
    mode: Literal["lexical", "hybrid", "semantic"] = "lexical"
    min_similarity: float = Field(default=0.2, ge=0, le=1, allow_inf_nan=False)
    repetitions: int = Field(default=1, ge=1, le=5)
    bootstrap_samples: int = Field(default=1000, ge=100, le=10000)
    bootstrap_seed: int = 90210
    primary_metric: Literal["recall_at_k"] = "recall_at_k"
    aggregation: Literal["case_macro_with_history_cluster_ci"] = "case_macro_with_history_cluster_ci"
    max_cases: int = Field(default=500, ge=1, le=1000)
    max_histories: int = Field(default=100, ge=1, le=120)
    max_generation_calls: int = Field(default=0, ge=0, le=20)
    prompt_budget: int = Field(default=16000, ge=1024, le=32768)
    generation_reserve: int = Field(default=512, ge=256, le=1024)
    num_ctx: int = Field(default=32768, ge=4096, le=65536)
    embedding_model: str = "embeddinggemma:latest"
    embedding_dimension: int = Field(default=768, ge=1, le=4096)
    embedding_version: str = "stage9-ollama-embed-v1"
    generator_model: str = "llama3:latest"

    @model_validator(mode="after")
    def bounded_and_comparable(self):
        if not self.methods or len(set(self.methods)) != len(self.methods) or not set(self.methods) <= set(METHODS):
            raise ValueError("unknown or duplicated method")
        if len(set(self.seeds)) != len(self.seeds) or any(s < 0 or s > 1_000_000 for s in self.seeds):
            raise ValueError("invalid or duplicated seeds")
        if len(set(self.sizes)) != len(self.sizes) or any(s not in (16, 64, 128, 512, 1024) for s in self.sizes):
            raise ValueError("sizes must be distinct supported scales")
        valid = {"long_history", "temporal", "contradiction", "multihop", "negative", "noisy"}
        if not self.categories or len(set(self.categories)) != len(self.categories) or not set(self.categories) <= valid:
            raise ValueError("invalid categories")
        if self.summary_budget > self.evidence_budget:
            raise ValueError("summary cannot receive extra memory capacity")
        if self.prompt_budget + self.generation_reserve + 256 > self.num_ctx:
            raise ValueError("prompt byte proxy plus reserves exceeds configured model context")
        if self.mode != "lexical" and not {"flat_vector", "oomp_full"} <= set(self.methods):
            raise ValueError("live primary comparisons must include both vector and OOMP")
        return self


class Prepared(Frozen):
    """The same authorized prefix and canonical corpus supplied to every adapter."""
    history_id: str
    events: tuple[MemoryEvent, ...]
    memories: tuple[MemoryNode, ...]
    source_digest: str
    canonical_digest: str
    replay_known_at: datetime


class Evidence(Frozen):
    source_ids: tuple[str, ...]
    content: str
    temporal_status: str = "uninterpreted"
    valid_from: UtcDateTime | None = None
    valid_until: UtcDateTime | None = None
    memory_id: str | None = None
    # Each path preserves its ordered event endpoints, actual edge IDs and proof.
    paths: tuple[dict, ...] = ()


class Result(Frozen):
    method: str
    status: Literal["ok", "unavailable", "failed", "invalid"] = "ok"
    error_code: str | None = None
    evidence: tuple[Evidence, ...] = ()
    packet: str = ""
    packet_bytes: int = 0
    retrieval_ms: float = 0
    packing_ms: float | None = None
    warnings: tuple[str, ...] = ()
    trace: dict = Field(default_factory=dict)
