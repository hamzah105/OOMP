"""Thin scoped adapter to existing Stage 2–6 services; no protocol implementation."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone

from oomp.domain.enums import MemoryStatus
from oomp.domain.graph import TemporalQuery
from oomp.domain.models import MemoryEvent
from oomp.retrieval.contracts import RetrievalRequest, GraphPath, MemoryEvidence
from oomp.retrieval.engine import RetrievalEngine
from oomp.storage.sqlite import SQLiteEventStore
from oomp.storage.mind_store import SQLiteMindStore
from oomp.storage.retrieval_store import SQLiteRetrievalStore
from oomp.storage.graph_store import _valid_at

from .authorization import GrantResolver
from .configuration import Grant, ServerConfiguration
from .contracts import (
    RetrieveArguments, RetrieveResult, ExpandArguments, ExpandResult, ExpandedEdge,
    SourceArguments, SourceResult, SourceEvidence, StatusArguments, StatusResult,
    IndexInformation, QueueInformation, EmbeddingIdentity, IngestArguments, IngestResult,
)
from .errors import BoundaryError


class MemoryService:
    def __init__(self, config: ServerConfiguration, resolver: GrantResolver):
        self.config, self.resolver = config, resolver
        status = SQLiteEventStore(config.database).status()
        if not status.ready or status.schema_version != 5:
            raise BoundaryError("storage_unavailable")
        provider = config.embedding.construct_provider() if config.embedding else None
        self.retrieval = RetrievalEngine(config.database, provider=provider)
        self.projection = SQLiteRetrievalStore(config.database)
        self.events = SQLiteEventStore(config.database)
        self.mind = SQLiteMindStore(config.database)

    def retrieve(self, grant: Grant, arguments: RetrieveArguments) -> RetrieveResult:
        scope = self.resolver.scope(grant)
        request = RetrievalRequest(
            tenant_id=scope.tenant_id, namespace=scope.namespace,
            **arguments.model_dump(mode="json"),
        )
        response = self.retrieval.retrieve(scope, request)
        return RetrieveResult.model_validate(response.model_dump(mode="json"))

    def expand(self, grant: Grant, arguments: ExpandArguments) -> ExpandResult:
        scope = self.resolver.scope(grant)
        temporal = TemporalQuery(
            known_at=arguments.known_at,
            valid_at=arguments.valid_at if arguments.valid_at is not None else
                (None if arguments.historical else datetime.now(timezone.utc)),
        )
        with self.projection.read_snapshot(scope) as session:
            traversal = session.traverse(
                arguments.memory_id, max_depth=arguments.max_depth,
                max_nodes=arguments.max_nodes,
                allowed_relationships=arguments.allowed_relationships, query=temporal,
            )
            # These are presentation paths over the existing traversal's actual edges.
            paths = {arguments.memory_id: GraphPath(node_ids=(arguments.memory_id,))}
            adjacency = {node: [] for node in traversal.node_ids}
            for record in traversal.edges:
                edge = record.edge
                adjacency[edge.source_node_id].append((edge.target_node_id, record, "forward"))
                adjacency[edge.target_node_id].append((edge.source_node_id, record, "reverse"))
            queue = deque([arguments.memory_id])
            while queue:
                current = queue.popleft()
                previous = paths[current]
                for other, record, direction in adjacency[current]:
                    if other in paths:
                        continue
                    edge = record.edge
                    paths[other] = GraphPath(
                        node_ids=previous.node_ids + (other,),
                        edge_ids=previous.edge_ids + (edge.edge_id,),
                        relationship_types=previous.relationship_types + (edge.relationship_type,),
                        edge_evidence=previous.edge_evidence + (tuple(e.source_reference for e in record.evidence),),
                        edge_directions=previous.edge_directions + (direction,),
                        edge_validity=previous.edge_validity + (_valid_at(edge.valid_from, edge.valid_until, temporal.valid_at),),
                    )
                    queue.append(other)
            memories = []
            for identifier in traversal.node_ids:
                node = session.memory(identifier)
                state = session.memory_state(identifier, temporal)
                if node is None or not state.evidence:
                    raise BoundaryError("not_found")
                memories.append(MemoryEvidence(
                    memory_id=identifier, canonical_content=node.canonical_content,
                    memory_type=node.memory_type, source_event_ids=state.source_event_ids,
                    source_references=tuple(e.source_reference for e in state.evidence),
                    valid_from=node.valid_from, valid_until=node.valid_until,
                    status=state.effective_status or node.status,
                    temporal_status="valid" if state.valid is True else "uncertain",
                    selection_reasons=("explicit_structural_expansion",),
                    graph_paths=(paths[identifier],),
                ))
            edges = tuple(ExpandedEdge(
                edge_id=r.edge.edge_id, source_node_id=r.edge.source_node_id,
                target_node_id=r.edge.target_node_id, relationship_type=r.edge.relationship_type,
                source_event_ids=tuple(e.event_id for e in r.evidence),
                source_references=tuple(e.source_reference for e in r.evidence),
                recorded_at=r.recorded_at, valid_from=r.edge.valid_from,
                valid_until=r.edge.valid_until,
                valid=_valid_at(r.edge.valid_from, r.edge.valid_until, temporal.valid_at),
            ) for r in traversal.edges)
        return ExpandResult(memory_id=arguments.memory_id, memories=tuple(memories),
                            edges=edges, truncated=traversal.truncated)

    def get_source(self, grant: Grant, arguments: SourceArguments) -> SourceResult:
        if arguments.include_content and "read_source" not in grant.capabilities:
            raise BoundaryError("forbidden")
        scope = self.resolver.scope(grant)
        with self.projection.read_snapshot(scope) as session:
            state = session.memory_state(arguments.memory_id, TemporalQuery(known_at=arguments.known_at))
            if (state.known is not True or not state.evidence
                    or state.effective_status is MemoryStatus.RETRACTED):
                raise BoundaryError("not_found")
            identifiers = sorted(state.source_event_ids)
            if arguments.event_id is not None:
                if arguments.event_id not in identifiers:
                    raise BoundaryError("not_found")
                identifiers = [arguments.event_id]
            if arguments.after_event_id is not None:
                if arguments.after_event_id not in identifiers:
                    raise BoundaryError("invalid_parameters")
                identifiers = identifiers[identifiers.index(arguments.after_event_id)+1:]
            selected = identifiers[:arguments.limit]
            next_id = selected[-1] if len(identifiers) > len(selected) else None
        sources = []
        for identifier in selected:
            event = self.events.get(scope, identifier)
            if event is None:
                raise BoundaryError("not_found")
            sources.append(SourceEvidence(
                event_id=event.event_id, event_type=event.event_type,
                source_type=event.source_type.value, source_reference=event.source_reference,
                occurred_at=event.occurred_at, ingested_at=event.ingested_at,
                content=event.content if arguments.include_content else None,
            ))
        return SourceResult(memory_id=arguments.memory_id, sources=tuple(sources), next_event_id=next_id)

    def status(self, grant: Grant, arguments: StatusArguments) -> StatusResult:
        scope = self.resolver.scope(grant)
        index = self.retrieval.index_status(scope)
        provider = self.retrieval.provider
        space = provider.space if provider is not None else None
        queue = self.mind.status(scope)
        return StatusResult(
            read_only="ingest" not in grant.capabilities,
            capabilities=grant.capabilities,
            retrieval_modes=("lexical",) if space is None else ("lexical", "semantic", "hybrid"),
            embedding_space=EmbeddingIdentity.model_validate(space.model_dump(mode="json")) if space else None,
            index=IndexInformation(
                canonical_count=index.canonical_count, lexical_count=index.lexical_count,
                lexical_stale=index.lexical_stale,
                compatible_embeddings=index.compatible_embeddings if space else None,
                stale_embeddings=index.stale_embeddings if space else None,
            ),
            jobs=QueueInformation(**{key: queue[key] for key in QueueInformation.model_fields}),
        )

    def ingest(self, grant: Grant, arguments: IngestArguments) -> IngestResult:
        payload = self.resolver.verify_approval(grant, arguments)
        scope = self.resolver.scope(grant)
        event = MemoryEvent(
            **payload.model_dump(mode="python"),
            tenant_id=scope.tenant_id, namespace=scope.namespace,
            source_type=grant.ingest_source_type, ingested_at=datetime.now(timezone.utc),
            metadata={"ingested_by": grant.principal_id, "interface": "mcp"},
        )
        stored = self.events.append(scope, event)
        intake = self.mind.event_intake_status(scope, stored.event_id)
        return IngestResult(event_id=stored.event_id, **intake)