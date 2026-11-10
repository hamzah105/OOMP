"""Small deterministic query plans; hints have no storage or source authority."""
from __future__ import annotations

import re

from .contracts import ContextArgumentsFields, QueryPlan, RetrievalIntent

PLANNER_VERSION = "context.plan.v1"
_WORD = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)
_STOP = frozenset("a an and are as at be been being by can could did do does during for from had has have how i in is it its me mention mentioned my name names of on or our please recall remember said say tell than that the their them then there these they this those to us was we were what when where which who why will with would you your earlier previously before again about discussing discuss discussion talked talking talk conversation conversations session sessions chat chats information know recap summarize summarise repeat give explicitly".split())
_VAGUE = frozenset("not something anything everything thing things decide decided decision decisions plan plans happened continue carry next now same last recent previous old first".split())
_QUESTION_WORDS = frozenset("What Which Who When Where Why How Did Do Does Can Could Would Please Remember Tell Is Was Are Have".split())
_EXPLANATION_STYLE_QUERY = re.compile(
    r"\bhow\s+(?:do|should|would|can)\s+you\s+(?:explain|teach|present|describe)\s+"
    r"(?:technical\s+)?(?:topics?|concepts?)\s+to\s+me\b", re.I)
_TOPICS = (
    ("relocation", re.compile(r"\b(?:mov(?:e|ed|ing)|relocat\w*|cit(?:y|ies)|infrastructure|destination)\b", re.I), "relocate plan moved relocation move moving cities infrastructure"),
    ("projects", re.compile(r"\b(?:project\w*|robot\w*|build(?:ing)?)\b", re.I), "project robot prototype projects build building developing"),
    ("preferences", re.compile(r"\b(?:prefer\w*|(?:response|answer|reply) style|technical explanations?|format\w*\s+(?:(?:my|your|the)\s+)?(?:replies|responses|answers)|(?:replies|responses|answers)\s+(?:to be\s+)?format\w*)\b", re.I), "reply replies preference prefer response answers concise style"),
    ("identity-claims", re.compile(r"\b(?:alias|nickname|display name|my (?:(?:earlier|previous|old|original|legal|verified) )?name|call me|called me)\b", re.I), "alias nickname name call"),
    ("sensitive-discussion", re.compile(r"\b(?:politic\w*|prime minister|president|religio\w*)\b", re.I), "political politics discussion"),
)


def _terms(text):
    result = []
    for match in _WORD.finditer(text):
        value = match[0].casefold()
        if value not in _STOP and len(value) > 1 and len(value) <= 128 and value not in result:
            result.append(value)
        if len(result) == 32:
            break
    return result


def _topics(text):
    result = [name for name, pattern, _ in _TOPICS if pattern.search(text)]
    if _EXPLANATION_STYLE_QUERY.search(text) and "preferences" not in result:
        result.append("preferences")
    return result


def _anchors(request):
    result = list(dict.fromkeys(request.anchors))
    for match in re.finditer(r"[\"“]([^\"”\n]{1,160})[\"”]|\b[A-Z][A-Za-z0-9_-]*\b", request.query):
        value = match[1] if match[1] is not None else match[0]
        if value in _QUESTION_WORDS or value.casefold() in _STOP:
            continue
        # Explicit labels and mixed/upper-case names are hints, not resolved identity.
        if value not in result:
            result.append(value)
        if len(result) >= 4:
            break
    return result[:4]


def bounded_query_terms(plan):
    """Round-robin variants share the existing 32-token retrieval budget.

    A long primary question cannot consume every expansion/anchor slot. The
    strings are still literal data for the existing scoped FTS tokenizer.
    """
    variants = [re.findall(r'[^\W_]+', variant, re.UNICODE) for variant in plan.query_variants]
    result = []
    for index in range(max((len(words) for words in variants), default=0)):
        for words in variants:
            if index < len(words) and words[index].casefold() not in result:
                result.append(words[index].casefold())
                if len(result) == 32:
                    return tuple(result)
    return tuple(result)


def _intent(request, text, anchors):
    if re.search(r"\b(?:only (?:in )?(?:this|the current) (?:chat|session)|(?:in|from|during) (?:this|the current) (?:chat|session)(?: only)?)\b", text):
        return RetrievalIntent.CURRENT_SESSION_ONLY
    if (request.historical or re.search(r"\b(?:correction|corrected|renamed?|used to|as of|before (?:the )?change)\b", text)
            or re.search(r"\b(?:earlier|previous|old|original)\s+(?:project\s+)?name\b", text)):
        return RetrievalIntent.HISTORICAL_CORRECTION
    if re.search(r"\b(?:discuss\w*|talk\w*|conversation|episode)\b", text):
        return RetrievalIntent.EPISODIC_RECALL
    if re.search(r"\b(?:decid\w*|decision|plan\w*|relocat\w*|mov(?:e|ing)|next step|cancel\w*)\b", text):
        return RetrievalIntent.PLAN_FOLLOWUP
    if anchors or re.search(r"\b(?:project|alias|name|called)\b", text):
        return RetrievalIntent.ENTITY_LOOKUP
    return RetrievalIntent.FACTUAL_RECALL


def plan_request(request: ContextArgumentsFields) -> QueryPlan:
    """Plan only bounded relevance hints; never enumerate a user's archive."""
    if not isinstance(request, ContextArgumentsFields):
        raise TypeError("a validated context request is required")
    request = type(request).model_validate(request.model_dump(mode="json"))
    text = request.query.casefold()
    anchors = _anchors(request)
    terms = _terms(request.query)
    topics = _topics(text)
    intent = _intent(request, text, anchors)
    reasons = [PLANNER_VERSION]
    if re.search(r"\b(?:verified|authenticated|legal)\s+(?:personal\s+)?(?:name|identity)\b", text):
        return QueryPlan(retrieval_intent=RetrievalIntent.UNCERTAIN_RECALL,
                         search_allowed=False, needs_clarification=True,
                         reasons=(PLANNER_VERSION, "claimed_alias_not_verified_identity"))
    if intent is RetrievalIntent.CURRENT_SESSION_ONLY:
        return QueryPlan(retrieval_intent=intent, search_allowed=False,
                         reasons=(PLANNER_VERSION, "current_session_archive_search_disabled"))
    meaningful = [term for term in terms if term not in _VAGUE]
    if not meaningful and not anchors and not topics and request.recent_user_turns:
        # A supplied bounded referent can narrow a vague query. Different topics
        # remain ambiguous; recency alone cannot authenticate the intended subject.
        recent_topics = set(topic for turn in request.recent_user_turns for topic in _topics(turn))
        if len(recent_topics) == 1:
            topics = sorted(recent_topics)
            relevant = next(turn for turn in reversed(request.recent_user_turns) if topics[0] in _topics(turn))
            terms = list(dict.fromkeys((*terms, *_terms(relevant))))[:32]
            meaningful = [term for term in terms if term not in _VAGUE]
            reasons.append("authorized_recent_referent_hint")
    if not meaningful and not anchors and not topics:
        return QueryPlan(retrieval_intent=RetrievalIntent.UNCERTAIN_RECALL,
                         needs_clarification=True, search_allowed=False,
                         reasons=(PLANNER_VERSION, "ambiguous_referent_no_archive_scan"))
    variants = []
    # Quoted search terms are produced by the existing FTS layer. These strings
    # are bounded query data, not raw FTS expressions or statements of fact.
    primary = " ".join(terms) if terms else " ".join(anchors)
    if primary:
        variants.append(primary[:4096])
    # Reserve expansion slots for every requested facet rather than stopping
    # after the first two topics. This is one bounded lexical disjunction.
    expansions = [next(value for name, _, value in _TOPICS if name == topic).split() for topic in topics]
    expanded = []
    for index in range(max((len(words) for words in expansions), default=0)):
        for words in expansions:
            if index < len(words) and words[index] not in expanded:
                expanded.append(words[index])
            if len(expanded) == 28:
                break
        if len(expanded) == 28:
            break
    candidate = " ".join(expanded)
    if candidate and candidate not in variants:
        variants.append(candidate)
    if anchors and len(variants) < 3:
        candidate = " ".join(anchors)
        if candidate not in variants:
            variants.append(candidate[:4096])
    if not variants:
        return QueryPlan(retrieval_intent=RetrievalIntent.UNCERTAIN_RECALL,
                         needs_clarification=True, search_allowed=False,
                         reasons=(PLANNER_VERSION, "ambiguous_referent_no_archive_scan"))
    if len(_WORD.findall(request.query)) > 32:
        reasons.append("query_terms_bounded")
    if topics:
        reasons.append("literal_topic_query_expansion")
    if anchors:
        reasons.append("exact_anchor_hint")
    if anchors and 'identity-claims' in topics and re.match(r"\s*(?:is|was|are|were|does|did)\b", text):
        reasons.append("anchored_identity_contrast")
    if re.match(r"\s*(?:is|was|are|were|did|do|does|have|has|am)\b", text) and re.search(r"\band\b", text):
        reasons.append("conjunctive_claim_query")
    return QueryPlan(retrieval_intent=intent, query_variants=tuple(variants[:3]),
                     anchors=tuple(anchors), focus_terms=tuple(terms),
                     topic_hints=tuple(topics), reasons=tuple(reasons))
