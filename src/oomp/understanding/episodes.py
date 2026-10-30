"""Compact chronological episodes in established summary/evidence tables."""
from __future__ import annotations

import hashlib
import re

from oomp.domain.graph import TemporalQuery
from oomp.domain.enums import MemoryStatus
from oomp.storage.mind_projection_store import _digest
from oomp.storage.memory_store import _event_in_scope
from oomp.storage.sqlite import _timestamp

EPISODE_POLICY = "episode-extractive.v1"


def source_retracted(connection, scope, event_id, known_at=None):
    sql = "SELECT 1 FROM mind_retractions WHERE tenant_id=? AND namespace=? AND event_id=?"
    args = [scope.tenant_id, scope.namespace, event_id]
    if known_at is not None:
        sql += " AND recorded_at<=?"
        args.append(_timestamp(known_at))
    return connection.execute(sql + " LIMIT 1", args).fetchone() is not None


def source_acquired(connection, scope, event_id, known_at=None):
    """Durable P2 provenance independent of optional episode retention."""
    args = [scope.tenant_id, scope.namespace, event_id]
    sql = """SELECT 1 FROM mind_maintenance_audit WHERE tenant_id=? AND namespace=?
             AND target_id=? AND target_type='event' AND operation_type='mind2.acquisition'"""
    if known_at is not None:
        sql += " AND recorded_at<=?"
        args.append(_timestamp(known_at))
    if connection.execute(sql + " LIMIT 1", args).fetchone() is not None:
        return True
    args = [scope.tenant_id, scope.namespace, event_id]
    sql = """SELECT 1 FROM memory_sources s JOIN memory_source_recordings r
             ON r.tenant_id=s.tenant_id AND r.namespace=s.namespace
               AND r.memory_id=s.memory_id AND r.event_id=s.event_id
             WHERE s.tenant_id=? AND s.namespace=? AND s.event_id=?
               AND s.extraction_method LIKE 'mind2.%'"""
    if known_at is not None:
        sql += " AND r.recorded_at<=?"
        args.append(_timestamp(known_at))
    return connection.execute(sql + " LIMIT 1", args).fetchone() is not None


def topic_label(quote):
    # Source-keyword projection, never an inferred belief/personal attribute.
    for name, expression in (
        ("relocation", r"\b(?:mov\w*|relocat\w*|Karachi|Lahore|Islamabad|infrastructure|cities|candidates)\b"),
        ("projects", r"\b(?:project|robot|ORBIT42|build\w*)\b"),
        ("preferences", r"\b(?:prefer\w*|like|love)\b"),
        ("identity-claims", r"\b(?:name|alias|call me)\b"),
        ("sensitive-discussion", r"\b(?:politic\w*|prime minister|president|religio\w*)\b"),
    ):
        if re.search(expression, quote, re.I):
            return name
    return "conversation"


def episode_base(scope, event, quote):
    window = int(event.occurred_at.timestamp()) // 1800
    session = event.source_reference.session_id or event.event_id
    label = topic_label(quote)
    return "p2episode-" + _digest([scope.tenant_id, scope.namespace, scope.principal_id, session, window, label])[:40], label


def episode_snapshot(store, connection, scope, topic_id, *, known_at=None):
    rows = connection.execute(
        """SELECT m.* FROM topic_memberships t JOIN memories m
           ON m.tenant_id=t.tenant_id AND m.namespace=t.namespace AND m.memory_id=t.memory_id
           WHERE t.tenant_id=? AND t.namespace=? AND t.topic_id=? ORDER BY m.memory_id LIMIT 17""",
        (scope.tenant_id, scope.namespace, topic_id),
    ).fetchall()
    if len(rows) > 16:
        raise ValueError("episode_member_limit")
    selected = []
    for row in rows:
        memory = store._read_memory(connection, scope, row)
        if memory.metadata.get("p2_episode") is not True or len(memory.source_event_ids) != 1:
            raise ValueError("episode_member_invalid")
        event_id = memory.source_event_ids[0]
        if source_retracted(connection, scope, event_id, known_at):
            continue
        state = store._memory_state_in_connection(connection, scope, memory.memory_id, TemporalQuery(known_at=known_at))
        if not state.evidence or state.known is not True or state.effective_status is not MemoryStatus.ACTIVE:
            continue
        event = _event_in_scope(connection, scope, event_id)
        span = memory.metadata["source_span"]
        if event.content[span["start"]:span["end"]] != span["quote"]:
            raise ValueError("episode_span_invalid")
        selected.append((event.occurred_at, event.ingested_at, event.event_id, span["start"], memory))
    selected.sort(key=lambda item: item[:4])
    memories = tuple(item[4] for item in selected)
    content = "\n".join(memory.canonical_content for memory in memories)
    if len(content) > 4096:
        raise ValueError("episode_summary_limit")
    fingerprint = _digest([EPISODE_POLICY, [
        [m.memory_id, m.canonical_content, m.source_event_ids,
         [r.model_dump(mode="json") for r in m.provenance]] for m in memories
    ]])
    return memories, content, fingerprint


def refresh_episode(store, connection, scope, topic_id):
    memories, content, fingerprint = episode_snapshot(store, connection, scope, topic_id)
    current = connection.execute(
        """SELECT * FROM mind_summary_revisions WHERE tenant_id=? AND namespace=?
           AND topic_id=? AND retired_at IS NULL""", (scope.tenant_id, scope.namespace, topic_id),
    ).fetchone()
    if not memories or current is not None and current["source_fingerprint"] == fingerprint:
        return 0
    number = connection.execute(
        "SELECT COALESCE(MAX(revision_number),0)+1 FROM mind_summary_revisions WHERE tenant_id=? AND namespace=? AND topic_id=?",
        (scope.tenant_id, scope.namespace, topic_id),
    ).fetchone()[0]
    if current is not None:
        connection.execute(
            "UPDATE mind_summary_revisions SET retired_at=oomp_recorded_at() WHERE tenant_id=? AND namespace=? AND revision_id=?",
            (scope.tenant_id, scope.namespace, current["revision_id"]),
        )
    revision_id = "summary-" + _digest([scope.tenant_id, scope.namespace, topic_id, number, fingerprint])
    connection.execute(
        """INSERT INTO mind_summary_revisions (tenant_id,namespace,revision_id,topic_id,revision_number,
           content,source_fingerprint,policy_version,recorded_at,retired_at)
           VALUES (?,?,?,?,?,?,?,?,oomp_recorded_at(),NULL)""",
        (scope.tenant_id, scope.namespace, revision_id, topic_id, number, content, fingerprint, EPISODE_POLICY),
    )
    for memory in memories:
        connection.execute(
            "INSERT INTO mind_summary_sources (tenant_id,namespace,revision_id,memory_id,event_id) VALUES (?,?,?,?,?)",
            (scope.tenant_id, scope.namespace, revision_id, memory.memory_id, memory.source_event_ids[0]),
        )
    return 1


def assign_episode(store, connection, scope, event, memory):
    base, label = episode_base(scope, event, memory.metadata["source_span"]["quote"])
    # Replay retains membership; overflow shards bound text and source count.
    existing = connection.execute(
        "SELECT topic_id FROM topic_memberships WHERE tenant_id=? AND namespace=? AND memory_id=? LIMIT 1",
        (scope.tenant_id, scope.namespace, memory.memory_id),
    ).fetchone()
    if existing is not None:
        return existing[0]
    topic = base
    for attempt in range(17):
        rows = connection.execute(
            """SELECT length(m.canonical_content) AS chars FROM topic_memberships t JOIN memories m
               ON m.tenant_id=t.tenant_id AND m.namespace=t.namespace AND m.memory_id=t.memory_id
               WHERE t.tenant_id=? AND t.namespace=? AND t.topic_id=? LIMIT 17""",
            (scope.tenant_id, scope.namespace, topic),
        ).fetchall()
        if len(rows) < 16 and sum(row[0] + 1 for row in rows) + len(memory.canonical_content) + 1 <= 4000:
            break
        topic = "p2episode-" + hashlib.sha256(f"{base}:{event.event_id}:{attempt}".encode()).hexdigest()[:40]
    else:
        raise ValueError("episode_shard_limit")
    connection.execute(
        """INSERT OR IGNORE INTO topics (tenant_id,namespace,topic_id,name,parent_id,recorded_at)
           VALUES (?,?,?,?,NULL,oomp_recorded_at())""", (scope.tenant_id, scope.namespace, topic, "P2 " + label + " episode"),
    )
    connection.execute(
        "INSERT OR IGNORE INTO topic_memberships (tenant_id,namespace,topic_id,memory_id,recorded_at) VALUES (?,?,?,?,oomp_recorded_at())",
        (scope.tenant_id, scope.namespace, topic, memory.memory_id),
    )
    return topic
