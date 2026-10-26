"""Bounded, nonmutating conflict discovery with explicit trusted decisions."""

from __future__ import annotations

from os import PathLike

from oomp.domain.enums import RelationshipType
from oomp.domain.models import AuthorizedScope
from oomp.graph.service import GraphService
from oomp.storage.memory_store import SQLiteMemoryStore
from oomp.storage.mind_projection_store import SQLiteMindProjectionStore
from oomp.storage.sqlite import SQLiteEventStore

from .contracts import ReviewRecord, ReviewStatus
from .scheduler import _authorized


class ConflictReviewer:
    """Only Stage 4's structured RAM policy can propose protected relations."""

    def __init__(self, path: str | PathLike[str] | None = None) -> None:
        self.graph = GraphService(path)
        self.memories = SQLiteMemoryStore(path)
        self.events = SQLiteEventStore(path)
        self.projections = SQLiteMindProjectionStore(path)

    def inspect_event(
        self, scope: AuthorizedScope, event_id: str, *,
        max_memories: int = 64, max_proposals: int = 16,
    ) -> int:
        authorized = _authorized(scope)
        event = self.events.get(authorized, event_id)
        if event is None:
            raise ValueError("source event is missing from authorized scope")
        if type(max_memories) is not int or not 2 <= max_memories <= 100:
            raise ValueError("review memory bound must be 2 to 100")
        if type(max_proposals) is not int or not 1 <= max_proposals <= 32:
            raise ValueError("review proposal bound must be 1 to 32")
        page = self.memories.list_memories(authorized, limit=max_memories)
        if page.next_cursor is not None:
            raise ValueError("review corpus exceeds complete bound")
        sources = tuple(
            memory for memory in page.memories if event_id in memory.source_event_ids
        )
        if not sources:
            return 0
        created = 0
        seen: set[str] = set()
        for source in sources:
            for target in page.memories:
                if source.memory_id == target.memory_id:
                    continue
                if len(target.source_event_ids) > 4:
                    raise ValueError("review target evidence exceeds bound")
                for target_event_id in target.source_event_ids:
                    assessment = self.graph.propose_conflict(
                        authorized, source.memory_id, target.memory_id,
                        source_event_id=event_id, target_event_id=target_event_id,
                    )
                    proposal = assessment.proposal
                    if proposal is None or proposal.proposal_id in seen:
                        continue
                    seen.add(proposal.proposal_id)
                    if len(seen) > max_proposals:
                        raise ValueError("review proposals exceed complete bound")
                    _, was_created = self.projections.save_review(authorized, proposal)
                    created += int(was_created)
        return created

    def reject(self, scope: AuthorizedScope, proposal_id: str) -> ReviewRecord:
        return self.projections.decide_review(
            _authorized(scope), proposal_id, ReviewStatus.REJECTED,
        )

    def approve(self, scope: AuthorizedScope, proposal_id: str) -> ReviewRecord:
        """Apply Stage 4 policy and record approval in the same SQLite transaction."""
        return self.projections.approve_review(_authorized(scope), proposal_id)
