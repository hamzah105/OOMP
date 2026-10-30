"""Explicit selection and digest-bound preview, never private-history discovery."""
from __future__ import annotations

import hashlib
import json

from pydantic import TypeAdapter

from oomp.domain.models import Identifier
from oomp.mind.contracts import JobType
from oomp.mind.scheduler import POLICY_VERSIONS, job_identity
from oomp.storage.mind_store import SQLiteMindStore
from oomp.storage.memory_store import _event_in_scope
from oomp.storage.sqlite import _authorized

from .episodes import source_retracted
from .rules import blocked_reason


def _plan(connection, queue, scope, event_ids, config):
    identities, eligible, excluded = [], [], []
    for identifier in event_ids:
        event = _event_in_scope(connection, scope, identifier)
        reason = blocked_reason(scope, event, config)
        if source_retracted(connection, scope, identifier):
            reason = "source_retracted"
        fingerprint = hashlib.sha256(event.model_dump_json().encode()).hexdigest()
        identities.append([identifier, fingerprint, reason])
        if reason:
            excluded.append({"event_id": identifier, "code": reason})
        else:
            eligible.append(identifier)
    digest = hashlib.sha256(json.dumps([scope.model_dump(mode="json"), config.identity, identities], sort_keys=True).encode()).hexdigest()
    return {"version": "mind2.reprocess.v1", "plan_digest": digest, "selected_count": len(event_ids),
            "eligible_event_ids": eligible, "excluded": excluded, "configuration_id": config.identity,
            "model_route": "literal-loopback" if config.mode == "local-llm" else "offline",
            "requires_already_consented_sources": True, "jobs_started": False}


def reprocess(path, scope, event_ids, config, *, apply=False, consented=False, plan_digest=None):
    scope = _authorized(scope)
    if not isinstance(event_ids, (list, tuple)) or not 1 <= len(event_ids) <= 100:
        raise ValueError("reprocess_selection_limit")
    ids = tuple(TypeAdapter(Identifier).validate_python(i) for i in event_ids)
    if len(set(ids)) != len(ids):
        raise ValueError("reprocess_duplicate_selection")
    queue = SQLiteMindStore(path)
    if not apply:
        with queue._read() as connection:
            return _plan(connection, queue, scope, ids, config)
    if not consented or not isinstance(plan_digest, str):
        raise ValueError("reprocess_consent_and_preview_required")
    # Recompute the full plan and enqueue the whole bounded batch atomically.
    with queue._tx() as connection:
        plan = _plan(connection, queue, scope, ids, config)
        if plan_digest != plan["plan_digest"]:
            raise ValueError("reprocess_plan_changed")
        jobs = []
        for identifier in plan["eligible_event_ids"]:
            job = queue._enqueue_in_tx(connection, scope, JobType.EXTRACT_EVENT, "event", identifier,
                idempotency_key=job_identity(scope, JobType.EXTRACT_EVENT, identifier, "mind2-" + plan_digest),
                policy_version=POLICY_VERSIONS[JobType.EXTRACT_EVENT],
                config={"understanding": config.identity}, priority=0, max_attempts=3, available_at=None)
            jobs.append(job.job_id)
        return {**plan, "job_ids": jobs, "enqueued": len(jobs), "jobs_started": False}


def episodes(path, scope, *, limit=20, episode_id=None, show_content=False):
    from .storage import UnderstandingStore
    scope = _authorized(scope)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("episode_limit")
    store = UnderstandingStore(path)
    with store._graph_read() as connection:
        if episode_id:
            identifiers = [TypeAdapter(Identifier).validate_python(episode_id)]
        else:
            identifiers = [row[0] for row in connection.execute(
                """SELECT topic_id FROM mind_summary_revisions WHERE tenant_id=? AND namespace=?
                   AND policy_version='episode-extractive.v1' AND retired_at IS NULL
                   ORDER BY recorded_at DESC,topic_id LIMIT ?""", (scope.tenant_id, scope.namespace, limit))]
    result = []
    for identifier in identifiers:
        summary = store.get_summary(scope, identifier)
        if summary is None or summary.policy_version != "episode-extractive.v1":
            continue
        item = {"episode_id": identifier, "revision_id": summary.revision_id,
                "source_count": len(summary.source_event_ids), "clause_count": len(summary.source_memory_ids),
                "recorded_at": summary.recorded_at.isoformat(), "freshness": summary.freshness,
                "unresolved": "tentative/question/review clauses remain unresolved; no decision inferred"}
        if show_content:
            item.update(content=summary.content, source_event_ids=list(summary.source_event_ids),
                        sources=[s.model_dump(mode="json") for s in summary.sources])
        result.append(item)
    return result
