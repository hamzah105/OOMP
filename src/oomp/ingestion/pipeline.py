"""Synchronous, atomic-per-event orchestration from source to memory."""

from __future__ import annotations

from collections.abc import Sequence
from os import PathLike

from pydantic import ValidationError

from oomp.domain.memories import MemoryWrite, ProcessingResult
from oomp.domain.models import AuthorizedScope
from oomp.storage.sqlite import SQLiteEventStore
from oomp.storage.memory_store import SQLiteMemoryStore

from .canonicalization import canonicalize
from .contracts import CandidateExtractor, EventNotFoundError, MemoryCandidate, ProcessingError
from .extraction import DeterministicExtractor, MAX_CANDIDATES, eligibility_reason


class ExtractionPipeline:
    """The trusted service supplies AuthorizedScope; candidate providers have no write authority."""

    def __init__(
        self, path: str | PathLike[str] | None = None,
        *, extractor: CandidateExtractor | None = None,
    ) -> None:
        self.event_store = SQLiteEventStore(path)
        self.memory_store = SQLiteMemoryStore(path)
        self.extractor = extractor if extractor is not None else DeterministicExtractor()
        self._grounding_extractor = DeterministicExtractor()

    def process_event(self, scope: AuthorizedScope, event_id: str) -> ProcessingResult:
        if not isinstance(scope, AuthorizedScope):
            raise TypeError("an AuthorizedScope from a trusted caller is required")
        authorized = AuthorizedScope.model_validate(scope.model_dump(mode="json"))
        event = self.event_store.get(authorized, event_id)
        if event is None:
            raise EventNotFoundError("source event was not found in the authorized scope")
        reason = eligibility_reason(event)
        if reason is not None:
            return ProcessingResult(event_id=event.event_id, reason=reason)

        try:
            proposed = self.extractor.extract_candidates(authorized, event)
        except Exception as error:
            raise ProcessingError("candidate extractor failed") from error
        if not isinstance(proposed, Sequence) or isinstance(proposed, (str, bytes)):
            raise ProcessingError("candidate extractor must return a bounded sequence")
        if len(proposed) > MAX_CANDIDATES:
            raise ProcessingError("candidate extractor exceeded output limit")

        trusted = self._grounding_extractor.extract_candidates(authorized, event)
        allowed = {
            self._grounding_fields(candidate)
            for candidate in trusted
        }
        validated: list[MemoryCandidate] = []
        seen: set[tuple[str, int, int]] = set()
        for raw in proposed:
            try:
                payload = raw.model_dump(mode="json") if isinstance(raw, MemoryCandidate) else raw
                candidate = MemoryCandidate.model_validate(payload)
            except (ValidationError, ValueError, TypeError) as error:
                raise ProcessingError("candidate failed contract validation") from error
            if candidate.confidence is not None:
                raise ProcessingError("unmeasured candidate confidence is unsupported")
            if self._grounding_fields(candidate) not in allowed:
                raise ProcessingError("candidate is not supported by the source event")
            identity = (
                candidate.candidate_id, candidate.source_span.start, candidate.source_span.end
            )
            if identity in seen:
                raise ProcessingError("candidate extractor returned a duplicate proposal")
            seen.add(identity)
            validated.append(candidate)

        if not validated:
            return ProcessingResult(event_id=event.event_id, reason="no supported claim extracted")

        writes = tuple(
            MemoryWrite(
                memory=canonicalize(candidate, event),
                entities=candidate.entities,
                source_span=candidate.source_span,
                extraction_method=candidate.extraction_method,
            )
            for candidate in validated
        )
        persisted = self.memory_store.apply_batch(authorized, event.event_id, writes)
        data = persisted.model_dump(mode="json")
        data["candidates_extracted"] = len(validated)
        return ProcessingResult.model_validate(data)

    @staticmethod
    def _grounding_fields(candidate: MemoryCandidate) -> str:
        # Exact structured comparison against independent deterministic parsing.
        # A provider may label itself, but cannot propose a new factual transform.
        return candidate.model_dump_json(exclude={"candidate_id", "extraction_method"})
