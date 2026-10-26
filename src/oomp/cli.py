"""Local package and event-storage diagnostics."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import re
import sys

from . import __version__


def doctor() -> int:
    healthy = True
    print(f"OOMP {__version__}")
    python_ok = sys.version_info >= (3, 11)
    print(f"Python: {sys.version.split()[0]} ({'OK' if python_ok else 'requires 3.11+'})")
    healthy &= python_ok

    try:
        installed_oomp = importlib.metadata.version("oomp-memory")
        package_ok = installed_oomp == __version__
        print(f"oomp-memory: {installed_oomp} ({'OK' if package_ok else 'version mismatch'})")
        healthy &= package_ok
    except importlib.metadata.PackageNotFoundError:
        print("oomp-memory: not installed")
        healthy = False

    try:
        pydantic_version = importlib.metadata.version("pydantic")
        match = re.fullmatch(
            r"(\d+)\.(\d+)(?:\.(\d+))?(?:\.post\d+)?(?:\+[A-Za-z0-9.]+)?",
            pydantic_version,
        )
        dependency_ok = bool(match and (int(match[1]), int(match[2])) >= (2, 9) and int(match[1]) < 3)
        print(f"pydantic: {pydantic_version} ({'OK' if dependency_ok else 'requires >=2.9,<3'})")
        healthy &= dependency_ok
    except importlib.metadata.PackageNotFoundError:
        print("pydantic: not installed")
        healthy = False

    for module in (
        "oomp.domain.models", "oomp.domain.interfaces", "oomp.retrieval.contracts",
        "oomp.mind.worker", "oomp.storage.mind_projection_store", "oomp.storage.privacy_store",
    ):
        try:
            importlib.import_module(module)
            print(f"{module}: import OK")
        except ImportError as error:
            print(f"{module}: import failed ({error})")
            healthy = False

    print(f"Stage 1 package readiness: {'OK' if healthy else 'FAILED'}")
    print("Stage 6 worker: explicit execution only; database and provider not checked")
    return 0 if healthy else 1


def storage_init(database_path: str | None) -> int:
    """Create or migrate the local event database on explicit request."""
    from .storage import SQLiteEventStore
    from .storage.errors import StorageError

    try:
        store = SQLiteEventStore(database_path)
        version = store.initialize()
    except (StorageError, OSError, ValueError) as error:
        print(f"Storage initialization failed ({type(error).__name__}).", file=sys.stderr)
        return 1
    print(f"Database: {store.path}")
    print(f"Schema version: {version}")
    print("Storage readiness: OK")
    return 0


def storage_status(database_path: str | None) -> int:
    """Inspect an existing database without creating files or directories."""
    from .storage import SQLiteEventStore
    from .storage.errors import StorageError

    try:
        status = SQLiteEventStore(database_path).status()
    except (StorageError, OSError, ValueError) as error:
        print(f"Storage status failed ({type(error).__name__}).", file=sys.stderr)
        return 1
    print(f"Database: {status.path}")
    print(f"Exists: {'yes' if status.exists else 'no'}")
    print(f"Accessible: {'yes' if status.accessible else 'no'}")
    print(f"Schema version: {status.schema_version if status.schema_version is not None else 'unknown'}")
    print(f"Journal mode: {status.journal_mode if status.journal_mode else 'unknown'}")
    print(f"Storage readiness: {'OK' if status.ready else 'NOT READY'}")
    if status.message:
        print(f"Status: {status.message}")
    return 0 if status.ready else 1


def memory_extract(database_path: str | None, tenant: str, namespace: str, event_id: str) -> int:
    """Process one stored event using trusted local-machine scope authority."""
    from .domain.models import AuthorizedScope
    from .ingestion import ExtractionPipeline, ProcessingError
    from .storage.errors import SchemaUpgradeRequiredError, StorageError

    try:
        scope = AuthorizedScope(
            tenant_id=tenant, namespace=namespace, principal_id="local-cli"
        )
        result = ExtractionPipeline(database_path).process_event(scope, event_id)
    except (StorageError, ProcessingError, OSError, ValueError, TypeError) as error:
        if isinstance(error, SchemaUpgradeRequiredError):
            print("Run oomp storage init --db <path> to upgrade the database.", file=sys.stderr)
        print(f"Memory extraction failed ({type(error).__name__}).", file=sys.stderr)
        return 1
    print(result.model_dump_json())
    return 0


def memory_list(
    database_path: str | None, tenant: str, namespace: str, *,
    limit: int, show_content: bool,
) -> int:
    """List scoped memory identifiers and provenance; content requires opt-in."""
    from .domain.models import AuthorizedScope
    from .storage.errors import SchemaUpgradeRequiredError, StorageError
    from .storage.memory_store import SQLiteMemoryStore

    if not 1 <= limit <= 100:
        print("Memory list limit must be from 1 to 100.", file=sys.stderr)
        return 1
    try:
        scope = AuthorizedScope(
            tenant_id=tenant, namespace=namespace, principal_id="local-cli"
        )
        page = SQLiteMemoryStore(database_path).list_memories(scope, limit=limit)
    except (StorageError, OSError, ValueError, TypeError) as error:
        if isinstance(error, SchemaUpgradeRequiredError):
            print("Run oomp storage init --db <path> to upgrade the database.", file=sys.stderr)
        print(f"Memory listing failed ({type(error).__name__}).", file=sys.stderr)
        return 1
    for memory in page.memories:
        record = {
            "memory_id": memory.memory_id,
            "memory_type": memory.memory_type.value,
            "source_event_ids": list(memory.source_event_ids),
            "evidence_count": len(memory.source_event_ids),
        }
        if show_content:
            record["canonical_content"] = memory.canonical_content
        print(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    if page.next_cursor is not None:
        print(f"More memories available after: {page.next_cursor.memory_id}")
    return 0

def _graph_scope(tenant: str, namespace: str):
    from .domain.models import AuthorizedScope

    # This CLI is a trusted local administrative tool, not remote authentication.
    return AuthorizedScope(tenant_id=tenant, namespace=namespace, principal_id="local-cli")


def _graph_timestamp(value: str):
    from datetime import datetime

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("timestamp must be ISO 8601 with a UTC offset") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed


def _edge_summary(record) -> dict[str, object]:
    edge = record.edge
    return {
        "edge_id": edge.edge_id,
        "source_node_id": edge.source_node_id,
        "target_node_id": edge.target_node_id,
        "relationship_type": edge.relationship_type.value,
        "source_event_ids": list(edge.source_event_ids),
        "recorded_at": record.recorded_at.isoformat(),
        "valid_from": edge.valid_from.isoformat() if edge.valid_from else None,
        "valid_until": edge.valid_until.isoformat() if edge.valid_until else None,
    }


def _graph_command(args) -> int:
    from .domain.enums import RelationshipType
    from .graph import GraphService
    from .storage.errors import StorageError

    try:
        scope = _graph_scope(args.tenant, args.namespace)
        service = GraphService(args.db)
        if args.graph_command == "link":
            relation = RelationshipType(args.relationship)
            if relation in {RelationshipType.CONTRADICTS, RelationshipType.SUPERSEDES}:
                if not args.confirm_resolution:
                    raise ValueError("protected relationship requires --confirm-resolution")
                if args.valid_from is not None or args.valid_until is not None:
                    raise ValueError("protected validity comes from the reviewed source memories")
                selected_target = args.event_ids[1] if len(args.event_ids) > 1 else None
                assessment = service.propose_conflict(
                    scope, args.source, args.target,
                    source_event_id=args.event_ids[0],
                    target_event_id=selected_target,
                )
                proposal = assessment.proposal
                if proposal is None or proposal.relationship_type is not relation:
                    raise ValueError("no supported protected relationship proposal")
                if tuple(args.event_ids) != proposal.source_event_ids:
                    raise ValueError("provided event IDs do not match proposal evidence")
                record = service.resolve(scope, proposal, confirm=True)
            else:
                if args.confirm_resolution:
                    raise ValueError("--confirm-resolution is for protected relationships")
                record = service.link(
                    scope, args.source, args.target, relation, args.event_ids,
                    valid_from=args.valid_from, valid_until=args.valid_until,
                )
            print(json.dumps(_edge_summary(record), ensure_ascii=False, separators=(",", ":")))
            return 0
        if args.graph_command == "propose":
            assessment = service.propose_conflict(
                scope, args.source, args.target,
                source_event_id=args.source_event_id,
                target_event_id=args.target_event_id,
            )
            print(assessment.model_dump_json())
            return 0
        if args.graph_command == "neighbors":
            records = service.neighbors(
                scope, args.memory_id, direction=args.direction, limit=args.limit,
            )
            for record in records:
                print(json.dumps(_edge_summary(record), ensure_ascii=False, separators=(",", ":")))
            return 0
        if args.graph_command == "history":
            result = service.history(
                scope, args.memory_id, valid_at=args.valid_at, known_at=args.known_at,
            )
            state = result.memory
            summary = {
                "memory_id": state.memory_id,
                "known": state.known,
                "valid": state.valid,
                "effective_status": state.effective_status.value if state.effective_status else None,
                "recorded_at": state.recorded_at.isoformat() if state.recorded_at else None,
                "source_event_ids": list(state.source_event_ids),
                "superseded_by": list(state.superseded_by),
                "legacy_recording_unknown": state.legacy_recording_unknown,
                "incoming_edges": [_edge_summary(record) for record in result.incoming_edges],
                "outgoing_edges": [_edge_summary(record) for record in result.outgoing_edges],
            }
            print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
            return 0
        if args.graph_command == "topic-tree":
            tree = service.topic_tree(
                scope, args.root_topic_id, max_depth=args.max_depth,
                max_nodes=args.max_nodes,
            )
            print(json.dumps({
                "root_topic_id": tree.root_topic_id,
                "truncated": tree.truncated,
                "nodes": [
                    {
                        "topic_id": node.topic.topic_id,
                        "parent_id": node.topic.parent_id,
                        "depth": node.depth,
                        "memory_ids": list(node.memory_ids),
                    }
                    for node in tree.nodes
                ],
            }, ensure_ascii=False, separators=(",", ":")))
            return 0
    except (StorageError, OSError, ValueError, TypeError) as error:
        print(f"Graph operation failed ({type(error).__name__}).", file=sys.stderr)
        return 1
    raise AssertionError("unknown graph command")

def _retrieval_provider(args):
    if args.embedding_provider is None:
        if args.embedding_model is not None or args.embedding_dimension is not None:
            raise ValueError("--embedding-provider ollama is required for model options")
        return None
    if args.embedding_provider != "ollama":
        raise ValueError("unsupported embedding provider")
    if args.embedding_model is None or args.embedding_dimension is None:
        raise ValueError("--embedding-model and --embedding-dimension are required")
    from .providers import OllamaEmbeddingProvider
    return OllamaEmbeddingProvider(
        model=args.embedding_model, dimension=args.embedding_dimension,
        endpoint=args.embedding_endpoint, timeout_seconds=args.embedding_timeout,
        version=args.embedding_version,
    )


def _retrieval_scope(args):
    from .domain.models import AuthorizedScope
    return AuthorizedScope(
        tenant_id=args.tenant, namespace=args.namespace, principal_id="local-cli"
    )


def _retrieval_command(args) -> int:
    from .retrieval.contracts import RetrievalRequest
    from .retrieval.engine import RetrievalEngine, RetrievalUnavailableError
    from .storage.errors import StorageError, SchemaUpgradeRequiredError, RetrievalLimitError, EmbeddingSpaceError
    from .providers import EmbeddingProviderError
    from pydantic import ValidationError

    try:
        scope = _retrieval_scope(args)
        provider = _retrieval_provider(args)
        engine = RetrievalEngine(args.db, provider=provider)
        if args.command == "memory" and args.memory_command == "index":
            report = engine.index(
                scope, batch_size=args.batch_size,
                include_embeddings=provider is not None,
            )
            print(json.dumps(report.__dict__, ensure_ascii=False, separators=(",", ":")))
            return 1 if report.embeddings_failed else 0
        if args.command == "retrieval" and args.retrieval_command == "status":
            status = engine.index_status(scope)
            print(json.dumps(status.__dict__, ensure_ascii=False, separators=(",", ":")))
            return 0
        if args.command == "retrieve":
            request = RetrievalRequest(
                tenant_id=scope.tenant_id, namespace=scope.namespace,
                query=args.query, mode=args.mode, max_results=args.max_results,
                token_budget=args.token_budget, candidate_limit=args.candidate_limit,
                min_semantic_similarity=args.min_semantic_similarity,
                graph_depth=args.graph_depth, graph_nodes=args.graph_nodes,
                graph_edges=args.graph_edges, graph_work=args.graph_work,
                graph_relationships=tuple(args.graph_relationships) if args.graph_relationships else RetrievalRequest.model_fields["graph_relationships"].default,
                known_at=args.known_at, valid_at=args.valid_at, as_of=args.as_of,
                historical=args.historical, allow_degraded=args.allow_degraded,
            )
            response = engine.retrieve(scope, request)
            result = response.model_dump(mode="json")
            if not args.show_content:
                result.pop("context_packet", None)
                for memory in result["memories"]:
                    memory.pop("canonical_content", None)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
            else:
                print(
                    f"Retrieval: {response.retrieval_id} mode={response.retrieval_mode.value} "
                    f"memories={len(response.memories)} budget={response.estimated_token_count}/{response.token_budget} "
                    f"method={response.counting_method}"
                )
                for memory in result["memories"]:
                    print(json.dumps(memory, ensure_ascii=False, separators=(",", ":")))
                if response.warnings:
                    print("Warnings: " + ", ".join(response.warnings))
            return 0
    except (StorageError, EmbeddingProviderError, RetrievalUnavailableError, OSError, ValueError, TypeError) as error:
        if isinstance(error, ValidationError):
            hint = "Invalid retrieval options; check timestamps, limits and --help."
        elif isinstance(error, SchemaUpgradeRequiredError):
            hint = "Run oomp storage init --db PATH before retrieval."
        elif isinstance(error, RetrievalLimitError):
            hint = "A configured query, corpus or graph bound was exceeded."
        elif isinstance(error, RetrievalUnavailableError):
            hint = "The selected mode requires an explicit provider and complete compatible index."
        elif isinstance(error, EmbeddingProviderError):
            hint = "The opted-in local embedding service or model is unavailable or invalid."
        elif isinstance(error, EmbeddingSpaceError):
            hint = "The selected embedding space is unavailable or incomplete."
        else:
            hint = "Check scope, database path and command options."
        print(f"Retrieval operation failed ({type(error).__name__}). {hint}", file=sys.stderr)
        return 1
    raise AssertionError("unknown retrieval command")

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="oomp",
        description="OOMP contract, environment, and local storage tools",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("doctor", help="check installed package and runtime readiness")
    storage_parser = subparsers.add_parser("storage", help="inspect or initialize the local event database")
    storage_commands = storage_parser.add_subparsers(dest="storage_command")
    init_parser = storage_commands.add_parser("init", help="initialize or migrate the event database")
    init_parser.add_argument("--db", metavar="PATH", help="database path (overrides OOMP_DB_PATH)")
    status_parser = storage_commands.add_parser("status", help="inspect database readiness without creating it")
    status_parser.add_argument("--db", metavar="PATH", help="database path (overrides OOMP_DB_PATH)")
    memory_parser = subparsers.add_parser("memory", help="extract and inspect local canonical memories")
    memory_commands = memory_parser.add_subparsers(dest="memory_command")
    extract_parser = memory_commands.add_parser("extract", help="extract memories from one stored event")
    extract_parser.add_argument("--tenant", required=True)
    extract_parser.add_argument("--namespace", required=True)
    extract_parser.add_argument("--event-id", required=True)
    extract_parser.add_argument("--db", metavar="PATH", help="database path (overrides OOMP_DB_PATH)")
    list_parser = memory_commands.add_parser("list", help="list memory IDs and evidence in one scope")
    list_parser.add_argument("--tenant", required=True)
    list_parser.add_argument("--namespace", required=True)
    list_parser.add_argument("--db", metavar="PATH", help="database path (overrides OOMP_DB_PATH)")
    list_parser.add_argument("--limit", type=int, default=100, metavar="N")
    list_parser.add_argument("--show-content", action="store_true", help="print canonical content for trusted local inspection")
    index_parser = memory_commands.add_parser("index", help="index scoped canonical memories")
    index_parser.add_argument("--tenant", required=True)
    index_parser.add_argument("--namespace", required=True)
    index_parser.add_argument("--db", metavar="PATH")
    index_parser.add_argument("--batch-size", type=int, default=16)
    retrieve_parser = subparsers.add_parser("retrieve", help="retrieve bounded source-attributed evidence")
    retrieve_parser.add_argument("query")
    retrieve_parser.add_argument("--tenant", required=True)
    retrieve_parser.add_argument("--namespace", required=True)
    retrieve_parser.add_argument("--db", metavar="PATH")
    retrieve_parser.add_argument("--mode", choices=("lexical", "semantic", "hybrid"), default="lexical")
    retrieve_parser.add_argument("--token-budget", type=int, default=1200)
    retrieve_parser.add_argument("--max-results", type=int, default=8)
    retrieve_parser.add_argument("--candidate-limit", type=int, default=40)
    retrieve_parser.add_argument("--min-semantic-similarity", type=float, default=0.2)
    retrieve_parser.add_argument("--graph-depth", type=int, default=1)
    retrieve_parser.add_argument("--graph-nodes", type=int, default=16)
    retrieve_parser.add_argument("--graph-edges", type=int, default=40)
    retrieve_parser.add_argument("--graph-work", type=int, default=200)
    retrieve_parser.add_argument("--graph-relationship", dest="graph_relationships", action="append", choices=("RELATED_TO", "ABOUT", "SUPPORTS", "DERIVED_FROM", "SUPERSEDES", "CONTRADICTS", "DEPENDS_ON"))
    retrieve_parser.add_argument("--known-at", type=_graph_timestamp)
    retrieve_parser.add_argument("--valid-at", type=_graph_timestamp)
    retrieve_parser.add_argument("--as-of", type=_graph_timestamp)
    retrieve_parser.add_argument("--historical", action="store_true")
    retrieve_parser.add_argument("--allow-degraded", action="store_true")
    retrieve_parser.add_argument("--show-content", action="store_true")
    retrieve_parser.add_argument("--json", action="store_true")
    retrieval_parser = subparsers.add_parser("retrieval", help="inspect scoped index completeness")
    retrieval_commands = retrieval_parser.add_subparsers(dest="retrieval_command")
    retrieval_status_parser = retrieval_commands.add_parser("status")
    retrieval_status_parser.add_argument("--tenant", required=True)
    retrieval_status_parser.add_argument("--namespace", required=True)
    retrieval_status_parser.add_argument("--db", metavar="PATH")
    for retr in (index_parser, retrieve_parser, retrieval_status_parser):
        retr.add_argument("--embedding-provider", choices=("ollama",))
        retr.add_argument("--embedding-model")
        retr.add_argument("--embedding-version", default="ollama-api-embed-v1")
        retr.add_argument("--embedding-dimension", type=int)
        retr.add_argument("--embedding-endpoint", default="http://127.0.0.1:11434")
        retr.add_argument("--embedding-timeout", type=float, default=15.0)
    from .mind.cli import configure_mind_parser
    configure_mind_parser(subparsers)
    from .domain.enums import RelationshipType

    graph_parser = subparsers.add_parser("graph", help="inspect and link local memory graph records")
    graph_commands = graph_parser.add_subparsers(dest="graph_command")
    link_parser = graph_commands.add_parser("link", help="link two existing memories with real source evidence")
    link_parser.add_argument("--source", required=True, help="source memory ID")
    link_parser.add_argument("--target", required=True, help="target memory ID")
    link_parser.add_argument("--relationship", required=True, choices=[item.value for item in RelationshipType])
    link_parser.add_argument("--event-id", dest="event_ids", action="append", required=True, help="supporting source event ID; repeat for two-event contradiction")
    link_parser.add_argument("--valid-from", type=_graph_timestamp)
    link_parser.add_argument("--valid-until", type=_graph_timestamp)
    link_parser.add_argument("--confirm-resolution", action="store_true", help="explicitly commit a rederived protected relationship")
    propose_parser = graph_commands.add_parser("propose", help="inspect a conservative conflict proposal without writing")
    propose_parser.add_argument("--source", required=True, help="candidate newer/source memory ID")
    propose_parser.add_argument("--target", required=True, help="candidate older/target memory ID")
    propose_parser.add_argument("--source-event-id")
    propose_parser.add_argument("--target-event-id")
    neighbors_parser = graph_commands.add_parser("neighbors", help="list bounded adjacent edges")
    neighbors_parser.add_argument("--memory-id", required=True)
    neighbors_parser.add_argument("--direction", choices=("both", "incoming", "outgoing"), default="both")
    neighbors_parser.add_argument("--limit", type=int, default=100)
    history_parser = graph_commands.add_parser("history", help="inspect structural and temporal history")
    history_parser.add_argument("--memory-id", required=True)
    history_parser.add_argument("--valid-at", type=_graph_timestamp)
    history_parser.add_argument("--known-at", type=_graph_timestamp)
    topic_parser = graph_commands.add_parser("topic-tree", help="inspect a bounded topic projection")
    topic_parser.add_argument("--root-topic-id", required=True)
    topic_parser.add_argument("--max-depth", type=int, default=3)
    topic_parser.add_argument("--max-nodes", type=int, default=100)
    for graph_subparser in (link_parser, propose_parser, neighbors_parser, history_parser, topic_parser):
        graph_subparser.add_argument("--tenant", required=True)
        graph_subparser.add_argument("--namespace", required=True)
        graph_subparser.add_argument("--db", metavar="PATH", help="database path (overrides OOMP_DB_PATH)")
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return doctor()
    if args.command == "mind":
        from .mind.cli import mind_command
        if args.mind_command is None:
            parser.parse_args(["mind", "--help"])
            return 0
        return mind_command(args)
    if args.command == "storage":
        if args.storage_command == "init":
            return storage_init(args.db)
        if args.storage_command == "status":
            return storage_status(args.db)
        storage_parser.print_help()
        return 0
    if args.command == "memory":
        if args.memory_command == "extract":
            return memory_extract(args.db, args.tenant, args.namespace, args.event_id)
        if args.memory_command == "list":
            return memory_list(
                args.db, args.tenant, args.namespace,
                limit=args.limit, show_content=args.show_content,
            )
        if args.memory_command == "index":
            return _retrieval_command(args)
        memory_parser.print_help()
        return 0
    if args.command == "retrieve":
        return _retrieval_command(args)
    if args.command == "retrieval":
        if args.retrieval_command == "status":
            return _retrieval_command(args)
        retrieval_parser.print_help()
        return 0
    if args.command == "graph":
        if args.graph_command is None:
            graph_parser.print_help()
            return 0
        return _graph_command(args)
    parser.print_help()
    return 0
