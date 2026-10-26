"""Deterministic topic consolidation over explicit Stage 4 memberships."""

from __future__ import annotations

from os import PathLike

from oomp.domain.models import AuthorizedScope
from oomp.storage.mind_projection_store import SQLiteMindProjectionStore

from .contracts import SummaryRevision
from .scheduler import _authorized


class TopicConsolidator:
    def __init__(self, path: str | PathLike[str] | None = None) -> None:
        self.store = SQLiteMindProjectionStore(path)

    def consolidate(
        self, scope: AuthorizedScope, topic_id: str, *,
        max_sources: int = 16, max_chars: int = 4096,
    ) -> tuple[SummaryRevision | None, bool]:
        return self.store.consolidate_topic(
            _authorized(scope), topic_id,
            max_sources=max_sources, max_chars=max_chars,
        )

    def get(
        self, scope: AuthorizedScope, topic_id: str, *,
        known_at=None,
    ) -> SummaryRevision | None:
        return self.store.get_summary(_authorized(scope), topic_id, known_at=known_at)
