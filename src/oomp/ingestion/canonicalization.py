"""Conservative, versioned textual identity for derived memories."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone

from oomp.domain.models import MemoryEvent, MemoryNode

from .contracts import MemoryCandidate

CANONICALIZATION_VERSION = "1"


def normalize_content(content: str) -> str:
    """NFC, collapsed whitespace, and one terminal period; no paraphrase merge."""
    normalized = unicodedata.normalize("NFC", content)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.rstrip(".") + "."


def canonical_key(candidate: MemoryCandidate, event: MemoryEvent) -> str:
    content = normalize_content(candidate.canonical_content)
    identity = [
        candidate.tenant_id, candidate.namespace, candidate.memory_type.value,
        event.source_type.value, content,
    ]
    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return "v1:" + digest


def canonicalize(
    candidate: MemoryCandidate, event: MemoryEvent, *, now: datetime | None = None
) -> MemoryNode:
    if (candidate.tenant_id, candidate.namespace, candidate.source_event_id) != (
        event.tenant_id, event.namespace, event.event_id
    ):
        raise ValueError("candidate source or scope differs from event")
    key = canonical_key(candidate, event)
    timestamp = now or datetime.now(timezone.utc)
    return MemoryNode(
        memory_id="mem-" + key[3:],
        tenant_id=candidate.tenant_id,
        namespace=candidate.namespace,
        memory_type=candidate.memory_type,
        canonical_content=normalize_content(candidate.canonical_content),
        canonical_key=key,
        source_event_ids=(event.event_id,),
        provenance=(event.source_reference,),
        confidence=None,
        created_at=timestamp,
        updated_at=timestamp,
        valid_from=None,
        valid_until=None,
        metadata={
            "attribution": event.source_type.value,
            "verified": False,
            "canonicalization_version": CANONICALIZATION_VERSION,
        },
    )
