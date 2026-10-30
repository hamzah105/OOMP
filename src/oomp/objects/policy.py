"""Small, explainable object recognizers over already stored exact source spans.

These are navigation proposals, not a replacement extractor or an identity
resolver. Unsupported wording stays inspectable through its attributed fact.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from oomp.understanding.contracts import ExtractionConfiguration
from oomp.understanding.rules import blocked_reason, classify, sensitive_text
from .contracts import ObjectType

NAME = r"[\w][\w .'\u2019-]{0,79}?"
END = r"(?=[.!?]*$)"


@dataclass(frozen=True)
class Seed:
    kind: ObjectType
    role: str
    label: str
    label_start: int | None = None
    label_end: int | None = None
    context: bool = False
    previous_label: str | None = None


DOMAINS = {
    ObjectType.PERSON: ("Profile", "Claimed aliases"),
    ObjectType.PROJECT: ("Projects", "Named projects"),
    ObjectType.PLAN: ("Plans", "Relocation"),
    ObjectType.PLACE: ("Places", "Locations"),
    ObjectType.ORGANIZATION: ("Organizations", "Named organizations"),
    ObjectType.CONCEPT: ("Topics", "Concepts"),
    ObjectType.FACT: ("Facts", "Attributed claims"),
    ObjectType.SOURCE_EVENT: ("Evidence", "Original sources"),
    ObjectType.EPISODE: ("Episodes", "Discussions"),
    ObjectType.SUMMARY_REVISION: ("Episodes", "Summary revisions"),
}


def source_allowed(scope, event):
    return blocked_reason(scope, event, ExtractionConfiguration()) is None


def _literal(kind, role, span, match, group="label", **extra):
    raw = match[group]
    left, right = len(raw)-len(raw.lstrip()), len(raw.rstrip(" .!?"))
    label = raw[left:right]
    if not label or len(label)>80 or any(ord(char)<32 for char in label):
        return None
    start = span.start+match.start(group)+left
    return Seed(kind, role, label, start, start+len(label), **extra)


def seeds(event, span):
    """Derive each supported label and its literal subspan independently."""
    fields=classify(event, span)
    if sensitive_text(span.quote) or fields["assertion_kind"] not in {"explicit", "tentative"} or event.source_type.value!="user":
        return ()
    text=span.quote
    result=[]
    patterns=(
        (ObjectType.PERSON,"claimed_alias",r"^(?:my (?:name|display name|test alias|alias) is|call me|I go by)\s+(?P<label>"+NAME+")"+END),
        (ObjectType.PROJECT,"project_name",r"^I (?:am |'m )?developing a project called\s+(?P<label>"+NAME+")"+END),
        (ObjectType.ORGANIZATION,"organization_name",r"^I work for\s+(?P<label>"+NAME+")"+END),
        (ObjectType.PLACE,"claimed_current_city",r"^(?:I live in|my current city is|my city is|I am currently in|I'm currently in)\s+(?P<label>"+NAME+")"+END),
    )
    for kind,role,pattern in patterns:
        match=re.search(pattern,text,re.I)
        if match:
            seed=_literal(kind,role,span,match)
            if seed:result.append(seed)
    rename=re.search(r"^My project (?P<old>"+NAME+r") is now called (?P<label>"+NAME+")"+END,text,re.I)
    if rename:
        seed=_literal(ObjectType.PROJECT,"project_rename",span,rename,previous_label=rename["old"])
        if seed:result.append(seed)
    moving=bool(re.search(r"\b(?:mov(?:e|ing)|relocat\w*)\b",text,re.I))
    if fields["predicate"]=="plan":
        if moving:
            result.append(Seed(ObjectType.PLAN,"relocation_plan","Potential relocation"))
        else:
            match=re.search(r"^(?:I plan to|I want to|I intend to|I will|I'm considering|I am considering|I'm planning|I am planning)\s+(?P<label>.+?)[.!?]*$",text,re.I)
            if match:
                seed=_literal(ObjectType.PLAN,"plan",span,match)
                if seed:result.append(seed)
    if moving:
        route=re.search(r"\b(?:moving|move|relocating|relocate) from (?P<origin>"+NAME+r") to (?P<destination>"+NAME+")"+END,text,re.I)
        if route:
            for group,role in (("origin","origin_place"),("destination","candidate_place")):
                seed=_literal(ObjectType.PLACE,role,span,route,group,context=True)
                if seed:result.append(seed)
    candidates=re.search(r"^(?P<first>"+NAME+r") and (?P<second>"+NAME+r") are (?:possible )?candidates[.!?]*$",text,re.I)
    if candidates:
        for group in ("first","second"):
            seed=_literal(ObjectType.PLACE,"candidate_place",span,candidates,group,context=True)
            if seed:result.append(seed)
    criterion=re.search(r"^(?P<label>"+NAME+r") (?:matters most|is my (?:relocation )?criterion)(?: for project (?P<project>"+NAME+r"))?[.!?]*$",text,re.I)
    if criterion:
        seed=_literal(ObjectType.CONCEPT,"decision_criterion",span,criterion,context=True)
        if seed:result.append(seed)
    if fields["memory_category"]=="update" and re.search(r"\b(?:not to move|not moving|no longer (?:moving|considering moving))\b",text,re.I):
        match=re.search(r"(?P<label>not to move(?: this year)?|not moving(?: this year)?|no longer (?:moving|considering moving))",text,re.I)
        seed=_literal(ObjectType.PLAN,"plan_correction",span,match,context=True)
        if seed:result.append(seed)
    return tuple(result)


def episode_label(quote):
    from oomp.understanding.episodes import topic_label
    return {"relocation":"City comparison","projects":"Project discussion",
            "preferences":"Preferences discussion","identity-claims":"Claimed aliases discussion",
            "sensitive-discussion":"Sensitive discussion"}.get(topic_label(quote),"Conversation")


def status_for(assertion, role):
    if role=="plan_correction":return "correction_pending"
    if assertion=="tentative":return "tentative"
    if assertion in {"question","quoted","hypothetical","assistant-originated","uncertain"}:return "attributed"
    return "claimed"
