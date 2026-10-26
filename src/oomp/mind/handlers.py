"""Policy-checked job handlers over established extraction and retrieval services."""

from __future__ import annotations

from os import PathLike

from oomp.domain.models import AuthorizedScope
from oomp.ingestion.pipeline import ExtractionPipeline
from oomp.retrieval.engine import RetrievalEngine
from oomp.storage.errors import StorageBusyError
from oomp.storage.mind_store import SQLiteMindStore

from .contracts import JobType, MindJob
from .scheduler import POLICY_VERSIONS, MindScheduler, _authorized
from .worker import RetryableMindError, PermanentMindError


class MindHandlers:
    """One bounded operation per job; no job payload is accepted as authority."""

    def __init__(
        self, path: str | PathLike[str] | None = None, *,
        embedding_provider=None, auto_embed_on_extract: bool = False,
        max_pending: int = 1000, clock=None,
    ) -> None:
        self.path = path
        self.pipeline = ExtractionPipeline(path)
        self.retrieval = RetrievalEngine(path, provider=embedding_provider)
        self.scheduler = MindScheduler(path, max_pending=max_pending, clock=clock)
        self.store = SQLiteMindStore(path, max_pending=max_pending, clock=clock)
        if type(auto_embed_on_extract) is not bool:
            raise ValueError("auto embedding option must be boolean")
        if auto_embed_on_extract and embedding_provider is None:
            raise ValueError("auto embedding requires an explicit configured provider")
        self.embedding_provider = embedding_provider
        self.auto_embed_on_extract = auto_embed_on_extract

    def execute(self, scope: AuthorizedScope, job: MindJob) -> dict[str, int]:
        authorized = _authorized(scope)
        if not isinstance(job, MindJob):
            raise TypeError("validated MindJob required")
        current = MindJob.model_validate(job.model_dump(mode="json"))
        if (authorized.tenant_id, authorized.namespace) != (current.tenant_id, current.namespace):
            raise ValueError("job is outside the authorized worker scope")
        if current.policy_version != POLICY_VERSIONS[current.job_type]:
            raise ValueError("job handler policy version is unsupported")
        if current.job_type is JobType.EXTRACT_EVENT:
            if current.target_type != "event" or current.config:
                raise ValueError("extract job target or configuration is unsupported")
            result = self.pipeline.process_event(authorized, current.target_id)
            if result.memory_ids:
                index_config = (
                    {"include_embeddings": True,
                     "space": self.embedding_provider.space.model_dump(mode="json")}
                    if self.auto_embed_on_extract else {}
                )
                self.scheduler.enqueue(
                    authorized, JobType.MAINTAIN_INDEX, current.target_id,
                    generation=current.job_id, config=index_config,
                    priority=10,
                )
                self.scheduler.enqueue(
                    authorized, JobType.INSPECT_CONFLICTS, current.target_id,
                    generation=current.job_id, priority=10,
                )
            return {
                "candidates_extracted": result.candidates_extracted,
                "memories_created": result.memories_created,
                "memories_reused": result.memories_reused,
                "evidence_links_added": result.evidence_links_added,
            }
        if current.job_type is JobType.MAINTAIN_INDEX:
            if current.target_type != "event":
                raise ValueError("index job target is unsupported")
            include_embeddings = current.config.get("include_embeddings", False)
            if type(include_embeddings) is not bool or set(current.config) - {
                "include_embeddings", "space",
            }:
                raise ValueError("index job configuration is unsupported")
            if include_embeddings:
                provider = self.embedding_provider
                if provider is None or "space" not in current.config:
                    raise ValueError("pinned embedding provider is unavailable")
                if provider.space.model_dump(mode="json") != current.config["space"]:
                    raise ValueError("worker embedding space differs from pinned job")
            elif "space" in current.config:
                raise ValueError("embedding space requires explicit opt-in")
            report = self.retrieval.index(
                authorized, batch_size=16, include_embeddings=include_embeddings,
            )
            if report.embeddings_failed:
                if report.failure_code in {"provider_unavailable", "storage_busy"}:
                    raise RetryableMindError(report.failure_code)
                raise PermanentMindError("provider_invalid")
            if "index_scan_incomplete" in report.warnings:
                raise RetryableMindError("storage_busy")
            return {
                "lexical_indexed": report.lexical_indexed,
                "embeddings_indexed": report.embeddings_indexed,
                "embeddings_skipped": report.embeddings_skipped,
            }
        if current.job_type is JobType.CONSOLIDATE_TOPIC:
            if current.target_type != "topic" or current.config:
                raise ValueError("topic job target or configuration is unsupported")
            from .consolidation import TopicConsolidator
            _, created = TopicConsolidator(self.path).consolidate(
                authorized, current.target_id,
            )
            return {"summary_revisions_created": int(created)}
        if current.job_type is JobType.INSPECT_CONFLICTS:
            if current.target_type != "event" or current.config:
                raise ValueError("review job target or configuration is unsupported")
            from .governance import ConflictReviewer
            count = ConflictReviewer(self.path).inspect_event(
                authorized, current.target_id,
            )
            return {"review_proposals_created": count}
        raise ValueError("unsupported mind job type")
