"""Pure source entailment checks; no provider construction or inference."""
from __future__ import annotations

from oomp.ingestion.canonicalization import canonicalize
from oomp.ingestion.extraction import DeterministicExtractor, eligibility_reason
from oomp.storage.memory_store import _memory_fingerprint
from oomp.understanding.contracts import ExtractionConfiguration
from oomp.understanding.rules import RulesExtractor, proposal_for, classify, classify_legacy, blocked_reason, clauses
from oomp.understanding.storage import candidate_writes, _new_node
from oomp.understanding.validator import CandidateValidator


def legacy_episode_entails_memory(scope, event, span, memory):
    """Re-prove only an exact pre-correction generic P2 episode node.

    Applicable source interpretations are frozen by classify_legacy(); neither
    persisted fields nor caller-provided hints choose the interpretation.
    """
    config = ExtractionConfiguration(max_input_chars=16384, sensitive_episodes=True)
    if (memory.metadata.get('canonicalization_version') != 'p2.1'
            or memory.metadata.get('p2_episode') is not True
            or blocked_reason(scope, event, config) is not None
            or span not in clauses(event.content) or len(span.quote.split()) < 2):
        return False
    original = classify_legacy(event, span)
    if (original == classify(event, span) or original['memory_category'] != 'episodic'
            or original['predicate'] != 'stated'):
        return False
    candidate = proposal_for(scope, event, span, hints=original)
    old_episode = _new_node(scope, event, candidate, episode=True)
    return (_memory_fingerprint(old_episode) == _memory_fingerprint(memory)
            and old_episode.canonical_key == memory.canonical_key)


def source_entails_memory(scope, event, span, memory):
    """A valid link/quote alone does not prove a free canonical paraphrase.

    Reuse the same deterministic canonicalizers and independent literal-model
    validator as acquisition/erasure proof. The source-proof model label is
    validation metadata only and never reaches a provider.
    """
    target = _memory_fingerprint(memory)

    def matches(writes):
        return any(write.source_span == span and _memory_fingerprint(write.memory) == target
                   and write.memory.canonical_key == memory.canonical_key for write in writes)

    # P2 can deliberately reuse a legacy canonical shape for a declarative
    # clause inside a mixed question event. Re-prove that clause through P2;
    # the older whole-event '?' eligibility rule must not reject valid P2 data.
    config = ExtractionConfiguration(max_input_chars=16384, sensitive_episodes=True)
    for candidate in RulesExtractor(config).propose(scope, event):
        if candidate.source_spans == (span,) and matches(candidate_writes(scope, event, candidate, config)):
            return True
    # The narrowly extended rules do not rewrite old generic episodes. Rebuild
    # their complete original node from the source and frozen original grammar,
    # requiring the exact fingerprint/key; never infer old semantics from the
    # stored metadata itself. This fallback cannot create a typed alias/plan.
    if legacy_episode_entails_memory(scope, event, span, memory):
        return True
    if memory.metadata.get('canonicalization_version') == 'p2.1':
        try:
            proof_config = ExtractionConfiguration(mode='local-llm', model='source-proof',
                max_input_chars=16384, sensitive_episodes=True)
            candidate = proposal_for(scope, event, span, provider='ollama', model='source-proof', hints={
                'predicate': memory.metadata['predicate'],
                'memory_category': memory.metadata['category'],
                'assertion_kind': memory.metadata['assertion_kind'],
            })
            CandidateValidator(proof_config).validate(scope, event, (candidate,))
            if matches(candidate_writes(scope, event, candidate, proof_config)):
                return True
        except (ValueError, TypeError, KeyError):
            pass
    if eligibility_reason(event) is None:
        for candidate in DeterministicExtractor().extract_candidates(scope, event):
            if candidate.source_span == span:
                derived = canonicalize(candidate, event)
                if _memory_fingerprint(derived) == target and derived.canonical_key == memory.canonical_key:
                    return True
    metadata = {'attribution': event.source_type.value, 'verified': False}
    allowed = (metadata, {**metadata, 'principal_id': scope.principal_id})
    return (memory.canonical_content == span.quote == event.content
            and span.start == 0 and span.end == len(event.content)
            and memory.metadata in allowed
            and not memory.tags)
