"""Policy-pinned, scoped scheduling helpers; execution remains explicit."""

from __future__ import annotations

import hashlib
from os import PathLike

from oomp.domain.models import AuthorizedScope, Identifier
from oomp.storage.mind_store import SQLiteMindStore

from .contracts import JobType, MindJob

POLICY_VERSIONS = {
    JobType.EXTRACT_EVENT: "extract.v1",
    JobType.MAINTAIN_INDEX: "index.v1",
    JobType.CONSOLIDATE_TOPIC: "topic-extractive.v1",
    JobType.INSPECT_CONFLICTS: "ram-review.v1",
}


def _authorized(scope: AuthorizedScope) -> AuthorizedScope:
    if not isinstance(scope, AuthorizedScope):
        raise TypeError("trusted AuthorizedScope is required")
    return AuthorizedScope.model_validate(scope.model_dump(mode="json"))


def job_identity(scope: AuthorizedScope, job_type: JobType, target_id: str, generation: str) -> str:
    """One logical effect per scope, target, policy and triggering generation."""
    authorized = _authorized(scope)
    if not isinstance(job_type, JobType):
        job_type = JobType(job_type)
    if not isinstance(target_id, str) or not target_id:
        raise ValueError("target ID is required")
    if not isinstance(generation, str) or not generation or len(generation) > 128:
        raise ValueError("bounded generation is required")
    raw = "\0".join((
        authorized.tenant_id, authorized.namespace, job_type.value,
        POLICY_VERSIONS[job_type], target_id, generation,
    ))
    return "mind-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


class MindScheduler:
    """Store jobs for a trusted scope without importing or starting a worker."""

    def __init__(
        self, path: str | PathLike[str] | None = None, *, max_pending: int = 1000, clock=None,
    ) -> None:
        self.store = SQLiteMindStore(path, max_pending=max_pending, clock=clock)

    def backfill(self, scope: AuthorizedScope, *, limit: int = 100) -> int:
        return self.store.backfill_events(_authorized(scope), limit=limit)

    def dispatch(self, scope: AuthorizedScope, *, limit: int = 100) -> int:
        return self.store.dispatch_outbox(
            _authorized(scope), limit=limit,
            policy_version=POLICY_VERSIONS[JobType.EXTRACT_EVENT],
        )

    def enqueue(
        self, scope: AuthorizedScope, job_type: JobType,
        target_id: Identifier, *, generation: str,
        config: dict | None = None, priority: int = 0,
    ) -> MindJob:
        authorized = _authorized(scope)
        kind = JobType(job_type)
        target_type = {
            JobType.EXTRACT_EVENT: "event",
            JobType.MAINTAIN_INDEX: "event",
            JobType.CONSOLIDATE_TOPIC: "topic",
            JobType.INSPECT_CONFLICTS: "event",
        }[kind]
        return self.store.enqueue(
            authorized, kind, target_type, target_id,
            idempotency_key=job_identity(authorized, kind, target_id, generation),
            policy_version=POLICY_VERSIONS[kind], config=config or {},
            priority=priority,
        )
