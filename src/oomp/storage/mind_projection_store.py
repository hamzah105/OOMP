"""Scoped, source-validated summary and conflict-review projections."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from os import PathLike

from pydantic import TypeAdapter

from oomp.domain.enums import MemoryStatus
from oomp.domain.graph import TemporalQuery
from oomp.domain.graph_policy import ConflictProposal
from oomp.domain.models import AuthorizedScope, Identifier, UtcDateTime
from oomp.storage.graph_store import SQLiteGraphStore
from oomp.storage.sqlite import _authorized, _timestamp, _translate_sqlite_errors
from oomp.storage.memory_store import _event_in_scope
from oomp.storage.migrations import user_version
from oomp.storage.errors import SchemaUpgradeRequiredError

from oomp.mind.contracts import ReviewRecord, ReviewStatus, SummaryRevision, SummarySource


_ID = TypeAdapter(Identifier)
_TIME = TypeAdapter(UtcDateTime)
_SUMMARY_POLICY = "topic-extractive.v1"


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


class SQLiteMindProjectionStore(SQLiteGraphStore):
    """Dedicated summaries never become canonical memories or Stage 5 recall hits."""

    @staticmethod
    def _require_v5(c) -> None:
        if user_version(c) < 5:
            raise SchemaUpgradeRequiredError("mind projections require schema version 5")

    def _summary_input(self, c, scope: AuthorizedScope, topic_id: str, *, max_sources: int):
        topic = c.execute(
            "SELECT 1 FROM topics WHERE tenant_id=? AND namespace=? AND topic_id=?",
            (scope.tenant_id, scope.namespace, topic_id),
        ).fetchone()
        if topic is None:
            raise ValueError("topic is missing from authorized scope")
        rows = c.execute(
            """SELECT memory_id FROM topic_memberships
               WHERE tenant_id=? AND namespace=? AND topic_id=?
               ORDER BY memory_id LIMIT ?""",
            (scope.tenant_id, scope.namespace, topic_id, max_sources + 1),
        ).fetchall()
        if len(rows) > max_sources:
            raise ValueError("topic memberships exceed complete summary bound")
        selected = []
        proof_count = 0
        now = datetime.now(timezone.utc)
        for row in rows:
            memory_id = row["memory_id"]
            state = self._memory_state_in_connection(
                c, scope, memory_id, TemporalQuery(valid_at=now),
            )
            if state.known is not True or not state.evidence:
                continue
            if state.effective_status is not MemoryStatus.ACTIVE or state.valid is False:
                continue
            memory_row = c.execute(
                """SELECT * FROM memories
                   WHERE tenant_id=? AND namespace=? AND memory_id=?""",
                (scope.tenant_id, scope.namespace, memory_id),
            ).fetchone()
            if memory_row is None:
                raise ValueError("topic memory disappeared")
            memory = self._read_memory(c, scope, memory_row)
            content = memory.canonical_content
            if len(content) > 512:
                raise ValueError("topic source exceeds extractive summary text bound")
            metadata = json.loads(memory_row["metadata_json"])
            attribution = str(metadata.get("attribution", "unknown"))
            if len(attribution) > 32:
                raise ValueError("source attribution exceeds summary bound")
            verified = metadata.get("verified") is True
            validity = (
                "bounded" if memory_row["valid_from"] and memory_row["valid_until"]
                else "uncertain"
            )
            proof_count += len(state.evidence)
            if proof_count > 1000:
                raise ValueError("summary evidence exceeds complete bound")
            proof = tuple(
                (item.event_id, item.source_reference.model_dump(mode="json"))
                for item in state.evidence
            )
            selected.append(
                (memory_id, content, proof, attribution, verified, validity)
            )
        return tuple(selected)

    def _read_summary(self, c, scope: AuthorizedScope, row) -> SummaryRevision:
        links = c.execute(
            """SELECT memory_id,event_id FROM mind_summary_sources
               WHERE tenant_id=? AND namespace=? AND revision_id=?
               ORDER BY memory_id,event_id LIMIT 1001""",
            (scope.tenant_id, scope.namespace, row["revision_id"]),
        ).fetchall()
        if len(links) > 1000 or not links:
            raise ValueError("stored summary sources are missing or unbounded")
        memory_ids = tuple(dict.fromkeys(link["memory_id"] for link in links))
        event_ids = tuple(dict.fromkeys(link["event_id"] for link in links))
        sources = []
        for link in links:
            memory_row = c.execute(
                """SELECT metadata_json,valid_from,valid_until FROM memories
                   WHERE tenant_id=? AND namespace=? AND memory_id=?""",
                (scope.tenant_id, scope.namespace, link["memory_id"]),
            ).fetchone()
            if memory_row is None:
                raise ValueError("summary source memory is missing")
            metadata = json.loads(memory_row["metadata_json"])
            source = _event_in_scope(c, scope, link["event_id"])
            sources.append(SummarySource(
                memory_id=link["memory_id"], event_id=link["event_id"],
                source_reference=source.source_reference,
                attribution=str(metadata.get("attribution", "unknown")),
                verified=metadata.get("verified") is True,
                validity=(
                    "bounded" if memory_row["valid_from"] and memory_row["valid_until"]
                    else "uncertain"
                ),
            ))
        return SummaryRevision(
            revision_id=row["revision_id"], tenant_id=scope.tenant_id,
            namespace=scope.namespace, topic_id=row["topic_id"],
            revision_number=row["revision_number"], content=row["content"],
            source_memory_ids=memory_ids, source_event_ids=event_ids,
            sources=tuple(sources),
            source_fingerprint=row["source_fingerprint"],
            policy_version=row["policy_version"],
            recorded_at=_TIME.validate_python(row["recorded_at"]),
            retired_at=_TIME.validate_python(row["retired_at"]) if row["retired_at"] else None,
        )

    @_translate_sqlite_errors
    def consolidate_topic(
        self, scope: AuthorizedScope, topic_id: str, *,
        max_sources: int = 16, max_chars: int = 4096,
    ) -> tuple[SummaryRevision | None, bool]:
        authorized = _authorized(scope)
        topic = _ID.validate_python(topic_id)
        if type(max_sources) is not int or not 1 <= max_sources <= 16:
            raise ValueError("summary source bound must be 1 to 16")
        if type(max_chars) is not int or not 128 <= max_chars <= 4096:
            raise ValueError("summary character bound must be 128 to 4096")
        with self._graph_transaction() as c:
            self._require_schema(c)
            self._require_v5(c)
            selected = self._summary_input(c, authorized, topic, max_sources=max_sources)
            current = c.execute(
                """SELECT * FROM mind_summary_revisions
                   WHERE tenant_id=? AND namespace=? AND topic_id=? AND retired_at IS NULL""",
                (authorized.tenant_id, authorized.namespace, topic),
            ).fetchone()
            if not selected:
                if current is not None:
                    c.execute(
                        """UPDATE mind_summary_revisions SET retired_at=oomp_recorded_at()
                           WHERE tenant_id=? AND namespace=? AND revision_id=?""",
                        (authorized.tenant_id, authorized.namespace, current["revision_id"]),
                    )
                return None, current is not None
            lines = []
            for memory_id, content, proof, attribution, verified, validity in selected:
                reference_ids = ",".join(
                    f"{ref['source_system']}:{ref['external_event_id']}"
                    for _, ref in proof
                )
                lines.append(
                    f"[{memory_id}; {attribution}; verified={str(verified).lower()}; "
                    f"validity={validity}; sources={reference_ids}] {content}"
                )
            summary = "\n".join(lines)
            if len(summary) > max_chars:
                raise ValueError("complete extractive summary exceeds character bound")
            fingerprint = _digest([_SUMMARY_POLICY, selected])
            if current is not None and current["source_fingerprint"] == fingerprint:
                if current["content"] != summary or current["policy_version"] != _SUMMARY_POLICY:
                    raise ValueError("stored summary fingerprint collision")
                return self._read_summary(c, authorized, current), False
            last_number = c.execute(
                """SELECT COALESCE(MAX(revision_number),0) FROM mind_summary_revisions
                   WHERE tenant_id=? AND namespace=? AND topic_id=?""",
                (authorized.tenant_id, authorized.namespace, topic),
            ).fetchone()[0]
            number = int(last_number) + 1
            if current is not None:
                c.execute(
                    """UPDATE mind_summary_revisions SET retired_at=oomp_recorded_at()
                       WHERE tenant_id=? AND namespace=? AND revision_id=?""",
                    (authorized.tenant_id, authorized.namespace, current["revision_id"]),
                )
            revision_id = "summary-" + _digest([
                authorized.tenant_id, authorized.namespace, topic, number, fingerprint,
            ])
            c.execute(
                """INSERT INTO mind_summary_revisions
                   (tenant_id,namespace,revision_id,topic_id,revision_number,
                    content,source_fingerprint,policy_version,recorded_at,retired_at)
                   VALUES (?,?,?,?,?,?,?,?,oomp_recorded_at(),NULL)""",
                (authorized.tenant_id, authorized.namespace, revision_id, topic,
                 number, summary, fingerprint, _SUMMARY_POLICY),
            )
            for memory_id, _, proof, _, _, _ in selected:
                for event_id, _ in proof:
                    c.execute(
                        """INSERT INTO mind_summary_sources
                           (tenant_id,namespace,revision_id,memory_id,event_id)
                           VALUES (?,?,?,?,?)""",
                        (authorized.tenant_id, authorized.namespace, revision_id,
                         memory_id, event_id),
                    )
            row = c.execute(
                """SELECT * FROM mind_summary_revisions
                   WHERE tenant_id=? AND namespace=? AND revision_id=?""",
                (authorized.tenant_id, authorized.namespace, revision_id),
            ).fetchone()
            return self._read_summary(c, authorized, row), True

    @_translate_sqlite_errors
    def get_summary(
        self, scope: AuthorizedScope, topic_id: str, *,
        known_at: datetime | None = None,
    ) -> SummaryRevision | None:
        authorized = _authorized(scope)
        topic = _ID.validate_python(topic_id)
        known = _TIME.validate_python(known_at) if known_at is not None else None
        with self._graph_read() as c:
            self._require_schema(c)
            self._require_v5(c)
            if known is None:
                row = c.execute(
                    """SELECT * FROM mind_summary_revisions
                       WHERE tenant_id=? AND namespace=? AND topic_id=? AND retired_at IS NULL""",
                    (authorized.tenant_id, authorized.namespace, topic),
                ).fetchone()
            else:
                row = c.execute(
                    """SELECT * FROM mind_summary_revisions
                       WHERE tenant_id=? AND namespace=? AND topic_id=?
                         AND recorded_at<=? AND (retired_at IS NULL OR retired_at>?)
                       ORDER BY revision_number DESC LIMIT 1""",
                    (authorized.tenant_id, authorized.namespace, topic,
                     _timestamp(known), _timestamp(known)),
                ).fetchone()
            if row is None:
                return None
            revision = self._read_summary(c, authorized, row)
            if known is None:
                current = self._summary_input(c, authorized, topic, max_sources=16)
                if not current or _digest([_SUMMARY_POLICY, current]) != revision.source_fingerprint:
                    return None
            else:
                # Recorded artifacts remain inspectable at the knowledge cutoff;
                # freshness states whether memberships/proof had changed by then.
                membership_rows = c.execute(
                    """SELECT memory_id FROM topic_memberships
                       WHERE tenant_id=? AND namespace=? AND topic_id=?
                         AND recorded_at<=? ORDER BY memory_id LIMIT 17""",
                    (authorized.tenant_id, authorized.namespace, topic,
                     _timestamp(known)),
                ).fetchall()
                if len(membership_rows) > 16:
                    return revision.model_copy(update={"freshness": "stale"})
                freshness = (
                    "recorded_projection"
                    if {item["memory_id"] for item in membership_rows}
                       == set(revision.source_memory_ids)
                    else "stale"
                )
                for memory_id in revision.source_memory_ids:
                    state = self._memory_state_in_connection(
                        c, authorized, memory_id, TemporalQuery(known_at=known),
                    )
                    if state.known is not True:
                        return None
                    links = c.execute(
                        """SELECT event_id FROM mind_summary_sources
                           WHERE tenant_id=? AND namespace=? AND revision_id=?
                             AND memory_id=?""",
                        (authorized.tenant_id, authorized.namespace,
                         revision.revision_id, memory_id),
                    ).fetchall()
                    linked = {link["event_id"] for link in links}
                    if not linked.issubset(set(state.source_event_ids)):
                        return None
                    if linked != set(state.source_event_ids):
                        freshness = "stale"
                return revision.model_copy(update={"freshness": freshness})
            return revision

    def _read_review(self, row) -> ReviewRecord:
        return ReviewRecord(
            proposal_id=row["proposal_id"], tenant_id=row["tenant_id"],
            namespace=row["namespace"], source_node_id=row["source_memory_id"],
            target_node_id=row["target_memory_id"],
            source_event_ids=tuple(json.loads(row["source_event_ids_json"])),
            relationship_type=row["relationship_type"], reason=row["reason"],
            policy_version=row["policy_version"], status=ReviewStatus(row["status"]),
            recorded_at=_TIME.validate_python(row["recorded_at"]),
            decision_at=_TIME.validate_python(row["decision_at"]) if row["decision_at"] else None,
            decided_by=row["decided_by"],
        )

    @_translate_sqlite_errors
    def save_review(
        self, scope: AuthorizedScope, proposal: ConflictProposal,
    ) -> tuple[ReviewRecord, bool]:
        authorized = _authorized(scope)
        if not isinstance(proposal, ConflictProposal):
            raise TypeError("validated ConflictProposal required")
        incoming = ConflictProposal.model_validate(proposal.model_dump(mode="json"))
        if (incoming.tenant_id, incoming.namespace) != (authorized.tenant_id, authorized.namespace):
            raise ValueError("proposal differs from authorized scope")
        with self._graph_transaction() as c:
            self._require_schema(c)
            self._require_v5(c)
            existing = c.execute(
                """SELECT * FROM mind_review_proposals
                   WHERE tenant_id=? AND namespace=? AND proposal_id=?""",
                (authorized.tenant_id, authorized.namespace, incoming.proposal_id),
            ).fetchone()
            if existing is not None:
                review = self._read_review(existing)
                if (
                    review.source_node_id != incoming.source_node_id
                    or review.target_node_id != incoming.target_node_id
                    or review.source_event_ids != incoming.source_event_ids
                    or review.relationship_type != incoming.relationship_type.value
                    or review.policy_version != incoming.policy_version
                    or review.reason != incoming.reason
                ):
                    raise ValueError("review identity conflicts with stored proposal")
                return review, False
            # Re-derive inside this write transaction so a stale worker cannot
            # insert a proposal backed by changed or retracted source evidence.
            from oomp.domain.graph_policy import propose_conflict
            from oomp.storage.memory_store import _event_in_scope
            source_row = c.execute(
                """SELECT * FROM memories WHERE tenant_id=? AND namespace=? AND memory_id=?""",
                (authorized.tenant_id, authorized.namespace, incoming.source_node_id),
            ).fetchone()
            target_row = c.execute(
                """SELECT * FROM memories WHERE tenant_id=? AND namespace=? AND memory_id=?""",
                (authorized.tenant_id, authorized.namespace, incoming.target_node_id),
            ).fetchone()
            if source_row is None or target_row is None:
                raise ValueError("review endpoint disappeared")
            source = self._read_memory(c, authorized, source_row)
            target = self._read_memory(c, authorized, target_row)
            first = _event_in_scope(c, authorized, incoming.source_event_ids[0])
            target_ids = incoming.source_event_ids[1:] or target.source_event_ids
            supported = any(
                propose_conflict(
                    authorized, source, target, first,
                    _event_in_scope(c, authorized, target_id),
                ).proposal == incoming
                for target_id in target_ids
            )
            if not supported:
                raise ValueError("proposal is not supported by current evidence")
            # The source event must remain currently endorsed by its endpoint.
            source_state = self._memory_state_in_connection(
                c, authorized, source.memory_id, TemporalQuery(),
            )
            target_state = self._memory_state_in_connection(
                c, authorized, target.memory_id, TemporalQuery(),
            )
            if incoming.source_event_ids[0] not in source_state.source_event_ids:
                raise ValueError("review source evidence was retracted")
            if incoming.relationship_type.value == "CONTRADICTS":
                if incoming.source_event_ids[1] not in target_state.source_event_ids:
                    raise ValueError("review target evidence was retracted")
            elif not target_state.source_event_ids:
                raise ValueError("review target evidence was retracted")
            c.execute(
                """INSERT INTO mind_review_proposals
                   (tenant_id,namespace,proposal_id,source_memory_id,target_memory_id,
                    relationship_type,source_event_ids_json,reason,policy_version,
                    status,recorded_at,decision_at,decided_by)
                   VALUES (?,?,?,?,?,?,?,?,?,'pending',oomp_recorded_at(),NULL,NULL)""",
                (authorized.tenant_id, authorized.namespace, incoming.proposal_id,
                 incoming.source_node_id, incoming.target_node_id,
                 incoming.relationship_type.value,
                 json.dumps(incoming.source_event_ids, separators=(",", ":")),
                 incoming.reason, incoming.policy_version),
            )
            row = c.execute(
                """SELECT * FROM mind_review_proposals
                   WHERE tenant_id=? AND namespace=? AND proposal_id=?""",
                (authorized.tenant_id, authorized.namespace, incoming.proposal_id),
            ).fetchone()
            return self._read_review(row), True

    @_translate_sqlite_errors
    def list_reviews(
        self, scope: AuthorizedScope, *,
        status: ReviewStatus | None = ReviewStatus.PENDING, limit: int = 100,
    ) -> tuple[ReviewRecord, ...]:
        authorized = _authorized(scope)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("review limit must be 1 to 100")
        selected = ReviewStatus(status) if status is not None else None
        with self._graph_read() as c:
            self._require_schema(c)
            self._require_v5(c)
            sql = """SELECT * FROM mind_review_proposals
                     WHERE tenant_id=? AND namespace=?"""
            values: list[object] = [authorized.tenant_id, authorized.namespace]
            if selected is not None:
                sql += " AND status=?"
                values.append(selected.value)
            sql += " ORDER BY recorded_at,proposal_id LIMIT ?"
            values.append(limit + 1)
            rows = c.execute(sql, values).fetchall()
            return tuple(self._read_review(row) for row in rows[:limit])

    @_translate_sqlite_errors
    def decide_review(
        self, scope: AuthorizedScope, proposal_id: str, decision: ReviewStatus,
    ) -> ReviewRecord:
        authorized = _authorized(scope)
        identifier = _ID.validate_python(proposal_id)
        selected = ReviewStatus(decision)
        if selected is not ReviewStatus.REJECTED:
            raise ValueError("only rejection is supported by this decision path")
        with self._graph_transaction() as c:
            self._require_schema(c)
            self._require_v5(c)
            row = c.execute(
                """SELECT * FROM mind_review_proposals
                   WHERE tenant_id=? AND namespace=? AND proposal_id=?""",
                (authorized.tenant_id, authorized.namespace, identifier),
            ).fetchone()
            if row is None:
                raise ValueError("review proposal is missing")
            existing = self._read_review(row)
            if existing.status is not ReviewStatus.PENDING:
                if existing.status is selected:
                    return existing
                raise ValueError("review decision cannot be changed")
            c.execute(
                """UPDATE mind_review_proposals
                   SET status=?,decision_at=oomp_recorded_at(),decided_by=?
                   WHERE tenant_id=? AND namespace=? AND proposal_id=? AND status='pending'""",
                (selected.value, authorized.principal_id, authorized.tenant_id,
                 authorized.namespace, identifier),
            )
            return self._read_review(c.execute(
                """SELECT * FROM mind_review_proposals
                   WHERE tenant_id=? AND namespace=? AND proposal_id=?""",
                (authorized.tenant_id, authorized.namespace, identifier),
            ).fetchone())

    @_translate_sqlite_errors
    def retract_source(
        self, scope: AuthorizedScope, memory_id: str, event_id: str, *,
        reason_code: str = "operator_retraction",
    ) -> bool:
        authorized = _authorized(scope)
        memory = _ID.validate_python(memory_id)
        event = _ID.validate_python(event_id)
        reason = _ID.validate_python(reason_code)
        if reason not in {"operator_retraction", "source_correction", "evidence_withdrawn"}:
            raise ValueError("unsupported retraction reason code")
        with self._graph_transaction() as c:
            self._require_schema(c)
            self._require_v5(c)
            linked = c.execute(
                """SELECT 1 FROM memory_sources WHERE tenant_id=? AND namespace=?
                     AND memory_id=? AND event_id=?""",
                (authorized.tenant_id, authorized.namespace, memory, event),
            ).fetchone()
            if linked is None:
                raise ValueError("retraction target is not linked in authorized scope")
            prior = c.execute(
                """SELECT 1 FROM mind_retractions WHERE tenant_id=? AND namespace=?
                     AND memory_id=? AND event_id=? LIMIT 1""",
                (authorized.tenant_id, authorized.namespace, memory, event),
            ).fetchone()
            if prior is not None:
                return False
            c.execute(
                """INSERT INTO mind_retractions
                   (tenant_id,namespace,memory_id,event_id,recorded_at,reason_code,operator_id)
                   VALUES (?,?,?,?,oomp_recorded_at(),?,?)""",
                (authorized.tenant_id, authorized.namespace, memory, event,
                 reason, authorized.principal_id),
            )
            # Current summary revision containing this proof is now retired.
            c.execute(
                """UPDATE mind_summary_revisions SET retired_at=oomp_recorded_at()
                   WHERE tenant_id=? AND namespace=? AND retired_at IS NULL
                     AND revision_id IN (
                       SELECT revision_id FROM mind_summary_sources
                       WHERE tenant_id=? AND namespace=? AND memory_id=? AND event_id=?
                     )""",
                (authorized.tenant_id, authorized.namespace,
                 authorized.tenant_id, authorized.namespace, memory, event),
            )
            return True

    @_translate_sqlite_errors
    def get_review(
        self, scope: AuthorizedScope, proposal_id: str,
    ) -> ReviewRecord | None:
        authorized = _authorized(scope)
        identifier = _ID.validate_python(proposal_id)
        with self._graph_read() as c:
            self._require_schema(c)
            self._require_v5(c)
            row = c.execute(
                """SELECT * FROM mind_review_proposals
                   WHERE tenant_id=? AND namespace=? AND proposal_id=?""",
                (authorized.tenant_id, authorized.namespace, identifier),
            ).fetchone()
            return self._read_review(row) if row is not None else None

    @_translate_sqlite_errors
    def approve_review(
        self, scope: AuthorizedScope, proposal_id: str,
    ) -> ReviewRecord:
        """Commit the existing governed edge and review decision atomically."""
        authorized = _authorized(scope)
        identifier = _ID.validate_python(proposal_id)
        from oomp.domain.graph_policy import propose_conflict
        with self._graph_transaction() as c:
            self._require_schema(c)
            self._require_v5(c)
            row = c.execute(
                """SELECT * FROM mind_review_proposals
                   WHERE tenant_id=? AND namespace=? AND proposal_id=?""",
                (authorized.tenant_id, authorized.namespace, identifier),
            ).fetchone()
            if row is None:
                raise ValueError("review proposal is missing")
            existing = self._read_review(row)
            if existing.status is ReviewStatus.APPROVED:
                return existing
            if existing.status is ReviewStatus.REJECTED:
                raise ValueError("rejected review cannot be approved")
            source_row = c.execute(
                """SELECT * FROM memories
                   WHERE tenant_id=? AND namespace=? AND memory_id=?""",
                (authorized.tenant_id, authorized.namespace, existing.source_node_id),
            ).fetchone()
            target_row = c.execute(
                """SELECT * FROM memories
                   WHERE tenant_id=? AND namespace=? AND memory_id=?""",
                (authorized.tenant_id, authorized.namespace, existing.target_node_id),
            ).fetchone()
            if source_row is None or target_row is None:
                raise ValueError("review endpoint is missing")
            source = self._read_memory(c, authorized, source_row)
            target = self._read_memory(c, authorized, target_row)
            source_event = _event_in_scope(
                c, authorized, existing.source_event_ids[0],
            )
            target_ids = (
                existing.source_event_ids[1:]
                if existing.relationship_type == "CONTRADICTS"
                else target.source_event_ids
            )
            proposal = None
            for target_event_id in target_ids:
                target_event = _event_in_scope(c, authorized, target_event_id)
                assessment = propose_conflict(
                    authorized, source, target, source_event, target_event,
                )
                if (
                    assessment.proposal is not None
                    and assessment.proposal.proposal_id == identifier
                    and assessment.proposal.reason == existing.reason
                    and assessment.proposal.policy_version == existing.policy_version
                ):
                    proposal = assessment.proposal
                    break
            if proposal is None:
                raise ValueError("review is no longer supported by evidence")
            self._apply_resolution_in_transaction(c, authorized, proposal)
            c.execute(
                """UPDATE mind_review_proposals
                   SET status='approved',decision_at=oomp_recorded_at(),decided_by=?
                   WHERE tenant_id=? AND namespace=? AND proposal_id=? AND status='pending'""",
                (authorized.principal_id, authorized.tenant_id,
                 authorized.namespace, identifier),
            )
            decided = c.execute(
                """SELECT * FROM mind_review_proposals
                   WHERE tenant_id=? AND namespace=? AND proposal_id=?""",
                (authorized.tenant_id, authorized.namespace, identifier),
            ).fetchone()
            return self._read_review(decided)
