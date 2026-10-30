"""Atomic acquisition writes using schema v5 and its existing governance."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from oomp.domain.enums import MemoryType
from oomp.domain.memories import MemoryWrite, ProcessingResult
from oomp.domain.models import MemoryNode
from oomp.ingestion.canonicalization import canonicalize
from oomp.ingestion.extraction import _extract_statement
from oomp.storage.memory_store import _event_in_scope, _resolve_entity
from oomp.storage.mind_projection_store import SQLiteMindProjectionStore
from oomp.storage.mind_store import LostLeaseError
from oomp.storage.sqlite import _authorized, _timestamp, _translate_sqlite_errors

from .episodes import assign_episode, refresh_episode, source_retracted
from .rules import promotion, proposal_for
from .validator import CandidateValidator


def _new_node(scope, event, proposal, *, episode):
    decision, reason = promotion(proposal)
    span = proposal.source_spans[0]
    if episode:
        content = f"{event.occurred_at.isoformat()} {event.source_type.value} [{proposal.assertion_kind}; {decision}]: {span.quote}"
        kind = MemoryType.EPISODIC
    else:
        content = f"User-claimed {proposal.predicate} [{proposal.assertion_kind}]: {span.quote}"
        kind = (MemoryType.PROFILE if proposal.memory_category == "profile" else
                MemoryType.PROCEDURAL if proposal.memory_category == "procedural" else MemoryType.PROJECT_STATE)
    identity = [scope.tenant_id, scope.namespace, scope.principal_id, kind.value, content,
                event.event_id if episode else None, span.start if episode else None]
    key = hashlib.sha256(json.dumps(identity, ensure_ascii=True).encode()).hexdigest()
    metadata = {"attribution": event.source_type.value, "verified": False, "canonicalization_version": "p2.1",
                "assertion_kind": proposal.assertion_kind, "category": proposal.memory_category,
                "predicate": proposal.predicate, "importance": proposal.importance,
                "sensitivity": proposal.sensitivity,
                "promotion": decision, "promotion_reason": reason, "validity": "uncertain",
                "principal_id": scope.principal_id}
    if episode:
        metadata.update(p2_episode=True, source_span=span.model_dump(mode="json"),
                        occurred_at=event.occurred_at.isoformat(), session_id=event.source_reference.session_id)
    if proposal.predicate == "alias":
        metadata.update(identity_claim="display-alias", authenticated=False)
    return MemoryNode(memory_id="mem-" + key, tenant_id=scope.tenant_id, namespace=scope.namespace,
        memory_type=kind, canonical_content=content, canonical_key="p2:" + key,
        source_event_ids=(event.event_id,), provenance=(event.source_reference,),
        created_at=event.ingested_at, updated_at=event.ingested_at, metadata=metadata)


def candidate_writes(scope, event, proposal, config):
    decision, _ = promotion(proposal)
    method = "mind2." + proposal.extractor_provider + ".v1"
    if proposal.model_version:
        method += "." + hashlib.sha256(proposal.model_version.encode()).hexdigest()[:16]
    result = []
    if decision == "canonical":
        legacy = _extract_statement(event, proposal.source_spans[0])
        result.append(MemoryWrite(memory=canonicalize(legacy, event) if legacy else _new_node(scope, event, proposal, episode=False),
            entities=legacy.entities if legacy else (), source_span=proposal.source_spans[0], extraction_method=method))
    if config.retain_episodes:
        # The source episode's identity and interpretation are provider-neutral.
        # A richer model claim is a separate grounded canonical record.
        base = proposal_for(scope, event, proposal.source_spans[0])
        result.append(MemoryWrite(memory=_new_node(scope, event, base, episode=True),
            source_span=proposal.source_spans[0], extraction_method=method))
    return tuple(result)


class UnderstandingStore(SQLiteMindProjectionStore):
    def __init__(self, path=None, *, clock=None):
        super().__init__(path)
        self.acquisition_clock = clock or (lambda: datetime.now(timezone.utc))

    def _guard_job(self, connection, scope, job):
        if job is None:
            return
        row = connection.execute(
            "SELECT status,lease_owner,fencing_token,lease_expires_at FROM mind_jobs WHERE tenant_id=? AND namespace=? AND job_id=?",
            (scope.tenant_id, scope.namespace, job.job_id),
        ).fetchone()
        now = _timestamp(self.acquisition_clock())
        if (row is None or row["status"] != "running" or row["lease_owner"] != job.lease_owner
                or row["fencing_token"] != job.fencing_token or row["lease_expires_at"] <= now):
            raise LostLeaseError("extraction_job_lease_lost")

    @_translate_sqlite_errors
    def commit(self, scope, event, proposals, config, *, job=None):
        scope = _authorized(scope)
        with self._graph_transaction() as connection:
            self._require_v5(connection)
            self._guard_job(connection, scope, job)
            current = _event_in_scope(connection, scope, event.event_id)
            if current != event:
                raise ValueError("extraction_source_changed")
            if source_retracted(connection, scope, event.event_id):
                return ProcessingResult(event_id=event.event_id, reason="source_retracted"), 0
            accepted = CandidateValidator(config).validate(scope, current, proposals)
            created = reused = proofs = 0
            memory_ids, topics = [], set()
            for proposal in accepted:
                for write in candidate_writes(scope, current, proposal, config):
                    memory, new, added = self._upsert_in_transaction(connection, scope, write.memory,
                        source_spans={event.event_id: write.source_span}, extraction_method=write.extraction_method)
                    created += int(new)
                    reused += int(not new)
                    proofs += added
                    memory_ids.append(memory.memory_id)
                    for mention in write.entities:
                        entity, _ = _resolve_entity(connection, scope, mention, current)
                        connection.execute(
                            "INSERT OR IGNORE INTO memory_entities (tenant_id,namespace,memory_id,entity_id) VALUES (?,?,?,?)",
                            (scope.tenant_id, scope.namespace, memory.memory_id, entity.entity_id),
                        )
                    if memory.metadata.get("p2_episode") is True:
                        topics.add(assign_episode(self, connection, scope, current, memory))
            revisions = sum(refresh_episode(self, connection, scope, topic) for topic in sorted(topics))
            if accepted and connection.execute(
                """SELECT 1 FROM mind_maintenance_audit WHERE tenant_id=? AND namespace=?
                   AND target_id=? AND target_type='event' AND operation_type='mind2.acquisition' LIMIT 1""",
                (scope.tenant_id, scope.namespace, event.event_id),
            ).fetchone() is None:
                connection.execute(
                    """INSERT INTO mind_maintenance_audit
                       (tenant_id,namespace,job_id,operation_type,policy_version,actor_id,
                        recorded_at,status,error_code,affected_count,target_type,target_id)
                       VALUES (?,?,?,'mind2.acquisition','mind2.v1',?,oomp_recorded_at(),'completed',NULL,?,'event',?)""",
                    (scope.tenant_id, scope.namespace, job.job_id if job else None,
                     scope.principal_id, len(accepted), event.event_id),
                )
            self._guard_job(connection, scope, job)
            return ProcessingResult(event_id=event.event_id, candidates_extracted=len(accepted),
                memories_created=created, memories_reused=reused, evidence_links_added=proofs,
                memory_ids=tuple(dict.fromkeys(memory_ids))), revisions
