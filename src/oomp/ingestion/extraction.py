"""Small offline extractor for explicitly supported statement forms."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence

from oomp.domain.enums import EventType, MemoryType, SourceType
from oomp.domain.memories import EntityMention, EntityType, SourceSpan
from oomp.domain.models import AuthorizedScope, MemoryEvent, MemoryNode, RequestedScope

from .canonicalization import canonicalize
from .contracts import MemoryCandidate

MAX_INPUT_CHARS = 16_384
MAX_CANDIDATES = 32
_SECRET = re.compile(
    r"\b(?:password|passphrase|api[ _-]?key|secret[ _-]?key|access[ _-]?token|"
    r"refresh[ _-]?token|bearer\s+\S+|private[ _-]?key)\b|-----BEGIN [A-Z ]+-----",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT = re.compile(
    r"\b(?:secret|token|api[ _-]?key|password|passphrase)\s*(?:[:=]|\bis\b)\s*\S+"
    r"|\b(?:sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9_]{8,}|xoxb-[A-Za-z0-9-]{8,})\b",
    re.IGNORECASE,
)
_UNCERTAIN = re.compile(r"\b(?:maybe|might|could|should|would|if|unless|hypothetical|possibly|perhaps)\b", re.IGNORECASE)
_SENTENCES = re.compile(r"[^.!?]+(?:[.!?](?=\s|$)|$)")
_PREFERENCE = re.compile(r"^I (?P<negative>do not |don't )?prefer (?P<object>.+)$", re.IGNORECASE)
_PROJECT = re.compile(
    r"^I am developing a project called (?P<name>[^()]+?)(?:\s*\((?P<alias>[^()]+)\))?$",
    re.IGNORECASE,
)
_CONSIDERING = re.compile(r"^I am considering buying (?P<object>.+)$", re.IGNORECASE)
_PLAN = re.compile(r"^I plan to (?P<object>.+)$", re.IGNORECASE)
_PURCHASED = re.compile(r"^I purchased (?P<object>.+)$", re.IGNORECASE)
_DECISION = re.compile(r"^We decided to (?P<object>.+)$", re.IGNORECASE)
_TECHNICAL = re.compile(r"^(?P<subject>[A-Z][A-Za-z0-9_-]{1,63}) uses (?P<object>.+)$")


def eligibility_reason(event: MemoryEvent) -> str | None:
    if len(event.content) > MAX_INPUT_CHARS:
        return "source event exceeds extraction input limit"
    if _SECRET.search(event.content) or _SECRET_ASSIGNMENT.search(event.content):
        return "source event may contain a secret"
    if "?" in event.content:
        return "source event contains a question"
    if event.source_type is SourceType.USER and event.event_type in {
        EventType.USER_MESSAGE, EventType.CORRECTION, EventType.FEEDBACK,
    }:
        return None
    if event.source_type is SourceType.DOCUMENT and event.event_type is EventType.DOCUMENT:
        return None
    return "source role is ineligible for deterministic extraction"


def _scope_matches(scope: RequestedScope, event: MemoryEvent) -> None:
    if not isinstance(scope, RequestedScope):
        raise TypeError("a requested or authorized scope is required")
    if (scope.tenant_id, scope.namespace) != (event.tenant_id, event.namespace):
        raise ValueError("event scope differs from requested scope")


def _statement_spans(content: str):
    for match in _SENTENCES.finditer(content):
        raw = match.group()
        trimmed = raw.strip()
        if not trimmed:
            continue
        start = match.start() + len(raw) - len(raw.lstrip())
        end = match.end() - (len(raw) - len(raw.rstrip()))
        yield SourceSpan(start=start, end=end, quote=content[start:end])


def _collapse(text: str) -> str:
    return " ".join(text.split())


def _build_candidate(
    event: MemoryEvent, span: SourceSpan, memory_type: MemoryType, canonical_content: str,
    *, subject: str | None = None, entities: tuple[EntityMention, ...] = (),
) -> MemoryCandidate:
    identity = [event.event_id, span.start, span.end, memory_type.value, canonical_content]
    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return MemoryCandidate(
        tenant_id=event.tenant_id, namespace=event.namespace,
        candidate_id="cand-" + digest, memory_type=memory_type,
        canonical_content=canonical_content,
        source_event_id=event.event_id, source_span=span,
        subject=subject, entities=entities, confidence=None,
        extraction_method="deterministic",
    )


def _extract_statement(event: MemoryEvent, span: SourceSpan) -> MemoryCandidate | None:
    sentence = span.quote
    if "?" in sentence or _UNCERTAIN.search(sentence):
        return None
    body = sentence.rstrip(".!").strip()
    normalized_body = _collapse(body)
    if not body:
        return None
    user = event.source_type is SourceType.USER

    if user and (match := _PREFERENCE.fullmatch(normalized_body)):
        object_text = _collapse(match.group("object"))
        negative = match.group("negative") is not None
        prefix = "User does not prefer" if negative else "User prefers"
        return _build_candidate(event, span, MemoryType.PROFILE, f"{prefix} {object_text}.")
    if user and (match := _PROJECT.fullmatch(body)):
        name = _collapse(match.group("name"))
        alias = _collapse(match.group("alias")) if match.group("alias") else None
        if len(name) > 128 or (alias is not None and len(alias) > 128):
            return None
        begin = span.start + match.start("name")
        finish = span.start + (match.end("alias") + 1 if alias else match.end("name"))
        mention = EntityMention(
            name=name, entity_type=EntityType.PROJECT,
            aliases=(alias,) if alias else (), source_event_id=event.event_id,
            source_span=SourceSpan(
                start=begin, end=finish, quote=event.content[begin:finish],
            ),
        )
        return _build_candidate(
            event, span, MemoryType.PROJECT_STATE,
            f"User is developing a project called {name}.",
            subject=name, entities=(mention,),
        )
    if user and (match := _CONSIDERING.fullmatch(normalized_body)):
        return _build_candidate(
            event, span, MemoryType.PROJECT_STATE,
            f"User is considering buying {_collapse(match.group('object'))}.",
        )
    if user and (match := _PLAN.fullmatch(normalized_body)):
        return _build_candidate(
            event, span, MemoryType.PROJECT_STATE,
            f"User plans to {_collapse(match.group('object'))}.",
        )
    if user and (match := _PURCHASED.fullmatch(normalized_body)):
        return _build_candidate(
            event, span, MemoryType.EPISODIC,
            f"User purchased {_collapse(match.group('object'))}.",
        )
    if (match := _DECISION.fullmatch(normalized_body)):
        return _build_candidate(
            event, span, MemoryType.DECISION,
            f"We decided to {_collapse(match.group('object'))}.",
        )
    if (match := _TECHNICAL.fullmatch(normalized_body)):
        subject = match.group("subject")
        if subject.casefold() in {"this", "that", "user", "assistant"}:
            return None
        return _build_candidate(
            event, span, MemoryType.SEMANTIC,
            f"{subject} uses {_collapse(match.group('object'))}.",
        )
    return None


class DeterministicExtractor:
    """No network or model use. Unsupported text yields no candidates."""

    def extract_candidates(
        self, scope: RequestedScope, event: MemoryEvent
    ) -> tuple[MemoryCandidate, ...]:
        if not isinstance(event, MemoryEvent):
            raise TypeError("a MemoryEvent is required")
        event = MemoryEvent.model_validate(event.model_dump(mode="json"))
        _scope_matches(scope, event)
        if eligibility_reason(event) is not None:
            return ()
        candidates: list[MemoryCandidate] = []
        for span in _statement_spans(event.content):
            candidate = _extract_statement(event, span)
            if candidate is not None:
                candidates.append(candidate)
                if len(candidates) == MAX_CANDIDATES:
                    break
        return tuple(candidates)

    def extract(
        self, scope: AuthorizedScope, events: Sequence[MemoryEvent]
    ) -> tuple[MemoryNode, ...]:
        """Pure Stage 1 MemoryExtractor-compatible derivation; no persistence."""
        if not isinstance(scope, AuthorizedScope):
            raise TypeError("an AuthorizedScope from a trusted caller is required")
        authorized = AuthorizedScope.model_validate(scope.model_dump(mode="json"))
        return tuple(
            canonicalize(candidate, event)
            for event in events
            for candidate in self.extract_candidates(authorized, event)
        )
