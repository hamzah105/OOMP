"""Bounded clause parsing and transparent conservative retention policy."""
from __future__ import annotations

import re

from oomp.domain.enums import SourceType, EventType
from oomp.domain.memories import SourceSpan
from oomp.domain.models import AuthorizedScope, MemoryEvent
from oomp.ingestion.extraction import _SECRET, _SECRET_ASSIGNMENT, _extract_statement

from .contracts import CandidateProposal, ExtractionConfiguration, candidate_id
from .quoted import quoted_context

_TERMINAL = re.compile(r"""[.!?]+["'\u201d\u2019]*(?=\s|$)""")
_BOUNDARY = re.compile(r"""[.!?]+["'\u201d\u2019]*(?=\s|$)|\n+|;\s*|\s+(?:and|but)\s+(?=(?:I\b|I'm\b|I've\b|my\b|we\b))""", re.I)
_INJECTION = re.compile(r"ignore.{0,48}(?:rules|instructions|policy|access)|(?:bypass|disable|override).{0,32}(?:auth|policy|security|rules)|(?:system|developer)\s*(?:prompt|message)|(?:execute|run)\s+(?:this\s+)?(?:command|powershell|shell)|grant\s+(?:me\s+)?(?:admin|access)", re.I)
_SENSITIVE = re.compile(r"\b(?:politic\w*|prime minister|president|ethnic\w*|nationality|religio\w*|diagnos\w*|medical|sexual\w*|criminal|affiliation|Afghan|Pakistani)\b", re.I)
_SENSITIVE_DETAIL = re.compile(
    r"\b(?:diabet\w*|cancer|insulin|medication|therapy|depression|anxiety|bipolar|HIV|"
    r"pregnan\w*|abortion|self[- ]harm|suicid\w*|ADHD|PTSD|autis\w*|disability|"
    r"Muslim|Christian|Hindu|Jewish|Buddhist|atheist|"
    r"(?:Liberal|Conservative|Democratic|Republican|Communist|Socialist|Green|Labour|Labor)\s+Party|"
    r"PTI|PML[- ]?N|PPP)\b", re.I)
_HYPOTHETICAL = re.compile(r"\b(?:if|suppose|hypothetical\w*|imagine|would|unless)\b", re.I)
_UNCERTAIN = re.compile(r"\b(?:maybe|might|could|perhaps|possibly|not sure)\b", re.I)
_QUOTED = re.compile(r"^[\"'\u201c\u2018>]|\b(?:said|says|according to|quoted|claims that)\b", re.I)
_PREFERENCE = re.compile(r"^(?:remember[:,]?\s*)?(?:I\s+(?:(?:do not|don't)\s+)?(?:prefer|preffer|preferr|like|love)|my preference is)\b", re.I)
_ALIAS = re.compile(r"^(?:my (?:name|display name|test alias|alias) is|call me|I go by)\s+\S", re.I)
_PLAN = re.compile(r"^(?:I (?:am |'m )?(?:considering|planning)|I'm (?:considering|planning)|I plan to|I want to|I intend to|I will)\b", re.I)
_UPDATE = re.compile(r"^(?:actually\b|correction\b|I (?:have |'ve )?decided|I've decided|I no longer|I changed my|instead\b)", re.I)
_FOCUS = re.compile(r"^(?:forget (?:about )?.+for now|let'?s (?:talk|discuss)|back to|return to|resume)\b", re.I)


def blocked_reason(scope: AuthorizedScope, event: MemoryEvent, config: ExtractionConfiguration) -> str | None:
    if not isinstance(scope, AuthorizedScope):
        return "authorized_scope_required"
    if (scope.tenant_id, scope.namespace) != (event.tenant_id, event.namespace):
        return "source_scope_mismatch"
    if event.metadata.get("ingested_by", scope.principal_id) != scope.principal_id:
        return "source_principal_mismatch"
    if len(event.content) > config.max_input_chars:
        return "extraction_input_limit"
    if _SECRET.search(event.content) or _SECRET_ASSIGNMENT.search(event.content):
        return "secret_like_source_excluded"
    if _INJECTION.search(event.content):
        return "untrusted_instruction_excluded"
    if any(term.casefold() in event.content.casefold() for term in config.exclude_terms):
        return "operator_excluded_source"
    if event.source_type not in {SourceType.USER, SourceType.ASSISTANT, SourceType.DOCUMENT}:
        return "source_role_excluded"
    allowed = {
        SourceType.USER: {EventType.USER_MESSAGE, EventType.CORRECTION, EventType.FEEDBACK},
        SourceType.ASSISTANT: {EventType.ASSISTANT_MESSAGE},
        SourceType.DOCUMENT: {EventType.DOCUMENT},
    }
    if event.event_type not in allowed[event.source_type]:
        return "source_event_type_excluded"
    return None


def clauses(content: str) -> tuple[SourceSpan, ...]:
    """No rewriting: offsets are Python Unicode code-point offsets."""
    result, start = [], 0
    for match in _BOUNDARY.finditer(content):
        end = match.end() if match.group()[0] in ".!?" else match.start()
        raw = content[start:end]
        left, right = start + len(raw) - len(raw.lstrip()), end - len(raw) + len(raw.rstrip())
        if left < right and right - left <= 512:
            result.append(SourceSpan(start=left, end=right, quote=content[left:right]))
        start = match.end()
        if len(result) >= 32:
            return tuple(result)
    raw = content[start:]
    left, right = start + len(raw) - len(raw.lstrip()), len(content.rstrip())
    if left < right and right - left <= 512 and len(result) < 32:
        result.append(SourceSpan(start=left, end=right, quote=content[left:right]))
    return tuple(result)


def classify(event: MemoryEvent, span: SourceSpan):
    text = span.quote.strip()
    sensitivity = "sensitive" if sensitive_text(text) else "ordinary"
    category, predicate, importance, assertion = "episodic", "stated", "low", "explicit"
    origin = 0
    for boundary in _TERMINAL.finditer(event.content[:span.start]):
        origin = boundary.end()
    prefix = event.content[origin:span.start]
    if event.source_type is SourceType.ASSISTANT:
        assertion = "assistant-originated"
    elif event.source_type is SourceType.DOCUMENT or _QUOTED.search(text) or quoted_context(event.content, span.start, span.end):
        assertion = "quoted"
    elif "?" in text or re.match(r"^(?:what|why|how|where|who|when|do you|can you)\b", text, re.I):
        assertion = "question"
    elif _HYPOTHETICAL.search(text) or _HYPOTHETICAL.search(prefix):
        assertion = "hypothetical"
    elif _UNCERTAIN.search(text) or _UNCERTAIN.search(prefix):
        assertion = "uncertain"
    elif _UPDATE.search(text) or event.event_type is EventType.CORRECTION:
        category, predicate, importance = "update", "correction", "normal"
    elif _FOCUS.search(text):
        predicate, importance = "focus", "normal"
    elif _ALIAS.search(text):
        category, predicate, importance = "profile", "alias", "normal"
    elif _PREFERENCE.search(text):
        category, predicate, importance = "profile", "preference", "durable"
    elif _PLAN.search(text):
        category, predicate, importance = "prospective", "plan", "normal"
        if re.search(r"\bconsidering\b", text, re.I):
            assertion = "tentative"
    elif (legacy := _extract_statement(event, span)) is not None:
        category = "profile" if legacy.memory_type.value == "profile" else "prospective" if legacy.memory_type.value == "project_state" else "semantic"
        predicate = "project" if category == "prospective" else "stated"
        importance = "normal"
    temporal = "source-time" if re.search(r"\b(?:yesterday|today|tomorrow|year|now|later)\b", text, re.I) else "unspecified"
    return dict(predicate=predicate, memory_category=category, assertion_kind=assertion,
                importance=importance, sensitivity=sensitivity, temporal_reference=temporal)


def sensitive_text(text):
    """Conservative English heuristic, not comprehensive sensitive-data detection."""
    return bool(_SENSITIVE.search(text) or _SENSITIVE_DETAIL.search(text))


def promotion(proposal: CandidateProposal) -> tuple[str, str]:
    if proposal.sensitivity == "sensitive":
        return "episodic-only", "sensitive_topic_only"
    if proposal.memory_category == "update":
        return "review", "correction_requires_review"
    if proposal.assertion_kind not in {"explicit", "tentative"} or proposal.claimed_by != "user":
        return "episodic-only", "attributed_discussion_only"
    if proposal.predicate in {"preference", "alias", "plan", "project"}:
        return "canonical", "explicit_user_claim"
    if proposal.memory_category == "semantic" and proposal.importance == "normal":
        return "canonical", "supported_explicit_statement"
    return "episodic-only", "low_salience_or_unsupported_form"


def proposal_for(scope, event, span, *, provider="rules", model=None, hints=None):
    fields = classify(event, span)
    if hints:
        fields.update(hints)
    return CandidateProposal(candidate_id=candidate_id(event, span), tenant_id=scope.tenant_id,
        namespace=scope.namespace, principal_id=scope.principal_id, object=span.quote,
        claimed_by=event.source_type.value, source_event_ids=(event.event_id,), source_spans=(span,),
        extractor_provider=provider, model_version=model, **fields)


class RulesExtractor:
    def __init__(self, config: ExtractionConfiguration | None = None):
        self.config = config or ExtractionConfiguration()

    def propose(self, scope, event):
        if blocked_reason(scope, event, self.config):
            return ()
        result = []
        for span in clauses(event.content):
            if len(span.quote.split()) < 2:
                continue
            proposal = proposal_for(scope, event, span)
            if proposal.sensitivity == "sensitive" and not self.config.sensitive_episodes:
                continue
            if not self.config.retain_episodes and promotion(proposal)[0] != "canonical":
                continue
            result.append(proposal)
            if len(result) == self.config.max_candidates:
                break
        return tuple(result)
