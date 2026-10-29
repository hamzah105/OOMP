"""Explicit same-host worker with bounded SQLite claims and fenced acknowledgements."""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from os import PathLike
from typing import Callable

from oomp.domain.models import AuthorizedScope
from oomp.storage.errors import StorageBusyError
from oomp.storage.mind_store import SQLiteMindStore, QueueCapacityError

from .contracts import MindJob
from .scheduler import POLICY_VERSIONS, MindScheduler, _authorized


class RetryableMindError(RuntimeError):
    """A sanitized operation may be retried within the job's attempt bound."""

    def __init__(self, code: str = "provider_unavailable") -> None:
        self.code = code
        super().__init__(code)


class PermanentMindError(ValueError):
    """A sanitized invalid operation must reach terminal failure."""

    def __init__(self, code: str = "validation_error") -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class WorkerRun:
    claimed: int = 0
    completed: int = 0
    retried: int = 0
    failed: int = 0
    lost_lease: int = 0
    dispatched: int = 0


def _error_code(error: BaseException) -> str:
    if isinstance(error, QueueCapacityError):
        return "queue_full"
    if isinstance(error, StorageBusyError) or (
        isinstance(error, sqlite3.OperationalError)
        and getattr(error, "sqlite_errorname", "").startswith(("SQLITE_BUSY", "SQLITE_LOCKED"))
    ):
        return "storage_busy"
    if isinstance(error, (RetryableMindError, PermanentMindError)):
        return error.code
    if isinstance(error, (TypeError, ValueError)):
        return "validation_error"
    return "unknown_error"


def _retryable(error: BaseException) -> bool:
    return isinstance(error, (StorageBusyError, QueueCapacityError, RetryableMindError)) or (
        isinstance(error, sqlite3.OperationalError)
        and getattr(error, "sqlite_errorname", "").startswith(("SQLITE_BUSY", "SQLITE_LOCKED"))
    )


class MindWorker:
    """Claims only one operator-authorized scope. Effects use existing services."""

    def __init__(
        self, path: str | PathLike[str] | None, scope: AuthorizedScope, *,
        worker_id: str | None = None,
        lease_seconds: int = 120,
        handlers=None,
        clock=None,
        embedding_provider=None,
        auto_embed_on_extract: bool = False,
        max_pending: int = 1000,
        extraction_configuration=None,
        extraction_provider=None,
    ) -> None:
        self.scope = _authorized(scope)
        if type(lease_seconds) is not int or not 10 <= lease_seconds <= 3600:
            raise ValueError("lease duration must be 10 to 3600 seconds")
        self.lease_seconds = lease_seconds
        self.worker_id = worker_id or "worker-" + uuid.uuid4().hex
        self.store = SQLiteMindStore(
            path, busy_timeout_ms=1000, max_pending=max_pending,
            **({"clock": clock} if clock is not None else {}),
        )
        self.scheduler = MindScheduler(path, max_pending=max_pending, clock=clock)
        if handlers is None:
            from .handlers import MindHandlers
            handlers = MindHandlers(
                path, embedding_provider=embedding_provider,
                auto_embed_on_extract=auto_embed_on_extract,
                max_pending=max_pending, clock=clock,
                extraction_configuration=extraction_configuration,
                extraction_provider=extraction_provider,
            )
        self.handlers = handlers

    def _execute(self, job: MindJob) -> tuple[dict[str, int], bool]:
        stop_heartbeat = threading.Event()
        lost = threading.Event()

        def heartbeat() -> None:
            interval = max(1.0, self.lease_seconds / 3)
            while not stop_heartbeat.wait(interval):
                try:
                    if not self.store.renew(
                        self.scope, job.job_id, self.worker_id, job.fencing_token,
                        lease_seconds=self.lease_seconds,
                    ):
                        lost.set()
                        break
                except Exception:
                    lost.set()
                    break

        thread = threading.Thread(
            target=heartbeat, name="oomp-mind-heartbeat", daemon=True,
        )
        thread.start()
        try:
            result = self.handlers.execute(self.scope, job)
        finally:
            stop_heartbeat.set()
            thread.join(timeout=2)
        return result, lost.is_set()

    def run_once(self, *, max_jobs: int = 16, dispatch_limit: int = 100) -> WorkerRun:
        if type(max_jobs) is not int or not 1 <= max_jobs <= 100:
            raise ValueError("max_jobs must be 1 to 100")
        if type(dispatch_limit) is not int or not 1 <= dispatch_limit <= 100:
            raise ValueError("dispatch_limit must be 1 to 100")
        dispatched = self.scheduler.dispatch(self.scope, limit=dispatch_limit)
        claimed = completed = retried = failed = lost_lease = 0
        accepted = tuple(POLICY_VERSIONS.values())
        for _ in range(max_jobs):
            job = self.store.claim(
                self.scope, self.worker_id, lease_seconds=self.lease_seconds,
                accepted_policy_versions=accepted,
            )
            if job is None:
                break
            claimed += 1
            try:
                counts, heartbeat_lost = self._execute(job)
                if heartbeat_lost:
                    lost_lease += 1
                    continue
                if self.store.complete(
                    self.scope, job.job_id, self.worker_id, job.fencing_token,
                    result_counts=counts,
                ):
                    completed += 1
                else:
                    lost_lease += 1
            except KeyboardInterrupt:
                try:
                    self.store.fail(
                        self.scope, job.job_id, self.worker_id, job.fencing_token,
                        error_code="worker_interrupted", retryable=True,
                    )
                finally:
                    raise
            except Exception as error:
                code = _error_code(error)
                try:
                    outcome = self.store.fail(
                        self.scope, job.job_id, self.worker_id, job.fencing_token,
                        error_code=code, retryable=_retryable(error),
                    )
                except Exception:
                    lost_lease += 1
                    continue
                if outcome.status.value == "retry_wait":
                    retried += 1
                elif outcome.status.value == "failed":
                    failed += 1
                else:
                    lost_lease += 1
        return WorkerRun(claimed, completed, retried, failed, lost_lease, dispatched)

    def work(
        self, *, poll_seconds: float = 1.0, max_jobs: int = 16,
        max_cycles: int | None = None, stop: Callable[[], bool] | None = None,
    ) -> WorkerRun:
        if type(poll_seconds) not in (int, float) or not 0.1 <= poll_seconds <= 60:
            raise ValueError("poll interval must be 0.1 to 60 seconds")
        if max_cycles is not None and (type(max_cycles) is not int or not 1 <= max_cycles <= 1_000_000):
            raise ValueError("max_cycles must be 1 to 1000000")
        total = WorkerRun()
        cycles = 0
        while max_cycles is None or cycles < max_cycles:
            if stop is not None and stop():
                break
            try:
                current = self.run_once(max_jobs=max_jobs)
            except StorageBusyError:
                cycles += 1
                if max_cycles is None or cycles < max_cycles:
                    time.sleep(poll_seconds)
                continue
            total = WorkerRun(**{
                field: getattr(total, field) + getattr(current, field)
                for field in WorkerRun.__dataclass_fields__
            })
            cycles += 1
            if current.claimed == 0 and (max_cycles is None or cycles < max_cycles):
                time.sleep(poll_seconds)
        return total
