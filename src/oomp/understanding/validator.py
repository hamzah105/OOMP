"""Independent validation. Never trust provider authority or free paraphrase."""
from __future__ import annotations

from collections.abc import Sequence
import re

from .contracts import CandidateProposal, ExtractionConfiguration, candidate_id
from .rules import blocked_reason, clauses, classify, promotion


class CandidateRejected(ValueError):
    def __init__(self, code="candidate_rejected"):
        self.code = code
        super().__init__(code)


class CandidateValidator:
    version = "mind2.validator.v1"

    def __init__(self, config: ExtractionConfiguration | None = None):
        self.config = ExtractionConfiguration.model_validate(config.model_dump(mode="json")) if config else ExtractionConfiguration()

    def validate(self, scope, event, proposed):
        reason = blocked_reason(scope, event, self.config)
        if reason:
            raise CandidateRejected(reason)
        if not isinstance(proposed, Sequence) or isinstance(proposed, (str, bytes)) or len(proposed) > self.config.max_candidates:
            raise CandidateRejected("candidate_count_limit")
        supported = {(s.start, s.end, s.quote) for s in clauses(event.content)}
        result, seen = [], set()
        for raw in proposed:
            try:
                candidate = CandidateProposal.model_validate(raw.model_dump(mode="json") if isinstance(raw, CandidateProposal) else raw)
            except (ValueError, TypeError):
                raise CandidateRejected("candidate_contract_invalid") from None
            if (candidate.tenant_id, candidate.namespace, candidate.principal_id) != (scope.tenant_id, scope.namespace, scope.principal_id):
                raise CandidateRejected("candidate_scope_mismatch")
            span = candidate.source_spans[0]
            if candidate.source_event_ids != (event.event_id,) or candidate.claimed_by != event.source_type.value:
                raise CandidateRejected("candidate_source_authority_mismatch")
            if (span.start, span.end, span.quote) not in supported or event.content[span.start:span.end] != span.quote:
                raise CandidateRejected("candidate_span_invalid")
            if candidate.object != span.quote or candidate.candidate_id != candidate_id(event, span):
                raise CandidateRejected("candidate_content_invalid")
            if candidate.extractor_provider == "rules" and candidate.model_version is not None:
                raise CandidateRejected("candidate_provider_invalid")
            if candidate.extractor_provider == "ollama" and (
                    self.config.mode != "local-llm" or candidate.model_version != self.config.model):
                raise CandidateRejected("candidate_model_mismatch")
            if len(span.quote.split()) < 2:
                raise CandidateRejected("candidate_empty_claim")
            expected = classify(event, span)
            if any(getattr(candidate, field) != value for field, value in expected.items()):
                if not self._literal_model_refinement(event, candidate, expected):
                    raise CandidateRejected("candidate_semantics_unsupported")
            if candidate.sensitivity == "sensitive" and not self.config.sensitive_episodes:
                raise CandidateRejected("sensitive_source_excluded")
            if not self.config.retain_episodes and promotion(candidate)[0] != "canonical":
                raise CandidateRejected("episodic_retention_disabled")
            if candidate.candidate_id in seen:
                raise CandidateRejected("duplicate_candidate")
            seen.add(candidate.candidate_id)
            result.append(candidate)
        return tuple(result)

    @staticmethod
    def _literal_model_refinement(event, candidate, expected):
        """An independent, anchored entailment allowlist, not model confidence.

        Rules can retain the clause as an episode without selecting a richer
        interpretation. A model can propose these additional literal forms.
        No paraphrase, free entity, uncertain premise or profile inference.
        """
        if (candidate.extractor_provider != "ollama" or event.source_type.value != "user"
                or expected["assertion_kind"] != "explicit" or expected["sensitivity"] != "ordinary"
                or expected["memory_category"] != "episodic"
                or candidate.assertion_kind != "explicit"):
            return False
        allowed = None
        text = candidate.source_spans[0].quote
        if re.fullmatch(r"(?:my friends call me|I'm called|I am called|you can call me)\s+[^.!?]{1,128}[.!]?", text, re.I):
            allowed = ("alias", "profile")
        elif re.fullmatch(r"(?:please|remember that I)\s+(?:use|keep|explain|give|avoid|like|prefer)\b.+", text, re.I):
            allowed = ("preference", "procedural")
        elif re.fullmatch(r"(?:I'd rather|I tend to prefer|I usually prefer)\b.+", text, re.I):
            allowed = ("preference", "profile")
        elif re.fullmatch(r"my next step is to\s+.+", text, re.I):
            allowed = ("plan", "prospective")
        if allowed != (candidate.predicate, candidate.memory_category):
            return False
        return all(getattr(candidate, field) == value for field, value in expected.items()
                   if field not in {"predicate", "memory_category"})
