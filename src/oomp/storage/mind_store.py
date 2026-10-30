"""SQLite-backed, scoped Stage 6 intake and job queue.

All state changes use short BEGIN IMMEDIATE transactions. Handler side effects
run outside these transactions and must be idempotent.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from collections.abc import Callable, Sequence
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from pydantic import TypeAdapter

from oomp.domain.models import AuthorizedScope, Identifier
from oomp.mind.contracts import JobStatus, JobType, MindJob
from oomp.retrieval.contracts import EmbeddingSpace
from .errors import StorageError, SchemaUpgradeRequiredError, ScopeMismatchError
from .migrations import user_version
from .sqlite import SQLiteEventStore, _authorized, _canonical_json, _timestamp, _translate_sqlite_errors


_IDENT = TypeAdapter(Identifier)
_MAX_PENDING_HARD = 10_000
_MAX_BATCH = 100
_ERROR_CODES = frozenset({
    "storage_busy", "provider_unavailable", "provider_invalid", "extraction_error",
    "validation_error", "missing_target", "unsupported_policy", "unsupported_provider",
    "schema_error", "scope_error", "worker_interrupted", "lease_expired", "cancelled",
    "unknown_error", "queue_full",
})
_RETRYABLE_CODES = frozenset({
    "storage_busy", "provider_unavailable", "worker_interrupted", "lease_expired",
    "unknown_error", "queue_full",
})


class QueueCapacityError(StorageError):
    """The scoped active-job bound has been reached; outbox intake remains pending."""


class JobConflictError(StorageError):
    """A job identity collides with different durable work."""


class LostLeaseError(StorageError):
    """A worker's lease or fencing token no longer grants ownership."""


class InvalidJobTransitionError(StorageError):
    """The requested job state transition is not permitted."""


def _utc_now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return an aware UTC datetime")
    return value.astimezone(timezone.utc)


def _bounded(value: int, maximum: int, label: str) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{label} must be an integer from 1 to {maximum}")
    return value


def _job_from_row(row: sqlite3.Row) -> MindJob:
    try:
        return MindJob.model_validate({
            "job_id": row["job_id"], "tenant_id": row["tenant_id"],
            "namespace": row["namespace"], "job_type": row["job_type"],
            "target_type": row["target_type"], "target_id": row["target_id"],
            "idempotency_key": row["idempotency_key"], "status": row["status"],
            "priority": row["priority"], "attempt_count": row["attempt_count"],
            "max_attempts": row["max_attempts"], "created_at": row["created_at"],
            "updated_at": row["updated_at"], "available_at": row["available_at"],
            "lease_owner": row["lease_owner"], "lease_expires_at": row["lease_expires_at"],
            "fencing_token": row["fencing_token"], "policy_version": row["policy_version"],
            "config": json.loads(row["config_json"]),
            "last_error_code": row["last_error_code"],
        })
    except (ValueError, TypeError, KeyError) as error:
        raise StorageError("stored mind job failed validation") from None


class SQLiteMindStore(SQLiteEventStore):
    """Durable queue. Every public operation requires a trusted AuthorizedScope."""

    def __init__(
        self, path=None, *, clock: Callable[[], datetime] | None = None,
        busy_timeout_ms: int = 5000, max_pending: int = 1000,
    ) -> None:
        super().__init__(path, busy_timeout_ms=busy_timeout_ms)
        if type(max_pending) is not int or not 4 <= max_pending <= _MAX_PENDING_HARD:
            raise ValueError("max_pending must be an integer from 4 to 10000")
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.max_pending = max_pending

    @staticmethod
    def _require_v5(connection: sqlite3.Connection) -> None:
        SQLiteEventStore._require_schema(connection)
        if user_version(connection) < 5:
            raise SchemaUpgradeRequiredError("mind storage requires explicit schema version 5 initialization")

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with closing(self._connect("rw")) as connection:
            self._require_v5(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.execute("COMMIT")
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        with closing(self._connect("ro")) as connection:
            connection.execute("BEGIN")
            try:
                self._require_v5(connection)
                yield connection
            finally:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")

    @staticmethod
    def _row(connection: sqlite3.Connection, scope: AuthorizedScope, job_id: str):
        return connection.execute(
            "SELECT * FROM mind_jobs WHERE tenant_id=? AND namespace=? AND job_id=?",
            (scope.tenant_id, scope.namespace, job_id),
        ).fetchone()

    def _active_count(self, connection: sqlite3.Connection, scope: AuthorizedScope) -> int:
        return int(connection.execute(
            """SELECT COUNT(*) FROM mind_jobs WHERE tenant_id=? AND namespace=?
               AND status IN ('queued','retry_wait','running')""",
            (scope.tenant_id, scope.namespace),
        ).fetchone()[0])

    @staticmethod
    def _validate_spec(
        connection: sqlite3.Connection, scope: AuthorizedScope,
        job_type: JobType, target_type: str, target_id: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        expected_type = "topic" if job_type is JobType.CONSOLIDATE_TOPIC else "event"
        if target_type != expected_type:
            raise ValueError("job target type is incompatible with job type")
        table = "topics" if target_type == "topic" else "events"
        id_column = "topic_id" if target_type == "topic" else "event_id"
        row = connection.execute(
            f"SELECT 1 FROM {table} WHERE tenant_id=? AND namespace=? AND {id_column}=?",
            (scope.tenant_id,scope.namespace,target_id),
        ).fetchone()
        if row is None:
            raise ScopeMismatchError("job target is absent from authorized scope")
        if job_type is JobType.EXTRACT_EVENT and set(config) == {"understanding"}:
            identity = config["understanding"]
            if not isinstance(identity, str) or not re.fullmatch(r"[a-f0-9]{64}", identity):
                raise ValueError("invalid understanding configuration identity")
            return {"understanding": identity}
        if job_type is not JobType.MAINTAIN_INDEX:
            if config:
                raise ValueError("job configuration is unsupported for this type")
            return {}
        if not config:
            return {}
        if set(config) == {"include_embeddings"} and config["include_embeddings"] is False:
            return {"include_embeddings": False}
        if set(config) != {"include_embeddings", "space"} or config["include_embeddings"] is not True:
            raise ValueError("index job configuration is unsupported")
        if not isinstance(config["space"], dict):
            raise ValueError("index embedding space must be an object")
        space = EmbeddingSpace.model_validate(config["space"])
        if set(config["space"]) != {"provider","model","version","dimension"}:
            raise ValueError("index embedding space has unsupported fields")
        return {"include_embeddings": True, "space": space.model_dump(mode="json")}


    def _enqueue_in_tx(
        self, connection: sqlite3.Connection, scope: AuthorizedScope,
        job_type: JobType, target_type: str, target_id: str, *,
        idempotency_key: str, policy_version: str, config: dict[str, Any],
        priority: int, max_attempts: int, available_at: datetime | None,
    ) -> MindJob:
        config = self._validate_spec(connection, scope, job_type, target_type, target_id, config)
        existing = connection.execute(
            "SELECT * FROM mind_jobs WHERE tenant_id=? AND namespace=? AND idempotency_key=?",
            (scope.tenant_id, scope.namespace, idempotency_key),
        ).fetchone()
        if existing is not None:
            job = _job_from_row(existing)
            if (job.job_type, job.target_type, job.target_id, job.policy_version,
                job.config, job.priority, job.max_attempts) != (
                job_type, target_type, target_id, policy_version, config, priority, max_attempts
            ):
                raise JobConflictError("job idempotency key identifies different durable work")
            return job
        if self._active_count(connection, scope) >= self.max_pending:
            raise QueueCapacityError("scoped pending job limit reached")
        now = _utc_now(self.clock)
        when = available_at or now
        proposed = MindJob(
            job_id="job-" + uuid.uuid4().hex,
            tenant_id=scope.tenant_id, namespace=scope.namespace,
            job_type=job_type, target_type=target_type, target_id=target_id,
            idempotency_key=idempotency_key, status=JobStatus.QUEUED,
            priority=priority, attempt_count=0, max_attempts=max_attempts,
            created_at=now, updated_at=now, available_at=when,
            fencing_token=0, policy_version=policy_version, config=config,
        )
        connection.execute(
            """INSERT INTO mind_jobs (
                tenant_id,namespace,job_id,job_type,target_type,target_id,idempotency_key,
                status,priority,attempt_count,max_attempts,created_at,updated_at,
                available_at,lease_owner,lease_expires_at,fencing_token,policy_version,
                config_json,last_error_code
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                scope.tenant_id, scope.namespace, proposed.job_id, job_type.value,
                target_type, target_id, idempotency_key, JobStatus.QUEUED.value,
                priority, 0, max_attempts, _timestamp(now), _timestamp(now),
                _timestamp(when), None, None, 0, policy_version,
                _canonical_json(config), None,
            ),
        )
        return proposed

    @_translate_sqlite_errors
    def enqueue(
        self, scope: AuthorizedScope, job_type: JobType | str,
        target_type: str, target_id: str, *, idempotency_key: str,
        policy_version: str, config: dict[str, Any] | None = None,
        priority: int = 0, max_attempts: int = 3,
        available_at: datetime | None = None,
    ) -> MindJob:
        scope = _authorized(scope)
        kind = JobType(job_type)
        for item in (target_type, target_id, idempotency_key, policy_version):
            _IDENT.validate_python(item)
        if type(priority) is not int or not -100 <= priority <= 100:
            raise ValueError("priority must be an integer from -100 to 100")
        _bounded(max_attempts, 20, "max_attempts")
        if available_at is not None:
            if available_at.tzinfo is None or available_at.utcoffset() is None:
                raise ValueError("available_at must have a UTC offset")
            available_at = available_at.astimezone(timezone.utc)
        config = dict(config or {})
        with self._tx() as connection:
            return self._enqueue_in_tx(
                connection, scope, kind, target_type, target_id,
                idempotency_key=idempotency_key, policy_version=policy_version,
                config=config, priority=priority, max_attempts=max_attempts,
                available_at=available_at,
            )

    @_translate_sqlite_errors
    def backfill_events(self, scope: AuthorizedScope, *, limit: int = 100) -> int:
        scope = _authorized(scope)
        _bounded(limit, _MAX_BATCH, "backfill limit")
        now = _timestamp(_utc_now(self.clock))
        with self._tx() as connection:
            rows = connection.execute(
                """SELECT e.event_id FROM events e
                   WHERE e.tenant_id=? AND e.namespace=?
                     AND NOT EXISTS (
                         SELECT 1 FROM mind_event_outbox o
                         WHERE o.tenant_id=e.tenant_id AND o.namespace=e.namespace
                           AND o.event_id=e.event_id
                     )
                   ORDER BY e.event_id LIMIT ?""",
                (scope.tenant_id, scope.namespace, limit),
            ).fetchall()
            connection.executemany(
                """INSERT INTO mind_event_outbox
                   (tenant_id,namespace,event_id,inserted_at) VALUES (?,?,?,?)""",
                ((scope.tenant_id, scope.namespace, row[0], now) for row in rows),
            )
            return len(rows)

    @_translate_sqlite_errors
    def dispatch_outbox(
        self, scope: AuthorizedScope, *, limit: int = 100,
        policy_version: str = "extract.v1", max_attempts: int = 3,
    ) -> int:
        scope = _authorized(scope)
        _bounded(limit, _MAX_BATCH, "dispatch limit")
        _bounded(max_attempts, 20, "max_attempts")
        _IDENT.validate_python(policy_version)
        dispatched = 0
        with self._tx() as connection:
            rows = connection.execute(
                """SELECT event_id FROM mind_event_outbox
                   WHERE tenant_id=? AND namespace=? AND dispatched_at IS NULL
                   ORDER BY inserted_at,event_id LIMIT ?""",
                (scope.tenant_id, scope.namespace, limit),
            ).fetchall()
            for row in rows:
                # Keep two slots for the extraction handler's bounded downstream
                # index and conflict-review jobs. Intake remains in the outbox.
                if self._active_count(connection, scope) >= self.max_pending - 2:
                    break
                event_id = row[0]
                digest = hashlib.sha256(
                    (scope.tenant_id + "\0" + scope.namespace + "\0" + event_id +
                     "\0" + policy_version).encode("utf-8")
                ).hexdigest()
                try:
                    self._enqueue_in_tx(
                        connection, scope, JobType.EXTRACT_EVENT, "event", event_id,
                        idempotency_key="extract-" + digest,
                        policy_version=policy_version, config={},
                        priority=0, max_attempts=max_attempts, available_at=None,
                    )
                except QueueCapacityError:
                    break
                connection.execute(
                    """UPDATE mind_event_outbox SET dispatched_at=?
                       WHERE tenant_id=? AND namespace=? AND event_id=?
                         AND dispatched_at IS NULL""",
                    (_timestamp(_utc_now(self.clock)), scope.tenant_id, scope.namespace, event_id),
                )
                dispatched += 1
        return dispatched
    @staticmethod
    def _audit(
        connection: sqlite3.Connection, scope: AuthorizedScope, *,
        job_id: str | None, operation_type: str, policy_version: str,
        actor_id: str, recorded_at: str, status: str,
        error_code: str | None = None, affected_count: int = 0,
        target_type: str | None = None, target_id: str | None = None,
    ) -> None:
        connection.execute(
            """INSERT INTO mind_maintenance_audit
               (tenant_id,namespace,job_id,operation_type,policy_version,actor_id,
                recorded_at,status,error_code,affected_count,target_type,target_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (scope.tenant_id,scope.namespace,job_id,operation_type,policy_version,
             actor_id,recorded_at,status,error_code,affected_count,target_type,target_id),
        )

    def _close_expired_attempt(
        self, connection: sqlite3.Connection, scope: AuthorizedScope,
        job: MindJob, now: str, *, terminal: bool,
    ) -> None:
        connection.execute(
            """UPDATE mind_job_attempts SET ended_at=?,status='expired',
               error_code='lease_expired'
               WHERE tenant_id=? AND namespace=? AND job_id=?
                 AND attempt_number=? AND status='running'""",
            (now,scope.tenant_id,scope.namespace,job.job_id,job.attempt_count),
        )
        if terminal:
            connection.execute(
                """UPDATE mind_jobs SET status='failed',lease_owner=NULL,
                   lease_expires_at=NULL,updated_at=?,last_error_code='lease_expired'
                   WHERE tenant_id=? AND namespace=? AND job_id=? AND status='running'""",
                (now,scope.tenant_id,scope.namespace,job.job_id),
            )
            self._audit(
                connection,scope,job_id=job.job_id,operation_type="job_exhausted",
                policy_version=job.policy_version,actor_id=job.lease_owner or "worker",
                recorded_at=now,status="failed",error_code="lease_expired",
                target_type=job.target_type,target_id=job.target_id,
            )

    @_translate_sqlite_errors
    def claim(
        self, scope: AuthorizedScope, worker_id: str, *, lease_seconds: int = 60,
        accepted_policy_versions: Sequence[str] | None = None,
    ) -> MindJob | None:
        scope = _authorized(scope)
        worker_id = _IDENT.validate_python(worker_id)
        _bounded(lease_seconds, 3600, "lease_seconds")
        accepted = None
        if accepted_policy_versions is not None:
            accepted = frozenset(_IDENT.validate_python(x) for x in accepted_policy_versions)
            if len(accepted) > 100:
                raise ValueError("accepted policy version count exceeds 100")
        with self._tx() as connection:
            now_dt = _utc_now(self.clock)
            now = _timestamp(now_dt)
            lease_end = _timestamp(now_dt + timedelta(seconds=lease_seconds))
            expired = connection.execute(
                """SELECT * FROM mind_jobs
                   WHERE tenant_id=? AND namespace=? AND status='running'
                     AND lease_expires_at<=? AND attempt_count>=max_attempts
                   ORDER BY lease_expires_at,job_id LIMIT 100""",
                (scope.tenant_id,scope.namespace,now),
            ).fetchall()
            for row in expired:
                self._close_expired_attempt(connection,scope,_job_from_row(row),now,terminal=True)
            candidates = connection.execute(
                """SELECT * FROM mind_jobs
                   WHERE tenant_id=? AND namespace=? AND attempt_count<max_attempts
                     AND ((status IN ('queued','retry_wait') AND available_at<=?)
                          OR (status='running' AND lease_expires_at<=?))
                   ORDER BY priority DESC,available_at,job_id LIMIT 100""",
                (scope.tenant_id,scope.namespace,now,now),
            ).fetchall()
            for row in candidates:
                job = _job_from_row(row)
                if job.status is JobStatus.RUNNING:
                    self._close_expired_attempt(connection,scope,job,now,terminal=False)
                if accepted is not None and job.policy_version not in accepted:
                    connection.execute(
                        """UPDATE mind_jobs SET status='failed',lease_owner=NULL,
                           lease_expires_at=NULL,updated_at=?,last_error_code='unsupported_policy'
                           WHERE tenant_id=? AND namespace=? AND job_id=?""",
                        (now,scope.tenant_id,scope.namespace,job.job_id),
                    )
                    self._audit(
                        connection,scope,job_id=job.job_id,operation_type="job_policy_rejected",
                        policy_version=job.policy_version,actor_id=worker_id,
                        recorded_at=now,status="failed",error_code="unsupported_policy",
                        target_type=job.target_type,target_id=job.target_id,
                    )
                    continue
                changed = connection.execute(
                    """UPDATE mind_jobs SET status='running',attempt_count=attempt_count+1,
                       lease_owner=?,lease_expires_at=?,fencing_token=fencing_token+1,
                       updated_at=?,last_error_code=NULL
                       WHERE tenant_id=? AND namespace=? AND job_id=?
                         AND attempt_count=? AND fencing_token=?""",
                    (worker_id,lease_end,now,scope.tenant_id,scope.namespace,job.job_id,
                     job.attempt_count,job.fencing_token),
                ).rowcount
                if changed != 1:
                    raise StorageError("atomic job claim failed")
                fresh = _job_from_row(self._row(connection,scope,job.job_id))
                connection.execute(
                    """INSERT INTO mind_job_attempts
                       (tenant_id,namespace,job_id,attempt_number,fencing_token,
                        worker_id,started_at,status)
                       VALUES (?,?,?,?,?,?,?,'running')""",
                    (scope.tenant_id,scope.namespace,job.job_id,fresh.attempt_count,
                     fresh.fencing_token,worker_id,now),
                )
                self._audit(
                    connection,scope,job_id=job.job_id,operation_type="job_claim",
                    policy_version=job.policy_version,actor_id=worker_id,
                    recorded_at=now,status="running",
                    target_type=job.target_type,target_id=job.target_id,
                )
                return fresh
        return None

    def _owned(
        self, connection: sqlite3.Connection, scope: AuthorizedScope,
        job_id: str, worker_id: str, fencing_token: int, now: str,
    ) -> MindJob:
        row = self._row(connection,scope,job_id)
        if row is None:
            raise LostLeaseError("job is absent from authorized scope")
        job = _job_from_row(row)
        if (job.status is not JobStatus.RUNNING or job.lease_owner != worker_id
            or job.fencing_token != fencing_token or
            job.lease_expires_at is None or _timestamp(job.lease_expires_at) <= now):
            raise LostLeaseError("job lease or fencing token is no longer valid")
        return job

    @_translate_sqlite_errors
    def renew(
        self, scope: AuthorizedScope, job_id: str, worker_id: str,
        fencing_token: int, *, lease_seconds: int = 60,
    ) -> bool:
        scope = _authorized(scope)
        job_id = _IDENT.validate_python(job_id)
        worker_id = _IDENT.validate_python(worker_id)
        _bounded(lease_seconds,3600,"lease_seconds")
        if type(fencing_token) is not int or fencing_token < 1:
            raise ValueError("fencing token must be positive")
        with self._tx() as connection:
            now_dt = _utc_now(self.clock)
            now = _timestamp(now_dt)
            self._owned(connection,scope,job_id,worker_id,fencing_token,now)
            changed = connection.execute(
                """UPDATE mind_jobs SET lease_expires_at=?,updated_at=?
                   WHERE tenant_id=? AND namespace=? AND job_id=? AND status='running'
                     AND lease_owner=? AND fencing_token=? AND lease_expires_at>?""",
                (_timestamp(now_dt+timedelta(seconds=lease_seconds)),now,
                 scope.tenant_id,scope.namespace,job_id,worker_id,fencing_token,now),
            ).rowcount
            if changed != 1:
                raise LostLeaseError("job lease was replaced")
            return True

    @_translate_sqlite_errors
    def complete(
        self, scope: AuthorizedScope, job_id: str, worker_id: str,
        fencing_token: int, *, result_counts: dict[str, int] | None = None,
    ) -> bool:
        scope = _authorized(scope)
        job_id = _IDENT.validate_python(job_id)
        worker_id = _IDENT.validate_python(worker_id)
        if type(fencing_token) is not int or fencing_token < 1:
            raise ValueError("fencing token must be positive")
        result_counts = result_counts or {}
        if len(result_counts) > 20 or any(
            type(v) is not int or v < 0 or v > 100_000 for v in result_counts.values()
        ):
            raise ValueError("result counts must be bounded nonnegative integers")
        affected = sum(result_counts.values())
        with self._tx() as connection:
            now = _timestamp(_utc_now(self.clock))
            job = self._owned(connection,scope,job_id,worker_id,fencing_token,now)
            changed = connection.execute(
                """UPDATE mind_jobs SET status='completed',lease_owner=NULL,
                   lease_expires_at=NULL,updated_at=? WHERE tenant_id=? AND namespace=?
                   AND job_id=? AND status='running' AND lease_owner=?
                   AND fencing_token=? AND lease_expires_at>?""",
                (now,scope.tenant_id,scope.namespace,job_id,worker_id,fencing_token,now),
            ).rowcount
            if changed != 1:
                raise LostLeaseError("job lease was replaced")
            connection.execute(
                """UPDATE mind_job_attempts SET ended_at=?,status='completed'
                   WHERE tenant_id=? AND namespace=? AND job_id=?
                     AND attempt_number=? AND fencing_token=? AND status='running'""",
                (now,scope.tenant_id,scope.namespace,job_id,job.attempt_count,fencing_token),
            )
            self._audit(
                connection,scope,job_id=job_id,operation_type="job_complete",
                policy_version=job.policy_version,actor_id=worker_id,
                recorded_at=now,status="completed",affected_count=affected,
                target_type=job.target_type,target_id=job.target_id,
            )
            for key in ("extraction_degraded", "model_calls", "model_rejected"):
                if result_counts.get(key):
                    self._audit(
                        connection, scope, job_id=job_id, operation_type="mind2." + key,
                        policy_version="mind2.v1", actor_id=worker_id, recorded_at=now,
                        status="degraded" if key == "extraction_degraded" else "completed",
                        error_code="extraction_error" if key == "extraction_degraded" else None,
                        affected_count=result_counts[key], target_type=job.target_type, target_id=job.target_id,
                    )
            return True

    @_translate_sqlite_errors
    def fail(
        self, scope: AuthorizedScope, job_id: str, worker_id: str,
        fencing_token: int, *, error_code: str, retryable: bool = True,
    ) -> MindJob:
        scope = _authorized(scope)
        job_id = _IDENT.validate_python(job_id)
        worker_id = _IDENT.validate_python(worker_id)
        if type(fencing_token) is not int or fencing_token < 1:
            raise ValueError("fencing token must be positive")
        if error_code not in _ERROR_CODES:
            raise ValueError("error_code is not an approved sanitized code")
        if type(retryable) is not bool:
            raise TypeError("retryable must be boolean")
        with self._tx() as connection:
            now_dt = _utc_now(self.clock)
            now = _timestamp(now_dt)
            job = self._owned(connection,scope,job_id,worker_id,fencing_token,now)
            will_retry = retryable and error_code in _RETRYABLE_CODES and job.attempt_count < job.max_attempts
            status = JobStatus.RETRY_WAIT if will_retry else JobStatus.FAILED
            delay = min(3600,2 ** min(job.attempt_count-1,12)) if will_retry else 0
            available = _timestamp(now_dt+timedelta(seconds=delay))
            changed = connection.execute(
                """UPDATE mind_jobs SET status=?,lease_owner=NULL,lease_expires_at=NULL,
                   updated_at=?,available_at=?,last_error_code=?
                   WHERE tenant_id=? AND namespace=? AND job_id=? AND status='running'
                     AND lease_owner=? AND fencing_token=? AND lease_expires_at>?""",
                (status.value,now,available,error_code,scope.tenant_id,scope.namespace,
                 job_id,worker_id,fencing_token,now),
            ).rowcount
            if changed != 1:
                raise LostLeaseError("job lease was replaced")
            connection.execute(
                """UPDATE mind_job_attempts SET ended_at=?,status=?,error_code=?
                   WHERE tenant_id=? AND namespace=? AND job_id=?
                     AND attempt_number=? AND fencing_token=? AND status='running'""",
                (now,status.value,error_code,scope.tenant_id,scope.namespace,job_id,
                 job.attempt_count,fencing_token),
            )
            self._audit(
                connection,scope,job_id=job_id,operation_type="job_fail",
                policy_version=job.policy_version,actor_id=worker_id,recorded_at=now,
                status=status.value,error_code=error_code,
                target_type=job.target_type,target_id=job.target_id,
            )
            return _job_from_row(self._row(connection,scope,job_id))
    @_translate_sqlite_errors
    def cancel(self, scope: AuthorizedScope, job_id: str) -> MindJob:
        scope = _authorized(scope)
        job_id = _IDENT.validate_python(job_id)
        with self._tx() as connection:
            now = _timestamp(_utc_now(self.clock))
            row = self._row(connection,scope,job_id)
            if row is None:
                raise InvalidJobTransitionError("job is absent from authorized scope")
            job = _job_from_row(row)
            if job.status not in (JobStatus.QUEUED,JobStatus.RETRY_WAIT,JobStatus.RUNNING):
                raise InvalidJobTransitionError("job cannot be cancelled from current state")
            if job.status is JobStatus.RUNNING:
                connection.execute(
                    """UPDATE mind_job_attempts SET ended_at=?,status='cancelled',
                       error_code='cancelled'
                       WHERE tenant_id=? AND namespace=? AND job_id=?
                         AND attempt_number=? AND status='running'""",
                    (now,scope.tenant_id,scope.namespace,job_id,job.attempt_count),
                )
            connection.execute(
                """UPDATE mind_jobs SET status='cancelled',lease_owner=NULL,
                   lease_expires_at=NULL,fencing_token=fencing_token+1,
                   updated_at=?,last_error_code='cancelled'
                   WHERE tenant_id=? AND namespace=? AND job_id=?""",
                (now,scope.tenant_id,scope.namespace,job_id),
            )
            self._audit(
                connection,scope,job_id=job_id,operation_type="job_cancel",
                policy_version=job.policy_version,actor_id=scope.principal_id,
                recorded_at=now,status="cancelled",error_code="cancelled",
                target_type=job.target_type,target_id=job.target_id,
            )
            return _job_from_row(self._row(connection,scope,job_id))

    @_translate_sqlite_errors
    def retry(self, scope: AuthorizedScope, job_id: str) -> MindJob:
        """Trusted explicit retry of transient terminal failures, retaining attempts."""
        scope = _authorized(scope)
        job_id = _IDENT.validate_python(job_id)
        with self._tx() as connection:
            now = _timestamp(_utc_now(self.clock))
            row = self._row(connection,scope,job_id)
            if row is None:
                raise InvalidJobTransitionError("job is absent from authorized scope")
            job = _job_from_row(row)
            if job.status is not JobStatus.FAILED or job.last_error_code not in _RETRYABLE_CODES:
                raise InvalidJobTransitionError("only transient failed jobs may be retried")
            if job.max_attempts >= 20 or self._active_count(connection,scope) >= self.max_pending:
                raise QueueCapacityError("retry exceeds configured job bound")
            connection.execute(
                """UPDATE mind_jobs SET status='queued',max_attempts=?,
                   available_at=?,updated_at=?,last_error_code=NULL
                   WHERE tenant_id=? AND namespace=? AND job_id=? AND status='failed'""",
                (min(20,max(job.max_attempts+1,job.attempt_count+1)),now,now,
                 scope.tenant_id,scope.namespace,job_id),
            )
            self._audit(
                connection,scope,job_id=job_id,operation_type="job_retry",
                policy_version=job.policy_version,actor_id=scope.principal_id,
                recorded_at=now,status="queued",
                target_type=job.target_type,target_id=job.target_id,
            )
            return _job_from_row(self._row(connection,scope,job_id))

    @_translate_sqlite_errors
    def get_job(self, scope: AuthorizedScope, job_id: str) -> MindJob | None:
        scope = _authorized(scope)
        job_id = _IDENT.validate_python(job_id)
        with self._read() as connection:
            row = self._row(connection,scope,job_id)
            return None if row is None else _job_from_row(row)

    @_translate_sqlite_errors
    def list_jobs(
        self, scope: AuthorizedScope, *, limit: int = 100,
        status: JobStatus | None = None,
    ) -> tuple[MindJob,...]:
        scope = _authorized(scope)
        _bounded(limit,100,"job page limit")
        with self._read() as connection:
            if status is not None:
                status = JobStatus(status)
                rows = connection.execute(
                    """SELECT * FROM mind_jobs WHERE tenant_id=? AND namespace=?
                       AND status=? ORDER BY created_at DESC,job_id LIMIT ?""",
                    (scope.tenant_id,scope.namespace,status.value,limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """SELECT * FROM mind_jobs WHERE tenant_id=? AND namespace=?
                       ORDER BY created_at DESC,job_id LIMIT ?""",
                    (scope.tenant_id,scope.namespace,limit),
                ).fetchall()
            return tuple(_job_from_row(row) for row in rows)

    @_translate_sqlite_errors
    def status(self, scope: AuthorizedScope | None = None):
        if scope is None:
            return super().status()
        scope = _authorized(scope)
        now = _utc_now(self.clock)
        with self._read() as connection:
            counts = {value.value: 0 for value in JobStatus}
            for row in connection.execute(
                """SELECT status,COUNT(*) FROM mind_jobs WHERE tenant_id=? AND namespace=?
                   GROUP BY status""",
                (scope.tenant_id,scope.namespace),
            ):
                counts[row[0]] = int(row[1])
            pending = connection.execute(
                """SELECT MIN(created_at) FROM mind_jobs WHERE tenant_id=? AND namespace=?
                   AND status IN ('queued','running','retry_wait')""",
                (scope.tenant_id,scope.namespace),
            ).fetchone()[0]
            completed = connection.execute(
                """SELECT MAX(updated_at) FROM mind_jobs WHERE tenant_id=? AND namespace=?
                   AND status='completed'""",
                (scope.tenant_id,scope.namespace),
            ).fetchone()[0]
            latest_error = connection.execute(
                """SELECT last_error_code FROM mind_jobs WHERE tenant_id=? AND namespace=?
                   AND last_error_code IS NOT NULL ORDER BY updated_at DESC,job_id DESC LIMIT 1""",
                (scope.tenant_id,scope.namespace),
            ).fetchone()
            outbox_pending = int(connection.execute(
                """SELECT COUNT(*) FROM mind_event_outbox WHERE tenant_id=?
                   AND namespace=? AND dispatched_at IS NULL""",
                (scope.tenant_id,scope.namespace),
            ).fetchone()[0])
            events_pending = int(connection.execute(
                """SELECT COUNT(*) FROM (
                       SELECT event_id FROM mind_event_outbox
                       WHERE tenant_id=? AND namespace=? AND dispatched_at IS NULL
                       UNION
                       SELECT target_id FROM mind_jobs
                       WHERE tenant_id=? AND namespace=? AND job_type='extract_event'
                         AND status IN ('queued','running','retry_wait')
                   )""",
                (scope.tenant_id,scope.namespace,scope.tenant_id,scope.namespace),
            ).fetchone()[0])
            reviews_pending = int(connection.execute(
                """SELECT COUNT(*) FROM mind_review_proposals
                   WHERE tenant_id=? AND namespace=? AND status='pending'""",
                (scope.tenant_id,scope.namespace),
            ).fetchone()[0])
            age = None
            if pending is not None:
                age = max(0.0,(now-datetime.fromisoformat(pending.replace("Z","+00:00"))).total_seconds())
            return {
                **counts,
                "oldest_pending_age_seconds": age,
                "last_completed_at": completed,
                "last_error_code": latest_error[0] if latest_error else None,
                "outbox_pending": outbox_pending,
                "events_pending_extraction": events_pending,
                "outstanding_review_proposals": reviews_pending,
            }

    @_translate_sqlite_errors
    def attempt_count(self, scope: AuthorizedScope, job_id: str) -> int:
        scope = _authorized(scope)
        job_id = _IDENT.validate_python(job_id)
        with self._read() as connection:
            return int(connection.execute(
                """SELECT COUNT(*) FROM mind_job_attempts
                   WHERE tenant_id=? AND namespace=? AND job_id=?""",
                (scope.tenant_id,scope.namespace,job_id),
            ).fetchone()[0])
    @_translate_sqlite_errors
    def event_intake_status(self, scope: AuthorizedScope, event_id: str) -> dict[str, str | None]:
        """Report durable intake and latest extraction job state, without claiming completion."""
        authorized = _authorized(scope)
        identifier = _IDENT.validate_python(event_id)
        with self._read() as connection:
            row = connection.execute(
                """SELECT dispatched_at FROM mind_event_outbox
                   WHERE tenant_id=? AND namespace=? AND event_id=?""",
                (authorized.tenant_id, authorized.namespace, identifier),
            ).fetchone()
            if row is None:
                raise ScopeMismatchError("intake target is absent from authorized scope")
            job = connection.execute(
                """SELECT status FROM mind_jobs
                   WHERE tenant_id=? AND namespace=? AND target_type='event'
                     AND target_id=? AND job_type='extract_event'
                   ORDER BY updated_at DESC,job_id DESC LIMIT 1""",
                (authorized.tenant_id, authorized.namespace, identifier),
            ).fetchone()
            return {
                "outbox_state": "pending" if row["dispatched_at"] is None else "dispatched",
                "latest_extraction_job_status": job[0] if job else None,
            }
