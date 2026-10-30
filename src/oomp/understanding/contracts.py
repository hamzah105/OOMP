"""Providers propose; trusted callers, stored evidence and policy authorize."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Literal, Protocol

from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator

from oomp.domain.memories import SourceSpan
from oomp.domain.models import AuthorizedScope, ContractModel, Identifier, MemoryEvent

Assertion = Literal["explicit", "tentative", "hypothetical", "quoted", "assistant-originated", "question", "uncertain"]
Category = Literal["profile", "semantic", "prospective", "procedural", "episodic", "update"]
Predicate = Literal["preference", "alias", "plan", "project", "correction", "focus", "stated"]
Promotion = Literal["canonical", "episodic-only", "review"]


class ExtractionConfiguration(ContractModel):
    version: Literal["mind2.v1"] = "mind2.v1"
    mode: Literal["rules", "local-llm"] = "rules"
    model: str | None = Field(default=None, min_length=1, max_length=96)
    endpoint: str = "http://127.0.0.1:11434"
    timeout_seconds: StrictInt = Field(default=20, ge=1, le=60)
    max_input_chars: StrictInt = Field(default=8192, ge=64, le=16384)
    max_candidates: StrictInt = Field(default=16, ge=1, le=16)
    max_output_tokens: StrictInt = Field(default=1024, ge=128, le=2048)
    retain_episodes: StrictBool = True
    sensitive_episodes: StrictBool = False
    exclude_terms: tuple[str, ...] = Field(default=(), max_length=32)

    @field_validator("model")
    @classmethod
    def safe_model(cls, value):
        if value is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,95}", value):
            raise ValueError("invalid_extraction_model")
        return value

    @field_validator("exclude_terms")
    @classmethod
    def safe_exclusions(cls, values):
        if any(not v.strip() or len(v) > 80 or any(ord(c) < 32 for c in v) for v in values):
            raise ValueError("invalid_extraction_exclusion")
        return values

    @model_validator(mode="after")
    def configured(self):
        from .transport import loopback_endpoint
        loopback_endpoint(self.endpoint)
        if self.mode == "local-llm" and self.model is None:
            raise ValueError("extraction_model_required")
        if self.mode == "rules" and self.model is not None:
            raise ValueError("rules_mode_has_no_model")
        return self

    @property
    def identity(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class CandidateProposal(ContractModel):
    schema_version: Literal["mind2.candidate.v1"] = "mind2.candidate.v1"
    candidate_id: Identifier
    tenant_id: Identifier
    namespace: Identifier
    principal_id: Identifier
    subject: Literal["speaker"] = "speaker"
    predicate: Predicate
    object: str = Field(min_length=1, max_length=512)
    memory_category: Category
    claimed_by: Literal["user", "assistant", "document"]
    source_event_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=1)
    source_spans: tuple[SourceSpan, ...] = Field(min_length=1, max_length=1)
    assertion_kind: Assertion
    temporal_reference: Literal["source-time", "unspecified"] = "unspecified"
    importance: Literal["durable", "normal", "low"]
    sensitivity: Literal["ordinary", "sensitive"]
    validity: Literal["uncertain"] = "uncertain"
    status: Literal["proposed"] = "proposed"
    extractor_provider: Literal["rules", "ollama"]
    extractor_version: Literal["mind2.v1"] = "mind2.v1"
    model_version: str | None = Field(default=None, max_length=96)
    confidence_calibration_status: Literal["uncalibrated"] = "uncalibrated"


class WireCandidate(ContractModel):
    quote: str = Field(min_length=1, max_length=512)
    predicate: Predicate
    memory_category: Category
    assertion_kind: Assertion


class WireBatch(ContractModel):
    candidates: tuple[WireCandidate, ...] = Field(default=(), max_length=16)


class ExtractionProvider(Protocol):
    """External implementations require separately authorized construction.

    This package supplies rules and literal-loopback Ollama only. Implementors
    have no database or policy authority and must bound all inference work.
    """
    def propose(self, scope: AuthorizedScope, event: MemoryEvent) -> tuple[CandidateProposal, ...]: ...


def candidate_id(event: MemoryEvent, span: SourceSpan) -> str:
    identity = [event.tenant_id, event.namespace, event.event_id, span.start, span.end, span.quote]
    return "p2cand-" + hashlib.sha256(json.dumps(identity, ensure_ascii=True).encode()).hexdigest()
