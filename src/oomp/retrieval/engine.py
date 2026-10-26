"""Scoped retrieval orchestration over indexed canonical memory and graph snapshots."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from os import PathLike
from typing import Protocol, Sequence

from oomp.domain.enums import MemoryStatus, RelationshipType
from oomp.domain.interfaces import EmbeddingProvider as BaseEmbeddingProvider
from oomp.domain.graph import TemporalQuery
from oomp.domain.models import AuthorizedScope, RequestedScope
from oomp.storage.errors import EmbeddingSpaceError, RetrievalLimitError, ScopeMismatchError, StorageBusyError
from oomp.storage.retrieval_store import SQLiteRetrievalStore, content_digest

from .contracts import (
    EmbeddingSpace, GraphPath, MemoryEvidence, RetrievalMode, RetrievalRequest,
    RetrievalResponse, RetrievalTrace,
)
from .fusion import fuse_ranked
from .packing import COUNTING_METHOD, pack_evidence


_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_STOP = frozenset({
    "a", "an", "and", "are", "at", "be", "by", "did", "do", "does", "for",
    "from", "has", "have", "how", "i", "in", "is", "it", "me", "my", "of",
    "on", "or", "our", "the", "their", "them", "there", "these", "this",
    "those", "to", "us", "was", "were", "what", "when", "where", "which",
    "who", "why", "with", "you", "your", "user", "tell", "about",
})
_GRAPH_RELATIONS = (
    RelationshipType.RELATED_TO, RelationshipType.ABOUT, RelationshipType.SUPPORTS,
    RelationshipType.DERIVED_FROM, RelationshipType.SUPERSEDES,
    RelationshipType.CONTRADICTS, RelationshipType.DEPENDS_ON,
)
_PROTECTED = frozenset({RelationshipType.SUPERSEDES, RelationshipType.CONTRADICTS})


class RetrievalUnavailableError(ValueError):
    """The explicitly selected retrieval mode cannot run as requested."""


class ConfiguredEmbeddingProvider(BaseEmbeddingProvider, Protocol):
    space: EmbeddingSpace

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


@dataclass(frozen=True)
class IndexReport:
    lexical_indexed: int
    lexical_skipped: int
    embeddings_indexed: int = 0
    embeddings_skipped: int = 0
    embeddings_failed: int = 0
    warnings: tuple[str, ...] = ()
    failure_code: str | None = None


def _terms(value: str) -> frozenset[str]:
    return frozenset(item.casefold() for item in _WORD.findall(value)
                     if len(item) > 1 and item.casefold() not in _STOP)


def _names(value: str) -> tuple[str, ...]:
    words = re.findall(r"[^\W_]+(?:-[^\W_]+)*", value, re.UNICODE)
    names: list[str] = []
    for width in (1, 2, 3):
        for index in range(len(words) - width + 1):
            part = words[index:index + width]
            if not any(_terms(word) for word in part):
                continue
            candidate = " ".join(part)
            if candidate not in names:
                names.append(candidate)
            if len(names) == 16:
                return tuple(names)
    return tuple(names)


def _scoped_request(scope: AuthorizedScope, request: RetrievalRequest) -> RetrievalRequest:
    if not isinstance(scope, AuthorizedScope):
        raise TypeError("trusted AuthorizedScope is required")
    authorized = AuthorizedScope.model_validate(scope.model_dump(mode="json"))
    if not isinstance(request, RetrievalRequest):
        raise TypeError("a RetrievalRequest is required")
    incoming = RetrievalRequest.model_validate(request.model_dump(mode="json"))
    if (authorized.tenant_id, authorized.namespace) != (incoming.tenant_id, incoming.namespace):
        raise ScopeMismatchError("retrieval request differs from authorized scope")
    if len(incoming.query) > 4096:
        raise RetrievalLimitError("retrieval query exceeds 4096-character runtime limit")
    return incoming


def _path(seed_id: str, other_id: str, record, valid_at=None) -> GraphPath:
    from oomp.storage.graph_store import _valid_at
    return GraphPath(
        node_ids=(seed_id, other_id), edge_ids=(record.edge.edge_id,),
        relationship_types=(record.edge.relationship_type,),
        edge_evidence=(tuple(item.source_reference for item in record.evidence),),
        edge_directions=("forward" if record.edge.source_node_id == seed_id else "reverse",),
        edge_validity=(_valid_at(record.edge.valid_from, record.edge.valid_until, valid_at),),
    )


def _path_relevant(query_terms: frozenset[str], content: str, relationship: RelationshipType) -> bool:
    return relationship in _PROTECTED or bool(query_terms & _terms(content))


class RetrievalEngine:
    """Retrieves source-attributed context, never answers or mutates memory claims."""

    def __init__(
        self, path: str | PathLike[str] | None = None, *,
        provider: ConfiguredEmbeddingProvider | None = None,
    ) -> None:
        self.store = SQLiteRetrievalStore(path)
        self.provider = provider

    def index(
        self, scope: AuthorizedScope, *, batch_size: int = 16,
        include_embeddings: bool = False,
    ) -> IndexReport:
        if type(batch_size) is not int or not 1 <= batch_size <= 16:
            raise ValueError("index batch_size must be 1 to 16")
        if not isinstance(scope, AuthorizedScope):
            raise TypeError("trusted AuthorizedScope is required")
        authorized = AuthorizedScope.model_validate(scope.model_dump(mode="json"))
        lexical_indexed, lexical_skipped = self.store.index_lexical(authorized, batch_size=batch_size)
        if not include_embeddings:
            return IndexReport(lexical_indexed, lexical_skipped)
        if self.provider is None:
            raise RetrievalUnavailableError("explicit embedding provider required for vector indexing")
        space = EmbeddingSpace.model_validate(self.provider.space.model_dump(mode="json"))
        indexed = skipped = failed = 0
        warnings: list[str] = []
        failure_code = None
        cursor = None
        initial_count = self.store.index_status(authorized, space).canonical_count
        visited = 0
        while visited < initial_count:
            page = self.store.embedding_index_plan(authorized, space, batch_size=batch_size, after=cursor)
            if not page.memories:
                break
            visited += len(page.memories)
            pending = self.store.pending_embeddings(authorized, space, page.memories)
            skipped += len(page.memories) - len(pending)
            if pending:
                try:
                    vectors = self.provider.embed(tuple(item.canonical_content for item in pending))
                    if len(vectors) != len(pending):
                        raise RetrievalUnavailableError("embedding provider returned an incomplete batch")
                    items = tuple(
                        (item.memory_id, content_digest(item.canonical_content), vector)
                        for item, vector in zip(pending, vectors, strict=True)
                    )
                    added, existing = self.store.put_embedding_batch(authorized, space, items)
                    indexed += added
                    skipped += existing
                except Exception as error:
                    # Previously committed batches and lexical index remain intact.
                    from oomp.providers.errors import EmbeddingProviderUnavailable
                    failure_code = (
                        "storage_busy" if isinstance(error, StorageBusyError) else
                        "provider_unavailable"
                        if isinstance(error, (EmbeddingProviderUnavailable, TimeoutError, ConnectionError))
                        else "provider_invalid"
                    )
                    failed += len(pending)
                    warnings.append("embedding_batch_failed:" + type(error).__name__)
                    break
            cursor = page.next_cursor
            if cursor is None:
                break
        final_status = self.store.index_status(authorized, space)
        if (visited < initial_count or final_status.compatible_embeddings != final_status.canonical_count
                or final_status.stale_embeddings) and not failed:
            warnings.append("index_scan_incomplete")
        return IndexReport(
            lexical_indexed, lexical_skipped, indexed, skipped, failed,
            tuple(warnings), failure_code,
        )

    def index_status(self, scope: AuthorizedScope):
        space = None if self.provider is None else self.provider.space
        return self.store.index_status(scope, space)

    def retrieve(
        self, scope: AuthorizedScope, request: RetrievalRequest,
    ) -> RetrievalResponse:
        incoming = _scoped_request(scope, request)
        authorized = AuthorizedScope.model_validate(scope.model_dump(mode="json"))
        mode = incoming.mode
        warnings: list[str] = []
        degraded = False
        query_terms = _terms(incoming.query)
        if incoming.known_at is not None:
            warnings.append("historical_entity_index_unavailable")
        vector = None
        space = None
        if mode in {RetrievalMode.SEMANTIC, RetrievalMode.HYBRID}:
            if self.provider is None:
                if mode is RetrievalMode.SEMANTIC or not incoming.allow_degraded:
                    raise RetrievalUnavailableError("semantic retrieval requires an explicit embedding provider")
                degraded = True
                warnings.append("semantic_provider_unavailable")
            else:
                space = EmbeddingSpace.model_validate(self.provider.space.model_dump(mode="json"))
                try:
                    vectors = self.provider.embed((incoming.query,))
                    if len(vectors) != 1:
                        raise RetrievalUnavailableError("embedding provider returned an incomplete query batch")
                    vector = vectors[0]
                except Exception as error:
                    if mode is RetrievalMode.SEMANTIC or not incoming.allow_degraded:
                        raise RetrievalUnavailableError("local query embedding failed") from error
                    degraded = True
                    warnings.append("semantic_query_failed")
                    vector = None
        lanes: dict[str, tuple[str, ...]] = {}
        attribution: dict[str, list[str]] = {}
        trace_counts = {"lexical_candidates": 0, "semantic_candidates": 0,
                        "entity_candidates": 0, "topic_candidates": 0}
        effective_valid_at = incoming.effective_valid_at
        if effective_valid_at is None and not incoming.historical:
            effective_valid_at = datetime.now(timezone.utc)
        temporal = TemporalQuery(known_at=incoming.known_at, valid_at=effective_valid_at)
        paths: dict[str, list[GraphPath]] = {}
        graph_count = 0
        with self.store.read_snapshot(authorized) as session:
            if mode is not RetrievalMode.SEMANTIC:
                lexical = session.lexical(
                    incoming.query, limit=incoming.candidate_limit, known_at=incoming.known_at,
                )
                lexical_ids = []
                for hit in lexical:
                    node = session.memory(hit.memory_id)
                    if node is not None and query_terms & _terms(node.canonical_content):
                        lexical_ids.append(hit.memory_id)
                lanes["lexical"] = tuple(lexical_ids)
                trace_counts["lexical_candidates"] = len(lexical_ids)
            if vector is not None and space is not None:
                try:
                    hits = session.semantic(
                        vector, space, limit=incoming.candidate_limit,
                        known_at=incoming.known_at,
                    )
                except (EmbeddingSpaceError, RetrievalLimitError) as error:
                    if mode is RetrievalMode.SEMANTIC or not incoming.allow_degraded:
                        raise RetrievalUnavailableError("compatible complete embedding index is unavailable") from error
                    degraded = True
                    warnings.append("semantic_index_unavailable")
                else:
                    accepted = tuple(hit for hit in hits if hit.score >= incoming.min_semantic_similarity)
                    lanes["semantic"] = tuple(hit.memory_id for hit in accepted)
                    trace_counts["semantic_candidates"] = len(accepted)
            if mode is not RetrievalMode.SEMANTIC:
                names = _names(incoming.query)
                entity = session.entity_candidates(
                    names, known_at=incoming.known_at, limit=incoming.candidate_limit,
                )
                topic = session.topic_candidates(
                    names, known_at=incoming.known_at, limit=incoming.candidate_limit,
                )
                lanes["entity"] = tuple(hit.memory_id for hit in entity)
                lanes["topic"] = tuple(hit.memory_id for hit in topic)
                trace_counts["entity_candidates"] = len(entity)
                trace_counts["topic_candidates"] = len(topic)
                for hit in entity:
                    attribution.setdefault(hit.memory_id, []).append("entity:" + hit.entity_id)
                for hit in topic:
                    attribution.setdefault(hit.memory_id, []).append("topic:" + hit.topic_id)
            fused = fuse_ranked(lanes)
            scored: dict[str, float] = {item.memory_id: item.score for item in fused}
            reasons: dict[str, list[str]] = {
                item.memory_id: list(item.reasons) + attribution.get(item.memory_id, [])
                for item in fused
            }
            graph_truncated = False
            explored = set()
            if incoming.graph_depth and incoming.graph_relationships:
                seeds = tuple(item.memory_id for item in fused[:min(8, max(1, incoming.graph_nodes // 2))])
                explored.update(seeds)
                frontier = tuple((seed, seed, 0, None) for seed in seeds)
                work = 0
                used_edges: set[str] = set()
                while frontier:
                    next_frontier = []
                    for seed, current, depth, prior_path in frontier:
                        if depth >= incoming.graph_depth:
                            continue
                        state = session.memory_state(current, temporal)
                        if state.known is not True or not state.evidence or state.valid is False:
                            continue
                        if work >= incoming.graph_work:
                            graph_truncated = True
                            continue
                        edges = session.neighbors(
                            current, allowed_relationships=incoming.graph_relationships,
                            known_at=incoming.known_at,
                            limit=min(incoming.graph_work - work, 1000),
                        )
                        remaining = incoming.graph_work - work
                        if len(edges) > remaining:
                            edges = edges[:remaining]
                            graph_truncated = True
                        work += len(edges)
                        for record in edges:
                            edge = record.edge
                            from oomp.storage.graph_store import _valid_at
                            if temporal.valid_at is not None and _valid_at(
                                edge.valid_from, edge.valid_until, temporal.valid_at,
                            ) is False:
                                continue
                            other = edge.target_node_id if edge.source_node_id == current else edge.source_node_id
                            if other == seed or (prior_path is not None and other in prior_path.node_ids):
                                continue
                            node = session.memory(other)
                            if node is None:
                                continue
                            other_state = session.memory_state(other, temporal)
                            if other_state.known is not True or not other_state.evidence or other_state.valid is False:
                                continue
                            if not _path_relevant(query_terms, node.canonical_content, edge.relationship_type):
                                continue
                            if edge.edge_id not in used_edges and len(used_edges) >= incoming.graph_edges:
                                graph_truncated = True
                                continue
                            used_edges.add(edge.edge_id)
                            segment = _path(current, other, record, temporal.valid_at)
                            if prior_path is None:
                                candidate_path = segment
                            else:
                                candidate_path = GraphPath(
                                    node_ids=prior_path.node_ids + (other,),
                                    edge_ids=prior_path.edge_ids + segment.edge_ids,
                                    relationship_types=prior_path.relationship_types + segment.relationship_types,
                                    edge_evidence=prior_path.edge_evidence + segment.edge_evidence,
                                    edge_directions=prior_path.edge_directions + segment.edge_directions,
                                    edge_validity=prior_path.edge_validity + segment.edge_validity,
                                )
                            new_candidate = other not in scored
                            if other not in explored:
                                if len(explored) >= incoming.graph_nodes:
                                    graph_truncated = True
                                    continue
                                explored.add(other)
                                signal = scored[seed] * (
                                    0.6 if edge.relationship_type in _PROTECTED else 0.3
                                )
                                if other not in scored:
                                    graph_count += 1
                                    scored[other] = signal
                                    reasons[other] = ["graph:" + edge.relationship_type.value]
                                else:
                                    scored[other] = max(scored[other], signal)
                                    if edge.relationship_type in _PROTECTED:
                                        reasons[other].append("graph:" + edge.relationship_type.value)
                                next_frontier.append((seed, other, depth + 1, candidate_path))
                            if (new_candidate or edge.relationship_type in _PROTECTED) and len(paths.get(other, ())) < 2:
                                paths.setdefault(other, []).append(candidate_path)
                            if edge.relationship_type is RelationshipType.CONTRADICTS:
                                if len(paths.get(current, ())) < 2:
                                    paths.setdefault(current, []).append(candidate_path)
                    frontier = tuple(next_frontier)
            # Governed replacement lookup can follow an expired historical anchor to
            # the current head. Every hop still needs visible source and edge proof.
            replacement_work = 0
            replacement_queue = list(sorted(
                scored, key=lambda item: (-scored[item], item),
            )[:min(40, incoming.candidate_limit)])
            scheduled = set(replacement_queue)
            checked: set[str] = set()
            governed_paths: dict[str, GraphPath] = {}
            while replacement_queue:
                if len(checked) >= 40:
                    raise RetrievalLimitError("governed replacement chain exceeds bounded nodes")
                memory_id = replacement_queue.pop(0)
                if memory_id in checked:
                    continue
                checked.add(memory_id)
                state = session.memory_state(memory_id, temporal)
                if incoming.historical or state.known is not True or not state.evidence:
                    continue
                if state.effective_status not in {MemoryStatus.SUPERSEDED, None} and state.valid is not False:
                    continue
                if replacement_work >= 200:
                    raise RetrievalLimitError("governed replacement proof exceeds bounded work")
                records = session.neighbors(
                    memory_id, allowed_relationships=(RelationshipType.SUPERSEDES,),
                    known_at=incoming.known_at, limit=min(20, 200 - replacement_work),
                )
                replacement_work += len(records)
                for matching in records:
                    if matching.edge.target_node_id != memory_id:
                        continue
                    from oomp.storage.graph_store import _valid_at
                    relation_valid = _valid_at(
                        matching.edge.valid_from, matching.edge.valid_until, temporal.valid_at,
                    )
                    historical_link = (
                        relation_valid is False and state.valid is False
                        and temporal.valid_at is not None
                        and matching.edge.valid_from is not None
                        and matching.edge.valid_from <= temporal.valid_at
                        and matching.edge.valid_until is not None
                        and matching.edge.valid_until < temporal.valid_at
                    )
                    if relation_valid is False and not historical_link:
                        continue
                    replacement = matching.edge.source_node_id
                    if (state.effective_status is MemoryStatus.SUPERSEDED
                            and replacement not in state.superseded_by):
                        continue
                    replacement_state = session.memory_state(replacement, temporal)
                    if replacement_state.known is not True or not replacement_state.evidence:
                        continue
                    # An expired edge can only carry lineage through another expired
                    # claim; it cannot justify a current replacement by itself.
                    if historical_link and replacement_state.valid is not False:
                        continue
                    prior = governed_paths.get(memory_id)
                    if replacement == memory_id or (prior is not None and replacement in prior.node_ids):
                        continue
                    segment = _path(memory_id, replacement, matching, temporal.valid_at)
                    candidate_path = segment if prior is None else GraphPath(
                        node_ids=prior.node_ids + (replacement,),
                        edge_ids=prior.edge_ids + segment.edge_ids,
                        relationship_types=prior.relationship_types + segment.relationship_types,
                        edge_evidence=prior.edge_evidence + segment.edge_evidence,
                        edge_directions=prior.edge_directions + segment.edge_directions,
                        edge_validity=prior.edge_validity + segment.edge_validity,
                    )
                    governed_paths.setdefault(replacement, candidate_path)
                    if replacement not in scheduled:
                        if len(scheduled) >= 40:
                            raise RetrievalLimitError("governed replacement chain exceeds bounded nodes")
                        replacement_queue.append(replacement)
                        scheduled.add(replacement)
                    uncertain = relation_valid is None
                    if replacement not in scored:
                        if graph_count >= 40:
                            raise RetrievalLimitError("governed replacement candidate bound exceeded")
                        scored[replacement] = scored[memory_id] + (0.005 if uncertain else 0.01)
                        reasons[replacement] = [
                            "uncertain_governed_replacement" if uncertain
                            else "governed_replacement"
                        ]
                        graph_count += 1
                    if uncertain:
                        reasons[memory_id].append("supersession_validity_uncertain")
                        reasons[replacement].append("supersession_validity_uncertain")
                        warnings.append("supersession_validity_uncertain")
                        if len(paths.get(memory_id, ())) < 2:
                            paths.setdefault(memory_id, []).append(candidate_path)
                    if len(paths.get(replacement, ())) < 2:
                        paths.setdefault(replacement, []).append(candidate_path)
            # Read-only governance inspection remains active even with graph_depth=0.
            if len(scored) > 200:
                raise RetrievalLimitError("governed candidate inspection exceeds 200 memories")
            governed_conflicts = 0
            conflict_work = 0
            for memory_id in tuple(sorted(scored, key=lambda item: (-scored[item], item))):
                state = session.memory_state(memory_id, temporal)
                if state.known is not True or not state.evidence or state.valid is False:
                    continue
                if conflict_work >= 2000:
                    raise RetrievalLimitError("governed conflict inspection work limit exceeded")
                records = session.neighbors(
                    memory_id, allowed_relationships=(RelationshipType.CONTRADICTS,),
                    known_at=incoming.known_at, limit=min(20, 2000 - conflict_work),
                )
                conflict_work += len(records)
                for record in records:
                    from oomp.storage.graph_store import _valid_at
                    relation_valid = _valid_at(
                        record.edge.valid_from, record.edge.valid_until, temporal.valid_at,
                    ) if temporal.valid_at is not None else None
                    if relation_valid is False:
                        continue
                    other = (
                        record.edge.target_node_id if record.edge.source_node_id == memory_id
                        else record.edge.source_node_id
                    )
                    if other == memory_id:
                        continue
                    other_state = session.memory_state(other, temporal)
                    if (other_state.known is not True or not other_state.evidence
                            or other_state.valid is False):
                        continue
                    path = _path(memory_id, other, record, temporal.valid_at)
                    if len(paths.get(memory_id, ())) < 2:
                        paths.setdefault(memory_id, []).append(path)
                    if len(paths.get(other, ())) < 2:
                        paths.setdefault(other, []).append(_path(other, memory_id, record, temporal.valid_at))
                    if other not in scored:
                        if governed_conflicts >= 40:
                            raise RetrievalLimitError("governed conflict candidate bound exceeded")
                        scored[other] = scored[memory_id] * 0.8
                        reasons[other] = ["governed_contradiction"]
                        governed_conflicts += 1
                    else:
                        reasons[other].append("governed_contradiction")
                    if relation_valid is None:
                        warnings.append("contradiction_validity_uncertain")
                        reasons[memory_id].append("contradiction_validity_uncertain")
                        reasons[other].append("contradiction_validity_uncertain")
            eligible: list[MemoryEvidence] = []
            for memory_id in sorted(scored, key=lambda item: (-scored[item], item)):
                node = session.memory(memory_id)
                if node is None:
                    continue
                state = session.memory_state(memory_id, temporal)
                if state.known is not True or not state.evidence or state.valid is False:
                    continue
                if state.effective_status is MemoryStatus.RETRACTED:
                    continue
                if state.effective_status is MemoryStatus.SUPERSEDED and not incoming.historical:
                    continue
                relation_paths = tuple(paths.get(memory_id, ())[:2])
                disputed = any(
                    RelationshipType.CONTRADICTS in path.relationship_types
                    for path in relation_paths
                )
                if disputed:
                    temporal_status = "contradicted"
                elif state.effective_status is MemoryStatus.SUPERSEDED:
                    temporal_status = "superseded"
                elif state.effective_status is None or state.valid is None:
                    temporal_status = "uncertain"
                elif incoming.effective_valid_at is not None or incoming.historical:
                    temporal_status = "historical_reported"
                elif node.valid_from is None or node.valid_until is None:
                    temporal_status = "uncertain"
                else:
                    temporal_status = "current_reported"
                evidence = MemoryEvidence(
                    memory_id=node.memory_id, memory_type=node.memory_type,
                    canonical_content=node.canonical_content,
                    source_event_ids=state.source_event_ids,
                    source_references=tuple(item.source_reference for item in state.evidence),
                    retrieval_score=scored[memory_id],
                    valid_from=node.valid_from, valid_until=node.valid_until,
                    status=state.effective_status or node.status,
                    temporal_status=temporal_status,
                    selection_reasons=tuple(dict.fromkeys(reasons.get(memory_id, ())))[:16],
                    graph_paths=relation_paths,
                    metadata={
                        "validity": state.valid,
                        "effective_status": (
                            state.effective_status.value if state.effective_status else None
                        ),
                        "legacy_recording_unknown": state.legacy_recording_unknown,
                    },
                )
                eligible.append(evidence)
        diverse: list[MemoryEvidence] = []
        redundant: list[MemoryEvidence] = []
        seen_content: set[tuple[str, str]] = set()
        for item in eligible:
            normalized = " ".join(item.canonical_content.split()).casefold()
            key = (item.memory_type.value, normalized)
            if key in seen_content:
                redundant.append(item)
            else:
                seen_content.add(key)
                diverse.append(item)
        diversity_reordered = len(redundant)
        packed = pack_evidence((*diverse, *redundant), incoming.token_budget, incoming.max_results)
        if not packed.memories:
            warnings.append("no_supported_evidence_found")
        if graph_truncated:
            warnings.append("graph_expansion_truncated")
        if packed.dropped:
            warnings.append("evidence_omitted_by_budget_or_result_limit")
        sources = tuple(dict.fromkeys(
            reference for item in packed.memories for reference in item.source_references
        ))
        graph_paths = tuple(dict.fromkeys(
            path for item in packed.memories for path in item.graph_paths
        ))
        trace = RetrievalTrace(
            **trace_counts, graph_expanded_candidates=graph_count,
            governed_conflict_candidates=governed_conflicts,
            eligible_candidates=len(eligible), packed_memories=len(packed.memories),
            budget_dropped=packed.dropped,
            graph_truncated=graph_truncated, diversity_reordered=diversity_reordered,
        )
        identity = hashlib.sha256(json.dumps(
            [authorized.tenant_id, authorized.namespace, incoming.model_dump(mode="json"),
             [item.memory_id for item in packed.memories]],
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()[:32]
        return RetrievalResponse(
            retrieval_id="ret-" + identity, memories=packed.memories,
            source_references=sources, graph_paths=graph_paths,
            estimated_token_count=packed.estimated_token_count,
            token_budget=incoming.token_budget, counting_method=COUNTING_METHOD,
            context_packet=packed.context_packet, retrieval_mode=mode,
            degraded=degraded, warnings=tuple(dict.fromkeys(warnings)),
            retrieval_trace=trace,
        )