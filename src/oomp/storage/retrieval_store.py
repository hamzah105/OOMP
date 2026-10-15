"""Bounded, scoped retrieval indexes over canonical memory and Stage 4 history."""
from __future__ import annotations

import hashlib
import math
import re
import sqlite3
import struct
from collections.abc import Iterator, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

from oomp.domain.enums import RelationshipType
from oomp.domain.graph import EdgeRecord, MemoryState, TemporalQuery
from oomp.domain.memories import MemoryCursor, MemoryPage
from oomp.domain.models import AuthorizedScope, MemoryNode
from oomp.retrieval.contracts import EmbeddingSpace

from .memory_store import _normalize_name
from .errors import (
    EmbeddingSpaceError, RetrievalIndexError, RetrievalLimitError,
    ScopeMismatchError, SchemaUpgradeRequiredError, StoredMemoryCorruptionError,
)
from .graph_store import SQLiteGraphStore
from .memory_store import SQLiteMemoryStore
from .migrations import user_version
from .sqlite import _authorized, _timestamp, _translate_sqlite_errors

MAX_LEXICAL_DOCS = 10_000
MAX_LEXICAL_BYTES = 16 * 1024 * 1024
MAX_VECTOR_SCAN = 10_000
MAX_QUERY_CHARS = 4096
MAX_QUERY_TERMS = 32
MAX_CANDIDATES = 200
MAX_EMBEDDING_BATCH = 100
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True)
class LexicalHit:
    memory_id: str
    rank: int
    score: float


@dataclass(frozen=True)
class SemanticHit:
    memory_id: str
    rank: int
    score: float


@dataclass(frozen=True)
class EntityHit:
    memory_id: str
    entity_id: str
    matched_name: str


@dataclass(frozen=True)
class TopicHit:
    memory_id: str
    topic_id: str
    matched_name: str


@dataclass(frozen=True)
class IndexStatus:
    canonical_count: int
    lexical_count: int
    compatible_embeddings: int
    stale_embeddings: int
    lexical_limit: int = MAX_LEXICAL_DOCS
    lexical_bytes_limit: int = MAX_LEXICAL_BYTES
    vector_scan_limit: int = MAX_VECTOR_SCAN
    lexical_stale: int = 0


def content_digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _space_values(space: EmbeddingSpace) -> tuple[str, str, str]:
    if not isinstance(space, EmbeddingSpace):
        raise TypeError("a validated EmbeddingSpace is required")
    value = EmbeddingSpace.model_validate(space.model_dump(mode="json"))
    return value.provider, value.model, value.version


def _vector(vector: Sequence[float], dimension: int) -> tuple[float, ...]:
    if isinstance(vector, (str, bytes)) or len(vector) != dimension:
        raise EmbeddingSpaceError("embedding dimension differs from selected space")
    if any(type(item) not in (int, float) for item in vector):
        raise EmbeddingSpaceError("embedding contains a nonnumeric value")
    try:
        values = tuple(float(item) for item in vector)
    except (TypeError, ValueError, OverflowError):
        raise EmbeddingSpaceError("embedding contains a nonnumeric value") from None
    if any(not math.isfinite(item) for item in values):
        raise EmbeddingSpaceError("embedding contains a nonfinite value")
    if max(abs(item) for item in values) == 0:
        raise EmbeddingSpaceError("embedding must have a nonzero norm")
    return values


def _unit_vector(values: Sequence[float]) -> tuple[float, ...]:
    scale = max(abs(item) for item in values)
    if scale == 0:
        raise EmbeddingSpaceError("embedding must have a nonzero norm")
    scaled = tuple(item / scale for item in values)
    norm = math.sqrt(math.fsum(item * item for item in scaled))
    return tuple(item / norm for item in scaled)


def _decode_vector(blob: bytes, dimension: int) -> tuple[float, ...]:
    if len(blob) != dimension * 8:
        raise RetrievalIndexError("stored embedding dimensions are inconsistent")
    try:
        return _vector(struct.unpack(f"<{dimension}d", blob), dimension)
    except EmbeddingSpaceError:
        raise RetrievalIndexError("stored embedding failed validation") from None


def _validate_limit(limit: int, maximum: int, label: str) -> None:
    if type(limit) is not int or not 1 <= limit <= maximum:
        raise ValueError(f"{label} must be an integer from 1 to {maximum}")


def _bounded_corpus(
    connection: sqlite3.Connection, scope: AuthorizedScope, *,
    max_docs: int, max_bytes: int,
) -> tuple[int, int]:
    """Use the scoped primary key and SQL byte lengths; never load text to preflight."""
    rows = connection.execute(
        """SELECT length(CAST(canonical_content AS BLOB)) AS byte_count
           FROM memories WHERE tenant_id=? AND namespace=?
           ORDER BY memory_id LIMIT ?""",
        (scope.tenant_id, scope.namespace, max_docs + 1),
    )
    count = size = 0
    for row in rows:
        count += 1
        if count > max_docs:
            raise RetrievalLimitError("scoped canonical corpus exceeds document limit")
        size += row[0]
        if size > max_bytes:
            raise RetrievalLimitError("scoped canonical corpus exceeds byte limit")
    return count, size


class RetrievalReadSession:
    """All methods use one authorized SQLite snapshot; no connection escapes the context."""

    def __init__(self, store: SQLiteRetrievalStore, connection: sqlite3.Connection, scope: AuthorizedScope):
        self._store = store
        self._connection = connection
        self.scope = scope

    def _scoped_documents(self, known_at: datetime | None) -> tuple[tuple[str, str], ...]:
        c = self._connection
        count, _ = _bounded_corpus(
            c, self.scope, max_docs=self._store.max_lexical_docs,
            max_bytes=self._store.max_lexical_bytes,
        )
        rows = c.execute(
            """SELECT m.memory_id, m.canonical_content, d.doc_id,
                      f.canonical_content AS indexed_content
               FROM memories m
               LEFT JOIN memory_fts_docs d
                 ON d.tenant_id=m.tenant_id AND d.namespace=m.namespace
                AND d.memory_id=m.memory_id
               LEFT JOIN memory_fts f ON f.rowid=d.doc_id
               WHERE m.tenant_id=? AND m.namespace=?
               ORDER BY m.memory_id""",
            (self.scope.tenant_id, self.scope.namespace),
        )
        result: list[tuple[str, str]] = []
        seen = 0
        query = TemporalQuery(known_at=known_at) if known_at is not None else None
        for row in rows:
            seen += 1
            if row["doc_id"] is None or row["indexed_content"] != row["canonical_content"]:
                raise RetrievalIndexError("lexical index is stale or incomplete")
            if query is not None:
                state = self._store._memory_state_in_connection(c, self.scope, row["memory_id"], query)
                if state.known is not True:
                    continue
            result.append((row["memory_id"], row["canonical_content"]))
        if seen != count:
            raise RetrievalIndexError("lexical index mapping is inconsistent")
        return tuple(result)

    def lexical(
        self, query: str, *, limit: int = 40, known_at: datetime | None = None,
    ) -> tuple[LexicalHit, ...]:
        _validate_limit(limit, MAX_CANDIDATES, "lexical limit")
        if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_CHARS:
            raise ValueError("lexical query must contain 1 to 4096 characters")
        terms = tuple(dict.fromkeys(item.casefold() for item in _WORD.findall(query)))
        if not terms:
            return ()
        if len(terms) > MAX_QUERY_TERMS:
            raise RetrievalLimitError("lexical query exceeds term limit")
        # Every term is quoted as a literal FTS5 token; query grammar is never accepted.
        expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
        documents = self._scoped_documents(known_at)
        if not documents:
            return ()
        # The durable FTS5 inverted index generates matches. Scoped BM25 below
        # uses all authorized documents so other tenants cannot alter IDF/rank.
        durable = self._connection.execute(
            """SELECT d.memory_id FROM memory_fts
               JOIN memory_fts_docs d ON d.doc_id=memory_fts.rowid
               WHERE memory_fts MATCH ? AND d.tenant_id=? AND d.namespace=?
               ORDER BY d.memory_id LIMIT ?""",
            (expression, self.scope.tenant_id, self.scope.namespace, self._store.max_lexical_docs + 1),
        ).fetchall()
        if len(durable) > self._store.max_lexical_docs:
            raise RetrievalLimitError("durable lexical match set exceeds scope limit")
        visible_ids = {memory_id for memory_id, _ in documents}
        durable_ids = {row[0] for row in durable} & visible_ids
        with closing(sqlite3.connect(":memory:")) as scoped:
            scoped.execute("CREATE VIRTUAL TABLE scoped_fts USING fts5(memory_id UNINDEXED, content, tokenize='unicode61')")
            scoped.executemany(
                "INSERT INTO scoped_fts (memory_id,content) VALUES (?,?)", documents
            )
            rows = scoped.execute(
                """SELECT memory_id, bm25(scoped_fts) AS score FROM scoped_fts
                   WHERE scoped_fts MATCH ? ORDER BY score, memory_id LIMIT ?""",
                (expression, self._store.max_lexical_docs + 1),
            ).fetchall()
        if {row[0] for row in rows} != durable_ids:
            raise RetrievalIndexError("durable FTS5 match set differs from canonical scope")
        return tuple(
            LexicalHit(memory_id=row[0], rank=i + 1, score=float(row[1]))
            for i, row in enumerate(rows[:limit])
        )

    def semantic(
        self, query_vector: Sequence[float], space: EmbeddingSpace, *,
        limit: int = 40, scan_limit: int = MAX_VECTOR_SCAN,
        known_at: datetime | None = None,
    ) -> tuple[SemanticHit, ...]:
        _validate_limit(limit, MAX_CANDIDATES, "semantic limit")
        _validate_limit(scan_limit, MAX_VECTOR_SCAN, "vector scan limit")
        provider, model, version = _space_values(space)
        target_unit = _unit_vector(_vector(query_vector, space.dimension))
        c = self._connection
        total, _ = _bounded_corpus(
            c, self.scope, max_docs=min(scan_limit, self._store.max_vector_scan),
            max_bytes=self._store.max_lexical_bytes,
        )
        if total == 0:
            return ()
        compatible = c.execute(
            """SELECT dimension FROM embedding_spaces
               WHERE tenant_id=? AND namespace=? AND provider=? AND model=? AND config_version=?""",
            (self.scope.tenant_id, self.scope.namespace, provider, model, version),
        ).fetchone()
        if compatible is None:
            raise EmbeddingSpaceError("embedding space is not indexed in authorized scope")
        if compatible[0] != space.dimension:
            raise EmbeddingSpaceError("embedding dimension conflicts with stored model space")
        rows = c.execute(
            """SELECT m.memory_id,m.canonical_content,e.dimension,e.vector_blob,e.content_digest
               FROM memories m LEFT JOIN memory_embeddings e
                 ON e.tenant_id=m.tenant_id AND e.namespace=m.namespace
                AND e.memory_id=m.memory_id AND e.provider=? AND e.model=?
                AND e.config_version=?
               WHERE m.tenant_id=? AND m.namespace=? ORDER BY m.memory_id""",
            (provider, model, version, self.scope.tenant_id, self.scope.namespace),
        )
        scored: list[tuple[str, float]] = []
        temporal = TemporalQuery(known_at=known_at) if known_at is not None else None
        seen = 0
        for row in rows:
            seen += 1
            if temporal is not None:
                state = self._store._memory_state_in_connection(c, self.scope, row["memory_id"], temporal)
                if state.known is not True:
                    continue
            if row["vector_blob"] is None:
                raise EmbeddingSpaceError("embedding index is incomplete in authorized scope")
            if row["dimension"] != space.dimension:
                raise RetrievalIndexError("stored embedding dimension is inconsistent")
            if row["content_digest"] != content_digest(row["canonical_content"]):
                raise EmbeddingSpaceError("stored embedding is stale")
            normalized = _unit_vector(_decode_vector(row["vector_blob"], space.dimension))
            similarity = math.fsum(a*b for a,b in zip(target_unit, normalized, strict=True))
            scored.append((row["memory_id"], max(-1.0, min(1.0, similarity))))
        if seen != total:
            raise RetrievalIndexError("embedding corpus changed inside read snapshot")
        scored.sort(key=lambda x: (-x[1], x[0]))
        return tuple(SemanticHit(memory_id=memory_id, rank=i+1, score=score)
                     for i, (memory_id, score) in enumerate(scored[:limit]))

    def entity_candidates(
        self, names: Sequence[str], *, known_at: datetime | None = None, limit: int = 40,
    ) -> tuple[EntityHit, ...]:
        _validate_limit(limit, MAX_CANDIDATES, "entity limit")
        # Entity association/alias recording times are absent in schema 2.
        if known_at is not None:
            return ()
        if len(names) > 16:
            raise RetrievalLimitError("entity lookup name limit exceeded")
        normalized = tuple(dict.fromkeys(_normalize_name(name) for name in names if name.strip()))
        if not normalized:
            return ()
        c = self._connection
        found: dict[tuple[str, str], EntityHit] = {}
        for name in normalized:
            rows = c.execute(
                """SELECT me.memory_id, e.entity_id, e.canonical_name FROM entities e
                   JOIN memory_entities me
                     ON me.tenant_id=e.tenant_id AND me.namespace=e.namespace
                    AND me.entity_id=e.entity_id
                   WHERE e.tenant_id=? AND e.namespace=? AND e.normalized_name=?
                   UNION
                   SELECT me.memory_id, e.entity_id, a.alias_name FROM entity_aliases a
                   JOIN entities e
                     ON e.tenant_id=a.tenant_id AND e.namespace=a.namespace
                    AND e.entity_id=a.entity_id
                   JOIN memory_entities me
                     ON me.tenant_id=e.tenant_id AND me.namespace=e.namespace
                    AND me.entity_id=e.entity_id
                   WHERE a.tenant_id=? AND a.namespace=? AND a.normalized_alias=?
                   ORDER BY 1, 2 LIMIT ?""",
                (self.scope.tenant_id, self.scope.namespace, name,
                 self.scope.tenant_id, self.scope.namespace, name, limit+1),
            ).fetchall()
            if len(rows) > limit:
                raise RetrievalLimitError("entity lookup exceeds complete result limit")
            for row in rows:
                hit = EntityHit(row[0], row[1], row[2])
                found[(hit.memory_id, hit.entity_id)] = hit
            if len(found) > limit:
                raise RetrievalLimitError("entity lookup exceeds complete result limit")
        return tuple(found[key] for key in sorted(found))

    def topic_candidates(
        self, names: Sequence[str], *, known_at: datetime | None = None, limit: int = 40,
    ) -> tuple[TopicHit, ...]:
        _validate_limit(limit, MAX_CANDIDATES, "topic limit")
        if len(names) > 16:
            raise RetrievalLimitError("topic lookup name limit exceeded")
        normalized = {_normalize_name(name) for name in names if isinstance(name, str) and name.strip()}
        if not normalized:
            return ()
        c = self._connection
        topics = c.execute(
            """SELECT topic_id,name,recorded_at FROM topics
               WHERE tenant_id=? AND namespace=? ORDER BY topic_id LIMIT 501""",
            (self.scope.tenant_id, self.scope.namespace),
        ).fetchall()
        if len(topics) > 500:
            raise RetrievalLimitError("scoped topic catalog exceeds lookup limit")
        found: dict[tuple[str, str], TopicHit] = {}
        temporal = TemporalQuery(known_at=known_at) if known_at is not None else None
        for topic in topics:
            if _normalize_name(topic["name"]) not in normalized:
                continue
            if known_at is not None and topic["recorded_at"] > _timestamp(known_at):
                continue
            sql = """SELECT memory_id FROM topic_memberships
                     WHERE tenant_id=? AND namespace=? AND topic_id=?"""
            values: list[object] = [self.scope.tenant_id, self.scope.namespace, topic["topic_id"]]
            if known_at is not None:
                sql += " AND recorded_at<=?"
                values.append(_timestamp(known_at))
            sql += " ORDER BY memory_id LIMIT ?"
            values.append(limit+1)
            rows = c.execute(sql, values).fetchall()
            if len(rows) > limit:
                raise RetrievalLimitError("topic lookup exceeds complete result limit")
            for row in rows:
                if temporal is not None:
                    state = self._store._memory_state_in_connection(c,self.scope,row["memory_id"],temporal)
                    if state.known is not True:
                        continue
                hit = TopicHit(row["memory_id"],topic["topic_id"],topic["name"])
                found[(hit.memory_id,hit.topic_id)] = hit
            if len(found) > limit:
                raise RetrievalLimitError("topic lookup exceeds complete result limit")
        return tuple(found[key] for key in sorted(found))

    def memory(self, memory_id: str) -> MemoryNode | None:
        row = self._connection.execute(
            "SELECT * FROM memories WHERE tenant_id=? AND namespace=? AND memory_id=?",
            (self.scope.tenant_id, self.scope.namespace, memory_id),
        ).fetchone()
        return None if row is None else self._store._read_memory(self._connection, self.scope, row)

    def memory_state(self, memory_id: str, query: TemporalQuery) -> MemoryState:
        return self._store._memory_state_in_connection(
            self._connection, self.scope, memory_id, query,
        )

    def neighbors(
        self, node_id: str, *, allowed_relationships: tuple[RelationshipType, ...] | None = None,
        known_at: datetime | None = None, limit: int = 100,
    ) -> tuple[EdgeRecord, ...]:
        _validate_limit(limit, 1000, "neighbor limit")
        return self._store._neighbors_in_connection(
            self._connection, self.scope, node_id, direction="both",
            allowed_relationships=allowed_relationships, limit=limit, known_at=known_at,
        )


class SQLiteRetrievalStore(SQLiteGraphStore):
    """Persistent lexical/vector indexes with scoped snapshot reads."""

    def __init__(
        self, path=None, *, busy_timeout_ms: int = 5000,
        max_lexical_docs: int = MAX_LEXICAL_DOCS,
        max_lexical_bytes: int = MAX_LEXICAL_BYTES,
        max_vector_scan: int = MAX_VECTOR_SCAN,
    ) -> None:
        super().__init__(path, busy_timeout_ms=busy_timeout_ms)
        _validate_limit(max_lexical_docs, MAX_LEXICAL_DOCS, "lexical document ceiling")
        _validate_limit(max_lexical_bytes, MAX_LEXICAL_BYTES, "lexical byte ceiling")
        _validate_limit(max_vector_scan, MAX_VECTOR_SCAN, "vector scan ceiling")
        self.max_lexical_docs = max_lexical_docs
        self.max_lexical_bytes = max_lexical_bytes
        self.max_vector_scan = max_vector_scan

    @staticmethod
    def _require_v4(connection: sqlite3.Connection) -> None:
        SQLiteGraphStore._require_v3(connection)
        if user_version(connection) < 4:
            raise SchemaUpgradeRequiredError("retrieval storage requires explicit schema version 4 initialization")

    @contextmanager
    def read_snapshot(self, scope: AuthorizedScope) -> Iterator[RetrievalReadSession]:
        authorized = _authorized(scope)
        with self._graph_read() as connection:
            self._require_v4(connection)
            yield RetrievalReadSession(self, connection, authorized)

    @_translate_sqlite_errors
    def embedding_index_plan(
        self, scope: AuthorizedScope, space: EmbeddingSpace, *,
        batch_size: int = 32, after: MemoryCursor | None = None,
    ) -> MemoryPage:
        _space_values(space)
        _validate_limit(batch_size, MAX_EMBEDDING_BATCH, "embedding batch size")
        with self.read_snapshot(scope):
            return self.list_memories(scope, limit=batch_size, after=after)

    @_translate_sqlite_errors
    def pending_embeddings(
        self, scope: AuthorizedScope, space: EmbeddingSpace,
        memories: Sequence[MemoryNode],
    ) -> tuple[MemoryNode, ...]:
        authorized = _authorized(scope)
        provider, model, version = _space_values(space)
        if len(memories) > MAX_EMBEDDING_BATCH:
            raise ValueError("embedding plan batch exceeds 100 memories")
        pending: list[MemoryNode] = []
        with self.read_snapshot(authorized) as session:
            c = session._connection
            for memory in memories:
                if not isinstance(memory, MemoryNode):
                    raise TypeError("embedding plan requires MemoryNode values")
                if (memory.tenant_id, memory.namespace) != (authorized.tenant_id, authorized.namespace):
                    raise ScopeMismatchError("embedding plan memory differs from authorized scope")
                current = c.execute(
                    """SELECT canonical_content FROM memories
                       WHERE tenant_id=? AND namespace=? AND memory_id=?""",
                    (authorized.tenant_id, authorized.namespace, memory.memory_id),
                ).fetchone()
                if current is None or current[0] != memory.canonical_content:
                    raise EmbeddingSpaceError("canonical content changed during embedding plan")
                old = c.execute(
                    """SELECT content_digest,dimension FROM memory_embeddings
                       WHERE tenant_id=? AND namespace=? AND memory_id=?
                         AND provider=? AND model=? AND config_version=?""",
                    (authorized.tenant_id, authorized.namespace, memory.memory_id,
                     provider, model, version),
                ).fetchone()
                if old is None or old[0] != content_digest(memory.canonical_content):
                    pending.append(memory)
                elif old[1] != space.dimension:
                    raise EmbeddingSpaceError("stored embedding dimension conflicts with selected space")
        return tuple(pending)

    @_translate_sqlite_errors
    def put_embedding_batch(
        self, scope: AuthorizedScope, space: EmbeddingSpace,
        items: Sequence[tuple[str, str, Sequence[float]]],
    ) -> tuple[int, int]:
        authorized = _authorized(scope)
        provider, model, version = _space_values(space)
        if not isinstance(items, Sequence) or len(items) > MAX_EMBEDDING_BATCH:
            raise ValueError("embedding batch must contain at most 100 items")
        validated = []
        for memory_id, digest, vector in items:
            if not isinstance(memory_id, str) or not memory_id:
                raise ValueError("invalid memory ID")
            if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise ValueError("invalid canonical content digest")
            values = _vector(vector, space.dimension)
            validated.append((memory_id, digest, struct.pack(f"<{space.dimension}d", *values)))
        if len({item[0] for item in validated}) != len(validated):
            raise ValueError("embedding batch contains duplicate memory IDs")
        if not validated:
            return 0, 0
        indexed = skipped = 0
        with self._transaction() as c:
            self._require_v4(c)
            c.execute(
                """INSERT OR IGNORE INTO embedding_spaces
                   (tenant_id,namespace,provider,model,config_version,dimension)
                   VALUES (?,?,?,?,?,?)""",
                (authorized.tenant_id, authorized.namespace, provider, model, version, space.dimension),
            )
            dim = c.execute(
                """SELECT dimension FROM embedding_spaces WHERE tenant_id=? AND namespace=?
                   AND provider=? AND model=? AND config_version=?""",
                (authorized.tenant_id, authorized.namespace, provider, model, version),
            ).fetchone()[0]
            if dim != space.dimension:
                raise EmbeddingSpaceError("embedding dimension conflicts with stored model space")
            for memory_id, digest, blob in validated:
                row = c.execute(
                    """SELECT canonical_content FROM memories
                       WHERE tenant_id=? AND namespace=? AND memory_id=?""",
                    (authorized.tenant_id, authorized.namespace, memory_id),
                ).fetchone()
                if row is None:
                    raise ScopeMismatchError("embedding memory is absent from authorized scope")
                if content_digest(row[0]) != digest:
                    raise EmbeddingSpaceError("canonical content changed before embedding write")
                old = c.execute(
                    """SELECT content_digest,vector_blob FROM memory_embeddings
                       WHERE tenant_id=? AND namespace=? AND memory_id=?
                         AND provider=? AND model=? AND config_version=?""",
                    (authorized.tenant_id, authorized.namespace, memory_id, provider, model, version),
                ).fetchone()
                if old is not None and old[0] == digest and old[1] == blob:
                    skipped += 1
                    continue
                c.execute(
                    """INSERT INTO memory_embeddings
                       (tenant_id,namespace,memory_id,provider,model,config_version,
                        dimension,content_digest,vector_blob,generated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT (tenant_id,namespace,memory_id,provider,model,config_version)
                       DO UPDATE SET dimension=excluded.dimension,
                          content_digest=excluded.content_digest,
                          vector_blob=excluded.vector_blob,
                          generated_at=excluded.generated_at""",
                    (authorized.tenant_id, authorized.namespace, memory_id,
                     provider, model, version, space.dimension, digest, blob,
                     _timestamp(datetime.now(timezone.utc))),
                )
                indexed += 1
        return indexed, skipped

    @_translate_sqlite_errors
    def index_status(
        self, scope: AuthorizedScope, space: EmbeddingSpace | None = None,
    ) -> IndexStatus:
        authorized = _authorized(scope)
        with self.read_snapshot(authorized) as session:
            c = session._connection
            total, _ = _bounded_corpus(
                c, authorized, max_docs=self.max_lexical_docs,
                max_bytes=self.max_lexical_bytes,
            )
            lexical = c.execute(
                """SELECT COUNT(*) FROM memory_fts_docs d
                   JOIN memory_fts f ON f.rowid=d.doc_id
                   WHERE d.tenant_id=? AND d.namespace=?""",
                (authorized.tenant_id, authorized.namespace),
            ).fetchone()[0]
            lexical_stale = c.execute(
                """SELECT COUNT(*) FROM memories m
                   LEFT JOIN memory_fts_docs d
                     ON d.tenant_id=m.tenant_id AND d.namespace=m.namespace
                    AND d.memory_id=m.memory_id
                   LEFT JOIN memory_fts f ON f.rowid=d.doc_id
                   WHERE m.tenant_id=? AND m.namespace=?
                     AND (d.doc_id IS NULL OR f.rowid IS NULL
                          OR f.canonical_content<>m.canonical_content)""",
                (authorized.tenant_id, authorized.namespace),
            ).fetchone()[0]
            embedded = stale = 0
            if space is not None:
                provider, model, version = _space_values(space)
                rows = c.execute(
                    """SELECT e.content_digest,m.canonical_content,e.dimension
                       FROM memory_embeddings e JOIN memories m
                         ON m.tenant_id=e.tenant_id AND m.namespace=e.namespace
                        AND m.memory_id=e.memory_id
                       WHERE e.tenant_id=? AND e.namespace=? AND e.provider=?
                         AND e.model=? AND e.config_version=?""",
                    (authorized.tenant_id, authorized.namespace, provider, model, version),
                )
                for row in rows:
                    if row[2] != space.dimension:
                        raise RetrievalIndexError("stored embedding dimension is inconsistent")
                    if row[0] == content_digest(row[1]):
                        embedded += 1
                    else:
                        stale += 1
            return IndexStatus(total, lexical, embedded, stale,
                               self.max_lexical_docs, self.max_lexical_bytes,
                               self.max_vector_scan, lexical_stale)

    @_translate_sqlite_errors
    def rebuild_lexical(self, scope: AuthorizedScope, *, batch_size: int = 100) -> int:
        indexed, _ = self.index_lexical(scope, batch_size=batch_size, force=True)
        return indexed

    @_translate_sqlite_errors
    def index_lexical(
        self, scope: AuthorizedScope, *, batch_size: int = 100, force: bool = False,
    ) -> tuple[int, int]:
        _validate_limit(batch_size, 1000, "lexical batch size")
        authorized = _authorized(scope)
        with self.read_snapshot(authorized) as session:
            c = session._connection
            count, _ = _bounded_corpus(
                c, authorized, max_docs=self.max_lexical_docs,
                max_bytes=self.max_lexical_bytes,
            )
            # Freeze identities in this snapshot. New memories are indexed by trigger.
            ids = tuple(row[0] for row in c.execute(
                """SELECT memory_id FROM memories WHERE tenant_id=? AND namespace=?
                   ORDER BY memory_id""",
                (authorized.tenant_id, authorized.namespace),
            ))
            if len(ids) != count:
                raise RetrievalIndexError("canonical corpus changed inside read snapshot")
        indexed = skipped = processed_bytes = 0
        for offset in range(0, len(ids), batch_size):
            subset = ids[offset:offset+batch_size]
            marks = ",".join("?" for _ in subset)
            with self._transaction() as c:
                self._require_v4(c)
                current_bytes = c.execute(
                    f"""SELECT COALESCE(SUM(length(CAST(canonical_content AS BLOB))),0)
                        FROM memories WHERE tenant_id=? AND namespace=?
                          AND memory_id IN ({marks})""",
                    (authorized.tenant_id, authorized.namespace, *subset),
                ).fetchone()[0]
                processed_bytes += current_bytes
                if processed_bytes > self.max_lexical_bytes:
                    raise RetrievalLimitError("scoped lexical corpus grew beyond indexing byte limit")
                rows = c.execute(
                    f"""SELECT m.memory_id,m.canonical_content,d.doc_id,
                               f.canonical_content AS indexed_content
                        FROM memories m LEFT JOIN memory_fts_docs d
                          ON d.tenant_id=m.tenant_id AND d.namespace=m.namespace
                         AND d.memory_id=m.memory_id
                        LEFT JOIN memory_fts f ON f.rowid=d.doc_id
                        WHERE m.tenant_id=? AND m.namespace=?
                          AND m.memory_id IN ({marks}) ORDER BY m.memory_id""",
                    (authorized.tenant_id, authorized.namespace, *subset),
                ).fetchall()
                if len(rows) != len(subset):
                    raise RetrievalIndexError("canonical memory disappeared during indexing")
                for row in rows:
                    if row["doc_id"] is None:
                        c.execute(
                            """INSERT INTO memory_fts_docs (tenant_id,namespace,memory_id)
                               VALUES (?,?,?)""",
                            (authorized.tenant_id, authorized.namespace, row["memory_id"]),
                        )
                        doc_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                    else:
                        doc_id = row["doc_id"]
                    if not force and row["indexed_content"] == row["canonical_content"]:
                        skipped += 1
                        continue
                    c.execute("DELETE FROM memory_fts WHERE rowid=?", (doc_id,))
                    c.execute(
                        "INSERT INTO memory_fts (rowid,canonical_content) VALUES (?,?)",
                        (doc_id, row["canonical_content"]),
                    )
                    indexed += 1
        return indexed, skipped
