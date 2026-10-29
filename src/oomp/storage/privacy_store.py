"""Narrow, locally authorized privacy erasure of one source event.

The plan never contains source text. Confirmation recomputes its complete scoped
dependency identity inside a SQLite write transaction and fails closed when a
shared or graph dependency cannot be proved safe.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import TypeAdapter

from oomp.domain.models import AuthorizedScope, Identifier
from oomp.ingestion.canonicalization import canonicalize
from oomp.ingestion.extraction import DeterministicExtractor, eligibility_reason
from .errors import StorageError, ScopeMismatchError
from .memory_store import SQLiteMemoryStore, _contains_name, _memory_fingerprint
from .graph_store import _source_retracted
from .migrations import MIGRATION_1, verify_v5
from .mind_store import SQLiteMindStore
from .sqlite import _authorized, _canonical_json, _timestamp, _translate_sqlite_errors


_ID = TypeAdapter(Identifier)
_MAX_DEPENDENCIES = 1000


class ErasureBlockedError(StorageError):
    """The scoped dependencies cannot be removed safely by this narrow workflow."""


class StaleErasurePlanError(StorageError):
    """The approved dependency plan changed before confirmation."""


@dataclass(frozen=True)
class ErasurePlan:
    tenant_id: str
    namespace: str
    event_id: str
    plan_digest: str
    delete_memory_ids: tuple[str, ...]
    detach_memory_ids: tuple[str, ...]
    delete_summary_revision_ids: tuple[str, ...]
    delete_review_proposal_ids: tuple[str, ...]
    cancel_job_ids: tuple[str, ...]
    delete_alias_count: int
    delete_entity_ids: tuple[str, ...]
    affected_fts_docs: int
    affected_embeddings: int
    blocked_reason: str | None


@dataclass(frozen=True)
class ErasureResult:
    operation_id: str
    event_id: str
    deleted_memories: int
    detached_memories: int
    deleted_summary_revisions: int
    cancelled_jobs: int


class SQLitePrivacyStore(SQLiteMindStore):
    """Privileged event erasure is intentionally absent from ordinary stores."""

    def _plan_in_connection(
        self, connection: sqlite3.Connection, scope: AuthorizedScope, event_id: str,
    ) -> ErasurePlan:
        event_row = connection.execute(
            "SELECT * FROM events WHERE tenant_id=? AND namespace=? AND event_id=?",
            (scope.tenant_id,scope.namespace,event_id),
        ).fetchone()
        if event_row is None:
            raise ScopeMismatchError("event is absent from authorized scope")
        event = self._decode(event_row)
        proof_rows = connection.execute(
            """SELECT memory_id FROM memory_sources WHERE tenant_id=? AND namespace=?
               AND event_id=? ORDER BY memory_id LIMIT ?""",
            (scope.tenant_id,scope.namespace,event_id,_MAX_DEPENDENCIES+1),
        ).fetchall()
        if len(proof_rows)>_MAX_DEPENDENCIES:
            raise ErasureBlockedError("dependency_limit")
        delete_memories=[]
        detach_memories=[]
        proof_manifest=[]
        blocked=None
        proof_work=0
        for proof in proof_rows:
            memory_id=proof["memory_id"]
            sources=connection.execute(
                """SELECT event_id FROM memory_sources WHERE tenant_id=? AND namespace=?
                   AND memory_id=? ORDER BY ordinal LIMIT ?""",
                (scope.tenant_id,scope.namespace,memory_id,_MAX_DEPENDENCIES+1),
            ).fetchall()
            proof_work += len(sources)
            if proof_work>_MAX_DEPENDENCIES:
                raise ErasureBlockedError("dependency_limit")
            source_ids=tuple(row[0] for row in sources)
            proof_manifest.append((memory_id,source_ids))
            if len(source_ids)==1:
                delete_memories.append(memory_id)
            else:
                detach_memories.append(memory_id)
                if not self._shared_memory_safe(connection,scope,memory_id,event_id,source_ids):
                    blocked="unsupported_shared_proof"
        affected=set(delete_memories)|set(detach_memories)
        edge_ids=set()
        for memory_id in affected:
            edges=connection.execute(
                """SELECT edge_id FROM memory_edges WHERE tenant_id=? AND namespace=?
                   AND (source_node_id=? OR target_node_id=?) LIMIT ?""",
                (scope.tenant_id,scope.namespace,memory_id,memory_id,_MAX_DEPENDENCIES+1),
            ).fetchall()
            edge_ids.update(row[0] for row in edges)
        edge_ids.update(row[0] for row in connection.execute(
            """SELECT edge_id FROM edge_evidence WHERE tenant_id=? AND namespace=?
               AND event_id=? LIMIT ?""",
            (scope.tenant_id,scope.namespace,event_id,_MAX_DEPENDENCIES+1),
        ))
        if len(edge_ids)>_MAX_DEPENDENCIES:
            raise ErasureBlockedError("dependency_limit")
        if edge_ids:
            blocked=blocked or "graph_dependency"
        summary_ids=set()
        for row in connection.execute(
            """SELECT DISTINCT revision_id FROM mind_summary_sources WHERE tenant_id=?
               AND namespace=? AND event_id=? LIMIT ?""",
            (scope.tenant_id,scope.namespace,event_id,_MAX_DEPENDENCIES+1),
        ):
            summary_ids.add(row[0])
        for memory_id in delete_memories:
            for row in connection.execute(
                """SELECT DISTINCT revision_id FROM mind_summary_sources WHERE tenant_id=?
                   AND namespace=? AND memory_id=? LIMIT ?""",
                (scope.tenant_id,scope.namespace,memory_id,_MAX_DEPENDENCIES+1),
            ):
                summary_ids.add(row[0])
        if len(summary_ids)>_MAX_DEPENDENCIES:
            raise ErasureBlockedError("dependency_limit")
        review_ids=set()
        review_rows = connection.execute(
            """SELECT proposal_id,source_memory_id,target_memory_id,source_event_ids_json
               FROM mind_review_proposals WHERE tenant_id=? AND namespace=?
               LIMIT ?""",
            (scope.tenant_id,scope.namespace,_MAX_DEPENDENCIES+1),
        ).fetchall()
        if len(review_rows)>_MAX_DEPENDENCIES:
            raise ErasureBlockedError("dependency_limit")
        for row in review_rows:
            try:
                event_ids=json.loads(row["source_event_ids_json"])
            except (ValueError,TypeError):
                raise ErasureBlockedError("invalid_review_dependency") from None
            if (event_id in event_ids or row["source_memory_id"] in delete_memories
                or row["target_memory_id"] in delete_memories):
                review_ids.add(row["proposal_id"])
        if len(review_ids)>_MAX_DEPENDENCIES:
            raise ErasureBlockedError("dependency_limit")
        jobs=connection.execute(
            """SELECT job_id,status,fencing_token FROM mind_jobs WHERE tenant_id=?
               AND namespace=? AND target_type='event' AND target_id=?
               ORDER BY job_id LIMIT ?""",
            (scope.tenant_id,scope.namespace,event_id,_MAX_DEPENDENCIES+1),
        ).fetchall()
        if len(jobs)>_MAX_DEPENDENCIES:
            raise ErasureBlockedError("dependency_limit")
        cancel_jobs=tuple(row["job_id"] for row in jobs if row["status"] in
                          ("queued","retry_wait","running"))
        aliases=connection.execute(
            """SELECT entity_type,normalized_alias,entity_id FROM entity_aliases
               WHERE tenant_id=? AND namespace=? AND source_event_id=?
               ORDER BY entity_type,normalized_alias LIMIT ?""",
            (scope.tenant_id,scope.namespace,event_id,_MAX_DEPENDENCIES+1),
        ).fetchall()
        if len(aliases)>_MAX_DEPENDENCIES:
            raise ErasureBlockedError("dependency_limit")
        alias_keys=tuple((row["entity_type"],row["normalized_alias"]) for row in aliases)
        entity_ids=set(row["entity_id"] for row in aliases)
        for memory_id in delete_memories:
            entity_ids.update(row[0] for row in connection.execute(
                """SELECT entity_id FROM memory_entities WHERE tenant_id=?
                   AND namespace=? AND memory_id=? LIMIT ?""",
                (scope.tenant_id,scope.namespace,memory_id,_MAX_DEPENDENCIES+1),
            ))
        if len(entity_ids)>_MAX_DEPENDENCIES:
            raise ErasureBlockedError("dependency_limit")
        delete_entities=[]
        entity_manifest=[]
        for entity_id in sorted(entity_ids):
            links=tuple(row[0] for row in connection.execute(
                """SELECT memory_id FROM memory_entities WHERE tenant_id=?
                   AND namespace=? AND entity_id=? ORDER BY memory_id LIMIT ?""",
                (scope.tenant_id,scope.namespace,entity_id,_MAX_DEPENDENCIES+1),
            ))
            if len(links)>_MAX_DEPENDENCIES:
                raise ErasureBlockedError("dependency_limit")
            surviving=tuple(mid for mid in links if mid not in delete_memories)
            entity_manifest.append((entity_id,links))
            if surviving:
                if not self._entity_survives(connection,scope,entity_id,event_id,surviving):
                    blocked=blocked or "unsupported_entity_proof"
            else:
                other_alias=connection.execute(
                    """SELECT 1 FROM entity_aliases WHERE tenant_id=? AND namespace=?
                       AND entity_id=? AND source_event_id<>? LIMIT 1""",
                    (scope.tenant_id,scope.namespace,entity_id,event_id),
                ).fetchone()
                if other_alias:
                    if not self._entity_survives(connection,scope,entity_id,event_id,()):
                        blocked=blocked or "unsupported_entity_proof"
                else:
                    delete_entities.append(entity_id)
        fts_docs=0
        embedding_count=0
        for memory_id in delete_memories:
            fts_docs+=int(connection.execute(
                """SELECT COUNT(*) FROM memory_fts_docs WHERE tenant_id=? AND namespace=?
                   AND memory_id=?""",
                (scope.tenant_id,scope.namespace,memory_id),
            ).fetchone()[0])
            embedding_count+=int(connection.execute(
                """SELECT COUNT(*) FROM memory_embeddings WHERE tenant_id=? AND namespace=?
                   AND memory_id=?""",
                (scope.tenant_id,scope.namespace,memory_id),
            ).fetchone()[0])
        manifest={
            "scope":[scope.tenant_id,scope.namespace],"event_id":event_id,
            "proof":proof_manifest,"edges":sorted(edge_ids),"summary_ids":sorted(summary_ids),
            "review_ids":sorted(review_ids),"jobs":[tuple(row) for row in jobs],
            "aliases":alias_keys,"entities":entity_manifest,
            "delete_entities":sorted(delete_entities),"fts_docs":fts_docs,
            "embeddings":embedding_count,
            "outbox":tuple(connection.execute(
                """SELECT inserted_at,dispatched_at FROM mind_event_outbox
                   WHERE tenant_id=? AND namespace=? AND event_id=?""",
                (scope.tenant_id,scope.namespace,event_id),
            ).fetchone() or ()),
            "blocked":blocked,
        }
        digest=hashlib.sha256(_canonical_json(manifest).encode("utf-8")).hexdigest()
        return ErasurePlan(
            scope.tenant_id,scope.namespace,event_id,digest,
            tuple(sorted(delete_memories)),tuple(sorted(detach_memories)),
            tuple(sorted(summary_ids)),tuple(sorted(review_ids)),cancel_jobs,
            len(alias_keys),tuple(sorted(delete_entities)),fts_docs,embedding_count,blocked,
        )

    @staticmethod
    def _shared_memory_safe(
        connection: sqlite3.Connection, scope: AuthorizedScope,
        memory_id: str, erased_event_id: str, source_ids: tuple[str,...],
    ) -> bool:
        row=connection.execute(
            "SELECT * FROM memories WHERE tenant_id=? AND namespace=? AND memory_id=?",
            (scope.tenant_id,scope.namespace,memory_id),
        ).fetchone()
        if row is None:
            return False
        memory=SQLiteMemoryStore._read_memory(connection,scope,row)
        if memory.tags or memory.status.value!="active":
            return False
        if connection.execute(
            """SELECT 1 FROM memory_entities WHERE tenant_id=? AND namespace=?
               AND memory_id=? LIMIT 1""",
            (scope.tenant_id,scope.namespace,memory_id),
        ).fetchone():
            return False
        extractor=DeterministicExtractor()
        for source_id in source_ids:
            if source_id==erased_event_id or _source_retracted(connection,scope,memory_id,source_id):
                continue
            event_row=connection.execute(
                "SELECT * FROM events WHERE tenant_id=? AND namespace=? AND event_id=?",
                (scope.tenant_id,scope.namespace,source_id),
            ).fetchone()
            if event_row is None:
                return False
            source=SQLiteMindStore._decode(event_row)
            if memory.metadata.get("canonicalization_version") == "p2.1":
                from oomp.understanding.contracts import ExtractionConfiguration
                from oomp.understanding.rules import RulesExtractor
                from oomp.understanding.storage import candidate_writes
                try:
                    original_scope = AuthorizedScope(
                        tenant_id=scope.tenant_id, namespace=scope.namespace,
                        principal_id=memory.metadata["principal_id"],
                    )
                    config = ExtractionConfiguration()
                    for candidate in RulesExtractor(config).propose(original_scope, source):
                        for write in candidate_writes(original_scope, source, candidate, config):
                            if (_memory_fingerprint(write.memory) == row["payload_fingerprint"]
                                    and write.memory.canonical_key == memory.canonical_key):
                                return True
                    # Re-prove a supported literal model refinement using the
                    # independent validator. This is deterministic source proof,
                    # not an inference request or a claim that a model ran here.
                    from oomp.understanding.rules import clauses, proposal_for
                    from oomp.understanding.validator import CandidateValidator
                    proof_config = ExtractionConfiguration(mode="local-llm", model="source-proof")
                    for span in clauses(source.content):
                        candidate = proposal_for(original_scope, source, span, provider="ollama", model="source-proof",
                            hints={"predicate": memory.metadata["predicate"],
                                   "memory_category": memory.metadata["category"],
                                   "assertion_kind": memory.metadata["assertion_kind"]})
                        try:
                            CandidateValidator(proof_config).validate(original_scope, source, (candidate,))
                        except ValueError:
                            continue
                        for write in candidate_writes(original_scope, source, candidate, proof_config):
                            if (_memory_fingerprint(write.memory) == row["payload_fingerprint"]
                                    and write.memory.canonical_key == memory.canonical_key):
                                return True
                except (ValueError, TypeError, KeyError):
                    return False
            if eligibility_reason(source) is None:
                for candidate in extractor.extract_candidates(scope,source):
                    derived=canonicalize(candidate,source)
                    if (_memory_fingerprint(derived)==row["payload_fingerprint"] and
                        derived.canonical_key==memory.canonical_key):
                        return True
            # A trusted manual fact is safe only when the entire surviving source
            # is exactly the canonical body and metadata is the fixed attribution.
            if (source.content==memory.canonical_content and not memory.tags
                and memory.metadata=={"attribution":source.source_type.value,"verified":False}):
                return True
        return False

    @staticmethod
    def _entity_survives(
        connection: sqlite3.Connection, scope: AuthorizedScope, entity_id: str,
        erased_event_id: str, surviving_memory_ids: tuple[str,...],
    ) -> bool:
        row=connection.execute(
            """SELECT canonical_name FROM entities WHERE tenant_id=? AND namespace=?
               AND entity_id=?""",
            (scope.tenant_id,scope.namespace,entity_id),
        ).fetchone()
        if row is None:
            return False
        name=row["canonical_name"]
        for memory_id in surviving_memory_ids:
            evidence_rows = connection.execute(
                """SELECT e.content FROM memory_sources ms
                   JOIN events e ON e.tenant_id=ms.tenant_id AND e.namespace=ms.namespace
                                AND e.event_id=ms.event_id
                   WHERE ms.tenant_id=? AND ms.namespace=? AND ms.memory_id=?
                     AND ms.event_id<>? LIMIT ?""",
                (scope.tenant_id,scope.namespace,memory_id,erased_event_id,_MAX_DEPENDENCIES+1),
            ).fetchall()
            if len(evidence_rows)>_MAX_DEPENDENCIES:
                raise ErasureBlockedError("dependency_limit")
            for source in evidence_rows:
                if _contains_name(source[0],name):
                    return True
        alias_rows = connection.execute(
            """SELECT e.content FROM entity_aliases a JOIN events e
                 ON e.tenant_id=a.tenant_id AND e.namespace=a.namespace
                AND e.event_id=a.source_event_id
               WHERE a.tenant_id=? AND a.namespace=? AND a.entity_id=?
                 AND a.source_event_id<>? LIMIT ?""",
            (scope.tenant_id,scope.namespace,entity_id,erased_event_id,_MAX_DEPENDENCIES+1),
        ).fetchall()
        if len(alias_rows)>_MAX_DEPENDENCIES:
            raise ErasureBlockedError("dependency_limit")
        for source in alias_rows:
            if _contains_name(source[0],name):
                return True
        return False

    @_translate_sqlite_errors
    def erase_plan(self, scope: AuthorizedScope, event_id: str) -> ErasurePlan:
        scope=_authorized(scope)
        event_id=_ID.validate_python(event_id)
        with closing(self._connect("ro")) as connection:
            connection.execute("BEGIN")
            try:
                self._require_v5(connection)
                return self._plan_in_connection(connection,scope,event_id)
            finally:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
    @_translate_sqlite_errors
    def erase_confirm(
        self, scope: AuthorizedScope, event_id: str, plan_digest: str, *,
        confirm: bool = False,
    ) -> ErasureResult:
        scope=_authorized(scope)
        event_id=_ID.validate_python(event_id)
        if confirm is not True:
            raise ValueError("explicit erasure confirmation is required")
        if not isinstance(plan_digest,str) or len(plan_digest)!=64 or any(
            c not in "0123456789abcdef" for c in plan_digest
        ):
            raise ValueError("a current erasure plan digest is required")
        with self._tx() as connection:
            plan=self._plan_in_connection(connection,scope,event_id)
            if plan.plan_digest!=plan_digest:
                raise StaleErasurePlanError("erasure dependencies changed after planning")
            if plan.blocked_reason is not None:
                raise ErasureBlockedError(plan.blocked_reason)
            event=connection.execute(
                """SELECT idempotency_key FROM events WHERE tenant_id=? AND namespace=?
                   AND event_id=?""",
                (scope.tenant_id,scope.namespace,event_id),
            ).fetchone()
            if event is None:
                raise StaleErasurePlanError("erasure target no longer exists")
            now=_timestamp(datetime.now(timezone.utc))
            operation_id="erase-"+uuid.uuid4().hex
            for job_id in plan.cancel_job_ids:
                row=connection.execute(
                    """SELECT * FROM mind_jobs WHERE tenant_id=? AND namespace=?
                       AND job_id=?""",
                    (scope.tenant_id,scope.namespace,job_id),
                ).fetchone()
                if row is None or row["status"] not in ("queued","retry_wait","running"):
                    raise StaleErasurePlanError("pending erasure job changed")
                if row["status"]=="running":
                    connection.execute(
                        """UPDATE mind_job_attempts SET ended_at=?,status='cancelled',
                           error_code='cancelled'
                           WHERE tenant_id=? AND namespace=? AND job_id=?
                             AND attempt_number=? AND status='running'""",
                        (now,scope.tenant_id,scope.namespace,job_id,row["attempt_count"]),
                    )
                connection.execute(
                    """UPDATE mind_jobs SET status='cancelled',lease_owner=NULL,
                       lease_expires_at=NULL,fencing_token=fencing_token+1,
                       updated_at=?,last_error_code='cancelled'
                       WHERE tenant_id=? AND namespace=? AND job_id=?""",
                    (now,scope.tenant_id,scope.namespace,job_id),
                )
            for revision_id in plan.delete_summary_revision_ids:
                connection.execute(
                    """DELETE FROM mind_summary_sources WHERE tenant_id=?
                       AND namespace=? AND revision_id=?""",
                    (scope.tenant_id,scope.namespace,revision_id),
                )
                connection.execute(
                    """DELETE FROM mind_summary_revisions WHERE tenant_id=?
                       AND namespace=? AND revision_id=?""",
                    (scope.tenant_id,scope.namespace,revision_id),
                )
            for proposal_id in plan.delete_review_proposal_ids:
                connection.execute(
                    """DELETE FROM mind_review_proposals WHERE tenant_id=?
                       AND namespace=? AND proposal_id=?""",
                    (scope.tenant_id,scope.namespace,proposal_id),
                )
            for memory_id in plan.delete_memory_ids:
                doc=connection.execute(
                    """SELECT doc_id FROM memory_fts_docs WHERE tenant_id=?
                       AND namespace=? AND memory_id=?""",
                    (scope.tenant_id,scope.namespace,memory_id),
                ).fetchone()
                if doc is not None:
                    connection.execute("DELETE FROM memory_fts WHERE rowid=?",(doc[0],))
                    connection.execute(
                        """DELETE FROM memory_fts_docs WHERE tenant_id=?
                           AND namespace=? AND memory_id=?""",
                        (scope.tenant_id,scope.namespace,memory_id),
                    )
                for table in (
                    "memory_embeddings","mind_retractions","topic_memberships",
                    "memory_entities","memory_source_recordings","memory_recordings",
                ):
                    connection.execute(
                        f"DELETE FROM {table} WHERE tenant_id=? AND namespace=? AND memory_id=?",
                        (scope.tenant_id,scope.namespace,memory_id),
                    )
                connection.execute(
                    """DELETE FROM memory_sources WHERE tenant_id=? AND namespace=?
                       AND memory_id=?""",
                    (scope.tenant_id,scope.namespace,memory_id),
                )
                connection.execute(
                    """DELETE FROM memories WHERE tenant_id=? AND namespace=?
                       AND memory_id=?""",
                    (scope.tenant_id,scope.namespace,memory_id),
                )
            for memory_id in plan.detach_memory_ids:
                connection.execute(
                    """DELETE FROM mind_retractions WHERE tenant_id=? AND namespace=?
                       AND memory_id=? AND event_id=?""",
                    (scope.tenant_id,scope.namespace,memory_id,event_id),
                )
                connection.execute(
                    """DELETE FROM memory_source_recordings WHERE tenant_id=?
                       AND namespace=? AND memory_id=? AND event_id=?""",
                    (scope.tenant_id,scope.namespace,memory_id,event_id),
                )
                connection.execute(
                    """DELETE FROM memory_sources WHERE tenant_id=? AND namespace=?
                       AND memory_id=? AND event_id=?""",
                    (scope.tenant_id,scope.namespace,memory_id,event_id),
                )
                survivors=connection.execute(
                    """SELECT event_id,ordinal FROM memory_sources WHERE tenant_id=?
                       AND namespace=? AND memory_id=? ORDER BY ordinal""",
                    (scope.tenant_id,scope.namespace,memory_id),
                ).fetchall()
                if not survivors or len(survivors)>_MAX_DEPENDENCIES:
                    raise ErasureBlockedError("shared_dependency_changed")
                # Temporarily move ordinals above their original bounded range,
                # then assign a contiguous order without violating UNIQUE.
                for row in survivors:
                    connection.execute(
                        """UPDATE memory_sources SET ordinal=ordinal+1001
                           WHERE tenant_id=? AND namespace=? AND memory_id=?
                             AND event_id=?""",
                        (scope.tenant_id,scope.namespace,memory_id,row["event_id"]),
                    )
                for ordinal,row in enumerate(survivors):
                    connection.execute(
                        """UPDATE memory_sources SET ordinal=? WHERE tenant_id=?
                           AND namespace=? AND memory_id=? AND event_id=?""",
                        (ordinal,scope.tenant_id,scope.namespace,memory_id,row["event_id"]),
                    )
            connection.execute(
                """DELETE FROM entity_aliases WHERE tenant_id=? AND namespace=?
                   AND source_event_id=?""",
                (scope.tenant_id,scope.namespace,event_id),
            )
            for entity_id in plan.delete_entity_ids:
                connection.execute(
                    """DELETE FROM entity_aliases WHERE tenant_id=? AND namespace=?
                       AND entity_id=?""",
                    (scope.tenant_id,scope.namespace,entity_id),
                )
                connection.execute(
                    """DELETE FROM entities WHERE tenant_id=? AND namespace=?
                       AND entity_id=?""",
                    (scope.tenant_id,scope.namespace,entity_id),
                )
            connection.execute(
                """DELETE FROM mind_event_outbox WHERE tenant_id=? AND namespace=?
                   AND event_id=?""",
                (scope.tenant_id,scope.namespace,event_id),
            )
            connection.execute(
                """INSERT INTO mind_erased_events
                   (tenant_id,namespace,event_id,idempotency_key,erased_at,
                    operation_id,operator_id) VALUES (?,?,?,?,?,?,?)""",
                (scope.tenant_id,scope.namespace,event_id,event["idempotency_key"],
                 now,operation_id,scope.principal_id),
            )
            # The original trigger is lifted only in this one write transaction.
            # DDL rollback also restores it if any subsequent operation fails.
            connection.execute("DROP TRIGGER events_no_delete")
            connection.execute(
                """DELETE FROM events WHERE tenant_id=? AND namespace=? AND event_id=?""",
                (scope.tenant_id,scope.namespace,event_id),
            )
            connection.execute(MIGRATION_1[4])
            self._audit(
                connection,scope,job_id=None,operation_type="erase_event",
                policy_version="erasure.v1",actor_id=scope.principal_id,
                recorded_at=now,status="completed",
                affected_count=1+len(plan.delete_memory_ids)+len(plan.detach_memory_ids),
                target_type="event",target_id=event_id,
            )
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise ErasureBlockedError("foreign_key_dependency")
            if not verify_v5(connection):
                raise ErasureBlockedError("schema_guard_failed")
            return ErasureResult(
                operation_id,event_id,len(plan.delete_memory_ids),
                len(plan.detach_memory_ids),len(plan.delete_summary_revision_ids),
                len(plan.cancel_job_ids),
            )
