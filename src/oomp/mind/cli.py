"""Trusted local CLI for explicitly scoped background mind administration."""

from __future__ import annotations

import dataclasses
import json
import sys

from oomp.domain.models import AuthorizedScope


def _scope(args) -> AuthorizedScope:
    return AuthorizedScope(
        tenant_id=args.tenant, namespace=args.namespace, principal_id=args.principal,
    )


def _public(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if isinstance(value, tuple):
        return [_public(item) for item in value]
    if isinstance(value, dict):
        return {key: _public(item) for key, item in value.items()}
    return value


def configure_mind_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "mind", help="run and inspect scoped background memory maintenance",
    )
    commands = parser.add_subparsers(dest="mind_command")
    names = (
        "backfill", "enqueue", "run-once", "work", "status", "jobs",
        "retry", "cancel", "consolidate", "summary", "reviews",
        "retract", "erase-plan", "erase-confirm",
    )
    created = {name: commands.add_parser(name) for name in names}
    for cmd in created.values():
        cmd.add_argument("--db", required=True, metavar="PATH")
        cmd.add_argument("--tenant", required=True)
        cmd.add_argument("--namespace", required=True)
        cmd.add_argument("--principal", default="local-cli")
    created["backfill"].add_argument("--limit", type=int, default=100)
    created["enqueue"].add_argument(
        "--type", required=True,
        choices=("extract_event", "maintain_index", "consolidate_topic", "inspect_conflicts"),
    )
    created["enqueue"].add_argument("--target-id", required=True)
    created["enqueue"].add_argument("--generation", required=True)
    created["enqueue"].add_argument("--include-embeddings", action="store_true")
    created["run-once"].add_argument("--max-jobs", type=int, default=16)
    created["work"].add_argument("--max-jobs", type=int, default=16)
    created["work"].add_argument("--poll-seconds", type=float, default=1.0)
    created["work"].add_argument("--cycles", type=int)
    created["jobs"].add_argument("--limit", type=int, default=50)
    created["jobs"].add_argument("--status")
    for name in ("retry", "cancel"):
        created[name].add_argument("--job-id", required=True)
    for name in ("consolidate", "summary"):
        created[name].add_argument("--topic-id", required=True)
    created["summary"].add_argument("--known-at")
    created["summary"].add_argument("--show-content", action="store_true")
    created["reviews"].add_argument(
        "--action", choices=("list", "approve", "reject"), default="list",
    )
    created["reviews"].add_argument("--proposal-id")
    created["reviews"].add_argument("--limit", type=int, default=50)
    created["reviews"].add_argument("--confirm", action="store_true")
    created["retract"].add_argument("--memory-id", required=True)
    created["retract"].add_argument("--event-id", required=True)
    created["retract"].add_argument("--reason-code", default="operator_retraction")
    created["retract"].add_argument("--confirm", action="store_true")
    created["erase-plan"].add_argument("--event-id", required=True)
    created["erase-confirm"].add_argument("--event-id", required=True)
    created["erase-confirm"].add_argument("--plan-digest", required=True)
    created["erase-confirm"].add_argument("--confirm", action="store_true")
    for name in ("enqueue", "run-once", "work"):
        cmd = created[name]
        cmd.add_argument("--embedding-provider", choices=("ollama",))
        cmd.add_argument("--embedding-model")
        cmd.add_argument("--embedding-version", default="ollama-api-embed-v1")
        cmd.add_argument("--embedding-dimension", type=int)
        cmd.add_argument("--embedding-endpoint", default="http://127.0.0.1:11434")
        cmd.add_argument("--embedding-timeout", type=float, default=15.0)
    for name in ("run-once", "work"):
        created[name].add_argument("--auto-embed", action="store_true")
        created[name].add_argument("--max-pending", type=int, default=1000)
        created[name].add_argument("--extraction-mode", choices=("legacy", "rules", "local-llm"), default="legacy")
        created[name].add_argument("--extraction-model")
        created[name].add_argument("--extraction-endpoint", default="http://127.0.0.1:11434")


def _provider(args):
    from oomp.providers import OllamaEmbeddingProvider
    if args.embedding_provider is None:
        if getattr(args, "auto_embed", False):
            raise ValueError("auto embedding requires a configured local provider")
        return None
    if not args.embedding_model or args.embedding_dimension is None:
        raise ValueError("embedding model and dimension are required")
    return OllamaEmbeddingProvider(
        model=args.embedding_model, dimension=args.embedding_dimension,
        version=args.embedding_version, endpoint=args.embedding_endpoint,
        timeout_seconds=args.embedding_timeout,
    )


def mind_command(args) -> int:
    from oomp.mind.contracts import JobType, ReviewStatus
    from oomp.mind.scheduler import MindScheduler
    from oomp.mind.worker import MindWorker
    from oomp.mind.consolidation import TopicConsolidator
    from oomp.mind.governance import ConflictReviewer
    from oomp.storage.mind_store import SQLiteMindStore
    from oomp.storage.mind_projection_store import SQLiteMindProjectionStore
    try:
        scope = _scope(args)
        queue = SQLiteMindStore(args.db)
        scheduler = MindScheduler(args.db)
        command = args.mind_command
        if command == "backfill":
            result = {"backfilled": scheduler.backfill(scope, limit=args.limit)}
        elif command == "enqueue":
            kind = JobType(args.type)
            provider = _provider(args)
            if args.include_embeddings and (kind is not JobType.MAINTAIN_INDEX or provider is None):
                raise ValueError("embedding index job requires maintain_index and configured provider")
            config = (
                {"include_embeddings": True, "space": provider.space.model_dump(mode="json")}
                if args.include_embeddings else {}
            )
            job = scheduler.enqueue(
                scope, kind, args.target_id,
                generation=args.generation, config=config,
            )
            result = {"job_id": job.job_id, "status": job.status.value}
        elif command in {"run-once", "work"}:
            from oomp.understanding.contracts import ExtractionConfiguration
            if args.extraction_mode == "legacy" and args.extraction_model:
                raise ValueError("extraction_mode_required")
            extraction = None if args.extraction_mode == "legacy" else ExtractionConfiguration(
                mode=args.extraction_mode, model=args.extraction_model, endpoint=args.extraction_endpoint)
            worker = MindWorker(
                args.db, scope, embedding_provider=_provider(args),
                auto_embed_on_extract=args.auto_embed, max_pending=args.max_pending,
                extraction_configuration=extraction,
            )
            if command == "run-once":
                result = worker.run_once(max_jobs=args.max_jobs)
            else:
                result = worker.work(
                    max_jobs=args.max_jobs, poll_seconds=args.poll_seconds,
                    max_cycles=args.cycles,
                )
        elif command == "status":
            result = queue.status(scope)
        elif command == "jobs":
            result = [
                {
                    "job_id": job.job_id, "type": job.job_type.value,
                    "target_type": job.target_type, "target_id": job.target_id,
                    "status": job.status.value, "attempts": job.attempt_count,
                    "last_error_code": job.last_error_code,
                }
                for job in queue.list_jobs(scope, status=args.status, limit=args.limit)
            ]
        elif command in {"retry", "cancel"}:
            job = (
                queue.retry(scope, args.job_id)
                if command == "retry" else queue.cancel(scope, args.job_id)
            )
            result = {"job_id": job.job_id, "status": job.status.value}
        elif command == "consolidate":
            revision, created = TopicConsolidator(args.db).consolidate(
                scope, args.topic_id,
            )
            result = {
                "revision_id": revision.revision_id if revision else None,
                "revision_number": revision.revision_number if revision else None,
                "created": created,
            }
        elif command == "summary":
            known = None
            if args.known_at:
                from oomp.cli import _graph_timestamp
                known = _graph_timestamp(args.known_at)
            revision = TopicConsolidator(args.db).get(
                scope, args.topic_id, known_at=known,
            )
            if revision is None:
                result = {"summary": None}
            else:
                result = revision.model_dump(mode="json")
                if not args.show_content:
                    result.pop("content", None)
                    for source in result["sources"]:
                        source.pop("source_reference", None)
        elif command == "reviews":
            reviewer = ConflictReviewer(args.db)
            if args.action == "list":
                records = SQLiteMindProjectionStore(args.db).list_reviews(
                    scope, status=ReviewStatus.PENDING, limit=args.limit,
                )
                result = [
                    {
                        "proposal_id": item.proposal_id, "relationship": item.relationship_type,
                        "source_node_id": item.source_node_id,
                        "target_node_id": item.target_node_id,
                        "source_event_ids": item.source_event_ids,
                        "status": item.status.value,
                    }
                    for item in records
                ]
            else:
                if not args.proposal_id or not args.confirm:
                    raise ValueError("proposal ID and explicit --confirm are required")
                decided = (
                    reviewer.approve(scope, args.proposal_id)
                    if args.action == "approve"
                    else reviewer.reject(scope, args.proposal_id)
                )
                result = {"proposal_id": decided.proposal_id, "status": decided.status.value}
        elif command == "retract":
            if not args.confirm:
                raise ValueError("explicit --confirm is required")
            changed = SQLiteMindProjectionStore(args.db).retract_source(
                scope, args.memory_id, args.event_id, reason_code=args.reason_code,
            )
            result = {"retracted": changed}
        elif command == "erase-plan":
            from oomp.storage.privacy_store import SQLitePrivacyStore
            plan = SQLitePrivacyStore(args.db).erase_plan(scope, args.event_id)
            result = dataclasses.asdict(plan)
        elif command == "erase-confirm":
            from oomp.storage.privacy_store import SQLitePrivacyStore
            result = SQLitePrivacyStore(args.db).erase_confirm(
                scope, args.event_id, args.plan_digest, confirm=args.confirm,
            )
        else:
            raise ValueError("unknown mind command")
        print(json.dumps(_public(result), ensure_ascii=False, separators=(",", ":")))
        if command in {"run-once", "work"} and (result.failed or result.lost_lease):
            return 1
        return 0
    except KeyboardInterrupt:
        print("Mind worker interrupted.", file=sys.stderr)
        return 130
    except Exception as error:
        print(
            f"Mind operation failed ({type(error).__name__}). "
            "Check scope, database, limits and explicit confirmation.",
            file=sys.stderr,
        )
        return 1
