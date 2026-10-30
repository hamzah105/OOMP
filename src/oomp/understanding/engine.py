"""Rules-first acquisition; provider outage never suppresses deterministic work."""
from __future__ import annotations

from dataclasses import dataclass

from oomp.domain.memories import ProcessingResult
from oomp.storage.sqlite import SQLiteEventStore, _authorized
from oomp.storage.errors import SourceEventMissingError

from .contracts import ExtractionConfiguration
from .episodes import source_retracted
from .rules import RulesExtractor, blocked_reason, promotion
from .storage import UnderstandingStore
from .validator import CandidateValidator, CandidateRejected
from .transport import ExtractionUnavailable


@dataclass(frozen=True)
class AcquisitionResult:
    processing: ProcessingResult
    summary_revisions: int = 0
    model_calls: int = 0
    degraded: bool = False
    code: str = "extraction_completed"
    model_proposals: int = 0
    model_accepted: int = 0
    model_rejected: int = 0
    model_refinements: int = 0


class UnderstandingEngine:
    def __init__(self, path, config=None, *, provider=None, clock=None):
        self.config = ExtractionConfiguration.model_validate(config.model_dump(mode="json")) if config else ExtractionConfiguration()
        self.events = SQLiteEventStore(path)
        self.store = UnderstandingStore(path, clock=clock)
        self.rules = RulesExtractor(self.config)
        self.validator = CandidateValidator(self.config)
        if provider is None and self.config.mode == "local-llm":
            from .providers import OllamaExtractor
            provider = OllamaExtractor(self.config)
        self.provider = provider

    def acquire(self, scope, event, *, include_model=True):
        """Pure proposal stage; it has no persistence or job authority."""
        scope = _authorized(scope)
        reason = blocked_reason(scope, event, self.config)
        if reason:
            return (), dict(code=reason, degraded=False, model_calls=0, model_proposals=0, model_accepted=0, model_rejected=0, model_refinements=0)
        accepted = list(self.validator.validate(scope, event, self.rules.propose(scope, event)))
        stats = dict(code="extraction_completed", degraded=False, model_calls=0, model_proposals=0, model_accepted=0, model_rejected=0, model_refinements=0)
        if include_model and self.provider is not None:
            before = getattr(self.provider, "calls", 0)
            try:
                proposed = self.provider.propose(scope, event)
                if not isinstance(proposed, (tuple, list)) or len(proposed) > self.config.max_candidates:
                    raise CandidateRejected("candidate_count_limit")
                stats["model_proposals"] = len(proposed)
                seen = {item.candidate_id for item in accepted}
                provider_seen = set()
                for raw in proposed:
                    try:
                        candidate = self.validator.validate(scope, event, (raw,))[0]
                        if candidate.candidate_id in provider_seen:
                            raise CandidateRejected("duplicate_candidate")
                        provider_seen.add(candidate.candidate_id)
                        stats["model_accepted"] += 1
                        if candidate.candidate_id not in seen and len(accepted) < self.config.max_candidates:
                            accepted.append(candidate)
                            seen.add(candidate.candidate_id)
                        elif candidate.candidate_id in seen:
                            index = next(i for i, value in enumerate(accepted) if value.candidate_id == candidate.candidate_id)
                            rank = {"episodic-only": 0, "review": 1, "canonical": 2}
                            if rank[promotion(candidate)[0]] > rank[promotion(accepted[index])[0]]:
                                accepted[index] = candidate
                                stats["model_refinements"] += 1
                    except (CandidateRejected, ValueError, TypeError):
                        stats["model_rejected"] += 1
                        stats.update(degraded=True, code="model_candidates_rejected")
            except (ExtractionUnavailable, CandidateRejected) as error:
                stats.update(degraded=True, code=error.code)
            except Exception:
                stats.update(degraded=True, code="extraction_provider_failed")
            stats["model_calls"] = max(0, getattr(self.provider, "calls", before + 1) - before)
        return tuple(accepted), stats

    def process_event(self, scope, event_id, *, job=None):
        scope = _authorized(scope)
        event = self.events.get(scope, event_id)
        if event is None:
            raise SourceEventMissingError("extraction_source_missing")
        with self.store._graph_read() as connection:
            if source_retracted(connection, scope, event_id):
                return AcquisitionResult(ProcessingResult(event_id=event_id, reason="source_retracted"), code="source_retracted")
            self.store._guard_job(connection, scope, job)
        proposals, stats = self.acquire(scope, event)
        if not proposals:
            return AcquisitionResult(ProcessingResult(event_id=event_id, reason=stats["code"]), **stats)
        result, revisions = self.store.commit(scope, event, proposals, self.config, job=job)
        if result.reason == "source_retracted":
            stats["code"] = "source_retracted"
        return AcquisitionResult(result, summary_revisions=revisions, **stats)
