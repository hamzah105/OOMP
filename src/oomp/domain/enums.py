"""Stable vocabulary for source evidence and derived memory."""

from enum import StrEnum


class EventType(StrEnum):
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    DOCUMENT = "document"
    TOOL_RESULT = "tool_result"
    CORRECTION = "correction"
    FEEDBACK = "feedback"


class SourceType(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    DOCUMENT = "document"
    TOOL = "tool"
    SYSTEM = "system"


class MemoryType(StrEnum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROFILE = "profile"
    PROCEDURAL = "procedural"
    PROJECT_STATE = "project_state"
    RESOURCE = "resource"
    DECISION = "decision"
    TOPIC_SUMMARY = "topic_summary"


class MemoryStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"


class RelationshipType(StrEnum):
    ABOUT = "ABOUT"
    RELATED_TO = "RELATED_TO"
    PART_OF = "PART_OF"
    DERIVED_FROM = "DERIVED_FROM"
    OCCURRED_IN = "OCCURRED_IN"
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    SUPERSEDES = "SUPERSEDES"
    DEPENDS_ON = "DEPENDS_ON"
